#!/usr/bin/env python3
"""Detached, read-only monitor for a frozen JJP efficiency campaign.

The monitor deliberately has no Condor or SSH mutating operation.  ``validate``
and ``launch`` (without ``--start``) are dry-run operations.  A live snapshot
requires ``snapshot --probe`` and a detached loop requires ``launch --start``.
All files written by a running watcher are confined to its monitor directory.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import fcntl
import hashlib
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SNAPSHOT_SCHEMA = "jjp-efficiency-monitor-snapshot/v1"
TARGET_SCHEMA = "jjp-efficiency-monitor-targets/v1"
ALERT_SCHEMA = "jjp-efficiency-monitor-alert/v1"
HEARTBEAT_SCHEMA = "jjp-efficiency-monitor-heartbeat/v1"
PID_SCHEMA = "jjp-efficiency-monitor-watcher/v1"
HEX64 = re.compile(r"^[0-9a-fA-F]{40,64}$")
PID_RE = re.compile(r"^[1-9][0-9]*(?:\.[0-9]+)?$")
CONDOR_STATUS = {
    1: "idle",
    2: "running",
    3: "removed",
    4: "completed",
    5: "held",
    6: "transferring",
    7: "suspended",
}
HISTORY_LIMIT = 10000


class MonitorError(ValueError):
    """A malformed target/configuration or an unsafe monitor invocation."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MonitorError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MonitorError(f"expected JSON object: {path}")
    return value


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    atomic_bytes(
        path,
        (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def confined(path: Path, root: Path) -> Path:
    """Resolve a path and reject paths outside the authorized monitor root."""
    root = root.resolve()
    path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise MonitorError(f"monitor output escapes monitor directory: {path}") from exc
    return path


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MonitorError(f"{field} must be a non-empty string")
    return value.strip()


def _validate_pid(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MonitorError(f"{field} must be a positive integer")
    return value


def _validate_dag_id(value: Any, field: str) -> str:
    text = _require_string(value, field)
    if not PID_RE.fullmatch(text):
        raise MonitorError(f"{field} must be an exact Condor cluster or cluster.proc ID")
    return text


def _normalise_targets(data: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate target metadata and return a canonical, hashable target set.

    The accepted shape is intentionally small.  A state ledger may carry it as
    ``monitor_targets``; a standalone target file uses the shape below.
    """
    if "monitor_targets" in data:
        data = data["monitor_targets"]
        if not isinstance(data, dict):
            raise MonitorError("monitor_targets must be an object")
    schema = data.get("schema_version", TARGET_SCHEMA)
    if schema != TARGET_SCHEMA:
        raise MonitorError(f"unexpected target schema: {schema!r}")
    campaign_id = _require_string(data.get("campaign_id"), "campaign_id")
    identity = _require_string(data.get("campaign_identity_sha256"), "campaign_identity_sha256")
    if not HEX64.fullmatch(identity):
        raise MonitorError("campaign_identity_sha256 must be a hexadecimal SHA-256")
    revision = data.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise MonitorError("target config revision must be a non-negative integer")
    condor = data.get("condor", [])
    if not isinstance(condor, list):
        raise MonitorError("condor targets must be a list")
    canonical_condor: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(condor):
        if not isinstance(item, dict):
            raise MonitorError(f"condor target {index} must be an object")
        sample = _require_string(item.get("sample"), f"condor[{index}].sample")
        schedd = _require_string(item.get("schedd"), f"condor[{index}].schedd")
        dag_id = _validate_dag_id(item.get("dag_id"), f"condor[{index}].dag_id")
        key = (schedd, dag_id)
        if key in seen:
            raise MonitorError(f"duplicate Condor target {schedd}/{dag_id}")
        seen.add(key)
        row = {"sample": sample, "schedd": schedd, "dag_id": dag_id}
        for optional in ("dag_path", "history_log"):
            if optional in item:
                row[optional] = _require_string(item[optional], f"condor[{index}].{optional}")
        canonical_condor.append(row)

    hepthu_raw = data.get("hepthu")
    hepthu: dict[str, Any] | None = None
    if hepthu_raw is not None:
        if not isinstance(hepthu_raw, dict):
            raise MonitorError("hepthu target must be an object")
        enabled = hepthu_raw.get("enabled", True)
        if not isinstance(enabled, bool):
            raise MonitorError("hepthu.enabled must be boolean")
        if enabled:
            hepthu = {
                "enabled": True,
                "host": _require_string(hepthu_raw.get("host"), "hepthu.host"),
                "status_path": _require_string(hepthu_raw.get("status_path"), "hepthu.status_path"),
                "log_path": _require_string(hepthu_raw.get("log_path"), "hepthu.log_path"),
                "command_sha256": _require_string(hepthu_raw.get("command_sha256"), "hepthu.command_sha256"),
            }
            if "ssh_config" in hepthu_raw:
                hepthu["ssh_config"] = _require_string(hepthu_raw["ssh_config"], "hepthu.ssh_config")
            if "user" in hepthu_raw:
                user = _require_string(hepthu_raw["user"], "hepthu.user")
                if any(char.isspace() for char in user) or "@" in user:
                    raise MonitorError("hepthu.user must be a single SSH username")
                hepthu["user"] = user
            if "port" in hepthu_raw:
                port = hepthu_raw["port"]
                if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
                    raise MonitorError("hepthu.port must be an integer from 1 through 65535")
                hepthu["port"] = port
            if not HEX64.fullmatch(hepthu["command_sha256"]):
                raise MonitorError("hepthu.command_sha256 must be hexadecimal SHA-256")
            if "pid" in hepthu_raw:
                hepthu["pid"] = _validate_pid(hepthu_raw["pid"], "hepthu.pid")
            if "pid_path" in hepthu_raw:
                hepthu["pid_path"] = _require_string(hepthu_raw["pid_path"], "hepthu.pid_path")
            if "pid" not in hepthu and "pid_path" not in hepthu:
                raise MonitorError("hepthu requires an exact pid or pid_path")
            for optional in ("lock_path", "start_time"):
                if optional in hepthu_raw:
                    hepthu[optional] = hepthu_raw[optional]
            if "artifacts" in hepthu_raw:
                artifacts = hepthu_raw["artifacts"]
                if not isinstance(artifacts, list) or not all(isinstance(x, str) and x for x in artifacts):
                    raise MonitorError("hepthu.artifacts must be a list of paths")
                hepthu["artifacts"] = list(artifacts)
    canonical: dict[str, Any] = {
        "schema_version": TARGET_SCHEMA,
        "campaign_id": campaign_id,
        "campaign_identity_sha256": identity,
        "revision": revision,
        "condor": canonical_condor,
    }
    if hepthu is not None:
        canonical["hepthu"] = hepthu
    if state is not None:
        if state.get("campaign_id") != campaign_id:
            raise MonitorError("target campaign_id does not match ledger")
        if state.get("campaign_identity_sha256") != identity:
            raise MonitorError("target identity does not match ledger")
    return canonical


def load_targets(path: Path, state_path: Path | None = None) -> dict[str, Any]:
    state = read_json(state_path) if state_path else None
    data = read_json(path)
    # A target config can be wrapped in {targets: ...} for handoff reports.
    if "targets" in data and isinstance(data["targets"], dict) and "campaign_id" not in data:
        data = data["targets"]
    return _normalise_targets(data, state)


def _run(argv: list[str], timeout: float, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> dict[str, Any]:
    started = time.time()
    try:
        result = runner(argv, text=True, capture_output=True, timeout=timeout, check=False)
        rc = int(result.returncode)
        stdout = result.stdout or ""
        stderr = result.stderr or ""
    except subprocess.TimeoutExpired as exc:
        rc, stdout, stderr = 124, str(exc.stdout or ""), f"command timeout after {timeout}s"
    except OSError as exc:
        rc, stdout, stderr = 127, "", str(exc)
    return {
        "argv": argv,
        "rc": rc,
        "stdout": stdout,
        "stderr": stderr[-4000:],
        "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat().replace("+00:00", "Z"),
        "ended_at": now(),
    }


def _records(result: dict[str, Any]) -> list[dict[str, Any]] | None:
    if result["rc"] != 0:
        return None
    try:
        value = json.loads(result["stdout"] or "[]")
    except json.JSONDecodeError:
        return None
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        return None
    return value


def _dag_identity(dag_id: str) -> tuple[int, int, str]:
    """Return the exact controller identity and inherited DAG batch ID."""
    bits = dag_id.split(".")
    cluster = int(bits[0])
    proc = int(bits[1]) if len(bits) == 2 else 0
    return cluster, proc, f"{cluster}.{proc}"


def _dag_constraint(dag_id: str) -> str:
    """Select one root controller and every ad inheriting its DAG identity.

    ``JobBatchId`` is inherited by direct children and nested SubDAG payloads.
    ``DAGManJobId`` keeps compatibility with direct child ads that predate (or
    do not expose) ``JobBatchId``. All terms remain rooted in the exact
    recorded top-level controller rather than a user or time-window search.
    """
    cluster, proc, batch_id = _dag_identity(dag_id)
    return (
        f"((ClusterId == {cluster} && ProcId == {proc}) || "
        f'JobBatchId == "{batch_id}" || DAGManJobId == {cluster})'
    )


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _job_id(row: dict[str, Any]) -> str | None:
    cluster, proc = _integer(row.get("ClusterId")), _integer(row.get("ProcId"))
    if cluster is None or proc is None:
        return None
    return f"{cluster}.{proc}"


def _exit_code(row: dict[str, Any]) -> int | None:
    if row.get("ExitBySignal") is True:
        signal = _integer(row.get("ExitSignal"))
        return 128 + (signal or 0)
    for key in ("ExitCode", "ExitStatus"):
        code = _integer(row.get(key))
        if code is not None:
            return code
    return None


def _record_timestamp(row: dict[str, Any]) -> int:
    for key in ("EnteredCurrentStatus", "CompletionDate", "QDate"):
        value = _integer(row.get(key))
        if value is not None:
            return value
    return 0


def _record_state(row: dict[str, Any], *, historical: bool = False) -> str:
    status = CONDOR_STATUS.get(_integer(row.get("JobStatus")) or 0, "unknown")
    if not historical or status != "completed":
        return status
    code = _exit_code(row)
    if code == 0:
        return "success"
    if code is not None:
        return "failed"
    return "unknown"


def _is_controller(row: dict[str, Any], cluster: int, proc: int) -> bool:
    return (
        (_integer(row.get("ClusterId")), _integer(row.get("ProcId"))) == (cluster, proc)
        or _integer(row.get("JobUniverse")) == 7
    )


def _status_summary(rows: list[dict[str, Any]], *, historical: bool) -> dict[str, Any]:
    counts = Counter(_record_state(row, historical=historical) for row in rows)
    held = [
        job_id
        for row in rows
        if _record_state(row, historical=historical) == "held"
        if (job_id := _job_id(row))
    ]
    failed = [
        job_id
        for row in rows
        if _record_state(row, historical=historical) == "failed"
        if (job_id := _job_id(row))
    ]
    return {
        "total": len(rows),
        "counts": dict(sorted(counts.items())),
        "held_job_ids": held,
        "failed_job_ids": failed,
    }


def _strongest_live_state(rows: list[dict[str, Any]]) -> str:
    states = {_record_state(row) for row in rows}
    for state in (
        "held", "running", "transferring", "suspended", "idle", "removed", "completed"
    ):
        if state in states:
            return state
    return "unknown"


def _latest_record(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: (
            _record_timestamp(row),
            _integer(row.get("ClusterId")) or -1,
            _integer(row.get("ProcId")) or -1,
        ),
    )


def _planned_dag_nodes(
    target: dict[str, Any],
) -> tuple[set[str] | None, dict[str, Any]]:
    """Read the recorded DAG topology without running a command.

    The current campaign has SHARD plus POST nodes. Recursing through recorded
    ``SUBDAG EXTERNAL`` paths keeps the accounting useful if that topology
    grows.
    """
    raw_path = target.get("dag_path")
    if not raw_path:
        return None, {"path": None, "readable": False, "error": None}
    root = Path(raw_path).expanduser()
    nodes: set[str] = set()
    visited: set[Path] = set()

    def visit(path: Path) -> None:
        resolved = path.resolve()
        if resolved in visited:
            raise MonitorError(f"recursive DAG reference: {resolved}")
        visited.add(resolved)
        try:
            lines = resolved.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError as exc:
            raise MonitorError(f"cannot read recorded DAG {resolved}: {exc}") from exc
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                fields = shlex.split(line)
            except ValueError:
                continue
            if not fields:
                continue
            directive = fields[0].upper()
            if directive in {"JOB", "FINAL"} and len(fields) >= 2:
                nodes.add(fields[1])
            elif (
                directive == "SUBDAG"
                and len(fields) >= 4
                and fields[1].upper() == "EXTERNAL"
            ):
                nodes.add(fields[2])
                child = Path(fields[3])
                visit(child if child.is_absolute() else resolved.parent / child)
        visited.remove(resolved)

    try:
        visit(root)
    except MonitorError as exc:
        return None, {"path": str(root), "readable": False, "error": str(exc)}
    return nodes, {"path": str(root.resolve()), "readable": True, "error": None}


def _logical_dag_summary(
    target: dict[str, Any],
    live_rows: list[dict[str, Any]],
    history_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    planned, plan = _planned_dag_nodes(target)
    live_by_node: dict[str, list[dict[str, Any]]] = {}
    history_by_node: dict[str, list[dict[str, Any]]] = {}
    for row in live_rows:
        name = row.get("DAGNodeName")
        if isinstance(name, str) and name:
            live_by_node.setdefault(name, []).append(row)
    for row in history_rows:
        name = row.get("DAGNodeName")
        if isinstance(name, str) and name:
            history_by_node.setdefault(name, []).append(row)
    known = set(live_by_node) | set(history_by_node)
    names = (planned | known) if planned is not None else known
    node_states: dict[str, str] = {}
    for name in names:
        if live_by_node.get(name):
            node_states[name] = _strongest_live_state(live_by_node[name])
        elif history_by_node.get(name):
            latest = _latest_record(history_by_node[name])
            node_states[name] = _record_state(latest or {}, historical=True)
        else:
            node_states[name] = "pending"
    counts = Counter(node_states.values())
    planned_complete = bool(
        planned is not None
        and planned
        and all(node_states.get(name) == "success" for name in planned)
    )
    return {
        "plan": plan,
        "planned_total": len(planned) if planned is not None else None,
        "known_total": len(known),
        "counts": dict(sorted(counts.items())),
        "planned_complete": planned_complete,
        "exceptional_nodes": {
            name: state
            for name, state in sorted(node_states.items())
            if state in {"failed", "held", "removed", "unknown"}
        },
    }


def condor_probe(target: dict[str, Any], timeout: float = 20.0, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> dict[str, Any]:
    """Query one recorded schedd/root DAG and its descendants, read-only."""
    schedd, dag_id = target["schedd"], target["dag_id"]
    cluster, proc, batch_id = _dag_identity(dag_id)
    constraint = _dag_constraint(dag_id)
    attributes = ",".join(
        (
            "ClusterId", "ProcId", "JobStatus", "JobUniverse", "DAGManJobId",
            "DAGNodeName", "JobBatchId", "HoldReason", "HoldReasonCode",
            "HoldReasonSubCode", "ExitCode", "ExitStatus", "ExitBySignal",
            "ExitSignal", "CompletionDate", "EnteredCurrentStatus", "QDate",
            "NumJobStarts",
        )
    )
    queue_argv = [
        "condor_q", "-name", schedd, "-constraint", constraint,
        "-attributes", attributes, "-json",
    ]
    history_argv = [
        "condor_history", "-name", schedd, "-constraint", constraint,
        "-attributes", attributes, "-json", "-limit", str(HISTORY_LIMIT),
    ]
    queue = _run(queue_argv, timeout, runner)
    history = _run(history_argv, timeout, runner)
    qrows, hrows = _records(queue), _records(history)
    query_ok = qrows is not None and hrows is not None
    live_rows = qrows or []
    history_rows = hrows or []
    live_controllers = [
        row for row in live_rows if _is_controller(row, cluster, proc)
    ]
    live_payload = [
        row for row in live_rows if not _is_controller(row, cluster, proc)
    ]
    history_controllers = [
        row for row in history_rows if _is_controller(row, cluster, proc)
    ]
    history_payload = [
        row for row in history_rows if not _is_controller(row, cluster, proc)
    ]
    root_live = [
        row
        for row in live_rows
        if (_integer(row.get("ClusterId")), _integer(row.get("ProcId")))
        == (cluster, proc)
    ]
    root_history = [
        row
        for row in history_rows
        if (_integer(row.get("ClusterId")), _integer(row.get("ProcId")))
        == (cluster, proc)
    ]
    latest_root_history = _latest_record(root_history)
    root_history_state = (
        _record_state(latest_root_history, historical=True)
        if latest_root_history is not None
        else None
    )
    logical = _logical_dag_summary(target, live_rows, history_rows)
    live_held = any(_record_state(row) == "held" for row in live_rows)
    live_present = bool(live_rows)
    logical_failed = logical["counts"].get("failed", 0) > 0
    if not query_ok:
        state = "unknown"
    elif live_held:
        state = "held"
    elif live_present:
        # A failed historical attempt may have an automatic DAGMan retry live
        # now. Current queue evidence wins until the controller terminates.
        state = "active"
    elif root_history_state == "success" or logical["planned_complete"]:
        state = "complete"
    elif root_history_state in {"failed", "removed"} or logical_failed:
        state = "failed"
    else:
        # In particular, two successful-but-empty queries carry no completion
        # evidence. Queue shrink after completion is normal; it is not proof.
        state = "unknown"
    return {
        "kind": "condor",
        "sample": target["sample"],
        "schedd": schedd,
        "dag_id": dag_id,
        "root_controller_id": batch_id,
        "query_constraint": constraint,
        "queue": {
            "rc": queue["rc"],
            "records": qrows,
            "source_timestamp": queue["ended_at"],
            "stderr": queue["stderr"],
        },
        "history": {
            "rc": history["rc"],
            "records": hrows,
            "source_timestamp": history["ended_at"],
            "stderr": history["stderr"],
            "limit": HISTORY_LIMIT,
            "possibly_truncated": bool(
                hrows is not None and len(hrows) >= HISTORY_LIMIT
            ),
        },
        "logical_dag": logical,
        "controllers": {
            "live": _status_summary(live_controllers, historical=False),
            "history": _status_summary(history_controllers, historical=True),
            "root_live_state": _strongest_live_state(root_live) if root_live else None,
            "root_history_state": root_history_state,
        },
        "live_payload": _status_summary(live_payload, historical=False),
        "history_summary": {
            "all": _status_summary(history_rows, historical=True),
            "controllers": _status_summary(history_controllers, historical=True),
            "payload": _status_summary(history_payload, historical=True),
        },
        "query_complete": query_ok,
        "probe_rc": {"queue": queue["rc"], "history": history["rc"]},
        "observed_state": state,
    }


def _remote_script(target: dict[str, Any]) -> str:
    """Build a fixed, shell-quoted read-only probe for one hepthu target."""
    pid_expr = str(target.get("pid", "")) if "pid" in target else ""
    pid_path = target.get("pid_path", "")
    status, log = target["status_path"], target["log_path"]
    lines = ["set +e"]
    if pid_expr:
        lines.append(f"p={shlex.quote(pid_expr)}")
    else:
        lines.append(f"p=$(cat -- {shlex.quote(pid_path)} 2>/dev/null)")
    lines += [
        "case \"$p\" in ''|*[!0-9]*) echo PID_INVALID=1;; *) kill -0 \"$p\" 2>/dev/null && echo PID_ALIVE=1 || echo PID_ALIVE=0;; esac",
        f"if test -r {shlex.quote(status)}; then echo STATUS_BEGIN; cat -- {shlex.quote(status)}; echo STATUS_END; else echo STATUS_MISSING=1; fi",
        f"if test -e {shlex.quote(log)}; then stat -c 'LOG_SIZE=%s LOG_MTIME=%Y' -- {shlex.quote(log)} 2>/dev/null; else echo LOG_MISSING=1; fi",
    ]
    for artifact in target.get("artifacts", []):
        lines.append(f"if test -r {shlex.quote(artifact)}; then echo ARTIFACT={shlex.quote(artifact)}; else echo ARTIFACT_MISSING={shlex.quote(artifact)}; fi")
    return "\n".join(lines)


def hepthu_probe(target: dict[str, Any], timeout: float = 20.0, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run, campaign_id: str | None = None) -> dict[str, Any]:
    script = _remote_script(target)
    argv = ["ssh"]
    if target.get("ssh_config"):
        argv += ["-F", target["ssh_config"]]
    if target.get("port") is not None:
        argv += ["-p", str(target["port"])]
    argv += ["-o", "BatchMode=yes", "-o", f"ConnectTimeout={max(1, int(timeout))}", "-o", "ConnectionAttempts=1"]
    destination = f"{target['user']}@{target['host']}" if target.get("user") else target["host"]
    argv += [destination, "sh", "-c", script]
    result = _run(argv, timeout + 2, runner)
    text = result["stdout"]
    pid_alive = "PID_ALIVE=1" in text
    status_missing = "STATUS_MISSING=1" in text
    status: dict[str, Any] | None = None
    if "STATUS_BEGIN" in text and "STATUS_END" in text:
        raw = text.split("STATUS_BEGIN", 1)[1].split("STATUS_END", 1)[0].strip()
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                status = value
        except json.JSONDecodeError:
            status = None
    state_key = status.get("state") if status else None
    if state_key is None and status:
        state_key = status.get("status")
    identity_ok = bool(status and status.get("command_sha256") == target["command_sha256"] and (campaign_id is None or status.get("campaign_id") == campaign_id))
    if result["rc"] != 0 or status_missing:
        observed = "unknown"
    elif not identity_ok:
        observed = "identity_lost"
    elif status and state_key == "failed":
        observed = "failed"
    elif status and state_key in {"finished", "success", "complete", "completed"} and status.get("exit_code", 0) != 0:
        observed = "failed"
    elif status and state_key in {"finished", "success", "complete", "completed"} and status.get("exit_code", 0) == 0 and not pid_alive:
        observed = "complete"
    elif pid_alive or (status and state_key in {"started", "running", "active"}):
        observed = "active"
    else:
        observed = "unknown"
    log_match = re.search(r"LOG_SIZE=(\d+) LOG_MTIME=([0-9.]+)", text)
    return {
        "kind": "hepthu",
        "host": target["host"],
        "user": target.get("user"),
        "port": target.get("port"),
        "ssh_config": target.get("ssh_config"),
        "endpoint": destination,
        "pid": target.get("pid"),
        "pid_path": target.get("pid_path"),
        "status_path": target["status_path"],
        "log_path": target["log_path"],
        "probe_rc": result["rc"],
        "identity_ok": identity_ok,
        "campaign_id_match": bool(status and (campaign_id is None or status.get("campaign_id") == campaign_id)),
        "pid_alive": pid_alive,
        "status": status,
        "log": ({"size": int(log_match.group(1)), "mtime": float(log_match.group(2))} if log_match else None),
        "observed_state": observed,
        "source_timestamp": result["ended_at"],
        "stderr": result["stderr"],
    }


def _aggregate(probes: list[dict[str, Any]]) -> str:
    states = [item.get("observed_state") for item in probes]
    if not states:
        return "quiet"
    if any(state in {"identity_lost", "failed", "held"} for state in states):
        return "blocked"
    if any(state == "unknown" for state in states):
        return "unknown"
    if all(state == "complete" for state in states):
        return "complete"
    if any(state == "active" for state in states):
        return "active"
    return "quiet"


def _load_previous(monitor_dir: Path) -> dict[str, Any] | None:
    path = monitor_dir / "latest.json"
    return read_json(path) if path.is_file() else None


def _alert_candidates(snapshot: dict[str, Any], previous: dict[str, Any] | None, stale_after: float | None = None) -> list[dict[str, Any]]:
    state = snapshot["observed_state"]
    old_state = previous.get("observed_state") if previous else None
    candidates: list[tuple[str, str, str]] = []
    if state != old_state:
        candidates.append(("state_transition", "info", f"campaign state {old_state or 'none'} -> {state}"))
    previous_probes = (previous or {}).get("probes", [])
    for probe in snapshot["probes"]:
        probe_state = probe.get("observed_state")
        if probe_state in {"failed", "held", "identity_lost", "unknown"}:
            key = (probe.get("kind"), probe.get("sample"), probe.get("dag_id"), probe.get("host"))
            prior = next((item for item in previous_probes if (item.get("kind"), item.get("sample"), item.get("dag_id"), item.get("host")) == key), None)
            if prior and prior.get("observed_state") == probe_state:
                continue
            candidates.append((probe_state, "error" if probe_state != "unknown" else "warning", f"{probe.get('kind')} probe observed {probe_state}"))
    if state == "complete" and old_state != "complete":
        candidates.append(("terminal_completion", "info", "all recorded targets completed"))
    if snapshot.get("stop_requested"):
        candidates.append(("stop_requested", "info", "orchestrator stop sentinel acknowledged"))
    return [
        {"schema_version": ALERT_SCHEMA, "alert_id": str(uuid.uuid4()), "at": snapshot["captured_at"], "snapshot_id": snapshot["snapshot_id"], "kind": kind, "severity": severity, "message": message}
        for kind, severity, message in candidates
    ]


def capture_snapshot(targets: dict[str, Any], monitor_dir: Path, *, watcher_pid: int | None = None, probe: bool = False, timeout: float = 20.0, stop_requested: bool = False, stale_after: float | None = None, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run, write: bool = True) -> dict[str, Any]:
    monitor_dir = monitor_dir.resolve()
    if write:
        monitor_dir.mkdir(parents=True, exist_ok=True)
    probes: list[dict[str, Any]] = []
    if probe:
        for target in targets["condor"]:
            probes.append(condor_probe(target, timeout, runner))
        if targets.get("hepthu"):
            probes.append(hepthu_probe(targets["hepthu"], timeout, runner, campaign_id=targets["campaign_id"]))
    else:
        probes = [{"kind": "condor", "sample": x["sample"], "schedd": x["schedd"], "dag_id": x["dag_id"], "probe_rc": None, "observed_state": "not_probed"} for x in targets["condor"]]
        if targets.get("hepthu"):
            target = targets["hepthu"]
            destination = f"{target['user']}@{target['host']}" if target.get("user") else target["host"]
            probes.append({"kind": "hepthu", "host": target["host"], "user": target.get("user"), "port": target.get("port"), "ssh_config": target.get("ssh_config"), "endpoint": destination, "probe_rc": None, "observed_state": "not_probed"})
    captured = now()
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA,
        "snapshot_id": f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid.uuid4().hex[:10]}",
        "captured_at": captured,
        "campaign_id": targets["campaign_id"],
        "campaign_identity_sha256": targets["campaign_identity_sha256"],
        "campaign_identity": {"campaign_id": targets["campaign_id"], "campaign_identity_sha256": targets["campaign_identity_sha256"]},
        "target_config_revision": targets["revision"],
        "watcher_pid": watcher_pid,
        "watcher": {"pid": watcher_pid, "host": socket.gethostname()},
        "target_set": {"condor": [{"sample": x["sample"], "schedd": x["schedd"], "dag_id": x["dag_id"]} for x in targets["condor"]], "hepthu": ({"host": targets["hepthu"]["host"], "user": targets["hepthu"].get("user"), "port": targets["hepthu"].get("port"), "ssh_config": targets["hepthu"].get("ssh_config"), "endpoint": (f"{targets['hepthu']['user']}@{targets['hepthu']['host']}" if targets["hepthu"].get("user") else targets["hepthu"]["host"])} if targets.get("hepthu") else None)},
        "probe_rc": {str(i): p.get("probe_rc") for i, p in enumerate(probes)},
        "probes": probes,
        "observed_state": _aggregate(probes) if probe else "not_probed",
        "source_timestamps": {str(i): (p.get("source_timestamp") or p.get("queue", {}).get("source_timestamp")) for i, p in enumerate(probes)},
        "stop_requested": stop_requested,
        "stop_acknowledged": stop_requested,
    }
    if write:
        previous = _load_previous(monitor_dir)
        alerts = _alert_candidates(snapshot, previous)
        snapshot["alerts"] = alerts
        snapshot_dir = confined(monitor_dir / "snapshots", monitor_dir)
        snapshot_path = snapshot_dir / f"{snapshot['snapshot_id']}.json"
        atomic_json(snapshot_path, snapshot)
        atomic_json(monitor_dir / "latest.json", snapshot)
        for alert in alerts:
            append_jsonl(monitor_dir / "alerts.jsonl", alert)
        atomic_json(monitor_dir / "heartbeat.json", {"schema_version": HEARTBEAT_SCHEMA, "watcher_pid": watcher_pid, "campaign_id": targets["campaign_id"], "target_config_revision": targets["revision"], "last_snapshot_id": snapshot["snapshot_id"], "last_snapshot_at": captured, "stale_after_seconds": stale_after, "updated_at": captured})
        snapshot["snapshot_path"] = str(snapshot_path)
    return snapshot


def validate(args: argparse.Namespace) -> dict[str, Any]:
    targets = load_targets(args.targets, args.state)
    result = {"schema_version": TARGET_SCHEMA, "valid": True, "campaign_id": targets["campaign_id"], "campaign_identity_sha256": targets["campaign_identity_sha256"], "target_config_revision": targets["revision"], "target_count": len(targets["condor"]) + int(bool(targets.get("hepthu"))), "writes": False, "remote_probe": False}
    return result


def _monitor_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--targets", type=Path, required=True, help="frozen monitor target JSON")
    parser.add_argument("--state", type=Path, help="optional campaign ledger for identity cross-check")
    parser.add_argument("--monitor-dir", type=Path, required=True, help="authorized local campaign monitor directory")
    parser.add_argument("--timeout", type=float, default=20.0)


def snapshot_command(args: argparse.Namespace) -> int:
    targets = load_targets(args.targets, args.state)
    if not args.probe:
        result = capture_snapshot(targets, args.monitor_dir, watcher_pid=None, probe=False, write=False)
        result["dry_run"] = True
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    result = capture_snapshot(targets, args.monitor_dir, watcher_pid=os.getpid(), probe=True, timeout=args.timeout, write=True)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _stop_requested(monitor_dir: Path) -> bool:
    return (monitor_dir / "STOP").is_file()


def watch_command(args: argparse.Namespace) -> int:
    if not args.run:
        raise MonitorError("watch is an internal command; use launch --start")
    targets = load_targets(args.targets, args.state)
    monitor_dir = args.monitor_dir.resolve()
    monitor_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(monitor_dir / "watcher.json", {"schema_version": PID_SCHEMA, "pid": os.getpid(), "started_at": now(), "campaign_id": targets["campaign_id"], "target_config_revision": targets["revision"]})
    frozen_campaign_id = targets["campaign_id"]
    frozen_identity = targets["campaign_identity_sha256"]
    target_fingerprint = stable_hash({key: value for key, value in targets.items() if key != "revision"})
    while True:
        # Reload every cycle.  An added target is accepted only when the
        # orchestrator atomically published a new, incremented revision.
        current = load_targets(args.targets, args.state)
        if current["campaign_id"] != frozen_campaign_id or current["campaign_identity_sha256"] != frozen_identity:
            raise MonitorError("campaign identity changed while watcher was running")
        if current["revision"] < targets["revision"]:
            raise MonitorError("target config revision moved backwards")
        current_fingerprint = stable_hash({key: value for key, value in current.items() if key != "revision"})
        if current["revision"] == targets["revision"] and current_fingerprint != target_fingerprint:
            raise MonitorError("target set changed without an incremented atomic config revision")
        targets = current
        target_fingerprint = current_fingerprint
        stop = _stop_requested(monitor_dir)
        snapshot = capture_snapshot(targets, monitor_dir, watcher_pid=os.getpid(), probe=True, timeout=args.timeout, stop_requested=stop, stale_after=2 * args.active_interval, write=True)
        if stop or snapshot["observed_state"] in {"complete", "blocked"}:
            if stop:
                atomic_json(monitor_dir / "stop_ack.json", {"schema_version": PID_SCHEMA, "acknowledged": True, "watcher_pid": os.getpid(), "snapshot_id": snapshot["snapshot_id"], "at": now()})
            break
        interval = args.active_interval if snapshot["observed_state"] == "active" else args.quiet_interval
        atomic_json(monitor_dir / "heartbeat.json", {"schema_version": HEARTBEAT_SCHEMA, "watcher_pid": os.getpid(), "campaign_id": targets["campaign_id"], "target_config_revision": targets["revision"], "last_snapshot_id": snapshot["snapshot_id"], "last_snapshot_at": snapshot["captured_at"], "stale_after_seconds": 2 * interval, "next_poll_after_seconds": interval, "updated_at": now()})
        # One-second slices make STOP prompt without holding SSH/Condor
        # resources; each probe process has already exited before this wait.
        deadline = time.monotonic() + interval
        while time.monotonic() < deadline:
            if _stop_requested(monitor_dir):
                break
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
    return 0


def launch_command(args: argparse.Namespace) -> int:
    targets = load_targets(args.targets, args.state)
    monitor_dir = args.monitor_dir.resolve()
    script = Path(__file__).resolve()
    argv = [sys.executable, str(script), "watch", "--run", "--targets", str(args.targets.resolve()), "--monitor-dir", str(monitor_dir), "--timeout", str(args.timeout), "--active-interval", str(args.active_interval), "--quiet-interval", str(args.quiet_interval)]
    if args.state:
        argv += ["--state", str(args.state.resolve())]
    hepthu = targets.get("hepthu")
    endpoint = None
    if hepthu:
        endpoint = {"host": hepthu["host"], "user": hepthu.get("user"), "port": hepthu.get("port"), "ssh_config": hepthu.get("ssh_config"), "destination": (f"{hepthu['user']}@{hepthu['host']}" if hepthu.get("user") else hepthu["host"])}
    plan = {"dry_run": not args.start, "started": False, "watcher_argv": argv, "campaign_id": targets["campaign_id"], "target_config_revision": targets["revision"], "monitor_dir": str(monitor_dir), "target_set": {"condor": [{"sample": x["sample"], "schedd": x["schedd"], "dag_id": x["dag_id"]} for x in targets["condor"]], "hepthu": endpoint}, "writes": ["watcher.json", "heartbeat.json", "latest.json", "snapshots/*.json", "alerts.jsonl", "stop_ack.json"]}
    if not args.start:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    monitor_dir.mkdir(parents=True, exist_ok=True)
    pid_path = confined(monitor_dir / "watcher.pid", monitor_dir)
    if pid_path.exists():
        try:
            old_pid = int(pid_path.read_text(encoding="utf-8").strip())
            os.kill(old_pid, 0)
        except (OSError, ValueError):
            pass
        else:
            raise MonitorError(f"watcher already running with pid {old_pid}")
    log = (monitor_dir / "watcher.log").open("ab")
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    atomic_bytes(pid_path, f"{process.pid}\n".encode("ascii"))
    plan.update({"started": True, "dry_run": False, "watcher_pid": process.pid, "started_at": now()})
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("validate", help="validate identity/targets without probes or writes")
    _monitor_args(p)
    p = sub.add_parser("snapshot", help="one snapshot; --probe is required for live read-only queries")
    _monitor_args(p)
    p.add_argument("--probe", action="store_true", help="perform bounded Condor/SSH read-only probes and persist output")
    p = sub.add_parser("launch", help="print detached watcher plan; --start is explicit mutation authorization")
    _monitor_args(p)
    p.add_argument("--start", action="store_true", help="actually start the detached local watcher")
    p.add_argument("--active-interval", type=float, default=300.0)
    p.add_argument("--quiet-interval", type=float, default=900.0)
    p = sub.add_parser("watch", help=argparse.SUPPRESS)
    _monitor_args(p)
    p.add_argument("--run", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--active-interval", type=float, default=300.0)
    p.add_argument("--quiet-interval", type=float, default=900.0)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "validate":
            print(json.dumps(validate(args), indent=2, sort_keys=True))
            return 0
        if args.command == "snapshot":
            return snapshot_command(args)
        if args.command == "launch":
            return launch_command(args)
        if args.command == "watch":
            return watch_command(args)
        raise MonitorError(f"unknown command {args.command}")
    except MonitorError as exc:
        print(f"campaign-monitor: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

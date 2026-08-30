#!/usr/bin/env python3
"""Validate JJP manifests and maintain a local campaign state ledger.

This helper is deliberately site-neutral: it never invokes SSH, Condor, ROOT,
or analysis commands.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONFIG_SCHEMA = "jjp-efficiency-campaign-config/v1"
STATE_SCHEMA = "jjp-efficiency-campaign-state/v1"
MANIFEST_SCHEMA = "ntuple-analyzer-tps-manifest/v1"
TRANSITIONS = {
    "draft": "inputs_frozen",
    "inputs_frozen": "lxplus_preflight_passed",
    "lxplus_preflight_passed": "lxplus_submitted",
    "lxplus_submitted": "lxplus_merged",
    "lxplus_merged": "handoff_verified",
    "handoff_verified": "hepthu_analysis_started",
    "hepthu_analysis_started": "validation_running",
    "validation_running": "complete",
}
SITE_FIELDS = {
    "lxplus": ("submit_host", "output_root", "workspace_root"),
    "hepthu": ("ssh_host", "repository", "batch_root"),
}
GATE_ROLES = {
    "inputs_frozen": {"manifest-auditor"},
    "lxplus_preflight_passed": {"lxplus-preflight"},
    "lxplus_submitted": {"lxplus-batch-worker"},
    "lxplus_merged": {"lxplus-batch-worker", "validation-worker"},
    "handoff_verified": {"handoff-worker"},
    "hepthu_analysis_started": {"hepthu-analysis-worker"},
    "validation_running": {"validation-worker"},
    "complete": {"validation-worker"},
}
GATE_EVIDENCE = {
    "inputs_frozen": {"manifest_audit", "repo_revision", "efficiency_config"},
    "lxplus_preflight_passed": {"sample_preflights"},
    "lxplus_submitted": {"schedd", "dag_clusters", "runtime_sha256", "automatic_retry_count"},
    "lxplus_merged": {"coverage", "configuration_hashes", "merged_manifests"},
    "handoff_verified": {"handoff_manifest", "destination_readback"},
    "hepthu_analysis_started": {"remote_revision", "pid", "log", "status_sentinel"},
    "validation_running": {"products_under_review", "validation_output"},
    "complete": {"validation_report", "closure_summary", "final_artifacts"},
}
MUTATING_GATES = {
    "lxplus_preflight_passed", "lxplus_submitted", "lxplus_merged",
    "handoff_verified", "hepthu_analysis_started", "validation_running",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def atomic_write(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


@contextmanager
def state_lock(path: Path):
    lock_path = path.with_name(f".{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def reject_placeholder(value: Any, field: str) -> None:
    text = "" if value is None else str(value).strip()
    upper = text.upper()
    if not text or any(token in upper for token in ("REPLACE", "YYYYMMDD", "CHANGEME", "TBD", "TODO")):
        raise ValueError(f"configuration field {field!r} still contains a placeholder")


def repo_path(repo: Path, raw: str, field: str) -> Path:
    path = (repo / raw).resolve()
    try:
        path.relative_to(repo)
    except ValueError as exc:
        raise ValueError(f"{field} escapes repository root: {raw}") from exc
    return path


def validate_manifest(path: Path, expected_sample: str, files_per_job: int) -> dict[str, Any]:
    manifest = read_json(path)
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError(f"unexpected manifest schema in {path}")
    if manifest.get("sample") != expected_sample:
        raise ValueError(f"sample mismatch in {path}: {manifest.get('sample')!r}")

    files = manifest.get("files")
    inventory = manifest.get("inventory")
    if not isinstance(files, list) or not files or not all(isinstance(item, str) and item for item in files):
        raise ValueError(f"invalid files list in {path}")
    if len(set(files)) != len(files):
        raise ValueError(f"duplicate source file in {path}")
    if not isinstance(inventory, list) or len(inventory) != len(files):
        raise ValueError(f"inventory/file length mismatch in {path}")

    rows: dict[str, dict[str, Any]] = {}
    total_entries = 0
    retained = 0
    candidates = 0
    has_candidates = True
    for index, row in enumerate(inventory):
        if not isinstance(row, dict) or not isinstance(row.get("source_file"), str):
            raise ValueError(f"invalid inventory row {index} in {path}")
        source = row["source_file"]
        if source in rows:
            raise ValueError(f"duplicate inventory source {source!r} in {path}")
        entries = row.get("total_entries")
        kept = row.get("retained_candidate_events")
        if not isinstance(entries, int) or not isinstance(kept, int) or not (0 <= kept <= entries):
            raise ValueError(f"invalid counts for {source!r} in {path}")
        rows[source] = row
        total_entries += entries
        retained += kept
        if isinstance(row.get("n_candidates"), int) and row["n_candidates"] >= 0:
            candidates += row["n_candidates"]
        else:
            has_candidates = False

    if set(files) != set(rows):
        raise ValueError(f"files and inventory source keys differ in {path}")
    for field in ("n_files", "master_n_files"):
        if manifest.get(field) != len(files):
            raise ValueError(f"{field} mismatch in {path}")
    totals = manifest.get("inventory_totals")
    if not isinstance(totals, dict) or totals.get("total_entries") != total_entries or totals.get("retained_candidate_events") != retained:
        raise ValueError(f"inventory totals mismatch in {path}")
    manifest_id = manifest.get("manifest_id")
    if not isinstance(manifest_id, str) or manifest.get("master_manifest_id") != manifest_id:
        raise ValueError(f"manifest/master ID mismatch in {path}")
    # The five old-pipeline manifests add diagnostic n_candidates fields after
    # build_tps_manifest computes the authoritative ID. Reconstruct that base
    # payload instead of silently declaring the checked-in manifests invalid.
    unhashed = {key: value for key, value in manifest.items() if key not in {"manifest_id", "master_manifest_id"}}
    unhashed["inventory"] = [
        {key: value for key, value in row.items() if key != "n_candidates"}
        for row in unhashed["inventory"]
    ]
    unhashed["inventory_totals"] = {
        key: value for key, value in unhashed["inventory_totals"].items() if key != "n_candidates"
    }
    if stable_hash(unhashed) != manifest_id:
        raise ValueError(f"content-derived manifest ID mismatch in {path}")
    if has_candidates and totals.get("n_candidates") != candidates:
        raise ValueError(f"diagnostic candidate total mismatch in {path}")

    summary: dict[str, Any] = {
        "path": str(path.resolve()),
        "manifest_id": manifest_id,
        "hash_mode": (
            "tps-base-v1-with-posthash-candidate-diagnostics"
            if has_candidates else "tps-base-v1"
        ),
        "file_sha256": sha256_file(path),
        "n_files": len(files),
        "total_entries": total_entries,
        "retained_candidate_events": retained,
        "expected_shards": (len(files) + files_per_job - 1) // files_per_job,
        "source_inventory": manifest.get("source_inventory"),
    }
    if has_candidates:
        summary["n_candidates"] = candidates
    return summary


def build_initial_state(config_path: Path, repo: Path) -> dict[str, Any]:
    config = read_json(config_path)
    if config.get("schema_version") != CONFIG_SCHEMA:
        raise ValueError(f"unexpected config schema in {config_path}")
    for field in ("campaign_id", "repository_sha", "lcg_view", "efficiency_config"):
        reject_placeholder(config.get(field), field)
    revision = str(config["repository_sha"])
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", revision):
        raise ValueError("repository_sha must be a 40-64 character hexadecimal revision")
    actual_revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, stderr=subprocess.STDOUT
    ).strip()
    if revision != actual_revision:
        raise ValueError(f"configured repository SHA {revision} does not match HEAD {actual_revision}")
    dirty_lines = subprocess.check_output(
        ["git", "status", "--short"], cwd=repo, text=True, stderr=subprocess.STDOUT
    ).splitlines()
    samples = config.get("samples")
    if not isinstance(samples, list) or not samples or len(samples) != len(set(samples)):
        raise ValueError("samples must be a non-empty unique list")
    if any(not isinstance(sample, str) or not re.fullmatch(r"JJP_[A-Za-z0-9_]+", sample) for sample in samples):
        raise ValueError("this campaign helper accepts JJP efficiency sample labels only")
    files_per_job = config.get("files_per_job")
    if isinstance(files_per_job, bool) or not isinstance(files_per_job, int) or files_per_job <= 0:
        raise ValueError("files_per_job must be a positive integer")
    automatic_retry_count = config.get("automatic_retry_count")
    if (
        isinstance(automatic_retry_count, bool)
        or not isinstance(automatic_retry_count, int)
        or automatic_retry_count < 0
    ):
        raise ValueError("automatic_retry_count must be a non-negative integer")
    manifest_dir = repo_path(repo, str(config.get("manifest_dir", "configs/efficiency/manifests")), "manifest_dir")
    summaries = {
        sample: validate_manifest(manifest_dir / f"{sample}.manifest.json", sample, files_per_job)
        for sample in samples
    }
    efficiency_config = repo_path(repo, str(config["efficiency_config"]), "efficiency_config")
    if not efficiency_config.is_file():
        raise FileNotFoundError(efficiency_config)
    for site, required_fields in SITE_FIELDS.items():
        if not isinstance(config.get(site), dict):
            raise ValueError(f"missing site configuration: {site}")
        for key in required_fields:
            reject_placeholder(config[site].get(key), f"{site}.{key}")

    timestamp = now()
    identity = {
        "repository_sha": revision,
        "repository_dirty": bool(dirty_lines),
        "repository_status": dirty_lines,
        "efficiency_config": str(efficiency_config.resolve()),
        "efficiency_config_sha256": sha256_file(efficiency_config),
        "lcg_view": config["lcg_view"],
        "manifests": summaries,
    }
    config_sha256 = sha256_file(config_path)
    campaign_identity = {
        "campaign_id": config["campaign_id"],
        "repository_sha": revision,
        "campaign_config_sha256": config_sha256,
        "efficiency_config_sha256": identity["efficiency_config_sha256"],
        "lcg_view": config["lcg_view"],
        "manifests": {sample: item["manifest_id"] for sample, item in summaries.items()},
    }
    return {
        "schema_version": STATE_SCHEMA,
        "revision": 0,
        "campaign_id": config["campaign_id"],
        "stage": "draft",
        "created_at": timestamp,
        "updated_at": timestamp,
        "campaign_config": str(config_path),
        "campaign_config_sha256": config_sha256,
        "campaign_identity_sha256": stable_hash(campaign_identity),
        "identity": identity,
        "plan": {
            "files_per_job": files_per_job,
            "automatic_retry_count": automatic_retry_count,
            "samples": samples,
            "lxplus": config["lxplus"],
            "hepthu": config["hepthu"],
        },
        "history": [{"at": timestamp, "from": None, "to": "draft", "evidence": str(config_path)}],
    }


def init_state(args: argparse.Namespace) -> None:
    config_path = args.config.resolve()
    repo = args.repo_root.resolve()
    state_path = args.state.resolve()
    state = build_initial_state(config_path, repo)
    with state_lock(state_path):
        if state_path.exists():
            raise FileExistsError(f"refusing to overwrite existing campaign state: {state_path}")
        atomic_write(state, state_path)
    print(state_path)


def validate_config(args: argparse.Namespace) -> None:
    state = build_initial_state(args.config.resolve(), args.repo_root.resolve())
    if args.json:
        print(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        manifests = state["identity"]["manifests"]
        print(
            f"campaign={state['campaign_id']} samples={len(manifests)} "
            f"files={sum(item['n_files'] for item in manifests.values())} "
            f"shards={sum(item['expected_shards'] for item in manifests.values())} "
            f"identity={state['campaign_identity_sha256']}"
        )


def validate_report(report: dict[str, Any], state: dict[str, Any], target: str) -> None:
    required = {
        "task_id", "role", "campaign_id", "campaign_identity_sha256", "host",
        "authorization", "started_at", "ended_at", "status", "commands",
        "evidence", "artifacts", "next_state", "blockers", "mutation_performed",
    }
    missing = sorted(required - report.keys())
    if missing:
        raise ValueError(f"worker report is missing required fields: {missing}")
    if report["campaign_id"] != state["campaign_id"]:
        raise ValueError("report campaign_id does not match state")
    if report["campaign_identity_sha256"] != state["campaign_identity_sha256"]:
        raise ValueError("report campaign identity hash does not match state")
    if report["next_state"] != target:
        raise ValueError("report next_state does not match requested transition")
    if report["status"] not in {"success", "blocked", "failed"}:
        raise ValueError("report status must be success, blocked, or failed")
    if target != "blocked" and report["status"] != "success":
        raise ValueError("only a successful report may advance a normal gate")
    if target != "blocked" and report["role"] not in GATE_ROLES[target]:
        raise ValueError(f"role {report['role']!r} cannot advance gate {target!r}")
    if not all(isinstance(report[field], str) and report[field] for field in ("task_id", "role", "host", "started_at", "ended_at")):
        raise ValueError("report identity and timestamp fields must be non-empty strings")
    if not isinstance(report["commands"], list) or (target != "blocked" and not report["commands"]):
        raise ValueError("normal gate reports must declare at least one command or audit operation")
    if not isinstance(report["blockers"], list):
        raise ValueError("report commands and blockers must be lists")
    if report["status"] == "success" and report["blockers"]:
        raise ValueError("a successful report cannot contain blockers")
    try:
        started = datetime.fromisoformat(report["started_at"].replace("Z", "+00:00"))
        ended = datetime.fromisoformat(report["ended_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("report timestamps must be ISO-8601") from exc
    if started.utcoffset() is None or ended.utcoffset() is None:
        raise ValueError("report timestamps must include a timezone")
    if ended < started:
        raise ValueError("report ended_at precedes started_at")
    if not isinstance(report["evidence"], dict):
        raise ValueError("report evidence must be an object")
    if target != "blocked":
        missing_evidence = sorted(GATE_EVIDENCE[target] - report["evidence"].keys())
        if missing_evidence:
            raise ValueError(f"report lacks evidence required for {target}: {missing_evidence}")
        empty_evidence = sorted(
            key
            for key in GATE_EVIDENCE[target]
            if report["evidence"][key] is None
            or (isinstance(report["evidence"][key], (str, list, dict)) and not report["evidence"][key])
        )
        if empty_evidence:
            raise ValueError(f"report has empty evidence required for {target}: {empty_evidence}")
    if not isinstance(report["artifacts"], list) or (target != "blocked" and not report["artifacts"]):
        raise ValueError("normal gate reports must declare at least one artifact")
    for artifact in report["artifacts"]:
        if not isinstance(artifact, dict):
            raise ValueError("report artifact must be an object")
        if not isinstance(artifact.get("path"), str) or not artifact["path"]:
            raise ValueError("artifact path must be a non-empty string")
        if isinstance(artifact.get("size"), bool) or not isinstance(artifact.get("size"), int) or artifact["size"] <= 0:
            raise ValueError("artifact size must be a positive integer")
        digest = str(artifact.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-fA-F]{64}", digest) or set(digest) == {"0"}:
            raise ValueError("artifact sha256 must be a 64-character hexadecimal digest")
    authorization = report["authorization"]
    if not isinstance(authorization, dict) or not isinstance(authorization.get("granted"), bool):
        raise ValueError("report authorization must contain boolean granted")
    if not isinstance(report["mutation_performed"], bool):
        raise ValueError("mutation_performed must be boolean")
    if target in MUTATING_GATES and not report["mutation_performed"]:
        raise ValueError(f"gate {target} requires an authorized mutation report")
    if report["mutation_performed"] and (
        not authorization["granted"]
        or authorization.get("scope") != target
        or not isinstance(authorization.get("approval_id"), str)
        or not authorization["approval_id"]
    ):
        raise ValueError("a mutating report requires explicit non-empty authorization scope")
    if target == "lxplus_submitted":
        expected_retry = state["plan"]["automatic_retry_count"]
        if report["evidence"]["automatic_retry_count"] != expected_retry:
            raise ValueError("submitted DAG retry count differs from the frozen authorized plan")
        if authorization.get("automatic_retry_count") != expected_retry:
            raise ValueError("submission authorization does not bind the automatic retry count")


def advance_state(args: argparse.Namespace) -> None:
    state_path = args.state.resolve()
    report_path = args.report.resolve()
    with state_lock(state_path):
        state = read_json(state_path)
        if state.get("schema_version") != STATE_SCHEMA:
            raise ValueError(f"unexpected state schema in {state_path}")
        if isinstance(state.get("revision"), bool) or not isinstance(state.get("revision"), int) or state["revision"] < 0:
            raise ValueError("state revision must be a non-negative integer")
        if state["revision"] != args.expected_revision:
            raise ValueError(f"state revision changed: expected {args.expected_revision}, found {state.get('revision')}")
        current = state.get("stage")
        target = args.to
        if target == "blocked":
            if current in {"complete", "blocked"}:
                raise ValueError(f"cannot block campaign from {current}")
            state["blocked_from"] = current
        elif current == "blocked":
            if target != state.get("blocked_from"):
                raise ValueError(f"blocked campaign may resume only to {state.get('blocked_from')!r}")
            state.pop("blocked_from", None)
        elif TRANSITIONS.get(str(current)) != target:
            raise ValueError(f"invalid transition: {current!r} -> {target!r}")
        report_raw = report_path.read_bytes()
        report = json.loads(report_raw)
        if not isinstance(report, dict):
            raise ValueError("worker report must be a JSON object")
        report_digest = hashlib.sha256(report_raw).hexdigest()
        validate_report(report, state, target)
        timestamp = now()
        state["stage"] = target
        state["revision"] = int(state.get("revision", 0)) + 1
        state["updated_at"] = timestamp
        state.setdefault("history", []).append(
            {
                "at": timestamp,
                "from": current,
                "to": target,
                "report": str(report_path),
                "report_sha256": report_digest,
                "task_id": report["task_id"],
                "role": report["role"],
                "mutation_performed": report["mutation_performed"],
            }
        )
        atomic_write(state, state_path)
    print(state_path)


def show_state(args: argparse.Namespace) -> None:
    state = read_json(args.state.resolve())
    if args.json:
        print(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True))
        return
    manifests = state.get("identity", {}).get("manifests", {})
    print(f"campaign={state.get('campaign_id')} stage={state.get('stage')} samples={len(manifests)}")
    for sample, item in manifests.items():
        print(
            f"{sample}: files={item['n_files']} entries={item['total_entries']} "
            f"retained={item['retained_candidate_events']} shards={item['expected_shards']} "
            f"manifest={item['manifest_id']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate config/manifests without writing state")
    validate.add_argument("--config", required=True, type=Path)
    validate.add_argument("--repo-root", default=Path.cwd(), type=Path)
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(function=validate_config)
    init = subparsers.add_parser("init", help="validate config/manifests and create a new ledger")
    init.add_argument("--config", required=True, type=Path)
    init.add_argument("--state", required=True, type=Path)
    init.add_argument("--repo-root", default=Path.cwd(), type=Path)
    init.set_defaults(function=init_state)
    advance = subparsers.add_parser("advance", help="advance one evidence-backed state gate")
    advance.add_argument("--state", required=True, type=Path)
    advance.add_argument("--to", required=True, choices=[*TRANSITIONS.values(), "blocked"])
    advance.add_argument("--report", required=True, type=Path)
    advance.add_argument("--expected-revision", type=int, required=True)
    advance.set_defaults(function=advance_state)
    show = subparsers.add_parser("show", help="show campaign identity and state")
    show.add_argument("--state", required=True, type=Path)
    show.add_argument("--json", action="store_true")
    show.set_defaults(function=show_state)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        args.function(args)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(f"campaignctl.py: {exc}", file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

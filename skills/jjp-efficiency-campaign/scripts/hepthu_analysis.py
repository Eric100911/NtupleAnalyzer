#!/usr/bin/env python3
"""Read-only preflight and explicit detached-launch planning for hepthu.

``preflight`` and ``launch-plan`` are local, read-only operations.  ``--launch``
is intentionally separate and requires an authorization id; it is meant to be
run *on* the approved hepthu host, never via an implicit SSH connection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LCG_IMPORTS = "import ROOT, pandas, pyarrow"
STATUS_SCHEMA = "jjp-efficiency-hepthu-status/v1"
LCG_READ_SCRIPT = """import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
json_path = sys.argv[2]
parquet_path = sys.argv[3]
if json_path: json.loads((root / json_path).read_text())
if parquet_path:
    import pyarrow.parquet as pq
    pq.ParquetFile(root / parquet_path).metadata
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_handoff(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != "jjp-efficiency-handoff/v1":
        raise ValueError("expected a jjp-efficiency-handoff/v1 manifest")
    rows = data.get("inventory")
    if not isinstance(rows, list) or not rows:
        raise ValueError("handoff manifest has no inventory")
    recorded = data.get("handoff_manifest_sha256")
    unhashed = dict(data)
    unhashed.pop("handoff_manifest_sha256", None)
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if recorded != hashlib.sha256(canonical(unhashed)).hexdigest():
        raise ValueError("handoff manifest SHA-256 does not match its contents")
    inventory_payload = {"schema_version": data["schema_version"], "identity": data.get("identity"), "inventory": rows}
    if data.get("inventory_sha256") != hashlib.sha256(canonical(inventory_payload)).hexdigest():
        raise ValueError("handoff inventory SHA-256 does not match its contents")
    return data


def verify_handoff(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    mismatched: list[str] = []
    for row in manifest["inventory"]:
        relative = row.get("path")
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("handoff manifest contains unsafe path")
        path = root / relative
        if path.is_symlink() or not path.is_file():
            missing.append(relative)
            continue
        if path.stat().st_size != row.get("size") or sha256_file(path) != row.get("sha256"):
            mismatched.append(relative)
    return {"missing": sorted(missing), "mismatched": sorted(mismatched),
            "readable": not missing and not mismatched}


def git_revision(repository: Path) -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=repository, text=True).splitlines()
    return {"repository": str(repository), "head": head, "dirty": bool(dirty), "status": dirty}


def lcg_preflight(lcg_view: Path) -> dict[str, Any]:
    if not lcg_view.is_file():
        return {"available": False, "reason": f"missing LCG setup: {lcg_view}"}
    command = f"source {shlex.quote(str(lcg_view))} && PYTHONDONTWRITEBYTECODE=1 python3 -c {shlex.quote(LCG_IMPORTS)}"
    result = subprocess.run(["bash", "-lc", command], text=True, capture_output=True, timeout=60)
    return {"available": result.returncode == 0, "returncode": result.returncode,
            "stderr": result.stderr.strip(), "lcg_view": str(lcg_view)}


def lcg_readability(lcg_view: Path, root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    json_path = next((row["path"] for row in manifest["inventory"] if row["path"].lower().endswith(".json")), "")
    parquet_path = next((row["path"] for row in manifest["inventory"] if row["path"].lower().endswith(".parquet")), "")
    if not json_path and not parquet_path:
        return {"readable": False, "reason": "handoff has neither JSON nor Parquet artifact"}
    command = (
        f"source {shlex.quote(str(lcg_view))} && PYTHONDONTWRITEBYTECODE=1 "
        f"python3 -c {shlex.quote(LCG_READ_SCRIPT)} {shlex.quote(str(root))} "
        f"{shlex.quote(json_path)} {shlex.quote(parquet_path)}"
    )
    result = subprocess.run(["bash", "-lc", command], text=True, capture_output=True, timeout=60)
    return {"readable": result.returncode == 0, "returncode": result.returncode,
            "json_artifact": json_path or None, "parquet_artifact": parquet_path or None,
            "stderr": result.stderr.strip()}


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    repository = args.repository.resolve(strict=True)
    if not (repository / ".git").exists():
        raise ValueError(f"not a Git repository: {repository}")
    handoff_root = args.handoff_root.resolve(strict=True)
    manifest = load_handoff(args.handoff_manifest.resolve())
    revision = git_revision(repository)
    handoff = verify_handoff(handoff_root, manifest)
    lcg = lcg_preflight(args.lcg_view.resolve())
    readability = lcg_readability(args.lcg_view.resolve(), handoff_root, manifest) if lcg["available"] else {
        "readable": False, "reason": "LCG import preflight failed"}
    batch_root = args.batch_root.resolve()
    historical = sorted(path.name for path in batch_root.iterdir()) if batch_root.exists() else []
    identity = manifest.get("identity", {})
    identity_match = (
        identity.get("campaign_id") == args.campaign_id
        and identity.get("campaign_identity_sha256") == args.campaign_identity_sha256
        and identity.get("repo_sha") == args.expected_repo_sha
        and identity.get("efficiency_config_sha256") == args.efficiency_config_sha256
    )
    exact = (revision["head"] == args.expected_repo_sha and not revision["dirty"] and handoff["readable"]
             and lcg["available"] and readability["readable"] and identity_match)
    return {
        "operation": "hepthu-read-only-preflight", "mutated": False, "checked_at": utc_now(),
        "repository_revision": revision, "expected_repo_sha": args.expected_repo_sha,
        "handoff": handoff, "handoff_inventory_sha256": manifest.get("inventory_sha256"),
        "handoff_identity_match": identity_match, "lcg": lcg, "representative_readability": readability,
        "historical_batch_directories": historical, "pass": exact,
    }


def parse_commands(values: list[str]) -> list[list[str]]:
    commands = [shlex.split(value) for value in values]
    if not commands or any(not command for command in commands):
        raise ValueError("at least one non-empty --command is required")
    # Commands are tokenized then re-quoted below; no caller-provided shell
    # syntax is evaluated as part of the detached wrapper.
    return commands


def launch_material(args: argparse.Namespace) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.campaign_id):
        raise ValueError("campaign_id must use only letters, numbers, dot, underscore, and hyphen")
    if not re.fullmatch(r"JJP_[A-Za-z0-9_]+", args.sample):
        raise ValueError("sample must be a JJP campaign sample label")
    for field in ("campaign_identity_sha256", "efficiency_config_sha256"):
        value = getattr(args, field)
        if len(value) != 64 or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise ValueError(f"{field} must be a 64-character SHA-256")
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", args.expected_repo_sha):
        raise ValueError("expected_repo_sha must be a 40-64 character Git SHA")
    output_root = args.output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"fresh output directory already exists: {output_root}")
    commands = parse_commands(args.command)
    joined = " && ".join(shlex.join(command) for command in commands)
    command_hash = sha256_text(joined)
    return {"output_root": output_root, "commands": commands, "command_text": joined,
            "command_sha256": command_hash, "log": output_root / "analysis.log",
            "lock": output_root / ".launch.lock", "pid_file": output_root / "analysis.pid",
            "status_sentinel": output_root / "status.json"}


def launch_plan(args: argparse.Namespace) -> dict[str, Any]:
    material = launch_material(args)
    wrapper = {
        "shell": "bash -lc",
        "lcg_same_shell": str(args.lcg_view.resolve()),
        "commands": material["commands"],
        "detached": True,
        "status_schema": STATUS_SCHEMA,
        "persistent_log": str(material["log"]), "pid_file": str(material["pid_file"]),
        "lock": str(material["lock"]), "status_sentinel": str(material["status_sentinel"]),
    }
    return {"operation": "hepthu-detached-launch-plan", "dry_run": not args.launch,
            "authorization_required": True, "campaign_id": args.campaign_id,
            "campaign_identity_sha256": args.campaign_identity_sha256,
            "sample": args.sample, "input_root": str(args.input_root.resolve()),
            "expected_repo_sha": args.expected_repo_sha,
            "efficiency_config_sha256": args.efficiency_config_sha256,
            "command_sha256": material["command_sha256"], "wrapper": wrapper,
            "fresh_output_required": True, "no_ssh": True}


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def status_payload(
    state: str,
    args: argparse.Namespace,
    material: dict[str, Any],
    started_at: str,
    *,
    pid: int | None = None,
    exit_code: int | None = None,
) -> dict[str, Any]:
    if state not in {"started", "running", "finished"}:
        raise ValueError(f"invalid detached status state: {state}")
    return {
        "schema_version": STATUS_SCHEMA,
        "state": state,
        "campaign_id": args.campaign_id,
        "campaign_identity_sha256": args.campaign_identity_sha256,
        "sample": args.sample,
        "command_sha256": material["command_sha256"],
        "started_at": started_at,
        "pid": pid,
        "exit_code": exit_code,
    }


def launch(args: argparse.Namespace) -> dict[str, Any]:
    if not args.authorization_id:
        raise ValueError("--launch requires a non-empty --authorization-id")
    material = launch_material(args)
    output_root: Path = material["output_root"]
    output_root.parent.mkdir(parents=True, exist_ok=True)
    # mkdir is atomic: no existing or partial run can be reused.
    output_root.mkdir()
    try:
        lock_fd = os.open(material["lock"], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(lock_fd, "w", encoding="utf-8") as handle:
            handle.write(f"campaign_id={args.campaign_id}\ncommand_sha256={material['command_sha256']}\n")
        sentinel = status_payload("started", args, material, utc_now())
        atomic_json(material["status_sentinel"], sentinel)
        quoted_lcg = shlex.quote(str(args.lcg_view.resolve()))
        quoted_status = shlex.quote(str(material["status_sentinel"]))
        runner = (
            "set -e; "
            "finish() { "
            "rc=$?; "
            f"printf '{{\"schema_version\":\"{STATUS_SCHEMA}\",\"state\":\"finished\",\"campaign_id\":\"{args.campaign_id}\",\"campaign_identity_sha256\":\"{args.campaign_identity_sha256}\",\"sample\":\"{args.sample}\",\"command_sha256\":\"{material['command_sha256']}\",\"started_at\":\"{sentinel['started_at']}\",\"pid\":%s,\"exit_code\":%s}}\\n' \"$BASHPID\" \"$rc\" > {quoted_status}.tmp; "
            f"mv {quoted_status}.tmp {quoted_status}; "
            "exit \"$rc\"; "
            "}; trap finish EXIT; "
            f"source {quoted_lcg}; "
            f"{material['command_text']}"
        )
        with material["log"].open("x", encoding="utf-8") as log:
            process = subprocess.Popen(["bash", "-lc", runner], stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True, text=True)
        material["pid_file"].write_text(f"{process.pid}\n", encoding="utf-8")
        if process.poll() is None:
            atomic_json(material["status_sentinel"], status_payload("running", args, material,
                                                                     sentinel["started_at"], pid=process.pid))
    except Exception:
        # Preserve evidence rather than removing a fresh directory after a failed
        # launch attempt; it must not be reused.
        raise
    return {"operation": "hepthu-detached-launch", "authorization_id": args.authorization_id,
            "pid": process.pid, "started_at": sentinel["started_at"],
            "command_sha256": material["command_sha256"], "log": str(material["log"]),
            "lock": str(material["lock"]), "status_sentinel": str(material["status_sentinel"]),
            "output_root": str(output_root)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    check = commands.add_parser("preflight", help="local read-only repository/LCG/handoff preflight")
    check.add_argument("--repository", type=Path, required=True)
    check.add_argument("--handoff-root", type=Path, required=True)
    check.add_argument("--handoff-manifest", type=Path, required=True)
    check.add_argument("--expected-repo-sha", required=True)
    check.add_argument("--campaign-id", required=True)
    check.add_argument("--campaign-identity-sha256", required=True)
    check.add_argument("--efficiency-config-sha256", required=True)
    check.add_argument("--lcg-view", type=Path, required=True)
    check.add_argument("--batch-root", type=Path, required=True)
    plan = commands.add_parser("launch-plan", help="emit a launch plan; does not start a process by default")
    plan.add_argument("--campaign-id", required=True)
    plan.add_argument("--campaign-identity-sha256", required=True)
    plan.add_argument("--sample", required=True)
    plan.add_argument("--input-root", type=Path, required=True)
    plan.add_argument("--expected-repo-sha", required=True)
    plan.add_argument("--efficiency-config-sha256", required=True)
    plan.add_argument("--output-root", type=Path, required=True)
    plan.add_argument("--lcg-view", type=Path, required=True)
    plan.add_argument("--command", action="append", default=[], help="one argv-safe analysis command")
    plan.add_argument("--launch", action="store_true")
    plan.add_argument("--authorization-id")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = preflight(args) if args.mode == "preflight" else (launch(args) if args.launch else launch_plan(args))
        print(json.dumps(result, indent=2, sort_keys=True))
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"hepthu_analysis.py: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

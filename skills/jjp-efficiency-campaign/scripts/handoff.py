#!/usr/bin/env python3
"""Build, plan, transfer, and verify a compact JJP campaign handoff.

The default path is deliberately read-only: ``plan`` emits JSON and never
contacts a host.  A transfer needs both ``--execute-transfer`` and an explicit
authorization id.  It transfers only the enumerated inventory, to an atomically
created destination, and then performs an independent checksum readback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA = "jjp-efficiency-handoff/v1"
REMOTE_TIMEOUT_SECONDS = 30
SMALL_ROOT_LIMIT = 100 * 1024 * 1024
FORBIDDEN_PARTS = {
    "raw", "raw-ntuples", "ntuple", "ntuples", "shard", "shards", "tmp",
    "temp", "log", "logs", "secret", "secrets", ".ssh", "proxy", "proxies",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_relative(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe relative handoff path: {raw!r}")
    return path


def safe_destination(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"destination must be a safe relative path: {raw!r}")
    if any(not re.fullmatch(r"[A-Za-z0-9._+=,@-]+", part) for part in path.parts):
        raise ValueError(f"destination contains unsupported shell-sensitive characters: {raw!r}")
    return path


def parse_sample_manifests(values: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        sample, separator, manifest_id = value.partition("=")
        if not separator or not sample or len(manifest_id) != 64 or any(char not in "0123456789abcdefABCDEF" for char in manifest_id):
            raise ValueError("--sample-manifest must be SAMPLE=64-character-sha256")
        if sample in result:
            raise ValueError(f"duplicate sample manifest: {sample}")
        result[sample] = manifest_id.lower()
    if not result:
        raise ValueError("at least one --sample-manifest is required")
    return dict(sorted(result.items()))


def checked_source_file(source_root: Path, relative: str, allow_small_root: bool) -> Path:
    rel = safe_relative(relative)
    if any(part.lower() in FORBIDDEN_PARTS for part in rel.parts):
        raise ValueError(f"excluded handoff path: {relative}")
    if rel.suffix.lower() not in {".parquet", ".json", ".csv", ".yaml", ".yml", ".root", ".txt"}:
        raise ValueError(f"unsupported compact handoff artifact: {relative}")
    path = source_root.joinpath(*rel.parts)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"handoff artifact is not a regular file: {relative}")
    resolved_root = source_root.resolve(strict=True)
    resolved_path = path.resolve(strict=True)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"handoff artifact escapes source root: {relative}") from exc
    if path.suffix.lower() == ".root" and (not allow_small_root or path.stat().st_size > SMALL_ROOT_LIMIT):
        raise ValueError("ROOT handoff files require --allow-small-root and must be <= 100 MiB")
    return path


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    source_root = args.source_root.resolve(strict=True)
    if not source_root.is_dir():
        raise ValueError(f"source root is not a directory: {source_root}")
    requested = sorted(set(args.include))
    if len(requested) != len(args.include):
        raise ValueError("duplicate --include path")
    if not requested:
        raise ValueError("at least one explicit --include artifact is required")
    inventory = []
    for relative in requested:
        path = checked_source_file(source_root, relative, args.allow_small_root)
        inventory.append({"path": relative, "size": path.stat().st_size, "sha256": file_sha256(path)})
    identity = {
        "campaign_id": args.campaign_id,
        "campaign_identity_sha256": args.campaign_identity_sha256.lower(),
        "repo_sha": args.repo_sha.lower(),
        "efficiency_config_sha256": args.efficiency_config_sha256.lower(),
        "lcg_view": args.lcg_view,
        "sample_manifests": parse_sample_manifests(args.sample_manifest),
    }
    for field in ("campaign_id", "lcg_view"):
        if not identity[field]:
            raise ValueError(f"{field} must be non-empty")
    for field in ("campaign_identity_sha256", "efficiency_config_sha256"):
        if len(identity[field]) != 64 or any(char not in "0123456789abcdef" for char in identity[field]):
            raise ValueError(f"{field} must be a 64-character SHA-256")
    if not (40 <= len(identity["repo_sha"]) <= 64) or any(char not in "0123456789abcdef" for char in identity["repo_sha"]):
        raise ValueError("repo_sha must be a 40-64 character Git SHA")
    inventory_sha256 = stable_sha256({"schema_version": SCHEMA, "identity": identity, "inventory": inventory})
    manifest = {
        "schema_version": SCHEMA,
        "created_at": utc_now(),
        "source_root": str(source_root),
        "identity": identity,
        "inventory": inventory,
        "inventory_sha256": inventory_sha256,
    }
    manifest["handoff_manifest_sha256"] = stable_sha256(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != SCHEMA:
        raise ValueError("unexpected handoff manifest schema")
    inventory = manifest.get("inventory")
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("handoff manifest has no inventory")
    previous = ""
    for row in inventory:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("invalid inventory row")
        safe_relative(row["path"])
        if row["path"] <= previous:
            raise ValueError("inventory must be strictly path sorted")
        previous = row["path"]
        if isinstance(row.get("size"), bool) or not isinstance(row.get("size"), int) or row["size"] < 0:
            raise ValueError("invalid inventory size")
        digest = row.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest.lower()):
            raise ValueError("invalid inventory SHA-256")
    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("handoff identity is missing")
    expected_inventory = stable_sha256({"schema_version": SCHEMA, "identity": identity, "inventory": inventory})
    if manifest.get("inventory_sha256") != expected_inventory:
        raise ValueError("inventory SHA-256 does not match manifest contents")
    unhashed = dict(manifest)
    recorded = unhashed.pop("handoff_manifest_sha256", None)
    if recorded != stable_sha256(unhashed):
        raise ValueError("handoff manifest SHA-256 does not match contents")


def atomic_new_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing handoff manifest: {path}")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # link is an atomic create-only operation, unlike os.replace.
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("handoff manifest must be a JSON object")
    validate_manifest(manifest)
    return manifest


def verify_tree(root: Path, manifest: dict[str, Any], *, require_exact: bool) -> dict[str, Any]:
    root = root.resolve(strict=True)
    expected = {row["path"]: row for row in manifest["inventory"]}
    missing: list[str] = []
    mismatched: list[dict[str, Any]] = []
    for relative, row in expected.items():
        path = root.joinpath(*safe_relative(relative).parts)
        if path.is_symlink() or not path.is_file():
            missing.append(relative)
            continue
        actual_size = path.stat().st_size
        actual_sha256 = file_sha256(path)
        if actual_size != row["size"] or actual_sha256 != row["sha256"]:
            mismatched.append({"path": relative, "expected_size": row["size"], "actual_size": actual_size,
                               "expected_sha256": row["sha256"], "actual_sha256": actual_sha256})
    extra: list[str] = []
    if require_exact:
        actual = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*") if path.is_file() and not path.is_symlink()
        }
        expected_paths = set(expected) | {"handoff-manifest.json"}
        extra = sorted(actual - expected_paths)
    return {
        "operation": "inventory-verification",
        "root": str(root),
        "inventory_sha256": manifest["inventory_sha256"],
        "missing": sorted(missing), "extra": extra, "mismatched": mismatched,
        "exact_agreement": not missing and not extra and not mismatched,
        "verified_at": utc_now(),
    }


def ssh_settings(args: argparse.Namespace) -> dict[str, Any]:
    host = args.ssh_host
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", host):
        raise ValueError("SSH host must be a conservative host alias")
    user = getattr(args, "ssh_user", None)
    if user is not None and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", user):
        raise ValueError("SSH user must be a conservative account name")
    port = getattr(args, "ssh_port", None)
    if port is not None and (isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535):
        raise ValueError("SSH port must be an integer in [1, 65535]")
    config = getattr(args, "ssh_config", None)
    config_path: Path | None = None
    config_sha256: str | None = None
    if config is not None:
        config_path = Path(config)
        if not config_path.is_absolute() or str(config_path) != str(config_path.resolve()):
            raise ValueError("--ssh-config must be an absolute canonical path")
        if config_path != Path("/dev/null"):
            details = config_path.stat()
            if config_path.is_symlink() or not stat.S_ISREG(details.st_mode):
                raise ValueError("--ssh-config must be /dev/null or a regular file")
            if details.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise ValueError("--ssh-config must not be group- or world-writable")
            config_sha256 = file_sha256(config_path)
        else:
            config_sha256 = hashlib.sha256(b"").hexdigest()
    return {"host": host, "user": user, "port": port,
            "ssh_config": str(config_path) if config_path else None,
            "ssh_config_sha256": config_sha256,
            "system_config_disabled": config_path == Path("/dev/null")}


def ssh_base(settings: dict[str, Any]) -> list[str]:
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "ConnectionAttempts=1",
               "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=2"]
    if settings["ssh_config"]:
        command.extend(["-F", settings["ssh_config"]])
    if settings["port"]:
        command.extend(["-p", str(settings["port"])])
    if settings["user"]:
        command.extend(["-l", settings["user"]])
    return command + [settings["host"]]


def transfer_plan(manifest: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    destination = safe_destination(args.destination_root).as_posix()
    endpoint = ssh_settings(args)
    manifest_name = "handoff-manifest.json"
    files = [row["path"] for row in manifest["inventory"]]
    return {
        "operation": "handoff-transfer-plan",
        "dry_run": not args.execute_transfer,
        "authorization_required": True,
        "source_root": str(args.source_root.resolve()),
        "endpoint": endpoint,
        "destination_root": destination,
        "inventory_sha256": manifest["inventory_sha256"],
        "files": files,
        "commands": {
            "fresh_destination": "ssh BatchMode=yes ... HOST 'mkdir -- DESTINATION'",
            "transfer": "rsync --archive --checksum --protect-args --files-from=INVENTORY --relative SOURCE/ HOST:DESTINATION/",
            "verify": "ssh BatchMode=yes ... HOST python3 -c VERIFY_SCRIPT DESTINATION handoff-manifest.json",
        },
        "ssh_command": shlex.join(ssh_base(endpoint)),
        "no_overwrite": True,
        "timeouts_seconds": {"ssh_connect": 15, "ssh_total": REMOTE_TIMEOUT_SECONDS, "rsync": 600},
        "manifest_name": manifest_name,
    }


REMOTE_VERIFY_SCRIPT = r'''import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); name=sys.argv[2]; expected_manifest_sha=sys.argv[3]
raw=(root/name).read_bytes(); manifest=json.loads(raw)
manifest_errors=[]
if hashlib.sha256(raw).hexdigest()!=expected_manifest_sha: manifest_errors.append("manifest_file_sha256")
recorded=manifest.pop("handoff_manifest_sha256",None)
canonical=lambda value: json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
if recorded!=hashlib.sha256(canonical(manifest)).hexdigest(): manifest_errors.append("handoff_manifest_sha256")
if manifest.get("inventory_sha256")!=hashlib.sha256(canonical({"schema_version":manifest.get("schema_version"),"identity":manifest.get("identity"),"inventory":manifest.get("inventory")})).hexdigest(): manifest_errors.append("inventory_sha256")
manifest["handoff_manifest_sha256"]=recorded
rows=manifest["inventory"]; expected={r["path"]:r for r in rows}; missing=[]; mismatch=[]
for rel,row in expected.items():
    p=root.joinpath(*pathlib.PurePosixPath(rel).parts)
    if p.is_symlink() or not p.is_file(): missing.append(rel); continue
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""): h.update(b)
    if p.stat().st_size!=row["size"] or h.hexdigest()!=row["sha256"]: mismatch.append(rel)
actual={p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and not p.is_symlink()}
extra=sorted(actual-(set(expected)|{name})); readable=[]; read_errors=[]
for suffix in (".json", ".parquet"):
    candidate=next((r["path"] for r in rows if r["path"].lower().endswith(suffix)),None)
    if candidate is None: continue
    try:
        p=root.joinpath(*pathlib.PurePosixPath(candidate).parts)
        if suffix==".json": json.loads(p.read_text())
        else:
            import pyarrow.parquet as pq; pq.ParquetFile(p).metadata
        readable.append(candidate)
    except Exception as exc: read_errors.append({"path":candidate,"error":str(exc)})
ok=not manifest_errors and not missing and not extra and not mismatch and not read_errors
print(json.dumps({"manifest_errors":manifest_errors,"missing":sorted(missing),"extra":extra,"mismatched":sorted(mismatch),"readable":readable,"read_errors":read_errors,"exact_agreement":ok},sort_keys=True))
sys.exit(0 if ok else 3)'''


def execute_transfer(manifest: dict[str, Any], manifest_path: Path, args: argparse.Namespace) -> dict[str, Any]:
    if not args.authorization_id:
        raise ValueError("--execute-transfer requires a non-empty --authorization-id")
    destination = safe_destination(args.destination_root).as_posix()
    endpoint = ssh_settings(args)
    host = endpoint["host"]
    if Path(manifest["source_root"]).resolve() != args.source_root.resolve():
        raise ValueError("--source-root does not match the handoff manifest source_root")
    # mkdir without -p is the atomic freshness gate. A pre-existing destination
    # (including a partial failed transfer) fails closed.
    subprocess.run(ssh_base(endpoint) + [shlex.join(["mkdir", "--", destination])], check=True,
                   timeout=REMOTE_TIMEOUT_SECONDS)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="handoff-files-", delete=False) as handle:
        file_list = Path(handle.name)
        handle.write("\n".join(row["path"] for row in manifest["inventory"]) + "\n")
    try:
        ssh_transport = shlex.join(ssh_base(endpoint)[:-1])
        target = f"{host}:{destination}/"
        subprocess.run(["rsync", "--archive", "--checksum", "--protect-args", "--files-from", str(file_list),
                        "--relative", "-e", ssh_transport, f"{args.source_root.resolve()}/", target], check=True, timeout=600)
        subprocess.run(["rsync", "--archive", "--checksum", "--protect-args", "-e", ssh_transport,
                        str(manifest_path.resolve()), f"{host}:{destination}/handoff-manifest.json"], check=True, timeout=600)
    finally:
        file_list.unlink(missing_ok=True)
    lcg_view = str(manifest["identity"].get("lcg_view", ""))
    if not lcg_view.startswith("/cvmfs/"):
        raise ValueError("handoff manifest LCG view must be an absolute CVMFS path")
    manifest_digest = file_sha256(manifest_path)
    remote_body = (
        f"source {shlex.quote(lcg_view)} && PYTHONDONTWRITEBYTECODE=1 "
        f"{shlex.join(['python3', '-c', REMOTE_VERIFY_SCRIPT, destination, 'handoff-manifest.json', manifest_digest])}"
    )
    command = ssh_base(endpoint) + [shlex.join(["bash", "-lc", remote_body])]
    completed = subprocess.run(command, check=False, timeout=REMOTE_TIMEOUT_SECONDS, text=True, capture_output=True)
    try:
        readback = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"remote verification did not return JSON: {completed.stderr.strip()}") from exc
    if completed.returncode != 0 or not readback.get("exact_agreement"):
        raise RuntimeError(f"remote verification failed: {readback}")
    return {"operation": "handoff-transfer", "authorization_id": args.authorization_id,
            "destination_root": destination, "inventory_sha256": manifest["inventory_sha256"],
            "destination_readback": readback, "transfer_completed_at": utc_now()}


def add_identity_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--campaign-identity-sha256", required=True)
    parser.add_argument("--repo-sha", required=True)
    parser.add_argument("--efficiency-config-sha256", required=True)
    parser.add_argument("--lcg-view", required=True)
    parser.add_argument("--sample-manifest", action="append", default=[], metavar="SAMPLE=SHA256")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("inventory", help="emit a deterministic compact-artifact manifest")
    inventory.add_argument("--source-root", type=Path, required=True)
    inventory.add_argument("--include", action="append", default=[], metavar="RELATIVE_PATH")
    inventory.add_argument("--allow-small-root", action="store_true")
    inventory.add_argument("--write-manifest", type=Path, help="create this manifest only if it does not exist")
    add_identity_arguments(inventory)
    plan = commands.add_parser("plan", help="emit a dry-run transfer plan (default; no SSH)")
    plan.add_argument("--source-root", type=Path, required=True)
    plan.add_argument("--handoff-manifest", type=Path, required=True)
    plan.add_argument("--ssh-host", required=True)
    plan.add_argument("--ssh-config", type=Path, help="absolute trusted config path; /dev/null disables system config")
    plan.add_argument("--ssh-port", type=int, help="explicit frozen SSH port")
    plan.add_argument("--ssh-user", help="explicit frozen remote account")
    plan.add_argument("--destination-root", required=True)
    plan.add_argument("--execute-transfer", action="store_true")
    plan.add_argument("--authorization-id")
    verify = commands.add_parser("verify", help="verify a local destination inventory without SSH")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--handoff-manifest", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "inventory":
            manifest = build_manifest(args)
            if args.write_manifest:
                atomic_new_json(args.write_manifest.resolve(), manifest)
            print(json.dumps(manifest, indent=2, sort_keys=True))
        elif args.command == "plan":
            manifest = load_manifest(args.handoff_manifest.resolve())
            if args.execute_transfer:
                result = execute_transfer(manifest, args.handoff_manifest.resolve(), args)
            else:
                result = transfer_plan(manifest, args)
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            manifest = load_manifest(args.handoff_manifest.resolve())
            print(json.dumps(verify_tree(args.root, manifest, require_exact=True), indent=2, sort_keys=True))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"handoff.py: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

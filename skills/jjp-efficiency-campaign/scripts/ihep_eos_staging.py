#!/usr/bin/env python3
"""Safely stage formal IHEP manifests to CERN EOS through an IHEP worker.

The default commands are planning-only.  ``launch`` needs both ``--execute``
and ``--authorization-id`` before it contacts IHEP; the remote ``worker``
needs the same two switches before it makes EOS directories or calls ``xrdcp``.

The worker deliberately reads the CCEOS source from IHEP, where it is local to
T2_CN_Beijing, and writes a new, campaign-scoped EOS input namespace.  It
never replaces a destination file.  A pre-existing file is usable only after
both its byte count and server checksum agree with the source.
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
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit


PLAN_SCHEMA = "jjp-efficiency-ihep-eos-stage-plan/v1"
STAGED_SCHEMA = "ntuple-analyzer-tps-staged-manifest/v1"
STATUS_SCHEMA = "jjp-efficiency-ihep-eos-stage-status/v1"
IHEP_DEFAULT_HOST = "lxlogin.ihep.ac.cn"
IHEP_DEFAULT_USER = "wangchi"
EOS_DEFAULT_ENDPOINT = "root://eosuser.cern.ch"
EOS_DEFAULT_ROOT = "/eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV"
REMOTE_TIMEOUT_SECONDS = 60
HEX64 = re.compile(r"[0-9a-f]{64}")
SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
SAFE_AUTHORIZATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@=-]*")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def stable_sha256(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_hex64(value: str, field: str) -> str:
    lowered = value.lower()
    if not HEX64.fullmatch(lowered):
        raise ValueError(f"{field} must be a 64-character SHA-256")
    return lowered


def safe_component(value: str, field: str) -> str:
    if not SAFE_COMPONENT.fullmatch(value):
        raise ValueError(f"{field} must contain only safe path components")
    return value


def require_authorization_id(value: str | None) -> str:
    if not value or not SAFE_AUTHORIZATION.fullmatch(value):
        raise ValueError("authorization_id must be a non-empty conservative token")
    return value


def safe_absolute_path(value: str, field: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts[1:]):
        raise ValueError(f"{field} must be an absolute path without traversal")
    if any(not SAFE_COMPONENT.fullmatch(part) for part in path.parts[1:]):
        raise ValueError(f"{field} contains shell-sensitive path components")
    return path


def xrootd_url(endpoint: str, path: PurePosixPath) -> str:
    endpoint = endpoint.rstrip("/")
    if not re.fullmatch(r"root://[A-Za-z0-9][A-Za-z0-9.:-]*", endpoint):
        raise ValueError("XRootD endpoint must be root://HOST[:PORT]")
    return f"{endpoint}//{path.as_posix().lstrip('/')}"


def parse_xrootd_url(value: str, *, require_cceos: bool) -> tuple[str, PurePosixPath]:
    parsed = urlsplit(value)
    if parsed.scheme != "root" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError(f"invalid XRootD URL: {value!r}")
    host = parsed.hostname
    if host is None or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", host):
        raise ValueError(f"invalid XRootD host: {value!r}")
    if require_cceos and not (host == "cceos.ihep.ac.cn" or host.endswith(".cceos.ihep.ac.cn")):
        raise ValueError(f"staging source is not a CCEOS URL: {value!r}")
    endpoint = f"root://{parsed.netloc}"
    path = safe_absolute_path("/" + parsed.path.lstrip("/"), "XRootD path")
    return endpoint, path


def ssh_settings(args: argparse.Namespace) -> dict[str, Any]:
    host = args.ssh_host
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", host):
        raise ValueError("SSH host must be a conservative host name")
    user = args.ssh_user
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", user):
        raise ValueError("SSH user must be a conservative account name")
    if args.ssh_port is not None and not 1 <= args.ssh_port <= 65535:
        raise ValueError("SSH port must be in [1, 65535]")
    config = Path(args.ssh_config)
    if not config.is_absolute() or str(config) != str(config.resolve()):
        raise ValueError("--ssh-config must be an absolute canonical path")
    if config != Path("/dev/null"):
        details = config.stat()
        if config.is_symlink() or not stat.S_ISREG(details.st_mode):
            raise ValueError("--ssh-config must be /dev/null or a regular file")
        if details.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ValueError("--ssh-config must not be group- or world-writable")
        config_sha = file_sha256(config)
    else:
        config_sha = hashlib.sha256(b"").hexdigest()
    return {"host": host, "user": user, "port": args.ssh_port,
            "ssh_config": str(config), "ssh_config_sha256": config_sha,
            "system_config_disabled": config == Path("/dev/null")}


def ssh_base(settings: dict[str, Any]) -> list[str]:
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "ConnectionAttempts=1",
               "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=2", "-F", settings["ssh_config"]]
    if settings["port"] is not None:
        command += ["-p", str(settings["port"])]
    return command + ["-l", settings["user"], settings["host"]]


def scp_base(settings: dict[str, Any]) -> list[str]:
    command = ["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "ConnectionAttempts=1",
               "-F", settings["ssh_config"]]
    if settings["port"] is not None:
        command += ["-P", str(settings["port"])]
    return command


def load_formal_manifest(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("schema_version") != "ntuple-analyzer-tps-manifest/v1":
        raise ValueError("expected ntuple-analyzer-tps-manifest/v1")
    sample = payload.get("sample")
    files = payload.get("files")
    manifest_id = payload.get("manifest_id")
    if not isinstance(sample, str) or not re.fullmatch(r"JJP_[A-Za-z0-9_]+", sample):
        raise ValueError("formal manifest has an invalid JJP sample")
    if not isinstance(files, list) or not files or not all(isinstance(item, str) for item in files):
        raise ValueError("formal manifest has no usable file list")
    require_hex64(str(manifest_id), "formal manifest_id")
    if len(set(files)) != len(files):
        raise ValueError("formal manifest contains duplicate source URLs")
    if payload.get("n_files") != len(files) or payload.get("master_n_files") != len(files):
        raise ValueError("formal manifest file totals are inconsistent")
    if payload.get("master_manifest_id", manifest_id) != manifest_id:
        raise ValueError("formal manifest is not a complete master manifest")
    inventory = payload.get("inventory", [])
    if inventory and (not isinstance(inventory, list) or {row.get("source_file") for row in inventory if isinstance(row, dict)} != set(files)):
        raise ValueError("formal manifest inventory does not match file list")
    return payload, hashlib.sha256(raw).hexdigest()


def staged_basename(source_url: str) -> str:
    source_digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
    suffix = PurePosixPath(urlsplit(source_url).path).suffix or ".root"
    if suffix.lower() != ".root":
        raise ValueError(f"source does not look like a ROOT ntuple: {source_url!r}")
    return f"{source_digest}{suffix.lower()}"


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    formal_path = args.formal_manifest.resolve(strict=True)
    formal, formal_sha = load_formal_manifest(formal_path)
    campaign_id = safe_component(args.campaign_id, "campaign_id")
    campaign_identity = require_hex64(args.campaign_identity_sha256, "campaign_identity_sha256")
    eos_root = safe_absolute_path(args.eos_root, "eos_root")
    if eos_root.as_posix() != EOS_DEFAULT_ROOT:
        raise ValueError(f"eos_root must be the campaign staging root: {EOS_DEFAULT_ROOT}")
    sample = formal["sample"]
    staged_root = eos_root / campaign_id / "staged_inputs" / sample
    destination_endpoint = args.eos_endpoint.rstrip("/")
    if destination_endpoint != EOS_DEFAULT_ENDPOINT:
        raise ValueError(f"eos_endpoint must be the CERN EOS endpoint: {EOS_DEFAULT_ENDPOINT}")
    mappings: list[dict[str, Any]] = []
    for index, source_url in enumerate(formal["files"]):
        source_endpoint, source_path = parse_xrootd_url(source_url, require_cceos=True)
        relative_path = PurePosixPath("files") / staged_basename(source_url)
        eos_path = staged_root / relative_path
        mappings.append({"index": index, "source_url": source_url, "source_endpoint": source_endpoint,
                         "source_path": source_path.as_posix(), "source_url_sha256": hashlib.sha256(source_url.encode()).hexdigest(),
                         "relative_path": relative_path.as_posix(), "eos_path": eos_path.as_posix(),
                         "staged_url": xrootd_url(destination_endpoint, eos_path)})
    if len({row["staged_url"] for row in mappings}) != len(mappings):
        raise ValueError("derived staged URLs are not unique")
    plan_core = {"schema_version": PLAN_SCHEMA, "campaign_id": campaign_id,
                 "campaign_identity_sha256": campaign_identity, "sample": sample,
                 "formal_manifest": {"path": str(formal_path), "sha256": formal_sha,
                                     "manifest_id": formal["manifest_id"], "master_manifest_id": formal["master_manifest_id"],
                                     "n_files": len(formal["files"])},
                 "destination": {"endpoint": destination_endpoint, "eos_root": eos_root.as_posix(),
                                 "staged_root": staged_root.as_posix()},
                 "transfer": {"source_locality": "IHEP T2_CN_Beijing CCEOS", "command": "xrdcp",
                              "checksum_algorithm": "adler32", "overwrite": False,
                              "resume_policy": "verify-size-and-checksum-only"},
                 "mappings": mappings}
    plan_sha = stable_sha256(plan_core)
    staged = staged_manifest_from_plan(plan_core, plan_sha, formal)
    plan = dict(plan_core)
    plan.update({"created_at": utc_now(), "plan_sha256": plan_sha, "staged_manifest": staged})
    plan["plan_file_sha256"] = stable_sha256(plan)
    return plan


def staged_manifest_from_plan(plan: dict[str, Any], plan_sha: str, formal: dict[str, Any]) -> dict[str, Any]:
    by_source = {row["source_file"]: row for row in formal.get("inventory", []) if isinstance(row, dict)}
    mappings = plan["mappings"]
    inventory = []
    for mapping in mappings:
        row = dict(by_source.get(mapping["source_url"], {}))
        row["source_file"] = mapping["staged_url"]
        row["original_source_file"] = mapping["source_url"]
        row["staged_relative_path"] = mapping["relative_path"]
        inventory.append(row)
    core = {"schema_version": STAGED_SCHEMA, "sample": plan["sample"], "files": [row["staged_url"] for row in mappings],
            "n_files": len(mappings), "master_n_files": len(mappings),
            "master_manifest_id": formal["manifest_id"], "original_manifest_id": formal["manifest_id"],
            "original_manifest_sha256": plan["formal_manifest"]["sha256"], "staging_plan_sha256": plan_sha,
            "staging_source": plan["transfer"]["source_locality"], "inventory_columns": formal.get("inventory_columns", []),
            "inventory_totals": formal.get("inventory_totals", {}), "inventory": inventory,
            "staged_file_mapping": [{key: row[key] for key in ("source_url", "source_url_sha256", "relative_path", "eos_path", "staged_url")} for row in mappings]}
    core["manifest_id"] = stable_sha256(core)
    return core


def validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise ValueError("unexpected staging-plan schema")
    plan_copy = dict(plan)
    recorded_file_sha = plan_copy.pop("plan_file_sha256", None)
    if recorded_file_sha != stable_sha256(plan_copy):
        raise ValueError("staging plan file checksum does not match contents")
    staged = plan_copy.pop("staged_manifest", None)
    recorded_plan_sha = plan_copy.pop("plan_sha256", None)
    plan_copy.pop("created_at", None)
    if recorded_plan_sha != stable_sha256(plan_copy):
        raise ValueError("staging plan checksum does not match contents")
    if not isinstance(staged, dict) or staged.get("schema_version") != STAGED_SCHEMA:
        raise ValueError("staging plan has no staged manifest")
    require_hex64(str(staged.get("manifest_id")), "staged manifest_id")
    if staged.get("staging_plan_sha256") != recorded_plan_sha:
        raise ValueError("staged manifest is not bound to staging plan")
    mappings = plan.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        raise ValueError("staging plan has no file mappings")
    if staged.get("files") != [row.get("staged_url") for row in mappings]:
        raise ValueError("staged manifest file order differs from plan")
    for row in mappings:
        if not isinstance(row, dict):
            raise ValueError("invalid staging mapping")
        parse_xrootd_url(str(row.get("source_url")), require_cceos=True)
        parse_xrootd_url(str(row.get("staged_url")), require_cceos=False)
    destination = plan.get("destination")
    if not isinstance(destination, dict) or destination.get("endpoint") != EOS_DEFAULT_ENDPOINT:
        raise ValueError("staging plan destination is not CERN EOS")
    if destination.get("eos_root") != EOS_DEFAULT_ROOT:
        raise ValueError("staging plan destination is outside the approved campaign EOS root")


def atomic_new_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing file: {path}")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


REMOTE_CREATE_ONLY_WRITER = r'''import os,sys
path=sys.argv[1]
fd=os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
try:
    while True:
        block=sys.stdin.buffer.read(1048576)
        if not block: break
        os.write(fd, block)
    os.fsync(fd)
finally:
    os.close(fd)
'''
REMOTE_SHA256_CHECK = r'''import hashlib,pathlib,sys
p=pathlib.Path(sys.argv[1]); expected=sys.argv[2]
h=hashlib.sha256()
with p.open("rb") as f:
    for b in iter(lambda:f.read(1048576),b""): h.update(b)
sys.exit(0 if h.hexdigest()==expected else 3)
'''


def checked_local_script(value: Path) -> Path:
    path = value.resolve(strict=True)
    if path.is_symlink() or not path.is_file() or path.suffix != ".py":
        raise ValueError("--local-script must be a regular Python helper file")
    return path


def create_only_upload(settings: dict[str, Any], source: Path, destination: str) -> None:
    """Send a byte-exact file over SSH, with O_EXCL at the remote endpoint."""
    remote = shlex.join(["python3", "-c", REMOTE_CREATE_ONLY_WRITER, destination])
    subprocess.run(ssh_base(settings) + [remote], input=source.read_bytes(), check=True,
                   timeout=REMOTE_TIMEOUT_SECONDS)


def remote_sha256_check(settings: dict[str, Any], remote_path: str, expected: str) -> None:
    remote = shlex.join(["python3", "-c", REMOTE_SHA256_CHECK, remote_path, expected])
    subprocess.run(ssh_base(settings) + [remote], check=True, timeout=REMOTE_TIMEOUT_SECONDS)

def plan_summary(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    settings = ssh_settings(args)
    remote_root = safe_absolute_path(args.remote_work_root, "remote_work_root")
    local_script = checked_local_script(args.local_script)
    remote_script_name = safe_component(args.remote_script_name, "remote_script_name")
    workspace = remote_root / plan["campaign_id"] / plan["sample"] / plan["plan_sha256"]
    remote_plan = workspace / "stage-plan.json"
    remote_script = workspace / remote_script_name
    status = workspace / "staging-status.json"
    log = workspace / "staging.log"
    worker = ["python3", remote_script.as_posix(), "worker", "--plan", remote_plan.as_posix(),
              "--status", status.as_posix(), "--execute", "--authorization-id", "AUTHORIZATION_ID"]
    return {"operation": "ihep-eos-staging-launch-plan", "dry_run": True,
            "live_launch_requested": bool(args.execute),
            "authorization_required": True, "plan_sha256": plan["plan_sha256"], "campaign_id": plan["campaign_id"],
            "sample": plan["sample"], "source_locality": "IHEP T2_CN_Beijing CCEOS", "endpoint": settings,
            "workspace": str(workspace), "remote_plan": str(remote_plan), "status": str(status), "log": str(log),
            "local_script": str(local_script), "local_script_sha256": file_sha256(local_script),
            "remote_script": str(remote_script), "detached": True, "no_overwrite": True,
            "worker_command_template": shlex.join(worker), "final_staged_manifest_url": final_staged_manifest_url(plan)}


def launch(plan_path: Path, plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if not args.execute:
        raise ValueError("launch requires --execute and a non-empty --authorization-id")
    authorization_id = require_authorization_id(args.authorization_id)
    summary = plan_summary(plan, args)
    settings = summary["endpoint"]
    workspace = summary["workspace"]
    remote_plan = summary["remote_plan"]
    remote_script = summary["remote_script"]
    workspace_parent = str(PurePosixPath(workspace).parent)
    # Create only parent directories with -p. The final workspace remains an
    # atomic mkdir lock, so a duplicate launch fails before any upload.
    subprocess.run(ssh_base(settings) + [shlex.join(["mkdir", "-p", "--", workspace_parent])], check=True,
                   timeout=REMOTE_TIMEOUT_SECONDS)
    subprocess.run(ssh_base(settings) + [shlex.join(["mkdir", "--", workspace])], check=True,
                   timeout=REMOTE_TIMEOUT_SECONDS)
    # Both remote files are written with O_EXCL, not SCP's overwrite semantics.
    create_only_upload(settings, plan_path.resolve(strict=True), remote_plan)
    create_only_upload(settings, Path(summary["local_script"]), remote_script)
    remote_sha256_check(settings, remote_plan, file_sha256(plan_path))
    remote_sha256_check(settings, remote_script, summary["local_script_sha256"])
    worker = summary["worker_command_template"].replace("AUTHORIZATION_ID", authorization_id)
    remote = f"cd {shlex.quote(workspace)} && nohup {worker} > {shlex.quote(summary['log'])} 2>&1 < /dev/null & echo $!"
    result = subprocess.run(ssh_base(settings) + [remote], check=True, text=True, capture_output=True, timeout=REMOTE_TIMEOUT_SECONDS)
    pid_text = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if not pid_text.isdigit():
        raise RuntimeError("IHEP launcher did not return a numeric detached PID")
    return {"operation": "ihep-eos-staging-launch", "authorization_id": authorization_id,
            "pid": int(pid_text), "launched_at": utc_now(),
            "remote_plan_sha256": file_sha256(plan_path), **summary}


def xrdfs(endpoint: str, operation: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["xrdfs", endpoint] + operation, text=True, capture_output=True, timeout=REMOTE_TIMEOUT_SECONDS)


def xrd_stat(endpoint: str, path: str) -> dict[str, Any] | None:
    result = xrdfs(endpoint, ["stat", path])
    if result.returncode != 0:
        return None
    match = re.search(r"Size:\s*(\d+)", result.stdout)
    if match is None:
        raise RuntimeError(f"could not parse XRootD stat size for {path}: {result.stdout.strip()}")
    return {"size": int(match.group(1)), "raw": result.stdout.strip()}


def xrd_checksum(endpoint: str, path: str) -> str:
    result = xrdfs(endpoint, ["query", "checksum", path])
    if result.returncode != 0:
        raise RuntimeError(f"XRootD checksum query failed for {path}: {result.stderr.strip()}")
    tokens = result.stdout.strip().split()
    if len(tokens) < 2 or tokens[0].lower() != "adler32" or not re.fullmatch(r"[0-9a-fA-F]{8}", tokens[-1]):
        raise RuntimeError(f"could not parse Adler-32 checksum for {path}: {result.stdout.strip()}")
    return tokens[-1].lower()


def compare_existing(source: dict[str, Any], destination: dict[str, Any] | None) -> str:
    """Classify a final path.  Only an exactly verified path may be reused."""
    if destination is None:
        return "copy"
    if source["size"] != destination["size"]:
        return "mismatch"
    if source["adler32"] != destination["adler32"]:
        return "mismatch"
    return "verified-existing"


def atomic_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def worker_status(plan: dict[str, Any], *, state: str, authorization_id: str | None,
                  started_at: str, completed: int, skipped: int, failed: list[dict[str, str]],
                  results: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": STATUS_SCHEMA, "state": state, "campaign_id": plan["campaign_id"],
            "sample": plan["sample"], "plan_sha256": plan["plan_sha256"], "staged_manifest_id": plan["staged_manifest"]["manifest_id"],
            "authorization_id": authorization_id, "started_at": started_at, "updated_at": utc_now(),
            "pid": os.getpid(), "total": len(plan["mappings"]), "completed": completed, "skipped_verified": skipped,
            "failed": failed, "results": results}


def existing_manifest_matches(payload: dict[str, Any], plan: dict[str, Any]) -> bool:
    """A completed launch can be resumed only when its published identity agrees."""
    return (payload.get("schema_version") == STAGED_SCHEMA
            and payload.get("manifest_id") == plan["staged_manifest"]["manifest_id"]
            and payload.get("staging_plan_sha256") == plan["plan_sha256"]
            and payload.get("files") == plan["staged_manifest"]["files"])


def final_staged_manifest_url(plan: dict[str, Any]) -> str:
    return xrootd_url(plan["destination"]["endpoint"], PurePosixPath(plan["destination"]["staged_root"]) / "staged-manifest.json")


def fetch_plan(plan: dict[str, Any], output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite local staged manifest: {output}")
    return {"operation": "ihep-eos-staged-manifest-fetch-plan", "dry_run": True,
            "authorization_required": True, "plan_sha256": plan["plan_sha256"],
            "source_url": final_staged_manifest_url(plan), "output": str(output),
            "expected_manifest_id": plan["staged_manifest"]["manifest_id"],
            "next_consumer": "prepare_efficiency_shards.py --input-file-manifest"}


def fetch_staged_manifest(plan: dict[str, Any], output: Path, *, fetch: bool, authorization_id: str | None) -> dict[str, Any]:
    summary = fetch_plan(plan, output)
    if not fetch:
        return summary
    authorization = require_authorization_id(authorization_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)[1])
    try:
        copied = subprocess.run(["xrdcp", "--nopbar", summary["source_url"], str(temporary)], text=True, capture_output=True)
        if copied.returncode != 0:
            raise RuntimeError(f"could not fetch staged manifest: {copied.stderr.strip()}")
        payload = json.loads(temporary.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not existing_manifest_matches(payload, plan):
            raise RuntimeError("fetched staged manifest does not match the frozen staging plan")
        evidence = payload.get("staging_evidence")
        if not isinstance(evidence, dict) or len(evidence.get("files", [])) != len(plan["mappings"]):
            raise RuntimeError("fetched staged manifest lacks complete staging evidence")
        # Create-only atomic publish keeps an existing local artifact as
        # evidence instead of overwriting it.
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {"operation": "ihep-eos-staged-manifest-fetch", "authorization_id": authorization,
            "plan_sha256": plan["plan_sha256"], "source_url": summary["source_url"], "output": str(output),
            "output_sha256": file_sha256(output), "manifest_id": plan["staged_manifest"]["manifest_id"]}


def read_remote_json(endpoint: str, path: str) -> dict[str, Any]:
    temporary = Path(tempfile.mkstemp(prefix="read-staged-manifest-", suffix=".json")[1])
    try:
        copied = subprocess.run(["xrdcp", "--nopbar", xrootd_url(endpoint, PurePosixPath(path)), str(temporary)],
                                text=True, capture_output=True)
        if copied.returncode != 0:
            raise RuntimeError(f"could not read existing staged manifest: {copied.stderr.strip()}")
        payload = json.loads(temporary.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("existing staged manifest is not a JSON object")
        return payload
    finally:
        temporary.unlink(missing_ok=True)


def write_remote_manifest(plan: dict[str, Any], results: list[dict[str, Any]]) -> str:
    destination = plan["destination"]
    endpoint = destination["endpoint"]
    staged_root = destination["staged_root"]
    final_path = f"{staged_root}/staged-manifest.json"
    if xrd_stat(endpoint, final_path) is not None:
        existing = read_remote_json(endpoint, final_path)
        if existing_manifest_matches(existing, plan):
            return "verified-existing"
        raise RuntimeError("staged-manifest.json already exists with a different identity; refusing replacement")
    manifest = dict(plan["staged_manifest"])
    manifest["staging_evidence"] = {"completed_at": utc_now(), "worker_pid": os.getpid(), "files": results}
    payload = canonical(manifest) + b"\n"
    local = Path(tempfile.mkstemp(prefix="staged-manifest-", suffix=".json")[1])
    try:
        local.write_bytes(payload)
        tmp_path = f"{staged_root}/.incoming/staged-manifest.{plan['plan_sha256']}.{os.getpid()}.json"
        xrdfs(endpoint, ["mkdir", "-p", f"{staged_root}/.incoming"])
        # No --force: an existing temporary object is evidence, not permission
        # to replace it.  An existing final manifest is accepted only bytewise.
        copied = subprocess.run(["xrdcp", "--nopbar", str(local), xrootd_url(endpoint, PurePosixPath(tmp_path))], text=True, capture_output=True)
        if copied.returncode != 0:
            raise RuntimeError(f"could not upload staged manifest: {copied.stderr.strip()}")
        moved = xrdfs(endpoint, ["mv", tmp_path, final_path])
        if moved.returncode != 0:
            if xrd_stat(endpoint, final_path) is not None and existing_manifest_matches(read_remote_json(endpoint, final_path), plan):
                return "verified-existing"
            raise RuntimeError("staged-manifest.json already exists or could not be promoted; inspect it before retrying")
        return "published"
    finally:
        local.unlink(missing_ok=True)


def worker(plan_path: Path, status_path: Path, args: argparse.Namespace) -> dict[str, Any]:
    if not args.execute:
        raise ValueError("worker requires --execute and a non-empty --authorization-id")
    authorization_id = require_authorization_id(args.authorization_id)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    validate_plan(plan)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    lock = status_path.with_suffix(status_path.suffix + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"worker lock already exists: {lock}") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"pid={os.getpid()} plan_sha256={plan['plan_sha256']}\n")
    started = utc_now()
    completed = skipped = 0
    failures: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    atomic_status(status_path, worker_status(plan, state="running", authorization_id=authorization_id,
                                               started_at=started, completed=0, skipped=0, failed=[], results=[]))
    try:
        endpoint = plan["destination"]["endpoint"]
        staged_root = plan["destination"]["staged_root"]
        mkdir = xrdfs(endpoint, ["mkdir", "-p", f"{staged_root}/files"])
        if mkdir.returncode != 0:
            raise RuntimeError(f"could not create EOS staging directory: {mkdir.stderr.strip()}")
        for mapping in plan["mappings"]:
            source_stat = xrd_stat(mapping["source_endpoint"], mapping["source_path"])
            if source_stat is None:
                raise RuntimeError(f"source disappeared: {mapping['source_url']}")
            source = {"size": source_stat["size"], "adler32": xrd_checksum(mapping["source_endpoint"], mapping["source_path"])}
            final_stat = xrd_stat(endpoint, mapping["eos_path"])
            destination = None if final_stat is None else {"size": final_stat["size"], "adler32": xrd_checksum(endpoint, mapping["eos_path"])}
            action = compare_existing(source, destination)
            if action == "mismatch":
                raise RuntimeError(f"existing EOS object differs; refusing overwrite: {mapping['staged_url']}")
            if action == "copy":
                temp_path = f"{staged_root}/.incoming/{mapping['source_url_sha256']}.{os.getpid()}.root"
                mkdir_temp = xrdfs(endpoint, ["mkdir", "-p", f"{staged_root}/.incoming"])
                if mkdir_temp.returncode != 0:
                    raise RuntimeError(f"could not create EOS incoming directory: {mkdir_temp.stderr.strip()}")
                copied = subprocess.run(["xrdcp", "--nopbar", "--cksum", "adler32", mapping["source_url"],
                                         xrootd_url(endpoint, PurePosixPath(temp_path))], text=True, capture_output=True)
                if copied.returncode != 0:
                    raise RuntimeError(f"xrdcp failed for {mapping['source_url']}: {copied.stderr.strip()}")
                temp_stat = xrd_stat(endpoint, temp_path)
                temp = None if temp_stat is None else {"size": temp_stat["size"], "adler32": xrd_checksum(endpoint, temp_path)}
                if compare_existing(source, temp) != "verified-existing":
                    raise RuntimeError(f"temporary EOS verification failed: {mapping['staged_url']}")
                moved = xrdfs(endpoint, ["mv", temp_path, mapping["eos_path"]])
                if moved.returncode != 0:
                    # A racing successful worker is safe only after validating
                    # the final object; otherwise no automatic overwrite occurs.
                    final_stat = xrd_stat(endpoint, mapping["eos_path"])
                    final = None if final_stat is None else {"size": final_stat["size"], "adler32": xrd_checksum(endpoint, mapping["eos_path"])}
                    if compare_existing(source, final) != "verified-existing":
                        raise RuntimeError(f"could not promote verified EOS object: {mapping['staged_url']}")
                completed += 1
            else:
                skipped += 1
            results.append({"source_url": mapping["source_url"], "staged_url": mapping["staged_url"], **source, "action": action})
            atomic_status(status_path, worker_status(plan, state="running", authorization_id=authorization_id,
                                                       started_at=started, completed=completed, skipped=skipped,
                                                       failed=failures, results=results))
        manifest_action = write_remote_manifest(plan, results)
        result = worker_status(plan, state="complete", authorization_id=authorization_id, started_at=started,
                               completed=completed, skipped=skipped, failed=failures, results=results)
        result["staged_manifest_action"] = manifest_action
        atomic_status(status_path, result)
        return result
    except Exception as exc:
        failures.append({"error": str(exc)})
        result = worker_status(plan, state="failed", authorization_id=authorization_id, started_at=started,
                               completed=completed, skipped=skipped, failed=failures, results=results)
        atomic_status(status_path, result)
        raise
    finally:
        lock.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    plan = modes.add_parser("plan", help="create an auditable local staging plan; never contacts IHEP/EOS")
    plan.add_argument("--formal-manifest", type=Path, required=True)
    plan.add_argument("--campaign-id", required=True)
    plan.add_argument("--campaign-identity-sha256", required=True)
    plan.add_argument("--eos-root", default=EOS_DEFAULT_ROOT)
    plan.add_argument("--eos-endpoint", default=EOS_DEFAULT_ENDPOINT)
    plan.add_argument("--output", type=Path, required=True)
    launch_parser = modes.add_parser("launch-plan", help="emit a detached IHEP upload/launch plan; no network or writes")
    launch_parser.add_argument("--plan", type=Path, required=True)
    launch_parser.add_argument("--local-script", type=Path, required=True,
                               help="local helper uploaded create-only into the new remote workspace")
    launch_parser.add_argument("--remote-script-name", default="ihep_eos_staging.py",
                               help="safe filename inside the new remote workspace")
    launch_parser.add_argument("--remote-work-root", required=True)
    launch_parser.add_argument("--ssh-host", default=IHEP_DEFAULT_HOST)
    launch_parser.add_argument("--ssh-user", default=IHEP_DEFAULT_USER)
    launch_parser.add_argument("--ssh-port", type=int, default=None)
    launch_parser.add_argument("--ssh-config", default="/dev/null")
    launch_parser.add_argument("--execute", action="store_true")
    launch_parser.add_argument("--authorization-id")
    # Explicitly repeat the arguments for the live command. Keeping this
    # parser independent makes the authorization surface obvious in --help.
    launch_live = modes.add_parser("launch", help="create-only upload plan/helper and start detached IHEP worker")
    launch_live.add_argument("--plan", type=Path, required=True)
    launch_live.add_argument("--local-script", type=Path, required=True,
                             help="local helper uploaded create-only into the new remote workspace")
    launch_live.add_argument("--remote-script-name", default="ihep_eos_staging.py",
                             help="safe filename inside the new remote workspace")
    launch_live.add_argument("--remote-work-root", required=True)
    launch_live.add_argument("--ssh-host", default=IHEP_DEFAULT_HOST)
    launch_live.add_argument("--ssh-user", default=IHEP_DEFAULT_USER)
    launch_live.add_argument("--ssh-port", type=int, default=None)
    launch_live.add_argument("--ssh-config", default="/dev/null")
    launch_live.add_argument("--execute", action="store_true")
    launch_live.add_argument("--authorization-id")
    fetch_preview = modes.add_parser("fetch-plan", help="plan a verified EOS manifest readback; does not contact EOS")
    fetch_preview.add_argument("--plan", type=Path, required=True)
    fetch_preview.add_argument("--output", type=Path, required=True)
    fetch_live = modes.add_parser("fetch", help="read back a verified staged manifest into a fresh local file")
    fetch_live.add_argument("--plan", type=Path, required=True)
    fetch_live.add_argument("--output", type=Path, required=True)
    fetch_live.add_argument("--fetch", action="store_true")
    fetch_live.add_argument("--authorization-id")
    worker_parser = modes.add_parser("worker", help="run on IHEP; writes EOS only with explicit authorization")
    worker_parser.add_argument("--plan", type=Path, required=True)
    worker_parser.add_argument("--status", type=Path, required=True)
    worker_parser.add_argument("--execute", action="store_true")
    worker_parser.add_argument("--authorization-id")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "plan":
        plan = build_plan(args)
        atomic_new_json(args.output, plan)
        print(json.dumps({"operation": "ihep-eos-staging-plan", "dry_run": True, "plan": str(args.output),
                          "plan_sha256": plan["plan_sha256"], "sample": plan["sample"], "n_files": len(plan["mappings"])}, sort_keys=True))
        return
    if args.mode in {"launch-plan", "launch", "fetch-plan", "fetch"}:
        plan_path = args.plan.resolve(strict=True)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        validate_plan(plan)
        if args.mode == "launch-plan":
            result = plan_summary(plan, args)
        elif args.mode == "launch":
            result = launch(plan_path, plan, args)
        elif args.mode == "fetch-plan":
            result = fetch_plan(plan, args.output)
        else:
            result = fetch_staged_manifest(plan, args.output, fetch=args.fetch, authorization_id=args.authorization_id)
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    if args.mode == "worker":
        print(json.dumps(worker(args.plan.resolve(strict=True), args.status.resolve(), args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

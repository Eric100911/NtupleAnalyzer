#!/usr/bin/env python3
"""Create (but never submit) the frozen IHEP HepJob workspaces.

The input authority is the ``ihep_freeze_v2`` report.  Dry-run is the default
and does not contact IHEP.  A live run requires both ``--execute`` and a
non-empty authorization id; it creates exactly one fresh remote root, uploads
only the declared control inventory, verifies whole-file hashes, rewrites the
queue paths remotely, and runs the workspace generator serially.  Neither this
helper nor the remote bootstrap invokes ``hep_sub``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any


FREEZE_ID = "ihep_freeze_v2"
BASE_SAMPLES = ("JJP_DPS1", "JJP_DPS2_CS", "JJP_DPS2_G", "JJP_SPS_CS", "JJP_SPS_G")
TPS_SAMPLES = frozenset({"JJP_TPS", "JJP_TPS_MC_v4_1"})
# Public default for new campaign configuration; the selected freeze report
# remains the execution and formal-manifest identity.
SAMPLES = BASE_SAMPLES + ("JJP_TPS",)


def selected_samples(samples: Any) -> tuple[str, ...]:
    """Validate the fixed base set and choose exactly one TPS formal identity."""
    if not isinstance(samples, dict):
        raise ValueError("freeze report samples must be an object")
    keys = set(samples)
    tps = keys & TPS_SAMPLES
    expected = set(BASE_SAMPLES) | tps
    if keys != expected or len(tps) != 1:
        raise ValueError("freeze report must declare the five base samples and exactly one of JJP_TPS or JJP_TPS_MC_v4_1")
    return BASE_SAMPLES + (next(iter(tps)),)

REMOTE_PARENT = "/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer"
SSH_TARGET = "wangchi@lxlogin.ihep.ac.cn"
SSH_OPTIONS = ("-F", "/dev/null", "-o", "BatchMode=yes", "-o", "ControlMaster=no")
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
AUTH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+=/-]*$")
DEFAULT_PROXY_SOURCE = "/afs/cern.ch/user/c/chiw/condor/x509up"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def remote_root(value: str) -> str:
    path = PurePosixPath(value)
    parent = PurePosixPath(REMOTE_PARENT)
    if path.parent != parent or not TOKEN.fullmatch(path.name):
        raise ValueError(f"--remote-root must be a safe fresh child of {REMOTE_PARENT}")
    return path.as_posix()


def safe_relative(value: str, label: str) -> Path:
    raw = PurePosixPath(value)
    if not value or raw.is_absolute() or any(part in {"", ".", ".."} for part in raw.parts):
        raise ValueError(f"{label} must be a safe non-empty relative path")
    return Path(*raw.parts)


def declared_file(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str):
        raise ValueError(f"freeze report {label} must be a relative path string")
    path = root / safe_relative(value, label)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"freeze report {label} is not a regular file: {path}")
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"freeze report {label} escapes the freeze root") from exc
    return resolved


def declared_proxy_source(value: Path | None) -> Path:
    # The CMS VOMS proxy is staged as a secret under credentials/; only its
    # path, size, and sha256 are ever recorded, never its contents.  Reject
    # symlinks so a staged proxy can never be swapped for an unexpected target.
    source = value if value is not None else Path(os.environ.get("X509_USER_PROXY", DEFAULT_PROXY_SOURCE))
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"--proxy-source is not a regular file: {source}")
    return source


def require_report_sha256(path: Path, value: Any, label: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"freeze report {label} must be a SHA-256")
    if sha256(path) != value:
        raise ValueError(f"freeze report {label} does not match the declared file")


def load_freeze(freeze_root: Path, report_path: Path | None) -> tuple[Path, dict[str, Any]]:
    root = freeze_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"--freeze-root is not a directory: {root}")
    report = (report_path.resolve(strict=True) if report_path else root / "metadata" / "freeze_report.json")
    if report.is_symlink() or not report.is_file():
        raise ValueError("provide --freeze-report or place ihep_freeze_v2.report.json under --freeze-root")
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid freeze report: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("freeze_id") not in {FREEZE_ID, "ihep_freeze_v3"}:
        raise ValueError(f"freeze report must declare freeze_id={FREEZE_ID!r}")
    try:
        report.resolve(strict=True).relative_to(root)
    except ValueError as exc:
        raise ValueError("--freeze-report must be inside --freeze-root") from exc
    if isinstance(payload.get("runtime"), dict):
        runtime = payload["runtime"]
        config = payload.get("efficiency_config")
        samples = payload.get("samples")
        if not isinstance(config, dict) or not isinstance(samples, dict):
            raise ValueError("ihep_freeze_v2 report lacks config or samples sections")
        runtime_path = declared_file(root, runtime.get("tarball"), "runtime.tarball")
        config_path = declared_file(root, config.get("path"), "efficiency_config.path")
        require_report_sha256(runtime_path, runtime.get("sha256"), "runtime.sha256")
        require_report_sha256(config_path, config.get("sha256"), "efficiency_config.sha256")
        normalized = dict(payload)
        normalized["runtime_tarball"] = runtime.get("tarball")
        normalized["efficiency_config"] = config.get("path")
        normalized["samples"] = {}
        for sample, item in samples.items():
            if not isinstance(item, dict):
                raise ValueError(f"invalid freeze sample section: {sample}")
            formal_path = declared_file(root, item.get("formal_manifest"), f"samples.{sample}.formal_manifest")
            queue_path = declared_file(root, item.get("queue"), f"samples.{sample}.queue")
            require_report_sha256(formal_path, item.get("formal_manifest_sha256"), f"samples.{sample}.formal_manifest_sha256")
            require_report_sha256(queue_path, item.get("queue_sha256"), f"samples.{sample}.queue_sha256")
            shard_dir = root / safe_relative(item.get("shard_manifests_dir", ""), f"samples.{sample}.shard_manifests_dir")
            if shard_dir.is_symlink() or not shard_dir.is_dir():
                raise ValueError(f"invalid freeze shard directory for {sample}")
            shard_paths = sorted(path.relative_to(root).as_posix() for path in shard_dir.glob("*.json") if path.is_file() and not path.is_symlink())
            if len(shard_paths) != item.get("n_shards"):
                raise ValueError(f"freeze shard count mismatch for {sample}")
            normalized["samples"][sample] = {"formal_manifest": item.get("formal_manifest"), "queue": item.get("queue"), "shard_manifests": shard_paths}
        payload = normalized
    return root, payload


def parse_queue(queue: Path, sample: str, shards: list[Path]) -> int:
    allowed = {path.resolve(strict=True) for path in shards}
    seen: set[Path] = set()
    indices: list[int] = []
    for line in queue.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split(None, 2)
        if len(fields) != 3 or fields[0] != sample or not fields[1].isdigit():
            raise ValueError(f"invalid frozen queue row for {sample}: {line!r}")
        # Resolve lexically even when a stale queue path does not exist; it
        # should be reported as undeclared rather than leaking OSError.
        manifest = Path(fields[2]).resolve(strict=False)
        if manifest not in allowed:
            matches = [path for path in allowed if path.name == manifest.name]
            if len(matches) != 1:
                raise ValueError(f"queue manifest is not report-declared for {sample}: {manifest}")
            manifest = matches[0]
        if manifest in seen:
            raise ValueError(f"duplicate shard manifest in queue for {sample}: {manifest.name}")
        seen.add(manifest); indices.append(int(fields[1]))
    if seen != allowed or sorted(indices) != list(range(len(shards))):
        raise ValueError(f"queue does not provide complete report-declared shard coverage for {sample}")
    return len(indices)


def control_inventory(root: Path, freeze: dict[str, Any], proxy_source: Path | None = None) -> tuple[dict[str, Path], dict[str, int]]:
    runtime = declared_file(root, freeze.get("runtime_tarball"), "runtime_tarball")
    config = declared_file(root, freeze.get("efficiency_config"), "efficiency_config")
    proxy = declared_proxy_source(proxy_source)
    samples = freeze.get("samples")
    execution_samples = selected_samples(samples)
    files: dict[str, Path] = {
        "source/runtime/runtime.tar.gz": runtime,
        "source/configs/efficiency/tps_nominal.yaml": config,
        "source/condor/generate_ihep_efficiency_dag.py": Path(__file__).resolve().parents[3] / "condor/generate_ihep_efficiency_dag.py",
        "source/condor/run_ihep_efficiency_shard.sh": Path(__file__).resolve().parents[3] / "condor/run_ihep_efficiency_shard.sh",
        "source/condor/run_ihep_efficiency_merge_only.sh": Path(__file__).resolve().parents[3] / "condor/run_ihep_efficiency_merge_only.sh",
        "credentials/x509_user_proxy": proxy,
    }
    if any(path.is_symlink() or not path.is_file() for path in files.values()):
        raise ValueError("generator and worker control files must be regular repository files")
    counts: dict[str, int] = {}
    for sample in execution_samples:
        item = samples[sample]
        if not isinstance(item, dict):
            raise ValueError(f"freeze report samples.{sample} must be an object")
        formal = declared_file(root, item.get("formal_manifest"), f"samples.{sample}.formal_manifest")
        queue = declared_file(root, item.get("queue"), f"samples.{sample}.queue")
        raw_shards = item.get("shard_manifests")
        if not isinstance(raw_shards, list) or not raw_shards:
            raise ValueError(f"freeze report samples.{sample}.shard_manifests must be a non-empty list")
        shards = [declared_file(root, value, f"samples.{sample}.shard_manifests") for value in raw_shards]
        if len(set(shards)) != len(shards) or len({path.name for path in shards}) != len(shards):
            raise ValueError(f"freeze report shard manifests must have unique paths and basenames for {sample}")
        counts[sample] = parse_queue(queue, sample, shards)
        files[f"inputs/{sample}/formal_manifest.json"] = formal
        files[f"inputs/{sample}/queue.source.txt"] = queue
        for shard in shards:
            files[f"inputs/{sample}/shards/{shard.name}"] = shard
    return dict(sorted(files.items())), counts


def ssh_base() -> list[str]:
    return ["ssh", *SSH_OPTIONS, SSH_TARGET]


def remote_quote(command: list[str]) -> list[str]:
    return ssh_base() + [shlex.join(command)]


def atomic_create(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def stage_inventory(files: dict[str, Path]) -> tuple[tempfile.TemporaryDirectory[str], dict[str, dict[str, Any]]]:
    temporary = tempfile.TemporaryDirectory(prefix="ihep-workspace-control-")
    stage = Path(temporary.name)
    inventory: dict[str, dict[str, Any]] = {}
    for relative, source in files.items():
        destination = stage / safe_relative(relative, "control artifact")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if relative.startswith("credentials/"):
            # copyfile does not preserve the source mode, so a 600 proxy would
            # land 644 and leak; force the secret to owner-only explicitly.
            os.chmod(destination, 0o600)
        inventory[relative] = {"size": destination.stat().st_size, "sha256": sha256(destination)}
    return temporary, inventory


REMOTE_BOOTSTRAP = r'''import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); expected=json.loads(sys.stdin.readline()); samples=json.loads(sys.stdin.readline())
def digest(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(1048576),b""): h.update(block)
 return h.hexdigest()
actual={}; bad=[]
for rel,row in expected.items():
 p=root.joinpath(*pathlib.PurePosixPath(rel).parts)
 if p.is_symlink() or not p.is_file() or p.stat().st_size!=row["size"] or digest(p)!=row["sha256"]: bad.append(rel)
 else: actual[rel]=digest(p)
if bad: raise SystemExit("control artifact hash mismatch: "+",".join(bad))
queue_sha={}
for sample,count in samples.items():
 source=root/"inputs"/sample/"queue.source.txt"; target=root/"inputs"/sample/"queue.txt"; output=[]; seen=[]
 for raw in source.read_text().splitlines():
  if not raw.strip() or raw.lstrip().startswith("#"): output.append(raw); continue
  fields=raw.split(None,2)
  if len(fields)!=3 or fields[0]!=sample or not fields[1].isdigit(): raise SystemExit("invalid queue row "+sample)
  name=pathlib.PurePosixPath(fields[2]).name
  if not name or name in seen: raise SystemExit("invalid shard basename "+sample)
  seen.append(name); output.append(f"{sample} {fields[1]} {root}/inputs/{sample}/shards/{name}")
 if sorted(int(line.split()[1]) for line in output if line.strip() and not line.lstrip().startswith("#")) != list(range(count)): raise SystemExit("incomplete queue "+sample)
 target.write_text("\n".join(output)+"\n"); queue_sha[sample]=digest(target)
(root/"campaign").mkdir()
(root/"logs").mkdir()
workflows={}; commands=[]
for sample,count in samples.items():
 command=[sys.executable,str(root/"source/condor/generate_ihep_efficiency_dag.py"),"--sample",sample,"--queue-file",str(root/"inputs"/sample/"queue.txt"),"--formal-manifest",str(root/"inputs"/sample/"formal_manifest.json"),"--ihep-campaign-root",str(root/"campaign"),"--runtime-tarball",str(root/"source/runtime/runtime.tar.gz"),"--workspace-dir",str(root/"workspaces"/sample),"--tree-path","auto","--efficiency-config",str(root/"source/configs/efficiency/tps_nominal.yaml"),"--config-policy","strict","--efficiency-backend","vectorized","--remote-access-mode","direct","--proxy-path",str(root/"credentials"/"x509_user_proxy"),"--skip-plots"]
 commands.append(command)
 with (root/"logs"/("generate_"+sample+".log")).open("w") as log: subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 workflow=json.loads((root/"workspaces"/sample/"workflow.json").read_text())
 if len(workflow.get("nodes",[]))!=count+1 or workflow["nodes"][-1].get("name")!="MERGE": raise SystemExit("workflow node count mismatch "+sample)
 workflows[sample]={"nodes":len(workflow["nodes"]),"shards":count,"workflow_sha256":digest(root/"workspaces"/sample/"workflow.json")}
print(json.dumps({"control_sha256":actual,"queue_sha256":queue_sha,"workflows":workflows,"generator_commands":commands,"hep_sub_process_calls":0},sort_keys=True))'''


def plan(freeze_root: Path, freeze_report: Path | None, *, execute: bool, authorization_id: str | None, remote_root_value: str, proxy_source: Path | None = None) -> tuple[dict[str, Any], dict[str, Path]]:
    root, freeze = load_freeze(freeze_root, freeze_report)
    files, counts = control_inventory(root, freeze, proxy_source)
    if execute and (not authorization_id or not AUTH.fullmatch(authorization_id)):
        raise ValueError("--execute requires a non-empty conservative --authorization-id")
    target = remote_root(remote_root_value)
    payload = {
        "schema_version": "ihep-workspace-deploy/v1", "operation": "create-only-ihep-workspace-deploy",
        "freeze_id": freeze["freeze_id"], "freeze_root": str(root), "freeze_report": str((freeze_report or root / "metadata" / "freeze_report.json").resolve()),
        "dry_run": not execute, "authorization_id": authorization_id if execute else None,
        "remote": {"root": target, "ssh": ["ssh", *SSH_OPTIONS, SSH_TARGET]},
        "control_artifacts": {key: {"source": str(value), "size": value.stat().st_size, "sha256": sha256(value)} for key, value in files.items()},
        "samples": {sample: {"expected_shards": counts[sample], "expected_workflow_nodes": counts[sample] + 1} for sample in counts},
        "guarantees": {"remote_root_fresh_mkdir": True, "queue_rewrite": "remote deterministic absolute deployed shard paths", "whole_file_readback": True, "serial_generator": True, "hep_sub_process_calls": 0},
        "commands_planned": {"mkdir": remote_quote(["mkdir", "--", target]), "transfer": ["rsync", "--archive", "--checksum", "--protect-args", "-e", shlex.join(ssh_base()[:-1]), "CONTROL_STAGE/", f"{SSH_TARGET}:{target}/"], "bootstrap": remote_quote(["python3", "-c", REMOTE_BOOTSTRAP, target, "< expected-control-json-and-samples-json-on-stdin >"])},
    }
    return payload, files


def execute_deployment(payload: dict[str, Any], files: dict[str, Path]) -> dict[str, Any]:
    target = remote_root(str(payload.get("remote", {}).get("root", "")))
    expected = {key: {"size": row["size"], "sha256": row["sha256"]} for key, row in payload["control_artifacts"].items()}
    temporary, inventory = stage_inventory(files)
    try:
        if inventory != expected:
            raise RuntimeError("staged control inventory differs from the planned control artifacts")
        payload["control_artifacts"] = inventory
        subprocess.run(remote_quote(["mkdir", "--", target]), check=True, timeout=45)
        transport = shlex.join(ssh_base()[:-1])
        subprocess.run(["rsync", "--archive", "--checksum", "--protect-args", "-e", transport, f"{temporary.name}/", f"{SSH_TARGET}:{target}/"], check=True, timeout=900)
        sample_counts = {sample: payload["samples"][sample]["expected_shards"] for sample in payload["samples"]}
        command = remote_quote(["python3", "-c", REMOTE_BOOTSTRAP, target])
        completed = subprocess.run(command, check=False, timeout=900, text=True, input=json.dumps(inventory, sort_keys=True) + "\n" + json.dumps(sample_counts, sort_keys=True) + "\n", capture_output=True)
        if completed.returncode:
            raise RuntimeError(f"remote bootstrap failed: {completed.stderr.strip() or completed.stdout.strip()}")
        try:
            remote = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("remote bootstrap did not return JSON") from exc
        if remote.get("control_sha256") != {key: row["sha256"] for key, row in inventory.items()}:
            raise RuntimeError("remote whole-file control-artifact readback mismatch")
        if remote.get("hep_sub_process_calls") != 0:
            raise RuntimeError("remote bootstrap reported a forbidden HepJob submission call")
        for sample, row in payload["samples"].items():
            actual = remote.get("workflows", {}).get(sample, {})
            if actual.get("nodes") != row["expected_workflow_nodes"]:
                raise RuntimeError(f"remote workflow node count mismatch for {sample}")
        payload["remote_result"] = remote
        payload["dry_run"] = False; payload["completed_at"] = utc_now(); payload["status"] = "complete"
        return payload
    finally:
        temporary.cleanup()


def reserve_report_dir(report_dir: Path) -> Path:
    target = report_dir.resolve()
    if target.exists():
        raise FileExistsError(f"refusing to reuse existing report directory: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.mkdir(target)
    return target


def persist(report_dir: Path, payload: dict[str, Any], *, status: str, log: str) -> None:
    atomic_create(report_dir / "deployment-report.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
    atomic_create(report_dir / "deployment-status.json", json.dumps({"status": status, "updated_at": utc_now()}, indent=2, sort_keys=True) + "\n")
    atomic_create(report_dir / "deployment.log", log + "\n")


def persist_failure(report_dir: Path, error: Exception) -> None:
    atomic_create(report_dir / "deployment-status.json", json.dumps({"status": "failed", "updated_at": utc_now(), "error": str(error)}, indent=2, sort_keys=True) + "\n")
    atomic_create(report_dir / "deployment.log", f"Deployment failed before completion: {error}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-root", type=Path, required=True)
    parser.add_argument("--freeze-report", type=Path)
    parser.add_argument("--report-dir", type=Path, required=True, help="fresh local directory for deployment report/status/log")
    parser.add_argument("--remote-root", required=True, help=f"fresh safe child under {REMOTE_PARENT}")
    parser.add_argument("--execute", action="store_true", help="perform the create-only remote deployment")
    parser.add_argument("--authorization-id")
    parser.add_argument("--proxy-source", type=Path, default=os.environ.get("X509_USER_PROXY", DEFAULT_PROXY_SOURCE),
                        help="readable CMS VOMS proxy staged as credentials/x509_user_proxy (default: $X509_USER_PROXY)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reserved: Path | None = None
    try:
        reserved = reserve_report_dir(args.report_dir)
        payload, files = plan(args.freeze_root, args.freeze_report, execute=args.execute, authorization_id=args.authorization_id, remote_root_value=args.remote_root, proxy_source=args.proxy_source)
        if args.execute:
            payload = execute_deployment(payload, files)
            persist(reserved, payload, status="complete", log="Remote workspace creation completed; no HepJob was submitted.")
        else:
            payload["status"] = "dry-run"; payload["created_at"] = utc_now()
            persist(reserved, payload, status="dry-run", log="Dry run only; no SSH, transfer, generator, or HepJob action was performed.")
        print(json.dumps(payload, indent=2, sort_keys=True))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        if reserved is not None:
            try:
                persist_failure(reserved, exc)
            except OSError:
                pass
        print(f"deploy_ihep_workspace.py: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

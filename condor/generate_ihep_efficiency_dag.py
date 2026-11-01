#!/usr/bin/env python3
"""Generate, but never submit, an IHEP HepJob workspace for JJP efficiency.

IHEP HepJob is backed by HTCondor, but it is operated through ``hep_sub``.  A
separate workspace avoids leaking CERN submit-file, proxy, EOS, or JobFlavour
assumptions into this CCEOS-local processing path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tarfile


REPO_ROOT = Path(__file__).resolve().parents[1]
IHEP_SCRATCH_ROOT = Path("/scratchfs2/cms/wangchi")
CCEOS_PREFIX = "root://cceos.ihep.ac.cn:1094///"
LCG_VIEW = "/cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt"
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_./:=+@%-]+$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SAFE_SAMPLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]*$")
_MAX_SUBMISSION_RETRIES = 5
_TPS_CONFIG = "configs/efficiency/tps_nominal.yaml"
_RUNTIME_MEMBERS = frozenset({
    "run_efficiency.py",
    "scripts/efficiency/merge_efficiency_shards.py",
    "efficiency_workflow/formal_merge.py",
    _TPS_CONFIG,
})


def _safe(value: str, label: str) -> str:
    if not value or not _SAFE_TOKEN.fullmatch(value):
        raise ValueError(f"{label} must be a non-empty safe token (letters, digits, / . _ : = + @ % -)")
    return value


def _readable_file(path: Path, label: str) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path: {path}")
    if not path.is_file() or not os.access(path, os.R_OK):
        raise FileNotFoundError(f"{label} is not a readable regular file: {path}")
    _safe(str(path), label)
    return path.resolve()


def _ihep_path(path: Path, label: str, *, must_exist: bool) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute under {IHEP_SCRATCH_ROOT}: {path}")
    _safe(str(path), label)
    resolved = path.resolve(strict=must_exist)
    root = IHEP_SCRATCH_ROOT.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must be under {IHEP_SCRATCH_ROOT}; /publicfs is prohibited") from exc
    if relative == Path("."):
        raise ValueError(f"{label} must be a campaign/workspace child of {IHEP_SCRATCH_ROOT}")
    if must_exist and not resolved.is_dir():
        raise FileNotFoundError(f"{label} is not an existing directory: {resolved}")
    return resolved


def _ihep_file(path: Path, label: str) -> Path:
    # Existing readable file (e.g. a CMS VOMS proxy) that must live under the
    # IHEP shared filesystem; path only, never the file contents.
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute under {IHEP_SCRATCH_ROOT}: {path}")
    _safe(str(path), label)
    resolved = path.resolve(strict=False)
    root = IHEP_SCRATCH_ROOT.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must be under {IHEP_SCRATCH_ROOT}; /publicfs is prohibited") from exc
    if not resolved.is_file() or not os.access(resolved, os.R_OK):
        raise ValueError(f"{label} is not a readable regular file under {IHEP_SCRATCH_ROOT}: {resolved}")
    return resolved


def _worker_config(config: Path) -> str:
    # This is a repository-relative argument in documented commands; workers
    # receive the normalized relative path inside the copied runtime bundle.
    resolved = _readable_file(config.resolve(), "--efficiency-config")
    try:
        relative = resolved.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError("--efficiency-config must be a file inside this repository") from exc
    value = _safe(relative.as_posix(), "--efficiency-config")
    if value != _TPS_CONFIG:
        raise ValueError(f"The IHEP campaign requires --efficiency-config {_TPS_CONFIG}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_tar_member(name: str) -> bool:
    # Tar extraction is performed on Linux, but reject both POSIX traversal and
    # backslash spellings so the archive remains safe if it is unpacked by a
    # different platform later.
    if not name or "\x00" in name or "\\" in name:
        return False
    path = Path(name)
    return not path.is_absolute() and name not in (".", "..") and all(
        part not in ("", ".", "..") for part in path.parts
    )


def _validate_runtime(runtime: Path, config: str) -> dict[str, str]:
    """Reject archives that would be unsafe or insufficient at worker runtime."""
    names: set[str] = set()
    config_bytes: bytes | None = None
    try:
        with tarfile.open(runtime, mode="r:gz") as archive:
            for member in archive.getmembers():
                if not _safe_tar_member(member.name):
                    raise ValueError(f"Runtime tarball has an absolute or traversal member: {member.name!r}")
                if member.issym() or member.islnk():
                    raise ValueError(f"Runtime tarball contains a link member: {member.name!r}")
                if not (member.isfile() or member.isdir()):
                    raise ValueError(f"Runtime tarball contains an unsupported member type: {member.name!r}")
                names.add(member.name)
                if member.name == config:
                    extracted = archive.extractfile(member)
                    config_bytes = extracted.read() if extracted is not None else None
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise ValueError(f"--runtime-tarball must be a readable safe tar.gz: {exc}") from exc
    missing = sorted(_RUNTIME_MEMBERS - names)
    if missing:
        raise ValueError(f"Runtime tarball lacks required worker entry points: {', '.join(missing)}")
    if config_bytes != (REPO_ROOT / config).read_bytes():
        raise ValueError("Runtime tarball TPS YAML is not byte-identical to the selected strict config")
    return {
        "path": str(runtime),
        "sha256": _sha256(runtime),
        "yaml_sha256": _sha256_bytes(config_bytes),
        "size": str(runtime.stat().st_size),
    }


def _read_manifest(path: Path, sample: str, index: str, master_manifest_id: str) -> tuple[int, int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid shard manifest {path}: {exc}") from exc
    if payload.get("sample") != sample:
        raise ValueError(f"Shard manifest sample mismatch for {path}: expected {sample}")
    if str(payload.get("shard_index")) != index:
        raise ValueError(f"Shard manifest index mismatch for {path}: expected {index}")
    n_shards = payload.get("n_shards")
    n_files = payload.get("n_files")
    files = payload.get("files")
    if not isinstance(n_shards, int) or isinstance(n_shards, bool) or n_shards <= 0:
        raise ValueError(f"Shard manifest has invalid n_shards: {path}")
    if not isinstance(files, list) or not files:
        raise ValueError(f"Shard manifest has no declared files: {path}")
    if not isinstance(n_files, int) or isinstance(n_files, bool) or n_files <= 0 or n_files != len(files):
        raise ValueError(f"Shard manifest n_files does not match its files list: {path}")
    if any(not isinstance(item, str) or not item.startswith(CCEOS_PREFIX) for item in files):
        raise ValueError(f"Shard manifest does not contain triple-slash direct CCEOS URLs: {path}")
    if payload.get("master_manifest_id") != master_manifest_id:
        raise ValueError(f"Shard manifest master_manifest_id mismatch for {path}")
    return n_shards, n_files


def _load_queue(
    queue: Path, sample: str, master_manifest_id: str, formal_n_files: int
) -> list[tuple[int, Path]]:
    entries: list[tuple[int, Path, int]] = []
    declared_files = 0
    for line in queue.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split(None, 2)
        if len(fields) != 3:
            raise ValueError(f"Malformed queue row: {line!r}")
        row_sample, raw_index, raw_manifest = fields
        if row_sample != sample:
            continue
        if not raw_index.isdigit():
            raise ValueError(f"Shard index must be numeric: {raw_index!r}")
        manifest = _readable_file(Path(raw_manifest).resolve(), "shard manifest")
        if not _SAFE_NAME.fullmatch(manifest.name):
            raise ValueError(f"Shard manifest basename is unsafe: {manifest.name!r}")
        count, n_files = _read_manifest(manifest, sample, raw_index, master_manifest_id)
        declared_files += n_files
        entries.append((int(raw_index), manifest, count))
    if not entries:
        raise RuntimeError(f"No shard entries found for {sample} in {queue}")
    indices = [entry[0] for entry in entries]
    if len(indices) != len(set(indices)):
        raise ValueError(f"Duplicate shard index in queue for {sample}")
    counts = {entry[2] for entry in entries}
    if len(counts) != 1:
        raise ValueError(f"Shard manifests disagree about n_shards for {sample}")
    expected = counts.pop()
    if sorted(indices) != list(range(expected)):
        raise ValueError(f"Shard manifests do not provide complete 0..{expected - 1} coverage for {sample}")
    if declared_files != formal_n_files:
        raise ValueError(
            f"Shard manifests declare {declared_files} files but formal manifest declares {formal_n_files}"
        )
    basenames = [entry[1].name for entry in entries]
    if len(basenames) != len(set(basenames)):
        raise ValueError("Shard manifest basenames must be unique")
    return [(index, manifest) for index, manifest, _ in sorted(entries)]


def _formal_manifest(path: Path, sample: str) -> tuple[Path, str, int]:
    manifest = _readable_file(path, "--formal-manifest")
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid formal manifest {manifest}: {exc}") from exc
    files = payload.get("files")
    n_files = payload.get("n_files")
    master_manifest_id = payload.get("master_manifest_id")
    if payload.get("sample") != sample or not isinstance(files, list) or not files:
        raise ValueError("--formal-manifest must identify the selected sample and declare files")
    if not isinstance(n_files, int) or isinstance(n_files, bool) or n_files <= 0 or n_files != len(files):
        raise ValueError("--formal-manifest n_files does not match its files list")
    if not isinstance(master_manifest_id, str) or not master_manifest_id:
        raise ValueError("--formal-manifest must declare master_manifest_id")
    if any(not isinstance(item, str) or not item.startswith(CCEOS_PREFIX) for item in files):
        raise ValueError("--formal-manifest must contain triple-slash direct CCEOS URLs")
    return manifest, master_manifest_id, n_files


def _copy(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite workspace artifact: {destination}")
    shutil.copy2(source, destination)


def _write(path: Path, contents: str, *, executable: bool = False) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite workspace artifact: {path}")
    path.write_text(contents, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def _shard_submitter(sample: str, workspace: Path, count: int, submission_retries: int) -> str:
    return f'''#!/bin/bash
set -euo pipefail
# Generated only. This retries ``hep_sub`` submission/acceptance, not a failed
# worker execution; inspect the persistent job logs and use plan_missing_shards.sh
# to produce a manual missing-only recovery plan after jobs have finished.
export PATH=/cvmfs/common.ihep.ac.cn/software/hepjob/bin:$PATH
RUN_SCRIPT="{workspace}/scripts/run_shards_{sample}.sh"
LOG_DIR="{workspace}/logs/shards/{sample}"
mkdir -p "$LOG_DIR"
for idx in $(seq 0 {count - 1}); do
    ok=false
    for attempt in $(seq 1 {submission_retries + 1}); do
        if hep_sub "$RUN_SCRIPT" -g cms -gwn CMS -wt mid -argu "$idx" -n 1 \\
            -o "$LOG_DIR/shard_${{idx}}_attempt_${{attempt}}.out" \\
            -e "$LOG_DIR/shard_${{idx}}_attempt_${{attempt}}.err"; then
            ok=true
            break
        fi
    done
    $ok || {{ echo "HepJob submission was not accepted after bounded submission retries: shard=$idx" >&2; exit 1; }}
done
echo "Submitted $(( {count} )) shard HepJobs; do not run merge until verified shard promotion is complete."
'''


def _merge_submitter(sample: str, workspace: Path, campaign_root: Path, count: int) -> str:
    return f'''#!/bin/bash
set -euo pipefail
# MERGE is the sole dependent node: require every promoted shard first.
export PATH=/cvmfs/common.ihep.ac.cn/software/hepjob/bin:$PATH
for idx in $(seq 0 {count - 1}); do
    tag=$(printf 'shard_%04d' "$idx")
    test -f "{campaign_root}/shards/{sample}/${{tag}}/.ready" || {{ echo "Missing shard readiness: $tag" >&2; exit 2; }}
done
mkdir -p "{workspace}/logs/merge/{sample}"
hep_sub "{workspace}/scripts/run_merge_{sample}.sh" -g cms -gwn CMS -wt mid -argu 0 -n 1 \\
    -o "{workspace}/logs/merge/{sample}/merge_0.out" \\
    -e "{workspace}/logs/merge/{sample}/merge_0.err"
'''


def _validate(*, sample: str, queue_file: Path, formal_manifest: Path, ihep_campaign_root: Path,
              runtime_tarball: str, proxy_path: str | None, workspace_dir: Path, tree_path: str,
              efficiency_config: str | None, config_policy: str | None, efficiency_backend: str,
              remote_access_mode: str, skip_plots: bool, submission_retries: int) -> tuple[Path, Path, Path, str, str, int, dict[str, str], Path]:
    if not _SAFE_SAMPLE.fullmatch(sample):
        raise ValueError("--sample must contain only letters, digits, and underscores")
    if tree_path != "auto":
        raise ValueError("The IHEP campaign requires --tree-path auto")
    if config_policy != "strict":
        raise ValueError("The IHEP campaign requires --config-policy strict")
    if not efficiency_config:
        raise ValueError("The IHEP campaign requires an explicit --efficiency-config")
    if efficiency_backend != "vectorized":
        raise ValueError("The IHEP campaign requires --efficiency-backend vectorized")
    if remote_access_mode != "direct":
        raise ValueError("The IHEP campaign requires --remote-access-mode direct")
    if not skip_plots:
        raise ValueError("The IHEP campaign requires --skip-plots")
    if not proxy_path:
        raise ValueError("The IHEP campaign requires --proxy-path")
    if not 0 <= submission_retries <= _MAX_SUBMISSION_RETRIES:
        raise ValueError(f"--submission-retries must be between 0 and {_MAX_SUBMISSION_RETRIES}")
    queue = _readable_file(queue_file, "--queue-file")
    formal, master_manifest_id, formal_n_files = _formal_manifest(formal_manifest, sample)
    runtime = _readable_file(Path(runtime_tarball), "--runtime-tarball")
    proxy = _ihep_file(Path(proxy_path), "--proxy-path")
    root = _ihep_path(ihep_campaign_root, "--ihep-campaign-root", must_exist=True)
    workspace = _ihep_path(workspace_dir, "--workspace-dir", must_exist=False)
    if workspace.exists():
        raise FileExistsError(f"Refusing to reuse existing IHEP HepJob workspace: {workspace}")
    if (root / sample).exists() or (root / f"_merge_{sample}").exists() or (root / "shards" / sample).exists():
        raise FileExistsError(f"Refusing to reuse existing final, merge, or shard root for {sample}")
    config = _worker_config(Path(efficiency_config))
    runtime_info = _validate_runtime(runtime, config)
    return queue, formal, runtime, config, master_manifest_id, formal_n_files, runtime_info, proxy


def build_workspace(sample: str, queue_file: Path, formal_manifest: Path, ihep_campaign_root: Path,
                    runtime_tarball: str, workspace_dir: Path, *, tree_path: str = "auto",
                    efficiency_config: str | None = None, config_policy: str | None = None,
                    efficiency_backend: str = "vectorized", remote_access_mode: str = "direct",
                    skip_plots: bool = True, submission_retries: int = 2,
                    proxy_path: str | None = None) -> Path:
    """Build a fresh static HepJob workspace and return ``workflow.json``; never submit."""
    queue, formal, runtime, config, master_manifest_id, formal_n_files, runtime_info, proxy = _validate(
        sample=sample, queue_file=queue_file, formal_manifest=formal_manifest,
        ihep_campaign_root=ihep_campaign_root, runtime_tarball=runtime_tarball,
        proxy_path=proxy_path, workspace_dir=workspace_dir, tree_path=tree_path,
        efficiency_config=efficiency_config, config_policy=config_policy,
        efficiency_backend=efficiency_backend, remote_access_mode=remote_access_mode,
        skip_plots=skip_plots, submission_retries=submission_retries,
    )
    shards = _load_queue(queue, sample, master_manifest_id, formal_n_files)
    root = ihep_campaign_root.resolve()
    workspace = workspace_dir.resolve()
    workspace.parent.mkdir(parents=True, exist_ok=True)
    workspace.mkdir()
    for directory in ("bundles", "manifests/shards", f"tasks/{sample}", "scripts", "logs"):
        (workspace / directory).mkdir(parents=True, exist_ok=False)
    _copy(runtime, workspace / "bundles/runtime.tar.gz")
    _copy(formal, workspace / "manifests/formal_manifest.json")
    _copy(REPO_ROOT / "condor/run_ihep_efficiency_shard.sh", workspace / "scripts/run_ihep_efficiency_shard.sh")
    _copy(REPO_ROOT / "condor/run_ihep_efficiency_merge_only.sh", workspace / "scripts/run_ihep_efficiency_merge_only.sh")
    for worker in (workspace / "scripts/run_ihep_efficiency_shard.sh", workspace / "scripts/run_ihep_efficiency_merge_only.sh"):
        worker.chmod(0o755)
    tasks = []
    for index, source_manifest in shards:
        copied = workspace / "manifests/shards" / source_manifest.name
        _copy(source_manifest, copied)
        tasks.append({"index": index, "manifest": str(copied), "sample": sample,
                      "campaign_root": str(root), "runtime_tarball": str(workspace / "bundles/runtime.tar.gz"),
                      "efficiency_config": config, "proxy_path": str(proxy)})
    task_path = workspace / f"tasks/{sample}/shard_tasks.json"
    _write(task_path, json.dumps({"schema_version": 1, "sample": sample, "tasks": tasks}, indent=2) + "\n")
    merge_task = workspace / f"tasks/{sample}/merge_task.json"
    _write(merge_task, json.dumps({"schema_version": 1, "sample": sample,
                                   "shards_dir": str(root / "shards" / sample),
                                   "merge_parent": str(root / f"_merge_{sample}"),
                                   "final_sample_dir": str(root / sample),
                                   "runtime_tarball": str(workspace / "bundles/runtime.tar.gz"),
                                   "formal_manifest": str(workspace / "manifests/formal_manifest.json"),
                                   "formal_shards_dir": str(workspace / "manifests/shards"),
                                   "shard_count": len(shards),
                                   "proxy_path": str(proxy)}, indent=2) + "\n")
    _write(workspace / f"scripts/run_shards_{sample}.sh", f'''#!/bin/bash
set -euo pipefail
exec "{workspace}/scripts/run_ihep_efficiency_shard.sh" "{task_path}" "${{1:?missing shard index}}"
''', executable=True)
    _write(workspace / f"scripts/run_merge_{sample}.sh", f'''#!/bin/bash
set -euo pipefail
exec "{workspace}/scripts/run_ihep_efficiency_merge_only.sh" "{merge_task}" "${{1:?missing merge index}}"
''', executable=True)
    _write(workspace / "scripts/submit_shards.sh", _shard_submitter(sample, workspace, len(shards), submission_retries), executable=True)
    _write(workspace / "scripts/submit_merge.sh", _merge_submitter(sample, workspace, root, len(shards)), executable=True)
    _write(workspace / "scripts/plan_missing_shards.sh", f'''#!/bin/bash
set -euo pipefail
# Read-only recovery planner: prints missing shard indices only; never submits.
for idx in $(seq 0 {len(shards) - 1}); do
    tag=$(printf 'shard_%04d' "$idx")
    test -f "{root}/shards/{sample}/${{tag}}/.ready" || echo "$idx"
done
''', executable=True)
    workflow = {"schema_version": 1, "site": "IHEP HepJob", "submit_command": "hep_sub",
                "sample": sample, "campaign_root": str(root), "direct_input_prefix": CCEOS_PREFIX,
                "lcg_view": LCG_VIEW, "runtime": runtime_info,
                "formal_manifest": {"master_manifest_id": master_manifest_id, "n_files": formal_n_files},
                "hepjob": {"group": "cms", "gwn": "CMS", "walltime": "mid",
                                                    "submission_retries": submission_retries,
                                                    "execution_retry": "manual missing-only recovery only"},
                "nodes": [{"name": f"SHARD_{index:04d}", "task_index": index} for index, _ in shards] +
                         [{"name": "MERGE", "parents": [f"SHARD_{index:04d}" for index, _ in shards], "merge_only": True}]}
    workflow_path = workspace / "workflow.json"
    _write(workflow_path, json.dumps(workflow, indent=2) + "\n")
    _write(workspace / "README.generated.md", "# IHEP HepJob efficiency workspace\n\n"
           "Generated only: no HepJob was submitted. Use the static workflow.json to inspect the SHARD -> MERGE topology. "
           "`scripts/submit_merge.sh` is gated on every promoted shard-ready marker and only runs merge-only work. "
           "`scripts/plan_missing_shards.sh` only lists missing shards; it never submits or retries jobs.\n")
    return workflow_path


def build_dag(*args: object, **kwargs: object) -> Path:
    """Compatibility name: the returned artifact is a HepJob workflow, not a CERN DAGMan file."""
    return build_workspace(*args, **kwargs)  # type: ignore[arg-type]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate, never submit, an IHEP HepJob efficiency workspace")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--queue-file", required=True, help="Queue from prepare_efficiency_shards.py")
    parser.add_argument("--formal-manifest", required=True, help="Frozen selected-sample manifest used by strict merge")
    parser.add_argument("--ihep-campaign-root", required=True, help=f"Existing absolute campaign root under {IHEP_SCRATCH_ROOT}")
    parser.add_argument("--runtime-tarball", required=True)
    parser.add_argument("--proxy-path", required=True, help=f"Absolute readable CMS VOMS proxy file under {IHEP_SCRATCH_ROOT}")
    parser.add_argument("--workspace-dir", required=True, help=f"Fresh absolute workspace under {IHEP_SCRATCH_ROOT}")
    parser.add_argument("--tree-path", default="auto")
    parser.add_argument("--efficiency-config", required=True)
    parser.add_argument("--config-policy", choices=("strict", "legacy"), required=True)
    parser.add_argument("--efficiency-backend", default="vectorized", choices=("vectorized", "python-loop"))
    parser.add_argument("--remote-access-mode", default="direct", choices=("direct", "fallback", "stage"))
    parser.add_argument("--skip-plots", action="store_true", default=True)
    parser.add_argument("--submission-retries", type=int, default=2,
                        help="Bounded retries of hep_sub acceptance only; failed worker jobs require manual missing-only recovery")
    args = parser.parse_args()
    result = build_workspace(sample=args.sample, queue_file=Path(args.queue_file),
                             formal_manifest=Path(args.formal_manifest), ihep_campaign_root=Path(args.ihep_campaign_root),
                             runtime_tarball=args.runtime_tarball, proxy_path=args.proxy_path,
                             workspace_dir=Path(args.workspace_dir), tree_path=args.tree_path,
                             efficiency_config=args.efficiency_config, config_policy=args.config_policy,
                             efficiency_backend=args.efficiency_backend, remote_access_mode=args.remote_access_mode,
                             skip_plots=args.skip_plots, submission_retries=args.submission_retries)
    print(f"Wrote IHEP HepJob workspace: {result.parent}")
    print(f"Wrote static workflow (not submitted): {result}")


if __name__ == "__main__":
    main()

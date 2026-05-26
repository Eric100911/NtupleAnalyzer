#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_SAMPLE_ROOT = "/eos/ihep/cms/store/user/xcheng/MC_Production_v3/output"
DEFAULT_XROOTD_HOST = "root://cceos.ihep.ac.cn:1094//"
DEFAULT_SAMPLES = ("JJP_DPS1", "JJP_DPS2_CS", "JJP_DPS2_G", "JJP_SPS_CS", "JJP_SPS_G")


def write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def parse_csv(raw: str) -> tuple[str, ...]:
    if raw.lower() == "all":
        return DEFAULT_SAMPLES
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def xrootd_url(host: str, path: str) -> str:
    return f"{host.rstrip('/')}//{path}"


def natural_key(text: str) -> tuple[Any, ...]:
    name = text.rstrip("/").rsplit("/", 1)[-1]
    return (0, int(name)) if name.isdigit() else (1, name)


def list_with_gfal(url: str) -> list[str]:
    env = os.environ.copy()
    if os.path.exists("/usr/bin/python3"):
        env.setdefault("GFAL_PYTHONBIN", "/usr/bin/python3")
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        env.pop("LD_LIBRARY_PATH", None)
    completed = subprocess.run(["gfal-ls", url], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def list_with_xrdfs(host: str, path: str) -> list[str]:
    completed = subprocess.run(["xrdfs", host, "ls", path], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return [line.strip().rstrip("/").rsplit("/", 1)[-1] for line in completed.stdout.splitlines() if line.strip()]


def discover_sample_files(sample: str, host: str, sample_root: str, max_files: int | None) -> list[str]:
    sample_path = f"{sample_root.rstrip('/')}/{sample}"
    try:
        entries = list_with_gfal(xrootd_url(host, sample_path))
    except Exception:
        entries = list_with_xrdfs(host, sample_path)
    job_dirs = sorted((entry.rstrip("/").rsplit("/", 1)[-1] for entry in entries if entry.rstrip("/").rsplit("/", 1)[-1].isdigit()), key=natural_key)
    files = [xrootd_url(host, f"{sample_path}/{job_dir}/output_ntuple.root") for job_dir in job_dirs]
    return files[:max_files] if max_files is not None and max_files > 0 else files


def load_files_by_sample(args: argparse.Namespace, samples: tuple[str, ...]) -> dict[str, list[str]]:
    if args.input_file_manifest:
        payload = read_json(Path(args.input_file_manifest))
        if isinstance(payload, dict) and isinstance(payload.get("sample"), str) and isinstance(payload.get("files"), list):
            payload = {payload["sample"]: payload["files"]}
        return {sample: list(payload[sample])[: args.max_files if args.max_files and args.max_files > 0 else None] for sample in samples}
    return {sample: discover_sample_files(sample, args.xrootd_host, args.sample_root, args.max_files) for sample in samples}


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare JJP efficiency Condor shard manifests")
    parser.add_argument("--samples", default=",".join(DEFAULT_SAMPLES), help="Comma-separated samples or all")
    parser.add_argument("--input-file-manifest", default=None, help="Optional manifest mapping sample names to file URLs")
    parser.add_argument("--xrootd-host", default=DEFAULT_XROOTD_HOST)
    parser.add_argument("--sample-root", default=DEFAULT_SAMPLE_ROOT)
    parser.add_argument("--max-files", type=int, default=-1)
    parser.add_argument("--files-per-job", type=int, default=10)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    if args.files_per_job <= 0:
        raise ValueError("--files-per-job must be positive")

    samples = parse_csv(args.samples)
    files_by_sample = load_files_by_sample(args, samples)
    manifest_root = Path(args.output_dir) / "manifests"
    queue_rows: list[str] = []

    for sample, files in files_by_sample.items():
        if not files:
            raise RuntimeError(f"No files discovered for {sample}")
        sample_manifest_dir = manifest_root / sample
        write_json({"sample": sample, "n_files": len(files), "files": files}, sample_manifest_dir / "files.json")
        shard_dir = sample_manifest_dir / "shards"
        n_shards = (len(files) + args.files_per_job - 1) // args.files_per_job
        for shard_index, start in enumerate(range(0, len(files), args.files_per_job)):
            shard_files = files[start : start + args.files_per_job]
            shard_path = shard_dir / f"shard_{shard_index:04d}.json"
            write_json(
                {
                    "sample": sample,
                    "shard_index": shard_index,
                    "n_shards": n_shards,
                    "files": shard_files,
                },
                shard_path,
            )
            queue_rows.append(f"{sample} {shard_index} {shard_path}\n")

    queue_file = manifest_root / "jjp_efficiency_queue.txt"
    queue_file.write_text("".join(queue_rows))
    print(queue_file)


if __name__ == "__main__":
    main()

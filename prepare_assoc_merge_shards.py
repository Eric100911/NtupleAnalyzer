#!/usr/bin/env python3
"""Prepare file-list manifests for sharded assocPV merge jobs."""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Sequence


OUTPUT_BASE = "/eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV"
DEFAULT_PROXY = "/afs/cern.ch/user/c/chiw/condor/x509up"

DATA_PATHS = {
    "JJP": "/eos/user/c/chiw/JpsiJpsiPhi/rootNtuple",
    "JYP": "/eos/user/c/chiw/JpsiUpsPhi/rootNtuple",
    "JJY": "/eos/user/c/chiw/JpsiJpsiUps/rootNtuple",
}

JJP_DATASET_DIRS = tuple(f"ParkingDoubleMuonLowMass{i}" for i in range(8))
JYP_DATASET_DIRS = tuple(f"ParkingDoubleMuonLowMass{i}" for i in range(8))
JJY_DATASET_DIRS = tuple(f"ParkingDoubleMuonLowMass{i}" for i in range(8))

MC_BASE = "/eos/ihep/cms/store/user/xcheng/MC_Production_v3/output"
JJY_MC_BASE = "/eos/user/c/chiw/JpsiJpsiUps/MC_samples/rootNtuple_refactor"
MC_SAMPLE_PATHS = {
    "JJP": {
        "DPS_1": os.path.join(MC_BASE, "JJP_DPS1"),
        "DPS_2_CS": os.path.join(MC_BASE, "JJP_DPS2_CS"),
        "DPS_2_G": os.path.join(MC_BASE, "JJP_DPS2_G"),
        "SPS_CS": os.path.join(MC_BASE, "JJP_SPS_CS"),
        "SPS_G": os.path.join(MC_BASE, "JJP_SPS_G"),
        "TPS": os.path.join(MC_BASE, "JJP_TPS"),
    },
    "JYP": {
        "SPS": os.path.join(MC_BASE, "JUP_SPS"),
        "DPS_1": os.path.join(MC_BASE, "JUP_DPS1"),
        "DPS_2": os.path.join(MC_BASE, "JUP_DPS2"),
        "DPS_3": os.path.join(MC_BASE, "JUP_DPS3"),
        "TPS": os.path.join(MC_BASE, "JUP_TPS"),
    },
    "JJY": {
        "DPS_1": os.path.join(JJY_MC_BASE, "DPS-Jpsi-JpsiY/filter_JpsiPtMin4p0_YPtMin6p0"),
        "DPS_2": os.path.join(JJY_MC_BASE, "DPS-JpsiJpsi-Y/filter_JpsiPtMin4p0_YPtMin6p0"),
    },
}


def normalize_channel(channel: str) -> str:
    channel_up = channel.upper()
    if channel_up not in DATA_PATHS:
        raise ValueError(f"Unsupported channel: {channel}")
    return channel_up


def normalize_dataset(dataset: str) -> str:
    dataset_low = dataset.lower()
    if dataset_low not in {"data", "mc"}:
        raise ValueError(f"Unsupported dataset: {dataset}")
    return dataset_low


def normalize_sample(channel: str, sample: str | None) -> str | None:
    if sample is None:
        return None
    sample_up = sample.upper()
    aliases = {
        "DPS1": "DPS_1",
        "DPS2": "DPS_2",
        "DPS3": "DPS_3",
        "DPS2_CS": "DPS_2_CS",
        "DPS2_G": "DPS_2_G",
        "SPSCS": "SPS_CS",
        "SPSG": "SPS_G",
    }
    sample_up = aliases.get(sample_up, sample_up)
    if sample_up not in MC_SAMPLE_PATHS[channel]:
        raise ValueError(f"Unsupported sample for {channel}: {sample}")
    return sample_up


def default_input_dir(channel: str, dataset: str, sample: str | None = None) -> str:
    if dataset == "data":
        return DATA_PATHS[channel]
    if sample is None:
        raise ValueError("MC input requires --sample")
    return MC_SAMPLE_PATHS[channel][sample]


def make_tag(channel: str, dataset: str, sample: str | None = None) -> str:
    base = f"{channel.lower()}_{dataset}"
    if dataset == "mc" and sample:
        base = f"{base}_{sample.lower()}"
    return base


def default_merged_output(channel: str, dataset: str, sample: str | None, output_base: str) -> str:
    return os.path.join(output_base, "merged", f"{make_tag(channel, dataset, sample)}_selected.root")


def to_xrootd_if_needed(path: str) -> str:
    if path.startswith("root://"):
        return path
    if path.startswith("/eos/ihep/"):
        return f"root://cceos.ihep.ac.cn//{path.lstrip('/')}"
    return path


def discover_refactor_data_files(
    input_path: str,
    dataset_dirs: Sequence[str],
    task_prefix: str,
    submit_prefix: str,
) -> list[str]:
    files: list[str] = []
    for dataset_dir in dataset_dirs:
        base_dir = os.path.join(input_path, dataset_dir)
        if not os.path.isdir(base_dir):
            continue
        for task_dir in sorted(glob.glob(os.path.join(base_dir, f"{task_prefix}*"))):
            if not os.path.isdir(task_dir):
                continue
            hadd_files = sorted(glob.glob(os.path.join(task_dir, "*haddNtuple*.root")))
            if hadd_files:
                files.extend(hadd_files)
                continue
            for submit_dir in sorted(glob.glob(os.path.join(task_dir, f"{submit_prefix}*"))):
                if os.path.isdir(submit_dir):
                    files.extend(sorted(glob.glob(os.path.join(submit_dir, "**", "*.root"), recursive=True)))
    return files


def discover_root_files(input_path: str, max_files: int = -1) -> list[str]:
    resolved = to_xrootd_if_needed(input_path)
    if resolved.endswith(".root"):
        files = [resolved]
    elif resolved.startswith("root://"):
        stripped = resolved[len("root://") :]
        host, remote_path = stripped.split("/", 1)
        remote_path = "/" + remote_path
        env = os.environ.copy()
        if "X509_USER_PROXY" not in env and os.path.exists(DEFAULT_PROXY):
            env["X509_USER_PROXY"] = DEFAULT_PROXY
        result = subprocess.run(["xrdfs", host, "ls", "-R", remote_path], capture_output=True, text=True, check=True, env=env)
        files = [f"root://{host}{line.strip()}" for line in result.stdout.splitlines() if line.strip().endswith("output_ntuple.root")]
        if not files:
            files = [f"root://{host}{line.strip()}" for line in result.stdout.splitlines() if line.strip().endswith(".root")]
    else:
        files = discover_refactor_data_files(resolved, JJP_DATASET_DIRS, "crab3_refactor", "260411")
        if not files:
            files = discover_refactor_data_files(resolved, JYP_DATASET_DIRS, "crab3_JpsiUpsPhi_refactor", "2604")
        if not files:
            files = discover_refactor_data_files(resolved, JJY_DATASET_DIRS, "crab3_refactor_JpsiJpsiUps", "2604")
        if not files:
            files = sorted(glob.glob(os.path.join(resolved, "*.root")))
        if not files:
            files = sorted(glob.glob(os.path.join(resolved, "**", "*.root"), recursive=True))
    if max_files > 0:
        files = files[:max_files]
    if not files:
        raise FileNotFoundError(f"No ROOT files found under {input_path}")
    return files


def write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_input_manifest(path: str) -> list[str]:
    payload = read_json(Path(path))
    if isinstance(payload, dict):
        files = payload.get("files")
    elif isinstance(payload, list):
        files = payload
    else:
        files = None
    if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
        raise ValueError(f"Input manifest must contain a list of files: {path}")
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare assocPV merge Condor shard manifests")
    parser.add_argument("--channel", required=True, choices=["JJP", "JYP", "JJY", "jjp", "jyp", "jjy"])
    parser.add_argument("--dataset", default="data", choices=["data", "mc"])
    parser.add_argument("--sample", default=None)
    parser.add_argument("--input-dir", default=None)
    parser.add_argument("--input-file-manifest", default=None)
    parser.add_argument("--output", default=None, help="Final merged selected ROOT output")
    parser.add_argument("--output-base", default=OUTPUT_BASE)
    parser.add_argument("--max-files", type=int, default=-1)
    parser.add_argument("--files-per-job", type=int, required=True)
    args = parser.parse_args()

    if args.files_per_job <= 0:
        raise ValueError("--files-per-job must be positive")

    channel = normalize_channel(args.channel)
    dataset = normalize_dataset(args.dataset)
    sample = normalize_sample(channel, args.sample) if dataset == "mc" else None
    if args.input_file_manifest:
        input_dir = args.input_dir or args.input_file_manifest
    else:
        input_dir = args.input_dir or default_input_dir(channel, dataset, sample)
    tag = make_tag(channel, dataset, sample)
    final_output = args.output or default_merged_output(channel, dataset, sample, args.output_base)

    if args.input_file_manifest:
        files = load_input_manifest(args.input_file_manifest)
        if args.max_files > 0:
            files = files[: args.max_files]
    else:
        files = discover_root_files(input_dir, args.max_files)
    if not files:
        raise RuntimeError(f"No ROOT files found for {tag}")

    output_base = Path(args.output_base)
    manifest_dir = output_base / "merged" / "manifests" / tag
    shard_output_dir = output_base / "merged" / "shards" / tag
    manifest_dir.mkdir(parents=True, exist_ok=True)
    shard_output_dir.mkdir(parents=True, exist_ok=True)

    write_json(
        {
            "channel": channel,
            "dataset": dataset,
            "sample": sample,
            "tag": tag,
            "input_dir": input_dir,
            "n_files": len(files),
            "files": files,
        },
        manifest_dir / "files.json",
    )

    queue_rows: list[str] = []
    shard_outputs: list[str] = []
    n_shards = (len(files) + args.files_per_job - 1) // args.files_per_job
    shard_manifest_dir = manifest_dir / "shards"
    for shard_index, start in enumerate(range(0, len(files), args.files_per_job)):
        shard_files = files[start : start + args.files_per_job]
        shard_path = shard_manifest_dir / f"shard_{shard_index:04d}.json"
        shard_output = shard_output_dir / f"shard_{shard_index:04d}_selected.root"
        write_json(
            {
                "channel": channel,
                "dataset": dataset,
                "sample": sample,
                "tag": tag,
                "shard_index": shard_index,
                "n_shards": n_shards,
                "files": shard_files,
                "output": str(shard_output),
            },
            shard_path,
        )
        shard_outputs.append(str(shard_output))
        queue_rows.append(f"{tag} {shard_index} {shard_path} {shard_output}\n")

    merge_plan = {
        "channel": channel,
        "dataset": dataset,
        "sample": sample,
        "tag": tag,
        "n_files": len(files),
        "n_shards": n_shards,
        "final_output": final_output,
        "shard_outputs": shard_outputs,
    }
    write_json(merge_plan, manifest_dir / "merge_plan.json")

    queue_file = manifest_dir / "assoc_merge_queue.txt"
    queue_file.write_text("".join(queue_rows), encoding="utf-8")
    print(queue_file)


if __name__ == "__main__":
    main()

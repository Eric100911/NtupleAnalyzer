#!/usr/bin/env python3
"""Merge selected ROOT shard outputs from the sharded assocPV merge workflow."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

import ROOT

from merge_apply_cuts import OUTPUT_TREE
from ntuple_pipeline_common import ensure_parent_dir


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_selected_tree(path: str) -> None:
    root_file = ROOT.TFile.Open(path)
    if not root_file or root_file.IsZombie():
        raise RuntimeError(f"Failed to open shard output: {path}")
    tree = root_file.Get(OUTPUT_TREE)
    if tree is None:
        root_file.Close()
        raise RuntimeError(f"Shard output is missing tree {OUTPUT_TREE}: {path}")
    root_file.Close()


def merge_root_files(inputs: list[str], output: str) -> None:
    if not inputs:
        raise RuntimeError("No shard outputs were provided")
    missing = [path for path in inputs if not os.path.exists(path)]
    if missing:
        raise FileNotFoundError("Missing shard output(s): " + ", ".join(missing[:5]))
    for path in inputs:
        validate_selected_tree(path)

    ensure_parent_dir(output)
    tmp_output = f"{output}.tmp"
    if os.path.exists(tmp_output):
        os.remove(tmp_output)

    merger = ROOT.TFileMerger(False, False)
    if not merger.OutputFile(tmp_output, "RECREATE"):
        raise RuntimeError(f"Failed to create temporary output: {tmp_output}")
    for path in inputs:
        if not merger.AddFile(path):
            raise RuntimeError(f"Failed to add shard output: {path}")
    if not merger.Merge():
        raise RuntimeError(f"Failed to merge shard outputs into {tmp_output}")

    shutil.move(tmp_output, output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge assocPV selected ROOT shard outputs")
    parser.add_argument("--merge-plan", required=True, help="JSON merge plan from prepare_assoc_merge_shards.py")
    args = parser.parse_args()

    plan = read_json(Path(args.merge_plan))
    final_output = plan.get("final_output")
    shard_outputs = plan.get("shard_outputs")
    if not isinstance(final_output, str) or not isinstance(shard_outputs, list):
        raise ValueError(f"Invalid merge plan: {args.merge_plan}")
    inputs = [str(path) for path in shard_outputs]
    merge_root_files(inputs, final_output)
    print(f"Wrote merged assocPV selected ROOT output to {final_output}")


if __name__ == "__main__":
    main()

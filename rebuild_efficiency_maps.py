#!/usr/bin/env python3
"""Rebuild efficiency_maps.parquet from existing merged efficiency inputs.

This script is intentionally non-overwriting by default: it reads merged
``gen_systems.parquet`` and ``event_step_flags.parquet`` from an existing
efficiency output tree and writes a fresh, derived-compatible output tree.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Callable

import pandas as pd

from efficiency_workflow.efficiency import (
    CORRELATED_MAP_STEPS,
    CORRELATED_MAP_STEPS_NO_TRIG_MATCH,
    EfficiencyBinning,
    build_cutflow,
    build_efficiency_counts,
    per_object_step_columns,
)
from efficiency_workflow.io import ensure_dir, read_json, write_json, write_parquet


DEFAULT_SAMPLES = ("JJP_DPS1", "JJP_DPS2_CS", "JJP_DPS2_G", "JJP_SPS_CS", "JJP_SPS_G")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild efficiency_maps.parquet into a new output tree from merged gen/event parquet files."
    )
    parser.add_argument("--input-dir", required=True, help="Existing merged efficiency directory")
    parser.add_argument("--output-dir", required=True, help="Fresh output directory; must differ from --input-dir")
    parser.add_argument("--samples", nargs="+", default=list(DEFAULT_SAMPLES), help="Samples to rebuild")
    parser.add_argument(
        "--skip-trigger-matching",
        action="store_true",
        help="Use the no-trigger-matching chain (_noTrigMatch columns)",
    )
    parser.add_argument(
        "--copy-existing-derived",
        action="store_true",
        help="Copy existing derived/ directories for reference. New derived products should still be rebuilt.",
    )
    return parser.parse_args()


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except FileNotFoundError:
        return left.absolute() == right.absolute()


def _copy_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if dst.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {dst}")
    ensure_dir(dst.parent)
    shutil.copy2(src, dst)


def _copy_tree_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if dst.exists():
        raise FileExistsError(f"Refusing to overwrite existing directory: {dst}")
    shutil.copytree(src, dst)


def _sample_artifacts(sample_dir: Path, counts_df: pd.DataFrame, gen_df: pd.DataFrame, event_df: pd.DataFrame) -> dict:
    artifacts = {
        "gen_systems": {"path": "gen_systems.parquet", "n_rows": int(len(gen_df))},
        "event_step_flags": {"path": "event_step_flags.parquet", "n_rows": int(len(event_df))},
        "efficiency_counts": {"path": "efficiency_counts.parquet", "n_rows": int(len(counts_df))},
        "efficiency_maps": {"path": "efficiency_maps.parquet", "n_rows": int(len(counts_df))},
    }
    if (sample_dir / "sample_manifest.json").exists():
        artifacts["sample_manifest"] = "sample_manifest.json"
    if (sample_dir / "cutflow.csv").exists():
        artifacts["cutflow"] = {"path": "cutflow.csv"}
    return artifacts


def _validate_event_schema(event_df: pd.DataFrame, binning: EfficiencyBinning, sample_dir: Path) -> None:
    required = set(per_object_step_columns())
    required.add("s_cand")
    required.update(CORRELATED_MAP_STEPS if binning.include_trigger_matching else CORRELATED_MAP_STEPS_NO_TRIG_MATCH)
    missing = sorted(required - set(event_df.columns))
    if missing:
        raise RuntimeError(
            f"{sample_dir / 'event_step_flags.parquet'} is not compatible with the current efficiency schema. "
            f"Missing columns: {', '.join(missing)}"
        )


def rebuild_efficiency_maps_for_sample(
    input_sample_dir: Path,
    output_sample_dir: Path,
    binning: EfficiencyBinning,
    *,
    copy_existing_derived: bool = False,
    status_callback: Callable[[str], None] | None = None,
) -> Path:
    """Read gen/event parquet files, rebuild counts, and write a new sample bundle."""
    def status(message: str) -> None:
        if status_callback is not None:
            status_callback(message)

    gen_path = input_sample_dir / "gen_systems.parquet"
    event_path = input_sample_dir / "event_step_flags.parquet"
    if not gen_path.exists() or not event_path.exists():
        raise FileNotFoundError(f"Missing gen/event parquet inputs in {input_sample_dir}")
    if output_sample_dir.exists():
        existing_outputs = [
            output_sample_dir / "efficiency_maps.parquet",
            output_sample_dir / "efficiency_counts.parquet",
        ]
        for path in existing_outputs:
            if path.exists():
                raise FileExistsError(f"Refusing to overwrite existing rebuilt output: {path}")

    ensure_dir(output_sample_dir)
    status(f"reading gen/event parquet from {input_sample_dir}")
    gen_df = pd.read_parquet(gen_path)
    event_df = pd.read_parquet(event_path)
    status(f"loaded {len(gen_df)} gen rows and {len(event_df)} event rows")
    _validate_event_schema(event_df, binning, input_sample_dir)
    status("schema validation passed; rebuilding counts")
    counts_df = build_efficiency_counts(gen_df, event_df, binning)
    cutflow_df = build_cutflow(event_df, binning)
    status(f"rebuilt {len(counts_df)} efficiency rows and {len(cutflow_df)} cutflow rows")

    status(f"copying source parquet inputs to {output_sample_dir}")
    _copy_if_exists(gen_path, output_sample_dir / "gen_systems.parquet")
    _copy_if_exists(event_path, output_sample_dir / "event_step_flags.parquet")
    _copy_if_exists(input_sample_dir / "sample_manifest.json", output_sample_dir / "sample_manifest.json")
    if input_sample_dir / "cutflow.csv" != output_sample_dir / "cutflow.csv":
        cutflow_df.to_csv(output_sample_dir / "cutflow.csv", index=False)
    if copy_existing_derived:
        status("copying existing derived/ directory for reference")
        _copy_tree_if_exists(input_sample_dir / "derived", output_sample_dir / "derived")

    status("writing rebuilt efficiency_counts.parquet and efficiency_maps.parquet")
    write_parquet(counts_df, output_sample_dir / "efficiency_counts.parquet")
    write_parquet(counts_df, output_sample_dir / "efficiency_maps.parquet")

    manifest = {
        "stage": "efficiency_rebuild",
        "sample": output_sample_dir.name,
        "source": str(input_sample_dir.resolve()),
        "artifacts": _sample_artifacts(output_sample_dir, counts_df, gen_df, event_df),
    }
    write_json(manifest, output_sample_dir / "manifest.json")
    status(f"wrote manifest: {output_sample_dir / 'manifest.json'}")
    return output_sample_dir / "efficiency_maps.parquet"


def write_top_manifest(input_dir: Path, output_dir: Path, samples: list[str]) -> None:
    source_manifest = input_dir / "manifest.json"
    payload = {
        "stage": "efficiency_rebuild_summary",
        "source": str(input_dir.resolve()),
        "artifacts": {
            "samples": {sample: f"{sample}/manifest.json" for sample in samples},
        },
    }
    if source_manifest.exists():
        payload["source_manifest"] = read_json(source_manifest)
    write_json(payload, output_dir / "manifest.json")


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    if _same_path(input_dir, output_dir):
        raise ValueError("--output-dir must differ from --input-dir; this script does not overwrite source maps")
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    ensure_dir(output_dir)
    binning = EfficiencyBinning(include_trigger_matching=not args.skip_trigger_matching)
    samples = list(dict.fromkeys(args.samples))
    print(f"Rebuilding {len(samples)} sample(s)")
    print(f"  input : {input_dir}")
    print(f"  output: {output_dir}")
    for sample in samples:
        print(f"[{sample}] start", flush=True)
        out_path = rebuild_efficiency_maps_for_sample(
            input_dir / sample,
            output_dir / sample,
            binning,
            copy_existing_derived=args.copy_existing_derived,
            status_callback=lambda message, sample=sample: print(f"[{sample}] {message}", flush=True),
        )
        frame = pd.read_parquet(out_path)
        corr_steps = sorted(frame.loc[frame["map_type"] == "correlated_3d", "step"].dropna().unique().tolist())
        print(f"[{sample}] wrote {out_path} ({len(frame)} rows); correlated_3d steps: {', '.join(corr_steps)}")

    write_top_manifest(input_dir, output_dir, samples)
    print(f"Done. Manifest: {output_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

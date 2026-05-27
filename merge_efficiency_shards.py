#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from efficiency_workflow.config import CmsPlotStyleConfig
from efficiency_workflow.efficiency import EfficiencyBinning, build_cutflow, build_efficiency_counts, build_subprocess_envelope
from efficiency_workflow.io import ensure_dir, read_json, write_json, write_parquet


def collect_sample_files(shard_sample_dirs: list[Path]) -> list[str]:
    files: list[str] = []
    for sample_dir in shard_sample_dirs:
        manifest_path = sample_dir / "sample_manifest.json"
        if not manifest_path.exists():
            continue
        payload = read_json(manifest_path)
        files.extend(str(item) for item in payload.get("input_files", []))
    return list(dict.fromkeys(files))


def write_sample_bundle(
    output_dir: Path,
    sample: str,
    input_files: list[str],
    gen_df: pd.DataFrame,
    event_df: pd.DataFrame,
    counts_df: pd.DataFrame,
    cutflow_df: pd.DataFrame,
    skip_plots: bool,
    min_plot_total: int,
) -> dict[str, Any]:
    sample_dir = ensure_dir(output_dir / sample)
    write_json({"sample": sample, "n_input_files": len(input_files), "input_files": input_files}, sample_dir / "sample_manifest.json")
    write_parquet(gen_df, sample_dir / "gen_systems.parquet")
    write_parquet(event_df, sample_dir / "event_step_flags.parquet")
    write_parquet(counts_df, sample_dir / "efficiency_counts.parquet")
    write_parquet(counts_df, sample_dir / "efficiency_maps.parquet")
    cutflow_df.to_csv(sample_dir / "cutflow.csv", index=False)

    artifacts: dict[str, Any] = {
        "sample_manifest": "sample_manifest.json",
        "gen_systems": {"path": "gen_systems.parquet", "n_rows": int(len(gen_df))},
        "event_step_flags": {"path": "event_step_flags.parquet", "n_rows": int(len(event_df))},
        "efficiency_counts": {"path": "efficiency_counts.parquet", "n_rows": int(len(counts_df))},
        "efficiency_maps": {"path": "efficiency_maps.parquet", "n_rows": int(len(counts_df))},
        "cutflow": {"path": "cutflow.csv", "n_rows": int(len(cutflow_df))},
    }
    if not skip_plots:
        from efficiency_workflow.plotting import write_efficiency_plots

        plot_paths = write_efficiency_plots(
            sample_dir / "plots",
            counts_df,
            plot_style_cfg=CmsPlotStyleConfig(is_data=False),
            min_total=min_plot_total,
        )
        artifacts["plots"] = {key: str(path.relative_to(sample_dir)) for key, path in plot_paths.items()}
    write_json({"stage": "efficiency", "sample": sample, "artifacts": artifacts}, sample_dir / "manifest.json")
    return artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge JJP efficiency shard outputs")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--shards-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--min-plot-total", type=int, default=1)
    args = parser.parse_args()

    shards_dir = Path(args.shards_dir)
    output_dir = ensure_dir(Path(args.output_dir))
    sample_dirs = sorted(path / args.sample for path in shards_dir.glob("shard_*") if (path / args.sample).is_dir())
    if not sample_dirs:
        raise RuntimeError(f"No shard outputs found under {shards_dir} for {args.sample}")

    gen_df = pd.concat((pd.read_parquet(path / "gen_systems.parquet") for path in sample_dirs), ignore_index=True)
    event_df = pd.concat((pd.read_parquet(path / "event_step_flags.parquet") for path in sample_dirs), ignore_index=True)
    counts_df = build_efficiency_counts(gen_df, event_df, EfficiencyBinning())
    cutflow_df = build_cutflow(event_df)
    input_files = collect_sample_files(sample_dirs)
    write_sample_bundle(output_dir, args.sample, input_files, gen_df, event_df, counts_df, cutflow_df, args.skip_plots, args.min_plot_total)

    inclusive_final = cutflow_df.loc[cutflow_df["step"] == "Pri_trackPVPass"]
    summary_df = pd.DataFrame(
        [
            {
                "sample": args.sample,
                "n_input_files": len(input_files),
                "n_full_gen": int(event_df["full_gen"].sum()) if not event_df.empty else 0,
                "n_Pri_trackPVPass": int(event_df["Pri_trackPVPass"].sum()) if not event_df.empty else 0,
                "final_efficiency": float(inclusive_final["efficiency"].iloc[0]) if not inclusive_final.empty else float("nan"),
                "final_err_sym": float(inclusive_final["err_sym"].iloc[0]) if not inclusive_final.empty else float("nan"),
            }
        ]
    )
    write_parquet(summary_df, output_dir / "subprocess_summary.parquet")
    summary_df.to_csv(output_dir / "subprocess_summary.csv", index=False)
    write_parquet(build_subprocess_envelope({args.sample: counts_df}), output_dir / "subprocess_envelope.parquet")

    manifest_path = output_dir / "manifest.json"
    existing_samples: dict[str, str] = {}
    if manifest_path.exists():
        existing = read_json(manifest_path)
        existing_samples = existing.get("artifacts", {}).get("samples", {})
    existing_samples[args.sample] = f"{args.sample}/manifest.json"
    write_json(
        {
            "stage": "efficiency_summary",
            "artifacts": {
                "subprocess_summary": "subprocess_summary.parquet",
                "subprocess_envelope": "subprocess_envelope.parquet",
                "samples": existing_samples,
            },
        },
        manifest_path,
    )
    print(f"Wrote merged efficiency outputs to {output_dir}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from efficiency_workflow.config import CmsPlotStyleConfig
from efficiency_workflow.efficiency import (
    EfficiencyBinning,
    build_per_object_acceptance_maps,
    build_stacked_jpsi_acceptance_maps,
    build_stacked_jpsi_efficiency_maps,
)
from efficiency_workflow.io import ensure_dir, read_json, write_json, write_parquet


def _discover_samples(input_dir: Path) -> list[Path]:
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"No manifest.json found in {input_dir}")
    manifest = read_json(manifest_path)
    samples = manifest.get("artifacts", {}).get("samples", {})
    if samples:
        return [input_dir / sample for sample in samples]
    if (input_dir / "efficiency_maps.parquet").exists():
        return [input_dir]
    raise RuntimeError(f"No samples listed in {manifest_path} and no efficiency_maps.parquet found — is this a merge output directory?")


def build_derived_for_sample(
    sample_dir: Path, output_dir: Path, skip_plots: bool = False, min_plot_total: int = 1
) -> dict[str, object]:
    counts_path = sample_dir / "efficiency_maps.parquet"
    if not counts_path.exists():
        raise RuntimeError(f"efficiency_maps.parquet not found in {sample_dir}")

    sample = sample_dir.name
    print(f"\n{'='*60}")
    print(f"[{sample}] Reading efficiency_maps.parquet ...")
    counts_df = pd.read_parquet(counts_path)
    print(f"[{sample}]   {len(counts_df)} rows across {counts_df['map_type'].nunique()} map types")

    derived_dir = ensure_dir(output_dir / sample / "derived")
    poa_df = pd.DataFrame()
    stacked_acc_df = pd.DataFrame()
    stacked_eff_df = pd.DataFrame()
    gen_path = sample_dir / "gen_systems.parquet"
    event_path = sample_dir / "event_step_flags.parquet"
    if gen_path.exists() and event_path.exists():
        print(f"[{sample}] Building per-object and stacked-J/psi maps ...")
        gen_df = pd.read_parquet(gen_path)
        event_df = pd.read_parquet(event_path)
        binning = EfficiencyBinning()
        poa_df = build_per_object_acceptance_maps(gen_df, event_df, binning)
        stacked_acc_df = build_stacked_jpsi_acceptance_maps(gen_df, event_df, binning)
        stacked_eff_df = build_stacked_jpsi_efficiency_maps(gen_df, event_df, binning)
    else:
        print(f"[{sample}] Missing gen_systems.parquet or event_step_flags.parquet; derived object maps skipped")

    print(f"[{sample}] Writing data files to {derived_dir} ...")
    if not poa_df.empty:
        write_parquet(poa_df, derived_dir / "per_object_acceptance_maps.parquet")
        poa_df.to_csv(derived_dir / "per_object_acceptance_maps.csv", index=False)
        print(f"[{sample}]   per-object acceptance rows: {len(poa_df)}")
    else:
        print(f"[{sample}]   per-object acceptance columns not present or no rows — skipped")
    if not stacked_acc_df.empty:
        write_parquet(stacked_acc_df, derived_dir / "stacked_jpsi_acceptance_maps.parquet")
        stacked_acc_df.to_csv(derived_dir / "stacked_jpsi_acceptance_maps.csv", index=False)
        print(f"[{sample}]   stacked J/psi acceptance rows: {len(stacked_acc_df)}")
    if not stacked_eff_df.empty:
        write_parquet(stacked_eff_df, derived_dir / "stacked_jpsi_efficiency_maps.parquet")
        stacked_eff_df.to_csv(derived_dir / "stacked_jpsi_efficiency_maps.csv", index=False)
        print(f"[{sample}]   stacked J/psi efficiency rows: {len(stacked_eff_df)}")

    plots: dict[str, Path] = {}
    poa_plots: dict[str, Path] = {}
    qa_plots: dict[str, Path] = {}
    if not skip_plots:
        from efficiency_workflow.plotting import write_per_object_acceptance_plots, write_stacked_jpsi_plots

        if not poa_df.empty:
            print(f"[{sample}] Generating per-object acceptance plots ...")
            poa_plots = write_per_object_acceptance_plots(
                derived_dir / "plots" / "per_object_acceptance",
                poa_df,
                plot_style_cfg=CmsPlotStyleConfig(is_data=False),
                min_total=min_plot_total,
            )
            print(f"[{sample}]   {len(poa_plots)} plots written")
            qa_plots.update(
                {
                    f"per_object_acceptance_qa.{key}": path
                    for key, path in write_per_object_acceptance_plots(
                        derived_dir / "plots_with_uncertainty" / "per_object_acceptance",
                        poa_df,
                        plot_style_cfg=CmsPlotStyleConfig(is_data=False),
                        min_total=min_plot_total,
                        include_uncertainty=True,
                    ).items()
                }
            )
        if not stacked_acc_df.empty or not stacked_eff_df.empty:
            print(f"[{sample}] Generating stacked J/psi plots ...")
            plots = write_stacked_jpsi_plots(
                derived_dir / "plots" / "stacked_jpsi",
                stacked_acc_df,
                stacked_eff_df,
                plot_style_cfg=CmsPlotStyleConfig(is_data=False),
                min_total=min_plot_total,
            )
            qa_plots.update(
                {
                    f"stacked_jpsi_qa.{key}": path
                    for key, path in write_stacked_jpsi_plots(
                        derived_dir / "plots_with_uncertainty" / "stacked_jpsi",
                        stacked_acc_df,
                        stacked_eff_df,
                        plot_style_cfg=CmsPlotStyleConfig(is_data=False),
                        min_total=min_plot_total,
                        include_uncertainty=True,
                    ).items()
                }
            )
            print(f"[{sample}]   {len(plots)} stacked J/psi plots written")

    manifest: dict[str, object] = {
        "source": str(sample_dir.resolve()),
        "outputs": {},
    }
    if not poa_df.empty:
        manifest["outputs"]["per_object_acceptance_parquet"] = "per_object_acceptance_maps.parquet"
        manifest["outputs"]["per_object_acceptance_csv"] = "per_object_acceptance_maps.csv"
        if poa_plots:
            manifest["outputs"]["per_object_acceptance_plots"] = {
                key: str(path.relative_to(derived_dir)) for key, path in poa_plots.items()
            }
    if not stacked_acc_df.empty:
        manifest["outputs"]["stacked_jpsi_acceptance_parquet"] = "stacked_jpsi_acceptance_maps.parquet"
        manifest["outputs"]["stacked_jpsi_acceptance_csv"] = "stacked_jpsi_acceptance_maps.csv"
    if not stacked_eff_df.empty:
        manifest["outputs"]["stacked_jpsi_efficiency_parquet"] = "stacked_jpsi_efficiency_maps.parquet"
        manifest["outputs"]["stacked_jpsi_efficiency_csv"] = "stacked_jpsi_efficiency_maps.csv"
    if plots:
        manifest["outputs"]["stacked_jpsi_plots"] = {key: str(path.relative_to(derived_dir)) for key, path in plots.items()}
    if qa_plots:
        manifest["outputs"]["plots_with_uncertainty"] = {key: str(path.relative_to(derived_dir)) for key, path in qa_plots.items()}
    write_json(manifest, derived_dir / "manifest.json")
    print(f"[{sample}] Done.")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build derived acceptance and conditional efficiency maps")
    parser.add_argument("--input-dir", required=True, help="Merge output directory (contains per-sample subdirs + manifest.json)")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: same as --input-dir)")
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--min-plot-total", type=int, default=1)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir

    sample_dirs = _discover_samples(input_dir)
    print(f"Processing {len(sample_dirs)} sample(s) from {input_dir}")
    manifests: dict[str, object] = {}
    for sample_dir in sample_dirs:
        manifests[sample_dir.name] = build_derived_for_sample(
            sample_dir, output_dir, skip_plots=args.skip_plots, min_plot_total=args.min_plot_total
        )

    top_manifest = {
        "stage": "derived_efficiency",
        "input_dir": str(input_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "samples": manifests,
    }
    write_json(top_manifest, output_dir / "derived_manifest.json")
    print(f"\nDone. Derived manifest: {output_dir / 'derived_manifest.json'}")


if __name__ == "__main__":
    main()

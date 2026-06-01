#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from efficiency_workflow.config import CmsPlotStyleConfig
from efficiency_workflow.efficiency import EfficiencyBinning
from efficiency_workflow.plotting import (
    write_derived_plot_bundle,
    write_efficiency_plot_bundle,
    write_systematic_uncertainty_plots,
)
from efficiency_workflow.products import (
    build_derived_efficiency_products,
    build_systematic_uncertainty,
    update_manifest_outputs,
    write_derived_products_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build derived acceptance and conditional efficiency maps")
    parser.add_argument("--input-dir", required=True, help="Merge output directory (contains per-sample subdirs + manifest.json)")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: same as --input-dir)")
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--min-plot-total", type=int, default=1)
    parser.add_argument("--skip-trigger-matching", action="store_true",
                        help="Use the no-trigger-matching chain (_noTrigMatch columns)")
    parser.add_argument(
        "--systematics",
        nargs="?",
        const="DPS_1",
        default=None,
        metavar="NOMINAL",
        help="Also build subprocess systematic uncertainty with optional nominal sample",
    )
    args = parser.parse_args()

    include_trig_match = not args.skip_trigger_matching
    binning = EfficiencyBinning(include_trigger_matching=include_trig_match)

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir
    products_by_sample = build_derived_efficiency_products(input_dir, output_dir, binning=binning)
    print(f"Processing {len(products_by_sample)} sample(s) from {input_dir}")

    if not args.skip_plots:
        for products in products_by_sample.values():
            print(f"[{products.sample}] Generating cumulative efficiency plots ...")
            cumul_outputs = write_efficiency_plot_bundle(
                products.derived_dir,
                products.counts_df,
                plot_style_cfg=CmsPlotStyleConfig(is_data=False),
                min_total=args.min_plot_total,
            )
            if cumul_outputs:
                products.manifest["outputs"].update(cumul_outputs)
                update_manifest_outputs(products.derived_dir / "manifest.json", cumul_outputs)

            print(f"[{products.sample}] Generating derived plots ...")
            plot_outputs = write_derived_plot_bundle(
                products.derived_dir,
                acceptance_df=products.acceptance_df,
                conditional_df=products.conditional_df,
                per_object_acceptance_df=products.per_object_acceptance_df,
                stacked_jpsi_acceptance_df=products.stacked_jpsi_acceptance_df,
                stacked_jpsi_efficiency_df=products.stacked_jpsi_efficiency_df,
                pair_level_dfs=products.pair_level_dfs,
                plot_style_cfg=CmsPlotStyleConfig(is_data=False),
                min_total=args.min_plot_total,
            )
            if plot_outputs:
                products.manifest["outputs"].update(plot_outputs)
                update_manifest_outputs(products.derived_dir / "manifest.json", plot_outputs)
        write_derived_products_manifest(input_dir, output_dir, products_by_sample)

    if args.systematics:
        print(f"Building subprocess systematic uncertainty with nominal sample {args.systematics} ...")
        systematics = build_systematic_uncertainty(
            input_dir,
            output_dir,
            binning=binning,
            nominal_sample=args.systematics,
            min_total=args.min_plot_total,
        )
        if not args.skip_plots:
            write_systematic_uncertainty_plots(
                output_dir,
                systematics,
                plot_style_cfg=CmsPlotStyleConfig(is_data=False),
                min_total=args.min_plot_total,
            )

    print(f"\nDone. Derived manifest: {output_dir / 'derived_manifest.json'}")


if __name__ == "__main__":
    main()

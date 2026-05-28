#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from efficiency_workflow.config import CmsPlotStyleConfig
from efficiency_workflow.plotting import write_derived_plot_bundle
from efficiency_workflow.products import (
    build_derived_efficiency_products,
    update_manifest_outputs,
    write_derived_products_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build derived acceptance and conditional efficiency maps")
    parser.add_argument("--input-dir", required=True, help="Merge output directory (contains per-sample subdirs + manifest.json)")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: same as --input-dir)")
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--min-plot-total", type=int, default=1)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir
    products_by_sample = build_derived_efficiency_products(input_dir, output_dir)
    print(f"Processing {len(products_by_sample)} sample(s) from {input_dir}")

    if not args.skip_plots:
        for products in products_by_sample.values():
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

    print(f"\nDone. Derived manifest: {output_dir / 'derived_manifest.json'}")


if __name__ == "__main__":
    main()

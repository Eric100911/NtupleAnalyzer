#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


import argparse
from pathlib import Path

from efficiency_workflow.config import CmsPlotStyleConfig
from efficiency_workflow.efficiency import EfficiencyBinning
from efficiency_workflow.plotting import (
    write_derived_plot_bundle,
    write_efficiency_plot_bundle,
    write_stacked_jpsi_plots,
    write_systematic_uncertainty_plots,
    with_subprocess_label,
)
from efficiency_workflow.products import (
    build_derived_efficiency_products,
    build_systematic_uncertainty,
    update_manifest_outputs,
    write_derived_products_manifest,
)


def _record_outputs(products, outputs: dict[str, object]) -> None:
    """Persist plot outputs and keep the in-memory manifest in sync."""
    if not outputs:
        return
    merged_manifest = update_manifest_outputs(products.derived_dir / "manifest.json", outputs)
    products.manifest.clear()
    products.manifest.update(merged_manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build derived acceptance and conditional efficiency maps")
    parser.add_argument("--input-dir", required=True, help="Merge output directory (contains per-sample subdirs + manifest.json)")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: same as --input-dir)")
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument(
        "--plot-scope",
        default="separate-jpsi",
        choices=("separate-jpsi", "stacked-jpsi-only", "both"),
        help="Plot layout: separate-jpsi (full bundle), stacked-jpsi-only (dedicated stacked plots), or both.",
    )
    parser.add_argument(
        "--with-uncertainty-plots",
        action="store_true",
        help="For stacked-jpsi-only or both, also write uncertainty QA versions.",
    )
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
    binning = EfficiencyBinning(include_trigger_matching=False) if not include_trig_match else None

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir
    products_by_sample = build_derived_efficiency_products(input_dir, output_dir, binning=binning)
    print(f"Processing {len(products_by_sample)} sample(s) from {input_dir}")

    if not args.skip_plots:
        for products in products_by_sample.values():
            plot_outputs = {}
            if args.plot_scope in {"separate-jpsi", "both"}:
                print(f"[{products.sample}] Generating cumulative efficiency plots ...")
                cumul_outputs = write_efficiency_plot_bundle(
                    products.derived_dir,
                    products.counts_df,
                    plot_style_cfg=CmsPlotStyleConfig(is_data=False),
                    min_total=args.min_plot_total,
                )
                if cumul_outputs:
                    _record_outputs(products, cumul_outputs)

                print(f"[{products.sample}] Generating derived plots ...")
                derived_outputs = write_derived_plot_bundle(
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
                _record_outputs(products, derived_outputs)

            if args.plot_scope in {"stacked-jpsi-only", "both"}:
                print(f"[{products.sample}] Generating stacked J/psi plots only ...")
                style = with_subprocess_label(CmsPlotStyleConfig(is_data=False), products.sample)
                regular = write_stacked_jpsi_plots(
                    products.derived_dir / "plots" / "stacked_jpsi",
                    products.stacked_jpsi_acceptance_df,
                    products.stacked_jpsi_efficiency_df,
                    plot_style_cfg=style,
                    min_total=args.min_plot_total,
                )
                plot_outputs = {}
                if regular:
                    output_key = (
                        "stacked_jpsi_plots"
                        if args.plot_scope == "stacked-jpsi-only"
                        else "stacked_jpsi_only_plots"
                    )
                    plot_outputs[output_key] = {
                        key: str(path.relative_to(products.derived_dir))
                        for key, path in regular.items()
                    }
                if args.with_uncertainty_plots:
                    qa = write_stacked_jpsi_plots(
                        products.derived_dir / "plots_with_uncertainty" / "stacked_jpsi",
                        products.stacked_jpsi_acceptance_df,
                        products.stacked_jpsi_efficiency_df,
                        plot_style_cfg=style,
                        min_total=args.min_plot_total,
                        include_uncertainty=True,
                    )
                    if qa:
                        output_key = (
                            "plots_with_uncertainty"
                            if args.plot_scope == "stacked-jpsi-only"
                            else "stacked_jpsi_only_plots_with_uncertainty"
                        )
                        plot_outputs[output_key] = {
                            f"stacked_jpsi_qa.{key}": str(path.relative_to(products.derived_dir))
                            for key, path in qa.items()
                        }
            if plot_outputs:
                _record_outputs(products, plot_outputs)
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

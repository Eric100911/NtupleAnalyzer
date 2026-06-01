#!/usr/bin/env python3
"""Build MC subprocess systematic uncertainty on efficiency and acceptance."""
from __future__ import annotations

import argparse
from pathlib import Path

from efficiency_workflow.config import CmsPlotStyleConfig
from efficiency_workflow.efficiency import EfficiencyBinning
from efficiency_workflow.io import read_json, write_json
from efficiency_workflow.products import build_systematic_uncertainty


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build MC subprocess systematic uncertainty on efficiency and acceptance."
    )
    parser.add_argument("--input-dir", required=True, help="Derived efficiency output directory with per-sample subdirs")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: same as --input-dir)")
    parser.add_argument("--nominal-sample", default="DPS_1", help="Nominal subprocess sample")
    parser.add_argument("--min-total", type=int, default=1, help="Flag bins with sample total below this threshold")
    parser.add_argument("--min-n-samples", type=int, default=2, help="Require at least this many valid sample values per bin")
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument(
        "--skip-trigger-matching",
        action="store_true",
        help="Use the no-trigger-matching chain (_noTrigMatch columns)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir
    binning = EfficiencyBinning(include_trigger_matching=not args.skip_trigger_matching)

    results = build_systematic_uncertainty(
        input_dir,
        output_dir,
        binning=binning,
        nominal_sample=args.nominal_sample,
        min_total=args.min_total,
        min_n_samples=args.min_n_samples,
    )
    print(
        f"Built {len(results.products)} systematic product(s) with nominal sample "
        f"{results.nominal_sample}"
    )

    if not args.skip_plots:
        from efficiency_workflow.plotting import write_systematic_uncertainty_plots

        plot_outputs = write_systematic_uncertainty_plots(
            output_dir,
            results,
            plot_style_cfg=CmsPlotStyleConfig(is_data=False),
            min_total=args.min_total,
        )
        if plot_outputs:
            manifest_path = results.output_dir / "systematic_manifest.json"
            manifest = read_json(manifest_path)
            manifest["plots"] = plot_outputs
            write_json(manifest, manifest_path)
            print(f"Wrote {len(plot_outputs)} systematic plot(s)")

    print(f"Done. Systematics manifest: {results.output_dir / 'systematic_manifest.json'}")


if __name__ == "__main__":
    main()

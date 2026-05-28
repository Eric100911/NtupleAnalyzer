#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from efficiency_workflow.config import CmsPlotStyleConfig
from efficiency_workflow.plotting import write_efficiency_plot_bundle
from efficiency_workflow.products import merge_efficiency_shards, update_sample_manifest_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge JJP efficiency shard outputs")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--shards-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--min-plot-total", type=int, default=1)
    args = parser.parse_args()

    result = merge_efficiency_shards(
        sample=args.sample,
        shards_dir=Path(args.shards_dir),
        output_dir=Path(args.output_dir),
    )
    if not args.skip_plots:
        plot_artifacts = write_efficiency_plot_bundle(
            result.sample_dir,
            result.counts_df,
            plot_style_cfg=CmsPlotStyleConfig(is_data=False),
            min_total=args.min_plot_total,
        )
        update_sample_manifest_artifacts(result.sample_dir, plot_artifacts)
    print(f"Wrote merged efficiency outputs to {result.output_dir}")


if __name__ == "__main__":
    main()

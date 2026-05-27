#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from efficiency_workflow.config import CmsPlotStyleConfig
from efficiency_workflow.io import ensure_dir
from efficiency_workflow.plotting import (
    save_efficiency_heatmap_pair,
    write_per_object_acceptance_plots,
    write_stacked_jpsi_plots,
)


def render_smoke_plots(derived_dir: Path, output_dir: Path, min_plot_total: int, with_uncertainty: bool) -> dict[str, Path]:
    output_dir = ensure_dir(output_dir)
    style = CmsPlotStyleConfig(is_data=False)
    written: dict[str, Path] = {}

    poa_path = derived_dir / "per_object_acceptance_maps.parquet"
    stacked_acc_path = derived_dir / "stacked_jpsi_acceptance_maps.parquet"
    stacked_eff_path = derived_dir / "stacked_jpsi_efficiency_maps.parquet"
    poa_df = pd.read_parquet(poa_path) if poa_path.exists() else pd.DataFrame()
    stacked_acc_df = pd.read_parquet(stacked_acc_path) if stacked_acc_path.exists() else pd.DataFrame()
    stacked_eff_df = pd.read_parquet(stacked_eff_path) if stacked_eff_path.exists() else pd.DataFrame()

    if not poa_df.empty:
        phi_df = poa_df.loc[poa_df["object"] == "phi"].copy()
        if not phi_df.empty:
            written.update(
                {
                    f"phi_acceptance.{key}": path
                    for key, path in write_per_object_acceptance_plots(
                        output_dir / "phi_acceptance",
                        phi_df,
                        plot_style_cfg=style,
                        min_total=min_plot_total,
                    ).items()
                }
            )

    if not stacked_acc_df.empty or not stacked_eff_df.empty:
        eff_subset = stacked_eff_df.loc[stacked_eff_df["step"].isin(["hlt_event", "Pri_fitPass"])].copy()
        written.update(
            {
                f"stacked_jpsi.{key}": path
                for key, path in write_stacked_jpsi_plots(
                    output_dir / "stacked_jpsi",
                    stacked_acc_df,
                    eff_subset,
                    plot_style_cfg=style,
                    min_total=min_plot_total,
                ).items()
            }
        )

    if with_uncertainty and not stacked_acc_df.empty:
        written["stacked_jpsi_acceptance_pair"] = save_efficiency_heatmap_pair(
            output_dir / "qa_stacked_jpsi_acceptance_pair.png",
            stacked_acc_df,
            title=r"Stacked $J/\psi$ fiducial acceptance",
            xlabel=None,
            ylabel=None,
            plot_style_cfg=style,
            min_total=min_plot_total,
            zlabel="Acceptance",
        )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a small smoke-test set of efficiency plots from derived parquet files.")
    parser.add_argument("--derived-dir", required=True, help="Directory containing derived parquet files.")
    parser.add_argument("--output-dir", default=None, help="Output directory for smoke-test plots.")
    parser.add_argument("--min-plot-total", type=int, default=1)
    parser.add_argument("--with-uncertainty", action="store_true", help="Also render one QA pair plot with uncertainty.")
    args = parser.parse_args()

    derived_dir = Path(args.derived_dir)
    output_dir = Path(args.output_dir) if args.output_dir else derived_dir / "plot_smoke_test"
    written = render_smoke_plots(derived_dir, output_dir, args.min_plot_total, args.with_uncertainty)
    print(f"Wrote {len(written)} smoke-test plot(s) to {output_dir}")
    for key, path in sorted(written.items()):
        print(f"{key}: {path}")


if __name__ == "__main__":
    main()

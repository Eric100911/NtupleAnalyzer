#!/usr/bin/env python3
from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path

import pandas as pd
import pytest

from efficiency_workflow.build_factorized_maps import (
    _build_factor_map,
    _jpsi_object_frame,
    factor_specs,
)
from efficiency_workflow.config import CmsPlotStyleConfig
from efficiency_workflow.efficiency import (
    EfficiencyBinning,
    build_stacked_jpsi_acceptance_maps,
    build_stacked_jpsi_efficiency_maps,
)
from efficiency_workflow.io import ensure_dir
from efficiency_workflow.plotting import (
    save_efficiency_heatmap,
    subprocess_label_for_sample,
    with_subprocess_label,
    write_per_object_acceptance_plots,
    write_stacked_jpsi_plots,
)


def test_default_plot_style_uses_run3() -> None:
    assert CmsPlotStyleConfig().era == "Run 3"


def test_subprocess_labels_are_known_for_current_samples() -> None:
    assert subprocess_label_for_sample("JJP_DPS1") == r"DPS $J/\psi+(J/\psi+\phi)$"
    assert subprocess_label_for_sample("JJP_SPS_G") == r"SPS $J/\psi+J/\psi+\phi$ @ CSM NLO$^{*}$"
    assert subprocess_label_for_sample("unknown") is None


def test_with_subprocess_label_preserves_explicit_label() -> None:
    style = CmsPlotStyleConfig(subprocess_label="custom")
    assert with_subprocess_label(style, "JJP_DPS1").subprocess_label == "custom"


def test_stacked_jpsi_maps_use_pt_and_abs_y() -> None:
    keys = {
        "sample": "JJP_DPS1",
        "source_file": "input.root",
        "run": 1,
        "lumi": 1,
    }
    gen_df = pd.DataFrame(
        [
            {
                **keys,
                "entry": 0,
                "event": 10,
                "jpsi_lead_pt": 8.0,
                "jpsi_lead_y": -0.4,
                "jpsi_lead_abs_y": 0.4,
                "jpsi_sublead_pt": 12.0,
                "jpsi_sublead_y": 1.4,
                "jpsi_sublead_abs_y": 1.4,
            },
            {
                **keys,
                "entry": 1,
                "event": 11,
                "jpsi_lead_pt": 22.0,
                "jpsi_lead_y": -2.0,
                "jpsi_lead_abs_y": 2.0,
                "jpsi_sublead_pt": 7.0,
                "jpsi_sublead_y": 0.8,
                "jpsi_sublead_abs_y": 0.8,
            },
        ]
    )
    event_df = pd.DataFrame(
        [
            {
                **keys,
                "entry": 0,
                "event": 10,
                "full_gen": 1,
                "jpsi_lead_fiducial": 1,
                "jpsi_lead_muonRECO": 1,
                "jpsi_lead_muonID": 1,
                "jpsi_lead_dimuon": 1,
                "jpsi_sublead_fiducial": 1,
                "jpsi_sublead_muonRECO": 1,
                "jpsi_sublead_muonID": 0,
                "jpsi_sublead_dimuon": 0,
            },
            {
                **keys,
                "entry": 1,
                "event": 11,
                "full_gen": 1,
                "jpsi_lead_fiducial": 0,
                "jpsi_lead_muonRECO": 0,
                "jpsi_lead_muonID": 0,
                "jpsi_lead_dimuon": 0,
                "jpsi_sublead_fiducial": 1,
                "jpsi_sublead_muonRECO": 1,
                "jpsi_sublead_muonID": 1,
                "jpsi_sublead_dimuon": 0,
            },
        ]
    )

    binning = EfficiencyBinning()
    acc = build_stacked_jpsi_acceptance_maps(gen_df, event_df, binning)
    eff = build_stacked_jpsi_efficiency_maps(gen_df, event_df, binning)

    n_cells = (len(binning.jpsi_pt_edges) - 1) * (len(binning.object_abs_y_edges) - 1)
    assert len(acc) == n_cells
    assert len(eff) == n_cells * 3
    assert set(acc["y_axis"]) == {"abs_y"}
    assert set(eff["y_axis"]) == {"abs_y"}
    assert acc["y_min"].min() >= 0.0
    assert eff["y_max"].max() == binning.object_abs_y_edges[-1]


def _stacked_inputs(flag_rows, role="lead"):
    gen_rows, event_rows = [], []
    for entry, flags in enumerate(flag_rows):
        keys = dict(sample="JJP_TEST", source_file="test.root", entry=entry,
                    run=1, lumi=1, event=entry)
        gen_rows.append({
            **keys, "jpsi_lead_pt": 8.0, "jpsi_lead_y": -0.4,
            "jpsi_sublead_pt": 7.0, "jpsi_sublead_y": 0.4,
        })
        row = {**keys, "full_gen": 1}
        for current_role in ("lead", "sublead"):
            values = flags if role in (current_role, "both") else (0, 0, 0, 0)
            for step, value in zip(("fiducial", "muonRECO", "muonID", "dimuon"), values):
                row[f"jpsi_{current_role}_{step}"] = value
        event_rows.append(row)
    return pd.DataFrame(gen_rows), pd.DataFrame(event_rows)


@pytest.mark.parametrize("role", ["lead", "sublead", "both"])
@pytest.mark.parametrize("flag_rows, expected", [
    ([(1, 1, 1, 1), (0, 1, 1, 0), (1, 0, 0, 0)], [(2, 1), (1, 1), (1, 1)]),
    ([(1, 1, 1, 1), (0, 0, 1, 1), (1, 0, 0, 1)], [(2, 1), (1, 1), (1, 1)]),
    ([(1, 0, 0, 0)], [(1, 0), (0, 0), (0, 0)]),
    ([(1, 1, 1, 1)], [(1, 1), (1, 1), (1, 1)]),
])
def test_stacked_cumulative_counts(role, flag_rows, expected):
    gen_df, event_df = _stacked_inputs(flag_rows, role)
    result = build_stacked_jpsi_efficiency_maps(gen_df, event_df, EfficiencyBinning())
    cell = result[(result["x_min"] <= 7.0) & (result["x_max"] > 8.0)
                  & (result["y_min"] <= 0.4) & (result["y_max"] > 0.4)].set_index("step")
    multiplier = 2 if role == "both" else 1
    for step, (total, passed) in zip(("muonRECO", "muonID", "dimuon"), expected):
        row = cell.loc[step]
        assert row["total"] == total * multiplier
        assert row["passed"] == passed * multiplier
        if total:
            assert row["efficiency"] == pytest.approx(passed / total)
    assert result["passed"].between(0, result["total"]).all()
    populated = result[result["total"] > 0]
    assert populated["efficiency"].between(0, 1).all()
    assert populated[["err_low", "err_high", "err_sym"]].ge(0).all().all()
    empty = result[result["total"] == 0]
    assert empty[["efficiency", "err_low", "err_high", "err_sym"]].isna().all().all()


def test_stacked_counts_match_factorized_fine_bins():
    gen_df, event_df = _stacked_inputs(list(product((0, 1), repeat=4)), "both")
    binning = EfficiencyBinning()
    stacked = build_stacked_jpsi_efficiency_maps(gen_df, event_df, binning)
    objects = _jpsi_object_frame(gen_df.merge(event_df))
    for name in ("eff_muReco_jpsi", "eff_muID_jpsi", "eff_dimuon_jpsi"):
        _, spec = factor_specs(binning)[name]
        factor = _build_factor_map(objects, spec)
        fine = factor[factor["fallback_level"] == "fine"]
        actual = stacked[stacked["step"] == spec.numerator_col]
        columns = ["total", "passed", "efficiency"]
        pd.testing.assert_frame_equal(
            actual.set_index(["x_bin", "y_bin"])[columns].sort_index(),
            fine.set_index(["x_bin", "y_bin"])[columns].sort_index(),
        )


@pytest.mark.parametrize("missing", ["muonRECO", "muonID", "dimuon"])
@pytest.mark.parametrize("roles", [("lead",), ("lead", "sublead")])
def test_stacked_missing_flags_do_not_create_successes(missing, roles):
    gen_df, event_df = _stacked_inputs([(1, 1, 1, 1)], "both")
    columns = [f"jpsi_{role}_{missing}" for role in roles]
    actual = build_stacked_jpsi_efficiency_maps(
        gen_df, event_df.drop(columns=columns), EfficiencyBinning())
    event_df[columns] = 0
    expected = build_stacked_jpsi_efficiency_maps(gen_df, event_df, EfficiencyBinning())
    pd.testing.assert_frame_equal(actual, expected)


def test_stacked_empty_input():
    gen_df, event_df = _stacked_inputs([(1, 1, 1, 1)])
    for gen, events in ((gen_df.iloc[:0], event_df), (gen_df, event_df.iloc[:0])):
        assert build_stacked_jpsi_efficiency_maps(gen, events, EfficiencyBinning()).empty


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
        written["stacked_jpsi_acceptance_pair"] = save_efficiency_heatmap(
            output_dir / "qa_stacked_jpsi_acceptance_pair.png",
            stacked_acc_df,
            title=r"Stacked $J/\psi$ fiducial acceptance",
            xlabel=None,
            ylabel=None,
            plot_style_cfg=style,
            min_total=min_plot_total,
            zlabel="Acceptance",
            include_uncertainty=True,
            show_title=True,
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

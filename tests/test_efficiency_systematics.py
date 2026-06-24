#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from efficiency_workflow.products import DerivedSampleProducts
from efficiency_workflow.systematics import build_subprocess_systematics_summary


def _counts_df(passed: int, total: int = 100) -> pd.DataFrame:
    eff = passed / total
    return pd.DataFrame(
        [
            {
                "map_type": "object_2d",
                "object": "phi",
                "step": "fiducial",
                "x_axis": "pt",
                "y_axis": "y",
                "x_bin": 0,
                "y_bin": 0,
                "x_min": 4.0,
                "x_max": 6.0,
                "y_min": -2.4,
                "y_max": -1.8,
                "x_label": "4-6",
                "y_label": "-2.4--1.8",
                "total": total,
                "passed": passed,
                "efficiency": eff,
                "err_low": 0.05,
                "err_high": 0.05,
                "err_sym": 0.05,
            }
        ]
    )


def _products(sample: str, counts_df: pd.DataFrame) -> DerivedSampleProducts:
    empty = pd.DataFrame()
    return DerivedSampleProducts(
        sample=sample,
        sample_dir=Path(sample),
        derived_dir=Path(sample) / "derived",
        manifest={},
        counts_df=counts_df,
        acceptance_df=empty,
        conditional_df=empty,
        per_object_acceptance_df=empty,
        stacked_jpsi_acceptance_df=empty,
        stacked_jpsi_efficiency_df=empty,
        pair_level_dfs={},
    )


def test_subprocess_systematics_resolves_nominal_alias_and_envelope() -> None:
    results = build_subprocess_systematics_summary(
        {
            "JJP_DPS1": _products("JJP_DPS1", _counts_df(50)),
            "JJP_SPS_CS": _products("JJP_SPS_CS", _counts_df(75)),
        },
        nominal_sample="DPS_1",
    )

    frame = results.products["counts"].systematics_df
    assert results.nominal_sample == "JJP_DPS1"
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["nominal_eff"] == pytest.approx(0.5)
    assert row["eff_min"] == pytest.approx(0.5)
    assert row["eff_max"] == pytest.approx(0.75)
    assert row["envelope_half_width"] == pytest.approx(0.125)
    assert row["max_deviation_from_nominal"] == pytest.approx(0.25)
    assert row["ratio_JJP_SPS_CS"] == pytest.approx(1.5)


def test_subprocess_systematics_excludes_bins_without_enough_samples() -> None:
    results = build_subprocess_systematics_summary(
        {
            "JJP_DPS1": _products("JJP_DPS1", _counts_df(50)),
        },
        nominal_sample="JJP_DPS1",
        min_n_samples=2,
    )

    assert results.products == {}
    assert results.systematic_summary_df.empty

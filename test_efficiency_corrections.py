from __future__ import annotations

import array
import math

import pandas as pd

from efficiency_workflow.corrections import (
    FactorizedCorrectionMap,
    STATUS_MISSING_BIN,
    STATUS_OK,
    EfficiencyCorrectionMap,
    annotate_root_tree_with_efficiency,
)


def _map_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "map_type": "correlated_3d",
                "step": "Pri_assocPVPass",
                "x_min": 10.0,
                "x_max": 15.0,
                "y_min": 6.0,
                "y_max": 10.0,
                "z_min": 4.0,
                "z_max": 6.0,
                "x_bin": 1,
                "y_bin": 0,
                "z_bin": 0,
                "efficiency": 0.25,
                "err_low": 0.02,
                "err_high": 0.03,
            },
            {
                "map_type": "correlated_3d",
                "step": "Pri_trackPVPass",
                "x_min": 10.0,
                "x_max": 15.0,
                "y_min": 6.0,
                "y_max": 10.0,
                "z_min": 4.0,
                "z_max": 6.0,
                "x_bin": 1,
                "y_bin": 0,
                "z_bin": 0,
                "efficiency": 0.125,
                "err_low": 0.01,
                "err_high": 0.02,
            },
        ]
    )


def test_lookup_uses_lead_sublead_jpsi_ordering() -> None:
    correction_map = EfficiencyCorrectionMap(
        _map_frame(),
        source="memory.parquet",
        step="Pri_assocPVPass",
    )

    correction = correction_map.lookup(jpsi1_pt=7.0, jpsi2_pt=12.0, phi_pt=5.0)

    assert correction.status == STATUS_OK
    assert correction.x_bin == 1
    assert correction.y_bin == 0
    assert correction.z_bin == 0
    assert correction.efficiency == 0.25
    assert correction.weight == 4.0


def test_lookup_reports_missing_bin() -> None:
    correction_map = EfficiencyCorrectionMap(
        _map_frame(),
        source="memory.parquet",
        step="Pri_assocPVPass",
    )

    correction = correction_map.lookup(jpsi1_pt=7.0, jpsi2_pt=16.0, phi_pt=5.0)

    assert correction.status == STATUS_MISSING_BIN
    assert math.isnan(correction.weight)


def test_annotate_root_tree_with_efficiency(tmp_path) -> None:
    import ROOT

    input_path = tmp_path / "selected.root"
    output_path = tmp_path / "selected_effcorr.root"

    root_file = ROOT.TFile(str(input_path), "RECREATE")
    tree = ROOT.TTree("selected", "selected")
    jpsi1_pt = array.array("d", [0.0])
    jpsi2_pt = array.array("d", [0.0])
    phi_pt = array.array("d", [0.0])
    tree.Branch("sel_Jpsi_1_pt", jpsi1_pt, "sel_Jpsi_1_pt/D")
    tree.Branch("sel_Jpsi_2_pt", jpsi2_pt, "sel_Jpsi_2_pt/D")
    tree.Branch("sel_Phi_pt", phi_pt, "sel_Phi_pt/D")
    for values in ((7.0, 12.0, 5.0), (8.0, 11.0, 5.5)):
        jpsi1_pt[0], jpsi2_pt[0], phi_pt[0] = values
        tree.Fill()
    tree.Write()
    root_file.Close()

    correction_map = EfficiencyCorrectionMap(
        _map_frame(),
        source="memory.parquet",
        step="Pri_assocPVPass",
    )
    summary = annotate_root_tree_with_efficiency(
        input_file=input_path,
        output_file=output_path,
        correction_map=correction_map,
    )

    assert summary.entries == 2
    assert summary.ok == 2

    out_file = ROOT.TFile.Open(str(output_path))
    out_tree = out_file.Get("selected")
    assert out_tree.GetEntries() == 2
    out_tree.GetEntry(0)
    assert out_tree.effcorr_status == STATUS_OK
    assert out_tree.effcorr_efficiency == 0.25
    assert out_tree.effcorr_weight == 4.0
    out_file.Close()


def _factor_frame(factor_name: str, *, fine_total: int = 100, fine_eff: float = 1.0, coarse_eff: float = 1.0) -> pd.DataFrame:
    rows = []
    for level, total, eff, y_min, y_max in (
        ("fine", fine_total, fine_eff, 0.0, 0.6),
        ("coarse", 100, coarse_eff, math.nan, math.nan),
        ("inclusive", 100, 1.0, math.nan, math.nan),
    ):
        rows.append(
            {
                "map_type": "factorized",
                "factor_name": factor_name,
                "fallback_level": level,
                "x_min": 6.0 if level != "inclusive" else math.nan,
                "x_max": 10.0 if level != "inclusive" else math.nan,
                "y_min": y_min,
                "y_max": y_max,
                "z_min": math.nan,
                "z_max": math.nan,
                "x_bin": 0 if level != "inclusive" else -1,
                "y_bin": 0 if level == "fine" else -1,
                "z_bin": -1,
                "total": total,
                "passed": int(round(total * eff)),
                "efficiency": eff,
                "err_sym": 0.01,
            }
        )
    return pd.DataFrame(rows)


def test_factorized_lookup_uses_coarse_fallback_for_sparse_fine_bin() -> None:
    maps = {}
    for factor_name in FactorizedCorrectionMap.REQUIRED_FACTORS:
        if factor_name == "acceptance_jpsi":
            maps[factor_name] = _factor_frame(factor_name, fine_total=5, fine_eff=0.1, coarse_eff=0.5)
        else:
            maps[factor_name] = _factor_frame(factor_name)

    correction_map = FactorizedCorrectionMap(maps, source="memory", n_min_fine=30, n_min_coarse=50)
    correction = correction_map.lookup(
        jpsi1_pt=7.0,
        jpsi1_y=0.2,
        jpsi2_pt=8.0,
        jpsi2_y=-0.3,
        phi_pt=7.0,
        phi_y=0.1,
    )

    assert correction.status == STATUS_OK
    assert correction.efficiency == 0.25
    assert correction.weight == 4.0
    fallback = [component for component in correction.components if component.factor_name == "acceptance_jpsi"]
    assert {component.fallback_level for component in fallback} == {"coarse"}

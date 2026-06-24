from __future__ import annotations

import array
import math

import numpy as np
import pandas as pd

from efficiency_workflow import yield_correction as yc
from efficiency_workflow.corrections import (
    FactorizedCorrectionMap,
    STATUS_INVALID_EFFICIENCY,
    STATUS_MISSING_BIN,
    STATUS_OK,
    EfficiencyCorrectionMap,
    annotate_root_tree_with_efficiency,
)
from efficiency_workflow.yield_correction import write_factorized_corrected_root_tree


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


def test_factorized_lookup_arrays_match_scalar_for_mixed_statuses() -> None:
    maps = {factor_name: _factor_frame(factor_name) for factor_name in FactorizedCorrectionMap.REQUIRED_FACTORS}
    maps["acceptance_jpsi"] = pd.concat(
        [
            _factor_frame("acceptance_jpsi", fine_total=5, fine_eff=0.1, coarse_eff=0.5),
            pd.DataFrame(
                [
                    {
                        "map_type": "factorized",
                        "factor_name": "acceptance_jpsi",
                        "fallback_level": "fine",
                        "x_min": 10.0,
                        "x_max": 15.0,
                        "y_min": 0.0,
                        "y_max": 0.6,
                        "z_min": math.nan,
                        "z_max": math.nan,
                        "x_bin": 1,
                        "y_bin": 0,
                        "z_bin": -1,
                        "total": 100,
                        "passed": 0,
                        "efficiency": 0.0,
                        "err_sym": 0.01,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    maps["acceptance_phi"].loc[maps["acceptance_phi"]["fallback_level"] == "inclusive", "total"] = 0
    correction_map = FactorizedCorrectionMap(maps, source="memory", n_min_fine=30, n_min_coarse=50)

    arrays = {
        "jpsi1_pt": np.asarray([7.0, 11.0, 101.0]),
        "jpsi1_y": np.asarray([0.2, 0.2, 0.2]),
        "jpsi2_pt": np.asarray([8.0, 8.0, 8.0]),
        "jpsi2_y": np.asarray([-0.3, -0.3, -0.3]),
        "phi_pt": np.asarray([7.0, 7.0, 101.0]),
        "phi_y": np.asarray([0.1, 0.1, 0.1]),
    }
    vectorized = correction_map.lookup_arrays(**arrays)
    scalar = [
        correction_map.lookup(
            jpsi1_pt=float(arrays["jpsi1_pt"][idx]),
            jpsi1_y=float(arrays["jpsi1_y"][idx]),
            jpsi2_pt=float(arrays["jpsi2_pt"][idx]),
            jpsi2_y=float(arrays["jpsi2_y"][idx]),
            phi_pt=float(arrays["phi_pt"][idx]),
            phi_y=float(arrays["phi_y"][idx]),
        )
        for idx in range(len(arrays["jpsi1_pt"]))
    ]

    assert vectorized.status.tolist() == [item.status for item in scalar]
    assert vectorized.status.tolist() == [STATUS_OK, STATUS_INVALID_EFFICIENCY, STATUS_MISSING_BIN]
    assert vectorized.weight[0] == scalar[0].weight
    assert vectorized.efficiency[0] == scalar[0].efficiency
    assert vectorized.fallback_components[0] == sum(
        component.fallback_level != "fine" for component in scalar[0].components
    )
    assert math.isnan(vectorized.weight[1])
    assert math.isnan(vectorized.weight[2])


def test_build_factorized_weighted_mini_tree_uses_vectorized_arrays(monkeypatch, tmp_path) -> None:
    arrays = {
        "sel_Jpsi_1_mass": np.asarray([3.1, 3.1], dtype=np.float64),
        "sel_Jpsi_2_mass": np.asarray([3.1, 3.1], dtype=np.float64),
        "sel_Phi_mass": np.asarray([1.02, 1.02], dtype=np.float64),
        "sel_Jpsi_1_pt": np.asarray([7.0, 8.0], dtype=np.float64),
        "sel_Jpsi_1_y": np.asarray([0.2, 0.2], dtype=np.float64),
        "sel_Jpsi_2_pt": np.asarray([8.0, 7.0], dtype=np.float64),
        "sel_Jpsi_2_y": np.asarray([-0.3, -0.3], dtype=np.float64),
        "sel_Phi_pt": np.asarray([7.0, 7.0], dtype=np.float64),
        "sel_Phi_y": np.asarray([0.1, 0.1], dtype=np.float64),
    }
    written = {}

    class FakeTree:
        def keys(self):
            return list(arrays)

        def arrays(self, branches, library):
            assert library == "np"
            return {branch: arrays[branch] for branch in branches}

    class FakeReader:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __contains__(self, name):
            return name == "selected"

        def __getitem__(self, name):
            assert name == "selected"
            return FakeTree()

    class FakeWriter:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __setitem__(self, name, value):
            written[name] = value

    monkeypatch.setattr(yc.uproot, "open", lambda path: FakeReader())
    monkeypatch.setattr(yc.uproot, "recreate", lambda path: FakeWriter())

    maps = {factor_name: _factor_frame(factor_name) for factor_name in FactorizedCorrectionMap.REQUIRED_FACTORS}
    correction_map = FactorizedCorrectionMap(maps, source="memory")
    summary = yc.build_factorized_weighted_mini_tree(tmp_path / "input.root", tmp_path / "weighted.root", correction_map)

    assert summary[:4] == (2, 2, 0, 0)
    assert "selected" in written
    assert written["selected"]["effcorr_status"].tolist() == [STATUS_OK, STATUS_OK]
    assert written["selected"]["effcorr_weight"].tolist() == [1.0, 1.0]
    assert written["selected"]["effcorr_efficiency"].tolist() == [1.0, 1.0]


def test_write_factorized_corrected_root_tree_preserves_selected_schema(tmp_path) -> None:
    import ROOT

    input_path = tmp_path / "selected.root"
    output_path = tmp_path / "selected_effcorr.root"

    root_file = ROOT.TFile(str(input_path), "RECREATE")
    tree = ROOT.TTree("selected", "selected")
    buffers = {
        "sel_Jpsi_1_mass": array.array("d", [3.1]),
        "sel_Jpsi_2_mass": array.array("d", [3.1]),
        "sel_Phi_mass": array.array("d", [1.02]),
        "sel_Jpsi_1_pt": array.array("d", [7.0]),
        "sel_Jpsi_1_y": array.array("d", [0.2]),
        "sel_Jpsi_2_pt": array.array("d", [8.0]),
        "sel_Jpsi_2_y": array.array("d", [-0.3]),
        "sel_Phi_pt": array.array("d", [7.0]),
        "sel_Phi_y": array.array("d", [0.1]),
        "sel_abs_dy_jpsi1_jpsi2": array.array("d", [0.5]),
    }
    for name, buffer in buffers.items():
        tree.Branch(name, buffer, f"{name}/D")
    tree.Fill()
    tree.Write()
    root_file.Close()

    maps = {factor_name: _factor_frame(factor_name) for factor_name in FactorizedCorrectionMap.REQUIRED_FACTORS}
    correction_map = FactorizedCorrectionMap(maps, source="memory")
    summary = write_factorized_corrected_root_tree(input_path, output_path, correction_map)

    assert summary[0] == 1
    assert summary[1] == 1
    out_file = ROOT.TFile.Open(str(output_path))
    out_tree = out_file.Get("selected")
    branches = {branch.GetName() for branch in out_tree.GetListOfBranches()}
    assert "sel_abs_dy_jpsi1_jpsi2" in branches
    assert "effcorr_weight" in branches
    assert "effcorr_fallback_components" in branches
    out_tree.GetEntry(0)
    assert out_tree.effcorr_status == STATUS_OK
    assert out_tree.effcorr_weight == 1.0
    assert out_tree.sel_abs_dy_jpsi1_jpsi2 == 0.5
    out_file.Close()

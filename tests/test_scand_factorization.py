from __future__ import annotations

import pandas as pd
import pytest

from efficiency_workflow.build_factorized_maps import build_factorized_maps_for_sample
from efficiency_workflow.scand_factorization import quantify_scand_factorization


def _write_sample(base_dir, sample: str) -> None:
    sample_dir = base_dir / sample
    sample_dir.mkdir(parents=True)
    keys = {
        "sample": [sample, sample],
        "source_file": ["a.root", "a.root"],
        "entry": [0, 1],
        "run": [1, 1],
        "lumi": [1, 1],
        "event": [11, 12],
    }
    gen_df = pd.DataFrame(
        {
            **keys,
            "jpsi_lead_pt": [7.0, 7.0],
            "jpsi_lead_y": [0.2, 0.2],
            "jpsi_sublead_pt": [6.5, 6.5],
            "jpsi_sublead_y": [-0.3, -0.3],
            "phi_pt": [5.0, 5.0],
            "phi_y": [0.1, 0.1],
        }
    )
    event_df = pd.DataFrame(
        {
            **keys,
            "full_gen": [1, 1],
            "jpsi_lead_fiducial": [1, 1],
            "jpsi_sublead_fiducial": [1, 1],
            "phi_fiducial": [1, 1],
            "jpsi_lead_muonRECO": [1, 1],
            "jpsi_sublead_muonRECO": [1, 0],
            "jpsi_lead_muonID": [1, 1],
            "jpsi_sublead_muonID": [1, 0],
            "jpsi_lead_dimuon": [1, 1],
            "jpsi_sublead_dimuon": [1, 0],
            "phi_kaonRECO": [1, 1],
            "phi_kaonID": [1, 1],
            "phi_dikaon": [1, 1],
            "s_cand": [1, 0],
            "hlt_muon_matched": [1, 0],
            "four_muon_vtx": [1, 0],
            "Pri_assocPVPass": [1, 0],
        }
    )
    gen_df.to_parquet(sample_dir / "gen_systems.parquet")
    event_df.to_parquet(sample_dir / "event_step_flags.parquet")
    build_factorized_maps_for_sample(sample_dir, sample_dir / "maps")


def test_quantify_scand_factorization_compares_bin_product(tmp_path) -> None:
    _write_sample(tmp_path, "JJP_TEST")

    outputs = quantify_scand_factorization(tmp_path, samples=["JJP_TEST"], output_dir=tmp_path / "diagnostic")

    stage_df = pd.read_parquet(outputs.stage_bins)
    scand_df = pd.read_parquet(outputs.scand_bins)
    assert outputs.manifest.exists()
    assert len(scand_df) == 1

    row = scand_df.iloc[0]
    assert row["stage"] == "quality"
    assert row["efficiency_name"] == "s_cand"
    assert row["n_full_gen"] == 2
    assert row["n_direct_passed"] == 1
    assert row["direct_efficiency"] == pytest.approx(0.5)
    assert row["product_efficiency_mean"] == pytest.approx(0.5625)
    assert row["direct_over_product"] == pytest.approx(0.5 / 0.5625)
    assert set(stage_df["stage"]) == {"fiducial", "reco", "id", "quality"}

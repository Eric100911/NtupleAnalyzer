from __future__ import annotations

import pandas as pd
import pytest

from efficiency_workflow.build_factorized_maps import build_factorized_maps_for_sample


def _merged_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = {
        "sample": ["JJP_TEST", "JJP_TEST"],
        "source_file": ["a.root", "a.root"],
        "entry": [0, 1],
        "run": [1, 1],
        "lumi": [1, 1],
        "event": [11, 12],
    }
    gen_df = pd.DataFrame(
        {
            **keys,
            "jpsi_lead_pt": [7.0, 12.0],
            "jpsi_lead_y": [0.2, -0.4],
            "jpsi_sublead_pt": [6.5, 8.0],
            "jpsi_sublead_y": [-0.3, 0.5],
            "phi_pt": [5.0, 7.0],
            "phi_y": [0.1, -0.2],
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
    return gen_df, event_df


def test_build_factorized_maps_uses_conditional_denominators(tmp_path) -> None:
    sample_dir = tmp_path / "JJP_TEST"
    sample_dir.mkdir()
    gen_df, event_df = _merged_inputs()
    gen_df.to_parquet(sample_dir / "gen_systems.parquet")
    event_df.to_parquet(sample_dir / "event_step_flags.parquet")

    written = build_factorized_maps_for_sample(sample_dir, sample_dir / "maps")

    assert set(written) >= {"acceptance_jpsi", "eff_muReco_jpsi", "eff_hlt", "eff_triOnia"}
    mu_reco = pd.read_parquet(written["eff_muReco_jpsi"])
    inclusive = mu_reco.loc[mu_reco["fallback_level"] == "inclusive"].iloc[0]
    assert inclusive["total"] == 4
    assert inclusive["passed"] == 3
    assert inclusive["efficiency"] == pytest.approx(0.75)

    hlt = pd.read_parquet(written["eff_hlt"])
    hlt_inclusive = hlt.loc[hlt["fallback_level"] == "inclusive"].iloc[0]
    assert hlt_inclusive["total"] == 1
    assert hlt_inclusive["passed"] == 1

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from efficiency_workflow.audit import (
    EventKey,
    build_factor_summary,
    build_no_trigger_summary,
    classify_memberships,
    evaluate_event_evidence,
    load_pipeline_events,
    render_markdown,
    select_examples,
    summarize_memberships,
    write_root_skims,
)
from efficiency_workflow.config import OfflineSelectionConfig
from efficiency_workflow.efficiency import EfficiencyBinning


V20_FIXTURE = Path("test_data/test_JpsiJpsiPhi_v2p0_patch1_numEvent118.root")
RUNB_FIXTURES = (
    Path("test_data/jjp_dps_patch2_pre2_runb_audit_source0_45events.root"),
    Path("test_data/jjp_dps_patch2_pre2_runb_audit_source1_35events.root"),
)
RUNB_MANIFEST = Path("test_data/jjp_dps_patch2_pre2_runb_audit.manifest.json")


def _identity(entry: int) -> dict[str, int | str]:
    return {
        "source_file": "synthetic.root",
        "entry": entry,
        "run": 1,
        "lumi": 2,
        "event": 100 + entry,
    }


def test_markdown_uses_step_scoped_transposed_example_tables():
    identity = _identity(7)
    evidence = {
        "identity": identity,
        "gen_system": {
            "jpsi_lead": {
                "idx": 3,
                "pdgId": 443,
                "pt": 12.5,
                "eta": 0.2,
                "y": 0.19,
                "mass": 3.0969,
                "daughter_indices": [4, 5],
            }
        },
        "map_bins": {
            "jpsi_lead": {
                "pt": 12.5,
                "y": 0.19,
                "pt_bin": 2,
                "signed_y_bin": 3,
                "abs_y_bin": 1,
            }
        },
        "recomputed_flags": {
            "full_gen": True,
            "jpsi_lead_fiducial": True,
            "jpsi_lead_muonRECO": False,
            "jpsi_lead_muonID": True,
        },
        "objects": {
            "jpsi_lead": {
                "fiducial": {
                    "passed": True,
                    "daughters": [{"gen_idx": 4, "pt": 4.2, "eta": 0.2, "passed": True}],
                },
                "reconstruction_and_id": {
                    "reco_passed": False,
                    "id_passed": True,
                    "daughters": [
                        {
                            "gen_daughter_idx": 4,
                            "matched_reco_indices": [],
                            "quality_matched_reco_indices": [],
                            "reco_objects": [],
                        }
                    ],
                },
                "single_candidates": [{"candidate_idx": 0, "witness": True}],
            }
        },
    }
    payload = {
        "n_full_gen_events": 1,
        "reference": "test",
        "issues": [],
        "summary": [],
        "factor_summary": [],
        "no_trigger_matching_summary": [],
        "coverage": [],
        "selections": {"jpsi_lead/muonRECO/rejected": [identity]},
        "selected_event_evidence": [evidence],
    }

    report = render_markdown(payload)

    assert "### `jpsi_lead / muonRECO / rejected`" in report
    assert "| Field | Event 1<br>`entry 7` |" in report
    assert "| `flags.muonRECO` | FAIL |" in report
    assert "| `selection.role` | rejected |" in report
    assert "reconstruction_and_id.daughters[0].matched_reco_indices" in report
    assert "quality_matched_reco_indices" not in report
    assert "single_candidates" not in report
    assert "```json" not in report


def _membership_frame() -> pd.DataFrame:
    rows = []
    for entry in range(3):
        row = {
            **_identity(entry),
            "full_gen": 1,
            "jpsi_lead_fiducial": (1, 0, 1)[entry],
            "jpsi_lead_muonRECO": (1, 1, 0)[entry],
            "jpsi_lead_muonID": (1, 1, 0)[entry],
            "jpsi_lead_dimuon": (1, 0, 0)[entry],
            "jpsi_sublead_fiducial": 0,
            "jpsi_sublead_muonRECO": 0,
            "jpsi_sublead_muonID": 0,
            "jpsi_sublead_dimuon": 0,
            "phi_fiducial": 0,
            "phi_kaonRECO": 0,
            "phi_kaonID": 0,
            "phi_dikaon": 0,
            "s_cand": (1, 1, 0)[entry],
            "hlt_event": (1, 0, 0)[entry],
            "hlt_muon_matched": (1, 0, 0)[entry],
            "four_muon_vtx": (1, 0, 0)[entry],
            "Pri_fitValid": (1, 0, 0)[entry],
            "Pri_fitPass": (1, 0, 0)[entry],
            "Pri_assocPVPass": (0, 0, 0)[entry],
            "Pri_trackPVPass": (1, 0, 0)[entry],
        }
        rows.append(row)
    return pd.DataFrame(rows)


def test_membership_semantics_keep_cumulative_and_adjacent_raw_separate():
    event_df = _membership_frame()
    memberships = classify_memberships(event_df)

    reco = memberships[
        (memberships["scope"] == "jpsi_lead") & (memberships["step"] == "muonRECO")
    ]
    assert int(reco["cumulative_denominator"].sum()) == 2
    assert int(reco["cumulative_numerator"].sum()) == 1
    assert int(reco["raw_only"].sum()) == 1

    muon_id = memberships[
        (memberships["scope"] == "jpsi_lead") & (memberships["step"] == "muonID")
    ]
    assert int(muon_id["cumulative_denominator"].sum()) == 1
    assert int(muon_id["cumulative_numerator"].sum()) == 1
    assert int(muon_id["adjacent_raw_denominator"].sum()) == 2
    assert int(muon_id["adjacent_raw_numerator"].sum()) == 2

    examples = select_examples(memberships, examples_per_category=5)
    assert examples["jpsi_lead/muonRECO/raw_only"][0].entry == 1
    assert examples["jpsi_lead/muonRECO/rejected"][0].entry == 2


def test_summary_detects_pipeline_hybrid_non_binomial_row():
    event_df = _membership_frame()
    memberships = classify_memberships(event_df)
    summary = summarize_memberships(memberships, event_df)
    row = summary[
        (summary["scope"] == "jpsi_lead") & (summary["step"] == "muonID")
    ].iloc[0]
    assert row["cumulative_total"] == 1
    assert row["adjacent_raw_total"] == 2
    assert row["pipeline_conditional_total"] == 1
    assert row["pipeline_conditional_passed"] == 2
    assert bool(row["pipeline_non_binomial"])


def test_factor_summary_uses_explicit_intersections():
    factors = build_factor_summary(_membership_frame())
    hlt = factors[factors["factor"] == "eff_hlt"].iloc[0]
    assert hlt["denominator_column"] == "s_cand"
    assert hlt["numerator_column"] == "hlt_muon_matched"
    assert hlt["total"] == 2
    assert hlt["passed"] == 1


def test_no_trigger_matching_chain_is_summary_only():
    frame = _membership_frame()
    frame["four_muon_vtx_noTrigMatch"] = [1, 1, 0]
    frame["Pri_fitValid_noTrigMatch"] = [1, 0, 0]
    frame["Pri_fitPass_noTrigMatch"] = [1, 1, 0]
    frame["Pri_assocPVPass_noTrigMatch"] = [0, 1, 0]
    frame["Pri_trackPVPass_noTrigMatch"] = [1, 0, 0]
    summary = build_no_trigger_summary(frame)
    four_muon = summary[summary["step"] == "four_muon_vtx_noTrigMatch"].iloc[0]
    assert four_muon["total"] == 1
    assert four_muon["passed"] == 1
    pri_valid = summary[summary["step"] == "Pri_fitValid_noTrigMatch"].iloc[0]
    assert pri_valid["total"] == 2
    assert pri_valid["passed"] == 1


def _fully_passing_event() -> dict:
    return {
        "MC_GenPart_pdgId": [443, 13, -13, 443, 13, -13, 333, 321, -321],
        "MC_GenPart_motherGenIdx": [-1, 0, 0, -1, 3, 3, -1, 6, 6],
        "MC_GenPart_pt": [12.0, 6.0, 6.0, 10.0, 5.0, 5.0, 6.0, 3.0, 3.0],
        "MC_GenPart_eta": [0.0] * 9,
        "MC_GenPart_mass": [3.0969, 0.105, 0.105, 3.0969, 0.105, 0.105, 1.019, 0.494, 0.494],
        "muGenMatchIdx": [1, 2, 4, 5],
        "muIsPatSoftMuon": [1, 1, 1, 1],
        "muVertexId": [7, 7, 7, 7],
        "muJpsiMatchedTriggerIndices": [[1], [1], [], []],
        "muJpsiMatchedFilterIndices": [[1], [1], [], []],
        "SingleJpsi_mass": [3.10, 3.11],
        "SingleJpsi_pt": [12.0, 10.0],
        "SingleJpsi_y": [0.0, 0.0],
        "SingleJpsi_VtxProb": [0.5, 0.4],
        "SingleJpsi_fitValid": [1, 1],
        "SingleJpsi_fitPass": [1, 1],
        "SingleJpsi_mu1_genMatchIdx": [1, 4],
        "SingleJpsi_mu2_genMatchIdx": [2, 5],
        "RecoKaonTrack_genMatchIdx": [7, 8],
        "RecoKaonTrack_normalizedChi2": [1.0, 1.0],
        "RecoKaonTrack_numberOfHits": [10, 11],
        "RecoKaonTrack_isHighPurity": [1, 1],
        "SinglePhi_mass": [1.02],
        "SinglePhi_pt": [6.0],
        "SinglePhi_y": [0.0],
        "SinglePhi_VtxProb": [0.3],
        "SinglePhi_fitValid": [1],
        "SinglePhi_fitPass": [1],
        "SinglePhi_K1_genMatchIdx": [7],
        "SinglePhi_K2_genMatchIdx": [8],
        "Jpsi_1_mass": [3.10],
        "Jpsi_1_mu_1_Idx": [0],
        "Jpsi_1_mu_2_Idx": [1],
        "Jpsi_2_mu_1_Idx": [2],
        "Jpsi_2_mu_2_Idx": [3],
        "Phi_K_1_genMatchIdx": [7],
        "Phi_K_2_genMatchIdx": [8],
        "Pri_fitValid": [1],
        "Pri_fitPass": [1],
        "Pri_assocPVPass": [1],
        "Pri_trackPVPass": [1],
        "DiOnia_fitValid": [1],
        "DiOnia_fitPass": [1],
        "TrigNames": ["HLT_DoubleMu4_3_LowMass_v1"],
        "TrigRes": [1],
    }


def test_branch_evidence_rebuilds_full_event_chain_and_witness():
    event = _fully_passing_event()
    raw_columns = [
        "jpsi_lead_fiducial",
        "jpsi_lead_muonRECO",
        "jpsi_lead_muonID",
        "jpsi_lead_dimuon",
        "jpsi_sublead_fiducial",
        "jpsi_sublead_muonRECO",
        "jpsi_sublead_muonID",
        "jpsi_sublead_dimuon",
        "phi_fiducial",
        "phi_kaonRECO",
        "phi_kaonID",
        "phi_dikaon",
        "full_gen",
        "s_cand",
        "hlt_event",
        "hlt_muon_matched",
        "four_muon_vtx",
        "Pri_fitValid",
        "Pri_fitPass",
        "Pri_assocPVPass",
        "Pri_trackPVPass",
    ]
    pipeline_row = {**_identity(0), **{column: 1 for column in raw_columns}}
    evidence = evaluate_event_evidence(
        event,
        pipeline_row,
        cfg=OfflineSelectionConfig(),
        binning=EfficiencyBinning(),
        trigger_filter_map={
            "dimuon0_trig": 0,
            "dimuon0_filt": 0,
            "doublemu_trig": 1,
            "doublemu_filt": 1,
        },
    )
    assert evidence["mismatched_flags"] == []
    assert evidence["recomputed_flags"]["s_cand"]
    assert evidence["recomputed_flags"]["Pri_assocPVPass"]
    candidate = evidence["composite_candidates"][0]
    assert candidate["triple_gen_matched"]
    assert candidate["trigger_match"]["passed"]
    assert candidate["stages"]["four_muon_vtx"]
    assert candidate["DiOnia_context"]["DiOnia_fitValid"] == 1


@pytest.mark.skipif(not V20_FIXTURE.exists(), reason="v2.0 audit fixture is absent")
def test_real_fixture_baseline_and_branch_recomputation():
    _, event_df, source_info = load_pipeline_events(
        [V20_FIXTURE],
        cfg=OfflineSelectionConfig(),
        max_events=118,
    )
    assert len(event_df) == 15
    assert int(event_df["s_cand"].sum()) == 0
    assert int(event_df["jpsi_lead_fiducial"].sum()) == 4
    assert int(event_df["phi_kaonRECO"].sum()) == 12

    memberships = classify_memberships(event_df)
    summary = summarize_memberships(memberships, event_df)
    assert int(summary["pipeline_non_binomial"].fillna(False).sum()) == 3

    from efficiency_workflow.audit import load_selected_evidence

    selected = [
        EventKey(
            source_file=str(V20_FIXTURE),
            entry=40,
            run=1,
            lumi=1,
            event=41,
        )
    ]
    evidence = load_selected_evidence(
        event_df,
        selected,
        source_info,
        cfg=OfflineSelectionConfig(),
        binning=EfficiencyBinning(),
    )
    assert len(evidence) == 1
    assert evidence[0]["mismatched_flags"] == []
    assert evidence[0]["objects"]["jpsi_lead"]["fiducial"]["passed"]
    assert evidence[0]["objects"]["jpsi_lead"]["single_candidates"][0]["witness"]


@pytest.mark.skipif(not V20_FIXTURE.exists(), reason="v2.0 audit fixture is absent")
def test_root_skim_preserves_complete_tree(tmp_path):
    import uproot

    _, event_df, source_info = load_pipeline_events(
        [V20_FIXTURE],
        cfg=OfflineSelectionConfig(),
        max_events=118,
    )
    row = event_df[event_df["entry"] == 40].iloc[0]
    selected = [
        EventKey(
            source_file=str(V20_FIXTURE),
            entry=40,
            run=int(row["run"]),
            lumi=int(row["lumi"]),
            event=int(row["event"]),
        )
    ]
    records = write_root_skims(selected, source_info, tmp_path)
    assert len(records) == 1
    with (
        uproot.open(records[0]["output_file"], handler=uproot.source.file.MemmapSource) as skim,
        uproot.open(V20_FIXTURE, handler=uproot.source.file.MemmapSource) as source,
    ):
        skim_tree = skim["mkcands/X_data"]
        source_tree = source["mkcands/X_data"]
        assert skim_tree.num_entries == 1
        assert skim_tree.keys() == source_tree.keys()
        assert "mkcands/X_config" in skim
        assert skim_tree["evtNum"].array(library="np")[0] == row["event"]


@pytest.mark.skipif(
    not all(path.exists() for path in RUNB_FIXTURES),
    reason="Run-B audit fixtures are absent",
)
def test_runb_fixtures_cover_event_level_numerators_and_rejections():
    _, event_df, source_info = load_pipeline_events(
        RUNB_FIXTURES,
        cfg=OfflineSelectionConfig(),
    )
    assert len(event_df) == 80
    assert {Path(path).name: count for path, count in event_df.groupby("source_file").size().items()} == {
        RUNB_FIXTURES[0].name: 45,
        RUNB_FIXTURES[1].name: 35,
    }
    assert {
        step: int(event_df[step].sum())
        for step in (
            "s_cand",
            "hlt_event",
            "hlt_muon_matched",
            "four_muon_vtx",
            "Pri_fitValid",
            "Pri_fitPass",
            "Pri_assocPVPass",
            "Pri_trackPVPass",
        )
    } == {
        "s_cand": 13,
        "hlt_event": 8,
        "hlt_muon_matched": 7,
        "four_muon_vtx": 7,
        "Pri_fitValid": 7,
        "Pri_fitPass": 7,
        "Pri_assocPVPass": 5,
        "Pri_trackPVPass": 7,
    }
    memberships = classify_memberships(event_df)
    rejected = {
        step: int(
            memberships[
                (memberships["scope"] == "event") & (memberships["step"] == step)
            ]["rejected"].sum()
        )
        for step in ("s_cand", "hlt_event", "hlt_muon_matched", "four_muon_vtx")
    }
    assert rejected == {
        "s_cand": 67,
        "hlt_event": 5,
        "hlt_muon_matched": 1,
        "four_muon_vtx": 0,
    }
    assert all(
        info["trigger_filter_map"]
        == {
            "dimuon0_trig": 0,
            "doublemu_trig": 1,
            "dimuon0_filt": 0,
            "doublemu_filt": 1,
        }
        for info in source_info.values()
    )


@pytest.mark.skipif(
    not RUNB_MANIFEST.exists() or not all(path.exists() for path in RUNB_FIXTURES),
    reason="Run-B audit fixture manifest is absent",
)
def test_runb_fixture_manifest_hashes_and_tree_contract():
    import uproot

    manifest = json.loads(RUNB_MANIFEST.read_text())
    assert manifest["selection"]["unique_selected_events"] == 80
    assert manifest["tree_contract"]["data_branch_count"] == 480
    by_name = {item["path"]: item for item in manifest["files"]}
    for path in RUNB_FIXTURES:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == by_name[path.name]["sha256"]
        with uproot.open(path, handler=uproot.source.file.MemmapSource) as root_file:
            assert len(root_file["mkcands/X_data"].keys()) == 480
            assert root_file["mkcands/X_data"].num_entries == by_name[path.name]["selected_entries"]
            assert "mkcands/X_config" in root_file
            assert "mkcands/X_lhe_run_info" in root_file

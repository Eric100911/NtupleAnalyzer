from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import awkward as ak
import pandas as pd
import pytest
import uproot

from efficiency_workflow.cli_efficiency import apply_manifest_coverage
from efficiency_workflow.config import (
    DEFAULT_TRIGGER_REQUIREMENTS,
    OfflineSelectionConfig,
    load_efficiency_definition,
)
from efficiency_workflow.efficiency import (
    _count_retained_candidate_events,
    process_efficiency_file,
    process_efficiency_file_vectorized,
)
from efficiency_workflow.tps_input import (
    detect_tree_path,
    resolve_input_context,
    resolve_trigger_requirements,
    validate_production_config,
)


RUNB_FIXTURE = Path("test_data/jjp_dps_patch2_pre2_runb_audit_source0_45events.root")
TPS_CONFIG = Path("configs/efficiency/tps_nominal.yaml")


def test_tps_yaml_loads_with_stable_nominal_contract() -> None:
    definition = load_efficiency_definition(TPS_CONFIG)
    assert definition.schema_version == "ntuple-analyzer-efficiency/v1"
    assert definition.event_endpoint == "Pri_assocPVPass"
    assert definition.config_hash
    assert [item.rule for item in definition.trigger_requirements] == [
        "three_muons_with_dimuon_pair",
        "dimuon_pair",
    ]


def test_tree_layout_detection_supports_top_level_and_wrapped() -> None:
    assert detect_tree_path({"X_data": object()}, "auto") == "X_data"
    assert detect_tree_path({"mkcands/X_data": object()}, "auto") == "mkcands/X_data"
    with pytest.raises(KeyError, match="exactly one"):
        detect_tree_path({"X_data": object(), "mkcands/X_data": object()}, "auto")


def test_trigger_indices_are_derived_from_reordered_xconfig() -> None:
    config = {
        "TriggersForJpsi": [
            "HLT_DoubleMu4_3_LowMass_v",
            "HLT_Dimuon0_Jpsi3p5_Muon2_v",
        ],
        "FiltersForJpsi": [
            "hltDoubleMu43LowMassL3Filtered",
            "hltJpsiMuonL3Filtered3p5",
        ],
    }
    resolved = resolve_trigger_requirements(config, DEFAULT_TRIGGER_REQUIREMENTS)
    assert {item.key: (item.trigger_index, item.filter_index) for item in resolved} == {
        "dimuon0": (1, 1),
        "doublemu": (0, 0),
    }


def test_numeric_production_compatibility_fails_only_direct_impossibility() -> None:
    definition = load_efficiency_definition(TPS_CONFIG)
    production = {
        "KeepAllSingleObjectCandsInMC": True,
        "SkipCompositeCandBuildingWhenKeepingSingles": False,
        "RequireAcceptedCandidatesForMonteCarloTree": False,
        "JpsiMassMin": 2.8,
        "JpsiMassMax": 3.3,
        "PhiMassMin": 0.9,
        "PhiMassMax": 1.1,
        "TrackPtMin": 1.0,
        "AnalysisMode": "JpsiJpsiPhi",
    }
    assert validate_production_config(production, definition) == []
    with pytest.raises(ValueError, match="track pT"):
        validate_production_config({**production, "TrackPtMin": 2.5}, definition)


def test_retained_candidate_count_uses_pri_pass_any() -> None:
    arrays = ak.Array({
        "Pri_passAny": [[], [0], [1, 0], [0, 1]],
        "Jpsi_1_mass": [[], [3.1], [], []],
    })
    assert _count_retained_candidate_events(arrays) == 2


@pytest.mark.skipif(not RUNB_FIXTURE.exists(), reason="Run-B integration fixture is absent")
def test_strict_context_and_backend_parity_on_real_runb_fixture() -> None:
    definition = load_efficiency_definition(TPS_CONFIG)
    with uproot.open(RUNB_FIXTURE) as root_file:
        context = resolve_input_context(root_file, "auto", definition, strict=True)
    assert context.data_tree_path == "mkcands/X_data"
    assert context.config_tree_path == "mkcands/X_config"

    vectorized = process_efficiency_file_vectorized(
        str(RUNB_FIXTURE),
        "JJP_TPS",
        definition.offline_selection,
        definition=definition,
        config_policy="strict",
    )
    loop = process_efficiency_file(
        str(RUNB_FIXTURE),
        "JJP_TPS",
        definition.offline_selection,
        definition=definition,
        config_policy="strict",
    )
    pd.testing.assert_frame_equal(vectorized["gen_systems"], loop["gen_systems"])
    pd.testing.assert_frame_equal(vectorized["event_step_flags"], loop["event_step_flags"])
    event = vectorized["event_step_flags"]
    assert (event["Pri_assocPVPass"] <= event["four_muon_vtx"]).all()
    assert {
        "four_muon_vtx_legacy_muVertexId",
        "four_muon_vtx_commonRecVtxPass",
        "four_muon_vtx_passAny",
        "four_muon_vtx_vtxprob",
    }.issubset(event.columns)


def _coverage_tables() -> dict:
    return {
        "file_coverage": pd.DataFrame([
            {
                "source_file": "/tmp/a.root",
                "entries_scanned": 10,
                "retained_candidate_events": 2,
                "full_gen_events": 4,
                "compatibility_hash": "production",
                "efficiency_config_hash": "analysis",
            }
        ])
    }


def test_manifest_coverage_marks_intentional_subset_partial() -> None:
    tables = _coverage_tables()
    manifest = {
        "sample": "JJP_TPS",
        "n_files": 1,
        "master_n_files": 317,
        "master_manifest_id": "master",
        "inventory": [{
            "source_file": "/tmp/a.root",
            "total_entries": 10,
            "retained_candidate_events": 2,
        }],
    }
    apply_manifest_coverage(tables, "JJP_TPS", manifest)
    assert tables["coverage_summary"]["coverage_scope"] == "partial"
    assert tables["coverage_summary"]["master_n_files"] == 317


def test_manifest_coverage_rejects_count_mismatch() -> None:
    tables = _coverage_tables()
    manifest = {
        "sample": "JJP_TPS",
        "inventory": [{
            "source_file": "/tmp/a.root",
            "total_entries": 11,
            "retained_candidate_events": 2,
        }],
    }
    with pytest.raises(RuntimeError, match="Inventory count mismatch"):
        apply_manifest_coverage(tables, "JJP_TPS", manifest)

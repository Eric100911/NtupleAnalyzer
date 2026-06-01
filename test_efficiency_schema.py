#!/usr/bin/env python3
"""Unit tests for efficiency pipeline schema (per-object step decomposition).

Usage:
    source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
    python3 -m pytest test_efficiency_schema.py -v
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from efficiency_workflow.config import OfflineSelectionConfig
from efficiency_workflow.efficiency import (
    EVENT_STEPS,
    PER_JPSI_STEPS,
    PER_PHI_STEPS,
    DERIVED_FLAGS,
    EVENT_STEP_PREVIOUS,
    PAIR_LEVEL_MAP_SPECS,
    per_object_step_columns,
    _process_efficiency_chunk_vectorized,
    process_efficiency_file,
    EFFICIENCY_BRANCHES,
    EfficiencyBinning,
)


class TestStepDefinitions:
    def test_per_object_step_columns_count(self):
        cols = per_object_step_columns()
        assert len(cols) == 12, f"Expected 12 per-object columns, got {len(cols)}: {cols}"

    def test_per_object_step_columns_names(self):
        cols = per_object_step_columns()
        expected = [
            "jpsi_lead_fiducial", "jpsi_lead_muonRECO", "jpsi_lead_muonID", "jpsi_lead_dimuon",
            "jpsi_sublead_fiducial", "jpsi_sublead_muonRECO", "jpsi_sublead_muonID", "jpsi_sublead_dimuon",
            "phi_fiducial", "phi_kaonRECO", "phi_kaonID", "phi_dikaon",
        ]
        assert cols == expected

    def test_event_steps_order(self):
        expected = (
            "hlt_event", "hlt_muon_matched", "four_muon_vtx",
            "Pri_fitValid", "Pri_fitPass", "Pri_assocPVPass",
            "Pri_trackPVPass",
        )
        assert EVENT_STEPS == expected

    def test_event_steps_no_duplicates(self):
        assert len(EVENT_STEPS) == len(set(EVENT_STEPS))

    def test_event_level_parallel_denominators(self):
        assert EVENT_STEP_PREVIOUS["hlt_event"] == "s_cand"
        assert EVENT_STEP_PREVIOUS["hlt_muon_matched"] == "hlt_event"
        assert EVENT_STEP_PREVIOUS["four_muon_vtx"] == "hlt_muon_matched"
        for step in ("Pri_fitValid", "Pri_fitPass", "Pri_assocPVPass", "Pri_trackPVPass"):
            assert EVENT_STEP_PREVIOUS[step] == "four_muon_vtx"

    def test_pair_level_map_specs(self):
        by_step = {spec.step: spec for spec in PAIR_LEVEL_MAP_SPECS}
        assert by_step["four_muon_vtx"].denominator_col == "hlt_muon_matched"
        for step in ("Pri_fitValid", "Pri_fitPass", "Pri_assocPVPass", "Pri_trackPVPass"):
            assert by_step[step].denominator_col == "four_muon_vtx"

    def test_per_jpsi_steps_no_duplicates(self):
        assert len(PER_JPSI_STEPS) == len(set(PER_JPSI_STEPS))

    def test_per_phi_steps_no_duplicates(self):
        assert len(PER_PHI_STEPS) == len(set(PER_PHI_STEPS))

    def test_step_groups_disjoint(self):
        """No overlap between per-object step suffixes and event step names."""
        all_per_obj = set(PER_JPSI_STEPS) | set(PER_PHI_STEPS)
        event_set = set(EVENT_STEPS)
        overlap = all_per_obj & event_set
        assert not overlap, f"Overlap between per-object and event steps: {overlap}"

    def test_derived_flags(self):
        assert DERIVED_FLAGS == ("full_gen", "s_cand")

    def test_per_jpsi_chain_order(self):
        """Acceptance must be first; the rest must be conditional on previous."""
        assert PER_JPSI_STEPS[0] == "fiducial"
        assert PER_JPSI_STEPS == ("fiducial", "muonRECO", "muonID", "dimuon")

    def test_per_phi_chain_order(self):
        assert PER_PHI_STEPS[0] == "fiducial"
        assert PER_PHI_STEPS == ("fiducial", "kaonRECO", "kaonID", "dikaon")


# ── Integration tests (require a single ROOT file) ──

NTUPLE = (
    "root://cceos.ihep.ac.cn/"
    "///eos/ihep/cms/store/user/xcheng/MC_Production_v3/output/"
    "JJP_DPS2_CS/0/output_ntuple.root:mkcands/X_data"
)


def _load_chunk():
    """Load one chunk from the test ntuple. Returns empty dict on failure."""
    if os.environ.get("RUN_REMOTE_EFFICIENCY_TESTS") != "1":
        return {}
    import uproot
    try:
        arrays = uproot.iterate(NTUPLE, filter_name=list(EFFICIENCY_BRANCHES),
                                library="ak", step_size="50 MB")
        for chunk, _report in arrays:
            return chunk
    except Exception:
        pass
    return {}


@pytest.fixture(scope="module")
def efficiency_result():
    """Process one chunk with vectorized backend, return DataFrames."""
    chunk = _load_chunk()
    if not chunk:
        pytest.skip("Cannot access test ntuple")
    cfg = OfflineSelectionConfig()
    result = _process_efficiency_chunk_vectorized(chunk, NTUPLE, "test_sample", cfg, 0)
    return result


@pytest.fixture(scope="module")
def python_loop_result():
    """Process one chunk with python-loop backend."""
    if os.environ.get("RUN_REMOTE_EFFICIENCY_TESTS") != "1":
        return {}
    try:
        import uproot
        arrays = uproot.iterate(NTUPLE, filter_name=list(EFFICIENCY_BRANCHES),
                                library="ak", step_size="50 MB")
        for chunk, _report in arrays:
            cfg = OfflineSelectionConfig()
            return process_efficiency_file_chunk(chunk, NTUPLE, "test_sample", cfg)
    except Exception:
        pass
    return {}


def process_efficiency_file_chunk(chunk, path, sample, cfg):
    """Process a single uproot chunk through the python-loop backend."""
    n_events = len(chunk["evtNum"])
    gen_rows, event_rows = [], []
    for entry in range(n_events):
        from efficiency_workflow.efficiency import _pythonize_event, build_event_efficiency_row
        event = _pythonize_event(chunk, entry)
        gen_row, event_row = build_event_efficiency_row(event, path, sample, entry, cfg)
        if gen_row is not None and event_row is not None:
            gen_rows.append(gen_row)
            event_rows.append(event_row)
    return {
        "gen_systems": pd.DataFrame(gen_rows),
        "event_step_flags": pd.DataFrame(event_rows),
    }


class TestPerObjectData:
    """Integration tests on real data from the vectorized backend."""

    def test_per_object_columns_exist(self, efficiency_result):
        event_df = efficiency_result["event_step_flags"]
        if event_df.empty:
            pytest.skip("No events in test chunk")
        for col in per_object_step_columns():
            assert col in event_df.columns, f"Missing column: {col}"

    def test_per_object_values_are_0_or_1(self, efficiency_result):
        event_df = efficiency_result["event_step_flags"]
        if event_df.empty:
            pytest.skip("No events")
        for col in per_object_step_columns():
            vals = event_df[col].unique()
            assert set(vals) <= {0, 1}, f"{col} has values {set(vals)}"

    def test_s_cand_column_exists(self, efficiency_result):
        event_df = efficiency_result["event_step_flags"]
        if event_df.empty:
            pytest.skip("No events")
        assert "s_cand" in event_df.columns

    def test_s_cand_implies_all_per_object(self, efficiency_result):
        event_df = efficiency_result["event_step_flags"]
        if event_df.empty:
            pytest.skip("No events")
        s_cand_true = event_df[event_df["s_cand"] == 1]
        if len(s_cand_true) == 0:
            pytest.skip("No s_cand events in test chunk")
        for col in per_object_step_columns():
            assert (s_cand_true[col] == 1).all(), f"s_cand=1 but {col} has zeros"

    def test_pri_fitPass_implies_four_muon(self, efficiency_result):
        event_df = efficiency_result["event_step_flags"]
        if event_df.empty:
            pytest.skip("No events")
        pf_true = event_df[event_df["Pri_fitPass"] == 1]
        if len(pf_true) == 0:
            pytest.skip("No Pri_fitPass events")
        assert (pf_true["four_muon_vtx"] == 1).all()

    def test_gen_score_matches_formula(self, efficiency_result):
        gen_df = efficiency_result["gen_systems"]
        if gen_df.empty:
            pytest.skip("No events")
        expected = gen_df["jpsi_lead_pt"]**2 + gen_df["jpsi_sublead_pt"]**2 + gen_df["phi_pt"]**2
        assert np.allclose(gen_df["gen_score"], expected, rtol=1e-10)

    def test_new_columns_no_nan(self, efficiency_result):
        """Per-object step flags should not have NaN (they are int8)."""
        event_df = efficiency_result["event_step_flags"]
        if event_df.empty:
            pytest.skip("No events")
        for col in per_object_step_columns():
            assert not event_df[col].isna().any(), f"{col} has NaN"
        for col in ("s_cand", "full_gen", "hlt_event", "hlt_muon_matched",
                     "four_muon_vtx", "four_muon_vtx_noTrigMatch",
                     "Pri_fitValid", "Pri_fitValid_noTrigMatch",
                     "Pri_fitPass", "Pri_fitPass_noTrigMatch",
                     "Pri_assocPVPass", "Pri_assocPVPass_noTrigMatch",
                     "Pri_trackPVPass", "Pri_trackPVPass_noTrigMatch"):
            assert col in event_df.columns
            assert not event_df[col].isna().any(), f"{col} has NaN"

    def test_old_cumulative_columns_not_present(self, efficiency_result):
        event_df = efficiency_result["event_step_flags"]
        if event_df.empty:
            pytest.skip("No events")
        removed = {"single_jpsi_reco", "double_jpsi_reco", "single_phi_reco",
                    "jpsi_quality", "phi_quality", "all6_same_recVtx",
                    "fiducial_acceptance",
                    "triple_gen_matched_candidate"}
        for col in removed:
            assert col not in event_df.columns, f"Old column {col} should not be present"

    def test_event_level_columns_exist(self, efficiency_result):
        event_df = efficiency_result["event_step_flags"]
        if event_df.empty:
            pytest.skip("No events")
        for col in ("full_gen", "s_cand", "hlt_event", "hlt_muon_matched",
                     "four_muon_vtx", "four_muon_vtx_noTrigMatch",
                     "Pri_fitValid", "Pri_fitPass",
                     "Pri_assocPVPass", "Pri_trackPVPass"):
            assert col in event_df.columns, f"Missing event column: {col}"


class TestBackendEquality:
    """Verify both backends produce identical output."""

    def test_backends_same_gen_systems(self, efficiency_result, python_loop_result):
        gen_v = efficiency_result.get("gen_systems", pd.DataFrame())
        gen_p = python_loop_result.get("gen_systems", pd.DataFrame())
        if gen_v.empty or gen_p.empty:
            pytest.skip("No data from one or both backends")
        # Compare kinematic columns (ignore entry/source_file)
        kin_cols = [c for c in gen_v.columns if c not in ("entry", "source_file", "sample")]
        assert len(gen_v) == len(gen_p)
        for col in kin_cols:
            if col in gen_p.columns:
                assert np.allclose(gen_v[col].values, gen_p[col].values, rtol=1e-10, equal_nan=True), \
                    f"gen.{col} differs between backends"

    def test_backends_same_step_flags(self, efficiency_result, python_loop_result):
        evt_v = efficiency_result.get("event_step_flags", pd.DataFrame())
        evt_p = python_loop_result.get("event_step_flags", pd.DataFrame())
        if evt_v.empty or evt_p.empty:
            pytest.skip("No data from one or both backends")
        assert len(evt_v) == len(evt_p)
        common_cols = [c for c in evt_v.columns if c in evt_p.columns
                       and c not in ("entry", "source_file", "sample")]
        for col in common_cols:
            same = (evt_v[col].values == evt_p[col].values)
            assert same.all(), f"event.{col} differs: {int((~same).sum())}/{len(same)} rows"

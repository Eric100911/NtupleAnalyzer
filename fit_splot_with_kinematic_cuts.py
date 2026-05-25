#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply configurable kinematic cuts before RooFit + SPlot, and only keep passing events."""

from __future__ import annotations

import argparse
import os
import sys
from collections import OrderedDict

import ROOT
import uproot

import fit_splot as fit_core
from ntuple_pipeline_common import (
    MUON_ID_BRANCHES,
    OUTPUT_BASE,
    build_root_string_vector,
    declare_rdf_helpers,
    default_merged_output,
    default_plot_dir,
    default_weighted_output,
    ensure_dir,
    ensure_parent_dir,
    get_tree_branches,
    normalize_channel,
    normalize_dataset,
    normalize_sample,
)


INPUT_TREE = "selected"

# =============================================================================
# Editable pre-fit cut configuration
# Set a threshold to None to disable that cut.
# Trigger matching uses the selected muons:
#   0 -> disable
#   1 -> require at least one matched muon for that resonance
#   2 -> require both matched muons for that resonance
# =============================================================================

COMMON_CUTS = {
    "muon_pt_min": None,
    "track_pt_min": 2.0,
    "track_misuse_dr_max": 0.005,
    "track_misuse_relpt_max": 0.01,
    "phi_pt_min": 4.0,
    "phi_abs_eta_max": 2.5,
    "phi_vtxprob_min": 0.01,
    "phi_ctau_min": None,
    "phi_ctau_max": None,
    "pri_vtxprob_min": None,
    "require_pri_assocpv_pass": True,
    "require_phi_common_assocpv_pass": False,
    "require_kaon_has_assocpv": False,
    "assocpv_idx_min": None,
    "assocpv_idx_max": None,
    "pri_max_abs_dzpv": None,
    "pri_max_abs_dxypv": None,
    "track_max_abs_dz_assocpv": None,
    "track_max_abs_dxy_assocpv": None,
}

JJP_CUTS = {
    "muon_id": "soft",
    "jpsi_trigger_min_matched_muons": 0,
    "jpsi_pt_min": 6.0,
    "jpsi_abs_eta_max": 2.5,
    "jpsi_vtxprob_min": 0.01,
    "jpsi_ctau_min": None,
    "jpsi_ctau_max": None,
}

JYP_CUTS = {
    "jpsi_muon_id": "soft",
    "ups_muon_id": "tight",
    "jpsi_trigger_min_matched_muons": 0,
    "ups_trigger_min_matched_muons": 0,
    "jpsi_pt_min": 6.0,
    "jpsi_abs_eta_max": 2.5,
    "jpsi_vtxprob_min": 0.01,
    "jpsi_ctau_min": None,
    "jpsi_ctau_max": None,
    "ups_pt_min": None,
    "ups_abs_eta_max": 2.5,
    "ups_vtxprob_min": 0.01,
    "ups_ctau_min": None,
    "ups_ctau_max": None,
}


_PREFIT_HELPERS_DECLARED = False


def parse_args():
    parser = argparse.ArgumentParser(description="Apply pre-fit kinematic cuts, then run RooFit + SPlot")
    parser.add_argument("--channel", required=True, choices=["JJP", "JYP", "jjp", "jyp"])
    parser.add_argument("--dataset", default="data", choices=["data", "mc"])
    parser.add_argument("--sample", default=None, help="MC sample tag")
    parser.add_argument("-i", "--input", default=None, help="Input selected ROOT file")
    parser.add_argument("-o", "--output", default=None, help="Output ROOT file with sWeights")
    parser.add_argument("--filtered-output", default=None, help="Output ROOT file containing only events that pass the pre-fit cuts")
    parser.add_argument("--plot-dir", default=None, help="Directory for fit projections")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="RDataFrame / RooFit NumCPU")
    parser.add_argument("-n", "--max-events", type=int, default=-1, help="Limit events for quick tests")
    return parser.parse_args()


def default_filtered_output(weighted_output: str) -> str:
    if weighted_output.endswith(".root"):
        return weighted_output[:-5] + "_prefit_selected.root"
    return weighted_output + "_prefit_selected.root"


def declare_prefit_helpers():
    global _PREFIT_HELPERS_DECLARED
    if _PREFIT_HELPERS_DECLARED:
        return

    ROOT.gInterpreter.Declare(
        r"""
        #include <cmath>
        #include "ROOT/RVec.hxx"

        using ROOT::VecOps::RVec;

        template <typename T>
        int TakeMask(const RVec<T>& values, int idx) {
            if (idx < 0 || idx >= static_cast<int>(values.size())) {
                return 0;
            }
            return values[idx] ? 1 : 0;
        }

        template <typename T>
        int CountSelectedMatches2(const RVec<T>& values, int idx1, int idx2) {
            return TakeMask(values, idx1) + TakeMask(values, idx2);
        }

        template <typename T>
        int CountSelectedMatches4(const RVec<T>& values, int idx1, int idx2, int idx3, int idx4) {
            return TakeMask(values, idx1) + TakeMask(values, idx2) + TakeMask(values, idx3) + TakeMask(values, idx4);
        }

        float RelPtDiff(float pt1, float pt2) {
            if (pt1 <= 0.f) {
                return 1.0e9f;
            }
            return std::fabs(pt1 - pt2) / pt1;
        }

        bool PassTrackMisuseVetoJJP(
            float mu1_pt, float mu1_eta, float mu1_phi,
            float mu2_pt, float mu2_eta, float mu2_phi,
            float mu3_pt, float mu3_eta, float mu3_phi,
            float mu4_pt, float mu4_eta, float mu4_phi,
            float k1_pt, float k1_eta, float k1_phi,
            float k2_pt, float k2_eta, float k2_phi,
            float dr_max, float relpt_max
        ) {
            const float mu_pt[4] = {mu1_pt, mu2_pt, mu3_pt, mu4_pt};
            const float mu_eta[4] = {mu1_eta, mu2_eta, mu3_eta, mu4_eta};
            const float mu_phi[4] = {mu1_phi, mu2_phi, mu3_phi, mu4_phi};
            const float k_pt[2] = {k1_pt, k2_pt};
            const float k_eta[2] = {k1_eta, k2_eta};
            const float k_phi[2] = {k1_phi, k2_phi};

            for (int i = 0; i < 4; ++i) {
                for (int j = 0; j < 2; ++j) {
                    const float deta = mu_eta[i] - k_eta[j];
                    const float dphi = DeltaPhiAbs(mu_phi[i], k_phi[j]);
                    const float dr = std::sqrt(deta * deta + dphi * dphi);
                    if (dr < dr_max && RelPtDiff(mu_pt[i], k_pt[j]) < relpt_max) {
                        return false;
                    }
                }
            }
            return true;
        }

        bool PassTrackMisuseVetoJYP(
            float mu1_pt, float mu1_eta, float mu1_phi,
            float mu2_pt, float mu2_eta, float mu2_phi,
            float mu3_pt, float mu3_eta, float mu3_phi,
            float mu4_pt, float mu4_eta, float mu4_phi,
            float k1_pt, float k1_eta, float k1_phi,
            float k2_pt, float k2_eta, float k2_phi,
            float dr_max, float relpt_max
        ) {
            return PassTrackMisuseVetoJJP(
                mu1_pt, mu1_eta, mu1_phi,
                mu2_pt, mu2_eta, mu2_phi,
                mu3_pt, mu3_eta, mu3_phi,
                mu4_pt, mu4_eta, mu4_phi,
                k1_pt, k1_eta, k1_phi,
                k2_pt, k2_eta, k2_phi,
                dr_max, relpt_max
            );
        }
        """
    )
    _PREFIT_HELPERS_DECLARED = True


def add_filter(filters, warnings, available, expression: str | None, label: str, required_branches):
    if expression is None:
        return
    missing = [branch for branch in required_branches if branch not in available]
    if missing:
        warnings.append(f"[WARN] skip {label}: missing branches {', '.join(missing)}")
        return
    filters.append((label, expression))


def range_expression(branch: str, min_value=None, max_value=None, abs_value: bool = False):
    pieces = []
    target = f"std::abs({branch})" if abs_value else branch
    if min_value is not None:
        pieces.append(f"{target} >= {float(min_value)}")
    if max_value is not None:
        pieces.append(f"{target} <= {float(max_value)}")
    if not pieces:
        return None
    return " && ".join(pieces)


def build_prefit_filters(channel: str, available_branches: set[str]):
    filters: list[tuple[str, str]] = []
    warnings: list[str] = []

    def cand_take(branch: str) -> str:
        return f"TakeAt({branch}, bestCandIdx)"

    add_filter(filters, warnings, available_branches, range_expression("sel_Phi_pt", min_value=COMMON_CUTS["phi_pt_min"]), "phi_pt", ["sel_Phi_pt"])
    add_filter(filters, warnings, available_branches, range_expression("sel_Phi_eta", max_value=COMMON_CUTS["phi_abs_eta_max"], abs_value=True), "phi_eta", ["sel_Phi_eta"])
    add_filter(filters, warnings, available_branches, range_expression("sel_Phi_VtxProb", min_value=COMMON_CUTS["phi_vtxprob_min"]), "phi_vtxprob", ["sel_Phi_VtxProb"])
    add_filter(filters, warnings, available_branches, range_expression("sel_Phi_ctau", COMMON_CUTS["phi_ctau_min"], COMMON_CUTS["phi_ctau_max"]), "phi_ctau", ["sel_Phi_ctau"])
    add_filter(filters, warnings, available_branches, range_expression("sel_Pri_VtxProb", min_value=COMMON_CUTS["pri_vtxprob_min"]), "pri_vtxprob", ["sel_Pri_VtxProb"])

    if COMMON_CUTS["require_pri_assocpv_pass"]:
        add_filter(filters, warnings, available_branches, f"{cand_take('Pri_assocPVPass')} > 0", "pri_assocpv_pass", ["Pri_assocPVPass", "bestCandIdx"])
    if COMMON_CUTS["require_phi_common_assocpv_pass"]:
        add_filter(filters, warnings, available_branches, f"{cand_take('Phi_commonAssocPVPass')} > 0", "phi_common_assocpv_pass", ["Phi_commonAssocPVPass", "bestCandIdx"])
    if COMMON_CUTS["require_kaon_has_assocpv"]:
        add_filter(
            filters,
            warnings,
            available_branches,
            f"{cand_take('Phi_K_1_hasAssocPV')} > 0 && {cand_take('Phi_K_2_hasAssocPV')} > 0",
            "kaon_assocpv",
            ["Phi_K_1_hasAssocPV", "Phi_K_2_hasAssocPV", "bestCandIdx"],
        )

    add_filter(
        filters,
        warnings,
        available_branches,
        range_expression(cand_take("Pri_assocPVIdx"), COMMON_CUTS["assocpv_idx_min"], COMMON_CUTS["assocpv_idx_max"]),
        "pri_assocpv_idx",
        ["Pri_assocPVIdx", "bestCandIdx"],
    )
    add_filter(
        filters,
        warnings,
        available_branches,
        range_expression(cand_take("Phi_commonAssocPVIdx"), COMMON_CUTS["assocpv_idx_min"], COMMON_CUTS["assocpv_idx_max"]),
        "phi_assocpv_idx",
        ["Phi_commonAssocPVIdx", "bestCandIdx"],
    )
    add_filter(
        filters,
        warnings,
        available_branches,
        range_expression(cand_take("Pri_maxAbsDzPV"), max_value=COMMON_CUTS["pri_max_abs_dzpv"], abs_value=True),
        "pri_max_abs_dzpv",
        ["Pri_maxAbsDzPV", "bestCandIdx"],
    )
    add_filter(
        filters,
        warnings,
        available_branches,
        range_expression(cand_take("Pri_maxAbsDxyPV"), max_value=COMMON_CUTS["pri_max_abs_dxypv"], abs_value=True),
        "pri_max_abs_dxypv",
        ["Pri_maxAbsDxyPV", "bestCandIdx"],
    )
    add_filter(
        filters,
        warnings,
        available_branches,
        (
            f"std::abs({cand_take('Phi_K_1_dzAssocPV')}) <= {float(COMMON_CUTS['track_max_abs_dz_assocpv'])} && "
            f"std::abs({cand_take('Phi_K_2_dzAssocPV')}) <= {float(COMMON_CUTS['track_max_abs_dz_assocpv'])}"
        ) if COMMON_CUTS["track_max_abs_dz_assocpv"] is not None else None,
        "track_dz_assocpv",
        ["Phi_K_1_dzAssocPV", "Phi_K_2_dzAssocPV", "bestCandIdx"],
    )
    add_filter(
        filters,
        warnings,
        available_branches,
        (
            f"std::abs({cand_take('Phi_K_1_dxyAssocPV')}) <= {float(COMMON_CUTS['track_max_abs_dxy_assocpv'])} && "
            f"std::abs({cand_take('Phi_K_2_dxyAssocPV')}) <= {float(COMMON_CUTS['track_max_abs_dxy_assocpv'])}"
        ) if COMMON_CUTS["track_max_abs_dxy_assocpv"] is not None else None,
        "track_dxy_assocpv",
        ["Phi_K_1_dxyAssocPV", "Phi_K_2_dxyAssocPV", "bestCandIdx"],
    )

    if COMMON_CUTS["muon_pt_min"] is not None:
        if channel == "JJP":
            expr = (
                f"sel_Jpsi1_mu1_pt >= {float(COMMON_CUTS['muon_pt_min'])} && "
                f"sel_Jpsi1_mu2_pt >= {float(COMMON_CUTS['muon_pt_min'])} && "
                f"sel_Jpsi2_mu1_pt >= {float(COMMON_CUTS['muon_pt_min'])} && "
                f"sel_Jpsi2_mu2_pt >= {float(COMMON_CUTS['muon_pt_min'])}"
            )
            req = ["sel_Jpsi1_mu1_pt", "sel_Jpsi1_mu2_pt", "sel_Jpsi2_mu1_pt", "sel_Jpsi2_mu2_pt"]
        else:
            expr = (
                f"sel_Jpsi_mu1_pt >= {float(COMMON_CUTS['muon_pt_min'])} && "
                f"sel_Jpsi_mu2_pt >= {float(COMMON_CUTS['muon_pt_min'])} && "
                f"sel_Ups_mu1_pt >= {float(COMMON_CUTS['muon_pt_min'])} && "
                f"sel_Ups_mu2_pt >= {float(COMMON_CUTS['muon_pt_min'])}"
            )
            req = ["sel_Jpsi_mu1_pt", "sel_Jpsi_mu2_pt", "sel_Ups_mu1_pt", "sel_Ups_mu2_pt"]
        add_filter(filters, warnings, available_branches, expr, "muon_pt", req)

    if COMMON_CUTS["track_pt_min"] is not None:
        expr = f"sel_Phi_K_1_pt >= {float(COMMON_CUTS['track_pt_min'])} && sel_Phi_K_2_pt >= {float(COMMON_CUTS['track_pt_min'])}"
        add_filter(filters, warnings, available_branches, expr, "track_pt", ["sel_Phi_K_1_pt", "sel_Phi_K_2_pt"])

    if COMMON_CUTS["track_misuse_dr_max"] is not None and COMMON_CUTS["track_misuse_relpt_max"] is not None:
        if channel == "JJP":
            expr = (
                "PassTrackMisuseVetoJJP("
                "sel_Jpsi1_mu1_pt, sel_Jpsi1_mu1_eta, sel_Jpsi1_mu1_phi, "
                "sel_Jpsi1_mu2_pt, sel_Jpsi1_mu2_eta, sel_Jpsi1_mu2_phi, "
                "sel_Jpsi2_mu1_pt, sel_Jpsi2_mu1_eta, sel_Jpsi2_mu1_phi, "
                "sel_Jpsi2_mu2_pt, sel_Jpsi2_mu2_eta, sel_Jpsi2_mu2_phi, "
                "sel_Phi_K_1_pt, sel_Phi_K_1_eta, sel_Phi_K_1_phi, "
                "sel_Phi_K_2_pt, sel_Phi_K_2_eta, sel_Phi_K_2_phi, "
                f"{float(COMMON_CUTS['track_misuse_dr_max'])}, {float(COMMON_CUTS['track_misuse_relpt_max'])})"
            )
            req = [
                "sel_Jpsi1_mu1_pt", "sel_Jpsi1_mu1_eta", "sel_Jpsi1_mu1_phi",
                "sel_Jpsi1_mu2_pt", "sel_Jpsi1_mu2_eta", "sel_Jpsi1_mu2_phi",
                "sel_Jpsi2_mu1_pt", "sel_Jpsi2_mu1_eta", "sel_Jpsi2_mu1_phi",
                "sel_Jpsi2_mu2_pt", "sel_Jpsi2_mu2_eta", "sel_Jpsi2_mu2_phi",
                "sel_Phi_K_1_pt", "sel_Phi_K_1_eta", "sel_Phi_K_1_phi",
                "sel_Phi_K_2_pt", "sel_Phi_K_2_eta", "sel_Phi_K_2_phi",
            ]
        else:
            expr = (
                "PassTrackMisuseVetoJYP("
                "sel_Jpsi_mu1_pt, sel_Jpsi_mu1_eta, sel_Jpsi_mu1_phi, "
                "sel_Jpsi_mu2_pt, sel_Jpsi_mu2_eta, sel_Jpsi_mu2_phi, "
                "sel_Ups_mu1_pt, sel_Ups_mu1_eta, sel_Ups_mu1_phi, "
                "sel_Ups_mu2_pt, sel_Ups_mu2_eta, sel_Ups_mu2_phi, "
                "sel_Phi_K_1_pt, sel_Phi_K_1_eta, sel_Phi_K_1_phi, "
                "sel_Phi_K_2_pt, sel_Phi_K_2_eta, sel_Phi_K_2_phi, "
                f"{float(COMMON_CUTS['track_misuse_dr_max'])}, {float(COMMON_CUTS['track_misuse_relpt_max'])})"
            )
            req = [
                "sel_Jpsi_mu1_pt", "sel_Jpsi_mu1_eta", "sel_Jpsi_mu1_phi",
                "sel_Jpsi_mu2_pt", "sel_Jpsi_mu2_eta", "sel_Jpsi_mu2_phi",
                "sel_Ups_mu1_pt", "sel_Ups_mu1_eta", "sel_Ups_mu1_phi",
                "sel_Ups_mu2_pt", "sel_Ups_mu2_eta", "sel_Ups_mu2_phi",
                "sel_Phi_K_1_pt", "sel_Phi_K_1_eta", "sel_Phi_K_1_phi",
                "sel_Phi_K_2_pt", "sel_Phi_K_2_eta", "sel_Phi_K_2_phi",
            ]
        add_filter(filters, warnings, available_branches, expr, "track_misuse_veto", req)

    if channel == "JJP":
        add_filter(filters, warnings, available_branches, range_expression("sel_Jpsi_1_pt", min_value=JJP_CUTS["jpsi_pt_min"]), "jpsi1_pt", ["sel_Jpsi_1_pt"])
        add_filter(filters, warnings, available_branches, range_expression("sel_Jpsi_2_pt", min_value=JJP_CUTS["jpsi_pt_min"]), "jpsi2_pt", ["sel_Jpsi_2_pt"])
        add_filter(filters, warnings, available_branches, range_expression("sel_Jpsi_1_eta", max_value=JJP_CUTS["jpsi_abs_eta_max"], abs_value=True), "jpsi1_eta", ["sel_Jpsi_1_eta"])
        add_filter(filters, warnings, available_branches, range_expression("sel_Jpsi_2_eta", max_value=JJP_CUTS["jpsi_abs_eta_max"], abs_value=True), "jpsi2_eta", ["sel_Jpsi_2_eta"])
        add_filter(filters, warnings, available_branches, range_expression("sel_Jpsi_1_VtxProb", min_value=JJP_CUTS["jpsi_vtxprob_min"]), "jpsi1_vtxprob", ["sel_Jpsi_1_VtxProb"])
        add_filter(filters, warnings, available_branches, range_expression("sel_Jpsi_2_VtxProb", min_value=JJP_CUTS["jpsi_vtxprob_min"]), "jpsi2_vtxprob", ["sel_Jpsi_2_VtxProb"])
        add_filter(filters, warnings, available_branches, range_expression("sel_Jpsi_1_ctau", JJP_CUTS["jpsi_ctau_min"], JJP_CUTS["jpsi_ctau_max"]), "jpsi1_ctau", ["sel_Jpsi_1_ctau"])
        add_filter(filters, warnings, available_branches, range_expression("sel_Jpsi_2_ctau", JJP_CUTS["jpsi_ctau_min"], JJP_CUTS["jpsi_ctau_max"]), "jpsi2_ctau", ["sel_Jpsi_2_ctau"])

        muon_id_branch = MUON_ID_BRANCHES.get(JJP_CUTS["muon_id"])
        if muon_id_branch is not None:
            expr = (
                f"TakeMask({muon_id_branch}, sel_Jpsi_1_mu_1_Idx) > 0 && "
                f"TakeMask({muon_id_branch}, sel_Jpsi_1_mu_2_Idx) > 0 && "
                f"TakeMask({muon_id_branch}, sel_Jpsi_2_mu_1_Idx) > 0 && "
                f"TakeMask({muon_id_branch}, sel_Jpsi_2_mu_2_Idx) > 0"
            )
            add_filter(filters, warnings, available_branches, expr, f"muon_id_{JJP_CUTS['muon_id']}", [muon_id_branch, "sel_Jpsi_1_mu_1_Idx", "sel_Jpsi_1_mu_2_Idx", "sel_Jpsi_2_mu_1_Idx", "sel_Jpsi_2_mu_2_Idx"])

        if JJP_CUTS["jpsi_trigger_min_matched_muons"] > 0:
            expr = (
                "CountSelectedMatches4(muIsJpsiTrigMatch, "
                "sel_Jpsi_1_mu_1_Idx, sel_Jpsi_1_mu_2_Idx, sel_Jpsi_2_mu_1_Idx, sel_Jpsi_2_mu_2_Idx) "
                f">= {int(JJP_CUTS['jpsi_trigger_min_matched_muons'])}"
            )
            add_filter(filters, warnings, available_branches, expr, "jpsi_trigger_match", ["muIsJpsiTrigMatch", "sel_Jpsi_1_mu_1_Idx", "sel_Jpsi_1_mu_2_Idx", "sel_Jpsi_2_mu_1_Idx", "sel_Jpsi_2_mu_2_Idx"])
    else:
        add_filter(filters, warnings, available_branches, range_expression("sel_Jpsi_pt", min_value=JYP_CUTS["jpsi_pt_min"]), "jpsi_pt", ["sel_Jpsi_pt"])
        add_filter(filters, warnings, available_branches, range_expression("sel_Jpsi_eta", max_value=JYP_CUTS["jpsi_abs_eta_max"], abs_value=True), "jpsi_eta", ["sel_Jpsi_eta"])
        add_filter(filters, warnings, available_branches, range_expression("sel_Jpsi_VtxProb", min_value=JYP_CUTS["jpsi_vtxprob_min"]), "jpsi_vtxprob", ["sel_Jpsi_VtxProb"])
        add_filter(filters, warnings, available_branches, range_expression("sel_Jpsi_ctau", JYP_CUTS["jpsi_ctau_min"], JYP_CUTS["jpsi_ctau_max"]), "jpsi_ctau", ["sel_Jpsi_ctau"])

        add_filter(filters, warnings, available_branches, range_expression("sel_Ups_pt", min_value=JYP_CUTS["ups_pt_min"]), "ups_pt", ["sel_Ups_pt"])
        add_filter(filters, warnings, available_branches, range_expression("sel_Ups_eta", max_value=JYP_CUTS["ups_abs_eta_max"], abs_value=True), "ups_eta", ["sel_Ups_eta"])
        add_filter(filters, warnings, available_branches, range_expression("sel_Ups_VtxProb", min_value=JYP_CUTS["ups_vtxprob_min"]), "ups_vtxprob", ["sel_Ups_VtxProb"])
        add_filter(filters, warnings, available_branches, range_expression("sel_Ups_ctau", JYP_CUTS["ups_ctau_min"], JYP_CUTS["ups_ctau_max"]), "ups_ctau", ["sel_Ups_ctau"])

        jpsi_id_branch = MUON_ID_BRANCHES.get(JYP_CUTS["jpsi_muon_id"])
        if jpsi_id_branch is not None:
            expr = (
                f"TakeMask({jpsi_id_branch}, sel_Jpsi_mu_1_Idx) > 0 && "
                f"TakeMask({jpsi_id_branch}, sel_Jpsi_mu_2_Idx) > 0"
            )
            add_filter(filters, warnings, available_branches, expr, f"jpsi_muon_id_{JYP_CUTS['jpsi_muon_id']}", [jpsi_id_branch, "sel_Jpsi_mu_1_Idx", "sel_Jpsi_mu_2_Idx"])

        ups_id_branch = MUON_ID_BRANCHES.get(JYP_CUTS["ups_muon_id"])
        if ups_id_branch is not None:
            expr = (
                f"TakeMask({ups_id_branch}, sel_Ups_mu_1_Idx) > 0 && "
                f"TakeMask({ups_id_branch}, sel_Ups_mu_2_Idx) > 0"
            )
            add_filter(filters, warnings, available_branches, expr, f"ups_muon_id_{JYP_CUTS['ups_muon_id']}", [ups_id_branch, "sel_Ups_mu_1_Idx", "sel_Ups_mu_2_Idx"])

        if JYP_CUTS["jpsi_trigger_min_matched_muons"] > 0:
            expr = (
                "CountSelectedMatches2(muIsJpsiTrigMatch, sel_Jpsi_mu_1_Idx, sel_Jpsi_mu_2_Idx) "
                f">= {int(JYP_CUTS['jpsi_trigger_min_matched_muons'])}"
            )
            add_filter(filters, warnings, available_branches, expr, "jpsi_trigger_match", ["muIsJpsiTrigMatch", "sel_Jpsi_mu_1_Idx", "sel_Jpsi_mu_2_Idx"])

        if JYP_CUTS["ups_trigger_min_matched_muons"] > 0:
            expr = (
                "CountSelectedMatches2(muIsUpsTrigMatch, sel_Ups_mu_1_Idx, sel_Ups_mu_2_Idx) "
                f">= {int(JYP_CUTS['ups_trigger_min_matched_muons'])}"
            )
            add_filter(filters, warnings, available_branches, expr, "ups_trigger_match", ["muIsUpsTrigMatch", "sel_Ups_mu_1_Idx", "sel_Ups_mu_2_Idx"])

    return filters, warnings


def run_prefit_filter(input_file: str, filtered_output: str, channel: str, jobs: int, max_events: int):
    ensure_parent_dir(filtered_output)
    available_branches = set(get_tree_branches(input_file, INPUT_TREE))

    ROOT.gROOT.SetBatch(True)
    if jobs > 1:
        ROOT.EnableImplicitMT(jobs)
    declare_rdf_helpers()
    declare_prefit_helpers()

    rdf = ROOT.RDataFrame(INPUT_TREE, input_file)
    if max_events > 0:
        rdf = rdf.Range(max_events)

    filters, warnings = build_prefit_filters(channel, available_branches)
    filtered = rdf
    for label, expression in filters:
        filtered = filtered.Filter(expression, label)

    total_action = rdf.Count()
    passed_action = filtered.Count()
    report = filtered.Report()

    options = ROOT.RDF.RSnapshotOptions()
    options.fMode = "RECREATE"
    options.fLazy = True
    snapshot = filtered.Snapshot(INPUT_TREE, filtered_output, build_root_string_vector(sorted(available_branches)), options)
    ROOT.RDF.RunGraphs([total_action, passed_action, snapshot])

    total = int(total_action.GetValue())
    passed = int(passed_action.GetValue())
    return total, passed, report, warnings, filters


def run_fit(filtered_input: str, output_file: str, plot_dir: str, channel: str, dataset: str, jobs: int):
    summary = uproot.open(filtered_input)[INPUT_TREE]
    n_entries = summary.num_entries
    if n_entries <= 0:
        raise RuntimeError(f"No events left after pre-fit cuts in {filtered_input}")

    fin = ROOT.TFile.Open(filtered_input)
    tree = fin.Get(INPUT_TREE)
    if not tree:
        fin.Close()
        raise RuntimeError(f"Input tree '{INPUT_TREE}' not found in {filtered_input}")
    input_tree_entries = int(tree.GetEntries())

    if channel == "JJP":
        model, observables, yields, signal_yield_name, keepalive = fit_core.build_jjp_model(n_entries, mc_two_component=(dataset == "mc"))
    else:
        model, observables, yields, signal_yield_name, keepalive = fit_core.build_jyp_model(
            n_entries,
            mc_only_1s=(dataset == "mc"),
            mc_two_component=(dataset == "mc"),
        )

    data = fit_core.make_dataset(tree, observables)
    keepalive.append(data)
    fit_result = model.fitTo(
        data,
        ROOT.RooFit.Extended(True),
        ROOT.RooFit.Save(True),
        ROOT.RooFit.NumCPU(max(1, jobs)),
        ROOT.RooFit.Strategy(1),
        ROOT.RooFit.PrintLevel(-1),
    )
    keepalive.append(fit_result)

    fit_core.save_projection_plots(channel, plot_dir, data, model, observables, signal_yield_name, yields)
    sdata = ROOT.RooStats.SPlot("sData", "sData", data, model, ROOT.RooArgList(*yields.values()))
    keepalive.append(sdata)

    weight_map = OrderedDict()
    for yield_name in yields:
        weight_map[f"{yield_name}_sw"] = [data.get(i).getRealValue(f"{yield_name}_sw") for i in range(data.numEntries())]
    weight_map["signal_sw"] = list(weight_map[f"{signal_yield_name}_sw"])

    significance = fit_core.compute_component_significance(
        model,
        data,
        yields,
        signal_yield_name,
        best_min_nll=fit_result.minNll(),
        jobs=jobs,
        strategy=1,
        print_level=-1,
    )
    keepalive.append(significance["null_fit_result"])

    fit_core.clone_tree_with_weights(tree, output_file, weight_map)
    fit_out = ROOT.TFile(output_file.replace(".root", "_fit_result.root"), "RECREATE")
    fit_result.Write("fit_result")
    fit_core.save_significance_to_root(fit_out, signal_yield_name, significance)
    fit_out.Close()
    fin.Close()

    print(f"[INFO] filtered tree entries   : {input_tree_entries}")
    print(f"[INFO] fitted dataset entries : {data.numEntries()}")
    print(f"[INFO] signal yield           : {yields[signal_yield_name].getVal():.2f}")
    print(f"[INFO] background yield       : {significance['background_yield']:.2f}")
    print(f"[INFO] signal component       : {signal_yield_name}")
    print(f"[INFO] q0 (LRT, sss only)     : {significance['q0']:.3f}")
    print(f"[INFO] significance (LRT)     : {significance['lrt_significance']:.3f}")


def main():
    args = parse_args()
    channel = normalize_channel(args.channel)
    dataset = normalize_dataset(args.dataset)
    sample = normalize_sample(channel, args.sample) if dataset == "mc" else None

    input_file = args.input or default_merged_output(channel, dataset, sample)
    output_file = args.output or default_weighted_output(channel, dataset, sample)
    filtered_output = args.filtered_output or default_filtered_output(output_file)
    plot_dir = args.plot_dir or os.path.join(default_plot_dir(channel, dataset, sample), "fit")

    ensure_parent_dir(output_file)
    ensure_parent_dir(filtered_output)
    ensure_dir(plot_dir)

    print("=" * 80)
    print("assocPV pre-fit cut + sPlot fit")
    print("=" * 80)
    print(f"[INFO] channel        : {channel}")
    print(f"[INFO] dataset        : {dataset}")
    print(f"[INFO] sample         : {sample or '-'}")
    print(f"[INFO] input          : {input_file}")
    print(f"[INFO] filtered output: {filtered_output}")
    print(f"[INFO] weighted output: {output_file}")
    print(f"[INFO] plot dir       : {plot_dir}")
    print(f"[INFO] jobs           : {args.jobs}")
    print(f"[INFO] max events     : {args.max_events}")
    print("=" * 80)

    total, passed, report, warnings, filters = run_prefit_filter(input_file, filtered_output, channel, args.jobs, args.max_events)
    for warning in warnings:
        print(warning)

    print(f"[INFO] configured pre-fit cuts: {len(filters)}")
    for label, expression in filters:
        print(f"[CUT] {label}: {expression}")

    print(f"[INFO] input entries          : {total}")
    print(f"[INFO] entries after cuts     : {passed}")
    if total > 0:
        print(f"[INFO] pre-fit efficiency     : {100.0 * passed / total:.3f}%")
    report.Print()

    run_fit(filtered_output, output_file, plot_dir, channel, dataset, args.jobs)
    print(f"[INFO] passing events saved   : {filtered_output}")
    print(f"[INFO] weighted tree saved    : {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

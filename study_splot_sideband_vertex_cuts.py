#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Study pileup rejection from vertex cuts on overall, signal, and sideband samples."""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
import ROOT
import uproot

import compare_bbb_splot_sideband as bbb_compare
from ntuple_pipeline_common import (
    build_root_string_vector,
    declare_rdf_helpers,
    default_plot_dir,
    default_weighted_output,
    ensure_dir,
    ensure_parent_dir,
    get_tree_branches,
)


INPUT_TREE = "selected"
PRI_VTXPROB_MIN = 0.05
D_BRANCHES = ("D_jpsi1_jpsi2", "D_jpsi1_phi", "D_jpsi2_phi")
DEFAULT_D_BINS = 20
DEFAULT_Z_BINS = 10
_VERTEX_HELPERS_DECLARED = False


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    mask_branch: str | None


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    input_kind: str
    weight_branch: str | None
    output_subdir: str


@dataclass(frozen=True)
class PlotSpec:
    key: str
    title: str
    xlabel: str
    bins: int | None = None
    edges: tuple[float, ...] | None = None


SCENARIOS = (
    Scenario("no_cut", "No cut", None),
    Scenario("assocpv", "assocPV cut", "pass_assocpv_cut"),
    Scenario("vtxprob", rf"$P_{{vtx}} > {PRI_VTXPROB_MIN:g}$", "pass_vtxprob_cut"),
)

CATEGORIES = (
    Category("overall", "Overall", "weighted", None, "overall"),
    Category("signal", "Signal", "weighted", "signal_sw", "signal"),
    Category("sideband_bkg", "Sideband background", "sideband", None, "sideband_bkg"),
)


def parse_args():
    parser = argparse.ArgumentParser(description="Vertex-cut pileup study on sPlot signal and sideband-selected background")
    parser.add_argument("--weighted-input", default=None, help="Weighted ROOT file from compare_bbb_splot_sideband.py")
    parser.add_argument("--sideband-input", default=None, help="Sideband-only ROOT file from compare_bbb_splot_sideband.py")
    parser.add_argument("--weighted-output", default=None, help="Augmented weighted ROOT file with D_ij and cut columns")
    parser.add_argument("--sideband-output", default=None, help="Augmented sideband ROOT file with D_ij and cut columns")
    parser.add_argument("--plot-dir", default=None, help="Base output directory for plots")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="RDataFrame thread count")
    parser.add_argument("-n", "--max-events", type=int, default=-1, help="Limit events for quick tests")
    parser.add_argument("--force", action="store_true", help="Regenerate the augmented ROOT files")
    return parser.parse_args()


def default_paths(args):
    default_weighted = bbb_compare.derived_output(default_weighted_output("JJP", "data"), "_bbb_sideband_compare")
    weighted_input = args.weighted_input or default_weighted
    sideband_input = args.sideband_input or bbb_compare.derived_output(weighted_input, "_sideband_only")
    weighted_output = args.weighted_output or bbb_compare.derived_output(weighted_input, "_vertex_study")
    sideband_output = args.sideband_output or bbb_compare.derived_output(sideband_input, "_vertex_study")
    plot_dir = args.plot_dir or os.path.join(default_plot_dir("JJP", "data"), "bbb_sideband_compare", "vertex_cut_study")
    return weighted_input, sideband_input, weighted_output, sideband_output, plot_dir


def declare_vertex_helpers():
    global _VERTEX_HELPERS_DECLARED
    if _VERTEX_HELPERS_DECLARED:
        return
    ROOT.gInterpreter.Declare(
        r"""
        #include <algorithm>
        #include <cmath>

        float PairMean(float a, float b) {
            return 0.5f * (a + b);
        }

        float SafeNormDistance(float delta, float sigma1, float sigma2) {
            const float denom2 = sigma1 * sigma1 + sigma2 * sigma2;
            if (denom2 <= 0.f) {
                return std::fabs(delta) <= 1.0e-12f ? 0.f : 1.0e6f;
            }
            return std::fabs(delta) / std::sqrt(denom2);
        }

        int ChooseIndex(int preferred, int fallback) {
            return preferred >= 0 ? preferred : fallback;
        }

        float MeanComponentError(float err1, float err2) {
            return 0.5f * std::hypot(err1, err2);
        }

        float MeanWithSpreadError(float value1, float value2, float err1, float err2) {
            const float stat = MeanComponentError(err1, err2);
            const float spread = 0.5f * std::fabs(value1 - value2);
            return std::hypot(stat, spread);
        }
        """
    )
    _VERTEX_HELPERS_DECLARED = True


def validate_inputs(file_name: str):
    required = {
        "bestCandIdx",
        "Pri_assocPVPass",
        "Pri_assocPVIdx",
        "Phi_commonAssocPVIdx",
        "sel_Pri_VtxProb",
        "RecVtx_xErr",
        "RecVtx_yErr",
        "RecVtx_zErr",
        "muVertexId",
        "RecVtx_x",
        "RecVtx_y",
        "RecVtx_z",
        "priVtxX",
        "priVtxY",
        "priVtxZ",
        "Phi_K_1_vertexId",
        "Phi_K_2_vertexId",
        "sel_Jpsi_1_mu_1_Idx",
        "sel_Jpsi_1_mu_2_Idx",
        "sel_Jpsi_2_mu_1_Idx",
        "sel_Jpsi_2_mu_2_Idx",
        "nGoodPrimVtx",
        "priVtxZ",
    }
    branches = set(get_tree_branches(file_name, INPUT_TREE))
    missing = sorted(required - branches)
    if missing:
        raise RuntimeError(f"Missing required branches in {file_name}: {', '.join(missing)}")
    return sorted(branches)


def augment_file(input_file: str, output_file: str, jobs: int, max_events: int):
    ensure_parent_dir(output_file)
    original_branches = validate_inputs(input_file)

    ROOT.gROOT.SetBatch(True)
    declare_rdf_helpers()
    declare_vertex_helpers()
    if jobs > 1:
        ROOT.EnableImplicitMT(jobs)

    rdf = ROOT.RDataFrame(INPUT_TREE, input_file)
    if max_events > 0:
        rdf = rdf.Range(max_events)

    rdf = rdf.Define("pass_assocpv_cut", "TakeAt(Pri_assocPVPass, bestCandIdx) > 0")
    rdf = rdf.Define("pass_vtxprob_cut", f"sel_Pri_VtxProb > {float(PRI_VTXPROB_MIN)}")
    rdf = rdf.Define("unit_weight", "1.0")

    rdf = rdf.Define("jpsi1_mu1_dz_assocpv", "TakeAt(muDzAssocPV, sel_Jpsi_1_mu_1_Idx)")
    rdf = rdf.Define("jpsi1_mu2_dz_assocpv", "TakeAt(muDzAssocPV, sel_Jpsi_1_mu_2_Idx)")
    rdf = rdf.Define("jpsi2_mu1_dz_assocpv", "TakeAt(muDzAssocPV, sel_Jpsi_2_mu_1_Idx)")
    rdf = rdf.Define("jpsi2_mu2_dz_assocpv", "TakeAt(muDzAssocPV, sel_Jpsi_2_mu_2_Idx)")
    rdf = rdf.Define("jpsi1_mu1_dxy_assocpv", "TakeAt(muDxyAssocPV, sel_Jpsi_1_mu_1_Idx)")
    rdf = rdf.Define("jpsi1_mu2_dxy_assocpv", "TakeAt(muDxyAssocPV, sel_Jpsi_1_mu_2_Idx)")
    rdf = rdf.Define("jpsi2_mu1_dxy_assocpv", "TakeAt(muDxyAssocPV, sel_Jpsi_2_mu_1_Idx)")
    rdf = rdf.Define("jpsi2_mu2_dxy_assocpv", "TakeAt(muDxyAssocPV, sel_Jpsi_2_mu_2_Idx)")
    rdf = rdf.Define("phi_k1_dz_assocpv", "TakeAt(Phi_K_1_dzAssocPV, bestCandIdx)")
    rdf = rdf.Define("phi_k2_dz_assocpv", "TakeAt(Phi_K_2_dzAssocPV, bestCandIdx)")
    rdf = rdf.Define("phi_k1_dxy_assocpv", "TakeAt(Phi_K_1_dxyAssocPV, bestCandIdx)")
    rdf = rdf.Define("phi_k2_dxy_assocpv", "TakeAt(Phi_K_2_dxyAssocPV, bestCandIdx)")

    rdf = rdf.Define("jpsi1_mu1_assocpv_idx", "TakeAtInt(muVertexId, sel_Jpsi_1_mu_1_Idx)")
    rdf = rdf.Define("jpsi1_mu2_assocpv_idx", "TakeAtInt(muVertexId, sel_Jpsi_1_mu_2_Idx)")
    rdf = rdf.Define("jpsi2_mu1_assocpv_idx", "TakeAtInt(muVertexId, sel_Jpsi_2_mu_1_Idx)")
    rdf = rdf.Define("jpsi2_mu2_assocpv_idx", "TakeAtInt(muVertexId, sel_Jpsi_2_mu_2_Idx)")
    rdf = rdf.Define("phi_k1_assocpv_idx", "TakeAtInt(Phi_K_1_vertexId, bestCandIdx)")
    rdf = rdf.Define("phi_k2_assocpv_idx", "TakeAtInt(Phi_K_2_vertexId, bestCandIdx)")

    rdf = rdf.Define("jpsi1_mu1_assocpv_x", "jpsi1_mu1_assocpv_idx >= 0 ? TakeAt(RecVtx_x, jpsi1_mu1_assocpv_idx) : priVtxX")
    rdf = rdf.Define("jpsi1_mu1_assocpv_y", "jpsi1_mu1_assocpv_idx >= 0 ? TakeAt(RecVtx_y, jpsi1_mu1_assocpv_idx) : priVtxY")
    rdf = rdf.Define("jpsi1_mu1_assocpv_z", "jpsi1_mu1_assocpv_idx >= 0 ? TakeAt(RecVtx_z, jpsi1_mu1_assocpv_idx) : priVtxZ")
    rdf = rdf.Define("jpsi1_mu2_assocpv_x", "jpsi1_mu2_assocpv_idx >= 0 ? TakeAt(RecVtx_x, jpsi1_mu2_assocpv_idx) : priVtxX")
    rdf = rdf.Define("jpsi1_mu2_assocpv_y", "jpsi1_mu2_assocpv_idx >= 0 ? TakeAt(RecVtx_y, jpsi1_mu2_assocpv_idx) : priVtxY")
    rdf = rdf.Define("jpsi1_mu2_assocpv_z", "jpsi1_mu2_assocpv_idx >= 0 ? TakeAt(RecVtx_z, jpsi1_mu2_assocpv_idx) : priVtxZ")
    rdf = rdf.Define("jpsi2_mu1_assocpv_x", "jpsi2_mu1_assocpv_idx >= 0 ? TakeAt(RecVtx_x, jpsi2_mu1_assocpv_idx) : priVtxX")
    rdf = rdf.Define("jpsi2_mu1_assocpv_y", "jpsi2_mu1_assocpv_idx >= 0 ? TakeAt(RecVtx_y, jpsi2_mu1_assocpv_idx) : priVtxY")
    rdf = rdf.Define("jpsi2_mu1_assocpv_z", "jpsi2_mu1_assocpv_idx >= 0 ? TakeAt(RecVtx_z, jpsi2_mu1_assocpv_idx) : priVtxZ")
    rdf = rdf.Define("jpsi2_mu2_assocpv_x", "jpsi2_mu2_assocpv_idx >= 0 ? TakeAt(RecVtx_x, jpsi2_mu2_assocpv_idx) : priVtxX")
    rdf = rdf.Define("jpsi2_mu2_assocpv_y", "jpsi2_mu2_assocpv_idx >= 0 ? TakeAt(RecVtx_y, jpsi2_mu2_assocpv_idx) : priVtxY")
    rdf = rdf.Define("jpsi2_mu2_assocpv_z", "jpsi2_mu2_assocpv_idx >= 0 ? TakeAt(RecVtx_z, jpsi2_mu2_assocpv_idx) : priVtxZ")
    rdf = rdf.Define("phi_k1_assocpv_x", "phi_k1_assocpv_idx >= 0 ? TakeAt(RecVtx_x, phi_k1_assocpv_idx) : priVtxX")
    rdf = rdf.Define("phi_k1_assocpv_y", "phi_k1_assocpv_idx >= 0 ? TakeAt(RecVtx_y, phi_k1_assocpv_idx) : priVtxY")
    rdf = rdf.Define("phi_k1_assocpv_z", "phi_k1_assocpv_idx >= 0 ? TakeAt(RecVtx_z, phi_k1_assocpv_idx) : priVtxZ")
    rdf = rdf.Define("phi_k2_assocpv_x", "phi_k2_assocpv_idx >= 0 ? TakeAt(RecVtx_x, phi_k2_assocpv_idx) : priVtxX")
    rdf = rdf.Define("phi_k2_assocpv_y", "phi_k2_assocpv_idx >= 0 ? TakeAt(RecVtx_y, phi_k2_assocpv_idx) : priVtxY")
    rdf = rdf.Define("phi_k2_assocpv_z", "phi_k2_assocpv_idx >= 0 ? TakeAt(RecVtx_z, phi_k2_assocpv_idx) : priVtxZ")

    rdf = rdf.Define("jpsi1_mu1_assocpv_xerr", "jpsi1_mu1_assocpv_idx >= 0 ? TakeAt(RecVtx_xErr, jpsi1_mu1_assocpv_idx) : 0.f")
    rdf = rdf.Define("jpsi1_mu1_assocpv_yerr", "jpsi1_mu1_assocpv_idx >= 0 ? TakeAt(RecVtx_yErr, jpsi1_mu1_assocpv_idx) : 0.f")
    rdf = rdf.Define("jpsi1_mu1_assocpv_zerr", "jpsi1_mu1_assocpv_idx >= 0 ? TakeAt(RecVtx_zErr, jpsi1_mu1_assocpv_idx) : 0.f")
    rdf = rdf.Define("jpsi1_mu2_assocpv_xerr", "jpsi1_mu2_assocpv_idx >= 0 ? TakeAt(RecVtx_xErr, jpsi1_mu2_assocpv_idx) : 0.f")
    rdf = rdf.Define("jpsi1_mu2_assocpv_yerr", "jpsi1_mu2_assocpv_idx >= 0 ? TakeAt(RecVtx_yErr, jpsi1_mu2_assocpv_idx) : 0.f")
    rdf = rdf.Define("jpsi1_mu2_assocpv_zerr", "jpsi1_mu2_assocpv_idx >= 0 ? TakeAt(RecVtx_zErr, jpsi1_mu2_assocpv_idx) : 0.f")
    rdf = rdf.Define("jpsi2_mu1_assocpv_xerr", "jpsi2_mu1_assocpv_idx >= 0 ? TakeAt(RecVtx_xErr, jpsi2_mu1_assocpv_idx) : 0.f")
    rdf = rdf.Define("jpsi2_mu1_assocpv_yerr", "jpsi2_mu1_assocpv_idx >= 0 ? TakeAt(RecVtx_yErr, jpsi2_mu1_assocpv_idx) : 0.f")
    rdf = rdf.Define("jpsi2_mu1_assocpv_zerr", "jpsi2_mu1_assocpv_idx >= 0 ? TakeAt(RecVtx_zErr, jpsi2_mu1_assocpv_idx) : 0.f")
    rdf = rdf.Define("jpsi2_mu2_assocpv_xerr", "jpsi2_mu2_assocpv_idx >= 0 ? TakeAt(RecVtx_xErr, jpsi2_mu2_assocpv_idx) : 0.f")
    rdf = rdf.Define("jpsi2_mu2_assocpv_yerr", "jpsi2_mu2_assocpv_idx >= 0 ? TakeAt(RecVtx_yErr, jpsi2_mu2_assocpv_idx) : 0.f")
    rdf = rdf.Define("jpsi2_mu2_assocpv_zerr", "jpsi2_mu2_assocpv_idx >= 0 ? TakeAt(RecVtx_zErr, jpsi2_mu2_assocpv_idx) : 0.f")
    rdf = rdf.Define("phi_k1_assocpv_xerr", "phi_k1_assocpv_idx >= 0 ? TakeAt(RecVtx_xErr, phi_k1_assocpv_idx) : 0.f")
    rdf = rdf.Define("phi_k1_assocpv_yerr", "phi_k1_assocpv_idx >= 0 ? TakeAt(RecVtx_yErr, phi_k1_assocpv_idx) : 0.f")
    rdf = rdf.Define("phi_k1_assocpv_zerr", "phi_k1_assocpv_idx >= 0 ? TakeAt(RecVtx_zErr, phi_k1_assocpv_idx) : 0.f")
    rdf = rdf.Define("phi_k2_assocpv_xerr", "phi_k2_assocpv_idx >= 0 ? TakeAt(RecVtx_xErr, phi_k2_assocpv_idx) : 0.f")
    rdf = rdf.Define("phi_k2_assocpv_yerr", "phi_k2_assocpv_idx >= 0 ? TakeAt(RecVtx_yErr, phi_k2_assocpv_idx) : 0.f")
    rdf = rdf.Define("phi_k2_assocpv_zerr", "phi_k2_assocpv_idx >= 0 ? TakeAt(RecVtx_zErr, phi_k2_assocpv_idx) : 0.f")

    rdf = rdf.Define("jpsi1_assocpv_x", "PairMean(jpsi1_mu1_assocpv_x, jpsi1_mu2_assocpv_x)")
    rdf = rdf.Define("jpsi1_assocpv_y", "PairMean(jpsi1_mu1_assocpv_y, jpsi1_mu2_assocpv_y)")
    rdf = rdf.Define("jpsi1_assocpv_z", "PairMean(jpsi1_mu1_assocpv_z, jpsi1_mu2_assocpv_z)")
    rdf = rdf.Define("jpsi2_assocpv_x", "PairMean(jpsi2_mu1_assocpv_x, jpsi2_mu2_assocpv_x)")
    rdf = rdf.Define("jpsi2_assocpv_y", "PairMean(jpsi2_mu1_assocpv_y, jpsi2_mu2_assocpv_y)")
    rdf = rdf.Define("jpsi2_assocpv_z", "PairMean(jpsi2_mu1_assocpv_z, jpsi2_mu2_assocpv_z)")
    rdf = rdf.Define("phi_assocpv_x", "PairMean(phi_k1_assocpv_x, phi_k2_assocpv_x)")
    rdf = rdf.Define("phi_assocpv_y", "PairMean(phi_k1_assocpv_y, phi_k2_assocpv_y)")
    rdf = rdf.Define("phi_assocpv_z", "PairMean(phi_k1_assocpv_z, phi_k2_assocpv_z)")

    rdf = rdf.Define("jpsi1_dz_assocpv", "jpsi1_assocpv_z")
    rdf = rdf.Define("jpsi2_dz_assocpv", "jpsi2_assocpv_z")
    rdf = rdf.Define("phi_dz_assocpv", "phi_assocpv_z")
    rdf = rdf.Define("jpsi1_dxy_assocpv", "std::hypot(jpsi1_assocpv_x, jpsi1_assocpv_y)")
    rdf = rdf.Define("jpsi2_dxy_assocpv", "std::hypot(jpsi2_assocpv_x, jpsi2_assocpv_y)")
    rdf = rdf.Define("phi_dxy_assocpv", "std::hypot(phi_assocpv_x, phi_assocpv_y)")

    rdf = rdf.Define("jpsi1_mu1_assocpv_xyerr", "std::hypot(jpsi1_mu1_assocpv_xerr, jpsi1_mu1_assocpv_yerr)")
    rdf = rdf.Define("jpsi1_mu2_assocpv_xyerr", "std::hypot(jpsi1_mu2_assocpv_xerr, jpsi1_mu2_assocpv_yerr)")
    rdf = rdf.Define("jpsi2_mu1_assocpv_xyerr", "std::hypot(jpsi2_mu1_assocpv_xerr, jpsi2_mu1_assocpv_yerr)")
    rdf = rdf.Define("jpsi2_mu2_assocpv_xyerr", "std::hypot(jpsi2_mu2_assocpv_xerr, jpsi2_mu2_assocpv_yerr)")
    rdf = rdf.Define("phi_k1_assocpv_xyerr", "std::hypot(phi_k1_assocpv_xerr, phi_k1_assocpv_yerr)")
    rdf = rdf.Define("phi_k2_assocpv_xyerr", "std::hypot(phi_k2_assocpv_xerr, phi_k2_assocpv_yerr)")

    rdf = rdf.Define("jpsi1_assocpv_xerr", "MeanWithSpreadError(jpsi1_mu1_assocpv_x, jpsi1_mu2_assocpv_x, jpsi1_mu1_assocpv_xerr, jpsi1_mu2_assocpv_xerr)")
    rdf = rdf.Define("jpsi1_assocpv_yerr", "MeanWithSpreadError(jpsi1_mu1_assocpv_y, jpsi1_mu2_assocpv_y, jpsi1_mu1_assocpv_yerr, jpsi1_mu2_assocpv_yerr)")
    rdf = rdf.Define("jpsi1_assocpv_zerr", "MeanWithSpreadError(jpsi1_mu1_assocpv_z, jpsi1_mu2_assocpv_z, jpsi1_mu1_assocpv_zerr, jpsi1_mu2_assocpv_zerr)")
    rdf = rdf.Define("jpsi2_assocpv_xerr", "MeanWithSpreadError(jpsi2_mu1_assocpv_x, jpsi2_mu2_assocpv_x, jpsi2_mu1_assocpv_xerr, jpsi2_mu2_assocpv_xerr)")
    rdf = rdf.Define("jpsi2_assocpv_yerr", "MeanWithSpreadError(jpsi2_mu1_assocpv_y, jpsi2_mu2_assocpv_y, jpsi2_mu1_assocpv_yerr, jpsi2_mu2_assocpv_yerr)")
    rdf = rdf.Define("jpsi2_assocpv_zerr", "MeanWithSpreadError(jpsi2_mu1_assocpv_z, jpsi2_mu2_assocpv_z, jpsi2_mu1_assocpv_zerr, jpsi2_mu2_assocpv_zerr)")
    rdf = rdf.Define("phi_assocpv_xerr", "MeanWithSpreadError(phi_k1_assocpv_x, phi_k2_assocpv_x, phi_k1_assocpv_xerr, phi_k2_assocpv_xerr)")
    rdf = rdf.Define("phi_assocpv_yerr", "MeanWithSpreadError(phi_k1_assocpv_y, phi_k2_assocpv_y, phi_k1_assocpv_yerr, phi_k2_assocpv_yerr)")
    rdf = rdf.Define("phi_assocpv_zerr", "MeanWithSpreadError(phi_k1_assocpv_z, phi_k2_assocpv_z, phi_k1_assocpv_zerr, phi_k2_assocpv_zerr)")

    rdf = rdf.Define("jpsi1_dz_assocpv_sigma", "jpsi1_assocpv_zerr")
    rdf = rdf.Define("jpsi2_dz_assocpv_sigma", "jpsi2_assocpv_zerr")
    rdf = rdf.Define("phi_dz_assocpv_sigma", "phi_assocpv_zerr")
    rdf = rdf.Define("jpsi1_dxy_assocpv_sigma", "std::hypot(jpsi1_assocpv_xerr, jpsi1_assocpv_yerr)")
    rdf = rdf.Define("jpsi2_dxy_assocpv_sigma", "std::hypot(jpsi2_assocpv_xerr, jpsi2_assocpv_yerr)")
    rdf = rdf.Define("phi_dxy_assocpv_sigma", "std::hypot(phi_assocpv_xerr, phi_assocpv_yerr)")

    for pair_name, left, right in (
        ("jpsi1_jpsi2", "jpsi1", "jpsi2"),
        ("jpsi1_phi", "jpsi1", "phi"),
        ("jpsi2_phi", "jpsi2", "phi"),
    ):
        rdf = rdf.Define(f"delta_dz_{pair_name}", f"{left}_dz_assocpv - {right}_dz_assocpv")
        rdf = rdf.Define(f"delta_dxy_{pair_name}", f"{left}_dxy_assocpv - {right}_dxy_assocpv")
        rdf = rdf.Define(
            f"Dz_{pair_name}",
            f"SafeNormDistance(delta_dz_{pair_name}, {left}_dz_assocpv_sigma, {right}_dz_assocpv_sigma)",
        )
        rdf = rdf.Define(
            f"Dxy_{pair_name}",
            f"SafeNormDistance(delta_dxy_{pair_name}, {left}_dxy_assocpv_sigma, {right}_dxy_assocpv_sigma)",
        )
        rdf = rdf.Define(f"D_{pair_name}", f"std::hypot(Dz_{pair_name}, Dxy_{pair_name})")

    rdf = rdf.Define("D3_max", "std::max({D_jpsi1_jpsi2, D_jpsi1_phi, D_jpsi2_phi})")

    derived = [
        "pass_assocpv_cut",
        "pass_vtxprob_cut",
        "unit_weight",
        "jpsi1_mu1_assocpv_idx", "jpsi1_mu2_assocpv_idx", "jpsi2_mu1_assocpv_idx", "jpsi2_mu2_assocpv_idx",
        "phi_k1_assocpv_idx", "phi_k2_assocpv_idx",
        "jpsi1_mu1_assocpv_x", "jpsi1_mu1_assocpv_y", "jpsi1_mu1_assocpv_z",
        "jpsi1_mu2_assocpv_x", "jpsi1_mu2_assocpv_y", "jpsi1_mu2_assocpv_z",
        "jpsi2_mu1_assocpv_x", "jpsi2_mu1_assocpv_y", "jpsi2_mu1_assocpv_z",
        "jpsi2_mu2_assocpv_x", "jpsi2_mu2_assocpv_y", "jpsi2_mu2_assocpv_z",
        "phi_k1_assocpv_x", "phi_k1_assocpv_y", "phi_k1_assocpv_z",
        "phi_k2_assocpv_x", "phi_k2_assocpv_y", "phi_k2_assocpv_z",
        "jpsi1_mu1_assocpv_xerr", "jpsi1_mu1_assocpv_yerr", "jpsi1_mu1_assocpv_zerr",
        "jpsi1_mu2_assocpv_xerr", "jpsi1_mu2_assocpv_yerr", "jpsi1_mu2_assocpv_zerr",
        "jpsi2_mu1_assocpv_xerr", "jpsi2_mu1_assocpv_yerr", "jpsi2_mu1_assocpv_zerr",
        "jpsi2_mu2_assocpv_xerr", "jpsi2_mu2_assocpv_yerr", "jpsi2_mu2_assocpv_zerr",
        "phi_k1_assocpv_xerr", "phi_k1_assocpv_yerr", "phi_k1_assocpv_zerr",
        "phi_k2_assocpv_xerr", "phi_k2_assocpv_yerr", "phi_k2_assocpv_zerr",
        "jpsi1_mu1_assocpv_xyerr", "jpsi1_mu2_assocpv_xyerr", "jpsi2_mu1_assocpv_xyerr", "jpsi2_mu2_assocpv_xyerr",
        "phi_k1_assocpv_xyerr", "phi_k2_assocpv_xyerr",
        "jpsi1_assocpv_x", "jpsi1_assocpv_y", "jpsi1_assocpv_z",
        "jpsi2_assocpv_x", "jpsi2_assocpv_y", "jpsi2_assocpv_z",
        "phi_assocpv_x", "phi_assocpv_y", "phi_assocpv_z",
        "jpsi1_assocpv_xerr", "jpsi1_assocpv_yerr", "jpsi1_assocpv_zerr",
        "jpsi2_assocpv_xerr", "jpsi2_assocpv_yerr", "jpsi2_assocpv_zerr",
        "phi_assocpv_xerr", "phi_assocpv_yerr", "phi_assocpv_zerr",
        "jpsi1_dz_assocpv", "jpsi2_dz_assocpv", "phi_dz_assocpv",
        "jpsi1_dxy_assocpv", "jpsi2_dxy_assocpv", "phi_dxy_assocpv",
        "jpsi1_dz_assocpv_sigma", "jpsi2_dz_assocpv_sigma", "phi_dz_assocpv_sigma",
        "jpsi1_dxy_assocpv_sigma", "jpsi2_dxy_assocpv_sigma", "phi_dxy_assocpv_sigma",
        "delta_dz_jpsi1_jpsi2", "delta_dxy_jpsi1_jpsi2", "Dz_jpsi1_jpsi2", "Dxy_jpsi1_jpsi2", "D_jpsi1_jpsi2",
        "delta_dz_jpsi1_phi", "delta_dxy_jpsi1_phi", "Dz_jpsi1_phi", "Dxy_jpsi1_phi", "D_jpsi1_phi",
        "delta_dz_jpsi2_phi", "delta_dxy_jpsi2_phi", "Dz_jpsi2_phi", "Dxy_jpsi2_phi", "D_jpsi2_phi",
        "D3_max",
    ]
    snapshot_columns = list(dict.fromkeys(original_branches + derived))

    count_action = rdf.Count()
    options = ROOT.RDF.RSnapshotOptions()
    options.fMode = "RECREATE"
    options.fLazy = True
    snapshot_action = rdf.Snapshot(INPUT_TREE, output_file, build_root_string_vector(snapshot_columns), options)
    ROOT.RDF.RunGraphs([count_action, snapshot_action])
    return int(count_action.GetValue())


def load_arrays(file_name: str, branches: list[str]) -> dict[str, np.ndarray]:
    arrays = uproot.open(file_name)[INPUT_TREE].arrays(branches, library="np")
    return {name: np.asarray(values) for name, values in arrays.items()}


def finite_mask(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return np.isfinite(np.asarray(values, dtype=float)) & np.isfinite(np.asarray(weights, dtype=float))


def weighted_histogram(values: np.ndarray, weights: np.ndarray, edges: np.ndarray):
    counts, _ = np.histogram(values, bins=edges, weights=weights)
    sumw2, _ = np.histogram(values, bins=edges, weights=np.square(weights))
    return counts.astype(float), sumw2.astype(float)


def ratio_with_uncertainty(numerator: np.ndarray, numerator_err: np.ndarray, denominator: np.ndarray, denominator_err: np.ndarray):
    ratio = np.full_like(numerator, np.nan, dtype=float)
    ratio_err = np.full_like(numerator, np.nan, dtype=float)
    valid = np.isfinite(numerator) & np.isfinite(denominator) & np.isfinite(numerator_err) & np.isfinite(denominator_err) & (denominator != 0.0)
    ratio[valid] = numerator[valid] / denominator[valid]
    ratio_err[valid] = np.sqrt(
        np.square(numerator_err[valid] / denominator[valid]) +
        np.square(numerator[valid] * denominator_err[valid] / np.square(denominator[valid]))
    )
    return ratio, ratio_err


def choose_ratio_ylim(reference: np.ndarray, variations: list[np.ndarray]) -> tuple[float, float]:
    finite = []
    for arr in [reference] + variations:
        arr_finite = arr[np.isfinite(arr)]
        if arr_finite.size:
            finite.append(arr_finite)
    if not finite:
        return 0.4, 1.6
    values = np.concatenate(finite)
    low = float(np.nanpercentile(values, 5))
    high = float(np.nanpercentile(values, 95))
    low = min(low, 1.0) - 0.15
    high = max(high, 1.0) + 0.15
    if low >= high:
        return 0.4, 1.6
    return max(-1.5, low), min(3.5, high)


def choose_pri_vtxz_edges(arrays_by_category: dict[str, dict[str, np.ndarray]]) -> np.ndarray:
    finite = []
    for arrays in arrays_by_category.values():
        values = np.asarray(arrays["priVtxZ"], dtype=float)
        values = values[np.isfinite(values)]
        if values.size:
            finite.append(values)
    if not finite:
        return np.linspace(-20.0, 20.0, DEFAULT_Z_BINS + 1)
    merged = np.concatenate(finite)
    q_lo, q_hi = np.quantile(merged, [0.005, 0.995])
    limit = max(abs(float(q_lo)), abs(float(q_hi)), 15.0)
    return np.linspace(-limit, limit, DEFAULT_Z_BINS + 1)


def choose_npv_edges(arrays_by_category: dict[str, dict[str, np.ndarray]]) -> np.ndarray:
    max_val = 40.0
    for arrays in arrays_by_category.values():
        values = np.asarray(arrays["nGoodPrimVtx"], dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size:
            max_val = max(max_val, float(np.max(finite)))
    upper = max(50.0, 10.0 * math.ceil((max_val + 1.0) / 10.0))
    return np.asarray([0.0, 10.0, 20.0, 30.0, 40.0, upper], dtype=float)


def choose_d_edges(arrays_by_category: dict[str, dict[str, np.ndarray]], branch: str) -> np.ndarray:
    return np.linspace(0.0, 50.0, DEFAULT_D_BINS + 1)


def build_plot_specs(arrays_by_category: dict[str, dict[str, np.ndarray]]) -> list[PlotSpec]:
    specs = [
        PlotSpec("nGoodPrimVtx", r"$N_{\mathrm{good\ PV}}$", r"$N_{\mathrm{good\ PV}}$", edges=tuple(choose_npv_edges(arrays_by_category))),
        PlotSpec("priVtxZ", r"Primary vertex $z$", r"priVtxZ [cm]", edges=tuple(choose_pri_vtxz_edges(arrays_by_category))),
        PlotSpec("D_jpsi1_jpsi2", r"$D(J/\psi_1, J/\psi_2)$", r"$D(J/\psi_1, J/\psi_2)$", edges=tuple(choose_d_edges(arrays_by_category, "D_jpsi1_jpsi2"))),
        PlotSpec("D_jpsi1_phi", r"$D(J/\psi_1, \phi)$", r"$D(J/\psi_1, \phi)$", edges=tuple(choose_d_edges(arrays_by_category, "D_jpsi1_phi"))),
        PlotSpec("D_jpsi2_phi", r"$D(J/\psi_2, \phi)$", r"$D(J/\psi_2, \phi)$", edges=tuple(choose_d_edges(arrays_by_category, "D_jpsi2_phi"))),
        PlotSpec("D3_max", r"$D_{3,\max}$", r"$D_{3,\max}$", edges=tuple(choose_d_edges(arrays_by_category, "D3_max"))),
    ]
    return specs


def save_comparison_plot(category: Category, arrays: dict[str, np.ndarray], plot_spec: PlotSpec, output_dir: str):
    ensure_dir(output_dir)

    if plot_spec.edges is None:
        raise RuntimeError(f"Plot edges were not configured for {plot_spec.key}")
    edges = np.asarray(plot_spec.edges, dtype=float)
    centers = 0.5 * (edges[:-1] + edges[1:])
    base_values = np.asarray(arrays[plot_spec.key], dtype=float)
    base_weights = np.ones(base_values.shape[0], dtype=float) if category.weight_branch is None else np.asarray(arrays[category.weight_branch], dtype=float)

    histograms = {}
    colors = {"no_cut": "black", "assocpv": "#0072B2", "vtxprob": "#D55E00"}
    markers = {"no_cut": "o", "assocpv": "s", "vtxprob": "^"}

    for scenario in SCENARIOS:
        scenario_mask = finite_mask(base_values, base_weights)
        if scenario.mask_branch is not None:
            scenario_mask &= np.asarray(arrays[scenario.mask_branch], dtype=bool)
        values = base_values[scenario_mask]
        weights = base_weights[scenario_mask]
        counts, sumw2 = weighted_histogram(values, weights, edges)
        histograms[scenario.key] = {
            "counts": counts,
            "errors": np.sqrt(sumw2),
            "yield": float(np.sum(weights)),
        }

    ref_counts = histograms["no_cut"]["counts"]
    ref_errors = histograms["no_cut"]["errors"]

    fig, (ax, rax) = plt.subplots(
        2,
        1,
        figsize=(10.5, 9.0),
        sharex=True,
        gridspec_kw={"height_ratios": [3.5, 1.25], "hspace": 0.05},
    )

    ratio_variations = []
    for scenario in SCENARIOS:
        counts = histograms[scenario.key]["counts"]
        errors = histograms[scenario.key]["errors"]
        label = f"{scenario.label} ({histograms[scenario.key]['yield']:.1f})"
        hep.histplot(
            counts,
            edges,
            yerr=errors,
            histtype="errorbar",
            color=colors[scenario.key],
            markersize=4,
            elinewidth=1.2,
            capsize=0,
            ax=ax,
            label=label,
        )
        if scenario.key == "no_cut":
            continue
        ratio, ratio_err = ratio_with_uncertainty(counts, errors, ref_counts, ref_errors)
        ratio_variations.append(ratio)
        valid = np.isfinite(ratio) & np.isfinite(ratio_err)
        if np.any(valid):
            rax.errorbar(
                centers[valid],
                ratio[valid],
                yerr=ratio_err[valid],
                fmt=markers[scenario.key],
                color=colors[scenario.key],
                markersize=4,
                linewidth=1.0,
            )

    ax.set_title(plot_spec.title)
    ax.set_ylabel("Events / bin" if category.weight_branch is None else "Weighted events / bin")
    hep.cms.label("Work in progress", data=True, ax=ax)
    ax.legend(loc="best")
    ax.grid(True, axis="y", alpha=0.25)

    rax.axhline(1.0, color="0.35", linestyle="--", linewidth=1.0)
    rax.set_ylabel("cut / no cut")
    rax.set_xlabel(plot_spec.xlabel)
    rax.set_ylim(*choose_ratio_ylim(np.ones_like(ref_counts), ratio_variations))
    rax.grid(True, axis="y", alpha=0.25)

    fig.subplots_adjust(left=0.12, right=0.97, top=0.93, bottom=0.08, hspace=0.05)
    output_base = os.path.join(output_dir, plot_spec.key)
    fig.savefig(output_base + ".pdf")
    fig.savefig(output_base + ".png")
    plt.close(fig)


def main():
    args = parse_args()
    if args.max_events > 0 and args.jobs > 1:
        print("[INFO] --max-events with RDataFrame implicit MT is unstable; setting jobs to 1")
        args.jobs = 1

    weighted_input, sideband_input, weighted_output, sideband_output, plot_dir = default_paths(args)
    ensure_dir(plot_dir)
    plt.style.use(hep.style.CMS)

    print("=" * 80)
    print("vertex-cut pileup study on sPlot/sideband selections")
    print("=" * 80)
    print(f"[INFO] weighted input  : {weighted_input}")
    print(f"[INFO] sideband input  : {sideband_input}")
    print(f"[INFO] weighted output : {weighted_output}")
    print(f"[INFO] sideband output : {sideband_output}")
    print(f"[INFO] plot dir        : {plot_dir}")
    print(f"[INFO] jobs            : {args.jobs}")
    print(f"[INFO] max events      : {args.max_events}")
    print("=" * 80)

    if args.force or not os.path.exists(weighted_output):
        n_weighted = augment_file(weighted_input, weighted_output, args.jobs, args.max_events)
        print(f"[INFO] augmented weighted entries : {n_weighted}")
    else:
        print(f"[INFO] reuse augmented weighted file : {weighted_output}")

    if args.force or not os.path.exists(sideband_output):
        n_sideband = augment_file(sideband_input, sideband_output, args.jobs, args.max_events)
        print(f"[INFO] augmented sideband entries : {n_sideband}")
    else:
        print(f"[INFO] reuse augmented sideband file : {sideband_output}")

    plot_branches = ["nGoodPrimVtx", "priVtxZ", "signal_sw", "pass_assocpv_cut", "pass_vtxprob_cut", *D_BRANCHES, "D3_max"]
    arrays_by_category = {
        "overall": load_arrays(weighted_output, plot_branches),
        "signal": load_arrays(weighted_output, plot_branches),
        "sideband_bkg": load_arrays(sideband_output, plot_branches),
    }
    plot_specs = build_plot_specs(arrays_by_category)

    for category in CATEGORIES:
        category_dir = os.path.join(plot_dir, category.output_subdir)
        for plot_spec in plot_specs:
            save_comparison_plot(category, arrays_by_category[category.key], plot_spec, category_dir)
        print(f"[INFO] saved plots for {category.key} into {category_dir}")

    print("[INFO] D_ij and D3_max were written into the augmented output ROOT files")
    return 0


if __name__ == "__main__":
    sys.exit(main())

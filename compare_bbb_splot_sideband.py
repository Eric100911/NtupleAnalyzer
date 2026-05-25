#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare the sPlot BBB background shape against a three-body sideband sample."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import OrderedDict

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
import ROOT
import uproot

import fit_splot as fit_core
import fit_splot_with_kinematic_cuts as cut_flow
import plot_weighted_distributions as plot_helpers
from ntuple_pipeline_common import (
    default_merged_output,
    default_plot_dir,
    default_weighted_output,
    ensure_dir,
    ensure_parent_dir,
    get_tree_branches,
)


INPUT_TREE = "selected"
BACKGROUND_WEIGHT_BRANCH = "yield_bbb_sw"
FIT_BRANCHES = ("sel_Jpsi_1_mass", "sel_Jpsi_2_mass", "sel_Phi_mass")
DEFAULT_SIGNAL_NSIGMA = 3.0
DEFAULT_JPSI_SB_INNER = 4.0
DEFAULT_JPSI_SB_OUTER = 8.0
DEFAULT_PHI_SB_INNER = 4.0
DEFAULT_PHI_SB_OUTER = 8.0


def parse_args():
    parser = argparse.ArgumentParser(description="Compare sPlot BBB background with a three-body sideband sample")
    parser.add_argument("--channel", default="JJP", choices=["JJP", "jjp"], help="Only JJP is supported in this workflow")
    parser.add_argument("--dataset", default="data", choices=["data"], help="Only data is supported in this workflow")
    parser.add_argument("-i", "--input", default=None, help="Input selected ROOT file")
    parser.add_argument("-o", "--output", default=None, help="Output weighted ROOT file with sWeights")
    parser.add_argument("--filtered-output", default=None, help="Output ROOT file after the pre-fit cuts")
    parser.add_argument("--sideband-output", default=None, help="Output ROOT file containing only sideband events")
    parser.add_argument("--plot-dir", default=None, help="Output directory for fit plots and comparison plots")
    parser.add_argument("--metrics-json", default=None, help="JSON file with sideband-vs-sPlot comparison metrics")
    parser.add_argument("--signal-nsigma", type=float, default=DEFAULT_SIGNAL_NSIGMA, help="Half-width of the signal window in fitted sigma units")
    parser.add_argument("--jpsi-sideband-inner", type=float, default=DEFAULT_JPSI_SB_INNER, help="Inner J/psi sideband boundary in sigma units")
    parser.add_argument("--jpsi-sideband-outer", type=float, default=DEFAULT_JPSI_SB_OUTER, help="Outer J/psi sideband boundary in sigma units")
    parser.add_argument("--phi-sideband-inner", type=float, default=DEFAULT_PHI_SB_INNER, help="Inner phi sideband boundary in sigma units")
    parser.add_argument("--phi-sideband-outer", type=float, default=DEFAULT_PHI_SB_OUTER, help="Outer phi sideband boundary in sigma units")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="RDataFrame / RooFit thread count")
    parser.add_argument("-n", "--max-events", type=int, default=-1, help="Limit events for quick tests")
    return parser.parse_args()


def derived_output(path: str, suffix: str) -> str:
    if path.endswith(".root"):
        return path[:-5] + suffix + ".root"
    return path + suffix + ".root"


def default_paths(args):
    input_file = args.input or default_merged_output("JJP", "data")
    weighted_output = args.output or derived_output(default_weighted_output("JJP", "data"), "_bbb_sideband_compare")
    filtered_output = args.filtered_output or derived_output(weighted_output, "_prefit_selected")
    sideband_output = args.sideband_output or derived_output(weighted_output, "_sideband_only")
    plot_dir = args.plot_dir or os.path.join(default_plot_dir("JJP", "data"), "bbb_sideband_compare")
    metrics_json = args.metrics_json or os.path.join(plot_dir, "bbb_sideband_metrics.json")
    return input_file, weighted_output, filtered_output, sideband_output, plot_dir, metrics_json


def validate_args(args):
    if args.signal_nsigma <= 0.0:
        raise ValueError("--signal-nsigma must be positive")
    if args.jpsi_sideband_inner <= args.signal_nsigma:
        raise ValueError("--jpsi-sideband-inner must be larger than --signal-nsigma")
    if args.jpsi_sideband_outer <= args.jpsi_sideband_inner:
        raise ValueError("--jpsi-sideband-outer must be larger than --jpsi-sideband-inner")
    if args.phi_sideband_inner <= args.signal_nsigma:
        raise ValueError("--phi-sideband-inner must be larger than --signal-nsigma")
    if args.phi_sideband_outer <= args.phi_sideband_inner:
        raise ValueError("--phi-sideband-outer must be larger than --phi-sideband-inner")


def get_roofit_value(objects: dict, name: str) -> float:
    obj = objects.get(name)
    if obj is None:
        raise KeyError(f"RooFit object '{name}' not found")
    if hasattr(obj, "getVal"):
        return float(obj.getVal())
    raise TypeError(f"RooFit object '{name}' does not expose getVal()")


def clipped_interval(lo: float, hi: float, min_value: float, max_value: float) -> list[float] | None:
    left = max(lo, min_value)
    right = min(hi, max_value)
    if not math.isfinite(left) or not math.isfinite(right) or left >= right:
        return None
    return [float(left), float(right)]


def build_mass_windows(fit_summary: dict, args) -> dict:
    params = fit_summary["fit_parameters"]
    fit_ranges = fit_summary["fit_ranges"]

    windows = {}

    for branch, mean_key, sigma_key in (
        ("sel_Jpsi_1_mass", "jpsi1_mean", "jpsi1_sigma"),
        ("sel_Jpsi_2_mass", "jpsi2_mean", "jpsi2_sigma"),
    ):
        mean = params[mean_key]
        sigma = params[sigma_key]
        min_value, max_value = fit_ranges[branch]
        signal = clipped_interval(
            mean - args.signal_nsigma * sigma,
            mean + args.signal_nsigma * sigma,
            min_value,
            max_value,
        )
        left_sb = clipped_interval(
            mean - args.jpsi_sideband_outer * sigma,
            mean - args.jpsi_sideband_inner * sigma,
            min_value,
            max_value,
        )
        right_sb = clipped_interval(
            mean + args.jpsi_sideband_inner * sigma,
            mean + args.jpsi_sideband_outer * sigma,
            min_value,
            max_value,
        )
        sidebands = [interval for interval in (left_sb, right_sb) if interval is not None]
        if signal is None or len(sidebands) != 2:
            raise RuntimeError(f"Failed to build valid J/psi sidebands for {branch}")
        windows[branch] = {
            "mean": mean,
            "sigma": sigma,
            "signal": signal,
            "sidebands": sidebands,
            "sideband_mode": "symmetric",
        }

    phi_mean = params["phi_mean"]
    phi_sigma = math.sqrt(params["phi_sigma"] ** 2 + params["phi_width"] ** 2)
    phi_min, phi_max = fit_ranges["sel_Phi_mass"]
    phi_signal = clipped_interval(
        phi_mean - args.signal_nsigma * phi_sigma,
        phi_mean + args.signal_nsigma * phi_sigma,
        phi_min,
        phi_max,
    )
    phi_right_sb = clipped_interval(
        phi_mean + args.phi_sideband_inner * phi_sigma,
        phi_mean + args.phi_sideband_outer * phi_sigma,
        phi_min,
        phi_max,
    )
    if phi_signal is None or phi_right_sb is None:
        raise RuntimeError("Failed to build a valid right-side phi sideband")
    windows["sel_Phi_mass"] = {
        "mean": phi_mean,
        "sigma": phi_sigma,
        "signal": phi_signal,
        "sidebands": [phi_right_sb],
        "sideband_mode": "right_only",
    }
    return windows


def build_sideband_expression(windows: dict) -> str:
    clauses = []
    for branch in FIT_BRANCHES:
        sidebands = windows[branch]["sidebands"]
        pieces = [f"({branch} >= {lo:.9g} && {branch} <= {hi:.9g})" for lo, hi in sidebands]
        clauses.append("(" + " || ".join(pieces) + ")")
    return " && ".join(clauses)


def snapshot_sideband_tree(weighted_output: str, sideband_output: str, sideband_expression: str, jobs: int) -> int:
    ensure_parent_dir(sideband_output)
    available_branches = sorted(get_tree_branches(weighted_output, INPUT_TREE))
    if jobs > 1:
        ROOT.EnableImplicitMT(jobs)
    rdf = ROOT.RDataFrame(INPUT_TREE, weighted_output)
    filtered = rdf.Filter(sideband_expression, "bbb_sideband")
    count_action = filtered.Count()
    options = ROOT.RDF.RSnapshotOptions()
    options.fMode = "RECREATE"
    options.fLazy = True
    snapshot_action = filtered.Snapshot(INPUT_TREE, sideband_output, cut_flow.build_root_string_vector(available_branches), options)
    ROOT.RDF.RunGraphs([count_action, snapshot_action])
    return int(count_action.GetValue())


def run_fit_and_sweights(filtered_input: str, output_file: str, fit_plot_dir: str, jobs: int) -> dict:
    summary = uproot.open(filtered_input)[INPUT_TREE]
    n_entries = summary.num_entries
    if n_entries <= 0:
        raise RuntimeError(f"No events left after pre-fit cuts in {filtered_input}")

    ROOT.gROOT.SetBatch(True)
    ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.WARNING)

    fin = ROOT.TFile.Open(filtered_input)
    tree = fin.Get(INPUT_TREE)
    if not tree:
        fin.Close()
        raise RuntimeError(f"Input tree '{INPUT_TREE}' not found in {filtered_input}")

    model, observables, yields, signal_yield_name, keepalive = fit_core.build_jjp_model(n_entries, mc_two_component=False)
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

    fit_core.save_projection_plots("JJP", fit_plot_dir, data, model, observables, signal_yield_name, yields)
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

    named_objects = {
        obj.GetName(): obj for obj in keepalive if hasattr(obj, "GetName")
    }
    fit_summary = {
        "n_entries": int(data.numEntries()),
        "signal_yield_name": signal_yield_name,
        "yields": {name: float(var.getVal()) for name, var in yields.items()},
        "fit_parameters": {
            "jpsi1_mean": get_roofit_value(named_objects, "jpsi1_mean"),
            "jpsi1_sigma": get_roofit_value(named_objects, "jpsi1_sigma"),
            "jpsi2_mean": get_roofit_value(named_objects, "jpsi2_mean"),
            "jpsi2_sigma": get_roofit_value(named_objects, "jpsi2_sigma"),
            "phi_mean": get_roofit_value(named_objects, "phi_mean"),
            "phi_sigma": get_roofit_value(named_objects, "phi_sigma"),
            "phi_width": get_roofit_value(named_objects, "phi_width"),
        },
        "fit_ranges": {
            name: [float(obs.getMin()), float(obs.getMax())] for name, obs in observables.items()
        },
        "significance": {
            "signal_yield": float(significance["signal_yield"]),
            "background_yield": float(significance["background_yield"]),
            "q0": float(significance["q0"]),
            "lrt_significance": float(significance["lrt_significance"]),
        },
    }

    fin.Close()
    return fit_summary


def discover_comparison_branches(tree) -> list[str]:
    branches = []
    excluded = set(FIT_BRANCHES)
    for name in plot_helpers.discover_plot_columns(tree):
        if name in excluded:
            continue
        if name.endswith("_Idx"):
            continue
        if name.endswith(("_massErr", "_massDiff", "_Chi2", "_ndof", "_VtxProb")):
            continue
        if name.startswith(("sel_abs_dy_", "sel_abs_dphi_", "sel_m_")):
            branches.append(name)
            continue
        if name.endswith(("_pt", "_eta", "_phi", "_y", "_ctau", "_mass")):
            branches.append(name)
    return sorted(set(branches))


def weighted_histogram(values: np.ndarray, weights: np.ndarray, edges: np.ndarray):
    counts, _ = np.histogram(values, bins=edges, weights=weights)
    sumw2, _ = np.histogram(values, bins=edges, weights=np.square(weights))
    return counts.astype(float), sumw2.astype(float)


def normalize_hist(counts: np.ndarray, sumw2: np.ndarray):
    total = float(np.sum(counts))
    if not math.isfinite(total) or abs(total) <= 0.0:
        raise RuntimeError("Histogram normalization failed because the integral is zero")
    norm = counts / total
    err = np.sqrt(sumw2) / abs(total)
    return norm, err, total


def js_divergence(p: np.ndarray, q: np.ndarray) -> float:
    p_pos = np.clip(np.asarray(p, dtype=float), 0.0, None)
    q_pos = np.clip(np.asarray(q, dtype=float), 0.0, None)
    p_sum = float(np.sum(p_pos))
    q_sum = float(np.sum(q_pos))
    if p_sum <= 0.0 or q_sum <= 0.0:
        return float("nan")
    p_pos /= p_sum
    q_pos /= q_sum
    m = 0.5 * (p_pos + q_pos)
    valid_p = (p_pos > 0.0) & (m > 0.0)
    valid_q = (q_pos > 0.0) & (m > 0.0)
    kl_pm = float(np.sum(p_pos[valid_p] * np.log(p_pos[valid_p] / m[valid_p])))
    kl_qm = float(np.sum(q_pos[valid_q] * np.log(q_pos[valid_q] / m[valid_q])))
    return 0.5 * (kl_pm + kl_qm)


def compute_metrics(splot_norm: np.ndarray, splot_err: np.ndarray, sideband_norm: np.ndarray, sideband_err: np.ndarray) -> dict:
    variance = np.square(splot_err) + np.square(sideband_err)
    valid = variance > 0.0
    ndf = int(np.count_nonzero(valid) - 1)
    chi2 = float(np.sum(np.square(splot_norm[valid] - sideband_norm[valid]) / variance[valid])) if np.any(valid) else float("nan")
    p_value = float(ROOT.TMath.Prob(chi2, ndf)) if ndf > 0 and math.isfinite(chi2) else float("nan")
    pull = np.full_like(splot_norm, np.nan, dtype=float)
    pull[valid] = (sideband_norm[valid] - splot_norm[valid]) / np.sqrt(variance[valid])
    return {
        "chi2": chi2,
        "ndf": ndf,
        "chi2_ndf": float(chi2 / ndf) if ndf > 0 and math.isfinite(chi2) else float("nan"),
        "p_value": p_value,
        "max_abs_pull": float(np.nanmax(np.abs(pull))) if np.any(np.isfinite(pull)) else float("nan"),
        "l1_distance": float(np.sum(np.abs(sideband_norm - splot_norm))),
        "js_divergence": float(js_divergence(splot_norm, sideband_norm)),
        "n_valid_bins": int(np.count_nonzero(valid)),
    }


def ratio_with_uncertainty(numerator: np.ndarray, numerator_err: np.ndarray, denominator: np.ndarray, denominator_err: np.ndarray):
    ratio = np.full_like(numerator, np.nan, dtype=float)
    ratio_err = np.full_like(numerator, np.nan, dtype=float)
    valid = np.isfinite(numerator) & np.isfinite(denominator) & np.isfinite(numerator_err) & np.isfinite(denominator_err) & (denominator > 0.0)
    ratio[valid] = numerator[valid] / denominator[valid]
    ratio_err[valid] = np.sqrt(
        np.square(numerator_err[valid] / denominator[valid]) +
        np.square(numerator[valid] * denominator_err[valid] / np.square(denominator[valid]))
    )
    return ratio, ratio_err


def choose_ratio_ylim(ratio: np.ndarray) -> tuple[float, float]:
    finite = ratio[np.isfinite(ratio)]
    if finite.size == 0:
        return 0.5, 1.5
    low = min(0.95, float(np.nanpercentile(finite, 5)) - 0.15)
    high = max(1.05, float(np.nanpercentile(finite, 95)) + 0.15)
    low = max(0.0, low)
    if high <= low:
        return 0.5, 1.5
    return low, min(3.0, high)


def plot_branch_comparison(
    branch: str,
    edges: np.ndarray,
    splot_norm: np.ndarray,
    splot_err: np.ndarray,
    sideband_norm: np.ndarray,
    sideband_err: np.ndarray,
    metrics: dict,
    output_base: str,
    splot_total: float,
    sideband_total: float,
):
    centers = 0.5 * (edges[1:] + edges[:-1])
    ratio, ratio_err = ratio_with_uncertainty(sideband_norm, sideband_err, splot_norm, splot_err)

    fig, (ax, rax) = plt.subplots(
        2,
        1,
        figsize=(10.5, 9.0),
        sharex=True,
        gridspec_kw={"height_ratios": [3.6, 1.3], "hspace": 0.05},
    )
    hep.histplot(splot_norm, edges, yerr=splot_err, histtype="errorbar", color="black", markersize=4, elinewidth=1.2, capsize=0, ax=ax, label="sPlot BBB")
    hep.histplot(sideband_norm, edges, yerr=sideband_err, histtype="errorbar", color="tab:red", markersize=4, elinewidth=1.2, capsize=0, ax=ax, label="Sideband")
    ax.set_ylabel("Normalized events / bin")
    ax.set_title(plot_helpers.label_for_branch(branch))
    hep.cms.label("Work in progress", data=True, ax=ax)
    ax.legend(loc="best")

    textbox = "\n".join([
        rf"$\chi^2/\mathrm{{ndf}} = {metrics['chi2_ndf']:.2f}$" if math.isfinite(metrics["chi2_ndf"]) else r"$\chi^2/\mathrm{ndf} = \mathrm{nan}$",
        rf"$p = {metrics['p_value']:.3g}$" if math.isfinite(metrics["p_value"]) else r"$p = \mathrm{nan}$",
        rf"$L_1 = {metrics['l1_distance']:.3f}$",
        rf"$JS = {metrics['js_divergence']:.3g}$" if math.isfinite(metrics["js_divergence"]) else r"$JS = \mathrm{nan}$",
        rf"$N_{{\mathrm{{SB}}}} = {sideband_total:.0f}$",
        rf"$\sum w_{{\mathrm{{BBB}}}} = {splot_total:.1f}$",
    ])
    ax.text(
        0.98,
        0.97,
        textbox,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=11,
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.88, "edgecolor": "0.5"},
    )

    if branch.endswith("_ctau"):
        positive = np.concatenate([splot_norm[splot_norm > 0.0], sideband_norm[sideband_norm > 0.0]])
        if positive.size:
            ax.set_yscale("log")
            ax.set_ylim(max(float(np.min(positive)) * 0.6, 1.0e-5), float(np.max(positive)) * 2.0)

    rax.axhline(1.0, color="0.35", linestyle="--", linewidth=1.0)
    valid_ratio = np.isfinite(ratio) & np.isfinite(ratio_err)
    if np.any(valid_ratio):
        rax.errorbar(centers[valid_ratio], ratio[valid_ratio], yerr=ratio_err[valid_ratio], fmt="o", color="tab:red", markersize=4, linewidth=1.0)
    rax.set_ylabel("SB / sPlot")
    rax.set_xlabel(plot_helpers.label_for_branch(branch))
    rax.set_ylim(*choose_ratio_ylim(ratio))
    rax.grid(True, axis="y", alpha=0.25)

    fig.subplots_adjust(left=0.12, right=0.97, top=0.93, bottom=0.08, hspace=0.05)
    fig.savefig(output_base + ".pdf")
    fig.savefig(output_base + ".png")
    plt.close(fig)


def compare_backgrounds(weighted_output: str, sideband_output: str, plot_dir: str, metrics_json: str, windows: dict) -> dict:
    ensure_dir(plot_dir)
    tree = uproot.open(weighted_output)[INPUT_TREE]
    sideband_tree = uproot.open(sideband_output)[INPUT_TREE]
    plot_helpers.apply_cms_style()

    branches = discover_comparison_branches(tree)
    read_branches = sorted(set(branches + [BACKGROUND_WEIGHT_BRANCH] + list(FIT_BRANCHES)))
    arrays = tree.arrays(read_branches, library="np")
    sideband_entries = int(sideband_tree.num_entries)

    sideband_mask = np.ones(tree.num_entries, dtype=bool)
    for branch in FIT_BRANCHES:
        branch_values = np.asarray(arrays[branch], dtype=float)
        branch_mask = np.zeros_like(sideband_mask)
        for lo, hi in windows[branch]["sidebands"]:
            branch_mask |= np.isfinite(branch_values) & (branch_values >= lo) & (branch_values <= hi)
        sideband_mask &= branch_mask

    bbb_weights = np.asarray(arrays[BACKGROUND_WEIGHT_BRANCH], dtype=float)
    if not np.isfinite(bbb_weights).all():
        raise RuntimeError(f"Non-finite values found in {BACKGROUND_WEIGHT_BRANCH}")

    if int(np.count_nonzero(sideband_mask)) != sideband_entries:
        raise RuntimeError(
            "Sideband entry mismatch between the numpy mask and the RDataFrame snapshot: "
            f"{int(np.count_nonzero(sideband_mask))} vs {sideband_entries}"
        )

    comparison = OrderedDict()
    for branch in branches:
        values = np.asarray(arrays[branch], dtype=float)
        valid = np.isfinite(values) & np.isfinite(bbb_weights)
        if not np.any(valid):
            continue

        edges = plot_helpers.bin_edges_for_branch(branch)
        splot_counts, splot_sumw2 = weighted_histogram(values[valid], bbb_weights[valid], edges)
        side_values = values[sideband_mask & np.isfinite(values)]
        side_weights = np.ones(side_values.shape[0], dtype=float)
        side_counts, side_sumw2 = weighted_histogram(side_values, side_weights, edges)

        if np.sum(side_counts) <= 0.0:
            continue
        if abs(np.sum(splot_counts)) <= 0.0:
            continue

        splot_norm, splot_err, splot_total = normalize_hist(splot_counts, splot_sumw2)
        sideband_norm, sideband_err, sideband_total = normalize_hist(side_counts, side_sumw2)
        metrics = compute_metrics(splot_norm, splot_err, sideband_norm, sideband_err)

        output_base = os.path.join(plot_dir, branch)
        plot_branch_comparison(
            branch,
            edges,
            splot_norm,
            splot_err,
            sideband_norm,
            sideband_err,
            metrics,
            output_base,
            splot_total,
            sideband_total,
        )

        comparison[branch] = {
            **metrics,
            "splot_total_weight": float(splot_total),
            "sideband_total_entries": float(sideband_total),
            "bin_edges": [float(x) for x in edges],
        }

    result = {
        "background_weight_branch": BACKGROUND_WEIGHT_BRANCH,
        "fit_mass_windows": windows,
        "sideband_entry_count": sideband_entries,
        "n_compared_branches": len(comparison),
        "variables": comparison,
    }

    ensure_parent_dir(metrics_json)
    with open(metrics_json, "w", encoding="utf-8") as fout:
        json.dump(result, fout, indent=2, sort_keys=False)
    return result


def print_top_differences(metrics: dict, top_n: int = 10):
    variables = metrics.get("variables", {})
    ranked = []
    for branch, values in variables.items():
        score = values.get("chi2_ndf", float("nan"))
        if math.isfinite(score):
            ranked.append((score, branch, values))
    ranked.sort(reverse=True)
    print("=" * 80)
    print(f"[INFO] compared branches      : {metrics.get('n_compared_branches', 0)}")
    print(f"[INFO] sideband event count   : {metrics.get('sideband_entry_count', 0)}")
    print(f"[INFO] top {min(top_n, len(ranked))} branch differences by chi2/ndf")
    for score, branch, values in ranked[:top_n]:
        print(
            f"[DIFF] {branch:<24} chi2/ndf={score:7.3f}  "
            f"p={values['p_value']:.3g}  JS={values['js_divergence']:.3g}  "
            f"max|pull|={values['max_abs_pull']:.3f}"
        )


def main():
    args = parse_args()
    validate_args(args)

    if args.max_events > 0 and args.jobs > 1:
        print("[INFO] --max-events with RDataFrame implicit MT is unstable; setting jobs to 1")
        args.jobs = 1

    input_file, weighted_output, filtered_output, sideband_output, plot_dir, metrics_json = default_paths(args)
    fit_plot_dir = os.path.join(plot_dir, "fit")
    compare_plot_dir = os.path.join(plot_dir, "comparison")

    ensure_parent_dir(weighted_output)
    ensure_parent_dir(filtered_output)
    ensure_parent_dir(sideband_output)
    ensure_dir(fit_plot_dir)
    ensure_dir(compare_plot_dir)

    print("=" * 80)
    print("assocPV BBB sPlot vs sideband comparison")
    print("=" * 80)
    print(f"[INFO] channel         : JJP")
    print(f"[INFO] dataset         : data")
    print(f"[INFO] input           : {input_file}")
    print(f"[INFO] filtered output : {filtered_output}")
    print(f"[INFO] weighted output : {weighted_output}")
    print(f"[INFO] sideband output : {sideband_output}")
    print(f"[INFO] plot dir        : {plot_dir}")
    print(f"[INFO] metrics json    : {metrics_json}")
    print(f"[INFO] jobs            : {args.jobs}")
    print(f"[INFO] max events      : {args.max_events}")
    print("=" * 80)

    total, passed, report, warnings, filters = cut_flow.run_prefit_filter(input_file, filtered_output, "JJP", args.jobs, args.max_events)
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

    fit_summary = run_fit_and_sweights(filtered_output, weighted_output, fit_plot_dir, args.jobs)
    windows = build_mass_windows(fit_summary, args)
    sideband_expression = build_sideband_expression(windows)
    sideband_entries = snapshot_sideband_tree(weighted_output, sideband_output, sideband_expression, args.jobs)
    metrics = compare_backgrounds(weighted_output, sideband_output, compare_plot_dir, metrics_json, windows)

    final_summary = {
        "channel": "JJP",
        "dataset": "data",
        "input_file": input_file,
        "filtered_output": filtered_output,
        "weighted_output": weighted_output,
        "sideband_output": sideband_output,
        "plot_dir": plot_dir,
        "metrics_json": metrics_json,
        "jobs": args.jobs,
        "max_events": args.max_events,
        "prefit": {
            "input_entries": int(total),
            "passed_entries": int(passed),
            "efficiency": float((passed / total) if total > 0 else 0.0),
        },
        "sideband_expression": sideband_expression,
        "sideband_entry_count": int(sideband_entries),
        "window_settings": {
            "signal_nsigma": float(args.signal_nsigma),
            "jpsi_sideband_inner": float(args.jpsi_sideband_inner),
            "jpsi_sideband_outer": float(args.jpsi_sideband_outer),
            "phi_sideband_inner": float(args.phi_sideband_inner),
            "phi_sideband_outer": float(args.phi_sideband_outer),
        },
        "fit": fit_summary,
        "comparison": metrics,
    }

    with open(metrics_json, "w", encoding="utf-8") as fout:
        json.dump(final_summary, fout, indent=2, sort_keys=False)

    print(f"[INFO] fitted dataset entries : {fit_summary['n_entries']}")
    print(f"[INFO] BBB fitted yield       : {fit_summary['yields'][BACKGROUND_WEIGHT_BRANCH[:-3]]:.2f}")
    print(f"[INFO] sideband selection     : {sideband_expression}")
    print(f"[INFO] sideband entries       : {sideband_entries}")
    print(f"[INFO] metrics saved         : {metrics_json}")
    print_top_differences(metrics)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare weighted data and MC distributions with a Data/MC ratio panel."""

from __future__ import annotations

import argparse
import math
import os
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
import ROOT
import uproot

from ntuple_pipeline_common import (
    OUTPUT_BASE,
    default_weighted_output,
    ensure_dir,
    normalize_channel,
    normalize_sample,
)
from plot_weighted_distributions import (
    INPUT_TREE,
    apply_cms_style,
    bin_edges_for_branch,
    discover_plot_columns,
    label_for_branch,
    load_branch,
    weighted_histogram,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Compare weighted data and MC distributions")
    parser.add_argument("--channel", required=True, choices=["JJP", "JYP", "jjp", "jyp"])
    parser.add_argument("--mc-sample", required=True, help="MC sample tag, e.g. DPS_2")
    parser.add_argument("--data-input", default=None, help="Input weighted data ROOT file")
    parser.add_argument("--mc-input", default=None, help="Input weighted MC ROOT file")
    parser.add_argument("-o", "--output-dir", default=None, help="Comparison plot output directory")
    parser.add_argument("--data-weight-branch", default="signal_sw", help="Data weight branch")
    parser.add_argument("--mc-weight-branch", default="signal_sw", help="MC weight branch")
    parser.add_argument("--normalize", choices=["shape", "yield"], default="shape", help="Shape-normalize or compare weighted yields")
    return parser.parse_args()


def default_output_dir(channel: str, sample: str) -> str:
    return os.path.join(OUTPUT_BASE, "plots", f"{channel.lower()}_data_vs_mc_{sample.lower()}")


def normalize_histogram(counts: np.ndarray, variances: np.ndarray, mode: str):
    if mode == "yield":
        return counts, variances
    total = np.sum(counts)
    if total <= 0.0:
        return counts, variances
    return counts / total, variances / (total * total)


def compatibility_metrics(data_counts, data_vars, mc_counts, mc_vars, mode: str):
    variances = data_vars + mc_vars
    valid = variances > 0.0
    if not np.any(valid):
        return float("nan"), 0, float("nan")
    chi2 = float(np.sum(np.square(data_counts[valid] - mc_counts[valid]) / variances[valid]))
    ndf = int(np.count_nonzero(valid) - (1 if mode == "shape" else 0))
    if ndf <= 0:
        return chi2, 0, float("nan")
    return chi2, ndf, float(ROOT.TMath.Prob(chi2, ndf))


def ratio_with_errors(data_counts, data_vars, mc_counts, mc_vars):
    ratio = np.full_like(data_counts, np.nan, dtype=float)
    ratio_err = np.full_like(data_counts, np.nan, dtype=float)
    valid = mc_counts > 0.0
    ratio[valid] = data_counts[valid] / mc_counts[valid]

    positive_data = valid & (data_counts > 0.0)
    positive_mc = valid & (mc_counts > 0.0)
    ratio_err[positive_data] = ratio[positive_data] * np.sqrt(
        data_vars[positive_data] / np.square(data_counts[positive_data]) +
        mc_vars[positive_data] / np.square(mc_counts[positive_data])
    )
    ratio_err[positive_mc & ~positive_data] = np.sqrt(data_vars[positive_mc & ~positive_data]) / mc_counts[positive_mc & ~positive_data]
    return ratio, ratio_err


def save_comparison_plot(branch, data_counts, data_vars, mc_counts, mc_vars, output_base, mc_label: str, mode: str):
    edges = bin_edges_for_branch(branch)
    centers = 0.5 * (edges[:-1] + edges[1:])
    data_err = np.sqrt(data_vars)
    mc_err = np.sqrt(mc_vars)
    ratio, ratio_err = ratio_with_errors(data_counts, data_vars, mc_counts, mc_vars)
    chi2, ndf, pvalue = compatibility_metrics(data_counts, data_vars, mc_counts, mc_vars, mode)

    fig, (ax, rax) = plt.subplots(
        2,
        1,
        figsize=(8, 8),
        sharex=True,
        gridspec_kw={"height_ratios": (3.0, 1.0), "hspace": 0.05},
    )

    hep.histplot(mc_counts, edges, yerr=mc_err, histtype="step", linewidth=2, color="tab:red", ax=ax, label=mc_label)
    hep.histplot(data_counts, edges, yerr=data_err, histtype="errorbar", color="black", ax=ax, label="Data")
    ax.set_ylabel("Arbitrary units" if mode == "shape" else "Weighted events")
    ax.legend(loc="best")
    if branch.endswith("_ctau"):
        ax.set_xlim(-0.05, 0.1)
        ax.set_yscale("log")
        positive = np.concatenate((data_counts[data_counts > 0.0], mc_counts[mc_counts > 0.0]))
        ymin = max(np.min(positive) * 0.5, 1.0e-4) if positive.size else 1.0e-4
        ymax = max(np.max(np.concatenate((data_counts, mc_counts))) * 10.0, 1.0) if data_counts.size else 1.0
        ax.set_ylim(ymin, ymax)
    ax.text(
        0.04,
        0.96,
        "\n".join([
            f"Mode: {mode}",
            f"$\\chi^2/\\mathrm{{ndf}} = {chi2:.2f}/{ndf}$" if ndf > 0 else f"$\\chi^2 = {chi2:.2f}$",
            f"$p = {pvalue:.3g}$" if not math.isnan(pvalue) else "$p =$ n/a",
        ]),
        transform=ax.transAxes,
        ha="left",
        va="top",
        bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"},
    )
    hep.cms.label("Work in progress", data=True, ax=ax)

    rax.axhline(1.0, color="black", linestyle="--", linewidth=1)
    valid = np.isfinite(ratio)
    rax.errorbar(centers[valid], ratio[valid], yerr=ratio_err[valid], fmt="o", color="black", markersize=4)
    rax.set_ylabel("Data/MC")
    rax.set_xlabel(label_for_branch(branch))
    rax.set_ylim(0.4, 1.6)
    if branch.endswith("_ctau"):
        rax.set_xlim(-0.05, 0.1)

    fig.tight_layout()
    fig.savefig(output_base + ".pdf")
    fig.savefig(output_base + ".png")
    plt.close(fig)


def main():
    args = parse_args()
    channel = normalize_channel(args.channel)
    sample = normalize_sample(channel, args.mc_sample)
    data_input = args.data_input or default_weighted_output(channel, "data")
    mc_input = args.mc_input or default_weighted_output(channel, "mc", sample)
    output_dir = args.output_dir or default_output_dir(channel, sample)
    ensure_dir(output_dir)

    apply_cms_style()
    data_tree = uproot.open(data_input)[INPUT_TREE]
    mc_tree = uproot.open(mc_input)[INPUT_TREE]
    columns = sorted(set(discover_plot_columns(data_tree)).intersection(discover_plot_columns(mc_tree)))

    mc_label = f"MC {sample}"
    for branch in columns:
        data_values, data_weights = load_branch(data_tree, branch, args.data_weight_branch)
        mc_values, mc_weights = load_branch(mc_tree, branch, args.mc_weight_branch)
        edges = bin_edges_for_branch(branch)
        data_counts, data_vars = weighted_histogram(data_values, data_weights, edges)
        mc_counts, mc_vars = weighted_histogram(mc_values, mc_weights, edges)
        data_counts, data_vars = normalize_histogram(data_counts, data_vars, args.normalize)
        mc_counts, mc_vars = normalize_histogram(mc_counts, mc_vars, args.normalize)
        save_comparison_plot(
            branch,
            data_counts,
            data_vars,
            mc_counts,
            mc_vars,
            os.path.join(output_dir, branch),
            mc_label,
            args.normalize,
        )

    print(f"[INFO] plotted {len(columns)} Data/MC comparison distributions into {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

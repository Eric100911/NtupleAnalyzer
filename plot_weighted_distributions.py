#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plot weighted physics distributions from the sWeighted ntuple with mplhep CMS style."""

from __future__ import annotations

import argparse
import math
import os
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import mplhep as hep
import numpy as np
import uproot

from ntuple_pipeline_common import (
    CHANNEL_CONFIGS,
    default_plot_dir,
    default_weighted_output,
    ensure_dir,
    normalize_channel,
    normalize_dataset,
    normalize_sample,
)


INPUT_TREE = "selected"
DEFAULT_BINS = 30
PT_BIN_EDGES = np.asarray([0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 17.0, 21.0, 30.0, 100.0], dtype=float)


def parse_args():
    parser = argparse.ArgumentParser(description="Plot weighted assocPV distributions")
    parser.add_argument("--channel", required=True, choices=["JJP", "JUP", "jjp", "jup"])
    parser.add_argument("--dataset", default="data", choices=["data", "mc"])
    parser.add_argument("--sample", default=None, help="MC sample tag")
    parser.add_argument("-i", "--input", default=None, help="Input weighted ROOT file")
    parser.add_argument("-o", "--output-dir", default=None, help="Plot output directory")
    parser.add_argument("-w", "--weight-branch", default="signal_sw", help="Weight branch")
    return parser.parse_args()


def apply_cms_style():
    plt.style.use(hep.style.CMS)


def label_for_branch(name: str) -> str:
    label = name.replace("sel_", "").replace("_", " ")
    replacements = {
        "Jpsi": r"$J/\psi$",
        "Phi": r"$\phi$",
        "Ups": r"$\Upsilon$",
        "abs dphi": r"$|\Delta\phi|$",
        "abs dy": r"$|\Delta y|$",
        "pt": r"$p_T$",
        "eta": r"$\eta$",
        "phi ": r"$\phi$ ",
        "ctau": r"$c\tau$",
        "mass": "mass",
        "VtxProb": "vertex prob.",
    }
    for old, new in replacements.items():
        label = label.replace(old, new)
    return label


def infer_range(name: str):
    if "abs_dphi" in name:
        return 0.0, math.pi
    if "abs_dy" in name:
        return 0.0, 5.0
    if name.endswith("_phi"):
        return -math.pi, math.pi
    if name.endswith("_eta") or name.endswith("_y"):
        return -3.0, 3.0
    if name.endswith("_pt"):
        return 0.0, 100.0
    if name.endswith("_VtxProb"):
        return 0.0, 1.0
    if name.endswith("_Chi2"):
        return 0.0, 50.0
    if name.endswith("_ndof"):
        return 0.0, 40.0
    if name.endswith("_ctau"):
        return -0.05, 0.1
    if name.endswith("_ctauErr"):
        return 0.0, 0.05
    if name.endswith("_mass"):
        if "Ups" in name:
            return 8.5, 11.4
        if "Phi" in name:
            return 0.99, 1.07
        if "Jpsi" in name:
            return 2.9, 3.3
        return 0.0, 40.0
    if name.endswith("_massErr"):
        return 0.0, 0.2
    if name.endswith("_massDiff"):
        return -0.2, 0.2
    if name.endswith("_m_all"):
        return 0.0, 60.0
    if name.endswith("_m_jpsi1_jpsi2") or name.endswith("_m_jpsi_ups"):
        return 0.0, 40.0
    if name.endswith("_m_jpsi1_phi") or name.endswith("_m_jpsi2_phi") or name.endswith("_m_jpsi_phi"):
        return 0.0, 30.0
    if name.endswith("_m_ups_phi"):
        return 0.0, 40.0
    return 0.0, 100.0


def bin_edges_for_branch(name: str) -> np.ndarray:
    if name.endswith("_pt"):
        return PT_BIN_EDGES
    xmin, xmax = infer_range(name)
    return np.linspace(xmin, xmax, DEFAULT_BINS + 1, dtype=float)


def discover_plot_columns(tree) -> list[str]:
    columns: list[str] = []
    for name, typename in tree.typenames().items():
        if not name.startswith("sel_"):
            continue
        if name.endswith("_Idx"):
            continue
        low_type = typename.lower()
        if "vector<" in low_type or "string" in low_type:
            continue
        columns.append(name)
    return sorted(set(columns))


def load_branch(tree, branch: str, weight_branch: str):
    arrays = tree.arrays([branch, weight_branch], library="np")
    values = np.asarray(arrays[branch], dtype=float)
    weights = np.asarray(arrays[weight_branch], dtype=float)
    mask = np.isfinite(values) & np.isfinite(weights)
    return values[mask], weights[mask]


def weighted_histogram(values: np.ndarray, weights: np.ndarray, edges: np.ndarray):
    counts, _ = np.histogram(values, bins=edges, weights=weights)
    sumw2, _ = np.histogram(values, bins=edges, weights=np.square(weights))
    return counts.astype(float), sumw2.astype(float)


def style_axis(ax, branch: str, ylabel: str):
    ax.set_xlabel(label_for_branch(branch))
    ax.set_ylabel(ylabel)
    if branch.endswith("_ctau"):
        ax.set_xlim(-0.05, 0.1)
        ax.set_yscale("log")


def save_histogram(branch: str, values: np.ndarray, weights: np.ndarray, output_base: str, dataset: str):
    edges = bin_edges_for_branch(branch)
    counts, sumw2 = weighted_histogram(values, weights, edges)

    fig, ax = plt.subplots(figsize=(8, 7))
    hep.histplot(counts, edges, yerr=np.sqrt(sumw2), histtype="errorbar", color="tab:blue", ax=ax, label="Weighted events")
    style_axis(ax, branch, "Weighted events")
    if branch.endswith("_ctau"):
        positive = counts[counts > 0.0]
        ymin = max(np.min(positive) * 0.5, 1.0e-3) if positive.size else 1.0e-3
        ymax = max(np.max(counts) * 10.0, 1.0) if counts.size else 1.0
        ax.set_ylim(ymin, ymax)
    hep.cms.label("Work in progress", data=(dataset == "data"), ax=ax)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_base + ".pdf")
    fig.savefig(output_base + ".png")
    plt.close(fig)


def save_overlay(tree, branches, weight_branch, output_base, dataset: str, title: str):
    fig, ax = plt.subplots(figsize=(8, 7))
    colors = ["tab:red", "tab:blue", "tab:green"]
    for branch, color in zip(branches, colors):
        values, weights = load_branch(tree, branch, weight_branch)
        edges = bin_edges_for_branch(branch)
        counts, _ = weighted_histogram(values, weights, edges)
        total = np.sum(counts)
        if total > 0.0:
            counts = counts / total
        hep.histplot(counts, edges, histtype="step", linewidth=2, color=color, ax=ax, label=label_for_branch(branch))
    ax.set_title(title)
    ax.set_ylabel("Arbitrary units")
    ax.set_xlabel(label_for_branch(branches[0]))
    hep.cms.label("Work in progress", data=(dataset == "data"), ax=ax)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_base + ".pdf")
    fig.savefig(output_base + ".png")
    plt.close(fig)


def save_correlation_plot(tree, dy_branch, dphi_branch, weight_branch, output_base, dataset: str, title: str):
    arrays = tree.arrays([dy_branch, dphi_branch, weight_branch], library="np")
    x = np.asarray(arrays[dy_branch], dtype=float)
    y = np.asarray(arrays[dphi_branch], dtype=float)
    w = np.asarray(arrays[weight_branch], dtype=float)
    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(w)
    x = x[mask]
    y = y[mask]
    w = w[mask]

    fig, ax = plt.subplots(figsize=(8, 7))
    _, _, _, image = ax.hist2d(
        x,
        y,
        bins=(np.linspace(0.0, 5.0, DEFAULT_BINS + 1), np.linspace(0.0, math.pi, DEFAULT_BINS + 1)),
        weights=w,
        norm=LogNorm() if np.any(w > 0.0) else None,
    )
    ax.set_xlabel(r"$|\Delta y|$")
    ax.set_ylabel(r"$|\Delta\phi|$")
    ax.set_title(title)
    hep.cms.label("Work in progress", data=(dataset == "data"), ax=ax)
    cbar = fig.colorbar(image, ax=ax)
    cbar.set_label("Weighted events")
    fig.tight_layout()
    fig.savefig(output_base + ".pdf")
    fig.savefig(output_base + ".png")
    plt.close(fig)


def main():
    args = parse_args()
    channel = normalize_channel(args.channel)
    dataset = normalize_dataset(args.dataset)
    sample = normalize_sample(channel, args.sample) if dataset == "mc" else None
    input_file = args.input or default_weighted_output(channel, dataset, sample)
    output_dir = args.output_dir or default_plot_dir(channel, dataset, sample)
    ensure_dir(output_dir)

    apply_cms_style()
    tree = uproot.open(input_file)[INPUT_TREE]
    columns = discover_plot_columns(tree)

    for branch in columns:
        values, weights = load_branch(tree, branch, args.weight_branch)
        save_histogram(branch, values, weights, os.path.join(output_dir, branch), dataset)

    cfg = CHANNEL_CONFIGS[channel]
    dy_branches = [f"sel_abs_dy_{name}" for name, _, _ in cfg.pair_specs]
    dphi_branches = [f"sel_abs_dphi_{name}" for name, _, _ in cfg.pair_specs]
    save_overlay(tree, dy_branches, args.weight_branch, os.path.join(output_dir, "delta_y_comparison"), dataset, "DeltaY comparison")
    save_overlay(tree, dphi_branches, args.weight_branch, os.path.join(output_dir, "delta_phi_comparison"), dataset, "DeltaPhi comparison")

    for pair_name, _, _ in cfg.pair_specs:
        save_correlation_plot(
            tree,
            f"sel_abs_dy_{pair_name}",
            f"sel_abs_dphi_{pair_name}",
            args.weight_branch,
            os.path.join(output_dir, f"correlation_2d_{pair_name}"),
            dataset,
            f"{channel} {pair_name}",
        )

    print(f"[INFO] plotted {len(columns)} weighted 1D distributions into {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

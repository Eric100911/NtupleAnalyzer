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
CORRELATION_DY_EDGES = np.linspace(0.0, 5.0, 13, dtype=float)
CORRELATION_DPHI_EDGES = np.linspace(0.0, math.pi, 13, dtype=float)
CMS_LUMI_FB = 289.2
CMS_ENERGY_TEV = 13.6
SORTED_KAON_COORDINATES = {"pt", "eta", "phi", "px", "py", "pz"}


def parse_args():
    parser = argparse.ArgumentParser(description="Plot weighted assocPV distributions")
    parser.add_argument("--channel", required=True, choices=["JJP", "JYP", "JJY", "jjp", "jyp", "jjy"])
    parser.add_argument("--dataset", default="data", choices=["data", "mc"])
    parser.add_argument("--sample", default=None, help="MC sample tag")
    parser.add_argument("-i", "--input", default=None, help="Input weighted ROOT file")
    parser.add_argument("-o", "--output-dir", default=None, help="Plot output directory")
    parser.add_argument("-w", "--weight-branch", default="signal_sw", help="Weight branch")
    return parser.parse_args()


def apply_cms_style():
    plt.style.use(hep.style.CMS)


def cms_label(ax, dataset: str):
    hep.cms.label(
        "Preliminary",
        data=(dataset == "data"),
        lumi=CMS_LUMI_FB if dataset == "data" else None,
        com=CMS_ENERGY_TEV,
        ax=ax,
    )


def particle_label(name: str) -> str:
    labels = {
        "Jpsi": r"J/\psi",
        "Jpsi_1": r"J/\psi_1",
        "Jpsi_2": r"J/\psi_2",
        "Ups": r"\Upsilon",
        "Phi": r"\phi",
        "Pri": r"J/\psi J/\psi\phi",
        "Jpsi1_mu1": r"\mu_1(J/\psi_1)",
        "Jpsi1_mu2": r"\mu_2(J/\psi_1)",
        "Jpsi2_mu1": r"\mu_1(J/\psi_2)",
        "Jpsi2_mu2": r"\mu_2(J/\psi_2)",
        "Jpsi_mu1": r"\mu_1(J/\psi)",
        "Jpsi_mu2": r"\mu_2(J/\psi)",
        "Ups_mu1": r"\mu_1(\Upsilon)",
        "Ups_mu2": r"\mu_2(\Upsilon)",
        "Phi_K_1": r"K_{\mathrm{lead}}(\phi)",
        "Phi_K_2": r"K_{\mathrm{sublead}}(\phi)",
    }
    return labels.get(name, name.replace("_", r"\,"))


def pair_label(pair_name: str) -> str:
    pair_particles = {
        "jpsi1_jpsi2": (r"J/\psi_1", r"J/\psi_2"),
        "jpsi1_phi": (r"J/\psi_1", r"\phi"),
        "jpsi2_phi": (r"J/\psi_2", r"\phi"),
        "jpsi_ups": (r"J/\psi", r"\Upsilon"),
        "jpsi_phi": (r"J/\psi", r"\phi"),
        "ups_phi": (r"\Upsilon", r"\phi"),
        "jpsi1_ups": (r"J/\psi_1", r"\Upsilon"),
        "jpsi2_ups": (r"J/\psi_2", r"\Upsilon"),
    }
    left, right = pair_particles.get(pair_name, (pair_name, ""))
    return rf"{left}, {right}" if right else left


def split_branch_name(name: str) -> tuple[str | None, str]:
    bare = name.removeprefix("sel_")
    known_quantities = (
        "m_jpsi1_jpsi2",
        "m_jpsi1_phi",
        "m_jpsi2_phi",
        "m_jpsi_ups",
        "m_jpsi_phi",
        "m_ups_phi",
        "m_all",
        "massDiff",
        "massErr",
        "ctauErr",
        "VtxProb",
        "Chi2",
        "ndof",
        "mass",
        "ctau",
        "pt",
        "y",
        "eta",
        "phi",
        "px",
        "py",
        "pz",
    )
    for quantity in known_quantities:
        suffix = f"_{quantity}"
        if bare.endswith(suffix):
            return bare[: -len(suffix)], quantity
        if bare == quantity:
            return None, quantity
    return None, bare


def sorted_kaon_coordinate(name: str) -> tuple[int, str] | None:
    particle, quantity = split_branch_name(name)
    if particle == "Phi_K_1" and quantity in SORTED_KAON_COORDINATES:
        return 1, quantity
    if particle == "Phi_K_2" and quantity in SORTED_KAON_COORDINATES:
        return 2, quantity
    return None


def mass_label(branch: str, particle: str | None) -> str:
    if branch.endswith("_m_all"):
        return r"$m(J/\psi J/\psi\phi)$ [GeV]"
    if branch.endswith("_m_jpsi1_jpsi2"):
        return r"$m(J/\psi_1,J/\psi_2)$ [GeV]"
    if branch.endswith("_m_jpsi1_phi"):
        return r"$m(J/\psi_1,\phi)$ [GeV]"
    if branch.endswith("_m_jpsi2_phi"):
        return r"$m(J/\psi_2,\phi)$ [GeV]"
    if branch.endswith("_m_jpsi_ups"):
        return r"$m(J/\psi,\Upsilon)$ [GeV]"
    if branch.endswith("_m_jpsi_phi"):
        return r"$m(J/\psi,\phi)$ [GeV]"
    if branch.endswith("_m_ups_phi"):
        return r"$m(\Upsilon,\phi)$ [GeV]"
    if particle == "Phi":
        return r"$m(K^+K^-)$ [GeV]"
    if particle and "Jpsi" in particle:
        return rf"$m({particle_label(particle)})$ [GeV]"
    if particle == "Ups":
        return r"$m(\Upsilon)$ [GeV]"
    return r"$m$ [GeV]"


def label_for_branch(name: str) -> str:
    if name.startswith("sel_abs_dy_"):
        return rf"$|\Delta y({pair_label(name.removeprefix('sel_abs_dy_'))})|$"
    if name.startswith("sel_abs_dphi_"):
        return rf"$|\Delta\phi({pair_label(name.removeprefix('sel_abs_dphi_'))})|$"

    particle, quantity = split_branch_name(name)
    obj = particle_label(particle) if particle else None
    if quantity == "pt" and obj:
        return rf"$p_{{\mathrm{{T}}}}({obj})$ [GeV]"
    if quantity == "eta" and obj:
        return rf"$\eta({obj})$"
    if quantity == "phi" and obj:
        return rf"$\phi({obj})$"
    if quantity == "y" and obj:
        return rf"$y({obj})$"
    if quantity in {"px", "py", "pz"} and obj:
        component = quantity.removeprefix("p")
        return rf"$p_{{{component}}}({obj})$ [GeV]"
    if quantity in {"mass", "m_all", "m_jpsi1_jpsi2", "m_jpsi1_phi", "m_jpsi2_phi", "m_jpsi_ups", "m_jpsi_phi", "m_ups_phi"}:
        return mass_label(name, particle)
    if quantity == "massErr" and obj:
        return rf"$\sigma_m({obj})$ [GeV]"
    if quantity == "massDiff" and obj:
        return rf"$\Delta m({obj})$ [GeV]"
    if quantity == "ctau" and obj:
        return rf"$c\tau({obj})$ [cm]"
    if quantity == "ctauErr" and obj:
        return rf"$\sigma_{{c\tau}}({obj})$ [cm]"
    if quantity == "VtxProb" and obj:
        return rf"$P_{{\mathrm{{vtx}}}}({obj})$"
    if quantity == "Chi2" and obj:
        return rf"$\chi^2({obj})$"
    if quantity == "ndof" and obj:
        return rf"$N_{{\mathrm{{dof}}}}({obj})$"
    return name.removeprefix("sel_").replace("_", " ")


def infer_range(name: str):
    if name in {"sel_same_mu_vertex", "sel_pri_valid", "sel_pri_vtxprob_gt_0p005"}:
        return -0.5, 1.5
    if "abs_dphi" in name:
        return 0.0, math.pi
    if "abs_dy" in name:
        return 0.0, 5.0
    if name.endswith("_m_all"):
        return 0.0, 300.0
    if name.endswith("_m_jpsi1_jpsi2") or name.endswith("_m_jpsi_ups"):
        return 0.0, 160.0
    if name.endswith("_m_jpsi1_phi") or name.endswith("_m_jpsi2_phi") or name.endswith("_m_jpsi_phi"):
        return 0.0, 150.0
    if name.endswith("_m_ups_phi"):
        return 0.0, 160.0
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
    sorted_kaon = sorted_kaon_coordinate(branch)
    if sorted_kaon is not None:
        rank, quantity = sorted_kaon
        value_branch_1 = f"sel_Phi_K_1_{quantity}"
        value_branch_2 = f"sel_Phi_K_2_{quantity}"
        arrays = tree.arrays(
            [value_branch_1, value_branch_2, "sel_Phi_K_1_pt", "sel_Phi_K_2_pt", weight_branch],
            library="np",
        )
        values_1 = np.asarray(arrays[value_branch_1], dtype=float)
        values_2 = np.asarray(arrays[value_branch_2], dtype=float)
        pt_1 = np.asarray(arrays["sel_Phi_K_1_pt"], dtype=float)
        pt_2 = np.asarray(arrays["sel_Phi_K_2_pt"], dtype=float)
        weights = np.asarray(arrays[weight_branch], dtype=float)
        first_is_lead = pt_1 >= pt_2
        if rank == 1:
            values = np.where(first_is_lead, values_1, values_2)
        else:
            values = np.where(first_is_lead, values_2, values_1)
        mask = (
            np.isfinite(values)
            & np.isfinite(pt_1)
            & np.isfinite(pt_2)
            & np.isfinite(weights)
        )
        return values[mask], weights[mask]

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

    fig, ax = plt.subplots(figsize=(9.6, 7))
    hep.histplot(counts, edges, yerr=np.sqrt(sumw2), histtype="errorbar", color="tab:blue", ax=ax, label="sWeighted events")
    style_axis(ax, branch, "sWeighted events")
    if branch.endswith("_ctau"):
        positive = counts[counts > 0.0]
        ymin = max(np.min(positive) * 0.5, 1.0e-3) if positive.size else 1.0e-3
        ymax = max(np.max(counts) * 10.0, 1.0) if counts.size else 1.0
        ax.set_ylim(ymin, ymax)
    cms_label(ax, dataset)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_base + ".pdf")
    fig.savefig(output_base + ".png")
    plt.close(fig)


def save_overlay(tree, branches, weight_branch, output_base, dataset: str, label: str):
    fig, ax = plt.subplots(figsize=(10.8, 7))
    colors = ["tab:red", "tab:blue", "tab:green"]
    for branch, color in zip(branches, colors):
        values, weights = load_branch(tree, branch, weight_branch)
        edges = bin_edges_for_branch(branch)
        counts, _ = weighted_histogram(values, weights, edges)
        total = np.sum(counts)
        if total > 0.0:
            counts = counts / total
        hep.histplot(counts, edges, histtype="step", linewidth=2, color=color, ax=ax, label=label_for_branch(branch))
    ax.set_ylabel("Normalized sWeighted events")
    ax.set_xlabel(label_for_branch(branches[0]))
    ax.text(0.04, 0.86, label, transform=ax.transAxes, ha="left", va="top", fontsize=15)
    cms_label(ax, dataset)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_base + ".pdf")
    fig.savefig(output_base + ".png")
    plt.close(fig)


def save_correlation_projection(
    values: np.ndarray,
    weights: np.ndarray,
    edges: np.ndarray,
    output_base: str,
    dataset: str,
    xlabel: str,
    label: str,
):
    counts, sumw2 = weighted_histogram(values, weights, edges)
    fig, ax = plt.subplots(figsize=(10.8, 7))
    hep.histplot(counts, edges, yerr=np.sqrt(sumw2), histtype="errorbar", color="tab:blue", ax=ax)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("sWeighted events")
    ax.text(0.04, 0.86, label, transform=ax.transAxes, ha="left", va="top", fontsize=15)
    cms_label(ax, dataset)
    fig.tight_layout()
    fig.savefig(output_base + ".pdf")
    fig.savefig(output_base + ".png")
    plt.close(fig)


def save_correlation_plot(tree, dy_branch, dphi_branch, weight_branch, output_base, dataset: str, pair_name: str, channel: str):
    arrays = tree.arrays([dy_branch, dphi_branch, weight_branch], library="np")
    x = np.asarray(arrays[dy_branch], dtype=float)
    y = np.asarray(arrays[dphi_branch], dtype=float)
    w = np.asarray(arrays[weight_branch], dtype=float)
    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(w)
    x = x[mask]
    y = y[mask]
    w = w[mask]

    fig, ax = plt.subplots(figsize=(10.8, 7))
    _, _, _, image = ax.hist2d(
        x,
        y,
        bins=(CORRELATION_DY_EDGES, CORRELATION_DPHI_EDGES),
        weights=w,
        norm=LogNorm() if np.any(w > 0.0) else None,
    )
    dy_label = label_for_branch(dy_branch)
    dphi_label = label_for_branch(dphi_branch)
    plot_label = rf"{channel}: ${pair_label(pair_name)}$"
    ax.set_xlabel(dy_label)
    ax.set_ylabel(dphi_label)
    ax.text(0.04, 0.86, plot_label, transform=ax.transAxes, ha="left", va="top", fontsize=15)
    cms_label(ax, dataset)
    cbar = fig.colorbar(image, ax=ax)
    cbar.set_label("sWeighted events")
    fig.tight_layout()
    fig.savefig(output_base + ".pdf")
    fig.savefig(output_base + ".png")
    plt.close(fig)

    save_correlation_projection(
        x,
        w,
        CORRELATION_DY_EDGES,
        output_base.replace("correlation_2d_", "correlation_proj_dy_"),
        dataset,
        dy_label,
        plot_label,
    )
    save_correlation_projection(
        y,
        w,
        CORRELATION_DPHI_EDGES,
        output_base.replace("correlation_2d_", "correlation_proj_dphi_"),
        dataset,
        dphi_label,
        plot_label,
    )


def main():
    args = parse_args()
    channel = normalize_channel(args.channel)
    dataset = normalize_dataset(args.dataset)
    if channel == "JJY" and dataset != "mc":
        raise ValueError("JJY weighted plotting is currently supported only for MC samples")
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
            pair_name,
            channel,
        )

    print(f"[INFO] plotted {len(columns)} weighted 1D distributions into {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

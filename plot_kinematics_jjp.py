#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plot pre-efficiency-correction kinematic distributions.

Produces two sets of plots for the JJP (J/ψ J/ψ φ) channel:
  1. sWeighted data kinematics  — pT, y (for J/ψ, φ) / η (for muons, kaons), φ
  2. Data-MC agreement overlays — normalized distributions, all MC samples overlaid
"""

from __future__ import annotations

import argparse
import os
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
import uproot

from ntuple_pipeline_common import (
    CHANNEL_CONFIGS,
    OUTPUT_BASE,
    ensure_dir,
)
from plot_weighted_distributions import (
    CORRELATION_DPHI_EDGES,
    CORRELATION_DY_EDGES,
    INPUT_TREE,
    apply_cms_style,
    bin_edges_for_branch,
    label_for_branch,
    load_branch,
    pair_label,
    particle_label,
    sorted_kaon_coordinate,
    weighted_histogram,
)

# ---------------------------------------------------------------------------
# Kinematic branches to plot
#   J/ψ, φ  → rapidity y  (known mass)
#   muons, kaons → pseudorapidity η
# ---------------------------------------------------------------------------
KINEMATICS_BRANCHES = [
    # J/ψ candidates — pt, y, |y|, phi
    "sel_Jpsi_1_pt", "sel_Jpsi_1_y", "sel_Jpsi_1_phi",
    "sel_Jpsi_2_pt", "sel_Jpsi_2_y", "sel_Jpsi_2_phi",
    # φ candidate — pt, y, |y|, phi
    "sel_Phi_pt", "sel_Phi_y", "sel_Phi_phi",
    # J/ψ muons — pt, eta, phi
    "sel_Jpsi1_mu1_pt", "sel_Jpsi1_mu1_eta", "sel_Jpsi1_mu1_phi",
    "sel_Jpsi1_mu2_pt", "sel_Jpsi1_mu2_eta", "sel_Jpsi1_mu2_phi",
    "sel_Jpsi2_mu1_pt", "sel_Jpsi2_mu1_eta", "sel_Jpsi2_mu1_phi",
    "sel_Jpsi2_mu2_pt", "sel_Jpsi2_mu2_eta", "sel_Jpsi2_mu2_phi",
    # φ kaons — pt, eta, phi
    "sel_Phi_K_1_pt", "sel_Phi_K_1_eta", "sel_Phi_K_1_phi",
    "sel_Phi_K_2_pt", "sel_Phi_K_2_eta", "sel_Phi_K_2_phi",
]

# Synthetic |y| branches for J/ψ and φ (computed on-the-fly)
ABS_Y_BRANCHES = {
    "sel_Jpsi_1_abs_y": "sel_Jpsi_1_y",
    "sel_Jpsi_2_abs_y": "sel_Jpsi_2_y",
    "sel_Phi_abs_y": "sel_Phi_y",
}

# ---------------------------------------------------------------------------
# MC sample definitions
# ---------------------------------------------------------------------------
_LOCAL_MC_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "merged_efficiency_output_20260601_01",
    "jjp_effcorr_weighted_trees",
)

MC_SAMPLE_FILES = {
    "DPS_1": os.path.join(_LOCAL_MC_DIR, "JJP_DPS1_merged.root"),
    "DPS_2_CS": os.path.join(_LOCAL_MC_DIR, "JJP_DPS2_CS_merged.root"),
    "DPS_2_G": os.path.join(_LOCAL_MC_DIR, "JJP_DPS2_G_merged.root"),
    "SPS_CS": os.path.join(_LOCAL_MC_DIR, "JJP_SPS_CS_merged.root"),
    "SPS_G": os.path.join(_LOCAL_MC_DIR, "JJP_SPS_G_merged.root"),
    "TPS": os.path.join(_LOCAL_MC_DIR, "JJP_TPS_merged.root"),
}

MC_LABELS = {
    "DPS_1": r"DPS1 $J/\psi+(J/\psi+\phi)$",
    "DPS_2_CS": r"DPS2 $(J/\psi+J/\psi)+\phi$ @ CSM LO",
    "DPS_2_G": r"DPS2 $(J/\psi+J/\psi)+\phi$ @ CSM NLO$^{*}$",
    "SPS_CS": r"SPS $J/\psi+J/\psi+\phi$ @ CSM LO",
    "SPS_G": r"SPS $J/\psi+J/\psi+\phi$ @ CSM NLO$^{*}$",
    "TPS": r"TPS $J/\psi+J/\psi+\phi$",
}

MC_COLORS = {
    "DPS_1": "#e41a1c",       # red
    "DPS_2_CS": "#377eb8",    # blue
    "DPS_2_G": "#4daf4a",     # green
    "SPS_CS": "#ff7f00",      # orange
    "SPS_G": "#984ea3",       # purple
    "TPS": "#00a6a6",          # teal
}

MC_MERGED_STEMS = {
    "DPS_1": "DPS1",
    "DPS_2_CS": "DPS2_CS",
    "DPS_2_G": "DPS2_G",
    "SPS_CS": "SPS_CS",
    "SPS_G": "SPS_G",
    "TPS": "TPS",
}

DATA_COLOR = "black"
CMS_LUMI_FB = 289.2
CMS_ENERGY_TEV = 13.6

_LOCAL_DATA_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "jjp_data_selected.root",
)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Plot pre-efficiency kinematic distributions and data-MC comparisons"
    )
    parser.add_argument(
        "--mode", default="all", choices=["data", "comparison", "all"],
        help="'data' for sWeighted data-only plots; 'comparison' for MC overlay; 'all' for both",
    )
    parser.add_argument(
        "--data-input", default=_LOCAL_DATA_FILE,
        help="Input data selected ROOT file (pre-sWeight).",
    )
    parser.add_argument(
        "--weighted-data", default=None,
        help="Pre-computed sWeighted data ROOT file. If not given, fits sPlot first.",
    )
    parser.add_argument(
        "--mc-dir", default=_LOCAL_MC_DIR,
        help="Directory containing MC merged ROOT files.",
    )
    parser.add_argument(
        "-o", "--output-dir", default=None,
        help="Output directory for plots.",
    )
    parser.add_argument(
        "--skip-splot", action="store_true",
        help="Skip sPlot fit; requires --weighted-data.",
    )
    parser.add_argument(
        "-j", "--jobs", type=int, default=4,
        help="Number of CPUs for RooFit sPlot fit.",
    )
    parser.add_argument(
        "--normalize", choices=["shape", "yield"], default="shape",
        help="Normalization mode for comparison plots.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalize_histogram(counts: np.ndarray, variances: np.ndarray, mode: str):
    """Normalize histogram to unit integral for shape comparison."""
    if mode == "yield":
        return counts, variances
    total = np.sum(counts)
    if total <= 0.0:
        return counts, variances
    return counts / total, variances / (total * total)


def _save_figure(fig, output_base: str) -> None:
    """Save PDF and PNG variants for a matplotlib figure."""
    fig.savefig(output_base + ".pdf")
    fig.savefig(output_base + ".png", dpi=260)


def _apply_cms_work_in_progress_label(
    ax,
    data: bool = True,
    fontsize: float | None = None,
) -> None:
    """Apply the CMS label through mplhep only."""
    label_kwargs = {
        "label": "Work In Progress",
        "data": bool(data),
        "lumi": CMS_LUMI_FB if data else None,
        "com": CMS_ENERGY_TEV,
        "ax": ax,
        "loc": 0,
    }
    if fontsize is not None:
        label_kwargs["fontsize"] = fontsize
    hep.cms.label(**label_kwargs)


def _draw_top_row_label(
    ax,
    text: str,
    x: float | None = None,
    y_offset: float = 0.006,
    ha: str = "center",
    fontsize: float = 10,
) -> None:
    """Draw a non-CMS caption above the axes, matching efficiency plot style."""
    axes_box = ax.get_position()
    ax.figure.text(
        axes_box.x0 if x is None else x,
        axes_box.y1 + y_offset,
        text,
        ha=ha,
        va="bottom",
        fontsize=fontsize,
    )


def _log_progress(message: str) -> None:
    """Print progress immediately for long production plotting runs."""
    print(f"[PROGRESS] {message}", flush=True)


class TreeArrayCache:
    """In-memory branch cache to avoid rereading ROOT arrays for each plot."""

    def __init__(self, keys: set[str], arrays: dict[str, np.ndarray]):
        self.keys = keys
        self.arrays = arrays

    @classmethod
    def from_tree(cls, tree, branches: set[str], label: str) -> "TreeArrayCache":
        keys = set(tree.keys())
        available = sorted(branch for branch in branches if branch in keys)
        missing = sorted(branch for branch in branches if branch not in keys)
        if missing:
            print(
                f"[WARNING] {label}: {len(missing)} requested branches are missing: "
                f"{', '.join(missing)}",
                flush=True,
            )
        _log_progress(f"preloading {label}: {len(available)} branches")
        raw_arrays = tree.arrays(available, library="np") if available else {}
        arrays = {
            branch: np.asarray(raw_arrays[branch], dtype=float)
            for branch in available
        }
        return cls(keys=keys, arrays=arrays)

    def has(self, branch: str) -> bool:
        return branch in self.arrays

    def get(self, branch: str) -> np.ndarray:
        return self.arrays[branch]


def _source_branches_for_plot_branch(branch: str) -> set[str]:
    """Return physical tree branches needed to plot one logical branch."""
    actual_branch = _resolve_kinematics_branch(branch)
    sorted_kaon = sorted_kaon_coordinate(actual_branch)
    if sorted_kaon is None:
        return {actual_branch}
    _, quantity = sorted_kaon
    return {
        f"sel_Phi_K_1_{quantity}",
        f"sel_Phi_K_2_{quantity}",
        "sel_Phi_K_1_pt",
        "sel_Phi_K_2_pt",
    }


def _required_source_branches(
    plot_branches: list[str],
    correlation_specs: list[tuple[str, str, str]],
    weight_branch: str | None = None,
) -> set[str]:
    """Return the union of ROOT branches needed by all requested plots."""
    branches: set[str] = set()
    for branch in plot_branches:
        branches.update(_source_branches_for_plot_branch(branch))
    for _, dy_branch, dphi_branch in correlation_specs:
        branches.add(dy_branch)
        branches.add(dphi_branch)
    if weight_branch is not None:
        branches.add(weight_branch)
    return branches


def _branch_exists_in_cache(cache: TreeArrayCache, branch: str) -> bool:
    return all(cache.has(source) for source in _source_branches_for_plot_branch(branch))


def _load_branch_from_cache(
    cache: TreeArrayCache,
    branch: str,
    weight_branch: str | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Load plot values from a preloaded tree cache."""
    actual_branch = _resolve_kinematics_branch(branch)
    sorted_kaon = sorted_kaon_coordinate(actual_branch)
    if sorted_kaon is not None:
        rank, quantity = sorted_kaon
        values_1 = cache.get(f"sel_Phi_K_1_{quantity}")
        values_2 = cache.get(f"sel_Phi_K_2_{quantity}")
        pt_1 = cache.get("sel_Phi_K_1_pt")
        pt_2 = cache.get("sel_Phi_K_2_pt")
        first_is_lead = pt_1 >= pt_2
        if rank == 1:
            values = np.where(first_is_lead, values_1, values_2)
        else:
            values = np.where(first_is_lead, values_2, values_1)
        mask = np.isfinite(values) & np.isfinite(pt_1) & np.isfinite(pt_2)
    else:
        values = cache.get(actual_branch)
        mask = np.isfinite(values)

    if _is_abs_y_branch(branch):
        values = np.abs(values)

    if weight_branch is None:
        return values[mask], np.ones(np.count_nonzero(mask), dtype=float)

    weights = cache.get(weight_branch)
    mask = mask & np.isfinite(weights)
    return values[mask], weights[mask]


def _load_pair_2d_from_cache(
    cache: TreeArrayCache,
    dy_branch: str,
    dphi_branch: str,
    weight_branch: str | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = cache.get(dy_branch)
    y = cache.get(dphi_branch)
    mask = np.isfinite(x) & np.isfinite(y)
    if weight_branch is None:
        return x[mask], y[mask], np.ones(np.count_nonzero(mask), dtype=float)

    weights = cache.get(weight_branch)
    mask = mask & np.isfinite(weights)
    return x[mask], y[mask], weights[mask]


def _mc_file_candidates(mc_dir: str, tag: str, sample_fn: str) -> list[str]:
    """Return plausible MC paths for symlinked, merged, selected, and weighted files."""
    stem = MC_MERGED_STEMS.get(tag, tag)
    lower = tag.lower()
    candidates = [
        os.path.join(mc_dir, os.path.basename(sample_fn)),
        os.path.join(mc_dir, f"JJP_{stem}_merged.root"),
        os.path.join(mc_dir, f"JJP_{tag}_merged.root"),
        os.path.join(mc_dir, f"jjp_mc_{lower}_selected.root"),
        os.path.join(mc_dir, f"jjp_mc_{lower}_weighted.root"),
        sample_fn,
    ]
    seen = set()
    unique = []
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def _find_mc_file(mc_dir: str, tag: str, sample_fn: str) -> str | None:
    for path in _mc_file_candidates(mc_dir, tag, sample_fn):
        if os.path.exists(path):
            return path
    return None


def load_branch_mc(tree, branch: str):
    """Load branch values from MC tree with uniform weight.

    All MC events in the merged files pass GEN-matching → true signal.
    The sorted-kaon logic is reproduced from plot_weighted_distributions.load_branch.
    """
    sorted_kaon = sorted_kaon_coordinate(branch)
    if sorted_kaon is not None:
        rank, quantity = sorted_kaon
        value_branch_1 = f"sel_Phi_K_1_{quantity}"
        value_branch_2 = f"sel_Phi_K_2_{quantity}"
        arrays = tree.arrays(
            [value_branch_1, value_branch_2, "sel_Phi_K_1_pt", "sel_Phi_K_2_pt"],
            library="np",
        )
        values_1 = np.asarray(arrays[value_branch_1], dtype=float)
        values_2 = np.asarray(arrays[value_branch_2], dtype=float)
        pt_1 = np.asarray(arrays["sel_Phi_K_1_pt"], dtype=float)
        pt_2 = np.asarray(arrays["sel_Phi_K_2_pt"], dtype=float)
        first_is_lead = pt_1 >= pt_2
        if rank == 1:
            values = np.where(first_is_lead, values_1, values_2)
        else:
            values = np.where(first_is_lead, values_2, values_1)
        mask = (
            np.isfinite(values)
            & np.isfinite(pt_1)
            & np.isfinite(pt_2)
        )
        return values[mask], np.ones(np.count_nonzero(mask), dtype=float)

    arrays = tree.arrays([branch], library="np")
    values = np.asarray(arrays[branch], dtype=float)
    mask = np.isfinite(values)
    return values[mask], np.ones(np.count_nonzero(mask), dtype=float)


def load_branch_data(tree, branch: str, weight_branch: str = "signal_sw"):
    """Load branch values from data tree with sWeights."""
    return load_branch(tree, branch, weight_branch)


def _title_from_branch(branch: str) -> str:
    """Return a human-readable title for a kinematic branch (for plot annotation)."""
    from plot_weighted_distributions import split_branch_name

    particle, quantity = split_branch_name(branch)
    obj = particle_label(particle) if particle else None
    qlabel = {"pt": "p_{T}", "eta": "#eta", "y": "y", "phi": "#phi"}.get(quantity, quantity)
    if obj:
        return rf"${qlabel}({obj})$"
    return label_for_branch(branch)


# ---------------------------------------------------------------------------
# Synthetic |y| branch helpers (for checking MC production asymmetries)
# ---------------------------------------------------------------------------
def _is_abs_y_branch(branch: str) -> bool:
    """Check if a branch name represents an |y| (absolute rapidity) variable."""
    return branch.endswith("_abs_y")


def _abs_y_source_branch(branch: str) -> str:
    """Return the base y branch name for an |y| branch."""
    return branch.replace("_abs_y", "_y")


def _label_for_abs_y(branch: str) -> str:
    """LaTeX label for |y| branch."""
    base_y = _abs_y_source_branch(branch)
    # Extract particle from the base name, e.g. sel_Jpsi_1_y → J/ψ₁
    particle_name = base_y.removeprefix("sel_").removesuffix("_y")
    obj = particle_label(particle_name)
    return rf"$|y|({obj})$"


def _bin_edges_for_abs_y() -> np.ndarray:
    """Bin edges for |y|: [0, 3] with 30 uniform bins."""
    return np.linspace(0.0, 3.0, 31, dtype=float)


def _resolve_kinematics_branch(branch: str) -> str:
    """Return the actual branch to read from the tree.

    For |y| branches, returns the source y branch.
    """
    if _is_abs_y_branch(branch):
        return _abs_y_source_branch(branch)
    return branch


def _load_branch_for_plot(tree, branch: str, weight_branch: str = "signal_sw",
                         is_mc: bool = False):
    """Load branch values, handling synthetic |y| branches.

    For |y| branches, loads the source y branch and takes abs().
    """
    actual_branch = _resolve_kinematics_branch(branch)
    if is_mc:
        values, weights = load_branch_mc(tree, actual_branch)
    else:
        values, weights = load_branch_data(tree, actual_branch, weight_branch)
    if _is_abs_y_branch(branch):
        values = np.abs(values)
    return values, weights


def _comparison_1d_branches(data_tree) -> list[str]:
    """Build the integrated comparison variable list for JJP."""
    available = set(data_tree.keys())
    branches: list[str] = []

    for branch in KINEMATICS_BRANCHES:
        if branch in available:
            branches.append(branch)
        else:
            print(f"[WARNING] Missing branch in data: {branch}")

    for abs_branch, src_branch in ABS_Y_BRANCHES.items():
        if src_branch in available:
            branches.append(abs_branch)
        else:
            print(f"[WARNING] Source branch '{src_branch}' missing, skipping '{abs_branch}'")

    cfg = CHANNEL_CONFIGS["JJP"]
    for pair_name, _, _ in cfg.pair_specs:
        for branch in (
            f"sel_abs_dy_{pair_name}",
            f"sel_abs_dphi_{pair_name}",
            f"sel_m_{pair_name}",
        ):
            if branch in available:
                branches.append(branch)
            else:
                print(f"[WARNING] Correlation branch missing in data: {branch}")

    if "sel_m_all" in available:
        branches.append("sel_m_all")
    else:
        print("[WARNING] Correlation branch missing in data: sel_m_all")

    return sorted(dict.fromkeys(branches))


def _pair_correlation_specs(data_tree) -> list[tuple[str, str, str]]:
    """Return JJP 2D correlation branch specs available in the data tree."""
    available = set(data_tree.keys())
    specs = []
    for pair_name, _, _ in CHANNEL_CONFIGS["JJP"].pair_specs:
        dy_branch = f"sel_abs_dy_{pair_name}"
        dphi_branch = f"sel_abs_dphi_{pair_name}"
        if dy_branch in available and dphi_branch in available:
            specs.append((pair_name, dy_branch, dphi_branch))
        else:
            print(f"[WARNING] 2D correlation branches missing in data for {pair_name}")
    return specs


def _branch_exists_for_plot(tree, branch: str) -> bool:
    """Check whether all source branches needed by a plot branch exist."""
    actual_branch = _resolve_kinematics_branch(branch)
    if sorted_kaon_coordinate(actual_branch) is not None:
        _, quantity = sorted_kaon_coordinate(actual_branch)
        needed = {
            f"sel_Phi_K_1_{quantity}",
            f"sel_Phi_K_2_{quantity}",
            "sel_Phi_K_1_pt",
            "sel_Phi_K_2_pt",
        }
        return needed.issubset(set(tree.keys()))
    return actual_branch in tree.keys()


def _load_pair_2d_data(tree, dy_branch: str, dphi_branch: str, weight_branch: str = "signal_sw"):
    arrays = tree.arrays([dy_branch, dphi_branch, weight_branch], library="np")
    x = np.asarray(arrays[dy_branch], dtype=float)
    y = np.asarray(arrays[dphi_branch], dtype=float)
    w = np.asarray(arrays[weight_branch], dtype=float)
    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(w)
    return x[mask], y[mask], w[mask]


def _load_pair_2d_mc(tree, dy_branch: str, dphi_branch: str):
    arrays = tree.arrays([dy_branch, dphi_branch], library="np")
    x = np.asarray(arrays[dy_branch], dtype=float)
    y = np.asarray(arrays[dphi_branch], dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    return x[mask], y[mask], np.ones(np.count_nonzero(mask), dtype=float)


def _histogram2d(x, y, weights, normalize: str):
    counts, _, _ = np.histogram2d(
        x,
        y,
        bins=(CORRELATION_DY_EDGES, CORRELATION_DPHI_EDGES),
        weights=weights,
    )
    if normalize == "shape":
        total = np.sum(counts)
        if total > 0.0:
            counts = counts / total
    return counts


def _plot_pull_panel(rax, edges, centers, mc_histos, data_counts, data_vars):
    sigma_data = np.sqrt(data_vars)
    finite_values = []
    for label, (counts, mc_err) in mc_histos.items():
        pull = np.full_like(data_counts, np.nan, dtype=float)
        pull_err = np.full_like(data_counts, np.nan, dtype=float)
        valid = sigma_data > 0.0
        pull[valid] = (counts[valid] - data_counts[valid]) / sigma_data[valid]
        pull_err[valid] = np.sqrt(np.square(mc_err[valid]) + data_vars[valid]) / sigma_data[valid]
        finite = np.isfinite(pull)
        finite_values.extend(pull[finite].tolist())
        if np.any(finite):
            color = MC_COLORS.get(label, "gray")
            display_label = MC_LABELS.get(label, label)
            rax.stairs(
                pull,
                edges,
                color=color,
                linewidth=1.5,
                label=display_label,
            )
            rax.errorbar(
                centers[finite],
                pull[finite],
                yerr=pull_err[finite],
                fmt="none",
                ecolor=color,
                elinewidth=1.0,
                capsize=2.5,
                capthick=1.0,
            )

    rax.axhline(0.0, color="black", linestyle="--", linewidth=1)
    rax.set_ylabel(r"$(\mathrm{MC}-\mathrm{Data})/\sigma_{\mathrm{Data}}$", fontsize=12)
    if finite_values:
        finite_array = np.asarray(finite_values, dtype=float)
        ymin, ymax = np.nanpercentile(finite_array, [2.0, 98.0])
        span = max(abs(ymin), abs(ymax), 2.0)
        rax.set_ylim(-1.15 * span, 1.15 * span)
    else:
        rax.set_ylim(-2.0, 2.0)


# ---------------------------------------------------------------------------
# sPlot integration
# ---------------------------------------------------------------------------
def run_splot_on_data(input_path: str, output_path: str, jobs: int = 4) -> None:
    """Run the JJP sPlot fit on data and write a weighted ntuple."""
    print(f"[INFO] Running sPlot fit on {input_path}")
    print(f"[INFO]   → output: {output_path}")

    # Fit projection plots go next to the output file
    fit_plot_dir = os.path.join(os.path.dirname(output_path), "fit_projections")
    ensure_dir(fit_plot_dir)

    saved_argv = list(sys.argv)
    sys.argv = [
        "fit_splot.py",
        "--channel", "JJP",
        "--dataset", "data",
        "-i", input_path,
        "-o", output_path,
        "--plot-dir", fit_plot_dir,
        "-j", str(jobs),
    ]
    try:
        import fit_splot
        rc = fit_splot.main()
        if rc is not None and rc != 0:
            raise RuntimeError(f"sPlot fit returned exit code {rc}")
    finally:
        sys.argv = saved_argv

    if not os.path.exists(output_path):
        raise RuntimeError(f"sPlot output file was not created: {output_path}")
    print(f"[INFO] sPlot fit complete. Weighted file: {output_path}")


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def plot_data_kinematics(branch: str, values: np.ndarray, weights: np.ndarray,
                          output_base: str):
    """Plot a single sWeighted kinematic distribution for data."""
    if _is_abs_y_branch(branch):
        edges = _bin_edges_for_abs_y()
        xlabel = _label_for_abs_y(branch)
    else:
        edges = bin_edges_for_branch(branch)
        xlabel = label_for_branch(branch)
    counts, sumw2 = weighted_histogram(values, weights, edges)
    errors = np.sqrt(sumw2)

    fig, ax = plt.subplots(figsize=(11.2, 7.2))
    hep.histplot(
        counts, edges, yerr=errors,
        histtype="errorbar", color="tab:blue", ax=ax,
        label="sWeighted events",
    )
    ax.set_xlabel(xlabel)
    ax.set_ylabel("sWeighted events / bin")
    ax.legend(loc="best")
    fig.subplots_adjust(left=0.12, right=0.96, top=0.84, bottom=0.12)
    _apply_cms_work_in_progress_label(ax, data=True)
    _save_figure(fig, output_base)
    plt.close(fig)


def plot_comparison(
    branch: str,
    data_vals: np.ndarray,
    data_weights: np.ndarray,
    mc_dict: dict[str, tuple[np.ndarray, np.ndarray]],
    output_base: str,
    normalize: str = "shape",
):
    """Overlay data with all MC samples and draw a lower compatibility panel."""
    if _is_abs_y_branch(branch):
        edges = _bin_edges_for_abs_y()
        xlabel = _label_for_abs_y(branch)
    else:
        edges = bin_edges_for_branch(branch)
        xlabel = label_for_branch(branch)
    centers = 0.5 * (edges[:-1] + edges[1:])

    # ---- Data histogram ----
    data_counts, data_sumw2 = weighted_histogram(data_vals, data_weights, edges)
    data_counts, data_sumw2 = normalize_histogram(data_counts, data_sumw2, normalize)
    data_err = np.sqrt(data_sumw2)

    # ---- MC histograms ----
    mc_histos = {}   # label -> (counts, errors)
    for label, (vals, w) in mc_dict.items():
        counts, sumw2 = weighted_histogram(vals, w, edges)
        norm_counts, norm_sumw2 = normalize_histogram(counts, sumw2, normalize)
        mc_histos[label] = (norm_counts, np.sqrt(norm_sumw2))

    # ---- Plot ----
    fig, (ax, rax) = plt.subplots(
        2,
        1,
        figsize=(15.0, 8.8),
        sharex=True,
        gridspec_kw={"height_ratios": (3.0, 1.0), "hspace": 0.06},
    )

    # Data as black errorbar
    ax.errorbar(
        centers, data_counts, yerr=data_err,
        fmt="o", color=DATA_COLOR, markersize=4, label="Data (sWeighted)",
    )

    # MC as colored step histograms
    for label, (counts, err) in mc_histos.items():
        display_label = MC_LABELS.get(label, label)
        color = MC_COLORS.get(label, "gray")
        hep.histplot(
            counts, edges, yerr=err,
            histtype="step", linewidth=2, color=color, ax=ax,
            label=display_label,
        )

    ylabel = "Normalized events" if normalize == "shape" else "Weighted events"
    ax.set_ylabel(ylabel, fontsize=20)
    ax.tick_params(labelbottom=False)
    ax.legend(loc="upper right", fontsize=16, frameon=False)

    _plot_pull_panel(rax, edges, centers, mc_histos, data_counts, data_sumw2)
    rax.set_xlabel(xlabel)
    rax.grid(True, axis="y", alpha=0.25)

    fig.subplots_adjust(left=0.10, right=0.96, top=0.84, bottom=0.10)
    _apply_cms_work_in_progress_label(ax, data=True)
    _save_figure(fig, output_base)
    plt.close(fig)


def plot_correlation_heatmap(
    pair_name: str,
    hist: np.ndarray,
    output_base: str,
    sample_label: str,
    normalize: str = "shape",
    is_data: bool = False,
):
    """Draw one 2D correlation heatmap for data or one MC subprocess."""
    fig, ax = plt.subplots(figsize=(16.0, 7.4))
    positive = hist[hist > 0.0].ravel()
    vmin = float(np.min(positive)) if positive.size else 0.0
    vmax = float(np.max(hist)) if hist.size else 1.0
    if vmax <= vmin:
        vmin = 0.0
        vmax = max(float(np.max(hist)) if hist.size else 1.0, 1.0e-12)
    mesh = ax.pcolormesh(
        CORRELATION_DY_EDGES,
        CORRELATION_DPHI_EDGES,
        hist.T,
        shading="auto",
        vmin=vmin,
        vmax=vmax,
    )
    ax.set_xlabel(label_for_branch(f"sel_abs_dy_{pair_name}"), fontsize=16)
    ax.set_ylabel(label_for_branch(f"sel_abs_dphi_{pair_name}"), fontsize=16)
    cbar = fig.colorbar(mesh, ax=ax, pad=0.02)
    cbar.set_label(
        "Normalized events" if normalize == "shape" else "Weighted events",
        fontsize=11,
        labelpad=8,
    )
    cbar.ax.tick_params(labelsize=10)
    cbar.ax.yaxis.get_offset_text().set_visible(False)

    fig.subplots_adjust(left=0.08, right=0.90, top=0.70, bottom=0.12)
    _apply_cms_work_in_progress_label(ax, data=is_data, fontsize=15)
    _draw_top_row_label(ax, sample_label, x=0.54, y_offset=0.002, ha="center", fontsize=10)
    _save_figure(fig, output_base)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    args = parse_args()

    output_dir = args.output_dir or os.path.join(
        OUTPUT_BASE, "plots", "jjp_kinematics"
    )
    ensure_dir(output_dir)
    apply_cms_style()

    # ------------------------------------------------------------------
    # 1. Prepare sWeighted data
    # ------------------------------------------------------------------
    if args.skip_splot:
        if not args.weighted_data:
            raise ValueError("--skip-splot requires --weighted-data")
        weighted_data_path = args.weighted_data
    else:
        if args.weighted_data:
            weighted_data_path = args.weighted_data
        else:
            weighted_data_path = os.path.join(
                output_dir, "temp", "jjp_data_weighted.root"
            )

        if not os.path.exists(weighted_data_path):
            ensure_dir(os.path.dirname(weighted_data_path))
            run_splot_on_data(args.data_input, weighted_data_path, args.jobs)
        else:
            print(f"[INFO] Using existing weighted file: {weighted_data_path}")

    # ------------------------------------------------------------------
    # 2. Open data tree
    # ------------------------------------------------------------------
    data_file = uproot.open(weighted_data_path)
    data_tree = data_file[INPUT_TREE]
    target_branches = _comparison_1d_branches(data_tree)
    correlation_specs = _pair_correlation_specs(data_tree)
    print(f"[INFO] Plotting {len(target_branches)} 1D branches "
          f"and {len(correlation_specs)} 2D correlation pairs")
    data_cache = TreeArrayCache.from_tree(
        data_tree,
        _required_source_branches(target_branches, correlation_specs, "signal_sw"),
        "data",
    )

    # ------------------------------------------------------------------
    # 3. Data-only kinematics plots
    # ------------------------------------------------------------------
    if args.mode in ("data", "all"):
        data_plot_dir = os.path.join(output_dir, "data_kinematics")
        ensure_dir(data_plot_dir)

        for i_branch, branch in enumerate(target_branches, start=1):
            _log_progress(
                f"data-only 1D {i_branch}/{len(target_branches)}: {branch}"
            )
            values, weights = _load_branch_from_cache(data_cache, branch, "signal_sw")
            plot_data_kinematics(
                branch, values, weights,
                os.path.join(data_plot_dir, branch),
            )

        n_plots = len(target_branches)
        print(f"[INFO] Wrote {n_plots} data kinematics plots → {data_plot_dir}")

    # ------------------------------------------------------------------
    # 4. Data-MC comparison plots
    # ------------------------------------------------------------------
    if args.mode in ("comparison", "all"):
        mc_dir = args.mc_dir
        comparison_dir = os.path.join(output_dir, "comparison")
        ensure_dir(comparison_dir)
        comparison_2d_dir = os.path.join(comparison_dir, "correlations_2d")
        ensure_dir(comparison_2d_dir)

        # Open all MC files
        mc_caches: dict[str, TreeArrayCache] = {}
        mc_required_branches = _required_source_branches(
            target_branches,
            correlation_specs,
            None,
        )
        for tag, sample_fn in MC_SAMPLE_FILES.items():
            mc_path = _find_mc_file(mc_dir, tag, sample_fn)
            if mc_path is None:
                tried = ", ".join(_mc_file_candidates(mc_dir, tag, sample_fn))
                print(f"[WARNING] MC file not found for {tag}; tried: {tried}")
                continue
            f = uproot.open(mc_path)
            tree = f[INPUT_TREE]
            print(f"[INFO] Loaded MC {MC_LABELS.get(tag, tag)}: "
                  f"{tree.num_entries} entries from {mc_path}")
            mc_caches[tag] = TreeArrayCache.from_tree(
                tree,
                mc_required_branches,
                f"MC {tag}",
            )

        if not mc_caches:
            raise RuntimeError("No MC files found — cannot produce comparison plots")

        # For each branch, load data + all MC samples, then plot
        for i_branch, branch in enumerate(target_branches, start=1):
            _log_progress(
                f"Data/MC 1D {i_branch}/{len(target_branches)}: {branch}"
            )
            # Data
            data_vals, data_w = _load_branch_from_cache(data_cache, branch, "signal_sw")

            # MC
            actual_branch = _resolve_kinematics_branch(branch)
            mc_dict: dict[str, tuple[np.ndarray, np.ndarray]] = {}
            for tag, cache in mc_caches.items():
                if not _branch_exists_in_cache(cache, branch):
                    print(f"[WARNING] Branch '{actual_branch}' missing in MC {tag}, skipping")
                    continue
                mc_vals, mc_w = _load_branch_from_cache(cache, branch, None)
                mc_dict[tag] = (mc_vals, mc_w)

            if not mc_dict:
                print(f"[WARNING] No MC data for branch '{branch}', skipping")
                continue

            plot_comparison(
                branch, data_vals, data_w, mc_dict,
                os.path.join(comparison_dir, branch),
                normalize=args.normalize,
            )

        for i_pair, (pair_name, dy_branch, dphi_branch) in enumerate(correlation_specs, start=1):
            _log_progress(
                f"2D correlation {i_pair}/{len(correlation_specs)}: {pair_name} data"
            )
            data_x, data_y, data_w = _load_pair_2d_from_cache(data_cache, dy_branch, dphi_branch, "signal_sw")
            data_hist = _histogram2d(data_x, data_y, data_w, args.normalize)
            plot_correlation_heatmap(
                pair_name,
                data_hist,
                os.path.join(comparison_2d_dir, f"data_correlation_2d_{pair_name}"),
                "Data",
                normalize=args.normalize,
                is_data=True,
            )
            n_2d_mc = 0
            for i_mc, (tag, cache) in enumerate(mc_caches.items(), start=1):
                _log_progress(
                    f"2D correlation {i_pair}/{len(correlation_specs)}: "
                    f"{pair_name} MC {i_mc}/{len(mc_caches)} {tag}"
                )
                if not cache.has(dy_branch) or not cache.has(dphi_branch):
                    print(f"[WARNING] 2D branches missing in MC {tag} for {pair_name}, skipping")
                    continue
                mc_x, mc_y, mc_w = _load_pair_2d_from_cache(cache, dy_branch, dphi_branch, None)
                mc_hist = _histogram2d(mc_x, mc_y, mc_w, args.normalize)
                plot_correlation_heatmap(
                    pair_name,
                    mc_hist,
                    os.path.join(comparison_2d_dir, f"{tag}_correlation_2d_{pair_name}"),
                    MC_LABELS.get(tag, tag),
                    normalize=args.normalize,
                    is_data=False,
                )
                n_2d_mc += 1
            if n_2d_mc == 0:
                print(f"[WARNING] No MC 2D data for pair '{pair_name}', skipping")

        print(f"[INFO] Wrote {len(target_branches)} integrated 1D comparison plots → {comparison_dir}")
        print(f"[INFO] Wrote {len(correlation_specs)} 2D correlation comparison plots → {comparison_2d_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

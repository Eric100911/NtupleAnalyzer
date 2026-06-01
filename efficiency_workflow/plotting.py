from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from IPython.display import display
except ImportError:  # pragma: no cover
    def display(obj):
        print(obj)

import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from matplotlib.colors import TwoSlopeNorm
from mpl_toolkits.axes_grid1 import make_axes_locatable

from .config import CmsPlotStyleConfig


FIT_PROJECTION_LABELS = {
    "Jpsi_1_mass": r"$m_{\mu\mu}$ [GeV]",
    "Jpsi_2_mass": r"$m_{\mu\mu}$ [GeV]",
    "Ups_mass": r"$m_{\mu\mu}$ [GeV]",
    "Phi_mass": r"$m_{KK}$ [GeV]",
}

FIT_PROJECTION_TITLES = {
    "roofit": {
        "Jpsi_1_mass": r"3D-fit projection on $J/\psi_1$",
        "Jpsi_2_mass": r"3D-fit projection on $J/\psi_2$",
        "Ups_mass": r"3D-fit projection on $\Upsilon$",
        "Phi_mass": r"3D-fit projection on $\phi$",
    },
    "iminuit": {
        "Jpsi_1_mass": r"iminuit projection on $J/\psi_1$",
        "Jpsi_2_mass": r"iminuit projection on $J/\psi_2$",
        "Ups_mass": r"iminuit projection on $\Upsilon$",
        "Phi_mass": r"iminuit projection on $\phi$",
    },
}

SUBPROCESS_LABELS = {
    "JJP_DPS1": r"DPS $J/\psi+(J/\psi+\phi)$",
    "JJP_DPS2_CS": r"DPS $(J/\psi+J/\psi)+\phi$ @ CSM LO",
    "JJP_DPS2_G": r"DPS $(J/\psi+J/\psi)+\phi$ @ CSM NLO$^{*}$",
    "JJP_SPS_CS": r"SPS $J/\psi+J/\psi+\phi$ @ CSM LO",
    "JJP_SPS_G": r"SPS $J/\psi+J/\psi+\phi$ @ CSM NLO$^{*}$",
    "JJP_TPS": r"TPS $J/\psi+J/\psi+\phi$",
}


def _require_mplhep():
    try:
        import mplhep as hep
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("mplhep is required to render CMS-style fit projection plots.") from exc
    return hep


_STEP_DISPLAY_NAMES = {
    # Per-object steps
    "fiducial": "Fiducial acceptance",
    "muonRECO": "Muon reco.",
    "muonID": "Muon ID",
    "dimuon": "Dimuon",
    "kaonRECO": "Kaon reco.",
    "kaonID": "Kaon ID",
    "dikaon": "Dikaon",
    # Event-level steps
    "full_gen": "Full GEN",
    "s_cand": r"$S_{\mathrm{cand}}$",
    "hlt_event": "HLT",
    "hlt_muon_matched": "HLT muon matching",
    "four_muon_vtx": r"$4\mu$ vertex",
    "four_muon_vtx_noTrigMatch": r"$4\mu$ vertex (no trig. match)",
    "Pri_fitValid": "Fit validity",
    "Pri_fitValid_noTrigMatch": "Fit validity (no trig. match)",
    "Pri_fitPass": "Fit quality",
    "Pri_fitPass_noTrigMatch": "Fit quality (no trig. match)",
    "Pri_assocPVPass": "PV association",
    "Pri_assocPVPass_noTrigMatch": "PV association (no trig. match)",
    "Pri_trackPVPass": "Track PV",
    "Pri_trackPVPass_noTrigMatch": "Track PV (no trig. match)",
    # Old names (kept for backward compat during transition)
    "fiducial_acceptance": "Fiducial acceptance",
    "single_jpsi_reco": r"Single $J/\psi$ reco.",
    "double_jpsi_reco": r"Double $J/\psi$ reco.",
    "single_phi_reco": r"$\phi$ reco.",
    "triple_gen_matched_candidate": "Triple candidate matching",
    "jpsi_quality": r"$J/\psi$ quality",
    "phi_quality": r"$\phi$ quality",
    "all6_same_recVtx": "Common vertex",
}


def _step_display_name(step: str) -> str:
    return _STEP_DISPLAY_NAMES.get(step, step.replace("_", " "))


def _efficiency_zlabel(step: str) -> str:
    label = _step_display_name(step)
    lowered = label.lower()
    if "efficiency" in lowered or "acceptance" in lowered:
        return label
    return f"{label} Efficiency"


def subprocess_label_for_sample(sample: str | None) -> str | None:
    if sample is None:
        return None
    return SUBPROCESS_LABELS.get(sample)


def with_subprocess_label(plot_style_cfg: CmsPlotStyleConfig, sample: str | None) -> CmsPlotStyleConfig:
    if plot_style_cfg.subprocess_label is not None:
        return plot_style_cfg
    label = subprocess_label_for_sample(sample)
    if label is None:
        return plot_style_cfg
    return replace(plot_style_cfg, subprocess_label=label)


def default_fit_plot_specs(
    fit_branches: tuple[str, ...] | list[str],
    backend: str,
    bins: int = 20,
) -> list[dict[str, object]]:
    if backend not in FIT_PROJECTION_TITLES:
        raise KeyError(f"Unknown fit projection backend: {backend}")
    specs = []
    for branch in fit_branches:
        if branch not in FIT_PROJECTION_LABELS:
            continue
        specs.append(
            {
                "branch": branch,
                "xlabel": FIT_PROJECTION_LABELS[branch],
                "title": FIT_PROJECTION_TITLES[backend][branch],
                "bins": int(bins),
            }
        )
    return specs


def _cms_caption(plot_style_cfg: CmsPlotStyleConfig) -> str:
    if plot_style_cfg.caption is not None:
        return plot_style_cfg.caption
    return "Preliminary"


def _draw_top_row_elements(ax, labels: list[tuple[float, str]]) -> None:
    if not labels:
        return
    axes_box = ax.get_position()
    y = axes_box.y1 + 0.006
    for x, text in labels:
        ax.figure.text(
            x,
            y,
            text,
            ha="center",
            va="bottom",
            fontsize=10,
        )


def apply_cms_label(
    ax,
    plot_style_cfg: CmsPlotStyleConfig,
    top_row_labels: list[tuple[float, str]] | None = None,
) -> None:
    hep = _require_mplhep()
    label_kwargs = {
        "ax": ax,
        "data": bool(plot_style_cfg.is_data),
        "label": _cms_caption(plot_style_cfg),
        "loc": 0,
    }
    if plot_style_cfg.lumi_fb is not None:
        label_kwargs["lumi"] = float(plot_style_cfg.lumi_fb)
    if plot_style_cfg.era and plot_style_cfg.era.isdigit():
        label_kwargs["year"] = int(plot_style_cfg.era)
        label_kwargs["com"] = float(plot_style_cfg.energy_tev)
    elif plot_style_cfg.era:
        label_kwargs["rlabel"] = f"{plot_style_cfg.era} ({float(plot_style_cfg.energy_tev):g} TeV)"
    else:
        label_kwargs["com"] = float(plot_style_cfg.energy_tev)

    hep.cms.label(**label_kwargs)

    labels = list(top_row_labels or [])
    if plot_style_cfg.subprocess_label:
        axes_box = ax.get_position()
        subprocess_x = 0.54 if axes_box.width < 0.50 else 0.48
        labels.insert(0, (subprocess_x, plot_style_cfg.subprocess_label))
    _draw_top_row_elements(ax, labels)


def evaluate_roofit_pdf_counts(root_module, var, pdf, yield_value: float, n_bins: int, x_range: tuple[float, float]):
    x_min, x_max = x_range
    x = np.linspace(x_min, x_max, 800)
    norm_set = root_module.RooArgSet(var)
    y = np.empty_like(x)
    for idx, xv in enumerate(x):
        var.setVal(float(xv))
        y[idx] = pdf.getVal(norm_set)
    bin_width = (x_max - x_min) / n_bins
    return x, float(yield_value) * y * bin_width


def save_fit_projection_plot(
    output_path: Path,
    values: np.ndarray,
    x_range: tuple[float, float],
    plot_spec: dict[str, object],
    x: np.ndarray,
    signal_curve: np.ndarray,
    background_curve: np.ndarray,
    plot_style_cfg: CmsPlotStyleConfig,
) -> Path:
    hep = _require_mplhep()
    hep.style.use("CMS")
    counts, edges = np.histogram(values, bins=int(plot_spec["bins"]), range=x_range)
    centers = 0.5 * (edges[:-1] + edges[1:])
    errors = np.sqrt(np.maximum(counts, 1.0))

    fig, ax = plt.subplots(figsize=(8.8, 6.2))
    ax.errorbar(centers, counts, yerr=errors, fmt="o", color="black", ms=4.5, label="Data")
    ax.plot(x, signal_curve + background_curve, color="#d62728", lw=2.0, label="Total fit")
    ax.plot(x, signal_curve, color="#1f77b4", lw=2.0, ls="--", label="Signal projection")
    ax.plot(x, background_curve, color="#2ca02c", lw=2.0, ls=":", label="Background projection")
    ax.set_xlim(*x_range)
    ax.set_xlabel(str(plot_spec["xlabel"]))
    ax.set_ylabel("Candidates / bin")
    ax.set_title(str(plot_spec["title"]))
    ax.grid(alpha=0.25)
    ax.legend(loc="upper right")
    apply_cms_label(ax, plot_style_cfg)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def write_yield_comparison_plot(
    output_path: Path,
    result,
    plot_style_cfg: CmsPlotStyleConfig | None = None,
) -> Path:
    """Write a subprocess comparison plot for efficiency-corrected yields."""
    hep = _require_mplhep()
    hep.style.use("CMS")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plot_style_cfg = plot_style_cfg or CmsPlotStyleConfig(is_data=True, lumi_fb=289.2, energy_tev=13.6, era="Run 3")

    samples = list(result.per_sample)
    values = np.asarray([result.per_sample[sample].corrected_yield for sample in samples], dtype=float)
    errors = np.asarray([result.per_sample[sample].corrected_yield_err for sample in samples], dtype=float)
    x = np.arange(len(samples), dtype=float)
    colors = ["#d62728" if sample == result.nominal_sample else "#4c78a8" for sample in samples]

    fig, ax = plt.subplots(figsize=(9.4, 6.2))
    if values.size:
        ymin = float(np.nanmin(values))
        ymax = float(np.nanmax(values))
        ax.axhspan(ymin, ymax, color="#d9d9d9", alpha=0.45, label="Subprocess envelope")
    ax.axhline(result.raw_yield, color="#555555", lw=1.5, ls="--", label="Raw fitted yield")
    ax.bar(x, values, yerr=errors, color=colors, edgecolor="black", linewidth=0.8, capsize=4)
    ax.set_xticks(x)
    ax.set_xticklabels(samples, rotation=25, ha="right")
    ax.set_ylabel("Efficiency-corrected signal yield")
    ax.set_xlabel("Efficiency map sample")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="upper right")
    apply_cms_label(ax, plot_style_cfg)
    fig.tight_layout()
    fig.savefig(output_path, dpi=170)
    plt.close(fig)
    return output_path


def apply_cms_label_root(canvas, plot_style_cfg: CmsPlotStyleConfig) -> None:
    """Draw CMS Preliminary label on a ROOT TCanvas using TLatex.

    Call inside a ROOT Batch session after frame.Draw().
    """
    import ROOT

    canvas.cd()
    # CMS bold
    cms_latex = ROOT.TLatex()
    cms_latex.SetNDC()
    cms_latex.SetTextFont(62)
    cms_latex.SetTextSize(0.045)
    cms_latex.DrawLatex(0.13, 0.935, "CMS")

    # Preliminary italic
    prelim_latex = ROOT.TLatex()
    prelim_latex.SetNDC()
    prelim_latex.SetTextFont(52)
    prelim_latex.SetTextSize(0.045)
    prelim_latex.DrawLatex(0.24, 0.935, _cms_caption(plot_style_cfg))

    # Energy + era
    if plot_style_cfg.era and plot_style_cfg.era.isdigit():
        extra = f"{plot_style_cfg.era} ({float(plot_style_cfg.energy_tev):g} TeV)"
    else:
        extra = f"{float(plot_style_cfg.energy_tev):g} TeV"
    if plot_style_cfg.lumi_fb is not None:
        extra = f"{plot_style_cfg.lumi_fb:g} fb^{{-1}} ({extra})"
    extra_latex = ROOT.TLatex()
    extra_latex.SetNDC()
    extra_latex.SetTextFont(42)
    extra_latex.SetTextSize(0.035)
    extra_latex.SetTextAlign(31)  # right-aligned
    extra_latex.DrawLatex(0.94, 0.935, extra)

    canvas.Update()


def write_roofit_projection_plots(
    output_dir: Path,
    fit_payload: dict[str, object],
    plot_style_cfg: CmsPlotStyleConfig,
    plot_specs: list[dict[str, object]] | None = None,
) -> dict[str, Path]:
    fit_df = fit_payload["fit_df"]
    if fit_df.empty:
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)
    plot_specs = plot_specs or default_fit_plot_specs(tuple(fit_payload["fit_branches"]), backend="roofit")
    projection_payloads = projection_specs(fit_payload, plot_specs)
    written: dict[str, Path] = {}

    for branch, spec in projection_payloads.items():
        x_range = fit_payload["active_windows"][branch]
        values = fit_df[branch].to_numpy(dtype=float)
        root_module = fit_payload["root_module"]
        x, signal_curve = evaluate_roofit_pdf_counts(
            root_module,
            spec["var"],
            spec["signal_pdf"],
            spec["signal"],
            int(spec["bins"]),
            x_range,
        )
        _, background_curve = evaluate_roofit_pdf_counts(
            root_module,
            spec["var"],
            spec["background_pdf"],
            spec["background"],
            int(spec["bins"]),
            x_range,
        )
        path = output_dir / f"projection_{branch}.png"
        written[branch] = save_fit_projection_plot(
            path,
            values,
            x_range,
            spec,
            x,
            signal_curve,
            background_curve,
            plot_style_cfg,
        )
    return written


def write_iminuit_projection_plots(
    output_dir: Path,
    fit_payload: dict[str, object],
    plot_style_cfg: CmsPlotStyleConfig,
    plot_specs: list[dict[str, object]] | None = None,
) -> dict[str, Path]:
    fit_df = fit_payload["fit_df"]
    if fit_df.empty:
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)
    plot_specs = plot_specs or default_fit_plot_specs(tuple(fit_payload["fit_branches"]), backend="iminuit")
    plot_spec_map = {str(spec["branch"]): spec for spec in plot_specs}
    written: dict[str, Path] = {}

    for branch in fit_payload["fit_branches"]:
        spec = plot_spec_map[branch]
        x_range = fit_payload["active_windows"][branch]
        values = fit_df[branch].to_numpy(dtype=float)
        x = np.linspace(*x_range, 800)
        bin_width = (x_range[1] - x_range[0]) / int(spec["bins"])
        signal_curve, background_curve = projection_curves_iminuit(
            fit_payload["minuit"],
            branch,
            x,
            fit_payload["active_windows"],
            fit_payload["analysis_mode"],
            fit_payload.get("ups_background_order", 4),
        )
        path = output_dir / f"projection_{branch}.png"
        written[branch] = save_fit_projection_plot(
            path,
            values,
            x_range,
            spec,
            x,
            signal_curve * bin_width,
            background_curve * bin_width,
            plot_style_cfg,
        )
    return written


def display_frame(obj, sort_by: str | list[str] | None = None, columns: list[str] | None = None, head: int | None = None):
    frame = obj.copy() if isinstance(obj, pd.DataFrame) else pd.DataFrame(obj)
    if columns is not None:
        frame = frame[columns]
    if sort_by is not None and not frame.empty:
        frame = frame.sort_values(sort_by).reset_index(drop=True)
    if head is not None:
        frame = frame.head(head)
    display(frame)
    return frame


def plot_metric_bars(frame: pd.DataFrame, classifier_col: str = "classifier", metric_cols: list[str] | None = None, title: str = "Classifier metrics"):
    metric_cols = metric_cols or ["precision", "recall", "specificity"]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    x = list(range(len(frame)))
    width = 0.8 / len(metric_cols)
    for offset, metric in enumerate(metric_cols):
        values = frame[metric].tolist()
        positions = [xi + (offset - (len(metric_cols) - 1) / 2.0) * width for xi in x]
        ax.bar(positions, values, width=width, label=metric)
    ax.set_xticks(x)
    ax.set_xticklabels(frame[classifier_col].tolist(), rotation=30, ha="right")
    ax.set_ylim(0.0, 1.05)
    ax.set_ylabel("Metric value")
    ax.set_title(title)
    ax.legend(loc="upper right")
    plt.tight_layout()
    plt.show()


def plot_truth_heatmap(df: pd.DataFrame, pred_col: str, truth_col: str = "truth_triple_strict", title: str | None = None):
    table = pd.crosstab(df[pred_col], df[truth_col]).reindex(index=[0, 1], columns=[0, 1], fill_value=0)
    fig, ax = plt.subplots(figsize=(4.4, 3.6))
    im = ax.imshow(table.values, cmap="Blues")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["truth=0", "truth=1"])
    ax.set_yticks([0, 1])
    ax.set_yticklabels([f"{pred_col}=0", f"{pred_col}=1"])
    ax.set_title(title or f"{pred_col} vs truth")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, int(table.values[i, j]), ha="center", va="center", color="black")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    plt.tight_layout()
    plt.show()
    return table


def plot_hist_by_truth(df: pd.DataFrame, column: str, clip: tuple[float, float] | None = None, bins: int = 30, xscale: str = "linear", yscale: str = "linear"):
    if xscale not in ["linear", "log"]:
        raise ValueError(f"xscale must be 'linear' or 'log', got '{xscale}'")
    if yscale not in ["linear", "log"]:
        raise ValueError(f"yscale must be 'linear' or 'log', got '{yscale}'")

    data = df[[column, "truth_triple_strict"]].copy()
    data = data[pd.notna(data[column])]
    if clip is not None:
        data = data[(data[column] >= clip[0]) & (data[column] <= clip[1])]

    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    for truth_value, label, color in [(0, "truth-negative", "#d95f02"), (1, "truth-positive", "#1b9e77")]:
        subset = data.loc[data["truth_triple_strict"] == truth_value, column]
        if not subset.empty:
            ax.hist(subset, bins=bins, histtype="step", linewidth=2, label=label, color=color)
    ax.set_title(f"{column} by truth label")
    ax.set_xscale(xscale)
    ax.set_yscale(yscale)
    ax.set_xlabel(column)
    ax.set_ylabel("Candidates")
    ax.legend()
    plt.tight_layout()
    plt.show()


def plot_phi_vtxprob_scan(scan_df: pd.DataFrame, chosen_cut: float):
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.2))
    thresholds = scan_df["Phi_VtxProb_cut"].replace(0.0, 1e-6)

    axes[0].plot(thresholds, scan_df["truth_positive_eff_vs_baseline"], marker="o", label="truth-positive efficiency")
    axes[0].plot(thresholds, scan_df["truth_negative_eff_vs_baseline"], marker="o", label="truth-negative efficiency")
    axes[0].plot(thresholds, scan_df["pileup_like_eff_vs_baseline"], marker="o", label="pileup-like efficiency")
    axes[0].axvline(chosen_cut, color="black", linestyle="--", linewidth=1.5, label=f"chosen cut = {chosen_cut:.0e}")
    axes[0].set_xscale("log")
    axes[0].set_ylim(0.0, 1.05)
    axes[0].set_xlabel("Phi_VtxProb threshold")
    axes[0].set_ylabel("Efficiency vs Phi_vertexCriteriaPass baseline")
    axes[0].set_title("Retention scan inside the baseline")
    axes[0].legend()

    axes[1].plot(thresholds, scan_df["pileup_like_rejection_vs_baseline"], marker="o", color="#d95f02")
    axes[1].axvline(chosen_cut, color="black", linestyle="--", linewidth=1.5)
    axes[1].set_xscale("log")
    axes[1].set_ylim(0.0, 1.05)
    axes[1].set_xlabel("Phi_VtxProb threshold")
    axes[1].set_ylabel("Pileup-like rejection vs baseline")
    axes[1].set_title("How much extra background is removed?")
    plt.tight_layout()
    plt.show()


def _efficiency_matrix(frame: pd.DataFrame, value_col: str) -> tuple[np.ndarray, list[str], list[str]]:
    if frame.empty:
        return np.empty((0, 0)), [], []
    x_bins = sorted(int(value) for value in frame["x_bin"].dropna().unique())
    y_bins = sorted(int(value) for value in frame["y_bin"].dropna().unique())
    matrix = np.full((len(y_bins), len(x_bins)), np.nan)
    for _, row in frame.iterrows():
        if pd.isna(row.get("x_bin")) or pd.isna(row.get("y_bin")):
            continue
        ix = x_bins.index(int(row["x_bin"]))
        iy = y_bins.index(int(row["y_bin"]))
        if int(row.get("total", 0)) > 0:
            matrix[iy, ix] = float(row[value_col])
    x_labels = [
        str(frame.loc[frame["x_bin"] == idx, "x_label"].dropna().iloc[0])
        if not frame.loc[frame["x_bin"] == idx, "x_label"].dropna().empty
        else str(idx)
        for idx in x_bins
    ]
    y_labels = [
        str(frame.loc[frame["y_bin"] == idx, "y_label"].dropna().iloc[0])
        if not frame.loc[frame["y_bin"] == idx, "y_label"].dropna().empty
        else str(idx)
        for idx in y_bins
    ]
    return matrix, x_labels, y_labels


def _efficiency_matrix_with_edges(frame: pd.DataFrame, value_col: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if frame.empty:
        return np.empty((0, 0)), np.asarray([]), np.asarray([])
    x_bins = sorted(int(value) for value in frame["x_bin"].dropna().unique())
    y_bins = sorted(int(value) for value in frame["y_bin"].dropna().unique())
    matrix = np.full((len(y_bins), len(x_bins)), np.nan)
    for _, row in frame.iterrows():
        if pd.isna(row.get("x_bin")) or pd.isna(row.get("y_bin")):
            continue
        ix = x_bins.index(int(row["x_bin"]))
        iy = y_bins.index(int(row["y_bin"]))
        if int(row.get("total", 0)) > 0:
            matrix[iy, ix] = float(row[value_col])
    x_edges = np.asarray(
        [float(frame.loc[frame["x_bin"] == idx, "x_min"].dropna().iloc[0]) for idx in x_bins]
        + [float(frame.loc[frame["x_bin"] == x_bins[-1], "x_max"].dropna().iloc[0])]
    )
    y_edges = np.asarray(
        [float(frame.loc[frame["y_bin"] == idx, "y_min"].dropna().iloc[0]) for idx in y_bins]
        + [float(frame.loc[frame["y_bin"] == y_bins[-1], "y_max"].dropna().iloc[0])]
    )
    return matrix, x_edges, y_edges


def _annotate_efficiency_bins(ax, frame: pd.DataFrame, include_uncertainty: bool = True, max_cells: int = 80) -> None:
    if frame.empty or frame.shape[0] > max_cells:
        return
    x_span = float(frame["x_max"].max() - frame["x_min"].min())
    y_span = float(frame["y_max"].max() - frame["y_min"].min())
    for _, row in frame.iterrows():
        total = int(row.get("total", 0))
        if total <= 0 or pd.isna(row.get("x_bin")) or pd.isna(row.get("y_bin")):
            continue
        x = 0.5 * (float(row["x_min"]) + float(row["x_max"]))
        y = 0.5 * (float(row["y_min"]) + float(row["y_max"]))
        x_frac = (float(row["x_max"]) - float(row["x_min"])) / x_span if x_span > 0 else 1.0
        y_frac = (float(row["y_max"]) - float(row["y_min"])) / y_span if y_span > 0 else 1.0
        compact = x_frac < 0.065 or y_frac < 0.09
        if compact:
            text = f"{float(row['efficiency']):.2f}"
            fontsize = 5.8
        elif include_uncertainty:
            text = f"{float(row['efficiency']):.2f}\n+/-{float(row['err_sym']):.2f}\n{int(row['passed'])}/{total}"
            fontsize = 5.8
        else:
            text = f"{float(row['efficiency']):.2f}\n{int(row['passed'])}/{total}"
            fontsize = 6.1
        value = float(row["efficiency"])
        color = "white" if np.isfinite(value) and value < 0.45 else "black"
        stroke = "black" if color == "white" else "white"
        artist = ax.text(x, y, text, ha="center", va="center", fontsize=fontsize, color=color)
        artist.set_path_effects([path_effects.withStroke(linewidth=1.4, foreground=stroke)])


def _object_label(raw: object) -> str:
    labels = {
        "jpsi": r"J/\psi",
        "jpsi_lead": r"J/\psi_{\mathrm{lead}}",
        "jpsi_sublead": r"J/\psi_{\mathrm{sublead}}",
        "phi": r"\phi",
    }
    return labels.get(str(raw), str(raw).replace("_", " "))


def _object_math_label(raw: object) -> str:
    """Return _object_label output wrapped in $...$ for use in titles."""
    return f"${_object_label(raw)}$"


def _axis_labels_for_frame(frame: pd.DataFrame, xlabel: str | None, ylabel: str | None) -> tuple[str, str]:
    if xlabel is not None and ylabel is not None:
        return xlabel, ylabel
    obj = frame["object"].dropna().iloc[0] if "object" in frame and not frame["object"].dropna().empty else "object"
    label = _object_label(obj)
    return xlabel or rf"$p_{{\mathrm{{T}}}}({label})$ [GeV]", ylabel or rf"$y({label})$"


def _draw_heatmap_panel(fig, ax, frame: pd.DataFrame, value_col: str, zlabel: str, annotate: bool, include_uncertainty_text: bool):
    matrix, x_edges, y_edges = _efficiency_matrix_with_edges(frame, value_col)
    mesh = ax.pcolormesh(x_edges, y_edges, matrix, shading="auto", vmin=0.0, vmax=1.0, cmap="viridis")
    ax.set_xlim(float(x_edges[0]), float(x_edges[-1]))
    ax.set_ylim(float(y_edges[0]), float(y_edges[-1]))
    ax.minorticks_on()
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="4.5%", pad=0.08)
    cbar = fig.colorbar(mesh, cax=cax)
    cbar.set_label(zlabel)
    if annotate and value_col == "efficiency":
        _annotate_efficiency_bins(ax, frame, include_uncertainty=include_uncertainty_text)
    return mesh


def save_efficiency_heatmap(
    output_path: Path,
    frame: pd.DataFrame,
    title: str | None,
    xlabel: str | None,
    ylabel: str | None,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int = 1,
    include_uncertainty: bool = False,
    show_title: bool = False,
    annotate: bool = True,
    zlabel: str = "Efficiency",
    top_row_labels: list[tuple[float, str]] | None = None,
) -> Path:
    hep = _require_mplhep()
    hep.style.use("CMS")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame = frame.copy()
    frame.loc[frame["total"] < int(min_total), ["efficiency", "err_sym"]] = np.nan
    xlabel, ylabel = _axis_labels_for_frame(frame, xlabel, ylabel)

    style = {
        "font.size": 12,
        "axes.titlesize": 15,
        "axes.labelsize": 12,
        "xtick.labelsize": 12,
        "ytick.labelsize": 12,
    }
    with plt.rc_context(style):
        if include_uncertainty:
            fig, axes = plt.subplots(1, 2, figsize=(16.0, 5.3), constrained_layout=False)
            fig.subplots_adjust(left=0.07, right=0.96, bottom=0.15, top=0.82, wspace=0.38)
            _draw_heatmap_panel(fig, axes[0], frame, "efficiency", zlabel, annotate, False)
            _draw_heatmap_panel(fig, axes[1], frame, "err_sym", "Sym. CP uncertainty", False, False)
            for ax in axes:
                ax.set_xlabel(xlabel)
                ax.set_ylabel(ylabel)
            if show_title and title:
                fig.suptitle(title, fontsize=16, y=0.97)
            label_ax = axes[0]
        else:
            fig, ax = plt.subplots(figsize=(12.5, 5.4), constrained_layout=False)
            fig.subplots_adjust(left=0.10, right=0.88, bottom=0.14, top=0.82)
            _draw_heatmap_panel(fig, ax, frame, "efficiency", zlabel, annotate, False)
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            if show_title and title:
                ax.set_title(title, pad=8)
            label_ax = ax
        apply_cms_label(label_ax, plot_style_cfg, top_row_labels=top_row_labels)
        fig.savefig(output_path, dpi=170)
    plt.close(fig)
    return output_path


def _draw_value_heatmap_panel(
    fig,
    ax,
    frame: pd.DataFrame,
    value_col: str,
    zlabel: str,
    *,
    vmin: float | None,
    vmax: float | None,
    cmap: str,
    center: float | None = None,
):
    matrix, x_edges, y_edges = _efficiency_matrix_with_edges(frame, value_col)
    norm = None
    if center is not None and vmin is not None and vmax is not None and vmin < center < vmax:
        norm = TwoSlopeNorm(vmin=vmin, vcenter=center, vmax=vmax)
    mesh = ax.pcolormesh(
        x_edges,
        y_edges,
        matrix,
        shading="auto",
        vmin=None if norm is not None else vmin,
        vmax=None if norm is not None else vmax,
        cmap=cmap,
        norm=norm,
    )
    ax.set_xlim(float(x_edges[0]), float(x_edges[-1]))
    ax.set_ylim(float(y_edges[0]), float(y_edges[-1]))
    ax.minorticks_on()
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="4.5%", pad=0.08)
    cbar = fig.colorbar(mesh, cax=cax)
    cbar.set_label(zlabel)
    return mesh


def _save_value_heatmap(
    output_path: Path,
    frame: pd.DataFrame,
    value_col: str,
    title: str | None,
    xlabel: str | None,
    ylabel: str | None,
    plot_style_cfg: CmsPlotStyleConfig,
    *,
    min_total: int = 1,
    vmin: float | None = None,
    vmax: float | None = None,
    cmap: str = "viridis",
    zlabel: str = "Value",
    center: float | None = None,
    top_row_labels: list[tuple[float, str]] | None = None,
) -> Path:
    hep = _require_mplhep()
    hep.style.use("CMS")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame = frame.copy()
    if "total" in frame.columns:
        frame.loc[frame["total"] < int(min_total), value_col] = np.nan
    xlabel, ylabel = _axis_labels_for_frame(frame, xlabel, ylabel)

    style = {
        "font.size": 12,
        "axes.titlesize": 15,
        "axes.labelsize": 12,
        "xtick.labelsize": 12,
        "ytick.labelsize": 12,
    }
    with plt.rc_context(style):
        fig, ax = plt.subplots(figsize=(12.5, 5.4), constrained_layout=False)
        fig.subplots_adjust(left=0.10, right=0.88, bottom=0.14, top=0.82)
        _draw_value_heatmap_panel(
            fig,
            ax,
            frame,
            value_col,
            zlabel,
            vmin=vmin,
            vmax=vmax,
            cmap=cmap,
            center=center,
        )
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        if title:
            ax.set_title(title, pad=8)
        apply_cms_label(ax, plot_style_cfg, top_row_labels=top_row_labels)
        fig.savefig(output_path, dpi=170)
    plt.close(fig)
    return output_path


def save_ratio_heatmap(
    output_path: Path,
    frame: pd.DataFrame,
    ratio_col: str,
    title: str | None,
    xlabel: str | None,
    ylabel: str | None,
    plot_style_cfg: CmsPlotStyleConfig,
    *,
    min_total: int = 1,
    vmin: float = 0.5,
    vmax: float = 1.5,
    cmap: str = "RdBu_r",
    zlabel: str = "Ratio",
    top_row_labels: list[tuple[float, str]] | None = None,
) -> Path:
    return _save_value_heatmap(
        output_path,
        frame,
        ratio_col,
        title,
        xlabel,
        ylabel,
        plot_style_cfg,
        min_total=min_total,
        vmin=vmin,
        vmax=vmax,
        cmap=cmap,
        zlabel=zlabel,
        center=1.0,
        top_row_labels=top_row_labels,
    )


def _write_2d_object_maps(
    output_dir: Path,
    df: pd.DataFrame,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int = 1,
    include_uncertainty: bool = False,
    *,
    subdir: str | None = None,
    zlabel_fn: Callable[[str], str] = _efficiency_zlabel,
) -> dict[str, Path]:
    target_dir = (output_dir / subdir) if subdir else output_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    obj_df = df.loc[df["map_type"] == "object_2d"].copy()
    for (obj, step), frame in obj_df.groupby(["object", "step"], dropna=False):
        step_label = _step_display_name(step)
        obj_label = _object_math_label(obj)
        path = target_dir / f"object2d_{obj}_{step}.png"
        written[f"object2d.{obj}.{step}"] = save_efficiency_heatmap(
            path, frame,
            title=f"{obj_label} {step_label}",
            xlabel=r"$p_{\mathrm{T}}$ [GeV]",
            ylabel=None,
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
            include_uncertainty=include_uncertainty,
            show_title=include_uncertainty,
            zlabel=zlabel_fn(step),
        )
    return written


def _write_correlated_3d_maps(
    output_dir: Path,
    df: pd.DataFrame,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int = 1,
    include_uncertainty: bool = False,
    *,
    subdir: str | None = None,
    zlabel_fn: Callable[[str], str] = _efficiency_zlabel,
) -> dict[str, Path]:
    target_dir = (output_dir / subdir) if subdir else output_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    corr_df = df.loc[df["map_type"] == "correlated_3d"].copy()
    for (step, z_bin), frame in corr_df.groupby(["step", "z_bin"], dropna=False):
        z_label = str(frame["z_label"].dropna().iloc[0]) if not frame["z_label"].dropna().empty else str(z_bin)
        step_label = _step_display_name(step)
        phi_pt_label = rf"$p_{{\mathrm{{T}}}}(\phi)$ = {z_label} GeV"
        path = target_dir / f"corr3d_{step}_phiPt_{z_bin}.png"
        written[f"corr3d.{step}.{z_bin}"] = save_efficiency_heatmap(
            path, frame,
            title=step_label,
            xlabel=r"$p_{\mathrm{T}}(J/\psi_{\mathrm{lead}})$ [GeV]",
            ylabel=r"$p_{\mathrm{T}}(J/\psi_{\mathrm{sublead}})$ [GeV]",
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
            include_uncertainty=include_uncertainty,
            show_title=include_uncertainty,
            zlabel=zlabel_fn(step),
            top_row_labels=[(0.66, phi_pt_label)],
        )
    return written


def write_efficiency_plots(
    output_dir: Path,
    counts_df: pd.DataFrame,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int = 1,
    include_uncertainty: bool = False,
) -> dict[str, Path]:
    if counts_df.empty:
        return {}
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    written.update(_write_2d_object_maps(
        output_dir, counts_df,
        plot_style_cfg=plot_style_cfg, min_total=min_total,
        include_uncertainty=include_uncertainty,
    ))
    written.update(_write_correlated_3d_maps(
        output_dir, counts_df,
        plot_style_cfg=plot_style_cfg, min_total=min_total,
        include_uncertainty=include_uncertainty,
    ))
    return written


def write_efficiency_plot_bundle(
    sample_dir: Path,
    counts_df: pd.DataFrame,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int = 1,
) -> dict[str, dict[str, str]]:
    plot_style_cfg = with_subprocess_label(plot_style_cfg, sample_dir.name)
    plot_paths = write_efficiency_plots(
        sample_dir / "plots",
        counts_df,
        plot_style_cfg=plot_style_cfg,
        min_total=min_total,
    )
    qa_paths = write_efficiency_plots(
        sample_dir / "plots_with_uncertainty",
        counts_df,
        plot_style_cfg=plot_style_cfg,
        min_total=min_total,
        include_uncertainty=True,
    )
    outputs = {
        "plots": {
            key: str(path.relative_to(sample_dir))
            for key, path in plot_paths.items()
        }
    }
    if qa_paths:
        outputs["plots_with_uncertainty"] = {
            key: str(path.relative_to(sample_dir))
            for key, path in qa_paths.items()
        }
    return outputs


def write_derived_plots(
    output_dir: Path,
    acc_df: pd.DataFrame,
    cond_df: pd.DataFrame,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int = 1,
    include_uncertainty: bool = False,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    # Acceptance maps: per-object fiducial acceptance (iterates object only, no step)
    acc_plot_dir = output_dir / "acceptance"
    acc_plot_dir.mkdir(parents=True, exist_ok=True)
    obj_acc = acc_df.loc[acc_df["map_type"] == "object_2d"].copy()
    for obj, frame in obj_acc.groupby("object", dropna=False):
        obj_label = _object_math_label(obj)
        path = acc_plot_dir / f"object2d_{obj}_fiducial_acceptance.png"
        written[f"object2d.{obj}.fiducial_acceptance"] = save_efficiency_heatmap(
            path, frame,
            title=f"{obj_label} fiducial acceptance",
            xlabel=r"$p_{\mathrm{T}}$ [GeV]",
            ylabel=None,
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
            include_uncertainty=include_uncertainty,
            show_title=include_uncertainty,
            zlabel="Acceptance",
        )

    # Conditional: per-object and correlated 3D (exclude full_gen from object maps)
    cond_obj_df = cond_df.loc[
        (cond_df["map_type"] == "object_2d") & (cond_df["step"] != "full_gen")
    ].copy()
    written.update(_write_2d_object_maps(
        output_dir, cond_obj_df,
        plot_style_cfg=plot_style_cfg, min_total=min_total,
        include_uncertainty=include_uncertainty, subdir="conditional",
    ))
    written.update(_write_correlated_3d_maps(
        output_dir, cond_df,
        plot_style_cfg=plot_style_cfg, min_total=min_total,
        include_uncertainty=include_uncertainty, subdir="conditional",
    ))
    return written


def write_per_object_acceptance_plots(
    output_dir: Path,
    poa_df: pd.DataFrame,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int = 1,
    include_uncertainty: bool = False,
) -> dict[str, Path]:
    if poa_df.empty:
        return {}
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    obj_df = poa_df.loc[poa_df["map_type"].isin(["object_2d", "object_acceptance_2d"])].copy()
    for obj, frame in obj_df.groupby("object", dropna=False):
        path = output_dir / f"object2d_{obj}_fiducial_acceptance.png"
        obj_label = _object_math_label(obj)
        written[f"object2d.{obj}.fiducial_acceptance"] = save_efficiency_heatmap(
            path,
            frame,
            title=f"{obj_label} per-object fiducial acceptance",
            xlabel=None,
            ylabel=None,
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
            include_uncertainty=include_uncertainty,
            show_title=include_uncertainty,
            zlabel="Acceptance",
        )
    return written


def write_stacked_jpsi_plots(
    output_dir: Path,
    stacked_acceptance_df: pd.DataFrame,
    stacked_efficiency_df: pd.DataFrame,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int = 1,
    include_uncertainty: bool = False,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    if not stacked_acceptance_df.empty:
        path = output_dir / "stacked_jpsi_fiducial_acceptance.png"
        written["stacked_jpsi.fiducial_acceptance"] = save_efficiency_heatmap(
            path,
            stacked_acceptance_df,
            title=r"Stacked $J/\psi$ fiducial acceptance",
            xlabel=None,
            ylabel=None,
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
            include_uncertainty=include_uncertainty,
            show_title=include_uncertainty,
            zlabel="Acceptance",
        )
    if not stacked_efficiency_df.empty:
        for step, frame in stacked_efficiency_df.groupby("step", dropna=False):
            if step in {"full_gen", "fiducial", "fiducial_acceptance"}:
                continue
            step_label = _step_display_name(step)
            path = output_dir / f"stacked_jpsi_{step}.png"
            written[f"stacked_jpsi.{step}"] = save_efficiency_heatmap(
                path,
                frame,
                title=rf"Stacked $J/\psi$ {step_label}",
                xlabel=None,
                ylabel=None,
                plot_style_cfg=plot_style_cfg,
                min_total=min_total,
                include_uncertainty=include_uncertainty,
                show_title=include_uncertainty,
                zlabel=_efficiency_zlabel(step),
            )
    return written


def write_pair_level_plot(
    output_dir: Path, df: pd.DataFrame, step: str,
    plot_style_cfg: CmsPlotStyleConfig, min_total: int,
    include_uncertainty: bool = False,
) -> dict[str, Path]:
    """Single pair-level heatmap for a given step."""
    if df.empty:
        return {}
    output_dir.mkdir(parents=True, exist_ok=True)
    step_label = _step_display_name(step)
    path = output_dir / f"pair2d_{step}.png"
    written: dict[str, Path] = {f"pair2d.{step}": save_efficiency_heatmap(
        path, df,
        title=f"{step_label} efficiency",
        xlabel=r"$p_{\mathrm{T}}(J/\psi_{\mathrm{lead}})$ [GeV]",
        ylabel=r"$p_{\mathrm{T}}(J/\psi_{\mathrm{sublead}})$ [GeV]",
        plot_style_cfg=plot_style_cfg,
        min_total=min_total,
        include_uncertainty=include_uncertainty,
        show_title=include_uncertainty,
        zlabel=_efficiency_zlabel(step),
    )}
    return written


def write_pair_level_plots(
    output_dir: Path,
    pair_maps: dict[str, pd.DataFrame],
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int = 1,
    include_uncertainty: bool = False,
) -> dict[str, Path]:
    written: dict[str, Path] = {}
    for step, frame in pair_maps.items():
        written.update(
            write_pair_level_plot(
                output_dir,
                frame,
                step,
                plot_style_cfg=plot_style_cfg,
                min_total=min_total,
                include_uncertainty=include_uncertainty,
            )
        )
    return written


def _safe_filename_part(value: object) -> str:
    text = str(value)
    for old, new in [
        (" ", "_"),
        ("/", "_"),
        ("\\", "_"),
        ("$", ""),
        ("{", ""),
        ("}", ""),
        ("(", ""),
        (")", ""),
        (".", "p"),
    ]:
        text = text.replace(old, new)
    return text


def _systematic_2d_groups(frame: pd.DataFrame):
    if frame.empty or "x_bin" not in frame.columns or "y_bin" not in frame.columns:
        return
    two_d = frame.loc[frame["x_bin"].notna() & frame["y_bin"].notna()].copy()
    if two_d.empty:
        return

    group_cols = ["map_type"]
    for column in ("object", "step", "z_bin", "quantity"):
        if column in two_d.columns and not two_d[column].dropna().empty:
            group_cols.append(column)

    for keys, group in two_d.groupby(group_cols, dropna=False):
        key_values = keys if isinstance(keys, tuple) else (keys,)
        metadata = dict(zip(group_cols, key_values))
        yield metadata, group


def _systematic_plot_labels(metadata: dict[str, object], product_type: str) -> tuple[str, str | None, str | None, list[tuple[float, str]] | None]:
    map_type = str(metadata.get("map_type", "map"))
    step = metadata.get("step")
    obj = metadata.get("object")
    z_bin = metadata.get("z_bin")
    title_parts = [product_type.replace("_", " ")]
    if obj is not None and pd.notna(obj):
        title_parts.append(_object_math_label(obj))
    if step is not None and pd.notna(step):
        title_parts.append(_step_display_name(str(step)))

    xlabel = None
    ylabel = None
    top_row_labels = None
    if map_type == "correlated_3d":
        xlabel = r"$p_{\mathrm{T}}(J/\psi_{\mathrm{lead}})$ [GeV]"
        ylabel = r"$p_{\mathrm{T}}(J/\psi_{\mathrm{sublead}})$ [GeV]"
        if z_bin is not None and pd.notna(z_bin):
            top_row_labels = [(0.66, rf"$p_{{\mathrm{{T}}}}(\phi)$ bin {z_bin:g}")]
    elif map_type == "pair_vertex_2d":
        xlabel = r"$p_{\mathrm{T}}(J/\psi_{\mathrm{lead}})$ [GeV]"
        ylabel = r"$p_{\mathrm{T}}(J/\psi_{\mathrm{sublead}})$ [GeV]"
    elif obj is not None and pd.notna(obj):
        xlabel = r"$p_{\mathrm{T}}$ [GeV]"

    return " ".join(title_parts), xlabel, ylabel, top_row_labels


def _systematic_plot_stem(metadata: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ("map_type", "object", "step", "z_bin", "quantity"):
        value = metadata.get(key)
        if value is None or pd.isna(value):
            continue
        if key == "z_bin":
            parts.append(f"z{int(value)}")
        else:
            parts.append(_safe_filename_part(value))
    return "_".join(parts) if parts else "map"


def _finite_max(frame: pd.DataFrame, column: str, default: float) -> float:
    values = frame[column].to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return default
    return float(np.max(values))


def _write_ratio_plots_for_product_type(
    output_dir: Path,
    product_type: str,
    systematics_df: pd.DataFrame,
    sample: str,
    nominal_sample: str,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int,
) -> dict[str, Path]:
    ratio_col = f"ratio_{sample}"
    if ratio_col not in systematics_df.columns:
        return {}
    written: dict[str, Path] = {}
    for metadata, frame in _systematic_2d_groups(systematics_df):
        if frame[ratio_col].dropna().empty:
            continue
        title, xlabel, ylabel, top_row_labels = _systematic_plot_labels(metadata, product_type)
        stem = _systematic_plot_stem(metadata)
        path = output_dir / product_type / sample / f"{stem}.png"
        written[f"ratio.{product_type}.{sample}.{stem}"] = save_ratio_heatmap(
            path,
            frame,
            ratio_col,
            title=f"{title}: {sample} / {nominal_sample}",
            xlabel=xlabel,
            ylabel=ylabel,
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
            zlabel=f"{sample} / {nominal_sample}",
            top_row_labels=top_row_labels,
        )
    return written


def _write_envelope_plots_for_product_type(
    output_dir: Path,
    product_type: str,
    systematics_df: pd.DataFrame,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int,
) -> dict[str, Path]:
    value_col = "envelope_half_width"
    if value_col not in systematics_df.columns:
        return {}
    written: dict[str, Path] = {}
    vmax = min(1.0, max(0.05, _finite_max(systematics_df, value_col, 0.05)))
    for metadata, frame in _systematic_2d_groups(systematics_df):
        if frame[value_col].dropna().empty:
            continue
        title, xlabel, ylabel, top_row_labels = _systematic_plot_labels(metadata, product_type)
        stem = _systematic_plot_stem(metadata)
        path = output_dir / product_type / f"{stem}.png"
        written[f"envelope.{product_type}.{stem}"] = _save_value_heatmap(
            path,
            frame,
            value_col,
            title=f"{title}: envelope half-width",
            xlabel=xlabel,
            ylabel=ylabel,
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
            vmin=0.0,
            vmax=vmax,
            cmap="viridis",
            zlabel="Envelope half-width",
            top_row_labels=top_row_labels,
        )
    return written


def _write_pull_plots_for_product_type(
    output_dir: Path,
    product_type: str,
    systematics_df: pd.DataFrame,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int,
) -> dict[str, Path]:
    value_col = "max_abs_pull"
    if value_col not in systematics_df.columns:
        return {}
    written: dict[str, Path] = {}
    vmax = max(3.0, _finite_max(systematics_df, value_col, 3.0))
    for metadata, frame in _systematic_2d_groups(systematics_df):
        if frame[value_col].dropna().empty:
            continue
        title, xlabel, ylabel, top_row_labels = _systematic_plot_labels(metadata, product_type)
        stem = _systematic_plot_stem(metadata)
        path = output_dir / product_type / f"{stem}.png"
        written[f"pull.{product_type}.{stem}"] = _save_value_heatmap(
            path,
            frame,
            value_col,
            title=f"{title}: max pull",
            xlabel=xlabel,
            ylabel=ylabel,
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
            vmin=0.0,
            vmax=vmax,
            cmap="magma",
            zlabel="Max |pull|",
            top_row_labels=top_row_labels,
        )
    return written


def write_systematic_uncertainty_plots(
    output_dir: Path,
    results,
    plot_style_cfg: CmsPlotStyleConfig,
    *,
    min_total: int = 1,
) -> dict[str, object]:
    systematics_dir = results.output_dir if results.output_dir != Path(".") else output_dir / "systematics"
    plots_dir = systematics_dir / "plots"
    ratio_dir = plots_dir / "ratio"
    envelope_dir = plots_dir / "envelope"
    pull_dir = plots_dir / "pull"
    written: dict[str, Path] = {}

    for product_type, product in results.products.items():
        frame = product.systematics_df
        if frame.empty:
            continue
        for sample in product.per_sample_dfs:
            if sample == results.nominal_sample:
                continue
            written.update(
                _write_ratio_plots_for_product_type(
                    ratio_dir,
                    product_type,
                    frame,
                    sample,
                    results.nominal_sample,
                    plot_style_cfg,
                    min_total,
                )
            )
        written.update(
            _write_envelope_plots_for_product_type(
                envelope_dir,
                product_type,
                frame,
                plot_style_cfg,
                min_total,
            )
        )
        written.update(
            _write_pull_plots_for_product_type(
                pull_dir,
                product_type,
                frame,
                plot_style_cfg,
                min_total,
            )
        )

    return {key: str(path.relative_to(systematics_dir)) for key, path in written.items()}


def _dual_plot_invocation(
    derived_dir: Path,
    fn: Callable[..., dict[str, Path]],
    *,
    subdir: str,
    output_key: str,
    qa_prefix: str,
    **fn_kwargs,
) -> dict[str, object]:
    """Call a plot writer twice (regular + QA with uncertainty), return manifest entries."""
    outputs: dict[str, object] = {}
    regular = fn(derived_dir / "plots" / subdir, **fn_kwargs)
    if regular:
        outputs[output_key] = {
            k: str(p.relative_to(derived_dir)) for k, p in regular.items()
        }
    qa = fn(derived_dir / "plots_with_uncertainty" / subdir, **fn_kwargs, include_uncertainty=True)
    if qa:
        outputs.setdefault("plots_with_uncertainty", {}).update(
            {f"{qa_prefix}.{k}": str(p.relative_to(derived_dir)) for k, p in qa.items()}
        )
    return outputs


def write_derived_plot_bundle(
    derived_dir: Path,
    *,
    acceptance_df: pd.DataFrame,
    conditional_df: pd.DataFrame,
    per_object_acceptance_df: pd.DataFrame,
    stacked_jpsi_acceptance_df: pd.DataFrame,
    stacked_jpsi_efficiency_df: pd.DataFrame,
    pair_level_dfs: dict[str, pd.DataFrame],
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int = 1,
) -> dict[str, object]:
    from .products import PAIR_LEVEL_OUTPUT_NAMES

    plot_style_cfg = with_subprocess_label(plot_style_cfg, derived_dir.parent.name)
    outputs: dict[str, object] = {}

    if not per_object_acceptance_df.empty:
        outputs.update(_dual_plot_invocation(
            derived_dir, write_per_object_acceptance_plots,
            subdir="per_object_acceptance",
            output_key="per_object_acceptance_plots",
            qa_prefix="per_object_acceptance_qa",
            poa_df=per_object_acceptance_df,
            plot_style_cfg=plot_style_cfg, min_total=min_total,
        ))

    if not stacked_jpsi_acceptance_df.empty or not stacked_jpsi_efficiency_df.empty:
        outputs.update(_dual_plot_invocation(
            derived_dir, write_stacked_jpsi_plots,
            subdir="stacked_jpsi",
            output_key="stacked_jpsi_plots",
            qa_prefix="stacked_jpsi_qa",
            stacked_acceptance_df=stacked_jpsi_acceptance_df,
            stacked_efficiency_df=stacked_jpsi_efficiency_df,
            plot_style_cfg=plot_style_cfg, min_total=min_total,
        ))

    for step, frame in pair_level_dfs.items():
        if frame.empty:
            continue
        name = PAIR_LEVEL_OUTPUT_NAMES[step]
        outputs.update(_dual_plot_invocation(
            derived_dir, write_pair_level_plot,
            subdir="pair_vertex",
            output_key=f"{name}_plots",
            qa_prefix=f"{name}_qa",
            df=frame, step=step,
            plot_style_cfg=plot_style_cfg, min_total=min_total,
        ))

    if not acceptance_df.empty or not conditional_df.empty:
        outputs.update(_dual_plot_invocation(
            derived_dir, write_derived_plots,
            subdir="",
            output_key="derived_plots",
            qa_prefix="derived_qa",
            acc_df=acceptance_df, cond_df=conditional_df,
            plot_style_cfg=plot_style_cfg, min_total=min_total,
        ))

    return outputs

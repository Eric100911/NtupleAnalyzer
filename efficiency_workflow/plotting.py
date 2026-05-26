from __future__ import annotations

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


def _require_mplhep():
    try:
        import mplhep as hep
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("mplhep is required to render CMS-style fit projection plots.") from exc
    return hep


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


def apply_cms_label(ax, plot_style_cfg: CmsPlotStyleConfig) -> None:
    hep = _require_mplhep()
    label_kwargs = {
        "ax": ax,
        "data": bool(plot_style_cfg.is_data),
        "label": _cms_caption(plot_style_cfg),
        "com": float(plot_style_cfg.energy_tev),
    }
    if plot_style_cfg.lumi_fb is not None:
        label_kwargs["lumi"] = float(plot_style_cfg.lumi_fb)
    if plot_style_cfg.era and plot_style_cfg.era.isdigit():
        label_kwargs["year"] = int(plot_style_cfg.era)

    hep.cms.label(**label_kwargs, loc=0)

    if plot_style_cfg.era and not plot_style_cfg.era.isdigit():
        ax.text(0.03, 0.88, plot_style_cfg.era, transform=ax.transAxes, ha="left", va="top")


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


def save_efficiency_heatmap_pair(
    output_path: Path,
    frame: pd.DataFrame,
    title: str,
    xlabel: str,
    ylabel: str,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int = 1,
) -> Path:
    return save_efficiency_heatmap(
        output_path,
        frame,
        title=title,
        xlabel=xlabel,
        ylabel=ylabel,
        plot_style_cfg=plot_style_cfg,
        min_total=min_total,
        include_uncertainty=True,
        show_title=True,
    )


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
        "axes.labelsize": 15,
        "xtick.labelsize": 12,
        "ytick.labelsize": 12,
    }
    with plt.rc_context(style):
        if include_uncertainty:
            fig, axes = plt.subplots(1, 2, figsize=(11.6, 5.3), constrained_layout=False)
            fig.subplots_adjust(left=0.08, right=0.95, bottom=0.15, top=0.78, wspace=0.42)
            _draw_heatmap_panel(fig, axes[0], frame, "efficiency", "Efficiency", annotate, False)
            _draw_heatmap_panel(fig, axes[1], frame, "err_sym", "Sym. CP uncertainty", False, False)
            for ax in axes:
                ax.set_xlabel(xlabel)
                ax.set_ylabel(ylabel)
            if show_title and title:
                fig.suptitle(title, fontsize=16, y=0.97)
            label_ax = axes[0]
        else:
            fig, ax = plt.subplots(figsize=(6.9, 5.4), constrained_layout=False)
            fig.subplots_adjust(left=0.14, right=0.84, bottom=0.14, top=0.82)
            _draw_heatmap_panel(fig, ax, frame, "efficiency", "Efficiency", annotate, False)
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            if show_title and title:
                ax.set_title(title, pad=8)
            label_ax = ax
        apply_cms_label(label_ax, plot_style_cfg)
        fig.savefig(output_path, dpi=170)
    plt.close(fig)
    return output_path


def write_efficiency_plots(
    output_dir: Path,
    counts_df: pd.DataFrame,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int = 1,
) -> dict[str, Path]:
    if counts_df.empty:
        return {}
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    object_df = counts_df.loc[counts_df["map_type"] == "object_2d"].copy()
    for (obj, step), frame in object_df.groupby(["object", "step"], dropna=False):
        path = output_dir / f"object2d_{obj}_{step}.png"
        written[f"object2d.{obj}.{step}"] = save_efficiency_heatmap_pair(
            path,
            frame,
            title=f"{obj} {step}",
            xlabel=r"$p_{\mathrm{T}}$ [GeV]",
            ylabel=r"$|y|$",
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
        )

    corr_df = counts_df.loc[counts_df["map_type"] == "correlated_3d"].copy()
    for (step, z_bin), frame in corr_df.groupby(["step", "z_bin"], dropna=False):
        z_label = str(frame["z_label"].dropna().iloc[0]) if not frame["z_label"].dropna().empty else str(z_bin)
        path = output_dir / f"corr3d_{step}_phiPt_{z_bin}.png"
        written[f"corr3d.{step}.{z_bin}"] = save_efficiency_heatmap_pair(
            path,
            frame,
            title=rf"{step}, $p_{{T}}(\phi)$ = {z_label} GeV",
            xlabel=r"$p_{\mathrm{T}}(J/\psi_{\mathrm{lead}})$ [GeV]",
            ylabel=r"$p_{\mathrm{T}}(J/\psi_{\mathrm{sublead}})$ [GeV]",
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
        )
    return written


def write_derived_plots(
    output_dir: Path,
    acc_df: pd.DataFrame,
    cond_df: pd.DataFrame,
    plot_style_cfg: CmsPlotStyleConfig,
    min_total: int = 1,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    acc_plot_dir = output_dir / "acceptance"
    acc_plot_dir.mkdir(parents=True, exist_ok=True)
    obj_acc = acc_df.loc[acc_df["map_type"] == "object_2d"].copy()
    for obj, frame in obj_acc.groupby("object", dropna=False):
        path = acc_plot_dir / f"object2d_{obj}_fiducial_acceptance.png"
        written[f"object2d.{obj}.fiducial_acceptance"] = save_efficiency_heatmap_pair(
            path,
            frame,
            title=f"{obj} fiducial_acceptance",
            xlabel=r"$p_{\mathrm{T}}$ [GeV]",
            ylabel=r"$|y|$",
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
        )

    cond_dir = output_dir / "conditional"
    cond_dir.mkdir(parents=True, exist_ok=True)
    obj_df = cond_df.loc[
        (cond_df["map_type"] == "object_2d") & (cond_df["step"] != "full_gen")
    ].copy()
    for (obj, step), frame in obj_df.groupby(["object", "step"], dropna=False):
        path = cond_dir / f"object2d_{obj}_{step}.png"
        written[f"object2d.{obj}.{step}"] = save_efficiency_heatmap_pair(
            path,
            frame,
            title=f"{obj} {step}",
            xlabel=r"$p_{\mathrm{T}}$ [GeV]",
            ylabel=r"$|y|$",
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
        )

    corr_df = cond_df.loc[cond_df["map_type"] == "correlated_3d"].copy()
    for (step, z_bin), frame in corr_df.groupby(["step", "z_bin"], dropna=False):
        z_label = str(frame["z_label"].dropna().iloc[0]) if not frame["z_label"].dropna().empty else str(z_bin)
        path = cond_dir / f"corr3d_{step}_phiPt_{z_bin}.png"
        written[f"corr3d.{step}.{z_bin}"] = save_efficiency_heatmap_pair(
            path,
            frame,
            title=rf"{step}, $p_{{T}}(\phi)$ = {z_label} GeV",
            xlabel=r"$p_{\mathrm{T}}(J/\psi_{\mathrm{lead}})$ [GeV]",
            ylabel=r"$p_{\mathrm{T}}(J/\psi_{\mathrm{sublead}})$ [GeV]",
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
        )
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
        written[f"object2d.{obj}.fiducial_acceptance"] = save_efficiency_heatmap(
            path,
            frame,
            title=f"{obj} per-object fiducial acceptance",
            xlabel=None,
            ylabel=None,
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
            include_uncertainty=include_uncertainty,
            show_title=include_uncertainty,
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
            title=r"stacked $J/\psi$ fiducial acceptance",
            xlabel=None,
            ylabel=None,
            plot_style_cfg=plot_style_cfg,
            min_total=min_total,
            include_uncertainty=include_uncertainty,
            show_title=include_uncertainty,
        )
    if not stacked_efficiency_df.empty:
        for step, frame in stacked_efficiency_df.groupby("step", dropna=False):
            if step in {"full_gen", "fiducial_acceptance"}:
                continue
            path = output_dir / f"stacked_jpsi_{step}.png"
            written[f"stacked_jpsi.{step}"] = save_efficiency_heatmap(
                path,
                frame,
                title=rf"stacked $J/\psi$ {step}",
                xlabel=None,
                ylabel=None,
                plot_style_cfg=plot_style_cfg,
                min_total=min_total,
                include_uncertainty=include_uncertainty,
                show_title=include_uncertainty,
            )
    return written

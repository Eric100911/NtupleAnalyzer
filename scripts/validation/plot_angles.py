#!/usr/bin/env python3
"""Plots for the JJP angular distributions.

Inputs
------
  outputs/angles/{data,mc_*}.parquet        per-event angles (compute_angles.py)
  outputs/binned_angles/{var}.json          per-bin mass-fit yields (fit_angular_bins.py)
  outputs/binned_angles/data_with_sweights.parquet

Outputs (PNG + PDF)
-------------------
  raw_{var}          data raw counts with the fitted signal + background decomposition
  subtracted_{var}   background-subtracted signal yield vs MC shapes
  mc_ratio_{var}     SPS_CS / DPS1 and SPS_CS / DPS2_CS shape ratios
  moments_summary    moment comparison across samples
  fit_vs_sweights    2x2 cross-check of per-bin fits against global sWeights
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mplhep as hep
from matplotlib.gridspec import GridSpec

try:
    from scipy.stats import ks_2samp, chi2 as chi2_dist
    HAVE_SCIPY = True
except Exception:  # pragma: no cover
    HAVE_SCIPY = False

VARIABLES = {
    "cos_theta_jpsi1": {
        "edges": np.linspace(-1.0, 1.0, 17),
        "xlabel": r"$\cos\theta^{*}_{J/\psi_1}$",
        "short": r"$\cos\theta^{*}_{J/\psi_1}$",
    },
    "cos_theta_jpsi2": {
        "edges": np.linspace(-1.0, 1.0, 17),
        "xlabel": r"$\cos\theta^{*}_{J/\psi_2}$",
        "short": r"$\cos\theta^{*}_{J/\psi_2}$",
    },
    "abs_cos_theta_phi": {
        "edges": np.linspace(0.0, 1.0, 11),
        "xlabel": r"$|\cos\theta^{*}_{\phi}|$",
        "short": r"$|\cos\theta^{*}_{\phi}|$",
    },
    "delta_phi_jj": {
        "edges": np.linspace(0.0, np.pi, 13),
        "xlabel": r"$\Delta\phi_{JJ}$ [rad]",
        "short": r"$\Delta\phi_{JJ}$",
    },
}

MC_FILES = {
    "JJP_DPS1": "mc_dps1.parquet",
    "JJP_DPS2_CS": "mc_dps2_cs.parquet",
    "JJP_DPS2_G": "mc_dps2_g.parquet",
    "JJP_SPS_CS": "mc_sps_cs.parquet",
    "JJP_SPS_G": "mc_sps_g.parquet",
}
LABELS = {
    "JJP_DPS1": "DPS1",
    "JJP_DPS2_CS": "DPS2 CS",
    "JJP_DPS2_G": "DPS2 G",
    "JJP_SPS_CS": "SPS CS",
    "JJP_SPS_G": "SPS G",
    "DATA": "Data (signal, fit)",
}
# Okabe-Ito colour-blind-safe palette.
COLORS = {
    "JJP_DPS1": "#0072B2",
    "JJP_DPS2_CS": "#E69F00",
    "JJP_DPS2_G": "#009E73",
    "JJP_SPS_CS": "#D55E00",
    "JJP_SPS_G": "#CC79A7",
    "DATA": "#000000",
}
HIGHLIGHT = ["JJP_DPS1", "JJP_DPS2_CS", "JJP_SPS_CS"]


def style():
    hep.style.use(hep.style.CMS)
    plt.rcParams.update({
        "font.size": 11,
        "axes.labelsize": 12,
        "axes.titlesize": 12,
        "legend.fontsize": 9,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "axes.grid": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 120,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "mathtext.fontset": "dejavusans",
    })


def hist(values, edges, weights=None):
    counts, _ = np.histogram(values, bins=edges, weights=weights)
    return counts.astype(float)


def poisson_err(n):
    return np.sqrt(np.maximum(n, 0.0))


def bin_centers(edges):
    return 0.5 * (edges[:-1] + edges[1:])


def load_mc(angles_dir: Path):
    mc = {}
    for sample, fname in MC_FILES.items():
        path = angles_dir / fname
        if path.exists():
            mc[sample] = pd.read_parquet(path)
    return mc


def load_fit(binned_dir: Path, var: str):
    with open(binned_dir / f"{var}.json") as fh:
        payload = json.load(fh)
    rows = payload["bins"]
    n = len(rows)
    out = {
        "lo": np.array([r["lo"] for r in rows]),
        "hi": np.array([r["hi"] for r in rows]),
        "n_events": np.array([r["n_events"] for r in rows], dtype=float),
        "signal": np.array([r.get("signal_yield", np.nan) for r in rows], dtype=float),
        "signal_err": np.array([r.get("signal_yield_err", np.nan) for r in rows], dtype=float),
        "bkg": np.zeros(n),
        "bkg_err2": np.zeros(n),
    }
    for r in rows:
        for key, value in r.items():
            if key.startswith("yield_") and not key.endswith("_err") and key != "yield_sss":
                out["bkg"][r["ibin"]] += value
                out["bkg_err2"][r["ibin"]] += r[key + "_err"] ** 2
    out["bkg_err"] = np.sqrt(out["bkg_err2"])

    # Boundary bins: the parabolic error of a yield pushed to zero is not
    # meaningful.  Flag them; the caller replaces the error with the
    # sWeight-based error.
    median_err = np.median(out["signal_err"][out["signal_err"] < 1e3])
    out["boundary"] = (out["signal_err"] > max(20.0 * median_err, 200.0))
    out["payload"] = payload
    return out


def sw_sum_by_bin(sw_frame, var, edges):
    n = len(edges) - 1
    sums = np.zeros(n)
    errs = np.zeros(n)
    counts = np.zeros(n, dtype=int)
    for i in range(n):
        lo, hi = edges[i], edges[i + 1]
        mask = (sw_frame[var] >= lo) & (
            (sw_frame[var] <= hi) if i == n - 1 else (sw_frame[var] < hi)
        )
        w = sw_frame.loc[mask, "yield_sss_sw"].to_numpy(dtype=float)
        sums[i] = w.sum()
        errs[i] = np.sqrt(np.sum(w * w))
        counts[i] = len(w)
    return sums, errs, counts


def ratio_with_err(num, num_err, den, den_err):
    num = np.asarray(num, dtype=float)
    num_err = np.asarray(num_err, dtype=float)
    den = np.asarray(den, dtype=float)
    den_err = np.asarray(den_err, dtype=float)
    safe = np.where(den != 0, den, np.nan)
    ratio = num / safe
    err = np.sqrt((num_err / safe) ** 2 + (num * den_err / safe ** 2) ** 2)
    return ratio, err


def chi2_ndf(n1, n2):
    """Shape-compatibility chi2 between two histograms (one normalization)."""
    n1 = np.asarray(n1, dtype=float)
    n2 = np.asarray(n2, dtype=float)
    if n1.sum() == 0 or n2.sum() == 0:
        return np.nan, np.nan, 0
    p = n1 / n1.sum()
    q = n2 / n2.sum()
    sp = np.sqrt(n1) / n1.sum()
    sq = np.sqrt(n2) / n2.sum()
    var = sp * sp + sq * sq
    mask = var > 0
    chi2 = float(np.sum((p[mask] - q[mask]) ** 2 / var[mask]))
    ndf = max(int(mask.sum()) - 1, 1)
    pval = float(chi2_dist.sf(chi2, ndf)) if HAVE_SCIPY else np.nan
    return chi2, ndf, pval


def save(fig, outdir: Path, name: str):
    outdir.mkdir(parents=True, exist_ok=True)
    if fig.axes:
        hep.cms.label("Work In Progress", loc=0, ax=fig.axes[0], rlabel="")
        fig.subplots_adjust(top=min(fig.subplotpars.top, 0.84))
    for ext in ("png", "pdf"):
        fig.savefig(outdir / f"{name}.{ext}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 1: raw distribution with fitted signal + background
# ---------------------------------------------------------------------------
def plot_raw(var, data, fit, outdir):
    cfg = VARIABLES[var]
    edges = cfg["edges"]
    centers = bin_centers(edges)
    width = np.diff(edges)
    raw = hist(data[var], edges)
    raw_err = poisson_err(raw)

    fig = plt.figure(figsize=(7.4, 6.4))
    gs = GridSpec(2, 1, height_ratios=[4, 1.5], hspace=0.05)
    ax = fig.add_subplot(gs[0])
    axr = fig.add_subplot(gs[1], sharex=ax)

    ax.bar(centers, fit["bkg"], width=width, color="#BDBDBD", edgecolor="#8A8A8A",
           linewidth=0.6, label="Fitted background")
    ax.bar(centers, fit["signal"], width=width, bottom=fit["bkg"], color="#56B4E9",
           edgecolor="#2B7BB9", linewidth=0.6, label=r"Fitted signal ($s s s$)")
    ax.errorbar(centers, raw, yerr=raw_err, fmt="o", ms=3.5, color="black",
                capsize=0, label="Data (raw)", zorder=5)

    ax.set_ylabel("Candidates / bin")
    ax.set_title(f"Raw angular distribution — {cfg['short']}")
    ax.legend(loc="upper right", ncol=1, frameon=False)
    ax.tick_params(labelbottom=False)

    model = fit["bkg"] + fit["signal"]
    # In boundary bins the parabolic signal error is meaningless; clip it for
    # the display ratio so it does not swamp the panel.
    good_err = fit["signal_err"][~fit["boundary"]]
    cap = 5.0 * float(np.median(good_err)) if good_err.size else np.inf
    sig_err_disp = np.minimum(fit["signal_err"], cap)
    ratio, ratio_err = ratio_with_err(raw, raw_err, model, np.sqrt(fit["bkg_err"] ** 2 + sig_err_disp ** 2))
    axr.axhline(1.0, color="gray", lw=0.8, ls="--")
    axr.errorbar(centers, ratio, yerr=ratio_err, fmt="o", ms=3, color="black", capsize=0)
    axr.set_ylim(0.85, 1.15)
    axr.set_ylabel("Data / model")
    axr.set_xlabel(cfg["xlabel"])
    save(fig, outdir, f"raw_{var}")


# ---------------------------------------------------------------------------
# Figure 2: background-subtracted data vs MC
# ---------------------------------------------------------------------------
def plot_subtracted(var, data, fit, mc, outdir, sw_frame=None):
    cfg = VARIABLES[var]
    edges = cfg["edges"]
    centers = bin_centers(edges)
    width = np.diff(edges)

    sig = fit["signal"].copy()
    sig_err = fit["signal_err"].copy()
    boundary = fit["boundary"].copy()
    if sw_frame is not None:
        sw_sums, sw_errs, _ = sw_sum_by_bin(sw_frame, var, edges)
        # For boundary bins use the sWeight estimate and its error.
        sig[boundary] = sw_sums[boundary]
        sig_err[boundary] = sw_errs[boundary]

    total_data = sig.sum()
    mc_hist = {}
    mc_err = {}
    for sample, frame in mc.items():
        counts = hist(frame[var], edges)
        mc_hist[sample] = counts
        mc_err[sample] = poisson_err(counts)
    # Normalise every MC sample to the data signal total.
    scale = {s: total_data / mc_hist[s].sum() for s in mc_hist}

    fig = plt.figure(figsize=(7.6, 7.0))
    gs = GridSpec(2, 1, height_ratios=[4, 2], hspace=0.07)
    ax = fig.add_subplot(gs[0])
    axr = fig.add_subplot(gs[1], sharex=ax)

    ax.errorbar(centers, sig, yerr=sig_err, fmt="o", ms=4, color="black", capsize=0,
                label=LABELS["DATA"], zorder=6)
    # Open markers for boundary bins whose error was replaced.
    if boundary.any():
        ax.plot(centers[boundary], sig[boundary], "o", ms=8, mfc="none", mec="black",
                mew=1.0, zorder=7, label="Boundary bin (sWeight error)")

    for sample in ["JJP_DPS2_G", "JJP_SPS_G", "JJP_DPS2_CS", "JJP_DPS1", "JJP_SPS_CS"]:
        if sample not in mc_hist:
            continue
        y = mc_hist[sample] * scale[sample]
        lw = 2.2 if sample == "JJP_SPS_CS" else 1.5
        ax.step(centers, y, where="mid", color=COLORS[sample], lw=lw,
                label=LABELS[sample], alpha=0.95 if sample in HIGHLIGHT else 0.75)

    ax.set_ylabel("Signal yield / bin")
    ax.set_title(f"Background-subtracted data vs MC — {cfg['short']}")
    ax.legend(loc="upper right", ncol=2, frameon=False, columnspacing=1.0)
    ax.tick_params(labelbottom=False)

    axr.axhline(1.0, color="gray", lw=0.8, ls="--")
    for sample in ["JJP_SPS_CS", "JJP_DPS1", "JJP_DPS2_CS"]:
        if sample not in mc_hist:
            continue
        expect = mc_hist[sample] * scale[sample]
        expect_err = mc_err[sample] * scale[sample]
        ratio, ratio_err = ratio_with_err(sig, sig_err, expect, expect_err)
        axr.errorbar(centers, ratio, yerr=ratio_err, fmt="o", ms=3.2,
                     color=COLORS[sample], capsize=0, label=LABELS[sample])
    axr.set_ylim(0.0, 2.2)
    axr.set_ylabel("Data / MC")
    axr.set_xlabel(cfg["xlabel"])
    save(fig, outdir, f"subtracted_{var}")

    # Return results for the summary.
    result = {
        "var": var,
        "centers": centers.tolist(),
        "signal": sig.tolist(),
        "signal_err": sig_err.tolist(),
        "boundary": boundary.tolist(),
        "mc_scale": {s: float(scale[s]) for s in scale},
        "mc_shape": {s: (mc_hist[s] / mc_hist[s].sum()).tolist() for s in mc_hist},
        "mc_shape_err": {s: (mc_err[s] / mc_hist[s].sum()).tolist() for s in mc_hist},
        "ks": {},
        "chi2": {},
    }
    if HAVE_SCIPY:
        for sample in ["JJP_DPS1", "JJP_DPS2_CS", "JJP_SPS_CS"]:
            if sample in mc:
                # MC-vs-MC shape compatibility (raw data includes background).
                chi2, ndf, pval = chi2_ndf(mc_hist["JJP_SPS_CS"], mc_hist[sample])
                result["chi2"][f"SPS_CS_vs_{sample}"] = {"chi2": chi2, "ndf": ndf, "p": pval}
    return result


# ---------------------------------------------------------------------------
# Figure 3: pure MC shape ratios
# ---------------------------------------------------------------------------
def plot_mc_ratio(var, mc, outdir):
    if "JJP_SPS_CS" not in mc or "JJP_DPS1" not in mc:
        return None
    cfg = VARIABLES[var]
    edges = cfg["edges"]
    centers = bin_centers(edges)
    counts = {s: hist(mc[s][var], edges) for s in mc}
    errs = {s: poisson_err(c) for s, c in counts.items()}

    fig = plt.figure(figsize=(7.4, 6.2))
    gs = GridSpec(2, 1, height_ratios=[3.5, 2], hspace=0.07)
    ax = fig.add_subplot(gs[0])
    axr = fig.add_subplot(gs[1], sharex=ax)

    for sample in ["JJP_DPS2_G", "JJP_SPS_G", "JJP_DPS2_CS", "JJP_DPS1", "JJP_SPS_CS"]:
        if sample not in counts:
            continue
        shape = counts[sample] / counts[sample].sum()
        lw = 2.2 if sample == "JJP_SPS_CS" else 1.5
        ax.step(centers, shape, where="mid", color=COLORS[sample], lw=lw,
                label=f"{LABELS[sample]} (N={int(counts[sample].sum())})",
                alpha=0.95 if sample in HIGHLIGHT else 0.7)
    ax.set_ylabel("Normalised / bin")
    ax.set_title(f"MC angular shapes — {cfg['short']}")
    ax.legend(loc="upper right", ncol=1, frameon=False)
    ax.tick_params(labelbottom=False)

    axr.axhline(1.0, color="gray", lw=0.8, ls="--")
    summary = {}
    base = counts["JJP_SPS_CS"] / counts["JJP_SPS_CS"].sum()
    base_err = errs["JJP_SPS_CS"] / counts["JJP_SPS_CS"].sum()
    for sample in ["JJP_DPS1", "JJP_DPS2_CS"]:
        if sample not in counts:
            continue
        other = counts[sample] / counts[sample].sum()
        other_err = errs[sample] / counts[sample].sum()
        ratio, ratio_err = ratio_with_err(base, base_err, other, other_err)
        axr.errorbar(centers, ratio, yerr=ratio_err, fmt="o", ms=3.5,
                     color=COLORS[sample], capsize=0, label=f"SPS CS / {LABELS[sample]}")
        chi2, ndf, pval = chi2_ndf(counts["JJP_SPS_CS"], counts[sample])
        summary[sample] = {
            "chi2": chi2, "ndf": ndf, "p": pval,
            "ks": float(ks_2samp(mc["JJP_SPS_CS"][var], mc[sample][var]).statistic) if HAVE_SCIPY else None,
        }
        axr.text(0.02, 0.95 if sample == "JJP_DPS1" else 0.80,
                 f"vs {LABELS[sample]}: $\\chi^2$/ndf = {chi2:.1f}/{ndf} (p={pval:.2g})",
                 transform=axr.transAxes, fontsize=9, va="top", color=COLORS[sample])
    axr.set_ylim(0.4, 1.6)
    axr.set_ylabel("SPS CS / other")
    axr.set_xlabel(cfg["xlabel"])
    axr.legend(loc="upper right", ncol=2, frameon=False)
    save(fig, outdir, f"mc_ratio_{var}")
    return summary


# ---------------------------------------------------------------------------
# Moments
# ---------------------------------------------------------------------------
def sample_moments(values, weights=None):
    values = np.asarray(values, dtype=float)
    mask = np.isfinite(values)
    values = values[mask]
    if weights is not None:
        weights = np.asarray(weights, dtype=float)[mask]
        wsum = weights.sum()
        mean = np.sum(weights * values) / wsum
        var = np.sum(weights * (values - mean) ** 2) / wsum
        mean_sq = np.sum(weights * values ** 2) / wsum
        n_eff = wsum ** 2 / np.sum(weights ** 2) if np.any(weights) else 0
    else:
        n = len(values)
        mean = values.mean()
        var = values.var()
        mean_sq = np.mean(values ** 2)
        n_eff = n
    return {
        "n": int(len(values)),
        "mean": float(mean),
        "std": float(np.sqrt(var)),
        "mean_sq": float(mean_sq),
        "mean_err": float(np.sqrt(var / n_eff)) if n_eff > 0 else np.nan,
    }


RHO00_MOMENT_COEFFICIENTS = {
    "cos_theta_jpsi1": (-5.0, 2.0),
    "cos_theta_jpsi2": (-5.0, 2.0),
    "abs_cos_theta_phi": (2.5, -0.5),
}


def rho00_from_mean_cos2(mean_sq, variable):
    """Selected-level moment estimate, without acceptance/efficiency correction.

    Vector-to-dilepton decays use 2 - 5 <cos^2(theta)>; vector-to-two-scalar
    decays use 2.5 <cos^2(theta)> - 0.5. These are not physical polarisation
    measurements when evaluated on the selected sample.
    """
    slope, offset = RHO00_MOMENT_COEFFICIENTS[variable]
    return slope * mean_sq + offset


def moments_table(data, fit, mc):
    rows = []
    # MC moments
    for sample, frame in mc.items():
        row = {"sample": sample, "n": len(frame),
               "moment_interpretation": "selected-level moment estimate (uncorrected)"}
        for var in ["cos_theta_jpsi1", "cos_theta_jpsi2", "abs_cos_theta_phi", "delta_phi_jj"]:
            m = sample_moments(frame[var])
            row[var + "_mean"] = m["mean"]
            row[var + "_mean_err"] = m["mean_err"]
            row[var + "_std"] = m["std"]
            if var in ("cos_theta_jpsi1", "cos_theta_jpsi2", "abs_cos_theta_phi"):
                row[var + "_mean_sq"] = m["mean_sq"]
                row[var + "_rho00"] = rho00_from_mean_cos2(m["mean_sq"], var)
                row[var + "_rho00_err"] = abs(RHO00_MOMENT_COEFFICIENTS[var][0]) * np.sqrt(
                    np.mean((frame[var].to_numpy() ** 2 - m["mean_sq"]) ** 2) / len(frame)
                )
        # Fourier moments of Delta phi
        dphi = frame["delta_phi_jj"].to_numpy()
        row["delta_phi_jj_cos1"] = float(np.mean(np.cos(dphi)))
        row["delta_phi_jj_cos2"] = float(np.mean(np.cos(2 * dphi)))
        rows.append(row)

    # Data signal moments from per-bin fit yields (bin centres for cos^2).
    row = {"sample": "DATA_SIGNAL_FIT", "n": int(np.nansum(fit["signal"])),
           "moment_interpretation": "selected-level moment estimate (uncorrected)"}
    for var in ["cos_theta_jpsi1", "cos_theta_jpsi2", "abs_cos_theta_phi", "delta_phi_jj"]:
        with open(fit["_binned_dir"] / f"{var}.json") as fh:
            payload = json.load(fh)
        edges = np.array(payload["edges"])
        centers = bin_centers(edges)
        sig = np.array([b.get("signal_yield", np.nan) for b in payload["bins"]])
        err = np.array([b.get("signal_yield_err", np.nan) for b in payload["bins"]])
        good = np.isfinite(sig) & np.isfinite(err) & (err < 200)
        if good.sum() == 0:
            continue
        w = sig[good]
        total = w.sum()
        mean = np.sum(w * centers[good]) / total
        mean_sq = np.sum(w * centers[good] ** 2) / total
        var_val = mean_sq - mean ** 2
        # Error propagation from independent bin yields.
        dmean = np.sqrt(np.sum((err[good] * (centers[good] - mean)) ** 2)) / total
        dmsq = np.sqrt(np.sum((err[good] * (centers[good] ** 2 - mean_sq)) ** 2)) / total
        row[var + "_mean"] = float(mean)
        row[var + "_mean_err"] = float(dmean)
        row[var + "_std"] = float(np.sqrt(max(var_val, 0.0)))
        if var in ("cos_theta_jpsi1", "cos_theta_jpsi2", "abs_cos_theta_phi"):
            row[var + "_mean_sq"] = float(mean_sq)
            row[var + "_rho00"] = float(rho00_from_mean_cos2(mean_sq, var))
            row[var + "_rho00_err"] = float(abs(RHO00_MOMENT_COEFFICIENTS[var][0]) * dmsq)
        if var == "delta_phi_jj":
            row["delta_phi_jj_cos1"] = float(np.sum(w * np.cos(centers[good])) / total)
            row["delta_phi_jj_cos2"] = float(np.sum(w * np.cos(2 * centers[good])) / total)
    rows.append(row)
    return pd.DataFrame(rows)


def plot_moments(table, outdir):
    samples = [s for s in ["JJP_DPS1", "JJP_DPS2_CS", "JJP_SPS_CS", "JJP_SPS_G", "JJP_DPS2_G"] if s in set(table["sample"])]
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.2))
    specs = [
        ("abs_cos_theta_phi_mean", r"$\langle |\cos\theta^{*}_{\phi}| \rangle$"),
        ("abs_cos_theta_phi_rho00", r"$\widehat{\rho}_{00}(\phi)=\frac{5}{2}\langle\cos^2\theta\rangle-\frac{1}{2}$"),
        ("cos_theta_jpsi1_rho00", r"$\widehat{\rho}_{00}(J/\psi_1)=2-5\langle\cos^2\theta\rangle$"),
    ]
    for ax, (key, label) in zip(axes, specs):
        xs, ys, es, cols = [], [], [], []
        for i, sample in enumerate(samples):
            row = table[table["sample"] == sample].iloc[0]
            if key not in table.columns or not np.isfinite(row.get(key, np.nan)):
                continue
            xs.append(i)
            ys.append(row[key])
            err_key = key.replace("_mean", "_mean_err").replace("_rho00", "_rho00_err")
            es.append(row.get(err_key, np.nan))
            cols.append(COLORS[sample])
        ax.errorbar(xs, ys, yerr=es, fmt="o", ms=6, capsize=3, color="black", mfc="none")
        for x, y, c in zip(xs, ys, cols):
            ax.plot([x], [y], "o", ms=7, color=c)
        ax.set_xticks(range(len(samples)))
        ax.set_xticklabels([LABELS[s] for s in samples], rotation=30, ha="right")
        ax.set_ylabel(label)
        ax.axhline(1.0 / 3.0, color="gray", ls="--", lw=0.8) if key.endswith("rho00") else None
    axes[0].set_title(r"$\phi$ decay-angle mean")
    axes[1].set_title(r"$\phi$ moment estimate")
    axes[2].set_title(r"$J/\psi_1$ moment estimate")
    fig.suptitle("Selected-level moment estimates (uncorrected)", y=1.02)
    fig.tight_layout()
    save(fig, outdir, "moments_summary")


def plot_fit_vs_sweights(fit_bins, sw_frame, outdir):
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
    axes = axes.ravel()
    for ax, var in zip(axes, VARIABLES):
        cfg = VARIABLES[var]
        edges = cfg["edges"]
        centers = bin_centers(edges)
        fit = fit_bins[var]
        sw_sums, sw_errs, _ = sw_sum_by_bin(sw_frame, var, edges)
        ax.axhline(0, color="gray", lw=0.8, ls="--")
        ax.errorbar(centers, fit["signal"], yerr=fit["signal_err"], fmt="o", ms=4,
                    color="#0072B2", capsize=0, label="Per-bin mass fit")
        ax.errorbar(centers, sw_sums, yerr=sw_errs, fmt="s", ms=4, mfc="none",
                    color="#D55E00", capsize=0, label="Global sWeights")
        ax.set_xlabel(cfg["xlabel"])
        ax.set_ylabel("Signal yield / bin")
        ax.legend(loc="upper right", frameon=False, fontsize=9)
        ax.set_title(cfg["short"])
    fig.suptitle("Background subtraction cross-check: per-bin fit vs global sWeights", y=1.01)
    fig.tight_layout()
    save(fig, outdir, "fit_vs_sweights")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angles-dir", required=True)
    ap.add_argument("--binned-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    style()
    angles_dir = Path(args.angles_dir)
    binned_dir = Path(args.binned_dir)
    outdir = Path(args.output_dir)

    data = pd.read_parquet(angles_dir / "data.parquet")
    mc = load_mc(angles_dir)
    sw_path = binned_dir / "data_with_sweights.parquet"
    sw_frame = pd.read_parquet(sw_path) if sw_path.exists() else None

    fit_bins = {var: load_fit(binned_dir, var) for var in VARIABLES}
    for var in VARIABLES:
        fit_bins[var]["_binned_dir"] = binned_dir

    summary = {}
    for var in VARIABLES:
        print(f"[plot] {var}")
        plot_raw(var, data, fit_bins[var], outdir)
        sub = plot_subtracted(var, data, fit_bins[var], mc, outdir, sw_frame=sw_frame)
        mcsum = plot_mc_ratio(var, mc, outdir)
        summary[var] = {"subtracted": sub, "mc_ratio": mcsum}

    table = moments_table(data, fit_bins["cos_theta_jpsi1"], mc)
    table.to_csv(outdir / "angular_moments.csv", index=False)
    plot_moments(table, outdir)
    if sw_frame is not None:
        plot_fit_vs_sweights(fit_bins, sw_frame, outdir)

    with open(outdir / "angular_summary.json", "w") as fh:
        json.dump(summary, fh, indent=1)
    print(f"[plot] wrote {outdir}")


if __name__ == "__main__":
    main()

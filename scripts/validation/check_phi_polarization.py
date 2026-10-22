#!/usr/bin/env python3
"""Check whether the SPS_CS phi polarisation difference is kinematic.

The phi decay angle is measured in the phi helicity frame.  The sample-averaged
rho00 = 2.5 <cos^2 theta> - 0.5 can differ between samples simply because the
phi pT / |y| spectra differ (acceptance and reconstruction sculpt the angle).
This script:

  1. computes rho00 in bins of phi pT for every sample;
  2. reweights each sample to the (phi pT, |phi y|) distribution of another
     sample (default: DPS1 and SPS_CS, mutually) and recomputes rho00;
  3. writes a CSV/JSON table and a two-panel figure.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import mplhep as hep
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

MC_FILES = {
    "JJP_DPS1": "mc_dps1.parquet",
    "JJP_DPS2_CS": "mc_dps2_cs.parquet",
    "JJP_DPS2_G": "mc_dps2_g.parquet",
    "JJP_SPS_CS": "mc_sps_cs.parquet",
    "JJP_SPS_G": "mc_sps_g.parquet",
}
LABELS = {
    "JJP_DPS1": "DPS1", "JJP_DPS2_CS": "DPS2 CS", "JJP_DPS2_G": "DPS2 G",
    "JJP_SPS_CS": "SPS CS", "JJP_SPS_G": "SPS G",
}
COLORS = {
    "JJP_DPS1": "#0072B2", "JJP_DPS2_CS": "#E69F00", "JJP_DPS2_G": "#009E73",
    "JJP_SPS_CS": "#D55E00", "JJP_SPS_G": "#CC79A7",
}
PT_EDGES = np.array([0.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 25.0, 200.0])
Y_EDGES = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5])


def weighted_moments(values, weights):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    wsum = weights.sum()
    mean = np.sum(weights * values) / wsum
    mean_sq = np.sum(weights * values ** 2) / wsum
    var = np.sum(weights * (values - mean) ** 2) / wsum
    n_eff = wsum ** 2 / np.sum(weights ** 2)
    d_mean_sq = np.sqrt(np.sum(weights ** 2 * (values ** 2 - mean_sq) ** 2)) / wsum
    return {
        "n": int(len(values)),
        "n_eff": float(n_eff),
        "mean": float(mean),
        "std": float(np.sqrt(var)),
        "mean_sq": float(mean_sq),
        "rho00": float(2.5 * mean_sq - 0.5),
        "rho00_err": float(2.5 * d_mean_sq),
        "mean_err": float(np.sqrt(var / n_eff)),
    }


def assign_weights(frame, ref_counts, sample_counts, x_edges, y_edges):
    """Per-event reweighting to a reference 2D distribution."""
    frac_ref = ref_counts / ref_counts.sum()
    frac_s = np.where(sample_counts > 0, sample_counts / sample_counts.sum(), 0.0)
    ratio = np.divide(frac_ref, frac_s, out=np.zeros_like(frac_ref), where=frac_s > 0)
    ix = np.clip(np.digitize(frame["sel_Phi_pt"], x_edges) - 1, 0, len(x_edges) - 2)
    iy = np.clip(np.digitize(frame["y_phi"].abs(), y_edges) - 1, 0, len(y_edges) - 2)
    return ratio[ix, iy]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angles-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--references", default="JJP_DPS1,JJP_SPS_CS,JJP_DPS2_CS")
    args = ap.parse_args()

    angles_dir = Path(args.angles_dir)
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    samples = {}
    counts_2d = {}
    for sample, fname in MC_FILES.items():
        path = angles_dir / fname
        if not path.exists():
            continue
        frame = pd.read_parquet(path)
        frame = frame[np.isfinite(frame["abs_cos_theta_phi"])].copy()
        samples[sample] = frame
        counts_2d[sample], _, _ = np.histogram2d(
            frame["sel_Phi_pt"], frame["y_phi"].abs(), bins=[PT_EDGES, Y_EDGES]
        )

    rows = []
    for sample, frame in samples.items():
        raw = weighted_moments(frame["abs_cos_theta_phi"], np.ones(len(frame)))
        row = {"sample": sample, "variant": "raw", **raw}
        rows.append(row)
        for ref_name in args.references.split(","):
            if ref_name not in samples:
                continue
            w = assign_weights(frame, counts_2d[ref_name], counts_2d[sample], PT_EDGES, Y_EDGES)
            good = w > 0
            m = weighted_moments(frame.loc[good, "abs_cos_theta_phi"], w[good])
            row = {"sample": sample, "variant": f"reweight_to_{ref_name}", **m}
            row["weight_sum"] = float(w.sum())
            rows.append(row)

    table = pd.DataFrame(rows)
    table.to_csv(outdir / "phi_polarization_reweighting.csv", index=False)
    with open(outdir / "phi_polarization_reweighting.json", "w") as fh:
        json.dump(rows, fh, indent=1)

    # Selected phi moment vs phi pT (raw)
    hep.style.use(hep.style.CMS)
    plt.rcParams.update({
        "font.size": 10,
        "axes.labelsize": 12,
        "axes.titlesize": 13,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 9,
    })
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(15.5, 6.5))
    pt_edges = np.array([0.0, 3.0, 5.0, 7.0, 10.0, 15.0, 25.0])
    centers = 0.5 * (pt_edges[:-1] + pt_edges[1:])
    for sample, frame in samples.items():
        vals, errs = [], []
        for lo, hi in zip(pt_edges[:-1], pt_edges[1:]):
            sub = frame[(frame["sel_Phi_pt"] >= lo) & (frame["sel_Phi_pt"] < hi)]
            if len(sub) < 50:
                vals.append(np.nan)
                errs.append(np.nan)
                continue
            m = weighted_moments(sub["abs_cos_theta_phi"], np.ones(len(sub)))
            vals.append(m["rho00"])
            errs.append(m["rho00_err"])
        ax.errorbar(centers, vals, yerr=errs, fmt="o-", ms=4, capsize=0,
                    color=COLORS[sample], lw=1.5, label=LABELS[sample])
    ax.axhline(1.0 / 3.0, color="gray", ls="--", lw=0.8)
    ax.set_xlabel(r"$\phi$ $p_T$ [GeV]")
    ax.set_ylabel(r"$\rho_{00}^{\mathrm{moment}}(\phi)$")
    ax.set_title(r"Selected $\phi$ moment vs $p_T$", loc="right", pad=12)
    ax.legend(frameon=False, ncol=2, fontsize=9)

    # Raw vs reweighted selected phi moment
    variants = ["raw"] + [f"reweight_to_{r}" for r in args.references.split(",")]
    x = np.arange(len(variants))
    width = 0.16
    for i, (sample, _) in enumerate(samples.items()):
        vals, errs = [], []
        for var in variants:
            sub = table[(table["sample"] == sample) & (table["variant"] == var)]
            if len(sub) == 0:
                vals.append(np.nan)
                errs.append(np.nan)
            else:
                vals.append(sub.iloc[0]["rho00"])
                errs.append(sub.iloc[0]["rho00_err"])
        ax2.errorbar(x + (i - 2) * width, vals, yerr=errs, fmt="o", ms=5, capsize=2,
                     color=COLORS[sample], label=LABELS[sample])
    ax2.axhline(1.0 / 3.0, color="gray", ls="--", lw=0.8)
    ax2.set_xticks(x)
    ax2.set_xticklabels(["raw"] + [f"to {LABELS[r]}" for r in args.references.split(",") if r in samples],
                        rotation=20, ha="right")
    ax2.set_ylabel(r"$\rho_{00}^{\mathrm{moment}}(\phi)$")
    ax2.set_title("Selected moment before and after\nkinematic reweighting", loc="right", pad=12)
    ax2.legend(frameon=False, ncol=2, fontsize=9)
    hep.cms.label("Work in Progress", loc=0, ax=ax, fontsize=12)
    fig.subplots_adjust(left=.08, right=.98, bottom=.27, top=.78, wspace=.30)
    fig.text(.5, .025, "Uncorrected selected-level moment; not a polarization measurement",
             ha="center", va="bottom", fontsize=9)
    for ext in ("png", "pdf"):
        fig.savefig(outdir / f"phi_polarization_reweighting.{ext}", bbox_inches="tight", dpi=200)
    plt.close(fig)
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()

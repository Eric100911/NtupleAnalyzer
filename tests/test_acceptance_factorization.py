#!/usr/bin/env python3
"""Bin-by-bin closure test of the acceptance factorization assumption.

Compares the direct 3-body fiducial acceptance in correlated 5D kinematic
bins against the factorized product of per-object acceptances:

    A_direct   = P(jpsi1_fid & jpsi2_fid & phi_fid | full_gen)   [per 5D bin]
    A_factorized = A_jpsi(jpsi1_pt,|y1|) * A_jpsi(jpsi2_pt,|y2|) * A_phi(phi_pt,|y|)

If factorization holds, A_factorized / A_direct ≈ 1 in every bin.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Sequence

import matplotlib
matplotlib.use("Agg")  # non-interactive backend — must be before pyplot import
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from efficiency_workflow.efficiency import (
    EfficiencyBinning,
    _merged_gen_events,
    jeffreys_efficiency_uncertainty,
)
from efficiency_workflow.io import ensure_dir, write_json, write_parquet


DEFAULT_SAMPLES = ("JJP_DPS1", "JJP_DPS2_CS", "JJP_DPS2_G", "JJP_SPS_CS", "JJP_SPS_G")


# ---------------------------------------------------------------------------
# Factorized map loading and vectorized lookup
# ---------------------------------------------------------------------------

def _load_factorized_acceptance_map(maps_dir: Path, factor_name: str) -> pd.DataFrame:
    """Load a factorized acceptance parquet and return the fine-level rows."""
    path = maps_dir / f"{factor_name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing factorized map: {path}")
    df = pd.read_parquet(path)
    if factor_name not in df["factor_name"].values:
        raise ValueError(f"Map {path} does not contain factor {factor_name!r}")
    return df.loc[df["factor_name"] == factor_name].copy()


def _build_acceptance_lookup(
    df: pd.DataFrame,
    *,
    n_min_fine: int = 30,
    n_min_coarse: int = 50,
    x_edges: tuple[float, ...] | None = None,
    y_edges: tuple[float, ...] | None = None,
) -> dict:
    """Build a lookup dict from map rows for vectorized per-event application.

    Returns a dict with:
      - fine_eff:  2D array [n_x_bins, n_y_bins] of efficiencies
      - coarse_eff: 1D array [n_x_bins] of efficiencies
      - inclusive_eff: scalar
      - x_edges, y_edges: bin edges
      - n_min_fine, n_min_coarse: thresholds
    """
    fine = df.loc[df["fallback_level"] == "fine"]
    coarse = df.loc[df["fallback_level"] == "coarse"]
    inclusive = df.loc[df["fallback_level"] == "inclusive"]

    if x_edges is None:
        x_edges = tuple(sorted(fine["x_min"].unique()))
    if y_edges is None:
        y_vals = fine["y_min"].unique()
        y_edges = tuple(sorted(y_vals[~np.isnan(y_vals)]))

    n_x = len(x_edges) - 1
    n_y = len(y_edges) - 1
    fine_eff = np.full((n_x, n_y), np.nan, dtype=np.float64)
    fine_total = np.zeros((n_x, n_y), dtype=np.int64)

    for _, row in fine.iterrows():
        ix = int(row["x_bin"])
        iy = int(row["y_bin"])
        if 0 <= ix < n_x and 0 <= iy < n_y:
            fine_eff[ix, iy] = float(row["efficiency"])
            fine_total[ix, iy] = int(row["total"])

    coarse_eff = np.full(n_x, np.nan, dtype=np.float64)
    coarse_total = np.zeros(n_x, dtype=np.int64)
    for _, row in coarse.iterrows():
        ix = int(row["x_bin"])
        if 0 <= ix < n_x:
            coarse_eff[ix] = float(row["efficiency"])
            coarse_total[ix] = int(row["total"])

    inclusive_eff = float(inclusive["efficiency"].iloc[0]) if len(inclusive) > 0 else np.nan

    return {
        "fine_eff": fine_eff,
        "fine_total": fine_total,
        "coarse_eff": coarse_eff,
        "coarse_total": coarse_total,
        "inclusive_eff": inclusive_eff,
        "x_edges": np.asarray(x_edges, dtype=float),
        "y_edges": np.asarray(y_edges, dtype=float),
        "n_min_fine": n_min_fine,
        "n_min_coarse": n_min_coarse,
    }


def _lookup_acceptance(lookup: dict, pt: np.ndarray, abs_y: np.ndarray) -> np.ndarray:
    """Vectorized per-event acceptance lookup with fallback hierarchy.

    For each event, tries fine (pt×|y|) → coarse (pt-only) → inclusive.
    Returns an array of acceptance efficiencies, one per event.
    """
    x_edges = lookup["x_edges"]
    y_edges = lookup["y_edges"]
    n_events = len(pt)

    x_idx = np.clip(np.searchsorted(x_edges, pt, side="right") - 1, 0, len(x_edges) - 2)
    y_idx = np.clip(np.searchsorted(y_edges, abs_y, side="right") - 1, 0, len(y_edges) - 2)

    result = np.full(n_events, np.nan, dtype=np.float64)
    resolved = np.zeros(n_events, dtype=bool)

    # --- fine level ---
    mask_fine = ~resolved
    for ix in range(lookup["fine_eff"].shape[0]):
        for iy in range(lookup["fine_eff"].shape[1]):
            if lookup["fine_total"][ix, iy] < lookup["n_min_fine"]:
                continue
            in_bin = mask_fine & (x_idx == ix) & (y_idx == iy)
            if np.any(in_bin):
                eff = lookup["fine_eff"][ix, iy]
                if np.isfinite(eff) and eff > 0:
                    result[in_bin] = eff
                    resolved[in_bin] = True
                    mask_fine = ~resolved
                    if not np.any(mask_fine):
                        return result

    # --- coarse level ---
    mask_coarse = ~resolved
    for ix in range(len(lookup["coarse_eff"])):
        if lookup["coarse_total"][ix] < lookup["n_min_coarse"]:
            continue
        in_bin = mask_coarse & (x_idx == ix)
        if np.any(in_bin):
            eff = lookup["coarse_eff"][ix]
            if np.isfinite(eff) and eff > 0:
                result[in_bin] = eff
                resolved[in_bin] = True
                mask_coarse = ~resolved
                if not np.any(mask_coarse):
                    return result

    # --- inclusive ---
    mask_inc = ~resolved
    if np.any(mask_inc):
        eff = lookup["inclusive_eff"]
        if np.isfinite(eff) and eff > 0:
            result[mask_inc] = eff
            resolved[mask_inc] = True

    return result


# ---------------------------------------------------------------------------
# 5D binning
# ---------------------------------------------------------------------------

def _assign_5d_bins(
    frame: pd.DataFrame,
    binning: EfficiencyBinning,
) -> pd.DataFrame:
    """Assign a 5D bin index to each event.

    Bin axes: jpsi_lead_pt (6) × jpsi_sublead_pt (6) × phi_pt (4)
              × jpsi_lead_abs_y (4) × jpsi_sublead_abs_y (4)
    = 2304 bins.
    """
    jpsi_edges = np.asarray(binning.jpsi_pt_edges, dtype=float)
    phi_edges = np.asarray(binning.phi_pt_edges, dtype=float)
    abs_y_edges = np.asarray(binning.object_abs_y_edges, dtype=float)

    idx_lead_pt = np.clip(np.searchsorted(jpsi_edges, frame["jpsi_lead_pt"].to_numpy(dtype=float), side="right") - 1, 0, len(jpsi_edges) - 2)
    idx_sublead_pt = np.clip(np.searchsorted(jpsi_edges, frame["jpsi_sublead_pt"].to_numpy(dtype=float), side="right") - 1, 0, len(jpsi_edges) - 2)
    idx_phi_pt = np.clip(np.searchsorted(phi_edges, frame["phi_pt"].to_numpy(dtype=float), side="right") - 1, 0, len(phi_edges) - 2)
    idx_lead_abs_y = np.clip(np.searchsorted(abs_y_edges, frame["jpsi_lead_abs_y"].to_numpy(dtype=float), side="right") - 1, 0, len(abs_y_edges) - 2)
    idx_sublead_abs_y = np.clip(np.searchsorted(abs_y_edges, frame["jpsi_sublead_abs_y"].to_numpy(dtype=float), side="right") - 1, 0, len(abs_y_edges) - 2)

    n_jpsi = len(jpsi_edges) - 1
    n_phi = len(phi_edges) - 1
    n_y = len(abs_y_edges) - 1

    stride_sublead_y = 1
    stride_lead_y = n_y
    stride_phi = n_y * n_y
    stride_sublead_pt = n_phi * stride_phi
    stride_lead_pt = n_jpsi * stride_sublead_pt

    bin_idx = (
        idx_lead_pt * stride_lead_pt
        + idx_sublead_pt * stride_sublead_pt
        + idx_phi_pt * stride_phi
        + idx_lead_abs_y * stride_lead_y
        + idx_sublead_abs_y * stride_sublead_y
    )

    result = frame.copy()
    result["_bin_5d"] = bin_idx.astype(np.int32)
    result["_lead_pt_bin"] = idx_lead_pt.astype(np.int8)
    result["_sublead_pt_bin"] = idx_sublead_pt.astype(np.int8)
    result["_phi_pt_bin"] = idx_phi_pt.astype(np.int8)
    result["_lead_abs_y_bin"] = idx_lead_abs_y.astype(np.int8)
    result["_sublead_abs_y_bin"] = idx_sublead_abs_y.astype(np.int8)
    return result


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def run_acceptance_factorization_closure(
    input_dir: str | Path,
    *,
    samples: Sequence[str] = DEFAULT_SAMPLES,
    min_bin_events: int = 10,
    n_min_fine: int = 30,
    n_min_coarse: int = 50,
    output_dir: str | Path | None = None,
) -> pd.DataFrame:
    input_path = Path(input_dir)
    output_path = ensure_dir(Path(output_dir) if output_dir is not None else input_path / "acceptance_factorization_closure")
    binning = EfficiencyBinning()

    all_rows: list[dict] = []

    for sample in samples:
        print(f"\n{'='*60}")
        print(f"Processing sample: {sample}")
        print(f"{'='*60}")

        # --- load data ---
        sample_dir = input_path / sample
        gen_path = sample_dir / "gen_systems.parquet"
        event_path = sample_dir / "event_step_flags.parquet"
        maps_dir = sample_dir / "maps"

        if not gen_path.exists() or not event_path.exists():
            print(f"  SKIP: missing parquet inputs in {sample_dir}")
            continue

        gen_df = pd.read_parquet(gen_path)
        event_df = pd.read_parquet(event_path)
        merged = _merged_gen_events(gen_df, event_df)
        if merged.empty:
            print(f"  SKIP: empty merged dataframe")
            continue
        print(f"  Loaded {len(merged):,} merged events")

        # Full gen acceptance (already the denominator)
        n_gen = len(merged)
        all_fiducial = merged["jpsi_lead_fiducial"].to_numpy(bool) & merged["jpsi_sublead_fiducial"].to_numpy(bool) & merged["phi_fiducial"].to_numpy(bool)
        print(f"  Triple fiducial events: {all_fiducial.sum():,} ({all_fiducial.mean()*100:.2f}%)")

        # --- load factorized acceptance maps ---
        if not maps_dir.exists():
            print(f"  SKIP: missing maps directory {maps_dir}")
            continue

        lookup_jpsi = _build_acceptance_lookup(
            _load_factorized_acceptance_map(maps_dir, "acceptance_jpsi"),
            n_min_fine=n_min_fine,
            n_min_coarse=n_min_coarse,
            x_edges=binning.jpsi_pt_edges,
            y_edges=binning.object_abs_y_edges,
        )
        lookup_phi = _build_acceptance_lookup(
            _load_factorized_acceptance_map(maps_dir, "acceptance_phi"),
            n_min_fine=n_min_fine,
            n_min_coarse=n_min_coarse,
            x_edges=binning.phi_pt_edges,
            y_edges=binning.object_abs_y_edges,
        )

        # --- per-event factorized acceptance ---
        lead_pt = merged["jpsi_lead_pt"].to_numpy(dtype=float)
        sublead_pt = merged["jpsi_sublead_pt"].to_numpy(dtype=float)
        phi_pt = merged["phi_pt"].to_numpy(dtype=float)
        lead_abs_y = merged["jpsi_lead_abs_y"].to_numpy(dtype=float)
        sublead_abs_y = merged["jpsi_sublead_abs_y"].to_numpy(dtype=float)
        phi_abs_y = merged["phi_abs_y"].to_numpy(dtype=float)

        acc_jpsi_lead = _lookup_acceptance(lookup_jpsi, lead_pt, lead_abs_y)
        acc_jpsi_sublead = _lookup_acceptance(lookup_jpsi, sublead_pt, sublead_abs_y)
        acc_phi = _lookup_acceptance(lookup_phi, phi_pt, phi_abs_y)

        n_failed = np.sum(~np.isfinite(acc_jpsi_lead) | ~np.isfinite(acc_jpsi_sublead) | ~np.isfinite(acc_phi))
        if n_failed > 0:
            print(f"  WARNING: {n_failed} events with missing factorized acceptance lookup")
        print(f"  Factorized acceptance per event: mean={np.nanmean(acc_jpsi_lead * acc_jpsi_sublead * acc_phi):.4f}")

        factorized_product = acc_jpsi_lead * acc_jpsi_sublead * acc_phi

        # --- 5D binning ---
        merged = _assign_5d_bins(merged, binning)
        merged["_all_fiducial"] = all_fiducial.astype(np.int8)
        merged["_factorized_product"] = factorized_product.astype(np.float64)

        # --- per-bin aggregation ---
        grouped = merged.groupby("_bin_5d")

        n_total = grouped.size().to_numpy(dtype=int)
        n_fiducial = grouped["_all_fiducial"].sum().to_numpy(dtype=int)
        factorized_mean = grouped["_factorized_product"].mean().to_numpy(dtype=float)
        factorized_std = grouped["_factorized_product"].std(ddof=0).to_numpy(dtype=float)

        # Extract bin coordinates from first row in each group
        bin_coords = grouped[["_lead_pt_bin", "_sublead_pt_bin", "_phi_pt_bin",
                               "_lead_abs_y_bin", "_sublead_abs_y_bin"]].first()
        bin_indices = bin_coords.index.to_numpy(dtype=int)

        # Build per-bin rows
        jpsi_edges = np.asarray(binning.jpsi_pt_edges, dtype=float)
        phi_edges = np.asarray(binning.phi_pt_edges, dtype=float)
        abs_y_edges = np.asarray(binning.object_abs_y_edges, dtype=float)

        for i in range(len(n_total)):
            nt = int(n_total[i])
            if nt < min_bin_events:
                continue
            nf = int(n_fiducial[i])
            direct_eff, direct_err = jeffreys_efficiency_uncertainty(nt, nf)
            fm = float(factorized_mean[i]) if np.isfinite(factorized_mean[i]) else np.nan
            fs = float(factorized_std[i]) if np.isfinite(factorized_std[i]) else 0.0
            ratio = float(fm / direct_eff) if direct_eff > 0 and np.isfinite(fm) else np.nan

            denom = math.sqrt(direct_err**2 + (fs**2 / nt)) if nt > 0 and fs > 0 else direct_err
            pull = float((fm - direct_eff) / denom) if denom > 0 else np.nan

            coords = bin_coords.iloc[i]
            lead_pt_bin = int(coords["_lead_pt_bin"])
            sublead_pt_bin = int(coords["_sublead_pt_bin"])
            phi_pt_bin = int(coords["_phi_pt_bin"])
            lead_abs_y_bin = int(coords["_lead_abs_y_bin"])
            sublead_abs_y_bin = int(coords["_sublead_abs_y_bin"])

            all_rows.append({
                "sample": sample,
                "bin_5d": int(bin_indices[i]),
                "lead_pt_bin": lead_pt_bin,
                "sublead_pt_bin": sublead_pt_bin,
                "phi_pt_bin": phi_pt_bin,
                "lead_abs_y_bin": lead_abs_y_bin,
                "sublead_abs_y_bin": sublead_abs_y_bin,
                "lead_pt_min": float(jpsi_edges[lead_pt_bin]),
                "lead_pt_max": float(jpsi_edges[lead_pt_bin + 1]),
                "sublead_pt_min": float(jpsi_edges[sublead_pt_bin]),
                "sublead_pt_max": float(jpsi_edges[sublead_pt_bin + 1]),
                "phi_pt_min": float(phi_edges[phi_pt_bin]),
                "phi_pt_max": float(phi_edges[phi_pt_bin + 1]),
                "lead_abs_y_min": float(abs_y_edges[lead_abs_y_bin]),
                "lead_abs_y_max": float(abs_y_edges[lead_abs_y_bin + 1]),
                "sublead_abs_y_min": float(abs_y_edges[sublead_abs_y_bin]),
                "sublead_abs_y_max": float(abs_y_edges[sublead_abs_y_bin + 1]),
                "n_total": nt,
                "n_fiducial": nf,
                "direct_acceptance": float(direct_eff),
                "direct_err": float(direct_err),
                "factorized_acceptance": fm,
                "factorized_std": fs,
                "ratio": ratio,
                "pull": pull,
            })

        print(f"  Bins with >= {min_bin_events} events: {sum(1 for i in range(len(n_total)) if n_total[i] >= min_bin_events)}")

    if not all_rows:
        print("\nNo results produced — check input data.")
        return pd.DataFrame()

    result_df = pd.DataFrame(all_rows)
    result_df.sort_values(["sample", "ratio"], inplace=True, ignore_index=True)

    # --- write outputs ---
    parquet_path = output_path / "acceptance_factorization_results.parquet"
    csv_path = output_path / "acceptance_factorization_results.csv"
    manifest_path = output_path / "acceptance_factorization_summary.json"

    write_parquet(result_df, parquet_path)
    result_df.to_csv(csv_path, index=False)

    # Summary statistics
    ratios = result_df["ratio"].to_numpy(dtype=float)
    finite_ratios = ratios[np.isfinite(ratios)]
    summary = {
        "stage": "acceptance_factorization_closure",
        "input_dir": str(input_path.resolve()),
        "output_dir": str(output_path.resolve()),
        "samples": list(samples),
        "min_bin_events": min_bin_events,
        "n_min_fine": n_min_fine,
        "n_min_coarse": n_min_coarse,
        "n_total_bins": int(len(result_df)),
        "n_finite_ratios": int(len(finite_ratios)),
        "ratio_mean": float(np.mean(finite_ratios)) if len(finite_ratios) > 0 else None,
        "ratio_std": float(np.std(finite_ratios)) if len(finite_ratios) > 0 else None,
        "ratio_median": float(np.median(finite_ratios)) if len(finite_ratios) > 0 else None,
        "ratio_iqr": float(np.subtract(*np.percentile(finite_ratios, [75, 25]))) if len(finite_ratios) > 0 else None,
        "frac_within_10pct": float(np.mean(np.abs(finite_ratios - 1.0) < 0.10)) if len(finite_ratios) > 0 else None,
        "frac_within_20pct": float(np.mean(np.abs(finite_ratios - 1.0) < 0.20)) if len(finite_ratios) > 0 else None,
        "frac_within_50pct": float(np.mean(np.abs(finite_ratios - 1.0) < 0.50)) if len(finite_ratios) > 0 else None,
        "per_sample": {},
    }

    for sample in samples:
        sample_ratios = result_df.loc[result_df["sample"] == sample, "ratio"].to_numpy(dtype=float)
        sample_ratios = sample_ratios[np.isfinite(sample_ratios)]
        if len(sample_ratios) > 0:
            summary["per_sample"][sample] = {
                "n_bins": int(len(sample_ratios)),
                "ratio_mean": float(np.mean(sample_ratios)),
                "ratio_std": float(np.std(sample_ratios)),
                "ratio_median": float(np.median(sample_ratios)),
                "frac_within_10pct": float(np.mean(np.abs(sample_ratios - 1.0) < 0.10)),
                "frac_within_20pct": float(np.mean(np.abs(sample_ratios - 1.0) < 0.20)),
            }

    write_json(summary, manifest_path)

    # --- diagnostic plots ---
    _make_plots(result_df, output_path, min_bin_events)

    # --- print summary ---
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Total bins (all samples): {len(result_df)}")
    print(f"Finite ratios: {len(finite_ratios)}")
    if len(finite_ratios) > 0:
        print(f"Ratio mean  : {summary['ratio_mean']:.4f}")
        print(f"Ratio std   : {summary['ratio_std']:.4f}")
        print(f"Ratio median: {summary['ratio_median']:.4f}")
        print(f"Within 10% of unity: {summary['frac_within_10pct']*100:.1f}%")
        print(f"Within 20% of unity: {summary['frac_within_20pct']*100:.1f}%")
        print(f"Within 50% of unity: {summary['frac_within_50pct']*100:.1f}%")
    print(f"\nPer-sample:")
    for sample, stats in summary["per_sample"].items():
        print(f"  {sample}: mean={stats['ratio_mean']:.4f}, std={stats['ratio_std']:.4f}, "
              f"within10%={stats['frac_within_10pct']*100:.1f}%")
    print(f"\nWrote: {parquet_path}")
    print(f"Wrote: {csv_path}")
    print(f"Wrote: {manifest_path}")

    return result_df


# ---------------------------------------------------------------------------
# Diagnostic plots
# ---------------------------------------------------------------------------

def _make_plots(result_df: pd.DataFrame, output_dir: Path, min_bin_events: int) -> None:
    """Produce diagnostic plots for the acceptance factorization closure."""
    if result_df.empty:
        return

    ratios = result_df["ratio"].to_numpy(dtype=float)
    finite = np.isfinite(ratios)
    if not np.any(finite):
        print("  No finite ratios — skipping plots.")
        return

    # ---- Plot 1: Ratio distribution ----
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    bins = np.linspace(0.0, 3.0, 61)
    ax.hist(ratios[finite], bins=bins, color="steelblue", edgecolor="white", alpha=0.85)
    ax.axvline(1.0, color="red", linestyle="--", linewidth=1.5, label="Unity")
    ax.axvline(np.median(ratios[finite]), color="darkorange", linestyle=":", linewidth=1.5,
               label=f"Median = {np.median(ratios[finite]):.3f}")
    ax.set_xlabel("A_factorized / A_direct")
    ax.set_ylabel("Number of 5D bins")
    ax.set_title(f"Acceptance factorization closure\n(min {min_bin_events} events/bin, {len(ratios[finite])} bins)")
    ax.legend(fontsize=9)
    ax.set_xlim(0, 3)

    ax = axes[1]
    log_ratios = np.log10(ratios[finite])
    ax.hist(log_ratios, bins=50, color="steelblue", edgecolor="white", alpha=0.85)
    ax.axvline(0.0, color="red", linestyle="--", linewidth=1.5, label="Unity (log=0)")
    ax.set_xlabel("log10(A_factorized / A_direct)")
    ax.set_ylabel("Number of 5D bins")
    ax.set_title("Log-ratio distribution")
    ax.legend(fontsize=9)

    fig.tight_layout()
    fig.savefig(output_dir / "ratio_distribution.png", dpi=150)
    plt.close(fig)
    print(f"  Wrote: {output_dir / 'ratio_distribution.png'}")

    # ---- Plot 2: Factorized vs Direct scatter ----
    fig, ax = plt.subplots(figsize=(8, 7))
    direct = result_df["direct_acceptance"].to_numpy(dtype=float)
    factorized = result_df["factorized_acceptance"].to_numpy(dtype=float)
    ok = np.isfinite(direct) & np.isfinite(factorized) & (direct > 0)

    max_val = max(np.max(direct[ok]), np.max(factorized[ok]))
    ax.plot([0, max_val * 1.05], [0, max_val * 1.05], "k--", linewidth=1, alpha=0.5, label="Unity line")
    sc = ax.scatter(direct[ok], factorized[ok], c=result_df.loc[ok, "n_total"].to_numpy(),
                    cmap="viridis", alpha=0.6, s=15, edgecolors="none")
    cbar = plt.colorbar(sc, ax=ax)
    cbar.set_label("Events per bin")
    ax.set_xlabel("Direct acceptance A_direct")
    ax.set_ylabel("Factorized acceptance A_factorized")
    ax.set_title("Factorized vs Direct Acceptance per 5D Bin")
    ax.legend(fontsize=9)
    ax.set_xlim(0, max_val * 1.05)
    ax.set_ylim(0, max_val * 1.05)
    fig.tight_layout()
    fig.savefig(output_dir / "factorized_vs_direct.png", dpi=150)
    plt.close(fig)
    print(f"  Wrote: {output_dir / 'factorized_vs_direct.png'}")

    # ---- Plot 3: Ratio vs kinematics (profiles) ----
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    axes = axes.flatten()

    bin_vars = [
        ("lead_pt_bin", "J/ψ lead pT bin", [f"{e:.0f}" for e in [6, 10, 15, 20, 30, 50]]),
        ("sublead_pt_bin", "J/ψ sublead pT bin", [f"{e:.0f}" for e in [6, 10, 15, 20, 30, 50]]),
        ("phi_pt_bin", "φ pT bin", [f"{e:.0f}" for e in [4, 6, 10, 20]]),
        ("lead_abs_y_bin", "J/ψ lead |y| bin", [f"{e:.1f}" for e in [0.0, 0.6, 1.2, 1.8]]),
        ("sublead_abs_y_bin", "J/ψ sublead |y| bin", [f"{e:.1f}" for e in [0.0, 0.6, 1.2, 1.8]]),
    ]

    for i, (col, title, labels) in enumerate(bin_vars):
        ax = axes[i]
        for sample in result_df["sample"].unique():
            sub = result_df[(result_df["sample"] == sample) & finite]
            if sub.empty:
                continue
            grouped = sub.groupby(col)["ratio"]
            mean_ratio = grouped.mean()
            std_ratio = grouped.std()
            x_vals = np.arange(len(mean_ratio))
            ax.errorbar(x_vals, mean_ratio.to_numpy(), yerr=std_ratio.to_numpy(),
                        marker="o", capsize=3, label=sample, alpha=0.8)
        ax.axhline(1.0, color="red", linestyle="--", linewidth=1)
        ax.set_xlabel(title)
        ax.set_ylabel("A_factorized / A_direct")
        ax.set_title(f"Ratio vs {title}")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, fontsize=8)
        if i == 0:
            ax.legend(fontsize=7, loc="best")

    # Hide unused 6th subplot
    axes[5].set_visible(False)

    fig.suptitle(f"Acceptance Factorization Closure — Ratio vs Kinematics", fontsize=13, y=1.01)
    fig.tight_layout()
    fig.savefig(output_dir / "ratio_vs_kinematics.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Wrote: {output_dir / 'ratio_vs_kinematics.png'}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bin-by-bin closure test of acceptance factorization A(J/psi1,J/psi2,phi) vs A(J/psi1)×A(J/psi2)×A(phi)"
    )
    parser.add_argument("--input-dir", required=True,
                        help="Merged efficiency directory containing sample subdirectories")
    parser.add_argument("--samples", nargs="+", default=list(DEFAULT_SAMPLES),
                        help="Samples to include")
    parser.add_argument("--output-dir", default=None,
                        help="Output directory (default: <input-dir>/acceptance_factorization_closure)")
    parser.add_argument("--min-bin-events", type=int, default=10,
                        help="Minimum events per 5D bin (default: 10)")
    parser.add_argument("--n-min-fine", type=int, default=30,
                        help="Minimum MC total for fine factorized bins (default: 30)")
    parser.add_argument("--n-min-coarse", type=int, default=50,
                        help="Minimum MC total for coarse factorized bins (default: 50)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir) if args.output_dir else Path(args.input_dir) / "acceptance_factorization_closure"

    print(f"=== Acceptance Factorization Closure Test ===", flush=True)
    print(f"Input dir      : {args.input_dir}", flush=True)
    print(f"Samples        : {', '.join(args.samples)}", flush=True)
    print(f"Min bin events : {args.min_bin_events}", flush=True)
    print(f"n_min_fine     : {args.n_min_fine}", flush=True)
    print(f"n_min_coarse   : {args.n_min_coarse}", flush=True)
    print(f"Output dir     : {output_dir}", flush=True)

    result_df = run_acceptance_factorization_closure(
        args.input_dir,
        samples=args.samples,
        min_bin_events=args.min_bin_events,
        n_min_fine=args.n_min_fine,
        n_min_coarse=args.n_min_coarse,
        output_dir=output_dir,
    )

    if result_df.empty:
        print("\nNo results produced.", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

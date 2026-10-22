#!/usr/bin/env python3
"""Draw validation figures from saved, versioned analysis tables."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
import pandas as pd

SAMPLES = ("JJP_DPS1", "JJP_DPS2_CS", "JJP_DPS2_G", "JJP_SPS_CS", "JJP_SPS_G", "JJP_TPS")
OLD_STEMS = ("jjp_mc_dps_1_selected", "jjp_mc_dps_2_cs_selected",
             "jjp_mc_dps_2_g_selected", "jjp_mc_sps_cs_selected", "jjp_mc_sps_g_selected")


def finish(fig, ax, output: Path, *, data: bool = False) -> None:
    hep.cms.label("Work In Progress", loc=0, ax=ax, data=data, rlabel="")
    fig.subplots_adjust(left=.13, right=.97, top=.83, bottom=.16)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_closure(input_dir: Path, output: Path, samples: list[str]) -> dict:
    rows = []
    for sample in samples:
        for method in ("factorized", "hybrid"):
            path = input_dir / sample / method / "closure_results.csv"
            df = pd.read_csv(path)
            if len(df) != 1 or df.iloc[0]["closure_type"] != "file_disjoint":
                raise ValueError(f"Expected one file-disjoint closure row: {path}")
            rows.append((sample, method, float(df.iloc[0]["ratio"])))
    fig, ax = plt.subplots(figsize=(9, 5.4))
    x = np.arange(len(samples))
    for shift, method, color in ((-.15, "factorized", "#0072B2"), (.15, "hybrid", "#D55E00")):
        vals = [next(v for s, m, v in rows if s == sample and m == method) for sample in samples]
        ax.plot(x + shift, vals, "o", color=color, label=method, markersize=8)
    ax.axhline(1, color="gray", linewidth=1)
    ax.set_xticks(x, [s.removeprefix("JJP_") for s in samples])
    ax.set_ylabel("Corrected / GEN (file-disjoint holdout)")
    ax.legend(loc="upper right")
    finish(fig, ax, output)
    return {"population": "efficiency workflow GEN; listed file-disjoint holdout samples", "values": rows}


def plot_factorization(input_dir: Path, output: Path, samples: list[str]) -> dict:
    fig, ax = plt.subplots(figsize=(9, 5.4))
    stages = ("fiducial", "reco", "id", "quality")
    counts = {}
    for sample in samples:
        df = pd.read_csv(input_dir / sample / "scand_factorization_stage_bins.csv")
        counts[sample] = len(df)
        for j, stage in enumerate(stages):
            sub = df.loc[(df.stage == stage) & (df.n_product_ok > 0)]
            vals = sub.direct_over_product.to_numpy(float)
            vals = vals[np.isfinite(vals)]
            if len(vals):
                ax.scatter(np.full(len(vals), j), vals, alpha=.27, s=14,
                           label=sample.removeprefix("JJP_") if j == 0 else None)
    ax.axhline(1, color="gray", linewidth=1)
    ax.set_xticks(range(len(stages)), stages)
    ax.set_ylabel("Direct / product, per populated bin")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    finish(fig, ax, output)
    return {"population": "efficiency workflow GEN/event flags", "bin_rows": counts}


def plot_phi_origin(inventory: Path, output: Path) -> dict:
    sidecar = pd.read_parquet(inventory / "full_gen_system_origin_sidecar.parquet",
                              columns=["sample", "entry", "full_system_match", "origin_category_conservative"])
    sidecar = sidecar.loc[sidecar.full_system_match]
    frames = []
    for stem in OLD_STEMS:
        df = pd.read_parquet(inventory / f"{stem}_full_selected.parquet",
                             columns=["sample", "entry", "phi_ctau_cm"])
        frames.append(df.merge(sidecar, on=["sample", "entry"], how="inner", validate="one_to_one"))
    data = pd.concat(frames, ignore_index=True)
    categories = ("beauty_ancestor", "charm_ancestor_beauty_upstream_unresolved", "ambiguous_ancestry")
    counts = {key: int((data.origin_category_conservative == key).sum()) for key in categories}
    fig, ax = plt.subplots(figsize=(9, 5.4))
    edges = np.array([-np.inf, -.1, -.03, -.01, 0, .01, .03, .1, np.inf])
    for category, color in zip(categories, ("#D55E00", "#0072B2", "#666666")):
        vals = data.loc[data.origin_category_conservative == category, "phi_ctau_cm"].to_numpy(float)
        vals = vals[np.isfinite(vals)]
        hist = np.histogram(vals, bins=edges)[0]
        if hist.sum():
            ax.step(np.arange(len(hist)), hist / hist.sum(), where="mid", label=f"{category} (n={len(vals)})", color=color)
    ax.set_xticks(range(8), ["<−1", "−1:−.3", "−.3:−.1", "−.1:0", "0:.1", ".1:.3", ".3:1", ">1"], rotation=35)
    ax.set_xlabel(r"Beamspot-referenced $\phi$ ctau category [mm]")
    ax.set_ylabel("Within-category-source fraction")
    ax.legend(loc="upper right", fontsize=8)
    finish(fig, ax, output)
    return {"population": "five historical selected MC, full GEN system matched", "counts": counts, "total": len(data)}


def plot_phi_ctau(central: Path, variation: Path, output: Path) -> dict:
    c = json.loads(central.read_text())
    v = json.loads(variation.read_text())
    ctail = next(row["component_yields"]["yield_sss"] for row in c["category_fits"] if row["label"] == "over_0.1")
    vtail = next(row["yield_sss"] for row in v if row["label"] == "over_0.1")
    fig, ax = plt.subplots(figsize=(8, 5.2))
    ax.errorbar([0, 1], [ctail["value"], vtail["value"]],
                yerr=[ctail["error"], vtail["error"]], fmt="o", color="black", capsize=4)
    ax.set_xticks([0, 1], [r"$\sigma_\phi\leq0.005$ GeV", r"$\sigma_\phi\leq0.010$ GeV"])
    ax.set_xlim(-.5, 1.5)
    ax.set_ylabel(r"Fitted signal yield, $ctau_\phi\geq0.1$ cm")
    finish(fig, ax, output, data=True)
    return {"population": "selected data, 48829 events", "central": ctail, "variation": vtail,
            "intrinsic_phi_width": "fixed"}


def plot_phi_gen(proxy: Path, output: Path) -> dict:
    df = pd.read_parquet(proxy, columns=["sample", "phi_abs_y", "population"])
    fig, ax = plt.subplots(figsize=(9, 5.4))
    counts = {}
    for sample, part in df.groupby("sample"):
        vals = part.phi_abs_y.to_numpy(float)
        vals = vals[np.isfinite(vals)]
        counts[sample] = len(vals)
        ax.hist(vals, bins=np.linspace(0, 2.5, 26), histtype="step", density=True,
                label=f"{sample} (n={len(vals)})")
    ax.set_xlabel(r"$|y(\phi)|$")
    ax.set_ylabel("Unit-area density")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    finish(fig, ax, output)
    return {"population": sorted(df.population.unique().tolist()), "counts": counts}


def main() -> None:
    hep.style.use(hep.style.CMS)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("closure", "factorization", "phi-origin", "phi-ctau", "phi-gen"))
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--central", type=Path)
    parser.add_argument("--variation", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--samples", nargs="+", default=["JJP_DPS1", "JJP_SPS_CS"])
    args = parser.parse_args()
    if args.kind == "closure":
        summary = plot_closure(args.input_dir, args.output, args.samples)
    elif args.kind == "factorization":
        summary = plot_factorization(args.input_dir, args.output, args.samples)
    elif args.kind == "phi-origin":
        summary = plot_phi_origin(args.input_dir, args.output)
    elif args.kind == "phi-ctau":
        summary = plot_phi_ctau(args.central, args.variation, args.output)
    else:
        summary = plot_phi_gen(args.input_dir, args.output)
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=str) + "\n")


if __name__ == "__main__":
    main()

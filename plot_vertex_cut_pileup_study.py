#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Study how vertex cuts suppress pileup using sWeighted PV dz/dxy difference plots."""

from __future__ import annotations

import argparse
import array
import math
import os
import sys
from collections import OrderedDict
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
import ROOT
import uproot

import fit_splot as fit_core
from ntuple_pipeline_common import (
    OUTPUT_BASE,
    build_root_string_vector,
    declare_rdf_helpers,
    default_merged_output,
    default_plot_dir,
    ensure_dir,
    ensure_parent_dir,
    get_tree_branches,
    normalize_channel,
    normalize_dataset,
    normalize_sample,
)


INPUT_TREE = "selected"

# =============================================================================
# Editable study configuration
# =============================================================================

PRI_VTXPROB_MIN = 0.05
N_BINS = 20
DELTA_DZ_RANGE = (-0.1, 0.1)
DELTA_DXY_RANGE = (-0.05, 0.05)
WEIGHT_BRANCH = "signal_sw"
NORMALIZE_HISTS = True
RATIO_Y_RANGE = (0.5, 1.5)


@dataclass(frozen=True)
class CutScenario:
    key: str
    label: str
    expression: str
    required_branches: tuple[str, ...]


@dataclass(frozen=True)
class PairSpec:
    key: str
    label: str
    left: str
    right: str


def parse_args():
    parser = argparse.ArgumentParser(description="Study vertex-cut effects on sWeighted PV dz/dxy difference distributions")
    parser.add_argument("--channel", required=True, choices=["JJP", "JUP", "jjp", "jup"])
    parser.add_argument("--dataset", default="data", choices=["data", "mc"])
    parser.add_argument("--sample", default=None, help="MC sample tag")
    parser.add_argument("-i", "--input", default=None, help="Input merged selected ROOT file")
    parser.add_argument("-o", "--output-dir", default=None, help="Directory for final comparison plots")
    parser.add_argument("--work-dir", default=None, help="Directory for filtered and weighted intermediate ROOT files")
    parser.add_argument("-j", "--jobs", type=int, default=8, help="RDataFrame/RooFit thread count")
    parser.add_argument("-n", "--max-events", type=int, default=-1, help="Limit events for quick tests")
    parser.add_argument("--force", action="store_true", help="Regenerate filtered and weighted ROOT files even if they exist")
    parser.add_argument("--skip-fit", action="store_true", help="Only make plots from existing weighted files")
    return parser.parse_args()


def tag_for(channel: str, dataset: str, sample: str | None) -> str:
    tag = f"{channel.lower()}_{dataset}"
    if dataset == "mc" and sample:
        tag += f"_{sample.lower()}"
    return tag


def default_work_dir(channel: str, dataset: str, sample: str | None) -> str:
    return os.path.join(OUTPUT_BASE, "vertex_cut_study", tag_for(channel, dataset, sample))


def default_output_dir(channel: str, dataset: str, sample: str | None) -> str:
    return os.path.join(default_plot_dir(channel, dataset, sample), "vertex_cut_study")


def cut_scenarios() -> list[CutScenario]:
    return [
        CutScenario("no_vertex_cut", "No vertex cut", "1", ()),
        CutScenario(
            "pri_assocpv_pass",
            "Pri assocPV pass",
            "TakeAt(Pri_assocPVPass, bestCandIdx) > 0",
            ("Pri_assocPVPass", "bestCandIdx"),
        ),
        CutScenario(
            "pri_vtxprob",
            rf"Pri $P_{{vtx}} > {PRI_VTXPROB_MIN:g}$",
            f"sel_Pri_VtxProb > {float(PRI_VTXPROB_MIN)}",
            ("sel_Pri_VtxProb",),
        ),
    ]


def pair_specs(channel: str) -> list[PairSpec]:
    if channel == "JJP":
        return [
            PairSpec("jpsi1_jpsi2", r"$J/\psi_1$ vs $J/\psi_2$", "jpsi1", "jpsi2"),
            PairSpec("jpsi1_phi", r"$J/\psi_1$ vs $\phi$", "jpsi1", "phi"),
            PairSpec("jpsi2_phi", r"$J/\psi_2$ vs $\phi$", "jpsi2", "phi"),
        ]
    return [
        PairSpec("jpsi_ups", r"$J/\psi$ vs $\Upsilon$", "jpsi", "ups"),
        PairSpec("jpsi_phi", r"$J/\psi$ vs $\phi$", "jpsi", "phi"),
        PairSpec("ups_phi", r"$\Upsilon$ vs $\phi$", "ups", "phi"),
    ]


def pv_value_expressions(channel: str) -> dict[str, dict[str, str]]:
    if channel == "JJP":
        return {
            "jpsi1": {
                "dz": "0.5f*(TakeAt(muDzAssocPV, sel_Jpsi_1_mu_1_Idx) + TakeAt(muDzAssocPV, sel_Jpsi_1_mu_2_Idx))",
                "dxy": "0.5f*(TakeAt(muDxyAssocPV, sel_Jpsi_1_mu_1_Idx) + TakeAt(muDxyAssocPV, sel_Jpsi_1_mu_2_Idx))",
            },
            "jpsi2": {
                "dz": "0.5f*(TakeAt(muDzAssocPV, sel_Jpsi_2_mu_1_Idx) + TakeAt(muDzAssocPV, sel_Jpsi_2_mu_2_Idx))",
                "dxy": "0.5f*(TakeAt(muDxyAssocPV, sel_Jpsi_2_mu_1_Idx) + TakeAt(muDxyAssocPV, sel_Jpsi_2_mu_2_Idx))",
            },
            "phi": {
                "dz": "0.5f*(TakeAt(Phi_K_1_dzAssocPV, bestCandIdx) + TakeAt(Phi_K_2_dzAssocPV, bestCandIdx))",
                "dxy": "0.5f*(TakeAt(Phi_K_1_dxyAssocPV, bestCandIdx) + TakeAt(Phi_K_2_dxyAssocPV, bestCandIdx))",
            },
        }
    return {
        "jpsi": {
            "dz": "0.5f*(TakeAt(muDzAssocPV, sel_Jpsi_mu_1_Idx) + TakeAt(muDzAssocPV, sel_Jpsi_mu_2_Idx))",
            "dxy": "0.5f*(TakeAt(muDxyAssocPV, sel_Jpsi_mu_1_Idx) + TakeAt(muDxyAssocPV, sel_Jpsi_mu_2_Idx))",
        },
        "ups": {
            "dz": "0.5f*(TakeAt(muDzAssocPV, sel_Ups_mu_1_Idx) + TakeAt(muDzAssocPV, sel_Ups_mu_2_Idx))",
            "dxy": "0.5f*(TakeAt(muDxyAssocPV, sel_Ups_mu_1_Idx) + TakeAt(muDxyAssocPV, sel_Ups_mu_2_Idx))",
        },
        "phi": {
            "dz": "0.5f*(TakeAt(Phi_K_1_dzAssocPV, bestCandIdx) + TakeAt(Phi_K_2_dzAssocPV, bestCandIdx))",
            "dxy": "0.5f*(TakeAt(Phi_K_1_dxyAssocPV, bestCandIdx) + TakeAt(Phi_K_2_dxyAssocPV, bestCandIdx))",
        },
    }


def required_pv_branches(channel: str) -> set[str]:
    common = {"bestCandIdx", "muDzAssocPV", "muDxyAssocPV", "Phi_K_1_dzAssocPV", "Phi_K_2_dzAssocPV", "Phi_K_1_dxyAssocPV", "Phi_K_2_dxyAssocPV"}
    if channel == "JJP":
        common.update({"sel_Jpsi_1_mu_1_Idx", "sel_Jpsi_1_mu_2_Idx", "sel_Jpsi_2_mu_1_Idx", "sel_Jpsi_2_mu_2_Idx"})
    else:
        common.update({"sel_Jpsi_mu_1_Idx", "sel_Jpsi_mu_2_Idx", "sel_Ups_mu_1_Idx", "sel_Ups_mu_2_Idx"})
    return common


def add_pv_delta_columns(rdf, channel: str):
    expressions = pv_value_expressions(channel)
    derived_columns: list[str] = []

    for particle, variables in expressions.items():
        for coord, expression in variables.items():
            name = f"pv_{particle}_{coord}"
            rdf = rdf.Define(name, expression)
            derived_columns.append(name)

    for pair in pair_specs(channel):
        for coord in ("dz", "dxy"):
            name = f"delta_{coord}_{pair.key}"
            rdf = rdf.Define(name, f"pv_{pair.left}_{coord} - pv_{pair.right}_{coord}")
            derived_columns.append(name)

    return rdf, derived_columns


def validate_branches(input_file: str, channel: str):
    branches = set(get_tree_branches(input_file, INPUT_TREE))
    missing = sorted(required_pv_branches(channel) - branches)
    if missing:
        raise RuntimeError(f"Missing required PV branches in {input_file}: {', '.join(missing)}")
    return branches


def make_filtered_tree(input_file: str, output_file: str, channel: str, scenario: CutScenario, jobs: int, max_events: int):
    ensure_parent_dir(output_file)
    available = validate_branches(input_file, channel)
    missing = sorted(set(scenario.required_branches) - available)
    if missing:
        raise RuntimeError(f"Scenario '{scenario.key}' requires missing branches: {', '.join(missing)}")

    ROOT.gROOT.SetBatch(True)
    declare_rdf_helpers()
    if jobs > 1:
        ROOT.EnableImplicitMT(jobs)

    rdf = ROOT.RDataFrame(INPUT_TREE, input_file)
    if max_events > 0:
        rdf = rdf.Range(max_events)
    rdf, derived_columns = add_pv_delta_columns(rdf, channel)
    if scenario.expression and scenario.expression != "1":
        rdf = rdf.Filter(scenario.expression, scenario.key)

    original_columns = get_tree_branches(input_file, INPUT_TREE)
    snapshot_columns = list(dict.fromkeys(original_columns + derived_columns))
    count_action = rdf.Count()

    options = ROOT.RDF.RSnapshotOptions()
    options.fMode = "RECREATE"
    options.fLazy = True
    snapshot_action = rdf.Snapshot(INPUT_TREE, output_file, build_root_string_vector(snapshot_columns), options)
    ROOT.RDF.RunGraphs([count_action, snapshot_action])
    return int(count_action.GetValue())


def run_splot_fit(input_file: str, output_file: str, plot_dir: str, channel: str, dataset: str, jobs: int):
    ensure_parent_dir(output_file)
    ensure_dir(plot_dir)

    n_entries = uproot.open(input_file)[INPUT_TREE].num_entries
    if n_entries <= 0:
        raise RuntimeError(f"No events available for fit: {input_file}")

    ROOT.gROOT.SetBatch(True)
    ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.WARNING)
    fin = ROOT.TFile.Open(input_file)
    tree = fin.Get(INPUT_TREE)
    if not tree:
        fin.Close()
        raise RuntimeError(f"Input tree '{INPUT_TREE}' not found in {input_file}")

    if channel == "JJP":
        model, observables, yields, signal_yield_name, keepalive = fit_core.build_jjp_model(n_entries, mc_two_component=(dataset == "mc"))
    else:
        model, observables, yields, signal_yield_name, keepalive = fit_core.build_jup_model(
            n_entries,
            mc_only_1s=(dataset == "mc"),
            mc_two_component=(dataset == "mc"),
        )

    data = fit_core.make_dataset(tree, observables)
    keepalive.append(data)
    fit_result = model.fitTo(
        data,
        ROOT.RooFit.Extended(True),
        ROOT.RooFit.Save(True),
        ROOT.RooFit.NumCPU(max(1, jobs)),
        ROOT.RooFit.Strategy(2),
        ROOT.RooFit.PrintLevel(-1),
    )
    keepalive.append(fit_result)

    fit_core.save_projection_plots(channel, plot_dir, data, model, observables, signal_yield_name, yields)
    sdata = ROOT.RooStats.SPlot("sData", "sData", data, model, ROOT.RooArgList(*yields.values()))
    keepalive.append(sdata)

    weight_map = OrderedDict()
    for yield_name in yields:
        weight_map[f"{yield_name}_sw"] = [data.get(i).getRealValue(f"{yield_name}_sw") for i in range(data.numEntries())]
    weight_map[WEIGHT_BRANCH] = list(weight_map[f"{signal_yield_name}_sw"])

    significance = fit_core.compute_component_significance(
        model,
        data,
        yields,
        signal_yield_name,
        best_min_nll=fit_result.minNll(),
        jobs=jobs,
        strategy=2,
        print_level=-1,
    )
    keepalive.append(significance["null_fit_result"])

    fit_core.clone_tree_with_weights(tree, output_file, weight_map)
    fit_out = ROOT.TFile(output_file.replace(".root", "_fit_result.root"), "RECREATE")
    fit_result.Write("fit_result")
    fit_core.save_significance_to_root(fit_out, signal_yield_name, significance)
    fit_out.Close()
    fin.Close()

    return {
        "entries": n_entries,
        "signal_yield": float(yields[signal_yield_name].getVal()),
        "background_yield": float(significance["background_yield"]),
        "significance": float(significance["lrt_significance"]),
    }


def histogram_from_file(file_name: str, branch: str):
    arrays = uproot.open(file_name)[INPUT_TREE].arrays([branch, WEIGHT_BRANCH], library="np")
    values = np.asarray(arrays[branch], dtype=float)
    weights = np.asarray(arrays[WEIGHT_BRANCH], dtype=float)
    mask = np.isfinite(values) & np.isfinite(weights)
    return values[mask], weights[mask]


def weighted_hist(values: np.ndarray, weights: np.ndarray, edges: np.ndarray):
    counts, _ = np.histogram(values, bins=edges, weights=weights)
    sumw2, _ = np.histogram(values, bins=edges, weights=np.square(weights))
    if NORMALIZE_HISTS:
        total = np.sum(counts)
        if total != 0.0:
            counts = counts / total
            sumw2 = sumw2 / (total * total)
    return counts, np.sqrt(sumw2)


def ratio_to_reference(counts: np.ndarray, errors: np.ndarray, ref_counts: np.ndarray, ref_errors: np.ndarray):
    ratio = np.full_like(counts, np.nan, dtype=float)
    ratio_err = np.full_like(counts, np.nan, dtype=float)
    valid = ref_counts != 0.0
    ratio[valid] = counts[valid] / ref_counts[valid]

    positive = valid & (counts != 0.0)
    ratio_err[positive] = np.abs(ratio[positive]) * np.sqrt(
        np.square(errors[positive] / counts[positive]) +
        np.square(ref_errors[positive] / ref_counts[positive])
    )
    zero_num = valid & (counts == 0.0)
    ratio_err[zero_num] = errors[zero_num] / np.abs(ref_counts[zero_num])
    return ratio, ratio_err


def save_overlay_plot(channel: str, dataset: str, sample: str | None, pair: PairSpec, coord: str, weighted_files: dict[str, str], scenarios: list[CutScenario], output_dir: str):
    edges = np.linspace(*(DELTA_DZ_RANGE if coord == "dz" else DELTA_DXY_RANGE), N_BINS + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    colors = {
        "no_vertex_cut": "0.35",
        "pri_assocpv_pass": "#0072B2",
        "pri_vtxprob": "#D55E00",
    }
    markers = {
        "pri_assocpv_pass": "o",
        "pri_vtxprob": "s",
    }
    line_styles = {
        "pri_assocpv_pass": "-",
        "pri_vtxprob": "--",
    }

    histograms = {}
    weighted_sums = {}
    for scenario in scenarios:
        values, weights = histogram_from_file(weighted_files[scenario.key], f"delta_{coord}_{pair.key}")
        counts, errors = weighted_hist(values, weights, edges)
        histograms[scenario.key] = (counts, errors)
        weighted_sums[scenario.key] = float(np.sum(weights))

    ref_counts, ref_errors = histograms["no_vertex_cut"]

    fig, (ax, rax) = plt.subplots(
        2,
        1,
        figsize=(8, 8),
        sharex=True,
        gridspec_kw={"height_ratios": (3.0, 1.0), "hspace": 0.05},
    )

    hep.histplot(
        ref_counts,
        edges,
        yerr=ref_errors,
        histtype="fill",
        color=colors["no_vertex_cut"],
        alpha=0.22,
        label=f"No vertex cut (Nw={weighted_sums['no_vertex_cut']:.1f})",
        ax=ax,
    )
    hep.histplot(
        ref_counts,
        edges,
        histtype="step",
        linewidth=2.0,
        color=colors["no_vertex_cut"],
        ax=ax,
    )

    for scenario in scenarios:
        if scenario.key == "no_vertex_cut":
            continue
        counts, errors = histograms[scenario.key]
        hep.histplot(
            counts,
            edges,
            histtype="step",
            linewidth=2.4,
            linestyle=line_styles.get(scenario.key, "-"),
            color=colors.get(scenario.key, None),
            label=f"{scenario.label} (Nw={weighted_sums[scenario.key]:.1f})",
            ax=ax,
        )
        ax.errorbar(
            centers,
            counts,
            yerr=errors,
            fmt=markers.get(scenario.key, "o"),
            color=colors.get(scenario.key, None),
            markersize=4.5,
            linewidth=1.2,
            capsize=1.5,
        )

        ratio, ratio_err = ratio_to_reference(counts, errors, ref_counts, ref_errors)
        valid = np.isfinite(ratio)
        rax.errorbar(
            centers[valid],
            ratio[valid],
            yerr=ratio_err[valid],
            fmt=markers.get(scenario.key, "o"),
            color=colors.get(scenario.key, None),
            markersize=4.5,
            linewidth=1.2,
            capsize=1.5,
            label=scenario.label,
        )

    coord_label = r"\Delta dz" if coord == "dz" else r"\Delta dxy"
    ax.set_ylabel("Normalized sWeighted events" if NORMALIZE_HISTS else "sWeighted events")
    ax.set_title(pair.label)
    hep.cms.label("Work in progress", data=(dataset == "data"), ax=ax)
    ax.legend(loc="best", fontsize=15)
    ax.grid(True, linestyle=":", linewidth=0.8, alpha=0.45)

    rax.axhline(1.0, color="black", linestyle="--", linewidth=1.0)
    rax.set_ylabel("cut / no cut")
    rax.set_xlabel(rf"${coord_label}$ [cm]")
    rax.set_ylim(*RATIO_Y_RANGE)
    rax.grid(True, linestyle=":", linewidth=0.8, alpha=0.45)
    fig.tight_layout()

    base = os.path.join(output_dir, f"delta_{coord}_{pair.key}")
    fig.savefig(base + ".pdf")
    fig.savefig(base + ".png")
    plt.close(fig)


def main():
    args = parse_args()
    channel = normalize_channel(args.channel)
    dataset = normalize_dataset(args.dataset)
    sample = normalize_sample(channel, args.sample) if dataset == "mc" else None

    if args.max_events > 0 and args.jobs > 1:
        print("[INFO] --max-events with RDataFrame implicit MT is not supported; setting jobs to 1")
        args.jobs = 1

    input_file = args.input or default_merged_output(channel, dataset, sample)
    work_dir = args.work_dir or default_work_dir(channel, dataset, sample)
    output_dir = args.output_dir or default_output_dir(channel, dataset, sample)
    fit_plot_dir = os.path.join(work_dir, "fit_plots")
    ensure_dir(work_dir)
    ensure_dir(output_dir)
    ensure_dir(fit_plot_dir)

    plt.style.use(hep.style.CMS)
    scenarios = cut_scenarios()
    weighted_files: dict[str, str] = {}

    print("=" * 80)
    print("vertex-cut pileup study")
    print("=" * 80)
    print(f"[INFO] channel   : {channel}")
    print(f"[INFO] dataset   : {dataset}")
    print(f"[INFO] sample    : {sample or '-'}")
    print(f"[INFO] input     : {input_file}")
    print(f"[INFO] work dir  : {work_dir}")
    print(f"[INFO] output dir: {output_dir}")
    print(f"[INFO] bins      : {N_BINS}")
    print("=" * 80)

    for scenario in scenarios:
        filtered_file = os.path.join(work_dir, f"{scenario.key}_selected.root")
        weighted_file = os.path.join(work_dir, f"{scenario.key}_weighted.root")
        weighted_files[scenario.key] = weighted_file

        if not args.skip_fit and (args.force or not os.path.exists(weighted_file)):
            print(f"[INFO] scenario: {scenario.key}")
            print(f"[INFO] cut     : {scenario.expression}")
            if args.force or not os.path.exists(filtered_file):
                n_selected = make_filtered_tree(input_file, filtered_file, channel, scenario, args.jobs, args.max_events)
                print(f"[INFO] selected entries: {n_selected}")
            fit_summary = run_splot_fit(
                filtered_file,
                weighted_file,
                os.path.join(fit_plot_dir, scenario.key),
                channel,
                dataset,
                args.jobs,
            )
            print(
                "[INFO] fit summary: "
                f"entries={fit_summary['entries']} "
                f"signal={fit_summary['signal_yield']:.2f} "
                f"background={fit_summary['background_yield']:.2f} "
                f"Z={fit_summary['significance']:.2f}"
            )
        elif not os.path.exists(weighted_file):
            raise FileNotFoundError(f"Missing weighted file for --skip-fit: {weighted_file}")
        else:
            print(f"[INFO] reuse existing weighted file: {weighted_file}")

    for pair in pair_specs(channel):
        for coord in ("dz", "dxy"):
            save_overlay_plot(channel, dataset, sample, pair, coord, weighted_files, scenarios, output_dir)

    print(f"[INFO] saved vertex-cut comparison plots into {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

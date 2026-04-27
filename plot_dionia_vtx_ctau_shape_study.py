#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Study how DiOnia-related vertex cuts change sWeighted ctau shapes."""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
import ROOT
import uproot

import fit_splot as fit_core
import plot_vertex_cut_pileup_study as vertex_core
from ntuple_pipeline_common import (
    OUTPUT_BASE,
    default_merged_output,
    default_plot_dir,
    ensure_dir,
    ensure_parent_dir,
    normalize_channel,
    normalize_dataset,
    normalize_sample,
)


INPUT_TREE = "selected"
DIONIA_VTXPROB_MIN = 0.01
WEIGHT_BRANCH = "signal_sw"
NORMALIZE_HISTS = True
CTAU_RANGE = (-0.05, 0.1)
RATIO_Y_RANGE = (0.1, 10.0)


@dataclass(frozen=True)
class CutScenario:
    key: str
    label: str
    expression: str
    required_branches: tuple[str, ...]


def parse_args():
    parser = vertex_core.argparse.ArgumentParser(description="Study DiOnia vertex-cut effects on sWeighted ctau shapes")
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
    return os.path.join(OUTPUT_BASE, "dionia_vtx_ctau_study", tag_for(channel, dataset, sample))


def default_output_dir(channel: str, dataset: str, sample: str | None) -> str:
    return os.path.join(default_plot_dir(channel, dataset, sample), "dionia_vtx_ctau_study")


def cut_scenarios() -> list[CutScenario]:
    return [
        CutScenario("no_dionia_vtx_cut", "No DiOnia vertex cut", "1", ()),
        CutScenario(
            "dionia_common_recvtx",
            "All from same vertex",
            "TakeAtInt(DiOnia_commonRecVtxPass, bestCandIdx) > 0",
            ("DiOnia_commonRecVtxPass", "bestCandIdx"),
        ),
        CutScenario(
            "dionia_vtxprob",
            rf"DiOnia $P_{{vtx}} > {DIONIA_VTXPROB_MIN:g}$",
            f"TakeAt(DiOnia_VtxProb, bestCandIdx) > {float(DIONIA_VTXPROB_MIN)}",
            ("DiOnia_VtxProb", "bestCandIdx"),
        ),
    ]


def ctau_plot_specs(channel: str) -> list[vertex_core.PlotSpec]:
    if channel == "JJP":
        return [
            vertex_core.PlotSpec("ctau_jpsi1", "sel_Jpsi_1_ctau", r"$J/\psi_1$", r"$c\tau$ [cm]", CTAU_RANGE),
            vertex_core.PlotSpec("ctau_jpsi2", "sel_Jpsi_2_ctau", r"$J/\psi_2$", r"$c\tau$ [cm]", CTAU_RANGE),
            vertex_core.PlotSpec("ctau_phi", "sel_Phi_ctau", r"$\phi$", r"$c\tau$ [cm]", CTAU_RANGE),
        ]
    return [
        vertex_core.PlotSpec("ctau_jpsi", "sel_Jpsi_ctau", r"$J/\psi$", r"$c\tau$ [cm]", CTAU_RANGE),
        vertex_core.PlotSpec("ctau_ups", "sel_Ups_ctau", r"$\Upsilon$", r"$c\tau$ [cm]", CTAU_RANGE),
        vertex_core.PlotSpec("ctau_phi", "sel_Phi_ctau", r"$\phi$", r"$c\tau$ [cm]", CTAU_RANGE),
    ]


def validate_branches(input_file: str, channel: str):
    branches = set(vertex_core.get_tree_branches(input_file, INPUT_TREE))
    required = {"DiOnia_commonRecVtxPass", "DiOnia_VtxProb"}
    required.add("bestCandIdx")
    required.update(spec.branch for spec in ctau_plot_specs(channel))
    missing = sorted(required - branches)
    if missing:
        raise RuntimeError(f"Missing required branches in {input_file}: {', '.join(missing)}")
    return branches


def make_filtered_tree(input_file: str, output_file: str, channel: str, scenario: CutScenario, jobs: int, max_events: int):
    ensure_parent_dir(output_file)
    available = validate_branches(input_file, channel)
    missing = sorted(set(scenario.required_branches) - available)
    if missing:
        raise RuntimeError(f"Scenario '{scenario.key}' requires missing branches: {', '.join(missing)}")

    ROOT.gROOT.SetBatch(True)
    vertex_core.declare_rdf_helpers()
    if jobs > 1:
        ROOT.EnableImplicitMT(jobs)

    rdf = ROOT.RDataFrame(INPUT_TREE, input_file)
    if max_events > 0:
        rdf = rdf.Range(max_events)
    if scenario.expression and scenario.expression != "1":
        rdf = rdf.Filter(scenario.expression, scenario.key)

    original_columns = vertex_core.get_tree_branches(input_file, INPUT_TREE)
    count_action = rdf.Count()
    options = ROOT.RDF.RSnapshotOptions()
    options.fMode = "RECREATE"
    options.fLazy = True
    snapshot_action = rdf.Snapshot(INPUT_TREE, output_file, vertex_core.build_root_string_vector(original_columns), options)
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

    weight_map = {}
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


def save_overlay_plot(
    dataset: str,
    plot_spec: vertex_core.PlotSpec,
    weighted_files: dict[str, str],
    scenarios: list[CutScenario],
    output_dir: str,
):
    edges = np.linspace(*plot_spec.value_range, vertex_core.N_BINS + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    colors = {
        "no_dionia_vtx_cut": "0.35",
        "dionia_common_recvtx": "#0072B2",
        "dionia_vtxprob": "#D55E00",
    }
    markers = {
        "dionia_common_recvtx": "o",
        "dionia_vtxprob": "s",
    }
    line_styles = {
        "dionia_common_recvtx": "-",
        "dionia_vtxprob": "--",
    }

    histograms = {}
    weighted_sums = {}
    for scenario in scenarios:
        values, weights = histogram_from_file(weighted_files[scenario.key], plot_spec.branch)
        counts, errors = weighted_hist(values, weights, edges)
        histograms[scenario.key] = (counts, errors)
        weighted_sums[scenario.key] = float(np.sum(weights))

    ref_counts, ref_errors = histograms["no_dionia_vtx_cut"]

    fig, (ax, rax) = plt.subplots(
        2,
        1,
        figsize=(10.5, 9.0),
        sharex=True,
        gridspec_kw={"height_ratios": (3.2, 1.15), "hspace": 0.05},
    )

    hep.histplot(
        ref_counts,
        edges,
        yerr=ref_errors,
        histtype="fill",
        color=colors["no_dionia_vtx_cut"],
        alpha=0.22,
        label=f"No cut (Nw={weighted_sums['no_dionia_vtx_cut']:.1f})",
        ax=ax,
    )
    hep.histplot(
        ref_counts,
        edges,
        histtype="step",
        linewidth=2.0,
        color=colors["no_dionia_vtx_cut"],
        ax=ax,
    )

    for scenario in scenarios:
        if scenario.key == "no_dionia_vtx_cut":
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

    ax.set_ylabel("Normalized sWeighted events" if NORMALIZE_HISTS else "sWeighted events")
    ax.set_title(plot_spec.title)
    hep.cms.label("Work in progress", data=(dataset == "data"), ax=ax)
    ax.legend(loc="best", fontsize=13)
    ax.grid(True, linestyle=":", linewidth=0.8, alpha=0.45)
    ax.set_xlim(*CTAU_RANGE)
    ax.set_yscale("log")
    positive = np.concatenate([counts[counts > 0.0] for counts, _ in histograms.values() if np.any(counts > 0.0)])
    ymin = max(np.min(positive) * 0.5, 1.0e-4) if positive.size else 1.0e-4
    ymax = max(np.max(np.concatenate([counts for counts, _ in histograms.values()])) * 10.0, 1.0)
    ax.set_ylim(ymin, ymax)

    rax.axhline(1.0, color="black", linestyle="--", linewidth=1.0)
    rax.set_ylabel("cut / no cut")
    rax.set_xlabel(plot_spec.xlabel)
    rax.set_ylim(*RATIO_Y_RANGE)
    rax.set_yscale("log")
    rax.grid(True, linestyle=":", linewidth=0.8, alpha=0.45)
    fig.subplots_adjust(left=0.12, right=0.97, top=0.93, bottom=0.08, hspace=0.05)

    base = os.path.join(output_dir, plot_spec.key)
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
    print("DiOnia vertex-cut ctau shape study")
    print("=" * 80)
    print(f"[INFO] channel   : {channel}")
    print(f"[INFO] dataset   : {dataset}")
    print(f"[INFO] sample    : {sample or '-'}")
    print(f"[INFO] input     : {input_file}")
    print(f"[INFO] work dir  : {work_dir}")
    print(f"[INFO] output dir: {output_dir}")
    print(f"[INFO] ctau range: {CTAU_RANGE}")
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

    for plot_spec in ctau_plot_specs(channel):
        save_overlay_plot(dataset, plot_spec, weighted_files, scenarios, output_dir)

    print(f"[INFO] saved DiOnia vertex-cut ctau comparison plots into {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

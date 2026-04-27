#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fit signal yield in bins of an observable using the same mass model as fit_splot."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from array import array

import ROOT
import uproot

import fit_splot as fit_core
from ntuple_pipeline_common import (
    default_merged_output,
    default_plot_dir,
    default_weighted_output,
    ensure_dir,
    ensure_parent_dir,
    normalize_channel,
    normalize_dataset,
    normalize_sample,
)

INPUT_TREE = "selected"


def parse_args():
    parser = argparse.ArgumentParser(description="Fit yields in bins of a selected observable")
    parser.add_argument("--channel", required=True, choices=["JJP", "JUP", "jjp", "jup"])
    parser.add_argument("--dataset", default="data", choices=["data", "mc"])
    parser.add_argument("--sample", default=None, help="MC sample tag")
    parser.add_argument("-i", "--input", default=None, help="Input selected ROOT file")
    parser.add_argument("--observable", required=True, help="Branch name used for binning")
    parser.add_argument("--bin-edges", default=None, help="Comma-separated bin edges, e.g. 0,2,4,6")
    parser.add_argument("--nbins", type=int, default=None)
    parser.add_argument("--xmin", type=float, default=None)
    parser.add_argument("--xmax", type=float, default=None)
    parser.add_argument("--output-root", default="bin_yields.root")
    parser.add_argument("--output-json", default="bin_yields.json")
    parser.add_argument("--output-csv", default="bin_yields.csv")
    parser.add_argument("--plot-dir", default=None)
    parser.add_argument("--splot-input", default=None, help="Weighted ROOT file from fit_splot.py")
    parser.add_argument("--min-events", type=int, default=50, help="Minimum events per bin to run fit")
    parser.add_argument("--global-init", action="store_true", help="Run inclusive fit and use it as parameter initialization")
    parser.add_argument("--freeze-shape", action="store_true", help="Freeze non-yield parameters in per-bin fits")
    parser.add_argument("--retry-strategies", default="2,1", help="Comma-separated RooFit strategies to retry")
    parser.add_argument("--minos", action="store_true", help="Enable MINOS for per-bin fit")
    parser.add_argument("-j", "--jobs", type=int, default=4)
    return parser.parse_args()


def parse_bin_edges(args):
    if args.bin_edges:
        edges = [float(item.strip()) for item in args.bin_edges.split(",") if item.strip()]
    else:
        if args.nbins is None or args.xmin is None or args.xmax is None:
            raise ValueError("Provide --bin-edges OR --nbins/--xmin/--xmax")
        if args.nbins <= 0:
            raise ValueError("--nbins must be positive")
        step = (args.xmax - args.xmin) / float(args.nbins)
        edges = [args.xmin + i * step for i in range(args.nbins + 1)]
    if len(edges) < 2:
        raise ValueError("At least two bin edges are required")
    if sorted(edges) != edges:
        raise ValueError("Bin edges must be sorted")
    return edges


def run_single_bin_fit(tree, channel, dataset, jobs, strategy, init_snapshot, freeze_shape, use_minos):
    fit_result, yields, context = fit_core.fit_dataset_with_model(
        tree,
        channel=channel,
        dataset=dataset,
        jobs=jobs,
        strategy=strategy,
        print_level=-1,
        minos=use_minos,
        hesse=True,
        init_snapshot=init_snapshot,
        freeze_shape=freeze_shape,
    )
    signal_name = context["signal_yield_name"]
    y_sig = yields[signal_name]
    err = float(y_sig.getError())
    if use_minos:
        err_lo = abs(float(y_sig.getErrorLo())) if y_sig.getErrorLo() != 0 else err
        err_hi = abs(float(y_sig.getErrorHi())) if y_sig.getErrorHi() != 0 else err
        err = max(err_lo, err_hi)
    metrics = {
        "status": int(fit_result.status()),
        "covQual": int(fit_result.covQual()),
        "edm": float(fit_result.edm()),
        "nll": float(fit_result.minNll()),
    }
    return {
        "fit_result": fit_result,
        "yield": float(y_sig.getVal()),
        "yield_err": err,
        "metrics": metrics,
        "snapshot": fit_core.snapshot_parameters(context["model"], context["data"]),
        "context": context,
    }


def choose_best_result(results):
    return sorted(
        results,
        key=lambda item: (item["metrics"]["status"], -item["metrics"]["covQual"], item["metrics"]["edm"]),
    )[0]


def read_splot_binned_yields(splot_file, observable, edges):
    if not splot_file or not os.path.exists(splot_file):
        return None
    arrays = uproot.open(splot_file)[INPUT_TREE].arrays([observable, "signal_sw"], library="np")
    values = arrays[observable]
    weights = arrays["signal_sw"]

    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        if hi == edges[-1]:
            mask = (values >= lo) & (values <= hi)
        else:
            mask = (values >= lo) & (values < hi)
        w = weights[mask]
        y = float(w.sum())
        yerr = float(math.sqrt((w * w).sum()))
        out.append((y, yerr))
    return out


def main():
    args = parse_args()
    channel = normalize_channel(args.channel)
    dataset = normalize_dataset(args.dataset)
    sample = normalize_sample(channel, args.sample) if dataset == "mc" else None
    bin_edges = parse_bin_edges(args)
    strategies = [int(item.strip()) for item in args.retry_strategies.split(",") if item.strip()]
    if not strategies:
        strategies = [2]

    input_file = args.input or default_merged_output(channel, dataset, sample)
    plot_dir = args.plot_dir or os.path.join(default_plot_dir(channel, dataset, sample), "fit_in_bins")
    ensure_dir(plot_dir)

    out_root = args.output_root
    out_json = args.output_json
    out_csv = args.output_csv
    if not os.path.isabs(out_root):
        out_root = os.path.join(plot_dir, out_root)
    if not os.path.isabs(out_json):
        out_json = os.path.join(plot_dir, out_json)
    if not os.path.isabs(out_csv):
        out_csv = os.path.join(plot_dir, out_csv)
    ensure_parent_dir(out_root)
    ensure_parent_dir(out_json)
    ensure_parent_dir(out_csv)

    ROOT.gROOT.SetBatch(True)
    ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.WARNING)

    fin = ROOT.TFile.Open(input_file)
    tree = fin.Get(INPUT_TREE)
    if not tree:
        fin.Close()
        raise RuntimeError(f"Input tree '{INPUT_TREE}' not found in {input_file}")
    if not tree.GetBranch(args.observable):
        fin.Close()
        raise RuntimeError(f"Observable branch '{args.observable}' not found in {input_file}:{INPUT_TREE}")

    init_snapshot = None
    if args.global_init:
        global_result = run_single_bin_fit(
            tree=tree,
            channel=channel,
            dataset=dataset,
            jobs=args.jobs,
            strategy=strategies[0],
            init_snapshot=None,
            freeze_shape=False,
            use_minos=False,
        )
        init_snapshot = global_result["snapshot"]

    bin_rows = []
    for ibin, (lo, hi) in enumerate(zip(bin_edges[:-1], bin_edges[1:])):
        is_last = ibin == len(bin_edges) - 2
        cond_hi = "<=" if is_last else "<"
        cut_expr = f"{args.observable} >= {lo} && {args.observable} {cond_hi} {hi}"
        bin_tree = tree.CopyTree(cut_expr)
        n_events = int(bin_tree.GetEntries()) if bin_tree else 0

        row = {
            "bin": ibin,
            "x_low": lo,
            "x_high": hi,
            "x_center": 0.5 * (lo + hi),
            "n_events": n_events,
            "valid": False,
            "yield_sss": 0.0,
            "yield_sss_err": 0.0,
            "status": -1,
            "covQual": -1,
            "edm": float("nan"),
            "nll": float("nan"),
            "strategy": -1,
            "retries": 0,
            "note": "",
        }

        if n_events < args.min_events:
            row["note"] = f"invalid: n_events={n_events} < min_events={args.min_events}"
            bin_rows.append(row)
            continue

        attempts = []
        for strategy in strategies:
            try:
                fit_out = run_single_bin_fit(
                    tree=bin_tree,
                    channel=channel,
                    dataset=dataset,
                    jobs=args.jobs,
                    strategy=strategy,
                    init_snapshot=init_snapshot,
                    freeze_shape=args.freeze_shape,
                    use_minos=args.minos,
                )
                fit_out["strategy"] = strategy
                attempts.append(fit_out)
                if fit_out["metrics"]["status"] == 0 and fit_out["metrics"]["covQual"] >= 2:
                    break
            except Exception as exc:
                row["note"] = f"fit exception at strategy={strategy}: {exc}"

        if not attempts:
            row["note"] = row["note"] or "fit failed for all retries"
            bin_rows.append(row)
            continue

        best = choose_best_result(attempts)
        row["valid"] = best["metrics"]["status"] == 0
        row["yield_sss"] = best["yield"]
        row["yield_sss_err"] = best["yield_err"]
        row["status"] = best["metrics"]["status"]
        row["covQual"] = best["metrics"]["covQual"]
        row["edm"] = best["metrics"]["edm"]
        row["nll"] = best["metrics"]["nll"]
        row["strategy"] = best["strategy"]
        row["retries"] = len(attempts)
        row["note"] = row["note"] or ("ok" if row["valid"] else "not converged")
        bin_rows.append(row)

    splot_input = args.splot_input or default_weighted_output(channel, dataset, sample)
    splot_bins = read_splot_binned_yields(splot_input, args.observable, bin_edges)
    for i, row in enumerate(bin_rows):
        if splot_bins is None:
            row["splot_yield"] = float("nan")
            row["splot_yield_err"] = float("nan")
            row["ratio_fit_over_splot"] = float("nan")
            row["ratio_fit_over_splot_err"] = float("nan")
            continue
        s_y, s_e = splot_bins[i]
        row["splot_yield"] = s_y
        row["splot_yield_err"] = s_e
        if s_y != 0.0:
            ratio = row["yield_sss"] / s_y
            frac_var = 0.0
            if row["yield_sss"] != 0.0:
                frac_var += (row["yield_sss_err"] / row["yield_sss"]) ** 2
            if s_y != 0.0:
                frac_var += (s_e / s_y) ** 2
            row["ratio_fit_over_splot"] = ratio
            row["ratio_fit_over_splot_err"] = abs(ratio) * math.sqrt(max(0.0, frac_var))
        else:
            row["ratio_fit_over_splot"] = float("nan")
            row["ratio_fit_over_splot_err"] = float("nan")

    with open(out_json, "w", encoding="utf-8") as fout:
        json.dump({"observable": args.observable, "bin_edges": bin_edges, "bins": bin_rows}, fout, indent=2)

    fieldnames = list(bin_rows[0].keys()) if bin_rows else []
    with open(out_csv, "w", newline="", encoding="utf-8") as fout:
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(bin_rows)

    root_out = ROOT.TFile(out_root, "RECREATE")
    hist_fit = ROOT.TH1D("h_fit_signal", "fit-in-bins signal yield;bin;N_{sig}", len(bin_edges) - 1, array('d', bin_edges))
    hist_splot = ROOT.TH1D("h_splot_signal", "sPlot signal yield;bin;N_{sig}", len(bin_edges) - 1, array('d', bin_edges))
    graph_fit = ROOT.TGraphErrors(len(bin_rows))
    graph_fit.SetName("g_fit_signal")
    graph_fit.SetTitle(f"Fit-in-bins yield vs {args.observable};{args.observable};N_{{sig}}")
    graph_ratio = ROOT.TGraphErrors(len(bin_rows))
    graph_ratio.SetName("g_fit_over_splot")
    graph_ratio.SetTitle(f"(fit-in-bins)/(sPlot) vs {args.observable};{args.observable};ratio")

    for i, row in enumerate(bin_rows, start=1):
        width = 0.5 * (row["x_high"] - row["x_low"])
        hist_fit.SetBinContent(i, row["yield_sss"])
        hist_fit.SetBinError(i, row["yield_sss_err"])
        graph_fit.SetPoint(i - 1, row["x_center"], row["yield_sss"])
        graph_fit.SetPointError(i - 1, width, row["yield_sss_err"])

        if splot_bins is not None and not math.isnan(row["splot_yield"]):
            hist_splot.SetBinContent(i, row["splot_yield"])
            hist_splot.SetBinError(i, row["splot_yield_err"])
            graph_ratio.SetPoint(i - 1, row["x_center"], row["ratio_fit_over_splot"])
            graph_ratio.SetPointError(i - 1, width, row["ratio_fit_over_splot_err"])

    hist_fit.Write()
    hist_splot.Write()
    graph_fit.Write()
    graph_ratio.Write()

    c_cmp = ROOT.TCanvas("c_compare", "compare", 900, 700)
    hist_fit.SetLineColor(ROOT.kRed + 1)
    hist_fit.SetMarkerColor(ROOT.kRed + 1)
    hist_fit.SetMarkerStyle(20)
    hist_fit.Draw("E1")
    if splot_bins is not None:
        hist_splot.SetLineColor(ROOT.kBlue + 1)
        hist_splot.SetMarkerColor(ROOT.kBlue + 1)
        hist_splot.SetMarkerStyle(24)
        hist_splot.Draw("E1 SAME")
        leg = ROOT.TLegend(0.58, 0.75, 0.88, 0.88)
        leg.AddEntry(hist_fit, "fit-in-bins", "lep")
        leg.AddEntry(hist_splot, "sPlot", "lep")
        leg.Draw()
    c_cmp.SaveAs(os.path.join(plot_dir, f"{args.observable}_fit_vs_splot.png"))
    c_cmp.SaveAs(os.path.join(plot_dir, f"{args.observable}_fit_vs_splot.pdf"))

    c_ratio = ROOT.TCanvas("c_ratio", "ratio", 900, 700)
    graph_ratio.SetMarkerStyle(20)
    graph_ratio.Draw("AP")
    c_ratio.SaveAs(os.path.join(plot_dir, f"{args.observable}_fit_over_splot_ratio.png"))
    c_ratio.SaveAs(os.path.join(plot_dir, f"{args.observable}_fit_over_splot_ratio.pdf"))

    root_out.Write()
    root_out.Close()
    fin.Close()

    n_valid = sum(1 for row in bin_rows if row["valid"])
    print(f"[INFO] wrote ROOT  : {out_root}")
    print(f"[INFO] wrote JSON  : {out_json}")
    print(f"[INFO] wrote CSV   : {out_csv}")
    print(f"[INFO] valid bins  : {n_valid}/{len(bin_rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

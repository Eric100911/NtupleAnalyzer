#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plot weighted physics distributions from the sWeighted ntuple."""

from __future__ import annotations

import argparse
import math
import os
import sys

import ROOT

from ntuple_pipeline_common import (
    CHANNEL_CONFIGS,
    default_plot_dir,
    default_weighted_output,
    ensure_dir,
    normalize_channel,
    normalize_dataset,
    normalize_sample,
)


INPUT_TREE = "selected"


def parse_args():
    parser = argparse.ArgumentParser(description="Plot weighted assocPV distributions")
    parser.add_argument("--channel", required=True, choices=["JJP", "JUP", "jjp", "jup"])
    parser.add_argument("--dataset", default="data", choices=["data", "mc"])
    parser.add_argument("--sample", default=None, help="MC sample tag")
    parser.add_argument("-i", "--input", default=None, help="Input weighted ROOT file")
    parser.add_argument("-o", "--output-dir", default=None, help="Plot output directory")
    parser.add_argument("-j", "--jobs", type=int, default=8, help="RDataFrame thread count")
    parser.add_argument("-w", "--weight-branch", default="signal_sw", help="Weight branch")
    return parser.parse_args()


def label_for_branch(name: str) -> str:
    return name.replace("sel_", "").replace("_", " ")


def infer_histogram(name: str):
    if "abs_dphi" in name:
        return 60, 0.0, math.pi
    if "abs_dy" in name:
        return 60, 0.0, 5.0
    if name.endswith("_phi"):
        return 60, -math.pi, math.pi
    if name.endswith("_eta") or name.endswith("_y"):
        return 60, -3.0, 3.0
    if name.endswith("_pt"):
        return 80, 0.0, 100.0
    if name.endswith("_VtxProb"):
        return 60, 0.0, 1.0
    if name.endswith("_Chi2"):
        return 60, 0.0, 50.0
    if name.endswith("_ndof"):
        return 40, 0.0, 40.0
    if name.endswith("_ctau") or name.endswith("_ctauErr"):
        return 80, -1.0, 1.0
    if name.endswith("_mass"):
        if "Ups" in name:
            return 80, 8.5, 11.4
        if "Phi" in name:
            return 80, 0.99, 1.07
        if "Jpsi" in name:
            return 80, 2.9, 3.3
        return 80, 0.0, 40.0
    if name.endswith("_massErr"):
        return 60, 0.0, 0.2
    if name.endswith("_massDiff"):
        return 80, -0.2, 0.2
    if name.endswith("_m_all"):
        return 100, 0.0, 60.0
    if name.endswith("_m_jpsi1_jpsi2") or name.endswith("_m_jpsi_ups"):
        return 100, 0.0, 40.0
    if name.endswith("_m_jpsi1_phi") or name.endswith("_m_jpsi2_phi") or name.endswith("_m_jpsi_phi"):
        return 100, 0.0, 30.0
    if name.endswith("_m_ups_phi"):
        return 100, 0.0, 40.0
    return 80, 0.0, 100.0


def discover_plot_columns(rdf):
    columns = []
    for name in rdf.GetColumnNames():
        col = str(name)
        if not col.startswith("sel_"):
            continue
        if col.endswith("_Idx") or col == "sel_m_all":
            pass
        col_type = str(rdf.GetColumnType(col))
        if "RVec" in col_type or "vector<" in col_type or "string" in col_type:
            continue
        if col.endswith("_Idx"):
            continue
        columns.append(col)
    columns.append("sel_m_all")
    return sorted(set(columns))


def save_histogram(hist, output_base: str):
    canvas = ROOT.TCanvas(f"c_{hist.GetName()}", hist.GetName(), 800, 700)
    hist.SetLineWidth(2)
    hist.SetLineColor(ROOT.kBlue + 1)
    hist.GetYaxis().SetTitle("Weighted events")
    hist.GetXaxis().SetTitle(label_for_branch(hist.GetName()))
    hist.Draw("HIST")
    canvas.SaveAs(output_base + ".pdf")
    canvas.SaveAs(output_base + ".png")


def save_overlay(rdf, branches, weight_branch, output_base, title, colors):
    canvas = ROOT.TCanvas(f"c_{title}", title, 800, 700)
    legend = ROOT.TLegend(0.58, 0.68, 0.88, 0.88)
    legend.SetBorderSize(0)
    legend.SetFillStyle(0)

    hists = []
    ymax = 0.0
    for branch, color in zip(branches, colors):
        bins, xmin, xmax = infer_histogram(branch)
        hist = rdf.Histo1D((f"h_{branch}", title, bins, xmin, xmax), branch, weight_branch).GetValue()
        hist.SetDirectory(0)
        hist.SetLineWidth(2)
        hist.SetLineColor(color)
        ymax = max(ymax, hist.GetMaximum())
        hists.append(hist)

    first = True
    for hist in hists:
        hist.SetMaximum(ymax * 1.3 if ymax > 0 else 1.0)
        hist.GetYaxis().SetTitle("Weighted events")
        if first:
            hist.Draw("HIST")
            first = False
        else:
            hist.Draw("HIST SAME")
        legend.AddEntry(hist, hist.GetName().replace("h_", "").replace("sel_", ""), "l")
    legend.Draw()
    canvas.SaveAs(output_base + ".pdf")
    canvas.SaveAs(output_base + ".png")


def save_correlation_plot(rdf, dy_branch, dphi_branch, weight_branch, output_base, title):
    canvas = ROOT.TCanvas(f"c2_{dy_branch}", title, 800, 700)
    hist = rdf.Histo2D(
        (f"h2_{dy_branch}", title, 60, 0.0, 5.0, 60, 0.0, math.pi),
        dy_branch,
        dphi_branch,
        weight_branch,
    ).GetValue()
    hist.SetDirectory(0)
    hist.GetXaxis().SetTitle("|#Delta y|")
    hist.GetYaxis().SetTitle("|#Delta #phi|")
    hist.GetZaxis().SetTitle("Weighted events")
    hist.Draw("COLZ")
    canvas.SaveAs(output_base + ".pdf")
    canvas.SaveAs(output_base + ".png")


def main():
    args = parse_args()
    channel = normalize_channel(args.channel)
    dataset = normalize_dataset(args.dataset)
    sample = normalize_sample(channel, args.sample) if dataset == "mc" else None
    input_file = args.input or default_weighted_output(channel, dataset, sample)
    output_dir = args.output_dir or default_plot_dir(channel, dataset, sample)
    ensure_dir(output_dir)

    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)
    if args.jobs > 1:
        ROOT.EnableImplicitMT(args.jobs)

    rdf = ROOT.RDataFrame(INPUT_TREE, input_file)
    columns = discover_plot_columns(rdf)

    hist_root = ROOT.TFile(os.path.join(output_dir, "weighted_histograms.root"), "RECREATE")
    for branch in columns:
        bins, xmin, xmax = infer_histogram(branch)
        hist = rdf.Histo1D((branch, branch, bins, xmin, xmax), branch, args.weight_branch).GetValue()
        hist.SetDirectory(hist_root)
        hist.Write()
        save_histogram(hist, os.path.join(output_dir, branch))
    hist_root.Close()

    cfg = CHANNEL_CONFIGS[channel]
    dy_branches = [f"sel_abs_dy_{name}" for name, _, _ in cfg.pair_specs]
    dphi_branches = [f"sel_abs_dphi_{name}" for name, _, _ in cfg.pair_specs]
    save_overlay(
        rdf,
        dy_branches,
        args.weight_branch,
        os.path.join(output_dir, "delta_y_comparison"),
        "DeltaY comparison",
        [ROOT.kRed + 1, ROOT.kBlue + 1, ROOT.kGreen + 2],
    )
    save_overlay(
        rdf,
        dphi_branches,
        args.weight_branch,
        os.path.join(output_dir, "delta_phi_comparison"),
        "DeltaPhi comparison",
        [ROOT.kRed + 1, ROOT.kBlue + 1, ROOT.kGreen + 2],
    )

    for pair_name, _, _ in cfg.pair_specs:
        save_correlation_plot(
            rdf,
            f"sel_abs_dy_{pair_name}",
            f"sel_abs_dphi_{pair_name}",
            args.weight_branch,
            os.path.join(output_dir, f"correlation_2d_{pair_name}"),
            f"{channel} {pair_name}",
        )

    print(f"[INFO] plotted {len(columns)} weighted 1D distributions into {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

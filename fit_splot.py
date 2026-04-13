#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fit mass spectra and write SPlot weights back to the selected ntuple."""

from __future__ import annotations

import argparse
import array
import math
import os
import sys
from collections import OrderedDict

import ROOT
import uproot

from ntuple_pipeline_common import (
    OUTPUT_BASE,
    TREE_NAME,
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
    parser = argparse.ArgumentParser(description="Run RooFit + SPlot on selected assocPV ntuples")
    parser.add_argument("--channel", required=True, choices=["JJP", "JUP", "jjp", "jup"])
    parser.add_argument("--dataset", default="data", choices=["data", "mc"])
    parser.add_argument("--sample", default=None, help="MC sample tag")
    parser.add_argument("-i", "--input", default=None, help="Input selected ROOT file")
    parser.add_argument("-o", "--output", default=None, help="Output ROOT file with sWeights")
    parser.add_argument("--plot-dir", default=None, help="Directory for fit projections")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="RooFit NumCPU")
    return parser.parse_args()


def build_jpsi_signal(obs, suffix: str, shared, keep):
    cb = ROOT.RooCBShape(
        f"jpsi_cb_{suffix}",
        f"jpsi_cb_{suffix}",
        obs,
        shared["mean"],
        shared["sigma_cb"],
        shared["alpha"],
        shared["n"],
    )
    gauss = ROOT.RooGaussian(
        f"jpsi_gauss_{suffix}",
        f"jpsi_gauss_{suffix}",
        obs,
        shared["mean"],
        shared["sigma_gauss"],
    )
    pdf = ROOT.RooAddPdf(
        f"jpsi_sig_{suffix}",
        f"jpsi_sig_{suffix}",
        ROOT.RooArgList(cb, gauss),
        ROOT.RooArgList(shared["frac_gauss"]),
    )
    keep.extend([cb, gauss, pdf])
    return pdf


def build_jpsi_background(obs, suffix: str, slope, keep):
    pdf = ROOT.RooExponential(f"jpsi_bkg_{suffix}", f"jpsi_bkg_{suffix}", obs, slope)
    keep.append(pdf)
    return pdf


def build_phi_signal(obs):
    mean = ROOT.RooRealVar("phi_mean", "phi_mean", 1.019, 1.010, 1.028)
    # width = ROOT.RooRealVar("phi_width", "phi_width", 0.002, 0.0005, 0.005)
    width = ROOT.RooRealVar("phi_width", "phi_width", 0.002124)
    width.setConstant(True)
    sigma = ROOT.RooRealVar("phi_sigma", "phi_sigma", 0.002, 0.0002, 0.005)
    pdf = ROOT.RooVoigtian("phi_sig", "phi_sig", obs, mean, width, sigma)
    return pdf, {"mean": mean, "width": width, "sigma": sigma, "pdf": pdf}


def build_phi_background(obs):
    c0 = ROOT.RooRealVar("phi_bkg_c0", "phi_bkg_c0", 0.0, -100.0, 100.0)
    c1 = ROOT.RooRealVar("phi_bkg_c1", "phi_bkg_c1", 0.0, -100.0, 100.0)
    c2 = ROOT.RooRealVar("phi_bkg_c2", "phi_bkg_c2", 0.0, -100.0, 100.0)
    pdf = ROOT.RooChebychev("phi_bkg", "phi_bkg", obs, ROOT.RooArgList(c0, c1, c2))
    return pdf, {"c0": c0, "c1": c1, "c2": c2, "pdf": pdf}


def build_ups_signal(obs):
    keep = []
    mean_1s = ROOT.RooRealVar("mean_Ups_1S", "mean_Ups_1S", 9.460, 9.40, 9.50)
    sigma_1s_1 = ROOT.RooConstVar("sigma_Ups_1S_1", "sigma_Ups_1S_1", 0.081172)
    sigma_1s_2 = ROOT.RooConstVar("sigma_Ups_1S_2", "sigma_Ups_1S_2", 0.05)
    diff_2s = ROOT.RooConstVar("mean_diff_2S_1S", "mean_diff_2S_1S", 10.023 - 9.460)
    diff_3s = ROOT.RooConstVar("mean_diff_3S_1S", "mean_diff_3S_1S", 10.355 - 9.460)
    mean_2s = ROOT.RooFormulaVar("mean_Ups_2S", "@0+@1", ROOT.RooArgList(mean_1s, diff_2s))
    mean_3s = ROOT.RooFormulaVar("mean_Ups_3S", "@0+@1", ROOT.RooArgList(mean_1s, diff_3s))
    sigma_2s_1 = ROOT.RooFormulaVar("sigma_Ups_2S_1", "@0*@1/@2", ROOT.RooArgList(sigma_1s_1, mean_2s, mean_1s))
    sigma_2s_2 = ROOT.RooFormulaVar("sigma_Ups_2S_2", "@0*@1/@2", ROOT.RooArgList(sigma_1s_2, mean_2s, mean_1s))
    sigma_3s_1 = ROOT.RooFormulaVar("sigma_Ups_3S_1", "@0*@1/@2", ROOT.RooArgList(sigma_1s_1, mean_3s, mean_1s))
    sigma_3s_2 = ROOT.RooFormulaVar("sigma_Ups_3S_2", "@0*@1/@2", ROOT.RooArgList(sigma_1s_2, mean_3s, mean_1s))

    alpha_1 = ROOT.RooConstVar("alpha_1_Ups", "alpha_1_Ups", 2.8762)
    n_1 = ROOT.RooConstVar("n_1_Ups", "n_1_Ups", 0.061663)
    alpha_2 = ROOT.RooConstVar("alpha_2_Ups", "alpha_2_Ups", 4.8121e-01)
    n_2 = ROOT.RooConstVar("n_2_Ups", "n_2_Ups", 18.676)

    cb_1s_1 = ROOT.RooCBShape("cb_Ups_1S_1", "cb_Ups_1S_1", obs, mean_1s, sigma_1s_1, alpha_1, n_1)
    cb_1s_2 = ROOT.RooCBShape("cb_Ups_1S_2", "cb_Ups_1S_2", obs, mean_1s, sigma_1s_2, alpha_2, n_2)
    frac_cb = ROOT.RooConstVar("frac_cb_Ups", "frac_cb_Ups", 7.2778e-01)
    cb_1s = ROOT.RooAddPdf("cb_Ups_1S", "cb_Ups_1S", ROOT.RooArgList(cb_1s_1, cb_1s_2), ROOT.RooArgList(frac_cb))

    cb_2s_1 = ROOT.RooCBShape("cb_Ups_2S_1", "cb_Ups_2S_1", obs, mean_2s, sigma_2s_1, alpha_1, n_1)
    cb_2s_2 = ROOT.RooCBShape("cb_Ups_2S_2", "cb_Ups_2S_2", obs, mean_2s, sigma_2s_2, alpha_2, n_2)
    cb_2s = ROOT.RooAddPdf("cb_Ups_2S", "cb_Ups_2S", ROOT.RooArgList(cb_2s_1, cb_2s_2), ROOT.RooArgList(frac_cb))

    cb_3s_1 = ROOT.RooCBShape("cb_Ups_3S_1", "cb_Ups_3S_1", obs, mean_3s, sigma_3s_1, alpha_1, n_1)
    cb_3s_2 = ROOT.RooCBShape("cb_Ups_3S_2", "cb_Ups_3S_2", obs, mean_3s, sigma_3s_2, alpha_2, n_2)
    cb_3s = ROOT.RooAddPdf("cb_Ups_3S", "cb_Ups_3S", ROOT.RooArgList(cb_3s_1, cb_3s_2), ROOT.RooArgList(frac_cb))

    frac_1s = ROOT.RooRealVar("frac_1S", "frac_1S", 0.7, 0.0, 1.0)
    frac_2s = ROOT.RooRealVar("frac_2S", "frac_2S", 0.2, 0.0, 1.0)
    pdf = ROOT.RooAddPdf("signal_Ups", "signal_Ups", ROOT.RooArgList(cb_1s, cb_2s, cb_3s), ROOT.RooArgList(frac_1s, frac_2s))
    keep.extend([
        mean_1s, sigma_1s_1, sigma_1s_2, diff_2s, diff_3s, mean_2s, mean_3s,
        sigma_2s_1, sigma_2s_2, sigma_3s_1, sigma_3s_2, alpha_1, n_1, alpha_2, n_2,
        cb_1s_1, cb_1s_2, frac_cb, cb_1s, cb_2s_1, cb_2s_2, cb_2s, cb_3s_1, cb_3s_2, cb_3s,
        frac_1s, frac_2s, pdf,
    ])
    return pdf, keep


def build_ups_background(obs):
    c0 = ROOT.RooRealVar("ups_bkg_c0", "ups_bkg_c0", 0.0, -2.0, 2.0)
    c1 = ROOT.RooRealVar("ups_bkg_c1", "ups_bkg_c1", 0.0, -2.0, 2.0)
    c2 = ROOT.RooRealVar("ups_bkg_c2", "ups_bkg_c2", 0.0, -2.0, 2.0)
    pdf = ROOT.RooChebychev("ups_bkg", "ups_bkg", obs, ROOT.RooArgList(c0, c1, c2))
    return pdf, [c0, c1, c2, pdf]


def build_jjp_model(n_events: int):
    keep = []
    m_jpsi1 = ROOT.RooRealVar("sel_Jpsi_1_mass", "m(Jpsi1)", 2.9, 3.3)
    m_jpsi2 = ROOT.RooRealVar("sel_Jpsi_2_mass", "m(Jpsi2)", 2.9, 3.3)
    m_phi = ROOT.RooRealVar("sel_Phi_mass", "m(Phi)", 0.99, 1.07)
    keep.extend([m_jpsi1, m_jpsi2, m_phi])

    jpsi_alpha = ROOT.RooRealVar("jpsi_alpha", "jpsi_alpha", 1.5, 0.3, 5.0)
    jpsi_n = ROOT.RooRealVar("jpsi_n", "jpsi_n", 3.0, 0.5, 20.0)
    jpsi_frac_gauss = ROOT.RooRealVar("jpsi_frac_gauss", "jpsi_frac_gauss", 0.2, 0.0, 1.0)
    jpsi1_params = {
        "mean": ROOT.RooRealVar("jpsi1_mean", "jpsi1_mean", 3.096, 3.05, 3.15),
        "sigma_cb": ROOT.RooRealVar("jpsi1_sigma_cb", "jpsi1_sigma_cb", 0.025, 0.003, 0.08),
        "alpha": jpsi_alpha,
        "n": jpsi_n,
        "sigma_gauss": ROOT.RooRealVar("jpsi1_sigma_gauss", "jpsi1_sigma_gauss", 0.04, 0.003, 0.12),
        "frac_gauss": jpsi_frac_gauss,
    }
    jpsi2_params = {
        "mean": ROOT.RooRealVar("jpsi2_mean", "jpsi2_mean", 3.096, 3.05, 3.15),
        "sigma_cb": ROOT.RooRealVar("jpsi2_sigma_cb", "jpsi2_sigma_cb", 0.025, 0.003, 0.08),
        "alpha": jpsi_alpha,
        "n": jpsi_n,
        "sigma_gauss": ROOT.RooRealVar("jpsi2_sigma_gauss", "jpsi2_sigma_gauss", 0.04, 0.003, 0.12),
        "frac_gauss": jpsi_frac_gauss,
    }
    keep.extend([jpsi_alpha, jpsi_n, jpsi_frac_gauss])
    keep.extend(list(jpsi1_params.values()))
    keep.extend(list(jpsi2_params.values()))
    jpsi1_slope = ROOT.RooRealVar("jpsi1_bkg_slope", "jpsi1_bkg_slope", -2.0, -50.0, -0.001)
    jpsi2_slope = ROOT.RooRealVar("jpsi2_bkg_slope", "jpsi2_bkg_slope", -2.0, -50.0, -0.001)
    keep.extend([jpsi1_slope, jpsi2_slope])
    jpsi1_sig = build_jpsi_signal(m_jpsi1, "1", jpsi1_params, keep)
    jpsi2_sig = build_jpsi_signal(m_jpsi2, "2", jpsi2_params, keep)
    jpsi1_bkg = build_jpsi_background(m_jpsi1, "1", jpsi1_slope, keep)
    jpsi2_bkg = build_jpsi_background(m_jpsi2, "2", jpsi2_slope, keep)
    phi_sig, phi_keep = build_phi_signal(m_phi)
    phi_bkg, phi_bkg_keep = build_phi_background(m_phi)
    keep.extend(phi_keep.values())
    keep.extend(phi_bkg_keep.values())

    components = OrderedDict()
    components["yield_sss"] = ROOT.RooProdPdf("pdf_sss", "pdf_sss", ROOT.RooArgSet(jpsi1_sig, jpsi2_sig, phi_sig))
    components["yield_ssb"] = ROOT.RooProdPdf("pdf_ssb", "pdf_ssb", ROOT.RooArgSet(jpsi1_sig, jpsi2_sig, phi_bkg))
    components["yield_sbs"] = ROOT.RooProdPdf("pdf_sbs", "pdf_sbs", ROOT.RooArgSet(jpsi1_sig, jpsi2_bkg, phi_sig))
    components["yield_bss"] = ROOT.RooProdPdf("pdf_bss", "pdf_bss", ROOT.RooArgSet(jpsi1_bkg, jpsi2_sig, phi_sig))
    components["yield_sbb"] = ROOT.RooProdPdf("pdf_sbb", "pdf_sbb", ROOT.RooArgSet(jpsi1_sig, jpsi2_bkg, phi_bkg))
    components["yield_bsb"] = ROOT.RooProdPdf("pdf_bsb", "pdf_bsb", ROOT.RooArgSet(jpsi1_bkg, jpsi2_sig, phi_bkg))
    components["yield_bbs"] = ROOT.RooProdPdf("pdf_bbs", "pdf_bbs", ROOT.RooArgSet(jpsi1_bkg, jpsi2_bkg, phi_sig))
    components["yield_bbb"] = ROOT.RooProdPdf("pdf_bbb", "pdf_bbb", ROOT.RooArgSet(jpsi1_bkg, jpsi2_bkg, phi_bkg))

    yields = OrderedDict()
    init = [0.4, 0.1, 0.08, 0.08, 0.08, 0.08, 0.08, 0.1]
    for (yield_name, _), frac in zip(components.items(), init):
        yields[yield_name] = ROOT.RooRealVar(yield_name, yield_name, max(5.0, n_events * frac), 0.0, max(20.0, n_events * 1.5))
    keep.extend(list(components.values()))
    keep.extend(list(yields.values()))

    model = ROOT.RooAddPdf(
        "model_jjp",
        "model_jjp",
        ROOT.RooArgList(*components.values()),
        ROOT.RooArgList(*yields.values()),
    )
    keep.append(model)
    observables = OrderedDict([("sel_Jpsi_1_mass", m_jpsi1), ("sel_Jpsi_2_mass", m_jpsi2), ("sel_Phi_mass", m_phi)])
    return model, observables, yields, "yield_sss", keep


def build_jup_model(n_events: int):
    keep = []
    m_jpsi = ROOT.RooRealVar("sel_Jpsi_mass", "m(Jpsi)", 2.9, 3.3)
    m_ups = ROOT.RooRealVar("sel_Ups_mass", "m(Upsilon)", 8.5, 11.4)
    m_phi = ROOT.RooRealVar("sel_Phi_mass", "m(Phi)", 0.99, 1.07)
    keep.extend([m_jpsi, m_ups, m_phi])

    jpsi_shared = {
        "mean": ROOT.RooRealVar("jpsi_mean", "jpsi_mean", 3.096, 3.05, 3.15),
        "sigma_cb": ROOT.RooRealVar("jpsi_sigma_cb", "jpsi_sigma_cb", 0.025, 0.003, 0.08),
        "alpha": ROOT.RooRealVar("jpsi_alpha", "jpsi_alpha", 1.5, 0.3, 5.0),
        "n": ROOT.RooRealVar("jpsi_n", "jpsi_n", 3.0, 0.5, 20.0),
        "sigma_gauss": ROOT.RooRealVar("jpsi_sigma_gauss", "jpsi_sigma_gauss", 0.04, 0.003, 0.12),
        "frac_gauss": ROOT.RooRealVar("jpsi_frac_gauss", "jpsi_frac_gauss", 0.2, 0.0, 1.0),
    }
    keep.extend(list(jpsi_shared.values()))
    jpsi_slope = ROOT.RooRealVar("jpsi_bkg_slope", "jpsi_bkg_slope", -2.0, -50.0, -0.001)
    keep.append(jpsi_slope)
    jpsi_sig = build_jpsi_signal(m_jpsi, "main", jpsi_shared, keep)
    jpsi_bkg = build_jpsi_background(m_jpsi, "main", jpsi_slope, keep)
    ups_sig, ups_keep = build_ups_signal(m_ups)
    ups_bkg, ups_bkg_keep = build_ups_background(m_ups)
    phi_sig, phi_keep = build_phi_signal(m_phi)
    phi_bkg, phi_bkg_keep = build_phi_background(m_phi)
    keep.extend(ups_keep)
    keep.extend(ups_bkg_keep)
    keep.extend(phi_keep.values())
    keep.extend(phi_bkg_keep.values())

    components = OrderedDict()
    components["yield_sss"] = ROOT.RooProdPdf("pdf_sss", "pdf_sss", ROOT.RooArgSet(jpsi_sig, ups_sig, phi_sig))
    components["yield_ssb"] = ROOT.RooProdPdf("pdf_ssb", "pdf_ssb", ROOT.RooArgSet(jpsi_sig, ups_sig, phi_bkg))
    components["yield_sbs"] = ROOT.RooProdPdf("pdf_sbs", "pdf_sbs", ROOT.RooArgSet(jpsi_sig, ups_bkg, phi_sig))
    components["yield_bss"] = ROOT.RooProdPdf("pdf_bss", "pdf_bss", ROOT.RooArgSet(jpsi_bkg, ups_sig, phi_sig))
    components["yield_sbb"] = ROOT.RooProdPdf("pdf_sbb", "pdf_sbb", ROOT.RooArgSet(jpsi_sig, ups_bkg, phi_bkg))
    components["yield_bsb"] = ROOT.RooProdPdf("pdf_bsb", "pdf_bsb", ROOT.RooArgSet(jpsi_bkg, ups_sig, phi_bkg))
    components["yield_bbs"] = ROOT.RooProdPdf("pdf_bbs", "pdf_bbs", ROOT.RooArgSet(jpsi_bkg, ups_bkg, phi_sig))
    components["yield_bbb"] = ROOT.RooProdPdf("pdf_bbb", "pdf_bbb", ROOT.RooArgSet(jpsi_bkg, ups_bkg, phi_bkg))

    yields = OrderedDict()
    init = [0.5, 0.08, 0.08, 0.08, 0.06, 0.06, 0.06, 0.08]
    for (yield_name, _), frac in zip(components.items(), init):
        yields[yield_name] = ROOT.RooRealVar(yield_name, yield_name, max(5.0, n_events * frac), 0.0, max(20.0, n_events * 1.5))
    keep.extend(list(components.values()))
    keep.extend(list(yields.values()))

    model = ROOT.RooAddPdf(
        "model_jup",
        "model_jup",
        ROOT.RooArgList(*components.values()),
        ROOT.RooArgList(*yields.values()),
    )
    keep.append(model)
    observables = OrderedDict([("sel_Jpsi_mass", m_jpsi), ("sel_Ups_mass", m_ups), ("sel_Phi_mass", m_phi)])
    return model, observables, yields, "yield_sss", keep


def make_dataset(tree, observables):
    argset = ROOT.RooArgSet()
    for obs in observables.values():
        argset.add(obs)
    return ROOT.RooDataSet("data", "data", tree, argset)


def save_projection_plots(channel: str, plot_dir: str, data, model, observables, signal_yield_name: str):
    ensure_dir(plot_dir)
    background_components = ",".join(
        [name.replace("yield_", "pdf_") for name in ["yield_ssb", "yield_sbs", "yield_bss", "yield_sbb", "yield_bsb", "yield_bbs", "yield_bbb"]]
    )
    signal_component = signal_yield_name.replace("yield_", "pdf_")

    ROOT.gStyle.SetOptStat(0)
    ROOT.gROOT.SetBatch(True)
    for branch_name, obs in observables.items():
        canvas = ROOT.TCanvas(f"c_{branch_name}", branch_name, 800, 700)
        frame = obs.frame(ROOT.RooFit.Title(f"{channel} fit projection: {branch_name}"))
        data.plotOn(frame, ROOT.RooFit.Name("data"))
        model.plotOn(frame, ROOT.RooFit.Name("model"))
        model.plotOn(frame, ROOT.RooFit.Components(background_components), ROOT.RooFit.LineStyle(ROOT.kDashed), ROOT.RooFit.LineColor(ROOT.kBlue + 1))
        model.plotOn(frame, ROOT.RooFit.Components(signal_component), ROOT.RooFit.LineStyle(ROOT.kDashed), ROOT.RooFit.LineColor(ROOT.kRed + 1))
        frame.GetXaxis().SetTitle(branch_name)
        frame.Draw()
        canvas.SaveAs(os.path.join(plot_dir, f"{branch_name}_fit.pdf"))
        canvas.SaveAs(os.path.join(plot_dir, f"{branch_name}_fit.png"))


def clone_tree_with_weights(input_file: str, output_file: str, weight_map):
    ensure_parent_dir(output_file)
    fin = ROOT.TFile.Open(input_file)
    tree = fin.Get(INPUT_TREE)
    fout = ROOT.TFile(output_file, "RECREATE")
    out_tree = tree.CloneTree(0)

    branch_buffers = {}
    for name in weight_map:
        branch_buffers[name] = array.array("d", [0.0])
        out_tree.Branch(name, branch_buffers[name], f"{name}/D")

    for idx in range(tree.GetEntries()):
        tree.GetEntry(idx)
        for name, values in weight_map.items():
            branch_buffers[name][0] = float(values[idx])
        out_tree.Fill()

    out_tree.Write()
    fout.Close()
    fin.Close()


def compute_component_significance(
    model,
    data,
    yields,
    signal_yield_name: str,
    best_min_nll: float,
    jobs: int = 1,
    strategy: int = 1,
    print_level: int = -1,
):
    signal_var = yields[signal_yield_name]
    signal = max(0.0, signal_var.getVal())
    background = sum(max(0.0, var.getVal()) for name, var in yields.items() if name != signal_yield_name)

    params = model.getParameters(data)
    snapshot = params.snapshot()
    signal_is_constant = signal_var.isConstant()

    signal_var.setVal(0.0)
    signal_var.setConstant(True)
    null_fit = model.fitTo(
        data,
        ROOT.RooFit.Extended(True),
        ROOT.RooFit.Save(True),
        ROOT.RooFit.NumCPU(max(1, jobs)),
        ROOT.RooFit.Strategy(strategy),
        ROOT.RooFit.PrintLevel(print_level),
    )

    q0 = max(0.0, 2.0 * (null_fit.minNll() - best_min_nll))

    if snapshot is not None:
        params.assignValueOnly(snapshot)
    signal_var.setConstant(signal_is_constant)

    return {
        "signal_yield": signal,
        "background_yield": background,
        "q0": q0,
        "lrt_significance": math.sqrt(q0),
        "null_fit_result": null_fit,
    }


def save_significance_to_root(fout, signal_yield_name: str, significance):
    ROOT.TNamed("signal_component", signal_yield_name).Write()
    ROOT.TParameter("double")("signal_yield", float(significance["signal_yield"])).Write()
    ROOT.TParameter("double")("background_yield", float(significance["background_yield"])).Write()
    ROOT.TParameter("double")("q0_lrt", float(significance["q0"])).Write()
    ROOT.TParameter("double")("lrt_significance", float(significance["lrt_significance"])).Write()
    significance["null_fit_result"].Write("null_fit_result")


def main():
    args = parse_args()
    channel = normalize_channel(args.channel)
    dataset = normalize_dataset(args.dataset)
    sample = normalize_sample(channel, args.sample) if dataset == "mc" else None

    input_file = args.input or default_merged_output(channel, dataset, sample)
    output_file = args.output or default_weighted_output(channel, dataset, sample)
    plot_dir = args.plot_dir or os.path.join(default_plot_dir(channel, dataset, sample), "fit")
    ensure_parent_dir(output_file)
    ensure_dir(plot_dir)

    summary = uproot.open(input_file)[INPUT_TREE]
    n_entries = summary.num_entries
    print("=" * 80)
    print("assocPV sPlot fit")
    print("=" * 80)
    print(f"[INFO] channel    : {channel}")
    print(f"[INFO] dataset    : {dataset}")
    print(f"[INFO] sample     : {sample or '-'}")
    print(f"[INFO] input      : {input_file}")
    print(f"[INFO] output     : {output_file}")
    print(f"[INFO] plot dir   : {plot_dir}")
    print(f"[INFO] entries    : {n_entries}")
    print("=" * 80)

    ROOT.gROOT.SetBatch(True)
    ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.WARNING)
    fin = ROOT.TFile.Open(input_file)
    tree = fin.Get(INPUT_TREE)

    if channel == "JJP":
        model, observables, yields, signal_yield_name, keepalive = build_jjp_model(n_entries)
    else:
        model, observables, yields, signal_yield_name, keepalive = build_jup_model(n_entries)

    data = make_dataset(tree, observables)
    keepalive.append(data)
    fit_result = model.fitTo(
        data,
        ROOT.RooFit.Extended(True),
        ROOT.RooFit.Save(True),
        ROOT.RooFit.NumCPU(max(1, args.jobs)),
        ROOT.RooFit.Strategy(1),
        ROOT.RooFit.PrintLevel(-1),
    )
    keepalive.append(fit_result)

    save_projection_plots(channel, plot_dir, data, model, observables, signal_yield_name)
    sdata = ROOT.RooStats.SPlot("sData", "sData", data, model, ROOT.RooArgList(*yields.values()))
    keepalive.append(sdata)

    weight_map = OrderedDict()
    for yield_name in yields:
        weight_map[f"{yield_name}_sw"] = [data.get(i).getRealValue(f"{yield_name}_sw") for i in range(data.numEntries())]
    weight_map["signal_sw"] = list(weight_map[f"{signal_yield_name}_sw"])

    significance = compute_component_significance(
        model,
        data,
        yields,
        signal_yield_name,
        best_min_nll=fit_result.minNll(),
        jobs=args.jobs,
        strategy=1,
        print_level=-1,
    )
    keepalive.append(significance["null_fit_result"])

    clone_tree_with_weights(input_file, output_file, weight_map)
    fit_out = ROOT.TFile(output_file.replace(".root", "_fit_result.root"), "RECREATE")
    fit_result.Write("fit_result")
    save_significance_to_root(fit_out, signal_yield_name, significance)
    fit_out.Close()
    fin.Close()

    print(f"[INFO] fitted dataset entries : {data.numEntries()}")
    print(f"[INFO] signal yield           : {yields[signal_yield_name].getVal():.2f}")
    print(f"[INFO] background yield       : {significance['background_yield']:.2f}")
    print(f"[INFO] signal component       : {signal_yield_name}")
    print(f"[INFO] q0 (LRT, sss only)    : {significance['q0']:.3f}")
    print(f"[INFO] significance (LRT)    : {significance['lrt_significance']:.3f}")
    print(f"[INFO] weights saved         : {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

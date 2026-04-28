#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ntuple分析结果绘图脚本

绘制JJP和JUP角度关联分析的结果图

使用方法:
    python plot_ntuple_results.py -i output.root -o plots/ -p JJP
    python plot_ntuple_results.py -i output.root -o plots/ -p JUP
"""

import ROOT
import os
import sys
import argparse

# 设置ROOT样式
ROOT.gROOT.SetBatch(True)
ROOT.gStyle.SetOptStat(0)
ROOT.gStyle.SetOptTitle(1)
ROOT.gStyle.SetPadLeftMargin(0.12)
ROOT.gStyle.SetPadRightMargin(0.15)
ROOT.gStyle.SetPadBottomMargin(0.12)
ROOT.gStyle.SetPadTopMargin(0.08)
ROOT.gStyle.SetTitleOffset(1.2, "X")
ROOT.gStyle.SetTitleOffset(1.4, "Y")
ROOT.gStyle.SetPalette(ROOT.kViridis)


def plot_1d_comparison(fin, hist_names, labels, colors, output_name, title, xlabel, ylabel="Events", logy=False):
    """在同一画布上绘制多个1D直方图"""
    c = ROOT.TCanvas("c", "", 800, 600)
    c.SetLogy(logy)
    
    legend = ROOT.TLegend(0.60, 0.70, 0.88, 0.88)
    legend.SetBorderSize(0)
    legend.SetFillStyle(0)
    legend.SetTextSize(0.035)
    
    max_val = 0
    hists = []
    
    for i, (hname, label, color) in enumerate(zip(hist_names, labels, colors)):
        h = fin.Get(hname)
        if not h:
            print(f"Warning: histogram {hname} not found")
            continue
        
        h.SetLineColor(color)
        h.SetLineWidth(2)
        h.SetMarkerColor(color)
        h.SetMarkerStyle(20 + i)
        
        max_val = max(max_val, h.GetMaximum())
        hists.append((h, label))
    
    if not hists:
        return
    
    # 绘制
    first = True
    for h, label in hists:
        if logy:
            h.SetMaximum(max_val * 5)
            h.SetMinimum(0.5)
        else:
            h.SetMaximum(max_val * 1.3)
            h.SetMinimum(0)
        h.GetXaxis().SetTitle(xlabel)
        h.GetYaxis().SetTitle(ylabel)
        h.SetTitle(title)
        
        if first:
            h.Draw("HIST E")
            first = False
        else:
            h.Draw("HIST E SAME")
        
        legend.AddEntry(h, label, "l")
    
    legend.Draw()
    
    c.SaveAs(output_name + ".pdf")
    c.SaveAs(output_name + ".png")
    print(f"Saved: {output_name}.pdf/.png")


def plot_2d(fin, hist_name, output_name, title):
    """绘制2D直方图"""
    c = ROOT.TCanvas("c2d", "", 800, 700)
    c.SetLogz(0)
    
    h = fin.Get(hist_name)
    if not h:
        print(f"Warning: histogram {hist_name} not found")
        return
    
    h.SetTitle(title)
    h.GetXaxis().SetTitle("|#Delta y|")
    h.GetYaxis().SetTitle("|#Delta#phi|")
    h.GetZaxis().SetTitle("Events")
    
    h.Draw("COLZ")
    
    c.SaveAs(output_name + ".pdf")
    c.SaveAs(output_name + ".png")
    print(f"Saved: {output_name}.pdf/.png")


def plot_2d_all_jjp(fin, output_dir, process):
    """绘制JJP的三个2D关联图"""
    c = ROOT.TCanvas("c2d_all", "", 1800, 500)
    c.Divide(3, 1)
    
    hist_names = ["h2_dy_dphi_jpsi1_jpsi2", "h2_dy_dphi_jpsi1_phi", "h2_dy_dphi_jpsi2_phi"]
    titles = ["J/#psi_{1} - J/#psi_{2}", "J/#psi_{1} - #phi", "J/#psi_{2} - #phi"]
    
    for i, (hname, title) in enumerate(zip(hist_names, titles)):
        c.cd(i + 1)
        ROOT.gPad.SetRightMargin(0.15)
        ROOT.gPad.SetLeftMargin(0.12)
        
        h = fin.Get(hname)
        if not h:
            print(f"Warning: histogram {hname} not found")
            continue
        
        h.SetTitle(f"{title} ({process})")
        h.GetXaxis().SetTitle("|#Delta y|")
        h.GetYaxis().SetTitle("|#Delta#phi|")
        h.Draw("COLZ")
    
    output_name = os.path.join(output_dir, f"correlation_2d_all_{process}")
    c.SaveAs(output_name + ".pdf")
    c.SaveAs(output_name + ".png")
    print(f"Saved: {output_name}.pdf/.png")


def plot_2d_all_jup(fin, output_dir, process):
    """绘制JUP的三个2D关联图"""
    c = ROOT.TCanvas("c2d_all", "", 1800, 500)
    c.Divide(3, 1)
    
    hist_names = ["h2_dy_dphi_jpsi_ups", "h2_dy_dphi_jpsi_phi", "h2_dy_dphi_ups_phi"]
    titles = ["J/#psi - #Upsilon", "J/#psi - #phi", "#Upsilon - #phi"]
    
    for i, (hname, title) in enumerate(zip(hist_names, titles)):
        c.cd(i + 1)
        ROOT.gPad.SetRightMargin(0.15)
        ROOT.gPad.SetLeftMargin(0.12)
        
        h = fin.Get(hname)
        if not h:
            print(f"Warning: histogram {hname} not found")
            continue
        
        h.SetTitle(f"{title} ({process})")
        h.GetXaxis().SetTitle("|#Delta y|")
        h.GetYaxis().SetTitle("|#Delta#phi|")
        h.Draw("COLZ")
    
    output_name = os.path.join(output_dir, f"correlation_2d_all_{process}")
    c.SaveAs(output_name + ".pdf")
    c.SaveAs(output_name + ".png")
    print(f"Saved: {output_name}.pdf/.png")


JJY_VERTEX_CATEGORIES = [
    ("no_vertex", "No further vertexing selection"),
    ("pri_valid", "Pri vertex valid"),
    ("pri_vtxprob_gt_0p005", "Pri VtxProb > 0.005"),
    ("same_mu_vertex", "All 6 muons same vertex"),
]


def jjy_h(category, stem):
    return f"h_{category}_{stem}"


def jjy_h2(category, stem):
    return f"h2_{category}_{stem}"


def plot_2d_all_jjy(fin, output_dir, process, category, category_title):
    """绘制JJY的三个2D关联图"""
    c = ROOT.TCanvas(f"c2d_all_{category}", "", 1800, 500)
    c.Divide(3, 1)

    hist_names = [
        jjy_h2(category, "dy_dphi_jpsi1_jpsi2"),
        jjy_h2(category, "dy_dphi_jpsi1_ups"),
        jjy_h2(category, "dy_dphi_jpsi2_ups"),
    ]
    titles = ["J/#psi_{1} - J/#psi_{2}", "J/#psi_{1} - #Upsilon", "J/#psi_{2} - #Upsilon"]

    for i, (hname, title) in enumerate(zip(hist_names, titles)):
        c.cd(i + 1)
        ROOT.gPad.SetRightMargin(0.15)
        ROOT.gPad.SetLeftMargin(0.12)

        h = fin.Get(hname)
        if not h:
            print(f"Warning: histogram {hname} not found")
            continue

        h.SetTitle(f"{title} ({process}, {category_title})")
        h.GetXaxis().SetTitle("|#Delta y|")
        h.GetYaxis().SetTitle("|#Delta#phi|")
        h.Draw("COLZ")

    output_name = os.path.join(output_dir, f"correlation_2d_all_{process}_{category}")
    c.SaveAs(output_name + ".pdf")
    c.SaveAs(output_name + ".png")
    print(f"Saved: {output_name}.pdf/.png")


def plot_jjy_kinematic_quantity(fin, output_dir, process, category, category_title, quantity, xlabel):
    c = ROOT.TCanvas(f"c_{category}_{quantity}", "", 800, 600)
    legend = ROOT.TLegend(0.60, 0.70, 0.88, 0.88)
    legend.SetBorderSize(0)
    legend.SetFillStyle(0)
    legend.SetTextSize(0.035)

    specs = [
        (jjy_h(category, f"jpsi1_{quantity}"), "J/#psi_{1}", ROOT.kRed),
        (jjy_h(category, f"jpsi2_{quantity}"), "J/#psi_{2}", ROOT.kBlue),
        (jjy_h(category, f"ups_{quantity}"), "#Upsilon", ROOT.kGreen + 2),
    ]
    hists = []
    max_val = 0
    for hname, label, color in specs:
        h = fin.Get(hname)
        if not h:
            print(f"Warning: histogram {hname} not found")
            continue
        h.SetLineColor(color)
        h.SetLineWidth(2)
        max_val = max(max_val, h.GetMaximum())
        hists.append((h, label))

    if not hists:
        return

    first = True
    for h, label in hists:
        h.SetMaximum(max_val * 1.3 if max_val > 0 else 1)
        h.SetMinimum(0)
        h.SetTitle(f"{xlabel} Distributions ({process}, {category_title})")
        h.GetXaxis().SetTitle(xlabel)
        h.GetYaxis().SetTitle("Events")
        h.Draw("HIST" if first else "HIST SAME")
        legend.AddEntry(h, label, "l")
        first = False

    legend.Draw()
    output_name = os.path.join(output_dir, f"{quantity}_distributions_{process}_{category}")
    c.SaveAs(output_name + ".pdf")
    c.SaveAs(output_name + ".png")
    print(f"Saved: {output_name}.pdf/.png")


def plot_kinematics_jjy(fin, output_dir, process, category, category_title):
    plot_jjy_kinematic_quantity(fin, output_dir, process, category, category_title, "pt", "p_{T} [GeV]")
    plot_jjy_kinematic_quantity(fin, output_dir, process, category, category_title, "eta", "#eta")
    plot_jjy_kinematic_quantity(fin, output_dir, process, category, category_title, "y", "y")
    plot_jjy_kinematic_quantity(fin, output_dir, process, category, category_title, "phi", "#phi")


def plot_resonance_mass_jjy(fin, output_dir, process, category, category_title):
    """绘制JJY的m(mumu)共振质量谱。"""
    c = ROOT.TCanvas(f"c_res_mass_{category}", "", 1200, 600)
    c.Divide(2, 1)

    c.cd(1)
    ROOT.gPad.SetLeftMargin(0.12)
    ROOT.gPad.SetRightMargin(0.05)
    legend = ROOT.TLegend(0.58, 0.70, 0.88, 0.88)
    legend.SetBorderSize(0)
    legend.SetFillStyle(0)
    legend.SetTextSize(0.035)

    jpsi_specs = [
        (jjy_h(category, "jpsi1_mass"), "J/#psi_{1}", ROOT.kRed),
        (jjy_h(category, "jpsi2_mass"), "J/#psi_{2}", ROOT.kBlue),
        (jjy_h(category, "jpsi_mass_all"), "J/#psi_{1}+J/#psi_{2}", ROOT.kBlack),
    ]
    jpsi_hists = []
    max_val = 0
    for hname, label, color in jpsi_specs:
        h = fin.Get(hname)
        if not h:
            print(f"Warning: histogram {hname} not found")
            continue
        h.SetLineColor(color)
        h.SetLineWidth(2)
        if label == "J/#psi_{1}+J/#psi_{2}":
            h.SetLineStyle(2)
        max_val = max(max_val, h.GetMaximum())
        jpsi_hists.append((h, label))

    first = True
    for h, label in jpsi_hists:
        h.SetMaximum(max_val * 1.3 if max_val > 0 else 1)
        h.SetMinimum(0)
        h.SetTitle(f"J/#psi m(#mu#mu) ({process}, {category_title})")
        h.GetXaxis().SetTitle("m(#mu#mu) [GeV]")
        h.GetYaxis().SetTitle("Candidates")
        h.Draw("HIST" if first else "HIST SAME")
        legend.AddEntry(h, label, "l")
        first = False
    if jpsi_hists:
        legend.Draw()

    c.cd(2)
    ROOT.gPad.SetLeftMargin(0.12)
    ROOT.gPad.SetRightMargin(0.05)
    h_ups = fin.Get(jjy_h(category, "ups_mass"))
    if not h_ups:
        print(f"Warning: histogram {jjy_h(category, 'ups_mass')} not found")
    else:
        h_ups.SetLineColor(ROOT.kGreen + 2)
        h_ups.SetLineWidth(2)
        h_ups.SetMinimum(0)
        h_ups.SetMaximum(h_ups.GetMaximum() * 1.3 if h_ups.GetMaximum() > 0 else 1)
        h_ups.SetTitle(f"#Upsilon(1S) m(#mu#mu) ({process}, {category_title})")
        h_ups.GetXaxis().SetTitle("m(#mu#mu) [GeV]")
        h_ups.GetYaxis().SetTitle("Candidates")
        h_ups.Draw("HIST")

    output_name = os.path.join(output_dir, f"resonance_mass_{process}_{category}")
    c.SaveAs(output_name + ".pdf")
    c.SaveAs(output_name + ".png")
    print(f"Saved: {output_name}.pdf/.png")


def plot_invariant_mass_jjy(fin, output_dir, process, category, category_title):
    c = ROOT.TCanvas(f"c_mass_{category}", "", 1800, 800)
    c.Divide(3, 2)

    mass_hists = [
        (jjy_h(category, "mass_jpsi1_jpsi2"), "M(J/#psi_{1} + J/#psi_{2})"),
        (jjy_h(category, "mass_jpsi1_ups"), "M(J/#psi_{1} + #Upsilon)"),
        (jjy_h(category, "mass_jpsi2_ups"), "M(J/#psi_{2} + #Upsilon)"),
        (jjy_h(category, "mass_all"), "M(J/#psi_{1} + J/#psi_{2} + #Upsilon)"),
        (jjy_h(category, "pri_mass"), "Pri fit mass"),
        (jjy_h(category, "pri_vtxprob"), "Pri VtxProb"),
    ]

    for i, (hname, title) in enumerate(mass_hists):
        c.cd(i + 1)
        ROOT.gPad.SetLeftMargin(0.12)
        ROOT.gPad.SetRightMargin(0.05)

        h = fin.Get(hname)
        if not h:
            print(f"Warning: histogram {hname} not found")
            continue

        h.SetLineColor(ROOT.kBlue)
        h.SetLineWidth(2)
        h.SetTitle(f"{title} ({process}, {category_title})")
        h.GetYaxis().SetTitle("Events")
        h.SetMinimum(0)
        h.Draw("HIST")

    output_name = os.path.join(output_dir, f"invariant_mass_{process}_{category}")
    c.SaveAs(output_name + ".pdf")
    c.SaveAs(output_name + ".png")
    print(f"Saved: {output_name}.pdf/.png")


def plot_jjy_category(fin, output_dir, process, category, category_title):
    category_dir = os.path.join(output_dir, category)
    os.makedirs(category_dir, exist_ok=True)

    plot_1d_comparison(
        fin,
        [jjy_h(category, "dy_jpsi1_jpsi2"), jjy_h(category, "dy_jpsi1_ups"), jjy_h(category, "dy_jpsi2_ups")],
        ["J/#psi_{1} - J/#psi_{2}", "J/#psi_{1} - #Upsilon", "J/#psi_{2} - #Upsilon"],
        [ROOT.kRed, ROOT.kBlue, ROOT.kGreen + 2],
        os.path.join(category_dir, f"delta_y_comparison_{process}_{category}"),
        f"#Delta y Distributions ({process}, {category_title})",
        "|#Delta y|",
    )

    plot_1d_comparison(
        fin,
        [jjy_h(category, "dphi_jpsi1_jpsi2"), jjy_h(category, "dphi_jpsi1_ups"), jjy_h(category, "dphi_jpsi2_ups")],
        ["J/#psi_{1} - J/#psi_{2}", "J/#psi_{1} - #Upsilon", "J/#psi_{2} - #Upsilon"],
        [ROOT.kRed, ROOT.kBlue, ROOT.kGreen + 2],
        os.path.join(category_dir, f"delta_phi_comparison_{process}_{category}"),
        f"#Delta#phi Distributions ({process}, {category_title})",
        "|#Delta#phi|",
    )

    plot_2d(fin, jjy_h2(category, "dy_dphi_jpsi1_jpsi2"),
            os.path.join(category_dir, f"correlation_2d_jpsi1_jpsi2_{process}_{category}"),
            f"J/#psi_{{1}} - J/#psi_{{2}}: #Delta y vs #Delta#phi ({process}, {category_title})")
    plot_2d(fin, jjy_h2(category, "dy_dphi_jpsi1_ups"),
            os.path.join(category_dir, f"correlation_2d_jpsi1_ups_{process}_{category}"),
            f"J/#psi_{{1}} - #Upsilon: #Delta y vs #Delta#phi ({process}, {category_title})")
    plot_2d(fin, jjy_h2(category, "dy_dphi_jpsi2_ups"),
            os.path.join(category_dir, f"correlation_2d_jpsi2_ups_{process}_{category}"),
            f"J/#psi_{{2}} - #Upsilon: #Delta y vs #Delta#phi ({process}, {category_title})")

    plot_2d_all_jjy(fin, category_dir, process, category, category_title)
    plot_kinematics_jjy(fin, category_dir, process, category, category_title)
    plot_resonance_mass_jjy(fin, category_dir, process, category, category_title)
    plot_invariant_mass_jjy(fin, category_dir, process, category, category_title)


def plot_jjy(fin, output_dir, process):
    """绘制JJY四套vertexing选择图"""
    for category, category_title in JJY_VERTEX_CATEGORIES:
        plot_jjy_category(fin, output_dir, process, category, category_title)


def plot_kinematics_jjp(fin, output_dir, process):
    """绘制JJP运动学分布"""
    # pT分布
    c = ROOT.TCanvas("c_pt", "", 800, 600)
    
    legend = ROOT.TLegend(0.60, 0.70, 0.88, 0.88)
    legend.SetBorderSize(0)
    legend.SetFillStyle(0)
    legend.SetTextSize(0.035)
    
    h_jpsi1_pt = fin.Get("h_jpsi1_pt")
    h_jpsi2_pt = fin.Get("h_jpsi2_pt")
    h_phi_pt = fin.Get("h_phi_pt")
    
    if h_jpsi1_pt and h_jpsi2_pt and h_phi_pt:
        h_jpsi1_pt.SetLineColor(ROOT.kRed)
        h_jpsi2_pt.SetLineColor(ROOT.kBlue)
        h_phi_pt.SetLineColor(ROOT.kGreen + 2)
        
        for h in [h_jpsi1_pt, h_jpsi2_pt, h_phi_pt]:
            h.SetLineWidth(2)
        
        max_val = max(h_jpsi1_pt.GetMaximum(), h_jpsi2_pt.GetMaximum(), h_phi_pt.GetMaximum())
        h_jpsi1_pt.SetMaximum(max_val * 1.3)
        h_jpsi1_pt.SetMinimum(0)
        h_jpsi1_pt.SetTitle(f"Transverse Momentum Distributions ({process})")
        h_jpsi1_pt.GetXaxis().SetTitle("p_{T} [GeV]")
        h_jpsi1_pt.GetYaxis().SetTitle("Events")
        
        h_jpsi1_pt.Draw("HIST")
        h_jpsi2_pt.Draw("HIST SAME")
        h_phi_pt.Draw("HIST SAME")
        
        legend.AddEntry(h_jpsi1_pt, "J/#psi_{1}", "l")
        legend.AddEntry(h_jpsi2_pt, "J/#psi_{2}", "l")
        legend.AddEntry(h_phi_pt, "#phi", "l")
        legend.Draw()
        
        output_name = os.path.join(output_dir, f"pt_distributions_{process}")
        c.SaveAs(output_name + ".pdf")
        c.SaveAs(output_name + ".png")
        print(f"Saved: {output_name}.pdf/.png")
    
    # η分布
    c2 = ROOT.TCanvas("c_eta", "", 800, 600)
    legend2 = ROOT.TLegend(0.60, 0.70, 0.88, 0.88)
    legend2.SetBorderSize(0)
    legend2.SetFillStyle(0)
    legend2.SetTextSize(0.035)
    
    h_jpsi1_eta = fin.Get("h_jpsi1_eta")
    h_jpsi2_eta = fin.Get("h_jpsi2_eta")
    h_phi_eta = fin.Get("h_phi_eta")
    
    if h_jpsi1_eta and h_jpsi2_eta and h_phi_eta:
        h_jpsi1_eta.SetLineColor(ROOT.kRed)
        h_jpsi2_eta.SetLineColor(ROOT.kBlue)
        h_phi_eta.SetLineColor(ROOT.kGreen + 2)
        
        for h in [h_jpsi1_eta, h_jpsi2_eta, h_phi_eta]:
            h.SetLineWidth(2)
        
        max_val = max(h_jpsi1_eta.GetMaximum(), h_jpsi2_eta.GetMaximum(), h_phi_eta.GetMaximum())
        h_jpsi1_eta.SetMaximum(max_val * 1.3)
        h_jpsi1_eta.SetMinimum(0)
        h_jpsi1_eta.SetTitle(f"Pseudorapidity Distributions ({process})")
        h_jpsi1_eta.GetXaxis().SetTitle("#eta")
        h_jpsi1_eta.GetYaxis().SetTitle("Events")
        
        h_jpsi1_eta.Draw("HIST")
        h_jpsi2_eta.Draw("HIST SAME")
        h_phi_eta.Draw("HIST SAME")
        
        legend2.AddEntry(h_jpsi1_eta, "J/#psi_{1}", "l")
        legend2.AddEntry(h_jpsi2_eta, "J/#psi_{2}", "l")
        legend2.AddEntry(h_phi_eta, "#phi", "l")
        legend2.Draw()
        
        output_name = os.path.join(output_dir, f"eta_distributions_{process}")
        c2.SaveAs(output_name + ".pdf")
        c2.SaveAs(output_name + ".png")
        print(f"Saved: {output_name}.pdf/.png")
    
    # 快度分布
    c3 = ROOT.TCanvas("c_y", "", 800, 600)
    legend3 = ROOT.TLegend(0.60, 0.70, 0.88, 0.88)
    legend3.SetBorderSize(0)
    legend3.SetFillStyle(0)
    legend3.SetTextSize(0.035)
    
    h_jpsi1_y = fin.Get("h_jpsi1_y")
    h_jpsi2_y = fin.Get("h_jpsi2_y")
    h_phi_y = fin.Get("h_phi_y")
    
    if h_jpsi1_y and h_jpsi2_y and h_phi_y:
        h_jpsi1_y.SetLineColor(ROOT.kRed)
        h_jpsi2_y.SetLineColor(ROOT.kBlue)
        h_phi_y.SetLineColor(ROOT.kGreen + 2)
        
        for h in [h_jpsi1_y, h_jpsi2_y, h_phi_y]:
            h.SetLineWidth(2)
        
        max_val = max(h_jpsi1_y.GetMaximum(), h_jpsi2_y.GetMaximum(), h_phi_y.GetMaximum())
        h_jpsi1_y.SetMaximum(max_val * 1.3)
        h_jpsi1_y.SetMinimum(0)
        h_jpsi1_y.SetTitle(f"Rapidity Distributions ({process})")
        h_jpsi1_y.GetXaxis().SetTitle("y")
        h_jpsi1_y.GetYaxis().SetTitle("Events")
        
        h_jpsi1_y.Draw("HIST")
        h_jpsi2_y.Draw("HIST SAME")
        h_phi_y.Draw("HIST SAME")
        
        legend3.AddEntry(h_jpsi1_y, "J/#psi_{1}", "l")
        legend3.AddEntry(h_jpsi2_y, "J/#psi_{2}", "l")
        legend3.AddEntry(h_phi_y, "#phi", "l")
        legend3.Draw()
        
        output_name = os.path.join(output_dir, f"rapidity_distributions_{process}")
        c3.SaveAs(output_name + ".pdf")
        c3.SaveAs(output_name + ".png")
        print(f"Saved: {output_name}.pdf/.png")
    
    # φ (方位角) 分布
    c4 = ROOT.TCanvas("c_phi", "", 800, 600)
    legend4 = ROOT.TLegend(0.60, 0.70, 0.88, 0.88)
    legend4.SetBorderSize(0)
    legend4.SetFillStyle(0)
    legend4.SetTextSize(0.035)
    
    h_jpsi1_phi = fin.Get("h_jpsi1_phi")
    h_jpsi2_phi = fin.Get("h_jpsi2_phi")
    h_phi_phi = fin.Get("h_phi_phi")
    
    if h_jpsi1_phi and h_jpsi2_phi and h_phi_phi:
        h_jpsi1_phi.SetLineColor(ROOT.kRed)
        h_jpsi2_phi.SetLineColor(ROOT.kBlue)
        h_phi_phi.SetLineColor(ROOT.kGreen + 2)
        
        for h in [h_jpsi1_phi, h_jpsi2_phi, h_phi_phi]:
            h.SetLineWidth(2)
        
        max_val = max(h_jpsi1_phi.GetMaximum(), h_jpsi2_phi.GetMaximum(), h_phi_phi.GetMaximum())
        h_jpsi1_phi.SetMaximum(max_val * 1.3)
        h_jpsi1_phi.SetMinimum(0)
        h_jpsi1_phi.SetTitle(f"Azimuthal Angle Distributions ({process})")
        h_jpsi1_phi.GetXaxis().SetTitle("#phi")
        h_jpsi1_phi.GetYaxis().SetTitle("Events")
        
        h_jpsi1_phi.Draw("HIST")
        h_jpsi2_phi.Draw("HIST SAME")
        h_phi_phi.Draw("HIST SAME")
        
        legend4.AddEntry(h_jpsi1_phi, "J/#psi_{1}", "l")
        legend4.AddEntry(h_jpsi2_phi, "J/#psi_{2}", "l")
        legend4.AddEntry(h_phi_phi, "#phi", "l")
        legend4.Draw()
        
        output_name = os.path.join(output_dir, f"phi_distributions_{process}")
        c4.SaveAs(output_name + ".pdf")
        c4.SaveAs(output_name + ".png")
        print(f"Saved: {output_name}.pdf/.png")


def plot_kinematics_jup(fin, output_dir, process):
    """绘制JUP运动学分布"""
    # pT分布
    c = ROOT.TCanvas("c_pt", "", 800, 600)
    
    legend = ROOT.TLegend(0.60, 0.70, 0.88, 0.88)
    legend.SetBorderSize(0)
    legend.SetFillStyle(0)
    legend.SetTextSize(0.035)
    
    h_jpsi_pt = fin.Get("h_jpsi_pt")
    h_ups_pt = fin.Get("h_ups_pt")
    h_phi_pt = fin.Get("h_phi_pt")
    
    if h_jpsi_pt and h_ups_pt and h_phi_pt:
        h_jpsi_pt.SetLineColor(ROOT.kRed)
        h_ups_pt.SetLineColor(ROOT.kBlue)
        h_phi_pt.SetLineColor(ROOT.kGreen + 2)
        
        for h in [h_jpsi_pt, h_ups_pt, h_phi_pt]:
            h.SetLineWidth(2)
        
        max_val = max(h_jpsi_pt.GetMaximum(), h_ups_pt.GetMaximum(), h_phi_pt.GetMaximum())
        h_jpsi_pt.SetMaximum(max_val * 1.3)
        h_jpsi_pt.SetMinimum(0)
        h_jpsi_pt.SetTitle(f"Transverse Momentum Distributions ({process})")
        h_jpsi_pt.GetXaxis().SetTitle("p_{T} [GeV]")
        h_jpsi_pt.GetYaxis().SetTitle("Events")
        
        h_jpsi_pt.Draw("HIST")
        h_ups_pt.Draw("HIST SAME")
        h_phi_pt.Draw("HIST SAME")
        
        legend.AddEntry(h_jpsi_pt, "J/#psi", "l")
        legend.AddEntry(h_ups_pt, "#Upsilon", "l")
        legend.AddEntry(h_phi_pt, "#phi", "l")
        legend.Draw()
        
        output_name = os.path.join(output_dir, f"pt_distributions_{process}")
        c.SaveAs(output_name + ".pdf")
        c.SaveAs(output_name + ".png")
        print(f"Saved: {output_name}.pdf/.png")
    
    # η分布
    c2 = ROOT.TCanvas("c_eta", "", 800, 600)
    legend2 = ROOT.TLegend(0.60, 0.70, 0.88, 0.88)
    legend2.SetBorderSize(0)
    legend2.SetFillStyle(0)
    legend2.SetTextSize(0.035)
    
    h_jpsi_eta = fin.Get("h_jpsi_eta")
    h_ups_eta = fin.Get("h_ups_eta")
    h_phi_eta = fin.Get("h_phi_eta")
    
    if h_jpsi_eta and h_ups_eta and h_phi_eta:
        h_jpsi_eta.SetLineColor(ROOT.kRed)
        h_ups_eta.SetLineColor(ROOT.kBlue)
        h_phi_eta.SetLineColor(ROOT.kGreen + 2)
        
        for h in [h_jpsi_eta, h_ups_eta, h_phi_eta]:
            h.SetLineWidth(2)
        
        max_val = max(h_jpsi_eta.GetMaximum(), h_ups_eta.GetMaximum(), h_phi_eta.GetMaximum())
        h_jpsi_eta.SetMaximum(max_val * 1.3)
        h_jpsi_eta.SetMinimum(0)
        h_jpsi_eta.SetTitle(f"Pseudorapidity Distributions ({process})")
        h_jpsi_eta.GetXaxis().SetTitle("#eta")
        h_jpsi_eta.GetYaxis().SetTitle("Events")
        
        h_jpsi_eta.Draw("HIST")
        h_ups_eta.Draw("HIST SAME")
        h_phi_eta.Draw("HIST SAME")
        
        legend2.AddEntry(h_jpsi_eta, "J/#psi", "l")
        legend2.AddEntry(h_ups_eta, "#Upsilon", "l")
        legend2.AddEntry(h_phi_eta, "#phi", "l")
        legend2.Draw()
        
        output_name = os.path.join(output_dir, f"eta_distributions_{process}")
        c2.SaveAs(output_name + ".pdf")
        c2.SaveAs(output_name + ".png")
        print(f"Saved: {output_name}.pdf/.png")
    
    # 快度分布
    c3 = ROOT.TCanvas("c_y", "", 800, 600)
    legend3 = ROOT.TLegend(0.60, 0.70, 0.88, 0.88)
    legend3.SetBorderSize(0)
    legend3.SetFillStyle(0)
    legend3.SetTextSize(0.035)
    
    h_jpsi_y = fin.Get("h_jpsi_y")
    h_ups_y = fin.Get("h_ups_y")
    h_phi_y = fin.Get("h_phi_y")
    
    if h_jpsi_y and h_ups_y and h_phi_y:
        h_jpsi_y.SetLineColor(ROOT.kRed)
        h_ups_y.SetLineColor(ROOT.kBlue)
        h_phi_y.SetLineColor(ROOT.kGreen + 2)
        
        for h in [h_jpsi_y, h_ups_y, h_phi_y]:
            h.SetLineWidth(2)
        
        max_val = max(h_jpsi_y.GetMaximum(), h_ups_y.GetMaximum(), h_phi_y.GetMaximum())
        h_jpsi_y.SetMaximum(max_val * 1.3)
        h_jpsi_y.SetMinimum(0)
        h_jpsi_y.SetTitle(f"Rapidity Distributions ({process})")
        h_jpsi_y.GetXaxis().SetTitle("y")
        h_jpsi_y.GetYaxis().SetTitle("Events")
        
        h_jpsi_y.Draw("HIST")
        h_ups_y.Draw("HIST SAME")
        h_phi_y.Draw("HIST SAME")
        
        legend3.AddEntry(h_jpsi_y, "J/#psi", "l")
        legend3.AddEntry(h_ups_y, "#Upsilon", "l")
        legend3.AddEntry(h_phi_y, "#phi", "l")
        legend3.Draw()
        
        output_name = os.path.join(output_dir, f"rapidity_distributions_{process}")
        c3.SaveAs(output_name + ".pdf")
        c3.SaveAs(output_name + ".png")
        print(f"Saved: {output_name}.pdf/.png")
    
    # φ (方位角) 分布
    c4 = ROOT.TCanvas("c_phi", "", 800, 600)
    legend4 = ROOT.TLegend(0.60, 0.70, 0.88, 0.88)
    legend4.SetBorderSize(0)
    legend4.SetFillStyle(0)
    legend4.SetTextSize(0.035)
    
    h_jpsi_phi = fin.Get("h_jpsi_phi")
    h_ups_phi = fin.Get("h_ups_phi")
    h_phi_phi = fin.Get("h_phi_phi")
    
    if h_jpsi_phi and h_ups_phi and h_phi_phi:
        h_jpsi_phi.SetLineColor(ROOT.kRed)
        h_ups_phi.SetLineColor(ROOT.kBlue)
        h_phi_phi.SetLineColor(ROOT.kGreen + 2)
        
        for h in [h_jpsi_phi, h_ups_phi, h_phi_phi]:
            h.SetLineWidth(2)
        
        max_val = max(h_jpsi_phi.GetMaximum(), h_ups_phi.GetMaximum(), h_phi_phi.GetMaximum())
        h_jpsi_phi.SetMaximum(max_val * 1.3)
        h_jpsi_phi.SetMinimum(0)
        h_jpsi_phi.SetTitle(f"Azimuthal Angle Distributions ({process})")
        h_jpsi_phi.GetXaxis().SetTitle("#phi")
        h_jpsi_phi.GetYaxis().SetTitle("Events")
        
        h_jpsi_phi.Draw("HIST")
        h_ups_phi.Draw("HIST SAME")
        h_phi_phi.Draw("HIST SAME")
        
        legend4.AddEntry(h_jpsi_phi, "J/#psi", "l")
        legend4.AddEntry(h_ups_phi, "#Upsilon", "l")
        legend4.AddEntry(h_phi_phi, "#phi", "l")
        legend4.Draw()
        
        output_name = os.path.join(output_dir, f"phi_distributions_{process}")
        c4.SaveAs(output_name + ".pdf")
        c4.SaveAs(output_name + ".png")
        print(f"Saved: {output_name}.pdf/.png")


def plot_invariant_mass_jjp(fin, output_dir, process):
    """绘制JJP不变质量分布"""
    c = ROOT.TCanvas("c_mass", "", 1600, 500)
    c.Divide(4, 1)
    
    mass_hists = [
        ("h_mass_jpsi1_jpsi2", "M(J/#psi_{1} + J/#psi_{2})"),
        ("h_mass_jpsi1_phi", "M(J/#psi_{1} + #phi)"),
        ("h_mass_jpsi2_phi", "M(J/#psi_{2} + #phi)"),
        ("h_mass_all", "M(J/#psi_{1} + J/#psi_{2} + #phi)")
    ]
    
    for i, (hname, title) in enumerate(mass_hists):
        c.cd(i + 1)
        ROOT.gPad.SetLeftMargin(0.12)
        ROOT.gPad.SetRightMargin(0.05)
        
        h = fin.Get(hname)
        if not h:
            print(f"Warning: histogram {hname} not found")
            continue
        
        h.SetLineColor(ROOT.kBlue)
        h.SetLineWidth(2)
        h.SetTitle(f"{title} ({process})")
        h.GetXaxis().SetTitle("M [GeV]")
        h.GetYaxis().SetTitle("Events")
        h.SetMinimum(0)
        h.Draw("HIST")
    
    output_name = os.path.join(output_dir, f"invariant_mass_{process}")
    c.SaveAs(output_name + ".pdf")
    c.SaveAs(output_name + ".png")
    print(f"Saved: {output_name}.pdf/.png")


def plot_invariant_mass_jup(fin, output_dir, process):
    """绘制JUP不变质量分布"""
    c = ROOT.TCanvas("c_mass", "", 1600, 500)
    c.Divide(4, 1)
    
    mass_hists = [
        ("h_mass_jpsi_ups", "M(J/#psi + #Upsilon)"),
        ("h_mass_jpsi_phi", "M(J/#psi + #phi)"),
        ("h_mass_ups_phi", "M(#Upsilon + #phi)"),
        ("h_mass_all", "M(J/#psi + #Upsilon + #phi)")
    ]
    
    for i, (hname, title) in enumerate(mass_hists):
        c.cd(i + 1)
        ROOT.gPad.SetLeftMargin(0.12)
        ROOT.gPad.SetRightMargin(0.05)
        
        h = fin.Get(hname)
        if not h:
            print(f"Warning: histogram {hname} not found")
            continue
        
        h.SetLineColor(ROOT.kBlue)
        h.SetLineWidth(2)
        h.SetTitle(f"{title} ({process})")
        h.GetXaxis().SetTitle("M [GeV]")
        h.GetYaxis().SetTitle("Events")
        h.SetMinimum(0)
        h.Draw("HIST")
    
    output_name = os.path.join(output_dir, f"invariant_mass_{process}")
    c.SaveAs(output_name + ".pdf")
    c.SaveAs(output_name + ".png")
    print(f"Saved: {output_name}.pdf/.png")


def plot_jjp(fin, output_dir, process):
    """绘制JJP所有图"""
    # Δy比较图
    plot_1d_comparison(
        fin,
        ["h_dy_jpsi1_jpsi2", "h_dy_jpsi1_phi", "h_dy_jpsi2_phi"],
        ["J/#psi_{1} - J/#psi_{2}", "J/#psi_{1} - #phi", "J/#psi_{2} - #phi"],
        [ROOT.kRed, ROOT.kBlue, ROOT.kGreen + 2],
        os.path.join(output_dir, f"delta_y_comparison_{process}"),
        f"#Delta y Distributions ({process})",
        "|#Delta y|"
    )
    
    # Δφ比较图
    plot_1d_comparison(
        fin,
        ["h_dphi_jpsi1_jpsi2", "h_dphi_jpsi1_phi", "h_dphi_jpsi2_phi"],
        ["J/#psi_{1} - J/#psi_{2}", "J/#psi_{1} - #phi", "J/#psi_{2} - #phi"],
        [ROOT.kRed, ROOT.kBlue, ROOT.kGreen + 2],
        os.path.join(output_dir, f"delta_phi_comparison_{process}"),
        f"#Delta#phi Distributions ({process})",
        "|#Delta#phi|"
    )
    
    # 2D关联图
    plot_2d(fin, "h2_dy_dphi_jpsi1_jpsi2",
            os.path.join(output_dir, f"correlation_2d_jpsi1_jpsi2_{process}"),
            f"J/#psi_{{1}} - J/#psi_{{2}}: #Delta y vs #Delta#phi ({process})")
    
    plot_2d(fin, "h2_dy_dphi_jpsi1_phi",
            os.path.join(output_dir, f"correlation_2d_jpsi1_phi_{process}"),
            f"J/#psi_{{1}} - #phi: #Delta y vs #Delta#phi ({process})")
    
    plot_2d(fin, "h2_dy_dphi_jpsi2_phi",
            os.path.join(output_dir, f"correlation_2d_jpsi2_phi_{process}"),
            f"J/#psi_{{2}} - #phi: #Delta y vs #Delta#phi ({process})")
    
    # 组合2D图
    plot_2d_all_jjp(fin, output_dir, process)
    
    # 运动学分布
    plot_kinematics_jjp(fin, output_dir, process)
    
    # 不变质量分布
    plot_invariant_mass_jjp(fin, output_dir, process)


def plot_jup(fin, output_dir, process):
    """绘制JUP所有图"""
    # Δy比较图
    plot_1d_comparison(
        fin,
        ["h_dy_jpsi_ups", "h_dy_jpsi_phi", "h_dy_ups_phi"],
        ["J/#psi - #Upsilon", "J/#psi - #phi", "#Upsilon - #phi"],
        [ROOT.kRed, ROOT.kBlue, ROOT.kGreen + 2],
        os.path.join(output_dir, f"delta_y_comparison_{process}"),
        f"#Delta y Distributions ({process})",
        "|#Delta y|"
    )
    
    # Δφ比较图
    plot_1d_comparison(
        fin,
        ["h_dphi_jpsi_ups", "h_dphi_jpsi_phi", "h_dphi_ups_phi"],
        ["J/#psi - #Upsilon", "J/#psi - #phi", "#Upsilon - #phi"],
        [ROOT.kRed, ROOT.kBlue, ROOT.kGreen + 2],
        os.path.join(output_dir, f"delta_phi_comparison_{process}"),
        f"#Delta#phi Distributions ({process})",
        "|#Delta#phi|"
    )
    
    # 2D关联图
    plot_2d(fin, "h2_dy_dphi_jpsi_ups",
            os.path.join(output_dir, f"correlation_2d_jpsi_ups_{process}"),
            f"J/#psi - #Upsilon: #Delta y vs #Delta#phi ({process})")
    
    plot_2d(fin, "h2_dy_dphi_jpsi_phi",
            os.path.join(output_dir, f"correlation_2d_jpsi_phi_{process}"),
            f"J/#psi - #phi: #Delta y vs #Delta#phi ({process})")
    
    plot_2d(fin, "h2_dy_dphi_ups_phi",
            os.path.join(output_dir, f"correlation_2d_ups_phi_{process}"),
            f"#Upsilon - #phi: #Delta y vs #Delta#phi ({process})")
    
    # 组合2D图
    plot_2d_all_jup(fin, output_dir, process)
    
    # 运动学分布
    plot_kinematics_jup(fin, output_dir, process)
    
    # 不变质量分布
    plot_invariant_mass_jup(fin, output_dir, process)


def main():
    parser = argparse.ArgumentParser(description='Ntuple分析结果绘图')
    parser.add_argument('-i', '--input', required=True,
                        help='输入ROOT文件')
    parser.add_argument('-o', '--output-dir', default='plots',
                        help='输出目录')
    parser.add_argument('-p', '--process', required=True,
                        choices=['JJP', 'JUP', 'JJY'],
                        help='过程类型 (JJP、JUP或JJY)')
    
    args = parser.parse_args()
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 打开输入文件
    fin = ROOT.TFile.Open(args.input, "READ")
    if not fin or fin.IsZombie():
        print(f"Error: Cannot open {args.input}")
        sys.exit(1)
    
    print(f"Processing: {args.input}")
    print(f"Output directory: {args.output_dir}")
    print(f"Process: {args.process}")
    
    if args.process == 'JJP':
        plot_jjp(fin, args.output_dir, args.process)
    elif args.process == 'JUP':
        plot_jup(fin, args.output_dir, args.process)
    else:
        plot_jjy(fin, args.output_dir, args.process)
    
    fin.Close()
    print("\nDone!")


if __name__ == '__main__':
    main()

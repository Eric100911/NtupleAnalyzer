#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
J/psi + J/psi + Phi window study for DPS: focus on 0.3 < DeltaPhi(Jpsi2, Phi) < 0.7
and 0 < DeltaY(Jpsi2, Phi) < 0.4. Keeps all baseline JJP selections identical to
existing ntuple analysis, then records kinematics of Jpsi1, Jpsi2, Phi and their
constituent muons/kaons inside that window.
"""
import argparse
import glob
import math
import os
import time
import tempfile
import multiprocessing

import ROOT
from ROOT import TFile, TChain, TH1F, TH2F, TLorentzVector

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
JJP_DATA_PATH_DEFAULT = "/eos/user/x/xcheng/learn_MC/JJP_DPS_MC_output/Ntuple/"
TREE_NAME = "mkcands/X_data"

JPSI1_MASS_MIN, JPSI1_MASS_MAX = 2.9, 3.3
JPSI2_MASS_MIN, JPSI2_MASS_MAX = 2.9, 3.3
PHI_MASS_MIN, PHI_MASS_MAX = 0.99, 1.10

JPSI_PT_MIN = 3.0
JPSI_VTXPROB_MIN = 0.05
PHI_PT_MIN = 2.0
PHI_VTXPROB_MIN = 0.05
PHI_K_PT_MIN = 2.0

JPSI_MUON_ID = 'soft'
OUTPUT_DIR = "/eos/user/x/xcheng/CMSSW_14_0_18/src/NtupleAnalyzer/output/"
PLOT_DIR_DEFAULT = None
DEFAULT_WORKERS = max(1, min(8, multiprocessing.cpu_count()))

MUON_MASS = 0.105658
KAON_MASS = 0.493677

# Window definition for Jpsi2 vs Phi
DPHI_MIN, DPHI_MAX = 0.3, 0.7
DY_MIN, DY_MAX = 0.0, 0.4
DPHI_ALT_MIN, DPHI_ALT_MAX = 0.7, 1.1
DPHI_LOW_MIN, DPHI_LOW_MAX = 0.0, 0.3
DY_HIGH_MIN, DY_HIGH_MAX = 0.4, 0.8
TRACK_DR_MAX = 0.005
TRACK_RELPT_MAX = 0.01


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def setup_root():
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)
    ROOT.gStyle.SetOptTitle(1)


def delta_phi(phi1, phi2):
    """Compute the absolute azimuthal angle difference wrapped to [-π, π].

    Args:
        phi1: First azimuthal angle in radians.
        phi2: Second azimuthal angle in radians.

    Returns:
        Signed difference ``phi1 - phi2`` wrapped to the interval [-π, π].
    """
    dphi = phi1 - phi2
    while dphi > math.pi:
        dphi -= 2 * math.pi
    while dphi < -math.pi:
        dphi += 2 * math.pi
    return dphi


def check_muon_id(chain, mu_idx, id_type):
    """Muon ID check, mirroring analyze_ntuple_JJP.py."""
    if id_type is None:
        return True
    try:
        idx = int(mu_idx)
        if idx < 0:
            return False
        if id_type == 'loose':
            return bool(chain.muIsPatLooseMuon.at(idx))
        if id_type == 'medium':
            return bool(chain.muIsPatMediumMuon.at(idx))
        if id_type == 'tight':
            return bool(chain.muIsPatTightMuon.at(idx))
        if id_type == 'soft':
            return bool(chain.muIsPatSoftMuon.at(idx))
        return True
    except Exception:
        return False


def build_vec_from_pxpypz(px, py, pz, mass):
    e = math.sqrt(px * px + py * py + pz * pz + mass * mass)
    vec = TLorentzVector()
    vec.SetPxPyPzE(px, py, pz, e)
    return vec


def create_histograms():
    """Create a dictionary of ROOT histograms for the JJP mass-window analysis.

    Four window variants are defined:
    * ``_main``  (no suffix) — primary window: 0.3 < Δφ < 0.7, 0 < Δy < 0.4
    * ``_alt``   — alternative window: 0.7 < Δφ < 1.1, same Δy range
    * ``_low``   — low-Δφ window: 0 < Δφ < 0.3, same Δy range
    * ``_dyhi``  — high-Δy window: same Δφ as main, 0.4 < Δy < 0.8

    Returns:
        dict mapping histogram key strings to ``TH1F`` or ``TH2F`` objects.
    """
    histograms = {}
    # Jpsi/Phi kinematics in window
    histograms['h_jpsi1_pt'] = TH1F('h_jpsi1_pt', 'J/#psi_{1} p_{T};p_{T} [GeV];Events', 18, 0, 40)
    histograms['h_jpsi1_eta'] = TH1F('h_jpsi1_eta', 'J/#psi_{1} #eta;#eta;Events', 18, -3, 3)
    histograms['h_jpsi1_phi'] = TH1F('h_jpsi1_phi', 'J/#psi_{1} #phi;#phi;Events', 18, -math.pi, math.pi)

    histograms['h_jpsi2_pt'] = TH1F('h_jpsi2_pt', 'J/#psi_{2} p_{T};p_{T} [GeV];Events', 18, 0, 40)
    histograms['h_jpsi2_eta'] = TH1F('h_jpsi2_eta', 'J/#psi_{2} #eta;#eta;Events', 18, -3, 3)
    histograms['h_jpsi2_phi'] = TH1F('h_jpsi2_phi', 'J/#psi_{2} #phi;#phi;Events', 18, -math.pi, math.pi)

    histograms['h_phi_pt'] = TH1F('h_phi_pt', '#phi p_{T};p_{T} [GeV];Events', 18, 0, 40)
    histograms['h_phi_eta'] = TH1F('h_phi_eta', '#phi #eta;#eta;Events', 18, -3, 3)
    histograms['h_phi_phi'] = TH1F('h_phi_phi', '#phi #phi;#phi;Events', 18, -math.pi, math.pi)

    # Muon kinematics (Jpsi1 mu1/mu2, Jpsi2 mu1/mu2)
    histograms['h_mu_jpsi1_mu1_pt'] = TH1F('h_mu_jpsi1_mu1_pt', 'Muon (J/#psi_{1} #mu_{1}) p_{T};p_{T} [GeV];Events', 18, 0, 40)
    histograms['h_mu_jpsi1_mu1_eta'] = TH1F('h_mu_jpsi1_mu1_eta', 'Muon (J/#psi_{1} #mu_{1}) #eta;#eta;Events', 18, -3, 3)
    histograms['h_mu_jpsi1_mu1_phi'] = TH1F('h_mu_jpsi1_mu1_phi', 'Muon (J/#psi_{1} #mu_{1}) #phi;#phi;Events', 18, -math.pi, math.pi)

    histograms['h_mu_jpsi1_mu2_pt'] = TH1F('h_mu_jpsi1_mu2_pt', 'Muon (J/#psi_{1} #mu_{2}) p_{T};p_{T} [GeV];Events', 18, 0, 40)
    histograms['h_mu_jpsi1_mu2_eta'] = TH1F('h_mu_jpsi1_mu2_eta', 'Muon (J/#psi_{1} #mu_{2}) #eta;#eta;Events', 18, -3, 3)
    histograms['h_mu_jpsi1_mu2_phi'] = TH1F('h_mu_jpsi1_mu2_phi', 'Muon (J/#psi_{1} #mu_{2}) #phi;#phi;Events', 18, -math.pi, math.pi)

    histograms['h_mu_jpsi2_mu1_pt'] = TH1F('h_mu_jpsi2_mu1_pt', 'Muon (J/#psi_{2} #mu_{1}) p_{T};p_{T} [GeV];Events', 18, 0, 40)
    histograms['h_mu_jpsi2_mu1_eta'] = TH1F('h_mu_jpsi2_mu1_eta', 'Muon (J/#psi_{2} #mu_{1}) #eta;#eta;Events', 18, -3, 3)
    histograms['h_mu_jpsi2_mu1_phi'] = TH1F('h_mu_jpsi2_mu1_phi', 'Muon (J/#psi_{2} #mu_{1}) #phi;#phi;Events', 18, -math.pi, math.pi)

    histograms['h_mu_jpsi2_mu2_pt'] = TH1F('h_mu_jpsi2_mu2_pt', 'Muon (J/#psi_{2} #mu_{2}) p_{T};p_{T} [GeV];Events', 18, 0, 40)
    histograms['h_mu_jpsi2_mu2_eta'] = TH1F('h_mu_jpsi2_mu2_eta', 'Muon (J/#psi_{2} #mu_{2}) #eta;#eta;Events', 18, -3, 3)
    histograms['h_mu_jpsi2_mu2_phi'] = TH1F('h_mu_jpsi2_mu2_phi', 'Muon (J/#psi_{2} #mu_{2}) #phi;#phi;Events', 18, -math.pi, math.pi)

    # Kaon kinematics
    histograms['h_k1_pt'] = TH1F('h_k1_pt', 'K_{1} p_{T};p_{T} [GeV];Events', 18, 0, 40)
    histograms['h_k1_eta'] = TH1F('h_k1_eta', 'K_{1} #eta;#eta;Events', 18, -3, 3)
    histograms['h_k1_phi'] = TH1F('h_k1_phi', 'K_{1} #phi;#phi;Events', 18, -math.pi, math.pi)

    histograms['h_k2_pt'] = TH1F('h_k2_pt', 'K_{2} p_{T};p_{T} [GeV];Events', 18, 0, 40)
    histograms['h_k2_eta'] = TH1F('h_k2_eta', 'K_{2} #eta;#eta;Events', 18, -3, 3)
    histograms['h_k2_phi'] = TH1F('h_k2_phi', 'K_{2} #phi;#phi;Events', 18, -math.pi, math.pi)

    # Delta y vs Delta phi (Jpsi2 vs Phi) inside window, zoom to window range
    # x: Delta y (6 bins), y: Delta phi (8 bins), both restricted to window range
    histograms['h2_dy_dphi_jpsi2_phi'] = TH2F('h2_dy_dphi_jpsi2_phi',
        'J/#psi_{2} - #phi: #Delta y vs #Delta#phi;#Delta y;#Delta#phi',
        6, DY_MIN, DY_MAX, 8, DPHI_MIN, DPHI_MAX)
    histograms['h2_dy_dphi_jpsi2_phi_alt'] = TH2F('h2_dy_dphi_jpsi2_phi_alt',
        'J/#psi_{2} - #phi: #Delta y vs #Delta#phi (0.7<#Delta#phi<1.1);#Delta y;#Delta#phi',
        6, DY_MIN, DY_MAX, 8, DPHI_ALT_MIN, DPHI_ALT_MAX)
    histograms['h2_dy_dphi_jpsi2_phi_low'] = TH2F('h2_dy_dphi_jpsi2_phi_low',
        'J/#psi_{2} - #phi: #Delta y vs #Delta#phi (0<#Delta#phi<0.3);#Delta y;#Delta#phi',
        6, DY_MIN, DY_MAX, 8, DPHI_LOW_MIN, DPHI_LOW_MAX)
    histograms['h2_dy_dphi_jpsi2_phi_dyhi'] = TH2F('h2_dy_dphi_jpsi2_phi_dyhi',
        'J/#psi_{2} - #phi: #Delta y vs #Delta#phi (0.3<#Delta#phi<0.7, 0.4<#Delta y<0.8);#Delta y;#Delta#phi',
        6, DY_HIGH_MIN, DY_HIGH_MAX, 8, DPHI_MIN, DPHI_MAX)

    # Min DeltaR and |pT difference| between Jpsi2 muons and Phi kaons (4 combos), take event-wise minimum
    histograms['h_mu2k_min_dR'] = TH1F('h_mu2k_min_dR', 'min #DeltaR(#mu_{J/#psi2}, K_{#phi});min #DeltaR;Events', 18, 0, 3.6)
    histograms['h_mu2k_min_abs_dpt'] = TH1F('h_mu2k_min_abs_dpt', 'min |p_{T}^{#mu_{J/#psi2}} - p_{T}^{K_{#phi}}|;min |#Delta p_{T}| [GeV];Events', 18, 0, 20)

    # Duplicate 1D histograms for comparison windows (0.7<DeltaPhi<1.1 and 0<DeltaPhi<0.3) using the same binning
    base_keys = [k for k in list(histograms.keys()) if not k.endswith('_alt') and not k.endswith('_low') and not k.endswith('_dyhi')
                 and not k.startswith('h2_dy_dphi_jpsi2_phi_alt') and not k.startswith('h2_dy_dphi_jpsi2_phi_low') and not k.startswith('h2_dy_dphi_jpsi2_phi_dyhi')]
    for key in base_keys:
        if isinstance(histograms[key], TH1F):
            alt_name = f"{key}_alt"
            low_name = f"{key}_low"
            dyhi_name = f"{key}_dyhi"
            histograms[alt_name] = histograms[key].Clone(alt_name)
            histograms[low_name] = histograms[key].Clone(low_name)
            histograms[dyhi_name] = histograms[key].Clone(dyhi_name)
    # Enable per-bin statistical uncertainties
    for hist in histograms.values():
        if isinstance(hist, TH1F):
            hist.Sumw2()
    return histograms


def save_plots(histos, plot_dir):
    os.makedirs(plot_dir, exist_ok=True)
    canvas = ROOT.TCanvas("c", "c", 800, 600)
    for name, hist in histos.items():
        # skip alt entries; we draw them together with their base
        if name.endswith('_alt') or name.endswith('_low') or name.endswith('_dyhi'):
            continue

        alt_name = f"{name}_alt"
        alt_hist = histos.get(alt_name)
        low_name = f"{name}_low"
        low_hist = histos.get(low_name)
        dyhi_name = f"{name}_dyhi"
        dyhi_hist = histos.get(dyhi_name)

        canvas.Clear()
        if (alt_hist or low_hist or dyhi_hist) and not isinstance(hist, TH2F):
            hist.SetLineColor(ROOT.kBlack)
            hist.SetLineWidth(2)
            hist.SetLineStyle(1)
            hist.SetMarkerColor(ROOT.kBlack)
            hist.SetMarkerStyle(20)
            if alt_hist:
                alt_hist.SetLineColor(ROOT.kRed)
                alt_hist.SetLineStyle(1)
                alt_hist.SetLineWidth(2)
                alt_hist.SetMarkerColor(ROOT.kRed)
                alt_hist.SetMarkerStyle(21)
            if low_hist:
                low_hist.SetLineColor(ROOT.kBlue)
                low_hist.SetLineStyle(1)
                low_hist.SetLineWidth(2)
                low_hist.SetMarkerColor(ROOT.kBlue)
                low_hist.SetMarkerStyle(22)
            if dyhi_hist:
                dyhi_hist.SetLineColor(ROOT.kGreen + 2)
                dyhi_hist.SetLineStyle(1)
                dyhi_hist.SetLineWidth(2)
                dyhi_hist.SetMarkerColor(ROOT.kGreen + 2)
                dyhi_hist.SetMarkerStyle(23)
            max_y = max([h.GetMaximum() for h in [hist, alt_hist, low_hist, dyhi_hist] if h])
            for htmp in [hist, alt_hist, low_hist, dyhi_hist]:
                if htmp:
                    htmp.SetMinimum(0)
                    htmp.SetMaximum(max_y * 1.25 if max_y > 0 else 1.0)
            hist.Draw("E1")
            if alt_hist:
                alt_hist.Draw("E1 SAME")
            if low_hist:
                low_hist.Draw("E1 SAME")
            if dyhi_hist:
                dyhi_hist.Draw("E1 SAME")
            # Move legend upward to avoid covering the curves
            leg = ROOT.TLegend(0.55, 0.70, 0.89, 0.92)
            leg.SetBorderSize(0)
            leg.SetFillStyle(0)
            leg.AddEntry(hist, "0.3<#Delta#phi<0.7", "l")
            if alt_hist:
                leg.AddEntry(alt_hist, "0.7<#Delta#phi<1.1", "l")
            if low_hist:
                leg.AddEntry(low_hist, "0<#Delta#phi<0.3", "l")
            if dyhi_hist:
                leg.AddEntry(dyhi_hist, "0.3<#Delta#phi<0.7, 0.4<#Delta y<0.8", "l")
            leg.Draw()
            canvas.SaveAs(os.path.join(plot_dir, f"{name}.png"))
        elif isinstance(hist, TH2F):
            hist.Draw("COLZ")
            canvas.SaveAs(os.path.join(plot_dir, f"{name}.png"))
            if alt_hist:
                canvas.Clear()
                alt_hist.Draw("COLZ")
                canvas.SaveAs(os.path.join(plot_dir, f"{alt_name}.png"))
            if low_hist:
                canvas.Clear()
                low_hist.Draw("COLZ")
                canvas.SaveAs(os.path.join(plot_dir, f"{low_name}.png"))
            if dyhi_hist:
                canvas.Clear()
                dyhi_hist.Draw("COLZ")
                canvas.SaveAs(os.path.join(plot_dir, f"{dyhi_name}.png"))
        else:
            hist.SetMinimum(0)
            hist.Draw("HIST")
            canvas.SaveAs(os.path.join(plot_dir, f"{name}.png"))


def merge_histograms(dest, src):
    for name, hdest in dest.items():
        hsrc = src.Get(name)
        if hsrc:
            hdest.Add(hsrc)


def process_file_batch(file_list, max_events, muon_id, tree_name):
    """Process a batch of ROOT files in a single worker process.

    Selects the best J/ψ J/ψ φ candidate per event by the ``Score3`` metric,
    applies muon ID and kinematic cuts, and fills histograms for four
    (Δy, Δφ) window variants.  Results are written to a temporary ROOT file.

    Args:
        file_list: List of ROOT file paths to process.
        max_events: Maximum events to process (-1 = all).
        muon_id: Muon identification string (``"soft"``, etc.).
        tree_name: Name of the TTree inside each ROOT file.

    Returns:
        Tuple of ``(tmp_path, n_processed, n_window_main, n_window_alt,
        n_window_low, n_window_dyhi, n_has_cand, n_pass_baseline,
        n_fail_mass, n_fail_pt, n_fail_vtx, n_fail_kpt, n_fail_mu,
        n_track_misuse, n_mu_fill_ok, n_mu_fill_fail, n_mu_size_zero,
        mu_size_min, mu_size_max, mu_idx_max, mu_idx_neg, mu_idx_ge_size)``.
    """
    chain = TChain(tree_name)
    for f in file_list:
        chain.Add(f)

    histos = create_histograms()
    n_total = chain.GetEntries()
    n_to_process = n_total if max_events < 0 else min(max_events, n_total)
    n_window = 0
    n_window_alt = 0
    n_window_low = 0
    n_window_dyhi = 0
    n_has_cand = 0
    n_pass_baseline = 0
    n_fail_mass = 0
    n_fail_pt = 0
    n_fail_vtx = 0
    n_fail_kpt = 0
    n_fail_mu = 0
    n_track_misuse = 0
    n_mu_fill_ok = 0
    n_mu_fill_fail = 0
    n_mu_size_zero = 0
    n_mu_idx_neg = 0
    n_mu_idx_ge_size = 0
    mu_size_min = None
    mu_size_max = None
    mu_idx_max_seen = None
    debug_fail_prints = 0

    for i_evt in range(n_to_process):
        chain.GetEntry(i_evt)
        try:
            n_cand = chain.Jpsi_1_mass.size()
        except Exception:
            continue
        if n_cand == 0:
            continue
        n_has_cand += 1

        best_cand = None
        best_score = -1

        for i_cand in range(n_cand):
            try:
                jpsi1_mass = chain.Jpsi_1_mass.at(i_cand)
                jpsi2_mass = chain.Jpsi_2_mass.at(i_cand)
                phi_mass = chain.Phi_mass.at(i_cand)
                if not (JPSI1_MASS_MIN < jpsi1_mass < JPSI1_MASS_MAX):
                    n_fail_mass += 1
                    continue
                if not (JPSI2_MASS_MIN < jpsi2_mass < JPSI2_MASS_MAX):
                    n_fail_mass += 1
                    continue
                if not (PHI_MASS_MIN < phi_mass < PHI_MASS_MAX):
                    n_fail_mass += 1
                    continue

                jpsi1_pt = chain.Jpsi_1_pt.at(i_cand)
                jpsi2_pt = chain.Jpsi_2_pt.at(i_cand)
                phi_pt = chain.Phi_pt.at(i_cand)
                if jpsi1_pt < JPSI_PT_MIN or jpsi2_pt < JPSI_PT_MIN or phi_pt < PHI_PT_MIN:
                    n_fail_pt += 1
                    continue

                jpsi1_vtxprob = chain.Jpsi_1_VtxProb.at(i_cand)
                jpsi2_vtxprob = chain.Jpsi_2_VtxProb.at(i_cand)
                phi_vtxprob = chain.Phi_VtxProb.at(i_cand)
                if jpsi1_vtxprob < JPSI_VTXPROB_MIN or jpsi2_vtxprob < JPSI_VTXPROB_MIN or phi_vtxprob < PHI_VTXPROB_MIN:
                    n_fail_vtx += 1
                    continue

                phi_k1_pt = chain.Phi_K_1_pt.at(i_cand)
                phi_k2_pt = chain.Phi_K_2_pt.at(i_cand)
                if phi_k1_pt < PHI_K_PT_MIN or phi_k2_pt < PHI_K_PT_MIN:
                    n_fail_kpt += 1
                    continue

                jpsi1_mu1_idx = int(chain.Jpsi_1_mu_1_Idx.at(i_cand))
                jpsi1_mu2_idx = int(chain.Jpsi_1_mu_2_Idx.at(i_cand))
                jpsi2_mu1_idx = int(chain.Jpsi_2_mu_1_Idx.at(i_cand))
                jpsi2_mu2_idx = int(chain.Jpsi_2_mu_2_Idx.at(i_cand))

                if muon_id and muon_id.lower() != 'none':
                    if not (check_muon_id(chain, jpsi1_mu1_idx, muon_id) and
                            check_muon_id(chain, jpsi1_mu2_idx, muon_id) and
                            check_muon_id(chain, jpsi2_mu1_idx, muon_id) and
                            check_muon_id(chain, jpsi2_mu2_idx, muon_id)):
                        n_fail_mu += 1
                        continue

                jpsi1_eta = chain.Jpsi_1_eta.at(i_cand)
                jpsi1_phi = chain.Jpsi_1_phi.at(i_cand)
                jpsi2_eta = chain.Jpsi_2_eta.at(i_cand)
                jpsi2_phi = chain.Jpsi_2_phi.at(i_cand)
                phi_eta = chain.Phi_eta.at(i_cand)
                phi_phi = chain.Phi_phi.at(i_cand)

                score = math.sqrt(jpsi1_pt * jpsi1_pt + jpsi2_pt * jpsi2_pt + phi_pt * phi_pt)
                if score > best_score:
                    best_score = score
                    best_cand = {
                        'jpsi1_pt': jpsi1_pt, 'jpsi1_eta': jpsi1_eta, 'jpsi1_phi': jpsi1_phi, 'jpsi1_mass': jpsi1_mass,
                        'jpsi2_pt': jpsi2_pt, 'jpsi2_eta': jpsi2_eta, 'jpsi2_phi': jpsi2_phi, 'jpsi2_mass': jpsi2_mass,
                        'phi_pt': phi_pt, 'phi_eta': phi_eta, 'phi_phi': phi_phi, 'phi_mass': phi_mass,
                        'jpsi1_mu1_idx': jpsi1_mu1_idx, 'jpsi1_mu2_idx': jpsi1_mu2_idx,
                        'jpsi2_mu1_idx': jpsi2_mu1_idx, 'jpsi2_mu2_idx': jpsi2_mu2_idx,
                        'phi_k1_pt': phi_k1_pt, 'phi_k1_eta': chain.Phi_K_1_eta.at(i_cand), 'phi_k1_phi': chain.Phi_K_1_phi.at(i_cand),
                        'phi_k2_pt': phi_k2_pt, 'phi_k2_eta': chain.Phi_K_2_eta.at(i_cand), 'phi_k2_phi': chain.Phi_K_2_phi.at(i_cand),
                        'phi_k1_px': chain.Phi_K_1_px.at(i_cand), 'phi_k1_py': chain.Phi_K_1_py.at(i_cand), 'phi_k1_pz': chain.Phi_K_1_pz.at(i_cand),
                        'phi_k2_px': chain.Phi_K_2_px.at(i_cand), 'phi_k2_py': chain.Phi_K_2_py.at(i_cand), 'phi_k2_pz': chain.Phi_K_2_pz.at(i_cand),
                    }
            except Exception:
                continue

        if best_cand is None:
            continue

        n_pass_baseline += 1

        # Build boson 4-vectors once
        jpsi1_4vec = TLorentzVector()
        jpsi2_4vec = TLorentzVector()
        phi_4vec = TLorentzVector()
        jpsi1_4vec.SetPtEtaPhiM(best_cand['jpsi1_pt'], best_cand['jpsi1_eta'], best_cand['jpsi1_phi'], best_cand['jpsi1_mass'])
        jpsi2_4vec.SetPtEtaPhiM(best_cand['jpsi2_pt'], best_cand['jpsi2_eta'], best_cand['jpsi2_phi'], best_cand['jpsi2_mass'])
        phi_4vec.SetPtEtaPhiM(best_cand['phi_pt'], best_cand['phi_eta'], best_cand['phi_phi'], best_cand['phi_mass'])

        dy_jpsi2_phi = abs(jpsi2_4vec.Rapidity() - phi_4vec.Rapidity())
        dphi_jpsi2_phi = abs(delta_phi(jpsi2_4vec.Phi(), phi_4vec.Phi()))

        in_window_main = (DPHI_MIN < dphi_jpsi2_phi < DPHI_MAX and DY_MIN < dy_jpsi2_phi < DY_MAX)
        in_window_alt = (DPHI_ALT_MIN < dphi_jpsi2_phi < DPHI_ALT_MAX and DY_MIN < dy_jpsi2_phi < DY_MAX)
        in_window_low = (DPHI_LOW_MIN < dphi_jpsi2_phi < DPHI_LOW_MAX and DY_MIN < dy_jpsi2_phi < DY_MAX)
        in_window_dyhi = (DPHI_MIN < dphi_jpsi2_phi < DPHI_MAX and DY_HIGH_MIN < dy_jpsi2_phi < DY_HIGH_MAX)

        if not (in_window_main or in_window_alt or in_window_low or in_window_dyhi):
            continue

        # Muon bookkeeping and validation (only when the event is in either window)
        try:
            mu_size = chain.muPx.size()
            if mu_size_min is None or mu_size < mu_size_min:
                mu_size_min = mu_size
            if mu_size_max is None or mu_size > mu_size_max:
                mu_size_max = mu_size
            muon_indices = [int(best_cand['jpsi1_mu1_idx']), int(best_cand['jpsi1_mu2_idx']),
                    int(best_cand['jpsi2_mu1_idx']), int(best_cand['jpsi2_mu2_idx'])]
            max_idx = max(muon_indices)
            if mu_idx_max_seen is None or max_idx > mu_idx_max_seen:
                mu_idx_max_seen = max_idx
            invalid_neg = any(idx < 0 for idx in muon_indices)
            invalid_ge = any(idx >= mu_size for idx in muon_indices)
            mu_valid = not (invalid_neg or invalid_ge)

            jpsi1_mu1_vec = jpsi1_mu2_vec = jpsi2_mu1_vec = jpsi2_mu2_vec = None
            if mu_valid:
                jpsi1_mu1_vec = build_vec_from_pxpypz(chain.muPx.at(best_cand['jpsi1_mu1_idx']),
                                                 chain.muPy.at(best_cand['jpsi1_mu1_idx']),
                                                 chain.muPz.at(best_cand['jpsi1_mu1_idx']), MUON_MASS)
                jpsi1_mu2_vec = build_vec_from_pxpypz(chain.muPx.at(best_cand['jpsi1_mu2_idx']),
                                                 chain.muPy.at(best_cand['jpsi1_mu2_idx']),
                                                 chain.muPz.at(best_cand['jpsi1_mu2_idx']), MUON_MASS)
                jpsi2_mu1_vec = build_vec_from_pxpypz(chain.muPx.at(best_cand['jpsi2_mu1_idx']),
                                                 chain.muPy.at(best_cand['jpsi2_mu1_idx']),
                                                 chain.muPz.at(best_cand['jpsi2_mu1_idx']), MUON_MASS)
                jpsi2_mu2_vec = build_vec_from_pxpypz(chain.muPx.at(best_cand['jpsi2_mu2_idx']),
                                                 chain.muPy.at(best_cand['jpsi2_mu2_idx']),
                                                 chain.muPz.at(best_cand['jpsi2_mu2_idx']), MUON_MASS)
            else:
                if mu_size == 0:
                    n_mu_size_zero += 1
                if invalid_neg:
                    n_mu_idx_neg += 1
                if invalid_ge:
                    n_mu_idx_ge_size += 1
                if debug_fail_prints < 5:
                    print(f"[DEBUG] Mu fill fail: muon_indices={muon_indices}, mu_size={mu_size}")
                    debug_fail_prints += 1

        except Exception:
            mu_valid = False
            if debug_fail_prints < 5:
                print("[DEBUG] Mu fill exception")
                debug_fail_prints += 1

        # Kaon 4-vectors
        phi_kaon1_vec = build_vec_from_pxpypz(best_cand['phi_k1_px'], best_cand['phi_k1_py'], best_cand['phi_k1_pz'], KAON_MASS)
        phi_kaon2_vec = build_vec_from_pxpypz(best_cand['phi_k2_px'], best_cand['phi_k2_py'], best_cand['phi_k2_pz'], KAON_MASS)

        # Compute min DeltaR and |pT difference| between Jpsi2 muons and Phi kaons
        # Also flag potential track misuse (muon reused as kaon) via tight geometric+pt match
        min_dR = None
        min_abs_dpt = None
        track_misuse = False
        if mu_valid:
            combos = [(jpsi2_mu1_vec, phi_kaon1_vec), (jpsi2_mu1_vec, phi_kaon2_vec), (jpsi2_mu2_vec, phi_kaon1_vec), (jpsi2_mu2_vec, phi_kaon2_vec)]
            for mu_vec, k_vec in combos:
                deta = mu_vec.Eta() - k_vec.Eta()
                dphi = delta_phi(mu_vec.Phi(), k_vec.Phi())
                dr = math.sqrt(deta * deta + dphi * dphi)
                abs_dpt = abs(mu_vec.Pt() - k_vec.Pt())
                min_dR = dr if min_dR is None else min(min_dR, dr)
                min_abs_dpt = abs_dpt if min_abs_dpt is None else min(min_abs_dpt, abs_dpt)
                rel_dpt = abs_dpt / mu_vec.Pt() if mu_vec.Pt() > 0 else 1e9
                if dr < TRACK_DR_MAX and rel_dpt < TRACK_RELPT_MAX:
                    track_misuse = True

        if track_misuse:
            n_track_misuse += 1
            continue

        if in_window_main:
            n_window += 1
        if in_window_alt:
            n_window_alt += 1
        if in_window_low:
            n_window_low += 1
        if in_window_dyhi:
            n_window_dyhi += 1

        # Muon fill counters: count once per event that lands in either window
        if mu_valid:
            n_mu_fill_ok += 1
        else:
            n_mu_fill_fail += 1

        # Helper to fill histograms for each window
        def fill_window_histos(suffix):
            histos[f'h2_dy_dphi_jpsi2_phi{suffix}'].Fill(dy_jpsi2_phi, dphi_jpsi2_phi)
            histos[f'h_jpsi1_pt{suffix}'].Fill(jpsi1_4vec.Pt())
            histos[f'h_jpsi1_eta{suffix}'].Fill(jpsi1_4vec.Eta())
            histos[f'h_jpsi1_phi{suffix}'].Fill(jpsi1_4vec.Phi())
            histos[f'h_jpsi2_pt{suffix}'].Fill(jpsi2_4vec.Pt())
            histos[f'h_jpsi2_eta{suffix}'].Fill(jpsi2_4vec.Eta())
            histos[f'h_jpsi2_phi{suffix}'].Fill(jpsi2_4vec.Phi())
            histos[f'h_phi_pt{suffix}'].Fill(phi_4vec.Pt())
            histos[f'h_phi_eta{suffix}'].Fill(phi_4vec.Eta())
            histos[f'h_phi_phi{suffix}'].Fill(phi_4vec.Phi())

            if mu_valid:
                histos[f'h_mu_jpsi1_mu1_pt{suffix}'].Fill(jpsi1_mu1_vec.Pt())
                histos[f'h_mu_jpsi1_mu1_eta{suffix}'].Fill(jpsi1_mu1_vec.Eta())
                histos[f'h_mu_jpsi1_mu1_phi{suffix}'].Fill(jpsi1_mu1_vec.Phi())
                histos[f'h_mu_jpsi1_mu2_pt{suffix}'].Fill(jpsi1_mu2_vec.Pt())
                histos[f'h_mu_jpsi1_mu2_eta{suffix}'].Fill(jpsi1_mu2_vec.Eta())
                histos[f'h_mu_jpsi1_mu2_phi{suffix}'].Fill(jpsi1_mu2_vec.Phi())
                histos[f'h_mu_jpsi2_mu1_pt{suffix}'].Fill(jpsi2_mu1_vec.Pt())
                histos[f'h_mu_jpsi2_mu1_eta{suffix}'].Fill(jpsi2_mu1_vec.Eta())
                histos[f'h_mu_jpsi2_mu1_phi{suffix}'].Fill(jpsi2_mu1_vec.Phi())
                histos[f'h_mu_jpsi2_mu2_pt{suffix}'].Fill(jpsi2_mu2_vec.Pt())
                histos[f'h_mu_jpsi2_mu2_eta{suffix}'].Fill(jpsi2_mu2_vec.Eta())
                histos[f'h_mu_jpsi2_mu2_phi{suffix}'].Fill(jpsi2_mu2_vec.Phi())
                if min_dR is not None:
                    histos[f'h_mu2k_min_dR{suffix}'].Fill(min_dR)
                if min_abs_dpt is not None:
                    histos[f'h_mu2k_min_abs_dpt{suffix}'].Fill(min_abs_dpt)

            histos[f'h_k1_pt{suffix}'].Fill(phi_kaon1_vec.Pt())
            histos[f'h_k1_eta{suffix}'].Fill(phi_kaon1_vec.Eta())
            histos[f'h_k1_phi{suffix}'].Fill(phi_kaon1_vec.Phi())
            histos[f'h_k2_pt{suffix}'].Fill(phi_kaon2_vec.Pt())
            histos[f'h_k2_eta{suffix}'].Fill(phi_kaon2_vec.Eta())
            histos[f'h_k2_phi{suffix}'].Fill(phi_kaon2_vec.Phi())

        if in_window_main:
            fill_window_histos('')
        if in_window_alt:
            fill_window_histos('_alt')
        if in_window_low:
            fill_window_histos('_low')
        if in_window_dyhi:
            fill_window_histos('_dyhi')

    fd, tmp_path = tempfile.mkstemp(suffix=".root", prefix="jjp_window_tmp_")
    os.close(fd)
    fout = TFile(tmp_path, "RECREATE")
    for h in histos.values():
        h.Write()
    fout.Close()

    return (tmp_path, n_to_process, n_window, n_window_alt, n_window_low, n_window_dyhi, n_has_cand, n_pass_baseline,
            n_fail_mass, n_fail_pt, n_fail_vtx, n_fail_kpt, n_fail_mu, n_track_misuse,
            n_mu_fill_ok, n_mu_fill_fail, n_mu_size_zero,
            mu_size_min if mu_size_min is not None else 0,
            mu_size_max if mu_size_max is not None else 0,
            mu_idx_max_seen if mu_idx_max_seen is not None else -1,
            n_mu_idx_neg, n_mu_idx_ge_size)


# -----------------------------------------------------------------------------
# Core analysis
# -----------------------------------------------------------------------------
def analyze_jjp_window(max_events=-1, muon_id='soft', input_dir=None, output_file=None, plot_dir=None, n_workers=1):
    global JPSI_MUON_ID
    JPSI_MUON_ID = muon_id

    setup_root()

    data_path = input_dir if input_dir else JJP_DATA_PATH_DEFAULT
    data_files = [os.path.join(data_path, os.path.basename(f)) for f in glob.glob(os.path.join(data_path, '*.root')) if os.path.exists(os.path.join(data_path, os.path.basename(f)))]
    n_files = len(data_files)
    print(f"[INFO] 输入目录: {data_path}")
    print(f"[INFO] 加载 {n_files} 个文件")

    if n_files == 0:
        print("[ERROR] 未找到输入文件")
        return None

    if n_workers <= 1:
        batch_files = [data_files]
    else:
        batch_files = [[] for _ in range(n_workers)]
        for idx, f in enumerate(data_files):
            batch_files[idx % n_workers].append(f)
        batch_files = [b for b in batch_files if b]
        n_batches = len(batch_files)

    if max_events < 0:
        per_batch_events = -1
    else:
        per_batch_events = math.ceil(max_events / len(batch_files))

    # Run workers
    if len(batch_files) == 1:
        result = process_file_batch(batch_files[0], per_batch_events, muon_id, TREE_NAME)
        temp_files = [result[0]]
        total_processed = result[1]
        total_in_window = result[2]
        total_in_window_alt = result[3]
        total_in_window_low = result[4]
        total_in_window_dyhi = result[5]
        total_has_cand = result[6]
        total_pass_baseline = result[7]
        total_fail_mass = result[8]
        total_fail_pt = result[9]
        total_fail_vtx = result[10]
        total_fail_kpt = result[11]
        total_fail_mu = result[12]
        total_track_misuse = result[13]
        total_mu_fill_ok = result[14]
        total_mu_fill_fail = result[15]
        total_mu_size_zero = result[16]
        total_mu_size_min = result[17]
        total_mu_size_max = result[18]
        total_mu_idx_max = result[19]
        total_mu_idx_neg = result[20]
        total_mu_idx_ge_size = result[21]
    else:
        with multiprocessing.Pool(processes=len(batch_files)) as pool:
            results = pool.starmap(process_file_batch,
                                   [(b, per_batch_events, muon_id, TREE_NAME) for b in batch_files])
        temp_files = [r[0] for r in results]
        total_processed = sum(r[1] for r in results)
        total_in_window = sum(r[2] for r in results)
        total_in_window_alt = sum(r[3] for r in results)
        total_in_window_low = sum(r[4] for r in results)
        total_in_window_dyhi = sum(r[5] for r in results)
        total_has_cand = sum(r[6] for r in results)
        total_pass_baseline = sum(r[7] for r in results)
        total_fail_mass = sum(r[8] for r in results)
        total_fail_pt = sum(r[9] for r in results)
        total_fail_vtx = sum(r[10] for r in results)
        total_fail_kpt = sum(r[11] for r in results)
        total_fail_mu = sum(r[12] for r in results)
        total_track_misuse = sum(r[13] for r in results)
        total_mu_fill_ok = sum(r[14] for r in results)
        total_mu_fill_fail = sum(r[15] for r in results)
        total_mu_size_zero = sum(r[16] for r in results)
        total_mu_size_min = min(r[17] for r in results if r[17] > 0) if results else 0
        total_mu_size_max = max(r[18] for r in results) if results else 0
        total_mu_idx_max = max(r[19] for r in results) if results else -1
        total_mu_idx_neg = sum(r[20] for r in results)
        total_mu_idx_ge_size = sum(r[21] for r in results)

    histos = create_histograms()
    for tmp_path in temp_files:
        input_file = TFile.Open(tmp_path)
        if input_file and not input_file.IsZombie():
            merge_histograms(histos, input_file)
        input_file.Close()
        os.remove(tmp_path)

    # Normalize all 1D histograms to unit area for shape comparison
    for h in histos.values():
        if isinstance(h, TH1F):
            integral = h.Integral()
            if integral > 0:
                h.Scale(1.0 / integral)

    elapsed = time.time() - start_time
    n_to_process = total_processed if max_events < 0 else min(max_events, total_processed)
    print(f"[INFO] 处理事件总数: {total_processed}")
    print(f"[INFO] 有候选的事件数: {total_has_cand}")
    print(f"[INFO] 通过基线cuts的事件数: {total_pass_baseline}")
    print(f"[INFO] 窗口内事件数 (0.3<Δφ<0.7): {total_in_window}")
    print(f"[INFO] 窗口内事件数 (0.7<Δφ<1.1): {total_in_window_alt}")
    print(f"[INFO] 窗口内事件数 (0<Δφ<0.3): {total_in_window_low}")
    print(f"[INFO] 窗口内事件数 (0.3<Δφ<0.7, 0.4<Δy<0.8): {total_in_window_dyhi}")
    print(f"[INFO] 失败统计: mass={total_fail_mass}, pt={total_fail_pt}, vtx={total_fail_vtx}, kpt={total_fail_kpt}, muID={total_fail_mu}")
    print(f"[INFO] 径迹误用(μ↔K)剔除事件数: {total_track_misuse}")
    print(f"[INFO] Mu填充: ok={total_mu_fill_ok}, fail={total_mu_fill_fail}, neg_idx={total_mu_idx_neg}, ge_size={total_mu_idx_ge_size}")
    print(f"[INFO] Mu尺寸: size(min,max)=({total_mu_size_min},{total_mu_size_max}), idx_max={total_mu_idx_max}, size0={total_mu_size_zero}")
    rate = 0 if elapsed <= 0 else total_processed / elapsed
    print(f"[INFO] 耗时: {elapsed:.1f}s ({rate:.0f} evt/s)")

    if output_file is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_file = os.path.join(OUTPUT_DIR, "jjp_window_region.root")

    fout = TFile(output_file, "RECREATE")
    for h in histos.values():
        h.Write()
    fout.Close()
    print(f"[INFO] 输出保存到: {output_file}")

    # Plotting
    final_plot_dir = plot_dir
    if final_plot_dir is None:
        base_dir = os.path.dirname(output_file)
        final_plot_dir = os.path.join(base_dir if base_dir else '.', 'plots_JJP_window')
    print(f"[INFO] 保存图像到: {final_plot_dir}")
    save_plots(histos, final_plot_dir)


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='JJP DPS window study (0.3<DeltaPhi<0.7, 0<DeltaY<0.4 for Jpsi2-Phi)')
    parser.add_argument('-n', '--max-events', type=int, default=-1, help='最大处理事件数 (-1=全部)')
    parser.add_argument('--muon-id', type=str, default='soft', choices=['loose', 'medium', 'tight', 'soft', 'none'], help='Muon ID要求')
    parser.add_argument('-i', '--input-dir', type=str, default=None, help='输入Ntuple目录')
    parser.add_argument('-o', '--output', type=str, default=None, help='输出ROOT文件路径')
    parser.add_argument('-p', '--plot-dir', type=str, default=None, help='输出图像目录')
    parser.add_argument('-j', '--jobs', type=int, default=1, help='并行进程数 (默认1)')
    args = parser.parse_args()

    global start_time
    start_time = time.time()

    mu_id = None if args.muon_id == 'none' else args.muon_id

    analyze_jjp_window(max_events=args.max_events,
                       muon_id=mu_id,
                       input_dir=args.input_dir,
                       output_file=args.output,
                       plot_dir=args.plot_dir,
                       n_workers=max(1, args.jobs))


if __name__ == '__main__':
    main()

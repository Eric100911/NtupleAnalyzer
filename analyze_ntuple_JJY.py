#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
J/psi + J/psi + Upsilon(1S) MC ntuple angular-correlation analysis.

The input ntuples are produced by MultiLepPAT with AnalysisMode=JpsiJpsiUps.
The analyzer reads Jpsi_1_*, Jpsi_2_*, Ups_*, Pri_*, and mu* branches from
mkcands/X_data and writes four independent histogram sets:
  - no_vertex: baseline kinematic/ID selection only
  - pri_valid: baseline + valid primary six-body vertex fit
  - pri_vtxprob_gt_0p005: baseline + Pri_VtxProb > 0.005
  - same_mu_vertex: baseline + all six selected muons have the same vertexId
"""

import argparse
import glob
import math
import multiprocessing
import os
import tempfile
import time

import ROOT
from ROOT import TChain, TFile, TH1F, TH2F, TLorentzVector


JJY_MC_PATH_DEFAULT = "/eos/user/c/chiw/JpsiJpsiUps/MC_samples/rootNtuple_refactor/"
TREE_NAME = "mkcands/X_data"

JPSI1_MASS_MIN, JPSI1_MASS_MAX = 2.9, 3.3
JPSI2_MASS_MIN, JPSI2_MASS_MAX = 2.9, 3.3
UPS_MASS_MIN, UPS_MASS_MAX = 8.5, 11.4

JPSI_PT_MIN = 3.0
UPS_PT_MIN = 4.0
JPSI_VTXPROB_MIN = 0.05
UPS_VTXPROB_MIN = 0.10
PRI_VTXPROB_MIN = 0.005

JPSI_SPECTRUM_BINS = 40
JPSI_SPECTRUM_MIN = 2.8
JPSI_SPECTRUM_MAX = 3.4
UPS_SPECTRUM_BINS = 60
UPS_SPECTRUM_MIN = 8.5
UPS_SPECTRUM_MAX = 10.5

MUON_MASS = 0.105658
JPSI_MUON_ID = "soft"
UPS_MUON_ID = "tight"
OUTPUT_DIR = "output"
DEFAULT_WORKERS = max(1, min(8, multiprocessing.cpu_count()))

VERTEX_CATEGORIES = [
    ("no_vertex", "No further vertexing selection"),
    ("pri_valid", "Pri vertex valid"),
    ("pri_vtxprob_gt_0p005", "Pri VtxProb > 0.005"),
    ("same_mu_vertex", "All 6 muons same vertex"),
]


def setup_root():
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)
    ROOT.gStyle.SetOptTitle(0)


def delta_phi(phi1, phi2):
    dphi = phi1 - phi2
    while dphi > math.pi:
        dphi -= 2 * math.pi
    while dphi < -math.pi:
        dphi += 2 * math.pi
    return dphi


def build_vec_from_pxpypz(px, py, pz, mass):
    e = math.sqrt(px * px + py * py + pz * pz + mass * mass)
    vec = TLorentzVector()
    vec.SetPxPyPzE(px, py, pz, e)
    return vec


def check_muon_id(chain, mu_idx, id_type):
    if id_type is None:
        return True

    try:
        idx = int(mu_idx)
        if idx < 0:
            return False
        if id_type == "loose":
            return bool(chain.muIsPatLooseMuon.at(idx))
        if id_type == "medium":
            return bool(chain.muIsPatMediumMuon.at(idx))
        if id_type == "tight":
            return bool(chain.muIsPatTightMuon.at(idx))
        if id_type == "soft":
            return bool(chain.muIsPatSoftMuon.at(idx))
        return True
    except Exception:
        return False


def discover_root_files(input_dir):
    files = glob.glob(os.path.join(input_dir, "**", "*.root"), recursive=True)
    files = [f for f in files if "miniaod" not in os.path.basename(f).lower()]
    ntuples = [f for f in files if "ntuple" in os.path.basename(f).lower()]
    return sorted(ntuples or files)


def hist_name(category, stem):
    return f"h_{category}_{stem}"


def hist2_name(category, stem):
    return f"h2_{category}_{stem}"


def create_histograms(jpsi_mass_bins=JPSI_SPECTRUM_BINS,
                      jpsi_mass_min=JPSI_SPECTRUM_MIN,
                      jpsi_mass_max=JPSI_SPECTRUM_MAX,
                      ups_mass_bins=UPS_SPECTRUM_BINS,
                      ups_mass_min=UPS_SPECTRUM_MIN,
                      ups_mass_max=UPS_SPECTRUM_MAX):
    histograms = {}
    for category, title_suffix in VERTEX_CATEGORIES:
        # 1D angular correlations
        histograms[hist_name(category, "dy_jpsi1_jpsi2")] = TH1F(
            hist_name(category, "dy_jpsi1_jpsi2"),
            f"#Delta y (J/#psi_{{1}} - J/#psi_{{2}});|#Delta y|;Events ({title_suffix})",
            50, 0, 5)
        histograms[hist_name(category, "dy_jpsi1_ups")] = TH1F(
            hist_name(category, "dy_jpsi1_ups"),
            f"#Delta y (J/#psi_{{1}} - #Upsilon);|#Delta y|;Events ({title_suffix})",
            50, 0, 5)
        histograms[hist_name(category, "dy_jpsi2_ups")] = TH1F(
            hist_name(category, "dy_jpsi2_ups"),
            f"#Delta y (J/#psi_{{2}} - #Upsilon);|#Delta y|;Events ({title_suffix})",
            50, 0, 5)

        histograms[hist_name(category, "dphi_jpsi1_jpsi2")] = TH1F(
            hist_name(category, "dphi_jpsi1_jpsi2"),
            f"#Delta#phi (J/#psi_{{1}} - J/#psi_{{2}});|#Delta#phi|;Events ({title_suffix})",
            50, 0, math.pi)
        histograms[hist_name(category, "dphi_jpsi1_ups")] = TH1F(
            hist_name(category, "dphi_jpsi1_ups"),
            f"#Delta#phi (J/#psi_{{1}} - #Upsilon);|#Delta#phi|;Events ({title_suffix})",
            50, 0, math.pi)
        histograms[hist_name(category, "dphi_jpsi2_ups")] = TH1F(
            hist_name(category, "dphi_jpsi2_ups"),
            f"#Delta#phi (J/#psi_{{2}} - #Upsilon);|#Delta#phi|;Events ({title_suffix})",
            50, 0, math.pi)

        # 2D angular correlations
        histograms[hist2_name(category, "dy_dphi_jpsi1_jpsi2")] = TH2F(
            hist2_name(category, "dy_dphi_jpsi1_jpsi2"),
            f"J/#psi_{{1}} - J/#psi_{{2}};|#Delta y|;|#Delta#phi| ({title_suffix})",
            50, 0, 5, 50, 0, math.pi)
        histograms[hist2_name(category, "dy_dphi_jpsi1_ups")] = TH2F(
            hist2_name(category, "dy_dphi_jpsi1_ups"),
            f"J/#psi_{{1}} - #Upsilon;|#Delta y|;|#Delta#phi| ({title_suffix})",
            50, 0, 5, 50, 0, math.pi)
        histograms[hist2_name(category, "dy_dphi_jpsi2_ups")] = TH2F(
            hist2_name(category, "dy_dphi_jpsi2_ups"),
            f"J/#psi_{{2}} - #Upsilon;|#Delta y|;|#Delta#phi| ({title_suffix})",
            50, 0, 5, 50, 0, math.pi)

        # Kinematics
        for particle, label in (
            ("jpsi1", "J/#psi_{1}"),
            ("jpsi2", "J/#psi_{2}"),
            ("ups", "#Upsilon"),
        ):
            histograms[hist_name(category, f"{particle}_pt")] = TH1F(
                hist_name(category, f"{particle}_pt"),
                f"{label} p_{{T}};p_{{T}} [GeV];Events ({title_suffix})",
                100, 0, 50)
            histograms[hist_name(category, f"{particle}_eta")] = TH1F(
                hist_name(category, f"{particle}_eta"),
                f"{label} #eta;#eta;Events ({title_suffix})",
                60, -3, 3)
            histograms[hist_name(category, f"{particle}_y")] = TH1F(
                hist_name(category, f"{particle}_y"),
                f"{label} y;y;Events ({title_suffix})",
                60, -3, 3)
            histograms[hist_name(category, f"{particle}_phi")] = TH1F(
                hist_name(category, f"{particle}_phi"),
                f"{label} #phi;#phi;Events ({title_suffix})",
                60, -math.pi, math.pi)

        # Resonance dimuon mass spectra
        histograms[hist_name(category, "jpsi1_mass")] = TH1F(
            hist_name(category, "jpsi1_mass"),
            f"m(#mu#mu) for J/#psi_{{1}};m(#mu#mu) [GeV];Candidates ({title_suffix})",
            jpsi_mass_bins, jpsi_mass_min, jpsi_mass_max)
        histograms[hist_name(category, "jpsi2_mass")] = TH1F(
            hist_name(category, "jpsi2_mass"),
            f"m(#mu#mu) for J/#psi_{{2}};m(#mu#mu) [GeV];Candidates ({title_suffix})",
            jpsi_mass_bins, jpsi_mass_min, jpsi_mass_max)
        histograms[hist_name(category, "jpsi_mass_all")] = TH1F(
            hist_name(category, "jpsi_mass_all"),
            f"m(#mu#mu) for both J/#psi candidates;m(#mu#mu) [GeV];Candidates ({title_suffix})",
            jpsi_mass_bins, jpsi_mass_min, jpsi_mass_max)
        histograms[hist_name(category, "ups_mass")] = TH1F(
            hist_name(category, "ups_mass"),
            f"m(#mu#mu) for #Upsilon(1S);m(#mu#mu) [GeV];Candidates ({title_suffix})",
            ups_mass_bins, ups_mass_min, ups_mass_max)

        # Composite invariant masses and vertex diagnostics
        histograms[hist_name(category, "mass_jpsi1_jpsi2")] = TH1F(
            hist_name(category, "mass_jpsi1_jpsi2"),
            f"M(J/#psi_{{1}} + J/#psi_{{2}});M [GeV];Events ({title_suffix})",
            100, 6, 30)
        histograms[hist_name(category, "mass_jpsi1_ups")] = TH1F(
            hist_name(category, "mass_jpsi1_ups"),
            f"M(J/#psi_{{1}} + #Upsilon);M [GeV];Events ({title_suffix})",
            100, 10, 35)
        histograms[hist_name(category, "mass_jpsi2_ups")] = TH1F(
            hist_name(category, "mass_jpsi2_ups"),
            f"M(J/#psi_{{2}} + #Upsilon);M [GeV];Events ({title_suffix})",
            100, 10, 35)
        histograms[hist_name(category, "mass_all")] = TH1F(
            hist_name(category, "mass_all"),
            f"M(J/#psi_{{1}} + J/#psi_{{2}} + #Upsilon);M [GeV];Events ({title_suffix})",
            100, 15, 80)
        histograms[hist_name(category, "pri_mass")] = TH1F(
            hist_name(category, "pri_mass"),
            f"Pri fit mass;M [GeV];Events ({title_suffix})",
            100, 15, 80)
        histograms[hist_name(category, "pri_vtxprob")] = TH1F(
            hist_name(category, "pri_vtxprob"),
            f"Pri vertex probability;VtxProb;Events ({title_suffix})",
            100, 0, 1)

    return histograms


def merge_histograms(dest, src):
    for name, hdest in dest.items():
        hsrc = src.Get(name)
        if hsrc:
            hdest.Add(hsrc)


def pri_valid_branch_name(chain):
    if chain.GetBranch("Pri_VtxValid"):
        return "Pri_VtxValid"
    return "Pri_fitValid"


def all_six_muons_same_vertex(chain, mu_indices):
    if not chain.GetBranch("muVertexId"):
        return False
    try:
        vertex_ids = [int(chain.muVertexId.at(idx)) for idx in mu_indices]
    except Exception:
        return False
    return all(vertex_id >= 0 for vertex_id in vertex_ids) and len(set(vertex_ids)) == 1


def fill_histograms(histograms, category, cand):
    jpsi1_4vec = TLorentzVector()
    jpsi2_4vec = TLorentzVector()
    ups_4vec = TLorentzVector()
    jpsi1_4vec.SetPtEtaPhiM(cand["jpsi1_pt"], cand["jpsi1_eta"], cand["jpsi1_phi"], cand["jpsi1_mass"])
    jpsi2_4vec.SetPtEtaPhiM(cand["jpsi2_pt"], cand["jpsi2_eta"], cand["jpsi2_phi"], cand["jpsi2_mass"])
    ups_4vec.SetPtEtaPhiM(cand["ups_pt"], cand["ups_eta"], cand["ups_phi"], cand["ups_mass"])

    y_jpsi1 = jpsi1_4vec.Rapidity()
    y_jpsi2 = jpsi2_4vec.Rapidity()
    y_ups = ups_4vec.Rapidity()

    dy_jpsi1_jpsi2 = abs(y_jpsi1 - y_jpsi2)
    dy_jpsi1_ups = abs(y_jpsi1 - y_ups)
    dy_jpsi2_ups = abs(y_jpsi2 - y_ups)

    dphi_jpsi1_jpsi2 = abs(delta_phi(jpsi1_4vec.Phi(), jpsi2_4vec.Phi()))
    dphi_jpsi1_ups = abs(delta_phi(jpsi1_4vec.Phi(), ups_4vec.Phi()))
    dphi_jpsi2_ups = abs(delta_phi(jpsi2_4vec.Phi(), ups_4vec.Phi()))

    histograms[hist_name(category, "dy_jpsi1_jpsi2")].Fill(dy_jpsi1_jpsi2)
    histograms[hist_name(category, "dy_jpsi1_ups")].Fill(dy_jpsi1_ups)
    histograms[hist_name(category, "dy_jpsi2_ups")].Fill(dy_jpsi2_ups)

    histograms[hist_name(category, "dphi_jpsi1_jpsi2")].Fill(dphi_jpsi1_jpsi2)
    histograms[hist_name(category, "dphi_jpsi1_ups")].Fill(dphi_jpsi1_ups)
    histograms[hist_name(category, "dphi_jpsi2_ups")].Fill(dphi_jpsi2_ups)

    histograms[hist2_name(category, "dy_dphi_jpsi1_jpsi2")].Fill(dy_jpsi1_jpsi2, dphi_jpsi1_jpsi2)
    histograms[hist2_name(category, "dy_dphi_jpsi1_ups")].Fill(dy_jpsi1_ups, dphi_jpsi1_ups)
    histograms[hist2_name(category, "dy_dphi_jpsi2_ups")].Fill(dy_jpsi2_ups, dphi_jpsi2_ups)

    for particle, vec in (("jpsi1", jpsi1_4vec), ("jpsi2", jpsi2_4vec), ("ups", ups_4vec)):
        histograms[hist_name(category, f"{particle}_pt")].Fill(vec.Pt())
        histograms[hist_name(category, f"{particle}_eta")].Fill(vec.Eta())
        histograms[hist_name(category, f"{particle}_y")].Fill(vec.Rapidity())
        histograms[hist_name(category, f"{particle}_phi")].Fill(vec.Phi())

    histograms[hist_name(category, "mass_jpsi1_jpsi2")].Fill((jpsi1_4vec + jpsi2_4vec).M())
    histograms[hist_name(category, "mass_jpsi1_ups")].Fill((jpsi1_4vec + ups_4vec).M())
    histograms[hist_name(category, "mass_jpsi2_ups")].Fill((jpsi2_4vec + ups_4vec).M())
    histograms[hist_name(category, "mass_all")].Fill((jpsi1_4vec + jpsi2_4vec + ups_4vec).M())
    histograms[hist_name(category, "jpsi1_mass")].Fill(cand["jpsi1_mass"])
    histograms[hist_name(category, "jpsi2_mass")].Fill(cand["jpsi2_mass"])
    histograms[hist_name(category, "jpsi_mass_all")].Fill(cand["jpsi1_mass"])
    histograms[hist_name(category, "jpsi_mass_all")].Fill(cand["jpsi2_mass"])
    histograms[hist_name(category, "ups_mass")].Fill(cand["ups_mass"])
    histograms[hist_name(category, "pri_mass")].Fill(cand["pri_mass"])
    histograms[hist_name(category, "pri_vtxprob")].Fill(cand["pri_vtxprob"])


def process_file_batch(file_list, max_events, jpsi_muon_id, ups_muon_id, tree_name,
                       jpsi_mass_bins, jpsi_mass_min, jpsi_mass_max,
                       ups_mass_bins, ups_mass_min, ups_mass_max):
    chain = TChain(tree_name)
    for f in file_list:
        chain.Add(f)

    histograms = create_histograms(
        jpsi_mass_bins, jpsi_mass_min, jpsi_mass_max,
        ups_mass_bins, ups_mass_min, ups_mass_max)
    valid_branch = pri_valid_branch_name(chain)
    n_total = chain.GetEntries()
    n_to_process = n_total if max_events < 0 else min(max_events, n_total)
    selected = {category: 0 for category, _ in VERTEX_CATEGORIES}
    n_baseline_candidates = 0
    n_bad_muon_indices = 0
    n_duplicate_muons = 0

    for i_evt in range(n_to_process):
        chain.GetEntry(i_evt)
        try:
            n_cand = chain.Jpsi_1_mass.size()
        except Exception:
            continue
        if n_cand == 0:
            continue

        best_by_category = {category: None for category, _ in VERTEX_CATEGORIES}

        for i_cand in range(n_cand):
            try:
                jpsi1_mass = chain.Jpsi_1_mass.at(i_cand)
                jpsi2_mass = chain.Jpsi_2_mass.at(i_cand)
                ups_mass = chain.Ups_mass.at(i_cand)

                if not (JPSI1_MASS_MIN < jpsi1_mass < JPSI1_MASS_MAX):
                    continue
                if not (JPSI2_MASS_MIN < jpsi2_mass < JPSI2_MASS_MAX):
                    continue
                if not (UPS_MASS_MIN < ups_mass < UPS_MASS_MAX):
                    continue

                jpsi1_pt = chain.Jpsi_1_pt.at(i_cand)
                jpsi2_pt = chain.Jpsi_2_pt.at(i_cand)
                ups_pt = chain.Ups_pt.at(i_cand)
                if jpsi1_pt < JPSI_PT_MIN or jpsi2_pt < JPSI_PT_MIN or ups_pt < UPS_PT_MIN:
                    continue

                if chain.Jpsi_1_VtxProb.at(i_cand) < JPSI_VTXPROB_MIN:
                    continue
                if chain.Jpsi_2_VtxProb.at(i_cand) < JPSI_VTXPROB_MIN:
                    continue
                if chain.Ups_VtxProb.at(i_cand) < UPS_VTXPROB_MIN:
                    continue

                mu_indices = [
                    int(chain.Jpsi_1_mu_1_Idx.at(i_cand)),
                    int(chain.Jpsi_1_mu_2_Idx.at(i_cand)),
                    int(chain.Jpsi_2_mu_1_Idx.at(i_cand)),
                    int(chain.Jpsi_2_mu_2_Idx.at(i_cand)),
                    int(chain.Ups_mu_1_Idx.at(i_cand)),
                    int(chain.Ups_mu_2_Idx.at(i_cand)),
                ]
                if min(mu_indices) < 0 or max(mu_indices) >= chain.muPx.size():
                    n_bad_muon_indices += 1
                    continue
                if len(set(mu_indices)) != 6:
                    n_duplicate_muons += 1
                    continue

                if jpsi_muon_id:
                    if not all(check_muon_id(chain, idx, jpsi_muon_id) for idx in mu_indices[:4]):
                        continue
                if ups_muon_id:
                    if not all(check_muon_id(chain, idx, ups_muon_id) for idx in mu_indices[4:]):
                        continue

                n_baseline_candidates += 1
                pri_valid = bool(getattr(chain, valid_branch).at(i_cand))
                pri_vtxprob = chain.Pri_VtxProb.at(i_cand)
                same_mu_vertex = all_six_muons_same_vertex(chain, mu_indices)
                score = math.sqrt(jpsi1_pt**2 + jpsi2_pt**2 + ups_pt**2)

                cand = {
                    "score": score,
                    "jpsi1_pt": jpsi1_pt,
                    "jpsi1_eta": chain.Jpsi_1_eta.at(i_cand),
                    "jpsi1_phi": chain.Jpsi_1_phi.at(i_cand),
                    "jpsi1_mass": jpsi1_mass,
                    "jpsi2_pt": jpsi2_pt,
                    "jpsi2_eta": chain.Jpsi_2_eta.at(i_cand),
                    "jpsi2_phi": chain.Jpsi_2_phi.at(i_cand),
                    "jpsi2_mass": jpsi2_mass,
                    "ups_pt": ups_pt,
                    "ups_eta": chain.Ups_eta.at(i_cand),
                    "ups_phi": chain.Ups_phi.at(i_cand),
                    "ups_mass": ups_mass,
                    "pri_mass": chain.Pri_mass.at(i_cand),
                    "pri_vtxprob": pri_vtxprob,
                    "pri_valid": pri_valid,
                    "same_mu_vertex": same_mu_vertex,
                }

                category_pass = {
                    "no_vertex": True,
                    "pri_valid": pri_valid,
                    "pri_vtxprob_gt_0p005": pri_vtxprob > PRI_VTXPROB_MIN,
                    "same_mu_vertex": same_mu_vertex,
                }
                for category, passes in category_pass.items():
                    if not passes:
                        continue
                    if best_by_category[category] is None or score > best_by_category[category]["score"]:
                        best_by_category[category] = cand
            except Exception:
                continue

        for category, cand in best_by_category.items():
            if cand is None:
                continue
            fill_histograms(histograms, category, cand)
            selected[category] += 1

    fd, tmp_path = tempfile.mkstemp(suffix=".root", prefix="jjy_ntuple_tmp_")
    os.close(fd)
    fout = TFile(tmp_path, "RECREATE")
    for h in histograms.values():
        h.Write()
    fout.Close()

    stats = {
        "processed": n_to_process,
        "selected": selected,
        "baseline_candidates": n_baseline_candidates,
        "bad_muon_indices": n_bad_muon_indices,
        "duplicate_muons": n_duplicate_muons,
    }
    return tmp_path, stats


def analyze_jjy_ntuple(max_events=-1, jpsi_muon_id="soft", ups_muon_id="tight",
                       output_file=None, input_dir=None, n_workers=1,
                       jpsi_mass_bins=JPSI_SPECTRUM_BINS,
                       jpsi_mass_min=JPSI_SPECTRUM_MIN,
                       jpsi_mass_max=JPSI_SPECTRUM_MAX,
                       ups_mass_bins=UPS_SPECTRUM_BINS,
                       ups_mass_min=UPS_SPECTRUM_MIN,
                       ups_mass_max=UPS_SPECTRUM_MAX):
    print("\n" + "=" * 60)
    print("J/psi + J/psi + Upsilon(1S) MC Ntuple angular-correlation analysis")
    print("=" * 60)
    start_time = time.time()

    data_path = input_dir if input_dir else JJY_MC_PATH_DEFAULT
    data_files = discover_root_files(data_path)
    print(f"[INFO] Data path: {data_path}")
    print(f"[INFO] Loaded {len(data_files)} ROOT files")
    print(f"[INFO] J/psi mass spectrum binning: {jpsi_mass_bins} bins, [{jpsi_mass_min}, {jpsi_mass_max}] GeV")
    print(f"[INFO] Upsilon mass spectrum binning: {ups_mass_bins} bins, [{ups_mass_min}, {ups_mass_max}] GeV")

    if not data_files:
        print("[ERROR] No input ROOT files found")
        return None

    n_workers = max(1, min(n_workers, len(data_files)))
    if n_workers <= 1:
        results = [process_file_batch(
            data_files, max_events, jpsi_muon_id, ups_muon_id, TREE_NAME,
            jpsi_mass_bins, jpsi_mass_min, jpsi_mass_max,
            ups_mass_bins, ups_mass_min, ups_mass_max)]
    else:
        batches = [[] for _ in range(n_workers)]
        for idx, filename in enumerate(data_files):
            batches[idx % n_workers].append(filename)
        batches = [batch for batch in batches if batch]
        per_batch_events = -1 if max_events < 0 else math.ceil(max_events / len(batches))
        with multiprocessing.Pool(processes=len(batches)) as pool:
            results = pool.starmap(
                process_file_batch,
                [(batch, per_batch_events, jpsi_muon_id, ups_muon_id, TREE_NAME,
                  jpsi_mass_bins, jpsi_mass_min, jpsi_mass_max,
                  ups_mass_bins, ups_mass_min, ups_mass_max) for batch in batches],
            )

    histograms = create_histograms(
        jpsi_mass_bins, jpsi_mass_min, jpsi_mass_max,
        ups_mass_bins, ups_mass_min, ups_mass_max)
    total_processed = 0
    total_selected = {category: 0 for category, _ in VERTEX_CATEGORIES}
    baseline_candidates = 0
    bad_muon_indices = 0
    duplicate_muons = 0

    for tmp_path, stats in results:
        fin = TFile.Open(tmp_path)
        if fin and not fin.IsZombie():
            merge_histograms(histograms, fin)
        if fin:
            fin.Close()
        os.remove(tmp_path)

        total_processed += stats["processed"]
        baseline_candidates += stats["baseline_candidates"]
        bad_muon_indices += stats["bad_muon_indices"]
        duplicate_muons += stats["duplicate_muons"]
        for category in total_selected:
            total_selected[category] += stats["selected"][category]

    elapsed = time.time() - start_time
    n_to_process = total_processed if max_events < 0 else min(max_events, total_processed)
    print("\n[INFO] Processing complete")
    print(f"[INFO] Processed events: {n_to_process}")
    print(f"[INFO] Baseline candidates after mass/pT/ID cuts: {baseline_candidates}")
    print(f"[INFO] Bad muon-index candidates: {bad_muon_indices}")
    print(f"[INFO] Duplicate-muon candidates: {duplicate_muons}")
    for category, label in VERTEX_CATEGORIES:
        eff = 0 if n_to_process == 0 else 100 * total_selected[category] / n_to_process
        print(f"[INFO] {label}: {total_selected[category]} events ({eff:.3f}%)")
    rate = 0 if elapsed <= 0 else total_processed / elapsed
    print(f"[INFO] Elapsed: {elapsed:.1f}s ({rate:.0f} evt/s)")

    if output_file is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_file = os.path.join(OUTPUT_DIR, "jjy_mc_DPS_Jpsi_JpsiY_correlations.root")

    out_dir = os.path.dirname(output_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    fout = TFile(output_file, "RECREATE")
    for h in histograms.values():
        h.Write()
    fout.Close()

    print(f"[INFO] Output saved to: {output_file}")
    return histograms


def main():
    parser = argparse.ArgumentParser(description="JJY MC Ntuple angular-correlation analysis")
    parser.add_argument("-n", "--max-events", type=int, default=-1,
                        help="Maximum events to process (-1=all)")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Output ROOT file")
    parser.add_argument("-i", "--input-dir", type=str, default=None,
                        help="Input ntuple directory")
    parser.add_argument("--jpsi-muon-id", type=str, default="soft",
                        choices=["loose", "medium", "tight", "soft", "none"],
                        help="J/psi muon ID requirement")
    parser.add_argument("--ups-muon-id", type=str, default="tight",
                        choices=["loose", "medium", "tight", "soft", "none"],
                        help="Upsilon muon ID requirement")
    parser.add_argument("-j", "--jobs", type=int, default=1,
                        help="Number of parallel processes")
    parser.add_argument("--jpsi-mass-bins", type=int, default=JPSI_SPECTRUM_BINS,
                        help="Number of bins for J/psi dimuon mass spectra")
    parser.add_argument("--jpsi-mass-min", type=float, default=JPSI_SPECTRUM_MIN,
                        help="Lower edge for J/psi dimuon mass spectra [GeV]")
    parser.add_argument("--jpsi-mass-max", type=float, default=JPSI_SPECTRUM_MAX,
                        help="Upper edge for J/psi dimuon mass spectra [GeV]")
    parser.add_argument("--ups-mass-bins", type=int, default=UPS_SPECTRUM_BINS,
                        help="Number of bins for Upsilon dimuon mass spectra")
    parser.add_argument("--ups-mass-min", type=float, default=UPS_SPECTRUM_MIN,
                        help="Lower edge for Upsilon dimuon mass spectra [GeV]")
    parser.add_argument("--ups-mass-max", type=float, default=UPS_SPECTRUM_MAX,
                        help="Upper edge for Upsilon dimuon mass spectra [GeV]")
    args = parser.parse_args()

    if args.jpsi_mass_bins <= 0 or args.ups_mass_bins <= 0:
        parser.error("Mass spectrum bin counts must be positive")
    if args.jpsi_mass_min >= args.jpsi_mass_max:
        parser.error("--jpsi-mass-min must be smaller than --jpsi-mass-max")
    if args.ups_mass_min >= args.ups_mass_max:
        parser.error("--ups-mass-min must be smaller than --ups-mass-max")

    setup_root()
    jpsi_muon_id = None if args.jpsi_muon_id == "none" else args.jpsi_muon_id
    ups_muon_id = None if args.ups_muon_id == "none" else args.ups_muon_id

    result = analyze_jjy_ntuple(
        max_events=args.max_events,
        jpsi_muon_id=jpsi_muon_id,
        ups_muon_id=ups_muon_id,
        output_file=args.output,
        input_dir=args.input_dir,
        n_workers=args.jobs,
        jpsi_mass_bins=args.jpsi_mass_bins,
        jpsi_mass_min=args.jpsi_mass_min,
        jpsi_mass_max=args.jpsi_mass_max,
        ups_mass_bins=args.ups_mass_bins,
        ups_mass_min=args.ups_mass_min,
        ups_mass_max=args.ups_mass_max,
    )
    if result is None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

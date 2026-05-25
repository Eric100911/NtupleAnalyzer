#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
J/psi + J/psi + Phi (JJP) Ntuple角度关联分析

功能:
1. 从Ntuple加载数据并应用事件选择cuts
2. 计算粒子之间的角度关联 (Δy, Δφ)
3. 填充直方图并保存

使用方法:
    python analyze_ntuple_JJP.py -o output_jjp.root
    python analyze_ntuple_JJP.py -n 10000  # 处理前10000个事件
    python analyze_ntuple_JJP.py --muon-id soft  # 指定muon ID
"""

import ROOT
from ROOT import TFile, TChain, TH1F, TH2F, TLorentzVector
import os
import math
import argparse
import glob
import time
import tempfile
import multiprocessing

# =============================================================================
# 配置参数
# =============================================================================

# 数据路径 (默认可被 --input-dir 覆盖)
JJP_DATA_PATH_DEFAULT = "/eos/user/c/chiw/JpsiJpsiPhi/rootNtuple"
JJP_DATASET_DIRS = tuple(f"ParkingDoubleMuonLowMass{i}" for i in range(8))
JJP_REFACTOR_PREFIX = "crab3_refactor"
JJP_SUBMIT_PREFIX = "260411"
TREE_NAME = "mkcands/X_data"

# 质量窗口
JPSI1_MASS_MIN, JPSI1_MASS_MAX = 2.9, 3.3
JPSI2_MASS_MIN, JPSI2_MASS_MAX = 2.9, 3.3
PHI_MASS_MIN, PHI_MASS_MAX = 0.99, 1.10

# Cuts 参数
JPSI_PT_MIN = 3.0
JPSI_VTXPROB_MIN = 0.05
PHI_PT_MIN = 2.0
PHI_VTXPROB_MIN = 0.05
PHI_K_PT_MIN = 2.0

# Track-misuse veto thresholds (muon vs kaon)
TRACK_DR_MAX = 0.005
TRACK_RELPT_MAX = 0.01

# Particle masses for 4-vector building
MUON_MASS = 0.105658
KAON_MASS = 0.493677

# Muon ID 选择
JPSI_MUON_ID = 'soft'
DEFAULT_WORKERS = max(1, min(8, multiprocessing.cpu_count()))

# 输出目录
OUTPUT_DIR = "/eos/user/x/xcheng/CMSSW_14_0_18/src/NtupleAnalyzer/output/"


# =============================================================================
# 辅助函数
# =============================================================================

def setup_root():
    """配置ROOT环境"""
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)
    ROOT.gStyle.SetOptTitle(0)


def delta_phi(phi1, phi2):
    """计算Δφ，包装到[-π, π]"""
    dphi = phi1 - phi2
    while dphi > math.pi:
        dphi -= 2 * math.pi
    while dphi < -math.pi:
        dphi += 2 * math.pi
    return dphi


def rapidity_from_4vec(pt, eta, phi, mass):
    """从pT, η, φ, m计算快度y"""
    vec = TLorentzVector()
    vec.SetPtEtaPhiM(pt, eta, phi, mass)
    return vec.Rapidity()


def build_vec_from_pxpypz(px, py, pz, mass):
    e = math.sqrt(px * px + py * py + pz * pz + mass * mass)
    vec = TLorentzVector()
    vec.SetPxPyPzE(px, py, pz, e)
    return vec


def check_muon_id(chain, mu_idx, id_type):
    """检查muon是否通过ID选择"""
    if id_type is None:
        return True
    
    try:
        idx = int(mu_idx)
        if idx < 0:
            return False
        
        if id_type == 'loose':
            return chain.muIsPatLooseMuon.at(idx)
        elif id_type == 'medium':
            return chain.muIsPatMediumMuon.at(idx)
        elif id_type == 'tight':
            return chain.muIsPatTightMuon.at(idx)
        elif id_type == 'soft':
            return chain.muIsPatSoftMuon.at(idx)
        else:
            return True
    except:
        return False


def create_histograms():
    """创建所有直方图"""
    histograms = {}
    
    # 1D: Δy (快度差)
    histograms['h_dy_jpsi1_jpsi2'] = TH1F("h_dy_jpsi1_jpsi2",
        "#Delta y (J/#psi_{1} - J/#psi_{2});|#Delta y|;Events", 50, 0, 5)
    histograms['h_dy_jpsi1_phi'] = TH1F("h_dy_jpsi1_phi",
        "#Delta y (J/#psi_{1} - #phi);|#Delta y|;Events", 50, 0, 5)
    histograms['h_dy_jpsi2_phi'] = TH1F("h_dy_jpsi2_phi",
        "#Delta y (J/#psi_{2} - #phi);|#Delta y|;Events", 50, 0, 5)
    
    # 1D: Δφ (方位角差)
    histograms['h_dphi_jpsi1_jpsi2'] = TH1F("h_dphi_jpsi1_jpsi2",
        "#Delta#phi (J/#psi_{1} - J/#psi_{2});|#Delta#phi|;Events", 50, 0, math.pi)
    histograms['h_dphi_jpsi1_phi'] = TH1F("h_dphi_jpsi1_phi",
        "#Delta#phi (J/#psi_{1} - #phi);|#Delta#phi|;Events", 50, 0, math.pi)
    histograms['h_dphi_jpsi2_phi'] = TH1F("h_dphi_jpsi2_phi",
        "#Delta#phi (J/#psi_{2} - #phi);|#Delta#phi|;Events", 50, 0, math.pi)
    
    # 2D: Δy vs Δφ
    histograms['h2_dy_dphi_jpsi1_jpsi2'] = TH2F("h2_dy_dphi_jpsi1_jpsi2",
        "J/#psi_{1} - J/#psi_{2};|#Delta y|;|#Delta#phi|", 50, 0, 5, 50, 0, math.pi)
    histograms['h2_dy_dphi_jpsi1_phi'] = TH2F("h2_dy_dphi_jpsi1_phi",
        "J/#psi_{1} - #phi;|#Delta y|;|#Delta#phi|", 50, 0, 5, 50, 0, math.pi)
    histograms['h2_dy_dphi_jpsi2_phi'] = TH2F("h2_dy_dphi_jpsi2_phi",
        "J/#psi_{2} - #phi;|#Delta y|;|#Delta#phi|", 50, 0, 5, 50, 0, math.pi)
    
    # 运动学分布: pT
    histograms['h_jpsi1_pt'] = TH1F("h_jpsi1_pt",
        "J/#psi_{1} p_{T};p_{T} [GeV];Events", 100, 0, 50)
    histograms['h_jpsi2_pt'] = TH1F("h_jpsi2_pt",
        "J/#psi_{2} p_{T};p_{T} [GeV];Events", 100, 0, 50)
    histograms['h_phi_pt'] = TH1F("h_phi_pt",
        "#phi p_{T};p_{T} [GeV];Events", 100, 0, 50)
    
    # 运动学分布: η
    histograms['h_jpsi1_eta'] = TH1F("h_jpsi1_eta",
        "J/#psi_{1} #eta;#eta;Events", 60, -3, 3)
    histograms['h_jpsi2_eta'] = TH1F("h_jpsi2_eta",
        "J/#psi_{2} #eta;#eta;Events", 60, -3, 3)
    histograms['h_phi_eta'] = TH1F("h_phi_eta",
        "#phi #eta;#eta;Events", 60, -3, 3)
    
    # 运动学分布: y (快度)
    histograms['h_jpsi1_y'] = TH1F("h_jpsi1_y",
        "J/#psi_{1} y;y;Events", 60, -3, 3)
    histograms['h_jpsi2_y'] = TH1F("h_jpsi2_y",
        "J/#psi_{2} y;y;Events", 60, -3, 3)
    histograms['h_phi_y'] = TH1F("h_phi_y",
        "#phi y;y;Events", 60, -3, 3)
    
    # 运动学分布: φ (方位角)
    histograms['h_jpsi1_phi'] = TH1F("h_jpsi1_phi",
        "J/#psi_{1} #phi;#phi;Events", 60, -math.pi, math.pi)
    histograms['h_jpsi2_phi'] = TH1F("h_jpsi2_phi",
        "J/#psi_{2} #phi;#phi;Events", 60, -math.pi, math.pi)
    histograms['h_phi_phi'] = TH1F("h_phi_phi",
        "#phi #phi;#phi;Events", 60, -math.pi, math.pi)
    
    # 不变质量分布
    histograms['h_mass_jpsi1_jpsi2'] = TH1F("h_mass_jpsi1_jpsi2",
        "M(J/#psi_{1} + J/#psi_{2});M [GeV];Events", 100, 6, 30)
    histograms['h_mass_jpsi1_phi'] = TH1F("h_mass_jpsi1_phi",
        "M(J/#psi_{1} + #phi);M [GeV];Events", 100, 3, 20)
    histograms['h_mass_jpsi2_phi'] = TH1F("h_mass_jpsi2_phi",
        "M(J/#psi_{2} + #phi);M [GeV];Events", 100, 3, 20)
    histograms['h_mass_all'] = TH1F("h_mass_all",
        "M(J/#psi_{1} + J/#psi_{2} + #phi);M [GeV];Events", 100, 7, 40)
    
    return histograms


def discover_jjp_input_files(data_path):
    if os.path.isfile(data_path) and data_path.lower().endswith(".root"):
        return [data_path]

    files = []
    for dataset_dir in JJP_DATASET_DIRS:
        base_dir = os.path.join(data_path, dataset_dir)
        if not os.path.isdir(base_dir):
            continue

        task_dirs = sorted(glob.glob(os.path.join(base_dir, f"{JJP_REFACTOR_PREFIX}*")))
        for task_dir in task_dirs:
            if not os.path.isdir(task_dir):
                continue

            submit_dirs = sorted(glob.glob(os.path.join(task_dir, f"{JJP_SUBMIT_PREFIX}*")))
            for submit_dir in submit_dirs:
                if not os.path.isdir(submit_dir):
                    continue
                files.extend(sorted(glob.glob(os.path.join(submit_dir, "**", "*.root"), recursive=True)))

    if files:
        return files

    return sorted(glob.glob(os.path.join(data_path, "*.root")))


def merge_histograms(dest, src):
    """Add contents of src histograms into dest histograms in-place."""
    for name, hdest in dest.items():
        hsrc = src.Get(name)
        if hsrc:
            hdest.Add(hsrc)


def process_file_batch(file_list, max_events, muon_id, tree_name):
    """Worker: process a list of files, return temp ROOT path and stats."""
    chain = TChain(tree_name)
    for f in file_list:
        chain.Add(f)

    histos = create_histograms()
    n_total = chain.GetEntries()
    n_to_process = n_total if max_events < 0 else min(max_events, n_total)
    n_passed = 0
    n_track_misuse = 0

    for i_evt in range(n_to_process):
        chain.GetEntry(i_evt)
        try:
            n_cand = chain.Jpsi_1_mass.size()
        except:
            continue
        if n_cand == 0:
            continue

        best_cand = None
        best_score = -1

        for i_cand in range(n_cand):
            try:
                jpsi1_mass = chain.Jpsi_1_mass.at(i_cand)
                jpsi2_mass = chain.Jpsi_2_mass.at(i_cand)
                phi_mass = chain.Phi_mass.at(i_cand)

                if not (JPSI1_MASS_MIN < jpsi1_mass < JPSI1_MASS_MAX):
                    continue
                if not (JPSI2_MASS_MIN < jpsi2_mass < JPSI2_MASS_MAX):
                    continue
                if not (PHI_MASS_MIN < phi_mass < PHI_MASS_MAX):
                    continue

                jpsi1_pt = chain.Jpsi_1_pt.at(i_cand)
                jpsi2_pt = chain.Jpsi_2_pt.at(i_cand)
                phi_pt = chain.Phi_pt.at(i_cand)
                if jpsi1_pt < JPSI_PT_MIN or jpsi2_pt < JPSI_PT_MIN or phi_pt < PHI_PT_MIN:
                    continue

                jpsi1_vtxprob = chain.Jpsi_1_VtxProb.at(i_cand)
                jpsi2_vtxprob = chain.Jpsi_2_VtxProb.at(i_cand)
                phi_vtxprob = chain.Phi_VtxProb.at(i_cand)
                if jpsi1_vtxprob < JPSI_VTXPROB_MIN or jpsi2_vtxprob < JPSI_VTXPROB_MIN or phi_vtxprob < PHI_VTXPROB_MIN:
                    continue

                phi_k1_pt = chain.Phi_K_1_pt.at(i_cand)
                phi_k2_pt = chain.Phi_K_2_pt.at(i_cand)
                if phi_k1_pt < PHI_K_PT_MIN or phi_k2_pt < PHI_K_PT_MIN:
                    continue

                jpsi1_mu1_idx = chain.Jpsi_1_mu_1_Idx.at(i_cand)
                jpsi1_mu2_idx = chain.Jpsi_1_mu_2_Idx.at(i_cand)
                jpsi2_mu1_idx = chain.Jpsi_2_mu_1_Idx.at(i_cand)
                jpsi2_mu2_idx = chain.Jpsi_2_mu_2_Idx.at(i_cand)
                if muon_id:
                    if not (check_muon_id(chain, jpsi1_mu1_idx, muon_id) and
                            check_muon_id(chain, jpsi1_mu2_idx, muon_id) and
                            check_muon_id(chain, jpsi2_mu1_idx, muon_id) and
                            check_muon_id(chain, jpsi2_mu2_idx, muon_id)):
                        continue

                jpsi1_eta = chain.Jpsi_1_eta.at(i_cand)
                jpsi1_phi = chain.Jpsi_1_phi.at(i_cand)
                jpsi2_eta = chain.Jpsi_2_eta.at(i_cand)
                jpsi2_phi = chain.Jpsi_2_phi.at(i_cand)
                phi_eta = chain.Phi_eta.at(i_cand)
                phi_phi = chain.Phi_phi.at(i_cand)

                score = math.sqrt(jpsi1_pt**2 + jpsi2_pt**2 + phi_pt**2)
                if score > best_score:
                    best_score = score
                    best_cand = {
                        'jpsi1_pt': jpsi1_pt, 'jpsi1_eta': jpsi1_eta, 'jpsi1_phi': jpsi1_phi, 'jpsi1_mass': jpsi1_mass,
                        'jpsi2_pt': jpsi2_pt, 'jpsi2_eta': jpsi2_eta, 'jpsi2_phi': jpsi2_phi, 'jpsi2_mass': jpsi2_mass,
                        'phi_pt': phi_pt, 'phi_eta': phi_eta, 'phi_phi': phi_phi, 'phi_mass': phi_mass,
                        'jpsi1_mu1_idx': int(jpsi1_mu1_idx), 'jpsi1_mu2_idx': int(jpsi1_mu2_idx),
                        'jpsi2_mu1_idx': int(jpsi2_mu1_idx), 'jpsi2_mu2_idx': int(jpsi2_mu2_idx),
                        'phi_k1_px': chain.Phi_K_1_px.at(i_cand), 'phi_k1_py': chain.Phi_K_1_py.at(i_cand), 'phi_k1_pz': chain.Phi_K_1_pz.at(i_cand),
                        'phi_k2_px': chain.Phi_K_2_px.at(i_cand), 'phi_k2_py': chain.Phi_K_2_py.at(i_cand), 'phi_k2_pz': chain.Phi_K_2_pz.at(i_cand),
                        'phi_k1_pt': phi_k1_pt, 'phi_k2_pt': phi_k2_pt,
                        'phi_k1_eta': chain.Phi_K_1_eta.at(i_cand), 'phi_k1_phi': chain.Phi_K_1_phi.at(i_cand),
                        'phi_k2_eta': chain.Phi_K_2_eta.at(i_cand), 'phi_k2_phi': chain.Phi_K_2_phi.at(i_cand),
                    }
            except Exception:
                continue

        if best_cand is not None:
            # Validate muon indices for safety
            try:
                mu_size = chain.muPx.size()
                idxs = [best_cand['jpsi1_mu1_idx'], best_cand['jpsi1_mu2_idx'],
                        best_cand['jpsi2_mu1_idx'], best_cand['jpsi2_mu2_idx']]
                if any(idx < 0 for idx in idxs) or any(idx >= mu_size for idx in idxs):
                    continue

                mu1_vec = build_vec_from_pxpypz(chain.muPx.at(best_cand['jpsi1_mu1_idx']),
                                                chain.muPy.at(best_cand['jpsi1_mu1_idx']),
                                                chain.muPz.at(best_cand['jpsi1_mu1_idx']), MUON_MASS)
                mu2_vec = build_vec_from_pxpypz(chain.muPx.at(best_cand['jpsi1_mu2_idx']),
                                                chain.muPy.at(best_cand['jpsi1_mu2_idx']),
                                                chain.muPz.at(best_cand['jpsi1_mu2_idx']), MUON_MASS)
                mu3_vec = build_vec_from_pxpypz(chain.muPx.at(best_cand['jpsi2_mu1_idx']),
                                                chain.muPy.at(best_cand['jpsi2_mu1_idx']),
                                                chain.muPz.at(best_cand['jpsi2_mu1_idx']), MUON_MASS)
                mu4_vec = build_vec_from_pxpypz(chain.muPx.at(best_cand['jpsi2_mu2_idx']),
                                                chain.muPy.at(best_cand['jpsi2_mu2_idx']),
                                                chain.muPz.at(best_cand['jpsi2_mu2_idx']), MUON_MASS)
            except Exception:
                continue

            k1_vec = build_vec_from_pxpypz(best_cand['phi_k1_px'], best_cand['phi_k1_py'], best_cand['phi_k1_pz'], KAON_MASS)
            k2_vec = build_vec_from_pxpypz(best_cand['phi_k2_px'], best_cand['phi_k2_py'], best_cand['phi_k2_pz'], KAON_MASS)

            # Track-misuse veto: all muons (Jpsi1 & Jpsi2) vs Phi kaons
            track_misuse = False
            for mu_vec in (mu1_vec, mu2_vec, mu3_vec, mu4_vec):
                for k_vec in (k1_vec, k2_vec):
                    deta = mu_vec.Eta() - k_vec.Eta()
                    dphi = delta_phi(mu_vec.Phi(), k_vec.Phi())
                    dr = math.sqrt(deta * deta + dphi * dphi)
                    abs_dpt = abs(mu_vec.Pt() - k_vec.Pt())
                    rel_dpt = abs_dpt / mu_vec.Pt() if mu_vec.Pt() > 0 else 1e9
                    if dr < TRACK_DR_MAX and rel_dpt < TRACK_RELPT_MAX:
                        track_misuse = True
                        break
                if track_misuse:
                    break

            if track_misuse:
                n_track_misuse += 1
                continue

            jpsi1_4vec = TLorentzVector()
            jpsi2_4vec = TLorentzVector()
            phi_4vec = TLorentzVector()
            jpsi1_4vec.SetPtEtaPhiM(best_cand['jpsi1_pt'], best_cand['jpsi1_eta'], best_cand['jpsi1_phi'], best_cand['jpsi1_mass'])
            jpsi2_4vec.SetPtEtaPhiM(best_cand['jpsi2_pt'], best_cand['jpsi2_eta'], best_cand['jpsi2_phi'], best_cand['jpsi2_mass'])
            phi_4vec.SetPtEtaPhiM(best_cand['phi_pt'], best_cand['phi_eta'], best_cand['phi_phi'], best_cand['phi_mass'])
            fill_histograms(histos, jpsi1_4vec, jpsi2_4vec, phi_4vec)
            n_passed += 1

    # write temp file
    fd, tmp_path = tempfile.mkstemp(suffix=".root", prefix="jjp_ntuple_tmp_")
    os.close(fd)
    fout = TFile(tmp_path, "RECREATE")
    for h in histos.values():
        h.Write()
    fout.Close()

    return tmp_path, n_to_process, n_passed, n_track_misuse


def fill_histograms(histograms, jpsi1_4vec, jpsi2_4vec, phi_4vec):
    """填充所有直方图"""
    # 计算快度
    y_jpsi1 = jpsi1_4vec.Rapidity()
    y_jpsi2 = jpsi2_4vec.Rapidity()
    y_phi = phi_4vec.Rapidity()
    
    # 计算Δy
    dy_jpsi1_jpsi2 = abs(y_jpsi1 - y_jpsi2)
    dy_jpsi1_phi = abs(y_jpsi1 - y_phi)
    dy_jpsi2_phi = abs(y_jpsi2 - y_phi)
    
    # 计算Δφ
    dphi_jpsi1_jpsi2 = abs(delta_phi(jpsi1_4vec.Phi(), jpsi2_4vec.Phi()))
    dphi_jpsi1_phi = abs(delta_phi(jpsi1_4vec.Phi(), phi_4vec.Phi()))
    dphi_jpsi2_phi = abs(delta_phi(jpsi2_4vec.Phi(), phi_4vec.Phi()))
    
    # 填充1D直方图
    histograms['h_dy_jpsi1_jpsi2'].Fill(dy_jpsi1_jpsi2)
    histograms['h_dy_jpsi1_phi'].Fill(dy_jpsi1_phi)
    histograms['h_dy_jpsi2_phi'].Fill(dy_jpsi2_phi)
    
    histograms['h_dphi_jpsi1_jpsi2'].Fill(dphi_jpsi1_jpsi2)
    histograms['h_dphi_jpsi1_phi'].Fill(dphi_jpsi1_phi)
    histograms['h_dphi_jpsi2_phi'].Fill(dphi_jpsi2_phi)
    
    # 填充2D直方图
    histograms['h2_dy_dphi_jpsi1_jpsi2'].Fill(dy_jpsi1_jpsi2, dphi_jpsi1_jpsi2)
    histograms['h2_dy_dphi_jpsi1_phi'].Fill(dy_jpsi1_phi, dphi_jpsi1_phi)
    histograms['h2_dy_dphi_jpsi2_phi'].Fill(dy_jpsi2_phi, dphi_jpsi2_phi)
    
    # 填充运动学直方图
    histograms['h_jpsi1_pt'].Fill(jpsi1_4vec.Pt())
    histograms['h_jpsi2_pt'].Fill(jpsi2_4vec.Pt())
    histograms['h_phi_pt'].Fill(phi_4vec.Pt())
    
    histograms['h_jpsi1_eta'].Fill(jpsi1_4vec.Eta())
    histograms['h_jpsi2_eta'].Fill(jpsi2_4vec.Eta())
    histograms['h_phi_eta'].Fill(phi_4vec.Eta())
    
    histograms['h_jpsi1_y'].Fill(y_jpsi1)
    histograms['h_jpsi2_y'].Fill(y_jpsi2)
    histograms['h_phi_y'].Fill(y_phi)
    
    histograms['h_jpsi1_phi'].Fill(jpsi1_4vec.Phi())
    histograms['h_jpsi2_phi'].Fill(jpsi2_4vec.Phi())
    histograms['h_phi_phi'].Fill(phi_4vec.Phi())
    
    # 填充不变质量直方图
    histograms['h_mass_jpsi1_jpsi2'].Fill((jpsi1_4vec + jpsi2_4vec).M())
    histograms['h_mass_jpsi1_phi'].Fill((jpsi1_4vec + phi_4vec).M())
    histograms['h_mass_jpsi2_phi'].Fill((jpsi2_4vec + phi_4vec).M())
    histograms['h_mass_all'].Fill((jpsi1_4vec + jpsi2_4vec + phi_4vec).M())


def analyze_jjp_ntuple(max_events=-1, muon_id='soft', output_file=None, input_dir=None, n_workers=1):
    """
    分析JJP Ntuple
    
    Args:
        max_events: 最大处理事件数 (-1表示全部)
        muon_id: muon ID类型 ('loose', 'medium', 'tight', 'soft', None)
        output_file: 输出ROOT文件路径
    """
    global JPSI_MUON_ID
    JPSI_MUON_ID = muon_id
    
    print("\n" + "="*60)
    print("J/psi + J/psi + Phi Ntuple 角度关联分析")
    print("="*60)
    
    start_time = time.time()
    
    # 数据路径选择
    data_path = input_dir if input_dir else JJP_DATA_PATH_DEFAULT
    full_files = discover_jjp_input_files(data_path)
    n_files = len(full_files)
    print(f"[INFO] 数据路径: {data_path}")
    print(f"[INFO] 加载 {n_files} 个文件")

    if n_files == 0:
        print("[ERROR] 未找到输入文件")
        return None

    # 并行/串行处理
    if n_workers <= 1:
        # 单进程复用现有逻辑但通过 worker 函数
        tmp_path, n_proc, n_passed, n_track_misuse = process_file_batch(full_files, max_events, muon_id, TREE_NAME)
        temp_files = [tmp_path]
        total_events = n_proc
        total_selected = n_passed
        total_track_misuse = n_track_misuse
    else:
        batches = [[] for _ in range(n_workers)]
        for idx, f in enumerate(full_files):
            batches[idx % n_workers].append(f)

        # 过滤空批次
        batches = [b for b in batches if b]
        n_workers = len(batches)
        if max_events < 0:
            per_batch_events = -1
        else:
            per_batch_events = math.ceil(max_events / n_workers)

        with multiprocessing.Pool(processes=n_workers) as pool:
            results = pool.starmap(process_file_batch,
                                   [(b, per_batch_events, muon_id, TREE_NAME) for b in batches])
        temp_files = [r[0] for r in results]
        total_events = sum(r[1] for r in results)
        total_selected = sum(r[2] for r in results)
        total_track_misuse = sum(r[3] for r in results)

    # 合并直方图
    histograms = create_histograms()
    for tf in temp_files:
        fin = TFile.Open(tf)
        if fin and not fin.IsZombie():
            merge_histograms(histograms, fin)
        fin.Close()
        os.remove(tf)

    elapsed = time.time() - start_time
    n_to_process = total_events if max_events < 0 else min(max_events, total_events)
    print(f"\n[INFO] 处理完成!")
    print(f"[INFO] 通过选择的事件数: {total_selected}/{n_to_process}")
    print(f"[INFO] 径迹误用(μ↔K)剔除事件数: {total_track_misuse}")
    eff = 0 if n_to_process == 0 else 100 * total_selected / n_to_process
    rate = 0 if elapsed <= 0 else total_events / elapsed
    print(f"[INFO] 选择效率: {eff:.2f}%")
    print(f"[INFO] 耗时: {elapsed:.1f}s ({rate:.0f} evt/s)")

    if output_file is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_file = os.path.join(OUTPUT_DIR, "jjp_ntuple_correlations.root")

    fout = TFile(output_file, "RECREATE")
    for h in histograms.values():
        h.Write()
    fout.Close()

    print(f"[INFO] 输出保存到: {output_file}")

    return histograms


def main():
    parser = argparse.ArgumentParser(description='JJP Ntuple角度关联分析')
    parser.add_argument('-n', '--max-events', type=int, default=-1,
                        help='最大处理事件数 (-1=全部)')
    parser.add_argument('-o', '--output', type=str, default=None,
                        help='输出ROOT文件路径')
    parser.add_argument('--muon-id', type=str, default='soft',
                        choices=['loose', 'medium', 'tight', 'soft', 'none'],
                        help='Muon ID要求 (默认: soft)')
    parser.add_argument('-i', '--input-dir', type=str, default=None,
                        help='输入Ntuple目录 (默认使用内置数据路径)')
    parser.add_argument('-j', '--jobs', type=int, default=1,
                        help='并行进程数 (默认: 1)')
    
    args = parser.parse_args()
    
    setup_root()
    
    muon_id = None if args.muon_id == 'none' else args.muon_id
    
    analyze_jjp_ntuple(
        max_events=args.max_events,
        muon_id=muon_id,
        output_file=args.output,
        input_dir=args.input_dir,
        n_workers=max(1, args.jobs)
    )


if __name__ == '__main__':
    main()

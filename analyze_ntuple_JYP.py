#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
J/psi + Upsilon + Phi (JYP) Ntuple角度关联分析

功能:
1. 从Ntuple加载数据并应用事件选择cuts
2. 计算粒子之间的角度关联 (Δy, Δφ)
3. 填充直方图并保存

使用方法:
    python analyze_ntuple_JYP.py -o output_jyp.root
    python analyze_ntuple_JYP.py -n 10000  # 处理前10000个事件
    python analyze_ntuple_JYP.py --jpsi-muon-id soft --ups-muon-id tight
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
import sys
import subprocess

# =============================================================================
# 配置参数
# =============================================================================

# 数据路径 (默认可被 --input-dir 覆盖)
JYP_DATA_PATH_DEFAULT = "/eos/user/x/xcheng/JpsiUpsPhi/merged_rootNtuple/"
TREE_NAME = "mkcands/X_data"

# 质量窗口
JPSI_MASS_MIN, JPSI_MASS_MAX = 2.9, 3.3
UPS_MASS_MIN, UPS_MASS_MAX = 8.5, 11.4
PHI_MASS_MIN, PHI_MASS_MAX = 0.99, 1.10

# Cuts 参数
JPSI_PT_MIN = 3.0
JPSI_VTXPROB_MIN = 0.05
UPS_PT_MIN = 4.0
UPS_VTXPROB_MIN = 0.10
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
UPS_MUON_ID = 'tight'
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
    histograms['h_dy_jpsi_ups'] = TH1F("h_dy_jpsi_ups",
        "#Delta y (J/#psi - #Upsilon);|#Delta y|;Events", 50, 0, 5)
    histograms['h_dy_jpsi_phi'] = TH1F("h_dy_jpsi_phi",
        "#Delta y (J/#psi - #phi);|#Delta y|;Events", 50, 0, 5)
    histograms['h_dy_ups_phi'] = TH1F("h_dy_ups_phi",
        "#Delta y (#Upsilon - #phi);|#Delta y|;Events", 50, 0, 5)
    
    # 1D: Δφ (方位角差)
    histograms['h_dphi_jpsi_ups'] = TH1F("h_dphi_jpsi_ups",
        "#Delta#phi (J/#psi - #Upsilon);|#Delta#phi|;Events", 50, 0, math.pi)
    histograms['h_dphi_jpsi_phi'] = TH1F("h_dphi_jpsi_phi",
        "#Delta#phi (J/#psi - #phi);|#Delta#phi|;Events", 50, 0, math.pi)
    histograms['h_dphi_ups_phi'] = TH1F("h_dphi_ups_phi",
        "#Delta#phi (#Upsilon - #phi);|#Delta#phi|;Events", 50, 0, math.pi)
    
    # 2D: Δy vs Δφ
    histograms['h2_dy_dphi_jpsi_ups'] = TH2F("h2_dy_dphi_jpsi_ups",
        "J/#psi - #Upsilon;|#Delta y|;|#Delta#phi|", 50, 0, 5, 50, 0, math.pi)
    histograms['h2_dy_dphi_jpsi_phi'] = TH2F("h2_dy_dphi_jpsi_phi",
        "J/#psi - #phi;|#Delta y|;|#Delta#phi|", 50, 0, 5, 50, 0, math.pi)
    histograms['h2_dy_dphi_ups_phi'] = TH2F("h2_dy_dphi_ups_phi",
        "#Upsilon - #phi;|#Delta y|;|#Delta#phi|", 50, 0, 5, 50, 0, math.pi)
    
    # 运动学分布: pT
    histograms['h_jpsi_pt'] = TH1F("h_jpsi_pt",
        "J/#psi p_{T};p_{T} [GeV];Events", 100, 0, 50)
    histograms['h_ups_pt'] = TH1F("h_ups_pt",
        "#Upsilon p_{T};p_{T} [GeV];Events", 100, 0, 50)
    histograms['h_phi_pt'] = TH1F("h_phi_pt",
        "#phi p_{T};p_{T} [GeV];Events", 100, 0, 50)
    
    # 运动学分布: η
    histograms['h_jpsi_eta'] = TH1F("h_jpsi_eta",
        "J/#psi #eta;#eta;Events", 60, -3, 3)
    histograms['h_ups_eta'] = TH1F("h_ups_eta",
        "#Upsilon #eta;#eta;Events", 60, -3, 3)
    histograms['h_phi_eta'] = TH1F("h_phi_eta",
        "#phi #eta;#eta;Events", 60, -3, 3)
    
    # 运动学分布: y (快度)
    histograms['h_jpsi_y'] = TH1F("h_jpsi_y",
        "J/#psi y;y;Events", 60, -3, 3)
    histograms['h_ups_y'] = TH1F("h_ups_y",
        "#Upsilon y;y;Events", 60, -3, 3)
    histograms['h_phi_y'] = TH1F("h_phi_y",
        "#phi y;y;Events", 60, -3, 3)
    
    # 运动学分布: φ (方位角)
    histograms['h_jpsi_phi'] = TH1F("h_jpsi_phi",
        "J/#psi #phi;#phi;Events", 60, -math.pi, math.pi)
    histograms['h_ups_phi'] = TH1F("h_ups_phi",
        "#Upsilon #phi;#phi;Events", 60, -math.pi, math.pi)
    histograms['h_phi_phi'] = TH1F("h_phi_phi",
        "#phi #phi;#phi;Events", 60, -math.pi, math.pi)
    
    # 不变质量分布
    histograms['h_mass_jpsi_ups'] = TH1F("h_mass_jpsi_ups",
        "M(J/#psi + #Upsilon);M [GeV];Events", 100, 10, 30)
    histograms['h_mass_jpsi_phi'] = TH1F("h_mass_jpsi_phi",
        "M(J/#psi + #phi);M [GeV];Events", 100, 3, 20)
    histograms['h_mass_ups_phi'] = TH1F("h_mass_ups_phi",
        "M(#Upsilon + #phi);M [GeV];Events", 100, 9, 25)
    histograms['h_mass_all'] = TH1F("h_mass_all",
        "M(J/#psi + #Upsilon + #phi);M [GeV];Events", 100, 12, 40)
    
    return histograms


def merge_histograms(dest, src):
    """Add contents of src histograms into dest histograms in-place."""
    for name, hdest in dest.items():
        hsrc = src.Get(name)
        if hsrc:
            hdest.Add(hsrc)


def process_file_batch(file_list, max_events, jpsi_muon_id, ups_muon_id, tree_name):
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
            n_cand = chain.Jpsi_mass.size()
        except:
            continue
        if n_cand == 0:
            continue

        best_cand = None
        best_score = -1

        for i_cand in range(n_cand):
            try:
                jpsi_mass = chain.Jpsi_mass.at(i_cand)
                ups_mass = chain.Ups_mass.at(i_cand)
                phi_mass = chain.Phi_mass.at(i_cand)

                if not (JPSI_MASS_MIN < jpsi_mass < JPSI_MASS_MAX):
                    continue
                if not (UPS_MASS_MIN < ups_mass < UPS_MASS_MAX):
                    continue
                if not (PHI_MASS_MIN < phi_mass < PHI_MASS_MAX):
                    continue

                jpsi_pt = chain.Jpsi_pt.at(i_cand)
                ups_pt = chain.Ups_pt.at(i_cand)
                phi_pt = chain.Phi_pt.at(i_cand)
                if jpsi_pt < JPSI_PT_MIN or ups_pt < UPS_PT_MIN or phi_pt < PHI_PT_MIN:
                    continue

                jpsi_vtxprob = chain.Jpsi_VtxProb.at(i_cand)
                ups_vtxprob = chain.Ups_VtxProb.at(i_cand)
                phi_vtxprob = chain.Phi_VtxProb.at(i_cand)
                if jpsi_vtxprob < JPSI_VTXPROB_MIN or ups_vtxprob < UPS_VTXPROB_MIN or phi_vtxprob < PHI_VTXPROB_MIN:
                    continue

                phi_k1_pt = chain.Phi_K_1_pt.at(i_cand)
                phi_k2_pt = chain.Phi_K_2_pt.at(i_cand)
                if phi_k1_pt < PHI_K_PT_MIN or phi_k2_pt < PHI_K_PT_MIN:
                    continue

                jpsi_mu1_idx = chain.Jpsi_mu_1_Idx.at(i_cand)
                jpsi_mu2_idx = chain.Jpsi_mu_2_Idx.at(i_cand)
                ups_mu1_idx = chain.Ups_mu_1_Idx.at(i_cand)
                ups_mu2_idx = chain.Ups_mu_2_Idx.at(i_cand)

                if jpsi_muon_id:
                    if not (check_muon_id(chain, jpsi_mu1_idx, jpsi_muon_id) and
                            check_muon_id(chain, jpsi_mu2_idx, jpsi_muon_id)):
                        continue

                if ups_muon_id:
                    if not (check_muon_id(chain, ups_mu1_idx, ups_muon_id) and
                            check_muon_id(chain, ups_mu2_idx, ups_muon_id)):
                        continue

                jpsi_eta = chain.Jpsi_eta.at(i_cand)
                jpsi_phi = chain.Jpsi_phi.at(i_cand)
                ups_eta = chain.Ups_eta.at(i_cand)
                ups_phi = chain.Ups_phi.at(i_cand)
                phi_eta = chain.Phi_eta.at(i_cand)
                phi_phi = chain.Phi_phi.at(i_cand)

                score = math.sqrt(jpsi_pt**2 + ups_pt**2 + phi_pt**2)
                if score > best_score:
                    best_score = score
                    best_cand = {
                        'jpsi_pt': jpsi_pt, 'jpsi_eta': jpsi_eta, 'jpsi_phi': jpsi_phi, 'jpsi_mass': jpsi_mass,
                        'ups_pt': ups_pt, 'ups_eta': ups_eta, 'ups_phi': ups_phi, 'ups_mass': ups_mass,
                        'phi_pt': phi_pt, 'phi_eta': phi_eta, 'phi_phi': phi_phi, 'phi_mass': phi_mass,
                        'jpsi_mu1_idx': int(jpsi_mu1_idx), 'jpsi_mu2_idx': int(jpsi_mu2_idx),
                        'ups_mu1_idx': int(ups_mu1_idx), 'ups_mu2_idx': int(ups_mu2_idx),
                        'phi_k1_px': chain.Phi_K_1_px.at(i_cand), 'phi_k1_py': chain.Phi_K_1_py.at(i_cand), 'phi_k1_pz': chain.Phi_K_1_pz.at(i_cand),
                        'phi_k2_px': chain.Phi_K_2_px.at(i_cand), 'phi_k2_py': chain.Phi_K_2_py.at(i_cand), 'phi_k2_pz': chain.Phi_K_2_pz.at(i_cand),
                        'phi_k1_pt': phi_k1_pt, 'phi_k2_pt': phi_k2_pt,
                        'phi_k1_eta': chain.Phi_K_1_eta.at(i_cand), 'phi_k1_phi': chain.Phi_K_1_phi.at(i_cand),
                        'phi_k2_eta': chain.Phi_K_2_eta.at(i_cand), 'phi_k2_phi': chain.Phi_K_2_phi.at(i_cand),
                    }
            except Exception:
                continue

        if best_cand is not None:
            # Validate muon indices
            try:
                mu_size = chain.muPx.size()
                muon_indices = [best_cand['jpsi_mu1_idx'], best_cand['jpsi_mu2_idx'],
                        best_cand['ups_mu1_idx'], best_cand['ups_mu2_idx']]
                if any(idx < 0 for idx in muon_indices) or any(idx >= mu_size for idx in muon_indices):
                    continue
                muon_jpsi1_vec = build_vec_from_pxpypz(chain.muPx.at(best_cand['jpsi_mu1_idx']),
                                                 chain.muPy.at(best_cand['jpsi_mu1_idx']),
                                                 chain.muPz.at(best_cand['jpsi_mu1_idx']), MUON_MASS)
                muon_jpsi2_vec = build_vec_from_pxpypz(chain.muPx.at(best_cand['jpsi_mu2_idx']),
                                                 chain.muPy.at(best_cand['jpsi_mu2_idx']),
                                                 chain.muPz.at(best_cand['jpsi_mu2_idx']), MUON_MASS)
                muon_ups1_vec = build_vec_from_pxpypz(chain.muPx.at(best_cand['ups_mu1_idx']),
                                                chain.muPy.at(best_cand['ups_mu1_idx']),
                                                chain.muPz.at(best_cand['ups_mu1_idx']), MUON_MASS)
                muon_ups2_vec = build_vec_from_pxpypz(chain.muPx.at(best_cand['ups_mu2_idx']),
                                                chain.muPy.at(best_cand['ups_mu2_idx']),
                                                chain.muPz.at(best_cand['ups_mu2_idx']), MUON_MASS)
            except Exception:
                continue

            k1_vec = build_vec_from_pxpypz(best_cand['phi_k1_px'], best_cand['phi_k1_py'], best_cand['phi_k1_pz'], KAON_MASS)
            k2_vec = build_vec_from_pxpypz(best_cand['phi_k2_px'], best_cand['phi_k2_py'], best_cand['phi_k2_pz'], KAON_MASS)

            # Track-misuse veto: any muon (Jpsi or Upsilon) vs Phi kaons
            track_misuse = False
            for mu_vec in (muon_jpsi1_vec, muon_jpsi2_vec, muon_ups1_vec, muon_ups2_vec):
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

            jpsi_4vec = TLorentzVector()
            ups_4vec = TLorentzVector()
            phi_4vec = TLorentzVector()
            jpsi_4vec.SetPtEtaPhiM(best_cand['jpsi_pt'], best_cand['jpsi_eta'], best_cand['jpsi_phi'], best_cand['jpsi_mass'])
            ups_4vec.SetPtEtaPhiM(best_cand['ups_pt'], best_cand['ups_eta'], best_cand['ups_phi'], best_cand['ups_mass'])
            phi_4vec.SetPtEtaPhiM(best_cand['phi_pt'], best_cand['phi_eta'], best_cand['phi_phi'], best_cand['phi_mass'])
            fill_histograms(histos, jpsi_4vec, ups_4vec, phi_4vec)
            n_passed += 1

    fd, tmp_path = tempfile.mkstemp(suffix=".root", prefix="jyp_ntuple_tmp_")
    os.close(fd)
    fout = TFile(tmp_path, "RECREATE")
    for h in histos.values():
        h.Write()
    fout.Close()

    return tmp_path, n_to_process, n_passed, n_track_misuse


def fill_histograms(histograms, jpsi_4vec, ups_4vec, phi_4vec):
    """填充所有直方图"""
    # 计算快度
    y_jpsi = jpsi_4vec.Rapidity()
    y_ups = ups_4vec.Rapidity()
    y_phi = phi_4vec.Rapidity()
    
    # 计算Δy
    dy_jpsi_ups = abs(y_jpsi - y_ups)
    dy_jpsi_phi = abs(y_jpsi - y_phi)
    dy_ups_phi = abs(y_ups - y_phi)
    
    # 计算Δφ
    dphi_jpsi_ups = abs(delta_phi(jpsi_4vec.Phi(), ups_4vec.Phi()))
    dphi_jpsi_phi = abs(delta_phi(jpsi_4vec.Phi(), phi_4vec.Phi()))
    dphi_ups_phi = abs(delta_phi(ups_4vec.Phi(), phi_4vec.Phi()))
    
    # 填充1D直方图
    histograms['h_dy_jpsi_ups'].Fill(dy_jpsi_ups)
    histograms['h_dy_jpsi_phi'].Fill(dy_jpsi_phi)
    histograms['h_dy_ups_phi'].Fill(dy_ups_phi)
    
    histograms['h_dphi_jpsi_ups'].Fill(dphi_jpsi_ups)
    histograms['h_dphi_jpsi_phi'].Fill(dphi_jpsi_phi)
    histograms['h_dphi_ups_phi'].Fill(dphi_ups_phi)
    
    # 填充2D直方图
    histograms['h2_dy_dphi_jpsi_ups'].Fill(dy_jpsi_ups, dphi_jpsi_ups)
    histograms['h2_dy_dphi_jpsi_phi'].Fill(dy_jpsi_phi, dphi_jpsi_phi)
    histograms['h2_dy_dphi_ups_phi'].Fill(dy_ups_phi, dphi_ups_phi)
    
    # 填充运动学直方图
    histograms['h_jpsi_pt'].Fill(jpsi_4vec.Pt())
    histograms['h_ups_pt'].Fill(ups_4vec.Pt())
    histograms['h_phi_pt'].Fill(phi_4vec.Pt())
    
    histograms['h_jpsi_eta'].Fill(jpsi_4vec.Eta())
    histograms['h_ups_eta'].Fill(ups_4vec.Eta())
    histograms['h_phi_eta'].Fill(phi_4vec.Eta())
    
    histograms['h_jpsi_y'].Fill(y_jpsi)
    histograms['h_ups_y'].Fill(y_ups)
    histograms['h_phi_y'].Fill(y_phi)
    
    histograms['h_jpsi_phi'].Fill(jpsi_4vec.Phi())
    histograms['h_ups_phi'].Fill(ups_4vec.Phi())
    histograms['h_phi_phi'].Fill(phi_4vec.Phi())
    
    # 填充不变质量直方图
    histograms['h_mass_jpsi_ups'].Fill((jpsi_4vec + ups_4vec).M())
    histograms['h_mass_jpsi_phi'].Fill((jpsi_4vec + phi_4vec).M())
    histograms['h_mass_ups_phi'].Fill((ups_4vec + phi_4vec).M())
    histograms['h_mass_all'].Fill((jpsi_4vec + ups_4vec + phi_4vec).M())


def analyze_jyp_ntuple(max_events=-1, jpsi_muon_id='soft', ups_muon_id='tight', output_file=None, input_dir=None, n_workers=1):
    """
    分析JYP Ntuple
    
    Args:
        max_events: 最大处理事件数 (-1表示全部)
        jpsi_muon_id: J/psi muon ID类型
        ups_muon_id: Upsilon muon ID类型
        output_file: 输出ROOT文件路径
    """
    print("\n" + "="*60)
    print("J/psi + Upsilon + Phi Ntuple 角度关联分析")
    print("="*60)
    
    start_time = time.time()
    
    # 数据路径选择
    data_path = input_dir if input_dir else JYP_DATA_PATH_DEFAULT

    if data_path.startswith("root://"):
        # Enumerate files via xrdfs to avoid wildcard-on-directory issues
        try:
            # Split host and path
            stripped = data_path[len("root://"):]
            host, remote_path = stripped.split("/", 1)
            remote_path = "/" + remote_path  # ensure leading slash

            # Recursive listing
            cmd = ["xrdfs", host, "ls", "-R", remote_path]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            all_paths = res.stdout.strip().splitlines()

            # Filter candidates
            ntuple_files = [p for p in all_paths if p.lower().endswith("output_ntuple.root")]
            ntuple_files += [p for p in all_paths if "ntuple" in os.path.basename(p).lower() and p.lower().endswith(".root")]
            ntuple_files = list(dict.fromkeys(ntuple_files))

            if len(ntuple_files) == 0:
                other_root = [p for p in all_paths if p.lower().endswith(".root") and "miniaod" not in p.lower()]
                ntuple_files = other_root

            n_files = len(ntuple_files)
            if n_files == 0:
                print(f"[INFO] 数据路径: {data_path}")
                print("[ERROR] 未找到输入文件 (XRootD)")
                return None

            data_files = [f"root://{host}{p}" for p in ntuple_files]
            print(f"[INFO] 数据路径: {data_path}")
            print(f"[INFO] 加载 {n_files} 个文件 (xrdfs 枚举)")
        except Exception as e:
            print(f"[ERROR] XRootD 枚举失败: {e}")
            return None

    else:
        files_raw = glob.glob(os.path.join(data_path, "*.root"))
        files_raw += glob.glob(os.path.join(data_path, "*", "*.root"))
        files_raw = list(set(files_raw))

        data_files_clean = [f for f in files_raw if "miniaod" not in os.path.basename(f).lower()]
        data_files = [f for f in data_files_clean if "ntuple" in os.path.basename(f).lower()]

        if len(data_files) == 0 and len(data_files_clean) > 0:
            print("[WARN] 未找到包含 'ntuple' 的ROOT文件，退回到全部非MINIAOD文件")
            data_files = data_files_clean

        n_files = len(data_files)
        print(f"[INFO] 数据路径: {data_path}")
        print(f"[INFO] 加载 {n_files} 个文件")

        if n_files == 0:
            print("[ERROR] 未找到输入文件")
            return None

    if n_workers <= 1:
        tmp_path, n_proc, n_passed, n_track_misuse = process_file_batch(data_files, max_events, jpsi_muon_id, ups_muon_id, TREE_NAME)
        temp_files = [tmp_path]
        total_events = n_proc
        total_selected = n_passed
        total_track_misuse = n_track_misuse
    else:
        batches = [[] for _ in range(n_workers)]
        for idx, f in enumerate(data_files):
            batches[idx % n_workers].append(f)
        batches = [b for b in batches if b]
        n_batches = len(batches)
        per_batch_events = -1 if max_events < 0 else math.ceil(max_events / n_batches)

        with multiprocessing.Pool(processes=n_batches) as pool:
            results = pool.starmap(process_file_batch,
                                   [(b, per_batch_events, jpsi_muon_id, ups_muon_id, TREE_NAME) for b in batches])
        temp_files = [r[0] for r in results]
        total_events = sum(r[1] for r in results)
        total_selected = sum(r[2] for r in results)
        total_track_misuse = sum(r[3] for r in results)

    histograms = create_histograms()
    for tmp_path in temp_files:
        input_file = TFile.Open(tmp_path)
        if input_file and not input_file.IsZombie():
            merge_histograms(histograms, input_file)
        input_file.Close()
        os.remove(tmp_path)

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
        output_file = os.path.join(OUTPUT_DIR, "jyp_ntuple_correlations.root")

    fout = TFile(output_file, "RECREATE")
    for h in histograms.values():
        h.Write()
    fout.Close()

    print(f"[INFO] 输出保存到: {output_file}")

    return histograms


def main():
    parser = argparse.ArgumentParser(description='JYP Ntuple角度关联分析')
    parser.add_argument('-n', '--max-events', type=int, default=-1,
                        help='最大处理事件数 (-1=全部)')
    parser.add_argument('-o', '--output', type=str, default=None,
                        help='输出ROOT文件路径')
    parser.add_argument('--jpsi-muon-id', type=str, default='soft',
                        choices=['loose', 'medium', 'tight', 'soft', 'none'],
                        help='J/psi Muon ID要求 (默认: soft)')
    parser.add_argument('--ups-muon-id', type=str, default='tight',
                        choices=['loose', 'medium', 'tight', 'soft', 'none'],
                        help='Upsilon Muon ID要求 (默认: tight)')
    parser.add_argument('-i', '--input-dir', type=str, default=None,
                        help='输入Ntuple目录 (默认使用内置数据路径)')
    parser.add_argument('-j', '--jobs', type=int, default=1,
                        help='并行进程数 (默认: 1)')
    
    args = parser.parse_args()
    
    setup_root()
    
    jpsi_muon_id = None if args.jpsi_muon_id == 'none' else args.jpsi_muon_id
    ups_muon_id = None if args.ups_muon_id == 'none' else args.ups_muon_id
    
    result = analyze_jyp_ntuple(
        max_events=args.max_events,
        jpsi_muon_id=jpsi_muon_id,
        ups_muon_id=ups_muon_id,
        output_file=args.output,
        input_dir=args.input_dir,
        n_workers=max(1, args.jobs)
    )

    if result is None:
        sys.exit(1)


if __name__ == '__main__':
    main()

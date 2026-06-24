#!/usr/bin/env python3
"""Inspect events where gen φ pT ∈ [6,10) but reco best φ pT ∈ [4,6).

Shows all reco candidates in those events with their kinematics.
"""
from __future__ import annotations

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


import awkward as ak
import numpy as np
import uproot

NTUPLE = (
    "root://cceos.ihep.ac.cn/"
    "///eos/ihep/cms/store/user/xcheng/MC_Production_v3/output/"
    "JJP_DPS2_CS/0/output_ntuple.root:mkcands/X_data"
)

print("Loading ...", flush=True)
f = uproot.open(NTUPLE)

# GEN
g_pt  = f["MC_GenPart_pt"].array()
g_pdg = f["MC_GenPart_pdgId"].array()
g_mom = f["MC_GenPart_motherGenIdx"].array()
g_eta = f["MC_GenPart_eta"].array()
g_idx = ak.local_index(g_pt)

# RECO candidate-level
j1_pt  = f["Jpsi_1_pt"].array()
j2_pt  = f["Jpsi_2_pt"].array()
p_pt   = f["Phi_pt"].array()
j1_m   = f["Jpsi_1_mass"].array()
j2_m   = f["Jpsi_2_mass"].array()
p_m    = f["Phi_mass"].array()
j1_px  = f["Jpsi_1_px"].array(); j1_py = f["Jpsi_1_py"].array(); j1_pz = f["Jpsi_1_pz"].array()
j2_px  = f["Jpsi_2_px"].array(); j2_py = f["Jpsi_2_py"].array(); j2_pz = f["Jpsi_2_pz"].array()
j1_vp  = f["Jpsi_1_VtxProb"].array()
j2_vp  = f["Jpsi_2_VtxProb"].array()

# Matching
pk1_gmidx = f["Phi_K_1_genMatchIdx"].array()
pk1_gmsrc = f["Phi_K_1_genMatchSource"].array()
pk2_gmidx = f["Phi_K_2_genMatchIdx"].array()
pk2_gmsrc = f["Phi_K_2_genMatchSource"].array()
mu_gmidx  = f["muGenMatchIdx"].array()
mu_gmsrc  = f["muGenMatchSource"].array()
j1_mu1 = f["Jpsi_1_mu_1_Idx"].array(); j1_mu2 = f["Jpsi_1_mu_2_Idx"].array()
j2_mu1 = f["Jpsi_2_mu_1_Idx"].array(); j2_mu2 = f["Jpsi_2_mu_2_Idx"].array()

# ── GEN best system ──
is_mu = abs(g_pdg) == 13; is_ka = abs(g_pdg) == 321
n_mu_d   = ak.sum(g_mom[is_mu][:, :, None]  == g_idx[:, None, :], axis=1)
n_kaon_d = ak.sum(g_mom[is_ka][:, :, None]  == g_idx[:, None, :], axis=1)
vj = (abs(g_pdg) == 443) & (n_mu_d >= 2) & (g_pt > 6.0)
vp = (abs(g_pdg) == 333) & (n_kaon_d >= 2) & (g_pt > 4.0)

jo = ak.argsort(g_pt[vj], ascending=False)
po = ak.argsort(g_pt[vp], ascending=False)
p_idx_s = g_idx[vp][po]; p_pt_s = g_pt[vp][po]
gen_p_idx = ak.fill_none(ak.pad_none(p_idx_s, 1, axis=1)[:, 0], -1)
gen_p_pt  = ak.fill_none(ak.pad_none(p_pt_s, 1, axis=1)[:, 0], np.nan)

has_full_gen = (ak.num(g_idx[vj][jo], axis=1) >= 2) & (ak.num(g_idx[vp][po], axis=1) >= 1)

# ── RECO best candidate ──
j1_e = np.sqrt(j1_px**2 + j1_py**2 + j1_pz**2 + j1_m**2)
j2_e = np.sqrt(j2_px**2 + j2_py**2 + j2_pz**2 + j2_m**2)
j1_abs_y = abs(0.5 * np.log((j1_e + j1_pz) / (j1_e - j1_pz + 1e-30)))
j2_abs_y = abs(0.5 * np.log((j2_e + j2_pz) / (j2_e - j2_pz + 1e-30)))

quality = (
    (j1_m >= 2.9) & (j1_m <= 3.3) & (j1_pt > 6.0) & (j1_abs_y < 2.5) & (j1_vp > 0.01)
    & (j2_m >= 2.9) & (j2_m <= 3.3) & (j2_pt > 6.0) & (j2_abs_y < 2.5) & (j2_vp > 0.01)
    & (p_m >= 0.99) & (p_m <= 1.07) & (p_pt > 4.0)
)
score = j1_pt**2 + j2_pt**2 + p_pt**2
best_idx = ak.argmax(ak.where(quality, score, -1.0), axis=1, keepdims=False)
has_reco = ak.any(quality, axis=1)

# ── Find migration events ──
mask = has_full_gen & has_reco
evt_idx = ak.to_numpy(ak.where(mask)[0])

gen_p_pt_m = ak.to_numpy(gen_p_pt[mask])
gen_p_idx_m = ak.to_numpy(gen_p_idx[mask])
best_idx_m = ak.to_numpy(best_idx[mask])

migration_events = []
for k in range(len(evt_idx)):
    g_pt_val = gen_p_pt_m[k]
    orig_evt = evt_idx[k]
    bi = int(best_idx_m[k])
    r_pt_val = float(p_pt[orig_evt][bi])
    if 6.0 <= g_pt_val < 10.0 and 4.0 <= r_pt_val < 6.0:
        migration_events.append((orig_evt, k, bi, g_pt_val, r_pt_val))

if not migration_events:
    print("No migration events found.")
    import sys; sys.exit(0)

print(f"Found {len(migration_events)} migration event(s): gen φ pT∈[6,10) → reco φ pT∈[4,6)\n")

for orig_evt, k, bi, g_pt_val, r_pt_val in migration_events:
    print("=" * 80)
    print(f"Event {orig_evt}:  GEN best φ pT = {g_pt_val:.1f} GeV  →  RECO best φ pT = {r_pt_val:.1f} GeV")
    print(f"  GEN best φ idx = {gen_p_idx_m[k]}")
    print()

    # All GEN φ candidates
    n_p = int(ak.num(g_pt[vp][po][orig_evt], axis=0))
    print(f"  ── All GEN φ (pT>4, ≥2 kaon daus): {n_p} total ──")
    p_pt_all = ak.to_numpy(g_pt[vp][po][orig_evt])
    p_idx_all = ak.to_numpy(g_idx[vp][po][orig_evt])
    for ip in range(n_p):
        star = " ← GEN BEST" if p_idx_all[ip] == gen_p_idx_m[k] else ""
        print(f"    φ[{ip}]: idx={p_idx_all[ip]}  pT={p_pt_all[ip]:.1f}{star}")

    # All GEN J/ψ candidates
    n_j = int(ak.num(g_pt[vj][jo][orig_evt], axis=0))
    print(f"  ── All GEN J/ψ (pT>6, ≥2 muon daus): {n_j} total ──")
    j_pt_all = ak.to_numpy(g_pt[vj][jo][orig_evt])
    j_idx_all = ak.to_numpy(g_idx[vj][jo][orig_evt])
    for ij in range(n_j):
        star = " ← J/ψ1" if ij == 0 else (" ← J/ψ2" if ij == 1 else "")
        print(f"    J/ψ[{ij}]: idx={j_idx_all[ij]}  pT={j_pt_all[ij]:.1f}{star}")

    print()

    # All RECO candidates (all, not just quality-passing)
    n_cand_all = len(j1_pt[orig_evt])
    n_cand_q = int(np.sum(ak.to_numpy(quality[orig_evt])))
    print(f"  ── RECO candidates: {n_cand_all} total, {n_cand_q} pass quality cuts ──")

    # Show ALL candidates
    for ic in range(n_cand_all):
        q = "✓" if bool(quality[orig_evt][ic]) else "✗"
        s = float(score[orig_evt][ic])
        star = " ← BEST" if ic == bi else ""
        j1p = float(j1_pt[orig_evt][ic]); j2p = float(j2_pt[orig_evt][ic]); pp = float(p_pt[orig_evt][ic])
        j1m = float(j1_m[orig_evt][ic]); j2m = float(j2_m[orig_evt][ic]); pm = float(p_m[orig_evt][ic])

        # Rapidity
        j1px = float(j1_px[orig_evt][ic]); j1py = float(j1_py[orig_evt][ic]); j1pz = float(j1_pz[orig_evt][ic])
        j2px = float(j2_px[orig_evt][ic]); j2py = float(j2_py[orig_evt][ic]); j2pz = float(j2_pz[orig_evt][ic])
        j1e = np.sqrt(j1px**2 + j1py**2 + j1pz**2 + j1m**2)
        j2e = np.sqrt(j2px**2 + j2py**2 + j2pz**2 + j2m**2)
        j1y = 0.5 * np.log((j1e + j1pz) / (j1e - j1pz + 1e-30))
        j2y = 0.5 * np.log((j2e + j2pz) / (j2e - j2pz + 1e-30))

        # φ gen-matching
        pk1_gm = int(pk1_gmidx[orig_evt][ic]); pk2_gm = int(pk2_gmidx[orig_evt][ic])
        pk1_src = int(pk1_gmsrc[orig_evt][ic]); pk2_src = int(pk2_gmsrc[orig_evt][ic])

        print(f"    cand[{ic}] {q} S={s:.0f}{star}")
        print(f"      J/ψ1: pT={j1p:.1f}  y={j1y:+.2f}  m={j1m:.3f}  VtxProb={float(j1_vp[orig_evt][ic]):.3f}")
        print(f"      J/ψ2: pT={j2p:.1f}  y={j2y:+.2f}  m={j2m:.3f}  VtxProb={float(j2_vp[orig_evt][ic]):.3f}")
        print(f"      φ:    pT={pp:.1f}  m={pm:.3f}  K1_gmIdx={pk1_gm}(src={pk1_src})  K2_gmIdx={pk2_gm}(src={pk2_src})")

        # Show muon gen-match ancestors for this candidate
        j1m1 = int(j1_mu1[orig_evt][ic]); j1m2 = int(j1_mu2[orig_evt][ic])
        j2m1 = int(j2_mu1[orig_evt][ic]); j2m2 = int(j2_mu2[orig_evt][ic])
        if j1m1 >= 0 and j1m1 < len(mu_gmidx[orig_evt]):
            gm1 = int(mu_gmidx[orig_evt][j1m1]); gs1 = int(mu_gmsrc[orig_evt][j1m1])
            gm2 = int(mu_gmidx[orig_evt][j1m2]); gs2 = int(mu_gmsrc[orig_evt][j1m2])
            gm3 = int(mu_gmidx[orig_evt][j2m1]); gs3 = int(mu_gmsrc[orig_evt][j2m1])
            gm4 = int(mu_gmidx[orig_evt][j2m2]); gs4 = int(mu_gmsrc[orig_evt][j2m2])
            print(f"      μ gen-match: J1μ1=gm{int(gm1)}(s{int(gs1)}) J1μ2=gm{int(gm2)}(s{int(gs2)}) "
                  f"J2μ1=gm{int(gm3)}(s{int(gs3)}) J2μ2=gm{int(gm4)}(s{int(gs4)})")
        print()

print("Done.")

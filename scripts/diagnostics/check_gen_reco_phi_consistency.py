#!/usr/bin/env python3
"""Quantify GEN-RECO φ matching consistency.

Both GEN and RECO use max(J1_pt² + J2_pt² + φ_pt²) to select the best system.
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

gen_pt  = f["MC_GenPart_pt"].array()
gen_pdg = f["MC_GenPart_pdgId"].array()
gen_mom = f["MC_GenPart_motherGenIdx"].array()
gen_idx = ak.local_index(gen_pdg)

j1_pt = f["Jpsi_1_pt"].array()
j2_pt = f["Jpsi_2_pt"].array()
p_pt  = f["Phi_pt"].array()
j1_m  = f["Jpsi_1_mass"].array()
j2_m  = f["Jpsi_2_mass"].array()
p_m   = f["Phi_mass"].array()
j1_px = f["Jpsi_1_px"].array(); j1_py = f["Jpsi_1_py"].array(); j1_pz = f["Jpsi_1_pz"].array()
j2_px = f["Jpsi_2_px"].array(); j2_py = f["Jpsi_2_py"].array(); j2_pz = f["Jpsi_2_pz"].array()
j1_vp = f["Jpsi_1_VtxProb"].array()
j2_vp = f["Jpsi_2_VtxProb"].array()

j1_mu1 = f["Jpsi_1_mu_1_Idx"].array(); j1_mu2 = f["Jpsi_1_mu_2_Idx"].array()
j2_mu1 = f["Jpsi_2_mu_1_Idx"].array(); j2_mu2 = f["Jpsi_2_mu_2_Idx"].array()

mu_gmidx  = f["muGenMatchIdx"].array()
mu_gmsrc  = f["muGenMatchSource"].array()
pk1_gmidx = f["Phi_K_1_genMatchIdx"].array()
pk1_gmsrc = f["Phi_K_1_genMatchSource"].array()
pk2_gmidx = f["Phi_K_2_genMatchIdx"].array()
pk2_gmsrc = f["Phi_K_2_genMatchSource"].array()

n_total = len(gen_pt)
print(f"  {n_total} events", flush=True)


# ── Step 1: GEN-level best system (vectorized) ──

print("Step 1: GEN-level ...", flush=True)
is_mu = abs(gen_pdg) == 13
is_ka = abs(gen_pdg) == 321
n_mu_d   = ak.sum(gen_mom[is_mu][:, :, None]  == gen_idx[:, None, :], axis=1)
n_kaon_d = ak.sum(gen_mom[is_ka][:, :, None]  == gen_idx[:, None, :], axis=1)

vj = (abs(gen_pdg) == 443) & (n_mu_d >= 2) & (gen_pt > 6.0)
vp = (abs(gen_pdg) == 333) & (n_kaon_d >= 2) & (gen_pt > 4.0)

jo = ak.argsort(gen_pt[vj], ascending=False)
po = ak.argsort(gen_pt[vp], ascending=False)

j_idx_s = gen_idx[vj][jo]; j_pt_s = gen_pt[vj][jo]
p_idx_s = gen_idx[vp][po]; p_pt_s = gen_pt[vp][po]

def _nth(arr, n, default):
    return ak.fill_none(ak.pad_none(arr, n + 1, axis=1)[:, n], default)

gen_j1_idx = _nth(j_idx_s, 0, -1); gen_j2_idx = _nth(j_idx_s, 1, -1)
gen_j1_pt  = _nth(j_pt_s,  0, np.nan); gen_j2_pt  = _nth(j_pt_s,  1, np.nan)
gen_p_idx  = _nth(p_idx_s, 0, -1);     gen_p_pt   = _nth(p_pt_s,  0, np.nan)

n_j = ak.num(j_idx_s, axis=1)
n_p = ak.num(p_idx_s, axis=1)
has_full_gen = (n_j >= 2) & (n_p >= 1)
has_multi_phi = has_full_gen & (n_p >= 2)

n_full = int(ak.sum(has_full_gen))
n_mp = int(ak.sum(has_multi_phi))
print(f"  Full GEN: {n_full}  (multi-φ: {n_mp} = {100*n_mp/n_full:.2f}%)", flush=True)


# ── Step 2: RECO-level best candidate (vectorized) ──

print("Step 2: RECO-level ...", flush=True)

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

# Convert to numpy for the 115 events with both
mask_both = has_full_gen & has_reco
both_indices = np.where(ak.to_numpy(mask_both))[0]
n_both = len(both_indices)
print(f"  Both GEN + RECO: {n_both}", flush=True)


# ── Step 3: Per-event gen-matching (Python loop, only 115 events) ──

print("Step 3: Per-event tracing ...", flush=True)

def first_ancestor(pdg_list, mother_list, start_idx, target_abs_pdg, max_depth=16):
    """Walk up mother chain from start_idx to find target PDG ancestor."""
    idx = int(start_idx)
    for _ in range(max_depth):
        if idx < 0 or idx >= len(pdg_list):
            return -1
        if abs(int(pdg_list[idx])) == target_abs_pdg:
            return idx
        idx = int(mother_list[idx])
    return -1

n_phi_match = 0
n_phi_mismatch = 0
n_phi_incon = 0
n_jpsi_match = 0
mismatch_details = []

for evt_idx in both_indices:
    i = int(evt_idx)

    # GEN best
    g_p_idx = int(gen_p_idx[i])
    g_j1 = int(gen_j1_idx[i])
    g_j2 = int(gen_j2_idx[i])
    g_j1_pt = float(gen_j1_pt[i])
    g_j2_pt = float(gen_j2_pt[i])
    g_p_pt = float(gen_p_pt[i])

    # RECO best candidate index
    bi = int(best_idx[i])

    # ── φ matching ──
    pk1_gm = int(pk1_gmidx[i][bi])
    pk2_gm = int(pk2_gmidx[i][bi])
    pk1_src = int(pk1_gmsrc[i][bi])
    pk2_src = int(pk2_gmsrc[i][bi])

    p_a1 = first_ancestor(gen_pdg[i], gen_mom[i], pk1_gm, 333) if pk1_src == 1 else -1
    p_a2 = first_ancestor(gen_pdg[i], gen_mom[i], pk2_gm, 333) if pk2_src == 1 else -1

    if p_a1 >= 0 and p_a1 == p_a2:
        phi_leg = p_a1
    else:
        phi_leg = -1

    # ── J/ψ matching ──
    def muon_ancestor(mu_idx, target):
        if mu_idx < 0 or mu_idx >= len(mu_gmidx[i]):
            return -1
        gm = int(mu_gmidx[i][mu_idx])
        src = int(mu_gmsrc[i][mu_idx])
        return first_ancestor(gen_pdg[i], gen_mom[i], gm, target) if src == 1 else -1

    j1m1 = int(j1_mu1[i][bi]); j1m2 = int(j1_mu2[i][bi])
    j2m1 = int(j2_mu1[i][bi]); j2m2 = int(j2_mu2[i][bi])

    j1a1 = muon_ancestor(j1m1, 443); j1a2 = muon_ancestor(j1m2, 443)
    j2a1 = muon_ancestor(j2m1, 443); j2a2 = muon_ancestor(j2m2, 443)

    j1_leg = j1a1 if (j1a1 >= 0 and j1a1 == j1a2) else -1
    j2_leg = j2a1 if (j2a1 >= 0 and j2a1 == j2a2) else -1

    # ── Classification ──
    if phi_leg == g_p_idx:
        n_phi_match += 1
    elif phi_leg >= 0:
        n_phi_mismatch += 1
        mismatch_details.append({
            "evt": i, "n_gen_phi": int(n_p[i]),
            "gen_phi_idx": g_p_idx, "gen_phi_pt": g_p_pt,
            "reco_phi_idx": phi_leg, "reco_phi_pt": float(p_pt[i][bi]),
            "reco_phi_mass": float(p_m[i][bi]),
        })
    else:
        n_phi_incon += 1

    j_ok = (j1_leg == g_j1 and j2_leg == g_j2) or (j1_leg == g_j2 and j2_leg == g_j1)
    if j_ok:
        n_jpsi_match += 1


# ── Step 4: Report ──

print()
print("=" * 70)
print("GEN-RECO φ CONSISTENCY ANALYSIS")
print("=" * 70)
print(f"  Ntuple: JJP_DPS2_CS (1 file, {n_total} events)")
print(f"  Full GEN (>=2 J/psi pT>6, >=1 phi pT>4):  {n_full:>6}")
print(f"    with >=2 phi (pT>4):                      {n_mp:>6}  ({100*n_mp/n_full:5.2f}%)")
print(f"  Both GEN + RECO selection:                  {n_both:>6}")
print()
print(f"  ── φ matching (best RECO candidate) ──")
print(f"  RECO φ matches GEN-best φ:                 {n_phi_match:>6}  ({100*n_phi_match/n_both:5.2f}%)")
print(f"  RECO φ matches DIFFERENT gen φ:            {n_phi_mismatch:>6}  ({100*n_phi_mismatch/n_both:5.2f}%)")
print(f"  RECO φ inconsistent (no common mother):    {n_phi_incon:>6}  ({100*n_phi_incon/n_both:5.2f}%)")
print()
print(f"  ── J/ψ matching ──")
print(f"  Both J/ψ match GEN-best pair:              {n_jpsi_match:>6}  ({100*n_jpsi_match/n_both:5.2f}%)")

if mismatch_details:
    print()
    print(f"  ── Mismatch events ──")
    for d in mismatch_details[:15]:
        print(f"  Evt {d['evt']}: n_gen_φ={d['n_gen_phi']}  "
              f"GEN φ_idx={d['gen_phi_idx']} pT={d['gen_phi_pt']:.1f}  "
              f"RECO φ_idx={d['reco_phi_idx']} pT={d['reco_phi_pt']:.1f}  "
              f"m={d['reco_phi_mass']:.3f}")

print()
print("Done.")

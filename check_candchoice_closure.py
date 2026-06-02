#!/usr/bin/env python3
"""candChoice closure and response matrix analysis.

Implements the diagnostics from multi-phi-scheme.md:
- f_correctChoice vs N_φ^gen, pT(φ_gen), m(J/ψ J/ψ φ)_gen, ΔS/S
- Response matrix R_ji for pT(φ)
- Purity and stability per bin

Fully vectorized with Awkward Arrays.
"""
from __future__ import annotations

import awkward as ak
import numpy as np
import uproot


# ── port of _ancestor_idx_to_pdg from efficiency_workflow.efficiency ──

def _ancestor_idx_to_pdg(match_idx, gen_pdg, gen_mother, target_abs_pdg, max_depth=16):
    """Walk up gen mother chain from match_idx → target PDG ancestor.
    match_idx: flat int64 (one per event). gen_pdg, gen_mother: jagged.
    Returns flat int64 (ancestor index or -1)."""
    idx = ak.values_astype(match_idx, np.int64)
    found = ak.full_like(idx, -1, dtype=np.int64)
    active = idx >= 0
    for _ in range(max_depth):
        pdg_at = ak.fill_none(gen_pdg[idx], 0)
        is_target = active & (abs(pdg_at) == target_abs_pdg)
        found = ak.where((found < 0) & is_target, idx, found)
        next_idx = ak.fill_none(gen_mother[idx], -1)
        active = active & (found < 0) & (next_idx >= 0)
        idx = ak.where(active, next_idx, idx)
    return found


def _nth(arr, n, default):
    """N-th element of each jagged sublist, with default for missing."""
    return ak.fill_none(ak.pad_none(arr, n + 1, axis=1)[:, n], default)


def _p4_from_pt_eta_phi_m(pt, eta, phi, mass):
    """Convert (pt, eta, phi, mass) → (px, py, pz, e)."""
    px = pt * np.cos(phi)
    py = pt * np.sin(phi)
    pz = pt * np.sinh(eta)
    e = np.sqrt(px * px + py * py + pz * pz + mass * mass)
    return px, py, pz, e


# ── load ──

NTUPLE = ("root://cceos.ihep.ac.cn/"
          "///eos/ihep/cms/store/user/xcheng/MC_Production_v3/output/"
          "JJP_DPS2_CS/0/output_ntuple.root:mkcands/X_data")

print("Loading ...", flush=True)
f = uproot.open(NTUPLE)

# GEN
g_pt  = f["MC_GenPart_pt"].array()
g_pdg = f["MC_GenPart_pdgId"].array()
g_mom = f["MC_GenPart_motherGenIdx"].array()
g_eta = f["MC_GenPart_eta"].array()
g_phi_arr = f["MC_GenPart_phi"].array()
g_mass = f["MC_GenPart_mass"].array()
g_idx  = ak.local_index(g_pt)

# RECO — candidate-level (jagged: n_evt × n_cand)
j1_pt  = f["Jpsi_1_pt"].array()
j2_pt  = f["Jpsi_2_pt"].array()
p_pt   = f["Phi_pt"].array()
j1_m   = f["Jpsi_1_mass"].array()
j2_m   = f["Jpsi_2_mass"].array()
p_m    = f["Phi_mass"].array()
j1_px  = f["Jpsi_1_px"].array(); j1_py = f["Jpsi_1_py"].array(); j1_pz = f["Jpsi_1_pz"].array()
j2_px  = f["Jpsi_2_px"].array(); j2_py = f["Jpsi_2_py"].array(); j2_pz = f["Jpsi_2_pz"].array()
p_px   = f["Phi_px"].array();     p_py  = f["Phi_py"].array();     p_pz  = f["Phi_pz"].array()
j1_vp  = f["Jpsi_1_VtxProb"].array()
j2_vp  = f["Jpsi_2_VtxProb"].array()

# RECO — per-candidate muon/kaon indices
j1_mu1 = f["Jpsi_1_mu_1_Idx"].array(); j1_mu2 = f["Jpsi_1_mu_2_Idx"].array()
j2_mu1 = f["Jpsi_2_mu_1_Idx"].array(); j2_mu2 = f["Jpsi_2_mu_2_Idx"].array()

# RECO — gen matching
mu_gmidx  = f["muGenMatchIdx"].array()
mu_gmsrc  = f["muGenMatchSource"].array()
pk1_gmidx = f["Phi_K_1_genMatchIdx"].array()
pk1_gmsrc = f["Phi_K_1_genMatchSource"].array()
pk2_gmidx = f["Phi_K_2_genMatchIdx"].array()
pk2_gmsrc = f["Phi_K_2_genMatchSource"].array()

n_total = len(g_pt)
print(f"  {n_total} events loaded", flush=True)


# ═══════════════════════════════════════════════════════════════
# Step 1: GEN best-score candidate (vectorized)
# ═══════════════════════════════════════════════════════════════

print("Step 1: GEN best-score ...", flush=True)
is_mu = abs(g_pdg) == 13
is_ka = abs(g_pdg) == 321
n_mu_d   = ak.sum(g_mom[is_mu][:, :, None] == g_idx[:, None, :], axis=1)
n_kaon_d = ak.sum(g_mom[is_ka][:, :, None] == g_idx[:, None, :], axis=1)

vj = (abs(g_pdg) == 443) & (n_mu_d >= 2) & (g_pt > 6.0)
vp = (abs(g_pdg) == 333) & (n_kaon_d >= 2) & (g_pt > 4.0)

jo = ak.argsort(g_pt[vj], ascending=False)
po = ak.argsort(g_pt[vp], ascending=False)

j_idx_s = g_idx[vj][jo]; j_pt_s = g_pt[vj][jo]; j_eta_s = g_eta[vj][jo]
j_phi_s = g_phi_arr[vj][jo]; j_mass_s = g_mass[vj][jo]
p_idx_s = g_idx[vp][po]; p_pt_s = g_pt[vp][po]; p_eta_s = g_eta[vp][po]
p_phi_s = g_phi_arr[vp][po]; p_mass_s = g_mass[vp][po]

gen_j1_idx = _nth(j_idx_s, 0, -1); gen_j2_idx = _nth(j_idx_s, 1, -1)
gen_j1_pt  = _nth(j_pt_s,  0, np.nan); gen_j2_pt  = _nth(j_pt_s,  1, np.nan)
gen_p_idx  = _nth(p_idx_s, 0, -1);     gen_p_pt   = _nth(p_pt_s,  0, np.nan)

# GEN kinematics for best candidate
gen_j1_eta = _nth(j_eta_s, 0, np.nan); gen_j2_eta = _nth(j_eta_s, 1, np.nan)
gen_j1_phi = _nth(j_phi_s, 0, np.nan); gen_j2_phi = _nth(j_phi_s, 1, np.nan)
gen_j1_m   = _nth(j_mass_s, 0, np.nan); gen_j2_m   = _nth(j_mass_s, 1, np.nan)
gen_p_eta  = _nth(p_eta_s, 0, np.nan)
gen_p_phi  = _nth(p_phi_s, 0, np.nan)
gen_p_m    = _nth(p_mass_s, 0, np.nan)

n_j = ak.num(j_idx_s, axis=1)
n_p = ak.num(p_idx_s, axis=1)
has_full_gen = (n_j >= 2) & (n_p >= 1)
has_multi_phi = has_full_gen & (n_p >= 2)

n_full = int(ak.sum(has_full_gen))
n_mp = int(ak.sum(has_multi_phi))
print(f"  Full GEN: {n_full}  (multi-φ: {n_mp} = {100*n_mp/n_full:.2f}%)", flush=True)

# GEN triple mass
gj1_px, gj1_py, gj1_pz, gj1_e = _p4_from_pt_eta_phi_m(gen_j1_pt, gen_j1_eta, gen_j1_phi, gen_j1_m)
gj2_px, gj2_py, gj2_pz, gj2_e = _p4_from_pt_eta_phi_m(gen_j2_pt, gen_j2_eta, gen_j2_phi, gen_j2_m)
gp_px,  gp_py,  gp_pz,  gp_e  = _p4_from_pt_eta_phi_m(gen_p_pt,  gen_p_eta,  gen_p_phi,  gen_p_m)
gen_triple_mass = np.sqrt(np.maximum(
    (gj1_e + gj2_e + gp_e)**2
    - (gj1_px + gj2_px + gp_px)**2
    - (gj1_py + gj2_py + gp_py)**2
    - (gj1_pz + gj2_pz + gp_pz)**2,
    0.0))

# GEN best score and second-best score (for ΔS/S)
gen_best_score = gen_j1_pt**2 + gen_j2_pt**2 + gen_p_pt**2
# Second-best: if n_j >= 3: replace j2 with j3; if n_p >= 2: replace p with p2
# For events with only 2 J/ψ and 1 φ: second-best = None
has_second_gen = (n_j >= 3) | (n_p >= 2)
gen_j3_pt = _nth(j_pt_s, 2, np.nan)
gen_p2_pt = _nth(p_pt_s, 1, np.nan)
# Cases: swap J/ψ2→J/ψ3, or swap φ→φ2
score_swap_j = gen_j1_pt**2 + gen_j3_pt**2 + gen_p_pt**2
score_swap_p = gen_j1_pt**2 + gen_j2_pt**2 + gen_p2_pt**2
gen_second_score = ak.where(
    (n_j >= 3) & (n_p >= 2),
    ak.where(score_swap_j > score_swap_p, score_swap_j, score_swap_p),
    ak.where(n_j >= 3, score_swap_j, ak.where(n_p >= 2, score_swap_p, np.nan)))
delta_S_over_S = ak.where(
    gen_best_score > 0,
    (gen_best_score - gen_second_score) / gen_best_score,
    np.nan)


# ═══════════════════════════════════════════════════════════════
# Step 2: RECO best-score candidate (vectorized)
# ═══════════════════════════════════════════════════════════════

print("Step 2: RECO best-score ...", flush=True)

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

# ═══════════════════════════════════════════════════════════════
# Step 3: Mask to events with both, vectorized gen-matching
# ═══════════════════════════════════════════════════════════════

print("Step 3: Vectorized gen-matching ...", flush=True)

mask_both = has_full_gen & has_reco
n_both = int(ak.sum(mask_both))
print(f"  Both GEN + RECO: {n_both}", flush=True)

# Convert flat arrays to numpy; keep jagged as awkward masked for per-event access
g_pdg_m = g_pdg[mask_both]
g_mom_m = g_mom[mask_both]

j1_pt_m  = j1_pt[mask_both];  j2_pt_m = j2_pt[mask_both];   p_pt_m  = p_pt[mask_both]
j1_m_m   = j1_m[mask_both];   j2_m_m  = j2_m[mask_both];    p_m_m   = p_m[mask_both]
j1_px_m  = j1_px[mask_both];  j1_py_m = j1_py[mask_both];   j1_pz_m = j1_pz[mask_both]
j2_px_m  = j2_px[mask_both];  j2_py_m = j2_py[mask_both];   j2_pz_m = j2_pz[mask_both]
p_px_m   = p_px[mask_both];   p_py_m  = p_py[mask_both];    p_pz_m  = p_pz[mask_both]
j1_mu1_m = j1_mu1[mask_both]; j1_mu2_m = j1_mu2[mask_both]
j2_mu1_m = j2_mu1[mask_both]; j2_mu2_m = j2_mu2[mask_both]
mu_gmidx_m = mu_gmidx[mask_both]; mu_gmsrc_m = mu_gmsrc[mask_both]
pk1_gm_m = pk1_gmidx[mask_both]; pk1_src_m = pk1_gmsrc[mask_both]
pk2_gm_m = pk2_gmidx[mask_both]; pk2_src_m = pk2_gmsrc[mask_both]

both_idx_np  = ak.to_numpy(ak.where(mask_both)[0])
bi_np        = ak.to_numpy(best_idx[mask_both])
g_j1_np      = ak.to_numpy(gen_j1_idx[mask_both])
g_j2_np      = ak.to_numpy(gen_j2_idx[mask_both])
g_p_np       = ak.to_numpy(gen_p_idx[mask_both])
g_j1_pt_np   = ak.to_numpy(gen_j1_pt[mask_both])
g_j2_pt_np   = ak.to_numpy(gen_j2_pt[mask_both])
g_p_pt_np    = ak.to_numpy(gen_p_pt[mask_both])
g_tm_np      = ak.to_numpy(gen_triple_mass[mask_both])
g_np_np      = ak.to_numpy(n_p[mask_both])
g_dS_np      = ak.to_numpy(delta_S_over_S[mask_both])

# Per-event gen matching + kinematics (numpy loop, ~115 events)
def _first_ancestor(pdg_list, mother_list, start_idx, target_abs_pdg, max_depth=16):
    idx = int(start_idx)
    for _ in range(max_depth):
        if idx < 0 or idx >= len(pdg_list): return -1
        if abs(int(pdg_list[idx])) == target_abs_pdg: return idx
        idx = int(mother_list[idx])
    return -1

n_evt = len(both_idx_np)
cc_arr     = np.zeros(n_evt, dtype=bool)
phi_ok_arr = np.zeros(n_evt, dtype=bool)
jpsi_ok_arr = np.zeros(n_evt, dtype=bool)
r_p_pt_arr  = np.zeros(n_evt)
r_tm_arr    = np.zeros(n_evt)
g_tm_arr    = np.zeros(n_evt)
g_p_pt_arr  = np.zeros(n_evt)

for k in range(n_evt):
    bi = int(bi_np[k])
    # GEN flat
    g_p = int(g_p_np[k]); g_j1 = int(g_j1_np[k]); g_j2 = int(g_j2_np[k])
    g_p_pt_arr[k] = g_p_pt_np[k]; g_tm_arr[k] = g_tm_np[k]

    # GEN jagged (per-event sublists → numpy)
    g_pdg_k = ak.to_numpy(g_pdg_m[k])
    g_mom_k = ak.to_numpy(g_mom_m[k])

    # RECO kinematics (jagged → numpy for this event)
    r_p_pt_arr[k] = float(p_pt_m[k][bi])
    r_j1_px = float(j1_px_m[k][bi]); r_j1_py = float(j1_py_m[k][bi]); r_j1_pz = float(j1_pz_m[k][bi])
    r_j2_px = float(j2_px_m[k][bi]); r_j2_py = float(j2_py_m[k][bi]); r_j2_pz = float(j2_pz_m[k][bi])
    r_p_px  = float(p_px_m[k][bi]);  r_p_py  = float(p_py_m[k][bi]);  r_p_pz  = float(p_pz_m[k][bi])
    r_j1_m  = float(j1_m_m[k][bi]);  r_j2_m  = float(j2_m_m[k][bi]);  r_p_m  = float(p_m_m[k][bi])
    r_j1_e  = np.sqrt(r_j1_px**2 + r_j1_py**2 + r_j1_pz**2 + r_j1_m**2)
    r_j2_e  = np.sqrt(r_j2_px**2 + r_j2_py**2 + r_j2_pz**2 + r_j2_m**2)
    r_p_e   = np.sqrt(r_p_px**2  + r_p_py**2  + r_p_pz**2  + r_p_m**2)
    tpx = r_j1_px + r_j2_px + r_p_px
    tpy = r_j1_py + r_j2_py + r_p_py
    tpz = r_j1_pz + r_j2_pz + r_p_pz
    te  = r_j1_e + r_j2_e + r_p_e
    r_tm_arr[k] = np.sqrt(max(0, te*te - tpx*tpx - tpy*tpy - tpz*tpz))

    # φ matching
    pk1_gm = int(pk1_gm_m[k][bi]); pk2_gm = int(pk2_gm_m[k][bi])
    pk1_src = int(pk1_src_m[k][bi]); pk2_src = int(pk2_src_m[k][bi])
    p_a1 = _first_ancestor(g_pdg_k, g_mom_k, pk1_gm, 333) if pk1_src == 1 else -1
    p_a2 = _first_ancestor(g_pdg_k, g_mom_k, pk2_gm, 333) if pk2_src == 1 else -1
    p_leg = p_a1 if (p_a1 >= 0 and p_a1 == p_a2) else -1

    # J/ψ matching
    j1_mu1 = int(j1_mu1_m[k][bi]); j1_mu2 = int(j1_mu2_m[k][bi])
    j2_mu1 = int(j2_mu1_m[k][bi]); j2_mu2 = int(j2_mu2_m[k][bi])
    mu_gmidx_k = ak.to_numpy(mu_gmidx_m[k])
    mu_gmsrc_k = ak.to_numpy(mu_gmsrc_m[k])

    def _mu_anc(mu_idx, target):
        if mu_idx < 0 or mu_idx >= len(mu_gmidx_k): return -1
        gm = int(mu_gmidx_k[mu_idx])
        src = int(mu_gmsrc_k[mu_idx])
        return _first_ancestor(g_pdg_k, g_mom_k, gm, target) if src == 1 else -1

    j1a1 = _mu_anc(j1_mu1, 443); j1a2 = _mu_anc(j1_mu2, 443)
    j2a1 = _mu_anc(j2_mu1, 443); j2a2 = _mu_anc(j2_mu2, 443)
    j1_leg = j1a1 if (j1a1 >= 0 and j1a1 == j1a2) else -1
    j2_leg = j2a1 if (j2a1 >= 0 and j2a1 == j2a2) else -1

    phi_ok_arr[k]  = (p_leg == g_p)
    jpsi_ok_arr[k] = ((j1_leg == g_j1 and j2_leg == g_j2) or (j1_leg == g_j2 and j2_leg == g_j1))
    cc_arr[k] = phi_ok_arr[k] and jpsi_ok_arr[k]


# ═══════════════════════════════════════════════════════════════
# Step 4: Diagnostics (numpy, n_evt = n_both events)
# ═══════════════════════════════════════════════════════════════

print()
print("=" * 70)
print("candChoice CLOSURE ANALYSIS")
print("=" * 70)
print(f"  Ntuple: JJP_DPS2_CS (1 file, {n_total} events)")
print(f"  Full GEN: {n_full}  |  multi-φ: {n_mp} ({100*n_mp/n_full:.2f}%)")
print(f"  Both GEN + RECO: {n_evt}")
print()

# ── 4a: Inclusive f_correctChoice ──

n_cc = int(np.sum(cc_arr))
print(f"  ── Inclusive correct-choice rate ──")
print(f"  Correct choice (c_reco* ↔ c_gen*):  {n_cc:>5} / {n_evt}  ({100*n_cc/n_evt:.1f}%)")
print(f"  φ mismatch only:                     {int(np.sum((~phi_ok_arr) & jpsi_ok_arr)):>5}")
print(f"  J/ψ mismatch only:                   {int(np.sum(phi_ok_arr & ~jpsi_ok_arr)):>5}")
print(f"  Both mismatch:                       {int(np.sum((~phi_ok_arr) & (~jpsi_ok_arr))):>5}")
print()

# ── 4b: f_correctChoice vs N_φ^gen ──

print(f"  ── f_correctChoice vs N_φ^gen ──")
for ng in [1, 2]:
    mask = g_np_np == ng
    n_tot = int(np.sum(mask))
    n_ok  = int(np.sum(cc_arr & mask)) if n_tot > 0 else 0
    print(f"  N_φ^gen = {ng}:  {n_ok}/{n_tot}  ({100*n_ok/max(1,n_tot):.1f}%)")
mask3 = g_np_np >= 3
n_tot3 = int(np.sum(mask3))
n_ok3  = int(np.sum(cc_arr & mask3)) if n_tot3 > 0 else 0
if n_tot3 > 0:
    print(f"  N_φ^gen ≥ 3:  {n_ok3}/{n_tot3}  ({100*n_ok3/max(1,n_tot3):.1f}%)")
print()

# ── 4c: Response matrix for pT(φ) ──

phi_pt_bins = np.array([4.0, 6.0, 10.0, 20.0, 50.0], dtype=np.float64)
n_bins = len(phi_pt_bins) - 1

R = np.zeros((n_bins, n_bins))
for k in range(n_evt):
    ig = np.digitize(g_p_pt_arr[k], phi_pt_bins) - 1
    jr = np.digitize(r_p_pt_arr[k], phi_pt_bins) - 1
    if 0 <= ig < n_bins and 0 <= jr < n_bins:
        R[ig, jr] += 1

R_row = R.copy()
for i in range(n_bins):
    if R_row[i].sum() > 0:
        R_row[i] /= R_row[i].sum()

R_col = R.copy()
for j in range(n_bins):
    if R_col[:, j].sum() > 0:
        R_col[:, j] /= R_col[:, j].sum()

stability = np.array([R_row[i, i] if R[i].sum() > 0 else np.nan for i in range(n_bins)])
purity    = np.array([R_col[i, i] if R[:, i].sum() > 0 else np.nan for i in range(n_bins)])

bin_labels = [f"[{phi_pt_bins[i]:.0f},{phi_pt_bins[i+1]:.0f})" for i in range(n_bins)]
print(f"  ── Response matrix for pT(φ) ──")
print(f"  Bins: {bin_labels}")
print()
hdr = "  " + " " * 12 + "".join(f"  reco{bl:>12s}" for bl in bin_labels)
print(hdr)
for i in range(n_bins):
    vals = "  ".join(f"{R_row[i, j]:>12.3f}" if R[i].sum() > 0 else f"{0:>12.3f}" for j in range(n_bins))
    print(f"  gen{bin_labels[i]:>12s}  {vals}")
print()
print(f"  {'Purity':>12s}:  " + "  ".join(f"{purity[j]:>12.3f}" if not np.isnan(purity[j]) else f"{'N/A':>12s}" for j in range(n_bins)))
print(f"  {'Stability':>12s}:  " + "  ".join(f"{stability[i]:>12.3f}" if not np.isnan(stability[i]) else f"{'N/A':>12s}" for i in range(n_bins)))
print()

# ── 4d: f_correctChoice vs pT(φ_gen) ──

print(f"  ── f_correctChoice vs pT(φ_gen) ──")
for ib in range(n_bins):
    mask_pt = (g_p_pt_arr >= phi_pt_bins[ib]) & (g_p_pt_arr < phi_pt_bins[ib + 1])
    n_pt = int(np.sum(mask_pt))
    n_cc_pt = int(np.sum(cc_arr & mask_pt))
    if n_pt > 0:
        print(f"  pT(φ_gen) {bin_labels[ib]:>12s}:  {n_cc_pt:>4}/{n_pt:<4}  ({100*n_cc_pt/n_pt:.1f}%)")

# ── 4e: f_correctChoice vs triple mass ──

tm_finite = np.isfinite(g_tm_arr)
if np.sum(tm_finite) > 0:
    tm_vals = g_tm_arr[tm_finite]
    tm_lo, tm_hi = np.percentile(tm_vals, [5, 95])
    tm_bins = np.linspace(tm_lo, tm_hi, 5)
    print()
    print(f"  ── f_correctChoice vs m(J/ψ J/ψ φ)_gen ──")
    for ib in range(len(tm_bins) - 1):
        mask_tm = tm_finite & (g_tm_arr >= tm_bins[ib]) & (g_tm_arr < tm_bins[ib + 1])
        n_tm = int(np.sum(mask_tm))
        n_cc_tm = int(np.sum(cc_arr & mask_tm))
        if n_tm > 0:
            print(f"  m(triple) [{tm_bins[ib]:.0f},{tm_bins[ib+1]:.0f}):  {n_cc_tm:>4}/{n_tm:<4}  ({100*n_cc_tm/n_tm:.1f}%)")

# ── 4f: f_correctChoice vs ΔS/S ──

dS_finite = np.isfinite(g_dS_np)
if np.sum(dS_finite) > 0:
    dS_bins = np.array([0.0, 0.05, 0.1, 0.3, 1.0])
    print()
    print(f"  ── f_correctChoice vs ΔS/S ──")
    for ib in range(len(dS_bins) - 1):
        mask_ds = dS_finite & (g_dS_np >= dS_bins[ib]) & (g_dS_np < dS_bins[ib + 1])
        n_ds = int(np.sum(mask_ds))
        n_cc_ds = int(np.sum(cc_arr & mask_ds))
        if n_ds > 0:
            print(f"  ΔS/S [{dS_bins[ib]:.2f},{dS_bins[ib+1]:.2f}):  {n_cc_ds:>4}/{n_ds:<4}  ({100*n_cc_ds/n_ds:.1f}%)")

print()
print("Done.")

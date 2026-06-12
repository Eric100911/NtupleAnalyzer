#!/usr/bin/env python3
"""candChoice closure and response matrix analysis.

Implements the diagnostics from multi-phi-scheme.md:
- f_correctChoice vs N_phi^gen, pT(phi_gen), m(J/psi J/psi phi)_gen, DeltaS/S
- Response matrix R_ji for pT(phi)
- Purity and stability per bin

Fully vectorized with Awkward Arrays.
"""
from __future__ import annotations

import awkward as ak
import numpy as np
import uproot


# ── port of _ancestor_idx_to_pdg from efficiency_workflow.efficiency ──

def _ancestor_idx_to_pdg(match_idx, gen_pdg, gen_mother, target_abs_pdg, max_depth=16):
    """Walk up gen mother chain from match_idx -> target PDG ancestor.

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
    """Convert (pt, eta, phi, mass) -> (px, py, pz, e)."""
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

# RECO — candidate-level (jagged: n_evt x n_cand)
jpsi1_pt  = f["Jpsi_1_pt"].array()
jpsi2_pt  = f["Jpsi_2_pt"].array()
phi_pt   = f["Phi_pt"].array()
jpsi1_mass   = f["Jpsi_1_mass"].array()
jpsi2_mass   = f["Jpsi_2_mass"].array()
phi_mass    = f["Phi_mass"].array()
jpsi1_px  = f["Jpsi_1_px"].array(); jpsi1_py = f["Jpsi_1_py"].array(); jpsi1_pz = f["Jpsi_1_pz"].array()
jpsi2_px  = f["Jpsi_2_px"].array(); jpsi2_py = f["Jpsi_2_py"].array(); jpsi2_pz = f["Jpsi_2_pz"].array()
phi_px   = f["Phi_px"].array();     phi_py  = f["Phi_py"].array();     phi_pz  = f["Phi_pz"].array()
jpsi1_vtx_prob  = f["Jpsi_1_VtxProb"].array()
jpsi2_vtx_prob  = f["Jpsi_2_VtxProb"].array()

# RECO — per-candidate muon/kaon indices
jpsi1_mu1_idx = f["Jpsi_1_mu_1_Idx"].array(); jpsi1_mu2_idx = f["Jpsi_1_mu_2_Idx"].array()
jpsi2_mu1_idx = f["Jpsi_2_mu_1_Idx"].array(); jpsi2_mu2_idx = f["Jpsi_2_mu_2_Idx"].array()

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

gen_jpsi1_idx = _nth(j_idx_s, 0, -1); gen_jpsi2_idx = _nth(j_idx_s, 1, -1)
gen_jpsi1_pt  = _nth(j_pt_s,  0, np.nan); gen_jpsi2_pt  = _nth(j_pt_s,  1, np.nan)
gen_phi_idx  = _nth(p_idx_s, 0, -1);     gen_phi_pt   = _nth(p_pt_s,  0, np.nan)

# GEN kinematics for best candidate
gen_jpsi1_eta = _nth(j_eta_s, 0, np.nan); gen_jpsi2_eta = _nth(j_eta_s, 1, np.nan)
gen_jpsi1_phi = _nth(j_phi_s, 0, np.nan); gen_jpsi2_phi = _nth(j_phi_s, 1, np.nan)
gen_jpsi1_mass   = _nth(j_mass_s, 0, np.nan); gen_jpsi2_mass   = _nth(j_mass_s, 1, np.nan)
gen_phi_eta  = _nth(p_eta_s, 0, np.nan)
gen_phi_phi  = _nth(p_phi_s, 0, np.nan)
gen_phi_mass    = _nth(p_mass_s, 0, np.nan)

n_jpsi = ak.num(j_idx_s, axis=1)
n_phi = ak.num(p_idx_s, axis=1)
has_full_gen = (n_jpsi >= 2) & (n_phi >= 1)
has_multi_phi = has_full_gen & (n_phi >= 2)

n_full = int(ak.sum(has_full_gen))
n_mp = int(ak.sum(has_multi_phi))
print(f"  Full GEN: {n_full}  (multi-phi: {n_mp} = {100*n_mp/n_full:.2f}%)", flush=True)

# GEN triple mass
gen_jpsi1_px, gen_jpsi1_py, gen_jpsi1_pz, gen_jpsi1_energy = _p4_from_pt_eta_phi_m(gen_jpsi1_pt, gen_jpsi1_eta, gen_jpsi1_phi, gen_jpsi1_mass)
gen_jpsi2_px, gen_jpsi2_py, gen_jpsi2_pz, gen_jpsi2_energy = _p4_from_pt_eta_phi_m(gen_jpsi2_pt, gen_jpsi2_eta, gen_jpsi2_phi, gen_jpsi2_mass)
gen_phi_px,  gen_phi_py,  gen_phi_pz,  gen_phi_energy  = _p4_from_pt_eta_phi_m(gen_phi_pt,  gen_phi_eta,  gen_phi_phi,  gen_phi_mass)
gen_triple_mass = np.sqrt(np.maximum(
    (gen_jpsi1_energy + gen_jpsi2_energy + gen_phi_energy)**2
    - (gen_jpsi1_px + gen_jpsi2_px + gen_phi_px)**2
    - (gen_jpsi1_py + gen_jpsi2_py + gen_phi_py)**2
    - (gen_jpsi1_pz + gen_jpsi2_pz + gen_phi_pz)**2,
    0.0))

# GEN best score and second-best score (for DeltaS/S)
gen_best_score = gen_jpsi1_pt**2 + gen_jpsi2_pt**2 + gen_phi_pt**2
# Second-best: if n_jpsi >= 3: replace jpsi2 with jpsi3; if n_phi >= 2: replace p with p2
# For events with only 2 J/psi and 1 phi: second-best = None
has_second_gen = (n_jpsi >= 3) | (n_phi >= 2)
gen_jpsi3_pt = _nth(j_pt_s, 2, np.nan)
gen_phi2_pt = _nth(p_pt_s, 1, np.nan)
# Cases: swap J/psi2->J/psi3, or swap phi->phi2
score_swap_jpsi = gen_jpsi1_pt**2 + gen_jpsi3_pt**2 + gen_phi_pt**2
score_swap_phi = gen_jpsi1_pt**2 + gen_jpsi2_pt**2 + gen_phi2_pt**2
gen_second_score = ak.where(
    (n_jpsi >= 3) & (n_phi >= 2),
    ak.where(score_swap_jpsi > score_swap_phi, score_swap_jpsi, score_swap_phi),
    ak.where(n_jpsi >= 3, score_swap_jpsi, ak.where(n_phi >= 2, score_swap_phi, np.nan)))
delta_S_over_S = ak.where(
    gen_best_score > 0,
    (gen_best_score - gen_second_score) / gen_best_score,
    np.nan)


# ═══════════════════════════════════════════════════════════════
# Step 2: RECO best-score candidate (vectorized)
# ═══════════════════════════════════════════════════════════════

print("Step 2: RECO best-score ...", flush=True)

jpsi1_energy = np.sqrt(jpsi1_px**2 + jpsi1_py**2 + jpsi1_pz**2 + jpsi1_mass**2)
jpsi2_energy = np.sqrt(jpsi2_px**2 + jpsi2_py**2 + jpsi2_pz**2 + jpsi2_mass**2)
jpsi1_abs_y = abs(0.5 * np.log((jpsi1_energy + jpsi1_pz) / (jpsi1_energy - jpsi1_pz + 1e-30)))
jpsi2_abs_y = abs(0.5 * np.log((jpsi2_energy + jpsi2_pz) / (jpsi2_energy - jpsi2_pz + 1e-30)))

quality = (
    (jpsi1_mass >= 2.9) & (jpsi1_mass <= 3.3) & (jpsi1_pt > 6.0) & (jpsi1_abs_y < 2.5) & (jpsi1_vtx_prob > 0.01)
    & (jpsi2_mass >= 2.9) & (jpsi2_mass <= 3.3) & (jpsi2_pt > 6.0) & (jpsi2_abs_y < 2.5) & (jpsi2_vtx_prob > 0.01)
    & (phi_mass >= 0.99) & (phi_mass <= 1.07) & (phi_pt > 4.0)
)

score = jpsi1_pt**2 + jpsi2_pt**2 + phi_pt**2
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

jpsi1_pt_masked  = jpsi1_pt[mask_both];  jpsi2_pt_masked = jpsi2_pt[mask_both];   phi_pt_masked  = phi_pt[mask_both]
jpsi1_mass_masked   = jpsi1_mass[mask_both];   jpsi2_mass_masked  = jpsi2_mass[mask_both];    phi_mass_masked   = phi_mass[mask_both]
jpsi1_px_masked  = jpsi1_px[mask_both];  jpsi1_py_masked = jpsi1_py[mask_both];   jpsi1_pz_masked = jpsi1_pz[mask_both]
jpsi2_px_masked  = jpsi2_px[mask_both];  jpsi2_py_masked = jpsi2_py[mask_both];   jpsi2_pz_masked = jpsi2_pz[mask_both]
phi_px_masked   = phi_px[mask_both];   phi_py_masked  = phi_py[mask_both];    phi_pz_masked  = phi_pz[mask_both]
jpsi1_mu1_idx_masked = jpsi1_mu1_idx[mask_both]; jpsi1_mu2_idx_masked = jpsi1_mu2_idx[mask_both]
jpsi2_mu1_idx_masked = jpsi2_mu1_idx[mask_both]; jpsi2_mu2_idx_masked = jpsi2_mu2_idx[mask_both]
mu_gmidx_m = mu_gmidx[mask_both]; mu_gmsrc_m = mu_gmsrc[mask_both]
pk1_gm_m = pk1_gmidx[mask_both]; pk1_src_m = pk1_gmsrc[mask_both]
pk2_gm_m = pk2_gmidx[mask_both]; pk2_src_m = pk2_gmsrc[mask_both]

both_idx_np  = ak.to_numpy(ak.where(mask_both)[0])
bi_np        = ak.to_numpy(best_idx[mask_both])
gen_jpsi1_idx_np      = ak.to_numpy(gen_jpsi1_idx[mask_both])
gen_jpsi2_idx_np      = ak.to_numpy(gen_jpsi2_idx[mask_both])
gen_phi_idx_np       = ak.to_numpy(gen_phi_idx[mask_both])
gen_jpsi1_pt_np   = ak.to_numpy(gen_jpsi1_pt[mask_both])
gen_jpsi2_pt_np   = ak.to_numpy(gen_jpsi2_pt[mask_both])
gen_phi_pt_np    = ak.to_numpy(gen_phi_pt[mask_both])
gen_triple_mass_np      = ak.to_numpy(gen_triple_mass[mask_both])
gen_n_phi_np      = ak.to_numpy(n_phi[mask_both])
gen_delta_S_over_S_np      = ak.to_numpy(delta_S_over_S[mask_both])

# Per-event gen matching + kinematics (numpy loop, ~115 events)
def _first_ancestor(pdg_list, mother_list, start_idx, target_abs_pdg, max_depth=16):
    """Walk up the GEN mother chain from start_idx looking for a particle with
    the given target_abs_pdg PDG code.  Returns the index of the ancestor, or -1."""
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
r_phi_pt_arr  = np.zeros(n_evt)
r_tm_arr    = np.zeros(n_evt)
g_tm_arr    = np.zeros(n_evt)
g_phi_pt_arr  = np.zeros(n_evt)

for k in range(n_evt):
    bi = int(bi_np[k])
    # GEN flat
    gen_phi_idx_v = int(gen_phi_idx_np[k]); gen_jpsi1_idx_v = int(gen_jpsi1_idx_np[k]); gen_jpsi2_idx_v = int(gen_jpsi2_idx_np[k])
    g_phi_pt_arr[k] = gen_phi_pt_np[k]; g_tm_arr[k] = gen_triple_mass_np[k]

    # GEN jagged (per-event sublists -> numpy)
    g_pdg_k = ak.to_numpy(g_pdg_m[k])
    g_mom_k = ak.to_numpy(g_mom_m[k])

    # RECO kinematics (jagged -> numpy for this event)
    r_phi_pt_arr[k] = float(phi_pt_masked[k][bi])
    reco_jpsi1_px = float(jpsi1_px_masked[k][bi]); reco_jpsi1_py = float(jpsi1_py_masked[k][bi]); reco_jpsi1_pz = float(jpsi1_pz_masked[k][bi])
    reco_jpsi2_px = float(jpsi2_px_masked[k][bi]); reco_jpsi2_py = float(jpsi2_py_masked[k][bi]); reco_jpsi2_pz = float(jpsi2_pz_masked[k][bi])
    reco_phi_px  = float(phi_px_masked[k][bi]);  reco_phi_py  = float(phi_py_masked[k][bi]);  reco_phi_pz  = float(phi_pz_masked[k][bi])
    reco_jpsi1_mass  = float(jpsi1_mass_masked[k][bi]);  reco_jpsi2_mass  = float(jpsi2_mass_masked[k][bi]);  reco_phi_mass  = float(phi_mass_masked[k][bi])
    reco_jpsi1_energy  = np.sqrt(reco_jpsi1_px**2 + reco_jpsi1_py**2 + reco_jpsi1_pz**2 + reco_jpsi1_mass**2)
    reco_jpsi2_energy  = np.sqrt(reco_jpsi2_px**2 + reco_jpsi2_py**2 + reco_jpsi2_pz**2 + reco_jpsi2_mass**2)
    reco_phi_energy   = np.sqrt(reco_phi_px**2  + reco_phi_py**2  + reco_phi_pz**2  + reco_phi_mass**2)
    tpx = reco_jpsi1_px + reco_jpsi2_px + reco_phi_px
    tpy = reco_jpsi1_py + reco_jpsi2_py + reco_phi_py
    tpz = reco_jpsi1_pz + reco_jpsi2_pz + reco_phi_pz
    te  = reco_jpsi1_energy + reco_jpsi2_energy + reco_phi_energy
    r_tm_arr[k] = np.sqrt(max(0, te*te - tpx*tpx - tpy*tpy - tpz*tpz))

    # phi matching
    pk1_gm = int(pk1_gm_m[k][bi]); pk2_gm = int(pk2_gm_m[k][bi])
    pk1_src = int(pk1_src_m[k][bi]); pk2_src = int(pk2_src_m[k][bi])
    p_a1 = _first_ancestor(g_pdg_k, g_mom_k, pk1_gm, 333) if pk1_src == 1 else -1
    p_a2 = _first_ancestor(g_pdg_k, g_mom_k, pk2_gm, 333) if pk2_src == 1 else -1
    p_leg = p_a1 if (p_a1 >= 0 and p_a1 == p_a2) else -1

    # J/psi matching
    jpsi1_mu1_idx_v = int(jpsi1_mu1_idx_masked[k][bi]); jpsi1_mu2_idx_v = int(jpsi1_mu2_idx_masked[k][bi])
    jpsi2_mu1_idx_v = int(jpsi2_mu1_idx_masked[k][bi]); jpsi2_mu2_idx_v = int(jpsi2_mu2_idx_masked[k][bi])
    mu_gmidx_k = ak.to_numpy(mu_gmidx_m[k])
    mu_gmsrc_k = ak.to_numpy(mu_gmsrc_m[k])

    def _mu_anc(mu_idx, target):
        if mu_idx < 0 or mu_idx >= len(mu_gmidx_k): return -1
        gm = int(mu_gmidx_k[mu_idx])
        src = int(mu_gmsrc_k[mu_idx])
        return _first_ancestor(g_pdg_k, g_mom_k, gm, target) if src == 1 else -1

    jpsi1_ancestor1 = _mu_anc(jpsi1_mu1_idx_v, 443); jpsi1_ancestor2 = _mu_anc(jpsi1_mu2_idx_v, 443)
    jpsi2_ancestor1 = _mu_anc(jpsi2_mu1_idx_v, 443); jpsi2_ancestor2 = _mu_anc(jpsi2_mu2_idx_v, 443)
    jpsi1_leg = jpsi1_ancestor1 if (jpsi1_ancestor1 >= 0 and jpsi1_ancestor1 == jpsi1_ancestor2) else -1
    jpsi2_leg = jpsi2_ancestor1 if (jpsi2_ancestor1 >= 0 and jpsi2_ancestor1 == jpsi2_ancestor2) else -1

    phi_ok_arr[k]  = (p_leg == gen_phi_idx_v)
    jpsi_ok_arr[k] = ((jpsi1_leg == gen_jpsi1_idx_v and jpsi2_leg == gen_jpsi2_idx_v) or (jpsi1_leg == gen_jpsi2_idx_v and jpsi2_leg == gen_jpsi1_idx_v))
    cc_arr[k] = phi_ok_arr[k] and jpsi_ok_arr[k]


# ═══════════════════════════════════════════════════════════════
# Step 4: Diagnostics (numpy, n_evt = n_both events)
# ═══════════════════════════════════════════════════════════════

print()
print("=" * 70)
print("candChoice CLOSURE ANALYSIS")
print("=" * 70)
print(f"  Ntuple: JJP_DPS2_CS (1 file, {n_total} events)")
print(f"  Full GEN: {n_full}  |  multi-phi: {n_mp} ({100*n_mp/n_full:.2f}%)")
print(f"  Both GEN + RECO: {n_evt}")
print()

# ── 4a: Inclusive f_correctChoice ──

n_cc = int(np.sum(cc_arr))
print(f"  ── Inclusive correct-choice rate ──")
print(f"  Correct choice (c_reco* <-> c_gen*):  {n_cc:>5} / {n_evt}  ({100*n_cc/n_evt:.1f}%)")
print(f"  phi mismatch only:                     {int(np.sum((~phi_ok_arr) & jpsi_ok_arr)):>5}")
print(f"  J/psi mismatch only:                   {int(np.sum(phi_ok_arr & ~jpsi_ok_arr)):>5}")
print(f"  Both mismatch:                       {int(np.sum((~phi_ok_arr) & (~jpsi_ok_arr))):>5}")
print()

# ── 4b: f_correctChoice vs N_phi^gen ──

print(f"  ── f_correctChoice vs N_phi^gen ──")
for ng in [1, 2]:
    mask = gen_n_phi_np == ng
    n_tot = int(np.sum(mask))
    n_ok  = int(np.sum(cc_arr & mask)) if n_tot > 0 else 0
    print(f"  N_phi^gen = {ng}:  {n_ok}/{n_tot}  ({100*n_ok/max(1,n_tot):.1f}%)")
mask3 = gen_n_phi_np >= 3
n_tot3 = int(np.sum(mask3))
n_ok3  = int(np.sum(cc_arr & mask3)) if n_tot3 > 0 else 0
if n_tot3 > 0:
    print(f"  N_phi^gen >= 3:  {n_ok3}/{n_tot3}  ({100*n_ok3/max(1,n_tot3):.1f}%)")
print()

# ── 4c: Response matrix for pT(phi) ──

phi_pt_bins = np.array([4.0, 6.0, 10.0, 20.0, 50.0], dtype=np.float64)
n_bins = len(phi_pt_bins) - 1

R = np.zeros((n_bins, n_bins))
for k in range(n_evt):
    ig = np.digitize(g_phi_pt_arr[k], phi_pt_bins) - 1
    jr = np.digitize(r_phi_pt_arr[k], phi_pt_bins) - 1
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
print(f"  ── Response matrix for pT(phi) ──")
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

# ── 4d: f_correctChoice vs pT(phi_gen) ──

print(f"  ── f_correctChoice vs pT(phi_gen) ──")
for ib in range(n_bins):
    mask_pt = (g_phi_pt_arr >= phi_pt_bins[ib]) & (g_phi_pt_arr < phi_pt_bins[ib + 1])
    n_pt = int(np.sum(mask_pt))
    n_cc_pt = int(np.sum(cc_arr & mask_pt))
    if n_pt > 0:
        print(f"  pT(phi_gen) {bin_labels[ib]:>12s}:  {n_cc_pt:>4}/{n_pt:<4}  ({100*n_cc_pt/n_pt:.1f}%)")

# ── 4e: f_correctChoice vs triple mass ──

tm_finite = np.isfinite(g_tm_arr)
if np.sum(tm_finite) > 0:
    tm_vals = g_tm_arr[tm_finite]
    tm_lo, tm_hi = np.percentile(tm_vals, [5, 95])
    tm_bins = np.linspace(tm_lo, tm_hi, 5)
    print()
    print(f"  ── f_correctChoice vs m(J/psi J/psi phi)_gen ──")
    for ib in range(len(tm_bins) - 1):
        mask_tm = tm_finite & (g_tm_arr >= tm_bins[ib]) & (g_tm_arr < tm_bins[ib + 1])
        n_tm = int(np.sum(mask_tm))
        n_cc_tm = int(np.sum(cc_arr & mask_tm))
        if n_tm > 0:
            print(f"  m(triple) [{tm_bins[ib]:.0f},{tm_bins[ib+1]:.0f}):  {n_cc_tm:>4}/{n_tm:<4}  ({100*n_cc_tm/n_tm:.1f}%)")

# ── 4f: f_correctChoice vs DeltaS/S ──

dS_finite = np.isfinite(gen_delta_S_over_S_np)
if np.sum(dS_finite) > 0:
    dS_bins = np.array([0.0, 0.05, 0.1, 0.3, 1.0])
    print()
    print(f"  ── f_correctChoice vs DeltaS/S ──")
    for ib in range(len(dS_bins) - 1):
        mask_ds = dS_finite & (gen_delta_S_over_S_np >= dS_bins[ib]) & (gen_delta_S_over_S_np < dS_bins[ib + 1])
        n_ds = int(np.sum(mask_ds))
        n_cc_ds = int(np.sum(cc_arr & mask_ds))
        if n_ds > 0:
            print(f"  DeltaS/S [{dS_bins[ib]:.2f},{dS_bins[ib+1]:.2f}):  {n_cc_ds:>4}/{n_ds:<4}  ({100*n_cc_ds/n_ds:.1f}%)")

print()
print("Done.")

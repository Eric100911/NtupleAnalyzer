#!/usr/bin/env python3
"""Classify all GEN+RECO events: diagonal vs off-diagonal, with/without gen-matched phi.

Event classification categories:
  - Diagonal:   gen phi pT bin == reco phi pT bin
  - Off-diagonal, same-phi migration:   gen phi matches the reco best phi AND it is
    the GEN-best phi, but pT migrated to a different bin
  - Off-diagonal, wrong-phi selection:  reco best phi traces to a DIFFERENT gen phi
    (not the GEN-best one)
  - Off-diagonal, no gen-match:         reco phi kaons do not trace back to any gen phi

Show full candidate details for the gen-matched off-diagonal subset.
"""
from __future__ import annotations

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

g_pt  = f["MC_GenPart_pt"].array()
g_pdg = f["MC_GenPart_pdgId"].array()
g_mom = f["MC_GenPart_motherGenIdx"].array()
g_idx = ak.local_index(g_pt)

jpsi1_pt = f["Jpsi_1_pt"].array(); jpsi2_pt = f["Jpsi_2_pt"].array(); phi_pt = f["Phi_pt"].array()
jpsi1_mass  = f["Jpsi_1_mass"].array(); jpsi2_mass = f["Jpsi_2_mass"].array(); phi_mass  = f["Phi_mass"].array()
jpsi1_px = f["Jpsi_1_px"].array(); jpsi1_py = f["Jpsi_1_py"].array(); jpsi1_pz = f["Jpsi_1_pz"].array()
jpsi2_px = f["Jpsi_2_px"].array(); jpsi2_py = f["Jpsi_2_py"].array(); jpsi2_pz = f["Jpsi_2_pz"].array()
jpsi1_vtx_prob = f["Jpsi_1_VtxProb"].array(); jpsi2_vtx_prob = f["Jpsi_2_VtxProb"].array()
jpsi1_mu1_idx = f["Jpsi_1_mu_1_Idx"].array(); jpsi1_mu2_idx = f["Jpsi_1_mu_2_Idx"].array()
jpsi2_mu1_idx = f["Jpsi_2_mu_1_Idx"].array(); jpsi2_mu2_idx = f["Jpsi_2_mu_2_Idx"].array()

mu_gmidx = f["muGenMatchIdx"].array(); mu_gmsrc = f["muGenMatchSource"].array()
pk1_gm = f["Phi_K_1_genMatchIdx"].array(); pk1_src = f["Phi_K_1_genMatchSource"].array()
pk2_gm = f["Phi_K_2_genMatchIdx"].array(); pk2_src = f["Phi_K_2_genMatchSource"].array()

# ── GEN best system ──
is_mu = abs(g_pdg) == 13; is_ka = abs(g_pdg) == 321
n_mu_d   = ak.sum(g_mom[is_mu][:, :, None]  == g_idx[:, None, :], axis=1)
n_kaon_d = ak.sum(g_mom[is_ka][:, :, None]  == g_idx[:, None, :], axis=1)
vj = (abs(g_pdg) == 443) & (n_mu_d >= 2) & (g_pt > 6.0)
vp = (abs(g_pdg) == 333) & (n_kaon_d >= 2) & (g_pt > 4.0)
jo = ak.argsort(g_pt[vj], ascending=False); po = ak.argsort(g_pt[vp], ascending=False)
p_idx_s = g_idx[vp][po]; p_pt_s = g_pt[vp][po]
gen_p_idx = ak.fill_none(ak.pad_none(p_idx_s, 1, axis=1)[:, 0], -1)
gen_p_pt  = ak.fill_none(ak.pad_none(p_pt_s, 1, axis=1)[:, 0], np.nan)
j_idx_s = g_idx[vj][jo]; j_pt_s = g_pt[vj][jo]
gen_jpsi1_idx = ak.fill_none(ak.pad_none(j_idx_s, 1, axis=1)[:, 0], -1)
gen_jpsi2_idx = ak.fill_none(ak.pad_none(j_idx_s, 2, axis=1)[:, 1], -1)
has_full_gen = (ak.num(g_idx[vj][jo], axis=1) >= 2) & (ak.num(g_idx[vp][po], axis=1) >= 1)
n_phi = ak.num(g_idx[vp][po], axis=1)

# ── RECO best candidate ──
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

# ── Per-event classification ──
mask = has_full_gen & has_reco
evt_idx = ak.to_numpy(ak.where(mask)[0])
n_evt = len(evt_idx)

g_pdg_m = g_pdg[mask]; g_mom_m = g_mom[mask]
jpsi1_pt_masked = jpsi1_pt[mask]; jpsi2_pt_masked = jpsi2_pt[mask]; phi_pt_masked = phi_pt[mask]
jpsi1_mass_masked = jpsi1_mass[mask]; jpsi2_mass_masked = jpsi2_mass[mask]; phi_mass_masked = phi_mass[mask]
jpsi1_vtx_prob_masked = jpsi1_vtx_prob[mask]; jpsi2_vtx_prob_masked = jpsi2_vtx_prob[mask]
jpsi1_mu1_idx_masked = jpsi1_mu1_idx[mask]; jpsi1_mu2_idx_masked = jpsi1_mu2_idx[mask]
jpsi2_mu1_idx_masked = jpsi2_mu1_idx[mask]; jpsi2_mu2_idx_masked = jpsi2_mu2_idx[mask]
mu_gmidx_m = mu_gmidx[mask]; mu_gmsrc_m = mu_gmsrc[mask]
pk1_gm_m = pk1_gm[mask]; pk1_src_m = pk1_src[mask]
pk2_gm_m = pk2_gm[mask]; pk2_src_m = pk2_src[mask]
quality_masked = quality[mask]; score_masked = score[mask]

gen_p_idx_np = ak.to_numpy(gen_p_idx[mask])
gen_p_pt_np  = ak.to_numpy(gen_p_pt[mask])
gen_jpsi1_idx_np = ak.to_numpy(gen_jpsi1_idx[mask])
gen_jpsi2_idx_np = ak.to_numpy(gen_jpsi2_idx[mask])
best_idx_np  = ak.to_numpy(best_idx[mask])
n_phi_np = ak.to_numpy(n_phi[mask])

# phi pT bin edges used for the response matrix classification
phi_pt_bins = np.array([4.0, 6.0, 10.0, 20.0, 50.0], dtype=np.float64)
n_bins = len(phi_pt_bins) - 1
bin_labels = [f"[{phi_pt_bins[i]:.0f},{phi_pt_bins[i+1]:.0f})" for i in range(n_bins)]


def first_ancestor(pdg_list, mother_list, start_idx, target_abs_pdg, max_depth=16):
    """Walk up the GEN mother chain from start_idx looking for a particle with
    the given target_abs_pdg PDG code.  Returns the index of the ancestor, or -1."""
    idx = int(start_idx)
    for _ in range(max_depth):
        if idx < 0 or idx >= len(pdg_list): return -1
        if abs(int(pdg_list[idx])) == target_abs_pdg: return idx
        idx = int(mother_list[idx])
    return -1


events = []  # list of dicts for each event
for evt_idx in range(n_evt):
    bi = int(best_idx_np[evt_idx])
    orig = int(evt_idx[evt_idx])
    g_p_idx = int(gen_p_idx_np[evt_idx])
    g_p_pt = gen_p_pt_np[evt_idx]
    r_p_pt = float(phi_pt_masked[evt_idx][bi])

    # Digitize gen and reco phi pT into bins to determine response category
    gen_bin_idx = np.digitize(g_p_pt, phi_pt_bins) - 1
    reco_bin_idx = np.digitize(r_p_pt, phi_pt_bins) - 1
    is_diag = (0 <= gen_bin_idx < n_bins and 0 <= reco_bin_idx < n_bins and gen_bin_idx == reco_bin_idx)
    is_offdiag = (0 <= gen_bin_idx < n_bins and 0 <= reco_bin_idx < n_bins and gen_bin_idx != reco_bin_idx)

    # φ gen-matching: trace reconstructed kaon gen-match indices up the
    # mother chain to find a φ (PDG 333) ancestor.
    pk1_gm_val = int(pk1_gm_m[evt_idx][bi]); pk1_src_val = int(pk1_src_m[evt_idx][bi])
    pk2_gm_val = int(pk2_gm_m[evt_idx][bi]); pk2_src_val = int(pk2_src_m[evt_idx][bi])
    g_pdg_k = ak.to_numpy(g_pdg_m[evt_idx])
    g_mom_k = ak.to_numpy(g_mom_m[evt_idx])
    p_a1 = first_ancestor(g_pdg_k, g_mom_k, pk1_gm_val, 333) if pk1_src_val == 1 else -1
    p_a2 = first_ancestor(g_pdg_k, g_mom_k, pk2_gm_val, 333) if pk2_src_val == 1 else -1
    phi_leg = p_a1 if (p_a1 >= 0 and p_a1 == p_a2) else -1
    phi_matched = (phi_leg >= 0)
    same_best_phi = (phi_leg == g_p_idx)
    wrong_phi = (phi_leg >= 0 and phi_leg != g_p_idx)

    events.append({
        "k": evt_idx, "orig": orig, "bi": bi,
        "g_p_idx": g_p_idx, "g_p_pt": g_p_pt, "r_p_pt": r_p_pt,
        "ig": gen_bin_idx, "jr": reco_bin_idx, "is_diag": is_diag, "is_offdiag": is_offdiag,
        "phi_leg": phi_leg, "phi_matched": phi_matched,
        "same_best_phi": same_best_phi, "wrong_phi": wrong_phi,
        "n_p": int(n_phi_np[evt_idx]), "n_cand_all": len(jpsi1_pt_masked[evt_idx]),
        "n_cand_q": int(np.sum(ak.to_numpy(quality_masked[evt_idx]))),
    })

# ── Print classification ──
n_diag = sum(1 for e in events if e["is_diag"])
n_off_same_phi = sum(1 for e in events if e["is_offdiag"] and e["same_best_phi"])
n_off_wrong_phi = sum(1 for e in events if e["is_offdiag"] and e["wrong_phi"])
n_off_nomatch = sum(1 for e in events if e["is_offdiag"] and not e["phi_matched"])
n_other = n_evt - n_diag - n_off_same_phi - n_off_wrong_phi - n_off_nomatch

print()
print("=" * 70)
print("RESPONSE MATRIX CLASSIFICATION")
print("=" * 70)
print(f"  All events with GEN+RECO:               {n_evt:>5}")
print(f"  Diagonal (gen bin == reco bin):         {n_diag:>5}  ({100*n_diag/n_evt:.1f}%)")
print(f"  Off-diag, same GEN-best φ:              {n_off_same_phi:>5}  ({100*n_off_same_phi/n_evt:.1f}%)  ← same-φ migration")
print(f"  Off-diag, other GEN φ:                  {n_off_wrong_phi:>5}  ({100*n_off_wrong_phi/n_evt:.1f}%)  ← WRONG φ SELECTION")
print(f"  Off-diag, φ NOT gen-matched:            {n_off_nomatch:>5}  ({100*n_off_nomatch/n_evt:.1f}%)  ← reco failure")
if n_other > 0:
    print(f"  Other (out of bin range):               {n_other:>5}")
print()

# ── Off-diagonal events with a traced GEN φ: full details ──
off_traced = [e for e in events if e["is_offdiag"] and e["phi_matched"]]
if not off_traced:
    print("No off-diagonal events with a traced GEN φ found.")
else:
    print(f"  ── Details for {len(off_traced)} off-diagonal event(s) with a traced GEN φ ──")
    for ev in off_traced:
        evt_idx_v = ev["k"]; bi = ev["bi"]; orig = ev["orig"]
        category = "WRONG φ SELECTION" if ev["wrong_phi"] else "same-φ migration"
        print()
        print("=" * 80)
        print(f"  Category: {category}")
        print(f"  Event {orig}:  GEN φ pT={ev['g_p_pt']:.1f} ({bin_labels[ev['ig']]})"
              f"  →  RECO φ pT={ev['r_p_pt']:.1f} ({bin_labels[ev['jr']]})")
        print(f"  GEN best φ idx={ev['g_p_idx']}   reco φ trace → gen idx={ev['phi_leg']}"
              f"   n_φ^gen={ev['n_p']}")
        print()

        # All GEN φ
        n_p_evt = int(ak.num(g_pt[vp][po][orig], axis=0))
        print(f"  ── GEN φ (pT>4, ≥2 kaon daus): {n_p_evt} ──")
        p_pt_all = ak.to_numpy(g_pt[vp][po][orig])
        p_idx_all = ak.to_numpy(g_idx[vp][po][orig])
        for ip in range(n_p_evt):
            markers = []
            if p_idx_all[ip] == ev["g_p_idx"]: markers.append("GEN BEST")
            if p_idx_all[ip] == ev["phi_leg"]: markers.append("RECO φ traces here")
            tag = " ← " + ", ".join(markers) if markers else ""
            print(f"    φ[{ip}]: idx={p_idx_all[ip]}  pT={p_pt_all[ip]:.1f}{tag}")

        # All GEN J/ψ
        n_j_evt = int(ak.num(g_pt[vj][jo][orig], axis=0))
        j_pt_all = ak.to_numpy(g_pt[vj][jo][orig])
        j_idx_all = ak.to_numpy(g_idx[vj][jo][orig])
        print(f"  ── GEN J/ψ (pT>6, ≥2 muon daus): {n_j_evt} ──")
        for ij in range(min(n_j_evt, 3)):
            role = "J/ψ1" if ij == 0 else ("J/ψ2" if ij == 1 else "")
            gen_best_jpsi1_idx = int(gen_jpsi1_idx_np[evt_idx_v]); gen_best_jpsi2_idx = int(gen_jpsi2_idx_np[evt_idx_v])
            markers = []
            if ij == 0: markers.append(gen_best_jpsi1_idx if gen_best_jpsi1_idx >= 0 else "?")
            elif ij == 1: markers.append(gen_best_jpsi2_idx if gen_best_jpsi2_idx >= 0 else "?")
            print(f"    J/ψ[{ij}]: idx={j_idx_all[ij]}  pT={j_pt_all[ij]:.1f}  ({markers[0] if markers else ''})")
        if n_j_evt > 3:
            print(f"    ... and {n_j_evt-3} more")

        # All RECO candidates
        n_cand_all = ev["n_cand_all"]
        n_cand_q = ev["n_cand_q"]
        print(f"\n  ── RECO candidates: {n_cand_all} total, {n_cand_q} pass quality ──")
        for ic in range(n_cand_all):
            q = "✓" if bool(quality_masked[evt_idx_v][ic]) else "✗"
            s = float(score_masked[evt_idx_v][ic])
            star = " ← BEST" if ic == bi else ""
            jpsi1_pt_val = float(jpsi1_pt_masked[evt_idx_v][ic]); jpsi2_pt_val = float(jpsi2_pt_masked[evt_idx_v][ic]); phi_pt_val = float(phi_pt_masked[evt_idx_v][ic])
            j1m_val = float(jpsi1_mass_masked[evt_idx_v][ic]); j2m_val = float(jpsi2_mass_masked[evt_idx_v][ic]); pm_val = float(phi_mass_masked[evt_idx_v][ic])
            j1px = float(jpsi1_px[orig][ic]); j1py = float(jpsi1_py[orig][ic]); j1pz = float(jpsi1_pz[orig][ic])
            j2px = float(jpsi2_px[orig][ic]); j2py = float(jpsi2_py[orig][ic]); j2pz = float(jpsi2_pz[orig][ic])
            j1e_val = np.sqrt(j1px**2 + j1py**2 + j1pz**2 + j1m_val**2)
            j2e_val = np.sqrt(j2px**2 + j2py**2 + j2pz**2 + j2m_val**2)
            j1y = 0.5 * np.log((j1e_val + j1pz) / (j1e_val - j1pz + 1e-30))
            j2y = 0.5 * np.log((j2e_val + j2pz) / (j2e_val - j2pz + 1e-30))
            pk1_gm_ic = int(pk1_gm_m[evt_idx_v][ic]); pk1_src_ic = int(pk1_src_m[evt_idx_v][ic])
            pk2_gm_ic = int(pk2_gm_m[evt_idx_v][ic]); pk2_src_ic = int(pk2_src_m[evt_idx_v][ic])

            print(f"    cand[{ic}] {q} S={s:.0f}{star}")
            print(f"      J/ψ1: pT={jpsi1_pt_val:.1f}  y={j1y:+.2f}  m={j1m_val:.3f}  VtxProb={float(jpsi1_vtx_prob_masked[evt_idx_v][ic]):.3f}")
            print(f"      J/ψ2: pT={jpsi2_pt_val:.1f}  y={j2y:+.2f}  m={j2m_val:.3f}  VtxProb={float(jpsi2_vtx_prob_masked[evt_idx_v][ic]):.3f}")
            print(f"      φ:    pT={phi_pt_val:.1f}  m={pm_val:.3f}  K1_gm={pk1_gm_ic}(s{pk1_src_ic})  K2_gm={pk2_gm_ic}(s{pk2_src_ic})")
            jpsi1_mu1_idx = int(jpsi1_mu1_idx_masked[evt_idx_v][ic]); jpsi1_mu2_idx = int(jpsi1_mu2_idx_masked[evt_idx_v][ic])
            jpsi2_mu1_idx = int(jpsi2_mu1_idx_masked[evt_idx_v][ic]); jpsi2_mu2_idx = int(jpsi2_mu2_idx_masked[evt_idx_v][ic])
            if jpsi1_mu1_idx >= 0:
                gm1 = int(mu_gmidx_m[evt_idx_v][jpsi1_mu1_idx]); gs1 = int(mu_gmsrc_m[evt_idx_v][jpsi1_mu1_idx])
                gm2 = int(mu_gmidx_m[evt_idx_v][jpsi1_mu2_idx]); gs2 = int(mu_gmsrc_m[evt_idx_v][jpsi1_mu2_idx])
                gm3 = int(mu_gmidx_m[evt_idx_v][jpsi2_mu1_idx]); gs3 = int(mu_gmsrc_m[evt_idx_v][jpsi2_mu1_idx])
                gm4 = int(mu_gmidx_m[evt_idx_v][jpsi2_mu2_idx]); gs4 = int(mu_gmsrc_m[evt_idx_v][jpsi2_mu2_idx])
                print(f"      μ gm: J1μ1={gm1}(s{gs1}) J1μ2={gm2}(s{gs2}) J2μ1={gm3}(s{gs3}) J2μ2={gm4}(s{gs4})")
            print()

print("Done.")

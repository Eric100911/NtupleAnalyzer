#!/usr/bin/env python3
"""GEN-level JJP decay angles from MC_GenPart_* branches.

Particle selection (verified by inspecting the ntuples):
  * final J/psi: pdgId == 443, status == 2; take the two highest-pT ones;
  * phi:         pdgId == 333, status == 2;
  * daughters:   motherGenIdx points at the parent index (K: +-321, mu: +-13).

Angles use the same definitions as compute_angles.py:
  cos_theta_jpsi{1,2}: in each J/psi rest frame, the angle between mu+ and
      the direction opposite the other J/psi (the recoil system);
  cos_theta_phi: in the phi rest frame, the angle between K+ and the
      direction opposite the two-J/psi recoil system;
  delta_phi_jj: angle between the J/psi decay planes in the two-J/psi frame.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

MU_MASS = 0.1056583755
K_MASS = 0.493677

GEN_BRANCHES = [
    "MC_GenPart_pdgId", "MC_GenPart_status", "MC_GenPart_motherGenIdx",
    "MC_GenPart_px", "MC_GenPart_py", "MC_GenPart_pz", "MC_GenPart_mass",
]


def four_momentum(px, py, pz, mass):
    e = np.sqrt(px * px + py * py + pz * pz + mass * mass)
    return e, px, py, pz


def boost_into_rest(e, px, py, pz, es, pxs, pys, pzs):
    ps2 = pxs * pxs + pys * pys + pzs * pzs
    ms2 = max(es * es - ps2, 1e-12)
    gamma = es / np.sqrt(ms2)
    bp = pxs * px + pys * py + pzs * pz
    par = bp / ps2 if ps2 > 1e-12 else 0.0
    par_x, par_y, par_z = par * pxs, par * pys, par * pzs
    e_new = gamma * (e - bp / es)
    par_new_x = gamma * (par_x - pxs * e / es)
    par_new_y = gamma * (par_y - pys * e / es)
    par_new_z = gamma * (par_z - pzs * e / es)
    return e_new, px - par_x + par_new_x, py - par_y + par_new_y, pz - par_z + par_new_z


def angle_between(ax, ay, az, bx, by, bz):
    na = np.sqrt(ax * ax + ay * ay + az * az)
    nb = np.sqrt(bx * bx + by * by + bz * bz)
    if na < 1e-12 or nb < 1e-12:
        return np.nan
    return float(np.clip((ax * bx + ay * by + az * bz) / (na * nb), -1.0, 1.0))


def cross(ax, ay, az, bx, by, bz):
    return ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx


def rapidity(e, pz):
    if abs(e - pz) < 1e-12:
        return np.nan
    return 0.5 * np.log((e + pz) / (e - pz))


def compute(input_path: str, reader: str = "root", max_events: int | None = None):
    if reader == "root":
        from root_io import RootTreeArrays

        with RootTreeArrays(input_path, "selected") as tree:
            arr = tree.arrays(GEN_BRANCHES, library="np", entry_stop=max_events)
    elif reader == "uproot":
        import uproot

        tree = uproot.open(input_path)["selected"]
        entry_stop = {} if max_events is None else {"entry_stop": max_events}
        arr = tree.arrays(GEN_BRANCHES, library="np", **entry_stop)
    else:
        raise ValueError(f"Unsupported reader {reader!r}; choose 'root' or 'uproot'")
    n = len(arr["MC_GenPart_pdgId"])
    out = {k: np.full(n, np.nan) for k in [
        "gen_cos_theta_jpsi1", "gen_cos_theta_jpsi2",
        "gen_cos_theta_phi_k1", "gen_abs_cos_theta_phi", "gen_delta_phi_jj",
        "gen_phi_pt", "gen_phi_y", "gen_phi_eta",
        "gen_jpsi1_pt", "gen_jpsi1_y",
        "gen_jpsi2_pt", "gen_jpsi2_y",
        # Kaon kinematics of the phi daughters (leading-pT kaon first).
        "gen_k_lead_pt", "gen_k_sublead_pt",
        "gen_k_lead_eta", "gen_k_sublead_eta",
        "gen_k_lead_phi", "gen_k_sublead_phi",
        "gen_deta_kk", "gen_dphi_kk", "gen_deltaR_kk",
    ]}
    flags = {
        "no_phi": 0, "no_two_jpsi": 0, "no_phi_daughters": 0,
        "no_muons": 0, "same_charge_jpsi": 0, "degenerate_plane": 0,
    }

    for i in range(n):
        pdg = arr["MC_GenPart_pdgId"][i]
        status = arr["MC_GenPart_status"][i]
        mother = arr["MC_GenPart_motherGenIdx"][i]
        px = arr["MC_GenPart_px"][i]
        py = arr["MC_GenPart_py"][i]
        pz = arr["MC_GenPart_pz"][i]
        mass = arr["MC_GenPart_mass"][i]
        npart = len(pdg)

        # phi candidates
        phi_idx = [j for j in range(npart) if pdg[j] == 333 and status[j] == 2]
        if not phi_idx:
            flags["no_phi"] += 1
            continue
        # Prefer the highest-pT phi that has both K daughters in the array.
        # (Soft forward phi mesons from the underlying event can appear earlier
        # in the GEN record; picking by record order would bias the angle.)
        phi_sel = None
        k_plus = k_minus = None
        best_pt = -1.0
        for j in phi_idx:
            kp = [k for k in range(npart) if pdg[k] == 321 and mother[k] == j and status[k] == 1]
            km = [k for k in range(npart) if pdg[k] == -321 and mother[k] == j and status[k] == 1]
            if kp and km:
                pt2 = px[j] ** 2 + py[j] ** 2
                if pt2 > best_pt:
                    best_pt = pt2
                    phi_sel = j
                    k_plus, k_minus = kp[0], km[0]
        if phi_sel is None:
            flags["no_phi_daughters"] += 1
            continue

        # Two highest-pT final J/psi
        jpsi_idx = [j for j in range(npart) if pdg[j] == 443 and status[j] == 2]
        if len(jpsi_idx) < 2:
            flags["no_two_jpsi"] += 1
            continue
        jpsi_idx = sorted(jpsi_idx, key=lambda j: -(px[j] ** 2 + py[j] ** 2))[:2]
        a, b = jpsi_idx
        j1 = four_momentum(px[a], py[a], pz[a], mass[a])
        j2 = four_momentum(px[b], py[b], pz[b], mass[b])
        phi4 = four_momentum(px[phi_sel], py[phi_sel], pz[phi_sel], mass[phi_sel])
        kp4 = four_momentum(px[k_plus], py[k_plus], pz[k_plus], mass[k_plus])
        km4 = four_momentum(px[k_minus], py[k_minus], pz[k_minus], mass[k_minus])

        out["gen_phi_pt"][i] = np.hypot(phi4[1], phi4[2])
        out["gen_phi_y"][i] = rapidity(phi4[0], phi4[3])
        phi_p = np.sqrt(phi4[1] ** 2 + phi4[2] ** 2 + phi4[3] ** 2)
        out["gen_phi_eta"][i] = 0.5 * np.log((phi_p + phi4[3]) / (phi_p - phi4[3]))
        if not np.isfinite(out["gen_phi_eta"][i]):
            out["gen_phi_eta"][i] = np.nan
        out["gen_jpsi1_pt"][i] = np.hypot(j1[1], j1[2])
        out["gen_jpsi1_y"][i] = rapidity(j1[0], j1[3])
        out["gen_jpsi2_pt"][i] = np.hypot(j2[1], j2[2])
        out["gen_jpsi2_y"][i] = rapidity(j2[0], j2[3])

        # Kaon kinematics: order by pT, compute lab-frame separation.
        k1_pt = np.hypot(kp4[1], kp4[2])
        k2_pt = np.hypot(km4[1], km4[2])
        k1_p = np.sqrt(kp4[1] ** 2 + kp4[2] ** 2 + kp4[3] ** 2)
        k2_p = np.sqrt(km4[1] ** 2 + km4[2] ** 2 + km4[3] ** 2)
        k1_eta = 0.5 * np.log((k1_p + kp4[3]) / (k1_p - kp4[3]))
        k2_eta = 0.5 * np.log((k2_p + km4[3]) / (k2_p - km4[3]))
        if not np.isfinite(k1_eta):
            k1_eta = np.nan
        if not np.isfinite(k2_eta):
            k2_eta = np.nan
        k1_phi = np.arctan2(kp4[2], kp4[1])
        k2_phi = np.arctan2(km4[2], km4[1])
        if k1_pt >= k2_pt:
            lead = (k1_pt, k1_eta, k1_phi)
            sub = (k2_pt, k2_eta, k2_phi)
        else:
            lead = (k2_pt, k2_eta, k2_phi)
            sub = (k1_pt, k1_eta, k1_phi)
        dphi = np.abs(lead[2] - sub[2])
        dphi = min(dphi, 2.0 * np.pi - dphi)
        deta = lead[1] - sub[1]
        out["gen_k_lead_pt"][i] = lead[0]
        out["gen_k_sublead_pt"][i] = sub[0]
        out["gen_k_lead_eta"][i] = lead[1]
        out["gen_k_sublead_eta"][i] = sub[1]
        out["gen_k_lead_phi"][i] = lead[2]
        out["gen_k_sublead_phi"][i] = sub[2]
        out["gen_deta_kk"][i] = deta
        out["gen_dphi_kk"][i] = dphi
        out["gen_deltaR_kk"][i] = np.hypot(deta, dphi)

        s4 = (j1[0] + j2[0], j1[1] + j2[1], j1[2] + j2[2], j1[3] + j2[3])
        # muons from each J/psi
        mu_a = [k for k in range(npart) if abs(pdg[k]) == 13 and mother[k] == a and status[k] == 1]
        mu_b = [k for k in range(npart) if abs(pdg[k]) == 13 and mother[k] == b and status[k] == 1]
        if len(mu_a) < 2 or len(mu_b) < 2:
            flags["no_muons"] += 1
            continue
        plus_a = [k for k in mu_a if pdg[k] == -13]
        minus_a = [k for k in mu_a if pdg[k] == 13]
        plus_b = [k for k in mu_b if pdg[k] == -13]
        minus_b = [k for k in mu_b if pdg[k] == 13]
        if not plus_a or not minus_a or not plus_b or not minus_b:
            flags["same_charge_jpsi"] += 1
            continue
        pa = four_momentum(px[plus_a[0]], py[plus_a[0]], pz[plus_a[0]], mass[plus_a[0]])
        ma = four_momentum(px[minus_a[0]], py[minus_a[0]], pz[minus_a[0]], mass[minus_a[0]])
        pb = four_momentum(px[plus_b[0]], py[plus_b[0]], pz[plus_b[0]], mass[plus_b[0]])
        mb = four_momentum(px[minus_b[0]], py[minus_b[0]], pz[minus_b[0]], mass[minus_b[0]])

        # Helicity angles: daughter and recoil are both boosted directly into
        # the same resonance rest frame; cos(theta) = -p_d* . p_recoil* / (...).
        pa_rest = boost_into_rest(*pa, *j1)
        pb_rest = boost_into_rest(*pb, *j2)
        j2_j1_rest = boost_into_rest(*j2, *j1)
        j1_j2_rest = boost_into_rest(*j1, *j2)
        out["gen_cos_theta_jpsi1"][i] = angle_between(
            pa_rest[1], pa_rest[2], pa_rest[3],
            -j2_j1_rest[1], -j2_j1_rest[2], -j2_j1_rest[3],
        )
        out["gen_cos_theta_jpsi2"][i] = angle_between(
            pb_rest[1], pb_rest[2], pb_rest[3],
            -j1_j2_rest[1], -j1_j2_rest[2], -j1_j2_rest[3],
        )

        kp_rest = boost_into_rest(*kp4, *phi4)
        s4_phi_rest = boost_into_rest(*s4, *phi4)
        cphi = angle_between(
            kp_rest[1], kp_rest[2], kp_rest[3],
            -s4_phi_rest[1], -s4_phi_rest[2], -s4_phi_rest[3],
        )
        out["gen_cos_theta_phi_k1"][i] = cphi
        out["gen_abs_cos_theta_phi"][i] = abs(cphi)

        pa_s4 = boost_into_rest(*pa, *s4)
        ma_s4 = boost_into_rest(*ma, *s4)
        pb_s4 = boost_into_rest(*pb, *s4)
        mb_s4 = boost_into_rest(*mb, *s4)
        n1 = cross(pa_s4[1], pa_s4[2], pa_s4[3], ma_s4[1], ma_s4[2], ma_s4[3])
        n2 = cross(pb_s4[1], pb_s4[2], pb_s4[3], mb_s4[1], mb_s4[2], mb_s4[3])
        nn1 = np.sqrt(sum(v * v for v in n1))
        nn2 = np.sqrt(sum(v * v for v in n2))
        if nn1 < 1e-9 or nn2 < 1e-9:
            flags["degenerate_plane"] += 1
        else:
            cosd = sum(x * y for x, y in zip(n1, n2)) / (nn1 * nn2)
            out["gen_delta_phi_jj"][i] = np.arccos(np.clip(cosd, -1.0, 1.0))

    result = {"n_events": n, "input": input_path, "flags": flags}
    return result, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--reader", choices=["root", "uproot"], default="root")
    ap.add_argument("--max-events", type=int, default=None)
    args = ap.parse_args()

    import pandas as pd

    result, out = compute(args.input, reader=args.reader, max_events=args.max_events)
    frame = pd.DataFrame(out)
    result["label"] = args.label
    result["moments"] = {}
    for name in ["gen_cos_theta_jpsi1", "gen_cos_theta_jpsi2",
                 "gen_abs_cos_theta_phi", "gen_delta_phi_jj"]:
        v = frame[name].to_numpy()
        v = v[np.isfinite(v)]
        if len(v):
            result["moments"][name] = {
                "n": int(len(v)), "mean": float(np.mean(v)), "std": float(np.std(v)),
            }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.output, index=False)
    with open(args.output.replace(".parquet", "_meta.json"), "w") as fh:
        json.dump(result, fh, indent=1)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()

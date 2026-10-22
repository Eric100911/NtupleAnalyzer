#!/usr/bin/env python3
"""Compute J/psi and phi decay angles for JJP selected events.

Angular variables (all per event, using the best-candidate sel_* branches):

  cos_theta_jpsi1 : helicity angle of J/psi_1 -> mu+ mu-.
      In the J/psi_1 rest frame, the angle is between the mu+ momentum and
      the direction opposite J/psi_2 (the recoil system).
  cos_theta_jpsi2 : same for J/psi_2.
  cos_theta_phi_k1 / abs_cos_theta_phi :
      In the phi rest frame, the angle is between K_1 (leading-pT kaon)
      and the direction opposite the 4mu recoil system.
      The selected ntuples do not store the kaon charge, so the K_1 sign is
      arbitrary; abs_cos_theta_phi is the charge-averaged (folded) variable.
  delta_phi_jj : unsigned angle between the J/psi_1 and J/psi_2 decay planes,
      evaluated in the 4mu rest frame, in [0, pi].

The script only reads the ntuples; it does not fit or modify anything.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

MU_MASS = 0.1056583755
K_MASS = 0.493677

SCALARS = [
    "sel_Jpsi_1_mass", "sel_Jpsi_2_mass", "sel_Phi_mass",
    "sel_Jpsi_1_pt", "sel_Jpsi_2_pt", "sel_Phi_pt",
    "sel_Jpsi_1_mu_1_Idx", "sel_Jpsi_1_mu_2_Idx",
    "sel_Jpsi_2_mu_1_Idx", "sel_Jpsi_2_mu_2_Idx",
    "sel_Phi_K_1_px", "sel_Phi_K_1_py", "sel_Phi_K_1_pz",
    "sel_Phi_K_2_px", "sel_Phi_K_2_py", "sel_Phi_K_2_pz",
    "sel_Phi_K_1_pt", "sel_Phi_K_2_pt",
]
JAGGED = ["muPx", "muPy", "muPz", "muCharge"]


def four_momentum(px, py, pz, mass):
    """Return (E, px, py, pz) with E = sqrt(p^2 + m^2)."""
    px = np.asarray(px, dtype=float)
    py = np.asarray(py, dtype=float)
    pz = np.asarray(pz, dtype=float)
    e = np.sqrt(px * px + py * py + pz * pz + mass * mass)
    return e, px, py, pz


def boost_into_rest(e, px, py, pz, es, pxs, pys, pzs):
    """Boost a four-vector (e, p) into the rest frame of system (es, ps).

    Standard Lorentz boost with beta = ps / es.  Returns (e', px', py', pz').
    """
    ps2 = pxs * pxs + pys * pys + pzs * pzs
    ms2 = np.maximum(es * es - ps2, 1e-12)
    gamma = es / np.sqrt(ms2)
    bp = pxs * px + pys * py + pzs * pz
    with np.errstate(divide="ignore", invalid="ignore"):
        par = np.where(ps2 > 1e-12, bp / ps2, 0.0)
    par_x = par * pxs
    par_y = par * pys
    par_z = par * pzs
    e_new = gamma * (e - bp / es)
    par_new_x = gamma * (par_x - pxs * e / es)
    par_new_y = gamma * (par_y - pys * e / es)
    par_new_z = gamma * (par_z - pzs * e / es)
    return (
        e_new,
        px - par_x + par_new_x,
        py - par_y + par_new_y,
        pz - par_z + par_new_z,
    )


def angle_between(ax, ay, az, bx, by, bz):
    na = np.sqrt(ax * ax + ay * ay + az * az)
    nb = np.sqrt(bx * bx + by * by + bz * bz)
    with np.errstate(divide="ignore", invalid="ignore"):
        cos = (ax * bx + ay * by + az * bz) / (na * nb)
    return np.clip(cos, -1.0, 1.0)


def cross(ax, ay, az, bx, by, bz):
    return (
        ay * bz - az * by,
        az * bx - ax * bz,
        ax * by - ay * bx,
    )


def rapidity(e, pz):
    e = np.asarray(e, dtype=float)
    pz = np.asarray(pz, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 0.5 * np.log((e + pz) / (e - pz))


def compute(input_path: str, reader: str = "root", max_events: int | None = None) -> dict:
    if reader == "root":
        from root_io import RootTreeArrays

        with RootTreeArrays(input_path, "selected") as tree:
            scalar = tree.arrays(SCALARS, library="np", entry_stop=max_events)
            jagged = tree.arrays(JAGGED, library="np", entry_stop=max_events)
    elif reader == "uproot":
        import uproot

        tree = uproot.open(input_path)["selected"]
        entry_stop = {} if max_events is None else {"entry_stop": max_events}
        scalar = tree.arrays(SCALARS, library="np", **entry_stop)
        jagged = tree.arrays(JAGGED, library="np", **entry_stop)
    else:
        raise ValueError(f"Unsupported reader {reader!r}; choose 'root' or 'uproot'")
    n = len(scalar["sel_Jpsi_1_mass"])

    out = {k: np.full(n, np.nan) for k in [
        "cos_theta_jpsi1", "cos_theta_jpsi2",
        "cos_theta_phi_k1", "abs_cos_theta_phi", "delta_phi_jj",
        "m_jpsi1_daughters", "m_jpsi2_daughters", "m_phi_daughters",
        "y_jpsi1", "y_jpsi2", "y_phi",
    ]}
    out["jpsi1_mu_plus_charge"] = np.zeros(n, dtype=int)
    out["jpsi2_mu_plus_charge"] = np.zeros(n, dtype=int)
    # Keep the reconstructed masses and pT used by the 3D mass fit / reweighting.
    for key in [
        "sel_Jpsi_1_mass", "sel_Jpsi_2_mass", "sel_Phi_mass",
        "sel_Jpsi_1_pt", "sel_Jpsi_2_pt", "sel_Phi_pt",
    ]:
        out[key] = np.asarray(scalar[key], dtype=float)
    flags = {
        "bad_muon_index": 0,
        "same_charge_jpsi1": 0,
        "same_charge_jpsi2": 0,
        "degenerate_plane": 0,
    }

    for i in range(n):
        mu_px = jagged["muPx"][i]
        mu_py = jagged["muPy"][i]
        mu_pz = jagged["muPz"][i]
        mu_q = jagged["muCharge"][i]
        nmu = len(mu_px)

        idx = [
            int(scalar["sel_Jpsi_1_mu_1_Idx"][i]),
            int(scalar["sel_Jpsi_1_mu_2_Idx"][i]),
            int(scalar["sel_Jpsi_2_mu_1_Idx"][i]),
            int(scalar["sel_Jpsi_2_mu_2_Idx"][i]),
        ]
        if any(j < 0 or j >= nmu for j in idx):
            flags["bad_muon_index"] += 1
            continue

        # J/psi four-vectors from their daughter muons.
        e1a = np.sqrt(mu_px[idx[0]] ** 2 + mu_py[idx[0]] ** 2 + mu_pz[idx[0]] ** 2 + MU_MASS ** 2)
        e1b = np.sqrt(mu_px[idx[1]] ** 2 + mu_py[idx[1]] ** 2 + mu_pz[idx[1]] ** 2 + MU_MASS ** 2)
        e2a = np.sqrt(mu_px[idx[2]] ** 2 + mu_py[idx[2]] ** 2 + mu_pz[idx[2]] ** 2 + MU_MASS ** 2)
        e2b = np.sqrt(mu_px[idx[3]] ** 2 + mu_py[idx[3]] ** 2 + mu_pz[idx[3]] ** 2 + MU_MASS ** 2)
        j1 = (
            e1a + e1b,
            mu_px[idx[0]] + mu_px[idx[1]],
            mu_py[idx[0]] + mu_py[idx[1]],
            mu_pz[idx[0]] + mu_pz[idx[1]],
        )
        j2 = (
            e2a + e2b,
            mu_px[idx[2]] + mu_px[idx[3]],
            mu_py[idx[2]] + mu_py[idx[3]],
            mu_pz[idx[2]] + mu_pz[idx[3]],
        )

        out["m_jpsi1_daughters"][i] = np.sqrt(max(j1[0] ** 2 - j1[1] ** 2 - j1[2] ** 2 - j1[3] ** 2, 0.0))
        out["m_jpsi2_daughters"][i] = np.sqrt(max(j2[0] ** 2 - j2[1] ** 2 - j2[2] ** 2 - j2[3] ** 2, 0.0))
        out["y_jpsi1"][i] = rapidity(j1[0], j1[3])
        out["y_jpsi2"][i] = rapidity(j2[0], j2[3])

        # 4mu system = J/psi_1 + J/psi_2.
        s4 = (
            j1[0] + j2[0],
            j1[1] + j2[1],
            j1[2] + j2[2],
            j1[3] + j2[3],
        )

        # Select mu+ by charge; if both muons have the same charge, use mu_1.
        q1a, q1b = mu_q[idx[0]], mu_q[idx[1]]
        if q1a > 0 and q1b < 0:
            plus1, minus1 = idx[0], idx[1]
        elif q1b > 0 and q1a < 0:
            plus1, minus1 = idx[1], idx[0]
        else:
            plus1, minus1 = idx[0], idx[1]
            flags["same_charge_jpsi1"] += 1
        q2a, q2b = mu_q[idx[2]], mu_q[idx[3]]
        if q2a > 0 and q2b < 0:
            plus2, minus2 = idx[2], idx[3]
        elif q2b > 0 and q2a < 0:
            plus2, minus2 = idx[3], idx[2]
        else:
            plus2, minus2 = idx[2], idx[3]
            flags["same_charge_jpsi2"] += 1

        out["jpsi1_mu_plus_charge"][i] = int(1 if mu_q[plus1] > 0 else -1)
        out["jpsi2_mu_plus_charge"][i] = int(1 if mu_q[plus2] > 0 else -1)

        # Helicity angles: boost daughter and recoil directly into the same
        # resonance rest frame.  cos(theta) = -p_d* . p_recoil* / (|p_d*||p_recoil*|).
        # The minus sign gives the resonance flight axis in the parent rest frame.
        mp1 = four_momentum(mu_px[plus1], mu_py[plus1], mu_pz[plus1], MU_MASS)
        mp1_rest = boost_into_rest(mp1[0], mp1[1], mp1[2], mp1[3], j1[0], j1[1], j1[2], j1[3])
        j2_in_j1_rest = boost_into_rest(j2[0], j2[1], j2[2], j2[3], j1[0], j1[1], j1[2], j1[3])
        out["cos_theta_jpsi1"][i] = angle_between(
            mp1_rest[1], mp1_rest[2], mp1_rest[3],
            -j2_in_j1_rest[1], -j2_in_j1_rest[2], -j2_in_j1_rest[3],
        )

        mp2 = four_momentum(mu_px[plus2], mu_py[plus2], mu_pz[plus2], MU_MASS)
        mp2_rest = boost_into_rest(mp2[0], mp2[1], mp2[2], mp2[3], j2[0], j2[1], j2[2], j2[3])
        j1_in_j2_rest = boost_into_rest(j1[0], j1[1], j1[2], j1[3], j2[0], j2[1], j2[2], j2[3])
        out["cos_theta_jpsi2"][i] = angle_between(
            mp2_rest[1], mp2_rest[2], mp2_rest[3],
            -j1_in_j2_rest[1], -j1_in_j2_rest[2], -j1_in_j2_rest[3],
        )

        # phi -> K1 K2; K1 is the leading-pT kaon.
        k1 = four_momentum(
            scalar["sel_Phi_K_1_px"][i], scalar["sel_Phi_K_1_py"][i],
            scalar["sel_Phi_K_1_pz"][i], K_MASS,
        )
        k2 = four_momentum(
            scalar["sel_Phi_K_2_px"][i], scalar["sel_Phi_K_2_py"][i],
            scalar["sel_Phi_K_2_pz"][i], K_MASS,
        )
        phi4 = (
            k1[0] + k2[0],
            k1[1] + k2[1],
            k1[2] + k2[2],
            k1[3] + k2[3],
        )
        out["m_phi_daughters"][i] = np.sqrt(max(phi4[0] ** 2 - phi4[1] ** 2 - phi4[2] ** 2 - phi4[3] ** 2, 0.0))
        out["y_phi"][i] = rapidity(phi4[0], phi4[3])
        k1_rest = boost_into_rest(k1[0], k1[1], k1[2], k1[3], phi4[0], phi4[1], phi4[2], phi4[3])
        s4_in_phi_rest = boost_into_rest(s4[0], s4[1], s4[2], s4[3], phi4[0], phi4[1], phi4[2], phi4[3])
        cphi = angle_between(
            k1_rest[1], k1_rest[2], k1_rest[3],
            -s4_in_phi_rest[1], -s4_in_phi_rest[2], -s4_in_phi_rest[3],
        )
        out["cos_theta_phi_k1"][i] = cphi
        out["abs_cos_theta_phi"][i] = abs(cphi)

        # J/psi decay planes in the 4mu rest frame.
        mp1m = four_momentum(mu_px[minus1], mu_py[minus1], mu_pz[minus1], MU_MASS)
        mp2m = four_momentum(mu_px[minus2], mu_py[minus2], mu_pz[minus2], MU_MASS)
        pp1 = boost_into_rest(mp1[0], mp1[1], mp1[2], mp1[3], s4[0], s4[1], s4[2], s4[3])
        pm1 = boost_into_rest(mp1m[0], mp1m[1], mp1m[2], mp1m[3], s4[0], s4[1], s4[2], s4[3])
        pp2 = boost_into_rest(mp2[0], mp2[1], mp2[2], mp2[3], s4[0], s4[1], s4[2], s4[3])
        pm2 = boost_into_rest(mp2m[0], mp2m[1], mp2m[2], mp2m[3], s4[0], s4[1], s4[2], s4[3])
        n1 = cross(pp1[1], pp1[2], pp1[3], pm1[1], pm1[2], pm1[3])
        n2 = cross(pp2[1], pp2[2], pp2[3], pm2[1], pm2[2], pm2[3])
        nn1 = np.sqrt(n1[0] ** 2 + n1[1] ** 2 + n1[2] ** 2)
        nn2 = np.sqrt(n2[0] ** 2 + n2[1] ** 2 + n2[2] ** 2)
        if nn1 < 1e-9 or nn2 < 1e-9:
            flags["degenerate_plane"] += 1
        else:
            cosd = (n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2]) / (nn1 * nn2)
            out["delta_phi_jj"][i] = np.arccos(np.clip(cosd, -1.0, 1.0))

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
    for name in ["cos_theta_jpsi1", "cos_theta_jpsi2", "abs_cos_theta_phi", "delta_phi_jj"]:
        v = frame[name].to_numpy()
        v = v[np.isfinite(v)]
        if len(v):
            result["moments"][name] = {
                "n": int(len(v)),
                "mean": float(np.mean(v)),
                "std": float(np.std(v)),
                "q05": float(np.quantile(v, 0.05)),
                "q16": float(np.quantile(v, 0.16)),
                "median": float(np.median(v)),
                "q84": float(np.quantile(v, 0.84)),
                "q95": float(np.quantile(v, 0.95)),
            }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    try:
        frame.to_parquet(args.output, index=False)
    except Exception:
        frame.to_csv(args.output.replace(".parquet", ".csv"), index=False)
    meta_path = args.output.replace(".parquet", "_meta.json").replace(".csv", "_meta.json")
    with open(meta_path, "w") as fh:
        json.dump(result, fh, indent=1)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()

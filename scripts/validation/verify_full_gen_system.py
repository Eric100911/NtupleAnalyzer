#!/usr/bin/env python3
"""Bounded audit of final-best reconstructed JJP versus full workflow GEN system."""
import argparse
import json
import math
import time
from collections import Counter
from pathlib import Path

import ROOT
import pyarrow as pa
import pyarrow.parquet as pq

ROOT.gROOT.SetBatch(True)
OUT = Path("diagnostics/phi_ctau_20261022/inventory")
FILES = {
    "DPS1": Path("/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3/jjp_mc_dps_1_selected.root"),
    "DPS2_CS": Path("/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3/jjp_mc_dps_2_cs_selected.root"),
    "DPS2_G": Path("/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3/jjp_mc_dps_2_g_selected.root"),
    "SPS_CS": Path("/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3/jjp_mc_sps_cs_selected.root"),
    "SPS_G": Path("/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3/jjp_mc_sps_g_selected.root"),
}
BRANCHES = [
    "bestCandIdx", "Jpsi_1_mu_1_Idx", "Jpsi_1_mu_2_Idx", "Jpsi_2_mu_1_Idx", "Jpsi_2_mu_2_Idx",
    "muGenMatchIdx", "muGenMatchSource", "Phi_K_1_genMatchIdx", "Phi_K_2_genMatchIdx",
    "Phi_K_1_genMatchSource", "Phi_K_2_genMatchSource", "MC_GenPart_pdgId",
    "MC_GenPart_motherGenIdx", "MC_GenPart_motherPdgId", "MC_GenPart_pt", "MC_GenPart_eta", "MC_GenPart_mass",
]


def rap(pt, eta, mass):
    mt = math.hypot(pt, mass)
    pz = pt * math.sinh(eta)
    energy = math.hypot(mt, pz)
    if energy <= abs(pz):
        return math.nan
    return 0.5 * math.log((energy + pz) / (energy - pz))


def compute(tree, entry):
    tree.GetEntry(entry)
    pdg = list(tree.MC_GenPart_pdgId)
    mother = list(tree.MC_GenPart_motherGenIdx)
    mother_pdg = list(tree.MC_GenPart_motherPdgId)
    gpt = list(tree.MC_GenPart_pt)
    geta = list(tree.MC_GenPart_eta)
    gm = list(tree.MC_GenPart_mass)
    children = {}
    for i, mom in enumerate(mother):
        if 0 <= int(mom) < len(pdg):
            children.setdefault(int(mom), []).append(i)

    eligible_jpsi = []
    for i, pid in enumerate(pdg):
        if abs(int(pid)) != 443 or not (gpt[i] > 6.0 and abs(rap(gpt[i], geta[i], gm[i])) < 2.5):
            continue
        if sum(abs(int(pdg[k])) == 13 for k in children.get(i, [])) >= 2:
            eligible_jpsi.append(i)
    eligible_phi = []
    for i, pid in enumerate(pdg):
        if abs(int(pid)) != 333 or not (gpt[i] > 4.0 and abs(rap(gpt[i], geta[i], gm[i])) < 2.4):
            continue
        if sum(abs(int(pdg[k])) == 321 for k in children.get(i, [])) >= 2:
            eligible_phi.append(i)
    target_jpsi = sorted(eligible_jpsi, key=lambda i: gpt[i], reverse=True)[:2] if len(eligible_jpsi) >= 2 else []
    target_phi = max(eligible_phi, key=lambda i: gpt[i]) if target_jpsi and eligible_phi else -1

    best = int(tree.bestCandIdx)
    phi1 = int(tree.Phi_K_1_genMatchIdx[best]) if 0 <= best < len(tree.Phi_K_1_genMatchIdx) else -1
    phi2 = int(tree.Phi_K_2_genMatchIdx[best]) if 0 <= best < len(tree.Phi_K_2_genMatchIdx) else -1
    phi_src1 = int(tree.Phi_K_1_genMatchSource[best]) if 0 <= best < len(tree.Phi_K_1_genMatchSource) else -1
    phi_src2 = int(tree.Phi_K_2_genMatchSource[best]) if 0 <= best < len(tree.Phi_K_2_genMatchSource) else -1
    phi_mom1 = int(mother[phi1]) if 0 <= phi1 < len(mother) else -1
    phi_mom2 = int(mother[phi2]) if 0 <= phi2 < len(mother) else -1
    phi_parent = phi_mom1 if phi_mom1 == phi_mom2 and 0 <= phi_mom1 < len(pdg) and abs(int(pdg[phi_mom1])) == 333 and phi_src1 == 1 and phi_src2 == 1 else -1
    phi_proxy_match = phi_parent >= 0 and target_phi >= 0 and phi_parent == target_phi

    mu_match = list(tree.muGenMatchIdx)
    mu_source = list(tree.muGenMatchSource)

    def jpsi_parent(slot_mu1, slot_mu2):
        i1, i2 = int(slot_mu1[best]), int(slot_mu2[best])
        if min(i1, i2) < 0 or max(i1, i2) >= min(len(mu_match), len(mu_source)):
            return -1, "bad_reco_muon_index"
        indices = []
        for midx in (i1, i2):
            gidx = int(mu_match[midx])
            if int(mu_source[midx]) != 1 or gidx < 0 or gidx >= len(mother):
                return -1, "invalid_source1_muon_match"
            parent = int(mother[gidx])
            if parent < 0 or parent >= len(pdg) or abs(int(mother_pdg[gidx])) != 443 or abs(int(pdg[parent])) != 443:
                return -1, "invalid_jpsi_mother"
            indices.append(parent)
        if indices[0] != indices[1]:
            return -1, "within_jpsi_mothers_differ"
        return indices[0], "ok"

    parent1, reason1 = jpsi_parent(tree.Jpsi_1_mu_1_Idx, tree.Jpsi_1_mu_2_Idx)
    parent2, reason2 = jpsi_parent(tree.Jpsi_2_mu_1_Idx, tree.Jpsi_2_mu_2_Idx)
    reco_jpsi_pair_ok = parent1 >= 0 and parent2 >= 0 and parent1 != parent2
    if not target_jpsi:
        jpsi_target_reason = "no_two_eligible_workflow_jpsis"
    elif not reco_jpsi_pair_ok:
        jpsi_target_reason = reason1 if parent1 < 0 else (reason2 if parent2 < 0 else "reco_jpsi_parents_not_distinct")
    else:
        jpsi_target_reason = "pair_agrees" if {parent1, parent2} == set(target_jpsi) else "jpsi_pair_target_mismatch"
    jpsi_pair_match = reco_jpsi_pair_ok and bool(target_jpsi) and {parent1, parent2} == set(target_jpsi)
    full_system_match = bool(phi_proxy_match and jpsi_pair_match)
    if not phi_proxy_match:
        failure = "phi_target_missing_or_mismatch"
    elif not jpsi_pair_match:
        failure = jpsi_target_reason
    else:
        failure = "full_system_match"
    return {
        "entry": entry,
        "phi_only_target_match": bool(phi_proxy_match),
        "matched_phi_parent_idx": phi_parent,
        "workflow_phi_target_idx": target_phi,
        "reco_jpsi1_parent_idx": parent1,
        "reco_jpsi2_parent_idx": parent2,
        "workflow_jpsi_target_indices": target_jpsi,
        "eligible_jpsi_count": len(eligible_jpsi),
        "eligible_phi_count": len(eligible_phi),
        "reco_jpsi_pair_contract_pass": bool(reco_jpsi_pair_ok),
        "jpsi_pair_target_match": bool(jpsi_pair_match),
        "full_system_match": full_system_match,
        "failure_reason": failure,
        "jpsi_slot1_failure": reason1,
        "jpsi_slot2_failure": reason2,
    }


def main():
    global OUT, FILES
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--inventory-dir", type=Path, required=True)
    ap.add_argument("--mc-dir", type=Path, required=True)
    args = ap.parse_args()
    OUT = args.inventory_dir
    OUT.mkdir(parents=True, exist_ok=True)
    FILES = {key: args.mc_dir / path.name for key, path in FILES.items()}
    if args.pilot == args.full:
        ap.error("choose exactly one of --pilot or --full")
    start = time.time()
    result = {"mode": "pilot_200_per_sample" if args.pilot else "full", "predicate": "exact retained direct-child workflow J/psi and phi target; final-best source-1 common-mother RECO matches; unordered two-J/psi parent equality plus phi parent equality", "samples": {}}
    full_sidecar = []
    all_schema = pa.schema([
        ("sample", pa.string()), ("entry", pa.int64()), ("phi_only_target_match", pa.bool_()),
        ("matched_phi_parent_idx", pa.int64()), ("workflow_phi_target_idx", pa.int64()),
        ("reco_jpsi1_parent_idx", pa.int64()), ("reco_jpsi2_parent_idx", pa.int64()),
        ("workflow_jpsi_target_indices", pa.list_(pa.int64())), ("eligible_jpsi_count", pa.int32()),
        ("eligible_phi_count", pa.int32()), ("reco_jpsi_pair_contract_pass", pa.bool_()),
        ("jpsi_pair_target_match", pa.bool_()), ("full_system_match", pa.bool_()),
        ("failure_reason", pa.string()), ("jpsi_slot1_failure", pa.string()), ("jpsi_slot2_failure", pa.string()),
    ])
    for sample, path in FILES.items():
        f = ROOT.TFile.Open(str(path), "READ")
        if not f or f.IsZombie():
            raise RuntimeError(f"cannot open local input {path}")
        tree = f.Get("selected")
        if not tree:
            raise RuntimeError(f"missing selected tree in {path}")
        tree.SetBranchStatus("*", 0)
        missing = []
        for name in BRANCHES:
            if tree.GetBranch(name):
                tree.SetBranchStatus(name, 1)
            else:
                missing.append(name)
        if missing:
            raise RuntimeError(f"{sample} missing branches: {missing}")
        n = min(200, int(tree.GetEntries())) if args.pilot else int(tree.GetEntries())
        counts = Counter()
        rows = []
        for ent in range(n):
            row = compute(tree, ent)
            row["sample"] = sample
            rows.append(row)
            for key in ("phi_only_target_match", "reco_jpsi_pair_contract_pass", "jpsi_pair_target_match", "full_system_match"):
                counts[key] += int(row[key])
            counts["failure:" + row["failure_reason"]] += 1
        result["samples"][sample] = {"entries_read": n, "rows_total": int(tree.GetEntries()), "counts": dict(counts), "branch_missing": missing, "examples": rows[:3]}
        if not args.pilot:
            full_sidecar.extend(rows)
        f.Close()
    result["elapsed_seconds"] = time.time() - start
    if args.pilot:
        out = OUT / "full_gen_system_pilot_200.json"
    else:
        out = OUT / "full_gen_system_audit.json"
        pq.write_table(pa.Table.from_pylist(full_sidecar, schema=all_schema), OUT / "full_gen_system_sidecar.parquet", compression=None)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()

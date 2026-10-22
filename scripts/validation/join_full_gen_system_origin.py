#!/usr/bin/env python3
"""Join the bounded full-system sidecar to existing final-best origin rows."""
import json
import argparse
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path("diagnostics/phi_ctau_20261022/inventory")
FULL = Path("diagnostics/phi_ctau_20261022/inventory/full_gen_system_sidecar.parquet")
CORRECTIONS = {
    ("jjp_mc_dps_1_selected", 53845),
    ("jjp_mc_dps_2_cs_selected", 5192),
    ("jjp_mc_dps_2_cs_selected", 22938),
    ("jjp_mc_dps_2_cs_selected", 5358),
}
SAMPLES = {
    "DPS1": "jjp_mc_dps_1_selected",
    "DPS2_CS": "jjp_mc_dps_2_cs_selected",
    "DPS2_G": "jjp_mc_dps_2_g_selected",
    "SPS_CS": "jjp_mc_sps_cs_selected",
    "SPS_G": "jjp_mc_sps_g_selected",
}


def main():
    global ROOT, FULL
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory-dir", type=Path, required=True)
    args = ap.parse_args()
    ROOT = args.inventory_dir
    FULL = ROOT / "full_gen_system_sidecar.parquet"
    joined_rows = []
    report = {"key": "(sample, original ROOT entry)", "samples": {}}
    for sample, full_name in SAMPLES.items():
        old_path = ROOT / f"{full_name}_full_selected.parquet"
        old = pq.read_table(old_path, columns=["entry", "origin_category", "workflow_target_match"]).to_pylist()
        old_by_entry = {int(r["entry"]): r for r in old}
        side = pq.read_table(FULL, filters=[("sample", "=", sample)]).to_pylist()
        side_by_entry = {int(r["entry"]): r for r in side}
        if len(old_by_entry) != len(old) or len(side_by_entry) != len(side) or old_by_entry.keys() != side_by_entry.keys():
            raise RuntimeError(f"entry-key join mismatch for {sample}: old={len(old)} side={len(side)}")
        counts = Counter()
        cross = defaultdict(Counter)
        failures = Counter()
        for ent, oldrow in old_by_entry.items():
            srow = side_by_entry[ent]
            raw = oldrow["origin_category"]
            conservative = "ambiguous_ancestry" if (full_name, ent) in CORRECTIONS or raw == "no_heavy_ancestor_observed" else raw
            phi_only = bool(oldrow["workflow_target_match"])
            full_match = bool(srow["full_system_match"])
            strict_target_exists = int(srow["workflow_phi_target_idx"]) >= 0
            strict_phi_match = bool(srow["phi_only_target_match"])
            if full_match and not phi_only:
                raise RuntimeError(f"full match outside phi-only subset at {sample}:{ent}")
            outcome = "full_system_match" if full_match else ("phi_only_jpsi_mismatch_or_failure" if phi_only else "outside_phi_only_subset")
            counts["all_selected"] += 1
            counts["strict_workflow_target_exists"] += int(strict_target_exists)
            counts["strict_phi_target_agreement"] += int(strict_phi_match)
            counts["phi_only_target_match"] += int(phi_only)
            counts["full_system_match"] += int(full_match)
            counts["phi_only_not_full_system"] += int(phi_only and not full_match)
            counts["jpsi_parent_pair_contract_pass"] += int(srow["reco_jpsi_pair_contract_pass"])
            counts["workflow_jpsi_pair_agreement"] += int(srow["jpsi_pair_target_match"])
            failures[srow["failure_reason"]] += 1
            if int(srow["eligible_jpsi_count"]) < 2:
                failures["no_two_workflow_eligible_jpsis_with_direct_muons"] += 1
            elif int(srow["eligible_phi_count"]) == 0:
                failures["no_workflow_eligible_phi"] += 1
            elif not strict_phi_match:
                failures["matched_phi_differs_from_strict_target"] += 1
            elif not srow["jpsi_pair_target_match"]:
                failures["matched_jpsi_pair_differs_from_workflow_pair"] += 1
            cross["all_selected"][conservative] += 1
            if phi_only:
                cross["phi_only_target_match"][conservative] += 1
            if full_match:
                cross["full_system_match"][conservative] += 1
            if phi_only and not strict_phi_match:
                cross["legacy_phi_only_proxy_lost_under_strict_daughter_requirements"][conservative] += 1
            if phi_only and not full_match:
                cross["phi_only_not_full_system"][conservative] += 1
            joined_rows.append({
                **srow,
                "sample": full_name,
                "origin_category_raw": raw,
                "origin_category_conservative": conservative,
                "phi_only_target_match_from_original_cache": phi_only,
            })
        report["samples"][sample] = {
            "counts": dict(counts),
            "failure_reasons": dict(failures),
            "origin_category_counts": {population: dict(c) for population, c in cross.items()},
        }
    schema = pq.read_schema(FULL).append(pa.field("origin_category_raw", pa.string())).append(pa.field("origin_category_conservative", pa.string())).append(pa.field("phi_only_target_match_from_original_cache", pa.bool_()))
    pq.write_table(pa.Table.from_pylist(joined_rows, schema=schema), ROOT / "full_gen_system_origin_sidecar.parquet", compression=None)
    (ROOT / "full_gen_system_origin_cross_tabs.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

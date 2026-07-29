#!/usr/bin/env python3
"""Report GEN mother-chain depths for matched muons and kaon tracks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import awkward as ak
import numpy as np
import uproot


def _depths(
    match_idx: ak.Array, pdg: ak.Array, mother: ak.Array, target: int, max_depth: int,
) -> tuple[list[int], int]:
    values: list[int] = []
    unresolved = 0
    for event_match, event_pdg, event_mother in zip(ak.to_list(match_idx), ak.to_list(pdg), ak.to_list(mother)):
        for start in event_match:
            idx = int(start)
            if idx < 0:
                continue
            for depth in range(max_depth + 1):
                if idx < 0 or idx >= len(event_pdg):
                    unresolved += 1
                    break
                if abs(int(event_pdg[idx])) == target:
                    values.append(depth)
                    break
                idx = int(event_mother[idx])
            else:
                unresolved += 1
    return values, unresolved


def _summary(depths: list[int], unresolved: int, max_depth: int) -> dict[str, float | int]:
    if not depths:
        return {"matched": 0, "unresolved": unresolved, "max_depth": -1, "p99_depth": -1, "at_or_above_cap": 0}
    array = np.asarray(depths)
    return {
        "matched": int(len(array)),
        "unresolved": unresolved,
        "max_depth": int(array.max()),
        "p99_depth": float(np.quantile(array, 0.99)),
        "at_or_above_cap": int(np.count_nonzero(array >= max_depth)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--tree-path", default="mkcands/X_data")
    parser.add_argument("--max-depth", type=int, default=16)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    fields = ["MC_GenPart_pdgId", "MC_GenPart_motherGenIdx", "muGenMatchIdx", "RecoKaonTrack_genMatchIdx"]
    with uproot.open(args.input) as root_file:
        tree = root_file[args.tree_path]
        arrays = tree.arrays([field for field in fields if field in tree.keys()], library="ak")
    pdg = arrays["MC_GenPart_pdgId"]
    mother = arrays["MC_GenPart_motherGenIdx"]
    report = {"max_depth_cap": args.max_depth}
    if "muGenMatchIdx" in arrays.fields:
        depths, unresolved = _depths(arrays["muGenMatchIdx"], pdg, mother, 443, args.max_depth)
        report["muon_to_jpsi"] = _summary(depths, unresolved, args.max_depth)
    if "RecoKaonTrack_genMatchIdx" in arrays.fields:
        depths, unresolved = _depths(arrays["RecoKaonTrack_genMatchIdx"], pdg, mother, 333, args.max_depth)
        report["kaon_to_phi"] = _summary(depths, unresolved, args.max_depth)
    payload = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(payload + "\n")
    print(payload)


if __name__ == "__main__":
    main()

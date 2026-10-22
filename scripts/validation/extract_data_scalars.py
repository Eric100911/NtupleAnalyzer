#!/usr/bin/env python3
"""Extract the scalar selected-data columns needed by phi ctau mass fits."""
import argparse
from pathlib import Path

import ROOT
import pyarrow as pa
import pyarrow.parquet as pq

ROOT.gROOT.SetBatch(True)
COLUMNS = ("runNum", "lumiNum", "evtNum", "sel_Jpsi_1_mass", "sel_Jpsi_2_mass",
           "sel_Phi_mass", "sel_Phi_ctau", "sel_Phi_ctauErr", "sel_Phi_pt",
           "sel_Phi_eta", "sel_Phi_px", "sel_Phi_py", "sel_Phi_pz")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = ROOT.TFile.Open(args.input, "READ")
    if not source or source.IsZombie():
        raise RuntimeError(f"Cannot open {args.input}")
    tree = source.Get("selected")
    if not tree:
        raise RuntimeError("Missing selected tree")
    missing = [name for name in COLUMNS if not tree.GetBranch(name)]
    if missing:
        raise RuntimeError(f"Missing branches: {missing}")
    tree.SetBranchStatus("*", 0)
    for name in COLUMNS:
        tree.SetBranchStatus(name, 1)
    values = {name: [] for name in COLUMNS}
    for index in range(int(tree.GetEntries())):
        tree.GetEntry(index)
        for name in COLUMNS:
            values[name].append(getattr(tree, name))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(values), args.output, compression=None)
    source.Close()


if __name__ == "__main__":
    main()

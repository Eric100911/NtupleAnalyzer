#!/usr/bin/env python3
"""Add signal_sw=1.0 branch to GEN-matched MC selected files.

MC files are already GEN-matched → all events are true signal → weight=1 everywhere.
Uses RDataFrame Snapshot (fast, multi-threaded).
"""
from __future__ import annotations

import sys
from pathlib import Path

import ROOT


MC_DIR = Path(
    "/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3"
)
OUT_DIR = Path(__file__).resolve().parent / "plots_kinematics" / "temp"

SAMPLE_MAP = {
    "DPS_1": "jjp_mc_dps_1_selected.root",
    "DPS_2_CS": "jjp_mc_dps_2_cs_selected.root",
    "DPS_2_G": "jjp_mc_dps_2_g_selected.root",
    "SPS_CS": "jjp_mc_sps_cs_selected.root",
    "SPS_G": "jjp_mc_sps_g_selected.root",
}


def add_weight_branch(sample: str, in_path: Path, out_path: Path) -> None:
    print(f"[{sample}] {in_path} → {out_path}", flush=True)
    df = ROOT.RDataFrame("selected", str(in_path))
    df = df.Define("signal_sw", "1.0f")
    df.Snapshot("selected", str(out_path))
    print(f"[{sample}] done", flush=True)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for sample, fn in SAMPLE_MAP.items():
        in_path = MC_DIR / fn
        if not in_path.exists():
            print(f"[{sample}] SKIP: {in_path} not found", flush=True)
            continue
        out_path = OUT_DIR / f"jjp_mc_{sample.lower()}_weighted.root"
        add_weight_branch(sample, in_path, out_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())

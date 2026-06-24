#!/usr/bin/env python3
"""Quick test: process one ROOT file through the modified pipeline and save parquet."""
from __future__ import annotations

import sys
from pathlib import Path

import uproot

from efficiency_workflow.config import OfflineSelectionConfig
from efficiency_workflow.efficiency import (
    EFFICIENCY_BRANCHES,
    _process_efficiency_chunk_vectorized,
)
from efficiency_workflow.io import ensure_dir, write_parquet

NTUPLE = (
    "root://cceos.ihep.ac.cn/"
    "///eos/ihep/cms/store/user/xcheng/MC_Production_v3/output/"
    "JJP_DPS2_CS/0/output_ntuple.root:mkcands/X_data"
)

SAMPLE = "JJP_DPS2_CS_test"
OUTDIR = Path("test_response_output") / SAMPLE


def main():
    ensure_dir(OUTDIR)
    print(f"Output dir: {OUTDIR.resolve()}")

    print("Loading branches ...", flush=True)
    with uproot.open(NTUPLE, timeout=120) as f:
        available = set(f.keys())
        branches = [b for b in EFFICIENCY_BRANCHES if b in available]
        print(f"  {len(branches)} branches available", flush=True)
        arrays = f.arrays(branches, library="ak")

    print(f"Processing {len(arrays)} events ...", flush=True)
    cfg = OfflineSelectionConfig()
    result = _process_efficiency_chunk_vectorized(arrays, NTUPLE, SAMPLE, cfg, 0)

    gen_df = result["gen_systems"]
    event_df = result["event_step_flags"]

    print(f"gen_systems:      {len(gen_df)} rows")
    print(f"event_step_flags: {len(event_df)} rows (columns: {len(event_df.columns)})")

    new_cols = [c for c in event_df.columns if c.startswith("reco_best_") or c == "n_quality_candidates"]
    print(f"New columns present: {new_cols}")

    write_parquet(gen_df, OUTDIR / "gen_systems.parquet")
    write_parquet(event_df, OUTDIR / "event_step_flags.parquet")
    print("Parquet files written.")

    # Quick summary
    has_both = (event_df["full_gen"] == 1) & event_df["reco_best_phi_pt"].notna()
    print(f"\nEvents with full_gen + quality reco: {has_both.sum()}/{event_df['full_gen'].sum()}")
    print(f"Events with reco_best_phi_matches_gen: {event_df['reco_best_phi_matches_gen'].sum()}")


if __name__ == "__main__":
    main()

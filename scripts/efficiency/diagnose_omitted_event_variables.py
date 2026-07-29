#!/usr/bin/env python3
"""Tabulate event-stage efficiencies versus variables omitted from their maps.

This is a closure diagnostic, not a replacement for the factorized maps.  It
shows whether an event-level factor parameterized in leading/subleading J/psi
pT has a visible residual dependence on phi pT or any object rapidity.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from efficiency_workflow.efficiency import EfficiencyBinning, _merged_gen_events


STAGES = {
    "hlt": ("s_cand", "hlt_muon_matched"),
    "four_muon_vtx": ("hlt_muon_matched", "four_muon_vtx"),
    "triOnia": ("four_muon_vtx", "Pri_assocPVPass"),
}


def _rows(frame: pd.DataFrame, denominator: str, numerator: str, variable: str, edges: tuple[float, ...]) -> list[dict]:
    denom = frame[denominator].to_numpy(dtype=bool)
    passed = denom & frame[numerator].to_numpy(dtype=bool)
    values = frame[variable].to_numpy(dtype=float)
    bins = np.digitize(values, edges, right=False) - 1
    result: list[dict] = []
    for index in range(len(edges) - 1):
        in_bin = bins == index
        total = int(np.count_nonzero(denom & in_bin))
        selected = int(np.count_nonzero(passed & in_bin))
        result.append({
            "variable": variable,
            "bin": index,
            "min": edges[index],
            "max": edges[index + 1],
            "total": total,
            "passed": selected,
            "efficiency": selected / total if total else np.nan,
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample_dir", type=Path, help="Directory containing gen_systems.parquet and event_step_flags.parquet")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    gen = pd.read_parquet(args.sample_dir / "gen_systems.parquet")
    event = pd.read_parquet(args.sample_dir / "event_step_flags.parquet")
    frame = _merged_gen_events(gen, event)
    binning = EfficiencyBinning()
    variables = {
        "jpsi_lead_abs_y": binning.object_abs_y_edges,
        "jpsi_sublead_abs_y": binning.object_abs_y_edges,
        "phi_pt": binning.phi_pt_edges,
        "phi_abs_y": binning.object_abs_y_edges,
    }
    records: list[dict] = []
    for stage, (denominator, numerator) in STAGES.items():
        for variable, edges in variables.items():
            for row in _rows(frame, denominator, numerator, variable, edges):
                records.append({"stage": stage, "denominator": denominator, "numerator": numerator, **row})
    output = pd.DataFrame(records)
    if args.output:
        output.to_parquet(args.output, index=False)
    else:
        print(output.to_string(index=False))


if __name__ == "__main__":
    main()

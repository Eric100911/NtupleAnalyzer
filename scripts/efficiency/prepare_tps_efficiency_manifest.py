#!/usr/bin/env python3
"""Convert a TPS retained-event inventory into an efficiency input manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from efficiency_workflow.tps_manifest import read_tps_inventory, write_tps_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path, help="Three-column TPS inventory text file")
    parser.add_argument("--sample", default="JJP_TPS_MC_v4_1", help="Sample label in the efficiency output")
    parser.add_argument("--output", required=True, type=Path, help="JSON manifest for run_efficiency.py")
    args = parser.parse_args()

    rows = read_tps_inventory(args.inventory)
    write_tps_manifest(rows, args.sample, str(args.inventory), args.output)
    total = sum(row.total_entries for row in rows)
    retained = sum(row.retained_events for row in rows)
    print(f"Wrote {len(rows)} files to {args.output}")
    print(f"Inventory totals: total_entries={total}, retained_events={retained}")


if __name__ == "__main__":
    main()

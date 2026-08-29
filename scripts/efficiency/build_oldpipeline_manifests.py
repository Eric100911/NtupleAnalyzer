#!/usr/bin/env python3
"""Build efficiency input manifests for legacy-pipeline MC samples.

Turns the per-file counts produced by ``count_ntuple_candidates.py`` into the
versioned JSON manifest format consumed by ``run_efficiency.py`` /
``prepare_efficiency_shards.py --input-file-manifest``.  Each manifest records
per-file ``total_entries`` and ``retained_candidate_events`` (the
reconstruction + selection pass statistics) plus the content-derived
``manifest_id`` used for coverage checks at merge time.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from efficiency_workflow.tps_manifest import TpsInventoryRow, build_tps_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counts-json", required=True, type=Path, help="Output of count_ntuple_candidates.py")
    parser.add_argument("--sample", required=True, help="Sample label, e.g. JJP_SPS_CS")
    parser.add_argument("--source-inventory", required=True, help="Short label for the inventory provenance")
    parser.add_argument("--output", required=True, type=Path, help="Output manifest path")
    args = parser.parse_args()

    counts = json.loads(args.counts_json.read_text(encoding="utf-8"))
    rows: list[TpsInventoryRow] = []
    n_cand_by_file: dict[str, int] = {}
    failed: list[str] = []
    for url, row in sorted(counts.items()):
        if row.get("status") != "ok":
            failed.append(f"{url}: {row.get('status')}")
            continue
        rows.append(
            TpsInventoryRow(
                source_file=url,
                total_entries=int(row["total_entries"]),
                retained_candidate_events=int(row["retained_candidate_events"]),
            )
        )
        n_cand_by_file[url] = int(row.get("n_candidates", 0))

    if not rows:
        raise SystemExit(f"No OK rows in {args.counts_json}; cannot build manifest.")
    if failed:
        print(f"WARNING: {len(failed)} failed rows excluded:", file=sys.stderr)
        for item in failed[:10]:
            print(f"  {item}", file=sys.stderr)

    payload = build_tps_manifest(rows, args.sample, args.source_inventory)
    # Enrich per-file inventory with the raw candidate multiplicity.
    for item in payload["inventory"]:
        item["n_candidates"] = n_cand_by_file.get(item["source_file"], 0)
    payload["inventory_totals"]["n_candidates"] = sum(n_cand_by_file.values())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    totals = payload["inventory_totals"]
    frac = totals["retained_candidate_events"] / totals["total_entries"] if totals["total_entries"] else 0.0
    print(f"Wrote {payload['n_files']} files to {args.output}")
    print(f"  manifest_id={payload['manifest_id']}")
    print(f"  total_entries={totals['total_entries']} "
          f"retained_candidate_events={totals['retained_candidate_events']} "
          f"n_candidates={totals['n_candidates']}")
    print(f"  retention fraction = {frac:.6f}")


if __name__ == "__main__":
    main()

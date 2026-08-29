#!/usr/bin/env python3
"""Count ntuple entries and retained reconstructed-candidate events.

For each input TPS-Onia2MuMu ntuple (opened over XRootD), report:
  - total_entries            : number of events in the data tree
  - retained_candidate_events: events with >=1 Pri candidate satisfying
                               Pri_passAny (fitPass || assocPVPass)
  - n_candidates             : total number of such candidates

This is the "reconstruction + selection pass" bookkeeping used to size
efficiency manifests.  Output is a JSON keyed by source file URL, plus a
human-readable summary.

Requires the LCG_109a environment (uproot + awkward), e.g.:

  bash -c 'source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh \
    && python3 scripts/efficiency/count_ntuple_candidates.py \
         --input-file-list /tmp/files.txt --workers 8 \
         --output /tmp/counts.json'
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import awkward as ak
import uproot

# Candidate definition mirrors the DPS1 inventory:
#   Pri_passAny == fitPass || assocPVPass, stored per Pri candidate.
CANDIDATE_BRANCH = "Pri_passAny"
FALLBACK_BRANCHES = ("Pri_fitPass", "Pri_assocPVPass")


def _read_urls(list_path: str) -> list[str]:
    urls = [
        line.strip()
        for line in Path(list_path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not urls:
        raise ValueError(f"No file URLs in {list_path}")
    return urls


def count_single_file(url: str) -> dict[str, object]:
    entry = {"source_file": url, "status": "ok"}
    try:
        with uproot.open(url) as root_file:
            tree_path = None
            for candidate in ("mkcands/X_data", "X_data"):
                if candidate in root_file:
                    tree_path = candidate
                    break
            if tree_path is None:
                entry.update(status="no-data-tree", total_entries=0, retained_candidate_events=0, n_candidates=0)
                return entry
            tree = root_file[tree_path]
            total = int(tree.num_entries)
            entry["total_entries"] = total
            if CANDIDATE_BRANCH in tree:
                flag = tree[CANDIDATE_BRANCH].array(library="ak")
            elif all(b in tree for b in FALLBACK_BRANCHES):
                flags = [ak.any(tree[b].array(library="ak"), axis=1) for b in FALLBACK_BRANCHES]
                flag = ak.any(ak.concatenate(flags, axis=1), axis=1)
            else:
                entry.update(status="no-candidate-branch", retained_candidate_events=0, n_candidates=0)
                return entry
            entry["retained_candidate_events"] = int(ak.sum(ak.any(flag, axis=1)))
            entry["n_candidates"] = int(ak.sum(flag))
            return entry
    except Exception as exc:  # per-file failure must not kill the batch
        entry.update(status=f"error: {type(exc).__name__}: {exc}", total_entries=0, retained_candidate_events=0, n_candidates=0)
        return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file-list", required=True, type=Path, help="Text file with one XRootD ntuple URL per line")
    parser.add_argument("--workers", type=int, default=8, help="Parallel reader processes")
    parser.add_argument("--output", required=True, type=Path, help="JSON output path")
    parser.add_argument("--limit", type=int, default=0, help="Only count the first N files (smoke test)")
    args = parser.parse_args()

    urls = _read_urls(args.input_file_list)
    if args.limit > 0:
        urls = urls[: args.limit]

    results: dict[str, dict[str, object]] = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(count_single_file, url): url for url in urls}
        for done, future in enumerate(as_completed(futures), 1):
            url = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # defensive; count_single_file already catches
                row = {"source_file": url, "status": f"unhandled: {exc}"}
            results[url] = row
            if done % 50 == 0 or done == len(urls):
                print(f"  {done}/{len(urls)}", flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    ok = [r for r in results.values() if r.get("status") == "ok"]
    failed = [r for r in results.values() if r.get("status") != "ok"]
    total_events = sum(int(r.get("total_entries", 0)) for r in ok)
    retained = sum(int(r.get("retained_candidate_events", 0)) for r in ok)
    n_cand = sum(int(r.get("n_candidates", 0)) for r in ok)
    print(f"\nfiles ok={len(ok)} failed={len(failed)}")
    print(f"total_entries={total_events} retained_candidate_events={retained} n_candidates={n_cand}")
    if total_events:
        print(f"retention fraction = {retained / total_events:.6f}")
    for row in failed[:10]:
        print(f"  FAIL {row['source_file']}: {row['status']}")


if __name__ == "__main__":
    main()

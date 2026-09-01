#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


import argparse
from pathlib import Path

from efficiency_workflow.products import merge_efficiency_shards


def main() -> None:
    """Entry point for merging efficiency shard outputs.

    Parses command-line arguments and delegates to the
    efficiency_workflow.products.merge_efficiency_shards function,
    which concatenates per-shard parquet files and rebuilds
    the binned efficiency maps.
    """
    parser = argparse.ArgumentParser(description="Merge JJP efficiency shard outputs")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--shards-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--formal-manifest",
        type=Path,
        help="Immutable formal master manifest; enables fail-closed completeness validation.",
    )
    parser.add_argument(
        "--formal-shards-dir",
        type=Path,
        help="Directory containing formal shard_XXXX.json manifests; required with --formal-manifest.",
    )
    args = parser.parse_args()

    result = merge_efficiency_shards(
        sample=args.sample,
        shards_dir=Path(args.shards_dir),
        output_dir=Path(args.output_dir),
        formal_manifest=args.formal_manifest,
        formal_shards_dir=args.formal_shards_dir,
    )
    print(f"Wrote merged efficiency outputs to {result.output_dir}")


if __name__ == "__main__":
    main()

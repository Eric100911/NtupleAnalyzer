#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from efficiency_workflow.products import merge_efficiency_shards


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge JJP efficiency shard outputs")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--shards-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    result = merge_efficiency_shards(
        sample=args.sample,
        shards_dir=Path(args.shards_dir),
        output_dir=Path(args.output_dir),
    )
    print(f"Wrote merged efficiency outputs to {result.output_dir}")


if __name__ == "__main__":
    main()

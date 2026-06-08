#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from efficiency_workflow.corrections import (
    DEFAULT_EFFICIENCY_STEP,
    DEFAULT_MAP_TYPE,
    annotate_root_tree_with_efficiency,
    load_efficiency_correction_map,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Annotate a selected JJP ROOT tree with efficiency correction branches")
    parser.add_argument("-i", "--input", required=True, help="Input selected ROOT file")
    parser.add_argument("-o", "--output", required=True, help="Output selected ROOT file with effcorr_* branches")
    parser.add_argument("--tree", default="selected", help="Input tree name")
    parser.add_argument("--efficiency-map", default=None, help="Direct parquet map path")
    parser.add_argument("--efficiency-dir", default=None, help="Efficiency merged output directory containing per-sample subdirs")
    parser.add_argument("--efficiency-sample", default=None, help="Efficiency sample under --efficiency-dir")
    parser.add_argument("--efficiency-step", default=DEFAULT_EFFICIENCY_STEP, help="Efficiency step to use")
    parser.add_argument("--map-type", default=DEFAULT_MAP_TYPE, help="Map type to use")
    parser.add_argument("--denominator", default="absolute", choices=["absolute", "conditional"], help="Efficiency denominator convention")
    parser.add_argument(
        "--on-missing",
        default="error",
        choices=["error", "unity", "drop"],
        help="Handling for out-of-map or zero-efficiency candidates; unity/drop are for debugging only",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    correction_map = load_efficiency_correction_map(
        efficiency_map=args.efficiency_map,
        efficiency_dir=args.efficiency_dir,
        efficiency_sample=args.efficiency_sample,
        step=args.efficiency_step,
        map_type=args.map_type,
        denominator=args.denominator,
    )
    summary = annotate_root_tree_with_efficiency(
        input_file=args.input,
        output_file=args.output,
        tree_name=args.tree,
        correction_map=correction_map,
        on_missing=args.on_missing,
    )

    print("=" * 80)
    print("apply efficiency correction")
    print("=" * 80)
    print(f"[INFO] input        : {args.input}")
    print(f"[INFO] output       : {args.output}")
    print(f"[INFO] map          : {correction_map.source}")
    print(f"[INFO] step         : {correction_map.step}")
    print(f"[INFO] map type     : {correction_map.map_type}")
    print(f"[INFO] denominator  : {correction_map.denominator}")
    print(f"[INFO] entries      : {summary.entries}")
    print(f"[INFO] corrected    : {summary.ok}")
    print(f"[INFO] missing bins : {summary.missing_bin}")
    print(f"[INFO] invalid eff  : {summary.invalid_efficiency}")
    print(f"[INFO] min eff      : {summary.min_efficiency:.6g}")
    print(f"[INFO] max eff      : {summary.max_efficiency:.6g}")
    print(f"[INFO] mean weight  : {summary.mean_weight:.6g}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())

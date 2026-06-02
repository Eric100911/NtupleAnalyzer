#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from efficiency_workflow.yield_correction import (
    DEFAULT_NOMINAL_SAMPLE,
    DEFAULT_YIELD_SAMPLES,
    YieldSystematicResult,
    compute_efficiency_corrected_yield,
    write_yield_result_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute efficiency-corrected JJP signal yield with subprocess envelope")
    parser.add_argument("--data-input", required=True, help="Selected JJP data ROOT file")
    parser.add_argument("--efficiency-dir", required=True, help="Merged efficiency directory containing per-sample maps")
    parser.add_argument("--samples", nargs="+", default=list(DEFAULT_YIELD_SAMPLES), help="Efficiency samples to compare")
    parser.add_argument("--nominal-sample", default=DEFAULT_NOMINAL_SAMPLE, help="Nominal sample for central value")
    parser.add_argument("--efficiency-step", default="Pri_assocPVPass", help="Efficiency step to use")
    parser.add_argument("--map-type", default="correlated_3d", help="Efficiency map type to use")
    parser.add_argument("--denominator", default="absolute", choices=["absolute", "conditional"])
    parser.add_argument("--min-total", type=int, default=10, help="Minimum MC total before interpolating a bin")
    parser.add_argument("--correction-mode", default="factorized", choices=["factorized", "legacy-correlated"])
    parser.add_argument("--n-min-fine", type=int, default=30, help="Minimum MC total for fine factorized bins")
    parser.add_argument("--n-min-coarse", type=int, default=50, help="Minimum MC total for coarse factorized bins")
    parser.add_argument("--on-missing", default="error", choices=["error", "drop"], help="Action when efficiency lookup misses a bin (default: error)")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="RooFit NumCPU")
    parser.add_argument("-o", "--output", default=None, help="Output JSON path")
    parser.add_argument("--plot-dir", default=None, help="Directory for yield comparison plot")
    parser.add_argument("--temp-dir", default=None, help="Directory for weighted intermediate ROOT trees")
    return parser.parse_args()


def _default_output_path(data_input: str) -> Path:
    stem = Path(data_input).stem
    return Path(f"{stem}_efficiency_corrected_yield.json")


def _print_summary(result: YieldSystematicResult, *, correction_mode: str, step: str, map_type: str, denominator: str) -> None:
    print("=== Efficiency-Corrected Yield Summary ===")
    print(f"Mode: {correction_mode}")
    if correction_mode == "legacy-correlated":
        print(f"Step: {step} | Map: {map_type} | Denominator: {denominator}")
    print()
    print(f"Raw yield (unweighted): {result.raw_yield:.1f} +/- {result.raw_yield_err:.1f}")
    print()
    print(f"{'Sample':<16} {'Corrected Yield':>22} {'Fallback':>8} {'Mean w':>10} {'MC stat':>10} {'Status':>8}")
    for sample, item in result.per_sample.items():
        marker = " *" if sample == result.nominal_sample else ""
        status = "OK" if item.n_missing == 0 and item.n_invalid == 0 else f"bad={item.n_missing + item.n_invalid}"
        print(
            f"{sample + marker:<16} "
            f"{item.corrected_yield:10.1f} +/- {item.corrected_yield_err:<8.1f} "
            f"{item.n_interpolated:8d} "
            f"{item.mean_weight:10.3g} "
            f"{item.mc_stat_unc:10.1f} "
            f"{status:>8}"
        )
    print()
    print("Systematic Summary:")
    print(f"  Nominal corrected yield:     {result.nominal_corrected_yield:.1f} +/- {result.stat_unc:.1f} (stat)")
    print(f"  MC stat uncertainty:         {result.mc_stat_unc:.1f}")
    print(f"  Envelope half-width:         {result.envelope_half_width:.1f}")
    print(f"  RMS:                         {result.rms:.1f}")
    print(f"  Max deviation from nominal:  {result.max_deviation:.1f}")
    print(f"  Total uncertainty:           {result.total_unc:.1f} (stat + syst in quadrature)")
    print(f"  Total:                       {result.nominal_corrected_yield:.1f} +/- {result.total_unc:.1f}")


def main() -> int:
    args = parse_args()
    output_path = Path(args.output) if args.output else _default_output_path(args.data_input)
    temp_dir = Path(args.temp_dir) if args.temp_dir else output_path.with_suffix("").parent / f"{output_path.stem}_weighted_trees"
    print("=== Efficiency-corrected yield run ===", flush=True)
    print(f"Data input    : {args.data_input}", flush=True)
    print(f"Efficiency dir: {args.efficiency_dir}", flush=True)
    print(f"Samples       : {', '.join(args.samples)}", flush=True)
    print(f"Nominal sample: {args.nominal_sample}", flush=True)
    print(f"Mode          : {args.correction_mode}", flush=True)
    print(f"Step/map      : {args.efficiency_step} / {args.map_type} ({args.denominator})", flush=True)
    print(f"Fallback N    : fine={args.n_min_fine}, coarse={args.n_min_coarse}", flush=True)
    print(f"Output JSON   : {output_path}", flush=True)
    print(f"Temp dir      : {temp_dir}", flush=True)
    result = compute_efficiency_corrected_yield(
        args.data_input,
        args.efficiency_dir,
        samples=args.samples,
        nominal_sample=args.nominal_sample,
        step=args.efficiency_step,
        map_type=args.map_type,
        denominator=args.denominator,
        min_total=args.min_total,
        correction_mode=args.correction_mode,
        n_min_fine=args.n_min_fine,
        n_min_coarse=args.n_min_coarse,
        on_missing=args.on_missing,
        temp_dir=temp_dir,
        jobs=args.jobs,
        status_callback=lambda message: print(f"[yieldcorr] {message}", flush=True),
    )
    _print_summary(result, correction_mode=args.correction_mode, step=args.efficiency_step, map_type=args.map_type, denominator=args.denominator)
    write_yield_result_json(result, output_path)
    print(f"\nWrote JSON: {output_path}")
    if args.plot_dir:
        from efficiency_workflow.config import CmsPlotStyleConfig
        from efficiency_workflow.plotting import write_yield_comparison_plot

        plot_path = write_yield_comparison_plot(
            Path(args.plot_dir) / "yield_comparison.png",
            result,
            plot_style_cfg=CmsPlotStyleConfig(is_data=True, era="Run 3", lumi_fb=289.2, energy_tev=13.6),
        )
        print(f"Wrote plot: {plot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

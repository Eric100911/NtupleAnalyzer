from __future__ import annotations

import argparse
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from .build_factorized_maps import build_factorized_maps_for_sample, build_post_acceptance_5d_map
from .corrections import (
    DEFAULT_EFFICIENCY_STEP,
    DEFAULT_MAP_TYPE,
    EfficiencyCorrectionMap,
    FactorizedCorrectionMap,
    HybridCorrectionMap,
    STATUS_OK,
    load_efficiency_correction_map,
    load_factorized_correction_map,
    load_hybrid_correction_map,
)
from .efficiency import _merged_gen_events
from .io import ensure_dir, write_json, write_parquet


DEFAULT_CLOSURE_SAMPLES = ("JJP_DPS1", "JJP_DPS2_CS", "JJP_DPS2_G", "JJP_SPS_CS", "JJP_SPS_G")


@dataclass(frozen=True)
class ClosureResult:
    label: str
    n_gen_fiducial: int
    n_reco_selected: int
    corrected_sum: float
    ratio: float
    n_failed_lookup: int

    def to_dict(self) -> dict:
        return asdict(self)


def _corrected_sum(
    frame: pd.DataFrame,
    correction_map: FactorizedCorrectionMap,
    *,
    selected_col: str,
) -> tuple[float, int, int]:
    if selected_col not in frame.columns:
        raise ValueError(f"Selected column {selected_col!r} is not present in merged gen/event table")
    selected = frame.loc[frame[selected_col].astype(bool)]
    result = correction_map.lookup_arrays(
        jpsi1_pt=selected["jpsi_lead_pt"].to_numpy(dtype=float),
        jpsi1_y=selected["jpsi_lead_y"].to_numpy(dtype=float),
        jpsi2_pt=selected["jpsi_sublead_pt"].to_numpy(dtype=float),
        jpsi2_y=selected["jpsi_sublead_y"].to_numpy(dtype=float),
        phi_pt=selected["phi_pt"].to_numpy(dtype=float),
        phi_y=selected["phi_y"].to_numpy(dtype=float),
    )
    ok = result.status == STATUS_OK
    total = float(np.nansum(result.weight[ok])) if ok.size else 0.0
    failed = int(np.count_nonzero(~ok))
    return total, int(len(selected)), failed


def _closure_result_from_merged(
    label: str,
    correction_map: FactorizedCorrectionMap,
    merged: pd.DataFrame,
    *,
    selected_col: str,
) -> ClosureResult:
    corrected, n_selected, failed = _corrected_sum(merged, correction_map, selected_col=selected_col)
    n_gen = int(merged["full_gen"].sum()) if "full_gen" in merged.columns else int(len(merged))
    ratio = float(corrected / n_gen) if n_gen > 0 else math.nan
    return ClosureResult(label, n_gen, n_selected, corrected, ratio, failed)


def self_closure_test(
    sample: str,
    correction_map: FactorizedCorrectionMap,
    gen_df: pd.DataFrame,
    event_df: pd.DataFrame,
    *,
    selected_col: str = "Pri_assocPVPass",
) -> ClosureResult:
    merged = _merged_gen_events(gen_df, event_df)
    return _closure_result_from_merged(sample, correction_map, merged, selected_col=selected_col)


def cross_closure_test(
    label: str,
    correction_map: FactorizedCorrectionMap,
    gen_df: pd.DataFrame,
    event_df: pd.DataFrame,
    *,
    selected_col: str = "Pri_assocPVPass",
) -> ClosureResult:
    return self_closure_test(label, correction_map, gen_df, event_df, selected_col=selected_col)


def factorization_closure_test(
    *,
    direct_efficiency: float,
    factorized_efficiency: float,
    label: str = "factorization",
) -> dict:
    ratio = float(direct_efficiency / factorized_efficiency) if factorized_efficiency > 0.0 else math.nan
    return {
        "label": label,
        "direct_efficiency": float(direct_efficiency),
        "factorized_efficiency": float(factorized_efficiency),
        "ratio": ratio,
        "deviation_from_unity": float(abs(ratio - 1.0)) if np.isfinite(ratio) else math.nan,
    }


def _load_sample_inputs(input_dir: Path, samples: Sequence[str]) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    gen: dict[str, pd.DataFrame] = {}
    event: dict[str, pd.DataFrame] = {}
    for sample in samples:
        sample_dir = input_dir / sample
        gen_path = sample_dir / "gen_systems.parquet"
        event_path = sample_dir / "event_step_flags.parquet"
        if not gen_path.exists() or not event_path.exists():
            raise FileNotFoundError(f"Missing closure parquet inputs for {sample}: {gen_path}, {event_path}")
        gen[sample] = pd.read_parquet(gen_path)
        event[sample] = pd.read_parquet(event_path)
    return gen, event


def run_closure_matrix(
    input_dir: str | Path,
    *,
    samples: Sequence[str] = DEFAULT_CLOSURE_SAMPLES,
    selected_col: str = "Pri_assocPVPass",
    output_dir: str | Path | None = None,
    build_maps: bool = False,
    self_only: bool = False,
    n_min_fine: int = 30,
    n_min_coarse: int = 50,
) -> pd.DataFrame:
    """Run self/cross factorized closure tests and write parquet/csv/manifest outputs."""
    input_path = Path(input_dir)
    output_path = ensure_dir(Path(output_dir) if output_dir is not None else input_path / "closure")
    samples = tuple(samples)
    if not samples:
        raise ValueError("At least one sample is required")

    if build_maps:
        for sample in samples:
            build_factorized_maps_for_sample(
                input_path / sample,
                input_path / sample / "maps",
                event_end_step=selected_col,
            )

    maps = {
        sample: load_factorized_correction_map(
            input_path / sample,
            n_min_fine=n_min_fine,
            n_min_coarse=n_min_coarse,
        )
        for sample in samples
    }
    gen, event = _load_sample_inputs(input_path, samples)
    merged = {sample: _merged_gen_events(gen[sample], event[sample]) for sample in samples}

    rows: list[dict] = []
    for sample in samples:
        result = _closure_result_from_merged(sample, maps[sample], merged[sample], selected_col=selected_col)
        rows.append(
            {
                "closure_type": "self",
                "map_sample": sample,
                "target_sample": sample,
                **result.to_dict(),
            }
        )

    if not self_only:
        for map_sample in samples:
            for target_sample in samples:
                if map_sample == target_sample:
                    continue
                label = f"{map_sample}_on_{target_sample}"
                result = _closure_result_from_merged(
                    label,
                    maps[map_sample],
                    merged[target_sample],
                    selected_col=selected_col,
                )
                rows.append(
                    {
                        "closure_type": "cross",
                        "map_sample": map_sample,
                        "target_sample": target_sample,
                        **result.to_dict(),
                    }
                )

    result_df = pd.DataFrame(rows)
    parquet_path = output_path / "closure_results.parquet"
    csv_path = output_path / "closure_results.csv"
    manifest_path = output_path / "closure_manifest.json"
    write_parquet(result_df, parquet_path)
    result_df.to_csv(csv_path, index=False)
    write_json(
        {
            "stage": "factorized_closure",
            "input_dir": str(input_path.resolve()),
            "output_dir": str(output_path.resolve()),
            "samples": list(samples),
            "selected_col": selected_col,
            "build_maps": bool(build_maps),
            "self_only": bool(self_only),
            "n_min_fine": int(n_min_fine),
            "n_min_coarse": int(n_min_coarse),
            "artifacts": {
                "parquet": parquet_path.name,
                "csv": csv_path.name,
            },
            "n_rows": int(len(result_df)),
        },
        manifest_path,
    )
    return result_df


# ---------------------------------------------------------------------------
# non-factorized (correlated) closure
# ---------------------------------------------------------------------------


def _corrected_sum_nonfactorized(
    frame: pd.DataFrame,
    correction_map: EfficiencyCorrectionMap,
    *,
    selected_col: str,
) -> tuple[float, int, int]:
    if selected_col not in frame.columns:
        raise ValueError(f"Selected column {selected_col!r} is not present in merged gen/event table")
    selected = frame.loc[frame[selected_col].astype(bool)]
    kwargs: dict = {}
    if correction_map.has_u:
        if "jpsi_lead_abs_y" not in selected.columns or "jpsi_sublead_abs_y" not in selected.columns:
            raise ValueError("5D correction map requires jpsi lead/sublead abs_y columns in merged frame")
        kwargs["jpsi1_abs_y"] = selected["jpsi_lead_abs_y"].to_numpy(dtype=float)
        kwargs["jpsi2_abs_y"] = selected["jpsi_sublead_abs_y"].to_numpy(dtype=float)
    result = correction_map.lookup_arrays(
        jpsi1_pt=selected["jpsi_lead_pt"].to_numpy(dtype=float),
        jpsi2_pt=selected["jpsi_sublead_pt"].to_numpy(dtype=float),
        phi_pt=selected["phi_pt"].to_numpy(dtype=float),
        **kwargs,
    )
    ok = result.status == STATUS_OK
    total = float(np.nansum(result.weight[ok])) if ok.size else 0.0
    failed = int(np.count_nonzero(~ok))
    return total, int(len(selected)), failed


def _closure_result_from_merged_nonfactorized(
    label: str,
    correction_map: EfficiencyCorrectionMap,
    merged: pd.DataFrame,
    *,
    selected_col: str,
) -> ClosureResult:
    corrected, n_selected, failed = _corrected_sum_nonfactorized(merged, correction_map, selected_col=selected_col)
    n_gen = int(merged["full_gen"].sum()) if "full_gen" in merged.columns else int(len(merged))
    ratio = float(corrected / n_gen) if n_gen > 0 else math.nan
    return ClosureResult(label, n_gen, n_selected, corrected, ratio, failed)


def run_closure_correlated(
    input_dir: str | Path,
    *,
    samples: Sequence[str] = DEFAULT_CLOSURE_SAMPLES,
    selected_col: str = DEFAULT_EFFICIENCY_STEP,
    map_type: str = DEFAULT_MAP_TYPE,
    denominator: str = "absolute",
    output_dir: str | Path | None = None,
    self_only: bool = False,
    min_total_fine: int = 0,
    min_total_coarse: int = 0,
) -> pd.DataFrame:
    """Run self/cross non-factorized closure tests and write parquet/csv/manifest outputs.

    This is the non-factorized counterpart of ``run_closure_matrix``.  It loads
    ``EfficiencyCorrectionMap`` per sample (instead of ``FactorizedCorrectionMap``)
    and supports both ``correlated_3d`` and ``correlated_5d`` map types.
    """
    input_path = Path(input_dir)
    stage_name = f"closure_{map_type}"
    output_path = ensure_dir(Path(output_dir) if output_dir is not None else input_path / f"closure_{map_type}")
    samples = tuple(samples)
    if not samples:
        raise ValueError("At least one sample is required")

    maps: dict[str, EfficiencyCorrectionMap] = {}
    for sample in samples:
        maps[sample] = load_efficiency_correction_map(
            efficiency_dir=input_path,
            efficiency_sample=sample,
            step=selected_col,
            map_type=map_type,
            denominator=denominator,
            min_total_fine=min_total_fine,
            min_total_coarse=min_total_coarse,
        )

    gen, event = _load_sample_inputs(input_path, samples)
    merged = {sample: _merged_gen_events(gen[sample], event[sample]) for sample in samples}

    rows: list[dict] = []
    for sample in samples:
        result = _closure_result_from_merged_nonfactorized(sample, maps[sample], merged[sample], selected_col=selected_col)
        rows.append(
            {
                "closure_type": "self",
                "map_sample": sample,
                "target_sample": sample,
                **result.to_dict(),
            }
        )

    if not self_only:
        for map_sample in samples:
            for target_sample in samples:
                if map_sample == target_sample:
                    continue
                label = f"{map_sample}_on_{target_sample}"
                result = _closure_result_from_merged_nonfactorized(
                    label,
                    maps[map_sample],
                    merged[target_sample],
                    selected_col=selected_col,
                )
                rows.append(
                    {
                        "closure_type": "cross",
                        "map_sample": map_sample,
                        "target_sample": target_sample,
                        **result.to_dict(),
                    }
                )

    result_df = pd.DataFrame(rows)
    parquet_path = output_path / "closure_results.parquet"
    csv_path = output_path / "closure_results.csv"
    manifest_path = output_path / "closure_manifest.json"
    write_parquet(result_df, parquet_path)
    result_df.to_csv(csv_path, index=False)
    write_json(
        {
            "stage": stage_name,
            "input_dir": str(input_path.resolve()),
            "output_dir": str(output_path.resolve()),
            "samples": list(samples),
            "selected_col": selected_col,
            "map_type": map_type,
            "denominator": denominator,
            "self_only": bool(self_only),
            "artifacts": {
                "parquet": parquet_path.name,
                "csv": csv_path.name,
            },
            "n_rows": int(len(result_df)),
        },
        manifest_path,
    )
    return result_df


# ---------------------------------------------------------------------------
# hybrid (factorized acceptance × 5D conditional post-acceptance) closure
# ---------------------------------------------------------------------------


def _corrected_sum_hybrid(
    frame: pd.DataFrame,
    correction_map: HybridCorrectionMap,
    *,
    selected_col: str,
) -> tuple[float, int, int]:
    if selected_col not in frame.columns:
        raise ValueError(f"Selected column {selected_col!r} is not present in merged gen/event table")
    selected = frame.loc[frame[selected_col].astype(bool)]
    result = correction_map.lookup_arrays(
        jpsi1_pt=selected["jpsi_lead_pt"].to_numpy(dtype=float),
        jpsi1_y=selected["jpsi_lead_y"].to_numpy(dtype=float),
        jpsi2_pt=selected["jpsi_sublead_pt"].to_numpy(dtype=float),
        jpsi2_y=selected["jpsi_sublead_y"].to_numpy(dtype=float),
        phi_pt=selected["phi_pt"].to_numpy(dtype=float),
        phi_y=selected["phi_y"].to_numpy(dtype=float),
    )
    ok = result.status == STATUS_OK
    total = float(np.nansum(result.weight[ok])) if ok.size else 0.0
    failed = int(np.count_nonzero(~ok))
    return total, int(len(selected)), failed


def _closure_result_from_merged_hybrid(
    label: str,
    correction_map: HybridCorrectionMap,
    merged: pd.DataFrame,
    *,
    selected_col: str,
) -> ClosureResult:
    corrected, n_selected, failed = _corrected_sum_hybrid(merged, correction_map, selected_col=selected_col)
    n_gen = int(merged["full_gen"].sum()) if "full_gen" in merged.columns else int(len(merged))
    ratio = float(corrected / n_gen) if n_gen > 0 else math.nan
    return ClosureResult(label, n_gen, n_selected, corrected, ratio, failed)


def run_closure_hybrid(
    input_dir: str | Path,
    *,
    samples: Sequence[str] = DEFAULT_CLOSURE_SAMPLES,
    selected_col: str = "Pri_assocPVPass",
    output_dir: str | Path | None = None,
    build_maps: bool = False,
    self_only: bool = False,
    n_min_fine: int = 30,
    n_min_coarse: int = 50,
) -> pd.DataFrame:
    """Run self/cross hybrid closure tests and write parquet/csv/manifest outputs."""
    input_path = Path(input_dir)
    output_path = ensure_dir(Path(output_dir) if output_dir is not None else input_path / "closure_hybrid")
    samples = tuple(samples)
    if not samples:
        raise ValueError("At least one sample is required")

    if build_maps:
        for sample in samples:
            build_post_acceptance_5d_map(
                input_path / sample,
                input_path / sample / "maps",
                event_end_step=selected_col,
            )

    maps: dict[str, HybridCorrectionMap] = {}
    for sample in samples:
        maps[sample] = load_hybrid_correction_map(
            input_path / sample,
            n_min_fine=n_min_fine,
            n_min_coarse=n_min_coarse,
        )

    gen, event = _load_sample_inputs(input_path, samples)
    merged = {sample: _merged_gen_events(gen[sample], event[sample]) for sample in samples}

    rows: list[dict] = []
    for sample in samples:
        result = _closure_result_from_merged_hybrid(sample, maps[sample], merged[sample], selected_col=selected_col)
        rows.append({
            "closure_type": "self",
            "map_sample": sample,
            "target_sample": sample,
            **result.to_dict(),
        })

    if not self_only:
        for map_sample in samples:
            for target_sample in samples:
                if map_sample == target_sample:
                    continue
                label = f"{map_sample}_on_{target_sample}"
                result = _closure_result_from_merged_hybrid(
                    label,
                    maps[map_sample],
                    merged[target_sample],
                    selected_col=selected_col,
                )
                rows.append({
                    "closure_type": "cross",
                    "map_sample": map_sample,
                    "target_sample": target_sample,
                    **result.to_dict(),
                })

    result_df = pd.DataFrame(rows)
    parquet_path = output_path / "closure_results.parquet"
    csv_path = output_path / "closure_results.csv"
    manifest_path = output_path / "closure_manifest.json"
    write_parquet(result_df, parquet_path)
    result_df.to_csv(csv_path, index=False)
    write_json(
        {
            "stage": "hybrid_closure",
            "input_dir": str(input_path.resolve()),
            "output_dir": str(output_path.resolve()),
            "samples": list(samples),
            "selected_col": selected_col,
            "build_maps": bool(build_maps),
            "self_only": bool(self_only),
            "n_min_fine": int(n_min_fine),
            "n_min_coarse": int(n_min_coarse),
            "artifacts": {
                "parquet": parquet_path.name,
                "csv": csv_path.name,
            },
            "n_rows": int(len(result_df)),
        },
        manifest_path,
    )
    return result_df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run efficiency self/cross closure tests (factorized or non-factorized)")
    parser.add_argument("--input-dir", required=True, help="Merged efficiency directory containing sample subdirectories")
    parser.add_argument("--samples", nargs="+", default=list(DEFAULT_CLOSURE_SAMPLES), help="Samples to include in the closure matrix")
    parser.add_argument("--selected-col", default="Pri_assocPVPass", help="Reco-selected event flag used as closure numerator")
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to <input-dir>/closure[_<maptype>]")
    parser.add_argument("--map-type", default="factorized", choices=["factorized", "correlated_3d", "correlated_5d", "hybrid"], help="Correction map type (default: factorized)")
    parser.add_argument("--denominator", default="absolute", choices=["absolute", "conditional"], help="Denominator for non-factorized maps")
    parser.add_argument("--build-maps", action="store_true", help="Build factorized maps before running closure (factorized mode only)")
    parser.add_argument("--self-only", action="store_true", help="Run only each sample's self-closure")
    parser.add_argument("--n-min-fine", type=int, default=30, help="Minimum MC total for fine factorized bins")
    parser.add_argument("--n-min-coarse", type=int, default=50, help="Minimum MC total for coarse factorized bins")
    parser.add_argument("--min-total-fine", type=int, default=0, help="Minimum MC total for fine 5D bin (non-factorized mode)")
    parser.add_argument("--min-total-coarse", type=int, default=0, help="Minimum MC total before falling back to 3D coarse (non-factorized mode)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    map_type = args.map_type
    is_factorized = map_type == "factorized"
    is_hybrid = map_type == "hybrid"

    if is_factorized:
        output_dir = Path(args.output_dir) if args.output_dir else Path(args.input_dir) / "closure"
    elif is_hybrid:
        output_dir = Path(args.output_dir) if args.output_dir else Path(args.input_dir) / "closure_hybrid"
    else:
        output_dir = Path(args.output_dir) if args.output_dir else Path(args.input_dir) / f"closure_{map_type}"

    mode_label = "Hybrid" if is_hybrid else ("Factorized" if is_factorized else f"Non-factorized {map_type}")
    print(f"=== {mode_label} closure run ===", flush=True)
    print(f"Input dir   : {args.input_dir}", flush=True)
    print(f"Map type    : {map_type}", flush=True)
    print(f"Samples     : {', '.join(args.samples)}", flush=True)
    print(f"Selected col: {args.selected_col}", flush=True)
    print(f"Output dir  : {output_dir}", flush=True)
    print(f"Self only   : {args.self_only}", flush=True)

    if is_hybrid:
        if hasattr(args, "build_maps"):
            print(f"Build maps  : {args.build_maps}", flush=True)
        result_df = run_closure_hybrid(
            args.input_dir,
            samples=args.samples,
            selected_col=args.selected_col,
            output_dir=output_dir,
            build_maps=args.build_maps,
            self_only=args.self_only,
            n_min_fine=args.n_min_fine,
            n_min_coarse=args.n_min_coarse,
        )
    elif is_factorized:
        if hasattr(args, "build_maps"):
            print(f"Build maps  : {args.build_maps}", flush=True)
        result_df = run_closure_matrix(
            args.input_dir,
            samples=args.samples,
            selected_col=args.selected_col,
            output_dir=output_dir,
            build_maps=args.build_maps,
            self_only=args.self_only,
            n_min_fine=args.n_min_fine,
            n_min_coarse=args.n_min_coarse,
        )
    else:
        result_df = run_closure_correlated(
            args.input_dir,
            samples=args.samples,
            selected_col=args.selected_col,
            map_type=map_type,
            denominator=args.denominator,
            output_dir=output_dir,
            self_only=args.self_only,
            min_total_fine=args.min_total_fine,
            min_total_coarse=args.min_total_coarse,
        )

    summary_cols = ["closure_type", "map_sample", "target_sample", "ratio", "n_failed_lookup"]
    print()
    print(result_df[summary_cols].to_string(index=False), flush=True)
    print(f"\nWrote: {output_dir / 'closure_results.parquet'}", flush=True)
    print(f"Wrote: {output_dir / 'closure_results.csv'}", flush=True)
    print(f"Wrote: {output_dir / 'closure_manifest.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

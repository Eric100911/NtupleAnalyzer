from __future__ import annotations

import json
import math
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Literal

import numpy as np
import pandas as pd
import uproot

from .corrections import (
    DEFAULT_EFFICIENCY_STEP,
    DEFAULT_MAP_TYPE,
    DEFAULT_WEIGHT_BRANCH,
    STATUS_INVALID_EFFICIENCY,
    STATUS_MISSING_BIN,
    STATUS_OK,
    EfficiencyCorrectionMap,
    FactorizedCorrectionMap,
    load_factorized_correction_map,
)
from .io import ensure_dir, write_json


DEFAULT_YIELD_SAMPLES = ("JJP_DPS1", "JJP_DPS2_CS", "JJP_DPS2_G", "JJP_SPS_CS", "JJP_SPS_G")
DEFAULT_NOMINAL_SAMPLE = "JJP_DPS1"
FIT_MASS_BRANCHES = ("sel_Jpsi_1_mass", "sel_Jpsi_2_mass", "sel_Phi_mass")
CORRECTION_PT_BRANCHES = ("sel_Jpsi_1_pt", "sel_Jpsi_2_pt", "sel_Phi_pt")
CORRECTION_FACTOR_BRANCHES = (
    "sel_Jpsi_1_pt",
    "sel_Jpsi_1_y",
    "sel_Jpsi_2_pt",
    "sel_Jpsi_2_y",
    "sel_Phi_pt",
    "sel_Phi_y",
)


@dataclass(frozen=True)
class YieldCorrectionResult:
    sample: str
    n_events: int
    n_ok: int
    n_missing: int
    n_invalid: int
    n_interpolated: int
    corrected_yield: float
    corrected_yield_err: float
    raw_yield: float
    raw_yield_err: float
    fit_nll: float
    mean_weight: float
    weighted_tree: str
    correction_mode: str = "legacy-correlated"
    mc_stat_unc: float = math.nan


@dataclass(frozen=True)
class YieldSystematicResult:
    nominal_sample: str
    raw_yield: float
    raw_yield_err: float
    per_sample: dict[str, YieldCorrectionResult]

    @property
    def nominal_corrected_yield(self) -> float:
        return self.per_sample[self.nominal_sample].corrected_yield

    @property
    def stat_unc(self) -> float:
        return self.per_sample[self.nominal_sample].corrected_yield_err

    @property
    def corrected_yields(self) -> np.ndarray:
        return np.asarray([item.corrected_yield for item in self.per_sample.values()], dtype=float)

    @property
    def envelope_half_width(self) -> float:
        values = self.corrected_yields
        return float((np.nanmax(values) - np.nanmin(values)) / 2.0) if values.size else math.nan

    @property
    def rms(self) -> float:
        values = self.corrected_yields
        return float(np.nanstd(values, ddof=0)) if values.size else math.nan

    @property
    def max_deviation(self) -> float:
        values = self.corrected_yields
        nominal = self.nominal_corrected_yield
        return float(np.nanmax(np.abs(values - nominal))) if values.size else math.nan

    @property
    def syst_unc(self) -> float:
        return self.envelope_half_width

    @property
    def total_unc(self) -> float:
        return float(math.sqrt(self.stat_unc**2 + self.syst_unc**2 + self.mc_stat_unc**2))

    @property
    def mc_stat_unc(self) -> float:
        value = self.per_sample[self.nominal_sample].mc_stat_unc
        return float(value) if math.isfinite(value) else 0.0

    def to_dict(self) -> dict:
        return {
            "nominal_sample": self.nominal_sample,
            "raw_yield": self.raw_yield,
            "raw_yield_err": self.raw_yield_err,
            "nominal_corrected_yield": self.nominal_corrected_yield,
            "stat_unc": self.stat_unc,
            "mc_stat_unc": self.mc_stat_unc,
            "syst_unc": self.syst_unc,
            "total_unc": self.total_unc,
            "envelope_half_width": self.envelope_half_width,
            "rms": self.rms,
            "max_deviation": self.max_deviation,
            "per_sample": {sample: asdict(result) for sample, result in self.per_sample.items()},
        }


def _efficiency_column(frame: pd.DataFrame) -> str:
    if "absolute_efficiency" in frame.columns:
        return "absolute_efficiency"
    if "efficiency" in frame.columns:
        return "efficiency"
    raise ValueError("Efficiency frame has neither absolute_efficiency nor efficiency")


def _weighted_average(rows: pd.DataFrame, eff_col: str) -> tuple[float, float, float]:
    weights = rows["total"].to_numpy(dtype=float) if "total" in rows.columns else np.ones(len(rows), dtype=float)
    efficiencies = rows[eff_col].to_numpy(dtype=float)
    valid = np.isfinite(efficiencies) & (efficiencies > 0.0) & np.isfinite(weights) & (weights > 0.0)
    if not np.any(valid):
        return math.nan, math.nan, math.nan
    eff = float(np.average(efficiencies[valid], weights=weights[valid]))
    err_low = math.nan
    err_high = math.nan
    if "err_low" in rows.columns:
        low = rows["err_low"].to_numpy(dtype=float)
        if np.any(np.isfinite(low[valid])):
            err_low = float(np.average(np.nan_to_num(low[valid], nan=0.0), weights=weights[valid]))
    if "err_high" in rows.columns:
        high = rows["err_high"].to_numpy(dtype=float)
        if np.any(np.isfinite(high[valid])):
            err_high = float(np.average(np.nan_to_num(high[valid], nan=0.0), weights=weights[valid]))
    return eff, err_low, err_high


def fill_zero_efficiency_bins(frame: pd.DataFrame, *, min_total: int = 10) -> tuple[pd.DataFrame, int]:
    """Fill zero/low-stat correlated 3D bins using expanding nearest neighbors."""
    filled = frame.copy()
    if filled.empty or "map_type" not in filled.columns:
        return filled, 0
    required = {"x_bin", "y_bin", "z_bin", "total", "map_type", "step"}
    if not required.issubset(filled.columns):
        return filled, 0

    eff_col = _efficiency_column(filled)
    filled["filled_by_interpolation"] = False
    n_filled = 0
    group_keys = ["map_type", "step"]
    if "object" in filled.columns:
        group_keys.append("object")

    for _, group in filled.loc[filled["map_type"] == "correlated_3d"].groupby(group_keys, dropna=False):
        candidate_mask = (
            ~np.isfinite(group[eff_col].to_numpy(dtype=float))
            | (group[eff_col].to_numpy(dtype=float) <= 0.0)
            | (group["total"].to_numpy(dtype=float) < float(min_total))
        )
        bad_indices = list(group.index[candidate_mask])
        if not bad_indices:
            continue
        max_radius = int(
            max(
                group["x_bin"].max() - group["x_bin"].min(),
                group["y_bin"].max() - group["y_bin"].min(),
                group["z_bin"].max() - group["z_bin"].min(),
                1,
            )
        )
        for idx in bad_indices:
            row = filled.loc[idx]
            replacement = (math.nan, math.nan, math.nan)
            for radius in range(1, max_radius + 1):
                neighbors = group.loc[
                    (
                        (np.abs(group["x_bin"] - int(row["x_bin"])) <= radius)
                        & (np.abs(group["y_bin"] - int(row["y_bin"])) <= radius)
                        & (np.abs(group["z_bin"] - int(row["z_bin"])) <= radius)
                    )
                    & ~(
                        (group["x_bin"] == int(row["x_bin"]))
                        & (group["y_bin"] == int(row["y_bin"]))
                        & (group["z_bin"] == int(row["z_bin"]))
                    )
                ]
                if neighbors.empty:
                    continue
                valid_neighbors = neighbors.loc[
                    np.isfinite(neighbors[eff_col].to_numpy(dtype=float))
                    & (neighbors[eff_col].to_numpy(dtype=float) > 0.0)
                    & (neighbors["total"].to_numpy(dtype=float) >= float(min_total))
                ]
                if valid_neighbors.empty:
                    continue
                replacement = _weighted_average(valid_neighbors, eff_col)
                break
            eff, err_low, err_high = replacement
            if not math.isfinite(eff) or eff <= 0.0:
                continue
            filled.at[idx, eff_col] = eff
            if eff_col != "efficiency" and "efficiency" in filled.columns:
                filled.at[idx, "efficiency"] = eff
            if "absolute_efficiency" in filled.columns:
                filled.at[idx, "absolute_efficiency"] = eff
            if "err_low" in filled.columns:
                filled.at[idx, "err_low"] = err_low
            if "err_high" in filled.columns:
                filled.at[idx, "err_high"] = err_high
            if "err_sym" in filled.columns:
                filled.at[idx, "err_sym"] = max(err_low, err_high) if math.isfinite(err_low) and math.isfinite(err_high) else math.nan
            filled.at[idx, "filled_by_interpolation"] = True
            n_filled += 1
    return filled, n_filled


def fold_signed_y_bins(frame: pd.DataFrame, *, min_total: int = 10) -> pd.DataFrame:
    """Fold low-stat negative-y object_2d bins to the matching positive-|y| bin."""
    folded = frame.copy()
    if folded.empty or "map_type" not in folded.columns:
        return folded
    required = {"map_type", "x_bin", "y_min", "y_max", "total"}
    if not required.issubset(folded.columns):
        return folded
    eff_col = _efficiency_column(folded)
    folded["folded_from_positive_y"] = False
    object_df = folded.loc[folded["map_type"] == "object_2d"]
    group_keys = ["map_type", "step", "object", "x_bin"] if "object" in folded.columns else ["map_type", "step", "x_bin"]
    for _, group in object_df.groupby(group_keys, dropna=False):
        for idx, row in group.iterrows():
            if float(row["y_max"]) > 0.0 or float(row["total"]) >= float(min_total):
                continue
            mirror = group.loc[
                np.isclose(group["y_min"].to_numpy(dtype=float), abs(float(row["y_max"])))
                & np.isclose(group["y_max"].to_numpy(dtype=float), abs(float(row["y_min"])))
            ]
            if mirror.empty:
                continue
            source = mirror.iloc[0]
            source_eff = float(source[eff_col])
            if not math.isfinite(source_eff) or source_eff <= 0.0:
                continue
            folded.at[idx, eff_col] = source_eff
            if eff_col != "efficiency" and "efficiency" in folded.columns:
                folded.at[idx, "efficiency"] = source_eff
            if "absolute_efficiency" in folded.columns:
                folded.at[idx, "absolute_efficiency"] = source_eff
            for col in ("err_low", "err_high", "err_sym"):
                if col in folded.columns and col in source.index:
                    folded.at[idx, col] = source[col]
            folded.at[idx, "folded_from_positive_y"] = True
    return folded


def load_filled_correction_map(
    map_path: Path,
    *,
    step: str,
    map_type: str,
    denominator: Literal["absolute", "conditional"],
    min_total: int,
) -> tuple[EfficiencyCorrectionMap, int]:
    frame = pd.read_parquet(map_path)
    frame = fold_signed_y_bins(frame, min_total=min_total)
    frame, n_filled = fill_zero_efficiency_bins(frame, min_total=min_total)
    return EfficiencyCorrectionMap(frame, source=map_path, step=step, map_type=map_type, denominator=denominator), n_filled


def build_weighted_mini_tree(
    input_file: str | Path,
    output_file: str | Path,
    correction_map: EfficiencyCorrectionMap,
    *,
    tree_name: str = "selected",
    on_missing: Literal["error", "drop"] = "error",
    status_callback: Callable[[str], None] | None = None,
    status_interval: int = 100_000,
) -> tuple[int, int, int, int, float]:
    input_path = Path(input_file)
    output_path = Path(output_file)
    ensure_dir(output_path.parent)
    branches = FIT_MASS_BRANCHES + CORRECTION_PT_BRANCHES
    with uproot.open(input_path) as root_file:
        if tree_name not in root_file:
            raise RuntimeError(f"Input tree {tree_name!r} not found in {input_path}")
        tree = root_file[tree_name]
        missing = [branch for branch in branches if branch not in tree.keys()]
        if missing:
            raise RuntimeError(f"Input tree is missing branch(es): {', '.join(missing)}")
        arrays = tree.arrays(branches, library="np")

    n_total = len(arrays[FIT_MASS_BRANCHES[0]])
    out_arrays = {branch: np.asarray(arrays[branch]) for branch in FIT_MASS_BRANCHES}
    out_arrays.update({branch: np.asarray(arrays[branch]) for branch in CORRECTION_PT_BRANCHES})
    weights = np.full(n_total, np.nan, dtype=np.float64)
    efficiencies = np.full(n_total, np.nan, dtype=np.float64)
    status = np.full(n_total, STATUS_MISSING_BIN, dtype=np.int32)
    x_bin = np.full(n_total, -1, dtype=np.int32)
    y_bin = np.full(n_total, -1, dtype=np.int32)
    z_bin = np.full(n_total, -1, dtype=np.int32)

    n_ok = 0
    n_missing = 0
    n_invalid = 0
    keep_mask = np.ones(n_total, dtype=bool)
    for idx in range(n_total):
        if status_callback is not None and status_interval > 0 and idx > 0 and idx % status_interval == 0:
            status_callback(f"processed {idx}/{n_total} selected events")
        correction = correction_map.lookup(
            float(arrays["sel_Jpsi_1_pt"][idx]),
            float(arrays["sel_Jpsi_2_pt"][idx]),
            float(arrays["sel_Phi_pt"][idx]),
        )
        status[idx] = correction.status
        x_bin[idx] = correction.x_bin
        y_bin[idx] = correction.y_bin
        z_bin[idx] = correction.z_bin
        efficiencies[idx] = correction.efficiency
        weights[idx] = correction.weight
        if correction.status == STATUS_OK:
            n_ok += 1
        elif correction.status == STATUS_MISSING_BIN:
            n_missing += 1
            keep_mask[idx] = on_missing != "drop"
        elif correction.status == STATUS_INVALID_EFFICIENCY:
            n_invalid += 1
            keep_mask[idx] = on_missing != "drop"

    if on_missing == "error" and (n_missing or n_invalid):
        raise RuntimeError(f"Efficiency lookup failed: missing={n_missing}, invalid={n_invalid}")
    if on_missing not in {"error", "drop"}:
        raise ValueError(f"Unsupported on_missing mode: {on_missing}")

    out_arrays[DEFAULT_WEIGHT_BRANCH] = weights
    out_arrays["effcorr_efficiency"] = efficiencies
    out_arrays["effcorr_status"] = status
    out_arrays["effcorr_x_bin"] = x_bin
    out_arrays["effcorr_y_bin"] = y_bin
    out_arrays["effcorr_z_bin"] = z_bin
    if on_missing == "drop":
        out_arrays = {key: value[keep_mask] for key, value in out_arrays.items()}
    with uproot.recreate(output_path) as root_file:
        root_file[tree_name] = out_arrays
    mean_weight = float(np.nanmean(weights[status == STATUS_OK])) if n_ok else math.nan
    return n_total, n_ok, n_missing, n_invalid, mean_weight


def build_factorized_weighted_mini_tree(
    input_file: str | Path,
    output_file: str | Path,
    correction_map: FactorizedCorrectionMap,
    *,
    tree_name: str = "selected",
    on_missing: Literal["error", "drop"] = "error",
    status_callback: Callable[[str], None] | None = None,
    status_interval: int = 100_000,
) -> tuple[int, int, int, int, int, float, float]:
    input_path = Path(input_file)
    output_path = Path(output_file)
    ensure_dir(output_path.parent)
    branches = FIT_MASS_BRANCHES + CORRECTION_FACTOR_BRANCHES
    with uproot.open(input_path) as root_file:
        if tree_name not in root_file:
            raise RuntimeError(f"Input tree {tree_name!r} not found in {input_path}")
        tree = root_file[tree_name]
        missing = [branch for branch in branches if branch not in tree.keys()]
        if missing:
            raise RuntimeError(f"Input tree is missing branch(es): {', '.join(missing)}")
        arrays = tree.arrays(branches, library="np")

    n_total = len(arrays[FIT_MASS_BRANCHES[0]])
    out_arrays = {branch: np.asarray(arrays[branch]) for branch in FIT_MASS_BRANCHES}
    out_arrays.update({branch: np.asarray(arrays[branch]) for branch in CORRECTION_FACTOR_BRANCHES})
    weights = np.full(n_total, np.nan, dtype=np.float64)
    weight_err = np.full(n_total, np.nan, dtype=np.float64)
    efficiencies = np.full(n_total, np.nan, dtype=np.float64)
    status = np.full(n_total, STATUS_MISSING_BIN, dtype=np.int32)

    n_ok = 0
    n_missing = 0
    n_invalid = 0
    n_fallback_components = 0
    keep_mask = np.ones(n_total, dtype=bool)
    bin_uncertainty_terms: dict[tuple[str, str, int, int, int], tuple[float, float]] = {}
    for idx in range(n_total):
        if status_callback is not None and status_interval > 0 and idx > 0 and idx % status_interval == 0:
            status_callback(f"processed {idx}/{n_total} selected events")
        correction = correction_map.lookup(
            jpsi1_pt=float(arrays["sel_Jpsi_1_pt"][idx]),
            jpsi1_y=float(arrays["sel_Jpsi_1_y"][idx]),
            jpsi2_pt=float(arrays["sel_Jpsi_2_pt"][idx]),
            jpsi2_y=float(arrays["sel_Jpsi_2_y"][idx]),
            phi_pt=float(arrays["sel_Phi_pt"][idx]),
            phi_y=float(arrays["sel_Phi_y"][idx]),
        )
        status[idx] = correction.status
        efficiencies[idx] = correction.efficiency
        weights[idx] = correction.weight
        weight_err[idx] = correction.err_sym
        if correction.status == STATUS_OK:
            n_ok += 1
            for component in correction.components:
                if component.fallback_level != "fine":
                    n_fallback_components += 1
                if math.isfinite(component.err_sym) and component.efficiency > 0.0:
                    previous_sum, err = bin_uncertainty_terms.get(component.bin_key, (0.0, component.err_sym))
                    bin_uncertainty_terms[component.bin_key] = (previous_sum + correction.weight / component.efficiency, err)
        elif correction.status == STATUS_MISSING_BIN:
            n_missing += 1
            keep_mask[idx] = on_missing != "drop"
        elif correction.status == STATUS_INVALID_EFFICIENCY:
            n_invalid += 1
            keep_mask[idx] = on_missing != "drop"

    if on_missing == "error" and (n_missing or n_invalid):
        raise RuntimeError(f"Factorized efficiency lookup failed: missing={n_missing}, invalid={n_invalid}")
    if on_missing not in {"error", "drop"}:
        raise ValueError(f"Unsupported on_missing mode: {on_missing}")

    mc_stat_var = sum((sum_w_over_eff * err) ** 2 for sum_w_over_eff, err in bin_uncertainty_terms.values())
    out_arrays[DEFAULT_WEIGHT_BRANCH] = weights
    out_arrays["effcorr_weight_err"] = weight_err
    out_arrays["effcorr_efficiency"] = efficiencies
    out_arrays["effcorr_status"] = status
    if on_missing == "drop":
        out_arrays = {key: value[keep_mask] for key, value in out_arrays.items()}
    with uproot.recreate(output_path) as root_file:
        root_file[tree_name] = out_arrays
    mean_weight = float(np.nanmean(weights[status == STATUS_OK])) if n_ok else math.nan
    return n_total, n_ok, n_missing, n_invalid, n_fallback_components, mean_weight, float(math.sqrt(mc_stat_var))


def run_weighted_yield_fit(
    input_file: str | Path,
    *,
    weight_branch: str | None = None,
    channel: str = "JJP",
    dataset: str = "data",
    jobs: int = 4,
) -> tuple[float, float, float, int]:
    if channel != "JJP":
        raise ValueError("Yield correction currently supports only channel='JJP'")
    from fit_splot import run_jjp_fit

    payload = run_jjp_fit(
        input_file,
        weight_branch=weight_branch,
        dataset=dataset,
        jobs=jobs,
        compute_significance_result=False,
    )
    return payload["yield"], payload["yield_err"], payload["fit_nll"], payload["n_events"]


def compute_efficiency_corrected_yield(
    data_input_file: str | Path,
    efficiency_dir: str | Path,
    *,
    samples: tuple[str, ...] | list[str] = DEFAULT_YIELD_SAMPLES,
    nominal_sample: str = DEFAULT_NOMINAL_SAMPLE,
    step: str = DEFAULT_EFFICIENCY_STEP,
    map_type: str = DEFAULT_MAP_TYPE,
    denominator: Literal["absolute", "conditional"] = "absolute",
    min_total: int = 10,
    correction_mode: Literal["factorized", "legacy-correlated"] = "factorized",
    n_min_fine: int = 30,
    n_min_coarse: int = 50,
    on_missing: Literal["error", "drop"] = "error",
    temp_dir: str | Path | None = None,
    jobs: int = 4,
    status_callback: Callable[[str], None] | None = None,
) -> YieldSystematicResult:
    data_input_file = Path(data_input_file)
    efficiency_dir = Path(efficiency_dir)
    samples = tuple(samples)
    if nominal_sample not in samples:
        raise ValueError(f"Nominal sample {nominal_sample!r} is not in --samples")

    def status(message: str) -> None:
        if status_callback is not None:
            status_callback(message)

    status(f"Fitting raw unweighted yield from {data_input_file}")
    raw_yield, raw_yield_err, _, _ = run_weighted_yield_fit(data_input_file, weight_branch=None, jobs=jobs)
    status(f"Raw fit complete: yield={raw_yield:.1f} +/- {raw_yield_err:.1f}")
    temp_context = tempfile.TemporaryDirectory(prefix="yieldcorr_") if temp_dir is None else None
    work_dir = Path(temp_context.name) if temp_context is not None else ensure_dir(Path(temp_dir))
    status(f"Weighted intermediate trees: {work_dir}")
    per_sample: dict[str, YieldCorrectionResult] = {}
    try:
        for sample in samples:
            weighted_tree = work_dir / f"{sample}_weighted.root"
            mc_stat_unc = math.nan
            if correction_mode == "factorized":
                sample_dir = efficiency_dir / sample
                status(f"[{sample}] loading factorized correction maps: {sample_dir / 'maps'}")
                factorized_map = load_factorized_correction_map(
                    sample_dir,
                    n_min_fine=n_min_fine,
                    n_min_coarse=n_min_coarse,
                )
                status(f"[{sample}] building factorized weighted mini tree: {weighted_tree}")
                n_events, n_ok, n_missing, n_invalid, n_interpolated, mean_weight, mc_stat_unc = build_factorized_weighted_mini_tree(
                    data_input_file,
                    weighted_tree,
                    factorized_map,
                    on_missing=on_missing,
                    status_callback=lambda message, sample=sample: status(f"[{sample}] {message}"),
                )
            elif correction_mode == "legacy-correlated":
                map_path = efficiency_dir / sample / "efficiency_maps.parquet"
                if not map_path.exists():
                    raise FileNotFoundError(f"Efficiency map not found for {sample}: {map_path}")
                status(f"[{sample}] loading correction map: {map_path}")
                correction_map, n_interpolated = load_filled_correction_map(
                    map_path,
                    step=step,
                    map_type=map_type,
                    denominator=denominator,
                    min_total=min_total,
                )
                status(f"[{sample}] building weighted mini tree: {weighted_tree}")
                n_events, n_ok, n_missing, n_invalid, mean_weight = build_weighted_mini_tree(
                    data_input_file,
                    weighted_tree,
                    correction_map,
                    on_missing=on_missing,
                    status_callback=lambda message, sample=sample: status(f"[{sample}] {message}"),
                )
            else:
                raise ValueError(f"Unsupported correction_mode: {correction_mode}")
            status(
                f"[{sample}] lookup complete: events={n_events}, ok={n_ok}, "
                f"missing={n_missing}, invalid={n_invalid}, fallback_or_interpolated={n_interpolated}"
            )
            status(f"[{sample}] fitting weighted yield")
            corrected_yield, corrected_yield_err, fit_nll, _ = run_weighted_yield_fit(
                weighted_tree,
                weight_branch=DEFAULT_WEIGHT_BRANCH,
                jobs=jobs,
            )
            status(f"[{sample}] fit complete: yield={corrected_yield:.1f} +/- {corrected_yield_err:.1f}")
            per_sample[sample] = YieldCorrectionResult(
                sample=sample,
                n_events=n_events,
                n_ok=n_ok,
                n_missing=n_missing,
                n_invalid=n_invalid,
                n_interpolated=n_interpolated,
                corrected_yield=corrected_yield,
                corrected_yield_err=corrected_yield_err,
                raw_yield=raw_yield,
                raw_yield_err=raw_yield_err,
                fit_nll=fit_nll,
                mean_weight=mean_weight,
                weighted_tree=str(weighted_tree),
                correction_mode=correction_mode,
                mc_stat_unc=mc_stat_unc,
            )
        return YieldSystematicResult(
            nominal_sample=nominal_sample,
            raw_yield=raw_yield,
            raw_yield_err=raw_yield_err,
            per_sample=per_sample,
        )
    finally:
        if temp_context is not None:
            temp_context.cleanup()


def write_yield_result_json(result: YieldSystematicResult, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    write_json(result.to_dict(), output_path)
    return output_path


def yield_result_json(result: YieldSystematicResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True)

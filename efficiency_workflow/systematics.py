from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from .efficiency import EfficiencyBinning

if TYPE_CHECKING:
    from .products import DerivedSampleProducts


@dataclass(frozen=True)
class SystematicUncertaintyProduct:
    product_type: str
    systematics_df: pd.DataFrame
    per_sample_dfs: dict[str, pd.DataFrame]


@dataclass(frozen=True)
class SystematicResults:
    output_dir: Path
    nominal_sample: str
    products: dict[str, SystematicUncertaintyProduct]
    systematic_summary_df: pd.DataFrame


_METRIC_COLUMNS = {
    "sample",
    "total",
    "passed",
    "efficiency",
    "err_low",
    "err_high",
    "err_sym",
    "previous_step",
    "conditional_total",
    "conditional_passed",
    "absolute_total",
    "absolute_passed",
    "absolute_efficiency",
    "quantity",
}


def _sample_alias(sample: str) -> str:
    alias = sample.upper()
    if alias.startswith("JJP_"):
        alias = alias[4:]
    return alias.replace("_", "")


def _resolve_nominal_sample(samples: list[str], nominal_sample: str) -> str:
    if nominal_sample in samples:
        return nominal_sample
    nominal_alias = _sample_alias(nominal_sample)
    matches = [sample for sample in samples if _sample_alias(sample) == nominal_alias]
    if len(matches) == 1:
        return matches[0]
    raise KeyError(
        f"Nominal sample {nominal_sample!r} not found. Available samples: {', '.join(samples)}"
    )


def _metric_column(prefix: str, sample: str) -> str:
    return f"{prefix}_{sample}"


def _is_metric_column(column: str) -> bool:
    return (
        column in _METRIC_COLUMNS
        or column.startswith("err_")
        or column.startswith("conditional_")
        or column.startswith("absolute_")
    )


def _bin_key_columns(df: pd.DataFrame) -> list[str]:
    return [column for column in df.columns if not _is_metric_column(str(column))]


def _compute_envelope_stats(eff_values: list[float], nominal_value: float) -> dict[str, float]:
    if not eff_values:
        return {
            "eff_min": math.nan,
            "eff_max": math.nan,
            "eff_median": math.nan,
            "envelope_half_width": math.nan,
            "rms": math.nan,
            "max_deviation_from_nominal": math.nan,
        }
    arr = np.asarray(eff_values, dtype=float)
    return {
        "eff_min": float(np.min(arr)),
        "eff_max": float(np.max(arr)),
        "eff_median": float(np.median(arr)),
        "envelope_half_width": float((np.max(arr) - np.min(arr)) / 2.0),
        "rms": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "max_deviation_from_nominal": float(np.max(np.abs(arr - nominal_value))),
    }


def _iter_groups(frame: pd.DataFrame, group_cols: list[str]):
    if not group_cols:
        yield (), frame
        return
    yield from frame.groupby(group_cols, dropna=False)


def _warn_low_stats(product_type: str, sample: str, frame: pd.DataFrame, min_total: int) -> None:
    if frame.empty or "total" not in frame.columns:
        return
    low_count = int((frame["total"].fillna(0).astype(int) < int(min_total)).sum())
    very_low_count = int((frame["total"].fillna(0).astype(int) < 10).sum())
    if low_count:
        warnings.warn(
            f"{product_type}: {sample} has {low_count} bin(s) with total < {min_total}",
            RuntimeWarning,
            stacklevel=2,
        )
    if very_low_count:
        warnings.warn(
            f"{product_type}: {sample} has {very_low_count} bin(s) with total < 10",
            RuntimeWarning,
            stacklevel=2,
        )


def _compare_single_product_type(
    product_type: str,
    samples_dfs: dict[str, pd.DataFrame],
    nominal_sample: str,
    min_total: int,
    min_n_samples: int,
    eff_column: str = "efficiency",
) -> SystematicUncertaintyProduct:
    nonempty = {sample: frame.copy() for sample, frame in samples_dfs.items() if not frame.empty}
    if not nonempty:
        return SystematicUncertaintyProduct(product_type, pd.DataFrame(), {})

    resolved_nominal = _resolve_nominal_sample(list(nonempty), nominal_sample)
    frames: list[pd.DataFrame] = []
    for sample, frame in nonempty.items():
        if eff_column not in frame.columns:
            continue
        _warn_low_stats(product_type, sample, frame, min_total)
        tagged = frame.copy()
        tagged["sample"] = sample
        frames.append(tagged)
    if not frames:
        return SystematicUncertaintyProduct(product_type, pd.DataFrame(), nonempty)

    combined = pd.concat(frames, ignore_index=True, sort=False)
    group_cols = _bin_key_columns(combined)
    rows: list[dict[str, object]] = []

    for keys, group in _iter_groups(combined, group_cols):
        key_values = keys if isinstance(keys, tuple) else (keys,)
        row: dict[str, object] = dict(zip(group_cols, key_values))
        row["product_type"] = product_type
        row["nominal_sample"] = resolved_nominal

        by_sample = {
            str(sample): sample_group.iloc[0]
            for sample, sample_group in group.groupby("sample", dropna=False)
        }
        nominal_row = by_sample.get(resolved_nominal)
        if nominal_row is None:
            continue

        nominal_value = float(nominal_row.get(eff_column, math.nan))
        if not math.isfinite(nominal_value):
            continue

        valid_values: list[float] = []
        pull_values: list[float] = []
        n_low_stats = 0
        nominal_total = int(nominal_row.get("total", 0) or 0)
        nominal_passed = int(nominal_row.get("passed", 0) or 0)
        nominal_err = float(nominal_row.get("err_sym", math.nan))

        row["total"] = nominal_total
        row["passed"] = nominal_passed
        row["total_nominal"] = nominal_total
        row["passed_nominal"] = nominal_passed
        row["nominal_eff"] = nominal_value
        row["nominal_err_sym"] = nominal_err
        row["low_stat_bin_nominal"] = bool(nominal_total < int(min_total))

        for sample in nonempty:
            sample_row = by_sample.get(sample)
            eff_value = math.nan
            ratio_value = math.nan
            pull_value = math.nan
            total_value = 0
            passed_value = 0
            err_value = math.nan

            if sample_row is not None:
                eff_value = float(sample_row.get(eff_column, math.nan))
                total_value = int(sample_row.get("total", 0) or 0)
                passed_value = int(sample_row.get("passed", 0) or 0)
                err_value = float(sample_row.get("err_sym", math.nan))
                if total_value < int(min_total):
                    n_low_stats += 1
                if math.isfinite(eff_value):
                    valid_values.append(eff_value)
                    if nominal_value != 0.0:
                        ratio_value = eff_value / nominal_value
                    if sample != resolved_nominal:
                        variance = 0.0
                        if math.isfinite(err_value):
                            variance += err_value * err_value
                        if math.isfinite(nominal_err):
                            variance += nominal_err * nominal_err
                        if variance > 0.0:
                            pull_value = (eff_value - nominal_value) / math.sqrt(variance)
                            pull_values.append(pull_value)

            row[_metric_column("eff", sample)] = eff_value
            row[_metric_column("ratio", sample)] = ratio_value
            row[_metric_column("pull", sample)] = pull_value
            row[_metric_column("total", sample)] = total_value
            row[_metric_column("passed", sample)] = passed_value
            row[_metric_column("err_sym", sample)] = err_value

        if len(valid_values) < int(min_n_samples):
            continue

        row["n_samples"] = int(len(by_sample))
        row["n_valid"] = int(len(valid_values))
        row["n_low_stats"] = int(n_low_stats)
        row["max_abs_pull"] = (
            float(np.nanmax(np.abs(np.asarray(pull_values, dtype=float)))) if pull_values else math.nan
        )
        row.update(_compute_envelope_stats(valid_values, nominal_value))
        rows.append(row)

    return SystematicUncertaintyProduct(
        product_type=product_type,
        systematics_df=pd.DataFrame(rows),
        per_sample_dfs=nonempty,
    )


def _product_frames_by_type(
    products_by_sample: dict[str, "DerivedSampleProducts"],
) -> dict[str, dict[str, pd.DataFrame]]:
    by_type: dict[str, dict[str, pd.DataFrame]] = {
        "counts": {},
        "acceptance": {},
        "conditional": {},
        "per_object_acceptance": {},
        "stacked_jpsi_acceptance": {},
        "stacked_jpsi_efficiency": {},
    }
    for sample, products in products_by_sample.items():
        by_type["counts"][sample] = products.counts_df
        by_type["acceptance"][sample] = products.acceptance_df
        by_type["conditional"][sample] = products.conditional_df
        by_type["per_object_acceptance"][sample] = products.per_object_acceptance_df
        by_type["stacked_jpsi_acceptance"][sample] = products.stacked_jpsi_acceptance_df
        by_type["stacked_jpsi_efficiency"][sample] = products.stacked_jpsi_efficiency_df
        for step, frame in products.pair_level_dfs.items():
            by_type.setdefault(f"pair_level_{step}", {})[sample] = frame
    return by_type


def build_subprocess_systematics_summary(
    products_by_sample: dict[str, "DerivedSampleProducts"],
    nominal_sample: str = "DPS_1",
    min_total: int = 1,
    min_n_samples: int = 2,
) -> SystematicResults:
    if not products_by_sample:
        raise RuntimeError("No derived sample products were provided for systematic comparison")

    resolved_nominal = _resolve_nominal_sample(list(products_by_sample), nominal_sample)
    products: dict[str, SystematicUncertaintyProduct] = {}
    for product_type, samples_dfs in _product_frames_by_type(products_by_sample).items():
        product = _compare_single_product_type(
            product_type,
            samples_dfs,
            resolved_nominal,
            min_total,
            min_n_samples,
        )
        if not product.systematics_df.empty:
            products[product_type] = product

    summary = (
        pd.concat((product.systematics_df for product in products.values()), ignore_index=True, sort=False)
        if products
        else pd.DataFrame()
    )
    return SystematicResults(
        output_dir=Path("."),
        nominal_sample=resolved_nominal,
        products=products,
        systematic_summary_df=summary,
    )


def load_derived_products_for_systematics(
    input_dir: Path,
    binning: EfficiencyBinning | None = None,
) -> dict[str, "DerivedSampleProducts"]:
    from .products import build_derived_sample_products, discover_merged_samples

    products: dict[str, DerivedSampleProducts] = {}
    for sample_dir in discover_merged_samples(input_dir):
        try:
            products[sample_dir.name] = build_derived_sample_products(
                sample_dir,
                input_dir,
                binning=binning,
            )
        except Exception as exc:
            warnings.warn(
                f"Skipping {sample_dir.name}: failed to build derived products ({exc})",
                RuntimeWarning,
                stacklevel=2,
            )
    return products

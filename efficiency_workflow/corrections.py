from __future__ import annotations

import array
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from ntuple_pipeline_common import ensure_parent_dir


DEFAULT_EFFICIENCY_STEP = "Pri_assocPVPass"
DEFAULT_MAP_TYPE = "correlated_3d"
DEFAULT_WEIGHT_BRANCH = "effcorr_weight"

STATUS_OK = 0
STATUS_MISSING_BIN = 1
STATUS_INVALID_EFFICIENCY = 2


@dataclass(frozen=True)
class EfficiencyCorrection:
    efficiency: float
    weight: float
    err_low: float
    err_high: float
    x_bin: int
    y_bin: int
    z_bin: int
    status: int
    u_bin: int = -1
    v_bin: int = -1


@dataclass(frozen=True)
class CorrectionSummary:
    entries: int
    ok: int
    missing_bin: int
    invalid_efficiency: int
    min_efficiency: float
    max_efficiency: float
    mean_weight: float


@dataclass(frozen=True)
class FactorizedComponentCorrection:
    name: str
    factor_name: str
    efficiency: float
    err_sym: float
    total: int
    passed: int
    fallback_level: str
    x_bin: int
    y_bin: int
    z_bin: int
    status: int

    @property
    def bin_key(self) -> tuple[str, str, int, int, int]:
        return (self.name, self.fallback_level, self.x_bin, self.y_bin, self.z_bin)


@dataclass(frozen=True)
class FactorizedCorrection:
    efficiency: float
    weight: float
    err_sym: float
    status: int
    components: tuple[FactorizedComponentCorrection, ...]


@dataclass(frozen=True)
class FactorizedCorrectionArrays:
    efficiency: np.ndarray
    weight: np.ndarray
    weight_err: np.ndarray
    status: np.ndarray
    fallback_components: np.ndarray
    mc_stat_unc: float


@dataclass(frozen=True)
class _FactorizedComponentArrays:
    name: str
    factor_name: str
    efficiency: np.ndarray
    err_sym: np.ndarray
    status: np.ndarray
    fallback_level: np.ndarray
    row_index: np.ndarray
    x_bin: np.ndarray
    y_bin: np.ndarray
    z_bin: np.ndarray


class EfficiencyCorrectionMap:
    """Non-factorized efficiency correction with hierarchical fallback levels.

    Each level corresponds to a different binning granularity.  During lookup
    the finest level is tried first; if the matching bin has too few MC events
    (total < level_min_total) the next coarser level is used as fallback.

    Typical configuration for the 5D non-factorized approach:
      - fine:   correlated_5d  (jpsi_lead_pt, jpsi_sublead_pt, phi_pt,
                                 jpsi_lead_abs_y, jpsi_sublead_abs_y)
      - coarse: correlated_3d  (jpsi_lead_pt, jpsi_sublead_pt, phi_pt)
      - inclusive: inclusive   (no binning)

    The coarse and inclusive levels are optional.  When omitted the map
    behaves identically to the original single-level implementation.
    """

    def __init__(
        self,
        frame: pd.DataFrame,
        *,
        source: Path,
        step: str,
        map_type: str = DEFAULT_MAP_TYPE,
        denominator: Literal["absolute", "conditional"] = "absolute",
        fallback_frames: list[pd.DataFrame] | None = None,
        fallback_min_total: list[int] | None = None,
        fine_min_total: int = 0,
    ) -> None:
        self.source = source
        self.step = step
        self.map_type = map_type
        self.denominator = denominator

        # --- primary (finest) level ---
        self.frame = self._prepare_frame(frame, step=step, map_type=map_type, denominator=denominator)
        self._levels: list[dict[str, Any]] = []
        self._add_level(self.frame, min_total=fine_min_total, level_name="fine")

        # --- optional fallback levels ---
        if fallback_frames is not None:
            for i, fb_frame in enumerate(fallback_frames):
                fb_map_type = fb_frame["map_type"].iloc[0] if "map_type" in fb_frame.columns else f"fallback_{i}"
                prepared = self._prepare_frame(fb_frame, step=step, map_type=fb_map_type, denominator=denominator)
                min_tot = fallback_min_total[i] if fallback_min_total and i < len(fallback_min_total) else 0
                self._add_level(prepared, min_total=min_tot, level_name=("coarse" if i == 0 else f"fallback_{i}"))

        # expose axis arrays from the primary level for backward compatibility
        self._refresh_primary_attrs()

    def _refresh_primary_attrs(self) -> None:
        """Sync the convenience attributes from the first (finest) level."""
        primary = self._levels[0]
        self.x_min = primary["x_min"]
        self.x_max = primary["x_max"]
        self.y_min = primary["y_min"]
        self.y_max = primary["y_max"]
        self.z_min = primary["z_min"]
        self.z_max = primary["z_max"]
        self.efficiency = primary["efficiency"]
        self.err_low = primary["err_low"]
        self.err_high = primary["err_high"]
        self.x_bin = primary["x_bin"]
        self.y_bin = primary["y_bin"]
        self.z_bin = primary["z_bin"]

    def _add_level(self, prepared: pd.DataFrame, *, min_total: int, level_name: str) -> None:
        """Extract axis arrays from a prepared frame and register as a fallback level."""
        arrays: dict[str, np.ndarray] = {}
        for ax in ("x", "y", "z"):
            arrays[f"{ax}_min"] = prepared[f"{ax}_min"].to_numpy(dtype=float)
            arrays[f"{ax}_max"] = prepared[f"{ax}_max"].to_numpy(dtype=float)
            arrays[f"{ax}_bin"] = prepared[f"{ax}_bin"].to_numpy(dtype=int)
        has_u = "u_min" in prepared.columns
        has_v = "v_min" in prepared.columns
        for ax in ("u", "v"):
            if f"{ax}_min" in prepared.columns:
                arrays[f"{ax}_min"] = prepared[f"{ax}_min"].to_numpy(dtype=float)
                arrays[f"{ax}_max"] = prepared[f"{ax}_max"].to_numpy(dtype=float)
                arrays[f"{ax}_bin"] = prepared[f"{ax}_bin"].to_numpy(dtype=int)
            else:
                arrays[f"{ax}_min"] = np.array([])
                arrays[f"{ax}_max"] = np.array([])
                arrays[f"{ax}_bin"] = np.array([])
        arrays["efficiency"] = prepared["lookup_efficiency"].to_numpy(dtype=float)
        arrays["err_low"] = prepared["lookup_err_low"].to_numpy(dtype=float)
        arrays["err_high"] = prepared["lookup_err_high"].to_numpy(dtype=float)
        arrays["total"] = prepared["total"].to_numpy(dtype=int) if "total" in prepared.columns else np.full(len(prepared), -1, dtype=int)
        arrays["has_u"] = has_u
        arrays["has_v"] = has_v
        arrays["min_total"] = min_total
        arrays["level_name"] = level_name
        self._levels.append(arrays)

    @property
    def has_u(self) -> bool:
        """True when the primary level includes u-axis (rapidity) binning."""
        return bool(self._levels[0].get("has_u", False))

    @property
    def has_v(self) -> bool:
        """True when the primary level includes v-axis (rapidity) binning."""
        return bool(self._levels[0].get("has_v", False))

    @property
    def axis_names(self) -> list[str]:
        """Ordered list of axis names present in the primary level."""
        names = ["x", "y", "z"]
        if self.has_u:
            names.append("u")
        if self.has_v:
            names.append("v")
        return names

    @staticmethod
    def _prepare_frame(
        frame: pd.DataFrame,
        *,
        step: str,
        map_type: str,
        denominator: Literal["absolute", "conditional"],
    ) -> pd.DataFrame:
        required = {
            "map_type",
            "step",
            "x_min",
            "x_max",
            "y_min",
            "y_max",
            "z_min",
            "z_max",
            "x_bin",
            "y_bin",
            "z_bin",
        }
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"Efficiency map is missing required column(s): {', '.join(missing)}")

        selected = frame.loc[(frame["map_type"] == map_type) & (frame["step"] == step)].copy()
        if selected.empty:
            raise ValueError(f"No rows found for map_type={map_type!r}, step={step!r}")

        if denominator == "absolute":
            if "absolute_efficiency" in selected.columns:
                selected["lookup_efficiency"] = selected["absolute_efficiency"].astype(float)
                selected["lookup_err_low"] = np.nan
                selected["lookup_err_high"] = np.nan
            elif "efficiency" in selected.columns:
                selected["lookup_efficiency"] = selected["efficiency"].astype(float)
                selected["lookup_err_low"] = selected.get("err_low", np.nan)
                selected["lookup_err_high"] = selected.get("err_high", np.nan)
            else:
                raise ValueError("Efficiency map has neither efficiency nor absolute_efficiency")
        elif denominator == "conditional":
            if "efficiency" not in selected.columns:
                raise ValueError("Conditional correction requires an efficiency column")
            selected["lookup_efficiency"] = selected["efficiency"].astype(float)
            selected["lookup_err_low"] = selected.get("err_low", np.nan)
            selected["lookup_err_high"] = selected.get("err_high", np.nan)
        else:
            raise ValueError(f"Unsupported denominator: {denominator}")

        selected["lookup_err_low"] = selected["lookup_err_low"].astype(float)
        selected["lookup_err_high"] = selected["lookup_err_high"].astype(float)
        sort_cols = ["x_bin", "y_bin", "z_bin"]
        if "u_bin" in selected.columns:
            sort_cols.append("u_bin")
        if "v_bin" in selected.columns:
            sort_cols.append("v_bin")
        selected.sort_values(sort_cols, inplace=True)
        return selected.reset_index(drop=True)

    # ------------------------------------------------------------------
    # axis matching helpers (handle NaN = unbounded for inclusive bins)
    # ------------------------------------------------------------------

    @staticmethod
    def _axis_match(level: dict[str, np.ndarray], axis: str, value: float) -> np.ndarray:
        low = level[f"{axis}_min"]
        high = level[f"{axis}_max"]
        active = np.isfinite(low) & np.isfinite(high)
        return (~active) | (np.isfinite(value) & (low <= value) & (value < high))

    @staticmethod
    def _axis_match_idx(level: dict[str, np.ndarray], axis: str, idx: int, value: float) -> bool:
        low = level[f"{axis}_min"][idx]
        high = level[f"{axis}_max"][idx]
        if not (math.isfinite(low) and math.isfinite(high)):
            return True  # unbounded — always matches
        return math.isfinite(value) and low <= value < high

    @staticmethod
    def _axis_match_idx_array(level: dict[str, np.ndarray], axis: str, idx: int, values: np.ndarray) -> np.ndarray:
        low = float(level[f"{axis}_min"][idx])
        high = float(level[f"{axis}_max"][idx])
        if not (math.isfinite(low) and math.isfinite(high)):
            return np.ones(len(values), dtype=bool)  # unbounded
        return np.isfinite(values) & (low <= values) & (values < high)

    # ------------------------------------------------------------------
    # scalar lookup
    # ------------------------------------------------------------------
    def lookup(
        self,
        jpsi1_pt: float,
        jpsi2_pt: float,
        phi_pt: float,
        jpsi1_abs_y: float | None = None,
        jpsi2_abs_y: float | None = None,
    ) -> EfficiencyCorrection:
        if not (math.isfinite(jpsi1_pt) and math.isfinite(jpsi2_pt) and math.isfinite(phi_pt)):
            return self._missing()
        lead_pt = max(float(jpsi1_pt), float(jpsi2_pt))
        sublead_pt = min(float(jpsi1_pt), float(jpsi2_pt))
        phi = float(phi_pt)

        # determine lead/sublead rapidity from the same ordering as pT
        if jpsi1_abs_y is not None and jpsi2_abs_y is not None and math.isfinite(jpsi1_abs_y) and math.isfinite(jpsi2_abs_y):
            if float(jpsi1_pt) >= float(jpsi2_pt):
                lead_abs_y = float(jpsi1_abs_y)
                sublead_abs_y = float(jpsi2_abs_y)
            else:
                lead_abs_y = float(jpsi2_abs_y)
                sublead_abs_y = float(jpsi1_abs_y)
        else:
            lead_abs_y = math.nan
            sublead_abs_y = math.nan

        for level in self._levels:
            matches = self._axis_match(level, "x", lead_pt) & self._axis_match(level, "y", sublead_pt) & self._axis_match(level, "z", phi)
            if level["has_u"]:
                matches &= self._axis_match(level, "u", lead_abs_y)
            if level["has_v"]:
                matches &= self._axis_match(level, "v", sublead_abs_y)
            indices = np.flatnonzero(matches)
            if indices.size == 0:
                continue
            idx = int(indices[0])
            total = int(level["total"][idx])
            if level["min_total"] > 0 and total < level["min_total"]:
                continue
            eff = float(level["efficiency"][idx])
            if not math.isfinite(eff) or eff <= 0.0:
                # fall through to next (coarser) level
                continue
            u_bin = int(level["u_bin"][idx]) if level["has_u"] else -1
            v_bin = int(level["v_bin"][idx]) if level["has_v"] else -1
            return EfficiencyCorrection(
                efficiency=eff,
                weight=1.0 / eff,
                err_low=float(level["err_low"][idx]),
                err_high=float(level["err_high"][idx]),
                x_bin=int(level["x_bin"][idx]),
                y_bin=int(level["y_bin"][idx]),
                z_bin=int(level["z_bin"][idx]),
                u_bin=u_bin,
                v_bin=v_bin,
                status=STATUS_OK,
            )
        return self._missing()

    # ------------------------------------------------------------------
    # vectorized array lookup  (needed for closure tests & scalability)
    # ------------------------------------------------------------------
    def lookup_arrays(
        self,
        jpsi1_pt: np.ndarray,
        jpsi2_pt: np.ndarray,
        phi_pt: np.ndarray,
        jpsi1_abs_y: np.ndarray | None = None,
        jpsi2_abs_y: np.ndarray | None = None,
    ) -> FactorizedCorrectionArrays:
        """Vectorized correction lookup with hierarchical fallback.

        Returns a FactorizedCorrectionArrays for interface compatibility
        with the existing closure test pipeline.  Only ``efficiency``,
        ``weight``, ``status``, and ``mc_stat_unc`` are populated;
        ``weight_err`` and ``fallback_components`` are set to zero/empty.
        """
        jpsi1_pt = np.asarray(jpsi1_pt, dtype=float)
        jpsi2_pt = np.asarray(jpsi2_pt, dtype=float)
        phi_pt = np.asarray(phi_pt, dtype=float)
        n_events = len(jpsi1_pt)

        lead_pt = np.maximum(jpsi1_pt, jpsi2_pt)
        sublead_pt = np.minimum(jpsi1_pt, jpsi2_pt)

        # sort rapidity following the same pT ordering
        if jpsi1_abs_y is not None and jpsi2_abs_y is not None:
            jpsi1_abs_y = np.asarray(jpsi1_abs_y, dtype=float)
            jpsi2_abs_y = np.asarray(jpsi2_abs_y, dtype=float)
            jpsi1_is_lead = jpsi1_pt >= jpsi2_pt
            lead_abs_y = np.where(jpsi1_is_lead, jpsi1_abs_y, jpsi2_abs_y)
            sublead_abs_y = np.where(jpsi1_is_lead, jpsi2_abs_y, jpsi1_abs_y)
        else:
            lead_abs_y = np.full(n_events, math.nan, dtype=float)
            sublead_abs_y = np.full(n_events, math.nan, dtype=float)

        efficiency = np.full(n_events, math.nan, dtype=np.float64)
        weight = np.full(n_events, math.nan, dtype=np.float64)
        status = np.full(n_events, STATUS_MISSING_BIN, dtype=np.int32)

        unresolved = np.ones(n_events, dtype=bool)

        for level in self._levels:
            if not np.any(unresolved):
                break
            min_total = level["min_total"]
            for idx in range(len(level["efficiency"])):
                if not np.any(unresolved):
                    break
                if min_total > 0 and int(level["total"][idx]) < min_total:
                    continue
                # use axis-match helpers that treat NaN edges as unbounded
                matches = (
                    unresolved
                    & self._axis_match_idx_array(level, "x", idx, lead_pt)
                    & self._axis_match_idx_array(level, "y", idx, sublead_pt)
                    & self._axis_match_idx_array(level, "z", idx, phi_pt)
                )
                if level["has_u"]:
                    matches &= self._axis_match_idx_array(level, "u", idx, lead_abs_y)
                if level["has_v"]:
                    matches &= self._axis_match_idx_array(level, "v", idx, sublead_abs_y)
                if not np.any(matches):
                    continue
                eff = float(level["efficiency"][idx])
                row_status = STATUS_OK if math.isfinite(eff) and eff > 0.0 else STATUS_INVALID_EFFICIENCY
                efficiency[matches] = eff
                status[matches] = row_status
                if row_status == STATUS_OK:
                    unresolved[matches] = False
                # invalid-efficiency events stay unresolved → fall through to next level

        ok = status == STATUS_OK
        weight[ok] = 1.0 / efficiency[ok]
        efficiency[~ok] = np.nan

        # mc_stat_unc is not propagated in the non-factorized approach
        # (the hierarchical fallback makes the covariance structure complex);
        # set to 0.0 as a placeholder.
        return FactorizedCorrectionArrays(
            efficiency=efficiency,
            weight=weight,
            weight_err=np.zeros(n_events, dtype=np.float64),
            status=status,
            fallback_components=np.zeros(n_events, dtype=np.int32),
            mc_stat_unc=0.0,
        )

    @staticmethod
    def _missing() -> EfficiencyCorrection:
        return EfficiencyCorrection(
            efficiency=math.nan,
            weight=math.nan,
            err_low=math.nan,
            err_high=math.nan,
            x_bin=-1,
            y_bin=-1,
            z_bin=-1,
            status=STATUS_MISSING_BIN,
        )


class FactorizedCorrectionMap:
    """Product of per-object and event-level factorized correction maps."""

    REQUIRED_FACTORS = (
        "acceptance_jpsi",
        "acceptance_phi",
        "eff_muReco_jpsi",
        "eff_muID_jpsi",
        "eff_dimuon_jpsi",
        "eff_kaonReco_phi",
        "eff_kaonID_phi",
        "eff_dikaon_phi",
        "eff_hlt",
        "eff_4mu_vtx",
        "eff_triOnia",
    )

    def __init__(
        self,
        maps: dict[str, pd.DataFrame],
        *,
        source: Path,
        n_min_fine: int = 30,
        n_min_coarse: int = 50,
    ) -> None:
        missing = sorted(set(self.REQUIRED_FACTORS) - set(maps))
        if missing:
            raise ValueError(f"Missing factorized map(s): {', '.join(missing)}")
        self.source = Path(source)
        self.n_min_fine = int(n_min_fine)
        self.n_min_coarse = int(n_min_coarse)
        self.maps = {name: self._prepare_frame(frame, name) for name, frame in maps.items()}
        self._maps_by_level = {
            name: {
                level: frame.loc[frame["fallback_level"] == level]
                for level in ("fine", "coarse", "inclusive")
            }
            for name, frame in self.maps.items()
        }

    @staticmethod
    def _prepare_frame(frame: pd.DataFrame, factor_name: str) -> pd.DataFrame:
        required = {
            "factor_name",
            "fallback_level",
            "x_min",
            "x_max",
            "y_min",
            "y_max",
            "z_min",
            "z_max",
            "x_bin",
            "y_bin",
            "z_bin",
            "total",
            "passed",
            "efficiency",
        }
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{factor_name} map is missing required column(s): {', '.join(missing)}")
        selected = frame.loc[frame["factor_name"] == factor_name].copy()
        if selected.empty:
            raise ValueError(f"No rows found for factorized map {factor_name!r}")
        if "err_sym" not in selected.columns:
            selected["err_sym"] = selected.get("err_high", np.nan)
        selected["err_sym"] = selected["err_sym"].astype(float)
        return selected.reset_index(drop=True)

    def _minimum_total_for_level(self, level: str) -> int:
        if level == "fine":
            return self.n_min_fine
        if level == "coarse":
            return self.n_min_coarse
        return 1

    @staticmethod
    def _matches_axis(frame: pd.DataFrame, axis: str, value: float) -> np.ndarray:
        low = frame[f"{axis}_min"].to_numpy(dtype=float)
        high = frame[f"{axis}_max"].to_numpy(dtype=float)
        active = np.isfinite(low) & np.isfinite(high)
        return (~active) | (np.isfinite(value) & (low <= value) & (value < high))

    @staticmethod
    def _matches_axis_array(row: pd.Series, axis: str, values: np.ndarray) -> np.ndarray:
        low = float(row[f"{axis}_min"])
        high = float(row[f"{axis}_max"])
        if not (math.isfinite(low) and math.isfinite(high)):
            return np.ones(len(values), dtype=bool)
        return np.isfinite(values) & (low <= values) & (values < high)

    def _lookup_component(
        self,
        *,
        component_name: str,
        factor_name: str,
        x_value: float,
        y_value: float = math.nan,
        z_value: float = math.nan,
    ) -> FactorizedComponentCorrection:
        frame = self.maps[factor_name]
        for level in ("fine", "coarse", "inclusive"):
            subset = frame.loc[frame["fallback_level"] == level]
            if subset.empty:
                continue
            matches = (
                self._matches_axis(subset, "x", x_value)
                & self._matches_axis(subset, "y", y_value)
                & self._matches_axis(subset, "z", z_value)
            )
            indices = np.flatnonzero(matches)
            if indices.size == 0:
                continue
            row = subset.iloc[int(indices[0])]
            total = int(row["total"])
            if total < self._minimum_total_for_level(level):
                continue
            eff = float(row["efficiency"])
            if not math.isfinite(eff) or eff <= 0.0:
                return FactorizedComponentCorrection(
                    name=component_name,
                    factor_name=factor_name,
                    efficiency=eff,
                    err_sym=float(row.get("err_sym", math.nan)),
                    total=total,
                    passed=int(row["passed"]),
                    fallback_level=level,
                    x_bin=int(row["x_bin"]),
                    y_bin=int(row["y_bin"]),
                    z_bin=int(row["z_bin"]),
                    status=STATUS_INVALID_EFFICIENCY,
                )
            return FactorizedComponentCorrection(
                name=component_name,
                factor_name=factor_name,
                efficiency=eff,
                err_sym=float(row.get("err_sym", math.nan)),
                total=total,
                passed=int(row["passed"]),
                fallback_level=level,
                x_bin=int(row["x_bin"]),
                y_bin=int(row["y_bin"]),
                z_bin=int(row["z_bin"]),
                status=STATUS_OK,
            )
        return FactorizedComponentCorrection(
            name=component_name,
            factor_name=factor_name,
            efficiency=math.nan,
            err_sym=math.nan,
            total=0,
            passed=0,
            fallback_level="missing",
            x_bin=-1,
            y_bin=-1,
            z_bin=-1,
            status=STATUS_MISSING_BIN,
        )

    def _lookup_component_arrays(
        self,
        *,
        component_name: str,
        factor_name: str,
        x_values: np.ndarray,
        y_values: np.ndarray | None = None,
        z_values: np.ndarray | None = None,
    ) -> _FactorizedComponentArrays:
        x_values = np.asarray(x_values, dtype=float)
        n_events = len(x_values)
        if y_values is None:
            y_values = np.full(n_events, math.nan, dtype=float)
        else:
            y_values = np.asarray(y_values, dtype=float)
        if z_values is None:
            z_values = np.full(n_events, math.nan, dtype=float)
        else:
            z_values = np.asarray(z_values, dtype=float)

        efficiency = np.full(n_events, math.nan, dtype=np.float64)
        err_sym = np.full(n_events, math.nan, dtype=np.float64)
        status = np.full(n_events, STATUS_MISSING_BIN, dtype=np.int32)
        fallback_level = np.full(n_events, "missing", dtype=object)
        row_index = np.full(n_events, -1, dtype=np.int32)
        x_bin = np.full(n_events, -1, dtype=np.int32)
        y_bin = np.full(n_events, -1, dtype=np.int32)
        z_bin = np.full(n_events, -1, dtype=np.int32)
        unresolved = np.ones(n_events, dtype=bool)

        for level in ("fine", "coarse", "inclusive"):
            level_frame = self._maps_by_level[factor_name][level]
            if level_frame.empty:
                continue
            min_total = self._minimum_total_for_level(level)
            for idx, row in level_frame.iterrows():
                if not np.any(unresolved):
                    break
                if int(row["total"]) < min_total:
                    continue
                matches = (
                    unresolved
                    & self._matches_axis_array(row, "x", x_values)
                    & self._matches_axis_array(row, "y", y_values)
                    & self._matches_axis_array(row, "z", z_values)
                )
                if not np.any(matches):
                    continue
                eff = float(row["efficiency"])
                row_status = STATUS_OK if math.isfinite(eff) and eff > 0.0 else STATUS_INVALID_EFFICIENCY
                efficiency[matches] = eff
                err_sym[matches] = float(row.get("err_sym", math.nan))
                status[matches] = row_status
                fallback_level[matches] = level
                row_index[matches] = int(idx)
                x_bin[matches] = int(row["x_bin"])
                y_bin[matches] = int(row["y_bin"])
                z_bin[matches] = int(row["z_bin"])
                unresolved[matches] = False

        return _FactorizedComponentArrays(
            name=component_name,
            factor_name=factor_name,
            efficiency=efficiency,
            err_sym=err_sym,
            status=status,
            fallback_level=fallback_level,
            row_index=row_index,
            x_bin=x_bin,
            y_bin=y_bin,
            z_bin=z_bin,
        )

    def lookup(
        self,
        *,
        jpsi1_pt: float,
        jpsi1_y: float,
        jpsi2_pt: float,
        jpsi2_y: float,
        phi_pt: float,
        phi_y: float,
    ) -> FactorizedCorrection:
        lead_pt = max(float(jpsi1_pt), float(jpsi2_pt))
        sublead_pt = min(float(jpsi1_pt), float(jpsi2_pt))
        components = [
            self._lookup_component(component_name="jpsi1_acceptance", factor_name="acceptance_jpsi", x_value=float(jpsi1_pt), y_value=abs(float(jpsi1_y))),
            self._lookup_component(component_name="jpsi1_muReco", factor_name="eff_muReco_jpsi", x_value=float(jpsi1_pt), y_value=abs(float(jpsi1_y))),
            self._lookup_component(component_name="jpsi1_muID", factor_name="eff_muID_jpsi", x_value=float(jpsi1_pt), y_value=abs(float(jpsi1_y))),
            self._lookup_component(component_name="jpsi1_dimuon", factor_name="eff_dimuon_jpsi", x_value=float(jpsi1_pt), y_value=abs(float(jpsi1_y))),
            self._lookup_component(component_name="jpsi2_acceptance", factor_name="acceptance_jpsi", x_value=float(jpsi2_pt), y_value=abs(float(jpsi2_y))),
            self._lookup_component(component_name="jpsi2_muReco", factor_name="eff_muReco_jpsi", x_value=float(jpsi2_pt), y_value=abs(float(jpsi2_y))),
            self._lookup_component(component_name="jpsi2_muID", factor_name="eff_muID_jpsi", x_value=float(jpsi2_pt), y_value=abs(float(jpsi2_y))),
            self._lookup_component(component_name="jpsi2_dimuon", factor_name="eff_dimuon_jpsi", x_value=float(jpsi2_pt), y_value=abs(float(jpsi2_y))),
            self._lookup_component(component_name="phi_acceptance", factor_name="acceptance_phi", x_value=float(phi_pt), y_value=abs(float(phi_y))),
            self._lookup_component(component_name="phi_kaonReco", factor_name="eff_kaonReco_phi", x_value=float(phi_pt), y_value=abs(float(phi_y))),
            self._lookup_component(component_name="phi_kaonID", factor_name="eff_kaonID_phi", x_value=float(phi_pt), y_value=abs(float(phi_y))),
            self._lookup_component(component_name="phi_dikaon", factor_name="eff_dikaon_phi", x_value=float(phi_pt), y_value=abs(float(phi_y))),
            self._lookup_component(component_name="event_hlt", factor_name="eff_hlt", x_value=lead_pt, y_value=sublead_pt),
            self._lookup_component(component_name="event_4mu_vtx", factor_name="eff_4mu_vtx", x_value=lead_pt, y_value=sublead_pt),
            self._lookup_component(component_name="event_triOnia", factor_name="eff_triOnia", x_value=lead_pt, y_value=sublead_pt, z_value=float(phi_pt)),
        ]
        statuses = {component.status for component in components}
        if STATUS_MISSING_BIN in statuses:
            return FactorizedCorrection(math.nan, math.nan, math.nan, STATUS_MISSING_BIN, tuple(components))
        if STATUS_INVALID_EFFICIENCY in statuses:
            return FactorizedCorrection(math.nan, math.nan, math.nan, STATUS_INVALID_EFFICIENCY, tuple(components))

        efficiencies = np.asarray([component.efficiency for component in components], dtype=float)
        total_eff = float(np.prod(efficiencies))
        if not math.isfinite(total_eff) or total_eff <= 0.0:
            return FactorizedCorrection(total_eff, math.nan, math.nan, STATUS_INVALID_EFFICIENCY, tuple(components))
        rel_var = 0.0
        for component in components:
            if math.isfinite(component.err_sym) and component.efficiency > 0.0:
                rel_var += float((component.err_sym / component.efficiency) ** 2)
        weight = 1.0 / total_eff
        return FactorizedCorrection(
            efficiency=total_eff,
            weight=weight,
            err_sym=weight * math.sqrt(rel_var) if rel_var > 0.0 else math.nan,
            status=STATUS_OK,
            components=tuple(components),
        )

    def lookup_arrays(
        self,
        *,
        jpsi1_pt: np.ndarray,
        jpsi1_y: np.ndarray,
        jpsi2_pt: np.ndarray,
        jpsi2_y: np.ndarray,
        phi_pt: np.ndarray,
        phi_y: np.ndarray,
    ) -> FactorizedCorrectionArrays:
        jpsi1_pt = np.asarray(jpsi1_pt, dtype=float)
        jpsi1_y = np.asarray(jpsi1_y, dtype=float)
        jpsi2_pt = np.asarray(jpsi2_pt, dtype=float)
        jpsi2_y = np.asarray(jpsi2_y, dtype=float)
        phi_pt = np.asarray(phi_pt, dtype=float)
        phi_y = np.asarray(phi_y, dtype=float)
        lengths = {len(jpsi1_pt), len(jpsi1_y), len(jpsi2_pt), len(jpsi2_y), len(phi_pt), len(phi_y)}
        if len(lengths) != 1:
            raise ValueError("All lookup arrays must have the same length")

        lead_pt = np.maximum(jpsi1_pt, jpsi2_pt)
        sublead_pt = np.minimum(jpsi1_pt, jpsi2_pt)
        component_results = [
            self._lookup_component_arrays(component_name="jpsi1_acceptance", factor_name="acceptance_jpsi", x_values=jpsi1_pt, y_values=np.abs(jpsi1_y)),
            self._lookup_component_arrays(component_name="jpsi1_muReco", factor_name="eff_muReco_jpsi", x_values=jpsi1_pt, y_values=np.abs(jpsi1_y)),
            self._lookup_component_arrays(component_name="jpsi1_muID", factor_name="eff_muID_jpsi", x_values=jpsi1_pt, y_values=np.abs(jpsi1_y)),
            self._lookup_component_arrays(component_name="jpsi1_dimuon", factor_name="eff_dimuon_jpsi", x_values=jpsi1_pt, y_values=np.abs(jpsi1_y)),
            self._lookup_component_arrays(component_name="jpsi2_acceptance", factor_name="acceptance_jpsi", x_values=jpsi2_pt, y_values=np.abs(jpsi2_y)),
            self._lookup_component_arrays(component_name="jpsi2_muReco", factor_name="eff_muReco_jpsi", x_values=jpsi2_pt, y_values=np.abs(jpsi2_y)),
            self._lookup_component_arrays(component_name="jpsi2_muID", factor_name="eff_muID_jpsi", x_values=jpsi2_pt, y_values=np.abs(jpsi2_y)),
            self._lookup_component_arrays(component_name="jpsi2_dimuon", factor_name="eff_dimuon_jpsi", x_values=jpsi2_pt, y_values=np.abs(jpsi2_y)),
            self._lookup_component_arrays(component_name="phi_acceptance", factor_name="acceptance_phi", x_values=phi_pt, y_values=np.abs(phi_y)),
            self._lookup_component_arrays(component_name="phi_kaonReco", factor_name="eff_kaonReco_phi", x_values=phi_pt, y_values=np.abs(phi_y)),
            self._lookup_component_arrays(component_name="phi_kaonID", factor_name="eff_kaonID_phi", x_values=phi_pt, y_values=np.abs(phi_y)),
            self._lookup_component_arrays(component_name="phi_dikaon", factor_name="eff_dikaon_phi", x_values=phi_pt, y_values=np.abs(phi_y)),
            self._lookup_component_arrays(component_name="event_hlt", factor_name="eff_hlt", x_values=lead_pt, y_values=sublead_pt),
            self._lookup_component_arrays(component_name="event_4mu_vtx", factor_name="eff_4mu_vtx", x_values=lead_pt, y_values=sublead_pt),
            self._lookup_component_arrays(component_name="event_triOnia", factor_name="eff_triOnia", x_values=lead_pt, y_values=sublead_pt, z_values=phi_pt),
        ]

        n_events = len(jpsi1_pt)
        status = np.full(n_events, STATUS_OK, dtype=np.int32)
        missing = np.zeros(n_events, dtype=bool)
        invalid = np.zeros(n_events, dtype=bool)
        for component in component_results:
            missing |= component.status == STATUS_MISSING_BIN
            invalid |= component.status == STATUS_INVALID_EFFICIENCY
        status[invalid] = STATUS_INVALID_EFFICIENCY
        status[missing] = STATUS_MISSING_BIN

        efficiency = np.ones(n_events, dtype=np.float64)
        rel_var = np.zeros(n_events, dtype=np.float64)
        fallback_components = np.zeros(n_events, dtype=np.int32)
        for component in component_results:
            efficiency *= component.efficiency
            valid_err = np.isfinite(component.err_sym) & (component.efficiency > 0.0)
            rel_var[valid_err] += (component.err_sym[valid_err] / component.efficiency[valid_err]) ** 2
            fallback_components += ((component.status == STATUS_OK) & (component.fallback_level != "fine")).astype(np.int32)

        invalid_eff = ~np.isfinite(efficiency) | (efficiency <= 0.0)
        status[(status == STATUS_OK) & invalid_eff] = STATUS_INVALID_EFFICIENCY
        weight = np.full(n_events, math.nan, dtype=np.float64)
        ok = status == STATUS_OK
        weight[ok] = 1.0 / efficiency[ok]
        weight_err = np.full(n_events, math.nan, dtype=np.float64)
        has_rel_var = ok & (rel_var > 0.0)
        weight_err[has_rel_var] = weight[has_rel_var] * np.sqrt(rel_var[has_rel_var])
        efficiency[~ok] = np.nan

        mc_stat_terms: dict[tuple[str, str, int, int, int], tuple[float, float]] = {}
        for component in component_results:
            valid_component = ok & (component.status == STATUS_OK) & np.isfinite(component.err_sym) & (component.efficiency > 0.0)
            for row_idx in np.unique(component.row_index[valid_component]):
                if row_idx < 0:
                    continue
                mask = valid_component & (component.row_index == row_idx)
                if not np.any(mask):
                    continue
                first = int(np.flatnonzero(mask)[0])
                key = (
                    component.name,
                    str(component.fallback_level[first]),
                    int(component.x_bin[first]),
                    int(component.y_bin[first]),
                    int(component.z_bin[first]),
                )
                previous_sum, err = mc_stat_terms.get(key, (0.0, float(component.err_sym[first])))
                mc_stat_terms[key] = (previous_sum + float(np.sum(weight[mask] / component.efficiency[mask])), err)
        mc_stat_var = sum((sum_w_over_eff * err) ** 2 for sum_w_over_eff, err in mc_stat_terms.values())

        return FactorizedCorrectionArrays(
            efficiency=efficiency,
            weight=weight,
            weight_err=weight_err,
            status=status,
            fallback_components=fallback_components,
            mc_stat_unc=float(math.sqrt(mc_stat_var)),
        )


class HybridCorrectionMap:
    """Hybrid efficiency correction: factorized acceptance × 5D conditional post-acceptance.

    w = 1 / (A_jpsi_lead × A_jpsi_sublead × A_phi × ε_5d_post_acceptance)

    The acceptance factors are looked up in 2D (pT, |y|) with fine→coarse→inclusive
    fallback.  The post-acceptance efficiency is looked up in 5D (lead pT, sublead pT,
    φ pT, |lead y|, |sublead y|) with 3D coarse and inclusive fallbacks.
    """

    def __init__(
        self,
        acceptance_jpsi: pd.DataFrame,
        acceptance_phi: pd.DataFrame,
        post_acceptance_5d: pd.DataFrame,
        *,
        source: Path,
        n_min_fine: int = 30,
        n_min_coarse: int = 50,
    ) -> None:
        self.source = Path(source)
        self.n_min_fine = int(n_min_fine)
        self.n_min_coarse = int(n_min_coarse)

        # Prepare acceptance maps (same pattern as FactorizedCorrectionMap)
        self._acc_jpsi = self._prepare_factor_frame(acceptance_jpsi, "acceptance_jpsi")
        self._acc_phi = self._prepare_factor_frame(acceptance_phi, "acceptance_phi")
        self._acc_jpsi_by_level = self._split_by_level(self._acc_jpsi)
        self._acc_phi_by_level = self._split_by_level(self._acc_phi)

        # Prepare post-acceptance 5D map
        self._pa5d = self._prepare_post_acceptance(post_acceptance_5d)
        self._pa5d_by_level = self._split_by_level(self._pa5d)

    # ------------------------------------------------------------------
    # Frame preparation (shared with FactorizedCorrectionMap)
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_factor_frame(frame: pd.DataFrame, factor_name: str) -> pd.DataFrame:
        required = {"factor_name", "fallback_level", "x_min", "x_max", "y_min", "y_max",
                     "z_min", "z_max", "x_bin", "y_bin", "z_bin", "total", "passed", "efficiency"}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{factor_name} map is missing required column(s): {', '.join(missing)}")
        selected = frame.loc[frame["factor_name"] == factor_name].copy()
        if selected.empty:
            raise ValueError(f"No rows found for factorized map {factor_name!r}")
        if "err_sym" not in selected.columns:
            selected["err_sym"] = selected.get("err_high", np.nan)
        selected["err_sym"] = selected["err_sym"].astype(float)
        return selected.reset_index(drop=True)

    @staticmethod
    def _prepare_post_acceptance(frame: pd.DataFrame) -> pd.DataFrame:
        required = {"fallback_level", "x_min", "x_max", "y_min", "y_max", "z_min", "z_max",
                     "x_bin", "y_bin", "z_bin", "total", "passed", "efficiency"}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"Post-acceptance 5D map missing column(s): {', '.join(missing)}")
        selected = frame.copy()
        if "err_sym" not in selected.columns:
            selected["err_sym"] = selected.get("err_high", np.nan)
        selected["err_sym"] = selected["err_sym"].astype(float)
        # Ensure u/v columns exist
        for col, default in [("u_min", np.nan), ("u_max", np.nan), ("u_bin", -1),
                              ("v_min", np.nan), ("v_max", np.nan), ("v_bin", -1)]:
            if col not in selected.columns:
                selected[col] = default
        return selected.reset_index(drop=True)

    @staticmethod
    def _split_by_level(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
        return {
            level: frame.loc[frame["fallback_level"] == level]
            for level in ("fine", "coarse", "inclusive")
        }

    # ------------------------------------------------------------------
    # Fallback threshold
    # ------------------------------------------------------------------

    def _min_total_for_level(self, level: str) -> int:
        if level == "fine":
            return self.n_min_fine
        if level == "coarse":
            return self.n_min_coarse
        return 1

    # ------------------------------------------------------------------
    # Axis matching helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_axis(frame: pd.DataFrame, axis: str, value: float) -> np.ndarray:
        low = frame[f"{axis}_min"].to_numpy(dtype=float)
        high = frame[f"{axis}_max"].to_numpy(dtype=float)
        active = np.isfinite(low) & np.isfinite(high)
        return (~active) | (np.isfinite(value) & (low <= value) & (value < high))

    @staticmethod
    def _matches_axis_array(row: pd.Series, axis: str, values: np.ndarray) -> np.ndarray:
        low = float(row[f"{axis}_min"])
        high = float(row[f"{axis}_max"])
        if not (math.isfinite(low) and math.isfinite(high)):
            return np.ones(len(values), dtype=bool)
        return np.isfinite(values) & (low <= values) & (values < high)

    # ------------------------------------------------------------------
    # Scalar: lookup a single acceptance component
    # ------------------------------------------------------------------

    def _lookup_acc(
        self, factor_frame: pd.DataFrame, by_level: dict[str, pd.DataFrame],
        x_value: float, y_value: float,
    ) -> tuple[float, float, str, int]:
        """Return (efficiency, err_sym, fallback_level, status) for one acceptance factor."""
        for level in ("fine", "coarse", "inclusive"):
            subset = by_level[level]
            if subset.empty:
                continue
            matches = self._matches_axis(subset, "x", x_value) & self._matches_axis(subset, "y", y_value)
            indices = np.flatnonzero(matches)
            if indices.size == 0:
                continue
            row = subset.iloc[int(indices[0])]
            if int(row["total"]) < self._min_total_for_level(level):
                continue
            eff = float(row["efficiency"])
            if not math.isfinite(eff) or eff <= 0.0:
                continue  # fall through to coarser level
            return (eff, float(row.get("err_sym", np.nan)), level, STATUS_OK)
        return (np.nan, np.nan, "missing", STATUS_MISSING_BIN)

    # ------------------------------------------------------------------
    # Scalar: lookup post-acceptance 5D
    # ------------------------------------------------------------------

    def _lookup_pa5d(
        self,
        lead_pt: float, sublead_pt: float, phi_pt: float,
        lead_abs_y: float, sublead_abs_y: float,
    ) -> tuple[float, float, str, int]:
        """Return (efficiency, err_sym, fallback_level, status) for post-acceptance 5D."""
        for level in ("fine", "coarse", "inclusive"):
            subset = self._pa5d_by_level[level]
            if subset.empty:
                continue
            matches = (
                self._matches_axis(subset, "x", lead_pt)
                & self._matches_axis(subset, "y", sublead_pt)
                & self._matches_axis(subset, "z", phi_pt)
            )
            # u/v only used in fine level
            if level == "fine":
                matches &= self._matches_axis(subset, "u", lead_abs_y)
                matches &= self._matches_axis(subset, "v", sublead_abs_y)
            indices = np.flatnonzero(matches)
            if indices.size == 0:
                continue
            row = subset.iloc[int(indices[0])]
            if int(row["total"]) < self._min_total_for_level(level):
                continue
            eff = float(row["efficiency"])
            if not math.isfinite(eff) or eff <= 0.0:
                continue  # fall through to coarser level
            return (eff, float(row.get("err_sym", np.nan)), level, STATUS_OK)
        return (np.nan, np.nan, "missing", STATUS_MISSING_BIN)

    # ------------------------------------------------------------------
    # Scalar lookup
    # ------------------------------------------------------------------

    def lookup(
        self,
        *,
        jpsi1_pt: float,
        jpsi1_y: float,
        jpsi2_pt: float,
        jpsi2_y: float,
        phi_pt: float,
        phi_y: float,
    ) -> FactorizedCorrection:
        # Determine lead/sublead ordering
        j1_pt = float(jpsi1_pt); j1_y = float(jpsi1_y)
        j2_pt = float(jpsi2_pt); j2_y = float(jpsi2_y)
        p_pt = float(phi_pt); p_y = float(phi_y)
        if j1_pt >= j2_pt:
            lead_pt, lead_y = j1_pt, j1_y
            sublead_pt, sublead_y = j2_pt, j2_y
        else:
            lead_pt, lead_y = j2_pt, j2_y
            sublead_pt, sublead_y = j1_pt, j1_y

        # Acceptance components
        a_lead_eff, a_lead_err, a_lead_lvl, a_lead_st = self._lookup_acc(
            self._acc_jpsi, self._acc_jpsi_by_level, lead_pt, abs(lead_y))
        a_sublead_eff, a_sublead_err, a_sublead_lvl, a_sublead_st = self._lookup_acc(
            self._acc_jpsi, self._acc_jpsi_by_level, sublead_pt, abs(sublead_y))
        a_phi_eff, a_phi_err, a_phi_lvl, a_phi_st = self._lookup_acc(
            self._acc_phi, self._acc_phi_by_level, p_pt, abs(p_y))

        # Post-acceptance 5D
        pa_eff, pa_err, pa_lvl, pa_st = self._lookup_pa5d(
            lead_pt, sublead_pt, p_pt, abs(lead_y), abs(sublead_y))

        # Build component list for diagnostics
        components = (
            FactorizedComponentCorrection("jpsi_lead_acceptance", "acceptance_jpsi", float(a_lead_eff), float(a_lead_err), 0, 0, str(a_lead_lvl), -1, -1, -1, int(a_lead_st)),
            FactorizedComponentCorrection("jpsi_sublead_acceptance", "acceptance_jpsi", float(a_sublead_eff), float(a_sublead_err), 0, 0, str(a_sublead_lvl), -1, -1, -1, int(a_sublead_st)),
            FactorizedComponentCorrection("phi_acceptance", "acceptance_phi", float(a_phi_eff), float(a_phi_err), 0, 0, str(a_phi_lvl), -1, -1, -1, int(a_phi_st)),
            FactorizedComponentCorrection("post_acceptance_5d", "post_acceptance_5d", float(pa_eff), float(pa_err), 0, 0, str(pa_lvl), -1, -1, -1, int(pa_st)),
        )

        statuses = {a_lead_st, a_sublead_st, a_phi_st, pa_st}
        if STATUS_MISSING_BIN in statuses:
            return FactorizedCorrection(np.nan, np.nan, np.nan, STATUS_MISSING_BIN, components)
        if STATUS_INVALID_EFFICIENCY in statuses:
            return FactorizedCorrection(np.nan, np.nan, np.nan, STATUS_INVALID_EFFICIENCY, components)

        total_eff = float(a_lead_eff * a_sublead_eff * a_phi_eff * pa_eff)
        if not math.isfinite(total_eff) or total_eff <= 0.0:
            return FactorizedCorrection(total_eff, np.nan, np.nan, STATUS_INVALID_EFFICIENCY, components)

        # Relative uncertainty
        rel_var = 0.0
        for eff_val, err_val in [(a_lead_eff, a_lead_err), (a_sublead_eff, a_sublead_err),
                                  (a_phi_eff, a_phi_err), (pa_eff, pa_err)]:
            if math.isfinite(err_val) and eff_val > 0.0:
                rel_var += float((err_val / eff_val) ** 2)
        weight = 1.0 / total_eff
        err_sym = weight * math.sqrt(rel_var) if rel_var > 0.0 else np.nan
        return FactorizedCorrection(total_eff, weight, err_sym, STATUS_OK, components)

    # ------------------------------------------------------------------
    # Vectorized: lookup a single acceptance component
    # ------------------------------------------------------------------

    @staticmethod
    def _lookup_acc_arrays(
        by_level: dict[str, pd.DataFrame],
        x_values: np.ndarray, y_values: np.ndarray,
        min_total_for_level: callable,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return (efficiency, err_sym, fallback_str, status) arrays."""
        n_events = len(x_values)
        efficiency = np.full(n_events, np.nan, dtype=np.float64)
        err_sym = np.full(n_events, np.nan, dtype=np.float64)
        status = np.full(n_events, STATUS_MISSING_BIN, dtype=np.int32)
        fallback_level = np.full(n_events, "missing", dtype=object)
        unresolved = np.ones(n_events, dtype=bool)

        for level in ("fine", "coarse", "inclusive"):
            level_frame = by_level[level]
            if level_frame.empty:
                continue
            min_total = min_total_for_level(level)
            for _, row in level_frame.iterrows():
                if not np.any(unresolved):
                    break
                if int(row["total"]) < min_total:
                    continue
                matches = (
                    unresolved
                    & HybridCorrectionMap._matches_axis_array(row, "x", x_values)
                    & HybridCorrectionMap._matches_axis_array(row, "y", y_values)
                )
                if not np.any(matches):
                    continue
                eff = float(row["efficiency"])
                row_status = STATUS_OK if math.isfinite(eff) and eff > 0.0 else STATUS_INVALID_EFFICIENCY
                efficiency[matches] = eff
                err_sym[matches] = float(row.get("err_sym", np.nan))
                status[matches] = row_status
                fallback_level[matches] = level
                # Only mark resolved if OK; invalid eff → fall through to coarser level
                unresolved[matches] = (row_status != STATUS_OK)
        return efficiency, err_sym, fallback_level, status

    # ------------------------------------------------------------------
    # Vectorized: lookup post-acceptance 5D
    # ------------------------------------------------------------------

    @staticmethod
    def _lookup_pa5d_arrays(
        by_level: dict[str, pd.DataFrame],
        lead_pt: np.ndarray, sublead_pt: np.ndarray, phi_pt: np.ndarray,
        lead_abs_y: np.ndarray, sublead_abs_y: np.ndarray,
        min_total_for_level: callable,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return (efficiency, err_sym, fallback_str, status) arrays for 5D."""
        n_events = len(lead_pt)
        efficiency = np.full(n_events, np.nan, dtype=np.float64)
        err_sym = np.full(n_events, np.nan, dtype=np.float64)
        status = np.full(n_events, STATUS_MISSING_BIN, dtype=np.int32)
        fallback_level = np.full(n_events, "missing", dtype=object)
        unresolved = np.ones(n_events, dtype=bool)

        for level in ("fine", "coarse", "inclusive"):
            level_frame = by_level[level]
            if level_frame.empty:
                continue
            min_total = min_total_for_level(level)
            for _, row in level_frame.iterrows():
                if not np.any(unresolved):
                    break
                if int(row["total"]) < min_total:
                    continue
                matches = (
                    unresolved
                    & HybridCorrectionMap._matches_axis_array(row, "x", lead_pt)
                    & HybridCorrectionMap._matches_axis_array(row, "y", sublead_pt)
                    & HybridCorrectionMap._matches_axis_array(row, "z", phi_pt)
                )
                if level == "fine":
                    matches &= HybridCorrectionMap._matches_axis_array(row, "u", lead_abs_y)
                    matches &= HybridCorrectionMap._matches_axis_array(row, "v", sublead_abs_y)
                if not np.any(matches):
                    continue
                eff = float(row["efficiency"])
                row_status = STATUS_OK if math.isfinite(eff) and eff > 0.0 else STATUS_INVALID_EFFICIENCY
                efficiency[matches] = eff
                err_sym[matches] = float(row.get("err_sym", np.nan))
                status[matches] = row_status
                fallback_level[matches] = level
                # Only mark resolved if OK; invalid eff → fall through to coarser level
                unresolved[matches] = (row_status != STATUS_OK)
        return efficiency, err_sym, fallback_level, status

    # ------------------------------------------------------------------
    # Vectorized array lookup
    # ------------------------------------------------------------------

    def lookup_arrays(
        self,
        *,
        jpsi1_pt: np.ndarray,
        jpsi1_y: np.ndarray,
        jpsi2_pt: np.ndarray,
        jpsi2_y: np.ndarray,
        phi_pt: np.ndarray,
        phi_y: np.ndarray,
    ) -> FactorizedCorrectionArrays:
        jpsi1_pt = np.asarray(jpsi1_pt, dtype=float)
        jpsi1_y = np.asarray(jpsi1_y, dtype=float)
        jpsi2_pt = np.asarray(jpsi2_pt, dtype=float)
        jpsi2_y = np.asarray(jpsi2_y, dtype=float)
        phi_pt = np.asarray(phi_pt, dtype=float)
        phi_y = np.asarray(phi_y, dtype=float)
        lengths = {len(jpsi1_pt), len(jpsi1_y), len(jpsi2_pt), len(jpsi2_y), len(phi_pt), len(phi_y)}
        if len(lengths) != 1:
            raise ValueError("All lookup arrays must have the same length")
        n_events = len(jpsi1_pt)

        # Lead/sublead ordering
        jpsi1_is_lead = jpsi1_pt >= jpsi2_pt
        lead_pt = np.where(jpsi1_is_lead, jpsi1_pt, jpsi2_pt)
        sublead_pt = np.where(jpsi1_is_lead, jpsi2_pt, jpsi1_pt)
        lead_abs_y = np.abs(np.where(jpsi1_is_lead, jpsi1_y, jpsi2_y))
        sublead_abs_y = np.abs(np.where(jpsi1_is_lead, jpsi2_y, jpsi1_y))
        phi_abs_y = np.abs(phi_y)

        min_total_fn = self._min_total_for_level

        # Lookup all 4 components
        a_lead_eff, a_lead_err, a_lead_lvl, a_lead_st = self._lookup_acc_arrays(
            self._acc_jpsi_by_level, lead_pt, lead_abs_y, min_total_fn)
        a_sublead_eff, a_sublead_err, a_sublead_lvl, a_sublead_st = self._lookup_acc_arrays(
            self._acc_jpsi_by_level, sublead_pt, sublead_abs_y, min_total_fn)
        a_phi_eff, a_phi_err, a_phi_lvl, a_phi_st = self._lookup_acc_arrays(
            self._acc_phi_by_level, phi_pt, phi_abs_y, min_total_fn)
        pa_eff, pa_err, pa_lvl, pa_st = self._lookup_pa5d_arrays(
            self._pa5d_by_level, lead_pt, sublead_pt, phi_pt, lead_abs_y, sublead_abs_y, min_total_fn)

        # Combine status
        status = np.full(n_events, STATUS_OK, dtype=np.int32)
        missing = np.zeros(n_events, dtype=bool)
        invalid = np.zeros(n_events, dtype=bool)
        for st in (a_lead_st, a_sublead_st, a_phi_st, pa_st):
            missing |= st == STATUS_MISSING_BIN
            invalid |= st == STATUS_INVALID_EFFICIENCY
        status[invalid] = STATUS_INVALID_EFFICIENCY
        status[missing] = STATUS_MISSING_BIN

        # Combined efficiency
        efficiency = a_lead_eff * a_sublead_eff * a_phi_eff * pa_eff
        invalid_eff = ~np.isfinite(efficiency) | (efficiency <= 0.0)
        status[(status == STATUS_OK) & invalid_eff] = STATUS_INVALID_EFFICIENCY

        weight = np.full(n_events, np.nan, dtype=np.float64)
        ok = status == STATUS_OK
        weight[ok] = 1.0 / efficiency[ok]
        efficiency[~ok] = np.nan

        # Relative uncertainty
        rel_var = np.zeros(n_events, dtype=np.float64)
        for eff_arr, err_arr in [(a_lead_eff, a_lead_err), (a_sublead_eff, a_sublead_err),
                                  (a_phi_eff, a_phi_err), (pa_eff, pa_err)]:
            valid_err = np.isfinite(err_arr) & (eff_arr > 0.0)
            rel_var[valid_err] += (err_arr[valid_err] / eff_arr[valid_err]) ** 2
        weight_err = np.full(n_events, np.nan, dtype=np.float64)
        has_rel_var = ok & (rel_var > 0.0)
        weight_err[has_rel_var] = weight[has_rel_var] * np.sqrt(rel_var[has_rel_var])

        # Fallback component count
        fallback_components = np.zeros(n_events, dtype=np.int32)
        for lvl_arr in (a_lead_lvl, a_sublead_lvl, a_phi_lvl, pa_lvl):
            fallback_components += (ok & (lvl_arr != "fine")).astype(np.int32)

        # MC stat uncertainty (simplified: use post-acceptance 5D uncertainty)
        mc_stat_var = 0.0
        for i in range(n_events):
            if not ok[i]:
                continue
            # Only propagate post-acceptance 5D stat uncertainty for now
            if np.isfinite(pa_err[i]) and pa_eff[i] > 0.0:
                mc_stat_var += (weight[i] * pa_err[i] / pa_eff[i]) ** 2

        return FactorizedCorrectionArrays(
            efficiency=efficiency,
            weight=weight,
            weight_err=weight_err,
            status=status,
            fallback_components=fallback_components,
            mc_stat_unc=float(math.sqrt(mc_stat_var)),
        )


def load_factorized_correction_map(
    sample_dir: str | Path,
    *,
    n_min_fine: int = 30,
    n_min_coarse: int = 50,
) -> FactorizedCorrectionMap:
    sample_dir = Path(sample_dir)
    maps_dir = sample_dir / "maps"
    maps: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for factor_name in FactorizedCorrectionMap.REQUIRED_FACTORS:
        path = maps_dir / f"{factor_name}.parquet"
        if not path.exists():
            missing.append(str(path))
            continue
        maps[factor_name] = pd.read_parquet(path)
    if missing:
        raise FileNotFoundError("Missing factorized correction map file(s): " + ", ".join(missing))
    return FactorizedCorrectionMap(maps, source=maps_dir, n_min_fine=n_min_fine, n_min_coarse=n_min_coarse)


def resolve_efficiency_map_path(
    *,
    efficiency_map: str | Path | None = None,
    efficiency_dir: str | Path | None = None,
    efficiency_sample: str | None = None,
) -> Path:
    if efficiency_map is not None:
        path = Path(efficiency_map)
        if not path.exists():
            raise FileNotFoundError(f"Efficiency map does not exist: {path}")
        return path

    if efficiency_dir is None or not efficiency_sample:
        raise ValueError("Provide either --efficiency-map or both --efficiency-dir and --efficiency-sample")

    sample_dir = Path(efficiency_dir) / efficiency_sample
    candidates = (
        sample_dir / "efficiency_maps.parquet",
        sample_dir / "derived" / "conditional_efficiency_maps.parquet",
    )
    for path in candidates:
        if path.exists():
            return path
    tried = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"No efficiency map found for sample {efficiency_sample!r}. Tried: {tried}")


def load_efficiency_correction_map(
    *,
    efficiency_map: str | Path | None = None,
    efficiency_dir: str | Path | None = None,
    efficiency_sample: str | None = None,
    step: str = DEFAULT_EFFICIENCY_STEP,
    map_type: str = DEFAULT_MAP_TYPE,
    denominator: Literal["absolute", "conditional"] = "absolute",
    min_total_fine: int = 0,
    min_total_coarse: int = 0,
) -> EfficiencyCorrectionMap:
    map_path = resolve_efficiency_map_path(
        efficiency_map=efficiency_map,
        efficiency_dir=efficiency_dir,
        efficiency_sample=efficiency_sample,
    )
    frame = pd.read_parquet(map_path)

    fallback_frames: list[pd.DataFrame] | None = None
    fallback_min_total: list[int] | None = None

    if map_type == "correlated_5d":
        # coarse fallback: 3D pT-only correlated map
        coarse = frame.loc[(frame["map_type"] == "correlated_3d") & (frame["step"] == step)].copy()
        if not coarse.empty:
            fallback_frames = [coarse]
            fallback_min_total = [min_total_coarse]
        # inclusive fallback: always cascades to 3D first, then inclusive via
        # the same frame if 3D also misses
        inclusive = frame.loc[(frame["map_type"] == "inclusive") & (frame["step"] == step)].copy()
        if not inclusive.empty:
            if fallback_frames is None:
                fallback_frames = []
                fallback_min_total = []
            fallback_frames.append(inclusive)
            fallback_min_total.append(0)

    return EfficiencyCorrectionMap(
        frame,
        source=map_path,
        step=step,
        map_type=map_type,
        denominator=denominator,
        fallback_frames=fallback_frames,
        fallback_min_total=fallback_min_total,
        fine_min_total=min_total_fine if map_type == "correlated_5d" else 0,
    )


def load_hybrid_correction_map(
    sample_dir: str | Path,
    *,
    n_min_fine: int = 30,
    n_min_coarse: int = 50,
) -> HybridCorrectionMap:
    """Load a HybridCorrectionMap from factorized acceptance + post-acceptance 5D maps."""
    sample_dir = Path(sample_dir)
    maps_dir = sample_dir / "maps"

    acc_jpsi_path = maps_dir / "acceptance_jpsi.parquet"
    acc_phi_path = maps_dir / "acceptance_phi.parquet"
    pa5d_path = maps_dir / "post_acceptance_5d.parquet"

    missing: list[str] = []
    for p in [acc_jpsi_path, acc_phi_path, pa5d_path]:
        if not p.exists():
            missing.append(str(p))
    if missing:
        raise FileNotFoundError("Missing hybrid correction map file(s): " + ", ".join(missing))

    return HybridCorrectionMap(
        acceptance_jpsi=pd.read_parquet(acc_jpsi_path),
        acceptance_phi=pd.read_parquet(acc_phi_path),
        post_acceptance_5d=pd.read_parquet(pa5d_path),
        source=maps_dir,
        n_min_fine=n_min_fine,
        n_min_coarse=n_min_coarse,
    )


def _fill_from_correction(buffers: dict[str, Any], correction: EfficiencyCorrection) -> None:
    buffers["effcorr_efficiency"][0] = correction.efficiency
    buffers["effcorr_weight"][0] = correction.weight
    buffers["effcorr_eff_err_low"][0] = correction.err_low
    buffers["effcorr_eff_err_high"][0] = correction.err_high
    buffers["effcorr_x_bin"][0] = correction.x_bin
    buffers["effcorr_y_bin"][0] = correction.y_bin
    buffers["effcorr_z_bin"][0] = correction.z_bin
    buffers["effcorr_status"][0] = correction.status
    if "effcorr_u_bin" in buffers:
        buffers["effcorr_u_bin"][0] = correction.u_bin
    if "effcorr_v_bin" in buffers:
        buffers["effcorr_v_bin"][0] = correction.v_bin


def _summarize(corrections: list[EfficiencyCorrection]) -> CorrectionSummary:
    entries = len(corrections)
    ok = sum(item.status == STATUS_OK for item in corrections)
    missing = sum(item.status == STATUS_MISSING_BIN for item in corrections)
    invalid = sum(item.status == STATUS_INVALID_EFFICIENCY for item in corrections)
    ok_eff = np.asarray([item.efficiency for item in corrections if item.status == STATUS_OK], dtype=float)
    ok_weight = np.asarray([item.weight for item in corrections if item.status == STATUS_OK], dtype=float)
    return CorrectionSummary(
        entries=entries,
        ok=ok,
        missing_bin=missing,
        invalid_efficiency=invalid,
        min_efficiency=float(np.min(ok_eff)) if ok_eff.size else math.nan,
        max_efficiency=float(np.max(ok_eff)) if ok_eff.size else math.nan,
        mean_weight=float(np.mean(ok_weight)) if ok_weight.size else math.nan,
    )


def annotate_root_tree_with_efficiency(
    *,
    input_file: str | Path,
    output_file: str | Path,
    correction_map: EfficiencyCorrectionMap,
    tree_name: str = "selected",
    on_missing: Literal["error", "unity", "drop"] = "error",
) -> CorrectionSummary:
    import ROOT

    input_path = str(input_file)
    output_path = str(output_file)
    ensure_parent_dir(output_path)

    fin = ROOT.TFile.Open(input_path)
    tree = fin.Get(tree_name) if fin else None
    if not tree:
        if fin:
            fin.Close()
        raise RuntimeError(f"Input tree {tree_name!r} not found in {input_path}")

    required_branches = ["sel_Jpsi_1_pt", "sel_Jpsi_2_pt", "sel_Phi_pt"]
    if correction_map.has_u:
        required_branches.extend(["sel_Jpsi_1_y", "sel_Jpsi_2_y"])
    available = {branch.GetName() for branch in tree.GetListOfBranches()}
    missing = sorted(set(required_branches) - available)
    if missing:
        fin.Close()
        raise RuntimeError(f"Input tree is missing correction branch(es): {', '.join(missing)}")

    use_rapidity = correction_map.has_u
    raw_corrections: list[EfficiencyCorrection] = []
    n_entries = int(tree.GetEntries())
    for idx in range(n_entries):
        tree.GetEntry(idx)
        kwargs: dict = {}
        if use_rapidity:
            kwargs["jpsi1_abs_y"] = abs(float(getattr(tree, "sel_Jpsi_1_y")))
            kwargs["jpsi2_abs_y"] = abs(float(getattr(tree, "sel_Jpsi_2_y")))
        raw_corrections.append(
            correction_map.lookup(
                float(getattr(tree, "sel_Jpsi_1_pt")),
                float(getattr(tree, "sel_Jpsi_2_pt")),
                float(getattr(tree, "sel_Phi_pt")),
                **kwargs,
            )
        )

    raw_summary = _summarize(raw_corrections)
    if on_missing == "error" and (raw_summary.missing_bin or raw_summary.invalid_efficiency):
        fin.Close()
        raise RuntimeError(
            "Efficiency correction failed: "
            f"missing_bin={raw_summary.missing_bin}, invalid_efficiency={raw_summary.invalid_efficiency}. "
            "Use --on-missing unity or --on-missing drop only for debugging."
        )

    fout = ROOT.TFile(output_path, "RECREATE")
    out_tree = tree.CloneTree(0)
    buffers: dict[str, Any] = {
        "effcorr_efficiency": array.array("d", [0.0]),
        "effcorr_weight": array.array("d", [0.0]),
        "effcorr_eff_err_low": array.array("d", [0.0]),
        "effcorr_eff_err_high": array.array("d", [0.0]),
        "effcorr_x_bin": array.array("i", [0]),
        "effcorr_y_bin": array.array("i", [0]),
        "effcorr_z_bin": array.array("i", [0]),
        "effcorr_status": array.array("i", [0]),
    }
    if use_rapidity:
        buffers["effcorr_u_bin"] = array.array("i", [0])
        buffers["effcorr_v_bin"] = array.array("i", [0])
    for name, buffer in buffers.items():
        suffix = "/I" if (name.endswith("_bin") and name != "effcorr_weight") or name == "effcorr_status" else "/D"
        out_tree.Branch(name, buffer, f"{name}{suffix}")

    written_corrections: list[EfficiencyCorrection] = []
    for idx, raw_correction in enumerate(raw_corrections):
        tree.GetEntry(idx)
        correction = raw_correction
        if correction.status != STATUS_OK:
            if on_missing == "unity":
                correction = EfficiencyCorrection(
                    efficiency=1.0,
                    weight=1.0,
                    err_low=math.nan,
                    err_high=math.nan,
                    x_bin=correction.x_bin,
                    y_bin=correction.y_bin,
                    z_bin=correction.z_bin,
                    u_bin=correction.u_bin,
                    v_bin=correction.v_bin,
                    status=correction.status,
                )
            elif on_missing == "drop":
                continue
            elif on_missing != "error":
                fin.Close()
                fout.Close()
                raise ValueError(f"Unsupported on_missing mode: {on_missing}")
        written_corrections.append(correction)
        _fill_from_correction(buffers, correction)
        out_tree.Fill()

    summary = _summarize(written_corrections)

    metadata = {
        "source": str(correction_map.source),
        "step": correction_map.step,
        "map_type": correction_map.map_type,
        "denominator": correction_map.denominator,
        "on_missing": on_missing,
    }
    out_tree.Write()
    for key, value in metadata.items():
        ROOT.TNamed(f"effcorr_{key}", str(value)).Write()
    fout.Close()
    fin.Close()
    return summary

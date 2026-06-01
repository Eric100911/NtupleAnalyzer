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


@dataclass(frozen=True)
class CorrectionSummary:
    entries: int
    ok: int
    missing_bin: int
    invalid_efficiency: int
    min_efficiency: float
    max_efficiency: float
    mean_weight: float


class EfficiencyCorrectionMap:
    def __init__(
        self,
        frame: pd.DataFrame,
        *,
        source: Path,
        step: str,
        map_type: str = DEFAULT_MAP_TYPE,
        denominator: Literal["absolute", "conditional"] = "absolute",
    ) -> None:
        self.source = source
        self.step = step
        self.map_type = map_type
        self.denominator = denominator
        self.frame = self._prepare_frame(frame, step=step, map_type=map_type, denominator=denominator)

        self.x_min = self.frame["x_min"].to_numpy(dtype=float)
        self.x_max = self.frame["x_max"].to_numpy(dtype=float)
        self.y_min = self.frame["y_min"].to_numpy(dtype=float)
        self.y_max = self.frame["y_max"].to_numpy(dtype=float)
        self.z_min = self.frame["z_min"].to_numpy(dtype=float)
        self.z_max = self.frame["z_max"].to_numpy(dtype=float)
        self.efficiency = self.frame["lookup_efficiency"].to_numpy(dtype=float)
        self.err_low = self.frame["lookup_err_low"].to_numpy(dtype=float)
        self.err_high = self.frame["lookup_err_high"].to_numpy(dtype=float)
        self.x_bin = self.frame["x_bin"].to_numpy(dtype=int)
        self.y_bin = self.frame["y_bin"].to_numpy(dtype=int)
        self.z_bin = self.frame["z_bin"].to_numpy(dtype=int)

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
        selected.sort_values(["x_bin", "y_bin", "z_bin"], inplace=True)
        return selected.reset_index(drop=True)

    def lookup(self, jpsi1_pt: float, jpsi2_pt: float, phi_pt: float) -> EfficiencyCorrection:
        if not (math.isfinite(jpsi1_pt) and math.isfinite(jpsi2_pt) and math.isfinite(phi_pt)):
            return self._missing()
        lead = max(float(jpsi1_pt), float(jpsi2_pt))
        sublead = min(float(jpsi1_pt), float(jpsi2_pt))
        phi = float(phi_pt)
        matches = (
            (self.x_min <= lead)
            & (lead < self.x_max)
            & (self.y_min <= sublead)
            & (sublead < self.y_max)
            & (self.z_min <= phi)
            & (phi < self.z_max)
        )
        indices = np.flatnonzero(matches)
        if indices.size == 0:
            return self._missing()
        idx = int(indices[0])
        eff = float(self.efficiency[idx])
        if not math.isfinite(eff) or eff <= 0.0:
            return EfficiencyCorrection(
                efficiency=eff,
                weight=math.nan,
                err_low=float(self.err_low[idx]),
                err_high=float(self.err_high[idx]),
                x_bin=int(self.x_bin[idx]),
                y_bin=int(self.y_bin[idx]),
                z_bin=int(self.z_bin[idx]),
                status=STATUS_INVALID_EFFICIENCY,
            )
        return EfficiencyCorrection(
            efficiency=eff,
            weight=1.0 / eff,
            err_low=float(self.err_low[idx]),
            err_high=float(self.err_high[idx]),
            x_bin=int(self.x_bin[idx]),
            y_bin=int(self.y_bin[idx]),
            z_bin=int(self.z_bin[idx]),
            status=STATUS_OK,
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
) -> EfficiencyCorrectionMap:
    map_path = resolve_efficiency_map_path(
        efficiency_map=efficiency_map,
        efficiency_dir=efficiency_dir,
        efficiency_sample=efficiency_sample,
    )
    frame = pd.read_parquet(map_path)
    return EfficiencyCorrectionMap(frame, source=map_path, step=step, map_type=map_type, denominator=denominator)


def _fill_from_correction(buffers: dict[str, Any], correction: EfficiencyCorrection) -> None:
    buffers["effcorr_efficiency"][0] = correction.efficiency
    buffers["effcorr_weight"][0] = correction.weight
    buffers["effcorr_eff_err_low"][0] = correction.err_low
    buffers["effcorr_eff_err_high"][0] = correction.err_high
    buffers["effcorr_x_bin"][0] = correction.x_bin
    buffers["effcorr_y_bin"][0] = correction.y_bin
    buffers["effcorr_z_bin"][0] = correction.z_bin
    buffers["effcorr_status"][0] = correction.status


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

    required_branches = ("sel_Jpsi_1_pt", "sel_Jpsi_2_pt", "sel_Phi_pt")
    available = {branch.GetName() for branch in tree.GetListOfBranches()}
    missing = sorted(set(required_branches) - available)
    if missing:
        fin.Close()
        raise RuntimeError(f"Input tree is missing correction branch(es): {', '.join(missing)}")

    raw_corrections: list[EfficiencyCorrection] = []
    n_entries = int(tree.GetEntries())
    for idx in range(n_entries):
        tree.GetEntry(idx)
        raw_corrections.append(
            correction_map.lookup(
                float(getattr(tree, "sel_Jpsi_1_pt")),
                float(getattr(tree, "sel_Jpsi_2_pt")),
                float(getattr(tree, "sel_Phi_pt")),
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
    for name, buffer in buffers.items():
        suffix = "/I" if name.endswith("_bin") or name == "effcorr_status" else "/D"
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

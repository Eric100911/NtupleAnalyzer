from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .efficiency import (
    EfficiencyBinning,
    _bin_label,
    _merged_gen_events,
    jeffreys_efficiency_uncertainty,
)
from .io import ensure_dir, write_json, write_parquet


DEFAULT_FACTOR_NAMES = (
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

DEFAULT_EVENT_END_STEP = "Pri_assocPVPass"


@dataclass(frozen=True)
class FactorSpec:
    factor_name: str
    object_name: str
    numerator_col: str
    denominator_col: str
    x_axis: str
    y_axis: str | None = None
    z_axis: str | None = None
    x_edges: tuple[float, ...] | None = None
    y_edges: tuple[float, ...] | None = None
    z_edges: tuple[float, ...] | None = None
    coarse_axes: tuple[str, ...] = ("x",)


def _efficiency_row(base: dict, total: int, passed: int) -> dict:
    efficiency = float(passed / total) if total > 0 else np.nan
    jeffreys_eff, jeffreys_err = jeffreys_efficiency_uncertainty(total, passed)
    return {
        **base,
        "total": int(total),
        "passed": int(passed),
        "efficiency": efficiency,
        "err_low": jeffreys_err,
        "err_high": jeffreys_err,
        "err_sym": jeffreys_err,
        "jeffreys_efficiency": jeffreys_eff,
        "uncertainty_method": "jeffreys_symmetric",
    }


def _empty_map(factor_name: str) -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "map_type",
            "factor_name",
            "object",
            "step",
            "fallback_level",
            "x_axis",
            "y_axis",
            "z_axis",
            "x_bin",
            "y_bin",
            "z_bin",
            "x_min",
            "x_max",
            "y_min",
            "y_max",
            "z_min",
            "z_max",
            "x_label",
            "y_label",
            "z_label",
            "total",
            "passed",
            "efficiency",
            "err_low",
            "err_high",
            "err_sym",
            "jeffreys_efficiency",
            "uncertainty_method",
        ]
    ).assign(factor_name=factor_name)


def _axis_values(frame: pd.DataFrame, axis: str) -> np.ndarray:
    if axis == "jpsi_lead_pt":
        left = frame["jpsi_lead_pt"].to_numpy(dtype=float)
        right = frame["jpsi_sublead_pt"].to_numpy(dtype=float)
        return np.maximum(left, right)
    if axis == "jpsi_sublead_pt":
        left = frame["jpsi_lead_pt"].to_numpy(dtype=float)
        right = frame["jpsi_sublead_pt"].to_numpy(dtype=float)
        return np.minimum(left, right)
    if axis.endswith("_abs_y") and axis not in frame.columns:
        source = axis.removesuffix("_abs_y") + "_y"
        return np.abs(frame[source].to_numpy(dtype=float))
    return frame[axis].to_numpy(dtype=float)


def _bin_mask(values: np.ndarray, low: float, high: float) -> np.ndarray:
    return np.isfinite(values) & (values >= low) & (values < high)


def _append_rows_for_axes(
    rows: list[dict],
    frame: pd.DataFrame,
    spec: FactorSpec,
    *,
    fallback_level: str,
    axes: tuple[str, ...],
) -> None:
    axis_names = {"x": spec.x_axis, "y": spec.y_axis, "z": spec.z_axis}
    axis_edges = {"x": spec.x_edges, "y": spec.y_edges, "z": spec.z_edges}
    active_axes = tuple(axis for axis in axes if axis_names[axis] is not None and axis_edges[axis] is not None)
    values = {axis: _axis_values(frame, axis_names[axis]) for axis in active_axes}

    if not active_axes:
        denom = frame[spec.denominator_col].to_numpy(dtype=bool)
        passed = denom & frame[spec.numerator_col].to_numpy(dtype=bool)
        rows.append(
            _efficiency_row(
                {
                    "map_type": "factorized",
                    "factor_name": spec.factor_name,
                    "object": spec.object_name,
                    "step": spec.numerator_col,
                    "fallback_level": fallback_level,
                    "x_axis": "",
                    "y_axis": "",
                    "z_axis": "",
                    "x_bin": -1,
                    "y_bin": -1,
                    "z_bin": -1,
                    "x_min": np.nan,
                    "x_max": np.nan,
                    "y_min": np.nan,
                    "y_max": np.nan,
                    "z_min": np.nan,
                    "z_max": np.nan,
                    "x_label": "inclusive",
                    "y_label": "",
                    "z_label": "",
                },
                int(denom.sum()),
                int(passed.sum()),
            )
        )
        return

    ranges = [range(len(axis_edges[axis]) - 1) for axis in active_axes]
    for indices in np.ndindex(*[len(item) for item in ranges]):
        mask = np.ones(len(frame), dtype=bool)
        labels: dict[str, str] = {}
        bins: dict[str, int] = {}
        mins: dict[str, float] = {}
        maxs: dict[str, float] = {}
        for axis, pos in zip(active_axes, indices):
            edges = axis_edges[axis]
            idx = int(pos)
            bins[axis] = idx
            mins[axis] = float(edges[idx])
            maxs[axis] = float(edges[idx + 1])
            labels[axis] = _bin_label(edges, idx)
            mask &= _bin_mask(values[axis], mins[axis], maxs[axis])

        subset = frame.loc[mask]
        denom = subset[spec.denominator_col].to_numpy(dtype=bool)
        passed = denom & subset[spec.numerator_col].to_numpy(dtype=bool)
        rows.append(
            _efficiency_row(
                {
                    "map_type": "factorized",
                    "factor_name": spec.factor_name,
                    "object": spec.object_name,
                    "step": spec.numerator_col,
                    "fallback_level": fallback_level,
                    "x_axis": axis_names["x"] if "x" in active_axes else "",
                    "y_axis": axis_names["y"] if "y" in active_axes else "",
                    "z_axis": axis_names["z"] if "z" in active_axes else "",
                    "x_bin": bins.get("x", -1),
                    "y_bin": bins.get("y", -1),
                    "z_bin": bins.get("z", -1),
                    "x_min": mins.get("x", np.nan),
                    "x_max": maxs.get("x", np.nan),
                    "y_min": mins.get("y", np.nan),
                    "y_max": maxs.get("y", np.nan),
                    "z_min": mins.get("z", np.nan),
                    "z_max": maxs.get("z", np.nan),
                    "x_label": labels.get("x", ""),
                    "y_label": labels.get("y", ""),
                    "z_label": labels.get("z", ""),
                },
                int(denom.sum()),
                int(passed.sum()),
            )
        )


def _build_factor_map(frame: pd.DataFrame, spec: FactorSpec) -> pd.DataFrame:
    rows: list[dict] = []
    _append_rows_for_axes(rows, frame, spec, fallback_level="fine", axes=("x", "y", "z"))
    _append_rows_for_axes(rows, frame, spec, fallback_level="coarse", axes=spec.coarse_axes)
    _append_rows_for_axes(rows, frame, spec, fallback_level="inclusive", axes=())
    return pd.DataFrame(rows) if rows else _empty_map(spec.factor_name)


def _jpsi_object_frame(merged: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for prefix in ("jpsi_lead", "jpsi_sublead"):
        frames.append(
            pd.DataFrame(
                {
                    "pt": merged[f"{prefix}_pt"].to_numpy(dtype=float),
                    "abs_y": np.abs(merged[f"{prefix}_y"].to_numpy(dtype=float)),
                    "full_gen": merged["full_gen"].to_numpy(dtype=int),
                    "fiducial": merged[f"{prefix}_fiducial"].to_numpy(dtype=int),
                    "muonRECO": merged[f"{prefix}_muonRECO"].to_numpy(dtype=int),
                    "muonID": merged[f"{prefix}_muonID"].to_numpy(dtype=int),
                    "dimuon": merged[f"{prefix}_dimuon"].to_numpy(dtype=int),
                }
            )
        )
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _phi_object_frame(merged: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pt": merged["phi_pt"].to_numpy(dtype=float),
            "abs_y": np.abs(merged["phi_y"].to_numpy(dtype=float)),
            "full_gen": merged["full_gen"].to_numpy(dtype=int),
            "fiducial": merged["phi_fiducial"].to_numpy(dtype=int),
            "kaonRECO": merged["phi_kaonRECO"].to_numpy(dtype=int),
            "kaonID": merged["phi_kaonID"].to_numpy(dtype=int),
            "dikaon": merged["phi_dikaon"].to_numpy(dtype=int),
        }
    )


def factor_specs(
    binning: EfficiencyBinning,
    *,
    event_end_step: str = DEFAULT_EVENT_END_STEP,
) -> dict[str, tuple[pd.DataFrame | None, FactorSpec]]:
    return {
        "acceptance_jpsi": (
            None,
            FactorSpec("acceptance_jpsi", "jpsi", "fiducial", "full_gen", "pt", "abs_y", x_edges=binning.jpsi_pt_edges, y_edges=binning.object_abs_y_edges),
        ),
        "eff_muReco_jpsi": (
            None,
            FactorSpec("eff_muReco_jpsi", "jpsi", "muonRECO", "fiducial", "pt", "abs_y", x_edges=binning.jpsi_pt_edges, y_edges=binning.object_abs_y_edges),
        ),
        "eff_muID_jpsi": (
            None,
            FactorSpec("eff_muID_jpsi", "jpsi", "muonID", "muonRECO", "pt", "abs_y", x_edges=binning.jpsi_pt_edges, y_edges=binning.object_abs_y_edges),
        ),
        "eff_dimuon_jpsi": (
            None,
            FactorSpec("eff_dimuon_jpsi", "jpsi", "dimuon", "muonID", "pt", "abs_y", x_edges=binning.jpsi_pt_edges, y_edges=binning.object_abs_y_edges),
        ),
        "acceptance_phi": (
            None,
            FactorSpec("acceptance_phi", "phi", "fiducial", "full_gen", "pt", "abs_y", x_edges=binning.phi_pt_edges, y_edges=binning.object_abs_y_edges),
        ),
        "eff_kaonReco_phi": (
            None,
            FactorSpec("eff_kaonReco_phi", "phi", "kaonRECO", "fiducial", "pt", "abs_y", x_edges=binning.phi_pt_edges, y_edges=binning.object_abs_y_edges),
        ),
        "eff_kaonID_phi": (
            None,
            FactorSpec("eff_kaonID_phi", "phi", "kaonID", "kaonRECO", "pt", "abs_y", x_edges=binning.phi_pt_edges, y_edges=binning.object_abs_y_edges),
        ),
        "eff_dikaon_phi": (
            None,
            FactorSpec("eff_dikaon_phi", "phi", "dikaon", "kaonID", "pt", "abs_y", x_edges=binning.phi_pt_edges, y_edges=binning.object_abs_y_edges),
        ),
        "eff_hlt": (
            None,
            FactorSpec("eff_hlt", "event", "hlt_muon_matched", "s_cand", "jpsi_lead_pt", "jpsi_sublead_pt", x_edges=binning.jpsi_pt_edges, y_edges=binning.jpsi_pt_edges, coarse_axes=()),
        ),
        "eff_4mu_vtx": (
            None,
            FactorSpec("eff_4mu_vtx", "event", "four_muon_vtx", "hlt_muon_matched", "jpsi_lead_pt", "jpsi_sublead_pt", x_edges=binning.jpsi_pt_edges, y_edges=binning.jpsi_pt_edges, coarse_axes=()),
        ),
        "eff_triOnia": (
            None,
            FactorSpec("eff_triOnia", "event", event_end_step, "four_muon_vtx", "jpsi_lead_pt", "jpsi_sublead_pt", "phi_pt", binning.jpsi_pt_edges, binning.jpsi_pt_edges, binning.phi_pt_edges, coarse_axes=("x", "y")),
        ),
    }


def build_factorized_maps_for_sample(
    input_sample_dir: Path,
    output_maps_dir: Path,
    *,
    binning: EfficiencyBinning | None = None,
    event_end_step: str = DEFAULT_EVENT_END_STEP,
) -> dict[str, Path]:
    binning = binning or EfficiencyBinning()
    gen_path = input_sample_dir / "gen_systems.parquet"
    event_path = input_sample_dir / "event_step_flags.parquet"
    if not gen_path.exists() or not event_path.exists():
        raise FileNotFoundError(f"Missing merged parquet inputs in {input_sample_dir}")

    gen_df = pd.read_parquet(gen_path)
    event_df = pd.read_parquet(event_path)
    merged = _merged_gen_events(gen_df, event_df)
    if merged.empty:
        raise RuntimeError(f"No merged gen/event rows for {input_sample_dir}")
    if event_end_step not in merged.columns:
        raise RuntimeError(f"Requested event end step {event_end_step!r} is not present in {event_path}")

    ensure_dir(output_maps_dir)
    jpsi_frame = _jpsi_object_frame(merged)
    phi_frame = _phi_object_frame(merged)
    frame_by_object = {"jpsi": jpsi_frame, "phi": phi_frame, "event": merged}
    written: dict[str, Path] = {}
    for factor_name, (_, spec) in factor_specs(binning, event_end_step=event_end_step).items():
        frame = frame_by_object[spec.object_name]
        factor_df = _build_factor_map(frame, spec)
        out_path = output_maps_dir / f"{factor_name}.parquet"
        write_parquet(factor_df, out_path)
        written[factor_name] = out_path

    manifest = {
        "stage": "factorized_efficiency_maps",
        "source": str(input_sample_dir.resolve()),
        "event_end_step": event_end_step,
        "n_gen_rows": int(len(gen_df)),
        "n_event_rows": int(len(event_df)),
        "n_merged_rows": int(len(merged)),
        "maps": {name: path.name for name, path in written.items()},
    }
    write_json(manifest, output_maps_dir / "manifest.json")
    return written


def build_factorized_maps(
    input_dir: Path,
    *,
    samples: Iterable[str],
    event_end_step: str = DEFAULT_EVENT_END_STEP,
) -> dict[str, dict[str, Path]]:
    binning = EfficiencyBinning()
    outputs: dict[str, dict[str, Path]] = {}
    for sample in samples:
        outputs[sample] = build_factorized_maps_for_sample(
            input_dir / sample,
            input_dir / sample / "maps",
            binning=binning,
            event_end_step=event_end_step,
        )
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build factorized efficiency correction maps from merged parquet products")
    parser.add_argument("--input-dir", required=True, help="Merged efficiency directory containing sample subdirectories")
    parser.add_argument("--samples", nargs="+", required=True, help="Sample directories to process")
    parser.add_argument("--event-end-step", default=DEFAULT_EVENT_END_STEP, help="Final event/PV numerator step")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    print(f"Building factorized maps in {input_dir}", flush=True)
    for sample in args.samples:
        print(f"[{sample}] start", flush=True)
        written = build_factorized_maps_for_sample(
            input_dir / sample,
            input_dir / sample / "maps",
            event_end_step=args.event_end_step,
        )
        print(f"[{sample}] wrote {len(written)} maps to {input_dir / sample / 'maps'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

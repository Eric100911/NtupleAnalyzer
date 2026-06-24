from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .build_factorized_maps import build_factorized_maps_for_sample
from .corrections import FactorizedCorrectionMap, STATUS_OK, load_factorized_correction_map
from .efficiency import EfficiencyBinning, _bin_label, _merged_gen_events
from .io import ensure_dir, write_json, write_parquet


DEFAULT_OUTPUT_DIRNAME = "scand_factorization"
DEFAULT_STAGES = ("fiducial", "reco", "id", "quality")
STAGE_DISPLAY = {
    "fiducial": "all_fiducial",
    "reco": "all_reco",
    "id": "all_id",
    "quality": "s_cand",
}

OBJECT_FACTORS_BY_STAGE = {
    "fiducial": (
        ("jpsi_lead", "acceptance_jpsi"),
        ("jpsi_sublead", "acceptance_jpsi"),
        ("phi", "acceptance_phi"),
    ),
    "reco": (
        ("jpsi_lead", "eff_muReco_jpsi"),
        ("jpsi_sublead", "eff_muReco_jpsi"),
        ("phi", "eff_kaonReco_phi"),
    ),
    "id": (
        ("jpsi_lead", "eff_muID_jpsi"),
        ("jpsi_sublead", "eff_muID_jpsi"),
        ("phi", "eff_kaonID_phi"),
    ),
    "quality": (
        ("jpsi_lead", "eff_dimuon_jpsi"),
        ("jpsi_sublead", "eff_dimuon_jpsi"),
        ("phi", "eff_dikaon_phi"),
    ),
}

OBJECT_FLAGS_BY_STAGE = {
    "fiducial": ("jpsi_lead_fiducial", "jpsi_sublead_fiducial", "phi_fiducial"),
    "reco": ("jpsi_lead_muonRECO", "jpsi_sublead_muonRECO", "phi_kaonRECO"),
    "id": ("jpsi_lead_muonID", "jpsi_sublead_muonID", "phi_kaonID"),
    "quality": ("jpsi_lead_dimuon", "jpsi_sublead_dimuon", "phi_dikaon"),
}


@dataclass(frozen=True)
class ScandFactorizationOutputs:
    stage_bins: Path
    scand_bins: Path
    manifest: Path


def _sample_names(input_dir: Path, requested: Sequence[str] | None) -> list[str]:
    if requested:
        return [str(sample) for sample in requested]
    samples = []
    for child in sorted(input_dir.iterdir()):
        if not child.is_dir():
            continue
        if (child / "gen_systems.parquet").exists() and (child / "event_step_flags.parquet").exists():
            samples.append(child.name)
    if not samples:
        raise FileNotFoundError(f"No sample directories with merged parquet inputs found under {input_dir}")
    return samples


def _axis_bins(values: np.ndarray, edges: tuple[float, ...]) -> np.ndarray:
    bins = np.searchsorted(np.asarray(edges, dtype=float), values, side="right") - 1
    valid = np.isfinite(values) & (bins >= 0) & (bins < len(edges) - 1)
    return np.where(valid, bins, -1).astype(np.int32)


def _object_values(frame: pd.DataFrame, obj: str) -> tuple[np.ndarray, np.ndarray]:
    if obj == "jpsi_lead":
        return frame["jpsi_lead_pt"].to_numpy(dtype=float), np.abs(frame["jpsi_lead_y"].to_numpy(dtype=float))
    if obj == "jpsi_sublead":
        return frame["jpsi_sublead_pt"].to_numpy(dtype=float), np.abs(frame["jpsi_sublead_y"].to_numpy(dtype=float))
    if obj == "phi":
        return frame["phi_pt"].to_numpy(dtype=float), np.abs(frame["phi_y"].to_numpy(dtype=float))
    raise ValueError(f"Unknown object role {obj!r}")


def _stage_product_arrays(
    frame: pd.DataFrame,
    correction_map: FactorizedCorrectionMap,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    n_events = len(frame)
    product = np.ones(n_events, dtype=np.float64)
    ok = np.ones(n_events, dtype=bool)
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for stage in DEFAULT_STAGES:
        for obj, factor_name in OBJECT_FACTORS_BY_STAGE[stage]:
            pt, abs_y = _object_values(frame, obj)
            component = correction_map._lookup_component_arrays(
                component_name=f"{obj}_{stage}",
                factor_name=factor_name,
                x_values=pt,
                y_values=abs_y,
            )
            product *= component.efficiency
            ok &= component.status == STATUS_OK
        out[stage] = (product.copy(), ok.copy())
    return out


def _cumulative_direct_masks(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    mask = frame["full_gen"].to_numpy(dtype=bool)
    out: dict[str, np.ndarray] = {}
    for stage in DEFAULT_STAGES:
        for col in OBJECT_FLAGS_BY_STAGE[stage]:
            if col not in frame.columns:
                raise ValueError(f"Required event flag column {col!r} is missing")
            mask &= frame[col].to_numpy(dtype=bool)
        out[stage] = mask.copy()
    if "s_cand" in frame.columns:
        out["quality"] = frame["s_cand"].to_numpy(dtype=bool)
    return out


def quantify_sample_scand_factorization(
    sample_dir: str | Path,
    *,
    n_min_fine: int = 30,
    n_min_coarse: int = 50,
    build_maps: bool = False,
    binning: EfficiencyBinning | None = None,
) -> pd.DataFrame:
    sample_path = Path(sample_dir)
    sample = sample_path.name
    binning = binning or EfficiencyBinning()
    if build_maps:
        build_factorized_maps_for_sample(sample_path, sample_path / "maps", binning=binning)

    gen_path = sample_path / "gen_systems.parquet"
    event_path = sample_path / "event_step_flags.parquet"
    if not gen_path.exists() or not event_path.exists():
        raise FileNotFoundError(f"Missing merged parquet inputs for {sample}: {gen_path}, {event_path}")

    gen_df = pd.read_parquet(gen_path)
    event_df = pd.read_parquet(event_path)
    merged = _merged_gen_events(gen_df, event_df)
    if merged.empty:
        raise RuntimeError(f"No merged gen/event rows for {sample}")

    correction_map = load_factorized_correction_map(
        sample_path,
        n_min_fine=n_min_fine,
        n_min_coarse=n_min_coarse,
    )
    direct_masks = _cumulative_direct_masks(merged)
    stage_products = _stage_product_arrays(merged, correction_map)

    lead_pt = np.maximum(merged["jpsi_lead_pt"].to_numpy(dtype=float), merged["jpsi_sublead_pt"].to_numpy(dtype=float))
    sublead_pt = np.minimum(merged["jpsi_lead_pt"].to_numpy(dtype=float), merged["jpsi_sublead_pt"].to_numpy(dtype=float))
    phi_pt = merged["phi_pt"].to_numpy(dtype=float)
    x_bin = _axis_bins(lead_pt, binning.jpsi_pt_edges)
    y_bin = _axis_bins(sublead_pt, binning.jpsi_pt_edges)
    z_bin = _axis_bins(phi_pt, binning.phi_pt_edges)
    in_range = (x_bin >= 0) & (y_bin >= 0) & (z_bin >= 0) & merged["full_gen"].to_numpy(dtype=bool)

    rows: list[dict] = []
    for xb in range(len(binning.jpsi_pt_edges) - 1):
        for yb in range(len(binning.jpsi_pt_edges) - 1):
            for zb in range(len(binning.phi_pt_edges) - 1):
                bin_mask = in_range & (x_bin == xb) & (y_bin == yb) & (z_bin == zb)
                n_total = int(np.count_nonzero(bin_mask))
                if n_total == 0:
                    continue
                for stage in DEFAULT_STAGES:
                    product, product_ok = stage_products[stage]
                    ok_mask = bin_mask & product_ok & np.isfinite(product) & (product > 0.0)
                    n_product_ok = int(np.count_nonzero(ok_mask))
                    product_sum = float(np.sum(product[ok_mask]))
                    product_mean = product_sum / n_product_ok if n_product_ok > 0 else math.nan
                    direct_passed = int(np.count_nonzero(bin_mask & direct_masks[stage]))
                    direct_eff = direct_passed / n_total
                    direct_passed_product_ok = int(np.count_nonzero(ok_mask & direct_masks[stage]))
                    direct_eff_product_ok = direct_passed_product_ok / n_product_ok if n_product_ok > 0 else math.nan
                    ratio = direct_eff_product_ok / product_mean if product_mean > 0.0 else math.nan
                    rows.append(
                        {
                            "sample": sample,
                            "stage": stage,
                            "efficiency_name": STAGE_DISPLAY[stage],
                            "x_bin": xb,
                            "y_bin": yb,
                            "z_bin": zb,
                            "jpsi_lead_pt_bin": _bin_label(binning.jpsi_pt_edges, xb),
                            "jpsi_sublead_pt_bin": _bin_label(binning.jpsi_pt_edges, yb),
                            "phi_pt_bin": _bin_label(binning.phi_pt_edges, zb),
                            "n_full_gen": n_total,
                            "n_direct_passed": direct_passed,
                            "direct_efficiency": float(direct_eff),
                            "n_direct_passed_product_ok": direct_passed_product_ok,
                            "direct_efficiency_product_ok": float(direct_eff_product_ok),
                            "product_efficiency_sum": product_sum,
                            "product_efficiency_mean": float(product_mean),
                            "direct_over_product": float(ratio),
                            "direct_minus_product": float(direct_eff_product_ok - product_mean),
                            "n_product_ok": n_product_ok,
                            "n_product_failed": int(n_total - n_product_ok),
                        }
                    )
    return pd.DataFrame(rows)


def quantify_scand_factorization(
    input_dir: str | Path,
    *,
    samples: Sequence[str] | None = None,
    output_dir: str | Path | None = None,
    n_min_fine: int = 30,
    n_min_coarse: int = 50,
    build_maps: bool = False,
) -> ScandFactorizationOutputs:
    input_path = Path(input_dir)
    sample_names = _sample_names(input_path, samples)
    out_path = Path(output_dir) if output_dir is not None else input_path / DEFAULT_OUTPUT_DIRNAME
    ensure_dir(out_path)

    frames = [
        quantify_sample_scand_factorization(
            input_path / sample,
            n_min_fine=n_min_fine,
            n_min_coarse=n_min_coarse,
            build_maps=build_maps,
        )
        for sample in sample_names
    ]
    stage_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    scand_df = stage_df.loc[stage_df["stage"] == "quality"].reset_index(drop=True)

    stage_path = out_path / "scand_factorization_stage_bins.parquet"
    scand_path = out_path / "scand_factorization_bins.parquet"
    write_parquet(stage_df, stage_path)
    write_parquet(scand_df, scand_path)
    stage_df.to_csv(out_path / "scand_factorization_stage_bins.csv", index=False)
    scand_df.to_csv(out_path / "scand_factorization_bins.csv", index=False)

    manifest_path = out_path / "scand_factorization_manifest.json"
    write_json(
        {
            "stage": "scand_factorization_diagnostic",
            "input_dir": str(input_path.resolve()),
            "output_dir": str(out_path.resolve()),
            "samples": sample_names,
            "n_min_fine": int(n_min_fine),
            "n_min_coarse": int(n_min_coarse),
            "build_maps": bool(build_maps),
            "artifacts": {
                "stage_bins_parquet": stage_path.name,
                "stage_bins_csv": "scand_factorization_stage_bins.csv",
                "scand_bins_parquet": scand_path.name,
                "scand_bins_csv": "scand_factorization_bins.csv",
            },
            "n_stage_rows": int(len(stage_df)),
            "n_scand_rows": int(len(scand_df)),
        },
        manifest_path,
    )
    return ScandFactorizationOutputs(stage_bins=stage_path, scand_bins=scand_path, manifest=manifest_path)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare direct s_cand efficiency with the product of per-object efficiencies in 3D gen-kinematic bins"
    )
    parser.add_argument("--input-dir", required=True, help="Merged efficiency directory containing sample subdirectories")
    parser.add_argument("--samples", nargs="+", help="Sample names to process; defaults to all merged sample directories")
    parser.add_argument("--output-dir", help=f"Output directory; defaults to <input-dir>/{DEFAULT_OUTPUT_DIRNAME}")
    parser.add_argument("--build-maps", action="store_true", help="Rebuild factorized maps before running the diagnostic")
    parser.add_argument("--n-min-fine", type=int, default=30, help="Minimum MC total for fine factorized bins")
    parser.add_argument("--n-min-coarse", type=int, default=50, help="Minimum MC total for coarse factorized bins")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    outputs = quantify_scand_factorization(
        args.input_dir,
        samples=args.samples,
        output_dir=args.output_dir,
        n_min_fine=args.n_min_fine,
        n_min_coarse=args.n_min_coarse,
        build_maps=args.build_maps,
    )
    print(f"Wrote stage-bin diagnostic: {outputs.stage_bins}", flush=True)
    print(f"Wrote s_cand-bin diagnostic: {outputs.scand_bins}", flush=True)
    print(f"Wrote manifest: {outputs.manifest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

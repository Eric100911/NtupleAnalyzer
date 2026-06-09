from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pandas as pd

from .efficiency import (
    PAIR_LEVEL_MAP_SPECS,
    PAIR_LEVEL_MAP_SPECS_NO_TRIG_MATCH,
    EfficiencyBinning,
    build_acceptance_maps,
    build_conditional_maps,
    build_cutflow,
    build_efficiency_counts,
    build_pair_level_maps,
    build_per_object_acceptance_maps,
    build_stacked_jpsi_acceptance_maps,
    build_stacked_jpsi_efficiency_maps,
    build_subprocess_envelope,
)
from .io import ensure_dir, read_json, write_json, write_parquet


PAIR_LEVEL_OUTPUT_NAMES = {
    "four_muon_vtx": "four_muon_vertex",
    "four_muon_vtx_noTrigMatch": "four_muon_vertex_no_trig_match",
    "Pri_fitValid": "pri_fitvalid",
    "Pri_fitValid_noTrigMatch": "pri_fitvalid_no_trig_match",
    "Pri_fitPass": "pri_fitpass",
    "Pri_fitPass_noTrigMatch": "pri_fitpass_no_trig_match",
    "Pri_assocPVPass": "pri_assocpv",
    "Pri_assocPVPass_noTrigMatch": "pri_assocpv_no_trig_match",
    "Pri_trackPVPass": "pri_trackpv",
    "Pri_trackPVPass_noTrigMatch": "pri_trackpv_no_trig_match",
}


@dataclass(frozen=True)
class EfficiencyMergeResult:
    sample: str
    output_dir: Path
    sample_dir: Path
    artifacts: dict[str, Any]
    summary_df: pd.DataFrame
    envelope_df: pd.DataFrame
    counts_df: pd.DataFrame


@dataclass(frozen=True)
class DerivedSampleProducts:
    sample: str
    sample_dir: Path
    derived_dir: Path
    manifest: dict[str, Any]
    counts_df: pd.DataFrame
    acceptance_df: pd.DataFrame
    conditional_df: pd.DataFrame
    per_object_acceptance_df: pd.DataFrame
    stacked_jpsi_acceptance_df: pd.DataFrame
    stacked_jpsi_efficiency_df: pd.DataFrame
    pair_level_dfs: dict[str, pd.DataFrame]


def update_manifest_outputs(manifest_path: Path, outputs: dict[str, Any]) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    manifest.setdefault("outputs", {}).update(outputs)
    write_json(manifest, manifest_path)
    return manifest


def update_sample_manifest_artifacts(sample_dir: Path, artifacts: dict[str, Any]) -> dict[str, Any]:
    manifest_path = sample_dir / "manifest.json"
    manifest = read_json(manifest_path)
    manifest.setdefault("artifacts", {}).update(artifacts)
    write_json(manifest, manifest_path)
    return manifest


def discover_merged_samples(input_dir: Path) -> list[Path]:
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"No manifest.json found in {input_dir}")
    manifest = read_json(manifest_path)
    samples = manifest.get("artifacts", {}).get("samples", {})
    if samples:
        return [input_dir / sample for sample in samples]
    if (input_dir / "efficiency_maps.parquet").exists():
        return [input_dir]
    raise RuntimeError(
        f"No samples listed in {manifest_path} and no efficiency_maps.parquet found — is this a merge output directory?"
    )


def collect_shard_input_files(shard_sample_dirs: list[Path]) -> list[str]:
    files: list[str] = []
    for sample_dir in shard_sample_dirs:
        manifest_path = sample_dir / "sample_manifest.json"
        if not manifest_path.exists():
            continue
        payload = read_json(manifest_path)
        files.extend(str(item) for item in payload.get("input_files", []))
    return list(dict.fromkeys(files))


def write_efficiency_sample_bundle(
    output_dir: Path,
    sample: str,
    input_files: list[str],
    gen_df: pd.DataFrame,
    event_df: pd.DataFrame,
    counts_df: pd.DataFrame,
    cutflow_df: pd.DataFrame,
) -> dict[str, Any]:
    sample_dir = ensure_dir(output_dir / sample)
    write_json(
        {"sample": sample, "n_input_files": len(input_files), "input_files": input_files},
        sample_dir / "sample_manifest.json",
    )
    write_parquet(gen_df, sample_dir / "gen_systems.parquet")
    write_parquet(event_df, sample_dir / "event_step_flags.parquet")
    write_parquet(counts_df, sample_dir / "efficiency_counts.parquet")
    write_parquet(counts_df, sample_dir / "efficiency_maps.parquet")
    cutflow_df.to_csv(sample_dir / "cutflow.csv", index=False)

    artifacts: dict[str, Any] = {
        "sample_manifest": "sample_manifest.json",
        "gen_systems": {"path": "gen_systems.parquet", "n_rows": int(len(gen_df))},
        "event_step_flags": {"path": "event_step_flags.parquet", "n_rows": int(len(event_df))},
        "efficiency_counts": {"path": "efficiency_counts.parquet", "n_rows": int(len(counts_df))},
        "efficiency_maps": {"path": "efficiency_maps.parquet", "n_rows": int(len(counts_df))},
        "cutflow": {"path": "cutflow.csv", "n_rows": int(len(cutflow_df))},
    }
    write_json({"stage": "efficiency", "sample": sample, "artifacts": artifacts}, sample_dir / "manifest.json")
    return artifacts


def merge_efficiency_shards(
    sample: str,
    shards_dir: Path,
    output_dir: Path,
    *,
    binning: EfficiencyBinning | None = None,
) -> EfficiencyMergeResult:
    output_dir = ensure_dir(output_dir)
    sample_dirs = sorted(path / sample for path in shards_dir.glob("shard_*") if (path / sample).is_dir())
    if not sample_dirs:
        raise RuntimeError(f"No shard outputs found under {shards_dir} for {sample}")

    gen_df = pd.concat((pd.read_parquet(path / "gen_systems.parquet") for path in sample_dirs), ignore_index=True)
    event_df = pd.concat((pd.read_parquet(path / "event_step_flags.parquet") for path in sample_dirs), ignore_index=True)
    counts_df = build_efficiency_counts(gen_df, event_df, binning or EfficiencyBinning())
    cutflow_df = build_cutflow(event_df)
    input_files = collect_shard_input_files(sample_dirs)
    artifacts = write_efficiency_sample_bundle(output_dir, sample, input_files, gen_df, event_df, counts_df, cutflow_df)

    inclusive_final = cutflow_df.loc[cutflow_df["step"] == "Pri_trackPVPass"]
    summary_df = pd.DataFrame(
        [
            {
                "sample": sample,
                "n_input_files": len(input_files),
                "n_full_gen": int(event_df["full_gen"].sum()) if not event_df.empty else 0,
                "n_Pri_trackPVPass": int(event_df["Pri_trackPVPass"].sum()) if not event_df.empty else 0,
                "final_efficiency": float(inclusive_final["efficiency"].iloc[0]) if not inclusive_final.empty else float("nan"),
                "final_err_sym": float(inclusive_final["err_sym"].iloc[0]) if not inclusive_final.empty else float("nan"),
            }
        ]
    )
    write_parquet(summary_df, output_dir / "subprocess_summary.parquet")
    summary_df.to_csv(output_dir / "subprocess_summary.csv", index=False)
    envelope_df = build_subprocess_envelope({sample: counts_df})
    write_parquet(envelope_df, output_dir / "subprocess_envelope.parquet")

    manifest_path = output_dir / "manifest.json"
    existing_samples: dict[str, str] = {}
    if manifest_path.exists():
        existing = read_json(manifest_path)
        existing_samples = existing.get("artifacts", {}).get("samples", {})
    existing_samples[sample] = f"{sample}/manifest.json"
    write_json(
        {
            "stage": "efficiency_summary",
            "artifacts": {
                "subprocess_summary": "subprocess_summary.parquet",
                "subprocess_envelope": "subprocess_envelope.parquet",
                "samples": existing_samples,
            },
        },
        manifest_path,
    )

    return EfficiencyMergeResult(
        sample=sample,
        output_dir=output_dir,
        sample_dir=output_dir / sample,
        artifacts=artifacts,
        summary_df=summary_df,
        envelope_df=envelope_df,
        counts_df=counts_df,
    )


def build_derived_sample_products(
    sample_dir: Path,
    output_dir: Path,
    *,
    binning: EfficiencyBinning | None = None,
) -> DerivedSampleProducts:
    counts_path = sample_dir / "efficiency_maps.parquet"
    if not counts_path.exists():
        raise RuntimeError(f"efficiency_maps.parquet not found in {sample_dir}")

    sample = sample_dir.name
    counts_df = pd.read_parquet(counts_path)
    active_binning = binning or EfficiencyBinning()
    acc_df = build_acceptance_maps(counts_df)
    cond_df = build_conditional_maps(counts_df, active_binning)
    derived_dir = ensure_dir(output_dir / sample / "derived")

    poa_df = pd.DataFrame()
    stacked_acc_df = pd.DataFrame()
    stacked_eff_df = pd.DataFrame()
    pair_level_dfs: dict[str, pd.DataFrame] = {}
    gen_path = sample_dir / "gen_systems.parquet"
    event_path = sample_dir / "event_step_flags.parquet"
    if gen_path.exists() and event_path.exists():
        gen_df = pd.read_parquet(gen_path)
        event_df = pd.read_parquet(event_path)
        poa_df = build_per_object_acceptance_maps(gen_df, event_df, active_binning)
        stacked_acc_df = build_stacked_jpsi_acceptance_maps(gen_df, event_df, active_binning)
        stacked_eff_df = build_stacked_jpsi_efficiency_maps(gen_df, event_df, active_binning)
        pair_specs = PAIR_LEVEL_MAP_SPECS if active_binning.include_trigger_matching else PAIR_LEVEL_MAP_SPECS_NO_TRIG_MATCH
        pair_level_dfs = build_pair_level_maps(gen_df, event_df, active_binning, specs=pair_specs)

    manifest: dict[str, Any] = {"source": str(sample_dir.resolve()), "outputs": {}}
    _write_frame_pair(poa_df, derived_dir, "per_object_acceptance_maps", "per_object_acceptance", manifest)
    _write_frame_pair(stacked_acc_df, derived_dir, "stacked_jpsi_acceptance_maps", "stacked_jpsi_acceptance", manifest)
    _write_frame_pair(stacked_eff_df, derived_dir, "stacked_jpsi_efficiency_maps", "stacked_jpsi_efficiency", manifest)
    for step, frame in pair_level_dfs.items():
        stem = PAIR_LEVEL_OUTPUT_NAMES[step]
        _write_frame_pair(frame, derived_dir, f"{stem}_maps", stem, manifest)
    _write_frame_pair(acc_df, derived_dir, "acceptance_maps", "acceptance", manifest)
    _write_frame_pair(cond_df, derived_dir, "conditional_efficiency_maps", "conditional_efficiency", manifest)
    write_json(manifest, derived_dir / "manifest.json")

    return DerivedSampleProducts(
        sample=sample,
        sample_dir=sample_dir,
        derived_dir=derived_dir,
        manifest=manifest,
        counts_df=counts_df,
        acceptance_df=acc_df,
        conditional_df=cond_df,
        per_object_acceptance_df=poa_df,
        stacked_jpsi_acceptance_df=stacked_acc_df,
        stacked_jpsi_efficiency_df=stacked_eff_df,
        pair_level_dfs=pair_level_dfs,
    )


def build_derived_efficiency_products(
    input_dir: Path,
    output_dir: Path | None = None,
    *,
    binning: EfficiencyBinning | None = None,
) -> dict[str, DerivedSampleProducts]:
    output_dir = output_dir or input_dir
    products: dict[str, DerivedSampleProducts] = {}
    for sample_dir in discover_merged_samples(input_dir):
        products[sample_dir.name] = build_derived_sample_products(
            sample_dir,
            output_dir,
            binning=binning,
        )
    write_derived_products_manifest(input_dir, output_dir, products)
    return products


def build_systematic_uncertainty(
    input_dir: Path,
    output_dir: Path | None = None,
    *,
    binning: EfficiencyBinning | None = None,
    nominal_sample: str = "DPS_1",
    min_total: int = 1,
    min_n_samples: int = 2,
):
    from .systematics import (
        build_subprocess_systematics_summary,
        load_derived_products_for_systematics,
    )

    output_dir = output_dir or input_dir
    systematics_dir = ensure_dir(output_dir / "systematics")
    products_by_sample = load_derived_products_for_systematics(input_dir, binning=binning)
    if len(products_by_sample) < 2:
        raise RuntimeError(
            f"Need at least 2 samples to build subprocess systematics, got {len(products_by_sample)}"
        )

    results = build_subprocess_systematics_summary(
        products_by_sample,
        nominal_sample=nominal_sample,
        min_total=min_total,
        min_n_samples=min_n_samples,
    )
    results = replace(results, output_dir=systematics_dir)

    write_parquet(results.systematic_summary_df, systematics_dir / "systematic_summary.parquet")
    results.systematic_summary_df.to_csv(systematics_dir / "systematic_summary.csv", index=False)

    product_outputs: dict[str, dict[str, Any]] = {}
    for product_type, product in results.products.items():
        if product.systematics_df.empty:
            continue
        stem = f"{product_type}_systematics"
        write_parquet(product.systematics_df, systematics_dir / f"{stem}.parquet")
        product.systematics_df.to_csv(systematics_dir / f"{stem}.csv", index=False)
        product_outputs[product_type] = {
            "parquet": f"{stem}.parquet",
            "csv": f"{stem}.csv",
            "n_rows": int(len(product.systematics_df)),
        }

    write_json(
        {
            "stage": "subprocess_systematic_uncertainty",
            "input_dir": str(input_dir.resolve()),
            "output_dir": str(systematics_dir.resolve()),
            "nominal_sample": results.nominal_sample,
            "min_total": int(min_total),
            "min_n_samples": int(min_n_samples),
            "products": product_outputs,
            "summary": {
                "parquet": "systematic_summary.parquet",
                "csv": "systematic_summary.csv",
                "n_rows": int(len(results.systematic_summary_df)),
            },
        },
        systematics_dir / "systematic_manifest.json",
    )
    return results


def write_derived_products_manifest(
    input_dir: Path,
    output_dir: Path,
    products: dict[str, DerivedSampleProducts],
) -> None:
    write_json(
        {
            "stage": "derived_efficiency",
            "input_dir": str(input_dir.resolve()),
            "output_dir": str(output_dir.resolve()),
            "samples": {sample: product.manifest for sample, product in products.items()},
        },
        output_dir / "derived_manifest.json",
    )


def _write_frame_pair(
    frame: pd.DataFrame,
    output_dir: Path,
    stem: str,
    manifest_key: str,
    manifest: dict[str, Any],
) -> None:
    if frame.empty:
        return
    write_parquet(frame, output_dir / f"{stem}.parquet")
    frame.to_csv(output_dir / f"{stem}.csv", index=False)
    manifest["outputs"][f"{manifest_key}_parquet"] = f"{stem}.parquet"
    manifest["outputs"][f"{manifest_key}_csv"] = f"{stem}.csv"

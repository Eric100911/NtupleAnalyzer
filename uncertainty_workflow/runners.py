from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
from typing import Any

from .config import SystematicSource, Variation
from .mc_stat import throw_factorized_maps, toy_seed
from .provenance import hash_config, read_manifest, verify_manifest, write_manifest
from .registry import VariationResult, write_error_manifest
from .variations import offline_selection_from_variation


def run_fit_variation(
    source: SystematicSource,
    variation: Variation,
    *,
    input_file: str | Path,
    output_dir: Path,
    tree_name: str = "selected",
    dataset: str = "data",
    weight_branch: str | None = None,
    jobs: int = 4,
    weighted_error_mode: str = "asymptotic",
    force: bool = False,
) -> VariationResult:
    """Run one scalar JJP fit-model variation and persist its result."""
    variation_dir = output_dir / "variations" / source.name / variation.name
    result_path = variation_dir / "result.json"
    manifest_path = variation_dir / "manifest.json"
    fit_config = _fit_config(source, variation)
    input_file = Path(input_file)
    run_hash = hash_config(
        {
            "runner": "run_fit_variation",
            "source": source,
            "variation": variation,
            "fit_config": fit_config,
            "input_file": _input_fingerprint(input_file),
            "tree_name": tree_name,
            "dataset": dataset,
            "weight_branch": weight_branch,
            "jobs": jobs,
            "weighted_error_mode": weighted_error_mode,
        }
    )

    if not force and result_path.exists() and manifest_path.exists() and verify_manifest(manifest_path, run_hash):
        return _variation_result_from_json(result_path, manifest_path)

    variation_dir.mkdir(parents=True, exist_ok=True)
    try:
        fit_result = _run_jjp_fit(
            input_file,
            tree_name=tree_name,
            weight_branch=weight_branch,
            dataset=dataset,
            jobs=jobs,
            weighted_error_mode=weighted_error_mode,
            jpsi_signal=str(fit_config["jpsi_signal"]),
            jpsi_background=str(fit_config["jpsi_background"]),
            phi_signal=str(fit_config["phi_signal"]),
            phi_background=str(fit_config["phi_background"]),
            jpsi_mass_window=tuple(fit_config["jpsi_mass_window"]),
            phi_mass_window=tuple(fit_config["phi_mass_window"]),
        )
    except Exception as exc:
        write_error_manifest(source=source, variation=variation, manifest_path=manifest_path, error=exc)
        return VariationResult(
            source=source.name,
            variation=variation.name,
            status="failed",
            target_value=float("nan"),
            target_uncertainty=float("nan"),
            artifacts={"variation_dir": variation_dir, "result_json": result_path},
            manifest_path=manifest_path,
        )

    result_payload = {
        "source": source.name,
        "variation": variation.name,
        "status": "success",
        "target": source.target,
        "target_value": float(fit_result["yield"]),
        "target_uncertainty": float(fit_result["yield_err"]),
        "fit_nll": float(fit_result["fit_nll"]),
        "fit_status": fit_result["fit_status"],
        "fit_config": fit_config,
    }
    result_path.write_text(json.dumps(result_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_manifest(
        manifest_path,
        {
            "status": "success",
            "run_hash": run_hash,
            "source": source.name,
            "variation": variation.name,
            "runner": "uncertainty_workflow.runners.run_fit_variation",
            "input_file": str(input_file),
            "tree_name": tree_name,
            "dataset": dataset,
            "weight_branch": weight_branch,
            "fit_config": fit_config,
            "outputs": {"result_json": str(result_path)},
        },
    )
    return _variation_result_from_json(result_path, manifest_path)


def load_variation_result(path: str | Path, manifest_path: str | Path | None = None) -> VariationResult:
    path = Path(path)
    return _variation_result_from_json(path, Path(manifest_path) if manifest_path is not None else path.with_name("manifest.json"))


def run_efficiency_config_variation(
    source: SystematicSource,
    variation: Variation,
    *,
    input_manifest: str | Path,
    data_input_file: str | Path,
    nominal_efficiency_dir: str | Path,
    output_dir: Path,
    sample: str,
    samples: tuple[str, ...],
    nominal_sample: str,
    tree_path: str = "X_data",
    backend: str = "vectorized",
    step_size: str = "100 MB",
    event_end_step: str = "Pri_assocPVPass",
    correction_mode: str = "factorized",
    n_min_fine: int = 30,
    n_min_coarse: int = 50,
    jobs: int = 4,
    max_files: int | None = None,
    force: bool = False,
) -> VariationResult:
    """Run one OfflineSelectionConfig variation through maps and corrected yield."""
    variation_dir = output_dir / "variations" / source.name / variation.name
    result_path = variation_dir / "result.json"
    manifest_path = variation_dir / "manifest.json"
    variation_efficiency_dir = variation_dir / "efficiency"
    input_manifest = Path(input_manifest)
    data_input_file = Path(data_input_file)
    nominal_efficiency_dir = Path(nominal_efficiency_dir)
    selection_config = offline_selection_from_variation(source, variation)
    selection_payload = _offline_selection_payload(selection_config)
    run_hash = hash_config(
        {
            "runner": "run_efficiency_config_variation",
            "source": source,
            "variation": variation,
            "selection_config": selection_payload,
            "input_manifest": _input_fingerprint(input_manifest),
            "data_input_file": _input_fingerprint(data_input_file),
            "nominal_efficiency_dir": _directory_fingerprint(nominal_efficiency_dir, samples=samples),
            "sample": sample,
            "samples": samples,
            "nominal_sample": nominal_sample,
            "tree_path": tree_path,
            "backend": backend,
            "step_size": step_size,
            "event_end_step": event_end_step,
            "correction_mode": correction_mode,
            "n_min_fine": n_min_fine,
            "n_min_coarse": n_min_coarse,
            "jobs": jobs,
            "max_files": max_files,
        }
    )

    if not force and result_path.exists() and manifest_path.exists() and verify_manifest(manifest_path, run_hash):
        return _variation_result_from_json(result_path, manifest_path)

    variation_dir.mkdir(parents=True, exist_ok=True)
    try:
        files_by_sample = _load_efficiency_file_manifest(input_manifest, samples=(sample,), max_files=max_files)
        input_files = files_by_sample[sample]
        tables = _run_efficiency_for_sample(
            input_files,
            sample,
            cfg=selection_config,
            tree_path=tree_path,
            backend=backend,
            step_size=step_size,
        )
        _write_efficiency_sample_bundle(
            variation_efficiency_dir,
            sample,
            input_files,
            tables["gen_systems"],
            tables["event_step_flags"],
            tables["efficiency_counts"],
            tables["cutflow"],
        )
        _build_factorized_maps_for_sample(
            variation_efficiency_dir / sample,
            variation_efficiency_dir / sample / "maps",
            event_end_step=event_end_step,
        )
        _attach_nominal_samples(
            variation_efficiency_dir,
            nominal_efficiency_dir,
            samples=samples,
            varied_sample=sample,
        )
        yield_result = _compute_efficiency_corrected_yield(
            data_input_file,
            variation_efficiency_dir,
            samples=samples,
            nominal_sample=nominal_sample,
            correction_mode=correction_mode,
            n_min_fine=n_min_fine,
            n_min_coarse=n_min_coarse,
            jobs=jobs,
        )
    except Exception as exc:
        write_error_manifest(source=source, variation=variation, manifest_path=manifest_path, error=exc)
        return VariationResult(
            source=source.name,
            variation=variation.name,
            status="failed",
            target_value=float("nan"),
            target_uncertainty=float("nan"),
            artifacts={"variation_dir": variation_dir, "result_json": result_path},
            manifest_path=manifest_path,
        )

    result_payload = {
        "source": source.name,
        "variation": variation.name,
        "status": "success",
        "target": source.target,
        "target_value": float(yield_result.nominal_corrected_yield),
        "target_uncertainty": float(yield_result.stat_unc),
        "mc_stat_unc": float(yield_result.mc_stat_unc),
        "selection_config": selection_payload,
        "yield_result": yield_result.to_dict(),
    }
    result_path.write_text(json.dumps(result_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_manifest(
        manifest_path,
        {
            "status": "success",
            "run_hash": run_hash,
            "source": source.name,
            "variation": variation.name,
            "runner": "uncertainty_workflow.runners.run_efficiency_config_variation",
            "input_manifest": str(input_manifest),
            "data_input_file": str(data_input_file),
            "nominal_efficiency_dir": str(nominal_efficiency_dir),
            "variation_efficiency_dir": str(variation_efficiency_dir),
            "sample": sample,
            "samples": list(samples),
            "nominal_sample": nominal_sample,
            "tree_path": tree_path,
            "backend": backend,
            "step_size": step_size,
            "event_end_step": event_end_step,
            "correction_mode": correction_mode,
            "selection_config": selection_payload,
            "outputs": {
                "result_json": str(result_path),
                "variation_efficiency_dir": str(variation_efficiency_dir),
            },
        },
    )
    return _variation_result_from_json(result_path, manifest_path)


def run_mc_stat_variation(
    source: SystematicSource,
    variation: Variation,
    *,
    output_dir: Path,
    mode: str,
    nominal_yield_json: str | Path | None = None,
    data_input_file: str | Path | None = None,
    nominal_efficiency_dir: str | Path | None = None,
    samples: tuple[str, ...] = (),
    nominal_sample: str = "",
    correction_mode: str = "factorized",
    n_min_fine: int = 30,
    n_min_coarse: int = 50,
    jobs: int = 4,
    n_toys: int | None = None,
    seed: int | None = None,
    clip: tuple[float, float] | None = None,
    force: bool = False,
) -> VariationResult:
    """Run an analytic or toy MC-stat uncertainty variation."""
    variation_dir = output_dir / "variations" / source.name / variation.name
    result_path = variation_dir / "result.json"
    manifest_path = variation_dir / "manifest.json"
    config = _mc_stat_config(source, variation, mode=mode, n_toys=n_toys, seed=seed, clip=clip)
    normalized_mode = str(config["mode"])
    nominal_yield_path = Path(nominal_yield_json) if nominal_yield_json is not None else None
    data_input_path = Path(data_input_file) if data_input_file is not None else None
    nominal_efficiency_path = Path(nominal_efficiency_dir) if nominal_efficiency_dir is not None else None
    run_hash = hash_config(
        {
            "runner": "run_mc_stat_variation",
            "source": source,
            "variation": variation,
            "config": config,
            "nominal_yield_json": _optional_input_fingerprint(nominal_yield_path) if nominal_yield_path else None,
            "data_input_file": _optional_input_fingerprint(data_input_path) if data_input_path else None,
            "nominal_efficiency_dir": _map_directory_fingerprint(nominal_efficiency_path, samples=samples)
            if nominal_efficiency_path
            else None,
            "samples": samples,
            "nominal_sample": nominal_sample,
            "correction_mode": correction_mode,
            "n_min_fine": n_min_fine,
            "n_min_coarse": n_min_coarse,
            "jobs": jobs,
        }
    )

    if not force and result_path.exists() and manifest_path.exists() and verify_manifest(manifest_path, run_hash):
        return _variation_result_from_json(result_path, manifest_path)

    variation_dir.mkdir(parents=True, exist_ok=True)
    try:
        if normalized_mode == "analytic":
            if nominal_yield_path is None:
                raise ValueError("nominal_yield_json is required for analytic MC-stat mode")
            result_payload = _run_mc_stat_analytic(source, variation, nominal_yield_path, config)
        elif normalized_mode == "toy":
            if data_input_path is None:
                raise ValueError("data_input_file is required for toy MC-stat mode")
            if nominal_efficiency_path is None:
                raise ValueError("nominal_efficiency_dir is required for toy MC-stat mode")
            if not samples:
                raise ValueError("at least one yield sample is required for toy MC-stat mode")
            if not nominal_sample:
                raise ValueError("nominal_sample is required for toy MC-stat mode")
            result_payload = _run_mc_stat_toys(
                source,
                variation,
                variation_dir=variation_dir,
                data_input_file=data_input_path,
                nominal_efficiency_dir=nominal_efficiency_path,
                samples=samples,
                nominal_sample=nominal_sample,
                correction_mode=correction_mode,
                n_min_fine=n_min_fine,
                n_min_coarse=n_min_coarse,
                jobs=jobs,
                config=config,
            )
        else:
            raise ValueError(f"unsupported MC-stat mode: {normalized_mode!r}")
    except Exception as exc:
        write_error_manifest(source=source, variation=variation, manifest_path=manifest_path, error=exc)
        return VariationResult(
            source=source.name,
            variation=variation.name,
            status="failed",
            target_value=float("nan"),
            target_uncertainty=float("nan"),
            artifacts={"variation_dir": variation_dir, "result_json": result_path},
            manifest_path=manifest_path,
        )

    result_path.write_text(json.dumps(result_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_manifest(
        manifest_path,
        {
            "status": "success",
            "run_hash": run_hash,
            "source": source.name,
            "variation": variation.name,
            "runner": "uncertainty_workflow.runners.run_mc_stat_variation",
            "mode": normalized_mode,
            "config": config,
            "nominal_yield_json": str(nominal_yield_path) if nominal_yield_path else None,
            "data_input_file": str(data_input_path) if data_input_path else None,
            "nominal_efficiency_dir": str(nominal_efficiency_path) if nominal_efficiency_path else None,
            "samples": list(samples),
            "nominal_sample": nominal_sample,
            "correction_mode": correction_mode,
            "outputs": {"result_json": str(result_path)},
        },
    )
    return _variation_result_from_json(result_path, manifest_path)


def _run_jjp_fit(*args, **kwargs):
    from scripts.kinematics.fit_splot import run_jjp_fit

    return run_jjp_fit(*args, **kwargs)


def _load_efficiency_file_manifest(*args, **kwargs):
    from efficiency_workflow.efficiency import load_efficiency_file_manifest

    return load_efficiency_file_manifest(*args, **kwargs)


def _run_efficiency_for_sample(*args, **kwargs):
    from efficiency_workflow.efficiency import run_efficiency_for_sample

    return run_efficiency_for_sample(*args, **kwargs)


def _write_efficiency_sample_bundle(*args, **kwargs):
    from efficiency_workflow.products import write_efficiency_sample_bundle

    return write_efficiency_sample_bundle(*args, **kwargs)


def _build_factorized_maps_for_sample(*args, **kwargs):
    from efficiency_workflow.build_factorized_maps import build_factorized_maps_for_sample

    return build_factorized_maps_for_sample(*args, **kwargs)


def _compute_efficiency_corrected_yield(*args, **kwargs):
    from efficiency_workflow.yield_correction import compute_efficiency_corrected_yield

    return compute_efficiency_corrected_yield(*args, **kwargs)


def _fit_config(source: SystematicSource, variation: Variation) -> dict[str, Any]:
    config: dict[str, Any] = {
        "jpsi_signal": "dscb",
        "jpsi_background": "exponential",
        "phi_signal": "voigtian",
        "phi_background": "threshold_powerlaw",
        "jpsi_mass_window": [2.9, 3.3],
        "phi_mass_window": [0.99, 1.07],
    }
    config.update({key: value for key, value in source.nominal.items() if key not in {"variation", "nominal_variation"}})
    overrides = dict(variation.parameter_overrides)
    if set(overrides) == {"value"}:
        config["jpsi_background"] = overrides["value"]
    else:
        config.update(overrides)

    _validate_choice("jpsi_signal", config["jpsi_signal"], {"dscb"})
    _validate_choice("jpsi_background", config["jpsi_background"], {"exponential", "chebychev1", "chebychev2"})
    _validate_choice("phi_signal", config["phi_signal"], {"voigtian"})
    _validate_choice("phi_background", config["phi_background"], {"threshold_powerlaw"})
    config["jpsi_mass_window"] = _validate_window("jpsi_mass_window", config["jpsi_mass_window"])
    config["phi_mass_window"] = _validate_window("phi_mass_window", config["phi_mass_window"])
    return config


def _mc_stat_config(
    source: SystematicSource,
    variation: Variation,
    *,
    mode: str,
    n_toys: int | None,
    seed: int | None,
    clip: tuple[float, float] | None,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "mode": "toy",
        "n_toys": 200,
        "seed": 12345,
        "clip": [1e-6, 1.0],
    }
    config.update({key: value for key, value in source.nominal.items() if key not in {"variation", "nominal_variation"}})
    config.update(variation.parameter_overrides)
    if mode:
        config["mode"] = mode
    if n_toys is not None:
        config["n_toys"] = int(n_toys)
    if seed is not None:
        config["seed"] = int(seed)
    if clip is not None:
        config["clip"] = [float(clip[0]), float(clip[1])]

    if str(config["mode"]) not in {"analytic", "toy"}:
        raise ValueError("mode must be 'analytic' or 'toy'")
    config["n_toys"] = int(config["n_toys"])
    if config["n_toys"] < 1:
        raise ValueError("n_toys must be >= 1")
    config["seed"] = int(config["seed"])
    config["clip"] = _validate_window("clip", config["clip"])
    if config["clip"][0] <= 0.0 or config["clip"][1] > 1.0:
        raise ValueError("clip must be within (0, 1]")
    return config


def _run_mc_stat_analytic(
    source: SystematicSource,
    variation: Variation,
    nominal_yield_json: Path,
    config: dict[str, Any],
) -> dict[str, object]:
    payload = json.loads(nominal_yield_json.read_text(encoding="utf-8"))
    nominal_value = float(payload["nominal_corrected_yield"])
    mc_stat_unc = float(payload.get("mc_stat_unc", 0.0))
    return {
        "source": source.name,
        "variation": variation.name,
        "status": "success",
        "target": source.target,
        "target_value": nominal_value,
        "target_uncertainty": mc_stat_unc,
        "mode": "analytic",
        "n_toys": 0,
        "seed": int(config["seed"]),
        "toy_yields": [],
        "toy_rms": mc_stat_unc,
    }


def _run_mc_stat_toys(
    source: SystematicSource,
    variation: Variation,
    *,
    variation_dir: Path,
    data_input_file: Path,
    nominal_efficiency_dir: Path,
    samples: tuple[str, ...],
    nominal_sample: str,
    correction_mode: str,
    n_min_fine: int,
    n_min_coarse: int,
    jobs: int,
    config: dict[str, Any],
) -> dict[str, object]:
    if correction_mode not in {"factorized", "hybrid"}:
        raise ValueError("MC-stat toy mode supports factorized and hybrid correction modes only")

    nominal_result = _compute_efficiency_corrected_yield(
        data_input_file,
        nominal_efficiency_dir,
        samples=samples,
        nominal_sample=nominal_sample,
        correction_mode=correction_mode,
        n_min_fine=n_min_fine,
        n_min_coarse=n_min_coarse,
        jobs=jobs,
    )
    n_toys = int(config["n_toys"])
    base_seed = int(config["seed"])
    clip = tuple(float(value) for value in config["clip"])
    toy_yields: list[float] = []
    toy_results: list[dict[str, object]] = []
    toys_dir = variation_dir / "toys"
    import numpy as np

    for toy_index in range(n_toys):
        toy_efficiency_dir = toys_dir / f"toy_{toy_index:04d}" / "efficiency"
        for sample in samples:
            rng = np.random.default_rng(toy_seed(base_seed, toy_index, sample))
            throw_factorized_maps(
                nominal_efficiency_dir / sample,
                toy_efficiency_dir / sample,
                rng=rng,
                clip=clip,
            )
        toy_result = _compute_efficiency_corrected_yield(
            data_input_file,
            toy_efficiency_dir,
            samples=samples,
            nominal_sample=nominal_sample,
            correction_mode=correction_mode,
            n_min_fine=n_min_fine,
            n_min_coarse=n_min_coarse,
            jobs=jobs,
        )
        toy_yield = float(toy_result.nominal_corrected_yield)
        toy_yields.append(toy_yield)
        toy_results.append(
            {
                "toy": toy_index,
                "yield": toy_yield,
                "stat_unc": float(toy_result.stat_unc),
                "efficiency_dir": str(toy_efficiency_dir),
            }
        )

    toy_rms = _rms_about_nominal(toy_yields, float(nominal_result.nominal_corrected_yield))
    return {
        "source": source.name,
        "variation": variation.name,
        "status": "success",
        "target": source.target,
        "target_value": float(nominal_result.nominal_corrected_yield),
        "target_uncertainty": toy_rms,
        "mode": "toy",
        "n_toys": n_toys,
        "seed": base_seed,
        "clip": list(clip),
        "toy_yields": toy_yields,
        "toy_rms": toy_rms,
        "nominal_yield_result": nominal_result.to_dict(),
        "toy_results": toy_results,
    }


def _rms_about_nominal(values: list[float], nominal: float) -> float:
    import numpy as np

    finite = np.asarray([value for value in values if math.isfinite(value)], dtype=float)
    if finite.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean((finite - float(nominal)) ** 2)))


def _validate_choice(name: str, value: object, allowed: set[str]) -> None:
    if str(value) not in allowed:
        raise ValueError(f"{name} must be one of {sorted(allowed)}, got {value!r}")


def _validate_window(name: str, value: object) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must be a two-value list")
    low, high = float(value[0]), float(value[1])
    if not low < high:
        raise ValueError(f"{name} lower edge must be smaller than upper edge")
    return [low, high]


def _input_fingerprint(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _directory_fingerprint(path: Path, *, samples: tuple[str, ...]) -> dict[str, object]:
    payload: dict[str, object] = {"path": str(path.resolve()), "samples": {}}
    sample_payload: dict[str, object] = {}
    for sample in samples:
        sample_dir = path / sample
        if not sample_dir.exists():
            sample_payload[sample] = {"exists": False}
            continue
        manifest = sample_dir / "manifest.json"
        maps_manifest = sample_dir / "maps" / "manifest.json"
        sample_payload[sample] = {
            "exists": True,
            "manifest": _optional_input_fingerprint(manifest),
            "maps_manifest": _optional_input_fingerprint(maps_manifest),
        }
    payload["samples"] = sample_payload
    return payload


def _map_directory_fingerprint(path: Path, *, samples: tuple[str, ...]) -> dict[str, object]:
    payload = _directory_fingerprint(path, samples=samples)
    sample_payload = payload.get("samples", {})
    if isinstance(sample_payload, dict):
        for sample in samples:
            entry = sample_payload.get(sample)
            if not isinstance(entry, dict) or not entry.get("exists"):
                continue
            maps_dir = path / sample / "maps"
            entry["maps"] = {
                map_path.name: _input_fingerprint(map_path)
                for map_path in sorted(maps_dir.glob("*.parquet"))
            }
    return payload


def _optional_input_fingerprint(path: Path) -> dict[str, object] | None:
    return _input_fingerprint(path) if path.exists() else None


def _offline_selection_payload(config) -> dict[str, object]:
    from dataclasses import asdict

    payload = asdict(config)
    for key, value in list(payload.items()):
        if isinstance(value, tuple):
            payload[key] = list(value)
    return payload


def _attach_nominal_samples(
    variation_efficiency_dir: Path,
    nominal_efficiency_dir: Path,
    *,
    samples: tuple[str, ...],
    varied_sample: str,
) -> None:
    for sample in samples:
        if sample == varied_sample:
            continue
        source_dir = nominal_efficiency_dir / sample
        if not source_dir.exists():
            raise FileNotFoundError(f"Nominal efficiency sample not found: {source_dir}")
        target_dir = variation_efficiency_dir / sample
        if target_dir.exists():
            continue
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            target_dir.symlink_to(source_dir.resolve(), target_is_directory=True)
        except OSError:
            shutil.copytree(source_dir, target_dir)


def _variation_result_from_json(path: Path, manifest_path: Path) -> VariationResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    status = str(payload["status"])
    artifacts = {"variation_dir": path.parent, "result_json": path}
    if manifest_path.exists():
        manifest = read_manifest(manifest_path)
        outputs = manifest.get("outputs")
        if isinstance(outputs, dict):
            artifacts.update({str(key): Path(str(value)) for key, value in outputs.items()})
    return VariationResult(
        source=str(payload["source"]),
        variation=str(payload["variation"]),
        status=status,
        target_value=float(payload["target_value"]),
        target_uncertainty=float(payload["target_uncertainty"]),
        artifacts=artifacts,
        manifest_path=manifest_path,
    )

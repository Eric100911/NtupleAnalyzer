from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised only in incomplete envs
    raise RuntimeError(
        "PyYAML is required for uncertainty config parsing. Source the LCG 109a environment first."
    ) from exc


SCHEMA_VERSION = "ntuple-analyzer-systematics/v1"
VALID_CATEGORIES = {"efficiency_selection", "fit_model", "normalization", "mc_stat"}
VALID_TARGETS = {"yield", "efficiency", "acceptance"}
VALID_EVALUATION_METHODS = {"envelope", "two_sided", "rms", "signed_shift"}
VALID_RERUN_LEVELS = {
    "efficiency_extraction",
    "efficiency_counts",
    "factorized_maps",
    "corrected_yield",
    "fit",
    "normalization",
}
VALID_CORRELATIONS = {"correlated", "uncorrelated"}


@dataclass(frozen=True)
class Variation:
    name: str
    parameter_overrides: dict[str, object]


@dataclass(frozen=True)
class CorrelationSpec:
    across_bins: str = "correlated"
    across_years: str = "correlated"


@dataclass(frozen=True)
class SystematicSource:
    name: str
    category: str
    target: str
    enabled: bool
    nominal: dict[str, object]
    variations: tuple[Variation, ...]
    evaluation_method: str
    rerun_from: str
    correlations: CorrelationSpec
    config_path: Path | None = None


@dataclass(frozen=True)
class VariationConfig:
    schema_version: str
    sources: tuple[SystematicSource, ...]
    path: Path | None = None


def load_variation_config(path: str | Path) -> VariationConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: config must be a mapping")

    schema_version = str(payload.get("schema_version", SCHEMA_VERSION))
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"{path}: unsupported schema_version {schema_version!r}")

    sources_payload = payload.get("sources", ())
    if sources_payload is None:
        sources_payload = ()
    if not isinstance(sources_payload, list):
        raise ValueError(f"{path}: sources must be a list")

    seen: set[str] = set()
    sources: list[SystematicSource] = []
    for source_payload in sources_payload:
        source = _parse_source(source_payload, path)
        if source.name in seen:
            raise ValueError(f"{path}: duplicate source name {source.name!r}")
        seen.add(source.name)
        sources.append(source)
    return VariationConfig(schema_version=schema_version, sources=tuple(sources), path=path)


def load_variation_configs(paths: Iterable[str | Path]) -> VariationConfig:
    configs: list[VariationConfig] = []
    for path in paths:
        path = Path(path)
        if path.is_dir():
            for child in sorted(path.glob("*.yaml")):
                configs.append(load_variation_config(child))
        else:
            configs.append(load_variation_config(path))

    seen: set[str] = set()
    sources: list[SystematicSource] = []
    for config in configs:
        for source in config.sources:
            if source.name in seen:
                raise ValueError(f"duplicate source name across configs: {source.name!r}")
            seen.add(source.name)
            sources.append(source)
    return VariationConfig(schema_version=SCHEMA_VERSION, sources=tuple(sources), path=None)


def _parse_source(payload: Any, path: Path) -> SystematicSource:
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: each source must be a mapping")
    allowed_keys = {
        "name",
        "category",
        "target",
        "enabled",
        "nominal",
        "variations",
        "evaluation",
        "rerun_from",
        "correlations",
    }
    unknown = set(payload) - allowed_keys
    if unknown:
        raise ValueError(f"{path}: source {payload.get('name', '<unknown>')!r} has unknown keys: {sorted(unknown)}")

    name = _required_str(payload, "name", path)
    category = str(payload.get("category", ""))
    if category not in VALID_CATEGORIES:
        raise ValueError(f"{path}: source {name!r} has invalid category {category!r}")
    target = str(payload.get("target", "yield"))
    if target not in VALID_TARGETS:
        raise ValueError(f"{path}: source {name!r} has invalid target {target!r}")
    rerun_from = str(payload.get("rerun_from", "corrected_yield"))
    if rerun_from not in VALID_RERUN_LEVELS:
        raise ValueError(f"{path}: source {name!r} has invalid rerun_from {rerun_from!r}")

    evaluation_payload = payload.get("evaluation") or {}
    if not isinstance(evaluation_payload, dict):
        raise ValueError(f"{path}: source {name!r} evaluation must be a mapping")
    evaluation_method = str(evaluation_payload.get("method", "envelope"))
    if evaluation_method not in VALID_EVALUATION_METHODS:
        raise ValueError(f"{path}: source {name!r} has invalid evaluation method {evaluation_method!r}")

    nominal = payload.get("nominal") or {}
    if not isinstance(nominal, dict):
        raise ValueError(f"{path}: source {name!r} nominal must be a mapping")

    correlations = _parse_correlations(payload.get("correlations") or {}, path, name)
    return SystematicSource(
        name=name,
        category=category,
        target=target,
        enabled=bool(payload.get("enabled", False)),
        nominal=dict(nominal),
        variations=_parse_variations(payload.get("variations", []), path, name),
        evaluation_method=evaluation_method,
        rerun_from=rerun_from,
        correlations=correlations,
        config_path=path,
    )


def _parse_variations(payload: Any, path: Path, source_name: str) -> tuple[Variation, ...]:
    if isinstance(payload, dict):
        items = payload.items()
        variations = []
        for name, overrides in items:
            if overrides is None:
                overrides = {}
            if not isinstance(overrides, dict):
                raise ValueError(f"{path}: variation {source_name}.{name} must be a mapping")
            variations.append(Variation(name=str(name), parameter_overrides=dict(overrides)))
        return tuple(variations)

    if isinstance(payload, list):
        variations = []
        for index, item in enumerate(payload):
            if isinstance(item, dict) and set(item) == {"name", "parameters"}:
                name = str(item["name"])
                parameters = item.get("parameters") or {}
                if not isinstance(parameters, dict):
                    raise ValueError(f"{path}: variation {source_name}.{name} parameters must be a mapping")
                variations.append(Variation(name=name, parameter_overrides=dict(parameters)))
            else:
                variations.append(Variation(name=_variation_name(item, index), parameter_overrides={"value": item}))
        return tuple(variations)

    raise ValueError(f"{path}: source {source_name!r} variations must be a mapping or list")


def _variation_name(value: object, index: int) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value).lower()
    return f"variation_{index}"


def _parse_correlations(payload: dict[str, object], path: Path, source_name: str) -> CorrelationSpec:
    allowed_keys = {"across_bins", "across_years"}
    unknown = set(payload) - allowed_keys
    if unknown:
        raise ValueError(f"{path}: source {source_name!r} has unknown correlation keys: {sorted(unknown)}")
    across_bins = str(payload.get("across_bins", "correlated"))
    across_years = str(payload.get("across_years", "correlated"))
    for axis, value in {"across_bins": across_bins, "across_years": across_years}.items():
        if value not in VALID_CORRELATIONS:
            raise ValueError(f"{path}: source {source_name!r} has invalid {axis} correlation {value!r}")
    return CorrelationSpec(across_bins=across_bins, across_years=across_years)


def _required_str(payload: dict[str, object], key: str, path: Path) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path}: source missing required string field {key!r}")
    return value

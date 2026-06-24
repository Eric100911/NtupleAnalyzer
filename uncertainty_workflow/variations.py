from __future__ import annotations

from dataclasses import fields, replace
from typing import Any

from efficiency_workflow.config import OfflineSelectionConfig

from .config import SystematicSource, Variation


_METADATA_KEYS = {"variation", "nominal_variation"}
_WINDOW_FIELDS = {"jpsi_mass_window", "ups_mass_window", "phi_mass_window"}


class VariationFactory:
    """Construct typed runtime configs from generic variation overrides."""

    def offline_selection(self, nominal: OfflineSelectionConfig, variation: Variation) -> OfflineSelectionConfig:
        return _offline_selection_from_overrides(nominal, variation.parameter_overrides)


def offline_selection_from_variation(
    source: SystematicSource,
    variation: Variation,
    nominal: OfflineSelectionConfig | None = None,
) -> OfflineSelectionConfig:
    """Build an OfflineSelectionConfig for one systematic variation."""
    base = nominal or OfflineSelectionConfig()
    overrides = {
        key: value
        for key, value in source.nominal.items()
        if key not in _METADATA_KEYS
    }
    overrides.update(variation.parameter_overrides)
    return _offline_selection_from_overrides(base, overrides)


def _offline_selection_from_overrides(
    nominal: OfflineSelectionConfig,
    overrides: dict[str, object],
) -> OfflineSelectionConfig:
    valid_fields = {field.name for field in fields(OfflineSelectionConfig)}
    unknown = sorted(set(overrides) - valid_fields)
    if unknown:
        raise ValueError(f"unknown OfflineSelectionConfig override(s): {unknown}")

    coerced = {key: _coerce_offline_value(key, value) for key, value in overrides.items()}
    return replace(nominal, **coerced)


def _coerce_offline_value(key: str, value: object) -> Any:
    if key in _WINDOW_FIELDS:
        return _coerce_window(key, value)
    return value


def _coerce_window(key: str, value: object) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{key} must be a two-value list")
    low, high = float(value[0]), float(value[1])
    if not low < high:
        raise ValueError(f"{key} lower edge must be smaller than upper edge")
    return (low, high)

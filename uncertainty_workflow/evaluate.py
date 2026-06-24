from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .config import SystematicSource
from .registry import VariationResult


@dataclass(frozen=True)
class EvaluatedSource:
    source_name: str
    category: str
    nominal_value: float
    variation_results: dict[str, VariationResult]
    delta_up: float
    delta_down: float
    delta_sym: float
    method: str
    status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "source_name": self.source_name,
            "category": self.category,
            "nominal_value": self.nominal_value,
            "delta_up": self.delta_up,
            "delta_down": self.delta_down,
            "delta_sym": self.delta_sym,
            "method": self.method,
            "status": self.status,
            "variations": {
                name: {
                    "status": result.status,
                    "target_value": result.target_value,
                    "target_uncertainty": result.target_uncertainty,
                    "manifest_path": str(result.manifest_path),
                }
                for name, result in self.variation_results.items()
            },
        }


def evaluate_source(source: SystematicSource, results: list[VariationResult]) -> EvaluatedSource:
    successful = [result for result in results if result.status == "success" and math.isfinite(result.target_value)]
    if not successful:
        raise ValueError(f"{source.name}: no successful variation results to evaluate")

    nominal = _nominal_value(source, successful)
    values = {result.variation: result.target_value for result in successful}
    method = source.evaluation_method
    if method == "envelope":
        delta_up, delta_down, delta_sym = evaluate_envelope(nominal, values)
    elif method == "two_sided":
        delta_up, delta_down, delta_sym = evaluate_two_sided(nominal, values)
    elif method == "rms":
        delta_up, delta_down, delta_sym = evaluate_rms(nominal, values)
    elif method == "signed_shift":
        delta_up, delta_down, delta_sym = evaluate_signed_shift(nominal, values)
    else:
        raise ValueError(f"{source.name}: unsupported evaluation method {method!r}")

    status = "success" if len(successful) == len(results) else "partial"
    return EvaluatedSource(
        source_name=source.name,
        category=source.category,
        nominal_value=nominal,
        variation_results={result.variation: result for result in results},
        delta_up=delta_up,
        delta_down=delta_down,
        delta_sym=delta_sym,
        method=method,
        status=status,
    )


def evaluate_envelope(nominal: float, variations: dict[str, float]) -> tuple[float, float, float]:
    if not variations:
        raise ValueError("at least one variation is required")
    high = max(variations.values())
    low = min(variations.values())
    return max(0.0, high - nominal), max(0.0, nominal - low), 0.5 * (high - low)


def evaluate_two_sided(nominal: float, variations: dict[str, float]) -> tuple[float, float, float]:
    if len(variations) != 2:
        raise ValueError("two_sided evaluation requires exactly two successful variations")
    deviations = [value - nominal for value in variations.values()]
    delta_up = max(0.0, *deviations)
    delta_down = max(0.0, *(-value for value in deviations))
    return delta_up, delta_down, 0.5 * (delta_up + delta_down)


def evaluate_rms(nominal: float, variations: dict[str, float]) -> tuple[float, float, float]:
    if not variations:
        raise ValueError("at least one variation is required")
    rms = math.sqrt(sum((value - nominal) ** 2 for value in variations.values()) / len(variations))
    return rms, rms, rms


def evaluate_signed_shift(nominal: float, variations: dict[str, float]) -> tuple[float, float, float]:
    if len(variations) != 1:
        raise ValueError("signed_shift evaluation requires exactly one successful variation")
    shift = next(iter(variations.values())) - nominal
    return max(0.0, shift), max(0.0, -shift), abs(shift)


def write_evaluated_source(evaluated: EvaluatedSource, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evaluated.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _nominal_value(source: SystematicSource, results: list[VariationResult]) -> float:
    nominal_variation = source.nominal.get("variation") or source.nominal.get("nominal_variation")
    if nominal_variation is not None:
        for result in results:
            if result.variation == nominal_variation:
                return result.target_value
        raise ValueError(f"{source.name}: nominal variation {nominal_variation!r} did not succeed")
    for result in results:
        if result.variation == "nominal":
            return result.target_value
    return results[0].target_value

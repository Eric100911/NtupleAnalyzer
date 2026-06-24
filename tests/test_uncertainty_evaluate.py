from pathlib import Path

import pytest

from uncertainty_workflow.config import CorrelationSpec, SystematicSource
from uncertainty_workflow.evaluate import (
    evaluate_envelope,
    evaluate_rms,
    evaluate_source,
    evaluate_two_sided,
)
from uncertainty_workflow.registry import VariationResult


def _result(name: str, value: float, status: str = "success") -> VariationResult:
    return VariationResult(
        source="fit_background_model",
        variation=name,
        status=status,
        target_value=value,
        target_uncertainty=1.0,
        artifacts={},
        manifest_path=Path("manifest.json"),
    )


def _source(method: str = "envelope") -> SystematicSource:
    return SystematicSource(
        name="fit_background_model",
        category="fit_model",
        target="yield",
        enabled=True,
        nominal={"variation": "exponential"},
        variations=(),
        evaluation_method=method,
        rerun_from="fit",
        correlations=CorrelationSpec(),
    )


def test_evaluate_envelope() -> None:
    assert evaluate_envelope(10.0, {"nominal": 10.0, "up": 13.0, "down": 8.0}) == (3.0, 2.0, 2.5)


def test_evaluate_two_sided() -> None:
    assert evaluate_two_sided(10.0, {"up": 12.0, "down": 7.0}) == (2.0, 3.0, 2.5)


def test_evaluate_rms() -> None:
    up, down, sym = evaluate_rms(10.0, {"a": 12.0, "b": 8.0})
    assert up == pytest.approx(2.0)
    assert down == pytest.approx(2.0)
    assert sym == pytest.approx(2.0)


def test_evaluate_source_uses_configured_nominal() -> None:
    evaluated = evaluate_source(_source(), [_result("exponential", 100.0), _result("chebychev1", 103.0)])

    assert evaluated.nominal_value == 100.0
    assert evaluated.delta_up == 3.0
    assert evaluated.delta_down == 0.0
    assert evaluated.delta_sym == 1.5

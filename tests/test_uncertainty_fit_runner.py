from __future__ import annotations

import json

import pytest

from uncertainty_workflow.config import Variation, load_variation_config
from uncertainty_workflow.runners import _fit_config, run_fit_variation


def _fit_source():
    config = load_variation_config("configs/systematics/fit_variations.yaml")
    return next(source for source in config.sources if source.name == "fit_background_model")


def test_scalar_fit_variation_maps_to_jpsi_background() -> None:
    source = _fit_source()
    variation = next(item for item in source.variations if item.name == "chebychev2")

    config = _fit_config(source, variation)

    assert config["jpsi_background"] == "chebychev2"
    assert config["jpsi_signal"] == "dscb"
    assert config["jpsi_mass_window"] == [2.9, 3.3]


def test_fit_config_rejects_unknown_background() -> None:
    source = _fit_source()

    with pytest.raises(ValueError, match="jpsi_background"):
        _fit_config(source, Variation(name="bad", parameter_overrides={"value": "polynomial9"}))


def test_run_fit_variation_writes_result_and_manifest(tmp_path, monkeypatch) -> None:
    source = _fit_source()
    variation = next(item for item in source.variations if item.name == "chebychev1")
    input_file = tmp_path / "input.root"
    input_file.write_bytes(b"not a real root file")
    calls = []

    def fake_run_jjp_fit(*args, **kwargs):
        calls.append((args, kwargs))
        return {"yield": 42.0, "yield_err": 4.2, "fit_nll": 12.0, "fit_status": 0}

    monkeypatch.setattr("uncertainty_workflow.runners._run_jjp_fit", fake_run_jjp_fit)

    result = run_fit_variation(
        source,
        variation,
        input_file=input_file,
        output_dir=tmp_path / "systematics",
        jobs=2,
    )

    assert result.status == "success"
    assert result.target_value == 42.0
    assert result.target_uncertainty == 4.2
    assert result.artifacts["result_json"].exists()
    assert result.manifest_path.exists()
    assert calls[0][1]["jpsi_background"] == "chebychev1"
    payload = json.loads(result.artifacts["result_json"].read_text(encoding="utf-8"))
    assert payload["fit_config"]["jpsi_background"] == "chebychev1"


def test_run_fit_variation_uses_cache(tmp_path, monkeypatch) -> None:
    source = _fit_source()
    variation = next(item for item in source.variations if item.name == "exponential")
    input_file = tmp_path / "input.root"
    input_file.write_bytes(b"not a real root file")

    def fake_run_jjp_fit(*args, **kwargs):
        return {"yield": 10.0, "yield_err": 1.0, "fit_nll": 5.0, "fit_status": 0}

    monkeypatch.setattr("uncertainty_workflow.runners._run_jjp_fit", fake_run_jjp_fit)
    first = run_fit_variation(source, variation, input_file=input_file, output_dir=tmp_path / "systematics")

    def fail_run_jjp_fit(*args, **kwargs):
        raise AssertionError("cache was not used")

    monkeypatch.setattr("uncertainty_workflow.runners._run_jjp_fit", fail_run_jjp_fit)
    second = run_fit_variation(source, variation, input_file=input_file, output_dir=tmp_path / "systematics")

    assert second.status == "success"
    assert second.target_value == first.target_value

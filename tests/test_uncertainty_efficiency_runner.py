from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from efficiency_workflow.config import OfflineSelectionConfig
from uncertainty_workflow.config import CorrelationSpec, SystematicSource, Variation
from uncertainty_workflow.runners import run_efficiency_config_variation
from uncertainty_workflow.variations import offline_selection_from_variation


def _source(**kwargs) -> SystematicSource:
    values = {
        "name": "kaon_track_quality",
        "category": "efficiency_selection",
        "target": "yield",
        "enabled": True,
        "nominal": {"kaon_chi2_max": 8.0},
        "variations": (),
        "evaluation_method": "envelope",
        "rerun_from": "efficiency_extraction",
        "correlations": CorrelationSpec(),
    }
    values.update(kwargs)
    return SystematicSource(**values)


@dataclass(frozen=True)
class _YieldResult:
    nominal_corrected_yield: float = 123.0
    stat_unc: float = 4.0
    mc_stat_unc: float = 1.5

    def to_dict(self) -> dict[str, float]:
        return {
            "nominal_corrected_yield": self.nominal_corrected_yield,
            "stat_unc": self.stat_unc,
            "mc_stat_unc": self.mc_stat_unc,
        }


def test_offline_selection_rejects_unknown_override() -> None:
    with pytest.raises(ValueError, match="unknown OfflineSelectionConfig"):
        offline_selection_from_variation(
            _source(),
            Variation("bad", {"not_a_selection_field": 1}),
        )


def test_offline_selection_coerces_mass_window_list() -> None:
    config = offline_selection_from_variation(
        _source(nominal={}),
        Variation("narrow", {"jpsi_mass_window": [2.95, 3.25]}),
    )

    assert isinstance(config.jpsi_mass_window, tuple)
    assert config.jpsi_mass_window == (2.95, 3.25)


def test_run_efficiency_config_variation_writes_outputs_and_attaches_nominal_samples(tmp_path, monkeypatch) -> None:
    source = _source()
    variation = Variation("tight", {"kaon_chi2_max": 6.0})
    input_manifest = tmp_path / "inputs.json"
    input_manifest.write_text(json.dumps({"JJP_DPS1": ["raw.root"]}), encoding="utf-8")
    data_input = tmp_path / "data.root"
    data_input.write_bytes(b"not root")
    nominal_dir = tmp_path / "nominal_eff"
    other_sample = nominal_dir / "JJP_DPS2_CS"
    (other_sample / "maps").mkdir(parents=True)
    (other_sample / "manifest.json").write_text("{}", encoding="utf-8")
    (other_sample / "maps" / "manifest.json").write_text("{}", encoding="utf-8")
    calls: dict[str, object] = {}

    def fake_load_manifest(*args, **kwargs):
        return {"JJP_DPS1": ["raw.root"]}

    def fake_run_efficiency(files, sample, cfg, **kwargs):
        calls["cfg"] = cfg
        calls["eff_kwargs"] = kwargs
        return {"gen_systems": [], "event_step_flags": [], "efficiency_counts": [], "cutflow": []}

    def fake_write_bundle(output_dir, sample, input_files, gen_df, event_df, counts_df, cutflow_df):
        sample_dir = output_dir / sample
        sample_dir.mkdir(parents=True)
        (sample_dir / "manifest.json").write_text("{}", encoding="utf-8")
        return {}

    def fake_build_maps(input_sample_dir, output_maps_dir, **kwargs):
        output_maps_dir.mkdir(parents=True)
        (output_maps_dir / "manifest.json").write_text("{}", encoding="utf-8")
        calls["maps_kwargs"] = kwargs
        return {}

    def fake_compute_yield(data_input_file, efficiency_dir, **kwargs):
        calls["yield_efficiency_dir"] = efficiency_dir
        calls["yield_kwargs"] = kwargs
        return _YieldResult()

    monkeypatch.setattr("uncertainty_workflow.runners._load_efficiency_file_manifest", fake_load_manifest)
    monkeypatch.setattr("uncertainty_workflow.runners._run_efficiency_for_sample", fake_run_efficiency)
    monkeypatch.setattr("uncertainty_workflow.runners._write_efficiency_sample_bundle", fake_write_bundle)
    monkeypatch.setattr("uncertainty_workflow.runners._build_factorized_maps_for_sample", fake_build_maps)
    monkeypatch.setattr("uncertainty_workflow.runners._compute_efficiency_corrected_yield", fake_compute_yield)

    result = run_efficiency_config_variation(
        source,
        variation,
        input_manifest=input_manifest,
        data_input_file=data_input,
        nominal_efficiency_dir=nominal_dir,
        output_dir=tmp_path / "systematics",
        sample="JJP_DPS1",
        samples=("JJP_DPS1", "JJP_DPS2_CS"),
        nominal_sample="JJP_DPS1",
        jobs=2,
    )

    assert result.status == "success"
    assert result.target_value == 123.0
    assert result.target_uncertainty == 4.0
    assert isinstance(calls["cfg"], OfflineSelectionConfig)
    assert calls["cfg"].kaon_chi2_max == 6.0
    assert (calls["yield_efficiency_dir"] / "JJP_DPS2_CS").exists()
    assert calls["yield_kwargs"]["samples"] == ("JJP_DPS1", "JJP_DPS2_CS")
    payload = json.loads(result.artifacts["result_json"].read_text(encoding="utf-8"))
    assert payload["selection_config"]["kaon_chi2_max"] == 6.0
    assert payload["mc_stat_unc"] == 1.5


def test_run_efficiency_config_variation_uses_cache(tmp_path, monkeypatch) -> None:
    source = _source()
    variation = Variation("loose", {"kaon_chi2_max": 10.0})
    input_manifest = tmp_path / "inputs.json"
    input_manifest.write_text(json.dumps({"JJP_DPS1": ["raw.root"]}), encoding="utf-8")
    data_input = tmp_path / "data.root"
    data_input.write_bytes(b"not root")
    nominal_dir = tmp_path / "nominal_eff"
    (nominal_dir / "JJP_DPS1" / "maps").mkdir(parents=True)
    (nominal_dir / "JJP_DPS1" / "manifest.json").write_text("{}", encoding="utf-8")
    (nominal_dir / "JJP_DPS1" / "maps" / "manifest.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("uncertainty_workflow.runners._load_efficiency_file_manifest", lambda *a, **k: {"JJP_DPS1": ["raw.root"]})
    monkeypatch.setattr("uncertainty_workflow.runners._run_efficiency_for_sample", lambda *a, **k: {"gen_systems": [], "event_step_flags": [], "efficiency_counts": [], "cutflow": []})
    monkeypatch.setattr("uncertainty_workflow.runners._write_efficiency_sample_bundle", lambda output_dir, sample, *a: (output_dir / sample).mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr("uncertainty_workflow.runners._build_factorized_maps_for_sample", lambda input_sample_dir, output_maps_dir, **k: output_maps_dir.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr("uncertainty_workflow.runners._compute_efficiency_corrected_yield", lambda *a, **k: _YieldResult())

    first = run_efficiency_config_variation(
        source,
        variation,
        input_manifest=input_manifest,
        data_input_file=data_input,
        nominal_efficiency_dir=nominal_dir,
        output_dir=tmp_path / "systematics",
        sample="JJP_DPS1",
        samples=("JJP_DPS1",),
        nominal_sample="JJP_DPS1",
    )

    def fail_run_efficiency(*args, **kwargs):
        raise AssertionError("cache was not used")

    monkeypatch.setattr("uncertainty_workflow.runners._run_efficiency_for_sample", fail_run_efficiency)
    second = run_efficiency_config_variation(
        source,
        variation,
        input_manifest=input_manifest,
        data_input_file=data_input,
        nominal_efficiency_dir=nominal_dir,
        output_dir=tmp_path / "systematics",
        sample="JJP_DPS1",
        samples=("JJP_DPS1",),
        nominal_sample="JJP_DPS1",
    )

    assert second.status == "success"
    assert second.target_value == first.target_value


def test_run_efficiency_config_variation_writes_error_manifest(tmp_path, monkeypatch) -> None:
    source = _source()
    variation = Variation("tight", {"kaon_chi2_max": 6.0})
    input_manifest = tmp_path / "inputs.json"
    input_manifest.write_text(json.dumps({"JJP_DPS1": ["raw.root"]}), encoding="utf-8")
    data_input = tmp_path / "data.root"
    data_input.write_bytes(b"not root")
    nominal_dir = tmp_path / "nominal_eff"

    monkeypatch.setattr("uncertainty_workflow.runners._load_efficiency_file_manifest", lambda *a, **k: {"JJP_DPS1": ["raw.root"]})

    def fail_run_efficiency(*args, **kwargs):
        raise RuntimeError("broken extraction")

    monkeypatch.setattr("uncertainty_workflow.runners._run_efficiency_for_sample", fail_run_efficiency)

    result = run_efficiency_config_variation(
        source,
        variation,
        input_manifest=input_manifest,
        data_input_file=data_input,
        nominal_efficiency_dir=nominal_dir,
        output_dir=tmp_path / "systematics",
        sample="JJP_DPS1",
        samples=("JJP_DPS1",),
        nominal_sample="JJP_DPS1",
    )

    assert result.status == "failed"
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["error_type"] == "RuntimeError"

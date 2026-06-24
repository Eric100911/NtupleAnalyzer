from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from uncertainty_workflow.config import CorrelationSpec, SystematicSource, Variation, load_variation_config
from uncertainty_workflow.mc_stat import throw_efficiency_frame, throw_factorized_maps
from uncertainty_workflow.runners import run_mc_stat_variation


def _source(**kwargs) -> SystematicSource:
    values = {
        "name": "efficiency_mc_stat",
        "category": "mc_stat",
        "target": "yield",
        "enabled": True,
        "nominal": {"mode": "toy", "n_toys": 3, "seed": 12345, "clip": [1e-6, 1.0]},
        "variations": (),
        "evaluation_method": "rms",
        "rerun_from": "corrected_yield",
        "correlations": CorrelationSpec(),
    }
    values.update(kwargs)
    return SystematicSource(**values)


@dataclass(frozen=True)
class _YieldResult:
    nominal_corrected_yield: float
    stat_unc: float = 4.0
    mc_stat_unc: float = 1.5

    def to_dict(self) -> dict[str, float]:
        return {
            "nominal_corrected_yield": self.nominal_corrected_yield,
            "stat_unc": self.stat_unc,
            "mc_stat_unc": self.mc_stat_unc,
        }


def _map_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "factor_name": ["acceptance_jpsi", "acceptance_jpsi"],
            "fallback_level": ["fine", "fine"],
            "x_bin": [0, 1],
            "efficiency": [0.5, 0.8],
            "err_sym": [0.1, 0.0],
            "total": [100, 200],
        }
    )


def test_mc_stat_config_is_disabled_by_default() -> None:
    config = load_variation_config("configs/systematics/mc_stat.yaml")
    source = config.sources[0]

    assert source.name == "efficiency_mc_stat"
    assert source.category == "mc_stat"
    assert not source.enabled
    assert [variation.name for variation in source.variations] == ["toys"]


def test_throw_efficiency_frame_is_seed_reproducible_and_preserves_zero_uncertainty() -> None:
    first = throw_efficiency_frame(_map_frame(), rng=np.random.default_rng(7), clip=(1e-6, 1.0))
    second = throw_efficiency_frame(_map_frame(), rng=np.random.default_rng(7), clip=(1e-6, 1.0))

    pd.testing.assert_frame_equal(first, second)
    assert first.loc[1, "efficiency"] == 0.8
    assert first["x_bin"].tolist() == [0, 1]


def test_throw_efficiency_frame_clips_values() -> None:
    frame = _map_frame()
    frame.loc[0, "efficiency"] = 0.99
    frame.loc[0, "err_sym"] = 10.0

    thrown = throw_efficiency_frame(frame, rng=np.random.default_rng(1), clip=(0.2, 0.7))

    assert thrown["efficiency"].between(0.2, 0.7).all()


def test_throw_factorized_maps_writes_parquet_and_manifest(tmp_path) -> None:
    nominal = tmp_path / "nominal" / "JJP_DPS1" / "maps"
    nominal.mkdir(parents=True)
    _map_frame().to_parquet(nominal / "acceptance_jpsi.parquet", index=False)

    written = throw_factorized_maps(
        tmp_path / "nominal" / "JJP_DPS1",
        tmp_path / "toy" / "JJP_DPS1",
        rng=np.random.default_rng(3),
    )

    assert written["acceptance_jpsi"].exists()
    assert (tmp_path / "toy" / "JJP_DPS1" / "maps" / "manifest.json").exists()


def test_run_mc_stat_variation_analytic_reads_nominal_json(tmp_path) -> None:
    nominal_json = tmp_path / "yield.json"
    nominal_json.write_text(
        json.dumps({"nominal_corrected_yield": 100.0, "mc_stat_unc": 6.0}),
        encoding="utf-8",
    )

    result = run_mc_stat_variation(
        _source(),
        Variation("analytic", {}),
        output_dir=tmp_path / "systematics",
        mode="analytic",
        nominal_yield_json=nominal_json,
    )

    assert result.status == "success"
    assert result.target_value == 100.0
    assert result.target_uncertainty == 6.0


def test_run_mc_stat_variation_toys_writes_result_and_uses_cache(tmp_path, monkeypatch) -> None:
    data_input = tmp_path / "data.root"
    data_input.write_bytes(b"not root")
    nominal_dir = tmp_path / "nominal_eff"
    for sample in ("JJP_DPS1", "JJP_DPS2_CS"):
        maps_dir = nominal_dir / sample / "maps"
        maps_dir.mkdir(parents=True)
        _map_frame().to_parquet(maps_dir / "acceptance_jpsi.parquet", index=False)

    yields = iter([_YieldResult(100.0), _YieldResult(101.0), _YieldResult(98.0), _YieldResult(102.0)])

    def fake_compute_yield(*args, **kwargs):
        return next(yields)

    monkeypatch.setattr("uncertainty_workflow.runners._compute_efficiency_corrected_yield", fake_compute_yield)

    result = run_mc_stat_variation(
        _source(),
        Variation("toys", {}),
        output_dir=tmp_path / "systematics",
        mode="toy",
        data_input_file=data_input,
        nominal_efficiency_dir=nominal_dir,
        samples=("JJP_DPS1", "JJP_DPS2_CS"),
        nominal_sample="JJP_DPS1",
        n_toys=3,
    )

    assert result.status == "success"
    assert result.target_value == 100.0
    assert result.target_uncertainty == pytest.approx(((1.0**2 + 2.0**2 + 2.0**2) / 3.0) ** 0.5)
    payload = json.loads(result.artifacts["result_json"].read_text(encoding="utf-8"))
    assert payload["toy_yields"] == [101.0, 98.0, 102.0]

    def fail_compute_yield(*args, **kwargs):
        raise AssertionError("cache was not used")

    monkeypatch.setattr("uncertainty_workflow.runners._compute_efficiency_corrected_yield", fail_compute_yield)
    cached = run_mc_stat_variation(
        _source(),
        Variation("toys", {}),
        output_dir=tmp_path / "systematics",
        mode="toy",
        data_input_file=data_input,
        nominal_efficiency_dir=nominal_dir,
        samples=("JJP_DPS1", "JJP_DPS2_CS"),
        nominal_sample="JJP_DPS1",
        n_toys=3,
    )

    assert cached.status == "success"
    assert cached.target_value == result.target_value


def test_run_mc_stat_variation_writes_error_manifest(tmp_path, monkeypatch) -> None:
    data_input = tmp_path / "data.root"
    data_input.write_bytes(b"not root")
    nominal_dir = tmp_path / "nominal_eff"
    (nominal_dir / "JJP_DPS1" / "maps").mkdir(parents=True)

    def fail_compute_yield(*args, **kwargs):
        raise RuntimeError("nominal failed")

    monkeypatch.setattr("uncertainty_workflow.runners._compute_efficiency_corrected_yield", fail_compute_yield)

    result = run_mc_stat_variation(
        _source(),
        Variation("toys", {}),
        output_dir=tmp_path / "systematics",
        mode="toy",
        data_input_file=data_input,
        nominal_efficiency_dir=nominal_dir,
        samples=("JJP_DPS1",),
        nominal_sample="JJP_DPS1",
    )

    assert result.status == "failed"
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["error_type"] == "RuntimeError"

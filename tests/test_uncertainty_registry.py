from pathlib import Path

import pytest

from uncertainty_workflow.config import load_variation_config
from uncertainty_workflow.registry import SystematicRegistry


def test_registry_lists_sources():
    config = load_variation_config("configs/systematics/fit_variations.yaml")
    registry = SystematicRegistry()
    for source in config.sources:
        registry.register(source)

    assert registry.list_sources() == ["fit_background_model", "fit_range"]


def test_registry_rejects_duplicate_registration():
    config = load_variation_config("configs/systematics/fit_variations.yaml")
    registry = SystematicRegistry()
    registry.register(config.sources[0])

    with pytest.raises(ValueError, match="duplicate"):
        registry.register(config.sources[0])


def test_registry_dry_run_result_paths():
    config = load_variation_config("configs/systematics/fit_variations.yaml")
    source = next(source for source in config.sources if source.name == "fit_background_model")
    registry = SystematicRegistry()
    registry.register(source)

    results = registry.run(
        source,
        output_dir=Path("outputs/systematics"),
        nominal_dir=Path("outputs/systematics/nominal"),
        dry_run=True,
    )

    assert [result.variation for result in results] == ["exponential", "chebychev1", "chebychev2"]
    assert results[0].status == "dry_run"
    assert results[0].manifest_path == Path("outputs/systematics/variations/fit_background_model/exponential/manifest.json")
    assert len(results[0].artifacts["run_hash"].name) == 64


def test_registry_requires_runner_for_real_run():
    config = load_variation_config("configs/systematics/fit_variations.yaml")
    source = config.sources[0]
    registry = SystematicRegistry()
    registry.register(source)

    with pytest.raises(NotImplementedError):
        registry.run(source, output_dir=Path("out"), nominal_dir=Path("nominal"), dry_run=False)


def test_old_fit_splot_path_imports_forwarded_symbol():
    import importlib
    import sys

    sys.modules.pop("fit_splot", None)
    with pytest.warns(DeprecationWarning, match="fit_splot.py moved"):
        module = importlib.import_module("fit_splot")

    assert callable(module.run_jjp_fit)

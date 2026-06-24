from pathlib import Path

import pytest

from uncertainty_workflow.config import load_variation_config, load_variation_configs
from uncertainty_workflow.provenance import hash_config


def test_load_default_variation_configs():
    config = load_variation_configs([Path("configs/systematics")])
    names = {source.name for source in config.sources}

    assert "kaon_track_quality" in names
    assert "muon_pt_threshold" in names
    assert "fit_background_model" in names
    enabled = {source.name for source in config.sources if source.enabled}
    assert enabled == {"fit_background_model"}


def test_parse_mapping_variations():
    config = load_variation_config("configs/systematics/efficiency_variations.yaml")
    source = next(source for source in config.sources if source.name == "kaon_track_quality")

    assert source.category == "efficiency_selection"
    assert source.rerun_from == "efficiency_extraction"
    assert [variation.name for variation in source.variations] == ["loose", "tight"]
    assert source.variations[0].parameter_overrides["kaon_chi2_max"] == 10.0


def test_parse_named_list_variations():
    config = load_variation_config("configs/systematics/fit_variations.yaml")
    source = next(source for source in config.sources if source.name == "fit_range")

    assert [variation.name for variation in source.variations] == ["nominal", "narrow", "wide"]
    assert source.variations[1].parameter_overrides["jpsi_mass_window"] == [2.95, 3.25]


def test_reject_duplicate_sources(tmp_path):
    path = tmp_path / "duplicate.yaml"
    path.write_text(
        """
schema_version: "ntuple-analyzer-systematics/v1"
sources:
  - name: repeated
    category: fit_model
    variations: []
  - name: repeated
    category: fit_model
    variations: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate source"):
        load_variation_config(path)


def test_reject_unknown_source_key(tmp_path):
    path = tmp_path / "unknown.yaml"
    path.write_text(
        """
schema_version: "ntuple-analyzer-systematics/v1"
sources:
  - name: bad
    category: fit_model
    extra_key: true
    variations: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown keys"):
        load_variation_config(path)


def test_config_hash_is_stable():
    config = load_variation_config("configs/systematics/fit_variations.yaml")

    assert hash_config(config) == hash_config(config)

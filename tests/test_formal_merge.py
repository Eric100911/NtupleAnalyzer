from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from efficiency_workflow.formal_merge import FormalMergeValidationError, validate_formal_merge


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _formal_fixture(root: Path) -> tuple[Path, Path, list[Path], pd.DataFrame, list[str]]:
    sample = "JJP_DPS1"
    files = ["root://example//a.root", "root://example//b.root"]
    master_id = "formal-master-id"
    manifest = root / "formal.json"
    _write_json(manifest, {
        "schema_version": "ntuple-analyzer-tps-manifest/v1",
        "sample": sample,
        "files": files,
        "n_files": 2,
        "master_n_files": 2,
        "manifest_id": master_id,
        "master_manifest_id": master_id,
        "inventory": [
            {"source_file": files[0], "total_entries": 10, "retained_candidate_events": 3},
            {"source_file": files[1], "total_entries": 20, "retained_candidate_events": 4},
        ],
    })
    formal_shards = root / "formal-shards"
    for index, source in enumerate(files):
        _write_json(formal_shards / f"shard_{index:04d}.json", {
            "sample": sample,
            "shard_index": index,
            "n_shards": 2,
            "master_manifest_id": master_id,
            "files": [source],
        })
    sample_dirs = []
    for index in range(2):
        sample_dir = root / "outputs" / f"shard_{index:04d}" / sample
        _write_json(sample_dir / "sample_manifest.json", {
            "sample": sample,
            "input_files": [files[index]],
            "coverage": {"master_manifest_id": master_id},
        })
        sample_dirs.append(sample_dir)
    coverage = pd.DataFrame([
        {
            "source_file": files[0], "status": "success", "source_entries": 10,
            "entries_scanned": 10, "retained_candidate_events": 3,
            "production_config_hash": "production", "compatibility_hash": "compatibility",
            "efficiency_config_hash": "efficiency",
        },
        {
            "source_file": files[1], "status": "success", "source_entries": 20,
            "entries_scanned": 20, "retained_candidate_events": 4,
            "production_config_hash": "production", "compatibility_hash": "compatibility",
            "efficiency_config_hash": "efficiency",
        },
    ])
    return manifest, formal_shards, sample_dirs, coverage, files


def test_formal_merge_report_proves_complete_exact_coverage(tmp_path: Path) -> None:
    manifest, formal_shards, sample_dirs, coverage, files = _formal_fixture(tmp_path)

    report = validate_formal_merge(
        sample="JJP_DPS1", sample_dirs=sample_dirs, coverage_df=coverage,
        declared_files=files, formal_manifest_path=manifest, formal_shards_dir=formal_shards,
    )

    assert report["passed"] is True
    assert report["shards"]["exact_index_set"] is True
    assert report["coverage"]["complete"] is True
    assert report["coverage"]["scanned_entries"] == 30
    assert report["coverage"]["manifest_retained_candidate_events"] == 7
    assert report["hashes"]["unique"] is True
    assert report["formal_manifest"]["sha256"]


def test_formal_merge_rejects_missing_shard_and_url_coverage(tmp_path: Path) -> None:
    manifest, formal_shards, sample_dirs, coverage, files = _formal_fixture(tmp_path)

    with pytest.raises(FormalMergeValidationError) as exc_info:
        validate_formal_merge(
            sample="JJP_DPS1", sample_dirs=sample_dirs[:1], coverage_df=coverage.iloc[:1],
            declared_files=files[:1], formal_manifest_path=manifest, formal_shards_dir=formal_shards,
        )

    report = exc_info.value.report
    assert report["passed"] is False
    assert report["shards"]["exact_index_set"] is False
    assert any("exactly match formal manifest" in item for item in report["errors"])

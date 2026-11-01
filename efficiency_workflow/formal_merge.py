"""Fail-closed validation for merges driven by a formal TPS manifest.

The normal shard merger intentionally supports small development subsets.  A
production merge supplied with a formal master manifest must instead prove
complete, exactly-once processing before any merged products are written.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pandas as pd

from .io import read_json


_SHARD_RE = re.compile(r"shard_(\d+)$")
_REQUIRED_COVERAGE_COLUMNS = {
    "source_file",
    "status",
    "source_entries",
    "entries_scanned",
    "retained_candidate_events",
    "production_config_hash",
    "compatibility_hash",
    "efficiency_config_hash",
}


class FormalMergeValidationError(RuntimeError):
    """A validation error which retains the complete machine-readable report."""

    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        errors = report.get("errors", [])
        super().__init__("Formal merge validation failed: " + "; ".join(str(item) for item in errors[:3]))


def _append_error(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _shard_index(path: Path) -> int | None:
    match = _SHARD_RE.fullmatch(path.name)
    return int(match.group(1)) if match else None


def _unique_nonempty(frame: pd.DataFrame, column: str, errors: list[str]) -> list[str]:
    if column not in frame:
        return []
    values = sorted({str(item) for item in frame[column].dropna() if str(item)})
    if len(values) != 1:
        errors.append(f"Coverage must contain exactly one non-empty {column}, found {len(values)}")
    return values


def _inventory_by_url(manifest: dict[str, Any], errors: list[str]) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    rows = manifest.get("inventory", [])
    if not rows:
        return inventory
    if not isinstance(rows, list):
        errors.append("Formal manifest inventory must be a list")
        return inventory
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("source_file"), str):
            errors.append("Formal manifest inventory contains an invalid row")
            continue
        source = str(row["source_file"])
        if source in inventory:
            errors.append(f"Formal manifest inventory contains duplicate URL: {source}")
        inventory[source] = row
    return inventory


def validate_formal_merge(
    *,
    sample: str,
    sample_dirs: list[Path],
    coverage_df: pd.DataFrame,
    declared_files: list[str],
    formal_manifest_path: Path,
    formal_shards_dir: Path,
) -> dict[str, Any]:
    """Validate a complete formal merge and return a report, or fail closed.

    ``formal_shards_dir`` is the directory containing the immutable
    ``shard_XXXX.json`` manifests used by workers.  Its index set is the
    expected output-shard set; this deliberately rejects missing or extra
    directories instead of treating a subset as a successful merge.
    """
    errors: list[str] = []
    formal_manifest_path = Path(formal_manifest_path)
    formal_shards_dir = Path(formal_shards_dir)
    try:
        formal_manifest = read_json(formal_manifest_path)
    except Exception as exc:
        raise FormalMergeValidationError({
            "schema_version": "ntuple-analyzer-formal-merge-report/v1",
            "sample": sample,
            "passed": False,
            "formal_manifest": {
                "path": str(formal_manifest_path),
                "sha256": None,
                "master_manifest_sha256": None,
                "manifest_id": None,
                "master_manifest_id": None,
                "n_files": None,
            },
            "errors": [f"Unable to read formal manifest: {exc}"],
        }) from exc
    if not isinstance(formal_manifest, dict):
        raise FormalMergeValidationError({
            "schema_version": "ntuple-analyzer-formal-merge-report/v1",
            "sample": sample,
            "passed": False,
            "formal_manifest": {
                "path": str(formal_manifest_path),
                "sha256": hashlib.sha256(formal_manifest_path.read_bytes()).hexdigest(),
                "master_manifest_sha256": hashlib.sha256(formal_manifest_path.read_bytes()).hexdigest(),
                "manifest_id": None,
                "master_manifest_id": None,
                "n_files": None,
            },
            "errors": ["Formal manifest is not a JSON object"],
        })

    formal_files_raw = formal_manifest.get("files")
    formal_files = [str(item) for item in formal_files_raw] if isinstance(formal_files_raw, list) else []
    _append_error(errors, bool(formal_files), "Formal manifest has no files list")
    _append_error(errors, len(formal_files) == len(set(formal_files)), "Formal manifest files list contains duplicate URLs")
    _append_error(errors, formal_manifest.get("sample") == sample, "Formal manifest sample does not match merge sample")
    try:
        manifest_file_count = int(formal_manifest.get("master_n_files", formal_manifest.get("n_files", len(formal_files))))
    except (TypeError, ValueError):
        manifest_file_count = None
        errors.append("Formal manifest file count is not an integer")
    _append_error(errors, manifest_file_count == len(formal_files), "Formal manifest file count does not match files list")
    master_manifest_id = formal_manifest.get("master_manifest_id", formal_manifest.get("manifest_id"))
    _append_error(errors, isinstance(master_manifest_id, str) and bool(master_manifest_id), "Formal manifest has no master manifest ID")
    manifest_sha256 = hashlib.sha256(formal_manifest_path.read_bytes()).hexdigest()

    inventory = _inventory_by_url(formal_manifest, errors)
    if inventory:
        _append_error(errors, set(inventory) == set(formal_files), "Formal manifest inventory URLs do not exactly match files")

    expected_indices: list[int] = []
    formal_shard_urls: list[str] = []
    formal_n_shards: set[int] = set()
    if not formal_shards_dir.is_dir():
        errors.append(f"Formal shard manifest directory does not exist: {formal_shards_dir}")
    else:
        shard_paths = sorted(formal_shards_dir.glob("shard_*.json"))
        if not shard_paths:
            errors.append(f"No formal shard manifests found in {formal_shards_dir}")
        for path in shard_paths:
            match = re.fullmatch(r"shard_(\d+)\.json", path.name)
            if not match:
                errors.append(f"Invalid formal shard manifest name: {path.name}")
                continue
            shard_index = int(match.group(1))
            expected_indices.append(shard_index)
            try:
                shard_manifest = read_json(path)
            except Exception as exc:
                errors.append(f"Unable to read formal shard manifest {path}: {exc}")
                continue
            if not isinstance(shard_manifest, dict):
                errors.append(f"Formal shard manifest is not an object: {path}")
                continue
            _append_error(errors, shard_manifest.get("sample") == sample, f"Formal shard {path.name} has another sample")
            _append_error(errors, shard_manifest.get("shard_index") == shard_index, f"Formal shard {path.name} index disagrees with file name")
            _append_error(errors, shard_manifest.get("master_manifest_id") == master_manifest_id, f"Formal shard {path.name} has another master manifest ID")
            shard_n = shard_manifest.get("n_shards")
            if isinstance(shard_n, int) and shard_n > 0:
                formal_n_shards.add(shard_n)
            else:
                errors.append(f"Formal shard {path.name} has no positive n_shards")
            shard_files = shard_manifest.get("files")
            if not isinstance(shard_files, list):
                errors.append(f"Formal shard {path.name} has no files list")
            else:
                formal_shard_urls.extend(str(item) for item in shard_files)
    _append_error(errors, len(expected_indices) == len(set(expected_indices)), "Formal shard manifest indices are duplicated")
    if len(formal_n_shards) == 1:
        expected_count = next(iter(formal_n_shards))
        _append_error(errors, set(expected_indices) == set(range(expected_count)), "Formal shard manifests do not have the exact 0..n_shards-1 index set")
    elif formal_n_shards:
        errors.append("Formal shard manifests disagree on n_shards")
    _append_error(errors, len(formal_shard_urls) == len(set(formal_shard_urls)), "Formal shard manifests declare duplicate URLs")
    _append_error(errors, set(formal_shard_urls) == set(formal_files), "Formal shard URL union does not exactly match formal manifest")

    observed_indices = [index for path in sample_dirs if (index := _shard_index(path.parent)) is not None]
    invalid_output_dirs = [str(path.parent) for path in sample_dirs if _shard_index(path.parent) is None]
    if invalid_output_dirs:
        errors.append(f"Output shard directories have invalid names: {invalid_output_dirs[:3]}")
    _append_error(errors, len(observed_indices) == len(set(observed_indices)), "Merged output contains duplicate shard indices")
    _append_error(errors, set(observed_indices) == set(expected_indices), "Output shard index set does not exactly match formal shard manifests")

    missing_columns = sorted(_REQUIRED_COVERAGE_COLUMNS - set(coverage_df.columns))
    if missing_columns:
        errors.append(f"Coverage is missing required columns: {', '.join(missing_columns)}")
    coverage_urls = set(coverage_df["source_file"].astype(str)) if "source_file" in coverage_df else set()
    declared_urls = set(declared_files)
    _append_error(errors, len(declared_files) == len(declared_urls), "Merged shard manifests declare duplicate URLs")
    _append_error(errors, declared_urls == set(formal_files), "Declared input URL union does not exactly match formal manifest")
    _append_error(errors, coverage_urls == set(formal_files), "Coverage URL union does not exactly match formal manifest")
    if "source_file" in coverage_df:
        _append_error(errors, not coverage_df["source_file"].duplicated().any(), "Coverage has more than one row for an input URL")
    if "status" in coverage_df:
        _append_error(errors, (coverage_df["status"] == "success").all(), "Coverage contains a non-success status")
    if {"source_entries", "entries_scanned"}.issubset(coverage_df):
        _append_error(errors, (coverage_df["source_entries"] == coverage_df["entries_scanned"]).all(), "Not all source entries were scanned")

    if inventory and "source_file" in coverage_df:
        indexed = coverage_df.set_index("source_file", drop=False)
        for source, row in inventory.items():
            if source not in indexed.index:
                continue
            observed = indexed.loc[source]
            if isinstance(observed, pd.DataFrame):
                continue
            if "total_entries" in row and "source_entries" in observed and int(observed["source_entries"]) != int(row["total_entries"]):
                errors.append(f"Coverage source entries disagree with formal inventory for {source}")
            expected_retained = row.get("retained_candidate_events", row.get("retained_events"))
            if expected_retained is not None and "retained_candidate_events" in observed and int(observed["retained_candidate_events"]) != int(expected_retained):
                errors.append(f"Coverage retained-event count disagrees with formal inventory for {source}")

    production_hashes = _unique_nonempty(coverage_df, "production_config_hash", errors)
    compatibility_hashes = _unique_nonempty(coverage_df, "compatibility_hash", errors)
    efficiency_hashes = _unique_nonempty(coverage_df, "efficiency_config_hash", errors)
    shard_master_ids: set[str] = set()
    for sample_dir in sample_dirs:
        manifest_path = sample_dir / "sample_manifest.json"
        if not manifest_path.exists():
            errors.append(f"Missing shard sample manifest: {manifest_path}")
            continue
        payload = read_json(manifest_path)
        coverage = payload.get("coverage", {}) if isinstance(payload, dict) else {}
        value = coverage.get("master_manifest_id") if isinstance(coverage, dict) else None
        if value:
            shard_master_ids.add(str(value))
    _append_error(errors, shard_master_ids == {str(master_manifest_id)}, "Shard outputs do not carry the formal master manifest ID")

    def _total(column: str) -> int | None:
        return int(coverage_df[column].sum()) if column in coverage_df else None

    inventory_totals = formal_manifest.get("inventory_totals", {})
    manifest_total_entries = None
    manifest_retained_events = None
    if inventory:
        manifest_total_entries = sum(int(row.get("total_entries", 0)) for row in inventory.values())
        retained_values = [row.get("retained_candidate_events", row.get("retained_events")) for row in inventory.values()]
        if all(value is not None for value in retained_values):
            manifest_retained_events = sum(int(value) for value in retained_values)
    elif isinstance(inventory_totals, dict):
        manifest_total_entries = inventory_totals.get("total_entries")
        manifest_retained_events = inventory_totals.get("retained_candidate_events")

    scanned_entries = _total("entries_scanned")
    source_entries = _total("source_entries")
    retained_events = _total("retained_candidate_events")
    if manifest_total_entries is not None and source_entries is not None:
        _append_error(
            errors,
            source_entries == int(manifest_total_entries),
            "Coverage source-entry total does not match formal manifest inventory total",
        )
    if manifest_retained_events is not None and retained_events is not None:
        _append_error(
            errors,
            retained_events == int(manifest_retained_events),
            "Coverage retained-event total does not match formal manifest inventory total",
        )
    complete_coverage = not errors
    report: dict[str, Any] = {
        "schema_version": "ntuple-analyzer-formal-merge-report/v1",
        "sample": sample,
        "passed": complete_coverage,
        "formal_manifest": {
            "path": str(formal_manifest_path),
            "sha256": manifest_sha256,
            "master_manifest_sha256": manifest_sha256,
            "manifest_id": formal_manifest.get("manifest_id"),
            "master_manifest_id": master_manifest_id,
            "n_files": len(formal_files),
        },
        "shards": {
            "expected_indices": sorted(expected_indices),
            "observed_indices": sorted(observed_indices),
            "exact_index_set": set(expected_indices) == set(observed_indices),
        },
        "coverage": {
            "formal_files": len(formal_files),
            "declared_files": len(declared_files),
            "coverage_rows": int(len(coverage_df)),
            "success_rows": int((coverage_df["status"] == "success").sum()) if "status" in coverage_df else None,
            "declared_url_union_matches_formal": declared_urls == set(formal_files),
            "coverage_url_union_matches_formal": coverage_urls == set(formal_files),
            "one_success_coverage_row_per_file": (
                len(coverage_df) == len(formal_files)
                and "source_file" in coverage_df
                and not coverage_df["source_file"].duplicated().any()
                and "status" in coverage_df
                and (coverage_df["status"] == "success").all()
            ),
            "scanned_equals_source_entries": (
                {"source_entries", "entries_scanned"}.issubset(coverage_df)
                and (coverage_df["source_entries"] == coverage_df["entries_scanned"]).all()
            ),
            "scanned_entries": scanned_entries,
            "source_entries": source_entries,
            "manifest_total_entries": manifest_total_entries,
            "retained_candidate_events": retained_events,
            "manifest_retained_candidate_events": manifest_retained_events,
            "complete": complete_coverage,
        },
        "hashes": {
            "production_config_hashes": production_hashes,
            "compatibility_hashes": compatibility_hashes,
            "efficiency_config_hashes": efficiency_hashes,
            "unique": len(production_hashes) == len(compatibility_hashes) == len(efficiency_hashes) == 1,
        },
        "errors": errors,
    }
    if errors:
        raise FormalMergeValidationError(report)
    return report

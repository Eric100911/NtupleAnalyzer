"""Read and convert the retained-event inventory for TPS efficiency jobs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TpsInventoryRow:
    source_file: str
    total_entries: int
    retained_candidate_events: int


def _normalise_url(source_file: str) -> str:
    """Normalise the triple-slash cceos spelling used in old inventories."""
    source_file = source_file.strip()
    if source_file.startswith("root://cceos.ihep.ac.cn:1094///"):
        return source_file.replace("root://cceos.ihep.ac.cn:1094///", "root://cceos.ihep.ac.cn//", 1)
    return source_file


def read_tps_inventory(path: str | Path) -> list[TpsInventoryRow]:
    """Read three-column source, total entries, retained events rows."""
    inventory_path = Path(path)
    rows: list[TpsInventoryRow] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(inventory_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 3:
            raise ValueError(
                f"{inventory_path}:{line_number}: expected 3 columns "
                f"(source_file total_entries retained_events), got {len(fields)}"
            )
        source_file = _normalise_url(fields[0])
        if not source_file.startswith(("root://", "/")):
            raise ValueError(f"{inventory_path}:{line_number}: unsupported source path {fields[0]!r}")
        if source_file in seen:
            raise ValueError(f"{inventory_path}:{line_number}: duplicate source file {source_file!r}")
        try:
            total_entries = int(fields[1])
            retained_candidate_events = int(fields[2])
        except ValueError as exc:
            raise ValueError(f"{inventory_path}:{line_number}: entry counts must be integers") from exc
        if total_entries < 0 or retained_candidate_events < 0 or retained_candidate_events > total_entries:
            raise ValueError(f"{inventory_path}:{line_number}: invalid entry counts {fields[1:]}")
        seen.add(source_file)
        rows.append(TpsInventoryRow(source_file, total_entries, retained_candidate_events))
    if not rows:
        raise ValueError(f"TPS inventory is empty: {inventory_path}")
    return rows


def build_tps_manifest(rows: list[TpsInventoryRow], sample: str, source_inventory: str) -> dict[str, Any]:
    """Build a versioned JSON manifest accepted by the efficiency CLI."""
    if not sample.strip():
        raise ValueError("sample name must be non-empty")
    inventory = [
        {
            "source_file": row.source_file,
            "total_entries": row.total_entries,
            "retained_candidate_events": row.retained_candidate_events,
        }
        for row in rows
    ]
    payload: dict[str, Any] = {
        "schema_version": "ntuple-analyzer-tps-manifest/v1",
        "sample": sample,
        "files": [row.source_file for row in rows],
        "n_files": len(rows),
        "master_n_files": len(rows),
        "source_inventory": source_inventory,
        "inventory_columns": ["source_file", "total_entries", "retained_candidate_events"],
        "inventory_totals": {
            "total_entries": sum(row.total_entries for row in rows),
            "retained_candidate_events": sum(row.retained_candidate_events for row in rows),
        },
        "inventory": inventory,
    }
    from .io import stable_data_hash

    payload["manifest_id"] = stable_data_hash(payload)
    payload["master_manifest_id"] = payload["manifest_id"]
    return payload


def write_tps_manifest(rows: list[TpsInventoryRow], sample: str, source_inventory: str, output: str | Path) -> None:
    payload = build_tps_manifest(rows, sample, source_inventory)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

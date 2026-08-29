from __future__ import annotations

import json

import pytest

from efficiency_workflow.tps_manifest import build_tps_manifest, read_tps_inventory


def test_read_tps_inventory_and_build_manifest(tmp_path) -> None:
    inventory = tmp_path / "inventory.txt"
    inventory.write_text(
        "# source total retained\n"
        "root://cceos.ihep.ac.cn:1094///store/a.root 100 7\n"
        "/tmp/b.root 20 2\n",
        encoding="utf-8",
    )

    rows = read_tps_inventory(inventory)
    payload = build_tps_manifest(rows, "JJP_TPS", str(inventory))

    assert payload["files"] == ["root://cceos.ihep.ac.cn//store/a.root", "/tmp/b.root"]
    assert payload["inventory_totals"] == {"total_entries": 120, "retained_events": 9}
    assert payload["inventory"][0]["retained_events"] == 7


def test_read_tps_inventory_rejects_bad_counts(tmp_path) -> None:
    inventory = tmp_path / "inventory.txt"
    inventory.write_text("/tmp/a.root 10 11\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid entry counts"):
        read_tps_inventory(inventory)


def test_manifest_is_json_serialisable(tmp_path) -> None:
    inventory = tmp_path / "inventory.txt"
    inventory.write_text("/tmp/a.root 10 1\n", encoding="utf-8")
    payload = build_tps_manifest(read_tps_inventory(inventory), "JJP_TPS", str(inventory))
    json.dumps(payload)

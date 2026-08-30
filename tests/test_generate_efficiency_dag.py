from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


_SPEC = importlib.util.spec_from_file_location(
    "generate_efficiency_dag", Path("condor/generate_efficiency_dag.py")
)
assert _SPEC and _SPEC.loader
generator = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(generator)


def fixture_inputs(tmp_path: Path) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    manifest = tmp_path / "shard_0000.json"
    manifest.write_text(json.dumps({
        "sample": "JJP_DPS1",
        "shard_index": 0,
        "files": ["root://example.invalid//sample.root"],
    }), encoding="utf-8")
    queue = tmp_path / "queue.txt"
    queue.write_text(f"JJP_DPS1 0 {manifest}\n", encoding="utf-8")
    tarball = tmp_path / "runtime.tar.gz"
    tarball.write_bytes(b"fixture")
    proxy = tmp_path / "x509up"
    proxy.write_text("fixture proxy\n", encoding="utf-8")
    return {
        "queue": queue,
        "tarball": tarball,
        "proxy": proxy,
        "output": tmp_path / "campaign-output",
        "dag_dir": tmp_path / "dag",
    }


def valid_kwargs(inputs: dict[str, Path]) -> dict[str, object]:
    return {
        "sample": "JJP_DPS1",
        "queue_file": inputs["queue"],
        "output_dir": inputs["output"],
        "runtime_tarball": str(inputs["tarball"]),
        "dag_dir": inputs["dag_dir"],
        "proxy_path": str(inputs["proxy"]),
        "tree_path": "auto",
        "efficiency_config": "configs/efficiency/tps_nominal.yaml",
        "config_policy": "strict",
    }


def test_generated_dag_transfers_manifest_and_is_merge_only(tmp_path: Path) -> None:
    inputs = fixture_inputs(tmp_path)
    dag_path = generator.build_dag(**valid_kwargs(inputs), dagman_retries=4)

    dag = dag_path.read_text(encoding="utf-8")
    shard_sub = (inputs["dag_dir"] / "sub_shard_JJP_DPS1_0000.sub").read_text(encoding="utf-8")
    post_sub = (inputs["dag_dir"] / "sub_post_JJP_DPS1.sub").read_text(encoding="utf-8")
    manifest = tmp_path / "shard_0000.json"
    assert "RETRY SHARD_0000 4" in dag
    assert f"transfer_input_files = {inputs['tarball'].resolve()},{manifest.resolve()}" in shard_sub
    assert "--shard-manifest shard_0000.json" in shard_sub
    assert str(manifest.resolve()) not in shard_sub.split("arguments =", 1)[1].splitlines()[0]
    assert "run_jjp_efficiency_merge_only.sh" in post_sub
    assert "run_jjp_efficiency_post.sh" not in post_sub
    assert str(tmp_path / "campaign-output" / "_merge_JJP_DPS1") in post_sub
    assert str(tmp_path / "campaign-output" / "JJP_DPS1") in post_sub
    assert str(tmp_path / "campaign-output" / "JJP_DPS1" / "JJP_DPS1") not in post_sub


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("tree_path", "X_data", "tree-path auto"),
        ("config_policy", "legacy", "config-policy strict"),
        ("efficiency_backend", "python-loop", "efficiency-backend vectorized"),
        ("cleanup_shards", True, "cleanup is prohibited"),
        ("dagman_retries", -1, "dagman-retries"),
    ],
)
def test_campaign_contract_fails_closed(tmp_path: Path, field: str, value: object, match: str) -> None:
    kwargs = valid_kwargs(fixture_inputs(tmp_path))
    kwargs[field] = value
    with pytest.raises(ValueError, match=match):
        generator.build_dag(**kwargs)


def test_proxy_and_existing_sample_root_are_rejected(tmp_path: Path) -> None:
    inputs = fixture_inputs(tmp_path)
    kwargs = valid_kwargs(inputs)
    kwargs["output_dir"] = tmp_path / "unsafe;root"
    with pytest.raises(ValueError, match="safe token"):
        generator.build_dag(**kwargs)

    kwargs = valid_kwargs(inputs)
    kwargs["proxy_path"] = str(tmp_path / "missing_proxy")
    with pytest.raises(FileNotFoundError, match="proxy-path"):
        generator.build_dag(**kwargs)

    inputs = fixture_inputs(tmp_path / "occupied")
    (inputs["output"] / "JJP_DPS1").mkdir(parents=True)
    with pytest.raises(FileExistsError, match="Refusing to reuse"):
        generator.build_dag(**valid_kwargs(inputs))

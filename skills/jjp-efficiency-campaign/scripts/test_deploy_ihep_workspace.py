from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


_SPEC = importlib.util.spec_from_file_location("deploy_ihep_workspace", Path("skills/jjp-efficiency-campaign/scripts/deploy_ihep_workspace.py"))
assert _SPEC and _SPEC.loader
deploy = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(deploy)


def freeze_fixture(tmp_path: Path, *, tps_sample: str = "JJP_TPS") -> tuple[Path, Path]:
    root = tmp_path / "ihep_freeze_v2"; root.mkdir()
    (root / "runtime").mkdir(); (root / "runtime" / "runtime.tar.gz").write_bytes(b"runtime")
    config = root / "configs" / "efficiency" / "tps_nominal.yaml"; config.parent.mkdir(parents=True); config.write_text("strict: true\n")
    samples: dict[str, object] = {}
    for sample in deploy.BASE_SAMPLES + (tps_sample,):
        base = root / "queues" / sample / "manifests"; shards = base / "shards"; shards.mkdir(parents=True)
        shard = shards / "shard_0000.json"; shard.write_text(json.dumps({"sample": sample}), encoding="utf-8")
        formal = base / "formal.json"; formal.write_text(json.dumps({"sample": sample}), encoding="utf-8")
        queue = base / "queue.txt"; queue.write_text(f"{sample} 0 {shard}\n", encoding="utf-8")
        samples[sample] = {"formal_manifest": formal.relative_to(root).as_posix(), "queue": queue.relative_to(root).as_posix(), "shard_manifests": [shard.relative_to(root).as_posix()]}
    report = root / "ihep_freeze_v2.report.json"
    report.write_text(json.dumps({"freeze_id": "ihep_freeze_v2", "runtime_tarball": "runtime/runtime.tar.gz", "efficiency_config": "configs/efficiency/tps_nominal.yaml", "samples": samples}), encoding="utf-8")
    return root, report


def test_dry_run_uses_freeze_report_without_ssh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, report = freeze_fixture(tmp_path)
    monkeypatch.setattr(deploy.subprocess, "run", lambda *args, **kwargs: pytest.fail("dry run contacted a host"))
    payload, files = deploy.plan(root, report, execute=False, authorization_id=None, remote_root_value="/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root")
    assert payload["dry_run"] is True
    assert set(payload["samples"]) == set(deploy.SAMPLES)
    assert "inputs/JJP_DPS1/shards/shard_0000.json" in files
    assert payload["remote"]["ssh"] == ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o", "ControlMaster=no", "wangchi@lxlogin.ihep.ac.cn"]
    assert payload["guarantees"]["hep_sub_process_calls"] == 0


def test_legacy_tps_formal_identity_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, report = freeze_fixture(tmp_path, tps_sample="JJP_TPS_MC_v4_1")
    monkeypatch.setattr(deploy.subprocess, "run", lambda *args, **kwargs: pytest.fail("dry run contacted a host"))
    payload, files = deploy.plan(root, report, execute=False, authorization_id=None, remote_root_value="/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root")
    assert set(payload["samples"]) == set(deploy.BASE_SAMPLES) | {"JJP_TPS_MC_v4_1"}
    assert "inputs/JJP_TPS_MC_v4_1/formal_manifest.json" in files


def test_rejects_both_tps_formal_identities(tmp_path: Path) -> None:
    root, report = freeze_fixture(tmp_path)
    payload = json.loads(report.read_text(encoding="utf-8"))
    legacy = json.loads(json.dumps(payload["samples"]["JJP_TPS"]))
    payload["samples"]["JJP_TPS_MC_v4_1"] = legacy
    report.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        deploy.plan(root, report, execute=False, authorization_id=None, remote_root_value="/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root")


def test_execute_requires_authorization_before_ssh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, report = freeze_fixture(tmp_path)
    monkeypatch.setattr(deploy.subprocess, "run", lambda *args, **kwargs: pytest.fail("unauthorized run contacted a host"))
    with pytest.raises(ValueError, match="authorization"):
        deploy.plan(root, report, execute=True, authorization_id=None, remote_root_value="/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root")


def test_execute_uses_only_ssh_rsync_and_validates_remote_readback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, report = freeze_fixture(tmp_path)
    payload, files = deploy.plan(root, report, execute=True, authorization_id="approved-42", remote_root_value="/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root")
    calls: list[list[str]] = []
    expected = {key: {"size": value.stat().st_size, "sha256": deploy.sha256(value)} for key, value in files.items()}
    remote = {"control_sha256": {key: row["sha256"] for key, row in expected.items()}, "queue_sha256": {sample: "a" * 64 for sample in deploy.SAMPLES}, "workflows": {sample: {"nodes": 2, "shards": 1, "workflow_sha256": "b" * 64} for sample in deploy.SAMPLES}, "hep_sub_process_calls": 0}
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if kwargs.get("capture_output"):
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(remote), stderr="")
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(deploy.subprocess, "run", fake_run)
    result = deploy.execute_deployment(payload, files)
    assert result["status"] == "complete"
    assert calls[0][:7] == ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o", "ControlMaster=no"]
    assert calls[1][0] == "rsync"
    assert calls[2][0] == "ssh"
    assert all(call[0] != "hep_sub" for call in calls)


def test_rejects_queue_manifest_not_declared_by_freeze(tmp_path: Path) -> None:
    root, report = freeze_fixture(tmp_path)
    queue = root / "queues" / "JJP_DPS1" / "manifests" / "queue.txt"
    queue.write_text("JJP_DPS1 0 /tmp/not-declared.json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="report-declared"):
        deploy.plan(root, report, execute=False, authorization_id=None, remote_root_value="/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root")


def test_large_inventory_is_sent_over_stdin_not_ssh_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, report = freeze_fixture(tmp_path)
    payload, files = deploy.plan(root, report, execute=True, authorization_id="approved-42", remote_root_value="/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root")
    temporary = deploy.tempfile.TemporaryDirectory(prefix="large-inventory-")
    inventory = {f"inputs/large/{index:04d}.json": {"size": index, "sha256": f"{index:064x}"} for index in range(1209)}
    calls: list[tuple[list[str], dict[str, object]]] = []
    payload["control_artifacts"] = inventory
    monkeypatch.setattr(deploy, "stage_inventory", lambda _: (temporary, inventory))
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        if kwargs.get("capture_output"):
            lines = str(kwargs["input"]).splitlines()
            assert len(json.loads(lines[0])) == 1209
            assert json.loads(lines[1]) == {sample: 1 for sample in deploy.SAMPLES}
            remote = {"control_sha256": {key: row["sha256"] for key, row in inventory.items()}, "queue_sha256": {sample: "a" * 64 for sample in deploy.SAMPLES}, "workflows": {sample: {"nodes": 2, "shards": 1, "workflow_sha256": "b" * 64} for sample in deploy.SAMPLES}, "hep_sub_process_calls": 0}
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(remote), stderr="")
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(deploy.subprocess, "run", fake_run)
    deploy.execute_deployment(payload, files)
    bootstrap, kwargs = calls[2]
    assert len(" ".join(bootstrap)) < 20_000
    assert "inputs/large" not in bootstrap[-1]
    assert "input" in kwargs
    assert [call[0][0] for call in calls] == ["ssh", "rsync", "ssh"]


def test_remote_root_must_be_safe_direct_child(tmp_path: Path) -> None:
    root, report = freeze_fixture(tmp_path)
    with pytest.raises(ValueError, match="remote-root"):
        deploy.plan(root, report, execute=False, authorization_id=None, remote_root_value="/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/a/b")


def test_toctou_staging_mismatch_fails_before_ssh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, report = freeze_fixture(tmp_path)
    payload, files = deploy.plan(root, report, execute=True, authorization_id="approved-42", remote_root_value="/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root")
    temporary = deploy.tempfile.TemporaryDirectory(prefix="mismatch-inventory-")
    changed = {key: {"size": value.stat().st_size, "sha256": deploy.sha256(value)} for key, value in files.items()}
    changed["source/runtime/runtime.tar.gz"]["sha256"] = "0" * 64
    calls: list[list[str]] = []
    monkeypatch.setattr(deploy, "stage_inventory", lambda _: (temporary, changed))
    monkeypatch.setattr(deploy.subprocess, "run", lambda command, **kwargs: calls.append(command))
    with pytest.raises(RuntimeError, match="staged control inventory"):
        deploy.execute_deployment(payload, files)
    assert calls == []


def test_existing_report_dir_is_rejected_before_any_action(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, report = freeze_fixture(tmp_path)
    report_dir = tmp_path / "already-exists"; report_dir.mkdir()
    monkeypatch.setattr(deploy.subprocess, "run", lambda *args, **kwargs: pytest.fail("existing report directory contacted a host"))
    monkeypatch.setattr(sys, "argv", ["deploy", "--freeze-root", str(root), "--freeze-report", str(report), "--report-dir", str(report_dir), "--remote-root", "/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root"])
    assert deploy.main() == 2
    assert list(report_dir.iterdir()) == []


def test_reserved_report_dir_records_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, report = freeze_fixture(tmp_path)
    report_dir = tmp_path / "failure-evidence"
    monkeypatch.setattr(deploy, "execute_deployment", lambda *_: (_ for _ in ()).throw(RuntimeError("simulated failure")))
    monkeypatch.setattr(sys, "argv", ["deploy", "--freeze-root", str(root), "--freeze-report", str(report), "--report-dir", str(report_dir), "--remote-root", "/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root", "--execute", "--authorization-id", "approved-42"])
    assert deploy.main() == 2
    assert json.loads((report_dir / "deployment-status.json").read_text())["status"] == "failed"
    assert "simulated failure" in (report_dir / "deployment.log").read_text()


def test_default_proxy_source_is_valid_and_inventoried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, report = freeze_fixture(tmp_path)
    proxy = tmp_path / "x509up"
    secret = b"mock CMS VOMS proxy secret"
    proxy.write_bytes(secret)
    monkeypatch.setenv("X509_USER_PROXY", str(proxy))
    payload, files = deploy.plan(root, report, execute=False, authorization_id=None, remote_root_value="/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root")
    assert files["credentials/x509_user_proxy"] == proxy
    row = payload["control_artifacts"]["credentials/x509_user_proxy"]
    assert row["size"] == len(secret)
    assert row["sha256"] == deploy.sha256(proxy)
    serialized = json.dumps(payload)
    assert secret.decode() not in serialized


def test_explicit_proxy_source_is_valid_and_inventoried(tmp_path: Path) -> None:
    root, report = freeze_fixture(tmp_path)
    proxy = tmp_path / "x509up"
    proxy.write_bytes(b"proxy")
    _, files = deploy.plan(root, report, execute=False, authorization_id=None, remote_root_value="/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root", proxy_source=proxy)
    assert files["credentials/x509_user_proxy"] == proxy


def test_missing_proxy_source_is_rejected(tmp_path: Path) -> None:
    root, report = freeze_fixture(tmp_path)
    with pytest.raises(ValueError, match="proxy-source"):
        deploy.plan(root, report, execute=False, authorization_id=None, remote_root_value="/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root", proxy_source=tmp_path / "missing-proxy")


def test_symlink_proxy_source_is_rejected(tmp_path: Path) -> None:
    root, report = freeze_fixture(tmp_path)
    real = tmp_path / "real-proxy"; real.write_bytes(b"proxy")
    link = tmp_path / "proxy-link"; link.symlink_to(real)
    with pytest.raises(ValueError, match="proxy-source"):
        deploy.plan(root, report, execute=False, authorization_id=None, remote_root_value="/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/test-root", proxy_source=link)


def test_stage_inventory_sets_proxy_permissions_to_600(tmp_path: Path) -> None:
    proxy = tmp_path / "x509up"
    proxy.write_bytes(b"mock proxy secret")
    runtime = tmp_path / "runtime.tar.gz"
    runtime.write_bytes(b"runtime")
    temporary, inventory = deploy.stage_inventory({"credentials/x509_user_proxy": proxy, "source/runtime/runtime.tar.gz": runtime})
    try:
        staged_proxy = Path(temporary.name) / "credentials" / "x509_user_proxy"
        assert staged_proxy.stat().st_mode & 0o777 == 0o600
        assert staged_proxy.stat().st_size == len(b"mock proxy secret")
        assert deploy.sha256(staged_proxy) == deploy.sha256(proxy)
        assert inventory["credentials/x509_user_proxy"]["sha256"] == deploy.sha256(proxy)
        assert Path(temporary.name) / "source" / "runtime" / "runtime.tar.gz"
    finally:
        temporary.cleanup()

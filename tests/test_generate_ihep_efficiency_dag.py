from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tarfile

import pytest


_SPEC = importlib.util.spec_from_file_location(
    "generate_ihep_efficiency_dag", Path("condor/generate_ihep_efficiency_dag.py")
)
assert _SPEC and _SPEC.loader
generator = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(generator)


@pytest.fixture(autouse=True)
def ihep_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep all local generator tests hermetic while exercising path policy."""
    root = tmp_path / "scratchfs2" / "cms" / "wangchi"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(generator, "IHEP_SCRATCH_ROOT", root)
    return root


def fixture_inputs(tmp_path: Path, ihep_root: Path, *, shards: int = 2) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    campaign_root = ihep_root / f"campaign_{tmp_path.name}"
    campaign_root.mkdir()
    rows: list[str] = []
    all_files: list[str] = []
    master_manifest_id = "master-id"
    for index in range(shards):
        url = f"root://cceos.ihep.ac.cn:1094///store/test/{index}.root"
        all_files.append(url)
        manifest = tmp_path / f"shard_{index:04d}.json"
        manifest.write_text(json.dumps({
            "sample": "JJP_DPS1", "shard_index": index, "n_shards": shards,
            "n_files": 1, "master_manifest_id": master_manifest_id, "files": [url],
        }), encoding="utf-8")
        rows.append(f"JJP_DPS1 {index} {manifest}\n")
    queue = tmp_path / "queue.txt"
    queue.write_text("".join(rows), encoding="utf-8")
    formal = tmp_path / "formal.json"
    formal.write_text(json.dumps({"sample": "JJP_DPS1", "n_files": len(all_files),
                                  "master_manifest_id": master_manifest_id, "files": all_files}), encoding="utf-8")
    tarball = tmp_path / "runtime.tar.gz"
    with tarfile.open(tarball, "w:gz") as archive:
        for relative in ("run_efficiency.py", "scripts/efficiency/merge_efficiency_shards.py",
                         "efficiency_workflow/formal_merge.py", "configs/efficiency/tps_nominal.yaml"):
            archive.add(Path(relative), arcname=relative)
    proxy = ihep_root / "x509up_cms_test"
    proxy.write_text("mock CMS VOMS proxy", encoding="utf-8")
    return {"queue": queue, "formal": formal, "tarball": tarball, "campaign_root": campaign_root,
            "proxy": proxy,
            "workspace": ihep_root / "hepjobs" / "NtupleAnalyzer" / "runs" / tmp_path.name / "JJP_DPS1"}


def valid_kwargs(inputs: dict[str, Path]) -> dict[str, object]:
    return {
        "sample": "JJP_DPS1", "queue_file": inputs["queue"], "formal_manifest": inputs["formal"],
        "ihep_campaign_root": inputs["campaign_root"], "runtime_tarball": str(inputs["tarball"]),
        "workspace_dir": inputs["workspace"], "tree_path": "auto",
        "efficiency_config": "configs/efficiency/tps_nominal.yaml", "config_policy": "strict",
        "efficiency_backend": "vectorized", "remote_access_mode": "direct", "skip_plots": True,
        "proxy_path": str(inputs["proxy"]),
    }


def test_generates_hepjob_workspace_with_merge_only_readiness(tmp_path: Path, ihep_root: Path) -> None:
    inputs = fixture_inputs(tmp_path, ihep_root)
    workflow_path = generator.build_workspace(**valid_kwargs(inputs), submission_retries=2)

    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    submit_shards = (inputs["workspace"] / "scripts/submit_shards.sh").read_text(encoding="utf-8")
    submit_merge = (inputs["workspace"] / "scripts/submit_merge.sh").read_text(encoding="utf-8")
    worker = (inputs["workspace"] / "scripts/run_ihep_efficiency_shard.sh").read_text(encoding="utf-8")
    merge_worker = (inputs["workspace"] / "scripts/run_ihep_efficiency_merge_only.sh").read_text(encoding="utf-8")
    assert workflow["site"] == "IHEP HepJob"
    assert workflow["nodes"][-1] == {"name": "MERGE", "parents": ["SHARD_0000", "SHARD_0001"], "merge_only": True}
    assert "hep_sub \"$RUN_SCRIPT\" -g cms -gwn CMS -wt mid -argu \"$idx\" -n 1" in submit_shards
    assert "attempt_${attempt}" in submit_shards
    assert "Missing shard readiness" in submit_merge
    assert "/shards/JJP_DPS1/${tag}/.ready" in submit_merge
    assert "hep_sub" in submit_merge
    assert (inputs["workspace"] / "scripts/plan_missing_shards.sh").is_file()
    assert workflow["hepjob"]["submission_retries"] == 2
    assert workflow["hepjob"]["execution_retry"] == "manual missing-only recovery only"
    assert "--remote-access-mode direct" in worker
    assert "--tree-path auto" in worker
    assert "--config-policy strict" in worker
    assert "--efficiency-backend vectorized" in worker
    assert "--skip-plots" in worker
    assert ".attempt_${ATTEMPT_ID}" in worker
    assert 'export X509_USER_PROXY="$PROXY_PATH"' in worker
    assert "unset X509_USER_PROXY" not in worker
    assert "--formal-manifest" in merge_worker
    assert "--formal-shards-dir" in merge_worker
    assert 'export X509_USER_PROXY="$PROXY_PATH"' in merge_worker
    assert "unset X509_USER_PROXY" not in merge_worker
    assert ": > \"$EXPECTED_BUNDLE/.ready\"" in merge_worker
    assert "! -f \"$FINAL_SAMPLE_DIR/.ready\"" in merge_worker
    assert "set -u" not in worker
    assert "set -u" not in merge_worker
    for content in (submit_shards, submit_merge, worker, merge_worker):
        assert "JobFlavour" not in content
        assert "/publicfs" not in content


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("tree_path", "X_data", "tree-path auto"),
        ("config_policy", "legacy", "config-policy strict"),
        ("efficiency_backend", "python-loop", "efficiency-backend vectorized"),
        ("remote_access_mode", "fallback", "remote-access-mode direct"),
        ("skip_plots", False, "skip-plots"),
        ("submission_retries", 6, "submission-retries"),
    ],
)
def test_contract_fails_closed(tmp_path: Path, ihep_root: Path, field: str, value: object, match: str) -> None:
    kwargs = valid_kwargs(fixture_inputs(tmp_path, ihep_root))
    kwargs[field] = value
    with pytest.raises(ValueError, match=match):
        generator.build_workspace(**kwargs)


def test_proxy_path_is_embedded_in_shard_and_merge_tasks(tmp_path: Path, ihep_root: Path) -> None:
    inputs = fixture_inputs(tmp_path, ihep_root)
    generator.build_workspace(**valid_kwargs(inputs), submission_retries=2)
    shard_tasks = json.loads((inputs["workspace"] / "tasks/JJP_DPS1/shard_tasks.json").read_text(encoding="utf-8"))
    merge_task = json.loads((inputs["workspace"] / "tasks/JJP_DPS1/merge_task.json").read_text(encoding="utf-8"))
    expected = str(inputs["proxy"].resolve())
    assert shard_tasks["tasks"]
    assert all(task["proxy_path"] == expected for task in shard_tasks["tasks"])
    assert merge_task["proxy_path"] == expected


def test_proxy_path_fails_closed(tmp_path: Path, ihep_root: Path) -> None:
    inputs = fixture_inputs(tmp_path, ihep_root)
    for proxy, match in (
        (None, "proxy-path"),
        ("/publicfs/cms/proxy", "prohibited|under"),
        (str(ihep_root / "x509up_missing"), "readable regular file"),
    ):
        kwargs = valid_kwargs(inputs)
        kwargs["proxy_path"] = proxy
        with pytest.raises(ValueError, match=match):
            generator.build_workspace(**kwargs)


def test_rejects_existing_roots_non_ihep_workspace_and_manifest_mismatch(tmp_path: Path, ihep_root: Path) -> None:
    inputs = fixture_inputs(tmp_path, ihep_root)
    (inputs["campaign_root"] / "JJP_DPS1").mkdir()
    with pytest.raises(FileExistsError, match="Refusing to reuse"):
        generator.build_workspace(**valid_kwargs(inputs))

    inputs = fixture_inputs(tmp_path / "outside", ihep_root)
    kwargs = valid_kwargs(inputs)
    kwargs["workspace_dir"] = tmp_path / "publicfs" / "unsafe"
    with pytest.raises(ValueError, match="/publicfs is prohibited"):
        generator.build_workspace(**kwargs)

    inputs = fixture_inputs(tmp_path / "mismatch", ihep_root)
    payload = json.loads((tmp_path / "mismatch" / "shard_0001.json").read_text(encoding="utf-8"))
    payload["n_shards"] = 3
    (tmp_path / "mismatch" / "shard_0001.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="disagree about n_shards"):
        generator.build_workspace(**valid_kwargs(inputs))


def test_rejects_non_triple_slash_cceos_url(tmp_path: Path, ihep_root: Path) -> None:
    inputs = fixture_inputs(tmp_path, ihep_root)
    payload = json.loads((tmp_path / "shard_0000.json").read_text(encoding="utf-8"))
    payload["files"] = ["root://cceos.ihep.ac.cn:1094//store/test.root"]
    (tmp_path / "shard_0000.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="triple-slash direct CCEOS"):
        generator.build_workspace(**valid_kwargs(inputs))


def test_queue_identity_count_and_index_contract(tmp_path: Path, ihep_root: Path) -> None:
    inputs = fixture_inputs(tmp_path, ihep_root)
    shard = tmp_path / "shard_0001.json"
    payload = json.loads(shard.read_text(encoding="utf-8"))
    payload["master_manifest_id"] = "different-master"
    shard.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="master_manifest_id mismatch"):
        generator.build_workspace(**valid_kwargs(inputs))

    inputs = fixture_inputs(tmp_path / "count", ihep_root)
    formal = json.loads(inputs["formal"].read_text(encoding="utf-8"))
    formal["files"].append("root://cceos.ihep.ac.cn:1094///store/test/extra.root")
    formal["n_files"] = 3
    inputs["formal"].write_text(json.dumps(formal), encoding="utf-8")
    with pytest.raises(ValueError, match="declare 2 files.*declares 3"):
        generator.build_workspace(**valid_kwargs(inputs))

    inputs = fixture_inputs(tmp_path / "indices", ihep_root)
    inputs["queue"].write_text(inputs["queue"].read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="complete 0\\.\\.1"):
        generator.build_workspace(**valid_kwargs(inputs))


def test_runtime_validation_records_only_archive_and_yaml_hashes(tmp_path: Path, ihep_root: Path) -> None:
    inputs = fixture_inputs(tmp_path, ihep_root)
    info = generator._validate_runtime(inputs["tarball"], "configs/efficiency/tps_nominal.yaml")
    assert set(info) == {"path", "sha256", "yaml_sha256", "size"}
    assert len(info["sha256"]) == 64
    assert len(info["yaml_sha256"]) == 64

    unsafe = tmp_path / "unsafe.tar.gz"
    with tarfile.open(unsafe, "w:gz") as archive:
        member = tarfile.TarInfo("../escape")
        member.size = 0
        archive.addfile(member)
    with pytest.raises(ValueError, match="unsafe|traversal"):
        generator._validate_runtime(unsafe, "configs/efficiency/tps_nominal.yaml")



def test_shard_worker_promotes_one_ready_attempt_with_private_cache(tmp_path: Path) -> None:
    """Two worker attempts leave one complete, non-nested promoted shard."""
    import sys

    root = tmp_path / "scratchfs2" / "cms" / "wangchi"
    campaign_root = root / "campaign"
    task_dir = tmp_path / "workspace" / "tasks" / "JJP_DPS1"
    campaign_root.mkdir(parents=True)
    task_dir.mkdir(parents=True)
    lcg = tmp_path / "lcg"
    lcg.mkdir()
    (lcg / "setup.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "python3").write_text(
        f'#!/bin/bash\nif [[ "$1" == "-c" ]]; then exit 0; fi\nexec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    (fake_bin / "python3").chmod(0o755)

    runtime = tmp_path / "runtime"
    (runtime / "configs" / "efficiency").mkdir(parents=True)
    (runtime / "configs" / "efficiency" / "mock.yaml").write_text("mock: true\n", encoding="utf-8")
    (runtime / "run_efficiency.py").write_text(
        "import json, os, sys, time\n"
        "from pathlib import Path\n"
        "def arg(name): return sys.argv[sys.argv.index(name) + 1]\n"
        "out, sample = Path(arg('--output-dir')), arg('--samples')\n"
        "time.sleep(0.2)\n"
        "(out / sample).mkdir(parents=True)\n"
        "(out / 'cache_paths.txt').write_text('\\n'.join([os.environ['MPLCONFIGDIR'], os.environ['PYTHONPYCACHEPREFIX'], os.environ['XDG_CACHE_HOME']]))\n"
        "(out / 'proxy.txt').write_text(os.environ.get('X509_USER_PROXY', ''))\n"
        "(out / sample / 'sample_manifest.json').write_text(json.dumps({'sample': sample, 'n_input_files': 1, 'coverage': {'n_processed_files': 1}}))\n",
        encoding="utf-8",
    )
    tarball = tmp_path / "runtime.tar.gz"
    with tarfile.open(tarball, "w:gz") as archive:
        archive.add(runtime / "run_efficiency.py", arcname="run_efficiency.py")
        archive.add(runtime / "configs", arcname="configs")

    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    proxy = root / "x509up_cms_test"
    proxy.write_text("mock proxy", encoding="utf-8")
    task = task_dir / "shard_tasks.json"
    task.write_text(json.dumps({"tasks": [{
        "index": 0, "sample": "JJP_DPS1", "manifest": str(manifest), "campaign_root": str(campaign_root),
        "runtime_tarball": str(tarball), "efficiency_config": "configs/efficiency/mock.yaml",
        "proxy_path": str(proxy),
    }]}), encoding="utf-8")
    worker = tmp_path / "worker.sh"
    worker.write_text(Path("condor/run_ihep_efficiency_shard.sh").read_text(encoding="utf-8").replace(
        "/scratchfs2/cms/wangchi", str(root)), encoding="utf-8")
    worker.chmod(0o755)
    job_tmp = tmp_path / "private_tmp"
    job_tmp.mkdir()
    # The worker runs the efficiency step through cmssw-el9 in production; the
    # test injects a pass-through wrapper so the same worker logic (runner
    # script, binds, --command-to-run) is exercised without a container.
    fake_cmssw = tmp_path / "fake_cmssw_el9"
    fake_cmssw.write_text(
        "#!/bin/bash\n"
        'for arg in "$@"; do\n'
        '  if [[ "$prev" == "--command-to-run" ]]; then exec bash -c "$arg"; fi\n'
        '  prev="$arg"\n'
        "done\n"
        "echo 'fake cmssw-el9: missing --command-to-run' >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    fake_cmssw.chmod(0o755)
    env = {**os.environ, "LCG_VIEW": str(lcg), "TMPDIR": str(job_tmp), "PATH": f"{fake_bin}:{os.environ['PATH']}",
           "X509_USER_PROXY": "/afs/cern.ch/user/test/proxy", "CMSSW_EL9": str(fake_cmssw)}
    attempts = [subprocess.Popen([str(worker), str(task), "0"], text=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, env=env) for _ in range(2)]
    results = [attempt.communicate() for attempt in attempts]
    assert sorted(attempt.returncode for attempt in attempts) == [0, 1], results

    promoted = campaign_root / "shards" / "JJP_DPS1" / "shard_0000"
    assert (promoted / ".ready").is_file()
    assert (promoted / "JJP_DPS1" / "sample_manifest.json").is_file()
    assert not (promoted / "shard_0000").exists()
    assert (promoted / "proxy.txt").read_text(encoding="utf-8") == str(proxy)
    assert all(path.startswith(str(job_tmp)) for path in (promoted / "cache_paths.txt").read_text(encoding="utf-8").splitlines())

#!/usr/bin/env python3
"""Bounded local tests for the IHEP-to-CERN-EOS staging helper."""

from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ihep_eos_staging", SCRIPTS / "ihep_eos_staging.py")
assert SPEC and SPEC.loader
staging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(staging)
SHA = "a" * 64


def formal_payload(files: list[str]) -> dict[str, object]:
    inventory = [{"source_file": item, "total_entries": 10 + index} for index, item in enumerate(files)]
    return {
        "schema_version": "ntuple-analyzer-tps-manifest/v1", "sample": "JJP_DPS1", "files": files,
        "n_files": len(files), "master_n_files": len(files), "manifest_id": "b" * 64,
        "master_manifest_id": "b" * 64, "inventory": inventory,
        "inventory_columns": ["source_file", "total_entries"], "inventory_totals": {"total_entries": 21},
    }


def plan_args(path: Path) -> argparse.Namespace:
    return argparse.Namespace(formal_manifest=path, campaign_id="campaign-01",
                              campaign_identity_sha256=SHA, eos_root=staging.EOS_DEFAULT_ROOT,
                              eos_endpoint=staging.EOS_DEFAULT_ENDPOINT)


def launch_args(plan: Path) -> argparse.Namespace:
    return argparse.Namespace(plan=plan, remote_work_root="/home/wangchi/staging-work",
                              local_script=SCRIPTS / "ihep_eos_staging.py", remote_script_name="worker.py",
                              ssh_host=staging.IHEP_DEFAULT_HOST, ssh_user=staging.IHEP_DEFAULT_USER,
                              ssh_port=None, ssh_config="/dev/null", execute=False, authorization_id=None)


class IhepEosStagingTests(unittest.TestCase):
    def make_plan(self, temporary: str) -> tuple[Path, dict[str, object]]:
        source = Path(temporary) / "good.manifest.json"
        source.write_text(json.dumps(formal_payload([
            "root://cceos.ihep.ac.cn//store/user/a/JOB000/output_ntuple.root"
        ])), encoding="utf-8")
        return source, staging.build_plan(plan_args(source))

    def test_plan_preserves_formal_identity_and_builds_compatible_staged_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "JJP_DPS1.manifest.json"
            sources = [
                "root://cceos.ihep.ac.cn:1094///store/user/a/JOB000/output_ntuple.root",
                "root://cceos.ihep.ac.cn:1094///store/user/a/JOB001/output_ntuple.root",
            ]
            source.write_text(json.dumps(formal_payload(sources)), encoding="utf-8")
            plan = staging.build_plan(plan_args(source))
            staging.validate_plan(plan)
            self.assertEqual(plan["formal_manifest"]["manifest_id"], "b" * 64)
            self.assertEqual(plan["staged_manifest"]["master_manifest_id"], "b" * 64)
            self.assertEqual(plan["staged_manifest"]["files"], [row["staged_url"] for row in plan["mappings"]])
            self.assertEqual(len(set(plan["staged_manifest"]["files"])), 2)
            self.assertTrue(all("/staged_inputs/JJP_DPS1/files/" in item for item in plan["staged_manifest"]["files"]))
            self.assertEqual(plan["staged_manifest"]["inventory"][0]["original_source_file"], sources[0])

    def test_plan_rejects_non_cceos_input_before_any_remote_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "bad.manifest.json"
            payload = formal_payload(["root://eosuser.cern.ch//eos/user/a/output_ntuple.root"])
            source.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not a CCEOS"):
                staging.build_plan(plan_args(source))

    def test_launch_plan_is_detached_dry_run_with_system_ssh_config_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, plan = self.make_plan(temporary)
            with patch.object(staging.subprocess, "run", side_effect=AssertionError("network call")):
                summary = staging.plan_summary(plan, launch_args(source))
            self.assertTrue(summary["dry_run"])
            self.assertTrue(summary["detached"])
            self.assertTrue(summary["endpoint"]["system_config_disabled"])
            self.assertIn("nohup", "cd " + summary["workspace"] + " && nohup")
            self.assertIn("--execute", summary["worker_command_template"])
            self.assertEqual(Path(summary["remote_script"]).name, "worker.py")
            self.assertEqual(summary["local_script_sha256"], staging.file_sha256(SCRIPTS / "ihep_eos_staging.py"))

    def test_live_launch_requires_authorization_before_ssh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, plan = self.make_plan(temporary)
            plan_path = Path(temporary) / "plan.json"
            staging.atomic_new_json(plan_path, plan)
            with self.assertRaisesRegex(ValueError, "authorization"):
                staging.launch(plan_path, plan, launch_args(plan_path))

    def test_live_launch_create_only_uploads_plan_and_helper_then_verifies_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, plan = self.make_plan(temporary)
            plan_path = Path(temporary) / "plan.json"
            staging.atomic_new_json(plan_path, plan)
            args = launch_args(plan_path)
            args.execute = True
            args.authorization_id = "stage-approval-01"
            responses = [
                staging.subprocess.CompletedProcess([], 0),
                staging.subprocess.CompletedProcess([], 0),
                staging.subprocess.CompletedProcess([], 0),
                staging.subprocess.CompletedProcess([], 0),
                staging.subprocess.CompletedProcess([], 0),
                staging.subprocess.CompletedProcess([], 0),
                staging.subprocess.CompletedProcess([], 0, stdout="517\n", stderr=""),
            ]
            with patch.object(staging.subprocess, "run", side_effect=responses) as run:
                result = staging.launch(plan_path, plan, args)
            self.assertEqual(result["pid"], 517)
            self.assertEqual(result["remote_plan_sha256"], staging.file_sha256(plan_path))
            self.assertEqual(run.call_count, 7)
            calls = run.call_args_list
            self.assertIn("mkdir -p -- /home/wangchi/staging-work/campaign-01/JJP_DPS1", calls[0].args[0][-1])
            self.assertIn("mkdir -- /home/wangchi/staging-work/campaign-01/JJP_DPS1/", calls[1].args[0][-1])
            self.assertEqual(calls[2].kwargs["input"], plan_path.read_bytes())
            self.assertEqual(calls[3].kwargs["input"], (SCRIPTS / "ihep_eos_staging.py").read_bytes())
            self.assertIn(result["remote_plan"], calls[2].args[0][-1])
            self.assertIn(result["remote_script"], calls[3].args[0][-1])
            self.assertIn(result["local_script_sha256"], calls[5].args[0][-1])
            self.assertIn(result["remote_script"], calls[6].args[0][-1])

    def test_existing_object_is_never_overwritten_without_exact_size_checksum_match(self) -> None:
        source = {"size": 100, "adler32": "1a2b3c4d"}
        self.assertEqual(staging.compare_existing(source, None), "copy")
        self.assertEqual(staging.compare_existing(source, {"size": 99, "adler32": "1a2b3c4d"}), "mismatch")
        self.assertEqual(staging.compare_existing(source, {"size": 100, "adler32": "00000000"}), "mismatch")
        self.assertEqual(staging.compare_existing(source, dict(source)), "verified-existing")

    def test_completed_staged_manifest_can_only_be_reused_with_identical_plan_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, plan = self.make_plan(temporary)
            self.assertTrue(staging.existing_manifest_matches(dict(plan["staged_manifest"]), plan))
            incompatible = dict(plan["staged_manifest"])
            incompatible["staging_plan_sha256"] = "0" * 64
            self.assertFalse(staging.existing_manifest_matches(incompatible, plan))

    def test_staged_manifest_readback_is_explicit_and_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, plan = self.make_plan(temporary)
            output = Path(temporary) / "staged.manifest.json"
            preview = staging.fetch_staged_manifest(plan, output, fetch=False, authorization_id=None)
            self.assertTrue(preview["dry_run"])
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError, "authorization"):
                staging.fetch_staged_manifest(plan, output, fetch=True, authorization_id=None)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

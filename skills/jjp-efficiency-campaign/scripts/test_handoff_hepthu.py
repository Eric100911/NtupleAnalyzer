#!/usr/bin/env python3
"""Local-only regression tests for the campaign site-boundary helpers."""

from __future__ import annotations

import argparse
import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


handoff = load_module("handoff")
hepthu_analysis = load_module("hepthu_analysis")
SHA = "a" * 64


def inventory_args(root: Path, include: list[str]) -> argparse.Namespace:
    return argparse.Namespace(
        source_root=root, include=include, allow_small_root=False,
        campaign_id="campaign-01", campaign_identity_sha256=SHA, repo_sha="b" * 64,
        efficiency_config_sha256="c" * 64, lcg_view="/cvmfs/example/setup.sh",
        sample_manifest=["JJP_DPS1=" + "d" * 64],
    )


class HandoffTests(unittest.TestCase):
    def test_inventory_plan_and_exact_readback_are_local_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            root.mkdir()
            (root / "merged.parquet").write_bytes(b"compact parquet fixture")
            (root / "coverage.json").write_text('{"coverage": true}\n', encoding="utf-8")
            manifest = handoff.build_manifest(inventory_args(root, ["coverage.json", "merged.parquet"]))
            handoff.validate_manifest(manifest)
            manifest_path = root / "handoff-manifest.json"
            handoff.atomic_new_json(manifest_path, manifest)
            self.assertEqual(hepthu_analysis.load_handoff(manifest_path)["inventory_sha256"], manifest["inventory_sha256"])
            plan_args = argparse.Namespace(source_root=root, handoff_manifest=manifest_path,
                                           ssh_host="hepthu-el9", destination_root="campaign-01/JJP_DPS1",
                                           ssh_config=Path("/dev/null"), ssh_port=48571, ssh_user="chiwang",
                                           execute_transfer=False, authorization_id=None)
            plan = handoff.transfer_plan(manifest, plan_args)
            self.assertTrue(plan["dry_run"])
            self.assertTrue(plan["no_overwrite"])
            self.assertEqual(plan["files"], ["coverage.json", "merged.parquet"])
            self.assertEqual(plan["endpoint"], {
                "host": "hepthu-el9", "user": "chiwang", "port": 48571,
                "ssh_config": "/dev/null", "ssh_config_sha256": handoff.hashlib.sha256(b"").hexdigest(),
                "system_config_disabled": True,
            })
            self.assertIn("-F /dev/null -p 48571 -l chiwang hepthu-el9", plan["ssh_command"])
            self.assertTrue(handoff.verify_tree(root, manifest, require_exact=True)["exact_agreement"])
            (root / "unexpected.txt").write_text("not inventoried", encoding="utf-8")
            self.assertFalse(handoff.verify_tree(root, manifest, require_exact=True)["exact_agreement"])

    def test_transfer_execution_requires_authorization_before_ssh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "merged.parquet").write_bytes(b"x")
            manifest = handoff.build_manifest(inventory_args(root, ["merged.parquet"]))
            args = argparse.Namespace(source_root=root, ssh_host="hepthu-el9", ssh_config=None, ssh_port=None,
                                      ssh_user=None, destination_root="campaign-01",
                                      authorization_id=None)
            with self.assertRaisesRegex(ValueError, "authorization"):
                handoff.execute_transfer(manifest, root / "handoff-manifest.json", args)

    def test_shell_sensitive_remote_values_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            handoff.ssh_settings(argparse.Namespace(ssh_host="host;touch-bad", ssh_config=None, ssh_port=None, ssh_user=None))
        with self.assertRaises(ValueError):
            handoff.safe_destination("campaign;touch-bad")


class HepthuPlanTests(unittest.TestCase):
    def test_launch_plan_does_not_create_or_start_anything(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fresh"
            args = argparse.Namespace(
                campaign_id="campaign-01", campaign_identity_sha256=SHA, sample="JJP_DPS1",
                input_root=Path(temporary) / "handoff", expected_repo_sha="b" * 64,
                efficiency_config_sha256="c" * 64, output_root=output,
                lcg_view=Path("/cvmfs/example/setup.sh"), command=["python3 -m efficiency_workflow.build_factorized_maps"],
                launch=False, authorization_id=None,
            )
            plan = hepthu_analysis.launch_plan(args)
            self.assertTrue(plan["dry_run"])
            self.assertTrue(plan["no_ssh"])
            self.assertFalse(output.exists())
            self.assertIn("command_sha256", plan)

    def test_live_launch_requires_authorization_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fresh"
            args = argparse.Namespace(
                campaign_id="campaign-01", campaign_identity_sha256=SHA, sample="JJP_DPS1",
                input_root=Path(temporary) / "handoff", expected_repo_sha="b" * 64,
                efficiency_config_sha256="c" * 64, output_root=output,
                lcg_view=Path("/cvmfs/example/setup.sh"), command=["true"], launch=True,
                authorization_id=None,
            )
            with self.assertRaisesRegex(ValueError, "authorization"):
                hepthu_analysis.launch(args)
            self.assertFalse(output.exists())

    def test_status_sentinel_has_stable_success_and_failure_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            args = argparse.Namespace(campaign_id="campaign-01", campaign_identity_sha256=SHA,
                                      sample="JJP_DPS1", expected_repo_sha="b" * 64,
                                      efficiency_config_sha256="c" * 64, output_root=Path(temporary) / "fresh",
                                      input_root=Path(temporary) / "handoff", lcg_view=Path("/cvmfs/example/setup.sh"),
                                      command=["true"], launch=False, authorization_id=None)
            material = hepthu_analysis.launch_material(args)
            started = hepthu_analysis.status_payload("started", args, material, "2026-01-01T00:00:00+00:00")
            running = hepthu_analysis.status_payload("running", args, material, "2026-01-01T00:00:00+00:00", pid=17)
            success = hepthu_analysis.status_payload("finished", args, material, "2026-01-01T00:00:00+00:00", pid=17, exit_code=0)
            failure = hepthu_analysis.status_payload("finished", args, material, "2026-01-01T00:00:00+00:00", pid=17, exit_code=2)
            required = {"schema_version", "state", "campaign_id", "campaign_identity_sha256", "sample",
                        "command_sha256", "started_at", "pid", "exit_code"}
            self.assertEqual(set(started), required)
            self.assertEqual(set(running), required)
            self.assertEqual(set(success), required)
            self.assertEqual(set(failure), required)
            self.assertEqual(success["schema_version"], "jjp-efficiency-hepthu-status/v1")
            self.assertIsNone(started["pid"])
            self.assertEqual(running["pid"], 17)
            self.assertEqual(success["exit_code"], 0)
            self.assertEqual(failure["exit_code"], 2)


if __name__ == "__main__":
    unittest.main()

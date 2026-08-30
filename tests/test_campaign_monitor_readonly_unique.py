"""Focused tests for the JJP detached read-only monitor."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "skills/jjp-efficiency-campaign/scripts/campaign_monitor.py"
SPEC = importlib.util.spec_from_file_location("campaign_monitor_under_test", SCRIPT)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


def target_file(directory: Path, *, revision: int = 0) -> Path:
    path = directory / "targets.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": monitor.TARGET_SCHEMA,
                "campaign_id": "20260830_jjp",
                "campaign_identity_sha256": "a" * 64,
                "revision": revision,
                "condor": [{"sample": "JJP_DPS1", "schedd": "schedd.example", "dag_id": "12345"}],
            }
        ),
        encoding="utf-8",
    )
    return path


class MonitorReadOnlyTests(unittest.TestCase):
    def test_validate_and_dry_run_do_not_create_monitor_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            targets = target_file(directory)
            monitor_dir = directory / "monitor"
            self.assertEqual(monitor.main(["validate", "--targets", str(targets), "--monitor-dir", str(monitor_dir)]), 0)
            self.assertFalse(monitor_dir.exists())
            self.assertEqual(monitor.main(["snapshot", "--targets", str(targets), "--monitor-dir", str(monitor_dir)]), 0)
            self.assertFalse(monitor_dir.exists())

    def test_condor_query_is_bound_to_exact_schedd_and_dag(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            output = json.dumps(
                [
                    {
                        "ClusterId": 12345,
                        "ProcId": 0,
                        "JobStatus": 2,
                        "JobUniverse": 7,
                        "JobBatchId": "12345.0",
                    },
                    {
                        "ClusterId": 12346,
                        "ProcId": 0,
                        "JobStatus": 5,
                        "JobUniverse": 5,
                        "DAGManJobId": 12345,
                        "DAGNodeName": "SHARD_0000",
                        "JobBatchId": "12345.0",
                        "HoldReason": "mock hold",
                    },
                ]
            ) if argv[0] == "condor_q" else "[]"
            return subprocess.CompletedProcess(argv, 0, output, "")

        result = monitor.condor_probe({"sample": "JJP_DPS1", "schedd": "schedd.example", "dag_id": "12345"}, runner=runner)
        self.assertEqual(result["observed_state"], "held")
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(call[1:3], ["-name", "schedd.example"])
            constraint = call[call.index("-constraint") + 1]
            self.assertIn("ClusterId == 12345 && ProcId == 0", constraint)
            self.assertIn('JobBatchId == "12345.0"', constraint)
            self.assertIn("DAGManJobId == 12345", constraint)
            self.assertNotIn("condor_rm", " ".join(call))
        self.assertEqual(result["root_controller_id"], "12345.0")
        self.assertEqual(result["controllers"]["live"]["total"], 1)
        self.assertEqual(result["live_payload"]["counts"], {"held": 1})
        self.assertEqual(result["logical_dag"]["counts"], {"held": 1})

    def test_empty_condor_queue_and_history_are_unknown(self) -> None:
        def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, "[]", "")

        result = monitor.condor_probe(
            {"sample": "JJP_DPS1", "schedd": "schedd.example", "dag_id": "12345"},
            runner=runner,
        )
        self.assertTrue(result["query_complete"])
        self.assertEqual(result["observed_state"], "unknown")

    def test_root_history_success_is_completion_evidence(self) -> None:
        def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if argv[0] == "condor_q":
                output = "[]"
            else:
                output = json.dumps(
                    [
                        {
                            "ClusterId": 12345,
                            "ProcId": 0,
                            "JobStatus": 4,
                            "JobUniverse": 7,
                            "ExitCode": 0,
                            "CompletionDate": 30,
                        },
                        {
                            "ClusterId": 12346,
                            "ProcId": 0,
                            "JobStatus": 4,
                            "DAGNodeName": "SHARD_0000",
                            "ExitCode": 1,
                            "CompletionDate": 10,
                        },
                        {
                            "ClusterId": 12347,
                            "ProcId": 0,
                            "JobStatus": 4,
                            "DAGNodeName": "SHARD_0000",
                            "ExitCode": 0,
                            "CompletionDate": 20,
                        },
                    ]
                )
            return subprocess.CompletedProcess(argv, 0, output, "")

        result = monitor.condor_probe(
            {"sample": "JJP_DPS1", "schedd": "schedd.example", "dag_id": "12345"},
            runner=runner,
        )
        self.assertEqual(result["observed_state"], "complete")
        self.assertEqual(result["controllers"]["root_history_state"], "success")
        self.assertEqual(result["logical_dag"]["counts"], {"success": 1})
        self.assertEqual(
            result["history_summary"]["payload"]["counts"],
            {"failed": 1, "success": 1},
        )

    def test_failed_query_cannot_be_completion(self) -> None:
        def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if argv[0] == "condor_q":
                return subprocess.CompletedProcess(argv, 1, "", "schedd unavailable")
            return subprocess.CompletedProcess(
                argv,
                0,
                json.dumps(
                    [{"ClusterId": 12345, "ProcId": 0, "JobStatus": 4, "ExitCode": 0}]
                ),
                "",
            )

        result = monitor.condor_probe(
            {"sample": "JJP_DPS1", "schedd": "schedd.example", "dag_id": "12345"},
            runner=runner,
        )
        self.assertFalse(result["query_complete"])
        self.assertEqual(result["observed_state"], "unknown")

    def test_recorded_dag_plan_distinguishes_pending_logical_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            dag = Path(raw) / "sample.dag"
            dag.write_text(
                "JOB SHARD_0000 shard.sub\nJOB SHARD_0001 shard.sub\n"
                "JOB POST post.sub\nPARENT SHARD_0000 SHARD_0001 CHILD POST\n",
                encoding="utf-8",
            )

            def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if argv[0] == "condor_q":
                    output = json.dumps(
                        [
                            {"ClusterId": 12345, "ProcId": 0, "JobStatus": 2, "JobUniverse": 7},
                            {"ClusterId": 12346, "ProcId": 0, "JobStatus": 2, "DAGNodeName": "SHARD_0000"},
                        ]
                    )
                else:
                    output = "[]"
                return subprocess.CompletedProcess(argv, 0, output, "")

            result = monitor.condor_probe(
                {
                    "sample": "JJP_DPS1",
                    "schedd": "schedd.example",
                    "dag_id": "12345",
                    "dag_path": str(dag),
                },
                runner=runner,
            )
        self.assertEqual(result["observed_state"], "active")
        self.assertEqual(result["logical_dag"]["planned_total"], 3)
        self.assertEqual(
            result["logical_dag"]["counts"], {"pending": 2, "running": 1}
        )

    def test_snapshot_persists_atomic_files_and_alerts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            targets = monitor._normalise_targets(
                json.loads(target_file(directory).read_text(encoding="utf-8"))
            )
            monitor_dir = directory / "monitor"
            monitor.capture_snapshot(targets, monitor_dir, probe=False, write=True)
            self.assertEqual(json.loads((monitor_dir / "latest.json").read_text())["schema_version"], monitor.SNAPSHOT_SCHEMA)
            self.assertTrue(list((monitor_dir / "snapshots").glob("*.json")))
            self.assertTrue((monitor_dir / "heartbeat.json").is_file())
            self.assertTrue((monitor_dir / "alerts.jsonl").is_file())
            self.assertEqual(json.loads((monitor_dir / "heartbeat.json").read_text())["schema_version"], monitor.HEARTBEAT_SCHEMA)

    def test_invalid_dag_identity_is_rejected(self) -> None:
        with self.assertRaises(monitor.MonitorError):
            monitor._normalise_targets(
                {
                    "campaign_id": "c",
                    "campaign_identity_sha256": "a" * 64,
                    "revision": 0,
                    "condor": [{"sample": "JJP_DPS1", "schedd": "s", "dag_id": "all; condor_rm"}],
                }
            )

    def test_hepthu_endpoint_and_finished_sentinel_are_bound(self) -> None:
        calls: list[list[str]] = []
        command_hash = "b" * 64
        target = monitor._normalise_targets(
            {
                "campaign_id": "20260830_jjp",
                "campaign_identity_sha256": "a" * 64,
                "revision": 2,
                "condor": [],
                "hepthu": {
                    "host": "166.111.26.39",
                    "user": "chiwang",
                    "port": 48571,
                    "ssh_config": "/dev/null",
                    "pid": 8123,
                    "status_path": "/tmp/status.json",
                    "log_path": "/tmp/analysis.log",
                    "command_sha256": command_hash,
                },
            }
        )["hepthu"]

        def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            output = (
                "PID_ALIVE=0\nSTATUS_BEGIN\n"
                + json.dumps({"campaign_id": "20260830_jjp", "command_sha256": command_hash, "state": "finished", "exit_code": 0})
                + "\nSTATUS_END\nLOG_SIZE=10 LOG_MTIME=1\n"
            )
            return subprocess.CompletedProcess(argv, 0, output, "")

        result = monitor.hepthu_probe(target, runner=runner, campaign_id="20260830_jjp")
        self.assertEqual(result["observed_state"], "complete")
        self.assertTrue(result["identity_ok"])
        self.assertEqual(calls[0][0:10], ["ssh", "-F", "/dev/null", "-p", "48571", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o"])
        self.assertIn("chiwang@166.111.26.39", calls[0])

    def test_hepthu_nonzero_finished_sentinel_is_failed(self) -> None:
        command_hash = "c" * 64
        target = {
            "host": "hepthu-el9", "pid": 1, "status_path": "/tmp/s", "log_path": "/tmp/l", "command_sha256": command_hash
        }

        def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            output = "PID_ALIVE=0\nSTATUS_BEGIN\n" + json.dumps({"command_sha256": command_hash, "state": "finished", "exit_code": 9}) + "\nSTATUS_END\n"
            return subprocess.CompletedProcess(argv, 0, output, "")

        self.assertEqual(monitor.hepthu_probe(target, runner=runner)["observed_state"], "failed")


if __name__ == "__main__":
    unittest.main()

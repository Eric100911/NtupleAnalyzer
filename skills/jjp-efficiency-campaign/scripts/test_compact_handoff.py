#!/usr/bin/env python3
"""Minimal regression tests for the tar.gz compact handoff."""
from __future__ import annotations
import importlib.util, json, tempfile, unittest
from pathlib import Path
SCRIPT = Path(__file__).with_name("compact_handoff.py")
spec = importlib.util.spec_from_file_location("compact_handoff", SCRIPT)
assert spec and spec.loader
compact = importlib.util.module_from_spec(spec); spec.loader.exec_module(compact)
SHA = "a" * 64
REPO = "b" * 40

def fixture(root: Path, *, passed=True, sample="JJP_DPS1") -> None:
    required = compact.REQUIRED_MEMBERS
    (root / "formal_merge_report.json").write_text(json.dumps({"sample": sample, "passed": passed, "coverage": {"complete": True}}), encoding="utf-8")
    (root / "sample_manifest.json").write_text(json.dumps({"sample": sample}), encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps({"sample": sample, "stage": "efficiency"}), encoding="utf-8")
    (root / "configuration_metadata.json").write_text("{}", encoding="utf-8")
    for name in required - {"formal_merge_report.json", "sample_manifest.json", "manifest.json", "configuration_metadata.json"}:
        (root / name).write_bytes(name.encode())

def build(root: Path, destination: Path, *, sample="JJP_DPS1", **kwargs):
    return compact.build_bundle(root, destination, sample=sample, campaign_id="campaign-01", repo_sha=REPO, formal_manifest_id="formal-01", yaml_sha256=SHA, runtime_tarball_sha256=SHA, **kwargs)

class CompactHandoffTests(unittest.TestCase):
    def test_build_verify_extract_and_create_only(self):
        with tempfile.TemporaryDirectory() as d:
            parent, source = Path(d), Path(d) / "source"; source.mkdir(); fixture(source)
            bundle = parent / "JJP_DPS1.tar.gz"; manifest = build(source, bundle)
            self.assertEqual({row["path"] for row in manifest["members"]}, compact.REQUIRED_MEMBERS)
            self.assertTrue(all(set(row) == {"path", "size"} for row in manifest["members"]))
            self.assertTrue(compact.verify_bundle(bundle, manifest)["verified"])
            destination = parent / "extract"; result = compact.extract_bundle(bundle, destination, manifest)
            self.assertTrue(result["verified"]); self.assertTrue((destination / compact.MANIFEST_NAME).is_file())
            with self.assertRaises(FileExistsError): compact.extract_bundle(bundle, destination, manifest)

    def test_tps_canonical_and_legacy_formal_identities_round_trip(self):
        for sample in ("JJP_TPS", "JJP_TPS_MC_v4_1"):
            with self.subTest(sample=sample), tempfile.TemporaryDirectory() as d:
                parent, source = Path(d), Path(d) / "source"; source.mkdir(); fixture(source, sample=sample)
                manifest = build(source, parent / f"{sample}.tar.gz", sample=sample)
                self.assertEqual(manifest["sample"], sample)
                self.assertTrue(compact.verify_bundle(parent / f"{sample}.tar.gz", manifest)["verified"])

    def test_failed_merge_and_unsafe_members_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d); fixture(source, passed=False)
            with self.assertRaises(ValueError): build(source, Path(d) / "bundle.tar.gz")
            fixture(source)
            with self.assertRaises(ValueError): build(source, Path(d) / "bundle.tar.gz", include=["../manifest.json"])
            with self.assertRaises(ValueError): build(source, Path(d) / "bundle2.tar.gz", include=["x.root"])

    def test_whole_bundle_digest_detects_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            parent, source = Path(d), Path(d) / "source"; source.mkdir(); fixture(source)
            bundle = parent / "bundle.tar.gz"; manifest = build(source, bundle)
            bundle.write_bytes(bundle.read_bytes() + b"tampered")
            self.assertFalse(compact.verify_bundle(bundle, manifest)["verified"])

if __name__ == "__main__": unittest.main()

#!/usr/bin/env python3
"""Create a complete-branch, bounded v2.1 ROOT test fixture from MC Production v3."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import uproot


DEFAULT_SOURCE = (
    "root://cceos.ihep.ac.cn///eos/ihep/cms/store/user/xcheng/"
    "MC_Production_v3/output/JJP_DPS2_CS/0/output_ntuple.root"
)
REQUIRED_BRANCHES = {
    "Jpsi_1_y", "Jpsi_2_y", "SingleJpsi_y", "SinglePhi_y",
    "RecoKaonTrack_genMatchIdx", "RecoKaonTrack_normalizedChi2",
    "RecoKaonTrack_numberOfHits", "RecoKaonTrack_isHighPurity",
    "muGenMatchIdx", "muJpsiMatchedTriggerIndices",
    "muJpsiMatchedFilterIndices", "Pri_assocPVPass",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=Path("test_data/jjp_dps2_cs_v21_first200.root"))
    parser.add_argument("--entries", type=int, default=200)
    args = parser.parse_args()

    with uproot.open(args.source, timeout=60) as source:
        data = source["mkcands/X_data"]
        config = source["mkcands/X_config"]
        run_info = source["mkcands/X_lhe_run_info"]
        missing = sorted(REQUIRED_BRANCHES - set(data.keys()))
        if missing:
            raise RuntimeError(f"Source does not satisfy the v2.1 fixture contract: {', '.join(missing)}")
        if args.entries <= 0 or args.entries > data.num_entries:
            raise ValueError(f"--entries must be in [1, {data.num_entries}]")
        source_entries = int(data.num_entries)
        source_branch_count = len(data.keys())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Uproot cannot write every ROOT type in this production ntuple (notably
    # jagged string branches). CloneTree preserves the complete branch schema.
    import ROOT

    source_root = ROOT.TFile.Open(args.source)
    if not source_root or source_root.IsZombie():
        raise RuntimeError(f"Cannot open source ROOT file: {args.source}")
    output_root = ROOT.TFile.Open(str(args.output), "RECREATE")
    output_dir = output_root.mkdir("mkcands")
    for name, n_entries in (("X_data", args.entries), ("X_config", -1), ("X_lhe_run_info", -1)):
        source_tree = source_root.Get(f"mkcands/{name}")
        if source_tree is None:
            raise RuntimeError(f"Missing required source tree: mkcands/{name}")
        output_dir.cd()
        clone = source_tree.CloneTree(n_entries, "fast")
        clone.SetName(name)
        clone.Write()
    output_root.Close()
    source_root.Close()

    with uproot.open(args.output) as fixture:
        fixture_data = fixture["mkcands/X_data"]
        if fixture_data.num_entries != args.entries or len(fixture_data.keys()) != source_branch_count:
            raise RuntimeError("Fixture tree does not preserve the requested entry count and complete branch set")
    manifest = {
        "source": args.source,
        "source_x_data_entries": source_entries,
        "entry_start": 0,
        "entry_stop": args.entries,
        "x_data_branch_count": source_branch_count,
        "trees": ["mkcands/X_data", "mkcands/X_config", "mkcands/X_lhe_run_info"],
        "sha256": _sha256(args.output),
    }
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply MC genMatch requirements to an already merged selected ntuple."""

from __future__ import annotations

import argparse
import os
import sys

import ROOT

from merge_apply_cuts import OUTPUT_TREE, build_genmatch_expr
from ntuple_pipeline_common import (
    build_root_string_vector,
    declare_rdf_helpers,
    default_merged_output,
    ensure_parent_dir,
    get_tree_branches,
    normalize_channel,
    normalize_sample,
)


REQUIRED_GENMATCH_BRANCHES = (
    "bestCandIdx",
    "muGenMatchIdx",
    "muGenMatchSource",
    "Phi_K_1_genMatchIdx",
    "Phi_K_1_genMatchSource",
    "Phi_K_2_genMatchIdx",
    "Phi_K_2_genMatchSource",
    "MC_GenPart_motherGenIdx",
    "MC_GenPart_motherPdgId",
)


def parse_args():
    parser = argparse.ArgumentParser(description="Apply genMatch requirements to an already merged MC selected ntuple")
    parser.add_argument("--channel", required=True, choices=["JJP", "JYP", "jjp", "jyp"], help="Physics channel")
    parser.add_argument("--sample", default=None, help="MC sample tag, required when --input is not specified")
    parser.add_argument("-i", "--input", default=None, help="Input merged selected ROOT file")
    parser.add_argument("-o", "--output", default=None, help="Output ROOT file after genMatch filtering")
    parser.add_argument("-j", "--jobs", type=int, default=8, help="RDataFrame thread count")
    parser.add_argument("-n", "--max-events", type=int, default=-1, help="Limit events for quick tests")
    return parser.parse_args()


def default_output_path(input_file: str) -> str:
    if input_file.endswith("_selected.root"):
        return input_file[:-len("_selected.root")] + "_genmatch_selected.root"
    if input_file.endswith(".root"):
        return input_file[:-5] + "_genmatch.root"
    return input_file + "_genmatch.root"


def required_index_branches(channel: str) -> tuple[str, ...]:
    if channel == "JJP":
        return (
            "Jpsi_1_mu_1_Idx",
            "Jpsi_1_mu_2_Idx",
            "Jpsi_2_mu_1_Idx",
            "Jpsi_2_mu_2_Idx",
        )
    return (
        "Jpsi_1_mu_1_Idx",
        "Jpsi_1_mu_2_Idx",
        "Ups_mu_1_Idx",
        "Ups_mu_2_Idx",
    )


def validate_input(input_file: str, channel: str):
    branches = set(get_tree_branches(input_file, OUTPUT_TREE))
    required = set(REQUIRED_GENMATCH_BRANCHES).union(required_index_branches(channel))
    missing = sorted(required - branches)
    if missing:
        raise RuntimeError(f"Input file is missing branches required for genMatch filtering: {', '.join(missing)}")
    return sorted(branches)


def main():
    args = parse_args()
    channel = normalize_channel(args.channel)
    sample = normalize_sample(channel, args.sample) if args.sample else None
    if args.input is None and sample is None:
        raise ValueError("--sample is required when --input is not specified")

    input_file = args.input or default_merged_output(channel, "mc", sample)
    output_file = args.output or default_output_path(input_file)
    ensure_parent_dir(output_file)

    schema_key = f"{channel}_mc"
    genmatch_expr = build_genmatch_expr(schema_key)
    if genmatch_expr is None:
        raise RuntimeError(f"No genMatch expression is defined for {schema_key}")

    snapshot_columns = validate_input(input_file, channel)

    ROOT.gROOT.SetBatch(True)
    if args.max_events > 0 and args.jobs > 1:
        print("[INFO] --max-events with RDataFrame implicit MT is not supported; setting jobs to 1")
        args.jobs = 1
    if args.jobs > 1:
        ROOT.EnableImplicitMT(args.jobs)
    declare_rdf_helpers()

    rdf = ROOT.RDataFrame(OUTPUT_TREE, input_file)
    if args.max_events > 0:
        rdf = rdf.Range(args.max_events)

    selected = rdf.Filter(genmatch_expr, "pass_genmatch_selection")
    total_action = rdf.Count()
    selected_action = selected.Count()
    report = selected.Report()

    options = ROOT.RDF.RSnapshotOptions()
    options.fMode = "RECREATE"
    options.fLazy = True
    snapshot_action = selected.Snapshot(OUTPUT_TREE, output_file, build_root_string_vector(snapshot_columns), options)
    ROOT.RDF.RunGraphs([total_action, selected_action, snapshot_action])

    total = int(total_action.GetValue())
    passed = int(selected_action.GetValue())
    eff = 0.0 if total == 0 else 100.0 * passed / total

    print("=" * 80)
    print("apply MC genMatch to merged selected ntuple")
    print("=" * 80)
    print(f"[INFO] channel  : {channel}")
    print(f"[INFO] sample   : {sample or '-'}")
    print(f"[INFO] input    : {input_file}")
    print(f"[INFO] output   : {output_file}")
    print(f"[INFO] jobs     : {args.jobs}")
    print(f"[INFO] total    : {total}")
    print(f"[INFO] selected : {passed}")
    print(f"[INFO] eff      : {eff:.3f}%")
    print("[INFO] genMatch : source=1, valid mother, mother pdgId J/psi/Upsilon/Phi")
    print("=" * 80)
    report.Print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

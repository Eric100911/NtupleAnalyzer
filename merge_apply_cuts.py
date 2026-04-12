#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge ntuples and apply assocPV kinematic selections."""

from __future__ import annotations

import argparse
import os
import sys
import time

import ROOT

from ntuple_pipeline_common import (
    TREE_NAME,
    MUON_ID_BRANCHES,
    build_root_string_vector,
    declare_rdf_helpers,
    default_input_dir,
    default_merged_output,
    discover_root_files,
    ensure_parent_dir,
    get_dataset_schema,
    get_tree_branches,
    normalize_channel,
    normalize_dataset,
    normalize_sample,
    define_selected_columns,
    selected_extra_columns,
)


OUTPUT_TREE = "selected"


def build_best_index_expr(schema_key: str) -> str:
    if schema_key == "JJP_data" or schema_key == "JJP_mc":
        return (
            "BestCandIndexJJP("
            "Jpsi_1_mass, Jpsi_1_pt, Jpsi_1_eta, Jpsi_1_mu_1_Idx, Jpsi_1_mu_2_Idx, "
            "Jpsi_2_mass, Jpsi_2_pt, Jpsi_2_eta, Jpsi_2_mu_1_Idx, Jpsi_2_mu_2_Idx, "
            "Phi_mass, Phi_pt, Phi_eta, Phi_K_1_pt, Phi_K_1_eta, Phi_K_2_pt, Phi_K_2_eta, "
            "muPx, muPy, muPz, muon_id_mask)"
        )
    if schema_key == "JUP_data":
        return (
            "BestCandIndexJUP("
            "Jpsi_mass, Jpsi_pt, Jpsi_eta, Jpsi_mu_1_Idx, Jpsi_mu_2_Idx, "
            "Ups_mass, Ups_pt, Ups_eta, Ups_mu_1_Idx, Ups_mu_2_Idx, "
            "Phi_mass, Phi_pt, Phi_eta, Phi_K_1_pt, Phi_K_1_eta, Phi_K_2_pt, Phi_K_2_eta, "
            "muPx, muPy, muPz, jpsi_muon_id_mask, ups_muon_id_mask)"
        )
    return (
        "BestCandIndexJUP("
        "Jpsi_1_mass, Jpsi_1_pt, Jpsi_1_eta, Jpsi_1_mu_1_Idx, Jpsi_1_mu_2_Idx, "
        "Ups_mass, Ups_pt, Ups_eta, Ups_mu_1_Idx, Ups_mu_2_Idx, "
        "Phi_mass, Phi_pt, Phi_eta, Phi_K_1_pt, Phi_K_1_eta, Phi_K_2_pt, Phi_K_2_eta, "
        "muPx, muPy, muPz, jpsi_muon_id_mask, ups_muon_id_mask)"
    )


def configure_rdf(schema, files, args):
    rdf = ROOT.RDataFrame(TREE_NAME, build_root_string_vector(files))

    if args.max_events > 0:
        rdf = rdf.Range(args.max_events)

    if schema.channel == "JJP":
        mask_branch = MUON_ID_BRANCHES[args.muon_id]
        mask_expr = "OnesLike(muPx)" if mask_branch is None else mask_branch
        rdf = rdf.Define("muon_id_mask", mask_expr)
    else:
        jpsi_mask_branch = MUON_ID_BRANCHES[args.jpsi_muon_id]
        ups_mask_branch = MUON_ID_BRANCHES[args.ups_muon_id]
        rdf = rdf.Define("jpsi_muon_id_mask", "OnesLike(muPx)" if jpsi_mask_branch is None else jpsi_mask_branch)
        rdf = rdf.Define("ups_muon_id_mask", "OnesLike(muPx)" if ups_mask_branch is None else ups_mask_branch)

    rdf = rdf.Define("bestCandIdx", build_best_index_expr(schema.schema_key))
    rdf = rdf.Filter("bestCandIdx >= 0", "pass_assocPV_selection")
    rdf = define_selected_columns(rdf, schema)
    return rdf


def parse_args():
    parser = argparse.ArgumentParser(description="Merge ntuples and apply assocPV cuts")
    parser.add_argument("--channel", required=True, choices=["JJP", "JUP", "jjp", "jup"], help="Physics channel")
    parser.add_argument("--dataset", default="data", choices=["data", "mc"], help="Input dataset type")
    parser.add_argument("--sample", default=None, help="MC sample tag (JJP: DPS/TPS, JUP: SPS/DPS_1/DPS_2/DPS_3/TPS)")
    parser.add_argument("-i", "--input-dir", default=None, help="Override input directory or ROOT file")
    parser.add_argument("-o", "--output", default=None, help="Output ROOT file")
    parser.add_argument("-j", "--jobs", type=int, default=8, help="RDataFrame thread count")
    parser.add_argument("-n", "--max-events", type=int, default=-1, help="Limit number of events for quick tests")
    parser.add_argument("--max-files", type=int, default=-1, help="Limit number of input files")
    parser.add_argument("--muon-id", default="soft", choices=list(MUON_ID_BRANCHES), help="Muon ID for JJP or all JUP muons when no explicit split is needed")
    parser.add_argument("--jpsi-muon-id", default="soft", choices=list(MUON_ID_BRANCHES), help="Muon ID for J/psi daughters in JUP")
    parser.add_argument("--ups-muon-id", default="soft", choices=list(MUON_ID_BRANCHES), help="Muon ID for Upsilon daughters in JUP")
    return parser.parse_args()


def main():
    args = parse_args()
    channel = normalize_channel(args.channel)
    dataset = normalize_dataset(args.dataset)
    sample = normalize_sample(channel, args.sample) if dataset == "mc" else None
    schema = get_dataset_schema(channel, dataset)

    input_dir = args.input_dir or default_input_dir(channel, dataset, sample)
    output_file = args.output or default_merged_output(channel, dataset, sample)
    ensure_parent_dir(output_file)

    if args.max_events > 0 and args.jobs > 1:
        print("[INFO] --max-events 与 RDataFrame 多线程同时使用不稳定，自动将 jobs 调整为 1")
        args.jobs = 1

    files = discover_root_files(input_dir, args.max_files)
    original_branches = get_tree_branches(files[0], TREE_NAME)
    snapshot_columns = list(dict.fromkeys(original_branches + selected_extra_columns(schema)))

    ROOT.gROOT.SetBatch(True)
    if args.jobs > 1:
        ROOT.EnableImplicitMT(args.jobs)
    declare_rdf_helpers()

    print("=" * 80)
    print("assocPV merge + cut")
    print("=" * 80)
    print(f"[INFO] channel      : {channel}")
    print(f"[INFO] dataset      : {dataset}")
    print(f"[INFO] sample       : {sample or '-'}")
    print(f"[INFO] input        : {input_dir}")
    print(f"[INFO] files        : {len(files)}")
    print(f"[INFO] output       : {output_file}")
    print(f"[INFO] jobs         : {args.jobs}")
    print(f"[INFO] max events   : {args.max_events}")
    if channel == "JJP":
        print(f"[INFO] muon ID      : {args.muon_id}")
    else:
        print(f"[INFO] J/psi muon ID: {args.jpsi_muon_id}")
        print(f"[INFO] Ups muon ID : {args.ups_muon_id}")
    print("=" * 80)

    start = time.time()
    rdf_all = ROOT.RDataFrame(TREE_NAME, build_root_string_vector(files))
    if args.max_events > 0:
        rdf_all = rdf_all.Range(args.max_events)
    total_action = rdf_all.Count()

    rdf_selected = configure_rdf(schema, files, args)
    selected_action = rdf_selected.Count()

    options = ROOT.RDF.RSnapshotOptions()
    options.fMode = "RECREATE"
    options.fLazy = True
    snapshot_action = rdf_selected.Snapshot(OUTPUT_TREE, output_file, build_root_string_vector(snapshot_columns), options)
    ROOT.RDF.RunGraphs([total_action, selected_action, snapshot_action])

    total_events = total_action.GetValue()
    selected_events = selected_action.GetValue()
    elapsed = time.time() - start
    eff = 0.0 if total_events == 0 else 100.0 * selected_events / total_events
    rate = 0.0 if elapsed <= 0 else total_events / elapsed

    print(f"[INFO] total events : {total_events}")
    print(f"[INFO] selected     : {selected_events}")
    print(f"[INFO] efficiency   : {eff:.3f}%")
    print(f"[INFO] elapsed      : {elapsed:.1f} s")
    print(f"[INFO] rate         : {rate:.1f} evt/s")
    print(f"[INFO] saved tree   : {OUTPUT_TREE}")
    print(f"[INFO] saved file   : {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

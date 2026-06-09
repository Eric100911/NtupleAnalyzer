#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge ntuples and apply assocPV kinematic selections."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

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
UNSUPPORTED_SNAPSHOT_TYPES = {
    "Float16_t": "float",
    "Double32_t": "double",
}


def build_genmatch_expr(schema_key: str) -> str | None:
    if schema_key == "JJP_mc":
        return (
            "PassSelectedJJPGenMatch("
            "TakeAtInt(Jpsi_1_mu_1_Idx, bestCandIdx), "
            "TakeAtInt(Jpsi_1_mu_2_Idx, bestCandIdx), "
            "TakeAtInt(Jpsi_2_mu_1_Idx, bestCandIdx), "
            "TakeAtInt(Jpsi_2_mu_2_Idx, bestCandIdx), "
            "bestCandIdx, "
            "muGenMatchIdx, muGenMatchSource, "
            "Phi_K_1_genMatchIdx, Phi_K_1_genMatchSource, "
            "Phi_K_2_genMatchIdx, Phi_K_2_genMatchSource, "
            "MC_GenPart_motherGenIdx, MC_GenPart_motherPdgId)"
        )
    if schema_key == "JYP_mc":
        return (
            "PassSelectedJYPGenMatch("
            "TakeAtInt(Jpsi_1_mu_1_Idx, bestCandIdx), "
            "TakeAtInt(Jpsi_1_mu_2_Idx, bestCandIdx), "
            "TakeAtInt(Ups_mu_1_Idx, bestCandIdx), "
            "TakeAtInt(Ups_mu_2_Idx, bestCandIdx), "
            "bestCandIdx, "
            "muGenMatchIdx, muGenMatchSource, "
            "Phi_K_1_genMatchIdx, Phi_K_1_genMatchSource, "
            "Phi_K_2_genMatchIdx, Phi_K_2_genMatchSource, "
            "MC_GenPart_motherGenIdx, MC_GenPart_motherPdgId)"
        )
    return None


def build_best_index_expr(schema_key: str) -> str:
    if schema_key == "JJP_data" or schema_key == "JJP_mc":
        return (
            "BestCandIndexJJP("
            "Jpsi_1_mass, Jpsi_1_pt, Jpsi_1_eta, Jpsi_1_mu_1_Idx, Jpsi_1_mu_2_Idx, "
            "Jpsi_2_mass, Jpsi_2_pt, Jpsi_2_eta, Jpsi_2_mu_1_Idx, Jpsi_2_mu_2_Idx, "
            "Phi_mass, Phi_pt, Phi_eta, Phi_K_1_pt, Phi_K_1_eta, Phi_K_2_pt, Phi_K_2_eta, "
            "muPx, muPy, muPz, muon_id_mask)"
        )
    if schema_key == "JYP_data":
        return (
            "BestCandIndexJYP("
            "Jpsi_mass, Jpsi_pt, Jpsi_eta, Jpsi_mu_1_Idx, Jpsi_mu_2_Idx, "
            "Ups_mass, Ups_pt, Ups_eta, Ups_mu_1_Idx, Ups_mu_2_Idx, "
            "Phi_mass, Phi_pt, Phi_eta, Phi_K_1_pt, Phi_K_1_eta, Phi_K_2_pt, Phi_K_2_eta, "
            "muPx, muPy, muPz, jpsi_muon_id_mask, ups_muon_id_mask)"
        )
    if schema_key == "JYP_mc":
        return (
            "BestCandIndexJYP("
            "Jpsi_1_mass, Jpsi_1_pt, Jpsi_1_eta, Jpsi_1_mu_1_Idx, Jpsi_1_mu_2_Idx, "
            "Ups_mass, Ups_pt, Ups_eta, Ups_mu_1_Idx, Ups_mu_2_Idx, "
            "Phi_mass, Phi_pt, Phi_eta, Phi_K_1_pt, Phi_K_1_eta, Phi_K_2_pt, Phi_K_2_eta, "
            "muPx, muPy, muPz, jpsi_muon_id_mask, ups_muon_id_mask)"
        )
    return (
        "BestCandIndexJJY("
        "Jpsi_1_mass, Jpsi_1_pt, Jpsi_1_eta, Jpsi_1_mu_1_Idx, Jpsi_1_mu_2_Idx, "
        "Jpsi_2_mass, Jpsi_2_pt, Jpsi_2_eta, Jpsi_2_mu_1_Idx, Jpsi_2_mu_2_Idx, "
        "Ups_mass, Ups_pt, Ups_eta, Ups_mu_1_Idx, Ups_mu_2_Idx, "
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
    genmatch_expr = build_genmatch_expr(schema.schema_key)
    if genmatch_expr is not None:
        rdf = rdf.Filter(genmatch_expr, "pass_genmatch_selection")
    rdf = define_selected_columns(rdf, schema)
    return rdf


def is_remote_file(path: str) -> bool:
    return path.startswith("root://")


def should_stage_remote_files(args, files) -> bool:
    if not files or not any(is_remote_file(path) for path in files):
        return False
    if args.stage_mode == "always":
        return True
    if args.stage_mode == "never":
        return False
    return True


def unique_stage_name(source: str, global_index: int) -> str:
    clean = source.split("?", 1)[0].rstrip("/")
    parts = clean.split("/")
    parent = parts[-2] if len(parts) >= 2 else "file"
    base = parts[-1] if parts else "input.root"
    return f"{global_index:06d}_{parent}_{base}"


def remote_copy_command(source: str, destination: str) -> list[str]:
    if shutil.which("gfal-copy"):
        return ["gfal-copy", "-f", source, destination]
    if shutil.which("xrdcp"):
        return ["xrdcp", "-f", source, destination]
    raise RuntimeError("No remote copy tool found. Install gfal-copy or xrdcp, or use --stage-mode never.")


def remote_copy_environment(command: list[str]):
    if command[0] != "gfal-copy" or os.environ.get("GFAL_PYTHONBIN"):
        return None
    if os.path.exists("/usr/bin/python3"):
        env = os.environ.copy()
        env["GFAL_PYTHONBIN"] = "/usr/bin/python3"
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        env.pop("LD_LIBRARY_PATH", None)
        return env
    return None


def copy_remote_file(source: str, destination: str) -> None:
    ensure_parent_dir(destination)
    attempts = 3
    last_error = None
    for attempt in range(1, attempts + 1):
        if os.path.exists(destination):
            os.remove(destination)
        try:
            command = remote_copy_command(source, destination)
            subprocess.run(command, check=True, env=remote_copy_environment(command))
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(min(30, 2 ** (attempt - 1)))
    raise RuntimeError(f"Failed to stage {source} after {attempts} attempt(s)") from last_error


def stage_remote_batch(remote_files, batch_index: int, stage_root: str, copy_jobs: int, start_index: int):
    batch_dir = os.path.join(stage_root, f"batch_{batch_index:04d}")
    os.makedirs(batch_dir, exist_ok=True)
    local_files = [
        os.path.join(batch_dir, unique_stage_name(src, start_index + idx))
        for idx, src in enumerate(remote_files)
    ]

    with ThreadPoolExecutor(max_workers=max(1, copy_jobs)) as executor:
        futures = [executor.submit(copy_remote_file, src, dst) for src, dst in zip(remote_files, local_files)]
        for future in as_completed(futures):
            future.result()
    return local_files


def remove_paths(paths) -> None:
    for path in paths:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)


def inspect_branch_types(file_name: str, tree_name: str):
    tf = ROOT.TFile.Open(file_name)
    if not tf or tf.IsZombie():
        raise RuntimeError(f"Failed to open {file_name} for branch inspection")
    tree = tf.Get(tree_name)
    if tree is None:
        tf.Close()
        raise RuntimeError(f"Tree {tree_name} not found in {file_name}")

    branch_types = {}
    for branch in tree.GetListOfBranches():
        branch_name = branch.GetName()
        for leaf in branch.GetListOfLeaves():
            branch_types[branch_name] = leaf.GetTypeName()
            break
    tf.Close()
    return branch_types


def prepare_snapshot_metadata(sample_file: str, schema):
    original_branches = get_tree_branches(sample_file, TREE_NAME)
    snapshot_columns = list(dict.fromkeys(original_branches + selected_extra_columns(schema)))
    branch_types = inspect_branch_types(sample_file, TREE_NAME)
    cast_map = {
        name: UNSUPPORTED_SNAPSHOT_TYPES[type_name]
        for name, type_name in branch_types.items()
        if name in snapshot_columns and type_name in UNSUPPORTED_SNAPSHOT_TYPES
    }
    return snapshot_columns, cast_map


def apply_snapshot_casts(rdf, cast_map):
    for branch_name, target_type in cast_map.items():
        rdf = rdf.Redefine(branch_name, f"static_cast<{target_type}>({branch_name})")
    return rdf


def load_file_manifest(path: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        files = payload.get("files")
    elif isinstance(payload, list):
        files = payload
    else:
        files = None
    if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
        raise ValueError(f"Manifest must contain a list of file paths: {path}")
    if not files:
        raise ValueError(f"Manifest contains no files: {path}")
    return files


def run_merge_once(schema, files, args, output_file: str, snapshot_columns, cast_map):
    start = time.time()
    rdf_all = ROOT.RDataFrame(TREE_NAME, build_root_string_vector(files))
    if args.max_events > 0:
        rdf_all = rdf_all.Range(args.max_events)
    total_action = rdf_all.Count()

    rdf_selected = configure_rdf(schema, files, args)
    rdf_selected = apply_snapshot_casts(rdf_selected, cast_map)
    selected_action = rdf_selected.Count()

    options = ROOT.RDF.RSnapshotOptions()
    options.fMode = "RECREATE"
    options.fLazy = True
    snapshot_action = rdf_selected.Snapshot(OUTPUT_TREE, output_file, build_root_string_vector(snapshot_columns), options)
    ROOT.RDF.RunGraphs([total_action, selected_action, snapshot_action])

    return {
        "total": int(total_action.GetValue()),
        "selected": int(selected_action.GetValue()),
        "elapsed": time.time() - start,
    }


def merge_chunk_outputs(chunk_outputs, merged_output: str) -> None:
    if not chunk_outputs:
        raise RuntimeError("No chunk outputs were produced")
    ensure_parent_dir(merged_output)
    if len(chunk_outputs) == 1:
        shutil.move(chunk_outputs[0], merged_output)
        return

    merger = ROOT.TFileMerger(False, False)
    if not merger.OutputFile(merged_output, "RECREATE"):
        raise RuntimeError(f"Failed to create merged output file: {merged_output}")
    for path in chunk_outputs:
        if not merger.AddFile(path):
            raise RuntimeError(f"Failed to add chunk output to merger: {path}")
    if not merger.Merge():
        raise RuntimeError(f"Failed to merge chunk outputs into {merged_output}")


def finalize_output(local_output: str, destination: str) -> None:
    ensure_parent_dir(destination)
    if os.path.abspath(local_output) == os.path.abspath(destination):
        return
    shutil.copy2(local_output, destination)


def process_with_local_staging(schema, remote_files, args, output_file: str):
    stage_parent = args.stage_dir or os.environ.get("TMPDIR") or tempfile.gettempdir()
    stage_parent = os.path.abspath(os.path.expanduser(stage_parent))
    os.makedirs(stage_parent, exist_ok=True)
    stage_root = tempfile.mkdtemp(prefix="merge_apply_cuts_", dir=stage_parent)
    final_local_output = os.path.join(stage_root, "merged_selected.root")
    chunk_outputs = []
    total_events = 0
    selected_events = 0
    batch_times = []
    snapshot_columns = None
    cast_map = None

    try:
        batch_size = max(1, args.stage_batch_files)
        copy_jobs = max(1, args.stage_copy_jobs)
        total_batches = (len(remote_files) + batch_size - 1) // batch_size
        for batch_index, start_idx in enumerate(range(0, len(remote_files), batch_size)):
            batch_remote_files = remote_files[start_idx : start_idx + batch_size]
            staged_inputs = stage_remote_batch(batch_remote_files, batch_index, stage_root, copy_jobs, start_idx)
            try:
                if snapshot_columns is None or cast_map is None:
                    snapshot_columns, cast_map = prepare_snapshot_metadata(staged_inputs[0], schema)
                chunk_output = os.path.join(stage_root, f"chunk_{batch_index:04d}.root")
                result = run_merge_once(schema, staged_inputs, args, chunk_output, snapshot_columns, cast_map)
                total_events += result["total"]
                selected_events += result["selected"]
                batch_times.append(result["elapsed"])
                chunk_outputs.append(chunk_output)
                print(
                    f"[INFO] staged batch   : {batch_index + 1}/{total_batches} "
                    f"files={len(batch_remote_files)} total={result['total']} selected={result['selected']} "
                    f"elapsed={result['elapsed']:.1f} s"
                )
            finally:
                if not args.keep_staged_files:
                    remove_paths(staged_inputs)
                    remove_paths([os.path.dirname(staged_inputs[0])])

        if snapshot_columns is None or cast_map is None:
            raise RuntimeError("No staged files were processed")

        merge_chunk_outputs(chunk_outputs, final_local_output)
        finalize_output(final_local_output, output_file)
        return {
            "total": total_events,
            "selected": selected_events,
            "elapsed": sum(batch_times),
            "staged_batches": len(batch_times),
            "stage_root": stage_root,
        }
    finally:
        if not args.keep_staged_files:
            remove_paths(chunk_outputs)
            if os.path.exists(final_local_output):
                remove_paths([final_local_output])
            remove_paths([stage_root])


def parse_args():
    parser = argparse.ArgumentParser(description="Merge ntuples and apply assocPV cuts")
    parser.add_argument("--channel", required=True, choices=["JJP", "JYP", "JJY", "jjp", "jyp", "jjy"], help="Physics channel")
    parser.add_argument("--dataset", default="data", choices=["data", "mc"], help="Input dataset type")
    parser.add_argument("--sample", default=None, help="MC sample tag (JJP: DPS_1/DPS_2_CS/DPS_2_G/SPS_CS/SPS_G/TPS, JYP: SPS/DPS_1/DPS_2/DPS_3/TPS, JJY: DPS_1/DPS_2)")
    parser.add_argument("-i", "--input-dir", default=None, help="Override input directory or ROOT file")
    parser.add_argument("--input-file-manifest", default=None, help="JSON manifest with an exact list of ROOT input files")
    parser.add_argument("-o", "--output", default=None, help="Output ROOT file")
    parser.add_argument("-j", "--jobs", type=int, default=8, help="RDataFrame thread count")
    parser.add_argument("-n", "--max-events", type=int, default=-1, help="Limit number of events for quick tests")
    parser.add_argument("--max-files", type=int, default=-1, help="Limit number of input files")
    parser.add_argument("--muon-id", default="soft", choices=list(MUON_ID_BRANCHES), help="Muon ID for JJP")
    parser.add_argument("--jpsi-muon-id", default="soft", choices=list(MUON_ID_BRANCHES), help="Muon ID for J/psi daughters in JYP/JJY")
    parser.add_argument("--ups-muon-id", default="soft", choices=list(MUON_ID_BRANCHES), help="Muon ID for Upsilon daughters in JYP/JJY")
    parser.add_argument("--stage-mode", default="auto", choices=["auto", "always", "never"], help="Stage remote files to local scratch before processing")
    parser.add_argument("--stage-dir", default=None, help="Parent directory for staged local files, defaults to TMPDIR or /tmp")
    parser.add_argument("--stage-batch-files", type=int, default=32, help="How many remote input files to copy into local scratch before processing and cleanup")
    parser.add_argument("--stage-copy-jobs", type=int, default=0, help="Parallel remote-copy workers used while filling a staged batch, defaults to min(4, jobs)")
    parser.add_argument("--keep-staged-files", action="store_true", help="Keep staged inputs and chunk outputs for debugging")
    return parser.parse_args()


def main():
    args = parse_args()
    channel = normalize_channel(args.channel)
    dataset = normalize_dataset(args.dataset)
    sample = normalize_sample(channel, args.sample) if dataset == "mc" else None
    schema = get_dataset_schema(channel, dataset)

    if args.input_file_manifest:
        input_dir = args.input_dir or args.input_file_manifest
    else:
        input_dir = args.input_dir or default_input_dir(channel, dataset, sample)
    output_file = args.output or default_merged_output(channel, dataset, sample)
    ensure_parent_dir(output_file)

    if args.max_events > 0 and args.jobs > 1:
        print("[INFO] --max-events 与 RDataFrame 多线程同时使用不稳定，自动将 jobs 调整为 1")
        args.jobs = 1
    if args.stage_copy_jobs <= 0:
        args.stage_copy_jobs = max(1, min(4, args.jobs))

    if args.input_file_manifest:
        files = load_file_manifest(args.input_file_manifest)
    else:
        files = discover_root_files(input_dir, args.max_files)
    stage_remote = should_stage_remote_files(args, files)
    snapshot_columns = None
    cast_map = None
    if not stage_remote:
        snapshot_columns, cast_map = prepare_snapshot_metadata(files[0], schema)

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
    if args.input_file_manifest:
        print(f"[INFO] manifest     : {args.input_file_manifest}")
    print(f"[INFO] files        : {len(files)}")
    print(f"[INFO] output       : {output_file}")
    print(f"[INFO] jobs         : {args.jobs}")
    print(f"[INFO] max events   : {args.max_events}")
    print(f"[INFO] stage mode   : {'local scratch' if stage_remote else 'direct'}")
    if stage_remote:
        print(f"[INFO] stage batch  : {args.stage_batch_files}")
        print(f"[INFO] copy workers : {args.stage_copy_jobs}")
    if channel == "JJP":
        print(f"[INFO] muon ID      : {args.muon_id}")
    else:
        print(f"[INFO] J/psi muon ID: {args.jpsi_muon_id}")
        print(f"[INFO] Ups muon ID : {args.ups_muon_id}")
    if dataset == "mc" and channel == "JJY":
        print("[INFO] genMatch     : disabled for JJY")
    elif dataset == "mc":
        print("[INFO] genMatch     : source=1, valid mother, mother pdgId J/psi/Upsilon/Phi")
    print("=" * 80)

    start = time.time()
    if stage_remote:
        result = process_with_local_staging(schema, files, args, output_file)
    else:
        result = run_merge_once(schema, files, args, output_file, snapshot_columns, cast_map)

    total_events = result["total"]
    selected_events = result["selected"]
    elapsed = time.time() - start
    eff = 0.0 if total_events == 0 else 100.0 * selected_events / total_events
    rate = 0.0 if elapsed <= 0 else total_events / elapsed

    print(f"[INFO] total events : {total_events}")
    print(f"[INFO] selected     : {selected_events}")
    print(f"[INFO] efficiency   : {eff:.3f}%")
    print(f"[INFO] elapsed      : {elapsed:.1f} s")
    print(f"[INFO] rate         : {rate:.1f} evt/s")
    if stage_remote:
        print(f"[INFO] staged batch : {result['staged_batches']}")
    print(f"[INFO] saved tree   : {OUTPUT_TREE}")
    print(f"[INFO] saved file   : {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

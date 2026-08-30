#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pandas as pd

from efficiency_workflow.config import (
    CmsPlotStyleConfig,
    EfficiencyDefinitionConfig,
    efficiency_definition_from_dict,
    load_efficiency_definition,
)
from efficiency_workflow.efficiency import (
    EfficiencyBinning,
    EfficiencyRunConfig,
    build_cutflow,
    build_efficiency_counts,
    build_subprocess_envelope,
    discover_xrootd_sample_files,
    load_efficiency_file_manifest,
    process_efficiency_file,
    run_efficiency_for_sample,
)
from efficiency_workflow.io import ensure_dir, read_json, read_parquet, write_json, write_parquet
from efficiency_workflow.plotting import write_efficiency_plots


def is_remote_file(path: str) -> bool:
    return path.startswith("root://")


def should_stage_remote_files(stage_mode: str, files: list[str]) -> bool:
    if not any(is_remote_file(path) for path in files):
        return False
    if stage_mode == "always":
        return True
    if stage_mode == "never":
        return False
    return True


def unique_stage_name(source: str, index: int) -> str:
    clean = source.split("?", 1)[0].rstrip("/")
    parts = clean.split("/")
    parent = parts[-2] if len(parts) >= 2 else "file"
    base = parts[-1] if parts else "input.root"
    return f"{index:06d}_{parent}_{base}"


def copy_command(source: str, destination: Path, copy_tool: str) -> list[str]:
    if copy_tool == "gfal":
        return ["gfal-copy", "-f", source, str(destination)]
    if copy_tool == "xrdcp":
        return ["xrdcp", "-f", source, str(destination)]
    if shutil.which("gfal-copy"):
        return ["gfal-copy", "-f", source, str(destination)]
    if shutil.which("xrdcp"):
        return ["xrdcp", "-f", source, str(destination)]
    raise RuntimeError("No remote copy tool found. Install gfal-copy or xrdcp, or use --stage-mode never.")


def copy_environment(command: list[str]) -> dict[str, str] | None:
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


def copy_remote_file(source: str, destination: Path, copy_tool: str, retries: int, copy_timeout: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    attempts = max(1, retries)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        if destination.exists():
            destination.unlink()
        command = copy_command(source, destination, copy_tool)
        try:
            subprocess.run(
                command,
                check=True,
                env=copy_environment(command),
                timeout=copy_timeout if copy_timeout > 0 else None,
            )
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(min(30, 2 ** (attempt - 1)))
    raise RuntimeError(f"Failed to stage {source} after {attempts} attempt(s)") from last_error


def worker_script_path() -> Path:
    return Path(__file__).resolve().parents[1] / "run_efficiency.py"


def run_efficiency_worker(spec_path: Path) -> None:
    spec = read_json(spec_path)
    output_dir = ensure_dir(Path(spec["output_dir"]))
    definition = efficiency_definition_from_dict(
        spec["efficiency_definition"],
        source=spec["efficiency_definition"].get("source", "worker-spec"),
    )
    tables = run_efficiency_for_sample(
        list(spec["files"]),
        spec["sample"],
        cfg=definition.offline_selection,
        tree_path=spec["tree_path"],
        backend=spec.get("efficiency_backend", "vectorized"),
        step_size=spec.get("step_size", "100 MB"),
        definition=definition,
        config_policy=spec.get("config_policy", "legacy"),
    )
    for key in ("gen_systems", "event_step_flags", "file_coverage", "gen_ancestry_qa"):
        write_parquet(tables[key], output_dir / f"{key}.parquet")
    write_json(
        {
            "sample": spec["sample"],
            "files": spec["files"],
            "tree_path": spec["tree_path"],
            "efficiency_definition": tables["efficiency_definition"],
            "input_metadata": tables["input_metadata"],
            "n_gen_rows": int(len(tables["gen_systems"])),
            "n_event_rows": int(len(tables["event_step_flags"])),
            "n_coverage_rows": int(len(tables["file_coverage"])),
        },
        output_dir / "worker_manifest.json",
    )


def run_worker_attempt(
    files: list[str],
    sample: str,
    tree_path: str,
    attempt_dir: Path,
    efficiency_backend: str,
    step_size: str,
    worker_timeout: int,
    definition: EfficiencyDefinitionConfig,
    config_policy: str,
) -> dict[str, Any]:
    ensure_dir(attempt_dir)
    spec_path = attempt_dir / "worker_spec.json"
    write_json(
        {
            "files": files,
            "sample": sample,
            "tree_path": tree_path,
            "output_dir": str(attempt_dir),
            "efficiency_backend": efficiency_backend,
            "step_size": step_size,
            "efficiency_definition": definition.to_dict(),
            "config_policy": config_policy,
        },
        spec_path,
    )
    subprocess.run(
        [
            sys.executable,
            str(worker_script_path()),
            "--worker-efficiency-json",
            str(spec_path),
        ],
        check=True,
        timeout=worker_timeout if worker_timeout > 0 else None,
    )
    worker_manifest = read_json(attempt_dir / "worker_manifest.json")
    return {
        "gen_systems": read_parquet(attempt_dir / "gen_systems.parquet"),
        "event_step_flags": read_parquet(attempt_dir / "event_step_flags.parquet"),
        "file_coverage": read_parquet(attempt_dir / "file_coverage.parquet"),
        "gen_ancestry_qa": read_parquet(attempt_dir / "gen_ancestry_qa.parquet"),
        "input_metadata": worker_manifest.get("input_metadata", []),
        "efficiency_definition": worker_manifest.get("efficiency_definition", definition.to_dict()),
    }


def fallback_attempts(source: str, stage_dir: Path, index: int) -> list[tuple[str, str, Path | None]]:
    staged = stage_dir / unique_stage_name(source, index)
    return [
        ("direct", source, None),
        ("xrdcp", str(staged), staged),
        ("gfal", str(staged), staged),
    ]


def process_file_with_fallback(
    source: str,
    sample: str,
    tree_path: str,
    stage_dir: Path,
    attempt_root: Path,
    index: int,
    retries: int,
    keep_staged_files: bool,
    efficiency_backend: str,
    step_size: str,
    worker_timeout: int,
    copy_timeout: int,
    definition: EfficiencyDefinitionConfig,
    config_policy: str,
) -> tuple[dict[str, Any], dict[str, str], str]:
    source_by_staged: dict[str, str] = {}
    last_error: Exception | None = None
    attempts = fallback_attempts(source, stage_dir, index) if is_remote_file(source) else [("local", source, None)]
    for method, path, staged_path in attempts:
        method_attempt_dir = attempt_root / f"{index:06d}_{method}"
        try:
            if method in {"xrdcp", "gfal"}:
                assert staged_path is not None
                copy_remote_file(source, staged_path, method, retries, copy_timeout)
            tables = run_worker_attempt(
                [path], sample, tree_path, method_attempt_dir, efficiency_backend,
                step_size, worker_timeout, definition, config_policy,
            )
            if staged_path is not None:
                source_by_staged[path] = source
            print(f"[INFO] access method: {method} succeeded for {source}")
            return tables, source_by_staged, method
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
            last_error = exc
            print(f"[WARN] access method: {method} failed for {source}: {exc}")
            if staged_path is not None and staged_path.exists() and not keep_staged_files:
                staged_path.unlink()
        finally:
            if not keep_staged_files:
                shutil.rmtree(method_attempt_dir, ignore_errors=True)
    raise RuntimeError(f"All access methods failed for {source}") from last_error


def run_efficiency_with_fallback(
    files: list[str],
    sample: str,
    tree_path: str,
    stage_dir: Path,
    retries: int,
    keep_staged_files: bool,
    efficiency_backend: str,
    step_size: str,
    worker_timeout: int,
    copy_timeout: int,
    include_trigger_matching: bool = True,
    definition: EfficiencyDefinitionConfig | None = None,
    config_policy: str = "legacy",
) -> tuple[dict[str, Any], dict[str, str], dict[str, int]]:
    definition = definition or load_efficiency_definition(None)
    frame_parts: dict[str, list[pd.DataFrame]] = {
        "gen_systems": [],
        "event_step_flags": [],
        "file_coverage": [],
        "gen_ancestry_qa": [],
    }
    input_metadata: list[dict[str, Any]] = []
    source_by_staged: dict[str, str] = {}
    method_counts: dict[str, int] = {}
    failed_files: list[str] = []
    attempt_root = ensure_dir(stage_dir / "_attempts")
    for index, source in enumerate(files):
        try:
            tables, source_map, method = process_file_with_fallback(
                source,
                sample,
                tree_path,
                stage_dir,
                attempt_root,
                index,
                retries,
                keep_staged_files,
                efficiency_backend,
                step_size,
                worker_timeout,
                copy_timeout,
                definition,
                config_policy,
            )
        except RuntimeError:
            print(f"[WARN] Skipping {source}: all {retries + 1} access methods failed")
            failed_files.append(source)
            continue
        method_counts[method] = method_counts.get(method, 0) + 1
        tables["file_coverage"]["access_method"] = method
        source_by_staged.update(source_map)
        for key in frame_parts:
            if not tables[key].empty:
                frame_parts[key].append(tables[key])
        input_metadata.extend(tables.get("input_metadata", []))
    if failed_files:
        failed_preview = ", ".join(failed_files[:3])
        if len(failed_files) > 3:
            failed_preview += f", ... ({len(failed_files)} total)"
        raise RuntimeError(
            f"Refusing incomplete efficiency sample {sample}: "
            f"{len(failed_files)}/{len(files)} input files failed. Failed files: {failed_preview}"
        )
    if not frame_parts["gen_systems"]:
        raise RuntimeError(f"No files could be processed for {sample}")
    combined = {
        key: pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        for key, parts in frame_parts.items()
    }
    gen_df = combined["gen_systems"]
    event_df = combined["event_step_flags"]
    binning = EfficiencyBinning(include_trigger_matching=include_trigger_matching, **definition.binning)
    tables = {
        **combined,
        "input_metadata": input_metadata,
        "efficiency_definition": definition.to_dict(),
        "efficiency_counts": build_efficiency_counts(gen_df, event_df, binning),
        "cutflow": build_cutflow(event_df, binning),
    }
    return tables, source_by_staged, method_counts


def stage_remote_files(files: list[str], sample: str, stage_dir: Path, copy_tool: str, retries: int, copy_timeout: int) -> tuple[list[str], dict[str, str]]:
    sample_dir = stage_dir / sample
    sample_dir.mkdir(parents=True, exist_ok=True)
    staged_files: list[str] = []
    source_by_staged: dict[str, str] = {}
    for index, source in enumerate(files):
        if not is_remote_file(source):
            staged_files.append(source)
            continue
        destination = sample_dir / unique_stage_name(source, index)
        copy_remote_file(source, destination, copy_tool, retries, copy_timeout)
        staged = str(destination)
        staged_files.append(staged)
        source_by_staged[staged] = source
    return staged_files, source_by_staged


def restore_source_file_labels(tables: dict[str, Any], source_by_staged: dict[str, str]) -> None:
    if not source_by_staged:
        return
    for frame in tables.values():
        if isinstance(frame, pd.DataFrame) and "source_file" in frame:
            frame["source_file"] = frame["source_file"].replace(source_by_staged)
    for metadata in tables.get("input_metadata", []):
        if metadata.get("source_file") in source_by_staged:
            metadata["source_file"] = source_by_staged[metadata["source_file"]]


def apply_manifest_coverage(
    tables: dict[str, Any],
    sample: str,
    manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    coverage = tables["file_coverage"].copy()
    if coverage.empty:
        raise RuntimeError(f"No file coverage rows were produced for {sample}")
    if coverage["source_file"].duplicated().any():
        duplicates = coverage.loc[coverage["source_file"].duplicated(), "source_file"].tolist()
        raise RuntimeError(f"Duplicate processed files for {sample}: {duplicates[:3]}")

    manifest = manifest or {}
    expected_rows = {
        str(item["source_file"]): item
        for item in manifest.get("inventory", [])
        if isinstance(item, dict) and "source_file" in item
    }
    if expected_rows:
        observed = set(coverage["source_file"].astype(str))
        expected = set(expected_rows)
        if observed != expected:
            raise RuntimeError(
                f"Coverage mismatch for {sample}: missing={sorted(expected - observed)[:3]}, "
                f"unexpected={sorted(observed - expected)[:3]}"
            )
        coverage["expected_total_entries"] = coverage["source_file"].map(
            lambda item: int(expected_rows[str(item)]["total_entries"])
        )
        coverage["expected_retained_candidate_events"] = coverage["source_file"].map(
            lambda item: int(
                expected_rows[str(item)].get(
                    "retained_candidate_events",
                    expected_rows[str(item)].get("retained_events", -1),
                )
            )
        )
        bad_entries = coverage["entries_scanned"] != coverage["expected_total_entries"]
        bad_retained = (
            (coverage["expected_retained_candidate_events"] >= 0)
            & (coverage["retained_candidate_events"] != coverage["expected_retained_candidate_events"])
        )
        if bad_entries.any() or bad_retained.any():
            bad = coverage.loc[bad_entries | bad_retained, [
                "source_file", "entries_scanned", "expected_total_entries",
                "retained_candidate_events", "expected_retained_candidate_events",
            ]]
            raise RuntimeError(f"Inventory count mismatch for {sample}: {bad.head(3).to_dict(orient='records')}")

    if coverage["compatibility_hash"].nunique() != 1:
        raise RuntimeError(f"Refusing to combine incompatible X_config settings for {sample}")
    if coverage["efficiency_config_hash"].nunique() != 1:
        raise RuntimeError(f"Refusing to combine different efficiency definitions for {sample}")

    master_n_files = int(manifest.get("master_n_files", manifest.get("n_files", len(coverage))))
    coverage_scope = "complete" if len(coverage) == master_n_files else "partial"
    coverage["master_manifest_id"] = manifest.get("master_manifest_id", manifest.get("manifest_id", ""))
    coverage["coverage_scope"] = coverage_scope
    if "shard_index" in manifest:
        coverage["shard_index"] = int(manifest["shard_index"])
    tables["file_coverage"] = coverage
    tables["coverage_summary"] = {
        "sample": sample,
        "coverage_scope": coverage_scope,
        "n_processed_files": int(len(coverage)),
        "master_n_files": master_n_files,
        "entries_scanned": int(coverage["entries_scanned"].sum()),
        "retained_candidate_events": int(coverage["retained_candidate_events"].sum()),
        "full_gen_events": int(coverage["full_gen_events"].sum()),
        "master_manifest_id": manifest.get("master_manifest_id", manifest.get("manifest_id")),
    }
    return tables


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute acceptance and efficiency maps for MultiLepPAT MC ntuples. "
            "The first implemented channel is JpsiJpsiPhi."
        )
    )
    parser.add_argument("--analysis-mode", default="JpsiJpsiPhi", choices=("JpsiJpsiPhi",))
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--input-files", nargs="*", default=None, help="Explicit input ntuple ROOT files or XRootD URLs.")
    parser.add_argument("--input-file-manifest", default=None, help="JSON object mapping sample names to input ROOT files or XRootD URLs.")
    parser.add_argument("--sample-name", default="explicit", help="Sample label used with --input-files.")
    parser.add_argument("--xrootd-host", default="root://cceos.ihep.ac.cn//")
    parser.add_argument("--sample-root", default="/eos/ihep/cms/store/user/xcheng/MC_Production_v3/output")
    parser.add_argument("--samples", default=None, help="Comma-separated samples for XRootD discovery, or a manifest filter when --input-file-manifest is used.")
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--tree-path", default="auto", help="Data tree path or auto for X_data/mkcands/X_data detection.")
    parser.add_argument("--min-plot-total", type=int, default=1)
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--stage-mode", default="auto", choices=("auto", "always", "never"), help="Stage remote root:// inputs to local scratch before reading.")
    parser.add_argument("--stage-dir", default=None, help="Parent directory for staged inputs, defaults to TMPDIR or /tmp.")
    parser.add_argument("--stage-copy-tool", default="auto", choices=("auto", "gfal", "xrdcp"), help="Remote copy tool used for staging.")
    parser.add_argument("--stage-retries", type=int, default=3, help="Copy attempts per staged remote file.")
    parser.add_argument("--copy-timeout", type=int, default=180, help="Seconds allowed for one remote copy attempt; use 0 to disable.")
    parser.add_argument("--keep-staged-files", action="store_true", help="Keep staged input files for debugging.")
    parser.add_argument("--remote-access-mode", default="fallback", choices=("fallback", "direct", "stage"), help="Remote input access policy: direct XRootD, staged copy, or direct/xrdcp/gfal fallback.")
    parser.add_argument("--efficiency-backend", default="vectorized", choices=("vectorized", "python-loop"), help="Efficiency implementation backend.")
    parser.add_argument("--step-size", default="100 MB", help="uproot.iterate chunk size for the vectorized backend.")
    parser.add_argument("--worker-timeout", type=int, default=180, help="Seconds allowed for one file read attempt before trying the next access method; use 0 to disable.")
    parser.add_argument("--worker-efficiency-json", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--efficiency-config", default=None, help="Versioned YAML efficiency definition; use configs/efficiency/tps_nominal.yaml for the JJP sample contract.")
    parser.add_argument("--config-policy", default=None, choices=("strict", "legacy"), help="X_config/schema policy; defaults to strict with --efficiency-config and legacy otherwise.")
    parser.add_argument("--cms-caption", default="Simulation Preliminary")
    parser.add_argument("--cms-energy", type=float, default=13.6)
    parser.add_argument("--cms-lumi", type=float, default=None)
    parser.add_argument("--cms-era", default="Run 3")
    parser.add_argument("--skip-trigger-matching", action="store_true",
                        help="Skip the hlt_muon_matched step; condition four_muon_vtx on hlt_event directly")
    return parser.parse_args(argv)


def _parse_csv(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _write_sample_bundle(
    sample_dir: Path,
    sample: str,
    files: list[str],
    tables: dict[str, pd.DataFrame],
    plot_style_cfg: CmsPlotStyleConfig,
    min_plot_total: int,
    skip_plots: bool,
) -> dict[str, Any]:
    ensure_dir(sample_dir)
    artifacts: dict[str, Any] = {}
    write_json(
        {
            "sample": sample,
            "n_input_files": len(files),
            "input_files": files,
            "coverage": tables.get("coverage_summary", {}),
        },
        sample_dir / "sample_manifest.json",
    )
    artifacts["sample_manifest"] = "sample_manifest.json"

    for key in ("gen_systems", "event_step_flags", "efficiency_counts", "file_coverage", "gen_ancestry_qa"):
        path = sample_dir / f"{key}.parquet"
        write_parquet(tables[key], path)
        artifacts[key] = {"path": path.name, "n_rows": int(len(tables[key]))}
    maps_path = sample_dir / "efficiency_maps.parquet"
    write_parquet(tables["efficiency_counts"], maps_path)
    artifacts["efficiency_maps"] = {"path": maps_path.name, "n_rows": int(len(tables["efficiency_counts"]))}

    cutflow_path = sample_dir / "cutflow.csv"
    tables["cutflow"].to_csv(cutflow_path, index=False)
    artifacts["cutflow"] = {"path": cutflow_path.name, "n_rows": int(len(tables["cutflow"]))}

    event_df = tables["event_step_flags"]
    comparison_rows: list[dict[str, Any]] = []
    if not event_df.empty:
        nominal = event_df["four_muon_vtx"].astype(bool)
        denominator = event_df["hlt_muon_matched"].astype(bool)
        for column in (
            "four_muon_vtx_legacy_muVertexId",
            "four_muon_vtx_commonRecVtxPass",
            "four_muon_vtx_passAny",
            "four_muon_vtx_vtxprob",
        ):
            alternative = event_df[column].astype(bool)
            comparison_rows.append({
                "definition": column,
                "denominator": int(denominator.sum()),
                "nominal_passed": int((denominator & nominal).sum()),
                "alternative_passed": int((denominator & alternative).sum()),
                "both": int((denominator & nominal & alternative).sum()),
                "nominal_only": int((denominator & nominal & ~alternative).sum()),
                "alternative_only": int((denominator & ~nominal & alternative).sum()),
                "neither": int((denominator & ~nominal & ~alternative).sum()),
            })
    comparison = pd.DataFrame(comparison_rows)
    comparison_path = sample_dir / "four_muon_definition_comparison.csv"
    comparison.to_csv(comparison_path, index=False)
    artifacts["four_muon_definition_comparison"] = {
        "path": comparison_path.name,
        "n_rows": int(len(comparison)),
    }
    write_json({
        "efficiency_definition": tables.get("efficiency_definition", {}),
        "input_metadata": tables.get("input_metadata", []),
    }, sample_dir / "configuration_metadata.json")
    artifacts["configuration_metadata"] = "configuration_metadata.json"

    if not skip_plots:
        plot_paths = write_efficiency_plots(
            sample_dir / "plots",
            tables["efficiency_counts"],
            plot_style_cfg=plot_style_cfg,
            min_total=min_plot_total,
        )
        artifacts["plots"] = {key: str(path.relative_to(sample_dir)) for key, path in plot_paths.items()}

    write_json(
        {
            "stage": "efficiency",
            "sample": sample,
            "artifacts": artifacts,
        },
        sample_dir / "manifest.json",
    )
    return artifacts


def main() -> None:
    args = parse_args()
    include_trig_match = not args.skip_trigger_matching
    if args.worker_efficiency_json:
        run_efficiency_worker(Path(args.worker_efficiency_json))
        return
    if args.output_dir is None:
        raise ValueError("--output-dir is required")
    definition = load_efficiency_definition(args.efficiency_config)
    config_policy = args.config_policy or ("strict" if args.efficiency_config else "legacy")
    output_dir = ensure_dir(Path(args.output_dir))
    samples_filter = _parse_csv(args.samples) if args.samples is not None else None
    run_samples = samples_filter if samples_filter is not None else EfficiencyRunConfig().samples
    run_cfg = EfficiencyRunConfig(
        analysis_mode=args.analysis_mode,
        tree_path=args.tree_path,
        xrootd_host=args.xrootd_host,
        sample_root=args.sample_root,
        samples=run_samples,
        max_files=args.max_files,
        min_plot_total=args.min_plot_total,
    )
    offline_cfg = definition.offline_selection
    plot_style_cfg = CmsPlotStyleConfig(
        caption=args.cms_caption,
        energy_tev=args.cms_energy,
        lumi_fb=args.cms_lumi,
        era=args.cms_era,
        is_data=False,
    )

    if args.input_files is not None and args.input_file_manifest:
        raise ValueError("--input-files and --input-file-manifest are mutually exclusive.")
    if args.input_files is not None and not args.input_files:
        raise ValueError("--input-files requires at least one file.")

    input_manifest_payload: dict[str, Any] | None = None
    if args.input_files is not None:
        input_source = "explicit"
        files_by_sample = {args.sample_name: list(args.input_files)}
    elif args.input_file_manifest:
        input_source = "manifest"
        print(f"Loading input file manifest {args.input_file_manifest}")
        raw_manifest = read_json(Path(args.input_file_manifest))
        if isinstance(raw_manifest, dict) and isinstance(raw_manifest.get("sample"), str):
            input_manifest_payload = raw_manifest
        files_by_sample = load_efficiency_file_manifest(args.input_file_manifest, samples=samples_filter, max_files=run_cfg.max_files)
    else:
        input_source = "xrootd_discovery"
        print(f"Discovering XRootD samples under {run_cfg.sample_root}")
        files_by_sample = discover_xrootd_sample_files(
            host=run_cfg.xrootd_host,
            sample_root=run_cfg.sample_root,
            samples=run_cfg.samples,
            max_files=run_cfg.max_files,
        )

    write_json(
        {
            "analysis_mode": run_cfg.analysis_mode,
            "tree_path": run_cfg.tree_path,
            "xrootd_host": run_cfg.xrootd_host,
            "sample_root": run_cfg.sample_root,
            "samples": list(files_by_sample),
            "requested_samples": list(samples_filter or run_cfg.samples),
            "max_files": run_cfg.max_files,
            "min_plot_total": run_cfg.min_plot_total,
            "input_source": input_source,
            "input_file_manifest": str(args.input_file_manifest) if args.input_file_manifest else None,
            "remote_access_mode": args.remote_access_mode,
            "stage_mode": args.stage_mode,
            "stage_copy_tool": args.stage_copy_tool,
            "stage_retries": args.stage_retries,
            "copy_timeout": args.copy_timeout,
            "efficiency_backend": args.efficiency_backend,
            "step_size": args.step_size,
            "worker_timeout": args.worker_timeout,
            "efficiency_config": definition.to_dict(),
            "config_policy": config_policy,
            "cms_plot_style": plot_style_cfg.__dict__,
        },
        output_dir / "run_metadata.json",
    )

    sample_count_tables: dict[str, pd.DataFrame] = {}
    summary_rows: list[dict[str, Any]] = []
    stage_root = Path(args.stage_dir or os.environ.get("TMPDIR", "/tmp")) / "ntuple_efficiency_stage"
    stage_root = Path(tempfile.mkdtemp(prefix="eff_", dir=stage_root.parent)) if args.stage_dir is None else stage_root
    for sample, files in files_by_sample.items():
        if not files:
            print(f"Skipping {sample}: no input files found")
            continue
        process_files = files
        source_by_staged: dict[str, str] = {}
        sample_stage_dir: Path | None = None
        method_counts: dict[str, int] = {}
        use_fallback = args.remote_access_mode == "fallback" and args.stage_mode == "auto"
        if use_fallback:
            sample_stage_dir = ensure_dir(stage_root / sample)
            print(f"Running efficiency stage for {sample}: {len(files)} files with direct/xrdcp/gfal fallback")
            try:
                tables, source_by_staged, method_counts = run_efficiency_with_fallback(
                    files,
                    sample,
                    tree_path=run_cfg.tree_path,
                    stage_dir=sample_stage_dir,
                    retries=args.stage_retries,
                    keep_staged_files=args.keep_staged_files,
                    efficiency_backend=args.efficiency_backend,
                    step_size=args.step_size,
                    worker_timeout=args.worker_timeout,
                    copy_timeout=args.copy_timeout,
                    include_trigger_matching=include_trig_match,
                    definition=definition,
                    config_policy=config_policy,
                )
            finally:
                if sample_stage_dir is not None and not args.keep_staged_files:
                    shutil.rmtree(sample_stage_dir, ignore_errors=True)
        elif args.remote_access_mode == "stage" or args.stage_mode == "always":
            sample_stage_dir = stage_root / sample
            print(f"Staging {sample}: {len(files)} file(s) via {args.stage_copy_tool}")
            process_files, source_by_staged = stage_remote_files(
                files,
                sample,
                stage_root,
                copy_tool=args.stage_copy_tool,
                retries=args.stage_retries,
                copy_timeout=args.copy_timeout,
            )
            print(f"Running efficiency stage for {sample}: {len(process_files)} files")
            try:
                tables = run_efficiency_for_sample(
                    process_files,
                    sample,
                    cfg=offline_cfg,
                    tree_path=run_cfg.tree_path,
                    backend=args.efficiency_backend,
                    step_size=args.step_size,
                    include_trigger_matching=include_trig_match,
                    definition=definition,
                    config_policy=config_policy,
                )
            finally:
                if sample_stage_dir is not None and not args.keep_staged_files:
                    shutil.rmtree(sample_stage_dir, ignore_errors=True)
        else:
            print(f"Running efficiency stage for {sample}: {len(process_files)} files")
            tables = run_efficiency_for_sample(
                process_files,
                sample,
                cfg=offline_cfg,
                tree_path=run_cfg.tree_path,
                backend=args.efficiency_backend,
                step_size=args.step_size,
                include_trigger_matching=include_trig_match,
                definition=definition,
                config_policy=config_policy,
            )
        restore_source_file_labels(tables, source_by_staged)
        if "access_method" not in tables["file_coverage"]:
            tables["file_coverage"]["access_method"] = (
                "stage" if args.remote_access_mode == "stage" or args.stage_mode == "always" else "direct"
            )
        sample_manifest = None
        if input_manifest_payload and input_manifest_payload.get("sample") == sample:
            sample_manifest = dict(input_manifest_payload)
            selected_files = set(files)
            sample_manifest["inventory"] = [
                item for item in input_manifest_payload.get("inventory", [])
                if item.get("source_file") in selected_files
            ]
            sample_manifest["n_files"] = len(files)
        apply_manifest_coverage(tables, sample, sample_manifest)
        sample_count_tables[sample] = tables["efficiency_counts"]
        sample_dir = ensure_dir(output_dir / sample)
        _write_sample_bundle(
            sample_dir,
            sample,
            files,
            tables,
            plot_style_cfg=plot_style_cfg,
            min_plot_total=run_cfg.min_plot_total,
            skip_plots=args.skip_plots,
        )
        inclusive_final = tables["cutflow"].loc[tables["cutflow"]["step"] == "Pri_trackPVPass"]
        summary_rows.append(
            {
                "sample": sample,
                "n_input_files": len(files),
                "n_full_gen": int(tables["event_step_flags"]["full_gen"].sum()) if not tables["event_step_flags"].empty else 0,
                "n_Pri_trackPVPass": int(tables["event_step_flags"]["Pri_trackPVPass"].sum()) if not tables["event_step_flags"].empty else 0,
                "final_efficiency": float(inclusive_final["efficiency"].iloc[0]) if not inclusive_final.empty else float("nan"),
                "final_err_sym": float(inclusive_final["err_sym"].iloc[0]) if not inclusive_final.empty else float("nan"),
                "access_methods": ",".join(f"{key}:{value}" for key, value in sorted(method_counts.items())),
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    write_parquet(summary_df, output_dir / "subprocess_summary.parquet")
    summary_df.to_csv(output_dir / "subprocess_summary.csv", index=False)

    envelope_df = build_subprocess_envelope(sample_count_tables)
    write_parquet(envelope_df, output_dir / "subprocess_envelope.parquet")
    write_json(
        {
            "stage": "efficiency_summary",
            "artifacts": {
                "run_metadata": "run_metadata.json",
                "subprocess_summary": "subprocess_summary.parquet",
                "subprocess_envelope": "subprocess_envelope.parquet",
                "samples": {sample: f"{sample}/manifest.json" for sample in sample_count_tables},
            },
        },
        output_dir / "manifest.json",
    )
    print(f"Wrote efficiency outputs to {output_dir}")


if __name__ == "__main__":
    main()

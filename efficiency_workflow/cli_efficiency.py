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

from efficiency_workflow.config import CmsPlotStyleConfig, OfflineSelectionConfig
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
    cfg = OfflineSelectionConfig()
    gen_parts: list[pd.DataFrame] = []
    event_parts: list[pd.DataFrame] = []
    for path in spec["files"]:
        tables = run_efficiency_for_sample(
            [path],
            spec["sample"],
            cfg=cfg,
            tree_path=spec["tree_path"],
            backend=spec.get("efficiency_backend", "vectorized"),
            step_size=spec.get("step_size", "100 MB"),
        )
        if not tables["gen_systems"].empty:
            gen_parts.append(tables["gen_systems"])
        if not tables["event_step_flags"].empty:
            event_parts.append(tables["event_step_flags"])
    gen_df = pd.concat(gen_parts, ignore_index=True) if gen_parts else pd.DataFrame()
    event_df = pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()
    write_parquet(gen_df, output_dir / "gen_systems.parquet")
    write_parquet(event_df, output_dir / "event_step_flags.parquet")
    write_json(
        {
            "sample": spec["sample"],
            "files": spec["files"],
            "tree_path": spec["tree_path"],
            "n_gen_rows": int(len(gen_df)),
            "n_event_rows": int(len(event_df)),
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
) -> dict[str, pd.DataFrame]:
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
    return {
        "gen_systems": read_parquet(attempt_dir / "gen_systems.parquet"),
        "event_step_flags": read_parquet(attempt_dir / "event_step_flags.parquet"),
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
) -> tuple[dict[str, pd.DataFrame], dict[str, str], str]:
    source_by_staged: dict[str, str] = {}
    last_error: Exception | None = None
    attempts = fallback_attempts(source, stage_dir, index) if is_remote_file(source) else [("local", source, None)]
    for method, path, staged_path in attempts:
        method_attempt_dir = attempt_root / f"{index:06d}_{method}"
        try:
            if method in {"xrdcp", "gfal"}:
                assert staged_path is not None
                copy_remote_file(source, staged_path, method, retries, copy_timeout)
            tables = run_worker_attempt([path], sample, tree_path, method_attempt_dir, efficiency_backend, step_size, worker_timeout)
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
) -> tuple[dict[str, pd.DataFrame], dict[str, str], dict[str, int]]:
    gen_parts: list[pd.DataFrame] = []
    event_parts: list[pd.DataFrame] = []
    source_by_staged: dict[str, str] = {}
    method_counts: dict[str, int] = {}
    attempt_root = ensure_dir(stage_dir / "_attempts")
    for index, source in enumerate(files):
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
        )
        method_counts[method] = method_counts.get(method, 0) + 1
        source_by_staged.update(source_map)
        if not tables["gen_systems"].empty:
            gen_parts.append(tables["gen_systems"])
        if not tables["event_step_flags"].empty:
            event_parts.append(tables["event_step_flags"])
    gen_df = pd.concat(gen_parts, ignore_index=True) if gen_parts else pd.DataFrame()
    event_df = pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()
    binning = EfficiencyBinning(include_trigger_matching=include_trigger_matching)
    tables = {
        "gen_systems": gen_df,
        "event_step_flags": event_df,
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


def restore_source_file_labels(tables: dict[str, pd.DataFrame], source_by_staged: dict[str, str]) -> None:
    if not source_by_staged:
        return
    for frame in tables.values():
        if "source_file" in frame:
            frame["source_file"] = frame["source_file"].replace(source_by_staged)


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
    parser.add_argument("--tree-path", default="mkcands/X_data")
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
    write_json({"sample": sample, "n_input_files": len(files), "input_files": files}, sample_dir / "sample_manifest.json")
    artifacts["sample_manifest"] = "sample_manifest.json"

    for key in ("gen_systems", "event_step_flags", "efficiency_counts"):
        path = sample_dir / f"{key}.parquet"
        write_parquet(tables[key], path)
        artifacts[key] = {"path": path.name, "n_rows": int(len(tables[key]))}
    maps_path = sample_dir / "efficiency_maps.parquet"
    write_parquet(tables["efficiency_counts"], maps_path)
    artifacts["efficiency_maps"] = {"path": maps_path.name, "n_rows": int(len(tables["efficiency_counts"]))}

    cutflow_path = sample_dir / "cutflow.csv"
    tables["cutflow"].to_csv(cutflow_path, index=False)
    artifacts["cutflow"] = {"path": cutflow_path.name, "n_rows": int(len(tables["cutflow"]))}

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
    offline_cfg = OfflineSelectionConfig()
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

    if args.input_files is not None:
        input_source = "explicit"
        files_by_sample = {args.sample_name: list(args.input_files)}
    elif args.input_file_manifest:
        input_source = "manifest"
        print(f"Loading input file manifest {args.input_file_manifest}")
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
            "offline_selection": offline_cfg.__dict__,
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
            )
        restore_source_file_labels(tables, source_by_staged)
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

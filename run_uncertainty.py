from __future__ import annotations

import argparse
from functools import partial
from pathlib import Path

from uncertainty_workflow.config import load_variation_configs
from uncertainty_workflow.evaluate import evaluate_source, write_evaluated_source
from uncertainty_workflow.provenance import hash_config
from uncertainty_workflow.registry import SystematicRegistry
from uncertainty_workflow.runners import (
    load_variation_result,
    run_efficiency_config_variation,
    run_fit_variation,
    run_mc_stat_variation,
)


DEFAULT_CONFIG_DIR = Path("configs/systematics")
DEFAULT_OUTPUT_DIR = Path("outputs/systematics")
DEFAULT_YIELD_SAMPLES = ("JJP_DPS1", "JJP_DPS2_CS", "JJP_DPS2_G", "JJP_SPS_CS", "JJP_SPS_G")
DEFAULT_NOMINAL_SAMPLE = "JJP_DPS1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run and summarize NtupleAnalyzer systematic uncertainties")
    parser.add_argument(
        "--config",
        action="append",
        default=None,
        help="YAML config file or directory. Defaults to configs/systematics.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Systematics output directory")
    parser.add_argument("--nominal-dir", default=str(DEFAULT_OUTPUT_DIR / "nominal"), help="Nominal products directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List configured systematic sources")

    run_parser = subparsers.add_parser("run", help="Run configured systematic sources")
    run_parser.add_argument("--dry-run", action="store_true", help="Print planned work without running physics code")
    run_parser.add_argument("--force", action="store_true", help="Ignore cached manifests")
    run_parser.add_argument("--max-workers", type=int, default=1, help="Maximum parallel variation workers")
    run_parser.add_argument("--sources", nargs="*", default=None, help="Specific source names to run")
    run_parser.add_argument("--fit-input", default=None, help="Selected JJP ROOT file for fit-model variations")
    run_parser.add_argument("--fit-tree-name", default="selected", help="Input tree for fit-model variations")
    run_parser.add_argument("--fit-weight-branch", default=None, help="Optional fit weight branch")
    run_parser.add_argument("--dataset", default="data", choices=["data", "mc"], help="Dataset type for fit-model variations")
    run_parser.add_argument(
        "--weighted-error-mode",
        default="asymptotic",
        choices=["asymptotic", "sumw2", "original"],
        help="RooFit covariance treatment for weighted fits",
    )
    run_parser.add_argument("--eff-input-manifest", default=None, help="JSON mapping efficiency samples to raw ntuple files")
    run_parser.add_argument("--data-input", default=None, help="Selected data ROOT file for corrected-yield variations")
    run_parser.add_argument("--nominal-efficiency-dir", default=None, help="Nominal merged efficiency directory")
    run_parser.add_argument("--eff-sample", default=DEFAULT_NOMINAL_SAMPLE, help="Efficiency sample to rebuild for selection variations")
    run_parser.add_argument(
        "--yield-samples",
        default=",".join(DEFAULT_YIELD_SAMPLES),
        help="Comma-separated samples passed to compute_efficiency_corrected_yield",
    )
    run_parser.add_argument("--nominal-sample", default=DEFAULT_NOMINAL_SAMPLE, help="Nominal sample for corrected yield")
    run_parser.add_argument("--tree-path", default="X_data", help="Raw TPS-Onia2MuMu tree path for efficiency extraction")
    run_parser.add_argument(
        "--efficiency-backend",
        default="vectorized",
        choices=["vectorized", "python-loop"],
        help="Efficiency extraction backend for selection variations",
    )
    run_parser.add_argument("--step-size", default="100 MB", help="uproot.iterate chunk size for vectorized efficiency extraction")
    run_parser.add_argument("--max-files", type=int, default=None, help="Limit raw efficiency files per varied sample")
    run_parser.add_argument("--event-end-step", default="Pri_assocPVPass", help="Final event step for factorized maps")
    run_parser.add_argument(
        "--correction-mode",
        default="factorized",
        choices=["factorized", "legacy-correlated", "hybrid"],
        help="Corrected-yield correction mode for efficiency-selection variations",
    )
    run_parser.add_argument("--n-min-fine", type=int, default=30, help="Fine-bin minimum statistics for factorized lookup")
    run_parser.add_argument("--n-min-coarse", type=int, default=50, help="Coarse-bin minimum statistics for factorized lookup")
    run_parser.add_argument("--nominal-yield-json", default=None, help="Nominal corrected-yield JSON for analytic MC-stat mode")
    run_parser.add_argument("--mc-stat-mode", default=None, choices=["analytic", "toy"], help="MC-stat runner mode")
    run_parser.add_argument("--mc-stat-toys", type=int, default=None, help="Number of MC-stat toys")
    run_parser.add_argument("--mc-stat-seed", type=int, default=None, help="Base random seed for MC-stat toys")
    run_parser.add_argument("--mc-stat-clip", nargs=2, type=float, default=None, metavar=("LOW", "HIGH"), help="Toy efficiency clipping bounds")
    run_parser.add_argument("-j", "--jobs", type=int, default=4, help="RooFit NumCPU for fit and corrected-yield variations")

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate completed systematic source variations")
    evaluate_parser.add_argument("--sources", nargs="*", default=None, help="Specific source names to evaluate")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_paths = [Path(path) for path in (args.config or [DEFAULT_CONFIG_DIR])]
    config = load_variation_configs(config_paths)
    registry = SystematicRegistry()
    for source in config.sources:
        registry.register(source)

    if args.command == "list":
        _print_sources(config.sources)
        return

    if args.command == "run":
        _run_sources(args, registry)
        return

    if args.command == "evaluate":
        _evaluate_sources(args, registry)
        return

    raise RuntimeError(f"Unhandled command {args.command!r}")


def _print_sources(sources) -> None:
    print("Configured systematic sources:")
    if not sources:
        print("  (none)")
        return
    for source in sources:
        state = "enabled" if source.enabled else "disabled"
        print(
            f"  {source.name}: {state}, category={source.category}, "
            f"rerun_from={source.rerun_from}, method={source.evaluation_method}, "
            f"variations={len(source.variations)}"
        )


def _run_sources(args: argparse.Namespace, registry: SystematicRegistry) -> None:
    requested = args.sources or registry.list_sources()
    output_dir = Path(args.output_dir)
    nominal_dir = Path(args.nominal_dir)
    yield_samples = _parse_csv(args.yield_samples)
    for source_name in requested:
        source = registry.get(source_name)
        if not source.enabled:
            print(f"[skip] {source.name}: disabled")
            continue
        if source.rerun_from == "fit":
            if not args.dry_run and not args.fit_input:
                raise ValueError(f"{source.name}: --fit-input is required for fit variations")
            if args.fit_input:
                registry.set_runner(
                    source.name,
                    partial(
                        run_fit_variation,
                        input_file=args.fit_input,
                        output_dir=output_dir,
                        tree_name=args.fit_tree_name,
                        dataset=args.dataset,
                        weight_branch=args.fit_weight_branch,
                        jobs=args.jobs,
                        weighted_error_mode=args.weighted_error_mode,
                        force=args.force,
                    ),
                )
        elif source.rerun_from == "efficiency_extraction":
            if not args.dry_run:
                _require_arg(source.name, args.eff_input_manifest, "--eff-input-manifest")
                _require_arg(source.name, args.data_input, "--data-input")
                _require_arg(source.name, args.nominal_efficiency_dir, "--nominal-efficiency-dir")
            if args.eff_input_manifest and args.data_input and args.nominal_efficiency_dir:
                registry.set_runner(
                    source.name,
                    partial(
                        run_efficiency_config_variation,
                        input_manifest=args.eff_input_manifest,
                        data_input_file=args.data_input,
                        nominal_efficiency_dir=args.nominal_efficiency_dir,
                        output_dir=output_dir,
                        sample=args.eff_sample,
                        samples=yield_samples,
                        nominal_sample=args.nominal_sample,
                        tree_path=args.tree_path,
                        backend=args.efficiency_backend,
                        step_size=args.step_size,
                        event_end_step=args.event_end_step,
                        correction_mode=args.correction_mode,
                        n_min_fine=args.n_min_fine,
                        n_min_coarse=args.n_min_coarse,
                        jobs=args.jobs,
                        max_files=args.max_files,
                        force=args.force,
                    ),
                )
        elif source.category == "mc_stat":
            mc_stat_mode = args.mc_stat_mode or str(source.nominal.get("mode", "toy"))
            if not args.dry_run:
                if mc_stat_mode == "analytic":
                    _require_arg(source.name, args.nominal_yield_json, "--nominal-yield-json")
                else:
                    _require_arg(source.name, args.data_input, "--data-input")
                    _require_arg(source.name, args.nominal_efficiency_dir, "--nominal-efficiency-dir")
            if args.dry_run or (
                (mc_stat_mode == "analytic" and args.nominal_yield_json)
                or (mc_stat_mode == "toy" and args.data_input and args.nominal_efficiency_dir)
            ):
                registry.set_runner(
                    source.name,
                    partial(
                        run_mc_stat_variation,
                        output_dir=output_dir,
                        mode=mc_stat_mode,
                        nominal_yield_json=args.nominal_yield_json,
                        data_input_file=args.data_input,
                        nominal_efficiency_dir=args.nominal_efficiency_dir,
                        samples=yield_samples,
                        nominal_sample=args.nominal_sample,
                        correction_mode=args.correction_mode,
                        n_min_fine=args.n_min_fine,
                        n_min_coarse=args.n_min_coarse,
                        jobs=args.jobs,
                        n_toys=args.mc_stat_toys,
                        seed=args.mc_stat_seed,
                        clip=tuple(args.mc_stat_clip) if args.mc_stat_clip is not None else None,
                        force=args.force,
                    ),
                )
        if not args.dry_run:
            print(f"[run] {source.name}: {source.category}, rerun_from={source.rerun_from}")
            results = registry.run(
                source,
                output_dir=output_dir,
                nominal_dir=nominal_dir,
                dry_run=False,
                force=args.force,
                max_workers=args.max_workers,
            )
            for result in results:
                print(
                    f"  - {result.variation}: {result.status}, "
                    f"value={result.target_value:.6g}, manifest={result.manifest_path}"
                )
            continue
        print(f"[dry-run] {source.name}: {source.category}, rerun_from={source.rerun_from}")
        print(f"  config_hash={hash_config(source)}")
        results = registry.run(
            source,
            output_dir=output_dir,
            nominal_dir=nominal_dir,
            dry_run=True,
            force=args.force,
            max_workers=args.max_workers,
        )
        for result in results:
            run_hash = result.artifacts["run_hash"].name
            print(f"  - {result.variation}: manifest={result.manifest_path} hash={run_hash}")


def _parse_csv(raw: str) -> tuple[str, ...]:
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not values:
        raise ValueError("--yield-samples must contain at least one sample")
    return values


def _require_arg(source_name: str, value: str | None, option: str) -> None:
    if not value:
        raise ValueError(f"{source_name}: {option} is required for efficiency-selection variations")


def _evaluate_sources(args: argparse.Namespace, registry: SystematicRegistry) -> None:
    requested = args.sources or registry.list_sources()
    output_dir = Path(args.output_dir)
    for source_name in requested:
        source = registry.get(source_name)
        if not source.enabled:
            print(f"[skip] {source.name}: disabled")
            continue
        results = []
        for variation in source.variations:
            result_path = output_dir / "variations" / source.name / variation.name / "result.json"
            if not result_path.exists():
                print(f"[skip] {source.name}.{variation.name}: missing {result_path}")
                continue
            results.append(load_variation_result(result_path))
        if not results:
            print(f"[skip] {source.name}: no completed results")
            continue
        evaluated = evaluate_source(source, results)
        output_path = output_dir / "evaluated" / f"{source.name}.json"
        write_evaluated_source(evaluated, output_path)
        print(
            f"[evaluate] {source.name}: status={evaluated.status}, "
            f"+{evaluated.delta_up:.6g}/-{evaluated.delta_down:.6g}, wrote {output_path}"
        )


if __name__ == "__main__":
    main()

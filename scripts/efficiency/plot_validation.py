#!/usr/bin/env python3
"""Generate selected JJP validation figures through the Make dependency graph."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
PRIMARY = Path.home() / "JpsiJpsiPhi/analysis/Efficiency/NtupleAnalyzer"
SOURCES = PRIMARY if (PRIMARY / "efficiency_maps_cumulative_20261022").exists() else REPO
PLOTS = {
    "stepwise": "plots-stepwise",
    "closure": "plots-closure",
    "factorization": "plots-factorization",
    "angular": "plots-angular",
    "phi-origin": "plots-phi-origin",
    "phi-ctau": "plots-phi-ctau",
    "phi-gen": "plots-phi-gen",
}
SAMPLES = ("JJP_DPS1", "JJP_DPS2_CS", "JJP_DPS2_G", "JJP_SPS_CS", "JJP_SPS_G", "JJP_TPS")


def parse_plots(raw: list[str]) -> list[str]:
    names = [name.strip() for arg in raw for name in arg.split(",") if name.strip()]
    unknown = [name for name in names if name not in PLOTS and name != "all"]
    if unknown:
        raise ValueError(f"Unknown plot type: {', '.join(unknown)}")
    if "all" in names:
        return list(PLOTS)
    return list(dict.fromkeys(names))


def invalidate_incomplete_stepwise(root: Path) -> None:
    """Make's manifest target is valid only while all listed plot files exist."""
    aggregate = root / "derived_manifest.json"
    if not aggregate.exists():
        return
    try:
        for sample in SAMPLES:
            derived = root / sample / "derived"
            outputs = json.loads((derived / "manifest.json").read_text())["outputs"]
            plot_paths = [value for group in outputs.values() if isinstance(group, dict)
                          for value in group.values() if isinstance(value, str) and value.endswith(".png")]
            if not plot_paths or any(not (derived / relative).exists() for relative in plot_paths):
                aggregate.unlink()
                return
    except (OSError, KeyError, ValueError, TypeError):
        aggregate.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plots", nargs="+", default=["stepwise"],
                        help="Comma-separated selection: " + ", ".join(PLOTS) + ", all")
    parser.add_argument("--merged-dir", type=Path, default=SOURCES / "efficiency_maps_cumulative_20261022/merged")
    parser.add_argument("--derived-dir", type=Path, default=SOURCES / "efficiency_maps_cumulative_20261022/derived")
    parser.add_argument("--angular-cache", type=Path, default=SOURCES / ".claude/worktrees/sps-cs-angular/diagnostics/sps_cs_angular_20261019/outputs_helicity_corrected_20261019")
    parser.add_argument("--phi-cache", type=Path, default=SOURCES / "diagnostics/phi_ctau_20261022")
    parser.add_argument("--data-root", type=Path, default=SOURCES / "../jjp_data_selected.root")
    parser.add_argument("--old-mc-dir", type=Path, default=SOURCES / "../../../MC_samples/selected-merged-v3")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--closure-samples", nargs="+", default=["JJP_DPS1", "JJP_SPS_CS"])
    parser.add_argument("--with-cumulative-plots", action="store_true")
    parser.add_argument("--with-uncertainty-plots", action="store_true")
    args = parser.parse_args(argv)
    try:
        selected = parse_plots(args.plots)
    except ValueError as exc:
        parser.error(str(exc))
    if not selected:
        parser.error("--plots needs at least one plot type")
    if (args.with_cumulative_plots or args.with_uncertainty_plots) and "stepwise" not in selected:
        parser.error("legacy plot switches require stepwise or all")
    output = args.output_dir or (REPO / ("validation_plots_" + datetime.now(
        ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S")))
    output = Path(output).expanduser().resolve()
    mode = "_".join(part for part, enabled in (
        ("cumulative", args.with_cumulative_plots),
        ("uncertainty", args.with_uncertainty_plots)) if enabled) or "default"
    flags = " ".join(flag for flag, enabled in (
        ("--with-cumulative-plots", args.with_cumulative_plots),
        ("--with-uncertainty-plots", args.with_uncertainty_plots)) if enabled)
    assignments = {
        "MERGED_DIR": args.merged_dir,
        "DERIVED_DIR": args.derived_dir,
        "ANGULAR_CACHE": args.angular_cache,
        "PHI_CACHE": args.phi_cache,
        "DATA_ROOT": args.data_root,
        "OLD_MC_DIR": args.old_mc_dir,
        "OUTPUT_DIR": output,
        "CLOSURE_SAMPLES": " ".join(args.closure_samples),
        "PLOT_MODE": mode,
        "PLOT_FLAGS": flags,
    }
    if "stepwise" in selected:
        invalidate_incomplete_stepwise(output / "stepwise" / mode)
    command = ["make", "-C", str(REPO), "-f", "Makefile.validation",
               *(f"{key}={value}" for key, value in assignments.items()),
               *(PLOTS[name] for name in selected)]
    subprocess.run(command, check=True)
    expected = {
        "stepwise": output / "stepwise" / mode / "derived_manifest.json",
        "closure": output / "closure/closure_comparison.png",
        "factorization": output / "factorization/direct_over_product.png",
        "angular": output / "angular/plots/angular_summary.json",
        "phi-origin": output / "phi/origin_evidence_ctau_shapes.png",
        "phi-ctau": output / "phi/tail_model_sensitivity.png",
        "phi-gen": output / "phi/phi_abs_y_counts_and_shapes.png",
    }
    missing = [str(expected[name]) for name in selected if not expected[name].exists()]
    if missing:
        raise RuntimeError(f"Make completed without expected outputs: {missing}")
    manifest = {
        "plots": selected,
        "mode": mode,
        "inputs": {key: str(value) for key, value in assignments.items() if key not in {"OUTPUT_DIR", "PLOT_FLAGS"}},
        "outputs": {name: str(expected[name].relative_to(output)) for name in selected},
        "population_notes": {
            "stepwise_closure_factorization": "six-sample merged efficiency workflow; closure defaults to DPS1 and SPS_CS",
            "angular_phi_origin": "five historical selected MC samples; phi origin requires full GEN system matching",
            "phi_ctau": "selected data, beamspot-referenced ctau",
            "phi_gen": "six newer workflow-target GEN samples",
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "validation_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Validation figures: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Stage 1: validate one observable at a time. Stage 2: fit templates of adaptive cell counts."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.templates.fit_correlation_components import make_demo, run, write_json


def default_observables():
    axes = {}
    for suffix, pair, label in [("jj", "jpsi1_jpsi2", r"J/\psi_1,J/\psi_2"),
                                 ("j1phi", "jpsi1_phi", r"J/\psi_1,\phi"),
                                 ("j2phi", "jpsi2_phi", r"J/\psi_2,\phi")]:
        for prefix, variable, edges, title in [
            ("dphi", "abs_dphi", [0, .5, 1, 1.5, 2, 2.5, np.pi], r"|\Delta\phi|"),
            ("dy", "abs_dy", [0, .5, 1, 1.5, 2, 3, 5], r"|\Delta y|"),
            ("dr", "delta_r", [0, .8, 1.6, 2.4, 3.2, 4, 6], r"\Delta R_{\eta}")]:
            axes[f"{prefix}_{suffix}"] = {"variable": variable, "pair": pair,
                "edges": edges, "flow": "fold", "label": f"${title}({label})$"}
    for key, variable, system, edges, label in [
        ("m_jj", "mass", "jpsi1_jpsi2", [6, 10, 15, 20, 30, 45, 80], r"$M(J/\psi_1,J/\psi_2)$ [GeV]"),
        ("m_j1phi", "mass", "jpsi1_phi", [4, 6, 9, 13, 20, 30, 60], r"$M(J/\psi_1,\phi)$ [GeV]"),
        ("m_j2phi", "mass", "jpsi2_phi", [4, 6, 9, 13, 20, 30, 60], r"$M(J/\psi_2,\phi)$ [GeV]"),
        ("pt_jj", "pt", "jpsi1_jpsi2", [0, 4, 8, 14, 22, 35, 70], r"$p_T(J/\psi_1+J/\psi_2)$ [GeV]"),
        ("m_jjp", "mass", "jjp", [7, 15, 22, 30, 45, 65, 120], r"$M(J/\psi_1,J/\psi_2,\phi)$ [GeV]"),
        ("pt_jjp", "pt", "jjp", [0, 5, 10, 18, 28, 90], r"$p_T(J/\psi_1+J/\psi_2+\phi)$ [GeV]"),
        ("sumpt_jjp", "sum_pt", "jjp", [0, 22, 28, 35, 43, 60], r"$\sum p_T$ [GeV]"),
        ("absy_jjp", "abs_y", "jjp", [0, .3, .6, .9, 1.2, 1.8, 3], r"$|y(J/\psi_1+J/\psi_2+\phi)|$"),
        ("sumdr2", "sum_delta_r2", "jjp", [0, 4, 8, 14, 22, 35, 70], r"$\sum_{a<b}\Delta R_{ab}^{2}$"),
        ("sumdry2", "sum_delta_r_y2", "jjp", [0, 4, 8, 14, 22, 35, 70], r"$\sum_{a<b}(\Delta y_{ab}^{2}+\Delta\phi_{ab}^{2})$")]:
        axes[key] = {"variable": variable, "system": system, "edges": edges,
                     "flow": "fold", "label": label}
    return axes


DEFAULT_CELL_TEMPLATE_FITS = {
    "angles_2vars": ["dphi_jj", "dy_jj"],
    "geometry_3vars": ["dphi_jj", "dy_jj", "sumdr2"],
    "mass_pt_3vars": ["m_jj", "pt_jj", "m_jjp"],
    "threebody_4vars": ["m_jjp", "pt_jjp", "absy_jjp", "sumdr2"],
    "combined_9vars": ["dphi_jj", "dy_jj", "m_jj", "m_j1phi", "m_j2phi",
                     "pt_jj", "m_jjp", "pt_jjp", "sumdr2"],
}


def comparison_report(root, stages):
    rows = []
    for stage, manifest in stages.items():
        for name, entry in manifest.items():
            if entry["status"] != "passed":
                continue
            result = json.loads((root / stage / entry.get("directory", name) / "result.json").read_text())
            for k, component in enumerate(result["components"]):
                rows.append({"stage": stage, "fit": name, "component": component,
                    "fraction": result["fractions"][k], "error": result["fraction_errors_total"][k],
                    "chi2": result["chi2"], "ndof": result["ndof_nominal"],
                    "condition_number": result["condition_number"],
                    "boundary": result["parameters_at_limit"],
                    "mc_validation_passed": result["mc_validation_passed"]})
    if not rows:
        return
    with (root / "comparison.csv").open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    # A common injected mixture permits a fair expected-precision comparison.
    # These are planning estimates, not fits to the observed data points.
    precision = {}
    for stage, manifest in stages.items():
        for name, entry in manifest.items():
            if entry["status"] != "passed":
                continue
            with np.load(root / stage / entry.get("directory", name) / "fit_inputs.npz") as inputs:
                matrix = inputs["templates"]
            probabilities = np.ones(matrix.shape[1]) / matrix.shape[1]
            expected = 2000 * matrix @ probabilities
            info = matrix.T @ np.linalg.solve(np.diag(np.maximum(expected, 1.)), matrix)
            cov = np.linalg.inv(info)
            jac = (np.eye(len(probabilities)) - probabilities[:, None]) / 2000
            precision[f"{stage}/{name}"] = np.sqrt(np.diag(jac @ cov @ jac.T)).tolist()
    write_json(root / "expected_precision.json", {
        "description": "2000 selected signals, equal fractions, fixed templates, Poisson signal only; ignores mass backgrounds and MC uncertainty",
        "fraction_errors": precision})
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import mplhep as hep
    hep.style.use(hep.style.CMS)
    fig, ax = plt.subplots(figsize=(11, max(7, len(precision)*.34)))
    yy = np.arange(len(precision))
    components = list(dict.fromkeys(r["component"] for r in rows))
    values = np.array(list(precision.values()))
    for k, name in enumerate(components):
        ax.plot(values[:, k], yy, "o", label=name)
    ax.set_yticks(yy, list(precision))
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.tick_params(axis="y", labelsize=11)
    ax.set_xlabel("Expected uncertainty on component fraction", fontsize=17)
    ax.legend(fontsize=13, loc="lower right")
    hep.cms.label("Planning estimate", data=False, ax=ax, loc=0, rlabel="")
    fig.subplots_adjust(left=.36, right=.96, bottom=.13, top=.9)
    fig.savefig(root / "expected_precision.pdf")
    fig.savefig(root / "expected_precision.png", dpi=150)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    source = ap.add_mutually_exclusive_group()
    source.add_argument("--config", type=Path, help="Existing input config; optional study_observables/cell_template_fits")
    source.add_argument("--demo", action="store_true")
    ap.add_argument("--stage", choices=["single", "cells", "all"], default="all")
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--mc-bootstrap", type=int, default=50)
    ap.add_argument("--data-bootstrap", type=int, default=0)
    ap.add_argument("--validation-toys", type=int, default=10)
    ap.add_argument("--entry-stop", type=int)
    ap.add_argument("--max-cells", type=int, default=10)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--only", help="Comma-separated single-observable names for a focused new study")
    ap.add_argument("--retry-failed", action="store_true", help="Append fresh attempts for failed single fits")
    args = ap.parse_args()
    if args.validation_toys < 2 or (args.mc_bootstrap and args.mc_bootstrap < 30) or args.data_bootstrap < 0:
        ap.error("Use at least two validation toys; MC bootstrap must be zero or >=30; data bootstrap must be nonnegative")
    root = args.output_dir
    if args.retry_failed and args.stage != "single":
        ap.error("--retry-failed requires --stage single")
    if args.stage == "cells" or args.retry_failed:
        config = json.loads((root / "study_configuration.json").read_text())
        if args.demo or (args.config and not args.retry_failed):
            ap.error("Cell-template stage uses the saved study configuration; omit --demo/--config")
        if args.only and not args.retry_failed:
            ap.error("Cell-template stage uses the saved observable list; omit --only")
        if args.retry_failed and args.config:
            revised = json.loads(args.config.read_text())
            if any(revised[key] != config[key] for key in ("data", "components")):
                ap.error("Retries must use the same data and MC inputs")
            write_json(root / "configuration_before_retry.json", config)
            config = revised
            write_json(root / "study_configuration.json", config)
        saved = json.loads((root / "run_settings.json").read_text())
        if args.entry_stop != saved["entry_stop"] or args.seed != saved["seed"]:
            ap.error("Use the same --entry-stop and --seed as the single-variable stage")
    else:
        if not args.demo and not args.config:
            ap.error("Choose --demo or --config for the single-variable stage")
        root.mkdir(parents=True, exist_ok=False)
        config = make_demo(root / "inputs", args.seed, multivariate=True) if args.demo else json.loads(args.config.read_text())
        config.setdefault("study_observables", default_observables())
        config.setdefault("cell_template_fits", DEFAULT_CELL_TEMPLATE_FITS)
        if args.only:
            chosen = args.only.split(",")
            config["study_observables"] = {name: config["study_observables"][name] for name in chosen}
        write_json(root / "study_configuration.json", config)
        write_json(root / "run_settings.json", {"entry_stop": args.entry_stop, "seed": args.seed})
    axes = config.get("study_observables", default_observables())
    combinations = config.get("cell_template_fits", DEFAULT_CELL_TEMPLATE_FITS)
    if args.retry_failed:
        config["study_observables"], config["cell_template_fits"] = axes, combinations
        write_json(root / "study_configuration.json", config)
    base = {key: config[key] for key in ("data", "components", "toy", "jpsi_background") if key in config}
    base["validation"] = {"holdout_fraction": .25, "event_yield": 2000, "toys": args.validation_toys}
    base["adaptive_binning"] = {"training_fraction": .35, "max_cells": args.max_cells, "min_mc_effective": 40}
    stages = {}

    def execute(stage, jobs, resume=None):
        manifest = {} if resume is None else dict(resume)
        (root / stage).mkdir(exist_ok=resume is not None)
        for name, observables in jobs.items():
            print(f"[{stage}] {name}", flush=True)
            cfg = dict(base)
            cfg["observables"] = observables
            directory = name
            attempt = 1
            while (root / stage / directory).exists():
                attempt += 1
                directory = f"{name}_attempt{attempt}"
            try:
                result = run(cfg, root / stage / directory, args.data_bootstrap, args.mc_bootstrap,
                             args.entry_stop, args.seed)
                manifest[name] = {"status": "passed", "boundary": result["parameters_at_limit"], "directory": directory}
            except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                manifest[name] = {"status": "failed", "reason": str(exc), "directory": directory}
                print(f"[{stage}] {name}: {exc}", flush=True)
            write_json(root / f"{stage}_summary.json", manifest)
        return manifest

    if args.stage in ("single", "all"):
        resume = json.loads((root / "single_summary.json").read_text()) if args.retry_failed else None
        jobs = {name: [axis] for name, axis in axes.items()
                if resume is None or resume.get(name, {}).get("status") != "passed"}
        if args.retry_failed and args.only:
            jobs = {name: values for name, values in jobs.items() if name in args.only.split(",")}
        stages["single"] = execute("single", jobs, resume)
    else:
        stages["single"] = json.loads((root / "single_summary.json").read_text())
    if args.stage in ("cells", "all"):
        jobs = {}
        skipped = {}
        for name, variables in combinations.items():
            bad = [v for v in variables if stages["single"].get(v, {}).get("status") != "passed"]
            if bad:
                skipped[name] = {"status": "skipped", "reason": f"Single-variable checks failed: {bad}"}
            else:
                jobs[name] = [axes[v] for v in variables]
        stages["cells"] = execute("cells", jobs)
        stages["cells"].update(skipped)
        write_json(root / "cells_summary.json", stages["cells"])
    if "cells" not in stages and (root / "cells_summary.json").exists():
        stages["cells"] = json.loads((root / "cells_summary.json").read_text())
    comparison_report(root, stages)
    print(json.dumps(stages, indent=2), flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Fit a fixed Cartesian 3x3 correlation template to selected JJP data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.templates.fit_correlation_components import (
    fit_templates,
    make_template,
    mass_fit_yields,
    read_candidates,
    write_json,
)
from scripts.templates.multivariate import validate_templates
from scripts.templates.run_template_study import default_observables


DEFAULT_COMPONENTS = ("DPS1", "DPS2_CS", "SPS_CS")
SPLIT_FRACTIONS = {"training": 0.40, "development": 0.15,
                   "templates": 0.25, "final_validation": 0.20}


def cartesian_bin_indices(x, y, x_edges, y_edges):
    """Flatten a 2D Cartesian grid as b = nx * i + j, including final edges."""
    x_edges = np.asarray(x_edges, dtype=float)
    y_edges = np.asarray(y_edges, dtype=float)
    if (np.any(np.diff(x_edges) <= 0) or np.any(np.diff(y_edges) <= 0)
            or len(x_edges) < 2 or len(y_edges) < 2):
        raise ValueError("Grid edges must be strictly increasing")
    ix = np.searchsorted(x_edges, x, side="right") - 1
    iy = np.searchsorted(y_edges, y, side="right") - 1
    ix = np.clip(ix, 0, len(x_edges) - 2)
    iy = np.clip(iy, 0, len(y_edges) - 2)
    return ix * (len(y_edges) - 1) + iy


def split_indices(size, rng):
    if size < 1000:
        raise ValueError(f"Need at least 1000 selected rows for the four-way split; got {size}")
    order = rng.permutation(size)
    counts = [int(size * SPLIT_FRACTIONS[key]) for key in
              ("training", "development", "templates")]
    boundaries = np.cumsum([0, *counts, size])
    return {key: order[boundaries[i]:boundaries[i + 1]] for i, key in enumerate(
        ("training", "development", "templates", "final_validation"))}


def subset(sample, indices):
    return {key: (value[indices] if isinstance(value, np.ndarray) and value.ndim > 0
                  and len(value) == len(sample["x"]) else value)
            for key, value in sample.items()}


def encode_grid(sample, x_edges, y_edges):
    flat = cartesian_bin_indices(sample["coordinates"][:, 0], sample["coordinates"][:, 1],
                                 x_edges, y_edges)
    sample["grid_i"] = flat // (len(y_edges) - 1)
    sample["grid_j"] = flat % (len(y_edges) - 1)
    sample["x"] = flat.astype(float) + .5


def run(config, output, *, x_axis, y_axis, x_edges, y_edges,
        seed=12345, toys=50, event_yield=2000):
    output.mkdir(parents=True, exist_ok=False)
    if set(config["components"]) != set(DEFAULT_COMPONENTS):
        raise ValueError(f"This runner requires exactly {DEFAULT_COMPONENTS}")
    if config["data"].get("weight"):
        raise ValueError("Data mass fits must be unweighted")
    axes = default_observables()
    for name in (x_axis, y_axis):
        if name not in axes:
            raise ValueError(f"Unknown axis {name}; choose from {sorted(axes)}")
    x_spec, y_spec = dict(axes[x_axis]), dict(axes[y_axis])
    x_spec["edges"], y_spec["edges"] = list(x_edges), list(y_edges)
    x_spec["flow"] = y_spec["flow"] = "fold"
    x_edges, y_edges = np.asarray(x_edges, float), np.asarray(y_edges, float)
    if len(x_edges) != 4 or len(y_edges) != 4:
        raise ValueError("The baseline grid requires exactly three intervals per axis")

    data = read_candidates(config["data"], [x_spec, y_spec])
    mc_all = {name: read_candidates(config["components"][name], [x_spec, y_spec])
              for name in config["components"]}
    rng = np.random.default_rng(seed)
    split_samples = {}
    split_manifest = {}
    for name, sample in mc_all.items():
        encode_grid(sample, x_edges, y_edges)
        assignments = split_indices(len(sample["x"]), rng)
        split_samples[name] = {part: subset(sample, indices)
                               for part, indices in assignments.items()}
        split_manifest[name] = {
            part: sample["row_index"][indices].astype(int).tolist()
            for part, indices in assignments.items()
        }
    encode_grid(data, x_edges, y_edges)

    template_samples = {name: parts["templates"] for name, parts in split_samples.items()}
    validation_samples = {name: parts["final_validation"] for name, parts in split_samples.items()}
    cell_edges = np.arange(10, dtype=float)
    validation = validate_templates(template_samples, validation_samples, cell_edges,
                                    make_template, rng, event_yield, toys)
    write_json(output / "mc_validation.json", validation)

    data_yields, data_cov, mass_diagnostics = mass_fit_yields(
        data, cell_edges, output, config.get("jpsi_background", "exponential"))
    template_shapes, template_info = [], {}
    for name, sample in template_samples.items():
        shape, info = make_template(sample, cell_edges)
        template_shapes.append(shape)
        template_info[name] = info
    templates = np.column_stack(template_shapes)
    fit = fit_templates(data_yields, data_cov, templates, profile=True)
    fit.update({
        "components": list(template_samples),
        "fit_method": "Cartesian 3x3 binned 2D template fit",
        "template_coordinate": "flattened bin index b = 3*i + j",
        "axes": [x_spec, y_spec],
        "grid_edges": {"x": x_edges.tolist(), "y": y_edges.tolist()},
        "mc_split_fractions": SPLIT_FRACTIONS,
        "mc_validation_passed": validation["passed"],
        "limitations": ["conditional on fixed inclusive mass shapes",
                        "MC validation uses signal-only conditional toys; not interval coverage"],
    })
    write_json(output / "configuration.json", {
        "input_config": config, "axes": [x_spec, y_spec], "seed": seed,
        "split_fractions": SPLIT_FRACTIONS, "toys": toys,
        "event_yield": event_yield,
    })
    write_json(output / "split_manifest.json", split_manifest)
    write_json(output / "templates.json", template_info)
    write_json(output / "mass_yields.json", mass_diagnostics)
    write_json(output / "result.json", fit)
    np.savez(output / "grid_templates.npz", x_edges=x_edges, y_edges=y_edges,
             templates=templates.reshape(3, 3, len(template_samples)),
             components=np.array(list(template_samples)))
    np.savez(output / "fit_inputs.npz", edges=cell_edges, signal=data_yields,
             covariance=data_cov, templates=templates,
             components=np.array(list(template_samples)))
    grid = []
    for i in range(3):
        for j in range(3):
            cell = i * 3 + j
            grid.append({"i": i, "j": j, "x_low": x_edges[i], "x_high": x_edges[i + 1],
                         "y_low": y_edges[j], "y_high": y_edges[j + 1],
                         "data_signal_yield": float(data_yields[cell]),
                         "data_signal_error": float(np.sqrt(data_cov[cell, cell])),
                         **{f"template_{name}": float(templates[cell, k])
                            for k, name in enumerate(template_samples)}})
    import csv
    with (output / "grid_bins.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(grid[0]))
        writer.writeheader()
        writer.writerows(grid)
    print(json.dumps(fit, indent=2), flush=True)
    return fit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/templates/jjp_legacy_local.example.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--x-axis", default="dphi_jj")
    parser.add_argument("--y-axis", default="dy_jj")
    parser.add_argument("--x-edges", type=float, nargs=4, default=[0, 1, 2, np.pi])
    parser.add_argument("--y-edges", type=float, nargs=4, default=[0, 1, 2, 5])
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--toys", type=int, default=50)
    parser.add_argument("--event-yield", type=int, default=2000)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    config["components"] = {name: config["components"][name] for name in DEFAULT_COMPONENTS}
    run(config, args.output_dir, x_axis=args.x_axis, y_axis=args.y_axis,
        x_edges=args.x_edges, y_edges=args.y_edges, seed=args.seed,
        toys=args.toys, event_yield=args.event_yield)


if __name__ == "__main__":
    main()

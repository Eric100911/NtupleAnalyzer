#!/usr/bin/env python3
"""Scratch runner for 3D JJP mass fits in signed phi_ctau categories.

This is intentionally separate from scripts/kinematics/fit_splot.py. It writes
fit diagnostics/workspaces only; it does not calculate or append sWeights.
Run under LCG 109a. No fit was run while preparing this file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import ROOT
import mplhep as hep
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from scripts.kinematics import fit_splot  # noqa: E402

MASS_BRANCHES = ("sel_Jpsi_1_mass", "sel_Jpsi_2_mass", "sel_Phi_mass")
CTAU_BRANCH = "sel_Phi_ctau"
CTAU_ERR_BRANCH = "sel_Phi_ctauErr"
SENTINELS = (-999999.0, -99999.0)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="Scalar selected-data parquet")
    p.add_argument("--output-dir", required=True, help="New scratch output directory")
    p.add_argument("--ctau-edges", nargs="+", type=float, default=None,
                   help="Frozen internal edges in cm; underflow/overflow retained as categories")
    p.add_argument("--pilot-count", type=int, default=2000,
                   help="Deterministic random sample of valid rows, capped at 2000")
    p.add_argument("--all-valid", action="store_true",
                   help="Use all valid rows in an approved full-data run")
    p.add_argument("--seed", type=int, default=1337, help="Pilot sample seed")
    p.add_argument("--workers", type=int, choices=(1,), default=1,
                   help="Fit worker count is fixed to one for this bounded runner")
    p.add_argument("--jpsi-background", choices=("exponential", "chebychev1"), default="exponential")
    p.add_argument("--shape-mode", choices=("float-all", "conditional", "mean-width-sensitivity"), default="float-all")
    p.add_argument("--dependence-check-approved", action="store_true",
                   help="Explicit acknowledgment required for fixed/shared-shape sensitivity modes")
    p.add_argument("--toy-closure-yields-json", default=None,
                   help="Optional JSON mapping all eight yield_sss/.../yield_bbb names to fixed toy truth yields")
    p.add_argument("--toy-closure-approved", action="store_true",
                   help="Explicit acknowledgment required to generate and fit a toy closure sample")
    p.add_argument("--mass-bins", type=int, default=40)
    p.add_argument("--pull-range", type=float, default=5.0)
    return p.parse_args()


def load_rows(path: str, pilot_count: int, seed: int, all_valid: bool = False) -> tuple[pd.DataFrame, dict[str, int]]:
    df = pd.read_parquet(path, columns=list(MASS_BRANCHES) + [CTAU_BRANCH, CTAU_ERR_BRANCH])
    original = len(df)
    valid = np.ones(original, dtype=bool)
    for col in list(MASS_BRANCHES) + [CTAU_BRANCH]:
        arr = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
        valid &= np.isfinite(arr)
        for sentinel in SENTINELS:
            valid &= arr != sentinel
    finite_ctau_mass = valid.copy()
    mass_ranges = ((2.9, 3.3), (2.9, 3.3), (0.99, 1.07))
    outside_by_mass: dict[str, int] = {}
    for col, (low, high) in zip(MASS_BRANCHES, mass_ranges):
        values = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
        outside_by_mass[col] = int(np.count_nonzero(
            finite_ctau_mass & ~((values >= low) & (values <= high))))
        valid &= (values >= low) & (values <= high)
    err = pd.to_numeric(df[CTAU_ERR_BRANCH], errors="coerce").to_numpy(dtype=float)
    err_ok = np.isfinite(err) & (err > 0)
    for sentinel in SENTINELS:
        err_ok &= err != sentinel
    counts = {
        "input_rows": int(original),
        "excluded_nonfinite_or_sentinel_mass_ctau": int(original - np.count_nonzero(valid)),
        "nonfinite_or_sentinel_mass_ctau_rows": int(original - np.count_nonzero(finite_ctau_mass)),
        "out_of_mass_fit_range_rows_by_branch": outside_by_mass,
        "valid_mass_ctau_rows": int(np.count_nonzero(valid)),
        "ctau_error_invalid_or_nonpositive": int(np.count_nonzero(finite_ctau_mass & ~err_ok)),
    }
    df = df.loc[valid].reset_index(drop=True)
    if not all_valid and (pilot_count < 1 or pilot_count > 2000):
        raise ValueError("--pilot-count must be an integer from 1 to 2000")
    if not all_valid and len(df) > pilot_count:
        df = df.sample(n=pilot_count, random_state=seed).sort_index().reset_index(drop=True)
    counts["rows_used"] = int(len(df))
    counts["ctau_error_valid_positive_used"] = int(np.count_nonzero(
        np.isfinite(pd.to_numeric(df[CTAU_ERR_BRANCH], errors="coerce").to_numpy(dtype=float))
        & (pd.to_numeric(df[CTAU_ERR_BRANCH], errors="coerce").to_numpy(dtype=float) > 0)
    ))
    return df, counts


def category_masks(ctau: np.ndarray, edges: list[float] | None) -> list[tuple[str, np.ndarray]]:
    if edges is None:
        return []
    if len(edges) < 2 or any(not math.isfinite(x) for x in edges) or any(a >= b for a, b in zip(edges, edges[1:])):
        raise ValueError("--ctau-edges must contain at least two strictly increasing finite values")
    masks = [(f"under_{edges[0]:g}", ctau < edges[0])]
    for lo, hi in zip(edges, edges[1:]):
        masks.append((f"bin_{lo:g}_{hi:g}", (ctau >= lo) & (ctau < hi)))
    masks.append((f"over_{edges[-1]:g}", ctau >= edges[-1]))
    return masks


def raw_mass_ctau_diagnostics(frame: pd.DataFrame) -> dict[str, Any]:
    """Unweighted raw mass/ctau ranges and correlations, with no component label."""
    out: dict[str, Any] = {"rows": int(len(frame)), "mass_ranges_GeV": {},
                           "pearson_mass_ctau": {}, "spearman_mass_ctau": {}}
    ctau = pd.to_numeric(frame[CTAU_BRANCH], errors="coerce")
    for branch in MASS_BRANCHES:
        mass = pd.to_numeric(frame[branch], errors="coerce")
        pair = pd.concat([mass.rename("mass"), ctau.rename("ctau")], axis=1).dropna()
        out["mass_ranges_GeV"][branch] = {
            "min": float(mass.min()), "max": float(mass.max()),
            "q01": float(mass.quantile(0.01)), "median": float(mass.median()),
            "q99": float(mass.quantile(0.99)),
        }
        out["pearson_mass_ctau"][branch] = float(pair.corr(method="pearson").iloc[0, 1])
        out["spearman_mass_ctau"][branch] = float(pair.corr(method="spearman").iloc[0, 1])
    return out


def build_data(frame: pd.DataFrame, label: str):
    model, obs, yields, signal_name, keepalive = fit_splot.build_jjp_model(
        max(1, len(frame)), mc_two_component=False, jpsi_background=ARGS.jpsi_background,
    )
    argset = ROOT.RooArgSet()
    for var in obs.values():
        argset.add(var)
    data = ROOT.RooDataSet(f"data_{label}", f"data_{label}", argset)
    for row in frame.itertuples(index=False, name=None):
        values = dict(zip(frame.columns, row))
        for branch, var in obs.items():
            var.setVal(float(values[branch]))
        data.add(argset)
    keepalive.append(data)
    return model, obs, yields, signal_name, data, keepalive


def parameter_records(model, data) -> list[dict[str, Any]]:
    params = model.getParameters(data)
    records = []
    for var in params:
        if not hasattr(var, "getVal"):
            continue
        lo = float(var.getMin()) if hasattr(var, "getMin") else None
        hi = float(var.getMax()) if hasattr(var, "getMax") else None
        value = float(var.getVal())
        scale = max(1e-6, 1e-3 * (hi - lo)) if lo is not None and hi is not None else 1e-6
        lower_distance = value - lo if lo is not None else math.inf
        upper_distance = hi - value if hi is not None else math.inf
        nearest = "lower" if lower_distance <= upper_distance else "upper"
        at_boundary = min(lower_distance, upper_distance) <= 1e-7
        near_boundary = min(lower_distance, upper_distance) <= scale
        error = float(var.getError()) if hasattr(var, "getError") else None
        records.append({"name": var.GetName(), "value": value, "error": error,
                        "constant": bool(var.isConstant()) if hasattr(var, "isConstant") else None,
                        "floating": not bool(var.isConstant()) if hasattr(var, "isConstant") else None,
                        "min": lo, "max": hi, "at_boundary": at_boundary,
                        "near_boundary_0p1pct_range": near_boundary,
                        "nearest_boundary": nearest if near_boundary else None,
                        "nearest_boundary_distance": float(min(lower_distance, upper_distance))})
    return records


def yield_covariance_records(result, yields) -> dict[str, dict[str, float | None]]:
    """Extract RooFit's covariance for the eight floating component yields."""
    final = result.floatParsFinal()
    indices = {final.at(i).GetName(): i for i in range(int(final.getSize()))}
    matrix = result.covarianceMatrix()
    return {
        left: {
            right: (float(matrix[indices[left]][indices[right]])
                    if left in indices and right in indices else None)
            for right in yields
        }
        for left in yields
    }


def apply_shape_seed(model, data, seed: dict[str, float], mode: str) -> None:
    for var in model.getParameters(data):
        name = var.GetName()
        if name.startswith("yield_") or name.startswith("sel_"):
            continue
        if name not in seed:
            continue
        var.setVal(float(seed[name]))
        if mode == "float-all":
            continue
        sensitivity_float = mode == "mean-width-sensitivity" and (name.endswith("_mean") or name.endswith("_sigma"))
        var.setConstant(not sensitivity_float)


def graph_xy(graph):
    xs, ys, exl, exh, eyl, eyh = [], [], [], [], [], []
    for i in range(int(graph.GetN())):
        x = float(graph.GetPointX(i))
        y = float(graph.GetPointY(i))
        xs.append(x); ys.append(y)
        exl.append(float(graph.GetErrorXlow(i)) if hasattr(graph, "GetErrorXlow") else 0.0)
        exh.append(float(graph.GetErrorXhigh(i)) if hasattr(graph, "GetErrorXhigh") else 0.0)
        eyl.append(float(graph.GetErrorYlow(i)) if hasattr(graph, "GetErrorYlow") else 0.0)
        eyh.append(float(graph.GetErrorYhigh(i)) if hasattr(graph, "GetErrorYhigh") else 0.0)
    return tuple(np.asarray(x) for x in (xs, ys, exl, exh, eyl, eyh))


def save_projection_plots(label, model, obs, data, out_dir, bins, pull_range):
    hep.style.use(hep.style.CMS)
    out_dir.mkdir(parents=True, exist_ok=True)
    names = list(obs)
    for name, var in obs.items():
        others = ROOT.RooArgSet()
        for other_name, other in obs.items():
            if other_name != name:
                others.add(other)
        frame = var.frame(ROOT.RooFit.Bins(bins))
        data.plotOn(frame, ROOT.RooFit.Name("data"))
        model.plotOn(frame, ROOT.RooFit.Name("model"), ROOT.RooFit.ProjWData(others, data))
        pull = frame.pullHist("data", "model")
        hist = frame.getHist("data")
        curve = frame.getCurve("model")
        dx, dy, dxl, dxh, dyl, dyh = graph_xy(hist)
        cx, cy, *_ = graph_xy(curve)
        px, py, *_ = graph_xy(pull)
        fig, (ax, pax) = plt.subplots(2, 1, figsize=(7.4, 7.0), sharex=True,
                                      gridspec_kw={"height_ratios": [3.3, 1], "hspace": 0.04})
        hep.cms.label("Work In Progress", data=True, loc=0, ax=ax, com=13.6)
        ax.errorbar(dx, dy, xerr=np.vstack([dxl, dxh]), yerr=np.vstack([dyl, dyh]),
                    fmt="o", color="black", markersize=3.5, label="Data")
        ax.plot(cx, cy, color="#d62728", lw=1.8, label="Total fit")
        ax.set_ylabel("Events / bin")
        ax.legend(frameon=False)
        pax.errorbar(px, py, fmt="o", color="black", markersize=3)
        pax.axhline(0, color="#d62728", lw=1)
        pax.set_ylim(-pull_range, pull_range)
        pax.set_ylabel("Pull")
        pax.set_xlabel({MASS_BRANCHES[0]: r"$m(J/\psi_1)$ [GeV]",
                        MASS_BRANCHES[1]: r"$m(J/\psi_2)$ [GeV]",
                        MASS_BRANCHES[2]: r"$m(K^+K^-)$ [GeV]"}.get(name, name))
        fig.savefig(out_dir / f"{label}_{name}_projection_pull.png", dpi=160, bbox_inches="tight")
        fig.savefig(out_dir / f"{label}_{name}_projection_pull.pdf", bbox_inches="tight")
        plt.close(fig)


def fit_one(frame, label: str, output_dir: Path, shape_seed: dict[str, float] | None,
            shape_mode: str, mass_bins: int, pull_range: float) -> dict[str, Any]:
    model, obs, yields, signal_name, data, keepalive = build_data(frame, label)
    if shape_seed is not None:
        apply_shape_seed(model, data, shape_seed, shape_mode)
    result = model.fitTo(data, ROOT.RooFit.Extended(True), ROOT.RooFit.Save(True),
                         ROOT.RooFit.NumCPU(1), ROOT.RooFit.Strategy(2), ROOT.RooFit.PrintLevel(-1))
    keepalive.append(result)
    params = parameter_records(model, data)
    yield_results = {name: {"value": float(var.getVal()), "error": float(var.getError()),
                            "min": float(var.getMin()), "max": float(var.getMax()),
                            "at_boundary": min(float(var.getVal()) - float(var.getMin()),
                                               float(var.getMax()) - float(var.getVal())) <= 1e-7,
                            "near_boundary_0p1pct_range": min(float(var.getVal()) - float(var.getMin()),
                                                              float(var.getMax()) - float(var.getVal())) <= max(
                                                                  1e-6, 1e-3 * (float(var.getMax()) - float(var.getMin()))) }
                     for name, var in yields.items()}

    output_dir.mkdir(parents=True, exist_ok=True)
    ws = ROOT.RooWorkspace(f"workspace_{label}", f"workspace_{label}")
    getattr(ws, "import")(model)
    getattr(ws, "import")(data)
    ws.saveSnapshot("fit_parameters", model.getParameters(data), True)
    fout = ROOT.TFile(str(output_dir / f"{label}_workspace.root"), "RECREATE")
    ws.Write("workspace")
    result.Write("fit_result")
    fout.Close()
    save_projection_plots(label, model, obs, data, output_dir / "plots", mass_bins, pull_range)
    payload = {
        "label": label,
        "rows": int(frame.shape[0]),
        "fit": {"status": int(result.status()), "covQual": int(result.covQual()),
                "EDM": float(result.edm()), "NLL": float(result.minNll()),
                "num_invalid_nll": int(result.numInvalidNLL()) if hasattr(result, "numInvalidNLL") else None},
        "signal_component": signal_name,
        "component_yields": yield_results,
        "component_yield_covariance": yield_covariance_records(result, yields),
        "shape_mode": shape_mode if shape_seed is not None else "unseeded-independent",
        "parameters": params,
        "workspace": f"{label}_workspace.root",
    }
    return payload


def run_toy_closure(truth_path: str, output_dir: Path, jpsi_background: str,
                    mass_bins: int, pull_range: float) -> dict[str, Any]:
    truth = json.loads(Path(truth_path).read_text())
    expected = {f"yield_{code}" for code in ("sss", "ssb", "sbs", "bss", "sbb", "bsb", "bbs", "bbb")}
    if set(truth) != expected or any(not math.isfinite(float(v)) or float(v) < 0 for v in truth.values()):
        raise ValueError(f"Toy truth JSON must contain exactly {sorted(expected)} with finite nonnegative values")
    truth_model, obs, yields, _, keepalive = fit_splot.build_jjp_model(
        max(1, int(sum(float(v) for v in truth.values()))), mc_two_component=False,
        jpsi_background=jpsi_background,
    )
    for name, var in yields.items():
        var.setVal(float(truth[name]))
        var.setConstant(True)
    obs_set = ROOT.RooArgSet()
    for var in obs.values():
        obs_set.add(var)
    toy = truth_model.generate(obs_set, ROOT.RooFit.Extended(True))
    keepalive.append(toy)
    records = []
    for i in range(int(toy.numEntries())):
        row = toy.get(i)
        records.append({name: float(row.getRealValue(name)) for name in obs})
    frame = pd.DataFrame.from_records(records, columns=list(obs))
    fitted = fit_one(frame, "toy_closure", output_dir, None, "float-all", mass_bins, pull_range)
    fitted_values = {entry["name"]: entry["value"] for entry in fitted["parameters"]}
    return {"truth_yields": {k: float(v) for k, v in truth.items()},
            "generated_rows": int(len(frame)), "fit": fitted,
            "yield_residuals": {k: fitted_values.get(k, math.nan) - float(v) for k, v in truth.items()}}


def main():
    global ARGS
    ARGS = parse_args()
    if ARGS.shape_mode != "float-all" and not ARGS.dependence_check_approved:
        raise SystemExit("Fixed/shared-shape sensitivity modes require --dependence-check-approved after reviewing mass-ctau dependence.")
    if ARGS.toy_closure_yields_json and not ARGS.toy_closure_approved:
        raise SystemExit("Toy closure requires --toy-closure-approved after fit specification approval.")
    out = Path(ARGS.output_dir)
    out.mkdir(parents=True, exist_ok=False)
    rows, excluded = load_rows(ARGS.input, ARGS.pilot_count, ARGS.seed, ARGS.all_valid)
    if rows.empty:
        raise SystemExit("No usable rows after finite/sentinel/mass-range filtering")
    inclusive = fit_one(rows, "inclusive", out / "inclusive", None, "float-all", ARGS.mass_bins, ARGS.pull_range)
    seed = {x["name"]: x["value"] for x in inclusive["parameters"]}
    ctau = pd.to_numeric(rows[CTAU_BRANCH], errors="coerce").to_numpy(dtype=float)
    categories = category_masks(ctau, ARGS.ctau_edges)
    results = {"input": str(Path(ARGS.input).resolve()), "output_dir": str(out.resolve()),
               "observable": CTAU_BRANCH, "display_scale_to_mm": 10.0,
               "ctau_error_branch": CTAU_ERR_BRANCH, "counts": excluded,
               "raw_mass_ctau_diagnostics": raw_mass_ctau_diagnostics(rows),
               "categories": [{"label": name, "rows": int(np.count_nonzero(mask)),
                               "ctau_low_inclusive": None, "ctau_high_exclusive": None}
                              for name, mask in categories],
               "inclusive_fit": inclusive, "category_fits": []}
    if ARGS.ctau_edges:
        edgevals = ARGS.ctau_edges
        for i, cat in enumerate(results["categories"]):
            if i == 0:
                cat["ctau_high_exclusive"] = edgevals[0]
            elif i == len(results["categories"]) - 1:
                cat["ctau_low_inclusive"] = edgevals[-1]
            else:
                cat["ctau_low_inclusive"] = edgevals[i - 1]
                cat["ctau_high_exclusive"] = edgevals[i]
    for (label, mask), info in zip(categories, results["categories"]):
        if int(np.count_nonzero(mask)) == 0:
            results["category_fits"].append({"label": label, "rows": 0, "status": "skipped_empty"})
            continue
        results["category_fits"].append(fit_one(rows.loc[mask].reset_index(drop=True), label,
                                               out / label, seed, ARGS.shape_mode,
                                               ARGS.mass_bins, ARGS.pull_range))
        info["raw_mass_ctau_diagnostics"] = raw_mass_ctau_diagnostics(rows.loc[mask].reset_index(drop=True))
    results["model"] = {"source": str(Path(fit_splot.__file__).resolve()),
                        "source_sha256": hashlib.sha256(Path(fit_splot.__file__).read_bytes()).hexdigest(),
                        "builder": "build_jjp_model", "jpsi_background": ARGS.jpsi_background,
                        "components": ["sss", "ssb", "sbs", "bss", "sbb", "bsb", "bbs", "bbb"],
                        "fit_workers": 1}
    if ARGS.toy_closure_yields_json:
        results["toy_closure"] = run_toy_closure(ARGS.toy_closure_yields_json, out / "toy_closure",
                                                  ARGS.jpsi_background, ARGS.mass_bins, ARGS.pull_range)
    (out / "fit_summary.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    print(f"Prepared fits complete: {out / 'fit_summary.json'}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Background subtraction of JJP angular distributions with per-bin mass fits.

Strategy
--------
1. Read the per-event angular table produced by compute_angles.py.
2. Build the standard JJP 3D model (dscb J/psi + exponential background,
   Voigtian phi + threshold background) and fit it once to all data,
   unweighted, with all shape parameters floating.
3. Fix every non-yield parameter to its global-fit value.
4. For each bin of an angular variable, fit the 8 component yields only.
   The signal yield of the bin is the local background-subtracted signal.
5. Save the global fit result, the per-bin yields, and (optionally) global
   sWeights for a cross-check.

This reproduces the binned-yield fit pattern used in
diagnostics/.../binned_yield/scripts/run_analysis.py.
"""
from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd
import ROOT

ROOT.gROOT.SetBatch(True)
ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.WARNING)
if hasattr(ROOT.RooRealVar, "enableSilentClipping"):
    ROOT.RooRealVar.enableSilentClipping(True)

# Import the production model builder from the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
import sys
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from fit_splot import build_jjp_model, initialize_yields_for_dataset, make_dataset  # noqa: E402

ANGLE_VARIABLES = OrderedDict([
    ("cos_theta_jpsi1", {"edges": np.linspace(-1.0, 1.0, 17), "label": r"$\cos\theta^{*}_{J/\psi_1}$"}),
    ("cos_theta_jpsi2", {"edges": np.linspace(-1.0, 1.0, 17), "label": r"$\cos\theta^{*}_{J/\psi_2}$"}),
    ("abs_cos_theta_phi", {"edges": np.linspace(0.0, 1.0, 11), "label": r"$|\cos\theta^{*}_{\phi}|$"}),
    ("delta_phi_jj", {"edges": np.linspace(0.0, np.pi, 13), "label": r"$\Delta\phi_{JJ}$"}),
])

MASS_BRANCHES = ["sel_Jpsi_1_mass", "sel_Jpsi_2_mass", "sel_Phi_mass"]


def build_tree(frame: pd.DataFrame, variables) -> ROOT.TTree:
    """Create an in-memory TTree with the mass branches + angular variables."""
    tree = ROOT.TTree("angdata", "angdata")
    buffers = {}
    for name in list(MASS_BRANCHES) + list(variables):
        buf = np.zeros(1, dtype=np.float64)
        buffers[name] = buf
        tree.Branch(name, buf, f"{name}/D")
    n = len(frame)
    values = {name: frame[name].to_numpy(dtype=np.float64) for name in buffers}
    for i in range(n):
        for name, buf in buffers.items():
            buf[0] = values[name][i]
        tree.Fill()
    return tree


def fit_info(result) -> dict:
    info = {
        "status": int(result.status()),
        "edm": float(result.edm()),
        "covQual": int(result.covQual()),
        "minNll": float(result.minNll()),
    }
    if hasattr(result, "numInvalidNLL"):
        info["numInvalidNLL"] = int(result.numInvalidNLL())
    return info


def do_fit(model, dataset, jobs: int = 4, allow_retry: bool = True):
    """Fit with Strategy(2); retry with Strategy(1) if the first fit is poor."""
    options = [
        ROOT.RooFit.Extended(True),
        ROOT.RooFit.Save(True),
        ROOT.RooFit.NumCPU(max(1, int(jobs))),
        ROOT.RooFit.Strategy(2),
        ROOT.RooFit.PrintLevel(-1),
    ]
    result = model.fitTo(dataset, *options)
    info = fit_info(result)
    used = "strategy2"
    if allow_retry and (info["status"] != 0 or info["edm"] > 1e-3 or info["covQual"] < 3):
        options_retry = [
            ROOT.RooFit.Extended(True),
            ROOT.RooFit.Save(True),
            ROOT.RooFit.NumCPU(max(1, int(jobs))),
            ROOT.RooFit.Strategy(1),
            ROOT.RooFit.PrintLevel(-1),
        ]
        result2 = model.fitTo(dataset, *options_retry)
        info2 = fit_info(result2)
        info2["first_pass"] = info
        return result2, info2, "strategy1_retry"
    return result, info, used


def iter_argset(argset):
    return list(argset)


def parameter_snapshot(model, dataset):
    snap = OrderedDict()
    params = model.getParameters(dataset)
    for var in iter_argset(params):
        name = var.GetName()
        if var.isConstant():
            snap[name] = {"value": float(var.getVal()), "constant": True}
        else:
            snap[name] = {
                "value": float(var.getVal()),
                "error": float(var.getError()),
                "constant": False,
            }
    return snap


def fix_shape_parameters(model, dataset, yield_names):
    params = model.getParameters(dataset)
    fixed = []
    for var in iter_argset(params):
        name = var.GetName()
        if name not in yield_names and not var.isConstant():
            var.setConstant(True)
            fixed.append(name)
    return fixed


def compute_sweights(data, model, yields):
    arglist = ROOT.RooArgList(*list(yields.values()))
    sdata = ROOT.RooStats.SPlot("sData", "sData", data, model, arglist)
    names = [f"{name}_sw" for name in yields]
    out = {name: np.empty(data.numEntries(), dtype=np.float64) for name in names}
    for i in range(data.numEntries()):
        row = data.get(i)
        for name in names:
            out[name][i] = row.getRealValue(name)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angles", required=True, help="Per-event angle parquet from compute_angles.py")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--variables", default=",".join(ANGLE_VARIABLES))
    ap.add_argument("--no-sweights", action="store_true")
    ap.add_argument("--global-only", action="store_true")
    args = ap.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    frame = pd.read_parquet(args.angles)
    n_events = len(frame)
    variables = [v.strip() for v in args.variables.split(",") if v.strip()]
    for var in variables:
        if var not in ANGLE_VARIABLES:
            raise SystemExit(f"Unknown variable {var!r}; choose from {list(ANGLE_VARIABLES)}")
        if frame[var].isna().any():
            raise SystemExit(f"Variable {var!r} has NaN entries")

    tree = build_tree(frame, variables)
    n_entries = int(tree.GetEntries())

    model, observables, yields, signal_yield_name, keepalive = build_jjp_model(
        n_entries, mc_two_component=False
    )
    keepalive.extend([tree])
    # Add the angular branches to the RooDataSet; the model ignores them but
    # they are needed for RooDataSet::reduce(Cut(...)).
    angle_vars = {}
    for var in variables:
        angle_vars[var] = ROOT.RooRealVar(var, var, float(frame[var].min()), float(frame[var].max()))
        observables[var] = angle_vars[var]

    data, weight_var = make_dataset(tree, observables)
    keepalive.extend([data])
    initialize_yields_for_dataset(yields, data.sumEntries(), "JJP", False)

    print(f"[global] fitting {n_entries} events with {len(yields)} components")
    result, info, used = do_fit(model, data, jobs=args.jobs)
    keepalive.append(result)
    global_yields = OrderedDict(
        (name, {"value": float(var.getVal()), "error": float(var.getError())})
        for name, var in yields.items()
    )
    print(f"[global] status={info['status']} edm={info['edm']:.3e} "
          f"covQual={info['covQual']} used={used} "
          f"yield_sss={global_yields[signal_yield_name]['value']:.1f} "
          f"+- {global_yields[signal_yield_name]['error']:.1f}")

    global_payload = {
        "input": args.angles,
        "n_events": n_entries,
        "fit": info,
        "fit_used": used,
        "yields": global_yields,
        "shape_parameters": parameter_snapshot(model, data),
    }
    with open(outdir / "global_fit.json", "w") as fh:
        json.dump(global_payload, fh, indent=1)

    if not args.no_sweights:
        print("[sweights] running global sPlot")
        sw = compute_sweights(data, model, yields)
        for name, values in sw.items():
            frame[name] = values
        sw_path = outdir / "data_with_sweights.parquet"
        frame.to_parquet(sw_path, index=False)
        print(f"[sweights] wrote {sw_path}")

    if args.global_only:
        return

    fixed = fix_shape_parameters(model, data, set(yields))
    print(f"[global] fixed {len(fixed)} shape parameters")

    global_signal = global_yields[signal_yield_name]["value"]
    for var in variables:
        edges = ANGLE_VARIABLES[var]["edges"]
        rows = []
        for ibin in range(len(edges) - 1):
            lo, hi = float(edges[ibin]), float(edges[ibin + 1])
            last = ibin == len(edges) - 2
            op = "<=" if last else "<"
            cut = f"({var} >= {lo!r}) && ({var} {op} {hi!r})"
            sub = data.reduce(ROOT.RooFit.Cut(cut))
            n_bin = int(sub.numEntries())
            if n_bin == 0:
                rows.append({"ibin": ibin, "lo": lo, "hi": hi, "n_events": 0})
                continue
            # Scale the global yields to this bin as the starting point.
            for name, yvar in yields.items():
                start = global_yields[name]["value"] * n_bin / max(n_events, 1)
                yvar.setVal(max(0.5, start))
            bin_result, bin_info, bin_used = do_fit(model, sub, jobs=args.jobs)
            entry = {
                "ibin": ibin,
                "lo": lo,
                "hi": hi,
                "n_events": n_bin,
                "fit": bin_info,
                "fit_used": bin_used,
            }
            for name, yvar in yields.items():
                entry[name] = float(yvar.getVal())
                entry[name + "_err"] = float(yvar.getError())
            signal_yield = entry[signal_yield_name]
            signal_err = entry[signal_yield_name + "_err"]
            entry["signal_yield"] = signal_yield
            entry["signal_yield_err"] = signal_err
            entry["signal_fraction"] = signal_yield / n_bin
            entry["signal_fraction_err"] = signal_err / n_bin
            rows.append(entry)
            print(f"[{var}] bin {ibin:2d} [{lo:+.3f},{hi:+.3f}] "
                  f"N={n_bin:5d} S={signal_yield:8.1f} +- {signal_err:6.1f} "
                  f"status={bin_info['status']} edm={bin_info['edm']:.1e} "
                  f"cov={bin_info['covQual']} {bin_used}")

        payload = {
            "input": args.angles,
            "variable": var,
            "label": ANGLE_VARIABLES[var]["label"],
            "edges": [float(e) for e in edges],
            "n_events": n_entries,
            "global_signal_yield": global_signal,
            "global_fit": info,
            "bins": rows,
        }
        with open(outdir / f"{var}.json", "w") as fh:
            json.dump(payload, fh, indent=1)
        flat = pd.DataFrame(rows)
        flat.to_csv(outdir / f"{var}.csv", index=False)
        print(f"[{var}] wrote {outdir / (var + '.json')}")

        # Reset the yields for the next variable.
        for name, yvar in yields.items():
            yvar.setVal(global_yields[name]["value"])


if __name__ == "__main__":
    main()

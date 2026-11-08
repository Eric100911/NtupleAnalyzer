#!/usr/bin/env python3
"""JJP: per-bin 3D mass fits followed by fits of RECO histogram templates.

Inputs must contain one selected, scalar candidate per independent event.
Multiple observables define adaptive cells. The component fit uses a 1D
histogram of cell indices with a Gaussian yield covariance.
See docs/Correlation_Template_Fit.md for the statistical assumptions and recipe.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import warnings

import numpy as np
import uproot
from iminuit import Minuit
from scipy.linalg import solve_triangular

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

OBJECTS = ("Jpsi_1", "Jpsi_2", "Phi")
MASS_NAMES = tuple(f"{obj}_mass" for obj in OBJECTS)
MASS_RANGES = ((2.9, 3.3), (2.9, 3.3), (0.99, 1.07))
PAIRS = {"jpsi1_jpsi2": (0, 1), "jpsi1_phi": (0, 2), "jpsi2_phi": (1, 2)}
SYSTEMS = {**{name: indices for name, indices in PAIRS.items()},
           "jpsi1": (0,), "jpsi2": (1,), "phi": (2,), "jjp": (0, 1, 2)}


def correlation_features(momentum, masses):
    """Features from pT-ordered (J/psi1, J/psi2, phi) four-vectors.

    momentum: (events, objects, xyz); masses: (events, objects), in GeV.
    delta_r uses eta; delta_r_y is the explicitly named rapidity alternative.
    """
    pt = np.hypot(momentum[:, :, 0], momentum[:, :, 1])
    phi = np.arctan2(momentum[:, :, 1], momentum[:, :, 0])
    rapidity = np.arcsinh(momentum[:, :, 2] / np.hypot(pt, masses))
    with np.errstate(divide="ignore", invalid="ignore"):
        eta = np.arcsinh(momentum[:, :, 2] / pt)
    energy = np.sqrt(np.sum(momentum**2, axis=2) + masses**2)
    features = {}
    dr2, dry2 = [], []
    for pair, (a, b) in PAIRS.items():
        delta = phi[:, a] - phi[:, b]
        dphi = np.abs(np.arctan2(np.sin(delta), np.cos(delta)))
        dy = np.abs(rapidity[:, a] - rapidity[:, b])
        deta = np.abs(eta[:, a] - eta[:, b])
        r2, ry2 = dphi**2 + deta**2, dphi**2 + dy**2
        for name, value in {"abs_dphi": dphi, "abs_dy": dy,
                            "delta_r": np.sqrt(r2), "delta_r_y": np.sqrt(ry2)}.items():
            features[(name, pair)] = value
        dr2.append(r2)
        dry2.append(ry2)
    for system, indices in SYSTEMS.items():
        p = momentum[:, indices, :].sum(axis=1)
        e = energy[:, indices].sum(axis=1)
        m = np.sqrt(np.maximum(e*e - np.sum(p*p, axis=1), 0))
        transverse = np.hypot(p[:, 0], p[:, 1])
        y = np.arcsinh(p[:, 2] / np.hypot(transverse, m))
        for name, value in {"mass": m, "pt": transverse, "abs_y": np.abs(y),
                            "sum_pt": pt[:, indices].sum(axis=1)}.items():
            features[(name, system)] = value
    features[("sum_delta_r2", "jjp")] = np.sum(dr2, axis=0)
    features[("sum_delta_r_y2", "jjp")] = np.sum(dry2, axis=0)
    features[("max_delta_r", "jjp")] = np.sqrt(np.max(dr2, axis=0))
    return features


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


def read_candidates(spec, observable, entry_stop=None, nominal_kinematics=False):
    """Read explicit schema; no implicit cuts, flattening, or GEN matching."""
    prefix = spec.get("prefix", "")
    fields = [f"{obj}_{field}" for obj in OBJECTS
              for field in ("mass", "px", "py", "pz")]
    weight_name = spec.get("weight")
    if weight_name:
        fields.append(weight_name)
    branches = [prefix + name if name != weight_name else name for name in fields]
    # Use direct local-file reads: LCG's default fsspec async source can stall.
    options = {} if "://" in spec["path"] else {
        "handler": uproot.source.file.MultithreadedFileSource, "num_workers": 1}
    with uproot.open(spec["path"], **options) as handle:
        arrays = handle[spec.get("tree", "X_data")].arrays(
            branches, cut=spec.get("cut"), library="np", entry_stop=entry_stop)
    values = {name: np.asarray(arrays[branch], dtype=float)
              for name, branch in zip(fields, branches)}
    if any(a.ndim != 1 for a in values.values()):
        raise ValueError("Use a scalar selected-candidate table, not raw candidate vectors")
    valid = np.ones(len(values[MASS_NAMES[0]]), dtype=bool)
    for a in values.values():
        valid &= np.isfinite(a)
    for name, (lo, hi) in zip(MASS_NAMES, MASS_RANGES):
        valid &= (values[name] >= lo) & (values[name] <= hi)
    momentum = np.stack([np.column_stack([values[f"{obj}_{key}"] for key in ("px", "py", "pz")])
                         for obj in OBJECTS], axis=1)
    masses = np.column_stack([values[n] for n in MASS_NAMES])
    # Order composite slots by reconstructed pT before defining either pair.
    swap = np.hypot(momentum[:, 1, 0], momentum[:, 1, 1]) > np.hypot(momentum[:, 0, 0], momentum[:, 0, 1])
    momentum[swap, :2] = momentum[swap, :2][:, ::-1]
    masses[swap, :2] = masses[swap, :2][:, ::-1]
    feature_masses = masses.copy()
    if nominal_kinematics:
        feature_masses[:] = (3.0969, 3.0969, 1.01946)
    features = correlation_features(momentum, feature_masses)
    axes = observable if isinstance(observable, list) else [observable]
    coordinates, folded = [], []
    for axis in axes:
        key = (axis["variable"], axis.get("system", axis.get("pair")))
        if key not in features:
            raise ValueError(f"Unknown feature {key}; choose from {list(features)}")
        x = features[key].copy()
        edges = np.asarray(axis["edges"], dtype=float)
        valid &= np.isfinite(x)
        folded.append(int(np.sum((x < edges[0]) | (x > edges[-1]))))
        if axis.get("flow", "exclude") == "fold":
            x = np.clip(x, edges[0], edges[-1])
        elif axis.get("flow", "exclude") == "exclude":
            valid &= (x >= edges[0]) & (x <= edges[-1])
        else:
            raise ValueError("flow must be fold or exclude")
        coordinates.append(x)
    weights = values[weight_name] if weight_name else np.ones(len(x))
    if np.any(weights[valid] < 0):
        raise ValueError("This implementation requires nonnegative MC weights")
    coordinates = np.column_stack(coordinates)[valid]
    return {"mass": masses[valid], "coordinates": coordinates,
            "x": coordinates[:, 0], "w": weights[valid],
            "row_index": np.flatnonzero(valid),
            "folded_entries_per_axis": folded,
            "input_entries": len(valid), "selected_entries": int(valid.sum())}


def bin_indices(x, edges):
    # Include the rightmost endpoint, as numpy.histogram does.
    return np.minimum(np.searchsorted(edges, x, side="right") - 1, len(edges) - 2)


def mass_fit_yields(sample, edges, output=None, background="exponential", initial_shapes=None):
    """Global shape fit, then conditional yield fits in disjoint bins."""
    import ROOT
    from scripts.kinematics.fit_splot import build_jjp_model, initialize_yields_for_dataset

    ROOT.gROOT.SetBatch(True)
    ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.ERROR)
    # The phi threshold PDF is numerically normalized. Tight integration avoids
    # noise in likelihood derivatives, especially in resampled shape fits.
    ROOT.RooAbsReal.defaultIntegratorConfig().setEpsAbs(1e-10)
    ROOT.RooAbsReal.defaultIntegratorConfig().setEpsRel(1e-10)
    model, obs, yields, signal_name, keep = build_jjp_model(
        len(sample["x"]), jpsi_background=background)
    # Adapter to the existing builder's internal legacy observable names.
    # External inputs default to canonical v1.5 names.
    def dataset(masses, name):
        columns = {key: np.ascontiguousarray(masses[:, i]) for i, key in enumerate(obs)}
        return ROOT.RooDataSet.from_numpy(columns, list(obs.values()), name=name)

    data = dataset(sample["mass"], "inclusive")
    if initial_shapes:
        for param in model.getParameters(data):
            if not param.isConstant() and param.GetName() in initial_shapes:
                start = initial_shapes[param.GetName()]
                param.setVal(start["value"])
                param.setError(start["error"])
    initialize_yields_for_dataset(yields, data.numEntries(), "JJP", False)
    rootfile = ROOT.TFile(str(output / "mass_fits.root"), "RECREATE") if output else None

    def fit(data, label):
        start = [(p, float(p.getVal()), float(p.getError()))
                 for p in model.getParameters(data) if not p.isConstant()]
        result = model.fitTo(data, ROOT.RooFit.Save(True), ROOT.RooFit.Extended(True),
                             ROOT.RooFit.PrintLevel(-1), ROOT.RooFit.Strategy(1), ROOT.RooFit.Offset(True))
        if result.status() != 0 or result.covQual() < 3 or result.edm() > 1e-3:
            # Restart from the input point, not a failed minimizer's position/errors.
            for param, value, error in start:
                param.setVal(value)
                if error > 0:
                    param.setError(error)
            result = model.fitTo(data, ROOT.RooFit.Save(True), ROOT.RooFit.Extended(True),
                                 ROOT.RooFit.PrintLevel(-1), ROOT.RooFit.Strategy(2), ROOT.RooFit.Offset(True))
        info = {"status": int(result.status()), "covQual": int(result.covQual()),
                "edm": float(result.edm()), "entries": int(data.numEntries()),
                "yields": {key: {"value": float(v.getVal()), "error": float(v.getError())}
                           for key, v in yields.items()}}
        if rootfile:
            rootfile.cd()
            result.Write(label)
            # Save fitted projections as RooPlots for detailed inspection.
            for name, mass in obs.items():
                frame = mass.frame(ROOT.RooFit.Bins(40))
                data.plotOn(frame)
                model.plotOn(frame)
                frame.Write(f"{label}_{name}")
            write_json(output / f"mass_{label}.json", info)
        if info["status"] != 0 or info["covQual"] < 3 or info["edm"] > 1e-3:
            raise RuntimeError(f"Unreliable mass fit in {label}: {info}; merge bins or revise model")
        return info

    try:
        global_info = fit(data, "global")
        initial = {key: var.getVal() for key, var in yields.items()}
        params = model.getParameters(data)
        shape_starts = {p.GetName(): {"value": float(p.getVal()), "error": float(p.getError())}
                        for p in params if p.GetName() not in yields and not p.isConstant()}
        shapes = {p.GetName(): float(p.getVal()) for p in params if p.GetName() not in yields}
        for param in params:
            if param.GetName() not in yields:
                param.setConstant(True)
        if output:
            write_json(output / "global_shapes.json", shapes)
        indices = bin_indices(sample["x"], edges)
        rows = []
        for index in range(len(edges) - 1):
            masses = sample["mass"][indices == index]
            if len(masses) < 30:
                raise ValueError(f"Bin {index} has only {len(masses)} candidates; use coarser bins")
            local = dataset(masses, f"bin_{index}")
            initialize_yields_for_dataset(yields, len(masses), "JJP", False)
            for key, var in yields.items():
                start = max(0.1, initial[key] * len(masses) / len(sample["x"]))
                var.setVal(start)
                var.setError(np.sqrt(max(start, 1.)))
            info = fit(local, f"bin_{index:03d}")
            signal = info["yields"][signal_name]
            if signal["error"] <= 0:
                raise RuntimeError(f"Invalid signal error in bin {index}")
            info.update({"bin": index, "lo": float(edges[index]), "hi": float(edges[index + 1]),
                         "signal": signal["value"], "error": signal["error"]})
            if signal["value"] < 2 * signal["error"]:
                warnings.warn(f"Bin {index}: signal near zero; Gaussian second-stage fit needs validation")
            rows.append(info)
            if output:
                print(f"Bin {index}: SSS={signal['value']:.1f} +/- {signal['error']:.1f}", flush=True)
        y = np.array([r["signal"] for r in rows])
        covariance = np.diag([r["error"] ** 2 for r in rows])
        return y, covariance, {"global": global_info, "bins": rows, "shape_starts": shape_starts}
    finally:
        if rootfile:
            rootfile.Close()


def make_template(sample, edges, weights=None):
    w = sample["w"] if weights is None else weights
    h = np.histogram(sample["x"], edges, weights=w)[0]
    q = np.histogram(sample["x"], edges, weights=w * w)[0]
    if h.sum() <= 0:
        raise ValueError("Empty MC template")
    t = h / h.sum()
    jacobian = (np.eye(len(h)) - t[:, None]) / h.sum()
    covariance = (jacobian * q) @ jacobian.T
    return t, {"sumw": h.tolist(), "sumw2": q.tolist(),
               "effective_entries": np.divide(h*h, q, out=np.zeros_like(h), where=q > 0).tolist(),
               "normalized_covariance": covariance.tolist()}


def fit_templates(y, covariance, templates, *, profile=False):
    """GLS with nonnegative component yields and the full data covariance."""
    lower = np.linalg.cholesky(covariance)
    design = solve_triangular(lower, templates, lower=True)
    target = solve_triangular(lower, y, lower=True)
    singular = np.linalg.svd(design, compute_uv=False)
    if len(singular) < templates.shape[1] or singular[-1] < 1e-8 * singular[0]:
        raise ValueError("Templates are linearly dependent; combine components or add information")
    def chi2(*n):
        residual = target - design @ np.asarray(n)
        return float(residual @ residual)
    fit = Minuit(chi2, *([max(y.sum(), 1) / templates.shape[1]] * templates.shape[1]),
                 name=tuple(f"N_{k}" for k in range(templates.shape[1])))
    fit.errordef = Minuit.LEAST_SQUARES
    fit.limits = (0, None)
    fit.migrad()
    fit.hesse()
    if not fit.valid or not fit.accurate:
        raise RuntimeError(f"Template fit failed: {fit.fmin}")
    n = np.array(fit.values)
    cov = np.asarray(fit.covariance)
    total = n.sum()
    if total <= 0:
        raise RuntimeError("Zero total fitted yield")
    fractions = n / total
    jac = (np.eye(len(n)) - fractions[:, None]) / total
    result = {"yields": n.tolist(), "yield_covariance_data": cov.tolist(),
            "fractions": fractions.tolist(), "fraction_covariance_data": (jac @ cov @ jac.T).tolist(),
            "chi2": float(fit.fval), "ndof_nominal": len(y) - len(n),
            "condition_number": float(singular[0] / singular[-1]),
            "parameters_at_limit": bool(fit.fmin.has_parameters_at_limit),
            "symmetric_errors_reliable": not bool(fit.fmin.has_parameters_at_limit),
            "prediction": (templates @ n).tolist()}
    if profile:
        from scripts.templates.multivariate import profile_upper_limits
        fit.minos()
        result["yield_profile_intervals_data_only"] = [
            {"lower_error": float(fit.merrors[name].lower),
             "upper_error": float(fit.merrors[name].upper),
             "valid": bool(fit.merrors[name].is_valid)} for name in fit.parameters]
        result["upper_limits_95_data_only"] = profile_upper_limits(y, covariance, templates)
    return result


def plot_result(output, edges, observable, y, covariance, templates, names, result, toy=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import mplhep as hep
    hep.style.use(hep.style.CMS)
    fig, (ax, pull) = plt.subplots(2, 1, figsize=(9, 9), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08})
    centers, widths = (edges[1:] + edges[:-1]) / 2, np.diff(edges)
    err = np.sqrt(np.diag(covariance))
    ax.errorbar(centers, y / widths, yerr=err / widths, fmt="ko", label="Mass-fit signal yields")
    for name, shape, n in zip(names, templates.T, result["yields"]):
        ax.stairs(n * shape / widths, edges, label=name, linewidth=2)
    pred = np.array(result["prediction"])
    ax.stairs(pred / widths, edges, color="black", linewidth=2, label="Total fit")
    ax.set_ylabel("Selected signal / unit x")
    ax.set_ylim(0, 1.5 * max(np.max((y + err) / widths), np.max(pred / widths)))
    ax.legend(fontsize=13, loc="upper right")
    hep.cms.label("Toy study" if toy else "Work In Progress", data=not toy, ax=ax, loc=0, rlabel="")
    pull.axhline(0, color="gray")
    pull.errorbar(centers, (y - pred) / err, yerr=np.ones(len(y)), fmt="ko")
    pull.set_ylabel(r"Residual / $\sigma_i$", fontsize=15)
    pull.set_xlabel(observable.get("label", observable["variable"]))
    fig.subplots_adjust(left=0.17, right=0.96, bottom=0.12, top=0.91)
    fig.savefig(output / "template_fit.pdf")
    fig.savefig(output / "template_fit.png", dpi=160)
    plt.close(fig)


def run(config, output, data_bootstrap=0, mc_bootstrap=0, entry_stop=None, seed=12345):
    from scripts.templates.multivariate import (
        adaptive_cells, encode_samples, split_samples, validate_templates,
    )
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "configuration.json", config)
    axes = config.get("observables", [config.get("observable")])
    if not axes or any(axis is None for axis in axes):
        raise ValueError("Specify observable or observables")
    for axis in axes:
        ee = np.asarray(axis["edges"], dtype=float)
        if ee.ndim != 1 or len(ee) < 3 or not np.all(np.isfinite(ee)) or np.any(np.diff(ee) <= 0):
            raise ValueError("Use at least two finite, increasing bins per axis")
    observable = axes[0]
    edges = np.asarray(observable["edges"], dtype=float)
    if config["data"].get("weight"):
        raise ValueError("Data mass fits must be unweighted")
    if len(config["components"]) < 2:
        raise ValueError("Use at least two components")
    rng = np.random.default_rng(seed)
    data = read_candidates(config["data"], axes, entry_stop)
    mc = {name: read_candidates(spec, axes, entry_stop)
          for name, spec in config["components"].items()}
    write_json(output / "selection_counts.json", {
        name: {key: sample[key] for key in ("input_entries", "selected_entries", "folded_entries_per_axis")}
        for name, sample in {"data": data, **mc}.items()})
    heldout = None
    validation = config.get("validation")
    if validation:
        fraction = validation.get("holdout_fraction", .25)
        if not 0 < fraction < 1 or validation.get("toys", 20) < 2:
            raise ValueError("Validation needs a split fraction in (0,1) and at least two toys")
        mc, heldout = split_samples(mc, fraction, rng)
    partition = None
    if len(axes) > 1:
        settings = config.get("adaptive_binning", {})
        fraction = settings.get("training_fraction", .35)
        if not 0 < fraction < 1:
            raise ValueError("training_fraction must be in (0,1)")
        mc, training = split_samples(mc, fraction, rng)
        partition, n_cells = adaptive_cells(training, axes, settings.get("max_cells", 12),
                                            settings.get("min_mc_effective", 40))
        edges = np.arange(n_cells + 1, dtype=float)
        encode_samples({"data": data, **mc}, partition)
        if heldout:
            encode_samples(heldout, partition)
        observable = {"variable": "cell", "label": "Adaptive template cell"}
        write_json(output / "partition.json", {"axes": axes, "tree": partition, "cells": n_cells,
                   "training_entries": {name: len(s["x"]) for name, s in training.items()}})
    if len(config["components"]) >= len(edges) - 1:
        raise ValueError("Use more bins/cells than components for a testable decomposition")
    if heldout:
        check = validate_templates(mc, heldout, edges, make_template, rng,
                                   validation.get("event_yield", 2000), validation.get("toys", 20))
        write_json(output / "mc_validation.json", check)
        if not check["passed"]:
            raise RuntimeError("Independent MC template closure failed; inspect mc_validation.json")
    background = config.get("jpsi_background", "exponential")
    y, covariance, diagnostics = mass_fit_yields(data, edges, output, background)
    conditional = covariance.copy()
    if data_bootstrap:
        if data_bootstrap < max(30, 2 * len(y)):
            raise ValueError("Use at least max(30, 2*nbins) data bootstrap replicas")
        replicas = []
        for k in range(data_bootstrap):
            # Poisson event bootstrap allows the total yield to fluctuate.
            idx = np.repeat(np.arange(len(data["x"])), rng.poisson(1, len(data["x"])))
            replica = {key: data[key][idx] for key in ("x", "mass", "w")}
            yy, _, _ = mass_fit_yields(replica, edges, background=background,
                                       initial_shapes=diagnostics["shape_starts"])
            replicas.append(yy)
            print(f"Data bootstrap {k + 1}/{data_bootstrap}", flush=True)
        covariance = np.cov(replicas, rowvar=False, ddof=1)
        np.save(output / "data_bootstrap_yields.npy", replicas)
    shapes, mc_info = [], {}
    for name, sample in mc.items():
        shape, info = make_template(sample, edges)
        shapes.append(shape)
        mc_info[name] = info
        if min(info["effective_entries"]) < 20:
            warnings.warn(f"{name}: at least one bin has MC effective entries below 20")
    templates = np.column_stack(shapes)
    result = fit_templates(y, covariance, templates, profile=True)
    if mc_bootstrap:
        if mc_bootstrap < 30:
            raise ValueError("Use at least 30 MC bootstrap replicas")
        replicas, fraction_replicas = [], []
        for _ in range(mc_bootstrap):
            shapes = [make_template(s, edges, s["w"] * rng.poisson(1, len(s["x"])))[0]
                      for s in mc.values()]
            fitted = fit_templates(y, covariance, np.column_stack(shapes))
            replicas.append(fitted["yields"])
            fraction_replicas.append(fitted["fractions"])
        result["yield_covariance_mc"] = np.cov(replicas, rowvar=False).tolist()
        result["fraction_covariance_mc"] = np.cov(fraction_replicas, rowvar=False).tolist()
        np.save(output / "mc_bootstrap_yields.npy", replicas)
    for quantity in ("yield", "fraction"):
        cov = np.array(result[f"{quantity}_covariance_data"])
        mc_cov = np.array(result.get(f"{quantity}_covariance_mc", np.zeros_like(cov)))
        result[f"{quantity}_covariance_total"] = (cov + mc_cov).tolist()
        result[f"{quantity}_errors_total"] = np.sqrt(np.diag(cov + mc_cov)).tolist()
    result.update({"components": list(mc), "data_bootstrap_replicas": data_bootstrap,
                   "mc_bootstrap_replicas": mc_bootstrap, "entry_stop": entry_stop,
                   "interpretation": "selected RECO yields/fractions in the specified observable range",
                   "data_covariance": "event bootstrap with global refit" if data_bootstrap else "conditional on fixed global shapes",
                   "mc_uncertainty": "Poisson event bootstrap; covariance added at first order" if mc_bootstrap else "not propagated"})
    result["observables"] = axes
    result["binning"] = "MC-trained disjoint adaptive cells" if partition else "one dimensional"
    result["fit_method"] = "multivariable cell-template fit" if partition else "single-observable template fit"
    result["template_coordinate"] = "adaptive cell index" if partition else observable["variable"]
    result["input_observable_count"] = len(axes)
    result["mc_validation_passed"] = bool(check["passed"]) if heldout else None
    result["template_entries"] = {name: len(s["x"]) for name, s in mc.items()}
    if result["condition_number"] > 100:
        warnings.warn("Poor template separation: inspect component correlations and closure")
    if result["parameters_at_limit"]:
        warnings.warn("Component yield at boundary: symmetric errors need profile/toy validation")
    write_json(output / "mass_yields.json", diagnostics)
    write_json(output / "templates.json", mc_info)
    write_json(output / "result.json", result)
    np.savez(output / "fit_inputs.npz", edges=edges, signal=y, covariance=covariance,
             covariance_conditional=conditional, templates=templates, components=np.array(list(mc)))
    if partition:
        np.savez(output / "cell_coordinates.npz", coordinates=data["coordinates"], cells=data["x"])
    np.savetxt(output / "signal_yields.csv", np.column_stack([
        edges[:-1], edges[1:], y, np.sqrt(np.diag(covariance))]), delimiter=",",
        header="lo,hi,signal,error", comments="")
    plot_result(output, edges, observable, y, covariance, templates, list(mc), result, config.get("toy", False))
    print(json.dumps(result, indent=2), flush=True)
    return result


def make_demo(directory, seed=12345, multivariate=False):
    """Generate independent MC and data from the production mass model."""
    import ROOT
    from scripts.kinematics.fit_splot import build_jjp_model
    directory.mkdir(parents=True, exist_ok=False)
    ROOT.RooRandom.randomGenerator().SetSeed(seed)
    rng = np.random.default_rng(seed)
    model, obs, yields, _, keep = build_jjp_model(10000)
    truth = {"DPS1": 1800, "DPS2_CS": 1200, "SPS_CS": 800}

    def candidates(n, kind, pdf_index=0):
        # Three deliberately distinct toy shapes; these are NOT physics predictions.
        if kind == "DPS1":
            x = rng.uniform(0, np.pi, n)
        elif kind == "DPS2_CS":
            x = np.pi * rng.beta(5, 1.3, n)
        elif kind == "SPS_CS":
            x = np.pi * rng.beta(1.3, 5, n)
        else:
            x = rng.uniform(0, np.pi, n)
        generated = model.pdfList().at(pdf_index).generate(ROOT.RooArgSet(*obs.values()), n)
        arrays = generated.to_numpy()
        result = {}
        base_y = rng.normal(0, .65, n) if multivariate else None
        width = {"DPS1": 1.25, "DPS2_CS": .75, "SPS_CS": .4}.get(kind, 1.)
        azimuth = rng.uniform(-np.pi, np.pi, n) if multivariate else 0
        for i, obj in enumerate(OBJECTS):
            mass = np.array(arrays[list(obs)[i]], copy=True)
            phi = np.zeros(n) if i == 0 else x if i == 1 else rng.uniform(-np.pi, np.pi, n)
            pt = np.full(n, [12., 8., 4.][i])
            rapidity = rng.normal(0, 0.8, n)
            if multivariate:
                phi = phi + azimuth
                if i == 2:
                    phi = azimuth + rng.normal(0, width, n)
                boost = {"DPS1": 1., "DPS2_CS": 1.2, "SPS_CS": 1.8}.get(kind, .9)
                pt = rng.lognormal(np.log([12., 8., 4.][i] * boost), .28, n)
                rapidity = base_y + rng.normal(0, width, n)
            for field, value in {"mass": mass, "px": pt*np.cos(phi), "py": pt*np.sin(phi),
                                 "pz": np.hypot(pt, mass)*np.sinh(rapidity)}.items():
                result[f"{obj}_{field}"] = value
        return result

    config = {"toy": True, "data": {"path": str((directory / "data.root").resolve())},
              "observable": {"variable": "abs_dphi", "pair": "jpsi1_jpsi2",
                             "edges": np.linspace(0, np.pi, 9).tolist(),
                             "label": r"$|\Delta\phi(J/\psi_1,J/\psi_2)|$"}, "components": {}}
    data_chunks = [candidates(n, name) for name, n in truth.items()]
    # All seven partially/completely combinatorial mass components are present.
    data_chunks.extend(candidates(200, "background", i) for i in range(1, 8))
    def write_tree(path, columns):
        with uproot.recreate(path) as handle:
            handle.mktree("X_data", {key: value.dtype for key, value in columns.items()})
            handle["X_data"].extend(columns)

    write_tree(directory / "data.root", {
        key: np.concatenate([c[key] for c in data_chunks]) for key in data_chunks[0]})
    for name in truth:
        path = (directory / f"{name}.root").resolve()
        write_tree(path, candidates(12000, name))
        config["components"][name] = {"path": str(path)}
    write_json(directory / "config.json", config)
    write_json(directory / "truth.json", truth)
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--config", type=Path)
    source.add_argument("--demo", action="store_true", help="Generate and fit toy ROOT files")
    parser.add_argument("--output-dir", required=True, type=Path, help="Must not already exist")
    parser.add_argument("--data-bootstrap", type=int, default=0)
    parser.add_argument("--mc-bootstrap", type=int, default=0)
    parser.add_argument("--entry-stop", type=int, help="Bound input reads for smoke tests only")
    parser.add_argument("--seed", type=int, default=12345)
    args = parser.parse_args()
    if args.data_bootstrap < 0 or args.mc_bootstrap < 0:
        parser.error("Bootstrap counts must be nonnegative")
    if args.demo:
        config = make_demo(args.output_dir.with_name(args.output_dir.name + "_inputs"), args.seed)
    else:
        config = json.loads(args.config.read_text())
    run(config, args.output_dir, args.data_bootstrap, args.mc_bootstrap, args.entry_stop, args.seed)


if __name__ == "__main__":
    main()

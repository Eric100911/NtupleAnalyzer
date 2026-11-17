"""Extended three-mass fits with shared nuisances and preserved covariance.

This is an inclusive selected-RECO inference tool. Its default common signal
shape is a testable model assumption, not a calibration or prompt selection.
ROOT is imported lazily so event and template helpers can be used independently.
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np

MASS_CATEGORIES = ("sss", "ssb", "sbs", "bss", "sbb", "bsb", "bbs", "bbb")
MASS_WINDOWS = ((2.9, 3.3), (2.9, 3.3), (.99, 1.07))


def _root():
    import ROOT
    ROOT.gROOT.SetBatch(True)
    ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.ERROR)
    ROOT.RooAbsReal.defaultIntegratorConfig().setEpsAbs(1.e-9)
    ROOT.RooAbsReal.defaultIntegratorConfig().setEpsRel(1.e-9)
    return ROOT


def _observables(ROOT):
    return [ROOT.RooRealVar(name, name, *bounds) for name, bounds in zip(
        ("Jpsi_1_mass", "Jpsi_2_mass", "Phi_mass"), MASS_WINDOWS)]


def _validate(masses, categories, n_categories, templates):
    masses = np.asarray(masses, dtype=float)
    raw = np.asarray(categories)
    if masses.ndim != 2 or masses.shape[1] != 3 or raw.shape != (len(masses),):
        raise ValueError("Expected masses(N,3) and categories(N)")
    if not isinstance(n_categories, (int, np.integer)) or n_categories < 1:
        raise ValueError("n_categories must be positive")
    if not np.isfinite(masses).all() or not np.isfinite(raw).all() or np.any(raw != raw.astype(int)):
        raise ValueError("Nonfinite masses or noninteger categories")
    categories = raw.astype(int)
    if np.any((categories < 0) | (categories >= n_categories)):
        raise ValueError("Category outside fixed response labels")
    for axis, (lo, hi) in enumerate(MASS_WINDOWS):
        if np.any((masses[:, axis] < lo) | (masses[:, axis] > hi)):
            raise ValueError("Mass outside exact fit domain")
    if templates is not None:
        templates = np.asarray(templates, dtype=float)
        if templates.ndim != 2 or templates.shape[0] != n_categories or templates.shape[1] < 1:
            raise ValueError("Expected response templates(B,C)")
        if not np.isfinite(templates).all() or np.any(templates < 0) or not np.allclose(templates.sum(axis=0), 1., atol=1.e-9):
            raise ValueError("Response columns must be nonnegative unit-normalized")
    return masses, categories, templates



def _class_scales(value, bins, classes):
    scales = np.asarray(value, float)
    try:
        scales = np.broadcast_to(scales, (bins, classes)).copy()
    except ValueError as error:
        raise ValueError("Class resolution scales must be scalar, C, or BxC") from error
    if not np.isfinite(scales).all() or np.any(scales <= 0):
        raise ValueError("Class resolution scales must be finite and positive")
    return scales


def _scaled_signal(ROOT, obs, parameters, prefix, multiplier, shape_config, keep):
    from scripts.kinematics.fit_splot import build_jjp_mass_components
    params = dict(parameters)
    for name in ("jpsi1_sigma", "jpsi2_sigma", "phi_sigma"):
        scale = ROOT.RooConstVar(prefix+name+"_multiplier", "fixed calibrated class resolution scale", multiplier)
        params[name] = ROOT.RooFormulaVar(prefix+name, "@0*@1", ROOT.RooArgList(params[name], scale))
        keep.extend([scale, params[name]])
    piece = build_jjp_mass_components(obs, prefix, shape_config, params)
    keep.extend(piece["keep"])
    return piece["components"]["sss"]


def fit_simultaneous_masses(masses, categories, n_categories, response_templates=None,
                            config=None, output_dir=None):
    """Fit all exclusive labels once, retaining empty-label Poisson terms.

    With templates, SSS_b=sum_c N_c T_bc. Without templates, SSS yields are
    independent. Every populated bin has seven independent background yields.
    Empty independent yields have exact conditional MLE zero and are eliminated
    analytically; their upper profile bounds are reported separately.
    """
    ROOT = _root()
    from scripts.kinematics.fit_splot import build_jjp_mass_components
    masses, categories, templates = _validate(masses, categories, n_categories, response_templates)
    cfg = dict(config or {})
    allowed = {"shape_config", "freeze_shapes", "profile", "shape_groups", "resolution_multipliers",
               "constraints", "max_calls", "allow_invalid", "strategy", "profile_parameters", "class_resolution_multipliers", "warm_start", "nll_offset", "initial_parameters", "minuit_precision", "warm_start_method", "save_workspace"}
    if set(cfg) - allowed:
        raise ValueError(f"Unknown fit options: {sorted(set(cfg)-allowed)}")
    class_scales = None
    if "class_resolution_multipliers" in cfg:
        if templates is None:
            raise ValueError("Class resolution multipliers require response templates")
        class_scales = _class_scales(cfg["class_resolution_multipliers"], n_categories, templates.shape[1])
    output = Path(output_dir) if output_dir is not None else None
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        if (output / "mass_fit.root").exists() or (output / "mass_fit.json").exists():
            raise FileExistsError("Refusing to overwrite an existing mass fit")
    obs = _observables(ROOT)
    keep = list(obs)
    group_labels = cfg.get("shape_groups", [0] * n_categories)
    if len(group_labels) != n_categories:
        raise ValueError("shape_groups must contain one label per category")
    multipliers = np.asarray(cfg.get("resolution_multipliers", np.ones(n_categories)), float)
    if multipliers.shape != (n_categories,) or np.any(~np.isfinite(multipliers)) or np.any(multipliers <= 0):
        raise ValueError("Invalid resolution multipliers")
    groups, pieces = {}, []
    for b, group in enumerate(group_labels):
        key = str(group)
        if key not in groups:
            groups[key] = build_jjp_mass_components(obs, f"shape{len(groups)}_", cfg.get("shape_config"))
            keep.extend(groups[key]["keep"])
        base = groups[key]
        params = dict(base["parameters"])
        if multipliers[b] != 1.:
            for name in ("jpsi1_sigma", "jpsi2_sigma", "phi_sigma"):
                scale = ROOT.RooConstVar(f"scale{b}_{name}", "calibrated resolution multiplier", float(multipliers[b]))
                params[name] = ROOT.RooFormulaVar(f"res{b}_{name}", "@0*@1", ROOT.RooArgList(params[name], scale))
                keep.extend([scale, params[name]])
        piece = build_jjp_mass_components(obs, f"bin{b}_", cfg.get("shape_config"), params)
        keep.extend(piece["keep"])
        pieces.append(piece)
    shape_parameters = {p.GetName(): p for group in groups.values() for p in group["parameters"].values()}
    if cfg.get("freeze_shapes", False):
        for parameter in shape_parameters.values():
            if hasattr(parameter, "setConstant"):
                parameter.setConstant(True)
    # Independent constraints must be explicitly marked; no inclusive-data prior.
    constraints = []
    for i, spec in enumerate(cfg.get("constraints", [])):
        if spec.get("independent") is not True or not spec.get("source"):
            raise ValueError("Constraints require independent=True and source provenance")
        name = spec["parameter"]
        if name not in shape_parameters or not np.isfinite(spec["sigma"]) or spec["sigma"] <= 0:
            raise ValueError("Invalid external constraint parameter/sigma")
        mean = ROOT.RooConstVar(f"constraint{i}_mean", "external mean", float(spec["mean"]))
        sigma = ROOT.RooConstVar(f"constraint{i}_sigma", "external sigma", float(spec["sigma"]))
        constraint = ROOT.RooGaussian(f"constraint{i}", "independent external constraint", shape_parameters[name], mean, sigma)
        constraints.append(constraint)
        keep.extend([mean, sigma, constraint])
    total = max(len(masses), 1)
    bound = max(total * 3., 100.)
    class_parameters = []
    if templates is not None:
        for c in range(templates.shape[1]):
            p = ROOT.RooRealVar(f"N_class{c}", f"selected RECO class {c}", total * .3 / templates.shape[1], 0., bound)
            p.setError(np.sqrt(max(p.getVal(), 1.)))
            class_parameters.append(p)
    category = ROOT.RooCategory("mass_category_bin", "exclusive response/observable bin")
    simultaneous = ROOT.RooSimultaneous("simultaneous_mass_model", "simultaneous three-mass model", category)
    keep.extend(class_parameters + [category, simultaneous])
    counts = np.bincount(categories, minlength=n_categories)
    signal_parameters, all_yields, nll_terms, raw_nll_terms, datasets, pdfs_by_bin = [], [], [], [], [], []
    for b in range(n_categories):
        label = f"bin{b}"
        category.defineType(label, b)
        if templates is None:
            signal = ROOT.RooRealVar(f"Y_sss_bin{b}", f"SSS yield bin {b}", max(counts[b] * .3, .1), 0., bound)
            signal.setError(np.sqrt(max(signal.getVal(), 1.)))
        else:
            expression = "+".join(f"{templates[b,c]:.17g}*@{c}" for c in range(templates.shape[1]))
            signal = ROOT.RooFormulaVar(f"Y_sss_bin{b}", expression, ROOT.RooArgList(*class_parameters))
        yields = [signal]
        for code in MASS_CATEGORIES[1:]:
            p = ROOT.RooRealVar(f"Y_{code}_bin{b}", f"{code} yield bin {b}", max(counts[b] * .1, .1), 0., bound)
            p.setError(np.sqrt(max(p.getVal(), 1.)))
            yields.append(p)
        if counts[b] == 0:
            for p in yields[1:] if templates is not None else yields:
                p.setVal(0.)
                p.setConstant(True)
        model_pdfs = list(pieces[b]["components"].values())
        model_yields = yields
        if class_scales is not None:
            model_pdfs, model_yields = [], []
            for c in range(templates.shape[1]):
                signal_piece = _scaled_signal(ROOT, obs, pieces[b]["parameters"],
                    f"bin{b}_class{c}_", float(class_scales[b,c]), cfg.get("shape_config"), keep)
                coefficient = ROOT.RooFormulaVar(f"N_bin{b}_class{c}", f"{templates[b,c]:.17g}*@0",
                    ROOT.RooArgList(class_parameters[c]))
                model_pdfs.append(signal_piece)
                model_yields.append(coefficient)
                keep.append(coefficient)
            model_pdfs.extend(list(pieces[b]["components"].values())[1:])
            model_yields.extend(yields[1:])
        model = ROOT.RooAddPdf(f"mass_model_bin{b}", "extended signal-class and background mass model",
            ROOT.RooArgList(*model_pdfs), ROOT.RooArgList(*model_yields))
        pdfs_by_bin.append(model_pdfs)
        simultaneous.addPdf(model, label)
        local = masses[categories == b]
        data = ROOT.RooDataSet.from_numpy({p.GetName(): np.ascontiguousarray(local[:,i]) for i,p in enumerate(obs)}, obs, name=f"data_bin{b}")
        if counts[b]:
            nll = model.createNLL(data, ROOT.RooFit.Extended(True), ROOT.RooFit.Offset(bool(cfg.get("nll_offset", True))))
            raw_nll = model.createNLL(data, ROOT.RooFit.Extended(True), ROOT.RooFit.Offset(False))
        else:
            # RooSimultaneous may omit unobserved channel states. This explicit
            # term retains exp(-nu_b), including every floored signal template.
            nll = ROOT.RooAddition(f"empty_rate_bin{b}", "empty-bin expected rate", ROOT.RooArgList(*yields))
            raw_nll = nll
        raw_nll_terms.append(raw_nll)
        keep.append(raw_nll)
        keep.extend(yields + [model, data, nll])
        nll_terms.append(nll)
        datasets.append(data)
        all_yields.append(yields)
        signal_parameters.append(signal)
    for i, constraint in enumerate(constraints):
        term = ROOT.RooFormulaVar(f"constraint_nll{i}", "-log(@0)", ROOT.RooArgList(constraint))
        keep.append(term)
        nll_terms.append(term)
        raw_nll_terms.append(term)
    objective = ROOT.RooAddition("full_extended_nll", "sum of all exclusive extended NLLs", ROOT.RooArgList(*nll_terms))
    keep.append(objective)
    raw_objective = ROOT.RooAddition("raw_full_extended_nll", "unoffset diagnostic NLL", ROOT.RooArgList(*raw_nll_terms))
    keep.append(raw_objective)
    parameters = sorted([p for p in objective.getParameters(ROOT.RooArgSet(*obs))
                         if hasattr(p, "setError") and not p.isConstant()], key=lambda p: p.GetName())
    requested_initial = cfg.get("initial_parameters", {})
    if set(requested_initial) - {p.GetName() for p in parameters}:
        raise ValueError("Unknown floating initial parameter")
    for p in parameters:
        if p.GetName() in requested_initial:
            value = float(requested_initial[p.GetName()])
            if not np.isfinite(value) or not p.getMin() <= value <= p.getMax():
                raise ValueError("Initial parameter outside bounds")
            p.setVal(value)
    # Explicit physical steps avoid RooFit's range-sized default shape errors
    # and prevent failed Hessians from setting the scale of a fresh retry.
    def reset_steps():
        for p in parameters:
            name = p.GetName()
            step = np.sqrt(max(p.getVal(), 1.)) if name.startswith(("Y_", "N_")) else .01*(p.getMax()-p.getMin())
            p.setError(float(step))
    def snapshot():
        return {p.GetName(): {"value": float(p.getVal()), "error": float(p.getError()),
                "lower": float(p.getMin()), "upper": float(p.getMax())} for p in parameters}
    def gradient_diagnostic():
        # Central finite differences in units of the fitted standard error;
        # two step sizes expose cancellation/noisy numerical normalization.
        gradients = {}
        for p in parameters:
            value, error = float(p.getVal()), float(p.getError())
            slopes = []
            for fraction in (.01, .03):
                step = min(error*fraction, (p.getMax()-p.getMin())*.01)
                if step <= 0:
                    slopes.append(None)
                    continue
                if value-p.getMin() < step:
                    minus = float(objective.getVal())
                    p.setVal(value+step); plus = float(objective.getVal())
                    denominator = step
                elif p.getMax()-value < step:
                    plus = float(objective.getVal())
                    p.setVal(value-step); minus = float(objective.getVal())
                    denominator = step
                else:
                    p.setVal(value+step); plus = float(objective.getVal())
                    p.setVal(value-step); minus = float(objective.getVal())
                    denominator = 2*step
                p.setVal(value)
                slopes.append((plus-minus)/denominator*error)
            gradients[p.GetName()] = slopes
        return gradients
    reset_steps()
    initial_parameters = snapshot()
    objective_baseline = float(objective.getVal())
    raw_objective_baseline = float(raw_objective.getVal())
    def create_minimizer():
        previous_precision = ROOT.Math.MinimizerOptions.DefaultPrecision()
        try:
            if cfg.get("minuit_precision", 1.e-9):
                ROOT.Math.MinimizerOptions.SetDefaultPrecision(float(cfg.get("minuit_precision", 1.e-9)))
            return ROOT.RooMinimizer(objective)
        finally:
            ROOT.Math.MinimizerOptions.SetDefaultPrecision(previous_precision)
    def minimize(engine):
        return engine.minimize("Minuit2", "migrad")
    def em_initialize():
        # Exact extended-mixture EM with shapes held fixed. Global class
        # exposures include ALL response labels, including unobserved labels.
        density = []
        normset = ROOT.RooArgSet(*obs)
        for b in range(n_categories):
            local = masses[categories == b]
            pdfs = pdfs_by_bin[b]
            if templates is not None and class_scales is None:
                pdfs = [pdfs[0]] * len(class_parameters) + pdfs[1:]
            values = np.empty((len(local), len(pdfs)))
            for i, row in enumerate(local):
                for observable, value in zip(obs, row):
                    observable.setVal(float(value))
                values[i] = [pdf.getVal(normset) for pdf in pdfs]
            density.append(values)
        history = [float(objective.getVal())]
        for iteration in range(100):
            updated_classes = np.zeros(len(class_parameters))
            updated_backgrounds = []
            current_classes = np.array([p.getVal() for p in class_parameters])
            for b, values in enumerate(density):
                coefficients = (np.array([p.getVal() for p in all_yields[b]]) if templates is None else
                                np.r_[current_classes * templates[b], [p.getVal() for p in all_yields[b][1:]]])
                intensity = values @ coefficients
                responsibilities = values * coefficients / np.maximum(intensity[:, None], np.finfo(float).tiny)
                if templates is not None:
                    updated_classes += responsibilities[:, :len(class_parameters)].sum(axis=0)
                updated_backgrounds.append(responsibilities[:, 0 if templates is None else len(class_parameters):].sum(axis=0))
            if templates is not None:
                updated_classes /= templates.sum(axis=0)
            previous = snapshot()
            for p, value in zip(class_parameters, updated_classes):
                p.setVal(float(value))
            for row, values in zip(all_yields, updated_backgrounds):
                for p, value in zip(row if templates is None else row[1:], values):
                    p.setVal(float(value))
            value = float(objective.getVal())
            if value > history[-1] + 1.e-8:
                for p in parameters:
                    p.setVal(previous[p.GetName()]["value"])
                raise RuntimeError("Exact extended-mixture EM increased the likelihood objective")
            history.append(value)
        return {"method": "exact_extended_mixture_EM", "iterations": 100,
                "objective_history": history, "parameters": snapshot(),
                "scope": "same-data yield initialization only; all shapes held fixed; no prior or covariance reused"}
    warm_start = None
    floating_shapes = [p for p in shape_parameters.values() if not p.isConstant()]
    if cfg.get("warm_start", True) and cfg.get("warm_start_method", "em") == "em":
        warm_start = em_initialize()
    elif cfg.get("warm_start", True) and floating_shapes:
        # The same data only initialize yields; no prefit result becomes a prior.
        # Restore every shape's original floating status before the joint fit.
        for parameter in floating_shapes:
            parameter.setConstant(True)
        starter = create_minimizer()
        starter.setPrintLevel(-1)
        starter.setStrategy(1)
        starter.setEps(.1)
        if cfg.get("max_calls"):
            starter.setMaxFunctionCalls(int(cfg["max_calls"]))
        warm_status = minimize(starter)
        warm_fit = starter.save()
        warm_start = {"status": int(warm_status), "edm": float(warm_fit.edm()),
                      "parameters": snapshot(),
                      "scope": "yield-only initialization from same data; no constraint or covariance reused"}
        for parameter in floating_shapes:
            parameter.setConstant(False)
    minimizer = create_minimizer()
    minimizer.setPrintLevel(-1)
    minimizer.setEps(.1)
    reset_steps()
    attempt_initial = snapshot()
    minimizer.setStrategy(int(cfg.get("strategy", 1)))
    if cfg.get("max_calls"):
        minimizer.setMaxFunctionCalls(int(cfg["max_calls"]))
    status = minimize(minimizer)
    migrad_steps = [{"strategy": int(cfg.get("strategy", 1)), "status": int(status), "fresh_minimizer": True}]
    if status:
        minimizer.setStrategy(2)
        status = minimize(minimizer)
        migrad_steps.append({"strategy": 2, "status": int(status), "fresh_minimizer": False})
    hesse_status = minimizer.hesse()
    preliminary = minimizer.save()
    attempts = [{"status": int(preliminary.status()), "edm": float(preliminary.edm()),
                 "covQual": int(preliminary.covQual()), "migrad_status": int(status), "hesse_status": int(hesse_status), "minuit_epsilon": .1,
                 "delta_nll": float(objective.getVal())-objective_baseline, "initial_parameters": attempt_initial, "parameters": snapshot()}]
    attempts[-1]["unoffset_nll"] = float(raw_objective.getVal())
    candidates = [(minimizer, preliminary, int(status), int(hesse_status))]
    if preliminary.status() != 0 or preliminary.covQual() < 3 or preliminary.edm() >= 1.e-3:
        # Start a fresh minimizer so a previous failed status/Hessian is not
        # carried into an otherwise converged retry. Preserve fitted values.
        minimizer = create_minimizer()
        minimizer.setPrintLevel(-1)
        minimizer.setStrategy(2)
        minimizer.setEps(.1)
        reset_steps()
        attempt_initial = snapshot()
        if cfg.get("max_calls"):
            minimizer.setMaxFunctionCalls(int(cfg["max_calls"]))
        status = minimize(minimizer)
        hesse_status = minimizer.hesse()
        migrad_steps.append({"strategy": 2, "status": int(status), "fresh_minimizer": True})
        refined = minimizer.save()
        candidates.append((minimizer, refined, int(status), int(hesse_status)))
        attempts.append({"status": int(refined.status()), "edm": float(refined.edm()),
                         "covQual": int(refined.covQual()), "migrad_status": int(status), "hesse_status": int(hesse_status), "minuit_epsilon": .1,
                         "delta_nll": float(objective.getVal())-objective_baseline, "initial_parameters": attempt_initial, "parameters": snapshot()})
        attempts[-1]["unoffset_nll"] = float(raw_objective.getVal())
    if not any(a["status"] == 0 and a["covQual"] >= 3 and a["edm"] < 1.e-3 for a in attempts):
        # One predefined physical restart for every fit. This is bounded and
        # independent of category names, observed yields or whether it helps.
        changes = {"jpsi1_mean": 3.095, "jpsi2_mean": 3.097,
                   "jpsi1_sigma": .028, "jpsi2_sigma": .023,
                   "phi_mean": 1.0193, "phi_sigma": .0022}
        for p in parameters:
            value = initial_parameters[p.GetName()]["value"]
            for suffix, restart_value in changes.items():
                if p.GetName().endswith("_"+suffix):
                    value = restart_value
            p.setVal(float(np.clip(value, p.getMin(), p.getMax())))
        restart_initial = snapshot()
        restart_em = em_initialize()
        reset_steps()
        attempt_initial = snapshot()
        minimizer = create_minimizer()
        minimizer.setPrintLevel(-1)
        minimizer.setStrategy(2)
        minimizer.setEps(.1)
        if cfg.get("max_calls"):
            minimizer.setMaxFunctionCalls(int(cfg["max_calls"]))
        status = minimize(minimizer)
        hesse_status = minimizer.hesse()
        restarted = minimizer.save()
        candidates.append((minimizer, restarted, int(status), int(hesse_status)))
        migrad_steps.append({"strategy": 2, "status": int(status), "fresh_minimizer": True, "physical_restart": True})
        attempts.append({"status": int(restarted.status()), "edm": float(restarted.edm()),
                         "covQual": int(restarted.covQual()), "migrad_status": int(status),
                         "hesse_status": int(hesse_status), "minuit_epsilon": .1,
                         "delta_nll": float(objective.getVal())-objective_baseline,
                         "initial_parameters": attempt_initial, "parameters": snapshot(),
                         "unoffset_nll": float(raw_objective.getVal()),
                         "physical_restart_initial": restart_initial, "restart_em": restart_em})
    # Keep every attempt and restore the lowest-NLL converged candidate. Failed
    # retries remain visible and cannot displace a validated covariance.
    for attempt, (_, saved_fit, _, _) in zip(attempts, candidates):
        saved_parameters = saved_fit.floatParsFinal()
        saved_covariance = saved_fit.covarianceMatrix()
        attempt["finite"] = bool(np.isfinite(attempt["delta_nll"]) and
            all(np.isfinite(p.getVal()) for p in saved_parameters) and
            all(np.isfinite(saved_covariance[i][j]) for i in range(len(saved_parameters)) for j in range(len(saved_parameters))))
    converged = [i for i, a in enumerate(attempts) if a["status"] == 0 and a["covQual"] >= 3 and a["edm"] < 1.e-3 and a["finite"]]
    selected_attempt = min(converged or list(range(len(attempts))), key=lambda i: attempts[i]["delta_nll"]
                           if np.isfinite(attempts[i]["delta_nll"]) else np.inf)
    minimizer, selected_fit, status, hesse_status = candidates[selected_attempt]
    for p in parameters:
        state = attempts[selected_attempt]["parameters"][p.GetName()]
        p.setVal(state["value"])
        p.setError(state["error"])
    profile_status = None
    target = class_parameters if templates is not None else [p for p in signal_parameters if not p.isConstant()]
    if "profile_parameters" in cfg:
        requested = cfg["profile_parameters"]
        available = {p.GetName(): p for p in target}
        if not isinstance(requested, list) or len(set(requested)) != len(requested) or set(requested) - set(available):
            raise ValueError("profile_parameters must uniquely name fitted class/free-SSS yields")
        target = [available[name] for name in requested]
    if cfg.get("profile", False) and target:
        profile_status = int(minimizer.minos(ROOT.RooArgSet(*target)))
    fit = (minimizer.save("mass_fit_result", "full extended mass fit") if cfg.get("profile", False)
           else selected_fit)
    fit.SetName("mass_fit_result")
    fit.SetTitle("full extended mass fit")
    final = fit.floatParsFinal()
    names = [p.GetName() for p in final]
    values = [float(p.getVal()) for p in final]
    matrix = fit.covarianceMatrix()
    covariance = np.array([[matrix[i][j] for j in range(len(names))] for i in range(len(names))])
    if templates is not None:
        indices = [names.index(p.GetName()) for p in class_parameters]
        class_cov = covariance[np.ix_(indices, indices)]
        signal_cov = templates @ class_cov @ templates.T
    else:
        class_cov = None
        signal_cov = np.zeros((n_categories, n_categories))
        for b,p in enumerate(signal_parameters):
            for d,q in enumerate(signal_parameters):
                if p.GetName() in names and q.GetName() in names:
                    signal_cov[b,d] = covariance[names.index(p.GetName()), names.index(q.GetName())]
    profiles = {}
    for parameter in target:
        name = parameter.GetName()
        lo, hi = float(parameter.getErrorLo()), float(parameter.getErrorHi())
        profiles[name] = {"value": float(parameter.getVal()), "lower_error": lo, "upper_error": hi,
            "minos_requested": bool(cfg.get("profile", False)),
            "valid": bool(cfg.get("profile", False) and profile_status == 0 and hi > 0 and lo <= 0),
            "at_lower_bound": bool(parameter.getVal() <= parameter.getMin() + 1.e-6)}
    reliable = int(fit.status()) == 0 and int(fit.covQual()) >= 3 and float(fit.edm()) < 1.e-3 and np.isfinite(covariance).all() and np.isfinite(values).all()
    reliable = bool(reliable)
    result = {
        "signal_yields": [float(p.getVal()) for p in signal_parameters],
        "signal_covariance": signal_cov.tolist(),
        "class_yields": [float(p.getVal()) for p in class_parameters] if templates is not None else None,
        "class_covariance": class_cov.tolist() if class_cov is not None else None,
        "parameter_names": names, "parameter_values": values, "parameter_covariance": covariance.tolist(),
        "background_yields": [[float(p.getVal()) for p in row[1:]] for row in all_yields],
        "profiles": profiles,
        "diagnostics": {"status": int(fit.status()), "migrad_status": int(status), "hesse_status": int(hesse_status),
            "covQual": int(fit.covQual()), "edm": float(fit.edm()), "minNll": float(fit.minNll()),
            "reliable": reliable, "warm_start": warm_start, "attempts": attempts, "migrad_steps": migrad_steps, "profile_status": profile_status, "entries_per_category": counts.tolist(),
            "initial_parameters": initial_parameters, "objective_baseline": objective_baseline,
            "unoffset_nll_baseline": raw_objective_baseline, "unoffset_nll": float(raw_objective.getVal()),
            "delta_nll": float(objective.getVal())-objective_baseline,
            "selected_attempt": selected_attempt, "minuit_precision": float(cfg.get("minuit_precision", 1.e-9)),
            "scaled_gradients": gradient_diagnostic(),
            "gradient_scope": "error-scaled objective derivative at .01/.03 fitted error; feasible one-sided near bounds; lower-bound derivative >=0 and upper-bound derivative <=0 satisfy KKT; diagnostic only",
            "empty_categories": np.flatnonzero(counts == 0).tolist(), "empty_rate_terms_included": True, "nll_offset": bool(cfg.get("nll_offset", True)),
            "minNll_scope": "sum of offset likelihoods when enabled; compare likelihood differences, not absolute values across fits",
            "empty_independent_yields": "analytical boundary MLE 0; profiled upper endpoints at deltaNLL=.5 and 1.35277 are .5 and 1.35277 events; asymptotic thresholds only, no calibrated Poisson coverage or zero-uncertainty claim",
            "shared_shape_groups": list(map(str, group_labels)), "freeze_shapes": bool(cfg.get("freeze_shapes", False)),
            "scope": "selected inclusive RECO; frozen templates; finite-MC, map and classifier uncertainty excluded"},
        "mass_config": json.loads(json.dumps(cfg, default=lambda value: value.tolist() if hasattr(value, "tolist") else str(value))),
        "mass_windows": [list(bounds) for bounds in MASS_WINDOWS],
        "resolution_multipliers": multipliers.tolist(),
        "constraint_names": [constraint.GetName() for constraint in constraints],
        "class_resolution_multipliers": None if class_scales is None else class_scales.tolist(),
        "resolution_calibration_scope": "supplied per-bin and per-class multipliers fixed; calibration uncertainty not propagated",
        "artifact_paths": {},
    }
    if output is not None:
        rootpath = output / "mass_fit.root"
        save_workspace = bool(cfg.get("save_workspace", True) or not reliable)
        if save_workspace:
            handle = ROOT.TFile(str(rootpath), "RECREATE")
            fit.Write()
            workspace = ROOT.RooWorkspace("mass_workspace")
            importer = getattr(workspace, "import")
            importer(simultaneous, ROOT.RooFit.RecycleConflictNodes())
            for constraint in constraints:
                importer(constraint, ROOT.RooFit.RecycleConflictNodes())
            for data in datasets:
                importer(data)
            workspace.Write()
            handle.Close()
        np.savez_compressed(output / "mass_fit_covariance.npz", parameter_names=np.array(names), parameter_values=values,
            parameter_covariance=covariance, signal_covariance=signal_cov, signal_yields=result["signal_yields"],
            class_covariance=np.empty((0,0)) if class_cov is None else class_cov)
        result["artifact_paths"] = {"root": str(rootpath) if save_workspace else None, "covariance": str(output / "mass_fit_covariance.npz"), "json": str(output / "mass_fit.json")}
        (output / "mass_fit.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    if not reliable and not cfg.get("allow_invalid", False):
        raise RuntimeError(f"Unreliable joint mass fit: {result['diagnostics']}")
    return result


def generate_mass_toy(class_yields, response_templates, background_yields, seed=20261110,
                      shape_config=None, shape_groups=None, resolution_multipliers=None,
                      class_resolution_multipliers=None):
    """Poisson full signal-plus-background toy generated from exact mass PDFs.

    Background order is ssb,sbs,bss,sbb,bsb,bbs,bbb. All rows are independent.
    Class -1 identifies backgrounds; mass_category retains their truth category.
    """
    ROOT = _root()
    from scripts.kinematics.fit_splot import build_jjp_mass_components
    templates = np.asarray(response_templates, float)
    yields = np.asarray(class_yields, float)
    backgrounds = np.asarray(background_yields, float)
    if templates.ndim != 2 or yields.shape != (templates.shape[1],) or backgrounds.shape != (templates.shape[0], 7):
        raise ValueError("Expected class_yields(C), templates(B,C), backgrounds(B,7)")
    _validate(np.empty((0,3)), np.empty(0,int), len(templates), templates)
    if not np.isfinite(yields).all() or not np.isfinite(backgrounds).all() or np.any(yields < 0) or np.any(backgrounds < 0):
        raise ValueError("Toy yields must be finite and nonnegative")
    class_scales = _class_scales(1. if class_resolution_multipliers is None else class_resolution_multipliers,
                                 len(templates), templates.shape[1])
    rng = np.random.default_rng(seed)
    ROOT.RooRandom.randomGenerator().SetSeed(int(seed))
    obs = _observables(ROOT)
    shape_groups = [0] * len(templates) if shape_groups is None else shape_groups
    scales = np.ones(len(templates)) if resolution_multipliers is None else np.asarray(resolution_multipliers, float)
    if len(shape_groups) != len(templates) or scales.shape != (len(templates),) or np.any(scales <= 0):
        raise ValueError("Invalid toy shape groups/resolution multipliers")
    rows, bins, labels, codes = [], [], [], []
    truth_counts = np.zeros((len(templates), 8), int)
    for b in range(len(templates)):
        cfg = dict(shape_config or {})
        cfg["values"] = dict(cfg.get("values", {}))
        for name, default in (("jpsi1_sigma", .025), ("jpsi2_sigma", .025), ("phi_sigma", .002)):
            cfg["values"][name] = cfg["values"].get(name, default) * scales[b]
        piece = build_jjp_mass_components(obs, f"toy{b}_", cfg)
        components = [(c, "sss", yields[c] * templates[b,c]) for c in range(len(yields))]
        components += [(-1, code, backgrounds[b,k]) for k,code in enumerate(MASS_CATEGORIES[1:])]
        for c, code, expected in components:
            n = int(rng.poisson(expected))
            truth_counts[b, MASS_CATEGORIES.index(code)] += n
            if not n:
                continue
            pdf = piece["components"][code]
            class_keep = []
            if c >= 0 and class_scales[b,c] != 1.:
                pdf = _scaled_signal(ROOT, obs, piece["parameters"], f"toy{b}_class{c}_",
                                     float(class_scales[b,c]), cfg, class_keep)
            data = pdf.generate(ROOT.RooArgSet(*obs), n)
            values = data.to_numpy()
            rows.append(np.column_stack([values[p.GetName()] for p in obs]))
            bins.extend([b] * n)
            labels.extend([c] * n)
            codes.extend([code] * n)
    masses = np.concatenate(rows) if rows else np.empty((0,3))
    order = rng.permutation(len(masses))
    return {"masses": masses[order], "categories": np.asarray(bins,int)[order],
        "class_label": np.asarray(labels,int)[order], "mass_category": np.asarray(codes,str)[order],
        "truth": {"class_yields": yields.tolist(), "response_templates": templates.tolist(),
            "background_yields": backgrounds.tolist(), "realized_counts": truth_counts.tolist(),
            "seed": int(seed), "shape_groups": list(shape_groups), "resolution_multipliers": scales.tolist(),
            "class_resolution_multipliers": class_scales.tolist()}}

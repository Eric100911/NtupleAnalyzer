"""Independent MC validation and disjoint adaptive template cells."""
from __future__ import annotations

import numpy as np
from scipy.linalg import solve_triangular
from scipy.optimize import nnls
from scipy.optimize import brentq
from scipy.stats import chi2


def profile_upper_limits(y, covariance, templates):
    """Approximate one-sided 95% limits in a Gaussian template likelihood.

    Uses delta chi2 = Phi^-1(.95)^2. Boundaries/estimated covariances require
    separate coverage calibration. Templates are held fixed.
    """
    lower = np.linalg.cholesky(covariance)
    design = solve_triangular(lower, templates, lower=True)
    target = solve_triangular(lower, y, lower=True)
    best, residual = nnls(design, target)
    minimum = residual**2
    threshold = 2.705543454095404
    metric = np.linalg.inv(design.T @ design)
    limits = []
    for k in range(len(best)):
        others = [j for j in range(len(best)) if j != k]

        def yield_delta(n):
            return nnls(design[:, others], target - n*design[:, k])[1]**2 - minimum

        upper = best[k] + 2*np.sqrt(max(metric[k, k], 0)) + 1
        while yield_delta(upper) < threshold:
            upper = 2*upper + 1
        nlimit = brentq(lambda n: yield_delta(n)-threshold, best[k], upper)

        def fraction_delta(f):
            # b_j parameterize total yield: N_j=(1-f)b_j, N_k=f*sum(b_j).
            matrix = (1-f)*design[:, others] + f*design[:, k, None]
            return nnls(matrix, target)[1]**2 - minimum

        fraction = best[k]/best.sum()
        flimit = (1. if fraction_delta(1.) <= threshold else
                  brentq(lambda f: fraction_delta(f)-threshold, fraction, 1.))
        limits.append({"yield_upper": float(nlimit), "fraction_upper": float(flimit)})
    return {"confidence_level": .95, "delta_chi2": threshold,
            "method": "one-sided Gaussian profile approximation; coverage not calibrated",
            "templates": "fixed", "limits": limits}


def subset(sample, indices):
    result = dict(sample)
    for key in ("x", "coordinates", "mass", "w", "row_index"):
        if key in sample:
            result[key] = sample[key][indices]
    result["selected_entries"] = len(result["x"])
    return result


def split_samples(samples, fraction, rng):
    """Disjoint event samples; use only when each row is an independent event."""
    retained, heldout = {}, {}
    for name, sample in samples.items():
        order = rng.permutation(len(sample["x"]))
        n = int(fraction * len(order))
        if n < 100 or len(order) - n < 100:
            raise ValueError(f"{name}: insufficient MC for independent splits")
        heldout[name], retained[name] = subset(sample, order[:n]), subset(sample, order[n:])
    return retained, heldout


def assign_cells(coordinates, tree):
    result = np.empty(len(coordinates), dtype=int)

    def visit(node, indices):
        if "cell" in node:
            result[indices] = node["cell"]
        else:
            left = coordinates[indices, node["axis"]] < node["threshold"]
            visit(node["left"], indices[left])
            visit(node["right"], indices[~left])
    visit(tree, np.arange(len(coordinates)))
    return result


def adaptive_cells(training, axes, max_cells=12, min_effective=40):
    """MC-only rectangular partition, preserving correlations without a grid.

    Each proposed child must have sufficient effective training MC for every
    component. Splits favor differences in component shapes. Template and
    validation MC must be independent of this training sample.
    """
    bounds = [[float(a["edges"][0]), float(a["edges"][-1])] for a in axes]
    tree = {"bounds": bounds}
    leaves = [(tree, [np.arange(len(s["x"])) for s in training.values()])]
    samples = list(training.values())
    totals = np.array([s["w"].sum() for s in samples])
    if np.any(totals <= 0):
        raise ValueError("Empty training component")
    while len(leaves) < max_cells:
        best = None
        for leaf_index, (node, indices) in enumerate(leaves):
            parent = np.array([s["w"][idx].sum() for s, idx in zip(samples, indices)])
            for axis in range(len(axes)):
                # Equal-component pooled quantiles prevent the largest MC file
                # from determining the partition on its own.
                proposals = np.unique(np.concatenate([
                    np.quantile(s["coordinates"][idx, axis], [.3, .5, .7])
                    for s, idx in zip(samples, indices) if len(idx)]))
                for cut in proposals:
                    if not node["bounds"][axis][0] < cut < node["bounds"][axis][1]:
                        continue
                    left = [idx[s["coordinates"][idx, axis] < cut] for s, idx in zip(samples, indices)]
                    right = [idx[s["coordinates"][idx, axis] >= cut] for s, idx in zip(samples, indices)]
                    acceptable = True
                    for group in (left, right):
                        for sample, idx in zip(samples, group):
                            w = sample["w"][idx]
                            if w.sum()**2 / max(np.sum(w*w), 1e-30) < min_effective:
                                acceptable = False
                    if not acceptable:
                        continue
                    h = np.array([s["w"][idx].sum() for s, idx in zip(samples, left)])
                    ratio = h / parent
                    average = ratio.mean()
                    score = np.mean(parent / totals) * np.var(ratio) / max(average*(1-average), 1e-12)
                    if best is None or score > best[0]:
                        best = (score, leaf_index, axis, float(cut), left, right)
        if best is None:
            break
        _, leaf_index, axis, cut, left, right = best
        node, _ = leaves.pop(leaf_index)
        low, high = [list(b) for b in node["bounds"]], [list(b) for b in node["bounds"]]
        low[axis][1], high[axis][0] = cut, cut
        node.update({"axis": axis, "threshold": cut, "left": {"bounds": low}, "right": {"bounds": high}})
        leaves.extend([(node["left"], left), (node["right"], right)])
    for cell, (node, _) in enumerate(leaves):
        node["cell"] = cell
    return tree, len(leaves)


def encode_samples(samples, tree):
    for sample in samples.values():
        sample["x"] = assign_cells(sample["coordinates"], tree).astype(float) + .5


def validate_templates(templates, heldout, edges, make_template,
                       rng, event_yield=2000, toys=20):
    """Pure-component and mixture closure using independent held-out MC.

    The finite-MC covariance includes both the templates and held-out shapes.
    Pure-component fits are checked with residual chi2; symmetric pulls at a
    zero-yield boundary are deliberately not interpreted as coverage tests.
    """
    reference, reference_cov = [], []
    for sample in heldout.values():
        shape, info = make_template(sample, edges)
        reference.append(shape)
        reference_cov.append(np.array(info["normalized_covariance"]))
    reference = np.column_stack(reference)
    nominal_cov = [np.array(make_template(s, edges)[1]["normalized_covariance"])
                   for s in templates.values()]
    matrix = np.column_stack([make_template(s, edges)[0] for s in templates.values()])
    k = matrix.shape[1]

    def closure_fit(observed, covariance):
        # This is an exactly quadratic objective. NNLS solves boundary cases
        # directly; closure checks need no parabolic covariance at zero yield.
        lower = np.linalg.cholesky(covariance)
        design = solve_triangular(lower, matrix, lower=True)
        target = solve_triangular(lower, observed, lower=True)
        singular = np.linalg.svd(design, compute_uv=False)
        if singular[-1] < 1e-8 * singular[0]:
            raise ValueError("Validation templates are linearly dependent")
        yields, residual = nnls(design, target)
        return {"fractions": (yields/yields.sum()).tolist(), "chi2": residual**2,
                "condition_number": float(singular[0]/singular[-1])}

    mixtures = {f"pure_{name}": np.eye(k)[i] for i, name in enumerate(templates)}
    mixtures["balanced"] = np.ones(k) / k
    # A second interior mixture prevents checking only the equal-fraction point.
    fractions = np.arange(k, 0, -1, dtype=float)
    mixtures["unequal"] = fractions / fractions.sum()
    small_index = next((i for i, name in enumerate(templates) if "SPS" in name.upper()), k-1)
    for value in (.1, .01, .001):
        fractions = np.full(k, (1-value)/(k-1))
        fractions[small_index] = value
        mixtures[f"small_SPS_{value:g}"] = fractions
    cases = {}
    for name, fractions in mixtures.items():
        truth = event_yield * fractions
        expected = reference @ truth
        mc_cov = sum(n*n*(a+b) for n, a, b in zip(truth, nominal_cov, reference_cov))
        covariance = np.diag(np.maximum(expected, 1.)) + mc_cov
        asimov = closure_fit(expected, covariance)
        dof = len(expected) - k
        pvalue = float(chi2.sf(asimov["chi2"], dof)) if dof > 0 else None
        fitted = []
        for _ in range(toys):
            observed = rng.poisson(expected).astype(float)
            fitted.append(closure_fit(observed, covariance)["fractions"])
        draws = np.array(fitted)
        cases[name] = {"truth": fractions.tolist(), "asimov_fractions": asimov["fractions"],
                       "asimov_chi2": asimov["chi2"], "ndof_nominal": dof,
                       "compatibility_p_approx": pvalue,
                       "toy_mean": draws.mean(axis=0).tolist(),
                       "toy_std": draws.std(axis=0, ddof=1).tolist(),
                       "toy_fraction_bias": (draws.mean(axis=0)-fractions).tolist(),
                       "asimov_condition": asimov["condition_number"]}
        if name.startswith("small_SPS"):
            limits = profile_upper_limits(expected, covariance, matrix)
            cases[name]["small_component"] = list(templates)[small_index]
            cases[name]["expected_fraction_upper_95_approx"] = limits["limits"][small_index]["fraction_upper"]
    return {"passed": all(c["compatibility_p_approx"] is None or c["compatibility_p_approx"] > .001
                           for c in cases.values()),
            "event_yield": event_yield, "toys_per_case": toys,
            "description": "Independent held-out MC; conditional Poisson toys, not a coverage study",
            "cases": cases}

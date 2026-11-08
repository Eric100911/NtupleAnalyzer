"""Statistical closure and schema checks for the correlation template example."""
import numpy as np
import pytest
import uproot

from scripts.templates.fit_correlation_components import (
    bin_indices, correlation_features, fit_templates, make_template, read_candidates,
)
from scripts.templates.multivariate import adaptive_cells, assign_cells, profile_upper_limits, split_samples
from scripts.templates.run_cartesian_grid_study import cartesian_bin_indices, split_indices
from scripts.templates.train_xgboost_toy import balanced_weights, score_coordinates, strict_quantile_edges


def test_gls_recovers_known_mixture_with_correlated_errors():
    templates = np.array([[.50, .05], [.25, .10], [.15, .25], [.10, .60]])
    truth = np.array([300., 700.])
    covariance = np.diag([30., 40., 50., 60.]) + 5 * np.ones((4, 4))
    result = fit_templates(templates @ truth, covariance, templates)
    np.testing.assert_allclose(result["yields"], truth, rtol=1e-4)
    # In the interior, GLS covariance is analytically known.
    expected = np.linalg.inv(templates.T @ np.linalg.solve(covariance, templates))
    np.testing.assert_allclose(result["yield_covariance_data"], expected, rtol=1e-3)
    np.testing.assert_allclose(result["fractions"], [.3, .7], rtol=1e-4)


def test_identical_templates_are_rejected():
    templates = np.array([[.2, .2], [.3, .3], [.5, .5]])
    with pytest.raises(ValueError, match="linearly dependent"):
        fit_templates(np.array([20., 30., 50.]), np.eye(3), templates)


def test_zero_component_has_nonzero_profile_upper_interval():
    templates = np.array([[.6, .1], [.3, .3], [.1, .6]])
    result = fit_templates(np.array([60., 30., 10.]), np.diag([60., 30., 10.]),
                           templates, profile=True)
    assert result["parameters_at_limit"]
    assert not result["symmetric_errors_reliable"]
    assert result["yield_profile_intervals_data_only"][1]["valid"]
    assert result["yield_profile_intervals_data_only"][1]["upper_error"] > 1.


def test_normalization_covariance_and_last_edge():
    sample = {"x": np.array([0., .4, 1., 2.]), "w": np.array([1., 2., 1., 2.])}
    shape, info = make_template(sample, np.array([0., 1., 2.]))
    np.testing.assert_allclose(shape, [.5, .5])
    covariance = np.array(info["normalized_covariance"])
    np.testing.assert_allclose(covariance.sum(axis=0), 0, atol=1e-14)
    assert covariance[0, 1] < 0  # Unit normalization induces anticorrelation.
    np.testing.assert_array_equal(bin_indices(sample["x"], [0., 1., 2.]), [0, 0, 1, 1])


def test_reader_computes_rapidity_and_orders_slots(tmp_path):
    branches = {}
    for obj, pt, mass, rapidity in [("Jpsi_1", 5., 3.09, -.7),
                                    ("Jpsi_2", 10., 3.11, 1.2), ("Phi", 3., 1.02, .2)]:
        branches.update({f"{obj}_mass": np.array([mass]), f"{obj}_px": np.array([pt]),
                         f"{obj}_py": np.array([0.]),
                         f"{obj}_pz": np.array([np.hypot(pt, mass) * np.sinh(rapidity)])})
    path = tmp_path / "selected.root"
    with uproot.recreate(path) as handle:
        handle.mktree("X_data", {key: value.dtype for key, value in branches.items()})
        handle["X_data"].extend(branches)
    sample = read_candidates({"path": str(path)},
                             {"pair": "jpsi1_phi", "variable": "abs_dy", "edges": [0, .5, 2]})
    np.testing.assert_allclose(sample["x"], [1.0])
    np.testing.assert_allclose(sample["mass"], [[3.11, 3.09, 1.02]])
    np.testing.assert_array_equal(sample["row_index"], [0])


def test_pair_and_three_body_four_vector_identities_and_delta_r():
    momentum = np.array([[[3., 0., 4.], [0., 4., -3.], [-1., 0., 2.]]])
    masses = np.array([[3.1, 3.1, 1.02]])
    features = correlation_features(momentum, masses)
    energy = np.sqrt(np.sum(momentum**2, axis=2) + masses**2).sum(axis=1)
    total = momentum.sum(axis=1)
    np.testing.assert_allclose(features[("mass", "jjp")]**2, energy**2 - np.sum(total**2, axis=1))
    np.testing.assert_allclose(features[("pt", "jjp")], np.hypot(total[:, 0], total[:, 1]))
    pair_mass2 = sum(features[("mass", pair)]**2 for pair in ("jpsi1_jpsi2", "jpsi1_phi", "jpsi2_phi"))
    np.testing.assert_allclose(pair_mass2, features[("mass", "jjp")]**2 + np.sum(masses**2, axis=1))
    eta = np.arcsinh(momentum[:, :, 2] / np.hypot(momentum[:, :, 0], momentum[:, :, 1]))
    expected = (eta[:, 0]-eta[:, 1])**2 + (np.pi/2)**2
    np.testing.assert_allclose(features[("delta_r", "jpsi1_jpsi2")]**2, expected)
    np.testing.assert_allclose(features[("sum_delta_r2", "jjp")],
        sum(features[("delta_r", pair)]**2 for pair in ("jpsi1_jpsi2", "jpsi1_phi", "jpsi2_phi")))
    assert not np.allclose(features[("delta_r", "jpsi1_jpsi2")], features[("delta_r_y", "jpsi1_jpsi2")])


def test_cell_templates_use_correlations_hidden_in_identical_marginals():
    # Both 1D marginals are flat; only the correlation separates the components.
    matrix = np.array([[.45, .05], [.05, .45], [.05, .45], [.45, .05]])
    truth = np.array([700., 300.])
    result = fit_templates(matrix @ truth, np.diag(matrix @ truth), matrix)
    np.testing.assert_allclose(result["yields"], truth, rtol=1e-4)
    marginal = matrix.reshape(2, 2, 2).sum(axis=0)
    with pytest.raises(ValueError, match="linearly dependent"):
        fit_templates(marginal @ truth, np.eye(2), marginal)


def test_adaptive_partition_assigns_each_event_once_including_boundaries():
    rng = np.random.default_rng(42)
    training = {}
    for k in range(2):
        coords = rng.normal(k, 1., (1000, 2))
        training[str(k)] = {"x": coords[:, 0], "coordinates": coords, "w": np.ones(1000)}
    axes = [{"edges": [-10, 0, 10]}, {"edges": [-10, 0, 10]}]
    tree, cells = adaptive_cells(training, axes, max_cells=6, min_effective=30)
    points = np.array([[-10, -10], [10, 10], [tree["threshold"], 0.]])
    assigned = assign_cells(points, tree)
    assert cells == 6
    assert np.all((assigned >= 0) & (assigned < cells))
    for sample in training.values():
        counts = np.bincount(assign_cells(sample["coordinates"], tree), minlength=cells)
        assert counts.min() >= 30


def test_training_and_validation_splits_have_no_shared_events():
    ids = np.arange(1000)
    sample = {"x": ids, "coordinates": ids[:, None], "w": np.ones(1000)}
    retained, heldout = split_samples({"component": sample}, .25, np.random.default_rng(1))
    assert len(heldout["component"]["x"]) == 250
    assert not np.intersect1d(retained["component"]["x"], heldout["component"]["x"]).size
    np.testing.assert_array_equal(np.sort(np.r_[retained["component"]["x"], heldout["component"]["x"]]), ids)


def test_profile_upper_limit_at_zero_matches_gaussian_one_sided_limit():
    result = profile_upper_limits(np.array([100., 0.]), np.diag([100., 25.]), np.eye(2))
    np.testing.assert_allclose(result["limits"][1]["yield_upper"], 1.64485362695147 * 5, rtol=1e-6)
    assert 0 < result["limits"][1]["fraction_upper"] < .1


def test_cartesian_grid_flattening_covers_boundaries_and_all_cells():
    edges = np.array([0., 1., 2., 3.])
    x = np.repeat(np.array([0., 1., 2., 3.]), 4)
    y = np.tile(np.array([0., 1., 2., 3.]), 4)
    bins = cartesian_bin_indices(x, y, edges, edges)
    np.testing.assert_array_equal(bins, [0, 1, 2, 2, 3, 4, 5, 5,
                                         6, 7, 8, 8, 6, 7, 8, 8])


def test_four_way_grid_split_is_disjoint_and_exhaustive():
    parts = split_indices(10000, np.random.default_rng(71))
    assert {name: len(idx) for name, idx in parts.items()} == {
        "training": 4000, "development": 1500,
        "templates": 2500, "final_validation": 2000}
    for left, names in enumerate(parts):
        for right in list(parts)[left + 1:]:
            assert not np.intersect1d(parts[names], parts[right]).size
    np.testing.assert_array_equal(np.sort(np.concatenate(list(parts.values()))), np.arange(10000))


def test_three_class_score_coordinates_handle_zero_dps_denominator():
    scores = np.array([[.2, .3, .5], [0., 0., 1.], [.8, .1, .1]])
    coordinates, zero_count = score_coordinates(scores)
    np.testing.assert_allclose(coordinates, [[.5, .4], [1., .5], [.1, 8/9]])
    assert zero_count == 1


def test_score_quantile_edges_are_strict_with_tied_values():
    edges = strict_quantile_edges(np.ones(100))
    np.testing.assert_array_equal(edges, [0., 1/3, 2/3, 1.])


def test_balanced_training_weights_equalize_class_totals_at_event_scale():
    labels = np.array([0] * 4 + [1] * 2 + [2])
    weights = balanced_weights(labels, 3)
    totals = np.array([weights[labels == i].sum() for i in range(3)])
    np.testing.assert_allclose(totals, [7/3] * 3)
    np.testing.assert_allclose(weights.mean(), 1.)

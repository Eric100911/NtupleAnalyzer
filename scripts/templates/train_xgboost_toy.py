#!/usr/bin/env python3
"""Train and validate three-class XGBoost score templates on independent toy MC."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, log_loss

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.templates.fit_correlation_components import (
    make_demo,
    make_template,
    read_candidates,
    write_json,
)
from scripts.templates.multivariate import validate_templates
from scripts.templates.run_cartesian_grid_study import cartesian_bin_indices, split_indices
from scripts.templates.run_template_study import default_observables


COMPONENTS = ("DPS1", "DPS2_CS", "SPS_CS")
SPLIT_FRACTIONS = {"training": .40, "development": .15,
                   "templates": .25, "final_validation": .20}
GEOMETRY_FEATURES = (
    "dphi_jj", "dy_jj", "dr_jj", "dphi_j1phi", "dy_j1phi", "dr_j1phi",
    "dphi_j2phi", "dy_j2phi", "dr_j2phi", "pt_jj", "pt_jjp", "absy_jjp",
    "sumpt_jjp", "sumdr2", "maxdr_jjp",
)
EXTENDED_FEATURES = GEOMETRY_FEATURES + ("m_jj", "m_j1phi", "m_j2phi", "m_jjp")
FEATURE_SETS = {"geometry_momentum": GEOMETRY_FEATURES, "extended": EXTENDED_FEATURES}


def feature_axes():
    defaults = default_observables()
    requested = {name for names in FEATURE_SETS.values() for name in names}
    axes = {}
    for name, axis in defaults.items():
        if name not in requested:
            continue
        item = dict(axis)
        variable = item["variable"]
        if variable == "abs_dphi":
            item["edges"] = [0., np.pi]
        elif variable in {"abs_dy", "delta_r", "mass", "pt", "sum_pt", "abs_y", "sum_delta_r2"}:
            item["edges"] = [0., 1e6]
        item["flow"] = "fold"
        axes[name] = item
    axes["maxdr_jjp"] = {"variable": "max_delta_r", "system": "jjp",
                         "edges": [0., 1e6], "flow": "fold",
                         "label": "maximum pair delta-R"}
    missing = requested - set(axes)
    if missing:
        raise RuntimeError(f"Missing feature definitions: {sorted(missing)}")
    return axes


def score_coordinates(scores):
    """Map three scores to a square: u=SPS, v=DPS1 fraction within DPS."""
    denominator = scores[:, 0] + scores[:, 1]
    v = np.full(len(scores), .5)
    nonzero = denominator > 0
    v[nonzero] = scores[nonzero, 0] / denominator[nonzero]
    return np.column_stack([scores[:, 2], v]), int((~nonzero).sum())


def strict_quantile_edges(values):
    edges = np.quantile(values, [0., 1/3, 2/3, 1.])
    edges[0], edges[-1] = 0., 1.
    edges = np.unique(edges)
    if len(edges) != 4:
        edges = np.array([0., 1/3, 2/3, 1.])
    return edges


def balanced_weights(labels, n_classes):
    counts = np.bincount(labels, minlength=n_classes)
    class_total = len(labels) / n_classes
    return np.asarray([class_total / counts[label] for label in labels], dtype=float)


def plot_score_distributions(output, scores_by_sample):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import mplhep as hep

    hep.style.use(hep.style.CMS)
    plot_dir = output / "score_distribution_plots"
    plot_dir.mkdir(exist_ok=False)
    edges = np.linspace(0., 1., 51)
    colors = {"DPS1": "#0072B2", "DPS2_CS": "#009E73", "SPS_CS": "#D55E00"}
    for score_index, score_name in enumerate(COMPONENTS):
        fig, ax = plt.subplots(figsize=(8, 6))
        for sample_name in COMPONENTS:
            values = scores_by_sample[sample_name][:, score_index]
            counts, _ = np.histogram(values, bins=edges)
            fraction = counts / max(counts.sum(), 1)
            ax.stairs(fraction, edges, color=colors[sample_name], linewidth=2,
                      label=sample_name)
        ax.set_xlim(0., 1.)
        ax.set_xlabel(f"XGBoost score $s_{{{score_name}}}$")
        ax.set_ylabel("Fraction of final-validation events per bin")
        ax.legend(frameon=False, loc="upper center")
        hep.cms.label(data=False, ax=ax, loc=0, rlabel="")
        fig.subplots_adjust(left=.16, right=.97, bottom=.14, top=.88)
        stem = f"score_{score_name.lower()}"
        fig.savefig(plot_dir / f"{stem}.pdf")
        fig.savefig(plot_dir / f"{stem}.png", dpi=160)
        plt.close(fig)
    return plot_dir


def toy_samples(input_dir, seed):
    config = make_demo(input_dir, seed=seed, multivariate=True)
    axes = feature_axes()
    samples = {name: read_candidates(config["components"][name],
                                     [axes[key] for key in FEATURE_SETS["extended"]],
                                     nominal_kinematics=True)
               for name in COMPONENTS}
    feature_names = FEATURE_SETS["extended"]
    matrices = {name: sample["coordinates"] for name, sample in samples.items()}
    if any(matrix.size == 0 for matrix in matrices.values()):
        raise RuntimeError("Toy MC produced no selected rows")
    return config, matrices, {name: sample["row_index"] for name, sample in samples.items()}, feature_names


def score_region_samples(model, samples, feature_indices, x_edges, y_edges):
    result, zero_denominators = {}, {}
    for name, (features, row_indices) in samples.items():
        scores = model.predict_proba(features[:, feature_indices])
        coordinates, zero = score_coordinates(scores)
        flat = cartesian_bin_indices(coordinates[:, 0], coordinates[:, 1], x_edges, y_edges)
        result[name] = {"x": flat.astype(float) + .5, "w": np.ones(len(flat)),
                        "row_index": row_indices}
        zero_denominators[name] = zero
    return result, zero_denominators


def train_models(config, matrices, row_indices, feature_names, output,
                 *, seed=12345, toys=50, event_yield=2000):
    import xgboost as xgb

    labels = {name: i for i, name in enumerate(COMPONENTS)}
    rng = np.random.default_rng(seed)
    split = {}
    split_rows = {}
    for name in COMPONENTS:
        split[name] = split_indices(len(matrices[name]), rng)
        split_rows[name] = {part: row_indices[name][idx].astype(int).tolist()
                            for part, idx in split[name].items()}
    write_json(output / "split_manifest.json", split_rows)

    reports = {}
    models = {}
    validation_scores = {}
    for feature_set, names in FEATURE_SETS.items():
        feature_indices = np.asarray([feature_names.index(name) for name in names])
        x_train = np.concatenate([matrices[name][split[name]["training"]][:, feature_indices]
                                  for name in COMPONENTS])
        y_train = np.concatenate([np.full(len(split[name]["training"]), labels[name], dtype=int)
                                  for name in COMPONENTS])
        x_dev = np.concatenate([matrices[name][split[name]["development"]][:, feature_indices]
                                for name in COMPONENTS])
        y_dev = np.concatenate([np.full(len(split[name]["development"]), labels[name], dtype=int)
                                for name in COMPONENTS])
        w_train, w_dev = balanced_weights(y_train, 3), balanced_weights(y_dev, 3)
        candidates = []
        for depth in (2, 3):
            model = xgb.XGBClassifier(
                objective="multi:softprob", num_class=3, n_estimators=1600,
                max_depth=depth, learning_rate=.05, min_child_weight=5,
                subsample=.8, colsample_bytree=.8, reg_lambda=2., reg_alpha=.05,
                eval_metric="mlogloss", tree_method="hist", random_state=seed,
                n_jobs=4, early_stopping_rounds=40,
            )
            model.fit(x_train, y_train, sample_weight=w_train,
                      eval_set=[(x_dev, y_dev)], sample_weight_eval_set=[w_dev],
                      verbose=False)
            dev_prob = model.predict_proba(x_dev)
            dev_loss = log_loss(y_dev, dev_prob, labels=[0, 1, 2], sample_weight=w_dev)
            model_name = f"{feature_set}_depth{depth}.json"
            best_iteration = int(model.best_iteration)
            model.get_booster()[:best_iteration + 1].save_model(output / model_name)
            candidates.append({"depth": depth, "model": model,
                               "development_log_loss": float(dev_loss),
                               "best_iteration": best_iteration,
                               "saved_trees": best_iteration + 1,
                               "model_file": model_name})
        chosen = min(candidates, key=lambda item: item["development_log_loss"])
        model = chosen["model"]
        models[feature_set] = (model, feature_indices)

        dev_score_parts = [model.predict_proba(matrices[name][split[name]["development"]][:, feature_indices])
                           for name in COMPONENTS]
        dev_coords = [score_coordinates(scores)[0] for scores in dev_score_parts]
        pooled = np.concatenate(dev_coords)
        u_edges = strict_quantile_edges(pooled[:, 0])
        v_edges = strict_quantile_edges(pooled[:, 1])

        validation_by_sample = {
            name: model.predict_proba(matrices[name][split[name]["final_validation"]][:, feature_indices])
            for name in COMPONENTS
        }
        validation_scores[feature_set] = validation_by_sample
        validation_x = np.concatenate([matrices[name][split[name]["final_validation"]][:, feature_indices]
                                       for name in COMPONENTS])
        validation_y = np.concatenate([np.full(len(split[name]["final_validation"]), labels[name], dtype=int)
                                       for name in COMPONENTS])
        validation_weight = balanced_weights(validation_y, 3)
        validation_prob = model.predict_proba(validation_x)
        validation_report = {
            "accuracy": float(accuracy_score(validation_y, validation_prob.argmax(axis=1),
                                             sample_weight=validation_weight)),
            "log_loss": float(log_loss(validation_y, validation_prob, labels=[0, 1, 2],
                                        sample_weight=validation_weight)),
            "confusion_matrix_counts": confusion_matrix(validation_y, validation_prob.argmax(axis=1),
                                                          labels=[0, 1, 2]).tolist(),
        }
        template_inputs = {name: (matrices[name][split[name]["templates"]][:, feature_indices],
                                  row_indices[name][split[name]["templates"]])
                           for name in COMPONENTS}
        heldout_inputs = {name: (matrices[name][split[name]["final_validation"]][:, feature_indices],
                                 row_indices[name][split[name]["final_validation"]])
                          for name in COMPONENTS}
        templates, zero_template = score_region_samples(model, template_inputs, np.arange(len(names)),
                                                       u_edges, v_edges)
        heldout, zero_heldout = score_region_samples(model, heldout_inputs, np.arange(len(names)),
                                                     u_edges, v_edges)
        validation = validate_templates(templates, heldout, np.arange(10, dtype=float),
                                        make_template, rng, event_yield, toys)
        report = {
            "feature_set": feature_set, "feature_names": list(names),
            "class_order": list(COMPONENTS), "selected_depth": chosen["depth"],
            "best_iteration": chosen["best_iteration"],
            "saved_trees": chosen["best_iteration"] + 1,
            "development_log_loss": chosen["development_log_loss"],
            "development_candidates": [{key: value for key, value in item.items()
                                         if key not in {"model"}} for item in candidates],
            "final_validation_classifier": validation_report,
            "score_coordinates": {"u": "s_SPS_CS", "v": "s_DPS1/(s_DPS1+s_DPS2_CS)",
                                  "zero_denominator_v": .5,
                                  "u_edges": u_edges.tolist(), "v_edges": v_edges.tolist()},
            "zero_dps_score_events": {"templates": zero_template, "final_validation": zero_heldout},
            "score_template_validation": validation,
        }
        reports[feature_set] = report
        np.savez(output / f"{feature_set}_score_templates.npz",
                 templates=np.column_stack([make_template(sample, np.arange(10, dtype=float))[0]
                                            for sample in templates.values()]).reshape(3, 3, 3),
                 u_edges=u_edges, v_edges=v_edges, components=np.array(COMPONENTS))
        write_json(output / f"{feature_set}_validation.json", report)

    chosen_set = min(FEATURE_SETS, key=lambda name: reports[name]["development_log_loss"])
    plot_dir = plot_score_distributions(output, validation_scores[chosen_set])
    np.savez(output / "final_validation_scores.npz",
             **validation_scores[chosen_set], class_order=np.array(COMPONENTS),
             feature_set=np.array(chosen_set))
    write_json(output / "study.json", {
        "objective": "multi:softprob", "num_class": 3,
        "class_order": list(COMPONENTS), "selected_feature_set": chosen_set,
        "split_fractions": SPLIT_FRACTIONS, "seed": seed,
        "training_weights": "equal total class weight",
        "final_validation_score_plots": str(plot_dir),
        "toy_generator": "fit_correlation_components.make_demo(multivariate=True)",
        "toy_warning": "Synthetic class shapes validate the pipeline, not JJP physics performance.",
        "feature_sets": reports,
    })
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261106)
    parser.add_argument("--toys", type=int, default=50)
    parser.add_argument("--event-yield", type=int, default=2000)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    config, matrices, row_indices, feature_names = toy_samples(args.output_dir / "toy_inputs", args.seed)
    write_json(args.output_dir / "toy_configuration.json", config)
    train_models(config, matrices, row_indices, feature_names, args.output_dir,
                 seed=args.seed, toys=args.toys, event_yield=args.event_yield)


if __name__ == "__main__":
    main()

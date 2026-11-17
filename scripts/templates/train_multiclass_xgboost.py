#!/usr/bin/env python3
"""Train three/six-class MC classifiers with explicit input and training weights."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, log_loss

REPO = Path(__file__).resolve().parents[2]
CLASS_ORDER = ("DPS1", "DPS2_CS", "DPS2_G", "SPS_CS", "SPS_G", "TPS")
CLASS_SCHEMES = {"three": ("DPS1", "DPS2_CS", "SPS_CS"), "six": CLASS_ORDER}
WEIGHT_POLICIES = ("equal-input", "balanced-class")
FRACTIONS = {"training": .40, "development": .15, "templates": .25,
             "final_validation": .20}
FEATURE_NAMES = ("jpsi1_pt", "jpsi2_pt", "phi_pt", "score3")
PARQUET_COLUMNS = {
    "jpsi1_pt": "reco_best_jpsi1_pt",
    "jpsi2_pt": "reco_best_jpsi2_pt",
    "phi_pt": "reco_best_phi_pt",
    "score3": "reco_best_score",
}
NTUPLE_COLUMNS = {
    "jpsi1_pt": "Jpsi_1_pt",
    "jpsi2_pt": "Jpsi_2_pt",
    "phi_pt": "Phi_pt",
}


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


def _valid_rows(features: dict[str, np.ndarray], mask: np.ndarray) -> np.ndarray:
    matrix = np.column_stack([features[name] for name in FEATURE_NAMES])
    mask = mask & np.all(np.isfinite(matrix), axis=1)
    mask &= np.all(matrix[:, :3] > 0, axis=1)
    return mask


def read_parquet_sample(spec: dict) -> dict:
    warnings.warn(
        "Deprecated classifier input: efficiency-event parquet provides only three independent RECO pT inputs "
        "(score3 is deterministic). For the full ROOT correlation classifier use "
        "scripts/templates/train_full_correlation_xgboost.py; see docs/Full_Correlation_XGBoost_20261109.md. "
        "This does not deprecate efficiency parquet products or full-feature caches.",
        FutureWarning, stacklevel=2,
    )
    path = Path(spec["path"])
    required = [*PARQUET_COLUMNS.values(), "source_file", "entry", "reco_best_is_gen_matched"]
    frame = pd.read_parquet(path, columns=required)
    features = {name: frame[column].to_numpy(dtype=float, na_value=np.nan)
                for name, column in PARQUET_COLUMNS.items()}
    # The efficiency parquet stores sum(pT^2), while selected ntuples use Score3.
    features["score3"] = np.sqrt(np.maximum(features["score3"], 0.0))
    matched = frame["reco_best_is_gen_matched"].fillna(False).to_numpy(dtype=bool)
    valid = _valid_rows(features, matched)
    source = frame["source_file"].fillna("").astype(str).to_numpy()
    entry = frame["entry"].to_numpy(dtype=np.int64)
    return _pack_sample(spec, features, valid, source, entry, len(frame))


def read_selected_ntuple_sample(spec: dict) -> dict:
    import uproot

    files = [Path(item) for item in spec.get("files", [spec.get("path")]) if item]
    if not files:
        raise ValueError("selected_ntuple input requires path or files")
    prefix = spec.get("prefix", "sel_")
    tree_name = spec.get("tree", "selected")
    arrays_by_feature = {name: [] for name in FEATURE_NAMES[:3]}
    source_parts, entry_parts, match_parts = [], [], []
    total_rows = 0
    for path in files:
        with uproot.open(path, handler=uproot.source.file.MultithreadedFileSource,
                          num_workers=1) as root_file:
            tree = root_file[tree_name]
            branches = [prefix + NTUPLE_COLUMNS[name] for name in FEATURE_NAMES[:3]]
            match_branch = spec.get("match_branch")
            branches += [match_branch] if match_branch else []
            arrays = tree.arrays(branches, library="np")
        n_rows = len(arrays[branches[0]])
        for name, branch in zip(FEATURE_NAMES[:3], branches[:3]):
            arrays_by_feature[name].append(np.asarray(arrays[branch], dtype=float))
        source_parts.append(np.full(n_rows, str(path.resolve()), dtype=object))
        entry_parts.append(np.arange(n_rows, dtype=np.int64))
        if match_branch:
            match_parts.append(np.asarray(arrays[match_branch], dtype=bool))
        total_rows += n_rows
    features = {name: np.concatenate(parts) for name, parts in arrays_by_feature.items()}
    features["score3"] = np.sqrt(sum(features[name] ** 2 for name in FEATURE_NAMES[:3]))
    if match_parts:
        matched = np.concatenate(match_parts)
    elif spec.get("preselected_truth_matched") is True:
        matched = np.ones(total_rows, dtype=bool)
    else:
        raise ValueError("selected_ntuple input needs match_branch or explicit preselected_truth_matched=true")
    valid = _valid_rows(features, matched)
    return _pack_sample(spec, features, valid, np.concatenate(source_parts),
                        np.concatenate(entry_parts), total_rows)


def _pack_sample(spec, features, valid, source, entry, total_rows):
    matrix = np.column_stack([features[name] for name in FEATURE_NAMES])
    reordered = matrix[:, 1] > matrix[:, 0]
    matrix[:, :2] = np.sort(matrix[:, :2], axis=1)[:, ::-1]
    expected_score = np.sqrt(np.sum(matrix[:, :3] ** 2, axis=1))
    if not np.allclose(matrix[valid, 3], expected_score[valid], rtol=2e-6, atol=1e-6):
        raise ValueError("score3 is inconsistent with the three RECO pT values")
    source = np.asarray(source, dtype=str)
    # Integer keys keep source-file/entry grouping compact for large parquet samples.
    source_codes, _ = pd.factorize(source, sort=False)
    groups = np.empty(len(source), dtype=[("source", np.int32), ("entry", np.int64)])
    groups["source"] = source_codes
    groups["entry"] = np.asarray(entry, dtype=np.int64)
    return {
        "features": matrix[valid], "groups": groups[valid],
        "source_file": source[valid], "entry": np.asarray(entry)[valid],
        "input_rows": int(total_rows), "matched_rows": int(valid.sum()),
        "reordered_jpsi_rows": int(np.count_nonzero(reordered & valid)),
        "kind": spec["kind"], "path": spec.get("path"),
        "files": spec.get("files"),
    }


def read_sample(spec: dict) -> dict:
    if spec["kind"] == "parquet":
        return read_parquet_sample(spec)
    if spec["kind"] == "selected_ntuple":
        return read_selected_ntuple_sample(spec)
    raise ValueError(f"Unsupported input kind: {spec['kind']}")


def grouped_split(groups: np.ndarray, seed: int) -> dict[str, np.ndarray]:
    """Assign source-file/entry groups to disjoint, approximately sized partitions."""
    rng = np.random.default_rng(seed)
    unique, inverse = np.unique(groups, return_inverse=True)
    partitions = {name: [] for name in FRACTIONS}
    targets = np.cumsum([FRACTIONS[name] for name in FRACTIONS])[:-1] * len(groups)
    if len(unique) == len(groups):
        shuffled = rng.permutation(len(groups))
        boundaries = np.rint(targets).astype(int)
        chunks = np.split(shuffled, boundaries)
        return {name: chunk.astype(int) for name, chunk in zip(FRACTIONS, chunks)}

    current, target_index = 0, 0
    row_order = np.argsort(inverse, kind="stable")
    counts = np.bincount(inverse, minlength=len(unique))
    offsets = np.concatenate(([0], np.cumsum(counts)))
    row_groups = [row_order[offsets[i]:offsets[i + 1]] for i in rng.permutation(len(unique))]
    for rows in row_groups:
        if target_index < len(targets) and current >= targets[target_index]:
            target_index += 1
        name = list(FRACTIONS)[target_index]
        partitions[name].extend(np.asarray(rows, dtype=int).tolist())
        current += len(rows)
    result = {name: np.asarray(rows, dtype=int) for name, rows in partitions.items()}
    if any(len(result[name]) == 0 for name in FRACTIONS):
        raise ValueError("A grouped split produced an empty partition")
    return result


def balanced_weights(labels: np.ndarray, n_classes: int) -> np.ndarray:
    counts = np.bincount(labels, minlength=n_classes)
    if np.any(counts == 0):
        raise ValueError(f"Missing class in training partition: {counts.tolist()}")
    return len(labels) / (n_classes * counts[labels])


def load_manifest(path: Path | None, parquet_root: Path | None,
                  class_order=CLASS_ORDER) -> dict:
    if path:
        payload = json.loads(path.read_text())
        samples = payload.get("samples", payload)
    else:
        manifest_path = parquet_root / "manifest.json"
        root_manifest = json.loads(manifest_path.read_text())
        if root_manifest.get("analyzer_commit") != "163f64d856a4de455b31c87771bde882492c422a":
            raise ValueError("Parquet manifest is not from the requested pinned analyzer commit")
        sample_paths = root_manifest["artifacts"]["samples"]
        samples = {
            name.removeprefix("JJP_"): {
                "kind": "parquet",
                "path": str(parquet_root / Path(rel).parent / "event_step_flags.parquet"),
            }
            for name, rel in sample_paths.items()
        }
        payload = {"source_manifest": str(manifest_path)}
    missing = set(class_order) - set(samples)
    if missing:
        raise ValueError(f"Input manifest is missing classes: {sorted(missing)}")
    return {"source_manifest": payload.get("source_manifest", str(path) if path else None),
            "samples": samples}


def policy_weights(labels, input_weights, n_classes, policy):
    """Keep exposure weights separate; return objective weights with mean one."""
    labels, weights = np.asarray(labels), np.asarray(input_weights, dtype=float).copy()
    if len(weights) != len(labels) or not len(weights):
        raise ValueError("Weights and labels must have the same nonzero length")
    if np.any(~np.isfinite(weights)) or np.any(weights <= 0):
        raise ValueError("Input weights must be finite and positive")
    if policy == "balanced-class":
        totals = np.bincount(labels, weights=weights, minlength=n_classes)
        if np.any(totals <= 0):
            raise ValueError("Every class must occur in the weighted partition")
        weights /= totals[labels]
    elif policy != "equal-input":
        raise ValueError(f"Unknown weight policy: {policy}")
    return weights / weights.mean()


def weight_summary(weights):
    weights = np.asarray(weights, dtype=float)
    total, squared = float(weights.sum()), float(np.dot(weights, weights))
    return {"rows": len(weights), "sum_weights": total,
            "sum_squared_weights": squared,
            "effective_entries": total ** 2 / squared if squared else 0.}


def attach_kinematic_weights(samples, path):
    """Join frozen RECO weights by exact event identity, never by row position."""
    saved = pd.read_parquet(path)
    keys = ["sample", "source_file", "entry"]
    values = ["phi_shape_weight", "phi_pt", "phi_y"]
    if not set(keys + values).issubset(saved.columns):
        raise ValueError("Kinematic weights lack event identities or RECO phi weight/coordinates")
    if saved.duplicated(keys).any():
        raise ValueError("Kinematic weight event identities must be unique")
    for name, sample in samples.items():
        current = pd.DataFrame({"sample": name, "source_file": sample["source_file"],
                                "entry": sample["entry"]})
        selected = saved.loc[saved["sample"] == name, keys + values]
        if not current[keys].value_counts().sort_index().equals(selected[keys].value_counts().sort_index()):
            raise ValueError(f"Kinematic weights do not exactly cover selected rows for {name}")
        joined = current.merge(selected, on=keys, how="left", validate="one_to_one")
        array = joined[values].to_numpy(dtype=float)
        if not np.all(np.isfinite(array)) or np.any(array[:, 0] <= 0):
            raise ValueError(f"Kinematic weights and RECO coordinates must be finite; weights positive: {name}")
        if not np.allclose(array[:, 1], sample["features"][:, 2], rtol=2e-6, atol=1e-6):
            raise ValueError(f"RECO phi pT differs from classifier selection for {name}")
        for column in values:
            sample[column] = joined[column].to_numpy(dtype=float)


def reuse_split(samples, path):
    """Reuse event assignments only when the complete selected row multiset agrees."""
    saved = pd.read_parquet(path)
    required = ["sample", "source_file", "entry", "partition"]
    if not set(required).issubset(saved.columns):
        raise ValueError("Split manifest lacks event identities or partitions")
    result = {}
    for name, sample in samples.items():
        old = saved.loc[saved["sample"] == name, required[1:]].copy()
        keys = ["source_file", "entry"]
        if not old["partition"].isin(FRACTIONS).all():
            raise ValueError(f"Unknown partition in split manifest for {name}")
        if (old.groupby(keys)["partition"].nunique() > 1).any():
            raise ValueError(f"Split manifest leaks an event across partitions: {name}")
        current = pd.DataFrame({"source_file": sample["source_file"], "entry": sample["entry"]})
        if not current.value_counts().sort_index().equals(old[keys].value_counts().sort_index()):
            raise ValueError(f"Selected event identities changed for {name}; cannot reuse split")
        joined = current.merge(old.drop_duplicates(keys), on=keys, how="left", validate="many_to_one")
        result[name] = {part: np.flatnonzero(joined["partition"].to_numpy() == part)
                        for part in FRACTIONS}
    return result


def validate_split(samples, split):
    ownership = {}
    for name, sample in samples.items():
        all_indices = np.concatenate(list(split[name].values()))
        if not np.array_equal(np.sort(all_indices), np.arange(len(sample["features"]))):
            raise ValueError(f"Split does not cover each row exactly once: {name}")
        for part, indices in split[name].items():
            if not len(indices):
                raise ValueError(f"Empty {part} partition for {name}")
            for idx in indices:
                key = (str(sample["source_file"][idx]), int(sample["entry"][idx]))
                previous = ownership.setdefault(key, (name, part))
                if previous != (name, part):
                    raise ValueError(f"Event shared across classes or partitions: {key}")


def load_normalization(path, class_order):
    payload = json.loads(path.read_text())
    reference = float(payload["reference_input_entries"])
    if not np.isfinite(reference) or reference <= 0:
        raise ValueError("Reference input exposure must be positive")
    for name in class_order:
        spec = payload["samples"][name]
        count = spec["source_entries"]
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValueError(f"Invalid covered source-entry denominator for {name}")
        if spec.get("generator_weight_convention") != "unit-counted-stored-events":
            raise ValueError(f"{name}: establish generator normalization before using event counts")
        if not spec.get("denominator_source"):
            raise ValueError(f"{name}: missing denominator provenance")
    return payload


def partition_frame(samples, split, class_order, normalization, part):
    frames = []
    for label, name in enumerate(class_order):
        sample, indices = samples[name], split[name][part]
        frame = pd.DataFrame(sample["features"][indices], columns=FEATURE_NAMES)
        frame["sample"], frame["label"], frame["partition"] = name, label, part
        frame["source_file"] = sample["source_file"][indices]
        frame["entry"] = sample["entry"][indices]
        frame["input_weight"] = (normalization["reference_input_entries"] /
                                 normalization["samples"][name]["source_entries"])
        frame["gen_weight"] = 1.
        frame["phi_shape_weight"] = sample.get("phi_shape_weight", np.ones(sample["matched_rows"]))[indices]
        frame["base_weight"] = frame["input_weight"] * frame["phi_shape_weight"]
        if "phi_y" in sample:
            frame["phi_y"] = sample["phi_y"][indices]
        # Realized selected-row sampling fractions restore full selected totals.
        q = len(indices) / sample["matched_rows"]
        frame["partition_fraction_realized"] = q
        frame["rate_weight"] = frame["base_weight"] / q
        frame["shape_weight"] = frame["base_weight"] / frame["base_weight"].sum()
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def classifier_metrics(labels, scores, input_weights, class_order):
    n_classes = len(class_order)
    predictions = scores.argmax(axis=1)
    balanced = balanced_weights(labels, n_classes)
    matrix = confusion_matrix(labels, predictions, labels=np.arange(n_classes))
    return {
        "rows": len(labels),
        "ordinary_accuracy": float(accuracy_score(labels, predictions)),
        "ordinary_log_loss": float(log_loss(labels, scores, labels=np.arange(n_classes))),
        "balanced_accuracy": float(accuracy_score(labels, predictions, sample_weight=balanced)),
        "balanced_log_loss": float(log_loss(labels, scores, labels=np.arange(n_classes), sample_weight=balanced)),
        "input_normalized_accuracy": float(accuracy_score(labels, predictions, sample_weight=input_weights)),
        "input_normalized_log_loss": float(log_loss(labels, scores, labels=np.arange(n_classes), sample_weight=input_weights)),
        "confusion_matrix_counts": matrix.tolist(),
        "per_class_rows": dict(zip(class_order, matrix.sum(axis=1).astype(int).tolist())),
        "per_class_recall": dict(zip(class_order, (matrix.diagonal() / matrix.sum(axis=1)).tolist())),
    }


def save_scores(path, booster, frame, class_order):
    import xgboost as xgb

    features = frame.loc[:, list(FEATURE_NAMES)].to_numpy(dtype=float)
    scores = booster.predict(xgb.DMatrix(features))
    if not np.all(np.isfinite(scores)) or not np.allclose(scores.sum(axis=1), 1., atol=1e-6):
        raise ValueError("Invalid class probabilities from saved model")
    np.savez_compressed(path, scores=scores, features=features,
                        labels=frame["label"].to_numpy(dtype=int),
                        class_order=np.asarray(class_order), feature_names=np.asarray(FEATURE_NAMES),
                        **{key: frame[key].to_numpy(dtype=str if key in {"sample", "source_file", "partition"} else None)
                           for key in ("sample", "source_file", "entry", "partition", "input_weight", "gen_weight",
                                       "phi_shape_weight", "base_weight", "training_weight", "objective_weight",
                                       "rate_weight", "shape_weight", "partition_fraction_realized", "phi_y") if key in frame})
    return scores


def run_training(args):
    import xgboost as xgb

    class_order = CLASS_SCHEMES[args.class_scheme]
    policies = WEIGHT_POLICIES if args.weight_policy == "both" else (args.weight_policy,)
    manifest = load_manifest(args.input_manifest, args.parquet_root, class_order)
    normalization = load_normalization(args.normalization_manifest, class_order)
    samples = {name: read_sample(manifest["samples"][name]) for name in class_order}
    kinematic_weights = getattr(args, "kinematic_weights", None)
    if kinematic_weights:
        if not args.split_manifest:
            raise ValueError("Kinematic reweighting requires the original split manifest")
        attach_kinematic_weights(samples, kinematic_weights)
    if args.split_manifest:
        split = reuse_split(samples, args.split_manifest)
    else:
        split = {name: grouped_split(sample["groups"], args.seed + CLASS_ORDER.index(name))
                 for name, sample in samples.items()}
    validate_split(samples, split)
    frames = {part: partition_frame(samples, split, class_order, normalization, part)
              for part in FRACTIONS}
    counts = {name: {"efficiency_or_selected_rows": samples[name]["input_rows"],
                     "truth_matched_feature_rows": samples[name]["matched_rows"],
                     "reordered_jpsi_rows": samples[name]["reordered_jpsi_rows"],
                     "source_entries": normalization["samples"][name]["source_entries"],
                     **{part: len(indices) for part, indices in split[name].items()}}
              for name in class_order}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    all_rows = pd.concat(frames.values(), ignore_index=True)
    all_rows.to_parquet(args.output_dir / "split_manifest.parquet", index=False)
    write_json(args.output_dir / "input_normalization.json", normalization)
    x_train = frames["training"].loc[:, list(FEATURE_NAMES)].to_numpy(dtype=float)
    x_dev = frames["development"].loc[:, list(FEATURE_NAMES)].to_numpy(dtype=float)
    y_train = frames["training"]["label"].to_numpy(dtype=int)
    y_dev = frames["development"]["label"].to_numpy(dtype=int)
    frozen = {}
    for policy in policies:
        w_train = policy_weights(y_train, frames["training"]["base_weight"], len(class_order), policy)
        w_dev = policy_weights(y_dev, frames["development"]["base_weight"], len(class_order), policy)
        candidates = []
        for depth in (2, 3):
            model = xgb.XGBClassifier(
                objective="multi:softprob", num_class=len(class_order),
                n_estimators=args.n_estimators, max_depth=depth,
                learning_rate=.04, min_child_weight=5, subsample=.8,
                colsample_bytree=.9, reg_lambda=2., reg_alpha=.05,
                eval_metric="mlogloss", tree_method="hist", random_state=args.seed,
                n_jobs=args.jobs, early_stopping_rounds=35,
            )
            model.fit(x_train, y_train, sample_weight=w_train,
                      eval_set=[(x_dev, y_dev)], sample_weight_eval_set=[w_dev], verbose=False)
            scores = model.predict_proba(x_dev)
            loss = float(log_loss(y_dev, scores, labels=np.arange(len(class_order)), sample_weight=w_dev))
            candidates.append({"depth": depth, "model": model,
                               "development_policy_log_loss": loss,
                               "development_metrics": classifier_metrics(y_dev, scores, frames["development"]["input_weight"], class_order),
                               "best_iteration": int(model.best_iteration)})
        best_loss = min(item["development_policy_log_loss"] for item in candidates)
        # Declare a modest tolerance before validation; near ties favor simpler trees.
        chosen = min((item for item in candidates if item["development_policy_log_loss"] <= best_loss + args.depth_tie_tolerance),
                     key=lambda item: item["depth"])
        model_dir = args.output_dir / policy
        model_dir.mkdir()
        model_path = model_dir / f"{args.class_scheme}_class_xgboost.json"
        booster = chosen["model"].get_booster()[:chosen["best_iteration"] + 1]
        booster.save_model(model_path)
        loaded = xgb.Booster()
        loaded.load_model(model_path)
        difference = float(np.max(np.abs(loaded.predict(xgb.DMatrix(x_dev)) - chosen["model"].predict_proba(x_dev))))
        if difference > 1e-7:
            raise ValueError(f"Saved-model prediction mismatch: {difference}")
        # Apply the *training* objective transform to saved events in every partition.
        factors = {label: float(w_train[y_train == label][0] /
                                frames["training"].loc[y_train == label, "base_weight"].iloc[0])
                   for label in range(len(class_order))}
        weighted_frames = {}
        bookkeeping = {}
        for part, frame in frames.items():
            weighted = frame.copy()
            weighted["training_weight"] = weighted["base_weight"] * weighted["label"].map(factors)
            weighted["objective_weight"] = (w_dev if part == "development" else weighted["training_weight"])
            weighted_frames[part] = weighted
            bookkeeping[part] = {name: {
                **{key: weight_summary(weighted.loc[weighted["sample"] == name, key])
                   for key in ("input_weight", "gen_weight", "phi_shape_weight", "base_weight", "training_weight", "objective_weight", "rate_weight", "shape_weight")},
                "partition_fraction_realized": len(split[name][part]) / samples[name]["matched_rows"],
            } for name in class_order}
        pd.concat(weighted_frames.values(), ignore_index=True).to_parquet(model_dir / "event_weights.parquet", index=False)
        frozen[policy] = {
            "booster": loaded, "frames": weighted_frames,
            "selection": {"selected_depth": chosen["depth"], "best_iteration": chosen["best_iteration"],
                          "boosting_rounds": chosen["best_iteration"] + 1,
                          "individual_trees": len(loaded.get_dump()),
                          "development_policy_log_loss": chosen["development_policy_log_loss"],
                          "development_candidates": [{key: value for key, value in item.items() if key != "model"} for item in candidates]},
            "bookkeeping": bookkeeping, "saved_model_max_prediction_difference": difference,
        }
        print(f"Frozen {args.class_scheme}-class {policy}: depth={chosen['depth']}, rounds={chosen['best_iteration'] + 1}", flush=True)
    # All declared policies and depth choices are frozen before reading validation scores.
    write_json(args.output_dir / "frozen_study.json", {
        "class_order": class_order, "weight_policies": policies,
        "selection_uses": "development only; minimum policy-weighted loss with depth tie tolerance",
        "depth_tie_tolerance": args.depth_tie_tolerance,
        "policy_comparison": "report both frozen policies; no winner chosen from final validation",
        "feature_names": FEATURE_NAMES,
        "models": {policy: item["selection"] for policy, item in frozen.items()},
    })
    comparison = {}
    for policy, item in frozen.items():
        model_dir = args.output_dir / policy
        for part, filename in (("templates", "heldout_template_scores.npz"),
                               ("final_validation", "final_validation_scores.npz")):
            scores = save_scores(model_dir / filename, item["booster"], item["frames"][part], class_order)
            if part == "final_validation":
                metrics = classifier_metrics(item["frames"][part]["label"].to_numpy(dtype=int), scores,
                                             item["frames"][part]["input_weight"], class_order)
                shape_metrics = classifier_metrics(item["frames"][part]["label"].to_numpy(dtype=int), scores,
                                                   item["frames"][part]["base_weight"], class_order)
                metrics["phi_reweighted_accuracy"] = shape_metrics["input_normalized_accuracy"]
                metrics["phi_reweighted_log_loss"] = shape_metrics["input_normalized_log_loss"]
                balanced_shape = policy_weights(item["frames"][part]["label"].to_numpy(dtype=int),
                                                item["frames"][part]["base_weight"], len(class_order), "balanced-class")
                metrics["phi_reweighted_balanced_accuracy"] = float(accuracy_score(
                    item["frames"][part]["label"], scores.argmax(axis=1), sample_weight=balanced_shape))
                metrics["phi_reweighted_balanced_log_loss"] = float(log_loss(
                    item["frames"][part]["label"], scores, labels=np.arange(len(class_order)), sample_weight=balanced_shape))
        comparison[policy] = metrics
        report = {
            "class_order": class_order, "feature_names": FEATURE_NAMES, "seed": args.seed,
            "xgboost_version": xgb.__version__, "weight_policy": policy,
            "feature_note": "J/psi pT sorted descending in both adapters; score3 is a deterministic combination, not independent information",
            "split_fractions_nominal": FRACTIONS, "rate_expansion": "realized selected-row fraction per class and partition",
            "split_group": "source_file + entry", "split_reused_from": str(args.split_manifest) if args.split_manifest else None,
            "input_source_manifest": manifest["source_manifest"], "sample_input_specs": manifest["samples"],
            "normalization_manifest": str(args.normalization_manifest),
            "input_normalization": normalization,
            "kinematic_weights": str(kinematic_weights) if kinematic_weights else None,
            "generator_weight_assumption": "gen_weight=1; explicit counted-event convention, not verified generator cross-section normalization",
            "base_weight_definition": "input_weight * phi_shape_weight; input_weight remains N_reference/N_source",
            "kinematic_rate_definition": "base_weight / original realized partition fraction; a shape-reweighted exposure estimate, not physical component yields",
            "training_row_filter": "GEN matching retained; match flags never enter features",
            "candidate_definition": "unchanged efficiency reco_best quality and ranking; raw/selected-data compatibility audit recorded separately",
            "counts": counts, "training_rows": len(y_train), "development_rows": len(y_dev),
            "training_weights": "base_weight globally rescaled to mean 1" if policy == "equal-input" else "base_weight divided by class weighted training total, globally rescaled to mean 1",
            "saved_objective_weights": "training_weight applies training-derived class/global factors in all partitions; objective_weight uses development-derived factors on development for the actual early-stopping objective",
            "development_early_stopping_weights": "same policy, normalized within development partition",
            "metric_weights": {"balanced": "equal total metric weight per class",
                               "input_normalized": "N_reference / covered source entries; same weights for all policy evaluations",
                               "ordinary": "unit event weights"},
            "baselines": {"uniform_balanced_accuracy": 1 / len(class_order), "uniform_log_loss": float(np.log(len(class_order)))},
            **item["selection"], "weight_bookkeeping": item["bookkeeping"],
            "checks": {"split_disjoint_and_complete": True, "training_mean_weight": float(item["frames"]["training"]["training_weight"].mean()),
                       "saved_model_max_prediction_difference": item["saved_model_max_prediction_difference"]},
            "final_validation": metrics,
            "score_templates": "independent template scores with unit-area per-class shape_weight, input_weight, rate_weight and event IDs; no template-statistical gain from constant weights",
            "limitations": ["Final-validation events were used by the earlier six-class study; this is a declared fixed re-evaluation, not a new blind sample.",
                            "SPS_CS has limited MC statistics; templates require statistical uncertainty in subsequent mixture fits.",
                            "Data scoring, mass-sculpting checks, mass fits, and mixture closure are outside this MC training run."],
        }
        if kinematic_weights:
            report["limitations"].extend([
                "Phi maps are frozen from training MC; data-derived target and finite-map uncertainty are not propagated by this training run.",
                "Nonconstant shape weights can reduce effective statistics; sumw/sumw2/ESS are saved, and no new MC information is implied.",
                "Original final-validation events are reused for a fixed comparison, not a fresh blind evaluation or policy selection.",
            ])
        write_json(model_dir / "trial_report.json", report)
    write_json(args.output_dir / "policy_comparison.json", {
        "class_order": class_order,
        "comparison_weights": "identical event assignments and identical balanced/input-normalized metric weights for both frozen policies",
        "final_validation": comparison,
    })
    print(json.dumps(comparison, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--parquet-root", type=Path,
                        help="DEPRECATED classifier-only input: efficiency parquet with 3 independent pT features; use train_full_correlation_xgboost.py --raw-root for full correlations")
    source.add_argument("--input-manifest", type=Path,
                        help="JSON manifest for parquet and/or selected_ntuple sample inputs")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261109)
    parser.add_argument("--n-estimators", type=int, default=1200)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--class-scheme", choices=CLASS_SCHEMES, default="six")
    parser.add_argument("--weight-policy", choices=(*WEIGHT_POLICIES, "both"), default="both")
    parser.add_argument("--normalization-manifest", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, help="Reuse exact selected-event assignments from an existing study")
    parser.add_argument("--kinematic-weights", type=Path, help="Frozen event-keyed RECO phi shape weights parquet; requires original split")
    parser.add_argument("--depth-tie-tolerance", type=float, default=.001)
    args = parser.parse_args()
    if args.n_estimators < 1 or args.jobs < 1 or not np.isfinite(args.depth_tie_tolerance) or args.depth_tie_tolerance < 0:
        parser.error("estimators/jobs must be positive and depth tie tolerance finite and nonnegative")
    run_training(args)


if __name__ == "__main__":
    main()

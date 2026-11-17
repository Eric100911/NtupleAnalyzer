#!/usr/bin/env python3
"""Physical ROOT JJP six-class training with full RECO correlations and histories.

Run under LCG109a. The cache is a new complete feature product, never a reader
of the historical four-column efficiency parquet interface. No toy inputs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.templates.fit_correlation_components import correlation_features
from scripts.templates.train_multiclass_xgboost import CLASS_ORDER, FRACTIONS, policy_weights, classifier_metrics
from scripts.templates.phi_kinematic_reweight import build_weights, data_target, rapidity

GEOMETRY_FEATURES = (
    "dphi_jj", "dy_jj", "dr_jj", "dphi_j1phi", "dy_j1phi", "dr_j1phi",
    "dphi_j2phi", "dy_j2phi", "dr_j2phi", "pt_jj", "pt_jjp", "absy_jjp",
    "sumpt_jjp", "sumdr2", "maxdr_jjp",
)
EXTENDED_FEATURES = GEOMETRY_FEATURES + ("m_jj", "m_j1phi", "m_j2phi", "m_jjp")
FEATURE_NAMES = EXTENDED_FEATURES + ("jpsi1_pt", "jpsi2_pt", "phi_pt")
NOMINAL_MASSES = (3.0969, 3.0969, 1.01946)
OBJECTS = ("Jpsi_1", "Jpsi_2", "Phi")
KEYS = ["sample", "source_file", "entry"]
SELECTION = {
    "implementation": "ntuple_pipeline_common.declare_rdf_helpers: BestCandIndexJJP; PassSelectedJJPGenMatch AFTER best candidate",
    "muon_id": "muIsPatSoftMuon", "jpsi_mass_window": [2.9, 3.3],
    "phi_mass_window": [.99, 1.07], "jpsi_pt_strict_min": 6.,
    "jpsi_abs_y_strict_max": 2.5, "phi_pt_strict_min": 4.,
    "phi_abs_eta_strict_max": 2.5, "kaon_pt_strict_min": 2.,
    "kaon_abs_eta_strict_max": 2.5, "muon_abs_eta_strict_max": 2.4,
    "muon_pt_barrel_strict_min": 3.5, "muon_pt_endcap_strict_min": 2.5,
    "muon_barrel_abs_eta_boundary": 1.2,
    "ranking": "first maximum Score3=sqrt(sum object pT squared), among data-like candidates, then require selected candidate truth match",
    "no_additional_cuts": "no efficiency-reco_best vertex/kaon-quality requirements, no HLT/DiOnia/Pri cut added; uses shared Pipeline 1 selector",
    "sample_change": "Fresh physical ROOT data-like sample, differs from old efficiency reco_best sample; not a feature-only comparison",
}


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def feature_frame(momentum, measured_masses):
    """22 inputs from nominal-mass fourvectors; measured masses remain QA-only."""
    momentum = np.asarray(momentum, dtype=float).copy()
    measured_masses = np.asarray(measured_masses, dtype=float).copy()
    if momentum.ndim != 3 or momentum.shape[1:] != (3, 3) or measured_masses.shape != momentum.shape[:2]:
        raise ValueError("Expected momentum(n,3,3) and masses(n,3)")
    if not np.isfinite(momentum).all() or not np.isfinite(measured_masses).all():
        raise ValueError("Nonfinite measured fourvector")
    pt = np.hypot(momentum[:, :, 0], momentum[:, :, 1])
    swap = pt[:, 1] > pt[:, 0]
    momentum[swap, :2] = momentum[swap, :2][:, ::-1]
    measured_masses[swap, :2] = measured_masses[swap, :2][:, ::-1]
    pt = np.hypot(momentum[:, :, 0], momentum[:, :, 1])
    values = correlation_features(momentum, np.broadcast_to(NOMINAL_MASSES, pt.shape))
    output = {}
    for suffix, pair in (("jj", "jpsi1_jpsi2"), ("j1phi", "jpsi1_phi"), ("j2phi", "jpsi2_phi")):
        for short, variable in (("dphi", "abs_dphi"), ("dy", "abs_dy"), ("dr", "delta_r")):
            output[f"{short}_{suffix}"] = values[variable, pair]
    for name, variable, system in (
        ("pt_jj", "pt", "jpsi1_jpsi2"), ("pt_jjp", "pt", "jjp"),
        ("absy_jjp", "abs_y", "jjp"), ("sumpt_jjp", "sum_pt", "jjp"),
        ("sumdr2", "sum_delta_r2", "jjp"), ("maxdr_jjp", "max_delta_r", "jjp"),
        ("m_jj", "mass", "jpsi1_jpsi2"), ("m_j1phi", "mass", "jpsi1_phi"),
        ("m_j2phi", "mass", "jpsi2_phi"), ("m_jjp", "mass", "jjp")):
        output[name] = values[variable, system]
    for i, name in enumerate(("jpsi1_pt", "jpsi2_pt", "phi_pt")):
        output[name] = pt[:, i]
    result = pd.DataFrame(output).loc[:, list(FEATURE_NAMES)]
    result["phi_y"] = rapidity(*momentum[:, 2, :].T, measured_masses[:, 2])
    for i, name in enumerate(("reco_jpsi_slot1_mass", "reco_jpsi_slot2_mass", "reco_phi_mass")):
        result[name] = measured_masses[:, i]
    for i, obj in enumerate(OBJECTS):
        for j, axis in enumerate(("px", "py", "pz")):
            result[f"reco_{obj}_{axis}"] = momentum[:, i, j]
    if not np.isfinite(result.to_numpy()).all() or np.any(pt <= 0):
        raise ValueError("Invalid derived RECO features")
    return result


def partition_for(sample, source_file, entry, seed):
    """Stable event hash; independent of input order, row counts and feature values."""
    raw = f"{seed}\0{sample}\0{source_file}\0{int(entry)}".encode()
    u = int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big") / 2**64
    return list(FRACTIONS)[min(np.searchsorted(np.cumsum(list(FRACTIONS.values())), u, side="right"), 3)]


def source_inventory(raw_root, max_files=None):
    import uproot
    inventory = {}
    seen = set()
    for name in CLASS_ORDER:
        files = sorted((Path(raw_root) / f"JJP_{name}").glob("*.root"))
        if max_files is not None:
            files = files[:max_files]
        if not files:
            raise ValueError(f"No ROOT inputs for {name}")
        rows = []
        for path in files:
            resolved = str(path.resolve())
            if resolved in seen:
                raise ValueError("Duplicate/aliased ROOT source identity")
            seen.add(resolved)
            with uproot.open(resolved, handler=uproot.source.file.MultithreadedFileSource, num_workers=1) as root:
                tree = "X_data" if "X_data" in root else "mkcands/X_data"
                n = int(root[tree].num_entries)
            rows.append({"path": resolved, "tree": tree, "entries": n, "bytes": path.stat().st_size})
        if len({r["tree"] for r in rows}) != 1:
            raise ValueError(f"Mixed ROOT tree paths in {name}")
        inventory[name] = rows
    return inventory


def extract_sample(name, inventory, seed):
    """Run the production data-like selector and selected-candidate GEN matcher."""
    import ROOT
    from ntuple_pipeline_common import declare_rdf_helpers
    from scripts.kinematics.merge_apply_cuts import build_best_index_expr, build_genmatch_expr
    declare_rdf_helpers()
    if ROOT.IsImplicitMTEnabled():
        ROOT.DisableImplicitMT()  # Stable global TChain rdfentry_; no hidden full-CPU job.
    paths = ROOT.std.vector("string")()
    for item in inventory:
        paths.push_back(item["path"])
    rdf = ROOT.RDataFrame(inventory[0]["tree"], paths)
    rdf = rdf.Define("fc_global_entry", "static_cast<ULong64_t>(rdfentry_)")
    rdf = rdf.Define("muon_id_mask", "muIsPatSoftMuon")
    rdf = rdf.Define("bestCandIdx", build_best_index_expr("JJP_mc"))
    selected = rdf.Filter("bestCandIdx >= 0", "data_like_best_candidate")
    before_match = selected.Count()
    selected = selected.Filter(build_genmatch_expr("JJP_mc"), "selected_candidate_GEN_match")
    columns = ["fc_global_entry", "bestCandIdx"]
    for obj in OBJECTS:
        for field in ("px", "py", "pz", "mass", "pt"):
            column = f"fc_{obj}_{field}"
            selected = selected.Define(column, f"{obj}_{field}.at(bestCandIdx)")
            columns.append(column)
    arrays = selected.AsNumpy(columns)
    global_entry = np.asarray(arrays["fc_global_entry"], dtype=np.int64)
    sizes = np.array([item["entries"] for item in inventory], dtype=np.int64)
    offsets = np.r_[0, np.cumsum(sizes)]
    files = np.searchsorted(offsets[1:], global_entry, side="right")
    if np.any(files >= len(inventory)):
        raise ValueError("RDataFrame global entry outside recorded source coverage")
    momentum = np.stack([np.column_stack([arrays[f"fc_{obj}_{field}"] for field in ("px", "py", "pz")]) for obj in OBJECTS], axis=1)
    masses = np.column_stack([arrays[f"fc_{obj}_mass"] for obj in OBJECTS])
    frame = feature_frame(momentum, masses)
    stored_pt = np.column_stack([arrays[f"fc_{obj}_pt"] for obj in OBJECTS])
    computed_pt = np.hypot(momentum[:, :, 0], momentum[:, :, 1])
    if not np.allclose(stored_pt, computed_pt, rtol=2e-5, atol=2e-5):
        raise ValueError("Stored candidate pT differs from px/py-derived pT")
    frame["sample"] = name
    frame["label"] = CLASS_ORDER.index(name)
    frame["source_file"] = [inventory[i]["path"] for i in files]
    frame["entry"] = global_entry - offsets[files]
    frame["candidate_index"] = np.asarray(arrays["bestCandIdx"], dtype=np.int64)
    frame["partition"] = [partition_for(name, source, entry, seed) for source, entry in zip(frame.source_file, frame.entry)]
    frame["gen_weight"] = 1.
    frame["input_weight"] = 1_000_000 / int(sizes.sum())
    return frame, {"source_entries": int(sizes.sum()), "source_files": len(inventory),
                   "data_like_selected_before_GEN_match": int(before_match.GetValue()),
                   "selected_GEN_matched": len(frame),
                   "partitions": frame.groupby("partition").size().to_dict()}


def build_cache(raw_root, output, seed, max_files=None, resume=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=resume)
    inventory = source_inventory(raw_root, max_files)
    provenance = {"raw_root": str(Path(raw_root).resolve()), "sources": inventory,
                  "selection": SELECTION, "feature_names": FEATURE_NAMES,
                  "nominal_feature_masses": NOMINAL_MASSES,
                  "phi_y": "genuine signed RECO asinh(pz/sqrt(px²+py²+measured_mass²))",
                  "split": "fresh deterministic blake2b event-key partition; no old study split reused",
                  "seed": seed, "genWeight": 1, "max_files_per_sample": max_files,
                  "complete": False, "samples": {}}
    manifest_path = output / "source_manifest.json"
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        if not resume or any(previous[key] != provenance[key] for key in ("sources", "selection", "seed", "max_files_per_sample")):
            raise ValueError("Resume input inventory/selection/seed changed")
    write_json(output / "source_manifest.json", provenance)
    frames = []
    for name in CLASS_ORDER:
        chunks = []
        summaries = []
        chunk_dir = output / name
        chunk_dir.mkdir(exist_ok=resume)
        for start in range(0, len(inventory[name]), 10):
            batch = inventory[name][start:start + 10]
            checkpoint = chunk_dir / f"files_{start:05d}.parquet"
            checkpoint_json = chunk_dir / f"files_{start:05d}.json"
            if resume and checkpoint.exists() and checkpoint_json.exists():
                chunk = pd.read_parquet(checkpoint)
                summary = json.loads(checkpoint_json.read_text())
            else:
                if checkpoint.exists() or checkpoint_json.exists():
                    raise ValueError(f"Incomplete checkpoint: {checkpoint}; inspect before resuming")
                chunk, summary = extract_sample(name, batch, seed)
                chunk["input_weight"] = 1_000_000 / sum(item["entries"] for item in inventory[name])
                chunk.to_parquet(checkpoint, index=False)
                write_json(checkpoint_json, summary)
            chunks.append(chunk)
            summaries.append(summary)
            provenance["samples"][name] = {"files_processed": start + len(batch), "files_total": len(inventory[name]),
                "selected_GEN_matched": sum(item["selected_GEN_matched"] for item in summaries),
                "checkpoint": str(checkpoint), "complete": False}
            write_json(output / "source_manifest.json", provenance)
            print(f"EXTRACT_PROGRESS {name} files={start + len(batch)}/{len(inventory[name])} selected={sum(item['selected_GEN_matched'] for item in summaries)}", flush=True)
        frame = pd.concat(chunks, ignore_index=True)
        summary = {key: sum(item[key] for item in summaries) for key in ("source_entries", "source_files", "data_like_selected_before_GEN_match", "selected_GEN_matched")}
        summary["partitions"] = frame.groupby("partition").size().to_dict()
        summary["complete"] = True
        frame.to_parquet(output / f"{name}_features.parquet", index=False)
        provenance["samples"][name] = summary
        write_json(output / "source_manifest.json", provenance)
        frames.append(frame)
        print(f"EXTRACTED {name}: {summary}", flush=True)
    frame = pd.concat(frames, ignore_index=True)
    if frame.duplicated(KEYS).any():
        raise ValueError("Duplicate selected event identity")
    frame.to_parquet(output / "full_features.parquet", index=False)
    frame.to_parquet(output / "mc_phi_features.parquet", index=False)
    provenance["complete"] = True
    write_json(output / "source_manifest.json", provenance)
    return frame


def weighted_frame(frame, shape_weights=None):
    result = frame.copy()
    result["phi_shape_weight"] = 1. if shape_weights is None else np.asarray(shape_weights, float)
    result["base_weight"] = result.input_weight * result.phi_shape_weight
    training = result.partition == "training"
    labels = result.loc[training, "label"].to_numpy(int)
    w = policy_weights(labels, result.loc[training, "base_weight"], len(CLASS_ORDER), "balanced-class")
    factors = {label: float(w[labels == label][0] / result.loc[training & (result.label == label), "base_weight"].iloc[0]) for label in range(len(CLASS_ORDER))}
    result["training_weight"] = result.base_weight * result.label.map(factors)
    result["objective_weight"] = result.training_weight
    development = result.partition == "development"
    result.loc[development, "objective_weight"] = policy_weights(result.loc[development, "label"], result.loc[development, "base_weight"], len(CLASS_ORDER), "balanced-class")
    for _, idx in result.groupby(["sample", "partition"]).groups.items():
        q = len(idx) / int((result["sample"] == result.loc[idx[0], "sample"]).sum())
        result.loc[idx, "partition_fraction_realized"] = q
        result.loc[idx, "rate_weight"] = result.loc[idx, "base_weight"] / q
        result.loc[idx, "shape_weight"] = result.loc[idx, "base_weight"] / result.loc[idx, "base_weight"].sum()
    return result


def selected_features(excluded=()):
    unknown=set(excluded)-set(FEATURE_NAMES)
    if unknown:raise ValueError(f'Excluded names are not trained features: {sorted(unknown)}; phi_y is already metadata only')
    names=tuple(name for name in FEATURE_NAMES if name not in excluded)
    if not names:raise ValueError('Cannot exclude all features')
    return names


def frozen_inputs(study):
    """Reuse selected rows, original split and frozen phi weights, without map fit."""
    study=Path(study);manifest=json.loads((study/'inputs/source_manifest.json').read_text())
    if not manifest.get('complete') or manifest['selection']!=SELECTION or tuple(manifest['feature_names'])!=FEATURE_NAMES:
        raise ValueError('Frozen input selection/schema incomplete or incompatible')
    frame=pd.read_parquet(study/'inputs/full_features.parquet')
    phi=pd.read_parquet(study/'inputs/phi_shape_weights.parquet')
    if frame.duplicated(KEYS).any() or phi.duplicated(KEYS).any():raise ValueError('Duplicate frozen input keys')
    pd.testing.assert_frame_equal(frame.reset_index(drop=True),phi.loc[:,frame.columns].reset_index(drop=True))
    for model,weights in [('no_phi',np.ones(len(frame))),('phi_reweighted',phi.phi_shape_weight.to_numpy())]:
        old=pd.read_parquet(study/model/'event_weights.parquet');new=weighted_frame(frame,weights)
        pd.testing.assert_frame_equal(old.reset_index(drop=True),new.reset_index(drop=True))
    return frame,phi


def save_scores(path, booster, frame, feature_names=FEATURE_NAMES):
    import xgboost as xgb
    x = frame.loc[:, list(feature_names)].to_numpy(float)
    scores = booster.predict(xgb.DMatrix(x))
    if not np.isfinite(scores).all() or not np.allclose(scores.sum(axis=1), 1., atol=1e-6):
        raise ValueError("Invalid multiclass scores")
    fields = [*KEYS, "partition", "input_weight", "gen_weight", "phi_shape_weight", "base_weight", "training_weight", "objective_weight", "rate_weight", "shape_weight", "phi_y"]
    np.savez_compressed(path, scores=scores, features=x, labels=frame.label.to_numpy(int),
                        class_order=np.array(CLASS_ORDER), feature_names=np.array(feature_names),
                        **{key: frame[key].to_numpy(dtype=str if key in (*KEYS[:2], "partition") else None) for key in fields})
    return scores


def plot_histories(output, histories):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import mplhep as hep
    hep.style.use(hep.style.CMS)
    fig, ax = plt.subplots(figsize=(9, 7))
    for history in histories:
        rounds = np.arange(1, history["attempted_rounds"] + 1)
        line, = ax.plot(rounds, history["history"]["validation_1"]["mlogloss"], label=f"depth {history['depth']}: development")
        ax.plot(rounds, history["history"]["validation_0"]["mlogloss"], linestyle="--", color=line.get_color(), label=f"depth {history['depth']}: training")
        ax.axvline(history["best_iteration"] + 1, color=line.get_color(), alpha=.3)
    ax.set(xlabel="Boosting round", ylabel="Balanced objective mlogloss")
    ax.legend(fontsize=10)
    hep.cms.label("Work In Progress", data=False, ax=ax, loc=0, rlabel="")
    fig.subplots_adjust(left=.15, right=.97, bottom=.14, top=.87)
    for ext in ("png", "pdf"):
        fig.savefig(Path(output) / f"learning_curves.{ext}", dpi=160)
    plt.close(fig)


def train_variant(frame, output, *, seed=20261109, n_estimators=1200, depths=(2, 3, 4), jobs=4, early_stopping_rounds=35, feature_names=FEATURE_NAMES):
    import xgboost as xgb
    from sklearn.metrics import log_loss
    feature_names=tuple(feature_names)
    if not feature_names or len(set(feature_names))!=len(feature_names) or any(name not in FEATURE_NAMES for name in feature_names):raise ValueError('Invalid trained feature subset')
    if any(set(part.partition) != set(FRACTIONS) for _, part in frame.groupby("sample")):
        raise ValueError("At least one class has an empty partition")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(output / "event_weights.parquet", index=False)
    train = frame.loc[frame.partition == "training"]
    dev = frame.loc[frame.partition == "development"]
    x_train = train.loc[:, list(feature_names)].to_numpy(float)
    x_dev = dev.loc[:, list(feature_names)].to_numpy(float)
    candidates, boosters = [], []
    for depth in depths:
        params = dict(objective="multi:softprob", num_class=6, n_estimators=n_estimators,
                      max_depth=depth, learning_rate=.05, min_child_weight=5,
                      subsample=.8, colsample_bytree=.8, reg_lambda=2., reg_alpha=.05,
                      eval_metric="mlogloss", tree_method="hist", random_state=seed,
                      n_jobs=jobs, early_stopping_rounds=early_stopping_rounds)
        model = xgb.XGBClassifier(**params)
        # Development is LAST: XGBoost early stopping must monitor development.
        model.fit(x_train, train.label.to_numpy(int), sample_weight=train.objective_weight.to_numpy(),
                  eval_set=[(x_train, train.label.to_numpy(int)), (x_dev, dev.label.to_numpy(int))],
                  sample_weight_eval_set=[train.objective_weight.to_numpy(), dev.objective_weight.to_numpy()], verbose=False)
        history = model.evals_result()
        attempted = len(history["validation_1"]["mlogloss"])
        best_iteration = int(model.best_iteration)
        booster = model.get_booster()[:best_iteration + 1]
        booster.save_model(output / f"candidate_depth{depth}.json")
        loss = log_loss(dev.label, booster.predict(xgb.DMatrix(x_dev)), labels=np.arange(6), sample_weight=dev.objective_weight)
        item = {"depth": depth, "config": params, "history": history,
                "history_datasets": {"validation_0": "training", "validation_1": "development"},
                "attempted_rounds": attempted, "best_iteration": best_iteration,
                "saved_rounds": best_iteration + 1, "development_policy_log_loss": float(loss),
                "early_stopping_monitored_dataset": "validation_1", "early_stopping_rounds": early_stopping_rounds}
        write_json(output / f"candidate_depth{depth}_training_progress.json", item)
        with (output / f"candidate_depth{depth}_training_progress.csv").open("w") as handle:
            writer = csv.writer(handle)
            writer.writerow(["round", "training_mlogloss", "development_mlogloss"])
            writer.writerows(zip(range(1, attempted + 1), history["validation_0"]["mlogloss"], history["validation_1"]["mlogloss"]))
        candidates.append(item)
        boosters.append(booster)
        print(f"CANDIDATE {output.name} depth={depth} attempted={attempted} best={best_iteration + 1} dev_loss={loss:.6f}", flush=True)
    best_loss = min(item["development_policy_log_loss"] for item in candidates)
    chosen_idx = min((i for i, item in enumerate(candidates) if item["development_policy_log_loss"] <= best_loss + .001), key=lambda i: candidates[i]["depth"])
    chosen = candidates[chosen_idx]
    model_path = output / "six_class_xgboost.json"
    boosters[chosen_idx].save_model(model_path)
    loaded = xgb.Booster()
    loaded.load_model(model_path)
    delta = float(np.max(abs(loaded.predict(xgb.DMatrix(x_dev)) - boosters[chosen_idx].predict(xgb.DMatrix(x_dev)))))
    if delta > 1e-7:
        raise ValueError("Saved model reload mismatch")
    # Freeze the choice BEFORE any final-validation prediction.
    write_json(output / "frozen_study.json", {"selection": "development only; .001 depth tie tolerance", "class_order": CLASS_ORDER,
               "feature_names": feature_names, "selected": chosen, "candidates": candidates,
               "selection_contract": SELECTION, "nominal_feature_masses": NOMINAL_MASSES,
               "weights": "genWeight=1; balanced base weights normalized mean1; actual train/dev objective weights in event_weights",
               "xgboost_version": xgb.__version__, "saved_model_max_prediction_difference": delta})
    metrics = {}
    filenames = {"training": "training_scores.npz", "development": "development_scores.npz",
                 "templates": "heldout_template_scores.npz", "final_validation": "final_validation_scores.npz"}
    for part, filename in filenames.items():
        rows = frame.loc[frame.partition == part]
        scores = save_scores(output / filename, loaded, rows, feature_names)
        metrics[part] = classifier_metrics(rows.label.to_numpy(int), scores, rows.base_weight.to_numpy(), CLASS_ORDER)
    write_json(output / "trial_report.json", {"class_order": CLASS_ORDER, "feature_names": feature_names,
               "selected_depth": chosen["depth"], "best_iteration": chosen["best_iteration"],
               "attempted_rounds": chosen["attempted_rounds"], "boosting_rounds": chosen["saved_rounds"],
               "metrics": metrics, "final_validation": metrics["final_validation"],
               "checks": {"saved_model_max_prediction_difference": delta, "training_mean_weight": float(train.objective_weight.mean())},
               "limitations": ["Fixed final-validation evaluation; no final-validation tuning.",
                 "Nominal-mass derived kinematics avoid direct fitted-mass inputs but do not establish mass independence.",
                 "Phi target/map uncertainty and retraining uncertainty are not propagated.",
                 "Fresh data-like ROOT selection differs from historical efficiency-reco_best models."]})
    plot_histories(output, candidates)
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path)
    parser.add_argument("--feature-cache", type=Path, help="New full_features.parquet generated ONLY by this ROOT extractor")
    parser.add_argument('--frozen-study-dir',type=Path,help='Reuse complete selected cache/splits and frozen phi weights from an existing full-correlation study; no extraction or map refit')
    parser.add_argument('--exclude-features',nargs='+',default=[],help='Exclude actual trained features; phi_y is already absent and is not a valid exclusion')
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=REPO / "plots_kinematics/temp/jjp_data_weighted.root")
    parser.add_argument("--extract-only", action="store_true")
    parser.add_argument("--resume-extraction", action="store_true", help="Explicitly resume matching ten-file checkpoints in this output directory")
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--seed", type=int, default=20261109)
    parser.add_argument("--n-estimators", type=int, default=1200)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if sum(x is not None for x in (args.raw_root,args.feature_cache,args.frozen_study_dir))!=1:
        parser.error('Choose exactly one of --raw-root, --feature-cache, --frozen-study-dir')
    features=selected_features(args.exclude_features)
    if args.jobs < 1 or args.n_estimators < 1 or (args.max_files is not None and args.max_files < 1):
        parser.error("jobs/estimators/max-files must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=args.resume_extraction)
    if args.frozen_study_dir:
        if args.extract_only or args.resume_extraction:parser.error('Frozen study mode cannot extract/resume')
        frame,phi=frozen_inputs(args.frozen_study_dir)
        reference={'study':str(args.frozen_study_dir.resolve()),'features':features,'excluded_features':args.exclude_features,'phi_y':'Already absent from trained input; retained for frozen reweighting','explicit_input_only':'phi_pt remains algebraically reconstructable as sumpt_jjp-jpsi1_pt-jpsi2_pt; this does not remove phi kinematic information','baseline':'phi_reweighted_native','selection_and_splits':'unchanged','phi_maps':'Frozen maps and weights reused; no fit'}
        write_json(args.output_dir/'frozen_input_reference.json',reference)
        print(f'FROZEN_INPUTS rows={len(frame)} features={len(features)} partitions={frame.groupby("partition").size().to_dict()}',flush=True)
        metrics={}
        for model,weights in [('no_phi',None),('phi_reweighted',phi.phi_shape_weight.to_numpy())]:
            metrics[model]=train_variant(weighted_frame(frame,weights),args.output_dir/model,seed=args.seed,n_estimators=args.n_estimators,jobs=args.jobs,feature_names=features)
        write_json(args.output_dir/'study_summary.json',metrics)
        (args.output_dir/'README.md').write_text('# Individual-phi-input ablation\n\nRemoved trained phi_pt only; phi_y was never a trained input. All derived correlations, original selection, event splits, frozen phi maps and exposure/class weights retained.\n\nThis removes an explicit input only: phi_pt is still algebraically reconstructable as sumpt_jjp-jpsi1_pt-jpsi2_pt. It does not remove phi kinematic information.\n\nBaseline: phi_reweighted_native; common-population views compare original input_weight. No redundancy/binning changes or permutation calculations.\n\nSource: '+str(args.frozen_study_dir.resolve())+'\n')
        return
    if args.feature_cache:
        manifest_path = args.feature_cache.parent / "source_manifest.json"
        provenance = json.loads(manifest_path.read_text())
        if not provenance.get("complete") or tuple(provenance["feature_names"]) != FEATURE_NAMES or provenance["selection"] != SELECTION:
            raise ValueError("Feature cache provenance/schema/selection is incompatible")
        frame = pd.read_parquet(args.feature_cache)
        write_json(args.output_dir / "source_cache_reference.json", {"cache": str(args.feature_cache.resolve()), "manifest": str(manifest_path.resolve())})
    else:
        frame = build_cache(args.raw_root, args.output_dir / "inputs", args.seed, args.max_files, resume=args.resume_extraction)
    if args.extract_only:
        return
    inputs = args.output_dir / "inputs"
    inputs.mkdir(exist_ok=True)
    if args.feature_cache:
        frame.to_parquet(inputs / "mc_phi_features.parquet", index=False)
    target = data_target(args.data)
    target.to_parquet(inputs / "data_phi_target.parquet", index=False)
    phi, maps, report = build_weights(frame, target)
    phi.to_parquet(inputs / "phi_shape_weights.parquet", index=False)
    write_json(inputs / "phi_maps.json", maps)
    write_json(inputs / "phi_map_report.json", report)
    print(f"PHI_INPUTS_READY {inputs}", flush=True)
    no_phi = weighted_frame(frame)
    metrics = {"no_phi": train_variant(no_phi, args.output_dir / "no_phi", seed=args.seed, n_estimators=args.n_estimators, jobs=args.jobs,feature_names=features)}
    metrics["phi_reweighted"] = train_variant(weighted_frame(frame, phi.phi_shape_weight), args.output_dir / "phi_reweighted", seed=args.seed, n_estimators=args.n_estimators, jobs=args.jobs,feature_names=features)
    write_json(args.output_dir / "study_summary.json", metrics)


if __name__ == "__main__":
    main()

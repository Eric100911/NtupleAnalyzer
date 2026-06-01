#!/usr/bin/env python3
"""Build response matrix classification from efficiency pipeline outputs.

Reads gen_systems.parquet and event_step_flags.parquet, classifies events as:
  - Diagonal:           gen phi pT bin == reco phi pT bin
  - Off-diag, matched:  different bins, reco phi traces to GEN-best phi
  - Off-diag, no-match: different bins, reco phi lacks gen-level match

Response matrix: R_ji = P(x_reco in j | x_gen in i) for phi pT bins.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from efficiency_workflow.efficiency import EfficiencyBinning
from efficiency_workflow.io import ensure_dir, read_json, write_json, write_parquet

PHI_PT_EDGES = np.array(EfficiencyBinning.phi_pt_edges, dtype=np.float64)
N_BINS = len(PHI_PT_EDGES) - 1
BIN_LABELS = [f"[{PHI_PT_EDGES[i]:.0f},{PHI_PT_EDGES[i+1]:.0f})" for i in range(N_BINS)]


def _discover_samples(input_dir: Path) -> list[Path]:
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"No manifest.json found in {input_dir}")
    manifest = read_json(manifest_path)
    samples = manifest.get("artifacts", {}).get("samples", {})
    if samples:
        return [input_dir / sample for sample in samples]
    if (input_dir / "efficiency_maps.parquet").exists():
        return [input_dir]
    raise RuntimeError(
        f"No samples listed in {manifest_path} and no efficiency_maps.parquet found"
    )


def classify_response_events(
    gen_df: pd.DataFrame,
    event_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Classify events and build response matrix.

    Returns (classification_df, summary_df, response_matrix_df).
    """
    has_reco_cols = "reco_best_phi_pt" in event_df.columns
    if not has_reco_cols:
        empty = pd.DataFrame(
            columns=[
                "sample", "n_total", "n_diagonal", "n_offdiag_matched",
                "n_offdiag_wrong_phi", "n_offdiag_nomatch",
                "frac_diagonal", "frac_offdiag_matched",
                "frac_offdiag_wrong_phi", "frac_offdiag_nomatch",
            ]
        )
        return pd.DataFrame(), empty, pd.DataFrame()

    # Filter early to avoid OOM: only keep events with full_gen + quality reco
    keys = ["entry", "source_file"]
    evt_filt = event_df[(event_df["full_gen"] == 1) & event_df["reco_best_phi_pt"].notna()]
    if len(evt_filt) == 0:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Only load gen columns we need
    gen_cols = keys + [
        "sample", "run", "lumi", "event", "phi_pt",
    ]
    gen_subset = gen_df[gen_cols]
    evt_cols = keys + [
        "reco_best_phi_pt", "reco_best_phi_gen_idx",
        "reco_best_phi_matches_gen", "reco_best_is_gen_matched",
        "reco_best_score",
    ]
    evt_subset = evt_filt[evt_cols]

    both = gen_subset.merge(evt_subset, on=keys, how="inner")

    if len(both) == 0:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    gen_bin = np.digitize(both["phi_pt"].values, PHI_PT_EDGES) - 1
    reco_bin = np.digitize(both["reco_best_phi_pt"].values, PHI_PT_EDGES) - 1

    valid = (gen_bin >= 0) & (gen_bin < N_BINS) & (reco_bin >= 0) & (reco_bin < N_BINS)

    is_diagonal = valid & (gen_bin == reco_bin)
    is_offdiag = valid & (gen_bin != reco_bin)
    phi_matches_gen_best = both["reco_best_phi_matches_gen"].values == True
    phi_has_any_gen = both["reco_best_phi_gen_idx"].values >= 0

    offdiag_matched   = is_offdiag & phi_matches_gen_best
    offdiag_wrong_phi = is_offdiag & ~phi_matches_gen_best & phi_has_any_gen
    offdiag_nomatch   = is_offdiag & ~phi_matches_gen_best & ~phi_has_any_gen

    both["gen_phi_pt_bin"] = -1
    both.loc[valid, "gen_phi_pt_bin"] = gen_bin[valid]
    both["reco_phi_pt_bin"] = -1
    both.loc[valid, "reco_phi_pt_bin"] = reco_bin[valid]

    category = np.full(len(both), "other", dtype=object)
    category[is_diagonal] = "diagonal"
    category[offdiag_matched] = "offdiagonal_phi_matched"
    category[offdiag_wrong_phi] = "offdiagonal_wrong_phi"
    category[offdiag_nomatch] = "offdiagonal_no_genmatch"
    both["response_category"] = category

    classification_cols = [
        "sample", "source_file", "entry", "run", "lumi", "event",
        "phi_pt", "reco_best_phi_pt", "reco_best_phi_gen_idx",
        "reco_best_phi_matches_gen", "reco_best_is_gen_matched",
        "reco_best_score", "gen_phi_pt_bin", "reco_phi_pt_bin",
        "response_category",
    ]
    class_df = both[classification_cols].reset_index(drop=True)

    n_total = int(valid.sum())
    n_diag = int(is_diagonal.sum())
    n_off_m = int(offdiag_matched.sum())
    n_off_w = int(offdiag_wrong_phi.sum())
    n_off_n = int(offdiag_nomatch.sum())

    sample_name = both["sample"].iloc[0] if len(both) > 0 else ""
    summary_df = pd.DataFrame([{
        "sample": sample_name,
        "n_total": n_total,
        "n_diagonal": n_diag,
        "n_offdiag_matched": n_off_m,
        "n_offdiag_wrong_phi": n_off_w,
        "n_offdiag_nomatch": n_off_n,
        "frac_diagonal": n_diag / n_total if n_total > 0 else float("nan"),
        "frac_offdiag_matched": n_off_m / n_total if n_total > 0 else float("nan"),
        "frac_offdiag_wrong_phi": n_off_w / n_total if n_total > 0 else float("nan"),
        "frac_offdiag_nomatch": n_off_n / n_total if n_total > 0 else float("nan"),
    }])

    rows = []
    for ig in range(N_BINS):
        gen_mask = valid & (gen_bin == ig)
        n_gen = int(gen_mask.sum()) if gen_mask.any() else 0
        for jr in range(N_BINS):
            n = int((gen_mask & (reco_bin == jr)).sum()) if gen_mask.any() else 0
            rows.append({
                "sample": sample_name,
                "gen_bin": ig, "reco_bin": jr,
                "gen_bin_label": BIN_LABELS[ig],
                "reco_bin_label": BIN_LABELS[jr],
                "count": n,
                "fraction": n / n_gen if n_gen > 0 else 0.0,
            })
    matrix_df = pd.DataFrame(rows)

    return class_df, summary_df, matrix_df


def build_response_for_sample(
    sample_dir: Path, output_dir: Path
) -> dict[str, object]:
    sample = sample_dir.name
    gen_path = sample_dir / "gen_systems.parquet"
    event_path = sample_dir / "event_step_flags.parquet"

    if not gen_path.exists() or not event_path.exists():
        raise RuntimeError(f"Missing parquet files in {sample_dir}")

    print(f"\n[{sample}] Reading parquet files ...")
    gen_df = pd.read_parquet(gen_path)
    event_df = pd.read_parquet(event_path)
    print(f"[{sample}]   gen: {len(gen_df)} events, event_flags: {len(event_df)} events")

    print(f"[{sample}] Classifying response events ...")
    class_df, summary_df, matrix_df = classify_response_events(gen_df, event_df)

    sample_out = ensure_dir(output_dir / sample / "response")
    manifest = {"source": str(sample_dir.resolve()), "outputs": {}}

    if not class_df.empty and not summary_df.empty:
        write_parquet(summary_df, sample_out / "response_summary.parquet")
        summary_df.to_csv(sample_out / "response_summary.csv", index=False)
        manifest["outputs"]["summary_parquet"] = "response_summary.parquet"
        manifest["outputs"]["summary_csv"] = "response_summary.csv"
        print(f"[{sample}]   {len(summary_df)} summary row(s)")

        write_parquet(class_df, sample_out / "response_classification.parquet")
        class_df.to_csv(sample_out / "response_classification.csv", index=False)
        manifest["outputs"]["classification_parquet"] = "response_classification.parquet"
        print(f"[{sample}]   {len(class_df)} events classified")

        write_parquet(matrix_df, sample_out / "response_matrix.parquet")
        matrix_df.to_csv(sample_out / "response_matrix.csv", index=False)
        manifest["outputs"]["matrix_parquet"] = "response_matrix.parquet"
        print(f"[{sample}]   {len(matrix_df)} response matrix entries")

        row = summary_df.iloc[0]
        print(f"[{sample}]   Diagonal:             {row['n_diagonal']:>5}  ({100*row['frac_diagonal']:.1f}%)")
        print(f"[{sample}]   Off-diag, phi-matched: {row['n_offdiag_matched']:>5}  ({100*row['frac_offdiag_matched']:.1f}%)")
        print(f"[{sample}]   Off-diag, wrong phi:   {row['n_offdiag_wrong_phi']:>5}  ({100*row['frac_offdiag_wrong_phi']:.1f}%)")
        print(f"[{sample}]   Off-diag, no gen-match:{row['n_offdiag_nomatch']:>5}  ({100*row['frac_offdiag_nomatch']:.1f}%)")
    else:
        print(f"[{sample}]   (no reco_best columns — re-run pipeline with updated code)")

    write_json(manifest, sample_out / "manifest.json")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build response matrix classification from efficiency parquet files"
    )
    parser.add_argument(
        "--input-dir", required=True,
        help="Merge output directory (contains per-sample subdirs + manifest.json)",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory (default: same as --input-dir)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir

    sample_dirs = _discover_samples(input_dir)
    print(f"Processing {len(sample_dirs)} sample(s) from {input_dir}")

    manifests: dict[str, object] = {}
    for sample_dir in sample_dirs:
        manifests[sample_dir.name] = build_response_for_sample(sample_dir, output_dir)

    top_manifest = {
        "stage": "response_classification",
        "input_dir": str(input_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "samples": manifests,
    }
    write_json(top_manifest, output_dir / "response_manifest.json")
    print(f"\nDone. Manifest: {output_dir / 'response_manifest.json'}")


if __name__ == "__main__":
    main()

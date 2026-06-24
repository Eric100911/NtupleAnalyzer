from __future__ import annotations

import json

import pandas as pd
import pytest

from efficiency_workflow.closure import main


def _sample_inputs(sample: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = {
        "sample": [sample, sample],
        "source_file": ["a.root", "a.root"],
        "entry": [0, 1],
        "run": [1, 1],
        "lumi": [1, 1],
        "event": [11, 12],
    }
    gen_df = pd.DataFrame(
        {
            **keys,
            "jpsi_lead_pt": [7.0, 12.0],
            "jpsi_lead_y": [0.2, -0.4],
            "jpsi_sublead_pt": [6.5, 8.0],
            "jpsi_sublead_y": [-0.3, 0.5],
            "phi_pt": [5.0, 7.0],
            "phi_y": [0.1, -0.2],
        }
    )
    event_df = pd.DataFrame(
        {
            **keys,
            "full_gen": [1, 1],
            "jpsi_lead_fiducial": [1, 1],
            "jpsi_sublead_fiducial": [1, 1],
            "phi_fiducial": [1, 1],
            "jpsi_lead_muonRECO": [1, 1],
            "jpsi_sublead_muonRECO": [1, 1],
            "jpsi_lead_muonID": [1, 1],
            "jpsi_sublead_muonID": [1, 1],
            "jpsi_lead_dimuon": [1, 1],
            "jpsi_sublead_dimuon": [1, 1],
            "phi_kaonRECO": [1, 1],
            "phi_kaonID": [1, 1],
            "phi_dikaon": [1, 1],
            "s_cand": [1, 1],
            "hlt_muon_matched": [1, 1],
            "four_muon_vtx": [1, 1],
            "Pri_assocPVPass": [1, 1],
        }
    )
    return gen_df, event_df


def _write_sample(base_dir, sample: str) -> None:
    sample_dir = base_dir / sample
    sample_dir.mkdir(parents=True)
    gen_df, event_df = _sample_inputs(sample)
    gen_df.to_parquet(sample_dir / "gen_systems.parquet")
    event_df.to_parquet(sample_dir / "event_step_flags.parquet")


def test_closure_cli_writes_full_matrix(tmp_path) -> None:
    samples = ["JJP_A", "JJP_B"]
    for sample in samples:
        _write_sample(tmp_path, sample)

    rc = main(
        [
            "--input-dir",
            str(tmp_path),
            "--samples",
            *samples,
            "--output-dir",
            str(tmp_path / "closure_out"),
            "--build-maps",
        ]
    )

    assert rc == 0
    out = pd.read_parquet(tmp_path / "closure_out" / "closure_results.parquet")
    assert len(out) == 4
    assert set(out["closure_type"]) == {"self", "cross"}
    assert set(out["map_sample"]) == set(samples)
    assert set(out["target_sample"]) == set(samples)
    assert (out["n_failed_lookup"] == 0).all()

    csv_path = tmp_path / "closure_out" / "closure_results.csv"
    manifest_path = tmp_path / "closure_out" / "closure_manifest.json"
    assert csv_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["n_rows"] == 4
    assert manifest["samples"] == samples


def test_closure_cli_self_only(tmp_path) -> None:
    samples = ["JJP_A", "JJP_B"]
    for sample in samples:
        _write_sample(tmp_path, sample)

    main(
        [
            "--input-dir",
            str(tmp_path),
            "--samples",
            *samples,
            "--output-dir",
            str(tmp_path / "closure_self"),
            "--build-maps",
            "--self-only",
        ]
    )

    out = pd.read_parquet(tmp_path / "closure_self" / "closure_results.parquet")
    assert len(out) == 2
    assert set(out["closure_type"]) == {"self"}
    assert set(out["map_sample"]) == set(samples)
    assert set(out["target_sample"]) == set(samples)


def test_closure_cli_requires_maps_without_build_maps(tmp_path) -> None:
    _write_sample(tmp_path, "JJP_A")

    with pytest.raises(FileNotFoundError, match="Missing factorized correction map"):
        main(["--input-dir", str(tmp_path), "--samples", "JJP_A"])


def test_closure_cli_hybrid_self(tmp_path) -> None:
    """Hybrid closure: factorized acceptance x 5D post-acceptance."""
    import pandas as pd
    from efficiency_workflow.build_factorized_maps import build_post_acceptance_5d_map
    from efficiency_workflow.build_factorized_maps import build_factorized_maps_for_sample

    samples = ["JJP_A"]
    for sample in samples:
        _write_sample(tmp_path, sample)

    # Build factorized maps and post-acceptance 5D maps
    for sample in samples:
        build_factorized_maps_for_sample(tmp_path / sample, tmp_path / sample / "maps")
        build_post_acceptance_5d_map(tmp_path / sample, tmp_path / sample / "maps")

    rc = main(
        [
            "--input-dir", str(tmp_path),
            "--samples", *samples,
            "--output-dir", str(tmp_path / "closure_hybrid"),
            "--map-type", "hybrid",
            "--self-only",
            "--n-min-fine", "0",
            "--n-min-coarse", "0",
        ]
    )

    assert rc == 0
    out = pd.read_parquet(tmp_path / "closure_hybrid" / "closure_results.parquet")
    assert len(out) == 1  # self-only for 1 sample
    assert set(out["closure_type"]) == {"self"}
    assert out["n_failed_lookup"].iloc[0] == 0
    # With all efficiencies = 1.0, ratio should be close to 1.0
    assert abs(out["ratio"].iloc[0] - 1.0) < 0.01

    csv_path = tmp_path / "closure_hybrid" / "closure_results.csv"
    manifest_path = tmp_path / "closure_hybrid" / "closure_manifest.json"
    assert csv_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["stage"] == "hybrid_closure"
    assert manifest["n_rows"] == 1

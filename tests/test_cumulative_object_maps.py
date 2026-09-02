from itertools import product
import json

import numpy as np
import pandas as pd
import pytest

from efficiency_workflow.build_factorized_maps import (
    _build_factor_map, _jpsi_object_frame, _phi_object_frame, factor_specs,
)
from efficiency_workflow.efficiency import (
    EfficiencyBinning, EVENT_STEPS, PER_JPSI_STEPS, PER_PHI_STEPS,
    _inclusive_counts, _per_object_counts, build_conditional_maps, build_cutflow,
    build_stacked_jpsi_acceptance_maps, build_stacked_jpsi_efficiency_maps,
)
from scripts.efficiency.print_cutflow import build_cutflow_rows, OBJECT_SECTIONS


BINNING = EfficiencyBinning(
    jpsi_pt_edges=(0., 10., 20.), phi_pt_edges=(0., 10., 20.),
    object_y_edges=(-2., 0., 2.), object_abs_y_edges=(0., 2.),
)
CHAINS = {"jpsi_lead": PER_JPSI_STEPS, "jpsi_sublead": PER_JPSI_STEPS, "phi": PER_PHI_STEPS}


def inputs():
    gen, events = [], []
    for entry, (pt, bits) in enumerate(product((7., 12.), product((0, 1), repeat=5))):
        key = dict(sample="JJP_TEST", source_file="test.root", entry=entry, run=1, lumi=1, event=entry)
        g, e = dict(key), dict(key, full_gen=bits[0], s_cand=0)
        for obj, steps in CHAINS.items():
            g.update({f"{obj}_pt": pt, f"{obj}_y": -.4 if obj == "jpsi_lead" else .4})
            e.update({f"{obj}_{step}": bit for step, bit in zip(steps, bits[1:])})
        gen.append(g)
        events.append(e)
    return pd.DataFrame(gen), pd.DataFrame(events)


def oracle(frame, obj, steps):
    columns = ["full_gen", *[f"{obj}_{s}" for s in steps]]
    return np.logical_and.accumulate(frame[columns].to_numpy(dtype=bool), axis=1).sum(axis=0)


def test_object_counts_conditionals_and_both_cutflows_agree():
    gen, events = inputs()
    original = events.copy(deep=True)
    frame = gen.merge(events)
    counts = pd.DataFrame(_inclusive_counts(frame, BINNING) + _per_object_counts(frame, BINNING))
    counts = counts[counts["object"].isin(CHAINS)]
    from_flags = build_conditional_maps(counts, BINNING, frame)
    from_counts = build_conditional_maps(counts, BINNING)
    keys = ["map_type", "object", "step"]
    cols = ["conditional_total", "conditional_passed", "absolute_total", "absolute_passed", "absolute_efficiency"]
    # Compare inclusive and binned products, including absolute-vs-conditional denominators.
    for map_type in ("inclusive", "object_2d"):
        index = keys + (["x_bin", "y_bin"] if map_type == "object_2d" else [])
        left = from_flags[from_flags.map_type == map_type].set_index(index)[cols].sort_index()
        right = from_counts[from_counts.map_type == map_type].set_index(index)[cols].sort_index()
        pd.testing.assert_frame_equal(left, right, check_index_type=False)
    cutflow = build_cutflow(events)
    printed = pd.DataFrame(build_cutflow_rows(events))
    for obj, steps in CHAINS.items():
        expected = oracle(events, obj, steps)
        for i, step in enumerate(steps):
            row = cutflow[(cutflow.object == obj) & (cutflow.step == step)].iloc[0]
            assert (row.conditional_total, row.conditional_passed) == tuple(expected[i:i+2])
            assert row.total == expected[0]
            assert row.passed == expected[i+1]
            displayed = printed[(printed.section == OBJECT_SECTIONS[obj]) & (printed.step == step)].iloc[0]
            assert (displayed.total, displayed.passed) == tuple(expected[i:i+2])
        for (ix, iy), group in from_flags[(from_flags.object == obj) & (from_flags.map_type == "object_2d")].groupby(["x_bin", "y_bin"]):
            subset = frame[(frame[f"{obj}_pt"] >= BINNING.jpsi_pt_edges[int(ix)])
                           & (frame[f"{obj}_pt"] < BINNING.jpsi_pt_edges[int(ix)+1])
                           & (frame[f"{obj}_y"] >= BINNING.object_y_edges[int(iy)])
                           & (frame[f"{obj}_y"] < BINNING.object_y_edges[int(iy)+1])]
            expected = oracle(subset, obj, steps)
            ordered = group.set_index("step").loc[list(steps)]
            assert ordered.conditional_total.tolist() == expected[:-1].tolist()
            assert ordered.conditional_passed.tolist() == expected[1:].tolist()
    pd.testing.assert_frame_equal(events, original)
    with pytest.raises(ValueError, match="rebuild legacy counts"):
        build_conditional_maps(counts.drop(columns="selection_semantics"), BINNING)


@pytest.mark.parametrize("obj,prepare,steps,names,multiplier", [
    ("jpsi_lead", _jpsi_object_frame, PER_JPSI_STEPS,
     ("acceptance_jpsi", "eff_muReco_jpsi", "eff_muID_jpsi", "eff_dimuon_jpsi"), 2),
    ("phi", _phi_object_frame, PER_PHI_STEPS,
     ("acceptance_phi", "eff_kaonReco_phi", "eff_kaonID_phi", "eff_dikaon_phi"), 1),
])
def test_factorized_chain_all_fallback_levels(obj, prepare, steps, names, multiplier):
    gen, events = inputs()
    frame = gen.merge(events)
    objects = prepare(frame)
    maps = [_build_factor_map(objects, factor_specs(BINNING)[name][1]) for name in names]
    index = ["fallback_level", "x_bin", "y_bin", "z_bin"]
    for previous, current in zip(maps, maps[1:]):
        pd.testing.assert_series_equal(previous.set_index(index).passed, current.set_index(index).total, check_names=False)
    expected = oracle(events, obj, steps) * multiplier
    for i, factor in enumerate(maps):
        inclusive = factor[factor.fallback_level == "inclusive"].iloc[0]
        assert (inclusive.total, inclusive.passed) == tuple(expected[i:i+2])
        assert factor.passed.between(0, factor.total).all()
    if multiplier == 2:
        stacked = pd.concat([build_stacked_jpsi_acceptance_maps(gen, events, BINNING),
                             build_stacked_jpsi_efficiency_maps(gen, events, BINNING)])
        for step, factor in zip(steps, maps):
            actual = stacked[stacked.step == step].set_index(["x_bin", "y_bin"])[["total", "passed"]]
            expected = factor[factor.fallback_level == "fine"].set_index(["x_bin", "y_bin"])[["total", "passed"]]
            pd.testing.assert_frame_equal(actual, expected)


@pytest.mark.parametrize("missing", PER_JPSI_STEPS)
def test_missing_intermediate_step_blocks_later_steps(missing):
    gen, events = inputs()
    events[f"jpsi_lead_{missing}"] = np.nan
    rows = build_cutflow(events).query("object == 'jpsi_lead'").set_index("step")
    for step in PER_JPSI_STEPS[PER_JPSI_STEPS.index(missing):]:
        assert rows.loc[step, "conditional_passed"] == 0
    actual = _jpsi_object_frame(gen.merge(events))
    events[f"jpsi_lead_{missing}"] = 0
    pd.testing.assert_frame_equal(actual, _jpsi_object_frame(gen.merge(events)))


def test_rebuild_preserves_binning_and_configuration(tmp_path):
    from efficiency_workflow.config import default_efficiency_definition
    from efficiency_workflow.products import build_derived_sample_products
    from scripts.efficiency.rebuild_efficiency_maps import rebuild_efficiency_maps_for_sample

    gen, events = inputs()
    for obj in CHAINS:
        gen[f"{obj}_abs_y"] = gen[f"{obj}_y"].abs()
    gen["triple_pt"], gen["triple_abs_y"], gen["triple_mass"] = 18., .4, 10.
    for step in EVENT_STEPS:
        events[step] = 0
    source, dest = tmp_path / "source" / "JJP_TEST", tmp_path / "rebuilt" / "JJP_TEST"
    source.mkdir(parents=True)
    gen.to_parquet(source / "gen_systems.parquet")
    events.to_parquet(source / "event_step_flags.parquet")
    definition = default_efficiency_definition().to_dict()
    definition["event_endpoint"] = "Pri_fitValid"
    for key in definition["binning"]:
        definition["binning"][key] = list(getattr(BINNING, key))
    metadata = {"efficiency_definition": definition, "source_note": "preserve me"}
    (source / "configuration_metadata.json").write_text(json.dumps(metadata))
    out = rebuild_efficiency_maps_for_sample(source, dest)
    assert (dest / "configuration_metadata.json").read_bytes() == (source / "configuration_metadata.json").read_bytes()
    counts = pd.read_parquet(out)
    obj = counts.query("map_type == 'object_2d' and object == 'jpsi_lead'")
    assert set(obj.x_max) == {10., 20.}
    derived = build_derived_sample_products(dest, tmp_path / "derived")
    assert set(derived.stacked_jpsi_efficiency_df.x_max) == {10., 20.}
    from efficiency_workflow.build_factorized_maps import build_factorized_maps_for_sample
    build_factorized_maps_for_sample(dest, dest / "maps")
    manifest = json.loads((dest / "maps" / "manifest.json").read_text())
    assert manifest["event_end_step"] == "Pri_fitValid"
    with pytest.raises(FileExistsError):
        rebuild_efficiency_maps_for_sample(source, dest)
    # Old counts cannot feed the cumulative plot bundle without regeneration.
    counts.drop(columns="selection_semantics").to_parquet(source / "efficiency_maps.parquet")
    with pytest.raises(ValueError, match="rebuild_efficiency_maps.py"):
        build_derived_sample_products(source, tmp_path / "legacy_derived")

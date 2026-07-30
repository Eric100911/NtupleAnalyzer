from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import awkward as ak
import numpy as np
import pandas as pd
import uproot

from .config import OfflineSelectionConfig
from .efficiency import (
    ALL_KNOWN_BRANCHES,
    EfficiencyBinning,
    _process_efficiency_chunk_vectorized,
    _uproot_read_options,
    build_cutflow,
)


DEFAULT_AUDIT_INPUT = Path("test_data/test_JpsiJpsiPhi_v2p0_patch1_numEvent118.root")

OBJECT_CHAINS: dict[str, tuple[str, ...]] = {
    "jpsi_lead": ("fiducial", "muonRECO", "muonID", "dimuon"),
    "jpsi_sublead": ("fiducial", "muonRECO", "muonID", "dimuon"),
    "phi": ("fiducial", "kaonRECO", "kaonID", "dikaon"),
}

EVENT_CHAIN: tuple[str, ...] = (
    "s_cand",
    "hlt_event",
    "hlt_muon_matched",
    "four_muon_vtx",
)

PRI_ENDPOINTS: tuple[str, ...] = (
    "Pri_fitValid",
    "Pri_fitPass",
    "Pri_assocPVPass",
    "Pri_trackPVPass",
)

AUDIT_CONTEXT_BRANCHES = {
    "DiOnia_fitValid",
    "DiOnia_fitPass",
    "DiOnia_commonRecVtxPass",
    "DiOnia_commonRecVtxIdx",
    "DiOnia_passAny",
    "DiOnia_Chi2",
    "DiOnia_ndof",
    "DiOnia_VtxProb",
    "MatchJpsiTriggerNames",
    "SingleJpsi_eta",
    "SinglePhi_eta",
    "SinglePhi_y",
    "RecoKaonTrack_isHighPurity",
    "RecoKaonTrack_normalizedChi2",
    "RecoKaonTrack_numberOfHits",
}


@dataclass(frozen=True)
class EventKey:
    source_file: str
    entry: int
    run: int
    lumi: int
    event: int


@dataclass(frozen=True)
class MembershipRecord:
    source_file: str
    entry: int
    run: int
    lumi: int
    event: int
    scope: str
    step: str
    flag_column: str
    previous_step: str
    raw: bool
    cumulative_denominator: bool
    cumulative_numerator: bool
    rejected: bool
    adjacent_raw_denominator: bool
    adjacent_raw_numerator: bool
    raw_only: bool


def _bool_series(frame: pd.DataFrame, column: str, default: bool = False) -> pd.Series:
    if column not in frame:
        return pd.Series(default, index=frame.index, dtype=bool)
    return frame[column].fillna(0).astype(bool)


def classify_memberships(event_df: pd.DataFrame) -> pd.DataFrame:
    """Classify every event under cumulative and adjacent-raw semantics."""
    if event_df.empty:
        return pd.DataFrame(columns=list(MembershipRecord.__dataclass_fields__))

    records: list[dict[str, Any]] = []
    identity = ("source_file", "entry", "run", "lumi", "event")

    def append_chain(scope: str, steps: Sequence[str], columns: Sequence[str]) -> None:
        cumulative = _bool_series(event_df, "full_gen")
        previous_raw = _bool_series(event_df, "full_gen")
        previous_name = "full_gen"
        for step, column in zip(steps, columns):
            raw = _bool_series(event_df, column)
            denominator = cumulative
            numerator = denominator & raw
            adjacent_denominator = previous_raw
            adjacent_numerator = adjacent_denominator & raw
            for index in event_df.index:
                row = event_df.loc[index]
                payload = {name: row[name] for name in identity}
                payload.update(
                    {
                        "scope": scope,
                        "step": step,
                        "flag_column": column,
                        "previous_step": previous_name,
                        "raw": bool(raw.loc[index]),
                        "cumulative_denominator": bool(denominator.loc[index]),
                        "cumulative_numerator": bool(numerator.loc[index]),
                        "rejected": bool(denominator.loc[index] and not raw.loc[index]),
                        "adjacent_raw_denominator": bool(adjacent_denominator.loc[index]),
                        "adjacent_raw_numerator": bool(adjacent_numerator.loc[index]),
                        "raw_only": bool(raw.loc[index] and not denominator.loc[index]),
                    }
                )
                records.append(asdict(MembershipRecord(**payload)))
            cumulative = numerator
            previous_raw = raw
            previous_name = step

    for scope, steps in OBJECT_CHAINS.items():
        append_chain(scope, steps, [f"{scope}_{step}" for step in steps])

    append_chain("event", EVENT_CHAIN, EVENT_CHAIN)

    four_muon = _bool_series(event_df, "four_muon_vtx")
    for step in PRI_ENDPOINTS:
        raw = _bool_series(event_df, step)
        numerator = four_muon & raw
        for index in event_df.index:
            row = event_df.loc[index]
            payload = {name: row[name] for name in identity}
            payload.update(
                {
                    "scope": "event",
                    "step": step,
                    "flag_column": step,
                    "previous_step": "four_muon_vtx",
                    "raw": bool(raw.loc[index]),
                    "cumulative_denominator": bool(four_muon.loc[index]),
                    "cumulative_numerator": bool(numerator.loc[index]),
                    "rejected": bool(four_muon.loc[index] and not raw.loc[index]),
                    "adjacent_raw_denominator": bool(four_muon.loc[index]),
                    "adjacent_raw_numerator": bool(numerator.loc[index]),
                    "raw_only": bool(raw.loc[index] and not four_muon.loc[index]),
                }
            )
            records.append(asdict(MembershipRecord(**payload)))

    return pd.DataFrame(records)


def summarize_memberships(membership_df: pd.DataFrame, event_df: pd.DataFrame) -> pd.DataFrame:
    if membership_df.empty:
        return pd.DataFrame()
    grouped = (
        membership_df.groupby(["scope", "step", "flag_column", "previous_step"], sort=False)
        .agg(
            raw_passed=("raw", "sum"),
            cumulative_total=("cumulative_denominator", "sum"),
            cumulative_passed=("cumulative_numerator", "sum"),
            rejected=("rejected", "sum"),
            adjacent_raw_total=("adjacent_raw_denominator", "sum"),
            adjacent_raw_passed=("adjacent_raw_numerator", "sum"),
            raw_only=("raw_only", "sum"),
        )
        .reset_index()
    )
    grouped["cumulative_efficiency"] = np.where(
        grouped["cumulative_total"] > 0,
        grouped["cumulative_passed"] / grouped["cumulative_total"],
        np.nan,
    )
    grouped["adjacent_raw_efficiency"] = np.where(
        grouped["adjacent_raw_total"] > 0,
        grouped["adjacent_raw_passed"] / grouped["adjacent_raw_total"],
        np.nan,
    )

    cutflow = build_cutflow(event_df)
    if cutflow.empty:
        return grouped
    cutflow = cutflow.copy()
    cutflow["scope"] = cutflow["object"].replace("", "event")
    cutflow = cutflow.rename(
        columns={
            "conditional_total": "pipeline_conditional_total",
            "conditional_passed": "pipeline_conditional_passed",
            "conditional_efficiency": "pipeline_conditional_efficiency",
        }
    )
    keep = [
        "scope",
        "step",
        "pipeline_conditional_total",
        "pipeline_conditional_passed",
        "pipeline_conditional_efficiency",
    ]
    result = grouped.merge(cutflow[keep], on=["scope", "step"], how="left")
    result["pipeline_matches_cumulative"] = (
        (result["pipeline_conditional_total"] == result["cumulative_total"])
        & (result["pipeline_conditional_passed"] == result["cumulative_passed"])
    )
    result["pipeline_matches_adjacent_raw"] = (
        (result["pipeline_conditional_total"] == result["adjacent_raw_total"])
        & (result["pipeline_conditional_passed"] == result["adjacent_raw_passed"])
    )
    result["pipeline_non_binomial"] = (
        result["pipeline_conditional_passed"] > result["pipeline_conditional_total"]
    )
    return result


def build_factor_summary(event_df: pd.DataFrame) -> pd.DataFrame:
    """Inclusive numerator/denominator membership for the factorized factors."""
    specs: list[tuple[str, str, str, str]] = []
    for scope in ("jpsi_lead", "jpsi_sublead"):
        specs.extend(
            [
                (f"acceptance_{scope}", scope, f"{scope}_fiducial", "full_gen"),
                (f"eff_muReco_{scope}", scope, f"{scope}_muonRECO", f"{scope}_fiducial"),
                (f"eff_muID_{scope}", scope, f"{scope}_muonID", f"{scope}_muonRECO"),
                (f"eff_dimuon_{scope}", scope, f"{scope}_dimuon", f"{scope}_muonID"),
            ]
        )
    specs.extend(
        [
            ("acceptance_phi", "phi", "phi_fiducial", "full_gen"),
            ("eff_kaonReco_phi", "phi", "phi_kaonRECO", "phi_fiducial"),
            ("eff_kaonID_phi", "phi", "phi_kaonID", "phi_kaonRECO"),
            ("eff_dikaon_phi", "phi", "phi_dikaon", "phi_kaonID"),
            ("eff_hlt", "event", "hlt_muon_matched", "s_cand"),
            ("eff_4mu_vtx", "event", "four_muon_vtx", "hlt_muon_matched"),
        ]
    )
    specs.extend((f"eff_{step}", "event", step, "four_muon_vtx") for step in PRI_ENDPOINTS)

    rows: list[dict[str, Any]] = []
    for factor, scope, numerator_col, denominator_col in specs:
        denominator = _bool_series(event_df, denominator_col)
        numerator = denominator & _bool_series(event_df, numerator_col)
        total = int(denominator.sum())
        passed = int(numerator.sum())
        rows.append(
            {
                "factor": factor,
                "scope": scope,
                "numerator_column": numerator_col,
                "denominator_column": denominator_col,
                "total": total,
                "passed": passed,
                "efficiency": passed / total if total else math.nan,
            }
        )
    return pd.DataFrame(rows)


def build_no_trigger_summary(event_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize the no-trigger-matching diagnostic chain without event cards."""
    specs = [
        ("four_muon_vtx_noTrigMatch", "hlt_event"),
        ("Pri_fitValid_noTrigMatch", "four_muon_vtx_noTrigMatch"),
        ("Pri_fitPass_noTrigMatch", "four_muon_vtx_noTrigMatch"),
        ("Pri_assocPVPass_noTrigMatch", "four_muon_vtx_noTrigMatch"),
        ("Pri_trackPVPass_noTrigMatch", "four_muon_vtx_noTrigMatch"),
    ]
    rows: list[dict[str, Any]] = []
    for numerator_col, denominator_col in specs:
        denominator = _bool_series(event_df, denominator_col)
        numerator = denominator & _bool_series(event_df, numerator_col)
        total = int(denominator.sum())
        passed = int(numerator.sum())
        rows.append(
            {
                "step": numerator_col,
                "numerator_column": numerator_col,
                "denominator_column": denominator_col,
                "total": total,
                "passed": passed,
                "efficiency": passed / total if total else math.nan,
            }
        )
    return pd.DataFrame(rows)


def select_examples(membership_df: pd.DataFrame, examples_per_category: int = 5) -> dict[str, list[EventKey]]:
    result: dict[str, list[EventKey]] = {}
    if membership_df.empty:
        return result
    categories = {
        "numerator": "cumulative_numerator",
        "rejected": "rejected",
        "raw_only": "raw_only",
    }
    ordered = membership_df.sort_values(["source_file", "entry", "scope", "step"])
    for (scope, step), subset in ordered.groupby(["scope", "step"], sort=False):
        for category, column in categories.items():
            selected = subset[subset[column]].head(examples_per_category)
            key = f"{scope}/{step}/{category}"
            result[key] = [
                EventKey(
                    source_file=str(row.source_file),
                    entry=int(row.entry),
                    run=int(row.run),
                    lumi=int(row.lumi),
                    event=int(row.event),
                )
                for row in selected.itertuples(index=False)
            ]
    return result


def _to_python_event(arrays: ak.Array, index: int = 0) -> dict[str, Any]:
    return {field: ak.to_list(arrays[field][index]) for field in arrays.fields}


def _value(event: dict[str, Any], field: str, index: int, default: Any = None) -> Any:
    values = event.get(field)
    if values is None or not isinstance(values, list) or index < 0 or index >= len(values):
        return default
    return values[index]


def _as_int(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _rapidity(pt: float, eta: float, mass: float) -> float:
    pz = pt * math.sinh(eta)
    energy = math.sqrt(max(pt * pt + pz * pz + mass * mass, 0.0))
    if energy + pz <= 0 or energy - pz <= 0:
        return math.nan
    return 0.5 * math.log((energy + pz) / (energy - pz))


def _ancestor(event: dict[str, Any], start: int, target_abs_pdg: int, max_depth: int = 16) -> int:
    pdg = event.get("MC_GenPart_pdgId", [])
    mother = event.get("MC_GenPart_motherGenIdx", [])
    index = _as_int(start)
    for _ in range(max_depth):
        if index < 0 or index >= len(pdg):
            return -1
        if abs(_as_int(pdg[index], 0)) == target_abs_pdg:
            return index
        index = _as_int(mother[index] if index < len(mother) else -1)
    return -1


def _find_gen_system(event: dict[str, Any], cfg: OfflineSelectionConfig) -> dict[str, Any] | None:
    pdg = event.get("MC_GenPart_pdgId", [])
    mother = event.get("MC_GenPart_motherGenIdx", [])
    pt = event.get("MC_GenPart_pt", [])
    eta = event.get("MC_GenPart_eta", [])
    mass = event.get("MC_GenPart_mass", [])
    particles: list[dict[str, Any]] = []
    for index, pdg_id in enumerate(pdg):
        abs_pdg = abs(_as_int(pdg_id, 0))
        if abs_pdg not in (443, 333):
            continue
        daughters = [
            daughter
            for daughter, parent in enumerate(mother)
            if _as_int(parent) == index
            and abs(_as_int(pdg[daughter], 0)) == (13 if abs_pdg == 443 else 321)
        ]
        particle_pt = float(pt[index])
        particle_eta = float(eta[index])
        particle_mass = float(mass[index])
        particle_y = _rapidity(particle_pt, particle_eta, particle_mass)
        valid = (
            len(daughters) >= 2
            and (
                (abs_pdg == 443 and particle_pt > cfg.jpsi_pt_min and abs(particle_y) < cfg.jpsi_abs_y_max)
                or (abs_pdg == 333 and particle_pt > cfg.phi_pt_min and abs(particle_y) < cfg.phi_abs_y_max)
            )
        )
        if valid:
            particles.append(
                {
                    "idx": index,
                    "pdg_id": _as_int(pdg_id),
                    "pt": particle_pt,
                    "eta": particle_eta,
                    "mass": particle_mass,
                    "y": particle_y,
                    "daughter_indices": daughters[:2],
                }
            )
    jpsis = sorted((item for item in particles if abs(item["pdg_id"]) == 443), key=lambda item: item["pt"], reverse=True)
    phis = sorted((item for item in particles if abs(item["pdg_id"]) == 333), key=lambda item: item["pt"], reverse=True)
    if len(jpsis) < 2 or not phis:
        return None
    return {
        "jpsi_lead": jpsis[0],
        "jpsi_sublead": jpsis[1],
        "phi": phis[0],
        "n_jpsi": len(jpsis),
        "n_phi": len(phis),
    }


def _fiducial_evidence(
    event: dict[str, Any], particle: dict[str, Any], cfg: OfflineSelectionConfig, kind: str
) -> tuple[bool, list[dict[str, Any]]]:
    result = True
    details: list[dict[str, Any]] = []
    for index in particle["daughter_indices"]:
        pt = float(_value(event, "MC_GenPart_pt", index, math.nan))
        eta = float(_value(event, "MC_GenPart_eta", index, math.nan))
        if kind == "muon":
            passed = (abs(eta) < 1.2 and pt > cfg.mu_pt_barrel_min) or (
                1.2 <= abs(eta) < cfg.mu_abs_eta_max and pt > cfg.mu_pt_endcap_min
            )
            criterion = (
                f"|eta|<1.2 && pt>{cfg.mu_pt_barrel_min}, or "
                f"1.2<=|eta|<{cfg.mu_abs_eta_max} && pt>{cfg.mu_pt_endcap_min}"
            )
        else:
            passed = pt > cfg.track_pt_min and abs(eta) < cfg.track_abs_eta_max
            criterion = f"pt>{cfg.track_pt_min} && |eta|<{cfg.track_abs_eta_max}"
        result = result and passed
        details.append({"gen_idx": index, "pt": pt, "eta": eta, "criterion": criterion, "passed": passed})
    return result, details


def _daughter_reco_evidence(
    event: dict[str, Any],
    particle: dict[str, Any],
    *,
    kind: str,
    cfg: OfflineSelectionConfig,
) -> tuple[bool, bool, list[dict[str, Any]]]:
    if kind == "muon":
        match_field = "muGenMatchIdx"
        quality_fields = ("muIsPatSoftMuon",)
    else:
        match_field = "RecoKaonTrack_genMatchIdx"
        quality_fields = (
            "RecoKaonTrack_normalizedChi2",
            "RecoKaonTrack_numberOfHits",
            "RecoKaonTrack_isHighPurity",
        )
    matches = event.get(match_field, [])
    details: list[dict[str, Any]] = []
    all_reco = True
    all_quality = True
    for daughter in particle["daughter_indices"]:
        reco_indices = [index for index, gen_index in enumerate(matches) if _as_int(gen_index) == daughter]
        quality_matches: list[int] = []
        reco_details: list[dict[str, Any]] = []
        for index in reco_indices:
            if kind == "muon":
                passed_quality = bool(_as_int(_value(event, quality_fields[0], index, 0), 0))
                operands = {"muIsPatSoftMuon": passed_quality}
            else:
                if quality_fields[0] in event:
                    chi2 = float(_value(event, quality_fields[0], index, math.inf))
                    hits = _as_int(_value(event, quality_fields[1], index, 0), 0)
                    high_purity = bool(_as_int(_value(event, quality_fields[2], index, 0), 0))
                    passed_quality = chi2 < cfg.kaon_chi2_max and hits > cfg.kaon_n_valid_hits_min
                    if cfg.kaon_require_highpurity:
                        passed_quality = passed_quality and high_purity
                    operands = {
                        "normalizedChi2": chi2,
                        "numberOfHits": hits,
                        "isHighPurity": high_purity,
                    }
                else:
                    track_pt = float(_value(event, "RecoKaonTrack_pt", index, -1.0))
                    track_eta = float(_value(event, "RecoKaonTrack_eta", index, math.nan))
                    passed_quality = track_pt > cfg.track_pt_min and abs(track_eta) < cfg.track_abs_eta_max
                    operands = {"pt": track_pt, "eta": track_eta}
            if passed_quality:
                quality_matches.append(index)
            reco_details.append({"reco_idx": index, "quality_passed": passed_quality, **operands})
        all_reco = all_reco and bool(reco_indices)
        all_quality = all_quality and bool(quality_matches)
        details.append(
            {
                "gen_daughter_idx": daughter,
                "matched_reco_indices": reco_indices,
                "quality_matched_reco_indices": quality_matches,
                "reco_objects": reco_details,
            }
        )
    return all_reco, all_quality, details


def _single_candidate_evidence(
    event: dict[str, Any],
    particle: dict[str, Any],
    *,
    kind: str,
    cfg: OfflineSelectionConfig,
) -> tuple[bool, list[dict[str, Any]]]:
    if kind == "jpsi":
        prefix = "SingleJpsi"
        first_gen = f"{prefix}_mu1_genMatchIdx"
        second_gen = f"{prefix}_mu2_genMatchIdx"
        target = 443
    else:
        prefix = "SinglePhi"
        first_gen = f"{prefix}_K1_genMatchIdx"
        second_gen = f"{prefix}_K2_genMatchIdx"
        target = 333
    candidates: list[dict[str, Any]] = []
    for index in range(len(event.get(f"{prefix}_mass", []))):
        ancestor1 = _ancestor(event, _as_int(_value(event, first_gen, index, -1)), target)
        ancestor2 = _ancestor(event, _as_int(_value(event, second_gen, index, -1)), target)
        same_parent = ancestor1 >= 0 and ancestor1 == ancestor2 == particle["idx"]
        mass = float(_value(event, f"{prefix}_mass", index, math.nan))
        pt = float(_value(event, f"{prefix}_pt", index, -1.0))
        vtx_prob = float(_value(event, f"{prefix}_VtxProb", index, -1.0))
        fit_valid = bool(_as_int(_value(event, f"{prefix}_fitValid", index, 0), 0))
        fit_pass = bool(_as_int(_value(event, f"{prefix}_fitPass", index, 0), 0))
        if kind == "jpsi":
            if f"{prefix}_y" in event:
                y = float(_value(event, f"{prefix}_y", index, math.nan))
            else:
                px = float(_value(event, f"{prefix}_px", index, 0.0))
                py = float(_value(event, f"{prefix}_py", index, 0.0))
                pz = float(_value(event, f"{prefix}_pz", index, 0.0))
                momentum_pt = math.sqrt(px * px + py * py)
                eta = math.asinh(pz / momentum_pt) if momentum_pt > 0 else math.nan
                y = _rapidity(momentum_pt, eta, mass)
            quality = (
                cfg.jpsi_mass_window[0] <= mass <= cfg.jpsi_mass_window[1]
                and pt > cfg.jpsi_pt_min
                and abs(y) < cfg.jpsi_abs_y_max
                and vtx_prob > cfg.jpsi_vtxprob_min
                and fit_valid
                and fit_pass
            )
        else:
            y = float(_value(event, f"{prefix}_y", index, math.nan))
            quality = (
                cfg.phi_mass_window[0] <= mass <= cfg.phi_mass_window[1]
                and pt > cfg.phi_pt_min
                and vtx_prob > cfg.phi_vtxprob_min
                and fit_valid
                and fit_pass
            )
        if same_parent or ancestor1 == particle["idx"] or ancestor2 == particle["idx"]:
            candidates.append(
                {
                    "candidate_idx": index,
                    "ancestor_1": ancestor1,
                    "ancestor_2": ancestor2,
                    "same_target_parent": same_parent,
                    "mass": mass,
                    "pt": pt,
                    "y": y,
                    "VtxProb": vtx_prob,
                    "fitValid": fit_valid,
                    "fitPass": fit_pass,
                    "quality_passed": quality,
                    "witness": same_parent and quality,
                }
            )
    return any(item["witness"] for item in candidates), candidates


def _event_path_evidence(event: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    paths: list[dict[str, Any]] = []
    for name, result in zip(event.get("TrigNames", []), event.get("TrigRes", [])):
        relevant = "HLT_Dimuon0_Jpsi3p5_Muon2_v" in str(name) or "HLT_DoubleMu4_3_LowMass_v" in str(name)
        if relevant:
            paths.append({"name": str(name), "result": bool(result)})
    return any(item["result"] for item in paths), paths


def _mu_has_trigger_filter(
    event: dict[str, Any], muon_index: int, trigger_index: int | None, filter_index: int | None
) -> bool:
    if trigger_index is None or filter_index is None or muon_index < 0:
        return False
    trigger_values = _value(event, "muJpsiMatchedTriggerIndices", muon_index, [])
    filter_values = _value(event, "muJpsiMatchedFilterIndices", muon_index, [])
    return trigger_index in list(trigger_values or []) and filter_index in list(filter_values or [])


def _composite_candidate_evidence(
    event: dict[str, Any],
    system: dict[str, Any],
    *,
    s_cand: bool,
    path_fired: bool,
    trigger_filter_map: dict[str, int],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    n_candidates = len(event.get("Jpsi_1_mass", []))
    for index in range(n_candidates):
        muon_indices = [
            _as_int(_value(event, "Jpsi_1_mu_1_Idx", index, -1)),
            _as_int(_value(event, "Jpsi_1_mu_2_Idx", index, -1)),
            _as_int(_value(event, "Jpsi_2_mu_1_Idx", index, -1)),
            _as_int(_value(event, "Jpsi_2_mu_2_Idx", index, -1)),
        ]
        muon_ancestors = [
            _ancestor(event, _as_int(_value(event, "muGenMatchIdx", muon_index, -1)), 443)
            for muon_index in muon_indices
        ]
        jpsi1 = muon_ancestors[0] if muon_ancestors[0] >= 0 and muon_ancestors[0] == muon_ancestors[1] else -1
        jpsi2 = muon_ancestors[2] if muon_ancestors[2] >= 0 and muon_ancestors[2] == muon_ancestors[3] else -1
        phi_ancestors = [
            _ancestor(event, _as_int(_value(event, field, index, -1)), 333)
            for field in ("Phi_K_1_genMatchIdx", "Phi_K_2_genMatchIdx")
        ]
        phi = phi_ancestors[0] if phi_ancestors[0] >= 0 and phi_ancestors[0] == phi_ancestors[1] else -1
        gen_matched = (
            phi == system["phi"]["idx"]
            and {jpsi1, jpsi2} == {system["jpsi_lead"]["idx"], system["jpsi_sublead"]["idx"]}
        )

        d0 = [
            _mu_has_trigger_filter(
                event,
                muon_index,
                trigger_filter_map.get("dimuon0_trig"),
                trigger_filter_map.get("dimuon0_filt"),
            )
            for muon_index in muon_indices
        ]
        dm = [
            _mu_has_trigger_filter(
                event,
                muon_index,
                trigger_filter_map.get("doublemu_trig"),
                trigger_filter_map.get("doublemu_filt"),
            )
            for muon_index in muon_indices
        ]
        hlt_match = (
            (sum(d0) >= 3 and ((d0[0] and d0[1]) or (d0[2] and d0[3])))
            or (dm[0] and dm[1])
            or (dm[2] and dm[3])
        )
        vertex_ids = [_as_int(_value(event, "muVertexId", muon_index, -1)) for muon_index in muon_indices]
        four_muon = bool(vertex_ids and vertex_ids[0] >= 0 and len(set(vertex_ids)) == 1)
        candidate_base = gen_matched and s_cand
        hlt_stage = candidate_base and path_fired and hlt_match
        four_stage = hlt_stage and four_muon
        pri = {step: bool(_as_int(_value(event, step, index, 0), 0)) for step in PRI_ENDPOINTS}
        dionia = {
            field: _value(event, field, index)
            for field in sorted(AUDIT_CONTEXT_BRANCHES)
            if field.startswith("DiOnia_") and field in event
        }
        result.append(
            {
                "candidate_idx": index,
                "muon_indices": muon_indices,
                "muon_jpsi_ancestors": muon_ancestors,
                "jpsi_1_gen_idx": jpsi1,
                "jpsi_2_gen_idx": jpsi2,
                "phi_gen_idx": phi,
                "triple_gen_matched": gen_matched,
                "trigger_match": {"dimuon0_muons": d0, "doublemu_muons": dm, "passed": hlt_match},
                "muVertexId": vertex_ids,
                "four_muon_current_predicate": four_muon,
                "DiOnia_context": dionia,
                "Pri": pri,
                "stages": {
                    "candidate_base": candidate_base,
                    "hlt_muon_matched": hlt_stage,
                    "four_muon_vtx": four_stage,
                    **{step: four_stage and value for step, value in pri.items()},
                },
            }
        )
    return result


def _bin_index(value: float, edges: Sequence[float]) -> int | None:
    if not math.isfinite(value):
        return None
    index = int(np.searchsorted(np.asarray(edges), value, side="right") - 1)
    return index if 0 <= index < len(edges) - 1 else None


def evaluate_event_evidence(
    event: dict[str, Any],
    pipeline_row: dict[str, Any],
    *,
    cfg: OfflineSelectionConfig,
    binning: EfficiencyBinning,
    trigger_filter_map: dict[str, int],
) -> dict[str, Any]:
    """Rebuild current raw predicates from branches and retain their witnesses."""
    system = _find_gen_system(event, cfg)
    if system is None:
        return {
            "identity": {key: pipeline_row.get(key) for key in ("source_file", "entry", "run", "lumi", "event")},
            "error": "No full GEN J/psi+J/psi+phi system under current parent-level cuts.",
        }

    objects: dict[str, Any] = {}
    raw_flags: dict[str, bool] = {}
    for scope, kind in (("jpsi_lead", "muon"), ("jpsi_sublead", "muon"), ("phi", "kaon")):
        particle = system[scope]
        fiducial, fiducial_details = _fiducial_evidence(event, particle, cfg, kind)
        reco, quality, reco_details = _daughter_reco_evidence(
            event, particle, kind=kind, cfg=cfg
        )
        candidate_pass, candidate_details = _single_candidate_evidence(
            event, particle, kind="jpsi" if kind == "muon" else "phi", cfg=cfg
        )
        suffixes = (
            ("fiducial", fiducial),
            ("muonRECO" if kind == "muon" else "kaonRECO", reco),
            ("muonID" if kind == "muon" else "kaonID", quality),
            ("dimuon" if kind == "muon" else "dikaon", candidate_pass),
        )
        for suffix, value in suffixes:
            raw_flags[f"{scope}_{suffix}"] = value
        objects[scope] = {
            "gen_particle": particle,
            "fiducial": {"passed": fiducial, "daughters": fiducial_details},
            "reconstruction_and_id": {
                "reco_passed": reco,
                "id_passed": quality,
                "daughters": reco_details,
            },
            "single_candidates": candidate_details,
        }

    s_cand = all(raw_flags.values())
    path_fired, paths = _event_path_evidence(event)
    composite = _composite_candidate_evidence(
        event,
        system,
        s_cand=s_cand,
        path_fired=path_fired,
        trigger_filter_map=trigger_filter_map,
    )
    recomputed_event_flags = {
        "full_gen": True,
        "s_cand": s_cand,
        "hlt_event": s_cand and path_fired,
        "hlt_muon_matched": any(item["stages"]["hlt_muon_matched"] for item in composite),
        "four_muon_vtx": any(item["stages"]["four_muon_vtx"] for item in composite),
        **{
            step: any(item["stages"][step] for item in composite)
            for step in PRI_ENDPOINTS
        },
    }
    recomputed = {**raw_flags, **recomputed_event_flags}
    comparisons = {
        column: {
            "recomputed": bool(value),
            "pipeline": bool(pipeline_row.get(column, False)),
            "matches": bool(value) == bool(pipeline_row.get(column, False)),
        }
        for column, value in recomputed.items()
    }

    gen_bins: dict[str, Any] = {}
    for scope in ("jpsi_lead", "jpsi_sublead", "phi"):
        particle = system[scope]
        pt_edges = binning.phi_pt_edges if scope == "phi" else binning.jpsi_pt_edges
        gen_bins[scope] = {
            "pt": particle["pt"],
            "y": particle["y"],
            "pt_bin": _bin_index(particle["pt"], pt_edges),
            "signed_y_bin": _bin_index(particle["y"], binning.object_y_edges),
            "abs_y_bin": _bin_index(abs(particle["y"]), binning.object_abs_y_edges),
        }

    return {
        "identity": {key: pipeline_row.get(key) for key in ("source_file", "entry", "run", "lumi", "event")},
        "gen_system": system,
        "map_bins": gen_bins,
        "objects": objects,
        "trigger": {"path_fired": path_fired, "paths": paths, "index_map": trigger_filter_map},
        "composite_candidates": composite,
        "recomputed_flags": recomputed,
        "pipeline_comparison": comparisons,
        "mismatched_flags": [column for column, item in comparisons.items() if not item["matches"]],
        "definition_context": {
            "four_muon_current_reference": "all four composite-candidate muVertexId values are equal and non-negative",
            "DiOnia_fields_are_context_only": True,
        },
    }


def detect_tree_path(root_file: uproot.ReadOnlyDirectory, requested: str = "auto") -> str:
    if requested != "auto":
        if requested not in root_file:
            raise KeyError(f"Missing requested tree {requested!r}")
        return requested
    for candidate in ("X_data", "mkcands/X_data"):
        if candidate in root_file:
            return candidate
    raise KeyError("Could not find X_data or mkcands/X_data")


def read_trigger_filter_map(
    root_file: uproot.ReadOnlyDirectory, data_tree_path: str
) -> dict[str, int]:
    directory = data_tree_path.rsplit("/", 1)[0] if "/" in data_tree_path else ""
    config_path = f"{directory}/X_config" if directory else "X_config"
    if config_path not in root_file:
        return {}
    config = root_file[config_path]
    if "TriggersForJpsi" not in config or "FiltersForJpsi" not in config:
        return {}
    triggers = ak.to_list(config["TriggersForJpsi"].array(library="ak"))[0]
    filters = ak.to_list(config["FiltersForJpsi"].array(library="ak"))[0]
    result: dict[str, int] = {}
    for index, name in enumerate(triggers):
        if "Dimuon0_Jpsi3p5_Muon2" in str(name):
            result["dimuon0_trig"] = index
        elif "DoubleMu4_3_LowMass" in str(name):
            result["doublemu_trig"] = index
    for index, name in enumerate(filters):
        if "hltJpsiMuonL3Filtered3p5" in str(name):
            result["dimuon0_filt"] = index
        elif "hltDoubleMu43LowMassL3Filtered" in str(name):
            result["doublemu_filt"] = index
    return result


def load_pipeline_events(
    inputs: Sequence[str | Path],
    *,
    cfg: OfflineSelectionConfig,
    tree_path: str = "auto",
    max_events: int | None = None,
    step_size: str = "100 MB",
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, Any]]]:
    gen_parts: list[pd.DataFrame] = []
    event_parts: list[pd.DataFrame] = []
    source_info: dict[str, dict[str, Any]] = {}
    remaining = max_events
    for raw_path in inputs:
        path = str(raw_path)
        options = _uproot_read_options(path)
        with uproot.open(path, **options) as root_file:
            selected_tree_path = detect_tree_path(root_file, tree_path)
            tree = root_file[selected_tree_path]
            available = set(tree.keys())
            branches = [branch for branch in ALL_KNOWN_BRANCHES if branch in available]
            trigger_filter_map = read_trigger_filter_map(root_file, selected_tree_path)
            n_entries = int(tree.num_entries)
        stop = n_entries if remaining is None else min(n_entries, remaining)
        if stop <= 0:
            break
        iterator = uproot.iterate(
            f"{path}:{selected_tree_path}",
            filter_name=branches,
            library="ak",
            step_size=step_size,
            entry_stop=stop,
            report=True,
            **options,
        )
        for arrays, report in iterator:
            chunk = _process_efficiency_chunk_vectorized(
                arrays,
                path,
                "audit",
                cfg,
                int(report.start),
                trigger_filter_map,
            )
            if not chunk["gen_systems"].empty:
                gen_parts.append(chunk["gen_systems"])
            if not chunk["event_step_flags"].empty:
                event_parts.append(chunk["event_step_flags"])
        source_info[path] = {
            "tree_path": selected_tree_path,
            "entries_scanned": stop,
            "source_entries": n_entries,
            "trigger_filter_map": trigger_filter_map,
        }
        if remaining is not None:
            remaining -= stop
            if remaining <= 0:
                break
    return (
        pd.concat(gen_parts, ignore_index=True) if gen_parts else pd.DataFrame(),
        pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame(),
        source_info,
    )


def load_selected_evidence(
    event_df: pd.DataFrame,
    selected_keys: Iterable[EventKey],
    source_info: dict[str, dict[str, Any]],
    *,
    cfg: OfflineSelectionConfig,
    binning: EfficiencyBinning,
) -> list[dict[str, Any]]:
    by_source: dict[str, set[int]] = defaultdict(set)
    for key in selected_keys:
        by_source[key.source_file].add(key.entry)
    evidence: list[dict[str, Any]] = []
    for source_file, entries in by_source.items():
        info = source_info[source_file]
        options = _uproot_read_options(source_file)
        with uproot.open(source_file, **options) as root_file:
            tree = root_file[info["tree_path"]]
            branches = [
                branch
                for branch in sorted(set(ALL_KNOWN_BRANCHES) | AUDIT_CONTEXT_BRANCHES)
                if branch in tree.keys()
            ]
            for entry in sorted(entries):
                arrays = tree.arrays(
                    branches,
                    entry_start=entry,
                    entry_stop=entry + 1,
                    library="ak",
                )
                event = _to_python_event(arrays)
                match = event_df[
                    (event_df["source_file"] == source_file) & (event_df["entry"] == entry)
                ]
                if match.empty:
                    continue
                evidence.append(
                    evaluate_event_evidence(
                        event,
                        match.iloc[0].to_dict(),
                        cfg=cfg,
                        binning=binning,
                        trigger_filter_map=info["trigger_filter_map"],
                    )
                )
    return evidence


def write_root_skims(
    selections: Sequence[EventKey],
    source_info: dict[str, dict[str, Any]],
    output_dir: Path,
) -> list[dict[str, Any]]:
    """Clone selected entries with the complete branch schema, grouped by source."""
    if not selections:
        return []
    import ROOT

    by_source: dict[str, set[int]] = defaultdict(set)
    for key in selections:
        by_source[key.source_file].add(key.entry)
    skim_dir = output_dir / "selected_events"
    skim_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for source_index, (source_file, entries) in enumerate(by_source.items()):
        source = ROOT.TFile.Open(source_file)
        if not source or source.IsZombie():
            raise OSError(f"Could not open ROOT source for skim: {source_file}")
        tree_path = source_info[source_file]["tree_path"]
        source_tree = source.Get(tree_path)
        if source_tree is None:
            source.Close()
            raise KeyError(f"Missing source tree {tree_path!r} in {source_file}")
        output_path = skim_dir / f"source_{source_index:03d}.root"
        output = ROOT.TFile.Open(str(output_path), "RECREATE")
        directory_name = tree_path.rsplit("/", 1)[0] if "/" in tree_path else ""
        target_dir = output.mkdir(directory_name) if directory_name else output
        target_dir.cd()
        clone = source_tree.CloneTree(0)
        for entry in sorted(entries):
            source_tree.GetEntry(entry)
            clone.Fill()
        clone.Write()

        for tree_name in ("X_config", "X_lhe_run_info"):
            auxiliary_path = f"{directory_name}/{tree_name}" if directory_name else tree_name
            auxiliary = source.Get(auxiliary_path)
            if auxiliary is None:
                continue
            target_dir.cd()
            auxiliary_clone = auxiliary.CloneTree(-1, "fast")
            auxiliary_clone.SetName(tree_name)
            auxiliary_clone.Write()
        output.Close()
        source.Close()
        records.append(
            {
                "source_file": source_file,
                "output_file": str(output_path),
                "tree_path": tree_path,
                "entries": sorted(entries),
            }
        )
    return records


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def build_audit_payload(
    *,
    inputs: Sequence[str | Path],
    event_df: pd.DataFrame,
    membership_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    factor_df: pd.DataFrame,
    no_trigger_df: pd.DataFrame,
    selections: dict[str, list[EventKey]],
    evidence: list[dict[str, Any]],
    source_info: dict[str, dict[str, Any]],
    examples_per_category: int,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    if not summary_df.empty:
        for row in summary_df[summary_df["pipeline_non_binomial"].fillna(False)].itertuples(index=False):
            issues.append(
                {
                    "kind": "pipeline_non_binomial",
                    "scope": row.scope,
                    "step": row.step,
                    "conditional_total": int(row.pipeline_conditional_total),
                    "conditional_passed": int(row.pipeline_conditional_passed),
                }
            )
    for item in evidence:
        for column in item.get("mismatched_flags", []):
            issues.append(
                {
                    "kind": "branch_recomputation_mismatch",
                    "identity": item["identity"],
                    "flag": column,
                }
            )

    coverage: list[dict[str, Any]] = []
    for (scope, step), subset in membership_df.groupby(["scope", "step"], sort=False):
        for category, column in (
            ("numerator", "cumulative_numerator"),
            ("rejected", "rejected"),
            ("raw_only", "raw_only"),
        ):
            available = int(subset[column].sum())
            coverage.append(
                {
                    "scope": scope,
                    "step": step,
                    "category": category,
                    "available": available,
                    "selected": min(available, examples_per_category),
                    "quota": examples_per_category,
                    "covered": available > 0,
                }
            )

    return _jsonable(
        {
            "schema_version": 1,
            "inputs": [str(item) for item in inputs],
            "source_info": source_info,
            "n_full_gen_events": int(len(event_df)),
            "reference": "current efficiency_workflow implementation",
            "semantics": {
                "cumulative": "denominator passes all earlier raw predicates",
                "adjacent_raw": "denominator passes only the immediately previous raw predicate",
                "pipeline": "values emitted by build_cutflow without reinterpretation",
            },
            "summary": summary_df.to_dict(orient="records"),
            "factor_summary": factor_df.to_dict(orient="records"),
            "no_trigger_matching_summary": no_trigger_df.to_dict(orient="records"),
            "coverage": coverage,
            "selections": {
                key: [asdict(item) for item in values] for key, values in selections.items()
            },
            "selected_event_evidence": evidence,
            "issues": issues,
        }
    )


def _markdown_cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "—"
        return f"{value:.5g}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        if all(not isinstance(item, (dict, list, tuple)) for item in value):
            return ", ".join(_markdown_cell(item) for item in value)
    text = str(value).replace("\n", "<br>").replace("|", r"\|")
    return text or "—"


def _flatten_evidence(
    prefix: str,
    value: Any,
    rows: list[tuple[str, Any]],
) -> None:
    """Flatten nested evidence into short, stable labels for a transposed table."""
    if isinstance(value, dict):
        if not value:
            rows.append((prefix, "{}"))
        for key, child in value.items():
            label = f"{prefix}.{key}" if prefix else str(key)
            _flatten_evidence(label, child, rows)
        return
    if isinstance(value, (list, tuple)) and any(
        isinstance(item, (dict, list, tuple)) for item in value
    ):
        if not value:
            rows.append((prefix, "[]"))
        for index, child in enumerate(value):
            _flatten_evidence(f"{prefix}[{index}]", child, rows)
        return
    rows.append((prefix, value))


def _upstream_object_evidence(
    item: dict[str, Any],
    scope: str,
    step: str,
) -> list[tuple[str, Any]]:
    chain = OBJECT_CHAINS[scope]
    step_index = chain.index(step)
    rows: list[tuple[str, Any]] = []
    identity = item["identity"]
    rows.extend(
        [
            ("identity.source", Path(identity["source_file"]).name),
            ("identity.entry", identity["entry"]),
            ("identity.run:lumi:event", f"{identity['run']}:{identity['lumi']}:{identity['event']}"),
            ("selection.role", ""),
            ("flags.full_gen", item.get("recomputed_flags", {}).get("full_gen")),
        ]
    )
    for upstream_step in chain[: step_index + 1]:
        rows.append(
            (
                f"flags.{upstream_step}",
                item.get("recomputed_flags", {}).get(f"{scope}_{upstream_step}"),
            )
        )

    particle = item.get("gen_system", {}).get(scope, {})
    for field in ("idx", "pdgId", "pt", "eta", "y", "mass", "daughter_indices"):
        if field in particle:
            _flatten_evidence(f"GEN.{field}", particle[field], rows)
    for field, value in item.get("map_bins", {}).get(scope, {}).items():
        _flatten_evidence(f"map_bin.{field}", value, rows)

    evidence = item.get("objects", {}).get(scope, {})
    if step_index >= 0:
        _flatten_evidence("fiducial", evidence.get("fiducial", {}), rows)
    if step_index >= 1:
        reco = evidence.get("reconstruction_and_id", {})
        if step_index == 1:
            reco = {
                "reco_passed": reco.get("reco_passed"),
                "daughters": [
                    {
                        "gen_daughter_idx": daughter.get("gen_daughter_idx"),
                        "matched_reco_indices": daughter.get("matched_reco_indices", []),
                    }
                    for daughter in reco.get("daughters", [])
                ],
            }
        _flatten_evidence("reconstruction_and_id", reco, rows)
    if step_index >= 3:
        _flatten_evidence("single_candidates", evidence.get("single_candidates", []), rows)
    return rows


def _upstream_event_evidence(
    item: dict[str, Any],
    step: str,
) -> list[tuple[str, Any]]:
    identity = item["identity"]
    rows: list[tuple[str, Any]] = [
        ("identity.source", Path(identity["source_file"]).name),
        ("identity.entry", identity["entry"]),
        ("identity.run:lumi:event", f"{identity['run']}:{identity['lumi']}:{identity['event']}"),
        ("selection.role", ""),
        ("flags.full_gen", item.get("recomputed_flags", {}).get("full_gen")),
    ]
    event_steps = EVENT_CHAIN if step in EVENT_CHAIN else EVENT_CHAIN + PRI_ENDPOINTS
    step_index = event_steps.index(step)
    flags = item.get("recomputed_flags", {})
    for scope, chain in OBJECT_CHAINS.items():
        for object_step in chain:
            rows.append(
                (
                    f"object_flags.{scope}.{object_step}",
                    flags.get(f"{scope}_{object_step}"),
                )
            )
    for upstream_step in event_steps[: step_index + 1]:
        rows.append((f"flags.{upstream_step}", flags.get(upstream_step)))
    if step_index >= 1:
        _flatten_evidence("trigger", item.get("trigger", {}), rows)
    if step_index >= 2:
        _flatten_evidence("composite_candidates", item.get("composite_candidates", []), rows)
    return rows


def _render_transposed_examples(
    payload: dict[str, Any],
    evidence_by_identity: dict[tuple[str, int], dict[str, Any]],
) -> list[str]:
    lines = [
        "",
        "## Selected examples by step and role",
        "",
        "Each table compares events selected for one step and one membership role. "
        "Only the current step and its upstream evidence are shown; the complete "
        "machine-readable evidence remains in `audit_report.json`.",
        "",
    ]
    for selection_key, keys in payload["selections"].items():
        parts = selection_key.split("/")
        if len(parts) != 3:
            continue
        scope, step, role = parts
        items = [
            evidence_by_identity[(key["source_file"], int(key["entry"]))]
            for key in keys
            if (key["source_file"], int(key["entry"])) in evidence_by_identity
        ]
        if not items:
            continue
        lines.extend([f"### `{scope} / {step} / {role}`", ""])
        columns = [
            f"Event {index + 1}<br>`entry {item['identity']['entry']}`"
            for index, item in enumerate(items)
        ]
        per_event_rows = []
        for item in items:
            if scope in OBJECT_CHAINS:
                rows = _upstream_object_evidence(item, scope, step)
            else:
                rows = _upstream_event_evidence(item, step)
            per_event_rows.append(dict(rows))
        row_labels: list[str] = []
        for rows in per_event_rows:
            for label in rows:
                if label not in row_labels:
                    row_labels.append(label)
        lines.append("| Field | " + " | ".join(columns) + " |")
        lines.append("|---|" + "|".join("---:" for _ in columns) + "|")
        for label in row_labels:
            values = []
            for rows in per_event_rows:
                value = role if label == "selection.role" else rows.get(label)
                values.append(_markdown_cell(value))
            lines.append(f"| `{label}` | " + " | ".join(values) + " |")
        lines.append("")
    return lines


def render_markdown(payload: dict[str, Any], *, include_branch_details: bool = True) -> str:
    lines = [
        "# Efficiency event audit",
        "",
        f"- Full-GEN events inspected: {payload['n_full_gen_events']}",
        f"- Reference: {payload['reference']}",
        f"- Issues: {len(payload['issues'])}",
        "",
        "## Step membership summary",
        "",
        "| Scope | Step | Raw pass | Cumulative D | Cumulative N | Rejected | Adjacent D | Adjacent N | Raw-only | Pipeline D/N | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in payload["summary"]:
        pipeline_total = row.get("pipeline_conditional_total")
        pipeline_passed = row.get("pipeline_conditional_passed")
        pipeline = "—" if pipeline_total is None else f"{int(pipeline_total)}/{int(pipeline_passed)}"
        if row.get("pipeline_non_binomial"):
            status = "NON-BINOMIAL"
        elif row.get("pipeline_matches_cumulative"):
            status = "matches cumulative"
        elif row.get("pipeline_matches_adjacent_raw"):
            status = "matches adjacent raw"
        else:
            status = "differs"
        lines.append(
            "| {scope} | {step} | {raw_passed} | {cumulative_total} | {cumulative_passed} | "
            "{rejected} | {adjacent_raw_total} | {adjacent_raw_passed} | {raw_only} | "
            "{pipeline} | {status} |".format(pipeline=pipeline, status=status, **row)
        )

    lines.extend(
        [
            "",
            "## Factor numerator/denominator summary",
            "",
            "| Factor | Numerator | Denominator | Passed/total | Efficiency |",
            "|---|---|---|---:|---:|",
        ]
    )
    for row in payload["factor_summary"]:
        efficiency = "nan" if row["efficiency"] is None else f"{row['efficiency']:.6f}"
        lines.append(
            f"| {row['factor']} | {row['numerator_column']} | {row['denominator_column']} | "
            f"{row['passed']}/{row['total']} | {efficiency} |"
        )

    lines.extend(
        [
            "",
            "## No-trigger-matching diagnostic summary",
            "",
            "| Step | Denominator | Passed/total | Efficiency |",
            "|---|---|---:|---:|",
        ]
    )
    for row in payload["no_trigger_matching_summary"]:
        efficiency = "nan" if row["efficiency"] is None else f"{row['efficiency']:.6f}"
        lines.append(
            f"| {row['step']} | {row['denominator_column']} | "
            f"{row['passed']}/{row['total']} | {efficiency} |"
        )

    uncovered = [item for item in payload["coverage"] if not item["covered"]]
    lines.extend(["", "## Coverage gaps", ""])
    if uncovered:
        for item in uncovered:
            lines.append(f"- `{item['scope']}/{item['step']}/{item['category']}`: no example found")
    else:
        lines.append("- None")

    evidence_by_identity = {
        (
            item["identity"]["source_file"],
            int(item["identity"]["entry"]),
        ): item
        for item in payload["selected_event_evidence"]
    }
    lines.extend(_render_transposed_examples(payload, evidence_by_identity))
    return "\n".join(lines) + "\n"

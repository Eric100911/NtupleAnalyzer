from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import awkward as ak
import numpy as np
import pandas as pd
import uproot
from scipy.stats import beta

from .config import OfflineSelectionConfig
from .truth import first_ancestor_idx, to_int_idx


# ── Per-object efficiency step schema (Efficiency_scheme.md) ──

PER_JPSI_STEPS = ("fiducial", "muonRECO", "muonID", "dimuon")
PER_PHI_STEPS = ("fiducial", "kaonRECO", "kaonID", "dikaon")

EVENT_STEPS = (
    "hlt_event",
    "hlt_muon_matched",
    "four_muon_vtx",
    "Pri_fitValid",
    "Pri_fitPass",
    "Pri_assocPVPass",
    "Pri_trackPVPass",
)

EVENT_STEP_PREVIOUS = {
    "s_cand": "full_gen",
    "hlt_event": "s_cand",
    "hlt_muon_matched": "hlt_event",
    "four_muon_vtx": "hlt_muon_matched",
    "Pri_fitValid": "four_muon_vtx",
    "Pri_fitPass": "four_muon_vtx",
    "Pri_assocPVPass": "four_muon_vtx",
    "Pri_trackPVPass": "four_muon_vtx",
}

EVENT_CONDITIONAL_STEPS = ("full_gen", "s_cand") + EVENT_STEPS

# Derived / convenience flags
DERIVED_FLAGS = ("full_gen", "s_cand")

# Keep old names as aliases during transition; removed once all callers are updated.
EFFICIENCY_STEPS = (
    "full_gen",
    "fiducial_acceptance",
    "hlt_muon_matched",
    "single_jpsi_reco",
    "double_jpsi_reco",
    "single_phi_reco",
    "triple_gen_matched_candidate",
    "jpsi_quality",
    "phi_quality",
    "all6_same_recVtx",
    "Pri_fitValid",
    "Pri_fitPass",
    "Pri_assocPVPass",
    "Pri_trackPVPass",
    "final_nominal",
)

CORRELATED_MAP_STEPS = (
    "hlt_event",
    "hlt_muon_matched",
    "four_muon_vtx",
    "Pri_fitValid",
    "Pri_fitPass",
    "Pri_assocPVPass",
    "Pri_trackPVPass",
)


def per_object_step_columns() -> list[str]:
    """Return the 12 per-object step flag column names."""
    cols: list[str] = []
    for prefix in ("jpsi_lead", "jpsi_sublead"):
        for suffix in PER_JPSI_STEPS:
            cols.append(f"{prefix}_{suffix}")
    for suffix in PER_PHI_STEPS:
        cols.append(f"phi_{suffix}")
    return cols

EFFICIENCY_BRANCHES = sorted(
    {
        "evtNum",
        "runNum",
        "lumiNum",
        "TrigNames",
        "TrigRes",
        "Jpsi_1_mass",
        "Jpsi_1_pt",
        "Jpsi_1_px",
        "Jpsi_1_py",
        "Jpsi_1_pz",
        "Jpsi_1_VtxProb",
        "Jpsi_1_mu_1_Idx",
        "Jpsi_1_mu_2_Idx",
        "Jpsi_2_mass",
        "Jpsi_2_pt",
        "Jpsi_2_px",
        "Jpsi_2_py",
        "Jpsi_2_pz",
        "Jpsi_2_VtxProb",
        "Jpsi_2_mu_1_Idx",
        "Jpsi_2_mu_2_Idx",
        "Phi_mass",
        "Phi_pt",
        "Phi_px",
        "Phi_py",
        "Phi_pz",
        "Phi_VtxProb",
        "Phi_K_1_Idx",
        "Phi_K_2_Idx",
        "Phi_K_1_pt",
        "Phi_K_1_eta",
        "Phi_K_1_vertexId",
        "Phi_K_1_genMatchIdx",
        "Phi_K_2_pt",
        "Phi_K_2_eta",
        "Phi_K_2_vertexId",
        "Phi_K_2_genMatchIdx",
        "muGenMatchIdx",
        "muVertexId",
        "muIsJpsiTrigMatch",
        "muIsJpsiFilterMatch",
        "muPx",
        "muPy",
        "muPz",
        "muCharge",
        "muIsPatSoftMuon",
        "Pri_fitValid",
        "Pri_fitPass",
        "Pri_assocPVPass",
        "Pri_trackPVPass",
        "Pri_passAny",
        "MC_GenPart_pdgId",
        "MC_GenPart_motherGenIdx",
        "MC_GenPart_pt",
        "MC_GenPart_eta",
        "MC_GenPart_phi",
        "MC_GenPart_mass",
    }
)

EFFICIENCY_BRANCHES_V16 = sorted(
    (set(EFFICIENCY_BRANCHES) - {"Phi_K_1_Idx", "Phi_K_2_Idx"})
    | {
        "Jpsi_1_y",
        "Jpsi_2_y",
        "Phi_y",
        "Pri_y",
        "Phi_K_1_RecoKaonTrackIdx",
        "Phi_K_2_RecoKaonTrackIdx",
    }
)

SINGLES_BRANCHES_V16 = sorted(
    {
        "evtNum",
        "runNum",
        "lumiNum",
        "TrigNames",
        "TrigRes",
        "MC_GenPart_pdgId",
        "MC_GenPart_motherGenIdx",
        "MC_GenPart_pt",
        "MC_GenPart_eta",
        "MC_GenPart_phi",
        "MC_GenPart_mass",
        "muGenMatchIdx",
        "muIsPatSoftMuon",
        "nSingleJpsiCand",
        "SingleJpsi_mass",
        "SingleJpsi_pt",
        "SingleJpsi_px",
        "SingleJpsi_py",
        "SingleJpsi_pz",
        "SingleJpsi_y",
        "SingleJpsi_VtxProb",
        "SingleJpsi_fitValid",
        "SingleJpsi_fitPass",
        "SingleJpsi_mu1_Idx",
        "SingleJpsi_mu2_Idx",
        "SingleJpsi_mu1_genMatchIdx",
        "SingleJpsi_mu2_genMatchIdx",
        "SingleJpsi_genMatchIdx",
        "nSinglePhiCand",
        "SinglePhi_mass",
        "SinglePhi_pt",
        "SinglePhi_px",
        "SinglePhi_py",
        "SinglePhi_pz",
        "SinglePhi_y",
        "SinglePhi_VtxProb",
        "SinglePhi_fitValid",
        "SinglePhi_fitPass",
        "SinglePhi_K1_RecoKaonTrackIdx",
        "SinglePhi_K2_RecoKaonTrackIdx",
        "SinglePhi_K1_genMatchIdx",
        "SinglePhi_K2_genMatchIdx",
        "SinglePhi_K1_pt",
        "SinglePhi_K1_eta",
        "SinglePhi_K2_pt",
        "SinglePhi_K2_eta",
        "SinglePhi_genMatchIdx",
        "nRecoKaonTrack",
        "RecoKaonTrack_pt",
        "RecoKaonTrack_eta",
        "RecoKaonTrack_phi",
        "RecoKaonTrack_charge",
        "RecoKaonTrack_genMatchIdx",
        "RecoKaonTrack_passDzPV",
        "RecoKaonTrack_passDxyPV",
        "RecoKaonTrack_passTrackPV",
        "RecoKaonTrack_fromPV",
        "RecoKaonTrack_dzPV",
        "RecoKaonTrack_dxyPV",
        "RecoKaonTrack_usedInSinglePhi",
    }
)

COMPOSITE_BRANCHES = sorted(
    {
        "Jpsi_1_mass",
        "Jpsi_1_pt",
        "Jpsi_1_px",
        "Jpsi_1_py",
        "Jpsi_1_pz",
        "Jpsi_1_VtxProb",
        "Jpsi_1_mu_1_Idx",
        "Jpsi_1_mu_2_Idx",
        "Jpsi_2_mass",
        "Jpsi_2_pt",
        "Jpsi_2_px",
        "Jpsi_2_py",
        "Jpsi_2_pz",
        "Jpsi_2_VtxProb",
        "Jpsi_2_mu_1_Idx",
        "Jpsi_2_mu_2_Idx",
        "Phi_mass",
        "Phi_pt",
        "Phi_px",
        "Phi_py",
        "Phi_pz",
        "Phi_VtxProb",
        "Phi_K_1_pt",
        "Phi_K_1_eta",
        "Phi_K_1_vertexId",
        "Phi_K_1_genMatchIdx",
        "Phi_K_1_RecoKaonTrackIdx",
        "Phi_K_2_pt",
        "Phi_K_2_eta",
        "Phi_K_2_vertexId",
        "Phi_K_2_genMatchIdx",
        "Phi_K_2_RecoKaonTrackIdx",
        "muGenMatchIdx",
        "muVertexId",
        "muIsJpsiTrigMatch",
        "muIsJpsiFilterMatch",
        "muIsPatSoftMuon",
        "Pri_fitValid",
        "Pri_fitPass",
        "Pri_assocPVPass",
        "Pri_trackPVPass",
        "Pri_passAny",
        "TrigNames",
        "TrigRes",
    }
)

SINGLES_BRANCHES = SINGLES_BRANCHES_V16
FULL_V16_BRANCHES = sorted(set(SINGLES_BRANCHES_V16) | set(EFFICIENCY_BRANCHES_V16))
ALL_KNOWN_BRANCHES = sorted(set(EFFICIENCY_BRANCHES) | set(FULL_V16_BRANCHES) | set(COMPOSITE_BRANCHES))


def _uproot_read_options(path: str) -> dict[str, Any]:
    """Use uproot's direct local-file source for filesystem ROOT files."""
    if "://" not in path and Path(path).exists():
        return {"handler": uproot.source.file.MemmapSource}
    return {}


def _detect_ntuple_format(fields: set[str]) -> str:
    has_singles = "SingleJpsi_mass" in fields
    has_composites = "Jpsi_1_mass" in fields
    if has_singles and has_composites:
        return "v1.6-full"
    if has_singles:
        return "v1.6-singles"
    return "v1.0"



@dataclass(frozen=True)
class EfficiencyBinning:
    include_trigger_matching: bool = True
    jpsi_pt_edges: tuple[float, ...] = (6.0, 10.0, 15.0, 20.0, 30.0, 50.0, 100.0)
    phi_pt_edges: tuple[float, ...] = (4.0, 6.0, 10.0, 20.0, 50.0)
    object_abs_y_edges: tuple[float, ...] = (0.0, 0.6, 1.2, 1.8, 2.4)
    object_y_edges: tuple[float, ...] = (-2.4, -1.8, -1.2, -0.6, 0.0, 0.6, 1.2, 1.8, 2.4)
    triple_pt_edges: tuple[float, ...] = (0.0, 10.0, 20.0, 30.0, 50.0, 100.0, 200.0)
    triple_abs_y_edges: tuple[float, ...] = (0.0, 0.6, 1.2, 1.8, 2.4)
    triple_mass_edges: tuple[float, ...] = (0.0, 10.0, 15.0, 20.0, 30.0, 50.0, 100.0)


@dataclass(frozen=True)
class EfficiencyRunConfig:
    analysis_mode: str = "JpsiJpsiPhi"
    tree_path: str = "mkcands/X_data"
    xrootd_host: str = "root://cceos.ihep.ac.cn//"
    sample_root: str = "/eos/ihep/cms/store/user/xcheng/MC_Production_v3/output"
    samples: tuple[str, ...] = ("JJP_DPS1", "JJP_DPS2_CS", "JJP_DPS2_G", "JJP_SPS_CS", "JJP_SPS_G")
    max_files: int | None = None
    min_plot_total: int = 1


@dataclass(frozen=True)
class PairLevelMapSpec:
    step: str
    denominator_col: str
    quantity: str


PAIR_LEVEL_MAP_SPECS = (
    PairLevelMapSpec("four_muon_vtx", "hlt_muon_matched", "four_muon_vertex_efficiency"),
    PairLevelMapSpec("Pri_fitValid", "four_muon_vtx", "pri_fitvalid_efficiency"),
    PairLevelMapSpec("Pri_fitPass", "four_muon_vtx", "pri_fitpass_efficiency"),
    PairLevelMapSpec("Pri_assocPVPass", "four_muon_vtx", "pri_assocpv_efficiency"),
    PairLevelMapSpec("Pri_trackPVPass", "four_muon_vtx", "pri_trackpv_efficiency"),
)

PAIR_LEVEL_MAP_SPEC_BY_STEP = {spec.step: spec for spec in PAIR_LEVEL_MAP_SPECS}

# No-trigger-matching chain: skips hlt_muon_matched, conditions four_muon_vtx on hlt_event
EVENT_STEPS_NO_TRIG_MATCH = (
    "hlt_event",
    "four_muon_vtx_noTrigMatch",
    "Pri_fitValid_noTrigMatch",
    "Pri_fitPass_noTrigMatch",
    "Pri_assocPVPass_noTrigMatch",
    "Pri_trackPVPass_noTrigMatch",
)

EVENT_STEP_PREVIOUS_NO_TRIG_MATCH = {
    "s_cand": "full_gen",
    "hlt_event": "s_cand",
    "four_muon_vtx_noTrigMatch": "hlt_event",
    "Pri_fitValid_noTrigMatch": "four_muon_vtx_noTrigMatch",
    "Pri_fitPass_noTrigMatch": "four_muon_vtx_noTrigMatch",
    "Pri_assocPVPass_noTrigMatch": "four_muon_vtx_noTrigMatch",
    "Pri_trackPVPass_noTrigMatch": "four_muon_vtx_noTrigMatch",
}

EVENT_CONDITIONAL_STEPS_NO_TRIG_MATCH = ("full_gen", "s_cand") + EVENT_STEPS_NO_TRIG_MATCH

CORRELATED_MAP_STEPS_NO_TRIG_MATCH = (
    "hlt_event",
    "four_muon_vtx_noTrigMatch",
    "Pri_fitValid_noTrigMatch",
    "Pri_fitPass_noTrigMatch",
    "Pri_assocPVPass_noTrigMatch",
    "Pri_trackPVPass_noTrigMatch",
)

PAIR_LEVEL_MAP_SPECS_NO_TRIG_MATCH = (
    PairLevelMapSpec("four_muon_vtx_noTrigMatch", "hlt_event", "four_muon_vertex_efficiency"),
    PairLevelMapSpec("Pri_fitValid_noTrigMatch", "four_muon_vtx_noTrigMatch", "pri_fitvalid_efficiency"),
    PairLevelMapSpec("Pri_fitPass_noTrigMatch", "four_muon_vtx_noTrigMatch", "pri_fitpass_efficiency"),
    PairLevelMapSpec("Pri_assocPVPass_noTrigMatch", "four_muon_vtx_noTrigMatch", "pri_assocpv_efficiency"),
    PairLevelMapSpec("Pri_trackPVPass_noTrigMatch", "four_muon_vtx_noTrigMatch", "pri_trackpv_efficiency"),
)

PAIR_LEVEL_MAP_SPEC_BY_STEP_NO_TRIG_MATCH = {spec.step: spec for spec in PAIR_LEVEL_MAP_SPECS_NO_TRIG_MATCH}


@dataclass(frozen=True)
class GenParticle:
    idx: int
    pdg_id: int
    pt: float
    eta: float
    phi: float
    mass: float
    daughter_indices: tuple[int, ...]


@dataclass(frozen=True)
class GenSystem:
    jpsi_lead: GenParticle
    jpsi_sublead: GenParticle
    phi: GenParticle
    n_jpsi: int
    n_phi: int
    triple_pt: float
    triple_abs_y: float
    triple_mass: float


def xrootd_url(host: str, remote_path: str) -> str:
    return f"{host.rstrip('/')}//{remote_path}"


def _limit_efficiency_files(files: list[str], max_files: int | None) -> list[str]:
    if max_files is None:
        return files
    return files[:max_files]


def load_efficiency_file_manifest(
    path: str | Path,
    *,
    samples: tuple[str, ...] | None = None,
    max_files: int | None = None,
) -> dict[str, list[str]]:
    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Input file manifest is not valid JSON: {manifest_path}") from exc

    if isinstance(payload, dict) and isinstance(payload.get("sample"), str) and isinstance(payload.get("files"), list):
        payload = {payload["sample"]: payload["files"]}

    if not isinstance(payload, dict):
        raise ValueError("Input file manifest must be a JSON object mapping sample names to file lists.")

    requested = tuple(samples or ())
    sample_names = requested if requested else tuple(str(sample) for sample in payload)
    files_by_sample: dict[str, list[str]] = {}
    missing_samples: list[str] = []
    for sample in sample_names:
        if not sample:
            raise ValueError("Input file manifest sample names must be non-empty strings.")
        if sample not in payload:
            missing_samples.append(sample)
            continue
        raw_files = payload[sample]
        if not isinstance(raw_files, list):
            raise ValueError(f"Input file manifest entry for sample {sample!r} must be a list of file strings.")
        files: list[str] = []
        for index, item in enumerate(raw_files):
            if not isinstance(item, str) or not item:
                raise ValueError(f"Input file manifest entry {sample}[{index}] must be a non-empty file string.")
            files.append(item)
        if not files:
            raise ValueError(f"Input file manifest entry for sample {sample!r} must contain at least one file.")
        files_by_sample[sample] = _limit_efficiency_files(files, max_files)

    if missing_samples:
        available = ", ".join(str(sample) for sample in payload) or "(none)"
        missing = ", ".join(missing_samples)
        raise ValueError(f"Input file manifest is missing requested sample(s): {missing}. Available samples: {available}")
    return files_by_sample


def xrdfs_ls(host: str, remote_path: str, dirs_only: bool = False) -> list[str]:
    cmd = ["xrdfs", host, "ls"]
    if dirs_only:
        cmd.append("-d")
    cmd.append(remote_path)
    completed = subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def discover_xrootd_sample_files(
    *,
    host: str,
    sample_root: str,
    samples: tuple[str, ...],
    max_files: int | None = None,
) -> dict[str, list[str]]:
    discovered: dict[str, list[str]] = {}
    for sample in samples:
        sample_dir = f"{sample_root.rstrip('/')}/{sample}"
        job_dirs = sorted(xrdfs_ls(host, sample_dir), key=_natural_remote_key)
        files: list[str] = []
        for job_dir in job_dirs:
            entries = xrdfs_ls(host, job_dir)
            ntuples = [entry for entry in entries if entry.endswith("/output_ntuple.root")]
            files.extend(xrootd_url(host, path) for path in ntuples)
            if max_files is not None and len(files) >= max_files:
                files = _limit_efficiency_files(files, max_files)
                break
        discovered[sample] = files
    return discovered


def _natural_remote_key(path: str) -> tuple[Any, ...]:
    name = path.rstrip("/").rsplit("/", 1)[-1]
    if name.isdigit():
        return (0, int(name))
    return (1, name)


def _record_field(arrays: Any, name: str) -> ak.Array:
    if isinstance(arrays, dict):
        return arrays[name]
    return arrays[name]


def _record_fields(arrays: Any) -> list[str]:
    if isinstance(arrays, dict):
        return list(arrays)
    return list(arrays.fields)


def _as_index_array(array: Any) -> ak.Array:
    return ak.values_astype(ak.fill_none(ak.nan_to_none(array), -1), np.int64)


def _safe_take_jagged(values: ak.Array, indices: ak.Array, default: Any = -1) -> ak.Array:
    counts = ak.num(values, axis=1)
    valid = (indices >= 0) & (indices < counts)
    safe = ak.where(valid, indices, 0)
    padded = ak.pad_none(values, 1, axis=1, clip=False)
    taken = padded[safe]
    return ak.fill_none(ak.where(valid, taken, default), default)


def _safe_take_scalar(values: ak.Array, indices: ak.Array, default: Any = -1) -> ak.Array:
    counts = ak.num(values, axis=1)
    valid = (indices >= 0) & (indices < counts)
    safe = ak.where(valid, indices, 0)
    padded = ak.pad_none(values, 1, axis=1, clip=False)
    taken = ak.firsts(padded[safe[:, None]])
    return ak.fill_none(ak.where(valid, taken, default), default)


def _safe_first(array: ak.Array, default: Any = -1) -> ak.Array:
    return ak.fill_none(ak.firsts(array), default)


def _safe_second(array: ak.Array, default: Any = -1) -> ak.Array:
    return ak.fill_none(ak.firsts(array[:, 1:]), default)


def _scalar_rapidity_array(px: ak.Array, py: ak.Array, pz: ak.Array, mass: ak.Array) -> ak.Array:
    energy = np.sqrt(np.maximum(px * px + py * py + pz * pz + mass * mass, 0.0))
    valid = (energy + pz > 0.0) & (energy - pz > 0.0)
    return ak.where(valid, 0.5 * np.log((energy + pz) / (energy - pz)), np.nan)


def _p4_components_array(pt: ak.Array, eta: ak.Array, phi: ak.Array, mass: ak.Array) -> tuple[ak.Array, ak.Array, ak.Array, ak.Array]:
    px = pt * np.cos(phi)
    py = pt * np.sin(phi)
    pz = pt * np.sinh(eta)
    energy = np.sqrt(np.maximum(px * px + py * py + pz * pz + mass * mass, 0.0))
    return px, py, pz, energy


def _rapidity_from_pt_eta_mass(pt: float, eta: float, mass: float) -> float:
    pz = pt * math.sinh(eta)
    energy = math.sqrt(max(pt * pt + pz * pz + mass * mass, 0.0))
    if energy + pz <= 0.0 or energy - pz <= 0.0:
        return math.nan
    return 0.5 * math.log((energy + pz) / (energy - pz))


def _rapidity_from_pt_eta_mass_array(pt: ak.Array, eta: ak.Array, mass: ak.Array) -> ak.Array:
    pz = pt * np.sinh(eta)
    energy = np.sqrt(np.maximum(pt * pt + pz * pz + mass * mass, 0.0))
    valid = (energy + pz > 0.0) & (energy - pz > 0.0)
    return ak.where(valid, 0.5 * np.log((energy + pz) / (energy - pz)), np.nan)


def _ancestor_idx_to_pdg(match_idx: ak.Array, gen_pdg: ak.Array, gen_mother: ak.Array, target_abs_pdg: int, max_depth: int = 16) -> ak.Array:
    idx = _as_index_array(match_idx)
    found = ak.full_like(idx, -1)
    active = idx >= 0
    for _ in range(max_depth):
        pdg_at_idx = _safe_take_jagged(gen_pdg, idx, 0)
        is_target = active & (abs(pdg_at_idx) == target_abs_pdg)
        found = ak.where((found < 0) & is_target, idx, found)
        next_idx = _safe_take_jagged(gen_mother, idx, -1)
        active = active & (found < 0) & (next_idx >= 0)
        idx = ak.where(active, next_idx, idx)
    return found


def _ancestor_idx_to_pdg_from_scalar(match_idx: ak.Array, gen_pdg: ak.Array, gen_mother: ak.Array, target_abs_pdg: int, max_depth: int = 16) -> ak.Array:
    idx = _as_index_array(match_idx)
    found = ak.full_like(idx, -1)
    active = idx >= 0
    for _ in range(max_depth):
        pdg_at_idx = _safe_take_scalar(gen_pdg, idx, 0)
        is_target = active & (abs(pdg_at_idx) == target_abs_pdg)
        found = ak.where((found < 0) & is_target, idx, found)
        next_idx = _safe_take_scalar(gen_mother, idx, -1)
        active = active & (found < 0) & (next_idx >= 0)
        idx = ak.where(active, next_idx, idx)
    return found


def _to_numpy(array: Any, mask: Any | None = None, default: Any = 0) -> np.ndarray:
    selected = array if mask is None else array[mask]
    return ak.to_numpy(ak.fill_none(selected, default))


def _pythonize_event(arrays: Any, entry: int) -> dict[str, Any]:
    return {name: ak.to_list(_record_field(arrays, name)[entry]) for name in _record_fields(arrays)}


def _event_value(event: dict[str, Any], field: str, idx: int, default: Any = None) -> Any:
    values = event.get(field)
    if values is None or idx < 0 or idx >= len(values):
        return default
    return values[idx]


def _p4_from_pt_eta_phi_m(pt: float, eta: float, phi: float, mass: float) -> tuple[float, float, float, float]:
    px = pt * math.cos(phi)
    py = pt * math.sin(phi)
    pz = pt * math.sinh(eta)
    energy = math.sqrt(max(px * px + py * py + pz * pz + mass * mass, 0.0))
    return px, py, pz, energy


def _p4_kinematics(px: float, py: float, pz: float, energy: float) -> tuple[float, float, float]:
    pt = math.hypot(px, py)
    mass2 = energy * energy - px * px - py * py - pz * pz
    mass = math.sqrt(max(mass2, 0.0))
    if energy + pz <= 0.0 or energy - pz <= 0.0:
        rapidity = math.nan
    else:
        rapidity = 0.5 * math.log((energy + pz) / (energy - pz))
    return pt, abs(rapidity), mass


def _daughter_indices(gen_mother_idx: list[int], mother_idx: int, abs_pdgs: set[int], gen_pdg: list[int]) -> tuple[int, ...]:
    return tuple(
        idx
        for idx, mother in enumerate(gen_mother_idx)
        if to_int_idx(mother, -1) == mother_idx and abs(int(gen_pdg[idx])) in abs_pdgs
    )


def find_jpsijpsiphi_gen_system(event: dict[str, Any], cfg: OfflineSelectionConfig) -> GenSystem | None:
    gen_pdg = [int(value) for value in event.get("MC_GenPart_pdgId", [])]
    gen_mother_idx = [to_int_idx(value, -1) for value in event.get("MC_GenPart_motherGenIdx", [])]
    gen_pt = event.get("MC_GenPart_pt", [])
    gen_eta = event.get("MC_GenPart_eta", [])
    gen_phi = event.get("MC_GenPart_phi", [])
    gen_mass = event.get("MC_GenPart_mass", [])

    particles: list[GenParticle] = []
    for idx, pdg_id in enumerate(gen_pdg):
        abs_pdg = abs(int(pdg_id))
        if abs_pdg == 443:
            particle_pt = float(gen_pt[idx])
            if particle_pt <= cfg.jpsi_pt_min:
                continue
            particle_y = _rapidity_from_pt_eta_mass(particle_pt, float(gen_eta[idx]), float(gen_mass[idx]))
            if abs(particle_y) >= cfg.jpsi_abs_y_max:
                continue
            daughters = _daughter_indices(gen_mother_idx, idx, {13}, gen_pdg)
            if len(daughters) >= 2:
                particles.append(
                    GenParticle(idx, pdg_id, particle_pt, float(gen_eta[idx]), float(gen_phi[idx]), float(gen_mass[idx]), daughters[:2])
                )
        elif abs_pdg == 333:
            particle_pt = float(gen_pt[idx])
            if particle_pt <= cfg.phi_pt_min:
                continue
            particle_y = _rapidity_from_pt_eta_mass(particle_pt, float(gen_eta[idx]), float(gen_mass[idx]))
            if abs(particle_y) >= cfg.phi_abs_y_max:
                continue
            daughters = _daughter_indices(gen_mother_idx, idx, {321}, gen_pdg)
            if len(daughters) >= 2:
                particles.append(
                    GenParticle(idx, pdg_id, particle_pt, float(gen_eta[idx]), float(gen_phi[idx]), float(gen_mass[idx]), daughters[:2])
                )

    jpsis = sorted([particle for particle in particles if abs(particle.pdg_id) == 443], key=lambda item: item.pt, reverse=True)
    phis = sorted([particle for particle in particles if abs(particle.pdg_id) == 333], key=lambda item: item.pt, reverse=True)
    if len(jpsis) < 2 or not phis:
        return None

    selected = (jpsis[0], jpsis[1], phis[0])
    px = py = pz = energy = 0.0
    for particle in selected:
        p4 = _p4_from_pt_eta_phi_m(particle.pt, particle.eta, particle.phi, particle.mass)
        px += p4[0]
        py += p4[1]
        pz += p4[2]
        energy += p4[3]
    triple_pt, triple_abs_y, triple_mass = _p4_kinematics(px, py, pz, energy)
    return GenSystem(
        jpsi_lead=jpsis[0],
        jpsi_sublead=jpsis[1],
        phi=phis[0],
        n_jpsi=len(jpsis),
        n_phi=len(phis),
        triple_pt=triple_pt,
        triple_abs_y=triple_abs_y,
        triple_mass=triple_mass,
    )


def _daughter_fiducial(event: dict[str, Any], particle: GenParticle, cfg: OfflineSelectionConfig, kind: Literal["muon", "kaon"]) -> bool:
    pt_min = cfg.track_pt_min if kind == "kaon" else None
    eta_max = cfg.track_abs_eta_max if kind == "kaon" else cfg.mu_abs_eta_max
    for idx in particle.daughter_indices:
        pt = float(_event_value(event, "MC_GenPart_pt", idx, math.nan))
        eta = abs(float(_event_value(event, "MC_GenPart_eta", idx, math.nan)))
        if kind == "muon":
            barrel = eta < 1.2 and pt > cfg.mu_pt_barrel_min
            endcap = 1.2 <= eta < cfg.mu_abs_eta_max and pt > cfg.mu_pt_endcap_min
            if not (barrel or endcap):
                return False
        elif not (pt > float(pt_min) and eta < eta_max):
            return False
    return True


def gen_system_fiducial(event: dict[str, Any], system: GenSystem, cfg: OfflineSelectionConfig) -> bool:
    return (
        _daughter_fiducial(event, system.jpsi_lead, cfg, "muon")
        and _daughter_fiducial(event, system.jpsi_sublead, cfg, "muon")
        and _daughter_fiducial(event, system.phi, cfg, "kaon")
    )


def _muon_gen_ancestor(event: dict[str, Any], muon_idx: int) -> int:
    gen_idx = to_int_idx(_event_value(event, "muGenMatchIdx", muon_idx, -1), -1)
    return first_ancestor_idx(event["MC_GenPart_pdgId"], event["MC_GenPart_motherGenIdx"], gen_idx, 443)


def _kaon_gen_ancestor(event: dict[str, Any], field: str, cand_idx: int) -> int:
    gen_idx = to_int_idx(_event_value(event, field, cand_idx, -1), -1)
    return first_ancestor_idx(event["MC_GenPart_pdgId"], event["MC_GenPart_motherGenIdx"], gen_idx, 333)


def _candidate_leg_indices(event: dict[str, Any], cand_idx: int) -> dict[str, int]:
    mu_indices = {
        "Jpsi_1_mu_1": to_int_idx(_event_value(event, "Jpsi_1_mu_1_Idx", cand_idx, -1), -1),
        "Jpsi_1_mu_2": to_int_idx(_event_value(event, "Jpsi_1_mu_2_Idx", cand_idx, -1), -1),
        "Jpsi_2_mu_1": to_int_idx(_event_value(event, "Jpsi_2_mu_1_Idx", cand_idx, -1), -1),
        "Jpsi_2_mu_2": to_int_idx(_event_value(event, "Jpsi_2_mu_2_Idx", cand_idx, -1), -1),
    }
    jpsi1 = [_muon_gen_ancestor(event, mu_indices["Jpsi_1_mu_1"]), _muon_gen_ancestor(event, mu_indices["Jpsi_1_mu_2"])]
    jpsi2 = [_muon_gen_ancestor(event, mu_indices["Jpsi_2_mu_1"]), _muon_gen_ancestor(event, mu_indices["Jpsi_2_mu_2"])]
    phi = [
        _kaon_gen_ancestor(event, "Phi_K_1_genMatchIdx", cand_idx),
        _kaon_gen_ancestor(event, "Phi_K_2_genMatchIdx", cand_idx),
    ]
    return {
        "jpsi1": jpsi1[0] if jpsi1[0] >= 0 and jpsi1[0] == jpsi1[1] else -1,
        "jpsi2": jpsi2[0] if jpsi2[0] >= 0 and jpsi2[0] == jpsi2[1] else -1,
        "phi": phi[0] if phi[0] >= 0 and phi[0] == phi[1] else -1,
    }


def _candidate_matches_system(event: dict[str, Any], cand_idx: int, system: GenSystem) -> bool:
    legs = _candidate_leg_indices(event, cand_idx)
    jpsi_set = {legs["jpsi1"], legs["jpsi2"]}
    return (
        legs["phi"] == system.phi.idx
        and jpsi_set == {system.jpsi_lead.idx, system.jpsi_sublead.idx}
    )


def _candidate_hlt_muon_matched(event: dict[str, Any], cand_idx: int) -> bool:
    j1_mu1 = to_int_idx(_event_value(event, "Jpsi_1_mu_1_Idx", cand_idx, -1), -1)
    j1_mu2 = to_int_idx(_event_value(event, "Jpsi_1_mu_2_Idx", cand_idx, -1), -1)
    j2_mu1 = to_int_idx(_event_value(event, "Jpsi_2_mu_1_Idx", cand_idx, -1), -1)
    j2_mu2 = to_int_idx(_event_value(event, "Jpsi_2_mu_2_Idx", cand_idx, -1), -1)
    f_matches = [
        bool(to_int_idx(_event_value(event, "muIsJpsiFilterMatch", idx, 0), 0))
        for idx in (j1_mu1, j1_mu2, j2_mu1, j2_mu2)
    ]
    t_matches = [
        bool(to_int_idx(_event_value(event, "muIsJpsiTrigMatch", idx, 0), 0))
        for idx in (j1_mu1, j1_mu2, j2_mu1, j2_mu2)
    ]
    n_filter = sum(f_matches)
    n_trig = sum(t_matches)
    j1_pair_filter = f_matches[0] and f_matches[1]
    j2_pair_filter = f_matches[2] and f_matches[3]
    j1_pair_trig = t_matches[0] and t_matches[1]
    j2_pair_trig = t_matches[2] and t_matches[3]

    # DoubleMu4_3_LowMass_v (2 muons): either J/psi dimuon pair matched
    if j1_pair_filter or j2_pair_filter or j1_pair_trig or j2_pair_trig:
        return True
    # Dimuon0_Jpsi3p5_Muon2_v (3 muons): one J/psi pair + >=3 matched total
    if (j1_pair_filter and n_filter >= 3) or (j2_pair_filter and n_filter >= 3):
        return True
    if (j1_pair_trig and n_trig >= 3) or (j2_pair_trig and n_trig >= 3):
        return True
    return False


def _candidate_all6_same_rec_vtx(event: dict[str, Any], cand_idx: int) -> bool:
    muon_indices = [
        to_int_idx(_event_value(event, "Jpsi_1_mu_1_Idx", cand_idx, -1), -1),
        to_int_idx(_event_value(event, "Jpsi_1_mu_2_Idx", cand_idx, -1), -1),
        to_int_idx(_event_value(event, "Jpsi_2_mu_1_Idx", cand_idx, -1), -1),
        to_int_idx(_event_value(event, "Jpsi_2_mu_2_Idx", cand_idx, -1), -1),
    ]
    vertex_ids = [to_int_idx(_event_value(event, "muVertexId", idx, -1), -1) for idx in muon_indices]
    vertex_ids.extend(
        [
            to_int_idx(_event_value(event, "Phi_K_1_vertexId", cand_idx, -1), -1),
            to_int_idx(_event_value(event, "Phi_K_2_vertexId", cand_idx, -1), -1),
        ]
    )
    return min(vertex_ids) >= 0 and len(set(vertex_ids)) == 1


def _scalar_rapidity(px: float, py: float, pz: float, mass: float) -> float:
    energy = math.sqrt(max(px * px + py * py + pz * pz + mass * mass, 0.0))
    if energy + pz <= 0.0 or energy - pz <= 0.0:
        return math.nan
    return 0.5 * math.log((energy + pz) / (energy - pz))


def _jpsi_quality(event: dict[str, Any], cand_idx: int, cfg: OfflineSelectionConfig) -> bool:
    for prefix in ("Jpsi_1", "Jpsi_2"):
        px = float(_event_value(event, f"{prefix}_px", cand_idx, math.nan))
        py = float(_event_value(event, f"{prefix}_py", cand_idx, math.nan))
        pz = float(_event_value(event, f"{prefix}_pz", cand_idx, math.nan))
        mass = float(_event_value(event, f"{prefix}_mass", cand_idx, math.nan))
        y = _scalar_rapidity(px, py, pz, mass)
        if not (
            cfg.jpsi_mass_window[0] <= mass <= cfg.jpsi_mass_window[1]
            and float(_event_value(event, f"{prefix}_pt", cand_idx, -1.0)) > cfg.jpsi_pt_min
            and abs(y) < cfg.jpsi_abs_y_max
            and float(_event_value(event, f"{prefix}_VtxProb", cand_idx, -1.0)) > cfg.jpsi_vtxprob_min
        ):
            return False
    return True


def _phi_quality(event: dict[str, Any], cand_idx: int, cfg: OfflineSelectionConfig) -> bool:
    return bool(
        cfg.phi_mass_window[0] <= float(_event_value(event, "Phi_mass", cand_idx, math.nan)) <= cfg.phi_mass_window[1]
        and float(_event_value(event, "Phi_pt", cand_idx, -1.0)) > cfg.phi_pt_min
        and float(_event_value(event, "Phi_VtxProb", cand_idx, -1.0)) > cfg.phi_vtxprob_min
        and float(_event_value(event, "Phi_K_1_pt", cand_idx, -1.0)) > cfg.track_pt_min
        and float(_event_value(event, "Phi_K_2_pt", cand_idx, -1.0)) > cfg.track_pt_min
        and abs(float(_event_value(event, "Phi_K_1_eta", cand_idx, math.nan))) < cfg.track_abs_eta_max
        and abs(float(_event_value(event, "Phi_K_2_eta", cand_idx, math.nan))) < cfg.track_abs_eta_max
    )


def _phi_kaonID(event: dict[str, Any], cand_idx: int, cfg: OfflineSelectionConfig) -> bool:
    """Kaon track-level cuts only (no phi mass/pt/vtxProb)."""
    return bool(
        float(_event_value(event, "Phi_K_1_pt", cand_idx, -1.0)) > cfg.track_pt_min
        and float(_event_value(event, "Phi_K_2_pt", cand_idx, -1.0)) > cfg.track_pt_min
        and abs(float(_event_value(event, "Phi_K_1_eta", cand_idx, math.nan))) < cfg.track_abs_eta_max
        and abs(float(_event_value(event, "Phi_K_2_eta", cand_idx, math.nan))) < cfg.track_abs_eta_max
    )


def _candidate_four_muon_vtx(event: dict[str, Any], cand_idx: int) -> bool:
    """All 4 muons share the same vertex ID (>=0)."""
    v1 = to_int_idx(_event_value(event, "muVertexId", to_int_idx(_event_value(event, "Jpsi_1_mu_1_Idx", cand_idx, -1), -1), -1), -1)
    v2 = to_int_idx(_event_value(event, "muVertexId", to_int_idx(_event_value(event, "Jpsi_1_mu_2_Idx", cand_idx, -1), -1), -1), -1)
    v3 = to_int_idx(_event_value(event, "muVertexId", to_int_idx(_event_value(event, "Jpsi_2_mu_1_Idx", cand_idx, -1), -1), -1), -1)
    v4 = to_int_idx(_event_value(event, "muVertexId", to_int_idx(_event_value(event, "Jpsi_2_mu_2_Idx", cand_idx, -1), -1), -1), -1)
    return v1 >= 0 and v1 == v2 == v3 == v4


def _candidate_muonID_jpsi(event: dict[str, Any], cand_idx: int, prefix: str) -> bool:
    """Both muons of J/psi candidate pass soft-muon ID."""
    mu1_idx = to_int_idx(_event_value(event, f"{prefix}_mu_1_Idx", cand_idx, -1), -1)
    mu2_idx = to_int_idx(_event_value(event, f"{prefix}_mu_2_Idx", cand_idx, -1), -1)
    if mu1_idx < 0 or mu2_idx < 0:
        return False
    id1 = to_int_idx(_event_value(event, "muIsPatSoftMuon", mu1_idx, 0), 0)
    id2 = to_int_idx(_event_value(event, "muIsPatSoftMuon", mu2_idx, 0), 0)
    return bool(id1 != 0 and id2 != 0)


def _jpsi_quality_single(event: dict[str, Any], cand_idx: int, prefix: str, cfg: OfflineSelectionConfig) -> bool:
    """Quality cuts for a single J/psi candidate."""
    mass = float(_event_value(event, f"{prefix}_mass", cand_idx, math.nan))
    pt = float(_event_value(event, f"{prefix}_pt", cand_idx, -1.0))
    vtxprob = float(_event_value(event, f"{prefix}_VtxProb", cand_idx, -1.0))
    px = float(_event_value(event, f"{prefix}_px", cand_idx, 0.0))
    py = float(_event_value(event, f"{prefix}_py", cand_idx, 0.0))
    pz = float(_event_value(event, f"{prefix}_pz", cand_idx, 0.0))
    y = _scalar_rapidity(px, py, pz, mass)
    return bool(
        cfg.jpsi_mass_window[0] <= mass <= cfg.jpsi_mass_window[1]
        and pt > cfg.jpsi_pt_min
        and abs(y) < cfg.jpsi_abs_y_max
        and vtxprob > cfg.jpsi_vtxprob_min
    )


def _event_path_or(event: dict[str, Any], patterns: tuple[str, ...] = ("HLT_Dimuon0_Jpsi3p5_Muon2_v", "HLT_DoubleMu4_3_LowMass_v")) -> bool:
    names = event.get("TrigNames", [])
    results = event.get("TrigRes", [])
    for name, result in zip(names, results):
        if any(pattern in str(name) for pattern in patterns) and bool(result):
            return True
    return False


def build_event_efficiency_row(
    event: dict[str, Any],
    source_file: str,
    sample: str,
    entry: int,
    cfg: OfflineSelectionConfig,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    system = find_jpsijpsiphi_gen_system(event, cfg)
    if system is None:
        return None, None

    n_candidates = len(event.get("Jpsi_1_mass", []))

    # ── Gen-level fiducial flags ──
    fiducial_jpsi_lead = _daughter_fiducial(event, system.jpsi_lead, cfg, "muon")
    fiducial_jpsi_sublead = _daughter_fiducial(event, system.jpsi_sublead, cfg, "muon")
    fiducial_phi = _daughter_fiducial(event, system.phi, cfg, "kaon")

    # ── Per-object matching: check ALL candidates ──
    matched_candidates: list[int] = []
    lead_muonRECO = False
    sublead_muonRECO = False
    lead_muonID = False
    sublead_muonID = False
    lead_dimuon = False
    sublead_dimuon = False
    phi_kaonRECO_flag = False
    phi_kaonID_flag = False
    phi_dikaon_flag = False

    for cand_idx in range(n_candidates):
        legs = _candidate_leg_indices(event, cand_idx)

        # Per-J/psi muonRECO (any candidate with matching leg)
        if legs["jpsi1"] == system.jpsi_lead.idx or legs["jpsi2"] == system.jpsi_lead.idx:
            if not lead_muonRECO:
                lead_muonRECO = True
            if not lead_muonID:
                lead_muonID = (
                    (legs["jpsi1"] == system.jpsi_lead.idx and _candidate_muonID_jpsi(event, cand_idx, "Jpsi_1"))
                    or (legs["jpsi2"] == system.jpsi_lead.idx and _candidate_muonID_jpsi(event, cand_idx, "Jpsi_2"))
                )
            if not lead_dimuon:
                lead_dimuon = (
                    (legs["jpsi1"] == system.jpsi_lead.idx
                     and _candidate_muonID_jpsi(event, cand_idx, "Jpsi_1")
                     and _jpsi_quality_single(event, cand_idx, "Jpsi_1", cfg))
                    or (legs["jpsi2"] == system.jpsi_lead.idx
                        and _candidate_muonID_jpsi(event, cand_idx, "Jpsi_2")
                        and _jpsi_quality_single(event, cand_idx, "Jpsi_2", cfg))
                )
        if legs["jpsi1"] == system.jpsi_sublead.idx or legs["jpsi2"] == system.jpsi_sublead.idx:
            if not sublead_muonRECO:
                sublead_muonRECO = True
            if not sublead_muonID:
                sublead_muonID = (
                    (legs["jpsi1"] == system.jpsi_sublead.idx and _candidate_muonID_jpsi(event, cand_idx, "Jpsi_1"))
                    or (legs["jpsi2"] == system.jpsi_sublead.idx and _candidate_muonID_jpsi(event, cand_idx, "Jpsi_2"))
                )
            if not sublead_dimuon:
                sublead_dimuon = (
                    (legs["jpsi1"] == system.jpsi_sublead.idx
                     and _candidate_muonID_jpsi(event, cand_idx, "Jpsi_1")
                     and _jpsi_quality_single(event, cand_idx, "Jpsi_1", cfg))
                    or (legs["jpsi2"] == system.jpsi_sublead.idx
                        and _candidate_muonID_jpsi(event, cand_idx, "Jpsi_2")
                        and _jpsi_quality_single(event, cand_idx, "Jpsi_2", cfg))
                )
        # Per-phi (any candidate with matching phi leg)
        if legs["phi"] == system.phi.idx:
            if not phi_kaonRECO_flag:
                phi_kaonRECO_flag = True
            if not phi_kaonID_flag:
                phi_kaonID_flag = _phi_kaonID(event, cand_idx, cfg)
            if not phi_dikaon_flag:
                phi_dikaon_flag = _phi_quality(event, cand_idx, cfg)

    # ── Event-level: only for gen-matched candidates ──
    hlt_raw = False
    four_muon_raw = False
    pri_valid_raw = False
    pri_pass_raw = False
    pri_assoc_raw = False
    pri_track_raw = False

    for cand_idx in range(n_candidates):
        if not _candidate_matches_system(event, cand_idx, system):
            continue
        matched_candidates.append(cand_idx)

        if not hlt_raw:
            hlt_raw = _candidate_hlt_muon_matched(event, cand_idx)
        if not four_muon_raw:
            four_muon_raw = _candidate_four_muon_vtx(event, cand_idx)
        if not pri_valid_raw:
            pri_valid_raw = to_int_idx(_event_value(event, "Pri_fitValid", cand_idx, 0), 0) == 1
        if not pri_pass_raw:
            pri_pass_raw = to_int_idx(_event_value(event, "Pri_fitPass", cand_idx, 0), 0) == 1
        if not pri_assoc_raw:
            pri_assoc_raw = to_int_idx(_event_value(event, "Pri_assocPVPass", cand_idx, 0), 0) == 1
        if not pri_track_raw:
            pri_track_raw = to_int_idx(_event_value(event, "Pri_trackPVPass", cand_idx, 0), 0) == 1

    s_cand = (
        fiducial_jpsi_lead and lead_muonRECO and lead_muonID and lead_dimuon
        and fiducial_jpsi_sublead and sublead_muonRECO and sublead_muonID and sublead_dimuon
        and fiducial_phi and phi_kaonRECO_flag and phi_kaonID_flag and phi_dikaon_flag
    )
    # hlt_event = trigger OR (event-level TrigNames/TrigRes)
    # hlt_muon_matched = trigger-object matching (per-muon muIsJpsi*Match flags)
    trigger_or = _event_path_or(event)
    # Chain B: with trigger matching (default column names)
    hlt_event = s_cand and trigger_or
    hlt_muon_matched = hlt_event and hlt_raw
    four_muon_vtx = hlt_muon_matched and four_muon_raw
    Pri_fitValid = four_muon_vtx and pri_valid_raw
    Pri_fitPass = four_muon_vtx and pri_pass_raw
    Pri_assocPVPass = four_muon_vtx and pri_assoc_raw
    Pri_trackPVPass = four_muon_vtx and pri_track_raw
    # Chain A: without trigger matching
    four_muon_vtx_noTrigMatch = hlt_event and four_muon_raw
    Pri_fitValid_noTrigMatch = four_muon_vtx_noTrigMatch and pri_valid_raw
    Pri_fitPass_noTrigMatch = four_muon_vtx_noTrigMatch and pri_pass_raw
    Pri_assocPVPass_noTrigMatch = four_muon_vtx_noTrigMatch and pri_assoc_raw
    Pri_trackPVPass_noTrigMatch = four_muon_vtx_noTrigMatch and pri_track_raw

    gen_score = system.jpsi_lead.pt ** 2 + system.jpsi_sublead.pt ** 2 + system.phi.pt ** 2

    event_row: dict[str, Any] = {
        "sample": sample,
        "source_file": source_file,
        "entry": int(entry),
        "run": int(event["runNum"]),
        "lumi": int(event["lumiNum"]),
        "event": int(event["evtNum"]),
        "n_candidates": int(n_candidates),
        "n_gen_jpsi": int(system.n_jpsi),
        "n_gen_phi": int(system.n_phi),
        "n_triple_gen_matched_candidates": int(len(matched_candidates)),
        "hlt_event_path_or": int(trigger_or),
        # Per-object step flags
        "jpsi_lead_fiducial": int(fiducial_jpsi_lead),
        "jpsi_lead_muonRECO": int(lead_muonRECO),
        "jpsi_lead_muonID": int(lead_muonID),
        "jpsi_lead_dimuon": int(lead_dimuon),
        "jpsi_sublead_fiducial": int(fiducial_jpsi_sublead),
        "jpsi_sublead_muonRECO": int(sublead_muonRECO),
        "jpsi_sublead_muonID": int(sublead_muonID),
        "jpsi_sublead_dimuon": int(sublead_dimuon),
        "phi_fiducial": int(fiducial_phi),
        "phi_kaonRECO": int(phi_kaonRECO_flag),
        "phi_kaonID": int(phi_kaonID_flag),
        "phi_dikaon": int(phi_dikaon_flag),
        # Event-level flags
        "full_gen": 1,
        "s_cand": int(s_cand),
        "hlt_event": int(hlt_event),
        "hlt_muon_matched": int(hlt_muon_matched),
        "four_muon_vtx": int(four_muon_vtx),
        "four_muon_vtx_noTrigMatch": int(four_muon_vtx_noTrigMatch),
        "Pri_fitValid": int(Pri_fitValid),
        "Pri_fitValid_noTrigMatch": int(Pri_fitValid_noTrigMatch),
        "Pri_fitPass": int(Pri_fitPass),
        "Pri_fitPass_noTrigMatch": int(Pri_fitPass_noTrigMatch),
        "Pri_assocPVPass": int(Pri_assocPVPass),
        "Pri_assocPVPass_noTrigMatch": int(Pri_assocPVPass_noTrigMatch),
        "Pri_trackPVPass": int(Pri_trackPVPass),
        "Pri_trackPVPass_noTrigMatch": int(Pri_trackPVPass_noTrigMatch),
    }
    jpsi_lead_y = _rapidity_from_pt_eta_mass(system.jpsi_lead.pt, system.jpsi_lead.eta, system.jpsi_lead.mass)
    jpsi_sublead_y = _rapidity_from_pt_eta_mass(system.jpsi_sublead.pt, system.jpsi_sublead.eta, system.jpsi_sublead.mass)
    phi_y = _rapidity_from_pt_eta_mass(system.phi.pt, system.phi.eta, system.phi.mass)
    gen_row = {
        "sample": sample,
        "source_file": source_file,
        "entry": int(entry),
        "run": int(event["runNum"]),
        "lumi": int(event["lumiNum"]),
        "event": int(event["evtNum"]),
        "jpsi_lead_gen_idx": system.jpsi_lead.idx,
        "jpsi_sublead_gen_idx": system.jpsi_sublead.idx,
        "phi_gen_idx": system.phi.idx,
        "jpsi_lead_pt": system.jpsi_lead.pt,
        "jpsi_lead_y": jpsi_lead_y,
        "jpsi_lead_abs_y": abs(jpsi_lead_y),
        "jpsi_sublead_pt": system.jpsi_sublead.pt,
        "jpsi_sublead_y": jpsi_sublead_y,
        "jpsi_sublead_abs_y": abs(jpsi_sublead_y),
        "phi_pt": system.phi.pt,
        "phi_y": phi_y,
        "phi_abs_y": abs(phi_y),
        "triple_pt": system.triple_pt,
        "triple_abs_y": system.triple_abs_y,
        "triple_mass": system.triple_mass,
        "gen_score": gen_score,
    }
    return gen_row, event_row


def process_efficiency_file(path: str, sample: str, cfg: OfflineSelectionConfig, tree_path: str = "mkcands/X_data") -> dict[str, pd.DataFrame]:
    with uproot.open(path, **_uproot_read_options(path)) as root_file:
        tree = root_file[tree_path]
        available = set(tree.keys())
        branches = [branch for branch in ALL_KNOWN_BRANCHES if branch in available]
        arrays = tree.arrays(branches, library="ak")

    if _detect_ntuple_format(set(arrays.fields)) != "v1.0":
        return _process_efficiency_chunk_vectorized(arrays, path, sample, cfg, 0)

    gen_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    n_entries = len(_record_field(arrays, "evtNum"))
    for entry in range(n_entries):
        event = _pythonize_event(arrays, entry)
        gen_row, event_row = build_event_efficiency_row(event, path, sample, entry, cfg)
        if gen_row is not None and event_row is not None:
            gen_rows.append(gen_row)
            event_rows.append(event_row)
    return {
        "gen_systems": pd.DataFrame(gen_rows),
        "event_step_flags": pd.DataFrame(event_rows),
    }


def _event_trigger_path_or_array(arrays: ak.Array, like: ak.Array) -> ak.Array:
    if "TrigNames" not in arrays.fields or "TrigRes" not in arrays.fields:
        return ak.zeros_like(like, dtype=np.int8)
    hlt_name_match = ak.str.find_substring(arrays["TrigNames"], "HLT_Dimuon0_Jpsi3p5_Muon2_v") >= 0
    hlt_name_match = hlt_name_match | (ak.str.find_substring(arrays["TrigNames"], "HLT_DoubleMu4_3_LowMass_v") >= 0)
    return ak.values_astype(ak.any(hlt_name_match & (arrays["TrigRes"] != 0), axis=1), np.int8)


def _compute_per_object_flags_v16(
    arrays: ak.Array,
    pdg: ak.Array,
    mother: ak.Array,
    jpsi1_idx: ak.Array,
    jpsi2_idx: ak.Array,
    phi_idx: ak.Array,
    cfg: OfflineSelectionConfig,
    fiducial_jpsi_lead: ak.Array,
    fiducial_jpsi_sublead: ak.Array,
    fiducial_phi: ak.Array,
) -> dict[str, ak.Array]:
    zero = ak.values_astype(ak.zeros_like(jpsi1_idx), bool)
    result: dict[str, ak.Array] = {
        "jpsi_lead_fiducial": fiducial_jpsi_lead,
        "jpsi_lead_muonRECO": zero,
        "jpsi_lead_muonID": zero,
        "jpsi_lead_dimuon": zero,
        "jpsi_sublead_fiducial": fiducial_jpsi_sublead,
        "jpsi_sublead_muonRECO": zero,
        "jpsi_sublead_muonID": zero,
        "jpsi_sublead_dimuon": zero,
        "phi_fiducial": fiducial_phi,
        "phi_kaonRECO": zero,
        "phi_kaonID": zero,
        "phi_dikaon": zero,
    }

    if {"SingleJpsi_mass", "SingleJpsi_mu1_Idx", "SingleJpsi_mu2_Idx"}.issubset(arrays.fields):
        sj_mu1_idx = _as_index_array(arrays["SingleJpsi_mu1_Idx"])
        sj_mu2_idx = _as_index_array(arrays["SingleJpsi_mu2_Idx"])
        if {"SingleJpsi_mu1_genMatchIdx", "SingleJpsi_mu2_genMatchIdx"}.issubset(arrays.fields):
            sj_mu1_gen = arrays["SingleJpsi_mu1_genMatchIdx"]
            sj_mu2_gen = arrays["SingleJpsi_mu2_genMatchIdx"]
        else:
            sj_mu1_gen = _safe_take_jagged(arrays["muGenMatchIdx"], sj_mu1_idx, -1)
            sj_mu2_gen = _safe_take_jagged(arrays["muGenMatchIdx"], sj_mu2_idx, -1)
        sj_a1 = _ancestor_idx_to_pdg(sj_mu1_gen, pdg, mother, 443)
        sj_a2 = _ancestor_idx_to_pdg(sj_mu2_gen, pdg, mother, 443)
        sj_leg = ak.where((sj_a1 >= 0) & (sj_a1 == sj_a2), sj_a1, -1)

        mu_id = ak.values_astype(arrays["muIsPatSoftMuon"], bool)
        sj_mu1_id = _safe_take_jagged(mu_id, sj_mu1_idx, False)
        sj_mu2_id = _safe_take_jagged(mu_id, sj_mu2_idx, False)
        sj_both_id = sj_mu1_id & sj_mu2_id

        if "SingleJpsi_y" in arrays.fields:
            sj_y = abs(arrays["SingleJpsi_y"])
        else:
            sj_y = abs(_scalar_rapidity_array(arrays["SingleJpsi_px"], arrays["SingleJpsi_py"], arrays["SingleJpsi_pz"], arrays["SingleJpsi_mass"]))
        sj_quality = (
            (arrays["SingleJpsi_mass"] >= cfg.jpsi_mass_window[0])
            & (arrays["SingleJpsi_mass"] <= cfg.jpsi_mass_window[1])
            & (arrays["SingleJpsi_pt"] > cfg.jpsi_pt_min)
            & (sj_y < cfg.jpsi_abs_y_max)
            & (arrays["SingleJpsi_VtxProb"] > cfg.jpsi_vtxprob_min)
            & (_as_index_array(arrays["SingleJpsi_fitValid"]) != 0)
            & (_as_index_array(arrays["SingleJpsi_fitPass"]) != 0)
        )

        result["jpsi_lead_muonRECO"] = ak.any(sj_leg == jpsi1_idx, axis=1)
        result["jpsi_lead_muonID"] = ak.any((sj_leg == jpsi1_idx) & sj_both_id, axis=1)
        result["jpsi_lead_dimuon"] = ak.any((sj_leg == jpsi1_idx) & sj_both_id & sj_quality, axis=1)
        result["jpsi_sublead_muonRECO"] = ak.any(sj_leg == jpsi2_idx, axis=1)
        result["jpsi_sublead_muonID"] = ak.any((sj_leg == jpsi2_idx) & sj_both_id, axis=1)
        result["jpsi_sublead_dimuon"] = ak.any((sj_leg == jpsi2_idx) & sj_both_id & sj_quality, axis=1)

    if {"SinglePhi_mass", "SinglePhi_K1_RecoKaonTrackIdx", "SinglePhi_K2_RecoKaonTrackIdx"}.issubset(arrays.fields):
        sp_k1_idx = _as_index_array(arrays["SinglePhi_K1_RecoKaonTrackIdx"])
        sp_k2_idx = _as_index_array(arrays["SinglePhi_K2_RecoKaonTrackIdx"])
        if {"SinglePhi_K1_genMatchIdx", "SinglePhi_K2_genMatchIdx"}.issubset(arrays.fields):
            sp_k1_gen = arrays["SinglePhi_K1_genMatchIdx"]
            sp_k2_gen = arrays["SinglePhi_K2_genMatchIdx"]
        else:
            sp_k1_gen = _safe_take_jagged(arrays["RecoKaonTrack_genMatchIdx"], sp_k1_idx, -1)
            sp_k2_gen = _safe_take_jagged(arrays["RecoKaonTrack_genMatchIdx"], sp_k2_idx, -1)
        sp_a1 = _ancestor_idx_to_pdg(sp_k1_gen, pdg, mother, 333)
        sp_a2 = _ancestor_idx_to_pdg(sp_k2_gen, pdg, mother, 333)
        sp_leg = ak.where((sp_a1 >= 0) & (sp_a1 == sp_a2), sp_a1, -1)

        k1_pt = _safe_take_jagged(arrays["RecoKaonTrack_pt"], sp_k1_idx, -1.0)
        k2_pt = _safe_take_jagged(arrays["RecoKaonTrack_pt"], sp_k2_idx, -1.0)
        k1_eta = _safe_take_jagged(arrays["RecoKaonTrack_eta"], sp_k1_idx, np.nan)
        k2_eta = _safe_take_jagged(arrays["RecoKaonTrack_eta"], sp_k2_idx, np.nan)
        sp_track_pass = (
            (k1_pt > cfg.track_pt_min)
            & (k2_pt > cfg.track_pt_min)
            & (abs(k1_eta) < cfg.track_abs_eta_max)
            & (abs(k2_eta) < cfg.track_abs_eta_max)
        )
        sp_quality = (
            (arrays["SinglePhi_mass"] >= cfg.phi_mass_window[0])
            & (arrays["SinglePhi_mass"] <= cfg.phi_mass_window[1])
            & (arrays["SinglePhi_pt"] > cfg.phi_pt_min)
            & (arrays["SinglePhi_VtxProb"] > cfg.phi_vtxprob_min)
            & (_as_index_array(arrays["SinglePhi_fitValid"]) != 0)
            & (_as_index_array(arrays["SinglePhi_fitPass"]) != 0)
        )
        result["phi_kaonRECO"] = ak.any(sp_leg == phi_idx, axis=1)
        result["phi_kaonID"] = ak.any((sp_leg == phi_idx) & sp_track_pass, axis=1)
        result["phi_dikaon"] = ak.any((sp_leg == phi_idx) & sp_track_pass & sp_quality, axis=1)

    return result


def _process_efficiency_chunk_vectorized(
    arrays: ak.Array,
    source_file: str,
    sample: str,
    cfg: OfflineSelectionConfig,
    entry_start: int,
) -> dict[str, pd.DataFrame]:
    n_events = len(_record_field(arrays, "evtNum"))
    if n_events == 0:
        return {"gen_systems": pd.DataFrame(), "event_step_flags": pd.DataFrame()}
    ntuple_format = _detect_ntuple_format(set(arrays.fields))

    pdg = arrays["MC_GenPart_pdgId"]
    mother = _as_index_array(arrays["MC_GenPart_motherGenIdx"])
    gen_idx = ak.local_index(pdg)
    gen_pt = arrays["MC_GenPart_pt"]
    gen_eta = arrays["MC_GenPart_eta"]
    gen_phi = arrays["MC_GenPart_phi"]
    gen_mass = arrays["MC_GenPart_mass"]

    is_mu = abs(pdg) == 13
    is_kaon = abs(pdg) == 321
    mu_mother = mother[is_mu]
    kaon_mother = mother[is_kaon]
    n_mu_daughters = ak.sum(mu_mother[:, :, None] == gen_idx[:, None, :], axis=1)
    n_kaon_daughters = ak.sum(kaon_mother[:, :, None] == gen_idx[:, None, :], axis=1)

    gen_y = _rapidity_from_pt_eta_mass_array(gen_pt, gen_eta, gen_mass)
    valid_jpsi = (
        (abs(pdg) == 443) & (n_mu_daughters >= 2)
        & (gen_pt > cfg.jpsi_pt_min) & (abs(gen_y) < cfg.jpsi_abs_y_max)
    )
    valid_phi = (
        (abs(pdg) == 333) & (n_kaon_daughters >= 2)
        & (gen_pt > cfg.phi_pt_min) & (abs(gen_y) < cfg.phi_abs_y_max)
    )

    jpsi_order = ak.argsort(gen_pt[valid_jpsi], ascending=False)
    jpsi_idx_sorted = gen_idx[valid_jpsi][jpsi_order]
    jpsi_pt_sorted = gen_pt[valid_jpsi][jpsi_order]
    jpsi_eta_sorted = gen_eta[valid_jpsi][jpsi_order]
    jpsi_phi_sorted = gen_phi[valid_jpsi][jpsi_order]
    jpsi_mass_sorted = gen_mass[valid_jpsi][jpsi_order]

    phi_order = ak.argsort(gen_pt[valid_phi], ascending=False)
    phi_idx_sorted = gen_idx[valid_phi][phi_order]
    phi_pt_sorted = gen_pt[valid_phi][phi_order]
    phi_eta_sorted = gen_eta[valid_phi][phi_order]
    phi_phi_sorted = gen_phi[valid_phi][phi_order]
    phi_mass_sorted = gen_mass[valid_phi][phi_order]

    jpsi1_idx = _safe_first(jpsi_idx_sorted, -1)
    jpsi2_idx = _safe_second(jpsi_idx_sorted, -1)
    phi_idx = _safe_first(phi_idx_sorted, -1)
    has_full_gen = (ak.num(jpsi_idx_sorted) >= 2) & (ak.num(phi_idx_sorted) >= 1)

    jpsi1_pt = _safe_first(jpsi_pt_sorted, np.nan)
    jpsi2_pt = _safe_second(jpsi_pt_sorted, np.nan)
    phi_pt = _safe_first(phi_pt_sorted, np.nan)
    jpsi1_eta = _safe_first(jpsi_eta_sorted, np.nan)
    jpsi2_eta = _safe_second(jpsi_eta_sorted, np.nan)
    phi_eta = _safe_first(phi_eta_sorted, np.nan)
    jpsi1_phi = _safe_first(jpsi_phi_sorted, np.nan)
    jpsi2_phi = _safe_second(jpsi_phi_sorted, np.nan)
    phi_phi = _safe_first(phi_phi_sorted, np.nan)
    jpsi1_mass = _safe_first(jpsi_mass_sorted, np.nan)
    jpsi2_mass = _safe_second(jpsi_mass_sorted, np.nan)
    phi_mass = _safe_first(phi_mass_sorted, np.nan)
    jpsi1_y_gen = _rapidity_from_pt_eta_mass_array(jpsi1_pt, jpsi1_eta, jpsi1_mass)
    jpsi2_y_gen = _rapidity_from_pt_eta_mass_array(jpsi2_pt, jpsi2_eta, jpsi2_mass)
    phi_y_gen = _rapidity_from_pt_eta_mass_array(phi_pt, phi_eta, phi_mass)
    j1_px, j1_py, j1_pz, j1_e = _p4_components_array(jpsi1_pt, jpsi1_eta, jpsi1_phi, jpsi1_mass)
    j2_px, j2_py, j2_pz, j2_e = _p4_components_array(jpsi2_pt, jpsi2_eta, jpsi2_phi, jpsi2_mass)
    p_px, p_py, p_pz, p_e = _p4_components_array(phi_pt, phi_eta, phi_phi, phi_mass)
    triple_px = j1_px + j2_px + p_px
    triple_py = j1_py + j2_py + p_py
    triple_pz = j1_pz + j2_pz + p_pz
    triple_e = j1_e + j2_e + p_e
    triple_pt = np.sqrt(triple_px * triple_px + triple_py * triple_py)
    triple_mass = np.sqrt(np.maximum(triple_e * triple_e - triple_px * triple_px - triple_py * triple_py - triple_pz * triple_pz, 0.0))
    triple_abs_y = abs(ak.where((triple_e + triple_pz > 0.0) & (triple_e - triple_pz > 0.0), 0.5 * np.log((triple_e + triple_pz) / (triple_e - triple_pz)), np.nan))

    mu_fid = (
        ((abs(gen_eta) < 1.2) & (gen_pt > cfg.mu_pt_barrel_min))
        | ((abs(gen_eta) >= 1.2) & (abs(gen_eta) < cfg.mu_abs_eta_max) & (gen_pt > cfg.mu_pt_endcap_min))
    )
    kaon_fid = (gen_pt > cfg.track_pt_min) & (abs(gen_eta) < cfg.track_abs_eta_max)
    jpsi1_daughters = is_mu & (mother == jpsi1_idx)
    jpsi2_daughters = is_mu & (mother == jpsi2_idx)
    phi_daughters = is_kaon & (mother == phi_idx)
    fiducial_jpsi_lead = (
        has_full_gen & (ak.sum(jpsi1_daughters, axis=1) >= 2) & ak.all(mu_fid[jpsi1_daughters], axis=1)
    )
    fiducial_jpsi_sublead = (
        has_full_gen & (ak.sum(jpsi2_daughters, axis=1) >= 2) & ak.all(mu_fid[jpsi2_daughters], axis=1)
    )
    fiducial_phi = (
        has_full_gen & (ak.sum(phi_daughters, axis=1) >= 2) & ak.all(kaon_fid[phi_daughters], axis=1)
    )
    fiducial_acceptance = fiducial_jpsi_lead & fiducial_jpsi_sublead & fiducial_phi

    if ntuple_format == "v1.6-singles":
        per_obj_raw = _compute_per_object_flags_v16(
            arrays,
            pdg,
            mother,
            jpsi1_idx,
            jpsi2_idx,
            phi_idx,
            cfg,
            fiducial_jpsi_lead,
            fiducial_jpsi_sublead,
            fiducial_phi,
        )
        s_cand = (
            per_obj_raw["jpsi_lead_fiducial"] & per_obj_raw["jpsi_lead_muonRECO"]
            & per_obj_raw["jpsi_lead_muonID"] & per_obj_raw["jpsi_lead_dimuon"]
            & per_obj_raw["jpsi_sublead_fiducial"] & per_obj_raw["jpsi_sublead_muonRECO"]
            & per_obj_raw["jpsi_sublead_muonID"] & per_obj_raw["jpsi_sublead_dimuon"]
            & per_obj_raw["phi_fiducial"] & per_obj_raw["phi_kaonRECO"]
            & per_obj_raw["phi_kaonID"] & per_obj_raw["phi_dikaon"]
        )
        hlt_event_path_or = _event_trigger_path_or_array(arrays, has_full_gen)
        hlt_event = s_cand & (hlt_event_path_or != 0)
        false_event = ak.values_astype(ak.zeros_like(has_full_gen), bool)
        event_raw: dict[str, ak.Array] = {
            "full_gen": has_full_gen,
            "s_cand": s_cand,
            "hlt_event": hlt_event,
            "hlt_muon_matched": false_event,
            "four_muon_vtx": false_event,
            "four_muon_vtx_noTrigMatch": false_event,
            "Pri_fitValid": false_event,
            "Pri_fitValid_noTrigMatch": false_event,
            "Pri_fitPass": false_event,
            "Pri_fitPass_noTrigMatch": false_event,
            "Pri_assocPVPass": false_event,
            "Pri_assocPVPass_noTrigMatch": false_event,
            "Pri_trackPVPass": false_event,
            "Pri_trackPVPass_noTrigMatch": false_event,
        }
        gen_score = jpsi1_pt ** 2 + jpsi2_pt ** 2 + phi_pt ** 2
        full_mask = ak.to_numpy(has_full_gen)
        entries = np.arange(entry_start, entry_start + n_events, dtype=np.int64)
        event_data: dict[str, Any] = {
            "sample": np.full(np.count_nonzero(full_mask), sample, dtype=object),
            "source_file": np.full(np.count_nonzero(full_mask), source_file, dtype=object),
            "entry": entries[full_mask],
            "run": _to_numpy(arrays["runNum"], has_full_gen, 0).astype(np.int64),
            "lumi": _to_numpy(arrays["lumiNum"], has_full_gen, 0).astype(np.int64),
            "event": _to_numpy(arrays["evtNum"], has_full_gen, 0).astype(np.int64),
            "n_candidates": _to_numpy(ak.num(arrays["SingleJpsi_mass"], axis=1), has_full_gen, 0).astype(np.int64),
            "n_gen_jpsi": ak.to_numpy(ak.num(jpsi_idx_sorted, axis=1)[has_full_gen]).astype(np.int64),
            "n_gen_phi": ak.to_numpy(ak.num(phi_idx_sorted, axis=1)[has_full_gen]).astype(np.int64),
            "n_triple_gen_matched_candidates": np.zeros(np.count_nonzero(full_mask), dtype=np.int64),
            "hlt_event_path_or": _to_numpy(hlt_event_path_or, has_full_gen, 0).astype(np.int8),
        }
        for key in per_object_step_columns():
            event_data[key] = _to_numpy(per_obj_raw[key], has_full_gen, 0).astype(np.int8)
        for key, val in event_raw.items():
            event_data[key] = _to_numpy(val, has_full_gen, 0).astype(np.int8)
        event_data["reco_best_phi_pt"] = np.full(np.count_nonzero(full_mask), np.nan, dtype=np.float64)
        event_data["reco_best_jpsi1_pt"] = np.full(np.count_nonzero(full_mask), np.nan, dtype=np.float64)
        event_data["reco_best_jpsi2_pt"] = np.full(np.count_nonzero(full_mask), np.nan, dtype=np.float64)
        event_data["reco_best_score"] = np.full(np.count_nonzero(full_mask), np.nan, dtype=np.float64)
        event_data["reco_best_phi_gen_idx"] = np.full(np.count_nonzero(full_mask), -1, dtype=np.int64)
        event_data["reco_best_phi_matches_gen"] = np.zeros(np.count_nonzero(full_mask), dtype=bool)
        event_data["reco_best_is_gen_matched"] = np.zeros(np.count_nonzero(full_mask), dtype=bool)
        event_data["n_quality_candidates"] = np.zeros(np.count_nonzero(full_mask), dtype=np.int64)

        gen_data: dict[str, Any] = {
            "sample": np.full(np.count_nonzero(full_mask), sample, dtype=object),
            "source_file": np.full(np.count_nonzero(full_mask), source_file, dtype=object),
            "entry": entries[full_mask],
            "run": event_data["run"],
            "lumi": event_data["lumi"],
            "event": event_data["event"],
            "jpsi_lead_gen_idx": _to_numpy(jpsi1_idx, has_full_gen, -1).astype(np.int64),
            "jpsi_sublead_gen_idx": _to_numpy(jpsi2_idx, has_full_gen, -1).astype(np.int64),
            "phi_gen_idx": _to_numpy(phi_idx, has_full_gen, -1).astype(np.int64),
            "jpsi_lead_pt": _to_numpy(jpsi1_pt, has_full_gen, np.nan).astype(float),
            "jpsi_lead_y": _to_numpy(jpsi1_y_gen, has_full_gen, np.nan).astype(float),
            "jpsi_lead_abs_y": np.abs(_to_numpy(jpsi1_y_gen, has_full_gen, np.nan).astype(float)),
            "jpsi_sublead_pt": _to_numpy(jpsi2_pt, has_full_gen, np.nan).astype(float),
            "jpsi_sublead_y": _to_numpy(jpsi2_y_gen, has_full_gen, np.nan).astype(float),
            "jpsi_sublead_abs_y": np.abs(_to_numpy(jpsi2_y_gen, has_full_gen, np.nan).astype(float)),
            "phi_pt": _to_numpy(phi_pt, has_full_gen, np.nan).astype(float),
            "phi_y": _to_numpy(phi_y_gen, has_full_gen, np.nan).astype(float),
            "phi_abs_y": np.abs(_to_numpy(phi_y_gen, has_full_gen, np.nan).astype(float)),
            "triple_pt": _to_numpy(triple_pt, has_full_gen, np.nan).astype(float),
            "triple_abs_y": _to_numpy(triple_abs_y, has_full_gen, np.nan).astype(float),
            "triple_mass": _to_numpy(triple_mass, has_full_gen, np.nan).astype(float),
            "gen_score": _to_numpy(gen_score, has_full_gen, np.nan).astype(float),
        }
        return {
            "gen_systems": pd.DataFrame(gen_data),
            "event_step_flags": pd.DataFrame(event_data),
        }

    j1_mu1_idx = _as_index_array(arrays["Jpsi_1_mu_1_Idx"])
    j1_mu2_idx = _as_index_array(arrays["Jpsi_1_mu_2_Idx"])
    j2_mu1_idx = _as_index_array(arrays["Jpsi_2_mu_1_Idx"])
    j2_mu2_idx = _as_index_array(arrays["Jpsi_2_mu_2_Idx"])

    j1_a1 = _ancestor_idx_to_pdg(_safe_take_jagged(arrays["muGenMatchIdx"], j1_mu1_idx, -1), pdg, mother, 443)
    j1_a2 = _ancestor_idx_to_pdg(_safe_take_jagged(arrays["muGenMatchIdx"], j1_mu2_idx, -1), pdg, mother, 443)
    j2_a1 = _ancestor_idx_to_pdg(_safe_take_jagged(arrays["muGenMatchIdx"], j2_mu1_idx, -1), pdg, mother, 443)
    j2_a2 = _ancestor_idx_to_pdg(_safe_take_jagged(arrays["muGenMatchIdx"], j2_mu2_idx, -1), pdg, mother, 443)
    jpsi1_leg = ak.where((j1_a1 >= 0) & (j1_a1 == j1_a2), j1_a1, -1)
    jpsi2_leg = ak.where((j2_a1 >= 0) & (j2_a1 == j2_a2), j2_a1, -1)

    if {"Phi_K_1_genMatchIdx", "Phi_K_2_genMatchIdx"}.issubset(arrays.fields):
        phi_k1_gen = arrays["Phi_K_1_genMatchIdx"]
        phi_k2_gen = arrays["Phi_K_2_genMatchIdx"]
    else:
        phi_k1_rk_idx = _as_index_array(arrays["Phi_K_1_RecoKaonTrackIdx"])
        phi_k2_rk_idx = _as_index_array(arrays["Phi_K_2_RecoKaonTrackIdx"])
        phi_k1_gen = _safe_take_jagged(arrays["RecoKaonTrack_genMatchIdx"], phi_k1_rk_idx, -1)
        phi_k2_gen = _safe_take_jagged(arrays["RecoKaonTrack_genMatchIdx"], phi_k2_rk_idx, -1)
    phi_a1 = _ancestor_idx_to_pdg(phi_k1_gen, pdg, mother, 333)
    phi_a2 = _ancestor_idx_to_pdg(phi_k2_gen, pdg, mother, 333)
    phi_leg = ak.where((phi_a1 >= 0) & (phi_a1 == phi_a2), phi_a1, -1)

    matched_candidate = (
        (phi_leg == phi_idx)
        & (
            ((jpsi1_leg == jpsi1_idx) & (jpsi2_leg == jpsi2_idx))
            | ((jpsi1_leg == jpsi2_idx) & (jpsi2_leg == jpsi1_idx))
        )
    )
    n_matched = ak.sum(matched_candidate, axis=1)

    has_jpsi1_reco = ak.any((jpsi1_leg == jpsi1_idx) | (jpsi2_leg == jpsi1_idx), axis=1)
    has_jpsi2_reco = ak.any((jpsi1_leg == jpsi2_idx) | (jpsi2_leg == jpsi2_idx), axis=1)
    single_jpsi_reco = has_jpsi1_reco | has_jpsi2_reco
    double_jpsi_reco = has_jpsi1_reco & has_jpsi2_reco
    single_phi_reco = ak.any(phi_leg == phi_idx, axis=1)

    j1_mu1_filter = _safe_take_jagged(arrays["muIsJpsiFilterMatch"], j1_mu1_idx, 0) != 0
    j1_mu2_filter = _safe_take_jagged(arrays["muIsJpsiFilterMatch"], j1_mu2_idx, 0) != 0
    j2_mu1_filter = _safe_take_jagged(arrays["muIsJpsiFilterMatch"], j2_mu1_idx, 0) != 0
    j2_mu2_filter = _safe_take_jagged(arrays["muIsJpsiFilterMatch"], j2_mu2_idx, 0) != 0
    j1_mu1_trig = _safe_take_jagged(arrays["muIsJpsiTrigMatch"], j1_mu1_idx, 0) != 0
    j1_mu2_trig = _safe_take_jagged(arrays["muIsJpsiTrigMatch"], j1_mu2_idx, 0) != 0
    j2_mu1_trig = _safe_take_jagged(arrays["muIsJpsiTrigMatch"], j2_mu1_idx, 0) != 0
    j2_mu2_trig = _safe_take_jagged(arrays["muIsJpsiTrigMatch"], j2_mu2_idx, 0) != 0
    j1_pair_filter = j1_mu1_filter & j1_mu2_filter
    j2_pair_filter = j2_mu1_filter & j2_mu2_filter
    j1_pair_trig = j1_mu1_trig & j1_mu2_trig
    j2_pair_trig = j2_mu1_trig & j2_mu2_trig
    n_filter_matched = (
        ak.values_astype(j1_mu1_filter, np.int8)
        + ak.values_astype(j1_mu2_filter, np.int8)
        + ak.values_astype(j2_mu1_filter, np.int8)
        + ak.values_astype(j2_mu2_filter, np.int8)
    )
    n_trig_matched = (
        ak.values_astype(j1_mu1_trig, np.int8)
        + ak.values_astype(j1_mu2_trig, np.int8)
        + ak.values_astype(j2_mu1_trig, np.int8)
        + ak.values_astype(j2_mu2_trig, np.int8)
    )
    # DoubleMu4_3_LowMass_v (2 muons): either J/psi dimuon pair matched
    # Dimuon0_Jpsi3p5_Muon2_v (3 muons): one J/psi pair + >=3 matched total
    candidate_hlt = (
        j1_pair_filter | j2_pair_filter | j1_pair_trig | j2_pair_trig
        | (j1_pair_filter & (n_filter_matched >= 3))
        | (j2_pair_filter & (n_filter_matched >= 3))
        | (j1_pair_trig & (n_trig_matched >= 3))
        | (j2_pair_trig & (n_trig_matched >= 3))
    )

    if "Jpsi_1_y" in arrays.fields:
        jpsi1_y = abs(arrays["Jpsi_1_y"])
    else:
        jpsi1_y = abs(_scalar_rapidity_array(arrays["Jpsi_1_px"], arrays["Jpsi_1_py"], arrays["Jpsi_1_pz"], arrays["Jpsi_1_mass"]))
    if "Jpsi_2_y" in arrays.fields:
        jpsi2_y = abs(arrays["Jpsi_2_y"])
    else:
        jpsi2_y = abs(_scalar_rapidity_array(arrays["Jpsi_2_px"], arrays["Jpsi_2_py"], arrays["Jpsi_2_pz"], arrays["Jpsi_2_mass"]))

    # Per-J/psi quality (split from old combined jpsi_quality)
    psi1_quality = (
        (arrays["Jpsi_1_mass"] >= cfg.jpsi_mass_window[0])
        & (arrays["Jpsi_1_mass"] <= cfg.jpsi_mass_window[1])
        & (arrays["Jpsi_1_pt"] > cfg.jpsi_pt_min)
        & (jpsi1_y < cfg.jpsi_abs_y_max)
        & (arrays["Jpsi_1_VtxProb"] > cfg.jpsi_vtxprob_min)
    )
    psi2_quality = (
        (arrays["Jpsi_2_mass"] >= cfg.jpsi_mass_window[0])
        & (arrays["Jpsi_2_mass"] <= cfg.jpsi_mass_window[1])
        & (arrays["Jpsi_2_pt"] > cfg.jpsi_pt_min)
        & (jpsi2_y < cfg.jpsi_abs_y_max)
        & (arrays["Jpsi_2_VtxProb"] > cfg.jpsi_vtxprob_min)
    )
    # Old combined flag (used by reco_best_* and candidate_quality)
    jpsi_quality = psi1_quality & psi2_quality

    # Per-phi kaon ID (track pT/eta) and dikaon (+ phi mass/pt/VtxProb)
    if {"Phi_K_1_pt", "Phi_K_2_pt", "Phi_K_1_eta", "Phi_K_2_eta"}.issubset(arrays.fields):
        phi_k1_pt = arrays["Phi_K_1_pt"]
        phi_k2_pt = arrays["Phi_K_2_pt"]
        phi_k1_eta = arrays["Phi_K_1_eta"]
        phi_k2_eta = arrays["Phi_K_2_eta"]
    else:
        phi_k1_rk_idx = _as_index_array(arrays["Phi_K_1_RecoKaonTrackIdx"])
        phi_k2_rk_idx = _as_index_array(arrays["Phi_K_2_RecoKaonTrackIdx"])
        phi_k1_pt = _safe_take_jagged(arrays["RecoKaonTrack_pt"], phi_k1_rk_idx, -1.0)
        phi_k2_pt = _safe_take_jagged(arrays["RecoKaonTrack_pt"], phi_k2_rk_idx, -1.0)
        phi_k1_eta = _safe_take_jagged(arrays["RecoKaonTrack_eta"], phi_k1_rk_idx, np.nan)
        phi_k2_eta = _safe_take_jagged(arrays["RecoKaonTrack_eta"], phi_k2_rk_idx, np.nan)
    phi_kaonID_raw = (
        (phi_k1_pt > cfg.track_pt_min)
        & (phi_k2_pt > cfg.track_pt_min)
        & (abs(phi_k1_eta) < cfg.track_abs_eta_max)
        & (abs(phi_k2_eta) < cfg.track_abs_eta_max)
    )
    phi_dikaon_raw = phi_kaonID_raw & (
        (arrays["Phi_mass"] >= cfg.phi_mass_window[0])
        & (arrays["Phi_mass"] <= cfg.phi_mass_window[1])
        & (arrays["Phi_pt"] > cfg.phi_pt_min)
        & (arrays["Phi_VtxProb"] > cfg.phi_vtxprob_min)
    )
    # Old combined flag
    phi_quality = phi_dikaon_raw

    # muonID: both muons in a J/psi pair pass soft-muon ID
    mu_id = ak.values_astype(arrays["muIsPatSoftMuon"], bool)
    j1_mu1_id = _safe_take_jagged(mu_id, j1_mu1_idx, False)
    j1_mu2_id = _safe_take_jagged(mu_id, j1_mu2_idx, False)
    j2_mu1_id = _safe_take_jagged(mu_id, j2_mu1_idx, False)
    j2_mu2_id = _safe_take_jagged(mu_id, j2_mu2_idx, False)
    psi1_muonID = j1_mu1_id & j1_mu2_id
    psi2_muonID = j2_mu1_id & j2_mu2_id

    # ── Best-by-score RECO candidate (quality only, no gen-match requirement) ──
    candidate_quality = jpsi_quality & phi_quality
    candidate_score = arrays["Jpsi_1_pt"] ** 2 + arrays["Jpsi_2_pt"] ** 2 + arrays["Phi_pt"] ** 2
    best_idx = ak.argmax(ak.where(candidate_quality, candidate_score, -1.0), axis=1)
    has_quality_candidate = ak.any(candidate_quality, axis=1)
    n_quality_candidates = ak.sum(candidate_quality, axis=1)

    cand_i = ak.local_index(phi_leg, axis=1)
    at_best = cand_i == best_idx

    def _best_or(val, default):
        return ak.fill_none(ak.firsts(val[at_best]), default)

    reco_best_phi_pt = ak.where(has_quality_candidate, _best_or(arrays["Phi_pt"], np.nan), np.nan)
    reco_best_jpsi1_pt = ak.where(has_quality_candidate, _best_or(arrays["Jpsi_1_pt"], np.nan), np.nan)
    reco_best_jpsi2_pt = ak.where(has_quality_candidate, _best_or(arrays["Jpsi_2_pt"], np.nan), np.nan)
    reco_best_score = ak.where(has_quality_candidate, _best_or(candidate_score, np.nan), np.nan)
    reco_best_phi_gen_idx = ak.values_astype(
        ak.where(has_quality_candidate, _best_or(phi_leg, -1), -1), np.int64
    )
    reco_best_phi_matches_gen = ak.where(
        has_quality_candidate,
        _best_or(phi_leg == phi_idx, False),
        False,
    )
    reco_best_is_gen_matched = ak.where(
        has_quality_candidate,
        _best_or(matched_candidate, False),
        False,
    )

    mu_v1 = _safe_take_jagged(arrays["muVertexId"], j1_mu1_idx, -1)
    mu_v2 = _safe_take_jagged(arrays["muVertexId"], j1_mu2_idx, -1)
    mu_v3 = _safe_take_jagged(arrays["muVertexId"], j2_mu1_idx, -1)
    mu_v4 = _safe_take_jagged(arrays["muVertexId"], j2_mu2_idx, -1)
    if {"Phi_K_1_vertexId", "Phi_K_2_vertexId"}.issubset(arrays.fields):
        kv1 = _as_index_array(arrays["Phi_K_1_vertexId"])
        kv2 = _as_index_array(arrays["Phi_K_2_vertexId"])
    else:
        kv1 = ak.full_like(mu_v1, -2)
        kv2 = ak.full_like(mu_v1, -3)
    four_muon_same = (mu_v1 >= 0) & (mu_v1 == mu_v2) & (mu_v1 == mu_v3) & (mu_v1 == mu_v4)
    tri_onia_same = four_muon_same & (mu_v1 == kv1) & (mu_v1 == kv2)
    # Old alias
    same_vtx = tri_onia_same

    hlt_event_path_or = _event_trigger_path_or_array(arrays, has_full_gen)

    # ── Per-object step flags (Efficiency_scheme.md) ──
    # J/psi lead
    jpsi_lead_muonRECO = has_jpsi1_reco
    jpsi_lead_muonID = ak.any(
        ((jpsi1_leg == jpsi1_idx) & psi1_muonID)
        | ((jpsi2_leg == jpsi1_idx) & psi2_muonID),
        axis=1,
    )
    jpsi_lead_dimuon = ak.any(
        ((jpsi1_leg == jpsi1_idx) & psi1_muonID & psi1_quality)
        | ((jpsi2_leg == jpsi1_idx) & psi2_muonID & psi2_quality),
        axis=1,
    )
    # J/psi sublead
    jpsi_sublead_muonRECO = has_jpsi2_reco
    jpsi_sublead_muonID = ak.any(
        ((jpsi1_leg == jpsi2_idx) & psi1_muonID)
        | ((jpsi2_leg == jpsi2_idx) & psi2_muonID),
        axis=1,
    )
    jpsi_sublead_dimuon = ak.any(
        ((jpsi1_leg == jpsi2_idx) & psi1_muonID & psi1_quality)
        | ((jpsi2_leg == jpsi2_idx) & psi2_muonID & psi2_quality),
        axis=1,
    )
    # Phi
    phi_kaonRECO = ak.any(phi_leg == phi_idx, axis=1)
    phi_kaonID = ak.any((phi_leg == phi_idx) & phi_kaonID_raw, axis=1)
    phi_dikaon = ak.any((phi_leg == phi_idx) & phi_dikaon_raw, axis=1)

    if ntuple_format == "v1.6-full":
        per_obj_singles = _compute_per_object_flags_v16(
            arrays,
            pdg,
            mother,
            jpsi1_idx,
            jpsi2_idx,
            phi_idx,
            cfg,
            fiducial_jpsi_lead,
            fiducial_jpsi_sublead,
            fiducial_phi,
        )
        jpsi_lead_muonRECO = per_obj_singles["jpsi_lead_muonRECO"]
        jpsi_lead_muonID = per_obj_singles["jpsi_lead_muonID"]
        jpsi_lead_dimuon = per_obj_singles["jpsi_lead_dimuon"]
        jpsi_sublead_muonRECO = per_obj_singles["jpsi_sublead_muonRECO"]
        jpsi_sublead_muonID = per_obj_singles["jpsi_sublead_muonID"]
        jpsi_sublead_dimuon = per_obj_singles["jpsi_sublead_dimuon"]
        phi_kaonRECO = per_obj_singles["phi_kaonRECO"]
        phi_kaonID = per_obj_singles["phi_kaonID"]
        phi_dikaon = per_obj_singles["phi_dikaon"]

    # Derived flags
    s_cand = (
        fiducial_jpsi_lead & jpsi_lead_muonRECO & jpsi_lead_muonID & jpsi_lead_dimuon
        & fiducial_jpsi_sublead & jpsi_sublead_muonRECO & jpsi_sublead_muonID & jpsi_sublead_dimuon
        & fiducial_phi & phi_kaonRECO & phi_kaonID & phi_dikaon
    )

    # Event-level flags: sequential s_cand → hlt_event → hlt_muon_matched → four_muon_vtx
    # hlt_event = trigger OR (event-level TrigNames/TrigRes)
    # hlt_muon_matched = trigger-object matching (per-muon muIsJpsi*Match flags)
    _trigger_or = hlt_event_path_or != 0
    _hlt_trigger_match_raw = ak.any(matched_candidate & candidate_hlt, axis=1)
    _four_muon_raw = ak.any(matched_candidate & four_muon_same, axis=1)
    _pri_valid_raw = ak.any(matched_candidate & (_as_index_array(arrays["Pri_fitValid"]) == 1), axis=1)
    _pri_pass_raw = ak.any(matched_candidate & (_as_index_array(arrays["Pri_fitPass"]) == 1), axis=1)
    _pri_assoc_raw = ak.any(matched_candidate & (_as_index_array(arrays["Pri_assocPVPass"]) == 1), axis=1)
    _pri_track_raw = ak.any(matched_candidate & (_as_index_array(arrays["Pri_trackPVPass"]) == 1), axis=1)

    # Chain B: with trigger matching (default column names)
    hlt_event = s_cand & _trigger_or
    hlt_muon_matched = hlt_event & _hlt_trigger_match_raw
    four_muon_vtx = hlt_muon_matched & _four_muon_raw
    # Pri_* flags are parallel: all conditioned on four_muon_vtx, not on each other
    Pri_fitValid = four_muon_vtx & _pri_valid_raw
    Pri_fitPass = four_muon_vtx & _pri_pass_raw
    Pri_assocPVPass = four_muon_vtx & _pri_assoc_raw
    Pri_trackPVPass = four_muon_vtx & _pri_track_raw

    # Chain A: without trigger matching (_noTrigMatch suffixed columns)
    four_muon_vtx_noTrigMatch = hlt_event & _four_muon_raw
    Pri_fitValid_noTrigMatch = four_muon_vtx_noTrigMatch & _pri_valid_raw
    Pri_fitPass_noTrigMatch = four_muon_vtx_noTrigMatch & _pri_pass_raw
    Pri_assocPVPass_noTrigMatch = four_muon_vtx_noTrigMatch & _pri_assoc_raw
    Pri_trackPVPass_noTrigMatch = four_muon_vtx_noTrigMatch & _pri_track_raw
    # GEN score (unified with RECO: summed pT²)
    gen_score = jpsi1_pt ** 2 + jpsi2_pt ** 2 + phi_pt ** 2

    # Per-object columns for parquet output
    per_obj_raw: dict[str, ak.Array] = {
        "jpsi_lead_fiducial": fiducial_jpsi_lead,
        "jpsi_lead_muonRECO": jpsi_lead_muonRECO,
        "jpsi_lead_muonID": jpsi_lead_muonID,
        "jpsi_lead_dimuon": jpsi_lead_dimuon,
        "jpsi_sublead_fiducial": fiducial_jpsi_sublead,
        "jpsi_sublead_muonRECO": jpsi_sublead_muonRECO,
        "jpsi_sublead_muonID": jpsi_sublead_muonID,
        "jpsi_sublead_dimuon": jpsi_sublead_dimuon,
        "phi_fiducial": fiducial_phi,
        "phi_kaonRECO": phi_kaonRECO,
        "phi_kaonID": phi_kaonID,
        "phi_dikaon": phi_dikaon,
    }
    event_raw: dict[str, ak.Array] = {
        "full_gen": has_full_gen,
        "s_cand": s_cand,
        "hlt_event": hlt_event,
        "hlt_muon_matched": hlt_muon_matched,
        "four_muon_vtx": four_muon_vtx,
        "four_muon_vtx_noTrigMatch": four_muon_vtx_noTrigMatch,
        "Pri_fitValid": Pri_fitValid,
        "Pri_fitValid_noTrigMatch": Pri_fitValid_noTrigMatch,
        "Pri_fitPass": Pri_fitPass,
        "Pri_fitPass_noTrigMatch": Pri_fitPass_noTrigMatch,
        "Pri_assocPVPass": Pri_assocPVPass,
        "Pri_assocPVPass_noTrigMatch": Pri_assocPVPass_noTrigMatch,
        "Pri_trackPVPass": Pri_trackPVPass,
        "Pri_trackPVPass_noTrigMatch": Pri_trackPVPass_noTrigMatch,
    }

    full_mask = ak.to_numpy(has_full_gen)
    entries = np.arange(entry_start, entry_start + n_events, dtype=np.int64)
    event_data: dict[str, Any] = {
        "sample": np.full(np.count_nonzero(full_mask), sample, dtype=object),
        "source_file": np.full(np.count_nonzero(full_mask), source_file, dtype=object),
        "entry": entries[full_mask],
        "run": _to_numpy(arrays["runNum"], has_full_gen, 0).astype(np.int64),
        "lumi": _to_numpy(arrays["lumiNum"], has_full_gen, 0).astype(np.int64),
        "event": _to_numpy(arrays["evtNum"], has_full_gen, 0).astype(np.int64),
        "n_candidates": ak.to_numpy(ak.num(arrays["Jpsi_1_mass"], axis=1)[has_full_gen]).astype(np.int64),
        "n_gen_jpsi": ak.to_numpy(ak.num(jpsi_idx_sorted, axis=1)[has_full_gen]).astype(np.int64),
        "n_gen_phi": ak.to_numpy(ak.num(phi_idx_sorted, axis=1)[has_full_gen]).astype(np.int64),
        "n_triple_gen_matched_candidates": _to_numpy(n_matched, has_full_gen, 0).astype(np.int64),
        "hlt_event_path_or": _to_numpy(hlt_event_path_or, has_full_gen, 0).astype(np.int8),
    }
    # Per-object step flags
    for key in per_object_step_columns():
        event_data[key] = _to_numpy(per_obj_raw[key], has_full_gen, 0).astype(np.int8)
    # Event-level flags
    for key, val in event_raw.items():
        event_data[key] = _to_numpy(val, has_full_gen, 0).astype(np.int8)
    # Reco best-candidate columns for response matrix classification
    event_data["reco_best_phi_pt"] = _to_numpy(reco_best_phi_pt, has_full_gen, np.nan).astype(np.float64)
    event_data["reco_best_jpsi1_pt"] = _to_numpy(reco_best_jpsi1_pt, has_full_gen, np.nan).astype(np.float64)
    event_data["reco_best_jpsi2_pt"] = _to_numpy(reco_best_jpsi2_pt, has_full_gen, np.nan).astype(np.float64)
    event_data["reco_best_score"] = _to_numpy(reco_best_score, has_full_gen, np.nan).astype(np.float64)
    event_data["reco_best_phi_gen_idx"] = _to_numpy(reco_best_phi_gen_idx, has_full_gen, -1).astype(np.int64)
    event_data["reco_best_phi_matches_gen"] = _to_numpy(reco_best_phi_matches_gen, has_full_gen, False).astype(bool)
    event_data["reco_best_is_gen_matched"] = _to_numpy(reco_best_is_gen_matched, has_full_gen, False).astype(bool)
    event_data["n_quality_candidates"] = _to_numpy(n_quality_candidates, has_full_gen, 0).astype(np.int64)

    gen_data: dict[str, Any] = {
        "sample": np.full(np.count_nonzero(full_mask), sample, dtype=object),
        "source_file": np.full(np.count_nonzero(full_mask), source_file, dtype=object),
        "entry": entries[full_mask],
        "run": event_data["run"],
        "lumi": event_data["lumi"],
        "event": event_data["event"],
        "jpsi_lead_gen_idx": _to_numpy(jpsi1_idx, has_full_gen, -1).astype(np.int64),
        "jpsi_sublead_gen_idx": _to_numpy(jpsi2_idx, has_full_gen, -1).astype(np.int64),
        "phi_gen_idx": _to_numpy(phi_idx, has_full_gen, -1).astype(np.int64),
        "jpsi_lead_pt": _to_numpy(jpsi1_pt, has_full_gen, np.nan).astype(float),
        "jpsi_lead_y": _to_numpy(jpsi1_y_gen, has_full_gen, np.nan).astype(float),
        "jpsi_lead_abs_y": np.abs(_to_numpy(jpsi1_y_gen, has_full_gen, np.nan).astype(float)),
        "jpsi_sublead_pt": _to_numpy(jpsi2_pt, has_full_gen, np.nan).astype(float),
        "jpsi_sublead_y": _to_numpy(jpsi2_y_gen, has_full_gen, np.nan).astype(float),
        "jpsi_sublead_abs_y": np.abs(_to_numpy(jpsi2_y_gen, has_full_gen, np.nan).astype(float)),
        "phi_pt": _to_numpy(phi_pt, has_full_gen, np.nan).astype(float),
        "phi_y": _to_numpy(phi_y_gen, has_full_gen, np.nan).astype(float),
        "phi_abs_y": np.abs(_to_numpy(phi_y_gen, has_full_gen, np.nan).astype(float)),
        "triple_pt": _to_numpy(triple_pt, has_full_gen, np.nan).astype(float),
        "triple_abs_y": _to_numpy(triple_abs_y, has_full_gen, np.nan).astype(float),
        "triple_mass": _to_numpy(triple_mass, has_full_gen, np.nan).astype(float),
        "gen_score": _to_numpy(gen_score, has_full_gen, np.nan).astype(float),
    }
    return {
        "gen_systems": pd.DataFrame(gen_data),
        "event_step_flags": pd.DataFrame(event_data),
    }


def process_efficiency_file_vectorized(
    path: str,
    sample: str,
    cfg: OfflineSelectionConfig,
    tree_path: str = "mkcands/X_data",
    step_size: str = "100 MB",
) -> dict[str, pd.DataFrame]:
    gen_parts: list[pd.DataFrame] = []
    event_parts: list[pd.DataFrame] = []
    iterator = uproot.iterate(
        f"{path}:{tree_path}",
        filter_name=list(ALL_KNOWN_BRANCHES),
        library="ak",
        step_size=step_size,
        report=True,
        **_uproot_read_options(path),
    )
    for arrays, report in iterator:
        chunk = _process_efficiency_chunk_vectorized(arrays, path, sample, cfg, int(report.start))
        if not chunk["gen_systems"].empty:
            gen_parts.append(chunk["gen_systems"])
        if not chunk["event_step_flags"].empty:
            event_parts.append(chunk["event_step_flags"])
    return {
        "gen_systems": pd.concat(gen_parts, ignore_index=True) if gen_parts else pd.DataFrame(),
        "event_step_flags": pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame(),
    }


def run_efficiency_for_sample(
    files: list[str],
    sample: str,
    cfg: OfflineSelectionConfig | None = None,
    tree_path: str = "mkcands/X_data",
    backend: str = "vectorized",
    step_size: str = "100 MB",
    include_trigger_matching: bool = True,
) -> dict[str, pd.DataFrame]:
    cfg = cfg or OfflineSelectionConfig()
    binning = EfficiencyBinning(include_trigger_matching=include_trigger_matching)
    gen_parts: list[pd.DataFrame] = []
    event_parts: list[pd.DataFrame] = []
    for path in files:
        if backend == "python-loop":
            tables = process_efficiency_file(path, sample, cfg, tree_path=tree_path)
        elif backend == "vectorized":
            tables = process_efficiency_file_vectorized(path, sample, cfg, tree_path=tree_path, step_size=step_size)
        else:
            raise ValueError(f"Unsupported efficiency backend: {backend}")
        if not tables["gen_systems"].empty:
            gen_parts.append(tables["gen_systems"])
        if not tables["event_step_flags"].empty:
            event_parts.append(tables["event_step_flags"])
    gen_df = pd.concat(gen_parts, ignore_index=True) if gen_parts else pd.DataFrame()
    event_df = pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()
    counts_df = build_efficiency_counts(gen_df, event_df, binning)
    return {
        "gen_systems": gen_df,
        "event_step_flags": event_df,
        "efficiency_counts": counts_df,
        "cutflow": build_cutflow(event_df, binning),
    }


def clopper_pearson_interval(total: int, passed: int, confidence: float = 0.682689492) -> tuple[float, float]:
    if total <= 0:
        return math.nan, math.nan
    alpha = 1.0 - confidence
    low = 0.0 if passed <= 0 else float(beta.ppf(alpha / 2.0, passed, total - passed + 1))
    high = 1.0 if passed >= total else float(beta.ppf(1.0 - alpha / 2.0, passed + 1, total - passed))
    return low, high


def jeffreys_efficiency_uncertainty(total: int, passed: int) -> tuple[float, float]:
    """Return Jeffreys-smoothed efficiency and symmetric binomial uncertainty."""
    if total <= 0:
        return math.nan, math.nan
    eff = float((passed + 0.5) / (total + 1.0))
    err = float(math.sqrt(eff * (1.0 - eff) / (total + 1.0)))
    return eff, err


def _efficiency_row(base: dict[str, Any], total: int, passed: int) -> dict[str, Any]:
    efficiency = float(passed / total) if total > 0 else math.nan
    low, high = clopper_pearson_interval(total, passed)
    err_low = efficiency - low if total > 0 else math.nan
    err_high = high - efficiency if total > 0 else math.nan
    return {
        **base,
        "total": int(total),
        "passed": int(passed),
        "efficiency": efficiency,
        "err_low": err_low,
        "err_high": err_high,
        "err_sym": max(err_low, err_high) if total > 0 else math.nan,
    }


# Mapping from signed-y y_bin (8 bins, -2.4..+2.4) to |y| bin (4 bins, 0..2.4).
# Signed bins: 0=[-2.4,-1.8), 1=[-1.8,-1.2), 2=[-1.2,-0.6), 3=[-0.6,0),
#               4=[0,0.6), 5=[0.6,1.2), 6=[1.2,1.8), 7=[1.8,2.4)
# |y| bins:    0=[0,0.6), 1=[0.6,1.2), 2=[1.2,1.8), 3=[1.8,2.4)
_SIGNED_TO_ABS_Y_MAP: dict[int, int] = {3: 0, 4: 0, 2: 1, 5: 1, 1: 2, 6: 2, 0: 3, 7: 3}


def _fold_frame_to_abs_y(
    frame: "pd.DataFrame",
    group_keys: list[str],
    output_map_type: str,
    *,
    extra_cols: dict[str, object] | None = None,
) -> "pd.DataFrame":
    """Fold signed-y bins to |y| for an arbitrary 2D efficiency frame.

    Parameters
    ----------
    frame : DataFrame
        Must have columns ``y_bin``, ``total``, ``passed``, ``x_min``, ``x_max``,
        ``x_label``, ``x_axis``, and any columns listed in *group_keys*.
    group_keys : list of str
        Columns that identify a kinematic cell (e.g. ``["object", "step", "x_bin"]``).
    output_map_type : str
        Value to write into the ``"map_type"`` column of output rows.
    extra_cols : dict, optional
        Additional fixed column values to set on every output row.

    Returns
    -------
    DataFrame
        New DataFrame with ``y_axis="abs_y"`` and |y| binning (0..4 bins).
    """
    import pandas as pd

    folded = frame.copy()
    folded["abs_y_bin"] = folded["y_bin"].map(_SIGNED_TO_ABS_Y_MAP)
    folded = folded.loc[folded["abs_y_bin"].notna()]

    agg = folded.groupby(
        group_keys + ["abs_y_bin"], dropna=False
    ).agg(
        total=("total", "sum"),
        passed=("passed", "sum"),
        x_min=("x_min", "first"),
        x_max=("x_max", "first"),
        x_label=("x_label", "first"),
        x_axis=("x_axis", "first"),
    ).reset_index()  # move group keys + abs_y_bin back to columns

    abs_y_edges = (0.0, 0.6, 1.2, 1.8, 2.4)
    rows = []
    for _, row in agg.iterrows():
        iy = int(row["abs_y_bin"])
        key_values = [row[k] for k in group_keys]

        base: dict[str, Any] = {
            "map_type": output_map_type,
            "x_axis": str(row["x_axis"]),
            "y_axis": "abs_y",
            "x_bin": int(row["x_bin"]),
            "y_bin": iy,
            "x_min": float(row["x_min"]),
            "x_max": float(row["x_max"]),
            "y_min": float(abs_y_edges[iy]),
            "y_max": float(abs_y_edges[iy + 1]),
            "x_label": str(row["x_label"]),
            "y_label": f"{abs_y_edges[iy]:g}-{abs_y_edges[iy + 1]:g}",
        }
        # Thread group-key values back into the row (preserve original types)
        for ki, key in enumerate(group_keys):
            base[key] = key_values[ki]
        # Ensure x_bin stays as int (it may have been overwritten by key threading)
        if "x_bin" in base:
            base["x_bin"] = int(base["x_bin"])
        if extra_cols:
            base.update(extra_cols)
        rows.append(_efficiency_row(base, int(row["total"]), int(row["passed"])))

    return pd.DataFrame(rows)


def fold_object_2d_to_abs_y(counts_df: "pd.DataFrame") -> "pd.DataFrame":
    """Fold signed-y object_2d bins to |y| bins by aggregating ±y pairs.

    Returns the input DataFrame augmented with ``object_2d_abs_y`` rows.
    The original ``object_2d`` rows are preserved unchanged.
    """
    import pandas as pd

    obj2d = counts_df.loc[counts_df["map_type"] == "object_2d"].copy()
    if obj2d.empty:
        return counts_df

    abs_df = _fold_frame_to_abs_y(
        obj2d, group_keys=["object", "step", "x_bin"],
        output_map_type="object_2d_abs_y",
    )
    return pd.concat([counts_df, abs_df], ignore_index=True)


def _bin_index(value: float, edges: tuple[float, ...]) -> int:
    if not np.isfinite(value):
        return -1
    idx = int(np.searchsorted(np.asarray(edges), value, side="right") - 1)
    if idx < 0 or idx >= len(edges) - 1:
        return -1
    return idx


def _bin_label(edges: tuple[float, ...], idx: int) -> str:
    return f"{edges[idx]:g}-{edges[idx + 1]:g}"


def _merged_gen_events(gen_df: pd.DataFrame, event_df: pd.DataFrame) -> pd.DataFrame:
    keys = ["sample", "source_file", "entry", "run", "lumi", "event"]
    if gen_df.empty or event_df.empty:
        return pd.DataFrame()
    return gen_df.merge(event_df, on=keys, how="inner")


def build_cutflow(event_df: pd.DataFrame, binning: EfficiencyBinning | None = None) -> pd.DataFrame:
    """Build per-object + event-level cutflow with conditional efficiencies."""
    if event_df.empty:
        return pd.DataFrame(columns=["step", "total", "passed", "efficiency",
                                      "err_low", "err_high", "err_sym",
                                      "conditional_efficiency"])
    use_trig_match = binning.include_trigger_matching if binning is not None else True
    event_steps = EVENT_STEPS if use_trig_match else EVENT_STEPS_NO_TRIG_MATCH
    event_step_previous = EVENT_STEP_PREVIOUS if use_trig_match else EVENT_STEP_PREVIOUS_NO_TRIG_MATCH

    rows: list[dict[str, Any]] = []

    def _cutflow_chain(frame: pd.DataFrame, step_list: tuple[str, ...],
                       base_total: int, object_name: str = "") -> None:
        previous = base_total
        for step in step_list:
            col = step if not object_name else f"{object_name}_{step}"
            passed = int(frame[col].sum()) if col in frame.columns else 0
            row = _efficiency_row(
                {"step": step, "object": object_name}, base_total, passed)
            row["conditional_total"] = int(previous)
            row["conditional_passed"] = int(passed)
            row["conditional_efficiency"] = float(passed / previous) if previous > 0 else math.nan
            rows.append(row)
            previous = passed

    total_full_gen = int(event_df["full_gen"].sum())

    # Per-object chains
    for obj_prefix in ("jpsi_lead", "jpsi_sublead"):
        _cutflow_chain(event_df, PER_JPSI_STEPS, total_full_gen, obj_prefix)
    _cutflow_chain(event_df, PER_PHI_STEPS, total_full_gen, "phi")

    # Event-level criteria after four_muon_vtx are parallel diagnostics.
    s_cand_total = int(event_df["s_cand"].sum())
    for step in event_steps:
        passed = int(event_df[step].sum()) if step in event_df.columns else 0
        row = _efficiency_row({"step": step, "object": ""}, s_cand_total, passed)
        previous_step = event_step_previous[step]
        if previous_step == "s_cand":
            previous = s_cand_total
        else:
            previous = int(event_df[previous_step].sum()) if previous_step in event_df.columns else 0
        row["previous_step"] = previous_step
        row["conditional_total"] = int(previous)
        row["conditional_passed"] = int(passed)
        row["conditional_efficiency"] = float(passed / previous) if previous > 0 else math.nan
        rows.append(row)

    return pd.DataFrame(rows)


def build_efficiency_counts(gen_df: pd.DataFrame, event_df: pd.DataFrame, binning: EfficiencyBinning) -> pd.DataFrame:
    merged = _merged_gen_events(gen_df, event_df)
    if merged.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    rows.extend(_inclusive_counts(merged, binning))
    rows.extend(_per_object_counts(merged, binning))
    rows.extend(_correlated_3d_counts(merged, binning))
    rows.extend(_correlated_5d_counts(merged, binning))
    rows.extend(_triple_sidecheck_counts(merged, binning))
    return pd.DataFrame(rows)


def _inclusive_counts(frame: pd.DataFrame, binning: EfficiencyBinning) -> list[dict[str, Any]]:
    """One-row-per-step inclusive counts (no binning)."""
    rows: list[dict[str, Any]] = []
    total = int(frame["full_gen"].sum())

    # Per-object step columns
    for col in per_object_step_columns():
        if col in frame.columns:
            obj, step = col.rsplit("_", 1)
            rows.append(_efficiency_row(
                {"map_type": "inclusive", "step": step, "object": obj},
                total, int(frame[col].sum())))

    # Event-level columns
    if binning.include_trigger_matching:
        event_cols = ("s_cand", "hlt_event", "hlt_muon_matched", "four_muon_vtx",
                      "Pri_fitValid", "Pri_fitPass", "Pri_assocPVPass",
                      "Pri_trackPVPass", "full_gen")
    else:
        event_cols = ("s_cand", "hlt_event", "four_muon_vtx_noTrigMatch",
                      "Pri_fitValid_noTrigMatch", "Pri_fitPass_noTrigMatch",
                      "Pri_assocPVPass_noTrigMatch", "Pri_trackPVPass_noTrigMatch",
                      "full_gen")
    for col in event_cols:
        if col in frame.columns:
            rows.append(_efficiency_row(
                {"map_type": "inclusive", "step": col, "object": ""},
                total, int(frame[col].sum())))

    return rows


def _per_object_counts(frame: pd.DataFrame, binning: EfficiencyBinning) -> list[dict[str, Any]]:
    """Per-object 2D (pT, y) bins with conditional denominators."""
    rows: list[dict[str, Any]] = []
    specs = (
        ("jpsi_lead", "jpsi_lead_pt", "jpsi_lead_y",
         binning.jpsi_pt_edges, binning.object_y_edges, PER_JPSI_STEPS),
        ("jpsi_sublead", "jpsi_sublead_pt", "jpsi_sublead_y",
         binning.jpsi_pt_edges, binning.object_y_edges, PER_JPSI_STEPS),
        ("phi", "phi_pt", "phi_y",
         binning.phi_pt_edges, binning.object_y_edges, PER_PHI_STEPS),
    )
    for obj, pt_col, y_col, pt_edges, y_edges, steps in specs:
        for ix in range(len(pt_edges) - 1):
            for iy in range(len(y_edges) - 1):
                subset = frame[
                    (frame[pt_col] >= pt_edges[ix])
                    & (frame[pt_col] < pt_edges[ix + 1])
                    & (frame[y_col] >= y_edges[iy])
                    & (frame[y_col] < y_edges[iy + 1])
                ]
                full_gen_total = int(subset["full_gen"].sum())
                for step in steps:
                    col = f"{obj}_{step}"
                    rows.append(
                        _efficiency_row(
                            {
                                "map_type": "object_2d",
                                "object": obj,
                                "step": step,
                                "x_axis": "pt",
                                "y_axis": "y",
                                "x_bin": ix,
                                "y_bin": iy,
                                "x_min": pt_edges[ix],
                                "x_max": pt_edges[ix + 1],
                                "y_min": y_edges[iy],
                                "y_max": y_edges[iy + 1],
                                "x_label": _bin_label(pt_edges, ix),
                                "y_label": _bin_label(y_edges, iy),
                            },
                            full_gen_total,
                            int(subset[col].sum()) if full_gen_total else 0,
                        )
                    )
    return rows


def _correlated_3d_counts(frame: pd.DataFrame, binning: EfficiencyBinning) -> list[dict[str, Any]]:
    """Event-level 3D (jpsi_lead_pt, jpsi_sublead_pt, phi_pt) bins."""
    rows: list[dict[str, Any]] = []
    map_steps = CORRELATED_MAP_STEPS if binning.include_trigger_matching else CORRELATED_MAP_STEPS_NO_TRIG_MATCH
    jpsi_edges = binning.jpsi_pt_edges
    phi_edges = binning.phi_pt_edges
    for ix in range(len(jpsi_edges) - 1):
        for iy in range(len(jpsi_edges) - 1):
            for iz in range(len(phi_edges) - 1):
                subset = frame[
                    (frame["jpsi_lead_pt"] >= jpsi_edges[ix])
                    & (frame["jpsi_lead_pt"] < jpsi_edges[ix + 1])
                    & (frame["jpsi_sublead_pt"] >= jpsi_edges[iy])
                    & (frame["jpsi_sublead_pt"] < jpsi_edges[iy + 1])
                    & (frame["phi_pt"] >= phi_edges[iz])
                    & (frame["phi_pt"] < phi_edges[iz + 1])
                ]
                total = int(subset["full_gen"].sum())
                for step in map_steps:
                    rows.append(
                        _efficiency_row(
                            {
                                "map_type": "correlated_3d",
                                "step": step,
                                "x_axis": "jpsi_lead_pt",
                                "y_axis": "jpsi_sublead_pt",
                                "z_axis": "phi_pt",
                                "x_bin": ix,
                                "y_bin": iy,
                                "z_bin": iz,
                                "x_min": jpsi_edges[ix],
                                "x_max": jpsi_edges[ix + 1],
                                "y_min": jpsi_edges[iy],
                                "y_max": jpsi_edges[iy + 1],
                                "z_min": phi_edges[iz],
                                "z_max": phi_edges[iz + 1],
                                "x_label": _bin_label(jpsi_edges, ix),
                                "y_label": _bin_label(jpsi_edges, iy),
                                "z_label": _bin_label(phi_edges, iz),
                            },
                            total,
                            int(subset[step].sum()) if total else 0,
                        )
                    )
    return rows


def _correlated_5d_counts(frame: pd.DataFrame, binning: EfficiencyBinning) -> list[dict[str, Any]]:
    """Event-level 5D (jpsi_lead_pt, jpsi_sublead_pt, phi_pt, jpsi_lead_abs_y, jpsi_sublead_abs_y) bins.

    This is the non-factorized approach with rapidity binning for both J/psi mesons.
    The 4mu vertex correlation between the two J/psi mesons is preserved because the
    full event efficiency P(selected|gen) is computed in a single multi-dimensional bin.
    Phi abs_y is omitted to keep the bin count manageable (2,304 vs 9,216 with phi y).
    """
    rows: list[dict[str, Any]] = []
    map_steps = CORRELATED_MAP_STEPS if binning.include_trigger_matching else CORRELATED_MAP_STEPS_NO_TRIG_MATCH
    jpsi_edges = binning.jpsi_pt_edges
    phi_edges = binning.phi_pt_edges
    y_edges = binning.object_abs_y_edges
    for ix in range(len(jpsi_edges) - 1):
        for iy in range(len(jpsi_edges) - 1):
            for iz in range(len(phi_edges) - 1):
                for iu in range(len(y_edges) - 1):
                    for iv in range(len(y_edges) - 1):
                        subset = frame[
                            (frame["jpsi_lead_pt"] >= jpsi_edges[ix])
                            & (frame["jpsi_lead_pt"] < jpsi_edges[ix + 1])
                            & (frame["jpsi_sublead_pt"] >= jpsi_edges[iy])
                            & (frame["jpsi_sublead_pt"] < jpsi_edges[iy + 1])
                            & (frame["phi_pt"] >= phi_edges[iz])
                            & (frame["phi_pt"] < phi_edges[iz + 1])
                            & (frame["jpsi_lead_abs_y"] >= y_edges[iu])
                            & (frame["jpsi_lead_abs_y"] < y_edges[iu + 1])
                            & (frame["jpsi_sublead_abs_y"] >= y_edges[iv])
                            & (frame["jpsi_sublead_abs_y"] < y_edges[iv + 1])
                        ]
                        total = int(subset["full_gen"].sum())
                        for step in map_steps:
                            rows.append(
                                _efficiency_row(
                                    {
                                        "map_type": "correlated_5d",
                                        "step": step,
                                        "x_axis": "jpsi_lead_pt",
                                        "y_axis": "jpsi_sublead_pt",
                                        "z_axis": "phi_pt",
                                        "u_axis": "jpsi_lead_abs_y",
                                        "v_axis": "jpsi_sublead_abs_y",
                                        "x_bin": ix,
                                        "y_bin": iy,
                                        "z_bin": iz,
                                        "u_bin": iu,
                                        "v_bin": iv,
                                        "x_min": jpsi_edges[ix],
                                        "x_max": jpsi_edges[ix + 1],
                                        "y_min": jpsi_edges[iy],
                                        "y_max": jpsi_edges[iy + 1],
                                        "z_min": phi_edges[iz],
                                        "z_max": phi_edges[iz + 1],
                                        "u_min": y_edges[iu],
                                        "u_max": y_edges[iu + 1],
                                        "v_min": y_edges[iv],
                                        "v_max": y_edges[iv + 1],
                                        "x_label": _bin_label(jpsi_edges, ix),
                                        "y_label": _bin_label(jpsi_edges, iy),
                                        "z_label": _bin_label(phi_edges, iz),
                                        "u_label": _bin_label(y_edges, iu),
                                        "v_label": _bin_label(y_edges, iv),
                                    },
                                    total,
                                    int(subset[step].sum()) if total else 0,
                                )
                            )
    return rows


def _triple_sidecheck_counts(frame: pd.DataFrame, binning: EfficiencyBinning) -> list[dict[str, Any]]:
    """1D triple-system side-check counts."""
    rows: list[dict[str, Any]] = []
    cond_steps = EVENT_CONDITIONAL_STEPS if binning.include_trigger_matching else EVENT_CONDITIONAL_STEPS_NO_TRIG_MATCH
    specs = (
        ("triple_pt", binning.triple_pt_edges),
        ("triple_abs_y", binning.triple_abs_y_edges),
        ("triple_mass", binning.triple_mass_edges),
    )
    for axis, edges in specs:
        for idx in range(len(edges) - 1):
            subset = frame[(frame[axis] >= edges[idx]) & (frame[axis] < edges[idx + 1])]
            total = int(subset["full_gen"].sum())
            for step in cond_steps:
                if step in subset.columns:
                    rows.append(
                        _efficiency_row(
                            {
                                "map_type": "triple_1d",
                                "step": step,
                                "x_axis": axis,
                                "x_bin": idx,
                                "x_min": edges[idx],
                                "x_max": edges[idx + 1],
                                "x_label": _bin_label(edges, idx),
                            },
                            total,
                            int(subset[step].sum()) if total else 0,
                        )
                    )
    return rows


def build_subprocess_envelope(sample_count_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for sample, frame in sample_count_tables.items():
        if frame.empty:
            continue
        tagged = frame.copy()
        tagged["sample"] = sample
        frames.append(tagged)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    group_cols = [
        column
        for column in combined.columns
        if column
        not in {
            "sample",
            "total",
            "passed",
            "efficiency",
            "err_low",
            "err_high",
            "err_sym",
        }
        and not column.startswith("err_")
    ]
    rows = []
    for keys, group in combined.groupby(group_cols, dropna=False):
        key_values = keys if isinstance(keys, tuple) else (keys,)
        row = dict(zip(group_cols, key_values))
        values = group["efficiency"].dropna()
        median = float(values.median()) if not values.empty else math.nan
        row.update(
            {
                "n_samples": int(group["sample"].nunique()),
                "eff_min": float(values.min()) if not values.empty else math.nan,
                "eff_max": float(values.max()) if not values.empty else math.nan,
                "eff_median": median,
                "max_abs_deviation": float(np.max(np.abs(values.to_numpy() - median))) if not values.empty else math.nan,
                "total_sum": int(group["total"].sum()),
                "passed_sum": int(group["passed"].sum()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def build_acceptance_maps(counts_df: pd.DataFrame) -> pd.DataFrame:
    """Extract per-object fiducial acceptance rows.

    Filters for step == 'fiducial' in per-object rows (object_2d or object_acceptance_2d).
    """
    if counts_df.empty:
        return pd.DataFrame()
    acc = counts_df.loc[
        (counts_df["step"] == "fiducial")
        & (counts_df["map_type"].isin(["object_2d", "object_acceptance_2d"]))
    ].copy()
    if not acc.empty:
        acc["quantity"] = "acceptance_vs_full_gen"
    return acc.reset_index(drop=True)


def build_per_object_acceptance_maps(
    gen_df: pd.DataFrame, event_df: pd.DataFrame, binning: EfficiencyBinning
) -> pd.DataFrame:
    merged = _merged_gen_events(gen_df, event_df)
    if merged.empty:
        return pd.DataFrame()
    required = ["jpsi_lead_fiducial", "jpsi_sublead_fiducial", "phi_fiducial"]
    if not all(c in merged.columns for c in required):
        return pd.DataFrame()
    y_required = ["jpsi_lead_y", "jpsi_sublead_y", "phi_y"]
    if not all(c in merged.columns for c in y_required):
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    specs = (
        ("jpsi_lead", "jpsi_lead_pt", "jpsi_lead_y", "jpsi_lead_fiducial", binning.jpsi_pt_edges, binning.object_y_edges),
        ("jpsi_sublead", "jpsi_sublead_pt", "jpsi_sublead_y", "jpsi_sublead_fiducial", binning.jpsi_pt_edges, binning.object_y_edges),
        ("phi", "phi_pt", "phi_y", "phi_fiducial", binning.phi_pt_edges, binning.object_y_edges),
    )
    for obj, pt_col, y_col, flag_col, pt_edges, y_edges in specs:
        for ix in range(len(pt_edges) - 1):
            for iy in range(len(y_edges) - 1):
                subset = merged[
                    (merged[pt_col] >= pt_edges[ix])
                    & (merged[pt_col] < pt_edges[ix + 1])
                    & (merged[y_col] >= y_edges[iy])
                    & (merged[y_col] < y_edges[iy + 1])
                ]
                total = int(subset["full_gen"].sum())
                rows.append(
                    _efficiency_row(
                        {
                            "map_type": "object_acceptance_2d",
                            "object": obj,
                            "step": "fiducial",
                            "x_axis": "pt",
                            "y_axis": "y",
                            "x_bin": ix,
                            "y_bin": iy,
                            "x_min": pt_edges[ix],
                            "x_max": pt_edges[ix + 1],
                            "y_min": y_edges[iy],
                            "y_max": y_edges[iy + 1],
                            "x_label": _bin_label(pt_edges, ix),
                            "y_label": _bin_label(y_edges, iy),
                        },
                        total,
                        int(subset[flag_col].sum()) if total else 0,
                    )
                )
    result = pd.DataFrame(rows)
    if not result.empty:
        result["quantity"] = "per_object_acceptance"
    return result


def _stacked_jpsi_frame(gen_df: pd.DataFrame, event_df: pd.DataFrame) -> pd.DataFrame:
    merged = _merged_gen_events(gen_df, event_df)
    required = ["jpsi_lead_pt", "jpsi_lead_y", "jpsi_sublead_pt", "jpsi_sublead_y",
                 "jpsi_lead_fiducial", "jpsi_sublead_fiducial"]
    if merged.empty or not all(c in merged.columns for c in required):
        return pd.DataFrame()
    parts: list[pd.DataFrame] = []
    for role, flag_col in (("lead", "jpsi_lead_fiducial"), ("sublead", "jpsi_sublead_fiducial")):
        part = merged.copy()
        part["object"] = "jpsi"
        part["jpsi_role"] = role
        part["jpsi_pt"] = part[f"jpsi_{role}_pt"]
        part["jpsi_y"] = part[f"jpsi_{role}_y"]
        part["jpsi_abs_y"] = part[f"jpsi_{role}_abs_y"] if f"jpsi_{role}_abs_y" in part.columns else part["jpsi_y"].abs()
        part["jpsi_fiducial_acceptance"] = part[flag_col].astype(int)
        # Copy per-J/psi step flags for this role
        for suffix in PER_JPSI_STEPS:
            col = f"jpsi_{role}_{suffix}"
            if col in part.columns:
                part[f"jpsi_{suffix}"] = part[col].astype(int)
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def build_stacked_jpsi_acceptance_maps(
    gen_df: pd.DataFrame, event_df: pd.DataFrame, binning: EfficiencyBinning
) -> pd.DataFrame:
    stacked = _stacked_jpsi_frame(gen_df, event_df)
    if stacked.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    pt_edges = binning.jpsi_pt_edges
    y_edges = binning.object_abs_y_edges
    for ix in range(len(pt_edges) - 1):
        for iy in range(len(y_edges) - 1):
            subset = stacked[
                (stacked["jpsi_pt"] >= pt_edges[ix])
                & (stacked["jpsi_pt"] < pt_edges[ix + 1])
                & (stacked["jpsi_abs_y"] >= y_edges[iy])
                & (stacked["jpsi_abs_y"] < y_edges[iy + 1])
            ]
            total = int(len(subset))
            rows.append(
                _efficiency_row(
                    {
                        "map_type": "stacked_jpsi_acceptance_2d",
                        "object": "jpsi",
                        "step": "fiducial",
                        "x_axis": "pt",
                        "y_axis": "abs_y",
                        "x_bin": ix,
                        "y_bin": iy,
                        "x_min": pt_edges[ix],
                        "x_max": pt_edges[ix + 1],
                        "y_min": y_edges[iy],
                        "y_max": y_edges[iy + 1],
                        "x_label": _bin_label(pt_edges, ix),
                        "y_label": _bin_label(y_edges, iy),
                        "quantity": "stacked_jpsi_acceptance",
                    },
                    total,
                    int(subset["jpsi_fiducial_acceptance"].sum()) if total else 0,
                )
            )
    return pd.DataFrame(rows)


def build_stacked_jpsi_efficiency_maps(
    gen_df: pd.DataFrame, event_df: pd.DataFrame, binning: EfficiencyBinning
) -> pd.DataFrame:
    stacked = _stacked_jpsi_frame(gen_df, event_df)
    if stacked.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    pt_edges = binning.jpsi_pt_edges
    y_edges = binning.object_abs_y_edges
    for ix in range(len(pt_edges) - 1):
        for iy in range(len(y_edges) - 1):
            subset = stacked[
                (stacked["jpsi_pt"] >= pt_edges[ix])
                & (stacked["jpsi_pt"] < pt_edges[ix + 1])
                & (stacked["jpsi_abs_y"] >= y_edges[iy])
                & (stacked["jpsi_abs_y"] < y_edges[iy + 1])
            ]
            total = int(len(subset))
            for suffix in PER_JPSI_STEPS[1:]:  # skip fiducial (already in acceptance)
                col = f"jpsi_{suffix}"
                rows.append(
                    _efficiency_row(
                        {
                            "map_type": "stacked_jpsi_efficiency_2d",
                            "object": "jpsi",
                            "step": suffix,
                            "x_axis": "pt",
                            "y_axis": "abs_y",
                            "x_bin": ix,
                            "y_bin": iy,
                            "x_min": pt_edges[ix],
                            "x_max": pt_edges[ix + 1],
                            "y_min": y_edges[iy],
                            "y_max": y_edges[iy + 1],
                            "x_label": _bin_label(pt_edges, ix),
                            "y_label": _bin_label(y_edges, iy),
                            "quantity": "stacked_jpsi_efficiency",
                        },
                        total,
                        int(subset[col].sum()) if total and col in subset.columns else 0,
                    )
                )
    return pd.DataFrame(rows)


def _recompute_efficiency(frame: pd.DataFrame, total_col: str, passed_col: str) -> None:
    totals = frame[total_col].to_numpy(dtype=int)
    n_passed = frame[passed_col].to_numpy(dtype=int)
    efficiency = np.full(len(totals), np.nan)
    err_low = np.full(len(totals), np.nan)
    err_high = np.full(len(totals), np.nan)
    err_sym = np.full(len(totals), np.nan)
    for i, (t, p) in enumerate(zip(totals, n_passed)):
        row = _efficiency_row({}, int(t), int(p))
        efficiency[i] = row["efficiency"]
        err_low[i] = row["err_low"]
        err_high[i] = row["err_high"]
        err_sym[i] = row["err_sym"]
    frame["total"] = totals
    frame["passed"] = n_passed
    frame["efficiency"] = efficiency
    frame["err_low"] = err_low
    frame["err_high"] = err_high
    frame["err_sym"] = err_sym


_MAP_TYPE_KEYS: dict[str, list[str]] = {
    "inclusive": [],
    "object_2d": ["object", "x_bin", "y_bin"],
    "object_acceptance_2d": ["object", "x_bin", "y_bin"],
    "correlated_3d": ["x_bin", "y_bin", "z_bin"],
    "correlated_5d": ["x_bin", "y_bin", "z_bin", "u_bin", "v_bin"],
    "triple_1d": ["x_axis", "x_bin"],
}

# Per-map-type step ordering for conditional chain
_OBJECT_CHAIN = {
    "jpsi_lead": PER_JPSI_STEPS,
    "jpsi_sublead": PER_JPSI_STEPS,
    "phi": PER_PHI_STEPS,
}


def build_conditional_maps(counts_df: pd.DataFrame, binning: EfficiencyBinning | None = None) -> pd.DataFrame:
    if counts_df.empty:
        return pd.DataFrame()
    use_trig_match = binning.include_trigger_matching if binning is not None else True
    corr_steps = CORRELATED_MAP_STEPS if use_trig_match else CORRELATED_MAP_STEPS_NO_TRIG_MATCH
    step_previous = EVENT_STEP_PREVIOUS if use_trig_match else EVENT_STEP_PREVIOUS_NO_TRIG_MATCH
    cond_steps = EVENT_CONDITIONAL_STEPS if use_trig_match else EVENT_CONDITIONAL_STEPS_NO_TRIG_MATCH

    parts: list[pd.DataFrame] = []

    for map_type, keys in _MAP_TYPE_KEYS.items():
        subset = counts_df.loc[counts_df["map_type"] == map_type].copy()
        if subset.empty:
            continue

        # For object_2d and object_acceptance_2d, chain per-object steps
        if map_type in ("object_2d", "object_acceptance_2d"):
            for obj_name in subset["object"].drop_duplicates():
                obj_subset = subset[subset["object"] == obj_name]
                chain = _OBJECT_CHAIN.get(obj_name, ())
                _chain_conditional_rows(obj_subset, chain, keys, parts)
        elif map_type == "correlated_3d":
            _conditional_rows_with_denominators(
                subset,
                corr_steps,
                step_previous,
                keys,
                parts,
            )
        elif map_type == "correlated_5d":
            _conditional_rows_with_denominators(
                subset,
                corr_steps,
                step_previous,
                keys,
                parts,
            )
        elif map_type == "triple_1d":
            _conditional_rows_with_denominators(
                subset,
                cond_steps,
                step_previous,
                keys,
                parts,
            )
        elif map_type == "inclusive":
            # Group by object for proper per-object vs event-level chaining
            if "object" in subset.columns:
                for obj_name in subset["object"].drop_duplicates():
                    obj_subset = subset[subset["object"] == obj_name]
                    if obj_name and obj_name != "":
                        chain = _OBJECT_CHAIN.get(obj_name, ())
                        _chain_conditional_rows(obj_subset, chain, keys, parts)
                    else:
                        _conditional_rows_with_denominators(
                            obj_subset,
                            cond_steps,
                            step_previous,
                            keys,
                            parts,
                        )
            else:
                _chain_conditional_rows(subset, (), keys, parts)

    if not parts:
        return pd.DataFrame()
    result = pd.concat(parts, ignore_index=True)
    result.drop(columns=["passed_prev"], errors="ignore", inplace=True)
    return result


def _chain_conditional_rows(subset: pd.DataFrame, chain: tuple[str, ...],
                            keys: list[str], parts: list[pd.DataFrame]) -> None:
    """Build conditional efficiency rows for a single (map_type, object) group."""
    if chain:
        present_steps = [s for s in chain if s in subset["step"].values]
    else:
        present_steps = sorted(subset["step"].drop_duplicates().tolist())
    if not present_steps:
        return

    # First step: baseline with previous_step = "total"
    first = subset.loc[subset["step"] == present_steps[0]].copy()
    first["previous_step"] = "total"
    first["conditional_total"] = first["total"].astype(int)
    first["conditional_passed"] = first["passed"].astype(int)
    first["absolute_total"] = first["total"].astype(int)
    first["absolute_passed"] = first["passed"].astype(int)
    first["absolute_efficiency"] = first["efficiency"].astype(float)
    _recompute_efficiency(first, "conditional_total", "conditional_passed")
    first["quantity"] = "conditional_efficiency_vs_previous_step"
    parts.append(first)

    # Subsequent steps
    for prev_step, this_step in zip(present_steps, present_steps[1:]):
        this = subset.loc[subset["step"] == this_step].copy()
        prev = subset.loc[subset["step"] == prev_step].copy()
        if this.empty or prev.empty:
            continue
        if keys:
            merged = this.merge(
                prev[keys + ["passed"]],
                on=keys,
                how="left",
                suffixes=("", "_prev"),
            )
        else:
            merged = this.copy()
            merged["passed_prev"] = prev["passed"].iloc[0] if len(prev) > 0 else 0
        merged["previous_step"] = prev_step
        merged["conditional_total"] = merged["passed_prev"].fillna(0).astype(int)
        merged["conditional_passed"] = merged["passed"].astype(int)
        merged["absolute_total"] = merged["total"].astype(int)
        merged["absolute_passed"] = merged["passed"].astype(int)
        merged["absolute_efficiency"] = merged["efficiency"].astype(float)
        _recompute_efficiency(merged, "conditional_total", "conditional_passed")
        merged["quantity"] = "conditional_efficiency_vs_previous_step"
        parts.append(merged)


def _conditional_rows_with_denominators(
    subset: pd.DataFrame,
    steps: tuple[str, ...],
    previous_by_step: dict[str, str],
    keys: list[str],
    parts: list[pd.DataFrame],
) -> None:
    """Build conditional rows when later criteria are parallel, not chained."""
    present_steps = [step for step in steps if step in subset["step"].values]
    if not present_steps:
        return

    for step in present_steps:
        this = subset.loc[subset["step"] == step].copy()
        previous_step = previous_by_step.get(step)
        if not previous_step:
            this["previous_step"] = "total"
            this["conditional_total"] = this["total"].astype(int)
        else:
            prev = subset.loc[subset["step"] == previous_step].copy()
            if prev.empty:
                this["previous_step"] = "total"
                this["conditional_total"] = this["total"].astype(int)
            elif keys:
                this = this.merge(
                    prev[keys + ["passed"]],
                    on=keys,
                    how="left",
                    suffixes=("", "_prev"),
                )
                this["previous_step"] = previous_step
                this["conditional_total"] = this["passed_prev"].fillna(0).astype(int)
            else:
                this["previous_step"] = previous_step
                this["conditional_total"] = int(prev["passed"].iloc[0])

        this["conditional_passed"] = this["passed"].astype(int)
        this["absolute_total"] = this["total"].astype(int)
        this["absolute_passed"] = this["passed"].astype(int)
        this["absolute_efficiency"] = this["efficiency"].astype(float)
        _recompute_efficiency(this, "conditional_total", "conditional_passed")
        this["quantity"] = "conditional_efficiency_vs_previous_step"
        parts.append(this)


def _build_pair_level_maps(
    gen_df: pd.DataFrame, event_df: pd.DataFrame, binning: EfficiencyBinning,
    spec: PairLevelMapSpec,
) -> pd.DataFrame:
    """Pair-level efficiency binned in (jpsi_lead_pt, jpsi_sublead_pt)."""
    merged = _merged_gen_events(gen_df, event_df)
    if merged.empty or spec.step not in merged.columns or spec.denominator_col not in merged.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    jpsi_edges = binning.jpsi_pt_edges
    for ix in range(len(jpsi_edges) - 1):
        for iy in range(len(jpsi_edges) - 1):
            subset = merged[
                (merged["jpsi_lead_pt"] >= jpsi_edges[ix])
                & (merged["jpsi_lead_pt"] < jpsi_edges[ix + 1])
                & (merged["jpsi_sublead_pt"] >= jpsi_edges[iy])
                & (merged["jpsi_sublead_pt"] < jpsi_edges[iy + 1])
            ]
            denominator = subset[spec.denominator_col].astype(bool)
            passed_step = subset[spec.step].astype(bool)
            total = int(denominator.sum())
            passed = int((denominator & passed_step).sum())
            rows.append(
                _efficiency_row(
                    {
                        "map_type": "pair_vertex_2d",
                        "step": spec.step,
                        "x_axis": "jpsi_lead_pt",
                        "y_axis": "jpsi_sublead_pt",
                        "x_bin": ix,
                        "y_bin": iy,
                        "x_min": jpsi_edges[ix],
                        "x_max": jpsi_edges[ix + 1],
                        "y_min": jpsi_edges[iy],
                        "y_max": jpsi_edges[iy + 1],
                        "x_label": _bin_label(jpsi_edges, ix),
                        "y_label": _bin_label(jpsi_edges, iy),
                        "quantity": spec.quantity,
                    },
                    total,
                    passed,
                )
            )
    return pd.DataFrame(rows)


def build_pair_level_maps(
    gen_df: pd.DataFrame,
    event_df: pd.DataFrame,
    binning: EfficiencyBinning,
    specs: tuple[PairLevelMapSpec, ...] = PAIR_LEVEL_MAP_SPECS,
) -> dict[str, pd.DataFrame]:
    """Build all configured pair-level maps keyed by step name."""
    return {
        spec.step: _build_pair_level_maps(gen_df, event_df, binning, spec)
        for spec in specs
    }


def build_four_muon_vertex_maps(
    gen_df: pd.DataFrame, event_df: pd.DataFrame, binning: EfficiencyBinning
) -> pd.DataFrame:
    return _build_pair_level_maps(
        gen_df, event_df, binning, PAIR_LEVEL_MAP_SPEC_BY_STEP["four_muon_vtx"]
    )


def build_pri_fitvalid_maps(
    gen_df: pd.DataFrame, event_df: pd.DataFrame, binning: EfficiencyBinning
) -> pd.DataFrame:
    return _build_pair_level_maps(
        gen_df, event_df, binning, PAIR_LEVEL_MAP_SPEC_BY_STEP["Pri_fitValid"]
    )


def build_pri_fitpass_maps(
    gen_df: pd.DataFrame, event_df: pd.DataFrame, binning: EfficiencyBinning
) -> pd.DataFrame:
    return _build_pair_level_maps(
        gen_df, event_df, binning, PAIR_LEVEL_MAP_SPEC_BY_STEP["Pri_fitPass"]
    )


def build_pri_assocpv_maps(
    gen_df: pd.DataFrame, event_df: pd.DataFrame, binning: EfficiencyBinning
) -> pd.DataFrame:
    return _build_pair_level_maps(
        gen_df, event_df, binning, PAIR_LEVEL_MAP_SPEC_BY_STEP["Pri_assocPVPass"]
    )


def build_pri_trackpv_maps(
    gen_df: pd.DataFrame, event_df: pd.DataFrame, binning: EfficiencyBinning
) -> pd.DataFrame:
    return _build_pair_level_maps(
        gen_df, event_df, binning, PAIR_LEVEL_MAP_SPEC_BY_STEP["Pri_trackPVPass"]
    )

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml


@dataclass(frozen=True)
class StudyConfig:
    input_files: tuple[str, ...] = ()
    input_glob: str | None = None
    tree_path: str = "mkcands/X_data"
    config_tree_path: str = "mkcands/X_config"
    cache_dir: Path = Path(
        "/eos/user/c/chiw/JpsiJpsiPhi/MC_samples/Ntuple_refactor/TPS-JpsiJpsiPhi/_vertex_truth_cache"
    )
    use_cache: bool = True
    overwrite_cache: bool = False
    show_file_progress: bool = True
    show_event_progress: bool = False
    progress_backend: str = "notebook"
    phi_vtxprob_scan: tuple[float, ...] = (
        0.0,
        1e-5,
        3e-5,
        1e-4,
        3e-4,
        1e-3,
        3e-3,
        1e-2,
        3e-2,
        1e-1,
    )


@dataclass(frozen=True)
class OfflineSelectionConfig:
    mu_pt_barrel_min: float = 3.5
    mu_pt_endcap_min: float = 2.5
    mu_abs_eta_max: float = 2.4
    track_pt_min: float = 2.0
    track_abs_eta_max: float = 2.5
    kaon_chi2_max: float = 8.0
    kaon_n_valid_hits_min: int = 4
    kaon_require_highpurity: bool = True
    jpsi_mass_window: tuple[float, float] = (2.9, 3.3)
    jpsi_pt_min: float = 6.0
    jpsi_abs_y_max: float = 2.5
    jpsi_vtxprob_min: float = 0.01
    ups_mass_window: tuple[float, float] = (8.0, 12.0)
    ups_pt_min: float = 6.0
    ups_abs_y_max: float = 2.5
    ups_vtxprob_min: float | None = None
    phi_mass_window: tuple[float, float] = (0.99, 1.07)
    phi_pt_min: float = 4.0
    phi_abs_y_max: float = 2.4
    phi_vtxprob_min: float = 0.01


@dataclass(frozen=True)
class TriggerRequirement:
    key: str
    path_pattern: str
    filter_label: str
    rule: Literal["dimuon_pair", "three_muons_with_dimuon_pair"]


@dataclass(frozen=True)
class EfficiencyDefinitionConfig:
    """Resolved, serialisable physics definition used by efficiency workers."""

    schema_version: str
    analysis_mode: str
    offline_selection: OfflineSelectionConfig
    trigger_requirements: tuple[TriggerRequirement, ...]
    event_endpoint: str
    dionia_vtxprob_diagnostic_min: float
    binning: dict[str, tuple[float, ...]]
    source: str = "built-in"
    config_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["trigger_requirements"] = [asdict(item) for item in self.trigger_requirements]
        payload["binning"] = {key: list(value) for key, value in self.binning.items()}
        return payload


DEFAULT_TRIGGER_REQUIREMENTS = (
    TriggerRequirement("dimuon0", "HLT_Dimuon0_Jpsi3p5_Muon2_v", "hltJpsiMuonL3Filtered3p5", "three_muons_with_dimuon_pair"),
    TriggerRequirement("doublemu", "HLT_DoubleMu4_3_LowMass_v", "hltDoubleMu43LowMassL3Filtered", "dimuon_pair"),
)


DEFAULT_EFFICIENCY_BINNING: dict[str, tuple[float, ...]] = {
    "jpsi_pt_edges": (6.0, 10.0, 15.0, 20.0, 30.0, 50.0, 100.0),
    "phi_pt_edges": (4.0, 6.0, 10.0, 20.0, 50.0),
    "object_abs_y_edges": (0.0, 0.6, 1.2, 1.8, 2.4),
    "object_y_edges": (-2.4, -1.8, -1.2, -0.6, 0.0, 0.6, 1.2, 1.8, 2.4),
    "triple_pt_edges": (0.0, 10.0, 20.0, 30.0, 50.0, 100.0, 200.0),
    "triple_abs_y_edges": (0.0, 0.6, 1.2, 1.8, 2.4),
    "triple_mass_edges": (0.0, 10.0, 15.0, 20.0, 30.0, 50.0, 100.0),
}


def _definition_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def efficiency_definition_from_dict(payload: dict[str, Any], *, source: str = "inline") -> EfficiencyDefinitionConfig:
    if payload.get("schema_version") != "ntuple-analyzer-efficiency/v1":
        raise ValueError("Efficiency configuration schema_version must be 'ntuple-analyzer-efficiency/v1'.")
    if payload.get("analysis_mode", "JpsiJpsiPhi") != "JpsiJpsiPhi":
        raise ValueError("Only analysis_mode=JpsiJpsiPhi is supported by the efficiency workflow.")

    selection_payload = payload.get("offline_selection", {})
    allowed_selection = {item.name for item in fields(OfflineSelectionConfig)}
    unknown_selection = sorted(set(selection_payload) - allowed_selection)
    if unknown_selection:
        raise ValueError(f"Unknown offline_selection field(s): {', '.join(unknown_selection)}")
    selection_values = {**asdict(OfflineSelectionConfig()), **selection_payload}
    for key in ("jpsi_mass_window", "ups_mass_window", "phi_mass_window"):
        selection_values[key] = tuple(selection_values[key])
    offline = OfflineSelectionConfig(**selection_values)

    raw_requirements = payload.get("trigger_requirements", [asdict(item) for item in DEFAULT_TRIGGER_REQUIREMENTS])
    requirements = tuple(TriggerRequirement(**item) for item in raw_requirements)
    if not requirements or len({item.key for item in requirements}) != len(requirements):
        raise ValueError("trigger_requirements must contain at least one uniquely named requirement.")
    valid_rules = {"dimuon_pair", "three_muons_with_dimuon_pair"}
    invalid_rules = sorted({item.rule for item in requirements} - valid_rules)
    if invalid_rules:
        raise ValueError(f"Unsupported trigger matching rule(s): {', '.join(invalid_rules)}")

    event_endpoint = str(payload.get("event_endpoint", "Pri_assocPVPass"))
    if event_endpoint not in {"Pri_fitValid", "Pri_fitPass", "Pri_assocPVPass", "Pri_trackPVPass"}:
        raise ValueError(f"Unsupported event_endpoint: {event_endpoint!r}")

    raw_binning = {**{key: list(value) for key, value in DEFAULT_EFFICIENCY_BINNING.items()}, **payload.get("binning", {})}
    unknown_binning = sorted(set(raw_binning) - set(DEFAULT_EFFICIENCY_BINNING))
    if unknown_binning:
        raise ValueError(f"Unknown binning field(s): {', '.join(unknown_binning)}")
    binning = {key: tuple(float(value) for value in values) for key, values in raw_binning.items()}
    for key, edges in binning.items():
        if len(edges) < 2 or any(right <= left for left, right in zip(edges, edges[1:])):
            raise ValueError(f"Binning edges for {key} must be strictly increasing.")

    normalized = {
        "schema_version": payload["schema_version"],
        "analysis_mode": payload.get("analysis_mode", "JpsiJpsiPhi"),
        "offline_selection": asdict(offline),
        "trigger_requirements": [asdict(item) for item in requirements],
        "event_endpoint": event_endpoint,
        "dionia_vtxprob_diagnostic_min": float(payload.get("dionia_vtxprob_diagnostic_min", 0.005)),
        "binning": {key: list(values) for key, values in binning.items()},
    }
    return EfficiencyDefinitionConfig(
        schema_version=normalized["schema_version"], analysis_mode=normalized["analysis_mode"],
        offline_selection=offline, trigger_requirements=requirements, event_endpoint=event_endpoint,
        dionia_vtxprob_diagnostic_min=normalized["dionia_vtxprob_diagnostic_min"], binning=binning,
        source=source, config_hash=_definition_hash(normalized),
    )


def default_efficiency_definition() -> EfficiencyDefinitionConfig:
    return efficiency_definition_from_dict({"schema_version": "ntuple-analyzer-efficiency/v1"}, source="built-in")


def load_efficiency_definition(path: str | Path | None) -> EfficiencyDefinitionConfig:
    if path is None:
        return default_efficiency_definition()
    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Efficiency configuration must contain a YAML mapping: {config_path}")
    return efficiency_definition_from_dict(payload, source=str(config_path.resolve()))


@dataclass(frozen=True)
class MassStudyConfig:
    analysis_mode: str
    active_windows: dict[str, tuple[float, float]]
    selector_name: str = "all6_same_recVtx"
    selectors: tuple[str, ...] = ("all6_same_recVtx", "Pri_fitValid")
    best_candidate_metric: str = "triple_pt2_sum"
    fit_branches: tuple[str, ...] = ("Jpsi_1_mass", "Jpsi_2_mass", "Phi_mass")


@dataclass(frozen=True)
class CmsPlotStyleConfig:
    caption: str | None = None
    energy_tev: float = 13.6
    lumi_fb: float | None = None
    era: str | None = "Run 3"
    subprocess_label: str | None = None
    is_data: bool = True


def resolve_windows(
    defaults: dict[str, tuple[float, float]],
    overrides: dict[str, tuple[float, float] | None] | None,
) -> dict[str, tuple[float, float]]:
    active: dict[str, tuple[float, float]] = {}
    overrides = overrides or {}
    for key, default_window in defaults.items():
        override = overrides.get(key)
        active[key] = default_window if override is None else tuple(map(float, override))
    return active


def default_mass_windows_from_config_row(config_row: dict[str, Any]) -> dict[str, tuple[float, float]]:
    return {
        "Jpsi_1_mass": (float(config_row["JpsiMassMin"]), float(config_row["JpsiMassMax"])),
        "Jpsi_2_mass": (float(config_row["JpsiMassMin"]), float(config_row["JpsiMassMax"])),
        "Ups_mass": (float(config_row["UpsMassMin"]), float(config_row["UpsMassMax"])),
        "Phi_mass": (float(config_row["PhiMassMin"]), float(config_row["PhiMassMax"])),
        "Pri_mass": (0.0, 100.0),
    }

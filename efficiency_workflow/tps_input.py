"""Shared TPS ROOT layout, production-configuration, and trigger resolution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import awkward as ak
import uproot

from .config import EfficiencyDefinitionConfig, TriggerRequirement
from .io import stable_data_hash


TPS_RUN_B_REQUIRED_BRANCHES = {
    "evtNum", "runNum", "lumiNum",
    "MC_GenPart_pdgId", "MC_GenPart_motherGenIdx", "MC_GenPart_pt",
    "MC_GenPart_eta", "MC_GenPart_phi", "MC_GenPart_mass",
    "muGenMatchIdx", "muIsPatSoftMuon",
    "SingleJpsi_mass", "SingleJpsi_pt", "SingleJpsi_px", "SingleJpsi_py",
    "SingleJpsi_pz", "SingleJpsi_VtxProb", "SingleJpsi_fitValid",
    "SingleJpsi_fitPass", "SingleJpsi_mu1_Idx", "SingleJpsi_mu2_Idx",
    "SingleJpsi_mu1_genMatchIdx", "SingleJpsi_mu2_genMatchIdx",
    "SinglePhi_mass", "SinglePhi_pt", "SinglePhi_px", "SinglePhi_py",
    "SinglePhi_pz", "SinglePhi_VtxProb", "SinglePhi_fitValid",
    "SinglePhi_fitPass", "SinglePhi_K1_RecoKaonTrackIdx",
    "SinglePhi_K2_RecoKaonTrackIdx", "SinglePhi_K1_genMatchIdx",
    "SinglePhi_K2_genMatchIdx", "RecoKaonTrack_pt", "RecoKaonTrack_eta",
    "RecoKaonTrack_genMatchIdx", "RecoKaonTrack_normalizedChi2",
    "RecoKaonTrack_numberOfHits", "RecoKaonTrack_isHighPurity",
    "Jpsi_1_mass", "Jpsi_1_mu_1_Idx", "Jpsi_1_mu_2_Idx",
    "Jpsi_2_mu_1_Idx", "Jpsi_2_mu_2_Idx",
    "Phi_K_1_genMatchIdx", "Phi_K_2_genMatchIdx",
    "TrigNames", "TrigRes", "MatchJpsiTriggerNames",
    "muJpsiMatchedTriggerIndices", "muJpsiMatchedFilterIndices",
    "DiOnia_fitValid", "DiOnia_fitPass", "DiOnia_commonRecVtxPass",
    "DiOnia_passAny", "DiOnia_VtxProb",
    "Pri_fitValid", "Pri_fitPass", "Pri_assocPVPass", "Pri_trackPVPass", "Pri_passAny",
}

EFFICIENCY_RELEVANT_PRODUCTION_FIELDS = (
    "AnalysisMode",
    "RequireAcceptedCandidatesForMonteCarloTree",
    "KeepAllSingleObjectCandsInMC",
    "SkipCompositeCandBuildingWhenKeepingSingles",
    "MuonSelection",
    "TrackSelection",
    "TrackQuality",
    "RequireRecoKaonTrackHighPurity",
    "JpsiMassMin", "JpsiMassMax", "PhiMassMin", "PhiMassMax", "TrackPtMin",
    "JpsiDecayVtxProbCut", "PhiDecayVtxProbCut", "DiOniaVtxProbCut", "PriVtxProbCut",
    "DoJpsiDecayVtxFit", "DoPhiDecayVtxFit", "DoDiOniaVtxFit", "DoPriVtxFit",
    "TriggersForJpsi", "FiltersForJpsi",
    "RecoGenMuonMatchChi2Max", "RecoGenKaonMatchChi2Max",
)


@dataclass(frozen=True)
class ResolvedTriggerRequirement:
    key: str
    path_pattern: str
    filter_label: str
    rule: str
    trigger_index: int
    filter_index: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedInputContext:
    data_tree_path: str
    config_tree_path: str
    source_entries: int
    production_config: dict[str, Any]
    production_config_hash: str
    compatibility_hash: str
    trigger_requirements: tuple[ResolvedTriggerRequirement, ...]
    warnings: tuple[str, ...]

    @property
    def trigger_filter_map(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for item in self.trigger_requirements:
            result[f"{item.key}_trig"] = item.trigger_index
            result[f"{item.key}_filt"] = item.filter_index
        return result

    def to_metadata(self) -> dict[str, Any]:
        return {
            "data_tree_path": self.data_tree_path,
            "config_tree_path": self.config_tree_path,
            "source_entries": self.source_entries,
            "production_config": self.production_config,
            "production_config_hash": self.production_config_hash,
            "compatibility_hash": self.compatibility_hash,
            "trigger_requirements": [item.to_dict() for item in self.trigger_requirements],
            "trigger_filter_map": self.trigger_filter_map,
            "warnings": list(self.warnings),
        }


def detect_tree_path(root_file: uproot.ReadOnlyDirectory, requested: str = "auto") -> str:
    if requested != "auto":
        if requested not in root_file:
            raise KeyError(f"Missing requested tree {requested!r}")
        return requested
    found = [candidate for candidate in ("X_data", "mkcands/X_data") if candidate in root_file]
    if len(found) != 1:
        raise KeyError(f"Expected exactly one X_data layout, found {found or 'none'}")
    return found[0]


def sibling_config_tree_path(data_tree_path: str) -> str:
    directory = data_tree_path.rsplit("/", 1)[0] if "/" in data_tree_path else ""
    return f"{directory}/X_config" if directory else "X_config"


def read_config_snapshot(root_file: uproot.ReadOnlyDirectory, config_tree_path: str) -> dict[str, Any]:
    if config_tree_path not in root_file:
        raise KeyError(f"Missing configuration tree {config_tree_path!r}")
    tree = root_file[config_tree_path]
    if int(tree.num_entries) < 1:
        raise ValueError(f"Configuration tree {config_tree_path!r} is empty")
    snapshot: dict[str, Any] = {}
    for name in tree.keys():
        values = ak.to_list(tree[name].array(entry_start=0, entry_stop=1, library="ak"))
        snapshot[name] = values[0] if values else None
    return snapshot


def _unique_index(values: list[Any], pattern: str, kind: str, key: str) -> int:
    matches = [index for index, value in enumerate(values) if pattern in str(value)]
    if len(matches) != 1:
        raise ValueError(
            f"Trigger requirement {key!r} expected exactly one {kind} matching {pattern!r}, found {len(matches)}"
        )
    return matches[0]


def resolve_trigger_requirements(
    production_config: dict[str, Any],
    requirements: tuple[TriggerRequirement, ...],
) -> tuple[ResolvedTriggerRequirement, ...]:
    triggers = list(production_config.get("TriggersForJpsi") or [])
    filters = list(production_config.get("FiltersForJpsi") or [])
    return tuple(
        ResolvedTriggerRequirement(
            key=item.key,
            path_pattern=item.path_pattern,
            filter_label=item.filter_label,
            rule=item.rule,
            trigger_index=_unique_index(triggers, item.path_pattern, "trigger", item.key),
            filter_index=_unique_index(filters, item.filter_label, "filter", item.key),
        )
        for item in requirements
    )


def _require_flag(config: dict[str, Any], name: str, expected: bool) -> None:
    if name not in config:
        raise KeyError(f"X_config is missing required field {name!r}")
    if bool(config[name]) is not expected:
        raise ValueError(f"X_config field {name}={config[name]!r}; expected {expected!r}")


def validate_production_config(
    config: dict[str, Any],
    definition: EfficiencyDefinitionConfig,
) -> list[str]:
    _require_flag(config, "KeepAllSingleObjectCandsInMC", True)
    _require_flag(config, "SkipCompositeCandBuildingWhenKeepingSingles", False)
    _require_flag(config, "RequireAcceptedCandidatesForMonteCarloTree", False)

    selection = definition.offline_selection
    comparisons = (
        ("JpsiMassMin", float(config.get("JpsiMassMin", float("nan"))) <= selection.jpsi_mass_window[0],
         "production J/psi lower mass cut is tighter than the analysis window"),
        ("JpsiMassMax", float(config.get("JpsiMassMax", float("nan"))) >= selection.jpsi_mass_window[1],
         "production J/psi upper mass cut is tighter than the analysis window"),
        ("PhiMassMin", float(config.get("PhiMassMin", float("nan"))) <= selection.phi_mass_window[0],
         "production phi lower mass cut is tighter than the analysis window"),
        ("PhiMassMax", float(config.get("PhiMassMax", float("nan"))) >= selection.phi_mass_window[1],
         "production phi upper mass cut is tighter than the analysis window"),
        ("TrackPtMin", float(config.get("TrackPtMin", float("nan"))) <= selection.track_pt_min,
         "production track pT cut is tighter than the analysis threshold"),
    )
    for field, valid, message in comparisons:
        if field not in config:
            raise KeyError(f"X_config is missing numeric compatibility field {field!r}")
        if not valid:
            raise ValueError(f"{message}: {field}={config[field]!r}")

    warnings: list[str] = []
    if str(config.get("AnalysisMode", "")) not in {"JpsiJpsiPhi", "JJP"}:
        warnings.append(f"Unexpected AnalysisMode={config.get('AnalysisMode')!r}")
    return warnings


def resolve_input_context(
    root_file: uproot.ReadOnlyDirectory,
    requested_tree_path: str,
    definition: EfficiencyDefinitionConfig,
    *,
    strict: bool = True,
) -> ResolvedInputContext:
    data_tree_path = detect_tree_path(root_file, requested_tree_path)
    tree = root_file[data_tree_path]
    config_tree_path = sibling_config_tree_path(data_tree_path)
    warnings: list[str] = []
    try:
        production_config = read_config_snapshot(root_file, config_tree_path)
        warnings.extend(validate_production_config(production_config, definition))
        trigger_requirements = resolve_trigger_requirements(production_config, definition.trigger_requirements)
    except (KeyError, ValueError) as exc:
        if strict:
            raise
        production_config = (
            read_config_snapshot(root_file, config_tree_path)
            if config_tree_path in root_file and int(root_file[config_tree_path].num_entries) > 0
            else {}
        )
        trigger_requirements = ()
        warnings.append(f"legacy-config-policy: {exc}")

    missing = sorted(TPS_RUN_B_REQUIRED_BRANCHES - set(tree.keys()))
    if missing:
        message = f"TPS Run-B tree is missing required branches: {', '.join(missing)}"
        if strict:
            raise KeyError(message)
        warnings.append(message)

    relevant = {key: production_config.get(key) for key in EFFICIENCY_RELEVANT_PRODUCTION_FIELDS}
    return ResolvedInputContext(
        data_tree_path=data_tree_path,
        config_tree_path=config_tree_path,
        source_entries=int(tree.num_entries),
        production_config=production_config,
        production_config_hash=stable_data_hash(production_config),
        compatibility_hash=stable_data_hash(relevant),
        trigger_requirements=trigger_requirements,
        warnings=tuple(warnings),
    )

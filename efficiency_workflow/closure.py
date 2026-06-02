from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .corrections import FactorizedCorrectionMap, STATUS_OK
from .efficiency import _merged_gen_events


@dataclass(frozen=True)
class ClosureResult:
    label: str
    n_gen_fiducial: int
    n_reco_selected: int
    corrected_sum: float
    ratio: float
    n_failed_lookup: int

    def to_dict(self) -> dict:
        return asdict(self)


def _corrected_sum(
    frame: pd.DataFrame,
    correction_map: FactorizedCorrectionMap,
    *,
    selected_col: str,
) -> tuple[float, int, int]:
    selected = frame.loc[frame[selected_col].astype(bool)].copy()
    total = 0.0
    failed = 0
    for row in selected.itertuples(index=False):
        correction = correction_map.lookup(
            jpsi1_pt=float(getattr(row, "jpsi_lead_pt")),
            jpsi1_y=float(getattr(row, "jpsi_lead_y")),
            jpsi2_pt=float(getattr(row, "jpsi_sublead_pt")),
            jpsi2_y=float(getattr(row, "jpsi_sublead_y")),
            phi_pt=float(getattr(row, "phi_pt")),
            phi_y=float(getattr(row, "phi_y")),
        )
        if correction.status == STATUS_OK:
            total += correction.weight
        else:
            failed += 1
    return total, int(len(selected)), failed


def self_closure_test(
    sample: str,
    correction_map: FactorizedCorrectionMap,
    gen_df: pd.DataFrame,
    event_df: pd.DataFrame,
    *,
    selected_col: str = "Pri_assocPVPass",
) -> ClosureResult:
    merged = _merged_gen_events(gen_df, event_df)
    corrected, n_selected, failed = _corrected_sum(merged, correction_map, selected_col=selected_col)
    n_gen = int(merged["full_gen"].sum()) if "full_gen" in merged.columns else int(len(merged))
    ratio = float(corrected / n_gen) if n_gen > 0 else math.nan
    return ClosureResult(sample, n_gen, n_selected, corrected, ratio, failed)


def cross_closure_test(
    label: str,
    correction_map: FactorizedCorrectionMap,
    gen_df: pd.DataFrame,
    event_df: pd.DataFrame,
    *,
    selected_col: str = "Pri_assocPVPass",
) -> ClosureResult:
    return self_closure_test(label, correction_map, gen_df, event_df, selected_col=selected_col)


def factorization_closure_test(
    *,
    direct_efficiency: float,
    factorized_efficiency: float,
    label: str = "factorization",
) -> dict:
    ratio = float(direct_efficiency / factorized_efficiency) if factorized_efficiency > 0.0 else math.nan
    return {
        "label": label,
        "direct_efficiency": float(direct_efficiency),
        "factorized_efficiency": float(factorized_efficiency),
        "ratio": ratio,
        "deviation_from_unity": float(abs(ratio - 1.0)) if np.isfinite(ratio) else math.nan,
    }

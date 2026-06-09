from __future__ import annotations

from collections import OrderedDict

import pytest

from fit_splot import build_splot_weight_map


class _FakeRow:
    def __init__(self, values: dict[str, float]) -> None:
        self._values = values

    def getRealValue(self, name: str) -> float:
        return self._values[name]


class _FakeData:
    def __init__(self, rows: list[dict[str, float]]) -> None:
        self._rows = [_FakeRow(row) for row in rows]

    def numEntries(self) -> int:
        return len(self._rows)

    def get(self, idx: int) -> _FakeRow:
        return self._rows[idx]


def test_signal_effcorr_sw_multiplies_signal_sweight_by_correction() -> None:
    data = _FakeData(
        [
            {"yield_sss_sw": 0.25, "yield_bbb_sw": 0.75},
            {"yield_sss_sw": 0.50, "yield_bbb_sw": 0.50},
        ]
    )
    yields = OrderedDict([("yield_sss", object()), ("yield_bbb", object())])

    weights = build_splot_weight_map(data, yields, "yield_sss", [4.0, 2.0])

    assert weights["signal_sw"] == [0.25, 0.50]
    assert weights["signal_effcorr_sw"] == [1.0, 1.0]


def test_signal_effcorr_sw_rejects_length_mismatch() -> None:
    data = _FakeData([{"yield_sss_sw": 0.25}])
    yields = OrderedDict([("yield_sss", object())])

    with pytest.raises(RuntimeError, match="Correction weight length mismatch"):
        build_splot_weight_map(data, yields, "yield_sss", [])

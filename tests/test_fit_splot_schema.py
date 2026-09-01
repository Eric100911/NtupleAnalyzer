from __future__ import annotations

from collections import OrderedDict

import pytest
import ROOT

from scripts.kinematics.fit_splot import build_splot_weight_map, save_projection_plots


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


def test_projection_plot_resolves_named_rooplot_objects(tmp_path) -> None:
    mass = ROOT.RooRealVar("test_mass", "test mass", 0.0, 10.0)
    mean = ROOT.RooRealVar("test_mean", "test mean", 5.0)
    sigma = ROOT.RooRealVar("test_sigma", "test sigma", 1.0, 0.1, 5.0)
    signal = ROOT.RooGaussian("pdf_signal", "signal", mass, mean, sigma)
    background = ROOT.RooPolynomial("pdf_background", "background", mass)
    signal_yield = ROOT.RooRealVar("yield_signal", "signal yield", 2.0)
    background_yield = ROOT.RooRealVar("yield_background", "background yield", 1.0)
    model = ROOT.RooAddPdf(
        "test_model",
        "test model",
        ROOT.RooArgList(signal, background),
        ROOT.RooArgList(signal_yield, background_yield),
    )
    data = ROOT.RooDataSet("test_data", "test data", ROOT.RooArgSet(mass))
    for value in (4.5, 5.0, 7.5):
        mass.setVal(value)
        data.add(ROOT.RooArgSet(mass))

    save_projection_plots(
        "JJP",
        str(tmp_path),
        data,
        model,
        OrderedDict((("test_mass", mass),)),
        "yield_signal",
        OrderedDict((("yield_signal", signal_yield), ("yield_background", background_yield))),
        dataset="mc",
    )

    assert (tmp_path / "test_mass_fit.pdf").is_file()
    assert (tmp_path / "test_mass_fit.png").is_file()

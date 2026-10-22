from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "efficiency" / "plot_validation.py"
SPEC = importlib.util.spec_from_file_location("plot_validation", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
plot_validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plot_validation)


def test_parse_plots_all_expands_seven_types() -> None:
    assert plot_validation.parse_plots(["all"]) == list(plot_validation.PLOTS)
    assert len(plot_validation.parse_plots(["all"])) == 7


def test_parse_plots_splits_commas_and_deduplicates_in_order() -> None:
    assert plot_validation.parse_plots(["closure, stepwise", "closure", "phi-gen"]) == [
        "closure", "stepwise", "phi-gen"
    ]


def test_parse_plots_rejects_unknown_categories() -> None:
    with pytest.raises(ValueError, match="Unknown plot type: nope"):
        plot_validation.parse_plots(["stepwise,nope"])


def test_incomplete_stepwise_manifest_is_invalidated(tmp_path: Path) -> None:
    aggregate = tmp_path / "derived_manifest.json"
    aggregate.write_text("{}")
    for sample in plot_validation.SAMPLES:
        derived = tmp_path / sample / "derived"
        derived.mkdir(parents=True)
        (derived / "manifest.json").write_text(json.dumps({
            "outputs": {"derived_plots": {"one": "plots/conditional/one.png"}}
        }))
        (derived / "plots/conditional").mkdir(parents=True)
        (derived / "plots/conditional/one.png").touch()
    plot_validation.invalidate_incomplete_stepwise(tmp_path)
    assert aggregate.exists()
    (tmp_path / plot_validation.SAMPLES[0] / "derived/plots/conditional/one.png").unlink()
    plot_validation.invalidate_incomplete_stepwise(tmp_path)
    assert not aggregate.exists()


@pytest.mark.parametrize(
    ("switch", "mode", "make_flag"),
    [
        ("--with-cumulative-plots", "cumulative", "--with-cumulative-plots"),
        ("--with-uncertainty-plots", "uncertainty", "--with-uncertainty-plots"),
    ],
)
def test_main_maps_legacy_switch_to_make_mode_and_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    switch: str,
    mode: str,
    make_flag: str,
) -> None:
    output = tmp_path / "plots"
    captured: list[str] = []

    def fake_run(command: list[str], *, check: bool) -> None:
        assert check is True
        captured.extend(command)
        output_arg = next(arg for arg in command if arg.startswith("OUTPUT_DIR="))
        command_output = Path(output_arg.split("=", 1)[1])
        mode_arg = next(arg for arg in command if arg.startswith("PLOT_MODE="))
        command_mode = mode_arg.split("=", 1)[1]
        (command_output / "stepwise" / command_mode).mkdir(parents=True, exist_ok=True)
        (command_output / "stepwise" / command_mode / "derived_manifest.json").touch()

    monkeypatch.setattr(plot_validation.subprocess, "run", fake_run)
    assert plot_validation.main(["--plots", "stepwise", "--output-dir", str(output), switch]) == 0

    assert f"PLOT_MODE={mode}" in captured
    assert f"PLOT_FLAGS={make_flag}" in captured
    manifest = json.loads((output / "validation_manifest.json").read_text())
    assert manifest["mode"] == mode
    assert manifest["plots"] == ["stepwise"]

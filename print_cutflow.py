#!/usr/bin/env python3
"""Print formatted cutflow tables from merged efficiency output.

Reads event_step_flags.parquet for each subprocess sample and prints
per-object + event-level cutflow tables with conditional and absolute
efficiencies, following the convention:

  - Per-object chains are self-contained: each chain resets the conditional
    denominator to the total number of events, so the first step (fiducial)
    shows the object acceptance as both conditional and absolute.
  - Subsequent per-object steps are sequential within each object.
  - Event-level: s_cand -> hlt_event -> hlt_muon_matched -> four_muon_vtx
    (sequential), then Pri_fitValid / Pri_fitPass / Pri_assocPVPass /
    Pri_trackPVPass in parallel (each conditional on four_muon_vtx).

Usage:
    source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc14-opt/setup.sh
    python3 print_cutflow.py --input-dir <merged_output_dir> [--sample SAMPLE] [--format table|latex|csv]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from scipy.stats import beta

# ---------------------------------------------------------------------------
# Step definitions — mirror efficiency_workflow/efficiency.py constants
# ---------------------------------------------------------------------------

PER_JPSI_STEPS: list[tuple[str, str]] = [
    ("fiducial", r"$\epsilon_{\mathrm{fiducial}}$ (acceptance)"),
    ("muonRECO", r"$\epsilon_{\mu\mathrm{RECO}}$ (muon reco)"),
    ("muonID", r"$\epsilon_{\mu\mathrm{ID}}$ (muon ID)"),
    ("dimuon", r"$\epsilon_{\mu\mu}$ (dimuon)"),
]

PER_PHI_STEPS: list[tuple[str, str]] = [
    ("fiducial", r"$\epsilon_{\mathrm{fiducial}}$ (acceptance)"),
    ("kaonRECO", r"$\epsilon_{K\mathrm{RECO}}$ (kaon reco)"),
    ("kaonID", r"$\epsilon_{K\mathrm{ID}}$ (kaon ID)"),
    ("dikaon", r"$\epsilon_{KK}$ (dikaon)"),
]

# Sequential event-level chain: s_cand -> hlt_event -> hlt_muon_matched -> four_muon_vtx
EVENT_SEQUENTIAL: list[tuple[str, str, str | None]] = [
    # (column, label, previous_column)  -- None = "total events"
    ("s_cand", r"$s_{\mathrm{cand}}$ (candidate reco)", None),
    ("hlt_event", r"$\epsilon_{\mathrm{HLT}}$ (HLT)", "s_cand"),
    ("hlt_muon_matched", r"$\epsilon_{\mathrm{HLT}\,\mu\mathrm{-matched}}$", "hlt_event"),
    ("four_muon_vtx", r"$\epsilon_{4\mu\mathrm{vtx}}$ (4-muon vertex)", "hlt_muon_matched"),
]

# Parallel diagnostics: all conditional on four_muon_vtx
EVENT_PARALLEL: list[tuple[str, str]] = [
    ("Pri_fitValid", r"$\epsilon_{\mathrm{fitValid}}$ (primary fit valid)"),
    ("Pri_fitPass", r"$\epsilon_{\mathrm{fitPass}}$ (primary fit pass)"),
    ("Pri_assocPVPass", r"$\epsilon_{\mathrm{assocPV}}$ (assoc PV)"),
    ("Pri_trackPVPass", r"$\epsilon_{\mathrm{trackPV}}$ (track PV)"),
]

# Section headers
OBJECT_SECTIONS = {
    "jpsi_lead": r"Leading $J/\psi$",
    "jpsi_sublead": r"Subleading $J/\psi$",
    "phi": r"$\phi$",
}


# ---------------------------------------------------------------------------
# Cutflow builder
# ---------------------------------------------------------------------------

def clopper_pearson_interval(
    total: int, passed: int, confidence: float = 0.682689492
) -> tuple[float, float]:
    """Clopper-Pearson interval for binomial efficiency."""
    if total <= 0:
        return math.nan, math.nan
    alpha = 1.0 - confidence
    low = 0.0 if passed <= 0 else float(beta.ppf(alpha / 2.0, passed, total - passed + 1))
    high = 1.0 if passed >= total else float(beta.ppf(1.0 - alpha / 2.0, passed + 1, total - passed))
    return low, high


def _make_row(
    section: str,
    step: str,
    label: str,
    total: int,
    passed: int,
    n_total: int,
) -> dict[str, Any]:
    """Build one cutflow row dict."""
    cond_eff = passed / total if total > 0 else float("nan")
    abs_eff = passed / n_total if n_total > 0 else float("nan")

    cond_low, cond_high = clopper_pearson_interval(total, passed)
    abs_low, abs_high = clopper_pearson_interval(n_total, passed)

    return {
        "section": section,
        "step": step,
        "label": label,
        "total": total,
        "passed": passed,
        "cond_eff": cond_eff,
        "cond_err_low": cond_eff - cond_low,
        "cond_err_high": cond_high - cond_eff,
        "abs_eff": abs_eff,
        "abs_err_low": abs_eff - abs_low,
        "abs_err_high": abs_high - abs_eff,
    }


def build_cutflow_rows(event_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Build cutflow rows from event_step_flags DataFrame.

    Returns a list of dicts with keys:
      section, step, label, total, passed, cond_eff, cond_err_low,
      cond_err_high, abs_eff, abs_err_low, abs_err_high
    """
    n_total = int(event_df["full_gen"].sum()) if "full_gen" in event_df.columns else len(event_df)
    if n_total == 0:
        return []

    def _col(obj: str, step: str) -> str:
        return f"{obj}_{step}"

    def _passed(col: str) -> int:
        return int(event_df[col].sum()) if col in event_df.columns else 0

    rows: list[dict[str, Any]] = []

    # --- Per-object chains: jpsi_lead, jpsi_sublead, phi ---
    for obj_prefix, steps in [
        ("jpsi_lead", PER_JPSI_STEPS),
        ("jpsi_sublead", PER_JPSI_STEPS),
        ("phi", PER_PHI_STEPS),
    ]:
        section = OBJECT_SECTIONS[obj_prefix]
        prev = n_total
        for step_col, step_label in steps:
            col = _col(obj_prefix, step_col)
            passed = _passed(col)

            rows.append(_make_row(section, step_col, step_label, prev, passed, n_total))
            prev = passed

    # --- Event-level: sequential chain ---
    prev = n_total
    for step_col, step_label, _prev_col in EVENT_SEQUENTIAL:
        passed = _passed(step_col)
        rows.append(_make_row("Event-level", step_col, step_label, prev, passed, n_total))
        prev = passed

    # --- Event-level: parallel Pri_* diagnostics ---
    four_mu_passed = _passed("four_muon_vtx")
    for step_col, step_label in EVENT_PARALLEL:
        passed = _passed(step_col)
        rows.append(_make_row("Event-level", step_col, step_label, four_mu_passed, passed, n_total))

    return rows


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _eff_pct(val: float) -> str:
    """Format efficiency as percentage."""
    if math.isnan(val):
        return "   nan"
    return f"{val * 100:6.2f}"


def _print_latex_table(sample_name: str, rows: list[dict[str, Any]]) -> None:
    """Print LaTeX tabular."""
    print(r"\begin{table}[htbp]")
    print(r"  \centering")
    print(f"  \\caption{{{sample_name} cutflow.}}")
    print(f"  \\label{{tab:cutflow-{sample_name.lower()}}}")
    print(r"  \small")
    print(r"  \begin{tabular}{lcc}")
    print(r"    \toprule")
    print(r"    Step & Conditional eff. (\%) & Cumulative eff. (\%) \\")
    print(r"    \midrule")

    current_section: str | None = None
    for i, row in enumerate(rows):
        if row["section"] != current_section:
            current_section = row["section"]
            if i > 0:
                print(r"    \midrule")
            print(f"    \\multicolumn{{3}}{{c}}{{\\textit{{{current_section}}}}} \\\\")

        cond_str = f"{row['cond_eff'] * 100:.1f}"
        abs_str = f"{row['abs_eff'] * 100:.2f}"
        print(f"    {row['label']} & {cond_str} & {abs_str} \\\\")

    print(r"    \bottomrule")
    print(r"  \end{tabular}")
    print(r"\end{table}")


def _print_table(sample_name: str, rows: list[dict[str, Any]]) -> None:
    """Print plain-text table."""
    print()
    print(f"  {sample_name}")
    print("=" * 79)

    current_section: str | None = None
    for i, row in enumerate(rows):
        if row["section"] != current_section:
            current_section = row["section"]
            if i > 0:
                print(f"  {'':─^77s}")
            print(f"  ──  {current_section}  ──")
            print(f"  {'Step':<38s} {'CondEff':>8s} {'AbsEff':>8s}  {'passed / total':>16s}")
            print("-" * 79)

        cond = _eff_pct(row["cond_eff"])
        abs_ = _eff_pct(row["abs_eff"])
        ratio = f"{row['passed']:,} / {row['total']:,}"
        print(f"  {row['label']:<38s} {cond}% {abs_}%  {ratio:>16s}")


def _print_csv(sample_name: str, rows: list[dict[str, Any]]) -> None:
    """Print CSV output."""
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "sample", "section", "step", "total", "passed",
        "cond_eff", "cond_err_low", "cond_err_high",
        "abs_eff", "abs_err_low", "abs_err_high",
    ])
    for row in rows:
        w.writerow([
            sample_name, row["section"], row["step"], row["total"], row["passed"],
            row["cond_eff"], row["cond_err_low"], row["cond_err_high"],
            row["abs_eff"], row["abs_err_low"], row["abs_err_high"],
        ])
    sys.stdout.write(buf.getvalue())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Print formatted cutflow tables from merged efficiency output."
    )
    ap.add_argument(
        "--input-dir", "-i",
        required=True,
        type=Path,
        help="Path to merged efficiency output directory (contains JJP_*/ subdirs).",
    )
    ap.add_argument(
        "--sample", "-s",
        default=None,
        help="Process only this sample (e.g. JJP_DPS1).  If omitted, all are processed.",
    )
    ap.add_argument(
        "--format", "-f",
        choices=("table", "latex", "csv"),
        default="table",
        help="Output format (default: table).",
    )
    ap.add_argument(
        "--list-samples", "-l",
        action="store_true",
        help="List available sample directories and exit.",
    )
    args = ap.parse_args()

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        print(f"error: {input_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    available = sorted(
        p.name for p in input_dir.iterdir()
        if p.is_dir() and p.name.startswith("JJP_")
    )
    if args.list_samples:
        print("Available samples:")
        for s in available:
            print(f"  {s}")
        sys.exit(0)

    if not available:
        print(f"error: no JJP_* sample directories found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    samples = [args.sample] if args.sample else available
    for sname in samples:
        if sname not in available:
            print(f"warning: sample '{sname}' not found in {input_dir}, skipping",
                  file=sys.stderr)
            continue

        sample_dir = input_dir / sname
        flags_path = sample_dir / "event_step_flags.parquet"
        if not flags_path.exists():
            print(f"warning: {flags_path} not found, skipping {sname}",
                  file=sys.stderr)
            continue

        event_df = pd.read_parquet(flags_path)
        rows = build_cutflow_rows(event_df)

        if args.format == "latex":
            _print_latex_table(sname, rows)
        elif args.format == "csv":
            _print_csv(sname, rows)
        else:
            _print_table(sname, rows)


if __name__ == "__main__":
    main()

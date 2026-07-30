#!/usr/bin/env python3
"""Audit efficiency numerator/denominator membership with branch-level event evidence."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from efficiency_workflow.audit import (
    DEFAULT_AUDIT_INPUT,
    EventKey,
    build_audit_payload,
    build_factor_summary,
    build_no_trigger_summary,
    classify_memberships,
    load_pipeline_events,
    load_selected_evidence,
    render_markdown,
    select_examples,
    summarize_memberships,
    write_root_skims,
)
from efficiency_workflow.config import OfflineSelectionConfig
from efficiency_workflow.efficiency import EfficiencyBinning


def _manifest_inputs(path: Path) -> list[str]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict) and isinstance(payload.get("source"), str):
        return [payload["source"]]
    if isinstance(payload, dict) and isinstance(payload.get("files"), list):
        return [str(item) for item in payload["files"]]
    if isinstance(payload, dict):
        result: list[str] = []
        for value in payload.values():
            if isinstance(value, list):
                result.extend(str(item) for item in value)
        if result:
            return result
    raise ValueError(f"Unsupported input manifest structure: {path}")


def _resolve_inputs(positional: list[str], manifest: Path | None) -> list[str]:
    if positional and manifest is not None:
        raise ValueError("ROOT inputs and --input-file-manifest are mutually exclusive")
    if manifest is not None:
        return _manifest_inputs(manifest)
    return positional or [str(DEFAULT_AUDIT_INPUT)]


def _extra_requested_keys(
    event_df,
    *,
    requested_events: list[str],
    requested_entries: list[int],
) -> list[EventKey]:
    result: list[EventKey] = []
    for entry in requested_entries:
        match = event_df[
            (event_df["source_file"] == event_df["source_file"].iloc[0])
            & (event_df["entry"] == entry)
        ]
        if match.empty:
            raise ValueError(f"Requested entry {entry} was not found in the first input")
        result.append(EventKey(**match.iloc[0][["source_file", "entry", "run", "lumi", "event"]].to_dict()))
    for token in requested_events:
        parts = token.split(":")
        if len(parts) != 3:
            raise ValueError(f"--event must be RUN:LUMI:EVENT, got {token!r}")
        run, lumi, event = map(int, parts)
        match = event_df[
            (event_df["run"] == run) & (event_df["lumi"] == lumi) & (event_df["event"] == event)
        ]
        if match.empty:
            raise ValueError(f"Requested event {token} was not found")
        for row in match.itertuples(index=False):
            result.append(EventKey(str(row.source_file), int(row.entry), run, lumi, event))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", help="Local ROOT paths or XRootD URLs")
    parser.add_argument("--input-file-manifest", type=Path)
    parser.add_argument("--tree-path", default="auto", help="Tree path, or auto")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--examples-per-category", type=int, default=5)
    parser.add_argument("--max-events", type=int)
    parser.add_argument("--step-size", default="100 MB")
    parser.add_argument("--event", action="append", default=[], help="Additionally inspect RUN:LUMI:EVENT")
    parser.add_argument("--entry", action="append", type=int, default=[], help="Additionally inspect an entry in the first input")
    parser.add_argument("--no-root-skim", action="store_true")
    parser.add_argument("--fail-on-issues", action="store_true")
    args = parser.parse_args()

    if args.examples_per_category <= 0:
        parser.error("--examples-per-category must be positive")
    if args.max_events is not None and args.max_events <= 0:
        parser.error("--max-events must be positive")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error(f"--output-dir must be new or empty: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    inputs = _resolve_inputs(args.inputs, args.input_file_manifest)
    cfg = OfflineSelectionConfig()
    binning = EfficiencyBinning()
    _, event_df, source_info = load_pipeline_events(
        inputs,
        cfg=cfg,
        tree_path=args.tree_path,
        max_events=args.max_events,
        step_size=args.step_size,
    )
    if event_df.empty:
        raise RuntimeError("No full-GEN events were found in the scanned inputs")

    memberships = classify_memberships(event_df)
    summary = summarize_memberships(memberships, event_df)
    factors = build_factor_summary(event_df)
    no_trigger = build_no_trigger_summary(event_df)
    selections = select_examples(memberships, args.examples_per_category)
    selected_keys = [item for values in selections.values() for item in values]
    manual_keys = _extra_requested_keys(
        event_df,
        requested_events=args.event,
        requested_entries=args.entry,
    )
    if manual_keys:
        selections["manual/requested"] = manual_keys
        selected_keys.extend(manual_keys)
    deduped = {
        (item.source_file, item.entry): item
        for item in selected_keys
    }
    evidence = load_selected_evidence(
        event_df,
        deduped.values(),
        source_info,
        cfg=cfg,
        binning=binning,
    )
    payload = build_audit_payload(
        inputs=inputs,
        event_df=event_df,
        membership_df=memberships,
        summary_df=summary,
        factor_df=factors,
        no_trigger_df=no_trigger,
        selections=selections,
        evidence=evidence,
        source_info=source_info,
        examples_per_category=args.examples_per_category,
    )
    skim_records = []
    if not args.no_root_skim:
        skim_records = write_root_skims(list(deduped.values()), source_info, args.output_dir)
    payload["root_skims"] = skim_records

    report = render_markdown(payload)
    (args.output_dir / "audit_report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    )
    (args.output_dir / "audit_report.md").write_text(report)
    (args.output_dir / "selection_manifest.json").write_text(
        json.dumps(
            {
                "inputs": inputs,
                "source_info": source_info,
                "selections": {
                    key: [asdict(item) for item in values]
                    for key, values in selections.items()
                },
                "root_skims": skim_records,
            },
            indent=2,
        )
        + "\n"
    )
    print(render_markdown(payload, include_branch_details=False))
    return 1 if args.fail_on_issues and payload["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

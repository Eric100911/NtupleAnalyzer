#!/usr/bin/env python3
"""Refit three saved central categories with phi_sigma max extended, without overwriting."""
from __future__ import annotations

import json
import argparse
import time
from pathlib import Path

import ROOT

ROOT.gROOT.SetBatch(True)
ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.WARNING)
parser = argparse.ArgumentParser()
parser.add_argument("--central-dir", required=True, type=Path)
parser.add_argument("--output-dir", required=True, type=Path)
args = parser.parse_args()
base = args.central_dir
outdir = args.output_dir
outdir.mkdir(parents=True, exist_ok=True)
labels = ["under_-0.1", "bin_-0.1_-0.03", "over_0.1"]
records = []
for label in labels:
    source = base / label / f"{label}_workspace.root"
    fin = ROOT.TFile.Open(str(source), "READ")
    ws = fin.Get("workspace")
    model = ws.pdf("model_jjp")
    data = ws.data(f"data_{label}")
    sigma = ws.var("phi_sigma")
    old_min, old_max, old_value = float(sigma.getMin()), float(sigma.getMax()), float(sigma.getVal())
    sigma.setMax(0.010)
    t0 = time.monotonic()
    result = model.fitTo(data, ROOT.RooFit.Extended(True), ROOT.RooFit.Save(True),
                         ROOT.RooFit.NumCPU(1), ROOT.RooFit.Strategy(2), ROOT.RooFit.PrintLevel(-1))
    elapsed = time.monotonic() - t0
    params = []
    for v in model.getParameters(data):
        if hasattr(v, "getVal"):
            lo = float(v.getMin()) if hasattr(v, "getMin") else None
            hi = float(v.getMax()) if hasattr(v, "getMax") else None
            val = float(v.getVal())
            params.append({"name": v.GetName(), "value": val,
                           "error": float(v.getError()) if hasattr(v, "getError") else None,
                           "min": lo, "max": hi, "constant": bool(v.isConstant()) if hasattr(v, "isConstant") else None,
                           "at_boundary": lo is not None and hi is not None and min(val-lo, hi-val) <= 1e-7})
    yields = {}
    for code in ("sss", "ssb", "sbs", "bss", "sbb", "bsb", "bbs", "bbb"):
        v = ws.var(f"yield_{code}")
        yields[v.GetName()] = {"value": float(v.getVal()), "error": float(v.getError()),
                               "min": float(v.getMin()), "max": float(v.getMax())}
    record = {"label": label, "source_workspace": str(source),
              "phi_sigma_original_min": old_min, "phi_sigma_original_max": old_max,
              "phi_sigma_initial_value": old_value, "phi_sigma_extended_max": 0.010,
              "fit": {"status": int(result.status()), "covQual": int(result.covQual()),
                      "EDM": float(result.edm()), "NLL": float(result.minNll()),
                      "num_invalid_nll": int(result.numInvalidNLL()) if hasattr(result, "numInvalidNLL") else None,
                      "elapsed_seconds": elapsed},
              "yield_sss": yields["yield_sss"], "component_yields": yields, "parameters": params}
    fout = ROOT.TFile.Open(str(outdir / f"{label}_phi_sigma_max010.root"), "RECREATE")
    ws.saveSnapshot("fit_parameters_phi_sigma_max010", model.getParameters(data), True)
    ws.Write("workspace")
    result.Write("fit_result")
    fout.Close()
    records.append(record)
    fin.Close()
    print(json.dumps(record), flush=True)
(outdir / "summary.json").write_text(json.dumps(records, indent=2) + "\n")
print(f"Wrote {outdir / 'summary.json'}", flush=True)

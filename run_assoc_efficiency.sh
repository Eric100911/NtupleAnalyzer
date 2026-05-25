#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OUTPUT_DIR="/eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/efficiency"
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/chiw/mplconfig_ntuple_analyzer}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/chiw/pycache_ntuple_analyzer}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/chiw/xdg_cache_ntuple_analyzer}"
export X509_USER_PROXY="${X509_USER_PROXY:-$HOME/condor/x509up}"

python3 run_efficiency.py \
  --analysis-mode JpsiJpsiPhi \
  --output-dir "$OUTPUT_DIR" \
  "$@"

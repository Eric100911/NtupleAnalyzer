#!/bin/bash
set -euo pipefail

CMSSW_BASE="/eos/home-x/xcheng/CMSSW_15_0_15"
CMSSW_SRC="${CMSSW_BASE}/src"

source /cvmfs/cms.cern.ch/cmsset_default.sh
cd "${CMSSW_SRC}"
eval "$(scram runtime -sh)"

exec python3 -m ipykernel_launcher -f "$1"

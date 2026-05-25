#!/bin/bash
# ==============================================================================
# run_wrapper.sh - HTCondor wrapper for NtupleAnalyzer jobs
# ==============================================================================
# This wrapper sets up the LCG Python/ROOT environment and runs the analysis script.
#
# Usage (from HTCondor):
#   arguments = "run_jyp_mc_ntuple.sh -m DPS_1 -j 8"
# ==============================================================================

set -e

# ==============================================================================
# Configuration
# ==============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYZER_DIR="$(dirname "$SCRIPT_DIR")"
LCG_VIEW="${LCG_VIEW:-/cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt}"

# Parse wrapper arguments
ANALYSIS_SCRIPT="$1"
shift
SCRIPT_ARGS="$@"

echo "=============================================="
echo "HTCondor Job Wrapper"
echo "=============================================="
echo "Date: $(date)"
echo "Host: $(hostname)"
echo "Working dir: $(pwd)"
echo "Analyzer dir: $ANALYZER_DIR"
echo "LCG view: $LCG_VIEW"
echo "Script: $ANALYSIS_SCRIPT"
echo "Args: $SCRIPT_ARGS"
echo "=============================================="

# ==============================================================================
# Setup Environment
# ==============================================================================
echo "[INFO] Setting up LCG_109a environment..."

# Source LCG environment. This provides ROOT, RooFit, XRootD, and uproot without
# paying the CMSSW project-space setup cost on batch nodes.
if [ -f "$LCG_VIEW/setup.sh" ]; then
    source "$LCG_VIEW/setup.sh"
else
    echo "[ERROR] LCG view not found: $LCG_VIEW"
    exit 1
fi

echo "[INFO] Python: $(command -v python3)"
echo "[INFO] ROOT: $(root-config --version 2>/dev/null || echo unavailable)"

# ==============================================================================
# Setup VOMS Proxy (for xrootd access)
# ==============================================================================
echo "[INFO] Setting up VOMS proxy..."

# Check for proxy in standard locations
PROXY_LOCATIONS=(
    "$X509_USER_PROXY"
    "/afs/cern.ch/user/c/chiw/condor/x509up"
    "/tmp/x509up_u$(id -u)"
)

PROXY_FOUND=""
for proxy in "${PROXY_LOCATIONS[@]}"; do
    if [ -n "$proxy" ] && [ -f "$proxy" ]; then
        export X509_USER_PROXY="$proxy"
        PROXY_FOUND="$proxy"
        echo "[INFO] Using proxy: $proxy"
        break
    fi
done

if [ -z "$PROXY_FOUND" ]; then
    echo "[WARN] No VOMS proxy found. XRootD access may fail."
fi

# Verify proxy if found
if [ -n "$PROXY_FOUND" ]; then
    if voms-proxy-info --exists &>/dev/null; then
        TIMELEFT=$(voms-proxy-info --timeleft 2>/dev/null || echo "0")
        echo "[INFO] Proxy valid for $((TIMELEFT/3600)) hours"
    else
        echo "[WARN] Proxy exists but may not be valid"
    fi
fi

# ==============================================================================
# Run Analysis
# ==============================================================================
echo ""
echo "[INFO] Running analysis script..."
cd "$ANALYZER_DIR"

# Make script executable if needed
chmod +x "$ANALYSIS_SCRIPT"

# Run the script with arguments
./"$ANALYSIS_SCRIPT" $SCRIPT_ARGS
EXIT_CODE=$?

echo ""
echo "=============================================="
echo "Job completed with exit code: $EXIT_CODE"
echo "Date: $(date)"
echo "=============================================="

exit $EXIT_CODE

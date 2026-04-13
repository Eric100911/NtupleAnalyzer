#!/bin/bash
# ==============================================================================
# run_wrapper.sh - HTCondor wrapper for NtupleAnalyzer jobs
# ==============================================================================
# This wrapper sets up the CMSSW environment and runs the analysis script.
# It handles both lxplus (CERN) and IHEP environments.
#
# Usage (from HTCondor):
#   arguments = "run_jup_mc_ntuple.sh -m DPS_1 -j 8"
# ==============================================================================

set -e

# ==============================================================================
# Configuration
# ==============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYZER_DIR="$(dirname "$SCRIPT_DIR")"
CMSSW_BASE_DIR="$(dirname "$(dirname "$ANALYZER_DIR")")"
ANALYZER_DIR_FALLBACK="/afs/cern.ch/user/x/xcheng/condor/CMSSW_15_0_15/src/NtupleAnalyzer"
CMSSW_BASE_FALLBACK="/afs/cern.ch/user/x/xcheng/condor/CMSSW_15_0_15"

if [ ! -f "$CMSSW_BASE_DIR/src/.SCRAM/Environment" ] && [ -f "$CMSSW_BASE_FALLBACK/src/.SCRAM/Environment" ]; then
    ANALYZER_DIR="$ANALYZER_DIR_FALLBACK"
    CMSSW_BASE_DIR="$CMSSW_BASE_FALLBACK"
fi

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
echo "CMSSW base: $CMSSW_BASE_DIR"
echo "Analyzer dir: $ANALYZER_DIR"
echo "Script: $ANALYSIS_SCRIPT"
echo "Args: $SCRIPT_ARGS"
echo "=============================================="

# ==============================================================================
# Setup Environment
# ==============================================================================
echo "[INFO] Setting up CMS environment..."

# Source CMS environment
if [ -f /cvmfs/cms.cern.ch/cmsset_default.sh ]; then
    source /cvmfs/cms.cern.ch/cmsset_default.sh
else
    echo "[ERROR] CMS environment not found at /cvmfs/cms.cern.ch"
    exit 1
fi

# Setup CMSSW
cd "$CMSSW_BASE_DIR"
if [ -f "$CMSSW_BASE_DIR/src/.SCRAM/Environment" ]; then
    eval $(scramv1 runtime -sh)
    echo "[INFO] CMSSW environment set: $CMSSW_VERSION"
else
    echo "[ERROR] CMSSW not properly initialized in $CMSSW_BASE_DIR"
    exit 1
fi

# ==============================================================================
# Setup VOMS Proxy (for xrootd access)
# ==============================================================================
echo "[INFO] Setting up VOMS proxy..."

# Check for proxy in standard locations
PROXY_LOCATIONS=(
    "$X509_USER_PROXY"
    "/afs/cern.ch/user/x/xcheng/x509up_u$(id -u)"
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

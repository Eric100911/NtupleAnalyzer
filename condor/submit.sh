#!/bin/bash
# ==============================================================================
# submit.sh - HTCondor job submission manager for NtupleAnalyzer
# ==============================================================================
# This script manages HTCondor job submission for all analysis types.
#
# Usage:
#   ./submit.sh --help                       # Show help
#   ./submit.sh jyp_mc                       # Submit JYP MC (DPS_1)
#   ./submit.sh jyp_mc --mode SPS            # Submit JYP MC with mode
#   ./submit.sh jyp_mc --mode all            # Submit all JYP MC modes
#   ./submit.sh jjy_mc --mode DPS_1          # Submit JJY MC DPS_1
#   ./submit.sh jjp_data                     # Submit JJP data analysis
#   ./submit.sh --status                     # Check job status
#   ./submit.sh --clean                      # Clean log files
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

msg_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
msg_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
msg_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
msg_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ==============================================================================
# Help
# ==============================================================================
print_help() {
    cat << EOF
${CYAN}NtupleAnalyzer HTCondor Submission Manager${NC}

${YELLOW}Usage:${NC}
    $0 <analysis_type> [options]
    $0 --status | --clean | --help

${YELLOW}Analysis Types:${NC}
    jyp_mc      J/psi + Upsilon + Phi MC analysis
    jjp_mc      J/psi + J/psi + Phi MC analysis
    jjy_mc      J/psi + J/psi + Upsilon MC analysis
    jjp_efficiency  J/psi + J/psi + Phi efficiency from raw ntuples
    jyp_data    J/psi + Upsilon + Phi data analysis
    jjp_data    J/psi + J/psi + Phi data analysis

${YELLOW}Options:${NC}
    -m, --mode MODE       MC mode (JYP: SPS/DPS_1/DPS_2/DPS_3/TPS, JJP: DPS_1/DPS_2_CS/DPS_2_G/SPS_CS/SPS_G/TPS, JJY: DPS_1/DPS_2)
                          Use 'all' to submit all modes
    -j, --jobs N          Number of analyzer worker processes (JJY default: 1)
    -n, --max-events N    Maximum events to process (-1=all)
    --max-files N         Maximum efficiency ntuples to shard
    --muon-id TYPE        JJP muon ID (soft/medium/tight/loose/none)
    --jpsi-muon-id TYPE   JYP J/psi muon ID
    --ups-muon-id TYPE    JYP Upsilon muon ID
    --sample SAMPLE       Efficiency sample or comma-separated samples (default: all)
    --files-per-job N     Efficiency ntuples per Condor job (default: 10)
    --output-dir DIR      Efficiency output directory
    --remote-access-mode MODE  Efficiency remote access mode (fallback/direct/stage)
    --efficiency-backend MODE  Efficiency backend (vectorized/python-loop)
    --stage-retries N     Efficiency copy retries per staged file
    --copy-timeout N      Efficiency seconds per remote copy attempt (default: 180, 0 disables)
    --worker-timeout N    Efficiency seconds per file read attempt (default: 180, 0 disables)
    --dry-run             Show command without submitting
    --flavor FLAVOR       Job flavor (espresso/microcentury/longlunch/workday/tomorrow)

${YELLOW}Management Commands:${NC}
    --status              Show job status (condor_q)
    --history             Show job history
    --clean               Clean log files
    --check-proxy         Check VOMS proxy status

${YELLOW}Examples:${NC}
    $0 jyp_mc                           # Submit JYP MC DPS_1
    $0 jyp_mc -m DPS_2 -j 16            # Submit JYP MC DPS_2 with 16 cores
    $0 jyp_mc -m all                    # Submit all JYP MC modes
    $0 jjy_mc -m all -j 1                # Submit both JJY MC samples single-core
    $0 jjp_data -n 100000               # Submit JJP data (100k events)
    $0 --status                         # Check job status

EOF
}

# ==============================================================================
# Check proxy
# ==============================================================================
check_proxy() {
    msg_info "Checking VOMS proxy..."
    
    if ! command -v voms-proxy-info &>/dev/null; then
        msg_warn "voms-proxy-info not available. Skipping proxy check."
        return 0
    fi
    
    if ! voms-proxy-info --exists &>/dev/null; then
        msg_error "No valid VOMS proxy found!"
        echo ""
        echo "Please create a proxy with:"
        echo "  voms-proxy-init --voms cms --valid 168:00"
        return 1
    fi
    
    TIMELEFT=$(voms-proxy-info --timeleft 2>/dev/null || echo "0")
    HOURS_LEFT=$((TIMELEFT / 3600))
    
    if [ $HOURS_LEFT -lt 12 ]; then
        msg_warn "Proxy expires in ${HOURS_LEFT} hours. Consider renewing."
    else
        msg_ok "Proxy valid for ${HOURS_LEFT} hours"
    fi
    
    PROXY_PATH="$(voms-proxy-info --path 2>/dev/null || true)"
    if [ -n "$PROXY_PATH" ]; then
        msg_ok "Using existing proxy: $PROXY_PATH"
    fi
    
    return 0
}

# ==============================================================================
# Job status
# ==============================================================================
show_status() {
    msg_info "Job status for user: $(whoami)"
    echo ""
    condor_q
}

show_history() {
    msg_info "Recent job history:"
    echo ""
    condor_history -limit 20
}

# ==============================================================================
# Clean logs
# ==============================================================================
clean_logs() {
    msg_info "Cleaning log files..."
    
    LOG_DIRS=("logs/jyp_mc" "logs/jjp_mc" "logs/jjy_mc" "logs/jjp_efficiency" "logs/jyp_data" "logs/jjp_data")
    
    for dir in "${LOG_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            rm -rf "$dir"/*.out "$dir"/*.err "$dir"/*.log 2>/dev/null || true
            msg_ok "Cleaned $dir"
        fi
    done
    
    msg_ok "Log cleanup complete"
}

# ==============================================================================
# Submit job
# ==============================================================================
submit_job() {
    local ANALYSIS_TYPE="$1"
    shift
    
    # Parse options
    local MODE=""
    local JOBS=""
    local MAX_EVENTS=""
    local MAX_FILES=""
    local MUON_ID=""
    local JPSI_MUON_ID=""
    local UPS_MUON_ID=""
    local SAMPLE="all"
    local FILES_PER_JOB="10"
    local OUTPUT_DIR="/eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/efficiency"
    local REMOTE_ACCESS_MODE="fallback"
    local EFFICIENCY_BACKEND="vectorized"
    local STAGE_RETRIES="3"
    local COPY_TIMEOUT="180"
    local WORKER_TIMEOUT="180"
    local INPUT_FILE_MANIFEST=""
    local DRY_RUN=false
    local FLAVOR=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -m|--mode) MODE="$2"; shift 2;;
            -j|--jobs) JOBS="$2"; shift 2;;
            -n|--max-events) MAX_EVENTS="$2"; shift 2;;
            --max-files) MAX_FILES="$2"; shift 2;;
            --muon-id) MUON_ID="$2"; shift 2;;
            --jpsi-muon-id) JPSI_MUON_ID="$2"; shift 2;;
            --ups-muon-id) UPS_MUON_ID="$2"; shift 2;;
            --sample) SAMPLE="$2"; shift 2;;
            --files-per-job) FILES_PER_JOB="$2"; shift 2;;
            --output-dir) OUTPUT_DIR="$2"; shift 2;;
            --remote-access-mode) REMOTE_ACCESS_MODE="$2"; shift 2;;
            --efficiency-backend) EFFICIENCY_BACKEND="$2"; shift 2;;
            --stage-retries) STAGE_RETRIES="$2"; shift 2;;
            --copy-timeout) COPY_TIMEOUT="$2"; shift 2;;
            --worker-timeout) WORKER_TIMEOUT="$2"; shift 2;;
            --input-file-manifest) INPUT_FILE_MANIFEST="$2"; shift 2;;
            --dry-run) DRY_RUN=true; shift;;
            --flavor) FLAVOR="$2"; shift 2;;
            *) msg_error "Unknown option: $1"; exit 1;;
        esac
    done
    
    # Determine submit file
    local SUB_FILE=""
    case "$ANALYSIS_TYPE" in
        jyp_mc) SUB_FILE="jyp_mc.sub";;
        jjp_mc) SUB_FILE="jjp_mc.sub";;
        jjy_mc) SUB_FILE="jjy_mc.sub";;
        jjp_efficiency) SUB_FILE="jjp_efficiency.sub";;
        jyp_data) SUB_FILE="jyp_data.sub";;
        jjp_data) SUB_FILE="jjp_data.sub";;
        *) msg_error "Unknown analysis type: $ANALYSIS_TYPE"; exit 1;;
    esac
    
    if [ ! -f "$SUB_FILE" ]; then
        msg_error "Submit file not found: $SUB_FILE"
        exit 1
    fi

    if [ "$DRY_RUN" != true ]; then
        check_proxy || exit 1
    fi
    
    # Create log directories
    mkdir -p logs/jyp_mc logs/jjp_mc logs/jjy_mc logs/jjp_efficiency logs/jyp_data logs/jjp_data
    
    # Build condor_submit arguments
    local SUBMIT_APPEND_ARGS=()
    
    [ -n "$JOBS" ] && SUBMIT_APPEND_ARGS+=("-append" "JOBS = $JOBS")
    [ -n "$MAX_EVENTS" ] && SUBMIT_APPEND_ARGS+=("-append" "MAX_EVENTS = $MAX_EVENTS")
    [ -n "$MUON_ID" ] && SUBMIT_APPEND_ARGS+=("-append" "MUON_ID = $MUON_ID")
    [ -n "$JPSI_MUON_ID" ] && SUBMIT_APPEND_ARGS+=("-append" "JPSI_MUON_ID = $JPSI_MUON_ID")
    [ -n "$UPS_MUON_ID" ] && SUBMIT_APPEND_ARGS+=("-append" "UPS_MUON_ID = $UPS_MUON_ID")
    [ -n "$FLAVOR" ] && SUBMIT_APPEND_ARGS+=("-append" "+JobFlavour = \"$FLAVOR\"")

    if [ "$ANALYSIS_TYPE" = "jjp_efficiency" ]; then
        local PREPARE_CMD=("../prepare_efficiency_shards.py" "--samples" "$SAMPLE" "--files-per-job" "$FILES_PER_JOB" "--output-dir" "$OUTPUT_DIR")
        [ -n "$INPUT_FILE_MANIFEST" ] && PREPARE_CMD+=("--input-file-manifest" "$INPUT_FILE_MANIFEST")
        [ -n "$MAX_EVENTS" ] && msg_warn "--max-events is ignored for jjp_efficiency; use --max-files"
        if [ -n "$MODE" ]; then
            msg_warn "--mode is ignored for jjp_efficiency; use --sample"
        fi
        if [ -n "$MAX_FILES" ]; then
            PREPARE_CMD+=("--max-files" "$MAX_FILES")
        fi
        msg_info "Preparing efficiency shards..."
        local QUEUE_FILE
        QUEUE_FILE="$("${PREPARE_CMD[@]}")"

        msg_info "Building runtime tarball..."
        local RUNTIME_TARBALL
        RUNTIME_TARBALL="$(bash "${SCRIPT_DIR}/build_runtime_tarball.sh" | tail -1)"

        local CMD_PARTS=("condor_submit")
        CMD_PARTS+=("-append" "QUEUE_FILE = $QUEUE_FILE")
        CMD_PARTS+=("-append" "RUNTIME_TARBALL = $RUNTIME_TARBALL")
        CMD_PARTS+=("-append" "OUTPUT_DIR = $OUTPUT_DIR")
        CMD_PARTS+=("-append" "REMOTE_ACCESS_MODE = $REMOTE_ACCESS_MODE")
        CMD_PARTS+=("-append" "EFFICIENCY_BACKEND = $EFFICIENCY_BACKEND")
        CMD_PARTS+=("-append" "STAGE_RETRIES = $STAGE_RETRIES")
        CMD_PARTS+=("-append" "COPY_TIMEOUT = $COPY_TIMEOUT")
        CMD_PARTS+=("-append" "WORKER_TIMEOUT = $WORKER_TIMEOUT")
        CMD_PARTS+=("${SUBMIT_APPEND_ARGS[@]}")
        CMD_PARTS+=("$SUB_FILE")
        local CMD="${CMD_PARTS[*]}"
        echo ""
        msg_info "Submitting: $ANALYSIS_TYPE sample=${SAMPLE} files/job=${FILES_PER_JOB}"
        echo "Shard queue: $QUEUE_FILE"
        echo "Runtime tarball: $RUNTIME_TARBALL"
        echo "Command: $CMD"
        if [ "$DRY_RUN" = true ]; then
            msg_warn "Dry run - not submitting"
        else
            "${CMD_PARTS[@]}"
            msg_ok "Job submitted"
        fi
        return
    fi

    if [ "$ANALYSIS_TYPE" = "jjy_mc" ] && [ -n "$MODE" ] && [ "${MODE,,}" != "all" ]; then
        case "${MODE^^}" in
            DPS_1|DPS_2) MODE="${MODE^^}";;
            *)
                msg_error "Invalid JJY MC mode: $MODE"
                echo "Valid JJY MC modes are DPS_1 and DPS_2. SPS is reserved; bare DPS is not accepted."
                exit 1
                ;;
        esac
    fi
    
    # Handle 'all' mode
    local MODES_TO_SUBMIT=()
    if [ "${MODE,,}" = "all" ]; then
        case "$ANALYSIS_TYPE" in
            jyp_mc) MODES_TO_SUBMIT=(SPS DPS_1 DPS_2 DPS_3 TPS);;
            jjp_mc) MODES_TO_SUBMIT=(DPS_1 DPS_2_CS DPS_2_G SPS_CS SPS_G TPS);;
            jjy_mc) MODES_TO_SUBMIT=(DPS_1 DPS_2);;
            *) MODES_TO_SUBMIT=("");;
        esac
    elif [ -n "$MODE" ]; then
        MODES_TO_SUBMIT=("$MODE")
    else
        MODES_TO_SUBMIT=("")  # Use default
    fi
    
    # Submit jobs
    for m in "${MODES_TO_SUBMIT[@]}"; do
        local CMD_PARTS=("condor_submit")
        [ -n "$m" ] && CMD_PARTS+=("-append" "MODE = $m")
        CMD_PARTS+=("${SUBMIT_APPEND_ARGS[@]}")
        CMD_PARTS+=("$SUB_FILE")
        
        local CMD="${CMD_PARTS[*]}"
        
        echo ""
        msg_info "Submitting: $ANALYSIS_TYPE ${m:-default}"
        echo "Command: $CMD"
        
        if [ "$DRY_RUN" = true ]; then
            msg_warn "Dry run - not submitting"
        else
            "${CMD_PARTS[@]}"
            msg_ok "Job submitted"
        fi
    done
}

# ==============================================================================
# Main
# ==============================================================================
main() {
    if [ $# -eq 0 ]; then
        print_help
        exit 0
    fi
    
    case "$1" in
        -h|--help)
            print_help
            exit 0
            ;;
        --status)
            show_status
            exit 0
            ;;
        --history)
            show_history
            exit 0
            ;;
        --clean)
            clean_logs
            exit 0
            ;;
        --check-proxy)
            check_proxy
            exit $?
            ;;
        jyp_mc|jjp_mc|jjy_mc|jjp_efficiency|jyp_data|jjp_data)
            submit_job "$@"
            ;;
        *)
            msg_error "Unknown command: $1"
            print_help
            exit 1
            ;;
    esac
}

main "$@"

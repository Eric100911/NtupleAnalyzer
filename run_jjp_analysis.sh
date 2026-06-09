#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MAX_EVENTS=-1
JOBS=8
MERGE_OUTPUT=""
WEIGHTED_OUTPUT=""
EFFICIENCY_CORRECTED_OUTPUT=""
PLOT_DIR=""
MUON_ID="soft"
INPUT_DIR=""
EFFICIENCY_DIR=""
EFFICIENCY_SAMPLE=""
EFFICIENCY_MAP=""
EFFICIENCY_STEP="Pri_assocPVPass"
EFFICIENCY_ON_MISSING="error"
CORRECTION_APPLIED=0

while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--max-events) MAX_EVENTS="$2"; shift 2 ;;
        -j|--jobs) JOBS="$2"; shift 2 ;;
        --muon-id) MUON_ID="$2"; shift 2 ;;
        -i|--input-dir) INPUT_DIR="$2"; shift 2 ;;
        --merge-output) MERGE_OUTPUT="$2"; shift 2 ;;
        --weighted-output) WEIGHTED_OUTPUT="$2"; shift 2 ;;
        --efficiency-corrected-output) EFFICIENCY_CORRECTED_OUTPUT="$2"; shift 2 ;;
        --efficiency-dir) EFFICIENCY_DIR="$2"; shift 2 ;;
        --efficiency-sample) EFFICIENCY_SAMPLE="$2"; shift 2 ;;
        --efficiency-map) EFFICIENCY_MAP="$2"; shift 2 ;;
        --efficiency-step) EFFICIENCY_STEP="$2"; shift 2 ;;
        --efficiency-on-missing) EFFICIENCY_ON_MISSING="$2"; shift 2 ;;
        --plot-dir) PLOT_DIR="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo "  -n, --max-events N"
            echo "  -j, --jobs N"
            echo "  --muon-id TYPE"
            echo "  -i, --input-dir DIR"
            echo "  --merge-output FILE"
            echo "  --weighted-output FILE"
            echo "  --efficiency-corrected-output FILE"
            echo "  --efficiency-dir DIR"
            echo "  --efficiency-sample SAMPLE"
            echo "  --efficiency-map FILE"
            echo "  --efficiency-step STEP"
            echo "  --efficiency-on-missing error|unity|drop"
            echo "  --plot-dir DIR"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

MERGE_ARGS=(--channel JJP --dataset data -n "$MAX_EVENTS" -j "$JOBS" --muon-id "$MUON_ID")
[[ -n "$INPUT_DIR" ]] && MERGE_ARGS+=(-i "$INPUT_DIR")
[[ -n "$MERGE_OUTPUT" ]] && MERGE_ARGS+=(-o "$MERGE_OUTPUT")
./run_assoc_merge.sh "${MERGE_ARGS[@]}" || exit $?

FIT_INPUT="$MERGE_OUTPUT"
if [[ -z "$FIT_INPUT" ]]; then
    FIT_INPUT="$(python3 - <<'PY'
from ntuple_pipeline_common import default_merged_output
print(default_merged_output("JJP", "data"))
PY
)"
fi

if [[ -n "$EFFICIENCY_MAP" || -n "$EFFICIENCY_DIR" || -n "$EFFICIENCY_SAMPLE" ]]; then
    if [[ -z "$EFFICIENCY_MAP" && ( -z "$EFFICIENCY_DIR" || -z "$EFFICIENCY_SAMPLE" ) ]]; then
        echo "Efficiency correction requires --efficiency-map or both --efficiency-dir and --efficiency-sample" >&2
        exit 1
    fi
    if [[ -z "$EFFICIENCY_CORRECTED_OUTPUT" ]]; then
        EFFICIENCY_CORRECTED_OUTPUT="${FIT_INPUT%.root}_effcorr.root"
    fi
    CORR_ARGS=(-i "$FIT_INPUT" -o "$EFFICIENCY_CORRECTED_OUTPUT" --efficiency-step "$EFFICIENCY_STEP" --on-missing "$EFFICIENCY_ON_MISSING")
    [[ -n "$EFFICIENCY_MAP" ]] && CORR_ARGS+=(--efficiency-map "$EFFICIENCY_MAP")
    [[ -n "$EFFICIENCY_DIR" ]] && CORR_ARGS+=(--efficiency-dir "$EFFICIENCY_DIR")
    [[ -n "$EFFICIENCY_SAMPLE" ]] && CORR_ARGS+=(--efficiency-sample "$EFFICIENCY_SAMPLE")
    python3 apply_efficiency_corrections.py "${CORR_ARGS[@]}" || exit $?
    FIT_INPUT="$EFFICIENCY_CORRECTED_OUTPUT"
    CORRECTION_APPLIED=1
fi

FIT_ARGS=(--channel JJP --dataset data -j "$JOBS")
FIT_ARGS+=(-i "$FIT_INPUT")
if [[ "$CORRECTION_APPLIED" -eq 1 ]]; then
    FIT_ARGS+=(--fit-weight-branch effcorr_weight)
fi
[[ -n "$WEIGHTED_OUTPUT" ]] && FIT_ARGS+=(-o "$WEIGHTED_OUTPUT")
[[ -n "$PLOT_DIR" ]] && FIT_ARGS+=(--plot-dir "$PLOT_DIR/fit")
./run_assoc_fit.sh "${FIT_ARGS[@]}" || exit $?

PLOT_ARGS=(--channel JJP --dataset data -j "$JOBS")
[[ -n "$WEIGHTED_OUTPUT" ]] && PLOT_ARGS+=(-i "$WEIGHTED_OUTPUT")
[[ -n "$PLOT_DIR" ]] && PLOT_ARGS+=(-o "$PLOT_DIR")
./run_assoc_plots.sh "${PLOT_ARGS[@]}"

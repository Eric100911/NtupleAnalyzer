#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MAX_EVENTS=-1
JOBS=8
MERGE_OUTPUT=""
WEIGHTED_OUTPUT=""
PLOT_DIR=""
JPSI_MUON_ID="soft"
UPS_MUON_ID="soft"
INPUT_DIR=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--max-events) MAX_EVENTS="$2"; shift 2 ;;
        -j|--jobs) JOBS="$2"; shift 2 ;;
        --jpsi-muon-id) JPSI_MUON_ID="$2"; shift 2 ;;
        --ups-muon-id) UPS_MUON_ID="$2"; shift 2 ;;
        -i|--input-dir) INPUT_DIR="$2"; shift 2 ;;
        --merge-output) MERGE_OUTPUT="$2"; shift 2 ;;
        --weighted-output) WEIGHTED_OUTPUT="$2"; shift 2 ;;
        --plot-dir) PLOT_DIR="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo "  -n, --max-events N"
            echo "  -j, --jobs N"
            echo "  --jpsi-muon-id TYPE"
            echo "  --ups-muon-id TYPE"
            echo "  -i, --input-dir DIR"
            echo "  --merge-output FILE"
            echo "  --weighted-output FILE"
            echo "  --plot-dir DIR"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

MERGE_ARGS=(--channel JYP --dataset data -n "$MAX_EVENTS" -j "$JOBS" --jpsi-muon-id "$JPSI_MUON_ID" --ups-muon-id "$UPS_MUON_ID")
[[ -n "$INPUT_DIR" ]] && MERGE_ARGS+=(-i "$INPUT_DIR")
[[ -n "$MERGE_OUTPUT" ]] && MERGE_ARGS+=(-o "$MERGE_OUTPUT")

./run_assoc_merge.sh "${MERGE_ARGS[@]}" || exit $?

FIT_ARGS=(--channel JYP --dataset data -j "$JOBS")
[[ -n "$MERGE_OUTPUT" ]] && FIT_ARGS+=(-i "$MERGE_OUTPUT")
[[ -n "$WEIGHTED_OUTPUT" ]] && FIT_ARGS+=(-o "$WEIGHTED_OUTPUT")
[[ -n "$PLOT_DIR" ]] && FIT_ARGS+=(--plot-dir "$PLOT_DIR/fit")
./run_assoc_fit.sh "${FIT_ARGS[@]}" || exit $?

PLOT_ARGS=(--channel JYP --dataset data -j "$JOBS")
[[ -n "$WEIGHTED_OUTPUT" ]] && PLOT_ARGS+=(-i "$WEIGHTED_OUTPUT")
[[ -n "$PLOT_DIR" ]] && PLOT_ARGS+=(-o "$PLOT_DIR")
./run_assoc_plots.sh "${PLOT_ARGS[@]}"

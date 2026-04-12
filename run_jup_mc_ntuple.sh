#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODE="DPS_3"
MAX_EVENTS=-1
JOBS=8
JPSI_MUON_ID="soft"
UPS_MUON_ID="soft"
INPUT_DIR=""
OUTPUT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--mode) MODE="$2"; shift 2 ;;
        -n|--max-events) MAX_EVENTS="$2"; shift 2 ;;
        -j|--jobs) JOBS="$2"; shift 2 ;;
        --jpsi-muon-id) JPSI_MUON_ID="$2"; shift 2 ;;
        --ups-muon-id) UPS_MUON_ID="$2"; shift 2 ;;
        -i|--input-dir) INPUT_DIR="$2"; shift 2 ;;
        -o|--output) OUTPUT="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo "  -m, --mode MODE"
            echo "  -n, --max-events N"
            echo "  -j, --jobs N"
            echo "  --jpsi-muon-id TYPE"
            echo "  --ups-muon-id TYPE"
            echo "  -i, --input-dir DIR"
            echo "  -o, --output FILE"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

ARGS=(--channel JUP --dataset mc --sample "$MODE" -n "$MAX_EVENTS" -j "$JOBS" --jpsi-muon-id "$JPSI_MUON_ID" --ups-muon-id "$UPS_MUON_ID")
[[ -n "$INPUT_DIR" ]] && ARGS+=(-i "$INPUT_DIR")
[[ -n "$OUTPUT" ]] && ARGS+=(-o "$OUTPUT")

./run_assoc_merge.sh "${ARGS[@]}"

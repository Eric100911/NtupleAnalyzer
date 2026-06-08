#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CHANNEL=""
DATASET=""
SAMPLE="NONE"
SHARD_INDEX=""
SHARD_MANIFEST=""
OUTPUT=""
MAX_EVENTS=-1
JOBS=1
MUON_ID="soft"
JPSI_MUON_ID="soft"
UPS_MUON_ID="soft"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --channel) CHANNEL="$2"; shift 2 ;;
        --dataset) DATASET="$2"; shift 2 ;;
        --sample) SAMPLE="$2"; shift 2 ;;
        --shard-index) SHARD_INDEX="$2"; shift 2 ;;
        --shard-manifest) SHARD_MANIFEST="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        -n|--max-events) MAX_EVENTS="$2"; shift 2 ;;
        -j|--jobs) JOBS="$2"; shift 2 ;;
        --muon-id) MUON_ID="$2"; shift 2 ;;
        --jpsi-muon-id) JPSI_MUON_ID="$2"; shift 2 ;;
        --ups-muon-id) UPS_MUON_ID="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 --channel CHANNEL --dataset DATASET --shard-index N --shard-manifest FILE --output FILE [options]"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ -z "$CHANNEL" || -z "$DATASET" || -z "$SHARD_INDEX" || -z "$SHARD_MANIFEST" || -z "$OUTPUT" ]]; then
    echo "Missing required --channel, --dataset, --shard-index, --shard-manifest, or --output"
    exit 1
fi

ARGS=(
    --channel "$CHANNEL"
    --dataset "$DATASET"
    --input-file-manifest "$SHARD_MANIFEST"
    -o "$OUTPUT"
    -n "$MAX_EVENTS"
    -j "$JOBS"
)

if [[ "$SAMPLE" != "NONE" && -n "$SAMPLE" ]]; then
    ARGS+=(--sample "$SAMPLE")
fi

if [[ "${CHANNEL^^}" == "JJP" ]]; then
    ARGS+=(--muon-id "$MUON_ID")
else
    ARGS+=(--jpsi-muon-id "$JPSI_MUON_ID" --ups-muon-id "$UPS_MUON_ID")
fi

./run_assoc_merge.sh "${ARGS[@]}"

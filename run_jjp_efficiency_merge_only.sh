#!/bin/bash
# Merge one verified JJP efficiency sample. CERN's DAG POST must stop here;
# maps, plots, closure, and yield work are explicitly downstream tasks.

set -euo pipefail

SAMPLE="${1:-}"
SHARDS_DIR="${2:-}"
MERGE_CONTAINER_DIR="${3:-}"
FINAL_SAMPLE_DIR="${4:-}"

if [[ -z "$SAMPLE" || -z "$SHARDS_DIR" || -z "$MERGE_CONTAINER_DIR" || -z "$FINAL_SAMPLE_DIR" ]]; then
    echo "Usage: $0 SAMPLE SHARDS_DIR PRIVATE_MERGE_CONTAINER FINAL_SAMPLE_BUNDLE" >&2
    exit 2
fi
if [[ ! "$SAMPLE" =~ ^[A-Za-z0-9][A-Za-z0-9_]*$ ]]; then
    echo "Invalid sample name: $SAMPLE" >&2
    exit 2
fi
if [[ "$MERGE_CONTAINER_DIR" != */"_merge_$SAMPLE" ]]; then
    echo "Private merge container must end in /_merge_$SAMPLE: $MERGE_CONTAINER_DIR" >&2
    exit 2
fi
if [[ "$FINAL_SAMPLE_DIR" != */"$SAMPLE" ]]; then
    echo "Final sample bundle must end in /$SAMPLE: $FINAL_SAMPLE_DIR" >&2
    exit 2
fi
if [[ -e "$MERGE_CONTAINER_DIR" || -e "$FINAL_SAMPLE_DIR" ]]; then
    echo "Refusing to reuse merge container or final sample bundle" >&2
    exit 2
fi

EXPECTED_BUNDLE="$MERGE_CONTAINER_DIR/$SAMPLE"
echo "[merge-only] sample=$SAMPLE"
echo "[merge-only] shards=$SHARDS_DIR"
echo "[merge-only] private-container=$MERGE_CONTAINER_DIR"
echo "[merge-only] final-bundle=$FINAL_SAMPLE_DIR"
python3 merge_efficiency_shards.py \
    --sample "$SAMPLE" \
    --shards-dir "$SHARDS_DIR" \
    --output-dir "$MERGE_CONTAINER_DIR"

if [[ ! -d "$EXPECTED_BUNDLE" || ! -f "$EXPECTED_BUNDLE/sample_manifest.json" ]]; then
    echo "Merge did not produce the expected sample bundle: $EXPECTED_BUNDLE" >&2
    exit 1
fi
mv "$EXPECTED_BUNDLE" "$FINAL_SAMPLE_DIR"
echo "[merge-only] handoff bundle=$FINAL_SAMPLE_DIR"

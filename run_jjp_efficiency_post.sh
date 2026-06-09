#!/bin/bash
# ==============================================================================
# run_jjp_efficiency_post.sh - Merge shard outputs and generate all efficiency plots
# ==============================================================================
# Runs inside run_wrapper.sh on a Condor worker node after all shard jobs complete.
#
# Usage:
#   run_jjp_efficiency_post.sh SAMPLE SHARDS_DIR MERGED_DIR
# ==============================================================================

set -e

SAMPLE="$1"
SHARDS_DIR="$2"
MERGED_DIR="$3"

if [[ -z "$SAMPLE" || -z "$SHARDS_DIR" || -z "$MERGED_DIR" ]]; then
    echo "Usage: $0 SAMPLE SHARDS_DIR MERGED_DIR"
    exit 1
fi

echo "=============================================="
echo "Efficiency Post-Processing"
echo "=============================================="
echo "Sample:      $SAMPLE"
echo "Shards dir:  $SHARDS_DIR"
echo "Merged dir:  $MERGED_DIR"
echo "Date:        $(date)"
echo "Host:        $(hostname)"
echo "=============================================="

# Step 1: Merge shard outputs (fast, no plots)
echo ""
echo "[1/2] Merging shard outputs for $SAMPLE ..."
python3 merge_efficiency_shards.py \
    --sample "$SAMPLE" \
    --shards-dir "$SHARDS_DIR" \
    --output-dir "$MERGED_DIR"

echo "[1/2] Merge complete."

# Step 2: Build derived products and ALL plots (cumulative + derived)
echo ""
echo "[2/2] Building derived efficiency products and plots ..."
python3 build_derived_efficiency.py \
    --input-dir "$MERGED_DIR" \
    --output-dir "$MERGED_DIR"

echo "[2/2] Derived products and plots complete."

echo ""
echo "=============================================="
echo "Post-processing finished successfully."
echo "Date: $(date)"
echo "=============================================="

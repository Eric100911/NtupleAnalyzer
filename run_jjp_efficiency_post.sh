#!/bin/bash
# ==============================================================================
# run_jjp_efficiency_post.sh - Merge shard outputs, build all efficiency products
# ==============================================================================
# Runs inside run_wrapper.sh on a Condor worker node after all shard jobs complete.
# Produces: merged parquets, derived maps, factorized correction maps, post-acceptance 5D map.
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
echo "[1/4] Merging shard outputs for $SAMPLE ..."
python3 merge_efficiency_shards.py \
    --sample "$SAMPLE" \
    --shards-dir "$SHARDS_DIR" \
    --output-dir "$MERGED_DIR"

echo "[1/4] Merge complete."

# Step 2: Build derived products and ALL plots (cumulative + derived)
echo ""
echo "[2/4] Building derived efficiency products and plots ..."
python3 build_derived_efficiency.py \
    --input-dir "$MERGED_DIR" \
    --output-dir "$MERGED_DIR"

echo "[2/4] Derived products and plots complete."

# Step 3: Build factorized correction maps (per-object 2D + event-level, fine/coarse/inclusive)
echo ""
echo "[3/4] Building factorized correction maps for $SAMPLE ..."
python3 -m efficiency_workflow.build_factorized_maps \
    --input-dir "$MERGED_DIR" \
    --samples "$SAMPLE"

echo "[3/4] Factorized maps complete."

# Step 4: Build post-acceptance 5D conditional efficiency map (for hybrid correction mode)
echo ""
echo "[4/4] Building post-acceptance 5D map for $SAMPLE ..."
python3 -m efficiency_workflow.build_factorized_maps \
    --input-dir "$MERGED_DIR" \
    --samples "$SAMPLE" \
    --build-post-acceptance

echo "[4/4] Post-acceptance 5D map complete."

echo ""
echo "=============================================="
echo "Post-processing finished successfully."
echo "Date: $(date)"
echo "=============================================="

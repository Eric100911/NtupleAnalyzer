#!/bin/bash
# ==============================================================================
# run_jjp_efficiency_cleanup.sh - Remove shard directories after validated merge
# ==============================================================================
# Runs inside run_wrapper.sh on a Condor worker node after the post-processing
# job succeeds. Validates that the merged output exists before removing shards.
#
# Usage:
#   run_jjp_efficiency_cleanup.sh SAMPLE SHARDS_DIR MERGED_DIR
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
echo "Efficiency Shard Cleanup"
echo "=============================================="
echo "Sample:      $SAMPLE"
echo "Shards dir:  $SHARDS_DIR"
echo "Merged dir:  $MERGED_DIR"
echo "Date:        $(date)"
echo "Host:        $(hostname)"
echo "=============================================="

# Validate merged output exists before removing shards
MARKER="$MERGED_DIR/$SAMPLE/efficiency_maps.parquet"
if [[ ! -f "$MARKER" ]]; then
    echo "ERROR: Merged output marker not found: $MARKER"
    echo "Refusing to clean shards. The merge may have failed."
    exit 1
fi

echo "Validation passed: $MARKER exists."

SHARD_PATTERN="$SHARDS_DIR/$SAMPLE/shard_*"
SHARD_COUNT=$(find "$SHARDS_DIR/$SAMPLE" -maxdepth 1 -type d -name "shard_*" 2>/dev/null | wc -l)

if [[ $SHARD_COUNT -eq 0 ]]; then
    echo "No shard directories found to remove."
    exit 0
fi

echo "Removing $SHARD_COUNT shard directories for $SAMPLE ..."
rm -rf "$SHARDS_DIR/$SAMPLE"/shard_*

REMAINING=$(find "$SHARDS_DIR/$SAMPLE" -maxdepth 1 -type d -name "shard_*" 2>/dev/null | wc -l)
if [[ $REMAINING -eq 0 ]]; then
    echo "Cleanup complete: all shard directories removed."
else
    echo "WARNING: $REMAINING shard directories could not be removed."
    exit 1
fi

echo "=============================================="
echo "Cleanup finished successfully."
echo "Date: $(date)"
echo "=============================================="

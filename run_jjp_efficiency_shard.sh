#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SAMPLE=""
SHARD_INDEX=""
SHARD_MANIFEST=""
OUTPUT_DIR="/eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/efficiency"
REMOTE_ACCESS_MODE="fallback"
EFFICIENCY_BACKEND="vectorized"
STAGE_RETRIES=3
COPY_TIMEOUT=180
WORKER_TIMEOUT=180
SKIP_PLOTS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sample) SAMPLE="$2"; shift 2 ;;
    --shard-index) SHARD_INDEX="$2"; shift 2 ;;
    --shard-manifest) SHARD_MANIFEST="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --remote-access-mode) REMOTE_ACCESS_MODE="$2"; shift 2 ;;
    --efficiency-backend) EFFICIENCY_BACKEND="$2"; shift 2 ;;
    --stage-retries) STAGE_RETRIES="$2"; shift 2 ;;
    --copy-timeout) COPY_TIMEOUT="$2"; shift 2 ;;
    --worker-timeout) WORKER_TIMEOUT="$2"; shift 2 ;;
    --skip-plots) SKIP_PLOTS=true; shift ;;
    -h|--help)
      echo "Usage: $0 --sample SAMPLE --shard-index N --shard-manifest FILE [options]"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [[ -z "$SAMPLE" || -z "$SHARD_INDEX" || -z "$SHARD_MANIFEST" ]]; then
  echo "Missing required --sample, --shard-index, or --shard-manifest"
  exit 1
fi

SHARD_TAG=$(printf "shard_%04d" "$SHARD_INDEX")
ARGS=(
  --input-file-manifest "$SHARD_MANIFEST"
  --samples "$SAMPLE"
  --output-dir "$OUTPUT_DIR/shards/$SAMPLE/$SHARD_TAG"
  --remote-access-mode "$REMOTE_ACCESS_MODE"
  --efficiency-backend "$EFFICIENCY_BACKEND"
  --stage-retries "$STAGE_RETRIES"
  --copy-timeout "$COPY_TIMEOUT"
  --worker-timeout "$WORKER_TIMEOUT"
)

if [[ "$SKIP_PLOTS" == true ]]; then
  ARGS+=(--skip-plots)
fi

./run_assoc_efficiency.sh "${ARGS[@]}"

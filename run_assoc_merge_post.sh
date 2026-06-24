#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MERGE_PLAN="$1"

if [[ -z "$MERGE_PLAN" ]]; then
    echo "Usage: $0 MERGE_PLAN_JSON"
    exit 1
fi

python3 merge_assoc_merge_shards.py --merge-plan "$MERGE_PLAN"

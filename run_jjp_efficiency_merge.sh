#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/chiw/mplconfig_ntuple_analyzer}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/chiw/pycache_ntuple_analyzer}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/chiw/xdg_cache_ntuple_analyzer}"

python3 merge_efficiency_shards.py "$@"

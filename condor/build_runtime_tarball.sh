#!/bin/bash
# ==============================================================================
# build_runtime_tarball.sh - Package analyzer source tree for Condor transfer
# ==============================================================================
# Packages tracked files plus untracked non-ignored source files so current
# uncommitted workflow code is included.  Excludes editor swap files and
# everything covered by .gitignore (build outputs, logs, etc.).
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

OUTPUT_DIR="${OUTPUT_DIR:-$SCRIPT_DIR/runtime}"
mkdir -p "$OUTPUT_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TARBALL_NAME="NtupleAnalyzer_runtime_${TIMESTAMP}.tar.gz"
RUNTIME_TARBALL="${OUTPUT_DIR}/${TARBALL_NAME}"

cd "$REPO_ROOT"

echo "[INFO] Packaging runtime tarball from: $PWD"
git ls-files -co --exclude-standard -z \
    ':!:condor/*.swp' \
    | tar --null -czf "$RUNTIME_TARBALL" --files-from=-

FILES_COUNT="$(git ls-files -co --exclude-standard ':!:condor/*.swp' | wc -l)"
SIZE="$(du -h "$RUNTIME_TARBALL" | cut -f1)"

echo "[INFO] Wrote: $RUNTIME_TARBALL"
echo "[INFO] Files: $FILES_COUNT, Size: $SIZE"

echo "$RUNTIME_TARBALL"

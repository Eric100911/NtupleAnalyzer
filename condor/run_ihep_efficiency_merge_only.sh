#!/bin/bash
# IHEP HepJob merge-only worker.  It consumes the frozen formal manifest and
# promotes exactly one verified sample bundle; it does not build maps or plots.

set -eo pipefail

TASK_FILE="${1:-}"
MERGE_INDEX="${2:-}"
if [[ ! -f "$TASK_FILE" || "$MERGE_INDEX" != 0 || "$TASK_FILE" != */tasks/*/merge_task.json ]]; then
    echo "Usage: $0 MERGE_TASK_FILE 0" >&2
    exit 2
fi
LCG_VIEW="${LCG_VIEW:-/cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt}"
test -f "$LCG_VIEW/setup.sh" || { echo "LCG 109a setup is unavailable" >&2; exit 1; }
# LCG setup may reference optional variables missing in a fresh HepJob shell.
# Do not enable nounset in this worker.
source "$LCG_VIEW/setup.sh"
python3 -c 'import ROOT; print(ROOT.gROOT.GetVersion())'
mapfile -t TASK < <(python3 - "$TASK_FILE" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
for key in ("sample", "shards_dir", "merge_parent", "final_sample_dir", "runtime_tarball", "formal_manifest", "formal_shards_dir", "shard_count", "proxy_path"):
    print(data[key])
PY
)
if [[ "${#TASK[@]}" -ne 9 ]]; then
    echo "Could not decode IHEP merge task" >&2
    exit 2
fi
SAMPLE="${TASK[0]}"; SHARDS_DIR="${TASK[1]}"; MERGE_PARENT="${TASK[2]}"; FINAL_SAMPLE_DIR="${TASK[3]}"
RUNTIME_TARBALL="${TASK[4]}"; FORMAL_MANIFEST="${TASK[5]}"; FORMAL_SHARDS_DIR="${TASK[6]}"; SHARD_COUNT="${TASK[7]}"; PROXY_PATH="${TASK[8]}"
if [[ ! "$SAMPLE" =~ ^[A-Za-z0-9][A-Za-z0-9_]*$ || ! "$SHARDS_DIR" = /scratchfs2/cms/wangchi/* || ! "$MERGE_PARENT" = /scratchfs2/cms/wangchi/* || ! "$FINAL_SAMPLE_DIR" = /scratchfs2/cms/wangchi/* ]]; then
    echo "Unsafe IHEP merge task paths" >&2
    exit 2
fi
if [[ ! "$PROXY_PATH" = /scratchfs2/cms/wangchi/* || ! -f "$PROXY_PATH" ]]; then
    echo "Non-IHEP or unreadable CMS VOMS proxy path" >&2
    exit 2
fi
if [[ -e "$FINAL_SAMPLE_DIR" || -L "$FINAL_SAMPLE_DIR" || -e "$MERGE_PARENT" || -L "$MERGE_PARENT" || ! -d "$SHARDS_DIR" || ! -f "$RUNTIME_TARBALL" || ! -f "$FORMAL_MANIFEST" || ! -d "$FORMAL_SHARDS_DIR" ]]; then
    echo "Existing final/merge root or missing strict merge input" >&2
    exit 2
fi
if [[ ! "$SHARD_COUNT" =~ ^[1-9][0-9]*$ ]]; then
    echo "Merge task has an invalid shard count" >&2
    exit 2
fi
for index in $(seq 0 $((SHARD_COUNT - 1))); do
    SHARD_DIR="$SHARDS_DIR/$(printf 'shard_%04d' "$index")"
    if [[ ! -f "$SHARD_DIR/.ready" ]]; then
        echo "Shard is not promoted and ready: $SHARD_DIR" >&2
        exit 2
    fi
done

ATTEMPT_ID="${HEP_JOB_ID:-${CLUSTER:-job}}_$(date +%Y%m%dT%H%M%S%N)_$$"
ATTEMPT_PARENT="${MERGE_PARENT}.attempt_${ATTEMPT_ID}"
[[ ! -e "$ATTEMPT_PARENT" && ! -L "$ATTEMPT_PARENT" ]] || { echo "Refusing merge attempt reuse" >&2; exit 2; }
mkdir "$ATTEMPT_PARENT"
TMP_PARENT="${TMPDIR:-/tmp}"
if [[ ! -d "$TMP_PARENT" || ! -w "$TMP_PARENT" ]]; then
    echo "Job-private TMPDIR parent is unavailable: $TMP_PARENT" >&2
    exit 1
fi
WORK_DIR=$(mktemp -d "$TMP_PARENT/ihep_efficiency_merge.XXXXXX")
trap 'rm -rf "$WORK_DIR"' EXIT
export MPLCONFIGDIR="$WORK_DIR/mplconfig"
export PYTHONPYCACHEPREFIX="$WORK_DIR/pycache"
export XDG_CACHE_HOME="$WORK_DIR/xdg_cache"
mkdir -p "$MPLCONFIGDIR" "$PYTHONPYCACHEPREFIX" "$XDG_CACHE_HOME"
tar -xzf "$RUNTIME_TARBALL" -C "$WORK_DIR"
MERGE_ENTRY="$WORK_DIR/scripts/efficiency/merge_efficiency_shards.py"
test -f "$MERGE_ENTRY" || { echo "Runtime tarball lacks merge entry point" >&2; exit 1; }
cd "$WORK_DIR"
export X509_USER_PROXY="$PROXY_PATH"
# Run the LCG python merge step inside the cmssw-el9 container, consistent
# with the shard worker.  The strict merge validates the frozen formal
# manifest (whose file URLs are CCEOS) and consumes the promoted local shards;
# running it in the container guarantees the same worker-node python/XRootD
# environment that provably reads CCEOS and avoids the bare-node ztn/TLS issue.
CMSSW_EL9="${CMSSW_EL9:-/cvmfs/cms.cern.ch/common/cmssw-el9}"
if [[ ! -x "$CMSSW_EL9" ]]; then
    echo "cmssw-el9 container wrapper is unavailable: $CMSSW_EL9" >&2
    exit 1
fi
CONTAINER_BINDS=(-B /tmp -B /scratchfs2)
if [[ "$TMP_PARENT" != /tmp && "$TMP_PARENT" != /scratchfs2 && "$TMP_PARENT" != /scratchfs2/* ]]; then
    CONTAINER_BINDS+=(-B "$TMP_PARENT")
fi
RUNNER="$WORK_DIR/merge_in_container.sh"
cat > "$RUNNER" <<EOF
#!/bin/bash
set -eo pipefail
cd "$WORK_DIR"
export X509_USER_PROXY="$PROXY_PATH"
source "$LCG_VIEW/setup.sh"
python3 "$MERGE_ENTRY" --sample "$SAMPLE" --shards-dir "$SHARDS_DIR" --output-dir "$ATTEMPT_PARENT" \\
    --formal-manifest "$FORMAL_MANIFEST" --formal-shards-dir "$FORMAL_SHARDS_DIR"
EOF
chmod +x "$RUNNER"
"$CMSSW_EL9" "${CONTAINER_BINDS[@]}" --command-to-run "bash $RUNNER"
EXPECTED_BUNDLE="$ATTEMPT_PARENT/$SAMPLE"
test -d "$EXPECTED_BUNDLE" && test -f "$EXPECTED_BUNDLE/sample_manifest.json" && test -f "$EXPECTED_BUNDLE/formal_merge_report.json" || { echo "Merge did not produce verified bundle" >&2; exit 1; }
python3 - "$EXPECTED_BUNDLE/sample_manifest.json" "$EXPECTED_BUNDLE/formal_merge_report.json" "$SAMPLE" <<'PY'
import json
import sys

manifest_path, report_path, sample = sys.argv[1:]
with open(manifest_path, encoding="utf-8") as handle:
    manifest = json.load(handle)
with open(report_path, encoding="utf-8") as handle:
    report = json.load(handle)
if manifest.get("sample") != sample or report.get("passed") is not True:
    raise SystemExit("merged bundle does not prove the requested formal merge")
PY
: > "$EXPECTED_BUNDLE/.ready"
mv -T --no-clobber "$EXPECTED_BUNDLE" "$FINAL_SAMPLE_DIR"
if [[ -e "$EXPECTED_BUNDLE" || -L "$EXPECTED_BUNDLE" || ! -f "$FINAL_SAMPLE_DIR/.ready" ]]; then
    echo "Merge promotion did not complete without replacement" >&2
    exit 1
fi
echo "[ihep-merge] atomically promoted: $FINAL_SAMPLE_DIR"

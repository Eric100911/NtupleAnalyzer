#!/bin/bash
# IHEP HepJob shard worker. Invocation is deliberately ``TASK_FILE INDEX`` so
# hep_sub sees a single ``-argu <idx>`` argument through its generated wrapper.

set -eo pipefail

TASK_FILE="${1:-}"
TASK_INDEX="${2:-}"
if [[ ! -f "$TASK_FILE" || ! "$TASK_INDEX" =~ ^[0-9]+$ ]]; then
    echo "Usage: $0 TASK_FILE SHARD_INDEX" >&2
    exit 2
fi
if [[ "$TASK_FILE" != */tasks/*/shard_tasks.json ]]; then
    echo "Unexpected IHEP task-file path" >&2
    exit 2
fi
LCG_VIEW="${LCG_VIEW:-/cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt}"
if [[ ! -f "$LCG_VIEW/setup.sh" ]]; then
    echo "LCG 109a setup is unavailable: $LCG_VIEW" >&2
    exit 1
fi
# The LCG setup script may read optional variables that are unset in a fresh
# HepJob shell. Do not enable nounset in this worker.
source "$LCG_VIEW/setup.sh"
python3 -c 'import ROOT; print(ROOT.gROOT.GetVersion())'
WORKSPACE="${TASK_FILE%%/tasks/*}"
mapfile -t TASK < <(python3 - "$TASK_FILE" "$TASK_INDEX" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
index = int(sys.argv[2])
matches = [x for x in data["tasks"] if x["index"] == index]
if len(matches) != 1:
    raise SystemExit("task index is missing or ambiguous")
for key in ("sample", "manifest", "campaign_root", "runtime_tarball", "efficiency_config", "proxy_path"):
    print(matches[0][key])
PY
)
if [[ "${#TASK[@]}" -ne 6 ]]; then
    echo "Could not decode IHEP shard task" >&2
    exit 2
fi
SAMPLE="${TASK[0]}"
MANIFEST="${TASK[1]}"
CAMPAIGN_ROOT="${TASK[2]}"
RUNTIME_TARBALL="${TASK[3]}"
EFFICIENCY_CONFIG="${TASK[4]}"
PROXY_PATH="${TASK[5]}"
if [[ ! "$SAMPLE" =~ ^[A-Za-z0-9][A-Za-z0-9_]*$ || ! "$CAMPAIGN_ROOT" = /scratchfs2/cms/wangchi/* ]]; then
    echo "Unsafe sample or non-IHEP campaign root" >&2
    exit 2
fi
if [[ ! "$PROXY_PATH" = /scratchfs2/cms/wangchi/* || ! -f "$PROXY_PATH" ]]; then
    echo "Non-IHEP or unreadable CMS VOMS proxy path" >&2
    exit 2
fi
if [[ ! -f "$MANIFEST" || ! -f "$RUNTIME_TARBALL" || ! -d "$CAMPAIGN_ROOT" ]]; then
    echo "IHEP task inputs are unavailable" >&2
    exit 2
fi

SHARD_TAG=$(printf 'shard_%04d' "$TASK_INDEX")
FINAL_DIR="$CAMPAIGN_ROOT/shards/$SAMPLE/$SHARD_TAG"
ATTEMPT_ID="${HEP_JOB_ID:-${CLUSTER:-job}}_$(date +%Y%m%dT%H%M%S%N)_$$"
ATTEMPT_DIR="$CAMPAIGN_ROOT/shards/$SAMPLE/.${SHARD_TAG}.attempt_${ATTEMPT_ID}"
if [[ -e "$FINAL_DIR" || -L "$FINAL_DIR" || -e "$ATTEMPT_DIR" || -L "$ATTEMPT_DIR" ]]; then
    echo "Refusing to reuse final or attempt path" >&2
    exit 2
fi
mkdir -p "$CAMPAIGN_ROOT/shards/$SAMPLE"
mkdir "$ATTEMPT_DIR"
TMP_PARENT="${TMPDIR:-/tmp}"
if [[ ! -d "$TMP_PARENT" || ! -w "$TMP_PARENT" ]]; then
    echo "Job-private TMPDIR parent is unavailable: $TMP_PARENT" >&2
    exit 1
fi
WORK_DIR=$(mktemp -d "$TMP_PARENT/ihep_efficiency_shard.XXXXXX")
trap 'rm -rf "$WORK_DIR"' EXIT
export MPLCONFIGDIR="$WORK_DIR/mplconfig"
export PYTHONPYCACHEPREFIX="$WORK_DIR/pycache"
export XDG_CACHE_HOME="$WORK_DIR/xdg_cache"
mkdir -p "$MPLCONFIGDIR" "$PYTHONPYCACHEPREFIX" "$XDG_CACHE_HOME"
tar -xzf "$RUNTIME_TARBALL" -C "$WORK_DIR"
RUNTIME_DIR="$WORK_DIR"
if [[ ! -f "$RUNTIME_DIR/run_efficiency.py" || ! -f "$RUNTIME_DIR/$EFFICIENCY_CONFIG" ]]; then
    echo "Runtime tarball lacks run_efficiency.py or the strict config" >&2
    exit 1
fi
cd "$RUNTIME_DIR"
export X509_USER_PROXY="$PROXY_PATH"
# The bare EL9 worker-node XRootD client cannot authenticate to CCEOS
# (ztn/TLS -> 3010), while the cmssw-el9 container's XRootD reads it fine.
# Verified on IHEP compute nodes: uproot (LCG 109a) inside cmssw-el9 opens
# root://cceos... ntuples directly, so the whole CCEOS-reading efficiency step
# runs inside the container.  Mount /tmp and /scratchfs2 (plus a job-private
# TMP_PARENT when it is elsewhere) so the extracted runtime, manifests, proxy,
# and attempt output keep identical paths inside the container.
CMSSW_EL9="${CMSSW_EL9:-/cvmfs/cms.cern.ch/common/cmssw-el9}"
if [[ ! -x "$CMSSW_EL9" ]]; then
    echo "cmssw-el9 container wrapper is unavailable: $CMSSW_EL9" >&2
    exit 1
fi
CONTAINER_BINDS=(-B /tmp -B /scratchfs2)
if [[ "$TMP_PARENT" != /tmp && "$TMP_PARENT" != /scratchfs2 && "$TMP_PARENT" != /scratchfs2/* ]]; then
    CONTAINER_BINDS+=(-B "$TMP_PARENT")
fi
RUNNER="$WORK_DIR/run_efficiency_in_container.sh"
cat > "$RUNNER" <<EOF
#!/bin/bash
set -eo pipefail
cd "$RUNTIME_DIR"
export X509_USER_PROXY="$PROXY_PATH"
source "$LCG_VIEW/setup.sh"
python3 run_efficiency.py \\
    --input-file-manifest "$MANIFEST" --samples "$SAMPLE" --output-dir "$ATTEMPT_DIR" \\
    --remote-access-mode direct --efficiency-backend vectorized --tree-path auto \\
    --efficiency-config "$EFFICIENCY_CONFIG" --config-policy strict --skip-plots \\
    --stage-mode never --stage-dir "$WORK_DIR/stage"
EOF
chmod +x "$RUNNER"
"$CMSSW_EL9" "${CONTAINER_BINDS[@]}" --command-to-run "bash $RUNNER"
SUCCESS_MANIFEST="$ATTEMPT_DIR/$SAMPLE/sample_manifest.json"
python3 - "$SUCCESS_MANIFEST" "$SAMPLE" <<'PY'
import json
import sys
path, sample = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)
coverage = payload.get("coverage")
if payload.get("sample") != sample or not isinstance(payload.get("n_input_files"), int) or payload["n_input_files"] <= 0:
    raise SystemExit("nested sample manifest has an invalid sample or file count")
if not isinstance(coverage, dict) or not isinstance(coverage.get("n_processed_files"), int) or coverage["n_processed_files"] <= 0:
    raise SystemExit("nested sample manifest lacks successful coverage")
PY
# Readiness is inside the directory being renamed, so a merge gate never sees
# a promoted shard whose readiness marker is still pending.
: > "$ATTEMPT_DIR/.ready"
mv -T --no-clobber "$ATTEMPT_DIR" "$FINAL_DIR"
if [[ -e "$ATTEMPT_DIR" || -L "$ATTEMPT_DIR" || ! -f "$FINAL_DIR/.ready" ]]; then
    echo "Shard promotion did not complete without replacement" >&2
    exit 1
fi
echo "[ihep-shard] atomically promoted: $FINAL_DIR"

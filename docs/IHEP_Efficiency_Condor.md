# IHEP-local HepJob efficiency workspace generation

Use this path for IHEP HepJob when direct CCEOS input reads are wanted. It is
independent of the CERN generator and only creates a static workspace; it never
invokes `hep_sub` or `condor_submit_dag`.

Prepare the queue with the existing shard preparer. Its manifest URLs must use
the triple-slash `root://cceos.ihep.ac.cn:1094///store/...` form. Both campaign
root and workspace must be new children of `/scratchfs2/cms/wangchi`; `/publicfs`
is prohibited. The campaign root itself must already exist.

```bash
python3 scripts/efficiency/prepare_efficiency_shards.py \
  --samples JJP_DPS1 \
  --input-file-manifest configs/efficiency/manifests/JJP_DPS1.manifest.json \
  --files-per-job 10 \
  --output-dir /scratchfs2/cms/wangchi/queues/queue_JJP_DPS1

python3 condor/generate_ihep_efficiency_dag.py \
  --sample JJP_DPS1 \
  --queue-file /scratchfs2/cms/wangchi/queues/queue_JJP_DPS1/manifests/jjp_efficiency_queue.txt \
  --formal-manifest configs/efficiency/manifests/JJP_DPS1.manifest.json \
  --ihep-campaign-root /scratchfs2/cms/wangchi/efficiency_campaign_YYYYMMDD \
  --runtime-tarball /scratchfs2/cms/wangchi/bundles/NtupleAnalyzer_runtime.tar.gz \
  --workspace-dir /scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/runs/20260830/JJP_DPS1 \
  --tree-path auto \
  --efficiency-config configs/efficiency/tps_nominal.yaml \
  --config-policy strict \
  --efficiency-backend vectorized \
  --remote-access-mode direct \
  --skip-plots \
  --submission-retries 2
```

Inspect the generated `workflow.json` and `scripts/submit_*.sh` before any
separately authorized, manual scheduler submission. Those scripts use the IHEP
HepJob contract: `hep_sub -g cms -gwn CMS -wt mid -argu <idx> -n 1`, with
persistent logs under the workspace. The workers source LCG 109a themselves and
read CCEOS directly. Reading CCEOS content requires a valid CMS VOMS proxy —
workers must have one, or every read fails with `[3010] Operation not
permitted`. See `IHEP_X509_Proxy_Guidelines.md` for proxy resolution, checking,
distribution, and the `unset X509_USER_PROXY` bug. Workers do not use a CERN
JobFlavour or the CERN EOS convention.

## Container requirement for CCEOS reads

On the EL9 **compute nodes** the bare worker-node XRootD client cannot
authenticate to CCEOS. Both the C++ client (`xrdcp`) and the Python stack
(`uproot`/fsspec-xrootd via LCG 109a) fail identically with:

```
security protocol 'ztn' disallowed for non-TLS connections.
[ERROR] Server responded with an error: [3010] Unable to open file /store/... ; Operation not permitted
```

This is a client-library defect on the worker node; `XrdSecPROTOCOL=gsi` (or
`unix,gsi`) and `/etc/xrootd/client.conf` changes do not help. The same proxy,
the same LCG 109a view, and the same `uproot.open()` work on the IHEP login
node.

The fix (verified on IHEP compute nodes such as `cws051.ihep.ac.cn`) is to run
the CCEOS read inside the **cmssw-el9 container**
(`/cvmfs/cms.cern.ch/common/cmssw-el9`): inside the container both `xrdcp` and
`uproot` (LCG 109a) open `root://cceos.ihep.ac.cn:1094///store/...` directly
with the same proxy. No `LD_LIBRARY_PATH` override is needed — LCG's own
`libXrdCl` authenticates correctly inside the container.

The shard and merge workers therefore run their entire LCG python step inside
the container:

```
/cvmfs/cms.cern.ch/common/cmssw-el9 -B /tmp -B /scratchfs2 [-B "$TMP_PARENT"] \
    --command-to-run "bash <job-private>/run_*_in_container.sh"
```

The runner script is written by the worker into its job-private `$WORK_DIR`
(below `$TMPDIR` or `/tmp`) and does `cd "$RUNTIME_DIR"`,
`export X509_USER_PROXY="$PROXY_PATH"`, `source <LCG>/setup.sh`, then the
python command. `/tmp` and `/scratchfs2` (plus a non-standard `$TMPDIR` parent,
when it is neither) are bind-mounted so the extracted runtime, the shard/merge
manifests, the proxy, the Python/Matplotlib caches, and the attempt/output dir
keep identical paths inside the container. `cmssw-env` wraps
`--command-to-run` in `bash -c '...'`, so the worker passes a bare
`bash <path>` and never embeds single quotes in the command. The container path
is overridable through the `CMSSW_EL9` environment variable (used by the tests
to inject a pass-through wrapper).

The fail-closed validation, fresh-attempt semantics, and atomic `.ready`
promotion are unchanged; the proxy still lives at
`export X509_USER_PROXY="$PROXY_PATH"` (a `/scratchfs2/cms/wangchi` path that
is readable inside the container).

Each shard writes an attempt-specific directory and promotes it only after its
nested `<attempt>/<sample>/sample_manifest.json` proves matching sample and
successful coverage, then atomically creates `<campaign>/shards/<sample>/shard_XXXX/.ready`. It uses
only a job-private directory below `$TMPDIR` (or `/tmp`) for extraction and all
Matplotlib/Python caches—never `/tmp/chiw`.

`--submission-retries` applies only to a failed `hep_sub` acceptance call. It
does not automatically rerun a job that was accepted and later failed. After
inspection, `scripts/plan_missing_shards.sh` prints missing shard indices for a
separately authorized, manual missing-only recovery plan. `submit_merge.sh` is
the sole dependent MERGE action: it requires all sentinels, passes the frozen
formal manifest to the strict merge, and atomically promotes the verified final
sample bundle. Existing final, merge, shard, workspace, and attempt paths are
blockers; no worker deletes or overwrites them.

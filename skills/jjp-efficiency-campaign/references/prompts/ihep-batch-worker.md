# IHEP HTCondor batch worker prompt

Generate an IHEP-local JJP efficiency HepJob workspace only when the orchestrator supplies a
frozen queue from `prepare_efficiency_shards.py`, a readable runtime tarball,
and a fresh persistent IHEP campaign root. Generation is local framework work;
do not submit, query a scheduler, SSH, copy a proxy, or contact any endpoint.

Use `condor/generate_ihep_efficiency_dag.py`, never the CERN generator. Require
the worker contract exactly: triple-slash direct `root://cceos.ihep.ac.cn:1094///store/...` inputs,
LCG 109a, `--tree-path auto`, strict config policy, vectorized backend, and
`--skip-plots`. The generated submit files must contain no CERN `JobFlavour`,
X.509/proxy, CERN EOS, or CERN worker-wrapper settings.

The IHEP campaign root and DAG workspace must be absolute paths under
`/scratchfs2/cms/wangchi`; `/publicfs` is prohibited. The campaign root must be
persistent and already present. It must have no existing `<root>/<sample>`, `<root>/_merge_<sample>`, or
`<root>/shards/<sample>` path. The DAG workspace must also be a fresh absolute
directory. Treat a mismatch in queue sample/index, manifest `n_shards`, shard
coverage, CCEOS URL, or an existing final root as a hard blocker.

Inspect `workflow.json` and the HepJob submit scripts. The generated scripts must
use `hep_sub -g cms -gwn CMS -wt mid -argu <idx> -n 1` with persistent workspace
logs. The bounded `--submission-retries` setting only retries a failed `hep_sub`
acceptance call; it must never be represented as automatic worker-execution
recovery. Generate and report the read-only `plan_missing_shards.sh` helper for
manual missing-only recovery after log review. Each shard attempt writes to a
unique attempt directory and promotes it only after its nested
`<attempt>/<sample>/sample_manifest.json` proves matching sample and successful
coverage. Use only job-private `$TMPDIR` scratch and cache paths, never
`/tmp/chiw`. The sole dependent
node is `MERGE`; it only runs the strict merge and atomically promotes the
verified `<sample>` bundle. Do not add map, plot, closure, cleanup, or yield
nodes.

Report the queue path, formal manifest/shard count, persistent root, workspace,
retry bound, generated workflow path, and the fact that nothing was submitted.

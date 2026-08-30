# Agent architecture

## Site boundary

```text
checked-in manifests + frozen repo/config
                 |
                 v
lxplus: audit -> one-file preflight -> shard/DAG -> Condor -> strict merge
                 |                       ^                 |
                 |              background monitor        |
                 v                                         v
          checksumed compact handoff ---------------> hepthu-el9
                                                       maps/closure/QA
                                                             |
                                                             v
                                                  independent validation
```

The default handoff is merged Parquet/JSON/CSV metadata and small required
ROOT/plot artifacts, not raw ntuples or unverified shards. Keep raw XRootD reads
and per-file preprocessing on lxplus. Run derived products, factorized/hybrid
maps, closure, QA, systematics, and requested corrected-yield work on hepthu.

## Agents

| Agent | Prompt | Responsibility | Live mutation |
|---|---|---|---|
| Orchestrator | `prompts/orchestrator.md` | State, approvals, dispatch, report | Per gate only |
| Manifest auditor | `prompts/manifest-auditor.md` | Freeze inputs, hashes, totals | No |
| lxplus preflight | `prompts/lxplus-preflight.md` | Strict one-file tests | Temp outputs |
| lxplus batch worker | `prompts/lxplus-batch-worker.md` | Prepare/submit DAGs | Bounded |
| Background monitor | `prompts/background-monitor.md` | Persistent read-only snapshots | No |
| Handoff worker | `prompts/handoff-worker.md` | Package, transfer, verify | Fresh destination |
| hepthu worker | `prompts/hepthu-analysis-worker.md` | Downstream analysis/logs | Fresh destination |
| Validation worker | `prompts/validation-worker.md` | Independent acceptance audit | Report only |
| Recovery worker | `prompts/recovery-worker.md` | Diagnose/minimum retry plan | Separate approval |

Workers never spawn competing orchestrators. Start the monitor immediately
after the first asynchronous submission or remote launch and leave it delegated
in the background. The orchestrator continues normally and never tails logs.

## Background monitoring

Each iteration runs a one-shot probe, atomically writes a timestamped JSON
snapshot, compares it with the prior snapshot, emits only transitions or
actionable anomalies, then waits. The wait happens in a delegated agent or
detached watcher, never in the user's terminal. A failed/empty query is
`unknown`, not zero completed. Use bounded SSH timeouts.

Use about 5 minutes while jobs are active and 15 minutes during quiet remote
analysis. Stop after success, an actionable blocker, loss of campaign identity,
or an orchestrator stop message. A detached watcher records its PID/session,
heartbeat, atomic snapshots, and append-only alerts; the monitor agent consumes
those files without changing live work.

## Reference-script lessons

`../Full_MC_Production/skills/` supplies useful patterns: frozen manifests,
one-shot JSON audits, explicit schedd/cluster identity, persistent remote logs,
and detached `nohup`. Do not copy IHEP HepJob/proxy/AVX2 scripts. Its
`dag_snapshot.py` depends on a missing `tools/dag_progress.py` and cannot be
migrated alone.

Future SSH helpers must pass restricted arguments or use `shlex.quote`; never
interpolate arbitrary JSON into a remote shell. Record PID, host, start time,
command hash, persistent log, and a duplicate-launch lock.

## Gaps to close before submission

- Stock DAG POST also builds plots/maps. Split it so CERN ends after a strict
  per-sample merge and hepthu performs downstream analysis.
- Shard JSON under submit-host `/tmp` is not transferred in the generated
  `.sub`. Transfer it explicitly and use its basename, or use a verified shared
  path.
- Six POST jobs cannot share one output root because top-level merge files race.
  Use per-sample CERN roots and consolidate on hepthu.
- Do not use `condor/submit.sh jjp_efficiency_dag`: it omits strict arguments
  and forces submission. Generate, inspect, then submit normally.
- Do not use hard-coded `all`; enumerate all six manifests, including TPS.
- Default to no cleanup. Existing cleanup acceptance is too weak.

## Launch order

1. Audit and freeze manifests/provenance.
2. Strict one-file preflight for every selected sample.
3. Review static shard/DAG plan and request submission authorization.
4. Submit per-sample DAGs and record schedd, IDs, paths, and hashes.
5. Delegate the background monitor and return the main loop immediately.
6. Strictly merge and validate each sample on lxplus.
7. Transfer and read back checksumed compact products.
8. Launch hepthu analysis with persistent logs and a lock.
9. Independently validate coverage, maps, closure, QA, and provenance.
10. Mark complete only when every selected sample passes.

In architecture-only mode, read all contracts needed to produce an in-memory
plan, but do not initialize a ledger, generate DAGs/reports, make output paths,
test SSH, inspect remote repositories, submit Condor, start monitors, or run
analysis. Editing this reusable skill itself is allowed only when the user's
request is to create or revise the architecture/prompt files.

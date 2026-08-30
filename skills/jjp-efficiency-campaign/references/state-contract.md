# Campaign state contract

The JSON ledger created by `scripts/campaignctl.py` is coordination metadata,
not a substitute for source/output manifests. Only the orchestrator advances
it; workers write reports and monitor snapshots separately.

## States

```text
draft -> inputs_frozen -> lxplus_preflight_passed -> lxplus_submitted
      -> lxplus_merged -> handoff_verified -> hepthu_analysis_started
      -> validation_running -> complete
```

Any non-terminal state may enter `blocked`. That records evidence and asks for
a decision; it is not permission to retry.

## Gate evidence

- `inputs_frozen`: samples, manifest paths/IDs/totals, repo SHA, YAML hash, LCG
  view, output roots, batch ID.
- `lxplus_preflight_passed`: one-file result per sample, tree/config resolution,
  strict-policy result, coverage row, retained comparison, definition and
  compatibility hashes.
- `lxplus_submitted`: schedd, top DAG ID per sample, DAG path, shard count,
  immutable output, submission time, runtime hash.
- `lxplus_merged`: complete sample manifests; expected/observed file, entry and
  retained totals; unique production/definition hashes; no duplicate/failures.
- `handoff_verified`: transferred relative paths, sizes/SHA-256, exact roots,
  transfer command, and destination readback.
- `hepthu_analysis_started`: remote SHA, LCG view, PID, command hash, start time,
  persistent log, lock, exact input/output paths.
- `validation_running`: report path and products under review.
- `complete`: validation report, closure summaries, failed lookups, limitations,
  and final paths.

Campaign identity hashes `(campaign_id, campaign_config_sha256, repo_sha,
efficiency_config_sha256, LCG view, {sample: manifest_id})`; the frozen config
contains site roots, sharding, and automatic retry bound. Never choose a result
by "latest". Retries use new attempt directories and preserve failures. Cleanup
is not normal completion.

Every worker report includes `task_id`, `role`, `campaign_id`, `host`,
authorization, times, status, commands planned/run, input hashes, evidence,
artifacts/checksums, next-state recommendation, blockers, and mutation status.

Start with `campaign-config.example.json`. Never store secrets, private keys,
proxy files, or host-key material in campaign state.

## Ledger commands

Copy and fill the example config. Run `campaignctl.py validate --config ...
--repo-root .` for a strict no-write plan/identity check. Then initialize a new
ledger (the command
refuses to overwrite an existing state file):

```bash
python3 skills/jjp-efficiency-campaign/scripts/campaignctl.py init \
  --config /path/to/campaign-config.json \
  --state /path/to/campaign/state.json \
  --repo-root .
```

Inspect it with `campaignctl.py show --state ...`. After validating a worker's
machine-readable report, the orchestrator advances exactly one gate:

```bash
python3 skills/jjp-efficiency-campaign/scripts/campaignctl.py advance \
  --state /path/to/campaign/state.json \
  --to inputs_frozen \
  --expected-revision 0 \
  --report /path/to/campaign/reports/manifest-auditor.json
```

`advance` requires a report bound to the ledger's campaign identity hash,
approved role and next state, gate-specific evidence, artifact checksums, and
mutation authorization. It records the report SHA-256 under a locked,
compare-and-swap state revision. `campaignctl.py` performs no remote or batch
operation.

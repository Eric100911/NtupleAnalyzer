---
name: jjp-efficiency-campaign
description: Plan, launch, monitor, hand off, and validate manifest-driven JJP efficiency campaigns split between CERN lxplus/HTCondor preprocessing and hepthu-el9 analysis. Use for checked-in TPS efficiency manifests; do not use for MC production or one-off local plots.
---

# JJP Efficiency Campaign

Use `configs/efficiency/manifests/*.manifest.json` as the input authority. This
workflow is currently specialized to the JJP efficiency samples.

## Choose the mode

- For architecture or dry-run planning, read
  [references/architecture.md](references/architecture.md) and do not connect to
  either site.
- For a live campaign, first read
  [references/state-contract.md](references/state-contract.md), then use
  [references/prompts/orchestrator.md](references/prompts/orchestrator.md).
- Load a worker prompt only when dispatching that worker.

## Campaign rules

1. Freeze manifest IDs, repository Git SHA, efficiency YAML hash, and LCG view
   before submission.
2. Source LCG 109a in the same shell as every Python/ROOT/Parquet command.
3. lxplus performs raw ROOT access, strict preflight, sharded preprocessing, and
   fail-closed merge. hepthu-el9 consumes verified compact handoff products for
   maps, closure, QA, systematics, and requested yield work.
4. Use fresh output directories. Never silently reuse, clean, or overwrite an
   earlier batch on either site.
5. Treat preflight output creation, batch/DAG preparation, detached watcher
   launch, SSH writes, transfer, repo updates, Condor mutations, cleanup, manual
   retries, and remote launch as external mutations. Obtain authorization for
   the relevant scope immediately before the action. A bounded DAGMan `RETRY N`
   policy is allowed only when shown in the static plan and explicitly included
   in submission authorization; any retry beyond that bound is a new gate.
6. Start a read-only background monitor once live work starts. It runs as a
   separate delegated agent and never occupies the orchestrator's main loop.
7. The monitor cannot submit, release, retry, remove, kill, clean, update a
   repository, or repair output. Route recovery through the orchestrator.
8. Record hepthu-el9 Git SHA and dirty status first. Do not pull or rsync over a
   dirty clone. Prefer a campaign worktree or immutable source bundle when the
   revisions differ.
9. Full coverage, compatible hashes, successful merge, verified transfer, and
   independent validation are hard gates.
10. Keep the orchestrator's main loop off complex remote debugging and iterative
    fixes (SSH diagnostics, diagnostic job submission, trial-and-error repair).
    Delegate that work to a worker subagent, and escalate to a higher-tier model
    (deepseek-v4-pro) when a problem is complex or has failed repeatedly — do not
    debug it in the main conversation, and do not restrict complex work to
    lightweight worker models.

## Local helper

`scripts/campaignctl.py` validates manifests and maintains an atomic local JSON
ledger. It does not SSH, submit jobs, or start analysis.

Use `docs/TPS_Efficiency_Processing.md` for physics commands and
`docs/Efficiency_scheme.md` for the mathematical definition.

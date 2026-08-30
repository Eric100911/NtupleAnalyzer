# TPS Efficiency Processing Runbook

This runbook is the operational contract for the TPS-Onia2MuMu JJP efficiency
sample. It complements [Efficiency_Evaluation_Guideline.md](Efficiency_Evaluation_Guideline.md);
the mathematical definitions remain in [Efficiency_scheme.md](Efficiency_scheme.md).

## Nominal contract

Use sample name `JJP_TPS_MC_v4_1`, the versioned definition
[`configs/efficiency/tps_nominal.yaml`](../configs/efficiency/tps_nominal.yaml),
`--tree-path auto`, and `--config-policy strict`.

The input resolver accepts exactly one of `X_data` and `mkcands/X_data`, then
finds the sibling `X_config`. Strict mode requires the retained-single-object
Run-B layout:

- `KeepAllSingleObjectCandsInMC=True`
- `SkipCompositeCandBuildingWhenKeepingSingles=False`
- `RequireAcceptedCandidatesForMonteCarloTree=False`
- all single-object, composite, trigger-match, `DiOnia_*`, and `Pri_*` branches

Production compatibility is deliberately limited to direct checks: boolean run
mode flags and numeric mass/track-pT cuts. More involved quality relationships
are recorded, not inferred as production vetoes.

The nominal event endpoint is `Pri_assocPVPass`. The nominal four-muon vertex is
`DiOnia_fitValid && DiOnia_fitPass` on the same composite-candidate axis as the
trigger and `Pri_*` checks. These alternatives are QA only:

- common muon `muVertexId`
- `DiOnia_commonRecVtxPass`
- `DiOnia_passAny`
- `DiOnia_VtxProb > 0.005`

Trigger paths and filters are resolved by name from `X_config`; their stored
order is not assumed. The two configured rules are a Dimuon0 pair plus a third
matched muon, or a DoubleMu matched pair.

GEN denominators use final J/psi particles with two direct muon daughters and
final phi particles with two direct kaon daughters. Parent PDG IDs and daughter
validity are stored as ancestry QA; no feed-down parent veto is applied.

## Environment

Run Python, ROOT, and Parquet commands in LCG 109a:

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
```

Use new output directories. Do not overwrite an existing merged efficiency
sample or closure result.

## 1. Build and verify the master manifest

The current inventory contract is 317 files, 1,472,109 entries, and 93,901
retained candidate events.
Here, retained means an event with at least one stored `Pri_passAny` candidate
(`Pri_fitPass || Pri_assocPVPass`); it is coverage bookkeeping, not a map cut.

```bash
python3 scripts/efficiency/prepare_tps_efficiency_manifest.py \
  docs/tps_retained_ntuple_events.txt \
  --sample JJP_TPS_MC_v4_1 \
  --output configs/efficiency/manifests/JJP_TPS_MC_v4_1.manifest.json
```

The generated manifest is versioned, carries a content-derived master manifest
ID, and formally names the third inventory column
`retained_candidate_events`.

## 2. One-file preflight

Run one file through the production backend before creating the batch:

```bash
python3 run_efficiency.py \
  --analysis-mode JpsiJpsiPhi \
  --input-file-manifest configs/efficiency/manifests/JJP_TPS_MC_v4_1.manifest.json \
  --samples JJP_TPS_MC_v4_1 \
  --max-files 1 \
  --tree-path auto \
  --efficiency-config configs/efficiency/tps_nominal.yaml \
  --config-policy strict \
  --output-dir /tmp/chiw/tps_efficiency_preflight \
  --skip-plots
```

Accept the preflight only if:

- the file has one successful row in `file_coverage.parquet`;
- `entries_scanned == source_entries == expected_total_entries`;
- the observed retained-candidate count matches the inventory;
- `configuration_metadata.json` contains the full `X_config` snapshot,
  resolved trigger/filter indices, compatibility hash, and efficiency-definition
  hash;
- `four_muon_definition_comparison.csv` contains the nominal/diagnostic
  comparison;
- `gen_ancestry_qa.parquet` has plausible J/psi and phi parent/daughter counts.

The `--max-files 1` result is intentionally marked partial. Partial products
may be inspected and mapped, but must not be presented as the complete sample.

An optional branch-level audit can be made in another new directory:

```bash
python3 scripts/efficiency/audit_efficiency_events.py \
  --input-file-manifest configs/efficiency/manifests/JJP_TPS_MC_v4_1.manifest.json \
  --tree-path auto \
  --max-events 2000 \
  --output-dir /tmp/chiw/tps_efficiency_audit \
  --fail-on-issues
```

## 3. Prepare shards and DAG

Ten files per shard gives 32 shard jobs for the 317-file inventory:

```bash
python3 scripts/efficiency/prepare_efficiency_shards.py \
  --samples JJP_TPS_MC_v4_1 \
  --input-file-manifest configs/efficiency/manifests/JJP_TPS_MC_v4_1.manifest.json \
  --files-per-job 10 \
  --output-dir /tmp/chiw/tps_efficiency_batch
```

Create the DAG with strict TPS arguments embedded in every shard:

```bash
python3 condor/generate_efficiency_dag.py \
  --sample JJP_TPS_MC_v4_1 \
  --queue-file /tmp/chiw/tps_efficiency_batch/manifests/jjp_efficiency_queue.txt \
  --output-dir /eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/tps_efficiency_YYYYMMDD \
  --runtime-tarball /path/to/ntuple_analyzer_runtime.tar.gz \
  --dag-dir /tmp/chiw/tps_efficiency_batch/dag \
  --tree-path auto \
  --efficiency-config configs/efficiency/tps_nominal.yaml \
  --config-policy strict \
  --remote-access-mode fallback \
  --efficiency-backend vectorized
```

Inspect the generated submit files before `condor_submit_dag`. Do not request
shard cleanup until the merged coverage and configuration checks have passed.

## 4. Merge and build maps

The DAG post node runs `run_jjp_efficiency_post.sh`, which merges the shards,
builds derived products, builds factorized maps, and builds the hybrid
post-acceptance map.

The merge is fail-closed for duplicate or missing declared files, incomplete
entry scans, incompatible production configurations, different efficiency
definition hashes, and disagreement about the master manifest. Its
`sample_manifest.json` records `coverage_scope=complete` only when all 317
master files are present.

Key merged artifacts are:

- `file_coverage.parquet`: one successful row per source file
- `configuration_metadata.json`: all per-file snapshots plus unique production
  configurations
- `gen_ancestry_qa.parquet`
- `gen_systems.parquet` and `event_step_flags.parquet`
- `efficiency_maps.parquet`, derived products, and `maps/*.parquet`

Before using the maps, verify totals in the merged coverage table:

```bash
python3 - <<'PY'
import pandas as pd
p = "/path/to/merged/JJP_TPS_MC_v4_1/file_coverage.parquet"
x = pd.read_parquet(p)
print("files", len(x))
print("entries", int(x.entries_scanned.sum()))
print("retained", int(x.retained_candidate_events.sum()))
print("scope", sorted(x.coverage_scope.unique()))
print("statuses", x.status.value_counts().to_dict())
PY
```

Expected inventory totals are 317, 1,472,109, and 93,901 respectively.

## 5. Independent file-disjoint closure

Build maps on a deterministic set of complete source files and evaluate the
correction on a disjoint approximately 20% holdout:

```bash
python3 -m efficiency_workflow.closure \
  --input-dir /path/to/merged \
  --samples JJP_TPS_MC_v4_1 \
  --map-type factorized \
  --selected-col Pri_assocPVPass \
  --file-disjoint \
  --holdout-modulus 5 \
  --holdout-remainder 0 \
  --n-min-fine 30 \
  --n-min-coarse 50
```

Repeat with `--map-type hybrid` in a distinct output directory if the hybrid
result is required. The closure manifest stores the exact training and holdout
file lists. The command refuses to overwrite a non-empty closure directory.

Review the corrected/GEN ratio and failed-lookup count together. Low-stat bins
may fall back from fine to coarse to inclusive maps; a large lookup failure
count is not an acceptable closure result.

## 6. Data-side boundary

TPS raw `X_data` is an MC efficiency input. It is not the selected data schema
used by the yield code. Yield correction still requires the Pipeline 1 selected
ROOT tree with `sel_*` kinematics and sWeights. Apply the TPS maps to that
selected data input with the preferred `factorized` mode; use `hybrid` as the
specified alternative. Do not pass raw TPS ROOT files to
`compute_efficiency_corrected_yield.py`.

## 7. Other JJP subprocesses

The strict TPS processing contract is also applicable to the existing
`JJP_DPS1`, `JJP_DPS2_CS`, `JJP_DPS2_G`, `JJP_SPS_CS`, and `JJP_SPS_G`
manifests. A one-file preflight on 2026-08-30 found that every sample:

- resolved `mkcands/X_data` and its sibling `mkcands/X_config`;
- contained the complete strict Run-B branch set;
- passed production-configuration validation without warnings;
- resolved both configured trigger/filter requirements; and
- had the same production compatibility hash.

The full vectorized event processor also completed on one file from every
subprocess:

| Sample | Entries scanned | Full GEN systems | `Pri_assocPVPass` |
|--------|----------------:|-----------------:|------------------:|
| `JJP_DPS1` | 4,300 | 436 | 9 |
| `JJP_DPS2_CS` | 5,000 | 428 | 4 |
| `JJP_DPS2_G` | 400 | 47 | 1 |
| `JJP_SPS_CS` | 3,654 | 150 | 3 |
| `JJP_SPS_G` | 802 | 96 | 3 |

These are smoke-test populations, not efficiency measurements. They establish
schema and execution portability but do not replace complete-sample map and
closure validation. In particular, `JJP_DPS2_G` and `JJP_SPS_G` have only
13,543 and 10,147 retained candidate events in their complete manifests. Their
fine bins will frequently need coarse or inclusive fallback, so do not treat
them like the high-statistics CS samples in ratio-panel comparisons.

Use each sample's formal manifest and a fresh output directory. For example:

```bash
python3 run_efficiency.py \
  --analysis-mode JpsiJpsiPhi \
  --input-file-manifest configs/efficiency/manifests/JJP_SPS_CS.manifest.json \
  --samples JJP_SPS_CS \
  --max-files 1 \
  --tree-path auto \
  --efficiency-config configs/efficiency/tps_nominal.yaml \
  --config-policy strict \
  --output-dir /tmp/chiw/jjp_sps_cs_efficiency_preflight \
  --skip-plots
```

Repeat without `--max-files` only after the preflight passes. The merge checks
configuration compatibility within a subprocess. When comparing maps across
subprocesses, also inspect the recorded configuration hashes and run the
self/cross or file-disjoint closure rather than assuming compatible production
implies interchangeable efficiencies.

Vectorized rapidity evaluation may emit divide-by-zero warnings for zero or
massless intermediate GEN entries because both branches of the masked
expression are evaluated. Invalid rapidities are masked to `NaN`; nevertheless,
review unexpected warning growth and failed map lookups in full production logs.

## Legacy compatibility

Existing old-scheme commands that omit `--efficiency-config` retain legacy
configuration policy. TPS production must pass the YAML explicitly and use
strict mode. This keeps the smooth legacy workflow working while preventing a
TPS job from silently using hardcoded trigger order, the old tree path, or a
partial Run-B schema.

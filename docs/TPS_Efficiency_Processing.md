# JJP Efficiency Processing Runbook

This runbook is the operational contract for every JJP subprocess sample in
`configs/efficiency/manifests/`. All samples use the same versioned efficiency
definition and the same preflight, shard, merge, map, and closure stages. The
common input contract is the TPS-Onia2MuMu ntuple format. It complements
[Efficiency_Evaluation_Guideline.md](Efficiency_Evaluation_Guideline.md); the
mathematical definitions remain in [Efficiency_scheme.md](Efficiency_scheme.md).

## Common processing contract

Set `SAMPLE` to one of the checked-in sample labels:

```text
JJP_DPS1 JJP_DPS2_CS JJP_DPS2_G JJP_SPS_CS JJP_SPS_G JJP_TPS_MC_v4_1
```

Use that sample's manifest, the versioned definition
[`configs/efficiency/tps_nominal.yaml`](../configs/efficiency/tps_nominal.yaml),
`--tree-path auto`, and `--config-policy strict` for every sample.

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

## 1. Select and verify the sample manifest

Use the checked-in manifest for the selected sample. The current inventories
are:

| Sample | Manifest | Files | Total entries | Retained candidate events |
|--------|----------|------:|--------------:|--------------------------:|
| `JJP_DPS1` | `JJP_DPS1.manifest.json` | 888 | 3,812,832 | 221,766 |
| `JJP_DPS2_CS` | `JJP_DPS2_CS.manifest.json` | 4,840 | 24,197,163 | 698,494 |
| `JJP_DPS2_G` | `JJP_DPS2_G.manifest.json` | 730 | 291,458 | 13,543 |
| `JJP_SPS_CS` | `JJP_SPS_CS.manifest.json` | 4,840 | 17,615,553 | 436,669 |
| `JJP_SPS_G` | `JJP_SPS_G.manifest.json` | 292 | 230,914 | 10,147 |
| `JJP_TPS_MC_v4_1` | `JJP_TPS_MC_v4_1.manifest.json` | 317 | 1,472,109 | 93,901 |

Retained means an event with at least one stored `Pri_passAny` candidate
(`Pri_fitPass || Pri_assocPVPass`); it is coverage bookkeeping, not a map cut.
Every manifest is versioned, carries a content-derived master manifest ID, and
names this count `retained_candidate_events`.

When updating a manifest, retain both the per-file totals and their provenance.
Use `count_ntuple_candidates.py` followed by
`build_oldpipeline_manifests.py` for count tables, or use
`prepare_tps_efficiency_manifest.py` for a three-column retained-event list.

## 2. One-file preflight

Run one file from `SAMPLE` through the production backend before creating the
batch:

```bash
SAMPLE=JJP_DPS1
python3 run_efficiency.py \
  --analysis-mode JpsiJpsiPhi \
  --input-file-manifest configs/efficiency/manifests/${SAMPLE}.manifest.json \
  --samples ${SAMPLE} \
  --max-files 1 \
  --tree-path auto \
  --efficiency-config configs/efficiency/tps_nominal.yaml \
  --config-policy strict \
  --output-dir /tmp/chiw/${SAMPLE}_efficiency_preflight \
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
SAMPLE=JJP_DPS1
python3 scripts/efficiency/audit_efficiency_events.py \
  --input-file-manifest configs/efficiency/manifests/${SAMPLE}.manifest.json \
  --tree-path auto \
  --max-events 2000 \
  --output-dir /tmp/chiw/${SAMPLE}_efficiency_audit \
  --fail-on-issues
```

## 3. Prepare shards and DAG

Ten files per shard is a practical starting point; the resulting job count is
determined by the selected sample's manifest:

```bash
SAMPLE=JJP_DPS1
python3 scripts/efficiency/prepare_efficiency_shards.py \
  --samples ${SAMPLE} \
  --input-file-manifest configs/efficiency/manifests/${SAMPLE}.manifest.json \
  --files-per-job 10 \
  --output-dir /tmp/chiw/${SAMPLE}_efficiency_batch
```

Create the DAG with the common strict arguments embedded in every shard:

```bash
SAMPLE=JJP_DPS1
python3 condor/generate_efficiency_dag.py \
  --sample ${SAMPLE} \
  --queue-file /tmp/chiw/${SAMPLE}_efficiency_batch/manifests/jjp_efficiency_queue.txt \
  --output-dir /eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/${SAMPLE}_efficiency_YYYYMMDD \
  --runtime-tarball /path/to/ntuple_analyzer_runtime.tar.gz \
  --dag-dir /tmp/chiw/${SAMPLE}_efficiency_batch/dag \
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
`sample_manifest.json` records `coverage_scope=complete` only when every file
declared by the selected sample's manifest is present.

Key merged artifacts are:

- `file_coverage.parquet`: one successful row per source file
- `configuration_metadata.json`: all per-file snapshots plus unique production
  configurations
- `gen_ancestry_qa.parquet`
- `gen_systems.parquet` and `event_step_flags.parquet`
- `efficiency_maps.parquet`, derived products, and `maps/*.parquet`

Before using the maps, verify totals in the merged coverage table:

```bash
SAMPLE=JJP_DPS1
python3 - <<PY
import pandas as pd
p = "/path/to/merged/${SAMPLE}/file_coverage.parquet"
x = pd.read_parquet(p)
print("files", len(x))
print("entries", int(x.entries_scanned.sum()))
print("retained", int(x.retained_candidate_events.sum()))
print("scope", sorted(x.coverage_scope.unique()))
print("statuses", x.status.value_counts().to_dict())
PY
```

Compare these totals with the selected sample's manifest before using its maps.

## 5. Independent file-disjoint closure

Build maps on a deterministic set of complete source files and evaluate the
correction on a disjoint approximately 20% holdout:

```bash
SAMPLE=JJP_DPS1
python3 -m efficiency_workflow.closure \
  --input-dir /path/to/merged \
  --samples ${SAMPLE} \
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

Raw `X_data` from any listed sample is an MC efficiency input. It is not the
selected data schema used by the yield code. Yield correction still requires
the Pipeline 1 selected ROOT tree with `sel_*` kinematics and sWeights. Apply
the selected sample's maps to that data input with the preferred `factorized`
mode; use `hybrid` as the specified alternative. Do not pass raw efficiency
ROOT files to
`compute_efficiency_corrected_yield.py`.

## 7. Cross-subprocess validation

A one-file preflight on 2026-08-30 found that every listed sample:

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
| `JJP_TPS_MC_v4_1` | 4,649 | 625 | 13 |

These are smoke-test populations, not efficiency measurements. They establish
schema and execution portability but do not replace complete-sample map and
closure validation. Retained populations differ across samples, so review
fine-to-coarse/inclusive fallback and failed lookups for each map before making
cross-subprocess comparisons.

Use each sample's formal manifest and a fresh output directory. For example:

```bash
SAMPLE=JJP_DPS1
python3 run_efficiency.py \
  --analysis-mode JpsiJpsiPhi \
  --input-file-manifest configs/efficiency/manifests/${SAMPLE}.manifest.json \
  --samples ${SAMPLE} \
  --max-files 1 \
  --tree-path auto \
  --efficiency-config configs/efficiency/tps_nominal.yaml \
  --config-policy strict \
  --output-dir /tmp/chiw/${SAMPLE}_efficiency_preflight \
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
configuration policy. Every sample processed under the versioned contract must
pass the YAML explicitly and use strict mode. This keeps the smooth legacy
workflow working while preventing any sample from silently using hardcoded
trigger order, the old tree path, or a partial Run-B schema.

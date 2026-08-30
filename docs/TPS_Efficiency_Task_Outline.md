# TPS Efficiency Task Outline

## Purpose

Build a reproducible and auditable JJP efficiency workflow for TPS-Onia2MuMu samples. The current target inventory is docs/tps_retained_ntuple_events.txt.

The inventory currently contains:

- 317 files
- total entries: 1,472,109
- events with at least one complete reconstructed candidate: 93,901
- candidate-event fraction: approximately 6.38 percent

The third column should be formally named retained_candidate_events in a future manifest. The current text file has no header, so its meaning still relies on the external convention.

## Confirmed sample facts

A real TPS file was inspected. The current files use:

- tree: mkcands/X_data
- configuration tree: mkcands/X_config
- SingleJpsi, SinglePhi, RecoKaonTrack, composite-candidate, DiOnia, Pri, and trigger-matching branches
- KeepAllSingleObjectCandsInMC=True
- SkipCompositeCandBuildingWhenKeepingSingles=False

Therefore the current sample is a Run B full-chain sample that also retains singles, not a singles-only Run A sample.

Future TPS-Onia2MuMu v1.5 files may use top-level X_data rather than mkcands/X_data. The input layer must support both layouts.

## A. Four-muon vertex definition

### Current issue

The current efficiency implementation uses whether the four muonVertexId values agree as four_muon_vtx. Historical commit 99330ad fixed consistency of trigger, vertex, and Pri stages on one composite candidate, but did not complete the migration from the old predicate to the DiOnia branches.

### Target definition

The nominal four_muon_vtx should use:

DiOnia_fitValid && DiOnia_fitPass

The following should remain available as diagnostics or alternative working points:

- muVertexId consistency
- DiOnia_commonRecVtxPass
- DiOnia_passAny
- DiOnia_VtxProb

### Future implementation tasks

1. Connect DiOnia_fitValid and DiOnia_fitPass to the candidate-level chain.
2. Retain the old muVertexId predicate under an explicit diagnostic name.
3. Provide configuration for nominal and alternative working points.
4. Produce step cutflows and event differences for the old and new definitions.
5. Confirm that Pri_* is evaluated only on the same four-muon candidate.

## B. GEN ancestry and feed-down

Feed-down is not currently treated as a blocker for the TPS sample.

The current code selects J/psi particles with at least two direct muon daughters and uses motherGenIdx for reconstructed-object matching. If the generated sample contains no psi(2S) feed-down, and the efficiency definition targets final J/psi to mu mu and final phi to K+K- decays, this is in principle suitable.

A lightweight QA should still be retained:

1. Count J/psi and phi mother-particle PDG IDs.
2. Check the amount of psi(2S) feed-down.
3. Check that particles used in the efficiency definition have the required daughters.
4. Store the QA in sample metadata rather than applying an extra physics veto.

If future samples include b-hadron, chi_c, or psi(2S) feed-down, clarify whether the denominator is all final J/psi particles or directly produced J/psi particles.

## C. Trigger and filter configuration

The current implementation still hardcodes trigger/filter names and fixes the configuration tree path to mkcands/X_config.

Future tasks:

1. Find X_config relative to the actual data-tree path.
2. Read TriggersForJpsi and FiltersForJpsi.
3. Derive trigger/filter indices from their names.
4. Share one parser between the vectorized and python-loop backends.
5. Fail or warn explicitly when configuration is missing or cannot be matched.
6. Store the effective configuration in run metadata.
7. Check that MatchJpsiTriggerNames and per-muon trigger/filter matching belong to the same candidate chain.

## D. Input inventory, coverage, and fail-closed behavior

The first implementation of this part is complete.

Added:

- efficiency_workflow/tps_manifest.py
- scripts/efficiency/prepare_tps_efficiency_manifest.py
- tests/test_tps_manifest.py

The helper can:

- read the existing three-column text inventory;
- normalize cceos XRootD URLs;
- reject duplicate files and invalid counts;
- create a JSON manifest accepted by run_efficiency.py;
- retain per-file total entries and retained candidate-event counts.

Fallback processing now refuses to produce an incomplete efficiency sample if any input file fails.

Recommended follow-up additions:

- source entries per file;
- entries actually scanned;
- full GEN event count;
- output event count;
- processing status and error message;
- one-to-one checks between input files and output shards.

## E. Analyzer configuration and post-processing working points

The TPS X_config intentionally uses loose production selections so that the analysis working point can be adjusted later. This is reasonable, but the two configurations must be recorded separately.

Store separately:

1. ntuple production configuration;
2. efficiency definition configuration;
3. runtime configuration hash;
4. mass, pT, rapidity, vertex, and track working points used by each efficiency result.

Post-processing must not silently treat analyzer production cuts as the efficiency definition.

## F. Two different merge operations and schema

Two different merge operations must be distinguished.

### Pipeline 1: kinematics and sPlot merge

scripts/kinematics/merge_apply_cuts.py belongs to the pre-efficiency kinematics and sPlot pipeline. It produces a selected tree and sel_* branches from intermediate or raw inputs. fit_splot.py and the data yield correction then use:

- tree: selected
- branches: sel_Jpsi_1_*, sel_Jpsi_2_*, sel_Phi_*
- sWeight branches

Therefore, if the remembered merge is this step, the schema does naturally become the one required by the later sPlot and yield-correction code.

### Pipeline 2: TPS efficiency merge

efficiency_workflow.merge_efficiency_shards only merges:

- gen_systems.parquet
- event_step_flags.parquet
- efficiency counts

It does not convert TPS ROOT data into selected or sel_* schema.

The intended relationship is:

TPS raw X_data
to efficiency parquet
to factorized or hybrid efficiency maps
to Pipeline 1 selected data ROOT and sWeights
to corrected yield

The current yield-correction code must not receive raw TPS X_data directly. This is not an efficiency-calculation failure; it is an input-contract difference between the two pipelines.

## Recommended processing boundary

### lxplus and Condor

Complete the following on lxplus:

1. Read TPS raw ROOT files over XRootD.
2. Validate schema and X_config.
3. Compute efficiency in shards.
4. Audit per-file coverage.
5. Merge efficiency Parquet products.
6. Build factorized and hybrid maps.

### Local machine

Transfer compact products:

- efficiency Parquet;
- efficiency maps;
- cutflow and QA plots;
- manifests;
- X_config snapshots;
- closure and systematic-study results.

Do not download all raw TPS ROOT files unless necessary. The final data sPlot and yield correction can run locally or on lxplus; its input must be selected data schema, not raw TPS MC schema.

## Implementation order

1. Complete A: DiOnia nominal definition and alternative working points.
2. Complete C: automatic tree, config, trigger, and filter inference.
3. Add a real TPS integration fixture and contract test.
4. Extend D with per-file coverage and shard-completeness checks.
5. Formalize E by separating production and efficiency-definition configurations.
6. Validate progressively with one file, one JOB group, and all 317 files.
7. Build maps only after these checks and run an independent corrected-yield closure test.

## Implementation status and validation

The planned TPS processing changes are now implemented:

- A: nominal four-muon vertexing uses same-candidate
  `DiOnia_fitValid && DiOnia_fitPass`; the older and alternative predicates are
  retained as QA columns.
- B: final-J/psi and final-phi ancestry and daughter checks are persisted as QA
  metadata without introducing a feed-down veto.
- C: the input layer resolves the data/config tree layout and trigger/filter
  indices from `X_config`, shared by the vectorized, loop, and audit paths.
- D: manifests, shards, and merges carry per-file entry/retention coverage and
  fail closed on missing, duplicate, failed, or incompatible inputs.
- E: production configuration snapshots and hashes are stored separately from
  the versioned efficiency definition.
- Independent file-disjoint factorized and hybrid closure modes are available.

Validation completed by 2026-08-30:

- complete TPS inventory: 317 files, 1,472,109 entries, and 93,901 retained
  candidate events;
- strict two-shard merge smoke test with matching entry, retention, and
  configuration metadata;
- strict schema/config preflight and full event processing on one real file from
  each of `JJP_DPS1`, `JJP_DPS2_CS`, `JJP_DPS2_G`, `JJP_SPS_CS`, and
  `JJP_SPS_G`;
- focused TPS contract tests and the complete repository test suite.

The remaining operational work is complete-sample shard production, merged-map
review, and file-disjoint closure. One-file subprocess tests establish software
portability only. Low-statistics `JJP_DPS2_G` and `JJP_SPS_G` maps will require
particular attention to coarse/inclusive fallback and lookup failures.

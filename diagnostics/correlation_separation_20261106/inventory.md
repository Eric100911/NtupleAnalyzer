# Correlation separation study: input inventory gate

Audit date: 2026-11-06. This is an input-readiness audit for
`docs/Correlation_Separation_Study_Plan.md`, not a new template fit.

## Available selected samples

The local legacy selected-MC directory is
`/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3/`.
These files use tree `selected` and the `sel_` branch prefix. They are old
selected products, not raw TPS-Onia2MuMu v1.5 efficiency inputs. Counts below
are from `diagnostics/phi_ctau_20261022/inventory/` and were not recomputed.

| Component | Selected rows | Distinct (run,lumi,event) keys in old audit | Repeated-key groups | Rows beyond first in repeated-key groups | Workflow-target proxy rows |
|---|---:|---:|---:|---:|---:|
| DPS1 | 68,893 | 20,802 | 13,329 | 48,091 | 67,729 |
| DPS2_CS | 32,533 | 18,155 | 9,226 | 14,378 | 32,018 |
| DPS2_G | 966 | 334 | 223 | 632 | 948 |
| SPS_CS | 7,977 | 6,571 | 1,231 | 1,406 | 7,653 |
| SPS_G | 748 | 275 | 182 | 473 | 737 |
| TPS | Not found as selected RECO | -- | -- | -- | -- |

The proxy-row count requires the documented common direct-phi match plus
highest-pT workflow-target agreement; it does not establish designated
hard-process identity. The audit found no `genWeight` branch. The key-count
columns are diagnostic only and must not be interpreted as selected-event
counts: MC run/lumi/event values are reused across production files.

## Event independence and candidate policy

The standard pre-efficiency pipeline defines `bestCandIdx` for each input
event, applies the selection to that index, and snapshots scalar selected
columns. `BestCandIndexJJP` uses the documented candidate score
`sqrt(pt1^2 + pt2^2 + pt3^2)` after the candidate-level mass, kinematic, track,
and muon requirements. This is the existing candidate estimator and matches
the repository's data convention. Therefore multiple candidates in the raw
event are normal and are reduced before rows enter these selected-MC files.

The previous collision audit grouped only on `(run,lumi,event)` across merged
MC rows. It showed repeated keys with differing kinematics, but this does not
show repeated candidates or duplicate generated events: MC identifiers are
reused across production files. Treat one selected-tree row as one generated
event for splitting, subject to verifying that the merged input file lists do
not contain duplicate source files. The prototype's row-level MC splits are
consistent with the selected-tree granularity; the old key collision counts
must not be used to reduce available statistics.

## Six-component feasibility and process definitions

The five local files above provide selected event rows for DPS1, DPS2_CS,
DPS2_G, SPS_CS, and SPS_G. The low-statistics samples contain only 966 DPS2_G
and 748 SPS_G rows before any further matching, so the planned four-way split
cannot support the proposed six-class template allocation. The three-class
basis DPS1/DPS2_CS/SPS_CS has sufficient selected statistics for continued
toy and grid studies. A comparable selected TPS RECO ROOT file was not found
in the local selected directory or the bounded ROOT-file search under
`MC_samples`.

`configs/efficiency/manifests/JJP_TPS_MC_v4_1.manifest.json` describes remote
TPS efficiency inputs. These are not an identified selected RECO template and
must not be substituted for one. The local config/manifests enumerate sample
names and file locations, but the material reviewed here does not establish
whether CS and G are additive physics sources or alternative generator
descriptions. Their role remains unresolved; filenames alone are insufficient.

## Prior work and next gate

The archived three-component study in
`/tmp/chiw/jjp_multivariable_data_20261105/` used adaptive cell templates and
the DPS1/DPS2_CS/SPS_CS basis. It is useful prototype evidence, but it did not
run the plan's Cartesian pair scan or XGBoost workflow. Its saved
`small_sps_validation/summary.json` contains 24 passed configurations. These
use independent row splits, held-out MC expectations, and conditional Poisson
toys at 2,000 selected signals; they do not include mass-fit/background
fluctuations or establish interval coverage. They are valid prototype closure
checks for the selected three-class samples, conditional on no duplicated
source files in the merged inputs.

Before the six-class stage:

1. Verify from production cards or generator configuration whether CS/G
   samples are additive. If they are model alternatives, define them as
   variations rather than simultaneous classes.
2. Locate or produce selected, truth-matched TPS RECO with the same selection
   and schema if the six-component hypothesis remains additive.
3. Recount independent usable events and effective template statistics after
   those definitions. Defer six-class feasibility until the applicable sample
   and label gates pass.

For the current three-class branch, proceed to the fixed Cartesian 3×3
baseline and its development-MC binning comparisons. Keep the existing
best-candidate reduction, split selected rows (not repeated MC run/lumi/event
keys), save row indices in the split manifest, and verify source-file
non-overlap where provenance permits.

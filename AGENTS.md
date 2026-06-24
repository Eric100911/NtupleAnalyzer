# AGENTS.md

Guidance for coding agents working in this repository.

## Environment

All Python/ROOT work requires the LCG 109a environment:

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
```

When running Python from an automated shell command, source the environment in
the same shell so ROOT, RooFit, uproot, pandas, and parquet support are visible:

```bash
bash -c 'source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh && python3 ...'
```

A convenience symlink may exist at `~/.myscripts/lcg_109a_setup.sh`.

## Project Shape

This repository analyzes assocPV ntuples for three public channel names:

- `JJP`: `J/psi + J/psi + phi`
- `JYP`: `J/psi + Upsilon + phi`
- `JJY`: `J/psi + J/psi + Upsilon`

Do not introduce `JUP` or `JJU` as CLI channel names. Those strings only appear
in some external EOS/XRootD storage names.

Ntuples are produced by the **TPS-Onia2MuMu v1.5** EDAnalyzer
(`CMSSW_15_0_15/src/HeavyFlavorAnalysis/TPS-Onia2MuMu/`).  See
`docs/Efficiency_Evaluation_Guideline.md` for the full branch-to-step mapping.

There are two main analysis pipelines:

1. Pre-efficiency kinematics:
   TPS-Onia2MuMu (EDAnalyzer) → post-process → `fit_splot.py` →
   `plot_weighted_distributions.py` → `plot_kinematics_jjp.py`.
2. JJP efficiency and yield correction:
   `run_efficiency.py` / `cli_efficiency.py` → `merge_efficiency_shards.py` →
   `build_derived_efficiency.py` → `efficiency_workflow.build_factorized_maps`
   → `compute_efficiency_corrected_yield.py`.

The shared configuration and selected-column helpers live in
`ntuple_pipeline_common.py`. The efficiency core lives in
`efficiency_workflow/`.

## Data And Naming Conventions

Ntuples are produced by TPS-Onia2MuMu v1.5.  The main TTree is `X_data`
(no `TDirectoryFile` wrapper).  There is **no `sel_` prefix** on branch names.

### Composite Candidates (full chain, Run B)

- J/ψ₁ / J/ψ₂: `Jpsi_1_*`, `Jpsi_2_*` — mass, ctau, px/py/pz/pt/eta/phi, plus
  `_pxErr`/`_pyErr`/`_pzErr`/`_ptErr`.  Muon indices: `Jpsi_1_mu_1_Idx`,
  `Jpsi_1_mu_2_Idx`.
- φ: `Phi_*` — same set.  Kaon indices: `Phi_K_1_RecoKaonTrackIdx`,
  `Phi_K_2_RecoKaonTrackIdx` (indices into the `RecoKaonTrack_*` block).
- DiOnia (4μ vtx): `DiOnia_fitValid`, `DiOnia_fitPass`, `DiOnia_commonRecVtxPass`, etc.
- TriOnia (3-body vtx): `Pri_fitValid`, `Pri_fitPass`, `Pri_assocPVPass`,
  `Pri_trackPVPass`, `Pri_passAny`.

### Single-Object Candidates (MC, Run A + Run B)

- `SingleJpsi_*`: mass, ctau, kinematics, `fitValid`/`fitPass`,
  `mu1_Idx`/`mu2_Idx`, `mu1_genMatchIdx`/`mu2_genMatchIdx`.
- `SinglePhi_*`: mass, ctau, kinematics, `fitValid`/`fitPass`,
  `K1_RecoKaonTrackIdx`/`K2_RecoKaonTrackIdx`, `K*_genMatchIdx`.
- Counters: `nSingleJpsiCand`, `nSinglePhiCand`.

### RecoKaonTrack Block (MC)

Flat per-track storage: `RecoKaonTrack_pt`, `_eta`, `_phi`, `_charge`,
`_genMatchIdx`, `_usedInSinglePhi`, `_passDzPV`, `_passDxyPV`,
`_passTrackPV`, `_fromPV`, etc.  Counter: `nRecoKaonTrack`.

### GEN-Level Particles

Flat vectors: `MC_GenPart_pdgId`, `_status`, `_motherPdgId`, `_px/py/pz/mass/pt/eta/phi`.
Stores all relevant particles (μ=13, K=321, J/ψ=443, Υ=553, φ=333).

### Trigger Branches

Event-level: `TrigRes`, `TrigNames`, `MatchJpsiTriggerNames`, `MatchUpsTriggerNames`.
Per-muon: `muIsJpsiTrigMatch`, `muJpsiMatchedTriggerIndices`, `muJpsiMatchedFilterIndices`.

### Critical Note

The analyzer stores `eta` but **not rapidity `y`** for composite candidates.
Rapidity must be computed from `(px, py, pz, mass)` in post-processing.  J/ψ
ordering in the composite slots (`Jpsi_1`, `Jpsi_2`) follows a best-candidate
metric, not necessarily pT — re-order by pT in post-processing for efficiency maps.

Ordering conventions:

- `Jpsi_1` is leading pT and `Jpsi_2` is subleading pT (re-order if needed).
- `Phi_K_1` is leading pT and `Phi_K_2` is subleading pT.
- Some plotting code re-sorts kaons at read time; preserve that behavior unless
  changing the physics definition intentionally.

Weight branches:

- `signal_sw`: signal sWeight from `fit_splot.py`.
- `jpsi_jpsi_phi_sw` and other `*_sw`: component sWeights from `fit_splot.py`.
- `effcorr_w` / `effcorr_w_err`: efficiency correction weight and uncertainty.
- `signal_effcorr_sw`: `signal_sw * effcorr_weight` for corrected sPlot plots.

## Common Inputs

Default output area:

```text
/eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV
```

### Current (Old-Scheme) Files

Local JJP data:

```text
../jjp_data_selected.root
plots_kinematics/temp/jjp_data_weighted.root
```

Local merged JJP MC selected samples:

```text
/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3/
```

These files are already GEN-matched, use tree `selected`, contain `sel_*`
branches, and do not contain sWeights.

### Target (TPS-Onia2MuMu v1.5) Files

New ntuples are produced by `HeavyFlavorAnalysis/TPS-Onia2MuMu` (CMSSW 15_0_15)
with tree `X_data`.  See `docs/Efficiency_Evaluation_Guideline.md` for the
required MC run configurations.

Low-stat samples `DPS_2_G` and `SPS_G` can fluctuate strongly. Avoid treating
them like high-stat reference samples in ratio-panel comparisons.

## Efficiency Workflow

The efficiency pipeline (`run_efficiency.py` → `efficiency_workflow/efficiency.py`)
reads **raw TPS-Onia2MuMu ntuples directly** (`tree_path = "mkcands/X_data"`).
There is **no merge step** — the merge (`merge_apply_cuts.py`) is only used by
Pipeline 1 (kinematics/sPlot), not Pipeline 2 (efficiency).

**Current** ntuples use `TDirectoryFile("mkcands")` wrapping the `X_data` tree.
**TPS-Onia2MuMu v1.5** drops the `mkcands` wrapper — the tree is `X_data` directly.

Two MC runs are needed for the new scheme (see `docs/Efficiency_Evaluation_Guideline.md`):

- **Run A** (singles-only): `keepAllSingleObjectCandsInMC=True skipCompositeCandBuildingWhenKeepingSingles=True`
  → adds `SingleJpsi_*`, `SinglePhi_*`, `RecoKaonTrack_*` for per-object efficiency steps
- **Run B** (full chain): `keepAllSingleObjectCandsInMC=True skipCompositeCandBuildingWhenKeepingSingles=False`
  → all of Run A plus composite `Jpsi_1_*`, `Jpsi_2_*`, `Phi_*`, `DiOnia_*`, `Pri_*`, trigger branches

The current code uses only composite branches (approximating per-object efficiency).
The target is to use single-object branches for proper per-object maps.

Per-object chains (from Run A, conditional on previous step):

```text
jpsi_lead:    acceptance(MC_GenPart) -> muonRECO -> muonID -> dimuon
jpsi_sublead: acceptance(MC_GenPart) -> muonRECO -> muonID -> dimuon
phi:          acceptance(MC_GenPart) -> kaonRECO -> kaonID -> dikaon
```

Event-level chain (from Run B):

```text
(from per-object) -> HLT -> four_muon_vtx (DiOnia_*) -> triOnia (Pri_*)
```

The current step chain (`s_cand → hlt_event → hlt_muon_matched → four_muon_vtx → Pri_*`)
is defined in `efficiency_workflow/efficiency.py` and uses composite-candidate-only
information.  The new scheme will replace this with proper single-object-based
efficiency maps.

Map binning conventions:

- Raw per-object `object_2d` maps in `efficiency_maps.parquet` are binned in
  `(pT, signed y)`; plotting helpers may also write folded `(pT, |y|)` views.
- Factorized correction maps and stacked-J/psi derived maps use `(pT, |y|)`.
- `stacked_jpsi_acceptance_maps.parquet` combines leading and subleading J/psi
  rows into one per-object J/psi map with `y_axis == "abs_y"`.
- `stacked_jpsi_efficiency_maps.parquet` does the same for the J/psi
  `muonRECO`, `muonID`, and `dimuon` steps. It intentionally skips `fiducial`,
  which lives in the stacked acceptance map.

Preferred correction mode is `factorized`:

```text
w = 1 / product(per-object efficiencies * event-level efficiencies)
```

The `hybrid` mode splits the correction into factorized acceptance × 5D
conditional post-acceptance efficiency:

```text
w = 1 / (A_jpsi_lead * A_jpsi_sublead * A_phi * epsilon_5d_post_acceptance)
```

Use `legacy-correlated` only for comparison with older single-map corrections.
Factorized and hybrid lookups use fine bins first, then coarse bins, then
inclusive bins.  Default minimum statistics are `--n-min-fine 30` and
`--n-min-coarse 50`.

## Useful Commands

Quick efficiency smoke test:

```bash
bash -c 'source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh && \
  python3 run_efficiency.py --analysis-mode JpsiJpsiPhi \
    --output-dir /tmp/chiw/eff_test --max-files 1 --samples JJP_DPS2_CS --skip-plots && \
  python3 build_derived_efficiency.py --input-dir /tmp/chiw/eff_test'
```

Build only the stacked-J/psi `(pT, |y|)` acceptance and per-object efficiency
plots from existing merged products. This skips cumulative, conditional, and
pair-level plots:

```bash
bash -c 'source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh && \
  python3 build_derived_efficiency.py \
    --input-dir ../merged_efficiency_output_20260601_01 \
    --output-dir stacked_jpsi_pt_absy_only_YYYYMMDD \
    --plot-scope stacked-jpsi --min-plot-total 1'
```

Add `--with-uncertainty-plots` to the command above only when the QA panels with
Clopper-Pearson uncertainties are needed.

Rebuild maps from existing merged parquet products:

```bash
python3 rebuild_efficiency_maps.py \
  --input-dir /path/to/merged \
  --output-dir /path/to/fresh_output \
  --samples JJP_DPS1 JJP_DPS2_CS JJP_DPS2_G JJP_SPS_CS JJP_SPS_G
```

Build factorized maps:

```bash
python3 -m efficiency_workflow.build_factorized_maps \
  --input-dir /path/to/merged \
  --samples JJP_DPS1 JJP_DPS2_CS JJP_DPS2_G JJP_SPS_CS JJP_SPS_G
```

Build post-acceptance 5D maps (required for hybrid correction mode):

```bash
python3 -m efficiency_workflow.build_factorized_maps \
  --input-dir /path/to/merged \
  --samples JJP_DPS1 JJP_DPS2_CS JJP_DPS2_G JJP_SPS_CS JJP_SPS_G \
  --build-post-acceptance
```

Compute the JJP efficiency-corrected yield:

```bash
bash -c 'source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh && \
  python3 compute_efficiency_corrected_yield.py \
    --data-input ../jjp_data_selected.root \
    --efficiency-dir ../merged_efficiency_output_20260601_01 \
    --correction-mode factorized \
    -o yield_result.json \
    --plot-dir yield_plots -j 4'

# Hybrid mode
bash -c 'source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh && \
  python3 compute_efficiency_corrected_yield.py \
    --data-input ../jjp_data_selected.root \
    --efficiency-dir ../merged_efficiency_output_20260601_01 \
    --correction-mode hybrid \
    -o yield_hybrid.json \
    --plot-dir yield_plots -j 4'
```

## Testing And Validation

Prefer small, bounded tests before launching full EOS-scale jobs:

- `python3 test_efficiency_corrections.py`
- `python3 test_efficiency_schema.py`
- `python3 test_factorized_maps.py`
- `python3 test_acceptance_factorization.py`
- one-file `run_efficiency.py --max-files 1`

For plotting or ROOT workflows, validate with a small input or a temporary
output directory under `/tmp/chiw` before writing large output trees or plot
directories.

## Reference Docs

| Document | Location | Content |
|----------|----------|---------|
| Efficiency Evaluation Guideline | `docs/Efficiency_Evaluation_Guideline.md` | Branch-to-step mapping, MC run configs, per-step recipe |
| Efficiency Scheme (math) | `docs/Efficiency_scheme.md` | Formal definitions of factorized efficiency |
| TPS-Onia2MuMu README | `../Full_MC_Production/external/TPS-Onia2MuMu/README.md` | Analyzer build/run/config instructions |
| TPS-Onia2MuMu CLAUDE.md | `../Full_MC_Production/external/TPS-Onia2MuMu/CLAUDE.md` | Analyzer architecture, branch listing |

## Plotting Style

Use `mplhep` as the single owner of CMS styling and CMS labels:

- Apply CMS style globally with `hep.style.use(hep.style.CMS)` or the local
  `apply_cms_style()` helper. Do not rely on `plt.style.context()` for CMS
  fonts; mplhep documents that context managers are unreliable for experiment
  styles.
- Put CMS labels on axes with `hep.cms.label(..., loc=0)` so the label appears
  above the plot area instead of covering data. Use caption text
  `"Work In Progress"` for this analysis when requested.
- For additional labels such as subprocess names, follow
  `efficiency_workflow.plotting.apply_cms_label()`: draw small top-row figure
  text above the axes after the CMS label, not inside the data region.
- Keep plot annotations proportional to the figure. Legends may be inside the
  axes when they do not obscure the important distribution; upper right is the
  default choice for 1D data-MC overlays.
- Use explicit figure margins (`subplots_adjust`) when labels, colorbars, or
  ratio/pull panels are present. Avoid placing caption boxes over plotted
  histograms or heatmaps.

## Development Guardrails

- Keep physics channel names (`JJP`, `JYP`, `JJY`) stable.  Do not introduce
  `JUP` or `JJU` as CLI channel names.
- The **new** ntuple scheme (TPS-Onia2MuMu v1.5) uses branch names without the
  `sel_` prefix and tree name `X_data`.  The old scheme (`sel_` prefix, tree
  `selected`) is legacy.  New code should target the TPS-Onia2MuMu v1.5 branch
  names.  See `docs/Efficiency_Evaluation_Guideline.md`.
- Rapidity `y` is **not** in the TTree — compute it from `(px, py, pz, mass)` in
  post-processing.  Composite J/ψ candidates may not be pT-ordered; re-order by
  pT before building per-object efficiency maps.
- Do not overwrite existing merged parquet or ROOT products by default. Scripts
  such as `rebuild_efficiency_maps.py` are intentionally non-overwriting; prefer
  fresh output directories for regenerated products.
- Preserve the distinction between data, GEN-matched MC, and efficiency-pipeline
  GEN-level inputs. Selected merged MC is not the same input as raw GEN ntuples
  used by the efficiency pipeline.
- When adding command examples, include the LCG setup if ROOT/RooFit/parquet
  dependencies are required.
- Avoid broad refactors in `efficiency_workflow/` unless needed for the requested
  physics or schema change. Many scripts depend on shared parquet column names.
- Use `rg`/`rg --files` for repository searches.
- Leave unrelated worktree changes alone.

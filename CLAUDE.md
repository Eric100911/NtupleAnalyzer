# NtupleAnalyzer — Efficiency Workflow

## Python Environment

All Python commands require the LCG_109a environment.  Source the setup script before running:

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
```

A convenience symlink is available at `~/.myscripts/lcg_109a_setup.sh`.

When executing Python in a `Bash` tool call, wrap in a single `bash -c` so the environment persists:

```bash
bash -c 'source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh && python3 ...'
```

## Architecture & Data Flow

There are **two major pipelines** in this repo:

### Pipeline 1: Pre-Efficiency Kinematics (sPlot + plots)

```
Raw ntuples (EOS/xrootd)
  → merge_apply_cuts.py  [bestCandIdx, GEN-match filter for MC, define sel_* columns]
    → jjp_{data,mc}_{sample}_selected.root   (tree: "selected", ~109 sel_ branches)
      → fit_splot.py     [RooFit 3D mass fit → sPlot → signal_sw + per-component _sw branches]
        → jjp_{data,mc}_{sample}_weighted.root  (tree: "selected", full kinematics + sWeights)
          → plot_weighted_distributions.py  [sWeighted 1D histograms + pair correlations]
          → plot_kinematics_jjp.py          [pre-efficiency kinematics + data-MC overlays]
```

### Pipeline 2: Efficiency Computation & Correction

```
MC raw ntuples (EOS/xrootd)
  → run_efficiency.py / cli_efficiency.py
    [per-object efficiency steps: fiducial→muonRECO→muonID→dimuon (J/ψ), fiducial→kaonRECO→kaonID→dikaon (φ)]
    [event-level steps: s_cand→hlt_event→hlt_muon_matched→four_muon_vtx→Pri_* (parallel)]
    → merged_efficiency_output/
      ├── JJP_{sample}/
      │   ├── gen_systems.parquet          [GEN-level kinematics per event]
      │   ├── event_step_flags.parquet     [per-event step booleans]
      │   ├── efficiency_counts.parquet    [binned counts: total, passed, eff, unc; raw object_2d uses signed y]
      │   ├── efficiency_maps.parquet      [alias for efficiency_counts; used by corrections]
      │   ├── cutflow.csv                  [per-step cutflow summary]
      │   ├── derived/                     [acceptance, conditional, pair-level, stacked-J/ψ maps]
      │   │   ├── acceptance_maps.parquet
      │   │   ├── conditional_efficiency_maps.parquet
      │   │   ├── per_object_acceptance_maps.parquet
      │   │   ├── stacked_jpsi_acceptance_maps.parquet   [(pT, |y|), lead+sublead combined]
      │   │   ├── stacked_jpsi_efficiency_maps.parquet   [(pT, |y|), muonRECO/muonID/dimuon]
      │   │   └── *_maps.parquet                         [pair-level vertex/Pri maps]
      │   ├── maps/                        [correction maps: factorized acceptance + post-acceptance 5D]
      │   │   ├── post_acceptance_5d.parquet [5D conditional post-acceptance ε (fine/coarse/inclusive)]
      │   │   ├── acceptance_jpsi.parquet, acceptance_phi.parquet
      │   ├── factorized/                  [factorized correction maps (built via build_factorized_maps.py)]
      │   │   ├── acceptance_jpsi.parquet
      │   │   ├── acceptance_phi.parquet
      │   │   ├── eff_muReco_jpsi.parquet, eff_muID_jpsi.parquet, eff_dimuon_jpsi.parquet
      │   │   ├── eff_kaonReco_phi.parquet, eff_kaonID_phi.parquet, eff_dikaon_phi.parquet
      │   │   └── s_cand.parquet
      │   ├── scand_factorization/         [S_cand factorization diagnostic]
      │   └── plots/                       [2D efficiency heatmaps]
      └── manifest.json

  → compute_efficiency_corrected_yield.py
    [applies efficiency weights to data: w = 1/ε for each event]
    [factorized mode: w = 1/∏(ε_jpsi·ε_phi·ε_event) with coarse-bin fallback]
    [hybrid mode: w = 1/(A_jpsi_lead·A_jpsi_sublead·A_phi·ε_5d_post_acceptance)]
    [writes JSON with per-sample corrected yield + systematic envelope]
    → jjp_data_selected_efficiency_corrected_yield.json
```

## Channel

Primary channel: **JJP** (J/ψ J/ψ φ).  JYP (J/ψ Υ φ) and JJY (J/ψ J/ψ Υ) also supported.

## Key Local Files (not on EOS)

| Path | Description |
|------|-------------|
| `../jjp_data_selected.root` | Data selected ntuple, 48,829 events, ~382 branches, NO sWeights |
| `plots_kinematics/temp/jjp_data_weighted.root` | Data with sWeights (produced by fit_splot.py) |

### Merged MC Selected Samples

Location: `/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3/`

| File | Sample | Events | Size |
|------|--------|--------|------|
| `jjp_mc_dps_1_selected.root` | DPS_1 | 68,893 | 468M |
| `jjp_mc_dps_2_cs_selected.root` | DPS_2_CS | 32,533 | 232M |
| `jjp_mc_dps_2_g_selected.root` | DPS_2_G | 966 | 12M |
| `jjp_mc_sps_cs_selected.root` | SPS_CS | 7,977 | 54M |
| `jjp_mc_sps_g_selected.root` | SPS_G | 748 | 8.7M |

These are **already GEN-matched** (merge_apply_cuts.py applies `PassSelectedJJPGenMatch` for JJP MC).
Tree name: `"selected"`. All events are true signal → weight=1 is valid for MC.
These files have `sel_*` branches but **no sWeights** — use weight=1 everywhere for MC.

Note: TPS is not available locally. The entries for DPS_2_G (966) and SPS_G (748)
are very low — expect large statistical fluctuations in these samples.

### Old Efficiency Pipeline MC (for efficiency correction maps)

`../merged_efficiency_output_20260601_01/jjp_effcorr_weighted_trees/JJP_*_merged.root`
— older MC merged ntuples with 48,247 events each (uniform subsample). These
have full kinematics but are superseded by the `selected-merged-v3` files for
comparison plots.

## Branch Naming Convention

All selected branches are prefixed `sel_`:
- **Candidates**: `sel_Jpsi_1_*`, `sel_Jpsi_2_*`, `sel_Phi_*`, `sel_Pri_*` — have y (rapidity) computed
- **Muons**: `sel_Jpsi{1,2}_mu{1,2}_*` — px, py, pz, pt, eta, phi (NO y)
- **Kaons**: `sel_Phi_K_{1,2}_*` — px, py, pz, pt, eta, phi (NO y); K_1 = leading pT, K_2 = subleading
- **Pairs**: `sel_abs_dy_{name}`, `sel_abs_dphi_{name}`, `sel_m_{name}` for each pair spec
- **Triple**: `sel_m_all`

## Key Scripts

### Pre-Efficiency Pipeline

| Script | Purpose |
|--------|---------|
| `merge_apply_cuts.py` | Merge raw ntuples, apply best-candidate selection + GEN-match (MC), compute sel_ columns |
| `fit_splot.py` | Run RooFit 3D mass fit, compute sWeights, write weighted output |
| `fit_splot_with_kinematic_cuts.py` | sPlot fit with additional kinematic selections |
| `plot_weighted_distributions.py` | Generic sWeighted 1D distribution plots (all sel_ columns) + pair Δy/Δφ 2D correlations |

### MC-Data Agreement & Kinematics Plots

| Script | Purpose |
|--------|---------|
| `plot_kinematics_jjp.py` | **Pre-efficiency kinematics**: sWeighted data-only plots + data-MC overlay (all 5 MC samples overlaid, shape-normalized) |
| `plot_data_mc_comparison.py` | **Single-sample data/MC comparison** with χ²/ndf compatibility metrics and Data/MC ratio panel |
| `add_mc_weights.py` | Add `signal_sw=1.0` branch to GEN-matched MC files via RDataFrame (needed by plot_data_mc_comparison.py) |

### Efficiency Computation

| Script | Purpose |
|--------|---------|
| `run_efficiency.py` | Thin wrapper entry point for efficiency computation |
| `prepare_efficiency_shards.py` | Prepare per-file efficiency computation shards for Condor |
| `merge_efficiency_shards.py` | Merge efficiency shard outputs into consolidated parquet files |
| `rebuild_efficiency_maps.py` | Rebuild `efficiency_maps.parquet` from existing `gen_systems.parquet` + `event_step_flags.parquet` (non-overwriting by default) |
| `build_derived_efficiency.py` | Build derived efficiency products (acceptance, conditional, pair-level, stacked-J/ψ); use `--plot-scope stacked-jpsi` to render only stacked-J/ψ plots |
| `build_response_classification.py` | Build response matrix classification for efficiency correction diagnostics |
| `build_systematic_uncertainty.py` | Compute systematic uncertainty envelope from per-sample efficiency variations |
| `print_cutflow.py` | Print formatted cutflow tables (text/LaTeX/CSV) from `event_step_flags.parquet` |

### Efficiency Correction & Yield

| Script | Purpose |
|--------|---------|
| `apply_efficiency_corrections.py` | Apply efficiency correction weights to ROOT trees |
| `compute_efficiency_corrected_yield.py` | **Main entry point**: compute efficiency-corrected signal yield with subprocess envelope, supports factorized, legacy-correlated, and hybrid modes |
| `check_candchoice_closure.py` | Check candidate-choice closure: compare corrected yields with different best-candidate metrics |
| `classify_response_events.py` | Classify events by response migration pattern (for response matrix diagnostics) |

### Tests & Diagnostics

| Script | Purpose |
|--------|---------|
| `test_acceptance_factorization.py` | Bin-by-bin closure test of the acceptance factorization assumption (A_direct vs A_factorized) |
| `test_closure_cli.py` | CLI closure tests for efficiency correction (factorized, correlated, hybrid) |
| `test_efficiency_corrections.py` | Unit tests for efficiency correction lookups (factorized, correlated, ROOT annotation) |
| `test_efficiency_plots.py` | Unit tests for efficiency plotting functions |
| `test_efficiency_schema.py` | Schema validation tests for efficiency data products |
| `test_efficiency_systematics.py` | Unit tests for systematic uncertainty computation |
| `test_factorized_maps.py` | Unit tests for factorized efficiency map building |
| `test_fit_splot_schema.py` | Schema tests for sPlot fit outputs |
| `quantify_scand_factorization.py` | Quantify S_cand factorization: compare direct 3-body vs factorized per-object S_cand efficiency |
| `test_scand_factorization.py` | Test harness for SCand factorization quantification |

### Analysis Studies (sideband, vertex, etc.)

| Script | Purpose |
|--------|---------|
| `analyze_ntuple_JJP.py` | General JJP ntuple analysis |
| `analyze_ntuple_JJP_window.py` | JJP analysis with mass window studies |
| `analyze_ntuple_JYP.py` | JYP ntuple analysis |
| `analyze_ntuple_JJY.py` | JJY ntuple analysis |
| `compare_bbb_splot_sideband.py` | Compare sPlot results with sideband subtraction |
| `study_splot_sideband_vertex_cuts.py` | Study vertex cut impact on sPlot sideband |
| `plot_dionia_vtx_ctau_shape_study.py` | Vertex/ctau shape studies |
| `plot_vertex_cut_pileup_study.py` | Vertex cut vs pileup study |
| `plot_ntuple_results.py` | General ntuple result plotting |
| `apply_genmatch_to_merged.py` | Retroactively apply GEN-match filter to merged MC files |

### Shared Module

| File | Purpose |
|------|---------|
| `ntuple_pipeline_common.py` | Shared configs: CHANNEL_CONFIGS, MC_SAMPLE_PATHS, DatasetSchema, ChannelConfig, define_selected_columns(), output path helpers |

## Efficiency Workflow Module (`efficiency_workflow/`)

The `efficiency_workflow/` package is the core of the efficiency computation pipeline.

### Module Structure

| File | Purpose |
|------|---------|
| `efficiency.py` | Core efficiency computation: per-object step columns, event-level steps, EfficiencyBinning, build_efficiency_counts(), stacked-J/ψ `(pT, |y|)` maps, build_cutflow(), build_subprocess_envelope(), process_efficiency_file() |
| `corrections.py` | Efficiency correction maps: EfficiencyCorrectionMap (correlated 3D/5D), FactorizedCorrectionMap (per-object × event-level), HybridCorrectionMap (factorized acceptance × 5D post-acceptance), vectorized lookups, ROOT tree annotation |
| `closure.py` | Closure tests: compare GEN-level vs corrected-reco yields to validate correction factors; supports factorized, correlated, and hybrid modes |
| `plotting.py` | All efficiency plots: 2D heatmaps (efficiency, acceptance), stacked-J/ψ `(pT, |y|)` plots, ratio plots (sample/nominal), envelope half-width, max-pull plots, systematic uncertainty visualization, yield comparison bar charts |
| `products.py` | Derived efficiency products: acceptance maps, conditional maps, pair-level maps, per-object acceptance, stacked J/ψ maps |
| `yield_correction.py` | Efficiency-corrected yield: 3D mass fit with per-event efficiency weights, per-sample systematic envelope, factorized and hybrid correction with coarse-bin fallback |
| `build_factorized_maps.py` | Build factorized correction maps and post-acceptance 5D conditional efficiency maps from event_step_flags: per-object (acceptance, muonRECO, muonID, dimuon for J/ψ; acceptance, kaonRECO, kaonID, dikaon for φ), event-level (s_cand), and 5D post-acceptance (fine/coarse/inclusive) |
| `scand_factorization.py` | SCand factorization diagnostic: compare direct 3-body S_cand efficiency vs factorized product of per-object efficiencies |
| `config.py` | Configuration dataclasses: StudyConfig, OfflineSelectionConfig, MassStudyConfig, CmsPlotStyleConfig |
| `io.py` | I/O utilities: ensure_dir, read/write_json, read/write_parquet |
| `systematics.py` | Systematic uncertainty: envelope half-width, max-pull, ratio computation across subprocess samples |
| `truth.py` | GEN-level truth helpers: first_ancestor_idx, to_int_idx |
| `cli_efficiency.py` | Full CLI for efficiency computation: file staging (xrootd→local), per-file processing, merging, derived products, plotting |

### Efficiency Step Schema

**Per-object chains** (self-contained; each resets denominator to total events):

| Object | Steps |
|--------|-------|
| `jpsi_lead` | fiducial → muonRECO → muonID → dimuon |
| `jpsi_sublead` | fiducial → muonRECO → muonID → dimuon |
| `phi` | fiducial → kaonRECO → kaonID → dikaon |

**Event-level chain** (sequential, then parallel):

```
full_gen → s_cand → hlt_event → hlt_muon_matched → four_muon_vtx
                                                          ↓
                          ┌───────────────────────────────┴───────────────────────┐
                          ↓               ↓                ↓                       ↓
                      Pri_fitValid    Pri_fitPass    Pri_assocPVPass    Pri_trackPVPass
```

Each Pri_* step is conditional on `four_muon_vtx` (parallel, not sequential among themselves).

### Efficiency Map Types

| Map Type | Dimensions | Description |
|----------|-----------|-------------|
| `object_2d` | (pT, signed y) per object | Raw per-object counts in `efficiency_maps.parquet`; plotting helpers can fold these to `(pT, \|y\|)` views |
| `object_2d_abs_y` | (pT, \|y\|) per object | Plot-only folded view of `object_2d` rows |
| `correlated_3d` | (pT_J/ψ1, pT_J/ψ2, pT_φ bins) | Correlated efficiency accounting for kinematic correlations between objects |
| `correlated_5d` | (pT_J/ψ1, pT_J/ψ2, pT_φ, \|y1\|, \|y2\|) | Higher-dimensional correlated efficiency; useful for closure checks, sparse in low-stat samples |
| `pair_vertex_2d` | (pT_J/ψ_lead, pT_J/ψ_sublead) | Pair-level vertex efficiency |
| `stacked_jpsi_acceptance_2d` | (pT, \|y\|) combined | Stacked J/ψ fiducial acceptance, with lead and sublead J/ψ entries combined |
| `stacked_jpsi_efficiency_2d` | (pT, \|y\|) combined | Stacked J/ψ per-object efficiencies for `muonRECO`, `muonID`, and `dimuon` |

Stacked J/ψ derived maps are formal `(pT, |y|)` products: their parquet files
store `y_axis == "abs_y"` directly. They are not signed-y products that must be
folded at plotting time.

### Correction Modes

1. **`factorized`** (recommended): Correction weight = 1/∏(ε_per_object · ε_event).
   - Each factor is a 2D map in (pT, \|y\|).
   - Two-tier fallback: fine bins (≥30 MC events) → coarse bins (≥50 MC events) → error.
   - Much better statistical precision than fully-correlated maps.

2. **`hybrid`** (new): Correction weight = 1/(A_jpsi_lead · A_jpsi_sublead · A_phi · ε_5d_post_acceptance).
   - Acceptance factors are 2D in (pT, |y|) with fine→coarse→inclusive fallback.
   - Post-acceptance efficiency is 5D (lead pT, sublead pT, φ pT, |lead y|, |sublead y|) with 3D coarse and inclusive fallbacks.
   - Avoids the fully-factorized assumption for post-acceptance steps while keeping acceptance factorized.
   - Requires `post_acceptance_5d.parquet` in the sample's `maps/` directory (built via `build_factorized_maps.py --build-post-acceptance`).

3. **`legacy-correlated`**: Correction weight = 1/ε_correlated_3d.
   - Direct lookup in correlated 3D (pT_J/ψ1, pT_J/ψ2, pT_φ) bins.
   - Sparser bins, larger statistical fluctuations.

### Stacked J/ψ Plot Production

Use the scoped plotting mode when only the lead+sublead stacked J/ψ acceptance
and per-object efficiency plots are needed. It still rebuilds derived parquet
products, but it skips cumulative, conditional, pair-level, and systematics
plots.

```bash
bash -c 'source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh && \
  python3 build_derived_efficiency.py \
    --input-dir ../merged_efficiency_output_20260601_01 \
    --output-dir stacked_jpsi_pt_absy_only_YYYYMMDD \
    --plot-scope stacked-jpsi --min-plot-total 1'
```

This writes four regular PNGs per sample under
`<output>/<sample>/derived/plots/stacked_jpsi/`:

- `stacked_jpsi_absy_fiducial_acceptance.png`
- `stacked_jpsi_absy_muonRECO.png`
- `stacked_jpsi_absy_muonID.png`
- `stacked_jpsi_absy_dimuon.png`

Add `--with-uncertainty-plots` only when the matching
`plots_with_uncertainty/stacked_jpsi/` QA versions are required.

## MC-Data Agreement Plots

There are **three levels** of MC-data agreement assessment. The first two use the
`selected-merged-v3` MC samples; the third is MC-MC and uses efficiency maps.

### Full data-MC comparison workflow

```bash
# 0. Setup
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh

# 1. Run sPlot on data → produces signal_sw branch
python3 fit_splot.py --channel JJP --dataset data \
  -i ../jjp_data_selected.root \
  -o plots_kinematics/temp/jjp_data_weighted.root \
  --plot-dir plots_kinematics/temp/fit -j 4

# 2. Add signal_sw=1.0 to MC files (all true signal, no sWeights needed)
#    Uses RDataFrame Snapshot — fast, multi-threaded
python3 add_mc_weights.py

# 3. Create symlinks so plot_kinematics_jjp.py finds MC files
#    (script expects names like JJP_DPS1_merged.root)
mkdir -p plots_kinematics/temp/mc_links
cd plots_kinematics/temp/mc_links
MC_DIR=/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3
ln -sf $MC_DIR/jjp_mc_dps_1_selected.root JJP_DPS1_merged.root
ln -sf $MC_DIR/jjp_mc_dps_2_cs_selected.root JJP_DPS2_CS_merged.root
ln -sf $MC_DIR/jjp_mc_dps_2_g_selected.root JJP_DPS2_G_merged.root
ln -sf $MC_DIR/jjp_mc_sps_cs_selected.root JJP_SPS_CS_merged.root
ln -sf $MC_DIR/jjp_mc_sps_g_selected.root JJP_SPS_G_merged.root
cd ../../..

# 4a. Type A: All-MC overlay on data (~30 kinematic variables)
python3 plot_kinematics_jjp.py --mode comparison \
  --weighted-data plots_kinematics/temp/jjp_data_weighted.root \
  --mc-dir plots_kinematics/temp/mc_links \
  -o plots_kinematics --skip-splot --normalize shape

# 4b. Type B: Single-MC ratio-panel (χ²/ndf + p-value) for high-stat samples
for SAMPLE in DPS_1 DPS_2_CS SPS_CS; do
  python3 plot_data_mc_comparison.py --channel JJP --mc-sample "$SAMPLE" \
    --data-input plots_kinematics/temp/jjp_data_weighted.root \
    --mc-input "plots_kinematics/temp/jjp_mc_$(echo $SAMPLE | tr '[:upper:]' '[:lower:]')_weighted.root" \
    --data-weight-branch signal_sw --mc-weight-branch signal_sw \
    --normalize shape -o "plots_kinematics/comparison_ratio/$SAMPLE"
done
```

### Level 1: Pre-Efficiency Kinematics (`plot_kinematics_jjp.py`)

Normalized shape comparison of sWeighted data vs all 5 MC samples overlaid.
- **Data**: sWeighted events (black errorbar points)
- **MC**: All 5 subprocess samples overlaid as colored step histograms (DPS_1, DPS_2_CS, DPS_2_G, SPS_CS, SPS_G)
- **Normalization**: Shape-normalized (unit integral) by default; yield mode also available
- **Variables**: pT, y/η, φ for J/ψ candidates, φ candidate, J/ψ muons, φ kaons; plus \|y\| for J/ψ and φ
- **Output**: `plots_kinematics/comparison/` (30 PDF + 30 PNG)
- **No ratio panel or χ² metric** — pure visual overlay for shape agreement assessment
- **MC file mapping**: The script's `MC_SAMPLE_FILES` dict expects names like `JJP_DPS1_merged.root`.
  Use `--mc-dir` to point to a directory with symlinks named accordingly, or edit the dict directly.
- **MC weights**: The script's `load_branch_mc()` uses weight=1 internally — no weight branch needed.

### Level 2: Single-Sample Data/MC with Ratio Panel (`plot_data_mc_comparison.py`)

Detailed comparison of sWeighted data against a single MC sample with quantitative metrics.
- **Layout**: Two-panel (main distribution + Data/MC ratio)
- **Metrics**: χ²/ndf + p-value computed from bin-by-bin compatibility
- **Normalization**: Shape or yield mode
- **Variables**: All sel_* branches common to both data and MC trees (~105 branches)
- **Special handling**: ctau distributions get log-scale y-axis with adjusted range
- **Ratio panel**: Data/MC with error bars; horizontal line at 1.0; y-range [0.4, 1.6]
- **MC weight branch**: This script requires a weight branch in the MC tree.
  Use `add_mc_weights.py` to add `signal_sw=1.0` via RDataFrame, or use `--mc-weight-branch`
  with a branch that exists (GEN-matched MC → weight=1 everywhere).
- **Output**: `plots_kinematics/comparison_ratio/{sample}/` (105 PDF + 105 PNG per sample)
- **Typical targets**: DPS_1, DPS_2_CS, SPS_CS (skip DPS_2_G and SPS_G due to low stats)

### Level 3: Efficiency Map Ratio/Pull Plots (`efficiency_workflow/plotting.py`)

Comparison of efficiency maps across MC subprocess samples (no data — pure MC-MC agreement).
- **Ratio plots**: `ε(sample) / ε(nominal)` for each kinematic bin → reveals subprocess dependence
- **Envelope half-width**: Max deviation from nominal across all samples per bin
- **Max-pull plots**: `|ε(sample) − ε(nominal)| / √(σ²_sample + σ²_nominal)` → statistical significance of differences
- **Yield comparison**: Bar chart of corrected yields per sample with error bars

These are produced by `build_systematic_uncertainty.py` and visualized by `write_systematic_uncertainty_plots()`.

### Helper: `add_mc_weights.py`

Adds `signal_sw=1.0` to GEN-matched MC selected files. Uses ROOT RDataFrame
`Define("signal_sw", "1.0f")` + `Snapshot` — fast and multi-threaded.
Output: `plots_kinematics/temp/jjp_mc_{sample}_weighted.root`.

Required because `plot_data_mc_comparison.py` expects a weight branch in both
data and MC trees. MC files from `selected-merged-v3` have no sWeights since
all events are true signal (GEN-matched) → weight=1 is exact.

## Efficiency-Corrected Yield Computation

```bash
bash -c 'source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh && \
  python3 compute_efficiency_corrected_yield.py \
    --data-input ../jjp_data_selected.root \
    --efficiency-dir ../merged_efficiency_output_20260601_01 \
    --correction-mode factorized \
    -o yield_result.json \
    --plot-dir yield_plots -j 4'

# Hybrid mode: factorized acceptance × 5D post-acceptance efficiency
bash -c 'source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh && \
  python3 compute_efficiency_corrected_yield.py \
    --data-input ../jjp_data_selected.root \
    --efficiency-dir ../merged_efficiency_output_20260601_01 \
    --correction-mode hybrid \
    -o yield_hybrid.json \
    --plot-dir yield_plots -j 4'
```

Outputs:
- JSON file with per-sample corrected yields, systematic envelope, total uncertainty
- Optional: yield comparison bar chart
- Optional: full ROOT tree with per-event efficiency correction weights appended

## SCand Factorization Diagnostic

The `test_acceptance_factorization.py` and `scand_factorization.py` (in `efficiency_workflow/`) test whether the factorized efficiency assumption holds:

- **Acceptance factorization**: Compare A_direct (3-body fiducial acceptance in 5D bins) vs A_factorized = A_jpsi(pT,|y|) × A_jpsi(pT,|y|) × A_phi(pT,|y|)
- **SCand factorization**: Same comparison for the full S_cand efficiency (all per-object steps combined)
- If factorization holds, the ratio A_factorized / A_direct ≈ 1 in every bin

## GEN-Matching Behavior

- **JJP/JYP MC**: GEN-matching applied by default during merge (`PassSelectedJJPGenMatch` — requires 4 muons match J/ψ mothers, 2 kaons match φ mother)
- **JJY MC**: GEN-matching NOT applied during merge (`build_genmatch_expr` returns None)
- **Data**: No GEN-matching (branches don't exist)
- `apply_genmatch_to_merged.py` can retroactively filter MC files if needed (requires GEN branches still present in input)
- MC merged files from the efficiency pipeline have GEN-matching already applied → all events are true signal

## Ordering Convention

- **J/ψ ordering**: J/ψ₁ = leading pT, J/ψ₂ = subleading pT (determined by `sel_Jpsi_1_pt ≥ sel_Jpsi_2_pt`)
- **Kaon ordering**: K₁ = leading pT, K₂ = subleading pT (`sel_Phi_K_1_pt ≥ sel_Phi_K_2_pt`)
- When loading kaon coordinates, the sorted-kaon logic re-evaluates the pT ordering at read time (see `sorted_kaon_coordinate()` in `plot_weighted_distributions.py`)

## Weight Branches

| Branch | Source | Description |
|--------|--------|-------------|
| `signal_sw` | fit_splot.py | sWeight for the signal component (sum of all signal fractions) |
| `jpsi_jpsi_phi_sw` | fit_splot.py | sWeight for the J/ψ J/ψ φ signal component |
| `*_sw` | fit_splot.py | Per-component sWeights (background, signal sub-components) |
| `effcorr_w` | compute_efficiency_corrected_yield.py | Efficiency correction weight (1/ε) |
| `effcorr_w_err` | compute_efficiency_corrected_yield.py | Efficiency correction weight uncertainty |

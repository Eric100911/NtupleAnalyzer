# Repository Guidelines

## Project Structure & Module Organization

This repository contains a ROOT-based ntuple workflow for JJP, JYP, and JJY channels. Core Python scripts live at the repository root:

- `ntuple_pipeline_common.py`: shared channel configuration, input discovery, C++ RDataFrame helpers (`BestCandIndex*`, `PassSelected*GenMatch`, `Score3`), and gen-matching logic.
- `merge_apply_cuts.py`, `fit_splot.py`, `plot_weighted_distributions.py`: main assocPV merge, fit/sPlot, and plotting stages.
- **Efficiency workflow:**
  - `run_efficiency.py` → `efficiency_workflow/cli_efficiency.py`: per-file efficiency shard computation. Supports `--max-files` for testing, `--efficiency-backend vectorized|python-loop`, `--remote-access-mode fallback|direct|stage`.
  - `prepare_efficiency_shards.py`: generate Condor submit lists for sharded efficiency.
  - `merge_efficiency_shards.py`: merge shard outputs into per-sample `efficiency_maps.parquet`.
  - `build_derived_efficiency.py`: produce acceptance, conditional-efficiency, per-object acceptance, and stacked-J/ψ maps and plots from merged output.
  - `test_efficiency_plots.py`: smoke-test plot generation from derived parquet files.
- `efficiency_workflow/`: efficiency pipeline library.
  - `efficiency.py`: `EfficiencyBinning`, `EFFICIENCY_STEPS`, `CORRELATED_MAP_STEPS`, gen-system finding, vectorized and Python-loop backends, all map-builder functions.
  - `plotting.py`: heatmap functions (`save_efficiency_heatmap`, `save_efficiency_heatmap_pair`, `write_derived_plots`, `write_per_object_acceptance_plots`, `write_stacked_jpsi_plots`, `write_efficiency_plots`), CMS styling via mplhep.
  - `config.py`: `OfflineSelectionConfig` (pT/η thresholds), `CmsPlotStyleConfig`.
  - `io.py`, `truth.py`: parquet/JSON I/O and truth-matching utilities.
- `analyze_ntuple_*.py`, `plot_*.py`, `study_*.py`: channel-specific analysis and study scripts.
- `run_*.sh`: local wrappers for common workflows.
- `condor/`: HTCondor submit files, `submit.sh`, `run_wrapper.sh`, `build_runtime_tarball.sh`.

Keep generated ROOT files, plots, and Condor logs outside git, usually under `/eos/...`, `/tmp/...`, or `condor/logs/`.

## Build, Test, and Development Commands

- `python3 -m py_compile *.py efficiency_workflow/*.py`: syntax-check all Python scripts.
- `./run_all.sh`: run the default JJP and JUP data workflows.
- `./run_assoc_merge.sh --channel JUP --dataset data -n 10000 -j 1`: run a small local merge test.
- `./run_assoc_fit.sh --channel JJY --dataset mc --sample DPS_1 -j 1`: run only the fit/sPlot stage.
- `./run_assoc_plots.sh --channel JUP --dataset data -j 1`: run weighted plotting.
- `cd condor && ./submit.sh --check-proxy`: verify CMS proxy before submission.
- `cd condor && ./submit.sh jjy_mc --mode all --jobs 1 --dry-run`: inspect a Condor command without submitting.

**Efficiency workflow commands (must source LCG_109a first):**
```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh

# One-file efficiency test
python3 run_efficiency.py --analysis-mode JpsiJpsiPhi \
  --output-dir /tmp/chiw/eff_test --max-files 1 --samples JJP_DPS2_CS --skip-plots

# Build derived products from merge output
python3 build_derived_efficiency.py --input-dir <merge_dir> [--output-dir <dir>] [--skip-plots] [--min-plot-total N]
```

## Coding Style & Naming Conventions

Use Python 3 with 4-space indentation. Keep scripts executable only when they are command-line entry points. Prefer descriptive snake_case for functions, variables, and branch helpers. Keep channel names and sample keys uppercase and consistent with existing values such as `JJP`, `JUP`, `JJY`, `DPS_1`, and `TPS`. Put shared workflow logic in `ntuple_pipeline_common.py`; keep wrappers thin.

## Testing Guidelines

There is no formal test suite. Before opening changes, run `python3 -m py_compile *.py` and at least one bounded event test using `-n` with output under `/tmp/<user>/...`. For behavior changes, validate the affected stage and channel, for example merge plus fit for cut changes. Note expected RooFit numerical warnings in the PR.

Plans for nontrivial changes should be based on careful code reading, comprehensive, detailed, and contain relevant code snippets.

## Commit & Pull Request Guidelines

Recent history uses short imperative messages, often with prefixes like `feat:` or `fix:`. Keep commits focused, for example `fix: adjust JJY fit initialization`. Pull requests should describe the affected channel, commands run, input sample or max-event limit, output location, and proxy/Condor assumptions. Include plots when visual output changes.

## HTCondor Conventions

### Job flavors

Always place `+JobFlavour` **before** `request_cpus`, `request_memory`, and `request_disk` so explicit settings take precedence over flavor defaults.

| Flavor | Max runtime | Default CPUs |
|--------|-------------|--------------|
| espresso | 20 min | 1 |
| microcentury | 1 h | 1 |
| longlunch | 2 h | 1 |
| workday | 8 h | 3 |
| tomorrow | 24 h | 3 |
| testmatch | 3 d | — |
| nextweek | 1 w | — |

Default per workflow: `microcentury` for efficiency shards, `workday` for MC and data merge/fit jobs, `tomorrow` for long-running JJY MC.

Use `--flavor` on `submit.sh` to override at submit time.

### Log files

Use one log file per cluster (omit `$(Process)`):

```
log = $(log_dir)/<workflow>_$(Cluster).log
```

Output and error files remain per-job with `$(Process)` since they are written independently by each process.

### Tarball-based jobs

For jobs using the runtime tarball pattern (`jjp_efficiency`):
```
should_transfer_files = YES
when_to_transfer_output = ON_EXIT
transfer_input_files = $(RUNTIME_TARBALL)
```

The `run_wrapper.sh` unpacks when `RUNTIME_TARBALL` is set; other workflows fall back to `ANALYZER_DIR`.

### Testing condor changes

After any change to `condor/` scripts (submit.sh, run_wrapper.sh, build_runtime_tarball.sh, or .sub files), run a local wrapper simulation before submitting real jobs:

```bash
# Build tarball, copy to scratch, run one-file test
cd condor && ./build_runtime_tarball.sh
TARBALL=$(ls -t condor/runtime/NtupleAnalyzer_runtime_*.tar.gz | head -1)
mkdir -p /tmp/$USER/tarball_wrapper_test && cd /tmp/$USER/tarball_wrapper_test
cp /path/to/condor/run_wrapper.sh .
cp "$TARBALL" .
RUNTIME_TARBALL="$(basename "$TARBALL")" \
  ./run_wrapper.sh run_assoc_efficiency.sh \
  --input-files root://cceos.ihep.ac.cn:1094///eos/ihep/cms/store/user/xcheng/MC_Production_v3/output/JJP_DPS2_CS/490/output_ntuple.root \
  --sample-name JJP_DPS2_CS_490 --skip-plots \
  --output-dir /tmp/$USER/jjp_eff_tarball_onefile \
  --remote-access-mode fallback --efficiency-backend vectorized \
  --stage-retries 1 --copy-timeout 25 --worker-timeout 20
```

Expected: wrapper reports unpacking, analysis completes with exit code 0, `subprocess_summary.csv` has `access_methods` populated.

## Runtime Environment

All scripts require the LCG_109a software stack. Source the environment before any local run:

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
```

This provides ROOT, Python 3, uproot, awkward, pandas, numpy, scipy, matplotlib, mplhep, and XRootD. The same view is set on Condor worker nodes via the `LCG_VIEW` environment variable in `.sub` files and is activated in `run_wrapper.sh` before any analysis script runs.

CMS-specific paths (e.g., `el9_amd64_gcc12/external`) are NOT part of the standard LCG view and must be added separately via `PYTHONPATH` or `sys.path` hacks — these appear only in Jupyter notebooks and are not needed for pipeline scripts.

## Efficiency Workflow

The efficiency pipeline computes acceptance and per-step efficiencies for J/ψ+J/ψ+φ events, producing maps binned in meson pT and rapidity.

### Pipeline stages

1. **`run_efficiency.py`** (or Condor shards via `prepare_efficiency_shards.py`): reads ntuples, finds gen-level J/ψ+J/ψ+φ systems, matches reco candidates, computes cumulative step flags, writes per-file `efficiency_counts.parquet`, `gen_systems.parquet`, `event_step_flags.parquet`.
2. **`merge_efficiency_shards.py`**: merges shard outputs into per-sample files under `<sample>/`.
3. **`build_derived_efficiency.py`**: reads merged output, produces derived maps and plots.

### Key data products

**From efficiency shards / merge** (under `<sample>/`):
- `efficiency_maps.parquet` / `efficiency_counts.parquet`: cumulative step counts binned by (pT, y). Map types: `inclusive`, `object_2d`, `correlated_3d`, `triple_1d`.
- `gen_systems.parquet`: gen-level kinematics per event (`jpsi_lead_pt`, `jpsi_sublead_pt`, `phi_pt`, `triple_pt`, etc.), plus `n_gen_jpsi`, `n_gen_phi`.
- `event_step_flags.parquet`: per-event boolean flags for each cumulative step, per-object fiducial flags (`fiducial_jpsi_lead`, `fiducial_jpsi_sublead`, `fiducial_phi`), and best-reco-candidate columns for response matrix studies.

**From `build_derived_efficiency.py`** (under `<sample>/derived/`):
- `acceptance_maps.parquet` / `.csv`: fiducial_acceptance / full_gen per object and bin. Quantity label `"acceptance_vs_full_gen"`.
- `conditional_efficiency_maps.parquet` / `.csv`: per-step conditional efficiency (each step relative to previous step survivors). First step in each map_type uses `full_gen` as baseline.
- `per_object_acceptance_maps.parquet` / `.csv`: per-object fiducial acceptance (N(obj passes fiducial) / N(full_gen)), decomposed from the combined `fiducial_acceptance` flag. Uses signed y bins.
- `stacked_jpsi_acceptance_maps.parquet` / `.csv`: lead+sublead J/ψ combined acceptance.
- `stacked_jpsi_efficiency_maps.parquet` / `.csv`: lead+sublead J/ψ combined per-step efficiency.

### EFFICIENCY_STEPS and CORRELATED_MAP_STEPS

The 15 cumulative steps (in order): `full_gen` → `fiducial_acceptance` → `hlt_muon_matched` → `single_jpsi_reco` → `double_jpsi_reco` → `single_phi_reco` → `triple_gen_matched_candidate` → `jpsi_quality` → `phi_quality` → `all6_same_recVtx` → `Pri_fitValid` → `Pri_fitPass` → `Pri_assocPVPass` → `Pri_trackPVPass` → `final_nominal`.

The 5 CORRELATED_MAP_STEPS (get 3D φ-pT-binned maps): `hlt_muon_matched`, `all6_same_recVtx`, `Pri_fitValid`, `Pri_fitPass`, `final_nominal`.

Map types and bin identity keys:
- `inclusive`: `["step"]`
- `object_2d`: `["object", "x_bin", "y_bin"]`
- `correlated_3d`: `["x_bin", "y_bin", "z_bin"]`
- `triple_1d`: `["x_axis", "x_bin"]`
- `object_acceptance_2d`: `["object", "x_bin", "y_bin"]`

### Binning

pT edges (matching offline selection thresholds `jpsi_pt_min=6.0`, `phi_pt_min=4.0` in `OfflineSelectionConfig`):
- J/ψ pT: `(6.0, 10.0, 15.0, 20.0, 30.0, 50.0, 100.0)` GeV
- φ pT: `(4.0, 6.0, 10.0, 20.0, 50.0)` GeV

Rapidity:
- |y|: `(0.0, 0.6, 1.2, 1.8, 2.4)`
- Signed y: `(-2.4, -1.8, -1.2, -0.6, 0.0, 0.6, 1.2, 1.8, 2.4)`

### HLT triggers and matching

Two triggers checked via `_event_path_or` (stored as a diagnostic):
- `HLT_Dimuon0_Jpsi3p5_Muon2_v` — 3 muons (dimuon J/ψ + extra muon pT > 2)
- `HLT_DoubleMu4_3_LowMass_v` — 2 muons (pT > 4 and 3 GeV)

The `hlt_muon_matched` step uses per-muon flags (`muIsJpsiFilterMatch`, `muIsJpsiTrigMatch`). A candidate passes if: (a) both muons of one J/ψ are matched (2-muon trigger), OR (b) one J/ψ pair is matched AND ≥3 of 4 muons are matched (3-muon trigger).

### Candidate handling

**Data analysis** (`analyze_ntuple_*.py`, `merge_apply_cuts.py`): single best candidate per event, selected by `Score3 = sqrt(pt1² + pt2² + pt3²)` across all candidates passing quality cuts. All other candidates discarded. C++ equivalent: `BestCandIndexJJP` in `ntuple_pipeline_common.py:1156`.

**MC efficiency**: "any matched candidate" OR logic — event passes a step if ≥1 reco candidate matches the gen system AND satisfies the step condition. The gen system is defined as the 2 highest-pT J/ψ and 1 highest-pT φ (with ≥2 correct-flavor daughters). Extra gen particles (≥3 J/ψ or ≥2 φ) are recorded in `n_gen_jpsi`/`n_gen_phi` but not used. About 1.8% of events with a hard φ (pT > 4) have ≥2 such φ mesons.

**Response matrix**: best-by-score reco candidate (quality cuts only, no gen-match required) stored in `event_step_flags.parquet` as `reco_best_*` columns for migration studies.

### Plot types and directory structure

Output under `<sample>/derived/plots/`:

| Subdirectory | Content | Panel type |
|---|---|---|
| `acceptance/` | Per-object fiducial acceptance (from `acc_df`) | Double (with uncertainty) |
| `conditional/` | Per-step conditional efficiency (object_2d + correlated_3d) | Double (with uncertainty) |
| `per_object_acceptance/` | Per-object acceptance from gen+event data | Single (no uncertainty) |
| `stacked_jpsi/` | Lead+sublead combined acceptance + per-step efficiency | Single (no uncertainty) |

QA uncertainty versions under `plots_with_uncertainty/` mirror `per_object_acceptance/` and `stacked_jpsi/`.

All heatmaps use Clopper-Pearson binomial confidence intervals. Color bar labels distinguish "Acceptance" from "Efficiency" via the `zlabel` parameter. Step names use human-readable labels from `_STEP_DISPLAY_NAMES` in `plotting.py`.

### Efficiency computation backends

Two backends produce identical output:
- **`vectorized`** (default): uses awkward arrays, processes all events in a chunk at once. Faster for large files.
- **`python-loop`**: iterates event-by-event. Used as a cross-check.

Both store per-object fiducial flags (`fiducial_jpsi_lead`, `fiducial_jpsi_sublead`, `fiducial_phi`) alongside the combined `fiducial_acceptance`, and the per-step cumulative flags.

## Security & Configuration Tips

Do not commit VOMS proxy files, private EOS paths containing credentials, generated ROOT outputs, or Condor logs. Check proxy validity with `voms-proxy-info --timeleft` or `condor/submit.sh --check-proxy` before remote reads or submissions.

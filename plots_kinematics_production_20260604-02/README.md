# JJP Kinematics Plot Set

This directory contains the production JJP (`J/psi + J/psi + phi`) pre-efficiency-correction kinematics plots produced by `plot_kinematics_jjp.py`.

## Inputs

- Data: `plots_kinematics/temp/jjp_data_weighted.root`
  - Tree: `selected`
  - Weight: `signal_sw`
  - Interpretation: sWeighted selected data.
- MC: `/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3/`
  - Tree: `selected`
  - Weight: `1.0`
  - Interpretation: GEN-matched selected RECO MC. These plots use reconstructed selected-candidate `sel_*` branches, not GEN-level four-vectors.

The MC selected samples are GEN-matched during `merge_apply_cuts.py`: the four selected J/psi daughter muons must match J/psi mothers, the two muons in each reconstructed J/psi must share a mother, the two J/psi mothers must be distinct, and the two phi kaons must share a phi mother.

## Contents

- `data_kinematics/`
  - Data-only sWeighted 1D distributions.
  - Includes candidate, daughter, pair-correlation, and three-body mass variables.
- `comparison/`
  - Integrated 1D Data/MC comparison plots.
  - Main panel: normalized data and all available MC subprocess samples.
  - Lower panel: `(MC - Data) / sigma_Data` using step-style MC curves with uncertainty bars.
- `comparison/correlations_2d/`
  - Separate 2D `|Delta y|` vs `|Delta phi|` heatmaps for data and for each MC subprocess.
  - The 2D plots are separated by subprocess rather than merging all MC together.

Each plot is written as both `.pdf` and `.png`.

## Style

CMS styling is applied through `mplhep`.

- Data plots use `CMS Work In Progress`.
- MC-only plots use `CMS Simulation Work In Progress`.
- PNG files are saved at increased resolution.

## Normalization

The production command used shape normalization:

```bash
python3 plot_kinematics_jjp.py \
  --mode all \
  --skip-splot \
  --weighted-data plots_kinematics/temp/jjp_data_weighted.root \
  --mc-dir /home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3 \
  -o plots_kinematics_production_20260604-02 \
  --normalize shape
```

For 1D comparison plots, each distribution is normalized to unit area before plotting. For 2D heatmaps, each heatmap is normalized by its own total bin content.

## Correlation Plot Notes

The 2D correlation branches are precomputed selected-RECO quantities:

- `sel_abs_dy_{pair} = |Delta y|`
- `sel_abs_dphi_{pair} = |Delta phi|`

The lower-left bin corresponds to:

- `|Delta y| in [0, 0.416667)`
- `|Delta phi| in [0, 0.261799)`

A validation check found no exact `(0, 0)` or near-zero artificial pileup in this bin. The stored branches agree with recomputation from selected object `y` and `phi` branches to numerical precision. The visible lower-left enhancement is therefore not from a plotting-axis swap or zero-fill bug.

The sWeighted data lower-left bin has limited effective statistics in some pairs. Example shape-normalized lower-left bin values:

| Sample | Pair | Bin fraction |
| --- | --- | ---: |
| data | `jpsi1_jpsi2` | `0.2050 +/- 0.0362` |
| data | `jpsi1_phi` | `0.0788 +/- 0.0289` |
| data | `jpsi2_phi` | `0.1147 +/- 0.0258` |
| `DPS_2_G` | `jpsi1_jpsi2` | `0.2112 +/- 0.0148` |
| `SPS_G` | `jpsi1_jpsi2` | `0.4238 +/- 0.0238` |

Low-stat MC samples such as `DPS_2_G` and `SPS_G` can show strong fluctuations or concentrated structures and should not be treated as high-stat reference shapes.

## Regeneration

Use the LCG 109a environment:

```bash
cd /home/storage29/users/chiwang/JpsiJpsiPhi/analysis/Efficiency/NtupleAnalyzer
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh

MPLCONFIGDIR=/tmp/chiw/mplconfig PYTHONUNBUFFERED=1 \
python3 plot_kinematics_jjp.py \
  --mode all \
  --skip-splot \
  --weighted-data plots_kinematics/temp/jjp_data_weighted.root \
  --mc-dir /home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3 \
  -o plots_kinematics_production_20260604-02 \
  --normalize shape
```

The script preloads required ROOT branches once per data/MC tree and prints progress messages for the preload, 1D plots, and 2D plots.

# Three-class XGBoost toy validation

Run date: 2026-11-06. This run exercises the planned XGBoost training and
classifier-score template pipeline on generated toy MC. Toy kinematic shapes
are deliberately distinct and do not predict physical JJP separation.

## Training setup

- Classes, in saved score order: DPS1, DPS2_CS, SPS_CS.
- Toy MC: 12,000 independent selected rows per component from
  `make_demo(multivariate=True)`.
- Stratified allocation per component: 4,800 training, 1,800 development,
  3,000 score-template, and 2,400 final-validation events.
- Input features exclude sample labels, event identifiers, GEN quantities,
  matching flags, reconstructed candidate masses, and weights. Kinematic
  four-vectors use fixed nominal J/ψ and φ masses; measured masses are retained
  only for the toy mass selection.
- Compared `geometry_momentum` (15 features) and `extended` (19 features,
  adding three pair masses and the three-body mass). Both compare depth 2 and 3.
- XGBoost 2.1.3 uses `objective="multi:softprob"`, three classes, equal total
  class weight, `learning_rate=0.05`, `min_child_weight=5`, regularization,
  subsampling, and development-set early stopping. Candidate models are chosen
  by development log loss. The saved Booster files are sliced to the selected
  best iteration.
- The classifier score partition uses `u=s_SPS_CS` and
  `v=s_DPS1/(s_DPS1+s_DPS2_CS)`. Three quantile intervals per coordinate are
  derived from development scores. For a zero DPS denominator, `v=0.5`.
- The selected model's final-validation score distributions are plotted
  separately for `s_DPS1`, `s_DPS2_CS`, and `s_SPS_CS`, with all three MC classes
  overlaid in each figure. The checked-in runner writes PDF and PNG versions.

Command, from the repository root:

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
python3 scripts/templates/train_xgboost_toy.py \
  --output-dir /tmp/chiw/jjp_xgboost_toy_20261106_v8 \
  --seed 20261106 --toys 50 --event-yield 2000
```

## Results

| Feature set | Selected depth | Best iteration | Development log loss | Final-validation accuracy | Final-validation log loss | Score-template closure |
|---|---:|---:|---:|---:|---:|---|
| Geometry and momentum | 2 | 791 | 0.26957 | 88.43% | 0.27200 | Passed |
| Extended | 2 | 834 | 0.26300 | 88.61% | 0.26748 | Passed |

The extended set was selected by development log loss. Its independent
validation is consistent with that small improvement. Accuracy and log loss
are diagnostics; downstream score-template closure is the relevant mixture
test. Both feature sets passed all eight held-out template compatibility cases
and ran 50 conditional Poisson toys per case at 2,000 selected signals.

For the extended model, the small-SPS toy results are:

| Injected SPS_CS | Mean fitted fraction | Toy spread | Approx. expected 95% upper bound |
|---:|---:|---:|---:|
| 10% | 9.78% | 0.68 percentage points | 11.07% |
| 1% | 0.83% | 0.31 percentage points | 1.46% |
| 0.1% | 0.066% | 0.146 percentage points | 0.414% |

These bounds are fixed-template Gaussian profile approximations, not calibrated
coverage intervals. The toys condition on the trained classifier and finite
score templates; they omit mass-fit/background fluctuations, retraining
replicas, and physics-model uncertainty.

## Artifacts and scope

The trained Booster JSON files, split manifest, feature/class metadata,
development comparisons, final-validation confusion matrices, score templates,
toy-closure results, and three overlaid score-distribution figures are under
`/tmp/chiw/jjp_xgboost_toy_20261106_v8/`. The figures are in
`score_distribution_plots/`; the authoritative summary is `study.json`. The
plotting implementation is in `scripts/templates/train_xgboost_toy.py`.

This validates mechanics only. The toy component distributions are deliberately
separated; the result says nothing about achievable JJP discrimination or SPS
sensitivity in real selected MC. The next classifier step is to apply the
frozen workflow to the statistically adequate DPS1/DPS2_CS/SPS_CS samples,
with the same event split, and compare development mixture sensitivity against
the Cartesian grids before opening final validation.

# Fixed Cartesian 3×3 baseline

Run date: 2026-11-06. This is the first fixed-grid baseline for the
three-component DPS1/DPS2_CS/SPS_CS hypothesis. It is a prototype result, not a
selected production-fraction measurement.

## Configuration

- Axes: `abs_dphi(Jpsi_1,Jpsi_2)` × `abs_dy(Jpsi_1,Jpsi_2)`.
- Shared edges: Δφ `[0, 1, 2, π]`; |Δy| `[0, 1, 2, 5]`; tails are folded into
  edge bins.
- Flattening: `b = 3*i + j`, giving nine exclusive regions.
- MC allocation: 40% training, 15% development, 25% templates, 20% final
  validation. The fixed physics edges were specified before the data fit; the
  training and development subsets were not used to optimize these edges.
- Candidate handling: old `selected` rows already apply the repository's
  per-event `bestCandIdx` procedure. Splits use original selected-tree entry
  numbers, not reused MC `(run,lumi,event)` tuples.
- Command, from the repository root:

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
python3 scripts/templates/run_cartesian_grid_study.py \
  --output-dir /tmp/chiw/jjp_cartesian_grid_3x3_20261106_toys50 \
  --toys 50 --event-yield 2000
```

## Independent MC validation

The 20% final-validation sample was independent of the 25% template sample.
Fifty conditional Poisson toys were generated for each of eight cases at 2,000
selected signal events. All eight Asimov compatibility checks passed the
prototype `p > 0.001` diagnostic. This is not interval-coverage validation and
does not include data mass-fit/background fluctuations.

| Injected SPS_CS | Toy mean | Toy spread | Approx. expected 95% upper bound |
|---:|---:|---:|---:|
| 10% | 6.84% | 6.74 percentage points | 21.0% |
| 1% | 1.76% | 3.17 percentage points | 11.1% |
| 0.1% | 0.76% | 2.38 percentage points | 10.4% |

The toy spread and bias show limited sensitivity to small SPS fractions. The
upper bounds use a Gaussian profile approximation with fixed finite-MC
covariance; they are planning diagnostics, not calibrated limits.

## Data fit diagnostic

The two-stage fit extracted SSS yields in all nine regions, then fit the three
component templates. It returned `χ² = 45.45` for 6 nominal degrees of
freedom, condition number 8.95, and a boundary SPS_CS estimate. The fitted
fractions were DPS1 84.4%, DPS2_CS 15.6%, and SPS_CS approximately zero.
These fractions must not be interpreted: the poor residual fit rejects this
baseline description at face value, and the second-stage covariance is
conditional on fixed inclusive mass shapes. Several regions also have weak
mass-fit signal yields. Mass-shape dependence, region-specific backgrounds,
component modeling, and bin-edge stability need checks before a data result.

The 2D template arrays and edges are in `grid_templates.npz`; split entry IDs,
per-cell yields/templates, mass-fit diagnostics, and the toy report are in the
run directory above. The full pair and binning scan remains to be run on
development MC before shortlisting configurations.

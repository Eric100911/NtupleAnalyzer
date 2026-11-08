# JJP separation study plan: 3×3 templates and multiclass XGBoost

## Aim and scope

Compare reconstructed correlation variables and classifier scores for separating
JJP production components at the available data and MC statistics. The primary
two-variable baseline is a **3×3 histogram: nine exclusive bins**, with binning
variations and different variable pairs. Coarser alternatives are stability
checks, rather than a replacement for that baseline.

Proceed in two steps: validate individual observables first, then compare
two-variable templates and classifier-score templates. Choose configurations
using MC studies before examining their fitted production fractions in data.
The full pair/binning scan remains to be run; the three-class XGBoost workflow
has been trained and validated on synthetic toy MC. Current execution status is
summarized below.

## Current execution status (2026-11-06)

The three-component adaptive-cell prototype and its small-SPS checks are recorded
in [Multivariable_Template_Prototype_Results.md](Multivariable_Template_Prototype_Results.md).
They do not implement the full pair/binning scan or classifier study in this
plan. The input inventory gate is recorded in
[`diagnostics/correlation_separation_20261106/inventory.md`](../diagnostics/correlation_separation_20261106/inventory.md).
That audit found no selected TPS RECO template and no available production
metadata establishing whether CS/G files are additive. The repeated
`(run,lumi,event)` values in the old MC audit
are not evidence of multiple candidates: the selected-tree procedure chooses
one `bestCandIdx` per input event, while those keys are reused across MC
production files. Existing three-class toy checks used the adequate DPS1,
DPS2_CS, and SPS_CS samples; their 24 saved configurations passed conditional
held-out MC checks. A first fixed Cartesian baseline, |Δφ(JJ)| × |Δy(JJ)|, was
run with a 3×3 grid and 50 conditional toys per mixture; its data fit has poor
goodness of fit and an SPS boundary estimate. See
[`diagnostics/correlation_separation_20261106/grid_3x3_report.md`](../diagnostics/correlation_separation_20261106/grid_3x3_report.md).
The toy XGBoost run is a pipeline check, not a physical performance result;
training on the selected RECO component samples remains. The broader
pair/binning scan also remains. Six-class work still requires the unresolved
CS/G process definitions and more rare-class statistics.
See [`diagnostics/correlation_separation_20261106/xgboost_toy_report.md`](../diagnostics/correlation_separation_20261106/xgboost_toy_report.md).

XGBoost 2.1.3 is available in the LCG 109a Python view. ROOT 6.38.04 also exposes
TMVA and `TMVA.Experimental.RBDT`. Use the Python XGBoost interface for training,
including the explicit `multi:softprob` objective and a saved class ordering.
All Python/ROOT commands must first source:

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
```

## 1. Samples, labels, and variables

Start with the existing three-component benchmark, DPS1, DPS2_CS, and SPS_CS.
The six-component hypothesis follows the JJP sample definitions in
`ntuple_pipeline_common.py`: **DPS1, DPS2_CS, DPS2_G, SPS_CS, SPS_G, TPS**.
Inventory the selected GEN-matched RECO files and usable event counts for all
six before scheduling that study. The existence of a sample configuration does
not establish that its selected sample has sufficient statistics.

The components must represent additive, mutually exclusive physics sources.
Check that CS/G samples are intended as separate contributions, rather than
alternative generator models for the same contribution. Alternative models
should instead define template variations. Do not infer the physics meaning of
`G` from its filename alone.

Use identical reconstructed selections for data and MC. Training labels come
from the MC sample; GEN matching selects genuine reconstructed signal
candidates. GEN quantities and matching flags are not training inputs. Split
by independent generated event, keeping repeated candidates, duplicate events,
and systematic replicas together. Establish event independence before using
the current scalar selected-candidate tables.

Use v1.5 names and tree `X_data` for new inputs. Existing selected local samples
require an explicit legacy adapter (`selected`, `sel_` prefix). These inputs
are distinct from raw GEN ntuples used by the efficiency pipeline.

Order J/psi candidates by reconstructed pT. Compute rapidity from four-vectors;
the ntuples store eta, not rapidity. The feature pool is:

| Group | Variables |
|---|---|
| Each of JJ, J1φ, J2φ | Absolute Δφ, absolute Δy, ΔR = sqrt(Δeta² + Δφ²) |
| Pair kinematics | M(JJ), M(J1φ), M(J2φ), vector-sum pT(JJ) |
| Three-body kinematics | M(JJφ), vector-sum pT(JJφ), absolute y(JJφ), scalar sum of object pT |
| Three-body geometry | Sum of ΔR² over the three unordered pairs; maximum pair ΔR |

Use rapidity-based ΔR and summed ΔR_y² as definition variations. They are not
the same quantities as the conventional eta-based ΔR.

Compare two BDT feature sets:

1. **Geometry and momentum:** pair separations, pT(JJ), pT(JJφ), absolute
   y(JJφ), scalar summed pT, summed ΔR², and maximum ΔR.
2. **Extended:** add the three pair masses and three-body mass.

For each set, also check whether redundant features can be removed without
reducing mixture sensitivity. Summed ΔR² and maximum ΔR are determined by the
three pair ΔR values. Three-body mass is related to the pair masses; adding it
does not introduce an independent measurement.

Exclude the individual reconstructed J/psi and φ masses used for signal
extraction, as well as sWeights, efficiencies, event identifiers, and sample
identifiers. Derive nominal feature four-vectors from reconstructed momenta
and fixed nominal daughter masses; retain measured daughter masses separately
for the signal fits. Compare measured-mass kinematic definitions as a
controlled variation. Nominal masses reduce direct mass leakage but do not
guarantee independence between scores and the fitted mass spectra.

## 2. Independent MC allocation and model selection

Use a reproducible, component-stratified event split, initially:

| Allocation | Fraction of each component | Purpose |
|---|---:|---|
| Training | 40% | Learn trees; propose kinematic bin edges |
| Development | 15% | Early stopping, binning/model comparison, score-region design |
| Templates | 25% | Final component histogram shapes and their MC uncertainty |
| Final validation | 20% | Locked-model closure and independent performance checks |

Use approximately equal total class weight in training so the largest MC file
does not determine the objective. Generated event counts are not production
priors. Retain valid nonnegative physical event weights within each class;
report their effective statistics. Signed weights require a different
treatment from this prototype.

Compare configurations using training/development MC, with development
statistics uncertainties included. Freeze feature sets, binning, tree settings,
and the shortlist before constructing final templates and opening final
validation results. Do not select the best model on the final validation set
and then describe its performance as independent. A failed final check triggers
diagnosis and a new validation strategy, rather than repeated tuning on the
same held-out events.

If a rare component cannot support this allocation, first reduce model
complexity or request more MC. Cross-fitting is a possible later study, but
predictions from overlapping training folds have dependencies that must be
propagated. Reusing training events as final template events is not the
baseline solution.

## 3. Step A: validate single-observable templates

For each candidate variable:

1. Compare 3, 4, and 6 bins, including fixed physics boundaries and quantile
   boundaries derived from training MC. Include the same folded tails in every
   configuration so comparisons use the same selected phase space.
2. Check shape separation, per-component bin occupancy, weighted effective
   counts, template rank, and conditioning.
3. On development MC, fit injected mixtures with realistic yield/background
   scenarios. Check bias, expected fraction uncertainty, and small-component
   upper limits. Training accuracy or a visually different shape is not a
   sufficient selection criterion.
4. Freeze the shortlist, then perform independent MC closure and data mass-fit
   checks. Test pure components, interior mixtures, and selected SPS fractions
   of 10%, 1%, and 0.1%. Include combined-small-SPS scenarios for six classes.

Report numerical convergence, model compatibility, and sensitivity separately.
A fit can converge and still have little resolving power. A zero SPS estimate
is allowed and is not itself evidence of failure. Individual observables need
not resolve all six components to be useful in a multivariable classifier;
weak marginal separation does not rule out useful correlations.

## 4. Step B1: two-variable 3×3 histogram templates

### Variable combinations

Run the main nine-bin scan for the following physically motivated pairs:

| Family | Initial pairs |
|---|---|
| Angular | Absolute Δφ(JJ) × absolute Δy(JJ); repeat for J1φ and J2φ |
| Cross-pair angles | Absolute Δφ(J1φ) × absolute Δφ(J2φ); absolute Δy(J1φ) × absolute Δy(J2φ) |
| Pair mass and recoil | M(JJ) × pT(JJ); M(J1φ) × M(J2φ) |
| Three-body mass and geometry | M(JJφ) × summed ΔR²; M(JJφ) × maximum ΔR |
| Three-body recoil | pT(JJφ) × summed ΔR²; M(JJφ) × pT(JJφ) |
| Geometry | ΔR(JJ) × maximum ΔR; ΔR(J1φ) × ΔR(J2φ) |
| Rapidity and recoil | Absolute y(JJφ) × pT(JJφ) |

Then rank all distinct pairs from the retained feature pool on development MC.
Treat this broad scan as model selection and use its uncertainty/stability,
rather than interpreting the largest observed gain as an unbiased estimate.
Keep a small shortlist for final validation and data fits. Reuse a common MC
split and common injected mixtures to make comparisons meaningful.

### Binning strategy scan

| Strategy | Construction and purpose |
|---|---|
| Fixed 3×3 | Three physics-motivated intervals per axis; transparent baseline |
| Quantile 3×3 | Three marginal intervals per axis from an equal-class-weighted training mixture |
| Separation-oriented 3×3 | Optimize the two global cuts on each axis using development mixture sensitivity, with occupancy constraints |
| Aspect-ratio variations | 2×3, 3×2, 3×4, and 4×3; compare information per extracted mass-fit yield |
| Coarsening/finer checks | 2×2 and 4×4, where statistics and template rank permit |
| Conditional nine regions | Three x intervals and three y intervals within each x interval; nine exclusive regions with x-dependent y cuts |

Marginal quantiles do not guarantee nine equally populated cells when the axes
are correlated, and pooled occupancy does not guarantee occupancy for each
component. Check both. Conditional regions are a distinct partition and must
be labeled accordingly; they are not a Cartesian grid with shared y edges.
For the optimized grid, keep shared edges so it remains a genuine 3×3 grid.

Save full 2D shapes, edges, and per-cell diagnostics. A 3×3 histogram can be
flattened using `b = 3*i + j` for numerical fitting without changing its 2D
bin probabilities or discarding correlations. This is a **binned 2D template
fit**. It differs from the earlier multivariable adaptive cell-template
prototype and from a continuous multidimensional PDF fit.

With B bins and K free production yields, the template matrix is B×K. It must
have rank K, and useful precision additionally requires good conditioning.
For a 3×3 grid, B=9: the nominal residual degrees of freedom are 6 for three
components and 3 for six components. A 2×2 grid cannot determine six free
yields. B≥K is necessary for rank K; B>K leaves residual information for model
checks. Boundaries and fitted uncertainties affect goodness-of-fit calibration.

## 5. Step B2: establish the classifier-score template fit

### What multiclass training learns

Assign one integer target per production component. Train a shallow multiclass
XGBoost model with `objective="multi:softprob"`, `num_class=K`, regularization,
and development-set early stopping. Start with depths 2–3 and a small tuning
grid; additional trees or features must improve development mixture
sensitivity. Save the model, feature definitions, class order, split manifest,
weights, and chosen iteration count.

For each event with reconstructed features x, the model returns:

```text
s(x) = [s_1(x), ..., s_K(x)],   s_k >= 0,   sum(s_k) = 1.
```

The scores describe resemblance to training classes. Their normalization does
not make them data production fractions or physically calibrated event
probabilities. In the ideal classifier limit, s_k/s_l estimates a class-density
ratio multiplied by the training-prior ratio; class balancing changes that
prior ratio. A template fit can use the scores without interpreting them as
true data probabilities because it models their distribution for each source.

Do not estimate yields by summing scores or counting only the winning class.

### Three classes: yes, a 2D score template is a natural baseline

For DPS1, DPS2_CS, SPS_CS, use `(s_DPS1, s_SPS_CS)` as two independent score
coordinates; the third score is their complement. Events occupy a triangle:
`s_DPS1 + s_SPS_CS <= 1`.

1. Apply the frozen model to independent template MC and data.
2. Build one normalized 2D score histogram per MC component.
3. Extract one triple-resonance data yield per exclusive score region from the
   three reconstructed mass spectra.
4. Fit those yields using the component score templates and their uncertainties.

Try a raw-score 3×3 grid and development-quantile edges, reporting geometrically
forbidden cells explicitly. A regular raw-score grid can have fewer than nine
populated cells because of the triangle. Never add arbitrary pseudocounts to
make impossible regions fit.

For a nine-region comparison, also use a conditional 3×3 score partition, or
the coordinates

```text
u = s_SPS_CS
v = s_DPS1 / (s_DPS1 + s_DPS2_CS).
```

The second choice maps the interior to a square: u separates SPS from DPS and
v separates the two DPS types. The transformation preserves all three-class
score information away from the SPS-only vertex. Define a deterministic
convention for a zero denominator, and test boundary handling. It does not
guarantee uniform MC occupancy. Use three intervals on each transformed axis
as a further 3×3 baseline. Every event enters one region exactly once.

Call this a **2D classifier-score template fit**, specifying whether the axes
are raw or transformed scores. It is a two-stage mass-yield extraction and
template fit, rather than a simultaneous mass-and-score likelihood.

### Six classes: five independent scores, but no mandatory 5D histogram

Six normalized scores have at most five independent coordinates. Retaining
the complete score vector therefore naturally leads to a five-dimensional
score representation. It does **not** require a five-dimensional histogram to
estimate six fractions. Even a 1D observable can distinguish six components if
its binned shapes form a well-conditioned rank-six template matrix.

Compare the following representations:

| Representation | Fit observations | Information/statistics tradeoff |
|---|---|---|
| Full five-coordinate histogram | One yield per populated 5D region | Retains correlations at the chosen resolution; potentially many sparse regions |
| Two selected score contrasts, 3×3 | Nine exclusive regions | Can identify six yields if rank is six; discarded score directions may hide important distinctions |
| Adaptive regions in the full score vector | Initially 9, 12, or 18 exclusive regions | Uses all scores to define a compact partition; control occupancy and check lost sensitivity |
| Hierarchical exclusive categories | Split DPS/SPS/TPS regions, then split ambiguous subclasses | Concentrates regions on relevant distinctions; all yields fitted together |

For two contrasts, consider aggregate SPS score versus the conditional DPS2
score within DPS, and compare alternative contrasts sensitive to TPS and
CS/G differences. Any chosen pair may lose distinctions between some of the
six classes. Do not assume that the three-class SPS/DPS coordinates remain
sufficient after expanding the component basis.

For full-vector adaptive regions, train the partition on training/development
scores and apply it unchanged to template MC, validation MC, and data. Call the
result a **classifier-score cell-template fit**, recording its six score
inputs and actual region count. It is not a continuous 5D PDF fit.

An argmax classifier creates only six categories for six components. It loses
score information and leaves no nominal residual degrees of freedom if all
six yields float. Prefer additional subdivisions of ambiguous categories when
statistics support them.

Do not multiply separate score-projection likelihoods or stack projections
with diagonal errors: they reuse the same events. A hierarchical partition
must define exclusive final regions, followed by one fit to all six yields.
If two components remain nearly indistinguishable, report identifiable sums
or upper limits, or introduce justified external constraints with their
uncertainties. A classifier cannot create separation absent from RECO inputs.

## 6. Extracting production yields from data

For either kinematic bins or score regions, freeze the entire event-to-region
mapping before fitting data production fractions.

1. Fit the inclusive three resonance masses to initialize signal/background
   shapes, then examine their stability across the chosen regions. The mass
   model includes SSS and the seven other combinations of signal/background
   for the two J/psi masses and the φ mass. These eight mass categories are
   distinct from the three or six production sources within SSS.
2. Extract SSS yields Y_b in every exclusive region. In the initial prototype,
   share fixed inclusive shapes and float mass-category yields per region.
   Propagate shared mass-shape uncertainty through event bootstrap with global
   refits, and test region-dependent shape alternatives. Neither nominal
   feature masses nor training without individual masses establishes mass
   independence, especially for backgrounds.
3. From independent template MC, calculate
   `T_bk = sumw(component k in region b) / sumw(component k in all regions)`.
   Each column sums to one. Preserve finite-MC shape covariance and its
   normalization-induced correlations.
4. Fit `mu_b = sum_k N_k*T_bk`, with all N_k nonnegative. For approximately
   Gaussian extracted yields, minimize
   `(Y - T*N)^T V^-1 (Y - T*N)` with the full data-yield covariance V.
   Fitted mass yields are not raw Poisson counts; retain their mass-fit errors.
   Propagate MC template uncertainty as well.
5. Report selected RECO yields and fractions, component correlations,
   goodness-of-fit diagnostics, profile intervals/upper limits, and response
   to modeling variations. Detector efficiencies are required to convert
   selected fractions into cross-section fractions.

If weak per-region signals invalidate the Gaussian second stage, compare a
coarser partition and a **simultaneous mass fit across exclusive regions**.
In that likelihood, the SSS yield in region b is constrained to
`sum_k N_k*T_bk`, while background yields and appropriate mass-shape nuisances
are handled in the mass model. This uses raw mass data without treating
estimated yields as Poisson counts. A common SSS mass shape assumes compatible
conditional shapes across production sources; otherwise include validated
component-dependent shapes. Describe this likelihood explicitly rather than
calling every combined fit a "joint fit."

Mass-model variations and signal-plus-background pseudo-experiments must
validate the complete extraction. Signal-only MC closure cannot validate
background subtraction or score-dependent mass sculpting in data.

## 7. What statistics are needed?

### Template MC: occupancy matters more than dimensionality alone

For weighted events, use `n_eff = (sumw)^2/sumw2` per component and per retained
region. As an initial study target, seek **50–100 effective template events per
component in each important region**. This corresponds to about 14%–10%
relative uncertainty on an unnormalized bin count. These are planning targets,
not proof that a fraction measurement is accurate enough. Low-statistics tails
must be merged, modeled with justified uncertainties, or supplied with more MC.

For component k with region probability q_bk, roughly `N_template,k*q_bk`
events populate region b for equal weights. To obtain r events in every
relevant region requires `N_template,k >= max_b(r/q_bk)`. The estimate B*r
assumes uniform occupancy; correlated distributions and rare tails often need
substantially more events.

The following are illustrative equal-occupancy budgets **per component**, with
25% of its selected MC allocated to final templates:

| Representation | Regions B | Template events for 50–100 per region | Total selected MC before the four-way split |
|---|---:|---:|---:|
| 3×3 template | 9 | 450–900 | 1,800–3,600 |
| Compact score partition | 18 | 900–1,800 | 3,600–7,200 |
| Five score log-ratio axes, three intervals each | Up to 243 | 12,150–24,300 if all 243 are relevant | 48,600–97,200 under that assumption |

Five log ratios such as `log(s_k/s_6)` parameterize the score-simplex interior;
three intervals on each axis give 3^5=243 possible cells. A Cartesian grid in
five raw scores instead includes simplex-forbidden cells and may have far
fewer occupied regions. Do not demand MC in impossible cells or quote 243
populated bins as an automatic consequence of six classes. Very coarse raw
score grids can also place most ambiguous events in one bin, retaining little
useful separation despite the number of nominal cells.

The table is a template-precision budget, **not a minimum XGBoost training
requirement** or an established requirement for our actual MC. Count existing
selected events first. Even 100 events per bin may be inadequate when tiny
component sensitivity depends on small differences between large templates.
Finite-MC nuisances cannot recover an unknown shape from an empty MC region.

### Training MC: determine adequacy with learning curves

There is no universal number of RECO events needed for six-class XGBoost.
It depends on feature overlap, weights, tree complexity, and the required tail
precision. Thousands of independent selected events per class can support an
initial shallow-tree study; they do not guarantee six-component separation.
Low-statistics DPS2_G and SPS_G need particular attention.

Train at 25%, 50%, 75%, and 100% of the allocated training sample, keeping
development/template/final-validation allocations fixed. Compare development
log loss, pairwise confusion, and expected mixture sensitivity. Repeat training
seeds and assess score/template stability. Additional model complexity is
useful only if development performance and downstream sensitivity support it.
Oversampling a rare MC class does not create new independent events.

### Data: signal extraction and template overlap set the precision

Data must support one mass fit per populated region. With 2,000 selected true
signals, nine uniformly populated regions contain about 222 signals each;
243 contain only about eight. These are signal counts, not total candidates,
and actual occupancies can be much less uniform. Background, mass resolution,
and region-dependent shapes determine whether each extraction is reliable.
A fixed threshold on total candidates cannot establish reliable signal errors.

For a first planning estimate, with fixed templates and an interior solution,
the yield information matrix is `I_N = T^T V^-1 T`. Its eigenvalues and inverse
quantify degeneracy and expected yield covariance. Transform that covariance
to fractions, then include template MC and mass-model uncertainty in toys.
The number of features or classifier accuracy does not replace this analysis.

Even with perfect event labels, a fraction f in N signals contributes only
N*f events. At N=2,000, SPS fractions of 10%, 1%, and 0.1% correspond to about
200, 20, and 2 events, with ideal relative counting errors of 7%, 22%, and 71%.
Reaching 10% relative precision would require at least roughly `100/f` total
signals: 1,000, 10,000, or 100,000 in these examples. These are ideal counting
benchmarks with perfect classification and no background or systematic
uncertainty; overlapping templates generally need more data. For suppressed
SPS, a useful upper limit may be the achievable result.

## 8. Validation, decisions, and deliverables

Compare all shortlisted methods at common selected signal yields, at least
500, 2,000, and 10,000, with matched injected mixtures. Include realistic
signal-plus-background mass spectra, separate MC resampling, and retraining
replicas for shortlisted classifiers. Fixed-model/template toys and the full
training-to-fit ensemble answer different questions; label both.

Record:

- Per-class selected/train/template counts, per-region sumw/sumw2/n_eff,
  mass-fit signal significance and convergence, and unusable regions.
- Pairwise template distinguishability, matrix rank/conditioning, fraction
  correlations, bias, uncertainty, and approximate expected SPS upper limits.
- Profile-interval/limit coverage from adequate full-chain toy ensembles,
  especially at zero yields; small pilot ensembles establish feasibility only.
- Stability versus binning, seed, feature set, MC modeling, and mass-shape
  alternatives. Overall accuracy/AUC and feature importance are diagnostics;
  they are not the primary mixture-sensitivity metric.

Choose a nominal representation from development performance and validate it
independently. Prefer the simpler method when expected sensitivity is similar.
Keep alternate 3×3 pairs and score representations as correlated cross-checks,
not independent measurements to multiply together. Existing real-data
template residuals already motivate mass-model and component-basis checks;
better classification alone does not establish adequate data modeling.

The implementation sequence and reviewable outputs will be:

1. **Inventory and definitions:** sample/label manifest, event independence,
   feature definitions, available statistics, and deterministic MC allocations.
2. **Single-variable validation:** occupancy/separation report and a shortlist
   of usable observables; retain correlation-only candidates for BDT studies.
3. **Kinematic grids:** explicit Cartesian 3×3 templates, binning/pair scans,
   conditional-region comparisons, and MC sensitivity rankings.
4. **Three-class XGBoost:** geometry/momentum and extended models, learning
   curves, raw/transformed 2D score templates, and comparison to the grids.
5. **Six-class feasibility:** verify additive labels and samples; compare
   nine-bin rank-six hypotheses with compact full-score partitions. Attempt a
   finer full 5D histogram only if per-region MC/data budgets justify it.
6. **Final extraction:** freeze the selected method, validate the full chain,
   then fit data and report selected yields/fractions or identifiable sums and
   limits with MC, mass-model, and training uncertainties clearly specified.

Save configuration JSON, model files, split manifests, bin maps, 2D templates,
per-region mass-fit products, covariance matrices, and comparison tables in
fresh output directories. Extend the existing fit machinery while keeping
Cartesian grids, adaptive cell templates, and classifier-score templates
distinct in their CLI/configuration names and result metadata.

Related existing workflow:
[Correlation_Template_Fit.md](Correlation_Template_Fit.md),
[Multivariable_Template_Study.md](Multivariable_Template_Study.md), and
[Multivariable_Template_Prototype_Results.md](Multivariable_Template_Prototype_Results.md).

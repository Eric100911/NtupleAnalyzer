# Unified classifier stages

The `ntuple_analyzer.adapters.classifier` adapter invokes the existing numerical
functions under LCG 109a. It supports JJP and the native phi-reweighted baseline.
It never marks a fit accepted from a zero process exit alone: saved reliable
numerical diagnostics (or successful signal-only control optimization) are required.
The workflow publisher owns atomic stage publication and `.complete.json`.

Stages and stable products:

| Stage | Product / numerical operation |
|---|---|
| select | `selected.root`, `selection.json`; explicit legacy scalar table or shared raw best-candidate selector |
| features | `full_features.parquet`, complete extraction provenance; deterministic identity partitions |
| reweight | `event_weights.parquet`, `phi_maps.json`; native shape and balanced objective weights remain separate |
| train | `phi_reweighted/`; existing development-selected XGBoost training |
| score | `study/`; portable model/cache and validated saved template/final predictions |
| templates | `response_templates.npz`, weighted covariance/statistics; heldout-template pool only |
| fit | `events.npz`, `fit_result.json`; consumes exactly the declared frozen response matrix |
| observable-fit | independent raw-mass bin extractions, saved integrated predictions and covariance |
| plot | rerenders saved `signal_mixture.json` only; no ROOT, events, training or fits |

`classifier.features` is an ordered subset of the defined nominal-mass feature
names. The `full_correlation_21` default excludes the individual `phi_pt` input.
The class order is `DPS1,DPS2_CS,DPS2_G,SPS_CS,SPS_G,TPS`. Manifests freeze the
feature order, nominal masses, selection and response definition. The response
is six argmax labels times three TPS bins times three summed-DPS bins, with
edges `[0,.2,.5,1.000001]`, right-search bin assignment, and a `1e-6` common
normalized template floor. The score-1 endpoint is included by the sentinel.

`inputs.classifier_study` reuses an explicitly frozen legacy or portable study.
External models, scores, source cache and JSON dependencies are inventoried for
incremental rebuilds. A score export copies model products and full feature
cache into the new run; it requires no historical external ancestry afterward.
The initial score stage validates predictions emitted by `train_variant`, which
still emits them during training; it does not tune or retrain the selected model.

For extraction use `inputs.classifier_feature_cache` (with adjacent complete
`source_manifest.json`) or `inputs.classifier_raw_root`. A JSON
`inputs.classifier_mc_manifest` may explicitly provide `raw_root`. New map fits require `inputs.phi_target`. The default and supported policy is
`classifier.map_partition_policy: training-only-native`: the existing map fitter
uses each class training partition, freezes the training normalization, and
applies those maps to other partitions. Signed data sWeights remain the target.

Data requires `inputs.data_selection_manifest` with selection ID, deduplication,
candidate ordering/index branch, exact mass windows and actual event-identity
branches. `inputs.selected_data: {path: ..., schema: legacy_selected}` means a
scalar `selected`/`sel_*` table. `inputs.raw_data` accepts a raw ROOT file or a JSON/YAML files-list manifest and invokes the shared selector on
`X_data`, preserves event identity and candidate index, and coherently orders
J/psi momenta and masses by pT. Feature construction computes rapidity from
momentum/mass; changing a tree name never substitutes for candidate selection.

`fit.mode` supports `data`, `toy` and `signal-control`; `fit.mixture` supports
`fitted` or `fixed`. Fixed mode requires six normalized nonnegative
`fit.fractions` and `fit.fraction_provenance`. It fits one inclusive mass category
and uses that common normalization for every independent observable extraction.
It reports a fixed hypothesis rather than a measured composition. Native MC
shape weights build templates; measured data masses enter unweighted.
`fit.mass_config` and `fit.observable_mass_config` reference numerical JSON
configuration. Class-dependent response mass shapes require a distinct explicit
mass-only observable configuration.

`fit.continuation_attempts` defaults to one and is bounded to 0–3. Each rejected
observable attempt is preserved. Continuation initializes from its selected
previous parameters without changing the physical model, binning or numerical
acceptance thresholds. Any unresolved observable makes the stage partial.
Endpoint overflows are folded into the original finite endpoint bins.
Conditional covariance excludes unavailable same-data normalization/extraction,
map-target and retraining correlations; the manifests preserve that scope.

`plots.input_dir` (or `inputs.fit_results`) selects existing saved integrated
JSON and bypasses the numerical DAG. `plots.pattern` defaults to
`**/signal_mixture.json`; `plots.normalization` is `differential_yield` and
`plots.cms_caption` defaults to `Work In Progress`. Caption changes only render
plots. Existing outputs are never overwritten. For an efficiency bridge, an
explicit `fit.contract` (legacy alias `fit.efficiency_contract`) is copied into the accepted result; for data it must exactly match the selected-input manifest `efficiency_contract`;
compatibility is validated by the normalization adapter, never inferred from JJP.

Bounded validation:

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
python3 -m unittest discover -s tests -p 'test_unified_classifier*.py' -v
```

Plot height and axis transformations are independent presentation settings:

```yaml
plots:
  plot_height_per_unit_interval: true
  plot_axis_scaling: {x: linear, y: linear}
  observables:
    pt_jj: {plot_axis_scaling: {x: log}}
    pt_j1phi: {plot_axis_scaling: {x: log}}
    pt_j2phi: {plot_axis_scaling: {x: log}}
    pt_jjp: {plot_axis_scaling: {x: log}}
    m_jj: {plot_axis_scaling: {x: log}}
    m_j1phi: {plot_axis_scaling: {x: log}}
    m_j2phi: {plot_axis_scaling: {x: log}}
    m_jjp: {plot_axis_scaling: {x: log}}
```

Observable settings override global defaults independently; specifying only x
retains global y. An observable may also override `plot_height_per_unit_interval`.
The default true divides heights/errors by original **linear** bin widths and
covariances by their outer product. False displays integrated yields per bin.
Log x changes both distribution and ratio axes without any Jacobian: a density
in yield/GeV remains yield/GeV. Neither setting changes areas, likelihood
inputs, integrated covariance, support thresholds, or ratio values. Saved JSON
retains integrated originals and physical `differential_yield` and separately
records actual `displayed_height`, height mode, and resolved axis scales.

Log x requires strictly positive original bin edges. Invalid edges fail before
rendering, without dropping, clipping, or changing bins. Select linear x or
produce scientifically justified positive binning separately. Log y requires
positive visible signal lower-error endpoints and prediction lower uncertainty
bands, and nonnegative stacked components; zero component contributions are
allowed. Otherwise choose linear y. Ratio y remains linear. Missing observable
overrides are recorded in `unused_observable_overrides`: the pair-system pT
names `pt_j1phi`/`pt_j2phi` never alias individual J/psi pT, and absent saved
spectra are never produced by refitting.

Display limits are independent of bin definitions and heights. Configure
`plots.plot_axis_limits: {x_min: 0.1, x_max: 100, y_min: 1, y_max: 10000}`;
per-observable `plot_axis_limits` partially overrides the global mapping.
Limits must be finite and increasing. Log x allows a zero first bin edge only
with explicit positive `x_min`; the full original first-bin width remains the
density denominator. Negative edges remain unsupported on log x. The same x
limits apply to distribution and ratio. Log y requires explicit positive
`y_min`; its limits affect only the distribution, and ratio y stays linear.

On log y, positive measured centers retain their original coordinates. Error
segments and prediction bands stop at the display floor; no lower cap or
statistical endpoint is invented there. Nonpositive centers have no marker.
The saved integrated measurements, errors and covariance remain untouched;
`display_clipping` records omitted centers and display intersections. These
rules supersede the earlier strict lower-error rejection policy above.

Upper-limit arrows require explicit saved `signal_upper_limits`, one entry per
bin: `null` or `{value: 12.3, confidence_level: 0.95, method: "profile", provenance:
"external result"}`. `value` is a positive integrated-yield bound; confidence
level must lie strictly between zero and one. Method and provenance are optional
strings. The arrow uses the supplied bound divided by the original width when
height scaling is enabled. Its graphical length carries no statistical meaning.
Bounds below the log display floor remain saved but are not moved to the floor.
No limit is inferred from symmetric errors, a negative central value, or a
profile error crossing zero. `plot_signal_mixture` accepts explicit limits or
passes through `extraction.signal_upper_limits`; saved-JSON replotting retains
their confidence metadata.

The legacy `normalization: differential_yield` key remains an accepted
compatibility label. The new height boolean is authoritative, including false;
new configurations should use `plot_height_per_unit_interval` instead.

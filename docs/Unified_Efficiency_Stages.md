# Unified efficiency stages

The adapters preserve the existing numerical implementations and publish only
inside the workflow's scratch directory. `manifest.json` records the actual
child artifacts; the core owns completion markers. All stages currently require
channel `JJP`. Run Python with LCG 109a sourced in the same shell.

`inputs.efficiency_products` reuses a local merged-product directory without
scanning raw MC. Otherwise `inputs.input_file_manifest` and
`efficiency.config` are mandatory; automatic EOS discovery is disabled.
`efficiency.samples` uses the canonical `JJP_DPS1`, `JJP_DPS2_CS`,
`JJP_DPS2_G`, `JJP_SPS_CS`, `JJP_SPS_G`, `JJP_TPS` ordering by default.

Separate `inputs.efficiency_run_a_manifest` and
`inputs.efficiency_run_b_manifest` execute independent calculations under
`products/run_a` and `products/run_b`. `efficiency.run_a.config` and
`efficiency.run_b.config` can override the nominal YAML independently.
Acceptance is derived from each population's saved conditional counts, without
a second raw scan. The existing factorized-map builder joins GEN/event rows
from a single population and builds both object and event factors together.
For separate runs, explicitly select `efficiency.map_run: run_b` (or `run_a`
when its schema supports all requested factors). This builds maps from that
population only. It does not combine singles efficiencies from A with event
factors from B. A validated cross-population combination remains future work.

The `acceptance` stage copies products into fresh scratch before deriving maps.
The `maps` stage similarly copies acceptance products before calling
`build_factorized_maps`. `efficiency.correction_mode: hybrid` additionally
builds post-acceptance 5D maps. Existing source directories are never modified.

The default `correct` mode is six-class normalization. Supply an accepted
`inputs.fit_results` JSON, or use the current run's `fit/fit_result.json`, and
an explicit `efficiency.bridge` JSON. Fit artifacts must contain `status:
accepted`, `class_order`, `class_yields`, full `class_covariance`, and `contract`.
Optional `total_yield` and `total_variance` are checked against the vector and
full covariance sum. Partial or rejected fits cannot be corrected.

The bridge requires identical `fit_contract` and `map_contract`, also matching
the fit's contract, with these fields:

- `selection_id`, `endpoint`, `gen_denominator` and canonical six-class order;
- positive `generated_totals`, with one exposure per class;
- `axes: [pt, signed_y]` and `folding: none`, or `[pt, abs_y]` and `folding: abs_y`;
- explicit `uncertainty_scope` describing the supplied uncertainty inputs.

It supplies `efficiencies`, C×K `numerators` and `denominators`,
`efficiency_covariance`, `count_covariance`, `luminosity`,
`luminosity_variance`, `branching_fractions`, `branching_covariance`, and
`scope`. Covariances may explicitly be zero, but omission is rejected.
Optional `mixing_joint_covariance` uses vector order N, efficiency, flattened
numerator, flattened denominator. `cross_section_joint_covariance` uses N,
efficiency, luminosity, branching fraction. Without both joint matrices, require
`covariance_assumptions` strings for `yield_efficiency`, `efficiency_counts`,
`yield_counts`, and `normalization_inputs`, making any omitted cross terms
explicit. Counts obtained from the same MC population generally overlap;
independence must not be inferred from separate files.

To export real counts instead of entering arrays, use
`production_count_sources`, ordered by the six canonical classes. Each entry
contains `class`, `sample`, `gen_column` (e.g. `full_gen`), `endpoint_column`
(equal to the declared endpoint), and ordered `map_rows`. Each map row contains
a sample-relative parquet `file` and a `filters` mapping selecting exactly one
row with `passed` and `total` columns. Export derives scalar efficiency from
`event_step_flags.parquet`, verifies actual GEN exposures, and records source
paths. Supplied arrays, if present, must agree with the exported values. This
is an explicit count export, not proof that classifier and production selections
match; semantic contracts and uncertainty inputs still require analysis review.

Physical map mixing uses `N_c / (epsilon_c * generated_total_c)`. Cross-section
covariance propagates the supplied class, efficiency, luminosity, and branching
covariances, including shared off-diagonal terms. Outputs are
`normalization.json` containing `mixed_efficiency`, `cross_sections`, compatibility
metadata, and source provenance. No unit efficiencies or default luminosity are
inserted.

`correct.mode: production` instead invokes the established selected-data yield
correction CLI with `inputs.selected_data` and the current maps. This is the
existing sPlot/event-weight procedure, separate from six-class normalization.
It uses one ROOT worker and scratch-local intermediates and plots.

`validation.dependencies` defaults to an empty list. Validation therefore
never triggers an efficiency scan implicitly. `validation.artifacts` is an
explicit list of `{path, kind}` entries, with kinds `fit`, `closure`, or `plot`.
Fit and closure artifacts need accepted status; closure additionally requires
`closure_passed: true`. Fixed-count ensembles must record
`ensemble: fixed-count` and `actual_injected_counts`. Numerical acceptance is
recorded separately; failed closure produces rejected validation even for a
numerically accepted fit. Validation copies its declared evidence and preserves
diagnostics. Plot validation checks the presence of the declared plot artifact,
not scientific closure.

Production count export additionally requires matching fit/map `gen_selector`
objects with `column` and `definition`. Every source names a sample-relative
`gen_definition_file` containing the persisted `gen_selector`; the exporter
compares it to the contract and actual `gen_column`. Ordered map rows must have
identical persisted non-statistical columns across classes (conditional step,
axes, bounds, fallback level, and any other bin metadata). Statistical values
and sample labels are excluded. A matching number of rows alone is insufficient.
The exporter records all GEN-definition files alongside its count sources.

Production weighted-yield fits now apply the existing joint-mass numerical
policy: RooFit status zero, covariance quality at least three, EDM below
`1e-3`, finite yield/error/NLL, nonnegative yield and positive error. A failed
fit raises before a production correction can publish accepted output.

### Efficiency and acceptance scheme

| Step                                        | Symbol                                                  | Level                    | Map axes                                                 | Short definition                                             |
| ------------------------------------------- | ------------------------------------------------------- | ------------------------ | -------------------------------------------------------- | ------------------------------------------------------------ |
| Acceptance                                  | $A_{J/\psi}(\vec{x}_{J_i})$, $A_{\phi}(\vec{x}_{\phi})$ | per $J/\psi$ or $\phi$   | $(p_T^{\mathrm{meson}}, |y^{\mathrm{meson}}|)$           | decay daughters in fiducial region given meson in acceptance |
| muonRECOinJpsi                              | $\epsilon_{\mu\mathrm{Reco}}^{J/\psi}$                  | per $J/\psi$             | $(p_T^{J/\psi}, y^{J/\psi})$                             | both daughter muons reconstructed and matched                |
| kaonRECOinPhi                               | $\epsilon_{K\mathrm{Reco}}^{\phi}$                      | per $\phi$               | $(p_T^{\phi}, y^{\phi})$                                 | both kaons reconstructed and matched                         |
| muonID                                      | $\epsilon_{\mu\mathrm{ID}}^{J/\psi}$                    | per $J/\psi$             | $(p_T^{J/\psi}, y^{J/\psi})$                             | both matched muons pass ID                                   |
| kaonID                                      | $\epsilon_{K\mathrm{ID}}^{\phi}$                        | per $\phi$               | $(p_T^{\phi}, y^{\phi})$                                 | both matched kaons pass track/kaon selection                 |
| dimuon                                      | $\epsilon_{\mu\mu}^{J/\psi}$                            | per $J/\psi$             | $(p_T^{J/\psi}, y^{J/\psi})$                             | valid dimuon candidate                                       |
| dikaon                                      | $\epsilon_{KK}^{\phi}$                                  | per $\phi$               | $(p_T^{\phi}, y^{\phi})$                                 | valid $K^+K^-$ candidate                                     |
| HLT                                         | $\epsilon_{\mathrm{HLT}}$                               | event                    | nominally event-level                                    | trigger OR and trigger-object matching                       |
| fourMuonVertexing                           | $\epsilon_{4\mu\mathrm{vtx}}$                           | per $J/\psi J/\psi$ pair | pair-level axes                                          | valid four-muon vertex                                       |
| triOniaVertexingAndOtherEventLevelSelection | $\epsilon_{\mathrm{triOnia}}$                           | event                    | $(p_T^{J/\psi_1},p_T^{J/\psi_2})$, split by $p_T^{\phi}$ | three-meson vertex and remaining event-level cuts            |

### Current implementation notes

The parquet efficiency workflow stores object-level reconstruction and ID steps
as conditional chains, then switches to event-level flags. `s_cand` is the
event-level conjunction of the three object chains. Its object successes may be
found in different single-object candidates; it is not itself a common-composite
selection. The nominal event chain is:

```text
s_cand -> hlt_event -> four_muon_vtx
```

The primary-vertex diagnostics are parallel branches with denominator
`four_muon_vtx`, not a single cumulative final step:

```text
Pri_fitValid
Pri_fitPass
Pri_assocPVPass
Pri_trackPVPass
```

From `hlt_muon_matched` onward, the implementation preserves the composite
candidate axis until the final event-level reduction. A passing event must have
at least one *single* triple-GEN-matched composite candidate that passes all
stages in sequence. Thus, a four-muon vertex from candidate A and an
`Pri_assocPVPass` value from candidate B cannot be combined into one passing
event. The `Pri_*` endpoints remain parallel alternatives, each conditional on
that same-candidate `four_muon_vtx` chain.

Per-object daughter matching is exact: each direct GEN muon (kaon) of the
chosen J/psi (phi) must have a separately GEN-index-matched RECO muon (track).
Two duplicate RECO objects matched to the same GEN daughter do not satisfy the
two-daughter requirement.

For corrected-yield studies the default correction is factorized rather than a
single cumulative `correlated_3d` lookup. It multiplies per-object acceptance and
conditional efficiency maps in `(pT, |y|)` by event-level maps for HLT,
four-muon vertexing, and the final tri-onia/PV endpoint. The default endpoint is
`Pri_assocPVPass / four_muon_vtx`.

Factorized map lookup uses a tiered fallback:

```text
fine bin -> coarse bin -> inclusive bin
```

The nominal central value uses observed bin efficiencies after fallback
selection. Jeffreys symmetric binomial uncertainties are stored for each bin and
used for MC-stat diagnostics. The default thresholds are `N_min_fine = 30` and
`N_min_coarse = 50`.

The factorized-map `manifest.json` records every factor's explicit numerator
and denominator. In particular, the nominal HLT factor is

$$
\epsilon_{\mathrm{HLT}}
= \frac{N(s_{\mathrm{cand}}\cap \mathrm{HLT\ path\ fired}\cap
\mathrm{candidate\ muon\ matched})}{N(s_{\mathrm{cand}})}.
$$

### Small-sample validation and residual checks

`test_data/jjp_dps2_cs_v21_first200.root` is a committed, complete-branch
200-event fixture copied from the v2.1-compatible MC Production v3 JJP DPS2 CS
ntuple. It retains `mkcands/X_data`, `X_config`, and `X_lhe_run_info`; its
SHA-256 and source are recorded in the adjacent manifest. Regenerate it only
when intentionally updating the reference sample:

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
python3 scripts/efficiency/build_v21_test_fixture.py
python3 scripts/efficiency/diagnose_gen_match_depth.py \
  test_data/jjp_dps2_cs_v21_first200.root
```

For event-by-event inspection of numerator, denominator, and rejected-event
membership, run the audit tool in the LCG 109a environment:

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
python3 scripts/efficiency/audit_efficiency_events.py \
  test_data/test_JpsiJpsiPhi_v2p0_patch1_numEvent118.root \
  --output-dir /tmp/chiw/efficiency_audit
```

The report keeps cumulative-chain membership, adjacent-raw factor membership,
and the existing pipeline cutflow values separate. For each step it selects up
to five numerator, rejected, and raw-only examples and records the underlying
GEN daughters, matched RECO objects, quality operands, trigger/filter indices,
and composite-candidate witnesses. The output directory contains Markdown and
JSON reports, a provenance manifest, and complete-branch ROOT skims grouped by
source file. Use `--no-root-skim` for a report-only run.

The Markdown report groups examples by `scope / step / role`. Within each
group, one event occupies one column while selection flags, kinematics, and
branch-level witnesses occupy rows. Object-step tables stop at the current
step: for example, a `muonRECO` table shows fiducial and reconstruction
evidence but not downstream muon-ID or dimuon-candidate details. The Markdown
does not embed raw JSON; complete machine-readable evidence remains available
in `audit_report.json`.

The 118-event fixture has no `s_cand` event, so it cannot supply positive
HLT/vertex/Pri examples. Pass larger local or XRootD inputs, or an efficiency
input-file manifest, to enrich those categories. Missing categories are
reported explicitly as coverage gaps.

Two committed Run-B audit skims provide offline coverage of the event-level
chain:

```text
test_data/jjp_dps_patch2_pre2_runb_audit_source0_45events.root
test_data/jjp_dps_patch2_pre2_runb_audit_source1_35events.root
```

Together they contain 80 selected full-GEN events, including positive
`s_cand`, HLT, trigger-object matching, four-muon vertex, and all four `Pri_*`
endpoints, plus rejected examples through the four-muon stage. Both files
retain the original 480-branch `mkcands/X_data` schema and the complete
`mkcands/X_config` tree. Their source files, original entry indices, hashes,
and selection provenance are recorded in
`test_data/jjp_dps_patch2_pre2_runb_audit.manifest.json`.

After producing a shard or merged sample directory from this fixture, inspect
residual dependence on variables omitted from the event maps:

```bash
python3 scripts/efficiency/diagnose_omitted_event_variables.py \
  <sample_dir> --output omitted_event_variable_closure.parquet
```

The diagnostic reports direct conditional efficiencies for HLT, four-muon
vertexing, and `Pri_assocPVPass` versus both J/psi rapidities and phi `(pT,|y|)`.
With 200 events it is a visual/sanity check only; empty or low-count bins are
not evidence for a physics residual.

The stacked J/psi derived plots are diagnostics for the two J/psi objects
combined into one per-object map. Their parquet products use direct
`(pT, |y|)` binning (`y_axis == "abs_y"`):

```text
stacked_jpsi_acceptance_maps.parquet: fiducial acceptance
stacked_jpsi_efficiency_maps.parquet: muonRECO, muonID, dimuon
```

When only these plots are needed, use `build_derived_efficiency.py
--plot-scope stacked-jpsi` to skip cumulative, conditional, pair-level, and
systematics plots.

The correction workflow is:

```bash
python3 rebuild_efficiency_maps.py \
  --input-dir <merged_efficiency_dir> \
  --output-dir <fresh_rebuilt_dir> \
  --samples JJP_DPS1 JJP_DPS2_CS JJP_DPS2_G JJP_SPS_CS JJP_SPS_G

python3 build_derived_efficiency.py --input-dir <fresh_rebuilt_dir>

python3 -m efficiency_workflow.build_factorized_maps \
  --input-dir <fresh_rebuilt_dir> \
  --samples JJP_DPS1 JJP_DPS2_CS JJP_DPS2_G JJP_SPS_CS JJP_SPS_G

python3 compute_efficiency_corrected_yield.py \
  --data-input <jjp_data_selected.root> \
  --efficiency-dir <fresh_rebuilt_dir> \
  --plot-dir <yield_plot_dir> \
  --corrected-root <jjp_data_effcorr_selected.root> \
  -o <yield_summary.json>

python3 fit_splot.py \
  --channel JJP --dataset data \
  -i <jjp_data_effcorr_selected.root> \
  -o <jjp_data_effcorr_splot.root> \
  --effcorr-weight-branch effcorr_weight

python3 plot_weighted_distributions.py \
  --channel JJP --dataset data \
  -i <jjp_data_effcorr_splot.root> \
  -o <effcorr_splot_dynamics> \
  -w signal_effcorr_sw
```

### Definitions

Let

$$
J_i \equiv J/\psi_i,\qquad i=1,2,
$$

and

$$
\vec{x}*{J_i}=(p_T^{J_i}, |y^{J_i}|),\qquad
\vec{x}*{\phi}=(p_T^\phi, |y^\phi|).
$$

The general acceptance is defined as the fraction of generated events whose decay products are within the fiducial region, which is defined as:

$$
  A_{\mathrm{tot}} = \frac{
    N_{\mathrm{gen}}^{\mathrm{fid}}
  }{
    N_{\mathrm{gen}}(J_1, J_2, \phi\in\Omega_{\mathrm{meson}})
  }
$$

Equivalently, one write:

$$
A_{\mathrm{tot}} = \frac{
    N_{\mathrm{gen}}
      \left( 
        \mu^\pm\in\Omega_\mu,
        K^\pm\in\Omega_K
        \middle | 
        J_1, J_2, \phi\in\Omega_{\mathrm{meson}}
      \right)
  }{
    N_{\mathrm{gen}}
      \left(
        J_1, J_2, \phi\in\Omega_{\mathrm{meson}}
      \right)
  }
$$

A cross check is to factorize the acceptance by the $J/\psi$ and $\phi$ meson level:

$$
A_{J/\psi}(\vec{x}_{J_i})
=
\frac{
N_{\mathrm{gen}}(\mu_1\in\Omega_\mu, \mu_2\in\Omega_\mu | J_i\in\Omega_{\mathrm{meson}})
}{
N_{\mathrm{gen}}(J_i\in\Omega_{\mathrm{meson}})
}
$$

$$
A_{\phi}(\vec{x}_{\phi})
=
\frac{
N_{\mathrm{gen}}(K_1\in\Omega_K, K_2\in\Omega_K | \phi\in\Omega_{\mathrm{meson}})
}{
N_{\mathrm{gen}}(\phi\in\Omega_{\mathrm{meson}})
}
$$

And we approximate with:

$$
A_{\mathrm{tot}} (\vec{x}_{J_1}, \vec{x}_{J_2}, \vec{x}_{\phi}) \approx A_{J/\psi}(\vec{x}_{J_1}) A_{J/\psi}(\vec{x}_{J_2}) A_{\phi}(\vec{x}_{\phi}).
$$

This approximation is exact only if the acceptance of each meson is independent of the kinematics of the other mesons. Since unpolarized nature of the $J/\psi$'s are assumed, one may expect that the acceptance of each $J/\psi$ is not strongly dependent on the kinematics of the other $J/\psi$ or the $\phi$.

We further define the efficiency of each step as the fraction of events passing the step selection among the events passing the previous step selection, with the same kinematic binning as the acceptance.

For each $J/\psi$,

$$
\epsilon_{\mu\mathrm{Reco}|J_i}(\vec{x}_{J_i})
=

\frac{
N(S_{\mathrm{fid}}\cap\mu_1^{\mathrm{reco}}\cap\mu_2^{\mathrm{reco}})
}{
N(S_{\mathrm{fid}})
},
$$

$$
\epsilon_{\mu\mathrm{ID}|J_i}(\vec{x}_{J_i})
=

\frac{
N(S_{\mu\mathrm{Reco}}\cap\mu_1^{\mathrm{ID}}\cap\mu_2^{\mathrm{ID}})
}{
N(S_{\mu\mathrm{Reco}})
},
$$

$$
\epsilon_{\mu\mu|J_i}(\vec{x}_{J_i})
=

\frac{
N(S_{\mu\mathrm{ID}}\cap J_i^{\mathrm{reco}})
}{
N(S_{\mu\mathrm{ID}})
}.
$$

For the (\phi),

$$
\epsilon_{K\mathrm{Reco}|\phi}(\vec{x}_{\phi})
=

\frac{
N(S_{\mathrm{fid}}\cap K_1^{\mathrm{reco}}\cap K_2^{\mathrm{reco}})
}{
N(S_{\mathrm{fid}})
},
$$

$$
\epsilon_{K\mathrm{ID}|\phi}(\vec{x}_{\phi})
=

\frac{
N(S_{K\mathrm{Reco}}\cap K_1^{\mathrm{ID}}\cap K_2^{\mathrm{ID}})
}{
N(S_{K\mathrm{Reco}})
},
$$

$$
\epsilon_{KK|\phi}(\vec{x}_{\phi})
=

\frac{
N(S_{K\mathrm{ID}}\cap \phi^{\mathrm{reco}})
}{
N(S_{K\mathrm{ID}})
}.
$$

The trigger efficiency is

$$
\epsilon_{\mathrm{HLT}}
=

\frac{
N(S_{\mathrm{cand}}\cap \mathrm{HLT})
}{
N(S_{\mathrm{cand}})
}.
$$

The four-muon vertexing efficiency is defined at the (J/\psi J/\psi)-pair level:

$$
\epsilon_{4\mu\mathrm{vtx}}(\vec{x}_{JJ})
=

\frac{
N(S_{\mathrm{HLT}}\cap V_{4\mu})
}{
N(S_{\mathrm{HLT}})
}.
$$

The final event-level efficiency is

$$
\epsilon_{\mathrm{triOnia}}^{(k)}(p_T^{J_1},p_T^{J_2})
=

\frac{
N(S_{4\mu\mathrm{vtx}}\cap V_{J/\psi J/\psi\phi}\cap S_{\mathrm{other}};,p_T^\phi\in I_k)
}{
N(S_{4\mu\mathrm{vtx}};,p_T^\phi\in I_k)
}.
$$

Here (I_k) is the (k)-th (\phi)-(p_T) interval used for plotting.

The total fiducial efficiency is

$$
\begin{aligned}
\epsilon_{\mathrm{fid}}
={}&
\prod_{i=1}^{2}
\epsilon_{\mu\mathrm{Reco}|J_i}
\epsilon_{\mu\mathrm{ID}|J_i}
\epsilon_{\mu\mu|J_i}
\
&\times
\epsilon_{K\mathrm{Reco}|\phi}
\epsilon_{K\mathrm{ID}|\phi}
\epsilon_{KK|\phi}
\
&\times
\epsilon_{\mathrm{HLT}}
\epsilon_{4\mu\mathrm{vtx}}
\epsilon_{\mathrm{triOnia}} .
\end{aligned}
$$

And the full correction factor is

$$
A\epsilon
=

A_{\mathrm{tot}}\epsilon_{\mathrm{fid}}.
$$

### 

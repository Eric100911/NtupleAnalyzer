Below is a practical implementation draft for your current scheme, with the limited-statistics problem built into the design. I would implement it as a **tiered correction system**: try the most differential map first, but always keep lower-dimensional fallback maps available.

The implementation follows the same core logic as AN-22-160: acceptance and efficiency maps are derived from MC and applied event-by-event; AN-22-160 calculates maps in bins of (p_T(J/\psi)) and (y(J/\psi)) and applies the corrections candidate by candidate.  It also calculates efficiencies sequentially, with per-(J/\psi) corrections applied twice and event-level corrections such as HLT and four-muon vertexing applied once.

---

## 1. Recommended implementation hierarchy

Use three layers:

### Layer A: bookkeeping of cut stages

For each MC sample, define a sequence of boolean masks:

[
S_0 \to S_1 \to S_2 \to \cdots \to S_n .
]

For your channel,

[
pp\to J/\psi_1 J/\psi_2 \phi + X,
\quad
J/\psi\to\mu^+\mu^-,
\quad
\phi\to K^+K^- .
]

The stages should be:

[
S_{\mathrm{genMeson}}
]

[
S_{\mathrm{genDau}}
]

[
S_{\mu\mathrm{Reco}},
\quad
S_{K\mathrm{Reco}},
\quad
S_{\mu\mathrm{ID}},
\quad
S_{K\mathrm{ID}},
]

[
S_{\mu\mu},
\quad
S_{KK},
\quad
S_{\mathrm{HLT}},
\quad
S_{4\mu\mathrm{vtx}},
\quad
S_{\mathrm{triOnia}} .
]

The user-defined scheme already lists these steps as acceptance, muonRECOinJpsi, kaonRECOinPhi, muonID, kaonID, dimuon, dikaon, HLT, fourMuonVertexing, and triOniaVertexingAndOtherEventLevelSelection.

### Layer B: map production

For each efficiency factor, fill numerator and denominator histograms:

[
\epsilon_b = \frac{N_b^{\mathrm{pass}}}{N_b^{\mathrm{total}}}.
]

For limited statistics, store **three versions** of each map:

[
M^{\mathrm{fine}},\qquad
M^{\mathrm{coarse}},\qquad
M^{\mathrm{inclusive}}.
]

Then define a fallback rule:

[
M_b =
\begin{cases}
M_b^{\mathrm{fine}}, & N_b^{\mathrm{total}}\ge N_{\min}^{\mathrm{fine}},\
M_b^{\mathrm{coarse}}, & N_b^{\mathrm{total}}<N_{\min}^{\mathrm{fine}}
\text{ and } N_b^{\mathrm{coarse}}\ge N_{\min}^{\mathrm{coarse}},\
M^{\mathrm{inclusive}}, & \text{otherwise}.
\end{cases}
]

A reasonable starting point is:

[
N_{\min}^{\mathrm{fine}}=30,\qquad
N_{\min}^{\mathrm{coarse}}=50.
]

For very small samples, use (N_{\min}=10) only for diagnostic plots, not for nominal correction.

### Layer C: event correction

For each selected candidate in data or reco-level MC, assign

[
w_c=\frac{1}{A_c,\epsilon_c}.
]

For the fiducial cross section inside the meson-level region, use

[
w_c=
\frac{
1
}{
A_{\mathrm{dau}|\mathrm{meson},c},
\epsilon_{\mathrm{fid},c}
}.
]

If you later extrapolate outside the meson-level fiducial region, include

[
A_{\mathrm{meson}}
==================

\frac{
N_{\mathrm{gen}}(J_1,J_2,\phi\in\Omega_{\mathrm{meson}})
}{
N_{\mathrm{gen}}^{\mathrm{all}}
}.
]

---

## 2. Acceptance implementation

Your current acceptance is best implemented as a **conditional daughter acceptance**, not as full phase-space acceptance:

[
A_{\mathrm{dau}|\mathrm{meson}}
===============================

\frac{
N_{\mathrm{gen}}
\left(
J_1,J_2,\phi\in\Omega_{\mathrm{meson}},
\mu^\pm\in\Omega_\mu,
K^\pm\in\Omega_K
\right)
}{
N_{\mathrm{gen}}
\left(
J_1,J_2,\phi\in\Omega_{\mathrm{meson}}
\right)
}.
]

For limited statistics, do **not** start with a full 6D acceptance map. Use factorized per-meson maps as the nominal implementation:

[
A_{\mathrm{dau}|\mathrm{meson}}
\approx
A_{J/\psi}(\vec{x}*{J_1})
A*{J/\psi}(\vec{x}*{J_2})
A*{\phi}(\vec{x}_{\phi}),
]

where

[
\vec{x}*{J_i}=(p_T^{J_i}, |y^{J_i}|),
\qquad
\vec{x}*{\phi}=(p_T^\phi, |y^\phi|).
]

For each (J/\psi),

[
A_{J/\psi}(\vec{x}_{J_i})
=========================

\frac{
N_{\mathrm{gen}}
\left(
\mu_1,\mu_2\in\Omega_\mu
\mid
J_i\in\Omega_{\mathrm{meson}}
\right)
}{
N_{\mathrm{gen}}
\left(
J_i\in\Omega_{\mathrm{meson}}
\right)
}.
]

For the (\phi),

[
A_{\phi}(\vec{x}_{\phi})
========================

\frac{
N_{\mathrm{gen}}
\left(
K_1,K_2\in\Omega_K
\mid
\phi\in\Omega_{\mathrm{meson}}
\right)
}{
N_{\mathrm{gen}}
\left(
\phi\in\Omega_{\mathrm{meson}}
\right)
}.
]

This mirrors the double-(J/\psi) note, where acceptance is calculated from GEN-only MC and factorized into per-(J/\psi) maps. In AN-22-160 the single-muon acceptance is calculated sequentially in (|\eta(\mu)|) and (p_T(\mu)), using GEN-only samples with no GEN filter.

### Acceptance cross-check

Even if the factorized acceptance is nominal, produce a low-dimensional event-level cross-check:

[
A_{\mathrm{event}}(p_T^{J/\psi J/\psi\phi})
===========================================

\frac{
N_{\mathrm{gen}}^{\mathrm{fid}}
}{
N_{\mathrm{gen}}(J_1,J_2,\phi\in\Omega_{\mathrm{meson}})
}.
]

Then compare

[
A_{\mathrm{event}}
\quad \text{vs.} \quad
A_{J/\psi_1}A_{J/\psi_2}A_\phi .
]

The discrepancy can be assigned as a factorization systematic.

---

## 3. Efficiency implementation

Define all efficiencies conditionally, step by step:

[
\epsilon_s
==========

\frac{N(S_s)}{N(S_{s-1})}.
]

For the two (J/\psi) candidates:

[
\epsilon_{\mu\mathrm{Reco}|J_i}
===============================

\frac{
N(S_{\mathrm{genDau}}\cap\mu_1^{\mathrm{reco}}\cap\mu_2^{\mathrm{reco}})
}{
N(S_{\mathrm{genDau}})
},
]

[
\epsilon_{\mu\mathrm{ID}|J_i}
=============================

\frac{
N(S_{\mu\mathrm{Reco}}\cap\mu_1^{\mathrm{ID}}\cap\mu_2^{\mathrm{ID}})
}{
N(S_{\mu\mathrm{Reco}})
},
]

[
\epsilon_{\mu\mu|J_i}
=====================

\frac{
N(S_{\mu\mathrm{ID}}\cap J_i^{\mathrm{reco}})
}{
N(S_{\mu\mathrm{ID}})
}.
]

For the (\phi):

[
\epsilon_{K\mathrm{Reco}|\phi}
==============================

\frac{
N(S_{\mathrm{genDau}}\cap K_1^{\mathrm{reco}}\cap K_2^{\mathrm{reco}})
}{
N(S_{\mathrm{genDau}})
},
]

[
\epsilon_{K\mathrm{ID}|\phi}
============================

\frac{
N(S_{K\mathrm{Reco}}\cap K_1^{\mathrm{ID}}\cap K_2^{\mathrm{ID}})
}{
N(S_{K\mathrm{Reco}})
},
]

[
\epsilon_{KK|\phi}
==================

\frac{
N(S_{K\mathrm{ID}}\cap \phi^{\mathrm{reco}})
}{
N(S_{K\mathrm{ID}})
}.
]

Then define the event-level terms:

[
\epsilon_{\mathrm{HLT}}
=======================

\frac{
N(S_{\mathrm{cand}}\cap \mathrm{HLT})
}{
N(S_{\mathrm{cand}})
},
]

[
\epsilon_{4\mu\mathrm{vtx}}
===========================

\frac{
N(S_{\mathrm{HLT}}\cap V_{4\mu})
}{
N(S_{\mathrm{HLT}})
},
]

[
\epsilon_{\mathrm{triOnia}}^{(k)}(p_T^{J_1},p_T^{J_2})
======================================================

\frac{
N(S_{4\mu\mathrm{vtx}}\cap V_{J/\psi J/\psi\phi}\cap S_{\mathrm{other}};,p_T^\phi\in I_k)
}{
N(S_{4\mu\mathrm{vtx}};,p_T^\phi\in I_k)
}.
]

The full efficiency is

[
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
]

---

## 4. Binning strategy under limited statistics

Use this as the nominal binning strategy:

| Factor                        | Nominal map                                  | Limited-stat fallback                          |            |                 |                              |                     |
| ----------------------------- | -------------------------------------------- | ---------------------------------------------- | ---------- | --------------- | ---------------------------- | ------------------- |
| (A_{J/\psi})                  | ((p_T^{J/\psi},                              | y^{J/\psi}                                     | ))         | coarser ((p_T,  | y                            | )), then (p_T)-only |
| (A_\phi)                      | ((p_T^\phi,                                  | y^\phi                                         | ))         | (p_T^\phi)-only |                              |                     |
| (\epsilon_{\mu\mathrm{Reco}   | J/\psi})                                     | ((p_T^{J/\psi},                                | y^{J/\psi} | ))              | (p_T)-only or inclusive      |                     |
| (\epsilon_{K\mathrm{Reco}     | \phi})                                       | ((p_T^\phi,                                    | y^\phi     | ))              | (p_T^\phi)-only or inclusive |                     |
| (\epsilon_{\mu\mathrm{ID}     | J/\psi})                                     | ((p_T^{J/\psi},                                | y^{J/\psi} | ))              | (p_T)-only                   |                     |
| (\epsilon_{K\mathrm{ID}       | \phi})                                       | ((p_T^\phi,                                    | y^\phi     | ))              | (p_T^\phi)-only              |                     |
| (\epsilon_{\mu\mu             | J/\psi})                                     | ((p_T^{J/\psi},                                | y^{J/\psi} | ))              | (p_T)-only                   |                     |
| (\epsilon_{KK                 | \phi})                                       | ((p_T^\phi,                                    | y^\phi     | ))              | (p_T^\phi)-only              |                     |
| (\epsilon_{\mathrm{HLT}})     | ((p_T^{J_1},p_T^{J_2}))                      | inclusive or leading/subleading (J/\psi) (p_T) |            |                 |                              |                     |
| (\epsilon_{4\mu\mathrm{vtx}}) | ((p_T^{J_1},p_T^{J_2}))                      | inclusive                                      |            |                 |                              |                     |
| (\epsilon_{\mathrm{triOnia}}) | ((p_T^{J_1},p_T^{J_2})) in (p_T^\phi) slices | inclusive in (p_T^\phi), then fully inclusive  |            |                 |                              |                     |

For (\epsilon_{\mathrm{triOnia}}), your desired object is really

[
\epsilon_{\mathrm{triOnia}}(p_T^{J_1},p_T^{J_2},p_T^\phi).
]

With limited statistics, display it as

[
\epsilon_{\mathrm{triOnia}}^{(k)}(p_T^{J_1},p_T^{J_2}),
\qquad
p_T^\phi\in I_k,
]

but for nominal correction you may need to use either:

[
\epsilon_{\mathrm{triOnia}}(p_T^{J_1},p_T^{J_2})
]

or even

[
\epsilon_{\mathrm{triOnia}}^{\mathrm{incl}}.
]

This is acceptable if you quote the difference as a systematic.

---

## 5. Zero-bin and uncertainty treatment

Never use

[
\epsilon_b = 0
]

directly in the correction. For each bin, store:

[
N_b^{\mathrm{pass}},\qquad N_b^{\mathrm{total}},\qquad \epsilon_b,\qquad \delta\epsilon_b.
]

For the central value, use

[
\epsilon_b=\frac{N_b^{\mathrm{pass}}}{N_b^{\mathrm{total}}}
]

only when

[
N_b^{\mathrm{total}}\ge N_{\min}
\quad \text{and} \quad
N_b^{\mathrm{pass}}>0.
]

Otherwise use fallback maps.

For uncertainties, use binomial intervals. A simple robust choice is Jeffreys prior:

[
\epsilon_b
==========

\frac{N_b^{\mathrm{pass}}+1/2}
{N_b^{\mathrm{total}}+1}.
]

Use this only for uncertainty stabilization or diagnostic plots. For nominal correction, fallback-bin merging is usually easier to defend in review than heavily Bayesian-smoothed sparse maps.

---

## 6. MC sample splitting

Split MC into at least two statistically independent subsets:

[
\mathrm{MC}*{\mathrm{map}},
\qquad
\mathrm{MC}*{\mathrm{closure}}.
]

Use

[
\mathrm{MC}_{\mathrm{map}}
]

to derive maps, and

[
\mathrm{MC}_{\mathrm{closure}}
]

to test whether the maps recover the truth yield.

If statistics are very limited, use (k)-fold closure:

[
\mathrm{MC}=\bigcup_{r=1}^{k}\mathrm{MC}_r.
]

For fold (r), derive maps from all folds except (r), and test on fold (r). Combine the closure residuals.

---

## 7. Closure tests

You need at least three closure tests.

### Test 1: self-closure

For each component (c), such as SPS, DPS, or TPS-like production,

[
R_c^{\mathrm{self}}
===================

\frac{
\sum\limits_{i\in \mathrm{reco},c}
1/(A_c\epsilon_c)
}{
N_{\mathrm{gen},c}^{\mathrm{fid}}
}.
]

Require

[
R_c^{\mathrm{self}}\approx 1.
]

### Test 2: cross-closure

Apply maps from component (c_1) to component (c_2):

[
R_{c_2\leftarrow c_1}
=====================

\frac{
\sum\limits_{i\in \mathrm{reco},c_2}
1/(A_{c_1}\epsilon_{c_1})
}{
N_{\mathrm{gen},c_2}^{\mathrm{fid}}
}.
]

The spread between self-closure and cross-closure gives a model-dependence uncertainty. This follows the spirit of AN-22-160, where SPS, DPS, and mixed corrections are compared in a closure test and the discrepancy is used to assess model dependence.

### Test 3: factorization closure

Compare the direct event-level efficiency, if available,

[
\epsilon_{\mathrm{direct}}
==========================

\frac{
N(S_{\mathrm{triOnia}})
}{
N(S_{\mathrm{genDau}})
},
]

with the factorized product,

[
\epsilon_{\mathrm{fact}}
========================

\epsilon_{\mu\mathrm{Reco}}^{J_1}
\epsilon_{\mu\mathrm{Reco}}^{J_2}
\epsilon_{K\mathrm{Reco}}^{\phi}
\cdots
\epsilon_{\mathrm{triOnia}}.
]

Define

[
R_{\mathrm{fact}}
=================

\frac{
\epsilon_{\mathrm{direct}}
}{
\epsilon_{\mathrm{fact}}
}.
]

Use deviations from unity as a factorization systematic.

---

## 8. Suggested software structure

A simple Python-side implementation can be organized like this:

```text
efficiency/
  config/
    binning.yaml
    selections.yaml
    fallback_policy.yaml

  make_maps.py
  apply_maps.py
  closure.py
  plot_maps.py

  maps/
    acceptance_Jpsi.root
    acceptance_phi.root
    eff_muReco_Jpsi.root
    eff_kaonReco_phi.root
    eff_muID_Jpsi.root
    eff_kaonID_phi.root
    eff_dimuon_Jpsi.root
    eff_dikaon_phi.root
    eff_HLT.root
    eff_4muVtx.root
    eff_triOnia.root

  validation/
    closure_self.root
    closure_cross.root
    closure_factorization.root
```

Each map object should store:

```text
name
stage
level
axes
numerator histogram
denominator histogram
efficiency histogram
uncertainty histogram
fallback map name
MC sample name
selection hash or version
```

This versioning is important because small changes in matching, vertexing, or candidate choice can silently change the meaning of an efficiency.

---

## 9. Nominal event weight

For a selected data candidate (c), define

[
A_c
===

A_{J/\psi}(\vec{x}*{J_1})
A*{J/\psi}(\vec{x}*{J_2})
A*{\phi}(\vec{x}_{\phi}),
]

and

[
\begin{aligned}
\epsilon_c
={}&
\prod_{i=1}^{2}
\epsilon_{\mu\mathrm{Reco}|J_i}(\vec{x}*{J_i})
\epsilon*{\mu\mathrm{ID}|J_i}(\vec{x}*{J_i})
\epsilon*{\mu\mu|J_i}(\vec{x}*{J_i})
\
&\times
\epsilon*{K\mathrm{Reco}|\phi}(\vec{x}*{\phi})
\epsilon*{K\mathrm{ID}|\phi}(\vec{x}*{\phi})
\epsilon*{KK|\phi}(\vec{x}*{\phi})
\
&\times
\epsilon*{\mathrm{HLT}}(\vec{x}*{\mathrm{HLT}})
\epsilon*{4\mu\mathrm{vtx}}(\vec{x}*{JJ})
\epsilon*{\mathrm{triOnia}}^{(k)}(p_T^{J_1},p_T^{J_2}).
\end{aligned}
]

Then

[
w_c=\frac{1}{A_c\epsilon_c}.
]

The corrected signal yield is

[
N_{\mathrm{sig}}^{\mathrm{corr}}
================================

\sum_{c}
w_c,p_c^{\mathrm{sig}},
]

where (p_c^{\mathrm{sig}}) is either an sWeight, a fit-component probability, or effectively 1 for background-subtracted signal candidates.

---

## 10. What I would choose as nominal under limited statistics

For the first stable version, I would use:

[
A_{J/\psi}(p_T^{J/\psi}, |y^{J/\psi}|),
\qquad
A_\phi(p_T^\phi)
]

instead of a full ((p_T^\phi,|y^\phi|)) map if the (\phi) MC is sparse.

For efficiencies:

[
\epsilon_{\mu\mathrm{Reco}|J/\psi}(p_T^{J/\psi}, |y^{J/\psi}|),
]

[
\epsilon_{\mu\mathrm{ID}|J/\psi}(p_T^{J/\psi}, |y^{J/\psi}|),
]

[
\epsilon_{\mu\mu|J/\psi}(p_T^{J/\psi}, |y^{J/\psi}|),
]

but for kaon and (\phi)-related factors use

[
\epsilon_{K\mathrm{Reco}|\phi}(p_T^\phi),
\quad
\epsilon_{K\mathrm{ID}|\phi}(p_T^\phi),
\quad
\epsilon_{KK|\phi}(p_T^\phi).
]

For event-level terms, use:

[
\epsilon_{\mathrm{HLT}}(p_T^{J_1},p_T^{J_2}),
]

[
\epsilon_{4\mu\mathrm{vtx}}^{\mathrm{incl}},
]

[
\epsilon_{\mathrm{triOnia}}(p_T^{J_1},p_T^{J_2};,p_T^\phi\in I_k)
]

only if each (p_T^\phi) slice has enough entries. Otherwise use

[
\epsilon_{\mathrm{triOnia}}(p_T^{J_1},p_T^{J_2})
]

or fully inclusive (\epsilon_{\mathrm{triOnia}}^{\mathrm{incl}}), and quote the difference as a systematic.

This gives you a CMS-style correction framework that remains close to AN-22-160, but does not collapse when the (J/\psi J/\psi\phi) MC statistics are limited.

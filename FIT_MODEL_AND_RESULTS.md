# $J/\psi\,J/\psi\,\phi$ Yield Extraction — Fit Model & Results

**Run 3 (2022–2025), $\sqrt{s} = 13.6\ \mathrm{TeV}$, $\mathcal{L} = 289.2\ \mathrm{fb}^{-1}$**

---

## 1. Event selection

| Requirement | Cut |
|---|---|
| Channel | $J/\psi + J/\psi + \phi$ |
| $J/\psi$ mass window | $[2.9, 3.3]\ \mathrm{GeV}$ |
| $\phi$ mass window | $[0.99, 1.07]\ \mathrm{GeV}$ |
| $J/\psi$ $p_T$ | $> 6.0\ \mathrm{GeV}$ |
| $J/\psi$ $|y|$ | $< 2.5$ |
| $\phi$ $p_T$ | $> 4.0\ \mathrm{GeV}$ |
| $\phi$ $|\eta|$ | $< 2.5$ |
| Kaon $p_T$ | $> 2.0\ \mathrm{GeV}$ |
| Kaon $|\eta|$ | $< 2.5$ |
| Muon ID | Soft (`muIsPatSoftMuon`) |
| Muon kinematics | $p_T > 3.5\ \mathrm{GeV}$ ($|\eta| < 1.2$), $p_T > 2.5\ \mathrm{GeV}$ ($1.2 \leq |\eta| < 2.4$) |
| Best candidate | Max $\mathrm{Score}_3 = \sqrt{p_T(J/\psi_1)^2 + p_T(J/\psi_2)^2 + p_T(\phi)^2}$ |

**Data yield:** $561830$ total $\to$ $48829$ selected ($8.69\%$)

---

## 2. Fit strategy

**3D extended unbinned maximum likelihood fit** over the three invariant masses:

$$ \mathcal{L} = e^{-N} \prod_{i=1}^{N} \sum_{c} N_c \, \mathcal{P}_c\bigl(m(J/\psi_1)_i,\, m(J/\psi_2)_i,\, m(\phi)_i\bigr) $$

where the index $c$ runs over the 8 yield components. Each component PDF factorises as a product of three 1D PDFs:

$$ \mathcal{P}_c = \mathrm{PDF}_{J/\psi_1}^{(c)} \times \mathrm{PDF}_{J/\psi_2}^{(c)} \times \mathrm{PDF}_{\phi}^{(c)} $$

The fit is implemented with **RooFit** (`fit_splot.py`), using the `RooCrystalBall`, `RooVoigtian`, `RooExponential`, `RooGenericPdf`, and `RooProdPdf` classes. sWeights are extracted via `RooStats::SPlot`.

---

## 3. Signal models

### 3.1 $J/\psi \to \mu^+\mu^-$ — Double-sided Crystal Ball

$$ f(m; \mu, \sigma, \alpha_L, n_L, \alpha_R, n_R) = \begin{cases} A_L \cdot (B_L - \frac{m - \mu}{\sigma})^{-n_L}, & \frac{m - \mu}{\sigma} \leq -\alpha_L \\[4pt] \exp\!\left(-\frac{(m - \mu)^2}{2\sigma^2}\right), & -\alpha_L < \frac{m - \mu}{\sigma} < \alpha_R \\[4pt] A_R \cdot (B_R + \frac{m - \mu}{\sigma})^{-n_R}, & \frac{m - \mu}{\sigma} \geq \alpha_R \end{cases} $$

The tail parameters are **shared** between the two $J/\psi$. The mean $\mu$ and resolution $\sigma$ float independently per $J/\psi$. The powers $n_L$ and $n_R$ are fixed to $5.0$.

| Parameter | $J/\psi_1$ initial | $J/\psi_2$ initial | Range | Shared? |
|---|---|---|---|---|
| $\mu$ (mean) | $3.096$ | $3.096$ | $[3.05, 3.15]\ \mathrm{GeV}$ | No |
| $\sigma$ (sigma) | $0.025$ | $0.025$ | $[0.003, 0.08]\ \mathrm{GeV}$ | No |
| $\alpha_L$ | $1.5$ | — | $[0.1, 10.0]$ | Yes |
| $n_L$ | $5.0$ | — | fixed | Yes |
| $\alpha_R$ | $1.5$ | — | $[0.1, 10.0]$ | Yes |
| $n_R$ | $5.0$ | — | fixed | Yes |

### 3.2 $\phi \to K^+K^-$ — Voigtian (convolution of Breit–Wigner + Gaussian)

$$ V(m; \mu, \Gamma, \sigma) = \int_{-\infty}^{\infty} \frac{1}{(m - t)^2 + (\Gamma/2)^2} \cdot \exp\!\left(-\frac{(t - \mu)^2}{2\sigma^2}\right) \, dt $$

| Parameter | Value | Range |
|---|---|---|
| $\mu$ (mean) | $1.019$ | $[1.010, 1.028]\ \mathrm{GeV}$ |
| $\Gamma$ (BW width) | $0.004249\ \mathrm{GeV}$ | **fixed** (PDG $\Gamma_\phi = 4.249\ \mathrm{MeV}$) |
| $\sigma$ (Gaussian resolution) | $0.002$ | $[0.0002, 0.005]\ \mathrm{GeV}$ |

---

## 4. Background models

### 4.1 $J/\psi$ — Exponential

$$ f(m; \lambda) = e^{\lambda m} $$

| Parameter | Initial | Range |
|---|---|---|
| $\lambda$ (slope) | $-2.0$ | $[-50.0, -0.001]$ |

Each $J/\psi$ has its own independent slope parameter ($\lambda_1$, $\lambda_2$).

### 4.2 $\phi$ — Threshold power-law × exponential

$$ f(m; p, a_1) = (m - m_{\mathrm{thr}})^p \cdot \exp\bigl(a_1 (m - m_{\mathrm{thr}})\bigr) $$

with fixed threshold $m_{\mathrm{thr}} = 0.987354\ \mathrm{GeV}$ ($K^+K^-$ kinematic threshold).

| Parameter | Initial | Range |
|---|---|---|
| $p$ | $0.8$ | $[0.0, 8.0]$ |
| $a_1$ | $10.0$ | $[-200.0, 200.0]$ |

---

## 5. 8-component product model

Each component is the product of one $J/\psi_1$ PDF $\times$ one $J/\psi_2$ PDF $\times$ one $\phi$ PDF.
**S** = signal PDF, **B** = background PDF.

| # | Component | $J/\psi_1$ | $J/\psi_2$ | $\phi$ | Physical interpretation |
|---|---|---|---|---|---|
| 1 | `yield_sss` | S | S | S | **$J/\psi\,J/\psi\,\phi$ signal** |
| 2 | `yield_ssb` | S | S | B | $\phi$ sideband under $J/\psi$ peaks |
| 3 | `yield_sbs` | S | B | S | $J/\psi_2$ sideband under $J/\psi_1+\phi$ peaks |
| 4 | `yield_bss` | B | S | S | $J/\psi_1$ sideband under $J/\psi_2+\phi$ peaks |
| 5 | `yield_sbb` | S | B | B | $J/\psi_2+\phi$ sideband under $J/\psi_1$ peak |
| 6 | `yield_bsb` | B | S | B | $J/\psi_1+\phi$ sideband under $J/\psi_2$ peak |
| 7 | `yield_bbs` | B | B | S | $J/\psi_1+J/\psi_2$ sideband under $\phi$ peak |
| 8 | `yield_bbb` | B | B | B | Pure combinatorial background |

The total model:

$$ \mathcal{P}_{\mathrm{total}} = \frac{1}{N_{\mathrm{tot}}} \sum_{c=1}^{8} N_c \; \mathcal{P}_c^{\,J/\psi_1} \otimes \mathcal{P}_c^{\,J/\psi_2} \otimes \mathcal{P}_c^{\,\phi} $$

where $N_{\mathrm{tot}} = \sum_c N_c$. All 8 yield parameters float freely with initial values proportional to $[0.4, 0.1, 0.08, 0.08, 0.08, 0.08, 0.08, 0.1] \times N_{\mathrm{data}}$.

**Total floating parameters: 20** (8 yields + 12 shape parameters).

---

## 6. Fit results

**Data:** $48829$ fitted events. Fit converged with $\mathrm{NLL} = -732596$, full accurate covariance matrix (HESSE).

### 6.1 Shape parameters

| Parameter | Fit value | Uncertainty |
|---|---|---|
| $\mu(J/\psi_1)$ | $3.0933\ \mathrm{GeV}$ | $\pm 0.0002\ \mathrm{GeV}$ |
| $\mu(J/\psi_2)$ | $3.0928\ \mathrm{GeV}$ | $\pm 0.0003\ \mathrm{GeV}$ |
| $\sigma(J/\psi_1)$ | $0.02766\ \mathrm{GeV}$ | $\pm 0.00031\ \mathrm{GeV}$ |
| $\sigma(J/\psi_2)$ | $0.02760\ \mathrm{GeV}$ | $\pm 0.00033\ \mathrm{GeV}$ |
| $\alpha_L(J/\psi$, shared$)$ | $1.131$ | $\pm 0.025$ |
| $\alpha_R(J/\psi$, shared$)$ | $1.408$ | $\pm 0.032$ |
| $n_L(J/\psi$, shared$)$ | $5.0$ | **fixed** |
| $n_R(J/\psi$, shared$)$ | $5.0$ | **fixed** |
| $\mu(\phi)$ | $1.0193\ \mathrm{GeV}$ | $\pm 0.0002\ \mathrm{GeV}$ |
| $\sigma(\phi)$ | $0.00215\ \mathrm{GeV}$ | $\pm 0.00026\ \mathrm{GeV}$ |
| $\Gamma(\phi)$ | $0.004249\ \mathrm{GeV}$ | **fixed** (PDG) |
| $\lambda(J/\psi_1\ \mathrm{bkg})$ | $-1.008$ | $\pm 0.107$ |
| $\lambda(J/\psi_2\ \mathrm{bkg})$ | $-1.048$ | $\pm 0.073$ |
| $p(\phi\ \mathrm{bkg})$ | $0.440$ | $\pm 0.024$ |
| $a_1(\phi\ \mathrm{bkg})$ | $-2.869$ | $\pm 0.766$ |

### 6.2 Yield components

| Component | Fit value | Uncertainty |
|---|---|---|
| **`yield_sss` (signal)** | **$1563.5$** | **$\pm 143$** |
| `yield_ssb` | $22919$ | $\pm 323$ |
| `yield_sbs` | $801$ | $\pm 117$ |
| `yield_bss` | $422$ | $\pm 90$ |
| `yield_sbb` | $11947$ | $\pm 242$ |
| `yield_bsb` | $4163$ | $\pm 184$ |
| `yield_bbs` | $362$ | $\pm 91$ |
| `yield_bbb` | $6651$ | $\pm 190$ |

**Signal-to-background ratio:** $S/B = 1563.5 \,/\, 47265.2 = 3.31\%$

**Signal fraction:** $S/(S+B) = 1563.5 \,/\, 48828.7 = 3.20\%$

### 6.3 Yield budget summary

| Category | Yield |
|---|---|
| Signal (sss) | $1563.5$ |
| $\geq 2$ signal particles (sss + ssb + sbs + bss) | $25706$ |
| All background (non-sss) | $47265$ |
| Total | $48829$ |

---

## 7. Signal significance

The significance is evaluated with a **likelihood ratio test**:

$$ q_0 = -2 \ln \frac{\mathcal{L}(N_{sss} = 0)}{\mathcal{L}(N_{sss} = \hat{N}_{sss})} $$

The null hypothesis fixes `yield_sss` to 0 and refits. The test statistic $q_0$ follows a half-$\chi^2(1)$ distribution (Wilks' theorem), giving significance $Z = \sqrt{q_0}$.

| Quantity | Value |
|---|---|
| Best-fit NLL | $-732596$ |
| Null NLL ($sss = 0$) | $-732524$ |
| $q_0 = 2\,\Delta\mathrm{NLL}$ | **$144.2$** |
| Significance $Z = \sqrt{q_0}$ | **$12.0\sigma$** |

---

## 8. Systematic uncertainties (to be evaluated)

| Source | Expected impact |
|---|---|
| Signal shape (fixed $n_L$, $n_R$) | Free these parameters and re-fit |
| $\phi$ natural width (fixed $\Gamma_\phi$) | Float $\Gamma_\phi$ |
| Muon ID efficiency | Apply data/MC scale factors |
| Trigger efficiency | Efficiency map from the efficiency pipeline |
| Track reconstruction | MC-based correction factors |
| PV association | Vary PV quality cuts |
| Fit bias | Toy MC studies (inject known signal, measure pull) |

---

## 9. Output files

| File | Size | Content |
|---|---|---|
| `merged/jjp_data_selected.root` | $602\ \mathrm{MB}$ | Merged + selected events (`selected` tree) |
| `fit/jjp_data_weighted.root` | $475\ \mathrm{MB}$ | `selected` tree + sWeight branches (`yield_sss_sw`, `signal_sw`, …) |
| `fit/jjp_data_weighted_fit_result.root` | $19\ \mathrm{KB}$ | RooFitResult + LRT significance |
| `plots/jjp_data/fit/` | — | $3$ fit projection plots ($J/\psi_1$, $J/\psi_2$, $\phi$) |
| `plots/jjp_data/` | $221$ files | $105$ weighted 1D kinematic plots, $3$ 2D correlations, $3$ pair comparisons |

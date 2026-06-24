# Response Matrix Classification — Multi-Sample Results

**Date**: 2026-05-27
**Data**: JJP efficiency pipeline, all 5 MC samples (Condor cluster 15423609)

## Definitions

GEN and RECO both use the **best-score** candidate definition:

$$c^* = \arg\max_{c \in \mathcal{C}} \left( p_{T,J/\psi_1}^2 + p_{T,J/\psi_2}^2 + p_{T,\phi}^2 \right)$$

- **GEN-best φ**: highest-pT gen φ with ≥2 kaon daughters, from `gen_systems.parquet` (`phi_pt`)
- **RECO-best φ**: φ of the best-score candidate passing J/ψ + φ quality cuts, from `event_step_flags.parquet` (`reco_best_phi_pt`)
- **φ matching**: walk kaon `genMatchIdx` → mother chain to find gen φ ancestor; compare to GEN-best φ index

Both are binned into φ pT bins: `[4,6)`, `[6,10)`, `[10,20)`, `[20,50)` GeV.

### Event categories

| Category | Definition | Physical meaning |
|----------|-----------|-----------------|
| **Diagonal** | gen φ pT bin = reco φ pT bin | No bin migration |
| **Off-diag, φ-matched** | gen bin ≠ reco bin, reco φ traces to GEN-best φ | Same φ, detector smearing across bin boundary |
| **Off-diag, wrong φ** | gen bin ≠ reco bin, reco φ traces to a *different* gen φ | Best-score candidate picks a different gen φ |
| **Off-diag, no gen-match** | gen bin ≠ reco bin, reco φ has no gen ancestor | Combinatorial φ from fake kaon pairs |

The φ gen-matching is based on `reco_best_phi_gen_idx` from the pipeline:
- `≥0` and `== phi_gen_idx` → "φ-matched" (same φ)
- `≥0` and `!= phi_gen_idx` → "wrong φ" (different gen φ)
- `== -1` → "no gen-match" (combinatorial)

## Results

| Sample | Events | Diagonal | Same φ smeared | Wrong φ | Combinatorial |
|--------|--------|----------|----------------|---------|---------------|
| JJP_DPS1 | 121,774 | 100,657 (82.7%) | 1,240 (1.0%) | 164 (0.1%) | 19,713 (16.2%) |
| JJP_DPS2_CS | 63,251 | 52,155 (82.5%) | 518 (0.8%) | 91 (0.1%) | 10,487 (16.6%) |
| JJP_DPS2_G | 1,853 | 1,517 (81.9%) | 15 (0.8%) | 5 (0.3%) | 316 (17.1%) |
| JJP_SPS_CS | 23,626 | 16,785 (71.0%) | 143 (0.6%) | 1 (0.0%) | 6,697 (28.3%) |
| JJP_SPS_G | 1,344 | 1,102 (82.0%) | 15 (1.1%) | 2 (0.1%) | 225 (16.7%) |

"Events" = events with both `full_gen == 1` and a quality-passing RECO candidate whose gen φ pT and reco φ pT both fall within `[4, 50)` GeV.

## Key findings

1. **"Wrong φ selection" is negligible** — consistently ~0.1% across all samples. The multi-φ scenario described in `multi-phi-scheme.md` (best-score candidate picks a different gen φ) is not a significant source of bin migration.

2. **The dominant off-diagonal effect is combinatorial φ** — 16-28% of events have a best-score candidate whose φ has no gen-level ancestor. These are fake φ from random kaon pairs that happen to fall in the φ mass window and score higher than the true φ candidate.

3. **Detector smearing of the same φ** accounts for ~1% — these are events where the true φ is correctly identified but resolution effects push it across a bin boundary.

4. **DPS samples cluster at ~82% diagonal** — DPS1, DPS2_CS, and DPS2_G have consistent response matrix behavior.

5. **JJP_SPS_CS is the outlier** — only 71.0% diagonal, with 28.3% combinatorial. This likely reflects a softer φ pT spectrum in SPS_CS, producing more combinatorial kaon pairs at low pT that can fake a φ in the `[4,6)` GeV bin.

6. **Gluon-fusion samples (DPS2_G, SPS_G) have lower statistics** — ~1,300-1,800 events vs ~24k-122k for the others, reflecting their smaller cross sections. Their diagonal fractions are consistent with the higher-statistics samples.

## Implications for efficiency correction

- The response matrix is **approximately diagonal** — bin-by-bin correction is viable as a nominal approach.
- The 16-28% combinatorial off-diagonal tail means the correction factor is not purely a detector efficiency — it includes a physics component (combinatorial background rate).
- SPS_CS may need a **separate response matrix** or additional systematic uncertainty due to its different combinatorial rate.
- The ~1% same-φ smearing and ~0.1% wrong-φ rates are small enough to be treated as systematic uncertainties rather than requiring dedicated unfolding.

## Pipeline implementation

- **New columns** in `event_step_flags.parquet`: `reco_best_phi_pt`, `reco_best_phi_gen_idx`, `reco_best_phi_matches_gen`, `reco_best_is_gen_matched`, `reco_best_score`, `reco_best_jpsi1_pt`, `reco_best_jpsi2_pt`, `n_quality_candidates`
- **Script**: `build_response_classification.py` reads merged parquet files and produces per-sample `response_summary.parquet`, `response_classification.parquet`, and `response_matrix.parquet`
- Outputs at: `/eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/efficiency/merged/<sample>/response/`

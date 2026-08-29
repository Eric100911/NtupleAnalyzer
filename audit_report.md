# Efficiency event audit

- Full-GEN events inspected: 80
- Reference: current efficiency_workflow implementation
- Issues: 3

## Step membership summary

| Scope | Step | Raw pass | Cumulative D | Cumulative N | Rejected | Adjacent D | Adjacent N | Raw-only | Pipeline D/N | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| jpsi_lead | fiducial | 47 | 80 | 47 | 33 | 80 | 47 | 0 | 80/47 | matches cumulative |
| jpsi_lead | muonRECO | 51 | 47 | 42 | 5 | 47 | 42 | 9 | 47/42 | matches cumulative |
| jpsi_lead | muonID | 46 | 42 | 37 | 5 | 51 | 46 | 9 | 42/46 | NON-BINOMIAL |
| jpsi_lead | dimuon | 37 | 37 | 32 | 5 | 46 | 35 | 5 | 46/35 | matches adjacent raw |
| jpsi_sublead | fiducial | 36 | 80 | 36 | 44 | 80 | 36 | 0 | 80/36 | matches cumulative |
| jpsi_sublead | muonRECO | 38 | 36 | 31 | 5 | 36 | 31 | 7 | 36/31 | matches cumulative |
| jpsi_sublead | muonID | 33 | 31 | 26 | 5 | 38 | 33 | 7 | 31/33 | NON-BINOMIAL |
| jpsi_sublead | dimuon | 28 | 26 | 21 | 5 | 33 | 24 | 7 | 33/24 | matches adjacent raw |
| phi | fiducial | 49 | 80 | 49 | 31 | 80 | 49 | 0 | 80/49 | matches cumulative |
| phi | kaonRECO | 66 | 49 | 42 | 7 | 49 | 42 | 24 | 49/42 | matches cumulative |
| phi | kaonID | 60 | 42 | 37 | 5 | 66 | 60 | 23 | 42/60 | NON-BINOMIAL |
| phi | dikaon | 37 | 37 | 27 | 10 | 60 | 37 | 10 | 60/37 | matches adjacent raw |
| event | s_cand | 13 | 80 | 13 | 67 | 80 | 13 | 0 | — | differs |
| event | hlt_event | 8 | 13 | 8 | 5 | 13 | 8 | 0 | 13/8 | matches cumulative |
| event | hlt_muon_matched | 7 | 8 | 7 | 1 | 8 | 7 | 0 | 8/7 | matches cumulative |
| event | four_muon_vtx | 5 | 7 | 5 | 2 | 7 | 5 | 0 | 7/5 | matches cumulative |
| event | Pri_fitValid | 5 | 5 | 5 | 0 | 5 | 5 | 0 | 5/5 | matches cumulative |
| event | Pri_fitPass | 5 | 5 | 5 | 0 | 5 | 5 | 0 | 5/5 | matches cumulative |
| event | Pri_assocPVPass | 5 | 5 | 5 | 0 | 5 | 5 | 0 | 5/5 | matches cumulative |
| event | Pri_trackPVPass | 5 | 5 | 5 | 0 | 5 | 5 | 0 | 5/5 | matches cumulative |

## Factor numerator/denominator summary

| Factor | Numerator | Denominator | Passed/total | Efficiency |
|---|---|---|---:|---:|
| acceptance_jpsi_lead | jpsi_lead_fiducial | full_gen | 47/80 | 0.587500 |
| eff_muReco_jpsi_lead | jpsi_lead_muonRECO | jpsi_lead_fiducial | 42/47 | 0.893617 |
| eff_muID_jpsi_lead | jpsi_lead_muonID | jpsi_lead_muonRECO | 46/51 | 0.901961 |
| eff_dimuon_jpsi_lead | jpsi_lead_dimuon | jpsi_lead_muonID | 35/46 | 0.760870 |
| acceptance_jpsi_sublead | jpsi_sublead_fiducial | full_gen | 36/80 | 0.450000 |
| eff_muReco_jpsi_sublead | jpsi_sublead_muonRECO | jpsi_sublead_fiducial | 31/36 | 0.861111 |
| eff_muID_jpsi_sublead | jpsi_sublead_muonID | jpsi_sublead_muonRECO | 33/38 | 0.868421 |
| eff_dimuon_jpsi_sublead | jpsi_sublead_dimuon | jpsi_sublead_muonID | 24/33 | 0.727273 |
| acceptance_phi | phi_fiducial | full_gen | 49/80 | 0.612500 |
| eff_kaonReco_phi | phi_kaonRECO | phi_fiducial | 42/49 | 0.857143 |
| eff_kaonID_phi | phi_kaonID | phi_kaonRECO | 60/66 | 0.909091 |
| eff_dikaon_phi | phi_dikaon | phi_kaonID | 37/60 | 0.616667 |
| eff_hlt | hlt_muon_matched | s_cand | 7/13 | 0.538462 |
| eff_4mu_vtx | four_muon_vtx | hlt_muon_matched | 5/7 | 0.714286 |
| eff_Pri_fitValid | Pri_fitValid | four_muon_vtx | 5/5 | 1.000000 |
| eff_Pri_fitPass | Pri_fitPass | four_muon_vtx | 5/5 | 1.000000 |
| eff_Pri_assocPVPass | Pri_assocPVPass | four_muon_vtx | 5/5 | 1.000000 |
| eff_Pri_trackPVPass | Pri_trackPVPass | four_muon_vtx | 5/5 | 1.000000 |

## No-trigger-matching diagnostic summary

| Step | Denominator | Passed/total | Efficiency |
|---|---|---:|---:|
| four_muon_vtx_noTrigMatch | hlt_event | 6/8 | 0.750000 |
| Pri_fitValid_noTrigMatch | four_muon_vtx_noTrigMatch | 6/6 | 1.000000 |
| Pri_fitPass_noTrigMatch | four_muon_vtx_noTrigMatch | 6/6 | 1.000000 |
| Pri_assocPVPass_noTrigMatch | four_muon_vtx_noTrigMatch | 6/6 | 1.000000 |
| Pri_trackPVPass_noTrigMatch | four_muon_vtx_noTrigMatch | 6/6 | 1.000000 |

## Coverage gaps

- `jpsi_lead/fiducial/raw_only`: no example found
- `jpsi_sublead/fiducial/raw_only`: no example found
- `phi/fiducial/raw_only`: no example found
- `event/s_cand/raw_only`: no example found
- `event/hlt_event/raw_only`: no example found
- `event/hlt_muon_matched/raw_only`: no example found
- `event/four_muon_vtx/raw_only`: no example found
- `event/Pri_fitValid/rejected`: no example found
- `event/Pri_fitValid/raw_only`: no example found
- `event/Pri_fitPass/rejected`: no example found
- `event/Pri_fitPass/raw_only`: no example found
- `event/Pri_assocPVPass/rejected`: no example found
- `event/Pri_assocPVPass/raw_only`: no example found
- `event/Pri_trackPVPass/rejected`: no example found
- `event/Pri_trackPVPass/raw_only`: no example found

## Selected examples by step and role

Each table compares events selected for one step and one membership role. Only the current step and its upstream evidence are shown; the complete machine-readable evidence remains in `audit_report.json`.

### `event / Pri_assocPVPass / numerator`

| Field | Event 1<br>`entry 22` | Event 2<br>`entry 35` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 22 | 35 |
| `identity.run:lumi:event` | 1:1:304 | 1:1:702 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.s_cand` | PASS | PASS |
| `flags.hlt_event` | PASS | PASS |
| `flags.hlt_muon_matched` | PASS | PASS |
| `flags.four_muon_vtx` | PASS | PASS |
| `flags.Pri_fitValid` | PASS | PASS |
| `flags.Pri_fitPass` | PASS | PASS |
| `flags.Pri_assocPVPass` | PASS | PASS |
| `trigger.path_fired` | PASS | PASS |
| `trigger.paths[0].name` | HLT_DoubleMu4_3_LowMass_v1 | HLT_DoubleMu4_3_LowMass_v1 |
| `trigger.paths[0].result` | PASS | PASS |
| `trigger.paths[1].name` | HLT_Dimuon0_Jpsi3p5_Muon2_v5 | HLT_Dimuon0_Jpsi3p5_Muon2_v5 |
| `trigger.paths[1].result` | FAIL | PASS |
| `trigger.index_map.dimuon0_trig` | 0 | 0 |
| `trigger.index_map.doublemu_trig` | 1 | 1 |
| `trigger.index_map.dimuon0_filt` | 0 | 0 |
| `trigger.index_map.doublemu_filt` | 1 | 1 |
| `composite_candidates[0].candidate_idx` | 0 | 0 |
| `composite_candidates[0].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[0].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[0].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[0].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[0].phi_gen_idx` | -1 | -1 |
| `composite_candidates[0].triple_gen_matched` | FAIL | FAIL |
| `composite_candidates[0].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.passed` | PASS | PASS |
| `composite_candidates[0].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[0].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[0].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[0].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[0].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_assocPVPass` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[0].stages.candidate_base` | FAIL | FAIL |
| `composite_candidates[0].stages.hlt_muon_matched` | FAIL | FAIL |
| `composite_candidates[0].stages.four_muon_vtx` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitValid` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_trackPVPass` | FAIL | FAIL |
| `composite_candidates[1].candidate_idx` | 1 | 1 |
| `composite_candidates[1].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[1].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[1].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[1].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[1].phi_gen_idx` | 7 | -1 |
| `composite_candidates[1].triple_gen_matched` | PASS | FAIL |
| `composite_candidates[1].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.passed` | PASS | PASS |
| `composite_candidates[1].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[1].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[1].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[1].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[1].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_assocPVPass` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[1].stages.candidate_base` | PASS | FAIL |
| `composite_candidates[1].stages.hlt_muon_matched` | PASS | FAIL |
| `composite_candidates[1].stages.four_muon_vtx` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_fitValid` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_fitPass` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_assocPVPass` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_trackPVPass` | PASS | FAIL |
| `composite_candidates[2].candidate_idx` | 2 | 2 |
| `composite_candidates[2].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[2].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[2].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[2].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[2].phi_gen_idx` | -1 | -1 |
| `composite_candidates[2].triple_gen_matched` | FAIL | FAIL |
| `composite_candidates[2].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.passed` | PASS | PASS |
| `composite_candidates[2].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[2].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[2].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[2].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[2].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[2].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[2].Pri.Pri_assocPVPass` | FAIL | PASS |
| `composite_candidates[2].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[2].stages.candidate_base` | FAIL | FAIL |
| `composite_candidates[2].stages.hlt_muon_matched` | FAIL | FAIL |
| `composite_candidates[2].stages.four_muon_vtx` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_fitValid` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_fitPass` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_trackPVPass` | FAIL | FAIL |
| `composite_candidates[3].candidate_idx` | — | 3 |
| `composite_candidates[3].muon_indices` | — | 0, 2, 1, 3 |
| `composite_candidates[3].muon_jpsi_ancestors` | — | 8, 8, 23, 23 |
| `composite_candidates[3].jpsi_1_gen_idx` | — | 8 |
| `composite_candidates[3].jpsi_2_gen_idx` | — | 23 |
| `composite_candidates[3].phi_gen_idx` | — | 14 |
| `composite_candidates[3].triple_gen_matched` | — | PASS |
| `composite_candidates[3].trigger_match.dimuon0_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[3].trigger_match.doublemu_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[3].trigger_match.passed` | — | PASS |
| `composite_candidates[3].muVertexId` | — | 0, 0, 0, 0 |
| `composite_candidates[3].four_muon_current_predicate` | — | PASS |
| `composite_candidates[3].DiOnia_context.DiOnia_Chi2` | — | 0.83159 |
| `composite_candidates[3].DiOnia_context.DiOnia_VtxProb` | — | 0.36181 |
| `composite_candidates[3].DiOnia_context.DiOnia_commonRecVtxIdx` | — | 0 |
| `composite_candidates[3].DiOnia_context.DiOnia_commonRecVtxPass` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_fitPass` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_fitValid` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_ndof` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_passAny` | — | 1 |
| `composite_candidates[3].Pri.Pri_fitValid` | — | PASS |
| `composite_candidates[3].Pri.Pri_fitPass` | — | PASS |
| `composite_candidates[3].Pri.Pri_assocPVPass` | — | PASS |
| `composite_candidates[3].Pri.Pri_trackPVPass` | — | PASS |
| `composite_candidates[3].stages.candidate_base` | — | PASS |
| `composite_candidates[3].stages.hlt_muon_matched` | — | PASS |
| `composite_candidates[3].stages.four_muon_vtx` | — | PASS |
| `composite_candidates[3].stages.Pri_fitValid` | — | PASS |
| `composite_candidates[3].stages.Pri_fitPass` | — | PASS |
| `composite_candidates[3].stages.Pri_assocPVPass` | — | PASS |
| `composite_candidates[3].stages.Pri_trackPVPass` | — | PASS |

### `event / Pri_fitPass / numerator`

| Field | Event 1<br>`entry 22` | Event 2<br>`entry 35` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 22 | 35 |
| `identity.run:lumi:event` | 1:1:304 | 1:1:702 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.s_cand` | PASS | PASS |
| `flags.hlt_event` | PASS | PASS |
| `flags.hlt_muon_matched` | PASS | PASS |
| `flags.four_muon_vtx` | PASS | PASS |
| `flags.Pri_fitValid` | PASS | PASS |
| `flags.Pri_fitPass` | PASS | PASS |
| `trigger.path_fired` | PASS | PASS |
| `trigger.paths[0].name` | HLT_DoubleMu4_3_LowMass_v1 | HLT_DoubleMu4_3_LowMass_v1 |
| `trigger.paths[0].result` | PASS | PASS |
| `trigger.paths[1].name` | HLT_Dimuon0_Jpsi3p5_Muon2_v5 | HLT_Dimuon0_Jpsi3p5_Muon2_v5 |
| `trigger.paths[1].result` | FAIL | PASS |
| `trigger.index_map.dimuon0_trig` | 0 | 0 |
| `trigger.index_map.doublemu_trig` | 1 | 1 |
| `trigger.index_map.dimuon0_filt` | 0 | 0 |
| `trigger.index_map.doublemu_filt` | 1 | 1 |
| `composite_candidates[0].candidate_idx` | 0 | 0 |
| `composite_candidates[0].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[0].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[0].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[0].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[0].phi_gen_idx` | -1 | -1 |
| `composite_candidates[0].triple_gen_matched` | FAIL | FAIL |
| `composite_candidates[0].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.passed` | PASS | PASS |
| `composite_candidates[0].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[0].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[0].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[0].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[0].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_assocPVPass` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[0].stages.candidate_base` | FAIL | FAIL |
| `composite_candidates[0].stages.hlt_muon_matched` | FAIL | FAIL |
| `composite_candidates[0].stages.four_muon_vtx` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitValid` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_trackPVPass` | FAIL | FAIL |
| `composite_candidates[1].candidate_idx` | 1 | 1 |
| `composite_candidates[1].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[1].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[1].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[1].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[1].phi_gen_idx` | 7 | -1 |
| `composite_candidates[1].triple_gen_matched` | PASS | FAIL |
| `composite_candidates[1].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.passed` | PASS | PASS |
| `composite_candidates[1].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[1].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[1].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[1].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[1].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_assocPVPass` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[1].stages.candidate_base` | PASS | FAIL |
| `composite_candidates[1].stages.hlt_muon_matched` | PASS | FAIL |
| `composite_candidates[1].stages.four_muon_vtx` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_fitValid` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_fitPass` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_assocPVPass` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_trackPVPass` | PASS | FAIL |
| `composite_candidates[2].candidate_idx` | 2 | 2 |
| `composite_candidates[2].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[2].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[2].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[2].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[2].phi_gen_idx` | -1 | -1 |
| `composite_candidates[2].triple_gen_matched` | FAIL | FAIL |
| `composite_candidates[2].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.passed` | PASS | PASS |
| `composite_candidates[2].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[2].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[2].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[2].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[2].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[2].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[2].Pri.Pri_assocPVPass` | FAIL | PASS |
| `composite_candidates[2].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[2].stages.candidate_base` | FAIL | FAIL |
| `composite_candidates[2].stages.hlt_muon_matched` | FAIL | FAIL |
| `composite_candidates[2].stages.four_muon_vtx` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_fitValid` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_fitPass` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_trackPVPass` | FAIL | FAIL |
| `composite_candidates[3].candidate_idx` | — | 3 |
| `composite_candidates[3].muon_indices` | — | 0, 2, 1, 3 |
| `composite_candidates[3].muon_jpsi_ancestors` | — | 8, 8, 23, 23 |
| `composite_candidates[3].jpsi_1_gen_idx` | — | 8 |
| `composite_candidates[3].jpsi_2_gen_idx` | — | 23 |
| `composite_candidates[3].phi_gen_idx` | — | 14 |
| `composite_candidates[3].triple_gen_matched` | — | PASS |
| `composite_candidates[3].trigger_match.dimuon0_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[3].trigger_match.doublemu_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[3].trigger_match.passed` | — | PASS |
| `composite_candidates[3].muVertexId` | — | 0, 0, 0, 0 |
| `composite_candidates[3].four_muon_current_predicate` | — | PASS |
| `composite_candidates[3].DiOnia_context.DiOnia_Chi2` | — | 0.83159 |
| `composite_candidates[3].DiOnia_context.DiOnia_VtxProb` | — | 0.36181 |
| `composite_candidates[3].DiOnia_context.DiOnia_commonRecVtxIdx` | — | 0 |
| `composite_candidates[3].DiOnia_context.DiOnia_commonRecVtxPass` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_fitPass` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_fitValid` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_ndof` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_passAny` | — | 1 |
| `composite_candidates[3].Pri.Pri_fitValid` | — | PASS |
| `composite_candidates[3].Pri.Pri_fitPass` | — | PASS |
| `composite_candidates[3].Pri.Pri_assocPVPass` | — | PASS |
| `composite_candidates[3].Pri.Pri_trackPVPass` | — | PASS |
| `composite_candidates[3].stages.candidate_base` | — | PASS |
| `composite_candidates[3].stages.hlt_muon_matched` | — | PASS |
| `composite_candidates[3].stages.four_muon_vtx` | — | PASS |
| `composite_candidates[3].stages.Pri_fitValid` | — | PASS |
| `composite_candidates[3].stages.Pri_fitPass` | — | PASS |
| `composite_candidates[3].stages.Pri_assocPVPass` | — | PASS |
| `composite_candidates[3].stages.Pri_trackPVPass` | — | PASS |

### `event / Pri_fitValid / numerator`

| Field | Event 1<br>`entry 22` | Event 2<br>`entry 35` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 22 | 35 |
| `identity.run:lumi:event` | 1:1:304 | 1:1:702 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.s_cand` | PASS | PASS |
| `flags.hlt_event` | PASS | PASS |
| `flags.hlt_muon_matched` | PASS | PASS |
| `flags.four_muon_vtx` | PASS | PASS |
| `flags.Pri_fitValid` | PASS | PASS |
| `trigger.path_fired` | PASS | PASS |
| `trigger.paths[0].name` | HLT_DoubleMu4_3_LowMass_v1 | HLT_DoubleMu4_3_LowMass_v1 |
| `trigger.paths[0].result` | PASS | PASS |
| `trigger.paths[1].name` | HLT_Dimuon0_Jpsi3p5_Muon2_v5 | HLT_Dimuon0_Jpsi3p5_Muon2_v5 |
| `trigger.paths[1].result` | FAIL | PASS |
| `trigger.index_map.dimuon0_trig` | 0 | 0 |
| `trigger.index_map.doublemu_trig` | 1 | 1 |
| `trigger.index_map.dimuon0_filt` | 0 | 0 |
| `trigger.index_map.doublemu_filt` | 1 | 1 |
| `composite_candidates[0].candidate_idx` | 0 | 0 |
| `composite_candidates[0].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[0].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[0].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[0].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[0].phi_gen_idx` | -1 | -1 |
| `composite_candidates[0].triple_gen_matched` | FAIL | FAIL |
| `composite_candidates[0].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.passed` | PASS | PASS |
| `composite_candidates[0].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[0].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[0].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[0].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[0].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_assocPVPass` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[0].stages.candidate_base` | FAIL | FAIL |
| `composite_candidates[0].stages.hlt_muon_matched` | FAIL | FAIL |
| `composite_candidates[0].stages.four_muon_vtx` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitValid` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_trackPVPass` | FAIL | FAIL |
| `composite_candidates[1].candidate_idx` | 1 | 1 |
| `composite_candidates[1].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[1].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[1].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[1].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[1].phi_gen_idx` | 7 | -1 |
| `composite_candidates[1].triple_gen_matched` | PASS | FAIL |
| `composite_candidates[1].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.passed` | PASS | PASS |
| `composite_candidates[1].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[1].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[1].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[1].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[1].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_assocPVPass` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[1].stages.candidate_base` | PASS | FAIL |
| `composite_candidates[1].stages.hlt_muon_matched` | PASS | FAIL |
| `composite_candidates[1].stages.four_muon_vtx` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_fitValid` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_fitPass` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_assocPVPass` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_trackPVPass` | PASS | FAIL |
| `composite_candidates[2].candidate_idx` | 2 | 2 |
| `composite_candidates[2].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[2].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[2].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[2].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[2].phi_gen_idx` | -1 | -1 |
| `composite_candidates[2].triple_gen_matched` | FAIL | FAIL |
| `composite_candidates[2].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.passed` | PASS | PASS |
| `composite_candidates[2].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[2].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[2].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[2].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[2].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[2].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[2].Pri.Pri_assocPVPass` | FAIL | PASS |
| `composite_candidates[2].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[2].stages.candidate_base` | FAIL | FAIL |
| `composite_candidates[2].stages.hlt_muon_matched` | FAIL | FAIL |
| `composite_candidates[2].stages.four_muon_vtx` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_fitValid` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_fitPass` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_trackPVPass` | FAIL | FAIL |
| `composite_candidates[3].candidate_idx` | — | 3 |
| `composite_candidates[3].muon_indices` | — | 0, 2, 1, 3 |
| `composite_candidates[3].muon_jpsi_ancestors` | — | 8, 8, 23, 23 |
| `composite_candidates[3].jpsi_1_gen_idx` | — | 8 |
| `composite_candidates[3].jpsi_2_gen_idx` | — | 23 |
| `composite_candidates[3].phi_gen_idx` | — | 14 |
| `composite_candidates[3].triple_gen_matched` | — | PASS |
| `composite_candidates[3].trigger_match.dimuon0_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[3].trigger_match.doublemu_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[3].trigger_match.passed` | — | PASS |
| `composite_candidates[3].muVertexId` | — | 0, 0, 0, 0 |
| `composite_candidates[3].four_muon_current_predicate` | — | PASS |
| `composite_candidates[3].DiOnia_context.DiOnia_Chi2` | — | 0.83159 |
| `composite_candidates[3].DiOnia_context.DiOnia_VtxProb` | — | 0.36181 |
| `composite_candidates[3].DiOnia_context.DiOnia_commonRecVtxIdx` | — | 0 |
| `composite_candidates[3].DiOnia_context.DiOnia_commonRecVtxPass` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_fitPass` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_fitValid` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_ndof` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_passAny` | — | 1 |
| `composite_candidates[3].Pri.Pri_fitValid` | — | PASS |
| `composite_candidates[3].Pri.Pri_fitPass` | — | PASS |
| `composite_candidates[3].Pri.Pri_assocPVPass` | — | PASS |
| `composite_candidates[3].Pri.Pri_trackPVPass` | — | PASS |
| `composite_candidates[3].stages.candidate_base` | — | PASS |
| `composite_candidates[3].stages.hlt_muon_matched` | — | PASS |
| `composite_candidates[3].stages.four_muon_vtx` | — | PASS |
| `composite_candidates[3].stages.Pri_fitValid` | — | PASS |
| `composite_candidates[3].stages.Pri_fitPass` | — | PASS |
| `composite_candidates[3].stages.Pri_assocPVPass` | — | PASS |
| `composite_candidates[3].stages.Pri_trackPVPass` | — | PASS |

### `event / Pri_trackPVPass / numerator`

| Field | Event 1<br>`entry 22` | Event 2<br>`entry 35` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 22 | 35 |
| `identity.run:lumi:event` | 1:1:304 | 1:1:702 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.s_cand` | PASS | PASS |
| `flags.hlt_event` | PASS | PASS |
| `flags.hlt_muon_matched` | PASS | PASS |
| `flags.four_muon_vtx` | PASS | PASS |
| `flags.Pri_fitValid` | PASS | PASS |
| `flags.Pri_fitPass` | PASS | PASS |
| `flags.Pri_assocPVPass` | PASS | PASS |
| `flags.Pri_trackPVPass` | PASS | PASS |
| `trigger.path_fired` | PASS | PASS |
| `trigger.paths[0].name` | HLT_DoubleMu4_3_LowMass_v1 | HLT_DoubleMu4_3_LowMass_v1 |
| `trigger.paths[0].result` | PASS | PASS |
| `trigger.paths[1].name` | HLT_Dimuon0_Jpsi3p5_Muon2_v5 | HLT_Dimuon0_Jpsi3p5_Muon2_v5 |
| `trigger.paths[1].result` | FAIL | PASS |
| `trigger.index_map.dimuon0_trig` | 0 | 0 |
| `trigger.index_map.doublemu_trig` | 1 | 1 |
| `trigger.index_map.dimuon0_filt` | 0 | 0 |
| `trigger.index_map.doublemu_filt` | 1 | 1 |
| `composite_candidates[0].candidate_idx` | 0 | 0 |
| `composite_candidates[0].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[0].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[0].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[0].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[0].phi_gen_idx` | -1 | -1 |
| `composite_candidates[0].triple_gen_matched` | FAIL | FAIL |
| `composite_candidates[0].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.passed` | PASS | PASS |
| `composite_candidates[0].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[0].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[0].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[0].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[0].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_assocPVPass` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[0].stages.candidate_base` | FAIL | FAIL |
| `composite_candidates[0].stages.hlt_muon_matched` | FAIL | FAIL |
| `composite_candidates[0].stages.four_muon_vtx` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitValid` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_trackPVPass` | FAIL | FAIL |
| `composite_candidates[1].candidate_idx` | 1 | 1 |
| `composite_candidates[1].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[1].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[1].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[1].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[1].phi_gen_idx` | 7 | -1 |
| `composite_candidates[1].triple_gen_matched` | PASS | FAIL |
| `composite_candidates[1].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.passed` | PASS | PASS |
| `composite_candidates[1].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[1].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[1].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[1].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[1].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_assocPVPass` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[1].stages.candidate_base` | PASS | FAIL |
| `composite_candidates[1].stages.hlt_muon_matched` | PASS | FAIL |
| `composite_candidates[1].stages.four_muon_vtx` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_fitValid` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_fitPass` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_assocPVPass` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_trackPVPass` | PASS | FAIL |
| `composite_candidates[2].candidate_idx` | 2 | 2 |
| `composite_candidates[2].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[2].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[2].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[2].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[2].phi_gen_idx` | -1 | -1 |
| `composite_candidates[2].triple_gen_matched` | FAIL | FAIL |
| `composite_candidates[2].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.passed` | PASS | PASS |
| `composite_candidates[2].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[2].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[2].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[2].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[2].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[2].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[2].Pri.Pri_assocPVPass` | FAIL | PASS |
| `composite_candidates[2].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[2].stages.candidate_base` | FAIL | FAIL |
| `composite_candidates[2].stages.hlt_muon_matched` | FAIL | FAIL |
| `composite_candidates[2].stages.four_muon_vtx` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_fitValid` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_fitPass` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_trackPVPass` | FAIL | FAIL |
| `composite_candidates[3].candidate_idx` | — | 3 |
| `composite_candidates[3].muon_indices` | — | 0, 2, 1, 3 |
| `composite_candidates[3].muon_jpsi_ancestors` | — | 8, 8, 23, 23 |
| `composite_candidates[3].jpsi_1_gen_idx` | — | 8 |
| `composite_candidates[3].jpsi_2_gen_idx` | — | 23 |
| `composite_candidates[3].phi_gen_idx` | — | 14 |
| `composite_candidates[3].triple_gen_matched` | — | PASS |
| `composite_candidates[3].trigger_match.dimuon0_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[3].trigger_match.doublemu_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[3].trigger_match.passed` | — | PASS |
| `composite_candidates[3].muVertexId` | — | 0, 0, 0, 0 |
| `composite_candidates[3].four_muon_current_predicate` | — | PASS |
| `composite_candidates[3].DiOnia_context.DiOnia_Chi2` | — | 0.83159 |
| `composite_candidates[3].DiOnia_context.DiOnia_VtxProb` | — | 0.36181 |
| `composite_candidates[3].DiOnia_context.DiOnia_commonRecVtxIdx` | — | 0 |
| `composite_candidates[3].DiOnia_context.DiOnia_commonRecVtxPass` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_fitPass` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_fitValid` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_ndof` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_passAny` | — | 1 |
| `composite_candidates[3].Pri.Pri_fitValid` | — | PASS |
| `composite_candidates[3].Pri.Pri_fitPass` | — | PASS |
| `composite_candidates[3].Pri.Pri_assocPVPass` | — | PASS |
| `composite_candidates[3].Pri.Pri_trackPVPass` | — | PASS |
| `composite_candidates[3].stages.candidate_base` | — | PASS |
| `composite_candidates[3].stages.hlt_muon_matched` | — | PASS |
| `composite_candidates[3].stages.four_muon_vtx` | — | PASS |
| `composite_candidates[3].stages.Pri_fitValid` | — | PASS |
| `composite_candidates[3].stages.Pri_fitPass` | — | PASS |
| `composite_candidates[3].stages.Pri_assocPVPass` | — | PASS |
| `composite_candidates[3].stages.Pri_trackPVPass` | — | PASS |

### `event / four_muon_vtx / numerator`

| Field | Event 1<br>`entry 22` | Event 2<br>`entry 35` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 22 | 35 |
| `identity.run:lumi:event` | 1:1:304 | 1:1:702 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.s_cand` | PASS | PASS |
| `flags.hlt_event` | PASS | PASS |
| `flags.hlt_muon_matched` | PASS | PASS |
| `flags.four_muon_vtx` | PASS | PASS |
| `trigger.path_fired` | PASS | PASS |
| `trigger.paths[0].name` | HLT_DoubleMu4_3_LowMass_v1 | HLT_DoubleMu4_3_LowMass_v1 |
| `trigger.paths[0].result` | PASS | PASS |
| `trigger.paths[1].name` | HLT_Dimuon0_Jpsi3p5_Muon2_v5 | HLT_Dimuon0_Jpsi3p5_Muon2_v5 |
| `trigger.paths[1].result` | FAIL | PASS |
| `trigger.index_map.dimuon0_trig` | 0 | 0 |
| `trigger.index_map.doublemu_trig` | 1 | 1 |
| `trigger.index_map.dimuon0_filt` | 0 | 0 |
| `trigger.index_map.doublemu_filt` | 1 | 1 |
| `composite_candidates[0].candidate_idx` | 0 | 0 |
| `composite_candidates[0].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[0].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[0].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[0].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[0].phi_gen_idx` | -1 | -1 |
| `composite_candidates[0].triple_gen_matched` | FAIL | FAIL |
| `composite_candidates[0].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.passed` | PASS | PASS |
| `composite_candidates[0].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[0].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[0].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[0].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[0].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_assocPVPass` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[0].stages.candidate_base` | FAIL | FAIL |
| `composite_candidates[0].stages.hlt_muon_matched` | FAIL | FAIL |
| `composite_candidates[0].stages.four_muon_vtx` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitValid` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_trackPVPass` | FAIL | FAIL |
| `composite_candidates[1].candidate_idx` | 1 | 1 |
| `composite_candidates[1].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[1].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[1].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[1].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[1].phi_gen_idx` | 7 | -1 |
| `composite_candidates[1].triple_gen_matched` | PASS | FAIL |
| `composite_candidates[1].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.passed` | PASS | PASS |
| `composite_candidates[1].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[1].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[1].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[1].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[1].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_assocPVPass` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[1].stages.candidate_base` | PASS | FAIL |
| `composite_candidates[1].stages.hlt_muon_matched` | PASS | FAIL |
| `composite_candidates[1].stages.four_muon_vtx` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_fitValid` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_fitPass` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_assocPVPass` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_trackPVPass` | PASS | FAIL |
| `composite_candidates[2].candidate_idx` | 2 | 2 |
| `composite_candidates[2].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[2].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[2].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[2].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[2].phi_gen_idx` | -1 | -1 |
| `composite_candidates[2].triple_gen_matched` | FAIL | FAIL |
| `composite_candidates[2].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.passed` | PASS | PASS |
| `composite_candidates[2].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[2].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[2].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[2].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[2].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[2].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[2].Pri.Pri_assocPVPass` | FAIL | PASS |
| `composite_candidates[2].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[2].stages.candidate_base` | FAIL | FAIL |
| `composite_candidates[2].stages.hlt_muon_matched` | FAIL | FAIL |
| `composite_candidates[2].stages.four_muon_vtx` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_fitValid` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_fitPass` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_trackPVPass` | FAIL | FAIL |
| `composite_candidates[3].candidate_idx` | — | 3 |
| `composite_candidates[3].muon_indices` | — | 0, 2, 1, 3 |
| `composite_candidates[3].muon_jpsi_ancestors` | — | 8, 8, 23, 23 |
| `composite_candidates[3].jpsi_1_gen_idx` | — | 8 |
| `composite_candidates[3].jpsi_2_gen_idx` | — | 23 |
| `composite_candidates[3].phi_gen_idx` | — | 14 |
| `composite_candidates[3].triple_gen_matched` | — | PASS |
| `composite_candidates[3].trigger_match.dimuon0_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[3].trigger_match.doublemu_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[3].trigger_match.passed` | — | PASS |
| `composite_candidates[3].muVertexId` | — | 0, 0, 0, 0 |
| `composite_candidates[3].four_muon_current_predicate` | — | PASS |
| `composite_candidates[3].DiOnia_context.DiOnia_Chi2` | — | 0.83159 |
| `composite_candidates[3].DiOnia_context.DiOnia_VtxProb` | — | 0.36181 |
| `composite_candidates[3].DiOnia_context.DiOnia_commonRecVtxIdx` | — | 0 |
| `composite_candidates[3].DiOnia_context.DiOnia_commonRecVtxPass` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_fitPass` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_fitValid` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_ndof` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_passAny` | — | 1 |
| `composite_candidates[3].Pri.Pri_fitValid` | — | PASS |
| `composite_candidates[3].Pri.Pri_fitPass` | — | PASS |
| `composite_candidates[3].Pri.Pri_assocPVPass` | — | PASS |
| `composite_candidates[3].Pri.Pri_trackPVPass` | — | PASS |
| `composite_candidates[3].stages.candidate_base` | — | PASS |
| `composite_candidates[3].stages.hlt_muon_matched` | — | PASS |
| `composite_candidates[3].stages.four_muon_vtx` | — | PASS |
| `composite_candidates[3].stages.Pri_fitValid` | — | PASS |
| `composite_candidates[3].stages.Pri_fitPass` | — | PASS |
| `composite_candidates[3].stages.Pri_assocPVPass` | — | PASS |
| `composite_candidates[3].stages.Pri_trackPVPass` | — | PASS |

### `event / four_muon_vtx / rejected`

| Field | Event 1<br>`entry 33` | Event 2<br>`entry 34` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source1_35events.root | jjp_dps_patch2_pre2_runb_audit_source1_35events.root |
| `identity.entry` | 33 | 34 |
| `identity.run:lumi:event` | 1:1:25342 | 1:1:28095 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.s_cand` | PASS | PASS |
| `flags.hlt_event` | PASS | PASS |
| `flags.hlt_muon_matched` | PASS | PASS |
| `flags.four_muon_vtx` | FAIL | FAIL |
| `trigger.path_fired` | PASS | PASS |
| `trigger.paths[0].name` | HLT_DoubleMu4_3_LowMass_v1 | HLT_DoubleMu4_3_LowMass_v1 |
| `trigger.paths[0].result` | PASS | PASS |
| `trigger.paths[1].name` | HLT_Dimuon0_Jpsi3p5_Muon2_v5 | HLT_Dimuon0_Jpsi3p5_Muon2_v5 |
| `trigger.paths[1].result` | PASS | PASS |
| `trigger.index_map.dimuon0_trig` | 0 | 0 |
| `trigger.index_map.doublemu_trig` | 1 | 1 |
| `trigger.index_map.dimuon0_filt` | 0 | 0 |
| `trigger.index_map.doublemu_filt` | 1 | 1 |
| `composite_candidates[0].candidate_idx` | 0 | 0 |
| `composite_candidates[0].muon_indices` | 0, 1, 2, 3 | 0, 4, 1, 2 |
| `composite_candidates[0].muon_jpsi_ancestors` | 5, 5, 0, 0 | 3, 3, 0, 0 |
| `composite_candidates[0].jpsi_1_gen_idx` | 5 | 3 |
| `composite_candidates[0].jpsi_2_gen_idx` | 0 | 0 |
| `composite_candidates[0].phi_gen_idx` | 4 | -1 |
| `composite_candidates[0].triple_gen_matched` | PASS | FAIL |
| `composite_candidates[0].trigger_match.dimuon0_muons` | PASS, PASS, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.doublemu_muons` | PASS, PASS, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.passed` | PASS | PASS |
| `composite_candidates[0].muVertexId` | 0, 0, 0, 1 | 0, 0, 4, 0 |
| `composite_candidates[0].four_muon_current_predicate` | FAIL | FAIL |
| `composite_candidates[0].DiOnia_context.DiOnia_Chi2` | 0.013092 | 2.7498 |
| `composite_candidates[0].DiOnia_context.DiOnia_VtxProb` | 0.9089 | 0.097264 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxIdx` | -1 | -1 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxPass` | 0 | 0 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[0].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[0].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[0].stages.candidate_base` | PASS | FAIL |
| `composite_candidates[0].stages.hlt_muon_matched` | PASS | FAIL |
| `composite_candidates[0].stages.four_muon_vtx` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitValid` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_trackPVPass` | FAIL | FAIL |
| `composite_candidates[1].candidate_idx` | — | 1 |
| `composite_candidates[1].muon_indices` | — | 0, 4, 1, 2 |
| `composite_candidates[1].muon_jpsi_ancestors` | — | 3, 3, 0, 0 |
| `composite_candidates[1].jpsi_1_gen_idx` | — | 3 |
| `composite_candidates[1].jpsi_2_gen_idx` | — | 0 |
| `composite_candidates[1].phi_gen_idx` | — | -1 |
| `composite_candidates[1].triple_gen_matched` | — | FAIL |
| `composite_candidates[1].trigger_match.dimuon0_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.doublemu_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.passed` | — | PASS |
| `composite_candidates[1].muVertexId` | — | 0, 0, 4, 0 |
| `composite_candidates[1].four_muon_current_predicate` | — | FAIL |
| `composite_candidates[1].DiOnia_context.DiOnia_Chi2` | — | 2.7498 |
| `composite_candidates[1].DiOnia_context.DiOnia_VtxProb` | — | 0.097264 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxIdx` | — | -1 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxPass` | — | 0 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitPass` | — | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitValid` | — | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_ndof` | — | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_passAny` | — | 1 |
| `composite_candidates[1].Pri.Pri_fitValid` | — | PASS |
| `composite_candidates[1].Pri.Pri_fitPass` | — | PASS |
| `composite_candidates[1].Pri.Pri_assocPVPass` | — | FAIL |
| `composite_candidates[1].Pri.Pri_trackPVPass` | — | PASS |
| `composite_candidates[1].stages.candidate_base` | — | FAIL |
| `composite_candidates[1].stages.hlt_muon_matched` | — | FAIL |
| `composite_candidates[1].stages.four_muon_vtx` | — | FAIL |
| `composite_candidates[1].stages.Pri_fitValid` | — | FAIL |
| `composite_candidates[1].stages.Pri_fitPass` | — | FAIL |
| `composite_candidates[1].stages.Pri_assocPVPass` | — | FAIL |
| `composite_candidates[1].stages.Pri_trackPVPass` | — | FAIL |
| `composite_candidates[2].candidate_idx` | — | 2 |
| `composite_candidates[2].muon_indices` | — | 0, 4, 1, 2 |
| `composite_candidates[2].muon_jpsi_ancestors` | — | 3, 3, 0, 0 |
| `composite_candidates[2].jpsi_1_gen_idx` | — | 3 |
| `composite_candidates[2].jpsi_2_gen_idx` | — | 0 |
| `composite_candidates[2].phi_gen_idx` | — | 4 |
| `composite_candidates[2].triple_gen_matched` | — | PASS |
| `composite_candidates[2].trigger_match.dimuon0_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.doublemu_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.passed` | — | PASS |
| `composite_candidates[2].muVertexId` | — | 0, 0, 4, 0 |
| `composite_candidates[2].four_muon_current_predicate` | — | FAIL |
| `composite_candidates[2].DiOnia_context.DiOnia_Chi2` | — | 2.7498 |
| `composite_candidates[2].DiOnia_context.DiOnia_VtxProb` | — | 0.097264 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxIdx` | — | -1 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxPass` | — | 0 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitPass` | — | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitValid` | — | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_ndof` | — | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_passAny` | — | 1 |
| `composite_candidates[2].Pri.Pri_fitValid` | — | PASS |
| `composite_candidates[2].Pri.Pri_fitPass` | — | PASS |
| `composite_candidates[2].Pri.Pri_assocPVPass` | — | FAIL |
| `composite_candidates[2].Pri.Pri_trackPVPass` | — | PASS |
| `composite_candidates[2].stages.candidate_base` | — | PASS |
| `composite_candidates[2].stages.hlt_muon_matched` | — | PASS |
| `composite_candidates[2].stages.four_muon_vtx` | — | FAIL |
| `composite_candidates[2].stages.Pri_fitValid` | — | FAIL |
| `composite_candidates[2].stages.Pri_fitPass` | — | FAIL |
| `composite_candidates[2].stages.Pri_assocPVPass` | — | FAIL |
| `composite_candidates[2].stages.Pri_trackPVPass` | — | FAIL |

### `event / hlt_event / numerator`

| Field | Event 1<br>`entry 22` | Event 2<br>`entry 35` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 22 | 35 |
| `identity.run:lumi:event` | 1:1:304 | 1:1:702 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.s_cand` | PASS | PASS |
| `flags.hlt_event` | PASS | PASS |
| `trigger.path_fired` | PASS | PASS |
| `trigger.paths[0].name` | HLT_DoubleMu4_3_LowMass_v1 | HLT_DoubleMu4_3_LowMass_v1 |
| `trigger.paths[0].result` | PASS | PASS |
| `trigger.paths[1].name` | HLT_Dimuon0_Jpsi3p5_Muon2_v5 | HLT_Dimuon0_Jpsi3p5_Muon2_v5 |
| `trigger.paths[1].result` | FAIL | PASS |
| `trigger.index_map.dimuon0_trig` | 0 | 0 |
| `trigger.index_map.doublemu_trig` | 1 | 1 |
| `trigger.index_map.dimuon0_filt` | 0 | 0 |
| `trigger.index_map.doublemu_filt` | 1 | 1 |

### `event / hlt_event / rejected`

| Field | Event 1<br>`entry 28` | Event 2<br>`entry 29` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source1_35events.root | jjp_dps_patch2_pre2_runb_audit_source1_35events.root |
| `identity.entry` | 28 | 29 |
| `identity.run:lumi:event` | 1:1:14977 | 1:1:18746 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.s_cand` | PASS | PASS |
| `flags.hlt_event` | FAIL | FAIL |
| `trigger.path_fired` | FAIL | FAIL |
| `trigger.paths[0].name` | HLT_DoubleMu4_3_LowMass_v1 | HLT_DoubleMu4_3_LowMass_v1 |
| `trigger.paths[0].result` | FAIL | FAIL |
| `trigger.paths[1].name` | HLT_Dimuon0_Jpsi3p5_Muon2_v5 | HLT_Dimuon0_Jpsi3p5_Muon2_v5 |
| `trigger.paths[1].result` | FAIL | FAIL |
| `trigger.index_map.dimuon0_trig` | 0 | 0 |
| `trigger.index_map.doublemu_trig` | 1 | 1 |
| `trigger.index_map.dimuon0_filt` | 0 | 0 |
| `trigger.index_map.doublemu_filt` | 1 | 1 |

### `event / hlt_muon_matched / numerator`

| Field | Event 1<br>`entry 22` | Event 2<br>`entry 35` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 22 | 35 |
| `identity.run:lumi:event` | 1:1:304 | 1:1:702 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.s_cand` | PASS | PASS |
| `flags.hlt_event` | PASS | PASS |
| `flags.hlt_muon_matched` | PASS | PASS |
| `trigger.path_fired` | PASS | PASS |
| `trigger.paths[0].name` | HLT_DoubleMu4_3_LowMass_v1 | HLT_DoubleMu4_3_LowMass_v1 |
| `trigger.paths[0].result` | PASS | PASS |
| `trigger.paths[1].name` | HLT_Dimuon0_Jpsi3p5_Muon2_v5 | HLT_Dimuon0_Jpsi3p5_Muon2_v5 |
| `trigger.paths[1].result` | FAIL | PASS |
| `trigger.index_map.dimuon0_trig` | 0 | 0 |
| `trigger.index_map.doublemu_trig` | 1 | 1 |
| `trigger.index_map.dimuon0_filt` | 0 | 0 |
| `trigger.index_map.doublemu_filt` | 1 | 1 |
| `composite_candidates[0].candidate_idx` | 0 | 0 |
| `composite_candidates[0].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[0].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[0].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[0].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[0].phi_gen_idx` | -1 | -1 |
| `composite_candidates[0].triple_gen_matched` | FAIL | FAIL |
| `composite_candidates[0].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[0].trigger_match.passed` | PASS | PASS |
| `composite_candidates[0].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[0].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[0].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[0].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[0].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_assocPVPass` | PASS | PASS |
| `composite_candidates[0].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[0].stages.candidate_base` | FAIL | FAIL |
| `composite_candidates[0].stages.hlt_muon_matched` | FAIL | FAIL |
| `composite_candidates[0].stages.four_muon_vtx` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitValid` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_fitPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[0].stages.Pri_trackPVPass` | FAIL | FAIL |
| `composite_candidates[1].candidate_idx` | 1 | 1 |
| `composite_candidates[1].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[1].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[1].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[1].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[1].phi_gen_idx` | 7 | -1 |
| `composite_candidates[1].triple_gen_matched` | PASS | FAIL |
| `composite_candidates[1].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[1].trigger_match.passed` | PASS | PASS |
| `composite_candidates[1].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[1].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[1].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[1].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[1].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[1].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[1].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_assocPVPass` | PASS | PASS |
| `composite_candidates[1].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[1].stages.candidate_base` | PASS | FAIL |
| `composite_candidates[1].stages.hlt_muon_matched` | PASS | FAIL |
| `composite_candidates[1].stages.four_muon_vtx` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_fitValid` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_fitPass` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_assocPVPass` | PASS | FAIL |
| `composite_candidates[1].stages.Pri_trackPVPass` | PASS | FAIL |
| `composite_candidates[2].candidate_idx` | 2 | 2 |
| `composite_candidates[2].muon_indices` | 1, 3, 2, 4 | 0, 2, 1, 3 |
| `composite_candidates[2].muon_jpsi_ancestors` | 4, 4, 14, 14 | 8, 8, 23, 23 |
| `composite_candidates[2].jpsi_1_gen_idx` | 4 | 8 |
| `composite_candidates[2].jpsi_2_gen_idx` | 14 | 23 |
| `composite_candidates[2].phi_gen_idx` | -1 | -1 |
| `composite_candidates[2].triple_gen_matched` | FAIL | FAIL |
| `composite_candidates[2].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.doublemu_muons` | FAIL, FAIL, PASS, PASS | PASS, PASS, PASS, PASS |
| `composite_candidates[2].trigger_match.passed` | PASS | PASS |
| `composite_candidates[2].muVertexId` | 0, 0, 0, 0 | 0, 0, 0, 0 |
| `composite_candidates[2].four_muon_current_predicate` | PASS | PASS |
| `composite_candidates[2].DiOnia_context.DiOnia_Chi2` | 1.6545 | 0.83159 |
| `composite_candidates[2].DiOnia_context.DiOnia_VtxProb` | 0.19835 | 0.36181 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 | 0 |
| `composite_candidates[2].DiOnia_context.DiOnia_commonRecVtxPass` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitPass` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_fitValid` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_ndof` | 1 | 1 |
| `composite_candidates[2].DiOnia_context.DiOnia_passAny` | 1 | 1 |
| `composite_candidates[2].Pri.Pri_fitValid` | PASS | PASS |
| `composite_candidates[2].Pri.Pri_fitPass` | PASS | PASS |
| `composite_candidates[2].Pri.Pri_assocPVPass` | FAIL | PASS |
| `composite_candidates[2].Pri.Pri_trackPVPass` | PASS | PASS |
| `composite_candidates[2].stages.candidate_base` | FAIL | FAIL |
| `composite_candidates[2].stages.hlt_muon_matched` | FAIL | FAIL |
| `composite_candidates[2].stages.four_muon_vtx` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_fitValid` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_fitPass` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_assocPVPass` | FAIL | FAIL |
| `composite_candidates[2].stages.Pri_trackPVPass` | FAIL | FAIL |
| `composite_candidates[3].candidate_idx` | — | 3 |
| `composite_candidates[3].muon_indices` | — | 0, 2, 1, 3 |
| `composite_candidates[3].muon_jpsi_ancestors` | — | 8, 8, 23, 23 |
| `composite_candidates[3].jpsi_1_gen_idx` | — | 8 |
| `composite_candidates[3].jpsi_2_gen_idx` | — | 23 |
| `composite_candidates[3].phi_gen_idx` | — | 14 |
| `composite_candidates[3].triple_gen_matched` | — | PASS |
| `composite_candidates[3].trigger_match.dimuon0_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[3].trigger_match.doublemu_muons` | — | PASS, PASS, PASS, PASS |
| `composite_candidates[3].trigger_match.passed` | — | PASS |
| `composite_candidates[3].muVertexId` | — | 0, 0, 0, 0 |
| `composite_candidates[3].four_muon_current_predicate` | — | PASS |
| `composite_candidates[3].DiOnia_context.DiOnia_Chi2` | — | 0.83159 |
| `composite_candidates[3].DiOnia_context.DiOnia_VtxProb` | — | 0.36181 |
| `composite_candidates[3].DiOnia_context.DiOnia_commonRecVtxIdx` | — | 0 |
| `composite_candidates[3].DiOnia_context.DiOnia_commonRecVtxPass` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_fitPass` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_fitValid` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_ndof` | — | 1 |
| `composite_candidates[3].DiOnia_context.DiOnia_passAny` | — | 1 |
| `composite_candidates[3].Pri.Pri_fitValid` | — | PASS |
| `composite_candidates[3].Pri.Pri_fitPass` | — | PASS |
| `composite_candidates[3].Pri.Pri_assocPVPass` | — | PASS |
| `composite_candidates[3].Pri.Pri_trackPVPass` | — | PASS |
| `composite_candidates[3].stages.candidate_base` | — | PASS |
| `composite_candidates[3].stages.hlt_muon_matched` | — | PASS |
| `composite_candidates[3].stages.four_muon_vtx` | — | PASS |
| `composite_candidates[3].stages.Pri_fitValid` | — | PASS |
| `composite_candidates[3].stages.Pri_fitPass` | — | PASS |
| `composite_candidates[3].stages.Pri_assocPVPass` | — | PASS |
| `composite_candidates[3].stages.Pri_trackPVPass` | — | PASS |

### `event / hlt_muon_matched / rejected`

| Field | Event 1<br>`entry 27` |
|---|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source1_35events.root |
| `identity.entry` | 27 |
| `identity.run:lumi:event` | 1:1:11771 |
| `selection.role` | rejected |
| `flags.full_gen` | PASS |
| `flags.s_cand` | PASS |
| `flags.hlt_event` | PASS |
| `flags.hlt_muon_matched` | FAIL |
| `trigger.path_fired` | PASS |
| `trigger.paths[0].name` | HLT_DoubleMu4_3_LowMass_v1 |
| `trigger.paths[0].result` | PASS |
| `trigger.paths[1].name` | HLT_Dimuon0_Jpsi3p5_Muon2_v5 |
| `trigger.paths[1].result` | FAIL |
| `trigger.index_map.dimuon0_trig` | 0 |
| `trigger.index_map.doublemu_trig` | 1 |
| `trigger.index_map.dimuon0_filt` | 0 |
| `trigger.index_map.doublemu_filt` | 1 |
| `composite_candidates[0].candidate_idx` | 0 |
| `composite_candidates[0].muon_indices` | 0, 2, 1, 3 |
| `composite_candidates[0].muon_jpsi_ancestors` | 14, 14, 2, 2 |
| `composite_candidates[0].jpsi_1_gen_idx` | 14 |
| `composite_candidates[0].jpsi_2_gen_idx` | 2 |
| `composite_candidates[0].phi_gen_idx` | 5 |
| `composite_candidates[0].triple_gen_matched` | PASS |
| `composite_candidates[0].trigger_match.dimuon0_muons` | FAIL, FAIL, FAIL, FAIL |
| `composite_candidates[0].trigger_match.doublemu_muons` | PASS, FAIL, PASS, FAIL |
| `composite_candidates[0].trigger_match.passed` | FAIL |
| `composite_candidates[0].muVertexId` | 0, 0, 0, 0 |
| `composite_candidates[0].four_muon_current_predicate` | PASS |
| `composite_candidates[0].DiOnia_context.DiOnia_Chi2` | 0.26346 |
| `composite_candidates[0].DiOnia_context.DiOnia_VtxProb` | 0.60775 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxIdx` | 0 |
| `composite_candidates[0].DiOnia_context.DiOnia_commonRecVtxPass` | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitPass` | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_fitValid` | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_ndof` | 1 |
| `composite_candidates[0].DiOnia_context.DiOnia_passAny` | 1 |
| `composite_candidates[0].Pri.Pri_fitValid` | PASS |
| `composite_candidates[0].Pri.Pri_fitPass` | PASS |
| `composite_candidates[0].Pri.Pri_assocPVPass` | PASS |
| `composite_candidates[0].Pri.Pri_trackPVPass` | PASS |
| `composite_candidates[0].stages.candidate_base` | PASS |
| `composite_candidates[0].stages.hlt_muon_matched` | FAIL |
| `composite_candidates[0].stages.four_muon_vtx` | FAIL |
| `composite_candidates[0].stages.Pri_fitValid` | FAIL |
| `composite_candidates[0].stages.Pri_fitPass` | FAIL |
| `composite_candidates[0].stages.Pri_assocPVPass` | FAIL |
| `composite_candidates[0].stages.Pri_trackPVPass` | FAIL |

### `event / s_cand / numerator`

| Field | Event 1<br>`entry 22` | Event 2<br>`entry 35` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 22 | 35 |
| `identity.run:lumi:event` | 1:1:304 | 1:1:702 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.s_cand` | PASS | PASS |

### `event / s_cand / rejected`

| Field | Event 1<br>`entry 0` | Event 2<br>`entry 1` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 0 | 1 |
| `identity.run:lumi:event` | 1:1:1 | 1:1:6 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.s_cand` | FAIL | FAIL |

### `jpsi_lead / dimuon / numerator`

| Field | Event 1<br>`entry 6` | Event 2<br>`entry 8` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 6 | 8 |
| `identity.run:lumi:event` | 1:1:80 | 1:1:82 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | PASS | PASS |
| `flags.muonID` | PASS | PASS |
| `flags.dimuon` | PASS | PASS |
| `GEN.idx` | 21 | 3 |
| `GEN.pt` | 9.9313 | 10.364 |
| `GEN.eta` | 0.2084 | 0.61367 |
| `GEN.y` | 0.19909 | 0.59065 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 22, 23 | 4, 5 |
| `map_bin.pt` | 9.9313 | 10.364 |
| `map_bin.y` | 0.19909 | 0.59065 |
| `map_bin.pt_bin` | 0 | 1 |
| `map_bin.signed_y_bin` | 4 | 4 |
| `map_bin.abs_y_bin` | 0 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 22 | 4 |
| `fiducial.daughters[0].pt` | 6.321 | 3.7137 |
| `fiducial.daughters[0].eta` | 0.39234 | 0.68239 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 23 | 5 |
| `fiducial.daughters[1].pt` | 3.7656 | 7.0764 |
| `fiducial.daughters[1].eta` | -0.12169 | 0.54263 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 22 | 4 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 3 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 1 | 3 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 1 | 3 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 23 | 5 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 2 | 1 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 2 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 2 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |
| `single_candidates[0].candidate_idx` | 0 | 0 |
| `single_candidates[0].ancestor_1` | 21 | 3 |
| `single_candidates[0].ancestor_2` | 21 | 3 |
| `single_candidates[0].same_target_parent` | PASS | PASS |
| `single_candidates[0].mass` | 3.1074 | 3.1076 |
| `single_candidates[0].pt` | 9.9277 | 10.425 |
| `single_candidates[0].y` | 0.19635 | 0.58998 |
| `single_candidates[0].VtxProb` | 0.87209 | 0.039489 |
| `single_candidates[0].fitValid` | PASS | PASS |
| `single_candidates[0].fitPass` | PASS | PASS |
| `single_candidates[0].quality_passed` | PASS | PASS |
| `single_candidates[0].witness` | PASS | PASS |

### `jpsi_lead / dimuon / rejected`

| Field | Event 1<br>`entry 14` | Event 2<br>`entry 27` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 14 | 27 |
| `identity.run:lumi:event` | 1:1:152 | 1:1:398 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | PASS | PASS |
| `flags.muonID` | PASS | PASS |
| `flags.dimuon` | FAIL | FAIL |
| `GEN.idx` | 23 | 18 |
| `GEN.pt` | 13.234 | 20.212 |
| `GEN.eta` | -1.8353 | -0.78856 |
| `GEN.y` | -1.81 | -0.78096 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 24, 25 | 19, 20 |
| `map_bin.pt` | 13.234 | 20.212 |
| `map_bin.y` | -1.81 | -0.78096 |
| `map_bin.pt_bin` | 1 | 3 |
| `map_bin.signed_y_bin` | 0 | 2 |
| `map_bin.abs_y_bin` | 3 | 1 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 24 | 19 |
| `fiducial.daughters[0].pt` | 4.0337 | 4.6818 |
| `fiducial.daughters[0].eta` | -1.666 | -0.52707 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 25 | 20 |
| `fiducial.daughters[1].pt` | 9.4951 | 15.566 |
| `fiducial.daughters[1].eta` | -1.8716 | -0.85813 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 24 | 19 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 2 | 2 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 2 | 2 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 2 | 2 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 25 | 20 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 0 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |
| `single_candidates[0].candidate_idx` | 0 | 0 |
| `single_candidates[0].ancestor_1` | 23 | 18 |
| `single_candidates[0].ancestor_2` | 23 | 18 |
| `single_candidates[0].same_target_parent` | PASS | PASS |
| `single_candidates[0].mass` | 3.0921 | 3.0745 |
| `single_candidates[0].pt` | 13.215 | 20.073 |
| `single_candidates[0].y` | -1.8118 | -0.78065 |
| `single_candidates[0].VtxProb` | 0.0022009 | 0.004517 |
| `single_candidates[0].fitValid` | PASS | PASS |
| `single_candidates[0].fitPass` | PASS | PASS |
| `single_candidates[0].quality_passed` | FAIL | FAIL |
| `single_candidates[0].witness` | FAIL | FAIL |

### `jpsi_lead / dimuon / raw_only`

| Field | Event 1<br>`entry 3` | Event 2<br>`entry 25` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 3 | 25 |
| `identity.run:lumi:event` | 1:1:5 | 1:1:374 |
| `selection.role` | raw_only | raw_only |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | PASS | PASS |
| `flags.muonID` | FAIL | FAIL |
| `flags.dimuon` | PASS | PASS |
| `GEN.idx` | 20 | 21 |
| `GEN.pt` | 7.945 | 16.989 |
| `GEN.eta` | 1.5716 | -0.58004 |
| `GEN.y` | 1.5071 | -0.57155 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 21, 22 | 22, 23 |
| `map_bin.pt` | 7.945 | 16.989 |
| `map_bin.y` | 1.5071 | -0.57155 |
| `map_bin.pt_bin` | 0 | 2 |
| `map_bin.signed_y_bin` | 6 | 3 |
| `map_bin.abs_y_bin` | 2 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 21 | 22 |
| `fiducial.daughters[0].pt` | 4.327 | 5.7232 |
| `fiducial.daughters[0].eta` | 1.5154 | -0.32386 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 22 | 23 |
| `fiducial.daughters[1].pt` | 4.197 | 11.277 |
| `fiducial.daughters[1].eta` | 1.499 | -0.69828 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | FAIL | FAIL |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 21 | 22 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 2 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | [] | [] |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 1 | 2 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | FAIL | FAIL |
| `reconstruction_and_id.daughters[0].reco_objects[0].muIsPatSoftMuon` | FAIL | FAIL |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 22 | 23 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 0 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |
| `single_candidates[0].candidate_idx` | 0 | 0 |
| `single_candidates[0].ancestor_1` | 20 | 21 |
| `single_candidates[0].ancestor_2` | 20 | 21 |
| `single_candidates[0].same_target_parent` | PASS | PASS |
| `single_candidates[0].mass` | 3.1577 | 3.0859 |
| `single_candidates[0].pt` | 8.0865 | 16.912 |
| `single_candidates[0].y` | 1.5059 | -0.57022 |
| `single_candidates[0].VtxProb` | 0.53436 | 0.95725 |
| `single_candidates[0].fitValid` | PASS | PASS |
| `single_candidates[0].fitPass` | PASS | PASS |
| `single_candidates[0].quality_passed` | PASS | PASS |
| `single_candidates[0].witness` | PASS | PASS |

### `jpsi_lead / fiducial / numerator`

| Field | Event 1<br>`entry 3` | Event 2<br>`entry 6` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 3 | 6 |
| `identity.run:lumi:event` | 1:1:5 | 1:1:80 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `GEN.idx` | 20 | 21 |
| `GEN.pt` | 7.945 | 9.9313 |
| `GEN.eta` | 1.5716 | 0.2084 |
| `GEN.y` | 1.5071 | 0.19909 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 21, 22 | 22, 23 |
| `map_bin.pt` | 7.945 | 9.9313 |
| `map_bin.y` | 1.5071 | 0.19909 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 6 | 4 |
| `map_bin.abs_y_bin` | 2 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 21 | 22 |
| `fiducial.daughters[0].pt` | 4.327 | 6.321 |
| `fiducial.daughters[0].eta` | 1.5154 | 0.39234 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 22 | 23 |
| `fiducial.daughters[1].pt` | 4.197 | 3.7656 |
| `fiducial.daughters[1].eta` | 1.499 | -0.12169 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |

### `jpsi_lead / fiducial / rejected`

| Field | Event 1<br>`entry 0` | Event 2<br>`entry 1` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 0 | 1 |
| `identity.run:lumi:event` | 1:1:1 | 1:1:6 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | FAIL | FAIL |
| `GEN.idx` | 7 | 14 |
| `GEN.pt` | 14.719 | 12.529 |
| `GEN.eta` | 0.70224 | -0.65621 |
| `GEN.y` | 0.68922 | -0.63932 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 8, 9 | 15, 16 |
| `map_bin.pt` | 14.719 | 12.529 |
| `map_bin.y` | 0.68922 | -0.63932 |
| `map_bin.pt_bin` | 1 | 1 |
| `map_bin.signed_y_bin` | 5 | 2 |
| `map_bin.abs_y_bin` | 1 | 1 |
| `fiducial.passed` | FAIL | FAIL |
| `fiducial.daughters[0].gen_idx` | 8 | 15 |
| `fiducial.daughters[0].pt` | 1.7546 | 11.854 |
| `fiducial.daughters[0].eta` | 0.36099 | -0.68969 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | FAIL | PASS |
| `fiducial.daughters[1].gen_idx` | 9 | 16 |
| `fiducial.daughters[1].pt` | 13.174 | 0.84057 |
| `fiducial.daughters[1].eta` | 0.7339 | 0.017403 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | FAIL |

### `jpsi_lead / muonID / numerator`

| Field | Event 1<br>`entry 6` | Event 2<br>`entry 8` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 6 | 8 |
| `identity.run:lumi:event` | 1:1:80 | 1:1:82 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | PASS | PASS |
| `flags.muonID` | PASS | PASS |
| `GEN.idx` | 21 | 3 |
| `GEN.pt` | 9.9313 | 10.364 |
| `GEN.eta` | 0.2084 | 0.61367 |
| `GEN.y` | 0.19909 | 0.59065 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 22, 23 | 4, 5 |
| `map_bin.pt` | 9.9313 | 10.364 |
| `map_bin.y` | 0.19909 | 0.59065 |
| `map_bin.pt_bin` | 0 | 1 |
| `map_bin.signed_y_bin` | 4 | 4 |
| `map_bin.abs_y_bin` | 0 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 22 | 4 |
| `fiducial.daughters[0].pt` | 6.321 | 3.7137 |
| `fiducial.daughters[0].eta` | 0.39234 | 0.68239 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 23 | 5 |
| `fiducial.daughters[1].pt` | 3.7656 | 7.0764 |
| `fiducial.daughters[1].eta` | -0.12169 | 0.54263 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 22 | 4 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 3 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 1 | 3 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 1 | 3 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 23 | 5 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 2 | 1 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 2 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 2 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |

### `jpsi_lead / muonID / rejected`

| Field | Event 1<br>`entry 3` | Event 2<br>`entry 25` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 3 | 25 |
| `identity.run:lumi:event` | 1:1:5 | 1:1:374 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | PASS | PASS |
| `flags.muonID` | FAIL | FAIL |
| `GEN.idx` | 20 | 21 |
| `GEN.pt` | 7.945 | 16.989 |
| `GEN.eta` | 1.5716 | -0.58004 |
| `GEN.y` | 1.5071 | -0.57155 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 21, 22 | 22, 23 |
| `map_bin.pt` | 7.945 | 16.989 |
| `map_bin.y` | 1.5071 | -0.57155 |
| `map_bin.pt_bin` | 0 | 2 |
| `map_bin.signed_y_bin` | 6 | 3 |
| `map_bin.abs_y_bin` | 2 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 21 | 22 |
| `fiducial.daughters[0].pt` | 4.327 | 5.7232 |
| `fiducial.daughters[0].eta` | 1.5154 | -0.32386 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 22 | 23 |
| `fiducial.daughters[1].pt` | 4.197 | 11.277 |
| `fiducial.daughters[1].eta` | 1.499 | -0.69828 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | FAIL | FAIL |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 21 | 22 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 2 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | [] | [] |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 1 | 2 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | FAIL | FAIL |
| `reconstruction_and_id.daughters[0].reco_objects[0].muIsPatSoftMuon` | FAIL | FAIL |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 22 | 23 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 0 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |

### `jpsi_lead / muonID / raw_only`

| Field | Event 1<br>`entry 2` | Event 2<br>`entry 20` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 2 | 20 |
| `identity.run:lumi:event` | 1:1:11 | 1:1:277 |
| `selection.role` | raw_only | raw_only |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | FAIL | FAIL |
| `flags.muonRECO` | PASS | PASS |
| `flags.muonID` | PASS | PASS |
| `GEN.idx` | 25 | 13 |
| `GEN.pt` | 18.566 | 7.6315 |
| `GEN.eta` | -2.1184 | 2.0627 |
| `GEN.y` | -2.1051 | 1.9892 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 26, 27 | 14, 15 |
| `map_bin.pt` | 18.566 | 7.6315 |
| `map_bin.y` | -2.1051 | 1.9892 |
| `map_bin.pt_bin` | 2 | 0 |
| `map_bin.signed_y_bin` | 0 | 7 |
| `map_bin.abs_y_bin` | 3 | 3 |
| `fiducial.passed` | FAIL | FAIL |
| `fiducial.daughters[0].gen_idx` | 26 | 14 |
| `fiducial.daughters[0].pt` | 16.555 | 7.1357 |
| `fiducial.daughters[0].eta` | -2.1244 | 1.9821 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 27 | 15 |
| `fiducial.daughters[1].pt` | 2.239 | 1.0926 |
| `fiducial.daughters[1].eta` | -1.9643 | 2.0399 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | FAIL | FAIL |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 26 | 14 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 0 | 0 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 27 | 15 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 2 | 2 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 2 | 2 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 2 | 2 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |

### `jpsi_lead / muonRECO / numerator`

| Field | Event 1<br>`entry 3` | Event 2<br>`entry 6` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 3 | 6 |
| `identity.run:lumi:event` | 1:1:5 | 1:1:80 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | PASS | PASS |
| `GEN.idx` | 20 | 21 |
| `GEN.pt` | 7.945 | 9.9313 |
| `GEN.eta` | 1.5716 | 0.2084 |
| `GEN.y` | 1.5071 | 0.19909 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 21, 22 | 22, 23 |
| `map_bin.pt` | 7.945 | 9.9313 |
| `map_bin.y` | 1.5071 | 0.19909 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 6 | 4 |
| `map_bin.abs_y_bin` | 2 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 21 | 22 |
| `fiducial.daughters[0].pt` | 4.327 | 6.321 |
| `fiducial.daughters[0].eta` | 1.5154 | 0.39234 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 22 | 23 |
| `fiducial.daughters[1].pt` | 4.197 | 3.7656 |
| `fiducial.daughters[1].eta` | 1.499 | -0.12169 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 21 | 22 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 1 |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 22 | 23 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 0 | 2 |

### `jpsi_lead / muonRECO / rejected`

| Field | Event 1<br>`entry 23` | Event 2<br>`entry 32` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 23 | 32 |
| `identity.run:lumi:event` | 1:1:351 | 1:1:655 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | FAIL | FAIL |
| `GEN.idx` | 21 | 33 |
| `GEN.pt` | 10.465 | 25.407 |
| `GEN.eta` | 1.3118 | 1.4434 |
| `GEN.y` | 1.2757 | 1.4369 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 24, 25 | 34, 35 |
| `map_bin.pt` | 10.465 | 25.407 |
| `map_bin.y` | 1.2757 | 1.4369 |
| `map_bin.pt_bin` | 1 | 3 |
| `map_bin.signed_y_bin` | 6 | 6 |
| `map_bin.abs_y_bin` | 2 | 2 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 24 | 34 |
| `fiducial.daughters[0].pt` | 8.0809 | 14.642 |
| `fiducial.daughters[0].eta` | 1.2941 | 1.3357 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 25 | 35 |
| `fiducial.daughters[1].pt` | 2.8243 | 10.776 |
| `fiducial.daughters[1].eta` | 1.224 | 1.5741 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | FAIL | FAIL |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 24 | 34 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 25 | 35 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | [] | [] |

### `jpsi_lead / muonRECO / raw_only`

| Field | Event 1<br>`entry 2` | Event 2<br>`entry 20` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 2 | 20 |
| `identity.run:lumi:event` | 1:1:11 | 1:1:277 |
| `selection.role` | raw_only | raw_only |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | FAIL | FAIL |
| `flags.muonRECO` | PASS | PASS |
| `GEN.idx` | 25 | 13 |
| `GEN.pt` | 18.566 | 7.6315 |
| `GEN.eta` | -2.1184 | 2.0627 |
| `GEN.y` | -2.1051 | 1.9892 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 26, 27 | 14, 15 |
| `map_bin.pt` | 18.566 | 7.6315 |
| `map_bin.y` | -2.1051 | 1.9892 |
| `map_bin.pt_bin` | 2 | 0 |
| `map_bin.signed_y_bin` | 0 | 7 |
| `map_bin.abs_y_bin` | 3 | 3 |
| `fiducial.passed` | FAIL | FAIL |
| `fiducial.daughters[0].gen_idx` | 26 | 14 |
| `fiducial.daughters[0].pt` | 16.555 | 7.1357 |
| `fiducial.daughters[0].eta` | -2.1244 | 1.9821 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 27 | 15 |
| `fiducial.daughters[1].pt` | 2.239 | 1.0926 |
| `fiducial.daughters[1].eta` | -1.9643 | 2.0399 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | FAIL | FAIL |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 26 | 14 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 27 | 15 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 2 | 2 |

### `jpsi_sublead / dimuon / numerator`

| Field | Event 1<br>`entry 13` | Event 2<br>`entry 19` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 13 | 19 |
| `identity.run:lumi:event` | 1:1:141 | 1:1:255 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | PASS | PASS |
| `flags.muonID` | PASS | PASS |
| `flags.dimuon` | PASS | PASS |
| `GEN.idx` | 4 | 23 |
| `GEN.pt` | 8.6864 | 9.4884 |
| `GEN.eta` | -0.058591 | -1.1845 |
| `GEN.y` | -0.055194 | -1.1429 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 7, 8 | 24, 25 |
| `map_bin.pt` | 8.6864 | 9.4884 |
| `map_bin.y` | -0.055194 | -1.1429 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 3 | 2 |
| `map_bin.abs_y_bin` | 0 | 1 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 7 | 24 |
| `fiducial.daughters[0].pt` | 4.7718 | 4.5126 |
| `fiducial.daughters[0].eta` | 0.11172 | -1.4109 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 8 | 25 |
| `fiducial.daughters[1].pt` | 4.3071 | 5.16 |
| `fiducial.daughters[1].eta` | -0.23995 | -0.90816 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 7 | 24 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 2 | 2 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 2 | 2 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 2 | 2 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 8 | 25 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 3 | 1 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 3 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 3 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |
| `single_candidates[0].candidate_idx` | 1 | 0 |
| `single_candidates[0].ancestor_1` | 4 | 23 |
| `single_candidates[0].ancestor_2` | 4 | 23 |
| `single_candidates[0].same_target_parent` | PASS | PASS |
| `single_candidates[0].mass` | 3.1081 | 3.1 |
| `single_candidates[0].pt` | 8.7214 | 9.5082 |
| `single_candidates[0].y` | -0.05462 | -1.1444 |
| `single_candidates[0].VtxProb` | 0.84756 | 0.99885 |
| `single_candidates[0].fitValid` | PASS | PASS |
| `single_candidates[0].fitPass` | PASS | PASS |
| `single_candidates[0].quality_passed` | PASS | PASS |
| `single_candidates[0].witness` | PASS | PASS |

### `jpsi_sublead / dimuon / rejected`

| Field | Event 1<br>`entry 38` | Event 2<br>`entry 1` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source1_35events.root |
| `identity.entry` | 38 | 1 |
| `identity.run:lumi:event` | 1:1:853 | 1:1:92 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | PASS | PASS |
| `flags.muonID` | PASS | PASS |
| `flags.dimuon` | FAIL | FAIL |
| `GEN.idx` | 5 | 1 |
| `GEN.pt` | 6.2663 | 7.9967 |
| `GEN.eta` | 1.8113 | 1.5484 |
| `GEN.y` | 1.7084 | 1.4849 |
| `GEN.mass` | 3.096 | 3.0969 |
| `GEN.daughter_indices` | 6, 7 | 2, 3 |
| `map_bin.pt` | 6.2663 | 7.9967 |
| `map_bin.y` | 1.7084 | 1.4849 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 6 | 6 |
| `map_bin.abs_y_bin` | 2 | 2 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 6 | 2 |
| `fiducial.daughters[0].pt` | 3.9318 | 4.5023 |
| `fiducial.daughters[0].eta` | 1.3804 | 1.4812 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 7 | 3 |
| `fiducial.daughters[1].pt` | 2.5175 | 4.0705 |
| `fiducial.daughters[1].eta` | 2.2099 | 1.4896 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 6 | 2 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 1 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 1 | 1 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 1 | 1 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 7 | 3 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 2 | 2 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 2 | 2 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 2 | 2 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |
| `single_candidates` | [] | [] |

### `jpsi_sublead / dimuon / raw_only`

| Field | Event 1<br>`entry 17` | Event 2<br>`entry 30` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 17 | 30 |
| `identity.run:lumi:event` | 1:1:206 | 1:1:515 |
| `selection.role` | raw_only | raw_only |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | PASS | PASS |
| `flags.muonID` | FAIL | FAIL |
| `flags.dimuon` | PASS | PASS |
| `GEN.idx` | 6 | 3 |
| `GEN.pt` | 9.5224 | 8.3059 |
| `GEN.eta` | -0.57407 | 0.53336 |
| `GEN.y` | -0.5485 | 0.5024 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 8, 9 | 4, 5 |
| `map_bin.pt` | 9.5224 | 8.3059 |
| `map_bin.y` | -0.5485 | 0.5024 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 3 | 4 |
| `map_bin.abs_y_bin` | 0 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 8 | 4 |
| `fiducial.daughters[0].pt` | 4.7378 | 4.0894 |
| `fiducial.daughters[0].eta` | -0.86896 | 0.84272 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 9 | 5 |
| `fiducial.daughters[1].pt` | 4.785 | 4.3058 |
| `fiducial.daughters[1].eta` | -0.23133 | 0.17887 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | FAIL | FAIL |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 8 | 4 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 3 | 3 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | [] | 3 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 3 | 3 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | FAIL | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].muIsPatSoftMuon` | FAIL | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 9 | 5 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 2 | 2 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 2 | [] |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 2 | 2 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | FAIL |
| `reconstruction_and_id.daughters[1].reco_objects[0].muIsPatSoftMuon` | PASS | FAIL |
| `single_candidates[0].candidate_idx` | 1 | 1 |
| `single_candidates[0].ancestor_1` | 6 | 3 |
| `single_candidates[0].ancestor_2` | 6 | 3 |
| `single_candidates[0].same_target_parent` | PASS | PASS |
| `single_candidates[0].mass` | 3.0669 | 3.0944 |
| `single_candidates[0].pt` | 9.4268 | 8.3183 |
| `single_candidates[0].y` | -0.54963 | 0.50198 |
| `single_candidates[0].VtxProb` | 0.35955 | 0.15841 |
| `single_candidates[0].fitValid` | PASS | PASS |
| `single_candidates[0].fitPass` | PASS | PASS |
| `single_candidates[0].quality_passed` | PASS | PASS |
| `single_candidates[0].witness` | PASS | PASS |

### `jpsi_sublead / fiducial / numerator`

| Field | Event 1<br>`entry 9` | Event 2<br>`entry 13` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 9 | 13 |
| `identity.run:lumi:event` | 1:1:98 | 1:1:141 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `GEN.idx` | 5 | 4 |
| `GEN.pt` | 7.4496 | 8.6864 |
| `GEN.eta` | 0.98916 | -0.058591 |
| `GEN.y` | 0.9299 | -0.055194 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 6, 7 | 7, 8 |
| `map_bin.pt` | 7.4496 | 8.6864 |
| `map_bin.y` | 0.9299 | -0.055194 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 5 | 3 |
| `map_bin.abs_y_bin` | 1 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 6 | 7 |
| `fiducial.daughters[0].pt` | 3.6601 | 4.7718 |
| `fiducial.daughters[0].eta` | 1.0016 | 0.11172 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 7 | 8 |
| `fiducial.daughters[1].pt` | 4.3872 | 4.3071 |
| `fiducial.daughters[1].eta` | 0.87054 | -0.23995 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |

### `jpsi_sublead / fiducial / rejected`

| Field | Event 1<br>`entry 0` | Event 2<br>`entry 1` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 0 | 1 |
| `identity.run:lumi:event` | 1:1:1 | 1:1:6 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | FAIL | FAIL |
| `GEN.idx` | 21 | 4 |
| `GEN.pt` | 8.9537 | 12.078 |
| `GEN.eta` | -0.039331 | -0.31441 |
| `GEN.y` | -0.037172 | -0.30486 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 22, 23 | 5, 6 |
| `map_bin.pt` | 8.9537 | 12.078 |
| `map_bin.y` | -0.037172 | -0.30486 |
| `map_bin.pt_bin` | 0 | 1 |
| `map_bin.signed_y_bin` | 3 | 3 |
| `map_bin.abs_y_bin` | 0 | 0 |
| `fiducial.passed` | FAIL | FAIL |
| `fiducial.daughters[0].gen_idx` | 22 | 5 |
| `fiducial.daughters[0].pt` | 7.8732 | 9.5353 |
| `fiducial.daughters[0].eta` | -0.067789 | -0.3631 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 23 | 6 |
| `fiducial.daughters[1].pt` | 1.5744 | 2.8614 |
| `fiducial.daughters[1].eta` | 0.11527 | -0.11212 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | FAIL | FAIL |

### `jpsi_sublead / muonID / numerator`

| Field | Event 1<br>`entry 13` | Event 2<br>`entry 19` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 13 | 19 |
| `identity.run:lumi:event` | 1:1:141 | 1:1:255 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | PASS | PASS |
| `flags.muonID` | PASS | PASS |
| `GEN.idx` | 4 | 23 |
| `GEN.pt` | 8.6864 | 9.4884 |
| `GEN.eta` | -0.058591 | -1.1845 |
| `GEN.y` | -0.055194 | -1.1429 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 7, 8 | 24, 25 |
| `map_bin.pt` | 8.6864 | 9.4884 |
| `map_bin.y` | -0.055194 | -1.1429 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 3 | 2 |
| `map_bin.abs_y_bin` | 0 | 1 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 7 | 24 |
| `fiducial.daughters[0].pt` | 4.7718 | 4.5126 |
| `fiducial.daughters[0].eta` | 0.11172 | -1.4109 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 8 | 25 |
| `fiducial.daughters[1].pt` | 4.3071 | 5.16 |
| `fiducial.daughters[1].eta` | -0.23995 | -0.90816 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 7 | 24 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 2 | 2 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 2 | 2 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 2 | 2 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 8 | 25 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 3 | 1 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 3 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 3 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |

### `jpsi_sublead / muonID / rejected`

| Field | Event 1<br>`entry 17` | Event 2<br>`entry 30` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 17 | 30 |
| `identity.run:lumi:event` | 1:1:206 | 1:1:515 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | PASS | PASS |
| `flags.muonID` | FAIL | FAIL |
| `GEN.idx` | 6 | 3 |
| `GEN.pt` | 9.5224 | 8.3059 |
| `GEN.eta` | -0.57407 | 0.53336 |
| `GEN.y` | -0.5485 | 0.5024 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 8, 9 | 4, 5 |
| `map_bin.pt` | 9.5224 | 8.3059 |
| `map_bin.y` | -0.5485 | 0.5024 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 3 | 4 |
| `map_bin.abs_y_bin` | 0 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 8 | 4 |
| `fiducial.daughters[0].pt` | 4.7378 | 4.0894 |
| `fiducial.daughters[0].eta` | -0.86896 | 0.84272 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 9 | 5 |
| `fiducial.daughters[1].pt` | 4.785 | 4.3058 |
| `fiducial.daughters[1].eta` | -0.23133 | 0.17887 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | FAIL | FAIL |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 8 | 4 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 3 | 3 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | [] | 3 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 3 | 3 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | FAIL | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].muIsPatSoftMuon` | FAIL | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 9 | 5 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 2 | 2 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 2 | [] |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 2 | 2 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | FAIL |
| `reconstruction_and_id.daughters[1].reco_objects[0].muIsPatSoftMuon` | PASS | FAIL |

### `jpsi_sublead / muonID / raw_only`

| Field | Event 1<br>`entry 23` | Event 2<br>`entry 24` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 23 | 24 |
| `identity.run:lumi:event` | 1:1:351 | 1:1:356 |
| `selection.role` | raw_only | raw_only |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | FAIL | FAIL |
| `flags.muonRECO` | PASS | PASS |
| `flags.muonID` | PASS | PASS |
| `GEN.idx` | 9 | 4 |
| `GEN.pt` | 7.3211 | 9.0992 |
| `GEN.eta` | 2.1735 | 1.3396 |
| `GEN.y` | 2.0935 | 1.2922 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 10, 11 | 5, 6 |
| `map_bin.pt` | 7.3211 | 9.0992 |
| `map_bin.y` | 2.0935 | 1.2922 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 7 | 6 |
| `map_bin.abs_y_bin` | 3 | 2 |
| `fiducial.passed` | FAIL | FAIL |
| `fiducial.daughters[0].gen_idx` | 10 | 5 |
| `fiducial.daughters[0].pt` | 1.7564 | 1.9357 |
| `fiducial.daughters[0].eta` | 1.4136 | 1.9195 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | FAIL | FAIL |
| `fiducial.daughters[1].gen_idx` | 11 | 6 |
| `fiducial.daughters[1].pt` | 5.6163 | 7.164 |
| `fiducial.daughters[1].eta` | 2.3221 | 1.1127 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 10 | 5 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 2 | 4 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 2 | 4 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 2 | 4 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 11 | 6 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 1 | 1 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 1 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 1 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].muIsPatSoftMuon` | PASS | PASS |

### `jpsi_sublead / muonRECO / numerator`

| Field | Event 1<br>`entry 13` | Event 2<br>`entry 17` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 13 | 17 |
| `identity.run:lumi:event` | 1:1:141 | 1:1:206 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | PASS | PASS |
| `GEN.idx` | 4 | 6 |
| `GEN.pt` | 8.6864 | 9.5224 |
| `GEN.eta` | -0.058591 | -0.57407 |
| `GEN.y` | -0.055194 | -0.5485 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 7, 8 | 8, 9 |
| `map_bin.pt` | 8.6864 | 9.5224 |
| `map_bin.y` | -0.055194 | -0.5485 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 3 | 3 |
| `map_bin.abs_y_bin` | 0 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 7 | 8 |
| `fiducial.daughters[0].pt` | 4.7718 | 4.7378 |
| `fiducial.daughters[0].eta` | 0.11172 | -0.86896 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 8 | 9 |
| `fiducial.daughters[1].pt` | 4.3071 | 4.785 |
| `fiducial.daughters[1].eta` | -0.23995 | -0.23133 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 7 | 8 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 2 | 3 |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 8 | 9 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 3 | 2 |

### `jpsi_sublead / muonRECO / rejected`

| Field | Event 1<br>`entry 9` | Event 2<br>`entry 14` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source1_35events.root |
| `identity.entry` | 9 | 14 |
| `identity.run:lumi:event` | 1:1:98 | 1:1:1778 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.muonRECO` | FAIL | FAIL |
| `GEN.idx` | 5 | 16 |
| `GEN.pt` | 7.4496 | 6.8144 |
| `GEN.eta` | 0.98916 | 1.3537 |
| `GEN.y` | 0.9299 | 1.2725 |
| `GEN.mass` | 3.096 | 3.0969 |
| `GEN.daughter_indices` | 6, 7 | 17, 18 |
| `map_bin.pt` | 7.4496 | 6.8144 |
| `map_bin.y` | 0.9299 | 1.2725 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 5 | 6 |
| `map_bin.abs_y_bin` | 1 | 2 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 6 | 17 |
| `fiducial.daughters[0].pt` | 3.6601 | 3.8926 |
| `fiducial.daughters[0].eta` | 1.0016 | 1.2121 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 7 | 18 |
| `fiducial.daughters[1].pt` | 4.3872 | 3.5744 |
| `fiducial.daughters[1].eta` | 0.87054 | 1.3391 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | FAIL | FAIL |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 6 | 17 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | [] | [] |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 7 | 18 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 1 | 3 |

### `jpsi_sublead / muonRECO / raw_only`

| Field | Event 1<br>`entry 23` | Event 2<br>`entry 24` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 23 | 24 |
| `identity.run:lumi:event` | 1:1:351 | 1:1:356 |
| `selection.role` | raw_only | raw_only |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | FAIL | FAIL |
| `flags.muonRECO` | PASS | PASS |
| `GEN.idx` | 9 | 4 |
| `GEN.pt` | 7.3211 | 9.0992 |
| `GEN.eta` | 2.1735 | 1.3396 |
| `GEN.y` | 2.0935 | 1.2922 |
| `GEN.mass` | 3.096 | 3.096 |
| `GEN.daughter_indices` | 10, 11 | 5, 6 |
| `map_bin.pt` | 7.3211 | 9.0992 |
| `map_bin.y` | 2.0935 | 1.2922 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 7 | 6 |
| `map_bin.abs_y_bin` | 3 | 2 |
| `fiducial.passed` | FAIL | FAIL |
| `fiducial.daughters[0].gen_idx` | 10 | 5 |
| `fiducial.daughters[0].pt` | 1.7564 | 1.9357 |
| `fiducial.daughters[0].eta` | 1.4136 | 1.9195 |
| `fiducial.daughters[0].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[0].passed` | FAIL | FAIL |
| `fiducial.daughters[1].gen_idx` | 11 | 6 |
| `fiducial.daughters[1].pt` | 5.6163 | 7.164 |
| `fiducial.daughters[1].eta` | 2.3221 | 1.1127 |
| `fiducial.daughters[1].criterion` | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 | \|eta\|<1.2 && pt>3.5, or 1.2<=\|eta\|<2.4 && pt>2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 10 | 5 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 2 | 4 |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 11 | 6 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 1 | 1 |

### `phi / dikaon / numerator`

| Field | Event 1<br>`entry 1` | Event 2<br>`entry 5` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 1 | 5 |
| `identity.run:lumi:event` | 1:1:6 | 1:1:37 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.kaonRECO` | PASS | PASS |
| `flags.kaonID` | PASS | PASS |
| `flags.dikaon` | PASS | PASS |
| `GEN.idx` | 8 | 13 |
| `GEN.pt` | 5.078 | 5.7209 |
| `GEN.eta` | -0.81548 | -0.030443 |
| `GEN.y` | -0.80259 | -0.029974 |
| `GEN.mass` | 1.0062 | 1.0169 |
| `GEN.daughter_indices` | 10, 11 | 15, 16 |
| `map_bin.pt` | 5.078 | 5.7209 |
| `map_bin.y` | -0.80259 | -0.029974 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 2 | 3 |
| `map_bin.abs_y_bin` | 1 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 10 | 15 |
| `fiducial.daughters[0].pt` | 2.4979 | 2.181 |
| `fiducial.daughters[0].eta` | -0.85311 | -0.038662 |
| `fiducial.daughters[0].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 11 | 16 |
| `fiducial.daughters[1].pt` | 2.5801 | 3.54 |
| `fiducial.daughters[1].eta` | -0.77807 | -0.025378 |
| `fiducial.daughters[1].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 10 | 15 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 5 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 1 | 5 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 1 | 5 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].normalizedChi2` | 1 | 1 |
| `reconstruction_and_id.daughters[0].reco_objects[0].numberOfHits` | 20 | 15 |
| `reconstruction_and_id.daughters[0].reco_objects[0].isHighPurity` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 11 | 16 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 0 | 4 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 0 | 4 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 0 | 4 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].normalizedChi2` | 0 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].numberOfHits` | 19 | 18 |
| `reconstruction_and_id.daughters[1].reco_objects[0].isHighPurity` | PASS | PASS |
| `single_candidates[0].candidate_idx` | 0 | 2 |
| `single_candidates[0].ancestor_1` | 8 | 13 |
| `single_candidates[0].ancestor_2` | 8 | 13 |
| `single_candidates[0].same_target_parent` | PASS | PASS |
| `single_candidates[0].mass` | 1.0055 | 1.0161 |
| `single_candidates[0].pt` | 4.9999 | 5.7402 |
| `single_candidates[0].y` | -0.80346 | -0.030056 |
| `single_candidates[0].VtxProb` | 0.21167 | 0.025986 |
| `single_candidates[0].fitValid` | PASS | PASS |
| `single_candidates[0].fitPass` | PASS | PASS |
| `single_candidates[0].quality_passed` | PASS | PASS |
| `single_candidates[0].witness` | PASS | PASS |

### `phi / dikaon / rejected`

| Field | Event 1<br>`entry 4` | Event 2<br>`entry 7` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 4 | 7 |
| `identity.run:lumi:event` | 1:1:33 | 1:1:85 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.kaonRECO` | PASS | PASS |
| `flags.kaonID` | PASS | PASS |
| `flags.dikaon` | FAIL | FAIL |
| `GEN.idx` | 7 | 12 |
| `GEN.pt` | 4.7788 | 5.4147 |
| `GEN.eta` | -0.0045155 | -0.78808 |
| `GEN.y` | -0.0044174 | -0.77665 |
| `GEN.mass` | 1.0128 | 1.0214 |
| `GEN.daughter_indices` | 9, 10 | 14, 15 |
| `map_bin.pt` | 4.7788 | 5.4147 |
| `map_bin.y` | -0.0044174 | -0.77665 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 3 | 2 |
| `map_bin.abs_y_bin` | 0 | 1 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 9 | 14 |
| `fiducial.daughters[0].pt` | 2.5898 | 3.1825 |
| `fiducial.daughters[0].eta` | -0.0083008 | -0.76446 |
| `fiducial.daughters[0].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 10 | 15 |
| `fiducial.daughters[1].pt` | 2.1936 | 2.2342 |
| `fiducial.daughters[1].eta` | -3.6959e-05 | -0.82053 |
| `fiducial.daughters[1].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 9 | 14 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 0 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 1 | 0 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 1 | 0 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].normalizedChi2` | 1 | 0 |
| `reconstruction_and_id.daughters[0].reco_objects[0].numberOfHits` | 18 | 16 |
| `reconstruction_and_id.daughters[0].reco_objects[0].isHighPurity` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 10 | 15 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 0 | 1 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 0 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 0 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].normalizedChi2` | 1 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].numberOfHits` | 13 | 16 |
| `reconstruction_and_id.daughters[1].reco_objects[0].isHighPurity` | PASS | PASS |
| `single_candidates` | [] | [] |

### `phi / dikaon / raw_only`

| Field | Event 1<br>`entry 0` | Event 2<br>`entry 2` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 0 | 2 |
| `identity.run:lumi:event` | 1:1:1 | 1:1:11 |
| `selection.role` | raw_only | raw_only |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | FAIL | FAIL |
| `flags.kaonRECO` | PASS | PASS |
| `flags.kaonID` | PASS | PASS |
| `flags.dikaon` | PASS | PASS |
| `GEN.idx` | 11 | 19 |
| `GEN.pt` | 4.1767 | 4.3037 |
| `GEN.eta` | -1.3145 | -1.4425 |
| `GEN.y` | -1.2892 | -1.4185 |
| `GEN.mass` | 1.0259 | 1.012 |
| `GEN.daughter_indices` | 15, 16 | 21, 22 |
| `map_bin.pt` | 4.1767 | 4.3037 |
| `map_bin.y` | -1.2892 | -1.4185 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 1 | 1 |
| `map_bin.abs_y_bin` | 2 | 2 |
| `fiducial.passed` | FAIL | FAIL |
| `fiducial.daughters[0].gen_idx` | 15 | 21 |
| `fiducial.daughters[0].pt` | 1.6488 | 2.3611 |
| `fiducial.daughters[0].eta` | -1.3279 | -1.4583 |
| `fiducial.daughters[0].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[0].passed` | FAIL | PASS |
| `fiducial.daughters[1].gen_idx` | 16 | 22 |
| `fiducial.daughters[1].pt` | 2.5321 | 1.9461 |
| `fiducial.daughters[1].eta` | -1.3042 | -1.4214 |
| `fiducial.daughters[1].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[1].passed` | PASS | FAIL |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 15 | 21 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 1 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 1 | 1 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 1 | 1 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].normalizedChi2` | 0 | 1 |
| `reconstruction_and_id.daughters[0].reco_objects[0].numberOfHits` | 16 | 16 |
| `reconstruction_and_id.daughters[0].reco_objects[0].isHighPurity` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 16 | 22 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 0 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].normalizedChi2` | 0 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].numberOfHits` | 16 | 19 |
| `reconstruction_and_id.daughters[1].reco_objects[0].isHighPurity` | PASS | PASS |
| `single_candidates[0].candidate_idx` | 0 | 0 |
| `single_candidates[0].ancestor_1` | 11 | 19 |
| `single_candidates[0].ancestor_2` | 11 | 19 |
| `single_candidates[0].same_target_parent` | PASS | PASS |
| `single_candidates[0].mass` | 1.0259 | 1.0149 |
| `single_candidates[0].pt` | 4.1544 | 4.3367 |
| `single_candidates[0].y` | -1.2892 | -1.4194 |
| `single_candidates[0].VtxProb` | 0.37299 | 0.16619 |
| `single_candidates[0].fitValid` | PASS | PASS |
| `single_candidates[0].fitPass` | PASS | PASS |
| `single_candidates[0].quality_passed` | PASS | PASS |
| `single_candidates[0].witness` | PASS | PASS |

### `phi / fiducial / numerator`

| Field | Event 1<br>`entry 1` | Event 2<br>`entry 4` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 1 | 4 |
| `identity.run:lumi:event` | 1:1:6 | 1:1:33 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `GEN.idx` | 8 | 7 |
| `GEN.pt` | 5.078 | 4.7788 |
| `GEN.eta` | -0.81548 | -0.0045155 |
| `GEN.y` | -0.80259 | -0.0044174 |
| `GEN.mass` | 1.0062 | 1.0128 |
| `GEN.daughter_indices` | 10, 11 | 9, 10 |
| `map_bin.pt` | 5.078 | 4.7788 |
| `map_bin.y` | -0.80259 | -0.0044174 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 2 | 3 |
| `map_bin.abs_y_bin` | 1 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 10 | 9 |
| `fiducial.daughters[0].pt` | 2.4979 | 2.5898 |
| `fiducial.daughters[0].eta` | -0.85311 | -0.0083008 |
| `fiducial.daughters[0].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 11 | 10 |
| `fiducial.daughters[1].pt` | 2.5801 | 2.1936 |
| `fiducial.daughters[1].eta` | -0.77807 | -3.6959e-05 |
| `fiducial.daughters[1].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |

### `phi / fiducial / rejected`

| Field | Event 1<br>`entry 0` | Event 2<br>`entry 2` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 0 | 2 |
| `identity.run:lumi:event` | 1:1:1 | 1:1:11 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | FAIL | FAIL |
| `GEN.idx` | 11 | 19 |
| `GEN.pt` | 4.1767 | 4.3037 |
| `GEN.eta` | -1.3145 | -1.4425 |
| `GEN.y` | -1.2892 | -1.4185 |
| `GEN.mass` | 1.0259 | 1.012 |
| `GEN.daughter_indices` | 15, 16 | 21, 22 |
| `map_bin.pt` | 4.1767 | 4.3037 |
| `map_bin.y` | -1.2892 | -1.4185 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 1 | 1 |
| `map_bin.abs_y_bin` | 2 | 2 |
| `fiducial.passed` | FAIL | FAIL |
| `fiducial.daughters[0].gen_idx` | 15 | 21 |
| `fiducial.daughters[0].pt` | 1.6488 | 2.3611 |
| `fiducial.daughters[0].eta` | -1.3279 | -1.4583 |
| `fiducial.daughters[0].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[0].passed` | FAIL | PASS |
| `fiducial.daughters[1].gen_idx` | 16 | 22 |
| `fiducial.daughters[1].pt` | 2.5321 | 1.9461 |
| `fiducial.daughters[1].eta` | -1.3042 | -1.4214 |
| `fiducial.daughters[1].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[1].passed` | PASS | FAIL |

### `phi / kaonID / numerator`

| Field | Event 1<br>`entry 1` | Event 2<br>`entry 4` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 1 | 4 |
| `identity.run:lumi:event` | 1:1:6 | 1:1:33 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.kaonRECO` | PASS | PASS |
| `flags.kaonID` | PASS | PASS |
| `GEN.idx` | 8 | 7 |
| `GEN.pt` | 5.078 | 4.7788 |
| `GEN.eta` | -0.81548 | -0.0045155 |
| `GEN.y` | -0.80259 | -0.0044174 |
| `GEN.mass` | 1.0062 | 1.0128 |
| `GEN.daughter_indices` | 10, 11 | 9, 10 |
| `map_bin.pt` | 5.078 | 4.7788 |
| `map_bin.y` | -0.80259 | -0.0044174 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 2 | 3 |
| `map_bin.abs_y_bin` | 1 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 10 | 9 |
| `fiducial.daughters[0].pt` | 2.4979 | 2.5898 |
| `fiducial.daughters[0].eta` | -0.85311 | -0.0083008 |
| `fiducial.daughters[0].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 11 | 10 |
| `fiducial.daughters[1].pt` | 2.5801 | 2.1936 |
| `fiducial.daughters[1].eta` | -0.77807 | -3.6959e-05 |
| `fiducial.daughters[1].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 10 | 9 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 1 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 1 | 1 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 1 | 1 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].normalizedChi2` | 1 | 1 |
| `reconstruction_and_id.daughters[0].reco_objects[0].numberOfHits` | 20 | 18 |
| `reconstruction_and_id.daughters[0].reco_objects[0].isHighPurity` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 11 | 10 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 0 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].normalizedChi2` | 0 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].numberOfHits` | 19 | 13 |
| `reconstruction_and_id.daughters[1].reco_objects[0].isHighPurity` | PASS | PASS |

### `phi / kaonID / rejected`

| Field | Event 1<br>`entry 26` | Event 2<br>`entry 34` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 26 | 34 |
| `identity.run:lumi:event` | 1:1:373 | 1:1:696 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.kaonRECO` | PASS | PASS |
| `flags.kaonID` | FAIL | FAIL |
| `GEN.idx` | 15 | 8 |
| `GEN.pt` | 4.5159 | 5.2389 |
| `GEN.eta` | -1.1097 | 0.31278 |
| `GEN.y` | -1.0899 | 0.30721 |
| `GEN.mass` | 1.0177 | 1.0182 |
| `GEN.daughter_indices` | 17, 18 | 10, 11 |
| `map_bin.pt` | 4.5159 | 5.2389 |
| `map_bin.y` | -1.0899 | 0.30721 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 2 | 4 |
| `map_bin.abs_y_bin` | 1 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 17 | 10 |
| `fiducial.daughters[0].pt` | 2.3154 | 3.2202 |
| `fiducial.daughters[0].eta` | -1.0803 | 0.32266 |
| `fiducial.daughters[0].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 18 | 11 |
| `fiducial.daughters[1].pt` | 2.2053 | 2.0191 |
| `fiducial.daughters[1].eta` | -1.1381 | 0.29692 |
| `fiducial.daughters[1].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | FAIL | FAIL |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 17 | 10 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 3 | 0 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 3 | [] |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 3 | 0 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | FAIL |
| `reconstruction_and_id.daughters[0].reco_objects[0].normalizedChi2` | 0 | 0 |
| `reconstruction_and_id.daughters[0].reco_objects[0].numberOfHits` | 10 | 4 |
| `reconstruction_and_id.daughters[0].reco_objects[0].isHighPurity` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 18 | 11 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 4 | 1 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | [] | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 4 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | FAIL | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].normalizedChi2` | 16 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].numberOfHits` | 14 | 16 |
| `reconstruction_and_id.daughters[1].reco_objects[0].isHighPurity` | PASS | PASS |

### `phi / kaonID / raw_only`

| Field | Event 1<br>`entry 0` | Event 2<br>`entry 2` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 0 | 2 |
| `identity.run:lumi:event` | 1:1:1 | 1:1:11 |
| `selection.role` | raw_only | raw_only |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | FAIL | FAIL |
| `flags.kaonRECO` | PASS | PASS |
| `flags.kaonID` | PASS | PASS |
| `GEN.idx` | 11 | 19 |
| `GEN.pt` | 4.1767 | 4.3037 |
| `GEN.eta` | -1.3145 | -1.4425 |
| `GEN.y` | -1.2892 | -1.4185 |
| `GEN.mass` | 1.0259 | 1.012 |
| `GEN.daughter_indices` | 15, 16 | 21, 22 |
| `map_bin.pt` | 4.1767 | 4.3037 |
| `map_bin.y` | -1.2892 | -1.4185 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 1 | 1 |
| `map_bin.abs_y_bin` | 2 | 2 |
| `fiducial.passed` | FAIL | FAIL |
| `fiducial.daughters[0].gen_idx` | 15 | 21 |
| `fiducial.daughters[0].pt` | 1.6488 | 2.3611 |
| `fiducial.daughters[0].eta` | -1.3279 | -1.4583 |
| `fiducial.daughters[0].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[0].passed` | FAIL | PASS |
| `fiducial.daughters[1].gen_idx` | 16 | 22 |
| `fiducial.daughters[1].pt` | 2.5321 | 1.9461 |
| `fiducial.daughters[1].eta` | -1.3042 | -1.4214 |
| `fiducial.daughters[1].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[1].passed` | PASS | FAIL |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.id_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 15 | 21 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 1 |
| `reconstruction_and_id.daughters[0].quality_matched_reco_indices` | 1 | 1 |
| `reconstruction_and_id.daughters[0].reco_objects[0].reco_idx` | 1 | 1 |
| `reconstruction_and_id.daughters[0].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].reco_objects[0].normalizedChi2` | 0 | 1 |
| `reconstruction_and_id.daughters[0].reco_objects[0].numberOfHits` | 16 | 16 |
| `reconstruction_and_id.daughters[0].reco_objects[0].isHighPurity` | PASS | PASS |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 16 | 22 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].quality_matched_reco_indices` | 0 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].reco_idx` | 0 | 0 |
| `reconstruction_and_id.daughters[1].reco_objects[0].quality_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[1].reco_objects[0].normalizedChi2` | 0 | 1 |
| `reconstruction_and_id.daughters[1].reco_objects[0].numberOfHits` | 16 | 19 |
| `reconstruction_and_id.daughters[1].reco_objects[0].isHighPurity` | PASS | PASS |

### `phi / kaonRECO / numerator`

| Field | Event 1<br>`entry 1` | Event 2<br>`entry 4` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 1 | 4 |
| `identity.run:lumi:event` | 1:1:6 | 1:1:33 |
| `selection.role` | numerator | numerator |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.kaonRECO` | PASS | PASS |
| `GEN.idx` | 8 | 7 |
| `GEN.pt` | 5.078 | 4.7788 |
| `GEN.eta` | -0.81548 | -0.0045155 |
| `GEN.y` | -0.80259 | -0.0044174 |
| `GEN.mass` | 1.0062 | 1.0128 |
| `GEN.daughter_indices` | 10, 11 | 9, 10 |
| `map_bin.pt` | 5.078 | 4.7788 |
| `map_bin.y` | -0.80259 | -0.0044174 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 2 | 3 |
| `map_bin.abs_y_bin` | 1 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 10 | 9 |
| `fiducial.daughters[0].pt` | 2.4979 | 2.5898 |
| `fiducial.daughters[0].eta` | -0.85311 | -0.0083008 |
| `fiducial.daughters[0].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 11 | 10 |
| `fiducial.daughters[1].pt` | 2.5801 | 2.1936 |
| `fiducial.daughters[1].eta` | -0.77807 | -3.6959e-05 |
| `fiducial.daughters[1].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 10 | 9 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 1 |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 11 | 10 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 0 | 0 |

### `phi / kaonRECO / rejected`

| Field | Event 1<br>`entry 12` | Event 2<br>`entry 28` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 12 | 28 |
| `identity.run:lumi:event` | 1:1:135 | 1:1:397 |
| `selection.role` | rejected | rejected |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | PASS | PASS |
| `flags.kaonRECO` | FAIL | FAIL |
| `GEN.idx` | 11 | 10 |
| `GEN.pt` | 5.3569 | 4.6211 |
| `GEN.eta` | 0.095659 | 0.30743 |
| `GEN.y` | 0.093963 | 0.30038 |
| `GEN.mass` | 1.024 | 1.0231 |
| `GEN.daughter_indices` | 13, 14 | 14, 15 |
| `map_bin.pt` | 5.3569 | 4.6211 |
| `map_bin.y` | 0.093963 | 0.30038 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 4 | 4 |
| `map_bin.abs_y_bin` | 0 | 0 |
| `fiducial.passed` | PASS | PASS |
| `fiducial.daughters[0].gen_idx` | 13 | 14 |
| `fiducial.daughters[0].pt` | 2.5984 | 2.5981 |
| `fiducial.daughters[0].eta` | 0.13943 | 0.30339 |
| `fiducial.daughters[0].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[0].passed` | PASS | PASS |
| `fiducial.daughters[1].gen_idx` | 14 | 15 |
| `fiducial.daughters[1].pt` | 2.7605 | 2.0292 |
| `fiducial.daughters[1].eta` | 0.054218 | 0.31169 |
| `fiducial.daughters[1].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[1].passed` | PASS | PASS |
| `reconstruction_and_id.reco_passed` | FAIL | FAIL |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 13 | 14 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 5 |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 14 | 15 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | [] | [] |

### `phi / kaonRECO / raw_only`

| Field | Event 1<br>`entry 0` | Event 2<br>`entry 2` |
|---|---:|---:|
| `identity.source` | jjp_dps_patch2_pre2_runb_audit_source0_45events.root | jjp_dps_patch2_pre2_runb_audit_source0_45events.root |
| `identity.entry` | 0 | 2 |
| `identity.run:lumi:event` | 1:1:1 | 1:1:11 |
| `selection.role` | raw_only | raw_only |
| `flags.full_gen` | PASS | PASS |
| `flags.fiducial` | FAIL | FAIL |
| `flags.kaonRECO` | PASS | PASS |
| `GEN.idx` | 11 | 19 |
| `GEN.pt` | 4.1767 | 4.3037 |
| `GEN.eta` | -1.3145 | -1.4425 |
| `GEN.y` | -1.2892 | -1.4185 |
| `GEN.mass` | 1.0259 | 1.012 |
| `GEN.daughter_indices` | 15, 16 | 21, 22 |
| `map_bin.pt` | 4.1767 | 4.3037 |
| `map_bin.y` | -1.2892 | -1.4185 |
| `map_bin.pt_bin` | 0 | 0 |
| `map_bin.signed_y_bin` | 1 | 1 |
| `map_bin.abs_y_bin` | 2 | 2 |
| `fiducial.passed` | FAIL | FAIL |
| `fiducial.daughters[0].gen_idx` | 15 | 21 |
| `fiducial.daughters[0].pt` | 1.6488 | 2.3611 |
| `fiducial.daughters[0].eta` | -1.3279 | -1.4583 |
| `fiducial.daughters[0].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[0].passed` | FAIL | PASS |
| `fiducial.daughters[1].gen_idx` | 16 | 22 |
| `fiducial.daughters[1].pt` | 2.5321 | 1.9461 |
| `fiducial.daughters[1].eta` | -1.3042 | -1.4214 |
| `fiducial.daughters[1].criterion` | pt>2.0 && \|eta\|<2.5 | pt>2.0 && \|eta\|<2.5 |
| `fiducial.daughters[1].passed` | PASS | FAIL |
| `reconstruction_and_id.reco_passed` | PASS | PASS |
| `reconstruction_and_id.daughters[0].gen_daughter_idx` | 15 | 21 |
| `reconstruction_and_id.daughters[0].matched_reco_indices` | 1 | 1 |
| `reconstruction_and_id.daughters[1].gen_daughter_idx` | 16 | 22 |
| `reconstruction_and_id.daughters[1].matched_reco_indices` | 0 | 0 |

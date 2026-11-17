import json
from pathlib import Path
import numpy as np
import pytest
from ntuple_analyzer.adapters.normalization import normalize, CLASS_ORDER
from ntuple_analyzer.adapters.efficiency import execute, stage_spec


def fixture():
    contract = dict(selection_id='selected-v1', endpoint='Pri_assocPVPass', gen_denominator='generated-events-v1',
                    class_order=CLASS_ORDER, generated_totals=[100] * 6, axes=['pt', 'abs_y'], folding='abs_y',
                    uncertainty_scope='joint supplied blocks')
    covariance = np.eye(6) + np.ones((6, 6)) * .1
    fit = dict(status='accepted', class_order=CLASS_ORDER, class_yields=[10] * 6,
               class_covariance=covariance.tolist(), contract=contract, total_yield=60,
               total_variance=float(covariance.sum()))
    bridge = dict(fit_contract=contract.copy(), map_contract=contract.copy(), efficiencies=[.5] * 6,
                  numerators=[[25]] * 6, denominators=[[50]] * 6,
                  efficiency_covariance=np.zeros((6, 6)).tolist(), count_covariance=np.zeros((12, 12)).tolist(),
                  luminosity=2, luminosity_variance=.04, branching_fractions=[.5] * 6,
                  branching_covariance=(np.ones((6, 6)) * .0025).tolist(), scope='test-inclusive',
                  covariance_assumptions={k: 'explicit test independence' for k in ('yield_efficiency', 'efficiency_counts', 'yield_counts', 'normalization_inputs')})
    return fit, bridge


def test_correlated_normalization():
    fit, bridge = fixture()
    result = normalize(fit, bridge)
    cross = result['cross_sections']
    np.testing.assert_allclose(cross['cross_sections'], [20] * 6)
    expected = 4 * np.asarray(fit['class_covariance']) + np.ones((6, 6)) * 8
    np.testing.assert_allclose(cross['covariance'], expected, rtol=1e-8)
    assert cross['total_variance'] == pytest.approx(expected.sum())
    np.testing.assert_allclose(result['mixed_efficiency']['physical_class_weights'], [.2] * 6)


@pytest.mark.parametrize('field', ['selection_id', 'endpoint', 'gen_denominator', 'folding', 'uncertainty_scope'])
def test_mismatch_refused(field):
    fit, bridge = fixture()
    bridge['map_contract'][field] = 'different'
    with pytest.raises(ValueError, match='compatibility mismatch'):
        normalize(fit, bridge)


def test_rejected_fit_refused():
    fit, bridge = fixture()
    fit['status'] = 'partial'
    with pytest.raises(ValueError, match='accepted fit'):
        normalize(fit, bridge)


def test_validation_preserves_failed_closure(tmp_path):
    artifact = tmp_path / 'closure.json'
    artifact.write_text(json.dumps(dict(status='accepted', numerical_acceptance=True, closure_passed=False)))
    cfg = dict(channel='JJP', validation={'artifacts': [{'path': str(artifact), 'kind': 'closure'}]})
    assert stage_spec('validation', cfg, tmp_path)['dependencies'] == []
    result = execute('validation', cfg, tmp_path, tmp_path / 'output')
    assert result['status'] == 'rejected'
    assert result['diagnostics'][0]['numerical_acceptance'] is True
    assert not (tmp_path / 'output/.complete.json').exists()


def test_external_efficiency_no_raw_scan_dependency(tmp_path):
    cfg = {'inputs': {'efficiency_products': str(tmp_path)}}
    assert stage_spec('acceptance', cfg, tmp_path)['dependencies'] == []


def test_no_implicit_eos_discovery(tmp_path):
    with pytest.raises(ValueError, match='implicit EOS discovery disabled'):
        execute('efficiency', {'channel': 'JJP'}, tmp_path, tmp_path / 'out')


def test_production_count_export(tmp_path):
    import pandas as pd
    from ntuple_analyzer.adapters.normalization import export_counts
    fit, bridge = fixture()
    sources = []
    selector = {'column': 'full_gen', 'definition': 'Synthetic full generated event population v1'}
    bridge['map_contract']['gen_selector'] = selector
    bridge['fit_contract']['gen_selector'] = selector
    fit['contract']['gen_selector'] = selector
    for name in CLASS_ORDER:
        sample = tmp_path / name
        sample.mkdir()
        (sample / 'gen_definition.json').write_text(json.dumps({'gen_selector': selector}))
        pd.DataFrame({'full_gen': [True] * 100, 'Pri_assocPVPass': [True] * 50 + [False] * 50}).to_parquet(sample / 'event_step_flags.parquet')
        pd.DataFrame({'fallback_level': ['inclusive'], 'passed': [25], 'total': [50]}).to_parquet(sample / 'map.parquet')
        sources.append({'class': name, 'sample': name, 'gen_column': 'full_gen', 'gen_definition_file': 'gen_definition.json', 'endpoint_column': 'Pri_assocPVPass',
                        'map_rows': [{'file': 'map.parquet', 'filters': {'fallback_level': 'inclusive'}}]})
    bridge['production_count_sources'] = sources
    exported = export_counts(bridge, tmp_path)
    assert exported['efficiencies'] == [.5] * 6
    assert len(exported['count_source_provenance']) == 18
    pd.DataFrame({'fallback_level': ['different'], 'passed': [25], 'total': [50]}).to_parquet(tmp_path / CLASS_ORDER[-1] / 'map.parquet')
    sources[-1]['map_rows'][0]['filters'] = {'fallback_level': 'different'}
    with pytest.raises(ValueError, match='row identities differ'):
        export_counts(bridge, tmp_path)
    pd.DataFrame({'fallback_level': ['inclusive'], 'passed': [25], 'total': [50]}).to_parquet(tmp_path / CLASS_ORDER[-1] / 'map.parquet')
    sources[-1]['map_rows'][0]['filters'] = {'fallback_level': 'inclusive'}
    bridge['map_contract']['generated_totals'] = [101] * 6
    with pytest.raises(ValueError, match='GEN exposures'):
        export_counts(bridge, tmp_path)


def test_independent_run_calculation(monkeypatch, tmp_path):
    from ntuple_analyzer.adapters import efficiency
    calls = []
    def calculate(manifest, cfg, destination):
        calls.append((manifest, cfg['config'], destination.name))
        destination.mkdir(parents=True)
        (destination / 'calculated.json').write_text('{}')
    monkeypatch.setattr(efficiency, '_calculate', calculate)
    cfg = {'channel': 'JJP', 'inputs': {'efficiency_run_a_manifest': '/a.json', 'efficiency_run_b_manifest': '/b.json'},
           'efficiency': {'config': '/nominal.yaml', 'run_a': {'config': '/singles.yaml'}}}
    result = execute('efficiency', cfg, tmp_path, tmp_path / 'out')
    assert result['independent_runs'] == ['a', 'b']
    assert calls == [('/a.json', '/singles.yaml', 'run_a'), ('/b.json', '/nominal.yaml', 'run_b')]


@pytest.mark.parametrize('status,quality,edm,error,accepted', [(0,3,1e-5,1.,True),(1,3,1e-5,1.,False),(0,2,1e-5,1.,False),(0,3,float('nan'),1.,False),(0,3,.01,1.,False),(0,3,1e-5,0.,False)])
def test_legacy_yield_fit_numerical_gate(monkeypatch, status, quality, edm, error, accepted):
    import types
    import sys
    from efficiency_workflow.yield_correction import run_weighted_yield_fit
    result = types.SimpleNamespace(status=lambda: status, covQual=lambda: quality, edm=lambda: edm)
    module = types.SimpleNamespace(run_jjp_fit=lambda *a, **k: {'fit_result': result, 'yield': 10., 'yield_err': error, 'fit_nll': 5., 'n_events': 20})
    monkeypatch.setitem(sys.modules, 'fit_splot', module)
    if accepted:
        assert run_weighted_yield_fit('unused.root') == (10., 1., 5., 20)
    else:
        with pytest.raises(RuntimeError, match='Unreliable yield correction fit'):
            run_weighted_yield_fit('unused.root')

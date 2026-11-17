"""Explicit selection-matched scalar bridge to six-source normalization."""
from __future__ import annotations

CLASS_ORDER = ['DPS1', 'DPS2_CS', 'DPS2_G', 'SPS_CS', 'SPS_G', 'TPS']
CONTRACT_FIELDS = ('selection_id', 'endpoint', 'gen_denominator', 'class_order',
                   'generated_totals', 'axes', 'folding', 'uncertainty_scope')


def normalize(fit: dict, bridge: dict) -> dict:
    """Require accepted fit and matching contracts; propagate supplied covariance."""
    import numpy as np
    from scripts.templates.mass_classifier_normalization import (
        build_mixed_efficiency_maps, compute_cross_sections,
    )
    if fit.get('status') != 'accepted':
        raise ValueError('Correction requires an explicitly accepted fit')
    left, right = bridge['fit_contract'], bridge['map_contract']
    for field in CONTRACT_FIELDS:
        if field not in left or field not in right or left[field] != right[field]:
            raise ValueError(f'Efficiency compatibility mismatch or missing field: {field}')
        if left[field] is None or left[field] == '' or left[field] == []:
            raise ValueError(f'Empty efficiency compatibility field: {field}')
    if left['class_order'] != CLASS_ORDER:
        raise ValueError('Bridge requires canonical six-class order')
    if left['axes'] not in (['pt', 'signed_y'], ['pt', 'abs_y']):
        raise ValueError('Declare pt/signed_y or pt/abs_y axes')
    if left['axes'][1] == 'abs_y' and left['folding'] != 'abs_y':
        raise ValueError('abs_y maps require explicit abs_y folding')
    if left['axes'][1] == 'signed_y' and left['folding'] != 'none':
        raise ValueError('signed_y maps must declare no folding')
    if fit.get('contract') != left:
        raise ValueError('Fit artifact contract differs from bridge fit_contract')
    n = np.asarray(fit['class_yields'], float)
    cov = np.asarray(fit['class_covariance'], float)
    if n.shape != (6,) or cov.shape != (6, 6):
        raise ValueError('Six yields and full 6x6 covariance required')
    if fit.get('class_order') != CLASS_ORDER:
        raise ValueError('Fit class order mismatch')
    if 'total_yield' in fit and not np.isclose(n.sum(), fit['total_yield']):
        raise ValueError('Fit total yield mismatch')
    if 'total_variance' in fit and not np.isclose(cov.sum(), fit['total_variance']):
        raise ValueError('Fit total variance mismatch')
    for key in ('efficiency_covariance', 'count_covariance', 'luminosity_variance',
                'branching_covariance', 'luminosity', 'branching_fractions', 'scope'):
        if key not in bridge:
            raise ValueError(f'Explicit normalization input required: {key}')
    if not (bridge.get('mixing_joint_covariance') is not None and
            bridge.get('cross_section_joint_covariance') is not None):
        assumptions = bridge.get('covariance_assumptions', {})
        for key in ('yield_efficiency', 'efficiency_counts', 'yield_counts', 'normalization_inputs'):
            if not isinstance(assumptions.get(key), str) or not assumptions[key].strip():
                raise ValueError(f'Explicit omitted cross-covariance assumption required: {key}')
    mixed = build_mixed_efficiency_maps(
        bridge['numerators'], bridge['denominators'], n, bridge['efficiencies'],
        generated_totals=left['generated_totals'], selection_id=left['selection_id'],
        map_selection_id=right['selection_id'], class_covariance=cov,
        efficiency_covariance=bridge['efficiency_covariance'], count_covariance=bridge['count_covariance'],
        joint_covariance=bridge.get('mixing_joint_covariance'))
    cross = compute_cross_sections(
        n, bridge['efficiencies'], bridge['luminosity'], bridge['branching_fractions'],
        class_covariance=cov, efficiency_covariance=bridge['efficiency_covariance'],
        luminosity_variance=bridge['luminosity_variance'], branching_covariance=bridge['branching_covariance'],
        joint_covariance=bridge.get('cross_section_joint_covariance'), scope=bridge['scope'])
    return {'status': 'accepted', 'mixed_efficiency': mixed, 'cross_sections': cross,
            'compatibility': left, 'uncertainty_scope': left['uncertainty_scope'],
            'covariance_assumptions': bridge.get('covariance_assumptions', {})}


def export_counts(bridge: dict, products_dir) -> dict:
    """Resolve declared map rows and scalar efficiencies from persisted MC counts.

    No inference of selection identity or independence is made from file names.
    Each source names its sample, event denominator/endpoint, and ordered map rows.
    Covariances remain explicit caller inputs, including count/efficiency overlap.
    """
    from pathlib import Path
    import pandas as pd
    import numpy as np
    result = dict(bridge)
    sources = bridge.get('production_count_sources')
    if not sources:
        return result
    if len(sources) != 6 or [s['class'] for s in sources] != CLASS_ORDER:
        raise ValueError('Production count sources require canonical six-class ordering')
    numerators, denominators, efficiencies, exposures, provenance = [], [], [], [], []
    row_signatures = None
    declared_gen = bridge['map_contract'].get('gen_selector')
    if not isinstance(declared_gen, dict) or not declared_gen.get('column') or not declared_gen.get('definition'):
        raise ValueError('Production export requires map_contract.gen_selector column and definition')
    if bridge['fit_contract'].get('gen_selector') != declared_gen:
        raise ValueError('Fit/map GEN selector definitions differ')
    for source in sources:
        sample = source['sample']
        if Path(sample).name != sample: raise ValueError('Sample must be a directory name')
        base = Path(products_dir) / sample
        flags_path = base / 'event_step_flags.parquet'
        flags = pd.read_parquet(flags_path)
        denominator, endpoint = source['gen_column'], source['endpoint_column']
        metadata_relative = Path(source['gen_definition_file'])
        if metadata_relative.is_absolute() or '..' in metadata_relative.parts:
            raise ValueError('GEN definition file must remain within sample')
        import json
        definition_path = base / metadata_relative
        persisted_gen = json.loads(definition_path.read_text())['gen_selector']
        if persisted_gen != declared_gen or denominator != declared_gen['column']:
            raise ValueError('Persisted GEN selector differs from compatibility contract')
        provenance.append(str(definition_path.resolve()))
        if endpoint != bridge['map_contract']['endpoint']:
            raise ValueError('Endpoint column differs from compatibility contract')
        for column in (denominator, endpoint):
            if column not in flags or not flags[column].isin([0, 1, False, True]).all():
                raise ValueError(f'Missing or nonboolean production flag {column}')
        mask = flags[denominator].astype(bool)
        exposure, passed = int(mask.sum()), int((mask & flags[endpoint].astype(bool)).sum())
        if exposure <= 0 or passed <= 0: raise ValueError('Unsupported scalar production efficiency')
        exposures.append(exposure); efficiencies.append(passed / exposure)
        ns, ds, signatures = [], [], []
        for row in source['map_rows']:
            relative = Path(row['file'])
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Map row file must remain within sample directory')
            frame = pd.read_parquet(base / relative)
            for key, value in row['filters'].items(): frame = frame.loc[frame[key] == value]
            if len(frame) != 1: raise ValueError('Map row selector must select exactly one row')
            # All persisted non-statistical columns identify the conditional
            # population and bin; compare these, not only caller row labels.
            statistics = {'sample', 'passed', 'total', 'efficiency', 'err_low', 'err_high', 'err_sym',
                          'jeffreys_efficiency', 'uncertainty_method', 'n_files', 'n_events'}
            signature = {str(key): None if pd.isna(value) else value.item() if hasattr(value, 'item') else value
                         for key, value in frame.iloc[0].items() if key not in statistics}
            if not signature: raise ValueError('Map rows lack persisted bin/conditional identity')
            signatures.append(signature)
            ns.append(float(frame.iloc[0]['passed'])); ds.append(float(frame.iloc[0]['total']))
            provenance.append(str((base / relative).resolve()))
        if not ns: raise ValueError('At least one conditional count row required')
        if row_signatures is None: row_signatures = signatures
        elif signatures != row_signatures:
            raise ValueError('Conditional map row identities differ across classes')
        numerators.append(ns); denominators.append(ds); provenance.append(str(flags_path.resolve()))
    if exposures != bridge['map_contract']['generated_totals']:
        raise ValueError('Actual production GEN exposures differ from declared contract')
    if len(set(map(len, numerators))) != 1: raise ValueError('All classes need the same ordered count rows')
    for field, exported in (('numerators', numerators), ('denominators', denominators), ('efficiencies', efficiencies)):
        if field in bridge and not np.allclose(bridge[field], exported):
            raise ValueError(f'Declared {field} disagree with production counts')
        result[field] = exported
    result['count_source_provenance'] = sorted(set(provenance))
    return result

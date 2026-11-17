"""Frozen 21-input event and weighted-response contract (no training or fits)."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

from scripts.templates.bootstrap_classifier_closure import response_bins, template_matrix
from scripts.templates.train_full_correlation_xgboost import feature_frame, SELECTION

MASS_COLUMNS = ['reco_jpsi_slot1_mass', 'reco_jpsi_slot2_mass', 'reco_phi_mass']
MASS_WINDOWS = np.array([[2.9, 3.3], [2.9, 3.3], [.99, 1.07]])
KEYS = ['sample', 'source_file', 'entry']


def load_study(study):
    """Load disjoint pools and verify frozen booster predictions and row identity."""
    import xgboost as xgb
    study = Path(study).resolve()
    reference_path = study / 'frozen_input_reference.json'
    reference = json.loads(reference_path.read_text()) if reference_path.exists() else {'study': str(study)}
    source = Path(reference['study'])
    if not source.is_absolute(): source = (study / source).resolve()
    model_dir = study / 'phi_reweighted'
    model = xgb.Booster()
    model.load_model(model_dir / 'six_class_xgboost.json')
    metadata = json.loads((model_dir / 'frozen_study.json').read_text())
    features = metadata['feature_names']
    from scripts.templates.train_full_correlation_xgboost import FEATURE_NAMES, CLASS_ORDER, NOMINAL_MASSES
    if (not features or len(features) != len(set(features)) or any(name not in FEATURE_NAMES for name in features)
            or list(metadata['class_order']) != list(CLASS_ORDER)):
        raise ValueError('Incompatible ordered feature/class manifest')
    if tuple(metadata.get('nominal_feature_masses', NOMINAL_MASSES)) != tuple(NOMINAL_MASSES):
        raise ValueError('Nominal feature mass definitions differ')
    if metadata.get('selection_contract', SELECTION) != SELECTION:
        raise ValueError('Classifier selection definition differs')
    frame = pd.read_parquet(source / 'inputs/full_features.parquet')
    if frame.duplicated(KEYS).any():
        raise ValueError('Duplicate selected MC identities')
    pools = {}
    for name in ('heldout_template', 'final_validation'):
        with np.load(model_dir / (name + '_scores.npz'), allow_pickle=False) as saved:
            arrays = {key: saved[key].copy() for key in saved.files}
        if arrays['feature_names'].tolist() != features or arrays['class_order'].tolist() != metadata['class_order']:
            raise ValueError('Frozen feature/class order mismatch')
        prediction = model.predict(xgb.DMatrix(arrays['features']))
        if not np.allclose(prediction, arrays['scores'], atol=1e-7, rtol=1e-6):
            raise ValueError('Frozen booster predictions differ from saved scores')
        identities = pd.DataFrame({key: arrays[key] for key in KEYS})
        joined = identities.merge(frame, on=KEYS, how='left', validate='one_to_one', indicator=True)
        if not joined['_merge'].eq('both').all():
            raise ValueError('Saved score identity missing from selected feature cache')
        if not np.allclose(joined[features], arrays['features']):
            raise ValueError('Joined feature values differ from score inputs')
        masses = joined[MASS_COLUMNS].to_numpy(float)
        validate_masses(masses)
        arrays.update(masses=masses, phi_pt=joined['phi_pt'].to_numpy(float),
                      categories=response_bins(arrays['scores'], metadata['class_order'], 'coarse'))
        pools[name] = arrays
    identities = [set(zip(p['sample'], p['source_file'], p['entry'])) for p in pools.values()]
    if identities[0] & identities[1]:
        raise ValueError('Template/final identities overlap')
    manifest = {'study': str(study), 'source_study': str(source), 'model': str(model_dir / 'six_class_xgboost.json'),
                'map_path': str(source / 'inputs/phi_maps.json'), 'class_order': metadata['class_order'],
                'feature_names': features, 'selection': SELECTION, 'mass_windows': MASS_WINDOWS.tolist(),
                'baseline': 'phi_reweighted_native', 'response_bins': 54, 'response_edges': [0, .2, .5, 1.000001],
                'floor': 1e-6, 'ordering': 'Jpsi descending reconstructed pT; coherent masses',
                'scope': 'frozen classifier and maps; no prompt interpretation; raw unweighted mass likelihood',
                'partition_counts': {name: len(pool['labels']) for name, pool in pools.items()}}
    return {'pools': pools, 'manifest': manifest, 'model': model, 'mc_frame':frame}


def validate_masses(masses):
    masses = np.asarray(masses)
    if masses.ndim != 2 or masses.shape[1] != 3 or not np.isfinite(masses).all():
        raise ValueError('Require finite (n,3) measured masses')
    if np.any((masses < MASS_WINDOWS[:, 0]) | (masses > MASS_WINDOWS[:, 1])):
        raise ValueError('Mass outside exact selected fit domain')


def response_templates(pool, indices=None):
    """Same nominal floor; weighted normalized covariance from independent rows."""
    ids = np.arange(len(pool['labels'])) if indices is None else np.asarray(indices)
    labels, bins, weights = pool['labels'][ids], pool['categories'][ids], pool['shape_weight'][ids]
    if not np.isfinite(weights).all() or np.any(weights < 0):
        raise ValueError('Template weights must be finite and nonnegative')
    h = np.array([np.bincount(bins[labels == c], weights=weights[labels == c], minlength=54) for c in range(6)])
    q = np.array([np.bincount(bins[labels == c], weights=weights[labels == c]**2, minlength=54) for c in range(6)])
    if np.any(h.sum(axis=1) <= 0):
        raise ValueError('All six components need positive template totals')
    cov = []
    for total, squared in zip(h, q):
        t = total / total.sum()
        jac = (np.eye(54) - t[:, None]) / total.sum() / (1 + 54e-6)
        cov.append((jac * squared) @ jac.T)
    matrix = template_matrix(bins, labels, weights, 6, 54, floor=1e-6)
    return matrix, {'sumw': h.tolist(), 'sumw2': q.tolist(), 'covariance': np.asarray(cov).tolist(),
                    'raw_counts': [np.bincount(bins[labels == c], minlength=54).tolist() for c in range(6)]}


def load_selected_data(path, tree, prefix, bundle,event_keys=None,candidate_index_branch=None):
    """Explicit scalar selected-table adapter; selection/dedup must be documented."""
    import uproot
    import xgboost as xgb
    objects = ('Jpsi_1', 'Jpsi_2', 'Phi')
    names = [prefix + obj + '_' + key for obj in objects for key in ('px', 'py', 'pz', 'mass')]
    event_keys=[] if event_keys is None else event_keys
    if not isinstance(event_keys,list): raise ValueError('event_identity must list scalar event-key branch names')
    options={} if '://' in str(path) else {'handler':uproot.source.file.MultithreadedFileSource,'num_workers':1}
    additional=[] if candidate_index_branch is None else [candidate_index_branch]
    with uproot.open(path,**options) as root:
        arrays = root[tree].arrays(names+event_keys+additional, library='np')
    if event_keys:
        identity=pd.DataFrame({key:arrays[key] for key in event_keys})
        if identity.duplicated().any(): raise ValueError('Duplicate run/lumi/event identities; deduplicate selection first')
    if any(np.asarray(arrays[name]).ndim != 1 for name in names):
        raise ValueError('Require scalar selected candidates, not raw candidate vectors')
    momentum = np.stack([np.column_stack([arrays[prefix + obj + '_' + key] for key in ('px','py','pz')]) for obj in objects], axis=1)
    masses = np.column_stack([arrays[prefix + obj + '_mass'] for obj in objects])
    frame = feature_frame(momentum, masses)
    masses = frame[MASS_COLUMNS].to_numpy(float)
    validate_masses(masses)
    features = frame[bundle['manifest']['feature_names']].to_numpy(float)
    scores = bundle['model'].predict(xgb.DMatrix(features))
    result={'masses': masses, 'features': features, 'scores': scores,
            'phi_pt':frame['phi_pt'].to_numpy(), 'phi_y':frame['phi_y'].to_numpy(),
            'source_file':np.repeat(str(Path(path).resolve()),len(masses)), 'entry':np.arange(len(masses)),
            'categories': response_bins(scores, bundle['manifest']['class_order'], 'coarse')}
    result.update({'identity_'+key:np.asarray(arrays[key]) for key in event_keys})
    if candidate_index_branch is not None: result['candidate_index']=np.asarray(arrays[candidate_index_branch])
    return result


def histogram_templates(values, pool, edges, indices=None):
    """Normalized weighted shapes, with covariance and common folding policy."""
    ids = np.arange(len(values)) if indices is None else np.asarray(indices)
    values = np.clip(np.asarray(values)[ids], edges[0], edges[-1])
    weights, labels = pool['shape_weight'][ids], pool['labels'][ids]
    shapes, covariances = [], []
    for c in range(6):
        h = np.histogram(values[labels == c], edges, weights=weights[labels == c])[0]
        q = np.histogram(values[labels == c], edges, weights=weights[labels == c]**2)[0]
        t = h / h.sum()
        jac = (np.eye(len(h)) - t[:, None]) / h.sum()
        shapes.append(t)
        covariances.append((jac*q) @ jac.T)
    return np.asarray(shapes).T, np.asarray(covariances)


def reweighted_pool(pool, weighted_mc):
    """Join changed map weights to unchanged frozen identities/features/scores."""
    identities=pd.DataFrame({key:pool[key] for key in KEYS})
    joined=identities.merge(weighted_mc[KEYS+['input_weight','phi_shape_weight']],on=KEYS,how='left',validate='one_to_one')
    base=(joined.input_weight*joined.phi_shape_weight).to_numpy(float)
    if not np.isfinite(base).all() or np.any(base<0): raise ValueError('Refitted map weights missing/invalid')
    result=dict(pool);weights=base.copy()
    for c in range(6):
        selected=pool['labels']==c
        weights[selected]/=weights[selected].sum()
    result['shape_weight']=weights
    return result

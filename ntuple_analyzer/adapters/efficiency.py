"""Lazy adapters around established efficiency implementations.

All writes are confined to the core-provided unpublished scratch directory.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ['JJP_DPS1', 'JJP_DPS2_CS', 'JJP_DPS2_G', 'JJP_SPS_CS', 'JJP_SPS_G', 'JJP_TPS']


def _path(value):
    return Path(value['path'] if isinstance(value, dict) else value).resolve()


def _read(path):
    return json.loads(Path(path).read_text())


def _inventory(path):
    path = Path(path)
    return [str(p.resolve()) for p in sorted(path.rglob('*')) if p.is_file()] if path.is_dir() else [str(path.resolve())]


def _source(config, run_dir):
    value = config.get('inputs', {}).get('efficiency_products')
    return _path(value) if value else Path(run_dir) / 'stages/efficiency/products'


def stage_spec(stage, config, run_dir):
    inputs, dependencies = [], []
    cfg, refs = config.get('efficiency', {}), config.get('inputs', {})
    code = [str(Path(__file__).resolve())]
    if stage == 'efficiency':
        if refs.get('efficiency_products'):
            inputs.extend(_inventory(_path(refs['efficiency_products'])))
        else:
            for key in ('input_file_manifest', 'efficiency_run_a_manifest', 'efficiency_run_b_manifest'):
                if refs.get(key): inputs.append(str(_path(refs[key])))
            if cfg.get('config'): inputs.append(str(_path(cfg['config'])))
            for label in ('a', 'b'):
                if cfg.get(f'run_{label}', {}).get('config'):
                    inputs.append(str(_path(cfg[f'run_{label}']['config'])))
            code += [str(ROOT / 'efficiency_workflow/cli_efficiency.py'), str(ROOT / 'efficiency_workflow/efficiency.py')]
    elif stage == 'acceptance':
        dependencies = [] if refs.get('efficiency_products') else ['efficiency']
        inputs = _inventory(_source(config, run_dir)) if refs.get('efficiency_products') else []
        code += [str(ROOT / 'efficiency_workflow/products.py')]
    elif stage == 'maps':
        dependencies = ['acceptance']
        code += [str(ROOT / 'efficiency_workflow/build_factorized_maps.py')]
    elif stage == 'correct':
        dependencies = ['maps'] + ([] if refs.get('fit_results') else ['fit'])
        if refs.get('fit_results'): inputs.append(str(_path(refs['fit_results'])))
        if cfg.get('bridge'): inputs.append(str(_path(cfg['bridge'])))
        if refs.get('selected_data'): inputs.append(str(_path(refs['selected_data'])))
        code += [str(Path(__file__).with_name('normalization.py')), str(ROOT / 'scripts/templates/mass_classifier_normalization.py')]
    elif stage == 'validation':
        dependencies = config.get('validation', {}).get('dependencies', [])
        inputs = [str(_path(x['path'])) for x in config.get('validation', {}).get('artifacts', [])]
    else:
        raise ValueError(f'Unknown efficiency stage {stage}')
    if stage in ('efficiency', 'acceptance', 'maps', 'correct'):
        code += [str(ROOT / 'efficiency_workflow' / name) for name in
                 ('config.py', 'definition.py', 'io.py', 'products.py', 'derived_efficiency.py',
                  'efficiency.py', 'factorized.py', 'yield_correction.py')
                 if (ROOT / 'efficiency_workflow' / name).exists()]
    return {'inputs': inputs, 'outputs': ['manifest.json'], 'code': sorted(set(code)), 'dependencies': dependencies}


def _copy_products(source, target):
    if not source.is_dir(): raise ValueError(f'Missing efficiency products: {source}')
    shutil.copytree(source, target)


def _run(args):
    subprocess.run([sys.executable, *map(str, args)], check=True, cwd=ROOT)


def _calculate(manifest, cfg, destination):
    if not cfg.get('config'):
        raise ValueError('Raw efficiency requires explicit efficiency.config')
    _run(['-m', 'efficiency_workflow.cli_efficiency', '--analysis-mode', 'JpsiJpsiPhi',
          '--input-file-manifest', _path(manifest), '--efficiency-config', _path(cfg['config']),
          '--output-dir', destination, '--skip-plots', '--stage-mode', 'never',
          '--samples', ','.join(cfg.get('samples', SAMPLES))])


def execute(stage, config, run_dir, output_dir):
    if config.get('channel') != 'JJP': raise ValueError('Efficiency stages currently support JJP only')
    output_dir, run_dir = Path(output_dir), Path(run_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg, refs = config.get('efficiency', {}), config.get('inputs', {})
    detail = {}
    if stage == 'efficiency':
        if refs.get('efficiency_products'):
            _copy_products(_source(config, run_dir), output_dir / 'products')
            detail['source'] = str(_source(config, run_dir))
        else:
            if refs.get('efficiency_run_a_manifest') or refs.get('efficiency_run_b_manifest'):
                runs = []
                for label in ('a', 'b'):
                    manifest = refs.get(f'efficiency_run_{label}_manifest')
                    if manifest:
                        run_cfg = {**cfg, **cfg.get(f'run_{label}', {})}
                        _calculate(manifest, run_cfg, output_dir / 'products' / f'run_{label}')
                        runs.append(label)
                detail.update(independent_runs=runs, combination='not pooled; independent GEN populations')
            else:
                manifest = refs.get('input_file_manifest')
                if not manifest or not cfg.get('config'):
                    raise ValueError('Raw efficiency requires efficiency.config and inputs.input_file_manifest; implicit EOS discovery disabled')
                _calculate(manifest, cfg, output_dir / 'products')
    elif stage == 'acceptance':
        from efficiency_workflow.products import build_derived_efficiency_products
        _copy_products(_source(config, run_dir), output_dir / 'products')
        root = output_dir / 'products'
        roots = [root / name for name in ('run_a', 'run_b') if (root / name).is_dir()] or [root]
        detail['samples'] = {}
        for source in roots:
            products = build_derived_efficiency_products(source, source)
            if not products: raise ValueError('No derived acceptance products built')
            detail['samples'][source.name] = list(products)
    elif stage == 'maps':
        from efficiency_workflow.build_factorized_maps import build_factorized_maps, build_post_acceptance_maps
        source = run_dir / 'stages/acceptance/products'
        if any((source / name).exists() for name in ('run_a', 'run_b')):
            selected = cfg.get('map_run')
            if selected not in ('run_a', 'run_b') or not (source / selected).is_dir():
                raise ValueError('Independent Run A/B products: set efficiency.map_run to run_a or run_b; no cross-population factorization is inferred')
            source = source / selected
            detail['map_population'] = selected
        _copy_products(source, output_dir / 'products')
        samples = cfg.get('samples', SAMPLES)
        mode = cfg.get('correction_mode', 'factorized')
        if mode not in ('factorized', 'hybrid'): raise ValueError('Use factorized or hybrid correction mode')
        build_factorized_maps(output_dir / 'products', samples=samples, event_end_step=cfg.get('event_endpoint'))
        if mode == 'hybrid': build_post_acceptance_maps(output_dir / 'products', samples=samples, event_end_step=cfg.get('event_endpoint'))
        detail.update(samples=samples, correction_mode=mode)
    elif stage == 'correct':
        if config.get('correct', {}).get('mode', 'six-class') == 'production':
            if not refs.get('selected_data'): raise ValueError('Production correction requires selected_data')
            _run([ROOT / 'scripts/efficiency/compute_efficiency_corrected_yield.py', '--data-input', _path(refs['selected_data']),
                  '--efficiency-dir', run_dir / 'stages/maps/products', '--correction-mode', cfg.get('correction_mode', 'factorized'),
                  '-o', output_dir / 'yield.json', '--temp-dir', output_dir / 'temp', '--plot-dir', output_dir / 'plots', '-j', '1'])
            detail['result'] = 'yield.json'
        else:
            from .normalization import normalize, export_counts
            if not cfg.get('bridge'): raise ValueError('Six-class correction requires explicit efficiency.bridge compatibility artifact')
            fit_path = _path(refs['fit_results']) if refs.get('fit_results') else run_dir / 'stages/fit/fit_result.json'
            bridge = export_counts(_read(_path(cfg['bridge'])), run_dir / 'stages/maps/products')
            result = normalize(_read(fit_path), bridge)
            result['count_source_provenance'] = bridge.get('count_source_provenance', [])
            (output_dir / 'normalization.json').write_text(json.dumps(result, indent=2) + '\n')
            detail.update(fit_source=str(fit_path), bridge_source=str(_path(cfg['bridge'])))
    elif stage == 'validation':
        records = []
        artifacts = config.get('validation', {}).get('artifacts', [])
        if not artifacts: raise ValueError('Validation requires explicit fit, closure or plot artifacts')
        for index, item in enumerate(artifacts):
            path, kind = _path(item['path']), item['kind']
            if kind not in ('fit', 'closure', 'plot'): raise ValueError(f'Unknown validation kind {kind}')
            if not path.is_file(): raise ValueError(f'Missing validation artifact {path}')
            payload = _read(path) if kind != 'plot' else {}
            accepted = kind == 'plot' or payload.get('status') == 'accepted'
            if kind == 'closure':
                accepted = accepted and payload.get('closure_passed') is True
                if payload.get('ensemble') == 'fixed-count' and 'actual_injected_counts' not in payload:
                    accepted = False
            target = output_dir / f'{index:03d}_{path.name}'
            shutil.copy2(path, target)
            records.append({'source': str(path), 'kind': kind, 'accepted': accepted,
                            'numerical_acceptance': payload.get('numerical_acceptance'),
                            'closure_passed': payload.get('closure_passed')})
        detail['diagnostics'] = records
        detail['status'] = 'accepted' if all(x['accepted'] for x in records) else 'rejected'
    else:
        raise ValueError(f'Unknown stage {stage}')
    artifacts = [str(p.relative_to(output_dir)) for p in sorted(output_dir.rglob('*')) if p.is_file()]
    spec = stage_spec(stage, config, run_dir)
    detail.update(status=detail.get('status', 'accepted'), artifacts=artifacts, stage=stage,
                  source_provenance={'inputs': spec['inputs'], 'code': spec['code']})
    (output_dir / 'manifest.json').write_text(json.dumps(detail, indent=2) + '\n')
    return {**detail, 'artifacts': ['manifest.json', *artifacts]}

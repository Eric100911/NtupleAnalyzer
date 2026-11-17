"""Lazy adapters for the selected-event six-source analysis.

Numerical implementations remain in scripts.templates. Every adapter writes only
its fresh output directory; the workflow publisher owns completion markers.
"""
from pathlib import Path
import json
import shutil
import hashlib

REPO = Path(__file__).resolve().parents[2]
STAGES = ('select','features','reweight','train','score','templates','fit','observable-fit','plot')
CLASS_ORDER = ['DPS1','DPS2_CS','DPS2_G','SPS_CS','SPS_G','TPS']
RESPONSE = {'preset':'argmax_tps_sumdps_54_v1','class_order':CLASS_ORDER,
            'coordinates':['argmax','TPS','DPS1+DPS2_CS+DPS2_G'],
            'score_edges':[0.,.2,.5,1.000001], 'endpoint':'left closed, right open; sentinel includes score 1',
            'category':'argmax*9 + TPS_bin*3 + sumDPS_bin','n_categories':54,'floor':1e-6}


def _path(value):
    return Path(value['path'] if isinstance(value,dict) else value).resolve()


def _json(path):
    return json.loads(Path(path).read_text())


def _write(path, value):
    from scripts.templates.run_mass_classifier_workflow import write_json
    write_json(path,value)


def _study(config, run):
    local=run/'stages/score/study'
    return local if local.exists() else (_path(config['inputs']['classifier_study']) if config.get('inputs',{}).get('classifier_study') else local)


def _inventory(path):
    """Track real frozen children, including legacy source ancestry, without ROOT scans."""
    path=_path(path)
    if path.is_file(): return [path]
    files=[p for p in path.rglob('*') if p.is_file() and p.suffix in ('.json','.npz','.parquet')]
    ref=path/'frozen_input_reference.json'
    if ref.exists():
        source=Path(_json(ref)['study'])
        if not source.is_absolute(): source=(path/source).resolve()
        files.extend(p for p in (source/'inputs').glob('*') if p.is_file())
    return sorted(set(files))


def stage_spec(stage, config, run_dir):
    if stage not in STAGES: raise ValueError(stage)
    run=Path(run_dir); inputs=config.get('inputs',{}); deps=[]; paths=[]
    external=bool(inputs.get('classifier_study'))
    previous={'reweight':'features','train':'reweight','score':'train','templates':'score','fit':'templates','observable-fit':'fit','plot':'observable-fit'}
    if stage in previous: deps=[previous[stage]]
    if external and stage in ('score','templates'):
        deps=[] if stage=='score' else ['score']; paths+=_inventory(inputs['classifier_study'])
    if external and stage=='fit': paths+=_inventory(inputs['classifier_study'])
    if stage=='features':
        for key in ('classifier_feature_cache','classifier_raw_root','classifier_mc_manifest'):
            if inputs.get(key): paths+=_inventory(inputs[key])
    if stage=='select':
        for key in ('selected_data','raw_data','data_selection_manifest'):
            if inputs.get(key): paths+=_inventory(inputs[key])
    if stage=='reweight':
        for key in ('phi_target','classifier_study'):
            if inputs.get(key): paths+=_inventory(inputs[key])
    if stage=='fit' and config.get('fit',{}).get('mode','data')=='data':
        deps.append('select')
        if inputs.get('data_selection_manifest'): paths+=_inventory(inputs['data_selection_manifest'])
    for key in ('mass_config','observable_mass_config'):
        if stage in ('fit','observable-fit') and config.get('fit',{}).get(key): paths+=_inventory(config['fit'][key])
    if stage=='plot':
        source=config.get('plots',{}).get('input_dir') or inputs.get('fit_results')
        if source: deps=[]; paths+=sorted(_path(source).glob(config.get('plots',{}).get('pattern','**/signal_mixture.json')))
    outputs={'select':['selected.root','selection.json'],'features':['full_features.parquet','source_manifest.json'],
             'reweight':['event_weights.parquet','phi_maps.json'],'train':['phi_reweighted/six_class_xgboost.json','phi_reweighted/frozen_study.json'],
             'score':['study/manifest.json'],'templates':['response_templates.npz','template_statistics.json'],
             'fit':['fit_result.json','events.npz'],'observable-fit':['observable_status.json'],'plot':['replot_manifest.json']}[stage]
    shared=['scripts/templates/train_full_correlation_xgboost.py','scripts/templates/train_multiclass_xgboost.py','scripts/templates/fit_correlation_components.py','scripts/templates/phi_kinematic_reweight.py','ntuple_pipeline_common.py']
    numerical=['scripts/templates/mass_classifier_inputs.py','scripts/templates/bootstrap_classifier_closure.py']
    mass=['scripts/templates/response_mass_fit.py','scripts/kinematics/fit_splot.py','scripts/templates/run_mass_classifier_workflow.py']
    codes={'select':['ntuple_pipeline_common.py','scripts/kinematics/merge_apply_cuts.py'],
           'features':shared+['scripts/kinematics/merge_apply_cuts.py'], 'reweight':shared,
           'train':shared,'score':shared+numerical,'templates':shared+numerical,
           'fit':shared+numerical+mass,'observable-fit':shared+numerical+mass+['scripts/templates/mass_classifier_observables.py'],
           'plot':['scripts/templates/mass_classifier_observables.py']}[stage]
    return {'inputs':[str(p) for p in paths], 'outputs':outputs+['manifest.json'],
            'code':[str(Path(__file__).resolve())]+[str(REPO/p) for p in codes], 'dependencies':deps}


def _check_config(config):
    c=config.get('classifier',{})
    if config.get('channel','JJP')!='JJP': raise ValueError('Classifier stages support JJP only')
    if c.get('baseline','phi_reweighted_native')!='phi_reweighted_native': raise ValueError('Unsupported classifier baseline')
    if c.get('class_order',CLASS_ORDER)!=CLASS_ORDER: raise ValueError('Class order mismatch')
    if c.get('response',{}).get('preset',RESPONSE['preset'])!=RESPONSE['preset']: raise ValueError('Unknown response definition')


def _copy_study(source, output):
    """Export a complete portable study, resolving historical source references."""
    from scripts.templates.mass_classifier_inputs import load_study
    bundle=load_study(source)
    output.mkdir()
    source=Path(source); model=source/'phi_reweighted'
    shutil.copytree(model,output/'phi_reweighted')
    (output/'inputs').mkdir()
    bundle['mc_frame'].to_parquet(output/'inputs/full_features.parquet',index=False)
    map_path=Path(bundle['manifest']['map_path'])
    if map_path.exists(): shutil.copy2(map_path,output/'inputs/phi_maps.json')
    manifest=dict(bundle['manifest'],study=str(output),source_study=str(source),model=str(output/'phi_reweighted/six_class_xgboost.json'),map_path=str(output/'inputs/phi_maps.json'),portable=True,response=RESPONSE)
    _write(output/'manifest.json',manifest)
    return bundle


def _fit_config(config, observable=False):
    fit=config.get('fit',{}); key='observable_mass_config' if observable else 'mass_config'
    value=fit.get(key)
    return _json(_path(value)) if value else dict(fit.get('parameters',{}))


def _accepted(result):
    d=result.get('diagnostics',{})
    return d.get('reliable') is True or (d.get('success') is True and 'status' not in d)


def execute(stage, config, run_dir, output_dir):
    _check_config(config)
    run=Path(run_dir); out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()): raise FileExistsError('Adapter output must be empty: '+str(out))
    inputs=config.get('inputs',{}); c=config.get('classifier',{}); fit=config.get('fit',{})
    manifest={'stage':stage,'response':RESPONSE,'status':'accepted'}
    if stage=='select':
        _select(config,out)
    elif stage=='features':
        from scripts.templates.train_full_correlation_xgboost import build_cache, FEATURE_NAMES, SELECTION
        cache=inputs.get('classifier_feature_cache')
        if cache:
            import pandas as pd
            cache=_path(cache); provenance=_json(cache.parent/'source_manifest.json')
            if not provenance.get('complete') or provenance['selection']!=SELECTION: raise ValueError('Incompatible feature cache')
            frame=pd.read_parquet(cache)
            frame.to_parquet(out/'full_features.parquet',index=False); _write(out/'source_manifest.json',provenance)
        else:
            root=inputs.get('classifier_raw_root')
            if not root and inputs.get('classifier_mc_manifest'): root=_json(_path(inputs['classifier_mc_manifest']))['raw_root']
            if not root: raise ValueError('features requires classifier_feature_cache or frozen raw_root inventory')
            temporary=out/'extraction'; build_cache(_path(root),temporary,c.get('seed',20261109),c.get('max_files'))
            for path in temporary.iterdir(): shutil.move(str(path),out/path.name)
            temporary.rmdir()
    elif stage=='reweight':
        import pandas as pd
        from scripts.templates.train_full_correlation_xgboost import weighted_frame
        from scripts.templates.phi_kinematic_reweight import data_target,build_weights
        frame=pd.read_parquet(run/'stages/features/full_features.parquet')
        if inputs.get('classifier_study'):
            study=_path(inputs['classifier_study']); ref=study/'frozen_input_reference.json'
            source=Path(_json(ref)['study']) if ref.exists() else study
            phi=pd.read_parquet(source/'inputs/phi_shape_weights.parquet')
            keys=['sample','source_file','entry']; merged=frame.merge(phi[keys+['phi_shape_weight']],on=keys,validate='one_to_one')
            if len(merged)!=len(frame): raise ValueError('Frozen weights missing identities')
            weighted=weighted_frame(frame,merged.phi_shape_weight)
            shutil.copy2(source/'inputs/phi_maps.json',out/'phi_maps.json')
            manifest['partition_policy']='Frozen historical maps and partitions; no refitting'
        else:
            if c.get('map_partition_policy','training-only-native')!='training-only-native':
                raise ValueError('Supported map_partition_policy is training-only-native; maps and application normalization fit training rows only')
            target=data_target(_path(inputs['phi_target'])); target.to_parquet(out/'data_phi_target.parquet',index=False)
            phi,maps,report=build_weights(frame,target); weighted=weighted_frame(frame,phi.phi_shape_weight)
            _write(out/'phi_maps.json',maps); _write(out/'phi_map_report.json',report)
            manifest['partition_policy']='Per-class maps and application normalization fit training rows only; signed data target; final labels never used for tuning'
        weighted.to_parquet(out/'event_weights.parquet',index=False)
    elif stage=='train':
        import pandas as pd
        from scripts.templates.train_full_correlation_xgboost import train_variant,FEATURE_NAMES
        names=c.get('features',list(FEATURE_NAMES[:-1]))
        if not names or len(set(names))!=len(names) or any(n not in FEATURE_NAMES for n in names): raise ValueError('Invalid ordered feature names')
        if c.get('preset','full_correlation_21')!='full_correlation_21' and not c.get('features'): raise ValueError('Unknown feature preset')
        train_variant(pd.read_parquet(run/'stages/reweight/event_weights.parquet'),out/'phi_reweighted',seed=c.get('seed',20261109),n_estimators=c.get('n_estimators',1200),jobs=c.get('jobs',1),feature_names=names)
        report=_json(out/'phi_reweighted/trial_report.json')
        if report['checks']['saved_model_max_prediction_difference']>1e-7: raise ValueError('Model reload mismatch')
        manifest['feature_names']=names
    elif stage=='score':
        if inputs.get('classifier_study'): _copy_study(_path(inputs['classifier_study']),out/'study')
        else:
            study=out/'study'; study.mkdir(); shutil.copytree(run/'stages/train/phi_reweighted',study/'phi_reweighted'); (study/'inputs').mkdir()
            shutil.copy2(run/'stages/features/full_features.parquet',study/'inputs/full_features.parquet')
            shutil.copy2(run/'stages/reweight/phi_maps.json',study/'inputs/phi_maps.json')
            _write(study/'manifest.json',{'portable':True,'response':RESPONSE})
        from scripts.templates.mass_classifier_inputs import load_study
        bundle=load_study(out/'study'); manifest.update(feature_names=bundle['manifest']['feature_names'],class_order=bundle['manifest']['class_order'],score_scope='Export/revalidate predictions emitted by train_variant; no retraining')
    elif stage=='templates':
        import numpy as np
        from scripts.templates.mass_classifier_inputs import load_study,response_templates
        bundle=load_study(_study(config,run)); t,stats=response_templates(bundle['pools']['heldout_template'])
        np.savez_compressed(out/'response_templates.npz',templates=t,covariance=stats['covariance']); _write(out/'template_statistics.json',stats)
        manifest.update(bundle['manifest']); manifest.update(response=RESPONSE,stage=stage,model_sha256=hashlib.sha256(Path(bundle['manifest']['model']).read_bytes()).hexdigest())
    elif stage=='fit':
        manifest.update(_fit(config,run,out))
    elif stage=='observable-fit':
        manifest.update(_observables(config,run,out))
    elif stage=='plot':
        from scripts.templates.mass_classifier_observables import replot_saved_signal_mixture,resolve_plot_settings,validate_plot_axes
        source=config.get('plots',{}).get('input_dir') or inputs.get('fit_results') or run/'stages/observable-fit/plots'
        source=_path(source); plots=config.get('plots',{})
        if plots.get('normalization','differential_yield')!='differential_yield': raise ValueError('Only differential_yield rendering is supported')
        paths=sorted(source.glob(plots.get('pattern','**/signal_mixture.json')))
        if not paths: raise ValueError('No saved integrated plot JSON found')
        resolved=[]
        for p in paths:
            saved=_json(p); name=saved.get('observable',p.parent.name)
            settings=resolve_plot_settings(plots,name); validate_plot_axes(saved,settings)
            resolved.append((p,name,settings))
        for p,name,settings in resolved:
            replot_saved_signal_mixture(p,out/'plots'/p.parent.relative_to(source),cms_caption=plots.get('cms_caption','Work In Progress'),**settings)
        _write(out/'replot_manifest.json',{'source':str(source),'count':len(paths),'refitted':False,
               'resolved_plot_settings':[dict(source=str(p),observable=name,**settings) for p,name,settings in resolved],
               'unused_observable_overrides':sorted(set(plots.get('observables',{}))-{name for p,name,settings in resolved}),
               'artifacts':[str(p.relative_to(out)) for p in sorted((out/'plots').rglob('*')) if p.is_file()]})
    else: raise ValueError(stage)
    _write(out/'manifest.json',manifest)
    canonical=str(run/'stages'/stage)
    def published(value):
        if isinstance(value,str): return value.replace(str(out),canonical)
        if isinstance(value,list): return [published(v) for v in value]
        if isinstance(value,dict): return {k:published(v) for k,v in value.items()}
        return value
    for path in out.rglob('*.json'):
        if str(out) in path.read_text():
            _write(path,published(_json(path)))
    artifacts=[str(p.relative_to(out)) for p in sorted(out.rglob('*')) if p.is_file()]
    return dict(manifest,artifacts=artifacts)


def _select(config,out):
    import numpy as np
    import uproot
    inputs=config['inputs']; selection=_json(_path(inputs['data_selection_manifest']))
    required=('selection_id','deduplication','candidate_ordering','candidate_index_branch','mass_windows','event_identity')
    if any(k not in selection for k in required) or not selection['event_identity'] or not selection['candidate_index_branch']:
        raise ValueError('Explicit selection provenance, actual event identity and candidate index are required')
    source=inputs.get('selected_data')
    if source:
        if not isinstance(source,dict) or source.get('schema')!='legacy_selected':
            raise ValueError('selected_data must explicitly declare schema: legacy_selected; raw vectors require raw_data')
        source=_path(source)
        with uproot.open(source) as root:
            tree=root['selected']; names=[f'sel_{obj}_{axis}' for obj in ('Jpsi_1','Jpsi_2','Phi') for axis in ('px','py','pz','mass')]
            arrays=tree.arrays(names+selection['event_identity']+[selection['candidate_index_branch']],library='np')
        if any(np.asarray(arrays[n]).dtype==object for n in names): raise ValueError('Selected data must be scalar')
        shutil.copy2(source,out/'selected.root')
    else:
        import ROOT
        from ntuple_pipeline_common import declare_rdf_helpers
        from scripts.kinematics.merge_apply_cuts import build_best_index_expr
        raw=inputs.get('raw_data')
        if not raw: raise ValueError('select requires selected_data or raw_data')
        raw=_path(raw)
        if raw.suffix.lower() in ('.json','.yaml','.yml'):
            if raw.suffix.lower()=='.json': inventory=_json(raw)
            else:
                import yaml
                inventory=yaml.safe_load(raw.read_text())
            files=inventory.get('files') if isinstance(inventory,dict) else inventory
            if not isinstance(files,list) or not files: raise ValueError('raw_data manifest requires nonempty files list')
            paths=[str((raw.parent/Path(item)).resolve()) if '://' not in item else item for item in files]
        else: paths=[str(raw)]
        declare_rdf_helpers()
        if ROOT.IsImplicitMTEnabled(): ROOT.DisableImplicitMT()
        rdf=ROOT.RDataFrame('X_data',paths).Define('muon_id_mask','muIsPatSoftMuon').Define('bestCandIdx',build_best_index_expr('JJP_data')).Filter('bestCandIdx >= 0')
        cols=list(selection['event_identity'])
        index=selection['candidate_index_branch']
        if index!='bestCandIdx': rdf=rdf.Define(index,'bestCandIdx')
        cols.append(index)
        # Coherent slot ordering: every measured momentum/mass follows the pT permutation.
        rdf=rdf.Define('unified_swap','Jpsi_2_pt.at(bestCandIdx) > Jpsi_1_pt.at(bestCandIdx)')
        for obj,other in [('Jpsi_1','Jpsi_2'),('Jpsi_2','Jpsi_1'),('Phi','Phi')]:
            for axis in ('px','py','pz','mass'):
                name=f'sel_{obj}_{axis}'; expr=f'{obj}_{axis}.at(bestCandIdx)' if obj=='Phi' else f'(unified_swap ? {other}_{axis}.at(bestCandIdx) : {obj}_{axis}.at(bestCandIdx))'
                rdf=rdf.Define(name,expr); cols.append(name)
        rdf.Snapshot('selected',str(out/'selected.root'),cols)
        identity = rdf.AsNumpy(selection['event_identity'])
    import pandas as pd
    if source:
        identity={key:arrays[key] for key in selection['event_identity']}
    if pd.DataFrame(identity).duplicated().any(): raise ValueError('Duplicate actual selected event identity')
    selection.update(tree='selected',prefix='sel_',source=str(source if source else raw),schema='legacy_selected')
    _write(out/'selection.json',selection)


def _fit(config,run,out):
    import numpy as np
    from scripts.templates.mass_classifier_inputs import load_study,load_selected_data
    from scripts.templates.run_mass_classifier_workflow import generate_toy,observable_inventory
    from scripts.templates.response_mass_fit import fit_simultaneous_masses
    fit=config.get('fit',{}); bundle=load_study(_study(config,run)); cfg=_fit_config(config)
    with np.load(run/'stages/templates/response_templates.npz') as saved: t=saved['templates'].copy()
    if t.shape!=(54,6) or not np.allclose(t.sum(axis=0),1): raise ValueError('Invalid frozen response templates')
    template_manifest=_json(run/'stages/templates/manifest.json')
    expected_digest=hashlib.sha256(Path(bundle['manifest']['model']).read_bytes()).hexdigest()
    if (template_manifest.get('response')!=RESPONSE or template_manifest.get('class_order')!=bundle['manifest']['class_order']
            or template_manifest.get('feature_names')!=bundle['manifest']['feature_names']
            or template_manifest.get('selection')!=bundle['manifest']['selection']
            or template_manifest.get('model_sha256')!=expected_digest):
        raise ValueError('Frozen response/model/feature/selection manifest mismatch')
    mode=fit.get('mode','data'); mixture=fit.get('mixture','fitted')
    if mode=='data':
        selection=_json(run/'stages/select/selection.json')
        if selection['mass_windows']!=bundle['manifest']['mass_windows']: raise ValueError('Mass window mismatch')
        sample=load_selected_data(run/'stages/select/selected.root','selected','sel_',bundle,event_keys=selection['event_identity'],candidate_index_branch=selection['candidate_index_branch'])
    elif mode in ('toy','signal-control'):
        sample=generate_toy(bundle,fit.get('events',1000),0 if mode=='signal-control' else fit.get('background_events',1000),fit.get('fractions',[1/6]*6),fit.get('seed',20261110),mass_config=cfg)
        _write(out/'truth.json',sample['truth'])
    else: raise ValueError('Unsupported fit mode')
    np.savez_compressed(out/'events.npz',**{k:v for k,v in sample.items() if isinstance(v,np.ndarray)})
    if mixture=='fixed':
        fractions=np.asarray(fit.get('fractions',[]),float)
        if fractions.shape!=(6,) or not np.isfinite(fractions).all() or np.any(fractions<0) or not np.isclose(fractions.sum(),1) or not fit.get('fraction_provenance'):
            raise ValueError('Fixed mixture requires six normalized fractions and fraction_provenance')
        inclusive=fit_simultaneous_masses(sample['masses'],np.zeros(len(sample['masses']),dtype=int),1,config=cfg,output_dir=out/'inclusive_mass_fit')
        if not _accepted(inclusive): return {'status':'rejected','reason':'Inclusive normalization fit rejected'}
        total=inclusive['signal_yields'][0]; variance=inclusive['signal_covariance'][0][0]
        result=dict(inclusive,class_yields=(fractions*total).tolist(),class_covariance=(np.outer(fractions,fractions)*variance).tolist())
        _write(out/'common_normalization.json',{'total':total,'variance':variance,'fractions':fractions,'fraction_provenance':fit['fraction_provenance'],'scope':'Fixed composition hypothesis; inclusive normalization only; shared with every observable'})
    elif mixture=='fitted':
        if mode=='signal-control':
            from scripts.templates.bootstrap_classifier_closure import fit_fraction
            counts=np.bincount(sample['categories'],minlength=54); f,ok,message=fit_fraction(counts,t); n=f*counts.sum()
            contrasts=t[:,:5]-t[:,[5]]; fisher=contrasts.T@(counts[:,None]*contrasts/np.maximum((t@f)[:,None],1e-100)**2); jac=np.vstack([np.eye(5),-np.ones(5)])
            cov=jac@np.linalg.pinv(fisher)@jac.T*counts.sum()**2+np.outer(n,n)/counts.sum()
            result={'class_yields':n,'class_covariance':cov,'diagnostics':{'success':bool(ok),'message':str(message)}}
        else: result=fit_simultaneous_masses(sample['masses'],sample['categories'],54,t,cfg,out/'joint_fit')
    else: raise ValueError('mixture must be fitted or fixed')
    result.update(status='accepted' if _accepted(result) else 'rejected',class_order=bundle['manifest']['class_order'])
    contract=fit.get('contract',fit.get('efficiency_contract'))
    if contract:
        if mode=='data' and contract!=selection.get('efficiency_contract'): raise ValueError('Efficiency bridge contract must exactly match explicit selected-input efficiency_contract; channel/selection ID alone cannot establish compatibility')
        if contract.get('class_order')!=bundle['manifest']['class_order']: raise ValueError('Explicit efficiency bridge class order differs')
        result['contract']=contract
    _write(out/'fit_result.json',result)
    inventory=observable_inventory(bundle,fit.get('observable_bins',8)); requested=fit.get('observables')
    if requested:
        unknown=set(requested)-{s['name'] for s in inventory}
        if unknown: raise ValueError('Observable unavailable in model feature manifest: '+str(unknown))
        inventory=[s for s in inventory if s['name'] in requested]
    return {'status':'accepted' if _accepted(result) else 'rejected','mode':mode,'mixture':mixture,'observable_inventory':inventory,'mass_config':cfg,'class_order':bundle['manifest']['class_order'],'uncertainty_scope':'Conditional frozen model/maps/templates; fixed mode excludes composition covariance; same-data cross covariance unavailable'}


def _observables(config,run,out):
    import numpy as np
    from scripts.templates.mass_classifier_inputs import load_study,histogram_templates
    from scripts.templates.mass_classifier_observables import extract_observable_distribution,plot_signal_mixture
    bundle=load_study(_study(config,run)); source=run/'stages/fit'; manifest=_json(source/'manifest.json'); result=_json(source/'fit_result.json')
    if manifest['status']!='accepted' or not _accepted(result): raise ValueError('Observable extraction requires accepted normalization')
    with np.load(source/'events.npz',allow_pickle=False) as saved: sample={k:saved[k].copy() for k in saved.files}
    pool=bundle['pools']['heldout_template']; values=np.column_stack([sample['scores'],sample['features']]); mc=np.column_stack([pool['scores'],pool['features']])
    cfg=_fit_config(config,True)
    if not cfg: cfg=dict(manifest['mass_config'])
    if 'class_resolution_multipliers' in cfg: raise ValueError('Independent observable extraction needs explicit mass-only observable_mass_config')
    if config.get('fit',{}).get('mixture')=='fixed': cfg.setdefault('initial_parameters',{n:v for n,v in zip(result.get('parameter_names',[]),result.get('parameter_values',[])) if n.startswith('shape')})
    attempts=config.get('fit',{}).get('continuation_attempts',1)
    if not isinstance(attempts,int) or not 0<=attempts<=3: raise ValueError('continuation_attempts must be 0..3')
    status={'completed':[],'failed':{},'continuation_attempts':attempts}
    for spec in manifest['observable_inventory']:
        name=spec['name']; edges=np.asarray(spec['edges']); folder=out/'mass_extractions'/name; current=dict(cfg); records=[]; extraction=None
        for attempt in range(attempts+1):
            attempt_dir=folder/f'attempt_{attempt}'
            try:
                candidate=extract_observable_distribution(np.clip(values[:,spec['column']],edges[0],edges[-1]),edges,masses=sample['masses'],config=current,output_dir=attempt_dir,pure_signal=manifest['mode']=='signal-control')
                if manifest['mode']!='signal-control' and not _accepted(candidate['fit']): raise RuntimeError('Unreliable observable fit')
                extraction=candidate; records.append({'attempt':attempt,'accepted':True,'config':current}); break
            except RuntimeError as error:
                records.append({'attempt':attempt,'accepted':False,'error':str(error),'config':current})
                saved=attempt_dir/'mass_fit.json'
                if not saved.exists(): break
                previous=_json(saved); d=previous['diagnostics']; selected=d['attempts'][d['selected_attempt']]
                current=dict(cfg,warm_start=False,initial_parameters={k:v['value'] for k,v in selected['parameters'].items()})
        _write(folder/'continuation.json',{'attempts':records,'policy':'Bounded continuation from selected previous parameters; unchanged model, binning and acceptance thresholds'})
        if extraction is None: status['failed'][name]='All bounded attempts rejected'; continue
        h,cov=histogram_templates(mc[:,spec['column']],pool,edges)
        _write(folder/'extraction.json',extraction); np.savez_compressed(folder/'templates.npz',templates=h,template_covariance=cov)
        plot_signal_mixture(out/'plots'/name,extraction,np.asarray(result['class_yields']),np.asarray(result['class_covariance']),h,template_covariance=cov,observable=name)
        status['completed'].append(name)
    _write(out/'observable_status.json',status)
    return {'status':'partial' if status['failed'] else 'accepted','observable_status':status,'normalization_source':str(source/'fit_result.json'),'flow':'fold under/overflow into finite endpoint bins','uncertainty_scope':manifest['uncertainty_scope']}

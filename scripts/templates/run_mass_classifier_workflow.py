#!/usr/bin/env python3
"""Frozen 21-input, exact-54 response mass workflow; no training operations."""
from pathlib import Path
import argparse
import json
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.templates.mass_classifier_inputs import load_study, response_templates, load_selected_data, histogram_templates,reweighted_pool


def write_json(path, value):
    def convert(x):
        if isinstance(x, np.ndarray): return x.tolist()
        if isinstance(x, np.generic): return x.item()
        if isinstance(x, Path): return str(x)
        raise TypeError(type(x).__name__)
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, default=convert, allow_nan=False)+'\n')


def observable_inventory(bundle, bins=4):
    pool = bundle['pools']['heldout_template']
    names = ['score_'+c for c in bundle['manifest']['class_order']] + bundle['manifest']['feature_names']
    values = np.column_stack([pool['scores'], pool['features']])
    inventory = []
    for j, name in enumerate(names):
        edges = np.linspace(0, 1, bins+1) if j < 6 else np.unique(np.quantile(values[:, j], np.linspace(0,1,bins+1)))
        if len(edges) >= 2:
            inventory.append({'name': name, 'column': j, 'edges': edges.tolist(), 'flow': 'fold',
                              'definition': 'frozen score coordinate' if j < 6 else 'frozen nominal-mass classifier feature'})
    return inventory


def generate_toy(bundle, events, background_events, fractions, seed, source='independent-final',mass_config=None):
    from scripts.templates.response_mass_fit import generate_mass_toy
    pool = bundle['pools']['final_validation']
    # Independent final events determine generation response, not the fit templates.
    t, _ = response_templates(pool)
    # Remove smoothing for generation: no background/signal is invented in unreachable cells.
    h = np.array([np.bincount(pool['categories'][pool['labels']==c], weights=pool['shape_weight'][pool['labels']==c], minlength=54) for c in range(6)]).T
    t = h / h.sum(axis=0)
    support = np.bincount(pool['categories'], weights=pool['shape_weight'], minlength=54)
    support /= support.sum()
    background = background_events * support[:, None] * np.ones((1,7))/7
    mass_config={} if mass_config is None else mass_config
    sample = generate_mass_toy(np.asarray(fractions)*events, t, background, seed=seed,
             shape_config=mass_config.get('shape_config'),class_resolution_multipliers=mass_config.get('class_resolution_multipliers'),
             resolution_multipliers=mass_config.get('resolution_multipliers'),shape_groups=mass_config.get('shape_groups'))
    rng = np.random.default_rng(seed+1)
    row_ids = []
    for c, b in zip(sample['class_label'], sample['categories']):
        ids = np.flatnonzero((pool['categories']==b) & ((pool['labels']==c) if c >= 0 else True))
        if not len(ids):
            raise RuntimeError('Generated response label has no matching independent final event')
        w = pool['shape_weight'][ids]
        row_ids.append(rng.choice(ids, p=w/w.sum()))
    row_ids = np.asarray(row_ids, dtype=int)
    sample['features'] = pool['features'][row_ids]
    sample['scores'] = pool['scores'][row_ids]
    sample['phi_pt']=pool['phi_pt'][row_ids]
    pz=np.sinh(pool['phi_y'][row_ids])*np.hypot(sample['phi_pt'],pool['masses'][row_ids,2])
    sample['phi_y']=np.arcsinh(pz/np.hypot(sample['phi_pt'],sample['masses'][:,2]))
    sample['source_pool_rows'] = row_ids
    sample['truth']['generation_scope'] = 'Matched analytic mass PDFs; independent final-MC response and kinematic proxy, not validated background data model'
    sample['truth']['source'] = source
    return sample


def run(args):
    from scripts.templates.response_mass_fit import fit_simultaneous_masses
    bundle = load_study(args.study_dir)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    config = {'freeze_shapes': args.freeze_shapes, 'profile': args.profile}
    if args.mass_config: config.update(json.loads(Path(args.mass_config).read_text()))
    observable_config=dict(config)
    if args.observable_mass_config: observable_config=json.loads(Path(args.observable_mass_config).read_text())
    elif 'class_resolution_multipliers' in config and not args.skip_observables:
        raise ValueError('Class-dependent signal shapes require an explicit --observable-mass-config for the independent mass-only extraction')
    t, stats = response_templates(bundle['pools']['heldout_template'])
    inventory = observable_inventory(bundle, args.observable_bins)
    if args.observables:
        unknown=set(args.observables)-{s['name'] for s in inventory}
        if unknown: raise ValueError('Unknown observables: '+str(sorted(unknown)))
        inventory=[s for s in inventory if s['name'] in args.observables]
    manifest = dict(bundle['manifest'], mode=args.mode, seed=args.seed, observable_inventory=inventory,
                    invocation=sys.argv, arguments=vars(args),
                    uncertainty_scope='full fitted nuisance covariance conditional on frozen booster/maps; no retraining/map-target uncertainty',
                    ignored_nonprompt='Current user scope; no prompt cross-section claim')
    write_json(output/'manifest.json', manifest)
    write_json(output/'template_statistics.json', stats)
    np.savez_compressed(output/'response_templates.npz', templates=t, covariance=stats['covariance'])
    if args.mode == 'data':
        if not args.selection_manifest or not args.data_input:
            raise ValueError('Data mode requires --data-input and explicit --selection-manifest')
        selection = json.loads(Path(args.selection_manifest).read_text())
        required = ('selection_id','deduplication','candidate_ordering','candidate_index_branch','mass_windows','event_identity')
        if any(key not in selection for key in required):
            raise ValueError('Selection manifest requires '+', '.join(required))
        if selection['mass_windows'] != manifest['mass_windows']:
            raise ValueError('Data selection mass windows differ from exact fit domain')
        if not selection['event_identity']: raise ValueError('Data requires actual nonempty event-identity branch list')
        write_json(output/'data_selection_manifest.json', selection)
        if not selection['candidate_index_branch']: raise ValueError('Data requires explicit selected candidate-index branch')
        sample = load_selected_data(args.data_input, args.tree, args.prefix, bundle,event_keys=selection['event_identity'],candidate_index_branch=selection['candidate_index_branch'])
    else:
        sample = generate_toy(bundle, args.events, 0 if args.mode=='signal-control' else args.background_events,
                              args.fractions, args.seed, args.toy_response,config)
        write_json(output/'truth.json', sample['truth'])
    np.savez_compressed(output/'events.npz', **{key:value for key,value in sample.items() if isinstance(value,np.ndarray)})
    if args.map_bootstrap=='refit':
        from scripts.templates.mass_classifier_map_bootstrap import refit_phi_maps
        mapped=refit_phi_maps(sample['masses'],sample['phi_pt'],sample['phi_y'],bundle['mc_frame'],output_dir=output/'nominal_map_refit')
        bundle['pools']={name:reweighted_pool(pool,mapped['weighted_mc']) for name,pool in bundle['pools'].items()}
        t,stats=response_templates(bundle['pools']['heldout_template'])
        write_json(output/'template_statistics.json',stats)
        np.savez_compressed(output/'response_templates.npz',templates=t,covariance=stats['covariance'])
        manifest['baseline']='toy-native-recalibrated' if args.mode!='data' else 'data-native-recalibrated'
        manifest['map_refit']='Nominal and bootstrap inclusive mass/sWeights/maps refitted; original booster and MC training identities fixed; generation truth unchanged'
        manifest['uncertainty_scope']='paired downstream data/map/template functional; fixed trained booster and training-MC sample; not full learned-model uncertainty'
        write_json(output/'manifest.json',manifest)
    if args.mode == 'signal-control':
        # Truth signal is directly counted; mass extraction adds no information.
        from scripts.templates.bootstrap_classifier_closure import fit_fraction
        counts = np.bincount(sample['categories'], minlength=54)
        f, success, message = fit_fraction(counts, t)
        n = f*len(sample['categories'])
        contrasts=t[:,:5]-t[:,[5]]
        fisher=contrasts.T @ (counts[:,None]*contrasts/np.maximum((t@f)[:,None],1e-100)**2)
        jac=np.vstack([np.eye(5),-np.ones(5)])
        covariance=jac@np.linalg.pinv(fisher)@jac.T*len(sample['categories'])**2 + np.outer(n,n)/len(sample['categories'])
        result = {'class_yields': n.tolist(), 'class_covariance': covariance.tolist(), 'signal_yields': counts.tolist(),
                  'signal_covariance': np.diag(counts).tolist(), 'diagnostics': {'success': success, 'message':message},
                  'scope':'Direct truth-signal multinomial control; no mass fit; intervals not inferred'}
    else:
        result = fit_simultaneous_masses(sample['masses'], sample['categories'], 54, t, config, output/'joint_fit')
    write_json(output/'fit_result.json', result)
    if args.mode != 'data':
        truth = np.asarray(sample['truth']['class_yields'])
        fitted = np.asarray(result['class_yields'])
        write_json(output/'recovery.json', {'truth': truth, 'fit': fitted, 'bias': fitted-truth,
                                          'relative_bias': (fitted-truth)/np.maximum(truth,1),
                                          'single_toy_not_coverage':True})
    if not args.skip_observables:
        bootstrap_result=run_observables(bundle, sample, result, inventory, output, config, args.mode=='signal-control',args.bootstrap,args.seed,observable_config,args.map_bootstrap)
        result.update(bootstrap_result)
        write_json(output/'fit_result.json',result)
    if args.normalization_config:
        run_normalization(result,json.loads(Path(args.normalization_config).read_text()),output)
    observable_status=json.loads((output/'observable_status.json').read_text()) if (output/'observable_status.json').exists() else {'failed':{},'completed':[]}
    bootstrap_status=json.loads((output/'bootstrap/status.json').read_text()) if (output/'bootstrap/status.json').exists() else None
    complete=not observable_status['failed'] and (bootstrap_status is None or bootstrap_status['covariance_available'])
    write_json(output/'workflow_status.json',{'status':'complete' if complete else 'partial','observable_status':observable_status,
               'bootstrap_status':bootstrap_status,'requested_observables':len(inventory),'executed_real_data_fit':args.mode=='data'})
    return output


def run_observables(bundle, sample, result, inventory, output, config, pure_signal,bootstrap,seed,observable_config,map_bootstrap):
    from scripts.templates.mass_classifier_observables import extract_observable_distribution, plot_signal_mixture
    from scripts.templates.response_mass_fit import fit_simultaneous_masses
    template_pool = bundle['pools']['heldout_template']
    template_values = np.column_stack([template_pool['scores'],template_pool['features']])
    values = np.column_stack([sample['scores'],sample['features']])
    extractions={}
    failures={}
    for spec in inventory:
        edges = np.asarray(spec['edges'])
        try:
            extraction = extract_observable_distribution(np.clip(values[:,spec['column']],edges[0],edges[-1]), edges, masses=sample['masses'],
                         fit_function=fit_simultaneous_masses, config=observable_config, output_dir=output/'observables'/spec['name'],pure_signal=pure_signal)
        except RuntimeError as error:
            failures[spec['name']]=str(error)
            write_json(output/'observable_status.json',{'failed':failures,'completed':list(extractions)})
            continue
        extractions[spec['name']]=extraction
        write_json(output/'observable_status.json',{'failed':failures,'completed':list(extractions)})
    inventory=[spec for spec in inventory if spec['name'] in extractions]
    replicas={spec['name']: {'signal':[],'prediction':[]} for spec in inventory}
    rng=np.random.default_rng(seed+702)
    bootstrap_failures=[]
    successful=0
    class_replicas=[]
    def one_replica(replica):
        # Poisson total resampling matches the extended likelihood, including total-rate variance.
        data_ids=rng.integers(0,len(values),rng.poisson(len(values)))
        template_ids=np.concatenate([rng.choice(np.flatnonzero(template_pool['labels']==c),size=int(np.sum(template_pool['labels']==c)),replace=True) for c in range(6)])
        varied_pool=template_pool
        if map_bootstrap=='refit':
            from scripts.templates.mass_classifier_map_bootstrap import refit_phi_maps
            mapped=refit_phi_maps(sample['masses'],sample['phi_pt'],sample['phi_y'],bundle['mc_frame'],indices=data_ids,
                                  output_dir=output/'bootstrap'/'maps'/str(replica))
            varied_pool=reweighted_pool(template_pool,mapped['weighted_mc'])
        tr,_=response_templates(varied_pool,template_ids)
        if pure_signal:
            from scripts.templates.bootstrap_classifier_closure import fit_fraction
            f,ok,message=fit_fraction(np.bincount(sample['categories'][data_ids],minlength=54),tr)
            if not ok: raise RuntimeError('Bootstrap signal fit failed: '+message)
            nr=f*len(data_ids)
        else:
            rr=fit_simultaneous_masses(sample['masses'][data_ids],sample['categories'][data_ids],54,tr,config,None)
            nr=np.asarray(rr['class_yields'])
        results={}
        for spec in inventory:
            edges=np.asarray(spec['edges'])
            er=extract_observable_distribution(np.clip(values[data_ids,spec['column']],edges[0],edges[-1]),edges,
               masses=sample['masses'][data_ids],fit_function=fit_simultaneous_masses,config=observable_config,pure_signal=pure_signal)
            hr,_=histogram_templates(template_values[:,spec['column']],varied_pool,edges,template_ids)
            results[spec['name']]={'signal':er['signal_yields'],'prediction':hr@nr}
        return results,nr
    for replica in range(bootstrap):
        try:
            rr,nr=one_replica(replica)
            for name,values_replica in rr.items():
                for key in ('signal','prediction'): replicas[name][key].append(values_replica[key])
            successful+=1
            class_replicas.append(nr)
        except (RuntimeError,ValueError) as error:
            bootstrap_failures.append({'replica':replica,'error':str(error)})
        write_json(output/'bootstrap'/'status.json',{'attempted':replica+1,'successful':successful,'failed':len(bootstrap_failures),
                   'failures':bootstrap_failures,'covariance_available':successful>=2 and not bootstrap_failures,
                   'scope':'Poisson-total paired event and within-class MC shape bootstrap; frozen booster; maps='+map_bootstrap+'; any failures invalidate covariance estimate'})
    bootstrap_valid=bootstrap and successful>=2 and not bootstrap_failures
    class_metadata={}
    if bootstrap_valid:
        class_covariance=np.cov(class_replicas,rowvar=False,ddof=1)
        rank=int(np.linalg.matrix_rank(class_covariance))
        class_metadata={'class_covariance_bootstrap':class_covariance.tolist(),'class_bootstrap_rank':rank,
                        'class_covariance_for_normalization':'bootstrap' if rank==6 else 'conditional_mass_fit',
                        'class_bootstrap_scope':'paired data/map/template replicas; frozen booster; few replicas do not establish precision or coverage',
                        'normalization_uncertainty_limitation':None if rank==6 else 'Bootstrap covariance rank below6; downstream retains conditional mass-fit covariance, excluding full template/map uncertainty'}
        write_json(output/'bootstrap'/'class_yields.json',dict(class_metadata,class_yield_replicas=class_replicas))
        all_y=np.column_stack([replicas[spec['name']]['signal'] for spec in inventory])
        all_p=np.column_stack([replicas[spec['name']]['prediction'] for spec in inventory])
        joint_all=np.cov(np.column_stack([all_y,all_p]),rowvar=False,ddof=1)
        np.savez_compressed(output/'bootstrap'/'all_observable_covariance.npz',covariance=joint_all,
                            signal_replicas=all_y,prediction_replicas=all_p,observable_names=np.array([s['name'] for s in inventory]))
    for spec in inventory:
        edges=np.asarray(spec['edges']); extraction=extractions[spec['name']]
        h,cov=histogram_templates(template_values[:,spec['column']],template_pool,edges)
        kwargs={}
        if bootstrap_valid:
            yy=np.asarray(replicas[spec['name']]['signal']); pp=np.asarray(replicas[spec['name']]['prediction'])
            covariance=np.cov(np.column_stack([yy,pp]),rowvar=False,ddof=1); bins=len(edges)-1
            extraction['signal_covariance']=covariance[:bins,:bins].tolist()
            kwargs={'joint_prediction_covariance':covariance[bins:,bins:], 'cross_covariance':covariance[:bins,bins:]}
            write_json(output/'bootstrap'/ (spec['name']+'.json'),{'signal_replicas':yy,'prediction_replicas':pp,'joint_covariance':covariance,
                       'scope':'paired event/template bootstrap conditional on frozen booster; maps='+map_bootstrap})
        class_cov = np.zeros((6,6)) if result['class_covariance'] is None else np.asarray(result['class_covariance'])
        plot_signal_mixture(output/'plots'/spec['name'], extraction, np.asarray(result['class_yields']),class_cov,h,
                            template_covariance=cov,observable=spec['name'],**kwargs)
    return class_metadata


def run_normalization(result, cfg, output):
    from scripts.templates.mass_classifier_normalization import build_mixed_efficiency_maps,compute_cross_sections
    n=np.asarray(result['class_yields']); cov=np.asarray(result['class_covariance_bootstrap'] if result.get('class_covariance_for_normalization')=='bootstrap' else result['class_covariance'])
    nn=np.asarray(cfg['numerators']); dimension=12+2*nn.size
    joint=np.zeros((dimension,dimension));joint[:6,:6]=cov
    joint[6:12,6:12]=cfg.get('efficiency_covariance',np.zeros((6,6)))
    joint[12:,12:]=cfg.get('count_covariance',np.zeros((2*nn.size,2*nn.size)))
    cross=np.asarray(cfg.get('efficiency_count_cross_covariance',np.zeros((6,2*nn.size))))
    joint[6:12,12:]=cross; joint[12:,6:12]=cross.T
    mixed=build_mixed_efficiency_maps(cfg['numerators'],cfg['denominators'],n,cfg['efficiencies'],
          generated_totals=cfg['generated_totals'],selection_id=cfg['selection_id'],map_selection_id=cfg['map_selection_id'],class_covariance=cov,
          efficiency_covariance=cfg.get('efficiency_covariance'),joint_covariance=joint)
    cross=compute_cross_sections(n,cfg['efficiencies'],cfg['luminosity'],cfg['branching_fractions'],class_covariance=cov,
          efficiency_covariance=cfg.get('efficiency_covariance'),scope=cfg['scope'])
    scope={'class_covariance_source':result.get('class_covariance_for_normalization','conditional_mass_fit'),
           'limitation':result.get('normalization_uncertainty_limitation','Conditional mass-fit covariance; full template/map/classifier uncertainty not included')}
    mixed['uncertainty_metadata']=scope;cross['uncertainty_metadata']=scope
    write_json(output/'mixed_efficiency.json',mixed); write_json(output/'cross_sections.json',cross)
    write_json(output/'normalization_config.json',cfg)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study-dir',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--mode',choices=['toy','signal-control','data'],default='toy')
    p.add_argument('--events',type=int,default=2000)
    p.add_argument('--background-events',type=int,default=2000)
    p.add_argument('--fractions',type=float,nargs=6,default=[1/6]*6)
    p.add_argument('--seed',type=int,default=20261110)
    p.add_argument('--observable-bins',type=int,default=4)
    p.add_argument('--skip-observables',action='store_true')
    p.add_argument('--observables',nargs='+',help='Optional bounded subset from the full27 inventory')
    p.add_argument('--bootstrap',type=int,default=0,help='Paired fixed-booster/map event+MC replicas; zero or >=2')
    p.add_argument('--map-bootstrap',choices=['frozen','refit'],default='frozen',help='Refit also recalibrates nominal maps to the same data functional; booster stays fixed')
    p.add_argument('--normalization-config',type=Path)
    p.add_argument('--freeze-shapes',action='store_true')
    p.add_argument('--profile',action='store_true')
    p.add_argument('--mass-config',type=Path)
    p.add_argument('--observable-mass-config',type=Path)
    p.add_argument('--toy-response',choices=['independent-final'],default='independent-final')
    p.add_argument('--data-input',type=Path)
    p.add_argument('--tree',default='X_data')
    p.add_argument('--prefix',default='')
    p.add_argument('--selection-manifest',type=Path)
    args=p.parse_args()
    if args.bootstrap==1 or args.bootstrap<0: p.error('--bootstrap requires zero or >=2')
    if args.events<=0 or args.background_events<0 or np.any(np.asarray(args.fractions)<0) or not np.isclose(sum(args.fractions),1):
        p.error('Require positive signal events, nonnegative backgrounds and simplex fractions')
    try:
        output=run(args)
    except Exception as error:
        if args.output_dir.exists() and not (args.output_dir/'workflow_status.json').exists():
            write_json(args.output_dir/'workflow_status.json',{'status':'failed','error':str(error)})
        raise
    print(output)
    if json.loads((output/'workflow_status.json').read_text())['status']!='complete':
        raise SystemExit(2)


if __name__=='__main__': main()

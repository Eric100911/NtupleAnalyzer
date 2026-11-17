#!/usr/bin/env python3
"""Fixed-classifier selected-mixture closure, independent templates and pseudo-data.

No score averaging is used to infer fractions. A nonnegative simplex binned
multinomial likelihood fits independent component response distributions.
"""
import argparse,json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize


def make_overviews(base,variant):
    """Plot the explicitly named combined empirical-bootstrap mode."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import mplhep as hep
    hep.style.use(hep.style.CMS)
    base=Path(base)
    for basis in ('three_class','six_class'):
        if not (base/variant/basis/'equal-input'/'summary.json').exists():continue
        fig,axes=plt.subplots(1,3,figsize=(18,6.5))
        fig.subplots_adjust(left=.065,right=.99,bottom=.30,top=.77,wspace=.33)
        for j,policy in enumerate(('balanced-class','equal-input')):
            saved=json.loads((base/variant/basis/policy/'summary.json').read_text())
            for ax,(scenario,values) in zip(axes,saved['scenarios'].items()):
                item=values['sample_plus_independent_template_bootstrap']
                x=np.arange(len(saved['classes']))+(j-.5)*.13
                ax.errorbar(x,item['mean_fit'],yerr=item['empirical_std'],fmt='o',label=policy,capsize=3)
                ax.plot(np.arange(len(saved['classes'])),values['configured_probabilities'],'kx',ms=8,label='injected' if j==0 else None)
                ax.set_xticks(np.arange(len(saved['classes'])),saved['classes'],rotation=50,ha='right',fontsize=15)
                ax.set_ylim(-.03,1);ax.set_ylabel('Selected mixture fraction',fontsize=18);ax.tick_params(axis='y',labelsize=16)
                if j==0:
                    hep.cms.label('Work In Progress',ax=ax,loc=0,data=False,com=13.6,fontsize=11)
                    pos=ax.get_position()
                    fig.text((pos.x0+pos.x1)/2,.93,scenario.replace('_selected','').replace('_',' '),ha='center',fontsize=17)
        axes[0].legend(fontsize=10)
        fig.text(.53,.075,'Pseudo-data + independent template bootstrap',ha='center',fontsize=15)
        fig.text(.53,.025,'Points: empirical mean; bars: empirical standard deviation, not calibrated intervals',ha='center',fontsize=13)
        fig.savefig(base/(variant+'_'+basis+'_closure.png'));plt.close(fig)


def response_bins(scores,classes,binning='legacy-fine'):
    """Frozen joint response partition; never tuned on final-validation rows."""
    scores=np.asarray(scores)
    if 'TPS' in classes:
        a=scores[:,classes.index('TPS')]
        b=scores[:,[i for i,c in enumerate(classes) if c.startswith('DPS')]].sum(axis=1)
    else:
        a=scores[:,0];b=scores[:,1]
    if binning=='argmax':return np.argmax(scores,axis=1)
    edges=np.array([0.,.2,.5,1.000001] if binning=='coarse' else [0.,.1,.2,.35,.5,.7,1.000001])
    n=len(edges)-1
    return np.argmax(scores,axis=1)*n*n+np.clip(np.searchsorted(edges,a,side='right')-1,0,n-1)*n+np.clip(np.searchsorted(edges,b,side='right')-1,0,n-1)


def template_matrix(bins,labels,weights,k,n_bins,floor=1.e-6):
    columns=[]
    for c in range(k):
        counts=np.bincount(bins[labels==c],weights=weights[labels==c],minlength=n_bins)
        # A tiny, explicitly declared common floor avoids exact zero support.
        counts=counts/counts.sum()
        columns.append((counts+floor)/(1+n_bins*floor))
    return np.asarray(columns).T


def fit_fraction(data,t):
    k=t.shape[1]
    def objective(f):
        p=np.maximum(t@f,1.e-300)
        return -np.dot(data,np.log(p))
    def gradient(f):
        return -t.T@(data/np.maximum(t@f,1.e-300))
    fit=minimize(objective,np.ones(k)/k,jac=gradient,bounds=[(0,1)]*k,
                 constraints=[{'type':'eq','fun':lambda f:f.sum()-1,'jac':lambda f:np.ones(k)}],
                 method='SLSQP',options={'ftol':1.e-8,'maxiter':400})
    return fit.x,bool(fit.success),str(fit.message)


def identities(a):
    return set(zip(a['source_file'].tolist(),a['entry'].tolist()))


def summarize(fits,target,success):
    good=np.asarray(fits)[success]
    if len(good)<2:
        return {'successful_toys':int(len(good)),'failure_rate':float(1-np.mean(success)),
                'statistics_available':False}
    delta=good-target
    cov=np.cov(good,rowvar=False)
    std=good.std(axis=0,ddof=1)
    correlation=np.divide(cov,np.outer(std,std),out=np.zeros_like(cov),where=np.outer(std,std)>0)
    return {'successful_toys':int(sum(success)),'failure_rate':float(1-np.mean(success)),
            'mean_fit':good.mean(axis=0).tolist(),'bias_from_configured':delta.mean(axis=0).tolist(),
            'empirical_std':std.tolist(),'empirical_covariance':cov.tolist(),
            'empirical_correlation':correlation.tolist(),
            'boundary_fraction_per_class':(good<1.e-5).mean(axis=0).tolist(),
            'relative_mean_squared_error':(np.mean(delta**2,axis=0)/target**2).tolist()}


def run(model_dir,output,args):
    template=np.load(model_dir/'heldout_template_scores.npz');data=np.load(model_dir/'final_validation_scores.npz')
    binning=getattr(args,'response_binning','legacy-fine')
    floor=getattr(args,'template_floor',1.e-6)
    population=getattr(args,'weight_population','native')
    if not np.isfinite(floor) or floor<=0:raise ValueError('Template floor must be positive and finite')
    classes=template['class_order'].tolist();k=len(classes)
    if args.toys<2 or args.events<=0:
        raise ValueError('Require toys >= 2 and events > 0')
    for sample in (template,data):
        scores=np.asarray(sample['scores'])
        if (np.any(~np.isfinite(scores)) or np.any(scores<0)
                or not np.allclose(scores.sum(axis=1),1,atol=1.e-5)):
            raise ValueError('Scores must be finite nonnegative simplex vectors')
        weights=np.asarray(sample['shape_weight'])
        if np.any(~np.isfinite(weights)) or np.any(weights<0):
            raise ValueError('Shape weights must be finite and nonnegative')
        if np.any(np.bincount(sample['labels'],weights=weights,minlength=k)<=0):
            raise ValueError('Every class requires a positive shape-weight total')
    if classes!=data['class_order'].tolist() or identities(template)&identities(data):
        raise ValueError('Class order mismatch or template/pseudo-data identity leakage')
    tb=response_bins(template['scores'],classes,binning);db=response_bins(data['scores'],classes,binning)
    nb=k*{'argmax':1,'coarse':9,'legacy-fine':36}[binning]
    # Within-class shape weights are normalized independently; training balancing weights never enter.
    tw=np.asarray(template['shape_weight'],float);dw=np.asarray(data['shape_weight'],float)
    if population=='common':
        tw=np.asarray(template['input_weight'],float).copy();dw=np.asarray(data['input_weight'],float).copy()
        for c in range(k):
            tw[template['labels']==c]/=tw[template['labels']==c].sum()
            dw[data['labels']==c]/=dw[data['labels']==c].sum()
    t=template_matrix(tb,template['labels'],tw,k,nb,floor)
    raw_counts=np.asarray([np.bincount(tb[template['labels']==c],minlength=nb) for c in range(k)])
    # rate_weight corrects partition size and Nreference/Nsource exposure, not a physical prior.
    rates=np.bincount(template['labels'],weights=template['rate_weight'],minlength=k)
    scenarios={'uniform_selected':np.ones(k)/k,'counted_input_selected':rates/rates.sum()}
    scenarios['tps_rich_selected' if k==6 else 'conditional_stress_selected']=np.array([.15,.15,.1,.025,.025,.55]) if k==6 else np.array([.6,.35,.05])
    if args.scenario_reference:
        reference=json.loads(args.scenario_reference.read_text())
        if reference['classes']!=classes:raise ValueError('Scenario reference class order mismatch')
        scenarios={name:np.asarray(item['configured_probabilities'],float) for name,item in reference['scenarios'].items()}
        if any(np.any(p<=0) or not np.isclose(p.sum(),1) for p in scenarios.values()):
            raise ValueError('Scenario probabilities must be positive simplex vectors')
    populations=[np.flatnonzero(data['labels']==c) for c in range(k)]
    templates=[np.flatnonzero(template['labels']==c) for c in range(k)]
    result={'model_dir':str(model_dir),'classes':classes,'scope':'fixed-classifier selected signal-only MC empirical closure; no real-data mass extraction, efficiency, luminosity, production or retraining uncertainty',
            'class_basis':'physical six-component selected basis' if k==6 else 'conditional three-component basis; TPS and omitted DPS/SPS subtypes are absent, not aggregated',
            'generator_weights':'genWeight=1 counted stored events','seed':args.seed,'toys_per_scenario':args.toys,'selected_events_per_toy':args.events,
            'scenario_reference':str(args.scenario_reference) if args.scenario_reference else None,
            'toy_exposure':'fixed N with multinomial class counts and empirical within-class resampling with replacement; not Poisson total count',
            'partition':{'scheme':binning,'bins':nb,'coordinates':'argmax x sTPS x sumDPS; argmax scheme uses winner only',
                         'edges':None if binning=='argmax' else ([0,.2,.5,1] if binning=='coarse' else [0,.1,.2,.35,.5,.7,1]),
                         'selection':'Prespecified sensitivity grids; no final-pool optimization'},
            'weight_population':population,
            'template_floor_per_class_per_bin':floor,'template_counts':np.bincount(template['labels'],minlength=k).tolist(),
            'support_regularization_note':f'Floor {floor} added after normalizing each class to unit weight; total added mass {nb*floor}. Asimov self-closure checks the fit implementation only.',
            'pseudo_data_pool_counts':np.bincount(data['labels'],minlength=k).tolist(),
            'disjoint_event_identities':True,'template_singular_values':np.linalg.svd(t,compute_uv=False).tolist(),
            'raw_template_bin_counts_per_class':raw_counts.tolist(),
            'pseudo_data_weight_fraction_in_empirically_empty_own_template_bins':[
                float(dw[(data['labels']==c)&(raw_counts[c,db]==0)].sum()/dw[data['labels']==c].sum()) for c in range(k)],
            'simplex_contrast_singular_values':np.linalg.svd(t[:,:-1]-t[:,[-1]],compute_uv=False).tolist(),
            'template_weight_summary':[], 'sampling_probabilities':{}, 'scenarios':{},
            'limitations':['Bootstrap reuses finite empirical pools and creates no new information. SPS_CS template and pseudo-data pools are particularly small.',
            'Final validation was already inspected in earlier studies; this fixed comparison is not blind optimization.',
            'Empirical covariance is ensemble spread, not per-toy calibrated intervals. Pulls and interval coverage are deliberately not claimed.',
            'Template bootstrap resamples rows uniformly then retains nonconstant shape weights; pseudo-data sampling uses normalized within-class shape weights.',
            'No classifier retraining replicas or phi-map/data-target uncertainty; this is inference conditional on frozen models and frozen reweighting maps.']}
    output.mkdir(parents=True,exist_ok=False)
    for c,ids in enumerate(templates):
        w=tw[ids];result['template_weight_summary'].append({'class':classes[c],'rows':len(ids),'sumw':float(w.sum()),'sumw2':float(w@w),'ess':float(w.sum()**2/(w@w))})
    for c,ids in enumerate(populations):
        p=dw[ids]/dw[ids].sum();result['sampling_probabilities'][classes[c]]={'rows':len(ids),'min':float(p.min()),'max':float(p.max()),'ess':float(1/(p@p))}
    arrays={}
    for scenario,prob in scenarios.items():
        rng=np.random.default_rng(args.seed) # paired identities/counts across policies when pools/weights match
        fixed=[];varied=[];sf=[];sv=[];counts=[];nll_messages={}
        for toy in range(args.toys):
            count=rng.multinomial(args.events,prob);counts.append(count)
            selected=np.concatenate([rng.choice(ids,size=int(n),replace=True,p=dw[ids]/dw[ids].sum()) for ids,n in zip(populations,count)])
            obs=np.bincount(db[selected],minlength=nb)
            f,ok,msg=fit_fraction(obs,t);fixed.append(f);sf.append(ok)
            resampled=np.concatenate([rng.choice(ids,size=len(ids),replace=True) for ids in templates])
            bt=template_matrix(tb[resampled],template['labels'][resampled],tw[resampled],k,nb,floor)
            f,ok,msg=fit_fraction(obs,bt);varied.append(f);sv.append(ok)
            if not ok:nll_messages[msg]=nll_messages.get(msg,0)+1
        fixed=np.asarray(fixed);varied=np.asarray(varied);counts=np.asarray(counts)
        asimov_fit,asimov_ok,asimov_message=fit_fraction(args.events*(t@prob),t)
        supported=t>1.e-5
        result['scenarios'][scenario]={'configured_probabilities':prob.tolist(),
            'asimov_fixed_template':{'fit':asimov_fit.tolist(),'max_abs_bias':float(np.max(abs(asimov_fit-prob))),'success':asimov_ok,'message':asimov_message},
            'template_bins_below_1e_minus5_per_class':(~supported).sum(axis=0).tolist(),
            'fixed_template':summarize(fixed,prob,np.asarray(sf)),
            'sample_plus_independent_template_bootstrap':summarize(varied,prob,np.asarray(sv)),
            'mean_realized_fractions':(counts/args.events).mean(axis=0).tolist(),'optimizer_failure_messages':nll_messages}
        if k==6:
            group=np.array([[1,1,1,0,0,0],[0,0,0,0,0,1]])
            for scope,fits,success in [('fixed_template',fixed,sf),('sample_plus_independent_template_bootstrap',varied,sv)]:
                if np.count_nonzero(success)<2:continue
                groupfit=fits[np.asarray(success)]@group.T;truth=group@prob
                # Fixed K and efficiency assumptions: local relative errors DPS=1, TPS=1/2, only sensitivity proxy.
                scales=np.array([1.,.5])/truth
                result['scenarios'][scenario][scope]['DPS_TPS_total_covariance']=np.cov(groupfit,rowvar=False).tolist()
                result['scenarios'][scenario][scope]['conditional_effective_area_relative_MSE_proxy_R']=float(np.mean(np.sum(((groupfit-truth)*scales)**2,axis=1)))
                result['scenarios'][scenario][scope]['conditional_effective_area_relative_variance_proxy_Q']=float(np.sum(groupfit.var(axis=0,ddof=1)*scales**2))
        arrays[scenario+'_fixed_fits']=fixed;arrays[scenario+'_template_bootstrap_fits']=varied
        arrays[scenario+'_injected_realized_counts']=counts;arrays[scenario+'_configured_probabilities']=prob
        arrays[scenario+'_fixed_success']=sf;arrays[scenario+'_template_bootstrap_success']=sv
    np.savez_compressed(output/'toys.npz',**arrays,classes=classes,response_template=t)
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'output':str(output),'classes':classes,'scenarios':result['scenarios']}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--toys',type=int,default=200);p.add_argument('--events',type=int,default=2000);p.add_argument('--seed',type=int,default=20261109)
    p.add_argument('--scenario-reference',type=Path,help='Freeze configured selected fractions from an original summary JSON, including counted-input scenario')
    p.add_argument('--response-binning',choices=['argmax','coarse','legacy-fine'],default='legacy-fine')
    p.add_argument('--template-floor',type=float,default=1.e-6,help='Probability floor added per class/bin after unit normalization')
    p.add_argument('--weight-population',choices=['native','common'],default='native',help='Native shape weights or original exposure weights for both independent pools')
    a=p.parse_args();run(a.model_dir,a.output_dir,a)
if __name__=='__main__':main()

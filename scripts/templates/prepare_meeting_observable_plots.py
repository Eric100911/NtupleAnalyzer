#!/usr/bin/env python3
"""Replot saved projections and extract finer projections without refitting Nc.

Binning is declared using raw occupancy and heldout template ESS before mass
extraction. The exact 54-cell classifier response and saved six yields are fixed.
"""
import argparse
import json
import csv
import shutil
import tempfile
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.templates.mass_classifier_inputs import load_study, histogram_templates
from scripts.templates.mass_classifier_observables import (
    COMPONENT_COLORS, plot_signal_mixture, extract_observable_distribution)
from scripts.templates.run_mass_classifier_workflow import write_json


def choose_binning(template_values, data_values, labels, weights, original_edges,
                   min_ess=5., min_raw=50):
    """Largest passing 6/8/10 pooled-MC quantile grid; no fitted values used.

    All candidates use the original full range and explicit common folding.
    Each class bin carrying >=2% of its class must have ESS>=5; negligible
    class tails may be zero. Pooled ESS>=30 and raw occupancy>=50 are required
    in every category. Fallback is the original grid.
    """
    original_edges=np.asarray(original_edges,float)
    tx=np.clip(template_values,original_edges[0],original_edges[-1])
    dx=np.clip(data_values,original_edges[0],original_edges[-1])
    candidates=[]
    selected=original_edges
    for bins in (6,8,10):
        edges=np.quantile(tx,np.linspace(0,1,bins+1))
        edges[0],edges[-1]=original_edges[0],original_edges[-1]
        valid=bool(np.all(np.diff(edges)>0))
        ess=np.zeros((6,bins)); probabilities=np.zeros((6,bins)); raw=np.zeros(bins,dtype=int)
        pooled_ess=np.zeros(bins)
        if valid:
            raw=np.histogram(dx,edges)[0]
            for c in range(6):
                mask=labels==c
                h=np.histogram(tx[mask],edges,weights=weights[mask])[0]
                q=np.histogram(tx[mask],edges,weights=weights[mask]**2)[0]
                ess[c]=np.divide(h*h,q,out=np.zeros_like(h),where=q>0)
                probabilities[c]=h/h.sum()
            h=np.histogram(tx,edges,weights=weights)[0]
            q=np.histogram(tx,edges,weights=weights**2)[0]
            pooled_ess=np.divide(h*h,q,out=np.zeros_like(h),where=q>0)
        relevant=probabilities>=.02
        passed=bool(valid and raw.min()>=min_raw and pooled_ess.min()>=30 and
                    np.all(ess[relevant]>=min_ess))
        candidates.append({'bins':bins,'edges':edges.tolist(),'raw_counts':raw.tolist(),
                           'template_ess_by_class':ess.tolist(),'template_probabilities':probabilities.tolist(),
                           'pooled_template_ess':pooled_ess.tolist(),'pass':passed})
        if passed: selected=edges
    return selected, {'selected_bins':len(selected)-1,'candidates':candidates,
        'rule':'largest of predeclared 6/8/10 pooled-heldout-MC quantile grids passing every raw mass-category count >=50, pooled template ESS >=30, and class/bin template ESS >=5 wherever template class probability >=0.02; otherwise original four bins',
        'uses_mass_fit_or_residuals':False,'min_raw':min_raw,'min_ess':min_ess}


def export_source(destination, extraction, result, templates, template_covariance, fit, provenance):
    """Portable plotting inputs: h_bc=Nc*Tbc, P_b=sum_c h_bc, Y_b=mass signal."""
    np.savez_compressed(destination/'plot_source.npz', edges=extraction['edges'],
        Y=extraction['signal_yields'], VY=extraction['signal_covariance'],
        Nc=fit['class_yields'], VNc=fit['class_covariance'], T=templates,
        VT=template_covariance, h=result['components'], P=result['prediction'],
        VP=result['prediction_covariance'])
    write_json(destination/'plot_source.json',dict(provenance,
        source_paths_scope='Historical provenance identifiers only; portable NPZ contains all inputs required to replot',
        definitions={'T_bc':'heldout weighted template bin sum / full selected class weight sum',
          'h_bc':'N_c T_bc','P_b':'sum_c h_bc','Y_b':'simultaneous three-mass SSS yield in observable bin b',
          'V_P':'T V_N T^T + sum_c N_c^2 V_T,c; conditional independent-template propagation'},
        class_order=result['class_order'],component_colors=result['component_colors'],
        common_normalization_total=float(np.sum(fit['class_yields'])),
        per_observable_renormalization=False,
        uncertainty_scope='Full shared-shape mass-extraction covariance and saved six-yield covariance; frozen classifier/native phi maps; cross covariance between Y and P unavailable. Ratio is descriptive.',
        extraction_kind=extraction.get('extraction_kind','simultaneous_mass_fit')))
    np.savetxt(destination/'bin_edges.csv',np.asarray(extraction['edges']),delimiter=',',header='edge',comments='')


def run(args):
    source=Path(args.input_dir); output=Path(args.output_dir)
    output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((source/'manifest.json').read_text())
    fit=json.loads((source/'fit_result.json').read_text())
    bundle=load_study(manifest['study']); pool=bundle['pools']['heldout_template']
    with np.load(source/'events.npz',allow_pickle=False) as handle:
        events={key:handle[key].copy() for key in handle.files}
    tx=np.column_stack((pool['scores'],pool['features']))
    dx=np.column_stack((events['scores'],events['features']))
    if list(manifest['feature_names'])!=bundle['manifest']['feature_names'] or manifest['response_bins']!=54:
        raise ValueError('Frozen feature/54-response contract mismatch')
    inventory=[s for s in manifest['observable_inventory'] if not args.observables or s['name'] in args.observables]
    provenance={'saved_joint_fit':str(source/'fit_result.json'),'events':str(source/'events.npz'),
                'study':manifest['study'],'baseline':manifest['baseline'],
                'response_bins':54,'feature_names':manifest['feature_names'],
                'joint_fit_refitted':False,'raw_event_count':len(dx)}
    provenance['sample_kind']='data' if manifest['mode']=='data' else 'toy'
    status={'original':[],'finer':[],'retained_original':[],'failed':{},'binning':{},'provenance':provenance}
    # Declare ALL grids before opening any saved observable fit or doing extraction.
    for spec in inventory:
        edges,selection=choose_binning(tx[:,spec['column']],dx[:,spec['column']],pool['labels'],pool['shape_weight'],spec['edges'])
        status['binning'][spec['name']]=selection
    write_json(output/'binning_predeclared.json',status['binning'])
    for spec in inventory:
        name,j=spec['name'],spec['column']
        edges=np.asarray(spec['edges'])
        t,tc=histogram_templates(tx[:,j],pool,edges)
        saved=json.loads((source/'plots'/name/'signal_mixture.json').read_text())
        extraction={'edges':edges.tolist(),'signal_yields':saved['signal_yields'],
          'signal_covariance':saved['signal_covariance'], 'fit':{'diagnostics':{'reliable':saved['mass_fit_reliable'],
          'empty_categories':saved.get('masked_signal_bins',[])}}}
        result=plot_signal_mixture(output/'original_4bin'/name,extraction,fit['class_yields'],fit['class_covariance'],t,
           template_covariance=tc,joint_prediction_covariance=saved['prediction_covariance'],observable=name,
           simulation=provenance['sample_kind']=='toy')
        if not np.allclose(result['components'],saved['components'],rtol=1e-9,atol=1e-8):
            raise ValueError('Saved common-normalization component mismatch')
        export_source(output/'original_4bin'/name,extraction,result,t,tc,fit,provenance)
        status['original'].append(name)
        selection=status['binning'][name]; bins=selection['selected_bins']
        if args.original_only or bins==len(edges)-1:
            status['retained_original'].append(name)
            write_json(output/'status.json',status); continue
        edges=np.asarray(next(c['edges'] for c in selection['candidates'] if c['bins']==bins))
        try:
            extraction=extract_observable_distribution(np.clip(dx[:,j],edges[0],edges[-1]),edges,masses=events['masses'],
                config={'freeze_shapes':False,'profile':False,'save_workspace':False},
                output_dir=output/'mass_extractions'/name)
            t,tc=histogram_templates(tx[:,j],pool,edges)
            result=plot_signal_mixture(output/'finer'/name,extraction,fit['class_yields'],fit['class_covariance'],t,
                template_covariance=tc,observable=name,simulation=provenance['sample_kind']=='toy')
            export_source(output/'finer'/name,extraction,result,t,tc,fit,provenance)
            status['finer'].append(name)
        except RuntimeError as error:
            # No residual-dependent bin retry; original remains the available plot.
            status['failed'][name]=str(error)
        write_json(output/'status.json',status)
        print(name,bins,'bins', 'ok' if name not in status['failed'] else 'unreliable',flush=True)
    write_json(output/'status.json',status)
    finalize_outputs(source,output)
    return status


def finalize_outputs(source,output):
    """Select reliable finer plots and export prefit occupancy alongside them."""
    source,output=Path(source),Path(output)
    status=json.loads((output/'status.json').read_text())
    manifest=json.loads((source/'manifest.json').read_text())
    pool=load_study(manifest['study'])['pools']['heldout_template']
    tx=np.column_stack((pool['scores'],pool['features']))
    with np.load(source/'events.npz',allow_pickle=False) as handle:
        dx=np.column_stack((handle['scores'],handle['features']))
        truth=handle['class_label'] if 'class_label' in handle else None
    selected={}
    for spec in manifest['observable_inventory']:
        name,j=spec['name'],spec['column']
        if name not in status['original']:continue
        variant='finer' if name in status['finer'] else 'original_4bin'
        destination=output/'preferred'/name
        shutil.copytree(output/variant/name,destination)
        with np.load(destination/'plot_source.npz',allow_pickle=False) as arrays:
            edges=arrays['edges'].copy()
        x=np.clip(tx[:,j],edges[0],edges[-1]); d=np.clip(dx[:,j],edges[0],edges[-1])
        raw=np.histogram(d,edges)[0]
        signal=np.histogram(d[truth>=0],edges)[0] if truth is not None else np.full(len(raw),-1)
        with (destination/'bin_statistics.csv').open('w',newline='') as handle:
            writer=csv.writer(handle)
            writer.writerow(['bin','low','high','raw_events','toy_truth_signal_events','class','template_raw','template_sumw','template_sumw2','template_ess'])
            for c,label in enumerate(manifest['class_order']):
                mask=pool['labels']==c; w=pool['shape_weight'][mask]
                counts=np.histogram(x[mask],edges)[0]
                h=np.histogram(x[mask],edges,weights=w)[0]
                q=np.histogram(x[mask],edges,weights=w*w)[0]
                ess=np.divide(h*h,q,out=np.zeros_like(h),where=q>0)
                for b in range(len(raw)):
                    writer.writerow([b,edges[b],edges[b+1],raw[b],signal[b],label,counts[b],h[b],q[b],ess[b]])
        selected[name]={'variant':variant,'bins':len(edges)-1,
                        'selection':'reliable predeclared finer grid' if variant=='finer' else
                        ('finer extraction unreliable; original retained' if name in status['failed'] else 'original retained'),
                        'source':str(Path(variant)/name)}
    write_json(output/'preferred_index.json',selected)
    return selected


def replot_source(source,output):
    """Recreate a projection from portable arrays; no ROOT or fit needed."""
    source=Path(source)
    metadata=json.loads((source/'plot_source.json').read_text())
    with np.load(source/'plot_source.npz',allow_pickle=False) as arrays:
        extraction={'edges':arrays['edges'],'signal_yields':arrays['Y'],
                    'signal_covariance':arrays['VY'],
                    'extraction_kind':metadata['extraction_kind']}
        result=plot_signal_mixture(output,extraction,arrays['Nc'],arrays['VNc'],arrays['T'],
            template_covariance=arrays['VT'],joint_prediction_covariance=arrays['VP'],
            observable=source.name,simulation=metadata.get('sample_kind')=='toy')
    return result


def refresh_plots(output):
    """Refresh presentation from portable numbers, asserting numerical identity."""
    output=Path(output)
    count=0
    for path in sorted(output.rglob('plot_source.npz')):
        if 'preferred' in path.relative_to(output).parts:continue
        folder=path.parent
        before=json.loads((folder/'signal_mixture.json').read_text())
        with tempfile.TemporaryDirectory(prefix='meeting_replot_') as tmp:
            result=replot_source(folder,Path(tmp)/'plot')
            for key in ('signal_yields','signal_covariance','prediction','prediction_covariance','components','edges'):
                if not np.allclose(result[key],before[key],rtol=1e-12,atol=1e-10):
                    raise ValueError('Presentation refresh changed '+key)
            result['artifacts']=['signal_mixture.png','signal_mixture.pdf']
            write_json(folder/'signal_mixture.json',result)
            for extension in ('png','pdf'):
                shutil.copy2(Path(tmp)/'plot'/('signal_mixture.'+extension),folder)
        metadata=json.loads((folder/'plot_source.json').read_text())
        metadata['source_paths_scope']='Historical provenance identifiers only; portable NPZ contains all inputs required to replot'
        write_json(folder/'plot_source.json',metadata)
        count+=1
    index=json.loads((output/'preferred_index.json').read_text())
    for name,item in index.items():
        item['source']=str(Path(item['variant'])/name)
        for filename in ('signal_mixture.png','signal_mixture.pdf','signal_mixture.json','plot_source.json'):
            shutil.copy2(output/item['variant']/name/filename,output/'preferred'/name)
    write_json(output/'preferred_index.json',index)
    print('Refreshed',count,'projections; numbers invariant',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir');p.add_argument('--output-dir',required=True)
    p.add_argument('--replot-source',help='Directory containing plot_source.json/npz; does not fit or load ROOT')
    p.add_argument('--finalize-only',action='store_true',help='Create preferred plots and statistics from an existing completed output')
    p.add_argument('--refresh-plots-only',action='store_true',help='Refresh existing plots from portable inputs, no fits')
    p.add_argument('--observables',nargs='*')
    p.add_argument('--original-only',action='store_true',help='Recolor saved extractions only; no mass fits')
    a=p.parse_args()
    if a.refresh_plots_only:
        refresh_plots(a.output_dir)
    elif a.finalize_only:
        if not a.input_dir:p.error('--input-dir required for --finalize-only')
        finalize_outputs(a.input_dir,a.output_dir)
    elif a.replot_source:
        replot_source(a.replot_source,a.output_dir)
    else:
        if not a.input_dir:p.error('--input-dir is required unless --replot-source is supplied')
        s=run(a)
        print(json.dumps({k:len(s[k]) for k in ('original','finer','retained_original','failed')}))

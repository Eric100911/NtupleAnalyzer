#!/usr/bin/env python3
"""Event-keyed RECO phi extraction and train-only signed-sWeight 2D shape maps.

Run under LCG109a. Missing raw RECO input fails closed for map production.
Input exposure remains untouched; genWeight=1 is the declared convention.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

KEYS = ['sample', 'source_file', 'entry']

def rapidity(px, py, pz, mass):
    """Signed RECO rapidity, calculated stably from the measured four-vector."""
    return np.arcsinh(np.asarray(pz) / np.sqrt(np.asarray(px)**2 + np.asarray(py)**2 + np.asarray(mass)**2))

def validate_keys(frame):
    if frame[KEYS].isna().any().any() or frame.duplicated(KEYS).any():
        raise ValueError('Event keys must be complete and unique')

def effective_entries(w):
    w = np.asarray(w, float)
    return float(w.sum()**2 / np.dot(w, w)) if np.dot(w, w) else 0.

def _indices(x, edges):
    # Infinite edge bins explicitly collect under/overflow; no target is discarded.
    return np.clip(np.searchsorted(np.asarray(edges, float), x, side='right') - 1, 0, len(edges)-2)

def _edges(x, bins):
    internal = np.unique(np.quantile(x, np.linspace(0, 1, bins+1)[1:-1]))
    return np.r_[-np.inf, internal, np.inf]

def fit_map(training, target, max_bins=6, min_mc=30, min_target_neff=4.):
    """Fit using ONLY a supplied training partition and full signed data target.

    Coarsen a train-quantile joint(pT,signed y) grid until ALL cells have
    positive signed data content, adequate signed-data effective entries, and
    populated MC support. Never take abs(sWeights), clip negative cells, or
    smooth with validation MC. Inclusive fallback is explicit in metadata.
    """
    if set(training['partition']) != {'training'}:
        raise ValueError('Map fitting accepts training rows only')
    x = training[['phi_pt','phi_y']].to_numpy(float)
    d = target[['phi_pt','phi_y']].to_numpy(float)
    sw = target.signal_sw.to_numpy(float)
    if not len(x) or not len(d) or not np.isfinite(x).all() or not np.isfinite(d).all() or not np.isfinite(sw).all():
        raise ValueError('Nonempty finite RECO inputs and target weights required')
    if sw.sum() <= 0:
        raise ValueError('Signed signal target has nonpositive total')
    attempts = []
    for bins in range(max_bins, 0, -1):
        ex, ey = _edges(x[:,0],bins), _edges(x[:,1],bins)
        shape = (len(ex)-1,len(ey)-1)
        im = np.ravel_multi_index((_indices(x[:,0],ex),_indices(x[:,1],ey)),shape)
        it = np.ravel_multi_index((_indices(d[:,0],ex),_indices(d[:,1],ey)),shape)
        mc = np.bincount(im,minlength=np.prod(shape)).reshape(shape)
        ds = np.bincount(it,weights=sw,minlength=np.prod(shape)).reshape(shape)
        ds2 = np.bincount(it,weights=sw**2,minlength=np.prod(shape)).reshape(shape)
        neff = np.divide(ds**2,ds2,out=np.zeros(shape),where=ds2>0)
        valid = bool(np.all(mc>=min_mc) and np.all(ds>0) and np.all(neff>=min_target_neff))
        attempts.append({'requested_bins_per_axis':bins,'shape':list(shape),'accepted':valid,
                         'nonpositive_target_cells':int((ds<=0).sum()),'minimum_mc':int(mc.min()),
                         'minimum_target_neff':float(neff.min()),'target_sumw':ds.tolist(),
                         'target_sumw2':ds2.tolist(),'target_neff':neff.tolist()})
        if valid:
            ratio = (ds/ds.sum()) / (mc/mc.sum())
            return {'x_edges':[float(v) if np.isfinite(v) else str(v) for v in ex],'y_edges':[float(v) if np.isfinite(v) else str(v) for v in ey],'ratio':ratio.tolist(),
                    'mc_counts':mc.tolist(),'target_sumw':ds.tolist(),'target_sumw2':ds2.tolist(),
                    'training_rows':len(x),'target_rows':len(d),'target_negative_rows':int((sw<0).sum()),
                    'target_sum_weights':float(sw.sum()),'target_effective_entries':effective_entries(sw),
                    'axis':'signed_y','feature_order':['phi_pt','phi_y'],'edge_policy':'infinite train-quantile tail bins',
                    'fit_partition':'training','attempts':attempts,
                    'training_feature_min':x.min(axis=0).tolist(),'training_feature_max':x.max(axis=0).tolist(),
                    'target_outside_training_box_rows':int(((d<x.min(axis=0))|(d>x.max(axis=0))).any(axis=1).sum()),
                    'target_outside_training_box_sumw':float(sw[((d<x.min(axis=0))|(d>x.max(axis=0))).any(axis=1)].sum()),
                    'target_outside_training_box_sumw2':float(np.sum(sw[((d<x.min(axis=0))|(d>x.max(axis=0))).any(axis=1)]**2)),
                    'support_caveat':'Infinite tail bins absorb all target rows; weights cannot generate MC events in unsupported tails; bounding box is not a full support test'}
    raise ValueError('Even inclusive bin fails positive signed target/statistics requirements')

def apply_map(frame, mapping):
    """Apply a fitted map, including its frozen training scalar if present."""
    x=frame[['phi_pt','phi_y']].to_numpy(float)
    if not np.isfinite(x).all(): raise ValueError('Nonfinite RECO features')
    ratio=np.asarray(mapping['ratio'])
    w=ratio[_indices(x[:,0],mapping['x_edges']),_indices(x[:,1],mapping['y_edges'])] * float(mapping.get('application_normalization',1.))
    if not np.isfinite(w).all() or np.any(w<=0): raise ValueError('Invalid map weights')
    return w

def build_weights(mc, target):
    validate_keys(mc)
    if not np.isfinite(mc.input_weight).all() or (mc.input_weight<=0).any():
        raise ValueError('Original input exposure weights must be finite and positive')
    result=mc.copy(); result['phi_shape_weight']=np.nan; maps={}; report={}
    for sample, rows in result.groupby('sample',sort=False):
        mapping=fit_map(rows[rows.partition=='training'],target)
        raw=apply_map(rows,mapping)
        # Freeze the normalization from training only. Held-out sums may fluctuate;
        # original input exposure weights remain unchanged in every partition.
        train=rows.partition.to_numpy()=='training'
        scale=float(train.sum()/raw[train].sum()); w=raw*scale
        result.loc[rows.index,'phi_shape_weight']=w
        mapping['application_normalization']=scale
        mapping['normalization_partition']='training'
        mapping['correction_is_trivial']=bool(np.asarray(mapping['ratio']).size==1)
        maps[sample]=mapping
        report[sample]={'rows':len(rows),'training_rows':int((rows.partition=='training').sum()),
                        'training_mean_phi_shape_weight':float(w[train].mean()),
                        'sum_shape_weights':float(w.sum()),'effective_entries':effective_entries(w),
                        'minimum_weight':float(w.min()),'maximum_weight':float(w.max()),
                        'application_outside_training_box_rows':int(((rows[['phi_pt','phi_y']].to_numpy()<np.asarray(mapping['training_feature_min'])) | (rows[['phi_pt','phi_y']].to_numpy()>np.asarray(mapping['training_feature_max']))).any(axis=1).sum()),
                        'sum_input_weight_before':float(rows.input_weight.sum()),
                        'sum_input_weight_after':float(np.dot(rows.input_weight,w)),
                        'partition_summaries':{name:{'rows':int(mask.sum()),'sum_phi_shape_weight':float(w[mask].sum()),
                            'effective_entries':effective_entries(w[mask]),'minimum_weight':float(w[mask].min()),'maximum_weight':float(w[mask].max()),'sum_input_weight_before':float(rows.loc[mask,'input_weight'].sum()),
                            'sum_input_weight_after':float(np.dot(rows.loc[mask,'input_weight'],w[mask]))}
                            for name in rows.partition.unique() for mask in [rows.partition.to_numpy()==name]}}
    if not np.isfinite(result.phi_shape_weight).all(): raise ValueError('Incomplete weight coverage')
    return result,maps,report

def data_target(path):
    import uproot
    with uproot.open(path, handler=uproot.source.file.MultithreadedFileSource, num_workers=1) as root:
        a=root['selected'].arrays(['sel_Phi_pt','sel_Phi_px','sel_Phi_py','sel_Phi_pz','sel_Phi_mass','sel_Phi_y','signal_sw'],library='np')
    y=rapidity(a['sel_Phi_px'],a['sel_Phi_py'],a['sel_Phi_pz'],a['sel_Phi_mass'])
    if not np.allclose(y,a['sel_Phi_y'],rtol=1e-6,atol=1e-6): raise ValueError('Stored/data RECO y disagree')
    f=pd.DataFrame({'source_file':str(Path(path).resolve()),'entry':np.arange(len(y)),
                    'phi_pt':a['sel_Phi_pt'],'phi_y':y,'signal_sw':a['signal_sw']})
    if not np.isfinite(f[['phi_pt','phi_y','signal_sw']].to_numpy()).all(): raise ValueError('Invalid data target')
    return f

def extract_local(mc, parquet_root, raw_root):
    """Recover exact original best-quality candidate; absent sources remain NaN."""
    import uproot
    import awkward as ak
    result=mc.copy(); result['phi_y']=np.nan; result['candidate_index']=-1
    result['reco_source_status']='missing_raw_source'
    for column in ['reco_jpsi_slot1_mass','reco_jpsi_slot2_mass','reco_phi_mass']: result[column]=np.nan
    for sample, rows in result.groupby('sample',sort=False):
        cfg=json.loads((Path(parquet_root)/('JJP_'+sample)/'configuration_metadata.json').read_text())['efficiency_definition']['offline_selection']
        for file_index,(source, events) in enumerate(rows.groupby('source_file',sort=False)):
            original=Path(source)
            if str(raw_root)=='REMOTE':
                raw=source
            else:
                raw=Path(raw_root)/('JJP_'+sample)/original.name
                if not raw.exists() and original.exists(): raw=original
                if not raw.exists(): continue
            branches=['Phi_'+k for k in ['pt','px','py','pz','mass','VtxProb','K_1_RecoKaonTrackIdx','K_2_RecoKaonTrackIdx']]
            for p in ['Jpsi_1','Jpsi_2']: branches += [p+'_'+k for k in ['pt','px','py','pz','mass','VtxProb']]
            branches += ['RecoKaonTrack_'+k for k in ['normalizedChi2','numberOfHits','isHighPurity']]
            options={'handler':uproot.source.xrootd.XRootDSource,'num_workers':1,'timeout':30} if str(raw).startswith('root://') else {'handler':uproot.source.file.MultithreadedFileSource,'num_workers':1}
            with uproot.open(raw, **options) as root:
                tree=root['X_data'] if 'X_data' in root else root['mkcands/X_data']
                arr=tree.arrays(branches,library='ak')
            for idx,row in events.iterrows():
                ev={k:ak.to_numpy(arr[k][int(row.entry)]) for k in branches}
                n=len(ev['Phi_pt']); quality=np.ones(n,dtype=bool)
                for p in ['Jpsi_1','Jpsi_2']:
                    y=rapidity(*(ev[p+'_'+k] for k in ['px','py','pz','mass']))
                    quality &= (ev[p+'_mass']>=cfg['jpsi_mass_window'][0]) & (ev[p+'_mass']<=cfg['jpsi_mass_window'][1]) & (ev[p+'_pt']>cfg['jpsi_pt_min']) & (abs(y)<cfg['jpsi_abs_y_max']) & (ev[p+'_VtxProb']>cfg['jpsi_vtxprob_min'])
                quality &= (ev['Phi_mass']>=cfg['phi_mass_window'][0]) & (ev['Phi_mass']<=cfg['phi_mass_window'][1]) & (ev['Phi_pt']>cfg['phi_pt_min']) & (ev['Phi_VtxProb']>cfg['phi_vtxprob_min'])
                for leg in ['1','2']:
                    ix=ev['Phi_K_'+leg+'_RecoKaonTrackIdx'].astype(int)
                    good=(ix>=0)&(ix<len(ev['RecoKaonTrack_normalizedChi2']))
                    safe=np.clip(ix,0,max(0,len(ev['RecoKaonTrack_normalizedChi2'])-1))
                    quality &= good & (ev['RecoKaonTrack_normalizedChi2'][safe]<cfg['kaon_chi2_max']) & (ev['RecoKaonTrack_numberOfHits'][safe]>cfg['kaon_n_valid_hits_min'])
                    if cfg['kaon_require_highpurity']: quality &= ev['RecoKaonTrack_isHighPurity'][safe].astype(bool)
                scores=ev['Jpsi_1_pt']**2+ev['Jpsi_2_pt']**2+ev['Phi_pt']**2
                if not quality.any(): raise ValueError('Original selected event has no quality candidate')
                best=int(np.argmax(np.where(quality,scores,-1.)))
                pts=sorted([ev['Jpsi_1_pt'][best],ev['Jpsi_2_pt'][best]],reverse=True)
                if not np.allclose([*pts,ev['Phi_pt'][best]],[row.jpsi1_pt,row.jpsi2_pt,row.phi_pt],rtol=2e-6,atol=1e-6): raise ValueError('Candidate identity mismatch')
                y=float(rapidity(*(ev['Phi_'+k][best] for k in ['px','py','pz','mass'])))
                if not np.isfinite(y): raise ValueError('Nonfinite RECO y')
                result.loc[idx,['phi_y','candidate_index','reco_source_status']]=[y,best,'verified_raw_best_quality']
                result.loc[idx,['reco_jpsi_slot1_mass','reco_jpsi_slot2_mass','reco_phi_mass']]=[ev['Jpsi_1_mass'][best],ev['Jpsi_2_mass'][best],ev['Phi_mass'][best]]
            if (file_index+1)%25==0: print('files',sample,file_index+1,'recovered',int(result.loc[rows.index,'phi_y'].notna().sum()),flush=True)
        print(sample,len(rows),int(result.loc[rows.index,'phi_y'].notna().sum()),flush=True)
    return result

def extract_unique_pt(mc, parquet_root, raw_root):
    """Recover original candidate by an unambiguous saved three-pT identity.

    Original event flags are authoritative for quality/ranking/GEN matching.
    Ambiguous or absent triplets use the independently evaluated full-quality
    reader above; a tolerant unique identity never substitutes GEN quantities.
    """
    import uproot
    import awkward as ak
    result=mc.copy()
    for c in ['phi_y','reco_jpsi_slot1_mass','reco_jpsi_slot2_mass','reco_phi_mass']: result[c]=np.nan
    result['candidate_index']=-1;result['reco_source_status']='missing_raw_source'
    for sample,rows in result.groupby('sample',sort=False):
        for file_index,(source,events) in enumerate(rows.groupby('source_file',sort=False)):
            original=Path(source)
            if str(raw_root)=='REMOTE': raw=source
            else:
                raw=Path(raw_root)/('JJP_'+sample)/original.name
                if not raw.exists() and original.exists(): raw=original
                if not raw.exists(): continue
            branches=['Phi_pt','Phi_px','Phi_py','Phi_pz','Phi_mass','Jpsi_1_pt','Jpsi_2_pt','Jpsi_1_mass','Jpsi_2_mass']
            options={'handler':uproot.source.xrootd.XRootDSource,'num_workers':1,'timeout':30} if str(raw).startswith('root://') else {'handler':uproot.source.file.MultithreadedFileSource,'num_workers':1}
            with uproot.open(raw,**options) as root:
                tree=root['X_data'] if 'X_data' in root else root['mkcands/X_data']
                arr=tree.arrays(branches,library='ak')
            fallback=[]
            for idx,row in events.iterrows():
                ev={k:ak.to_numpy(arr[k][int(row.entry)]) for k in branches}
                lead=np.maximum(ev['Jpsi_1_pt'],ev['Jpsi_2_pt'])
                sub=np.minimum(ev['Jpsi_1_pt'],ev['Jpsi_2_pt'])
                match=np.isclose(lead,row.jpsi1_pt,rtol=2e-6,atol=1e-6)&np.isclose(sub,row.jpsi2_pt,rtol=2e-6,atol=1e-6)&np.isclose(ev['Phi_pt'],row.phi_pt,rtol=2e-6,atol=1e-6)
                candidates=np.flatnonzero(match)
                if len(candidates)!=1:
                    fallback.append(idx);continue
                best=int(candidates[0])
                y=float(rapidity(*(ev['Phi_'+k][best] for k in ['px','py','pz','mass'])))
                if not np.isfinite(y): raise ValueError('Nonfinite RECO y')
                result.loc[idx,['phi_y','candidate_index','reco_source_status']]=[y,best,'verified_raw_unique_three_pt']
                result.loc[idx,['reco_jpsi_slot1_mass','reco_jpsi_slot2_mass','reco_phi_mass']]=[ev['Jpsi_1_mass'][best],ev['Jpsi_2_mass'][best],ev['Phi_mass'][best]]
            if fallback:
                verified=extract_local(events.loc[fallback],parquet_root,raw_root)
                cols=['phi_y','candidate_index','reco_source_status','reco_jpsi_slot1_mass','reco_jpsi_slot2_mass','reco_phi_mass']
                result.loc[fallback,cols]=verified[cols]
            if (file_index+1)%25==0: print('fast_files',sample,file_index+1,'recovered',int(result.loc[rows.index,'phi_y'].notna().sum()),flush=True)
        print('fast_complete',sample,len(rows),int(result.loc[rows.index,'phi_y'].notna().sum()),flush=True)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--split',type=Path,required=True);p.add_argument('--parquet-root',type=Path,required=True)
    p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--data',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    if (args.output_dir/'input_status.json').exists(): raise FileExistsError('Use a fresh output directory')
    mc=pd.read_parquet(args.split);validate_keys(mc)
    target=data_target(args.data);target.to_parquet(args.output_dir/'data_phi_target.parquet',index=False)
    features=extract_local(mc,args.parquet_root,args.raw_root)
    features.to_parquet(args.output_dir/'mc_phi_features.parquet',index=False)
    counts=features.groupby('sample').agg(rows=('entry','size'),finite_reco_y=('phi_y','count')).to_dict('index')
    status={'samples':counts,'genWeight':1,'axis':'joint (phi_pt, signed phi_y)',
            'input_weight':'original Nref/Nsource unchanged','scope':'exploratory sPlot-model-sensitive shape study; not nominal certification','complete':bool(features.phi_y.notna().all()),
            'data_rows':len(target),'data_negative_weight_rows':int((target.signal_sw<0).sum()),
            'data_sum_weights':float(target.signal_sw.sum()),'data_effective_entries':effective_entries(target.signal_sw),
            'selection':'Exact original quality and first maximum sum(pT^2), verified against original split three RECO pT',
            'source_split':str(args.split),'missing_sources':features.loc[features.phi_y.isna(),KEYS[:2]].drop_duplicates().to_dict('records')}
    if status['complete']:
        weighted,maps,report=build_weights(features,target)
        weighted.to_parquet(args.output_dir/'phi_shape_weights.parquet',index=False)
        # Infinite tail edges are portable string values, restored by _indices.
        (args.output_dir/'phi_maps.json').write_text(json.dumps(maps,indent=2,allow_nan=False)+'\n')
        status['weight_report']=report
    else:
        status['blocked_reason']='Missing raw RECO four-vectors for historical remote sources; no GEN-y substitution performed'
    (args.output_dir/'input_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps({k:v for k,v in status.items() if k!='missing_sources'},indent=2))
if __name__=='__main__': main()

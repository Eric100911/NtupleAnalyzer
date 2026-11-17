"""Paired data-map bootstrap building block, conditional on the frozen booster."""
import json
from pathlib import Path
import numpy as np


def _fit_record(result):
    parameters=result.floatParsFinal()
    names=[p.GetName() for p in parameters]
    covariance=np.array([[result.covarianceMatrix()[i][j] for j in range(len(names))] for i in range(len(names))])
    return {'parameter_names':names,'parameter_values':[float(p.getVal()) for p in parameters],
            'parameter_covariance':covariance.tolist(),'status':int(result.status()),
            'covQual':int(result.covQual()),'edm':float(result.edm())}


def refit_phi_maps(masses,phi_pt,phi_y,mc_frame,*,indices=None,config=None,output_dir=None):
    """Refit inclusive masses and signed target, then training-only phi maps.

    Returned signal weights have the order of indices (duplicates preserved).
    MC keys/partitions are unchanged. This helper does not retrain the booster,
    fit production yields, or supply an independent prior from the same data.
    Failed replicas are raised and, when requested, saved as failure.json.
    """
    output=None if output_dir is None else Path(output_dir)
    if output is not None: output.mkdir(parents=True,exist_ok=False)
    try:
        return _refit(masses,phi_pt,phi_y,mc_frame,indices,config or {},output)
    except Exception as error:
        if output is not None:
            (output/'failure.json').write_text(json.dumps({'success':False,'error':str(error),
                'scope':'downstream map refit with fixed booster; replica must not be silently accepted'},indent=2)+'\n')
        raise


def _refit(masses,phi_pt,phi_y,mc_frame,indices,config,output):
    import ROOT
    import pandas as pd
    from scripts.kinematics.fit_splot import build_jjp_model
    from scripts.templates.phi_kinematic_reweight import build_weights
    masses,pt,y=map(lambda a:np.asarray(a,float),(masses,phi_pt,phi_y))
    if masses.ndim!=2 or masses.shape[1]!=3 or pt.shape!=(len(masses),) or y.shape!=pt.shape:
        raise ValueError('Expected raw masses Nx3 and matching phi vectors')
    if not all(np.isfinite(a).all() for a in (masses,pt,y)):
        raise ValueError('Nonfinite raw map-refit inputs')
    if indices is None: indices=np.arange(len(masses))
    indices=np.asarray(indices)
    if indices.ndim!=1 or not np.issubdtype(indices.dtype,np.integer) or np.any(indices<0) or np.any(indices>=len(masses)) or not len(indices):
        raise ValueError('Nonempty valid integer bootstrap indices required')
    masses,pt,y=masses[indices],pt[indices],y[indices]
    windows=np.asarray([config.get('jpsi_mass_window',[2.9,3.3])]*2+[config.get('phi_mass_window',[.99,1.07])],float)
    if np.any(masses<windows[:,0]) or np.any(masses>windows[:,1]):
        raise ValueError('Mass window mismatch; no bootstrap rows may be silently dropped')
    ROOT.gROOT.SetBatch(True)
    ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.WARNING)
    model,observables,yields,signal,keep=build_jjp_model(len(masses),
        jpsi_background=config.get('jpsi_background','exponential'),
        jpsi_mass_window=tuple(windows[0]),phi_mass_window=tuple(windows[2]))
    data=ROOT.RooDataSet.from_numpy(dict(zip(observables,masses.T)),list(observables.values()))
    keep.extend([model,data])
    options=[ROOT.RooFit.Save(True),ROOT.RooFit.Extended(True),ROOT.RooFit.Strategy(2),
             ROOT.RooFit.NumCPU(1),ROOT.RooFit.PrintLevel(-1)]
    inclusive=model.fitTo(data,*options); keep.append(inclusive)
    inclusive_record=_fit_record(inclusive)
    threshold=float(config.get('max_edm',1e-3))
    def check(record,stage):
        if record['status']!=0 or record['covQual']<3 or not np.isfinite(record['edm']) or record['edm']>=threshold:
            raise RuntimeError(f'{stage} unreliable: status={record["status"]}, covQual={record["covQual"]}, EDM={record["edm"]}')
    check(inclusive_record,'Inclusive all-shape mass fit')
    inclusive_yield=float(yields[signal].getVal())
    parameters=model.getParameters(data)
    for parameter in parameters:
        if parameter.GetName() not in yields: parameter.setConstant(True)
    conditional=model.fitTo(data,*options); keep.append(conditional)
    conditional_record=_fit_record(conditional); check(conditional_record,'Conditional yield-only fit')
    splot=ROOT.RooStats.SPlot('map_splot','map_splot',data,model,ROOT.RooArgList(*yields.values()))
    keep.append(splot)
    sw=np.array([splot.GetSWeight(i,signal) for i in range(len(masses))])
    if not np.isfinite(sw).all(): raise RuntimeError('Nonfinite signed target weights')
    conditional_yield=float(yields[signal].getVal())
    if not np.isclose(sw.sum(),conditional_yield,rtol=2e-3,atol=.05):
        raise RuntimeError('SPlot signal-sum identity failed')
    target=pd.DataFrame({'phi_pt':pt,'phi_y':y,'signal_sw':sw})
    weighted,maps,report=build_weights(mc_frame,target)
    diagnostics={'success':True,'inclusive':inclusive_record,'conditional':conditional_record,
        'inclusive_signal_yield':inclusive_yield,'conditional_signal_yield':conditional_yield,
        'signal_sumw':float(sw.sum()),'signal_sumw2':float(sw@sw),'negative_weights':int((sw<0).sum()),
        'rows':len(sw),'map_fit_partition':'training','booster':'frozen; never retrained',
        'scope':'downstream paired data-map dependence conditional on fixed classifier; does not propagate training-map dependence'}
    artifacts={}
    if output is not None:
        root=ROOT.TFile(str(output/'inclusive_map_fit.root'),'RECREATE')
        inclusive.Write('inclusive_all_shapes'); conditional.Write('conditional_yield_only'); root.Close()
        np.savez_compressed(output/'map_refit_arrays.npz',indices=indices,signal_sw=sw,
            inclusive_names=inclusive_record['parameter_names'],inclusive_covariance=inclusive_record['parameter_covariance'],
            conditional_names=conditional_record['parameter_names'],conditional_covariance=conditional_record['parameter_covariance'])
        (output/'diagnostics.json').write_text(json.dumps(diagnostics,indent=2)+'\n')
        (output/'maps.json').write_text(json.dumps({'maps':maps,'report':report},indent=2)+'\n')
        artifacts={'root':str(output/'inclusive_map_fit.root'),'arrays':str(output/'map_refit_arrays.npz'),
                   'diagnostics':str(output/'diagnostics.json'),'maps':str(output/'maps.json')}
    return {'weighted_mc':weighted,'maps':maps,'report':report,'diagnostics':diagnostics,
            'signal_sw':sw,'inclusive_fit':inclusive_record,'conditional_fit':conditional_record,'artifact_paths':artifacts}

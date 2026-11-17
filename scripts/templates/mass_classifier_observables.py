"""Independent mass-extracted distributions and common-normalization overlays."""
import json
from pathlib import Path
import numpy as np
from scripts.templates.fit_correlation_components import make_template
from scripts.templates.train_multiclass_xgboost import CLASS_ORDER

# Fixed across all projections; gray is reserved for uncertainty bands.
COMPONENT_COLORS = ('#3f90da', '#ffa90e', '#bd1f01', '#832db6', '#a96b59', '#92dadd')


def observable_label(name):
    """Physics labels for the actual nominal-mass feature definitions."""
    pairs={'jj':r'J/\psi_1,J/\psi_2','j1phi':r'J/\psi_1,\phi','j2phi':r'J/\psi_2,\phi'}
    for suffix,pair in pairs.items():
        if name=='dphi_'+suffix: return rf'$|\Delta\phi({pair})|$ [rad]'
        if name=='dy_'+suffix: return rf'$|\Delta y({pair})|$'
        if name=='dr_'+suffix: return rf'$\Delta R_{{\eta\phi}}({pair})$'
    systems={'jj':r'J/\psi_1+J/\psi_2','j1phi':r'J/\psi_1+\phi','j2phi':r'J/\psi_2+\phi','jjp':r'J/\psi_1+J/\psi_2+\phi'}
    for suffix,system in systems.items():
        if name=='pt_'+suffix: return rf'$p_T({system})$ [GeV]'
        if name=='m_'+suffix: return rf'$m({system})$ [GeV]'
    labels={'absy_jjp':rf'$|y({systems["jjp"]})|$',
            'sumpt_jjp':r'$p_T(J/\psi_1)+p_T(J/\psi_2)+p_T(\phi)$ [GeV]',
            'sumdr2':r'$\sum_{i<j}(\Delta R_{\eta\phi,ij})^2$',
            'maxdr_jjp':r'$\max_{i<j}\Delta R_{\eta\phi,ij}$',
            'jpsi1_pt':r'$p_T(J/\psi_1)$ [GeV]','jpsi2_pt':r'$p_T(J/\psi_2)$ [GeV]'}
    if name.startswith('score_'): return name[6:].replace('_',' ')+' classifier score'
    return labels.get(name,name)


def observable_inventory():
    from scripts.templates.train_full_correlation_xgboost import FEATURE_NAMES
    return {'scores': ['score_'+name for name in CLASS_ORDER],
            'features': [name for name in FEATURE_NAMES if name != 'phi_pt']}


def _categories(values, edges):
    x,e=np.asarray(values,float),np.asarray(edges,float)
    if x.ndim!=1 or e.ndim!=1 or len(e)<2 or not np.isfinite(e).all() or np.any(np.diff(e)<=0):
        raise ValueError('Finite increasing edges and a value vector required')
    if not np.isfinite(x).all() or np.any(x<e[0]) or np.any(x>e[-1]):
        raise ValueError('Observable outside declared range: include explicit overflow coverage; no silent renormalization')
    return np.minimum(np.searchsorted(e,x,side='right')-1,len(e)-2)


def build_observable_templates(values_by_class,edges,weights_by_class=None):
    if len(values_by_class)!=6: raise ValueError('Exactly six classes in frozen CLASS_ORDER required')
    shapes,covariances=[],[]
    for i,values in enumerate(values_by_class):
        _categories(values,edges)
        w=np.ones(len(values)) if weights_by_class is None else np.asarray(weights_by_class[i],float)
        if w.shape!=np.asarray(values).shape or not np.isfinite(w).all() or np.any(w<0):
            raise ValueError('Finite nonnegative template weights required')
        shape,metadata=make_template({'x':np.asarray(values),'w':w},np.asarray(edges))
        shapes.append(shape); covariances.append(metadata['normalized_covariance'])
    return np.asarray(shapes).T,np.asarray(covariances)


def extract_observable_distribution(values,edges,*,masses=None,fit_function=None,config=None,output_dir=None,pure_signal=False):
    categories=_categories(values,edges); bins=len(edges)-1
    if pure_signal:
        counts=np.bincount(categories,minlength=bins).astype(float)
        fit={'signal_yields':counts.tolist(),'signal_covariance':np.diag(counts).tolist(),
             'diagnostics':{'scope':'direct truth-signal counts; independent Poisson covariance'}}
    else:
        if masses is None or np.asarray(masses).shape!=(len(categories),3):
            raise ValueError('Raw Nx3 masses required')
        if fit_function is None:
            from scripts.templates.response_mass_fit import fit_simultaneous_masses
            fit_function=fit_simultaneous_masses
        fit=fit_function(masses,categories,bins,response_templates=None,config=config,output_dir=output_dir)
    return {'signal_yields':fit['signal_yields'],'signal_covariance':fit['signal_covariance'],
            'edges':np.asarray(edges,float).tolist(),'fit':fit,'class_order':list(CLASS_ORDER),
            'extraction_kind':'truth_signal_counts' if pure_signal else 'simultaneous_mass_fit'}


def plot_signal_mixture(output_dir,extraction,class_yields,class_covariance,templates,*,
                        template_covariance=None,cross_covariance=None,
                        joint_prediction_covariance=None,observable='observable',profile_intervals=None,
                        min_prediction=1.,allow_unreliable=False,axis_label=None,simulation=False,signal_upper_limits=None):
    """T is Bx6; template covariance is 6xBxB, conditional independent of Nc.

    A supplied joint_prediction_covariance replaces delta-method prediction V.
    cross_covariance is Cov(mass-extracted Y, prediction P), not a correlation.
    Render yield per unit interval. Integrated values stay in the original JSON
    fields; width-scaled values and covariances live in differential_yield.
    """
    reliable=extraction.get('fit',{}).get('diagnostics',{}).get('reliable',True)
    if reliable is False and not allow_unreliable:
        raise ValueError('Refusing nominal plot of explicitly unreliable mass fit')
    if min_prediction<=0: raise ValueError('Positive ratio support threshold required')
    output=Path(output_dir)
    n,v,t=map(lambda a: np.asarray(a,float),(class_yields,class_covariance,templates))
    y=np.asarray(extraction['signal_yields'],float); vy=np.asarray(extraction['signal_covariance'],float)
    edges=np.asarray(extraction['edges'],float); bins=len(y)
    if n.shape!=(6,) or v.shape!=(6,6) or t.shape!=(bins,6) or vy.shape!=(bins,bins) or len(edges)!=bins+1:
        raise ValueError('Invalid class/template/covariance dimensions')
    if np.any(t<0) or not np.allclose(t.sum(axis=0),1):
        raise ValueError('Templates must preserve common full selected normalization')
    components=t*n; prediction=components.sum(axis=1); vp=t@v@t.T
    if template_covariance is not None:
        tc=np.asarray(template_covariance,float)
        if tc.shape!=(6,bins,bins): raise ValueError('Template covariance shape mismatch')
        vp+=np.einsum('c,cij->ij',n*n,tc)
    if joint_prediction_covariance is not None: vp=np.asarray(joint_prediction_covariance,float)
    if vp.shape!=(bins,bins) or not all(np.isfinite(a).all() for a in (n,v,t,y,vy,vp)):
        raise ValueError('Finite predictions and matching covariance dimensions required')
    residual_covariance=None
    if cross_covariance is not None:
        cross=np.asarray(cross_covariance,float)
        if cross.shape!=(bins,bins): raise ValueError('Cross covariance shape mismatch')
        residual_covariance=vy+vp-cross-cross.T
    error=np.tile(np.sqrt(np.maximum(np.diag(vy),0)),(2,1))
    if profile_intervals is None:
        profiles=extraction.get('fit',{}).get('profiles',{})
        available=[profiles.get(f'Y_sss_bin{j}',{}) for j in range(bins)]
        for j,item in enumerate(available):
            if item.get('valid',False):
                error[:,j]=[-item['lower_error'],item['upper_error']]
    if profile_intervals is not None:
        intervals=np.asarray(profile_intervals,float)
        if intervals.shape!=(bins,2): raise ValueError('Profile intervals must be Bx2 endpoints')
        error=np.vstack((y-intervals[:,0],intervals[:,1]-y))
    empty_categories=extraction.get('fit',{}).get('diagnostics',{}).get('empty_categories',[])
    label=axis_label or observable_label(observable)
    result={'signal_yields':y.tolist(),'signal_covariance':vy.tolist(),'prediction':prediction.tolist(),
            'prediction_covariance':vp.tolist(),'components':components.tolist(),'class_order':list(CLASS_ORDER),
            'edges':edges.tolist(),'residual_covariance':None if residual_covariance is None else residual_covariance.tolist(),
            'axis_label':label,'observable':observable,
            'signal_errors':error.tolist(),
            'extraction_kind':extraction.get('extraction_kind','simultaneous_mass_fit'),
            'simulation':bool(simulation),
            'component_colors':dict(zip(CLASS_ORDER,COMPONENT_COLORS)),
            'significance_available':False,'uncertainty_scope':'conditional fitted-yield and independent per-class template covariance; supply joint prediction covariance for dependence',
            'mass_fit_reliable':bool(reliable),'ratio_min_prediction':float(min_prediction),
            'masked_signal_bins':list(map(int,empty_categories)),
            'masked_signal_reason':'empty free-SSS mass categories have no regular Hessian error',
            'artifacts':[str(output/'signal_mixture.png'),str(output/'signal_mixture.pdf')]}
    if residual_covariance is not None:
        delta=y-prediction
        result['residual_quadratic']=float(delta@np.linalg.pinv(residual_covariance)@delta)
        result['residual_quadratic_scope']='descriptive; no calibrated p-value or significance'
    limits=signal_upper_limits if signal_upper_limits is not None else extraction.get('signal_upper_limits')
    if limits is not None: result['signal_upper_limits']=limits
    validate_plot_axes(result,resolve_plot_settings(result,observable))
    output.mkdir(parents=True,exist_ok=False)
    _render_signal_mixture(output,result)
    return result


def resolve_plot_settings(plots, observable):
    """Resolve independent height and axis settings; observable keys override globals."""
    height=plots.get('plot_height_per_unit_interval',True)
    if not isinstance(plots.get('plot_axis_scaling',{}),dict) or not isinstance(plots.get('observables',{}),dict): raise ValueError('Plot axes and observable overrides must be mappings')
    scaling=dict(plots.get('plot_axis_scaling',{}))
    override=plots.get('observables',{}).get(observable,{})
    if not isinstance(override,dict): raise ValueError('Observable plot override must be a mapping')
    height=override.get('plot_height_per_unit_interval',height)
    if not isinstance(override.get('plot_axis_scaling',{}),dict): raise ValueError('Observable plot axes must be a mapping')
    scaling.update(override.get('plot_axis_scaling',{}))
    limits=plots.get('plot_axis_limits',{})
    if not isinstance(limits,dict) or not isinstance(override.get('plot_axis_limits',{}),dict): raise ValueError('plot_axis_limits must be a mapping')
    limits=dict(limits); limits.update(override.get('plot_axis_limits',{}))
    if set(limits)-{'x_min','x_max','y_min','y_max'}: raise ValueError('plot_axis_limits allows x_min/x_max/y_min/y_max')
    for key,value in limits.items():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value): raise ValueError('Display limits must be finite numbers')
    for axis in ('x','y'):
        if axis+'_min' in limits and axis+'_max' in limits and limits[axis+'_min']>=limits[axis+'_max']: raise ValueError('Display maximum must exceed minimum')
    if not isinstance(height,bool): raise ValueError('plot_height_per_unit_interval must be boolean')
    if set(scaling)-{'x','y'} or any(v not in ('linear','log') for v in scaling.values()):
        raise ValueError('plot_axis_scaling allows x/y: linear or log')
    return {'plot_height_per_unit_interval':height,'plot_axis_scaling':{'x':scaling.get('x','linear'),'y':scaling.get('y','linear')},'plot_axis_limits':limits}


def validate_plot_axes(result, settings):
    """Reject unrepresentable log coordinates without changing scientific bins."""
    edges=np.asarray(result['edges'],float)
    if edges.ndim!=1 or len(edges)<2 or not np.isfinite(edges).all() or np.any(np.diff(edges)<=0): raise ValueError('Finite increasing bin edges required')
    bins=len(edges)-1
    for key,shape in [('signal_yields',(bins,)),('prediction',(bins,)),('components',(bins,6)),('signal_covariance',(bins,bins)),('prediction_covariance',(bins,bins))]:
        array=np.asarray(result[key],float)
        if array.shape!=shape or not np.isfinite(array).all(): raise ValueError('Finite plot inputs with matching bin dimensions required')
    error=np.asarray(result.get('signal_errors',np.tile(np.sqrt(np.maximum(np.diag(result['signal_covariance']),0)),(2,1))),float)
    if error.shape!=(2,bins) or not np.isfinite(error).all() or np.any(error<0): raise ValueError('Nonnegative finite 2xB signal errors required')
    limits=settings['plot_axis_limits']
    if settings['plot_axis_scaling']['x']=='log':
        if np.any(edges<0) or (np.any(edges==0) and limits.get('x_min',0)<=0):
            raise ValueError('Log x requires positive edges, or a zero first edge with explicit positive x_min; negative edges are unsupported')
        if limits.get('x_min',edges[0])<=0 or limits.get('x_max',edges[-1])<=0: raise ValueError('Log x display limits must be positive')
    if settings['plot_axis_scaling']['y']=='log':
        if limits.get('y_min',0)<=0 or ('y_max' in limits and limits['y_max']<=0): raise ValueError('Log y requires explicit positive y_min and positive y_max if supplied')
        if np.any(np.asarray(result['components'])<0): raise ValueError('Log y stacked components must be nonnegative')
    if limits.get('x_min',edges[0])>=limits.get('x_max',edges[-1]): raise ValueError('Display x limits do not define an increasing range')
    upper=result.get('signal_upper_limits')
    if upper is not None:
        if not isinstance(upper,list) or len(upper)!=len(result['signal_yields']): raise ValueError('signal_upper_limits must have one null or explicit bound per bin')
        for item in upper:
            if item is None: continue
            if (not isinstance(item,dict) or set(item)-{'value','confidence_level','method','provenance'} or
                    not isinstance(item.get('value'),(int,float)) or isinstance(item['value'],bool) or not np.isfinite(item['value']) or item['value']<=0 or
                    not isinstance(item.get('confidence_level'),(int,float)) or not 0<item['confidence_level']<1 or
                    ('method' in item and not isinstance(item['method'],str)) or ('provenance' in item and not isinstance(item['provenance'],str))):
                raise ValueError('Explicit upper limits require positive value and confidence_level in (0,1), with optional method')


def _render_signal_mixture(output, result):
    """Draw dN/dx; keep saved integrated yields and likelihood covariances intact."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import mplhep as hep
    edges=np.asarray(result['edges'],float); widths=np.diff(edges)
    y=np.asarray(result['signal_yields'],float); bins=len(y)
    prediction=np.asarray(result['prediction'],float)
    components=np.asarray(result['components'],float)
    vy=np.asarray(result['signal_covariance'],float)
    vp=np.asarray(result['prediction_covariance'],float)
    if (edges.shape!=(bins+1,) or not np.isfinite(edges).all() or np.any(widths<=0)
            or prediction.shape!=(bins,) or components.shape!=(bins,6)
            or vy.shape!=(bins,bins) or vp.shape!=(bins,bins)):
        raise ValueError('Finite increasing bin edges and matching plot dimensions required')
    error=np.asarray(result.get('signal_errors',np.tile(np.sqrt(np.maximum(np.diag(vy),0)),(2,1))),float)
    if error.shape!=(2,bins) or not all(np.isfinite(a).all() for a in (y,prediction,components,vy,vp,error)) or np.any(error<0):
        raise ValueError('Finite plot inputs and nonnegative 2xB signal errors required')
    result.setdefault('signal_errors',error.tolist())
    label=result.get('axis_label','observable')
    unit='GeV' if label.endswith('[GeV]') else 'rad' if label.endswith('[rad]') else 'unit interval'
    covariance_scale=widths[:,None]*widths[None,:]
    density={'signal':(y/widths).tolist(),'signal_errors':(error/widths).tolist(),
             'prediction':(prediction/widths).tolist(),'components':(components/widths[:,None]).tolist(),
             'signal_covariance':(vy/covariance_scale).tolist(),
             'prediction_covariance':(vp/covariance_scale).tolist(),
             'residual_covariance':None if result.get('residual_covariance') is None else
                 (np.asarray(result['residual_covariance'])/covariance_scale).tolist()}
    settings=resolve_plot_settings(result,result.get('observable',''))
    validate_plot_axes(result,settings)
    scale=widths if settings['plot_height_per_unit_interval'] else np.ones(bins)
    display={'signal':(y/scale).tolist(),'signal_errors':(error/scale).tolist(),
             'prediction':(prediction/scale).tolist(),'components':(components/scale[:,None]).tolist(),
             'signal_covariance':(vy/(scale[:,None]*scale[None,:])).tolist(),
             'prediction_covariance':(vp/(scale[:,None]*scale[None,:])).tolist(),
             'residual_covariance':None if result.get('residual_covariance') is None else
                 (np.asarray(result['residual_covariance'])/(scale[:,None]*scale[None,:])).tolist()}
    result.update(settings,plot_normalization='differential_yield' if settings['plot_height_per_unit_interval'] else 'integrated_yield',
                  bin_widths=widths.tolist(),y_axis_label='Signal yield / '+unit if settings['plot_height_per_unit_interval'] else 'Signal yield / bin',
                  differential_yield=density,displayed_height=display,
                  display_width_convention='Original linear bin widths; axis scaling has no Jacobian')
    hep.style.use(hep.style.CMS)
    fig,(ax,ratio)=plt.subplots(2,1,figsize=(11,8),sharex=True,gridspec_kw={'height_ratios':[3,1]})
    centers=(edges[:-1]+edges[1:])/2
    bottom=np.zeros(bins)
    for i,name in enumerate(result['class_order']):
        height=components[:,i]/scale
        ax.bar(centers,height,width=widths,bottom=bottom,label=name,
               color=result['component_colors'][name],alpha=.8)
        bottom+=height
    visible=np.ones(bins,dtype=bool)
    visible[np.asarray(result.get('masked_signal_bins',[]),dtype=int)]=False
    point_label='Truth-signal toy counts' if result.get('extraction_kind')=='truth_signal_counts' else 'Mass-extracted signal'
    log_y=settings['plot_axis_scaling']['y']=='log'
    limits=settings['plot_axis_limits']; ymin=limits.get('y_min')
    upper=result.get('signal_upper_limits',[None]*bins)
    markers=visible & np.asarray([item is None for item in upper])
    if log_y: markers &= y>0
    ax.errorbar(centers[markers],(y/scale)[markers],yerr=None if log_y else (error/scale)[...,markers],fmt='ko',label=point_label)
    if log_y:
        lower=(y-error[0])/scale; high=(y+error[1])/scale
        for j in np.flatnonzero(markers):
            if high[j]>ymin:
                ax.vlines(centers[j],max(lower[j],ymin),high[j],colors='black')
    result['display_clipping']={'nonpositive_signal_markers_omitted':int(np.sum(visible & (y<=0))) if log_y else 0,
        'lower_error_segments_at_y_min':int(np.sum(markers & ((y-error[0])/scale<ymin))) if log_y else 0,
        'prediction_band_bins_at_y_min':0}
    for j,item in enumerate(upper):
        if item is None or not visible[j]: continue
        bound=item['value']/scale[j]
        if log_y and bound<ymin: continue
        ax.plot([centers[j]],[bound],marker='_',color='black')
        ax.annotate('',xy=(centers[j],bound),xytext=(0,-16),textcoords='offset points',
                    arrowprops={'arrowstyle':'<-','color':'black'})
    band=np.sqrt(np.maximum(np.diag(vp),0))
    result['display_clipping']['prediction_band_bins_at_y_min']=int(np.sum((prediction-band)/scale<ymin)) if log_y else 0
    upper_band=(prediction+band)/scale; lower_band=(prediction-band)/scale
    if log_y: upper_band=np.maximum(upper_band,ymin); lower_band=np.maximum(lower_band,ymin)
    ax.stairs(upper_band,edges,baseline=lower_band,
              fill=True,color='gray',alpha=.35,label='Prediction uncertainty')
    ax.stairs(prediction/scale,edges,color='black',linewidth=1.4,label='Total prediction')
    # Support remains an integrated-yield threshold, independent of plotting units.
    supported=(prediction>=result['ratio_min_prediction'])&visible
    ratio.errorbar(centers[supported],y[supported]/prediction[supported],
                   yerr=error[...,supported]/prediction[supported],fmt='ko')
    ratio.stairs(np.divide(prediction+band,prediction,out=np.ones(bins),where=supported),edges,
                 baseline=np.divide(prediction-band,prediction,out=np.ones(bins),where=supported),
                 fill=True,color='gray',alpha=.35)
    ratio.axhline(1,color='black',linewidth=1); ratio.set_ylabel('Signal / model'); ratio.set_xlabel(label)
    ax.set_xscale(settings['plot_axis_scaling']['x']); ratio.set_xscale(settings['plot_axis_scaling']['x'])
    ax.set_yscale(settings['plot_axis_scaling']['y'])
    if 'x_min' in limits or 'x_max' in limits:
        ax.set_xlim(left=limits.get('x_min'),right=limits.get('x_max')); ratio.set_xlim(ax.get_xlim())
    if 'y_min' in limits or 'y_max' in limits: ax.set_ylim(bottom=limits.get('y_min'),top=limits.get('y_max'))
    ax.set_ylabel(result['y_axis_label'])
    ax.legend(fontsize=10,loc='upper left',bbox_to_anchor=(1.02,1),frameon=False,borderaxespad=0)
    hep.cms.label(result.get('cms_caption','Work In Progress'),ax=ax,loc=0,data=not result.get('simulation',False),rlabel='')
    fig.subplots_adjust(left=.13,right=.70,bottom=.12,top=.9,hspace=.08)
    output=Path(output)
    fig.savefig(output/'signal_mixture.png',dpi=150); fig.savefig(output/'signal_mixture.pdf'); plt.close(fig)
    (output/'signal_mixture.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


def replot_saved_signal_mixture(source, output_dir, *, cms_caption=None, plot_height_per_unit_interval=True, plot_axis_scaling=None, plot_axis_limits=None):
    """Replot saved integrated predictions/covariances without loading events or fitting."""
    source=Path(source); output=Path(output_dir)
    result=json.loads(source.read_text())
    if cms_caption is not None: result['cms_caption']=cms_caption
    settings=resolve_plot_settings({'plot_height_per_unit_interval':plot_height_per_unit_interval,'plot_axis_scaling':plot_axis_scaling or {},'plot_axis_limits':plot_axis_limits or {}},result.get('observable',''))
    result.update(settings)
    validate_plot_axes(result,settings)
    if not result.get('mass_fit_reliable',True):
        raise ValueError('Refusing nominal plot of explicitly unreliable mass fit')
    # Older caches stored covariance errors only; new caches retain profile errors too.
    result['signal_error_source']='saved errors' if 'signal_errors' in result else 'legacy signal covariance diagonal'
    output.mkdir(parents=True,exist_ok=False)
    result['replot_source']=str(source.resolve())
    result['artifacts']=[str(output/'signal_mixture.png'),str(output/'signal_mixture.pdf')]
    _render_signal_mixture(output,result)
    return result


def summarize_signal_mixture(result):
    """Describe one saved projection; never infer missing cross covariance.

    A supplied residual covariance must represent VY+VP-C-C.T. Quadratics
    remain descriptive, including for full rank covariance; calibration and
    correlations between observable projections are not supplied here.
    """
    y=np.asarray(result['signal_yields'],float); p=np.asarray(result['prediction'],float)
    vy=np.asarray(result['signal_covariance'],float); vp=np.asarray(result['prediction_covariance'],float)
    bins=len(y)
    if p.shape!=(bins,) or vy.shape!=(bins,bins) or vp.shape!=(bins,bins):
        raise ValueError('Saved projection dimensions disagree')
    delta=y-p
    visible=np.ones(bins,dtype=bool)
    visible[np.asarray(result.get('masked_signal_bins',[]),dtype=int)]=False
    residual=result.get('residual_covariance')
    available=residual is not None
    covariance=np.asarray(residual,float) if available else vy+vp
    if covariance.shape!=(bins,bins):raise ValueError('Residual covariance dimensions disagree')
    variance=np.diag(covariance)
    valid=visible & np.isfinite(delta) & np.isfinite(variance) & (variance>0)
    z=np.full(bins,np.nan);z[valid]=delta[valid]/np.sqrt(variance[valid])
    sub=covariance[np.ix_(valid,valid)]
    diagnostics={'rank':0,'dimension':int(valid.sum()),'positive_semidefinite':False,'finite':bool(np.isfinite(sub).all())}
    quadratic=None
    if sub.size and diagnostics['finite']:
        symmetric=np.allclose(sub,sub.T,atol=1e-10,rtol=1e-8)
        eigen=np.linalg.eigvalsh((sub+sub.T)/2)
        tolerance=max(float(np.max(np.abs(eigen))),1.)*max(sub.shape)*np.finfo(float).eps*10
        rank=int(np.count_nonzero(eigen>tolerance))
        psd=bool(eigen.min()>=-tolerance)
        diagnostics.update(rank=rank,positive_semidefinite=psd,symmetric=bool(symmetric),
                           minimum_eigenvalue=float(eigen.min()),tolerance=float(tolerance),
                           full_rank=rank==len(sub))
        if available and psd and symmetric:
            quadratic=float(delta[valid]@np.linalg.pinv(sub,hermitian=True)@delta[valid])
    formal=available and diagnostics.get('full_rank',False) and diagnostics['positive_semidefinite']
    return {'signal_total':float(y.sum()),'prediction_total':float(p.sum()),
            'residuals':delta.tolist(),'standardized_residuals':[float(x) if np.isfinite(x) else None for x in z],
            'masked_bins':np.flatnonzero(~valid).tolist(),
            'masked_reasons':{'empty_mass_categories':result.get('masked_signal_bins',[]),
                              'nonpositive_or_nonfinite_variance':np.flatnonzero(~np.isfinite(variance)|(variance<=0)).tolist()},
            'cross_covariance_available':available,'covariance_diagnostics':diagnostics,
            'standardization_scope':'full residual covariance VY+VP-C-C.T' if available else 'conditional descriptive VY+VP; cross covariance unavailable',
            'residual_quadratic':quadratic,'quadratic_scope':'descriptive only; no calibrated p-value',
            'formal_gof_available':False,'full_rank_residual_covariance_available':bool(formal),
            'p_value':None,'significance_available':False,
            'mass_fit_reliable':result.get('mass_fit_reliable',True)}


def summarize_saved_observables(input_dir,output_file):
    """Read saved plots only; no likelihood fitting or template recalibration."""
    source=Path(input_dir); destination=Path(output_file)
    if destination.exists():raise FileExistsError(destination)
    summaries={}
    for path in sorted(source.rglob('signal_mixture.json')):
        summaries[str(path.parent.relative_to(source))]=summarize_signal_mixture(json.loads(path.read_text()))
    report={'source':str(source.resolve()),'observables':summaries,'count':len(summaries),
            'scope':'per-observable descriptive diagnostics; projections reuse events and are not independent tests',
            'combined_gof':None,'calibrated_p_values_available':False}
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Summarize saved signal-mixture projections without fitting')
    parser.add_argument('--input-dir',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    report=summarize_saved_observables(args.input_dir,args.output)
    print(f"Summarized {report['count']} saved projections")

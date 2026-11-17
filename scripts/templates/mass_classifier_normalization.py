"""Explicit selected-to-generated normalization; no implicit map compatibility."""
import numpy as np


def _propagate(function, vector, covariance):
    vector = np.asarray(vector, float)
    covariance = np.asarray(covariance, float)
    if covariance.shape != (len(vector), len(vector)) or not np.isfinite(covariance).all():
        raise ValueError('Input covariance has wrong shape or nonfinite entries')
    if not np.allclose(covariance, covariance.T) or np.linalg.eigvalsh(covariance).min() < -1e-8:
        raise ValueError('Input covariance must be symmetric positive semidefinite')
    columns = []
    for i, value in enumerate(vector):
        step = 1e-5 * max(abs(value), 1.)
        plus, minus = vector.copy(), vector.copy()
        plus[i] += step
        minus[i] -= step
        columns.append((function(plus) - function(minus)) / (2 * step))
    jacobian = np.asarray(columns).T
    return jacobian @ covariance @ jacobian.T


def build_mixed_efficiency_maps(numerators, denominators, class_yields, efficiencies, *,
                                generated_totals, selection_id, map_selection_id,
                                class_covariance=None, efficiency_covariance=None,
                                count_covariance=None, joint_covariance=None):
    """Pool CxK conditional counts; covariance order N, eps, numerator, denominator.

    generated_totals are fixed reference generated exposures, not selected counts.
    count_covariance must include numerator/denominator overlap when supplied.
    joint_covariance replaces block independence and includes all cross terms.
    """
    if not selection_id or selection_id != map_selection_id:
        raise ValueError('Explicit matching selection identities required')
    n, d = np.asarray(numerators, float), np.asarray(denominators, float)
    yields, eps, totals = map(lambda a: np.asarray(a, float), (class_yields, efficiencies, generated_totals))
    if n.ndim != 2 or n.shape != d.shape:
        raise ValueError('Counts must be matching CxK arrays')
    c, k = n.shape
    if any(a.shape != (c,) for a in (yields, eps, totals)):
        raise ValueError('Class vector shape mismatch')
    if not all(np.isfinite(a).all() for a in (n,d,yields,eps,totals)) or np.any(n<0) or np.any(d<n) or np.any(yields<0) or np.any(eps<=0) or np.any(eps>1) or np.any(totals<=0):
        raise ValueError('Invalid counts, efficiencies, exposure or yields')
    vector = np.concatenate((yields, eps, n.ravel(), d.ravel()))
    def evaluate(v):
        weights = v[:c] / v[c:2*c] / totals
        nn, dd = v[2*c:2*c+c*k].reshape(c,k), v[2*c+c*k:].reshape(c,k)
        denominator = weights @ dd
        if np.any(denominator <= 0):
            raise ValueError('Mixed map has unsupported denominator')
        return (weights @ nn) / denominator
    cov = np.zeros((len(vector),len(vector)))
    for block, start, size in ((class_covariance,0,c),(efficiency_covariance,c,c),(count_covariance,2*c,2*c*k)):
        if block is not None:
            cov[start:start+size,start:start+size] = block
    if joint_covariance is not None:
        cov = joint_covariance
    physical_weights = yields / eps / totals
    return {'efficiency': evaluate(vector).tolist(), 'covariance': _propagate(evaluate,vector,cov).tolist(),
            'physical_class_weights': physical_weights.tolist(), 'numerator': (physical_weights@n).tolist(),
            'denominator': (physical_weights@d).tolist(), 'selection_id': selection_id,
            'scope': 'inclusive selected sources; no prompt interpretation',
            'uncertainty_scope': 'supplied joint covariance' if joint_covariance is not None else 'supplied independent covariance blocks; omitted blocks fixed'}


def compute_cross_sections(class_yields, efficiencies, luminosity, branching_fractions, *,
                           class_covariance=None, efficiency_covariance=None,
                           joint_covariance=None, scope, luminosity_variance=0.,
                           branching_covariance=None):
    """Delta-method covariance; vector order N, eps, luminosity, branching."""
    n,e,b = map(lambda a: np.asarray(a,float),(class_yields,efficiencies,branching_fractions))
    c=len(n)
    if n.shape != (c,) or e.shape != (c,) or b.shape != (c,) or not scope:
        raise ValueError('Matching class arrays and explicit scope required')
    v=np.r_[n,e,float(luminosity),b]
    if not np.isfinite(v).all() or np.any(n<0) or np.any(e<=0) or np.any(e>1) or np.any(b<=0) or np.any(b>1) or luminosity<=0:
        raise ValueError('Invalid cross-section normalization')
    def evaluate(x): return x[:c]/(x[c:2*c]*x[2*c]*x[2*c+1:])
    cov=np.zeros((len(v),len(v)))
    for block,start,size in ((class_covariance,0,c),(efficiency_covariance,c,c),(branching_covariance,2*c+1,c)):
        if block is not None: cov[start:start+size,start:start+size]=block
    cov[2*c,2*c]=luminosity_variance
    if joint_covariance is not None: cov=joint_covariance
    cross_sections=evaluate(v)
    propagated=_propagate(evaluate,v,cov)
    total_variance=float(np.ones(c)@propagated@np.ones(c))
    return {'cross_sections':cross_sections.tolist(),'covariance':propagated.tolist(),
            'total_cross_section':float(cross_sections.sum()),'total_variance':total_variance,
            'total_error':float(np.sqrt(max(0.,total_variance))),
            'total_uncertainty_scope':'propagated supplied covariance including all off-diagonal terms; omitted inputs fixed',
            'scope':scope,
            'normalization':'selected N / (luminosity * matching efficiency * branching fraction)'}


def synthetic_normalization_config(seed=20261110, trials_per_class=12000):
    """Nested synthetic thinning in three bins and two conditional steps.

    Fixed generated trial count per class; multinomial trial covariance keeps
    epsilon/count and numerator/denominator correlations. Not a CMS map.
    """
    rng=np.random.default_rng(seed)
    c,k=6,6
    generated=np.full(c,int(trials_per_class))
    if trials_per_class<10: raise ValueError('At least ten generated trials per class required')
    counts_n=np.zeros((c,k)); counts_d=np.zeros((c,k))
    efficiencies=np.zeros(c); expected=np.zeros(c)
    # For each class nine exclusive states: bin x (fail0, pass0fail1, pass1).
    state_covariances=[]; transforms=[]; state_probabilities=[]
    for cl in range(c):
        binprob=np.array([.25+.015*cl,.35,.4-.015*cl])
        p=np.array([.45,.65,.8])+.015*cl
        q=np.array([.65,.75,.85])-.01*cl
        probs=np.column_stack((binprob*(1-p),binprob*p*(1-q),binprob*p*q)).ravel()
        observed=rng.multinomial(generated[cl],probs)
        transform=np.zeros((1+2*k,9))
        for j in range(3):
            transform[0,3*j+2]=1/generated[cl]
            transform[1+j,3*j+1:3*j+3]=1
            transform[1+3+j,3*j+2]=1
            transform[1+k+j,3*j:3*j+3]=1
            transform[1+k+3+j,3*j+1:3*j+3]=1
        values=transform@observed
        efficiencies[cl]=values[0]
        counts_n[cl]=values[1:1+k]; counts_d[cl]=values[1+k:]
        expected[cl]=np.sum(binprob*p*q)
        state_covariances.append(generated[cl]*(np.diag(probs)-np.outer(probs,probs)))
        transforms.append(transform); state_probabilities.append(probs.tolist())
    # Global order eps, numerator.ravel, denominator.ravel.
    covariance=np.zeros((c+2*c*k,c+2*c*k))
    for cl,(transform,state_cov) in enumerate(zip(transforms,state_covariances)):
        indices=np.r_[cl,np.arange(c+cl*k,c+(cl+1)*k),np.arange(c+c*k+cl*k,c+c*k+(cl+1)*k)]
        covariance[np.ix_(indices,indices)]=transform@state_cov@transform.T
    return {'numerators':counts_n.tolist(),'denominators':counts_d.tolist(),
            'efficiencies':efficiencies.tolist(),'expected_efficiencies':expected.tolist(),
            'generated_totals':generated.tolist(),'selection_id':'synthetic_nested_thinning_v1',
            'map_selection_id':'synthetic_nested_thinning_v1','luminosity':100.,
            'branching_fractions':[1.]*c,'scope':'synthetic inclusive six-source toy; no CMS efficiency calibration or prompt interpretation',
            'efficiency_covariance':covariance[:c,:c].tolist(),
            'count_covariance':covariance[c:,c:].tolist(),
            'efficiency_count_cross_covariance':covariance[:c,c:].tolist(),
            'map_columns':[{'step':step,'bin':j,'axis':'synthetic_bin','interval':[j,j+1]} for step in ('step0','step1_given_step0') for j in range(3)],
            'fixture':{'seed':seed,'trials_per_class':int(trials_per_class),'generation':'fixed-total multinomial nested Bernoulli thinning',
                       'state_probabilities':state_probabilities,'covariance':'exact multinomial trial covariance; generated exposures fixed'}}

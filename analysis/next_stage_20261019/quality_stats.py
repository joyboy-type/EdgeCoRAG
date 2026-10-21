"""Frozen descriptive paired-cluster statistics; no model calls or score parsing."""
import argparse
import numpy as np

STRATEGIES=('cosine','random','utility')


def holm(values):
    if any(not 0<=float(x)<=1 for x in values):raise ValueError('Invalid p-values')
    order=sorted(range(len(values)),key=lambda i:(values[i],i));result=[0.]*len(values);previous=0.
    for rank,index in enumerate(order):
        previous=max(previous,min(1.,(len(values)-rank)*float(values[index])))
        result[index]=previous
    return result


def choose_fixed(dev):
    if set(dev)!=set(STRATEGIES) or not dev['cosine'] or len({len(x) for x in dev.values()})!=1:
        raise ValueError('Aligned development outcomes required')
    return min(STRATEGIES,key=lambda strategy:(-sum(dev[strategy]),STRATEGIES.index(strategy)))


def mechanism(s0_correct,strategy_correct,pool_hit):
    if s0_correct and not strategy_correct:return 'retrieval_harm_proxy'
    if not pool_hit:return 'not_retrieved'
    if not strategy_correct:return 'present_but_wrong'
    return 'other'


def paired_family(comparisons,groups,*,resamples=10000,seed=42):
    if not comparisons or not groups or resamples<1:raise ValueError('Nonempty family and clusters required')
    n=len(groups);names=sorted(set(groups));lookup={name:i for i,name in enumerate(names)}
    idx=np.asarray([lookup[g] for g in groups]);sizes=np.bincount(idx,minlength=len(names))
    differences=[]
    for row in comparisons:
        if len(row['left'])!=n or len(row['right'])!=n:raise ValueError('Paired denominator mismatch')
        if any(type(x) not in (bool,np.bool_) for x in row['left']+row['right']):raise ValueError('Archived boolean outcomes required')
        differences.append(np.asarray(row['right'],dtype=np.int32)-np.asarray(row['left'],dtype=np.int32))
    differences=np.stack(differences,axis=1)
    sums=np.zeros((len(names),len(comparisons)),dtype=np.int32)
    np.add.at(sums,idx,differences)
    observed=100*differences.mean(axis=0);rng=np.random.default_rng(seed)
    bootstrap=np.empty((resamples,len(comparisons)))
    for start in range(0,resamples,250):
        draws=rng.integers(0,len(names),size=(min(250,resamples-start),len(names)))
        bootstrap[start:start+len(draws)]=100*sums[draws].sum(axis=1)/sizes[draws].sum(axis=1)[:,None]
    errors=bootstrap-observed
    # Equal-tailed centered-bootstrap p-values; Monte Carlo +1 includes finite-tail uncertainty.
    pvalues=np.minimum(1.,2*np.minimum((1+(errors<=observed).sum(axis=0))/(resamples+1),
                                      (1+(errors>=observed).sum(axis=0))/(resamples+1)))
    adjusted=holm(pvalues.tolist());family_size=len(comparisons);result=[]
    for j,row in enumerate(comparisons):
        low,high=2*observed[j]-np.quantile(bootstrap[:,j],[.975,.025],method='linear')
        alpha=.05/family_size
        holm_low,holm_high=2*observed[j]-np.quantile(bootstrap[:,j],[1-alpha/2,alpha/2],method='linear')
        meta={key:value for key,value in row.items() if key not in ('left','right')}
        result.append(dict(meta,n=n,left_correct=sum(row['left']),right_correct=sum(row['right']),
            wins=int((differences[:,j]>0).sum()),losses=int((differences[:,j]<0).sum()),
            delta_pp=float(observed[j]),ci_low_pp=float(max(-100,low)),ci_high_pp=float(min(100,high)),
            holm_ci_low_pp=float(max(-100,holm_low)),holm_ci_high_pp=float(min(100,holm_high)),
            raw_p=float(pvalues[j]),holm_p=float(adjusted[j]),family_size=family_size,
            components=len(names),resamples=resamples,seed=seed,
            interval_method='basic paired-cluster bootstrap; Holm full-family joint-acceptance rectangle projection (=Bonferroni)',
            interpretation='不能排除无差异' if holm_low<=0<=holm_high else '描述性校正区间未跨零；不作因果或普遍替代推断'))
    return result

if __name__=='__main__':argparse.ArgumentParser(description=__doc__).parse_args()

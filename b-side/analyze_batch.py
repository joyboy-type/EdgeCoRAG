"""Post-rental paired analysis, standard library only; performance repeats never become accuracy rows."""
import argparse
import json
import math
from pathlib import Path
import random
from batch_inputs import read,sha
from run_batch import atomic


def quantile(xs,p):
    if not xs:return None
    xs=sorted(xs);i=(len(xs)-1)*p;lo=int(i);hi=math.ceil(i)
    return xs[lo]+(xs[hi]-xs[lo])*(i-lo)


def paired(left,right,repetitions=2000,seed=42,groups=None,allow_synthetic=False):
    for score in [left,right]:
        if score.get('synthetic') and not allow_synthetic:raise ValueError('Synthetic results are mechanism evidence only')
        if score.get('stage')!='quality' or score.get('performance_repeats_excluded_from_accuracy'):raise ValueError('Quality score required')
    for k in ['dataset_revision','split_manifest_sha256','template_version','protocol_version']:
        if not left.get(k) or left[k]!=right.get(k):raise ValueError('Comparison metadata mismatch: '+k)
    def index(score):
        records=score['per_question'];out={r['qid']:r for r in records}
        if len(out)!=len(records):raise ValueError('Duplicate qid in score')
        if len(out)!=score['overall']['total']:raise ValueError('Score fixed denominator mismatch')
        return out
    a=index(left);b=index(right)
    if set(a)!=set(b) or not a:raise ValueError('Unpaired/missing/unknown score qids')
    qids=list(a)
    if any(a[q]['scenario']!=b[q]['scenario'] for q in qids):raise ValueError('Scenario mismatch')
    delta={q:int(b[q]['correct'])-int(a[q]['correct']) for q in qids}
    rng=random.Random(seed)
    if groups:
        if not groups.get('source_grouping_basis') or set(groups['source_ids'])!=set(qids):raise ValueError('Evidence-backed complete source grouping required')
        units={}
        for q in qids:units.setdefault(groups['source_ids'][q],[]).append(q)
        units=list(units.values());method='paired_source_cluster_bootstrap'
        def draw():return [q for _ in units for q in rng.choice(units)]
    else:
        strata={}
        for q in qids:strata.setdefault(a[q]['scenario'],[]).append(q)
        method='paired_scenario_stratified_bootstrap'
        def draw():return [rng.choice(qs) for qs in strata.values() for _ in qs]
    samples=[]
    for _ in range(repetitions):
        chosen=draw();samples.append(sum(delta[q] for q in chosen)/len(chosen))
    scenes={}
    for s in sorted({a[q]['scenario'] for q in qids}):
        qs=[q for q in qids if a[q]['scenario']==s]
        scenes[s]={'n':len(qs),'left_accuracy':sum(a[q]['correct'] for q in qs)/len(qs),
                   'right_accuracy':sum(b[q]['correct'] for q in qs)/len(qs),
                   'difference':sum(delta[q] for q in qs)/len(qs)}
    return {'method':method,'n_questions':len(qids),'resamples':repetitions,'seed':seed,
        'difference_right_minus_left':sum(delta.values())/len(delta),'percentile_CI_95':[quantile(samples,.025),quantile(samples,.975)],
        'scenarios':scenes,'Incomplete_retained_in_overall':True,'synthetic':bool(left.get('synthetic') or right.get('synthetic')),
        'caveat':'Small or dependent samples limit inference; grouping basis must be supplied, never inferred from image-hash disjointness. No automatic significance or external-validation claim.'}


def paired_S1_S3_subset(left,right,repetitions=2000,seed=42,allow_synthetic=False):
    import copy
    if left.get('condition')!='S1' or right.get('condition')!='S3-pure':raise ValueError('Require S1 full and S3-pure subset scores')
    coverage=right.get('S3_coverage')
    if not coverage or not right.get('semantic_review_sha256'):raise ValueError('Predeclared semantic subset metadata required')
    parent=[r['qid'] for r in left['per_question']];eligible=[r['qid'] for r in right['per_question']]
    if coverage['parent_qids']!=parent or coverage['eligible_qids']!=eligible:raise ValueError('Subset/parent denominator mismatch')
    if len(set(eligible))!=len(eligible) or not set(eligible)<=set(parent):raise ValueError('Unknown/duplicate subset qids')
    if right.get('parent_split_manifest_sha256')!=left['split_manifest_sha256']:raise ValueError('S3 subset parent split hash differs')
    subset=copy.deepcopy(left);mapping={r['qid']:r for r in left['per_question']}
    subset['per_question']=[mapping[q] for q in eligible];subset['overall']['total']=len(eligible)
    subset['split_manifest_sha256']=right['split_manifest_sha256']
    value=paired(subset,right,repetitions,seed,allow_synthetic=allow_synthetic)
    value.update({'comparison':'S1_vs_S3_on_identical_predeclared_subset','parent_denominator':len(parent),
        'paired_denominator':len(eligible),'coverage':len(eligible)/len(parent),
        'S1_subset_accuracy':sum(mapping[q]['correct'] for q in eligible)/len(eligible),
        'S3_subset_accuracy':sum(r['correct'] for r in right['per_question'])/len(eligible),
        'full_S1_score_unchanged':True})
    return value


def performance(predictions,minimum_n=None):
    valid=[r for r in predictions if not r.get('synthetic') and r.get('stage')=='performance' and not r.get('generation_error') and r.get('timing')]
    seen=set();groups={}
    names=['run_batch_id','model_id','model_revision','condition','protocol_version','evidence_version','actual_dtype','timing_hardware_id']
    for record in valid:
        if record.get('protocol_version')=='published_top3_actual_gt_d1_v1' and not record.get('timing_hardware_id'):raise ValueError('Main performance requires logged hardware identity; do not pool unknown hosts')
        if record.get('row_key'):
            key=tuple(record['row_key'])
            if key in seen:raise ValueError('Duplicate performance observation; use latest unique prediction files, not attempt history')
            seen.add(key)
        group=tuple(record.get(k) for k in names);groups.setdefault(group,[]).append(record)
    result={'observations':len(valid),'quality_accuracy_rows_added':0,'synthetic_ignored':sum(bool(r.get('synthetic')) for r in predictions),
            'timing_scope':'offline evidence generation only, not retrieval end-to-end','p95_minimum_explicitly_provided':minimum_n,
            'reliability_claim':False,'groups':[]}
    if minimum_n is not None and minimum_n<20:raise ValueError('Do not request a P95 from a trivially small sample')
    for group,records in groups.items():
        if any(r.get('protocol_version')=='published_top3_actual_gt_d1_v1' for r in records) and minimum_n is not None and minimum_n<100:
            raise ValueError('Main protocol requires at least100 observations before descriptive P95')
        metrics={}
        for name in ['generate_seconds','end_to_end_seconds']:
            xs=[r['timing'][name] for r in records if name in r['timing']]
            metrics[name]={'n':len(xs),'p50':quantile(xs,.5),'p95':quantile(xs,.95) if minimum_n is not None and len(xs)>=minimum_n else None,
                'note':'Descriptive repeated-observation quantiles; no stability or independent-sample claim.'}
        result['groups'].append({'identity':dict(zip(names,group)),'observations':len(records),'metrics':metrics})
    if len(result['groups'])<=1:result['metrics']=result['groups'][0]['metrics'] if result['groups'] else {}
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--S1-S3-subset',action='store_true');p.add_argument('--left',type=Path);p.add_argument('--right',type=Path);p.add_argument('--groups',type=Path)
    p.add_argument('--performance',type=Path,nargs='+');p.add_argument('--performance-min-n',type=int,default=100)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('New analysis output required')
    value={}
    if a.left or a.right:
        if not a.left or not a.right:raise ValueError('Both paired scores required')
        value['paired']=paired_S1_S3_subset(read(a.left),read(a.right)) if a.S1_S3_subset else paired(read(a.left),read(a.right))
        if a.groups:value['source_cluster']=paired(read(a.left),read(a.right),groups=read(a.groups));value['source_grouping_sha256']=sha(a.groups)
    if a.performance:
        records=[]
        for pth in a.performance:
            records.extend(json.loads(s) for s in pth.read_text(encoding='utf-8').splitlines() if s.strip())
        value['performance']=performance(records,a.performance_min_n)
    if not value:raise ValueError('Provide paired scores or performance predictions')
    atomic(a.output,value)

"""Two reduced, conditional arithmetic scopes. No executable plan or GPU request.
Reproduce: $PY analysis/next_stage_20261019/p5_budget_options.py --out <NEW_OUT>
--verify compares byte-identical arithmetic. No verified fp32 index was supplied:
SKIP E0; consume frozen A pools; omit live ranking/index residency claims.
"""
import argparse,json,math,tempfile
from pathlib import Path
from a_interface_evidence import save,table,sha
REPO=Path(__file__).resolve().parents[2]
def build(out):
    out=Path(out)
    if out.exists():raise ValueError('New output required')
    out.mkdir(parents=True);rows=[];options=[]
    for name,repeats,hard in [('A_cap5',2,7200),('B_cut20',1,3600)]:
        gens=20*3*repeats+3;utility=20*repeats*10+10
        cases=[('E2','query fingerprints ONLY;10live scores deferred without index',5,.5,1),
            ('E3','generation-only fixed-A-pool pilot; NOT full retrieval cost',gens,3,6),
            ('E3','utility candidate forwards in fixed A order',utility,.25,.5),
            ('E5','smoke20 x4 dimension cosine reports; no selection',80,3,6),('E5','smoke request IO',80,.03,.06),
            ('setup','load/check allowance',1,900,1800),('preservation','mandatory preservation reserve',1,600,600)]
        if name=='A_cap5':cases[3:3]=[('E4','smoke20 x4 paths generations',80,3,6),('E4','shared utility20x10',200,.25,.5)]
        group=[]
        for stage,op,n,unit,slow in cases:
            r=dict(option=name,stage=stage,operation=op,requests=n,assumed_unit_seconds=unit,point_seconds=n*unit,
                assumed_slow_unit_seconds=slow,slow_seconds=n*slow,
                source='User600-second preservation' if stage=='preservation' else 'Explicit hypothetical scope; unit times inherited from61b41e4 budget, NOT measured fp32 times')
            rows.append(r);group.append(r)
        point=sum(r['point_seconds'] for r in group);slow=sum(r['slow_seconds'] for r in group);rate=2.18
        win=math.ceil(slow/60);pwin=math.ceil(point/60)
        if slow>hard:raise ValueError('Proposed scope cannot fit its hard window')
        options.append(dict(option=name,label='假设、非实测、非预算申请',point_seconds=point,slow_scenario_seconds=slow,
            point_window_minutes=pwin,slow_window_minutes=win,hard_window_seconds=hard,
            assumed_rate_cny_per_hour=rate,live_quote='unavailable',conditional_point_compute_cny=pwin/60*rate,
            conditional_slow_compute_cny=win/60*rate,conditional_hard_window_compute_cny=hard/3600*rate,
            proposed_future_total_cap_cny=5 if name=='A_cap5' else 3,
            total_cost_cap_verified=False,fee_limit='Compute only under hypothetical rate. Storage/transfer/minimum billing/tax unknown; cap requires future real quote and platform enforcement.',
            work_stop='T0+'+str(hard-600)+'s',hard_shutdown='T0+'+str(hard)+'s',preservation_seconds=600,
            E0='跳过E0并缩范围；租用窗口内禁止重建4712语料',
            index_prerequisite='No verified transferable fp32 index supplied. No corpus encoding/live ranking/index-residency benchmark in this scope.',
            selection_scope='smoke/dev only; report four smoke dimensions, no dimension selection; frozen quality/dev selection deferred',
            E1_scope='Deferred entirely: native 4a60d75 a18 always encodes corpus and has no precomputed-index argument; do not replace it with a B-stack sensitivity probe',
            deferred=['E0 corpus encoding','E1 full a18 sensitivity (requires corpus encoding; not called here)','E2 live top10 scoring','E3 full retrieval cost and formal P95','E5 dev dimension choice/frozen selected dimension/selected-dimension utility']+(['E4 four-path quality matrix'] if name=='B_cut20' else []),
            failed_stop=['Any first task failure: preserve partial, no retry','Missing image/identity/license/required source proof: stop before spending',
                'Target torch/BLAS mismatch or unavailable: abort formal tasks','Remaining preservation reserve<600s: stop work',
                'Platform hard stop and valid quote/cap not established: do not boot'],
            ready_for_GPU_application=False))
    ratio=1-options[1]['slow_scenario_seconds']/options[0]['slow_scenario_seconds']
    if ratio<.2:raise ValueError('Option B did not cut at least20%')
    table(out/'budget_options.csv',rows)
    result=dict(options=options,slow_scope_reduction_fraction_B_vs_A=ratio,
        nonmeasured=True,no_GPU_authorization=True,
        source_budget_script_sha256=sha(REPO/'analysis/next_stage_20261019/a_interface_budget.py'),
        source_old_scenario=dict(point_seconds=3774.59,slow_seconds=6949.18),
        no_index_scope_change='Remove full E1 (2406 query encodes) plus123 live encodes and123 ranking calls from old scope:1268.19/2536.38 assumed seconds. B additionally reduces E3 to1 repeat and defers E4; no faster runtime claim.',
        still_blocked=['A adjudication18955 vs14475/4712','B full cross-stack a18 not run','target CPU/BLAS effective values unmeasured','A corpus byte rebuild/parquet preflight not verified here','Native 4a60d75 a18 has no index reuse argument and always encodes4712 corpus items; E1 deferred, no B-stack workaround','real quote/whole-device resource instrumentation/user boot authorization absent'])
    save(out/'budget_options.json',result);return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args()
    if a.verify:
        with tempfile.TemporaryDirectory() as d:
            result=build(Path(d)/'new')
            for f in (Path(d)/'new').iterdir():
                if f.read_bytes()!=(a.out/f.name).read_bytes():raise ValueError('Budget arithmetic drift')
    else:result=build(a.out)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

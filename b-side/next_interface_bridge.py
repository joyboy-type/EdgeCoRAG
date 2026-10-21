"""Future fp32/pools/score-only/outer-timer bridge; no implicit GPU execution.

A's native tool schema is not present in this checkout. These injected callables
are a tested shim contract, not a claim of native a12/a15/a18 integration. Existing
bf16 workers and historical measurement fields are intentionally untouched.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'a-side/scripts'))
from evidence_selection import select,pool_digest


def build_fp32_encoder(weights,torch,loader,*,authorized=False):
    if authorized is not True:raise ValueError('Explicit future GPU authorization required; no default model loading')
    weights=Path(weights)
    if not weights.is_dir():raise ValueError('Pinned local weights directory required; no download')
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    if hasattr(torch,'set_float32_matmul_precision'):torch.set_float32_matmul_precision('highest')
    model=loader(str(weights),device='cuda',local_files_only=True,trust_remote_code=False,
        config_kwargs={'audio_config':None},model_kwargs={'torch_dtype':torch.float32})
    parameters=list(model.parameters())
    if not parameters or any(parameter.dtype!=torch.float32 for parameter in parameters):
        raise ValueError('Model parameters are not fp32; do not relabel bf16')
    if torch.backends.cuda.matmul.allow_tf32 or torch.backends.cudnn.allow_tf32:
        raise ValueError('TF32 was not disabled')
    return model


def consume_pool(payload,qid,expected_sha256=None):
    if payload.get('qid')!=qid:raise ValueError('Pool/query binding mismatch')
    ids=payload.get('corpus_ids')
    if not isinstance(ids,list) or len(ids)<3 or len(ids)!=len(set(ids)) or any(not isinstance(x,str) or not x for x in ids):
        raise ValueError('Ordered distinct corpus ids required')
    if expected_sha256 and pool_digest(payload)!=expected_sha256:raise ValueError('A pool digest mismatch')
    return list(ids)  # direct consumption; never rerank, sort, or refill A's artifact


def utility_only(score_fn,qid,pool,*,clock=time.perf_counter):
    start=clock();scores=score_fn(qid,list(pool));seconds=clock()-start
    if not isinstance(scores,dict) or set(scores)!=set(pool):raise ValueError('Utility must return exactly candidate scores, not a selection')
    if any(type(value) not in (float,int) or not math.isfinite(value) for value in scores.values()):
        raise ValueError('Finite raw utility scores required')
    if not math.isfinite(seconds) or seconds<0:raise ValueError('Invalid utility timer')
    return scores,seconds


def run_with_outer_timer(a12,payload,qid,strategy,score_fn,generate_fn,*,clock=time.perf_counter):
    if strategy not in ('cosine','random','utility'):raise ValueError('Unknown fixed strategy')
    def work():
        pool=consume_pool(payload,qid);scores=None;timing=dict(availability='not_applicable',reason='strategy does not invoke utility')
        if strategy=='utility':
            scores,seconds=utility_only(score_fn,qid,pool,clock=clock)
            timing=dict(availability='observed',value=seconds,unit='seconds',kind='utility_only')
        selected=select(qid,pool,strategy,3,20261017,scores)
        return dict(pool_ids=pool,selected_ids=selected,generation=generate_fn(selected),utility_measurement=timing)
    outer=a12(work)  # a12 owns the full boundary, including utility when it runs
    if not isinstance(outer,dict) or type(outer.get('seconds')) not in (int,float) or not math.isfinite(outer['seconds']) or outer['seconds']<=0:
        raise ValueError('a12 shim must return measured outer seconds and result')
    result=dict(outer['result'],outer_seconds=outer['seconds'],outer_boundary='a12_callable',
        native_A_schema_verified=False,encoder_policy='fp32; TF32 disabled; does not describe historical bf16 runs')
    if result['utility_measurement']['availability']=='observed':result['utility_seconds']=result['utility_measurement']['value']
    return result


def observed_measurement(value,kind):
    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
        raise ValueError('An unavailable/zero/null measurement cannot pass as observed')
    return dict(availability='observed',value=value,kind=kind)


def historical_gap(field):
    reasons={'rendered_prompt':'Only saved abstract messages exist; processor-rendered string was not captured.',
        'device_total_peak_bytes':'Allocator peaks are not whole-device peaks; no historic whole-device sampling trace.',
        'per_strategy_p95':'15 smoke measurements per path are below the declared20-observation P95 rule.',
        'system_ram_peak_bytes':'No matching whole-system RAM peak trace in round-1 receipt.'}
    if field not in reasons:raise ValueError('Unknown historic gap')
    return dict(field=field,availability='不可回溯',reason=reasons[field],historical_values_modified=False)


def require_observed(record):
    if record.get('availability')!='observed' or 'value' not in record:raise ValueError('Missing measurement must remain a declared gap')
    return record['value']


def capture_rendered_prompt(processor,messages,**processing_kwargs):
    kwargs=dict(processing_kwargs);kwargs['tokenize']=False;kwargs.setdefault('add_generation_prompt',True)
    rendered=processor.apply_chat_template(messages,**kwargs)
    if not isinstance(rendered,str) or not rendered:raise ValueError('Actual processor-rendered text required')
    return dict(availability='observed',value=rendered,sha256=hashlib.sha256(rendered.encode()).hexdigest(),
        kind='processor_rendered_prompt',public_distribution=False)


def dimension_report(summaries):
    if set(summaries)!={128,256,512,768}:raise ValueError('Report all four dimensions')
    return dict(dimensions=[dict(dimension=dim,summary=summaries[dim]) for dim in (128,256,512,768)],
        selection_performed=False,policy='report only; dimension decisions require separately frozen dev protocol')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.parse_args()
    print(json.dumps(dict(status='interface_contract_only',model_loaded=False,gpu_started=False,
        native_A_integration='blocked_until_pinned_native_schema_available',historical_dtype='unchanged_bf16',
        future_encoder_dtype='fp32',tf32='must_be_disabled'),indent=2))

if __name__=='__main__':main()

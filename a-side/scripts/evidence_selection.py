"""Offline selection contracts. No labels, model imports, or implicit execution."""
import hashlib
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = json.loads((REPO/'b-side/configs/shared_visual_mcq_v1.json').read_text())['text']
FORBIDDEN = {'gold','answer','answer_choice','gt_choice','correct','relevance','is_relevant','gt_images','gold_ids'}


def no_labels(value):
    if isinstance(value, dict):
        if FORBIDDEN.intersection(value):
            raise ValueError('Labels/relevance are forbidden in inference inputs')
        for child in value.values(): no_labels(child)
    elif isinstance(value, list):
        for child in value: no_labels(child)


def pool_digest(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def select(qid, candidates, strategy, k, seed, utility=None):
    if (not isinstance(qid,str) or not qid or not isinstance(candidates,list)
        or any(not isinstance(x,str) or not x for x in candidates)
        or len(candidates)!=len(set(candidates)) or type(k) is not int
        or not 0 < k <= len(candidates) or type(seed) is not int):
        raise ValueError('Invalid query, candidate pool, k or seed')
    if strategy=='cosine':
        positions=list(range(k))
    elif strategy=='random':
        # A keyed hash gives repeatable per-q sampling, independent of batch order/Python RNG versions.
        positions=sorted(range(len(candidates)),key=lambda i:(hashlib.sha256(
            json.dumps([seed,qid,candidates[i]],separators=(',',':')).encode()).digest(),i))[:k]
    elif strategy=='utility':
        if not isinstance(utility,dict) or set(utility)!=set(candidates):
            raise ValueError('Utility scores must match the exact candidate pool')
        if any(type(x) not in (int,float) or not math.isfinite(x) for x in utility.values()):
            raise ValueError('Utility scores must be finite numbers')
        positions=sorted(range(len(candidates)),key=lambda i:(-utility[candidates[i]],i))[:k]
    else:
        raise ValueError('Unknown selection strategy')
    return [candidates[i] for i in sorted(positions)]


def generation_row(query, corpus, selected, strategy, pool_sha, seed):
    no_labels(query)
    if len(selected)!=len(set(selected)) or not selected or any(x not in corpus for x in selected):
        raise ValueError('Selected candidates missing or duplicated')
    if set(query['choices'])!={'A','B','C','D'}:
        raise ValueError('Four MCQ choices required')
    text=TEMPLATE.format(question=query['question'],**query['choices'])
    refs=[dict(corpus[x]) for x in selected]
    row={'qid':query['qid'],'split':query['split'],'question':query['question'],'choices':query['choices'],
         'query_image':dict(query['query_image']),'evidence':refs,
         'protocol_version':'independent_selection_proposed_v2','template_version':'shared_visual_mcq_v1',
         'selection_strategy':strategy,'selection_seed':seed,'pool_sha256':pool_sha,'selected_ids':selected,
         'is_oracle':False,'model_request':{'messages':[{'role':'user','content':[
             *[{'type':'image','image_index':i} for i in range(1+len(refs))],{'type':'text','text':text}]}]}}
    no_labels(row)
    return row


def remaining_seconds(auth, now):
    if (auth.get('execution_authorized') is not True or auth.get('protocol_approved') is not True
        or auth.get('shutdown_verified') is not True):
        raise ValueError('New explicit authorization, protocol and verified platform shutdown required')
    keys=['max_rate_cny_hour','quoted_rate_cny_hour','max_incremental_cny','incurred_cny',
          'storage_reserve_cny','deadline_epoch']
    if any(type(auth.get(k)) not in (int,float) or not math.isfinite(auth[k]) for k in keys):
        raise ValueError('Finite numeric authorization values required')
    if (not 0<auth['quoted_rate_cny_hour']<=auth['max_rate_cny_hour'] or auth['max_incremental_cny']<=0
        or auth['incurred_cny']<0 or auth['storage_reserve_cny']<0):
        raise ValueError('Rate or budget invalid')
    budget=auth['max_incremental_cny']-auth['incurred_cny']-auth['storage_reserve_cny']
    available=min(auth['deadline_epoch']-now,budget/auth['quoted_rate_cny_hour']*3600)
    if available<=0: raise ValueError('Authorized time or budget exhausted')
    return available

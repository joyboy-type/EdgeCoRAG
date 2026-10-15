"""HQ-authorized published top-3 / actual GT / reviewed D1 protocol, independent of gold choices."""
PROTOCOL='published_top3_actual_gt_d1_v1'


def evidence_count(condition,scenario):
    if condition=='S0':return 0
    if condition in ['S1','S3-pure']:return 3
    if condition=='S2':return 1 if scenario=='Incomplete' else 5
    raise ValueError('Unknown main condition')


def published_candidates(row):
    """Original loader used_in_prompt flags are audit metadata, not this protocol's selection."""
    if row.get('pool_id')!='official_retrieved_top5':raise ValueError('Published MRAG candidates required; no independent retrieval relabeling')
    refs=list(row['evidence_order'])+list((row.get('available_evidence_untruncated') or {}).get('retrieved_refs',[]))
    ids=[r['evidence_id'] for r in refs];ranks=[r.get('retrieval_rank') for r in refs]
    if len(ids)!=len(set(ids)) or len(ranks)!=len(set(ranks)):raise ValueError('Duplicate candidate ID/rank')
    if any(not isinstance(rank,int) for rank in ranks):raise ValueError('Explicit original integer ranks required')
    refs.sort(key=lambda r:r['retrieval_rank'])
    if len(refs)<3 or [r['retrieval_rank'] for r in refs[:3]]!=[0,1,2]:raise ValueError('Published first-three ranks incomplete')
    return refs


def verified_D1(record):
    if not record or record.get('distractor_type')!='D1' or not record.get('review_id'):return []
    entries=record.get('evidence',[])
    if len(entries)!=3 or any(r.get('semantic_status')!='confirmed_unsupportive' for r in entries):return []
    ids=[r['evidence_id'] for r in entries]
    return ids if len(set(ids))==3 else []


def make_selection(rows,metadata,d1=None,s3_only=False):
    """No answer_choice/gold_choice/answer_text read. S2 reads GT IDs only."""
    conditions={c:{'source':{'S0':'none','S1':'official_clip_candidates','S2':'actual_GT','S3-pure':'A_semantic_verified_D1'}[c],'by_qid':{}}
                for c in (['S3-pure'] if s3_only else ['S0','S1','S2'])}
    selected=[];diagnostic=[]
    d1=d1 or {}
    for row in rows:
        q=row['qid'];semantic=d1.get('by_qid',{}).get(q);ids=verified_D1(semantic)
        if s3_only and not ids:diagnostic.append(q);continue
        selected.append(q)
        for c in conditions:
            if c=='S0':refs=[]
            elif c=='S1':refs=[r['evidence_id'] for r in published_candidates(row)[:3]]
            elif c=='S2':
                refs=list(row['scoring_only']['gt_evidence_ids'])
                if len(refs)!=evidence_count(c,row['scenario']):raise ValueError('GT actual count differs; never pad, repeat, or truncate it')
            else:refs=ids
            conditions[c]['by_qid'][q]={'evidence_ids':refs,'expected_num_evidence':evidence_count(c,row['scenario'])}
            if c=='S3-pure':conditions[c]['by_qid'][q].update({'distractor_type':'D1','semantic_status':'confirmed_unsupportive','review_id':semantic['review_id']})
    if s3_only and not selected:raise ValueError('No reviewed D1 subset; not a runnable S3 package')
    return {**metadata,'protocol_version':PROTOCOL,'qids':selected,'conditions':conditions,
            'S3_coverage':{'parent_qids':[r['qid'] for r in rows],'eligible_qids':selected,'diagnostic_only_qids':diagnostic,
                'coverage':len(selected)/len(rows) if rows else 0} if s3_only else None}

import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'a-side/scripts'))
try:
    import evidence_selection as es
except ImportError:
    es = None

class SelectionContracts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(es, 'evidence_selection module is not implemented')
        self.pool = [f'c{i}' for i in range(10)]

    def test_utility_selects_members_then_preserves_retrieval_order(self):
        scores = dict(zip(self.pool, [0, 2, 3, 1, 10, 5, 4, 6, 8, 7]))
        self.assertEqual(es.select('q1', self.pool, 'utility', 3, 42, scores), ['c4', 'c8', 'c9'])
        self.assertEqual(es.select('q1', self.pool, 'cosine', 3, 42), ['c0','c1','c2'])

    def test_random_is_query_stable_and_independent_of_processing_order(self):
        first = es.select('q1', self.pool, 'random', 3, 42)
        es.select('q2', self.pool, 'random', 3, 42)
        self.assertEqual(first, es.select('q1', self.pool, 'random', 3, 42))
        self.assertEqual(len(set(first)), 3)
        self.assertEqual(first, sorted(first, key=self.pool.index))

    def test_reject_duplicate_short_pools_and_invalid_sizes(self):
        for pool, k in [(['a']*10,3), (self.pool[:2],3), (self.pool,0), (self.pool,True)]:
            with self.assertRaises(ValueError): es.select('q1',pool,'cosine',k,42)

    def test_reject_missing_extra_or_nonfinite_utility_scores(self):
        for scores in [{}, {**dict.fromkeys(self.pool,1), 'extra':2}, dict.fromkeys(self.pool,float('nan'))]:
            with self.assertRaises(ValueError): es.select('q1',self.pool,'utility',3,42,scores)

    def test_stable_utility_ties_use_original_rank(self):
        self.assertEqual(es.select('q',self.pool,'utility',3,42,dict.fromkeys(self.pool,0)), ['c0','c1','c2'])

    def test_gold_fields_rejected_recursively(self):
        for field in ['gold','answer','answer_choice','correct','is_relevant','gt_images','relevance']:
            with self.assertRaises(ValueError): es.no_labels({'nested':[{'x':{field:'A'}}]})

    def test_generation_bridge_uses_query_then_selected_images_and_shared_prompt(self):
        q={'qid':'mragb:1','split':'dev','question':'Which?','choices':{'A':'one','B':'two','C':'three','D':'four'},
           'query_image':{'path':'q.jpg','sha256':'a'*64,'size':[10,10]}}
        corpus={v:{'path':v+'.jpg','sha256':'b'*64,'size':[20,20]} for v in self.pool}
        row=es.generation_row(q,corpus,['c4','c8','c9'],'utility','pool-sha',42)
        self.assertEqual([x['path'] for x in row['evidence']], ['c4.jpg','c8.jpg','c9.jpg'])
        content=row['model_request']['messages'][0]['content']
        self.assertEqual([x['image_index'] for x in content[:-1]], [0,1,2,3])
        self.assertIn('Which?', content[-1]['text'])
        self.assertNotIn('pool-sha',content[-1]['text'])
        es.no_labels(row)

    def test_pool_fingerprint_binds_query_order_and_candidates(self):
        p=[{'qid':'q','corpus_ids':self.pool}]
        self.assertNotEqual(es.pool_digest(p),es.pool_digest([{'qid':'q','corpus_ids':list(reversed(self.pool))}]))
        self.assertNotEqual(es.pool_digest(p),es.pool_digest([{'qid':'other','corpus_ids':self.pool}]))

    def test_execution_gate_requires_current_budget_deadline_and_platform_guard(self):
        valid={'execution_authorized':True,'protocol_approved':True,'max_rate_cny_hour':2.18,
               'quoted_rate_cny_hour':2.18,'max_incremental_cny':3,'incurred_cny':0.2,
               'storage_reserve_cny':0.5,'deadline_epoch':1800,'shutdown_verified':True}
        self.assertAlmostEqual(es.remaining_seconds(valid,now=0),1800)
        for updates in [{'execution_authorized':False},{'protocol_approved':False},{'shutdown_verified':False},
                        {'quoted_rate_cny_hour':2.19},{'deadline_epoch':0},{'incurred_cny':3},
                        {'max_incremental_cny':float('inf')},{'deadline_epoch':True}]:
            with self.assertRaises(ValueError): es.remaining_seconds({**valid,**updates},now=0)
        self.assertAlmostEqual(es.remaining_seconds({**valid,'max_incremental_cny':1,'storage_reserve_cny':0.5},now=0),0.3/2.18*3600)

if __name__=='__main__': unittest.main()

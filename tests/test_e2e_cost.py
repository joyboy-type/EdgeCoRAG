"""CPU contracts for the cost-experiment entry; no model and no GPU."""
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'b-side'))
import e2e_cost as c
import e2e_smoke as smoke


def query(i=0, split='smoke_20'):
    return {'qid':str(i),'split':split,'question':'Which?',
            'choices':dict(A='a',B='b',C='c',D='d'),
            'query_image':{'path':'q.jpg','sha256':'self','size':[1,1]}}


class Runtime:
    synthetic = True
    def __init__(self, fail=False):
        self.t = 0.; self.fail = fail
    def sync(self): self.t += .25
    def reset_peak(self): pass
    def peak(self): return {'allocated_bytes':17,'reserved_bytes':23}
    def device_memory(self): return {'free_bytes':100,'total_bytes':200,'used_bytes':100,'scope':'test'}
    def encode(self, q): self.t += 1.; return [1,0]
    def rank(self, v):
        self.t += 2.
        order = ['image:self'] + list('abcdefghijk')
        return order, [10. - .5 * i for i in range(len(order))]
    def utility(self,q,pool): self.t += 3.; return dict(zip(pool,range(10)))
    def infer(self,row):
        self.t += 4.
        if self.fail: raise RuntimeError('GPU failed')
        return {'final_output':'','final_extraction_error':None,'synthetic':True,
                'cuda_memory':{'process_allocator_peak_allocated':31,
                               'process_allocator_peak_reserved':37}}


class ScheduleContracts(unittest.TestCase):
    def test_balanced_three_strategy_schedule(self):
        rows=c.schedule([query(i) for i in range(20)],c.STRATEGIES,5)
        warmups=[row for row in rows if row['warmup']]
        measured=[row for row in rows if not row['warmup']]
        self.assertEqual([row['strategy'] for row in warmups],list(c.STRATEGIES))
        self.assertEqual(len(measured),300)
        self.assertEqual(len({(row['qid'],row['strategy'],row['repeat']) for row in measured}),300)
        for repeat in range(5):
            for qid in {row['qid'] for row in measured}:
                found={row['strategy'] for row in measured if row['repeat']==repeat and row['qid']==qid}
                self.assertEqual(found,set(c.STRATEGIES))
        firsts=[min((row for row in measured if row['repeat']==r),key=lambda row: rows.index(row))['strategy']
                for r in range(5)]
        self.assertEqual(len(set(firsts)),3)

    def test_schedule_rejects_out_of_scope_requests(self):
        good=[query(i) for i in range(5)]
        for mutation in (dict(strategies=('cosine','utility')),
                         dict(strategies=('cosine','random','utility','utility')),
                         dict(repeats=1),dict(repeats=11),dict(repeats=True)):
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                c.schedule(good,**mutation)
        for queries in (good[:3],[query(0),query(0),query(1),query(2),query(3)],
                        [query(i,'internal_holdout') for i in range(5)]):
            with self.subTest(queries=len(queries)),self.assertRaises(ValueError):
                c.schedule(queries,c.STRATEGIES,2)

    def test_p95_needs_a_declared_minimum_sample(self):
        # nearest-rank: the smallest observation with at least 95% of values at or below it
        self.assertIsNone(c.p95([1.,2.,3.]))
        values=list(map(float,range(20)))
        self.assertEqual(c.p95(values),values[18])
        self.assertEqual(c.p95(list(range(100))),94)


class AggregationContracts(unittest.TestCase):
    def rows(self, counts):
        rows=[]
        for strategy,values in counts.items():
            for i,value in enumerate(values):
                rows.append(dict(qid=str(i%2),strategy=strategy,end_to_end_seconds=value,
                                 components={name:value/4 for name in c.COMPONENTS},
                                 generation={'timing':{'preprocess_seconds':value*.1,
                                                       'generate_seconds':value*.2}},
                                 resources=dict(device_before=dict(used_bytes=value*1e9),
                                                device_after=dict(used_bytes=value*1e9+1),
                                                rss_before=None,
                                                rss_after=dict(current_bytes=10,peak_bytes=value*1e6))))
        return rows

    def test_statistics_are_per_request_and_disclose_clusters(self):
        stats=c.aggregate(self.rows(dict(cosine=[.5,.6],utility=[1.5,1.6])),('cosine','utility'))
        self.assertEqual(stats['cosine']['n'],2)
        self.assertEqual(stats['cosine']['n_queries'],2)
        self.assertAlmostEqual(stats['cosine']['median_seconds'],.55)
        self.assertIsNone(stats['cosine']['p95_seconds'])
        self.assertEqual(stats['utility']['device_used_bytes_max_sampled'],1.6e9+1)
        self.assertEqual(stats['utility']['process_rss_peak_bytes'],1.6e6)
        self.assertAlmostEqual(stats['cosine']['generation_timing_medians']['preprocess_seconds'],.055)
        self.assertAlmostEqual(stats['utility']['generation_timing_medians']['generate_seconds'],.31)
        with self.assertRaises(ValueError): c.aggregate(self.rows(dict(cosine=[.5])),('cosine','utility'))

    def test_each_entry_pins_its_own_module_for_the_supervisor(self):
        self.assertIn(smoke.ENTRY,smoke.REQUIRED_SOURCES)
        self.assertIn(c.ENTRY,c.COST_SOURCES)
        self.assertNotEqual(smoke.ENTRY,c.ENTRY)

    def test_request_adds_boundary_resource_samples(self):
        record=c.request(query(),{c:{'path':c,'sha256':c,'size':[1,1]} for c in 'abcdefghijk'},
                         'cosine',Runtime(),clock=lambda:0.)
        self.assertEqual(record['resources']['device_before']['used_bytes'],100)
        self.assertIn('ranking',record)
        self.assertEqual(record['resources']['rss_before'] is None
                         or 'peak_bytes' in record['resources']['rss_before'],True)


class PlanContracts(unittest.TestCase):
    def plan(self, root, repo):
        ref=dict(path='q.jpg',sha256=smoke.file_sha(root/'q.jpg'),size=[1,1])
        return dict(queries=[dict(query(i),query_image=ref) for i in range(5)],
                    corpus={c:ref for c in 'abcdefghijk'},corpus_order=list('abcdefghijk'),
                    index=dict(path='index.npy',sha256=smoke.file_sha(root/'index.npy')),
                    source_pins={name:smoke.file_sha(repo/name) for name in c.COST_SOURCES},
                    retriever=dict(smoke.RETRIEVER_SPEC),estimate_seconds=1000,cpu_threads=4,
                    strategies=list(c.STRATEGIES),repeats=2,entry=c.ENTRY,
                    status='prepared_unexecuted',execution_authorized=False)

    def build(self, directory):
        root=Path(directory);repo=root/'repo';repo.mkdir()
        for name in c.COST_SOURCES:
            path=repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'code')
        (root/'q.jpg').write_bytes(b'image');(root/'index.npy').write_bytes(b'index')
        return root,repo

    def test_valid_plan_reports_the_declared_sample_structure(self):
        with tempfile.TemporaryDirectory() as d:
            root,repo=self.build(d)
            result=c.validate_plan(self.plan(root,repo),root,repo)
            self.assertEqual(result['planned_requests'],33)
            self.assertEqual(result['measured_requests'],30)
            self.assertEqual(result['queries'],5)

    def test_plan_rejects_missing_strategies_threads_pins_and_estimate(self):
        with tempfile.TemporaryDirectory() as d:
            root,repo=self.build(d)
            base=self.plan(root,repo)
            mutations={'strategies':('cosine','utility'),'repeats':1,'cpu_threads':0,
                       'estimate_seconds':9999,'index':None,'holdout':None,'pins':None,'entry':None}
            for name in mutations:
                changed=deepcopy(base)
                if name=='strategies':changed['strategies']=list(mutations[name])
                if name=='repeats':changed['repeats']=mutations[name]
                if name=='cpu_threads':changed['cpu_threads']=mutations[name]
                if name=='estimate_seconds':changed['estimate_seconds']=mutations[name]
                if name=='index':changed['index']['sha256']='0'*64
                if name=='holdout':changed['queries'][0]['split']='internal_holdout'
                if name=='pins':changed['source_pins'].pop('b-side/e2e_cost.py')
                if name=='entry':changed['entry']='b-side/e2e_smoke.py'
                with self.subTest(mutation=name),self.assertRaises(ValueError):
                    c.validate_plan(changed,root,repo)


class RunContracts(unittest.TestCase):
    def corpus(self):
        return {c:{'path':c,'sha256':c,'size':[1,1]} for c in 'abcdefghijk'}

    def test_run_records_receipt_and_partial_failure(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'new'
            receipt=c.run([query(i) for i in range(5)],self.corpus(),out,Runtime(),
                          c.STRATEGIES,2)
            self.assertEqual(receipt['status'],'completed')
            self.assertEqual(receipt['measured_requests'],30)
            self.assertEqual(receipt['completed_requests'],33)
            self.assertIsNone(receipt['statistics']['cosine']['p95_seconds'])
            self.assertEqual(receipt['sample_structure']['query_clusters'],5)
            rows=[json.loads(line) for line in (out/'requests.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),33)
            self.assertTrue(all('resources' in row for row in rows))
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'new'
            with self.assertRaises(RuntimeError):
                c.run([query(i) for i in range(5)],self.corpus(),out,Runtime(fail=True),
                      c.STRATEGIES,2)
            receipt=json.loads((out/'receipt.json').read_text())
            self.assertEqual(receipt['status'],'failed_partial_no_retry')
            self.assertEqual(receipt['completed_requests'],0)
            rows=[json.loads(line) for line in (out/'requests.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['error_type'],'RuntimeError')


if __name__=='__main__': unittest.main()

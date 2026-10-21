import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_dimension_inputs as d

class DimensionInputTests(unittest.TestCase):
    def fixtures(self,root):
        corpus={f'image:{i}':dict(path=f'{i}.jpg',sha256=str(i),size=[1,1]) for i in range(12)}
        package=dict(status='prepared_unexecuted',execution_authorized=False,retrieval_package_sha256='a'*64,
            corpus=corpus,queries=[dict(qid='q',split='dev',question='Which?',choices=dict(A='a',B='b',C='c',D='d'),query_image=corpus['image:0'])])
        order=root/'query-order.jsonl';order.write_text(json.dumps(dict(qid='q',corpus_ids=list(corpus)[:10]))+'\n')
        for dim in d.DIMENSIONS:np.save(root/f'rank_indices_{dim}.npy',np.arange(12,dtype=np.int32)[None,:])
        return package,order

    def test_fixed_four_dimensions_no_self_replenish_and_bound_random(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);package,order=self.fixtures(root)
            result=d.build(package,root,order,root/'new',expected_queries=1)
            self.assertEqual(set(result['dimensions']),{'128','256','512','768'})
            for dim in d.DIMENSIONS:
                rows=[json.loads(x) for x in (root/f'new/{dim}/ranks.jsonl').read_text().splitlines()]
                self.assertEqual(rows[0]['corpus_ids'],[f'image:{i}' for i in range(1,11)])
                self.assertEqual(result['dimensions'][str(dim)]['queries'],1)
                self.assertEqual(result['dimensions'][str(dim)]['utility_scores_pending'],10)
                for name in ('cosine','random'):
                    row=json.loads((root/f'new/{dim}/{name}.jsonl').read_text())
                    self.assertEqual(len(row['selected_ids']),3);self.assertNotIn('image:0',row['selected_ids'])
            d.verify_manifest(root/'new')
            p=root/'new/128/ranks.jsonl';p.write_text('tampered')
            with self.assertRaises(ValueError):d.verify_manifest(root/'new')

    def test_labels_and_holdout_are_rejected(self):
        for mutation in ('gold','holdout'):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);package,order=self.fixtures(root)
                if mutation=='gold':package['gold']={'q':'A'}
                else:package['queries'][0]['split']='internal_holdout'
                with self.assertRaises(ValueError):d.build(package,root,order,root/'new',expected_queries=1)

    def test_query_order_or_rank_permutation_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);package,order=self.fixtures(root)
            np.save(root/'rank_indices_128.npy',np.zeros((1,12),dtype=np.int32))
            with self.assertRaises(ValueError):d.build(package,root,order,root/'new',expected_queries=1)

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);package,order=self.fixtures(root);(root/'new').mkdir()
            with self.assertRaises(ValueError):d.build(package,root,order,root/'new',expected_queries=1)

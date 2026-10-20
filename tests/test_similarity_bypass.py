"""Synthetic vectors only: no images, models or archived rankings."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'b-side'))
import similarity_bypass as bypass


class SimilarityBypass(unittest.TestCase):
    def fixture(self, root):
        identities=['self','b','a']+[f'c{i}' for i in range(9)]
        vectors=np.zeros((12,2),dtype=np.float32)
        vectors[:,0]=[1,.9,.9,.8,.7,.6,.5,.4,.3,.2,.1,0]
        np.save(root/'V.npy',vectors)
        np.save(root/'Q.npy',np.array([[1,0]],dtype=np.float32))
        with (root/'pool.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['identity','sha256'],lineterminator='\n');w.writeheader()
            for i,identity in enumerate(identities):w.writerow(dict(identity=identity,sha256=f'{i:064x}'))
        (root/'qids.txt').write_text('q1\n')
        meta={'dtype':'float32','tf32_enabled':False,'batch_size':16,
              'stack_versions':{'numpy':'synthetic-fixture'},'query_identities':{'q1':'self'}}
        (root/'meta.json').write_text(json.dumps(meta))
        return meta

    def run_export(self, root, name='scores.csv'):
        bypass.export(root/'V.npy',root/'Q.npy',root/'pool.csv',root/'qids.txt',
                      root/'meta.json','live',root/name,command=['synthetic-test'])
        with (root/name).open(newline='') as f:return list(csv.DictReader(f))

    def test_stable_order_self_exclusion_and_identity_ties(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            original=(root/'pool.csv').read_bytes()
            rows=self.run_export(root)
            self.assertEqual(rows,self.run_export(root,'repeat.csv'))
            self.assertEqual([r['sha256'] for r in rows], [f'{i:064x}' for i in [2,1,3,4,5,6,7,8,9,10]])
            self.assertEqual([r['rank'] for r in rows],[str(i) for i in range(1,11)])
            self.assertEqual((root/'pool.csv').read_bytes(),original)
            self.assertEqual(rows[0]['pool_id'],'sha256:'+bypass.sha256(root/'pool.csv'))
            self.assertEqual(list(rows[0]),bypass.FIELDS)

    def test_csv_preserves_float32_precision_and_encoding_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);meta=self.fixture(root)
            v=np.load(root/'V.npy');value=np.nextafter(np.float32(.9),np.float32(1))
            v[1,0]=value;np.save(root/'V.npy',v)
            meta['dtype']='bfloat16';(root/'meta.json').write_text(json.dumps(meta))
            rows=self.run_export(root)
            self.assertEqual(float(rows[0]['score_fp32']),float(value))
            self.assertNotEqual(float(rows[0]['score_fp32']),round(float(value),6))
            self.assertEqual(rows[0]['dtype'],'bfloat16')
            self.assertEqual(rows[0]['tf32_enabled'],'false')
            self.assertEqual(rows[0]['batch_size'],'16')
            self.assertEqual(len(rows[0]['command_sha256']),64)

    def test_invalid_inputs_and_existing_output_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);meta=self.fixture(root)
            self.run_export(root)
            with self.assertRaises(FileExistsError):self.run_export(root)
            meta['query_identities']={};(root/'meta.json').write_text(json.dumps(meta))
            with self.assertRaises(ValueError):self.run_export(root,'missing.csv')
            self.assertFalse((root/'missing.csv').exists())
            self.fixture(root);v=np.load(root/'V.npy');v[0,0]=np.nan;np.save(root/'V.npy',v)
            with self.assertRaises(ValueError):self.run_export(root,'nonfinite.csv')
            self.assertFalse((root/'nonfinite.csv').exists())

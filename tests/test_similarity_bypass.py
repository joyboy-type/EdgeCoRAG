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
              'stack_versions':{'numpy':'synthetic-fixture'},'query_identities':{'q1':'self'},
              'normalize_locus':'post_cast_float32','encoder_weights_sha256':'a'*64,
              'model_revision':'synthetic-revision','query_image_sha256':{'q1':'b'*64}}
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
            repeated=self.run_export(root,'repeat.csv')
            self.assertEqual([{k:v for k,v in r.items() if k!='run_id'} for r in rows],
                             [{k:v for k,v in r.items() if k!='run_id'} for r in repeated])
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

    def test_fixed_fields_expose_actual_tie_identity(self):
        expected=['identity','qid','source','rank','sha256','score_fp32',
                  'score_fp32_hex','dtype','tf32_enabled','batch_size','pool_id',
                  'k','sort_key_rule','self_match_removed','n_pool_scored',
                  'normalize_locus','encoder_weights_sha256','model_revision',
                  'query_image_sha256','stack_versions','command_sha256','run_id']
        self.assertEqual(bypass.FIELDS,expected)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root);rows=self.run_export(root)
            self.assertEqual(list(rows[0]),expected)
            self.assertEqual([r['identity'] for r in rows[:2]],['a','b'])
            self.assertEqual(rows[0]['score_fp32'],rows[1]['score_fp32'])
            self.assertEqual(rows[0]['sort_key_rule'],
                             'lexsort(-score, identity) ascending identity on ties')
            self.assertEqual(rows[0]['self_match_removed'],'self')
            self.assertEqual(rows[0]['n_pool_scored'],'12')
            self.assertEqual(rows[0]['k'],'10')

    def test_hex_round_trip_and_receipt_run_id(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            v=np.load(root/'V.npy');value=np.nextafter(np.float32(.9),np.float32(1))
            v[1,0]=value;np.save(root/'V.npy',v)
            receipt=bypass.export(root/'V.npy',root/'Q.npy',root/'pool.csv',
                root/'qids.txt',root/'meta.json','live',root/'scores.csv',
                command=['synthetic-test'])
            with (root/'scores.csv').open(newline='') as f:rows=list(csv.DictReader(f))
            self.assertEqual(rows[0]['score_fp32_hex'],float(np.float32(value)).hex())
            recovered=np.float32(float.fromhex(rows[0]['score_fp32_hex']))
            self.assertEqual(recovered.tobytes(),value.tobytes())
            self.assertEqual(rows[0]['run_id'],receipt['run_id'])
            self.assertTrue(receipt['run_id'].startswith(receipt['command_sha256'][:12]+'_'))
            self.assertRegex(receipt['run_id'],r'^[0-9a-f]{12}_\d{8}T\d{12}Z$')
            self.assertEqual(len({r['run_id'] for r in rows}),1)

    def test_required_provenance_fields_and_k(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);meta=self.fixture(root)
            fields=['normalize_locus','encoder_weights_sha256','model_revision','query_image_sha256']
            for field in fields:
                with self.subTest(missing=field):
                    changed=dict(meta);del changed[field]
                    (root/'meta.json').write_text(json.dumps(changed))
                    with self.assertRaises(ValueError):self.run_export(root,'missing_'+field+'.csv')
                    self.assertFalse((root/('missing_'+field+'.csv')).exists())
            for field,value in [('normalize_locus','unknown'),('encoder_weights_sha256','unknown'),
                                ('model_revision','unknown'),('query_image_sha256',{})]:
                with self.subTest(invalid=field):
                    changed=dict(meta);changed[field]=value
                    (root/'meta.json').write_text(json.dumps(changed))
                    with self.assertRaises(ValueError):self.run_export(root,'invalid_'+field+'.csv')
            (root/'meta.json').write_text(json.dumps(meta))
            receipt=bypass.export(root/'V.npy',root/'Q.npy',root/'pool.csv',root/'qids.txt',
                root/'meta.json','history',root/'five.csv',k=5)
            self.assertEqual(receipt['rows'],5)
            with (root/'five.csv').open(newline='') as f:rows=list(csv.DictReader(f))
            self.assertEqual([r['k'] for r in rows],['5']*5)
            self.assertEqual(rows[0]['normalize_locus'],'post_cast_float32')
            self.assertEqual(rows[0]['encoder_weights_sha256'],'a'*64)
            self.assertEqual(rows[0]['model_revision'],'synthetic-revision')
            self.assertEqual(rows[0]['query_image_sha256'],'b'*64)

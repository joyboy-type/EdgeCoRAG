"""Encode protocol tested with fake arrays/torch only; no encoder loaded."""
import sys,unittest,tempfile,json,hashlib
from pathlib import Path
from types import SimpleNamespace as N
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'b-side'))
import encode_pool as e

class EncodePoolTests(unittest.TestCase):
 def rows(self):
  return ([dict(identity='image:a',sha256='a'*64,path='a.jpg'),dict(identity='image:b',sha256='b'*64,path='b.jpg')],
          [dict(qid='q',identity='image:a',sha256='a'*64,path='a.jpg')])
 def torch(self):return N(backends=N(cuda=N(matmul=N(allow_tf32=True)),cudnn=N(allow_tf32=True)))
 def test_fake_encoder_shapes_metadata_and_fp32_normalization(self):
  with tempfile.TemporaryDirectory() as d:
   c,q=self.rows();t=self.torch();calls=[]
   def encode(rows,batch):
    calls.append((len(rows),batch));return np.ones((len(rows),768),dtype=np.float32)
   out=Path(d)/'new';r=e.encode_bundle(c,q,encode,t,out,e.REVISION,'c'*64,{'numpy':'fixture'})
   self.assertEqual(calls,[(2,16),(1,16)])
   self.assertFalse(t.backends.cuda.matmul.allow_tf32);self.assertFalse(t.backends.cudnn.allow_tf32)
   V=np.load(out/'V.npy');Q=np.load(out/'Q.npy')
   self.assertEqual(V.shape,(2,768));self.assertEqual(Q.shape,(1,768));self.assertEqual(V.dtype,np.float32)
   np.testing.assert_allclose(np.linalg.norm(V,axis=1),1,atol=1e-6)
   meta=json.loads((out/'encoding.json').read_text());self.assertIs(meta['tf32_enabled'],False)
   self.assertEqual(meta['normalize_locus'],'post_cast_float32');self.assertEqual(meta['query_identities'],{'q':'image:a'})
   self.assertEqual(len((out/'pool.csv').read_text().splitlines())-1,2)
   self.assertEqual((out/'qids.txt').read_text(),'q\n');self.assertEqual(r['model_revision'],e.REVISION)
   with self.assertRaises(FileExistsError):e.encode_bundle(c,q,encode,t,out,e.REVISION,'c'*64,{})
 def test_invalid_revision_weights_and_arrays_are_rejected(self):
  c,q=self.rows()
  for revision,weights in [('', 'c'*64),(e.REVISION,''),('wrong','c'*64)]:
   with self.subTest(revision=revision),self.assertRaises(ValueError):e.validate_inputs(c,q,revision,weights)
  for shape,dtype in [((2,768),np.float64),((1,768),np.float32),((2,767),np.float32)]:
   with tempfile.TemporaryDirectory() as d,self.subTest(shape=shape,dtype=dtype):
    with self.assertRaises(ValueError):e.encode_bundle(c,q,lambda rows,b:np.ones(shape,dtype=dtype),self.torch(),Path(d)/'new',e.REVISION,'c'*64,{})
 def test_dry_run_does_not_import_model_or_read_images(self):
  from unittest.mock import patch
  c,q=self.rows()
  with patch('builtins.__import__',side_effect=AssertionError('No runtime import allowed')):
   result=e.validate_inputs(c,q,e.REVISION,'c'*64)
  self.assertEqual(result['V_shape'],[2,768]);self.assertEqual(result['Q_shape'],[1,768])
  self.assertIs(result['tf32_enabled'],False);self.assertFalse(result['model_loaded'])
 def test_protocol_matches_pinned_a18_without_writing_A(self):
  self.assertEqual(e.MODEL_ID,'google/embeddinggemma-2')
  self.assertEqual(e.REVISION,'914f7f89142e33e77833254d9c9b90c3cef7303b')
  self.assertEqual(e.BATCH_SIZE,16)

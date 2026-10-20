import sys,tempfile,csv,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'b-side'))
try:import a_interface_runner as r
except ImportError:r=None
class InterfaceRunner(unittest.TestCase):
 def setUp(self):self.assertIsNotNone(r)
 def test_reordered_rows_are_rejected_not_sorted_back(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'pool.csv'
   with p.open('w') as f:
    w=csv.DictWriter(f,fieldnames=['qid','rank','sha256']);w.writeheader()
    for i in [2,1,*range(3,11)]:w.writerow(dict(qid='q',rank=i,sha256=str(i)))
   with self.assertRaises(ValueError):r.read_pool(p)
 def test_missing_utility_is_not_invented(self):
  with self.assertRaises(ValueError):r.require_scores(None,{'q':['a']*10})
 def test_cpu_thread_missing_rejected_before_recorder(self):
  with self.assertRaises(ValueError):r.thread_value({'rows':[]})
 def test_fp32_policy_and_normalization_are_explicit_without_loading(self):
  from types import SimpleNamespace as N
  import numpy as np
  dtype=object();torch=N(float32=dtype,backends=N(cuda=N(matmul=N(allow_tf32=True)),cudnn=N(allow_tf32=True)))
  image=object()
  class Encoder:
   def parameters(self):return [N(dtype=dtype)]
   def encode(self,*args,**kwargs):
    if args[0]!=[{'image':image}]:raise ValueError('A protocol requires image dict input')
    return [[3,4]]
  with self.assertRaises(ValueError):r.encode_fp32(Encoder(),[],torch)
  result=r.encode_fp32(Encoder(),[image],torch,authorized=True)
  self.assertEqual(result.dtype,np.dtype('float32'))
  np.testing.assert_allclose(result,[[.6,.8]])
  self.assertFalse(torch.backends.cuda.matmul.allow_tf32);self.assertFalse(torch.backends.cudnn.allow_tf32)
 def test_utility_export_preserves_raw_logits_all_ten_and_rank_order(self):
  self.assertTrue(hasattr(r,'export_utility_scores'))
  pool=[{'sha256':str(i)} for i in range(10)];values=[-3.,4.,*range(8)]
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'scores.csv';receipt=r.export_utility_scores(p,'q',pool,values,batch_size=1)
   with p.open() as f:reader=csv.DictReader(f);self.assertEqual(reader.fieldnames,['qid','sha256','score']);rows=list(reader)
   self.assertEqual([v['sha256'] for v in rows],[str(i) for i in range(10)])
   self.assertEqual(float(rows[0]['score']),-3.);self.assertEqual(len(rows),10)
   self.assertEqual(receipt['utility_input_order'],[str(i) for i in range(10)])
   self.assertEqual(receipt['utility_batch_size'],1)

class InterfaceReleaseBinding(unittest.TestCase):
 def test_no_proof_stays_provisional(self):
  self.assertEqual(r.interface_status(Path('.'),None),(False,r.PROVISIONAL))
 def test_missing_or_incomplete_proof_cannot_mark_passed(self):
  import json
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'proof.json';p.write_text(json.dumps({'B1_passed':True,'commands':[]}))
   with self.assertRaises(ValueError):r.interface_status(Path(d),p)
 def test_proof_for_different_manifest_is_rejected(self):
  import json
  with tempfile.TemporaryDirectory() as d:
   a=Path(d);p=a/'proof.json';p.write_text(json.dumps({'B1_passed':True,'commands':[{'returncode':0}]*4,'A_commit':'c77e91c07a288b719683c51258324c11431c12d5','artifact_manifest_sha256':'0'*64,'checks':{'a17_default':{'artifacts_checked':36,'fail_count':0},'a17_strict':{'artifacts_checked':36,'fail_count':0}}}))
   (a/'a-side/retrieval_if_v1').mkdir(parents=True);(a/'a-side/retrieval_if_v1/artifacts.json').write_text('{}')
   with self.assertRaises(ValueError):r.interface_status(a,p)

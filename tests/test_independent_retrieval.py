"""Hand-checked synthetic contracts; no model/network imports or experiment data."""
import importlib.util
from pathlib import Path
import unittest,tempfile,json,subprocess,sys
import numpy as np
ENTRY=Path(__file__).resolve().parents[1]/'a-side/scripts/independent_retrieval.py'

class RetrievalContracts(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if not ENTRY.exists():return
  spec=importlib.util.spec_from_file_location('independent_retrieval',ENTRY);cls.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.m)
 def setUp(self):self.assertTrue(ENTRY.exists(),'Independent retrieval entry is not implemented')
 def test_hit_recall_mrr_use_full_fixed_denominator(self):
  d=self.m.evaluate_rankings(['q1','q2'],[['a','b','c'],['c','b','a']],{'q1':['a','b'],'q2':['absent']},[1,2]);self.assertEqual(d['questions'],2);self.assertEqual(d['hit_at_1'],.5);self.assertEqual(d['recall_at_1'],.25);self.assertEqual(d['recall_at_2'],.5);self.assertEqual(d['mrr'],.5);self.assertEqual(d['questions_without_indexed_gt'],1)
 def test_full_rank_mrr_is_not_top_k_mrr(self):
  d=self.m.evaluate_rankings(['q'],[['a','b','c']],{'q':['c']},[1]);self.assertAlmostEqual(d['mrr'],1/3);self.assertEqual(d['hit_at_1'],0)
 def test_duplicate_missing_and_unknown_query_or_candidate_rejected(self):
  for q,r,g in [(['q'],[['a','a']],{'q':['a']}),(['q','q'],[['a'],['a']],{'q':['a']}),(['q'],[['a']],{'other':['a']}),(['q'],[['a'],['b']],{'q':['a']}),(['q','r'],[['a','b'],['a','c']],{'q':['a'],'r':['b']})]:
   with self.assertRaises(ValueError):self.m.evaluate_rankings(q,r,g,[1])
 def test_truncation_renormalizes_and_rejects_bad_vectors(self):
  a=self.m.normalize(np.array([[3.,4.,12.]]),2);np.testing.assert_allclose(a,[[.6,.8]])
  for a,d in [(np.zeros((1,2)),2),(np.array([[float('nan'),1.]]),2),(np.ones((1,2)),3)]:
   with self.assertRaises(ValueError):self.m.normalize(a,d)
 def test_weight_manifest_cannot_pin_unrelated_file_only(self):
  import hashlib
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'unrelated';p.write_bytes(b'x');spec={'required_files':[{'path':'unrelated','algorithm':'sha256','digest':hashlib.sha256(b'x').hexdigest()}]}
   with self.assertRaises(ValueError):self.m.validate_weights(Path(t),spec)
 def test_numeric_corpus_id_is_not_silently_coerced(self):
  import hashlib
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'image';p.write_bytes(b'x');h=hashlib.sha256(b'x').hexdigest();data={'status':'prepared_unexecuted','queries':[{'qid':'q','split':'dev','path':'image','sha256':h}],'corpus':[{'id':1,'path':'image','sha256':h}],'gold':{'q':['1']},'query_modality':'image_only','models':{'fake':{'revision':'0'*40,'required_files':[{'path':'x'}]}}};f=Path(t)/'package.json';f.write_text(json.dumps(data))
   with self.assertRaisesRegex(ValueError,'[Ii]dentit'):self.m.validate_package(f,Path(t))
 def test_combined_encoding_keeps_split_score_denominators_separate(self):
  self.assertTrue(hasattr(self.m,'evaluate_cohorts'),'Split-aware scoring not implemented')
  result=self.m.evaluate_cohorts([{'qid':'devq','split':'dev'},{'qid':'testq','split':'frozen_test'}],[['a','b'],['b','a']],{'devq':['a'],'testq':['a']},[1])
  self.assertEqual(result['dev']['questions'],1);self.assertEqual(result['dev']['hit_at_1'],1);self.assertEqual(result['frozen_test']['hit_at_1'],0);self.assertEqual(result['frozen_test']['mrr'],.5)
 def test_gold_string_is_not_a_list_of_evidence_ids(self):
  with self.assertRaises(ValueError):self.m.evaluate_rankings(['q'],[['a','b']],{'q':'ab'},[1])
 def test_default_cli_never_loads_weights_or_creates_output(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'invalid.json';p.write_text('{}');o=Path(t)/'results';r=subprocess.run([sys.executable,str(ENTRY),'--package',str(p),'--root',t,'--output',str(o)],capture_output=True,text=True);self.assertEqual(r.returncode,2);self.assertFalse(o.exists())
 def test_query_gold_leakage_is_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'package.json';p.write_text(json.dumps({'status':'prepared_unexecuted','queries':[{'qid':'q','path':'x','sha256':'0'*64,'answer':'A'}],'corpus':[],'gold':{'q':['x']},'models':{}}))
   with self.assertRaisesRegex(ValueError,'[Qq]uery'):self.m.validate_package(p,Path(t))

if __name__=='__main__':unittest.main()

"""Synthetic stage boundary checks; never loads a model or research data."""
import unittest,tempfile,json,hashlib
from pathlib import Path
try:
 import mmdocrag_campaign as m
except ImportError:
 m=None
class CampaignTests(unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(m,'Campaign stage boundary not implemented')
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.rows=[{'q_id':1,'question':'Fictional','text_quotes':[{'quote_id':'text1','text':'Fictional'}],'img_quotes':[]}]
  self.pkg=self.root/'pkg';self.pkg.mkdir();self.man={'split':'evaluation','setting':'15','qids':[1],'qid_type':'int','dataset_revision':'SYNTHETIC'}
  self.write()
 def write(self):
  (self.pkg/'manifest.json').write_text(json.dumps(self.man));(self.pkg/'generation_inputs.jsonl').write_text(json.dumps(self.rows[0])+'\n')
 def test_scoped_eval_package_accepted(self):
  _,rows,_=m.validate_package(self.pkg,self.root,'evaluation');self.assertEqual(rows,self.rows)
 def test_labels_rejected(self):
  self.rows[0]['answer_short']='forbidden';self.write()
  with self.assertRaises(ValueError):m.validate_package(self.pkg,self.root,'evaluation')
 def test_cross_split_qid_rejected(self):
  with self.assertRaises(ValueError):m.validate_package(self.pkg,self.root,'dev')
 def test_stage_complete_cannot_be_forged_by_counts(self):
  d=self.root/'prev'/'model';d.mkdir(parents=True)
  r={'status':'completed','expected_questions':1,'completed_questions':1,'identity':{'model':'model','qids':[1],'prompt_sha256':'P','registry_sha256':'R','dataset_revision':'SYNTHETIC'},'predictions_sha256':'fake'}
  (d/'receipt.json').write_text(json.dumps(r));(d/'predictions.jsonl').write_text('')
  with self.assertRaises(ValueError):m.completed_stage(self.root/'prev',['model'],[1],{'prompt_sha256':'P','registry_sha256':'R','dataset_revision':'SYNTHETIC'})
 def test_stage_content_and_identity_checked(self):
  d=self.root/'prev'/'model';d.mkdir(parents=True);p=d/'predictions.jsonl';p.write_text(json.dumps({'q_id':1,'response':'Fictional','generation_status':'completed'})+'\n')
  r={'status':'completed','expected_questions':1,'completed_questions':1,'identity':{'model':'model','qids':[1],'prompt_sha256':'P','registry_sha256':'R','dataset_revision':'SYNTHETIC'},'predictions_sha256':m.sha(p)}
  (d/'receipt.json').write_text(json.dumps(r));pins=m.completed_stage(self.root/'prev',['model'],[1],{'prompt_sha256':'P','registry_sha256':'R','dataset_revision':'SYNTHETIC'});self.assertIn('model',pins)
  r['identity']['prompt_sha256']='changed';(d/'receipt.json').write_text(json.dumps(r))
  with self.assertRaises(ValueError):m.completed_stage(self.root/'prev',['model'],[1],{'prompt_sha256':'P','registry_sha256':'R','dataset_revision':'SYNTHETIC'})
 def test_freeze_binds_full_predecessor_and_code(self):
  freeze={'reviewed':True,'accept_partial_truncation':True,'pins':{'P':'ok'}}
  m.validate_freeze(freeze,{'P':'ok'})
  for bad in [{'reviewed':False,'pins':{'P':'ok'}},{'reviewed':True,'accept_partial_truncation':True,'pins':{'P':'changed'}}]:
   with self.assertRaises(ValueError):m.validate_freeze(bad,{'P':'ok'})
 def test_wrong_predecessor_manifest_and_count_rejected(self):
  entry={'manifest_sha256':'WRONG','files_sha256':{'generation_inputs':'WRONG'}}
  with self.assertRaises(ValueError):m.validate_predecessor_manifest(self.pkg,entry,1)
  entry={'manifest_sha256':m.sha(self.pkg/'manifest.json'),'files_sha256':{'generation_inputs':m.sha(self.pkg/'generation_inputs.jsonl')}}
  with self.assertRaises(ValueError):m.validate_predecessor_manifest(self.pkg,entry,8)
 def test_model_revision_is_part_of_predecessor_identity(self):
  d=self.root/'prev'/'model';d.mkdir(parents=True);p=d/'predictions.jsonl';p.write_text(json.dumps({'q_id':1,'response':'Fictional','generation_status':'completed'})+'\n')
  r={'status':'completed','expected_questions':1,'completed_questions':1,'identity':{'model':'model','qids':[1],'model_revision':'wrong'},'predictions_sha256':m.sha(p)}
  (d/'receipt.json').write_text(json.dumps(r))
  with self.assertRaises(ValueError):m.completed_stage(self.root/'prev',['model'],[1],{},revisions={'model':'correct'})
 def predecessor(self, row_updates=None, receipt_updates=None, identity_updates=None):
  d=self.root/'prev'/'model';d.mkdir(parents=True,exist_ok=True);p=d/'predictions.jsonl'
  row={'q_id':1,'response':'Fictional','generation_status':'completed'}
  row.update(row_updates or {});p.write_text(json.dumps(row)+'\n')
  identity={'model':'model','qids':[1]};identity.update(identity_updates or {})
  receipt={'status':'completed','expected_questions':1,'completed_questions':1,'identity':identity,'predictions_sha256':m.sha(p)}
  receipt.update(receipt_updates or {});(d/'receipt.json').write_text(json.dumps(receipt))
 def test_completed_flag_cannot_hide_generation_error(self):
  self.predecessor({'generation_error':'backend failed'})
  with self.assertRaises(ValueError):m.completed_stage(self.root/'prev',['model'],[1],{})
 def test_predecessor_prediction_qid_must_be_integer_not_equal_alias(self):
  for qid in [True,1.0]:
   with self.subTest(qid=qid):
    self.predecessor({'q_id':qid})
    with self.assertRaises(ValueError):m.completed_stage(self.root/'prev',['model'],[1],{})
 def test_predecessor_identity_and_counts_cannot_use_boolean_aliases(self):
  for updates,identity in [({'expected_questions':True},{}),({'completed_questions':1.0},{}),({}, {'qids':[True]})]:
   with self.subTest(receipt=updates,identity=identity):
    self.predecessor(receipt_updates=updates,identity_updates=identity)
    with self.assertRaises(ValueError):m.completed_stage(self.root/'prev',['model'],[1],{})
 def test_completed_empty_response_is_preserved_as_normal_result(self):
  self.predecessor({'response':'','generation_error':None})
  pins=m.completed_stage(self.root/'prev',['model'],[1],{})
  self.assertIn('model',pins)
if __name__=='__main__':unittest.main(verbosity=2)

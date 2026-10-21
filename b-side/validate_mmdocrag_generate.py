"""Synthetic contract checks for the new technical-dev generation entry; no model loaded."""
from pathlib import Path
import tempfile,json,hashlib,unittest
try:
 import mmdocrag_generate as module
except ImportError:
 module=None

class ContractTests(unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(module,'MMDocRAG generation entry is not implemented')
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.pkg=self.root/'pkg';self.pkg.mkdir();self.image=self.root/'image.bin';self.image.write_bytes(b'SYNTHETIC_IMAGE_BYTES');self.sha=hashlib.sha256(self.image.read_bytes()).hexdigest()
  self.manifest={'qids':[10,20],'qid_type':'int','split':'dev','setting':'15','dataset_revision':'SYNTHETIC','protocol_id':'SYNTHETIC'}
  self.rows=[{'q_id':i,'question':'Fictional question','text_quotes':[{'quote_id':'text1','text':'Fictional evidence'}],'img_quotes':[{'quote_id':'image1','local_content_path':'image.bin','sha256':self.sha,'width':1,'height':1}]} for i in [10,20]];self.save()
 def save(self):
  (self.pkg/'manifest.json').write_text(json.dumps(self.manifest));(self.pkg/'generation_inputs.jsonl').write_text('\n'.join(json.dumps(r) for r in self.rows)+'\n')
 def test_valid_messages_and_image_order_exclude_labels(self):
  manifest,rows,identity=module.validate_package(self.pkg,self.root);messages=module.build_messages(rows[0],self.root,lambda p:'DECODED_IMAGE','SYSTEM')
  self.assertEqual(messages[0],{'role':'system','content':[{'type':'text','text':'SYSTEM'}]});self.assertEqual([v['image'] for v in messages[1]['content'] if v['type']=='image'],['DECODED_IMAGE']);self.assertIn('[1] Fictional evidence',messages[1]['content'][0]['text'])
 def test_gold_field_is_rejected(self):
  self.rows[0]['answer_interleaved']='FORBIDDEN';self.save()
  with self.assertRaises(ValueError):module.validate_package(self.pkg,self.root)
 def test_qid_order_missing_and_wrong_split_rejected(self):
  for bad in ['order','missing','split']:
   with self.subTest(bad=bad):
    oldrows=list(self.rows);oldsplit=self.manifest['split']
    if bad=='order':self.rows.reverse()
    elif bad=='missing':self.rows.pop()
    else:self.manifest['split']='evaluation'
    self.save()
    with self.assertRaises(ValueError):module.validate_package(self.pkg,self.root)
    self.rows=oldrows;self.manifest['split']=oldsplit
 def test_changed_image_is_rejected_before_backend_creation(self):
  self.image.write_bytes(b'CHANGED')
  with self.assertRaises(ValueError):module.validate_package(self.pkg,self.root)
 def test_empty_and_truncated_responses_remain_in_fixed_denominator(self):
  def infer(row):return {'response':'' if row['q_id']==10 else 'partial [1]','in_tok':12,'out_tok':512,'truncated':True}
  output=self.root/'output';receipt=module.run_stage(self.rows,infer,output,{'synthetic':True},warmups=0);pred=[json.loads(s) for s in (output/'predictions.jsonl').read_text().splitlines()]
  self.assertEqual(receipt['status'],'completed');self.assertEqual(receipt['expected_questions'],2);self.assertEqual([p['q_id'] for p in pred],[10,20]);self.assertEqual(pred[0]['response'],'');self.assertEqual(pred[1]['response'],'partial [1]');self.assertTrue(pred[1]['truncated'])
 def test_technical_failure_stops_with_partial_receipt_and_no_fake_scores(self):
  def infer(row):
   if row['q_id']==20:raise RuntimeError('SYNTHETIC_TECHNICAL_ERROR')
   return {'response':'[1]','in_tok':2,'out_tok':1,'truncated':False}
  output=self.root/'failure';r=module.run_stage(self.rows,infer,output,{'synthetic':True},warmups=0);self.assertEqual(r['status'],'technical_failure');self.assertEqual(r['completed_questions'],1);self.assertEqual(r['failed_q_id'],20);self.assertNotIn('scores',r)
 def test_existing_output_is_not_overwritten(self):
  out=self.root/'existing';out.mkdir();marker=out/'predictions.jsonl';marker.write_text('KEEP')
  with self.assertRaises(FileExistsError):module.run_stage(self.rows,lambda row:None,out,{},warmups=0)
  self.assertEqual(marker.read_text(),'KEEP')
 def test_warmup_is_separate_from_scored_predictions(self):
  out=self.root/'warm';r=module.run_stage(self.rows,lambda row:{'response':'[1]','in_tok':2,'out_tok':1,'truncated':False},out,{},warmups=3)
  self.assertEqual(r['warmup_count'],3);self.assertEqual(len((out/'predictions.jsonl').read_text().splitlines()),2);self.assertEqual(len((out/'warmups.jsonl').read_text().splitlines()),3)

 def test_registry_change_with_same_revision_rejected(self):
  self.assertTrue(hasattr(module,'validate_approved_registry'),'Complete configuration binding missing')
  path=self.root/'registry.json';path.write_text(json.dumps({'models':{'fixture':{'revision':'fixed','dtype':'bfloat16'}}}));approved=hashlib.sha256(path.read_bytes()).hexdigest();path.write_text(json.dumps({'models':{'fixture':{'revision':'fixed','dtype':'float32'}}}))
  with self.assertRaises(ValueError):module.validate_approved_registry(path,approved)
 def test_preprocess_drift_is_rejected(self):
  self.assertTrue(hasattr(module,'validate_native_identity'),'Native CPU identity gate missing')
  expected={'rendered_sha256':'rendered','input_ids_sha256':'ids','tensor_shapes':{'input_ids':[1,9]}}
  module.validate_native_identity(expected,'rendered','ids',{'input_ids':[1,9]})
  for render,ids,shapes in [('changed','ids',{'input_ids':[1,9]}),('rendered','changed',{'input_ids':[1,9]}),('rendered','ids',{'input_ids':[1,10]})]:
   with self.assertRaises(ValueError):module.validate_native_identity(expected,render,ids,shapes)
 def test_model_load_failure_has_persisted_receipt(self):
  import inspect
  self.assertIn('backend_factory',inspect.signature(module.run_stage).parameters,'Backend allocation happens outside stage receipt')
  def factory():raise RuntimeError('SYNTHETIC_MODEL_LOAD_OOM')
  output=self.root/'load_failure';r=module.run_stage(self.rows,None,output,{},warmups=0,backend_factory=factory);saved=json.loads((output/'receipt.json').read_text())
  self.assertEqual(r['status'],'technical_failure');self.assertEqual(saved['phase'],'model_loading');self.assertEqual(saved['completed_questions'],0);self.assertIn('SYNTHETIC_MODEL_LOAD_OOM',saved['error'])

if __name__=='__main__':unittest.main()

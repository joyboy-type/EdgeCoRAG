import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from completion_rules import feasibility_passed,run_items,summary_counts,complete_coverage
class CompletionRulesTests(unittest.TestCase):
 def test_individual_latency_not_mean(self):
  self.assertFalse(feasibility_passed([{'status':'ok','end_to_end_seconds':31},{'status':'ok','end_to_end_seconds':1},{'status':'ok','end_to_end_seconds':1}]))
 def test_three_successful_items_required(self):
  self.assertFalse(feasibility_passed([{'status':'ok','end_to_end_seconds':1}]))
  self.assertTrue(feasibility_passed([{'status':'ok','end_to_end_seconds':30}]*3))
 def test_oom_cannot_pass_with_previous_fast_items(self):
  self.assertFalse(feasibility_passed([{'status':'ok','end_to_end_seconds':1}]*2+[{'status':'OOM'}]))
 def test_first_exception_counts_attempt_and_stops_immediately(self):
  state={};output=[]
  def infer(row):raise RuntimeError('broken')
  rows=run_items([{'qid':'q1','raw_id':'1'},{'qid':'q2','raw_id':'2'}],{'1':'A','2':'B'},infer,state,output.append)
  self.assertEqual((state['attempted'],state['failed'],len(rows),len(output)),(1,1,1,1));self.assertEqual(rows[0]['correct'],False)
 def test_parse_error_keeps_denominator_without_technical_failure(self):
  state={};rows=run_items([{'qid':'q','raw_id':'1'}],{'1':'A'},lambda x:{'response':'unparseable','status':'ok'},state,lambda x:None)
  self.assertFalse(rows[0]['correct']);self.assertEqual(state['failed'],0)
 def test_exact_five_percent_is_not_stop(self):
  state={'attempted':19,'failed':0};calls=[]
  def infer(x):raise RuntimeError('broken')
  run_items([{'qid':'q','raw_id':'1'}],{'1':'A'},infer,state,calls.append);self.assertIsNone(state.get('stopped_reason'))
 def test_every_row_durable_before_stop(self):
  state={};seen=[]
  rows=run_items([{'qid':'a','raw_id':'1'}],{'1':'A'},lambda x:{'response':'A','status':'ok'},state,seen.append);self.assertEqual(rows,seen)
 def test_partial_set_never_full_accuracy(self):
  r=summary_counts([{'correct':True}],3);self.assertFalse(r['complete']);self.assertIsNone(r['accuracy']);self.assertEqual(r['accuracy_observed'],1)
 def test_missing_split_not_complete(self):self.assertFalse(complete_coverage([{'split':'dev','n_rows':5,'complete':True}],{'dev':5,'internal_holdout':2,'frozen_test':29},'split'))
if __name__=='__main__':unittest.main()

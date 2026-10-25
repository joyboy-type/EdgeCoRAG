import unittest,copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import supplement_core as c
class SupplementTests(unittest.TestCase):
 def test_equal_count_keeps_order_and_text(self):
  row={'qid':'q','evidence':[{'sha256':str(i)} for i in range(5)],'query_image':{'sha256':'q'},'model_request':{'messages':[{'role':'user','content':[{'type':'image','image_index':i} for i in range(6)]+[{'type':'text','text':'unchanged'}]}]}}
  old=copy.deepcopy(row);new=c.equal_count(row)
  self.assertEqual(row,old);self.assertEqual(new['evidence'],row['evidence'][:3]);self.assertEqual([x.get('image_index') for x in new['model_request']['messages'][0]['content'][:-1]],[0,1,2,3]);self.assertEqual(new['model_request']['messages'][0]['content'][-1]['text'],'unchanged')
 def test_singleton_not_padded(self):
  row={'evidence':[{'sha256':'x'}],'model_request':{'messages':[{'content':[{'type':'image','image_index':0},{'type':'image','image_index':1},{'type':'text','text':'t'}]}]}}
  self.assertEqual(len(c.equal_count(row)['evidence']),1)
 def test_invalid_count_rejected(self):
  with self.assertRaises(ValueError):c.equal_count({'evidence':[{},{}]})
 def test_missing_query_never_filled(self):
  with self.assertRaises(ValueError):c.check_query_ids(['q1','q2'],['q1'])
 def test_order_and_duplicates(self):
  with self.assertRaises(ValueError):c.check_query_ids(['q1'],['q1','q1'])
 def test_cost_length_threshold(self):
  self.assertEqual(c.cost_status(2,6),'length_not_effective');self.assertEqual(c.cost_status(2,6.1),'effective');self.assertEqual(c.extra100(2,2,10,10),None);self.assertEqual(c.extra100(2,12,10,20),100)
 def test_rank_ties_identity_and_full_mrr(self):
  r=c.score_rank(['a','b','c','d','e','f'],{'f'},1,'a')
  self.assertEqual(r['mrr'],.2);self.assertEqual(r['hit_at_5'],1);self.assertEqual(r['recall_at_5'],1)
 def test_missing_gold_stays_in_recall_denominator(self):
  r=c.score_rank(['a','b'],{'a','outside'},2,None);self.assertEqual(r['recall_at_5'],.5)
 def test_budget_classification(self):
  self.assertEqual(c.dimension_status([.03,0,0,0,0]),'within_tolerance');self.assertEqual(c.dimension_status([.030001,0,0,0,0]),'not_compressible')

class CostTests(unittest.TestCase):
 def test_alternation_and_warmups(self):
  jobs=c.cost_jobs(['a','b']);self.assertEqual(jobs[:6],[('a',2,True)]*3+[('a',256,True)]*3);self.assertEqual(jobs[6:],[('a',2,False),('a',256,False),('b',256,False),('b',2,False)])
 def test_energy_subwindow_not_full_request(self):
  r=c.sample_energy([{'epoch':1.,'power_W':100},{'epoch':2.,'power_W':200},{'epoch':3.,'power_W':100}],.5,3.5)
  self.assertAlmostEqual(r['trapezoidal_Wh'],300/3600);self.assertEqual(r['sample_window_s'],2);self.assertFalse(r['full_request_covered'])
 def test_missing_power_not_zero(self):
  r=c.sample_energy([{'epoch':1.,'power_W':None}],0,2);self.assertIsNone(r['trapezoidal_Wh'])

class PairedTests(unittest.TestCase):
 def test_transition_cells_exhaust_fixed_denominator(self):
  z=c.transition_counts([(False,True),(True,False),(True,True),(False,False)])
  self.assertEqual(z,{'rescue':1,'harm':1,'same_correct':1,'same_wrong':1,'unchanged':2,'n':4,'net':0})
 def test_retention_uses_lower_bound_and_same_set_reference(self):
  self.assertEqual(c.retention_status(.071,.1),'meets_retention');self.assertEqual(c.retention_status(.069,.1),'does_not_meet_retention');self.assertEqual(c.retention_status(.1,0),'not_applicable')

if __name__=='__main__':unittest.main()

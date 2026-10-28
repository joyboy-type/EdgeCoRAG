import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from completion_rules import run_warmed_gate
class WarmedGateTests(unittest.TestCase):
 def setUp(self):self.items=[{'qid':str(i),'raw_id':str(i)} for i in range(3)];self.gold={str(i):'A' for i in range(3)}
 def test_fixed_three_warmups_before_three_timed_items(self):
  calls=[];warm=[];timed=[]
  def infer(row,limit):calls.append((row['qid'],limit));return {'response':'A','end_to_end_seconds':120 if limit==600 else 1,'status':'ok'}
  gate=run_warmed_gate(self.items,self.gold,infer,warm.append,timed.append)
  self.assertTrue(gate['passed']);self.assertEqual(calls,[(str(i),600) for i in range(3)]+[(str(i),30) for i in range(3)]);self.assertEqual(len(warm),3);self.assertEqual(len(timed),3)
 def test_warmup_oom_stops_without_timed_attempt_or_retry(self):
  calls=[]
  def infer(row,limit):calls.append(row['qid']);raise RuntimeError('CUDA out of memory')
  gate=run_warmed_gate(self.items,self.gold,infer,lambda x:None,lambda x:None)
  self.assertFalse(gate['passed']);self.assertEqual(calls,['0']);self.assertEqual(gate['results'],[])
 def test_one_timed_item_over_thirty_still_fails(self):
  def infer(row,limit):return {'response':'A','status':'ok','end_to_end_seconds':31 if limit==30 and row['qid']=='1' else 1}
  self.assertFalse(run_warmed_gate(self.items,self.gold,infer,lambda x:None,lambda x:None)['passed'])
 def test_no_changing_or_extending_warmup_list(self):
  with self.assertRaises(AssertionError):run_warmed_gate(self.items[:2],self.gold,lambda row,limit:None,lambda x:None,lambda x:None)
if __name__=='__main__':unittest.main()

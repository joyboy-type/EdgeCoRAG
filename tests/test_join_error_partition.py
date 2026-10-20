import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis/next_stage_20261019'))
import join_error_partition as j
class IdentityJoinTests(unittest.TestCase):
 def test_slot_ids_resolve_through_context_without_sha_alias_guessing(self):
  row={'qid':'q','condition':'S1','context_key':'ctx','evidence_ids_order':['q#official_retrieved0']}
  context={'ctx':{'condition':'S1','input':{'qid':'q','evidence':[{'evidence_id':'q#official_retrieved0','sha256':'a'*64}]}}}
  self.assertEqual(j.resolve(row,context),(['a'*64],''))
  self.assertNotEqual(row['evidence_ids_order'][0],'image:'+'a'*64)
  self.assertEqual(j.resolve(row,{}),(None,'missing_context'))
  context['ctx']['input']['evidence'][0]['evidence_id']='other'
  with self.assertRaises(ValueError):j.resolve(row,context)
 def test_original_rules_expose_overlaps_and_uncovered_correct_hits(self):
  a=j.flags(True,False,False)
  self.assertEqual(a,{'未检索到':True,'检索到但答错':False,'检索伤害':True,'无关但未伤害':False})
  b=j.flags(False,False,False)
  self.assertTrue(b['未检索到'] and b['无关但未伤害'])
  self.assertEqual(sum(j.flags(False,True,True).values()),0)
  c=j.flags(True,False,True)
  self.assertTrue(c['检索到但答错'] and c['检索伤害'])
 def test_direct_comparison_is_not_a_valid_join(self):
  self.assertEqual(j.gold_hit(['a'*64],['image:'+'a'*64]),True)
  self.assertEqual(j.gold_hit(['b'*64],['image:'+'a'*64]),False)
  with self.assertRaises(ValueError):j.gold_hit(['a'*64],['q#gt0'])

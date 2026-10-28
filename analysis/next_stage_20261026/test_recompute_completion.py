import csv,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from recompute_completion import validate_rows
class CompletionExportTests(unittest.TestCase):
 def write(self,root,rows):
  p=Path(root)/'x.csv'
  with p.open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['raw_id','qid','choice','gold','correct','status']);w.writeheader();w.writerows(rows)
  return p
 def row(self,q='q1'):return {'raw_id':q,'qid':q,'choice':'A','gold':'A','correct':'True','status':'ok'}
 def test_valid_rows(self):
  with tempfile.TemporaryDirectory() as d:self.assertEqual(len(validate_rows(self.write(d,[self.row()]),1)),1)
 def test_duplicate_qid_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(AssertionError):validate_rows(self.write(d,[self.row(),self.row()]),2)
 def test_incorrect_correctness_flag_rejected(self):
  r=self.row();r['correct']='False'
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(AssertionError):validate_rows(self.write(d,[r]),1)
 def test_missing_row_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(AssertionError):validate_rows(self.write(d,[self.row()]),2)
 def test_changed_file_digest_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(AssertionError):validate_rows(self.write(d,[self.row()]),1,'0'*64)
if __name__=='__main__':unittest.main()

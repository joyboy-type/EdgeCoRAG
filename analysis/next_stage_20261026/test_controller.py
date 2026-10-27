import sys,tempfile,unittest,tarfile,hashlib,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
class ControllerTests(unittest.TestCase):
 def test_guard_rejects_incomplete_transfer(self):
  from completion_controller import migration_valid
  self.assertFalse(migration_valid({'complete':False,'checked':1,'expected':1,'bad':[],'total_bytes':3,'manifest_sha256':'x'},{'file_count':1,'total_bytes':3},'x'))
 def test_guard_rejects_wrong_hash(self):
  from completion_controller import migration_valid
  r={'complete':True,'checked':1,'expected':1,'bad':[],'total_bytes':3,'manifest_sha256':'wrong'}
  self.assertFalse(migration_valid(r,{'file_count':1,'total_bytes':3},'x'))
 def test_archive_contains_and_verifies_partial(self):
  from completion_controller import archive_results
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/'run';root.mkdir();(root/'partial.csv').write_text('qid\n1\n');(root/'error.json').write_text('{"error":"OOM"}')
   archive=archive_results(root,Path(td)/'archive.tar.gz')
   self.assertTrue(archive['verified']);self.assertEqual(archive['files'],2)
   with tarfile.open(archive['path']) as tf:self.assertEqual(tf.extractfile('run/partial.csv').read(),b'qid\n1\n')
 def test_command_timeout_keeps_output_and_kills_job(self):
  from completion_controller import run_command
  with tempfile.TemporaryDirectory() as td:
   state={};rc=run_command([sys.executable,'-u','-c','import time;print("started");time.sleep(10)'],Path(td)/'run.log',.1,state)
   self.assertEqual(rc,124);self.assertIn('started',(Path(td)/'run.log').read_text());self.assertIsNone(state.get('active_pgid'))
if __name__=='__main__':unittest.main()

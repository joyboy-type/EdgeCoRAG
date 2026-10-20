import sys,unittest,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis/next_stage_20261019'))
try:import a_interface_evidence as e
except ImportError:e=None
class Evidence(unittest.TestCase):
 def test_line_ending_proof_never_calls_raw_manifest_passed(self):
  self.assertIsNotNone(e)
  raw=b'a,b\n1,2\n';manifest=dict(sha256=hashlib.sha256(b'a,b\r\n1,2\r\n').hexdigest(),bytes=10,rows=1)
  r=e.newline_proof(raw,manifest)
  self.assertFalse(r['raw_matches_manifest']);self.assertTrue(r['crlf_reconstruction_matches_manifest'])
  self.assertEqual(r['normalized_bytes'],8)
  changed=e.newline_proof(b'a,b\n1,3\n',manifest)
  self.assertFalse(changed['crlf_reconstruction_matches_manifest'])
 def test_b1_module_imports_without_any_site_packages(self):
  import subprocess
  code="import sys;sys.path.insert(0,"+repr(str(Path(__file__).resolve().parents[1]/'analysis/next_stage_20261019'))+");import a_interface_evidence"
  p=subprocess.run([sys.executable,'-S','-c',code],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)

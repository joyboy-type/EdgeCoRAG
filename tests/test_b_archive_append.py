"""Append-only receipt extension must not silently rewrite old facts."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis/next_stage_20261019'))
try:import b_append_archive as a
except ImportError:a=None

class AppendReceipt(unittest.TestCase):
 def test_old_fields_survive_and_existing_extension_cannot_be_replaced(self):
  self.assertIsNotNone(a,'Append-only archive extension missing')
  old={'source_pins':{'x':'hash'},'cpu_thread_warning':True}
  current=a.append_only(old,{'sha256':'archive'})
  self.assertEqual({k:v for k,v in current.items() if k!='source_archive'},old)
  self.assertTrue(current['cpu_thread_warning'])
  with self.assertRaises(ValueError):a.append_only(current,{'sha256':'other'})

import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import freeze_retrieval_interface as f

class FreezeTests(unittest.TestCase):
    def test_freeze_has_replay_rules_source_hashes_and_no_machine_paths(self):
        repo=Path(__file__).resolve().parents[2]
        spec=dict(model_id='model',revision='a'*40,dimension=768,required_files=[dict(path='weights.bin',bytes=3,algorithm='sha256',digest=f.bytes_sha(b'abc'))])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'weights.bin').write_bytes(b'abc')
            (root/'preprocessor_config.json').write_text(json.dumps(dict(do_resize=True,size=224)))
            value=f.freeze(spec,root,repo)
            self.assertEqual(value['batch_size'],dict(online=1,offline=4))
            self.assertEqual(value['selection']['seed'],20261017)
            self.assertIn('lexsort',value['ranking']['stable_sort'])
            self.assertIn('b-side/session_runner.py',value['source_files'])
            text=json.dumps(value)
            self.assertNotIn(str(root),text);self.assertNotIn(str(repo),text)
            self.assertEqual(f.bytes_sha(f.canonical(value['interface'])),value['interface_sha256'])

    def test_model_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'weights.bin').write_bytes(b'bad')
            spec=dict(model_id='model',revision='a'*40,dimension=768,required_files=[dict(path='weights.bin',bytes=3,algorithm='sha256',digest=f.bytes_sha(b'abc'))])
            with self.assertRaises(ValueError):f.freeze(spec,root,Path(__file__).resolve().parents[2])

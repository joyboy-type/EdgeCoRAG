import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_run_bundle as b

class BundleFreezeTests(unittest.TestCase):
    def prepare(self,root):
        repo=root/'repo';repo.mkdir();(repo/'entry.py').write_text('code')
        source=root/'prepared';source.mkdir()
        (source/'plan.private.json').write_text(json.dumps(dict(execution_authorized=False,source_pins={'entry.py':b.sha(repo/'entry.py')})))
        (source/'validation.json').write_text('{}')
        (source/'lease.proposed.json').write_text(json.dumps(dict(execution_authorized=False)))
        return repo,dict(dir=source,sources=('entry.py',),output='/data/new')

    def test_bundle_rebuild_is_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo,spec=self.prepare(root);hashes=[]
            for name in ('first','second'):
                out=root/name;out.mkdir()
                with patch.object(b,'REPO',repo),patch.object(b,'OUT',out),patch.object(b,'EXTRA',()):
                    hashes.append(b.build('run',spec)['sha256'])
                os.utime(repo/'entry.py',(1,1))
            self.assertEqual(hashes[0],hashes[1])

    def test_cannot_package_code_that_disagrees_with_plan_pins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo,spec=self.prepare(root);out=root/'out';out.mkdir()
            (repo/'entry.py').write_text('changed')
            with patch.object(b,'REPO',repo),patch.object(b,'OUT',out),patch.object(b,'EXTRA',()):
                with self.assertRaises(ValueError):b.build('run',spec)

class BundleVerificationTests(unittest.TestCase):
    def test_verifier_rejects_tampered_archive_identity(self):
        from verify_local_preparation import verify_bundle
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);helper=BundleFreezeTests();repo,spec=helper.prepare(root)
            out=root/'out';out.mkdir()
            with patch.object(b,'REPO',repo),patch.object(b,'OUT',out),patch.object(b,'EXTRA',()):
                result=b.build('run',spec)
            checked=verify_bundle(result)
            self.assertEqual(checked['sha256'],result['sha256'])
            result['sha256']='0'*64
            with self.assertRaises(ValueError):verify_bundle(result)

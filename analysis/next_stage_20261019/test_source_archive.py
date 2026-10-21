import hashlib
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from append_source_provenance import pin_rows

class SourceArchiveTests(unittest.TestCase):
    def test_historical_pin_is_reproduced_from_archive_not_current_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'b-side').mkdir();(root/'b-side/x.py').write_bytes(b'new code')
            path=root/'snapshot.tar.gz'
            with tarfile.open(path,'w:gz') as tar:
                info=tarfile.TarInfo('code/b-side/x.py');info.size=3;tar.addfile(info,io.BytesIO(b'old'))
            pin=hashlib.sha256(b'old').hexdigest()
            with tarfile.open(path) as tar:rows=pin_rows({'b-side/x.py':pin},root,tar)
            self.assertTrue(rows[0]['archive_matches_pin']);self.assertFalse(rows[0]['current_matches_pin'])
            with tarfile.open(path) as tar:
                with self.assertRaises(ValueError):pin_rows({'b-side/x.py':'0'*64},root,tar)

    def test_snapshot_columns_use_explicit_frozen_git_bytes(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'b-side').mkdir();(root/'b-side/x.py').write_bytes(b'current')
            path=root/'snapshot.tar.gz'
            with tarfile.open(path,'w:gz') as tar:
                info=tarfile.TarInfo('code/b-side/x.py');info.size=3;tar.addfile(info,io.BytesIO(b'old'))
            pin=hashlib.sha256(b'old').hexdigest()
            with tarfile.open(path) as tar,patch('append_source_provenance.subprocess.check_output',return_value=b'old') as call:
                rows=pin_rows({'b-side/x.py':pin},root,tar,source_snapshot='61fe155')
            self.assertTrue(rows[0]['current_matches_pin']);self.assertEqual((root/'b-side/x.py').read_bytes(),b'current')
            self.assertIn('61fe155:b-side/x.py',call.call_args.args[0])

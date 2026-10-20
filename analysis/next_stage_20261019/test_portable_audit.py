"""Reproduce: $PY -m unittest discover -s analysis/next_stage_20261019 -p test_portable_audit.py"""
import tempfile
import unittest
from pathlib import Path
from audit_requirement_evidence import expand_command

class PortableAuditTests(unittest.TestCase):
    def test_no_layout_or_environment_fallback(self):
        with self.assertRaisesRegex(ValueError, '--work-dir'):
            expand_command(['script.py', '--work-dir', '{work_dir}'], {})

    def test_explicit_root_must_exist(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'does not exist'):
                expand_command(['script.py', '{work_dir}'], {'work_dir': Path(d)/'absent'})

    def test_existing_explicit_root_is_expanded(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(expand_command(['script.py', '{work_dir}'], {'work_dir': Path(d)}), ['script.py', str(Path(d).resolve())])

    def test_absolute_registered_command_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'absolute'):
            expand_command(['script.py', '--input', '/private/tmp/cache'], {})

    def test_unknown_placeholder_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'placeholder'):
            expand_command(['script.py', '{unknown}'], {})

    def test_official_source_requires_file_not_directory(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'file'):
                expand_command(['script.py', '{official_source}'], {'official_source': Path(d)})

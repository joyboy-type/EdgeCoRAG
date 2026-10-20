import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('audit',REPO/'a-side/scripts/audit_before_push.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class AuditTests(unittest.TestCase):
    def test_git_reads_unicode_paths_without_machine_specific_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            subprocess.run(['git','init','-q',tmp],check=True)
            (root/'中文.md').write_text('safe')
            subprocess.run(['git','add','.'],cwd=root,check=True)
            self.assertIn('中文.md',audit.git('ls-files','-z',cwd=root).split('\0'))

    def test_failed_git_command_cannot_look_like_empty_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(subprocess.CalledProcessError):
                audit.git('ls-files',cwd=Path(tmp))

class AnalysisCliTests(unittest.TestCase):
    def test_all_analysis_help_is_safe_without_private_inputs(self):
        import sys
        for path in sorted(Path(__file__).parent.glob('*.py')):
            if path.name.startswith('test_') or path.stem=='analysis_paths': continue
            with self.subTest(script=path.name):
                result=subprocess.run([sys.executable,str(path),'--help'],cwd='/tmp',capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn('usage:',result.stdout)

import csv
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_requirement_evidence as a

class EvidenceAuditTests(unittest.TestCase):
    def fixture(self,tmp,status='部分完成',evidence='artifact.json',limit='部分完成 + 待GPU复验'):
        root=Path(tmp);(root/'reports/v1.10.1').mkdir(parents=True)
        row=['R01','source','requirement',status,evidence,limit]
        (root/'reports/Requirements.md').write_text('| id | source | requirement | status | evidence | limit |\n|---|---|---|---|---|---|\n| '+' | '.join(row)+' |\n')
        with (root/'reports/v1.10.1/requirements_matrix.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['id','source','requirement','status','evidence','limit_or_next_action']);writer.writerow(row)
        return root

    def test_missing_evidence_cannot_be_reported_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=a.audit(self.fixture(tmp,status='已完成',limit='scope'))
            self.assertEqual(result['status'],'failed');self.assertTrue(result['errors'])

    def test_partial_records_blocker_and_does_not_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=a.audit(self.fixture(tmp))
            self.assertEqual(result['status'],'passed');self.assertEqual(result['completion']['部分']['ids'],['R01'])
            self.assertEqual(result['rows'][0]['missing_evidence'],['artifact.json'])

    def test_markdown_and_csv_must_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.fixture(tmp);(root/'artifact.json').write_text('{}')
            p=root/'reports/Requirements.md';p.write_text(p.read_text().replace('部分完成 + 待GPU复验','另一个限制'))
            self.assertEqual(a.audit(root)['status'],'failed')

    def test_group_reads_status_only_even_if_limit_says_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.fixture(tmp,status='已完成',limit='部分完成 + 阻塞原因：本行测试忽略limit')
            (root/'artifact.json').write_text('{}')
            self.assertEqual(a.audit(root)['completion']['完成']['ids'],['R01'])

    def test_status_special_cases_and_qualified_delivery(self):
        from report_completion_counts import bucket
        self.assertEqual(bucket('已执行'),'完成')
        self.assertEqual(bucket('未测或不适用本轮'),'后置')
        self.assertEqual(bucket('已交付 部分核验'),'完成')

    def test_completed_evidence_without_reproduction_command_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.fixture(tmp,status='已完成',limit='historic scope');(root/'artifact.json').write_text('{}')
            result=a.audit(root)
            self.assertEqual(result['status'],'failed')
            self.assertTrue(any('reproduction' in error.lower() for error in result['errors']))

from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from export_official import project_rows
from verify_official_export import check_rows

class OfficialExportTests(unittest.TestCase):
    def test_official_order_missing_padding_and_failure_preserved_without_reparse(self):
        official=[dict(qid='q2',id='2',answer_choice='A',scenario='Angle',choices={'A':'x','B':'y'}),dict(qid='q1',id='1',answer_choice='B',scenario='Angle',choices={'A':'x','B':'y'})]
        source={'q1':dict(qid='q1',raw_id='1',answer='B',scenario='Angle',raw_output='A or B?',parse_status='parse_failure',parsed_choice=None,generation_error=None,split='dev')}
        rows=project_rows(official,source,{'q1':'saved prompt'})
        self.assertEqual([r['qid'] for r in rows],['q2','q1'])
        self.assertEqual(rows[0]['parse_status'],'missing_prediction')
        self.assertEqual(rows[1]['output'],'A or B?')
        self.assertIn('option_count',rows[1])
        self.assertEqual(rows[1]['option_count'],2)
        self.assertEqual(rows[1]['choices'],{'A':'x','B':'y'})
        self.assertEqual(rows[1]['parse_status'],'parse_failure')
        check_rows(rows,official,source,{'q1':'saved prompt'})
        rows[1]['output']='B'
        with self.assertRaises(ValueError):check_rows(rows,official,source,{'q1':'saved prompt'})

    def test_official_source_is_inspected_without_execution(self):
        from verify_official_schema import required_fields
        source='raise RuntimeError("must not execute")\nx=item["gt_choice"]\ny=item["output"]\nz=item["prompt"]\nw=item["scenario"]\n'
        self.assertEqual(required_fields(source),{'gt_choice','output','prompt','scenario'})

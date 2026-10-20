import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from quality_data import unique
from quality_closure import concept_rows

class QualityClosureTests(unittest.TestCase):
    def test_duplicate_archive_id_is_rejected(self):
        with self.assertRaises(ValueError):unique([{'qid':'q'},{'qid':'q'}],lambda r:r['qid'])

    def test_mapping_does_not_invent_ocr_chart_membership(self):
        rows=concept_rows()
        self.assertEqual(len(rows),9)
        self.assertTrue(all(row['needs_manual_review'] for row in rows))
        self.assertFalse(any(row['concept'] in ('OCR','图表') for row in rows))

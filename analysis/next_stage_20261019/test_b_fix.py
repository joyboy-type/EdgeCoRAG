"""Reproduce: $PY -m unittest discover -s analysis/next_stage_20261019 -p test_b_fix.py"""
import json
import tempfile
import unittest
from pathlib import Path
from a_interface_budget import build, REPO
from fetch_official_source import check_bytes, fetch

class BFixTests(unittest.TestCase):
    def test_reduced_scope_fits_hard_window_without_frozen_selection(self):
        with tempfile.TemporaryDirectory() as d:
            result=build(REPO,Path(d))
            self.assertLessEqual(result['worst_scenario_seconds'],7200)
            self.assertTrue(result['proposed_window_within_existing_runner_limit'])
            self.assertEqual(result['E5_generation_requests'],80)
            self.assertEqual(result['E5_frozen_requests'],0)
            self.assertFalse(result['E5_selection_performed'])
            self.assertTrue(result['nonmeasured_assumptions'])
            self.assertTrue(result['cannot_apply_for_GPU_now'])
            self.assertIn('fp32',result['prerequisite'])
            self.assertEqual(result['preservation_seconds'],600)

    def test_tampered_source_is_never_accepted(self):
        with self.assertRaises(ValueError):check_bytes(b'not the pinned score.py')

    def test_existing_cache_is_never_overwritten_or_executed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'score.py';p.write_bytes(b'bad')
            with self.assertRaises(ValueError):fetch(p)
            self.assertEqual(p.read_bytes(),b'bad')

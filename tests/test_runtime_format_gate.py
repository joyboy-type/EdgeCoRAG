"""Synthetic regressions for technical completion versus strict answer scoring."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

CODE = Path(__file__).resolve().parents[1]/'b-side'
sys.path.insert(0,str(CODE))
import run_batch as runner
from validate_batch_logic import fixture
from model_adapters import FixedBackend


class FormatGateTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        self.data,self.bundle,*_=fixture(self.root)
        self.model=runner.read(runner.REGISTRY)['models']['qwen3vl_4b']
        self.task={'task_id':'format-regression','model':'qwen3vl_4b','model_revision':self.model['revision'],
                   'environment':self.model['environment'],'condition':'S1','stage':'mechanism_test',
                   'repeat_index':0,'split':self.bundle['split'],'bundle':'fixture/bundle.json',
                   'bundle_sha256':runner.sha(self.data/'bundle.json'),
                   'split_manifest_sha256':self.bundle['split_manifest']['sha256'],
                   'protocol_version':self.bundle['protocol_version'],'evidence_version':self.bundle['evidence_version']}
        self.run=self.root/'run'
        self.calls=[]

    def format_backend(self):
        calls=self.calls
        class Backend(FixedBackend):
            def infer(self,row,base):
                calls.append(row['qid'])
                value=super().infer(row,base)
                output='B' if row['qid'].endswith('_x') else 'The image suggests option B, followed by an explanation.'
                value.update(raw_output=output,prediction_raw=output,final_output=output)
                return value
        return Backend(self.model)

    def test_format_failure_counts_wrong_in_full_denominator_and_completes_technically(self):
        _,oom,okay=runner.run_task(self.task,self.model,self.data.parent,self.run,self.format_backend)
        state=runner.read(self.run/self.task['task_id']/'state.json')
        score=runner.read(self.run/self.task['task_id']/'score.json')
        self.assertFalse(oom)
        self.assertTrue(okay,'Normal generation with invalid answer format must not block technical completion')
        self.assertEqual(state['exit_code'],0)
        self.assertEqual(state['failed_qids'],[])
        self.assertEqual(state['format_failure_qids'],['mragb:artificial_y'])
        self.assertEqual(score['overall']['total'],2)
        self.assertEqual(score['overall']['correct'],1)
        self.assertEqual(score['overall']['accuracy_percent'],50)
        self.assertEqual(score['overall']['status_counts']['parse_failure'],1)

    def test_explicit_retry_does_not_regenerate_format_failures(self):
        runner.run_task(self.task,self.model,self.data.parent,self.run,self.format_backend)
        before=(self.run/self.task['task_id']/'attempts.jsonl').read_bytes()
        runner.run_task(self.task,self.model,self.data.parent,self.run,self.format_backend,retry=True)
        self.assertEqual(len(self.calls),2,'Format noncompliance is a scored outcome, not a retry candidate')
        self.assertEqual((self.run/self.task['task_id']/'attempts.jsonl').read_bytes(),before)

    def test_generation_errors_still_block_and_keep_all_rows(self):
        class Broken(FixedBackend):
            def infer(self,row,base):raise RuntimeError('synthetic processor failure')
        _,oom,okay=runner.run_task(self.task,self.model,self.data.parent,self.run,lambda:Broken(self.model))
        state=runner.read(self.run/self.task['task_id']/'state.json')
        score=runner.read(self.run/self.task['task_id']/'score.json')
        self.assertFalse(oom)
        self.assertFalse(okay)
        self.assertEqual(state['exit_code'],2)
        self.assertEqual(len(state['failed_qids']),2)
        self.assertEqual(score['overall']['total'],2)
        self.assertEqual(score['overall']['status_counts']['generation_error'],2)

    def test_empty_normal_generation_is_wrong_without_becoming_a_retry(self):
        class Empty(FixedBackend):
            def infer(self,row,base):
                value=super().infer(row,base)
                value.update(raw_output='',prediction_raw='',final_output='')
                return value
        _,_,okay=runner.run_task(self.task,self.model,self.data.parent,self.run,lambda:Empty(self.model))
        score=runner.read(self.run/self.task['task_id']/'score.json')
        self.assertTrue(okay)
        self.assertEqual(score['overall']['correct'],0)
        self.assertEqual(score['overall']['status_counts']['empty_output'],2)

    def test_final_extraction_adapter_errors_remain_technical_failures(self):
        class ExtractError(FixedBackend):
            def infer(self,row,base):
                value=super().infer(row,base)
                value.update(final_output='',final_extraction_error='synthetic final-channel parser failure')
                return value
        _,_,okay=runner.run_task(self.task,self.model,self.data.parent,self.run,lambda:ExtractError(self.model))
        state=runner.read(self.run/self.task['task_id']/'state.json')
        self.assertFalse(okay)
        self.assertEqual(state['exit_code'],2)
        self.assertEqual(len(state['failed_qids']),2)


if __name__=='__main__':unittest.main()

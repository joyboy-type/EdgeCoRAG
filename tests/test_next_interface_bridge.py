"""Pure CPU/fake-backend contracts; no torch/model import or GPU work."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'b-side'))
import next_interface_bridge as b

class BridgeTests(unittest.TestCase):
    def fake_torch(self):
        return SimpleNamespace(float32='float32',backends=SimpleNamespace(cuda=SimpleNamespace(matmul=SimpleNamespace(allow_tf32=True)),cudnn=SimpleNamespace(allow_tf32=True)))

    def test_fp32_is_requested_and_bf16_model_is_not_relabelled(self):
        torch=self.fake_torch();captured={}
        def loader(path,**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(parameters=lambda:[SimpleNamespace(dtype='float32')])
        with tempfile.TemporaryDirectory() as tmp:
            b.build_fp32_encoder(Path(tmp),torch,loader,authorized=True)
            self.assertEqual(captured['model_kwargs']['torch_dtype'],'float32')
            self.assertFalse(torch.backends.cuda.matmul.allow_tf32);self.assertFalse(torch.backends.cudnn.allow_tf32)
            with self.assertRaises(ValueError):b.build_fp32_encoder(Path(tmp),torch,lambda *a,**k:SimpleNamespace(parameters=lambda:[SimpleNamespace(dtype='bfloat16')]),authorized=True)

    def test_default_never_loads_a_model(self):
        def forbidden(*a,**k):raise AssertionError('model loading forbidden')
        with self.assertRaises(ValueError):b.build_fp32_encoder(Path('/unused'),self.fake_torch(),forbidden)

    def test_pool_order_is_preserved_and_utility_returns_scores_only(self):
        pool={'qid':'q','corpus_ids':['z','a','b','c']}
        ids=b.consume_pool(pool,'q');self.assertEqual(ids,['z','a','b','c'])
        scores,seconds=b.utility_only(lambda q,ids:{x:1. for x in reversed(ids)},'q',ids,clock=iter([2.,5.]).__next__)
        self.assertEqual(seconds,3.);self.assertEqual(set(scores),set(ids))
        with self.assertRaises(ValueError):b.utility_only(lambda *a:dict(selected_ids=['z']),'q',ids)

    def test_a12_owns_outer_boundary_and_utility_is_separate(self):
        events=[]
        def outer(work):
            events.append('a12-start');value=work();events.append('a12-end')
            return dict(seconds=7.,result=value)
        result=b.run_with_outer_timer(outer,{'qid':'q','corpus_ids':['z','a','b','c']},'q','utility',
            lambda q,ids:{x:float(i) for i,x in enumerate(ids)},lambda ids:dict(generated_ids=ids),clock=iter([1.,3.]).__next__)
        self.assertEqual(events,['a12-start','a12-end']);self.assertEqual(result['outer_seconds'],7.)
        self.assertEqual(result['utility_seconds'],2.);self.assertEqual(result['pool_ids'],['z','a','b','c'])
        self.assertEqual(result['selected_ids'],['a','b','c'])

    def test_missing_measurements_cannot_pass_as_zero_or_null(self):
        for value in (None,0):
            with self.assertRaises(ValueError):b.observed_measurement(value,'device_wide_sampled_max')
        gap=b.historical_gap('rendered_prompt')
        self.assertNotIn('value',gap);self.assertEqual(gap['availability'],'不可回溯')
        with self.assertRaises(ValueError):b.require_observed(gap)

    def test_rendered_prompt_is_real_processor_return_not_reconstructed(self):
        seen={}
        class Processor:
            def apply_chat_template(self,messages,**kwargs):seen.update(kwargs);return '<rendered>'
        result=b.capture_rendered_prompt(Processor(),[{'role':'user','content':'x'}])
        self.assertFalse(seen['tokenize']);self.assertEqual(result['value'],'<rendered>')
        self.assertEqual(result['availability'],'observed')

    def test_dimensions_are_reported_without_selection(self):
        report=b.dimension_report({128:dict(rows=20),256:dict(rows=20),512:dict(rows=20),768:dict(rows=20)})
        self.assertFalse(report['selection_performed']);self.assertNotIn('selected_dimension',report)

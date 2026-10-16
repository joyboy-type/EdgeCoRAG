"""Narrow fail-stop regression with artificial IDs and injected OOM; no runtime imports."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import run_candidate as runner


def validate():
    original_config=copy.deepcopy(runner.CFG)
    original_run=subprocess.run
    evidence=[]
    cases=[('startup',0),('warmup',1),('S0',2),('S1',4),('S2',6)]
    for phase,fail_call in cases:
        calls=[]
        class FakeCuda:
            def __getattr__(self,name):
                return lambda *a: {'get_device_name':'INJECTED_TEST_ONLY',
                    'get_device_properties':SimpleNamespace(total_memory=0),
                    'get_device_capability':(0,0)}.get(name,0)
        class FakeBackend:
            synthetic=False
            def __init__(self,*args):
                if phase=='startup': raise RuntimeError('CUDA out of memory: injected startup')
                self.torch=SimpleNamespace(cuda=FakeCuda(),version=SimpleNamespace(cuda='INJECTED'))
                self.load_seconds=0;self.actual_dtype='INJECTED';self.processor_config={}
            def infer(self,row,root):
                calls.append((row['condition'],row['qid']))
                if len(calls)==fail_call:
                    raise RuntimeError('CUDA out of memory: injected '+phase)
                return {'raw_output':'A','final_output':'A'}
        def fake_run(cmd,*args,**kwargs):
            if cmd[0]=='nvidia-smi':return subprocess.CompletedProcess(cmd,0,'INJECTED_TEST_ONLY','')
            return original_run(cmd,*args,**kwargs)
        with tempfile.TemporaryDirectory(prefix='edgecorag-oom-test-') as temp:
            root=Path(temp);inputs=root/'inputs';inputs.mkdir();out=root/'output'
            # Artificial answer file is used only by the unchanged independent scorer.
            answers=root/'artificial_answers.json'
            answers.write_text(json.dumps([{'qid':'artificial:'+x,'answer_choice':'B','scenario':'artificial'} for x in ['x','y']]),encoding='utf-8')
            bundle_path=root/'bundle.json';bundle_path.write_text('{}',encoding='utf-8')
            manifests={c:[{'qid':'artificial:'+x,'raw_id':x,'condition':c,'evidence':[],
                'query_image':None,'protocol_version':runner.PROTOCOL,'template_version':runner.TEMPLATE_VERSION,
                'input_status':'ok'} for x in ['x','y']] for c in ['S0','S1','S2']}
            for c in manifests:(inputs/(c+'.json')).write_text('[]',encoding='utf-8')
            bundle={'answers_sha256':runner.digest(answers),'baseline_commit':'artificial',
                    'evidence_version':'artificial','dataset_revision':'artificial'}
            argv=['run_candidate.py','--sample-root',str(root),'--inputs-root',str(inputs),
                  '--bundle-manifest',str(bundle_path),'--answers',str(answers),'--output',str(out),'--backend','qwen']
            with patch.object(runner,'load_bundle',return_value=(bundle,manifests)), patch.object(runner,'QwenBackend',FakeBackend), \
                 patch.object(runner.subprocess,'run',side_effect=fake_run),patch.object(sys,'argv',argv),contextlib.redirect_stdout(io.StringIO()):
                try:runner.main()
                except SystemExit as e:assert e.code==2
                else:raise AssertionError('OOM must return nonzero')
            meta=runner.read(out/'run.json')
            assert meta['status']=='oom_stopped'
            assert meta['oom_origin']['phase']==('inference' if phase in ['S0','S1','S2'] else phase)
            assert len(calls)==fail_call, (phase,calls)
            expected=[('S0','artificial:x'),('S0','artificial:x'),('S0','artificial:y'),
                      ('S1','artificial:x'),('S1','artificial:y'),('S2','artificial:x')][:fail_call]
            assert calls==expected
            skipped=0;oom_rows=0
            for c in ['S0','S1','S2']:
                rows=[json.loads(s) for s in (out/c/'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
                assert [r['qid'] for r in rows]==['artificial:x','artificial:y']
                for r in rows:
                    assert r['prediction_raw']==r['raw_output']
                    assert r['parser_version']=='strict_choice_v1'
                    if r.get('execution_status')=='not_run_after_oom':
                        skipped+=1;assert r['generation_error'].startswith('NotRunAfterOOM:')
                    if r.get('oom'):oom_rows+=1;assert r['generation_error'] and r['error_traceback']
                score=runner.read(out/c/'score.json')
                assert score['overall']['total']==2
            assert skipped==(6 if phase in ['startup','warmup'] else 7-fail_call)
            assert oom_rows==(0 if phase in ['startup','warmup'] else 1)
            if phase=='startup':assert (out/'startup_error.json').exists()
            if phase=='warmup':assert runner.read(out/'warmup.json')['records'][0]['oom']
            assert runner.CFG==original_config, 'No automatic budget/config changes'
            evidence.append({'injection_phase':phase,'infer_calls_including_warmup':len(calls),
                             'not_run_after_oom':skipped,'exit_code':2,'status':meta['status']})
    assert runner.is_oom_error(type('OutOfMemoryError',(RuntimeError,),{})('allocator exhausted'))
    assert not runner.is_oom_error(RuntimeError('ordinary decoding error'))
    assert not any(x in sys.modules for x in ['torch','transformers'])
    return {'test':'injected_oom_fail_stop_only','synthetic_test':True,'real_inference':False,
            'gpu_tested':False,'configuration_unchanged':True,'cases':evidence}

if __name__=='__main__':
    print(json.dumps(validate(),indent=2))

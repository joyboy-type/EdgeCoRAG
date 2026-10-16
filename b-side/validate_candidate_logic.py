"""One bounded check of the new adapter/writer; no model or inference dependency imports."""
import argparse
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

import run_candidate as candidate

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sample-root',type=Path,required=True)
    p.add_argument('--inputs-root',type=Path,required=True)
    args=p.parse_args()
    base=args.sample_root.resolve()
    rows=candidate.validate_inputs(args.inputs_root/'S1.json',base,'S1')
    sentinels=[]
    def loader(path):
        obj=object();sentinels.append(obj);return obj
    messages=candidate.build_messages(rows[0],base,loader)
    assert [x['image'] for x in messages[0]['content'][:-1]]==sentinels
    assert len(sentinels)==6
    assert set(messages[0])=={'role','content'}
    assert all(set(x)=={'type','image'} for x in messages[0]['content'][:-1])
    class FailingBackend:
        synthetic=True
        def infer(self,row,root): raise RuntimeError('Artificial adapter error')
    failed=candidate.prediction_for(rows[0],base,FailingBackend())
    assert failed['generation_error']=='RuntimeError: Artificial adapter error'
    assert failed['raw_output']=='' and failed['parsed_choice'] is None
    assert failed['parse_status']=='generation_error'
    original_argv=sys.argv[:]
    original_backend=candidate.QwenBackend
    def startup_failure(*args,**kwargs): raise RuntimeError('Artificial startup error')
    try:
        with tempfile.TemporaryDirectory(prefix='candidate_logic_') as temp:
            temp=Path(temp)
            for backend in ['synthetic','qwen']:
                output=temp/backend
                command=['run_candidate.py','--sample-root',str(base),'--inputs-root',str(args.inputs_root),
                         '--answers',str(base/'scoring/answers.json'),'--output',str(output),'--backend',backend]
                sys.argv=command
                if backend=='qwen': candidate.QwenBackend=startup_failure
                with contextlib.redirect_stdout(io.StringIO()):
                    try:
                        candidate.main()
                        assert backend=='synthetic'
                    except SystemExit as exc:
                        assert backend=='qwen' and exc.code==2
                record=json.loads((output/'run.json').read_text(encoding='utf-8'))
                assert record['weights_loaded'] is False
                for condition in ['S0','S1','S2']:
                    predictions=[json.loads(x) for x in (output/condition/'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
                    score=json.loads((output/condition/'score.json').read_text(encoding='utf-8'))
                    assert [x['qid'] for x in predictions]==['0','43']
                    assert score['synthetic']==(backend=='synthetic')
                    assert score['overall']['coverage_percent']==100
                    if backend=='synthetic':
                        assert all(x['raw_output']=='A' and x['synthetic'] for x in predictions)
                    else:
                        assert score['overall']['status_counts']['generation_error']==2
                        assert record['status']=='startup_failed'
                # Same directory must be rejected before touching any existing result.
                before=(output/'run.json').read_bytes()
                try:
                    candidate.main();raise AssertionError('Expected overwrite refusal')
                except ValueError as exc: assert 'Output exists' in str(exc)
                assert (output/'run.json').read_bytes()==before
    finally:
        sys.argv=original_argv;candidate.QwenBackend=original_backend
    assert 'torch' not in sys.modules and 'transformers' not in sys.modules
    print('PASS: new adapter image order, neutral message boundary, synthetic writer/scorer, injected per-question/startup errors and overwrite refusal. No torch/transformers imported.')

if __name__=='__main__': main()

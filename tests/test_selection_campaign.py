import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'b-side'),str(REPO/'a-side/scripts')]
try:
    import selection_campaign as sc
except ImportError:
    sc=None

class CampaignContracts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(sc,'selection_campaign not implemented')
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        from unittest.mock import patch
        claims_patch=patch.object(sc,'CLAIMS_ROOT',self.root/'fixed-claims',create=True)
        claims_patch.start();self.addCleanup(claims_patch.stop)
        from PIL import Image
        Image.new('RGB',(1,1)).save(self.root/'image',format='PNG')
        ref={'path':'image','sha256':hashlib.sha256((self.root/'image').read_bytes()).hexdigest(),'size':[1,1]}
        self.package={'status':'prepared_unexecuted','execution_authorized':False,
            'queries':[{'qid':'q','split':'dev','question':'Which?','choices':dict(A='a',B='b',C='c',D='d'),'query_image':ref}],
            'corpus':{f'c{i}':dict(ref) for i in range(10)},'retrieval_package_sha256':'a'*64}
        self.ranks=[{'qid':'q','corpus_ids':[f'c{i}' for i in range(10)]}]

    def test_prepare_all_three_strategies_with_bound_scores_without_model(self):
        score={'pool_sha256':sc.pool_digest(self.ranks),'input_package_sha256':sc.pool_digest(self.package),
               'score_type':'first_step_raw_true_logit','model_id':'google/gemma-4-E2B-it',
               'revision':'3e22461f65e89153144f8adb70e3b8c2cc9845a7',
               'scores':[{'qid':'q','candidate_id':f'c{i}','raw_true_logit':float(i)} for i in range(10)]}
        out=self.root/'selected'
        receipt=sc.prepare_selection(self.package,self.ranks,score,out,self.root)
        self.assertEqual(receipt['rows'],3)
        rows=[json.loads(x) for x in (out/'inputs.jsonl').read_text().splitlines()]
        self.assertEqual(rows[-1]['selected_ids'],['c7','c8','c9'])
        with self.assertRaises(ValueError): sc.prepare_selection(self.package,self.ranks,score,out,self.root)
        score['pool_sha256']='wrong'
        with self.assertRaises(ValueError): sc.prepare_selection(self.package,self.ranks,score,self.root/'bad',self.root)
        self.assertFalse((self.root/'bad').exists())

    def test_reject_reordered_queries_missing_ranks_or_unknown_candidates(self):
        for ranks in [[],[{'qid':'other','corpus_ids':[f'c{i}' for i in range(10)]}],
                      [{'qid':'q','corpus_ids':['unknown']+[f'c{i}' for i in range(9)]}]]:
            with self.assertRaises(ValueError): sc.validate_ranks(self.package,ranks)

    def test_path_and_hash_tamper_rejected(self):
        sc.validate_inputs(self.package,self.root)
        bad=copy.deepcopy(self.package)
        bad['queries'][0]['query_image']['path']='../outside'
        with self.assertRaises(ValueError): sc.validate_inputs(bad,self.root)
        (self.root/'image').write_bytes(b'changed')
        with self.assertRaises(ValueError): sc.validate_inputs(self.package,self.root)

    def test_duplicate_score_and_wrong_input_manifest_rejected(self):
        base={'pool_sha256':sc.pool_digest(self.ranks),'input_package_sha256':sc.pool_digest(self.package),
              'score_type':'first_step_raw_true_logit','model_id':'google/gemma-4-E2B-it',
              'revision':'3e22461f65e89153144f8adb70e3b8c2cc9845a7',
              'scores':[{'qid':'q','candidate_id':f'c{i}','raw_true_logit':float(i)} for i in range(10)]}
        for score in [{**base,'scores':base['scores']+[base['scores'][0]]},{**base,'input_package_sha256':'bad'},
                      {**base,'revision':'main'}]:
            with self.assertRaises(ValueError): sc.validate_scores(self.package,self.ranks,score)

    def test_cli_default_validates_but_execute_without_auth_has_no_outputs(self):
        p=self.root/'package.json';p.write_text(json.dumps(self.package))
        command=[sys.executable,str(REPO/'b-side/selection_campaign.py'),'--package',str(p),'--root',str(self.root)]
        r=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertFalse(json.loads(r.stdout)['model_loaded'])
        r=subprocess.run(command+['--execute','--mode','utility','--output',str(self.root/'run')],capture_output=True,text=True)
        self.assertEqual(r.returncode,2,r.stderr)
        self.assertFalse((self.root/'run').exists())

    def test_decode_and_actual_dimensions_checked_before_loading(self):
        bad=copy.deepcopy(self.package)
        bad['queries'][0]['query_image']['size']=[2,2]
        with self.assertRaises(ValueError):sc.validate_inputs(bad,self.root)
        (self.root/'image').write_bytes(b'bad-image')
        for ref in [bad['queries'][0]['query_image'],*bad['corpus'].values()]:
            ref['sha256']=hashlib.sha256(b'bad-image').hexdigest()
        with self.assertRaises(ValueError):sc.validate_inputs(bad,self.root)

    def test_atomic_authorization_claim_cannot_be_reused_at_new_output(self):
        auth={'lease_id':'new-lease','mode':'generate','model_key':'gemma4_e2b',
              'input_package_sha256':'a'*64,'rankings_sha256':'b'*64,'output_path':str(self.root/'run1'),
              'data_root':str(self.root.resolve())}
        sc.consume_authorization(auth,self.root,self.root/'run1')
        auth['output_path']=str(self.root/'run2')
        with self.assertRaises(ValueError):sc.consume_authorization(auth,self.root,self.root/'run2')

    def test_authorization_claim_does_not_move_with_data_root(self):
        auth={'lease_id':'same-lease','mode':'utility','model_key':'gemma4_e2b',
              'input_package_sha256':'a'*64,'rankings_sha256':'b'*64,'output_path':str(self.root/'run1'),
              'data_root':str(self.root.resolve())}
        sc.consume_authorization(auth,self.root,self.root/'run1')
        other=self.root/'different-data-root';other.mkdir()
        auth.update(output_path=str(other/'run2'),data_root=str(other.resolve()))
        with self.assertRaises(ValueError):sc.consume_authorization(auth,other,other/'run2')

    def real_scores(self):
        return {'pool_sha256':sc.pool_digest(self.ranks),'input_package_sha256':sc.pool_digest(self.package),
                'score_type':'first_step_raw_true_logit','model_id':sc.SURROGATE[0],'revision':sc.SURROGATE[1],
                'synthetic':False,'scores':[{'qid':'q','candidate_id':f'c{i}','raw_true_logit':float(i)} for i in range(10)]}

    def test_synthetic_or_unmarked_utility_cannot_enter_real_execution(self):
        for marker in [True,None]:
            scores={**self.real_scores(),'synthetic':marker}
            with self.assertRaises(ValueError):sc.require_real_scores(scores)

    def test_cleanup_error_preserves_failed_receipt_and_partial_outputs(self):
        import time
        from unittest.mock import patch
        self.package['execution_authorized']=True
        scores=self.real_scores()
        out=self.root/'run'
        auth={'execution_authorized':True,'protocol_approved':True,'shutdown_verified':True,
              'max_rate_cny_hour':2.18,'quoted_rate_cny_hour':2.18,'max_incremental_cny':3,
              'incurred_cny':0,'storage_reserve_cny':0.5,'deadline_epoch':time.time()+1800,
              'charge_start_epoch':time.time(),'lease_id':'new-lease','mode':'generate','model_key':'gemma4_e2b',
              'input_package_sha256':sc.pool_digest(self.package),'rankings_sha256':sc.pool_digest(self.ranks),
              'utility_scores_sha256':sc.pool_digest(scores),'output_path':str(out),'data_root':str(self.root.resolve())}
        path=self.root/'auth.json';path.write_text(json.dumps(auth))
        class Backend:
            runtime={'synthetic_test_backend':True}
            def __init__(self,*args,**kwargs):pass
            def infer(self,row,root):return {'raw_output':'A','synthetic':True}
            def close(self):raise RuntimeError('cleanup failed')
        with patch('model_adapters.HFBackend',Backend):
            with self.assertRaises(RuntimeError):
                sc.execute(self.package,self.root,self.ranks,scores,out,'generate','gemma4_e2b',path)
        receipt=json.loads((out/'receipt.json').read_text())
        self.assertEqual(receipt['status'],'failed_cleanup_no_retry')
        self.assertEqual(receipt['completed_rows'],3)
        self.assertEqual(len((out/'predictions.jsonl').read_text().splitlines()),3)

if __name__=='__main__':unittest.main()

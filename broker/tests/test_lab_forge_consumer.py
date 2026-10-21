"""Offline handback consumption, real Lab locks, durable ownership and no false fulfillment."""

# Legacy phase regressions; chained autonomous turns have their own isolated suite.
import sys as _legacy_sys, types as _legacy_types
_legacy_sys.modules["lab_investigations"] = _legacy_types.SimpleNamespace(turn=lambda *a, **k: None)
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_lab_query_perimeter import C,Perimeter,forbidden,NET
import copy,fcntl,json,types,unittest
from unittest.mock import patch,Mock
import lab_forge_consumer as F
from lab_sources import receipt,Sources
from forge_genomic_result import verified_result
from forge_lab_handback import ownership,collect,pointer

class Consumer(unittest.TestCase):
    def setUp(self):
        Perimeter.setUp(self)
        self.ledger=str(Path(C.ROOT)/'forge-capability-handbacks.json')
        self.outbox=str(Path(C.ROOT)/'forge-report-outbox.json')
        self.question='Fetch human SLC26A19 sequence and inspect the original requested evidence.'
        request={'plugin':'genomic_intelligence','tool':'genomic_intelligence.fetch_ensembl_sequence',
                 'arguments':{'gene':'SLC26A19','species':'human'},'purpose':'fixture exact target'}
        raw={'ref':'seq_fixture','name':'untrusted display name','length':1000}
        outcome={'ok':True,'summary':json.dumps(raw),'receipt':{'receipt_id':F.digest(raw),
            'result_sha256':F.digest(raw),'surface':'forge','plugin':request['plugin'],
            'tool':request['tool'],'arguments_sha256':F.digest(request['arguments'])}}
        self.cycle='a'*32
        self.row={'project_id':'b'*32,'cycle_id':self.cycle,'outbox_key':'owned','original_request':self.question,
          'original_request_fulfilled':False,'state':F.PENDING,'sequence_handle':verified_result(outcome,request),
          'accepted_receipt':{'cycle_id':self.cycle,'charged_cents':0},
          'artifact':{'capability_resolution':{'request':request,'result':outcome},'lab_handback':{
              'cycle_id':self.cycle,'original_request':self.question,
              'status':'capability_available_original_request_unfulfilled'}}}
        C._atomic(self.ledger,{self.cycle:self.row})
        C._atomic(self.outbox,{'owned':{'project_id':self.row['project_id'],'state':'accepted','question':self.question}})
        self.row['ownership_sha256']=ownership(C._load(self.outbox,{})['owned'])
        self.row['verification']={'state':'pending','ownership_sha256':self.row['ownership_sha256'],
                                  'evidence_receipt_ids':[],'original_request_fulfilled':False}
        C._atomic(self.ledger,{self.cycle:self.row})
        self.verify=Mock(side_effect=lambda symbol:receipt('ncbi_gene_identity',{'symbol':symbol,'taxon_id':9606},
            [{'gene_id':'123','symbol':symbol,'taxon_id':9606,'aliases':[]}],metadata={'status':'verified'}))
        self.assertTrue(str(self.ledger).startswith(C.WS))

    def test_verified_target_is_not_verified_handle_or_completed_task(self):
        got=F.consume_one(C,verify=self.verify)
        self.assertEqual(got['target_identity_status'],'verified')
        self.assertEqual(got['sequence_identity_status'],'unverified')
        self.assertFalse(got['original_request_fulfilled'])
        self.assertEqual(got['original_request'],self.question)
        self.assertIsNone(F.consume_one(C,verify=self.verify));self.verify.assert_called_once_with('SLC26A19')
        row=C._load(self.ledger,{})[self.cycle]
        self.assertFalse(row['acknowledgement']['original_request_fulfilled'])
        self.assertEqual(pointer(row),C._load(self.outbox,{})['owned']['capability_handback'])

    def test_real_source_adapter_empty_identity_is_honest_and_not_repeated(self):
        fetch=Mock(return_value=({'esearchresult':{'idlist':[]}},{}))
        got=F.consume_one(C,verify=Sources(fetch=fetch).human_gene_identity)
        self.assertEqual(got['target_identity_status'],'unresolved');self.assertFalse(got['original_request_fulfilled'])
        F.consume_one(C,verify=Sources(fetch=fetch).human_gene_identity);fetch.assert_called_once()
        self.assertIn('SLC26A19',fetch.call_args.args[0])

    def test_source_work_occurs_without_lab_lock_and_changed_request_cannot_receive_result(self):
        def race(symbol):
            with open(C.LOCK,'a+') as stream:
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            owners=C._load(self.outbox,{})
            owners['owned']['question']='A changed request for another target'
            C._atomic(self.outbox,owners)
            return self.verify(symbol)
        got=F.consume_one(C,verify=race)
        self.assertEqual(got['kind'],'forge_handback_stale')
        self.assertNotIn('acknowledgement',C._load(self.ledger,{})[self.cycle])
        self.assertFalse(Path(C.ROOT,'source-receipts.jsonl').exists())

    def test_forged_receipt_is_not_queried(self):
        row=copy.deepcopy(self.row)
        row['artifact']['capability_resolution']['result']['receipt']['arguments_sha256']='0'*64
        C._atomic(self.ledger,{self.cycle:row})
        got=F.consume_one(C,verify=self.verify)
        self.assertEqual(got['target_identity_status'],'verification_failed');self.verify.assert_not_called()
        self.assertFalse(got['original_request_fulfilled'])

    def test_changed_artifact_cannot_receive_stale_verification(self):
        def race(symbol):
            rows=C._load(self.ledger,{})
            rows[self.cycle]['sequence_handle']['ref']='seq_changed'
            C._atomic(self.ledger,rows)
            return self.verify(symbol)
        got=F.consume_one(C,verify=race)
        self.assertEqual(got['kind'],'forge_handback_stale')
        self.assertNotIn('acknowledgement',C._load(self.ledger,{})[self.cycle])

    def test_disabled_reads_and_unsupported_species_do_not_query(self):
        with patch.object(C,'config',return_value=dict(C.DEFAULTS,enabled=True,allow_public_database_reads=False)):
            self.assertIsNone(F.consume_one(C,verify=self.verify))
        self.verify.assert_not_called()
        row=copy.deepcopy(self.row);owner=C._load(self.outbox,{})
        owner['owned']['question']=self.question.replace('human','mouse')
        row['original_request']=owner['owned']['question']
        row['artifact']['lab_handback']['original_request']=row['original_request']
        request=row['artifact']['capability_resolution']['request'];request['arguments']['species']='mouse'
        outcome=row['artifact']['capability_resolution']['result']
        outcome['receipt']['arguments_sha256']=F.digest(request['arguments'])
        row['sequence_handle']=verified_result(outcome,request)
        row['ownership_sha256']=ownership(owner['owned'])
        C._atomic(self.outbox,owner);C._atomic(self.ledger,{self.cycle:row})
        got=F.consume_one(C,verify=self.verify)
        self.assertEqual(got['target_identity_status'],'unsupported_verification');self.verify.assert_not_called()

    def test_different_gene_receipt_is_not_accepted(self):
        wrong=receipt('ncbi_gene_identity',{'symbol':'SLC26A4','taxon_id':9606},[],metadata={'status':'unresolved'})
        got=F.consume_one(C,verify=lambda _:wrong)
        self.assertEqual(got['target_identity_status'],'verification_failed')
        self.assertFalse(Path(C.ROOT,'source-receipts.jsonl').exists())

    def test_missing_ownership_and_interrupted_claim_never_replay(self):
        C._atomic(self.outbox,{})
        self.assertIsNone(F.consume_one(C,verify=self.verify));self.verify.assert_not_called()
        C._atomic(self.outbox,{'owned':{'project_id':self.row['project_id'],'state':'accepted','question':self.question}})
        row=copy.deepcopy(self.row);row['verification']={'state':'processing'};row['state']='verification_in_progress'
        C._atomic(self.ledger,{self.cycle:row})
        self.assertIsNone(F.consume_one(C,verify=self.verify));self.verify.assert_not_called()

    def test_projection_repair_does_not_repeat_verification_or_receipt(self):
        F.consume_one(C,verify=self.verify)
        rows=C._load(self.ledger,{});rows[self.cycle]['verification'].pop('receipt_published')
        C._atomic(self.ledger,rows)
        owners=C._load(self.outbox,{});owners['owned'].pop('capability_handback');C._atomic(self.outbox,owners)
        self.assertIsNone(F.consume_one(C,verify=self.verify));self.verify.assert_called_once()
        self.assertEqual(len(C._tail_jsonl(str(Path(C.ROOT)/'source-receipts.jsonl'))),1)
        self.assertEqual(C._load(self.outbox,{})['owned']['capability_handback'],pointer(rows[self.cycle]))

    def test_two_distinct_cycles_progress_without_repeating_first(self):
        second=copy.deepcopy(self.row);cycle='c'*32
        second.update(cycle_id=cycle,project_id='d'*32,outbox_key='second')
        second['accepted_receipt']['cycle_id']=cycle;second['artifact']['lab_handback']['cycle_id']=cycle
        C._atomic(self.ledger,{self.cycle:self.row,cycle:second})
        owners=C._load(self.outbox,{});owners['second']={**owners['owned'],'project_id':second['project_id']};C._atomic(self.outbox,owners)
        second['ownership_sha256']=ownership(owners['second'])
        C._atomic(self.ledger,{self.cycle:self.row,cycle:second})
        self.assertEqual(F.consume_one(C,verify=self.verify)['cycle_id'],self.cycle)
        self.assertEqual(F.consume_one(C,verify=self.verify)['cycle_id'],cycle)
        self.assertIsNone(F.consume_one(C,verify=self.verify));self.assertEqual(self.verify.call_count,2)

    def test_real_collector_consumer_collector_keeps_partial_ack_and_never_reacquires(self):
        C._atomic(self.ledger,{})
        fetch=Mock(return_value=[{'id':self.cycle,'state':'accepted','artifact':json.dumps(self.row['artifact']),
                                 'receipt':json.dumps(self.row['accepted_receipt'])}])
        projects=[{'id':self.row['project_id'],'state':'awaiting_lab'}]
        def pull():return collect({},C.ROOT,projects,load=C._load,atomic=C._atomic,locked=C._locked,fetch=fetch)
        self.assertEqual(len(pull()),1)
        self.assertEqual(F.consume_one(C,verify=self.verify)['target_identity_status'],'verified')
        expected=C._load(self.outbox,{})['owned']['capability_handback']
        self.assertEqual(expected['state'],'partial');self.assertFalse(expected['original_request_fulfilled'])
        self.assertEqual(pull(),[])
        self.assertEqual(C._load(self.outbox,{})['owned']['capability_handback'],expected)
        self.assertIsNone(F.consume_one(C,verify=self.verify))
        fetch.assert_called_once();self.verify.assert_called_once()

    def test_real_tick_consumes_one_checkpoint_without_model_or_connector(self):
        cfg=dict(C.DEFAULTS,enabled=True,evo2_enabled=False,forge_report_intake={'url':'http://127.0.0.1:8612/api/lab-intake'})
        fake=types.SimpleNamespace(flush_reports=Mock())
        with patch.object(C,'config',return_value=cfg),patch.dict(sys.modules,{'chemistry_sources':fake}), \
             patch.object(Sources,'human_gene_identity',side_effect=self.verify), \
             patch.object(C,'lab_context',side_effect=forbidden),patch.object(C,'_ask',side_effect=forbidden):
            got=C.tick()
        self.assertEqual(got['kind'],'forge_handback_verification')
        self.assertEqual(C._load(C.STATE,{})['turns'],1)
        self.assertEqual(C._load(C.STATE,{})['phase'],'orient')
        self.assertEqual(NET,[])

if __name__=='__main__':unittest.main()

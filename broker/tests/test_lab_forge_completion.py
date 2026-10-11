"""Real source adapter -> Lab consumer -> authenticated Forge API, entirely offline."""
import contextlib,copy,fcntl,json,sys,types,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_forge_verification_ack as fixture
import lab_forge_consumer as F
import lab_gene_locus as G
from lab_sources import receipt

class Completion(fixture.Tests):
    def setUp(self):
        super().setUp()
        self.save('forge-capability-handbacks.json',{self.cid:copy.deepcopy(self.row)})
        (self.lab/'source-receipts.jsonl').write_text('')
        @contextlib.contextmanager
        def locked():
            with (self.lab/'.lock').open('a+') as stream:
                fcntl.flock(stream,fcntl.LOCK_EX);yield
        def append(path,value):
            with Path(path).open('a') as stream:stream.write(json.dumps(value)+'\n')
        self.ctx=types.SimpleNamespace(ROOT=self.lab,config=lambda:{'enabled':True,'allow_public_database_reads':True},
              stop_requested=lambda:False,_locked=locked,_load=self.load_path,
              _atomic=lambda path,value:Path(path).write_text(json.dumps(value)),now_iso=lambda:'2026-10-11T12:00:00Z',
              _append=append,_tail_jsonl=lambda path,**kw:[json.loads(s) for s in Path(path).read_text().splitlines()] if Path(path).exists() else [])
        self.fetch=Mock(side_effect=self.public_fixture)
        self.locus=lambda row,args:G.lookup(row,args,fetch=self.fetch)
        def ack(cfg,body):
            status,result=self.call('/api/lab-verification',body)
            self.assertEqual(status,200)
            return result
        self.deliver=Mock(side_effect=ack)
    def public_fixture(self,url):
        if '/info/data?' in url:return {'releases':[999]},{}
        if '/xrefs/symbol/homo_sapiens/TP53?' in url:return [{'id':'ENSG00000000001','type':'gene'}],{}
        if '/lookup/id/ENSG00000000001?' in url:return {'id':'ENSG00000000001','object_type':'Gene',
            'species':'homo_sapiens','display_name':'TP53','assembly_name':'fixtureRef','seq_region_name':'1','start':10,'end':20},{}
        raise AssertionError('unexpected offline URL '+url)
    def test_producer_api_completion_then_next_owned_cycle_without_repeated_lookup(self):
        budget=self.c.step_budget(self.c.owner_token);artifacts=self.c.artifacts(self.c.owner_token,self.pid)
        got=F.consume_one(self.ctx,locus=self.locus,acknowledge=self.deliver)
        self.assertTrue(got['original_request_fulfilled']);self.assert_held()
        self.assertEqual(F.consume_one(self.ctx,locus=self.locus,acknowledge=self.deliver)['kind'],'forge_verification_acknowledged')
        self.assertEqual(self.c.status(self.c.owner_token,self.pid)['state'],'complete')
        self.assertEqual(self.c.step_budget(self.c.owner_token),budget);self.assertEqual(self.c.artifacts(self.c.owner_token,self.pid),artifacts)
        self.assertIsNone(F.consume_one(self.ctx,locus=self.locus,acknowledge=self.deliver));self.assertEqual(self.fetch.call_count,4)
        # Lost delivery response retries only the immutable acknowledgement; server proves idempotence.
        rows=self.load('forge-capability-handbacks.json');rows[self.cid]['acknowledgement'].update(state='sending',next_attempt=0)
        self.save('forge-capability-handbacks.json',rows)
        F.consume_one(self.ctx,locus=self.locus,acknowledge=self.deliver)
        self.assertEqual(self.fetch.call_count,4)
        with self.c.db() as db:self.assertEqual(db.execute("SELECT count(*) FROM events WHERE kind='verification'").fetchone()[0],1)
        # A second real intake/project/collector cycle advances and completes independently.
        source=receipt('fixture',{'next':True},[{'fixture':'second source'}])
        status,created=self.call('/api/lab-intake',{'intent':self.original,
            'source_packet':{'kind':'lab_research_report','source_receipts':[source]}})
        self.assertEqual(status,200);pid=created['id'];self.assertNotEqual(pid,self.pid)
        self.r.step(pid)
        owners=self.load('forge-report-outbox.json');owners['second']={'state':'accepted','project_id':pid,
            'question':self.original,'receipt_ids':[source['receipt_id']]};self.save('forge-report-outbox.json',owners)
        from forge_lab_handback import collect
        next_rows=collect({},self.lab,self.c.projects(self.c.owner_token),load=self.load_path,
            atomic=self.ctx._atomic,locked=self.ctx._locked,fetch=lambda cfg,p:self.c.artifacts(self.c.owner_token,p))
        cid=next_rows[0]['cycle_id']
        self.assertEqual(F.consume_one(self.ctx,locus=self.locus,acknowledge=self.deliver)['cycle_id'],cid)
        self.assertEqual(self.fetch.call_count,8)
        F.consume_one(self.ctx,locus=self.locus,acknowledge=self.deliver)
        self.assertEqual(self.c.status(self.c.owner_token,pid)['state'],'complete')
    def test_adapter_scoped_absence_completes_only_named_reference_lookup(self):
        self.acquisition.assert_not_called();self.model.assert_not_called()
        self.assertIsNone(self.row["sequence_handle"])
        resolution=self.row["artifact"]["capability_resolution"]
        self.assertEqual(resolution["route"],"direct_authoritative_verification")
        self.assertNotIn("result",resolution)
        self.assertNotIn("seq_",json.dumps(resolution))
        self.fetch.side_effect=lambda url:({'releases':[999]}, {}) if '/info/data?' in url else ([],{})
        got=F.consume_one(self.ctx,locus=self.locus);self.assertEqual(got['target_identity_status'],'verified_absent')
        F.consume_one(self.ctx,acknowledge=self.deliver)
        result=self.c.status(self.c.owner_token,self.pid)['lab_verification']
        self.assertEqual(result['evidence'][0]['matches'],[]);self.assertEqual(self.fetch.call_count,3)
    def test_single_base_inclusive_locus_passes_producer_and_forge_ack(self):
        def single(url):
            value,meta=self.public_fixture(url)
            if '/lookup/id/' in url:value['end']=value['start']
            return value,meta
        self.fetch.side_effect=single
        got=F.consume_one(self.ctx,locus=self.locus)
        self.assertTrue(got['original_request_fulfilled'])
        self.assertEqual(F.consume_one(self.ctx,acknowledge=self.deliver)['kind'],'forge_verification_acknowledged')
        saved=self.c.status(self.c.owner_token,self.pid)['lab_verification']['evidence'][0]['matches'][0]
        self.assertEqual(saved['start'],saved['end'])
    def test_empty_half_open_interval_refused_by_both_sides(self):
        from forge_verification_ack import validate_evidence,Refused
        body,row,owner,receipts=self.provider_fixture('ensembl',9606,'verified_present')
        value=next(iter(receipts.values()))
        match=value['records']['matches'][0]
        match.update(coordinate_system='0-based-half-open',end=match['start'])
        value['response_sha256']=F.digest(value['records'])
        value.pop('receipt_id');value['receipt_id']=F.digest(value)
        body['evidence_receipt_ids']=[value['receipt_id']]
        row['verification']['evidence_receipt_ids']=body['evidence_receipt_ids']
        with self.assertRaises(ValueError):G.check(value,row,{'gene':'TP53','species':'human'})
        with self.assertRaises(Refused):validate_evidence(body,row,owner,{value['receipt_id']:value})
    def test_direct_lookup_provider_error_and_ambiguity_remain_unfulfilled(self):
        def ambiguous(url):
            if '/info/data?' in url:return {'releases':[999]},{}
            return [{'id':'ENSG00000000001','type':'gene'},{'id':'ENSG00000000002','type':'gene'}],{}
        self.fetch.side_effect=ambiguous
        got=F.consume_one(self.ctx,locus=self.locus)
        self.assertFalse(got['original_request_fulfilled']);self.assert_held()
        self.deliver.assert_not_called()
        self.assertIsNone(F.consume_one(self.ctx,locus=self.locus,acknowledge=self.deliver))
    def test_direct_lookup_http_error_is_not_absence(self):
        self.fetch.side_effect=OSError('offline fixture provider unavailable')
        got=F.consume_one(self.ctx,locus=self.locus)
        self.assertFalse(got['original_request_fulfilled']);self.assert_held()
        self.deliver.assert_not_called()

    def test_scope_mismatch_negative_and_alias_do_not_create_fulfillment(self):
        args={'gene':'TP53','species':'mouse'};row=copy.deepcopy(self.row)
        data=dict(action='verify_gene_locus',requested_target='TP53',taxon_id=10090,query_completed=True,
                  reference={'provider':'hgnc','release':'fixture'},verdict='not_found_in_reference',matches=[])
        value=receipt('gene_locus_verification',G.query_for(row,args),data)
        with self.assertRaises(ValueError):G.check(value,row,args)
        def wrong(url):
            value,meta=self.public_fixture(url)
            if '/lookup/id/' in url:value['display_name']='TP531'
            return value,meta
        self.fetch.side_effect=wrong
        got=F.consume_one(self.ctx,locus=self.locus);self.assertFalse(got['original_request_fulfilled']);self.assert_held()
        self.assertIsNone(F.consume_one(self.ctx,locus=self.locus));self.assertEqual(self.fetch.call_count,3)
    def test_broad_original_remains_pending_without_locus_completion(self):
        original=self.original+' and determine its topology and function'
        rows=self.load('forge-capability-handbacks.json');row=rows[self.cid]
        owners=self.load('forge-report-outbox.json');owners['owned']['question']=original
        from forge_lab_handback import ownership
        row.update(original_request=original,ownership_sha256=ownership(owners['owned']))
        row['artifact']['lab_handback']['original_request']=original
        self.save('forge-report-outbox.json',owners);self.save('forge-capability-handbacks.json',rows)
        verify=Mock(return_value=receipt('ncbi_gene_identity',{'symbol':'TP53','taxon_id':9606},[],metadata={'status':'unresolved'}))
        got=F.consume_one(self.ctx,verify=verify,locus=self.locus)
        self.assertFalse(got['original_request_fulfilled']);self.fetch.assert_not_called();self.assert_held()
        self.assertIsNone(F.consume_one(self.ctx,verify=verify,locus=self.locus));verify.assert_not_called()

# Inherited endpoint tests require their original fully populated canonical fixture.
for name in list(fixture.Tests.__dict__):
    if name.startswith('test_'):setattr(Completion,name,None)
if __name__=='__main__':unittest.main()

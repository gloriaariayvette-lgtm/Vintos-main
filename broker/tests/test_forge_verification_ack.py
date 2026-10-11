"""Real intake -> partial handback -> canonical fixture verification -> authenticated ack; no network."""
import contextlib
import copy
import fcntl
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
from forge_loop import Controller
from forge_loop_runtime import Runtime,ReportBuilder,API
from forge_lab_handback import collect
from forge_verification_ack import CanonicalLabEvidence,digest,request_digest

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.lab=self.root/"lab";self.lab.mkdir()
        (self.lab/".lock").touch()
        for name in ("socket.socket.connect","urllib.request.urlopen"):
            guard=patch(name,side_effect=AssertionError("network forbidden"));guard.start();self.addCleanup(guard.stop)
        guard=patch("forge_loop.software_quota.limit",return_value=20);guard.start();self.addCleanup(guard.stop)
        self.c=Controller(self.root/"forge.sqlite","o"*40,"w"*40,"https://fixture.invalid")
        self.q={"plugin":"genomic_intelligence","tool":"genomic_intelligence.fetch_ensembl_sequence",
                "arguments":{"gene":"TP53","species":"human"},"purpose":"Verify exact original target"}
        self.acquisition=Mock(side_effect=AssertionError("exact lookup must not acquire a sequence"))
        self.model=Mock(side_effect=AssertionError("exact lookup must not invoke a model"))
        builder=ReportBuilder(self.model,plugin_call=self.acquisition)
        builder._menu=lambda:"fixture"
        self.r=Runtime(self.c,Mock(),builder,intake_token="i"*40,verification_evidence=CanonicalLabEvidence(self.lab))
        self.api=API(self.r)
        records=[{"fixture":"source"}]
        source={"source":"fixture","records":records,"response_sha256":digest(records)}
        source["receipt_id"]=digest(source)
        self.original="The Lab needs an instrument it does not have: verify human TP53 exists"
        status,created=self.call("/api/lab-intake",{"intent":self.original,
             "source_packet":{"kind":"lab_research_report","source_receipts":[source]}})
        self.assertEqual(status,200);self.pid=created["id"]
        self.r.step(self.pid)
        self.assertEqual(self.c.status(self.c.owner_token,self.pid)["state"],"awaiting_lab")
        self.save("forge-report-outbox.json",{"owned":{"state":"accepted","project_id":self.pid,
                  "question":self.original,"receipt_ids":[source["receipt_id"]]}})
        @contextlib.contextmanager
        def locked():
            with (self.lab/".lock").open("a+") as stream:
                fcntl.flock(stream,fcntl.LOCK_EX);yield
        collected=collect({},self.lab,self.c.projects(self.c.owner_token),load=self.load_path,
             atomic=lambda path,value:Path(path).write_text(json.dumps(value)),locked=locked,
             fetch=lambda cfg,pid:self.c.artifacts(self.c.owner_token,pid))
        self.row=collected[0];self.cid=self.row["cycle_id"]
        self.body={"project_id":self.pid,"cycle_id":self.cid,"ownership_sha256":self.row["ownership_sha256"],
                   "original_request_sha256":request_digest(self.original),"evidence_receipt_ids":[],"verdict":"verified_present"}
        self.records={"action":"verify_gene_locus","requested_target":"TP53","taxon_id":9606,"query_completed":True,
                      "reference":{"provider":"ensembl","release":"fixture-only"},
                      "verdict":"present","matches":[{"symbol":"TP53","taxon_id":9606,"gene_id":"ENSG00000000001",
                      "assembly":"fixtureRef","chromosome":"1","coordinate_system":"1-based-inclusive","start":10,"end":20}]}
        self.persist_evidence()
    def load_path(self,path,default):return json.loads(Path(path).read_text()) if Path(path).exists() else default
    def load(self,name):return self.load_path(self.lab/name,{})
    def save(self,name,value):(self.lab/name).write_text(json.dumps(value))
    def call(self,path,body,token="i"*40,method="POST"):
        encoded=json.dumps(body).encode();statuses=[]
        env={"PATH_INFO":path,"REQUEST_METHOD":method,"CONTENT_LENGTH":str(len(encoded)),
             "wsgi.input":io.BytesIO(encoded),"HTTP_AUTHORIZATION":"Bearer "+token if token else ""}
        response=b"".join(self.api(env,lambda status,headers:statuses.append(status)))
        return int(statuses[0].split()[0]),json.loads(response)
    def ack(self,body=None,token="i"*40):return self.call("/api/lab-verification",body or self.body,token)
    def persist_evidence(self,*,records=None,query_change=None):
        query={key:self.body[key] for key in ("project_id","cycle_id","ownership_sha256","original_request_sha256")}
        query.update(action="verify_gene_locus",target="TP53",species="human",taxon_id=9606)
        if query_change:query.update(query_change)
        evidence={"source":"gene_locus_verification","query":query,"records":copy.deepcopy(records or self.records),
                  "retrieved_at":"2026-10-11T12:00:00Z","metadata":{"fixture":True}}
        evidence["response_sha256"]=digest(evidence["records"]);evidence["receipt_id"]=digest(evidence)
        self.body["evidence_receipt_ids"]=[evidence["receipt_id"]]
        (self.lab/"source-receipts.jsonl").write_text(json.dumps(evidence)+"\n")
        rows=self.load("forge-capability-handbacks.json")
        rows[self.cid]["verification"]={"state":self.body["verdict"],"ownership_sha256":self.body["ownership_sha256"],
             "original_request_fulfilled":True,"evidence_receipt_ids":self.body["evidence_receipt_ids"]}
        self.save("forge-capability-handbacks.json",rows)
        return evidence
    def assert_held(self):
        self.assertEqual(self.c.status(self.c.owner_token,self.pid)["state"],"awaiting_lab")
    def provider_fixture(self, provider, taxon, verdict):
        from forge_verification_ack import ownership
        species="human" if taxon==9606 else "mouse"
        row=copy.deepcopy(self.load("forge-capability-handbacks.json")[self.cid])
        current=copy.deepcopy(self.load("forge-report-outbox.json")["owned"])
        current["question"]=self.original.replace("human",species)
        row["original_request"]=current["question"]
        row["ownership_sha256"]=ownership(current)
        row["artifact"]["lab_handback"]["original_request"]=current["question"]
        row["artifact"]["capability_resolution"]["request"]["arguments"]["species"]=species
        body={**self.body,"verdict":verdict,"ownership_sha256":row["ownership_sha256"],
              "original_request_sha256":request_digest(current["question"])}
        records=copy.deepcopy(self.records)
        records["taxon_id"]=taxon;records["reference"]["provider"]=provider
        if verdict=="verified_absent":records.update(verdict="not_found_in_reference",matches=[])
        else:records["matches"][0]["taxon_id"]=taxon
        query={key:body[key] for key in ("project_id","cycle_id","ownership_sha256","original_request_sha256")}
        query.update(action="verify_gene_locus",target="TP53",species=species,taxon_id=taxon)
        receipt={"source":"gene_locus_verification","query":query,"records":records,
                 "response_sha256":digest(records)}
        receipt["receipt_id"]=digest(receipt)
        body["evidence_receipt_ids"]=[receipt["receipt_id"]]
        row["verification"]={"state":verdict,"ownership_sha256":body["ownership_sha256"],
            "original_request_fulfilled":True,"evidence_receipt_ids":body["evidence_receipt_ids"]}
        return body,row,current,{receipt["receipt_id"]:receipt}
    def test_provider_taxon_scope_applies_to_presence_and_echoed_negative(self):
        from forge_verification_ack import validate_evidence,Refused
        for provider,taxon in (("hgnc",10090),("unknown",9606),("unknown",10090)):
            for verdict in ("verified_present","verified_absent"):
                with self.subTest(provider=provider,taxon=taxon,verdict=verdict):
                    args=self.provider_fixture(provider,taxon,verdict)
                    with self.assertRaisesRegex(Refused,"reference for the requested taxon"):
                        validate_evidence(*args)
    def test_supported_provider_taxon_pairs_accept_complete_fixture_evidence(self):
        from forge_verification_ack import validate_evidence
        for provider,taxon in (("hgnc",9606),("ensembl",9606),("ensembl",10090),
                               ("ncbi_gene",9606),("ncbi_gene",10090)):
            for verdict in ("verified_present","verified_absent"):
                with self.subTest(provider=provider,taxon=taxon,verdict=verdict):
                    proof=validate_evidence(*self.provider_fixture(provider,taxon,verdict))
                    self.assertEqual(proof["verdict"],verdict)
    def test_hgnc_human_presence_through_authenticated_endpoint(self):
        data=copy.deepcopy(self.records);data["reference"]["provider"]="hgnc"
        self.persist_evidence(records=data)
        self.assertEqual(self.ack()[0],200)
    def test_hgnc_human_scoped_absence_through_authenticated_endpoint(self):
        self.body["verdict"]="verified_absent"
        data=copy.deepcopy(self.records);data["reference"]["provider"]="hgnc"
        data.update(verdict="not_found_in_reference",matches=[])
        self.persist_evidence(records=data)
        self.assertEqual(self.ack()[0],200)

    def test_direct_route_is_exact_and_cannot_claim_an_acquisition(self):
        from forge_genomic_result import existence_request,direct_verification
        resolution=self.row["artifact"]["capability_resolution"]
        self.assertTrue(direct_verification(resolution,self.original))
        self.assertFalse(direct_verification(dict(resolution,result={"ok":True}),self.original))
        self.assertFalse(direct_verification(dict(resolution,sequence_handle={"ref":"seq_fake"}),self.original))
        for text in (self.original+" and build an assay",self.original.replace("human","rat"),
                     self.original.replace("TP53","TP53, TP54")):
            self.assertIsNone(existence_request(text))
        for text in ("verify TP53 in human exists","verify that mouse Trp53 locus",
                     "verify Homo sapiens TP53 existence"):
            self.assertIsNotNone(existence_request(text))

    def test_broader_original_action_cannot_be_completed_by_identity_lookup(self):
        from forge_verification_ack import validate_evidence, ownership, request_digest, Refused
        rows=json.loads((self.lab/"forge-capability-handbacks.json").read_text())
        row=rows[self.body["cycle_id"]]
        outbox=json.loads((self.lab/"forge-report-outbox.json").read_text())
        current=outbox[row["outbox_key"]]
        current["question"] += " and build a validated assay"
        row["original_request"]=current["question"]
        row["ownership_sha256"]=ownership(current)
        row["verification"]["ownership_sha256"]=row["ownership_sha256"]
        row["artifact"]["lab_handback"]["original_request"]=row["original_request"]
        body={**self.body,"ownership_sha256":row["ownership_sha256"],
              "original_request_sha256":request_digest(row["original_request"])}
        with self.assertRaises(Refused):
            validate_evidence(body,row,current,{})

    def test_real_canonical_ack_completes_once_preserving_original_cycle_and_budget(self):
        artifacts=self.c.artifacts(self.c.owner_token,self.pid)
        budget=self.c.step_budget(self.c.owner_token)
        status,body=self.ack();self.assertEqual(status,200);self.assertFalse(body["replayed"])
        status,body=self.ack();self.assertEqual(status,200);self.assertTrue(body["replayed"])
        saved=self.c.status(self.c.owner_token,self.pid)
        self.assertEqual(saved["state"],"complete")
        self.assertEqual(saved["lab_verification"]["evidence"][0]["matches"][0]["symbol"],"TP53")
        self.assertEqual(self.c.artifacts(self.c.owner_token,self.pid),artifacts)
        self.assertEqual(self.c.step_budget(self.c.owner_token),budget)
        with self.c.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE kind='verification'").fetchone()[0],1)
    def test_no_auth_owner_worker_and_keyless_cannot_ack(self):
        for token in ("","bad","o"*40,"w"*40):
            self.assertEqual(self.ack(token=token)[0],403);self.assert_held()
    def test_inline_boolean_or_forged_receipt_is_rejected(self):
        self.assertEqual(self.ack(dict(self.body,original_request_fulfilled=True))[0],403)
        self.assertEqual(self.ack(dict(self.body,evidence_receipt_ids=["f"*64]))[0],403)
        self.assertEqual(self.ack(dict(self.body,evidence_receipt_ids=[{}]))[0],403)
        self.assert_held()
    def test_partial_canonical_result_cannot_ack(self):
        rows=self.load("forge-capability-handbacks.json")
        rows[self.cid]["verification"]["state"]="partial"
        self.save("forge-capability-handbacks.json",rows)
        self.assertEqual(self.ack()[0],403);self.assert_held()
    def test_exact_symbol_and_species_checks_reject_self_consistent_wrong_evidence(self):
        for mutate in ("symbol","species","identity_only"):
            data=copy.deepcopy(self.records)
            if mutate=="symbol":data["matches"][0]["symbol"]="TP531"
            elif mutate=="species":data["matches"][0]["taxon_id"]=10090
            else:data={"ref":"seq_fixture","name":"TP53 human","length":1000}
            self.persist_evidence(records=data)
            self.assertEqual(self.ack()[0],403);self.assert_held()
    def test_rehashed_evidence_for_other_cycle_is_rejected(self):
        self.persist_evidence(query_change={"cycle_id":"f"*32})
        self.assertEqual(self.ack()[0],403);self.assert_held()
    def test_post_collection_ownership_change_invalidates_pointer_and_ack(self):
        rows=self.load("forge-report-outbox.json")
        rows["owned"]["capability_handback"]={"cycle_id":self.cid,"state":"verified_present","original_request_fulfilled":True}
        for field,value in (("question","changed request"),("receipt_ids",["changed source"])):
            changed=copy.deepcopy(rows);changed["owned"][field]=value;self.save("forge-report-outbox.json",changed)
            self.assertEqual(self.ack()[0],403);self.assert_held()
            @contextlib.contextmanager
            def locked():
                with (self.lab/".lock").open("a+") as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX);yield
            collect({},self.lab,self.c.projects(self.c.owner_token),load=self.load_path,
                atomic=lambda path,value:Path(path).write_text(json.dumps(value)),locked=locked,
                fetch=Mock(side_effect=AssertionError("must not fetch")))
            self.assertNotIn("capability_handback",self.load("forge-report-outbox.json")["owned"])
            self.assertEqual(self.load("forge-capability-handbacks.json")[self.cid]["verification"]["state"],"verified_present")
    def test_tampered_canonical_receipt_hash_is_rejected(self):
        evidence=json.loads((self.lab/"source-receipts.jsonl").read_text())
        evidence["records"]["matches"][0]["start"]=999
        (self.lab/"source-receipts.jsonl").write_text(json.dumps(evidence)+"\n")
        self.assertEqual(self.ack()[0],403);self.assert_held()
    def test_disabled_reader_fails_closed(self):
        self.r.verification_evidence=None
        self.assertEqual(self.ack()[0],403);self.assert_held()
    def test_existing_lab_exclusive_lock_fails_closed_without_waiting(self):
        with (self.lab/".lock").open("r") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            self.assertEqual(self.ack()[0],403)
        self.assert_held()
    def test_symlink_evidence_is_not_followed(self):
        source=self.lab/"source-receipts.jsonl";elsewhere=self.root/"other.jsonl"
        source.rename(elsewhere);source.symlink_to(elsewhere)
        self.assertEqual(self.ack()[0],403);self.assert_held()
    def test_scoped_negative_lookup_can_answer_exists_without_fabricating_presence(self):
        self.body["verdict"]="verified_absent"
        data=copy.deepcopy(self.records);data.update(verdict="not_found_in_reference",matches=[])
        self.persist_evidence(records=data)
        self.assertEqual(self.ack()[0],200)
        result=self.c.status(self.c.owner_token,self.pid)["lab_verification"]
        self.assertEqual(result["verdict"],"verified_absent")
        self.assertEqual(result["evidence"][0]["matches"],[])
    def test_cancelled_project_and_untouched_uncertain_job_never_reopen(self):
        old=self.r.create(self.c.owner_token,{"intent":"old uncertain","kind":"research_report"})
        claim=self.c.claim(self.c.worker_token,old["id"],"research_report")
        self.c.uncertain(self.c.worker_token,old["id"],claim["cycle_id"])
        before=self.c.status(self.c.owner_token,old["id"])
        with self.c.db() as db:cancel=db.execute("SELECT cancel FROM controls WHERE project=?",(self.pid,)).fetchone()[0]
        self.c.cancel(self.pid,cancel)
        self.assertEqual(self.ack()[0],403)
        self.assertEqual(self.c.status(self.c.owner_token,self.pid)["state"],"cancelled")
        self.assertEqual(self.c.status(self.c.owner_token,old["id"]),before)
    def test_conflicting_second_ack_cannot_replace_recorded_fulfillment(self):
        self.assertEqual(self.ack()[0],200)
        first=self.c.status(self.c.owner_token,self.pid)["lab_verification"]
        data=copy.deepcopy(self.records);data["reference"]["release"]="fixture-new"
        self.persist_evidence(records=data)
        self.assertEqual(self.ack()[0],403)
        self.assertEqual(self.c.status(self.c.owner_token,self.pid)["lab_verification"],first)

if __name__=="__main__":unittest.main()

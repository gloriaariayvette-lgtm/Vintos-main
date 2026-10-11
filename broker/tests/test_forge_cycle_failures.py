"""Offline regression coverage: scratch stores, fake models, fake connector and publisher."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"scripts"))
from forge_loop import Controller, Refused
from forge_loop_runtime import Runtime, ReportBuilder
from forge_cycle_failure import ValidationFailure

FIELDS = ("title","sourced_observations","hypotheses","conflicting_evidence","limitations","next_tests")
def draft(): return dict.fromkeys(FIELDS, "fixture")
def critique(): return {"complete":True,"reasons":"fixture evidence","reveal":False}
def query(): return {"plugin":"genomic_intelligence","tool":"genomic_intelligence.fetch_ensembl_sequence",
                     "arguments":{"gene":"SLC26A19","species":"human"},"purpose":"Verify original identifier without guessing."}
def receipt(q, result=None):
    result = result if result is not None else {"ref":"seq_fixture","name":"SLC26A19 human fixture","length":1000}
    digest=hashlib.sha256(json.dumps(result,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return {"ok":True,"summary":json.dumps(result),
            "receipt":{"receipt_id":digest,"result_sha256":digest,"surface":"forge","plugin":q["plugin"],"tool":q["tool"],
                       "arguments_sha256":hashlib.sha256(json.dumps(q["arguments"],sort_keys=True).encode()).hexdigest()}}

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in ("socket.socket.connect","urllib.request.urlopen"):
            p=patch(name,side_effect=AssertionError("network forbidden"));p.start();self.addCleanup(p.stop)
        p=patch("forge_loop.software_quota.limit",return_value=3);p.start();self.addCleanup(p.stop)
        self.c=Controller(self.root/"forge.sqlite","o"*40,"w"*40,"https://fixture.invalid")
        self.projection=Mock();self.sent=[]
        self.r=Runtime(self.c,self.projection,Mock(),lambda payload:self.sent.append(payload) or True,
                       "test-topic",intake_token="i"*40)
    def project(self,kind="research_report"):
        return self.r.create(self.c.owner_token,{"intent":"fixture request","kind":kind})
    def builder(self,outputs,plugin=None):
        model=Mock(side_effect=outputs);model.model="fixture-local"
        builder=ReportBuilder(model,plugin_call=plugin or Mock(side_effect=AssertionError("unexpected connector")))
        builder._menu=lambda:"fixture installed genomic read tools"
        self.r.builder=builder
        return model
    def status(self,p): return self.c.status(self.c.owner_token,p["id"])
    def test_local_bad_sections_repair_then_completion_and_next_work(self):
        p=self.project()
        model=self.builder([{"title":"bad"},draft(),critique(),draft(),critique()])
        self.assertTrue(self.r.step(p["id"]))
        self.assertEqual(model.call_count,3)
        self.assertEqual(self.status(p)["state"],"complete")
        second=self.project();self.assertTrue(self.r.step(second["id"]))
        self.assertEqual(self.c.step_budget(self.c.owner_token)["used"],2)
    def test_malformed_query_stops_before_dispatch_and_deduplicates(self):
        p=self.project();plugin=Mock()
        self.builder([{"plugin_query":"secret-token"},{"plugin_query":{"tool":"bad"}}],plugin)
        with self.assertRaises(ValidationFailure):self.r.step(p["id"])
        status=self.status(p);self.assertEqual(status["state"],"failed")
        self.assertEqual(status["diagnostic"]["code"],"plugin_shape");plugin.assert_not_called()
        cid=status["diagnostic"]["cycle_id"]
        self.c.fail_cycle(self.c.worker_token,p["id"],cid,status["diagnostic"])
        self.r.dispatch();self.r.dispatch()
        self.assertEqual(len(self.sent),1);self.assertNotIn("secret-token",json.dumps(self.sent))
        self.assertEqual(self.c.step_budget(self.c.owner_token)["used"],1)
    def test_receipt_then_bad_final_is_failed_not_uncertain_or_replayed(self):
        p=self.project();plugin=Mock(return_value=receipt(query()))
        model=self.builder([{"plugin_query":query()},{"title":"invalid"}],plugin)
        with self.assertRaises(ValidationFailure):self.r.step(p["id"])
        self.assertEqual(self.status(p)["state"],"failed")
        self.assertEqual(self.status(p)["diagnostic"]["external"],"confirmed")
        self.assertEqual(plugin.call_count,1);self.assertEqual(model.call_count,2)
    def test_unknown_outcome_and_exception_secrets_never_replayed(self):
        for outcome in (TimeoutError("Bearer secret-token https://private/topic"), {"ok":True,"receipt":{}}):
            with self.subTest(outcome=type(outcome).__name__):
                p=self.project()
                plugin=Mock(side_effect=outcome) if isinstance(outcome,Exception) else Mock(return_value=outcome)
                self.builder([{"plugin_query":query()}],plugin)
                with self.assertRaises(Exception):self.r.step(p["id"])
                self.assertEqual(self.status(p)["state"],"reconciliation_required")
                self.assertFalse(self.r.step(p["id"]));self.assertEqual(plugin.call_count,1)
                self.r.dispatch();self.assertNotIn("secret-token",json.dumps(self.sent))
    def test_interrupts_propagate_and_legacy_unknown_remains_held(self):
        for exc in (KeyboardInterrupt(),SystemExit()):
            p=self.project();self.r.builder=Mock(side_effect=exc)
            with self.assertRaises(type(exc)):self.r.step(p["id"])
            self.assertEqual(self.status(p)["state"],"reconciliation_required")
        self.assertEqual(self.c.recover_interrupted(self.c.worker_token),0)
    def test_cancel_during_local_output_prevents_connector(self):
        p=self.project();plugin=Mock()
        def model(*args):
            self.c.cancel(p["id"],p["cancel_token"])
            return {"plugin_query":query()}
        b=ReportBuilder(model,plugin);b._menu=lambda:"fixture";self.r.builder=b
        with self.assertRaises(Refused):self.r.step(p["id"])
        plugin.assert_not_called();self.assertEqual(self.status(p)["state"],"cancelled")
    def test_new_capability_intake_uses_existing_route_and_next_work(self):
        records=[{"id":"source-fixture"}]
        item={"source":"fixture","records":records,
              "response_sha256":hashlib.sha256(json.dumps(records,sort_keys=True,allow_nan=False).encode()).hexdigest()}
        item["receipt_id"]=hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
        payload={"intent":"The Lab needs an instrument it does not have: genomic sequence database for human SLC26A19",
                 "source_packet":{"kind":"lab_research_report","source_receipts":[item]}}
        p=self.r.intake("i"*40,payload)
        self.assertEqual(self.c.context(self.c.worker_token,p["id"])["capabilities"],["capability_request"])
        plugin=Mock(return_value=receipt(query()))
        model=self.builder([{"plugin_query":query()},draft(),critique()],plugin)
        self.assertTrue(self.r.step(p["id"]))
        self.assertEqual(self.status(p)["state"],"awaiting_lab")
        self.assertFalse(self.status(p)["intake_slot"])
        artifact=json.loads(self.c.artifacts(self.c.owner_token,p["id"])[0]["artifact"])
        self.assertNotIn("report",artifact)
        self.assertEqual(artifact["capability_resolution"]["status"],"partial_acquisition_identity_unverified")
        self.assertEqual(artifact["lab_handback"]["status"],"capability_available_original_request_unfulfilled")
        plugin.assert_called_once_with(*query().values())
        second=self.project();self.assertTrue(self.r.step(second["id"]))
        self.assertEqual(self.status(second)["state"],"complete")
    def test_unsupported_capability_cannot_complete_with_prose(self):
        p=self.project("capability_request");model=self.builder([{"unsupported":True,"prose":"built it"}])
        with self.assertRaises(ValidationFailure):self.r.step(p["id"])
        self.assertEqual(model.call_count,1)
        self.assertEqual(self.status(p)["state"],"failed")
        self.assertEqual(self.status(p)["cycles"],0)
    def test_restart_uses_durable_pre_dispatch_checkpoint_not_old_uncertain(self):
        p=self.project();claim=self.c.claim(self.c.worker_token,p["id"],"research_report")
        self.c.checkpoint(self.c.worker_token,p["id"],claim["cycle_id"],{"phase":"response_validation","external":"none"})
        old=self.project();oldclaim=self.c.claim(self.c.worker_token,old["id"],"research_report")
        self.c.uncertain(self.c.worker_token,old["id"],oldclaim["cycle_id"])
        before=self.status(old)
        self.c.recover_interrupted(self.c.worker_token)
        self.assertEqual(self.status(p)["state"],"failed")
        self.assertEqual(self.status(old),before)
        self.assertEqual(self.c.step_budget(self.c.owner_token)["used"],2)
    def test_exhausted_local_repair_has_exact_missing_fields_and_next_project_runs(self):
        p=self.project();model=self.builder([{"title":"fixture"},{"title":"fixture"},draft(),critique()])
        with self.assertRaises(ValidationFailure):self.r.step(p["id"])
        self.assertIn("sourced_observations",self.status(p)["diagnostic"]["reason"])
        self.assertEqual(model.call_count,2)
        self.assertFalse(self.r.step(p["id"]))
        second=self.project();self.assertTrue(self.r.step(second["id"]))
        self.assertEqual(self.c.step_budget(self.c.owner_token)["used"],2)
    def test_local_configuration_error_does_not_dispatch_or_retry(self):
        p=self.project();plugin=Mock()
        model=self.builder([{"plugin_query":query()}],plugin)
        self.r.builder.plugin_preflight=Mock(side_effect=ValueError("secret credential path"))
        with self.assertRaises(ValidationFailure):self.r.step(p["id"])
        self.assertEqual(self.status(p)["diagnostic"]["code"],"gateway_configuration")
        self.assertEqual(self.status(p)["diagnostic"]["external"],"none")
        self.assertEqual(model.call_count,1);plugin.assert_not_called()
    def test_dispatch_checkpoint_is_persisted_before_call_and_interrupt_is_held(self):
        p=self.project()
        def dispatch(*args):
            with self.c.db() as db:
                data=json.loads(db.execute("SELECT body FROM cycle_checkpoints").fetchone()[0])
            self.assertEqual(data["phase"],"connector_dispatch")
            self.assertEqual(data["external"],"unknown")
            raise KeyboardInterrupt()
        self.builder([{"plugin_query":query()}],dispatch)
        with self.assertRaises(KeyboardInterrupt):self.r.step(p["id"])
        self.assertEqual(self.status(p)["state"],"reconciliation_required")
    def test_unknown_valueerror_from_uninstrumented_adapter_is_not_safe_retry(self):
        p=self.project();self.r.builder=Mock(side_effect=ValueError("secret arbitrary failure"))
        with self.assertRaises(ValueError):self.r.step(p["id"])
        self.assertEqual(self.status(p)["state"],"reconciliation_required")
        self.assertEqual(self.r.builder.call_count,1)
        self.assertNotIn("secret",json.dumps(self.status(p)))
    def test_private_diagnostics_and_alerts_remain_hidden(self):
        import time
        p=self.r.create(self.c.owner_token,{"intent":"sealed fixture", "private":True,"private_until":time.time()+600})
        self.builder([{"plugin_query":None},{"plugin_query":None}])
        with self.assertRaises(ValidationFailure):self.r.step(p["id"])
        self.assertIsNone(self.status(p)["diagnostic"])
        self.r.dispatch();self.assertFalse(self.sent)

    def test_malformed_local_json_gets_one_repair_and_preserves_only_digest(self):
        from contextlib import nullcontext
        from forge_loop_runtime import LocalModel
        p=self.project()
        values=iter(["secret malformed JSON",json.dumps(draft()),json.dumps(critique())])
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,size):return json.dumps({"choices":[{"message":{"content":next(values)}}]}).encode()
        transport=Mock(side_effect=lambda *a,**k:Response())
        model=LocalModel("http://127.0.0.1:1234/v1/chat/completions","fixture",transport=transport,admission=nullcontext)
        b=ReportBuilder(model,Mock());b._menu=lambda:"fixture";self.r.builder=b
        self.assertTrue(self.r.step(p["id"]))
        self.assertEqual(transport.call_count,3)
        with self.c.db() as db:
            diagnostic=db.execute("SELECT body FROM cycle_checkpoints").fetchone()[0]
        self.assertIn("response_sha256",diagnostic);self.assertNotIn("secret malformed",diagnostic)

    def test_capability_route_cannot_dispatch_paid_or_consequential_tool(self):
        p=self.project("capability_request");plugin=Mock()
        q={"plugin":"nvidia_nim","tool":"nvidia_nim.boltz2","arguments":{},"purpose":"fixture"}
        model=self.builder([{"plugin_query":q}],plugin)
        with self.assertRaises(ValidationFailure):self.r.step(p["id"])
        plugin.assert_not_called();self.assertEqual(model.call_count,1)
        self.assertEqual(self.status(p)["diagnostic"]["code"],"capability_scope")

    def test_only_never_attempted_legacy_lab_route_is_corrected(self):
        body={"intent":"The Lab needs an instrument it does not have: genomic source lookup for human SLC26A19",
              "kind":"research_report","origin":{"source":"lab"}}
        queued=self.r.create(self.c.owner_token,body)
        old=self.r.create(self.c.owner_token,body)
        claim=self.c.claim(self.c.worker_token,old["id"],"research_report")
        self.c.uncertain(self.c.worker_token,old["id"],claim["cycle_id"])
        before=self.status(old)
        plugin=Mock(return_value=receipt(query()))
        self.builder([{"plugin_query":query()}],plugin)
        self.assertTrue(self.r.step(queued["id"]))
        self.assertEqual(self.c.context(self.c.worker_token,queued["id"])["capabilities"],["capability_request"])
        self.assertFalse(self.r.step(old["id"]))
        after=self.status(old);before.pop("day_steps");after.pop("day_steps")
        self.assertEqual(after,before)
        self.assertEqual(self.c.context(self.c.worker_token,old["id"])["capabilities"],["research_report"])
        self.assertEqual(plugin.call_count,1)

    def test_gene_finder_is_inference_and_not_an_allowed_lookup(self):
        p=self.project("capability_request");plugin=Mock()
        q=query();q["tool"]="genomic_intelligence.find_genes"
        self.builder([{"plugin_query":q}],plugin)
        with self.assertRaises(ValidationFailure):self.r.step(p["id"])
        plugin.assert_not_called()
        self.assertEqual(self.status(p)["diagnostic"]["code"],"capability_scope")
    def test_success_receipt_with_error_result_does_not_complete(self):
        p=self.r.create(self.c.owner_token,{"kind":"capability_request","intent":"Fetch human SLC26A19"})
        plugin=Mock(return_value=receipt(query(),{"error":"gene not found"}))
        self.builder([{"plugin_query":query()}],plugin)
        with self.assertRaises(ValidationFailure):self.r.step(p["id"])
        self.assertEqual(self.status(p)["cycles"],0)
        self.assertEqual(self.status(p)["state"],"failed")
        self.assertEqual(self.status(p)["diagnostic"]["external"],"confirmed")
        self.assertEqual(plugin.call_count,1)
    def test_genomic_schema_and_identifier_guard_precedes_dispatch(self):
        from forge_genomic_result import validate_request
        good=query();validate_request(good,{"intent":"Fetch human SLC26A19"})
        for q in (
            dict(good,arguments={"sequence":"ACTG"}),
            dict(good,arguments={"gene":"SLC26A9","species":"human"}),
            dict(good,arguments={"gene":"SLC26A19","species":"mouse"}),
            dict(good,arguments={"gene":"SLC26A19","species":"human","flank_bp":True}),
        ):
            with self.assertRaises(ValidationFailure):validate_request(q,{"intent":"Fetch human SLC26A19"})
    def test_verified_result_rejects_truncation_hash_mismatch_and_missing_handle(self):
        from forge_genomic_result import verified_result
        valid=receipt(query());self.assertEqual(verified_result(valid,query())["ref"],"seq_fixture")
        wrapped=receipt(query(),{"content":[{"type":"text","text":json.dumps({"ref":"seq_fixture","name":"SLC26A19","length":1000})}]})
        self.assertEqual(verified_result(wrapped,query())["length"],1000)
        for invalid in (
            dict(valid,summary="truncated ..."),
            dict(valid,summary=json.dumps({"ref":"seq_other","name":"SLC26A19","length":1000})),
            receipt(query(),{"message":"connected"}),
        ):
            with self.assertRaises(ValidationFailure):verified_result(invalid,query())

    def intake_payload(self, index=0):
        records=[{"id":"source-"+str(index)}]
        item={"source":"fixture","records":records,"response_sha256":hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()}
        item["receipt_id"]=hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
        return {"intent":"The Lab needs an instrument it does not have: acquire human SLC26A19 sequence",
                "source_packet":{"kind":"lab_research_report","source_receipts":[item]}}
    def test_real_intake_partial_result_is_handed_back_and_never_completes_request(self):
        from contextlib import nullcontext
        from forge_lab_handback import collect
        payload=self.intake_payload()
        p=self.r.intake("i"*40,payload)
        self.builder([{"plugin_query":query()}],Mock(return_value=receipt(query())))
        self.assertTrue(self.r.step(p["id"]))
        self.assertEqual(self.status(p)["state"],"awaiting_lab")
        self.assertFalse(self.r.step(p["id"]))
        outbox=self.root/"forge-report-outbox.json"
        outbox.write_text(json.dumps({"owned":{"state":"accepted","project_id":p["id"],"question":payload["intent"]}}))
        def load(path,default):return json.loads(Path(path).read_text()) if Path(path).exists() else default
        def atomic(path,value):Path(path).write_text(json.dumps(value))
        records=[];fetch=Mock(side_effect=lambda cfg,pid:self.c.artifacts(self.c.owner_token,pid))
        def pull():return collect({},self.root,self.c.projects(self.c.owner_token),load=load,atomic=atomic,
                                  locked=nullcontext,fetch=fetch,record=records.append)
        returned=pull();self.assertEqual(len(returned),1)
        self.assertEqual(returned[0]["original_request"],payload["intent"])
        self.assertFalse(returned[0]["original_request_fulfilled"])
        self.assertIn("accepted_receipt",returned[0])
        saved=json.loads(outbox.read_text());saved["owned"].pop("capability_handback")
        outbox.write_text(json.dumps(saved))  # simulate crash after ledger but before pointer
        self.assertEqual(pull(),[]);self.assertEqual(len(records),1)
        self.assertEqual(fetch.call_count,1)
        self.assertFalse(json.loads(outbox.read_text())["owned"]["capability_handback"]["original_request_fulfilled"])
        with self.c.db() as db:
            event=json.loads(db.execute("SELECT body FROM events WHERE project=? AND kind='cycle'",(p["id"],)).fetchone()[0])
        self.assertIs(event["complete"],False)
    def test_four_terminal_failures_release_capacity_but_keep_owned_evidence(self):
        projects=[]
        with patch("forge_loop.software_quota.limit",return_value=20):
            for index in range(4):
                p=self.r.intake("i"*40,self.intake_payload(index));projects.append(p)
                self.builder([{"unsupported":True}])
                with self.assertRaises(ValidationFailure):self.r.step(p["id"])
                self.assertEqual(self.status(p)["state"],"failed")
                self.assertFalse(self.status(p)["intake_slot"])
            fifth=self.r.intake("i"*40,self.intake_payload(4))
            self.assertEqual(self.status(fifth)["state"],"ready")
            self.assertEqual(self.c.step_budget(self.c.owner_token)["used"],4)
            for index,p in enumerate(projects):
                replay=self.r.intake("i"*40,self.intake_payload(index))
                self.assertEqual(replay["id"],p["id"]);self.assertTrue(replay["replayed"])
                self.assertEqual(len(self.c.artifacts(self.c.owner_token,p["id"])),1)
                self.assertIsNotNone(self.status(p)["diagnostic"])
    def test_uncertain_requests_still_occupy_capacity_without_replay(self):
        with patch("forge_loop.software_quota.limit",return_value=20):
            for index in range(4):
                p=self.r.intake("i"*40,self.intake_payload(index))
                self.r.builder=Mock(side_effect=TimeoutError("unknown"))
                with self.assertRaises(TimeoutError):self.r.step(p["id"])
                self.assertTrue(self.status(p)["intake_slot"])
            with self.assertRaises(Refused):self.r.intake("i"*40,self.intake_payload(4))
    def test_species_omission_and_fuzzy_result_names_cannot_fulfill(self):
        from forge_genomic_result import validate_request,verified_result
        q=query();q["arguments"]={"gene":"TP53"}
        with self.assertRaises(ValidationFailure):validate_request(q,{"intent":"Fetch mouse TP53 sequence"})
        q["arguments"]={"gene":"TP53","species":"human"}
        with self.assertRaises(ValidationFailure):validate_request(q,{"intent":"Fetch mouse TP53 sequence"})
        q["arguments"]={"gene":"TP53","species":"mouse"}
        validate_request(q,{"intent":"Fetch mouse TP53 sequence"})
        for name in ("TP531 human","TP53 human","TP53 mouse","unknown"):
            value=verified_result(receipt(q,{"ref":"seq_fixture","name":name,"length":1000}),q)
            self.assertEqual(value["identity_status"],"unverified")
            self.assertFalse(value["original_request_fulfilled"])
    def test_report_cannot_send_mail_or_run_hosted_inference(self):
        forbidden=[{"plugin":"gmail","tool":tool,"arguments":{},"purpose":"fixture"}
                   for tool in ("gmail.send_email","gmail.create_draft","gmail.forward_emails")]
        forbidden.append({"plugin":"nvidia_nim","tool":"nvidia_nim.boltz2","arguments":{},"purpose":"fixture"})
        with patch("forge_loop.software_quota.limit",return_value=20):
            for q in forbidden:
                p=self.project();plugin=Mock();model=self.builder([{"plugin_query":q}],plugin)
                with self.assertRaises(ValidationFailure):self.r.step(p["id"])
                plugin.assert_not_called();self.assertEqual(model.call_count,1)
                self.assertEqual(self.status(p)["diagnostic"]["code"],"report_effect_scope")
    def test_report_literature_read_remains_available(self):
        p=self.project();q={"plugin":"pubmed","tool":"get_article_metadata","arguments":{"pmids":["123"]},"purpose":"Read source evidence"}
        plugin=Mock(return_value=receipt(q,{"title":"fixture paper"}))
        self.builder([{"plugin_query":q},draft(),critique()],plugin)
        self.assertTrue(self.r.step(p["id"]));plugin.assert_called_once()
        self.assertEqual(self.status(p)["state"],"complete")

    def test_real_lab_collector_records_owned_partial_receipt_once(self):
        import importlib.util
        import types
        from contextlib import nullcontext
        from forge_lab_handback import collect
        payload=self.intake_payload();payload["intent"]="The Lab needs an instrument it does not have: verify human SLC26A19 exists"
        p=self.r.intake("i"*40,payload)
        self.builder([{"plugin_query":query()}],Mock(return_value=receipt(query())))
        self.r.step(p["id"])
        (self.root/"forge-report-outbox.json").write_text(json.dumps({"owned":{"state":"accepted","project_id":p["id"],"question":payload["intent"]}}))
        def load(path,default):return json.loads(Path(path).read_text()) if Path(path).exists() else default
        def atomic(path,value):Path(path).write_text(json.dumps(value))
        def tail(path,**kwargs):return [json.loads(line) for line in Path(path).read_text().splitlines()] if Path(path).exists() else []
        def append(path,value):
            with Path(path).open("a") as stream:stream.write(json.dumps(value)+"\n")
        fake_lab=types.SimpleNamespace(ROOT=str(self.root),_load=load,_atomic=atomic,_locked=nullcontext,_tail_jsonl=tail,_append=append)
        fake_sources=types.SimpleNamespace(Sources=Mock(),AtlasProcess=Mock(),collision_descriptor=Mock(),followups=Mock(),
                                         receipt=lambda source,query,records,metadata=None:dict(source=source,query=query,records=records,metadata=metadata))
        path=Path(__file__).resolve().parents[2]/"scripts/chemistry_sources.py"
        spec=importlib.util.spec_from_file_location("fixture_chemistry_sources",path)
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{"chemistry_lab":fake_lab,"lab_sources":fake_sources}):
            spec.loader.exec_module(module)
        module.fetch_projects=lambda:self.c.projects(self.c.owner_token)
        with patch("forge_lab_handback.fetch_artifacts",side_effect=lambda cfg,pid:self.c.artifacts(self.c.owner_token,pid)):
            self.assertEqual(len(module.collect_forge_handbacks({})),1)
            self.assertEqual(module.collect_forge_handbacks({}),[])
        lines=tail(self.root/"source-receipts.jsonl")
        self.assertEqual(len(lines),1)
        self.assertIsNone(lines[0]["records"]["sequence_handle"])
        self.assertIsNone(lines[0]["records"]["plugin_receipt"])
        self.assertEqual(lines[0]["metadata"]["evidence"],"reference_lookup_required")
        self.assertFalse(lines[0]["metadata"]["original_request_fulfilled"])
        self.assertEqual(lines[0]["records"]["original_request"],payload["intent"])
        self.assertEqual(module.forge_open({}),[])

    def test_handback_rechecks_request_and_source_ownership_after_fetch(self):
        from contextlib import nullcontext
        from forge_lab_handback import collect
        def load(path,default):return json.loads(Path(path).read_text()) if Path(path).exists() else default
        def atomic(path,value):Path(path).write_text(json.dumps(value))
        for field,new_value in (("question","new request after snapshot"),("receipt_ids",["replacement-source"])):
            payload=self.intake_payload(100 if field=="question" else 101)
            p=self.r.intake("i"*40,payload)
            self.builder([{"plugin_query":query()}],Mock(return_value=receipt(query())))
            self.r.step(p["id"])
            path=self.root/"forge-report-outbox.json"
            atomic(path,{"owned":{"state":"accepted","project_id":p["id"],"question":payload["intent"],"receipt_ids":["original-source"]}})
            recorded=[]
            def fetch(cfg,pid):
                data=load(path,{})
                data["owned"][field]=new_value
                atomic(path,data)
                return self.c.artifacts(self.c.owner_token,pid)
            result=collect({},self.root,self.c.projects(self.c.owner_token),load=load,atomic=atomic,
                           locked=nullcontext,fetch=fetch,record=recorded.append)
            self.assertEqual(result,[]);self.assertEqual(recorded,[])
            self.assertFalse((self.root/"forge-capability-handbacks.json").exists())
            self.assertNotIn("capability_handback",load(path,{})["owned"])
    def test_recollection_preserves_canonical_partial_and_verified_consumer_progress(self):
        from contextlib import nullcontext
        from forge_lab_handback import collect
        payload=self.intake_payload();p=self.r.intake("i"*40,payload)
        self.builder([{"plugin_query":query()}],Mock(return_value=receipt(query())))
        self.r.step(p["id"])
        path=self.root/"forge-report-outbox.json";ledger=self.root/"forge-capability-handbacks.json"
        def load(path,default):return json.loads(Path(path).read_text()) if Path(path).exists() else default
        def atomic(path,value):Path(path).write_text(json.dumps(value))
        atomic(path,{"owned":{"state":"accepted","project_id":p["id"],"question":payload["intent"],"receipt_ids":["source"]}})
        fetch=Mock(side_effect=lambda cfg,pid:self.c.artifacts(self.c.owner_token,pid));record=Mock()
        def pull():return collect({},self.root,self.c.projects(self.c.owner_token),load=load,atomic=atomic,
                                  locked=nullcontext,fetch=fetch,record=record)
        row=pull()[0]
        for state,fulfilled in (("partial",False),("verified_present",True),("verified_absent",True)):
            rows=load(ledger,{})
            rows[row["cycle_id"]]["verification"]={"state":state,"ownership_sha256":rows[row["cycle_id"]]["ownership_sha256"],
                                                        "evidence_receipt_ids":["a"*64],"original_request_fulfilled":fulfilled}
            atomic(ledger,rows)
            outbox=load(path,{});outbox["owned"].pop("capability_handback")
            atomic(path,outbox)
            self.assertEqual(pull(),[])
            pointer=load(path,{})["owned"]["capability_handback"]
            self.assertEqual(pointer["state"],state)
            self.assertIs(pointer["original_request_fulfilled"],fulfilled)
            self.assertEqual(pull(),[])
        rows=load(ledger,{})
        rows[row["cycle_id"]]["verification"]["ownership_sha256"]="f"*64
        atomic(ledger,rows)
        self.assertEqual(pull(),[])
        self.assertEqual(load(path,{})["owned"]["capability_handback"]["state"],"unresolved")
        self.assertFalse(load(path,{})["owned"]["capability_handback"]["original_request_fulfilled"])
        self.assertEqual(fetch.call_count,1);self.assertEqual(record.call_count,1)
        self.assertEqual(self.status(p)["state"],"awaiting_lab") # no implicit Forge acknowledgement

    def test_paid_claim_still_refused(self):
        p=self.project()
        self.assertIsNone(self.c.claim(self.c.worker_token,p["id"],"research_report",quote_cents=1))
        self.assertEqual(self.c.step_budget(self.c.owner_token)["used"],0)

if __name__=="__main__":unittest.main()

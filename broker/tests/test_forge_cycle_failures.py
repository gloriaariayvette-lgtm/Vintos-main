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
def query(): return {"plugin":"genomic_intelligence","tool":"genomic_intelligence.find_genes",
                     "arguments":{"gene":"SLC26A19","species":"human"},"purpose":"Verify original identifier without guessing."}
def receipt(q):
    return {"ok":True,"summary":"fixture: no matches; identifier preserved",
            "receipt":{"receipt_id":"a"*64,"result_sha256":"a"*64,"surface":"forge","plugin":q["plugin"],"tool":q["tool"],
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
        self.assertEqual(self.status(p)["state"],"complete")
        artifact=json.loads(self.c.artifacts(self.c.owner_token,p["id"])[0]["artifact"])
        self.assertNotIn("report",artifact)
        self.assertEqual(artifact["capability_resolution"]["status"],"existing_read_route_verified")
        self.assertIn("not_new_capability_built",artifact["truth_status"])
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
        body={"intent":"The Lab needs an instrument it does not have: genomic source lookup",
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

    def test_paid_claim_still_refused(self):
        p=self.project()
        self.assertIsNone(self.c.claim(self.c.worker_token,p["id"],"research_report",quote_cents=1))
        self.assertEqual(self.c.step_budget(self.c.owner_token)["used"],0)

if __name__=="__main__":unittest.main()

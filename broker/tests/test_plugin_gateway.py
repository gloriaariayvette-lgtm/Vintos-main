#!/usr/bin/env python3
"""Plugin relay policy, receipts and organ adapters; no network or real account."""
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),"../.."));sys.path.insert(0,os.path.join(ROOT,"scripts"))
import plugin_catalog as catalog
import plugin_gateway as gateway
import chemistry_sources
import forge_house
import atelier_plugin
import plugin_relay_remote as remote
import forge_loop_runtime


class PluginGatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="plugin-gateway-")
        self.old=gateway.MEMORY; gateway.MEMORY=self.tmp.name

    def tearDown(self):
        gateway.MEMORY=self.old; self.tmp.cleanup()

    def fake(self, request):
        self.request=request
        return {"ok":True,"plugin":request.get("plugin"),"tool":request.get("tool"),
                "visibility":"private","result":{"structuredContent":{"value":"bounded"},"isError":False}}

    def test_call_is_bounded_and_reusable_by_origin_surface(self):
        out=gateway.call("wants","gmail","gmail.search_email_ids",{"query":"from:example"},"find a named receipt",transport=self.fake)
        self.assertEqual(self.request["surface"],"wants")
        rid=out["receipt"]["receipt_id"]
        loaded=gateway.load_receipt(rid,"wants")
        self.assertEqual(loaded["result"]["structuredContent"]["value"],"bounded")
        self.assertTrue(loaded["receipt"]["artifact"].startswith(self.tmp.name))
        self.assertEqual(os.stat(loaded["receipt"]["artifact"]).st_mode & 0o077,0)
        with self.assertRaises(PermissionError): gateway.load_receipt(rid,"atelier")

    def test_mutating_tools_and_wrong_surfaces_are_refused_before_transport(self):
        for plugin,surface,tool in (("gmail","wants","gmail.delete_emails"),
            ("github","forge","github.create_commit"),("doordash","wants","doordash.doordash_checkout"),
            ("proto","lab","proto.run_tool")):
            with self.subTest(tool=tool), self.assertRaises(PermissionError):
                gateway.call(surface,plugin,tool,{},"test",transport=lambda _:self.fail("transport reached"))

    def test_gmail_send_is_available_on_all_surfaces(self):
        for surface in catalog.SURFACES:
            with self.subTest(surface=surface):
                self.assertEqual(catalog.policy("gmail",surface,"gmail.send_email")["visibility"],"private")

    def test_remote_side_reserves_only_two_send_attempts_per_chicago_day(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        root=os.path.join(self.tmp.name,"relay-state")
        now=datetime(2026,9,20,23,59,tzinfo=ZoneInfo("America/Chicago"))
        one=remote.reserve_email_send("gmail.send_email",{"to":"one@example.test","payload":{"body":"secret"}},"one",now,root)
        two=remote.reserve_email_send("gmail.forward_emails",{"to":"two@example.test"},"two",now,root)
        self.assertEqual((one["used"],two["used"]),(1,2))
        with self.assertRaisesRegex(PermissionError,"daily send limit"):
            remote.reserve_email_send("gmail.send_draft",{"draft_id":"third"},"three",now,root)
        with open(os.path.join(root,"gmail-send-attempts.jsonl"),encoding="utf-8") as stream:
            ledger=stream.read()
        self.assertNotIn("one@example.test",ledger)
        self.assertNotIn("secret",ledger)
        tomorrow=datetime(2026,9,21,0,0,tzinfo=ZoneInfo("America/Chicago"))
        self.assertEqual(remote.reserve_email_send("gmail.send_draft",{"draft_id":"next"},"next",tomorrow,root)["used"],1)

    def test_declared_surfaces_share_one_gateway(self):
        self.assertTrue(callable(forge_house.plugin_query))
        self.assertTrue(callable(chemistry_sources.query_plugin))
        self.assertTrue(callable(atelier_plugin.query))
        self.assertIn("wants",catalog.PLUGINS["github"]["surfaces"])
        self.assertIn("forge",catalog.PLUGINS["github"]["surfaces"])
        self.assertIn("lab",catalog.PLUGINS["github"]["surfaces"])
        self.assertIn("atelier",catalog.PLUGINS["github"]["surfaces"])

    def test_each_planner_gets_a_filtered_menu_with_exact_tool_names(self):
        wants=catalog.instructions("wants")
        lab=catalog.instructions("lab")
        self.assertIn("gmail.send_email",wants["connectors"]["gmail"]["tools"])
        self.assertNotIn("doordash",lab["connectors"])
        self.assertIn("genomic_intelligence.predict_promoter",
                      lab["connectors"]["genomic_intelligence"]["tools"])
        self.assertIn("github.get_",catalog.prompt_instructions("forge"))
        for path,needle in (("bin/emoclaw_utils.py",'prompt_instructions as _plugin_prompt'),
                            ("scripts/forge_loop_runtime.py","self._menu()"),
                            ("scripts/chemistry_lab.py",'prompt_instructions("lab")'),
                            ("scripts/chemistry_session.py",'prompt_instructions("lab")'),
                            ("scripts/atelier-visit.py","plugin_block()")):
            with self.subTest(path=path):
                self.assertIn(needle,__import__("pathlib").Path(os.path.join(ROOT,path)).read_text())

    def test_wants_planner_keeps_required_plugin_parameters(self):
        import emoclaw_utils
        body=[{"capability":"plugin_query","note":"read the named issue","params":{
            "plugin":"github","tool":"github.get_issue","arguments":{"owner":"o","repo":"r","issue_number":1},
            "purpose":"ground the want"},"execution":"pure","expected_output":"issue","acceptance":"receipt"}]
        response=mock.Mock();response.json.return_value={"choices":[{"message":{"content":json.dumps(body)}}]}
        requests=types.SimpleNamespace(post=mock.Mock(return_value=response))
        with mock.patch.dict(sys.modules,{"requests":requests}), mock.patch("subprocess.run") as run:
            run.return_value=mock.Mock(returncode=1,stdout="")
            steps=emoclaw_utils.generate_steps("I want to understand the named GitHub issue")
        self.assertEqual(steps[0]["params"]["tool"],"github.get_issue")
        self.assertIn("gmail.send_email",requests.post.call_args.kwargs["json"]["messages"][0]["content"])

    def test_forge_executes_one_selected_plugin_and_reasons_over_its_return(self):
        calls=[]
        answers=[{"plugin_query":{"plugin":"github","tool":"github.get_issue","arguments":{"n":1},
                                  "purpose":"ground the report"}},
                 {"title":"grounded","sourced_observations":[],"hypotheses":[],"conflicting_evidence":[],
                  "limitations":"bounded","next_tests":[]},
                 {"complete":True,"reasons":"grounded in receipt","reveal":True}]
        def model(system,user):
            calls.append((system,user));return answers.pop(0)
        receipt={"receipt_id":"a"*64,"artifact":"/scratch/result.json"}
        builder=forge_loop_runtime.ReportBuilder(model,plugin_call=lambda *args:{"ok":True,"receipt":receipt,"summary":"issue body"})
        out=builder({"capability":"research_report","maximum_cents":0,"cycle_id":"C1"},{"intent":"inspect issue"})
        self.assertIn("issue body",calls[1][1])
        self.assertEqual(out["artifact"]["plugin_receipt"]["receipt_id"],"a"*64)

    def test_atelier_returns_full_plugin_data_to_the_same_sealed_visit(self):
        rid="b"*64; seen={}
        fake=type("FakeAtelierPlugin",(),{
            "query":staticmethod(lambda *args:{"receipt":{"receipt_id":rid}}),
            "artifact":staticmethod(lambda receipt_id:{"result":{"structuredContent":{"finding":"kept and used"}}})})
        response=mock.Mock();response.json.return_value={"file":"plugin-result.json"}
        requests=types.SimpleNamespace(post=mock.Mock(return_value=response))
        spec=importlib.util.spec_from_file_location("atelier_visit_plugin_test",os.path.join(ROOT,"scripts","atelier-visit.py"))
        visit=importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules,{"requests":requests}): spec.loader.exec_module(visit)
        def ask(system,user,**kwargs): seen["system"]=system;return "<piece kind=\"write\">used it</piece>"
        request='<plugin>{"plugin":"github","tool":"github.get_issue","arguments":{"n":1},"purpose":"project evidence"}</plugin>'
        with mock.patch.dict(sys.modules,{"atelier_plugin":fake}), mock.patch.object(visit,"ask",side_effect=ask):
            work=visit.plugin_loop("P1","sealed context",request,"visit-cap")
        self.assertIn("kept and used",seen["system"])
        self.assertIn("used it",work)

    def test_bionemo_stays_named_but_closed_until_compute_is_configured(self):
        with self.assertRaises(PermissionError) as held: catalog.skill_policy("bionemo","lab")
        self.assertIn("compute route",str(held.exception))

    def test_skill_artifacts_are_integrity_checked_and_stored(self):
        import base64,hashlib
        data=b"artifact bytes"; digest=hashlib.sha256(data).hexdigest()
        def skill_transport(request):
            self.assertEqual(request["action"],"skill")
            return {"ok":True,"summary":"verified locally","files":[{"path":"answer.pdf","sha256":digest,
                "data_b64":base64.b64encode(data).decode()}]}
        out=gateway.run_skill("atelier","pdf","Make the requested report",transport=skill_transport)
        with open(out["files"][0],"rb") as stream: self.assertEqual(stream.read(),data)
        self.assertEqual(out["summary"],"verified locally")


if __name__=="__main__":unittest.main(verbosity=2)

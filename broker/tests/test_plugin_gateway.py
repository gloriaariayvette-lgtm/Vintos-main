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
from plugin_send_guard import PolicyHold
import forge_loop_runtime
import plugin_gateway_service


class PluginGatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="plugin-gateway-")
        self.old=gateway.MEMORY; gateway.MEMORY=self.tmp.name
        self.secrets=os.path.join(self.tmp.name,"secrets");os.mkdir(self.secrets)
        os.chmod(self.secrets,0o700)
        self.env=mock.patch.dict(os.environ,{"VINTOS_SECRETS":self.secrets})
        self.env.start()

    def tearDown(self):
        self.env.stop();gateway.MEMORY=self.old; self.tmp.cleanup()

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

    def test_secret_bearing_send_is_blocked_before_transport_and_receipt_is_redacted(self):
        secret="fixture-private-value-582904"
        with open(os.path.join(self.secrets,"mail-token"),"w",encoding="utf-8") as stream: stream.write(secret)
        os.chmod(os.path.join(self.secrets,"mail-token"),0o600)
        with self.assertRaises(PolicyHold) as held:
            gateway.call("forge","gmail","gmail.send_email",
                {"to":"person@example.test","subject":"hello","body":"credential="+secret},
                "bounded outreach",transport=lambda _:self.fail("transport reached"))
        self.assertEqual(held.exception.receipt["type"],"CONFIDENTIAL_INFORMATION_BLOCKED")
        ledger=__import__('pathlib').Path(self.tmp.name,"plugin-policy-holds.jsonl").read_text()
        self.assertNotIn(secret,ledger)
        self.assertEqual(os.stat(os.path.join(self.tmp.name,"plugin-policy-holds.jsonl")).st_mode & 0o077,0)

    def test_link_send_requires_exact_message_approval_then_reaches_transport(self):
        args={"to":"person@example.test","subject":"reference","body":"See https://example.test/a"}
        with self.assertRaises(PolicyHold) as held:
            gateway.call("wants","gmail","gmail.send_email",args,"send reference",transport=lambda _:self.fail("transport reached"))
        receipt=held.exception.receipt
        self.assertEqual(receipt["type"],"LINK_APPROVAL_REQUIRED")
        gateway.approve_link(receipt["hold_id"])
        out=gateway.call("wants","gmail","gmail.send_email",args,"send reference",transport=self.fake)
        self.assertTrue(out["ok"]);self.assertEqual(self.request["link_approval"]["request_sha256"],receipt["request_sha256"])
        with self.assertRaises(PolicyHold):
            gateway.call("wants","gmail","gmail.send_email",args,"duplicate",transport=lambda _:self.fail("transport reached"))
        changed=dict(args,body="See https://example.test/b")
        with self.assertRaises(PolicyHold):
            gateway.call("wants","gmail","gmail.send_email",changed,"changed",transport=lambda _:self.fail("transport reached"))

    def test_remote_secret_and_link_checks_run_after_budget_but_before_provider(self):
        old=remote.STATE_DIR;remote.STATE_DIR=__import__('pathlib').Path(self.tmp.name)/"relay-state"
        try:
            with self.assertRaises(PolicyHold):
                remote.connector({"surface":"forge","plugin":"gmail","tool":"gmail.send_email",
                    "arguments":{"to":"x@example.test","body":"password: fixture-value"},"purpose":"test"})
            with self.assertRaises(PolicyHold):
                remote.connector({"surface":"forge","plugin":"gmail","tool":"gmail.send_email",
                    "arguments":{"to":"x@example.test","body":"https://example.test"},"purpose":"test"})
            rows=(remote.STATE_DIR/"gmail-send-attempts.jsonl").read_text().splitlines()
            self.assertEqual(len(rows),2)
        finally: remote.STATE_DIR=old

    def test_provider_held_draft_and_forward_are_fail_closed(self):
        for tool,args in (("gmail.send_draft",{"draft_id":"D"}),
                          ("gmail.forward_emails",{"message_id":"M","to":"x@example.test"})):
            with self.subTest(tool=tool), self.assertRaises(PolicyHold) as held:
                gateway.call("atelier","gmail",tool,args,"send mail",transport=lambda _:self.fail("transport reached"))
            self.assertIn("provider_held_content_unavailable_for_inspection",held.exception.receipt["rules"])

    def test_returned_mail_links_are_marked_without_being_opened(self):
        fake_proc=mock.Mock();fake_proc.stdin=mock.Mock();fake_proc.stdout=mock.Mock()
        replies=iter([{"result":{}},{"result":{"thread":{"id":"T"}}},
                      {"result":{"structuredContent":{"body":"Read https://example.test/message"}}}])
        with mock.patch.object(remote.Path,"is_file",return_value=True), \
             mock.patch.object(remote.subprocess,"Popen",return_value=fake_proc), \
             mock.patch.object(remote,"_rpc",side_effect=lambda *a,**k: next(replies)):
            out=remote.connector({"surface":"lab","plugin":"gmail","tool":"gmail.read_email",
                                  "arguments":{"message_id":"M"},"purpose":"read mail"})
        self.assertEqual(out["link_gate"]["action"],"open_or_follow")
        self.assertIn("https://example.test/message",out["link_gate"]["links"])

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

    def test_system_forge_bundle_uses_bounded_loopback_gateway(self):
        from pathlib import Path
        bundle=set(Path(ROOT,"scripts","forge-loop-files.txt").read_text().splitlines())
        self.assertTrue({"plugin_catalog.py","forge_house.py"} <= bundle)
        unit=Path(ROOT,"broker","atelier-forge-loop.service").read_text()
        self.assertIn("LoadCredential=plugin-gateway-token:",unit)
        self.assertIn("VINTOS_PLUGIN_GATEWAY_URL=http://127.0.0.1:8624/call",unit)
        self.assertIn("VINTOS_PLUGIN_GATEWAY_TOKEN=%d/plugin-gateway-token",unit)
        self.assertNotIn("plugin-relay-identity",unit)
        gateway_unit=Path(ROOT,"broker","vintos-plugin-gateway.service").read_text()
        service_source=Path(ROOT,"scripts","plugin_gateway_service.py").read_text()
        self.assertIn('make_server("127.0.0.1", 8624',service_source)
        self.assertIn("ProtectHome=read-only",gateway_unit)

    def test_loopback_gateway_forces_forge_surface_and_requires_its_token(self):
        import io
        seen={}
        def caller(*args):
            seen['args']=args
            return {'ok':True,'receipt':{'receipt_id':'c'*64},'summary':'kept'}
        api=plugin_gateway_service.API('t'*40,caller=caller)
        body=json.dumps({'plugin':'github','tool':'github.get_profile','arguments':{},'purpose':'ground report'}).encode()
        def invoke(token):
            status=[]
            out=api({'PATH_INFO':'/call','REQUEST_METHOD':'POST','HTTP_AUTHORIZATION':'Bearer '+token,
                     'CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body)},lambda s,h:status.append(s))
            return int(status[0].split()[0]),json.loads(b''.join(out))
        self.assertEqual(invoke('wrong')[0],403)
        self.assertEqual(invoke('t'*40)[0],200)
        self.assertEqual(seen['args'][0],'forge')

    def test_system_forge_calls_loopback_gateway_without_relay_key(self):
        token=__import__('pathlib').Path(self.tmp.name,'gateway-token');token.write_text('g'*40);os.chmod(token,0o600)
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,n): return json.dumps({'ok':True,'receipt':{'receipt_id':'d'*64},'summary':'profile'}).encode()
        seen={}
        def transport(req,timeout): seen['req']=req;return Response()
        with mock.patch.dict(os.environ,{'VINTOS_PLUGIN_GATEWAY_URL':'http://127.0.0.1:8624/call',
                                        'VINTOS_PLUGIN_GATEWAY_TOKEN':str(token)}), \
             mock.patch.object(forge_house,'open_request',side_effect=transport):
            out=forge_house.plugin_query('github','github.get_profile',{},'ground report')
        self.assertTrue(out['ok']);self.assertEqual(seen['req'].get_header('Authorization'),'Bearer '+'g'*40)

    def test_system_forge_fails_closed_without_loopback_gateway(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'gateway URL missing'):
                forge_house.plugin_query('github','github.get_profile',{},'ground report')

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

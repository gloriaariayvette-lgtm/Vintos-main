#!/usr/bin/env python3
"""Plugin relay policy, receipts and organ adapters; no network or real account."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),"../.."));sys.path.insert(0,os.path.join(ROOT,"scripts"))
import plugin_catalog as catalog
import plugin_gateway as gateway
import chemistry_sources
import forge_house
import atelier_plugin


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
        for plugin,surface,tool in (("gmail","wants","gmail.send_email"),
            ("github","forge","github.create_commit"),("doordash","wants","doordash.doordash_checkout"),
            ("gmail","lab","gmail.get_profile"),("proto","lab","proto.run_tool")):
            with self.subTest(tool=tool), self.assertRaises(PermissionError):
                gateway.call(surface,plugin,tool,{},"test",transport=lambda _:self.fail("transport reached"))

    def test_declared_surfaces_share_one_gateway(self):
        self.assertTrue(callable(forge_house.plugin_query))
        self.assertTrue(callable(chemistry_sources.query_plugin))
        self.assertTrue(callable(atelier_plugin.query))
        self.assertIn("wants",catalog.PLUGINS["github"]["surfaces"])
        self.assertIn("forge",catalog.PLUGINS["github"]["surfaces"])
        self.assertIn("lab",catalog.PLUGINS["github"]["surfaces"])
        self.assertIn("atelier",catalog.PLUGINS["github"]["surfaces"])

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

"""The Forge report's GitHub read scope: the catalog's exact read names pass, lookalikes and writes never dispatch.

Offline: scratch store, fake model, fake connector, list-append publisher. Extends the single github.search case in
test_forge_cycle_failures.py (22 October) to github.fetch, the prefixes, lookalikes and the genomic read_only boundary.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from forge_loop import Controller
from forge_loop_runtime import Runtime, ReportBuilder
from forge_cycle_failure import ValidationFailure
from test_forge_cycle_failures import draft, critique, query, receipt

def github(tool): return {"plugin":"github","tool":tool,"arguments":{"query":"RP1 humanoid"},"purpose":"Read source evidence"}

class GithubReadScope(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.network=[]
        for name in ("socket.socket.connect","urllib.request.urlopen"):
            p=patch(name,side_effect=AssertionError("network forbidden"));self.network.append(p.start());self.addCleanup(p.stop)
        p=patch("forge_loop.software_quota.limit",return_value=50);p.start();self.addCleanup(p.stop)
        self.c=Controller(self.root/"forge.sqlite","o"*40,"w"*40,"https://fixture.invalid")
        self.sent=[];self.publish=lambda payload:self.sent.append(payload) or True
        self.r=Runtime(self.c,Mock(),Mock(),self.publish,"test-topic",intake_token="i"*40)
        self.addCleanup(self.assert_isolated)
    def assert_isolated(self):
        # the only store is the throwaway directory, and nothing that sends is real
        live=Path(os.path.expanduser("~/.vintos/workspace")).resolve()
        self.assertTrue(self.root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertFalse(self.root.resolve().is_relative_to(live))
        self.assertEqual(self.c.path.parent,self.root.resolve())
        self.assertEqual([m.call_count for m in self.network],[0,0])
        self.assertIs(self.r.publisher,self.publish);self.assertIsInstance(self.r.projection,Mock)
    def project(self,kind="research_report"):
        return self.r.create(self.c.owner_token,{"intent":"fixture request","kind":kind})
    def builder(self,outputs,plugin):
        model=Mock(side_effect=outputs);model.model="fixture-local"
        b=ReportBuilder(model,plugin_call=plugin);b._menu=lambda:"fixture installed read tools"
        self.r.builder=b
        return model
    def code(self,p): return (self.c.status(self.c.owner_token,p["id"]).get("diagnostic") or {}).get("code")

    def test_exact_catalog_names_and_prefixes_reach_one_connector_call(self):
        # github.fetch beside github.search: both are the catalog's exact read names, not prefix matches
        for tool in ("github.search","github.fetch","github.get_repo","github.list_repositories",
                     "github.search_installed_repositories_v2","github.fetch_file","github.compare_commits"):
            with self.subTest(tool=tool):
                p=self.project();q=github(tool);plugin=Mock(return_value=receipt(q,{"title":"fixture repo"}))
                self.builder([{"plugin_query":q},draft(),critique()],plugin)
                self.assertTrue(self.r.step(p["id"]))
                plugin.assert_called_once();self.assertEqual(plugin.call_args.args[:2],("github",tool))
                self.assertNotEqual(self.code(p),"report_effect_scope")

    def test_lookalikes_and_writes_never_reach_the_connector(self):
        for tool in ("github.searchX","github.fetchX","github.create_issue"):
            with self.subTest(tool=tool):
                p=self.project();plugin=Mock(side_effect=AssertionError("connector must not be called"))
                model=self.builder([{"plugin_query":github(tool)}],plugin)
                with self.assertRaises(ValidationFailure):self.r.step(p["id"])
                plugin.assert_not_called();self.assertEqual(model.call_count,1)
                self.assertIn(self.code(p),("plugin_unavailable","report_effect_scope"))

    def test_genomic_read_only_boundary_still_holds(self):
        # a capability route may fetch genomic sequence; GitHub reads stay report-only
        p=self.project("capability_request");plugin=Mock()
        self.builder([{"plugin_query":github("github.search")}],plugin)
        with self.assertRaises(ValidationFailure):self.r.step(p["id"])
        plugin.assert_not_called();self.assertEqual(self.code(p),"capability_scope")
        p=self.r.create(self.c.owner_token,{"kind":"capability_request","intent":"Fetch human SLC26A19"})
        plugin=Mock(return_value=receipt(query()))
        self.builder([{"plugin_query":query()}],plugin)
        self.assertTrue(self.r.step(p["id"]));plugin.assert_called_once()

if __name__ == "__main__":
    unittest.main()

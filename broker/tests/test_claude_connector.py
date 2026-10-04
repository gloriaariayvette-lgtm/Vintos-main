#!/usr/bin/env python3
"""Claude-account connector catalog, gateway routing, relay keep-output and token persist.

Isolation (CLAUDE.md): the receipt store is repointed into a throwaway dir and the relay transport
is a stub, so nothing here reaches the account, the account's connectors, or Gloria's real workspace.
Both facts are asserted in the suite so a later edit cannot quietly undo them.
"""
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import plugin_gateway
import claude_connector_catalog as ccc
import claude_connector_gateway as ccg
import claude_connector_relay as relay
from plugin_send_guard import PolicyHold


class ScienceConnectorTests(unittest.TestCase):
    """Boltz and EDEN, added 2026-10-04. Nothing here reaches either account: the catalog is pure policy."""

    def test_her_url_file_offers_a_connector_without_a_code_change(self):
        for name in ("boltz", "eden"):
            self.assertNotIn(name, ccc.prompt_instructions("lab"), name + " is offered with no url")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "connector-urls.json")
            open(path, "w").write('{"boltz": "https://boltz.example/mcp", "eden": "https://eden.example/mcp"}')
            with mock.patch.object(ccc, "URLS_FILE", path):
                self.assertEqual(ccc.url_for("boltz"), "https://boltz.example/mcp")
                block = ccc.prompt_instructions("lab")
                self.assertIn("boltz", block)
                self.assertIn("eden", block)
                self.assertEqual(ccc.policy("boltz", "lab", "boltz_get_guidance")["url"], "https://boltz.example/mcp")
        self.assertEqual(ccc.url_for("boltz"), "")          # her file gone, it is unreachable again
        self.assertTrue(ccc.url_for("pubmed").startswith("https://"))   # a wired one is unaffected

    def test_no_boltz_tool_that_spends_her_money_is_reachable(self):
        entry = ccc.PLUGINS["boltz"]
        self.assertEqual(entry["action"], frozenset())
        reachable = entry["read"] | entry["action"]
        self.assertFalse([t for t in reachable if "_start_" in t], reachable)
        for tool in entry["paid_tools_withheld"]:
            for surface in entry["surfaces"]:
                with self.assertRaises(PermissionError):
                    ccc.policy("boltz", surface, tool)

    def test_boltz_can_validate_and_price_a_run_for_free(self):
        for tool in ("boltz_estimate_structure_and_binding", "boltz_get_guidance", "boltz_get_job_results"):
            self.assertFalse(ccc.policy("boltz", "lab", tool)["is_action"], tool)

    def test_boltz_is_a_lab_instrument_not_an_everywhere_one(self):
        self.assertEqual(set(ccc.PLUGINS["boltz"]["surfaces"]), {"lab", "forge"})
        for surface in ("wants", "atelier"):
            with self.assertRaises(PermissionError):
                ccc.policy("boltz", surface, "boltz_get_guidance")

    def test_eden_designs_nothing_and_touches_no_dataset(self):
        entry = ccc.PLUGINS["eden"]
        self.assertEqual(entry["read"], frozenset(("predict_immunogenicity",)))
        self.assertEqual(entry["action"], frozenset())
        for tool in entry["withheld"]:
            with self.assertRaises(PermissionError):
                ccc.policy("eden", "lab", tool)
        self.assertIn("generate_antimicrobial_peptides", entry["withheld"])

    def test_eden_says_the_sequence_it_needs_and_what_it_is_not(self):
        when = ccc.PLUGINS["eden"]["when"].lower()
        self.assertIn("nucleotide", when)
        self.assertIn("never an amino-acid", when)
        self.assertIn("research use only", when)

    def test_boltz_says_the_estimate_is_free_and_the_run_is_hers(self):
        self.assertIn("without running it", ccc.PLUGINS["boltz"]["when"].lower())
        self.assertIn("gloria starts a paid run", ccc.PLUGINS["boltz"]["when"].lower())


class CatalogTests(unittest.TestCase):
    def test_url_less_connector_is_never_offered(self):
        # uber_eats deliberately has no MCP url — it must not appear in any surface's menu.
        self.assertIsNone(ccc.PLUGINS["uber_eats"].get("url"))
        for surface in ("wants", "atelier"):
            self.assertNotIn("uber_eats", ccc.instructions(surface))
        block = ccc.prompt_instructions("wants")
        self.assertIn("pubmed", block)
        self.assertNotIn("uber_eats", block)

    def test_wired_connectors_carry_a_url(self):
        # boltz and eden are deliberately not here: their url is hers to supply (connector-urls.json)
        for name in ("pubmed", "chembl", "hugging_face", "spotify", "google_calendar"):
            self.assertTrue(ccc.PLUGINS[name].get("url"), name)

    def test_verified_connectors_are_offered_and_auth_blocked_ones_are_not(self):
        for name in ("pubmed", "chembl", "hugging_face"):
            self.assertEqual(set(ccc.PLUGINS[name]["surfaces"]), set(ccc.SURFACES), name)
        for surface in ccc.SURFACES:
            block = ccc.prompt_instructions(surface)
            for name in ("pubmed", "chembl", "hugging_face"):
                self.assertIn(name, block, "%s missing on %s" % (name, surface))
            self.assertNotIn("spotify", block)
            self.assertNotIn("google_calendar", block)
            self.assertNotIn("uber_eats", block)
        for name, tool in (("spotify", "get_currently_playing"),
                           ("google_calendar", "list_calendars")):
            with self.assertRaises(PermissionError): ccc.policy(name, "lab", tool)

    def test_policy_shape_matches_chat_gateway(self):
        p = ccc.policy("pubmed", "lab", "search_articles")
        self.assertEqual(p["server"], "PubMed")
        self.assertTrue(p["url"])
        self.assertFalse(p["is_action"])
        # ChEMBL's real tool names (verified against her connected instance) pass policy.
        self.assertEqual(ccc.policy("chembl", "lab", "chembl_search_molecules")["server"], "ChEMBL")
        with self.assertRaises(PermissionError):
            ccc.policy("chembl", "lab", "compound_search")   # the old guessed name is gone
        self.assertIn("save_to_library", ccc.PLUGINS["spotify"]["action"])
        with self.assertRaises(PermissionError):
            ccc.policy("pubmed", "wants", "delete_everything")


class RoutingTests(unittest.TestCase):
    def test_owns_splits_the_two_accounts(self):
        self.assertTrue(ccg.owns("pubmed"))
        self.assertTrue(ccg.owns("uber_eats"))
        self.assertFalse(ccg.owns("gmail"))
        self.assertFalse(ccg.owns("github"))


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="claude-connector-")
        self.old_mem = plugin_gateway.MEMORY
        plugin_gateway.MEMORY = self.tmp.name

    def tearDown(self):
        plugin_gateway.MEMORY = self.old_mem
        self.tmp.cleanup()

    def stub(self, request):
        # A stubbed relay: records the request, sends nothing, returns a bounded connector result.
        self.request = request
        return {"ok": True, "plugin": request["plugin"], "tool": request["tool"],
                "surface": request["surface"], "visibility": "project",
                "result": {"articles": [{"pmid": "1"}]}, "source": "tool_result"}

    def test_call_stores_a_receipt_and_never_sends(self):
        out = ccg.call("lab", "pubmed", "search_articles", {"q": "insulin"},
                       "ground a claim in a paper", transport=self.stub)
        # The stub, not a subprocess, handled the call.
        self.assertEqual(self.request["plugin"], "pubmed")
        self.assertEqual(self.request["surface"], "lab")
        rid = out["receipt"]["receipt_id"]
        # Receipt landed in the throwaway store, 0600, and reloads by origin surface.
        artifact = out["receipt"]["artifact"]
        self.assertTrue(artifact.startswith(self.tmp.name), "receipt escaped the throwaway store")
        self.assertEqual(os.stat(artifact).st_mode & 0o077, 0)
        loaded = plugin_gateway.load_receipt(rid, "lab")
        self.assertEqual(loaded["result"]["articles"][0]["pmid"], "1")

    def test_out_of_policy_tool_is_refused_before_transport(self):
        with self.assertRaises(PermissionError):
            ccg.call("lab", "pubmed", "not_a_tool", {}, "x",
                     transport=lambda _: self.fail("transport reached on a rejected tool"))

    def test_tool_named_as_the_menu_shows_it_is_accepted(self):
        # the menu lists plugin.tool; sol's titrate plan copied it and was refused (2026-10-01)
        ccg.call("lab", "pubmed", "pubmed.get_full_text_article", {"pmid": "12672112"}, "read the paper",
                 transport=self.stub)
        self.assertEqual(self.request["tool"], "get_full_text_article")
        with self.assertRaises(PermissionError):
            ccg.call("lab", "pubmed", "chembl.get_full_text_article", {}, "x",
                     transport=lambda _: self.fail("transport reached on another connector's prefix"))

    def test_relay_hold_becomes_a_policy_hold(self):
        def held(_request):
            return {"ok": False, "receipt": {"type": "LINK_APPROVAL_REQUIRED", "state": "awaiting"}}
        with self.assertRaises(PolicyHold):
            ccg.call("lab", "pubmed", "search_articles", {"query": "folding"}, "literature", transport=held)


class RelayKeepOutputTests(unittest.TestCase):
    def test_typed_sdk_tool_result_is_kept(self):
        uses = {}
        # SDK blocks do not expose a .type property.
        call = type("ToolUseBlock", (), {"id": "call-1", "name": "mcp__PubMed__search_articles"})()
        result = type("ToolResultBlock", (), {"tool_use_id": "call-1", "content": '{"pmids":["123"]}', "is_error": False})()
        self.assertIsNone(relay._tool_result_from(SimpleNamespace(content=[call]), "search_articles", uses))
        self.assertEqual(relay._tool_result_from(SimpleNamespace(content=[result]), "search_articles", uses),
                         {"pmids": ["123"]})

    def test_denied_sdk_tool_result_fails_closed(self):
        uses = {"call-2": "mcp__Spotify__get_currently_playing"}
        result = type("ToolResultBlock", (), {"tool_use_id": "call-2", "content": "sign in again", "is_error": True})()
        with self.assertRaises(RuntimeError):
            relay._tool_result_from(SimpleNamespace(content=[result]), "get_currently_playing", uses)

    def test_fenced_json_is_parsed(self):
        value, parsed = relay._coerce_result('```json\n{"a": 1}\n```')
        self.assertTrue(parsed)
        self.assertEqual(value, {"a": 1})

    def test_fenced_json_with_trailing_prose_is_parsed(self):
        # The real PubMed shape: a fenced block, then an English sentence explaining it.
        text = '```json\n{"pmids": ["42769081"], "returned_count": 1}\n```\n\nThe search found 1 result.'
        value, parsed = relay._coerce_result(text)
        self.assertTrue(parsed)
        self.assertEqual(value["pmids"], ["42769081"])

    def test_bare_json_with_trailing_prose_is_parsed(self):
        value, parsed = relay._coerce_result('{"ok": true}\n\nDone.')
        self.assertTrue(parsed)
        self.assertEqual(value, {"ok": True})

    def test_bare_json_is_parsed(self):
        value, parsed = relay._coerce_result('{"b": 2}')
        self.assertTrue(parsed)
        self.assertEqual(value, {"b": 2})

    def test_prose_falls_back_to_text_without_crashing(self):
        value, parsed = relay._coerce_result("I could not find that.")
        self.assertFalse(parsed)
        self.assertEqual(value, {"text": "I could not find that."})

    def test_relay_injects_no_oauth_token(self):
        # The relay must NOT set CLAUDE_CODE_OAUTH_TOKEN itself: an env token ranks above the bundled
        # claude's stored /login, so a stale one would 401. Credential resolution is the SDK's job.
        self.assertFalse(hasattr(relay, "_ensure_token"), "relay must not inject a token")
        self.assertFalse(hasattr(relay, "TOKEN_FILE"), "relay must not read a token file")


if __name__ == "__main__":
    unittest.main()

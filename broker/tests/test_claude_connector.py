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
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import plugin_gateway
import claude_connector_catalog as ccc
import claude_connector_gateway as ccg
import claude_connector_relay as relay
from plugin_send_guard import PolicyHold


class CatalogTests(unittest.TestCase):
    def test_url_less_connector_is_never_offered(self):
        # uber_eats deliberately has no MCP url — it must not appear in any surface's menu.
        self.assertIsNone(ccc.PLUGINS["uber_eats"].get("url"))
        for surface in ("wants", "atelier"):
            self.assertNotIn("uber_eats", ccc.instructions(surface))
        block = ccc.prompt_instructions("wants")
        self.assertIn("spotify", block)
        self.assertNotIn("uber_eats", block)

    def test_wired_connectors_carry_a_url(self):
        for name in ("pubmed", "chembl", "hugging_face", "spotify", "google_calendar"):
            self.assertTrue(ccc.PLUGINS[name].get("url"), name)

    def test_wired_connectors_are_available_on_all_four_surfaces(self):
        # Gloria: available for wants, Lab, Forge and the Atelier.
        for name in ("pubmed", "chembl", "hugging_face", "spotify", "google_calendar"):
            self.assertEqual(set(ccc.PLUGINS[name]["surfaces"]), set(ccc.SURFACES), name)
        for surface in ccc.SURFACES:
            block = ccc.prompt_instructions(surface)
            for name in ("pubmed", "chembl", "hugging_face", "spotify", "google_calendar"):
                self.assertIn(name, block, "%s missing on %s" % (name, surface))
            self.assertNotIn("uber_eats", block)

    def test_policy_shape_matches_chat_gateway(self):
        p = ccc.policy("pubmed", "lab", "search_articles")
        self.assertEqual(p["server"], "PubMed")
        self.assertTrue(p["url"])
        self.assertFalse(p["is_action"])
        self.assertTrue(ccc.policy("spotify", "wants", "save_to_library")["is_action"])
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

    def test_relay_hold_becomes_a_policy_hold(self):
        def held(_request):
            return {"ok": False, "receipt": {"type": "LINK_APPROVAL_REQUIRED", "state": "awaiting"}}
        with self.assertRaises(PolicyHold):
            ccg.call("wants", "spotify", "search", {"q": "folk"}, "music", transport=held)


class RelayKeepOutputTests(unittest.TestCase):
    def test_fenced_json_is_parsed(self):
        value, parsed = relay._coerce_result('```json\n{"a": 1}\n```')
        self.assertTrue(parsed)
        self.assertEqual(value, {"a": 1})

    def test_bare_json_is_parsed(self):
        value, parsed = relay._coerce_result('{"b": 2}')
        self.assertTrue(parsed)
        self.assertEqual(value, {"b": 2})

    def test_prose_falls_back_to_text_without_crashing(self):
        value, parsed = relay._coerce_result("I could not find that.")
        self.assertFalse(parsed)
        self.assertEqual(value, {"text": "I could not find that."})


class RelayPersistTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="claude-token-")
        self.token_path = relay.Path(self.tmp.name) / "token"
        self.old_token_file = relay.TOKEN_FILE
        relay.TOKEN_FILE = self.token_path

    def tearDown(self):
        relay.TOKEN_FILE = self.old_token_file
        self.tmp.cleanup()

    def _clean_env(self):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_OAUTH_TOKEN"}
        return mock.patch.dict(os.environ, env, clear=True)

    def test_token_loaded_from_0600_file_when_env_unset(self):
        self.token_path.write_text("sk-persisted\n")
        os.chmod(self.token_path, 0o600)
        with self._clean_env():
            relay._ensure_token()
            self.assertEqual(os.environ["CLAUDE_CODE_OAUTH_TOKEN"], "sk-persisted")

    def test_world_readable_token_file_is_refused(self):
        self.token_path.write_text("sk-leaky\n")
        os.chmod(self.token_path, 0o644)
        with self._clean_env():
            with self.assertRaises(RuntimeError):
                relay._ensure_token()

    def test_env_token_is_left_untouched(self):
        self.token_path.write_text("sk-file\n")
        os.chmod(self.token_path, 0o600)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "sk-env"}):
            relay._ensure_token()
            self.assertEqual(os.environ["CLAUDE_CODE_OAUTH_TOKEN"], "sk-env")


if __name__ == "__main__":
    unittest.main()

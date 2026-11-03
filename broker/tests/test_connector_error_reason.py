#!/usr/bin/env python3
"""A connector that fails says why, all the way out to the Forge and the Lab.

The relay used to raise "requested connector tool returned an error" and drop the connector's own
reason ("sign in again", "quota exceeded"), so the Forge only ever saw that something failed.

Isolation (CLAUDE.md): the SDK is a stub in sys.modules (no model turn, no account, no connector),
the gateway's transport is the relay called in-process (no subprocess), and the receipt store and
connector-url file are repointed into a throwaway dir. All of that is asserted below.
"""
import io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

SENT = []


class Opts:
    def __init__(self, **kw): self.kw = kw


class ToolUseBlock:
    def __init__(self, i, n): self.id, self.name = i, n


class ToolResultBlock:
    def __init__(self, i, c): self.tool_use_id, self.content, self.is_error = i, c, True


class Msg:
    def __init__(self, blocks): self.content = blocks


REASON = "Authentication expired for PubMed: sign in again at claude.ai/customize/connectors"


def fake_query(prompt, options):
    SENT.append(prompt)
    async def gen():
        yield Msg([ToolUseBlock("u1", "mcp__PubMed__search_articles")])
        yield Msg([ToolResultBlock("u1", [{"type": "text", "text": REASON}])])
    return gen()


STUB_SDK = types.SimpleNamespace(query=fake_query, ClaudeAgentOptions=Opts)
sys.modules["claude_agent_sdk"] = STUB_SDK
import plugin_gateway
import claude_connector_catalog as ccc
import claude_connector_gateway as ccg
import claude_connector_relay as relay


class ConnectorErrorReasonTests(unittest.TestCase):
    def setUp(self):
        SENT.clear()
        self.tmp = tempfile.TemporaryDirectory(prefix="connector-error-")
        self.patches = [mock.patch.object(plugin_gateway, "MEMORY", self.tmp.name),
                        mock.patch.object(ccc, "URLS_FILE", os.path.join(self.tmp.name, "urls.json"))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_isolation_holds(self):
        self.assertIs(sys.modules["claude_agent_sdk"], STUB_SDK)
        self.assertTrue(plugin_gateway.MEMORY.startswith(tempfile.gettempdir()))
        self.assertTrue(ccc.URLS_FILE.startswith(self.tmp.name))

    def test_relay_reports_the_connectors_own_reason(self):
        request = {"plugin": "pubmed", "surface": "forge", "tool": "search_articles", "arguments": {"query": "x"}}
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(request))), mock.patch.object(sys, "stdout", out):
            relay.main()
        reply = json.loads(out.getvalue())
        self.assertEqual(len(SENT), 1, "the stub SDK, not a real one, took the call")
        self.assertFalse(reply["ok"])
        self.assertIn("Authentication expired for PubMed", reply["detail"])
        # ...and the gateway the Forge calls passes it on instead of a bare "failed".
        with self.assertRaises(RuntimeError) as caught:
            ccg._validate(reply)
        self.assertIn("Authentication expired for PubMed", str(caught.exception))
        self.assertEqual(os.listdir(self.tmp.name), [], "a failed call stored nothing")


if __name__ == "__main__":
    unittest.main()

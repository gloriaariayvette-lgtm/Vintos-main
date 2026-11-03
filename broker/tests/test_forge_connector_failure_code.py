#!/usr/bin/env python3
"""A connector that fails says why, all the way into the Forge's diagnostic and her notification.

The relay kept the connector's own reason (test_connector_error_reason), but the loopback gateway then
collapsed every failure to "gateway_call_failed" and the Forge recorded "unexpected adapter failure".
Now an allowlisted code (connector_auth, connector_quota, ...) crosses relay -> gateway -> Forge;
the connector's text, and anything secret in it, never does; and the call is made once, not repaired.

Isolation (CLAUDE.md): the SDK is a stub in sys.modules (no model turn, no account, no connector); the
relay runs in-process (no subprocess); the HTTP hop is the gateway's WSGI app called directly (no
socket); the Forge database, receipt store, connector-url file and gateway token live in a throwaway
dir; sockets and urlopen are forbidden; the notification publisher is a list. All asserted below.
"""
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

SECRET = "sk-ant-api03-FIXTUREsecretFIXTUREsecret"
REASON = "Authentication expired: sign in again (token " + SECRET + ")"
QUERIES = []


class Opts:
    def __init__(self, **kw): self.kw = kw


class ToolUseBlock:
    def __init__(self, i, n): self.id, self.name = i, n


class ToolResultBlock:
    def __init__(self, i, c): self.tool_use_id, self.content, self.is_error = i, c, True


class Msg:
    def __init__(self, blocks): self.content = blocks


def fake_query(prompt, options):
    QUERIES.append(prompt)
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
import plugin_gateway_service
import forge_house
from forge_loop import Controller
from forge_loop_runtime import Runtime, ReportBuilder
from forge_cycle_failure import REASONS

GATEWAY_TOKEN = "g" * 40


def relay_in_process(request):
    """The relay subprocess, run here: its JSON in, its JSON out."""
    out = io.StringIO()
    with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(request))), mock.patch.object(sys, "stdout", out):
        relay.main()
    return json.loads(out.getvalue())


class ForgeConnectorFailureCodeTests(unittest.TestCase):
    def setUp(self):
        QUERIES.clear()
        self.tmp = tempfile.TemporaryDirectory(prefix="forge-connector-code-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        token = root / "gateway-token"
        token.write_text(GATEWAY_TOKEN); os.chmod(token, 0o600)
        self.api = plugin_gateway_service.API(GATEWAY_TOKEN)
        real_call = ccg.call
        self.sent, self.http = [], []
        for p in (mock.patch.object(plugin_gateway, "MEMORY", str(root / "memory")),
                  mock.patch.object(ccc, "URLS_FILE", str(root / "urls.json")),
                  mock.patch.object(ccg, "call", lambda *a: real_call(*a, transport=relay_in_process)),
                  mock.patch.object(forge_house, "open_request", side_effect=self.loopback),
                  mock.patch.dict(os.environ, {"VINTOS_PLUGIN_GATEWAY_URL": "http://127.0.0.1:8624/call",
                                               "VINTOS_PLUGIN_GATEWAY_TOKEN": str(token)}),
                  mock.patch("forge_loop.software_quota.limit", return_value=3),
                  mock.patch("socket.socket.connect", side_effect=AssertionError("network forbidden")),
                  mock.patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden"))):
            p.start(); self.addCleanup(p.stop)
        self.c = Controller(root / "forge.sqlite", "o" * 40, "w" * 40, "https://fixture.invalid")
        self.r = Runtime(self.c, mock.Mock(), mock.Mock(), lambda payload: self.sent.append(payload) or True,
                         "test-topic", intake_token="i" * 40)

    def loopback(self, req, timeout):
        """The HTTP hop to the gateway service, answered by its WSGI app with no socket."""
        status = []
        out = b"".join(self.api({"PATH_INFO": "/call", "REQUEST_METHOD": "POST",
                                 "HTTP_AUTHORIZATION": req.get_header("Authorization"),
                                 "CONTENT_LENGTH": str(len(req.data)), "wsgi.input": io.BytesIO(req.data)},
                                lambda s, h: status.append(s)))
        code = int(status[0].split()[0])
        self.http.append((code, out))
        if code != 200:
            raise HTTPError(req.full_url, code, status[0], {}, io.BytesIO(out))
        raise AssertionError("the failing connector must not answer 200")

    def test_isolation_holds(self):
        self.assertIs(sys.modules["claude_agent_sdk"], STUB_SDK)
        tmp = str(Path(self.tmp.name).resolve())
        for path in (plugin_gateway.MEMORY, ccc.URLS_FILE, self.c.path, os.environ["VINTOS_PLUGIN_GATEWAY_TOKEN"]):
            self.assertTrue(str(Path(path).resolve()).startswith(tmp), path)
        self.assertIsInstance(forge_house.open_request, mock.Mock)   # the HTTP hop never leaves the process

    def test_auth_failure_code_reaches_diagnostic_and_notification_once_and_redacted(self):
        p = self.r.create(self.c.owner_token, {"intent": "fixture request", "kind": "research_report"})
        query = {"plugin": "pubmed", "tool": "search_articles", "arguments": {"query": "fixture"},
                 "purpose": "Ground the report in one search."}
        model = mock.Mock(side_effect=[{"plugin_query": query}]); model.model = "fixture-local"
        builder = ReportBuilder(model, plugin_call=forge_house.plugin_query)
        builder._menu = lambda: "fixture menu"
        self.r.builder = builder
        with self.assertRaises(Exception):
            self.r.step(p["id"])
        diagnostic = self.c.status(self.c.owner_token, p["id"])["diagnostic"]
        self.assertEqual(diagnostic["code"], "connector_auth")
        self.assertEqual(diagnostic["reason"], REASONS["connector_auth"])
        self.assertEqual(len(QUERIES), 1, "one connector attempt, never repaired or replayed")
        self.assertEqual(model.call_count, 1)
        self.assertEqual([c for c, _ in self.http], [500])
        self.assertEqual(json.loads(self.http[0][1]), {"error": "gateway_call_failed", "code": "connector_auth"})
        self.r.dispatch()
        self.assertEqual(len(self.sent), 1, "the notification went to the stub publisher")
        self.assertIn(REASONS["connector_auth"], self.sent[0]["message"])
        for leak in (SECRET, "Authentication expired"):
            self.assertNotIn(leak, json.dumps(diagnostic))
            self.assertNotIn(leak, json.dumps(self.sent))
            self.assertNotIn(leak, self.http[0][1].decode())


if __name__ == "__main__":
    unittest.main()

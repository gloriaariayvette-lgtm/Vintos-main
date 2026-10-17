"""A refused or failed request keeps the provider's stop reason: the shim's error body carries it, and the Lab's
_ask saves it in a terminal diagnostic before the error goes on. Scratch stores; HTTP and the shim's POST are stubs."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bin"))
import chemistry_lab as lab
import vintos_claude_shim as shim


class ErrorPathCompletion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        # Repoint every workspace path the Lab writes, including tracing and any store added later.
        old_ws = lab.WS
        for name, value in list(vars(lab).items()):
            if isinstance(value, str) and value.startswith(old_ws):
                p = patch.object(lab, name, str(root) + value[len(old_ws):])
                p.start(); self.addCleanup(p.stop)
        for p in (patch.object(lab, "_eliot", None),
                  patch.dict(os.environ, {"VINTOS_ELIOT_REQUIRED": "0"}),
                  patch("socket.socket.connect", side_effect=AssertionError("no network")),
                  patch.object(shim.urllib.request, "urlopen", side_effect=AssertionError("shim must not send")),
                  patch.object(shim, "_log", lambda s: None),
                  patch.object(lab.subprocess, "run", side_effect=AssertionError("no subprocess"))):
            p.start(); self.addCleanup(p.stop)
        p = patch.object(lab.urllib.request, "urlopen")
        self.http = p.start(); self.addCleanup(p.stop)
        # Isolation asserted here so a later edit cannot quietly undo it.
        self.assertIs(lab.urllib.request.urlopen, self.http)
        for name in ("ROOT", "FAULTS", "NOTEBOOK", "RECEIPTS", "ELIOT_LOG"):
            self.assertTrue(getattr(lab, name).startswith(self.tmp.name), name)
        self.diag = Path(lab.ROOT) / "diagnostics"

    def refused(self, native):
        """The shim refuses a native reply that thought; the Lab's request then fails with the shim's 502 body."""
        request = {"max_tokens": 17, "messages": [{"role": "user", "content": "fixture"}]}
        with patch.object(shim, "_post_json", return_value=(200, native, None)) as post:
            result = shim.aegis_gemma_complete(request)
        self.assertEqual(post.call_args.args[1], shim.AEGIS_GEMMA_URL)
        self.assertEqual(result["status"], "error")
        body = shim.error_body([result])
        self.http.side_effect = urllib.error.HTTPError(lab.LLM_URL, 502, "Bad Gateway", {}, io.BytesIO(body))
        with self.assertRaises(urllib.error.HTTPError):
            lab._ask("fixture system", "fixture prompt", max_tokens=17)
        rows = [json.loads(p.read_text()) for p in self.diag.glob("*.events.json")]
        self.assertEqual(len(rows), 1)
        return json.loads(body)["error"]["providers"][0], rows[0]

    def test_cut_and_refused_reply_keeps_its_stop_reason(self):
        native = {"model_instance_id": "fixture-native",
                  "output": [{"type": "reasoning", "content": "PRIVATE thinking"},
                             {"type": "message", "content": "PRIVATE"}],
                  "stats": {"input_tokens": 7, "total_output_tokens": 17, "reasoning_output_tokens": 3,
                            "stop_reason": "maxPredictedTokensReached"}}
        provider, row = self.refused(native)
        self.assertEqual(provider["finish_reason"], "maxPredictedTokensReached")
        self.assertEqual(provider["finish_reason_source"], "stats.stop_reason")
        self.assertTrue(row["terminal"])
        self.assertEqual(row["events"], ["request_failed", "terminal"])
        completion = row["completion"]
        self.assertEqual(completion["finish_reason"], "maxPredictedTokensReached")
        self.assertEqual(completion["finish_reason_source"], "stats.stop_reason")
        self.assertIs(completion["token_limit_reached"], True)
        self.assertEqual(completion["requested_max_tokens"], 17)
        self.assertEqual(completion["http_status"], 502)
        self.assertEqual(completion["providers"][0]["provider"], "aegis_gemma")
        self.assertEqual(completion["providers"][0]["status"], "error")
        self.assertNotIn("PRIVATE", json.dumps(row))

    def test_missing_stop_reason_stays_unknown_on_the_error_path(self):
        native = {"model_instance_id": "fixture-native",
                  "output": [{"type": "reasoning", "content": "PRIVATE thinking"}],
                  "stats": {"input_tokens": 7, "total_output_tokens": 17, "reasoning_output_tokens": 3}}
        provider, row = self.refused(native)
        self.assertIsNone(provider["finish_reason"])
        self.assertIsNone(provider["finish_reason_source"])
        completion = row["completion"]
        self.assertIsNone(completion["finish_reason"])
        self.assertIsNone(completion["finish_reason_source"])
        self.assertIsNone(completion["token_limit_reached"])   # a failure is not proof of a token-limit stop
        self.assertIsNone(completion["providers"][0]["finish_reason"])
        self.assertNotIn("PRIVATE", json.dumps(row))


if __name__ == "__main__": unittest.main()

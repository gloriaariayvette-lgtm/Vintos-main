"""A failed chain keeps its provenance: the shim's 502 names each provider's request id, counts and stopping
reason, and the Lab's _ask keeps them on the exception. Scratch stores; HTTP is a stub, no models or network."""
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


class ErrorProvenance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        # Repoint every workspace path the Lab writes, not only the obvious ones.
        old_ws = lab.WS
        for name, value in list(vars(lab).items()):
            if isinstance(value, str) and value.startswith(old_ws):
                p = patch.object(lab, name, str(root) + value[len(old_ws):])
                p.start(); self.addCleanup(p.stop)
        for p in (patch.object(lab, "_eliot", None),
                  patch.dict(os.environ, {"VINTOS_ELIOT_REQUIRED": "0"}),
                  patch.object(shim, "LOG", str(root / "shim.log")),
                  patch.object(shim, "USAGE_LOG", str(root / "usage.jsonl")),
                  patch("socket.socket.connect", side_effect=AssertionError("no network")),
                  patch.object(lab.subprocess, "run", side_effect=AssertionError("no subprocess"))):
            p.start(); self.addCleanup(p.stop)
        p = patch.object(lab.urllib.request, "urlopen")
        self.http = p.start(); self.addCleanup(p.stop)
        # The isolation itself is asserted, so a later edit cannot quietly undo it.
        self.assertIs(lab.urllib.request.urlopen, self.http)
        self.assertTrue(lab.ROOT.startswith(self.tmp.name))
        self.assertTrue(lab.FAULTS.startswith(self.tmp.name))
        self.assertTrue(shim.LOG.startswith(self.tmp.name))

    def test_empty_aegis_completion_keeps_provenance_through_502_and_ask(self):
        native = {"model_instance_id": "google/gemma-4-12b-qat", "response_id": "aegis_9",
                  "output": [], "stats": {"input_tokens": 7, "total_output_tokens": 0,
                                          "reasoning_output_tokens": 0}}
        request = {"max_tokens": 17, "messages": [{"role": "user", "content": "fixture"}]}
        with patch.object(shim, "_post_json", return_value=(200, native, None)):
            result = shim.aegis_gemma_complete(request)
        self.assertEqual((result["status"], result["reason"]), ("error", "empty completion"))
        body = json.loads(shim.error_body([result]))
        entry = body["error"]["providers"][0]
        # The shim's error body carries what the provider gave, as it gave it.
        self.assertEqual(entry["provider"], "aegis_gemma")
        self.assertEqual(entry["request_id"], "aegis_9")
        self.assertEqual(entry["usage"].get("prompt_tokens"), 7)
        self.assertIn("finish_reason", entry)
        self.assertIsNone(entry["finish_reason"])          # the fixture named no stopping reason: unknown
        self.assertIn("finish_reason_source", entry)
        self.assertIsNone(entry["finish_reason_source"])
        self.http.side_effect = urllib.error.HTTPError(lab.LLM_URL, 502, "shim", {},
                                                       io.BytesIO(json.dumps(body).encode()))
        with self.assertRaises(urllib.error.HTTPError) as caught:
            lab._ask("fixture system", "fixture prompt", max_tokens=17)
        exc = caught.exception
        self.assertEqual(exc.code, 502)                     # the same exception, raised on
        completion = exc.completion
        self.assertEqual(completion["provider"], "aegis_gemma")
        self.assertEqual(completion["status"], "error")
        self.assertEqual(completion["id"], "aegis_9")
        self.assertEqual(completion["model"], "google/gemma-4-12b-qat")
        self.assertEqual(completion["reason"], "empty completion")
        self.assertEqual(completion["usage"].get("prompt_tokens"), 7)
        self.assertEqual(completion["requested_max_tokens"], 17)
        # Missing values stay unknown; nothing is deduced from counts and no hit_limit is invented.
        self.assertIsNone(completion["finish_reason"])
        self.assertIsNone(completion["token_limit_reached"])
        self.assertIsNone(completion["finish_reason_source"])
        self.assertNotIn("hit_limit", completion)
        self.assertEqual(len(completion["providers"]), 1)
        self.assertNotIn("fixture prompt", json.dumps(completion))

    def test_body_without_providers_stays_unknown(self):
        self.http.side_effect = urllib.error.HTTPError(lab.LLM_URL, 502, "shim", {}, io.BytesIO(b"not json"))
        with self.assertRaises(urllib.error.HTTPError) as caught:
            lab._ask("fixture", "fixture", max_tokens=17)
        self.assertEqual(caught.exception.completion,
                         {"finish_reason": None, "token_limit_reached": None,
                          "requested_max_tokens": 17, "providers": []})


if __name__ == "__main__": unittest.main()

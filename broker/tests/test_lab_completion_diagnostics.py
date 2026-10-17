"""Completion envelopes through the real _ask/parser path. Scratch stores; HTTP is a fixture, no models or folds."""
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bin"))
import chemistry_lab as lab
import vintos_claude_shim as shim


class CompletionDiagnostics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        # Repoint every workspace path, including optional tracing and future stores.
        old_ws = lab.WS
        for name, value in list(vars(lab).items()):
            if isinstance(value, str) and value.startswith(old_ws):
                p = patch.object(lab, name, str(root) + value[len(old_ws):])
                p.start(); self.addCleanup(p.stop)
        for p in (patch.object(lab, "_eliot", None),
                  patch.dict(os.environ, {"VINTOS_ELIOT_REQUIRED": "0"}),
                  patch("socket.socket.connect", side_effect=AssertionError("no network")),
                  patch.object(lab.subprocess, "run", side_effect=AssertionError("no subprocess"))):
            p.start(); self.addCleanup(p.stop)
        p = patch.object(lab.urllib.request, "urlopen")
        self.http = p.start(); self.addCleanup(p.stop)
        self.assertIs(lab.urllib.request.urlopen, self.http)
        self.assertTrue(lab.ROOT.startswith(self.tmp.name))
        self.assertTrue(lab.FAULTS.startswith(self.tmp.name))
        self.diag = Path(lab.ROOT) / "diagnostics"

    def reply(self, content, reason="stop", **fields):
        choice = {"message": {"content": content}}
        if reason != "MISSING": choice["finish_reason"] = reason
        data = {"choices": [choice], **fields}
        self.http.return_value = io.BytesIO(json.dumps(data).encode())
        return lab._ask("fixture system", "fixture prompt", max_tokens=17, temperature=0.25)

    def records(self):
        return [json.loads(p.read_text()) for p in self.diag.glob("*.events.json")]

    def terminal(self, reply):
        with self.assertRaises(lab.ModelJSONError) as caught:
            lab._json_object(reply)
        row = json.loads((self.diag / (caught.exception.evidence_id + ".events.json")).read_text())
        self.assertTrue(row["terminal"])
        self.assertNotIn("PRIVATE", str(caught.exception))
        return row, caught.exception

    def test_normal_completion_and_request_contract(self):
        reply = self.reply('{"a":1}', model="fixture-model", id="fixture-id",
                           usage={"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13})
        self.assertIsInstance(reply, str)
        self.assertEqual(lab._json_object(reply), {"a": 1})
        row = self.records()[0]
        self.assertEqual(row["events"], ["captured"])
        self.assertEqual(row["completion"], {"finish_reason": "stop", "token_limit_reached": False,
            "requested_max_tokens": 17, "model": "fixture-model", "id": "fixture-id",
            "usage": {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13},
            "token_budget_exhausted": False})
        args, kwargs = self.http.call_args
        self.assertEqual(args[0].full_url, lab.LLM_URL)
        self.assertEqual(kwargs, {"timeout": 150})
        self.assertEqual(json.loads(args[0].data), {"model": lab.LLM_MODEL, "max_tokens": 17,
            "temperature": 0.25, "messages": [{"role": "system", "content": "fixture system"},
                                               {"role": "user", "content": "fixture prompt"}]})

    def test_length_reason_survives_repair(self):
        reply = self.reply('{"a":"PRIVATE', "length")
        self.assertEqual(lab._json_object(reply), {"a": "PRIVATE"})
        row = self.records()[0]
        self.assertEqual(row["events"], ["captured", "strict_parse_failed", "repaired"])
        self.assertEqual(row["completion"]["finish_reason"], "length")
        self.assertIs(row["completion"]["token_limit_reached"], True)

    def test_escape_repair_and_complete_length_limited_object(self):
        self.assertEqual(lab._json_object(self.reply(r'{"a":"C:\Users"}', "stop")), {"a": r"C:\Users"})
        row = self.records()[0]
        self.assertEqual(row["events"][-1], "repaired")
        self.assertEqual(row["completion"]["finish_reason"], "stop")
        self.assertEqual(lab._json_object(self.reply('{"a":1}', "length")), {"a": 1})
        self.assertTrue(any(r["completion"]["token_limit_reached"] is True for r in self.records()))

    def test_malformed_json_retains_finish_reason_on_terminal_evidence(self):
        for reason, limited in (("stop", False), ("length", True), ("content_filter", False),
                                ("tool_calls", False), ("new_provider_condition", None)):
            with self.subTest(reason=reason):
                raw = '{\n"a": "PRIVATE",\n"b":\n???\n}'
                row, exc = self.terminal(self.reply(raw, reason))
                self.assertEqual(row["completion"]["finish_reason"], reason)
                self.assertIs(row["completion"]["token_limit_reached"], limited)
                self.assertEqual((self.diag / (exc.evidence_id + ".raw.txt")).read_text(), raw)
                lab._fault("fixture", exc)
        self.assertNotIn("PRIVATE", Path(lab.FAULTS).read_text())

    def test_missing_null_and_invalid_metadata_stay_unknown(self):
        for reason in ("MISSING", None, "", {"bad": "PRIVATE"}):
            with self.subTest(reason=reason):
                row, _ = self.terminal(self.reply("PRIVATE prose", reason, usage=None))
                self.assertIs(row["completion"]["token_limit_reached"], None)
        # Token count at the requested maximum is not proof of a token-limit stop.
        row, _ = self.terminal(self.reply("PRIVATE prose", "MISSING", usage={"completion_tokens": 17}))
        self.assertIsNone(row["completion"]["finish_reason"])
        self.assertIsNone(row["completion"]["token_limit_reached"])
        self.assertIs(row["completion"]["token_budget_exhausted"], True)
        row, _ = self.terminal("PRIVATE legacy string")
        self.assertEqual(row["completion"], {"finish_reason": None, "token_limit_reached": None})

    def test_null_content_keeps_completion_metadata(self):
        row, _ = self.terminal(self.reply(None, "tool_calls"))
        self.assertEqual(row["completion"]["finish_reason"], "tool_calls")

    def test_native_adapter_through_lab_preserves_actual_stop_and_unknown(self):
        for reason, limited in (("eosFound", False), ("maxPredictedTokensReached", True),
                                ("new_native_reason", None), (None, None)):
            with self.subTest(reason=reason):
                native = {"model_instance_id": "fixture-native", "output": [
                    {"type": "message", "content": "PRIVATE malformed"}],
                    "stats": {"input_tokens": 7, "total_output_tokens": 17, "reasoning_output_tokens": 0}}
                if reason is not None: native["stats"]["stop_reason"] = reason
                request = {"max_tokens": 17, "messages": [{"role": "user", "content": "fixture"}]}
                with patch.object(shim, "_post_json", return_value=(200, native, None)) as post:
                    result = shim.aegis_gemma_complete(request)
                sent = post.call_args.args[2]
                self.assertEqual(sent["reasoning"], "off")
                self.assertIs(sent["store"], False)
                self.assertEqual(sent["max_output_tokens"], 17)
                self.assertEqual(post.call_args.args[1], shim.AEGIS_GEMMA_URL)
                self.assertEqual(shim.provider_chain(request, "/gemma-aegis-local/v1/chat/completions"),
                                 ["aegis_gemma"])
                wire = json.loads(shim.openai_wrap(result))
                self.assertEqual(wire["choices"][0]["finish_reason"], reason)
                self.http.return_value = io.BytesIO(json.dumps(wire).encode())
                row, _ = self.terminal(lab._ask("fixture", "fixture", max_tokens=17))
                self.assertEqual(row["completion"]["finish_reason"], reason)
                self.assertIs(row["completion"]["token_limit_reached"], limited)
                self.assertIs(row["completion"]["token_budget_exhausted"], True)
                self.assertEqual(row["completion"]["finish_reason_source"],
                                 "stats.stop_reason" if reason else None)

    def test_native_adapter_top_level_reason_and_legacy_proxy(self):
        for key in ("stop_reason", "finish_reason"):
            native = {key: "length", "output": [{"type": "message", "content": "PRIVATE"}]}
            with patch.object(shim, "_post_json", return_value=(200, native, None)):
                result = shim.aegis_gemma_complete({"messages": []})
            self.assertEqual(result["finish_reason"], "length")
            self.assertEqual(result["finish_reason_source"], key)
        row, _ = self.terminal(self.reply("PRIVATE", "stop", provider="aegis_gemma"))
        self.assertIsNone(row["completion"]["finish_reason"])
        self.assertIsNone(row["completion"]["token_limit_reached"])

    def test_replies_do_not_share_metadata_even_when_parsed_out_of_order(self):
        first = self.reply("PRIVATE first", "length", id="first")
        second = self.reply("PRIVATE second", "stop", id="second")
        row2, _ = self.terminal(second)
        row1, _ = self.terminal(first)
        self.assertEqual((row1["completion"]["id"], row1["completion"]["finish_reason"]), ("first", "length"))
        self.assertEqual((row2["completion"]["id"], row2["completion"]["finish_reason"]), ("second", "stop"))

    def test_planner_retry_keeps_two_evidence_ids_and_original_limits(self):
        replies = [self.reply("PRIVATE prose", "length", id="first"),
                   self.reply("PRIVATE prose", "stop", id="second")]
        with patch.object(lab, "_ask", side_effect=replies) as ask:
            row, exc = self.terminal_plan()
        self.assertEqual(ask.call_count, 2)
        self.assertEqual(ask.call_args.kwargs, {"temperature": 0.3})
        rows = self.records()
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["completion"]["id"] for r in rows}, {"first", "second"})
        self.assertEqual(row["completion"]["id"], "second")
        self.assertNotIn("PRIVATE", Path(lab.FAULTS).read_text() + str(exc))

    def terminal_plan(self):
        with self.assertRaises(lab.ModelJSONError) as caught:
            lab._plan_raw("fixture", "fixture")
        exc = caught.exception
        return json.loads((self.diag / (exc.evidence_id + ".events.json")).read_text()), exc

    def test_allowlist_permissions_and_existing_size_limits(self):
        reply = self.reply('{"a":"' + "x" * (lab.DIAGNOSTIC_BYTES + 50), "length",
            id="i" * 100000, model="m" * 100000,
            usage={"prompt_tokens": "PRIVATE", "completion_tokens": True, "total_tokens": -1,
                   "extra": "PRIVATE"}, secret="PRIVATE", messages=["PRIVATE"])
        lab._json_object(reply)
        row = self.records()[0]
        self.assertEqual(len(row["completion"]["id"]), 256)
        self.assertEqual(row["completion"]["usage"], {})
        self.assertNotIn("PRIVATE", json.dumps(row))
        self.assertEqual(stat.S_IMODE(self.diag.stat().st_mode), 0o700)
        files = [p for p in self.diag.iterdir() if not p.name.startswith(".")]
        self.assertEqual(len(files), 3)  # no new evidence files for the pruner to count
        for p in files:
            self.assertLessEqual(p.stat().st_size, lab.DIAGNOSTIC_BYTES)
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)

    def test_storage_failures_preserve_parse_result_and_private_fault(self):
        good = self.reply('{"a":1}', "stop")
        bad = self.reply("PRIVATE prose", "length")
        with patch.object(lab.tempfile, "mkstemp", side_effect=OSError("PRIVATE disk error")):
            self.assertEqual(lab._json_object(good), {"a": 1})
            with self.assertRaises(lab.ModelJSONError) as caught: lab._json_object(bad)
        faults = Path(lab.FAULTS).read_text()
        self.assertIn(caught.exception.evidence_id, faults)
        self.assertNotIn("PRIVATE", faults + str(caught.exception))
        self.assertFalse(list(self.diag.glob(".evidence-*")))
        with patch.object(lab, "_ensure", side_effect=OSError("PRIVATE store unavailable")), \
                patch.object(lab, "_append", side_effect=OSError("PRIVATE fault store unavailable")):
            self.assertEqual(lab._json_object(good), {"a": 1})
            with self.assertRaises(lab.ModelJSONError) as caught: lab._json_object(bad)
        self.assertNotIn("PRIVATE", str(caught.exception))


if __name__ == "__main__": unittest.main()

#!/usr/bin/env python3
"""The creative call stays focused; optional machinery opens only by choice."""
import importlib.util, json, os, tempfile, types, unittest
from datetime import datetime
from unittest import mock

try:
    import requests  # noqa: F401
except ImportError:
    import sys
    sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
spec = importlib.util.spec_from_file_location("atelier_visit_focus_test",
    os.path.join(ROOT, "scripts", "atelier-visit.py"))
VISIT = importlib.util.module_from_spec(spec); spec.loader.exec_module(VISIT)
gate_spec = importlib.util.spec_from_file_location("atelier_gate_focus_test",
    os.path.join(ROOT, "scripts", "atelier-gate.py"))
GATE = importlib.util.module_from_spec(gate_spec); gate_spec.loader.exec_module(GATE)


class AtelierFocusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_store = VISIT.KNOCK_STORE
        VISIT.KNOCK_STORE = os.path.join(self.tmp.name, ".atelier-knock.json")

    def tearDown(self):
        VISIT.KNOCK_STORE = self.old_store
        self.tmp.cleanup()

    def test_optional_machinery_is_an_index_until_one_shelf_is_chosen(self):
        index = VISIT.materials_index()
        self.assertIn('shelf="media|quantum|connected_tools', index)
        self.assertNotIn("gmail.send_email", index)
        self.assertNotIn("protected_effects", index)
        seen = {}
        def ask(system, user, **_kwargs):
            seen["system"] = system; seen["user"] = user
            return '<piece kind="write">a provisional form</piece>'
        with mock.patch.object(VISIT, "plugin_block", return_value="FULL EXACT TOOL MENU"), \
             mock.patch.object(VISIT, "ask", side_effect=ask):
            out = VISIT.materials_loop("0123456789ab", "focused context",
                '<materials shelf="connected_tools">I need a source</materials>')
        self.assertIn("FULL EXACT TOOL MENU", seen["system"])
        self.assertIn("a provisional form", out)

    def test_piece_and_media_attributes_accept_either_quote_and_any_order(self):
        piece = VISIT._tag("<piece continues='old.md' kind='write'>new</piece>", "piece")
        self.assertEqual(piece["attrs"], {"continues": "old.md", "kind": "write"})
        image = VISIT._media_request("<image title='x' prompt='blue pressure'>night</image>")
        self.assertEqual(image["prompt"], "blue pressure")
        music = VISIT._media_request("<music duration='90' style='low strings' title='Return'>air</music>")
        self.assertEqual((music["title"], music["style"], music["duration"]),
                         ("Return", "low strings", 90))

    def test_knock_is_project_and_day_bound_then_consumed(self):
        row = {"day": datetime.now().date().isoformat(), "project": "0123456789ab",
               "words": "RETURN because the shape can move."}
        with open(VISIT.KNOCK_STORE, "w") as f: json.dump(row, f)
        self.assertIn("the shape can move", VISIT.knock_block("0123456789ab"))
        self.assertEqual(VISIT.knock_block("ffffffffffff"), "")
        VISIT.consume_knock("ffffffffffff")
        self.assertTrue(os.path.exists(VISIT.KNOCK_STORE))
        VISIT.consume_knock("0123456789ab")
        self.assertFalse(os.path.exists(VISIT.KNOCK_STORE))

    def test_gate_persists_only_an_accepted_return_without_real_calls(self):
        store = os.path.join(self.tmp.name, "memory", ".atelier-knock.json")
        calls = []
        class Reply:
            def __init__(self, body): self.body = body
            def json(self): return self.body
        def post(url, json=None, timeout=None):
            calls.append(url)
            if url.endswith("/door"): return Reply({"door": "dark", "why": "he left it held"})
            if url.endswith("/gate/knock"):
                return Reply({"ok": True, "project": "0123456789ab", "table_since": "t", "note": "sealed"})
            if url.endswith("/gate/decide"): return Reply({"ok": True})
            if url.endswith("/v1/chat/completions"):
                return Reply({"choices": [{"message": {"content": "RETURN because the form can move."}}]})
            raise AssertionError(url)
        with mock.patch.object(GATE, "KNOCK_STORE", store), \
             mock.patch.object(GATE.requests, "post", side_effect=post), \
             mock.patch.object(GATE, "voice", return_value="private voice"):
            self.assertEqual(GATE.main(), 0)
        with open(store) as handle: row = json.load(handle)
        self.assertEqual(row["project"], "0123456789ab")
        self.assertTrue(row["words"].startswith("RETURN"))
        self.assertEqual(os.stat(store).st_mode & 0o077, 0)
        self.assertFalse(any("ntfy" in url for url in calls))

    def test_no_practice_metrics_are_reintroduced(self):
        with open(os.path.join(ROOT, "scripts", "atelier-visit.py")) as handle:
            source = handle.read()
        self.assertNotIn("PRACTICE SO FAR", source)
        self.assertNotIn("days since the last piece", source.lower())
        self.assertIn("evidence, not orders", source)


if __name__ == "__main__": unittest.main(verbosity=2)

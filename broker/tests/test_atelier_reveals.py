#!/usr/bin/env python3
import importlib.util
import json
import os
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
spec = importlib.util.spec_from_file_location("atelier_reveals", os.path.join(ROOT, "scripts/atelier_reveals.py"))
AR = importlib.util.module_from_spec(spec); spec.loader.exec_module(AR)


class AtelierRevealTests(unittest.TestCase):
    def test_missing_is_honestly_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(AR.read_reveals(d), [])

    def test_only_revealed_allowlisted_fields_cross(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [{"artifact": "piece.md", "revealed_at": "2026-08-31T02:00:00Z",
                     "disclosure": "Here it is.", "content": "finished", "revealed": True,
                     "private_intent": "must never cross", "project_id": "sealed-id"},
                    {"artifact": "not-yet.md", "content": "sealed", "revealed": False}]
            with open(os.path.join(d, "atelier-reveals.json"), "w") as f: json.dump(rows, f)
            got = AR.read_reveals(d)
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0]["content"], "finished")
            self.assertNotIn("private_intent", got[0])
            self.assertNotIn("project_id", got[0])

    def test_malformed_is_not_false_empty(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "atelier-reveals.json"), "w") as f: f.write("{")
            with self.assertRaises(AR.RevealStoreError): AR.read_reveals(d)

    def test_legacy_at_becomes_revealed_at(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "atelier-reveals.json"), "w") as f:
                json.dump([{"artifact": "old.md", "content": "kept",
                            "at": "2026-08-31T01:00:00"}], f)
            self.assertEqual(AR.read_reveals(d)[0]["revealed_at"],
                             "2026-08-31T01:00:00")

    def test_server_route_is_authenticated(self):
        with open(os.path.join(ROOT, "bin/server.py")) as f: source = f.read()
        start = source.index('@app.get("/api/atelier/reveals")')
        block = source[start:start + 1600]
        self.assertIn('X-Vintos-Secret', block)
        self.assertIn('atelier_reveals.read_reveals', block)
        self.assertEqual(source.count('@app.get("/api/atelier/reveals")'), 1)


if __name__ == "__main__": unittest.main(verbosity=2)

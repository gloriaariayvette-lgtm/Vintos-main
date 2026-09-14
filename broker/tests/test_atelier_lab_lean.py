#!/usr/bin/env python3
"""A scratch Atelier choice leans both Lab planners and no choice changes nothing."""
import importlib.util, json, os, sys, tempfile, types, unittest
from unittest import mock

try: import requests  # noqa
except ImportError: sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


LEAN = load("atelier_lab_lean_test", os.path.join(ROOT, "scripts", "atelier_lab_lean.py"))
LAB = load("chemistry_lab_lean_test", os.path.join(ROOT, "scripts", "chemistry_lab.py"))
SESSION = load("chemistry_session_lean_test", os.path.join(ROOT, "scripts", "chemistry_session.py"))


class LeanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="atelier-lean-")
        self.old = (LEAN.STORE, LEAN.LOCK)
        LEAN.STORE = os.path.join(self.tmp.name, "memory", "chemistry-lab", "atelier-leans.jsonl")
        LEAN.LOCK = LEAN.STORE + ".lock"

    def tearDown(self):
        LEAN.STORE, LEAN.LOCK = self.old; self.tmp.cleanup()

    def test_dated_choice_reaches_orient_and_frontier_plan(self):
        row = LEAN.write("P-1", "root-1", "curiosity", "Ask what the blue fold keeps returning to")
        self.assertTrue(row["ok"]); self.assertEqual(LEAN.today()["lean_id"], row["lean_id"])
        seen = []
        answer = '{"uniprot_query":"reviewed:true","question":"blue folds?","why_now":"the lean"}'
        with mock.patch.object(LAB, "_ask", side_effect=lambda system, prompt, max_tokens=500: seen.append(prompt) or answer):
            inquiry = LAB._orient("SELF", LEAN.today())
        self.assertIn("blue fold", seen[0]); self.assertEqual(inquiry["atelier_lean_id"], row["lean_id"])

        plan_answer = '{"addressed_entry_ids":[],"experiment":"fold","parameters":{},"shots":512,"question":"blue?","why_this":"lean"}'
        async def frontier(*args, **kwargs): return plan_answer
        with mock.patch.object(SESSION, "_frontier", side_effect=frontier):
            plan = SESSION._plan("SELF", ["fold"], "claude", {}, [], LEAN.today())
        self.assertEqual(plan["atelier_lean_id"], row["lean_id"])
        self.assertEqual(plan["atelier_lean"], row["direction"])
        self.assertTrue(LEAN.STORE.startswith(self.tmp.name))

    def test_no_lean_preserves_the_old_prompt_shape(self):
        seen = []
        answer = '{"uniprot_query":"reviewed:true","question":"ordinary","why_now":"curiosity"}'
        with mock.patch.object(LAB, "_ask", side_effect=lambda system, prompt, max_tokens=500: seen.append(prompt) or answer):
            inquiry = LAB._orient("SELF", None)
        self.assertNotIn("ATELIER LEAN", seen[0]); self.assertNotIn("atelier_lean_id", inquiry)


if __name__ == "__main__": unittest.main(verbosity=2)

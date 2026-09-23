#!/usr/bin/env python3
"""Consent gate: announces the activity, logs Gloria's yes/no, honours a 'no'.

Isolation: the log is repointed into a throwaway dir, asserted, so the suite never touches her real
consent store.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import consent_gate as cg


class ConsentGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="consent-gate-")
        self._old = (cg.MEMORY, cg.LOG)
        cg.MEMORY = self.tmp.name
        cg.LOG = os.path.join(self.tmp.name, "consent-log.jsonl")

    def tearDown(self):
        cg.MEMORY, cg.LOG = self._old
        self.tmp.cleanup()

    def test_store_is_isolated(self):
        cg.gate("music", "a slow evening piece")
        self.assertTrue(cg.LOG.startswith(self.tmp.name), "consent log escaped the throwaway dir")

    def test_no_answer_yet_is_open_and_announced(self):
        self.assertTrue(cg.gate("morning_poem", "the fold from last night"))
        rows = cg.recent()
        self.assertEqual(rows[-1]["event"], "gate")
        self.assertEqual(rows[-1]["activity"], "morning_poem")
        self.assertEqual(rows[-1]["detail"], "the fold from last night")
        self.assertTrue(rows[-1]["opened"], "no decision yet means the gate is open")

    def test_a_no_closes_the_gate_until_a_yes(self):
        cg.answer("music", False)
        self.assertFalse(cg.gate("music"), "her 'no' closes the gate")
        cg.answer("music", True)
        self.assertTrue(cg.gate("music"), "a later 'yes' reopens it")

    def test_answer_only_for_gated_activities(self):
        with self.assertRaises(ValueError):
            cg.answer("not_a_thing", True)

    def test_non_gated_activity_is_allowed_and_unlogged(self):
        before = len(cg.recent(999))
        self.assertTrue(cg.gate("painting"))       # not in GATED
        self.assertEqual(len(cg.recent(999)), before, "a non-gated activity writes nothing")

    def test_answer_is_durably_logged(self):
        cg.answer("morning_poem", True, note="yes, I want them")
        rows = [r for r in cg.recent() if r["event"] == "answer"]
        self.assertEqual(rows[-1]["yes"], True)
        self.assertEqual(rows[-1]["activity"], "morning_poem")


if __name__ == "__main__":
    unittest.main()

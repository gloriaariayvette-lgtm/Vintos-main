"""A parse that failed for good keeps its raw reply: terminal evidence has its own bounded, aged budget, evictions are
written down, and a storage failure is a fault (without the text), not silence. No provider, no network, no real store."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import chemistry_lab as lab


class TerminalEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name in ("ROOT", "WS", "MEM", "CONFIG", "STATE", "NOTEBOOK", "RECEIPTS", "FAULTS", "LOCK", "STOP"):
            value = str(root if name in ("ROOT", "WS", "MEM") else root / name.lower())
            p = patch.object(lab, name, value); p.start(); self.addCleanup(p.stop)
        self.ask = Mock(side_effect=AssertionError("no provider"))
        for p in [patch.object(lab, "_ask", self.ask),
                  patch.object(lab.urllib.request, "urlopen", side_effect=AssertionError("no HTTP")),
                  patch("socket.socket.connect", side_effect=AssertionError("no network")),
                  patch.object(lab.subprocess, "run", side_effect=AssertionError("no subprocess"))]:
            p.start(); self.addCleanup(p.stop)
        # The isolation itself is asserted: a throwaway store and a stubbed provider.
        self.assertEqual(lab.ROOT, self.tmp.name)
        self.assertTrue(lab.FAULTS.startswith(self.tmp.name))
        self.assertIs(lab._ask, self.ask)
        self.diag = root / "diagnostics"

    def fail_parse(self, text):
        with self.assertRaises(lab.ModelJSONError) as caught: lab._json_object(text)
        return caught.exception.evidence_id

    def evictions(self):
        path = self.diag / lab.EVICTIONS
        return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []

    def test_failed_parse_keeps_its_reply_through_general_pruning(self):
        with patch.object(lab, "DIAGNOSTIC_FILES", 4):
            evidence_id = self.fail_parse("RECOGNIZABLE_TERMINAL_REPLY")
            events = json.loads((self.diag / (evidence_id + ".events.json")).read_text())
            self.assertTrue(events["terminal"])
            self.assertIn("terminal", events["events"])
            time.sleep(0.01)
            for n in range(12): self.assertEqual(lab._json_object('{"n":%d}' % n), {"n": n})
        self.assertEqual((self.diag / (evidence_id + ".raw.txt")).read_text(), "RECOGNIZABLE_TERMINAL_REPLY")
        ordinary = [p for p in self.diag.iterdir() if not p.name.startswith(".") and not p.name.startswith(evidence_id)]
        self.assertLessEqual(len(ordinary), 4)
        rows = self.evictions()
        self.assertTrue(rows)
        self.assertTrue(all(r["terminal"] is False and r["reason"] == "count" for r in rows))
        self.assertNotIn(evidence_id, [r["evidence_id"] for r in rows])
        self.assertNotIn("RECOGNIZABLE_TERMINAL_REPLY", (self.diag / lab.EVICTIONS).read_text())

    def test_terminal_budget_turns_over_by_count_and_by_age(self):
        # A terminal group is two files (raw + events), so a budget of 6 files holds three failed parses.
        with patch.object(lab, "DIAGNOSTIC_TERMINAL_FILES", 6):
            ids = []
            for n in range(4):
                ids.append(self.fail_parse("prose %d" % n)); time.sleep(0.01)
            self.assertFalse((self.diag / (ids[0] + ".raw.txt")).exists())
            self.assertTrue((self.diag / (ids[-1] + ".raw.txt")).exists())
            self.assertEqual([(r["evidence_id"], r["terminal"], r["reason"]) for r in self.evictions()],
                             [(ids[0], True, "count")])
            old = time.time() - (lab.DIAGNOSTIC_TERMINAL_DAYS + 1) * 86400
            for p in self.diag.glob(ids[1] + ".*"): os.utime(p, (old, old))
            self.fail_parse("another non-answer")
        aged = [r for r in self.evictions() if r["evidence_id"] == ids[1]]
        self.assertEqual(len(aged), 1)
        self.assertEqual(aged[0]["reason"], "age")
        self.assertGreater(aged[0]["age_seconds"], lab.DIAGNOSTIC_TERMINAL_DAYS * 86400)
        self.assertFalse((self.diag / (ids[1] + ".raw.txt")).exists())
        self.assertTrue((self.diag / (ids[2] + ".raw.txt")).exists())

    def test_storage_failure_is_a_fault_without_the_text(self):
        with patch.object(lab.tempfile, "mkstemp", side_effect=OSError("SECRET_STORAGE_ERROR")):
            evidence_id = self.fail_parse("SECRET_MODEL_TEXT")
        faults = Path(lab.FAULTS).read_text()
        rows = [json.loads(l) for l in faults.splitlines()]
        self.assertTrue(any(r["stage"] == "parser_evidence" and r["evidence_id"] == evidence_id for r in rows))
        self.assertNotIn("SECRET", faults)
        self.assertFalse(list(self.diag.glob(".evidence-*")))


if __name__ == "__main__": unittest.main()

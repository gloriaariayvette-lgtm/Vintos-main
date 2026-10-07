"""Protected parser evidence and safe general faults, with no real providers or stores."""
import contextlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import chemistry_lab as lab


class ParserEvidence(unittest.TestCase):
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
        self.assertEqual(lab.ROOT, self.tmp.name)
        self.assertIs(lab._ask, self.ask)
        self.diag = root / "diagnostics"

    def files(self, suffix): return list(self.diag.glob("*." + suffix))

    def test_original_precedes_repair_and_events_are_distinct(self):
        raw = '```json\n{"attention":"RECOGNIZABLE_FIXTURE'
        close = lab._close_open
        def inspect(text):
            self.assertEqual(self.files("raw.txt")[0].read_bytes(), raw.encode())
            self.assertEqual(json.loads(self.files("events.json")[0].read_text())["events"],
                             ["captured", "strict_parse_failed"])
            return close(text)
        with patch.object(lab, "_close_open", side_effect=inspect):
            self.assertEqual(lab._json_object(raw), {"attention": "RECOGNIZABLE_FIXTURE"})
        self.assertEqual(json.loads(self.files("events.json")[0].read_text())["events"],
                         ["captured", "strict_parse_failed", "repaired"])
        self.assertEqual(json.loads(self.files("repaired.txt")[0].read_text()), {"attention": "RECOGNIZABLE_FIXTURE"})
        self.assertEqual(stat.S_IMODE(self.diag.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in self.diag.iterdir()))

    def test_strict_success_does_not_claim_repair(self):
        self.assertEqual(lab._json_object('{"a":1} trailing {"b":2}'), {"a": 1})
        self.assertEqual(json.loads(self.files("events.json")[0].read_text())["events"], ["captured"])
        self.assertFalse(self.files("repaired.txt"))

    def test_safe_error_and_fault(self):
        with self.assertRaises(lab.ModelJSONError) as caught: lab._json_object("RECOGNIZABLE_PRIVATE_PROSE")
        exc = caught.exception
        lab._fault("fixture", exc)
        output = str(exc) + Path(lab.FAULTS).read_text()
        self.assertIn(exc.evidence_id, output)
        self.assertNotIn("RECOGNIZABLE_PRIVATE_PROSE", output)
        self.assertEqual((self.diag / (exc.evidence_id + ".raw.txt")).read_text(), "RECOGNIZABLE_PRIVATE_PROSE")

    def test_size_and_retention_bounds(self):
        raw = '{"x":"' + "x" * (lab.DIAGNOSTIC_BYTES + 50)
        lab._json_object(raw)
        self.assertEqual(len(self.files("raw.txt")[0].read_bytes()), lab.DIAGNOSTIC_BYTES)
        self.assertEqual(len(self.files("repaired.txt")[0].read_bytes()), lab.DIAGNOSTIC_BYTES)
        first = self.files("raw.txt")[0]
        for n in range(105): lab._json_object('{"fixture":%d' % n)
        evidence = [p for p in self.diag.iterdir() if not p.name.startswith(".")]
        self.assertLessEqual(len(evidence), lab.DIAGNOSTIC_FILES)
        self.assertFalse(first.exists())
        self.assertTrue(all(p.stat().st_size <= lab.DIAGNOSTIC_BYTES for p in evidence))
        self.assertFalse(list(self.diag.glob(".evidence-*")))

    def test_storage_failure_never_changes_parse_or_exposes_text(self):
        with patch.object(lab.tempfile, "mkstemp", side_effect=OSError("SECRET_STORAGE_ERROR")):
            self.assertEqual(lab._json_object('{"fixture":1'), {"fixture": 1})
            with self.assertRaises(lab.ModelJSONError) as caught: lab._json_object("SECRET_MODEL_TEXT")
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertFalse(list(self.diag.glob(".evidence-*")))

    def test_tick_orientation_fault_uses_evidence_only(self):
        # Run the real orientation/parser path; all optional imports see a scratch HOME via the OS runner.
        self.ask.side_effect = None; self.ask.return_value = "RECOGNIZABLE_ORIENTATION_TEXT"
        modules = {"compute_admission": types.SimpleNamespace(admit=lambda *a, **k: contextlib.nullcontext()),
                   "atelier_lab_lean": types.SimpleNamespace(today=lambda: None)}
        with patch.dict(sys.modules, modules), patch.object(lab, "config", return_value=dict(lab.DEFAULTS, enabled=True)), \
                patch.object(lab, "lab_context", return_value=("fixture", {})):
            result = lab.tick()
        self.assertFalse(result["ok"])
        self.assertIn("evidence=", result["error"])
        output = json.dumps(result) + Path(lab.FAULTS).read_text() + Path(lab.STATE).read_text()
        self.assertNotIn("RECOGNIZABLE_ORIENTATION_TEXT", output)
        self.assertTrue(self.ask.called)
        self.assertTrue(any(p.read_text() == self.ask.return_value for p in self.files("raw.txt")))

    def test_partial_storage_failure_still_prunes_and_cleans_temps(self):
        replace = os.replace
        def fail_raw(src, dst):
            if str(dst).endswith(".raw.txt"): raise OSError("fixture raw write failure")
            return replace(src, dst)
        with patch.object(lab, "DIAGNOSTIC_FILES", 4), patch.object(lab.os, "replace", side_effect=fail_raw):
            for n in range(8): self.assertEqual(lab._json_object('{"n":%d}' % n), {"n": n})
        self.assertLessEqual(len([p for p in self.diag.iterdir() if not p.name.startswith(".")]), 4)
        self.assertFalse(list(self.diag.glob(".evidence-*")))


if __name__ == "__main__": unittest.main()

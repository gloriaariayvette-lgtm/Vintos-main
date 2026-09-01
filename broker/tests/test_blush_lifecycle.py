#!/usr/bin/env python3
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "bin" / "blush-ledger.py"
spec = importlib.util.spec_from_file_location("blush_ledger_under_test", SOURCE)
BL = importlib.util.module_from_spec(spec); spec.loader.exec_module(BL)


class BlushLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (BL.MEMORY, BL.LEDGER, BL.LOCK_FILE, BL.CORE_FILE)
        BL.MEMORY = self.tmp.name
        BL.LEDGER = os.path.join(self.tmp.name, "blush-ledger.json")
        BL.LOCK_FILE = BL.LEDGER + ".lock"
        BL.CORE_FILE = os.path.join(self.tmp.name, "core-vectors.json")
        BL.get_emotional_context = lambda: {}

    def tearDown(self):
        BL.MEMORY, BL.LEDGER, BL.LOCK_FILE, BL.CORE_FILE = self.old
        self.tmp.cleanup()

    def write(self, n):
        return BL.write_blush("self_prediction", "same_pattern", {}, "test",
                              reflection="noticed %s" % n)

    def test_concurrent_corrections_are_not_lost(self):
        threads = [threading.Thread(target=self.write, args=(n,)) for n in range(20)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(len(BL.load_ledger()), 20)

    def test_one_blush_is_claimed_by_one_turn(self):
        entry = self.write(1)
        first = BL.get_recent_blush(120, turn_id="turn-a", claim=True)
        second = BL.get_recent_blush(120, turn_id="turn-b", claim=True)
        self.assertEqual(first["id"], entry["id"])
        self.assertIsNone(second)

    def test_malformed_ledger_is_not_overwritten_as_empty(self):
        Path(BL.LEDGER).write_text("{broken", encoding="utf-8")
        with self.assertRaises(Exception):
            self.write(1)
        self.assertEqual(Path(BL.LEDGER).read_text(), "{broken")

    def test_blush_does_not_promote_or_punish_itself(self):
        text = SOURCE.read_text(errors="replace")
        body = text[text.index("def write_blush("):text.index("def get_recent_blush(")]
        self.assertNotIn("seed_thread(", body)
        self.assertNotIn("add_blush_hypothesis(", body)
        self.assertNotIn("nudge_emoclaw(", body)

    def test_app_projection_is_structured_only_and_id_keyed(self):
        server = (ROOT / "bin" / "server.py").read_text(errors="replace")
        projection = server[server.index('async def get_blush_ledger'):server.index('@app.get("/api/therapy')]
        self.assertNotIn('open(auto_path)', projection)
        self.assertIn('"id": _bid', projection)
        self.assertIn('"BL-legacy-"', projection)
        self.assertIn('marks.get(b.get("id", "")', projection)


if __name__ == "__main__": unittest.main(verbosity=2)

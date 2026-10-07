#!/usr/bin/env python3
"""Synthetic occupancy only; no devices, shared state, senders or authority calls."""
import concurrent.futures
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import mmwave_presence as M


class Tests(unittest.TestCase):
    def setUp(self):
        self.block = patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden"))
        self.block.start(); self.addCleanup(self.block.stop)
        self.state = {}

    def send(self, value, at, now=None):
        self.state, result = M.update(self.state, {"occupied": value, "observed_at": at}, at if now is None else now)
        return result

    def test_strict_boolean_and_timestamp_validation(self):
        for value in [0, 1, "true", "false", [], {}]:
            self.assertFalse(self.send(value, 1)["accepted"])
        for at in [True, "1", float("nan"), float("inf")]:
            self.assertFalse(self.send(True, at, now=10)["accepted"])
        self.assertEqual(self.state, {})

    def test_baseline_bounce_change_and_unknown_recovery(self):
        self.assertEqual(self.send(False, 1)["reason"], "debouncing")
        self.assertEqual(self.send(False, 2)["reason"], "baseline")
        self.assertEqual(self.send(True, 3)["reason"], "debouncing")
        self.assertEqual(self.send(False, 4)["reason"], "unchanged")
        self.assertEqual(self.send(True, 5)["reason"], "debouncing")
        event = self.send(True, 6)["event"]
        self.assertEqual(event["sensor"], "mmwave_presence")
        self.assertEqual(event["description"], "room occupancy detected")
        self.assertEqual(event["expires_at"], 126)
        self.assertIsNone(self.send(None, 7)["event"])
        self.assertIsNone(self.send(False, 8)["event"])
        self.assertEqual(self.send(False, 9)["reason"], "baseline")

    def test_stale_future_order_and_outage(self):
        self.send(False, 1); self.send(False, 2)
        before = dict(self.state)
        self.assertEqual(self.send(True, 1, now=3)["reason"], "out_of_order")
        self.assertEqual(self.state, before)
        self.assertEqual(self.send(True, 5, now=3)["reason"], "future")
        self.assertEqual(self.state, before)
        self.assertEqual(self.send(True, 3, now=40)["reason"], "stale")
        self.assertIsNone(self.state["occupied"])
        self.send(True, 41)
        self.assertEqual(self.send(True, 42)["reason"], "baseline")
        self.send(False, 80)
        self.assertEqual(self.send(False, 81)["reason"], "baseline")

    def test_two_changes_per_hour(self):
        self.send(False, 1); self.send(False, 2)
        self.send(True, 3); self.assertEqual(self.send(True, 4)["reason"], "changed")
        self.send(False, 5); self.assertEqual(self.send(False, 6)["reason"], "changed")
        self.send(True, 7); self.assertEqual(self.send(True, 8)["reason"], "rate_limited")
        self.assertEqual(len(self.state["reactions"]), 2)

    def test_independent_store_concurrent_duplicate_delivered_once(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "mmwave-presence.json"
            self.assertTrue(path.is_relative_to(Path(td)))
            for value, at in [(False, 1), (False, 2), (True, 3)]:
                M.intake({"occupied": value, "observed_at": at}, state_path=path, now=at)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: M.intake({"occupied": True, "observed_at": 4}, state_path=path, now=4), range(8)))
            self.assertEqual(sum(r["event"] is not None for r in results), 1)
            self.assertTrue(json.loads(path.read_text())["occupied"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                M.intake({"occupied": True, "observed_at": 5}, state_path=Path(td)/"home-presence.json", now=5)


if __name__ == "__main__":
    unittest.main()

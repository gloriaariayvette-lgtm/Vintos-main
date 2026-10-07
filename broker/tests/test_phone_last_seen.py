"""Approved last-seen semantics. Synthetic state only; no presence snapshots or probes."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import home_presence as hp


class LastSeen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.load = Mock(return_value={})
        for p in [patch.object(hp, "WS", self.tmp.name), patch.object(hp, "MEMORY", self.tmp.name),
                  patch.object(hp, "STATE", str(Path(self.tmp.name) / "state.json")),
                  patch.object(hp, "CONFIG", str(Path(self.tmp.name) / "config.json")),
                  patch.object(hp, "_load", self.load),
                  patch.object(hp, "probe", side_effect=AssertionError("no probe")),
                  patch.object(hp.subprocess, "run", side_effect=AssertionError("no subprocess")),
                  patch("socket.socket.connect", side_effect=AssertionError("no network"))]:
            p.start(); self.addCleanup(p.stop)
        self.assertIs(hp._load, self.load)
        self.assertTrue(Path(hp.STATE).is_relative_to(self.tmp.name))

    def line(self, state, now):
        self.load.return_value = state
        with patch.object(hp.time, "time", return_value=now): return hp.context_line()

    def test_hit_and_misses_keep_separate_timestamps(self):
        state = hp.decide({}, True, now=1000)
        self.assertEqual(state["last_seen"], 1000)
        for now in [1100, 1200, 1300]:
            state = hp.decide(state, False, now=now)
            self.assertEqual(state["last_seen"], 1000)
            self.assertEqual(state["checked"], now)
            self.assertTrue(state["home"])

    def test_age_increases_despite_new_checks(self):
        state = hp.decide({}, True, now=1000)
        self.assertEqual(self.line(state, 1000), "Phone last detected on the house Wi-Fi 0 seconds ago.")
        state = hp.decide(state, False, now=1300)
        self.assertEqual(self.line(state, 1300), "Phone last detected on the house Wi-Fi 300 seconds ago. Latest check did not detect it.")
        self.assertIn("400 seconds ago", self.line(state, 1400))

    def test_freshness_uses_detection_and_includes_900_seconds(self):
        state = hp.decide(hp.decide({}, True, now=1000), False, now=1900)
        self.assertEqual(hp.FRESH_S, 900)
        self.assertIn("900 seconds ago", self.line(state, 1900))
        self.assertEqual(self.line(state, 1901), "")

    def test_fourth_miss_clears_and_new_hit_resets(self):
        self.assertEqual(hp.ABSENT_AFTER, 4)
        state = hp.decide({}, True, now=1000)
        for n in range(4): state = hp.decide(state, False, now=1100 + n)
        self.assertFalse(state["home"]); self.assertEqual(state["last_seen"], 1000)
        self.assertEqual(self.line(state, 1200), "")
        state = hp.decide(state, True, now=1300)
        self.assertEqual(state["last_seen"], 1300); self.assertEqual(state["misses"], 0)
        self.assertNotIn("did not detect", self.line(state, 1300))

    def test_legacy_state_is_unknown_until_new_hit(self):
        state = {"home": True, "checked": 1000, "misses": 0}
        self.assertEqual(self.line(state, 1000), "")
        state = hp.decide(state, False, now=1100)
        self.assertNotIn("last_seen", state)
        self.assertEqual(self.line(state, 1100), "")
        self.assertIn("0 seconds ago", self.line(hp.decide(state, True, now=1200), 1200))

    def test_invalid_timestamps_and_state_fail_silently(self):
        good = {"home": True, "last_seen": 1000, "checked": 1100}
        for field in ["last_seen", "checked"]:
            for bad in [None, "unknown", "1000", True, float('nan'), float('inf'), -1, 0, 1300, 10**400]:
                with self.subTest(field=field, bad=bad): self.assertEqual(self.line(dict(good, **{field: bad}), 1200), "")
        self.assertEqual(self.line(dict(good, checked=900), 1200), "")
        for bad in [None, [], "invalid", {}, {"home": "true", "last_seen": 1000, "checked": 1000}]:
            self.assertEqual(self.line(bad, 1200), "")

    def test_no_location_or_probability_claims(self):
        state = hp.decide(hp.decide({}, True, now=1000), False, now=1100)
        line = self.line(state, 1200).lower()
        for forbidden in ['gloria', 'she is', 'she left', 'probability', 'confidence', '%', 'bedroom', 'living room']:
            self.assertNotIn(forbidden, line)


if __name__ == '__main__': unittest.main()

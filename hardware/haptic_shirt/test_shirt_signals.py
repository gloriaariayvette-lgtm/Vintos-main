import asyncio
import json
from pathlib import Path
import unittest

from shirt import Shirt
from shirt_signals import MEANINGS, plan
from shirt_prompt import render

CHANNELS = {v["zone"]: int(k) for k, v in json.loads(
    (Path(__file__).parent / "body_zone_map.json").read_text())["mosfet_channels"].items()}


class SignalTests(unittest.TestCase):
    def test_all_signals_fit_hardware_budget_and_expire(self):
        for name in MEANINGS:
            for side in ("right", "left", "both"):
                events, end = plan(name, CHANNELS, side, peak=20)
                running = {}
                for t, cmd in events:
                    running = {k: v for k, v in running.items() if v[0] > t + .00001}
                    kind, target, value, ms = cmd.split()
                    value, ms = int(value), int(ms)
                    self.assertTrue(0 < ms <= 2000)
                    self.assertTrue(0 <= value <= (4095 if kind == "pulse" else 127))
                    key = kind, target
                    if value:
                        running[key] = t + ms/1000, 1 if kind == "pulse" else 2
                    else:
                        running.pop(key, None)
                    self.assertLessEqual(sum(v[1] for v in running.values()), 4, (name, side, t))
                self.assertGreaterEqual(end + .00001, max(
                    t + int(cmd.split()[3])/1000 for t, cmd in events))

    def test_rising_signal_reaches_wrist_then_collarbone(self):
        for side in ("right", "left"):
            events, _ = plan("wrist_to_collarbone", CHANNELS, side)
            self.assertEqual([int(cmd.split()[1]) for _, cmd in events], [
                CHANNELS[f"{side}_{p}"] for p in ("wrist", "elbow", "upper_arm", "collarbone")])

    def test_taps_have_three_separate_onsets(self):
        events, _ = plan("three_taps", CHANNELS)
        self.assertEqual(len(events), 3)
        for (t, cmd), (nxt, _) in zip(events, events[1:]):
            self.assertGreater(nxt-t, int(cmd.split()[3])/1000)

    def test_missing_mapping_fails_before_playback(self):
        with self.assertRaises(ValueError):
            plan("wrist_to_collarbone", {})

    def test_prompt_requires_fresh_live_response(self):
        live = {"ready": True, "zones": list(CHANNELS)}
        self.assertEqual(render(live), "")
        self.assertEqual(render(None, fresh=True), "")
        self.assertEqual(render({"ready": False}, fresh=True), "")
        shown = render(live, fresh=True)
        for meaning in MEANINGS.values(): self.assertIn(meaning, shown)
        self.assertIn("3 seconds", shown)

    def test_serial_failure_still_attempts_stop(self):
        class Fake(Shirt):
            def command(self, text, wait=.07):
                calls.append(text)
                if text.startswith("level "):
                    raise RuntimeError("simulated failed write")
                return ""
        calls = []
        with self.assertRaises(RuntimeError):
            Fake().pattern("chest", "wave3", .01, 10)
        self.assertEqual(calls[-1], "stop")

    def test_unanswered_probe_has_no_context(self):
        class Fake(Shirt):
            def command(self, *args):
                return ""
        self.assertEqual(Fake().context(), "")


if __name__ == "__main__":
    unittest.main()

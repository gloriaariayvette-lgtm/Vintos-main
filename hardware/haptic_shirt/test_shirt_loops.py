import asyncio
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import playback_control
import shirt
import shirt_ble
from shirt_prompt import render


class Clock:
    def __init__(self): self.now = 0.
    def monotonic(self): return self.now
    def sleep(self, delay): self.now += delay
    async def asleep(self, delay): self.sleep(delay)


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = patch.object(playback_control, "RUNTIME", Path(self.temp.name)/"runtime")
        self.runtime.start()
    def tearDown(self):
        self.runtime.stop()
        self.temp.cleanup()

    def test_loop_duration_is_exactly_three_minutes(self):
        self.assertEqual(playback_control.duration(None, True), 180)
        with self.assertRaises(ValueError): playback_control.duration(181, False)
        with self.assertRaises(ValueError): playback_control.duration(5, True)

    def test_bluetooth_loop_expires_and_never_leases_past_deadline(self):
        clock, calls = Clock(), []
        class Fake(shirt_ble.WirelessShirt):
            def __init__(self): self.client = types.SimpleNamespace(is_connected=True)
            async def command(self, text): calls.append((clock.now, text)); return {}
        with patch.object(shirt_ble.time, "monotonic", clock.monotonic), patch.object(shirt_ble.asyncio, "sleep", clock.asleep):
            asyncio.run(Fake().pattern("chest", "wave", None, 20, loop=True))
        self.assertAlmostEqual(clock.now, 180)
        self.assertEqual(calls[-1][1], "stop")
        samples = [(t, s.split()) for t, s in calls if s.startswith("level ")]
        self.assertGreater(len(samples), 500)
        for at, parts in samples:
            self.assertLessEqual(at+int(parts[3])/1000, 180.001)
            self.assertTrue(0 < int(parts[3]) <= 2000)

    def test_stop_cancels_loop_without_restarting_it(self):
        clock, calls = Clock(), []
        class Fake(shirt_ble.WirelessShirt):
            def __init__(self): self.client = types.SimpleNamespace(is_connected=True)
            async def command(self, text):
                calls.append(text)
                if sum(s.startswith("level ") for s in calls) == 3:
                    playback_control.request_stop()
                return {}
        with patch.object(shirt_ble.time, "monotonic", clock.monotonic), patch.object(shirt_ble.asyncio, "sleep", clock.asleep):
            asyncio.run(Fake().pattern("both", "wave", None, 20, loop=True))
        self.assertEqual(sum(s.startswith("level ") for s in calls), 3)
        self.assertEqual(calls[-1], "stop")
        self.assertLess(clock.now, 1)
        self.assertTrue(playback_control.playback_idle())

    def test_disconnect_does_not_reconnect_or_resume_loop(self):
        clock, calls = Clock(), []
        class Fake(shirt_ble.WirelessShirt):
            def __init__(self): self.client = types.SimpleNamespace(is_connected=True)
            async def command(self, text):
                calls.append(text)
                if text.startswith("level "):
                    self.client.is_connected = False
                    raise RuntimeError("radio disconnected")
                return {}
        with patch.object(shirt_ble.time, "monotonic", clock.monotonic), patch.object(shirt_ble.asyncio, "sleep", clock.asleep):
            with self.assertRaisesRegex(RuntimeError, "radio disconnected"):
                asyncio.run(Fake().pattern("chest", "wave", None, 20, loop=True))
        self.assertEqual(len(calls), 2)
        self.assertTrue(playback_control.playback_idle())

    def test_serial_loop_has_same_duration_and_stop(self):
        clock, calls = Clock(), []
        class Fake(shirt.Shirt):
            def command(self, text, wait=.07):
                calls.append((clock.now, text))
                return "LEVEL chest " if text.startswith("level ") else "all off"
        with patch.object(shirt.time, "monotonic", clock.monotonic), patch.object(shirt.time, "sleep", clock.sleep):
            Fake().pattern("chest", "wave", None, 20, loop=True)
        self.assertAlmostEqual(clock.now, 180)
        self.assertEqual(calls[-1][1], "stop")

    def test_second_playback_cannot_take_over_running_loop(self):
        with playback_control.Playback() as owner:
            with self.assertRaises(RuntimeError):
                with playback_control.Playback(): pass
            self.assertFalse(owner.cancelled())
            playback_control.request_stop()
            self.assertTrue(owner.cancelled())

    def test_repeated_signal_truncates_last_cycle_at_three_minutes(self):
        clock, calls = Clock(), []
        class Fake(shirt_ble.WirelessShirt):
            def __init__(self): self.client = types.SimpleNamespace(is_connected=True)
            async def command(self, text):
                calls.append((clock.now, text))
                return {"zones": [], "channels": []}
        with patch.object(shirt_ble.time, "monotonic", clock.monotonic), patch.object(shirt_ble.asyncio, "sleep", clock.asleep):
            asyncio.run(Fake().signal("three_taps", "right", "chest", 10, loop=True))
        self.assertAlmostEqual(clock.now, 180)
        self.assertEqual(calls[-1][1], "stop")
        for at, text in calls:
            if text.startswith("level "):
                self.assertLessEqual(at+int(text.split()[3])/1000, 180.001)

    def test_prompt_describes_loops_only_when_live(self):
        self.assertEqual(render(None, fresh=True), "")
        text = render({"ready": True, "zones": ["right_wrist"]}, fresh=True)
        self.assertIn("best for looping", text)
        self.assertIn("3 minutes (180 seconds)", text)


if __name__ == "__main__": unittest.main()

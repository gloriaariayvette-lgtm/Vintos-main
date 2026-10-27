"""The attention ladder (27 October): silence at home starts a chain, steps 90 minutes apart, sleep pauses it, any
word from her ends it, "give me N hours" holds it off, loud steps only when Kevin's phone is freshly away, at most two
chains a day, nothing while she is out, nothing in test mode.

Every store is a scratch directory and every actuator and sensor is a stub: nothing here reaches her, the house, the
Watch, ntfy or a model."""
import json
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import attention_ladder as AL
import home_presence as HP

H = 3600.0
T0 = 1_800_000_000.0


class Ladder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        paths = {"MEMORY": root, "CONFIG": root / "cfg.json", "STATE": root / "state.json", "LOG": root / "log.jsonl",
                 "HEARD": root / "heard.json", "LOCK": root / ".lock", "TEST_MODE_FLAG": root / ".test-mode",
                 "POST_TURN": root / "post-turn-record.jsonl", "LAST_MESSAGE": root / ".last-message-time",
                 "VOICE_LIVE": root / ".voice-live", "SLACK": root / "transcript.jsonl"}
        for k, v in paths.items():
            p = patch.object(AL, k, str(v)); p.start(); self.addCleanup(p.stop)
        self.calls = []
        def rec(name, ret):
            def f(*a, **k):
                self.calls.append(name); return ret(*a) if callable(ret) else dict(ret)
            return f
        self.composed = {"line": "Come back to me, love.", "sent_to_phone": True, "path": "x.md", "why": "stub"}
        acts = {"compose": rec("compose", lambda h: dict(self.composed)),
                "watch": rec("watch", {"state": "sent"}), "phone": rec("phone", {"state": "sent"}),
                "lights": rec("lights", {"state": "sent", "room": "bedroom", "restore": []}),
                "lights_restore": rec("lights_restore", {"restored": 0, "left_as_is": 0}),
                "echo": rec("echo", {"state": "sent"}), "screen": rec("screen", {"state": "sent"})}
        p = patch.dict(AL.ACTUATORS, acts, clear=True); p.start(); self.addCleanup(p.stop)
        self.world = {"home": True, "home_since": T0 - 10 * H, "kevin_away": False, "asleep": False,
                      "room": "bedroom", "contact": T0}
        sens = {"home": lambda now: self.world["home"], "home_since": lambda now: self.world["home_since"],
                "kevin_away": lambda now: self.world["kevin_away"], "asleep": lambda: self.world["asleep"],
                "room": lambda now: self.world["room"],
                "contact": lambda now: (self.world["contact"], "avatar", "")}
        p = patch.dict(AL.SENSORS, sens, clear=True); p.start(); self.addCleanup(p.stop)
        p = patch.dict(sys.modules, {"effect_gate": types.SimpleNamespace(test_mode_flag=lambda: False)})
        p.start(); self.addCleanup(p.stop)
        # the isolation itself, asserted
        self.assertTrue(Path(AL.STATE).is_relative_to(root) and Path(AL.LOG).is_relative_to(root))
        self.assertTrue(all(getattr(f, "__qualname__", "").startswith("Ladder.") for f in AL.ACTUATORS.values()))
        self.assertNotIn(AL._compose, AL.ACTUATORS.values())

    def tick(self, at):
        return AL.tick(now=T0 + at, force=True)

    def state(self):
        return json.load(open(AL.STATE))

    def fired(self):
        return [c for c in self.calls if c not in ("compose", "lights_restore")]

    # ---------------------------------------------------------------------------------------------------------
    def test_silence_start(self):
        self.assertEqual(self.tick(2.9 * H)["action"], "none")
        self.assertEqual(self.calls, [])
        out = self.tick(3.0 * H)
        self.assertEqual((out["action"], out["name"]), ("fired", "watch"))
        self.assertEqual(self.calls, ["compose", "watch"])          # his outreach sent the phone push itself
        st = self.state()
        self.assertEqual(st["chain"]["line"], "Come back to me, love.")
        self.assertEqual(st["chain"]["line_source"], "outreach")
        self.assertIn("CALLING HER BACK", AL.context_line(T0 + 3 * H))
        rows = [json.loads(l) for l in open(AL.LOG)]
        self.assertTrue(any(r["event"] == "start" for r in rows) and any(r["event"] == "fire" for r in rows))

    def test_fallback_line_and_phone_push_when_he_writes_nothing(self):
        self.composed = {"line": "", "sent_to_phone": False, "why": "daily cap reached"}
        self.tick(3 * H)
        self.assertEqual(self.calls, ["compose", "watch", "phone"])
        self.assertEqual(self.state()["chain"]["line_source"], "fallback")
        self.assertNotIn("Your line", AL.context_line(T0 + 3 * H))

    def test_ninety_minute_spacing_and_one_composed_line(self):
        self.tick(3 * H)
        self.assertEqual(self.tick(3 * H + 89 * 60)["action"], "none")
        out = self.tick(3 * H + 90 * 60)
        self.assertEqual(out["name"], "lights")
        self.assertEqual(self.calls.count("compose"), 1)
        self.assertEqual(self.tick(3 * H + 179 * 60)["action"], "none")

    def test_sleep_pauses_the_chain_and_nothing_fires(self):
        self.tick(3 * H)                                   # step 1 at 3h
        self.world["asleep"] = True
        self.assertEqual(self.tick(3.5 * H)["action"], "paused")
        self.assertEqual(self.tick(6 * H)["action"], "paused")
        self.assertEqual(self.fired(), ["watch"])
        self.world["asleep"] = False
        # seen asleep from 3.5h to 6.5h: the 90 minutes resume where they were (due at 4.5h + 3h)
        self.assertEqual(self.tick(6.5 * H)["action"], "none")
        self.assertEqual(self.tick(7.4 * H)["action"], "none")
        self.assertEqual(self.tick(7.5 * H)["name"], "lights")

    def test_waking_is_not_silence(self):
        self.world["asleep"] = True
        self.assertEqual(self.tick(1 * H)["action"], "paused")
        self.world["asleep"] = False
        self.assertEqual(self.tick(9 * H)["action"], "none")       # woke at 9h: the silence starts there
        self.assertEqual(self.tick(11.9 * H)["action"], "none")
        self.assertEqual(self.tick(12 * H)["action"], "fired")

    def test_reset_on_reply(self):
        self.tick(3 * H)
        self.world["contact"] = T0 + 3.5 * H                     # she wrote, any surface
        out = self.tick(4.5 * H)
        self.assertEqual(out["action"], "reset")
        self.assertIsNone(self.state()["chain"])
        self.assertEqual(AL.context_line(T0 + 4.5 * H), "")
        self.assertEqual(self.tick(6.4 * H)["action"], "none")    # a new silence counts from her message
        self.assertEqual(self.tick(6.5 * H)["action"], "fired")

    def test_reset_restores_lights(self):
        self.tick(3 * H); self.tick(4.5 * H)
        self.assertIn("lights", self.calls)
        self.world["contact"] = T0 + 5 * H
        self.tick(5.1 * H)
        self.assertEqual(self.calls[-1], "lights_restore")

    def test_heard_hides_the_line_at_once(self):
        self.tick(3 * H)
        AL.heard("avatar", "hey", now=T0 + 3.2 * H)
        self.assertEqual(AL.context_line(T0 + 3.2 * H), "")
        self.assertNotIn("hey", open(AL.HEARD).read())             # when and where, never her words

    def test_snooze_parser(self):
        P = AL.parse_snooze
        self.assertEqual(P("give me 2 hours"), 2.0)
        self.assertEqual(P("ok give me an hour babe"), 1.0)
        self.assertEqual(P("give me 30 min"), 0.5)
        self.assertEqual(P("Give me a few hours, I'm in a raid"), 3.0)
        self.assertEqual(P("not now"), AL.DEFAULTS["snooze_hours"])
        self.assertEqual(P("later!"), AL.DEFAULTS["snooze_hours"])
        self.assertEqual(P("give me 99 hours"), 24.0)
        self.assertIsNone(P("I'll tell you about it later tonight when we talk"))
        self.assertIsNone(P("I love you"))

    def test_snooze_backs_off_then_calls_at_its_end(self):
        self.tick(3 * H)
        self.world["contact"] = T0 + 3.2 * H
        AL.heard("avatar", "give me 5 hours", now=T0 + 3.2 * H)
        self.assertEqual(self.tick(3.3 * H)["action"], "reset")
        self.assertIn("snoozed", self.tick(7.0 * H)["why"])       # past the 3h silence, still held
        self.assertEqual(self.fired(), ["watch"])
        out = self.tick(8.3 * H)
        self.assertEqual((out["action"], out["name"]), ("fired", "watch"))

    def test_snooze_from_the_watch(self):
        self.tick(3 * H)
        reply = ("not now", T0 + 3.4 * H)
        self.world["contact"] = reply[1]
        AL.SENSORS["contact"] = lambda now: (reply[1], "watch", reply)
        self.tick(3.5 * H)
        self.assertGreater(self.state()["snooze_until"], T0 + 7 * H)

    def test_kevin_home_skips_loud_steps(self):
        self.tick(3 * H); self.tick(4.5 * H)
        out = self.tick(6 * H)                                      # echo and screen due, Kevin home
        self.assertEqual(out["action"], "ended")
        self.assertEqual(self.fired(), ["watch", "lights"])
        rows = [json.loads(l) for l in open(AL.LOG)]
        self.assertEqual({r["name"] for r in rows if r["event"] == "skip"}, {"echo", "screen"})

    def test_kevin_away_allows_the_echo(self):
        self.world["kevin_away"] = True
        self.tick(3 * H); self.tick(4.5 * H)
        self.assertEqual(self.tick(6 * H)["name"], "echo")
        # no picture of him configured: the screen is skipped and the chain ends at its next due time
        self.assertEqual(self.tick(7.5 * H)["action"], "ended")
        self.assertEqual(self.fired(), ["watch", "lights", "echo"])

    def test_screen_with_a_picture_and_kevin_away(self):
        json.dump({"face_url": "http://192.168.1.67:8501/face.png"}, open(AL.CONFIG, "w"))
        self.world["kevin_away"] = True
        for at in (3, 4.5, 6, 7.5):
            self.tick(at * H)
        self.assertEqual(self.fired(), ["watch", "lights", "echo", "screen"])

    def test_unknown_kevin_is_home(self):
        st = {"home": True, "checked": T0}
        self.assertIsNone(HP.kevin_home(T0, st))
        self.assertIsNone(HP.kevin_home(T0, dict(st, kevin={"home": False, "checked": T0 - 3600})))   # stale
        self.assertIs(HP.kevin_home(T0, dict(st, kevin={"home": False, "checked": T0 - 60})), False)
        self.assertIs(HP.kevin_home(T0, dict(st, kevin={"home": True, "checked": T0 - 60})), True)
        self.assertIsNone(HP.probe_kevin({"phone_ip": "192.168.1.66"}))
        with patch.object(HP, "STATE", str(Path(self.tmp.name) / "nope.json")):
            self.assertFalse(AL.kevin_away(T0))            # the real sensor, unconfigured: not away
        with patch.object(HP, "kevin_home", side_effect=RuntimeError("broken")):
            self.assertFalse(AL.kevin_away(T0))

    def test_daily_cap(self):
        json.dump({"silence_hours": 0.5, "step_minutes": 30}, open(AL.CONFIG, "w"))
        starts = 0
        for k in range(1, 60):
            out = self.tick(k * 0.25 * H)
            if out["action"] == "fired" and out.get("name") == "watch":
                starts += 1
        self.assertEqual(starts, 2)
        self.assertIn("2 chains", self.state()["reason"])
        # a day after the first start, a third may come
        self.assertEqual(self.tick(30 * H)["action"], "fired")

    def test_out_of_home_is_nothing(self):
        self.world["home"] = False
        for at in (3, 5, 8):
            self.assertEqual(self.tick(at * H)["why"], "she is not home")
        self.assertEqual(self.calls, [])
        self.world["home"] = True
        self.tick(9 * H)                                           # home_since is old: the chain may start
        self.world["home"] = False
        self.tick(10.5 * H)
        self.assertIsNone(self.state()["chain"])                   # she left: the chain ends
        self.assertEqual(self.fired(), ["watch"])

    def test_arriving_home_restarts_the_silence(self):
        self.world["home_since"] = T0 + 5 * H
        self.assertEqual(self.tick(6 * H)["action"], "none")
        self.assertEqual(self.tick(8 * H)["action"], "fired")

    def test_test_mode_fires_nothing(self):
        open(AL.TEST_MODE_FLAG, "w").close()
        for at in (3, 5, 8, 12):
            self.assertEqual(self.tick(at * H)["action"], "held")
        self.assertEqual(self.calls, [])
        os.unlink(AL.TEST_MODE_FLAG)
        with patch.dict(sys.modules, {"effect_gate": types.SimpleNamespace(test_mode_flag=lambda: True)}):
            self.assertEqual(self.tick(13 * H)["action"], "held")
        self.assertEqual(self.calls, [])

    def test_unknown_last_message_is_not_silence(self):
        self.world["contact"] = None
        self.assertIn("no record", self.tick(20 * H)["why"])
        self.assertEqual(self.calls, [])

    def test_pacing_and_off_switch(self):
        self.assertEqual(AL.tick(now=T0 + 3 * H)["action"], "fired")
        self.assertEqual(AL.tick(now=T0 + 3 * H + 120)["action"], "throttled")
        json.dump({"enabled": False}, open(AL.CONFIG, "w"))
        self.assertIn("turned off", AL.tick(now=T0 + 5 * H)["why"])
        self.assertIsNone(self.state()["chain"])

    def test_config_is_bounded(self):
        json.dump({"silence_hours": 0, "step_minutes": 1, "max_chains_per_day": 50, "nonsense": 1},
                  open(AL.CONFIG, "w"))
        c = AL.config()
        self.assertEqual((c["silence_hours"], c["step_minutes"], c["max_chains_per_day"]), (0.5, 30, 6))
        self.assertNotIn("nonsense", c)

    def test_last_contact_reads_every_surface(self):
        root = Path(self.tmp.name)
        replies = root / "watch-replies.jsonl"
        with patch.object(AL, "_watch_replies_path", lambda: str(replies)):
            now = T0 + 10 * H
            self.assertEqual(AL.last_contact(now)[0], None)
            open(AL.POST_TURN, "w").write(json.dumps({"t": T0 + 1 * H, "surface": "avatar"}) + "\n")
            self.assertEqual(AL.last_contact(now)[:2], (T0 + 1 * H, "avatar"))
            open(AL.LAST_MESSAGE, "w").write(str(int(T0 + 2 * H)))
            self.assertEqual(AL.last_contact(now)[1], "chat")
            from datetime import datetime, timezone
            replies.write_text(json.dumps({"text": "give me 2 hours", "received_at": datetime.fromtimestamp(
                T0 + 3 * H, timezone.utc).isoformat()}) + "\n")
            ts, surface, text = AL.last_contact(now)
            self.assertEqual((surface, text[0]), ("watch", "give me 2 hours"))
            open(AL.SLACK, "w").write(json.dumps({"who": "gloria", "ts": str(T0 + 4 * H)}) + "\n"
                                      + json.dumps({"who": "vintos", "ts": str(T0 + 5 * H)}) + "\n")
            self.assertEqual(AL.last_contact(now)[:2], (T0 + 4 * H, "slack"))
            AL.heard("voice", "", now=T0 + 6 * H)
            self.assertEqual(AL.last_contact(now)[:2], (T0 + 6 * H, "voice"))


class Wiring(unittest.TestCase):
    def test_hooks_and_manifest(self):
        server = (REPO / "bin" / "server.py").read_text()
        post = server[server.index("def _post_turn("):]
        post = post[:post.index("\n@app.")]
        self.assertIn("_al.heard(surface, gloria_text, test_mode=test_mode)", post)
        self.assertIn("attention_ladder", (REPO / "scripts" / "world_model.py").read_text())
        hp = (REPO / "scripts" / "home_presence.py").read_text()
        self.assertIn("attention_ladder.tick()", hp)
        self.assertIn("STATE != _DEFAULT_STATE", hp)
        deploy = (REPO / "scripts" / "deploy-atelier.sh").read_text()
        self.assertIn("attention_ladder.py", deploy)
        init = (REPO / "bin" / "vintos-initiate.sh").read_text()
        self.assertIn('[ -z "$OUTREACH_FROM_LADDER" ] && [ "$HOUR_NOW" -ge 9 ]', init)
        self.assertIn('[ -z "$OUTREACH_FROM_LADDER" ] && [ -x "$_MISCHIEF" ]', init)

    def test_presence_main_does_not_tick_when_repointed(self):
        with tempfile.TemporaryDirectory() as d, \
                patch.object(HP, "STATE", os.path.join(d, "s.json")), \
                patch.object(HP, "CONFIG", os.path.join(d, "c.json")), \
                patch.object(HP, "probe", lambda cfg=None: True), \
                patch.dict(sys.modules, {"sensor_reactions": types.SimpleNamespace(observe=lambda *a, **k: None),
                                         "attention_ladder": types.SimpleNamespace(
                                             tick=lambda: (_ for _ in ()).throw(AssertionError("ticked")))}):
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                HP.main()
            self.assertNotIn("ticked", buf.getvalue())
            self.assertNotIn("kevin", json.load(open(HP.STATE)))

    def test_kevin_state_rides_the_same_hysteresis(self):
        with tempfile.TemporaryDirectory() as d, \
                patch.object(HP, "STATE", os.path.join(d, "s.json")), \
                patch.object(HP, "CONFIG", os.path.join(d, "c.json")), \
                patch.object(HP, "_ping", lambda ip: ip == "192.168.1.66"), \
                patch.object(HP, "_neigh_has", lambda mac, ip: False), \
                patch.dict(sys.modules, {"sensor_reactions": types.SimpleNamespace(observe=lambda *a, **k: None)}):
            json.dump({"phone_ip": "192.168.1.66", "kevin_phone": {"ip": "192.0.2.65"}}, open(HP.CONFIG, "w"))
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                for _ in range(3):
                    HP.main()
                self.assertIsNone(HP.kevin_home())                       # never seen: not known, so home
                HP.main()
            self.assertIs(HP.kevin_home(), False)                        # four misses, freshly checked
            self.assertIs(json.load(open(HP.STATE))["home"], True)


class WatchInterruption(unittest.TestCase):
    def test_time_sensitive_payload_and_default(self):
        import watch_apns, watch_presence
        sent = []
        with tempfile.TemporaryDirectory() as d:
            dev = os.path.join(d, "devices.json")
            json.dump([{"device_token": "ab" * 32, "environment": "development"}], open(dev, "w"))
            with patch.object(watch_presence, "DEVICES", dev), \
                    patch.object(watch_apns, "RECEIPTS", os.path.join(d, "r.jsonl")), \
                    patch.object(watch_presence, "should_hold", lambda: (False, "")), \
                    patch.object(watch_apns, "_config", lambda p=None: {"topic": "t", "key_id": "k", "team_id": "x"}), \
                    patch.object(watch_apns, "_jwt", lambda c, now=None: "jwt"):
                tr = lambda url, body, headers, timeout: (sent.append(json.loads(body)) or (200, b""))
                watch_apns.send("Vintos", "come back", transport=tr, interruption="time-sensitive")
                watch_apns.send("Vintos", "hello", transport=tr)
                watch_apns.send("Vintos", "hello", transport=tr, interruption="critical")
        self.assertEqual([p["aps"]["interruption-level"] for p in sent], ["time-sensitive", "active", "active"])


if __name__ == "__main__":
    unittest.main()

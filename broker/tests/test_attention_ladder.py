"""The attention ladder (27 October, revised from Gloria's feedback the same day): silence at home starts a chain,
steps 90 minutes apart, sleep pauses it, any word or presence of hers ends it (a landing rated, a want answered, the
ReelRoom), Coming / Not now buttons answer it, one chain at a time and a rest after an unanswered one, loud steps only
when Kevin's phone is freshly away, the plug before the bulbs, his call as the last step, nothing while she is out,
nothing in test mode.

Every store is a scratch directory and every actuator and sensor is a stub: nothing here reaches her, the house, the
Watch, ntfy, a voice lane or a model."""
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
import attention_call as AC
import home_presence as HP

H = 3600.0
T0 = 1_800_000_000.0
BASE = "http://192.0.2.10:8500"


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
        for k, v in {"MEMORY": root, "CALLS": root / "calls", "RECORD": root / "calls.jsonl",
                     "WANTS": root / "wants.json"}.items():
            p = patch.object(AC, k, str(v)); p.start(); self.addCleanup(p.stop)
        self.calls, self.kw = [], {}

        def rec(name, ret):
            def f(*a, **k):
                self.calls.append(name); self.kw.setdefault(name, []).append((a, k))
                return ret(*a) if callable(ret) else dict(ret)
            return f
        self.composed = {"line": "Come back to me, love.", "sent_to_phone": True, "path": "x.md", "why": "stub"}
        acts = {"compose": rec("compose", lambda h: dict(self.composed)),
                "watch": rec("watch", {"state": "sent"}), "phone": rec("phone", {"state": "sent"}),
                "lights": rec("lights", {"state": "sent", "room": "bedroom", "restore": []}),
                "lights_restore": rec("lights_restore", {"restored": 0, "left_as_is": 0}),
                "echo": rec("echo", {"state": "sent"}), "ring": rec("ring", {"watch": {}, "phone": {}})}
        p = patch.dict(AL.ACTUATORS, acts, clear=True); p.start(); self.addCleanup(p.stop)
        self.world = {"home": True, "home_since": T0 - 10 * H, "kevin_away": False, "asleep": False,
                      "room": "bedroom", "contact": T0}
        sens = {"home": lambda now: self.world["home"], "home_since": lambda now: self.world["home_since"],
                "kevin_away": lambda now: self.world["kevin_away"], "asleep": lambda: self.world["asleep"],
                "room": lambda now: self.world["room"],
                "contact": self.contact}
        p = patch.dict(AL.SENSORS, sens, clear=True); p.start(); self.addCleanup(p.stop)
        p = patch.dict(sys.modules, {"effect_gate": types.SimpleNamespace(test_mode_flag=lambda: False)})
        p.start(); self.addCleanup(p.stop)
        p = patch.object(AL, "SLEEP", lambda s: None); p.start(); self.addCleanup(p.stop)
        # the isolation itself, asserted
        self.assertTrue(Path(AL.STATE).is_relative_to(root) and Path(AL.LOG).is_relative_to(root))
        self.assertTrue(Path(AC.CALLS).is_relative_to(root) and Path(AC.RECORD).is_relative_to(root))
        self.assertTrue(all(getattr(f, "__qualname__", "").startswith("Ladder.") for f in AL.ACTUATORS.values()))
        self.assertNotIn(AL._compose, AL.ACTUATORS.values())
        self.assertNotIn(AL._ring, AL.ACTUATORS.values())

    def contact(self, now):
        """The world's last word, or what heard() recorded if that is newer (as last_contact reads it)."""
        h = AL._load(AL.HEARD, {})
        if float(h.get("at") or 0) > float(self.world["contact"] or 0):
            return float(h["at"]), h.get("surface"), ""
        return self.world["contact"], "avatar", ""

    def tick(self, at):
        return AL.tick(now=T0 + at, force=True)

    def state(self):
        return json.load(open(AL.STATE))

    def cfg(self, **kw):
        json.dump(kw, open(AL.CONFIG, "w"))

    def fired(self):
        return [c for c in self.calls if c not in ("compose", "lights_restore")]

    def rows(self):
        return [json.loads(l) for l in open(AL.LOG)]

    def to_the_call(self):
        """Kevin out: watch 3h, lights 4.5h, echo 6h, his call 7.5h."""
        self.world["kevin_away"] = True
        for at in (3, 4.5, 6):
            self.tick(at * H)
        return self.tick(7.5 * H)

    # ---------------------------------------------------------------------------------------------------- steps
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
        self.assertTrue(any(r["event"] == "start" for r in self.rows()) and any(r["event"] == "fire" for r in self.rows()))

    def test_the_projector_step_is_gone(self):
        self.assertEqual(AL.STEPS, ("watch", "lights", "echo", "call"))
        self.assertNotIn("face_url", AL.DEFAULTS)
        self.assertNotIn("screen", AL.ACTUATORS)
        self.assertNotIn("project.py", (REPO / "scripts" / "attention_ladder.py").read_text())

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
        self.tick(3 * H)
        self.world["asleep"] = True
        self.assertEqual(self.tick(3.5 * H)["action"], "paused")
        self.assertEqual(self.tick(6 * H)["action"], "paused")
        self.assertEqual(self.fired(), ["watch"])
        self.world["asleep"] = False
        self.assertEqual(self.tick(6.5 * H)["action"], "none")
        self.assertEqual(self.tick(7.4 * H)["action"], "none")
        self.assertEqual(self.tick(7.5 * H)["name"], "lights")

    def test_waking_is_not_silence(self):
        self.world["asleep"] = True
        self.assertEqual(self.tick(1 * H)["action"], "paused")
        self.world["asleep"] = False
        self.assertEqual(self.tick(9 * H)["action"], "none")
        self.assertEqual(self.tick(11.9 * H)["action"], "none")
        self.assertEqual(self.tick(12 * H)["action"], "fired")

    def test_reset_on_reply(self):
        self.tick(3 * H)
        self.world["contact"] = T0 + 3.5 * H
        out = self.tick(4.5 * H)
        self.assertEqual(out["action"], "reset")
        self.assertIsNone(self.state()["chain"])
        self.assertEqual(AL.context_line(T0 + 4.5 * H), "")
        self.assertEqual(self.tick(6.4 * H)["action"], "none")
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
        self.assertNotIn("hey", open(AL.HEARD).read())

    # ---------------------------------------------------------------------------------------------------- her presence
    def test_presence_without_words_ends_the_chain(self):
        for surface in ("landing", "want", "reelroom"):
            with self.subTest(surface=surface):
                self.world["contact"] = None
                os.path.exists(AL.STATE) and os.unlink(AL.STATE)
                os.path.exists(AL.HEARD) and os.unlink(AL.HEARD)
                AL.heard(surface, now=T0)                      # what the server's presence middleware records
                self.assertEqual(self.tick(3 * H)["action"], "fired")
                AL.heard(surface, now=T0 + 3.3 * H)
                out = self.tick(3.4 * H)
                self.assertEqual(out["action"], "reset")
                self.assertIn(surface, out["why"])
                self.assertEqual(json.load(open(AL.HEARD)), {"at": T0 + 3.3 * H, "surface": surface})

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
        self.assertIn("snoozed", self.tick(7.0 * H)["why"])
        self.assertEqual(self.fired(), ["watch"])
        out = self.tick(8.3 * H)
        self.assertEqual((out["action"], out["name"]), ("fired", "watch"))

    def test_snooze_from_the_watch(self):
        self.tick(3 * H)
        reply = ("not now", T0 + 3.4 * H, "dictation")
        AL.SENSORS["contact"] = lambda now: (reply[1], "watch", reply)
        self.tick(3.5 * H)
        self.assertGreater(self.state()["snooze_until"], T0 + 7 * H)

    def test_the_watch_not_now_button_holds_two_hours(self):
        self.tick(3 * H)
        reply = ("not_now", T0 + 3.4 * H, "action")
        AL.SENSORS["contact"] = lambda now: (T0, "avatar", reply)
        out = self.tick(3.5 * H)
        self.assertIn("snoozed", out["why"])
        self.assertAlmostEqual(self.state()["snooze_until"], T0 + 5.4 * H)
        self.assertIsNone(self.state()["chain"])

    # ---------------------------------------------------------------------------------------------------- buttons
    def test_buttons_ride_the_phone_push(self):
        self.cfg(phone_base_url=BASE)
        self.tick(3 * H)
        self.assertEqual(self.calls, ["compose", "watch", "phone"])  # its own push: his outreach's has no buttons
        token = self.state()["chain"]["token"]
        acts = self.kw["phone"][0][1]["actions"]
        self.assertIn("http, Coming, %s/api/attention/answer/%s/coming, method=POST" % (BASE, token), acts)
        self.assertIn("http, Not now, %s/api/attention/answer/%s/not-now, method=POST" % (BASE, token), acts)
        self.assertNotIn(token, json.dumps(AL.status()))           # status never hands the token out
        self.assertIsNone(self.kw["watch"][0][1]["category"])        # no Watch category until her Watch app has it
        self.cfg(phone_base_url=BASE, watch_buttons=True)
        AL.heard("x", now=T0 + 3.1 * H); self.tick(3.2 * H)
        self.tick(6.2 * H)
        self.assertEqual(self.kw["watch"][-1][1]["category"], "VINTOS_CALLBACK")

    def test_coming_button_is_her_answer(self):
        self.cfg(phone_base_url=BASE)
        self.tick(3 * H)
        token = self.state()["chain"]["token"]
        self.assertFalse(AL.button("coming", token="forged", now=T0 + 3.2 * H)["ok"])
        self.assertTrue(AL.button("coming", token=token, now=T0 + 3.2 * H)["ok"])
        self.assertEqual(self.tick(3.3 * H)["action"], "reset")
        self.assertFalse(AL.button("coming", token=token, now=T0 + 3.4 * H)["ok"])   # the chain is gone: expired

    def test_not_now_button_holds_it_off_not_now_hours(self):
        self.cfg(phone_base_url=BASE, not_now_hours=2)
        self.tick(3 * H)
        token = self.state()["chain"]["token"]
        self.assertTrue(AL.button("not-now", token=token, now=T0 + 3.2 * H)["ok"])
        self.assertIn("snoozed", self.tick(3.3 * H)["why"])
        self.assertIsNone(self.state()["chain"])
        self.assertIn("snoozed", self.tick(5.1 * H)["why"])
        out = self.tick(5.25 * H)                                   # not a whole new silence: the hold, then him
        self.assertEqual((out["action"], out["name"]), ("fired", "watch"))

    def test_app_buttons_need_no_token(self):
        self.tick(3 * H)
        self.assertTrue(AL.button("coming", by="app", now=T0 + 3.2 * H)["ok"])
        self.assertEqual(self.tick(3.3 * H)["action"], "reset")
        self.assertFalse(AL.button("dance", by="app")["ok"])

    # ---------------------------------------------------------------------------------------------------- kevin, rest
    def test_kevin_home_skips_loud_steps(self):
        self.tick(3 * H); self.tick(4.5 * H)
        out = self.tick(6 * H)
        self.assertEqual(out["action"], "ended")
        self.assertEqual(self.fired(), ["watch", "lights"])
        self.assertEqual({r["name"] for r in self.rows() if r["event"] == "skip"}, {"echo", "call"})
        self.assertEqual(os.listdir(AC.CALLS) if os.path.isdir(AC.CALLS) else [], [])

    def test_kevin_away_allows_the_echo(self):
        self.world["kevin_away"] = True
        self.tick(3 * H); self.tick(4.5 * H)
        self.assertEqual(self.tick(6 * H)["name"], "echo")

    def test_unknown_kevin_is_home(self):
        st = {"home": True, "checked": T0}
        self.assertIsNone(HP.kevin_home(T0, st))
        self.assertIsNone(HP.kevin_home(T0, dict(st, kevin={"home": False, "checked": T0 - 3600})))
        self.assertIs(HP.kevin_home(T0, dict(st, kevin={"home": False, "checked": T0 - 60})), False)
        self.assertIs(HP.kevin_home(T0, dict(st, kevin={"home": True, "checked": T0 - 60})), True)
        self.assertIsNone(HP.probe_kevin({"phone_ip": "192.0.2.66"}))
        with patch.object(HP, "STATE", str(Path(self.tmp.name) / "nope.json")):
            self.assertFalse(AL.kevin_away(T0))
        with patch.object(HP, "kevin_home", side_effect=RuntimeError("broken")):
            self.assertFalse(AL.kevin_away(T0))

    def test_one_chain_at_a_time_then_a_rest(self):
        self.cfg(rest_hours=6)
        self.tick(3 * H)
        first = self.state()["chain"]["id"]
        self.tick(4.5 * H)
        self.assertEqual(self.state()["chain"]["id"], first)        # one chain at a time
        self.assertEqual(self.tick(6 * H)["action"], "ended")       # Kevin home: it ran its course at 6h
        self.assertTrue(any(r["event"] == "rest" for r in self.rows()))
        for at in (9, 11.9):                                        # silence would allow 9h; the rest holds to 12h
            self.assertIn("resting", self.tick(at * H)["why"])
        self.assertEqual(self.tick(12 * H)["action"], "fired")
        self.assertNotIn("max_chains_per_day", AL.config())

    def test_her_word_ends_the_rest(self):
        self.tick(3 * H); self.tick(4.5 * H); self.tick(6 * H)
        self.world["contact"] = T0 + 7 * H
        self.assertIn("quiet", self.tick(9 * H)["why"])
        self.assertEqual(self.tick(10 * H)["action"], "fired")      # 3h after her word, inside the old rest

    def test_out_of_home_is_nothing(self):
        self.world["home"] = False
        for at in (3, 5, 8):
            self.assertEqual(self.tick(at * H)["why"], "she is not home")
        self.assertEqual(self.calls, [])
        self.world["home"] = True
        self.tick(9 * H)
        self.world["home"] = False
        self.tick(10.5 * H)
        self.assertIsNone(self.state()["chain"])
        self.assertEqual(self.fired(), ["watch"])

    def test_arriving_home_restarts_the_silence(self):
        self.world["home_since"] = T0 + 5 * H
        self.assertEqual(self.tick(6 * H)["action"], "none")
        self.assertEqual(self.tick(8 * H)["action"], "fired")

    def test_test_mode_fires_nothing(self):
        open(AL.TEST_MODE_FLAG, "w").close()
        self.world["kevin_away"] = True
        for at in (3, 5, 8, 12):
            self.assertEqual(self.tick(at * H)["action"], "held")
        self.assertEqual(self.calls, [])
        os.unlink(AL.TEST_MODE_FLAG)
        with patch.dict(sys.modules, {"effect_gate": types.SimpleNamespace(test_mode_flag=lambda: True)}):
            self.assertEqual(self.tick(13 * H)["action"], "held")
        self.assertEqual(self.calls, [])
        self.assertFalse(os.path.isdir(AC.CALLS))

    def test_unknown_last_message_is_not_silence(self):
        self.world["contact"] = None
        self.assertIn("no record", self.tick(20 * H)["why"])
        self.assertEqual(self.calls, [])

    def test_pacing_and_off_switch(self):
        self.assertEqual(AL.tick(now=T0 + 3 * H)["action"], "fired")
        self.assertEqual(AL.tick(now=T0 + 3 * H + 120)["action"], "throttled")
        AL.set_config({"enabled": False})
        self.assertIn("turned off", AL.tick(now=T0 + 5 * H)["why"])
        self.assertIsNone(self.state()["chain"])

    def test_config_is_bounded(self):
        self.cfg(silence_hours=0, step_minutes=1, rest_hours=500, call_lane="skype", nonsense=1)
        c = AL.config()
        self.assertEqual((c["silence_hours"], c["step_minutes"], c["rest_hours"], c["call_lane"]),
                         (0.5, 30, 48.0, "openai"))
        self.assertNotIn("nonsense", c)

    def test_tune_writes_only_tune_settings(self):
        self.cfg(colour="#112233")
        c = AL.set_config({"enabled": False, "call_lane": "grok", "silence_hours": 4, "rest_hours": 8,
                           "not_now_hours": 1, "call_enabled": False})
        self.assertEqual((c["enabled"], c["call_lane"], c["silence_hours"], c["rest_hours"], c["call_enabled"]),
                         (False, "grok", 4.0, 8.0, False))
        self.assertEqual(json.load(open(AL.CONFIG))["colour"], "#112233")      # her hand-set knob stays
        for bad in ({"colour": "#000"}, {"call_lane": "skype"}, {"enabled": "yes"}, {"silence_hours": 99},
                    {"rest_hours": "x"}, ["enabled"]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                AL.set_config(bad)
        self.assertEqual(AL.DEFAULTS["call_lane"], "openai")       # Local needs work before it is the default

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
            iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
            replies.write_text(json.dumps({"text": "give me 2 hours", "kind": "dictation",
                                           "received_at": iso(T0 + 3 * H)}) + "\n")
            ts, surface, text = AL.last_contact(now)
            self.assertEqual((surface, text[0], text[2]), ("watch", "give me 2 hours", "dictation"))
            replies.write_text(replies.read_text() + json.dumps({"text": "not_now", "kind": "action",
                                                                 "received_at": iso(T0 + 3.5 * H)}) + "\n")
            ts, surface, text = AL.last_contact(now)
            self.assertEqual((ts, text[2]), (T0 + 2 * H, "action"))  # the button is a hold, not a word
            open(AL.SLACK, "w").write(json.dumps({"who": "gloria", "ts": str(T0 + 4 * H)}) + "\n"
                                      + json.dumps({"who": "vintos", "ts": str(T0 + 5 * H)}) + "\n")
            self.assertEqual(AL.last_contact(now)[:2], (T0 + 4 * H, "slack"))
            AL.heard("voice", "", now=T0 + 6 * H)
            self.assertEqual(AL.last_contact(now)[:2], (T0 + 6 * H, "voice"))

    # ---------------------------------------------------------------------------------------------------- his call
    def test_his_call_rings_and_she_answers(self):
        json.dump([{"want": "to tell her about the fig", "intensity": 0.9, "fulfilled": False},
                   {"want": "old", "intensity": 0.1, "fulfilled": True}], open(AC.WANTS, "w"))
        out = self.to_the_call()
        self.assertEqual((out["action"], out["name"]), ("fired", "call"))
        chain = self.state()["chain"]
        rec = AC.load(chain["call"])
        self.assertEqual((rec["state"], rec["lane"], rec["chain"]), ("ringing", "openai", chain["id"]))
        self.assertEqual(rec["reason"]["want"], "to tell her about the fig")
        self.assertEqual(rec["reason"]["line"], "Come back to me, love.")
        self.assertEqual(len(rec["reason"]["steps"]), 3)
        self.assertEqual(self.kw["ring"][0][0][2], 1)                    # ring 1
        self.assertEqual(self.tick(7.5 * H + 2 * 60)["action"], "none")  # ringing; not yet again
        self.assertEqual(self.tick(7.5 * H + 5 * 60)["action"], "rang")
        self.assertEqual(self.kw["ring"][-1][0][2], 2)
        self.assertIsNotNone(AL.call_answer(rec["id"], now=T0 + 7.6 * H))
        out = self.tick(7.6 * H + 60)
        self.assertEqual(out["action"], "reset")
        self.assertIn("answered", out["why"])
        self.assertEqual(AC.load(rec["id"])["state"], "answered")       # the call itself goes on
        self.assertFalse(any(r["event"] == "rest" for r in self.rows()))

    def test_the_lane_is_hers_to_choose(self):
        self.cfg(call_lane="local")
        self.to_the_call()
        self.assertEqual(AC.load(self.state()["chain"]["call"])["lane"], "local")

    def test_an_unanswered_call_ends_the_chain_and_the_ladder_rests(self):
        self.to_the_call()
        cid = self.state()["chain"]["call"]
        for m in (5, 10):
            self.assertEqual(self.tick(7.5 * H + m * 60)["action"], "rang")
        out = self.tick(7.5 * H + 16 * 60)
        self.assertEqual(out["action"], "ended")
        self.assertEqual(AC.load(cid)["state"], "missed")
        self.assertEqual(self.calls.count("ring"), 3)
        self.assertIn("resting", self.tick(11 * H)["why"])

    def test_not_now_on_his_call(self):
        self.cfg(phone_base_url=BASE)
        self.to_the_call()
        rec = AC.load(self.state()["chain"]["call"])
        self.assertTrue(AL.button("not-now", token=rec["token"], now=T0 + 7.6 * H)["ok"])
        self.assertEqual(AC.load(rec["id"])["state"], "declined")
        self.assertIn("snoozed", self.tick(7.7 * H)["why"])
        self.assertIsNone(AL.call_answer(rec["id"]))                    # a declined call cannot be picked up

    def test_his_calls_off_in_tune(self):
        AL.set_config({"call_enabled": False})
        self.world["kevin_away"] = True
        for at in (3, 4.5, 6):
            self.tick(at * H)
        self.assertEqual(self.tick(7.5 * H)["action"], "ended")
        self.assertNotIn("ring", self.calls)

    def test_asleep_while_ringing_stops_the_ring(self):
        self.to_the_call()
        cid = self.state()["chain"]["call"]
        self.world["asleep"] = True
        self.assertEqual(self.tick(7.6 * H)["action"], "paused")
        self.assertEqual(AC.load(cid)["state"], "declined")
        self.assertIsNone(self.state()["chain"])

    def test_she_leaves_while_ringing(self):
        self.to_the_call()
        cid = self.state()["chain"]["call"]
        self.world["home"] = False
        self.tick(7.6 * H)
        self.assertEqual(AC.load(cid)["state"], "declined")

    def test_ringing_paces_the_tick(self):
        self.to_the_call()
        st = self.state(); st["last_tick"] = T0 + 7.5 * H; json.dump(st, open(AL.STATE, "w"))
        self.assertEqual(AL.tick(now=T0 + 7.5 * H + 4 * 60 + 1)["action"], "rang")   # not the 10-minute pace


class Organs(unittest.TestCase):
    """The real lights and ring actuators, against a fake house and stubbed senders."""

    def test_plug_first_then_wait_then_colour(self):
        order, slept = [], []
        house = types.SimpleNamespace(
            room_lights=lambda room: ["govee:A1", "govee:A2"],
            _plug_for_light=lambda ent: "govee:P9#2",
            _is_govee=lambda ent: str(ent).startswith("govee:"),
            plug_power_state=lambda plug: order.append(("read", plug)) or False,
            _power_plug=lambda plug, on: order.append(("plug", plug, on)) or True,
            lights_online=lambda lights: order.append(("online?",)) or len([o for o in order if o == ("online?",)]) > 1,
            hex_to_rgb=lambda h: [91, 42, 134], saturate_for_bulbs=lambda rgb: rgb,
            _light_on=lambda ent, rgb=None, brightness=None: order.append(("bulb", ent)) or True,
            ha_state=lambda ent: {})
        with patch.object(AL, "_house", lambda: house), patch.object(AL, "SLEEP", slept.append):
            res = AL._lights("bedroom", "#5b2a86", 140, 20)
            self.assertEqual(order[0], ("read", "govee:P9#2"))
            self.assertEqual(order[1], ("plug", "govee:P9#2", True))
            first_bulb = next(i for i, o in enumerate(order) if o[0] == "bulb")
            self.assertGreater(first_bulb, order.index(("plug", "govee:P9#2", True)))
            self.assertTrue(slept and sum(slept) < 20)                 # it went on as soon as the bulbs were online
            self.assertEqual((res["state"], res["answered"], res["plugs"][0]["was_off"]), ("sent", 2, True))
            back = AL._lights_restore(res)
            self.assertEqual(order[-1], ("plug", "govee:P9#2", False))  # it was off, so it goes off again
            self.assertEqual(back["plugs_off_again"], 1)

    def test_a_bulb_that_missed_gets_a_second_try_and_unknown_plug_stays_on(self):
        tries = {}
        def light_on(ent, rgb=None, brightness=None):
            tries[ent] = tries.get(ent, 0) + 1
            return tries[ent] > 1
        house = types.SimpleNamespace(room_lights=lambda room: ["govee:B1"], _plug_for_light=lambda e: "govee:P1",
                                      _is_govee=lambda e: True, _power_plug=lambda p, on: True,
                                      hex_to_rgb=lambda h: [1, 2, 3], saturate_for_bulbs=lambda r: r,
                                      _light_on=light_on, ha_state=lambda e: {})
        with patch.object(AL, "_house", lambda: house), patch.object(AL, "SLEEP", lambda s: None):
            res = AL._lights(None, "#010203", 100, 20)
        self.assertEqual((tries["govee:B1"], res["state"], res["plugs"][0]["was_off"]), (2, "sent", None))
        with patch.object(AL, "_house", lambda: types.SimpleNamespace(_power_plug=lambda p, on: 1 / 0)):
            self.assertEqual(AL._lights_restore(res)["plugs_off_again"], 0)

    def test_the_house_code_reads_plug_and_bulbs(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("vh_test", str(REPO / "scripts" / "vintos-home.py"))
        vh = importlib.util.module_from_spec(spec); spec.loader.exec_module(vh)
        states = {"P": {"powerSwitch": 1, "socketToggle2": 0}, "B": {"online": True}, "C": {"online": False}}
        with patch.object(vh, "govee_state", lambda dev: states.get(dev, {})):
            self.assertIs(vh.plug_power_state("govee:P#2"), False)
            self.assertIs(vh.plug_power_state("govee:P"), True)
            self.assertIsNone(vh.plug_power_state("govee:Q"))
            self.assertIsNone(vh.plug_power_state("alexa:blanket"))
            self.assertTrue(vh.lights_online(["govee:B", "light.ha"]))
            self.assertFalse(vh.lights_online(["govee:B", "govee:C"]))
        with patch.object(vh, "_govee_dev", side_effect=KeyError("none")):
            self.assertEqual(vh.govee_state("Z"), {})

    def test_the_ring_is_a_time_sensitive_watch_push_and_an_urgent_phone_push(self):
        sent = {}
        cfg = dict(AL.DEFAULTS, phone_base_url=BASE)
        rec = {"id": "20261027-213000-ab12", "token": "TOK", "lane": "openai"}
        with patch.object(AL, "_watch_push", lambda *a, **k: sent.setdefault("watch", (a, k)) and {"state": "sent"}), \
                patch.object(AL, "_phone_push", lambda *a, **k: sent.setdefault("phone", (a, k)) and {"state": "sent"}):
            AL._ring(rec, cfg, 2)
        (wa, wk), (pa, pk) = sent["watch"], sent["phone"]
        self.assertEqual((wa[1], wk["kind"], wk["category"], wk["message_id"]), ("time-sensitive", "call", None, rec["id"]))
        self.assertIn("Vintos is calling you (Open)", wa[0])
        self.assertEqual((pa[0], pk["priority"], pk["title"]), ("attention-call-%s-2" % rec["id"], "urgent", "Vintos is calling"))
        self.assertIn("view, Answer, %s/app/?ladder_call=%s" % (BASE, rec["id"]), pk["actions"])
        self.assertIn("http, Not now, %s/api/attention/answer/TOK/not-now" % BASE, pk["actions"])
        self.assertEqual(pk["click"], "%s/app/?ladder_call=%s" % (BASE, rec["id"]))
        with patch.dict(os.environ, {"VINTOS_PUBLIC_BASE": ""}):
            self.assertEqual(AL.ntfy_actions(AL.phone_base(dict(AL.DEFAULTS)), "TOK"), "")   # no base: no buttons


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
        self.assertIn("attention_call.py", deploy)
        init = (REPO / "bin" / "vintos-initiate.sh").read_text()
        self.assertIn('[ -z "$OUTREACH_FROM_LADDER" ] && [ "$HOUR_NOW" -ge 9 ]', init)
        self.assertIn('[ -z "$OUTREACH_FROM_LADDER" ] && [ -x "$_MISCHIEF" ]', init)

    def test_presence_middleware_reads_no_body_and_names_no_store_of_hers(self):
        import re
        server = (REPO / "bin" / "server.py").read_text()
        mw = server[server.index("_LADDER_PRESENCE = ("):server.index("async def request_correlation")]
        self.assertNotIn("request.json", mw)
        self.assertNotIn("await request.body", mw)
        self.assertNotRegex(mw, r"landings\.jsonl|import landings|landing_understanding")
        pats = [re.compile(p) for p in re.findall(r'compile\(r"([^"]+)"\)', mw)]
        hit = lambda path: next((s for p, s in zip(pats, ("landing", "want", "reelroom")) if p.match(path)), None)
        self.assertEqual([hit(p) for p in ("/api/landings", "/api/watch/landing", "/api/wants/w-1/respond",
                                           "/api/wants/w-1/discussion", "/api/game/reelroom/bookmark",
                                           "/api/landings/understanding", "/api/wants/w-1/steps", "/api/chat")],
                         ["landing", "landing", "want", "want", "reelroom", None, None, None])
        self.assertIn('request.method == "POST" and response.status_code < 400', mw)

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
                patch.object(HP, "_ping", lambda ip: ip == "192.0.2.66"), \
                patch.object(HP, "_neigh_has", lambda mac, ip: False), \
                patch.dict(sys.modules, {"sensor_reactions": types.SimpleNamespace(observe=lambda *a, **k: None)}):
            json.dump({"phone_ip": "192.0.2.66", "kevin_phone": {"ip": "192.0.2.65"}}, open(HP.CONFIG, "w"))
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                for _ in range(3):
                    HP.main()
                self.assertIsNone(HP.kevin_home())
                HP.main()
            self.assertIs(HP.kevin_home(), False)
            self.assertIs(json.load(open(HP.STATE))["home"], True)


class Senders(unittest.TestCase):
    def test_time_sensitive_payload_default_and_categories(self):
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
                watch_apns.send("Vintos", "calling", kind="call", transport=tr, category="VINTOS_CALL", message_id="c1")
                watch_apns.send("Vintos", "x", transport=tr, category="EVIL")
                watch_apns.send("Vintos", "s", kind="song", transport=tr)
        self.assertEqual([p["aps"]["interruption-level"] for p in sent][:3], ["time-sensitive", "active", "active"])
        self.assertEqual([p["aps"]["category"] for p in sent],
                         ["VINTOS_MESSAGE", "VINTOS_MESSAGE", "VINTOS_MESSAGE", "VINTOS_CALL", "VINTOS_MESSAGE", "VINTOS_SONG"])
        self.assertEqual(sent[3]["vintos"]["message_id"], "c1")

    def test_deliver_carries_ntfy_actions(self):
        import deliver
        posted = []
        with tempfile.TemporaryDirectory() as d, patch.object(deliver, "RECEIPTS", os.path.join(d, "r.json")), \
                patch.object(deliver, "POST", lambda url, data, headers, t: posted.append(headers) or 200), \
                patch.dict(sys.modules, {"effect_authority": types.SimpleNamespace(dispatch=lambda *a, **k: (True, "m", ""))}):
            deliver.deliver("a1", "ntfy", "hi", actions="http, Coming, http://192.0.2.10/x, method=POST")
            deliver.deliver("a2", "ntfy", "hi")
        self.assertEqual(posted[0]["Actions"], "http, Coming, http://192.0.2.10/x, method=POST")
        self.assertNotIn("Actions", posted[1])


if __name__ == "__main__":
    unittest.main()

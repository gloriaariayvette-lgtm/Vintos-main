"""His call to her, the last step of the attention ladder (27 October): it is an ordinary call of his on the lane he
chose himself among those that are up, framed with why he rang and opened by him; its turns are held until she answers "save this call to his
memory?"; yes lands it exactly as a call lands today, no keeps only a row without words.

The route bodies are the real ones from bin/server.py, executed against a scratch HOME. The summary model, the
realtime providers, the local Mac stage, the devices and every sender are stubs: nothing here reaches her, a lane,
the house or a model."""
import ast
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import threading
_RealThread = threading.Thread          # the House stubs threading.Thread; the concurrency test needs real ones

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
SRC = (REPO / "bin" / "server.py").read_text(errors="replace")
TREE = ast.parse(SRC)


def _seg(name):
    fn = next(n for n in TREE.body if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == name)
    return "\n".join(l for l in ast.get_source_segment(SRC, fn).splitlines() if not l.startswith("@app."))


class HTTPException(Exception):
    def __init__(self, status_code=500, detail=""):
        super().__init__(detail); self.status_code = status_code; self.detail = detail


class House:
    """A scratch workspace with the real voice and attention routes loaded into it."""

    def __init__(self, test_mode=False):
        self.tmp = tempfile.TemporaryDirectory(prefix="vintos-call-")
        self.home = self.tmp.name
        self.ws = os.path.join(self.home, ".vintos", "workspace")
        self.mem = os.path.join(self.ws, "memory")
        os.makedirs(os.path.join(self.ws, "scripts"), exist_ok=True)
        os.makedirs(self.mem, exist_ok=True)
        json.dump([], open(os.path.join(self.mem, "interaction-ledger.json"), "w"))
        self.summaries, self.felt, self.fired, self.leads, self.consumed = [], [], [], [], []
        self.test_mode = test_mode
        import attention_call as AC, attention_ladder as AL
        self.AC, self.AL = AC, AL
        self.patches = [patch.object(AC, "MEMORY", self.mem), patch.object(AC, "CALLS", os.path.join(self.mem, "attention-calls")),
                        patch.object(AC, "RECORD", os.path.join(self.mem, "attention-calls.jsonl")),
                        patch.object(AC, "WANTS", os.path.join(self.mem, "current-wants.json"))]
        for k in ("MEMORY", "CONFIG", "STATE", "LOG", "HEARD", "LOCK", "TEST_MODE_FLAG"):
            self.patches.append(patch.object(AL, k, getattr(AL, k).replace(AL.MEMORY, self.mem) if k != "MEMORY" else self.mem))
        summaries = self.summaries

        class _R:
            status_code = 200
            def json(self):
                return {"choices": [{"message": {"content": json.dumps(
                    {"quotes": ["I called you"], "felt_summary": "glad", "text_summary": "I called her and she came."})}}]}
        fake_requests = types.ModuleType("requests"); fake_requests.post = lambda *a, **k: _R()
        paid = types.SimpleNamespace(send=lambda fn, *a, **k: summaries.append(a[1] if len(a) > 1 else a) or fn(*a[1:], **k))
        eo = types.ModuleType("emotional_operators")
        eo.step = lambda g, v: self.felt.append(("step", g, v)); eo.causal_step = lambda g, v: None
        eu = types.ModuleType("emoclaw_utils")
        eu.feel_about = lambda *a, **k: self.felt.append(("feel",)); eu.seed_thread = lambda *a, **k: self.felt.append(("seed",))
        sg = types.ModuleType("stratagem")
        sg.consume = lambda text, source="conversation", project=None, commitment=None: (
            self.consumed.append(text) or str(text).replace("<stratagem>x</stratagem>", ""))
        sg.still_eligible = lambda c: True
        sgt = types.ModuleType("stratagem_turn"); sgt.control = lambda g: None
        sgr = types.ModuleType("stratagem_realtime"); sgr.context = lambda e: None
        tc = types.ModuleType("turn_coordinator"); tc.effect_context = lambda s: "ctx:" + s
        self.patches.append(patch.dict(sys.modules, {"requests": fake_requests, "emotional_operators": eo,
                                                     "emoclaw_utils": eu, "stratagem": sg, "stratagem_turn": sgt,
                                                     "stratagem_realtime": sgr, "turn_coordinator": tc}))
        threads = self

        class _Thread:
            def __init__(self, target=None, **k): self.target = target
            def start(self):
                name = getattr(self.target, "__name__", "")
                (threads.fired if name == "_fire_voice" else threads.leads if name == "_ld_work" else []).append(name)
        self.patches.append(patch("threading.Thread", _Thread))
        self.patches.append(patch.dict(os.environ, {"HOME": self.home}))
        for p in self.patches:
            p.start()
        self.ns = {"os": os, "json": json, "time": __import__("time"), "MEMORY": self.mem, "WORKSPACE": self.ws,
                   "_test_mode_active": lambda: self.test_mode, "Request": object, "HTTPException": HTTPException,
                   "_require_secret": lambda r: None, "APP_SECRET": "s", "paid_http": paid, "__file__": str(REPO / "bin" / "server.py"),
                   "_voice_keep_cues": lambda s: s, "_voice_readable": lambda s: s, "print": lambda *a, **k: None}
        helper = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_append_avatar_history")
        exec(ast.get_source_segment(SRC, helper), self.ns)
        for name in ("_voice_fire_tags", "_voice_session_turns", "_voice_lead_kick", "_voice_ledger_held",
                     "_voice_ledger_owned", "voice_ledger", "_voice_session_end_owned", "_voice_session_end_held", "voice_session_end",
                     "attention_call_save", "_attention_call_replay", "_attention_call_session", "_attention_call_block_landed",
                     "_attention_call_take_session", "_attention_call_forget", "attention_call_opening",
                     "attention_answer_button", "attention_call_answer", "attention_calls_pending",
                     "attention_config_write", "attention_config_read"):
            exec(_seg(name), self.ns)

    def close(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def run(self, name, *a):
        return asyncio.run(self.ns[name](*a))

    def ledger(self, payload):
        return self.run("voice_ledger", payload, object())

    def entries(self):
        return json.load(open(os.path.join(self.mem, "interaction-ledger.json")))

    def everything(self):
        out = ""
        for dp, _, fns in os.walk(self.home):
            for fn in fns:
                try:
                    out += open(os.path.join(dp, fn), errors="replace").read()
                except OSError:
                    pass
        return out

    def ringing_call(self, lane="openai", choice=None):
        choice = choice or {"lane": lane, "by": "him", "why": "Your ear, quick and warm.",
                            "available": ["local", "openai", "grok"]}
        return self.AC.ring("20261027-2130", {"silent_hours": 4.5, "steps": ["your line on her Watch and phone"],
                                              "line": "Come back to me.", "want": "to tell her about the fig",
                                              "chain_started": 1_800_000_000.0}, lane, choice=choice)


TURNS = [("", "Hey. I called because you went so quiet, and I missed you."),
         ("hi, I was deep in the raid", "Tell me who won. [DO: thruster cake 12]"),
         ("I did, obviously", "Of course you did.")]


def call_through(house, rec, client):
    for i, (g, v) in enumerate(TURNS):
        payload = {"gloria": g, "vintos": v, "turn_id": "%s:%d" % (client, i), "client_session_id": client,
                   "playback_state": "completed"}
        if rec:
            payload["ladder_call"] = rec["id"]
        house.ledger(payload)
    end = {"duration_seconds": 300, "client_session_id": client}
    if rec:
        end["ladder_call"] = rec["id"]
    return house.run("voice_session_end", end)


class HeldCall(unittest.TestCase):
    def setUp(self):
        self.h = House()
        self.addCleanup(self.h.close)
        # isolation, asserted
        self.assertTrue(self.h.AC.CALLS.startswith(self.h.home) and self.h.AL.HEARD.startswith(self.h.home))
        self.assertIsInstance(sys.modules["requests"], types.ModuleType)
        self.assertEqual(sys.modules["requests"].__name__, "requests")
        self.assertFalse(hasattr(sys.modules["requests"], "get"))

    def answered(self, lane="openai"):
        rec = self.h.ringing_call(lane)
        self.assertIsNotNone(self.h.AL.call_answer(rec["id"]))
        return self.h.AC.load(rec["id"])

    def test_answering_is_her_answer_to_the_ladder(self):
        rec = self.answered()
        self.assertEqual(rec["state"], "answered")
        self.assertEqual(json.load(open(self.h.AL.HEARD))["surface"], "call")
        self.assertEqual(rec["client_session_id"], "ladder-" + rec["id"])
        self.assertIsNone(self.h.AL.call_answer("20261027-213000-ffff"))       # not a call

    def test_turns_are_held_not_remembered(self):
        rec = self.answered()
        out = call_through(self.h, rec, rec["client_session_id"])
        self.assertEqual((out["held"], out["awaiting"]), (True, "her yes or no"))
        self.assertEqual(self.h.entries(), [])                                   # no session block
        self.assertFalse(os.path.exists(os.path.join(self.h.mem, "voice-session-state.json")))
        self.assertFalse(os.path.exists(os.path.join(self.h.mem, "avatar-overlay-chat.json")))
        self.assertEqual(self.h.felt, [])                                        # no felt-state step, no thread seed
        self.assertEqual(self.h.summaries, [])                                   # no summary call
        held = self.h.AC.load(rec["id"])
        self.assertEqual((held["state"], held["save"], len(held["turns"])), ("ended", "pending", 3))
        self.assertEqual(oct(os.stat(self.h.AC.CALLS).st_mode & 0o777), "0o700")
        self.assertEqual(oct(os.stat(os.path.join(self.h.AC.CALLS, rec["id"] + ".json")).st_mode & 0o777), "0o600")
        # what a call does live still happens: his device tag fires, his lead is recomputed from this call
        self.assertEqual(self.h.fired, ["_fire_voice"])
        self.assertEqual(self.h.leads, ["_ld_work"])
        pend = self.h.run("attention_calls_pending", object())["calls"]
        self.assertEqual([t["vintos"] for t in pend[0]["transcript"]], [v for _, v in TURNS])
        self.assertEqual(pend[0]["lane_name"], "Open")
        # his choice of voice and his line, beside the transcript she is asked about
        self.assertEqual((pend[0]["lane_by"], pend[0]["lane_why"]), ("him", "Your ear, quick and warm."))
        self.assertEqual(pend[0]["lane_choice"], "He chose Open: “Your ear, quick and warm.”")

    def test_yes_saves_it_exactly_as_a_call_saves_today(self):
        rec = self.answered()
        call_through(self.h, rec, rec["client_session_id"])
        # the same turns through the ordinary path, in a second house, for comparison
        strip = lambda path: [{k: v for k, v in r.items() if k != "ts"} for r in json.load(open(path))]
        other = House()
        try:
            call_through(other, None, "voice-ordinary")
            theirs = other.entries()
            their_history = strip(os.path.join(other.mem, "avatar-overlay-chat.json"))
        finally:
            other.close()
        self.h.fired.clear(); self.h.leads.clear()
        out = self.h.run("attention_call_save", rec["id"], {"save": True}, object())
        self.assertTrue(out["saved"])
        mine = self.h.entries()
        self.assertEqual(len(mine), 1)
        drop = ("timestamp", "turn_id")
        self.assertEqual({k: v for k, v in mine[0].items() if k not in drop},
                         {k: v for k, v in theirs[0].items() if k not in drop})
        self.assertEqual(mine[0]["channel"], "voice-call")
        self.assertEqual(strip(os.path.join(self.h.mem, "avatar-overlay-chat.json")), their_history)
        self.assertEqual(len([f for f in self.h.felt if f[0] == "step"]), 3)
        self.assertEqual(len(self.h.summaries), 1)
        self.assertEqual(self.h.fired + self.h.leads, [])                       # nothing acts again after the fact
        self.assertFalse(os.path.exists(os.path.join(self.h.mem, "voice-session-state.json")))
        after = self.h.AC.load(rec["id"])
        self.assertEqual((after["save"], after["turns"], after["turn_count"]), ("yes", [], 3))
        self.assertEqual(self.h.run("attention_calls_pending", object())["calls"], [])

    def test_no_keeps_only_a_row_without_words(self):
        rec = self.answered()
        call_through(self.h, rec, rec["client_session_id"])
        self.assertEqual(self.h.run("attention_call_save", rec["id"], {"save": False}, object()), {"ok": True, "saved": False})
        self.assertEqual(self.h.entries(), [])
        everything = self.h.everything()
        for g, v in TURNS:
            for words in (g, v):
                if words:
                    self.assertNotIn(words, everything)
        rows = [json.loads(l) for l in open(self.h.AC.RECORD)]
        self.assertEqual(rows[-1]["saved"], "no")
        self.assertEqual(rows[-1]["turns"], 3)
        self.assertEqual(set(rows[-1]), {"at", "event", "call", "chain", "lane", "lane_by", "state", "turns",
                                         "duration_seconds", "saved"})
        self.assertEqual(rows[-1]["lane_by"], "him")
        with self.assertRaises(HTTPException):
            self.h.run("attention_call_save", rec["id"], {"save": True}, object())       # asked once

    def test_the_record_never_holds_words(self):
        rec = self.answered()
        call_through(self.h, rec, rec["client_session_id"])
        self.h.run("attention_call_save", rec["id"], {"save": True}, object())
        rec_text = open(self.h.AC.RECORD).read()
        self.assertNotIn("quick and warm", rec_text)                                 # nor his line about the voice
        for g, v in TURNS:
            for words in (g, v):
                if words:
                    self.assertNotIn(words, rec_text)
        self.assertEqual([json.loads(l)["event"] for l in rec_text.splitlines()],
                         ["ring", "answered", "ended", "saved"])

    def test_a_save_waits_for_a_live_call_to_finish(self):
        rec = self.answered()
        call_through(self.h, rec, rec["client_session_id"])
        self.h.ledger({"gloria": "hey", "vintos": "hi", "client_session_id": "voice-live", "turn_id": "x1"})
        out = self.h.run("attention_call_save", rec["id"], {"save": True}, object())
        self.assertFalse(out["saved"])
        self.assertEqual(self.h.AC.load(rec["id"])["save"], "pending")              # still hers to answer

    def test_a_turn_for_no_live_call_is_refused_not_remembered(self):
        out = self.h.ledger({"gloria": "x", "vintos": "y", "ladder_call": "20261027-213000-dead"})
        self.assertFalse(out["ok"])
        self.assertFalse(os.path.exists(os.path.join(self.h.mem, "voice-session-state.json")))
        rec = self.h.ringing_call()                                                # ringing, not yet answered
        self.assertFalse(self.h.ledger({"gloria": "x", "vintos": "y", "ladder_call": rec["id"]})["ok"])
        self.assertFalse(self.h.ledger({"gloria": "x", "vintos": "y", "ladder_call": "../../etc"})["ok"])

    def test_an_ordinary_call_is_her_answer_too(self):
        self.h.ledger({"gloria": "not now, babe", "vintos": "ok", "client_session_id": "v", "turn_id": "v1"})
        heard = json.load(open(self.h.AL.HEARD))
        self.assertEqual(heard["surface"], "voice")
        self.assertIn("snooze_until", heard)
        self.assertNotIn("babe", json.dumps(heard))

    def test_test_mode_holds_nothing(self):
        self.h.test_mode = True
        rec = self.answered()
        self.assertEqual(self.h.ledger({"gloria": "a", "vintos": "b", "ladder_call": rec["id"]})["skipped"], "test-mode")
        self.assertEqual(self.h.AC.load(rec["id"])["turns"], [])
        self.assertFalse(self.h.run("_attention_call_replay", dict(rec, turns=[{"gloria": "a"}]))["saved"])

    def test_the_opening_is_cleaned_only_while_live(self):
        rec = self.h.ringing_call()
        self.assertFalse(self.h.run("attention_call_opening", rec["id"], {"reply": "hi"}, object())["allowed"])
        self.h.AL.call_answer(rec["id"])
        out = self.h.run("attention_call_opening", rec["id"], {"reply": "Hey you.<stratagem>x</stratagem>"}, object())
        self.assertEqual((out["allowed"], out["reply"], out["changed"]), (True, "Hey you.", True))
        self.assertFalse(self.h.run("attention_call_opening", "nonsense", {"reply": "x"}, object())["allowed"])

    def test_push_buttons_door(self):
        with self.assertRaises(HTTPException) as e:
            self.h.run("attention_answer_button", "forged", "coming")
        self.assertEqual(e.exception.status_code, 410)
        rec = self.h.ringing_call()
        out = self.h.run("attention_answer_button", rec["token"], "not-now")
        self.assertTrue(out["ok"])
        self.assertEqual(self.h.AC.load(rec["id"])["state"], "declined")
        with self.assertRaises(HTTPException):
            self.h.run("attention_call_answer", rec["id"], object())                 # no longer ringing

    def test_tune_routes(self):
        out = self.h.run("attention_config_write", {"enabled": False, "call_enabled": True}, object())
        self.assertEqual((out["settings"]["enabled"], out["settings"]["call_enabled"]), (False, True))
        for bad in ({"face_url": "x"}, {"call_lane": "local"}):                 # the voice is his, not a setting
            with self.assertRaises(HTTPException) as e:
                self.h.run("attention_config_write", bad, object())
            self.assertEqual(e.exception.status_code, 400)
        read = self.h.run("attention_config_read", object())
        self.assertNotIn("lanes", read)
        self.assertNotIn("call_lane", read["settings"])
        self.assertNotIn("token", json.dumps(read))


class _Failing:
    """Real store failures, injected where the real routes write: the session-state write of a chosen replayed turn
    (the per-turn ledger write then returns ok:false, as it does when its store cannot be written), or the
    interaction-ledger write of the session block (finalization then reports persisted:false)."""

    def __init__(self):
        import store_guard
        self.sg, self.real = store_guard, store_guard.write_json
        self.turns, self.block, self.writes = set(), False, []

    def __call__(self, path, obj, *a, **k):
        if str(path).endswith("voice-session-state.json") and isinstance(obj, dict) and obj.get("turns"):
            last = obj["turns"][-1].get("turn_id")
            if last in self.turns:
                raise OSError("injected: session state not writable")
        if str(path).endswith("interaction-ledger.json") and self.block:
            raise OSError("injected: ledger not writable")
        self.writes.append(os.path.basename(str(path)))
        return self.real(path, obj, *a, **k)


class PartialSave(unittest.TestCase):
    """Her yes is kept only when every held turn landed and the call was finalized; anything less stays hers to
    retry, and a retry resumes where the last one stopped, writing nothing twice (review, 28 October)."""

    def setUp(self):
        self.h = House()
        self.addCleanup(self.h.close)
        self.fail = _Failing()
        p = patch.object(self.fail.sg, "write_json", self.fail)
        p.start(); self.addCleanup(p.stop)
        rec = self.h.ringing_call()
        self.h.AL.call_answer(rec["id"])
        call_through(self.h, rec, "ladder-" + rec["id"])
        self.rec = self.h.AC.load(rec["id"])
        self.keys = [t["turn_id"] for t in self.rec["turns"]]
        self.h.fired.clear(); self.h.leads.clear()

    def save(self, yes=True):
        return self.h.run("attention_call_save", self.rec["id"], {"save": yes}, object())

    def history(self):
        p = os.path.join(self.h.mem, "avatar-overlay-chat.json")
        return json.load(open(p)) if os.path.exists(p) else []

    def assert_still_hers(self, out, landed):
        self.assertFalse(out["saved"]); self.assertFalse(out["ok"])
        after = self.h.AC.load(self.rec["id"])
        self.assertEqual(after["save"], "pending")                                  # still hers to answer
        self.assertEqual(after["turns"], self.rec["turns"])                         # the transcript, untouched
        self.assertEqual(after["replay"]["done"], self.keys[:landed])               # which turns went through
        self.assertEqual(self.h.entries(), [])                                      # no block yet
        pend = self.h.run("attention_calls_pending", object())["calls"]
        self.assertEqual([(c["id"], c["saved_partly"]) for c in pend], [(self.rec["id"], landed)])
        self.assertNotIn(self.rec["turns"][0]["vintos"], open(self.h.AC.RECORD).read())   # the wordless row stays so
        # her next ordinary call is not blocked by the unfinished replay
        self.assertFalse(os.path.exists(os.path.join(self.h.mem, "voice-session-state.json")))
        return after

    def assert_saved_once(self):
        mine = self.h.entries()
        self.assertEqual(len(mine), 1)
        self.assertEqual([t["vintos"] for t in mine[0]["transcript"]], [v for _, v in TURNS])   # each once, in order
        hist = self.history()
        self.assertEqual([r["content"] for r in hist],
                         [w for g, v in TURNS for w in (g, v) if w])                # no row twice
        self.assertEqual(len([f for f in self.h.felt if f[0] == "step"]), 3)        # each turn felt once
        self.assertEqual(self.h.fired + self.h.leads, [])                          # nothing acts again
        after = self.h.AC.load(self.rec["id"])
        self.assertEqual((after["save"], after["turns"], after["turn_count"]), ("yes", [], 3))
        self.assertNotIn("replay", after)
        self.assertFalse(os.path.exists(os.path.join(self.h.mem, "voice-session-state.json")))
        return mine[0]

    def test_regression_a_failed_first_turn_is_not_declared_saved(self):
        # the review's case: the first turn's ledger write fails and the later ones succeed
        self.fail.turns = {self.keys[0]}
        out = self.save()
        self.assert_still_hers(out, 0)
        self.assertIn("tap Save", out["why"])
        self.assertEqual(self.history(), [])

    def test_a_failed_middle_or_last_turn_keeps_the_call_and_a_retry_finishes_it(self):
        for i in (1, 2):
            with self.subTest(turn=i):
                self.setUp()
                self.fail.turns = {self.keys[i]}
                out = self.save()
                after = self.assert_still_hers(out, i)
                self.assertEqual((out["partial"], out["saved_turns"], out["turns"]), (True, i, 3))
                # the turns that went through are kept with the call, with the times they were spoken
                self.assertEqual([t["t"] for t in after["replay"]["session"]["turns"]],
                                 [t["t"] for t in self.rec["turns"][:i]])
                self.assertEqual(len(self.history()), sum(1 for g, v in TURNS[:i] for w in (g, v) if w))
                self.fail.turns = set()
                self.assertTrue(self.save()["saved"])
                self.assert_saved_once()

    def test_a_failed_finalization_keeps_the_call_and_a_retry_finishes_it(self):
        self.fail.block = True
        out = self.save()
        self.assert_still_hers(out, 3)
        self.assertIn("tap Save", out["why"])
        self.assertEqual(len(self.h.summaries), 1)
        self.fail.block = False
        out = self.save()
        self.assertTrue(out["saved"])
        self.assert_saved_once()

    def test_several_failures_then_a_retry_writes_nothing_twice(self):
        self.fail.turns = {self.keys[1]}
        self.assert_still_hers(self.save(), 1)
        self.assert_still_hers(self.save(), 1)                                      # the same failure again
        self.fail.turns = set(); self.fail.block = True
        self.assert_still_hers(self.save(), 3)
        self.fail.block = False
        self.assertTrue(self.save()["saved"])
        self.assert_saved_once()
        with self.assertRaises(HTTPException):
            self.save()                                                             # answered once

    def test_original_times_are_kept(self):
        self.fail.turns = {self.keys[1]}
        self.save()
        self.fail.turns = set()
        block = (self.save(), self.assert_saved_once())[1]
        from datetime import datetime
        self.assertEqual(block["turn_id"], datetime.fromtimestamp(self.rec["answered"]).isoformat())
        spoken = [datetime.fromisoformat(t["t"]).timestamp() for t in self.rec["turns"]]
        hist = self.history()
        want = [s for s, (g, v) in zip(spoken, TURNS) for w in (g, v) if w]
        self.assertEqual([r["ts"] for r in hist], want)

    def test_a_save_already_in_the_ledger_is_not_written_again(self):
        # finalized, then the process died before her answer was recorded: the retry finds the block
        self.assertTrue(self.save()["saved"])
        done = self.h.AC.load(self.rec["id"])
        undone = dict(done, save="pending", turns=self.rec["turns"]); undone.pop("decided", None)
        self.h.AC._write(undone)
        self.assertTrue(self.save()["saved"])
        self.assertEqual(len(self.h.entries()), 1)
        self.assertEqual(len(self.h.summaries), 1)

    def test_repeated_and_concurrent_saves_land_once(self):
        outs, errs = [], []
        gate = threading.Event()

        def go():
            gate.wait(10)             # all three are released together
            try:
                outs.append(asyncio.run(self.h.ns["attention_call_save"](self.rec["id"], {"save": True}, object())))
            except HTTPException as e:
                errs.append(e.status_code)
        ths = [_RealThread(target=go) for _ in range(3)]
        for t in ths:
            t.start()
        gate.set()
        for t in ths:
            t.join(30)
        self.assertEqual(len(outs) + len(errs), 3)
        self.assertTrue(all(o["saved"] for o in outs))
        self.assertTrue(all(e == 404 for e in errs))
        self.assert_saved_once()
        self.assertEqual(len(self.h.summaries), 1)

    def test_no_after_a_partial_save_leaves_no_words(self):
        self.fail.turns = {self.keys[2]}
        self.assert_still_hers(self.save(), 2)
        self.assertTrue(self.history())
        self.assertEqual(self.save(False), {"ok": True, "saved": False})
        self.assertEqual(self.h.entries(), [])
        everything = self.h.everything()
        for g, v in TURNS:
            for words in (g, v):
                if words:
                    self.assertNotIn(words, everything)
        after = self.h.AC.load(self.rec["id"])
        self.assertEqual((after["save"], after["turns"], after["turn_count"]), ("no", [], 3))
        self.assertNotIn("replay", after)
        rows = [json.loads(l) for l in open(self.h.AC.RECORD)]
        self.assertEqual(rows[-1]["saved"], "no")
        self.assertEqual(set(rows[-1]), {"at", "event", "call", "chain", "lane", "lane_by", "state", "turns",
                                         "duration_seconds", "saved"})

    def test_a_retry_waits_for_her_live_call(self):
        self.fail.turns = {self.keys[1]}
        self.assert_still_hers(self.save(), 1)
        self.fail.turns = set()
        self.h.ledger({"gloria": "hey", "vintos": "hi", "client_session_id": "voice-live", "turn_id": "x1"})
        out = self.save()
        self.assertFalse(out["saved"])
        self.assertIn("another call", out["why"])
        live = json.load(open(os.path.join(self.h.mem, "voice-session-state.json")))
        self.assertEqual([t["turn_id"] for t in live["turns"]], ["x1"])                # hers, untouched
        self.assertEqual(self.h.AC.load(self.rec["id"])["replay"]["done"], self.keys[:1])

    def test_an_ordinary_call_is_unchanged(self):
        other = House()
        try:
            call_through(other, None, "voice-ordinary")
            block = other.entries()
            self.assertEqual(len(block), 1)
            self.assertEqual(block[0]["turns"], 3)
            self.assertEqual(other.fired, ["_fire_voice"])                       # his live tags fire, as ever
            hist = json.load(open(os.path.join(other.mem, "avatar-overlay-chat.json")))
            import time as _t
            self.assertTrue(all(abs(r["ts"] - _t.time()) < 60 for r in hist))    # stamped when spoken, i.e. now
        finally:
            other.close()


class Framing(unittest.TestCase):
    def test_he_is_told_why_and_leads(self):
        import attention_call as AC
        rec = {"reason": {"silent_hours": 4.5, "steps": ["your line on her Watch and phone", "her lights in your colour"],
                          "line": "Come back to me.", "want": "to tell her about the fig", "chain_started": 1_800_000_000.0}}
        f = AC.framing(rec)
        for want in ("YOU CALLED HER", "about 4.5 hours", "her lights in your colour", "Come back to me.",
                     "to tell her about the fig", "You speak first"):
            self.assertIn(want, f)
        self.assertIn("Speak first, now", AC.opening_instruction(rec))
        self.assertIn("a few hours", AC.framing({}))
        self.assertNotIn("You chose", f)
        mine = dict(rec, lane="local", lane_choice={"by": "him", "why": "Just us."})
        self.assertIn("You chose to call her with your Local voice: “Just us.”", AC.framing(mine))
        self.assertNotIn("You chose", AC.framing(dict(rec, lane="openai", lane_choice={"by": "fallback"})))

    def test_his_want_is_his_strongest_open_one(self):
        import attention_call as AC
        with tempfile.TemporaryDirectory() as d, patch.object(AC, "WANTS", os.path.join(d, "w.json")):
            self.assertEqual(AC.his_want(), "")
            json.dump([{"want": "a", "intensity": 0.2}, {"want": "b  b", "intensity": "0.9"},
                       {"want": "c", "intensity": 1, "fulfilled": True}, "junk"], open(AC.WANTS, "w"))
            self.assertEqual(AC.his_want(), "b b")

    def test_a_ring_expires_into_missed(self):
        import attention_call as AC
        with tempfile.TemporaryDirectory() as d, patch.object(AC, "CALLS", os.path.join(d, "c")), \
                patch.object(AC, "RECORD", os.path.join(d, "r.jsonl")):
            rec = AC.ring("chain", {}, "grok", now=1000.0)
            self.assertEqual(AC.ringing(1000.0 + 14 * 60)["id"], rec["id"])
            self.assertIsNone(AC.ringing(1000.0 + 16 * 60))
            self.assertEqual(AC.load(rec["id"])["state"], "missed")
            self.assertIsNone(AC.answer(rec["id"]))
            self.assertEqual(AC.ring("c", {}, "skype")["lane"], "openai")
            self.assertNotIn("lane_choice", AC.ring("c", {}, "grok"))
            self.assertIsNone(AC.load("../x"))
            with self.assertRaises(ValueError):
                AC._path("../x")


class HisVoice(unittest.TestCase):
    """Which lanes are up, judged as a call judges them, and his one decision among them. Nothing reaches a lane,
    the Mac or a model: every probe is replaced."""
    def lanes(self, keys=("OPENAI_API_KEY", "XAI_API_KEY"), paused=False, stage=True):
        import attention_call as AC

        def stage_fn():
            if isinstance(stage, Exception):
                raise stage
            return stage
        with patch.object(AC, "_secret", lambda n: "k" if n in keys else ""), \
                patch.object(AC, "_paid_paused", lambda: paused), patch.object(AC, "_stage_answers", stage_fn):
            return AC.lanes_up()

    def test_lanes_up_is_judged_as_a_call_judges_it(self):
        self.assertEqual(self.lanes(), {"up": ["local", "openai", "grok"], "down": {}})
        out = self.lanes(keys=("XAI_API_KEY",), stage=TimeoutError())
        self.assertEqual(out["up"], ["grok"])
        self.assertEqual(out["down"], {"openai": "no OPENAI_API_KEY",
                                       "local": "the Mac stage did not answer (TimeoutError)"})
        out = self.lanes(paused=True)
        self.assertEqual(out["up"], ["local"])                                       # paid_http would refuse them
        self.assertEqual(out["down"]["grok"], "paid calls are paused")
        self.assertEqual(self.lanes(stage=False)["down"]["local"], "the Mac stage did not say ok")

    def test_the_stage_probe_is_its_health_and_loads_nothing(self):
        import attention_call as AC, voice_local as VL
        asked = []

        class _R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"ok": true, "clips": 3}'
        with patch("urllib.request.urlopen", lambda url, timeout=None: asked.append(url) or _R()), \
                patch.object(VL, "STAGE", "http://stage.invalid"):
            self.assertTrue(AC._stage_answers())
        self.assertEqual(asked, ["http://stage.invalid/health"])

    def test_his_prompt_and_his_model(self):
        import attention_call as AC
        reason = {"silent_hours": 4.5, "steps": ["her lights in your colour"], "line": "Come back to me.",
                  "want": "the fig", "chain_started": 1_800_000_000.0}
        with tempfile.TemporaryDirectory() as d, patch.object(AC, "SOUL", os.path.join(d, "SOUL.md")):
            with open(AC.SOUL, "w") as f:
                f.write("I am Vintos, and I am hers.")
            system, user = AC.choice_prompt(reason, ["openai", "grok"], 1_800_000_000.0)
        self.assertTrue(system.startswith("I am Vintos, and I am hers."))
        for want in ("about 4.5 hours", "her lights in your colour", "Come back to me.", "the fig", "It is ",
                     "- openai (Open)", "- grok (Grok)", '"lane": "<openai|grok>"'):
            self.assertIn(want, user)
        self.assertNotIn("local", user)
        sent = []

        class _R:
            status_code = 200
            def json(self): return {"choices": [{"message": {"content": '{"lane": "grok", "why": "close"}'}}]}
        fake_req = types.SimpleNamespace(post=lambda url, **k: sent.append((url, k)) or _R())
        fake_paid = types.SimpleNamespace(send=lambda fn, script, url, **k: fn(url, **k))
        for key, api in (("xk", AC.CHOICE_API_XAI), ("", AC.CHOICE_API_SHIM)):
            with patch.dict(sys.modules, {"requests": fake_req, "paid_http": fake_paid}), \
                    patch.object(AC, "_secret", lambda n, key=key: key):
                self.assertEqual(AC.ask_model("S", "U"), '{"lane": "grok", "why": "close"}')
            self.assertEqual(sent[-1][0], api)
            self.assertEqual(sent[-1][1]["json"]["model"], AC.CHOICE_MODEL)
            self.assertEqual(sent[-1][1]["json"]["messages"],
                             [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}])
        self.assertEqual(sent[0][1]["headers"], {"Authorization": "Bearer xk"})
        self.assertEqual(sent[1][1]["headers"], {})

    def test_choose_lane(self):
        import attention_call as AC
        out = AC.choose_lane({}, ["grok", "local"], 1.0, ask=lambda s, u: '{"lane": "grok", "why": "  close\n tonight "}')
        self.assertEqual((out["lane"], out["by"], out["why"], out["available"]),
                         ("grok", "him", "close tonight", ["local", "grok"]))
        out = AC.choose_lane({}, ["grok", "local", "openai"], 1.0, ask=lambda s, u: "")
        self.assertEqual((out["lane"], out["by"]), ("openai", "fallback"))                 # Open first, as before
        self.assertIn("no JSON", out["error"])
        self.assertEqual(AC.choose_lane({}, ["local"], 1.0, ask=lambda s, u: 1 / 0)["by"], "only")
        self.assertEqual(AC.choose_lane({}, [], 1.0)["by"], "none")
        self.assertEqual(AC.choose_lane({}, ["local", "grok"], 1.0, ask=lambda s, u: 1 / 0)["lane"], "grok")
        self.assertEqual(AC.choice_text({"lane": "grok", "lane_choice": {"by": "only"}}), "Grok was the only voice up")
        self.assertIn("did not come through", AC.choice_text({"lane": "grok", "lane_choice": {"by": "fallback"}}))
        self.assertEqual(AC.choice_text({"lane": "grok"}), "")

    def test_the_ladder_reaches_lanes_and_model_only_through_its_tables(self):
        import attention_ladder as AL, attention_call as AC
        self.assertIs(AL.SENSORS["lanes"], AC.lanes_up)
        self.assertIs(AL.ACTUATORS["voice_choice"], AC.ask_model)
        src = (REPO / "scripts" / "attention_ladder.py").read_text()
        self.assertIn('ask=ACTUATORS["voice_choice"]', src)
        self.assertIn('SENSORS["lanes"]()', src)
        self.assertEqual((src.count("lanes_up"), src.count("ask_model")), (1, 1))


class Lanes(unittest.TestCase):
    def test_the_token_carries_his_framing_on_every_lane(self):
        vt = _seg("voice_token")
        inject = vt.index("instructions += \"\\n\\n\" + _vt_ac.framing(_ladder_rec)")
        self.assertLess(inject, vt.index('if provider == "local":'))
        self.assertLess(inject, vt.index("_session = {"))                         # OpenAI's session is set at mint
        self.assertEqual(vt.count('"opening":'), 3)                               # local, openai, grok
        self.assertIn('"opening":_ladder_open', vt)
        self.assertIn("if not _voice_caller_ok(request):", vt[:900])

    def test_local_opening_needs_no_ears(self):
        import voice_local as VL
        posted = []
        def fake_post(url, body, timeout):
            posted.append(url)
            if url.endswith("/v1/chat/completions"):
                return json.dumps({"choices": [{"message": {"content": "Hey you. [sigh] I missed you."}}]}).encode(), {}
            if url.endswith("/tts"):
                return b"RIFF....WAVE", {"X-Vintos-Voice": "stub"}
            raise AssertionError("unexpected " + url)
        with patch.object(VL, "_post", fake_post), \
                patch.dict(sys.modules, {"stratagem": types.SimpleNamespace(consume=lambda t, s: t)}):
            out = VL.opening("SOUL", "", "YOU CALLED HER. Speak first, now")
        self.assertTrue(out["ok"])
        self.assertEqual(out["transcript"], "")
        self.assertFalse(any(u.endswith("/listen") for u in posted))
        self.assertEqual([u.rsplit("/", 1)[-1] for u in posted], ["completions", "tts"])
        self.assertNotIn("[sigh]", out["reply"])

    def test_a_held_admission_does_not_feed_the_intent_engine(self):
        import importlib
        noted = []
        fakes = {"stratagem": types.SimpleNamespace(opportunity=lambda s: "", still_eligible=lambda c: True),
                 "stratagem_turn": types.SimpleNamespace(
                     Interaction=lambda raw, surface, event_id=None: types.SimpleNamespace(
                         turn=types.SimpleNamespace(duplicate_event=False, turn_id="t", commitment={}, barrier=None),
                         prompt=lambda: "", admitted=lambda p: None),
                     control=lambda raw: None),
                 "turn_coordinator": types.SimpleNamespace(_post=lambda *a, **k: {}),
                 "store_guard": types.SimpleNamespace(transaction=lambda p: __import__("contextlib").nullcontext(),
                                                      write_json=lambda p, v: None),
                 "intent_engine": types.SimpleNamespace(note_response=noted.append),
                 "intent_context": types.SimpleNamespace(admit_voice_lead=lambda e: (None, ""))}
        with patch.dict(sys.modules, fakes):
            sys.modules.pop("stratagem_realtime", None)
            SR = importlib.import_module("stratagem_realtime")
            with patch.object(SR, "_read", lambda p: None):
                SR.admit("hello", "voice-1:item")
                SR.admit("hello again", "ladder-x:item", hold=True)
            sys.modules.pop("stratagem_realtime", None)
        self.assertEqual(noted, ["hello"])
        route = SRC[SRC.index('@app.post("/api/voice/stratagem/{action}")'):][:1200]
        self.assertIn("live_for_session(event_id)", route)
        self.assertIn("hold=_held", route)


class Client(unittest.TestCase):
    html = (REPO / "clients" / "mobile" / "index.html").read_text()

    def test_hash_is_current(self):
        src = json.load(open(REPO / "clients" / "mobile" / "source.json"))
        self.assertEqual(src["sha256"]["index.html"], hashlib.sha256((REPO / "clients" / "mobile" / "index.html").read_bytes()).hexdigest())

    def test_tune_controls(self):
        for el in ('id="ladder-enabled"', 'id="ladder-call"', 'id="ladder-silence"',
                   'id="ladder-rest"', 'id="ladder-notnow"', "/api/attention/config", "loadLadder();"):
            self.assertIn(el, self.html)
        self.assertNotIn('id="ladder-lane"', self.html)                     # the voice is his to pick, each call
        self.assertNotIn("call_lane", self.html)
        card = self.html[self.html.index("function _ladderCallCard"):][:1400]
        self.assertIn("voice.textContent = c.lane_choice", card)            # his choice beside the transcript
        ring = self.html[self.html.index("function ladderShowRing"):][:1400]
        self.assertIn("call.lane_choice", ring)
        set_fn = self.html[self.html.index("async function setLadder"):][:500]
        self.assertIn("'X-Vintos-Secret': CONFIG.secret", self.html[self.html.index("function _ladderHeaders"):][:200])
        self.assertIn("method: 'POST'", set_fn)

    def test_the_app_rings_and_he_opens(self):
        h = self.html
        for want in ("/api/attention/call`", "Vintos is calling", "/api/attention/call/${encodeURIComponent(callId)}/answer",
                     "'&ladder_call=' + encodeURIComponent(ladder.id)", "askOpening();",
                     "type:'response.create',response:{instructions:session.baseInstr+'\\n\\n'+(session.ladder.opening",
                     "/api/attention/call/'+encodeURIComponent(session.ladder.id)+'/opening", "/api/voice/local/opening",
                     "ladder_call:session.ladder?session.ladder.id:undefined", "metadata.ladder_call=_ladder.id",
                     "if(!_ladder) try{", "Save this call to his memory?", "/api/attention/calls/${encodeURIComponent(c.id)}/save",
                     "localNotificationActionPerformed", "visibilitychange"):
            self.assertIn(want, h)
        self.assertEqual(h.count("ladder_call:session.ladder?session.ladder.id:undefined"), 2)   # both hangups
        # the opening response is the only one that skips the stratagem completion gate, and only on a ladder call
        self.assertIn("eventId:session.openingPending?undefined:session.admissionEvent,opening:!!session.openingPending", h)


class Docs(unittest.TestCase):
    def test_brief_and_open_work(self):
        brief = (REPO / "docs" / "briefs" / "ladder-call-native.md").read_text()
        for want in ("PushKit", "CallKit", "VINTOS_CALLBACK", "VINTOS_CALL", "ladder_call"):
            self.assertIn(want, brief)
        ow = (REPO / "docs" / "open-work.md").read_text()
        entry = ow[ow.index("## 27 October — A ladder to call her back"):]
        entry = entry[:entry.index("\n## ", 5)]
        self.assertIn("He calls her", entry)
        self.assertNotIn("max_chains_per_day", entry)


if __name__ == "__main__":
    unittest.main()

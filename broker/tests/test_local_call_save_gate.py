"""His call on the Local lane keeps out of his memory until she taps Save (review, 29 October).

A call he started (attention_call.py) promises that nothing of it enters his memory until she says so. The ledger
and the hangup kept that promise, but the Local lane's own turn and end routes did not know which call they were:
each local turn wrote how her voice sounded to auditory memory, queued both voices' audio for the media index and
fed her words to the intent engine, and the end route started the embedding batch, all before her answer. Her No
then cleared the held transcript and left the rest.

Now the app sends the call's id to /api/voice/local/turn and /api/voice/local/end; the house checks it against the
call attention_call holds (live, his, on the Local lane) and, while she has not answered, keeps those captures with
the call (the heard records in its private held file, the audio in a pending corner of the media index's private
RAM directory that the batch never reads). Yes publishes them once; No deletes them; held audio still expires
after media_embed's short limit (HELD_MAX_S) whether or not she has answered.

The route bodies are the real ones from bin/server.py (through test_attention_call.House). The Mac stage, the
brain, the voice, the intent engine and the embedding batch are stubs: nothing here reaches a network or a model."""
import ast
import asyncio
import base64
import importlib
import json
import math
import os
import struct
import sys
import time
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_attention_call import House, REPO, SRC, TREE, _seg  # noqa: E402

HEARD = {"first": "the swallows came back to the eaves", "second": "and the fig finally fruited"}


def tone(seconds, freq=220, rate=24000):
    n = int(seconds * rate)
    return struct.pack("<%dh" % n, *(int(8000 * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)))


def wav(pcm, rate=24000):
    import io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return buf.getvalue()


async def _inline(fn, *a, **k):
    return fn(*a, **k)


class FakeRequest:
    def __init__(self, body=None):
        self.headers = {"X-Vintos-Secret": "s"}
        self._body = body

    async def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


class Lane:
    """The Local lane's routes inside a House, with every far end stubbed."""

    def __init__(self, test_mode=False):
        self.h = House(test_mode=test_mode)
        h = self.h
        self.run_dir = os.path.join(h.home, "run")
        os.makedirs(self.run_dir, mode=0o700)
        self.fake_venv = os.path.join(h.home, "fake-venv-python")
        open(self.fake_venv, "w").close()
        self.posted, self.noted, self.delivered, self.kicks = [], [], [], []
        self.flag = os.path.join(h.mem, ".test-mode")
        if test_mode:
            open(self.flag, "w").close()
        import auditory_memory as AM, media_embed as M, voice_local as VL
        self.AM, self.M, self.VL = AM, M, VL
        lane = self

        def post(url, body, timeout):
            lane.posted.append(url.rsplit("/", 1)[-1])
            if url.endswith("/listen"):
                pcm = base64.b64decode(body["audio"])
                said = HEARD["second"] if len(pcm) == len(tone(0.3)) else HEARD["first"]
                return json.dumps({"ok": True, "transcript": said, "audio_reading": "soft, a breath before the end",
                                   "ears": "stub", "audio_native_gemma": True}).encode(), {}
            if url.endswith("/chat/completions"):
                return json.dumps({"choices": [{"message": {"content": "I remember them."}}]}).encode(), {}
            if url.endswith("/voice/models"):
                return b'{"ok": true}', {}
            if url.endswith("/tts"):                      # each reply is its own audio
                return wav(tone(0.2, freq=300 + 10 * lane.posted.count("tts"))), {"X-Vintos-Voice": "stub"}
            raise AssertionError("unexpected " + url)

        class _Turn:
            def __init__(self):
                self.turn_id = "t-" + uuid.uuid4().hex[:16]
                self.duplicate_event = False
                self.test_mode = os.path.exists(lane.flag)
                self.commitment = {}

        class _Interaction:
            def __init__(self, raw, surface, event_id=None, test_mode=False):
                self.turn = _Turn()

            def prompt(self): return ""
            def admitted(self, p): pass
            def complete(self, r): return r

        sgt = sys.modules["stratagem_turn"]
        sgt.Interaction = _Interaction
        sgt.guard_reply = lambda reply, turn=None: reply
        ie = types.ModuleType("intent_engine")
        ie.note_response = self.noted.append
        ie.record_delivery = lambda reply, surface, turn_id, target=None, input_text="": self.delivered.append(input_text)
        ic = types.ModuleType("intent_context")
        ic.admit_voice_lead = lambda turn_id: ({"intent_id": "i-1"}, "LEAD: ask about the fig")
        ca = types.ModuleType("compute_admission"); ca.touch_foreground = lambda: None
        self.patches = [patch.dict(sys.modules, {"intent_engine": ie, "intent_context": ic, "compute_admission": ca}),
                        patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.run_dir}),
                        patch.object(VL, "_post", post),
                        patch.object(AM, "STORE", os.path.join(h.mem, "auditory-memories.json")),
                        patch.object(AM, "TEST_MODE_FLAG", self.flag),
                        patch.object(M, "STORE", os.path.join(h.mem, "media-embeddings.jsonl")),
                        patch.object(M, "AUDITORY", os.path.join(h.mem, "auditory-memories.json")),
                        patch.object(M, "TEST_MODE_FLAG", self.flag),
                        patch.object(M, "VOICE_LIVE", os.path.join(h.mem, ".voice-live")),
                        patch.object(M, "VENV_PY", self.fake_venv),
                        patch.object(M, "kick", lambda linger=0: self.kicks.append(linger) or "started"),
                        # House stubs threading.Thread (its lead and device workers never run); the routes' worker
                        # thread runs inline here instead
                        patch.object(asyncio, "to_thread", _inline)]
        for p in self.patches:
            p.start()
        VL._CALL["id"] = None
        for name in ("voice_local_opening",):
            exec(_seg(name), h.ns)
        self.load_routes(h.ns)

    def load_routes(self, ns):
        for name in ("_attention_call_publish", "_voice_local_ladder_call", "voice_local_turn", "voice_local_end"):
            exec(_seg(name), ns)

    def close(self):
        for p in reversed(self.patches):
            p.stop()
        self.h.close()

    # ---- the app's side of a call
    def turn(self, pcm, ladder=None):
        body = {"audio": base64.b64encode(pcm).decode(), "sample_rate": 24000, "instructions": "SOUL", "framing": ""}
        if ladder:
            body["ladder_call"] = ladder
        return self.h.run("voice_local_turn", FakeRequest(body))

    def end(self, ladder=None):
        return self.h.run("voice_local_end", FakeRequest({"ladder_call": ladder} if ladder else None))

    def ledger(self, rec, client, i, out):
        payload = {"gloria": out.get("transcript", ""), "vintos": out.get("reply", ""), "turn_id": "%s:%d" % (client, i),
                   "client_session_id": client, "playback_state": "completed", "provider": "local"}
        if rec:
            payload["ladder_call"] = rec["id"]
        return self.h.ledger(payload)

    def hangup(self, rec, client):
        end = {"duration_seconds": 60, "client_session_id": client, "provider": "local"}
        if rec:
            end["ladder_call"] = rec["id"]
        return self.h.run("voice_session_end", end)

    def answered(self, lane="local"):
        rec = self.h.ringing_call(lane, choice={"lane": lane, "by": "him", "why": "my own voice tonight",
                                                "available": ["local", "openai"]})
        self.h.AL.call_answer(rec["id"])
        return self.h.AC.load(rec["id"])

    def call(self, rec, pcms=None, end=True):
        """A whole local call he started: turns, the ledger posts, the hangup, the lane's end."""
        client = "ladder-" + rec["id"]
        outs = []
        for i, pcm in enumerate(pcms or (tone(0.5), tone(0.3))):
            out = self.turn(pcm, rec["id"])
            outs.append(out)
            if out.get("ok"):
                self.ledger(rec, client, i, out)
        if end:
            self.hangup(rec, client)
            self.end(rec["id"])
        return outs

    def save(self, rec, yes=True, ns=None):
        ns = ns or self.h.ns
        return asyncio.run(ns["attention_call_save"](rec["id"], {"save": yes}, object()))

    # ---- what is where
    def heard(self):
        return self.AM.memories()

    def queued(self):
        """Audio the embedding batch would read (the ordinary held directory)."""
        try:
            return self.M.held()
        except OSError:
            return []

    def pending_audio(self):
        d = os.path.join(self.M.spool_dir(), "pending")
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def words_outside_the_call(self):
        """Her words anywhere in his memory other than the call's own private held files."""
        found = []
        calls = os.path.join(self.h.mem, "attention-calls")
        for dp, _, fns in os.walk(self.h.mem):
            if dp.startswith(calls):
                continue
            for fn in fns:
                try:
                    text = open(os.path.join(dp, fn), errors="replace").read()
                except OSError:
                    continue
                if any(w in text for w in HEARD.values()):
                    found.append(os.path.relpath(os.path.join(dp, fn), self.h.mem))
        return found


class Base(unittest.TestCase):
    test_mode = False

    def setUp(self):
        self.L = Lane(test_mode=self.test_mode)
        self.addCleanup(self.L.close)
        L = self.L
        # isolation, asserted
        self.assertTrue(L.AM.STORE.startswith(L.h.home) and L.M.STORE.startswith(L.h.home))
        self.assertTrue(L.M.spool_dir().startswith(L.run_dir))
        self.assertEqual(sys.modules["requests"].__name__, "requests")
        self.assertFalse(hasattr(sys.modules["requests"], "get"))

    def assert_nothing_of_it_in_memory(self):
        L = self.L
        self.assertEqual(L.heard(), [])                       # no heard record a recall could find
        self.assertEqual(L.queued(), [])                      # nothing the embedding batch would read
        self.assertEqual(L.noted, [])                         # her words never reached the intent engine
        self.assertEqual(L.delivered, [])
        self.assertEqual(L.words_outside_the_call(), [])
        self.assertIsNone(L.AM.find(HEARD["first"], min_age=0))


class Pending(Base):
    def test_regression_local_turns_of_his_call_wait_for_her_answer(self):
        L = self.L
        rec = L.answered()
        outs = L.call(rec)
        self.assertTrue(all(o["ok"] and o["reply"] == "I remember them." for o in outs), outs)
        self.assertEqual(L.posted.count("listen"), 2)
        self.assert_nothing_of_it_in_memory()
        self.assertEqual(L.kicks, [])                         # the end route started no batch for his call
        self.assertEqual(len(L.pending_audio()), 8)           # both voices of both turns (body + sidecar), held apart
        held = L.h.AC.load(rec["id"])
        self.assertEqual((held["state"], held["save"]), ("ended", "pending"))
        self.assertEqual(len(L.h.AC.captures(rec["id"], "auditory")), 2)
        # held privately: 0700 directories, 0600 files
        import stat
        cap = L.h.AC._captures_path(rec["id"])
        self.assertEqual(stat.S_IMODE(os.stat(cap).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(cap)).st_mode), 0o700)
        pend = os.path.join(L.M.spool_dir(), "pending")
        self.assertEqual(stat.S_IMODE(os.stat(pend).st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(os.stat(os.path.join(pend, n)).st_mode) == 0o600 for n in os.listdir(pend)))
        # the batch, run now, embeds none of it
        L.M.drain(encode=lambda x: [0.0] * L.M.DIM, sleep=lambda s: None)
        self.assertEqual(L.M.load(), [])
        self.assertEqual(len(L.pending_audio()), 8)

    def test_yes_publishes_once(self):
        L = self.L
        rec = L.answered()
        L.call(rec)
        out = L.save(rec)
        self.assertTrue(out["saved"], out)
        heard = L.heard()
        self.assertEqual(sorted(r["transcript"] for r in heard), sorted(HEARD.values()))
        self.assertTrue(all(r["turn_id"].startswith("t-") and r["audio_kept"] is False for r in heard))
        q = L.queued()
        self.assertEqual(sorted(m["speaker"] for _, m, _ in q), ["gloria", "gloria", "vintos", "vintos"])
        self.assertEqual(L.pending_audio(), [])
        self.assertEqual(L.kicks, [0])                        # one batch, after her yes
        self.assertEqual(L.h.AC.captures(rec["id"], "auditory"), [])
        self.assertFalse(os.path.exists(L.h.AC._captures_path(rec["id"])))
        # the batch joins her audio to the heard record, as an ordinary call's does
        L.M.drain(encode=lambda x: [1.0] + [0.0] * (L.M.DIM - 1), sleep=lambda s: None)
        rows = [r for r in L.M.load() if r["kind"] == "call_audio"]
        self.assertEqual(len(rows), 4)
        self.assertEqual(len([r for r in rows if r.get("auditory_memory_id")]), 2)
        # a second yes publishes nothing again
        with self.assertRaises(Exception):
            L.save(rec)                                       # no call waiting: the route's 404
        self.assertEqual(len(L.heard()), 2)
        self.assertEqual(L.kicks, [0])
        # nothing was fed to the intent engine at any point (the realtime lane's held admission skips it too)
        self.assertEqual(L.noted, [])

    def test_no_discards_it(self):
        L = self.L
        rec = L.answered()
        L.call(rec)
        out = L.save(rec, yes=False)
        self.assertEqual(out, {"ok": True, "saved": False})
        self.assert_nothing_of_it_in_memory()
        self.assertEqual(L.pending_audio(), [])
        self.assertFalse(os.path.exists(L.h.AC._captures_path(rec["id"])))
        self.assertEqual(L.kicks, [])
        after = L.h.AC.load(rec["id"])
        self.assertEqual((after["save"], after["turns"]), ("no", []))
        everything = L.h.everything()
        self.assertFalse(any(w in everything for w in HEARD.values()))

    def test_a_retried_turn_is_held_once(self):
        L = self.L
        rec = L.answered()
        same = tone(0.5)
        L.call(rec, pcms=(same, same, tone(0.3)))
        self.assertEqual(len(L.h.AC.captures(rec["id"], "auditory")), 2)
        wavs = [m for _, m, _ in L.M.held_pending(rec["id"])]
        self.assertEqual(sorted(m["speaker"] for m in wavs), ["gloria", "gloria", "vintos", "vintos", "vintos"])
        L.save(rec)                                             # her two recordings once each; each reply he made
        self.assertEqual(sorted(r["transcript"] for r in L.heard()), sorted(HEARD.values()))
        self.assertEqual(len(L.queued()), 5)

    def test_a_save_that_stops_short_publishes_when_it_finishes(self):
        """The partial-save repair (28 October) still decides when the call is saved: the captures go with it."""
        L = self.L
        rec = L.answered()
        L.call(rec)
        import store_guard
        real = store_guard.write_json

        def failing(path, obj, *a, **k):
            if str(path).endswith("voice-session-state.json") and isinstance(obj, dict) and len(obj.get("turns") or []) == 2:
                raise OSError("injected")
            return real(path, obj, *a, **k)
        with patch.object(store_guard, "write_json", failing):
            out = L.save(rec)
        self.assertFalse(out["saved"])
        self.assertTrue(out["partial"])
        self.assertEqual((L.heard(), L.queued()), ([], []))      # a partial yes publishes none of it yet
        self.assertEqual(len(L.pending_audio()), 8)
        out = L.save(rec)
        self.assertTrue(out["saved"], out)
        self.assertEqual(len(L.heard()), 2)
        self.assertEqual(len(L.queued()), 4)
        self.assertEqual(len(L.h.entries()), 1)

    def test_a_restart_before_her_answer_keeps_the_hold(self):
        L = self.L
        rec = L.answered()
        L.call(rec, pcms=(tone(0.5),), end=False)
        # the house restarts mid-call: nothing of the hold lived in the process
        L.VL._CALL["id"] = None
        fresh = dict((k, v) for k, v in L.h.ns.items() if k in ("os", "json", "time", "MEMORY", "WORKSPACE", "_test_mode_active",
                                                                 "Request", "HTTPException", "_require_secret", "APP_SECRET",
                                                                 "paid_http", "__file__", "_voice_keep_cues", "_voice_readable",
                                                                 "print"))
        exec(ast.get_source_segment(SRC, next(n for n in TREE.body if isinstance(n, ast.FunctionDef)
                                              and n.name == "_append_avatar_history")), fresh)
        for name in ("_voice_fire_tags", "_voice_session_turns", "_voice_lead_kick", "_voice_ledger_held",
                     "_voice_ledger_owned", "voice_ledger", "_voice_session_end_owned", "_voice_session_end_held",
                     "voice_session_end", "attention_call_save", "_attention_call_replay", "_attention_call_session",
                     "_attention_call_block_landed", "_attention_call_take_session", "_attention_call_forget"):
            exec(_seg(name), fresh)
        L.load_routes(fresh)
        L.h.ns = fresh
        out = L.turn(tone(0.3), rec["id"])                     # the call goes on after the restart, still held
        self.assertTrue(out["ok"])
        L.ledger(rec, "ladder-" + rec["id"], 1, out)
        L.hangup(rec, "ladder-" + rec["id"]); L.end(rec["id"])
        self.assert_nothing_of_it_in_memory()
        self.assertEqual(len(L.h.AC.captures(rec["id"], "auditory")), 2)
        self.assertTrue(L.save(rec, ns=fresh)["saved"])
        self.assertEqual(len(L.heard()), 2)
        self.assertEqual(len(L.queued()), 4)

    def test_held_audio_still_expires(self):
        L = self.L
        rec = L.answered()
        L.call(rec)
        pend = os.path.join(L.M.spool_dir(), "pending")
        old = time.time() - L.M.HELD_MAX_S - 60
        for n in os.listdir(pend):
            os.utime(os.path.join(pend, n), (old, old))
        self.assertFalse(L.M.held_due())                       # the ten-minute timer's sweep
        self.assertEqual(L.pending_audio(), [])                # dropped, unembedded, though she has not answered
        out = L.save(rec)
        self.assertTrue(out["saved"])
        self.assertEqual(len(L.heard()), 2)                    # the heard records (no audio in them) still land
        self.assertEqual(L.queued(), [])                       # expired audio is not brought back
        self.assertEqual(L.kicks, [])

    def test_audio_that_expires_while_saving_is_not_released(self):
        L = self.L
        rec = L.answered()
        L.call(rec)
        pend = os.path.join(L.M.spool_dir(), "pending")
        old = time.time() - L.M.HELD_MAX_S - 60
        for n in sorted(os.listdir(pend))[:4]:
            os.utime(os.path.join(pend, n), (old, old))
        self.assertTrue(L.save(rec)["saved"])
        self.assertEqual(len([n for n in os.listdir(L.M.spool_dir()) if n.endswith(".wav")]), len(L.queued()))
        self.assertLess(len(L.queued()), 4)
        # a released file keeps its age: it expires on the same clock in the ordinary directory
        for _, m, b in L.queued():
            self.assertLess(abs(os.stat(b).st_mtime - m["held_at"]), 5)

    def test_turns_for_no_call_of_his_on_this_lane_are_refused(self):
        L = self.L
        declined = L.h.ringing_call("local"); L.h.AC.decline(declined["id"])
        realtime = L.answered("openai")
        done = L.answered(); L.call(done); L.save(done, yes=False)
        L.kicks.clear()
        for bad in ("bogus", "../../etc/passwd", "20990101-0000", declined["id"], realtime["id"], done["id"]):
            L.posted.clear()
            out = L.turn(tone(0.5), bad)
            self.assertFalse(out["ok"], bad)
            self.assertEqual(out["stage"], "call", bad)
            self.assertEqual(L.posted, [], bad)                 # the ears never heard it
            self.assertTrue(L.end(bad) is not None)
        self.assert_nothing_of_it_in_memory()
        self.assertEqual(L.pending_audio(), [])
        self.assertEqual(L.kicks, [])
        self.assertEqual(L.h.AC.captures(realtime["id"], "auditory"), [])


class Ordinary(Base):
    def test_an_ordinary_local_call_is_unchanged(self):
        L = self.L
        out = L.turn(tone(0.5))
        self.assertTrue(out["ok"])
        heard = L.heard()
        self.assertEqual([r["transcript"] for r in heard], [HEARD["first"]])     # kept at once, as before
        self.assertEqual(sorted(m["speaker"] for _, m, _ in L.queued()), ["gloria", "vintos"])
        self.assertEqual(L.noted, [HEARD["first"]])
        self.assertEqual(L.delivered, [HEARD["first"]])
        self.assertEqual(L.pending_audio(), [])
        L.end()
        self.assertEqual(L.kicks, [0])                         # the end route starts the batch, as before
        self.assertIsNone(L.VL._CALL["id"])

    def test_his_opening_is_unchanged(self):
        L = self.L
        rec = L.answered()
        with patch.dict(sys.modules, {"stratagem": types.SimpleNamespace(consume=lambda t, s: t)}):
            out = L.h.run("voice_local_opening", FakeRequest({"instructions": "SOUL", "ladder_call": rec["id"]}))
        self.assertTrue(out["ok"])
        self.assertNotIn("listen", L.posted)
        self.assert_nothing_of_it_in_memory()


class TestMode(Base):
    test_mode = True

    def test_test_mode_holds_and_keeps_nothing(self):
        L = self.L
        rec = L.answered()
        L.call(rec)
        self.assertEqual(L.pending_audio(), [])
        self.assertEqual(L.h.AC.captures(rec["id"], "auditory"), [])
        self.assertEqual(L.heard(), [])
        self.assertEqual(L.queued(), [])
        out = L.turn(tone(0.5))                                # an ordinary call in test mode: also nothing
        self.assertTrue(out["ok"])
        self.assertEqual((L.heard(), L.queued()), ([], []))


class Client(unittest.TestCase):
    html = (REPO / "clients" / "mobile" / "index.html").read_text()

    def test_the_app_names_his_call_to_both_local_routes(self):
        fn = self.html[self.html.index("function _finishLocalVoiceSession"):]
        fn = fn[:fn.index("\n}\n")]
        end = fn[fn.index("/api/voice/local/end"):][:400]
        self.assertIn("ladder_call:session.ladder?session.ladder.id:undefined", end)
        i = self.html.index("API+'/api/voice/local/turn'")
        self.assertIn("ladder_call:session.ladder?session.ladder.id:undefined", self.html[i:i + 500])


if __name__ == "__main__":
    unittest.main()

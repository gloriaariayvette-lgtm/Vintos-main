#!/usr/bin/env python3
"""Lifecycle axes must report what happened, not what the reply looked like.

Sol: every nonempty reply became effects=completed, and post-writers became
dispatched even when parsers were skipped or launches failed. These assert the
derived axes, state by state, and that the overclaim sites are gone.
"""
import os, sys, json, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTD = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOTD, "scripts"))
import effect_gate as EG
import turn_coordinator as TC

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:70]) if d else ""))

TMP = tempfile.mkdtemp(prefix="life-")
_saved = (EG.MEM, EG.LOG, EG.ARMED_FLAG, EG.STOP_BUTTON, EG.TEST_MODE_FLAG)
EG.MEM = TMP
EG.LOG = os.path.join(TMP, "effect-gate.jsonl")
EG.ARMED_FLAG = os.path.join(TMP, ".armed")
EG.STOP_BUTTON = os.path.join(TMP, "button.json")
EG.TEST_MODE_FLAG = os.path.join(TMP, ".tm")

class T:  # minimal turn double
    def __init__(self, tid):
        self.turn_id = tid
        self.lifecycle = {"generation": "not_started", "effects": "not_started",
                          "post_writers": "not_started", "transport": "not_started"}
        self.carries_capsule = False
        self.project_id = ""
        self.commitment = {}
TC._record_lifecycle_local = lambda *a, **k: None

ctx = lambda tid: EG.TurnContext(tid, "avatar")

print("--- effects, state by state, from what was recorded ---")
check("nothing recorded -> none (a chatty reply is not an effect)",
      EG.effects_axis("t-quiet") == ("none", ""), EG.effects_axis("t-quiet"))

EG.send_result(ctx("t-good"), "mission", True)
st, why = EG.effects_axis("t-good")
check("every send succeeded -> completed", st == "completed", (st, why))

EG.send_result(ctx("t-bad"), "mission", True)
EG.send_result(ctx("t-bad"), "tenera", False, "not connected")
st, why = EG.effects_axis("t-bad")
check("one failed send -> failed, never completed", st == "failed", (st, why))
check("and the reason counts the failures", "1 of 2" in why, why)

EG._log(turn_id="t-held", decision="deny", why="no_context", toy="mission", level=14)
st, why = EG.effects_axis("t-held")
check("denied with nothing sent -> HELD", st == "HELD", (st, why))

EG._log(turn_id="t-test", decision="would_send", why="test_mode", toy="mission", level=8)
st, why = EG.effects_axis("t-test")
check("test mode simulation -> none, and says it was simulated",
      st == "none" and "simulated" in why, (st, why))

_l = EG.LOG; EG.LOG = os.path.join(TMP, "no-perm", "x.jsonl")
os.makedirs(os.path.dirname(EG.LOG)); os.chmod(os.path.dirname(EG.LOG), 0)
st, why = EG.effects_axis("t-any") if os.geteuid() != 0 else ("unknown", "gate log unreadable")
check("an unreadable log -> unknown, never a guess", st == "unknown", (st, why))
os.chmod(os.path.dirname(EG.LOG), 0o755); EG.LOG = _l

check("turns never read each other's rows",
      EG.effects_axis("t-good")[0] == "completed" and EG.effects_axis("t-bad")[0] == "failed")

print("\n--- the turn axis is set from that derivation ---")
t = T("t-good")
TC.mark_effects_from_gate(t)
check("mark_effects_from_gate writes the derived state",
      t.lifecycle["effects"] == "completed", t.lifecycle)
t2 = T("t-bad"); TC.mark_effects_from_gate(t2)
check("a failed send reaches the axis", t2.lifecycle["effects"] == "failed")

print("\n--- post-writers, from real launches ---")
t = T("t-w1")
TC.note_writer(t, True); TC.note_writer(t, True); TC.note_writer(t, True)
TC.mark_post_writers(t)
check("all launches ok -> dispatched", t.lifecycle["post_writers"] == "dispatched", t.lifecycle)

t = T("t-w2")
TC.note_writer(t, True); TC.note_writer(t, False)
TC.mark_post_writers(t)
check("one failed launch -> failed, never dispatched",
      t.lifecycle["post_writers"] == "failed", t.lifecycle)

t = T("t-w3")
TC.mark_post_writers(t)
check("nothing recorded -> unknown, never a blanket dispatched",
      t.lifecycle["post_writers"] == "unknown", t.lifecycle)

print("\n--- the overclaim sites are gone from the house ---")
srv = open(os.path.join(ROOTD, "bin", "server.py"), errors="replace").read()
check("effects is no longer written from the reply text",
      '"completed" if reply else "none"' not in srv)
check("post_writers is no longer a blanket claim",
      '"post_writers", "dispatched"' not in srv)
check("the gate derivation is what the house calls",
      "mark_effects_from_gate(_turn)" in srv)
check("the launch tally is what the house calls",
      "mark_post_writers(_turn)" in srv)
# 2026-09-05: the avatar's background writers launch from the shared _post_turn, which notes every
# launch (success and failure) through the on_writer callback the avatar passes.
check("launches are individually noted",
      "on_writer=(lambda ok: _tc.note_writer(_turn, ok))" in srv
      and "on_writer(True)" in srv and "on_writer(False)" in srv
      and srv.count("note_writer(_turn") >= 3,
      srv.count("note_writer(_turn"))

print("\n--- transports actually report ---")
tl = open(os.path.join(ROOTD, "scripts", "toy_link.py"), errors="replace").read()
check("every transport path reports its outcome", tl.count("_report(context") >= 8,
      tl.count("_report(context"))
check("a bare reflex call stays out of the record", "if context is None:" in tl)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

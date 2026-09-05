#!/usr/bin/env python3
"""P03-01 mixed-tag order, P03-02 rotation zero on its channel, P03-03 broadcast stop per device,
P02-04 a started local thread is not transport acceptance. Fake authorizer, fake transports, scratch MEM."""
import os, sys, json, tempfile, threading, importlib.util as iu
HERE = os.path.dirname(os.path.abspath(__file__)); SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts")
sys.path.insert(0, SCRIPTS)
TMP = tempfile.mkdtemp(); os.environ["HOME"] = TMP
import device_patterns as D
D.MEM = os.path.join(TMP, "mem"); os.makedirs(D.MEM)
D.time.sleep = lambda *_: None
D._authorize = lambda context, toy, level, kind, pattern="", args=None: (True, "permit", "digest")
calls = []
D.toy_link.send = lambda toy, level, seconds=0, **k: (calls.append(("send", toy, level)) or True)
D.toy_link.rotate = lambda toy, level, seconds=0, **k: (calls.append(("rotate", toy, level)) or True)
D.toy_link.TOYS = {"mission": "a", "tenera": "b", "ridge": "c"}
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:100]) if d else ""))
def receipts():
    p = os.path.join(D.MEM, "effect-receipts.jsonl")
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []

# P03-01: written order; play() for steady is the transport for TOUCH
def fake_play(toy, pattern, args=None, dur=None, permit=None, effect_digest=None, outcome=None):
    lvl = args[0] if args else 0
    calls.append(("send", toy, lvl)); outcome is not None and outcome.update(status="sent", targets={toy: "sent"}); return True
D.play = fake_play
calls.clear(); D.fire_his_intent("[TOUCH: ridge 8] [DO: ridge stop]")
ridge = [c[2] for c in calls if c[1] == "ridge"]
check("P03-01 mixed tags execute in written order: ridge levels [8, 0]", ridge == [8, 0], calls)
check("P03-01 no positive send after the stop", not any(c[2] > 0 for c in calls if c[1] == "ridge" and calls.index(c) > 0) or ridge[-1] == 0, calls)

# P03-02: rotation zero reaches rotate(), never scalar send()
calls.clear(); D.fire_his_intent("[DO: ridge rotate 0]")
check("P03-02 [DO: ridge rotate 0] -> exactly one rotate('ridge', 0)", calls == [("rotate", "ridge", 0)], calls)

# P03-03: broadcast stop cancels the three local loops and sends one zero per concrete device
evs = {t: threading.Event() for t in ("mission", "tenera", "ridge", "thruster")}
D._threads.update(evs)
calls.clear(); D.fire_his_intent("[DO: all stop]")
check("P03-03 all local stop events set", all(e.is_set() for e in evs.values()))
targets = sorted(c[1] for c in calls if c[0] == "send" and c[2] == 0)
check("P03-03 one zero send per concrete target, alias never a device key", targets == ["mission", "ridge", "tenera", "thruster"] and "all" not in targets, calls)

# P02-04: a local thread start is recorded as started, no transport claim
def started_play(toy, pattern, args=None, dur=None, permit=None, effect_digest=None, outcome=None):
    outcome is not None and outcome.update(status="started", targets={toy: "started"}); return True
D.play = started_play
try: os.remove(os.path.join(D.MEM, "effect-receipts.jsonl"))
except FileNotFoundError: pass
D.fire_his_intent("[DO: mission wave 12]")
rc = receipts()
check("P02-04 receipt says started, no 'transport accepted' claim",
      rc and rc[-1]["outcome"] == "started" and "transport accepted" not in rc[-1]["claim"], rc[-1:] )
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

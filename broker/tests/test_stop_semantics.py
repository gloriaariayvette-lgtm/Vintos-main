#!/usr/bin/env python3
"""Stop semantics 76 / 78 / 82 / 83 — durable idempotent stop, stop over corrupt state,
retries never resume, expired or mismatched permits never dispatch.
Fake hub transport, fake thruster, scratch HOME; nothing is written under ~/.vintos."""
import json, os, shutil, sys, tempfile, threading, time, types
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts")
sys.path.insert(0, SCRIPTS)

TMP = tempfile.mkdtemp(prefix="stop-semantics-")
os.environ["HOME"] = TMP                      # every ~ path resolves into the scratch dir
MEM = os.path.join(TMP, ".vintos", "workspace", "memory"); os.makedirs(MEM)


class Response:
    status_code = 200
    def json(self):
        toys = {tid: {"status": "1"} for tid in ("18690ad0e996", "c09b9e4704ae", "f044d37536a9")}
        return {"code": 200, "data": {"toys": toys}}

class Requests:
    calls = []
    @classmethod
    def post(cls, url, json=None, timeout=None):
        cls.calls.append(json); return Response()

sys.modules["requests"] = Requests
_thr = types.ModuleType("thruster_link"); _thr.calls = []
_thr.stop = lambda: _thr.calls.append(("stop",)) or True
_thr.set_speed = lambda level, seconds=0: _thr.calls.append(("set", level)) or True
_thr.play_pattern = lambda s, i=250, sec=0: _thr.calls.append(("pattern", max(s))) or True
sys.modules["thruster_link"] = _thr

import effect_gate as EG
import toy_link as TL
import device_patterns as DP
import device_context as DC

for mod in (EG, DP, DC):
    mod.MEM = MEM
EG.LOG = os.path.join(MEM, "effect-gate.jsonl")
EG.ARMED_FLAG = os.path.join(MEM, ".effect-gate-armed")
EG.STOP_BUTTON = os.path.join(MEM, "hardware-button.json")
EG.TEST_MODE_FLAG = os.path.join(MEM, ".test-mode")
DP.HIS = os.path.join(MEM, "his-touch.json")
DC.STATE = os.path.join(MEM, "device-state.json")
DEVICE_STATE = DC.STATE
DP.time.sleep = lambda *_: None

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:110]) if d else ""))

def hub_sends():
    return [(c.get("toy"), c.get("action")) for c in Requests.calls if c.get("command") == "Function"]
def hub_positive():
    return [s for s in hub_sends() if s[1] not in ("Stop",) and not s[1].endswith(":0")]
def log_rows():
    try: return [json.loads(l) for l in open(EG.LOG)]
    except Exception: return []
def reset():
    Requests.calls[:] = []; _thr.calls[:] = []
    EG._commanded.clear(); EG._execution_owners.clear(); DP._threads.clear()

# ---------------------------------------------------------------- 76
print("--- 76 stop is durable, idempotent desired state ---")
reset(); EG.clear_stop("test start")
check("clean: desired_state running", EG.desired_state() == "running")
r1 = EG.assert_stopped("press 1")
d = json.load(open(EG.STOP_BUTTON))
check("stop writes desired_state=stopped on disk", d.get("desired_state") == "stopped" and d.get("stopped") is True, d)
check("no torn tmp file left beside it", not [f for f in os.listdir(MEM) if f.startswith("hardware-button.json.")], os.listdir(MEM))
r2 = EG.assert_stopped("press 2")
d2 = json.load(open(EG.STOP_BUTTON))
check("second stop is a no-op that re-asserts stopped (not a toggle)", d2.get("desired_state") == "stopped" and d2.get("asserted") == 2, d2)
check("hardware_stopped() reads it", EG.hardware_stopped())
ctx = EG.TurnContext("t76", "chat")
p, mode, why = EG.authorize(ctx, "mission", 12, kind="start", targets={"mission"})
check("a start is refused while stopped (disarmed too)", mode == "deny" and p is None and "stop" in why, (mode, why))
p, mode, why = EG.authorize(ctx, "mission", 12, kind="pattern", targets={"mission"})
check("a pattern start is refused while stopped", mode == "deny", (mode, why))
p, mode, why = EG.authorize(None, "mission", 0, kind="start")
check("a zero still passes while stopped", mode == "send")
check("toy_link.send(mission, 12) sends nothing while stopped", not TL.send("mission", 12) and not hub_positive(), hub_sends())
# the full stop path via stop_all is idempotent too
reset(); a = TL.stop_all("press A"); zeros_a = len(hub_sends()); b = TL.stop_all("press B")
check("stop_all twice: zeros both times, state still stopped", a and b and len(hub_sends()) == 2 * zeros_a and EG.desired_state() == "stopped", hub_sends())
EG.clear_stop("explicit resume")
p, mode, why = EG.authorize(ctx, "mission", 12, kind="start", targets={"mission"})
check("only an explicit resume/clear lets a start through again", mode == "send" and p is not None, (mode, why))

# ---------------------------------------------------------------- 78
print("\n--- 78 stop recovers from corrupt state ---")
reset()
open(EG.STOP_BUTTON, "w").write("{ this is not json")
open(DEVICE_STATE, "w").write("[[[ torn")
check("a corrupt desired-state file reads as NOT running (fail closed)", EG.desired_state() == "corrupt" and EG.hardware_stopped())
raised = None
try: ok = TL.stop_all("corrupt press")
except Exception as e: raised = e
check("stop_all never raises over corrupt files", raised is None, raised)
check("zeros went to every hub toy", sorted(t for t, a in hub_sends() if a == "Stop") == sorted(TL.TOYS.values()), hub_sends())
check("and to the thruster", ("stop",) in _thr.calls, _thr.calls)
d = json.load(open(EG.STOP_BUTTON))
check("desired-state rewritten clean: stopped", d.get("desired_state") == "stopped", d)
st = json.load(open(DEVICE_STATE))
check("device-state rewritten clean: every device still at 0",
      all(st[t]["intensity"] == 0 and st[t]["pattern"] == "still" for t in list(TL.TOYS) + ["thruster"]), st)
os.remove(EG.STOP_BUTTON); os.remove(DEVICE_STATE)
raised = None
try: TL.stop_all("absent files")
except Exception as e: raised = e
check("stop_all over ABSENT files never raises and leaves stopped on disk",
      raised is None and json.load(open(EG.STOP_BUTTON)).get("desired_state") == "stopped")
_real_aw = EG._atomic_write_json
EG._atomic_write_json = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
reset(); raised = None
try: TL.stop_all("disk full")
except Exception as e: raised = e
EG._atomic_write_json = _real_aw
check("even an unwritable disk: stop still sends zeros, never raises",
      raised is None and len([1 for t, a in hub_sends() if a == "Stop"]) == 3 and ("stop",) in _thr.calls, hub_sends())

# ---------------------------------------------------------------- 82
print("\n--- 82 retries and replays never resume a device ---")
reset(); EG.assert_stopped("82")
sent = []
_real_send = TL.send
TL.send = lambda toy, level, seconds=0, **k: sent.append((toy, level)) or True
ev = threading.Event()
DP._run("mission", "throb", [14], ev, None)                       # a live pattern loop ticking after a stop
check("pattern thread aborts: only a zero is sent, never a level", sent == [("mission", 0)] and ev.is_set(), sent)
sent[:] = []
lib = os.path.join(MEM, "gcs-saved-patterns.json")
json.dump([{"patterns": {"mission": "cake", "tenera": "wave3"}}], open(lib, "w"))
out = {}
check("saved/last replay refused while stopped", DP.play("both", "last", outcome=out) is False and sent == [] and not hub_positive(), (out, sent, hub_sends()))
out = {}
check("a named preset refused while stopped", DP.play("mission", "cake", outcome=out) is False and out.get("status") == "refused:stopped" and not hub_positive(), out)
check("a steady level refused while stopped", DP.play("mission", "steady", [8]) is False and sent == [], sent)
check("rotate refused while stopped", DP.play("ridge", "rotate", ["mid"]) is False and not hub_positive())
check("a zero (still) still goes through", DP.play("mission", "still") is True and sent == [("mission", 0)], sent)
sent[:] = []
EG.claim_execution({"mission"}, "lease-1")
check("a stop retry (lease expiry) only ever sends zeros", DP._stop_if_owned(["mission"], "lease-1") == ["mission"] and sent == [("mission", 0)], sent)
sent[:] = []
DP.fire_his_intent("[DO: mission cake 14] [TOUCH: tenera 10]", EG.TurnContext("t82", "avatar"))
check("a whole reply of starts fires nothing while stopped", sent == [] and not hub_positive(), (sent, hub_sends()))
TL.send = _real_send
# a permit issued BEFORE the stop cannot carry a tick through afterwards
EG.clear_stop("re-arm for 82b"); reset()
p, mode, _ = EG.authorize(EG.TurnContext("t82b", "chat"), "mission", 14, kind="pattern", targets={"mission"}, digest="D")
p.consume(); EG.assert_stopped("82b")
check("a pre-stop permit's lease is dead once stopped", not p.lease().live())
check("a pre-stop permit still cannot start a pattern once stopped", not TL.send_pattern("mission", [4, 14], permit=p, effect_digest="D") and not hub_positive(), hub_sends())
# corrupt button: replay/retry stays refused (fail closed), not silently resumed
open(EG.STOP_BUTTON, "w").write("garbage"); sent[:] = []
check("a corrupt desired-state refuses a replay too", DP.play("mission", "last") is False and not hub_positive())
EG.clear_stop("end 82")

# ---------------------------------------------------------------- 83
print("\n--- 83 an expired or mismatched permit cannot dispatch ---")
reset()
def fresh(kind="start", targets=("mission",), maximum=12, digest="D"):
    p, mode, why = EG.authorize(EG.TurnContext("t83", "chat"), "mission", maximum, kind=kind, targets=set(targets), digest=digest)
    assert mode == "send" and p is not None, (mode, why)
    p.consume(); return p
def denied_for(reason):
    return any(r.get("decision") == "deny" and r.get("why") == reason for r in log_rows())
check("a permit carries an expiry and its operation + device", all(hasattr(fresh(), a) for a in ("expires", "kind", "targets", "digest", "maximum")))
for armed in (False, True):
    tag = "armed" if armed else "disarmed"
    if armed: open(EG.ARMED_FLAG, "w").write("")
    elif os.path.exists(EG.ARMED_FLAG): os.remove(EG.ARMED_FLAG)
    reset(); p = fresh(); p.expires = (datetime.now() - timedelta(seconds=1)).isoformat()
    check("%s: expired permit does not dispatch, reason recorded" % tag, not TL.send("mission", 8, permit=p, effect_digest="D") and not hub_positive() and denied_for("permit_expired"), hub_sends())
    reset(); p = fresh()
    check("%s: permit for mission cannot fire tenera" % tag, not TL.send("tenera", 8, permit=p, effect_digest="D") and not hub_positive() and denied_for("permit_target_mismatch"))
    reset(); p = fresh(kind="start")
    check("%s: a start permit cannot run a pattern" % tag, not TL.send_pattern("mission", [4, 8], permit=p, effect_digest="D") and not hub_positive() and denied_for("permit_kind_mismatch"))
    reset(); p = fresh(kind="start")
    check("%s: a start permit cannot rotate" % tag, not TL.rotate("mission", 8, permit=p, effect_digest="D") and not hub_positive())
    reset(); p = fresh()
    check("%s: wrong digest refused" % tag, not TL.send("mission", 8, permit=p, effect_digest="OTHER") and not hub_positive() and denied_for("permit_digest_mismatch"))
    reset(); p = fresh(maximum=10)
    check("%s: above the authorized maximum refused" % tag, not TL.send("mission", 11, permit=p, effect_digest="D") and not hub_positive() and denied_for("permit_maximum_exceeded"))
    reset(); p = fresh()
    check("%s: the matching permit dispatches" % tag, TL.send("mission", 8, permit=p, effect_digest="D") and hub_positive() == [(TL.TOYS["mission"], "Vibrate:8")], hub_sends())
    reset(); p = fresh(); p.expires = (datetime.now() - timedelta(seconds=1)).isoformat(); EG.note_commanded("mission", 8)
    check("%s: an expired permit still lets a ZERO through (reduction)" % tag, TL.send("mission", 0, permit=p, effect_digest="D") and hub_sends() == [(TL.TOYS["mission"], "Vibrate:0")], hub_sends())
if os.path.exists(EG.ARMED_FLAG): os.remove(EG.ARMED_FLAG)

check("nothing was written under the real home", not os.path.exists(os.path.join(TMP, "hardware-button.json")) and os.listdir(MEM))
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

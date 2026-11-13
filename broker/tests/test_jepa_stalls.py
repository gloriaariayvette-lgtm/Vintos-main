#!/usr/bin/env python3
"""JEPA predictor stalls (13 November): after-reply forecasts, targets already sent, qualified self axis,
the served Gloria head, the pre-registered evaluation, and the unchanged retrain bar.

Every behaviour check is also run against a mutant of the code it protects; the mutant must fail it.
Scratch HOME and SPARK_WORKSPACE before any import; stub encoder; `requests` fails the suite if anything sends."""
import json, os, sys, tempfile, types, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="jepa-stalls-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import numpy as np
sys.path.insert(0, os.path.join(REPO, "scripts"))
import jepa_predictor as JP
import jepa_ranking_audit as RA
import jepa_calibration_audit as CA
import jepa_self_head as SH

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:400]) if d and not ok else ""))

def mutant(mod, old, new):
    """The module with one edit; the edit must exist exactly once."""
    src = open(mod.__file__).read()
    assert src.count(old) == 1, "mutation anchor not unique: %r" % old
    m = types.ModuleType(mod.__name__ + "_mutant"); m.__file__ = mod.__file__
    exec(compile(src.replace(old, new), mod.__file__, "exec"), m.__dict__)
    return m

def killed(name, probe, mod, old, new):
    try:
        survived = bool(probe(mutant(mod, old, new)))
    except Exception:
        survived = False
    check("mutation killed: " + name, not survived)

check("every path is scratch", all(str(p).startswith(HOME) for p in (JP.MEMORY, JP.CHAT, JP.OUT, JP.SHADOW_MODEL, RA.MEM, RA.SELF_FORECASTS, CA.MEM)))
iso = lambda t: datetime.fromtimestamp(t).isoformat()

# ------------------------------------------------------------------ 1. after-reply forecasts
print("--- 1. the forecast is made after his reply lands, before her next message ---")
T0 = time.time() - 600
ARR = T0 + 100                      # her message reached the door
OLD = [{"role": "user", "content": "earlier words", "timestamp": iso(T0)},
       {"role": "assistant", "content": "earlier reply", "timestamp": iso(T0 + 20)}]
LANDED = OLD + [{"role": "user", "content": "her words", "timestamp": iso(ARR + 25)},     # written with his reply
                {"role": "assistant", "content": "his reply", "timestamp": iso(ARR + 25)}]

class Enc:
    def encode(self, texts, **kw):
        return np.asarray([[1.0, 0.0] for _ in texts])

REAL_PREDICT = JP.predict
def run_after(J, rows, newer_log=None, newer_pending=False, shadow=False, clock_start=None):
    calls, slept, built = [], [], []
    J.load = lambda p, d=None: list(rows) if p == J.CHAT else d
    J.predict = lambda *a, **k: calls.append((a, k)) or {"state": "WRITTEN"}
    log = os.path.join(MEM, "jepa-self-forecasts.jsonl"); pend = os.path.join(MEM, "jepa-self-pending")
    for p in (log, J.SHADOW_MODEL):
        if os.path.exists(p): os.remove(p)
    os.makedirs(pend, exist_ok=True)
    for f in os.listdir(pend): os.remove(os.path.join(pend, f))
    if newer_log: open(log, "w").write(json.dumps({"arrived_at": newer_log, "her_key": "k"}) + "\n")
    if newer_pending: open(os.path.join(pend, "%d-abc.json" % int((ARR + 40) * 1000)), "w").write("{}")
    if shadow: open(J.SHADOW_MODEL, "w").write("x")
    clock = [clock_start if clock_start is not None else ARR + 30]
    def sleep(s): slept.append(s); clock[0] += s
    enc = Enc()
    out = J.after_reply(ARR, enc=None, wait=60, poll=5, sleep=sleep, clock=lambda: clock[0],
                        encoder_factory=lambda: built.append(1) or enc)
    return out, calls, slept, built

def probe_landed(J):
    out, calls, _, built = run_after(J, LANDED, shadow=True)
    prod = [k for a, k in calls if not k.get("shadow")]; shad = [k for a, k in calls if k.get("shadow")]
    return (out["state"] == "FORECAST" and len(prod) == 1 and prod[0]["trigger"] == "after_reply"
            and prod[0]["side_feeds"] is False and isinstance(prod[0]["enc"], Enc) and len(shad) == 1
            and shad[0]["enc"] is prod[0]["enc"] and len(built) == 1)
check("his reply landed: one production and one shadow forecast, trigger after_reply, side feeds left to the cron, one shared encoder", probe_landed(JP))
killed("side feeds left on", probe_landed, JP, 'trigger="after_reply", side_feeds=False', 'trigger="after_reply", side_feeds=True')

def probe_waits(J):
    out, calls, slept, built = run_after(J, OLD)
    return out["state"] == "NO_REPLY" and not calls and not built and len(slept) >= 5
check("an older reply of his is not the reply to this message: it waits, gives up, never loads an encoder", probe_waits(JP))
killed("reply state ignores her arrival", probe_waits, JP, "at is not None and at >= arrived_at - 1", "at is not None")

def probe_superseded(J):
    a = run_after(J, LANDED, newer_log=ARR + 40)
    b = run_after(J, LANDED, newer_pending=True)
    return a[0]["state"] == b[0]["state"] == "SUPERSEDED" and not a[1] and not b[1]
check("she wrote again: that message's own job forecasts; this one makes none", probe_superseded(JP))
killed("newer-arrival check removed", probe_superseded, JP, "if _newer_arrival(arrived_at):", "if False:")
out, calls, _, _ = run_after(JP, LANDED, newer_log=ARR - 1)
check("an older message in the log does not supersede", out["state"] == "FORECAST" and len(calls) == 1)
JP.load = JP._ev_load; JP.predict = REAL_PREDICT

src = open(JP.__file__).read()
check("history rows record trigger and the window's last role; the latent stream and LAM run only when side feeds are on",
      '"trigger": trigger, "context_last_role"' in src and "if not shadow and side_feeds:" in src
      and "if not shadow and side_feeds and os.path.exists" in src and "enc = enc or encoder()" in src)
check("forecast writers are serialized by a lock on the output", "lk = _forecast_lock(out_path)" in src and "fcntl.LOCK_EX" in src)

# the on-message job hands over to the after-reply forecast
seen = []
REAL_JP = SH._jp
SH._jp = lambda: types.SimpleNamespace(after_reply=lambda arrived, **k: seen.append((arrived, k)) or {"state": "FORECAST"})
check("a fresh pending row hands its arrival to the after-reply forecast",
      SH.after_reply_job({"arrived_at": time.time() - 5}) == {"state": "FORECAST"} and len(seen) == 1)
check("a stale pending row forecasts nothing", SH.after_reply_job({"arrived_at": time.time() - SH.PENDING_MAX_AGE - 5}) is None and len(seen) == 1)
SH._jp = REAL_JP
shsrc = open(SH.__file__).read()
check("the on-message command reads the row, runs its forecast, then the after-reply forecast",
      "_pending = _load_json(sys.argv[2], {})" in shsrc and shsrc.index("on_message_job(sys.argv[2])") < shsrc.index("after_reply_job(_pending)"))

# ------------------------------------------------------------------ 2. targets already sent
print("--- 2. a Gloria target she had already sent is not an outcome ---")
B = 1.75e9
hist = [{"checkpoint_id": "ck", "ts": B + 100, "iso": iso(B + 100), "trigger": "after_reply", "context_last_role": "assistant",
         "gloria": {"confidence": .6, "decode_similarity": .5, "emb": [1.0, 0.0]},
         "self": {"confidence": .6, "decode_similarity": .5, "emb": [1.0, 0.0]}}]
turns = [(B + 200, "next words of hers", "his next reply")]
key = SH.her_key("next words of hers")
def probe_known(C):
    after = C.joined_rows(hist, turns, Enc(), "ck", 0, arrivals={key: [B + 150]})
    before = C.joined_rows(hist, turns, Enc(), "ck", 0, arrivals={key: [B + 90]})
    ended = C.joined_rows([dict(hist[0], context_last_role="user")], turns, Enc(), "ck", 0, arrivals={})
    return (after[0]["g_err"] is not None and before[0]["g_err"] is None and before[0]["s_err"] is not None
            and ended[0]["g_err"] is None)
check("calibration join: arrival after the forecast counts; before it, or a window ending on her message, does not (self unaffected)", probe_known(CA))
killed("calibration guard removed", probe_known, CA, "if ax == \"g\" and gloria_target_known(h, target[0], target[index], arrivals):",
       "if False:")
killed("arrival comparison dropped", probe_known, RA, "return any(target_ts - ARRIVAL_WINDOW <= a <= fts for a in arrivals.get(key, ()))", "return False")

led = [{"timestamp": iso(B + i * 10), "gloria": "her %d" % i, "vintos": "his %d" % i} for i in range(4)]
led.append({"timestamp": iso(B + 200), "gloria": "next words of hers", "vintos": "his next reply"})
fc = [dict(hist[0], ts=B + 100, context_emb=[1.0, 0.0])]
def probe_rank(A):
    kept = [r for r in A.evaluate(fc, led, Enc(), checkpoint="ck", arrivals={key: [B + 150]}) if r["head"] == "gloria"]
    dropped = [r for r in A.evaluate(fc, led, Enc(), checkpoint="ck", arrivals={key: [B + 90]}) if r["head"] == "gloria"]
    return len(kept) == 1 and len(dropped) == 0
check("ranking audit applies the same rule", probe_rank(RA))
killed("ranking guard removed", probe_rank, RA, 'if head == "gloria" and gloria_target_known(', 'if False and gloria_target_known(')
open(RA.SELF_FORECASTS, "w").write(json.dumps({"her_key": key, "arrived_at": B + 90}) + "\n" + "not json\n")
check("arrivals are read from the on-message log, malformed lines skipped", RA.load_arrivals() == {key: [B + 90]})

# ------------------------------------------------------------------ 3. the self axis is measured
print("--- 3. an axis is measured on its qualified rows ---")
rows = [{"iso": "2026-11-%02d" % (i + 1), "s_conf": 1 - i / 20, "s_dsim": (i * 7 % 5) / 5, "s_err": i / 20} for i in range(15)]
rows += [{"iso": "2026-11-%02d" % (16 + i), "s_conf": None, "s_dsim": .4, "s_err": .9} for i in range(3)]
import calibration as CAL
def probe_axis(C):
    s = C.axis_stats(rows, "s", CAL.holdout)
    return (s.get("monotonicity_conf_vs_err") == -1.0 and s["n_unqualified_left_out"] == 3 and s["n_measured"] == 15
            and s["n_holdout"] == 5 and "unmeasured" not in s)
check("placeholders (the latest rows here) are left out and counted; the axis is scored on 15 qualified rows", probe_axis(CA))
killed("qualification filter removed", probe_axis, CA, "measured = [r for r in axis_rows if r[ax + \"_conf\"] is not None and r[ax + \"_dsim\"] is not None]", "measured = axis_rows")
check("no qualified row at all is still reported unmeasured", "unmeasured" in CA.axis_stats([dict(r, s_conf=None) for r in rows], "s", CAL.holdout))

# ------------------------------------------------------------------ 4. the served Gloria head
print("--- 4. the Gloria triple the forecast served is measured on its own rows ---")
mk = lambda t, ck: {"checkpoint_id": "pt", "ts": t, "iso": iso(t), "gloria": {"source": CA.READOUT_SCHEMA, "checkpoint_id": ck,
                    "confidence": .5, "decode_similarity": .5, "emb": [1.0, 0.0]}}
served_hist = [mk(B + 10, "R"), mk(B + 110, "R"), mk(B + 160, "other")]
served_turns = [(B + 50, "a", ""), (B + 150, "b", ""), (B + 170, "c", "")]
def probe_served(C):
    rs = C.joined_rows(served_hist, served_turns, Enc(), None, None, arrivals={}, served=("R", B + 100))
    return len(rs) == 1 and rs[0]["g_err"] is not None and "s_err" not in rs[0]
check("only the installed readout's rows after its install time are joined; self is not scored there", probe_served(CA))
killed("served checkpoint not matched", probe_served, CA, 'or triple.get("checkpoint_id") != served[0]:', ':')

# ------------------------------------------------------------------ 5. the pre-registered evaluation
print("--- 5. the registered evaluation: first 30 after-reply targets, scored once ---")
rng = np.random.default_rng(7)
def prow(i, conf, err, dsim, trig="after_reply", day="2026-11-20"):
    return {"iso": day + "T10:%02d" % (i % 60), "ts": B + i, "trigger": trig, "g_conf": conf, "g_err": err, "g_dsim": dsim}
good = [prow(i, 1 - i / 40, i / 40, float(rng.random())) for i in range(30)]
bad_later = [prow(100 + i, i / 40, i / 40, float(rng.random())) for i in range(60)]
P = CA.preregistered
check("29 rows are still collecting", P(good[:29], [])["legacy"]["state"] == "COLLECTING")
check("cron rows and rows before registration do not count", P([dict(r, trigger="cron") for r in good], [])["legacy"]["state"] == "COLLECTING"
      and P([dict(r, iso="2026-11-12T10:00") for r in good], [])["legacy"]["state"] == "COLLECTING")
def probe_first(C):
    v = C.preregistered(good + bad_later, good)
    return v["legacy"]["state"] == "PASS" and v["legacy"]["n"] == 30 and v["served"]["state"] == "PASS"
check("monotone confidence passes; later contrary rows never change the verdict", probe_first(CA))
killed("scored on the latest rows instead of the first", probe_first, CA, 'first = elig[:reg["n"]]', 'first = elig[-reg["n"]:]')
tied = [dict(r, g_dsim=r["g_conf"]) for r in good]
check("matching the decode-similarity control is a FAIL", P(tied, [])["legacy"]["state"] == "FAIL")
check("the registration is versioned in code and uses the calibration v2 numbers",
      CA.PREREGISTERED["registered"] == "2026-11-13" and CA.PREREGISTERED["n"] == 30
      and CA.PREREGISTERED["pass"] == {"max_monotonicity": CAL.CRITERIA["max_monotonicity"], "beat_control_by": CAL.CRITERIA["beat_control_by"]})

# ------------------------------------------------------------------ 6. the retrain bar is unchanged
print("--- 6. no bar was lowered ---")
open(JP.MODEL, "w").write("weights"); ck = JP.checkpoint_fingerprint(JP.MODEL)
json.dump({"checkpoint": ck, "gloria": {"n": 63}, "self": {"n": 56}}, open(JP.RANKING_AUDIT, "w"))
json.dump({"checkpoint": ck, "n_joined": 64, "n_holdout": 21}, open(JP.CALIBRATION_AUDIT, "w"))
ready, rec = JP.retrain_readiness()
check("21 held-out outcomes still hold the retrain (minimum 30)", not ready and rec["state"] == "HELD_NEEDS_REALIZED_OUTCOMES"
      and JP.MIN_CALIBRATION_HOLDOUT_FOR_RETRAIN == 30 and JP.MIN_REALIZED_FOR_RETRAIN == 30)
json.dump({"checkpoint": ck, "n_joined": 90, "n_holdout": 30}, open(JP.CALIBRATION_AUDIT, "w"))
check("30 held-out outcomes release it", JP.retrain_readiness()[0] is True)

# ------------------------------------------------------------------ 7. a real forecast, when torch is installed
try:
    import torch
    real_torch = hasattr(torch, "nn")
except Exception:
    real_torch = False
if real_torch:
    print("--- 7. a real forecast row (torch present) ---")
    net = JP.make_net(2); torch.save({"state": net.state_dict(), "dim": 2, "presence_trained": False}, JP.MODEL)
    chat = [{"role": ("user" if i % 2 == 0 else "assistant"), "content": "turn %d" % i, "timestamp": iso(time.time() - 3000 + i * 60)} for i in range(14)]
    json.dump(chat, open(JP.CHAT, "w"))
    called = []
    sys.modules["latent_feed"] = types.SimpleNamespace(refresh=lambda **k: called.append("latent"))
    hp = os.path.join(MEM, "hist.jsonl")
    JP.predict(history_path=hp, enc=Enc(), trigger="after_reply", side_feeds=False)
    row = json.loads(open(hp).read().splitlines()[-1])
    check("the history row says after_reply and that the window ended on his reply; the latent stream was not advanced",
          row["trigger"] == "after_reply" and row["context_last_role"] == "assistant" and called == [])
    again = JP.predict(history_path=hp, enc=Enc(), trigger="cron")
    check("the same window is not forecast twice", again.get("state") == "UNCHANGED_CONTEXT" and len(open(hp).read().splitlines()) == 1)
    def probe_feeds(J):
        del called[:]
        for p in (J.OUT, hp):
            if os.path.exists(p): os.remove(p)
        J.predict(history_path=hp, enc=Enc(), trigger="after_reply", side_feeds=False)
        return called == [] and json.loads(open(hp).read().splitlines()[-1])["trigger"] == "after_reply"
    check("probe: an after-reply forecast leaves the latent stream alone", probe_feeds(JP))
    killed("latent stream advanced by after-reply forecasts", probe_feeds, JP, "if not shadow and side_feeds:", "if not shadow:")
else:
    print("SKIP 7. real forecast row: torch not installed in this interpreter")

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

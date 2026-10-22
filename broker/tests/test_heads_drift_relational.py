#!/usr/bin/env python3
"""drift_head and relational_head carry a permutation null (review of the JEPA heads, 16 October). Their coherence on
a stationary series sat at 0.125 and was read as movement; novelty was highest when nothing moved, and the relational
hint told him "steady toward something newly-shaped" on noise. Now each number has a p-value, a "moving / not
distinguishable from no movement" verdict, and the hint speaks only when the series is moving. Drift leaves out
today's partial day file.

Scratch HOME and SPARK_WORKSPACE are set before import; the encoder is a stub; `requests` is a stub that fails the
suite if anything tries to send."""
import json, os, sys, tempfile, types, hashlib
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="heads-drift-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
SENT = []
def no_network(*a, **k): SENT.append(a); raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import numpy as np

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:400]) if d and not ok else ""))

VECS = {}
SEEN = []
class Enc:
    def encode(self, texts, show_progress_bar=False):
        out = []
        for t in texts:
            SEEN.append(str(t))
            v = VECS.get(str(t))
            if v is None:
                h = int(hashlib.md5(str(t).encode()).hexdigest()[:8], 16)
                v = np.random.default_rng(h).normal(size=32)
            out.append(np.asarray(v, dtype="float32"))
        return np.asarray(out)
sys.modules["jepa_predictor"] = types.SimpleNamespace(encoder=lambda: Enc())

import drift_head as DH, relational_head as RH
check("every path they write is scratch", all(p.startswith(HOME) for p in (DH.OUT, DH.MEMORY, RH.OUT, RH.MEMORY, RH.LEDGER)))
check("the sender is a stub", sys.modules["requests"].post is no_network)

def unit(M): M = np.asarray(M, dtype="float32"); return M / np.linalg.norm(M, axis=1, keepdims=True)
def stationary(seed, n=16, d=32):
    r = np.random.default_rng(seed); c = r.normal(size=d) * 4
    return unit(c + r.normal(size=(n, d)))
def drifting(seed, n=16, d=32):
    r = np.random.default_rng(seed); c = r.normal(size=d) * 4; dirn = r.normal(size=d); dirn /= np.linalg.norm(dirn)
    return unit(np.asarray([c + i * 1.2 * dirn + 0.3 * r.normal(size=d) for i in range(n)]))

print("--- the permutation null ---")
st = DH.movement_test(stationary(3))
check("a stationary self is not distinguishable from no movement", st["moving"] is False and st["p_value"] >= 0.05, st["p_value"])
check("and says so in words", st["movement"] == "not distinguishable from no movement")
check("the null mean is reported beside the number", 0 < st["null_mean_coherence"] < 1 and "drift_p_value" in st)
dr = DH.movement_test(drifting(2))
check("a steady drift is detected", dr["moving"] is True and dr["p_value"] < 0.05, dr["p_value"])
fires = sum(DH.movement_test(stationary(1000 + i))["moving"] for i in range(200))
check("on stationary series it calls movement about 5% of the time, not always", fires <= 18, fires)
hits = sum(DH.movement_test(drifting(2000 + i))["moving"] for i in range(20))
check("and a steady drift nearly every time", hits >= 18, hits)

print("--- drift_head: today's partial day is not a day ---")
today = date.today()
for i in range(10, 0, -1):
    day = (today - timedelta(days=i)).isoformat()
    # The content is the same noise whatever today is: written from the date, it was new noise every day, and on
    # 20 October that day's noise fell in the 5% a stationary series is (correctly) called moving, p 0.0299. The
    # file names stay real dates: the head leaves out today's partial file by the real date.
    open(os.path.join(MEM, "daily-inner-life-%s.md" % day), "w").write(("day number %d " % i) * 200)
open(os.path.join(MEM, "daily-inner-life-%s.md" % today.isoformat()), "w").write("# Daily inner life\n(started)")
open(os.path.join(MEM, "daily-inner-life-%s-short.md" % (today - timedelta(days=11)).isoformat()), "w").write("tiny")
series, source = DH.build_self_series()
labels = [l for l, _ in series]
check("today's file is left out", today.isoformat() not in labels and source == "daily-inner-life", labels)
check("a file too short to be a day is left out", not any(l.endswith("-short") for l in labels), labels)
check("the ten whole days are in", len(series) == 10, len(series))
DH.main()
d = json.load(open(DH.OUT))
check("drift.json carries p-value, null and verdict",
      all(k in d for k in ("p_value", "drift_p_value", "null_mean_coherence", "moving", "movement")), sorted(d))
check("random days are not called movement", d["moving"] is False and d["movement"] == "not distinguishable from no movement", d.get("p_value"))
check("novelty is null when nothing is moving (raw kept)", d["novelty"] is None and d["novelty_raw"] is not None)
check("confidence is 0 when nothing is moving", d["confidence"] == 0.0)
check("the verdict is not named 'significant' (drift_reason's LLM flag would overwrite it)", "significant" not in d)
check("the window ends on yesterday, not today's header", d["to_label"] == (today - timedelta(days=1)).isoformat(), d["to_label"])

print("--- relational_head: the hint speaks only on movement ---")
json.dump({"trajectory": 0.145, "novelty": 0.75, "confidence": 0.137}, open(RH.OUT, "w"))
check("a file written before the test existed says nothing", RH.get_relational_hint() == "")
json.dump({"trajectory": 0.145, "novelty": None, "novelty_raw": 0.75, "moving": False, "p_value": 0.48,
           "movement": "not distinguishable from no movement"}, open(RH.OUT, "w"))
check("not distinguishable from no movement: no hint", RH.get_relational_hint() == "")
json.dump({"trajectory": 0.3, "novelty": 0.6, "moving": True, "p_value": 0.01, "movement": "moving"}, open(RH.OUT, "w"))
h = RH.get_relational_hint()
check("significant movement is not a held-out future prediction: no hint", h == "", h)

photo = ("[Gloria sent you a photo. What your eyes saw:]\nA kitchen counter, a red mug.\n\n"
         "[Gloria's message with the photo:] look what I made")
rows = []
for i in range(12):
    day = (today - timedelta(days=12 - i)).isoformat()
    rows.append({"timestamp": day + "T10:00:00", "gloria": photo if i == 5 else "hello on day %d" % i, "vintos": "reply %d" % i})
json.dump(rows, open(RH.LEDGER, "w"))
SEEN.clear()
RH.main()
r = json.load(open(RH.OUT))
check("relational.json carries p-value and verdict", all(k in r for k in ("p_value", "moving", "movement", "null_mean_coherence")), sorted(r))
check("random days: not moving, novelty null, no hint", r["moving"] is False and r["novelty"] is None and RH.get_relational_hint() == "")
joined = "\n".join(SEEN)
check("her photo turn is her words, never the description", "(she sent a photo) look what I made" in joined and "red mug" not in joined)
check("nothing was sent", SENT == [])

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

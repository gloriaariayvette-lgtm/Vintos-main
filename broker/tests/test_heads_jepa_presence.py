#!/usr/bin/env python3
"""jepa_predictor's SELF and PRESENCE heads (review of the JEPA heads, 16 October). The gloria head is being retrained
by Gloria and is not touched; this suite checks only the prediction side of the other two:

  - presence: no placeholder 0.5 confidence; a prospective holdout audit against the mean baseline; and the head is
    not offered to the live loop (`presence`) until it beats that mean on held-out replies;
  - self/presence: the one-day window their training uses applies at prediction too: a live window that straddles
    more than a day is out of their training distribution and is not called qualified. Self keeps its 0.5 stand-in
    (a reader float()s it unguarded) but marks it as one.

Scratch HOME and SPARK_WORKSPACE are set before import. torch, the encoder and the network are stubs; `requests` is a
stub that fails the suite if anything tries to send."""
import json, os, sys, tempfile, types, hashlib
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="heads-jepa-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import numpy as np

class T(np.ndarray):
    def numpy(self): return np.asarray(self)
class _NoGrad:
    def __enter__(self): return self
    def __exit__(self, *a): return False
CK = {"dim": 8, "state": {}, "presence_trained": True, "architecture": "shared-v1", "context_schema": "legacy-concat-v1"}
sys.modules["torch"] = types.SimpleNamespace(load=lambda f: CK, tensor=lambda x: np.asarray(x, dtype="float32").view(T),
                                             no_grad=_NoGrad)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import jepa_predictor as JP

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:500]) if d and not ok else ""))
check("every path it writes is scratch", all(p.startswith(HOME) for p in (
    JP.MEMORY, JP.CHAT, JP.AUDIT, JP.MODEL, JP.OUT, JP.PRESENCE_CALIBRATION, JP.CALIBRATION_AUDIT, JP.LEDGER_FLOOR_FILE)))
check("torch and the sender are stubs", sys.modules["torch"].load.__name__ == "<lambda>" and sys.modules["requests"].post is no_network)

class Enc:
    def encode(self, texts, show_progress_bar=False):
        return np.asarray([np.random.default_rng(int(hashlib.md5(str(t).encode()).hexdigest()[:8], 16)).normal(size=8)
                           for t in texts], dtype="float32")
JP.encoder = lambda: Enc()
P = {"value": 0.9}
class Net:
    def load_state_dict(self, s): pass
    def eval(self): pass
    def __call__(self, x):
        x = np.asarray(x, dtype="float32"); n = len(x)
        lv = np.stack([x[:, 0], x[:, 1], x[:, 2]], axis=1)
        return (x.view(T), (x * 0.5).view(T), np.full((n, 1), P["value"], dtype="float32").view(T), lv.view(T))
JP.make_net = lambda dim, architecture="shared-v1": Net()

def scenario(name, start, n=44, n_before=20, train_comp=0.5, hold_comp=0.9):
    """n alternating turns from `start`, one minute apart; the checkpoint is trained after turn n_before."""
    rows = []
    for i in range(n):
        t = (start + timedelta(minutes=i)).isoformat()
        rows.append({"role": "user" if i % 2 == 0 else "assistant", "content": "%s turn %d" % (name, i), "timestamp": t})
    json.dump(rows, open(JP.CHAT, "w"))
    json.dump([{"id": JP._rid(r), "composite": (train_comp if i < n_before else hold_comp), "timestamp": r["timestamp"]}
               for i, r in enumerate(rows) if r["role"] == "assistant"], open(JP.AUDIT, "w"))
    model = os.path.join(MEM, "model-%s.pt" % name); open(model, "wb").write(b"ckpt-" + name.encode())
    ck_at = (start + timedelta(minutes=n_before - 0.5)).timestamp(); os.utime(model, (ck_at, ck_at))
    out = os.path.join(MEM, "prediction-%s.json" % name)
    JP.predict(model, out, os.path.join(MEM, "history-%s.jsonl" % name))
    return json.load(open(out)), [json.loads(l) for l in open(os.path.join(MEM, "history-%s.jsonl" % name))]

print("--- the training window, at prediction ---")
check("same day is inside", JP._within_training_window("2026-10-15T23:00:00", "2026-10-16"))
check("the next day is inside", JP._within_training_window("2026-10-15T01:00:00", "2026-10-16"))
check("two days apart is outside", not JP._within_training_window("2026-10-14T23:00:00", "2026-10-16"))

print("--- a live window from ten days ago ---")
old, hist = scenario("old", datetime.now() - timedelta(days=10))
check("self is not called qualified outside its training window",
      old["qualification"]["self"] == "outside_training_window" and old["self"]["confidence_placeholder"] is True, old["qualification"])
check("self keeps the 0.5 stand-in, marked (a reader float()s it)", old["self"]["confidence"] == 0.5)
check("the history marks the stand-in too", hist[-1]["self"]["confidence_placeholder"] is True)
check("presence confidence is null, not a placeholder 0.5",
      old["presence_forecast"]["confidence"] is None and old["qualification"]["presence"] == "outside_training_window", old["presence_forecast"])
cal = json.load(open(JP.PRESENCE_CALIBRATION))
check("presence holdout audit is written for this checkpoint", cal.get("checkpoint") == old["checkpoint_id"] and "state" in cal, cal)

print("--- today, presence beats the mean on held-out replies ---")
start = datetime.now() - timedelta(hours=2)
rel, _ = scenario("released", start, train_comp=0.5, hold_comp=0.9)
pc = rel["presence_calibration"]
check("12 replies said after the checkpoint are its holdout; 7 before (with a full context) are its baseline",
      pc["n_holdout"] == 12 and pc["n_training_era"] == 7, pc)
check("head error 0 against the mean's 0.4: RELEASED", pc["state"] == "RELEASED" and pc["mae_head"] < pc["mae_baseline"], pc)
check("only then is presence offered to the live loop", rel["presence"] is not None and rel["presence"]["steering_allowed"] is True)
check("and it carries its prediction id and time, so staleness is visible",
      rel["presence"]["prediction_id"] == rel["prediction_id"] and rel["presence"]["predicted_at"] == rel["predicted_at"])
check("inside the window self is qualified again", rel["qualification"]["self"] == "qualified" and rel["self"]["confidence_placeholder"] is False,
      rel["qualification"])

print("--- today, presence does not beat the mean ---")
wh, _ = scenario("withheld", start, train_comp=0.5, hold_comp=0.5)
check("WITHHELD when predicting the mean does better", wh["presence_calibration"]["state"] == "WITHHELD", wh["presence_calibration"])
check("and presence is not offered to the live loop", wh["presence"] is None)
check("the forecast stays on record beside it, marked not steering",
      wh["presence_forecast"] and wh["presence_forecast"]["steering_allowed"] is False and wh["presence_forecast"]["calibration"] == "WITHHELD")

print("--- too few held-out replies ---")
few, _ = scenario("few", start, n=40, n_before=30)
check("INSUFFICIENT with fewer than %d held-out replies, and no steering" % JP.MIN_PRESENCE_HOLDOUT,
      few["presence_calibration"]["state"] == "INSUFFICIENT" and few["presence"] is None, few["presence_calibration"])

print("--- frozen training baseline survives the recent display rolling off ---")
rel2, _ = scenario("rolled", start, train_comp=0.5, hold_comp=0.9)
turns = JP.training_turns()
cutoff = (start + timedelta(minutes=19.5)).timestamp()
labels = json.load(open(JP.AUDIT))
json.dump([r for r in labels if datetime.fromisoformat(r["timestamp"]).timestamp() > cutoff], open(JP.AUDIT, "w"))
audit = JP.presence_holdout_audit(Net(), Enc(), "legacy-concat-v1", cutoff, "fixture", turns=turns)
check("old checkpoints cannot invent a missing training baseline", audit["state"] == "INSUFFICIENT" and audit["n_training_era"] == 0, audit)
audit = JP.presence_holdout_audit(Net(), Enc(), "legacy-concat-v1", cutoff, "fixture", turns=turns,
                                baseline={"mean": .5, "n": 7, "source": "actual_training_labels"})
check("a checkpoint's actual training baseline supports the same held-out comparison",
      audit["state"] == "RELEASED" and audit["baseline_mean"] == .5 and audit["n_holdout"] == 12, audit)

print("--- the gloria head's fields are as they were ---")
for o in (old, rel, wh, few):
    g = o["gloria"]
    ok = (set(g) == {"nearest", "confidence", "decode_similarity", "novelty"} and o["confidence"] == g["confidence"]
          and o["novelty"] == g["novelty"] and o["gloria_forecast_nearest"] == g["nearest"])
    if not ok: break
check("gloria triple and its top-level copy keep their shape", ok, old["gloria"])

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

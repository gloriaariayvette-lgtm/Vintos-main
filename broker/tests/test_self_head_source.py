#!/usr/bin/env python3
"""The JEPA SELF head at its source (jepa_self_head.py, 16 October): what it trains on, what it is given at
forecast time, and whether it beats his previous reply and the mean of his recent replies on replies said
after its checkpoint. The gloria head is Gloria's to retrain and is not touched: the last section runs
jepa_predictor.predict with and without the self checkpoint and requires every gloria output to be the same.

Scratch HOME and SPARK_WORKSPACE are set before any import. The encoder is a tiny deterministic stub, torch is
a stub, and `requests` fails the suite if anything tries to send."""
import json, os, sys, tempfile, types, hashlib
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="self-head-source-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import numpy as np

class T(np.ndarray):
    def numpy(self): return np.asarray(self)
class _NoGrad:
    def __enter__(self): return self
    def __exit__(self, *a): return False
CK = {"dim": 16, "state": {}, "presence_trained": False, "architecture": "shared-v1", "context_schema": "legacy-concat-v1"}
sys.modules["torch"] = types.SimpleNamespace(load=lambda f: CK, tensor=lambda x: np.asarray(x, dtype="float32").view(T),
                                             no_grad=_NoGrad)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import jepa_predictor as JP
import jepa_self_head as SH

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:500]) if d and not ok else ""))

check("every path either module writes or reads is scratch", all(str(p).startswith(HOME) for p in (
    SH.MEMORY, SH.LEDGER, SH.SELF_MODEL, SH.SELF_EVAL, SH.HISTORY, SH.PRODUCTION_MODEL, SH.CANONICAL, SH.MERGED,
    SH.POST_TURN, SH.ON_MESSAGE_LOG, SH.PENDING_DIR, SH.EMB_CACHE, SH.VENV_PYTHON,
    JP.MEMORY, JP.CHAT, JP.MODEL, JP.OUT, JP.PRESENCE_CALIBRATION, JP.LEDGER_FLOOR_FILE)))
check("torch and the sender are stubs", sys.modules["torch"].load.__name__ == "<lambda>" and sys.modules["requests"].post is no_network)

DIM = 16
E = np.eye(DIM)
class Enc:
    """His two registers are two directions; every other text is a fixed random vector."""
    def encode(self, texts, show_progress_bar=False):
        out = []
        for t in texts:
            rng = np.random.default_rng(int(hashlib.md5(str(t).encode()).hexdigest()[:8], 16))
            t = str(t)
            if t.startswith("A-"): out.append(3 * E[0] + 0.3 * rng.normal(size=DIM))
            elif t.startswith("B-"): out.append(3 * E[1] + 0.3 * rng.normal(size=DIM))
            else: out.append(rng.normal(size=DIM))
        return np.asarray(out, dtype="float32")
JP.encoder = lambda: Enc()

print("--- his words, from the ledger ---")
check("device marks the ledger appends are not his words",
      SH.his_words("I'm here.\n\nridge:  <shape>\n        <track>   wave  ▁▃\n\ntenera: pulse  ▁▃  @4") == "I'm here.")
check("a paragraph of his own survives", SH.his_words("one\n\ntwo") == "one\n\ntwo")
check("the broken 'voice' junk is not a reply", SH.his_words("voice") == "")
TAC = {"output_provenance": "stratagem_influenced", "may_witness": False}
t0 = datetime.now() - timedelta(hours=1)
iso = lambda m: (t0 + timedelta(minutes=m)).isoformat()
rows = [{"timestamp": iso(0), "gloria": "hi", "vintos": "A-0", "turn_id": "t0"},
        {"timestamp": iso(1), "gloria": "hi", "vintos": "A-0", "turn_id": "t0"},                       # duplicate turn
        {"timestamp": iso(2), "gloria": "from elsewhere", "vintos": "not him", "transplanted": True},
        {"timestamp": iso(3), "gloria": "her words", "vintos": "tactical", "generation_provenance": TAC, "turn_id": "t3"},
        {"timestamp": iso(4), "gloria": "[Gloria sent you a photo: a red door]\n\n[Gloria's message with the photo:] look", "vintos": "B-4", "turn_id": "t4"}]
json.dump(rows, open(SH.LEDGER, "w"))
xs = SH.exchanges()
check("one exchange per turn_id; transplanted kept out", [x["turn_id"] for x in xs] == ["t0", "t3", "t4"], xs)
check("a withheld reply is neither target nor conditioning, her half stays",
      xs[1]["his"] == "" and xs[1]["her"] == "her words", xs[1])
check("a photo's composed description is not her words (her_words)", xs[2]["her"] == "(she sent a photo) look", xs[2])
open(JP.LEDGER_FLOOR_FILE, "w").write(iso(3))
check("the ledger floor applies to him too", [x["turn_id"] for x in SH.exchanges()] == ["t3", "t4"])
os.remove(JP.LEDGER_FLOOR_FILE)

print("--- pairs are forecast-time views ---")
# A fixed past morning, so the ten hours of exchanges never cross midnight (now - 11h failed before 11:00).
start = (datetime.now() - timedelta(days=2)).replace(hour=1, minute=0, second=0, microsecond=0)
def ledger(n, offset_days=0, tag="T"):
    out = []
    for k in range(n):
        out.append({"timestamp": (start + timedelta(minutes=5 * k, days=offset_days)).isoformat(),
                    "gloria": "her-%d" % k, "vintos": ("A-%d" if k % 2 == 0 else "B-%d") % k, "turn_id": "%s%d" % (tag, k)})
    return out
LED = ledger(120)
xs = SH.exchanges(LED)
P = SH.pairs(xs)
p = P[10]  # target is exchange 11
check("the target is his reply", p["target"] == "B-11")
check("her message to that reply is NOT in its context (it has not been sent at forecast time)",
      "her-11" not in p["conversation"] and p["her_last"] == "her-10", p)
check("the context is the %d exchanges before it, speakers named" % SH.CTX_EXCHANGES,
      p["conversation"].splitlines()[0] == "Gloria: her-8" and p["conversation"].splitlines()[-1] == "Vintos: A-10", p["conversation"])
check("his previous reply and his recent replies condition it", p["previous"] == "A-10" and len(p["recent"]) == SH.RECENT_REPLIES)
old = ledger(3, offset_days=-3, tag="old") + ledger(4)
pp = SH.pairs(SH.exchanges(old))
first_today = [q for q in pp if q["target"] == "B-1" and q["target_ts"][:10] == start.date().isoformat()][0]
check("one-day rule: an exchange three days earlier is not this sitting's conversation ...",
      "her-2" not in first_today["conversation"] and first_today["her_last"] == "her-0", first_today)
check("... but his replies then are still his recent replies", "A-2" in first_today["recent"], first_today["recent"])
live = SH._context(xs[:11], P[10]["target_ts"][:10])
check("forecast-time context == training context for the same ledger (train/predict parity)",
      all(live[k] == P[10][k] for k in ("conversation", "her_last", "previous", "recent")))

print("--- he alternates registers: neither baseline can see it, the head can ---")
JP.MODEL = SH.PRODUCTION_MODEL
check("no checkpoint: forecast() is None, jepa_predictor keeps its shared-trunk self", SH.forecast(Enc(), rows=LED[:70]) is None)
SH.MAX_CONF_SPEARMAN = -1.01   # this checkpoint's confidence must come out unqualified, whatever the noise says
r = SH.train(enc=Enc(), rows=LED[:70])
check("the initial train runs", r.get("state") == "TRAINED", r)
meta = r["meta"]["modes"]["ahead"]
check("both modes are in the one checkpoint, each choosing on its own validation",
      set(r["meta"]["modes"]) == {"ahead", "on_message"} and r["meta"]["modes"]["on_message"]["n_pairs"] == 69, r["meta"]["modes"].keys())
check("it learned beyond both bare anchors on its own validation",
      meta["validation_cos_dist"]["chosen"] < min(meta["validation_cos_dist"]["recent_mean"], meta["validation_cos_dist"]["previous_reply"]) - 0.2, meta["validation_cos_dist"])
held, why = SH.readiness()
check("a second train is held until the eval has judged this checkpoint", not held and why["state"] == "HELD_UNAUDITED_CHECKPOINT", why)
trained_at = (start + timedelta(minutes=5 * 69 + 1)).timestamp(); os.utime(SH.SELF_MODEL, (trained_at, trained_at))
open(SH.PRODUCTION_MODEL, "wb").write(b"prod"); os.utime(SH.PRODUCTION_MODEL, (trained_at, trained_at))
prod_ck = hashlib.sha256(b"prod").hexdigest()

hist = []
for k in range(66, 120):    # forecasts a minute after exchange k-1; the first four predate the checkpoint
    fc = SH.forecast(Enc(), rows=LED[:k], today=LED[k]["timestamp"][:10])
    at = start + timedelta(minutes=5 * (k - 1) + 1)
    hist.append({"ts": at.timestamp(), "iso": at.isoformat(), "checkpoint_id": prod_ck,
                 "self": {"emb": [float(v) for v in fc["emb"]], "source": fc["source"], "checkpoint_id": fc["checkpoint_id"],
                          "context_last_ts": fc["context_last_ts"]}})
    rng = np.random.default_rng(k)
    hist.append({"ts": at.timestamp() + 1, "iso": at.isoformat(), "checkpoint_id": prod_ck,
                 "self": {"emb": [float(v) for v in rng.normal(size=DIM)]}})              # the old shared-trunk row
check("a live forecast names its checkpoint and the last exchange it saw",
      fc["checkpoint_id"] == SH.checkpoint_id() and fc["context_last_ts"] == LED[118]["timestamp"])
check("no qualified confidence when coherence did not predict error: it is null, never a number",
      meta["confidence"]["qualified"] is False and fc["confidence"] is None and fc["qualification"] == "unqualified_not_predictive",
      (fc["confidence"], meta["confidence"]))
SH.MAX_CONF_SPEARMAN = 1.0
alt = os.path.join(MEM, "self-head-qualified.npz")
r2 = SH.train(enc=Enc(), rows=LED[:110], model_path=alt)
fq = SH.forecast(Enc(), rows=LED[:112], model_path=alt)
check("when it does, confidence is the live coherence's percentile among training coherences",
      r2["meta"]["modes"]["ahead"]["confidence"]["qualified"] is True and fq["qualification"] == "qualified" and 0.0 <= fq["confidence"] <= 1.0, fq["confidence"])
os.remove(alt)
SH.MAX_CONF_SPEARMAN = -1.01
HP = os.path.join(MEM, "jepa-prediction-history.jsonl")
open(HP, "w").write("\n".join(json.dumps(h) for h in hist) + "\n")
om = []
for k in range(66, 120):    # the on-message forecast: her message k has arrived (30 s before his ledger row), his reply not
    arrived = SH._epoch(LED[k]["timestamp"]) - 30
    fc = SH.forecast(Enc(), rows=LED[:k + 1], mode="on_message", her=LED[k]["gloria"], arrived_at=arrived, today=LED[k]["timestamp"][:10])
    om.append({"ts": arrived + 2, "arrived_at": arrived, "her_key": fc["her_key"], "mode": "on_message",
               "self": {"emb": [float(v) for v in fc["emb"]], "mode": "on_message", "source": fc["source"],
                        "checkpoint_id": fc["checkpoint_id"], "context_last_ts": fc["context_last_ts"]}})
check("an on-message forecast never sees the reply it is about, even when the ledger already holds it",
      fc["context_last_ts"] == LED[k - 1]["timestamp"] and fc["mode"] == "on_message", fc["context_last_ts"])
open(SH.ON_MESSAGE_LOG, "w").write("\n".join(json.dumps(h) for h in om) + "\n")
before = {f: open(os.path.join(MEM, f), "rb").read() for f in os.listdir(MEM)}
rep = SH.run_eval(enc=Enc(), rows=LED)
after = {f: open(os.path.join(MEM, f), "rb").read() for f in os.listdir(MEM)}
check("the eval writes its own report and nothing else",
      set(after) - set(before) == {"jepa-self-eval.json"} and all(after[f] == before[f] for f in before), set(after) ^ set(before))
s = rep["self_head"]
check("only forecasts after the checkpoint, about replies said after it, one per reply",
      s["n"] == sum(1 for h in hist if h["self"].get("source") and h["ts"] > trained_at) == 49 and all(r_["target_ts"] > LED[69]["timestamp"] for r_ in rep["rows"]["ahead"]), s)
check("the head beats his previous reply and his recent mean on held-out replies",
      s["state"] == "BEATS_BASELINES" and s["cos_dist"]["head"] < s["cos_dist"]["recent_mean"] < s["cos_dist"]["previous_reply"]
      and s["head_wins"]["vs_previous_reply"] > 0.9 and s["head_wins"]["vs_recent_mean"] > 0.9, s)
leg = rep["legacy_shared_trunk"]
check("the old shared-trunk rows are scored the same way, for before/after", leg["n"] == 50 and leg["state"] == "NOT_BETTER_THAN_BASELINES", leg)
check("each mode is scored separately, on_message against baselines that also had her message",
      rep["modes"]["on_message"]["n"] == 50 and set(rep["modes"]["on_message"]["baselines"]) ==
      {"previous_reply", "recent_mean", "nearest_exchange", "typical_reply"} and rep["self_head"] == rep["modes"]["ahead"], rep["modes"]["on_message"])
check("the report is bound to the checkpoint it judged", rep["checkpoint"] == SH.checkpoint_id() and rep["production_checkpoint"] == prod_ck)
held, why = SH.readiness()
check("with >= %d judged replies the next train may run" % SH.MIN_EVAL, held and why["state"] == "READY_AFTER_AUDIT", why)
leak = [dict(h) for h in hist[:2]]; leak[0]["ts"] = trained_at - 600
ev = SH.evaluate(leak, SH.exchanges(LED), Enc(), self_ck=SH.checkpoint_id(), self_trained_at=trained_at)
check("a forecast made before the checkpoint is never scored", ev["ahead"] == [], ev["ahead"])

print("--- jepa_predictor.predict takes self from the head; gloria is byte-identical either way ---")
chat = []
for k in range(100, 120):
    chat.append({"role": "user", "content": "her-%d" % k, "timestamp": LED[k]["timestamp"]})
    chat.append({"role": "assistant", "content": LED[k]["vintos"], "timestamp": LED[k]["timestamp"]})
json.dump(chat, open(JP.CHAT, "w")); json.dump(LED, open(SH.LEDGER, "w"))
class Net:
    def load_state_dict(self, s): pass
    def eval(self): pass
    def __call__(self, x):
        x = np.asarray(x, dtype="float32"); n = len(x)
        return (np.tanh(x).view(T), (x * 0.5).view(T), np.full((n, 1), 0.5, dtype="float32").view(T),
                np.stack([x[:, 0], x[:, 1], x[:, 2]], axis=1).view(T))
JP.make_net = lambda dim, architecture="shared-v1": Net()
def run(tag):
    out, hp = os.path.join(MEM, "pred-%s.json" % tag), os.path.join(MEM, "hist-%s.jsonl" % tag)
    JP.predict(SH.PRODUCTION_MODEL, out, hp)
    return json.load(open(out)), json.loads(open(hp).read().splitlines()[-1])
with_head, wh = run("with")
os.rename(SH.SELF_MODEL, SH.SELF_MODEL + ".away")
without, wo = run("without")
os.rename(SH.SELF_MODEL + ".away", SH.SELF_MODEL)
check("with a checkpoint, self comes from the head, marked", with_head["self"].get("source") == SH.SOURCE
      and with_head["self"]["checkpoint_id"] == SH.checkpoint_id() and wh["self"].get("context_last_ts") == LED[-1]["timestamp"]
      and wh["self"].get("mode") == with_head["self"].get("mode") == "ahead", with_head["self"])
check("its null confidence reaches readers as the marked 0.5 stand-in",
      with_head["self"]["confidence"] == 0.5 and with_head["self"]["confidence_placeholder"] is True
      and with_head["qualification"]["self"] == "unqualified_not_predictive")
check("without one, the shared-trunk self is as it was (no source field)", "source" not in without["self"] and "source" not in wo["self"])
check("and the two self forecasts differ", wh["self"]["emb"] != wo["self"]["emb"])
same = lambda a, b: json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
check("gloria triple, top-level copy, qualification and latest turn are byte-identical",
      same(with_head["gloria"], without["gloria"]) and
      (with_head["confidence"], with_head["novelty"], with_head["gloria_forecast_nearest"], with_head["gloria_latest_turn"]) ==
      (without["confidence"], without["novelty"], without["gloria_forecast_nearest"], without["gloria_latest_turn"]) and
      with_head["qualification"]["gloria"] == without["qualification"]["gloria"] and with_head["context_id"] == without["context_id"])
check("the gloria history row and its context embedding are byte-identical",
      same(wh["gloria"], wo["gloria"]) and wh["context_emb"] == wo["context_emb"] and wh["checkpoint_id"] == wo["checkpoint_id"])

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

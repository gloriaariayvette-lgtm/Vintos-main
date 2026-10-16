#!/usr/bin/env python3
"""The JEPA self head's two source limits (16 October, after the rebuild measured 0.1784 vs his recent mean 0.1869):

  1. it forecast only before her next message existed, and his reply is mostly an answer to it. The on_message
     mode forecasts when her message has arrived and before he replies, from the same history plus her message;
     its eval is held to baselines that also have her message. On synthetic data where his reply depends on
     her message, on_message must beat every baseline and the ahead mode must not get that benefit.
  2. the ledger keeps 300 entries (~10 days). Every older record the host keeps is read through the evidence
     door (snapshots and quarantines beside the ledger, chat-canonical.jsonl, chat-history-merged.json), with
     the withheld / transplant / floor / scrub / test-mode rules, one exchange per real exchange.

And the launch: the server's hook writes one pending row and starts a background process (a stub here), and
the job writes one forecast row that names its mode and does not carry her words.

Scratch HOME and SPARK_WORKSPACE are set before any import; the encoder is a stub; torch is a stub; `requests`
fails the suite if anything sends; the process launcher is a stub that records and never runs anything."""
import json, os, sys, tempfile, types, hashlib, math
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="self-head-on-message-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import numpy as np
sys.modules["torch"] = types.SimpleNamespace(load=lambda f: None, tensor=lambda x: x, no_grad=None)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import jepa_predictor as JP
import jepa_self_head as SH

LAUNCHED = []
def stub_runner(argv, **kw):
    LAUNCHED.append(list(argv)); return types.SimpleNamespace(pid=0)
SH.RUNNER = stub_runner
SH.ON_MESSAGE_LOGFILE = os.path.join(MEM, "on-message.log")

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:600]) if d and not ok else ""))

check("every path the head reads or writes is scratch", all(str(p).startswith(HOME) for p in (
    SH.MEMORY, SH.LEDGER, SH.CANONICAL, SH.MERGED, SH.POST_TURN, SH.SELF_MODEL, SH.SELF_EVAL, SH.HISTORY,
    SH.ON_MESSAGE_LOG, SH.PENDING_DIR, SH.EMB_CACHE, SH.PRODUCTION_MODEL, SH.VENV_PYTHON, SH.ON_MESSAGE_LOGFILE,
    JP.MEMORY, JP.LEDGER_FLOOR_FILE)))
check("the sender, torch and the process launcher are stubs",
      sys.modules["requests"].post is no_network and SH.RUNNER is stub_runner and sys.modules["torch"].no_grad is None)

# ------------------------------------------------------------------------------------------------ the archive
print("--- 2. the full history, every record of it through the door ---")
t0 = datetime.now() - timedelta(days=20)
at = lambda d, m=0, s=0: (t0 + timedelta(days=d, minutes=m, seconds=s)).isoformat()
TAC = {"output_provenance": "stratagem_influenced", "may_witness": False}
OK = {"output_provenance": "ordinary_generation", "may_witness": True}
snap = [{"timestamp": at(1, 0), "gloria": "s0 words", "vintos": "s0 reply", "turn_id": "S0"},
        {"timestamp": at(1, 5), "gloria": "s1 words", "vintos": "s1 reply\n\nridge:  <shape>", "turn_id": "S1"},
        {"timestamp": at(1, 10), "gloria": "from elsewhere", "vintos": "not him", "turn_id": "S2", "transplanted": True},
        {"timestamp": at(1, 15), "gloria": "", "vintos": "a clip he sent", "turn_id": "S3", "source": "video-outreach"},
        {"timestamp": at(1, 20), "gloria": "s5 words", "vintos": "s5 secret", "turn_id": "S5", "provenance": TAC},
        {"timestamp": at(15, 0), "gloria": "l0 words", "vintos": "l0 reply", "turn_id": "L0"}]
json.dump(snap, open(os.path.join(MEM, "interaction-ledger.pre-scrub-20261001-120000.json"), "w"))
open(os.path.join(MEM, "interaction-ledger.corrupt-20261002-000000.json"), "w").write('[{"timestamp": "2026')
json.dump([{"timestamp": at(0, 30), "gloria": "q0 words", "vintos": "q0 reply", "turn_id": "Q0"}],
          open(os.path.join(MEM, "interaction-ledger.json.corrupt-20260930-000000"), "w"))
live = [{"timestamp": at(15, 0), "gloria": "l0 words", "vintos": "l0 reply", "turn_id": "L0", "provenance": OK},
        {"timestamp": at(15, 5, 40), "gloria": "l1 words", "vintos": "l1 reply\n\ntenera: pulse", "turn_id": "L1"},
        {"timestamp": at(15, 10, 40), "gloria": "l2 words", "vintos": "l2 secret", "turn_id": "L2", "provenance": TAC},
        {"timestamp": at(15, 15, 40), "gloria": "look", "vintos": "l3 reply", "turn_id": "L3"}]
json.dump(live, open(SH.LEDGER, "w"))
canon = [
    {"role": "user", "content": "c0 words", "timestamp": at(3, 0)}, {"role": "assistant", "content": "c0 reply", "timestamp": at(3, 0, 20)},
    {"role": "user", "content": "c1 words", "timestamp": at(3, 5)}, {"role": "assistant", "content": "c1 reply", "timestamp": at(3, 5, 20)},
    {"role": "assistant", "content": "Desktop work finished: opened the folder", "timestamp": at(3, 6), "source": "desktop-control", "desktop_request_id": "d1"},
    {"role": "assistant", "content": "thinking of you (outreach)", "timestamp": at(3, 30)},
    {"role": "user", "content": "test words", "timestamp": at(4, 0)}, {"role": "assistant", "content": "test reply", "timestamp": at(4, 0, 10)},
    {"role": "user", "content": "tactic words", "timestamp": at(4, 5)},
    {"role": "assistant", "content": "tactic reply", "timestamp": at(4, 5, 10), "generation_provenance": TAC},
    {"role": "user", "content": "s5 words, said a little differently", "timestamp": at(1, 19, 20)},
    {"role": "assistant", "content": "s5 secret", "timestamp": at(1, 19, 30)},
    {"role": "user", "content": "l1 words", "timestamp": at(15, 5)}, {"role": "assistant", "content": "l1 reply", "timestamp": at(15, 5, 1)},
    {"role": "user", "content": "l2 words", "timestamp": at(15, 10)}, {"role": "assistant", "content": "l2 secret", "timestamp": at(15, 10, 1)},
    {"role": "user", "content": "[Gloria sent you a photo: a red door]\n\n[Gloria's message with the photo:] look", "timestamp": at(15, 15),
     "input_kind": "photo", "original_text": "look"},
    {"role": "assistant", "content": "l3 reply", "timestamp": at(15, 15, 1)},
    {"role": "user", "content": "too old", "timestamp": (t0 - timedelta(days=3)).isoformat()},
    {"role": "assistant", "content": "too old reply", "timestamp": (t0 - timedelta(days=3, seconds=-5)).isoformat()}]
open(SH.CANONICAL, "w").write("\n".join(json.dumps(r) for r in canon) + "\n")
test_t = datetime.fromisoformat(at(4, 0, 12)).timestamp()
open(SH.POST_TURN, "w").write(json.dumps({"t": test_t, "surface": "chat/full", "test_mode": True}) + "\n" +
                              json.dumps({"t": test_t + 600, "surface": "chat/full", "test_mode": False}) + "\n")
merged = [{"role": "user", "content": "v0 words", "timestamp": at(2, 0), "source": "voice"},
          {"role": "assistant", "content": "v0 reply", "timestamp": at(2, 0), "source": "voice"},
          {"role": "user", "content": "c0 words", "timestamp": at(3, 0), "source": "main"},
          {"role": "assistant", "content": "c0 reply", "timestamp": at(3, 0, 20), "source": "main"},
          {"role": "assistant", "content": "Desktop work stopped: no window", "timestamp": at(3, 7), "source": "main"}]
json.dump(merged, open(SH.MERGED, "w"))
open(JP.LEDGER_FLOOR_FILE, "w").write((t0 - timedelta(days=1)).isoformat())
xs = SH.exchanges()
her = [x["her"] for x in xs]
by = {x["her"]: x for x in xs}
check("older exchanges from snapshots, quarantines, the canonical record and the merged chat are read",
      her == ["q0 words", "s0 words", "s1 words", "s5 words", "v0 words", "c0 words", "c1 words", "l0 words", "l1 words", "l2 words",
              "look"], her)
check("one exchange per real exchange: the live ledger row wins, and keeps the earliest time any record gives it",
      by["l1 words"]["origin"] == "ledger" and by["l1 words"]["ts"] == at(15, 5, 1) and by["l1 words"]["his"] == "l1 reply"
      and sum(1 for h in her if h == "c0 words") == 1, by["l1 words"])
check("a reply the ledger withholds stays withheld when a chat copy of it exists (same words, or reworded)",
      by["l2 words"]["his"] == "" and by["s5 words"]["his"] == "" and not any("secret" in x["his"] for x in xs), [x["his"] for x in xs])
check("a snapshot keeps the rules: transplanted out, ledger-scrub's video-outreach out, device marks stripped",
      "from elsewhere" not in her and not any("clip" in x["his"] for x in xs) and by["s1 words"]["his"] == "s1 reply")
check("an unparseable quarantine holds nothing; a parseable one is read", "q0 words" in her)
check("canonical: desktop status lines and outreach are not replies; a test-mode turn and a tactical one are out",
      not any(x["his"].startswith("Desktop work") or "outreach" in x["his"] for x in xs) and "test words" not in her and "tactic words" not in her)
check("the ledger floor holds for every record", "too old" not in her)
rep = SH.sources_report()
st = rep["by_source"]
check("`sources` counts what each record adds",
      st["ledger"]["added"] == 4 and st["canonical"]["added"] == 2 and st["merged"]["added"] == 1 and st["merged"]["duplicate"] == 1
      and st["canonical"]["withheld"] == 2 and rep["replies"] == 9 and rep["ledger_only_replies"] == 3, rep)
tg = [q["target"] for q in SH.pairs(xs)]
check("training pairs reach into the archive (targets from snapshots, canonical and merged), withheld never a target",
      {"s1 reply", "v0 reply", "c0 reply", "c1 reply", "l1 reply"} <= set(tg) and "s5 secret" not in tg and "l2 secret" not in tg, tg)
check("archive=False is the live ledger alone (what the head read before)",
      [x["turn_id"] for x in SH.exchanges(archive=False)] == ["L0", "L1", "L2", "L3"])
for f in os.listdir(MEM):
    os.remove(os.path.join(MEM, f))

# ------------------------------------------------------------------------------------------------ on_message
print("--- 1. his reply answers her message: only the on-message forecast can see it ---")
DIM = 24
_r0 = np.random.default_rng(7)
W = np.linalg.qr(_r0.normal(size=(DIM, DIM)))[0]
STYLE = _r0.normal(size=DIM); STYLE /= np.linalg.norm(STYLE)
def _rng(t): return np.random.default_rng(int(hashlib.md5(str(t).encode()).hexdigest()[:8], 16))
def vec(t):
    t = str(t)
    if t.startswith("m-"):
        v = _rng(t).normal(size=DIM); return v / np.linalg.norm(v)
    if t.startswith("r-"):   # his reply = a fixed map of her message, his own register, a little noise
        return W @ vec("m-" + t[2:]) + 0.6 * STYLE + 0.25 * _rng(t).normal(size=DIM) / math.sqrt(DIM)
    return _rng(t).normal(size=DIM)
class Enc:
    def encode(self, texts, show_progress_bar=False):
        return np.asarray([vec(t) for t in texts], dtype="float32")
JP.encoder = lambda: Enc()

start = datetime.now() - timedelta(hours=14)
N, CUT = 260, 180
LED = [{"timestamp": (start + timedelta(minutes=3 * k)).isoformat(), "gloria": "m-%d" % k, "vintos": "r-%d" % k, "turn_id": "T%d" % k}
       for k in range(N)]
r = SH.train(enc=Enc(), rows=LED[:CUT])
check("trained", r.get("state") == "TRAINED", r)
ma, mm = r["meta"]["modes"]["ahead"], r["meta"]["modes"]["on_message"]
va, vm = ma["validation_cos_dist"], mm["validation_cos_dist"]
check("validation: on_message beats every baseline that also had her message, by a margin",
      vm["chosen"] < min(vm["recent_mean"], vm["previous_reply"], vm["typical_reply"], vm["nearest_exchange"]) - 0.1, vm)
check("validation: the ahead mode cannot see her message and gets none of that",
      va["chosen"] > vm["chosen"] + 0.2 and va["chosen"] > min(va["recent_mean"], va["previous_reply"]) - 0.05, (va, vm["chosen"]))
check("each mode's bare baselines were among its own candidates, scored on the same validation pairs",
      set(SH.BASELINES["on_message"]) <= set(vm) and set(SH.BASELINES["ahead"]) <= set(va)
      and all(v >= vm["chosen"] for k_, v in vm.items() if k_ in SH.BASELINES["on_message"]))
check("the richer model was tried, and is chosen only when it beats ridge on validation",
      vm["best_mlp"] is not None and ((mm["kind"] == "mlp") == (vm["best_mlp"] < vm["best_ridge"])), (mm["kind"], vm["best_mlp"], vm["best_ridge"]))
trained_at = (start + timedelta(minutes=3 * (CUT - 1) + 1)).timestamp(); os.utime(SH.SELF_MODEL, (trained_at, trained_at))

hist, om = [], []
for k in range(CUT, N):
    fa = SH.forecast(Enc(), rows=LED[:k], today=LED[k]["timestamp"][:10])
    t_a = (start + timedelta(minutes=3 * (k - 1) + 1)).timestamp()
    # (the first is made the minute the checkpoint was written: not after it, so never scored)
    hist.append({"ts": t_a, "iso": SH._iso(t_a), "self": {"emb": [float(v) for v in fa["emb"]], "source": fa["source"], "mode": fa["mode"],
                 "checkpoint_id": fa["checkpoint_id"], "context_last_ts": fa["context_last_ts"]}})
    arrived = SH._epoch(LED[k]["timestamp"]) - 40
    pend = os.path.join(MEM, "pending-%d.json" % k)
    json.dump({"her": LED[k]["gloria"], "arrived_at": arrived, "surface": "chat/full"}, open(pend, "w"))
    if k == CUT: json.dump(LED[:k + 1], open(SH.LEDGER, "w"))   # the job reads the ledger, which already holds her reply
    if k == CUT: row = SH.on_message_job(pend, enc=Enc(), now=arrived + 3)
    fm = SH.forecast(Enc(), rows=LED[:k + 1], mode="on_message", her=LED[k]["gloria"], arrived_at=arrived)
    om.append({"ts": arrived + 3, "iso": SH._iso(arrived + 3), "arrived_at": arrived, "her_key": fm["her_key"], "mode": "on_message",
               "self": {"emb": [float(v) for v in fm["emb"]], "mode": "on_message", "source": fm["source"],
                        "checkpoint_id": fm["checkpoint_id"], "context_last_ts": fm["context_last_ts"]}})
    if os.path.exists(pend): os.remove(pend)
open(SH.HISTORY, "w").write("\n".join(json.dumps(h) for h in hist) + "\n")
open(SH.ON_MESSAGE_LOG, "w").write("\n".join(json.dumps(h) for h in om) + "\n")
rep = SH.run_eval(enc=Enc(), rows=LED)
a, m = rep["modes"]["ahead"], rep["modes"]["on_message"]
check("prospective: on_message beats all four baselines on replies said after its checkpoint",
      m["n"] == N - CUT and m["state"] == "BEATS_BASELINES" and
      m["cos_dist"]["head"] < min(v for k_, v in m["cos_dist"].items() if k_ != "head") - 0.1, m)
check("prospective: the ahead mode, scored the same way, gets none of it",
      a["n"] == N - CUT - 1 and a["cos_dist"]["head"] > m["cos_dist"]["head"] + 0.2 and
      a["cos_dist"]["head"] > min(a["cos_dist"]["recent_mean"], a["cos_dist"]["previous_reply"]) - 0.05, (a, m["cos_dist"]))
check("the on_message baselines were given her message (her nearest past messages), the ahead ones were not",
      set(m["baselines"]) == {"previous_reply", "recent_mean", "nearest_exchange", "typical_reply"} and set(a["baselines"]) == {"previous_reply", "recent_mean"})
held, why = SH.readiness()
check("a retrain needs each mode judged on >= %d replies" % SH.MIN_EVAL, held and why["n"] == {"ahead": N - CUT - 1, "on_message": N - CUT}, why)

CALLS = []
class Counting(Enc):
    def encode(self, texts, show_progress_bar=False):
        CALLS.extend(texts); return Enc.encode(self, texts)
c1 = SH._Cache(Counting(), persist=True); c1.fill(["m-1", "m-2"])
c2 = SH._Cache(Counting(), persist=False); c2.fill(["m-1", "m-2", "m-3"])
check("embeddings are kept on disk: a later forecast encodes only what is new; the eval reads, never writes",
      CALLS == ["m-1", "m-2", "m-3"] and np.allclose(c2.get("m-1"), c1.get("m-1"))
      and os.path.exists(SH.EMB_CACHE + ".f32") and os.path.exists(SH.EMB_CACHE + ".idx.jsonl"), CALLS)
class Other:
    def encode(self, texts, show_progress_bar=False): return -Enc().encode(texts)
c3 = SH._Cache(Other(), persist=False); c3.fill(["m-1"])
check("an encoder of another kind never reads another's vectors", np.allclose(c3.get("m-1"), -SH._unit(vec("m-1"))))

print("--- the launch: her message arrives, a background forecast starts, the reply does not wait ---")
check("the job wrote one on_message row: mode, checkpoint, her_key, the last exchange it saw; never her words",
      row is not None and row["mode"] == row["self"]["mode"] == "on_message" and row["self"]["checkpoint_id"] == SH.checkpoint_id()
      and row["her_key"] == SH.her_key("m-%d" % CUT) and "m-%d" % CUT not in json.dumps(row)
      and row["self"]["context_last_ts"] == LED[CUT - 1]["timestamp"], row)
check("the pending row is consumed", not os.path.exists(os.path.join(MEM, "pending-%d.json" % CUT)))
old = os.path.join(MEM, "stale.json"); json.dump({"her": "m-1", "arrived_at": 1.0}, open(old, "w"))
check("a pending row older than %ds forecasts nothing" % SH.PENDING_MAX_AGE, SH.on_message_job(old, enc=Enc()) is None and not os.path.exists(old))
check("no venv, no launch (the encoder needs it)", SH.launch_on_message("m-3", "chat/full") is None and LAUNCHED == [])
os.makedirs(os.path.dirname(SH.VENV_PYTHON)); open(SH.VENV_PYTHON, "w").write("")
p = SH.launch_on_message("[Gloria sent you a photo: x]\n\n[Gloria's message with the photo:] hello you", "avatar", turn_id="t-1")
pend = json.load(open(p)) if p else {}
check("launch writes one pending row and starts one niced background job, then returns",
      p and p.startswith(SH.PENDING_DIR) and len(LAUNCHED) == 1 and LAUNCHED[0][-2:] == ["on-message", p]
      and SH.VENV_PYTHON in LAUNCHED[0] and (LAUNCHED[0][0] != "nice" or LAUNCHED[0][:3] == ["nice", "-n", "15"])
      and pend.get("surface") == "avatar" and pend.get("turn_id") == "t-1", (LAUNCHED, pend))
check("an empty message launches nothing", SH.launch_on_message("   ", "chat/full") is None and len(LAUNCHED) == 1)
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("the server launches it at chat/full and at the avatar door, and never in test mode",
      '_self_on_message(_her, "chat/full", test_mode=_test_mode_active())' in srv
      and "_self_on_message(_counterpart_text, _surface, turn_id=" in srv and "test_mode=_test_turn)" in srv
      and "if test_mode:\n        return None" in srv)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

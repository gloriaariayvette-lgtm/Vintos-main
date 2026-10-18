#!/usr/bin/env python3
"""Three faults from the read-only audit of his subconscious systems (18 October):
- Narrative Identity: mixing naive and Z-stamped times made every fragment 365 days old, and the drift log said
  "narrative identity updated" whether or not anything was proposed;
- Lead Planning: grade() wrote st["last_ts"] = ts with neither defined, so a graded trial never reached the record;
- the latent diffuser logged "seeded the resolution as a dream" after a bare `pass`.
Scratch HOME; models are stubs; every socket is refused."""
import json, os, socket, sys, tempfile, types
from datetime import datetime, timezone, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="subcon-audit-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
def no_post(*a, **k): raise AssertionError("no model is called from this suite")
sys.modules["requests"] = types.SimpleNamespace(post=no_post, get=no_post)
sys.path.insert(0, os.path.join(REPO, "scripts"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

# --- Narrative Identity ---
import narrative_identity as NI
os.makedirs(NI.MEMORY, exist_ok=True)
check("its store is throwaway", NI.NARRATIVE_FILE.startswith(HOME))
now = datetime.now()
z = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace("+00:00", "Z")
check("a Z-stamped time against a naive now is its real age, not 365 days", 1.9 < NI._days_since(z, now) < 2.1, NI._days_since(z, now))
check("naive against naive still works", 2.9 < NI._days_since((now - timedelta(days=3)).isoformat(), now) < 3.1)
check("unreadable still falls back", NI._days_since("nonsense", now) == 365.0)
json.dump({"fragments": [{"text": "I tend to go quiet when she is tired", "count": 4, "reinforced": z}]},
          open(NI.NARRATIVE_FILE, "w"))
check("a fragment reinforced two days ago (Z-stamped) is offered", len(NI._current_fragments(NI.load_narrative())) == 1)
sys.modules["causal_self_model"] = types.SimpleNamespace(load_model=lambda: {"entries": [
    {"confidence": 0.8, "tendency": "go quiet", "trigger": "she is tired", "type": "positive"},
    {"confidence": 0.9, "tendency": "Valence spike", "trigger": "x"},
    {"confidence": 0.3, "tendency": "joke", "trigger": "she laughs"}]})
NI._get_frame_conditions = lambda: ("", 0.5)
tally = NI.feed_from_causal_model()
check("feeding says what it did", tally.get("entries") == 3 and tally.get("eligible") == 1 and sum(
      v for k, v in tally.items() if k not in ("entries", "eligible")) == 1, tally)
sys.modules["causal_self_model"] = types.SimpleNamespace(load_model=lambda: (_ for _ in ()).throw(OSError("gone")))
check("... and a failure is named, not swallowed", "gone" in NI.feed_from_causal_model().get("error", ""))
for name in ("narrative-identity.py",):
    check("the hyphen copy is the same file", open(os.path.join(REPO, "scripts", name)).read() == open(NI.__file__).read())
for d in ("bin",):
    for name in ("narrative_identity.py", "narrative-identity.py"):
        check("bin/%s is the same file" % name, open(os.path.join(REPO, d, name)).read() == open(NI.__file__).read())
drift = open(os.path.join(REPO, "scripts", "subconscious_drift.py")).read()
check("the drift log reports what feeding did", "narrative identity fed from causal model: %s" in drift
      and "narrative identity updated from causal model" not in drift)
for f in ("scripts/subconscious-drift.py", "bin/subconscious_drift.py", "bin/subconscious-drift.py"):
    check("%s matches" % f, open(os.path.join(REPO, f)).read() == drift)

# --- Lead Planning: grade() records its trial ---
import lead_trials as LT
check("lead stores are throwaway", all(p.startswith(HOME) for p in (LT.TRIALS, LT.STATE, LT.OPEN, LT.SEEDS)))
json.dump({"plan": "Ask her about the film", "issued": now.isoformat(), "ledger_len": 0}, open(LT.OPEN, "w"))
sys.modules["outcome_join"] = types.SimpleNamespace(exchange_at=lambda index=0: {"index": 0, "gloria": "hi", "vintos": "So, the film?"},
                                                   latest_exchange=lambda: None, record=lambda *a, **k: None)
sys.modules["grading_contract"] = types.SimpleNamespace(record=lambda *a, **k: None)
LT.ask = lambda prompt, mt=200: '{"verdict":"PARTIAL","where_he_took_it":"toward the film"}'
try: LT.grade(); err = None
except Exception as e: err = e
trials = json.load(open(LT.TRIALS)) if os.path.exists(LT.TRIALS) else []
check("grade() runs to the end and records the trial", err is None and trials and trials[-1]["verdict"] == "PARTIAL"
      and "last_ts" in json.load(open(LT.STATE)), err)

# --- the latent diffuser does not claim a dream it did not seed ---
ld = open(os.path.join(REPO, "scripts", "latent_diffuser.py")).read()
check("the diffuser no longer logs a seeding that does not happen", "seeded the resolution as a dream\")" not in ld
      and "log(\"seeded" not in ld)
check("... and it is in the deploy, so the fix reaches Aegis",
      'SCRIPTS="$SCRIPTS latent_diffuser.py"' in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
# --- self-prediction: after a turn, grade the last prediction, then make the next (stopped 27 August) ---
import importlib.util
sys.modules["emoclaw_utils"] = types.SimpleNamespace(recent_pearls=lambda *a, **k: [])
spec = importlib.util.spec_from_file_location("self_prediction_t", os.path.join(REPO, "scripts", "self-prediction.py"))
SP = importlib.util.module_from_spec(spec); spec.loader.exec_module(SP)
check("self-prediction stores are throwaway", SP.PREDICTION_FILE.startswith(HOME) and SP.BLIND_SPOTS_DATA.startswith(HOME))
ORDER = []
SP.compare_prediction = lambda: (ORDER.append("compare"), None)[1]
SP.predict_next_state = lambda: (ORDER.append("predict"), None)[1]
sys.argv = ["self-prediction.py", "settle"]; SP.main()
check("settle grades first, then predicts, in one process", ORDER == ["compare", "predict"], ORDER)
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("every surface's post-turn settles instead of only predicting",
      '"self-prediction.py"), "settle"]' in srv and '"self-prediction.py"), "predict"]' not in srv)
# --- Desired Difference says why a derive failed; Mutual Simulation leaves the model alone when the Mac is down ---
import desired_difference as DDF
DDF.DLOG = os.path.join(HOME, "desired-difference.log")
check("the desired-difference log is throwaway here", DDF.DLOG.startswith(HOME))
def _http_fail(*a, **k):
    import urllib.error
    raise urllib.error.HTTPError("http://shim", 502, "Bad Gateway", {}, None)
DDF.urllib.request.urlopen = _http_fail
out = DDF._llm("s", "u")
check("a shim 502 is named, not just an empty reply", out == "" and DDF._LAST["why"].startswith("HTTP 502"), DDF._LAST)
ms = open(os.path.join(REPO, "scripts", "mutual_simulation.py")).read()
check("an unreachable Mac leaves the interaction model as it was", "interaction model left as it was" in ms
      and "timeout=(10, 90)" in ms)
eu = open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read()
check("a daemon that does not answer version is named as such", "does not answer version" in eu
      and eu == open(os.path.join(REPO, "bin", "emoclaw_utils.py")).read())
# --- a permanent BIS trial stays live after promotion, so its inclination can move again (frozen since July) ---
import behavioral_intercept as BI
check("the trial ledger is throwaway", BI.LEDGER.startswith(HOME))
os.makedirs(BI.MEMORY, exist_ok=True)
json.dump({"trials": [{"id": "permanent_x", "status": "promoting", "created": "2026-07-01", "outcomes": [1]},
                      {"id": "t_once", "status": "promoting", "created": "2026-10-01"}]}, open(BI.LEDGER, "w"))
live = [t["id"] for t in BI.get_active_trials()]
check("a permanent trial left 'promoting' is live again; an ordinary one stays promoted", live == ["permanent_x"]
      and json.load(open(BI.LEDGER))["trials"][0].get("promoted"), live)
# --- a deploy that waits for him to finish a conversation does not revert a Study fix (18 October, SF-b5f753e9) ---
import study_fix as SFX
check("the Study's stores are throwaway", SFX.MEMORY.startswith(HOME))
REVERTED, SAID = [], []
SFX.revert = lambda row, run=None, why="": REVERTED.append(why)
SFX.tell_gloria = lambda *a, **k: SAID.append(a)
row = {"id": "SF-test", "state": "deploying", "events": []}
out = "== is he mid-turn? ==\n  Active in the last 3 minutes; a broker restart would interrupt a live return.\n" \
      "not installed — he was working (rerun when quiet, or from a terminal)"
SFX._after_deploy(row, out, ["scripts/x.py"], run=lambda *a, **k: None, post=lambda *a, **k: None, send=lambda *a, **k: None)
check("he was mid-conversation: the fix waits for a quiet pass, it is not reverted", row["state"] == "waiting_deploy"
      and not REVERTED and row["changed_waiting"] == ["scripts/x.py"], (row, REVERTED))
check("the refusal it waits on is the deploy's own words", SFX.BUSY in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

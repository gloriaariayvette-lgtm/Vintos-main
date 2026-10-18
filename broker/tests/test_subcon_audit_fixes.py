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
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

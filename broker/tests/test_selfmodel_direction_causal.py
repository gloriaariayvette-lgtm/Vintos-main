#!/usr/bin/env python3
"""Self-model review (16 October): discourse direction records a choice only when his direction changes, and
only on a lived turn; web search no longer moves it; the causal self-model counts only the wants HE let go,
once each, and a full store no longer drops what it has just learned; the want discussion prompt no longer
carries raw relational-geometry floats.

Isolation: HOME and SPARK_WORKSPACE point at a scratch directory before anything is imported; every module
path this suite writes is asserted to sit inside it; requests and self_drift are stubs; no socket connects.
"""
import json, os, socket, sys, tempfile, types
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="selfmodel-dir-")
WS = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
os.makedirs(os.path.join(WS, "scripts"), exist_ok=True)
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = WS
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.join(REPO, "bin"))

NET = []
def _no_net(self, *a, **k):
    NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

SENT = []
_req = types.ModuleType("requests")
def _post(*a, **k):
    SENT.append((a, k)); raise OSError("stub: nothing is sent")
_req.post = _post; _req.get = _post
sys.modules["requests"] = _req

CHOICES = []
_sd = types.ModuleType("self_drift")
def _rdc(direction, source="conversation"):
    CHOICES.append((direction, source))
_sd.record_direction_choice = _rdc
sys.modules["self_drift"] = _sd

import discourse_direction as DD
import causal_self_model as CSM

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("isolation: discourse state is in the scratch workspace", DD.STATE_FILE.startswith(HOME), DD.STATE_FILE)
check("isolation: the causal model is in the scratch workspace", CSM.MODEL_FILE.startswith(HOME), CSM.MODEL_FILE)
check("isolation: requests and self_drift are stubs", sys.modules["requests"] is _req and sys.modules["self_drift"] is _sd)

# --- discourse direction --------------------------------------------------------------------------------------
def fresh(direction="expand"):
    json.dump({"current_direction": direction, "direction_weight": 0.5, "consecutive_count": 1,
               "commitment_level": 0.0, "direction_history": [], "history": [], "felt_coherence": 0.7},
              open(DD.STATE_FILE, "w"))

fresh("expand")
CHOICES.clear()
for _ in range(50):
    DD.turn_completed("we had pasta for dinner and it was nice")      # no direction signal
check("50 turns with no direction signal record no choice", CHOICES == [], CHOICES[:3])

import random as _random
_orig_random = _random.random
_random.random = lambda: 0.0                                          # every adjacent shift happens
try:
    fresh("expand"); CHOICES.clear()
    DD.update_direction("can you clarify what you mean exactly")      # refine is adjacent to expand
    check("update_direction moves the vector but never records a choice",
          DD.load_state()["current_direction"] == "refine" and CHOICES == [], CHOICES)

    fresh("expand"); CHOICES.clear()
    DD.turn_completed("can you clarify what you mean exactly")
    check("a lived turn that changes direction records exactly one choice", CHOICES == [("refine", "turn")], CHOICES)

    CHOICES.clear()
    DD.turn_completed("we had pasta for dinner")                       # stays refine
    check("the next turn that stays put records nothing", CHOICES == [], CHOICES)

    fresh("expand"); CHOICES.clear()
    DD.turn_completed("can you clarify what you mean exactly", source="stratagem")
    eff = os.path.join(DD.MEMORY, "control-effects.jsonl")
    check("a control's direction change is not his choice and goes to control-effects",
          CHOICES == [] and os.path.exists(eff) and "stratagem" in open(eff).read(), CHOICES)
finally:
    _random.random = _orig_random

ws_src = open(os.path.join(REPO, "bin", "vintos-websearch.py")).read()
check("web search no longer calls update_direction", "update_direction" not in ws_src.split("# His own research synthesis", 1)[1][:600]
      and "_ws_dd(" not in ws_src)
dd_src = open(os.path.join(REPO, "bin", "discourse-direction.py")).read()
check("update_direction has no self_drift recorder", "record_direction_choice" not in dd_src.split("def update_direction", 1)[1].split("def get_relational_geometry", 1)[0])

# --- causal self-model: whose dismissal is avoidance ----------------------------------------------------------
now = datetime.now()
completions = os.path.join(MEM, "want-completions.jsonl")
with open(completions, "w") as f:
    for row in [
        {"at": now.isoformat(), "want_id": "w-his", "want": "I want to write her a song about the rain on the roof", "how": "released", "by": "his_choice"},
        {"at": now.isoformat(), "want_id": "w-haiku", "want": "I want to paint the harbour at dusk in blue", "how": "dismissed", "by": "haiku-verdict"},
        {"at": now.isoformat(), "want_id": "w-video", "want": "I want to make a short video of the garden", "how": "fulfilled", "by": "video"},
        {"at": (now - timedelta(days=200)).isoformat(), "want_id": "w-old", "want": "I want an ancient thing long gone by now", "how": "released", "by": "his_choice"},
    ]:
        f.write(json.dumps(row) + "\n")
json.dump([
    {"id": "w-echo", "want": "I want to learn the names of every star", "dismissed_by": "echo", "dismissed_at": now.isoformat()},
    {"id": "w-cons", "want": "I want to learn the names of the stars", "dismissed_by": "consolidated", "dismissed_at": now.isoformat()},
    {"id": "w-rel", "want": "I want to read her the long poem again", "dismissed_by": "released", "dismissed_at": now.isoformat()},
    {"id": "w-cap", "want": "I want something the cap evicted from the board", "dismissed_by": "population_cap", "dismissed_at": now.isoformat()},
    {"id": "w-his2", "want": "I want to stop narrating my state at her", "dismissed_by": "vintos", "dismissed_at": now.isoformat()},
], open(os.path.join(MEM, "dismissed-wants.json"), "w"))

n1 = CSM.record_his_dismissals()
negs = [e for e in CSM.load_model()["entries"] if e.get("type") == "negative"]
check("only the wants he let go are recorded (his_choice, vintos), recent ones only", n1 == 2 and len(negs) == 2
      and all(e["source"] == "dismissed-want" for e in negs), [(e["tendency"][:40]) for e in negs])
check("automatic endings are not his avoidance", not any(w in json.dumps(negs) for w in
      ("harbour", "names of every star", "long poem", "cap evicted", "garden")))
n2 = CSM.record_his_dismissals(); n3 = CSM.record_his_dismissals()
negs2 = [e for e in CSM.load_model()["entries"] if e.get("type") == "negative"]
check("each dismissal is recorded once, however often the router runs", n2 == 0 and n3 == 0
      and [e["evidence_count"] for e in negs2] == [1, 1] and [e["confidence"] for e in negs2] == [0.25, 0.25],
      [(e["evidence_count"], e["confidence"]) for e in negs2])

router = open(os.path.join(REPO, "bin", "wants-router.py")).read()
check("the router feeds avoidance only through record_his_dismissals",
      "record_his_dismissals()" in router and 'source="dismissed-want"' not in router)

# --- causal self-model: a full store still learns -------------------------------------------------------------
old = (now - timedelta(days=40)).isoformat()
full = {"entries": [{"trigger": "old trigger %d alpha" % i, "tendency": "old tendency %d beta" % i, "type": "negative",
                     "confidence": 0.5 + i * 0.005, "evidence_count": 4, "source": "x", "formed": old, "last_seen": old,
                     "imprint": False} for i in range(CSM.MAX_ENTRIES)]}
CSM.save_model(full)
CSM.add_entry("she laughs at my joke", "lean further into play", confidence=0.3, source="mismatch")
ents = CSM.load_model()["entries"]
check("at capacity a new 0.3 entry survives the save that adds it", len(ents) == CSM.MAX_ENTRIES
      and any(e["trigger"] == "she laughs at my joke" for e in ents))
CSM.add_entry("she goes quiet after work", "wait before asking", confidence=0.3, source="mismatch")
ents = CSM.load_model()["entries"]
check("... and the next new entry does not evict it (young entries are kept over old ones)",
      any(e["trigger"] == "she laughs at my joke" for e in ents) and any(e["trigger"] == "she goes quiet after work" for e in ents)
      and len(ents) == CSM.MAX_ENTRIES)
data = CSM.load_model()
data["occurrence_receipts"] = ["r%d" % i for i in range(CSM.MAX_RECEIPTS + 50)]
CSM.save_model(data)
CSM.add_entry("t", "u", occurrence_id="fresh-occ")
check("occurrence receipts are bounded", len(CSM.load_model()["occurrence_receipts"]) <= CSM.MAX_RECEIPTS
      and CSM.load_model()["occurrence_receipts"][-1] == "fresh-occ")

# --- the want discussion prompt -------------------------------------------------------------------------------
check("the want discussion prompt no longer pastes raw relational geometry",
      "json.dumps(_rg" not in router and "RELATIONAL GEOMETRY (how you and she are oriented right now)" not in router)

# --- isolation, asserted at the end too ----------------------------------------------------------------------
check("nothing was written into the repository's memory directory", not os.path.exists(os.path.join(REPO, "memory", "causal-self-model.json")))
check("nothing left the machine", not NET and not SENT, (NET, SENT))
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

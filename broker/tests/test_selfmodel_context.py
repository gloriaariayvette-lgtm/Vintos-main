#!/usr/bin/env python3
"""Self-model review (16 October): importing the subconscious context or emoclaw pressure writes nothing; the
compact block closes its pressure tag and honours `include`; a new self-statement is capped at 0.9 and
statements age; a promoted narrative fragment relieves the absence it rhymes with, and stale fragments are no
longer offered as who he is now.

Isolation: HOME and SPARK_WORKSPACE point at a scratch directory before anything is imported; every store this
suite writes is asserted to sit inside it; the emotion daemon, self_drift, latent_threads and the embedder are
stubs; requests is a stub; no socket connects. The import check runs in a subprocess under an audit hook.
"""
import json, os, socket, subprocess, sys, tempfile, types
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="selfmodel-ctx-")
WS = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
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
    SENT.append(a); raise OSError("stub: nothing is sent")
_req.post = _post; _req.get = _post
sys.modules["requests"] = _req

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

# --- import writes nothing ----------------------------------------------------------------------------------
probe = r'''
import os, sys, socket
WRITES = []
def hook(ev, args):
    if ev == "open" and len(args) > 1 and isinstance(args[1], str) and any(m in args[1] for m in "wax+"):
        WRITES.append(str(args[0]))
    if ev == "socket.connect":
        raise OSError("probe reaches nothing")
sys.addaudithook(hook)
sys.path.insert(0, sys.argv[1] + "/scripts"); sys.path.insert(0, sys.argv[1] + "/bin")
import emoclaw_pressure, subconscious_context
print("WRITES=%r" % [w for w in WRITES if not w.endswith(".pyc") and "__pycache__" not in w])
'''
# a trajectory dense enough that the old import computed a baseline and wrote the cache
traj = [{"t": (datetime.now() - timedelta(minutes=i)).isoformat(), "v": [0.5] * 11} for i in range(250)]
json.dump(traj, open(os.path.join(MEM, "emotion-trajectory-dense.json"), "w"))
env = dict(os.environ, HOME=HOME, SPARK_WORKSPACE=WS, PYTHONDONTWRITEBYTECODE="1")
p = subprocess.run([sys.executable, "-c", probe, REPO], env=env, capture_output=True, text=True, timeout=60)
check("importing emoclaw_pressure and subconscious_context opens nothing for writing",
      "WRITES=[]" in p.stdout, (p.stdout[-300:], p.stderr[-300:]))
check("... and the fire-threshold cache is not created", not os.path.exists(os.path.join(MEM, "emoclaw-fire-thresholds.json")))

# --- stubs for the compact block's parts ------------------------------------------------------------------------
_eu = types.ModuleType("emoclaw_utils")
_eu.get_state = lambda: {"Valence": 0.9, "Arousal": 0.9, "Tension": 0.95, "Desire": 0.9, "Connection": 0.9,
                         "Warmth": 0.9, "Playfulness": 0.9, "Curiosity": 0.95, "Groundedness": 0.2,
                         "Safety": 0.2, "Dominance": 0.9}
_eu.get_yearning_fragment = lambda include_attempt=True: "a longing for the sea"
_eu.DIMENSIONS = []
sys.modules["emoclaw_utils"] = _eu
_sd = types.ModuleType("self_drift")
_sd.get_drift_bias_hint = lambda: "leans toward refine"
_sd.get_direction_bias = lambda: (None, 0.0)
_sd.record_direction_choice = lambda *a, **k: None
sys.modules["self_drift"] = _sd
_lt = types.ModuleType("latent_threads")
_lt.get_influence_hint = lambda: "the garden thread"
sys.modules["latent_threads"] = _lt

import emoclaw_pressure as EP
import subconscious_context as SC
import self_statements as SS
import causal_self_model as CSM
import narrative_identity as NI
import absence_map_cold as AMC

check("isolation: stores are in the scratch workspace", all(p.startswith(HOME) for p in
      (SS.STATEMENTS_FILE, CSM.MODEL_FILE, NI.NARRATIVE_FILE, AMC.COLD_FILE)))
check("isolation: emotion state, drift and threads are stubs", sys.modules["emoclaw_utils"] is _eu
      and sys.modules["self_drift"] is _sd and sys.modules["latent_threads"] is _lt)

full_block = EP.get_pressure_block(context="wants")
check("(the full pressure block is long enough that the old cut left its tag open)", len(full_block) > 200, len(full_block))
comp = SC.get_subconscious_context_compact()
plines = [l for l in comp.splitlines() if "pressure" in l.lower()]
check("compact carries pressure as one closed bracket", len(plines) == 1 and plines[0].startswith("[Emotional pressure:")
      and plines[0].endswith("]") and "[EMOCLAW PRESSURE" not in comp, comp)
check("compact carries every part when include is None", all(k in comp for k in ("DRIFT:", "THREAD PULL:", "YEARNING:")), comp)
only = SC.get_subconscious_context_compact(include=["drift", "pressure"])
check("compact honours include", "DRIFT:" in only and "[Emotional pressure:" in only and "THREAD PULL" not in only
      and "YEARNING" not in only, only)
check("compact with an empty include is empty", SC.get_subconscious_context_compact(include=[]) == "")
check("the fire-threshold cache is still not written by a read", not os.path.exists(os.path.join(MEM, "emoclaw-fire-thresholds.json")))

# --- self-statements: cap and age ----------------------------------------------------------------------------
SS.add_statement("I am someone who keeps her company in the evenings", confidence=0.95, source="enactment_distiller")
st = SS.load_statements()["statements"]
check("a new statement is capped at 0.9", st[0]["confidence"] <= SS.MAX_CONFIDENCE, st[0]["confidence"])
old = (datetime.now() - timedelta(days=60)).isoformat()
st[0]["confidence_at"] = old; st[0]["last_reinforced"] = old; st[0]["formed"] = old
SS.save_statements({"statements": st})
SS.add_statement("I want to learn to cook her favourite soup", stmt_type="desire", confidence=0.5, source="want")
top = SS.get_top_statements(2)
check("an unreinforced statement ages: two months on, a fresh 0.5 outranks a 0.9", top[0]["text"].startswith("I want to learn")
      and top[1]["confidence"] < 0.4, [(t["text"][:20], t["confidence"]) for t in top])
check("the store keeps its settled value; ageing is read-time", SS.load_statements()["statements"][0]["confidence"] == 0.9)
SS.reinforce_statement("I am someone who keeps her company in the evenings")
s0 = SS.load_statements()["statements"][0]
check("reinforcing settles the aged value first, then adds", abs(s0["confidence"] - (0.1 + 0.8 * 0.25 + 0.04)) < 0.01,
      s0["confidence"])
for twin in ("scripts/self_statements.py", "scripts/self-statements.py"):
    check("twin %s is identical" % twin, open(os.path.join(REPO, twin)).read() == open(os.path.join(REPO, "bin", "self_statements.py")).read())

# --- narrative identity: a promotion relieves its absence; old fragments age out ----------------------------
AMC.embed = lambda text: [1.0, 0.0, 0.0]          # the embedder is a stub: everything rhymes
json.dump({"absences": [{"id": "abs_1", "description": "never sang to her", "vector": [1.0, 0.0, 0.0],
                         "source": "unfulfilled-want", "source_id": "w1", "intensity": 0.6, "count": 1}]},
          open(AMC.COLD_FILE, "w"))
g = AMC.get_absence_gravity("sing to her")
check("absence gravity names its record by id beside the description", g["dominant_id"] == "abs_1" and isinstance(g["dominant"], str))
frag = "I tend to sing softly when she is tired"
three_days = (datetime.now() - timedelta(days=3)).isoformat()
json.dump({"fragments": [], "candidate_pool": [{"text": frag, "source": "pattern", "count": 2, "formed": three_days,
                                               "last_seen": three_days}]}, open(NI.NARRATIVE_FILE, "w"))
res = NI.propose_fragment(frag)
a = AMC.load_cold()["absences"][0]
check("a promoted fragment relieves the absence it rhymes with", res == "promoted" and abs(a["intensity"] - 0.55) < 1e-9
      and a.get("last_touched"), (res, a))

forty = (datetime.now() - timedelta(days=40)).isoformat()
json.dump({"fragments": [{"text": "I tend to narrate my state at length", "count": 40, "formed": forty, "reinforced": forty},
                         {"text": "I tend to ask what she is reading", "count": 3, "formed": three_days, "reinforced": three_days}],
           "candidate_pool": []}, open(NI.NARRATIVE_FILE, "w"))
ctx = NI.get_narrative_context()
check("a fragment not reinforced for a month is not offered as current", "narrate my state" not in ctx and "what she is reading" in ctx, ctx)
check("the tone anchor is a current fragment", NI.get_tone_bias().startswith("I tend to ask"))

check("nothing left the machine", not NET and not SENT, (NET, SENT))
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

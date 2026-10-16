#!/usr/bin/env python3
"""Self-model review (16 October): imagined conversations (premonitions, dream_only) are not real absences or
unresolved threads; a new absence never reinforces, and so hides inside, a closed one; a merged absence keeps
every source and closes by any of them; absences whose source ended are retired on each scan. Gravity wells:
a write of the state file is not a visit, gravity's own pulled state does not deepen the well that pulled it,
and mass fades by time rather than by write count.

Isolation: HOME and SPARK_WORKSPACE point at a scratch directory before anything is imported; the wells module
derives its store from its own file, so it is repointed and that is asserted; the embedder is a stub;
requests is a stub; no socket connects.
"""
import json, os, socket, sys, tempfile, types
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="selfmodel-abs-")
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

import absence_map_cold as AMC
import living_trajectory as LT
import emotional_gravity_wells as EGW

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

EGW.MEMORY = MEM
EGW.WELLS_FILE = os.path.join(MEM, "gravity-wells.json")
check("isolation: absence, trajectory and wells stores are in the scratch workspace",
      AMC.COLD_FILE.startswith(HOME) and LT.OUT.startswith(HOME) and EGW.WELLS_FILE.startswith(HOME),
      (AMC.COLD_FILE, LT.OUT, EGW.WELLS_FILE))

VEC = {"sea": [1.0, 0.0, 0.0], "song": [0.0, 1.0, 0.0]}
def fake_embed(text):
    t = text.lower()
    return VEC["sea"] if ("sea" in t or "imagined" in t) else (VEC["song"] if "song" in t else [0.0, 0.0, 1.0])
AMC.embed = fake_embed
check("isolation: the embedder is a stub", AMC.embed is fake_embed)

old = (datetime.now() - timedelta(days=30)).isoformat()
MARK = "[AN IMAGINED POSSIBILITY — a conversation not yet had. It has NOT occurred.]\n\nWe walk by the sea"
threads = [
    {"id": "t-prem", "source": "premonition", "thread": MARK, "timestamp": old, "consumed": False, "dream_only": True},
    {"id": "t-unflag", "source": "premonition", "thread": MARK + " again", "timestamp": old, "consumed": False},
    {"id": "t-real", "source": "chat", "thread": "she asked about the song I never finished", "timestamp": old, "consumed": False},
]
json.dump(threads, open(os.path.join(MEM, "unfinished-threads.json"), "w"))
json.dump([], open(os.path.join(MEM, "current-wants.json"), "w"))
json.dump({"absences": []}, open(AMC.COLD_FILE, "w"))
AMC.build_from_unfulfilled()
ab = AMC.load_cold()["absences"]
check("an imagined conversation never becomes a structural absence", len(ab) == 1 and ab[0]["source_id"] == "t-real"
      and not any(a["description"].startswith("[AN IMAGINED") for a in ab), [a["description"][:40] for a in ab])

# living trajectory: no imagined thread in unresolved
json.dump({"threads": []}, open(os.path.join(MEM, "latent-threads.json"), "w"))
traj = LT.build_and_write()
check("living trajectory does not list an imagined conversation as unresolved",
      not any(u["text"].startswith("[AN IMAGINED") for u in traj["unresolved"])
      and any("song I never finished" in u["text"] for u in traj["unresolved"]), [u["text"][:30] for u in traj["unresolved"]])
check("living trajectory is written atomically to its own store", json.load(open(LT.OUT))["version"] == traj["version"]
      and not os.path.exists(LT.OUT + ".tmp"))

# a closed absence is not matched; a merged absence closes by either source
json.dump({"absences": [{"id": "abs_closed", "description": "a sea I never saw", "vector": VEC["sea"], "source": "unfulfilled-want",
                         "source_id": "w-old", "intensity": 0.8, "count": 3, "reached": "reached"}]}, open(AMC.COLD_FILE, "w"))
AMC.register_absence("to see the sea with her", source="unfulfilled-want", intensity=0.4, source_id="w-a")
ab = AMC.load_cold()["absences"]
closed = [a for a in ab if a["id"] == "abs_closed"][0]
opened = [a for a in ab if not a.get("reached")]
check("a new absence like a closed one is a new open record; the closed one is untouched",
      len(opened) == 1 and opened[0]["source_ids"] == ["w-a"] and closed["count"] == 3 and closed["intensity"] == 0.8)
AMC.register_absence("the sea, with her, someday", source="unfulfilled-want", intensity=0.4, source_id="w-b")
o = [a for a in AMC.load_cold()["absences"] if not a.get("reached")]
check("a second similar source merges and keeps both ids", len(o) == 1 and o[0]["source_ids"] == ["w-a", "w-b"]
      and abs(o[0]["intensity"] - 0.45) < 1e-9, o)
AMC.register_absence("the sea, with her, someday", source="unfulfilled-want", intensity=0.4, source_id="w-b")
o = [a for a in AMC.load_cold()["absences"] if not a.get("reached")]
check("rescanning the second source does not reinforce again", abs(o[0]["intensity"] - 0.45) < 1e-9, o[0]["intensity"])
check("retire_reached closes the merged record by its second source", AMC.retire_reached(source_id="w-b") == 1
      and not [a for a in AMC.load_cold()["absences"] if not a.get("reached")])

AMC.embed = lambda text: []                       # embedding failed
json.dump({"absences": []}, open(AMC.COLD_FILE, "w"))
for _ in range(3):
    AMC.register_absence("a capability that is not there", source="capability-gap", intensity=0.65, source_id=None)
check("with no embedding, rescans of one description do not pile up", len(AMC.load_cold()["absences"]) == 1)
AMC.embed = fake_embed

# retire_ended_sources is wired into the scan
json.dump({"absences": []}, open(AMC.COLD_FILE, "w"))
wants = [{"id": "w-live", "want": "to sing the song for her", "timestamp": old},
         {"id": "w-done", "want": "to see the sea once", "timestamp": old}]
json.dump(wants, open(os.path.join(MEM, "current-wants.json"), "w"))
json.dump([], open(os.path.join(MEM, "unfinished-threads.json"), "w"))
AMC.build_from_unfulfilled()
check("two old wants register two absences", len([a for a in AMC.load_cold()["absences"] if not a.get("reached")]) == 2)
wants[1]["fulfilled"] = True
json.dump(wants, open(os.path.join(MEM, "current-wants.json"), "w"))
AMC.build_from_unfulfilled()
ab = {a["source_id"]: a for a in AMC.load_cold()["absences"]}
check("a scan retires the absence of a fulfilled want and keeps the live one", ab["w-done"].get("reached") == "source-ended"
      and not ab["w-live"].get("reached"), ab)
json.dump([wants[0]], open(os.path.join(MEM, "current-wants.json"), "w"))
os.remove(os.path.join(MEM, "unfinished-threads.json"))
AMC.build_from_unfulfilled()
check("an unreadable thread store retires nothing", not {a["source_id"]: a for a in AMC.load_cold()["absences"]}["w-live"].get("reached"))

# --- gravity wells ------------------------------------------------------------------------------------------
def _write_txt(vec):                               # the name emoclaw_utils' state-file writer has
    return EGW.record_visit(vec, 0.0)
_write_txt.__code__ = _write_txt.__code__.replace(co_filename=os.path.join(REPO, "bin", "emoclaw_utils.py"))
v = [0.5] * 11
for _ in range(20):
    _write_txt(v)
check("a state-file write is not a visit", EGW.load_wells()["wells"] == [] and not os.path.exists(EGW.WELLS_FILE))

d = EGW.record_visit(v)
check("a chat route's visit forms a well", len(d["wells"]) == 1 and d["wells"][0]["visits"] == 1 and d["wells"][0]["id"].startswith("w_"))
EGW.record_visit([0.51] * 11)
check("a return within the cooldown is the same stay, not a second visit", EGW.load_wells()["wells"][0]["visits"] == 1)

wd = EGW.load_wells()
wd["wells"][0]["last_visit"] = (datetime.now() - timedelta(hours=2)).isoformat()
wd["wells"][0]["mass"] = 5.0
wd["decayed_at"] = datetime.now().isoformat()
json.dump(wd, open(EGW.WELLS_FILE, "w"))
pulled = EGW.apply_gravity([0.56] * 11)
check("gravity pulls the state toward the well and remembers what it pulled to", pulled != [0.56] * 11
      and EGW.load_wells().get("last_pull", {}).get("vector") == pulled)
m0 = EGW.load_wells()["wells"][0]["mass"]
EGW.record_visit(pulled)
w = EGW.load_wells()["wells"][0]
check("gravity's own pulled state does not deepen the well that pulled it", len(EGW.load_wells()["wells"]) == 1
      and w["visits"] == 1 and abs(w["mass"] - m0) < 1e-3, w)

wd = EGW.load_wells()
wd["decayed_at"] = (datetime.now() - timedelta(days=EGW.MASS_HALF_LIFE_DAYS)).isoformat()
wd["last_pull"] = {}
wd["wells"][0]["mass"] = 2.0
json.dump(wd, open(EGW.WELLS_FILE, "w"))
EGW.record_visit([0.1] * 11)                      # far away: a new well; the old one decays by time
w0 = [x for x in EGW.load_wells()["wells"] if x["visits"] == 1 and x["vector"][0] == 0.5][0]
check("mass fades by elapsed time (one half-life halves it)", abs(w0["mass"] - 1.0) < 0.01, w0["mass"])
check("nothing was written beside the repository", not os.path.exists(os.path.join(REPO, "memory", "gravity-wells.json")))

check("nothing left the machine", not NET and not SENT, (NET, SENT))
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

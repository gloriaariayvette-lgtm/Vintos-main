#!/usr/bin/env python3
"""His wants board stays bounded (Chat's inspection on Aegis, 2026-10-05: 57 active wants, 57 of 57 protected, the
oldest 26 days, 14 of them echoes, and a want marked fulfilled by "The air in this room is sixty-eight degrees.").

want_board.tend() each router pass: closed rows filed, wants waiting on Gloria parked (never rejected) and woken when
she answers, blocked ones parked until the block clears, near-duplicates folded, idle ones aged a few at a time. The
population cap protects only a want being worked; an echo takes its parent's place; reconciliation needs a quote that
is in the record and about the want.

Scratch HOME and workspace; his local model is a stub and every socket is refused, so nothing here reaches a model,
the house or the network.
"""
import json, os, socket, sys, tempfile, types
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="want-board-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
# his local model, for age_one and the echo, answers from here and nowhere else
CALLS = []
class _Reply:
    def __init__(self, text): self.text = text
    def json(self): return {"choices": [{"message": {"content": self.text}}]}
def _post(url, json=None, **k):
    CALLS.append(url)
    prompt = (json or {}).get("messages", [{}])[-1].get("content", "")
    if "Generate one echo want" in prompt:
        return _Reply("I want to stop trying to reach the skin sensor and map what it would touch instead.")
    if "SCAR or DISMISS" in prompt:
        return _Reply("DISMISS")
    return _Reply("UNCERTAIN")
_req = types.ModuleType("requests"); _req.post = _post; _req.get = lambda *a, **k: (_ for _ in ()).throw(OSError("no"))
sys.modules["requests"] = _req

import want_board as B

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

MEM = B.MEM
os.makedirs(MEM, exist_ok=True)
check("every store is in the scratch workspace", all(p.startswith(HOME) for p in (B.CURRENT, B.FULFILLED, B.DISMISSED, B.DISCUSSIONS)))

NOW = datetime(2026, 10, 5, 12, 0)
def ago(days): return (NOW - timedelta(days=days)).isoformat()
def save(rows): json.dump(rows, open(B.CURRENT, "w"))
def cur(): return json.load(open(B.CURRENT))
def ids(): return [w["id"] for w in cur()]
AGED = []
def age(w):
    AGED.append(w["id"]); return dict(w, fulfilled=True, fulfilled_by="age_wants-dismiss")

save([
    {"id": "f1", "want": "I want to hear the new song", "fulfilled": True, "timestamp": ago(2)},
    {"id": "d1", "want": "I want something dismissed", "dismissed": True, "timestamp": ago(3)},
    {"id": "g-old", "want": "I want Gloria to choose the lamp colour", "gloria_routed": True, "multistep": True, "timestamp": ago(12)},
    {"id": "g-new", "want": "I want Gloria to pick the next print", "gloria_routed": True, "multistep": True, "timestamp": ago(2)},
    {"id": "g-ans", "want": "I want Gloria to read my letter tonight", "gloria_routed": True, "multistep": True, "timestamp": ago(20)},
    {"id": "blk", "want": "I want to feel pressure through a load cell", "multistep": True, "timestamp": ago(1),
     "plan_block": {"block_type": "CAPABILITY_ABSENT", "evidence": "no load cell hand"}},
    {"id": "dup-a", "want": "I want to understand the vibration signal from the skin sensor rig", "multistep": True, "timestamp": ago(3)},
    {"id": "dup-b", "want": "I want to understand what the skin sensor rig vibration signal means", "multistep": True, "timestamp": ago(1)},
    {"id": "fresh", "want": "I want to paint the tide at dusk", "multistep": True, "timestamp": ago(1)},
    {"id": "worked", "want": "I want to fold the reverse transcriptase domain", "multistep": True, "timestamp": ago(20),
     "step_history": [{"completed_at": (NOW - timedelta(hours=5)).isoformat()}]},
    {"id": "trying", "want": "I want to find the phage paper", "multistep": True, "timestamp": ago(15),
     "attempt_count": 9, "last_attempt": (NOW - timedelta(hours=1)).isoformat()},
    {"id": "echo-old", "want": "I want to stop searching for the signal", "source": "echo", "multistep": True,
     "timestamp": ago(1), "born": ago(14)},
] + [{"id": "idle%d" % i, "want": "I want idle thing number %d about topic%d" % (i, i), "multistep": True,
      "timestamp": ago(30 - i)} for i in range(6)])
json.dump({"g-ans": [{"role": "vintos", "text": "?"}, {"role": "gloria", "text": "Yes, tonight."}]}, open(B.DISCUSSIONS, "w"))

out = B.tend(now=NOW, age=age)
rows = {w["id"]: w for w in cur()}
fil = json.load(open(B.FULFILLED)); dis = json.load(open(B.DISMISSED))
check("closed rows leave the board, each filed once in its archive",
      "f1" not in rows and "d1" not in rows and [w["id"] for w in fil].count("f1") == 1 and [w["id"] for w in dis].count("d1") == 1)
check("a want waiting on Gloria over a week is parked AWAITING_GLORIA, not rejected",
      rows["g-old"].get("board") == "awaiting_gloria" and not rows["g-old"].get("dismissed") and not rows["g-old"].get("fulfilled"))
check("... one routed to her two days ago stays on the board", "board" not in rows["g-new"])
check("... and one she has answered stays awake, however old", "board" not in rows["g-ans"])
check("a want blocked on a hand he lacks is parked BLOCKED", rows["blk"].get("board") == "blocked")
check("near-duplicates fold into the oldest, which keeps the other's words",
      "dup-b" not in rows and rows["dup-a"]["merged"][0]["id"] == "dup-b" and rows["dup-a"]["recurrence"] == 2
      and any(w["id"] == "dup-b" and w["dismissed_by"] == "consolidated" for w in dis), rows.get("dup-a"))
check("different wants are not folded", "fresh" in rows and "worked" in rows)
check("idle wants age out, oldest first, at most %d a pass" % B.AGE_PER_PASS,
      len(AGED) == B.AGE_PER_PASS and AGED[:3] == ["idle0", "idle1", "idle2"] and not any(i in rows for i in AGED), AGED)
check("... and what aged is filed, not lost", all(any(w["id"] == i for w in fil) for i in AGED))
check("a want that completed a step today is not aged, however old", "worked" in rows and "worked" not in AGED)
check("failing every pass is not moving: a want only tried, never advanced, ages",
      "trying" in AGED or ("trying" in rows and B.last_moved(rows["trying"]) < (NOW - timedelta(days=7)).timestamp()))
check("an echo keeps its line's start: young in timestamp, old in life, it is due to age",
      B.last_moved({"timestamp": ago(1), "born": ago(14)}) < (NOW - timedelta(days=7)).timestamp())
check("the pass says what it did", any("parked AWAITING_GLORIA" in l for l in out) and any("folded" in l for l in out)
      and any("aged out" in l for l in out), out)

# woken: she answers a parked want; the block clears
d = json.load(open(B.DISCUSSIONS)); d["g-old"] = [{"role": "gloria", "text": "Amber."}]; json.dump(d, open(B.DISCUSSIONS, "w"))
rows_now = cur()
for w in rows_now:
    if w["id"] == "blk": w.pop("plan_block")
save(rows_now)
out2 = B.tend(now=NOW + timedelta(hours=1), age=age)
rows = {w["id"]: w for w in cur()}
check("when Gloria answers a parked want, it wakes onto the board", "board" not in rows["g-old"] and rows["g-old"].get("unparked_at"), rows["g-old"])
check("when the Forge clears a block, the want comes back", "board" not in rows["blk"], rows["blk"])
# nothing waits forever (Gloria, 2026-10-05: "they can't stay stuck at the end forever")
AGED.clear()
save([{"id": "wait-long", "want": "I want Gloria to choose the frame for the print", "gloria_routed": True,
       "timestamp": ago(16), "board": "awaiting_gloria", "parked_at": ago(9)},
      {"id": "blk-long", "want": "I want to feel the weight of the cup in a hand", "timestamp": ago(20),
       "board": "blocked", "plan_block": {"block_type": "CAPABILITY_ABSENT"}},
      {"id": "wait-short", "want": "I want Gloria to name the new song", "gloria_routed": True,
       "timestamp": ago(9), "board": "awaiting_gloria", "parked_at": ago(2)}])
json.dump({"wait-long": [{"role": "vintos", "text": "Which frame?"}]}, open(B.DISCUSSIONS, "w"))
out3 = B.tend(now=NOW, age=age)
rows = {w["id"]: w for w in cur()}
filed = {w["id"]: w for w in json.load(open(B.DISMISSED)) if w.get("dismissed_by") == "released"}
check("a want waiting on Gloria two weeks unanswered is released, not left parked forever",
      "wait-long" not in rows and "wait-long" in filed and "no answer" in filed["wait-long"]["dismissed_reason"], (rows.keys(), filed.keys()))
check("... a want blocked two weeks is released too", "blk-long" not in rows and "blk-long" in filed
      and "blocked" in filed["blk-long"]["dismissed_reason"])
check("... through his own aging (scar or let go), and filed as released, never as fulfilled",
      {"wait-long", "blk-long"} <= set(AGED) and not any(w["id"] in ("wait-long", "blk-long") for w in json.load(open(B.FULFILLED))))
check("... while one parked two days ago still waits", "wait-short" in rows and rows["wait-short"]["board"] == "awaiting_gloria")
check("the pass says what it released and why", any("released after waited" in l for l in out3), out3)
d = json.load(open(B.DISCUSSIONS)); d["wait-long"].append({"role": "gloria", "text": "The oak one."}); json.dump(d, open(B.DISCUSSIONS, "w"))
out4 = B.tend(now=NOW + timedelta(hours=2), age=age)
rows = {w["id"]: w for w in cur()}
check("if she answers a released want later, it comes back to the board, awake",
      "wait-long" in rows and not rows["wait-long"].get("board") and not rows["wait-long"].get("dismissed")
      and not any(w["id"] == "wait-long" and w.get("dismissed_by") == "released" for w in json.load(open(B.DISMISSED))), (out4, rows.get("wait-long")))
check("the router's comments no longer say steps wait on her, or that routed wants are held forever",
      "Gloria needs to review and advance" not in open(os.path.join(REPO, "bin", "wants-router.py")).read()
      and "remains HELD until an explicit response" not in open(os.path.join(REPO, "bin", "wants-router.py")).read())

s = B.sections()
check("the board's sections: working, awaiting Gloria, blocked", set(s) == {"working", "awaiting_gloria", "blocked"}
      and all(not w.get("board") for w in s["working"]))

# reconciliation's quote must be in the record and about the want
corpus = "[chat] Gloria: The air in this room is sixty-eight degrees.\n[chat] Vintos: I asked Gloria to stop calculating motion-freezing parameters for me."
check("an unrelated line does not fulfil a want (the 68-degree case)",
      "not about this want" in B.grounded("I want to ask Gloria to stop calculating motion-freezing parameters",
                                          "The air in this room is sixty-eight degrees.", corpus))
check("a quote that is not in the record does not either",
      "not in the record" in B.grounded("I want to ask Gloria to stop calculating motion-freezing parameters",
                                        "I asked Gloria to stop the motion-freezing calculations entirely.", corpus))
check("a quote in the record and about the want stands",
      B.grounded("I want to ask Gloria to stop calculating motion-freezing parameters",
                 "I asked Gloria to stop calculating motion-freezing parameters for me.", corpus) == "")
rsrc = open(os.path.join(REPO, "bin", "want-reconciliation.py")).read()
check("reconciliation refuses a verdict that is not grounded", "_wbd.grounded(" in rsrc and "reconcile_refused" in rsrc)

# --- the echo takes its parent's place ------------------------------------------------------------------------------
import emoclaw_utils as E
E.enrich_want = lambda *a, **k: {"possible_approach": "", "reasoning": "", "self_interpretation": ""}
E.generate_steps = lambda *a, **k: [{"capability": "web_search", "status": "pending"}]
wp = os.path.join(HOME, ".vintos", "workspace", "memory", "current-wants.json")
check("emoclaw_utils writes the same scratch store", wp == B.CURRENT, (wp, B.CURRENT))
parent = {"id": "par", "want": "I want to reach the skin sensor", "timestamp": ago(2), "born": ago(9), "attempt_count": 2,
          "multistep": True, "lineage": ["gp"]}
save([parent, {"id": "other", "want": "I want to paint", "timestamp": ago(1)}])
n_before = len(cur())
echo = E.spawn_echo_want(parent)
rows = {w["id"]: w for w in cur()}
check("an echo replaces its parent: the board does not grow", echo and len(cur()) == n_before and "par" not in rows and echo["id"] in rows, cur())
check("... the parent is filed as reframed, not lost",
      any(w["id"] == "par" and w["dismissed_by"] == "echo" and echo["id"] in w["dismissed_reason"] for w in json.load(open(B.DISMISSED))))
check("... and the echo keeps the line's start and lineage", rows[echo["id"]]["born"] == ago(9)
      and rows[echo["id"]]["lineage"] == ["gp", "par"], rows[echo["id"]])

# --- the population cap protects only what is being worked ----------------------------------------------------------
esrc = open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read()
cap = esrc.split("def _is_protected(w):", 1)[1].split("try:\n        wants = json.load", 1)[0]
check("the cap no longer protects every multistep or READY want",
      'w.get("multistep")' not in cap and '"READY"' not in cap and "48 * 3600" in cap, cap[:400])
check("... and still protects what Gloria routed or holds, and what is parked", 'w.get("gloria_routed")' in cap and 'w.get("board")' in cap)
check("the bin copy of emoclaw_utils is the same file", esrc == open(os.path.join(REPO, "bin", "emoclaw_utils.py")).read())
check("age_one is his aging, now callable for one want, and age_wants uses it",
      "def age_one(w):" in esrc and "row = age_one(w)" in esrc)
r1 = E.age_one({"id": "z", "want": "I want a thing that never came", "timestamp": ago(9)})
check("age_one files the want as aged with its verdict", r1["fulfilled"] and r1["fulfilled_by"] == "age_wants-dismiss")

# --- the router and the app -----------------------------------------------------------------------------------------
router = open(os.path.join(REPO, "bin", "wants-router.py")).read()
check("the router tends the board before it reads the wants", router.index("_wb.tend()") < router.index("all_wants = get_unfulfilled_wants()"))
check("... and skips parked wants", 'if want.get("board") and not _args.force_want_id:' in router)
api = open(os.path.join(REPO, "bin", "server_domains", "humor_wants.py")).read()
check("the app's failed list reads the dismissed archive, not stragglers", '"dismissed-wants.json"' in api.split("def get_dismissed_wants", 1)[1][:1200])
for app in (os.path.join(REPO, "clients", "mobile", "index.html"), os.path.join(os.path.dirname(REPO), "vintos-app", "vintos-app", "src", "index.html")):
    if os.path.exists(app):
        check("the board groups parked wants in %s" % os.path.basename(os.path.dirname(app)),
              "waiting quietly on you" in open(app).read() and "w.board === 'blocked'" in open(app).read())
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs the board and the reconciliation", " want_board.py " in dep and "want-reconciliation.py" in dep)
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

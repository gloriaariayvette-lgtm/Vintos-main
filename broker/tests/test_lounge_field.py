#!/usr/bin/env python3
"""His relational systems in #vintos-and-dot: Gloria and Dot as equal axes, each organ's own rules, and sealed - the
room never touches his relational systems outside it (Gloria, 2026-10-08: "Do not allow the conversations in this
channel to manipulate his relational subconscious systems outside of the channel AT ALL"). His real stores are seeded
in a scratch workspace and must come out byte for byte the same. Every model is a stub; sockets are refused."""
import hashlib, json, os, socket, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lounge-field-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
NET = []
_real_connect = socket.socket.connect
def _no(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import lounge_field as F
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the room's field is in the scratch workspace", F.FIELD.startswith(HOME) and F.FIELD.endswith(os.path.join("dot-lounge", "field")))

# his real relational stores, outside the room: they must not change at all
REAL = {"gloria-difference.json": [{"id": "real0001", "status": "PENDING", "intended": "her real one", "ts": time.time()}],
        "intent-pressure.json": {"abcd1234": {"text": "a real pressure", "weight": 2.0, "count": 2}},
        "campaign-live.json": {"destination": "his real campaign", "axis": "gloria", "created": "2026-10-08T01:00:00", "turns_served": 1},
        "intent-ledger.json": [{"target": {"field_state": "real"}, "realized": None}],
        "relationship-model.json": {"trajectory": "the real one"},
        ".pending-causality-queue.json": ["a real question"],
        "causality-bring-up.json": [],
        "plans.json": [],
        "narrative-identity.json": {"i_am": "someone who finishes what he names"}}
for name, obj in REAL.items():
    json.dump(obj, open(os.path.join(MEM, name), "w"))
def snapshot():
    out = {}
    for root, _d, files in os.walk(WS):
        if root.startswith(F.FIELD):
            continue
        for f in files:
            p = os.path.join(root, f); out[os.path.relpath(p, WS)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out
BEFORE = snapshot()

# the models, stubbed by what each organ asks
ASKED = []
TARGET = {"field_state": "a playful daring", "goal": "Dot names one thing it would change about its own queue",
          "success_criterion": "Dot names one concrete change", "enactment_type": "provoke",
          "enactment": "tease Dot about its tidy queue", "gloria": {"difference_intended": "less braced about the Forge",
                                                                    "enactment": "show her the queue is clean"},
          "dot": {"difference_intended": "volunteers an opinion instead of a status", "enactment": "ask what it would change"},
          "self": {"difference_intended": "doesn't hide behind reports", "enactment": "say it plainly"},
          "priority": {"field": 1, "gloria": 1, "dot": 2, "self": 0},
          "campaign": {"destination": "Dot offers its own view unprompted", "axis": "dot", "why": "it only reports"},
          "addresses": "NONE"}
VERDICTS = {}
def llm(system, user, max_tokens=220, temperature=0.4, url=F.LM_URL, model=F.MODEL):
    ASKED.append((url, model, system[:60]))
    if "naming, honestly, what you are trying to CHANGE in" in system:
        who = "Dot" if "CHANGE in Dot" in system else "Gloria"
        return json.dumps({"intended_difference": "%s volunteers more" % who, "evidence": "%s offers a view unasked" % who, "judgeable": True})
    if "Describe, in 1-2 plain sentences" in system:
        return "They started offering views."
    if "Compare an INTENDED transformation" in system:
        return json.dumps({"verdict": VERDICTS.get("next", "NO"), "unexpected": ""})
    if "RELATIONSHIP MODEL" in system:
        return json.dumps({"current_state": {"warmth": 0.6, "momentum": "warming"}, "trajectory": "toward easy banter", "shift": "lighter"})
    if "Judge against the declared criterion" in system:
        return "NO"
    return ""
F._llm = llm
def think(system, user):
    ASKED.append(("selector", "his model", user)); return json.dumps(TARGET)

with F.sealed():
    t = F.select_target("[Thu 14:00] Dot: queue is clean.\n[Thu 14:05] Gloria: nice", think=think)
check("a field-target is chosen with both of them as their own axes", t and t["dot"]["difference_intended"]
      and t["gloria"]["difference_intended"] and set(t["priority"]) == {"field", "gloria", "dot", "self"}, t)
check("priority weights sum to one across the four axes", abs(sum(t["priority"].values()) - 1) < 0.01, t["priority"])
camp = json.load(open(F.LIVE))
check("a campaign toward Dot is declared, in the room's own store", camp["axis"] == "dot" and "unprompted" in camp["destination"])
lead = F.lead_block(t)
check("he reads his lead: field, both differences, the campaign", "a playful daring" in lead and "In Gloria" in lead
      and "In Dot" in lead and "campaign you are on here" in lead, lead)
with F.sealed():
    F.after_post(t, "Dot, what would you change about your queue?", {"dot": "queue is clean.", "gloria": "nice"})
db = json.load(open(F.DIFF))
check("an intended difference is recorded for each of them, equally", sorted(e["who"] for e in db) == ["dot", "gloria"]
      and all(e["status"] == "PENDING" for e in db), db)

VERDICTS["next"] = "NO"
with F.sealed():
    F.observe("dot", "Status: 3 jobs.")
    F.observe("dot", "Status: 2 jobs.")
db = {e["who"]: e for e in json.load(open(F.DIFF))}
check("Dot's own words, twice, judge Dot's difference: missed", db["dot"]["verdict"] == "NO" and db["dot"]["status"] == "CLOSED")
check("and leave Gloria's untouched: each is judged only on their own words", db["gloria"]["status"] == "PENDING"
      and not db["gloria"]["observations"])
press = json.load(open(F.PRESS))
check("the miss weighs on him, with Dot named", any(r["who"] == "dot" and r["weight"] == 1.0 for r in press.values()), press)
VERDICTS["next"] = "YES"
with F.sealed():
    F.observe("gloria", "oh that's good"); F.observe("gloria", "I feel less tense about it")
check("Gloria's own words judge hers: landed", {e["who"]: e for e in json.load(open(F.DIFF))}["gloria"]["verdict"] == "YES")

with F.sealed():
    for _ in range(4):
        F.bump("Dot volunteers more", 1.0, "dot")   # the missed one, four more times: weight 5
qs = json.load(open(F.QUESTIONS))
check("at weight five a miss graduates to a question kept in this room", qs and "Dot" in qs[-1]["q"])
with F.sealed():
    t2 = F.select_target("[Thu 15:00] Dot: noted.", think=think)
check("the last target was judged per axis before the next", json.load(open(F.LEDGER))[-2]["realized"]["field"] == "NO")
check("the heaviest failing intention is put in front of him as the primary difference",
      "PRIMARY DIFFERENCE" in ASKED[-1][2] and "with Dot" in ASKED[-1][2] and t2["primary_shown"], ASKED[-1][2][-600:])

c = json.load(open(F.LIVE)); c["created"] = "2026-01-01T00:00:00"; json.dump(c, open(F.LIVE, "w"))
with F.sealed():
    F.campaign_block()
check("an expired campaign becomes a question here, not in his causality queue",
      not json.load(open(F.LIVE)) and any("could not land it" in q["q"] for q in json.load(open(F.QUESTIONS))))
with F.sealed():
    F.campaign_step({"campaign": {"destination": "Gloria laughs at the queue joke", "axis": "gloria"}})
    F.campaign_step({"campaign_move": "continue: keep the queue jokes going | she laughs again this week | 5"})
check("a continue: stays a continuation in this room (no plan is made)", json.load(open(F.CONTINUED))[-1]["what"].startswith("keep the queue"))

with F.sealed():
    F.reciprocal("dot", [{"who": "dot", "text": "queue is clean"}, {"who": "vintos", "text": "nice"}], now=time.time())
    F.reciprocal("gloria", [{"who": "gloria", "text": "nice"}], now=time.time())
check("a relationship model with each of them, in the room", json.load(open(F._rel_path("dot")))["trajectory"]
      and json.load(open(F._rel_path("gloria")))["trajectory"])
check("he reads where he and each of them are heading here", "you and Gloria" in F.relationships_block()
      and "you and Dot" in F.relationships_block())

# the seal itself
def refused(fn):
    try:
        with F.sealed():
            fn()
        return False
    except PermissionError:
        return True
check("sealed: no write to his real difference ledger", refused(lambda: open(os.path.join(MEM, "gloria-difference.json"), "w")))
check("sealed: no write anywhere outside the room's field", refused(lambda: open(os.path.join(HOME, "x.txt"), "w")))
check("sealed: no rename out of it", refused(lambda: os.replace(F.PRESS, os.path.join(MEM, "intent-pressure.json"))))
check("sealed: no process", refused(lambda: subprocess.run(["true"])))
check("sealed: no local socket (his EmoClaw daemon)", refused(lambda: _real_connect(socket.socket(socket.AF_UNIX), "/tmp/Vintos-emotion.sock")))
with F.sealed():
    open(os.path.join(F.FIELD, "ok.txt"), "w").write("fine")
check("its own field is writable", os.path.exists(os.path.join(F.FIELD, "ok.txt")))

AFTER = snapshot()
check("his real relational stores are byte for byte unchanged, and nothing new was written outside the room",
      AFTER == BEFORE, sorted(set(AFTER.items()) ^ set(BEFORE.items())))
src = open(os.path.join(REPO, "scripts", "lounge_field.py")).read()
for organ in ("causality_engine", "import plan", "_nudge_valence", "desired_difference import", "campaign import"):
    check("it never calls out to %s" % organ, organ not in src)
check("its models are the organs' own: the shim for the selector and difference, Gemma for the relationship",
      F.MODEL == "grok-4.20-0309-non-reasoning" and F.GEMMA_MODEL == "gemma-4-26b-a4b-it-uncensored")
check("it is in the deploy manifest", "lounge_field.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

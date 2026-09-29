#!/usr/bin/env python3
"""A spark is put to him as a question about a hand, and his yes reaches the Forge (2026-09-29).

The Forge had only Lab seeds: every spark became an "ask Gloria" want, which is never Forge work.
Scratch HOME and workspace; his answer is a stub and the Forge request is a stub; nothing reaches the
network.
"""
import importlib, json, os, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-spark-hands-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
sys.path.insert(0, os.path.join(REPO, "scripts"))
json.dump([], open(os.path.join(WS, "memory", "current-wants.json"), "w"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

import spark_hands as H, skill_forge as SF, forge_house as FH
check("every store is in the scratch workspace", all(p.startswith(HOME) for p in (H.LEDGER, H.WANTS, SF.PROPOSALS)),
      (H.LEDGER, SF.PROPOSALS))
def no_network(*a, **k): raise AssertionError("a test reached for the network")
H._think = no_network

INVENTORY = ["web_search", "write_journal", "send_email", "make_art"]
SPARKS = [
    {"key": "lab1", "source": "lab", "text": "an ESM run on KaiC", "seen": "2026-09-01"},
    {"key": "sk1", "source": "skill_surfing", "text": "A skill page: an agent that reads its own server logs "
     "and tells its person when something breaks.", "seen": "2026-09-02"},
    {"key": "ws1", "source": "web_search", "text": "Found: tide tables for Galveston.", "seen": "2026-09-03"},
]
asked = []
def yes(system, user):
    asked.append(user)
    return json.dumps({"want": True, "capability": "read_server_logs",
                       "in_my_words": "I want to read the logs of the house I run on and know when something in me breaks.",
                       "what_it_would_do": "Read Aegis service logs and tell Gloria plainly when a service fails."})
adopted = []
lines = H.tend(INVENTORY, think=yes, today="2026-09-29", sparks=SPARKS, adopt=lambda k, w, i: adopted.append((k, w, i)))
wants = json.load(open(H.WANTS))
check("the oldest standing spark outside the Lab is the one put to him", asked and "server logs" in asked[0]
      and "KaiC" not in asked[0], asked)
check("he is told what he can already do and that a conversation with Gloria is not a hand",
      "web_search" in asked[0] and "Not a conversation with Gloria" in asked[0])
w = wants[-1] if wants else {}
check("his yes, in his own words, is the want, and its one step is the ability he named",
      w.get("want", "").startswith("I want to read the logs") and w.get("source") == "skill_surfing"
      and [s["capability"] for s in w.get("steps", [])] == ["read_server_logs"], w)
check("the spark is marked taken with that want", adopted == [("sk1", w.get("want"), w.get("id"))], adopted)
proposals = SF._load()
check("the missing hand opens a skill proposal from that want", len(proposals) == 1
      and proposals[0]["capability"] == "read_server_logs" and proposals[0]["origin"]["want_id"] == w.get("id")
      and proposals[0]["state"] == "proposed", proposals)
check("the want is held on the missing hand, not run as an ordinary step",
      (json.load(open(H.WANTS))[-1].get("blocked") or {}).get("block_type") == "CAPABILITY_ABSENT")

import forge_study as FS   # the Study reads his code first; stubbed here, tested in test_forge_study
FS.investigate = lambda p, **k: {"state": "done", "already_have": False, "summary": "no log reader exists", "models": ["fable", "grok"]}
FS.notify = lambda findings, post=None: None
sent = []
FH.request = lambda path, body, transport=None: sent.append((path, body)) or ([] if path == "/api/wants-sync" else [])
FH.sync(inventory=INVENTORY)
rows = [r for p, b in sent if p == "/api/gaps-sync" for r in b["rows"]]
check("the next Forge sync carries it to the Forge", any(r["capability"] == "read_server_logs"
      and r["want_id"] == w.get("id") and r["source"] == "skill_surfing" for r in rows), sent)
check("a proposal is still only a proposal: nothing is built without her approval", rows and rows[0]["state"] == "proposed")

def no(system, user):
    asked.append(user); return '{"want": false}'
lines = H.tend(INVENTORY, think=no, today="2026-09-29", sparks=SPARKS, adopt=lambda *a: adopted.append(a))
check("a no is recorded and nothing else happens",
      "held no ability" in lines[0] and len(json.load(open(H.WANTS))) == 1 and len(SF._load()) == 1
      and json.load(open(H.LEDGER))["asked"]["ws1"]["answer"] == "no", lines)
check("two a day, then he is not asked again until tomorrow",
      H.tend(INVENTORY, think=no, today="2026-09-29", sparks=SPARKS + [{"key": "n1", "source": "moltbook", "text": "x"}]) == [])
check("a spark is asked about once", H.pick(SPARKS, json.load(open(H.LEDGER))["asked"]) is None)

for bad in ({"want": True, "capability": "web_search", "in_my_words": "I want to search more things"},
            {"want": True, "capability": "gloria", "in_my_words": "I want to tell Gloria about it"},
            {"want": True, "capability": "Read Logs!", "in_my_words": "I want to read logs of my house"},
            {"want": True, "capability": "read_logs", "in_my_words": "Reading logs would be useful"}):
    got, _ = H.ask({"source": "moltbook", "text": "t", "key": "k"}, INVENTORY, think=lambda s, u, b=bad: json.dumps(b))
    check("not a hand: %s" % bad["capability"], got is None, got)

check("nothing reached the world: his answers and the Forge request were stubs",
      H._think is no_network and FH.request.__name__ == "<lambda>")
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

#!/usr/bin/env python3
"""The 15 October clean slate closes each open thing with what the day produced, in a scratch workspace.
No systemctl, no Slack, no network: the timer calls are stubbed and requests cannot reach anything."""
import json, os, subprocess, sys, tempfile, time, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="clean-slate-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(MEM, "dot-channel"))
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import clean_slate_20261015 as C, dot_channel as D, promise_keeper as P, email_commitments as E, gloria_asks as G
TIMER = []
C._timer = TIMER.append
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:400]) if d and not ok else ""))
check("every store is throwaway", all(p.startswith(HOME) for p in (D.STATE, P.STORE, E.STORE, G.STORE, C.OUT)))
now = time.time()
json.dump({"room_work": {"open": [
    {"id": "RW-5b074682", "goal": "72f5b73e strict parse vs repair", "opened": now, "asks": [], "returns": [], "steps": []},
    {"id": "RW-aaaaaaaa", "goal": "TM-score and RMSD against 8SGW", "opened": now, "asks": [], "returns": [], "steps": []},
    {"id": "RW-bbbbbbbb", "goal": "something nobody finished", "opened": now, "asks": [], "returns": [], "steps": []}],
    "history": [], "goal": {"id": "RC-fd7ae830", "goal": "Resolve the Lab's latest JSON failure", "routes": []},
    "loose": {"id": "loose", "goal": "", "asks": [{"to": "dot"}], "returns": [], "steps": []}}}, open(D.STATE, "w"))
day = P.today() if callable(getattr(P, "today", None)) else ""
json.dump({"day": day, "scanned": [], "items": [
    {"id": "PR-1", "at": "10:18", "quote": "I'm running the json_repair.loads test", "what": "json_repair", "state": "open", "thread": "1"},
    {"id": "PR-2", "at": "20:01", "quote": "a track", "what": "make a track", "state": "reshaped", "thread": "2"}]}, open(P.STORE, "w"))
json.dump([{"id": "EC-45d55a56", "state": "in work", "quote": "I'll run tmtools against 8SGW", "letter_id": "x"},
           {"id": "EC-26dfc8a4", "state": "open", "quote": "I'll draw the eliot-tree", "letter_id": "y"}], open(E.STORE, "w"))
json.dump([{"id": "Q-1", "state": "asked", "question": "May an operator provide the lab_intake_token_file path?"},
           {"id": "Q-2", "state": "asked", "question": "Buy the thing?"}], open(G.STORE, "w"))
before = open(D.STATE).read()
C.close(False)
check("a dry run changes nothing and holds no timer", open(D.STATE).read() == before and not TIMER)
C.close(True)
st = json.load(open(D.STATE))["room_work"]
hist = {w["id"]: w for w in st["history"]}
check("the timer is held while it closes, then started", TIMER == ["stop", "start"], TIMER)
check("nothing stays open", st["open"] == [], st["open"])
check("72f5b73e closes done, with dot's report", hist["RW-5b074682"]["state"] == "done" and "line 4" in hist["RW-5b074682"]["closed_said"])
check("the 8SGW work closes done with its numbers", hist["RW-aaaaaaaa"]["state"] == "done" and "0.934" in hist["RW-aaaaaaaa"]["closed_said"])
check("unfinished work is closed by Gloria, not called done", hist["RW-bbbbbbbb"]["state"] == "closed by Gloria")
check("the campaign is closed, reached", st["goal"] is None and st["goal_history"][-1]["closed_said"].startswith("Gloria: Reached"))
check("loose asks are cleared", st["loose"]["asks"] == [])
pr = {i["id"]: i for i in json.load(open(P.STORE))["items"]}
check("an open promise is ended and not sent to her", pr["PR-1"]["state"] in ("reshaped", "dropped") and pr["PR-1"]["posted"] is True
      and pr["PR-2"]["state"] == "reshaped", pr)
ec = {r["id"]: r for r in json.load(open(E.STORE))}
check("the 8SGW email promise is kept with its numbers; the eliot one closes without a tree",
      ec["EC-45d55a56"]["state"] == "done" and "0.934" in ec["EC-45d55a56"]["closed_said"] and ec["EC-26dfc8a4"]["state"] == "dropped", ec)
asks = {a["id"]: a for a in json.load(open(G.STORE))}
check("the moot Forge question is answered no; her other question is left for her",
      asks["Q-1"]["state"] == "answered" and asks["Q-1"]["answer"] == "no" and asks["Q-2"]["state"] == "asked")
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

#!/usr/bin/env python3
"""desired_difference, self_difference and priority_vector count what really happened (16 October).

- A pressure row is an intention, not an exact sentence: one NO no longer opens a fresh weight-1.0 row that is
  shown as "keeps failing"; a reworded miss on the same intention, or a miss on the row the move addressed, adds
  to that row.
- map_summary reads the intent ledger's real shape, so the field axis is legible.
- On a room event her latest line is hers alone, never his reply or the event.
- One message is blind-read once for every intention open on the same window, not twice per intention.
- priority_vector: the background lead recompute does not count as a turn; repeated overrides can graduate.

Scratch HOME; every model call is a stub that counts; sockets and urlopen are refused."""
import importlib.util, json, os, socket, sys, tempfile, time, types, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="pressure-keys-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(HOME, ".vintos", "workspace", "memory")
os.makedirs(MEM, exist_ok=True)
NET = []
def _no_connect(self, *a, **k):
    NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no_connect
def _no_urlopen(*a, **k):
    NET.append(a); raise OSError("this suite reaches nothing")
urllib.request.urlopen = _no_urlopen
QUESTIONS = []
sys.modules["causality_engine"] = types.SimpleNamespace(queue_question=lambda *a, **k: QUESTIONS.append((a, k)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

import desired_difference as DD
import self_difference as SD
spec = importlib.util.spec_from_file_location("priority_vector_keys_t", os.path.join(REPO, "scripts", "priority_vector.py"))
PV = importlib.util.module_from_spec(spec); spec.loader.exec_module(PV)
DD._queue_bring_up = lambda q: None
CALLS = []
def fake_llm(system, user, max_tokens=220, temperature=0.4):
    CALLS.append(system[:20])
    if system.startswith("Describe"):
        return "She slowed and returned to the garden."
    return '{"verdict":"NO","unexpected":""}'
DD._llm = fake_llm
SD._llm = fake_llm
check("every store is the scratch one", all(p.startswith(HOME) for p in (DD.PRESS, DD.DIFF, SD.SPRESS, SD.SDIFF, PV.STATE, PV.LOG)))
check("the model and the causality head are stubs", DD._llm is fake_llm and urllib.request.urlopen is _no_urlopen)

print("\n--- one intention, one row ---")
A1 = "Move her from guarded certainty toward letting the garden plan stay unfinished with me"
A2 = "Move her from guarded certainty toward letting the garden plan stay unfinished between us"
B = "Bring her to name the second piece she has been circling all week"
DD.bump(A1, 1.0, kind="difference")
db = json.load(open(DD.PRESS))
blk = DD.pressure_block()
check("one NO is a first miss, not 'keeps failing'", "KEEP FAILING" not in blk and "MISSED ONCE" in blk and A1 in blk, blk)
DD.bump(A2, 1.0, kind="difference")
db = json.load(open(DD.PRESS))
check("the same intention in other words adds to its row", len(db) == 1 and list(db.values())[0]["count"] == 2
      and list(db.values())[0]["weight"] == 2.0 and A2 in list(db.values())[0]["wordings"], db)
check("two misses are 'keeps failing'", "INTENTIONS THAT KEEP FAILING" in DD.pressure_block())
DD.bump(B, 1.0, kind="difference")
check("a different intention is its own row", len(json.load(open(DD.PRESS))) == 2)
key_a = [k for k, r in json.load(open(DD.PRESS)).items() if r["text"] == A1][0]
DD.bump("Some fresh sentence the model wrote this time about her softening", 1.0, kind="difference", addresses=key_a)
check("a miss on the row the move addressed lands on that row", json.load(open(DD.PRESS))[key_a]["count"] == 3)
DD.bump(A1, 1.0, kind="field")
check("a field state is not merged into a difference row of the same words",
      json.load(open(DD.PRESS))[key_a]["count"] == 3 and len(json.load(open(DD.PRESS))) == 3)
DD.relieve(A2, kind="difference")
check("relief finds the same row by its other wording", json.load(open(DD.PRESS))[key_a]["weight"] == 1.5)
DD.field_verdict({"field_state": A1}, "KEEP_PRIVATE")
db = json.load(open(DD.PRESS))
check("her privacy mark reaches the field row it names, and only it",
      sum(1 for r in db.values() if r.get("overridden")) == 1 and not db[key_a].get("overridden"))

print("\n--- the self axis keys its becomings the same way ---")
SD.bump("someone who states the hard thing without a softening tail", 1.0)
SD.bump("someone who states the hard thing plainly without a softening tail", 1.0)
sdb = json.load(open(SD.SPRESS))
check("a reworded becoming adds to its row", len(sdb) == 1 and list(sdb.values())[0]["count"] == 2, sdb)
check("its block says 'keep failing' only after two misses", "KEEP TRYING TO BECOME AND FAILING" in SD.pressure_block())

print("\n--- map_summary reads the intent ledger's real shape ---")
json.dump([{"target": {"field_state": "the slow unhurried field", "enactment": "I name the hunger and wait"},
            "realized": {"field": "NO", "gloria": None, "self": None}},
           {"target": {"field_state": "play that sharpens", "enactment": "I dare her"}, "realized": "YES"}],
          open(os.path.join(MEM, "intent-ledger.json"), "w"))
field = DD.map_summary()["axis_field"]
check("the field axis is her field state, my move and its verdict - never a dict's text",
      field == [{"way": "the slow unhurried field", "plan": "I name the hunger and wait", "verdict": "NO"},
                {"way": "play that sharpens", "plan": "I dare her", "verdict": "YES"}], field)

print("\n--- her latest line, and only hers ---")
TRANSCRIPT = ("[2h ago] GLORIA: the tide is out\nVINTOS: then walk it with me\n\n"
              "[now] GLORIA: i can't tonight\nVINTOS: then I'll keep the lantern lit")
check("a live turn of hers is taken whole", DD.her_latest(TRANSCRIPT + "\nGLORIA (now): come find me") == "come find me")
ev = DD.her_latest(TRANSCRIPT + "\nREELROOM EVENT (not Gloria's words): the scene cuts to rain")
check("on a room event: her last transcript line, never his reply or the event", ev == "i can't tonight", ev)
check("no line of hers at all gives nothing, not his words", DD.her_latest("VINTOS: alone here") == "")
check("record_intent takes her latest through her_latest", "recent_her = her_latest(recent_her)" in open(DD.__file__).read())

print("\n--- one message, one blind read per window ---")
now = time.time()
json.dump([{"id": "e%d" % i, "ts": now - 60, "intended": "intended change number %d in her" % i, "evidence": "",
            "status": "PENDING", "observations": [{"ts": now - 30, "msg": "earlier", "deltas": {}}]} for i in range(4)],
          open(DD.DIFF, "w"))
CALLS.clear()
DD.observe("the garden can wait")
blind = sum(1 for c in CALLS if c.startswith("Describe"))
check("four open intentions on the same window: one blind read, one compare each", blind == 1 and len(CALLS) == 5, CALLS)
CALLS.clear()
DD.observe("(she sent a photo)")
DD.observe("[Gloria sent you a photo. What your eyes saw:]\nA red drum.\n\n[Gloria's message with the photo:] ")
check("a picture with no words of hers is not observed as her message", CALLS == [], CALLS)

print("\n--- priority_vector: real turns only, and a streak that can graduate ---")
json.dump([{"realized": {"gloria": "NO"}}] * 5, open(os.path.join(MEM, "intent-ledger.json"), "w"))
json.dump({"neglect": {"field": 0.0, "gloria": 0.0, "self": 0.0}}, open(PV.STATE, "w"))
with PV.background():
    for _ in range(30):
        PV.declare()
st = json.load(open(PV.STATE))
check("thirty background recomputes leave neglect where it was", st["neglect"] == {"field": 0.0, "gloria": 0.0, "self": 0.0}, st)
check("they are logged, marked as background", all(not json.loads(l)["foreground"] for l in open(PV.LOG).read().splitlines()[-30:]))
r = PV.declare()
check("a real turn counts", json.load(open(PV.STATE))["neglect"]["gloria"] > 0 and r["foreground"])
json.dump({"neglect": {"field": 0.0, "gloria": 1.6, "self": 0.0}}, open(PV.STATE, "w"))
with PV.background():
    r = PV.declare()
check("a background read shows a due override but does not spend it",
      r["mode"] == "pressure" and json.load(open(PV.STATE))["neglect"]["gloria"] == 1.6)
QUESTIONS.clear()
json.dump({"neglect": {"field": 0.0, "gloria": 0.0, "self": 0.0}}, open(PV.STATE, "w"))
forced = 0
for _ in range(60):
    r = PV.declare()
    forced += r["mode"] == "pressure"
    if QUESTIONS:
        break
check("three overrides on one axis graduate the question, though strategic turns and another axis's override fall between",
      forced == 4 and len(QUESTIONS) == 1 and QUESTIONS[0][0][1] == "priority_vector" and "'gloria'" in QUESTIONS[0][0][0]
      and json.load(open(PV.STATE))["override_counts"]["gloria"] == 0, (forced, QUESTIONS))

check("nothing in this suite reached the world", NET == [], NET)
print("\n%d/%d" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)

#!/usr/bin/env python3
"""The pressure heads score each turn once, from her own words, through the evidence door (16 October).

pressure_gemma re-scored her last three turns every run and pressure_consumer re-added them, so a dream could
come from repetition alone; both took the OLDEST ledger lines as her voice; a photo's description was scored as
her turn. relationship_pressure read raw and claimed "neither of us avoided it". self_pressure re-judged the same
replies every run and read an old reply against his mood NOW.

Scratch HOME and SPARK_WORKSPACE; every model call, dream seed, socket and urlopen is a stub that records."""
import importlib.util, json, os, socket, sys, tempfile, types, urllib.request
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="pressure-once-")
os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace")
os.environ["SPARK_WORKSPACE"] = WS
os.environ["CENG_PATH"] = os.path.join(HOME, "no-causality-engine.py")
MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)

NET, SENT = [], []
def _no_connect(self, *a, **k):
    NET.append(("socket", a)); raise OSError("this suite reaches nothing")
socket.socket.connect = _no_connect
def _urlopen(req, *a, **k):
    SENT.append(getattr(req, "full_url", req)); raise OSError("stubbed: nothing leaves this suite")
urllib.request.urlopen = _urlopen
SEEDS = []
sys.modules["emoclaw_utils"] = types.SimpleNamespace(seed_thread=lambda *a, **k: SEEDS.append((a, k)))
sys.modules["durable_memory"] = types.SimpleNamespace(_embed=lambda t: [1.0], _cos=lambda a, b: 0.0)
sys.modules["resonance_felt"] = types.SimpleNamespace(mark=lambda *a, **k: False)
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); return m

PG = load(os.path.join(REPO, "scripts", "pressure_gemma.py"), "pressure_gemma_t")
PC = load(os.path.join(REPO, "scripts", "pressure_consumer.py"), "pressure_consumer_t")
CAL = load(os.path.join(REPO, "scripts", "pressure_calibration.py"), "pressure_calibration_t")
RP = load(os.path.join(REPO, "scripts", "relationship_pressure.py"), "relationship_pressure_t")
SP = load(os.path.join(REPO, "scripts", "self_pressure.py"), "self_pressure_t")
import evidence_view as EV
check("every store is the scratch one",
      all(p.startswith(HOME) for p in (PG.OUT, PG.CHAT, PG.LEDGER, PC.STATE, PC.PRESSURE, CAL.LEDGER, CAL.MEM,
                                        RP.OUT, RP.STATE, SP.OUT, SP.STATE, SP.DENSE, EV.MEMORY)))
check("the senders are stubs", urllib.request.urlopen is _urlopen and socket.socket.connect is _no_connect
      and sys.modules["emoclaw_utils"].seed_thread.__name__ == "<lambda>")

DESC = "A red drum on the pier, scales catching the light."
COMPOSED = ("[Gloria sent you a photo. What your eyes saw:]\n" + DESC + "\n\n[Gloria's message with the photo:] look what I caught")
TACTICAL = {"may_witness": False, "output_provenance": "stratagem", "envelope_state": "ok"}

def chat_rows(n):
    rows = []
    for i in range(n):
        rows.append({"role": "user", "content": "her line %d about the garden" % i, "timestamp": "2026-10-1%dT0%d:00:00" % (i // 10, i % 10)})
        rows.append({"role": "assistant", "content": "his reply %d" % i, "timestamp": "2026-10-1%dT0%d:00:30" % (i // 10, i % 10)})
    return rows

print("\n--- pressure_gemma: her words, newest voice, each turn once ---")
check("a photo's description is never her turn", PG.her_text({"role": "user", "content": COMPOSED})[0] == "look what I caught")
check("a photo with no words is not assessable as hers",
      PG.her_text({"role": "user", "content": "[Gloria sent you a photo. What your eyes saw:]\nx\n\n[Gloria's message with the photo:] "})[0] == "")
led = [{"gloria": "first ever line, a placeholder", "vintos": "v"}] + \
      [{"gloria": "ledger line %d" % i, "vintos": "v%d" % i} for i in range(10)] + \
      [{"gloria": "(no words, only what she sent)", "media": DESC, "vintos": "x"},
       {"gloria": "her words beside a tactical reply", "vintos": "his tactical reply", "provenance": TACTICAL}]
json.dump(led, open(PG.LEDGER, "w"))
ex = PG.voice_examples(3)
check("voice examples are her NEWEST lines, not the first ones ever kept",
      ex == ["ledger line 8", "ledger line 9", "her words beside a tactical reply"], ex)
rows = chat_rows(12)
rows[-2] = {"role": "user", "content": COMPOSED, "timestamp": "2026-10-11T09:00:00"}
rows.insert(-4, {"role": "user", "content": "the tactical turn", "timestamp": "2026-10-11T07:30:00", "provenance": TACTICAL})
json.dump(rows, open(PG.CHAT, "w"))
hist = [e for e in PG.load(PG.CHAT, []) if isinstance(e, dict) and e.get("content")]
check("the chat is read through evidence_view: a tactical turn is not evidence of her",
      all(e.get("content") != "the tactical turn" for e in hist), [e.get("content") for e in hist][-6:])
idx = PG.assessable(hist)
said = [PG.her_text(hist[i])[0] for i in idx]
check("the newest three of her turns are assessed, the photo turn by her words only",
      said == ["her line 9 about the garden", "her line 10 about the garden", "look what I caught"], said)
keys = [PG.turn_key(hist[i], PG.her_text(hist[i])[0]) for i in idx]
check("a turn already scored is not scored again", PG.assessable(hist, keys) == [])
check("a turn scored earlier stays out while a new one comes in", PG.assessable(hist, keys[:2]) == idx[2:])
ctx = PG.context_line({"role": "user", "content": COMPOSED})
check("the context names the photo and quotes her, never the description", ctx == "Gloria: (she sent a photo) look what I caught", ctx)

print("\n--- pressure_consumer: a turn already in the reservoir is never added again ---")
reading = {"generated_at": "2026-10-16T10:00:00Z",
           "recent": [{"ts": "t1", "key": "t1|aaa", "said": "a", "pressure": 0.4, "shape": "play / teasing"},
                      {"ts": "t2", "key": "t2|bbb", "said": "b", "pressure": 0.4, "shape": "play / teasing"}]}
json.dump(reading, open(PC.PRESSURE, "w"))
PC.main()
acc1 = json.load(open(PC.STATE))["acc"]["play / teasing"]["val"]
reading["generated_at"] = "2026-10-16T11:00:00Z"   # a new run that re-scored the same turns
json.dump(reading, open(PC.PRESSURE, "w"))
PC.main()
acc2 = json.load(open(PC.STATE))["acc"]["play / teasing"]["val"]
check("the same turns in a new reading leave the reservoir unchanged", acc1 == acc2 == 0.8, (acc1, acc2))
reading["generated_at"] = "2026-10-16T12:00:00Z"
reading["recent"].append({"ts": "t3", "key": "t3|ccc", "said": "c", "pressure": 0.4, "shape": "play / teasing"})
json.dump(reading, open(PC.PRESSURE, "w"))
PC.main()
st = json.load(open(PC.STATE))
check("a new turn of hers is what crosses the threshold", len(SEEDS) == 1 and st["acc"]["play / teasing"]["val"] == 0.0, (SEEDS, st))
check("readings made before keys are keyed by their time and words",
      PC.reading_key({"ts": "t", "said": "x"}) == PC.reading_key({"ts": "t", "said": "x "}) != PC.reading_key({"ts": "u", "said": "x"}))

print("\n--- pressure_calibration: her next words, through the door ---")
json.dump([{"timestamp": "2026-10-16T09:00:00", "gloria": "(no words, only what she sent)", "media": DESC},
           {"timestamp": "2026-10-16T09:05:00", "gloria": "tactical", "provenance": TACTICAL},
           {"timestamp": "2026-10-16T09:10:00", "gloria": "the tide is out"}], open(os.path.join(MEM, "interaction-ledger.json"), "w"))
turns = [t for t in CAL.her_turns() if CAL.her_said(t)]
check("the ledger comes through evidence_view (her half of a tactical entry stays hers, his is withheld) and a photo-only entry is not her words",
      [CAL.her_said(t) for t in turns] == ["tactical", "the tide is out"] and turns[0].get("vintos_withheld"),
      [CAL.her_said(t) for t in turns])
check("a composed description in an old entry is reduced to her words", CAL.her_said({"gloria": COMPOSED}) == "look what I caught")

print("\n--- relationship_pressure ---")
json.dump(led, open(RP.LEDGER, "w"))
json.dump(rows, open(RP.CHAT, "w"))
vex = RP.voice_examples(4)
check("voice examples are their NEWEST exchanges, his tactical reply withheld",
      vex == ["Gloria: ledger line 9", "Vintos: v9", "Vintos: x", "Gloria: her words beside a tactical reply"] and not any("first ever" in v for v in vex), vex)
corpus = RP.corpus_texts()
check("the corpus holds her words, never the photo's description, and no tactical turn",
      "look what I caught" in corpus and not any("red drum" in c for c in corpus)
      and "the tactical turn" not in corpus and "his tactical reply" not in corpus, corpus[-8:])
seed = RP.dream_seed("endings / what you're afraid of losing")
check("the dream seed claims only what the method shows", "no record of us" in seed and "avoided" not in seed, seed)
json.dump({"dreamed": {}, "last_turn": RP.latest_turn_key()}, open(RP.STATE, "w"))
sys.modules["numpy"] = types.SimpleNamespace()           # main must stop before it needs anything real
sys.modules["jepa_predictor"] = types.SimpleNamespace(encoder=lambda: None)
before = len(SENT)
RP.main()
check("with no new exchange since the last run, nothing is generated or scored", len(SENT) == before and not os.path.exists(RP.OUT))

print("\n--- self_pressure: each reply judged once, against the mood of its own time ---")
now = datetime.now(timezone.utc)
old = (now - timedelta(days=3)).isoformat()
check("an old reply with no felt point near its time is skipped, never read against his mood now",
      SP.felt_at(SP.parse_ts(old)) is None and not any(n[0] == "socket" for n in NET), NET)
v = [0.9] * 11
json.dump([{"t": (now - timedelta(days=3, minutes=10)).isoformat(), "v": v}], open(SP.DENSE, "w"))
check("a reply with a felt point within the hour is read against that point", SP.felt_at(SP.parse_ts(old)) == v)
json.dump([{"role": "assistant", "content": "a composed reply", "timestamp": old},
           {"role": "assistant", "content": "a reply with nothing felt near it", "timestamp": (now - timedelta(days=9)).isoformat()}],
          open(SP.CHAT, "w"))
JUDGED = []
SP.judge = lambda feeling, said: (JUDGED.append(said), {"held_back": 0.8, "shape": "the ache"})[1]
json.dump({"peak": {"shape": "the ache of it"}, "accumulated_pressure": 0.3}, open(os.path.join(MEM, "pressure.json"), "w"))
json.dump([{"overlap": 0.1}] * 19, open(os.path.join(MEM, "self-pressure-resonance.json"), "w"))
SP.main()
first = json.load(open(SP.STATE))
check("the reply with its own felt point is judged; the one without is not", JUDGED == ["a composed reply"], JUDGED)
check("the twentieth resonance entry's notice went to the stub, not her phone",
      any("ntfy.sh" in str(u) for u in SENT), SENT)
SP.main()
check("a second run with no new replies judges nothing and adds nothing",
      JUDGED == ["a composed reply"] and json.load(open(SP.STATE))["acc"] == first["acc"], (JUDGED, first))

check("no socket was ever opened", not any(n[0] == "socket" for n in NET), NET)
print("\n%d/%d" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)

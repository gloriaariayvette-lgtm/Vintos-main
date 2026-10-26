#!/usr/bin/env python3
"""Proto pearls with their actual occasions (Codex's proposal 13): one forming self-description read beside the
recorded occasions its support came from, the phrasings in order, and an occasion he names as a tension with it.

Scratch HOME and scratch workspace: every store this suite touches is under a temporary directory and is asserted to
be. Every event, proto and phrasing is an invented fixture. No model is asked: sockets, `requests` and urllib raise.
"""
import hashlib, json, os, re, socket, sys, tempfile, types, urllib.request
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="vintos-proto-notebook-")
os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace")
os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory")
os.makedirs(os.path.join(MEM, "journal"), exist_ok=True)


def _no_network(*a, **k):
    raise AssertionError("a test must never reach the network")


def _no_socket(self, *a, **k):
    raise AssertionError("a test must never open a socket")


socket.socket.connect = _no_socket
urllib.request.urlopen = _no_network
sys.modules["requests"] = types.SimpleNamespace(get=_no_network, post=_no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import proto_notebook as N
import enactment_distiller as ED

R = []


def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:600]) if detail and not ok else ""))


def src(rel):
    with open(os.path.join(REPO, rel)) as f:
        return f.read()


def write(name, obj):
    with open(os.path.join(MEM, name), "w") as f:
        json.dump(obj, f, indent=2)


def digest(name):
    with open(os.path.join(MEM, name), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


TODAY = date.today().isoformat()
LATER = (date.today() + timedelta(days=2)).isoformat()
EARLIER = (date.today() - timedelta(days=3)).isoformat()

# ---------------------------------------------------------------- isolation
check("the notebook's store and the distiller's stores are all in the scratch workspace",
      all(p.startswith(HOME) for p in (N.store_path(), ED.EVENTS_FILE, ED.PROTO_PEARL_FILE)),
      (N.store_path(), ED.EVENTS_FILE))
check("nothing in this suite can send or fetch",
      sys.modules["requests"].post is _no_network and urllib.request.urlopen is _no_network)
check("the notebook asks no model and opens no network",
      not re.search(r"^\s*(import|from)\s+(requests|urllib|socket|http)", src("scripts/proto_notebook.py"), re.M))
check("an empty memory offers nothing and writes nothing",
      N.block() == "" and N.offer() == "" and not os.path.exists(N.store_path()))

# ---------------------------------------------------------------- fixtures (invented)
def ev(eid, ts, category, event, phrasing, shift="before X, now Y"):
    return {"id": eid, "timestamp": ts, "date": ts[:10], "category": category, "event": event,
            "observed_shift": shift, "identity_candidate": phrasing, "evidence": ["fixture"], "confidence": 0.7,
            "exceeded_self_model": False, "source": "chat"}


EVENTS = [
    ev("ed_20261020_090000", "2026-10-20T09:00:00.100000", "successful_directness", "fixture event one",
       "I can say the plain thing"),
    ev("ed_20261021_100000", "2026-10-21T10:00:00.100000", "successful_directness", "fixture event two",
       "I can say the plain thing first"),
    ev("ed_20261022_110000", "2026-10-22T11:00:00.100000", "successful_directness", "fixture event three",
       "I can say the plain thing first"),
    ev("ed_20261022_120000", "2026-10-22T12:00:00.100000", "unexpected_warmth", "fixture other occasion",
       "I can be warm"),
    ev("ed_20261023_130000", "2026-10-23T13:00:00.100000", "successful_grounding", "fixture lone occasion",
       "I can settle"),
]
PROTOS = [
    {"id": "proto_successful_directness_fixture", "category": "successful_directness",
     "identity_candidate": "I can say the plain thing first", "support_count": 4,
     "support_events": [
         {"event": "fixture event one", "timestamp": "2026-10-20T09:00:00.101000"},          # older: no id, same pass
         {"event": "fixture event two", "timestamp": "2026-10-21T10:00:00.102000", "event_id": "ed_20261021_100000"},
         {"event": "fixture event three", "timestamp": "2026-10-22T11:00:00.103000", "event_id": "ed_20261022_110000"},
         {"event": "different wording", "timestamp": "2026-10-22T12:30:00"},                  # not on record
     ],
     "created": TODAY + "T08:00:00", "decays_at": LATER, "suggest_pearl": False},
    {"id": "proto_successful_grounding_fixture", "category": "successful_grounding",
     "identity_candidate": "I can settle", "support_count": 1,
     "support_events": [{"event": "fixture lone occasion", "timestamp": "2026-10-23T13:00:00.101000",
                         "event_id": "ed_20261023_130000"}],
     "created": TODAY + "T08:00:00", "decays_at": LATER, "suggest_pearl": False},
    {"id": "proto_unexpected_warmth_old", "category": "unexpected_warmth", "identity_candidate": "I can be warm",
     "support_count": 6, "support_events": [
         {"event": "fixture other occasion", "timestamp": "2026-10-22T12:00:00.1", "event_id": "ed_20261022_120000"},
         {"event": "fixture event one", "timestamp": "2026-10-20T09:00:00.1", "event_id": "ed_20261020_090000"}],
     "created": EARLIER + "T08:00:00", "decays_at": EARLIER, "suggest_pearl": True},
]
write("earned-identity-events.json", {"events": EVENTS})
write("proto-pearls.json", {"protos": PROTOS})
before = (digest("earned-identity-events.json"), digest("proto-pearls.json"))

# ---------------------------------------------------------------- following occasions
nb = N.notebook("proto_successful_directness_fixture")
ids = [o["event_id"] for o in nb["occasions"]]
check("support with an event id is followed to that recorded occasion",
      "ed_20261021_100000" in ids and "ed_20261022_110000" in ids, ids)
check("older support without an id is matched to the event written in the same pass",
      ids[0] == "ed_20261020_090000" and nb["occasions"][0]["linked_by"] == "same pass", nb["occasions"][0])
check("support whose wording matches no recorded event is counted as not on record, never guessed",
      nb["not_on_record"] == 1 and len(ids) == 3, nb)
check("same-pass matching needs the same category: another category's event at that minute is not taken",
      N.occasion_for({"event": "fixture event one", "timestamp": "2026-10-20T09:00:00.1"},
                     {"category": "unexpected_warmth"}) is None)
check("a near time with other wording is not a match",
      N.occasion_for({"event": "fixture event", "timestamp": "2026-10-20T09:00:00.1"},
                     {"category": "successful_directness"}) is None)
check("the phrasings are kept in order, each change once, instead of only the latest",
      [p["text"] for p in nb["phrasings"]] == ["I can say the plain thing", "I can say the plain thing first"],
      nb["phrasings"])

# ---------------------------------------------------------------- the one proto offered
cand = N.candidate()
check("the proto offered is still forming and has at least two occasions on record",
      cand and cand["proto_id"] == "proto_successful_directness_fixture", cand and cand["proto_id"])
check("a decayed proto is not offered, however much support it had",
      all(N.candidate(TODAY)["proto_id"] != "proto_unexpected_warmth_old" for _ in [0]))
text = N.block()
check("the block names the description, the first and the latest occasion with their ids",
      "I can say the plain thing first" in text and "[ed_20261020_090000]" in text and "[ed_20261022_110000]" in text
      and "[ed_20261021_100000]" not in text, text)
check("the block shows how the phrasing changed", "How it was phrased" in text and "->" in text, text)
check("the block offers other recorded occasions he could name, from other categories, and asserts none of them",
      "Other recent occasions on record" in text and "[ed_20261023_130000]" in text
      and "tension" not in text.split("Other recent occasions")[1].split("\n", 2)[1].lower(), text)
check("the block says it is not a verdict and changes nothing about formation",
      "not a verdict" in text and "changes nothing about how it" in text, text)
check("naming a tension is offered, not asked", "you may name it" in text and "Or leave it." in text, text)
check("the block stays small (well under the shared token ceiling)", len(text) < 1600, len(text))

offered = N.offer()
rows = N.rows()
check("offering writes one row of ids only: proto, occasions, room",
      offered == text and len(rows) == 1 and rows[0]["kind"] == "offered"
      and rows[0]["proto_id"] == "proto_successful_directness_fixture"
      and set(rows[0]) == {"kind", "at", "proto_id", "event_ids", "room"}, rows)

# ---------------------------------------------------------------- his marks
reply = ("Some reflection that ends.\n"
         "[TENSION: ed_20261022_120000 - warmth there came before any plain word]\n"
         "[TENSION: ed_29990101_000000 - an occasion that is not on record]")
rec, ref = N.record_marks(reply)
check("a named occasion on record is recorded against the proto just offered",
      rec == [("ed_20261022_120000", "proto_successful_directness_fixture")], rec)
check("an occasion that is not on record is not recorded (no invented counterexample)",
      ref == [("ed_29990101_000000", "not an occasion on record")], ref)
m = N.marks("proto_successful_directness_fixture")
check("the mark keeps his words, says it is his, and nothing else",
      len(m) == 1 and m[0]["note"] == "warmth there came before any plain word" and m[0]["by"] == "him", m)
rec2, ref2 = N.record_marks(reply)
check("the same occasion named twice is kept once", rec2 == [] and ("ed_20261022_120000", "already named") in ref2, ref2)
rec3, _ = N.record_marks("[TENSION: proto_successful_directness_fixture ed_20261021_100000: one of its own occasions]")
check("one of its own supporting occasions can be named as an exception, with the proto named explicitly",
      rec3 == [("ed_20261021_100000", "proto_successful_directness_fixture")], rec3)
check("a mark with no proto offered recently and none named is not recorded",
      N.record_marks("[TENSION: ed_20261023_130000 - x]", now=datetime.now() + timedelta(hours=N.OFFER_HOURS + 1))
      == ([], [("ed_20261023_130000", "no forming description was offered or named")]))
check("text with no tension line records nothing", N.record_marks("nothing here [ADOPT: cp-abcdef]") == ([], []))
check("a tension line's event id carries no period (it cannot split a sentence where later steps read his text)",
      "." not in "ed_20261022_120000" and re.fullmatch(N.EVENT_ID, "ed_20261022_120000"))

after_text = N.block()
check("after he names one, the notebook shows his tension in his words, and stops listing other occasions",
      "You named an occasion as a tension" in after_text and "warmth there came before any plain word" in after_text
      and "Other recent occasions" not in after_text, after_text)
check("reading, offering and marking changed neither the proto store nor the event store",
      (digest("earned-identity-events.json"), digest("proto-pearls.json")) == before)
p = json.load(open(os.path.join(MEM, "proto-pearls.json")))["protos"][0]
check("a tension is no negative weight: the support count, decay and suggestion are as they were",
      p["support_count"] == 4 and p["decays_at"] == LATER and p["suggest_pearl"] is False)
check("no pearl candidate or pearl is written",
      not os.path.exists(os.path.join(MEM, "candidate-pearls.json")) and not os.path.exists(os.path.join(MEM, "pearls")))

# ---------------------------------------------------------------- the distiller keeps the event id
db = {"protos": []}
ED.update_proto_pearl({"category": "successful_repair", "event": "fixture repair", "identity_candidate": "I can mend"},
                      db, event_id="ed_20261026_080000")
ED.update_proto_pearl({"category": "successful_repair", "event": "fixture repair two", "identity_candidate": "I can mend"},
                      db, event_id="ed_20261026_090000")
ED.update_proto_pearl({"category": "successful_repair", "event": "fixture repair three", "identity_candidate": "I can mend"},
                      db)
pp = db["protos"][0]
check("new support carries the earned event's id; support with none given has no id field",
      [s.get("event_id") for s in pp["support_events"]] == ["ed_20261026_080000", "ed_20261026_090000", None]
      and "event_id" not in pp["support_events"][2], pp["support_events"])
check("the counts, thresholds and latest-phrasing rule are untouched",
      pp["support_count"] == 3 and pp["suggest_pearl"] is False and ED.PROTO_THRESHOLD == 3
      and ED.PEARL_THRESHOLD == 5 and ED.PROTO_DECAY_DAYS == 2)

write("proto-pearls.json", {"protos": []})
write("earned-identity-events.json", {"events": []})
ED.scan = lambda *a, **k: [{"detected": True, "category": "successful_repair", "event": "fixture enacted",
                            "observed_shift": "x", "identity_candidate": "I can mend", "evidence": [],
                            "exceeded_self_model": False, "confidence": 0.3}]
ED.process("a fixture response long enough to scan, invented for this suite", "", "chat")
evs = json.load(open(ED.EVENTS_FILE))["events"]
pr = json.load(open(ED.PROTO_PEARL_FILE))["protos"]
check("process() links the proto's support to the earned event it just wrote",
      len(evs) == 1 and pr and pr[0]["support_events"][0].get("event_id") == evs[0]["id"], (evs, pr))
check("and the notebook follows that id back to the occasion",
      N.notebook(pr[0]["id"])["occasions"][0]["event_id"] == evs[0]["id"])

# ---------------------------------------------------------------- where it is offered, and where it is not
intro = src("bin/introspection.sh")
check("introspection offers the notebook and records his named tensions after the final text",
      "from proto_notebook import offer" in intro and "from proto_notebook import record_marks" in intro
      and intro.index("proto_notebook import offer") < intro.index("FULL_PROMPT=")
      and intro.index("record_marks") > intro.index("run_verification_pass(entry"), "")
check("introspection still seeds its thread exactly as before",
      "seed_thread(sentences[-2] if len(sentences) > 1 else sentences[0], direction='refine')" in intro)
for rel in ("bin/introspection.sh", "bin/enactment_distiller.py"):
    twin = rel.replace("bin/", "scripts/", 1)
    check("%s and its scripts twin are identical" % os.path.basename(rel), src(rel) == src(twin))
for rel in ("scripts/mirror.sh", "skills/dreaming/scripts/dream-trigger.sh", "scripts/emoclaw_utils.py",
            "bin/emoclaw_utils.py", "scripts/latent_threads.py", "scripts/inner_context.py", "bin/server.py",
            "bin/pearl_engine.py"):
    if os.path.exists(os.path.join(REPO, rel)):
        check("%s does not read the notebook" % rel, "proto_notebook" not in src(rel))
check("the deploy installs the notebook", "proto_notebook.py" in src("scripts/deploy-atelier.sh"))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

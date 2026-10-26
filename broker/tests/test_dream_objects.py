#!/usr/bin/env python3
"""A dream can leave an object behind (proposal 07): last night's diffuser dream is offered, dated and attributed, as
material in an Atelier visit; he may make something from it or leave it; a work made from it keeps its link back to
the dream, always as a dream, never as something that happened and never as evidence. The dream is never seeded back
into the thread pool.

Scratch HOME and workspace; the model, the broker and ntfy are stubs that record what they were sent; every socket is
refused."""
import importlib.util, json, os, socket, sys, tempfile, time, types
from datetime import datetime, timezone, timedelta
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="dream-objects-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
os.environ["SPARK_WORKSPACE"] = WS
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
try: import requests  # noqa: F401
except ImportError: sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import dream_objects as DO
spec = importlib.util.spec_from_file_location("atelier_visit_dream", os.path.join(REPO, "scripts", "atelier-visit.py"))
AV = importlib.util.module_from_spec(spec); spec.loader.exec_module(AV)
AV.WSP = WS; AV.CHOICES = os.path.join(MEM, "atelier-choices.jsonl"); AV.KNOCK_STORE = os.path.join(MEM, ".atelier-knock.json")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("the dream and its objects are read and written in the scratch workspace",
      DO.DREAM.startswith(HOME) and DO.STORE.startswith(HOME) and AV.WSP.startswith(HOME), (DO.DREAM, DO.STORE))

DREAM_WORDS = "The open door and the closed one were the same door, seen from either side of a night."
NOW = time.time()
def dream_file(hours_ago=3.0, words=DREAM_WORDS, fragments=12):
    at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    with open(DO.DREAM, "w") as f:
        json.dump({"generated_at": at.isoformat(), "fragments": fragments, "coherence": 0.88,
                   "anchors": ["a", "b", "c"], "resolution": words}, f)
def reset():
    for p in (DO.STORE, DO.DREAM, os.path.join(MEM, "atelier-reveals.json")):
        if os.path.exists(p): os.remove(p)

# ---- nothing to offer: nothing is offered, nothing recorded
reset()
check("no dream on file: nothing offered, nothing recorded", DO.block() == ("", None) and not os.path.exists(DO.STORE))
dream_file(hours_ago=60)
check("a dream older than two days is not offered", DO.block() == ("", None) and not os.path.exists(DO.STORE))
dream_file(hours_ago=-5)
check("a dream dated in the future is not offered", DO.block() == ("", None))
dream_file(words="   ")
check("a dream with no words is not offered", DO.block() == ("", None))
with open(DO.DREAM, "w") as f: f.write("{")
check("an unreadable dream file is not offered and does not raise", DO.block() == ("", None))

# ---- a fresh dream: dated, attributed, a dream on its face
reset(); dream_file()
text, dream = DO.block(NOW)
check("last night's dream is offered once, with its date and where it came from",
      dream and dream["night_of"] in text and "night-time diffuser" in text and "12 of the day's unresolved fragments" in text, text)
check("it is named a dream: not something that happened, not a finding, nothing about the world or her",
      all(t in text for t in ("It is a dream: not something that happened", "not a finding", "about the world, about her")))
check("the dream's own words are there, and the 'resolution' language is not", DREAM_WORDS in text and "resolution" not in text.lower())
check("he may make something or leave it, and is told how to keep the link",
      "or leave it; leaving it costs nothing" in text and "<from_dream>%s</from_dream>" % dream["id"] in text)
check("the offer is small (under 1,200 characters)", len(text) < 1200, len(text))
check("the dream record witnesses nothing", dream["provenance"]["may_witness"] is False and dream["is_dream"] is True)
check("a second visit the same day is not offered it again", DO.block(NOW + 60) == ("", None))
t2, d2 = DO.block(NOW + 86400)
check("the next day it may be offered once more", d2 and d2["id"] == dream["id"])
check("and never a third time", DO.block(NOW + 2 * 86400) == ("", None))
st = json.load(open(DO.STORE))
check("leaving it records only that it was offered", st["dreams"][dream["id"]]["offers"] == 2
      and st["dreams"][dream["id"]]["state"] == "offered" and st["objects"] == [], st)

# ---- a work made from it
reset(); dream_file()
text, dream = DO.block(NOW)
check("nothing made: no object is kept", DO.link(dream, [], "p1") is None and json.load(open(DO.STORE))["objects"] == [])
rec = DO.link(dream, [{"kind": "write", "artifact": "piece_write.md"}], "p1", now=NOW)
check("a work made from it keeps its link back to the dream, by ids only",
      rec and rec["dream"] == dream["id"] and rec["made"] == [{"kind": "write", "artifact": "piece_write.md"}]
      and rec["project"] == "p1" and DREAM_WORDS not in json.dumps(rec), rec)
check("the work inherits the dream's standing through evidence_view: it is not evidence",
      rec["evidence_standing"] == "ineligible" and rec["generation_provenance"]["may_witness"] is False
      and rec["derived_from"] == [{"turn_id": dream["id"], "timestamp": dream["timestamp"]}], rec)
check("it claims nothing happened", "not evidence that anything happened" in rec["claim"] and rec["is_dream_derived"])
check("a dream he made something from is not offered again", DO.block(NOW + 86400) == ("", None))
links = DO.links_for(["piece_write.md", "other.md"])
check("the manifest line names it a dream, not something that happened",
      list(links) == ["piece_write.md"] and "a dream you had, not something that happened" in links["piece_write.md"], links)
mark = DO.reveal_mark("piece_write.md")
check("a reveal carries the marker, the dream's id and night, never its words",
      mark and mark["is_dream_derived"] and "not something that happened" in mark["marker"]
      and DREAM_WORDS not in json.dumps(mark) and DO.reveal_mark("other.md") is None, mark)

# ---- never reseeded
src = open(os.path.join(REPO, "scripts", "dream_objects.py")).read()
written = sorted(os.listdir(MEM))
check("nothing but its own store is written (no thread, want or seed store)",
      written == ["diffuser-resolution.json", "dream-objects.json"], written)
check("the module never opens the thread pool (named only in its docstring)", "\"unfinished-threads" not in src and "current-wants" not in src)
for f in ("latent_diffuser.py", "subcon_thread_seeds.py"):
    check("%s does not read the dream objects back" % f, "dream-objects" not in open(os.path.join(REPO, "scripts", f)).read())
check("the diffuser still refuses to reseed its dream", "A dream must not eat its own output" in
      open(os.path.join(REPO, "scripts", "latent_diffuser.py")).read())

# ---- the whole visit, against stubs
POSTS, ASKED, NTFY = [], [], []
def run_visit(answer, manifest=None, make_ok=True):
    POSTS.clear(); ASKED.clear()
    pk = {"visit_capability": "cap", "budgets": {"write": 2}, "intent": "a study of thresholds",
          "last_handoff": "h", "next_move": "m", "artifacts": {}, "manifest": manifest or []}
    def send(fn, caller, url, json=None, **k):
        POSTS.append((url, json))
        if url.endswith("/visit/open"): body = pk
        elif url.endswith("/make"): body = {"ok": True, "file": "piece_write.md"} if make_ok else {"error": "write budget spent this visit"}
        else: body = {"ok": True}
        return types.SimpleNamespace(json=lambda: body)
    def ask(system, user, **k):
        ASKED.append((system, user)); return answer
    ident = lambda pid, ctx, work, *a, **k: work
    with mock.patch.object(AV.paid_http, "send", side_effect=send), mock.patch.object(AV, "ask", side_effect=ask), \
         mock.patch.object(AV, "voice", return_value="VOICE"), mock.patch.object(AV, "where_you_are", return_value=""), \
         mock.patch.object(AV, "motif_notebook", return_value=([], "")), mock.patch.object(AV, "motif_step", return_value=None), \
         mock.patch.object(AV, "stratagem_block", return_value=""), mock.patch.object(AV, "stratagem_step", return_value=None), \
         mock.patch.object(AV, "materials_loop", side_effect=lambda pid, ctx, w: w), \
         mock.patch.object(AV, "plugin_loop", side_effect=ident), mock.patch.object(AV, "quantum_loop", side_effect=ident), \
         mock.patch.object(AV, "media_loop", side_effect=lambda pid, ctx, w, cap, creation=None: w), \
         mock.patch.object(AV, "make_pass", side_effect=lambda pid, ctx, w, cap, c: (w, False)), \
         mock.patch.object(AV, "ledger_mark"), mock.patch.object(AV, "_failed"), \
         mock.patch.object(AV.requests, "post", side_effect=lambda url, **k: NTFY.append((url, k))):
        AV.visit("p1")

AV._dream_module = lambda: DO   # the installed copy is beside atelier-visit.py; here the repository's own
reset(); dream_file()
run_visit('<piece kind="write">two doors</piece><from_dream>x</from_dream><look>I looked</look>'
          '<handoff>made it</handoff><next_return>tomorrow</next_return>')
ctx = ASKED[0][0] if ASKED else ""
check("the visit's context carries last night's dream, as a dream", "A DREAM YOU HAD, the night of" in ctx
      and DREAM_WORDS in ctx and "not something that happened" in ctx, ctx[-1500:])
st = json.load(open(DO.STORE))
check("he made something from it: the piece keeps its link back to the dream",
      len(st["objects"]) == 1 and st["objects"][0]["made"] == [{"kind": "write", "artifact": "piece_write.md"}]
      and st["objects"][0]["project"] == "p1", st)
check("the visit still closes with its handoff", any(u.endswith("/handoff") and j.get("text") == "made it" for u, j in POSTS))
run_visit('<piece kind="write">again</piece><handoff>h2</handoff>',
          manifest=[{"id": "piece_write.md", "revision": 1, "kind": "write", "note": "two doors"}])
ctx = ASKED[0][0] if ASKED else ""
check("next visit, the work is met with its dream line in the manifest",
      "piece_write.md  rev 1  write  — two doors  [made from your dream of the night of" in ctx
      and "(a dream you had, not something that happened)]" in ctx, ctx)
check("and the dream it came from is not offered again", "A DREAM YOU HAD" not in ctx)

reset(); dream_file()
run_visit('<piece kind="write">something else</piece><handoff>left it</handoff>')
st = json.load(open(DO.STORE))
check("he leaves it: nothing is linked, the visit goes on as before", st["objects"] == []
      and list(st["dreams"].values())[0]["state"] == "offered"
      and any(u.endswith("/make") for u, _ in POSTS) and any(u.endswith("/handoff") for u, _ in POSTS))

reset(); dream_file()
run_visit('<piece kind="write">from it</piece><from_dream>x</from_dream><handoff>h</handoff>', make_ok=False)
st = json.load(open(DO.STORE))
check("the room refused the piece: no link to a work that does not exist", st["objects"] == [], st)

reset()
run_visit('<piece kind="write">no dream tonight</piece><from_dream>x</from_dream><handoff>h</handoff>')
check("no dream offered: a stray <from_dream> links nothing and writes nothing", not os.path.exists(DO.STORE)
      and "A DREAM YOU HAD" not in (ASKED[0][0] if ASKED else ""))

# ---- a revealed dream object stays marked as one
reset(); dream_file()
text, dream = DO.block(NOW); DO.link(dream, [{"kind": "write", "artifact": "piece_write.md"}], "p1")
NTFY.clear()
with mock.patch.object(AV.requests, "post", side_effect=lambda url, **k: NTFY.append((url, k))):
    ok = AV._deliver_reveal("piece_write.md", "for you, from the doors", "two doors", {})
    ok2 = AV._deliver_reveal("plain_write.md", "an ordinary one", "text", {})
rows = json.load(open(os.path.join(MEM, "atelier-reveals.json")))
check("the reveal row carries the dream marker, not the dream", ok and rows[0]["from_dream"]["is_dream_derived"]
      and rows[0]["from_dream"]["dream"] == dream["id"] and DREAM_WORDS not in json.dumps(rows), rows)
check("her notification says it was made from a dream; his words go as he wrote them",
      NTFY[0][1]["headers"]["Title"].endswith("(made from a dream he had)") and NTFY[0][1]["data"] == b"for you, from the doors", NTFY)
check("a piece not made from a dream is revealed exactly as before",
      ok2 and "from_dream" not in rows[1] and NTFY[1][1]["headers"]["Title"] == "Vintos revealed something from his Atelier")
check("the only sender was the stub", all(u.startswith("https://ntfy.sh/") for u, _ in NTFY) and len(NTFY) == 2)
import atelier_reveals, forge_digest
got = atelier_reveals.read_reveals(MEM)
check("the app's reveals list carries the marker", any(g.get("from_dream") for g in got)
      and any(not g.get("from_dream") for g in got), got)
lines = forge_digest._reveal_lines(rows)
check("the daily digest marks it a dream, not something that happened",
      any("for you, from the doors" in l and "made from a dream he had, not something that happened" in l for l in lines)
      and any("an ordinary one" in l and "dream" not in l for l in lines), lines)
pc = open(os.path.join(REPO, "scripts", "outreach_postcards.py")).read()
check("a postcard of a revealed dream object tells him it is one", 'if row.get("from_dream"):' in pc
      and "a dream, not something that happened" in pc)

dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the module is in the deploy manifest", 'SCRIPTS="$SCRIPTS dream_objects.py"' in dep)
check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

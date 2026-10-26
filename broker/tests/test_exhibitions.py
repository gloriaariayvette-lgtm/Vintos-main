#!/usr/bin/env python3
"""Exhibitions of what mattered to him (proposal 20): in an Atelier visit he already has, he may make Gloria an
exhibition of three to six works that are already out of the room (revealed by his own act, or paintings he kept),
in his order, a line from him about each, how one changed into another, and beside a work its recorded occasion.
Sealed work is never read or shown; a dream-made work keeps its dream marker; nothing is posted or sent.

Scratch HOME and workspace; the model, the broker and ntfy are stubs that record what they were sent; every socket is
refused."""
import hashlib, importlib.util, json, os, re, socket, sys, tempfile, time, types
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="exhibitions-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); ART = os.path.join(MEM, "art")
os.makedirs(os.path.join(ART, "music"), exist_ok=True)
os.environ["SPARK_WORKSPACE"] = WS
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
try: import requests  # noqa: F401
except ImportError: sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import exhibitions as EX
import work_episodes as WE
spec = importlib.util.spec_from_file_location("atelier_visit_exhibitions", os.path.join(REPO, "scripts", "atelier-visit.py"))
AV = importlib.util.module_from_spec(spec); spec.loader.exec_module(AV)
AV.WSP = WS; AV.CHOICES = os.path.join(MEM, "atelier-choices.jsonl"); AV.KNOCK_STORE = os.path.join(MEM, ".atelier-knock.json")
AV._exhibition_module = lambda: EX
AV._dream_module = lambda: None
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every store is in the scratch workspace", EX.MEMORY.startswith(HOME) and WE.MEMORY.startswith(HOME)
      and AV.WSP.startswith(HOME), (EX.MEMORY, WE.MEMORY))

SEALED = "SEALED-ATELIER-WORDS"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
def w(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(data, bytes) else "w") as f: f.write(data)

def setup():
    for p in (os.path.join(MEM, EX.STORE_NAME),):
        if os.path.exists(p): os.remove(p)
    # the sealed room's own store and an unrevealed row: never read, never shown
    w(os.path.join(MEM, "atelier", "p9", "piece_write.md"), SEALED)
    w(os.path.join(MEM, "atelier-sealed-retry.json"), json.dumps({"x": SEALED}))
    for n in ("kept.png", "dreamt.png", "down.png", "unkept.png", "sealed.png", "p2_image.png"):
        w(os.path.join(ART, n), PNG)
    w(os.path.join(MEM, "atelier-reveals.json"), json.dumps([
        {"revealed_at": "2026-09-01T10:00:00", "revealed": True, "artifact": "p1_write.md", "medium": "write",
         "content": "the first revealed words", "disclosure": "for you"},
        {"revealed_at": "2026-10-20T10:00:00", "revealed": True, "artifact": "p2_image.png", "medium": "image",
         "content": "", "disclosure": "a dreamt one", "sha256": "x", "bytes_verified": True,
         "from_dream": {"dream": "dream:abc", "night_of": "2026-10-19", "is_dream_derived": True}},
        {"revealed_at": "2026-10-21T10:00:00", "revealed": False, "artifact": "p9_write.md", "content": SEALED},
        {"revealed_at": "2026-10-22T10:00:00", "revealed": True, "artifact": "atelier/p9/piece_write.md", "content": SEALED},
    ]))
    w(os.path.join(ART, "gallery.json"), json.dumps([
        {"image": "kept.png", "timestamp": "2026-09-10T09:00:00", "prompt": "a lantern over water", "verdict": "keep",
         "image_class": "WANT_ACT", "want_id": "w1"},
        {"image": "dreamt.png", "timestamp": "2026-10-01T09:00:00", "prompt": "a soft door", "verdict": "keep",
         "image_class": "DREAM_BORN", "dream_source": "dream"},
        {"image": "down.png", "timestamp": "2026-10-02T09:00:00", "verdict": "keep", "taken_down": True},
        {"image": "unkept.png", "timestamp": "2026-10-03T09:00:00", "verdict": "discard"},
        {"image": "sealed.png", "timestamp": "2026-10-04T09:00:00", "verdict": "keep", "sealed": True, "content": SEALED},
        {"image": "missing.png", "timestamp": "2026-10-05T09:00:00", "verdict": "keep"},
    ]))
    w(os.path.join(MEM, "current-wants.json"), json.dumps({"wants": [
        {"id": "w1", "want": "to paint the light I keep seeing", "timestamp": "2026-09-09T20:00:00", "source": "pull"}]}))

setup()
C = EX.candidates()
keys = {c["artifact"]: c["key"] for c in C}
check("eligible: revealed works and paintings he kept; nothing unrevealed, sealed, taken down, unkept or missing",
      sorted(keys) == ["dreamt.png", "kept.png", "p1_write.md", "p2_image.png"], sorted(keys))
check("no sealed words reach a candidate", SEALED not in json.dumps(C))
by = {c["artifact"]: c for c in C}
check("a revealed dream-made work keeps its dream marker", (by["p2_image.png"]["dream"] or {}).get("marker") == EX.DREAM_MARKER
      and by["p2_image.png"]["dream"]["night_of"] == "2026-10-19")
check("a dream-born kept painting keeps its dream marker", (by["dreamt.png"]["dream"] or {}).get("is_dream_derived"))
check("an ordinary work carries no dream marker", by["kept.png"]["dream"] is None and by["p1_write.md"]["dream"] is None)
check("links are relative private shelf routes only", by["kept.png"]["link"] == "/api/art/painting/kept.png"
      and by["p1_write.md"]["link"] is None and by["p1_write.md"]["content"] == "the first revealed words")
occ = by["kept.png"]["occasion"]
check("a painting's recorded occasion comes from work_episodes (the want it answered)",
      occ and occ["id"] == "want:w1" and occ["kind"] == "want", occ)

# ---- the offer
NOW = time.time()
text, offered = EX.block(NOW)
check("the offer lists every eligible work by key, with what he said and the dream marker",
      offered and all(k in text for k in keys.values()) and "made from a dream you had, not something that happened" in text
      and "its recorded occasion: want:w1" in text, text)
check("the offer says it is not a finding and that nothing is posted",
      "not a finding about yourself" in text and "nothing is posted or sent" in text)
check("the offer is within its character cap and holds no sealed words", len(text) <= EX.BLOCK_CHARS and SEALED not in text)
check("not offered again within a week", EX.block(NOW + 3600) == ("", None))
os.remove(os.path.join(MEM, EX.STORE_NAME))
g = json.load(open(os.path.join(ART, "gallery.json")))
w(os.path.join(ART, "gallery.json"), json.dumps(g[:1]))
w(os.path.join(MEM, "atelier-reveals.json"), "[]")
check("fewer than three works out of the room: nothing offered, nothing recorded",
      EX.block(NOW) == ("", None) and not os.path.exists(os.path.join(MEM, EX.STORE_NAME)))
setup()
text, offered = EX.block(NOW)
K = {c["artifact"]: c["key"] for c in offered}

def ex(works, rels="", title="Lanterns, and a door", arg="what I kept coming back to"):
    return ('<exhibition title="%s"><argument>%s</argument>%s%s</exhibition>' % (title, arg, works, rels))
def wk(name, line="this one", beside=""):
    return '<work id="%s"%s>%s</work>' % (K.get(name, name), (' beside="%s"' % beside) if beside else "", line)

# ---- refusals: kept nowhere, the reason recorded content-free
for name, body in [
    ("two works", ex(wk("kept.png") + wk("p1_write.md"))),
    ("a work not offered", ex(wk("kept.png") + wk("p1_write.md") + wk("p:deadbeef"))),
    ("a work twice", ex(wk("kept.png") + wk("kept.png") + wk("p1_write.md"))),
    ("a work with no line", ex(wk("kept.png") + wk("p1_write.md") + wk("dreamt.png", line=" "))),
    ("an occasion that is not that work's", ex(wk("kept.png") + wk("p1_write.md", beside="want:w1") + wk("dreamt.png"))),
    ("a relation outside the exhibition", ex(wk("kept.png") + wk("p1_write.md") + wk("dreamt.png"),
                                             '<relation from="%s" to="%s">grew</relation>' % (K["kept.png"], K["p2_image.png"]))),
    ("no title", ex(wk("kept.png") + wk("p1_write.md") + wk("dreamt.png"), title="")),
]:
    rec, why = EX.make(offered, body, "p1", NOW)
    check("refused: %s" % name, rec is None and why, why)
rec, why = EX.make(None, ex(wk("kept.png") + wk("p1_write.md") + wk("dreamt.png")), "p1", NOW)
check("refused: nothing was offered this visit", rec is None and "offered" in why, why)
st = json.load(open(os.path.join(MEM, EX.STORE_NAME)))
check("refusals keep only when and why", not st["exhibitions"] and st["refused"]
      and all(set(r) == {"at", "project", "why"} for r in st["refused"]))

# ---- one that holds
body = ex(wk("p1_write.md", "where it started") + wk("kept.png", "the light I kept painting", beside="want:w1")
          + wk("p2_image.png", "and then it came back in a dream <b>"),
          '<relation from="%s" to="%s">the words became a light</relation>' % (K["p1_write.md"], K["kept.png"]))
rec, why = EX.make(offered, body, "p1", NOW)
check("an exhibition of three works in his order, with a line each, is kept", rec and not why
      and [x["artifact"] for x in rec["works"]] == ["p1_write.md", "kept.png", "p2_image.png"], why)
check("its occasion and relation are kept by id", rec["works"][1]["beside"] == "want:w1"
      and rec["relations"] == [{"from": K["p1_write.md"], "to": K["kept.png"], "how": "the words became a light"}])
check("the record holds keys and his words, never a work's content", "the first revealed words" not in json.dumps(rec))
check("it is marked his curation, not evidence about him", rec["is_curation"] and not rec["generation_provenance"]["may_witness"]
      and rec["evidence_standing"] == "ineligible" and "not independent evidence" in rec["claim"])
check("the dream-made work carries its marker in the record", rec["works"][2]["from_dream"]["marker"] == EX.DREAM_MARKER)

# ---- what she sees
V = EX.view(MEM)
v = V[0]["works"]
check("the app view joins each work as it is now", v[0]["content"] == "the first revealed words"
      and v[1]["link"] == "/api/art/painting/kept.png" and v[1]["beside"]["id"] == "want:w1"
      and v[2]["from_dream"]["marker"] == EX.DREAM_MARKER)
check("the view holds no sealed words", SEALED not in json.dumps(V))
doc = EX.page(rec["id"], base="http://shelf")
check("the page escapes his words and runs no script", "<script" not in doc.lower() and "dream &lt;b&gt;" in doc)
check("the page links the private shelf routes and marks the dream",
      'src="http://shelf/api/art/painting/kept.png"' in doc and "a dream, not something that happened" in doc
      and "the words became a light" in doc)
g = json.load(open(os.path.join(ART, "gallery.json"))); g[0]["taken_down"] = True
w(os.path.join(ART, "gallery.json"), json.dumps(g))
v = EX.view(MEM)[0]["works"]
check("a work taken down later is withdrawn: no link, no content", v[1]["withdrawn"] and "link" not in v[1]
      and "content" not in v[1])
setup()

# ---- the whole visit, against stubs
POSTS, ASKED, NTFY = [], [], []
def run_visit(answer):
    POSTS.clear(); ASKED.clear()
    pk = {"visit_capability": "cap", "budgets": {"write": 2}, "intent": "a study of light",
          "last_handoff": "h", "next_move": "m", "artifacts": {}, "manifest": []}
    def send(fn, caller, url, json=None, **k):
        POSTS.append((url, json))
        body = pk if url.endswith("/visit/open") else {"ok": True, "file": "piece_write.md"} if url.endswith("/make") else {"ok": True}
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

def key_of(name):
    return next(c["key"] for c in EX.candidates() if c["artifact"] == name)
inner = ('<exhibition title="Three lights"><work id="%s">one</work><work id="%s">two <reveal artifact="p9_write.md">x</reveal>'
         '</work><work id="%s">three</work></exhibition>' % (key_of("p1_write.md"), key_of("kept.png"), key_of("dreamt.png")))
run_visit('<piece kind="write">a lamp</piece>' + inner + '<look>I looked</look><handoff>made it</handoff>')
ctx = ASKED[0][0] if ASKED else ""
st = json.load(open(os.path.join(MEM, EX.STORE_NAME)))
check("the visit carries the offer in its existing turn (one model call)", "YOUR WORKS ALREADY OUT OF THIS ROOM" in ctx
      and len(ASKED) == 1)
check("the exhibition he wrote in the visit is kept", len(st["exhibitions"]) == 1
      and st["exhibitions"][0]["title"] == "Three lights", st)
check("a tag inside the exhibition is not acted on: no reveal, nothing sent",
      not any("/reveal/" in u for u, _ in POSTS) and NTFY == [], [u for u, _ in POSTS])
check("the piece he made is made as before", any(u.endswith("/make") for u, _ in POSTS))
run_visit('<piece kind="write">again</piece>' + inner + '<handoff>h</handoff>')
st = json.load(open(os.path.join(MEM, EX.STORE_NAME)))
check("within the week there is no offer, and an unoffered exhibition is not kept",
      "YOUR WORKS ALREADY OUT OF THIS ROOM" not in ASKED[0][0] and len(st["exhibitions"]) == 1
      and st["refused"][-1]["why"] == "no exhibition was offered this visit")

# ---- boundaries in the source
src = open(os.path.join(REPO, "scripts", "exhibitions.py")).read()
check("the module calls no model and sends nothing", not re.search(r"import requests|ntfy|deliver|paid_http|urlopen", src))
check("the module never opens the sealed store (only the reveal export ledger and the gallery)",
      "atelier-reveals.json" not in src and "read_reveals" in src and "visit_capability" not in src)
readers = []
for top in ("bin", "scripts"):
    for dp, _d, fns in os.walk(os.path.join(REPO, top)):
        for fn in fns:
            p = os.path.join(dp, fn)
            if fn.endswith((".py", ".sh")) and fn != "exhibitions.py" and not os.path.islink(p):
                s = open(p, encoding="utf-8", errors="replace").read()
                if "exhibitions.json" in s or "import exhibitions" in s: readers.append(os.path.relpath(p, REPO))
check("only the visit and her app route use it; nothing feeds it to his self-model, wants or threads",
      sorted(readers) == ["bin/server.py", "scripts/atelier-visit.py"], readers)
server = open(os.path.join(REPO, "bin", "server.py")).read()
i = server.index('@app.get("/api/atelier/exhibitions")')
check("the app route is authenticated and reads only the view", "X-Vintos-Secret" in server[i:i + 900]
      and "exhibitions.view(MEMORY" in server[i:i + 900] and server.count('/api/atelier/exhibitions"') == 1)
app = open(os.path.join(REPO, "clients", "mobile", "index.html"), encoding="utf-8").read()
check("the Atelier tab shows exhibitions and marks dream-made works", "/api/atelier/exhibitions" in app
      and "a dream, not something that happened" in app and "_renderAtelierExhibitions" in app)
man = json.load(open(os.path.join(REPO, "clients", "mobile", "source.json")))
check("the mobile release manifest names this index.html", man["sha256"]["index.html"]
      == hashlib.sha256(open(os.path.join(REPO, "clients", "mobile", "index.html"), "rb").read()).hexdigest())
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the module is in the deploy manifest", 'SCRIPTS="$SCRIPTS exhibitions.py"' in dep)
check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

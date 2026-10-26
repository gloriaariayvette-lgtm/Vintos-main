#!/usr/bin/env python3
"""From a work back to its occasion (design 03): exact joins by content hash and receipt ids, never by title, minute
or cosine; revision selection; a moved file keeps its origin, a changed file under the same name does not; missing
origins stay missing; a source withdrawn after indexing is gone from the next look and from what is offered; Landings
and Atelier stores are never opened; events and readings stay apart; two hops at most; a per-turn and per-day cap on
what reaches a paid prompt; the use log holds ids only. Every record is invented fixture text in a scratch workspace;
the encoder is a deterministic stub; sockets are refused."""
import builtins, hashlib, json, os, socket, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="work-episodes-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
os.environ["VINTOS_LANDINGS_DIR"] = os.path.join(HOME, ".vintos", "landings")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import work_episodes as W
import media_embed as M
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("every store it reads or writes is in the scratch workspace",
      all(p.startswith(HOME) for p in list(W.SOURCES.values()) + [W.OFFERS, W.USES, W.ART]) and M.ART == W.ART)
check("no Landings or Atelier store is among its sources",
      not any("landing" in p.lower() or "atelier" in p.lower() for p in W.SOURCES.values()))

MEM, ART = W.MEMORY, W.ART
for d in ("video", "music", "archive"):
    os.makedirs(os.path.join(ART, d), exist_ok=True)
def put(rel, data):
    p = os.path.join(ART, rel); open(p, "wb").write(data); return p
sha = lambda b: hashlib.sha256(b).hexdigest()
def dump(path, obj):
    open(path, "w").write(json.dumps(obj))
    st = os.stat(path); os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1000000))   # a rewrite is always a change

B_TIDE, B_MOVED, B_HARBOR_OLD, B_HARBOR_NEW = b"lantern tide", b"quiet stairwell", b"harbor at noon", b"harbor at night"
tide = put("painting-tide.png", B_TIDE)
moved = put("archive/painting-moved-elsewhere.png", B_MOVED)          # the receipt still names its old place
harbor = put("painting-harbor.png", B_HARBOR_NEW)                     # same name, different bytes than its receipt
dream = put("painting-dream.png", b"a door in fog")
sealed = put("painting-sealed.png", b"not for the house")
salt1 = put("music/Salt_Hours_v1.mp3", b"first salt song")
salt2 = put("music/Salt_Hours_b2_v1.mp3", b"second salt song")
dump(os.path.join(ART, "gallery.json"), [
    {"image": "painting-tide.png", "path": "painting-tide.png", "sha256": sha(B_TIDE), "revision": 1, "want_id": "w-tide",
     "timestamp": "2026-09-01T10:00:00", "prompt": "a lantern hung over the low tide", "dream_source": "want",
     "his_reading": "the lantern is too bright; the water is right", "sighted_at": "2026-09-03T08:00:00", "verdict": "keep"},
    {"image": "painting-moved.png", "path": "painting-moved.png", "sha256": sha(B_MOVED), "revision": 1, "want_id": "w-moved",
     "timestamp": "2026-09-02T10:00:00", "prompt": "a stairwell with no one on it"},
    {"image": "painting-harbor.png", "path": "painting-harbor.png", "sha256": sha(B_HARBOR_OLD), "revision": 1,
     "want_id": "w-harbor", "timestamp": "2026-09-04T10:00:00", "prompt": "the harbor at noon"},
    {"image": "painting-dream.png", "timestamp": "2026-09-05T10:00:00", "prompt": "a door in fog", "dream_source": "dream"},
    {"image": "painting-sealed.png", "path": "painting-sealed.png", "sha256": sha(b"not for the house"), "sealed": True,
     "source": "atelier", "want_id": "w-sealed", "timestamp": "2026-09-06T10:00:00", "prompt": "SEALED-PROMPT-TEXT"}])
dump(os.path.join(ART, "music", "music.json"), {"generated": [
    {"title": "Salt Hours", "task_id": "task-1", "generated_at": "2026-09-07T10:00:00", "want_id": "w-salt1",
     "felt_sense": "the tide pulling at my ribs, slow and warm", "shares_in_context": ["share-1"],
     "tracks": [{"version": 1, "local_file": salt1}], "landed": {"state": "landed", "note": "it settled like evening"}},
    {"title": "Salt Hours", "task_id": "task-2", "generated_at": "2026-09-08T10:00:00", "want_id": "w-salt2",
     "felt_sense": "brittle and quick", "tracks": [{"version": 1, "local_file": salt2}]}],
    "landings": [{"task_id": "task-1", "landed_at": "2026-09-07T10:05:00", "state": "landed"}]})
dump(os.path.join(ART, "video", "video-gallery.json"), [])
WANTS_FULFILLED = [
    {"id": "w-tide", "want": "to paint the lantern I kept seeing at the shore", "source": "wants-check",
     "timestamp": "2026-08-31T21:00:00", "fulfilled_at": "2026-09-01T10:00:00", "self_interpretation": "a light kept low"},
    {"id": "w-moved", "want": "to make an empty stairwell", "source": "wants-check", "timestamp": "2026-09-01T09:00:00"},
    {"id": "w-harbor", "want": "the harbor before the boats go out", "source": "wants-check", "timestamp": "2026-09-03T09:00:00"},
    {"id": "w-salt1", "want": "a song for the salt on the window", "source": "wants-router", "timestamp": "2026-09-06T09:00:00"},
    {"id": "w-salt2", "want": "WITHDRAWN-WANT-TEXT a second salt song", "source": "wants-router", "timestamp": "2026-09-07T09:00:00"},
    {"id": "w-sealed", "want": "SEALED-WANT-TEXT", "source": "wants-check", "timestamp": "2026-09-05T09:00:00"}]
dump(W.SOURCES["fulfilled_wants"], WANTS_FULFILLED)
dump(W.SOURCES["current_wants"], {"wants": []})
open(W.SOURCES["completions"], "w").write(json.dumps({"at": "2026-09-01T10:01:00", "want_id": "w-tide", "how": "fulfilled",
                                                       "by": "self-action", "turn_id": "t-fixture-1"}) + "\n")
dump(W.SOURCES["moments"], {"moments": {"m1": {"moment_id": "2026-09-01T10:01:00Z#want-fulfilled#AA", "timestamp": "2026-09-01T10:01:00",
    "source": "want-fulfilled", "content": "to paint the lantern", "links": {"want_id": "w-tide"},
    "snapshot": {"active_threads": [{"origin": "the shoreline at dusk"}]}}}})
dump(W.SOURCES["durable"], [
    {"occurred_at": "2026-09-01T11:00:00", "event": "she asked what the lantern meant", "gloria": "HER-PRIVATE-QUOTE",
     "exact_words": "I said it was for waiting", "felt_like": "held and a little shy", "source_turns": ["t-fixture-1"],
     "interpretations": [{"at": "2026-09-20T09:00:00", "verdict": "partial", "meaning": "it was less about waiting than about being found"}]},
    {"occurred_at": "2026-09-09T11:00:00", "event": "a talk about songs", "exact_words": "Salt Hours is my favourite of mine",
     "felt_like": "proud"},
    {"occurred_at": "2026-09-10T11:00:00", "event": "about the fog door", "exact_words": "painting-dream.png was a gift",
     "felt_like": "warm", "standing": "invalidated"}])
dump(W.SOURCES["shares"], [{"id": "share-1", "song": "A borrowed tune", "gloria_said": "HER-SHARE-WORDS"}])
os.makedirs(os.environ["VINTOS_LANDINGS_DIR"]); open(os.path.join(os.environ["VINTOS_LANDINGS_DIR"], "notes.json"), "w").write("RATING-SECRET")
open(os.path.join(MEM, "atelier-reveals.json"), "w").write("ATELIER-SECRET")

OPENED = []
_open = builtins.open
def _spy(p, *a, **k):
    OPENED.append(str(p)); return _open(p, *a, **k)
builtins.open = _spy

j = W.lookup(tide)
eps = {e["id"]: e for e in j["episodes"]}
check("a work joins the want its receipt names, by id", "want:w-tide" in eps and eps["want:w-tide"]["hop"] == 1
      and "operation receipt gallery#0" in eps["want:w-tide"]["support"], j["episodes"])
check("and its identity is the content hash, not the title or the minute",
      j["artifact"]["identity"] == "content hash" and j["artifact"]["id"] == "art:" + sha(B_TIDE)[:16])
check("the moment the want was fulfilled is found by the want id in its links",
      any(e["kind"] == "moment" and e["on_your_mind"] == ["the shoreline at dusk"] for e in j["episodes"]))
check("the completion's turn leads to the durable memory of it: the second hop",
      any(e["kind"] == "durable" and e["hop"] == 2 for e in j["episodes"]), j["episodes"])
check("no join goes past two hops", all(e.get("hop", 1) <= 2 for e in j["episodes"]))
check("what he wrote then, and how he read it later, are kept apart from the event",
      any(s["kind"] == "what you asked for" for s in j["said_then"])
      and {r["kind"] for r in j["readings"]} >= {"how you read it when you saw it", "reread on recall"}
      and not set(x["id"] for x in j["readings"]) & set(eps)
      and not any(r["text"] in json.dumps(j["episodes"]) for r in j["readings"]), j)
check("her words in a durable memory are not carried into the join", "HER-PRIVATE-QUOTE" not in json.dumps(j))

# two works with the same title: each joins only its own receipt; a title in his words links neither
s1, s2 = W.lookup(salt1), W.lookup(salt2)
check("identical titles: each song joins its own want and not the other's",
      [e["id"] for e in s1["episodes"] if e["kind"] == "want"] == ["want:w-salt1"]
      and [e["id"] for e in s2["episodes"] if e["kind"] == "want"] == ["want:w-salt2"], (s1["episodes"], s2["episodes"]))
check("and a title another work shares links no memory to either", not any(e["kind"] == "durable" for e in s1["episodes"] + s2["episodes"])
      and any("another work has this title" in m["why"] for m in s1["missing"]))
check("her shared song in the composer's context is present, not a cause; her words stay out",
      s1["co_present"] and s1["co_present"][0]["relation"] == "co_present" and "HER-SHARE-WORDS" not in json.dumps(s1)
      and "not a cause" in "\n".join(W.lines_for(s1)))

mv = W.lookup(moved)
check("a moved file with the same hash keeps its origin, and says where its receipt last had it",
      any(e["id"] == "want:w-moved" for e in mv["episodes"]) and mv["artifact"].get("moved_from") == "painting-moved.png", mv)
hb = W.lookup(harbor)
check("a changed file under the same name does not inherit the old revision's origin",
      not hb["episodes"] and any("different revision" in m["why"] for m in hb["missing"]), hb)
dr = W.lookup(dream)
check("a dream-made work with no dream record stays unlinked, honestly",
      not dr["episodes"] and any("dream" in m["why"] for m in dr["missing"]), dr)
check("an invalidated memory that names a work links nothing, and is counted as withdrawn",
      not any(e["kind"] == "durable" for e in dr["episodes"]) and len(W.projection()["withdrawn"]) == 1)
none = W.lookup(put("painting-unknown.png", b"no receipt at all"))
check("a work with no receipt: origin not recorded", not none["episodes"] and W.lines_for(none) == ["  (origin not recorded)"])
sl = W.lookup(sealed)
check("a sealed Atelier piece on the shelf is never joined or shown",
      not sl["episodes"] and "SEALED" not in json.dumps(sl) and W.status()["sealed_skipped"] == 1, sl)

# the media index hands over the exact identity of what it found; the episode is looked up from that handle
CONCEPTS = ["lantern", "stairwell", "harbor", "salt", "fog"]
def encode(item):
    text = item if isinstance(item, str) else _open(next(v if isinstance(v, str) else v[0] for k, v in item.items() if k != "text"), "rb").read().decode()
    v = [1.0 if c in text else 0.0 for c in CONCEPTS] + [0.0] * (M.DIM - len(CONCEPTS))
    return v if any(v) else [0.0] * (M.DIM - 1) + [1.0]
M._excerpts = lambda path, tmp: []
M.index(encode=encode)
hits = M.search("that lantern", k=3, encode=encode)
check("a search result carries the revision's sha256 and an episode handle",
      hits and hits[0]["path"] == tide and hits[0]["sha256"] == sha(B_TIDE) and hits[0]["artifact_id"] == "art:" + sha(B_TIDE)[:16], hits)
check("the handle leads to the same joined record", any(e["id"] == "want:w-tide" for e in W.lookup(hits[0]["artifact_id"])["episodes"]))

# ranked lists are combined by identity, never by averaging vectors from two spaces
fused = W.fuse([{"path": harbor}, {"path": tide, "sha256": sha(B_TIDE)}], [{"sha256": sha(B_TIDE), "path": tide}])
check("two ranked lists fuse by the work's identity", fused[0]["path"] == tide and len(fused) == 2, fused)
check("and no more than five come back", len(W.fuse([{"path": "/x/%d.png" % i} for i in range(9)])) == 5)

# what reaches him: compact, attributed, capped per turn and per day; a test transcript
per, header = W.context([hits[0], {"path": harbor}], surface="chat")
blk_lines = per.get(tide) or []
check("the offered context names the want with its source id and date", any("[want:w-tide]" in l and "2026-08-31" in l for l in blk_lines), per)
check("and says plainly that nearness is not origin and an unrecorded origin is not to be guessed",
      "only resemblance" in header and "don't have the origin" in header)
check("one turn's episode lines stay within the turn cap", sum(len(l) + 1 for ls in per.values() for l in ls) <= W.TURN_CHARS)
reply = "That one came from wanting to paint the lantern I kept seeing at the shore - I still think the water is right."
use = W.note_use(reply, "chat", "t-reply-1")
check("his reply's use of the recorded detail is logged by source id", use and any(u["id"] == "want:w-tide" for u in use["used"]), use)
check("the same offer is not counted twice", W.note_use(reply, "chat", "t-reply-1") is None)
logs = _open(W.OFFERS).read() + _open(W.USES).read()
check("the offer and use logs hold ids and sizes, no words of the works or the wants",
      "lantern" not in logs and "shore" not in logs and "w-tide" in logs)
check("an unsupported 'you felt...' claim is refused", W.attest(tide, "you felt lonely and afraid")["supported"] is False)
ok = W.attest(salt1, "you felt the tide pulling at your ribs")
check("a felt claim the record holds is supported, with its source", ok["supported"] and ok["by"][0] == "music#0#felt", ok)

# a source withdrawn after indexing is gone from the next look and from what is offered
before = W.lookup(salt2)
dump(W.SOURCES["fulfilled_wants"], [w for w in WANTS_FULFILLED if w["id"] != "w-salt2"])
after = W.lookup(salt2)
per2, _ = W.context([{"path": salt2, "kind": "audio", "title": "Salt Hours"}], surface="chat")
check("a want withdrawn after indexing leaves a dangling id, never its words",
      any(e["id"] == "want:w-salt2" for e in before["episodes"]) and not after["episodes"]
      and any(m.get("want") == "w-salt2" for m in after["missing"]) and "WITHDRAWN-WANT-TEXT" not in json.dumps(after), after)
check("and nothing cached carries it into the next offer", "WITHDRAWN-WANT-TEXT" not in json.dumps(per2), per2)

# media_embed's chat block: episode lines under each work, and the plain block when the episode door fails
M.near = lambda text, k=3, timeout=1.5: [h for h in hits if h["path"] == tide]
blk = M.block("the lantern again")
check("the chat block puts the origin under the work and keeps its own wording", 'your painting "' in blk
      and "only if one truly fits" in blk and "[want:w-tide]" in blk and "only resemblance" in blk, blk)
real_ctx = W.context
W.context = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
plain = M.block("the lantern again")
check("with the episode door broken, the works block still reaches him unchanged", plain.startswith("Your own works nearest")
      and "[want:" not in plain and 'your painting "' in plain, plain)
W.context = real_ctx
open(W.OFFERS, "w").write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "surface": "chat", "chars": W.DAILY_CHARS}) + "\n")
check("past the day's cap nothing more is added to a paid prompt", W.context([hits[0]], surface="chat") == ({}, ""))
check("the journal, read by no paid model, is not held by the day's cap", W.context([hits[0]], surface="journal", record=False)[0])

check("Landings notes and Atelier stores were never opened",
      not any("landings" in p or "atelier" in os.path.basename(p) for p in OPENED), [p for p in OPENED if "atelier" in p or "landings" in p])
builtins.open = _open

srv = _open(os.path.join(REPO, "bin", "server.py")).read()
check("after each reply, his use of what was offered is noted, inline and skipped in test mode",
      '_inline("work_episodes", _work_use)' in srv and "_we.note_use(reply, surface, turn_id)" in srv)
wr = _open(os.path.join(REPO, "bin", "wants-router.py")).read()
check("a fulfilled want's moment carries the want's id in its links", '_mlinks["want_id"] = str(want.get("id"))' in wr)
for jp in ("scripts/idle-journal.sh", "bin/idle-journal.sh"):
    jr = _open(os.path.join(REPO, jp)).read()
    check("his journal's works footnote carries their origins (%s)" % jp,
          'media_embed.episodes_for(hits, surface="journal")' in jr and "Near this, among my own works" in jr)
dep = _open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs it", "work_episodes.py" in dep)
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

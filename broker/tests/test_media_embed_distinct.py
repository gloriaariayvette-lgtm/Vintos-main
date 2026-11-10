#!/usr/bin/env python3
"""The journal's "Near this, among my own works:" named the same song twice in a row: a song is made as two takes
under one title on one day, two files and two rows, and both were nearest. A work that prints as the same line is
now named once, and the journal and chat ask for two more hits so another work takes the second place.

Pure: synthetic hits, the search service is a stub, every socket is refused."""
import os, socket, sys, tempfile
HOME = tempfile.mkdtemp(prefix="vintos-works-distinct-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import media_embed as M

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

A1 = {"path": "/w/art/music/take_a_20260805.mp3", "kind": "audio", "title": "Fixture Song", "score": 0.61}
A2 = {"path": "/w/art/music/take_b_20260805.mp3", "kind": "audio", "title": "Fixture Song", "score": 0.60}
B = {"path": "/w/art/gallery/painting_20260901.png", "kind": "image", "title": "Fixture Painting", "score": 0.40}
C = {"path": "/w/art/music/other_20260805.mp3", "kind": "audio", "title": "Another Song", "score": 0.39}
per = {A1["path"]: ['  then: "fixture quote"'], A2["path"]: ['  then: "fixture quote"']}

out = M.describe([A1, A2], per)
check("two takes of one song are named once", out.count('"Fixture Song"') == 1 and out.count("fixture quote") == 1, out)
check("the nearer take is the one named, with its own lines", out.splitlines()[1] == per[A1["path"]][0], out)
check("distinct keeps order and fills to k from further hits", M.distinct([A1, A2, B, C], 2) == [A1, B])
check("distinct without k keeps every different work", M.distinct([A1, A2, B, C]) == [A1, B, C])
check("same title on another day is a different work",
      len(M.distinct([A1, dict(A2, path="/w/art/music/take_b_20260806.mp3")])) == 2)
check("different works still print as before", M.describe([A1, B]).count("- your ") == 2)
check("nothing gives nothing", M.describe([]) == "" and M.distinct([], 2) == [])

asked = []
M.near = lambda text, k=3, **kw: (asked.append(k) or [A1, A2, B, C][:k])
M.episodes_for = lambda hits, surface="chat": ({}, "")
blk = M.block("what she said", k=2)
check("the chat block asks two more than it shows", asked == [4], asked)
check("and shows two different works", blk.count('"Fixture Song"') == 1 and '"Fixture Painting"' in blk, blk)

for f in ("bin/idle-journal.sh", "scripts/idle-journal.sh"):
    src = open(os.path.join(REPO, f)).read()
    seg = src[src.index("_WORKS_NEAR=$("):src.index("WORKSNEAREOF\n)")]
    check("%s: the journal asks four and keeps two distinct" % f,
          "media_embed.distinct(media_embed.near(" in seg and ", 4, timeout=30), 2)" in seg, seg[-400:])

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

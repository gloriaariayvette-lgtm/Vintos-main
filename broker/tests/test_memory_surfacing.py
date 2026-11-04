#!/usr/bin/env python3
"""One exact past line surfaces when what she says is truly near it (4 November). Scratch HOME; every socket is
refused; the embedder is a stand-in, so nothing reaches LM Studio. Checks: exact words, the high bar, nothing recent,
nothing twice in a week, her words never echoed back, forgotten or edited-away words never return, test mode quiet."""
import json, os, socket, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="surfacing-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ.pop("SURFACING_INDEX_DIR", None); os.environ.pop("VINTOS_TEST_MODE", None)
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import numpy as np
import memory_surfacing as S
S._refresh_in_background = lambda: None

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every store is throwaway", all(p.startswith(HOME) for p in (S.META, S.VECS, S.SURFACED, S.LEDGER)))
os.makedirs(os.path.join(S.MEM, "journal"), exist_ok=True)
NOW = time.time(); DAY = 86400
iso = lambda t: __import__("datetime").datetime.fromtimestamp(t).isoformat()

# topics: each text's vector is its topic's axis, so similarity is exact and readable
TOPICS = ["pier", "rain", "violin", "bread", "orchard"]
def vec(t):
    v = np.full(len(TOPICS) + 1, 0.0); hit = [i for i, w in enumerate(TOPICS) if w in t.lower()]
    for i in hit: v[i] = 1.0
    if not hit: v[-1] = 1.0
    return list(v / np.linalg.norm(v))
fake = lambda texts, **k: [vec(t) for t in texts]

json.dump([{"timestamp": iso(NOW - 20 * DAY), "turn_id": "T1",
            "gloria": "I sat on the pier until the light went and thought about you the whole time.",
            "vintos": "[he leans in] I kept the pier in me all night, the boards still warm under your feet."},
           {"timestamp": iso(NOW - 1 * DAY), "turn_id": "T2",
            "gloria": "The rain today made the whole street smell like metal and wet stone.", "vintos": "ok"}],
          open(S.LEDGER, "w"))
open(os.path.join(S.MEM, "journal", "2026-10-01.md"), "w").write(
    "# Journal\n\nI wanted to learn the violin only so my hands would know what longing weighs.\n\nShort.\n")

check("passages keep her words, his words and his journal, exactly", sorted((p["kind"], p["who"]) for p in S.corpus())
      == [("chat", "her"), ("chat", "her"), ("chat", "him"), ("writing", "him")], [p["text"] for p in S.corpus()])
check("stage directions are not anyone's words", not any("[he leans in]" in p["text"] for p in S.corpus()))
check("headings and short lines are not passages", not any(p["text"] in ("# Journal", "Short.") for p in S.corpus()))
print(S.build_index(embed_fn=fake))
meta, vecs = S.load_index()
check("the index holds every passage, one vector each", len(meta) == 4 and vecs.shape == (4, 6))

hit = S.near("Tell me about the violin again", now=NOW, embed_fn=fake)
check("a truly near passage surfaces, with its exact words", hit and hit["text"].startswith("I wanted to learn the violin")
      and hit["score"] >= S.THRESHOLD, hit)
line = S.line_for(hit)
check("the line says when, where it came from, and quotes it", "A MEMORY SURFACED" in line and "your journal" in line
      and '"I wanted to learn the violin only so my hands would know what longing weighs."' in line, line)
check("nothing near enough, nothing surfaces", S.near("what should we cook tonight", now=NOW, embed_fn=fake) is None)
check("a day-old turn is the conversation, not a memory", S.near("the rain smelled like that again", now=NOW, embed_fn=fake) is None)
h = S.near("I am on the pier again", now=NOW, embed_fn=fake)
check("from the conversation, her line or his", h and h["kind"] == "chat" and "pier" in h["text"], h)
check("her own message is never handed back to her",
      S.near("I sat on the pier until the light went and thought about you the whole time.", now=NOW, embed_fn=fake)["who"] == "him")

S.embed = fake
out = S.block("Tell me about the violin again", surface="avatar", turn_id="T9")
check("block gives the line and keeps that it surfaced", out.startswith("[A MEMORY SURFACED")
      and json.loads(open(S.SURFACED).read().splitlines()[-1])["turn_id"] == "T9", out)
check("the same passage stays quiet for a week", S.block("Tell me about the violin again") == "")
os.remove(S.SURFACED)
open(os.path.join(S.MEM, "journal", "2026-10-01.md"), "w").write("# Journal\n\nI rewrote this entry entirely.\n")
check("words edited away from their source never come back", S.near("Tell me about the violin again", now=NOW, embed_fn=fake) is None)
open(os.path.join(S.MEM, ".test-mode"), "w").close()
check("test mode surfaces nothing", S.block("I am on the pier again") == "")
os.remove(os.path.join(S.MEM, ".test-mode"))
S.embed = lambda *a, **k: (_ for _ in ()).throw(OSError("LM Studio down"))
check("LM Studio down: nothing, and nothing raised", S.block("I am on the pier again") == "")

srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("every chat route that shows his works also offers a surfaced memory",
      srv.count("{_works_near(msg)}\n{_memory_surfaced(msg)}") == 4 == srv.count("{_works_near(msg)}"))
check("the deploy carries it", "memory_surfacing.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

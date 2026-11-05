#!/usr/bin/env python3
"""The same message is embedded once a turn, not once per caller (5 November). Scratch HOME; the embedder is a
stand-in that counts its calls, so nothing reaches LM Studio. Checks: durable memory, residue and the map views share
one vector for the same text; a different text, model or server is asked for afresh; an old vector is not reused; a
broken cache only means the embedder is asked as before."""
import os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="embcache-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(os.environ["SPARK_WORKSPACE"], "memory"))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import requests
asked = []
class _R:
    def __init__(self, text): self.text = text
    def json(self): return {"data": [{"embedding": [float(len(self.text)), 1.0]}]}
def _post(url, json=None, headers=None, timeout=None):
    asked.append((url, json["model"], json["input"])); return _R(json["input"])
requests.post = _post
import embed_cache as E, durable_memory, residue, map_view_compiler

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("the cache lives in his scratch memory", E.DB.startswith(HOME))
msg = "Ha. I thought you might be kind enough to be the one to use the shirt on me."
a, b, c = durable_memory._embed(msg), residue._embed(msg), map_view_compiler._embed(msg)
check("three callers, one message: nomic is asked once", len(asked) == 1 and a == b == c, asked)
residue._embed("something else entirely")
check("a different text is asked for", len(asked) == 2)
E.embed("http://elsewhere:1234/v1/embeddings", E_MODEL := "text-embedding-nomic-embed-text-v1.5", msg)
check("the same text from another server is asked for", len(asked) == 3)
E.embed(durable_memory.LM_EMBED_URL, "another-model", msg)
check("and from another model", len(asked) == 4)
import sqlite3
with sqlite3.connect(E.DB) as con:
    con.execute("UPDATE v SET t = ?", (time.time() - E.TTL_S - 1,))
durable_memory._embed(msg)
check("an old vector is not reused", len(asked) == 5)
open(E.DB, "w").write("not a database")
check("a damaged cache only means nomic is asked as before", durable_memory._embed(msg) == a and len(asked) == 6)
check("the deploy carries it", "embed_cache.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
durable_memory._embed(msg); durable_memory._embed(msg)
check("and the damaged cache is started again: one ask, then shared", len(asked) == 7)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

#!/usr/bin/env python3
"""What the search SERVES, not only what it embeds.

The recall that reaches his prompt reads the legacy embeddings.jsonl when it exists. Two faults
lived there:
  (b) the dream marker only fired on source=='dreams' or '/dreams/' in `path`, but a legacy row
      carries only `file`/`title` — so ~600 dream rows came back WITHOUT the
      "[A DREAM he had - not something that happened]" marker and were told to him as things that
      happened;
  (a) the append-only index still pointed at deleted/superseded source files, so a memory he no
      longer has was still recalled.

This suite builds a scratch legacy index with synthetic rows and asserts: a legacy dream row gets
the marker and is_dream, a row whose source file is gone is not served, and ordinary present rows
are served as before. Nothing reaches the network (the embedding service is stubbed).
"""
import os, sys, json, tempfile, types, importlib.util

HOME = tempfile.mkdtemp(prefix="mem-serve-"); os.environ["HOME"] = HOME
os.environ.pop("SPARK_WORKSPACE", None)
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

MEM = os.path.join(HOME, ".vintos", "workspace", "memory")
DREAMS = os.path.join(MEM, "skills", "dreaming", "memory", "dreams")
JOURNAL = os.path.join(MEM, "journal")
for d in (DREAMS, JOURNAL):
    os.makedirs(d)

# Real source files on disk for the rows that should still be served.
dream_file = os.path.join(DREAMS, "2026-10-01_001.md"); open(dream_file, "w").write("a dream body")
present_file = os.path.join(JOURNAL, "2026-10-02.md"); open(present_file, "w").write("a journal body")
# A legacy row pointing at a file that no longer exists (deleted / superseded).
gone_file = os.path.join(JOURNAL, "2026-09-09-DELETED.md")   # never created

with open(os.path.join(MEM, "embeddings.jsonl"), "w") as f:
    # legacy dream row: only file/title/text, no `source`, no `path` — the old marker missed this
    f.write(json.dumps({"embedding": [1.0, 0.0], "file": dream_file, "title": "a dream", "text": "I flew over the city"}) + "\n")
    # legacy ordinary row whose source file is present
    f.write(json.dumps({"embedding": [1.0, 0.0], "file": present_file, "title": "journal", "text": "an ordinary memory"}) + "\n")
    # legacy ordinary row whose source file is GONE — must not be served
    f.write(json.dumps({"embedding": [1.0, 0.0], "file": gone_file, "title": "deleted", "text": "a memory he no longer has"}) + "\n")

# Stub the embedding service: the query embedding matches everything so scores don't gate the test.
NET = []
class Resp:
    status_code = 200
    def json(self): return {"data": [{"embedding": [1.0, 0.0]}]}
class RequestException(Exception): pass
def post(url, json=None, timeout=None, **k):
    NET.append(url); return Resp()
sys.modules["requests"] = types.SimpleNamespace(post=post, RequestException=RequestException)

spec = importlib.util.spec_from_file_location("memory_search_serve_t", os.path.join(REPO, "scripts", "memory-search.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
check("the memory store is scratch", M.MEMORY.startswith(HOME))

# --- the helpers directly ---
print("--- the serve-time helpers ---")
check("a legacy dream row (file only) is recognised as a dream",
      M._is_dream({"file": dream_file, "title": "a dream"}) is True)
check("a legacy journal row is not a dream", M._is_dream({"file": present_file}) is False)
check("a v2 dream row (source=='dreams') is still a dream", M._is_dream({"source": "dreams", "path": dream_file}) is True)
check("a row whose source file exists is present", M._source_present({"file": present_file}) is True)
check("a row whose source file is gone is not present", M._source_present({"file": gone_file}) is False)
check("a v2 chunk with no file reference is left alone", M._source_present({"source": "journal", "chunk": "x"}) is True)

# --- through the full search path ---
print("\n--- through search() ---")
got = M.search("anything", limit=10)
texts = [r["text"] for r in got]
dream_hit = next((r for r in got if "I flew over the city" in r["text"]), None)
check("the dream row is served", dream_hit is not None, texts)
check("and it carries the dream marker on its face",
      dream_hit and dream_hit["text"].startswith("[A DREAM he had - not something that happened] "), dream_hit)
check("and is flagged is_dream", dream_hit and dream_hit["is_dream"] is True)
check("the present ordinary memory is served", any("an ordinary memory" in t for t in texts))
check("the ordinary memory is NOT marked a dream",
      all(not r["is_dream"] for r in got if "an ordinary memory" in r["text"]))
check("the row whose source file is gone is NOT served",
      not any("a memory he no longer has" in t for t in texts), texts)
check("nothing reached the real network", NET and all(u.startswith("http://172.") for u in NET), NET)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

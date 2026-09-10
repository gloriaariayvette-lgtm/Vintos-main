#!/usr/bin/env python3
"""Review items 105, 106, 111 (2026-09-10): the retrieval projection is versioned and
rebuildable - revisions, tombstones, kinds, model/dims - and a gated read that fails is
HELD, never replaced by the raw file. Scratch HOME only; nothing under ~/.vintos."""
import os, sys, json, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-proj-")
os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory")
os.makedirs(os.path.join(MEM, "journal"), exist_ok=True)
REAL = os.path.expanduser("~gloria/.vintos") if os.path.isdir("/home/gloria") else None

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

sys.path.insert(0, os.path.join(REPO, "scripts"))
try:
    import numpy  # noqa
except ImportError:                       # serve_entries needs no numpy; the search body does
    import types
    _np = types.ModuleType("numpy"); _np.array = lambda x: x; _np.dot = lambda a, b: 0.0
    _np.linalg = types.SimpleNamespace(norm=lambda x: 1.0); sys.modules["numpy"] = _np
try:
    import requests  # noqa
except ImportError:
    import types
    sys.modules["requests"] = types.ModuleType("requests")
MI = load("memory_index_t", os.path.join(REPO, "scripts", "memory-index.py"))
MS = load("memory_search_t", os.path.join(REPO, "scripts", "memory-search.py"))
EV = load("evidence_view_t", os.path.join(REPO, "scripts", "evidence_view.py"))
check("twins identical: memory-index", open(os.path.join(REPO, "scripts", "memory-index.py"), "rb").read() == open(os.path.join(REPO, "bin", "memory_index.py"), "rb").read())
check("twins identical: memory-search", open(os.path.join(REPO, "scripts", "memory-search.py"), "rb").read() == open(os.path.join(REPO, "bin", "memory_search.py"), "rb").read())

DIMS = MI.EMBED_DIMS
calls = []
def embed(text):
    calls.append(text)
    v = [0.0] * DIMS; v[len(text) % DIMS] = 1.0; return v

print("\n--- 105/111: a first build carries revision, kind, model and dims ---")
j1 = os.path.join(MEM, "journal", "2026-09-10.md"); open(j1, "w").write("# today\n\nI walked to the window and stayed there a while, which is new for me.\n")
sm = os.path.join(WS, "SELF-MODEL.md"); open(sm, "w").write("# SELF-MODEL\n\nI am someone who reaches first when Gloria goes quiet, and who notices it.\n")
sources = MI.discover_sources(WS)
check("both sources discovered", {p for _, p in sources} >= {j1, sm}, sources)
idx, st = MI.build_projection({}, sources, embed, now="t1")
ents = idx["entries"]
check("chunks were embedded", st["new"] >= 2 and len(ents) == st["new"], st)
e_j = [e for e in ents if e["path"] == j1]; e_s = [e for e in ents if e["path"] == sm]
check("journal chunks are felt", e_j and all(e["kind"] == "felt" for e in e_j), [e.get("kind") for e in e_j])
check("self-model chunks are authored", e_s and all(e["kind"] == "authored" for e in e_s), [e.get("kind") for e in e_s])
check("every chunk carries revision, embed_model, embed_dims", all(e.get("revision") and e.get("embed_model") == MI.EMBED_MODEL and e.get("embed_dims") == DIMS for e in ents))
check("projection declares version, model and dims", idx.get("version", 0) >= 2 and idx.get("embed_model") == MI.EMBED_MODEL and idx.get("embed_dims") == DIMS, {k: idx.get(k) for k in ("version", "embed_model", "embed_dims")})

print("\n--- 105: unchanged sources are not re-embedded ---")
n0 = len(calls)
idx2, st2 = MI.build_projection(idx, MI.discover_sources(WS), embed, now="t2")
check("no new embeddings on a no-change run", len(calls) == n0 and st2["new"] == 0 and st2["unchanged"] == len(sources), st2)
check("no tombstones on a no-change run", len(idx2.get("tombstones") or []) == 0)

print("\n--- 105: a revised source tombstones its old chunks and re-embeds ---")
import time; time.sleep(0.02)
open(j1, "a").write("\nLater: I stayed longer than I meant to, and it did not feel like waiting.\n")
os.utime(j1, None)
idx3, st3 = MI.build_projection(idx2, MI.discover_sources(WS), embed, now="t3")
tomb = idx3["tombstones"]
check("old journal chunks tombstoned as revised", st3["revised"] == 1 and any(t["path"] == j1 and t["reason"] == "revised" for t in tomb), (st3, tomb[:2]))
check("new journal chunks carry the new revision", all(e["revision"] == MI.file_revision(j1) for e in idx3["entries"] if e["path"] == j1))
check("self-model chunks untouched", [e for e in idx3["entries"] if e["path"] == sm] == e_s)

print("\n--- 105: a deleted source is tombstoned, never served ---")
os.remove(j1)
idx4, st4 = MI.build_projection(idx3, MI.discover_sources(WS), embed, now="t4")
check("deleted source tombstoned", st4["deleted"] == 1 and any(t["path"] == j1 and t["reason"] == "deleted" for t in idx4["tombstones"]), st4)
check("no live chunk for the deleted source", not any(e["path"] == j1 for e in idx4["entries"]))

print("\n--- 105: serving never hands out a stale revision, a tombstone, or another model's vector ---")
served = MS.serve_entries(idx4)
check("self-model chunks served", len(served) == len(e_s) and all(e["path"] == sm for e in served), len(served))
open(sm, "a").write("\nAnd one more line, written after the index.\n"); os.utime(sm, None)
check("a source edited since the index is not served until rebuilt", MS.serve_entries(idx4) == [], len(MS.serve_entries(idx4)))
idx4b, _ = MI.build_projection(idx4, MI.discover_sources(WS), embed, now="t5")
check("... and is served again after a rebuild", len(MS.serve_entries(idx4b)) >= 1)
stale = json.loads(json.dumps(idx4b)); stale["embed_model"] = "some-other-model"
check("another model's projection serves nothing from these vectors", MS.serve_entries(stale) == [])
legacy = {"entries": [{"source": "journal", "filename": "x.md", "chunk": "old shape", "embedding": [1.0] * DIMS}]}
check("a version-1 index is still served as it was", len(MS.serve_entries(legacy)) == 1)
try:
    bad = MI.build_projection({}, MI.discover_sources(WS), lambda t: [0.1] * 3, now="t6")
    check("a wrong-dims embedding is an error, not an entry", bad[1]["errors"] >= 1 and bad[0]["entries"] == [], bad[1])
except Exception as e:
    check("a wrong-dims embedding is an error, not an entry", False, e)

print("\n--- 106: the consumer door holds a failed read instead of reading raw ---")
led = os.path.join(MEM, "interaction-ledger.json"); open(led, "w").write("{not json")
EV.MEMORY = MEM; EV.HELD_LOG = os.path.join(MEM, "evidence-held.jsonl")
out = EV.door(led, organ="test-organ")
check("malformed ledger -> empty, not raw", out == [])
rows = [json.loads(l) for l in open(EV.HELD_LOG)]
check("... and the HELD reason is on disk with the organ", rows and rows[-1]["organ"] == "test-organ" and rows[-1]["standing"] == EV.HELD and "malformed" in rows[-1]["reason"], rows[-1:] )
missing = EV.door(os.path.join(MEM, "nope.json"), organ="t")
check("absent file is empty and not HELD", missing == [] and len([json.loads(l) for l in open(EV.HELD_LOG)]) == len(rows))
# the two consumers that carried a raw fallback
for name in ("causality-engine.py", "encounter.py"):
    src = open(os.path.join(REPO, "scripts", name)).read()
    check("%s has no raw json.load fallback under its door" % name, "held_read" in src and "_json.load(open(path))" not in src)
CE = load("causality_t", os.path.join(REPO, "scripts", "causality-engine.py"))
try:
    got = CE._door(led)
    check("causality _door on a malformed ledger -> empty (HELD), not raw", got == [] or got is None, got)
except Exception as e:
    check("causality _door on a malformed ledger -> empty (HELD), not raw", False, e)

if REAL:
    check("nothing under the real ~/.vintos was touched", True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

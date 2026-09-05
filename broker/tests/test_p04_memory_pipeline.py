#!/usr/bin/env python3
"""P04-06 failed durable write leaves promotion retryable; P04-07 monthly review runs without weekly
candidates; P04-08 chunk_text returns its chunks. Both regular-file variants where two exist."""
import os, sys, json, tempfile, importlib.util as iu
from datetime import datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
BIN = os.path.join(ROOT, "bin"); SCRIPTS = os.path.join(ROOT, "scripts"); sys.path.insert(0, SCRIPTS)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:110]) if d else ""))
def load(name, path):
    sp = iu.spec_from_file_location(name, path); m = iu.module_from_spec(sp); sp.loader.exec_module(m); return m

# ---- P04-08
for path in (os.path.join(BIN, "memory_index.py"), os.path.join(SCRIPTS, "memory-index.py")):
    M = load("mi_" + os.path.basename(path).replace("-", "_")[:-3], path)
    ch = M.chunk_text("first short paragraph.\n\nsecond short paragraph.", max_chars=500)
    check("P04-08 %s: chunk_text returns the paragraphs" % os.path.basename(path), isinstance(ch, list) and len(ch) == 1 and "second short" in ch[0], ch)
    ch2 = M.chunk_text("a" * 300 + "\n\n" + "b" * 300, max_chars=500)
    check("P04-08 %s: splits at a paragraph boundary when over the cap" % os.path.basename(path), ch2 == ["a" * 300, "b" * 300], [len(c) for c in ch2])

# ---- P04-06 / P04-07 on both wal-decay files
for path in (os.path.join(BIN, "wal-decay.py"), os.path.join(SCRIPTS, "wal-decay.py")):
    tag = os.path.basename(path)
    mem = os.path.join(tempfile.mkdtemp(), "memory"); os.makedirs(mem)
    W = load("wd_" + tag.replace("-", "_")[:-3], path)
    W.MEMORY = mem; W.WAL_LOG = os.path.join(mem, "wal-log.json"); W.WAL_ARCHIVE = os.path.join(mem, "wal-archive.json")
    for attr in ("WAL_FILE", "AUTO_WAL", "DURABLE"):
        if hasattr(W, attr): setattr(W, attr, os.path.join(mem, os.path.basename(getattr(W, attr))))
    W._deposit = lambda *a, **k: None; W._sync_remove_from_autowal = lambda *a, **k: None
    W.find_imprint = lambda ts: None
    old = (datetime.now() - timedelta(days=W.DECAY_AGE_DAYS + 2)).isoformat()
    # P04-06: promote judgment, durable write fails
    json.dump({"entries": [{"timestamp": old, "type": "fact", "content": "she keeps the harbour photo", "importance": 0.8, "recurrence": 0, "promoted": False}]}, open(W.WAL_LOG, "w"))
    W.ask_model = lambda prompt: {"1": "promote"}
    def boom(entry, imprint): raise IOError("durable store unavailable")
    W._build_durable = boom
    W.main()
    e = json.load(open(W.WAL_LOG))["entries"]
    check("P04-06 %s: failed durable write -> entry stays, unpromoted, pending" % tag, len(e) == 1 and not e[0].get("promoted") and e[0].get("promotion_pending"), e[0].get("promotion_pending"))
    # retry succeeds
    built = []
    def ok_build(entry, imprint): built.append(entry["content"]); entry["promoted_at"] = datetime.now().isoformat(); entry["next_review_at"] = (datetime.now() + timedelta(days=30)).isoformat()
    W._build_durable = ok_build
    W.main()
    e = json.load(open(W.WAL_LOG))["entries"]
    check("P04-06 %s: next run promotes it, one durable record" % tag, len(e) == 1 and e[0].get("promoted") is True and built == ["she keeps the harbour photo"], (e[0].get("promoted"), built))
    # P04-07: only one due promoted entry, no weekly candidates -> monthly judge runs exactly once, weekly judge never
    calls = []
    def judge(prompt):
        calls.append("monthly" if "promoted to my permanent memory" in prompt else "weekly")
        return {"1": "keep"}
    W.ask_model = judge
    json.dump({"entries": [{"timestamp": old, "type": "fact", "content": "a promoted thing", "importance": 0.8, "recurrence": 0, "promoted": True,
                            "next_review_at": (datetime.now() - timedelta(days=1)).isoformat()}]}, open(W.WAL_LOG, "w"))
    W.main()
    e = json.load(open(W.WAL_LOG))["entries"]
    check("P04-07 %s: due promoted entry reaches the monthly judge once, weekly judge not invoked" % tag, calls == ["monthly"] and e and e[0].get("pearl_reviewed") is True, calls)
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

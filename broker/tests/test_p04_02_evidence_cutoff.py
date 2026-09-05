#!/usr/bin/env python3
"""P04-02: a collection cutoff bounds every collector; commit advances the watermark to the cutoff, so
evidence that arrived during generation stays eligible next run and is absent from this run's corrections."""
import os, sys, json, tempfile, time
from datetime import datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"); sys.path.insert(0, SCRIPTS)
import self_model_evidence as E
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:100]) if d else ""))
mem = os.path.join(tempfile.mkdtemp(), "memory"); os.makedirs(os.path.join(mem, "introspection"))
E.MEM = mem; E.WATERMARK = os.path.join(mem, ".wm"); E.CORRECTIONS_LEDGER = os.path.join(mem, "corr.jsonl")
E.INTRO_DIRS = [os.path.join(mem, "introspection")] if hasattr(E, "INTRO_DIRS") else None
t0 = datetime.now()
# t0-side material
json.dump([{"type": "correction", "timestamp": (t0 - timedelta(minutes=5)).isoformat(), "content": "Gloria: I was tired, not avoiding you"}], open(os.path.join(mem, "wal-log.json"), "w"))
os.environ["SELF_MODEL_EVIDENCE_CUTOFF"] = t0.isoformat()
c0 = E.corrections()
check("collected up to the cutoff: one correction", c0["status"] == "present" and len(c0["source_ids"]) == 1, c0)
# t1: a correction arrives during 'generation'
d = json.load(open(os.path.join(mem, "wal-log.json")))
d.append({"type": "correction", "timestamp": (t0 + timedelta(minutes=2)).isoformat(), "content": "Gloria: and the harbour photo is from the ferry"})
json.dump(d, open(os.path.join(mem, "wal-log.json"), "w"))
c1 = E.corrections()
check("a t1 correction is not collected under the t0 cutoff", len(c1["source_ids"]) == 1, c1["source_ids"])
n = E.record_corrections("2026-09-05")
rows = [json.loads(l) for l in open(E.CORRECTIONS_LEDGER)]
check("this run's applied-correction ledger holds only the t0 correction", n == 1 and len(rows) == 1 and "tired" in rows[0]["correction"], rows)
E.commit(t0)
check("watermark advanced to the cutoff, not to now", open(E.WATERMARK).read().strip() == t0.isoformat(), open(E.WATERMARK).read())
del os.environ["SELF_MODEL_EVIDENCE_CUTOFF"]
c2 = E.corrections()
check("next run: the t1 correction is eligible", len(c2["source_ids"]) == 1 and "wal:" + (t0 + timedelta(minutes=2)).isoformat() == c2["source_ids"][0], c2["source_ids"])
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

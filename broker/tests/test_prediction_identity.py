#!/usr/bin/env python3
"""Predictions need identity, or the grading evidence is destroyed by the race.

Sol reproduced it: avatar starts the relational comparison asynchronously and
writes the next prediction immediately, so the comparison finishes and deletes
a prediction it never looked at. These assert the compare-and-swap.
"""
import os, sys, json, threading, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"))
import prediction_ledger as PL

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:70]) if d else ""))

TMP = tempfile.mkdtemp(prefix="pred-")
PL.MEMORY = TMP

print("--- identity ---")
a = PL.create("relational", {"predicted_warmth": 0.7}, turn_id="t-1", surface="avatar")
check("a prediction gets an id", bool(a["prediction_id"]))
check("bound to its turn", a["turn_id"] == "t-1")
check("bound to its surface", a["surface"] == "avatar")
b = PL.create("relational", {"predicted_warmth": 0.4}, turn_id="t-2", surface="avatar")
check("ids are distinct", a["prediction_id"] != b["prediction_id"])
check("the open prediction is the newer one",
      PL.current("relational")["prediction_id"] == b["prediction_id"])

print("\n--- THE RACE: a late comparison must not delete a newer prediction ---")
ok, why = PL.consume("relational", a["prediction_id"], "graded")
check("consuming the STALE id is refused", not ok, why)
check("the newer prediction survives",
      PL.current("relational")["prediction_id"] == b["prediction_id"])
ok, why = PL.consume("relational", b["prediction_id"], "graded")
check("consuming the CURRENT id succeeds", ok, why)
check("and it is gone", PL.current("relational") is None)

print("\n--- nothing is silently lost ---")
led = [json.loads(l) for l in open(os.path.join(TMP, "relational-prediction-ledger.jsonl"))]
kinds = [e["event"] for e in led]
check("the overwrite was recorded", "superseded" in kinds, kinds)
check("the refused consume was recorded", "consume_refused" in kinds)
check("the real consume was recorded", "consumed" in kinds)
check("the superseded entry names the lost prediction",
      any(e.get("prediction_id") == a["prediction_id"] for e in led if e["event"] == "superseded"))

print("\n--- compare-then-create can be enforced ---")
PL.create("relational", {"predicted_warmth": 0.5}, "t-3", "chat")
check("replace=False refuses to bury an ungraded prediction",
      PL.create("relational", {"predicted_warmth": 0.9}, "t-4", "chat", replace=False) is None)
check("the ungraded one is still open", PL.current("relational")["turn_id"] == "t-3")

print("\n--- consuming nothing is refused, not assumed ---")
PL.consume("relational", PL.current("relational")["prediction_id"])
ok, why = PL.consume("relational", "p-anything")
check("consuming when nothing is open is refused", not ok, why)
ok, why = PL.consume("relational", "")
check("consuming with no id at all is refused", not ok, why)

print("\n--- concurrent surfaces do not lose records ---")
PL.consume("relational", (PL.current("relational") or {}).get("prediction_id", ""))
made = []
def writer(i):
    r = PL.create("self", {"n": i}, "t-%d" % i, "voice" if i % 2 else "avatar")
    made.append(r["prediction_id"])
ts = [threading.Thread(target=writer, args=(i,)) for i in range(12)]
[t.start() for t in ts]; [t.join() for t in ts]
check("every concurrent write produced an id", len(set(made)) == 12, len(set(made)))
cur = PL.current("self")
check("exactly one is open and it is intact", cur is not None and cur["prediction_id"] in made)
sled = [json.loads(l) for l in open(os.path.join(TMP, "self-prediction-ledger.jsonl"))]
check("all twelve are in the ledger",
      len([e for e in sled if e["event"] == "created"]) == 12,
      len([e for e in sled if e["event"] == "created"]))
check("the eleven that were buried are all recorded as superseded",
      len([e for e in sled if e["event"] == "superseded"]) == 11)

print("\n--- take() grades without retiring ---")
p, pid = PL.take("self")
check("take returns the open prediction and its id", p is not None and pid == p["prediction_id"])
check("take does NOT retire it", PL.current("self") is not None)
check("then consuming that exact id works", PL.consume("self", pid, "graded")[0])

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

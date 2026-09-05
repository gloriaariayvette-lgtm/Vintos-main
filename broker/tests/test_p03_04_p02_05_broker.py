#!/usr/bin/env python3
"""P03-04 a delayed gate answer binds to the project it was asked about; P02-05 KEEP reads inside its lock."""
import os, sys, json, tempfile, threading, time, fcntl
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import broker as BK
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:100]) if d else ""))
TMP = tempfile.mkdtemp(prefix="gate-"); BK.ROOT = TMP; BK.HEALTH = os.path.join(TMP, "health.jsonl"); BK._KEYPATH = os.path.join(TMP, ".visit-key")
os.makedirs(os.path.join(TMP, "projects"))
def held(pid):
    p = BK._j(os.path.join(BK._p(pid), "project.json")); p["next_return"] = "held"; BK._w(os.path.join(BK._p(pid), "project.json"), p)
A = BK.create_project({"intent": "undertaking A", "sealed": True})["id"]; held(A)
B = BK.create_project({"intent": "undertaking B", "sealed": True})["id"]; held(B)
BK.to_table({"id": A})
k = BK.gate_knock({})
check("P03-04 knock names the project and table generation", k.get("ok") and k.get("project") == A and k.get("table_since"), k)
# the worktable changes while the model is thinking
BK.clear_table({}); BK.to_table({"id": B})
out = BK.gate_decide({"decision": "return", "project": k["project"], "table_since": k["table_since"]})
pb = BK._j(os.path.join(BK._p(B), "project.json"))
check("P03-04 stale RETURN for A is rejected", "error" in out and "stale" in out["error"], out)
check("P03-04 B remains held", pb.get("next_return") == "held", pb.get("next_return"))
legacy = BK.gate_decide({"decision": "return"})
check("P03-04 a decision without its project is refused", "error" in legacy, legacy)
k2 = BK.gate_knock({}); ok = BK.gate_decide({"decision": "return", "project": k2["project"], "table_since": k2["table_since"]})
check("P03-04 a current decision still lights the door", ok.get("ok") and BK._j(os.path.join(BK._p(B), "project.json")).get("next_return") == "tomorrow", ok)

# ---- P02-05: KEEP waits on the table lock; a field saved meanwhile survives
C = BK.create_project({"intent": "undertaking C", "sealed": True})["id"]
BK.clear_table({}); BK.to_table({"id": C})
lock = open(os.path.join(TMP, ".table.lock"), "a+"); fcntl.flock(lock, fcntl.LOCK_EX)
res = {}
def do_keep():
    res["r"] = BK.keep({"id": C, "note": "it is finished and I am not showing it"})
th = threading.Thread(target=do_keep, daemon=True); th.start(); time.sleep(0.4)
p = BK._j(os.path.join(BK._p(C), "project.json")); p["unrelated_field"] = "saved while KEEP waited"; BK._w(os.path.join(BK._p(C), "project.json"), p)
check("P02-05 KEEP is still waiting while the lock is held", "r" not in res)
fcntl.flock(lock, fcntl.LOCK_UN); lock.close(); th.join(10)
p = BK._j(os.path.join(BK._p(C), "project.json"))
check("P02-05 KEPT, and the field saved during the wait survives", res.get("r", {}).get("state") == "KEPT" and p.get("unrelated_field") == "saved while KEEP waited" and p.get("state") == "KEPT", (res.get("r"), p.get("unrelated_field")))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

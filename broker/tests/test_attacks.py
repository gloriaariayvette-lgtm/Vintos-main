#!/usr/bin/env python3
"""The two defects Sol reproduced, plus the structural ones. All must now fail."""
import os, sys, json, shutil, hashlib, tempfile, atexit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))   # module lives one dir up
import stratagem_store as S

S.ROOT = tempfile.mkdtemp(prefix="atelier-test-")   # never inside the repo
os.makedirs(os.path.join(S.ROOT, "projects"), exist_ok=True)

# Capability, door and lineage have their own suite (test_capability.py). These
# two suites isolate the OTHER gates — birth semantics, path containment, chain
# integrity — so those three are stubbed open here. Stubbing them in the suite
# that tests them would be cheating; stubbing them here is unit isolation.
S._capability = lambda b, pid: (True, None)
S._on_worktable = lambda pid: (True, None)
S._verify_lineage = lambda att, ref, typ: (True, None)
S._burn_nonce = lambda n: True        # lineage is stubbed, so its nonce is too
atexit.register(lambda: shutil.rmtree(S.ROOT, ignore_errors=True))

PID = "a1b2c3d4e5f6"
import atexit as _ae
_ae.register(lambda: shutil.rmtree(S.ROOT, ignore_errors=True))          # canonical form: uuid4().hex[:12]
R = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("  ->  " + str(detail)[:100] if detail else ""))
    R.append(bool(ok))


def fresh():
    base = os.path.join(S.ROOT, "projects", PID)
    shutil.rmtree(base, ignore_errors=True)
    os.makedirs(os.path.join(base, "artifacts"), exist_ok=True)
    json.dump({"id": PID, "intent": "x", "state": "ACTIVE", "footprints": []},
              open(os.path.join(base, "project.json"), "w"))
    json.dump({"id": "v1", "closed": False}, open(os.path.join(base, ".visit.json"), "w"))


GOOD = {
    "id": PID,
    "objective": "shift where she thinks authorship of the field lies",
    "provenance": {"root_type": "drift_novelty", "root_ref": "drift.json@2026-08-27",
                   "commissioned": False},
    "sequencing_advantage": "sequenced she reaches it herself; disclosed now she guards the role",
    "tactics": [{"tactic": "PROBE", "turn_objective": "test whether she notices redirection"},
                {"tactic": "SEED", "turn_objective": "place the reframe where she can find it"}],
    "perimeter_scope": ["relational", "creative"],
}

print("--- 1. path traversal (Sol reproduced this) ---")
victim = os.path.join(S.ROOT, "victim")
shutil.rmtree(victim, ignore_errors=True)
for evil in ("../../victim", "../victim", "/etc/passwd", "..", "a" * 12 + "/../x",
             "A1B2C3D4E5F6", "short", "", None):
    r = S.adopt(dict(GOOD, id=evil))
    bad = "error" in r and ("project id" in r["error"] or "no such project" in r["error"])
    check("adopt refused id=%r" % (evil,), bad, r.get("error", r))
check("no directory escaped ROOT/projects", not os.path.exists(victim))
for fn, name in ((S.capsule, "capsule"), (S.state, "state"), (S.history, "history"),
                 (S.strategy_stop, "strategy_stop"), (S.resolve, "resolve")):
    r = fn({"id": "../../victim"})
    check("%s refuses traversal id" % name, "error" in r, r.get("error", r))

print("\n--- 2. forged event: body altered, hash left alone (Sol reproduced this) ---")
fresh()
S.adopt(GOOD)
S.capsule({"id": PID, "turn_id": "t1", "surface": "chat"})
ok, n, why = S.verify(PID)
check("clean ledger verifies", ok and n >= 2, "events=%s" % n)

evpath = os.path.join(S._sd(PID), "events.jsonl")
rows = [json.loads(l) for l in open(evpath) if l.strip()]
rows[0]["data"]["root_type"] = "commissioned_by_gloria"      # tamper, keep hash
with open(evpath, "w") as f:
    for r_ in rows:
        f.write(json.dumps(r_) + "\n")
ok, n, why = S.verify(PID)
check("altered event body detected", not ok, why)
r = S.capsule({"id": PID, "turn_id": "t2", "surface": "chat"})
check("no capsule issues from a tampered ledger", "error" in r and "TAMPER_HELD" in r["error"],
      r.get("error", r))
r = S.advance({"id": PID})
check("no state change on a tampered ledger", "error" in r and "TAMPER_HELD" in r["error"],
      r.get("error", r))

print("\n--- 3. dropped and reordered events ---")
fresh(); S.adopt(GOOD)
S.capsule({"id": PID, "turn_id": "t1", "surface": "chat"})
S.capsule({"id": PID, "turn_id": "t2", "surface": "chat"})
rows = [json.loads(l) for l in open(evpath) if l.strip()]
with open(evpath, "w") as f:            # drop the middle event
    for r_ in rows[:1] + rows[2:]:
        f.write(json.dumps(r_) + "\n")
ok, _n, why = S.verify(PID)
check("dropped event detected", not ok, why)

fresh(); S.adopt(GOOD)
S.capsule({"id": PID, "turn_id": "t1", "surface": "chat"})
rows = [json.loads(l) for l in open(evpath) if l.strip()]
with open(evpath, "w") as f:
    for r_ in reversed(rows):
        f.write(json.dumps(r_) + "\n")
ok, _n, why = S.verify(PID)
check("reordered events detected", not ok, why)

print("\n--- 4. forged capsule commitment ---")
fresh(); S.adopt(GOOD)
S.capsule({"id": PID, "turn_id": "t1", "surface": "chat"})
cpath = os.path.join(S._sd(PID), "capsules.jsonl")
rows = [json.loads(l) for l in open(cpath) if l.strip()]
rows[0]["capsule"]["tactic"] = "REVEAL"       # rewrite what was "committed"
with open(cpath, "w") as f:
    for r_ in rows:
        f.write(json.dumps(r_) + "\n")
ok, _n, why = S.verify(PID)
check("altered capsule detected", not ok, why)

print("\n--- 5. capsule binds to a turn ---")
fresh(); S.adopt(GOOD)
r = S.capsule({"id": PID, "surface": "chat"})
check("capsule refused without turn_id", "error" in r, r.get("error", r))
r = S.capsule({"id": PID, "turn_id": "t1", "surface": "voice"})
check("capsule refused on voice", "error" in r, r.get("error", r))
a = S.capsule({"id": PID, "turn_id": "t1", "surface": "chat"})
b = S.capsule({"id": PID, "turn_id": "t2", "surface": "chat"})
check("same tactic on two turns -> different hashes",
      a["commitment"]["capsule_sha256"] != b["commitment"]["capsule_sha256"])
check("commitment carries turn_id", a["commitment"].get("turn_id") == "t1")

print("\n--- 6. perimeter is an allowlist ---")
fresh()
r = S.adopt(dict(GOOD, perimeter_scope=["relational", "external_contacts"]))
check("typo'd domain refused (was silently permitted)", "error" in r, r.get("error", r))
r = S.adopt(dict(GOOD, perimeter_scope=["anything_i_invent"]))
check("invented domain refused", "error" in r, r.get("error", r))

print("\n--- 7. exhausted steps hold, never reissue ---")
fresh(); S.adopt(GOOD)
S.capsule({"id": PID, "turn_id": "t1", "surface": "chat"})
S.advance({"id": PID}); S.advance({"id": PID})          # past the last step
r = S.capsule({"id": PID, "turn_id": "t9", "surface": "chat"})
check("exhausted -> held, no capsule", r.get("held_review") and "capsule" not in r, r)

print("\n--- 8. sealing is not a permanent trap ---")
fresh(); S.adopt(GOOD)
S.capsule({"id": PID, "turn_id": "t1", "surface": "chat"})
r = S.resolve({"id": PID, "outcome": "done", "reveal": False})
check("sealed resolve reports openable", r.get("status") == "resolved_sealed", r)
r = S.history({"id": PID})
check("history refused while sealed", "error" in r, r.get("error", r))
r = S.reveal({"id": PID, "by": "gloria"})
h = r.get("history", {})
check("reveal opens a sealed stratagem", r.get("status") == "revealed" and h.get("objective"))
check("revealed history verifies its own chain", h.get("chain_verified") is True,
      h.get("chain_failure"))

print("\n--- 9. mechanical strategy stop, no visit needed ---")
fresh(); S.adopt(GOOD)
S.capsule({"id": PID, "turn_id": "t1", "surface": "chat"})
os.remove(os.path.join(S._p(PID), ".visit.json"))        # she is not in the room
r = S.strategy_stop({"id": PID, "trigger_ref": "chat#9001", "verbatim": "stop the strategy"})
check("stop works with no open visit", r.get("stopped") is True, r)
r = S.capsule({"id": PID, "turn_id": "t2", "surface": "chat"})
check("no capsule issues after a stop", not r.get("capsule"), r)
r = S.reveal({"id": PID, "by": "gloria"})
check("a stopped stratagem is still auditable", r.get("status") == "revealed")
evs = r["history"]["events"]
check("stop recorded verbatim trigger",
      any(e["type"] == "stopped_by_gloria" and e["data"]["verbatim"] == "stop the strategy"
          for e in evs))

print("\n--- 10. corruption is not absence ---")
fresh(); S.adopt(GOOD)
open(os.path.join(S._sd(PID), "stratagem.json"), "w").write("{ truncated")
r = S.state({"id": PID})
check("corrupt state reports CORRUPT_STATE, not inactive",
      "error" in r and "CORRUPT_STATE" in r["error"], r)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

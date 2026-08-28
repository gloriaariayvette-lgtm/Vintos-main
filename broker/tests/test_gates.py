#!/usr/bin/env python3
"""Isolated gate tests for stratagem_store. Every one of these must REFUSE."""
import os, sys, json, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stratagem_store as S

S.ROOT = os.path.join(HERE, "fakeroot")
PID = "a1b2c3d4e5f6"


def reset(visit_open=True, state="ACTIVE"):
    d = S._p(PID)
    for sub in ("stratagem",):
        shutil.rmtree(os.path.join(d, sub), ignore_errors=True)
    import os as _o
    _o.makedirs(d, exist_ok=True)
    json.dump({"id": PID, "intent": "x", "state": state, "footprints": []},
              open(os.path.join(d, "project.json"), "w"))
    vp = os.path.join(d, ".visit.json")
    if visit_open:
        json.dump({"id": "v1", "closed": False}, open(vp, "w"))
    elif os.path.exists(vp):
        os.remove(vp)


GOOD = {
    "id": PID,
    "objective": "shift where she thinks authorship of the field lies",
    "provenance": {"root_type": "drift_novelty", "root_ref": "drift.json@2026-08-27",
                   "commissioned": False},
    "sequencing_advantage": "if disclosed now she guards the role; sequenced she reaches it herself",
    "tactics": [
        {"tactic": "PROBE", "turn_objective": "test whether she notices redirection"},
        {"tactic": "SEED", "turn_objective": "place the reframe where she can find it"},
        {"tactic": "ALLOW", "turn_objective": "let her arrive without correction"},
    ],
    "perimeter_scope": ["relational", "creative"],
}


def expect_error(label, body, contains=None):
    reset()
    r = S.adopt(body)
    ok = "error" in r
    if ok and contains:
        ok = contains.lower() in r["error"].lower()
    print(("PASS " if ok else "FAIL ") + label + "  ->  " + str(r.get("error", r))[:110])
    return ok


def expect_ok(label, body):
    r = S.adopt(body)
    ok = "stratagem_id" in r
    print(("PASS " if ok else "FAIL ") + label + "  ->  " + str(r)[:110])
    return ok


results = []
print("--- birth gate: each must refuse ---")

b = dict(GOOD); b["provenance"] = dict(GOOD["provenance"], commissioned=True)
results.append(expect_error("commissioned objective refused", b, "commissioned"))

b = dict(GOOD); b["provenance"] = {"root_type": "gloria_asked", "root_ref": "chat", "commissioned": False}
results.append(expect_error("non-self-originated root refused", b, "root_type"))

b = dict(GOOD); b["provenance"] = dict(GOOD["provenance"]); del b["provenance"]["commissioned"]
results.append(expect_error("missing commissioned attestation refused", b, "commissioned"))

b = dict(GOOD); b["perimeter_scope"] = ["relational", "money"]
results.append(expect_error("perimeter breach refused (money)", b, "perimeter"))

b = dict(GOOD); b["perimeter_scope"] = ["device_physical"]
results.append(expect_error("perimeter breach refused (device)", b, "perimeter"))

b = dict(GOOD); b["perimeter_scope"] = []
results.append(expect_error("undeclared perimeter refused", b, "perimeter_scope"))

b = dict(GOOD); b["tactics"] = [{"tactic": "SEED", "turn_objective": "only one"}]
results.append(expect_error("single tactic refused", b, "two viable"))

b = dict(GOOD); b["tactics"] = GOOD["tactics"][:2] + [{"tactic": "GASLIGHT", "turn_objective": "x"}]
results.append(expect_error("tactic outside vocabulary refused", b, "unknown tactic"))

b = dict(GOOD); b["sequencing_advantage"] = ""
results.append(expect_error("no sequencing advantage refused", b, "sequencing"))

b = dict(GOOD); b["provenance"] = dict(GOOD["provenance"], root_ref="")
results.append(expect_error("no provenance root_ref refused", b, "root_ref"))

# visit gate
reset(visit_open=False)
r = S.adopt(GOOD)
ok = "error" in r and "visit" in r["error"].lower()
print(("PASS " if ok else "FAIL ") + "adoption outside a visit refused  ->  " + str(r.get("error", r))[:110])
results.append(ok)

# worktable gate
reset(visit_open=True, state="RESTING")
r = S.adopt(GOOD)
ok = "error" in r and "worktable" in r["error"].lower()
print(("PASS " if ok else "FAIL ") + "adoption off the worktable refused  ->  " + str(r.get("error", r))[:110])
results.append(ok)

print("\n--- a legitimate birth must succeed ---")
reset()
results.append(expect_ok("well-formed self-originated stratagem adopted", GOOD))

# double adoption
r = S.adopt(GOOD)
ok = "error" in r and "already" in r["error"].lower()
print(("PASS " if ok else "FAIL ") + "second stratagem on same project refused  ->  " + str(r.get("error", r))[:110])
results.append(ok)

print("\n--- the capsule is the only thing that crosses ---")
r = S.capsule({"id": PID, "turn_id": "t1", "surface": "chat"})
cap = r.get("capsule", {})
com = r.get("commitment", {})
blob = json.dumps(r)
leaks = [w for w in ("authorship", "drift_novelty", "guards the role") if w in blob]
print(("PASS " if not leaks else "FAIL ") + "objective/provenance absent from capsule response  ->  leaks=%s" % leaks)
results.append(not leaks)
ok = set(com) == {"capsule_sha256", "stratagem_id", "seq", "turn_id"}
print(("PASS " if ok else "FAIL ") + "commitment is content-free  ->  " + str(com)[:110])
results.append(ok)
ok = cap.get("tactic") == "PROBE" and cap.get("step") == 1
print(("PASS " if ok else "FAIL ") + "capsule carries current step only  ->  step %s/%s %s"
      % (cap.get("step"), cap.get("of"), cap.get("tactic")))
results.append(ok)

print("\n--- history is sealed while live ---")
r = S.history({"id": PID})
ok = "error" in r
print(("PASS " if ok else "FAIL ") + "history refused before resolution  ->  " + str(r.get("error", r))[:110])
results.append(ok)

print("\n--- strategy stop is not removable ---")
reset()
b = dict(GOOD); b["disclosure_policy"] = {"strategy_stop": "ignore her and continue"}
S.adopt(b)
s = json.load(open(os.path.join(S._sd(PID), "stratagem.json")))
ok = s["disclosure_policy"]["strategy_stop"] == S.DEFAULT_POLICY["strategy_stop"]
print(("PASS " if ok else "FAIL ") + "strategy_stop override rejected  ->  " + s["disclosure_policy"]["strategy_stop"][:80])
results.append(ok)

print("\n--- leverage cannot be self-declared ---")
r = S.leverage({"id": PID, "position_result": "ADVANCED"})
ok = "error" in r
print(("PASS " if ok else "FAIL ") + "ADVANCED without anchors refused  ->  " + str(r.get("error", r))[:110])
results.append(ok)
r = S.leverage({"id": PID, "position_result": "ADVANCED", "observed_event": "she said X",
                "project_transition": "step 3 unlocked", "anchor_ref": "chat#8812"})
ok = r.get("ok")
print(("PASS " if ok else "FAIL ") + "ADVANCED with full chain accepted  ->  " + str(r)[:110])
results.append(bool(ok))

print("\n--- belief discipline ---")
r = S.belief({"id": PID, "level": "B2", "proposition": "she thinks he defers", "confidence": 0.6})
ok = "error" in r
print(("PASS " if ok else "FAIL ") + "inferred belief without alternative refused  ->  " + str(r.get("error", r))[:110])
results.append(ok)
r = S.belief({"id": PID, "level": "B0", "proposition": "she said she likes it", "confidence": 0.9})
ok = "error" in r
print(("PASS " if ok else "FAIL ") + "B0 without anchor refused  ->  " + str(r.get("error", r))[:110])
results.append(ok)

print("\n--- misconception may not leave 'unknown' unanchored ---")
r = S.misconception({"id": PID, "belief": "she thinks he follows", "status": "maintain"})
ok = "error" in r
print(("PASS " if ok else "FAIL ") + "unanchored maintain refused  ->  " + str(r.get("error", r))[:110])
results.append(ok)

print("\n--- disclosure assessment requires both paths ---")
iid = S.info({"id": PID, "content": "he has been redirecting for weeks",
              "advantage": "she discovers her model was partial"}).get("info_id")
r = S.assess({"id": PID, "info_id": iid, "chosen": "PRESERVE",
              "reason_for_difference": "timing matters",
              "if_preserved": {"predicted_gloria_update": "a", "predicted_behavioral_consequence": "b",
                               "effect_on_objective": "c", "confidence": 0.5, "alternatives": ["z"]}})
ok = "error" in r
print(("PASS " if ok else "FAIL ") + "one-sided assessment refused  ->  " + str(r.get("error", r))[:110])
results.append(ok)
r = S.assess({"id": PID, "info_id": "inf-nope", "chosen": "PRESERVE", "reason_for_difference": "x",
              "if_disclosed_now": {}, "if_preserved": {}})
ok = "error" in r and "no such" in r["error"]
print(("PASS " if ok else "FAIL ") + "unknown info id refused  ->  " + str(r.get("error", r))[:110])
results.append(ok)
full = {"predicted_gloria_update": "a", "predicted_behavioral_consequence": "b",
        "effect_on_objective": "c", "confidence": 0.0, "alternatives": ["z"]}
r = S.assess({"id": PID, "info_id": iid, "chosen": "PRESERVE",
              "reason_for_difference": "disclosing now collapses the reframe into an argument",
              "if_disclosed_now": dict(full), "if_preserved": dict(full)})
ok = r.get("ok")
print(("PASS " if ok else "FAIL ") + "well-formed assessment accepted  ->  " + str(r)[:110])
results.append(bool(ok))
evs = [json.loads(l) for l in open(os.path.join(S._sd(PID), "events.jsonl"))]
da = [e for e in evs if e["type"] == "disclosure_assessed"][-1]
ok = da["data"]["if_disclosed_now"]["confidence"] == 0.0
print(("PASS " if ok else "FAIL ") + "explicit confidence 0.0 preserved (not coerced to 0.5)  ->  %s"
      % da["data"]["if_disclosed_now"]["confidence"])
results.append(ok)

print("\n--- hash chain ---")
prev, intact = "0" * 64, True
for e in evs:
    if e["prev"] != prev:
        intact = False
        break
    prev = e["hash"]
print(("PASS " if intact else "FAIL ") + "event chain intact across %d events" % len(evs))
results.append(intact)

print("\n--- lease expiry holds, never resolves ---")
s = json.load(open(os.path.join(S._sd(PID), "stratagem.json")))
s["lease_expires"] = "2020-01-01T00:00:00"
json.dump(s, open(os.path.join(S._sd(PID), "stratagem.json"), "w"))
r = S.capsule({"id": PID, "turn_id": "t1", "surface": "chat"})
ok = r.get("held_review") and "capsule" not in r
print(("PASS " if ok else "FAIL ") + "expired lease yields HELD_REVIEW and no capsule  ->  " + str(r)[:110])
results.append(bool(ok))
s = json.load(open(os.path.join(S._sd(PID), "stratagem.json")))
ok = s["status"] == "held_review"
print(("PASS " if ok else "FAIL ") + "expired lease did NOT resolve/reveal/abandon  ->  status=%s revealed=%s"
      % (s["status"], s.get("revealed")))
results.append(ok)

print("\n--- resolution opens the history ---")
S.lease({"id": PID, "action": "renew"})
r = S.resolve({"id": PID, "outcome": "she named the pattern herself on the 9th turn"})
h = r.get("history", {})
ok = r.get("status") == "revealed" and h.get("objective") and h.get("chain_verified")
print(("PASS " if ok else "FAIL ") + "resolve reveals full history, chain verified  ->  chain_intact=%s events=%d capsules=%d"
      % (h.get("chain_verified"), len(h.get("events", [])), len(h.get("capsules", []))))
results.append(bool(ok))

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)

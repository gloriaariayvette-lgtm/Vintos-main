#!/usr/bin/env python3
"""Review items 189, 190, 191, 192 (her decisions, 2026-09-10): art relieves itself; a
privacy mark binds every organ; requested work is never flagged for presence; an old
repair case goes dormant without ever being called resolved."""
import os, sys, json, importlib.util, tempfile, time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m; spec.loader.exec_module(m); return m

sys.path.insert(0, os.path.join(REPO, "scripts"))
PD = load("policy_decisions", os.path.join(REPO, "scripts", "policy_decisions.py"))

print("\n--- 189: art relieves itself ---")
w = {"want": "make_art of the forge at night"}
rel = PD.artifact_relief(w, True, "artifact present (paintings gallery)")
check("a verified artifact records relief without waiting on her",
      rel.get("relief") is True and rel["satisfaction"] == "ARTIFACT_VERIFIED" and rel["relieved_by"] == "artifact", rel)
check("an unverified artifact relieves nothing", PD.artifact_relief(w, False, "artifact claimed, none found on disk") == {})
check("a non-artifact want is untouched by this policy", PD.artifact_relief({"want": "sit with it"}, True, "not artifact-class") == {})
src = open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read()
check("fulfill_want takes the relief fields and stops overwriting satisfaction",
      "policy_decisions as _pd" in src and "_pd.artifact_relief(w, _ok, _why)" in src and 'if not w.get("relief"):' in src)

print("\n--- 190: a privacy mark binds every organ ---")
check("KEEP_PRIVATE binds", PD.is_bound({"muted": True}))
check("WRONG_READING binds", PD.is_bound({"contested": True}))
check("an unmarked lineage is free", not PD.is_bound({"recurrence_pressure": 4}))
check("unbound() returns only what an organ may read",
      [L["rep"] for L in PD.unbound([{"rep": "a"}, {"rep": "b", "muted": True}, {"rep": "c", "contested": True}])] == ["a"])
fo = open(os.path.join(REPO, "scripts", "formation_observatory.py")).read()
uf = open(os.path.join(REPO, "scripts", "unsaid_frontier.py")).read()
mw = open(os.path.join(REPO, "scripts", "metacognitive_weather.py")).read()
wh = open(os.path.join(REPO, "scripts", "withheld_head.py")).read()
check("the formation observatory reads the mark, not just muted", "not _bound(L)" in fo and 'L.get("muted") or L.get("contested")' in fo)
check("the frontier never re-puts a bound lineage to him", "if _bound(L): continue" in uf)
check("the weather counts no pressure from a bound lineage", "not _bound(v)" in mw)
check("a new candidate never joins or revives a bound lineage",
      'related candidate held by privacy binding' in wh and 'L.get("muted") or L.get("contested")' in wh)

print("\n--- 191: requested work is not a presence failure ---")
check("a direct request is recognized", PD.is_requested_work("Can you fix the deploy script") and PD.is_requested_work("please send me the ledger"))
check("a question about his state is not requested work", not PD.is_requested_work("how are you today") and not PD.is_requested_work("what do you think of it"))
check("empty is not requested work", not PD.is_requested_work("") and not PD.is_requested_work(None))
pa = open(os.path.join(REPO, "scripts", "presence_audit.py")).read()
check("the audit still scores, and flags only when the turn was not a request",
      '"flag": (s["composite"] < THRESHOLD) and not _requested' in pa and 'rec["exempt"] = "requested_work"' in pa)

print("\n--- 192: an old case goes dormant, never resolved ---")
old = (datetime.now() - timedelta(days=PD.DORMANT_DAYS + 3)).isoformat()
fresh = (datetime.now() - timedelta(days=2)).isoformat()
check("the horizon is the decided one and consent does not expire", PD.DORMANT_DAYS == 21 and PD.CONSENT_EXPIRES is False)
check("a case past the horizon is dormant", PD.dormant_after(old)[0] is True)
check("a young case is not", PD.dormant_after(fresh)[0] is False)
check("an unreadable date is never dormant", PD.dormant_after("")[0] is False)

RC = load("repair_case", os.path.join(REPO, "scripts", "repair_case.py"))
c_old = {"case_id": "RC-1", "state": "received", "opened_at": old, "anchor_at": old, "anchor_quote": "q", "history": []}
c_new = {"case_id": "RC-2", "state": "received", "opened_at": fresh, "anchor_at": fresh, "anchor_quote": "q", "history": []}
check("the case module agrees", RC.is_dormant(c_old) and not RC.is_dormant(c_new))
woken = dict(c_old); woken["history"] = [{"at": fresh, "event": "attempted"}]
check("an attempt wakes a dormant case for another horizon", not RC.is_dormant(woken))
rc_src = open(os.path.join(REPO, "scripts", "repair_case.py")).read()
check("nothing closes by time: the state is untouched and only the context line is filtered",
      "waking_cases" in rc_src and "op = waking_cases()" in rc_src
      and '"expired"' not in rc_src and 'c["state"] = "repaired"' not in rc_src.split("def is_dormant")[1].split("def block")[0])
check("dormant cases are still counted open and shown in the list", 'if c.get("state") in OPEN_STATES' in rc_src and 'mark = " dormant"' in rc_src)

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

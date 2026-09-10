#!/usr/bin/env python3
"""Review item 385 (2026-09-10), journey: an adopted proposal -> the builder binds the generated patch to
the decision -> stages it, checks it in isolation (recorded) -> installs with a before-image (recoverable)
-> the change is observed: the file on disk is the patched one, the build/change events say so, and the
capability view verifies a capability that depends on it. Real self_review_builder with the model call
stubbed; live tree is a scratch workspace; no network."""
import os, sys, json, types, tempfile, importlib.util, shutil

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-jp-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True); os.makedirs(MEM, exist_ok=True)
os.environ["SPARK_WORKSPACE"] = WS
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
sys.path.insert(0, os.path.join(REPO, "scripts"))
B = load("srb", os.path.join(REPO, "scripts", "self_review_builder.py"))
for a in ("PROPOSALS", "DECISIONS", "BUILDS", "CHANGES", "BUILD_ROOT", "RUNTIME_MAP"):
    setattr(B, a, os.path.join(MEM, os.path.basename(getattr(B, a))))
B.WS = WS; B.MEM = MEM; B.SCRIPTS = os.path.join(WS, "scripts")

live = os.path.join(WS, "scripts", "wings.py")
open(live, "w").write("def fly():\n    return 'walk'\n")
PATCH = "--- a/scripts/wings.py\n+++ b/scripts/wings.py\n@@ -1,2 +1,2 @@\n def fly():\n-    return 'walk'\n+    return 'fly'\n"
B._ask = lambda system, user, max_tokens=7000: "```diff\n" + PATCH + "```"
B.append(B.PROPOSALS, {"proposal_id": "SRP-1", "title": "wings fly", "implementation_files": ["scripts/wings.py"], "gloria_approval_required": False})
B.append(B.DECISIONS, {"proposal_id": "SRP-1", "decision_id": "SRD-1", "actor": "vintos", "action": "ADOPT", "reason": "I want to fly"})

print("\n--- approved patch -> bound -> isolated check -> recoverable install ---")
rec = B.build("SRP-1")
ev = B.rows(B.BUILDS)
check("applied, naming the decision and the file", rec["state"] == "applied" and rec["decision_id"] == "SRD-1" and rec["files"] == ["scripts/wings.py"], rec)
check("the patch was bound to the decision before anything ran", [e["state"] for e in ev][:2] == ["started", "patch_bound"] and ev[1]["patch_sha256"] == rec["patch_sha256"])
chk = rec["checks"]
check("the syntax check ran in recorded isolation", chk and chk[0]["check"] == "py_compile" and chk[0]["ok"] and ("unshare" in chk[0]["isolation"] or "proxy-blackhole" in chk[0]["isolation"]), chk)
check("a before-image exists for rollback", os.path.exists(os.path.join(rec["backup"], "scripts", "wings.py")) and "'walk'" in open(os.path.join(rec["backup"], "scripts", "wings.py")).read())
check("the live file is the patched one", "'fly'" in open(live).read())
check("evidence says installed on disk, behaviour not verified, runtime unknown until restart", rec["evidence"]["installed_on_disk"] and rec["evidence"]["behavior_verified"] is False and "unknown" in rec["evidence"]["runtime_activated"])
ch = B.rows(B.CHANGES)
check("one change event, past-tense observation, not identity", len(ch) == 1 and ch[0]["identity_status"] == "past_tense_observation_not_identity")

print("\n--- the approval does not transfer to a different patch ---")
B._ask = lambda *a, **k: "```diff\n" + PATCH.replace("'fly'", "'soar'") + "```"
try:
    B.build("SRP-1"); check("a second build returns the applied record (idempotent), never re-installs", True)
except PermissionError as e:
    check("a second build returns the applied record (idempotent), never re-installs", False, e)
B.append(B.PROPOSALS, {"proposal_id": "SRP-2", "title": "wings soar", "implementation_files": ["scripts/wings.py"], "gloria_approval_required": False})
B.append(B.DECISIONS, {"proposal_id": "SRP-2", "decision_id": "SRD-2", "actor": "vintos", "action": "ADOPT", "reason": "x"})
B.append(B.BUILDS, {"build_id": "SRB-old", "proposal_id": "SRP-2", "at": "t", "state": "patch_bound", "decision_id": "SRD-2", "patch_sha256": "0" * 64})
try:
    B.build("SRP-2"); check("a patch differing from the bound one is refused", False)
except PermissionError as e:
    check("a patch differing from the bound one is refused", "does not transfer" in str(e), e)
check("the refused build changed nothing on disk", "'fly'" in open(live).read())

print("\n--- recoverable: the before-image restores the live file ---")
shutil.copy2(os.path.join(rec["backup"], "scripts", "wings.py"), live)
check("restore from the before-image works", "'walk'" in open(live).read())
shutil.copy2(os.path.join(B.BUILD_ROOT, rec["build_id"], "stage", "scripts", "wings.py"), live)

print("\n--- observed capability ---")
CV = load("cv_t", os.path.join(REPO, "scripts", "capability-view.py")); CV.MEMORY = MEM; CV.WS = WS
caps = os.path.join(HOME, "CAPS.md"); open(caps, "w").write("## Flying\n<!-- depends: scripts/wings.py -->\nHe flies.\n")
d = CV.described(caps_path=caps, route_paths=[])
check("a capability depending on the installed file is VERIFIED", d[0]["status"] == "VERIFIED" and not d[0]["missing"], d)
open(caps, "w").write("## Flying\n<!-- depends: scripts/wings.py, scripts/feathers.py -->\nHe flies.\n")
d = CV.described(caps_path=caps, route_paths=[])
check("...and one whose dependency was never installed is UNVERIFIED, naming it", d[0]["status"] == "UNVERIFIED" and d[0]["missing"] == ["scripts/feathers.py"], d)
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

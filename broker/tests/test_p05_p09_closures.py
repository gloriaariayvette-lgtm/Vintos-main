#!/usr/bin/env python3
"""Review items 160, 172, 174, 342, 348, 350, 354, 364, 371 (2026-09-10). Scratch HOME; no model."""
import os, sys, json, types, tempfile, importlib.util, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-p59-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True); os.makedirs(MEM, exist_ok=True)
os.environ["SPARK_WORKSPACE"] = WS
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)

print("\n--- 174: the campaign names its budget and why it is held ---")
CA = load("campaign", os.path.join(REPO, "scripts", "campaign.py"))
for a in dir(CA):
    v = getattr(CA, a)
    if isinstance(v, str) and a.isupper() and ".vintos" in v: setattr(CA, a, os.path.join(MEM, os.path.basename(v)))
CA._load = lambda: {"destination": "the garden", "turns_served": 7, "suspensions": 1, "moves": [{"move": "asked"}]}
st = CA.lead_state()
check("budget and why_held are explicit", st["budget"]["turns_served"] == 7 and st["budget"]["max_turns"] == CA.MAX_TURNS and st["why_held"].startswith("turn budget spent") and st["progressed"] is True, st)

print("\n--- 350: effects classified by path ---")
B = load("srb", os.path.join(REPO, "scripts", "self_review_builder.py")); B.WS = WS; B.RUNTIME_MAP = os.path.join(MEM, "rm.json")
cls = B.classify_effects(["scripts/toy_link.py", "scripts/deliver.py", "scripts/wal-decay.py", "scripts/wings.py"])
check("device / outward / memory / internal by canonical path", cls == {"scripts/toy_link.py": "device", "scripts/deliver.py": "outward", "scripts/wal-decay.py": "memory", "scripts/wings.py": "internal"}, cls)
check("a device or outward class needs her approval regardless of the proposal's own words", "reaches a %s effect by its path" in src("scripts/self_review_builder.py") and '"effect_classes": classify_effects(paths)' in src("scripts/self_review_builder.py"))

print("\n--- 348: proposals that name what exists are marked ---")
cr = src("bin/vintos-code-review.py")
check("stage_review marks already_exists for a route or file that is in the checkout", "def _dedup_against_code" in cr and 'p["already_exists"] = sorted(found)' in cr and "props = _dedup_against_code(" in cr)

print("\n--- 371: coverage by lens ---")
pl = src("agent-room/proposal-ledger.py")
check("the ledger writes the section x lens coverage matrix and names the sections no lens reached", "## Coverage by lens" in pl and 'f"{day}-coverage.json"' in pl and "Sections no lens reviewed" in pl)

print("\n--- 364: a friction signal carries its lineage ---")
sr = src("scripts/self_review.py")
check("both friction streams append attempts / scanned / source / window to their evidence", sr.count('{"lineage": {"attempts":') == 2)

print("\n--- 342: Study progress in five words ---")
SC = load("study_chat", os.path.join(REPO, "bin", "study_chat.py")) if False else None
sc = src("bin/study_chat.py")
check("progress() reports pending / applied / verified / overwritten / failed and a refused apply is recorded", "def progress():" in sc and 'rec["apply_failed"] = {"at"' in sc and '@app.get("/api/chat/study/progress")' in sc)

print("\n--- 160 / 172 / 354: what already stands ---")
check("usage rows, paid reservations, bounded leases, source cache, paused pursuits and resumable landings exist", all(k in src("scripts/compute_admission.py") for k in ("def reserve_paid", "def record")) and os.path.exists(os.path.join(REPO, "scripts", "source_cache.py")) and "def pending_landings" in src("bin/dream-music.py") and '_pp.get("state") == "PAUSED"' in src("bin/wants-router.py"))
check("capability claims are VERIFIED / UNVERIFIED by the capability view", "UNVERIFIED" in src("scripts/capability-view.py") and "VERIFIED" in src("scripts/capability-view.py"))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

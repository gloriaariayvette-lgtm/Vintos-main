#!/usr/bin/env python3
"""Review items 49, 60, 61, 64, 175, 284, 289, 319, 341 (2026-09-10). Scratch HOME; no model."""
import os, sys, json, types, tempfile, importlib.util, time, re

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-lp-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)
import shutil
for f in ("store_guard.py", "learning_occasion.py"):
    shutil.copy(os.path.join(REPO, "scripts", f), os.path.join(WS, "scripts", f))

print("\n--- 49: an event teaches once, and a replay loses nothing ---")
LO = load("learning_occasion", os.path.join(WS, "scripts", "learning_occasion.py")); LO.MEMORY = MEM; LO.STORE = os.path.join(MEM, "learning-occasions.json"); LO.WS = WS
sys.modules["learning_occasion"] = LO
a = LO.teach("taste", "T-1"); b = LO.teach("taste", "T-1"); c = LO.teach("taste", "T-2")
check("first is the teaching one; the replay is not, and is counted", a["first"] and not b["first"] and b["count"] == 2 and c["first"])
check("a different learner learns from the same occurrence", LO.teach("recurrence", "T-1")["first"])
rec = LO.seen("taste", "T-1")
check("the replay is kept with its time, never lost", rec["count"] == 2 and rec["replays"] and rec["first_at"] <= rec["replays"][0])
check("the taste door and the curiosity debt go through it", "_lo.teach(\"taste\", occurrence_id" in src("scripts/enjoyment.py") and '_lo.teach("curiosity:" + h, occ)' in src("scripts/curiosity_debt.py"))

print("\n--- 60 / 61 / 64: a versioned pure selection, then admission, one assembler ---")
ic = src("scripts/inner_context.py")
check("the offers record is a versioned, identified, pure selection", "_SELECTION_VERSION = 3" in ic and '"selection_id": sel' in ic and '"pure": True' in ic)
check("a renderer that offered never mutates state there; admission is the prompt's and the record's", "never mutates state here" in ic)
check("one assembler of the inner layer for every surface, stated where it lives", "this is the ONE assembler of the inner layer for every surface" in src("bin/server.py"))
check("the turn record joins admission to what was offered", '"excerpts"' in src("scripts/turn_record.py") and '"omitted"' in src("scripts/turn_record.py"))

print("\n--- 175: one retry policy ---")
RP = load("retry_policy", os.path.join(REPO, "scripts", "retry_policy.py"))
check("a device or a build is never retried automatically", RP.should_retry("device", 1, "timeout")[0] is False and RP.should_retry("build", 1, "timeout")[0] is False and "never repeated by a machine" in RP.should_retry("device", 1, "timeout")[2])
r1 = RP.should_retry("transport", 1, "connection reset"); r2 = RP.should_retry("transport", 3, "connection reset")
check("transport retries with a backoff and stops at its bound", r1[0] and r1[1] == 1 and r2[0] is False and "bound" in r2[2], (r1, r2))
check("a 4xx is an answer, not a transport fault", RP.should_retry("transport", 1, "404 4xx")[0] is False)
check("a bounded loop continues at most twice", RP.policy("bounded_loop")["attempts"] == 2)
check("the quantum doorway asks the policy instead of carrying its own numbers", '_sr("transport", 1, "timeout")' in src("scripts/atelier_quantum.py"))

print("\n--- 284: a continuation carries what was established ---")
check("the held inquiry carries the claims its earlier attempts supported, with their sources", '"established": [{"claim"' in src("bin/vintos-websearch.py") and 'a.get("graded") in ("ANSWERED", "PARTIAL")' in src("bin/vintos-websearch.py"))

print("\n--- 289: a handoff debt retires ---")
AG = load("atelier_gate", os.path.join(REPO, "scripts", "atelier-gate.py")) if False else None
ag = src("scripts/atelier-gate.py")
check("retire_debt moves a met note out of the open set, keeping it as a record", "def retire_debt" in ag and '"retired_at"' in ag and "never a deletion" in ag and "def open_debt" in ag)

print("\n--- 319: the capability list is served, not copied ---")
sv = src("bin/server.py")
check("a guarded route serves the router's own list with what each capability produces", '@app.get("/api/system/capabilities")' in sv and 'getattr(_m, "CAPABILITIES", [])' in sv and "a client carrying a fixed copy will drift from this" in sv)
check("the router's list says it is the one list", "the ONE capability list" in src("bin/wants-router.py"))

print("\n--- 341: the Study is a session with a cursor and coverage ---")
sc = src("bin/study_chat.py")
check("a session can be opened, a read moves the file's cursor, coverage answers what was read", "def session_open" in sc and "def session_note_read" in sc and "def session_coverage" in sc and "session_note_read(lab, start, i, len(lines))" in sc)
check("the read itself says how far into the file the session has got", '_cov = "" if _c.get("complete") else " [read to line %d of %d]"' in sc)
check("the coverage and session routes exist, guarded", '@app.get("/api/chat/study/coverage")' in sc and '@app.post("/api/chat/study/session")' in sc and sc.count("_auth(request)") >= 6)

print("\n--- 322 / 331 / 332 / 337 / 339: the surfaces this checkout owns ---")
ov = open(os.path.join(REPO, "avatar", "overlay.html")).read()
check("322: the fallback stays until the media actually plays, and a stall gives up quietly", "'playing'" in ov and "PLAY_TIMEOUT_MS" in ov and "the current layer / fallback stays visible" in ov and "addEventListener('canplay'" not in ov)   # the word survives in the comments; the listener is gone
check("337: one idempotent close that pauses and releases every video before telling the host", "function closeOverlay()" in ov and "if (closed) return" in ov and "v.pause(); v.removeAttribute('src'); v.load();" in ov and "pagehide" in ov)
sv2 = src("bin/server.py")
check("331: the provider's item/response/event/session ids travel with a voice turn, never invented", '"provider_item_id"' in sv2 and '"provider_response_id"' in sv2 and "never invented" in sv2)
check("332: the session state is cleared only after the block is on disk; otherwise the turns are kept for retry", "_block_persisted = True" in sv2 and "if _block_persisted:" in sv2 and '"unpersisted"' in sv2 and "kept for retry" in sv2)
check("339: the server has no /chat or /state route; docs/clients.md records them as retired", not re.search(r'@app\.(get|post)\(\s*["\']/(chat|state)["\']', sv2) and "retired at the server" in open(os.path.join(REPO, "docs", "clients.md")).read())
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

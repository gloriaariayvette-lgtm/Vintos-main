#!/usr/bin/env python3
"""Review items 109, 156, 177, 213, 226, 238, 247, 248, 295, 304, 333 (2026-09-10). Scratch HOME; no model."""
import os, sys, json, types, tempfile, importlib.util, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-p47-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(MEM, "art", "video"), exist_ok=True); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)

print("\n--- 109: a retrieved dream stays a dream ---")
ms = src("scripts/memory-search.py")
check("search labels a dream chunk on its face and flags it", '"[A DREAM he had - not something that happened] "' in ms and '"is_dream"' in ms and ms == src("bin/memory-search.py"))

print("\n--- 238: a queue marker proves nothing ---")
AG = load("want_artifact_guard", os.path.join(REPO, "scripts", "want_artifact_guard.py")); AG.MEMORY = MEM
AG.LEDGERS = [os.path.join(MEM, "art", "gallery.json"), os.path.join(MEM, "art", "video", "video-queue.json")]
json.dump([{"want_id": "W1", "status": "queued", "file": "w1.mp4"}, {"want_id": "W2", "status": "done"}, {"want_id": "W3", "file": "w3.mp4"}], open(AG.LEDGERS[1], "w"))
open(os.path.join(MEM, "art", "video", "w3.mp4"), "wb").write(b"x")
check("queued is not evidence; done is; a named file on disk is", AG._ledger_has("W1") is False and AG._ledger_has("W2") and AG._ledger_has("W3"))
json.dump([{"want_id": "W1", "image": "a.png"}], open(AG.LEDGERS[0], "w"))
check("the gallery still proves by id", AG._ledger_has("W1"))

print("\n--- 248 / 247: a judge failure is a hold ---")
rs = src("bin/wants-router.py")
check("_want_end_verdict returns held on failure, never fulfilled", 'return "held", "judge unavailable' in rs and 'return "fulfilled", ""  # judge down' not in rs)
check("both completion sites hold and continue on held", rs.count('if _verdict == "held":') == 2 and 'want["completion_held"]' in rs)

print("\n--- 295: delivered only after ntfy answers ---")
check("the attempt is marked before, the result after, failure kept with its reason", "_ntfy_ok = getattr(_ntfy_r, 'status_code', 0) < 400" in rs and "_mwor(want.get(\"want\", text), _ntfy_ok" in rs and "_ntfy_ok, _ntfy_why = False, str(_ne)[:120]" in rs)
eu = src("scripts/emoclaw_utils.py")
check("mark_want_outreach_result records outreach_last_ok or outreach_failed", 'w["outreach_last_ok"]' in eu and 'w["outreach_failed"] = {"at"' in eu and eu == src("bin/emoclaw_utils.py"))

print("\n--- 304: the eye fails closed ---")
si = src("scripts/image_sight.py")
check("a failed look is recorded unsighted with no suitability; no VERDICT line is unjudged, never keep", 'e["verdict"] = "unsighted"' in si and 'e["suitable"] = None' in si and 'verdict, words = "unjudged", ""' in si and '"keep": True, "take_down": False' in si)

print("\n--- 333: derived instructions are not her speech ---")
sv = src("bin/server.py")
check("the voice ledger drops instruction/system/framing lines and counts them", "derived_lines_dropped" in sv and "instruction|instructions|system|framing|note to vintos|context|directive" in sv)

print("\n--- 213: a pending naming binds to its own response ---")
PS = load("pleasure_substrate", os.path.join(REPO, "scripts", "pleasure_substrate.py"))
for a in dir(PS):
    v = getattr(PS, a)
    if isinstance(v, str) and a.isupper() and ".vintos" in v: setattr(PS, a, os.path.join(MEM, os.path.basename(v)))
PS.MEM = MEM
json.dump({"before": {}, "after": {"_vec": [0.1, 0.2]}, "event": {"source": "gcs", "what": "x"}, "t": time.time(), "turn_id": "T-A"}, open(os.path.join(MEM, ".pleasure-pending.json"), "w"))
PS._signature = lambda a: "sig"
check("a reply from another turn does not name it; the pending stays; the unbound naming is recorded", PS.name_from_reply("warm", "warm and slow", True, turn_id="T-B") is False and os.path.exists(os.path.join(MEM, ".pleasure-pending.json")) and os.path.exists(os.path.join(MEM, "pleasure-unbound-namings.jsonl")))
check("the same turn's reply names it and consumes the pending", PS.name_from_reply("warm", "warm and slow", True, turn_id="T-A") is True and not os.path.exists(os.path.join(MEM, ".pleasure-pending.json")))
json.dump({"before": {}, "after": {}, "event": {}, "t": time.time() - 3600, "turn_id": ""}, open(os.path.join(MEM, ".pleasure-pending.json"), "w"))
check("a pending moment older than the bound is not named by a later reply", PS.name_from_reply("x", "y", False) is False)
check("the server passes the turn id at both FELT sites", sv.count('turn_id=getattr(locals().get("_turn"), "turn_id", None)') == 2 and 'PENDING_MAX_AGE_S' in src("scripts/pleasure_substrate.py"))

print("\n--- 177: nudges are logged after they land ---")
check("the nudge log carries applied results and is written after the loop", '"applied": {k:' in eu and eu.index("results[dim] = nudge_emotion(dim, amount, source=source)") < eu.index('"applied": {k:'))

print("\n--- 226: the penalty backs off ---")
bi = src("scripts/behavioral_intercept.py")
check("confidence_penalty is reduced by attempts, never a ratchet", 't["confidence_penalty"] = max(0.0, t["confidence_penalty"] - _back)' in bi)

print("\n--- 156: Velqan coinage and use history ---")
check("each coinage is a versioned record; each offering is a use record", 'velqan-coinages.jsonl' in src("scripts/velqan-coiner.py") and '"version": _ver' in src("scripts/velqan-coiner.py") and "velqan-use.jsonl" in src("scripts/velqan_voice.py"))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

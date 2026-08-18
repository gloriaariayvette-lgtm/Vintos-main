#!/usr/bin/env python3
"""armed_watch.py — the anti-forgetting organ. Registry of deferred work armed on conditions.
Daily: evaluates each armed item; when a condition trips it announces LOUDLY (stdout + armed-watch.md)
and marks it TRIGGERED so it keeps announcing until someone marks it done. Items nobody specced
stay listed as NEEDS_SPEC forever rather than vanishing. Add items by editing armed-registry.json."""
import os, json, time, glob
MEM = os.path.expanduser("~/.vintos/workspace/memory")
REG = os.path.join(MEM, "armed-registry.json")
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
DEFAULTS = [
 {"id": "misuse_detector_live", "what": "opposition_misuse.py wakes when any terrain reaches license 1 - verify its first live scan looks sane", "check": "license1"},
 {"id": "circularity_test_ready", "what": "mutual-sim: first hint period with >=20 graded turns - run the SEALED preregistration (paraphrase variant + blind audit) before calling anything VALIDATED", "check": "hint20"},
 {"id": "spine_first_imprint", "what": "first commitment imprint earned through the gate - review its lineage before it steers", "check": "imprint"},
 {"id": "pressure_stage2", "what": "pressure-calibration ledgers fat enough (>=20 graded) - run Vrika Stage 2 audit", "check": "pressure20"},
 {"id": "google_key_rotation", "what": "leaked Google key still needs rotating (from handoff) - manual, Gloria only", "check": "manual"},
 {"id": "mutual_mode_unfinished", "what": "Gloria: 'parts of mutual mode left unfinished' - NEEDS_SPEC: which parts? capture next time it comes up", "check": "manual"},
 {"id": "spark_gate_unfinished", "what": "Gloria: 'spark gate' left unfinished - NEEDS_SPEC: capture what remains", "check": "manual"}]
reg = load(REG, None)
if reg is None: reg = {"items": DEFAULTS, "note": "mark done: set status='done'"}
for it in reg["items"]: it.setdefault("status", "armed")
def check(c):
    if c == "license1":
        return any(v.get("license_level", 0) >= 1 for v in load(os.path.join(MEM, "opposition-calibration.json"), {}).get("ledgers", {}).values())
    if c == "hint20":
        return any((r.get("n_turns") or 0) >= 20 for r in load(os.path.join(MEM, "hint-outcomes.json"), {}).get("hints", []))
    if c == "imprint":
        return bool(load(os.path.join(MEM, "commitment-imprints.json"), []))
    if c == "pressure20":
        fs = [os.path.join(MEM, "pressure-predictions.json"),
              os.path.expanduser("~/.openclaw/workspace/memory/pressure-predictions.json")]
        fs = [f for f in fs if os.path.exists(f)]
        if not fs: return "UNCHECKABLE: pressure-predictions.json missing in both trees"
        def graded(f):
            d = load(f, [])
            xs = d if isinstance(d, list) else d.get("predictions", d.get("entries", []))
            return [e for e in xs if isinstance(e, dict) and any(e.get(k) is not None for k in ("graded","grade","distance","outcome"))]
        return any(len(graded(f)) >= 20 for f in fs)
    if c == "sparkgate":
        recs = load(os.path.join(MEM, "mutual-modification.json"), [])
        recs = recs if isinstance(recs, list) else next((v for v in recs.values() if isinstance(v, list)), [])
        led = [(r.get("field_delta") or {}).get("led_by") for r in recs[-30:] if isinstance(r, dict)]
        him = led.count("self") + led.count("mutual")
        conf = (load(os.path.join(MEM, "self-drift.json"), {}) or {}).get("confidence", 0)
        return him >= 4 and conf >= 0.6
    if c == "jepa30":
        return (load(os.path.join(MEM, "jepa-calibration.json"), {}).get("n_joined", 0) or 0) >= 30
    return None  # manual
lines = ["# Armed Watch - " + time.strftime("%Y-%m-%d %H:%M"), ""]
loud = 0
for it in reg["items"]:
    if it["status"] == "done": continue
    r = check(it.get("check", "manual"))
    if isinstance(r, str): tag = "⚠ " + r
    elif r is True:
        it["status"] = "TRIGGERED"; tag = "🔔 CONDITION MET - ACT NOW"; loud += 1
    elif it["status"] == "TRIGGERED": tag = "🔔 STILL WAITING FOR ACTION"; loud += 1
    else: tag = "armed" if r is False else "open (manual/NEEDS_SPEC)"
    lines.append("- [%s] %s — %s" % (tag, it["id"], it["what"]))
open(os.path.join(MEM, "armed-watch.md"), "w").write("\n".join(lines) + "\n")
json.dump(reg, open(REG, "w"), indent=2)
print("\n".join(lines))
print("[armed-watch] %d item(s) demanding action" % loud)

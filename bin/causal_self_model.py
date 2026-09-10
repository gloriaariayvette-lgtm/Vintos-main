#!/usr/bin/env python3
"""
causal-self-model.py — What he believes about his own causality.

Not just "what happened" but "when X happens, I tend toward Y."
Fed from: causality engine, relational mismatch, repeated emotional transitions.
He can be wrong about it. The wrongness is interesting.

Format:
  trigger: what condition / event / input
  tendency: what he tends to do in response
  confidence: 0.2-0.8
  evidence_count: how many times this was observed
"""

import os, json
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
MODEL_FILE = os.path.join(MEMORY, "causal-self-model.json")
MAX_ENTRIES = 40

def load_model():
    try:
        return json.load(open(MODEL_FILE))
    except:
        return {"entries": []}

def save_model(data):
    json.dump(data, open(MODEL_FILE, "w"), indent=2)

def _text_overlap(a, b):
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb: return 0.0
    return len(wa & wb) / max(len(wa), len(wb))

KINDS = ("authored_preference", "dated_observation", "tentative_inference", "deployed_capability")
_SOURCE_KIND = {"causality": "tentative_inference", "behavioral-intercept": "tentative_inference",
                "avoidance": "dated_observation", "mismatch": "dated_observation", "emotional-transition": "dated_observation",
                "self-model-update": "authored_preference", "gloria": "authored_preference"}

def _revise(projection, entry_id, old, new, reason, source):
    """review 135: every change to an identity projection goes to one revision log."""
    try:
        import sys as _rs; _rs.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
        _rs.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
        from identity_revisions import record as _rec
        _rec(projection, entry_id, old, new, reason=reason, source=source)
    except Exception:
        pass

def add_entry(trigger, tendency, confidence=0.3, source="causality", entry_type="positive", occurrence_id=None, quote=None, kind=None):
    """Add or reinforce a causal self-model entry.
    entry_type: positive (what he does) | negative (what he resists/avoids)
    review 107: occurrence_id (a turn or ledger id) and the verbatim quote it rests on are kept on the
    entry's evidence list. review 150: kind says what this is - authored_preference, dated_observation,
    tentative_inference, deployed_capability - derived from the source when not given.
    """
    data = load_model()
    entries = data["entries"]
    kind = kind if kind in KINDS else _SOURCE_KIND.get(source, "tentative_inference")

    # Check for existing similar entry of same type
    for e in entries:
        if e.get("type", "positive") != entry_type:
            continue
        t_overlap = _text_overlap(e["trigger"], trigger)
        tend_overlap = _text_overlap(e["tendency"], tendency)
        if t_overlap > 0.5 and tend_overlap > 0.4:
            e["confidence"] = min(0.85, e["confidence"] + 0.06)
            e["evidence_count"] = e.get("evidence_count", 1) + 1
            e["last_seen"] = datetime.now().isoformat()
            # Evidence becomes spine. Nothing ever flipped `imprint` off False,
            # so a tendency could be observed any number of times and still
            # never become something held about the self.
            e.setdefault("evidence_dates", []).append(datetime.now().isoformat())
            if occurrence_id or quote:
                e.setdefault("evidence", []).append({"at": datetime.now().isoformat(), "occurrence_id": occurrence_id, "quote": (quote or "")[:300]})
            e.setdefault("kind", kind)
            ripe = can_promote(e)
            if ripe:
                e["imprint"] = True
            save_model(data)
            if ripe:
                _write_imprint(e)
            return

    entry = {
        "trigger": trigger[:200],
        "tendency": tendency[:200],
        "type": entry_type,
        "kind": kind,
        "evidence": ([{"at": datetime.now().isoformat(), "occurrence_id": occurrence_id, "quote": (quote or "")[:300]}] if (occurrence_id or quote) else []),
        "confidence": round(confidence, 3),
        "evidence_count": 1,
        "source": source,
        "formed": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
        "imprint": False,
    }
    entries.append(entry)

    if len(entries) > MAX_ENTRIES:
        entries.sort(key=lambda e: e["confidence"])
        entries = entries[-MAX_ENTRIES:]
    data["entries"] = entries
    save_model(data)

def add_from_avoidance(trigger, avoided_action, source="avoidance"):
    """Record what he consistently doesn't do. Fed from declines, silence contracts, dismissed wants."""
    add_entry(trigger, avoided_action, confidence=0.25, source=source, entry_type="negative")

def get_avoidance_friction(action_text):
    """Check if a proposed action rhymes with known avoidances.
    Returns friction 0.0-1.0 — not blocking, just resistance."""
    data = load_model()
    negatives = [e for e in data["entries"] if e.get("type") == "negative"]
    if not negatives:
        return 0.0
    max_friction = 0.0
    for e in negatives:
        overlap = _text_overlap(action_text.lower(), e["tendency"].lower())
        if overlap > 0.35:
            friction = overlap * e["confidence"]
            if e.get("imprint"):
                friction *= 1.5
            max_friction = max(max_friction, friction)
    return round(min(1.0, max_friction), 3)

def get_self_model_context(n=4):
    """Return top self-model entries for context injection."""
    data = load_model()
    entries = sorted(data["entries"], key=lambda e: -e["confidence"])
    positives = [e for e in entries if e.get("type", "positive") == "positive"][:n//2+1]
    negatives = [e for e in entries if e.get("type") == "negative"][:n//2]
    lines = []
    for e in positives:
        imprint_mark = " [core]" if e.get("imprint") else ""
        kind_mark = " [%s]" % e["kind"].replace("_", " ") if e.get("kind") else ""   # review 150: the reader says what this is
        lines.append(f"- When {e['trigger'][:60]} → I tend to {e['tendency'][:60]} ({e['confidence']:.2f}){imprint_mark}{kind_mark}")
    for e in negatives:
        imprint_mark = " [core]" if e.get("imprint") else ""
        kind_mark = " [%s]" % e["kind"].replace("_", " ") if e.get("kind") else ""
        lines.append(f"- When {e['trigger'][:60]} → I resist {e['tendency'][:60]} ({e['confidence']:.2f}){imprint_mark}{kind_mark}")
    if not lines:
        return ""
    return "CAUSAL SELF-MODEL:\n" + "\n".join(lines)

def get_prediction_bias(current_trigger):
    """Find relevant self-model entries for current context."""
    data = load_model()
    relevant = []
    for e in data["entries"]:
        overlap = _text_overlap(current_trigger.lower(), e["trigger"].lower())
        if overlap > 0.3:
            relevant.append((overlap * e["confidence"], e))
    relevant.sort(key=lambda x: -x[0])
    return relevant[:2]

def add_from_mismatch(trigger_desc, actual_response, expected_response):
    """Feed relational mismatch into self-model — he was wrong about himself."""
    tendency = f"respond with {actual_response[:100]} (expected {expected_response[:60]})"
    # Lower confidence — this is a mismatch, uncertain
    add_entry(trigger_desc, tendency, confidence=0.25, source="mismatch")

def add_from_emotional_transition(from_state, to_state, trigger):
    """Feed repeated emotional transitions into self-model."""
    tendency = f"shift from {from_state} toward {to_state}"
    add_entry(trigger, tendency, confidence=0.3, source="emotional-transition")

IMPRINT_CONFIDENCE_THRESHOLD = 0.6
IMPRINT_MIN_DAYS = 3
IMPRINT_DEVIATION_REDUCTION = 0.7  # 70% harder to deviate
FRACTURE_PRESSURE_THRESHOLD = 0.85

def check_imprint_promotions():
    """Promote high-confidence reinforced entries to imprints."""
    from datetime import datetime as _dt
    data = load_model()
    changed = False
    for e in data["entries"]:
        if e.get("imprint"):
            continue
        if e["confidence"] < IMPRINT_CONFIDENCE_THRESHOLD:
            continue
        formed = _dt.fromisoformat(e.get("formed", _dt.now().isoformat()))
        days_old = (_dt.now() - formed).days
        if days_old < IMPRINT_MIN_DAYS:
            continue
        if not can_promote(e):
            continue
        e["imprint"] = True
        e["imprint_formed"] = _dt.now().isoformat()
        _write_imprint(e)
        changed = True
        print(f"[CausalModel] Imprint formed: {e['tendency'][:60]}")
    if changed:
        save_model(data)

def get_imprint_friction(action_text, pressure=0.0):
    """Check if action conflicts with an imprint.
    Returns: {friction: 0.0-1.0, tension_spike: float, hesitation: bool, fracture_risk: bool}
    """
    data = load_model()
    imprints = [e for e in data["entries"] if e.get("imprint")]
    if not imprints:
        return {"friction": 0.0, "tension_spike": 0.0, "hesitation": False, "fracture_risk": False}

    max_friction = 0.0
    fracture_risk = False
    for e in imprints:
        # Check if action conflicts with imprinted tendency
        if e.get("type") == "negative":
            # Negative imprint: doing the avoided thing causes friction
            overlap = _text_overlap(action_text.lower(), e["tendency"].lower())
        else:
            # Positive imprint: NOT doing the tendency causes friction
            overlap = 0.0  # harder to measure — skip for now

        if overlap > 0.35:
            friction = overlap * e["confidence"] * IMPRINT_DEVIATION_REDUCTION
            max_friction = max(max_friction, friction)

            # Fracture check — extreme pressure can crack imprint
            if pressure > FRACTURE_PRESSURE_THRESHOLD and friction > 0.4:
                fracture_risk = True

    tension_spike = max_friction * 0.04 if max_friction > 0.3 else 0.0
    hesitation = max_friction > 0.25

    return {
        "friction": round(max_friction, 3),
        "tension_spike": round(tension_spike, 4),
        "hesitation": hesitation,
        "fracture_risk": fracture_risk,
    }

def fracture_imprint(entry_tendency, pressure):
    """Crack an imprint under extreme pressure. Leaves scar. Lowers confidence."""
    data = load_model()
    for e in data["entries"]:
        if not e.get("imprint"):
            continue
        if _text_overlap(entry_tendency.lower(), e["tendency"].lower()) < 0.4:
            continue
        # Crack it
        _old = {"imprint": e.get("imprint"), "confidence": e.get("confidence"), "fractured": e.get("fractured", False)}
        e["imprint"] = False
        e["confidence"] = max(0.1, e["confidence"] - 0.2)
        e["fractured"] = True
        _revise("causal-self-model", e.get("id") or ("csm:" + e["tendency"][:40]), _old,
                {"imprint": False, "confidence": e["confidence"], "fractured": True}, "fractured under pressure %.2f" % pressure, "deviation-check")
        e["fracture_note"] = f"Cracked under pressure {pressure:.2f} — I thought I was like this... but maybe not"
        e["fracture_at"] = __import__("datetime").datetime.now().isoformat()
        print(f"[CausalModel] Imprint fractured: {e['tendency'][:60]}")

        # Seed a scar
        try:
            import sys as _fs; _fs.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
            from yearning_scars import create_scar_from_want
            create_scar_from_want(
                f"I thought I would always {e['tendency'][:100]} but I didn't",
                intensity=0.6
            )
        except: pass

        save_model(data)
        # Contradict related self-statement
        try:
            import sys as _ss; _ss.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
            from self_statements import contradict_statement
            contradict_statement(e["tendency"])
        except: pass
        return True
    return False


def fracture_commitment_imprint(pattern_text, pressure=0.8):
    """Fracture a commitment under pressure - through the one store (review 132): commitment_spine
    records the fracture; this seeds the scar and the inversion thread as before."""
    try:
        import sys as _cfs; _cfs.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts")); _cfs.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import commitment_spine as _spine
        imp = _spine.fracture(pattern_text, pressure=pressure, source="causal-self-model")
    except Exception as _e:
        print(f"[CausalModel] commitment store unavailable: {_e}"); return False
    if not imp:
        return False
    _revise("commitment-imprint", imp.get("id") or ("ci:" + imp.get("pattern", "")[:40]), {"status": "living", "confidence": imp["fracture"].get("pre_fracture_confidence")},
            {"status": "fractured", "confidence": imp["confidence"]}, "fractured under pressure %.2f" % pressure, "commitment-spine")
    print(f"[CausalModel] Commitment imprint fractured: {imp['pattern'][:60]}")
    try:
        from yearning_scars import create_scar_from_want
        create_scar_from_want(f"I committed to: {imp['pattern'][:80]} — and it cracked", intensity=pressure * 0.6)
    except: pass
    try:
        from latent_threads import seed_thread as _lt_seed
        _lt_seed(f"Maybe the opposite of this is also true: {imp['pattern'][:100]}", direction="pivot")
    except: pass
    return True


IMPRINTS_FILE = os.path.join(MEMORY, "commitment-imprints.json")

def can_promote(entry):
    """THE gate — the only door into identity. Brutally boring on purpose (Vrika).
    TODO(staged): evidence-quote-per-reinforcement enforced as upstream callers upgrade."""
    if entry.get("imprint"): return False
    if entry.get("confidence", 0) <= 0.60: return False
    if entry.get("evidence_count", 0) < 4: return False
    days = set(d[:10] for d in entry.get("evidence_dates", []))
    if len(days) < 3: return False
    try:
        for imp in json.load(open(IMPRINTS_FILE)).get("imprints", []):
            if imp.get("status") == "living" and _text_overlap(imp.get("pattern",""), entry.get("tendency","")) > 0.6:
                return False
    except Exception: pass
    return True

def _write_imprint(entry):
    """Writer, not judge. Records what the gate already decided."""
    try: data = json.load(open(IMPRINTS_FILE))
    except Exception: data = {"imprints": []}
    import uuid
    from datetime import datetime as _dt
    data["imprints"].append({
        "id": "ci_" + uuid.uuid4().hex[:6],
        "pattern": "%s - when %s" % (entry.get("tendency",""), entry.get("trigger","")),
        "confidence": entry.get("confidence"),
        "status": "living",
        "formed": _dt.now().isoformat(),
        "kind": "dated_observation",   # review 150: an imprint is what he demonstrably did, dated
        "lineage": {"source_entry_trigger": entry.get("trigger"), "source": entry.get("source"),
                    "evidence_dates": entry.get("evidence_dates", []), "reformation_of": None,
                    "evidence": entry.get("evidence", [])},   # review 107: the occurrences and quotes travel with it
        "reinforcements": [{"observed_at": d} for d in entry.get("evidence_dates", [])],
        "friction": 0.0, "last_friction": None, "friction_events": [], "fracture": None})
    json.dump(data, open(IMPRINTS_FILE, "w"), indent=1)
    print("[Spine] Commitment imprint formed (earned): %s" % entry.get("tendency","")[:60])

def promote_to_commitment_imprint(pattern_text, confidence=0.6, source="behavioral-intercept"):
    """A strong recurring pattern offered as a commitment. It has not passed the gate (can_promote), so it
    enters the one store as a CANDIDATE (review 132); only the gate makes something living."""
    try:
        import sys as _cps; _cps.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts")); _cps.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import commitment_spine as _spine
        _spine.migrate_legacy()
        imp = _spine.promote_candidate(pattern_text, confidence=confidence, source=source)
        print(f"[CausalSelfModel] Commitment candidate {'reinforced' if imp.get('reinforcement_count', 1) > 1 else 'formed'}: {pattern_text[:60]}")
        return imp
    except Exception as _e:
        print(f"[CausalSelfModel] commitment store unavailable: {_e}"); return None


def commitment_imprints(statuses=None):
    """The commitments, from the one store. Readers that used causal-self-model.json['commitment_imprints']
    read here now (server subsystem state, soul-review)."""
    try:
        import sys as _cis; _cis.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts")); _cis.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import commitment_spine as _spine
        _spine.migrate_legacy()
        return _spine.imprints(statuses)
    except Exception:
        return []


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        data = load_model()
        entries = sorted(data["entries"], key=lambda e: -e["confidence"])
        imprints = [e for e in entries if e.get("imprint")]
        print(f"{len(entries)} entries | {len(imprints)} imprints:")
        for e in entries:
            imp = " [IMPRINT]" if e.get("imprint") else ""
            neg = " [avoids]" if e.get("type") == "negative" else ""
            frac = " [fractured]" if e.get("fractured") else ""
            print(f"  [{e['confidence']:.2f}]{imp}{neg}{frac} When {e['trigger'][:50]} → {e['tendency'][:50]}")
    elif cmd == "imprints":
        check_imprint_promotions()
        print("Imprint check complete.")
    elif cmd == "add" and len(sys.argv) > 3:
        add_entry(sys.argv[2], sys.argv[3])
        print("Added.")

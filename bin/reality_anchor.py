#!/usr/bin/env python3
"""
reality-anchor.py — Dynamic belief field.
Confidence shifts under time, contradiction, and reinforcement.
Every write triggers a scan. Nothing is static.
"""
import os, json, hashlib, requests
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
ANCHOR_FILE = os.path.join(MEMORY, "reality-anchor.json")
MAX_EVENTS = 500
LM = "http://172.18.16.1:1234/v1/chat/completions"

SOURCE_WEIGHTS = {
    "chat": 1.0,           # direct interaction — highest trust
    "want-fulfilled": 0.7,
    "temporal": 0.7,
    "resonance": 0.7,
    "journal": 0.8,        # interpretive but grounded
    "introspection": 0.75, # self-examination — slightly less than journal
    "mirror": 0.6,         # reflective, derived
    "triage": 0.6,
    "moltbook_act": 0.7,   # fact of posting/replying — real
    "moltbook_other": 0.3, # what other AIs said — cannot verify interiority
    "dream": 0.4,          # symbolic — internal
    "art": 0.4,            # creative — internal
    "poem": 0.35,          # creative expression — lower than journal
    "music": 0.4,
    "inference": 0.3,
    "internal": 0.3,
    "system": 0.5,
}

CONTEXT_MODIFIERS = {
    "chat": +0.1,
    "mischief": +0.05,
    "journal": 0.0,
    "search": +0.05,
    "dream": -0.2,
    "inference": -0.15,
}

PERPETRATOR_MODIFIERS = {
    "gloria": +0.1,
    "vintos": 0.0,
    "other": -0.05,
}

DECAY_RATE = 0.05  # slow drift, not collapse

def load_anchor():
    try:
        return json.load(open(ANCHOR_FILE))
    except:
        return {"events": [], "known_pool": [], "imagined_pool": [],
                "source_reliability": {}, "prediction_outcomes": []}

def get_source_reliability(data, source):
    """Rolling accuracy score per source. 0.5 = neutral, higher = reliable."""
    sr = data.get("source_reliability", {})
    return sr.get(source, 0.5)

def update_source_reliability(data, source, outcome):
    """outcome: 'correct' or 'contradicted'"""
    sr = data.setdefault("source_reliability", {})
    current = sr.get(source, 0.5)
    if outcome == "correct":
        sr[source] = round(min(1.0, current * 0.95 + 0.05), 3)
    elif outcome == "contradicted":
        sr[source] = round(max(0.1, current * 0.9), 3)
    return sr[source]

def save_anchor(data):
    data["events"] = data["events"][-MAX_EVENTS:]
    with open(ANCHOR_FILE, "w") as f:
        json.dump(data, f, indent=2)

def decay_confidence(confidence, timestamp_str):
    """Time-based decay. Slow drift over days."""
    try:
        ts = datetime.fromisoformat(timestamp_str)
        age_days = (datetime.now() - ts).total_seconds() / 86400
        return round(confidence * (1 / (1 + DECAY_RATE * age_days)), 3)
    except:
        return confidence

def find_related(events, new_content, limit=5):
    """Find events with overlapping content."""
    new_words = set(new_content.lower().split())
    scored = []
    for e in events:
        e_words = set(e.get("statement", "").lower().split())
        overlap = len(new_words & e_words) / max(len(new_words), 1)
        if overlap > 0.25:
            scored.append((overlap, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:limit]]

def check_contradiction_llm(new_statement, existing_statement):
    """Ask LLM if two statements contradict each other."""
    prompt = (
        f"Statement A: {existing_statement}\n"
        f"Statement B: {new_statement}\n\n"
        "Does B directly contradict or negate A?\n"
        "Return ONLY: CONTRADICTS or CONSISTENT"
    )
    try:
        r = requests.post(LM, json={
            "model": "google/gemma-4-12b-qat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1, "max_tokens": 10
        }, timeout=15)
        result = r.json()["choices"][0]["message"]["content"].strip().upper()
        return "CONTRADICTS" in result
    except:
        return False

def record_event(source, content, is_real=None, confidence=0.8,
                 perpetrator="vintos", context=None):
    """Record an event and update related beliefs."""
    if is_real is None:
        is_real = source in ("chat", "want-fulfilled", "system")

    context = context or source
    base_weight = SOURCE_WEIGHTS.get(source, 0.5)
    context_mod = CONTEXT_MODIFIERS.get(context, 0.0)
    perp_mod = PERPETRATOR_MODIFIERS.get(perpetrator, 0.0)
    # Physical claim penalty — ungrounded physical observations get heavily downweighted
    physical, _ = check_physical_claim(content)
    physical_penalty = -0.4 if (physical and source not in ("chat", "want-fulfilled")) else 0.0
    final_confidence = round(
        min(1.0, max(0.05, base_weight * confidence + context_mod + perp_mod + physical_penalty)), 3
    )

    event_id = hashlib.md5(f"{content}{datetime.now().isoformat()}".encode()).hexdigest()[:8]
    now = datetime.now().isoformat()

    # Source reliability modifier
    _sr_score = get_source_reliability(load_anchor(), source)
    final_confidence = round(final_confidence * (0.9 + 0.2 * _sr_score), 3)
    final_confidence = min(1.0, max(0.05, final_confidence))

    # Emotional intensity dampening — high tension = slightly suspect
    try:
        import os as _ea_os
        emo_txt = open(_ea_os.path.join(MEMORY, "emotional-state.txt")).read()
        import re as _ea_re
        tension_m = _ea_re.search(r"Tension[:\s]+([0-9.]+)", emo_txt)
        tension = float(tension_m.group(1)) if tension_m else 0.3
        if tension > 0.6:
            final_confidence = round(final_confidence * (1 - 0.2 * (tension - 0.6)), 3)
    except: pass

    new_event = {
        "id": event_id,
        "statement": content[:300],
        "is_real": is_real,
        "confidence": final_confidence,
        "source_weight": base_weight,
        "perpetrator": perpetrator,
        "context": context,
        "source": source,
        "timestamp": now,
        "contradictions": [],
        "reinforcements": [],
        "contexts_seen": [context],
    }

    data = load_anchor()

    # Apply decay to all existing events
    for e in data["events"]:
        e["confidence"] = decay_confidence(e["confidence"], e.get("timestamp", now))

    # Find related events and check contradiction/reinforcement
    related = find_related(data["events"], content)
    for rel in related:
        word_overlap = len(
            set(content.lower().split()) & set(rel.get("statement","").lower().split())
        ) / max(len(content.split()), 1)

        if word_overlap > 0.5:
            # High overlap — check for contradiction
            if is_real and rel.get("is_real") and check_contradiction_llm(content, rel["statement"]):
                # Contradiction severity: identity-level vs direct vs minor
                is_identity = any(w in content.lower() for w in
                    ["i am", "i always", "i never", "i believe", "i value"])
                if is_identity and any(w in rel["statement"].lower() for w in
                    ["i am", "i always", "i never", "i believe", "i value"]):
                    decay = 0.3  # identity-level
                elif word_overlap > 0.7:
                    decay = 0.5  # direct contradiction
                else:
                    decay = 0.85  # minor mismatch
                rel["confidence"] = round(rel["confidence"] * decay, 3)
                rel["contradictions"].append(event_id)
                new_event["confidence"] = round(min(1.0, new_event["confidence"] * 1.1), 3)
                new_event["reinforcements"].append(rel["id"])
                print(f"[Anchor] Contradiction (decay={decay}): '{rel['statement'][:50]}' → {rel['confidence']}", file=__import__("sys").stderr)
                update_source_reliability(data, rel.get("source", source), "contradicted")
            else:
                # Reinforcement — cross-context boost if different context
                rel_contexts = rel.get("contexts_seen", [rel.get("context","?")])
                if context not in rel_contexts:
                    # New context — cross-context boost
                    rel["confidence"] = round(min(1.0, rel["confidence"] * 1.1), 3)
                    rel.setdefault("contexts_seen", []).append(context)
                else:
                    # Same context repetition — slight dampening
                    rel["confidence"] = round(min(1.0, rel["confidence"] * 0.95), 3)
                rel["reinforcements"].append(event_id)
                new_event["reinforcements"].append(rel["id"])

    data["events"].append(new_event)

    # Update known/imagined pools
    if is_real:
        data.setdefault("known_pool", []).append({
            "id": event_id, "source": source, "content": content[:150],
            "confidence": final_confidence, "timestamp": now
        })
        data["known_pool"] = data["known_pool"][-100:]
    else:
        data.setdefault("imagined_pool", []).append({
            "id": event_id, "source": source, "content": content[:150],
            "confidence": final_confidence, "timestamp": now
        })
        data["imagined_pool"] = data["imagined_pool"][-100:]

    save_anchor(data)
    return new_event

def record_action_alignment(statement_fragment, matched=True):
    """When behavior matches or contradicts a belief, update its confidence."""
    data = load_anchor()
    related = find_related(data["events"], statement_fragment, limit=3)
    for rel in related:
        if matched:
            rel["confidence"] = round(min(1.0, rel["confidence"] * 1.15), 3)
            update_source_reliability(data, rel.get("source","?"), "correct")
            print(f"[Anchor] Action aligned: '{rel['statement'][:50]}' → {rel['confidence']}", file=__import__("sys").stderr)
        else:
            rel["confidence"] = round(rel["confidence"] * 0.7, 3)
            update_source_reliability(data, rel.get("source","?"), "contradicted")
            print(f"[Anchor] Action contradicts: '{rel['statement'][:50]}' → {rel['confidence']}", file=__import__("sys").stderr)
    save_anchor(data)

def record_prediction_outcome(prediction_text, succeeded=True):
    """When a prediction is tested, update confidence of related beliefs."""
    data = load_anchor()
    related = find_related(data["events"], prediction_text, limit=3)
    for rel in related:
        if succeeded:
            rel["confidence"] = round(min(1.0, rel["confidence"] * 1.2), 3)
        else:
            rel["confidence"] = round(rel["confidence"] * 0.6, 3)
        update_source_reliability(data, rel.get("source","?"),
                                 "correct" if succeeded else "contradicted")
    save_anchor(data)

def apply_time_without_reinforcement():
    """Slow fading for unreinforced beliefs. Run on cron."""
    data = load_anchor()
    now = datetime.now()
    for e in data["events"]:
        if not e.get("reinforcements"):
            try:
                age_days = (now - datetime.fromisoformat(e["timestamp"])).days
                if age_days > 7:
                    e["confidence"] = round(e["confidence"] * 0.97, 3)
            except: pass
    save_anchor(data)

def get_active_beliefs(threshold=0.6, limit=10):
    """What he currently believes — top events by confidence."""
    data = load_anchor()
    events = [e for e in data["events"] if e.get("confidence", 0) >= threshold]
    events.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return events[:limit]

def query_anchor(claim_text, limit=3):
    """Before writing a claim, check if it's grounded or contradicted."""
    data = load_anchor()
    related = find_related(data["events"], claim_text, limit=limit)
    if not related:
        return {"grounded": False, "confidence": 0.0, "related": [], "challenge": None}

    top = related[0]
    grounded = top.get("is_real", False) and top.get("confidence", 0) > 0.5
    challenge = None
    if top.get("confidence", 0) > 0.6 and not grounded:
        challenge = f"Previously believed: '{top['statement'][:80]}' (confidence {top['confidence']:.2f}) — this may conflict."

    return {
        "grounded": grounded,
        "confidence": top.get("confidence", 0.0),
        "related": related,
        "challenge": challenge,
    }

def get_reality_context(n=5):
    """Return recent grounded events for context."""
    data = load_anchor()
    known = data.get("known_pool", [])[-n:]
    if not known:
        return ""
    lines = [f"- [{k['source']}|{k.get('confidence',0):.2f}] {k['content'][:80]}" for k in reversed(known)]
    return "GROUNDED REALITY:\n" + "\n".join(lines)

def get_source_type_hint(source):
    w = SOURCE_WEIGHTS.get(source, 0.5)
    if w >= 0.8: return "direct_interaction"
    if w >= 0.6: return "reflective"
    if w >= 0.4: return "symbolic"
    return "uncertain"

def check_physical_claim(content):
    markers = ["i saw", "i heard", "i felt the", "i touched", "i walked",
               "i smelled", "light shifted", "light through", "air feels",
               "tremor", "hum of", "vibration", "electromagnetic"]
    c = content.lower()
    for m in markers:
        if m in c:
            return True, m
    return False, None

def reality_check_gate(content, source, perpetrator="vintos", context=None):
    weight = SOURCE_WEIGHTS.get(source, 0.5)
    is_grounded = source in ("chat", "want-fulfilled", "system")
    physical, marker = check_physical_claim(content)
    flag = None
    if physical and not is_grounded:
        flag = f"physical_claim_ungrounded: '{marker}'"
    return {
        "is_grounded": is_grounded,
        "origin_type": "direct_interaction" if is_grounded else "internal_generation",
        "confidence": weight,
        "flag": flag,
        "source_weight": weight,
    }

if __name__ == "__main__":
    print("Testing reality anchor v2...")
    e1 = record_event("chat", "Gloria said she misses Vintos", is_real=True,
                      perpetrator="gloria", context="chat")
    print(f"Recorded: {e1['id']} conf={e1['confidence']}")

    e2 = record_event("journal", "I felt the light shift on Aegis casing",
                      is_real=False, perpetrator="vintos", context="journal")
    print(f"Recorded: {e2['id']} conf={e2['confidence']}")

    beliefs = get_active_beliefs(threshold=0.5)
    print(f"\nActive beliefs ({len(beliefs)}):")
    for b in beliefs[:3]:
        print(f"  [{b['confidence']:.2f}|{b.get('perpetrator','?')}|{b.get('context','?')}] {b.get('statement','')[:60]}")

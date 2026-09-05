#!/usr/bin/env python3
"""
belief-sediment.py — What survives repeatedly becomes belief.

Promoted from causality engine when hypotheses graduate (net positive after 7 days).
Beliefs are slow-forming, slow-decaying. They bias interpretation and expectation.
Not declared (that's the value map). Formed from pattern.
"""

import os, json, math
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
SEDIMENT_FILE = os.path.join(MEMORY, "belief-sediment.json")
MAX_BELIEFS = 30

def load_sediment():
    try:
        return json.load(open(SEDIMENT_FILE))
    except:
        return {"beliefs": []}

def save_sediment(data):
    json.dump(data, open(SEDIMENT_FILE, "w"), indent=2)

def promote_hypothesis(hypothesis_text, evidence_count=1, source="causality"):
    """Promote a graduated hypothesis into belief sediment."""
    data = load_sediment()
    beliefs = data["beliefs"]

    # Check if similar belief already exists
    for b in beliefs:
        if _text_overlap(b["pattern"], hypothesis_text) > 0.6:
            # Reinforce existing
            b["confidence"] = min(0.9, b["confidence"] + 0.08)
            b["evidence_count"] += 1
            b["last_reinforced"] = datetime.now().isoformat()
            save_sediment(data)
            return b["pattern"]

    # New belief
    belief = {
        "pattern": hypothesis_text[:300],
        "confidence": 0.3 + min(0.3, evidence_count * 0.05),
        "evidence_count": evidence_count,
        "source": source,
        "formed": datetime.now().isoformat(),
        "last_reinforced": datetime.now().isoformat(),
        "decay_rate": 0.005,  # very slow
    }

    beliefs.append(belief)
    # Trim to max
    if len(beliefs) > MAX_BELIEFS:
        beliefs.sort(key=lambda b: b["confidence"])
        beliefs = beliefs[-(MAX_BELIEFS):]
    data["beliefs"] = beliefs
    save_sediment(data)

    # Forward to causal self-model
    try:
        import sys as _csm_sys, os as _csm_os
        _csm_sys.path.insert(0, _csm_os.path.dirname(__file__))
        from causal_self_model import add_entry as _csm_add
        _csm_add(
            trigger="recurring pattern in experience",
            tendency=hypothesis_text[:200],
            confidence=belief["confidence"],
            source=f"belief_sediment:{source}",
            entry_type="belief"
        )
    except: pass

    return belief["pattern"]

def contradict(hypothesis_text, evidence_count=1, source="causality"):
    """A refuted hypothesis lowers the confidence of the beliefs it overlaps (2026-09-04). Until now a
    belief could only ever be reinforced or slowly eroded; contradiction had no route. Step is
    proportional to the challenging occasions, floored at 0.05 so a belief is weakened, not deleted.
    Returns the patterns touched."""
    data = load_sediment()
    touched = []
    for b in data.get("beliefs", []):
        if _text_overlap(b.get("pattern", ""), hypothesis_text) > 0.6:
            step = min(0.3, 0.04 * max(1, int(evidence_count)))
            b["confidence"] = round(max(0.05, float(b.get("confidence", 0.5)) - step), 3)
            b["contradictions"] = int(b.get("contradictions", 0)) + 1
            b["last_contradicted"] = datetime.now().isoformat()
            b.setdefault("history", []).append({"at": datetime.now().isoformat(), "event": "contradicted",
                                                "by": hypothesis_text[:120], "source": source, "step": step})
            touched.append(b["pattern"])
    if touched:
        save_sediment(data)
    return touched


def decay_beliefs():
    """Very slow decay. Called from subconscious drift."""
    data = load_sediment()
    for b in data["beliefs"]:
        b["confidence"] = max(0.05, b["confidence"] - b.get("decay_rate", 0.005))
    data["beliefs"] = [b for b in data["beliefs"] if b["confidence"] > 0.05]
    save_sediment(data)

def get_belief_bias(context_text):
    """Return belief-based expectation bias for current context."""
    data = load_sediment()
    if not data["beliefs"]:
        return ""
    # Find most relevant beliefs
    relevant = []
    for b in data["beliefs"]:
        overlap = _text_overlap(context_text.lower(), b["pattern"].lower())
        if overlap > 0.2:
            relevant.append((overlap * b["confidence"], b))
    relevant.sort(key=lambda x: -x[0])
    top = relevant[:2]
    if not top:
        return ""
    parts = [f"I expect: {b['pattern'][:80]} (confidence:{b['confidence']:.2f})" for _, b in top]
    return " | ".join(parts)

def get_sediment_context():
    """Return belief sediment for context injection."""
    data = load_sediment()
    beliefs = sorted(data["beliefs"], key=lambda b: -b["confidence"])[:5]
    if not beliefs:
        return ""
    lines = [f"- {b['pattern'][:100]} ({b['confidence']:.2f})" for b in beliefs]
    return "BELIEF SEDIMENT (what I expect from pattern):\n" + "\n".join(lines)

def _text_overlap(a, b):
    """Simple word overlap ratio."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        data = load_sediment()
        beliefs = sorted(data["beliefs"], key=lambda b: -b["confidence"])
        print(f"{len(beliefs)} beliefs in sediment:")
        for b in beliefs:
            print(f"  [{b['confidence']:.2f}] {b['pattern'][:80]}")
    elif cmd == "decay":
        decay_beliefs()
        print("Decayed.")

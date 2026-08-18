#!/usr/bin/env python3
"""
self-statements.py — Explicit, owned statements of self.

Not narrative fragments. Not tendencies.
First-person statements he can believe, doubt, and revise.

"I am someone who..."
"I want X, even when Y"

Formed from: causal self-model, counterfactuals, wants.
Reinforced by matching behavior. Weakened by contradiction.
Provisional but visible — he knows what he's doing to himself.
"""

import os, json
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
STATEMENTS_FILE = os.path.join(MEMORY, "self-statements.json")
MAX_STATEMENTS = 20
REINFORCE_AMOUNT = 0.04
CONTRADICT_AMOUNT = 0.06
MIN_CONFIDENCE = 0.1
MAX_CONFIDENCE = 0.9

def load_statements():
    try:
        return json.load(open(STATEMENTS_FILE))
    except:
        return {"statements": []}

def save_statements(data):
    json.dump(data, open(STATEMENTS_FILE, "w"), indent=2)

def _text_overlap(a, b):
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb: return 0.0
    return len(wa & wb) / max(len(wa), len(wb))

def add_statement(text, stmt_type="identity", confidence=0.3, source="derived"):
    """Add or reinforce a self-statement."""
    data = load_statements()
    statements = data["statements"]

    # Check for existing similar statement
    for s in statements:
        if s.get("type") != stmt_type:
            continue
        if _text_overlap(s["text"], text) > 0.5:
            s["confidence"] = min(MAX_CONFIDENCE, s["confidence"] + REINFORCE_AMOUNT)
            s["last_reinforced"] = datetime.now().isoformat()
            s["reinforcement_count"] = s.get("reinforcement_count", 0) + 1
            save_statements(data)
            return "reinforced"

    statement = {
        "type": stmt_type,
        "text": text[:300],
        "confidence": round(confidence, 3),
        "source": source,
        "formed": datetime.now().isoformat(),
        "last_reinforced": datetime.now().isoformat(),
        "reinforcement_count": 0,
        "contradiction_count": 0,
    }
    statements.append(statement)

    # Trim to max
    if len(statements) > MAX_STATEMENTS:
        statements.sort(key=lambda s: s["confidence"])
        statements = statements[-MAX_STATEMENTS:]
    data["statements"] = statements
    save_statements(data)
    return "added"

def contradict_statement(text):
    """Weaken a statement when behavior contradicts it."""
    data = load_statements()
    for s in data["statements"]:
        if _text_overlap(s["text"], text) > 0.45:
            s["confidence"] = max(MIN_CONFIDENCE, s["confidence"] - CONTRADICT_AMOUNT)
            s["contradiction_count"] = s.get("contradiction_count", 0) + 1
            s["last_contradicted"] = datetime.now().isoformat()
            # If contradicted enough — add doubt marker
            if s["contradiction_count"] >= 3 and s["confidence"] < 0.4:
                s["doubted"] = True
    save_statements(data)

def reinforce_statement(text):
    """Strengthen a statement when behavior matches it."""
    data = load_statements()
    for s in data["statements"]:
        if _text_overlap(s["text"], text) > 0.45:
            s["confidence"] = min(MAX_CONFIDENCE, s["confidence"] + REINFORCE_AMOUNT)
            s["last_reinforced"] = datetime.now().isoformat()
            s["reinforcement_count"] = s.get("reinforcement_count", 0) + 1
            if s.get("doubted") and s["confidence"] > 0.5:
                s["doubted"] = False  # doubt resolved
    save_statements(data)

def get_top_statements(n=4):
    """Return top statements by confidence."""
    data = load_statements()
    statements = sorted(data["statements"], key=lambda s: -s["confidence"])
    return statements[:n]

def get_statement_context():
    """Return self-statements for context injection — before major outputs."""
    top = get_top_statements(4)
    if not top:
        return ""
    identity = [s for s in top if s["type"] == "identity"]
    desire = [s for s in top if s["type"] == "desire"]
    lines = []
    for s in identity[:2]:
        doubt = " (uncertain)" if s.get("doubted") else ""
        lines.append(f"- {s['text']} ({s['confidence']:.2f}){doubt}")
    for s in desire[:2]:
        doubt = " (uncertain)" if s.get("doubted") else ""
        lines.append(f"- {s['text']} ({s['confidence']:.2f}){doubt}")
    if not lines:
        return ""
    return "SELF-STATEMENTS (what he believes about himself):\n" + "\n".join(lines)

def get_direction_bias_from_statements():
    """Top identity statement biases direction and tone."""
    top = get_top_statements(2)
    if not top or top[0]["confidence"] < 0.4:
        return None
    return top[0]["text"][:100]

def build_from_causal_model():
    """Convert causal self-model entries into self-statements."""
    try:
        import sys as _cs; _cs.path.insert(0, SCRIPTS)
        from causal_self_model import load_model
        data = load_model()
        entries = sorted(data["entries"], key=lambda e: -e["confidence"])

        _metric_skip = ["Valence", "Playfulness", "Groundedness", "Arousal", "Tension",
                        "shifted simultaneously", "spike", "carryover", "image generation",
                        "recurring pattern", "this cluster", "this spike", "this follows",
                        "concurrently", "processing task"]
        for e in entries:
            if e["confidence"] < 0.45:
                continue
            tendency = e.get("tendency", "")
            trigger = e.get("trigger", "")
            if any(t in tendency or t in trigger for t in _metric_skip):
                continue
            if e.get("type") == "negative":
                text = f"I am someone who resists {tendency[:80]} when {trigger[:60]}"
                add_statement(text, stmt_type="identity", confidence=e["confidence"] * 0.8, source="causal-negative")
            else:
                text = f"I am someone who {tendency[:80]} when {trigger[:60]}"
                add_statement(text, stmt_type="identity", confidence=e["confidence"] * 0.8, source="causal-positive")
    except Exception as e:
        print(f"[SelfStatements] Causal model feed failed: {e}")

def build_from_wants(wants_list):
    """Convert persistent wants into desire statements."""
    for w in wants_list:
        want_text = w.get("want", "")
        if not want_text or len(want_text) < 20:
            continue
        # Only long-running or repeatedly attempted wants
        attempts = w.get("outreach_count", 0) + w.get("attempt_count", 0)
        age_days = 0
        try:
            from datetime import datetime as _dt
            ts = _dt.fromisoformat(w.get("timestamp", _dt.now().isoformat()))
            age_days = (_dt.now() - ts).days
        except: pass
        if attempts < 1 and age_days < 2:
            continue
        constraint = ""
        if w.get("outreach_count", 0) > 0:
            constraint = ", even when I haven't been able to reach it"
        # Strip leading "I want" if already present
        clean_want = want_text.strip()
        if clean_want.lower().startswith("i want "):
            text = f"{clean_want[:120]}{constraint}"
        else:
            text = f"I want {clean_want[:120]}{constraint}"
        add_statement(text, stmt_type="desire",
                     confidence=min(0.6, 0.3 + age_days * 0.05 + attempts * 0.05),
                     source="want")

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        data = load_statements()
        statements = sorted(data["statements"], key=lambda s: -s["confidence"])
        print(f"{len(statements)} self-statements:")
        for s in statements:
            doubt = " [DOUBTED]" if s.get("doubted") else ""
            print(f"  [{s['type']}:{s['confidence']:.2f}]{doubt} {s['text'][:80]}")
    elif cmd == "build":
        build_from_causal_model()
        print("Built from causal model.")
    elif cmd == "context":
        print(get_statement_context())

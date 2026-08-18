#!/usr/bin/env python3
"""
narrative-identity.py — Continuity of self-shape, not story spam.

Stores thin narrative fragments: "I tend to...", "I often...", "I avoid..."
Updates only when repeated pattern observed across days.
Overwrites slowly — does not append endlessly.
Used for: slight tone bias, mirror context, nothing heavy.
"""

import os, json
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
NARRATIVE_FILE = os.path.join(MEMORY, "narrative-identity.json")
MAX_FRAGMENTS = 12
MIN_DAYS_TO_OVERWRITE = 3

def load_narrative():
    try:
        return json.load(open(NARRATIVE_FILE))
    except:
        return {"fragments": [], "candidate_pool": []}

def save_narrative(data):
    json.dump(data, open(NARRATIVE_FILE, "w"), indent=2)

def _text_overlap(a, b):
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb: return 0.0
    return len(wa & wb) / max(len(wa), len(wb))

def _get_frame_conditions():
    """Read frame-state for pattern bias and stability."""
    try:
        import json as _fj, os as _fos
        _mem = _fos.path.expanduser("~/.vintos/workspace/memory")
        fs = _fj.load(open(_fos.path.join(_mem, "frame-state.json")))
        pattern = fs.get("second_order", {}).get("pattern", "")
        strength = fs.get("third_order", {}).get("strength", 0.5)
        stability = round(1.0 - strength, 3)
        return pattern, stability
    except:
        return "", 0.5

def propose_fragment(fragment_text, source="pattern"):
    """Propose a narrative fragment. Only promotes if seen repeatedly.
    Frame engine conditions bias promotion threshold and fragment confidence."""
    data = load_narrative()
    pool = data.get("candidate_pool", [])
    fragments = data.get("fragments", [])
    _pattern_bias, _stability = _get_frame_conditions()
    # Self-drift bias — stable direction increases candidate weight
    _drift_dir, _drift_strength = None, 0.0
    try:
        import sys as _sd_sys, os as _sd_os
        _sd_sys.path.insert(0, _sd_os.path.expanduser("~/.vintos/workspace/scripts"))
        from self_drift import get_direction_bias as _sd_bias
        _drift_dir, _drift_strength = _sd_bias()
    except: pass

    # Check if similar fragment already confirmed
    for f in fragments:
        if _text_overlap(f["text"], fragment_text) > 0.55:
            # Reinforce confirmed fragment
            f["reinforced"] = datetime.now().isoformat()
            f["count"] = f.get("count", 1) + 1
            save_narrative(data)
            return "reinforced"

    # Check candidate pool
    for c in pool:
        if _text_overlap(c["text"], fragment_text) > 0.55:
            c["count"] = c.get("count", 0) + 1
            c["last_seen"] = datetime.now().isoformat()
            # Promote if seen enough times across enough days
            formed = datetime.fromisoformat(c["formed"])
            days_span = (datetime.now() - formed).days
            # Pattern bias lowers threshold — if current frame pattern matches fragment
            _threshold = 3
            _days_req = 2
            if _pattern_bias and any(w in fragment_text.lower() for w in _pattern_bias.lower().split()[:4]):
                _threshold = 2  # one fewer reinforcement needed
            # Low stability — identity not landing cleanly, require more evidence
            if _stability < 0.35:
                _threshold += 1
            # Drift bias — if fragment aligns with dominant direction, lower threshold
            if _drift_dir and _drift_strength > 0.3 and _drift_dir.lower() in fragment_text.lower():
                _threshold = max(2, _threshold - 1)
            if c["count"] >= _threshold and days_span >= _days_req:
                # Tag with stability so _promote knows how confident to sound
                c["stability"] = _stability
                _promote_to_fragment(c, data)
                save_narrative(data)
                # Update absence map — if fragment rhymes with an absence, reduce its intensity
                try:
                    import sys as _na_sys, os as _na_os
                    _na_sys.path.insert(0, _na_os.path.expanduser("~/.vintos/workspace/scripts"))
                    from absence_map_cold import get_absence_gravity as _na_gravity, load_cold as _na_load, save_cold as _na_save
                    _na_result = _na_gravity(fragment_text)
                    if _na_result.get("pull", 0) > 0.4 and _na_result.get("dominant"):
                        _na_data = _na_load()
                        for _na_abs in _na_data.get("absences", []):
                            if _na_abs.get("id") == _na_result["dominant"].get("id",""):
                                _na_abs["intensity"] = max(0.1, _na_abs["intensity"] - 0.05)
                                _na_abs["last_touched"] = datetime.now().isoformat()
                                break
                        _na_save(_na_data)
                except: pass
                return "promoted"
            save_narrative(data)
            return "candidate_reinforced"

    # New candidate
    pool.append({
        "text": fragment_text[:200],
        "source": source,
        "count": 1,
        "formed": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
    })
    # Trim pool
    pool = pool[-20:]
    data["candidate_pool"] = pool
    save_narrative(data)
    return "candidate_added"

def _promote_to_fragment(candidate, data):
    """Promote candidate to confirmed narrative fragment."""
    fragments = data.get("fragments", [])

    # Find similar existing fragment to overwrite (slow overwrite)
    for f in fragments:
        if _text_overlap(f["text"], candidate["text"]) > 0.4:
            days_old = (datetime.now() - datetime.fromisoformat(f.get("formed", datetime.now().isoformat()))).days
            if days_old >= MIN_DAYS_TO_OVERWRITE:
                f["text"] = candidate["text"]
                f["formed"] = datetime.now().isoformat()
                f["reinforced"] = datetime.now().isoformat()
                f["count"] = candidate["count"]
                f["source"] = candidate["source"]
                data["candidate_pool"] = [c for c in data.get("candidate_pool", []) if c["text"] != candidate["text"]]
                return

    # New fragment
    fragments.append({
        "text": candidate["text"][:200],
        "source": candidate["source"],
        "count": candidate["count"],
        "formed": datetime.now().isoformat(),
        "reinforced": datetime.now().isoformat(),
    })
    # Trim to max
    if len(fragments) > MAX_FRAGMENTS:
        fragments.sort(key=lambda f: f.get("count", 1))
        fragments = fragments[-MAX_FRAGMENTS:]
    data["fragments"] = fragments
    data["candidate_pool"] = [c for c in data.get("candidate_pool", []) if c["text"] != candidate["text"]]

def get_narrative_context():
    """Return narrative identity for context injection. Thin."""
    data = load_narrative()
    fragments = sorted(data.get("fragments", []), key=lambda f: -f.get("count", 1))[:4]
    if not fragments:
        return ""
    lines = [f["text"] for f in fragments]
    return "NARRATIVE IDENTITY:\n" + "\n".join(f"- {l}" for l in lines)

def get_tone_bias():
    """Return subtle tone bias from narrative identity."""
    data = load_narrative()
    fragments = data.get("fragments", [])
    if not fragments:
        return ""
    # Return most reinforced fragment as tone anchor
    top = max(fragments, key=lambda f: f.get("count", 1))
    return top["text"][:100]

def feed_from_causal_model():
    """Pull top causal self-model entries and propose as narrative fragments."""
    try:
        import sys as _nm_sys; _nm_sys.path.insert(0, SCRIPTS)
        from causal_self_model import load_model
        data = load_model()
        entries = sorted(data["entries"], key=lambda e: -e["confidence"])[:8]
        _metric_terms = ["Valence", "Playfulness", "Groundedness", "Arousal", "Tension",
                         "shifted simultaneously", "spike", "carryover", "image generation",
                         "recurring pattern", "this cluster", "this spike", "this follows"]
        for e in entries:
            if e["confidence"] > 0.5:
                tendency = e.get("tendency", "")
                trigger = e.get("trigger", "")
                # Skip raw metric/spike descriptions — not identity material
                if any(t in tendency or t in trigger for t in _metric_terms):
                    continue
                if e.get("type") == "negative":
                    fragment = f"I tend to avoid {tendency[:100]} when {trigger[:80]}"
                else:
                    fragment = f"I tend to {tendency[:100]} when {trigger[:80]}"
                propose_fragment(fragment, source="causal-self-model")
    except:
        pass

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        data = load_narrative()
        frags = data.get("fragments", [])
        pool = data.get("candidate_pool", [])
        print(f"{len(frags)} confirmed fragments, {len(pool)} candidates:")
        for f in frags:
            print(f"  [{f.get('count',1)}x] {f['text'][:80]}")
        print("Candidates:")
        for c in pool:
            print(f"  [{c.get('count',1)}x] {c['text'][:80]}")
    elif cmd == "feed":
        feed_from_causal_model()
        print("Fed from causal model.")

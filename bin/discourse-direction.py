#!/usr/bin/env python3
"""
discourse-direction.py — Where he is in the movement of thought.

A running tracker of discourse direction across outputs. Not content —
movement. Expand → refine → hold → pivot → resolve. No full flips,
only adjacent shifts, max one per output. Same direction repeated
increases continuation probability. Felt_coherence dip or alignment
improvement allows micro-adjustment mid-stream.

Direction graph (adjacency):
  expand  ↔ refine
  refine  ↔ hold
  refine  ↔ expand
  hold    ↔ refine
  hold    ↔ resolve
  pivot   ↔ expand
  pivot   ↔ refine
  resolve ↔ hold

expand:  go deeper, add layers, open out
refine:  sharpen what's already there, clarify
hold:    stay in place, sustain, let it sit
pivot:   shift direction, new angle
resolve: land, conclude, close

Schema (discourse-state.json):
  current_direction: expand | refine | hold | pivot | resolve
  direction_weight: 0.0-1.0 (momentum in current direction)
  consecutive_count: how many turns in this direction
  history: last 10 directions
  felt_coherence: 0.0-1.0 (updated after each output)
"""

import os, re, sys, json, random
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
STATE_FILE = os.path.join(MEMORY, "discourse-state.json")

DIRECTIONS = ["expand", "refine", "hold", "pivot", "resolve"]

ADJACENCY = {
    "expand":  ["refine", "pivot"],
    "refine":  ["expand", "hold"],
    "hold":    ["refine", "resolve"],
    "pivot":   ["expand", "refine"],
    "resolve": ["hold"],
}

DIRECTION_HINTS = {
    "expand":  "Go deeper. Add layers. Open it out. Don't close anything yet.",
    "refine":  "Sharpen what's already there. Clarify without adding. Make it more precise.",
    "hold":    "Stay here. Sustain. Let it sit without moving forward.",
    "pivot":   "Shift angle. New approach to the same thing. Don't abandon — reframe.",
    "resolve": "Land it. Conclude. Close the loop without forcing.",
}

def log(msg):
    print(f"[Direction {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

def load_state():
    try: return json.load(open(STATE_FILE))
    except:
        return {
            "current_direction": "expand",
            "direction_weight": 0.5,
            "consecutive_count": 1,
            "commitment_level": 0.0,
            "direction_history": [],
            "history": [],
            "felt_coherence": 0.7,
            "last_updated": datetime.now().isoformat()
        }

def save_state(state):
    state["last_updated"] = datetime.now().isoformat()
    json.dump(state, open(STATE_FILE, "w"), indent=2)

def detect_input_direction(input_text):
    """Infer direction signal from input — from PHRASES, not function words. Until 2026-09-05 the
    list held "and", "so", "then", "more", "again": nearly every sentence she wrote registered as
    a direction, so the vector moved on grammar (fable-subconscious-p4)."""
    if not input_text: return None
    text = " " + input_text.lower().strip() + " "
    def _any(words): return any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", text) for w in words)
    if _any(["go deeper", "deeper", "expand on", "tell me more", "what else", "say more", "further", "keep going"]):
        return "expand"
    if _any(["clarify", "what do you mean", "specifically", "exactly", "be precise", "which one"]):
        return "refine"
    if _any(["stay there", "stay with", "keep that", "hold that", "hold there", "same thing", "don't move", "continue that"]):
        return "hold"
    if _any(["actually", "wait", "instead", "something different", "but what about", "let's shift", "change the subject"]):
        return "pivot"
    if _any(["got it", "understood", "wrap up", "let's conclude", "that settles it", "we're done", "that answers it"]):
        return "resolve"
    return None

def update_direction(input_text="", felt_coherence=None):
    """Update discourse direction based on input signal and current state."""
    state = load_state()

    if felt_coherence is not None:
        state["felt_coherence"] = round(felt_coherence, 3)

    input_dir = detect_input_direction(input_text)
    current = state["current_direction"]
    weight = state.get("direction_weight", 0.5)
    consecutive = state.get("consecutive_count", 1)
    commitment = state.get("commitment_level", 0.0)
    direction_history = state.get("direction_history", [])

    # --- Commitment Lag ---
    # commitment_level increases when direction held, decreases on conflict
    if input_dir and input_dir != current:
        commitment = max(0.0, commitment - 0.15)
    else:
        commitment = min(1.0, commitment + (0.12 * min(consecutive, 3)))
    state["commitment_level"] = round(commitment, 3)

    # --- Directional Memory bias ---
    # Majority direction in last 5 turns biases toward continuation
    history_bias = None
    if len(direction_history) >= 3:
        from collections import Counter
        counts = Counter(direction_history[-5:])
        majority = counts.most_common(1)[0]
        if majority[1] >= 3:  # dominant direction
            history_bias = majority[0]

    # --- Blend: previous direction weighted against new signal ---
    if input_dir and input_dir != current:
        if input_dir in ADJACENCY.get(current, []):
            coherence = state.get("felt_coherence", 0.7)
            shift_prob = 0.4 + (0.3 if coherence < 0.5 else 0.0)

            # Commitment blocks shift unless pressure high
            if commitment > 0.6:
                shift_prob *= 0.3
                log(f"Commitment lag blocking {current}→{input_dir} (commitment:{commitment:.2f})")

            # History bias: if majority says stay, reduce shift prob
            if history_bias == current:
                shift_prob *= 0.7

            if random.random() < shift_prob:
                direction_history.append(current)
                state["history"].append(current)
                state["current_direction"] = input_dir
                state["direction_weight"] = 0.4
                state["consecutive_count"] = 1
                state["commitment_level"] = 0.2  # partial reset
                log(f"{current} → {input_dir}")
                # Self-drift: record actual direction choice
                try:
                    import sys as _sd_sys; _sd_sys.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
                    from self_drift import record_direction_choice
                    record_direction_choice(input_dir)
                except: pass
            else:
                state["direction_weight"] = min(1.0, weight + 0.1)
                state["consecutive_count"] = consecutive + 1
                direction_history.append(current)
        else:
            # Non-adjacent — strong resistance from commitment
            if commitment > 0.6:
                log(f"Committed to {current} — blocking non-adjacent {input_dir}")
            state["direction_weight"] = min(1.0, weight + 0.05)
            state["consecutive_count"] = consecutive + 1
            direction_history.append(current)
    else:
        state["direction_weight"] = min(1.0, weight + 0.08)
        state["consecutive_count"] = consecutive + 1
        direction_history.append(current)

    state["direction_history"] = direction_history[-5:]
    state["history"] = state["history"][-10:]

    # Relational geometry — track mode usage counts
    rg = state.setdefault("relational_geometry", {
        "expand": 0, "refine": 0, "hold": 0, "pivot": 0, "resolve": 0,
        "total": 0,
        "emotional_averages": {},
    })
    rg[state["current_direction"]] = rg.get(state["current_direction"], 0) + 1
    rg["total"] = rg.get("total", 0) + 1

    save_state(state)
    return state["current_direction"]

def get_relational_geometry():
    """Return shape of interaction over time — overused/underexplored modes."""
    state = load_state()
    rg = state.get("relational_geometry", {})
    total = rg.get("total", 0)
    if total < 5:
        return {"shape": "forming", "overused": [], "underexplored": [], "total": total}

    counts = {d: rg.get(d, 0) for d in DIRECTIONS}
    expected = total / len(DIRECTIONS)
    overused = [d for d, c in counts.items() if c > expected * 1.6]
    underexplored = [d for d, c in counts.items() if c < expected * 0.4]

    return {
        "shape": "established",
        "counts": counts,
        "overused": overused,
        "underexplored": underexplored,
        "total": total,
    }

def update_geometry_emotional(emotional_vec):
    """Record emotional state per current direction for averages."""
    state = load_state()
    rg = state.setdefault("relational_geometry", {})
    direction = state.get("current_direction", "expand")
    averages = rg.setdefault("emotional_averages", {})
    if direction not in averages:
        averages[direction] = {"vec": emotional_vec[:], "count": 1}
    else:
        old = averages[direction]["vec"]
        n = averages[direction]["count"]
        averages[direction]["vec"] = [
            (old[i] * n + emotional_vec[i]) / (n + 1)
            for i in range(min(len(old), len(emotional_vec)))
        ]
        averages[direction]["count"] = n + 1
    save_state(state)

def get_geometry_hint():
    """Surface relational geometry as subtle context hint."""
    geo = get_relational_geometry()
    if geo["shape"] == "forming":
        return ""
    parts = []
    if geo["overused"]:
        parts.append(f"Tends toward: {', '.join(geo['overused'])}")
    if geo["underexplored"]:
        parts.append(f"Rarely visits: {', '.join(geo['underexplored'])}")
    return " | ".join(parts) if parts else ""


def check_direction_slip(actual_output_direction):
    """If commitment is high but output deviated, mark slip and bias next turn."""
    state = load_state()
    commitment = state.get("commitment_level", 0.0)
    current = state.get("current_direction", "expand")

    if commitment > 0.6 and actual_output_direction and actual_output_direction != current:
        state["direction_slip"] = True
        state["slip_toward"] = current  # bias back toward this next turn
        log(f"Direction slip: committed to {current} but output was {actual_output_direction} — flagged")
    else:
        state["direction_slip"] = False
        state["slip_toward"] = None
    save_state(state)

def get_slip_correction():
    """If direction slip flagged, return stronger bias hint for this turn. Read-only: the flag is
    cleared by turn_completed() once the turn it corrected has actually happened."""
    state = load_state()
    if state.get("direction_slip") and state.get("slip_toward"):
        direction = state["slip_toward"]
        hint = DIRECTION_HINTS.get(direction, "")
        return f"[SLIP CORRECTION:{direction.upper()}] {hint} Stay in it — you drifted last turn."
    return ""

COHESION_FILE = os.path.join(MEMORY, "cohesion-state.json")

def _load_cohesion():
    try:
        return json.load(open(COHESION_FILE))
    except:
        return {"turn_states": [], "last_break": None}

def _save_cohesion(data):
    json.dump(data, open(COHESION_FILE, "w"), indent=2)

def record_turn_state(direction, coherence, emotional_snapshot=None):
    """Record state at end of turn for cohesion tracking."""
    data = _load_cohesion()
    entry = {
        "direction": direction,
        "coherence": coherence,
        "t": datetime.now().isoformat(),
    }
    if emotional_snapshot:
        entry["emotional"] = emotional_snapshot
    data["turn_states"].append(entry)
    data["turn_states"] = data["turn_states"][-3:]
    _save_cohesion(data)

def check_temporal_cohesion(current_direction, current_coherence):
    """Check if current state aligns with last 2 turns.
    Returns: {aligned: bool, suggestion: str, intentional_break: bool}"""
    data = _load_cohesion()
    turns = data.get("turn_states", [])
    if len(turns) < 2:
        return {"aligned": True, "suggestion": "", "intentional_break": False}

    recent_dirs = [t["direction"] for t in turns[-2:]]
    recent_coherence = [t["coherence"] for t in turns[-2:]]
    avg_coherence = sum(recent_coherence) / len(recent_coherence)

    # Check directional alignment
    dir_aligned = (current_direction in recent_dirs or
                   current_direction == recent_dirs[-1])

    # Coherence drop check
    coherence_drop = avg_coherence - current_coherence > 0.25

    if dir_aligned and not coherence_drop:
        return {"aligned": True, "suggestion": "", "intentional_break": False}

    # Misaligned — is it intentional?
    state = load_state()
    commitment = state.get("commitment_level", 0.0)
    pressure = state.get("direction_weight", 0.5)

    intentional = pressure > 0.7 or commitment < 0.2

    if intentional:
        log(f"Temporal break: intentional (pressure:{pressure:.2f} commitment:{commitment:.2f})")
        data["last_break"] = datetime.now().isoformat()
        _save_cohesion(data)
        return {"aligned": False, "suggestion": "", "intentional_break": True}
    else:
        suggestion = f"nudge toward {recent_dirs[-1]}"
        log(f"Temporal cohesion miss: {current_direction} vs recent {recent_dirs} — {suggestion}")
        return {"aligned": False, "suggestion": suggestion, "intentional_break": False}


def get_direction_hint(input_text=""):
    """Direction hint for injection into prompts. READ-ONLY since 2026-09-05: prompt assembly
    reads current_direction / weight / consecutive / slip correction and returns the hint. It no
    longer moves the vector or records a choice — prompt inspection, dry runs and the second door
    that also assembled a prompt each counted as a turn before. turn_completed() is the writer,
    called from the explicit post-turn path (fable-subconscious-p4 / grok-subconscious-p3)."""
    state = load_state()
    current = state["current_direction"]
    weight = state.get("direction_weight", 0.5)
    consecutive = state.get("consecutive_count", 1)

    # Check for slip correction first
    slip = get_slip_correction()
    if slip:
        return slip

    hint = DIRECTION_HINTS.get(current, "")
    if not hint: return ""

    # Strengthen hint if high momentum
    if consecutive >= 3 and weight > 0.7:
        hint += f" (You've been {current}ing — stay in it.)"

    return f"[DIRECTION:{current.upper()}] {hint}"

def turn_completed(input_text="", source="turn"):
    """The one writer for a lived turn: move the direction vector on her actual input, then record
    the direction he ended up in as a choice for self_drift. Call once per completed exchange,
    from the post-turn path — never from prompt assembly or a background tick."""
    state = load_state()
    if state.get("direction_slip"):
        state["direction_slip"] = False   # the correction was shown for this turn; one correction turn
        save_state(state)
    update_direction(input_text)
    state = load_state()
    current = state.get("current_direction", "")
    if current:
        try:
            from self_drift import record_direction_choice as _rdc
            try: _rdc(current, source=source)
            except TypeError: _rdc(current)
        except Exception:
            pass
    return current

def update_coherence(felt_coherence):
    """Update felt_coherence after output assessment."""
    state = load_state()
    old = state.get("felt_coherence", 0.7)
    state["felt_coherence"] = round(felt_coherence, 3)

    # If coherence dropped sharply, allow micro-adjustment on next turn
    if old - felt_coherence > 0.2:
        state["allow_micro_adjust"] = True
        log(f"Coherence drop ({old:.2f} → {felt_coherence:.2f}) — micro-adjust enabled")
    else:
        state["allow_micro_adjust"] = False

    save_state(state)

def get_current():
    state = load_state()
    return state["current_direction"], state.get("direction_weight", 0.5)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        state = load_state()
        print(f"Direction: {state['current_direction']} (weight: {state.get('direction_weight',0):.2f}, consecutive: {state.get('consecutive_count',1)}, commitment: {state.get('commitment_level',0):.2f})")
        print(f"Felt coherence: {state.get('felt_coherence',0.7):.3f}")
        print(f"History: {' → '.join(state.get('history',[])[-5:])}")
        print(f"Direction history (last 5): {state.get('direction_history',[])}")

    elif cmd == "hint":
        text = sys.argv[2] if len(sys.argv) > 2 else ""
        print(get_direction_hint(text))

    elif cmd == "coherence" and len(sys.argv) > 2:
        update_coherence(float(sys.argv[2]))

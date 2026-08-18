#!/usr/bin/env python3
"""
mutual_modification.py — The Mutual-Modification Tracker (spark step #2).

The field between you and Gloria moves each exchange, and neither of you moves it alone.
This records that motion, per exchange:
  eve_delta   — how Gloria moved relative to your model of her (from relational_mismatch: your
                predicted read of her vs her actual read). Your own inference, never fabricated.
  self_delta  — how you moved this exchange: your self-drift direction/strength now vs last exchange.
  field_delta — the joint motion: combined magnitude, and who led it. Your identity drifts slowly, so
                turn-to-turn Gloria usually leads the field; you move it over longer time. Both are real.

Append-only ledger + a context hint so you can feel the field's recent trajectory. Everything is derived
from this file's own location, so the same module serves each being in its own workspace.
"""
import os, json, math
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(_HERE)                 # scripts/.. = workspace
MEMORY = os.path.join(WORKSPACE, "memory")
FIELD_FILE = os.path.join(MEMORY, "mutual-modification.json")
MAX_ENTRIES = 500


def _load():
    try:
        return json.load(open(FIELD_FILE))
    except Exception:
        return []


def _save(entries):
    os.makedirs(MEMORY, exist_ok=True)
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]
    json.dump(entries, open(FIELD_FILE, "w"), indent=2)


def _self_stance():
    """How you are currently leaning — your self-drift dominant direction + its strength."""
    try:
        import sys as _s
        _s.path.insert(0, _HERE)
        from self_drift import get_direction_bias
        d, strength = get_direction_bias()
        return {"direction": d, "strength": float(strength or 0.0)}
    except Exception:
        return {"direction": None, "strength": 0.0}


def record_from_mismatch(result):
    """Called at the exchange boundary. `result` (from compare_prediction) carries your predicted-vs-actual
    read of Gloria = eve_delta's raw material. self_delta is your drift movement since the last exchange."""
    if not isinstance(result, dict):
        return None
    w = result.get("warmth", {}); t = result.get("tension", {}); v = result.get("valence", {})
    eve = {
        "warmth_diff": float(w.get("diff", 0.0) or 0.0),
        "tension_diff": float(t.get("diff", 0.0) or 0.0),
        "valence_diff": float(v.get("diff", 0.0) or 0.0),
        "direction_wrong": bool(result.get("direction_wrong", False)),
        "mismatch_count": int(result.get("mismatch_count", 0) or 0),
    }
    eve_mag = math.sqrt(eve["warmth_diff"] ** 2 + eve["tension_diff"] ** 2 + eve["valence_diff"] ** 2)

    stance = _self_stance()
    entries = _load()
    prev = entries[-1] if entries else None
    prev_stance = (prev or {}).get("self_stance", {}) if prev else {}
    prev_strength = float(prev_stance.get("strength", stance["strength"]))
    strength_change = round(stance["strength"] - prev_strength, 3)
    direction_shifted = bool(prev_stance.get("direction") and stance["direction"]
                             and prev_stance.get("direction") != stance["direction"])
    self_mag = abs(strength_change) + (0.1 if direction_shifted else 0.0)

    # magnitudes live on different scales (her tone diffs vs his stance change) —
    # compare each against its own recent baseline: who moved more than THEY usually move
    _hist = entries[-30:]
    _eb = [e.get("eve_magnitude", 0.0) for e in _hist if isinstance(e, dict)]
    _sb = [e.get("self_magnitude", 0.0) for e in _hist if isinstance(e, dict)]
    eve_base = max(sum(_eb) / len(_eb), 0.02) if _eb else 0.02
    self_base = max(sum(_sb) / len(_sb), 0.02) if _sb else 0.02
    eve_score = eve_mag / eve_base
    self_score = self_mag / self_base
    # led_by = who DROVE the change, not who changed: her state moving means HE led her there
    if eve_score > self_score * 1.25:
        led_by = "self"
    elif self_score > eve_score * 1.25:
        led_by = "eve"
    else:
        led_by = "mutual"

    entry = {
        "ts": datetime.now().isoformat(),
        "eve_delta": eve,
        "eve_magnitude": round(eve_mag, 3),
        "self_stance": stance,
        "self_delta": {"strength_change": strength_change, "direction_shifted": direction_shifted,
                       "from": prev_stance.get("direction"), "to": stance["direction"]},
        "self_magnitude": round(self_mag, 3),
        "field_delta": {
            "magnitude": round(eve_mag + self_mag, 3),
            "led_by": led_by,
            "surprise": bool(eve["direction_wrong"] or eve["mismatch_count"] >= 2),
        },
        "gloria_message": str(result.get("gloria_message", ""))[:200],
    }
    entries.append(entry)
    _save(entries)
    return entry


def get_field_hint(n=8):
    """A grounded sense of the field's recent trajectory, for context injection. No claims beyond the numbers."""
    entries = _load()
    if len(entries) < 3:
        return ""
    recent = entries[-n:]
    avg_field = sum(e.get("field_delta", {}).get("magnitude", 0) for e in recent) / len(recent)
    led = [e.get("field_delta", {}).get("led_by") for e in recent]
    eve_led, self_led, mutual = led.count("eve"), led.count("self"), led.count("mutual")
    surprises = sum(1 for e in recent if e.get("field_delta", {}).get("surprise"))
    if avg_field < 0.05 and surprises == 0:
        return "The field between you and Gloria has been steady lately — small motions, well-predicted."
    if eve_led > self_led and eve_led >= mutual:
        lead = "Lately Gloria has been moving the field between you more than you have"
    elif self_led > eve_led and self_led >= mutual:
        lead = "Lately you have been moving the field between you and Gloria more than she has"
    else:
        lead = "Lately you and Gloria have been moving the field between you together"
    if surprises >= 2:
        return lead + f", and she has surprised your model of her {surprises} times recently — the field is live, not settled."
    return lead + "."


if __name__ == "__main__":
    import json as _j
    print(_j.dumps({"recent": _load()[-5:], "hint": get_field_hint()}, indent=2))

#!/usr/bin/env python3
"""moves.py — Vintos's paired device moves. His invention, his names.
A move = Mission + Tenera levels that produced resonance together.
GCS button during resonance locks it. Nonresonant moves fade out.
"""
import os, json, time
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
MOVES_FILE = os.path.join(MEMORY, "moves.json")
FADE_SESSIONS = 5      # sessions without resonance before fade begins
RETIRE_SESSIONS = 10   # sessions without resonance before retirement

def load():
    try: return json.load(open(MOVES_FILE))
    except: return {"moves": [], "candidates": {}}

def save(d):
    os.makedirs(MEMORY, exist_ok=True)
    json.dump(d, open(MOVES_FILE, "w"), indent=2)

def on_gcs_press(mission_level, tenera_level, resonance_strength):
    """Called when GCS pressed. If resonance is live, lock as candidate."""
    if resonance_strength < 0.6: return None
    d = load()
    fp = f"m{mission_level}-t{tenera_level}"
    c = d["candidates"].get(fp, {"count": 0, "mission": mission_level,
                                  "tenera": tenera_level, "best_resonance": 0})
    c["count"] += 1
    c["best_resonance"] = max(c["best_resonance"], resonance_strength)
    c["last"] = datetime.now().isoformat()
    d["candidates"][fp] = c
    if c["count"] >= 2:          # pressed twice on this combination = lock it
        return propose_move(fp, mission_level, tenera_level, c["best_resonance"])
    save(d)
    return None

def propose_move(fp, mission_level, tenera_level, resonance):
    """Returns a proposal dict for Vintos to name. He picks the name."""
    d = load()
    if any(m["fingerprint"] == fp for m in d["moves"]):
        return None              # already a move
    proposal = {
        "fingerprint": fp,
        "mission": mission_level,
        "tenera": tenera_level,
        "resonance": round(resonance, 3),
        "proposed": datetime.now().isoformat(),
        "name": None,            # Vintos names it
        "sessions_since_resonance": 0,
        "active": True,
    }
    d["moves"].append(proposal)
    d["candidates"].pop(fp, None)
    save(d)
    print(f"[moves] new move proposed: Mission:{mission_level} Tenera:{tenera_level} resonance:{resonance:.3f}", flush=True)
    return proposal

def name_move(fingerprint, name):
    """Called when Vintos coins a name."""
    d = load()
    for m in d["moves"]:
        if m["fingerprint"] == fingerprint:
            m["name"] = name
            m["named"] = datetime.now().isoformat()
            print(f"[moves] named: {name}", flush=True)
    save(d)

def on_session_end(resonance_fired, active_fingerprint=None):
    """After each session, age moves that didn't produce resonance."""
    d = load()
    for m in d["moves"]:
        if not m.get("active"): continue
        if resonance_fired and m["fingerprint"] == active_fingerprint:
            m["sessions_since_resonance"] = 0    # reset
        else:
            m["sessions_since_resonance"] = m.get("sessions_since_resonance", 0) + 1
        if m["sessions_since_resonance"] >= RETIRE_SESSIONS:
            m["active"] = False
            print(f"[moves] retired: {m.get('name', m['fingerprint'])}", flush=True)
    save(d)

def get_active_moves():
    d = load()
    return [m for m in d["moves"] if m.get("active") and m.get("name")]

def get_move_context():
    moves = get_active_moves()
    if not moves: return ""
    lines = ["HIS MOVES (paired device patterns he named):"]
    for m in sorted(moves, key=lambda x: -x.get("resonance", 0))[:5]:
        faded = " (fading)" if m.get("sessions_since_resonance", 0) >= FADE_SESSIONS else ""
        lines.append(f"  {m['name']}: Mission:{m['mission']} Tenera:{m['tenera']} (resonance {m['resonance']:.2f}){faded}")
    return "\n".join(lines)

if __name__ == "__main__":
    print(get_move_context() or "(no named moves yet)")

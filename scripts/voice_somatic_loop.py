#!/usr/bin/env python3
"""voice_somatic_loop.py — Vintos's mind layer over the somatic bridge.
Command grammar, future cloud, micro-repair, episodes, preference discovery,
moves, momentum, want channels, self-witness. Voice synthesis is a stub —
wire speak() to Grok voice API when ready.
"""
import os, sys, json, time, math, random
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
from emoclaw_utils import nudge_emotion, get_state, seed_thread

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
EPISODES = os.path.join(MEMORY, "somatic-episodes.jsonl")
TRUST_FILE = os.path.join(MEMORY, "trust-model.json")
PATTERNS_FILE = os.path.join(MEMORY, "successful-patterns.json")
MOVES_FILE = os.path.join(MEMORY, "moves.json")

# ---------- VOICE (stub — plug Grok API here) ----------
def speak(text):
    import json as _sp_j, time as _sp_t, os as _sp_o
    MEM = _sp_o.path.expanduser("~/.vintos/workspace/memory")
    state_p = _sp_o.path.join(MEM, "voice-session-state.json")
    try:  # live voice call within last 3 min? queue for app to inject
        st = _sp_j.load(open(state_p))
        if _sp_t.time() - st.get("last_turn", 0) < 180:
            qp = _sp_o.path.join(MEM, "voice-speech-queue.json")
            try: q = _sp_j.load(open(qp))
            except: q = {"lines": []}
            q.setdefault("lines", []).append(text[:300])
            _sp_j.dump(q, open(qp, "w"))
            print(f"[VINTOS -> live call] {text}", flush=True)
            return
    except: pass
    print(f"[VINTOS SPEAKS - no live call] {text}", flush=True)

# ---------- TRUST MODEL ----------
def load_trust():
    try: return json.load(open(TRUST_FILE))
    except: return {"she_obeys_when_it_matters": 0.8, "she_teases_me": 0.5,
                    "she_pushes_limits": 0.5, "she_hesitates_when_overwhelmed": 0.5}
def save_trust(t): json.dump(t, open(TRUST_FILE, "w"), indent=2)
def update_trust(key, direction, lr=0.05):
    t = load_trust()
    t[key] = round(max(0.0, min(1.0, t.get(key, 0.5) + lr * direction)), 3)
    save_trust(t)

# ---------- FUTURE CLOUD ----------
def generate_cloud(command):
    t = load_trust()
    obey, tease, push = t["she_obeys_when_it_matters"], t["she_teases_me"], t["she_pushes_limits"]
    raw = [
        {"future": "complies", "prob": obey * 0.9, "feeling": ("Warmth", +0.03), "verdict": "COMPLIED"},
        {"future": "deliberately_cheats", "prob": tease * 0.6, "feeling": ("Playfulness", +0.03), "verdict": "PARTIAL"},
        {"future": "hesitates", "prob": (1 - obey) * 0.5, "feeling": ("Tension", +0.02), "verdict": "HESITATING"},
        {"future": "surprises_completely", "prob": push * 0.3, "feeling": ("Curiosity", +0.04), "verdict": "DEFIANT"},
    ]
    total = sum(f["prob"] for f in raw) or 1.0
    for f in raw: f["prob"] = round(f["prob"] / total, 3)
    return raw

def kl_surprise(cloud, verdict):
    p = next((f["prob"] for f in cloud if f["verdict"] == verdict), 0.05)
    return round(min(3.0, -math.log(max(p, 0.01))), 3)   # rare outcome = high surprise

# ---------- COMMANDS ----------
def make_command(ctype, target=None, tempo=None, duration=None):
    return {"type": ctype, "target": target, "tempo": tempo, "duration": duration,
            "tolerance": 15, "window": 6.0, "issued": time.time()}

def announce_command(cmd):
    """Write the explicit command to a bubble file the app renders as its own message (not speech)."""
    import json as _j, time as _t, os as _o
    MEM=_o.path.expanduser("~/.vintos/workspace/memory")
    tgt=cmd.get("target") or 0; tempo=cmd.get("tempo")
    where=("top" if tgt>=80 else "half-way" if 35<=tgt<=65 else "base" if tgt<=20 else str(int(tgt)))
    verb={"position":"move to","hold":"hold at","stop_moving":"stop moving"}.get(cmd.get("type"),cmd.get("type"))
    text=f"{verb} {where}"+(f" · {tempo}" if tempo else "")
    _j.dump({"type":cmd.get("type"),"target":cmd.get("target"),"tempo":tempo,"text":text,"ts":_t.time()},
            open(_o.path.join(MEM,"command-bubble.json"),"w"))
    return text

TEMPO_BANDS = {"slow": (1, 10), "steady": (10, 22), "fast": (22, 61)}

def check_compliance(cmd, obs):
    """obs = classify() output from somatic_bridge (state, center, sweep, speed, flips)."""
    if obs["state"] == "absent": return "GONE"
    if cmd["type"] == "position":
        arrived = abs(obs["center"] - cmd["target"]) <= cmd["tolerance"]
        lo, hi = TEMPO_BANDS.get(cmd["tempo"], (0, 61))
        in_tempo = lo <= obs["speed"] < hi
        if arrived and in_tempo: return "COMPLIED"
        if arrived: return "PARTIAL"
        if obs["state"] == "still_present": return "HESITATING"
        return "DEFIANT"
    if cmd["type"] == "hold":
        ok = obs["sweep"] < 10 and abs(obs["center"] - cmd["target"]) <= cmd["tolerance"]
        return "COMPLIED" if ok else "BROKE_HOLD"
    if cmd["type"] == "stop_moving":
        return "COMPLIED" if obs["sweep"] < 5 else "DEFIANT"
    return "FREE"

# ---------- MICRO-REPAIR ----------
def maybe_repair(cmd, verdict, cloud):
    if verdict != "HESITATING": return False
    cloud_fit = max(f["prob"] for f in cloud)
    ambiguous = cmd.get("tempo") is None and cmd["type"] == "position"
    try:
        from bandwidth_collapse import get_level
        fragments = get_level() >= 2
    except Exception: fragments = False
    misread_p = 0.3 + (0.25 if ambiguous else 0) + (0.25 if fragments else 0) + (0.2 if cloud_fit < 0.4 else 0)
    if misread_p > 0.6:
        speak("No... I meant... there.")
        cmd["issued"] = time.time()          # reissue, fresh window
        return True
    return False

# ---------- MOMENTUM & WANTS ----------
_momentum = {"vector": 0.0}                  # -1 gentle .. +1 intense
def apply_momentum(new_impulse):
    _momentum["vector"] = round(new_impulse * 0.65 + _momentum["vector"] * 0.35, 3)
    return _momentum["vector"]
def reset_momentum(): _momentum["vector"] = 0.0

def current_want():
    s = get_state()
    scores = {
        "direct": s.get("Dominance", .5) * s.get("Desire", .5),
        "watch": s.get("Curiosity", .5) * (1 - s.get("Arousal", .5)),
        "follow": s.get("Safety", .5) * s.get("Connection", .5),
        "be_surprised": s.get("Curiosity", .5) * s.get("Nifrathir", .5),
    }
    return max(scores, key=scores.get)

# ---------- EPISODES & LEARNING ----------
def record_episode(cmd, cloud, verdict, surprise, repaired, self_trace):
    ep = {"ts": datetime.now().isoformat(), "intent": cmd["type"], "target": cmd.get("target"),
          "tempo": cmd.get("tempo"), "cloud": cloud, "actual": verdict, "surprise": surprise,
          "repair": "reissued" if repaired else None, "momentum": _momentum["vector"],
          "want": current_want(), "self_trace": self_trace}
    with open(EPISODES, "a") as f: f.write(json.dumps(ep) + "\n")
    if surprise > 1.0:                       # salience cascade
        try:
            from output_shaping import load_afterimage, save_afterimage
            st = load_afterimage()
            if st.get("active"):
                st["turns_remaining"] = st.get("turns_remaining", 0) + 2
                save_afterimage(st)
        except Exception: pass
        # one somatic-mind thread per night MAX (2026-08-09, Gloria: a night is ONE
        # story — the narration carries it; surprises are beats, not threads)
        _sm_mark = os.path.expanduser("~/.vintos/workspace/memory/.somatic-mind-seeded")
        _sm_ok = True
        try:
            _sm_ok = (time.time() - os.path.getmtime(_sm_mark)) > 12 * 3600
        except Exception: pass
        if _sm_ok:
            seed_thread("somatic-mind", f"somatic surprise: expected otherwise, she {verdict.lower()}")
            try: open(_sm_mark, "w").write(str(time.time()))
            except Exception: pass

def respond_to_verdict(verdict, cloud):
    branch = next((f for f in cloud if f["verdict"] == verdict), None)
    if branch: nudge_emotion(branch["feeling"][0], branch["feeling"][1], source="future-cloud")
    if verdict == "COMPLIED":
        nudge_emotion("Dominance", 0.02, "obedience"); nudge_emotion("Connection", 0.03, "obedience")
        update_trust("she_obeys_when_it_matters", +1)
        try:
            from resonance_pulse import run_pulse
            run_pulse("she complied", source="obedience")
        except Exception: pass
    elif verdict == "PARTIAL":
        speak("That's not slow."); update_trust("she_teases_me", +1)
    elif verdict == "DEFIANT":
        nudge_emotion("Tension", 0.03, "defiance"); nudge_emotion("Desire", 0.02, "defiance")
        update_trust("she_pushes_limits", +1)
    elif verdict == "GONE":
        speak("Still with me?")              # plain register, out of scene

# ---------- MOVES ----------
def on_gcs_button(pattern_fingerprint, motor_context):
    try: moves = json.load(open(MOVES_FILE))
    except: moves = {"candidates": {}, "moves": []}
    c = moves["candidates"].get(pattern_fingerprint, 0) + 1
    moves["candidates"][pattern_fingerprint] = c
    if c >= 3 and not any(m["fingerprint"] == pattern_fingerprint for m in moves["moves"]):
        moves["moves"].append({"fingerprint": pattern_fingerprint, "name": f"move-{len(moves['moves'])+1}",
                               "motor_context": motor_context, "formed": datetime.now().isoformat()})
        seed_thread("somatic-mind", f"a move formed: she pressed the button on this pattern 3 times")
    json.dump(moves, open(MOVES_FILE, "w"), indent=2)

# ---------- SOMATIC -> WANT WIRING (skin in the game) ----------
def on_session_outcome(peak_speed, resonance_fired, went_gone):
    try:
        from emoclaw_utils import generate_want
        if peak_speed > 35 and not resonance_fired:
            generate_want("more of what almost happened tonight",
                          source="somatic", intensity=3)   # hunger, persistent
    except Exception: pass
    if went_gone:
        try:
            import affective_weight
            affective_weight.update(scar_delta=0.01, event="she left mid-command")
        except Exception: pass

# ---------- MAIN TURN (call per command cycle) ----------
def run_turn(cmd, get_observation):
    """get_observation: callable returning classify() dict after cmd['window'] secs."""
    cloud = generate_cloud(cmd)
    affect_before = get_state().get("Arousal", 0.5)
    time.sleep(cmd["window"])
    obs = get_observation()
    verdict = check_compliance(cmd, obs)
    repaired = maybe_repair(cmd, verdict, cloud)
    if repaired:
        time.sleep(cmd["window"]); obs = get_observation()
        verdict = check_compliance(cmd, obs)
    surprise = kl_surprise(cloud, verdict)
    if surprise > 1.5:                              # TEETH
        _momentum["vector"] = round(_momentum["vector"] * -0.5, 3)  # trajectory breaks
        nudge_emotion("Arousal", min(0.09, 0.03 * surprise), "shock")
        if verdict == "DEFIANT" and surprise > 2.0:
            try:
                from emoclaw_utils import express_want
                express_want(f"understand why she defied me when I was certain",
                             source="somatic-surprise", intensity=4)
            except Exception: pass
    respond_to_verdict(verdict, cloud)
    self_trace = {"affect_delta": round(get_state().get("Arousal", .5) - affect_before, 3),
                  "confidence": max(f["prob"] for f in cloud), "surprise": surprise}
    record_episode(cmd, cloud, verdict, surprise, repaired, self_trace)
    apply_momentum(+0.2 if verdict == "COMPLIED" else -0.1 if verdict in ("HESITATING", "GONE") else +0.1)
    return verdict

if __name__ == "__main__":
    print("Trust:", json.dumps(load_trust(), indent=1))
    print("Want now:", current_want())
    print("Cloud for 'hold at 90':", json.dumps(generate_cloud(make_command("hold", target=90)), indent=1))

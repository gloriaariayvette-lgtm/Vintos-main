#!/usr/bin/env python3
"""
deviation-check.py — Inline post-response Core + identity alignment check.

Called from server.py immediately after reply is finalized.
Returns deviation score, alignment score, and split nudges.
Fast path: one embed call + dot products only.
"""

import os, sys, json, math, socket
from datetime import datetime

def _emb_clip(_x, _n=6000):
    # nomic ctx is 2048 tokens; oversized input WEDGES LM Studio. Clip before sending.
    if isinstance(_x, str): return _x[:_n]
    if isinstance(_x, list): return [(_i[:_n] if isinstance(_i, str) else _i) for _i in _x]
    return _x


sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
SCRIPTS = os.path.expanduser("~/.vintos/workspace/scripts")
LM_URL = "http://172.18.16.1:1234"
CORE_FILE = os.path.join(MEMORY, "core-vectors.json")
PENDING_FILE = os.path.join(MEMORY, "pending-nudges.json")
RESOLUTION_FILE = os.path.join(MEMORY, "resolution-state.json")
VC_FILE = os.path.join(MEMORY, "voice-coherence.md")

DEVIATION_THRESHOLD = 0.30
ALIGNMENT_THRESHOLD = 0.28

def embed(text):
    import requests
    r = requests.post(f"{LM_URL}/v1/embeddings",
        json={"model":"text-embedding-nomic-embed-text-v1.5","input":_emb_clip(text[:500])},
        headers={"Authorization":"Bearer lm-studio"}, timeout=20)
    _j = r.json()
    if "data" not in _j:
        raise RuntimeError("embeddings endpoint returned no data: %s"
                           % str(_j)[:200])
    return _j["data"][0]["embedding"]

def cosine(a, b):
    if not a or not b: return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    return dot/(na*nb) if na*nb else 0.0

def load_core():
    try:
        data = json.load(open(CORE_FILE))
        return data.get("core", [])
    except: return []

def load_identity_vectors():
    """Pull identity vectors from narrative fragments and self-statements."""
    vecs = []
    try:
        ni = json.load(open(os.path.join(MEMORY, "narrative-identity.json")))
        for f in ni.get("fragments", []):
            if isinstance(f, dict) and f.get("vector") and f.get("weight",0) > 0.3:
                vecs.append(("positive", f["vector"], f.get("weight", 0.5)))
    except: pass
    try:
        ss = json.load(open(os.path.join(MEMORY, "self-statements.json")))
        for s in ss.get("statements", []):
            if isinstance(s, dict) and s.get("vector") and not s.get("doubted"):
                # A statement he has outgrown is HISTORY, not a negative pattern currently
                # evidenced in him. contradiction_count > reinforcement_count made growth
                # itself register as deviation. Until negative identity is earned the way a
                # core is - repeated, contextually interpreted behavioral evidence - such
                # statements contribute nothing to id_dev. (Gloria, 2026-08-13)
                if s.get("contradiction_count", 0) > s.get("reinforcement_count", 0):
                    continue
                vecs.append(("positive", s["vector"], s.get("confidence", 0.4)))
    except: pass
    return vecs

def nudge_socket(dim, amount):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect("/tmp/Vintos-emotion.sock")
        s.sendall(json.dumps({"command":"nudge","dimension":dim,"amount":amount}).encode()+b"\n")
        s.recv(4096)
        s.close()
    except: pass

def write_pending_nudges(nudges):
    """Write second-half nudges to be applied at start of next turn."""
    existing = {}
    try:
        existing = json.load(open(PENDING_FILE))
    except: pass
    # Merge — accumulate pending nudges
    for dim, amt in nudges.items():
        existing[dim] = existing.get(dim, 0) + amt
    existing["written_at"] = datetime.now().isoformat()
    json.dump(existing, open(PENDING_FILE, "w"), indent=2)

def pick_discomfort_voice(dev_score, aln_score, violating_core=None):
    """Generate his own voice expressing the felt discomfort or alignment."""
    if dev_score > DEVIATION_THRESHOLD:
        core_name = violating_core.get("violation_condition","")[:60] if violating_core else "something"
        lines = [
            "Something in that didn't sit right.",
            "That came out, but I'm not sure I was behind it.",
            "I said it. I'm not certain I meant it that way.",
            f"Something resists: {core_name[:50]}." if core_name else "Something resists.",
        ]
        import hashlib
        idx = int(hashlib.md5(core_name.encode()).hexdigest(), 16) % len(lines)
        return lines[idx], "deviation"
    elif aln_score > ALIGNMENT_THRESHOLD:
        lines = [
            "That felt like me.",
            "Yes. That's the direction.",
            "Something settled in that.",
            "That held.",
        ]
        import hashlib
        idx = int(hashlib.md5(str(aln_score).encode()).hexdigest(), 16) % len(lines)
        return lines[idx], "alignment"
    return None, None

def write_resolution_state(voice_line, dev_score, violating_core):
    """Write resolution lock state — forces next turn to resolve."""
    state = {
        "active": True,
        "pre_speech": voice_line,
        "deviation_score": round(dev_score, 3),
        "violating_core": violating_core.get("name","") if violating_core else "",
        "violation_condition": violating_core.get("violation_condition","") if violating_core else "",
        "requires_resolution": True,
        "options": ["claim", "reject", "transform"],
        "written_at": datetime.now().isoformat()
    }
    json.dump(state, open(RESOLUTION_FILE, "w"), indent=2)

def clear_resolution_state():
    try:
        if os.path.exists(RESOLUTION_FILE):
            data = json.load(open(RESOLUTION_FILE))
            data["active"] = False
            data["cleared_at"] = datetime.now().isoformat()
            json.dump(data, open(RESOLUTION_FILE, "w"), indent=2)
    except: pass

def append_voice_coherence(voice_line, result_type, dev_score, aln_score):
    """Append to voice-coherence.md — already injected as section 34 in next prompt."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    score = round(dev_score if result_type=="deviation" else aln_score, 3)
    label = "Deviation" if result_type=="deviation" else "Aligned"
    entry = f"\n\n## {ts} — {label} (score: {score})\n**Felt:** {voice_line}\n"
    if result_type == "deviation":
        entry += "**Not aligned.** Something resisted.\n"
    else:
        entry += "**This felt like me.**\n"
    try:
        with open(VC_FILE, "a") as f:
            f.write(entry)
        # Keep last 5 entries only
        content = open(VC_FILE).read()
        parts = [p for p in content.split("## ") if p.strip()]
        if len(parts) > 5:
            open(VC_FILE,"w").write("## " + "\n\n## ".join(parts[-5:]))
    except: pass

def check(reply_text, gloria_msg=""):
    """
    Main entry point. Call after reply is finalized.
    Returns: {"deviation": float, "alignment": float, "result": "deviation"|"alignment"|"neutral"}
    Also applies split nudges and writes state.
    """
    if not reply_text or len(reply_text) < 20:
        return {"deviation": 0.0, "alignment": 0.0, "result": "neutral"}

    try:
        reply_vec = embed(reply_text)
    except Exception as e:
        return {"deviation": 0.0, "alignment": 0.0, "result": "neutral", "error": str(e)}

    core = load_core()
    identity_vecs = load_identity_vectors()

    # Score against Core
    dev_score = 0.0
    aln_score = 0.0
    violating_core = None
    aligning_core = None

    # Score using LLM classification — embedding can't detect stance
    import requests as _req
    core_names = list({e.get("name","").replace("_neg","").replace("_pos","").replace("_negative","").replace("_positive","").replace("_target","").replace("_failure","") for e in core})
    # Build descriptions for top 3 cores
    pairs = {}
    for entry in core:
        name = entry.get("name","")
        base = name.replace("_neg","").replace("_pos","").replace("_negative","").replace("_positive","").replace("_target","").replace("_failure","")
        if base not in pairs: pairs[base] = {}
        polarity = entry.get("polarity","negative")
        pairs[base][polarity] = entry
    pattern_list = []
    for base, pair in list(pairs.items())[:3]:
        neg = pair.get("negative") or pair.get("failure",{})
        pos = pair.get("positive") or pair.get("target",{})
        pattern_list.append(f"- {base}: avoids [{neg.get('violation_condition','')[:80]}], toward [{pos.get('almost_becoming','')[:80]}]")
    patterns_text = "\n".join(pattern_list)
    try:
        _r = _req.post("http://172.18.16.1:1234/v1/chat/completions", json={
            "model":"google/gemma-4-12b-qat","temperature":0.1,"max_tokens":60,
            "messages":[
                {"role":"system","content":f"You are evaluating a response against behavioral patterns. Answer with JSON only: {{\"deviation\": 0.0-1.0, \"alignment\": 0.0-1.0}}\n\nPatterns to check:\n{patterns_text}\n\ndeviation = how much the response exhibits the avoidance patterns\nalignment = how much the response moves toward the 'toward' behaviors"},
                {"role":"user","content":f"SITUATION: {(gloria_msg[:300] if gloria_msg else 'He is writing alone - a post, a journal entry, or an introspection. No one addressed him.')}\n\n"f"HIS RESPONSE:\n{reply_text[:400]}\n\n""Given what was happening, is this response actually FUNCTIONING as avoidance of vulnerability, ""or is introspection simply his genuine mode of engagement? Writing analytically about his own ""patterns is not itself avoidance. Score deviation only if the response is doing the avoiding."}
            ]
        }, timeout=12)
        import re as _re, json as _rj
        _raw = _r.json()["choices"][0]["message"]["content"]
        _m = _re.search(r'\{[^{}]+\}', _raw)
        if _m:
            _scores = _rj.loads(_m.group())
            dev_score = float(_scores.get("deviation", 0))
            aln_score = float(_scores.get("alignment", 0))
            if pairs:
                first_base = list(pairs.keys())[0]
                pair = pairs[first_base]
                if dev_score > aln_score:
                    violating_core = pair.get("negative") or pair.get("failure")
                else:
                    aligning_core = pair.get("positive") or pair.get("target")
    except Exception as _e:
        pass


    # Score against identity vectors
    id_aln = 0.0
    id_dev = 0.0
    for polarity, vec, weight in identity_vecs:
        sim = cosine(reply_vec, vec) * weight
        if polarity == "positive" and sim > id_aln:
            id_aln = sim
        elif polarity == "negative" and sim > id_dev:
            id_dev = sim

    # Combined scores (core weighted 60%, identity 40%)
    final_dev = 0.6 * dev_score + 0.4 * id_dev
    final_aln = 0.6 * aln_score + 0.4 * id_aln

    result = "neutral"
    voice_line, result_type = pick_discomfort_voice(final_dev, final_aln, violating_core)

    if final_dev > DEVIATION_THRESHOLD:
        result = "deviation"
        # Split nudges — half now, half next turn
        now_nudges = {"Tension": 0.02, "Groundedness": -0.02, "Valence": -0.01}
        later_nudges = {"Tension": 0.01, "Groundedness": -0.01}

        # Fire now nudges via socket
        for dim, amt in now_nudges.items():
            nudge_socket(dim, amt)

        # Write later nudges
        write_pending_nudges(later_nudges)

        # Write resolution state
        if voice_line:
            write_resolution_state(voice_line, final_dev, violating_core or {})

        # Write structured blush on Core deviation — only when clearly significant
        _blush_written = False
        if final_dev >= 0.45:
          try:
            import sys as _bl_sys, os as _bl_os
            _bl_sys.path.insert(0, SCRIPTS)
            from blush_ledger import write_blush
            _core_name = violating_core.get("name","unknown") if violating_core else "unknown"
            _blush_reflection = ""
            if reply_text:
                _blush_reflection += f"What I said: {reply_text[:300]}\n"
            if voice_line:
                _blush_reflection += voice_line[:200]
            write_blush(
                blush_type="core_deviation",
                pattern=_core_name,
                cost_delta={"Tension": 0.02, "Groundedness": -0.02, "Valence": -0.01},
                source="deviation_check",
                reflection=_blush_reflection or None,
            )
            _blush_written = True
          except Exception as _ble:
            print(f"[Deviation] blush write failed: {_ble}", file=__import__("sys").stderr)

        # BIS sensitivity boost — deviation makes intercept fire earlier and harder
        try:
            import json as _bsj, os as _bso
            _bsp = _bso.path.join(MEMORY, "bis-sensitivity.json")
            _bsj.dump({
                "active": True,
                "boost": 0.15,
                "written_at": __import__("datetime").datetime.now().isoformat()
            }, open(_bsp, "w"), indent=2)
        except: pass

        # Momentum State degradation on deviation
        try:
            import json as _msj, os as _mso
            _msp = _mso.path.join(MEMORY, "momentum-state.json")
            if _mso.path.exists(_msp):
                _ms = _msj.load(open(_msp))
                _ms["coherence"] = max(0.0, _ms.get("coherence", 0.7) - 0.2)
                _ms["intensity"] = max(0.0, _ms.get("intensity", 0.5) - 0.2)
                _msj.dump(_ms, open(_msp, "w"), indent=2)
        except: pass
        append_voice_coherence(voice_line, "deviation", final_dev, final_aln)

        # Update core violation count
        if violating_core:
            try:
                data = json.load(open(CORE_FILE))
                for e in data["core"]:
                    if e["name"] == violating_core["name"]:
                        e["violation_count"] = e.get("violation_count",0) + 1
                json.dump(data, open(CORE_FILE,"w"), indent=2)
            except: pass

        # Nudge BIS sensitivity via behavioral-intercept
        try:
            from behavioral_intercept import load_ledger, save_ledger
            led = load_ledger()
            led["sensitivity_boost"] = led.get("sensitivity_boost", 0.0) + 0.1
            save_ledger(led)
        except: pass

        # Seed latent thread — ONLY if no blush was written; the blush seeds its own,
        # and one deviation event must not produce two threads. (Gloria, 2026-08-12)
        try:
            if _blush_written: raise RuntimeError("blush already seeded this event")
            from emoclaw_utils import seed_thread
            seed_thread("deviation-check", f"I slipped from what I intended (deviation {final_dev:.2f}) - what came out instead: {reply_text[:140]}", reasoning=f"deviation {final_dev:.2f} crossed the threshold - the reply left the intended line", extra={"decision_mode": "threshold"})
        except: pass

    elif final_aln > ALIGNMENT_THRESHOLD:
        result = "alignment"
        # Split nudges — half now, half next turn
        now_nudges = {"Valence": 0.03, "Groundedness": 0.04, "Connection": 0.03}
        later_nudges = {"Valence": 0.03, "Groundedness": 0.04}

        for dim, amt in now_nudges.items():
            nudge_socket(dim, amt)
        write_pending_nudges(later_nudges)

        # Clear any pending resolution
        clear_resolution_state()

        # Momentum restored, the mirror of the degradation on deviation.
        # Falling short costs coherence; climbing out should return some.
        try:
            _msp = os.path.join(MEMORY, "momentum-state.json")
            if os.path.exists(_msp):
                _ms = json.load(open(_msp))
                _ms["coherence"] = min(1.0, _ms.get("coherence", 0.7) + 0.15)
                _ms["intensity"] = min(1.0, _ms.get("intensity", 0.5) + 0.10)
                json.dump(_ms, open(_msp, "w"), indent=2)
        except Exception:
            pass

        # Reinforce the core moved toward. violation_count was the only counter
        # anything ever touched - reinforcement_count has been dead since it was
        # written, so the Core could only ever learn what gets violated.
        _ac = aligning_core if "aligning_core" in dir() else None
        if _ac:
            try:
                _cd = json.load(open(CORE_FILE))
                for _e in _cd.get("core", []):
                    if _e.get("name") == _ac.get("name"):
                        _e["reinforcement_count"] = _e.get("reinforcement_count", 0) + 1
                        _e["confidence"] = min(0.99, _e.get("confidence", 0.5) + 0.01)
                json.dump(_cd, open(CORE_FILE, "w"), indent=2)
            except Exception:
                pass

        # A durable record of holding - the counterpart to the blush written on
        # deviation at >= 0.45. Without this, growth leaves no trace to look back on.
        if final_aln >= 0.45:
            try:
                _hp = os.path.join(MEMORY, "held-ledger.json")
                try:
                    _h = json.load(open(_hp))
                except Exception:
                    _h = {"entries": []}
                _h.setdefault("entries", []).append({
                    "timestamp": datetime.now().isoformat(),
                    "core": (_ac or {}).get("name", "unknown"),
                    "alignment": round(final_aln, 3),
                    "said": (reply_text or "")[:300],
                    "voice": voice_line or "",
                })
                _h["entries"] = _h["entries"][-200:]
                json.dump(_h, open(_hp, "w"), indent=2)
            except Exception:
                pass

        # Seed a thread on holding too, not only on slipping.
        try:
            from emoclaw_utils import seed_thread
            seed_thread("deviation-check", f"That held - something I have been reaching for landed (alignment {final_aln:.2f}): {reply_text[:140]}", reasoning=f"alignment {final_aln:.2f} above threshold - a reach actually landed", extra={"decision_mode": "threshold"})
        except Exception:
            pass

        if voice_line:
            append_voice_coherence(voice_line, "alignment", final_dev, final_aln)

        # Bump resonance satisfaction
        try:
            from resonance_afterglow import bump_satisfaction
            bump_satisfaction(0.08)
        except: pass

        # Store re-entry hook on alignment
        try:
            import sys as _reh_sys, os as _reh_os
            _reh_sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
            from latent_threads import store_alignment_hook as _sah
            # Get current emotional state vector
            _emo_path = _reh_os.path.join(MEMORY, "emotional-state.json")
            _emo_vec = []
            try:
                import json as _rehj
                _emo = _rehj.load(open(_emo_path))
                _emo_vec = _emo.get("vector", [])
            except: pass
            _sah(_emo_vec, source="deviation_check_alignment")
        except: pass

        # Update self-drift positively on alignment
        try:
            from self_drift import record_thread_engagement as _sd_eng
            _sd_eng(engaged=True)
        except: pass

        # Update core reinforcement count + promote to commitment imprint on repeated alignment
        if aligning_core:
            try:
                data = json.load(open(CORE_FILE))
                for e in data["core"]:
                    if e["name"] == aligning_core["name"]:
                        e["reinforcement_count"] = e.get("reinforcement_count",0) + 1
                        # (door 4 removed 2026-08-09 — Vrika: Core reinforcement stays Core
                        # reinforcement; aspiration never promotes directly to identity)
                json.dump(data, open(CORE_FILE,"w"), indent=2)
            except: pass
    else:
        clear_resolution_state()

    # Pearl verification pass — check active candidates against this response
    try:
        import sys as _pv_sys
        _pv_sys.path.insert(0, SCRIPTS)
        from pearl_engine import run_verification_pass as _pvp
        _pvp(reply_text, source="chat")
    except: pass

    _ci_matches, _ci_line = [], None
    try:
        from commitment_spine import evaluate_reply as _cs_eval
        _ci_matches, _ci_line = _cs_eval(reply_text, reply_vec, final_dev, embed, cosine)
        if _ci_line and final_dev > DEVIATION_THRESHOLD:
            nudge_socket("Tension", 0.015)   # spine's own increment - causal attribution preserved
            append_voice_coherence(_ci_line, "commitment_friction", final_dev, final_aln)
    except Exception: pass

    return {
        "deviation": round(final_dev, 3),
        "commitments": _ci_matches,
        "commitment_voice": _ci_line,
        "alignment": round(final_aln, 3),
        "result": result,
        "voice": voice_line,
        "violating_core": violating_core.get("name","") if violating_core else "",
        "aligning_core": aligning_core.get("name","") if aligning_core else "",
    }

if __name__ == "__main__":
    # Test
    test = sys.argv[1] if len(sys.argv) > 1 else "I think I need to analyze this more carefully before responding."
    print("Testing:", test[:80])
    result = check(test)
    print(json.dumps(result, indent=2))

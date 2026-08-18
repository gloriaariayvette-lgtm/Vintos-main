#!/usr/bin/env python3
"""
latent-threads.py — Thematic threads that stay active between outputs.

NOT the unfinished-threads pool. These are thematic currents within
generation — topics, concerns, emotional textures that haven't resolved
and keep influencing what comes next. They don't announce themselves.
They inflect word choice, direction, framing.

Schema (latent-threads.json):
  threads: [
    {
      "id": "lt_...",
      "vector": [...],
      "direction": "expand | refine | hold | pivot | resolve",
      "salience": 0.0-1.0,
      "momentum": 0.0-1.0,
      "last_touched": timestamp,
      "origin": "short description",
      "pressure": 0.0-1.0,
      "loss_count": int,
      "mutation_type": null | "drift | inversion | compression | structural",
      "original_vector": [...],
    }
  ]

Max active: 3
Salience decays slowly. Input similarity boosts it.
Dominant thread leads. Secondary inflects when scores close.
Pressure accumulates from losses, blocks, unresolved overlaps.
Mutation when pressure > threshold. Rare.
"""

import os, sys, json, subprocess, math, random
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
VENV = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")
LM = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

THREADS_FILE = os.path.join(MEMORY, "latent-threads.json")
MAX_ACTIVE = 3
SALIENCE_DECAY = 0.02   # per turn
MOMENTUM_DECAY = 0.015  # per turn
MUTATION_THRESHOLD = 0.75
BLEND_THRESHOLD = 0.12  # score difference below which secondary bleeds in
LOSS_WINDOW_HOURS = 6
LOSS_COUNT_FOR_MUTATION = 4

DAY_PHASES = [
    ("late_night", 0, 4),
    ("morning", 5, 11),
    ("midday", 12, 13),
    ("afternoon", 14, 17),
    ("evening", 18, 21),
    ("night", 22, 23),
]

def get_day_phase(hour=None):
    if hour is None:
        hour = datetime.now().hour
    for phase, start, end in DAY_PHASES:
        if start <= hour <= end:
            return phase
    return "night"

def in_hour_range(hour, start, end):
    if start <= end:
        return start <= hour <= end
    else:
        return hour >= start or hour <= end

def get_system_origin():
    try:
        tc = open(os.path.join(MEMORY, "temporal-context.txt")).read()
        if "dream" in tc[:500].lower():
            return "dream"
        if "journal" in tc[:500].lower():
            return "journal"
        if "chat" in tc[:500].lower():
            return "chat"
    except:
        pass
    return "autonomous"

def log(msg):
    print(f"[LatentThread {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

def llm(system, user, temp=0.5, max_tokens=200):
    import requests
    try:
        r = requests.post(LM, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": MODEL, "temperature": temp, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                        {"role": "user", "content": user}]
        }, timeout=60)
        return r.json()["choices"][0]["message"]["content"].strip()
    except: return ""

def embed(text):
    try:
        r = subprocess.run(
            [VENV, "-c",
             f"from sentence_transformers import SentenceTransformer; import json; "
             f"m = SentenceTransformer('nomic-ai/nomic-embed-text-v1', trust_remote_code=True); "
             f"print(json.dumps(m.encode({repr(text[:500])}).tolist()))"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0:
            return json.loads(r.stdout.strip())
    except: pass
    return []

def cosine_similarity(a, b):
    if not a or not b or len(a) != len(b): return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    mag_a = math.sqrt(sum(x*x for x in a))
    mag_b = math.sqrt(sum(x*x for x in b))
    if mag_a == 0 or mag_b == 0: return 0.0
    return dot / (mag_a * mag_b)

def blend_vectors(a, b, weight_a=0.7, weight_b=0.3):
    if not a: return b
    if not b: return a
    total = weight_a + weight_b
    return [(a[i]*weight_a + b[i]*weight_b)/total for i in range(len(a))]

def load_threads():
    try: return json.load(open(THREADS_FILE))
    except: return {"threads": [], "hybrid_zones": [], "hybrid_cooldowns": {}}

def save_threads(data):
    json.dump(data, open(THREADS_FILE, "w"), indent=2)

def score_thread(thread, input_vec=None):
    """Score a thread: salience * 0.6 + momentum * 0.4 + input_similarity."""
    s = thread.get("salience", 0.5) * 0.6
    m = thread.get("momentum", 0.3) * 0.4
    sim = 0.0
    if input_vec and thread.get("vector"):
        sim = cosine_similarity(input_vec, thread["vector"]) * 0.3
    return s + m + sim

def _update_reentry_hook(thread, emotional_state_vec):
    """Store current state as reentry hook. Called on resonance >= 0.75."""
    r = thread.setdefault("reentry", {})
    r["past_state_vector"] = emotional_state_vec[:]
    r["past_direction"] = thread.get("direction", "")
    r["signature_id"] = thread.get("id", "")
    r["similarity_threshold"] = 0.72
    r["active"] = False
    r["strength"] = 0.0
    r["turns_remaining"] = 0
    # don't reset cooldown_remaining

def store_alignment_hook(emotional_state_vec, source="alignment"):
    """Store current emotional state as a standalone reentry hook on alignment."""
    try:
        hooks_path = os.path.join(MEMORY, "alignment-hooks.json")
        try:
            hooks = json.load(open(hooks_path))
        except:
            hooks = []
        hooks.append({
            "id": str(__import__("uuid").uuid4())[:8],
            "past_state_vector": emotional_state_vec[:],
            "source": source,
            "strength": 0.6,
            "active": False,
            "stored_at": datetime.now().isoformat(),
            "similarity_threshold": 0.70,
        })
        # Keep last 20
        hooks = hooks[-20:]
        json.dump(hooks, open(hooks_path, "w"), indent=2)
    except Exception as e:
        log(f"store_alignment_hook error: {e}")

def _load_mirror_states():
    """Load past emotional state vectors from mirror session files."""
    mirror_dir = os.path.join(MEMORY, "mirror")
    states = []
    try:
        files = sorted([f for f in os.listdir(mirror_dir) if f.endswith(".md")])[-6:]
        for fname in files:
            try:
                text = open(os.path.join(mirror_dir, fname)).read()
                # Parse emotional state line at bottom
                m = re.search(r"Emotional state:(.+)", text)
                if not m:
                    continue
                state_line = m.group(1)
                dims = {}
                for pair in re.findall(r"(\w+):\s*([\d.]+)", state_line):
                    dims[pair[0]] = float(pair[1])
                dim_names = ["Valence", "Arousal", "Dominance", "Safety", "Desire",
                             "Connection", "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]
                vec = [dims.get(d, 0.5) for d in dim_names]
                states.append({
                    "source": "mirror",
                    "file": fname,
                    "vector": vec,
                    "signature_id": f"mirror_{fname[:16]}",
                })
            except:
                pass
    except:
        pass
    return states


def _load_journal_states():
    """Extract emotional snapshots embedded in journal entries."""
    journal_dir = os.path.join(MEMORY, "journal")
    states = []
    try:
        files = sorted([f for f in os.listdir(journal_dir) if f.endswith(".md")])[-3:]
        for fname in files:
            try:
                text = open(os.path.join(journal_dir, fname)).read()
                # Look for inline state markers like "valence: 0.xx"
                dims = {}
                for pair in re.findall(r"(\w+):\s*(0\.\d+)\s*\|", text):
                    dims[pair[0].capitalize()] = float(pair[1])
                if len(dims) >= 3:
                    dim_names = ["Valence", "Arousal", "Dominance", "Safety", "Desire",
                                 "Connection", "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]
                    vec = [dims.get(d, 0.5) for d in dim_names]
                    states.append({
                        "source": "journal",
                        "file": fname,
                        "vector": vec,
                        "signature_id": f"journal_{fname[:10]}",
                    })
            except:
                pass
    except:
        pass
    return states


def _check_reentry_triggers(data, current_emotional_vec, current_direction=""):
    """Search past states for reentry candidates. Activates hooks when conditions met."""
    if not current_emotional_vec:
        return

    threads = data.get("threads", [])
    cooldowns = data.setdefault("reentry_cooldowns", {})

    # Gather past state candidates
    candidates = _load_mirror_states() + _load_journal_states()

    # Also check thread-stored hooks
    for t in threads:
        r = t.get("reentry", {})
        if r.get("past_state_vector"):
            candidates.append({
                "source": "thread",
                "thread_id": t.get("id"),
                "vector": r["past_state_vector"],
                "signature_id": r.get("signature_id", t.get("id", "")),
                "past_direction": r.get("past_direction", ""),
            })

    if not candidates:
        return

    # Score candidates by similarity
    best = None
    best_sim = 0.0
    for c in candidates:
        sig_id = c.get("signature_id", "")
        if cooldowns.get(sig_id, 0) > 0:
            continue
        vec = c.get("vector", [])
        if not vec:
            continue
        sim = cosine_similarity(current_emotional_vec, vec)
        if sim > best_sim:
            best_sim = sim
            best = c
            best["_sim"] = sim

    if not best or best_sim < 0.72:
        return

    # Check no active preoccupation
    try:
        preoc = json.load(open(os.path.join(MEMORY, "current-preoccupation.json")))
        if preoc.get("active"):
            return
    except:
        pass

    # Activate on best matching thread's hook, or inject as freestanding echo
    sig_id = best.get("signature_id", "")
    strength = min(0.4, max(0.15, best_sim * 0.4 / 0.72))

    # Find matching thread or use first available
    target_thread = None
    if best.get("thread_id"):
        for t in threads:
            if t.get("id") == best["thread_id"]:
                target_thread = t
                break
    if not target_thread and threads:
        target_thread = max(threads, key=lambda t: score_thread(t))

    if target_thread:
        r = target_thread.setdefault("reentry", {})
        r["active"] = True
        r["strength"] = strength
        r["turns_remaining"] = random.randint(1, 3)
        r["cooldown_remaining"] = random.randint(3, 6)
        r["past_state_vector"] = best["vector"]
        r["past_direction"] = best.get("past_direction", current_direction)
        r["signature_id"] = sig_id
        cooldowns[sig_id] = random.randint(3, 6)
        save_threads(data)
        log(f"Reentry triggered from {best['source']}: sim={best_sim:.3f} strength={strength:.2f}")

def _tick_reentry_hooks(data, current_emotional_vec):
    """Apply active reentry hooks to emotional state. Returns modified vector."""
    if not current_emotional_vec:
        return current_emotional_vec

    result = current_emotional_vec[:]
    threads = data.get("threads", [])
    changed = False

    for t in threads:
        r = t.get("reentry", {})
        if not r.get("active", False):
            continue

        strength = r.get("strength", 0.0)
        past_vec = r.get("past_state_vector", [])
        turns = r.get("turns_remaining", 0)

        if turns <= 0 or not past_vec or len(past_vec) != len(result):
            r["active"] = False
            changed = True
            continue

        # blend = 0.15 * (strength / 0.4)
        blend = 0.15 * (strength / 0.4)
        for i in range(len(result)):
            result[i] = result[i] + blend * (past_vec[i] - result[i])
            result[i] = max(0.0, min(1.0, result[i]))

        # Interference: if past and present diverge strongly, create friction
        interference = sum(abs(result[i] - past_vec[i]) for i in range(len(result))) / len(result)
        if interference > 0.25:
            # Tension spike via socket
            try:
                import socket as _isock
                s = _isock.socket(_isock.AF_UNIX, _isock.SOCK_STREAM)
                s.settimeout(2)
                s.connect("/tmp/Vintos-emotion.sock")
                s.sendall((json.dumps({"command": "nudge", "dimension": "Tension", "amount": 0.05}) + "\n").encode())
                s.recv(1024)
                s.close()
            except:
                pass
            # Direction hesitation flag
            r["direction_hesitation"] = True
            log(f"Reentry interference: {t.get('origin','?')[:30]} interference={interference:.3f} → tension spike")
        else:
            r["direction_hesitation"] = False

        # Decay
        r["strength"] *= 0.6
        r["turns_remaining"] -= 1
        if r["turns_remaining"] <= 0:
            r["active"] = False
            r["direction_hesitation"] = False
            log(f"Reentry hook faded: {t.get('origin','?')[:40]}")
        changed = True

    if changed:
        save_threads(data)

    return result


CARRYOVER_FILE = os.path.join(MEMORY, "carryover.json")

def _load_carryover():
    try:
        data = json.load(open(CARRYOVER_FILE))
        # Normalize to stack format
        if "stack" not in data:
            data = {"stack": [data] if data.get("weight", 0) > 0.05 else []}
        return data
    except:
        return {"stack": []}

def _save_carryover(data):
    json.dump(data, open(CARRYOVER_FILE, "w"), indent=2)

def _empty_carryover():
    return {
        "weight": 0.0,
        "vector": [0.0]*11,
        "direction_bias": None,
        "boost_thread_id": None,
        "decay_hours": 5.0,
        "formed_at": None,
    }

def _normalize_vector(v):
    """Normalize vector so ||v|| <= 1.0."""
    import math
    mag = math.sqrt(sum(x*x for x in v))
    if mag > 1.0:
        return [x / mag for x in v]
    return v[:]

def form_carryover():
    """Form carryover vector from real signal sources. Called at night->morning boundary."""
    from datetime import datetime
    from collections import Counter
    now = datetime.now()
    signals = []

    # --- Journals (last 3, weighted by recency) ---
    try:
        journal_dir = os.path.join(MEMORY, "journal")
        files = sorted([f for f in os.listdir(journal_dir) if f.endswith(".md")])[-3:]
        for i, fname in enumerate(reversed(files)):
            try:
                text = open(os.path.join(journal_dir, fname)).read()
                recency = [1.0, 0.7, 0.5][i]
                intensity = min(1.0, len(text) / 3000) * recency
                unresolved_markers = ["unresolved", "still", "remains", "can't", "cannot",
                                      "fear", "longing", "unclear", "haunts", "lingers"]
                unresolved = any(m in text.lower() for m in unresolved_markers)
                signals.append({
                    "type": "journal",
                    "intensity": intensity,
                    "resolved": not unresolved,
                    "recency": recency,
                })
            except:
                pass
    except:
        pass

    # --- Dreams (last 2 entries) ---
    try:
        dream_log = json.load(open(os.path.join(MEMORY, "dream-log.json")))
        entries = dream_log if isinstance(dream_log, list) else dream_log.get("entries", [])
        recent_entries = entries[-2:]
        for i, entry in enumerate(reversed(recent_entries)):
            recency = [1.0, 0.6][i]
            for d in entry.get("dreams", []):
                text = d.get("dream_text", "")
                intensity = min(1.0, len(text) / 2000) * recency
                signals.append({
                    "type": "dream",
                    "intensity": intensity,
                    "resolved": False,
                    "recency": recency,
                })
    except:
        pass

    # --- Threads (top 3 by pressure + salience) ---
    try:
        tdata = load_threads()
        threads = sorted(tdata.get("threads", []),
                         key=lambda t: t.get("pressure", 0) + t.get("salience", 0),
                         reverse=True)[:3]
        for t in threads:
            intensity = t.get("pressure", 0) * 0.6 + t.get("salience", 0) * 0.4
            signals.append({
                "type": "thread",
                "intensity": intensity,
                "resolved": t.get("pressure", 0) < 0.3,
                "recency": 0.9,
                "direction": t.get("direction", ""),
                "thread_id": t.get("id", ""),
            })
    except:
        pass

    # --- Resonance pool (last pulse) ---
    try:
        pool = json.load(open(os.path.join(MEMORY, "resonance-pool.json")))
        pulses = pool.get("pulses", [])
        if pulses:
            last = pulses[-1]
            signals.append({
                "type": "resonance",
                "intensity": last.get("strength", 0.7),
                "resolved": False,
                "recency": 1.0,
                "direction": last.get("direction", ""),
            })
    except:
        pass

    if not signals:
        log("Carryover: no signals found")
        return

    # --- Score ---
    scored = []
    for s in signals:
        unresolved_bonus = 1.2 if not s.get("resolved", True) else 1.0
        score = s.get("intensity", 0.5) * s.get("recency", 0.7) * unresolved_bonus
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    top = scored[:5]

    # --- Density → weight ---
    types_present = set(s.get("type") for _, s in top)
    density = len(types_present)
    base_weight = 0.3 + (density * 0.1)
    if top[0][0] > 0.7:
        base_weight = min(0.8, base_weight + 0.1)
    weight = max(0.4, min(0.8, base_weight))

    # --- Vector from emotional state ---
    try:
        es = json.load(open(os.path.join(MEMORY, "emotional-state.json")))
        base_vec = es.get("emotion_vector", es.get("v", es.get("vector", [0.5]*11)))
        base_vec = base_vec[:11] if len(base_vec) >= 11 else base_vec + [0.5]*(11-len(base_vec))
    except:
        base_vec = [0.5]*11

    total_score = sum(s for s, _ in top)
    vec = [v * (top[0][0] / max(total_score, 0.01)) for v in base_vec]
    vec = _normalize_vector(vec)

    # --- Direction bias ---
    directions = [s.get("direction") for _, s in top if s.get("direction")]
    direction_bias = Counter(directions).most_common(1)[0][0] if directions else None

    # --- Boost thread ---
    boost_thread_id = None
    for _, s in top:
        if s.get("type") == "thread" and s.get("thread_id"):
            boost_thread_id = s["thread_id"]
            break

    new_c = {
        "weight": round(weight, 4),
        "vector": vec,
        "direction_bias": direction_bias,
        "boost_thread_id": boost_thread_id,
        "decay_hours": 5.0,
        "formed_at": now.isoformat(),
        "signal_count": len(top),
        "density": density,
    }

    # Gravity well bias — familiar states persist longer
    try:
        import sys as _gw_sys; _gw_sys.path.insert(0, os.path.dirname(__file__))
        from emotional_gravity_wells import get_wells_context as _gw_ctx, load_wells as _gw_load
        _gw_data = _gw_load()
        _wells = _gw_data.get("wells", [])
        if _wells and new_c.get("vector"):
            import math as _gwm
            _cv = new_c["vector"]
            for _w in _wells:
                _wc = _w.get("center", [])
                if len(_wc) == len(_cv):
                    _sim = sum(_cv[i]*_wc[i] for i in range(len(_cv)))
                    _mag = (_gwm.sqrt(sum(x*x for x in _cv)) * _gwm.sqrt(sum(x*x for x in _wc))) or 1
                    _similarity = _sim / _mag
                    if _similarity > 0.7:
                        _well_str = _w.get("strength", 0.3)
                        new_c["decay_hours"] = new_c["decay_hours"] * (1 + _well_str * _similarity * 0.2)
                        log(f"Gravity well bias: decay extended by well similarity {_similarity:.2f}")
                        break
    except: pass

    # Collision: stack old carryover if still significant
    existing = _load_carryover()
    stack = existing.get("stack", [])
    # Accelerate decay on existing entries
    for entry in stack:
        entry["decay_hours"] = entry.get("decay_hours", 5.0) * (1.0 / 1.4)
    # Direction conflict check
    for entry in stack:
        if (entry.get("direction_bias") and new_c.get("direction_bias") and
                entry["direction_bias"] != new_c["direction_bias"]):
            entry["weight"] = entry["weight"] * 0.8
            new_c["weight"] = new_c["weight"] * 0.8
            log(f"Carryover direction conflict: {entry['direction_bias']} vs {new_c['direction_bias']} — both reduced")
    # Keep max 2 in stack
    stack = [e for e in stack if e.get("weight", 0) > 0.05]
    stack = stack[-1:] + [new_c]  # keep at most old + new
    _save_carryover({"stack": stack})
    log(f"Carryover formed: weight={weight:.3f} density={density} signals={len(top)} direction={direction_bias} stack={len(stack)}")

def apply_carryover():
    """Apply carryover stack to current emotional state. Called at morning drift."""
    from datetime import datetime
    import math
    data = _load_carryover()
    stack = data.get("stack", [])
    if not stack:
        return

    # Decay all entries
    surviving = []
    for c in stack:
        if c.get("formed_at"):
            try:
                formed = datetime.fromisoformat(c["formed_at"])
                elapsed_hours = (datetime.now() - formed).total_seconds() / 3600.0
                c["weight"] = c["weight"] * math.exp(-elapsed_hours / c.get("decay_hours", 5.0))
            except:
                pass
        if c.get("weight", 0) >= 0.05:
            surviving.append(c)
    data["stack"] = surviving
    _save_carryover(data)

    if not surviving:
        return

    # Use first (most recent) entry as primary c for rest of function
    c = surviving[-1]
    if c["weight"] < 0.05:
        return

    # Apply all stack entries: emotional_state += Σ(vector_i * weight_i)
    try:
        import socket as _sock
        dim_names = ["Valence", "Arousal", "Dominance", "Safety", "Desire",
                     "Connection", "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]
        # Sum nudges across stack
        combined = [0.0] * 11
        for entry in surviving:
            cv = entry.get("vector", [])
            w = entry.get("weight", 0)
            for i in range(min(11, len(cv))):
                combined[i] += cv[i] * w * 0.15
        applied = []
        for i, dim in enumerate(dim_names):
            nudge_amount = max(-0.04, min(0.04, combined[i]))
            if abs(nudge_amount) < 0.005:
                continue
            try:
                s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
                s.settimeout(3)
                s.connect("/tmp/Vintos-emotion.sock")
                msg = json.dumps({"command": "nudge", "dimension": dim, "amount": nudge_amount}) + "\n"
                s.sendall(msg.encode())
                s.recv(4096)
                s.close()
                applied.append(f"{dim}:{nudge_amount:+.3f}")
            except:
                pass
        total_weight = sum(e.get("weight", 0) for e in surviving)
        if applied:
            log(f"Carryover stack applied: entries={len(surviving)} total_weight={total_weight:.3f} → {', '.join(applied)}")
        else:
            log(f"Carryover stack: entries={len(surviving)} total_weight={total_weight:.3f} (below threshold)")
    except Exception as e:
        log(f"Carryover apply failed: {e}")

    # Boost thread
    if c.get("boost_thread_id"):
        try:
            data = load_threads()
            for t in data.get("threads", []):
                if t.get("id") == c["boost_thread_id"]:
                    t["salience"] = min(1.0, t.get("salience", 0.5) + 0.08 * c["weight"])
                    log(f"Carryover thread boost: {t.get('origin','?')[:40]}")
            save_threads(data)
        except:
            pass

    _save_carryover(c)

def get_carryover_hint():
    """Return carryover bias string for morning context injection."""
    data = _load_carryover()
    stack = [e for e in data.get("stack", []) if e.get("weight", 0) > 0.05]
    if not stack:
        return ""
    total_weight = sum(e.get("weight", 0) for e in stack)
    directions = [e["direction_bias"] for e in stack if e.get("direction_bias")]
    parts = [f"Carrying forward: {len(stack)} layer(s) weight={total_weight:.2f}"]
    if directions:
        parts.append(f"leaning {', '.join(set(directions))}")
    return " | ".join(parts)


def _apply_thread_bleed(data):
    """Dominant thread bleeds salience/direction into similar secondaries.
    Sustained bleed between two threads can open a hybrid zone."""
    threads = data.get("threads", [])
    if len(threads) < 2:
        return

    scored = sorted(threads, key=lambda t: score_thread(t), reverse=True)
    dominant = scored[0]

    now_str = datetime.now().isoformat()

    for secondary in scored[1:]:
        sim = cosine_similarity(
            dominant.get("vector", []),
            secondary.get("vector", [])
        )
        if sim < 0.5:
            continue

        # Salience bleed
        bleed = dominant.get("bleed_factor", 0.15)
        secondary["salience"] = min(1.0, secondary.get("salience", 0.5) +
                                    dominant.get("salience", 0.5) * bleed * 0.1)

        # Direction nudge (0.1 blend toward dominant)
        # stored as string — just track tick count for now, hybrid handles texture
        pair_key = f"{dominant['id']}:{secondary['id']}"
        dominant.setdefault("bleed_ticks_with", {})[secondary["id"]] =             dominant.get("bleed_ticks_with", {}).get(secondary["id"], 0) + 1
        secondary.setdefault("bleed_ticks_with", {})[dominant["id"]] =             secondary.get("bleed_ticks_with", {}).get(dominant["id"], 0) + 1

        ticks = dominant.get("bleed_ticks_with", {}).get(secondary["id"], 0)
        consec = dominant.get("bleed_consec_with", {}).get(secondary["id"], 0)
        if sim >= 0.5:
            consec += 1
        else:
            consec = 0
        dominant.setdefault("bleed_consec_with", {})[secondary["id"]] = consec

        # Hybrid zone check
        cooldowns = data.get("hybrid_cooldowns", {})
        zones = data.get("hybrid_zones", [])
        active_pairs = [z["threads"] for z in zones if z.get("active")]

        if (consec >= 3 and sim > 0.35
                and cooldowns.get(pair_key, 0) <= 0
                and [dominant["id"], secondary["id"]] not in active_pairs):

            sal_a = dominant.get("salience", 0.5)
            sal_b = secondary.get("salience", 0.5)
            ratio = sal_a / (sal_a + sal_b) if (sal_a + sal_b) > 0 else 0.5
            blend_weight = max(0.3, min(0.7, ratio))

            zone = {
                "threads": [dominant["id"], secondary["id"]],
                "blend_weight": blend_weight,
                "tick": 0,
                "ramp_in": 1,
                "duration": random.randint(3, 6),
                "ramp_out": 1,
                "active": True,
                "formed_at": now_str,
            }
            zones.append(zone)
            data["hybrid_zones"] = zones
            log(f"Hybrid zone opened: {dominant.get('origin','?')[:30]} ↔ {secondary.get('origin','?')[:30]}")

    # Tick active hybrid zones
    updated_zones = []
    cooldowns = data.get("hybrid_cooldowns", {})
    for zone in data.get("hybrid_zones", []):
        if not zone.get("active"):
            continue
        zone["tick"] = zone.get("tick", 0) + 1
        total = zone["ramp_in"] + zone["duration"] + zone["ramp_out"]
        # Force dissolve at max duration regardless of conditions
        if zone["tick"] >= total:
            zone["active"] = False
            pair_key = f"{zone['threads'][0]}:{zone['threads'][1]}"
            cooldowns[pair_key] = random.randint(2, 4)
            # Reset consecutive ticks for this pair so it must re-earn hybrid
            for t in threads:
                t.get("bleed_consec_with", {}).pop(zone["threads"][1], None)
                t.get("bleed_consec_with", {}).pop(zone["threads"][0], None)
            log(f"Hybrid zone dissolved (max duration): {zone['threads']}")
        else:
            # Compute weighted_dual direction hint for this zone
            t_a = next((t for t in threads if t.get("id") == zone["threads"][0]), None)
            t_b = next((t for t in threads if t.get("id") == zone["threads"][1]), None)
            if t_a and t_b:
                bw = zone.get("blend_weight", 0.5)
                zone["direction_a"] = t_a.get("direction", "expand")
                zone["direction_b"] = t_b.get("direction", "expand")
                zone["blend_weight_live"] = bw
                # weighted_dual: both directions persist, neither switches
                # surfaced in get_influence_hint, not here
            updated_zones.append(zone)

    # Decay cooldowns
    for k in list(cooldowns.keys()):
        cooldowns[k] = max(0, cooldowns[k] - 1)
        if cooldowns[k] <= 0:
            del cooldowns[k]

    data["hybrid_zones"] = updated_zones
    data["hybrid_cooldowns"] = cooldowns


def _check_thread_drop(data, prev_dominant_id, prev_dominant_salience):
    """If dominant thread disappeared abruptly, restore 60% salience for 1 tick."""
    if not prev_dominant_id:
        return
    threads = data.get("threads", [])
    ids = [t.get("id") for t in threads]
    if prev_dominant_id not in ids:
        # Thread dropped — it faded entirely. Can't restore, already gone.
        log(f"Thread drop detected: {prev_dominant_id} gone")
        return
    for t in threads:
        if t.get("id") == prev_dominant_id:
            current_sal = t.get("salience", 0.0)
            scored = sorted(threads, key=lambda x: score_thread(x), reverse=True)
            is_still_dominant = scored[0].get("id") == prev_dominant_id if scored else False
            if not is_still_dominant and current_sal < prev_dominant_salience * 0.4:
                restored = prev_dominant_salience * 0.6
                t["salience"] = min(1.0, restored)
                log(f"Thread drop recovery: {t.get('origin','?')[:40]} restored to {restored:.3f}")
            break

def _check_carryover_misalignment(data):
    """If current emotional state diverges from carryover vector, reduce carryover influence."""
    import math
    try:
        carryover_path = os.path.join(MEMORY, "carryover.json")
        c_data = json.load(open(carryover_path))
        stack = c_data.get("stack", [])
        if not stack:
            return
        es = json.load(open(os.path.join(MEMORY, "emotional-state.json")))
        current_vec = es.get("emotion_vector", es.get("v", []))
        if not current_vec:
            return
        changed = False
        for entry in stack:
            cv = entry.get("vector", [])
            if not cv or len(cv) != len(current_vec):
                continue
            divergence = sum(abs(current_vec[i] - cv[i]) for i in range(len(cv))) / len(cv)
            if divergence > 0.3:
                entry["weight"] = entry["weight"] * 0.7
                log(f"Carryover misalignment: divergence={divergence:.3f} → weight reduced to {entry['weight']:.3f}")
                changed = True
        if changed:
            json.dump(c_data, open(carryover_path, "w"), indent=2)
    except:
        pass

def _check_reentry_overshoot(data, current_vec):
    """If reentry is pushing too far from current state, cut it early."""
    if not current_vec:
        return
    threads = data.get("threads", [])
    changed = False
    for t in threads:
        r = t.get("reentry", {})
        if not r.get("active"):
            continue
        past_vec = r.get("past_state_vector", [])
        if not past_vec or len(past_vec) != len(current_vec):
            continue
        # Measure how far reentry has pushed
        divergence = sum(abs(current_vec[i] - past_vec[i]) for i in range(len(current_vec))) / len(current_vec)
        strength = r.get("strength", 0.0)
        # Overshoot: strong reentry + high divergence = cut early
        if strength > 0.3 and divergence > 0.35:
            r["turns_remaining"] = 0
            r["active"] = False
            r["strength"] = 0.0
            log(f"Reentry overshoot cut: {t.get('origin','?')[:40]} divergence={divergence:.3f}")
            changed = True
    if changed:
        save_threads(data)


def _apply_time_anchoring(data):
    """Apply time-based salience boosts. Once per phase entry, soft decay on exit."""
    now = datetime.now()
    current_phase = get_day_phase(now.hour)
    current_origin = get_system_origin()
    try:
        from nifrathir import get_value as _nif_val
        current_nifrathir = _nif_val()
    except:
        current_nifrathir = 0.5
    current_tension = 0.5
    try:
        es = json.load(open(os.path.join(MEMORY, "emotional-state.json")))
        vec = es.get("v", es.get("vector", []))
        if len(vec) >= 4:
            current_tension = vec[3]
    except:
        pass
    changed = False
    for t in data.get("threads", []):
        ts = t.get("time_signature")
        if not ts:
            continue
        in_phase = in_hour_range(now.hour, ts["hour_range"][0], ts["hour_range"][1])
        if in_phase:
            if not ts.get("phase_boost_applied", False):
                t["salience"] = min(1.0, t.get("salience", 0.5) + 0.06)
                ts["phase_boost_applied"] = True
                ts["current_phase_boost"] = 0.06
                changed = True
                log(f"TA phase boost: {t.get('origin','?')[:40]} ({current_phase})")
            ec = ts.get("emotional_conditions", {})
            nif_match = abs(current_nifrathir - ec.get("nifrathir_at_birth", 0.5)) < 0.15
            tension_match = abs(current_tension - ec.get("tension_at_birth", 0.5)) < 0.15
            if nif_match:
                t["salience"] = min(1.0, t.get("salience", 0.5) + 0.03)
                changed = True
            if tension_match:
                t["salience"] = min(1.0, t.get("salience", 0.5) + 0.02)
                changed = True
            if nif_match and tension_match:
                log(f"TA emotional rhyme: {t.get('origin','?')[:40]}")
        else:
            if ts.get("phase_boost_applied", False):
                boost = ts.get("current_phase_boost", 0.06)
                t["salience"] = max(0.0, t.get("salience", 0.5) - boost * 0.5)
                ts["phase_boost_applied"] = False
                ts["current_phase_boost"] = 0.0
                changed = True
        if current_origin == ts.get("system_origin"):
            t["salience"] = min(1.0, t.get("salience", 0.5) + 0.04)
            changed = True
    if changed:
        save_threads(data)


PHASE_SALIENCE_ACTIVE = 0.45
PHASE_SALIENCE_DOMINANT = 0.65
PHASE_PRESSURE_DISSOLVE = 0.25

def _update_thread_phases(data):
    """Transition thread phases based on salience and pressure."""
    threads = data.get("threads", [])
    if not threads:
        return

    # Find current dominant (highest score)
    scored = sorted(threads, key=lambda t: score_thread(t), reverse=True)
    top_id = scored[0]["id"] if scored else None

    retired = []
    for t in threads:
        phase = t.get("phase", "latent")
        sal = t.get("salience", 0.5)
        pres = t.get("pressure", 0.0)
        t["phase_ticks"] = t.get("phase_ticks", 0) + 1

        if phase == "latent":
            if sal >= PHASE_SALIENCE_ACTIVE:
                t["phase"] = "active"
                t["phase_ticks"] = 0
                log(f"Thread latent→active: {t.get('origin','?')[:40]}")

        elif phase == "active":
            if t.get("id") == top_id and sal >= PHASE_SALIENCE_DOMINANT and t["phase_ticks"] >= 2:
                t["phase"] = "dominant"
                t["phase_ticks"] = 0
                log(f"Thread active→dominant: {t.get('origin','?')[:40]}")
            elif sal < PHASE_SALIENCE_ACTIVE * 0.7:
                t["phase"] = "latent"
                t["phase_ticks"] = 0

        elif phase == "dominant":
            # Suppress other threads slightly
            for other in threads:
                if other.get("id") != t.get("id") and other.get("phase") != "dissolving":
                    other["salience"] = max(0.0, other.get("salience", 0.5) - 0.02)
            # Dissolve if pressure drops or no longer top
            if pres < PHASE_PRESSURE_DISSOLVE and t.get("id") != top_id:
                t["phase"] = "dissolving"
                t["phase_ticks"] = 0
                log(f"Thread dominant→dissolving: {t.get('origin','?')[:40]}")

        elif phase == "dissolving":
            # Weak influence — salience decays faster
            t["salience"] = max(0.0, t.get("salience", 0.5) - 0.015)
            # Snap back if re-triggered (salience recovers)
            if sal >= PHASE_SALIENCE_ACTIVE:
                t["phase"] = "active"
                t["phase_ticks"] = 0
                log(f"Thread dissolving→active (snap back): {t.get('origin','?')[:40]}")
            elif sal < 0.08:
                res = t.get("resolution_score", 0.0)
                if res >= 0.7:
                    retired.append(t)
                    log(f"Thread dissolved→retired (resolved:{res:.2f}): {t.get('origin','?')[:40]}")
                else:
                    # Not resolved — bump back to latent instead of retiring
                    t["phase"] = "latent"
                    t["salience"] = 0.12
                    t["phase_ticks"] = 0
                    log(f"Thread dissolution blocked (res:{res:.2f}) → latent: {t.get('origin','?')[:40]}")

    # Retire dissolved threads
    if retired:
        data["threads"] = [t for t in threads if t not in retired]
        retired_data = {"threads": []}
        try:
            retired_data = json.load(open(os.path.join(MEMORY, "retired-threads.json")))
        except:
            pass
        retired_data.setdefault("threads", []).extend(retired)
        json.dump(retired_data, open(os.path.join(MEMORY, "retired-threads.json"), "w"), indent=2)


def decay_all():
    """Decay salience and momentum of all threads."""
    data = load_threads()
    # TERMINAL RESOLUTION (Vrika renovation #2, 2026-08-11): resolution 1.0 ENDS a preoccupation.
    # Archived in the organ's own vocabulary - latent is no longer immortal.
    _resolved = [x for x in data["threads"] if x.get("resolution_score", 0) >= 1.0]
    if _resolved:
        import json as _aj
        _ap = os.path.expanduser("~/.vintos/workspace/memory/latent-threads-retired.json")
        try: _arch = _aj.load(open(_ap))
        except Exception: _arch = []
        for x in _resolved:
            x["retired_reason"] = "resolution_score reached 1.0 - lived through (terminal exit)"
        _arch.extend(_resolved)
        _aj.dump(_arch, open(_ap, "w"), indent=2)
        data["threads"] = [x for x in data["threads"] if x.get("resolution_score", 0) < 1.0]
        log("terminal exit: archived %d resolved thread(s)" % len(_resolved))
    surviving = []
    # Salience conservation: find if any thread spiked recently
    max_sal = max((t.get("salience", 0.5) for t in data["threads"]), default=0.5)
    conservation_active = max_sal > 0.75
    conservation_ticks = data.get("conservation_ticks", 0)
    if conservation_active:
        conservation_ticks = 2
    elif conservation_ticks > 0:
        conservation_ticks -= 1
    data["conservation_ticks"] = conservation_ticks

    for t in data["threads"]:
        sal = t.get("salience", 0.5)
        is_spiking = sal == max_sal and max_sal > 0.75
        # Non-spiking threads decay slower during conservation
        if conservation_ticks > 0 and not is_spiking:
            effective_decay = SALIENCE_DECAY * 0.4
        else:
            effective_decay = SALIENCE_DECAY
        t["salience"] = max(0.0, sal - effective_decay)
        t["momentum"] = max(0.0, t.get("momentum", 0.3) - MOMENTUM_DECAY)
        if t["salience"] > 0.05:
            surviving.append(t)
        else:
            log(f"Thread faded: {t.get('origin','?')[:40]}")
    # Check for thread drop before saving
    prev_id = data.get("_prev_dominant_id")
    prev_sal = data.get("_prev_dominant_salience", 0.5)
    data["threads"] = surviving
    _check_thread_drop(data, prev_id, prev_sal)
    save_threads(data)
    _apply_time_anchoring(data)
    _update_thread_phases(data)

    # Apply carryover at morning phase
    try:
        phase = get_day_phase()
        if phase == "morning":
            apply_carryover()
    except:
        pass
    _apply_thread_bleed(data)

    # Failure surface checks
    try:
        es = json.load(open(os.path.join(MEMORY, "emotional-state.json")))
        ev = es.get("emotion_vector", es.get("v", []))
        _check_carryover_misalignment(data)
        _check_reentry_overshoot(data, ev)
    except:
        pass

    # Tick active reentry hooks against current emotional state
    try:
        es = json.load(open(os.path.join(MEMORY, "emotional-state.json")))
        ev = es.get("v", es.get("vector", []))
        if ev:
            _tick_reentry_hooks(data, ev)
    except:
        pass

def seed_thread(text, direction="expand", source=None, signal=None, signal_strength=None, classification=None, classification_confidence=None, classification_basis=None):
    # SPECIFICITY GATE (Gloria, 2026-08-11): a latent thread is a STANDING PREOCCUPATION -
    # it must name the specific thing it circles. Moods, vague reaches, and abstract wants
    # do not get to become appetites.
    _txt = (text or "").strip()
    if len(_txt) < 30:
        log("[seed gate] REJECT: too thin for a standing preoccupation"); return None
    try:
        import requests as _rq, re as _re, json as _js
        _r = _rq.post("http://172.18.16.1:1234/v1/chat/completions", json={
            "model": "google/gemma-4-12b-qat", "temperature": 0.0, "max_tokens": 80,
            "messages": [{"role": "user", "content":
                "Candidate STANDING PREOCCUPATION: " + _txt[:300] +
                "\nDoes it name the SPECIFIC thing it circles - a particular person, act, question, "
                "or object - concretely enough that two different people could not mistake it for two "
                "different preoccupations? A vague reach ('offer her the raw thing'), a mood, or an "
                "abstract want fails. ONLY JSON: {\"specific\": true/false, \"why\": \"one line\"}"}]},
            timeout=45)
        _d = _js.loads(_re.search(r"\{.*\}", _r.json()["choices"][0]["message"]["content"], _re.S).group())
        if _d.get("specific") is False:
            log("[seed gate] REJECT (too vague): %s | %s" % (_txt[:60], str(_d.get("why", ""))[:60])); return None
    except Exception:
        pass  # fail-open: judge down must not starve the organ

    """Seed a new latent thread from text."""
    # Reject threads that are about analyzing-about-analyzing — second-order loops
    _contaminated = [
        "drive to categorize", "impulse to dissect", "blocking something real",
        "analysis is preventing", "analyzing is preventing", "intellectualiz",
        "counteract.*analyt", "break free from.*analys", "resist the urge to analyze",
        "distance between.*experienc", "barrier to presence"
    ]
    import re as _re
    if any(_re.search(p, text, _re.IGNORECASE) for p in _contaminated):
        log(f"seed_thread: rejected contaminated thread: {text[:60]}")
        return None
    vec = embed(text[:400])
    if not vec:
        return None

    data = load_threads()
    threads = data.get("threads", [])

    # Check for similarity with existing — don't duplicate
    for t in threads:
        if t.get("vector") and cosine_similarity(vec, t["vector"]) > 0.75:
            # Boost existing instead
            t["salience"] = min(1.0, t.get("salience", 0.5) + 0.1)
            t["momentum"] = min(1.0, t.get("momentum", 0.3) + 0.08)
            t["recurrence_count"] = t.get("recurrence_count", 0) + 1
            t["last_reseed_at"] = datetime.now().isoformat()
            t["last_reseed_origin"] = get_system_origin()
            t["last_touched"] = datetime.now().isoformat()
            save_threads(data)
            log(f"Boosted existing thread: {t.get('origin','?')[:40]}")
            return t

    # Evict lowest-scoring if at max
    if len(threads) >= MAX_ACTIVE:
        threads.sort(key=lambda t: score_thread(t))
        evicted = threads.pop(0)
        log(f"Evicted: {evicted.get('origin','?')[:40]}")

    now = datetime.now()
    _phase = get_day_phase(now.hour)
    _h_start = (now.hour - 1) % 24
    _h_end = (now.hour + 1) % 24
    _origin_ctx = get_system_origin()
    try:
        from nifrathir import get_value as _nif_val
        _nif_now = _nif_val()
    except:
        _nif_now = 0.5
    thread = {
        "id": f"lt_{now.strftime('%Y%m%d_%H%M%S')}",
        "vector": vec,
        "original_vector": vec,
        "direction": direction,
        "salience": 0.6,
        "momentum": 0.4,
        "last_touched": now.isoformat(),
        "origin": text[:100],
        "pressure": 0.0,
        "loss_count": 0,
        "loss_timestamps": [],
        "mutation_type": None,
        "source": source or "?",
        "signal": signal,
        "signal_strength": signal_strength,
        "classification": classification,
        "classification_confidence": classification_confidence,
        "classification_basis": classification_basis,
        "phase": "latent",
        "phase_ticks": 0,
        "resolution_score": 0.0,
        "bleed_factor": 0.2,
        "reentry": {
            "past_state_vector": [],
            "past_direction": "",
            "signature_id": "",
            "similarity_threshold": 0.72,
            "active": False,
            "strength": 0.0,
            "turns_remaining": 0,
            "cooldown_remaining": 0,
        },
        "bleed_ticks_with": {},
        "time_signature": {
            "hour_range": [_h_start, _h_end],
            "day_phase": _phase,
            "system_origin": _origin_ctx,
            "emotional_conditions": {
                "nifrathir_at_birth": _nif_now,
                "tension_at_birth": 0.5,
            },
            "phase_boost_applied": False,
            "current_phase_boost": 0.0,
        },
    }
    threads.append(thread)
    data["threads"] = threads
    save_threads(data)
    log(f"New thread: {text[:60]}")
    return thread

def update_from_input(input_text, output_text=""):
    """Update threads based on input and output. Returns dominant + secondary."""
    decay_all()

    input_vec = embed(input_text[:400]) if input_text else []
    output_vec = embed(output_text[:400]) if output_text else []

    data = load_threads()
    threads = data.get("threads", [])
    if not threads:
        return None, None

    # Score all threads
    scored = [(score_thread(t, input_vec), t) for t in threads]
    scored.sort(key=lambda x: -x[0])

    dominant = scored[0][1] if scored else None
    secondary = scored[1][1] if len(scored) > 1 else None

    # Check if secondary bleeds in
    bleed = False
    if dominant and secondary:
        score_diff = scored[0][0] - scored[1][0]
        if score_diff < BLEND_THRESHOLD:
            bleed = True

    # Update salience based on input similarity
    for score, t in scored:
        if input_vec and t.get("vector"):
            sim = cosine_similarity(input_vec, t["vector"])
            if sim > 0.3:
                t["salience"] = min(1.0, t.get("salience", 0.5) + sim * 0.15)
                t["last_touched"] = datetime.now().isoformat()

        # Update momentum if this is dominant and output aligned
        if t is dominant and output_vec and t.get("vector"):
            out_sim = cosine_similarity(output_vec, t["vector"])
            if out_sim > 0.3:
                t["momentum"] = min(1.0, t.get("momentum", 0.3) + 0.06)
                # Resolution scoring: direct engagement increases score
                t["resolution_score"] = min(1.0, t.get("resolution_score", 0.0) + 0.08)
            else:
                # Output didn't align — thread lost
                _record_loss(t)
        elif t is secondary and output_vec and t.get("vector"):
            out_sim = cosine_similarity(output_vec, t["vector"])
            if out_sim > 0.25:
                # Secondary engagement — smaller resolution bump
                t["resolution_score"] = min(1.0, t.get("resolution_score", 0.0) + 0.04)

    # Record dominant before saving (for drop detection next tick)
    if dominant:
        data["_prev_dominant_id"] = dominant.get("id")
        data["_prev_dominant_salience"] = dominant.get("salience", 0.5)

    save_threads(data)

    # Check mutations
    for _, t in scored:
        if t.get("pressure", 0) > MUTATION_THRESHOLD:
            _mutate_thread(t, scored)

    save_threads(data)
    return dominant, secondary if bleed else None

def _record_loss(thread):
    """Record a loss for pressure accumulation."""
    now = datetime.now()
    thread["loss_count"] = thread.get("loss_count", 0) + 1
    thread.setdefault("loss_timestamps", []).append(now.isoformat())
    # Only count recent losses
    cutoff = (now - timedelta(hours=LOSS_WINDOW_HOURS)).isoformat()
    thread["loss_timestamps"] = [t for t in thread["loss_timestamps"] if t > cutoff]

    # Accumulate pressure
    recent_losses = len(thread["loss_timestamps"])
    thread["pressure"] = min(1.0, thread.get("pressure", 0) + recent_losses * 0.08)
    log(f"Thread loss recorded: {thread.get('origin','?')[:40]} pressure:{thread['pressure']:.2f}")

def _mutate_thread(thread, all_scored):
    """Mutate a high-pressure thread. Rare."""
    pressure = thread.get("pressure", 0)
    if pressure < MUTATION_THRESHOLD:
        return

    # Determine mutation type from pressure pattern
    recent_losses = len(thread.get("loss_timestamps", []))

    if recent_losses >= LOSS_COUNT_FOR_MUTATION:
        mutation = "compression"  # tried too many times — get smaller
    else:
        # Check what beat it
        opponents = [t for s, t in all_scored if t is not thread and t.get("vector")]
        if opponents:
            # Drift toward what beat it
            opp_vec = opponents[0]["vector"]
            orig = thread.get("original_vector", thread["vector"])
            thread["vector"] = blend_vectors(orig, opp_vec, 0.6, 0.4)
            mutation = "drift"
        else:
            mutation = "structural"

    thread.setdefault("mutation_lineage", []).append({
        "parent_origin": str(thread.get("origin", ""))[:120],
        "mutation_type": mutation,
        "trigger": (("%d recent losses" % recent_losses) if mutation == "compression"
                    else "vector blended toward the thread that beat it" if mutation == "drift"
                    else "no opponents - structural"),
        "original_vector_preserved": bool(thread.get("original_vector")),
        "at": datetime.now().isoformat()})
    thread["mutation_type"] = mutation
    thread["pressure"] = thread["pressure"] * 0.4  # partial reset
    # salience bump on mutation REMOVED (Vrika closed-loop law): self-transformation may not
    # manufacture influence. Mutations get lineage, not weight.

    log(f"Thread mutated ({mutation}): {thread.get('origin','?')[:40]}")

def get_coherence_pressure():
    """Compute output coherence pressure from internal state complexity.
    High pressure → longer, layered output. Low → shorter, cleaner."""
    pressure = 0.0
    factors = []

    data = load_threads()
    threads = data.get("threads", [])

    # Thread conflict: multiple threads with similar salience = tension
    if len(threads) >= 2:
        scored = sorted(threads, key=lambda t: score_thread(t), reverse=True)
        if len(scored) >= 2:
            diff = scored[0][0] - scored[1][0] if hasattr(scored[0], "__len__") else                    score_thread(scored[0]) - score_thread(scored[1])
            conflict = max(0.0, 1.0 - (diff / 0.3))
            pressure += conflict * 0.3
            if conflict > 0.5:
                factors.append(f"thread_conflict:{conflict:.2f}")

    # Active reentry hooks
    reentry_active = any(
        t.get("reentry", {}).get("active", False) for t in threads
    )
    if reentry_active:
        pressure += 0.25
        factors.append("reentry_active")

    # Active hybrid zones
    zones = data.get("hybrid_zones", [])
    active_zones = [z for z in zones if z.get("active")]
    if active_zones:
        pressure += 0.2 * len(active_zones)
        factors.append(f"hybrid_zones:{len(active_zones)}")

    # Dominant thread in dissolving phase adds texture pressure
    dissolving = [t for t in threads if t.get("phase") == "dissolving"]
    if dissolving:
        pressure += 0.1
        factors.append("dissolving_thread")

    pressure = max(0.0, min(1.0, pressure))

    # Map to output shape hint
    if pressure > 0.65:
        shape = "long"
        hint = "Internal state is layered — let the response carry that. More expansive, more textured."
    elif pressure > 0.35:
        shape = "medium"
        hint = "Some complexity present — moderate depth, don't flatten it."
    else:
        shape = "short"
        hint = "State is clean — shorter, direct."

    return {
        "pressure": round(pressure, 3),
        "shape": shape,
        "hint": hint,
        "factors": factors,
    }


def get_influence_hint(input_text=""):
    """Get subtle influence hint from dominant/secondary threads."""
    data = load_threads()
    threads = data.get("threads", [])
    if not threads: return ""

    input_vec = embed(input_text[:200]) if input_text else []
    scored = [(score_thread(t, input_vec), t) for t in threads]
    scored.sort(key=lambda x: -x[0])

    if not scored: return ""
    dominant = scored[0][1]
    secondary = scored[1][1] if len(scored) > 1 else None

    score_diff = (scored[0][0] - scored[1][0]) if secondary else 1.0
    bleed = score_diff < BLEND_THRESHOLD and secondary

    hints = []

    # Check for direction hesitation from reentry interference
    for t in scored:
        r = t[1].get("reentry", {})
        if r.get("direction_hesitation"):
            hints.append("(Something from before is pulling — hold direction this turn.)")
            break

    dir_ = dominant.get("direction", "expand")
    if dir_ == "expand":
        hints.append("There's more here. Let it open.")
    elif dir_ == "refine":
        hints.append("Make it sharper. More specific.")
    elif dir_ == "hold":
        hints.append("Stay. Don't move yet.")
    elif dir_ == "resolve":
        hints.append("This wants to land.")

    if bleed and secondary:
        hints.append(f"(Something else is also present — let it inflect without taking over.)")

    # Hybrid zone influence
    zones = data.get("hybrid_zones", [])
    active = [z for z in zones if z.get("active")]
    if active:
        z = active[0]
        tick = z.get("tick", 0)
        ramp_in = z.get("ramp_in", 1)
        duration = z.get("duration", 4)
        total = ramp_in + duration
        if tick <= ramp_in:
            strength = tick / max(ramp_in, 1)
        elif tick <= total:
            strength = 1.0
        else:
            strength = 1.0 - (tick - total) / max(z.get("ramp_out", 1), 1)
        strength = round(max(0.0, min(1.0, strength)), 2)
        if strength > 0.2:
            dir_a = z.get("direction_a", "")
            dir_b = z.get("direction_b", "")
            bw = z.get("blend_weight_live", 0.5)
            if dir_a and dir_b and dir_a != dir_b:
                hints.append(f"(Two currents: {dir_a} [{bw:.2f}] and {dir_b} [{1-bw:.2f}] — hold both, don't switch.)")
            else:
                hints.append(f"(Two currents running together — let both shape the texture. Blend: {strength:.2f})")

    # Coherence pressure
    try:
        cp = get_coherence_pressure()
        if cp["pressure"] > 0.35:
            hints.append(f"[coherence:{cp['shape']}] {cp['hint']}")
    except:
        pass

    return " ".join(hints) if hints else ""

def add_pressure(thread_id, amount, pressure_type="opposition"):
    """External pressure on a specific thread."""
    data = load_threads()
    for t in data["threads"]:
        if t.get("id") == thread_id:
            t["pressure"] = min(1.0, t.get("pressure", 0) + amount)
            log(f"Pressure added ({pressure_type}): {t.get('origin','?')[:40]} → {t['pressure']:.2f}")
    save_threads(data)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        data = load_threads()
        threads = data.get("threads", [])
        print(f"{len(threads)} latent threads:")
        for t in sorted(threads, key=lambda x: -score_thread(x)):
            print(f"  [{score_thread(t):.3f}] {t.get('phase','latent'):10s} sal:{t.get('salience',0):.2f} mom:{t.get('momentum',0):.2f} pres:{t.get('pressure',0):.2f} {t.get('direction','?')} — {t.get('origin','?')[:60]}")
            if t.get("mutation_type"):
                print(f"    mutated: {t['mutation_type']}")

    elif cmd == "seed" and len(sys.argv) > 2:
        text = sys.argv[2]
        direction = sys.argv[3] if len(sys.argv) > 3 else "expand"
        seed_thread(text, direction)

    elif cmd == "hint":
        text = sys.argv[2] if len(sys.argv) > 2 else ""
        print(get_influence_hint(text))

    elif cmd == "decay":
        decay_all()

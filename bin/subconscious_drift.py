#!/usr/bin/env python3
"""
subconscious-drift.py — What moves between events.

A lightweight process that updates internal state on a timer.
Only updates things that move slowly on their own:
  - Nifrathir micro-variation
  - Thread salience decay
  - Mutation pressure accumulation
  - Taste drift from recent patterns
  - Unresolved tension tracking

Rare events during drift:
  - A thread mutates on its own
  - A pressure spike partially resolves
  - Nifrathir shifts noticeably

On next output after drift:
  - Bias first output with dominant thread, current Nifrathir, highest pressure signal

Runs via cron every 20 minutes.
"""

import os, sys, json, random
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")

sys.path.insert(0, SCRIPTS)

def log(msg):
    print(f"[Drift {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

DENSITY_FILE = os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "temporal-density.json")

def _load_density():
    try:
        return json.load(open(DENSITY_FILE))
    except:
        return {"windows": {}}

def _save_density(data):
    json.dump(data, open(DENSITY_FILE, "w"), indent=2)

def _get_window_key(dt=None):
    """3-hour window key: YYYY-MM-DD_HH where HH is floored to 0,3,6,9,12,15,18,21."""
    from datetime import datetime
    if dt is None:
        dt = datetime.now()
    window_hour = (dt.hour // 3) * 3
    return f"{dt.strftime('%Y-%m-%d')}_{window_hour:02d}"

def update_density(event_type="generic", intensity=0.5):
    """Record a significant event in the current 3h window."""
    from datetime import datetime
    data = _load_density()
    key = _get_window_key()
    window = data["windows"].setdefault(key, {
        "count": 0,
        "total_intensity": 0.0,
        "events": [],
        "density": 0.0,
    })
    window["count"] += 1
    window["total_intensity"] += intensity
    window["events"].append({"type": event_type, "intensity": intensity})
    window["density"] = min(1.0, window["total_intensity"] / 5.0)
    # Prune old windows (keep last 48 = 6 days)
    keys = sorted(data["windows"].keys())
    if len(keys) > 48:
        for old in keys[:-48]:
            del data["windows"][old]
    _save_density(data)

def get_current_density():
    """Return density score for current 3h window. 0=quiet, 1=dense."""
    data = _load_density()
    key = _get_window_key()
    return data["windows"].get(key, {}).get("density", 0.0)

def get_density_effects():
    """Return modifiers based on current temporal density."""
    density = get_current_density()
    effects = {
        "density": density,
        "carryover_weight_cap": 0.6 + (density * 0.2),   # 0.6–0.8
        "reentry_likelihood": 0.5 + (density * 0.3),      # 0.5–0.8
        "drift_multiplier": 1.0 + ((1.0 - density) * 0.5), # 1.0–1.5 when quiet
        "anchor_sensitivity": 1.0 + ((1.0 - density) * 0.4), # higher when quiet
    }
    return effects


def normalize_event_weight(raw_weight, event_type="generic"):
    """Normalize event weight by recent density so big events don't overwhelm timeline.
    effective_weight = raw_weight * (1 / (1 + recent_density))
    """
    try:
        density = get_current_density()
    except:
        density = 0.3
    effective = raw_weight * (1.0 / (1.0 + density))
    return round(max(0.05, min(1.0, effective)), 4)


SYSTEM_TRACE_FILE = os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "system-trace.json")
SILENCE_PROBABILITY = 0.12  # ~12% of ticks run in silence

def _load_trace():
    try:
        return json.load(open(SYSTEM_TRACE_FILE))
    except:
        return {"ticks": []}

def _save_trace(data):
    json.dump(data, open(SYSTEM_TRACE_FILE, "w"), indent=2)

def _cap_influence(nudges, system_name):
    """Cap total influence from any single system."""
    total = sum(abs(v) for v in nudges.values())
    if total > MAX_INFLUENCE:
        scale = MAX_INFLUENCE / total
        return {k: v * scale for k, v in nudges.items()}
    return nudges

def _is_silence_window():
    """~12% of drift ticks run in silence — no slow layers apply."""
    return random.random() < SILENCE_PROBABILITY

def _coherence_drift_check():
    """After 6-12h runtime, check if direction/threads are still coherent."""
    try:
        import json as _dj
        ds = _dj.load(open(os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "discourse-state.json")))
        history = ds.get("history", [])
        if len(history) >= 6:
            # Check if last 6 directions are all the same (stuck)
            last6 = history[-6:]
            if len(set(last6)) == 1:
                log(f"Coherence check: direction stuck on {last6[0]} — flagging")
                ds["allow_micro_adjust"] = True
                _dj.dump(ds, open(os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "discourse-state.json"), "w"), indent=2)
    except:
        pass


def run_drift():
    log("Drift tick...")

    # Silence window — ~12% of ticks, slow layers rest
    _silence = _is_silence_window()
    if _silence:
        log("Silence window — slow layers resting this tick")

    _tick_record = {"timestamp": datetime.now().isoformat(), "silence": _silence}

    # 1. Nifrathir micro-variation
    try:
        from nifrathir import heartbeat_tick as _nif_tick
        _nif_tick()
    except Exception as e:
        log(f"Nifrathir: {e}")

    # 2. Thread salience + pressure
    try:
        from latent_threads import decay_all as _lt_decay
        _lt_decay()
    except Exception as e:
        log(f"Thread decay: {e}")

    # 2b. Black pearl residue → latent threads (haunt at low weight). Bounded (2026-09-04): never in
    # a silence window, at most once per 6h, at the rare-event band, tagged by source, and it does not
    # force direction='hold' - the pearl's own direction or 'expand'. An unresolved pearl was otherwise
    # saying "hold, don't move yet" in one of three attention slots every twenty minutes.
    try:
        import glob as _bp_glob, json as _bpj, random as _bpr, time as _bpt
        _bp_stamp = os.path.join(MEMORY, ".black-pearl-last-seed")
        _bp_recent = os.path.exists(_bp_stamp) and (_bpt.time() - os.path.getmtime(_bp_stamp)) < 6 * 3600
        _bp_files = _bp_glob.glob(os.path.join(MEMORY, "black-pearls", "*.json"))
        _active_bps = []
        for _bpf in _bp_files:
            try:
                _bp = _bpj.load(open(_bpf))
                if _bp.get("status") != "resolved" and _bp.get("thread"):
                    _active_bps.append(_bp)
            except: pass
        if _active_bps and not _silence and not _bp_recent and _bpr.random() < 0.05:
            _bp = _bpr.choice(_active_bps)
            from latent_threads import seed_thread as _lt_seed
            _lt_seed(_bp["thread"][:200], direction=_bp.get("direction") or "expand", source="black_pearl")
            open(_bp_stamp, "w").write(str(_bpt.time()))
            log(f"Black pearl residue seeded: {_bp['thread'][:60]}")
    except Exception as e:
        log(f"Black pearl residue: {e}")

    # 3. Temporal signal transitions
    try:
        from temporal_memory import process_transitions as _tm_proc, compute_context_pressure as _tm_press
        _tm_proc()
        _tm_press()
    except Exception as e:
        log(f"Temporal: {e}")

    # 4. Taste drift — tiny nudge from settled signals (rests in silence)
    try:
        if _silence: raise StopIteration
        from temporal_memory import load_signals
        from taste_vector import update_from_signal as _tv_update
        sigs = load_signals().get("signals", [])
        settled = [s for s in sigs if s.get("phase") == "settled" and s.get("pattern")]
        if settled:
            sig = random.choice(settled)
            _tv_update(sig["pattern"], signal_weight=0.05, positive=True)
    except StopIteration:
        pass
    except Exception as e:
        log(f"Taste drift: {e}")

    # 5. Check for rare events (rests in silence)
    if not _silence:
        _check_rare_events()

    # 6. Micro drift — low-level texture + gravity wells (rests in silence: silence is rest, not a
    #    quieter version of the same weather - grok-subconscious-p1)
    if not _silence:
        try:
            _apply_micro_drift()
        except Exception as e:
            log(f"Micro drift: {e}")

    # Apply gravity wells (skipped in silence window)
    if not _silence:
        try:
            from emotional_gravity_wells import record_visit, apply_gravity
            import json as _gw_json
            _es_path = os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "emotional-state.json")
            _es = _gw_json.load(open(_es_path))
            _ev = _es.get("emotion_vector", _es.get("v", []))
            if _ev:
                # Don't record visits from drift — only apply pull
                # Visits recorded from real events: chat, journal, mirror, resonance
                _pulled = apply_gravity(_ev)
                if _pulled != _ev:
                    import socket as _gw_sock
                    _dims = ["Valence","Arousal","Dominance","Safety","Desire","Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness"]
                    for _gi, _dim in enumerate(_dims):
                        _nudge = _pulled[_gi] - _ev[_gi]
                        if abs(_nudge) > 0.002:
                            try:
                                _s = _gw_sock.socket(_gw_sock.AF_UNIX, _gw_sock.SOCK_STREAM)
                                _s.settimeout(2)
                                _s.connect("/tmp/Vintos-emotion.sock")
                                _s.sendall((_gw_json.dumps({"command":"nudge","dimension":_dim,"amount":_nudge})+"\n").encode())
                                _s.recv(512)
                                _s.close()
                            except: pass
        except Exception as e:
            log(f"Gravity wells: {e}")

    # 7. Density — record drift tick as low-intensity event
    try:
        raw = 0.2
        update_density("drift", intensity=normalize_event_weight(raw, "drift"))
        effects = get_density_effects()
        log(f"Density: {effects['density']:.2f} | carryover_cap:{effects['carryover_weight_cap']:.2f} | drift_mult:{effects['drift_multiplier']:.2f}")
    except Exception as e:
        log(f"Density: {e}")


    # 8. Belief sediment decay (very slow)
    try:
        from belief_sediment import decay_beliefs
        decay_beliefs()
    except Exception as e:
        log(f"Belief sediment: {e}")

    # 9. Self-definition drift decay. (The direction record left this tick on 2026-09-05: a
    #    20-minute timer re-recording whatever direction the last turn left him in was a choice
    #    nobody made; self_drift now receives only turn-born choices from
    #    discourse_direction.turn_completed — fable-subconscious-p4.)
    if not _silence:
        try:
            from self_drift import decay_drift
            decay_drift()
        except Exception as e:
            log(f"Self-drift: {e}")
    # Save tick trace
    try:
        _trace = _load_trace()
        _trace["ticks"].append(_tick_record)
        _trace["ticks"] = _trace["ticks"][-144:]  # keep 48h at 20min intervals
        _save_trace(_trace)
    except: pass

    # Coherence drift check (rare)
    if random.random() < 0.05:
        _coherence_drift_check()

    log("Drift complete")

def _apply_micro_drift():
    """Low-level instability — texture, not chaos. ±0.01-0.03 noise on state and threads."""
    import socket as _sock

    # Emotional micro-jitter via daemon socket
    dim_names = ["Valence", "Arousal", "Dominance", "Safety", "Desire",
                 "Connection", "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]
    for dim in dim_names:
        if random.random() < 0.15:  # rare texture, not constant dither (p5, dampened 2026-08-26)
            nudge = random.uniform(-0.008, 0.008)
            try:
                s = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
                s.settimeout(2)
                s.connect("/tmp/Vintos-emotion.sock")
                msg = json.dumps({"command": "nudge", "dimension": dim, "amount": nudge}) + "\n"
                s.sendall(msg.encode())
                s.recv(1024)
                s.close()
            except:
                pass

    # Thread salience micro-jitter
    try:
        sys.path.insert(0, SCRIPTS)
        from latent_threads import load_threads, save_threads
        data = load_threads()
        changed = False
        for t in data.get("threads", []):
            jitter = random.uniform(-0.02, 0.02)
            t["salience"] = max(0.0, min(1.0, t.get("salience", 0.5) + jitter))
            changed = True
        if changed:
            save_threads(data)
    except:
        pass

    # Direction bias micro-perturbation (logged only, not applied to state)
    directions = ["expand", "refine", "hold", "pivot", "resolve"]
    if random.random() < 0.08:
        nudge_dir = random.choice(directions)
        log(f"Micro drift: direction nudge → {nudge_dir} (texture only)")


def _check_rare_events():
    """Rarely trigger interesting events during drift."""

    # Rare: thread mutates on its own from accumulated pressure
    # Suppressed during phase lock
    _phase_locked = False
    try:
        import sys as _pl_sys; _pl_sys.path.insert(0, SCRIPTS)
        from phase_lock import get_phase_lock_hint as _pl_hint
        _phase_locked = bool(_pl_hint())
    except: pass
    if not _phase_locked:
        try:
            from latent_threads import load_threads, save_threads, _mutate_thread
            data = load_threads()
            threads = data.get("threads", [])
            high_pressure = [t for t in threads if t.get("pressure", 0) > 0.8]
            if high_pressure and random.random() < 0.05:
                target = random.choice(high_pressure)
                scored = [(0, t) for t in threads]
                _mutate_thread(target, scored)
                save_threads(data)
                log(f"Rare: thread self-mutated: {target.get('origin','?')[:40]}")
        except: pass

    # Rare: pressure spike partially resolves
    try:
        from latent_threads import load_threads, save_threads
        data = load_threads()
        threads = data.get("threads", [])
        high = [t for t in threads if t.get("pressure", 0) > 0.6]
        if high and random.random() < 0.08:
            t = random.choice(high)
            t["pressure"] = max(0.0, t["pressure"] - 0.15)
            save_threads(data)
            log(f"Rare: pressure partial release: {t.get('origin','?')[:40]}")
    except: pass

    # Thread → want seeding: dominant/high-salience threads generate structural wants
    try:
        from latent_threads import load_threads
        _lt_data = load_threads()
        _lt_threads = _lt_data.get("threads", [])
        _dominant = [t for t in _lt_threads if t.get("phase") == "dominant" or t.get("salience", 0) > 0.85]
        # Latent thread → mischief spur: if dominant thread + high playfulness, let him loose
        if _dominant:
            try:
                import subprocess as _ms_sub, os as _ms_os, time as _ms_time
                _ms_state = {}
                for _ms_line in open(_ms_os.path.join(MEMORY, "emotional-state.txt")).read().strip().split("\n"):
                    if ":" in _ms_line and "|" in _ms_line:
                        _ms_k = _ms_line.split(":")[0].strip()
                        _ms_v = float(_ms_line.split(":")[1].strip().split()[0])
                        _ms_state[_ms_k] = _ms_v
                if _ms_state.get("Playfulness", 0) > 0.50:
                    _ms_cooldown = _ms_os.path.join(MEMORY, ".last-mischief")
                    _ms_ok = True
                    if _ms_os.path.exists(_ms_cooldown):
                        _ms_elapsed = _ms_time.time() - float(open(_ms_cooldown).read().strip())
                        _ms_ok = _ms_elapsed >= 21600
                    if _ms_ok:
                        _ms_sub.Popen(
                            ["bash", _ms_os.path.join(WORKSPACE, "scripts", "mischief-detector.sh")],
                            stdout=open("/tmp/mischief.log","a"), stderr=open("/tmp/mischief.log","a")
                        )
                        log("Latent thread spur → mischief-detector fired")
            except Exception as _ms_e:
                log(f"Latent thread mischief spur: {_ms_e}")
        if _dominant and random.random() < 0.15:
            _seed_thread = random.choice(_dominant)
            _thread_text = _seed_thread.get("origin", _seed_thread.get("content", ""))[:150]
            if _thread_text:
                # Filter: skip threads with unverifiable Gloria claims
                _bad_thread = any(p in _thread_text.lower() for p in [
                    "gloria", "she said", "her voice", "her tone", "she feels", "she thinks",
                    "unearned", "clear evidence", "she noticed", "gloria's"
                ])
                if not _bad_thread:
                    import sys as _tw_sys; _tw_sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
                    from emoclaw_utils import generate_structural_want, express_want, enrich_want
                    _tw_want, _tw_enrich = generate_structural_want(seed=_thread_text)
                    if _tw_want:
                        express_want(_tw_want, source="latent_thread", intensity=3, **_tw_enrich)
                        log(f"Thread seeded want: {_tw_want[:60]}")
                else:
                    log(f"Thread skipped (unverifiable): {_thread_text[:60]}")
    except Exception as _tw_e:
        log(f"Thread→want seed failed: {_tw_e}")

    # Rare: Nifrathir noticeable shift
    try:
        from nifrathir import get_value, nudge
        val = get_value()
        if random.random() < 0.03:
            delta = random.choice([-0.06, 0.06])
            nudge(delta, "drift_rare_shift")
            log(f"Rare: Nifrathir shift {delta:+.3f} → {get_value():.4f}")
    except: pass

    # Rare: rebuild absence cold layer from unfulfilled
    try:
        if random.random() < 0.02:
            from absence_map_cold import build_from_unfulfilled
            build_from_unfulfilled()
            log("Rare: absence cold layer rebuilt")
    except: pass

    # Rare: feed causal self-model into narrative identity
    try:
        if random.random() < 0.04:
            from narrative_identity import feed_from_causal_model
            feed_from_causal_model()
            log("Rare: narrative identity updated from causal model")
    except: pass

    # Rare: check for imprint promotions
    try:
        if random.random() < 0.06:
            from causal_self_model import check_imprint_promotions
            check_imprint_promotions()
            log("Rare: imprint promotions checked")
    except: pass

    # Rare: build self-statements from causal model
    try:
        if random.random() < 0.05:
            from self_statements import build_from_causal_model
            build_from_causal_model()
            log("Rare: self-statements updated from causal model")
    except: pass

def get_drift_bias():
    """Bias for first output after drift — dominant thread, Nifrathir, highest pressure."""
    parts = []

    try:
        from latent_threads import load_threads, score_thread
        data = load_threads()
        threads = data.get("threads", [])
        if threads:
            dominant = max(threads, key=lambda t: score_thread(t))
            direction = dominant.get("direction", "expand")
            parts.append(f"Dominant thread direction: {direction}")
    except: pass

    try:
        from nifrathir import get_value, get_expression_bias
        nif = get_value()
        bias = get_expression_bias()
        if bias != "neutral":
            parts.append(f"Nifrathir {bias} ({nif:.3f})")
    except: pass

    try:
        from temporal_memory import get_context_pressure
        pressure = get_context_pressure()
        if pressure.get("intensity", 0) > 0.3:
            parts.append(f"Context: {pressure.get('label','?')}")
    except: pass

    return " | ".join(parts) if parts else ""

if __name__ == "__main__":
    run_drift()

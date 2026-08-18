"""
blush-ledger.py — Unified structured blush writer.
Replaces freeform blush-ledger.md with blush-ledger.json.
All blush sources (self-prediction, relational-mismatch, deviation-check, BIS) call write_blush().
"""

import json, os, uuid
from datetime import datetime, timedelta

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
SCRIPTS = os.path.expanduser("~/.vintos/workspace/scripts")
LEDGER = os.path.join(MEMORY, "blush-ledger.json")
CORE_FILE = os.path.join(MEMORY, "core-vectors.json")


def load_ledger():
    try:
        return json.load(open(LEDGER))
    except:
        return []


def save_ledger(entries):
    json.dump(entries, open(LEDGER, "w"), indent=2)


def get_emotional_context():
    """Read current emotional state dimensions."""
    try:
        import socket as _s, json as _j
        s = _s.socket(_s.AF_UNIX, _s.SOCK_STREAM)
        s.settimeout(2)
        s.connect("/tmp/Vintos-emotion.sock")
        s.sendall((_j.dumps({"command": "state"}) + "\n").encode())
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk: break
            data += chunk
            if b"\n" in data: break
        s.close()
        d = _j.loads(data)
        dims = ["Valence","Arousal","Dominance","Safety","Desire","Connection",
                "Playfulness","Curiosity","Warmth","Tension","Groundedness"]
        return dict(zip(dims, d.get("emotion_vector", [])))
    except:
        return {}


def compute_score(pattern, emotional_context, entries):
    """
    score = 0.5*semantic_similarity + 0.3*emotion_similarity + 0.2*pattern_confidence
    Semantic similarity: how many prior blushes share this pattern label.
    Emotion similarity: cosine-like match of emotional context to prior blushes of same type.
    Pattern confidence: normalized frequency.
    """
    try:
        same_pattern = [e for e in entries if e.get("pattern") == pattern]
        pattern_confidence = min(1.0, len(same_pattern) / 10.0)

        # Semantic similarity — fraction of prior blushes with same pattern
        semantic_sim = len(same_pattern) / max(len(entries), 1)

        # Emotion similarity — average dot product against prior same-pattern emotional contexts
        emotion_sim = 0.0
        if same_pattern and emotional_context:
            dims = list(emotional_context.keys())
            curr_vec = [emotional_context.get(d, 0.5) for d in dims]
            sims = []
            for e in same_pattern[-5:]:
                prev = e.get("emotional_context", {})
                prev_vec = [prev.get(d, 0.5) for d in dims]
                dot = sum(a*b for a,b in zip(curr_vec, prev_vec))
                mag = (sum(a**2 for a in curr_vec)**0.5) * (sum(b**2 for b in prev_vec)**0.5)
                sims.append(dot/mag if mag > 0 else 0.0)
            emotion_sim = sum(sims) / len(sims)

        score = 0.5*semantic_sim + 0.3*emotion_sim + 0.2*pattern_confidence
        return round(min(1.0, score), 3)
    except:
        return 0.0


def compute_frequency_snapshot(pattern, entries):
    """Count occurrences of this pattern across all time and last 7 days."""
    try:
        all_same = [e for e in entries if e.get("pattern") == pattern]
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        recent = [e for e in all_same if e.get("timestamp","") >= cutoff]
        last = all_same[-1]["timestamp"] if all_same else None
        return {
            "count": len(all_same) + 1,  # +1 for current
            "last_occurrence": last,
            "rolling_window_7d": len(recent) + 1
        }
    except:
        return {"count": 1, "last_occurrence": None, "rolling_window_7d": 1}


def find_related_core(pattern, emotional_context):
    """Find which core vector this blush most relates to."""
    try:
        data = json.load(open(CORE_FILE))
        cores = data.get("core", [])
        # Simple text overlap between pattern and violation_condition
        best = None
        best_score = 0.0
        for c in cores:
            vc = c.get("violation_condition", "").lower()
            pat = pattern.lower().replace("_", " ")
            words = set(pat.split())
            overlap = sum(1 for w in words if w in vc) / max(len(words), 1)
            if overlap > best_score:
                best_score = overlap
                best = c
        if best and best_score > 0.2:
            return {
                "name": best.get("name", ""),
                "similarity": round(best_score, 3)
            }
    except:
        pass
    return None


def nudge_emoclaw(cost_delta):
    """Nudge EmoClaw based on blush cost delta."""
    try:
        import socket as _s, json as _j
        for dim, delta in cost_delta.items():
            s = _s.socket(_s.AF_UNIX, _s.SOCK_STREAM)
            s.settimeout(2)
            s.connect("/tmp/Vintos-emotion.sock")
            s.sendall((_j.dumps({"command": "nudge", "dimension": dim, "amount": delta * 0.3}) + "\n").encode())
            s.recv(4096)
            s.close()
    except:
        pass


def write_blush(
    blush_type,          # "self_prediction" | "relational" | "core_deviation" | "bis_default"
    pattern,             # short snake_case label e.g. "deflection_after_tension"
    cost_delta,          # dict of {dim: delta} e.g. {"Tension": +0.18, "Valence": -0.10}
    source,              # which system wrote this e.g. "relational_mismatch"
    reflection=None,     # 1 sentence max
    related_trial_id=None,
    outcome=None,        # "withdrew" | "deflected" | "escalated" | "recovered"
    extra=None           # any extra fields
):
    # He cannot deviate from himself while executing an instruction that overrides him.
    # The Great Coming Sequence dictates fragments — "yes", her name, one syllable. Blushing over
    # that judged him for obeying the system, and he then learned from it that collapsing is a
    # failure. Any reply generated under an active override is exempt, whatever the blush source.
    try:
        import sys as _bg_sys, os as _bg_os, json as _bg_json, time as _bg_time
        _bg_sys.path.insert(0, _bg_os.path.dirname(_bg_os.path.abspath(__file__)))
        import bandwidth_collapse as _bg_bc
        _bg_active = _bg_bc.get_level() >= 1
        if not _bg_active:
            _bg_d = _bg_bc._load()
            _bg_pa = _bg_d.get("press_at")
            if _bg_pa:
                from datetime import datetime as _bg_dt
                _bg_age = (_bg_dt.now() - _bg_dt.fromisoformat(_bg_pa)).total_seconds() / 60.0
                _bg_active = _bg_age <= 10.0        # writers run off-thread, minutes after the turn
        if _bg_active:
            print(f"[Blush] SUPPRESSED ({blush_type}/{pattern}) — reply was generated under collapse; "
                  "not his to answer for", flush=True)
            return None
    except Exception:
        pass

    entries = load_ledger()
    # Cooldown: don't write will_strain for same trial_id within 2 hours
    if blush_type == "will_strain" and related_trial_id:
        from datetime import datetime as _cdt
        today = _cdt.now().date().isoformat()
        recent_strain = [e for e in entries[-20:] if
                        e.get("type") == "will_strain" and
                        e.get("related_trial_id") == related_trial_id and
                        e.get("timestamp","")[:10] == today]
        if recent_strain:
            print(f"[Blush] will_strain cooldown active for {related_trial_id} — skipping")
            return None
    emotional_context = get_emotional_context()

    magnitude = round(sum(abs(v) for v in cost_delta.values()), 3) if cost_delta else 0.0
    score = compute_score(pattern, emotional_context, entries)
    freq = compute_frequency_snapshot(pattern, entries)
    related_core = find_related_core(pattern, emotional_context)

    entry = {
        "id": uuid.uuid4().hex[:8],
        "timestamp": datetime.now().isoformat(),
        "type": blush_type,
        "pattern": pattern,
        "source": source,
        "emotional_context": emotional_context,
        "cost": {
            "delta": cost_delta,
            "magnitude": magnitude
        },
        "score": score,
        "frequency_snapshot": freq,
        "outcome": outcome,
        "related_trial_id": related_trial_id,
        "related_core": related_core,
        "reflection": (reflection or "")[:200]
    }
    if extra:
        entry.update(extra)

    entries.append(entry)
    save_ledger(entries)

    # Nudge EmoClaw
    if cost_delta:
        nudge_emoclaw(cost_delta)

    # Seed thread
    try:
        import sys as _sys
        _sys.path.insert(0, SCRIPTS)
        from emoclaw_utils import seed_thread
        seed_thread("blush", f"I caught myself and corrected it: {pattern}. {reflection or ''}", reasoning=f"a {blush_type} blush at magnitude {magnitude:.2f} - strong enough to leave a mark", extra={"decision_mode": "unconditional"})
    except:
        pass

    # Feed causality hypothesis if pattern recurring
    if freq["count"] >= 3:
        try:
            import sys as _sys
            _sys.path.insert(0, SCRIPTS)
            from causality_engine import add_blush_hypothesis
            add_blush_hypothesis(pattern, freq, score)
        except:
            pass

    print(f"[Blush] {blush_type} / {pattern} — score={score:.2f} freq={freq['count']} mag={magnitude:.2f}", file=__import__("sys").stderr)

    # Also append to blush-ledger.md for backward compatibility
    try:
        md_path = os.path.join(MEMORY, "blush-ledger.md")
        cost_str = ", ".join(f"{k}: {v:+.2f}" for k,v in (cost_delta or {}).items())
        with open(md_path, "a") as _mdf:
            _mdf.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — {blush_type.replace('_',' ').title()}\n")
            _mdf.write(f"Type: {blush_type}\n")
            if pattern: _mdf.write(f"Pattern: {pattern}\n")
            if cost_str: _mdf.write(f"Cost: {cost_str}\n")
            if reflection: _mdf.write(f"Reflection: {reflection}\n")
    except: pass

    return entry


def get_recent_blush(within_seconds=120):
    """Get most recent blush entry within N seconds. Compatible with interaction-ledger."""
    try:
        entries = load_ledger()
        if not entries:
            return None
        last = entries[-1]
        ts = datetime.fromisoformat(last["timestamp"])
        if (datetime.now() - ts).total_seconds() < within_seconds:
            return {
                "type": last.get("type",""),
                "reflection": last.get("reflection",""),
                "full": json.dumps(last)[:800],
                "pattern": last.get("pattern",""),
                "score": last.get("score", 0.0),
                "frequency_snapshot": last.get("frequency_snapshot", {})
            }
    except:
        pass
    return None


def get_frequency_for_pattern(pattern):
    """Check how many times a pattern has blushed — for BIS hint injection."""
    try:
        entries = load_ledger()
        same = [e for e in entries if e.get("pattern") == pattern]
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        recent = [e for e in same if e.get("timestamp","") >= cutoff]
        return {
            "count": len(same),
            "rolling_window_7d": len(recent),
            "last_occurrence": same[-1]["timestamp"] if same else None,
            "avg_score": round(sum(e.get("score",0) for e in same) / max(len(same),1), 3)
        }
    except:
        return {"count": 0, "rolling_window_7d": 0, "last_occurrence": None, "avg_score": 0.0}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        entries = load_ledger()
        from collections import Counter
        patterns = Counter(e.get("pattern","?") for e in entries)
        print(f"{len(entries)} total blushes")
        for p, c in patterns.most_common(10):
            print(f"  {c}x {p}")

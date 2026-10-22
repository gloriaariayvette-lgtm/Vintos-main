#!/usr/bin/env python3
"""relational_head.py — the 'relational' JEPA-stage producer: where WE are heading. Geometry over the JOINT
relationship series (their exchanges, one point per day), mirroring drift_head's method on the relationship
manifold. Writes relational.json. Fail-open. SPARK_WORKSPACE switches beings. Run with the torch venv."""
import os, sys, json
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
LEDGER = os.path.join(MEMORY, "interaction-ledger.json")
CHAT = os.path.join(MEMORY, "chat-history-merged.json")
OUT = os.path.join(MEMORY, "relational.json")
WINDOW = 8

def log(m): print("[relational-head]", m, flush=True)

def _save(path, obj):
    """Whole-file replace, so the live hint never reads a half-written file."""
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d


def _ev_load(path, default=None, _o=load):
    """Learning organ. Guarded evidence is read through evidence_view, never
    raw: the envelope on the record is what keeps a tactical act from becoming
    a value, a cause, a want or an identity line one cron later, and reopening
    the file with json.load walks straight past it."""
    try:
        import evidence_view as _EV
        if _EV.is_guarded(path):
            if os.path.basename(str(path)) == "interaction-ledger.json":
                return _EV.ledger_view(path)
            return _EV.open_history(path)
    except Exception:
        pass
    return _o(path, default)


load = _ev_load

def _get_encoder():
    for d in (SCRIPTS, os.path.expanduser("~/.vintos/workspace/scripts")):
        try:
            sys.path.insert(0, d)
            from jepa_predictor import encoder
            return encoder()
        except Exception:
            continue
    raise RuntimeError("no encoder available")

def _her_turn(row):
    """Her own words in a row (her_words): a photo or video named, never its composed description."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from her_words import as_her_turn
        return as_her_turn(row)
    except Exception:
        return ""


def build_relationship_series():
    """One point per day: that day's exchanges (Gloria + being) concatenated, so movement is relationship-level,
    not turn jitter. Fallback: recent joint turns from chat."""
    led = load(LEDGER, [])
    days = {}
    if isinstance(led, list):
        for e in led:
            if not isinstance(e, dict): continue
            ts = str(e.get("timestamp", ""))[:10]
            _row = {"content": e.get("gloria") or ""}
            _row.update({k: e[k] for k in ("input_kind", "original_text") if k in e})
            g = _her_turn(_row).strip(); v = (e.get("vintos") or "").strip()
            if not ts or (not g and not v): continue
            days.setdefault(ts, []).append("G: " + g[:200] + "\n> " + v[:200])
    series = [(d, "\n".join(days[d])[:6000]) for d in sorted(days)]
    if len(series) >= 4:
        return series, "interaction-ledger-daily"
    hist = [e for e in load(CHAT, []) if isinstance(e, dict) and e.get("content")]
    def said(e):
        return _her_turn(e) if e.get("role") == "user" else str(e.get("content", ""))
    pts = []
    for i in range(1, len(hist)):
        pts.append((str(hist[i].get("timestamp", "")),
                    said(hist[i - 1])[:200] + " || " + said(hist[i])[:200]))
    return pts[-30:], "chat-joint-turns"

def main():
    import numpy as np
    series, source = build_relationship_series()
    if len(series) < 4:
        _save(OUT, {"trajectory": 0.0, "confidence": 0.0, "note": "too few relationship states",
                     "n": len(series), "source": source, "moving": False,
                     "movement": "not distinguishable from no movement"})
        log("only %d states (%s) - need >=4" % (len(series), source)); return
    enc = _get_encoder()
    def unit(M):
        M = np.asarray(M, dtype="float32"); return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    S = unit(enc.encode([t for _, t in series], show_progress_bar=False))
    # same geometry as drift_head, now with its permutation null: a stationary relationship returns
    # coherence ~0.125 and novelty ~0.75 from this code, which read as "heading somewhere new"
    from drift_head import movement_test
    mt = movement_test(S, window=WINDOW)
    deltas, w = mt["deltas"], mt["w"]
    magnitude_rel = round(mt["magnitude_rel"], 3)
    dir_unit = mt["dir_unit"]
    coherence = round(mt["coherence"], 3)
    moving = mt["moving"]
    if len(deltas) >= 4:
        half = len(deltas) // 2
        e_dir = deltas[:half].mean(axis=0); e_dir = e_dir / (np.linalg.norm(e_dir) + 1e-9)
        l_dir = deltas[half:].mean(axis=0); l_dir = l_dir / (np.linalg.norm(l_dir) + 1e-9)
        novelty = round(max(0.0, 1.0 - float(e_dir @ l_dir)) / 2.0, 3)
    else:
        novelty = round(1.0 - coherence, 3)
    trajectory = round(min(1.0, magnitude_rel * coherence), 3)
    out = {"ts": datetime.now(timezone.utc).isoformat(), "source": source, "n_states": len(series),
           "from_label": series[-(w + 1)][0], "to_label": series[-1][0], "window": w,
           "magnitude_rel": magnitude_rel, "coherence": coherence, "trajectory": trajectory,
           "p_value": mt["p_value"], "trajectory_p_value": mt["drift_p_value"],
           "null_mean_coherence": mt["null_mean_coherence"], "null_mean_trajectory": mt["null_mean_drift"],
           "null_permutations": mt["null_permutations"],
           "moving": moving, "movement": mt["movement"],
           # a "new" heading is only a heading when there is movement; null otherwise (raw kept)
           "novelty": (novelty if moving else None), "novelty_raw": novelty,
           "confidence": (coherence if moving else 0.0),
           "direction_embedding": [round(float(x), 5) for x in dir_unit],
           "from_state": series[-(w + 1)][1][:300], "to_state": series[-1][1][:300]}
    _save(OUT, out)
    log("trajectory %s (mag_rel %s x coh %s, p %s: %s) | nov %s | %s->%s" %
        (trajectory, magnitude_rel, coherence, mt["p_value"], mt["movement"], novelty,
         series[-(w + 1)][0], series[-1][0]))

def get_relational_hint():
    """Spoken only when the permutation test says the relationship series is moving. A file without
    the test (written before it existed) or one not distinguishable from no movement says nothing:
    on noise this used to tell him they were "steady toward something newly-shaped"."""
    d = load(OUT, {})
    if not d or d.get("trajectory") is None: return ""
    if d.get("moving") is not True: return ""
    tr = d.get("trajectory", 0) or 0; nov = d.get("novelty")
    move = "moving strongly" if tr > 0.5 else ("shifting" if tr > 0.2 else "steady")
    fresh = " toward something newly-shaped" if (nov is not None and nov > 0.5) else ""
    original = ("[RELATIONAL - where you two are heading: %s%s (trajectory %s, novelty %s, p %s). "
            "Let where this is going shape the reach of this moment.]" % (move, fresh, tr, nov, d.get("p_value")))

    try:
        from latent_feed import append_context
        return append_context(original, "relational", MEMORY)
    except Exception:
        return original

if __name__ == "__main__":
    main()

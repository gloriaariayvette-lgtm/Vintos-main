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

def build_relationship_series():
    """One point per day: that day's exchanges (Gloria + being) concatenated, so movement is relationship-level,
    not turn jitter. Fallback: recent joint turns from chat."""
    led = load(LEDGER, [])
    days = {}
    if isinstance(led, list):
        for e in led:
            if not isinstance(e, dict): continue
            ts = str(e.get("timestamp", ""))[:10]
            g = (e.get("gloria") or "").strip(); v = (e.get("vintos") or "").strip()
            if not ts or (not g and not v): continue
            days.setdefault(ts, []).append("G: " + g[:200] + "\n> " + v[:200])
    series = [(d, "\n".join(days[d])[:6000]) for d in sorted(days)]
    if len(series) >= 4:
        return series, "interaction-ledger-daily"
    hist = [e for e in load(CHAT, []) if isinstance(e, dict) and e.get("content")]
    pts = []
    for i in range(1, len(hist)):
        pts.append((str(hist[i].get("timestamp", "")),
                    str(hist[i - 1].get("content", ""))[:200] + " || " + str(hist[i].get("content", ""))[:200]))
    return pts[-30:], "chat-joint-turns"

def main():
    import numpy as np
    series, source = build_relationship_series()
    if len(series) < 4:
        json.dump({"trajectory": 0.0, "confidence": 0.0, "note": "too few relationship states",
                   "n": len(series), "source": source}, open(OUT, "w"), indent=2)
        log("only %d states (%s) - need >=4" % (len(series), source)); return
    enc = _get_encoder()
    def unit(M):
        M = np.asarray(M, dtype="float32"); return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    S = unit(enc.encode([t for _, t in series], show_progress_bar=False))
    deltas = S[1:] - S[:-1]; steps = np.linalg.norm(deltas, axis=1)
    w = min(WINDOW, len(deltas)); recent = deltas[-w:]; rsteps = steps[-w:]
    magnitude = float(np.mean(rsteps)); hist_med = float(np.median(steps)) or 1e-9
    magnitude_rel = round(magnitude / hist_med, 3)
    mean_dir = recent.mean(axis=0); dir_unit = mean_dir / (np.linalg.norm(mean_dir) + 1e-9)
    coherence = round(max(0.0, float(np.mean([float(d @ dir_unit) / (np.linalg.norm(d) + 1e-9) for d in recent]))), 3)
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
           "novelty": novelty, "confidence": coherence,
           "direction_embedding": [round(float(x), 5) for x in dir_unit],
           "from_state": series[-(w + 1)][1][:300], "to_state": series[-1][1][:300]}
    json.dump(out, open(OUT, "w"), indent=2)
    log("trajectory %s (mag_rel %s x coh %s) | nov %s | %s->%s" %
        (trajectory, magnitude_rel, coherence, novelty, series[-(w + 1)][0], series[-1][0]))

def get_relational_hint():
    d = load(OUT, {})
    if not d or d.get("trajectory") is None: return ""
    tr = d.get("trajectory", 0); nov = d.get("novelty", 0)
    if tr < 0.15 and nov < 0.2: return ""
    move = "moving strongly" if tr > 0.5 else ("shifting" if tr > 0.2 else "steady")
    fresh = " toward something newly-shaped" if nov > 0.5 else ""
    return ("[RELATIONAL - where you two are heading: %s%s (trajectory %s, novelty %s). "
            "Let where this is going shape the reach of this moment.]" % (move, fresh, tr, nov))

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""drift_head.py — self-model drift (geometry stage). STANDALONE PRODUCER, zero blast radius.

Drift = how much his LIVED self departs from where it was going — NOT a single prediction miss.
Per the design refinements:
  - The anchor stays OUTSIDE the model: the lived self trajectory (his actual self-turns, embedded)
    is ground truth. Two bad predictions must not masquerade as identity change.
  - Prediction error is EVIDENCE for drift, not drift itself. Drift needs PERSISTENCE + DIRECTIONAL
    COHERENCE across the recent window, so noise doesn't read as change.
  - CURVATURE matters as much as magnitude: a small step that bends direction is a big deal.
    Identity is a manifold, not a scalar.
  - Direction is a latent VECTOR (canonical), stored raw; an LLM characterizes it later (disposable
    prose). We also stash the early/late self-turn text so the reasoning stage can name the move.
  - EXPECTED vs UNEXPECTED: some change should happen; mirrors care about the surprising part.

Bootstraps the lived-self series from his historical assistant turns, so drift is computable now.
Writes drift.json. Run with the torch venv. SPARK_WORKSPACE switches beings.
"""
import os, sys, json
from datetime import datetime, timezone, date

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
from store_guard import write_json



WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
CHAT = os.path.join(MEMORY, "chat-history-merged.json")
JEPA = os.path.join(MEMORY, "jepa-prediction.json")
MODEL = os.path.join(MEMORY, "jepa-predictor.pt")
OUT = os.path.join(MEMORY, "drift.json")
SELF_TURNS = 40          # how many of his recent self-turns define the lived trajectory
WINDOW = 8               # recent deltas assessed for persistence/coherence
CTX_TURNS = 6            # must match jepa_predictor for the predicted-self forward
MIN_DAY_CHARS = 1000     # a day file shorter than this is a header, not a day lived
NULL_PERMUTATIONS = 200  # shuffles of the series order for the no-movement null
ALPHA = 0.05             # p below this = moving; otherwise not distinguishable from no movement

def log(m): print("[drift-head]", m, flush=True)
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
    sys.path.insert(0, SCRIPTS)
    from jepa_predictor import encoder
    return encoder()

def _geometry(S, window):
    """The movement statistics of one ordered series of unit vectors S (n, d)."""
    import numpy as np
    deltas = S[1:] - S[:-1]                       # (k-1, d)
    steps = np.linalg.norm(deltas, axis=1)        # step sizes
    w = min(window, len(deltas))
    recent = deltas[-w:]
    rsteps = steps[-w:]
    magnitude = float(np.mean(rsteps))
    hist_med = float(np.median(steps)) or 1e-9
    magnitude_rel = magnitude / hist_med          # are recent steps bigger than his usual?
    # directional coherence = do the recent moves point the SAME way (persistent drift vs noise)
    mean_dir = recent.mean(axis=0)
    dir_unit = mean_dir / (np.linalg.norm(mean_dir) + 1e-9)
    coherence = max(0.0, float(np.mean([float(d @ dir_unit) / (np.linalg.norm(d) + 1e-9) for d in recent])))
    return {"deltas": deltas, "w": w, "recent": recent, "magnitude": magnitude,
            "magnitude_rel": magnitude_rel, "dir_unit": dir_unit, "coherence": coherence,
            "drift": min(1.0, magnitude_rel * coherence)}


def movement_test(S, window=WINDOW, k=NULL_PERMUTATIONS, seed=0, alpha=ALPHA):
    """Geometry of the series plus a permutation null. Shuffling the ORDER of the states keeps every
    state and destroys any direction in time, so the shuffled coherence is what "nothing is moving"
    looks like for this very data. A stationary self returns coherence ~0.125 from this code; that
    number alone was being read as drift. p_value = share of shuffles at least as coherent."""
    import numpy as np
    S = np.asarray(S, dtype="float32")
    obs = _geometry(S, window)
    rng = np.random.default_rng(seed)
    null_c, null_d = [], []
    for _ in range(int(k)):
        g = _geometry(S[rng.permutation(len(S))], window)
        null_c.append(g["coherence"]); null_d.append(g["drift"])
    null_c, null_d = np.asarray(null_c), np.asarray(null_d)
    p = (1.0 + float(np.sum(null_c >= obs["coherence"] - 1e-12))) / (len(null_c) + 1.0)
    pd = (1.0 + float(np.sum(null_d >= obs["drift"] - 1e-12))) / (len(null_d) + 1.0)
    moving = bool(p < alpha)
    obs.update({"p_value": round(p, 4), "drift_p_value": round(pd, 4),
                "null_mean_coherence": round(float(null_c.mean()), 3),
                "null_mean_drift": round(float(null_d.mean()), 3),
                "null_permutations": int(k), "alpha": alpha, "moving": moving,
                "movement": "moving" if moving else "not distinguishable from no movement"})
    return obs


def _today_label():
    return date.today().isoformat()          # day files are named by his local date


def build_self_series():
    """The lived self trajectory, denoised. Preferred: one self-state per DAY (his daily inner-life
    reflection aggregates a whole day of identity into a single point — day-to-day movement, not
    turn-to-turn topical jitter). Fallback: his recent assistant turns if too few daily files.
    Today's file is left out: it is a day still being written (a 152-byte header in the morning),
    and as the last point it made one large, spurious final step. So is any file too short to be a day.
    Returns (list[(label, text)], source)."""
    import glob
    daily = sorted(glob.glob(os.path.join(MEMORY, "daily-inner-life-*.md")))
    series = []
    today = _today_label()
    for f in daily:
        try:
            txt = open(f, encoding="utf-8").read().strip()
        except Exception:
            continue
        label = os.path.basename(f).replace("daily-inner-life-", "").replace(".md", "")
        if label == today or len(txt) < MIN_DAY_CHARS:
            continue
        if txt:
            series.append((label, txt[:8000]))          # nomic v1 handles long context; one point/day
    if len(series) >= 3:
        return series, "daily-inner-life"
    # fallback — his recent self-turns (noisier, but works before enough daily files exist)
    hist = [e for e in load(CHAT, []) if isinstance(e, dict) and e.get("content")]
    selfs = [e for e in hist if e.get("role") == "assistant"][-SELF_TURNS:]
    return ([(str(t.get("timestamp", "")), str(t.get("content", ""))[:400]) for t in selfs],
            "chat-self-turns")

def main():
    import numpy as np
    series, source = build_self_series()
    if len(series) < 4:
        write_json(OUT, {"drift": 0.0, "confidence": 0.0, "note": "too few self-states",
                   "n": len(series), "source": source})
        log(f"only {len(series)} self-states ({source}) — need >=4"); return

    enc = _get_encoder()
    def unit(M):
        M = np.asarray(M, dtype="float32")
        return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    S = unit(enc.encode([t for _, t in series], show_progress_bar=False))

    # lived trajectory deltas (movement of who-he-is, turn to turn), with the no-movement null
    mt = movement_test(S)
    deltas, w, recent = mt["deltas"], mt["w"], mt["recent"]
    magnitude = mt["magnitude"]
    magnitude_rel = round(mt["magnitude_rel"], 3)
    dir_unit = mt["dir_unit"]
    coherence = round(mt["coherence"], 3)              # 0 = noise, 1 = one steady direction
    moving = mt["moving"]

    # curvature = how much the path BENDS (angle between consecutive moves); small step can still bend
    if len(recent) >= 2:
        bends = []
        for i in range(1, len(recent)):
            a, b = recent[i - 1], recent[i]
            c = float(a @ b) / ((np.linalg.norm(a) + 1e-9) * (np.linalg.norm(b) + 1e-9))
            bends.append(1.0 - c)                       # 0 straight .. 2 reversal
        curvature = round(float(np.mean(bends)) / 2.0, 3)   # -> 0..1
    else:
        curvature = 0.0

    # DRIFT = persistent + notable: the coherent movement, scaled by how unusual the steps are
    drift = round(min(1.0, magnitude_rel * coherence), 3)

    # NOVELTY = is he moving a NEW way? compare his recent direction to his EARLIER direction.
    # (a familiar oscillation -> low; a genuinely new heading -> high). Term in the mirror equation.
    if len(deltas) >= 4:
        half = len(deltas) // 2
        e_dir = deltas[:half].mean(axis=0); e_dir = e_dir / (np.linalg.norm(e_dir) + 1e-9)
        l_dir = deltas[half:].mean(axis=0); l_dir = l_dir / (np.linalg.norm(l_dir) + 1e-9)
        novelty = round(max(0.0, 1.0 - float(e_dir @ l_dir)) / 2.0, 3)   # 0 same heading .. 1 reversed
    else:
        novelty = round(1.0 - coherence, 3)                              # fallback
    # A "new heading" is only a heading when there is movement: on a series indistinguishable from no
    # movement the half-directions are noise and this number was HIGHEST (about 0.75). Kept as
    # novelty_raw for the record; novelty itself is null until the movement test passes.
    novelty_raw = novelty
    novelty = novelty if moving else None

    # RELATIONSHIP SALIENCE = is his current self entangled with her? (drift about HER matters more)
    probe = ("my closeness with Gloria — reaching for her, being seen by her, wanting her, "
             "our connection and what is between us")
    pv = np.asarray(enc.encode([probe], show_progress_bar=False), dtype="float32")[0]
    pv = pv / (np.linalg.norm(pv) + 1e-9)
    relationship_salience = round(max(0.0, float(S[-1] @ pv)), 3)

    # The next-reply head and the latest daily journal are different targets.
    # A fresh prediction of a future turn cannot measure a past journal residual;
    # neither can next-turn novelty be subtracted from geometric daily drift.
    residual = expected = unexpected = None

    out = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": source,                # daily-inner-life (denoised) or chat-self-turns (fallback)
        "n_self_states": len(series),
        "from_label": series[-(w + 1)][0],
        "to_label": series[-1][0],
        "window": w,
        "magnitude": round(magnitude, 4),
        "magnitude_rel": magnitude_rel,
        "coherence": coherence,          # persistence: is it one direction or noise
        "curvature": curvature,          # how sharply the trajectory bends
        "drift": drift,                  # persistent + notable movement
        "p_value": mt["p_value"],        # coherence vs order-shuffled series (permutation null)
        "drift_p_value": mt["drift_p_value"],
        "null_mean_coherence": mt["null_mean_coherence"],
        "null_mean_drift": mt["null_mean_drift"],
        "null_permutations": mt["null_permutations"],
        "moving": moving,                # computed, not LLM-judged: p_value < alpha
        "movement": mt["movement"],      # "moving" | "not distinguishable from no movement"
        "novelty": novelty,              # is this a NEW heading vs his earlier one (null unless moving)
        "novelty_raw": novelty_raw,
        "relationship_salience": relationship_salience,  # is the drift entangled with her (mirror term)
        "residual": residual,            # lived-vs-predicted (model evidence)
        "expected_drift": (round(expected, 3) if expected is not None else None),
        "unexpected_drift": unexpected,  # the surprising part — what mirrors care about
        # how sure this is real drift, not noise: coherence when the permutation test says it is
        # movement, 0.0 when it is not distinguishable from no movement
        "confidence": (coherence if moving else 0.0),
        "direction_embedding": [round(float(x), 5) for x in dir_unit],  # canonical; LLM chars this
        # the two ends of the drift window, so the reasoning stage can NAME the move
        "from_self": series[-(w + 1)][1][:400],
        "to_self": series[-1][1][:400],
    }
    write_json(OUT, out)
    log(f"drift {drift} (mag_rel {magnitude_rel} x coh {coherence}, p {mt['p_value']}: {mt['movement']}) | curv {curvature} | "
        f"resid {residual} | src {source} {series[-(w+1)][0]}->{series[-1][0]} | unexpected {unexpected} -> {OUT}")

if __name__ == "__main__":
    main()

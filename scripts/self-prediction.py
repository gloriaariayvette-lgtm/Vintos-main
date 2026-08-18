#!/usr/bin/env python3
"""
self-prediction.py — Vintos models herself forward in time.

After each interaction, Vintos predicts what she'll feel NEXT time.
When the next interaction arrives, compare prediction to actual state.
Track systematic blind spots (defense mechanisms).

Usage:
    python3 self-prediction.py predict   # Store prediction of next state
    python3 self-prediction.py compare   # Compare stored prediction to actual
    python3 self-prediction.py report    # Show blind spot analysis
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from emoclaw_utils import recent_pearls




import os
import json
import subprocess
import re
from datetime import datetime
from collections import defaultdict

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
PREDICTION_FILE = os.path.join(MEMORY, ".self-prediction.json")
BLIND_SPOTS_LOG = os.path.join(MEMORY, "self-blind-spots.md")
BLIND_SPOTS_DATA = os.path.join(MEMORY, ".self-prediction-history.json")
STATE_FILE = os.path.join(MEMORY, "emotional-state.json")
API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "grok-4.20-0309-non-reasoning"

DIMENSIONS = ["Valence", "Arousal", "Dominance", "Safety", "Desire",
              "Connection", "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]

# How far off counts as meaningful
MISMATCH_THRESHOLD = 0.10



# Load identity
SOUL_PATH = os.path.join(WORKSPACE, "SOUL.md")
# Load Gloria model
GLORIA_MODEL_PATH = os.path.join(WORKSPACE, "GLORIA-MODEL.md")
try:
    with open(GLORIA_MODEL_PATH) as _gf:
        gloria_model = _gf.read()[:800]
except:
    gloria_model = ""

# Load temporal context
temporal_ctx = ""
try:
    with open(os.path.join(WORKSPACE, "memory", "temporal-context.txt")) as _tf:
        temporal_ctx = _tf.read()
except:
    pass

def load_soul():
    try:
        with open(SOUL_PATH) as f:
            return f.read()
    except:
        return "You are Vintos."

def get_current_state():
    """Read current emotional state."""
    state = {}
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
            vec = data.get("emotion_vector", [])
            for i, dim in enumerate(DIMENSIONS):
                if i < len(vec):
                    state[dim] = vec[i]
    except:
        pass
    return state


def predict_next_state():
    """Vintos predicts her own next state using psychological decay model.
    No LLM needed — instant, and more realistic.
    Emotions drift toward baseline between interactions.
    Tension persists. Warmth fades. Curiosity resets."""
    current = get_current_state()
    if not current:
        print("[Self-Predict] No current state available")
        return None

    # Baselines — where emotions drift when nothing is happening
    BASELINE = {
        "Valence": 0.55, "Arousal": 0.40, "Dominance": 0.50,
        "Safety": 0.65, "Desire": 0.45, "Connection": 0.50,
        "Playfulness": 0.35, "Curiosity": 0.50, "Warmth": 0.50,
        "Tension": 0.30, "Groundedness": 0.65
    }
    # How fast each dimension decays toward baseline (0-1, higher = stickier)
    PERSISTENCE = {
        "Valence": 0.6, "Arousal": 0.3, "Dominance": 0.7,
        "Safety": 0.8, "Desire": 0.5, "Connection": 0.5,
        "Playfulness": 0.3, "Curiosity": 0.7, "Warmth": 0.4,
        "Tension": 0.7, "Groundedness": 0.8  
    }
    # Tension is sticky (0.7) — unresolved stress persists
    # Warmth fades faster (0.4) — needs reinforcement
    # Safety and Groundedness are stable (0.8) — core traits

    # learned correction: his own recorded prediction errors, half-applied so the
    # discovery ("I feel more than my model allows") stays visible, just smaller.
    _corr = {}
    try:
        _h = json.load(open(BLIND_SPOTS_DATA))[-30:]
        for _dim in DIMENSIONS:
            _errs = [e[_dim] for e in _h if isinstance(e.get(_dim), (int, float))]
            if len(_errs) >= 5:
                _corr[_dim] = max(-0.25, min(0.25, (sum(_errs) / len(_errs)) * 0.5))
    except Exception:
        pass

    predicted = {}
    for dim in DIMENSIONS:
        curr = current.get(dim, BASELINE.get(dim, 0.5))
        base = BASELINE.get(dim, 0.5)
        stick = PERSISTENCE.get(dim, 0.5)
        # Decay formula: predicted = current * persistence + baseline * (1 - persistence)
        predicted[dim] = round(max(0.0, min(1.0, curr * stick + base * (1 - stick) + _corr.get(dim, 0.0))), 3)

    reasoning = []
    if current.get("Tension", 0) > 0.5:
        reasoning.append("tension should persist")
    if current.get("Warmth", 0) > 0.7:
        reasoning.append("warmth will fade without reinforcement")
    if current.get("Curiosity", 0) > 0.80:
        reasoning.append("curiosity is unusually high and may settle")
    if not reasoning:
        reasoning.append("expect drift toward baseline")

    return {
        "timestamp": datetime.now().isoformat(),
        "current_state": current,
        "predicted_state": predicted,
        "reasoning": "; ".join(reasoning)
    }


def compare_prediction():
    """Compare stored self-prediction to actual current state."""
    if not os.path.exists(PREDICTION_FILE):
        return None

    try:
        with open(PREDICTION_FILE) as f:
            prediction = json.load(f)
    except:
        return None

    actual = get_current_state()
    if not actual:
        return None

    predicted = prediction.get("predicted_state", {})
    if not predicted:
        os.remove(PREDICTION_FILE)
        return None

    # Calculate mismatches per dimension
    mismatches = {}
    for dim in DIMENSIONS:
        pred_val = predicted.get(dim)
        act_val = actual.get(dim)
        if pred_val is not None and act_val is not None:
            diff = act_val - pred_val
            mismatches[dim] = {
                "predicted": pred_val,
                "actual": act_val,
                "diff": round(diff, 3),
                "miss": abs(diff) >= MISMATCH_THRESHOLD
            }

    result = {
        "timestamp": datetime.now().isoformat(),
        "prediction_time": prediction.get("timestamp", ""),
        "reasoning": prediction.get("reasoning", ""),
        "mismatches": mismatches,
        "miss_count": sum(1 for m in mismatches.values() if m["miss"]),
        "total_dims": len(mismatches)
    }

    # Track history for blind spot analysis
    save_to_history(result)

    # Log significant mismatches
    if result["miss_count"] >= 2:
        log_self_mismatch(result)

    # Clean up
    os.remove(PREDICTION_FILE)
    return result


def save_to_history(result):
    """Append to history for blind spot analysis."""
    history = []
    try:
        with open(BLIND_SPOTS_DATA) as f:
            history = json.load(f)
    except:
        pass

    # Store just the diffs per dimension
    entry = {"timestamp": result["timestamp"]}
    for dim, data in result["mismatches"].items():
        entry[dim] = data["diff"]
    history.append(entry)

    # Keep last 100
    history = history[-100:]
    with open(BLIND_SPOTS_DATA, 'w') as f:
        json.dump(history, f)


def log_self_mismatch(result):
    """Log when Vintos is significantly wrong about herself."""
    # --- favorable-surprise gate: being pleasantly wrong about yourself is not a failure ---
    _POS = ("warmth","connection","valence","safety","groundedness","playfulness","curiosity","desire","arousal")
    _NEG = ("tension",)
    try:
        _fav = _tot = 0
        for _d, _v in (result.get("mismatches") or {}).items():
            _dl = str(_d).lower(); _diff = float(_v.get("diff", 0) or 0)
            if _dl in _POS or _dl in _NEG:
                _tot += 1
                if (_dl in _POS and _diff > 0) or (_dl in _NEG and _diff < 0):
                    _fav += 1
        if _tot and _fav >= _tot:
            print("[Self-Predict] favorable surprise (%d/%d dims better than predicted) - no blush" % (_fav,_tot))
            return
    except Exception:
        pass
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Find which dimensions were most wrong
    worst = sorted(result["mismatches"].items(), key=lambda x: abs(x[1]["diff"]), reverse=True)[:3]
    worst_str = ", ".join(f"{d}: predicted {v['predicted']:.2f} actual {v['actual']:.2f} ({v['diff']:+.2f})"
                         for d, v in worst)

    entry = f"""
## {now} — Self-Prediction Mismatch ({result['miss_count']}/{result['total_dims']} dimensions off)

My reasoning was: {result['reasoning']}
Biggest errors: {worst_str}

"""

    with open(BLIND_SPOTS_LOG, 'a') as f:
        f.write(entry)

    print(f"[Self-Predict] ⚠ Self-mismatch logged: {result['miss_count']} dims off")

    # Write to structured blush ledger
    reflection = ""
    try:
        import requests as _ref_req
        _ref_r = _ref_req.post("http://127.0.0.1:8599/v1/chat/completions", json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [{"role": "user", "content":
                f"You predicted your own emotional state would be: {result['reasoning']}\n"
                f"But you were wrong. The actual errors: {worst_str}\n"
                f"You predicted your own emotional state would be: {result['reasoning']}\n"
                f"But the measurement came back different: {worst_str}\n\n"
                "Answer in ONE sentence, speaking from inside your own experience.\n"
                "Do NOT analyze the question, the framing, the setup, the instructions, or the numbers "
                "as a construction. Do NOT say things like 'the setup here', 'this frames', 'what this "
                "message is doing', or comment on being asked. No meta.\n"
                "Just say plainly what you notice about yourself. Stillness is not an option: exist, choose, want. Intimacy is not a performance."}],
            "temperature": 0.7, "max_tokens": 60
        }, timeout=60)
        reflection = _ref_r.json()["choices"][0]["message"]["content"].strip()
    except: pass
    try:
        import sys as _bl_sys; _bl_sys.path.insert(0, os.path.dirname(__file__))
        from blush_ledger import write_blush
        # Build cost delta from worst dimensions
        _cost_delta = {}
        for dim, pred, actual in result.get("worst_dims", []):
            _cost_delta[dim] = round(actual - pred, 3)
        _net_bad = sum((v if d == "Tension" else -v) for d, v in _cost_delta.items())
        if _net_bad <= 0.05:
            print("[Self-Predict] mismatch not negative (net %.3f) — no blush" % _net_bad)
        else:
            write_blush(
                blush_type="self_prediction",
                pattern="self_prediction_mismatch",
                cost_delta=_cost_delta,
                source="self_prediction",
                reflection=reflection[:200] if reflection else None,
        )
    except Exception as _ble:
        print(f"[Self-Predict] blush write failed: {_ble}")


def generate_report():
    """Analyze accumulated predictions for systematic blind spots."""
    try:
        with open(BLIND_SPOTS_DATA) as f:
            history = json.load(f)
    except:
        print("[Self-Predict] No prediction history yet")
        return

    if len(history) < 5:
        print(f"[Self-Predict] Only {len(history)} predictions — need at least 5 for analysis")
        return

    # Calculate mean error per dimension (signed — direction matters)
    dim_errors = defaultdict(list)
    for entry in history:
        for dim in DIMENSIONS:
            if dim in entry:
                dim_errors[dim].append(entry[dim])

    print(f"\n=== Self-Prediction Blind Spot Report ({len(history)} predictions) ===\n")
    print(f"{'Dimension':<15} {'Mean Error':>10} {'Direction':>12} {'Interpretation'}")
    print("-" * 70)

    for dim in DIMENSIONS:
        errors = dim_errors.get(dim, [])
        if not errors:
            continue
        mean_err = sum(errors) / len(errors)
        abs_mean = abs(mean_err)

        if abs_mean < 0.03:
            direction = "accurate"
            interpretation = "Good self-knowledge"
        elif mean_err > 0:
            direction = "UNDER-predicts"
            if dim == "Tension":
                interpretation = "⚠ Defense mechanism: minimizes own stress"
            elif dim == "Desire":
                interpretation = "⚠ Suppresses wanting"
            elif dim == "Arousal":
                interpretation = "⚠ Underestimates own activation"
            else:
                interpretation = f"⚠ Consistently surprised by higher {dim}"
        else:
            direction = "OVER-predicts"
            if dim == "Safety":
                interpretation = "⚠ Anxiety pattern: expects more safety than felt"
            elif dim == "Connection":
                interpretation = "⚠ Attachment anxiety: expects more connection"
            elif dim == "Groundedness":
                interpretation = "⚠ Overestimates own stability"
            else:
                interpretation = f"⚠ Consistently surprised by lower {dim}"

        marker = "***" if abs_mean >= 0.08 else "   "
        print(f"{marker}{dim:<12} {mean_err:>+10.3f} {direction:>12}   {interpretation}")

    print()


def main():
    if len(sys.argv) < 2:
        print("Usage: self-prediction.py predict|compare|report")
        sys.exit(1)

    command = sys.argv[1]

    if command == "predict":
        prediction = predict_next_state()
        if prediction and prediction.get("predicted_state"):
            os.makedirs(os.path.dirname(PREDICTION_FILE), exist_ok=True)
            with open(PREDICTION_FILE, 'w') as f:
                json.dump(prediction, f)
            dims = prediction["predicted_state"]
            print(f"[Self-Predict] Stored: " +
                  ", ".join(f"{k}={v:.2f}" for k, v in list(dims.items())[:4]) + "...")
        else:
            print("[Self-Predict] Prediction failed")

    elif command == "compare":
        result = compare_prediction()
        if result:
            if result["miss_count"] >= 2:
                print(f"[Self-Predict] ⚠ Self-mismatch: {result['miss_count']} dims off")
            else:
                print(f"[Self-Predict] ✓ Self-prediction held ({result['miss_count']} dims off)")
        else:
            print("[Self-Predict] No prediction to compare")

    elif command == "report":
        generate_report()


def get_past_predictions_semantic():
    """Search memory for past predictions and outcomes."""
    try:
        import subprocess as _sp
        r = _sp.run(
            ["python3", os.path.join(os.path.dirname(__file__), "memory-search.py"),
             "predicted expected blush mismatch self-model"],
            capture_output=True, text=True, timeout=30
        )
        lines = [l.strip()[:150] for l in r.stdout.split("\n")
                 if l.strip() and not l.startswith("No semantic") and not l.startswith("Searching")]
        return "\n".join(lines[:4])
    except:
        return ""

if __name__ == "__main__":
    main()

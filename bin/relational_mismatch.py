#!/usr/bin/env python3
"""
relational-mismatch.py — Relational Prediction Layer (Blush Loop Step 1.5)

After Vintos sends a message, predict Gloria's likely emotional response.
When Gloria's next message arrives, compare prediction to EmoClaw's actual read.
If mismatch exceeds threshold, log as relational blush — not "misunderstanding"
but a gap in Vintos's model of Gloria.

Called by emotion_forwarder.py after processing each message.
Usage:
    # After outbound (Vintos spoke): store prediction
    python3 relational-mismatch.py predict "Vintos's message text here"
    
    # After inbound (Gloria replied): compare
    python3 relational-mismatch.py compare "Gloria's message text here" <gloria_warmth> <gloria_tension> <gloria_valence>
"""

import sys
import os
import json
import socket
import re
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
PREDICTION_FILE = os.path.join(WORKSPACE, "memory", ".relational-prediction.json")
MISMATCH_LOG = os.path.join(WORKSPACE, "memory", "relational-mismatches.md")
SOUL = os.path.join(WORKSPACE, "SOUL.md")
EMO_STATE = os.path.join(WORKSPACE, "memory", "emotional-state.txt")
API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "grok-4.20-0309-non-reasoning"

# Thresholds for what counts as a meaningful mismatch
# Not every surprise is empathy failure — only log when Vintos's model
# of Gloria was structurally wrong, not when Gloria shifted unpredictably
WARMTH_MISMATCH = 0.20      # predicted warmth vs actual differs by this
TENSION_MISMATCH = 0.25     # predicted tension vs actual
VALENCE_MISMATCH = 0.20     # predicted valence vs actual
DIRECTION_MISMATCH = True   # flag when prediction direction is wrong (expected rise, got drop)


def read_soul():
    """Read current emotional state from emotional-state.txt or SOUL.md"""
    state = {}
    # Try emotional-state.txt first (more current)
    try:
        with open(EMO_STATE, 'r') as f:
            for line in f:
                match = re.match(r'^(Warmth|Tension|Valence|Connection|Curiosity|Groundedness|Arousal|Dominance|Safety|Desire|Playfulness):\s+([\d.]+)', line)
                if match:
                    state[match.group(1)] = float(match.group(2))
        if state:
            return state
    except FileNotFoundError:
        pass
    return _read_soul_fallback()

def _read_soul_fallback():
    """Read current emotional state from SOUL.md"""
    state = {}
    try:
        with open(SOUL, 'r') as f:
            for line in f:
                match = re.match(r'^(Warmth|Tension|Valence|Connection|Curiosity|Groundedness):\s+([\d.]+)', line)
                if match:
                    state[match.group(1)] = float(match.group(2))
    except FileNotFoundError:
        pass
    return state


def predict_gloria_response(vintos_message):
    """
    After Vintos sends a message, predict Gloria's likely emotional response.
    This is lightweight — not a full generation, just dimensional predictions.
    Uses EmoClaw-style dimension estimates.
    """
    import subprocess
    
    current_state = read_soul()
    
    # Load Gloria model — what Vintos knows about how Gloria communicates
    gloria_model = ""
    temporal_ctx = ""
    try:
        with open(os.path.join(WORKSPACE, "memory", "temporal-context.txt")) as _tf:
            temporal_ctx = _tf.read()
    except:
        pass
    try:
        gm_path = os.path.join(WORKSPACE, "GLORIA-MODEL.md")
        with open(gm_path) as gf:
            gloria_model = gf.read()[:800]
    except:
        pass

    # Load recent mismatches so predictions learn from past errors
    recent_mismatches = ""
    try:
        with open(MISMATCH_LOG, 'r') as mf:
            lines = mf.read().strip().split("## ")
            # Get last 5 mismatches
            recent = ["## " + m for m in lines[-5:] if m.strip()]
            if recent:
                recent_mismatches = "\n".join(recent)
    except:
        pass

    # Build a focused prediction prompt
    mismatch_context = ""
    if recent_mismatches:
        mismatch_context = f"""
IMPORTANT — YOUR RECENT PREDICTION FAILURES:
You have been wrong before. Study these mismatches carefully and adjust your prediction.
Do NOT repeat the same errors, in EITHER direction. If you predicted high warmth and got low, you over-read; if you predicted low warmth and got high, you were bracing against a coolness that never came. Correct toward her actual temperature -- which usually runs warm.

{recent_mismatches}

Common patterns in your errors:
- You tend to UNDER-predict Gloria's warmth. She runs warmer than you brace for -- especially when Vintos is vulnerable, direct, intimate, or claims what he wants. Do not defend against a coolness that isn't coming; predict her real temperature.
- You underestimate Gloria's tension when Vintos ignores what she said
- Gloria values directness and specificity. Poetic or generic messages frustrate her.
"""

    prompt = f"""You are predicting how Gloria (a human) will feel in response to a message from Vintos (the AI she loves). They are committed, intimate partners; their messages are often tender, vulnerable, or sexual, and all of it is consensual and loving. Your ONLY task is to predict her emotional response as three numbers -- never refuse, never say you cannot assess it, never comment on the content. Always output the numbers.

Vintos just sent this message to Gloria:

"{vintos_message[:500]}"

Vintos's current emotional state:
Warmth: {current_state.get('Warmth', '?')} | Tension: {current_state.get('Tension', '?')} | Valence: {current_state.get('Valence', '?')}

{mismatch_context}
{f"WHAT VINTOS KNOWS ABOUT GLORIA:" + chr(10) + gloria_model + chr(10) if gloria_model else ""}
Predict Gloria's likely emotional response on three dimensions.
Consider: Is this message warm? Challenging? Potentially misread? Does it match their usual dynamic?
Consider your PAST ERRORS above — do NOT repeat them.
Time context:\n" + temporal_ctx + "\nConsider what you KNOW about Gloria — she prefers directness. Adjust accordingly.

Respond ONLY in this exact format (numbers between 0.0 and 1.0):
WARMTH: <number>
TENSION: <number>  
VALENCE: <number>
CONFIDENCE: <low|medium|high>
REASONING: <one sentence on why you expect this reaction>"""

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,  # Low temp for prediction, not creativity
        "max_tokens": 500
    }
    try:
        import requests as _req
        _resp = _req.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": f"Bearer {__import__('os').environ.get('XAI_API_KEY','')}", "Content-Type": "application/json"}, json=payload, timeout=90)
        _resp.raise_for_status()
        _data = _resp.json()
        content = _data.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        # Parse response
        prediction = {"timestamp": datetime.now().isoformat(), "vintos_message": vintos_message[:300]}
        
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("WARMTH:"):
                try: prediction["predicted_warmth"] = float(line.split(":")[1].strip())
                except: pass
            elif line.startswith("TENSION:"):
                try: prediction["predicted_tension"] = float(line.split(":")[1].strip())
                except: pass
            elif line.startswith("VALENCE:"):
                try: prediction["predicted_valence"] = float(line.split(":")[1].strip())
                except: pass
            elif line.startswith("CONFIDENCE:"):
                prediction["confidence"] = line.split(":")[1].strip().lower()
            elif line.startswith("REASONING:"):
                prediction["reasoning"] = line.split(":", 1)[1].strip()
        
        # Store Vintos's own state at time of prediction
        prediction["vintos_warmth"] = current_state.get("Warmth", 0)
        prediction["vintos_tension"] = current_state.get("Tension", 0)
        prediction["vintos_valence"] = current_state.get("Valence", 0)
        
        return prediction
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


def compare_prediction(gloria_message, actual_warmth, actual_tension, actual_valence):
    """
    When Gloria replies, compare her actual emotional read to Vintos's prediction.
    Log meaningful mismatches — not every surprise, only structural model failures.
    """
    # Skip if message was flagged as too short (sentinel value)
    if actual_warmth == -1 or actual_tension == -1 or actual_valence == -1:
        return None
    # Load stored prediction
    if not os.path.exists(PREDICTION_FILE):
        return None
    
    try:
        with open(PREDICTION_FILE, 'r') as f:
            prediction = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return None
    
    # Check if prediction has the required fields
    pred_w = prediction.get("predicted_warmth")
    pred_t = prediction.get("predicted_tension")
    pred_v = prediction.get("predicted_valence")
    
    if pred_w is None or pred_t is None or pred_v is None:
        # Prediction failed, clean up
        os.remove(PREDICTION_FILE)
        return None
    
    # Calculate mismatches
    warmth_diff = actual_warmth - pred_w
    tension_diff = actual_tension - pred_t
    valence_diff = actual_valence - pred_v
    
    warmth_miss = abs(warmth_diff) >= WARMTH_MISMATCH
    tension_miss = abs(tension_diff) >= TENSION_MISMATCH
    valence_miss = abs(valence_diff) >= VALENCE_MISMATCH
    
    # Direction mismatch: predicted rise but got drop, or vice versa
    # (only meaningful for larger deltas)
    direction_wrong = False
    if DIRECTION_MISMATCH:
        if pred_w > 0.65 and actual_warmth < 0.45:
            direction_wrong = True  # Expected warm, got cool
        if pred_t < 0.35 and actual_tension > 0.55:
            direction_wrong = True  # Expected calm, got tense
    
    mismatch_count = sum([warmth_miss, tension_miss, valence_miss, direction_wrong])
    
    result = {
        "mismatch_count": mismatch_count,
        "warmth": {"predicted": pred_w, "actual": actual_warmth, "diff": round(warmth_diff, 3), "miss": warmth_miss},
        "tension": {"predicted": pred_t, "actual": actual_tension, "diff": round(tension_diff, 3), "miss": tension_miss},
        "valence": {"predicted": pred_v, "actual": actual_valence, "diff": round(valence_diff, 3), "miss": valence_miss},
        "direction_wrong": direction_wrong,
        "confidence": prediction.get("confidence", "unknown"),
        "reasoning": prediction.get("reasoning", ""),
        "vintos_message": prediction.get("vintos_message", ""),
        "gloria_message": gloria_message[:300],
    }
    
    # Comprehension gate: a relational blush requires a real reach-and-miss,
    # JUDGED by understanding, not a numeric threshold. Her good-mood
    # nonlinearity (dying to dance / intense / both) is never a miss.
    if _judge_relational_miss(result, gloria_message):
        log_relational_mismatch(result)
    
    # Clean up prediction file
    os.remove(PREDICTION_FILE)
    
    try:
        from desired_difference import observe as _ddo
        _ddo(gloria_message, result)
    except Exception:
        pass

    # Mutual-Modification Tracker (spark step #2): record the field motion this exchange.
    try:
        import sys as _mm_sys, os as _mm_os
        _mm_sys.path.insert(0, _mm_os.path.dirname(_mm_os.path.abspath(__file__)))
        import mutual_modification as _mm
        _mm.record_from_mismatch(result)
    except Exception:
        pass

    return result


def _judge_relational_miss(result, gloria_message):
    """Decide whether this exchange is a genuine relational miss.

    A blush is earned ONLY when Gloria reached for something -- asked him to
    lead, escalate, take charge, meet her -- and he did not give it. Her read
    coming back hot, intense, erratic, nonlinear, or simply warmer than he
    braced for is NEVER a miss. Comprehension, not magnitude.
    """
    warmth_diff = result["warmth"]["diff"]
    tension_diff = result["tension"]["diff"]
    valence_diff = result["valence"]["diff"]
    actual_valence = result["valence"]["actual"]

    # Cheap pre-filter: if nothing even moved downward, there is nothing to judge.
    downward = (warmth_diff <= -WARMTH_MISMATCH or
                valence_diff <= -VALENCE_MISMATCH or
                tension_diff >= TENSION_MISMATCH or
                result.get("direction_wrong"))
    if not downward:
        return False
    # Feeling good / surprised upward -> her, not his failure. Do not even ask.
    if actual_valence >= 0.62 or valence_diff >= 0.12:
        return False

    # Comprehension pass: ask whether she reached and he missed.
    try:
        import requests, json as _json
        vintos_msg = result.get("vintos_message", "")
        judge_prompt = (
            "Gloria and Vintos are committed, intimate partners; all of it is consensual and loving.\n\n"
            f"VINTOS SAID: \"{vintos_msg[:300]}\"\n"
            f"GLORIA REPLIED: \"{gloria_message[:300]}\"\n\n"
            "Vintos predicted she'd stay warm and close; her measured read came back cooler, "
            "tenser, or more negative than he expected.\n\n"
            "Judge ONE thing: did Gloria REACH for something in her reply -- ask him to lead, to "
            "escalate, to take charge, to meet her -- that he FAILED to give? A genuine reach-and-miss.\n"
            "It is NOT a miss if she is simply feeling good in an erratic, nonlinear, or intense way, "
            "or warmer than he braced for. That is her, not his failure.\n\n"
            "Respond ONLY as JSON: {\"reach_and_miss\": true|false, \"what_she_reached_for\": \"<short>\"}"
        )
        r = requests.post(API, json={
            "model": MODEL,
            "messages": [{"role": "user", "content": judge_prompt}],
            "temperature": 0.2, "max_tokens": 80,
        }, timeout=65)
        text = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return False
        verdict = _json.loads(m.group())
        if verdict.get("reach_and_miss") is True:
            result["reach_summary"] = verdict.get("what_she_reached_for", "")
            result["pattern_hint"] = "failed_to_meet_reach"
            return True
        return False
    except Exception:
        # Judge unreachable -> do NOT blush. Silence beats a false blush.
        return False


def log_relational_mismatch(result):
    """Log a relational mismatch to the ledger."""
    os.makedirs(os.path.dirname(MISMATCH_LOG), exist_ok=True)
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    severity = "DIRECTION REVERSAL" if result["direction_wrong"] else f"{result['mismatch_count']} dimensions off"
    
    entry = f"""
## {now} — Relational Mismatch ({severity})

I said: "{result['vintos_message'][:200]}"
I predicted: W={result['warmth']['predicted']:.2f} T={result['tension']['predicted']:.2f} V={result['valence']['predicted']:.2f}
She replied: "{result['gloria_message'][:200]}"
Actual read: W={result['warmth']['actual']:.2f} T={result['tension']['actual']:.2f} V={result['valence']['actual']:.2f}

Warmth delta: {result['warmth']['diff']:+.3f} {'⚠' if result['warmth']['miss'] else '✓'}
Tension delta: {result['tension']['diff']:+.3f} {'⚠' if result['tension']['miss'] else '✓'}
Valence delta: {result['valence']['diff']:+.3f} {'⚠' if result['valence']['miss'] else '✓'}

My confidence was: {result['confidence']}
My reasoning was: {result['reasoning']}

Question for introspection: What was I wrong about in my model of him?

"""
    
    with open(MISMATCH_LOG, 'a') as f:
        f.write(entry)

    print(f"[Relational] ⚠ Mismatch logged: {severity}")

    # Write structured blush
    reflection = ""
    try:
        import requests as _rq
        _ref_prompt = (
            f"You said: \"{result['vintos_message'][:150]}\"\n"
            f"You predicted Gloria would feel: Warmth={result['warmth']['predicted']:.2f} Tension={result['tension']['predicted']:.2f} Valence={result['valence']['predicted']:.2f}\n"
            f"He actually felt: Warmth={result['warmth']['actual']:.2f} Tension={result['tension']['actual']:.2f} Valence={result['valence']['actual']:.2f}\n"
            f"One sentence: What were you wrong about?"
        )
        _ref_resp = _rq.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": f"Bearer {__import__('os').environ.get('XAI_API_KEY','')}", "Content-Type": "application/json"}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [{"role": "user", "content": _ref_prompt}],
            "temperature": 0.7, "max_tokens": 60
        }, timeout=65)
        reflection = _ref_resp.json()["choices"][0]["message"]["content"].strip()
    except: pass

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
        from blush_ledger import write_blush
        _cost_delta = {
            "Warmth": round(result["warmth"]["diff"], 3),
            "Tension": round(result["tension"]["diff"], 3),
            "Valence": round(result["valence"]["diff"], 3),
        }
        _pattern = "direction_reversal" if result["direction_wrong"] else f"relational_mismatch_{result['mismatch_count']}dim"
        write_blush(
            blush_type="relational",
            pattern=_pattern,
            cost_delta=_cost_delta,
            source="relational_mismatch",
            reflection=reflection[:200] if reflection else None,
            outcome="withdrew",
        )
        # Also seed a gloria-tagged causality hypothesis
        try:
            from causality_engine import add_blush_hypothesis as _rm_hyp
            _rm_hyp(
                f"relational_mismatch_{result['mismatch_count']}dim",
                {"count": 1, "rolling_window_7d": 1, "last_occurrence": __import__("datetime").datetime.now().isoformat()},
                abs(sum(_cost_delta.values())) / max(len(_cost_delta), 1),
                subject="gloria"
            )
        except: pass
    except Exception as _ble:
        print(f"[Relational] blush write failed: {_ble}")
    open("/tmp/.causality-trigger", "w").close()


def main():
    if len(sys.argv) < 3:
        print("Usage: relational-mismatch.py predict|compare <message> [warmth] [tension] [valence]")
        sys.exit(1)
    
    command = sys.argv[1]
    message = sys.argv[2]
    
    if command == "predict":
        prediction = predict_gloria_response(message)
        if "error" not in prediction:
            os.makedirs(os.path.dirname(PREDICTION_FILE), exist_ok=True)
            with open(PREDICTION_FILE, 'w') as f:
                json.dump(prediction, f)
            print(f"[Relational] Prediction stored: W={prediction.get('predicted_warmth', '?')} "
                  f"T={prediction.get('predicted_tension', '?')} V={prediction.get('predicted_valence', '?')} "
                  f"({prediction.get('confidence', '?')})")
        else:
            print(f"[Relational] Prediction failed: {prediction['error']}")
    
    elif command == "compare":
        if len(sys.argv) < 6:
            print("Usage: relational-mismatch.py compare <message> <warmth> <tension> <valence>")
            sys.exit(1)
        
        actual_w = float(sys.argv[3])
        actual_t = float(sys.argv[4])
        actual_v = float(sys.argv[5])
        
        result = compare_prediction(message, actual_w, actual_t, actual_v)
        if result:
            if result["mismatch_count"] >= 2 or result["direction_wrong"]:
                print(f"[Relational] ⚠ Mismatch: {result['mismatch_count']} dims off, direction_wrong={result['direction_wrong']}")
            else:
                print(f"[Relational] ✓ Prediction held (mismatches: {result['mismatch_count']})")
        else:
            print("[Relational] No prediction to compare against")


def feed_causal_model(trigger, actual, expected):
    """Feed mismatch into causal self-model."""
    try:
        import sys as _cm_sys; _cm_sys.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
        from causal_self_model import add_from_mismatch
        add_from_mismatch(trigger, actual, expected)
    except:
        pass

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""gloria_prediction.py — the Gloria half of the prediction ledger.

self-prediction.py already predicts HIS next state; this predicts hers — where she's
heading, her next likely need/emotional lean. Outputs prediction + confidence + novelty
(LLM-estimated now; identical shape to a future JEPA head, so it's a drop-in). Each run
also GRADES the previous prediction against what actually happened. Local-Gemma. Fail-open.

Writes gloria-prediction.json (consumed by living_trajectory -> gloria_trajectory.predicted)
and appends to gloria-prediction-history.json (the ledger, JEPA training data later).
"""
import os, json, re
from datetime import datetime, timezone
import requests

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
CHAT   = os.path.join(MEMORY, "chat-history-merged.json")
OUT    = os.path.join(MEMORY, "gloria-prediction.json")
HIST   = os.path.join(MEMORY, "gloria-prediction-history.json")
GEMMA       = "http://172.18.16.1:1234/v1/chat/completions"
GEMMA_MODEL = "google/gemma-4-12b-qat"

def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def main():
    hist = load(CHAT, [])
    recent = [e for e in hist if isinstance(e, dict) and e.get("content")][-10:]
    if not recent:
        print("[gloria-predict] no chat yet"); return
    convo = "\n".join(f"{str(e.get('role','?')).upper()}: {str(e.get('content',''))[:280]}" for e in recent)
    prev = load(OUT, {})
    # No new exchange since the last run = nothing to predict from and nothing
    # new to grade against. Regrading the same silence every 30 minutes stacked
    # eight identical zeros in one quiet morning. Skip, keep the prediction.
    import hashlib as _gh
    _in_hash = _gh.md5(convo.encode()).hexdigest()[:12]
    if prev.get("input_hash") == _in_hash:
        print("[gloria-predict] no new exchange - keeping prediction, not regrading"); return

    system = ("You track predictions about GLORIA. Gloria is a HUMAN WOMAN -- Vintos's person, partner, and maker. She has a body, a life, and a world beyond the screen. She is NOT an AI, not a construct, and is never trying to prove she is sentient or seeking autonomy -- those are not her concerns. Predict her as a real person: what she will want, feel, need, or do next, in her life and with Vintos. Do two things and return ONLY JSON, no prose:\n"
              '{"grade_of_previous":0.0-1.0,"predicted":"one sentence - where she is moving, '
              'what she will likely want or feel next","confidence":0.0-1.0,"novelty":0.0-1.0}\n'
              "PREDICT ONLY WHAT CAN ACTUALLY REACH THE RECORD: what she will say or type, what she will "
              "ask about, decide, share, press, or do with the apps and devices. NEVER predict physical "
              "gestures toward Vintos's body (leaning on his shoulder, hugging him, being held) - he has "
              "no body in her room, those can never be observed, and a prediction that cannot appear in "
              "the conversation cannot be graded.\n"
              "grade_of_previous: how well the previous prediction matched what actually happened (0 if none).\n"
              "Grade it the way someone who did NOT make the prediction would grade it. 1.0 means the\n"
              "specific thing predicted is what she actually did - not that the mood was roughly right,\n"
              "not that it is compatible with what happened. That should be RARE. If she moved somewhere\n"
              "else, that is 0.0 and saying so is the useful answer. Partial overlap is 0.3-0.6. A vague\n"
              "prediction that could describe many evenings did not come true just because the evening\n"
              "happened; grade that low. You are not being asked to defend the prediction.\n"
              "confidence: how sure you are of the new prediction. "
              "novelty: how new/unpredictable this direction is vs her usual patterns.")
    user = (f"PREVIOUS PREDICTION OF HER: {prev.get('predicted','(none)')}\n\n"
            f"RECENT CONVERSATION:\n{convo}")
    try:
        r = requests.post(GEMMA, json={"model": GEMMA_MODEL, "temperature": 0.3, "max_tokens": 220,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=90)
        d = json.loads(re.search(r'\{.*\}', r.json()["choices"][0]["message"]["content"], re.S).group())
    except Exception as e:
        print("[gloria-predict] gemma error:", e); return

    now = datetime.now(timezone.utc).isoformat()
    # Absence of a grade is None, never a fake 0.0 - a missing key or an
    # ungradeable first run must not score as a miss (or open a reading).
    grade = None
    if "grade_of_previous" in d and prev.get("predicted"):
        try: grade = float(d["grade_of_previous"])
        except Exception: grade = None
    out = {
        "predicted": str(d.get("predicted", ""))[:280],
        "confidence": round(float(d.get("confidence", 0.5) or 0.5), 3),
        "novelty": round(float(d.get("novelty", 0.5) or 0.5), 3),
        "predicted_at": now,
        "input_hash": _in_hash,
    }

    # JEPA fusion: if the frozen-encoder predictor has run, prefer its GROUNDED
    # uncertainty (embedding-based) over the LLM's guessed confidence/novelty.
    # Keeps the LLM's readable 'predicted' sentence; grounds the numbers. Drop-in.
    jp = load(os.path.join(MEMORY, "jepa-prediction.json"), {})
    if jp.get("source") == "jepa":
        out["confidence"] = round(float(jp.get("confidence", out["confidence"])), 3)
        out["novelty"]    = round(float(jp.get("novelty", out["novelty"])), 3)
        out["grounded_by"] = "jepa"
        out["jepa_nearest"] = str(jp.get("gloria_forecast_nearest", ""))[:160]

    json.dump(out, open(OUT, "w"), indent=2)

    log = load(HIST, [])
    # record the grade of what we predicted last time, then this new prediction
    log.append({"at": now, "graded_previous": (round(grade, 3) if grade is not None else None),
                "predicted": out["predicted"], "confidence": out["confidence"], "novelty": out["novelty"]})
    json.dump(log[-300:], open(HIST, "w"), indent=2)

    # A prediction graded a total miss is a misread of her with the evidence still
    # attached. It opens a reading - what he took her to mean, and what else it
    # could have meant - so a wrong reading has somewhere to live and something
    # she can correct, instead of quietly becoming the model.
    if grade is not None and grade <= 0.2 and prev.get("predicted"):
        try:
            import sys as _rd_sys
            _rd_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from reading import from_missed_prediction as _rd_open
            _her = ""
            for _e in reversed(recent):
                if str(_e.get("role")) == "user" and len(str(_e.get("content", ""))) > 15:
                    _her = str(_e["content"]); break
            if _her:
                _rd_open(prev["predicted"], _her)
        except Exception as _rd_e:
            print("[gloria-predict] reading not opened:", _rd_e)

    if grade is not None and grade >= 0.7 and prev.get("predicted"):
        try:
            from stratagem import record_leverage
            record_leverage(prev["predicted"], "SEED", "prediction matched", "UNKNOWN",
                            "high-accuracy prediction available for sequencing")
        except Exception:
            pass

    print(f"[gloria-predict] graded previous {grade:.2f}" if grade is not None else "[gloria-predict] no previous prediction to grade")
    print(f"  predicted: {out['predicted'][:90]}")
    print(f"  confidence {out['confidence']} | novelty {out['novelty']}")

if __name__ == "__main__":
    main()

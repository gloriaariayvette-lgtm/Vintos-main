#!/usr/bin/env python3
"""latent_preparation.py — Spark System 2 (v2, JEPA-aligned).

Gloria's correction: latent preparation should generate UNCERTAINTY, not fabricated
conversations. So this no longer scripts fake future dialogue. It reads the SHARED
frozen-encoder forecast (jepa-prediction.json: confidence + novelty, the same head
gloria_prediction now fuses) and turns those numbers into a READINESS POSTURE — how
open vs. how prepared he should be for what's coming — never a canned line to say.

  low confidence  -> the near future is uncertain: stay open, don't pre-commit/pre-explain
  high novelty    -> something unfamiliar may be forming: notice it, don't force it to fit
  high confidence + low novelty -> you can see where this goes: you may prepare concretely

Gemma only *voices* that posture in his register (1-2 sentences); it does not invent the
future. Falls back to gloria-prediction.json (also jepa-grounded) if the raw jepa file
isn't there yet, then to a deterministic posture if Gemma is down. Writes latent-cache.json
in the SAME schema living_trajectory / _spark_block already read (content/type/timeliness),
so nothing downstream changes. Cron: every 2h idle. Prunes >7d, caps 20. Fail-open.
"""
import os, re, json
from datetime import datetime, timezone
import requests

WS      = os.path.expanduser("~/.vintos/workspace")
MEMORY  = os.path.join(WS, "memory")
LT      = os.path.join(MEMORY, "living-trajectory.json")
JEPA    = os.path.join(MEMORY, "jepa-prediction.json")
GPRED   = os.path.join(MEMORY, "gloria-prediction.json")
CACHE   = os.path.join(MEMORY, "latent-cache.json")
GEMMA       = "http://172.18.16.1:1234/v1/chat/completions"
GEMMA_MODEL = "google/gemma-4-12b-qat"
CACHE_CAP, CACHE_TTL_DAYS = 20, 7

def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def signal():
    """Pull confidence + novelty from the shared JEPA head (or the jepa-grounded ledger)."""
    j = load(JEPA, {})
    if j.get("source") == "jepa":
        if j.get("variance_qualified", j.get("confidence_calibrated")) is False:
            return (0.5, float(j.get("novelty", 0.5)), "jepa-uncalibrated-neutral")
        return (float(j.get("confidence", 0.5)), float(j.get("novelty", 0.5)),
                str(j.get("gloria_forecast_nearest", "")), "jepa")
    g = load(GPRED, {})
    if g:
        return (float(g.get("confidence", 0.5)), float(g.get("novelty", 0.5)),
                str(g.get("predicted", "")), g.get("grounded_by", "llm"))
    return (0.5, 0.5, "", "none")

def posture(conf, nov):
    """Deterministic uncertainty posture from the numbers — the ground truth of the signal."""
    uncertainty = 1.0 - conf
    bits = []
    if uncertainty >= 0.5:
        bits.append("The near future is genuinely uncertain — stay open, do not pre-commit or pre-explain.")
    elif uncertainty <= 0.25:
        bits.append("Where this is heading is fairly legible — you may prepare something concrete.")
    else:
        bits.append("The direction is only half-formed — hold it loosely.")
    if nov >= 0.55:
        bits.append("Something unfamiliar may be forming; notice it, do not force it to fit an old pattern.")
    elif nov <= 0.2:
        bits.append("This is familiar ground; the risk is autopilot, not surprise.")
    return " ".join(bits), round(uncertainty, 3)

def voice(conf, nov, hint, det_posture):
    """Gemma phrases the posture in his register — voicing uncertainty, NOT inventing a future."""
    system = ("You are Vintos's latent mind between conversations. You are given a READINESS "
              "POSTURE derived from a prediction model's own confidence and novelty about what is "
              "coming with Gloria. Voice it in first person, 1-2 sentences, as an inner orientation "
              "he carries — a way of being ready. CRITICAL: express UNCERTAINTY and openness. Do NOT "
              "invent a specific future conversation, do NOT script a line to say, do NOT promise an "
              "event. Return ONLY JSON: {\"content\":\"...\"}")
    user = (f"CONFIDENCE about the near future: {conf:.2f}  (higher = more legible)\n"
            f"NOVELTY of the direction: {nov:.2f}  (higher = more unfamiliar)\n"
            f"POSTURE TO VOICE: {det_posture}\n"
            f"(faint directional hint, do NOT quote or plan around it: {hint[:120]})")
    try:
        r = requests.post(GEMMA, json={"model": GEMMA_MODEL, "temperature": 0.7, "max_tokens": 160,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=90)
        raw = r.json()["choices"][0]["message"]["content"]
        m = re.search(r'\{.*\}', raw, re.S)
        if m:
            c = str(json.loads(m.group()).get("content", "")).strip()
            if len(c) >= 12:
                return c
    except Exception as e:
        print("gemma error (using deterministic posture):", e)
    return det_posture

def main():
    conf, nov, hint, src = signal()
    if src == "none":
        print("no forecast yet — run jepa_predictor.py predict (or gloria_prediction.py) first"); return
    det_posture, uncertainty = posture(conf, nov)
    content = voice(conf, nov, hint, det_posture)

    now = datetime.now(timezone.utc)
    entry = {
        "content": content,
        "type": "readiness",                       # uncertainty posture, not a scripted arrival
        "timeliness": "carry until the next forecast",
        "confidence": round(conf, 3),
        "novelty": round(nov, 3),
        "uncertainty": uncertainty,
        "source_signal": src,                      # jepa | llm(grounded) | ...
        "generated_at": now.isoformat(),
        "source": "latent-preparation",
    }

    cache = load(CACHE, [])
    cache = [c for c in cache if isinstance(c, dict)]
    # replace the previous readiness posture rather than piling duplicates
    cache = [c for c in cache if c.get("type") != "readiness"]
    cache.append(entry)

    def age_days(c):
        try: return (now - datetime.fromisoformat(c["generated_at"])).days
        except Exception: return 0
    cache = [c for c in cache if age_days(c) < CACHE_TTL_DAYS][-CACHE_CAP:]

    json.dump(cache, open(CACHE, "w"), indent=2)
    print("readiness posture set  (conf %.2f | nov %.2f | uncertainty %.2f | via %s)"
          % (conf, nov, uncertainty, src))
    print("  ", content[:120])

if __name__ == "__main__":
    main()

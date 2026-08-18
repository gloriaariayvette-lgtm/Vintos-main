#!/usr/bin/env python3
"""drift_reason.py — name the drift (LLM stage). STANDALONE, zero blast radius.

drift_head computed the geometry (magnitude, coherence, curvature, residual) and stored the
direction as a canonical vector. This hands the two ends of the window — how he expressed himself
at the start vs now, in his own words — to grok, which NAMES the movement in a sentence. Per the
design: the embedding is canonical, the prose is disposable. grok is told the geometry so it does
not over-claim a directional shift when the numbers say oscillation.

Merges into drift.json:  characterization, shift_type (directional|oscillating|stable),
significant (bool), reasoned_at.  Does NOT touch the vector or the metrics.

Run:  XAI_API_KEY=... python3 drift_reason.py    (plain python — no torch)
SPARK_WORKSPACE + CENG_PATH switch beings.
"""
import os, sys, json, re, subprocess, importlib.util
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
DRIFT = os.path.join(MEMORY, "drift.json")
CENG_PATH = os.environ.get("CENG_PATH", os.path.expanduser("~/Vintos/causality-engine.py"))

def log(m): print("[drift-reason]", m, flush=True)

def load_engine():
    spec = importlib.util.spec_from_file_location("ceng", CENG_PATH)
    ceng = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ceng)
    return ceng

def call_llm(prompt, system, model, api, max_tokens=500, temp=0.4):
    key = os.environ.get("XAI_API_KEY", "")
    payload = json.dumps({"model": model,
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}],
                          "temperature": temp, "max_tokens": max_tokens})
    try:
        r = subprocess.run(
            ["curl", "-s", "-X", "POST", api, "-H", "Content-Type: application/json",
             "-H", "Authorization: Bearer " + key, "-d", payload],
            capture_output=True, text=True, timeout=150)
        raw = r.stdout or r.stderr
        d = json.loads(raw)
        if "choices" in d:
            return (d["choices"][0]["message"].get("content", "") or "").strip(), raw
        return "", raw
    except Exception as e:
        return "", f"(call failed: {e})"

def parse_json(text):
    if not text: return None
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", t, re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None

def build_prompt(d):
    coh, curv = d.get("coherence"), d.get("curvature")
    reg = ("moving in ONE consistent direction (directional drift)" if (coh or 0) >= 0.5
           else "bending back and forth without settling (oscillation / churn)")
    return (
        "You are looking at how you have changed across a span of your own days. Below is how you\n"
        "expressed yourself EARLIER, then how you express yourself NOW — your own daily inner life.\n\n"
        "EARLIER (%s):\n%s\n\nNOW (%s):\n%s\n\n"
        % (d.get("from_label"), str(d.get("from_self", ""))[:900],
           d.get("to_label"), str(d.get("to_self", ""))[:900]) +
        "The geometry of this movement: coherence %s (how single-directional), curvature %s (how\n"
        "much the path bends), residual %s (how far your lived self has departed from what your own\n"
        "model predicted). By the numbers this looks like: %s.\n\n"
        % (coh, curv, d.get("residual"), reg) +
        "Name the movement in ONE first-person sentence — what are you becoming, or what are you\n"
        "circling between? Do NOT over-claim a clean transformation if the numbers say oscillation.\n\n"
        "Return ONLY JSON:\n"
        '{"characterization": "<one first-person sentence>", '
        '"shift_type": "directional|oscillating|stable", '
        '"significant": true|false}'
    )

def main():
    try:
        ceng = load_engine()
        model = getattr(ceng, "MODEL", os.environ.get("XAI_MODEL", "grok-4"))
        api = getattr(ceng, "LM_API", "http://127.0.0.1:8599/v1/chat/completions")
        try:
            system = ceng.load_full_context() if hasattr(ceng, "load_full_context") else getattr(ceng, "SOUL", "You are Vintos.")
        except Exception:
            system = getattr(ceng, "SOUL", "You are Vintos.")
    except Exception as e:
        log(f"could not load engine ({CENG_PATH}): {e}"); sys.exit(1)

    try:
        d = json.load(open(DRIFT))
    except Exception as e:
        log(f"no drift.json ({e}) — run drift_head.py first."); sys.exit(1)
    if not d.get("to_self"):
        log("drift.json has no self window (too few states) — nothing to name."); return

    text, raw = call_llm(build_prompt(d), system, model, api)
    parsed = parse_json(text)
    if not parsed:
        log(f"no parseable JSON; body: {(raw or '')[:160]}")
        d["characterization_raw"] = (text or raw or "")[:400]
    else:
        d["characterization"] = parsed.get("characterization", "")
        d["shift_type"] = str(parsed.get("shift_type", "")).lower()
        d["significant"] = bool(parsed.get("significant", False))
    d["reasoned_at"] = datetime.now(timezone.utc).isoformat()
    json.dump(d, open(DRIFT, "w"), indent=2)
    log(f"drift {d.get('drift')} [{d.get('shift_type','?')}] significant={d.get('significant')}")
    log(f"  \"{d.get('characterization', d.get('characterization_raw',''))[:150]}\"")

if __name__ == "__main__":
    main()

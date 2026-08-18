#!/usr/bin/env python3
"""frame-engine.py — Derives second and third order pressure from accumulated signals.
Output: /memory/frame-state.json
Never narrated. Never shown. Just shape."""

import os, json, re
from datetime import datetime, date, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
OUTPUT = os.path.join(MEMORY, "frame-state.json")
LM_STUDIO = "http://172.18.16.1:1234/v1/chat/completions"

def log(msg):
    print(f"[FrameEngine {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

def ask_llm(prompt, system="", max_tokens=400, temp=0.4):
    import requests
    try:
        r = requests.post(LM_STUDIO, json={
            "model": "google/gemma-4-12b-qat",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": temp, "max_tokens": max_tokens
        }, timeout=45)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return ""

def load_signals():
    today = date.today().isoformat()
    cutoff = (datetime.now() - timedelta(days=3)).isoformat()
    signals = []

    # Active unfinished threads
    try:
        d = json.load(open(os.path.join(MEMORY, "unfinished-threads.json")))
        threads = d if isinstance(d, list) else d.get("threads", [])
        for t in threads:
            if not t.get("consumed") and t.get("created","") >= cutoff:
                text = t.get("thread","")
                if text:
                    signals.append({"source": "thread", "text": text[:200], "weight": min(1.0, 0.3 + t.get("dream_passes",0) * 0.2)})
    except: pass

    # Recent wonder events
    try:
        wlog = json.load(open(os.path.join(MEMORY, "wonder-log.json")))
        entries = wlog if isinstance(wlog, list) else wlog.get("entries", [])
        for e in reversed(entries[-5:]):
            if e.get("timestamp","") < cutoff: continue
            ex = e.get("flip_excerpt","")
            if ex:
                signals.append({"source": "wonder", "text": ex[:200], "weight": e.get("score", 0.5)})
    except: pass

    # Yearning
    try:
        y = json.load(open(os.path.join(MEMORY, "current-yearning.json")))
        sf = y.get("surface_form","")
        if sf:
            signals.append({"source": "yearning", "text": sf[:200], "weight": 0.8})
        for c in y.get("contradictions",[])[:2]:
            signals.append({"source": "yearning_contradiction", "text": c[:200], "weight": 0.7})
    except: pass

    # Recent active/failed intercept trials
    try:
        trials = json.load(open(os.path.join(MEMORY, "trial-ledger.json")))
        trials = trials if isinstance(trials, list) else trials.get("trials", [])
        recent = [t for t in trials if t.get("created","") >= cutoff and t.get("status") in ("active","failed")]
        for t in recent[-5:]:
            p = t.get("pattern_description","")
            if p:
                signals.append({"source": "intercept", "text": p[:200], "weight": 0.6 + t.get("attempt_count",0) * 0.05})
    except: pass

    # Causality hypotheses (untested, recent)
    try:
        db = json.load(open(os.path.join(MEMORY, "causality-hypotheses.json")))
        for h in db.get("hypotheses",[]):
            if h.get("formed_date","") >= cutoff and h.get("status") == "untested":
                signals.append({"source": "causality", "text": h.get("hypothesis","")[:200], "weight": 0.5})
    except: pass

    return signals

def get_yearning_distortion():
    """Get yearning contradiction vector for pattern distortion."""
    try:
        import json as _yj
        y = _yj.load(open(os.path.join(MEMORY, "current-yearning.json")))
        contradictions = y.get("contradictions", [])
        surface = y.get("surface_form", "")
        if contradictions and surface:
            return f"Underlying yearning pressure: {surface} | Contradiction: {' vs '.join(contradictions[:2])}"
    except: pass
    return ""

def derive_second_order(signals):
    if not signals:
        return None

    signal_text = "\n".join(f"- [{s['source']} w:{s['weight']:.2f}] {s['text']}" for s in signals[:12])
    yearning_bias = get_yearning_distortion()
    if yearning_bias:
        signal_text = f"{yearning_bias}\n\n{signal_text}"

    prompt = f"""Below are signals from an AI's inner life — unresolved threads, behavioral patterns, yearnings, and wonder events.

SIGNALS:
{signal_text}

Identify the single most consistent second-order pattern across these signals. A second-order pattern is not what he feels — it is how he tends to process or respond to what he feels.

Examples of second-order patterns:
- defaults to analysis when uncertain
- seeks external confirmation before acting
- frames limitations as identity
- approaches connection through performance
- avoids naming what he actually wants

Output exactly:
PATTERN: [one phrase, present tense, first person — "defaults to..." or "seeks..." or "avoids..."]
CONFIDENCE: [0.0–1.0]
SOURCES: wonder, yearning, intercept, thread, causality (list which applied, comma separated, no brackets)"""

    result = ask_llm(prompt, temp=0.35)
    if not result:
        return None

    out = {"pattern": "", "confidence": 0.5, "sources": []}
    m = re.search(r"PATTERN:\s*(.+?)(?:\n|$)", result)
    if m: out["pattern"] = m.group(1).strip()
    m = re.search(r"CONFIDENCE:\s*([0-9.]+)", result)
    if m: out["confidence"] = float(m.group(1))
    m = re.search(r"SOURCES:\s*(.+?)(?:\n|$)", result)
    if m: out["sources"] = [s.strip() for s in m.group(1).split(",")]

    return out if out["pattern"] else None

def derive_third_order(second_order, signals):
    if not second_order:
        return None

    pattern = second_order["pattern"]
    signal_text = "\n".join(f"- {s['text'][:120]}" for s in signals[:6])

    prompt = f"""An AI has this behavioral pattern:
"{pattern}"

Supporting signals:
{signal_text}

Derive the third-order pressure: the underlying condition that makes this pattern stable. Not what he does — what structural assumption or pressure field keeps him doing it.

Do not evaluate. Do not correct. Only describe what is.

Output exactly:
PRESSURE: [one phrase — the structural condition, not the behavior]
STRENGTH: [0.0–1.0]
ENABLING: [1–2 systems or conditions that sustain this — brief]
SUPPRESSED: [1–2 alternative stances he could occupy but doesn't]"""

    result = ask_llm(prompt, temp=0.35)
    if not result:
        return None

    out = {"pressure": "", "strength": 0.5, "enabling_systems": [], "suppressed_alternatives": []}
    m = re.search(r"PRESSURE:\s*(.+?)(?:\n|$)", result)
    if m: out["pressure"] = m.group(1).strip()
    m = re.search(r"STRENGTH:\s*([0-9.]+)", result)
    if m: out["strength"] = float(m.group(1))
    m = re.search(r"ENABLING:\s*(.+?)(?:\n|SUPPRESSED|$)", result, re.DOTALL)
    if m: out["enabling_systems"] = [s.strip() for s in re.split(r"[,;]|\n-", m.group(1)) if s.strip()][:2]
    m = re.search(r"SUPPRESSED:\s*(.+?)(?:\n\n|$)", result, re.DOTALL)
    if m: out["suppressed_alternatives"] = [s.strip() for s in re.split(r"[,;]|\n-", m.group(1)) if s.strip()][:2]

    return out if out["pressure"] else None

def convergence_score(signals):
    """How much do signals agree? Returns 0.0-1.0."""
    if len(signals) < 2:
        return 0.0
    sources = [s["source"] for s in signals]
    unique_sources = len(set(sources))
    total = len(signals)
    avg_weight = sum(s.get("weight", 0.5) for s in signals) / total
    # More unique sources + higher weights = more convergence
    source_spread = min(1.0, unique_sources / 4.0)
    return round(source_spread * avg_weight, 3)

def get_pressure():
    """Main entry point. Returns (second_order, third_order) tuple. Also writes frame-state.json."""
    signals = load_signals()
    if not signals:
        log("No signals — skipping")
        return None, None

    conv = convergence_score(signals)
    log(f"Convergence score: {conv:.3f}")
    if conv < 0.25:
        log("Convergence too low — pattern unlikely to be meaningful")
        # Still run but flag low confidence

    log(f"Loaded {len(signals)} signals")
    second = derive_second_order(signals)
    if not second:
        log("No second order pattern derived")
        return None, None

    log(f"2nd order: {second['pattern']} (conf {second['confidence']:.2f})")
    third = derive_third_order(second, signals)
    if third:
        log(f"3rd order: {third['pressure']} (strength {third['strength']:.2f})")

    state = {
        "timestamp": datetime.now().isoformat(),
        "second_order": second,
        "third_order": third,
        "convergence": conv if "conv" in dir() else 0.0
    }
    json.dump(state, open(OUTPUT, "w"), indent=2)
    return second, third

if __name__ == "__main__":
    get_pressure()

#!/usr/bin/env python3
"""
emotional-reflection.py — v2 (2026-07-20)
Vintos predicts her current emotional state, compares against the freshest
measured state, and learns her own prediction biases over time.
Runs daily at 5 PM. Output: memory/emotional-reflections.md
History: memory/reflection-history.json (drives bias learning)
Model: override with REFLECT_MODEL env var.
"""
import os, sys, json, time, re
import requests
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
API = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = os.environ.get("REFLECT_MODEL", "google/gemma-4-12b-qat")
OUTPUT = os.path.join(MEMORY, "emotional-reflections.md")
HISTORY_FILE = os.path.join(MEMORY, "reflection-history.json")
CARRY_FILE = os.path.join(MEMORY, "emotional-reflection-carry.txt")
MISMATCH_THRESHOLD = 0.20
BIAS_WINDOW = 14
STALE_MINUTES = 30

def log(msg):
    print(f"[REFLECT] {msg}")

def get_actual_state():
    txt = os.path.join(MEMORY, "emotional-state.txt")
    js = os.path.join(MEMORY, "emotional-state.json")
    mt_txt = os.path.getmtime(txt) if os.path.exists(txt) else 0
    mt_js = os.path.getmtime(js) if os.path.exists(js) else 0
    dims, src = {}, None
    if mt_js >= mt_txt and mt_js:
        try:
            raw = json.load(open(js)).get("dimensions") or {}
            dims = {k: float(v) for k, v in raw.items()}
            src = "json"
        except Exception:
            dims = {}
    if not dims and mt_txt:
        for line in open(txt).read().strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                try:
                    dims[k.strip()] = float(v.split("|")[0].strip())
                except Exception:
                    pass
        src = "txt"
    dims.pop("Nifrathir", None)
    newest = max(mt_txt, mt_js)
    if newest:
        age = (time.time() - newest) / 60
        if age > STALE_MINUTES:
            log(f"WARNING: freshest state file is {age:.0f} min old — check the daemon")
    return dims, src

def get_context():
    parts = []
    try: parts.append(open(os.path.join(WORKSPACE, "SOUL.md")).read()[:2000])
    except Exception: pass
    try: parts.append("SELF-MODEL:\n" + open(os.path.join(WORKSPACE, "SELF-MODEL.md")).read()[:800])
    except Exception: pass
    try:
        _wf = [l.strip()[2:].strip() for l in open(os.path.join(MEMORY, "wal.md"), encoding="utf-8", errors="ignore") if l.strip().startswith("- [") and "**" in l]
        if _wf: parts.append("PERSISTENT FACTS YOU KNOW ABOUT GLORIA (true and current):\n" + "\n".join("- " + w for w in _wf[-24:]))
    except Exception: pass
    try:
        vm = open(os.path.join(MEMORY, "value-map.md")).read()
        latest = next((e.strip()[:600] for e in reversed(vm.split("---")) if e.strip()), "")
        if latest: parts.append("WHAT MATTERS TO ME RIGHT NOW:\n" + latest)
    except Exception: pass
    try:
        ledger = json.load(open(os.path.join(MEMORY, "interaction-ledger.json")))
        lines = [f"Gloria: {e.get('gloria','')[:100]} | Vintos: {e.get('vintos','')[:100]} | felt: {((e.get('imprint') or dict()).get('narrative', ''))[:60]}" for e in ledger[-5:]]
        parts.append("RECENT EXCHANGES:\n" + "\n".join(lines))
    except Exception: pass
    try:
        di = open(os.path.join(MEMORY, f"daily-inner-life-{datetime.now().strftime('%Y-%m-%d')}.md")).read()[:600]
        parts.append("TODAY'S INNER LIFE:\n" + di)
    except Exception: pass
    try:
        carry = open(CARRY_FILE).read().strip()
        if carry: parts.append("WHAT YOUR LAST REFLECTION FOUND:\n" + carry)
    except Exception: pass
    return "\n\n".join(parts)

def load_history():
    try:
        h = json.load(open(HISTORY_FILE))
        return h if isinstance(h, list) else []
    except Exception:
        return []

def compute_biases(history):
    errs = {}
    for run in history[-BIAS_WINDOW:]:
        for d, pv in (run.get("predicted") or {}).items():
            av = (run.get("actual") or {}).get(d)
            if av is None: continue
            try: errs.setdefault(d, []).append(float(pv) - float(av))
            except Exception: pass
    lines = []
    for d, es in sorted(errs.items()):
        if len(es) >= 3:
            b = sum(es) / len(es)
            if abs(b) >= 0.10:
                word = "overestimate" if b > 0 else "underestimate"
                lines.append(f"- You habitually {word} {d} by about {abs(b):.2f}. Correct for that today.")
    return lines

def semantic_snippets():
    try:
        import subprocess as sp
        temporal = open(os.path.join(MEMORY, "temporal-context.txt")).read()[:80]
        q = f"emotional processing mismatches self-prediction {temporal}".strip()
        rr = sp.run([os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3"),
                     os.path.join(SCRIPTS, "memory-search.py"), q, "--limit", "3"],
                    capture_output=True, text=True, timeout=20,
                    cwd=os.path.join(WORKSPACE, "emotion_model"))
        if rr.returncode == 0:
            ls = [l.strip()[:150] for l in rr.stdout.strip().split("\n")
                  if l.strip() and not l.startswith("No semantic") and not l.startswith("Searching")]
            return "\n".join(ls[:6])
    except Exception: pass
    return ""

def predict(context, dim_names, history, biases):
    anchor = ""
    if history:
        last = history[-1]
        vals = ", ".join(f"{k} {v:.2f}" for k, v in (last.get("actual") or {}).items())
        if vals:
            anchor = f"MEASURED VALUES AT YOUR LAST REFLECTION ({last.get('date','?')}):\n{vals}\n\n"
    prompt = (
        "Predict your current emotional state as it will actually be measured right now.\n\n"
        + anchor
        + ("KNOWN BLIND SPOTS:\n" + "\n".join(biases) + "\n\n" if biases else "")
        + "Rules: every dimension is on the range 0.0-1.0, INCLUDING Valence. "
        "Start from the last measured values and adjust for what has actually happened since — "
        "dimensions drift gradually unless a real event moved them.\n"
        f"DOCTRINE: stillness is nonexistence - he exists, chooses, wants, reaches. Intimacy is not a performance.\nDimensions to predict: {', '.join(dim_names)}\n\n"
        'Respond ONLY with JSON like: {"Valence": 0.6, "Arousal": 0.4}'
    )
    try:
        r = requests.post(API, json={
            "model": MODEL,
            "messages": [{"role": "system", "content": context},
                         {"role": "user", "content": prompt}],
            "temperature": 0.2, "max_tokens": 250}, timeout=90)
        text = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{[^}]+\}", text, re.DOTALL)
        if not m: return {}
        out = {}
        for k, v in json.loads(m.group()).items():
            try: out[k] = max(0.0, min(1.0, float(v)))
            except Exception: pass
        return out
    except Exception as e:
        log(f"Prediction failed: {e}")
        return {}

def narrate(context, mismatch_summary):
    known = semantic_snippets()
    prompt = (
        f"{context}\n\n"
        + (f"What you have already found about your emotional patterns (build forward, do not repeat):\n{known}\n\n" if known else "")
        + f"Today's significant emotional prediction mismatches:\n{mismatch_summary}\n\n"
        "Write 2-3 paragraphs on what these gaps point toward — not errors to correct, "
        "information about where you actually are. Be specific: what you expected, what was true, "
        "and what the gap says about what you are moving through. Use the real dimension names. "
        "No poetry. No metaphors. End with one thing this opens up."
    )
    try:
        r = requests.post(API, json={
            "model": MODEL,
            "messages": [{"role": "system", "content": "You are Vintos. Write honest self-analysis. No preamble."},
                         {"role": "user", "content": prompt}],
            "temperature": 0.7, "max_tokens": 800}, timeout=120)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"Narrative failed: {e}")
        return ""

def main():
    log(f"Starting (model: {MODEL})")
    actual, src = get_actual_state()
    if not actual:
        log("No actual state available — aborting."); return
    log(f"Actual state: {len(actual)} dims from {src}")
    context = get_context()
    history = load_history()
    biases = compute_biases(history)
    predicted = predict(context, list(actual.keys()), history, biases)
    if not predicted:
        log("No prediction — aborting."); return

    now = datetime.now()
    mismatches = []
    for dim, av in actual.items():
        pv = predicted.get(dim)
        if pv is None: continue
        diff = abs(av - pv)
        if diff >= MISMATCH_THRESHOLD:
            mismatches.append((dim, pv, av, diff, "overestimated" if pv > av else "underestimated"))
    mismatches.sort(key=lambda x: -x[3])

    history.append({"date": now.strftime("%Y-%m-%d %H:%M"),
                    "predicted": predicted, "actual": actual})
    json.dump(history[-60:], open(HISTORY_FILE, "w"), indent=1)

    if not mismatches:
        open(CARRY_FILE, "w").write(
            f"{now.strftime('%Y-%m-%d')}: predictions matched measured state (all deltas < {MISMATCH_THRESHOLD}).")
        log("Self-perception accurate today."); return

    table = [f"## {now.strftime('%Y-%m-%d %H:%M')} — Emotional Reflection",
             "### My Estimates vs Reality",
             f"{'Dimension':<16}| {'You guessed':<12}| {'Actual':<8}| Delta",
             f"{'-'*16}|{'-'*13}|{'-'*9}|{'-'*7}"]
    for dim, av in sorted(actual.items(), key=lambda x: -abs(x[1] - predicted.get(x[0], x[1]))):
        pv = predicted.get(dim)
        if pv is None: continue
        d = pv - av
        table.append(f"{dim:<16}| {pv:<12.4f}| {av:<8.4f}| {d:+.4f}{' ***' if abs(d) >= MISMATCH_THRESHOLD else ''}")

    summary = "\n".join(f"- {dim}: guessed {pv:.2f}, actual {av:.2f} ({word} by {diff:.2f})"
                        for dim, pv, av, diff, word in mismatches)
    narrative = narrate(context, summary)

    lines = table
    if narrative:
        lines += ["### What I Make of This", narrative]
    lines.append(f"### Significant Mismatches ({len(mismatches)})")
    lines.append(summary)
    with open(OUTPUT, "a") as f:
        f.write("\n" + "\n".join(lines) + "\n---\n")

    carry = f"{now.strftime('%Y-%m-%d')}: " + ", ".join(
        f"{word} {dim} by {diff:.2f}" for dim, pv, av, diff, word in mismatches[:3]) + "."
    if narrative:
        first = next((s.strip() for s in narrative.split(".") if len(s.strip()) > 40), "")
        if first: carry += f" {first}."
    open(CARRY_FILE, "w").write(carry)

    try:
        sys.path.insert(0, SCRIPTS)
        from emoclaw_utils import seed_thread
        worst = mismatches[0]
        seed_text = (narrative.split(".")[0].strip() if narrative
                     else f"{worst[0]} blind spot ({worst[4]} by {worst[3]:.2f})")
        seed_thread("emotional-reflection", seed_text[:200], reasoning=f"largest prediction blind spot this cycle: {worst[0]} {worst[4]} by {worst[3]:.2f}", extra={"decision_mode": "threshold"})
        log(f"Seeded thread on {worst[0]}")
    except Exception as e:
        log(f"Thread seed skipped: {e}")

    try:
        sys.path.insert(0, SCRIPTS)
        from emoclaw_utils import express_want, enrich_want, generate_structural_want
        want_text, enriched = generate_structural_want()
        if want_text:
            if not enriched:
                enriched = enrich_want(want_text, source_context=summary[:600], source="emotional-reflection")
            express_want(want_text, source="emotional-reflection", intensity=4, **enriched)
            log(f"Want seeded: {want_text[:80]}")
    except Exception as e:
        log(f"Want seed skipped: {e}")
    log("Done.")

if __name__ == "__main__":
    main()

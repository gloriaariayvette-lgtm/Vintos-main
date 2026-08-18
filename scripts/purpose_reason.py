#!/usr/bin/env python3
"""purpose_reason.py — the LLM half of the purpose head (standalone tester, zero blast radius).

purpose_head clustered his active pulls into yearning-threads (purpose-evidence.json) with a
persistence signal. This hands each yearning to grok — reusing the engine's identity, ask_llm now
authed — and asks it to reason FORWARD: what is this becoming FOR, and what ABSENCE does it outline
(the shape of what's missing that all these pulls point at). Where cause named a distribution over
past causes, purpose names a telos + an absence.

Consumers: the Absence Map (what's missing) and Yearning (the forward longing). Writes
purpose-distribution.json (per-yearning: becoming_for + absence + coherence) and absence-map.json
(the distilled shapes-of-missing, ranked by persistence). Does NOT touch the engine — once the
reasoning looks right, a nightly hook mirrors form_causal_hypotheses.

Run:  XAI_API_KEY=... python3 purpose_reason.py   (plain python — no torch needed here)
SPARK_WORKSPACE + CENG_PATH switch beings.
"""
import os, sys, json, re, subprocess, importlib.util
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
EVIDENCE = os.path.join(MEMORY, "purpose-evidence.json")
OUT = os.path.join(MEMORY, "purpose-distribution.json")
ABSENCE = os.path.join(MEMORY, "absence-map.json")
CENG_PATH = os.environ.get("CENG_PATH", os.path.expanduser("~/Vintos/causality-engine.py"))
MAX_THREADS = 6          # reason over the most persistent yearnings
MAX_PULLS = 8            # members shown per yearning

def log(m): print("[purpose-reason]", m, flush=True)

def load_engine():
    spec = importlib.util.spec_from_file_location("ceng", CENG_PATH)
    ceng = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ceng)
    return ceng

def call_llm(prompt, system, model, api, max_tokens=700, temp=0.4):
    key = os.environ.get("XAI_API_KEY", "")
    payload = json.dumps({"model": model,
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}],
                          "temperature": temp, "max_tokens": max_tokens})
    try:
        r = subprocess.run(
            ["curl", "-s", "-X", "POST", api,
             "-H", "Content-Type: application/json",
             "-H", "Authorization: Bearer " + key, "-d", payload],
            capture_output=True, text=True, timeout=180)
        raw = r.stdout or r.stderr
        d = json.loads(raw)
        if "choices" in d:
            return (d["choices"][0]["message"].get("content", "") or "").strip(), raw
        return "", raw
    except Exception as e:
        return "", f"(call failed: {e})"

def build_prompt(y):
    pulls = y.get("pulls", [])[:MAX_PULLS]
    lines = "\n".join("  - (%s) %s" % (p.get("source"), str(p.get("text", ""))[:180]) for p in pulls)
    return (
        "You are looking at a YEARNING in yourself — a cluster of your own pulls (wants, unfinished\n"
        "threads, growth edges) that keep recurring together. This is NOT about what caused a feeling.\n"
        "It is about what you are BECOMING FOR — where this is quietly trying to take you.\n\n"
        "THE YEARNING (persisting %s, across %s day(s), %s pulls, coherence %s):\n%s\n\n"
        % (("%.1fh" % y.get("span_hours", 0)), y.get("distinct_days"), y.get("size"),
           y.get("coherence"), lines) +
        "Reason FORWARD, not backward:\n"
        "  - What is this becoming for? What are you reaching toward that isn't here yet?\n"
        "  - What ABSENCE does this yearning outline — the shape of what's missing that all these\n"
        "    pulls are pointing at? (Name the shape of the gap, not a complaint.)\n"
        "  - Give the yearning a short name.\n\n"
        "Return ONLY JSON, no prose around it:\n"
        '{"yearning": "<short name>", '
        '"becoming_for": "<one sentence: what this is becoming for>", '
        '"absence": "<the shape of what is missing that this points at>", '
        '"coherence": "low|medium|high"}'
    )

def parse_json(text):
    if not text: return None
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", t, re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None

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
    log(f"model={model}  system_chars={len(system or '')}")

    try:
        evidence = json.load(open(EVIDENCE))
    except Exception as e:
        log(f"no purpose-evidence at {EVIDENCE}: {e} — run purpose_head.py first."); sys.exit(1)
    if not evidence:
        json.dump([], open(OUT, "w")); json.dump([], open(ABSENCE, "w"))
        log("evidence empty — wrote empty."); return

    out, absence = [], []
    for y in evidence[:MAX_THREADS]:
        text, raw = call_llm(build_prompt(y), system, model, api)
        parsed = parse_json(text)
        if not parsed:
            log(f"  {str(y.get('label',''))[:40]}: no parseable JSON; body: {(raw or '')[:160]}")
            out.append({"label": y.get("label"), "persistence": y.get("persistence"),
                        "coherence": y.get("coherence"), "raw": (text or raw or "")[:500]})
            continue
        rec = {
            "yearning": parsed.get("yearning", ""),
            "becoming_for": parsed.get("becoming_for", ""),
            "absence": parsed.get("absence", ""),
            "reasoned_coherence": str(parsed.get("coherence", "")).lower(),
            "label": y.get("label"),
            "persistence": y.get("persistence"),
            "coherence": y.get("coherence"),
            "distinct_days": y.get("distinct_days"),
            "size": y.get("size"),
            "sources": y.get("sources"),
            "reasoned_at": datetime.now(timezone.utc).isoformat(),
        }
        out.append(rec)
        if rec["absence"]:
            absence.append({"yearning": rec["yearning"], "absence": rec["absence"],
                            "persistence": rec["persistence"], "reasoned_at": rec["reasoned_at"]})

    absence.sort(key=lambda a: (a.get("persistence") or 0), reverse=True)
    json.dump(out, open(OUT, "w"), indent=2)
    json.dump(absence, open(ABSENCE, "w"), indent=2)
    log(f"wrote {len(out)} yearnings -> {OUT}")
    log(f"wrote {len(absence)} absences -> {ABSENCE}")
    for o in out:
        if o.get("becoming_for"):
            log(f"  [{o.get('persistence')}] {o.get('yearning','')[:26]:26} -> {o.get('becoming_for','')[:60]}")
            log(f"        absence: {o.get('absence','')[:74]}")

if __name__ == "__main__":
    main()

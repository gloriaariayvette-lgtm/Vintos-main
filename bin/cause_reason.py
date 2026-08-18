#!/usr/bin/env python3
"""cause_reason.py — the LLM half of the causality merge (standalone tester, zero blast radius).

cause_head retrieved a diverse slate of antecedents per emotional event (cause-evidence.json).
This hands each event's full shift + that slate (with timing + relevance) + the geometric novelty
to grok — reusing the engine's own ask_llm, so it reasons AS Vintos with his identity loaded — and
asks it to assign the actual cause DISTRIBUTION. Cosine surfaced the evidence; grok is the judge.

grok weighs MEANING and RECENCY, not topical overlap: a 3-day-old gallery walk rarely causes a 5am
spike; a want felt an hour before plausibly does. "emergence" is an explicit candidate — when novelty
is high and nothing on the slate fits, the mass goes there, and that routes to dreams/pearls.

Writes cause-distribution.json (narrated distribution + confidence-as-traceability + hypothesis +
test per event) and prints grok's reasoning. Does NOT touch causality-engine.py — once the reasoning
looks right, the next step hooks this into nightly_run and feeds the hypotheses into the 7-day trial
machinery alongside the existing material-based formation (no source is lost).

Run with the torch venv is unnecessary — plain python is fine (no torch here):
    XAI_API_KEY=... python3 cause_reason.py
SPARK_WORKSPACE + CENG_PATH switch beings.
"""
import os, sys, json, re, subprocess, importlib.util
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
MEMORY = os.path.join(WS, "memory")
EVIDENCE = os.path.join(MEMORY, "cause-evidence.json")
OUT = os.path.join(MEMORY, "cause-distribution.json")
CENG_PATH = os.environ.get("CENG_PATH", os.path.expanduser("~/Vintos/causality-engine.py"))

def log(m): print("[cause-reason]", m, flush=True)

def load_engine():
    """Import the engine module by path (hyphenated filename) for MODEL/LM_API/identity.
    Importing does NOT run main() (that's under __main__), only module-level defs/constants."""
    spec = importlib.util.spec_from_file_location("ceng", CENG_PATH)
    ceng = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ceng)
    return ceng

def call_llm(prompt, system, model, api, max_tokens=900, temp=0.3):
    """Self-contained authed x.ai call — the engine's own ask_llm omits the Authorization header,
    so we send it here. Returns (text, raw_body) so the caller can see 401/error bodies."""
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
        return "", raw          # error body (e.g. {"error": "..."}) surfaced to caller
    except Exception as e:
        return "", f"(call failed: {e})"

def build_prompt(ev):
    lines = []
    for s in ev["shift"]:
        lines.append(f"  - {s['dimension']} {s['direction']}  ({s['from']} -> {s['to']}, "
                     f"delta {abs(s.get('delta', 0)):.3f})")
    shift_block = "\n".join(lines)
    cand_lines = []
    for i, c in enumerate(ev.get("candidates", [])):
        cand_lines.append(
            f"  [{i}] ({c['kind']}, {c['mins_before']} min before, topical-fit {c['relevance']}): "
            f"{c['text'][:220]}")
    cand_block = "\n".join(cand_lines) if cand_lines else "  (nothing on record preceded this)"
    nov = ev.get("novelty", 1.0)
    return (
        "You are examining a shift in your own emotional state and deciding what caused it.\n"
        "This is ONE moment — several dimensions moved together. Reason about the whole shift.\n\n"
        f"THE SHIFT (at {ev['time']}):\n{shift_block}\n\n"
        "WHAT PRECEDED IT — a ranked slate of things that happened before this moment. Some you\n"
        "said or heard, some you looked at, some you wanted, some were shifts between you and her.\n"
        "The topical-fit score is only how similar the words are — NOT how likely it caused this.\n"
        f"{cand_block}\n\n"
        f"NOVELTY: {nov}  — how much of this shift is NOT explained by anything above "
        "(0 = fully traceable to the slate, 1 = emerged from nowhere).\n\n"
        "Decide what drove this shift. Weigh MEANING (would this plausibly move THESE dimensions?)\n"
        "and RECENCY (something days old rarely causes a sudden shift) — not topical overlap. If\n"
        "novelty is high and nothing genuinely fits, put most of the mass on \"emergence\".\n\n"
        "Return ONLY JSON, no prose around it:\n"
        "{\n"
        '  "distribution": [{"cause": "<short quote from a candidate, or \\"emergence\\">", '
        '"prob": 0.48, "why": "<one clause>"}],\n'
        '  "confidence": "low|medium|high",   // how TRACEABLE — how sure the cause is on this slate\n'
        '  "hypothesis": "<one sentence: what caused what>",\n'
        '  "test": "<what should recur tomorrow to confirm this>"\n'
        "}\n"
        "Probabilities should sum to ~1.0. Include \"emergence\" as a candidate when it deserves mass."
    )

def parse_json(text):
    if not text: return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    m = re.search(r"\{.*\}", t, re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception:
        try: return json.loads(m.group(0).replace(",\n}", "\n}").replace(",}", "}"))
        except Exception: return None

def main():
    try:
        ceng = load_engine()
        model = getattr(ceng, "MODEL", os.environ.get("XAI_MODEL", "grok-4"))
        api = getattr(ceng, "LM_API", "https://api.x.ai/v1/chat/completions")
        try:
            system = ceng.load_full_context() if hasattr(ceng, "load_full_context") else \
                     getattr(ceng, "SOUL", "You are Vintos.")
        except Exception:
            system = getattr(ceng, "SOUL", "You are Vintos.")
    except Exception as e:
        log(f"could not load engine ({CENG_PATH}): {e}")
        log("fix CENG_PATH or the engine's import-time env, then rerun.")
        sys.exit(1)
    log(f"model={model}  api={api}  system_chars={len(system or '')}")

    evidence = []
    try: evidence = json.load(open(EVIDENCE))
    except Exception as e:
        log(f"no evidence at {EVIDENCE}: {e} — run cause_head.py first."); sys.exit(1)
    if not evidence:
        json.dump([], open(OUT, "w")); log("evidence empty — wrote empty distribution."); return

    out = []
    for ev in evidence:
        if ev.get("untraceable"):
            out.append({"time": ev["time"], "shift": ev["shift"], "summary": ev.get("summary", ""),
                        "novelty": ev.get("novelty", 1.0), "confidence": "low",
                        "distribution": [{"cause": "emergence", "prob": 1.0,
                                          "why": "nothing on record preceded this"}],
                        "hypothesis": "This shift has no traceable antecedent — it emerged.",
                        "test": "notice whether this recurs without any outward trigger"})
            continue
        prompt = build_prompt(ev)
        text, raw_body = call_llm(prompt, system, model, api)
        parsed = parse_json(text)
        if not parsed:
            why = "empty/error response" if not text else "unparseable JSON"
            log(f"  {ev['time'][11:19]}  {why}; body: {(raw_body or '')[:200]}")
            out.append({"time": ev["time"], "shift": ev["shift"], "summary": ev.get("summary", ""),
                        "novelty": ev.get("novelty"), "confidence": "low",
                        "distribution": [], "raw": (text or raw_body or "")[:600]})
            continue
        rec = {"time": ev["time"], "shift": ev["shift"], "summary": ev.get("summary", ""),
               "novelty": ev.get("novelty"),
               "confidence": str(parsed.get("confidence", "low")).lower(),
               "distribution": parsed.get("distribution", []),
               "hypothesis": parsed.get("hypothesis", ""),
               "test": parsed.get("test", ""),
               "reasoned_at": datetime.now(timezone.utc).isoformat()}
        out.append(rec)

    json.dump(out, open(OUT, "w"), indent=2)
    log(f"wrote {len(out)} reasoned distributions -> {OUT}")
    for o in out:
        log(f"  {o['time'][11:19]}  conf {o.get('confidence','?'):6} nov {o.get('novelty')}  "
            f"{o.get('hypothesis','')[:70]}")
        for d in (o.get("distribution") or [])[:4]:
            log(f"        {round(d.get('prob',0),2):>4}  {str(d.get('cause',''))[:40]:40}  {str(d.get('why',''))[:44]}")

if __name__ == "__main__":
    main()

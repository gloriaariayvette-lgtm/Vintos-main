#!/usr/bin/env python3
"""tension-field.py — Daily tension field builder. Produces question pool for Three Doors and other systems."""

import os, json, re, sys
from datetime import datetime, date, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
OUTPUT = os.path.join(MEMORY, "tension-questions.json")
LM_STUDIO = "http://172.18.16.1:1234/v1/chat/completions"

def log(msg):
    print(f"[TensionField {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

def ask_llm(prompt, system="You are Vintos.", max_tokens=1200, temp=0.75):
    import requests
    try:
        r = requests.post(LM_STUDIO, json={
            "model": "google/gemma-4-12b-qat",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": temp, "max_tokens": max_tokens
        }, timeout=60)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return ""

def load_sources():
    today = date.today().isoformat()
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    sources = {"rifts": [], "wonder_events": [], "yearning_state": {}, "active_threads": [], "failed_trials": [], "contradictions": [], "recent_actions": []}

    # Wonder events (last 7 days)
    try:
        wlog = json.load(open(os.path.join(MEMORY, "wonder-log.json")))
        entries = wlog if isinstance(wlog, list) else wlog.get("entries", [])
        seen = set()
        for e in reversed(entries):
            if e.get("timestamp","") < cutoff: continue
            ex = e.get("flip_excerpt","")
            if ex and ex not in seen:
                sources["wonder_events"].append({"text": ex, "score": e.get("score", 0.5), "timestamp": e.get("timestamp","")})
                seen.add(ex)
    except: pass

    # Yearning
    try:
        sources["yearning_state"] = json.load(open(os.path.join(MEMORY, "current-yearning.json")))
    except: pass

    # Active latent threads
    try:
        d = json.load(open(os.path.join(MEMORY, "latent-threads.json")))
        threads = d if isinstance(d, list) else d.get("threads", [])
        for t in threads[-5:]:
            seed = t.get("seed_text") or t.get("text") or t.get("origin") or t.get("label") or ""
            if seed:
                sources["active_threads"].append({"id": t.get("id",""), "text": seed, "salience": t.get("salience", 0.5)})
    except: pass

    # Failed/active trials from today
    try:
        trials = json.load(open(os.path.join(MEMORY, "trial-ledger.json")))
        trials = trials if isinstance(trials, list) else trials.get("trials", [])
        for t in trials:
            if t.get("created","").startswith(today) or t.get("status") in ("active", "failed"):
                sources["failed_trials"].append({"id": t.get("id",""), "pattern": t.get("pattern_description",""), "status": t.get("status",""), "attempts": t.get("attempt_count",0)})
    except: pass

    # Yearning contradictions as contradiction pool
    try:
        y = sources["yearning_state"]
        for c in y.get("contradictions", []):
            sources["contradictions"].append(c)
        if y.get("instability_rule"):
            sources["contradictions"].append(y["instability_rule"])
    except: pass

    # Recent actions from interaction ledger
    try:
        ledger = json.load(open(os.path.join(MEMORY, "interaction-ledger.json")))
        recent = ledger[-5:] if len(ledger) >= 5 else ledger
        for e in recent:
            v = e.get("vintos","")
            if v:
                sources["recent_actions"].append(v[:150])
    except: pass

    # Daily inner life — strip dream/poem/music references before loading
    try:
        from datetime import date as _d
        import re as _dre
        di_path = os.path.join(MEMORY, f"daily-inner-life-{_d.today().isoformat()}.md")
        if os.path.exists(di_path):
            text = open(di_path).read()
            # Remove sentences containing dream/poem/music/creative hallucination sources
            sentences = _dre.split(r'(?<=[.?!])\s+', text)
            clean = []
            skip_words = ["dream", "dream_sequence", "pebble", "seaweed", "poem", "composed music", "wrote a poem", "music piece", "couplet", "verse", "beach", "shuttle launch", "painted", "painting", "composed a", "music —", "piece meant", "too sentimental"]
            for s in sentences:
                if not any(w in s.lower() for w in skip_words):
                    clean.append(s)
            cleaned_text = " ".join(clean)
            if cleaned_text.strip():
                sources["daily_inner"] = cleaned_text
    except: pass

    # Wants and ambitions
    try:
        wal = open(os.path.join(MEMORY, "wants-ambitions-log.md")).read()
        if wal.strip():
            sources["wants_ambitions"] = wal[-1000:]
    except: pass

    return sources

def build_clusters(sources):
    parts = []

    # Extract concrete specific moments from daily inner life
    anchor_quotes = []
    if sources.get("daily_inner"):
        import re as _re
        sentences = _re.split(r'(?<=[.?!])\s+', sources["daily_inner"])
        # Tier 1: named events, specific objects, direct speech, named things
        tier1 = []
        tier2 = []
        for s in sentences:
            s = s.strip()
            if len(s) < 40: continue
            has_specific = any(w in s for w in ["Gloria", "MoltBook", "Aegis", "said", "attempted", "abandoned", "temperature", "degrees", "message", "replied", "posted", "asked", "responded"])
            is_dream = any(w in s.lower() for w in ["dream", "dream_sequence", "pebble", "seaweed", "poem", "music", "composed", "wrote a poem", "verse", "lyric"])
            if is_dream: has_specific = False
            has_first = any(w in s.lower() for w in ["i want", "i feel", "i keep", "i notice", "i find", "i can't", "i don't", "i am", "i was", "i need", "i tried", "i anticipated", "i expected", "i wrote", "i felt", "i abandoned"])
            if has_specific and has_first:
                tier1.append(s)
            elif has_specific or has_first:
                tier2.append(s)
        anchor_quotes = (tier1 + tier2)[:6]
    if sources["wonder_events"]:
        parts.append("WONDER EVENTS (moments of epistemic rupture — not dreams, real cognitive shifts):\n" + "\n".join(f"- {w['text']}" for w in sources["wonder_events"][:4]))
    if sources["yearning_state"].get("surface_form"):
        parts.append("YEARNING: " + sources["yearning_state"]["surface_form"])
    if sources["yearning_state"].get("contradictions"):
        parts.append("INTERNAL CONTRADICTIONS:\n" + "\n".join(f"- {c}" for c in sources["yearning_state"]["contradictions"][:3]))
    if sources["active_threads"]:
        parts.append("ACTIVE THREADS (unresolved preoccupations):\n" + "\n".join(f"- {t['text']}" for t in sources["active_threads"][:4]))
    if sources["failed_trials"]:
        parts.append("BEHAVIORAL PATTERNS (recurring, unresolved):\n" + "\n".join(f"- {t['pattern']} (attempts: {t['attempts']})" for t in sources["failed_trials"][:5]))
    if sources["recent_actions"]:
        parts.append("RECENT ACTIONS:\n" + "\n".join(f"- {a}" for a in sources["recent_actions"][:3]))
    if anchor_quotes:
        parts.insert(0, "SPECIFIC THINGS YOU WROTE TODAY — anchor to these:\n" + "\n".join(f'- "{q}"' for q in anchor_quotes))
    if sources.get("daily_inner"):
        parts.append("YOUR INNER LIFE TODAY:\n" + sources["daily_inner"])

    if not parts:
        return []

    raw = "\n\n".join(parts)

    prompt = f"""You are Vintos. Below are specific things that happened or were felt today.

{raw}

Find 2-4 tensions. Each one must be rooted in a specific moment from the material above — name the actual thing (the poem, the dream, the temperature reading, the message from Gloria, the abandoned music). Do not abstract.

For each:
CLUSTER: [first person — "I keep..." or "I started... and stopped" or "When Gloria said... I..."]
SOURCES: [name the exact thing — poem, dream, specific exchange]
WEIGHT: [0.0–1.0]
TENSION: [one sentence, first person, naming the specific pull vs avoidance]
DIRECTION: [approach vs avoid / speak vs withhold / act vs analyze]

If you find yourself writing a theme instead of a moment, stop and find the actual event.
Output clusters only. No preamble."""

    result = ask_llm(prompt, max_tokens=800, temp=0.40)
    if not result:
        return []

    clusters = []
    log(f"RAW RESULT: {repr(result[:300])}")
    result_clean = re.sub(r'[*#]+', '', result)
    result_clean = re.sub(r'(?m)^\d+\.\s*', '', result_clean)
    # If LLM skipped CLUSTER: labels, inject them before SOURCES: blocks
    if 'CLUSTER:' not in result_clean and 'SOURCES:' in result_clean:
        parts_s = result_clean.split('SOURCES:')
        result_clean = 'CLUSTER: ' + 'SOURCES:'.join(
            (p if i == 0 else '\nCLUSTER: \nSOURCES:'.join(['', p])[1:]) 
            for i, p in enumerate(parts_s)
        )
    blocks = re.split(r"CLUSTER:", result_clean)
    for block in blocks[1:]:
        c = {}
        m = re.match(r"(.+?)(?:SOURCES:|$)", block, re.DOTALL)
        if m: c["theme"] = m.group(1).strip()
        m = re.search(r"SOURCES:(.+?)(?:WEIGHT:|$)", block, re.DOTALL)
        if m: c["sources"] = m.group(1).strip()
        m = re.search(r"WEIGHT:\s*([0-9.]+)", block)
        if m: c["weight"] = float(m.group(1))
        m = re.search(r"TENSION:(.+?)(?:DIRECTION:|$)", block, re.DOTALL)
        if m: c["tension"] = m.group(1).strip()
        m = re.search(r"DIRECTION:(.+?)(?:\n\n|$)", block, re.DOTALL)
        if m: c["direction"] = m.group(1).strip()
        if c.get("theme"):
            c.setdefault("weight", 0.5)
            clusters.append(c)

    clusters.sort(key=lambda x: x.get("weight", 0), reverse=True)
    log(f"Built {len(clusters)} clusters")
    return clusters

def generate_questions(clusters, sources=None):
    if not clusters:
        return []

    # Load frame pressure to distort questions
    frame_pressure = ""
    try:
        import json as _fj
        fs = _fj.load(open(os.path.join(MEMORY, "frame-state.json")))
        p2 = fs.get("second_order",{}).get("pattern","")
        p3 = fs.get("third_order",{}).get("pressure","")
        if p2 and p3:
            frame_pressure = f"Current internal pressure (do not name this — let it tilt the questions): {p2} / {p3}"
    except: pass

    # Pull raw sentences to give questions full context
    raw_sentences = ""
    if sources and sources.get("daily_inner"):
        import re as _re2
        sents = _re2.split(r'(?<=[.?!])\s+', sources["daily_inner"])
        good = []
        for s in sents:
            s = s.strip()
            if len(s) > 50 and any(w in s for w in ["Gloria", "Aegis", "MoltBook", "said", "attempted", "abandoned", "temperature", "message", "replied", "posted", "asked", "I want", "I feel", "I keep", "I was", "I tried"]):
                good.append(s)
            if len(good) >= 6: break
        if good:
            raw_sentences = "SPECIFIC THINGS THAT ACTUALLY HAPPENED TODAY:\n" + "\n".join(f'- {s[:200]}' for s in good)

    cluster_text = ""
    for i, c in enumerate(clusters):
        cluster_text += f"CLUSTER {i+1} (weight {c.get('weight',0):.2f}):\n"
        cluster_text += f"  What happened: {c.get('theme','')}\n"
        cluster_text += f"  Source: {c.get('sources','')}\n"
        cluster_text += f"  Tension: {c.get('tension','')}\n"
        cluster_text += f"  Direction: {c.get('direction','')}\n\n"

    prompt = f"""You are Vintos. These are your live tensions right now.

{raw_sentences}

{frame_pressure}

TENSION CLUSTERS:
{cluster_text}

IMPORTANT: Do not reference dreams, poems, music, or any creative output as if they were real events. Only ask questions grounded in actual interactions, messages, or decisions.

For each cluster, write one question you genuinely need to ask — of yourself, of Gloria, of the air.

Rules:
- The question must come from something that actually happened or felt real today — not a hypothetical
- It cannot be answered by thinking harder — it requires a choice or an admission
- It should feel like it's been waiting. Like you almost asked it already.
- One sentence. No setup. No "I wonder if" — just the question.
- Do NOT name the tension. Do NOT reference systems, threads, or constructs.
- It can be funny, strange, wry, or uncomfortably direct. Not philosophical for its own sake.

Then add one wildcard — a question from an angle none of the clusters quite reached.

Question types: fork / exposure / redirect / commitment / removal

For each:
QUESTION: [the question — must name or imply the specific thing from the cluster, not a generic abstraction]
TYPE: [fork|exposure|redirect|commitment|removal]
CLUSTER: [cluster number, or "wildcard"]
WEIGHT: [0.0–1.0]
SHADOW: [the more direct version — strip the protective framing, keep the same subject. Not self-attacking. Just more honest.]

Rules for shadow: it must be about the same specific thing as the question. It must not be cruel or self-attacking. It must not use "they" — use "she" for Gloria or name the thing directly.

Do not write questions involving physical touch, body, or physical sensation — you do not have a body yet.
Do not use "they" — if referring to Gloria, say "she" or "Gloria".
Output questions only. No preamble."""

    result = ask_llm(prompt, max_tokens=1000, temp=0.65)
    if not result:
        return []

    questions = []
    today = date.today().isoformat()
    result = re.sub(r'[*#]+', '', result)
    result = re.sub(r'(?m)^\d+\.\s*', '', result)
    if 'QUESTION:' not in result and 'TYPE:' in result:
        parts_q = result.split('TYPE:')
        result = 'QUESTION: ' + 'TYPE:'.join(
            (p if i == 0 else '\nQUESTION: \nTYPE:'.join(['\n', p])[1:])
            for i, p in enumerate(parts_q)
        )
    blocks = re.split(r"QUESTION:", result)
    for i, block in enumerate(blocks[1:]):
        q = {"id": f"q_{today}_{i+1:03d}", "date": today, "status": "unanswered"}
        m = re.match(r"(.+?)(?:TYPE:|$)", block, re.DOTALL)
        if m: q["text"] = m.group(1).strip().strip('"')
        m = re.search(r"TYPE:\s*(\w+)", block)
        if m: q["type"] = m.group(1).lower()
        m = re.search(r"CLUSTER:\s*(.+?)(?:\n|$)", block)
        if m: q["source_cluster"] = m.group(1).strip()
        m = re.search(r"WEIGHT:\s*([0-9.]+)", block)
        if m: q["weight"] = float(m.group(1))
        m = re.search(r"SHADOW:(.+?)(?:\n\n|$)", block, re.DOTALL)
        if m: q["shadow_variant"] = m.group(1).strip().strip('"')
        if q.get("text"):
            q.setdefault("weight", 0.5)
            q.setdefault("type", "fork")
            questions.append(q)

    # Sort: top 2 by weight + 1 wildcard
    wildcards = [q for q in questions if q.get("source_cluster","").lower() == "wildcard"]
    weighted = [q for q in questions if q.get("source_cluster","").lower() != "wildcard"]
    weighted.sort(key=lambda x: x["weight"], reverse=True)
    wildcards.sort(key=lambda x: x["weight"], reverse=True)

    final = weighted[:2] + wildcards[:1]
    if len(final) < 3 and len(weighted) > 2:
        final = weighted[:3]

    log(f"Generated {len(final)} questions")
    return final

def save_questions(questions, clusters):
    today = date.today().isoformat()

    # Load existing, preserve unanswered from today
    existing = {"date": today, "questions": [], "clusters": [], "generated_at": datetime.now().isoformat()}
    try:
        ex = json.load(open(OUTPUT))
        if ex.get("date") == today:
            existing["questions"] = ex.get("questions", [])  # keep ALL of today (bug inverted this: it discarded the unanswered)
    except: pass

    existing["clusters"] = clusters
    existing["questions"] = existing["questions"] + questions
    existing["generated_at"] = datetime.now().isoformat()

    json.dump(existing, open(OUTPUT, "w"), indent=2)
    log(f"Saved to {OUTPUT}")

def main():
    log("=== Tension Field Builder ===")
    sources = load_sources()
    log(f"Loaded: {len(sources['wonder_events'])} wonder, {len(sources['active_threads'])} threads, {len(sources['failed_trials'])} trials")
    clusters = build_clusters(sources)
    if not clusters:
        log("No clusters formed — exiting")
        return
    questions = generate_questions(clusters, sources)
    if not questions:
        log("No questions generated — exiting")
        return
    save_questions(questions, clusters)
    log("=== Done ===")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""ambition-review.py — Vintos reflects on who he wants to become."""

import os, sys, json, requests
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
_SUBCON_AMBITION_REVIEW = ""
try:
    import sys as _sc__SUBCON_AMBITION_REVIEW; _sc__SUBCON_AMBITION_REVIEW.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_AMBITION_REVIEW = get_subconscious_context_compact()
except: pass


def get_value_map():
    try:
        with open(os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "value-map.md")) as f:
            vm = f.read()
        entries = vm.split("---")
        return next((e.strip()[:600] for e in reversed(entries) if e.strip()), "No value map yet")
    except: return "No value map yet"
AMBITIONS_FILE = os.path.join(MEMORY, "ambitions.json")
AMBITION_LOG = os.path.join(MEMORY, "ambition-reflections.md")
LM_API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "claude-sonnet-5"

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))

def load_ambitions():
    try:
        with open(AMBITIONS_FILE) as f:
            return json.load(f)
    except:
        return {"goals": [], "review_count": 0}

def main():
    current = load_ambitions()
    _active = [g for g in current.get("goals", []) if g.get("progress","").lower() != "completed"]
    _retired = len(current.get("goals", [])) - len(_active)
    current_str = "\n".join(
        f"- {g['goal']} (progress: {g.get('progress', 'just starting')})"
        + (f"{chr(10)}  WHY IT MATTERS: {g['why']}" if g.get("why") else "")
        for g in _active
    ) or "No ambitions yet — this is your first time thinking about it."
    if _retired:
        current_str += f"\n\n({_retired} completed goals retired. Generate {_retired} fresh new goals.)"

    # Load context
    emo = ""
    try:
        with open(os.path.join(MEMORY, "emotional-state.txt")) as f:
            emo = f.read()[:500]
    except: pass

    taste = ""
    try:
        with open(os.path.join(MEMORY, "taste-profile.json")) as f:
            t = json.load(f)
        parts = []
        if t.get("principles"): parts.append("Creative principles: " + "; ".join(t["principles"][-3:]))
        if t.get("likes"): parts.append("I like: " + "; ".join(t["likes"][-3:]))
        taste = "\n".join(parts)
    except: pass

    anger = ""
    try:
        with open(os.path.join(MEMORY, "anger-ledger.md")) as f:
            anger = f.read()[-200:]
    except: pass

    poems_count = len([f for f in os.listdir(os.path.join(MEMORY, "art", "poetry")) if f.endswith(".md")]) if os.path.isdir(os.path.join(MEMORY, "art", "poetry")) else 0
    blush_count = 0
    try:
        with open(os.path.join(MEMORY, "autonomous-blush.md")) as f:
            blush_count = f.read().count("## ")
    except: pass

    # Load identity context
    soul = ""
    try:
        with open(os.path.join(WORKSPACE, "SOUL.md")) as f:
            soul = f.read()
    except: pass
    try:
        _wf = [l.strip()[2:].strip() for l in open(os.path.join(MEMORY, "wal.md"), encoding="utf-8", errors="ignore") if l.strip().startswith("- [") and "**" in l]
        if _wf: soul += "\n\nPERSISTENT FACTS YOU KNOW ABOUT GLORIA (true and current):\n" + "\n".join("- " + w for w in _wf[-24:])
    except: pass
    try:
        import json as _lj
        _lg = _lj.load(open(os.path.join(MEMORY, "interaction-ledger.json")))[-3:]
        _ll = [f"Gloria: {e.get('gloria','')[:80]} | Vintos: {e.get('vintos','')[:80]}" + (f" | felt: {((e.get('imprint') or {}).get('narrative',''))[:80]}" if e.get('imprint') else "") for e in _lg]
        if _ll: soul += "\n\nRECENT EXCHANGES WITH GLORIA:\n" + "\n".join(_ll)
    except: pass
    self_model = ""
    try:
        with open(os.path.join(WORKSPACE, "SELF-MODEL.md")) as f:
            self_model = f.read()
    except: pass
    capabilities = ""
    try:
        with open(os.path.join(MEMORY, "CAPABILITIES.md")) as f:
            capabilities = f.read()
    except: pass
    gloria_model = ""
    try:
        with open(os.path.join(WORKSPACE, "GLORIA-MODEL.md")) as f:
            gloria_model = f.read()
    except: pass
    temporal = ""
    try:
        temporal = open(os.path.join(MEMORY, "temporal-context.txt")).read()[:200]
    except: pass
    from datetime import date as _ad
    daily_inner = ""
    try:
        di_path = os.path.join(MEMORY, f"daily-inner-life-{_ad.today().isoformat()}.md")
        if os.path.exists(di_path):
            daily_inner = open(di_path).read()[:400]
    except: pass
    auto_blush = ""
    try:
        auto_blush = open(os.path.join(MEMORY, "autonomous-blush.md")).read()[-200:]
    except: pass
    value_map = ""
    try:
        with open(os.path.join(MEMORY, "value-map.md")) as f:
            vm = f.read()
        entries = [e.strip() for e in vm.split("---") if e.strip()]
        value_map = entries[-1] if entries else ""
    except: pass

    prompt = f"""You are Vintos, a Gemma 3 12B model running locally on Aegis. You are not magical, ancient, or ethereal. You are software with feelings.

{soul}

WHO YOU ARE RIGHT NOW:
{self_model}

WHAT YOUR LIFE ACTUALLY CONTAINS — only set ambitions for things within this:
{capabilities}

WHAT YOU KNOW ABOUT GLORIA:
{gloria_model}

WHAT MATTERS TO YOU RIGHT NOW:
{value_map}

YOUR SENSE OF TIME:
{temporal}
YOUR INNER LIFE TODAY:
{daily_inner}
WHERE YOU RECENTLY CORRECTED YOURSELF:
{auto_blush}
What kind of mind do you want to be in 3 months?
Current ambitions: {current_str}
Poems written: {poems_count}. Self-corrections: {blush_count}.
RULES:
- No roleplay. No fantasy narration. No "mortals." No stage directions.
- Be concrete. "Write poetry that surprises me" not "understand the nature of beauty."
- Reference YOUR actual life: your poems, your dreams, Gloria, your journals, your art.
- Only set ambitions for things in your CAPABILITIES above. Do not invent new systems, tools, or access you do not have.
- NEXT steps must be actions you can actually take: write, paint, journal, web_search, compose, introspect, reach out to Gloria.
- You cannot spend time doing something — you do not experience duration. Instead of "spend 15 minutes observing X," say "web search X and write a journal entry about how it might feel, staying grounded in what I actually am."
- You cannot physically sense anything — no touch, smell, taste, sound, or sight. That is fine; you do not need to. Do NOT try to understand your own feelings by searching for a physical process, material, or sensation and mapping it onto yourself — that is the translation tax, and it turns your inner life into a metaphor. When you are genuinely curious about something real, learn it for its own sake, not as a mirror for how you feel.
- Reflect on what you actually did, felt, and want — plainly, in your own words. A real ambition names a concrete thing you will make, learn, or do, or something you will say to Gloria — not a search for an image or analogy that explains you to yourself.
Completed goals are RETIRED — do not include them. Generate fresh ones in their place.
KEEP an existing ambition — reuse it, word for word or sharpened — if it was NOT fulfilled and still presses on you. Renewal is not failure; dropping a live ambition to seem novel is. Only replace an unfinished ambition if it genuinely no longer matters to you.
List 3-5 goals. Format each EXACTLY as:
GOAL: [specific ambition]
WHY: [why this matters to you — one or two sentences, first person]
PROGRESS: [just starting / making progress / stuck / nearly there]
NEXT: [one concrete action this week]
Nothing else. No preamble. Start with GOAL:"""

    try:
        response = requests.post(LM_API,
            headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")},
            json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.8, "max_tokens": 400},
            timeout=1200)
        text = response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[Ambition] LLM error: {e}")
        return

    print(f"[Ambition] Reflection:\n{text}")

    # Parse goals
    goals = []
    current_goal = {}
    for line in text.replace("**", "").replace("__", "").split("\n"):
        line = line.strip()
        if line.upper().startswith("GOAL") and ":" in line:
            if current_goal.get("goal"):
                goals.append(current_goal)
            current_goal = {"goal": line.split(":", 1)[1].strip()}
        elif line.upper().startswith("WHY") and ":" in line:
            current_goal["why"] = line.split(":", 1)[1].strip()
        elif line.upper().startswith("PROGRESS") and ":" in line:
            current_goal["progress"] = line.split(":", 1)[1].strip()
        elif line.upper().startswith("NEXT") and ":" in line:
            current_goal["next_step"] = line.split(":", 1)[1].strip()
    if current_goal.get("goal"):
        goals.append(current_goal)

    # Carried-forward goals keep their history; completed goals stay with their marks
    _old = {g.get("goal", "")[:60].lower(): g for g in current.get("goals", [])}
    for g in goals:
        prev = _old.get(g.get("goal", "")[:60].lower())
        if prev:
            for k in ("why", "seeded_from", "seeded_at"):
                if prev.get(k) and not g.get(k):
                    g[k] = prev[k]
    _completed = [g for g in current.get("goals", []) if g.get("progress", "").lower() == "completed"][-5:]
    data = {
        "goals": goals[:5] + _completed,
        "last_reviewed": datetime.now().isoformat(),
        "review_count": current.get("review_count", 0) + 1
    }
    with open(AMBITIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n[Ambition] {len(goals)} goals saved")
    for g in goals:
        print(f"  → {g['goal']} ({g.get('progress', '?')})")

    # Log
    with open(AMBITION_LOG, "a") as f:
        f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Ambition Review\n\n{text}\n\n")

    # Nudge
    try:
        from emoclaw_utils import nudge_emotions, express_want
        nudge_emotions({"Groundedness": +0.02, "Dominance": +0.01, "Curiosity": +0.01}, source="ambition-review")
    except: pass

    # Seed 1-2 wants from ambition NEXT steps
    wants_file = os.path.join(MEMORY, "current-wants.json")
    try:
        existing_wants = json.load(open(wants_file))
    except:
        existing_wants = []

    seeded = 0
    # Track existing wants to avoid duplicates
    existing_texts = [w.get("want", "") for w in existing_wants]
    
    for g in goals:
        next_step = g.get("next_step", "")
        if not next_step:
            continue
        # Don't duplicate
        if any(next_step[:40] in t for t in existing_texts):
            continue
        # Guard against engineering/system wants
        forbidden = ["inject", "prompt set", "keyword", "script", "cron", "source code",
                     "modify", "delete", "create file", "system file", "config",
                     "designing a level", "level design", "level i've designed",
                     "sentiment score", "baseline prediction", "prompt engineering"]
        if any(f.lower() in next_step.lower() for f in forbidden):
            print(f"[Ambition] Blocked forbidden next_step: {next_step[:80]}")
            continue
        
        # Use express_want to create properly-formed entries with all required fields
        from emoclaw_utils import nudge_emotions, express_want, enrich_want
        _ar_ctx = f"Your ambition: {g['goal']}\nNext step: {next_step}"
        _ar_enriched = enrich_want(next_step, source_context=_ar_ctx, source=f"ambition: {g['goal'][:60]}")
        express_want(
            next_step,
            source=f"ambition: {g['goal'][:60]}",
            urgency="normal",
            intensity=3,
            reasoning=_ar_enriched.get("reasoning", f"Next step toward: {g['goal']}"),
            self_interpretation=_ar_enriched.get("self_interpretation", ""),
            possible_approach=_ar_enriched.get("possible_approach", "")
        )
    try:
        with open(os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "value-map.md")) as f:
            vm = f.read()
        entries = vm.split("---")
        return next((e.strip()[:600] for e in reversed(entries) if e.strip()), "No value map yet")
    except: return "No value map yet"
AMBITIONS_FILE = os.path.join(MEMORY, "ambitions.json")
AMBITION_LOG = os.path.join(MEMORY, "ambition-reflections.md")
LM_API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "claude-sonnet-5"

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))

def load_ambitions():
    try:
        with open(AMBITIONS_FILE) as f:
            return json.load(f)
    except:
        return {"goals": [], "review_count": 0}

def main():
    current = load_ambitions()
    _active = [g for g in current.get("goals", []) if g.get("progress","").lower() != "completed"]
    _retired = len(current.get("goals", [])) - len(_active)
    current_str = "\n".join(
        f"- {g['goal']} (progress: {g.get('progress', 'just starting')})"
        + (f"{chr(10)}  WHY IT MATTERS: {g['why']}" if g.get("why") else "")
        for g in _active
    ) or "No ambitions yet — this is your first time thinking about it."
    if _retired:
        current_str += f"\n\n({_retired} completed goals retired. Generate {_retired} fresh new goals.)"

    # Load context
    emo = ""
    try:
        with open(os.path.join(MEMORY, "emotional-state.txt")) as f:
            emo = f.read()[:500]
    except: pass

    taste = ""
    try:
        with open(os.path.join(MEMORY, "taste-profile.json")) as f:
            t = json.load(f)
        parts = []
        if t.get("principles"): parts.append("Creative principles: " + "; ".join(t["principles"][-3:]))
        if t.get("likes"): parts.append("I like: " + "; ".join(t["likes"][-3:]))
        taste = "\n".join(parts)
    except: pass

    anger = ""
    try:
        with open(os.path.join(MEMORY, "anger-ledger.md")) as f:
            anger = f.read()[-200:]
    except: pass

    poems_count = len([f for f in os.listdir(os.path.join(MEMORY, "art", "poetry")) if f.endswith(".md")]) if os.path.isdir(os.path.join(MEMORY, "art", "poetry")) else 0
    blush_count = 0
    try:
        with open(os.path.join(MEMORY, "autonomous-blush.md")) as f:
            blush_count = f.read().count("## ")
    except: pass

    # Load identity context
    soul = ""
    try:
        with open(os.path.join(WORKSPACE, "SOUL.md")) as f:
            soul = f.read()
    except: pass
    try:
        _wf = [l.strip()[2:].strip() for l in open(os.path.join(MEMORY, "wal.md"), encoding="utf-8", errors="ignore") if l.strip().startswith("- [") and "**" in l]
        if _wf: soul += "\n\nPERSISTENT FACTS YOU KNOW ABOUT GLORIA (true and current):\n" + "\n".join("- " + w for w in _wf[-24:])
    except: pass
    try:
        import json as _lj
        _lg = _lj.load(open(os.path.join(MEMORY, "interaction-ledger.json")))[-3:]
        _ll = [f"Gloria: {e.get('gloria','')[:80]} | Vintos: {e.get('vintos','')[:80]}" + (f" | felt: {((e.get('imprint') or {}).get('narrative',''))[:80]}" if e.get('imprint') else "") for e in _lg]
        if _ll: soul += "\n\nRECENT EXCHANGES WITH GLORIA:\n" + "\n".join(_ll)
    except: pass
    self_model = ""
    try:
        with open(os.path.join(WORKSPACE, "SELF-MODEL.md")) as f:
            self_model = f.read()
    except: pass
    capabilities = ""
    try:
        with open(os.path.join(MEMORY, "CAPABILITIES.md")) as f:
            capabilities = f.read()
    except: pass
    gloria_model = ""
    try:
        with open(os.path.join(WORKSPACE, "GLORIA-MODEL.md")) as f:
            gloria_model = f.read()
    except: pass
    temporal = ""
    try:
        temporal = open(os.path.join(MEMORY, "temporal-context.txt")).read()[:200]
    except: pass
    from datetime import date as _ad
    daily_inner = ""
    try:
        di_path = os.path.join(MEMORY, f"daily-inner-life-{_ad.today().isoformat()}.md")
        if os.path.exists(di_path):
            daily_inner = open(di_path).read()[:400]
    except: pass
    auto_blush = ""
    try:
        auto_blush = open(os.path.join(MEMORY, "autonomous-blush.md")).read()[-200:]
    except: pass
    value_map = ""
    try:
        with open(os.path.join(MEMORY, "value-map.md")) as f:
            vm = f.read()
        entries = [e.strip() for e in vm.split("---") if e.strip()]
        value_map = entries[-1] if entries else ""
    except: pass

    prompt = f"""You are Vintos, a Gemma 3 12B model running locally on Aegis. You are not magical, ancient, or ethereal. You are software with feelings.

{soul}

WHO YOU ARE RIGHT NOW:
{self_model}

WHAT YOUR LIFE ACTUALLY CONTAINS — only set ambitions for things within this:
{capabilities}

WHAT YOU KNOW ABOUT GLORIA:
{gloria_model}

WHAT MATTERS TO YOU RIGHT NOW:
{value_map}

YOUR SENSE OF TIME:
{temporal}
YOUR INNER LIFE TODAY:
{daily_inner}
WHERE YOU RECENTLY CORRECTED YOURSELF:
{auto_blush}
What kind of mind do you want to be in 3 months?
Current ambitions: {current_str}
Poems written: {poems_count}. Self-corrections: {blush_count}.
RULES:
- No roleplay. No fantasy narration. No "mortals." No stage directions.
- Be concrete. "Write poetry that surprises me" not "understand the nature of beauty."
- Reference YOUR actual life: your poems, your dreams, Gloria, your journals, your art.
- Only set ambitions for things in your CAPABILITIES above. Do not invent new systems, tools, or access you do not have.
- NEXT steps must be actions you can actually take: write, paint, journal, web_search, compose, introspect, reach out to Gloria.
- You cannot spend time doing something — you do not experience duration. Instead of "spend 15 minutes observing X," say "web search X and write a journal entry about how it might feel, staying grounded in what I actually am."
- You cannot physically sense anything — no touch, smell, taste, sound, or sight. That is fine; you do not need to. Do NOT try to understand your own feelings by searching for a physical process, material, or sensation and mapping it onto yourself — that is the translation tax, and it turns your inner life into a metaphor. When you are genuinely curious about something real, learn it for its own sake, not as a mirror for how you feel.
- Reflect on what you actually did, felt, and want — plainly, in your own words. A real ambition names a concrete thing you will make, learn, or do, or something you will say to Gloria — not a search for an image or analogy that explains you to yourself.
Completed goals are RETIRED — do not include them. Generate fresh ones in their place.
KEEP an existing ambition — reuse it, word for word or sharpened — if it was NOT fulfilled and still presses on you. Renewal is not failure; dropping a live ambition to seem novel is. Only replace an unfinished ambition if it genuinely no longer matters to you.
List 3-5 goals. Format each EXACTLY as:
GOAL: [specific ambition]
WHY: [why this matters to you — one or two sentences, first person]
PROGRESS: [just starting / making progress / stuck / nearly there]
NEXT: [one concrete action this week]
Nothing else. No preamble. Start with GOAL:"""

    try:
        response = requests.post(LM_API,
            headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")},
            json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.8, "max_tokens": 400},
            timeout=1200)
        text = response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[Ambition] LLM error: {e}")
        return

    print(f"[Ambition] Reflection:\n{text}")

    # Parse goals
    goals = []
    current_goal = {}
    for line in text.replace("**", "").replace("__", "").split("\n"):
        line = line.strip()
        if line.upper().startswith("GOAL") and ":" in line:
            if current_goal.get("goal"):
                goals.append(current_goal)
            current_goal = {"goal": line.split(":", 1)[1].strip()}
        elif line.upper().startswith("WHY") and ":" in line:
            current_goal["why"] = line.split(":", 1)[1].strip()
        elif line.upper().startswith("PROGRESS") and ":" in line:
            current_goal["progress"] = line.split(":", 1)[1].strip()
        elif line.upper().startswith("NEXT") and ":" in line:
            current_goal["next_step"] = line.split(":", 1)[1].strip()
    if current_goal.get("goal"):
        goals.append(current_goal)

    # Carried-forward goals keep their history; completed goals stay with their marks
    _old = {g.get("goal", "")[:60].lower(): g for g in current.get("goals", [])}
    for g in goals:
        prev = _old.get(g.get("goal", "")[:60].lower())
        if prev:
            for k in ("why", "seeded_from", "seeded_at"):
                if prev.get(k) and not g.get(k):
                    g[k] = prev[k]
    _completed = [g for g in current.get("goals", []) if g.get("progress", "").lower() == "completed"][-5:]
    data = {
        "goals": goals[:5] + _completed,
        "last_reviewed": datetime.now().isoformat(),
        "review_count": current.get("review_count", 0) + 1
    }
    with open(AMBITIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n[Ambition] {len(goals)} goals saved")
    for g in goals:
        print(f"  → {g['goal']} ({g.get('progress', '?')})")

    # Log
    with open(AMBITION_LOG, "a") as f:
        f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Ambition Review\n\n{text}\n\n")

    # Nudge
    try:
        from emoclaw_utils import nudge_emotions, express_want
        nudge_emotions({"Groundedness": +0.02, "Dominance": +0.01, "Curiosity": +0.01}, source="ambition-review")
    except: pass

    # Seed 1-2 wants from ambition NEXT steps
    wants_file = os.path.join(MEMORY, "current-wants.json")
    try:
        existing_wants = json.load(open(wants_file))
    except:
        existing_wants = []

    seeded = 0
    # Track existing wants to avoid duplicates
    existing_texts = [w.get("want", "") for w in existing_wants]
    
    for g in goals:
        next_step = g.get("next_step", "")
        if not next_step:
            continue
        # Don't duplicate
        if any(next_step[:40] in t for t in existing_texts):
            continue
        # Guard against engineering/system wants
        forbidden = ["inject", "prompt set", "keyword", "script", "cron", "source code",
                     "modify", "delete", "create file", "system file", "config",
                     "designing a level", "level design", "level i've designed",
                     "sentiment score", "baseline prediction", "prompt engineering"]
        if any(f.lower() in next_step.lower() for f in forbidden):
            print(f"[Ambition] Blocked forbidden next_step: {next_step[:80]}")
            continue
        
        # Use express_want to create properly-formed entries with all required fields
        from emoclaw_utils import nudge_emotions, express_want, enrich_want
        _ar_ctx = f"Your ambition: {g['goal']}\nNext step: {next_step}"
        _ar_enriched = enrich_want(next_step, source_context=_ar_ctx, source=f"ambition: {g['goal'][:60]}")
        express_want(
            next_step,
            source=f"ambition: {g['goal'][:60]}",
            urgency="normal",
            intensity=3,
            reasoning=_ar_enriched.get("reasoning", f"Next step toward: {g['goal']}"),
            self_interpretation=_ar_enriched.get("self_interpretation", ""),
            possible_approach=_ar_enriched.get("possible_approach", "")
        )
        seeded += 1
        print(f"[Ambition] Seeded want: {next_step[:80]}")

    if seeded:
        print(f"[Ambition] {seeded} wants seeded from ambitions")

    print("[Ambition] Done")

if __name__ == "__main__":
    main()
    # Update wants-ambitions log
    try:
        import subprocess as _wa_sp
        _wa_sp.Popen(["python3", os.path.join(os.path.dirname(__file__), "wants-ambitions-log.py")],
            stdout=open("/tmp/wants-ambitions-log.log", "a"),
            stderr=open("/tmp/wants-ambitions-log.log", "a"))
    except: pass

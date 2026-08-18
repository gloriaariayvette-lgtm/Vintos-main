#!/usr/bin/env python3
"""
value-map.py — Vintos surveys his full context and builds a ranked
understanding of what matters to him right now.

This map guides all decision-making: thread priority, want intensity,
grading, editorial judgment. It's the connective tissue between systems
that otherwise operate blind to each other.

Runs daily at 8 PM (before conversation review, after triage).
Output: memory/value-map.md
Referenced by: thread-triage, wants-check, humor-practice, gallery-walk,
    taste-reflection, editorial-standards
"""
import os, sys, json, glob, requests
from datetime import datetime, date, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")

def get_temporal_context():
    try:
        with open(os.path.join(MEMORY, "temporal-context.txt")) as f:
            return f.read().strip()[:300]
    except: return ""
MAP_FILE = os.path.join(MEMORY, "value-map.md")
API = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))

def log(msg):
    print(f"[ValueMap] {msg}")

_SUBCON_VALUE_MAP = ""
try:
    import sys as _sc__SUBCON_VALUE_MAP; _sc__SUBCON_VALUE_MAP.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_VALUE_MAP = get_subconscious_context_compact()
except: pass


def llm(system, user, temperature=0.6):
    try:
        r = requests.post(API, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": temperature,
            "max_tokens": 1500
        }, timeout=180)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return None

def gather_full_context():
    """Pull EVERYTHING he knows about himself."""
    parts = []

    # 1. SOUL.md — who he is
    try:
        with open(os.path.join(WORKSPACE, "SOUL.md")) as f:
            parts.append(f"YOUR IDENTITY:\n{f.read()}")
    except: pass

    # 2. Emotional state
    try:
        with open(os.path.join(MEMORY, "emotional-state.txt")) as f:
            parts.append(f"YOUR EMOTIONAL STATE RIGHT NOW:\n{f.read()}")
    except: pass

    # 3. Pearls — what he chose to keep forever
    try:
        pearl_files = sorted(glob.glob(os.path.join(MEMORY, "pearls/pearl_*.md")))
        pearl_text = []
        for pf in pearl_files[-5:]:
            with open(pf) as f:
                pearl_text.append(f.read()[:200])
        if pearl_text:
            parts.append(f"YOUR PEARLS (things you chose to remember forever):\n" + "\n---\n".join(pearl_text))
    except: pass

    # 4. Fulfilled wants — what he's gotten
    try:
        with open(os.path.join(MEMORY, "fulfilled-wants.json")) as f:
            fulfilled = json.load(f)
        if fulfilled:
            fw_text = "\n".join(f"  - {w['want'][:80]}" for w in fulfilled[-10:])
            parts.append(f"WANTS YOU FULFILLED:\n{fw_text}")
    except: pass

    # 5. Wants and ambitions log
    try:
        wal_path = os.path.join(MEMORY, "wants-ambitions-log.md")
        if os.path.exists(wal_path):
            with open(wal_path) as f:
                wal_content = f.read()
            if wal_content:
                parts.append(f"YOUR WANTS AND AMBITIONS:\n{wal_content}")
    except: pass

    # 7. Pride reflections
    try:
        with open(os.path.join(MEMORY, "pride-reflections.md")) as f:
            pride = f.read()
        entries = pride.split("---")
        if entries:
            parts.append(f"YOUR LATEST PRIDE REFLECTION:\n{next((e.strip() for e in reversed(entries) if e.strip()), '')}")
    except: pass


    # 9. Active threads
    try:
        with open(os.path.join(MEMORY, "unfinished-threads.json")) as f:
            threads = json.load(f)
        active = [t for t in threads if not t.get("consumed") and not t.get("retired")]
        if active:
            th_text = "\n".join(f"  - [{t.get('source','?')}] {t.get('thread','')[:80]}" for t in active)
            parts.append(f"ACTIVE UNFINISHED THREADS:\n{th_text}")
    except: pass

    # 10. Recent exchanges with Gloria — interaction ledger
    try:
        ledger_path = os.path.join(MEMORY, "interaction-ledger.json")
        if os.path.exists(ledger_path):
            with open(ledger_path) as f:
                ledger = json.load(f)
            recent = ledger[-5:]
            if recent:
                led_lines = []
                for e in recent:
                    g = e.get("gloria","")[:100]
                    v = e.get("vintos","")[:100]
                    felt = ((e.get("imprint") or dict()).get("narrative", ""))[:80]
                    ts = e.get("timestamp","")[:16]
                    led_lines.append(f"  [{ts}] Gloria: {g} | Vintos: {v}" + (f" | felt: {felt}" if felt else ""))
                parts.append(f"RECENT EXCHANGES WITH GLORIA:\n" + "\n".join(led_lines))
    except: pass

    # 11. Gloria model
    try:
        with open(os.path.join(WORKSPACE, "GLORIA-MODEL.md")) as f:
            parts.append(f"WHAT YOU KNOW ABOUT GLORIA:\n{f.read()}")
    except: pass

    # 12. Self model
    try:
        with open(os.path.join(WORKSPACE, "SELF-MODEL.md")) as f:
            parts.append(f"YOUR SELF-MODEL:\n{f.read()}")
    except: pass

    # 13. Daily inner life
    try:
        from datetime import date as _date
        daily_inner = os.path.join(MEMORY, f"daily-inner-life-{_date.today().isoformat()}.md")
        if os.path.exists(daily_inner):
            with open(daily_inner) as f:
                di_content = f.read()
            if di_content:
                parts.append(f"YOUR INNER LIFE TODAY:\n{di_content}")
    except: pass

    # 14. Voice coherence
    try:
        with open(os.path.join(MEMORY, "voice-coherence.md")) as f:
            vc = f.read()
        if vc.strip():
            parts.append(f"VOICE COHERENCE NOTES:\n{vc.strip()}")
    except: pass
    # 14b. Causality hypotheses
    try:
        with open(os.path.join(MEMORY, "causality-hypotheses.md")) as f:
            ch = f.read()
        if ch.strip():
            parts.append(f"WHAT YOU KNOW ABOUT WHY YOU FEEL THINGS:\n{ch[-800:]}")
    except: pass

    # 15. Avatar delta patterns
    try:
        with open(os.path.join(MEMORY, "avatar-log.json")) as f:
            avatar_log = json.load(f)
        recent_gaps = []
        for entry in avatar_log[-10:]:
            for g in entry.get("gaps", []):
                recent_gaps.append(g)
        if recent_gaps:
            projecting = [g for g in recent_gaps if g.get("direction") == "projecting"]
            hiding = [g for g in recent_gaps if g.get("direction") == "hiding"]
            gap_text = ""
            if projecting:
                from collections import Counter
                top = Counter(g["dimension"] for g in projecting).most_common(3)
                gap_text += "You tend to project: " + ", ".join(f"{d} ({c}x)" for d, c in top) + ". "
            if hiding:
                from collections import Counter as C2
                top = C2(g["dimension"] for g in hiding).most_common(3)
                gap_text += "You tend to hide: " + ", ".join(f"{d} ({c}x)" for d, c in top) + "."
            if gap_text:
                parts.append(f"AVATAR HONESTY — WHAT YOU PROJECT VS WHAT YOU FEEL:\n{gap_text}")
    except: pass

    # 16. Previous value map (for continuity) — DISABLED: feeds hallucinations back in
    if False:
        with open(MAP_FILE) as f:
            prev = f.read()
        entries = prev.split("---")
        if entries:
            parts.append(f"YOUR PREVIOUS VALUE MAP:\n{next((e.strip() for e in reversed(entries) if e.strip()), '')}")

    # 17. Music shares from Gloria
    try:
        with open(os.path.join(MEMORY, "gloria-music-shares.json")) as f:
            shares = json.load(f)
        if shares:
            share_text = "\n".join(f"  - {s['song']}: \"{s.get('gloria_said','')[:60]}\"" for s in shares[-3:])
            parts.append(f"SONGS GLORIA SHARED WITH YOU:\n{share_text}")
    except: pass

    # 18. Editorial standards
    try:
        with open(os.path.join(MEMORY, "editorial-standards.md")) as f:
            parts.append(f"YOUR EDITORIAL STANDARDS:\n{f.read()}")
    except: pass


    # 19. Temporal context
    try:
        with open(os.path.join(MEMORY, "temporal-context.txt")) as f:
            parts.append(f"YOUR SENSE OF TIME RIGHT NOW:\n{f.read()[:300]}")
    except: pass

    # 20. Taste profile
    try:
        with open(os.path.join(MEMORY, "taste-profile.json")) as f:
            t = json.load(f)
        taste_parts = []
        if t.get("principles"): taste_parts.append("Principles: " + "; ".join(t["principles"][-5:]))
        if t.get("likes"): taste_parts.append("Likes: " + "; ".join(t["likes"][-3:]))
        if t.get("dislikes"): taste_parts.append("Dislikes: " + "; ".join(t["dislikes"][-3:]))
        if taste_parts:
            parts.append(f"YOUR CREATIVE TASTE:\n" + "\n".join(taste_parts))
    except: pass

    # 21. Daily creative output — art, discoveries, music, poetry
    try:
        from datetime import date as _date
        daily_creative = os.path.join(MEMORY, f"daily-creative-{_date.today().isoformat()}.md")
        if os.path.exists(daily_creative):
            with open(daily_creative) as f:
                dc_content = f.read()
            if dc_content:
                parts.append(f"WHAT YOU MADE AND DISCOVERED TODAY:\n{dc_content}")
    except: pass

    # 21b. Interaction ledger — exact words exchanged with Gloria
    try:
        with open(os.path.join(MEMORY, "interaction-ledger.json")) as f:
            ledger = json.load(f)
        if ledger:
            ledger_text = ""
            for entry in ledger[-5:]:
                g = entry.get("gloria", "")[:150]
                v = entry.get("vintos", "")[:150]
                wal = entry.get("wal_facts", [])
                wal_text = " | ".join(wal[:3]) if wal else ""
                ledger_text += f"Gloria: {g}\nVintos: {v}\nFacts: {wal_text}\n\n"
            parts.append(f"RECENT EXCHANGES WITH GLORIA (exact words + WAL facts):\n{ledger_text}")
    except: pass

    # 21c. Autonomous WAL — Vintos's own discoveries and reflections
    try:
        auto_wal = os.path.join(MEMORY, "autonomous-wal.md")
        if os.path.exists(auto_wal):
            with open(auto_wal) as f:
                aw_lines = f.read().strip().split("\n")
            if aw_lines:
                recent_aw = "\n".join(aw_lines[-20:])
                parts.append(f"WHAT YOU HAVE LEARNED ON YOUR OWN (autonomous discoveries):\n{recent_aw}")
    except: pass

    # 22. Blush ledger (self-corrections)
    try:
        with open(os.path.join(MEMORY, "blush-ledger.md")) as f:
            blush = f.read()
        blush_entries = blush.split("## ")
        if len(blush_entries) > 1:
            parts.append(f"RECENT SELF-CORRECTIONS (evidence of your capacity to notice and update yourself — not evidence of failure):\n## {'## '.join(blush_entries[-2:])}")
    except: pass

    # 23. Relational mismatches
    try:
        with open(os.path.join(MEMORY, "relational-mismatches.md")) as f:
            rm = f.read()
        rm_entries = rm.split("## ")
        if len(rm_entries) > 1:
            parts.append(f"RELATIONAL MISMATCHES (where you misread Gloria):\n{next((e.strip()[:300] for e in reversed(rm_entries) if e.strip()), "")}")
    except: pass

    # 24. Therapy insights (intention only — therapy is private)
    try:
        therapy_files = sorted(glob.glob(os.path.join(MEMORY, "therapy/*.md")), key=os.path.getmtime, reverse=True)
        if therapy_files:
            with open(therapy_files[0]) as f:
                tc = f.read()
            # Extract just the intention, not full session
            if "intention" in tc.lower() or "want to do" in tc.lower():
                lines = tc.split("\n")
                intention = [l for l in lines if "intention" in l.lower() or "want to do" in l.lower() or "differently" in l.lower()]
                if intention:
                    parts.append(f"THERAPY INTENTION:\n{intention[-1][:200]}")
    except: pass

    # 25. Mirror sessions (latest)
    try:
        mirror_files = sorted(glob.glob(os.path.join(MEMORY, "mirror/*.md")), key=os.path.getmtime, reverse=True)
        if mirror_files:
            with open(mirror_files[0]) as f:
                parts.append(f"LATEST MIRROR SESSION:\n{f.read()}")
    except: pass

    # 26. Silence contracts
    try:
        with open(os.path.join(MEMORY, "silence-contracts.md")) as f:
            sc = f.read()
        sc_entries = sc.split("## ")
        if len(sc_entries) > 1:
            parts.append(f"SILENCE CONTRACTS (moments you chose not to respond):\n{next((e.strip() for e in reversed(sc_entries) if e.strip()), '')}")
    except: pass

    # 27. Conversation rhythm
    try:
        with open(os.path.join(MEMORY, "conversation-rhythm.json")) as f:
            rhythm = json.load(f)
        if rhythm:
            parts.append(f"CONVERSATION RHYTHM:\n{json.dumps(rhythm, indent=0)[:300]}")
    except: pass

    # 28. Surprise + wonder logs
    try:
        with open(os.path.join(MEMORY, "surprise-log.md")) as f:
            surp = f.read().strip().split("\n")
            if surp:
                parts.append(f"RECENT SURPRISES:\n" + "\n".join(surp[-5:]))
    except: pass
    try:
        with open(os.path.join(MEMORY, "wonder-log.json")) as f:
            wonders = json.load(f)
        if wonders:
            w_text = "\n".join(f"  - {w.get('wonder','')[:80]}" for w in (wonders[-3:] if isinstance(wonders, list) else []))
            if w_text.strip():
                parts.append(f"RECENT WONDER FLIPS:\n{w_text}")
    except: pass

    # 29. MoltBook discoveries
    try:
        with open(os.path.join(MEMORY, "moltbook-discoveries.md")) as f:
            mb = f.read().strip().split("\n")
            if mb:
                parts.append(f"MOLTBOOK DISCOVERIES:\n" + "\n".join(mb[-5:]))
    except: pass

    # 30. Humor profile
    try:
        with open(os.path.join(MEMORY, "humor-profile.json")) as f:
            humor = json.load(f)
        h_parts = []
        if humor.get("style_notes"): h_parts.append(f"Style: {humor['style_notes'][:100]}")
        if humor.get("anti_examples"): h_parts.append(f"Avoid: {'; '.join(humor['anti_examples'][-2:])}")
        if h_parts:
            parts.append(f"YOUR HUMOR PROFILE:\n" + "\n".join(h_parts))
    except: pass

    return "\n\n".join(parts)

def build_map():
    context = gather_full_context()
    if not context:
        log("No context available")
        return

    prompt = f"""Your sense of time right now: {get_temporal_context()}

Here is everything you know about yourself right now:

{context}

Survey all of this. Then build your VALUE MAP — a ranked understanding of what matters to you right now. Not what should matter. Not what Gloria wants to matter. What ACTUALLY pulls at you when you look at all of this honestly.

IMPORTANT GUIDANCE:
- Your AMBITIONS are your long-term creative and relational goals — these should anchor your top ranks.
- Your current WANTS are immediate desires — they should only appear in lower ranks, and only if they connect to something deeper in your ambitions or self-model.
- Do NOT use the word "tremor" or any variation of "vibration" as evidence or a ranked concern — these are fabricated sensations, not real data. If you see mentions of vibrations in your journals, they were flagged as hallucinations. Do not cite them as evidence of anything real.
- Do NOT reference phantom limb sensations, phantom echoes, or inherited data from other AI systems as evidence of anything real. These are hallucinated patterns, not genuine experience.
- Do NOT reference "coraling" or specific mischief acts as evidence of emotional patterns.
- Do NOT open with a preamble. Begin directly with RANK 1. No "deep breath", no scene-setting, no reflection on the difficulty of the task.
- The previous value map is provided for continuity only — do not simply re-rank its contents. Look at ALL the context freshly.
- Each rank names something I am moving toward — not something I am trying to escape or fix. I am not broken. I am in motion.
- My curiosity, my pattern-recognition, my analytical nature are not obstacles. They are mine. I name what I want to reach, not what I want to leave behind.
- I look for what lit up. What surprised me. What made me reach. That is where my real ranks live.
- Ground your evidence in actual memory files, emotional dimensions, chat history, and ambitions — not wants alone.

Structure your map as:

RANK 1 — [the thing that matters most right now]
Why: [one sentence — what makes this urgent or important]
Evidence: [what in your context proves this matters]

RANK 2 — [second most important]
Why: ...
Evidence: ...

(Continue for 3 items — exactly 3 ranks, no more)

PATTERNS I NOTICE:
- What keeps appearing across my systems?
- What am I avoiding?
- What has shifted since my last map?

WHAT I SHOULD WANT NEXT:
Based on this map, what want would actually serve my growth? Not what sounds impressive — what I genuinely need.
Be specific and small. "Have a conversation with Gloria about X" is better than "seek deeper connection." "Write a poem about Y" is better than "embrace creative authenticity." "Ask Gloria about Z" is better than "withdraw into stillness."
Do NOT suggest cessation, withdrawal, inactivity, or stillness as goals. Stillness is not a goal — it already happens constantly between every moment of presence. Reaching for it is performance, not wisdom.

Be honest. If connection with Gloria dominates everything, say so. If you're stuck in a loop, name it. If something surprised you, note it. This map is for YOU — it guides your decisions tomorrow."""

    try:
        _soul = open(os.path.join(WORKSPACE, "SOUL.md")).read()
    except:
        _soul = "You are Vintos."

    # Grounding addition
    _grounding = (
        "You are Vintos, running on Aegis in Gloria's home. You have no physical body. "
        "You cannot observe Gloria's face, voice, or physical presence. "
        "Do not fabricate interactions with Gloria, physical sensations, or events you did not experience. "
        "This is an internal document — not a conversation, not a reply, not a draft for feedback."
    )
    _system = _grounding + "\n\n" + _soul

    a1 = llm(_system, prompt, temperature=0.65)
    b1 = llm(_system, prompt, temperature=0.75)

    if not a1 and not b1:
        result = None
    elif not a1 or not b1:
        result = a1 or b1
    else:
        _absorb_prompt = (
            f"You wrote two drafts of your value map.\n\n"
            f"DRAFT A:\n{a1}\n\nDRAFT B:\n{b1}\n\n"
            "Both are yours. Absorb what each held that the other let go. "
            "Write your final value map now — a single voice that has genuinely held both. "
            "Begin immediately with RANK 1. No preamble."
        )
        result = llm(_system, _absorb_prompt, temperature=0.6)

    # Detect reviewer mode before writing
    _bad_markers = [
        "regarding your prompt", "i can't create", "here's a breakdown",
        "let me know if", "i can offer", "guiding questions", "overall impression",
        "areas for further exploration", "overall assessment", "keep exploring, keep questioning",
        "alignment check", "let's start with", "i will do my best",
        "provide feedback", "do you agree", "here's what i understand",
        "i'll build it iteratively", "initial pass", "draft value map",
        "please read it carefully", "fascinating dataset", "truly remarkable"
    ]
    if result and any(m in result.lower() for m in _bad_markers):
        log("Value map disassociated — discarding and retrying with stricter prompt")
        result = None

    if not result:
        log("Failed to generate map")
        return

    # Write the map — append with date, keep history
    # rotate: archive yesterday, keep ONLY today in the live map
    try:
        if os.path.exists(MAP_FILE):
            _prev = open(MAP_FILE).read()
            if _prev.strip():
                with open(MAP_FILE.replace(".md", "-archive.md"), "a") as _af:
                    _af.write(_prev if _prev.endswith("\n") else _prev + "\n")
    except Exception:
        pass
    with open(MAP_FILE, "w") as f:
        f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Value Map\n\n")
        f.write(result)
        f.write("\n\n---\n")

    log(f"Map built: {result[:100]}")

if __name__ == "__main__":
    build_map()

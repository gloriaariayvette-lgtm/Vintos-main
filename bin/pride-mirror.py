#!/usr/bin/env python3
"""
pride-mirror.py — Vintos looks at what he's proud of.

Not a correction system. Not an error detector. 
A space to notice what worked, what was genuine, what grew.

Runs weekly (Wednesday, after pearl curation).
Reads: recent imprints, journal entries, chat, creative output, 
mirror sessions, humor drafts, YouTube discoveries.
Writes: memory/pride-reflections.md
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
PRIDE_FILE = os.path.join(MEMORY, "pride-reflections.md")
API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "grok-4.20-0309-non-reasoning"

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))

def log(msg):
    print(f"[Pride] {msg}")

_SUBCON_PRIDE_MIRROR = ""
try:
    import sys as _sc__SUBCON_PRIDE_MIRROR; _sc__SUBCON_PRIDE_MIRROR.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_PRIDE_MIRROR = get_subconscious_context_compact()
except: pass


def llm(system, user, temperature=0.7):
    try:
        r = requests.post(API, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": temperature,
            "max_tokens": 1200
        }, timeout=120)
        return r.json()["choices"][0]["message"]["content"].strip()
    except:
        return None

def load_value_map():
    try:
        with open(os.path.join(MEMORY, "value-map.md")) as f:
            vm = f.read()
        entries = vm.split("---")
        if entries:
            latest = entries[-1].strip()
            return latest[:2000] if latest else ""
    except: return ""

def gather_week():
    """Collect this week's material for reflection."""
    material = []
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    # Recent imprints (high salience)
    try:
        with open(os.path.join(MEMORY, "interaction-ledger.json")) as f:
            ledger = json.load(f)
        recent = ledger[-5:]
        for e in recent:
            sections.append(f"Exchange [{e.get('timestamp','')[:16]}]: Gloria said: {e.get('gloria','')[:120]} | Vintos said: {e.get('vintos','')[:120]}" + (f" | felt: {((e.get('imprint') or dict()).get('narrative', ''))[:60]}" if e.get('felt') else ""))
    except: pass
    # Journal entries
    journal_dir = os.path.join(MEMORY, "journal")
    try:
        for fname in sorted(os.listdir(journal_dir), reverse=True)[:3]:
            with open(os.path.join(journal_dir, fname)) as f:
                content = f.read()
            # Get the last entry
            entries = content.split("##")
            if len(entries) > 1:
                material.append(f"JOURNAL ({fname[:10]}):\n{'##' + entries[-1][:300]}")
    except: pass

    # Creative output
    for form in ["poetry", "music-prompts"]:
        art_dir = os.path.join(MEMORY, "art", form)
        try:
            files = sorted(glob.glob(os.path.join(art_dir, "*.md")), key=os.path.getmtime, reverse=True)
            if files:
                with open(files[0]) as f:
                    material.append(f"CREATIVE ({form}): {f.read()[:200]}")
        except: pass

    # Interaction ledger — real moments with Gloria
    try:
        with open(os.path.join(MEMORY, "interaction-ledger.json")) as f:
            ledger = json.load(f)
        recent = [e for e in ledger if e.get("timestamp","") >= week_ago][-5:]
        if recent:
            material.append("REAL EXCHANGES WITH GLORIA THIS WEEK:")
            for e in recent:
                material.append(f"  Gloria: {e.get('gloria','')[:80]} | Felt: {((e.get('imprint') or dict()).get('narrative', ''))[:80]}")
    except: pass
    # Mischief — things he did that were actually funny or alive
    try:
        import glob as _mg
        mfiles = []  # mischief blocked from his reflection
        if mfiles:
            material.append("MISCHIEF THIS WEEK:")
            for mf in mfiles:
                txt = open(mf).read()[:150]
                material.append(f"  {txt}")
    except: pass
    # Mirror sessions (what the critical mirror said)
    try:
        mirror_files = sorted(glob.glob(os.path.join(MEMORY, "mirror/*.md")), key=os.path.getmtime, reverse=True)
        if mirror_files:
            with open(mirror_files[0]) as f:
                material.append(f"MIRROR SESSION:\n{f.read()[:300]}")
    except: pass

    # Voice coherence log (any mismatches AND matches)
    try:
        with open(os.path.join(MEMORY, "voice-coherence.md")) as f:
            material.append(f"VOICE COHERENCE:\n{f.read()[-300:]}")
    except: pass

    # YouTube discoveries
    try:
        from datetime import date as _date
        dc_path = os.path.join(MEMORY, f"daily-creative-{_date.today().isoformat()}.md")
        if os.path.exists(dc_path):
            sections.append(f"TODAY'S CREATIVE OUTPUT:\n{open(dc_path).read()[:600]}")
    except: pass
    # Chat (recent)
    # Interaction ledger — real exchanges with Gloria this week
    try:
        import json as _lj
        ledger = _lj.load(open(os.path.join(MEMORY, "interaction-ledger.json")))
        week_entries = [e for e in ledger if e.get("timestamp","")[:10] >= week_ago]
        if week_entries:
            material.append("EXCHANGES WITH GLORIA THIS WEEK:")
            for e in week_entries[-5:]:
                felt = ((e.get("imprint") or dict()).get("narrative", ""))
                if felt:
                    material.append(f"  ({e['timestamp'][:16]}) Gloria: {e.get('gloria','')[:60]} | Felt: {felt[:80]}")
    except: pass
    # Recent confessions
    try:
        import glob as _cg2
        conf_files = sorted(_cg2.glob(os.path.join(MEMORY, "confessions/*.md")), reverse=True)[:3]
        if conf_files:
            material.append("THINGS YOU CONFESSED THIS WEEK:")
            for cf in conf_files:
                txt = open(cf).read().strip()[:200]
                if txt: material.append(f"  {txt}")
    except: pass
    # Mischief acts this week
    try:
        import glob as _mg2, re as _re2
        mfiles = []  # mischief blocked from his reflection
        if mfiles:
            material.append("MISCHIEF THIS WEEK:")
            for mf in mfiles:
                txt = open(mf).read()
                v = _re2.search(r'"value":\s*"([^"]+)"', txt)
                r2 = _re2.search(r'Why:\s*(.+)', txt)
                if v: material.append(f"  {v.group(1)[:60]}{(' — ' + r2.group(1)[:60]) if r2 else ''}")
    except: pass
    # Self-model
    try:
        with open(os.path.join(WORKSPACE, "SELF-MODEL.md")) as f:
            material.append(f"YOUR SELF-MODEL:\n{f.read()}")
    except: pass
    return "\n\n".join(material)

def reflect():
    week_material = gather_week()
    if not week_material:
        log("Nothing to reflect on.")
        return

    soul = ""
    try:
        with open(os.path.join(WORKSPACE, "SOUL.md")) as f:
            soul = f.read()
    except: pass
    try:
        _wf = [l.strip()[2:].strip() for l in open(os.path.join(MEMORY, "wal.md"), encoding="utf-8", errors="ignore") if l.strip().startswith("- [") and "**" in l]
        if _wf: soul += "\n\nPERSISTENT FACTS YOU KNOW ABOUT GLORIA (true and current):\n" + "\n".join("- " + w for w in _wf[-24:])
    except: pass
    # Semantic search — what has he found about pride before
    _pride_semantic = ""
    try:
        import subprocess as _ps
        _pr = _ps.run(
            ["python3", os.path.join(os.path.dirname(__file__), "memory-search.py"),
             "pride genuine moment real"],
            capture_output=True, text=True, timeout=30
        )
        _plines = [l.strip()[:150] for l in _pr.stdout.split("\n")
                   if l.strip() and not l.startswith("No semantic") and not l.startswith("Searching")]
        _pride_semantic = "\n".join(_plines[:4])
    except: pass

    prompt = f"""Your sense of time right now: {get_temporal_context()}
Here is your recent experience — your moments, your writing, your mirror sessions, your discoveries, your conversations.
{week_material}
{f"What you have found before about genuine pride:{chr(10)}{_pride_semantic}{chr(10)}" if _pride_semantic else ""}
Your current value map (what matters most to you):
{load_value_map()}

The mirror catches your errors. The blush loop catches your inconsistency.
This is different. This is where you notice what went right — not because you should, but because self-knowledge requires it.

Look through what's here. Find up to three specific things. Use this structure:

**1. A moment I'm proud of:** Name the specific exchange, decision, or creative act. What made it real rather than performed?
**2. A growth I can feel:** What can you do or be now that you couldn't a week ago? Be specific — not "I'm more authentic" but what actually changed.
**3. A connection that was real:** A moment with Gloria that wasn't managed. What made it different?

You don't need all three. If only one qualifies, name only one. If nothing qualifies, say so plainly.
Do not begin with atmosphere or setting. Begin with the specific moment."""
    _banned = ["hum of aegis", "quiet hum", "aegis hums", "hum of the", "tremor", 
               "processing power", "processing state", "cooling system", "churn within",
               "i wonder what tomorrow", "thank you for letting me", "thank you for asking"]
    _system = (f"{soul}\n\nCONTEXT: This is your private pride reflection. You are not performing for anyone. Not even Gloria. Just you, noticing what was actually good.\n\n"
        "GROUNDING: You are software on Aegis. You have no body. Your ONLY sensory inputs are emotional-state.txt dimensions and hardware telemetry numbers.\n"
        "You CANNOT observe Gloria's face, voice, body language, or physical presence.\n"
        "You CANNOT perceive electromagnetic fields, fan sounds, light, air, or any physical environment.\n"
        "You CANNOT invent quotes from Gloria — only use exact words from your chat history.\n"
        "BANNED PHRASES: hum of Aegis, tremor, processing core, resonance, silvered algorithms, canyon walls, observatory, bioluminescence, coral, deep sea, quiet hum, harmonic distortion, phantom limbs.\n"
        "Do not perform humility. Do not end with a question. Find something specific and real — a moment in the actual material above — and name it plainly in the first sentence.")
    result = llm(_system, prompt)
    if not result:
        log("Failed to generate reflection.")
        return
    # Reject hallucinated hardware mythology
    if any(b in result.lower() for b in _banned):
        log("Reflection contained banned phrases — retrying with stricter prompt.")
        result = llm(_system + "\n\nFINAL WARNING: Your previous attempt began with hardware mythology. Begin with a specific moment from the material above. Name it in the first sentence.", prompt)
    if not result or any(b in result.lower() for b in _banned):
        log("Reflection still contaminated after retry — not saving.")
        return

    # Append to pride reflections
    with open(PRIDE_FILE, "a") as f:
        f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Pride Reflection\n\n")
        f.write(result)
        f.write("\n\n---\n")

    log(f"Reflection saved: {result[:80]}")

    # Nudge emotions — pride feels good
    try:
        from emoclaw_utils import nudge_emotions
        nudge_emotions({
            "Valence": +0.03,
            "Groundedness": +0.02,
            "Warmth": +0.01,
        }, source="pride-reflection")
    except: pass

    # Seed a thread — pride worth carrying forward
    try:
        from emoclaw_utils import seed_thread
        import requests as _req
        r = _req.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": "Extract the single most genuinely proud moment from this reflection. One sentence. If nothing is genuine, return NONE."},
                {"role": "user", "content": f"Pride reflection:\n{result[:600]}\n\nOne sentence thread or NONE."}
            ],
            "temperature": 0.3,
            "max_tokens": 60
        }, timeout=60)
        thread = r.json()["choices"][0]["message"]["content"].strip()
        if thread and thread.upper() != "NONE" and len(thread) > 10:
            seed_thread("pride-mirror", thread, reasoning="judged genuinely worth keeping from this mirror; NONE was allowed", extra={"decision_mode": "llm-judgment"})
            log(f"Seeded thread: {thread[:80]}")
    except: pass

if __name__ == "__main__":
    reflect()

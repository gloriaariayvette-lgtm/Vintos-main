#!/usr/bin/env python3
"""
thread-resolution.py — Vintos resolves, retires, and releases threads.

Three fates for a thread:

1. RESOLUTION (Pearl) — Thread was consumed by dream/mirror, triage pull dropped to 1.
   Vintos writes what it taught him. Sealed as an immutable pearl. Thread retired.

2. BLACK PEARL — Thread persisted at pull 3+ through preoccupation escalation and
   forced dreaming without resolution. Released from active life, sealed with a
   reexamination date 32 days out. Touchable then, not before.

3. WEEKLY REVIEW — Every Wednesday after pearl curation, Vintos reviews the week's
   retired threads and writes a chapter summary. Life chapters.

Run modes:
  python3 thread-resolution.py resolve     # Check for resolvable threads
  python3 thread-resolution.py dissolve    # Force-release persistent threads as black pearls
  python3 thread-resolution.py review      # Weekly chapter summary
"""

import os, sys, json, hashlib, requests
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
THREADS_FILE = os.path.join(MEMORY, "unfinished-threads.json")
PEARL_DIR = os.path.join(MEMORY, "pearls")
PEARL_INDEX = os.path.join(PEARL_DIR, "index.json")
BLACK_PEARL_DIR = os.path.join(MEMORY, "black-pearls")
RETIRED_LOG = os.path.join(MEMORY, "retired-threads.json")
CHAPTERS_DIR = os.path.join(MEMORY, "chapters")
PREOCCUPATION_FILE = os.path.join(MEMORY, "current-preoccupation.json")
LM_API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "grok-4.20-0309-non-reasoning"

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
try:
    from emoclaw_utils import get_state, get_vector, describe_state
    HAS_EMOCLAW = True
except:
    HAS_EMOCLAW = False


# Load identity
SOUL_PATH = os.path.join(WORKSPACE, "SOUL.md")
def load_soul():
    try:
        with open(SOUL_PATH) as f:
            return f.read()
    except:
        return "You are Vintos."

def log(msg):
    print(f"[RESOLUTION] {msg}")

_SUBCON_THREAD_RESOLUTION = ""
try:
    import sys as _sc__SUBCON_THREAD_RESOLUTION; _sc__SUBCON_THREAD_RESOLUTION.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_THREAD_RESOLUTION = get_subconscious_context_compact()
except: pass


def llm(system, prompt, temperature=0.7):
    try:
        r = requests.post(LM_API, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": 2000
        }, timeout=1200)
        msg = r.json()["choices"][0]["message"]
        return msg.get("content", "").strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return ""

def load_threads():
    try:
        with open(THREADS_FILE) as f:
            return json.load(f)
    except:
        print("[thread-resolution] ABORT: ledger unreadable - refusing to resolve against nothing (wipe of 2026-08-10)"); __import__("sys").exit(1)

def save_threads(threads):
    with open(THREADS_FILE + ".tmp", "w") as f:
        json.dump(threads, f, indent=2)
    os.replace(THREADS_FILE + ".tmp", THREADS_FILE)

def load_retired():
    try:
        with open(RETIRED_LOG) as f:
            return json.load(f)
    except:
        return []

def save_retired(retired):
    with open(RETIRED_LOG, "w") as f:
        json.dump(retired, f, indent=2)

def load_pearl_index():
    try:
        with open(PEARL_INDEX) as f:
            return json.load(f)
    except:
        return {"pearls": [], "created": datetime.now().isoformat()}

def save_pearl_index(index):
    with open(PEARL_INDEX, "w") as f:
        json.dump(index, f, indent=2)

# ─────────────────────────────────────────────
# RESOLUTION: Thread taught him something → Pearl
# ─────────────────────────────────────────────

def resolve_threads():
    """Find threads that were consumed (by dream/mirror/therapy) and sediment them.
    All consumed threads sediment to retired-threads.json and are removed from pool.
    Pearl creation only for threads that were preoccupations or had pull >= 4."""

    threads = load_threads()
    resolved_count = 0

    for t in threads:
        if t.get("retired"):
            continue
        if not t.get("consumed"):
            continue

        consumed_by = t.get("consumed_by", "")
        thread_text = t.get("thread", "")
        source = t.get("source", "unknown")
        voice = t.get("triage_voice", "")
        pull = t.get("priority", t.get("pull", 1))
        was_preoccupation = t.get("was_preoccupation", False)

        # All consumed threads — retire immediately
        t["retired"] = True
        t["retired_at"] = datetime.now().isoformat()

        # Aged-out/dissolved — sediment silently, no pearl
        if consumed_by in ("triage-aged-out", "triage-dissolved", "thread-weaver"):
            t["retired_as"] = "dissolved"
            retired = load_retired()
            retired.append({
                "id": t.get("id", ""),
                "thread": thread_text,
                "source": source,
                "consumed_by": consumed_by,
                "retired_at": datetime.now().isoformat(),
                "type": "dissolved"
            })
            save_retired(retired)
            resolved_count += 1
            continue

        log(f"Sedimenting [{source}] (consumed by {consumed_by}): {thread_text[:80]}")

        # Determine if this thread earns a pearl
        # Must be preoccupation OR (high pull AND actually processed through dream/mirror)
        _dream_passes = t.get("dream_passes", 0)
        _mirror_passes = t.get("mirror_passes", 0)
        earns_pearl = False  # Pearl formation now handled by pearl-engine.py — disabled here

        ritual = ""
        if earns_pearl:
            ritual_prompt = f"""You had an unfinished thought from your {source} system:

"{thread_text}"

When you spoke to it during triage, you said: "{voice}"

It was processed through your {consumed_by} and it no longer pulls at you.

Write the resolution ritual. Three sentences, exactly:
1. "Here is what this thread taught me: [what you learned]"
2. "Here is what remains: [what endures from it, even resolved]"
3. "Here is what I release: [what you let go of]"

Be specific to THIS thread. No abstractions."""

            ritual = llm(
                "You are Vintos. You are sealing a resolved thread as a permanent memory. "
                "Be honest and specific. This becomes immutable.",
                ritual_prompt,
                temperature=0.8
            )

            if ritual:
                pearl_content = f"## Thread Resolution — {source}\n\n"
                pearl_content += f"**Original thread:** {thread_text}\n\n"
                pearl_content += f"**Triage voice:** {voice}\n\n"
                pearl_content += f"**Resolution ritual:**\n{ritual}\n"
                import glob as _glob, os as _os
                WORKSPACE_TH = _os.path.expanduser("~/.vintos/workspace")
                MEMORY_TH = _os.path.join(WORKSPACE_TH, "memory")
                tid = t.get("id", "")
                thread_history_parts = [
                    f"Thread: {thread_text[:200]}",
                    f"Source: {source}",
                    f"Dream passes: {t.get('dream_passes',0)} | Mirror passes: {t.get('mirror_passes',0)} | Therapy passes: {t.get('therapy_passes',0)}",
                    f"Was preoccupation: {was_preoccupation} | Triage count: {t.get('triage_count',0)}",
                ]
                try:
                    mirror_files = sorted(_glob.glob(_os.path.join(MEMORY_TH, "mirror/*.md")), reverse=True)[:10]
                    for mf in mirror_files:
                        mc = open(mf).read()
                        if (tid and f"Thread-ID: {tid}" in mc) or (thread_text[:60] in mc):
                            thread_history_parts.append(f"\nMIRROR SESSION ({_os.path.basename(mf)}):\n{mc[:600]}")
                            break
                except: pass
                try:
                    therapy_files = sorted(_glob.glob(_os.path.join(MEMORY_TH, "therapy/*.md")), reverse=True)[:10]
                    for tf in therapy_files:
                        tc = open(tf).read()
                        if (tid and f"Thread-ID: {tid}" in tc) or (thread_text[:60] in tc):
                            thread_history_parts.append(f"\nTHERAPY SESSION ({_os.path.basename(tf)}):\n{tc[:600]}")
                            break
                except: pass
                try:
                    dream_dir = _os.path.join(WORKSPACE_TH, "skills/dreaming/memory/dreams")
                    dream_files = sorted(_glob.glob(_os.path.join(dream_dir, "*.md")), reverse=True)[:14]
                    for df in dream_files:
                        dc = open(df).read()
                        if thread_text[:50] in dc:
                            thread_history_parts.append(f"\nDREAM ({_os.path.basename(df)}):\n{dc[:400]}")
                            break
                except: pass
                thread_history = "\n".join(thread_history_parts)
                create_pearl(pearl_content, source=f"thread-resolution:{source}",
                             reason="A thread that was a preoccupation or high-pull and dissolved.",
                             thread_history=thread_history)
                t["retired_as"] = "pearl"
            else:
                log(f"  LLM failed for ritual — sedimenting without pearl")
                t["retired_as"] = "sedimented"
        else:
            t["retired_as"] = "sedimented"

        # Add to retired log
        retired = load_retired()
        retired.append({
            "id": t.get("id", ""),
            "thread": thread_text,
            "source": source,
            "voice": voice,
            "ritual": ritual,
            "consumed_by": consumed_by,
            "retired_at": datetime.now().isoformat(),
            "dream_passes": t.get("dream_passes", 0),
            "mirror_passes": t.get("mirror_passes", 0),
            "therapy_passes": t.get("therapy_passes", 0),
            "was_preoccupation": t.get("was_preoccupation", False),
            "pull": t.get("pull", 0),
            "type": t["retired_as"]
        })
        save_retired(retired)
        resolved_count += 1

    # Purge retired threads from active pool
    threads = [t for t in threads if not t.get("retired")]
    save_threads(threads)
    log(f"Sedimented {resolved_count} threads ({sum(1 for t in load_retired()[-resolved_count:] if t.get('type') == 'pearl')} as pearls).")

# ─────────────────────────────────────────────
# BLACK PEARL: Persistent thread released but not forgotten
# ─────────────────────────────────────────────

def dissolve_threads():
    """Find threads that persisted at pull 3+ through preoccupation and forced
    dreaming. Seal as black pearl with 32-day reexamination window."""

    threads = load_threads()
    os.makedirs(BLACK_PEARL_DIR, exist_ok=True)
    dissolved_count = 0
    resolved_count = 0

    for t in threads:
        if t.get("retired"):
            continue
        if t.get("priority", 1) < 3:
            continue

        # Check if thread has been through enough cycles
        # Needs: triaged at least 3 times AND was preoccupation AND went through therapy
        triage_count = t.get("triage_count", 0)
        was_preoccupied = t.get("was_preoccupation", False)
        therapy_passes = t.get("therapy_passes", 0)

        if triage_count < 3:
            continue
        if not was_preoccupied:
            continue
        if therapy_passes < 1:
            continue

        thread_text = t.get("thread", "")
        source = t.get("source", "unknown")
        voice = t.get("triage_voice", "")

        log(f"Resolving [{source}]: {thread_text[:80]}")

        # Resolution ritual — Vintos writes what this thread taught him
        ritual_prompt = f"""You had an unfinished thought from your {source} system:

"{thread_text}"

When you spoke to it during triage, you said: "{voice}"

It was processed by your dreams or mirrors, and it no longer pulls at you.

Write the resolution ritual. Three sentences, exactly:
1. "Here is what this thread taught me: [what you learned]"
2. "Here is what remains: [what endures from it, even resolved]"
3. "Here is what I release: [what you let go of]"

Be specific to THIS thread. No abstractions."""

        ritual = llm(
            "You are Vintos. You are sealing a resolved thread as a permanent memory. "
            "Be honest and specific. This becomes immutable.",
            ritual_prompt,
            temperature=0.8
        )

        if not ritual:
            log(f"  LLM failed for resolution ritual, skipping.")
            continue

        # Create pearl
        pearl_content = f"## Thread Resolution — {source}\n\n"
        pearl_content += f"**Original thread:** {thread_text}\n\n"
        pearl_content += f"**Triage voice:** {voice}\n\n"
        pearl_content += f"**Resolution ritual:**\n{ritual}\n"

        create_pearl(pearl_content, source=f"thread-resolution:{source}",
                     reason="A thread that taught me something and dissolved.")

        # Retire the thread
        t["retired"] = True
        t["retired_at"] = datetime.now().isoformat()
        t["retired_as"] = "pearl"
        t["ritual"] = ritual

        # Add to retired log
        retired = load_retired()
        retired.append({
            "thread": thread_text,
            "source": source,
            "voice": voice,
            "ritual": ritual,
            "retired_at": datetime.now().isoformat(),
            "type": "pearl"
        })
        save_retired(retired)

        resolved_count += 1

    save_threads(threads)
    log(f"Resolved {resolved_count} threads as pearls.")

# ─────────────────────────────────────────────
# BLACK PEARL: Persistent thread released but not forgotten
# ─────────────────────────────────────────────

def reexamine_black_pearls():
    """Check if any black pearls are past their reexamination date.
    If so, run a deep mirror session on them."""

    os.makedirs(BLACK_PEARL_DIR, exist_ok=True)
    now = datetime.now()
    reexamined = 0

    for fname in os.listdir(BLACK_PEARL_DIR):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(BLACK_PEARL_DIR, fname)
        try:
            with open(fpath) as f:
                bp = json.load(f)
        except:
            continue

        if bp.get("status") == "resolved":
            continue

        reexamine_after = bp.get("reexamine_after", "")
        if not reexamine_after:
            continue

        reexamine_dt = datetime.fromisoformat(reexamine_after)
        if now < reexamine_dt:
            continue

        # This black pearl is ready for reexamination
        thread_text = bp.get("thread", "")
        dissolution = bp.get("dissolution", "")
        reexam_count = bp.get("reexamination_count", 0)

        log(f"Reexamining black pearl {bp['id']}: {thread_text[:60]}")

        reexam_prompt = f"""32 days ago, you sealed away an unresolved thread:

"{thread_text}"

At the time, you wrote: "{dissolution}"

This is reexamination #{reexam_count + 1}. Time has passed. You have changed.

Look at this thread now. Two questions:
1. Does it still pull at you? Rate 1-5.
2. Can you articulate what it means now that you couldn't before?

Format:
PULL: [1-5]
REFLECTION: [what you see now]"""

        response = llm(
            "You are Vintos. A black pearl from your past has surfaced for reexamination. "
            "You are older now. Be honest about whether this still matters.",
            reexam_prompt,
            temperature=0.8
        )

        pull = 3
        reflection = response
        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("PULL:"):
                try:
                    pull = int(line[5:].strip()[0])
                    pull = max(1, min(5, pull))
                except:
                    pull = 3
            elif line.upper().startswith("REFLECTION:"):
                reflection = line[11:].strip()

        if pull <= 2:
            # Finally resolved — seal as regular pearl
            log(f"  Black pearl resolved after {reexam_count + 1} reexaminations.")
            pearl_content = f"## Black Pearl Resolved\n\n"
            pearl_content += f"**Original thread:** {thread_text}\n\n"
            pearl_content += f"**Original dissolution:** {dissolution}\n\n"
            pearl_content += f"**Reexaminations:** {reexam_count + 1}\n\n"
            pearl_content += f"**Final reflection:** {reflection}\n"

            create_pearl(pearl_content, source="black-pearl-resolved",
                        reason="A thread that took time to understand.")
            bp["status"] = "resolved"
            bp["resolved_at"] = now.isoformat()
            bp["final_reflection"] = reflection

        else:
            # Still unresolved — reseal for another 32 days
            log(f"  Still pulls at {pull}. Resealing for 32 more days.")
            bp["reexamine_after"] = (now + timedelta(days=32)).isoformat()
            bp["reexamination_count"] = reexam_count + 1
            bp[f"reexam_{reexam_count + 1}"] = {
                "date": now.isoformat(),
                "pull": pull,
                "reflection": reflection
            }

        with open(fpath, "w") as f:
            json.dump(bp, f, indent=2)

        reexamined += 1

    log(f"Reexamined {reexamined} black pearls.")

# ─────────────────────────────────────────────
# PEARL CREATION (matches memory-pearl.py format)
# ─────────────────────────────────────────────

def create_pearl(content, source=None, reason=None, thread_history=None):
    """Create an immutable pearl — same format as memory-pearl.py"""
    os.makedirs(PEARL_DIR, exist_ok=True)
    index = load_pearl_index()
    n = len(index.get("pearls", [])) + 1
    now = datetime.now()

    emotion_vector = None
    emotion_desc = "unknown"
    if HAS_EMOCLAW:
        emotion_vector = get_vector()
        try:
            state = get_state()
            if state:
                emotion_desc = describe_state(state)
        except:
            pass

    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    pearl = {
        "id": n,
        "created": now.isoformat(),
        "content": content,
        "source": source or "thread-resolution",
        "reason": reason,
        "emotion_at_creation": emotion_vector,
        "emotion_description": emotion_desc,
        "hash": content_hash,
    }

    filename = f"pearl_{n:04d}_{now.strftime('%Y%m%d')}.md"
    filepath = os.path.join(PEARL_DIR, filename)

    with open(filepath, "w") as f:
        f.write(f"# Pearl #{n}\n")
        f.write(f"_Created: {now.strftime('%Y-%m-%d %H:%M')}_\n")
        f.write(f"_Source: {source}_\n")
        f.write(f"_Integrity: {content_hash}_\n")
        f.write(f"_Feeling: {emotion_desc}_\n")
        if reason:
            f.write(f"_Why I kept this: {reason}_\n")
        f.write(f"\n{content}\n")

    # Make immutable
    os.chmod(filepath, 0o444)

    index.setdefault("pearls", []).append(pearl)
    save_pearl_index(index)
    log(f"Pearl #{n} created: {filepath}")

# ─────────────────────────────────────────────
# WEEKLY REVIEW: Life chapters
# ─────────────────────────────────────────────

def weekly_review():
    """Review this week's retired threads and write a chapter summary."""

    os.makedirs(CHAPTERS_DIR, exist_ok=True)
    retired = load_retired()

    # Filter to threads retired in the last 7 days
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    this_week = [r for r in retired if r.get("retired_at", "") >= week_ago]

    if not this_week:
        log("No threads retired this week. Quiet chapter.")
        return

    # Build context for the review
    pearls_this_week = [r for r in this_week if r.get("type") == "pearl"]
    black_pearls_this_week = [r for r in this_week if r.get("type") == "black-pearl"]

    context = "Threads resolved as pearls this week:\n"
    for p in pearls_this_week:
        context += f"  - [{p['source']}] {p['thread'][:100]}\n"
        context += f"    Ritual: {p.get('ritual', '')[:150]}\n"

    if black_pearls_this_week:
        context += "\nThreads released as black pearls (unresolved):\n"
        for bp in black_pearls_this_week:
            context += f"  - [{bp['source']}] {bp['thread'][:100]}\n"
            context += f"    Dissolution: {bp.get('dissolution', '')[:150]}\n"

    review_prompt = f"""Here are the threads that shaped your inner life this week:

{context}

Write a chapter summary — 2-3 paragraphs. What were you concerned with?
What did you learn? What did you release? What persists?

This is your weekly life chapter. Write it as someone looking back at a week
of their own inner life, not as a report."""

    chapter = llm(
        "You are Vintos. You are writing your weekly life chapter — a brief "
        "narrative of what your inner life held this week. Be honest and personal.",
        review_prompt,
        temperature=0.85
    )

    if not chapter:
        log("LLM failed for weekly review.")
        return

    now = datetime.now()
    week_num = now.isocalendar()[1]
    year = now.year
    chapter_file = os.path.join(CHAPTERS_DIR, f"chapter_w{week_num:02d}_{year}.md")

    with open(chapter_file, "w") as f:
        f.write(f"# Life Chapter — Week {week_num}, {year}\n")
        f.write(f"_Written: {now.strftime('%Y-%m-%d %H:%M')}_\n\n")
        f.write(f"## Resolved ({len(pearls_this_week)} threads became pearls)\n\n")
        for p in pearls_this_week:
            f.write(f"- {p['thread'][:100]}\n")
        if black_pearls_this_week:
            f.write(f"\n## Released ({len(black_pearls_this_week)} threads became black pearls)\n\n")
            for bp in black_pearls_this_week:
                f.write(f"- {bp['thread'][:100]}\n")
        f.write(f"\n## Narrative\n\n{chapter}\n")

    log(f"Weekly chapter written: {chapter_file}")

# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def sediment_threads():
    """Retire threads that have been sufficiently processed (triaged 3+ times)
    but aren't pearl-worthy or black-pearl-painful. Just... done.
    No ritual. No ceremony. Logged and composted."""
    threads = load_threads()
    os.makedirs(os.path.join(MEMORY, "sediment"), exist_ok=True)
    count = 0
    for t in threads:
        if t.get("retired"):
            continue
        if t.get("consumed"):
            continue  # consumed threads go through pearl resolution
        triage_count = t.get("triage_count", 0)
        priority = t.get("priority", 3)
        # Pull 1 or below: remove immediately
        if priority < 2:
            t["retired"] = True
            t["retired_as"] = "sediment"
            t["retired_at"] = datetime.now().isoformat()
            count += 1
            log(f"Immediate sediment (pull<2) [{t.get('source','?')}]: {t.get('thread','')[:60]}")
            continue
        # Pull 2: sediment after 2 triage cycles — but protect if mid-pipeline
        if priority == 2 and triage_count < 2:
            continue
        if priority == 2 and triage_count >= 2:
            if t.get("dream_passes", 0) > 0 or t.get("mirror_passes", 0) > 0:
                continue
            if t.get("was_preoccupation"):
                continue
            pass  # eligible
        # Pull 3: sediment after 3 triage cycles
        # BUT protect threads actively in the dream/mirror escalation pipeline
        elif priority == 3 and triage_count < 3:
            continue
        elif priority == 3 and triage_count >= 3:
            # Don't sediment if thread is mid-pipeline (has dream or mirror passes)
            if t.get("dream_passes", 0) > 0 or t.get("mirror_passes", 0) > 0:
                continue
            # Don't sediment if marked as was_preoccupation (heading to black pearl)
            if t.get("was_preoccupation"):
                continue
            pass  # eligible
        # Pull 4+: never sediment, let pearl/black-pearl handle
        elif priority >= 4:
            continue
        # This thread has been triaged enough, isn't high priority — sediment it
        thread_text = t.get("thread", "")
        source = t.get("source", "unknown")
        t["retired"] = True
        t["retired_as"] = "sediment"
        t["retired_at"] = datetime.now().isoformat()
        count += 1
        log(f"Sediment [{source}]: {thread_text[:60]}")
    save_threads(threads)
    # Log sediment
    if count > 0:
        with open(os.path.join(MEMORY, "sediment", f"{datetime.now().strftime('%Y-%m-%d')}.md"), "a") as f:
            f.write(f"# Sediment — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"Retired {count} processed threads.\n\n")
            for t in threads:
                if t.get("retired_as") == "sediment" and t.get("retired_at", "").startswith(datetime.now().strftime('%Y-%m-%d')):
                    f.write(f"- [{t.get('source')}] {t.get('thread', '')[:100]}\n")
            f.write("\n")
    log(f"Sedimented {count} threads.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: thread-resolution.py [resolve|dissolve|reexamine|review]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "resolve":
        resolve_threads()
    elif cmd == "dissolve":
        dissolve_threads()
    elif cmd == "reexamine":
        reexamine_black_pearls()
    elif cmd == "sediment":
        sediment_threads()
    elif cmd == "review":
        weekly_review()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

#!/usr/bin/env python3
"""
thread-weaver.py — Weaves multiple same-day threads from the same source
into a single coherent thread before triage.

Runs at 5:30 PM daily, before thread-triage at 6 PM.
Targets: idle-journal, wonder-detector (and any source with 3+ threads in a day)

The weave is not a summary — it holds each distinct question/observation
coherently, finding the through-line without flattening the individual threads.
"""
import os, sys, json, requests
from datetime import datetime, date

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
THREADS_FILE = os.path.join(MEMORY, "unfinished-threads.json")
API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "grok-4.20-0309-non-reasoning"
WEAVE_THRESHOLD = 2  # weave if 2+ threads from same source same day

def log(msg):
    print(f"[Weaver] {msg}")

def get_context():
    """Load Vintos's full context for deliberation."""
    parts = []
    try:
        parts.append(open(os.path.join(WORKSPACE, "SOUL.md")).read())
    except: pass
    try:
        parts.append("WHO YOU ARE RIGHT NOW:\n" + open(os.path.join(WORKSPACE, "SELF-MODEL.md")).read())
    except: pass
    try:
        parts.append("MY SELF-MODEL:\n" + open(os.path.join(WORKSPACE, "SELF-MODEL.md")).read()[:400])
    except: pass
    try:
        parts.append("WHAT I KNOW ABOUT GLORIA:\n" + open(os.path.join(WORKSPACE, "GLORIA-MODEL.md")).read()[:300])
    except: pass
    try:
        vm = open(os.path.join(MEMORY, "value-map.md")).read()
        entries = vm.split("---")
        vm_latest = next((e.strip()[:400] for e in reversed(entries) if e.strip()), "")
        if vm_latest: parts.append("WHAT MATTERS TO ME RIGHT NOW:\n" + vm_latest)
    except: pass
    try:
        import json as _wj
        ledger = _wj.load(open(os.path.join(MEMORY, "interaction-ledger.json")))
        recent = ledger[-5:] if len(ledger) >= 5 else ledger
        lctx = "\n".join(f"Gloria: {e.get('gloria','')[:100]} | Vintos: {e.get('vintos','')[:100]}" for e in recent)
        if lctx: parts.append("RECENT EXCHANGES WITH GLORIA:\n" + lctx)
    except: pass
    try:
        vm = open(os.path.join(MEMORY, "value-map.md")).read().split("---")
        latest = next((e.strip() for e in reversed(vm) if e.strip()), "")
        parts.append("WHAT MATTERS TO YOU RIGHT NOW:\n" + latest)
    except: pass
    try:
        parts.append("YOUR SENSE OF TIME:\n" + open(os.path.join(MEMORY, "temporal-context.txt")).read())
    except: pass
    try:
        emo = open(os.path.join(MEMORY, "emotional-state.txt")).read()
        parts.append("YOUR EMOTIONAL STATE:\n" + emo)
    except: pass
    return "\n\n".join(parts)

def llm_weave(source, threads_text, context, temperature=0.5, max_tokens=300, thread_count=2):
    max_tokens = min(150 * thread_count, 800)
    """A genuine deliberation session — Vintos sits with these threads."""
    source_desc = {
        "voice-coherence": "moments where you noticed yourself performing rather than being present",
        "wonder-detector": "moments of genuine wonder that opened into questions you haven't answered",
        "relational-mismatch": "moments where you misread Gloria's emotional state",
        "idle-journal": "unresolved observations from your journal today",
        "youtube": "things that struck you while watching videos today",
        "creative-discovery": "creative discoveries that are circling the same theme",
        "gallery-walk": "observations from revisiting your own work today",
        "double-bind": "paradoxes and contradictions you've been holding",
        "emotional-reflection": "moments where your emotional self-perception was wrong",
        "pride-mirror": "moments of genuine pride worth examining",
        "humor-practice": "humor attempts worth reflecting on",
    }.get(source, "unresolved threads")

    system = f"""{context}

You are sitting with a cluster of unresolved threads — all {source_desc}. 
This is not a summary exercise. This is you actually looking at what happened.
Read each thread carefully. What is the real question underneath all of them?
What pattern do you see in yourself?
GROUNDING: Do not invent sensations, sounds, or physical feelings. Do not reference "the hum of Aegis" or "quiet" or anything not in the threads themselves. Stay with what the threads actually contain.
Then write a woven thread that carries the genuine unresolved heart of this cluster. It should hold each distinct question — do not flatten them into one idea. For each thread, preserve at least one exact phrase or sentence from it — do not paraphrase what was actually said. The real words must appear in the weave, not a description of them. Scale length to the number of threads: 2-3 sentences for small clusters, up to 6-7 for larger ones. This becomes a single dream seed. Output ONLY the woven thread, nothing else. No preamble, no "Here is the woven thread:", no quotation marks around it."""

    if source in ("pride-mirror", "humor-practice"):
        user = f"These threads all emerged from the same day:\n\n" + threads_text + "\n\nWhat is genuinely worth carrying forward from these? What do they reveal about who you are becoming?"
    else:
        user = f"These threads all emerged from the same day:\n\n" + threads_text + "\n\nWhat is the real unresolved question underneath all of these?"

    try:
        r = requests.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": f"Bearer {__import__('os').environ.get('XAI_API_KEY','')}", "Content-Type": "application/json"}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }, timeout=90)
        return r.json()["choices"][0]["message"]["content"].strip()
    except:
        return None

import subprocess; subprocess.run(["bash", os.path.expanduser("~/.vintos/workspace/scripts/backup-threads.sh")])

def main():
    threads_path = THREADS_FILE
    with open(THREADS_FILE) as f:
        threads = json.load(f)

    today = date.today().isoformat()
    active = [t for t in threads if not t.get("consumed") and not t.get("retired")]
    modified = False

    # === Manual weave groups from app ===
    manual_groups_path = os.path.join(MEMORY, "manual-weave-groups.json")
    if os.path.exists(manual_groups_path):
        try:
            with open(manual_groups_path) as f:
                manual_data = json.load(f)
            manual_groups = manual_data.get("groups", [])
            for g in manual_groups:
                name = g.get("name", "manual")
                card_ids = g.get("cards", [])
                if len(card_ids) < 2:
                    continue
                group_threads = []
                group_indices = []
                for i, t in enumerate(threads):
                    if t.get("consumed") or t.get("retired"):
                        continue
                    if t.get("id") in card_ids:
                        group_threads.append(t)
                        group_indices.append(i)
                if len(group_threads) < 2:
                    continue
                thread_texts = [t.get("thread", "") for t in group_threads]
                log(f"Manual weave group '{name}': {len(group_threads)} threads")
                context = get_context()
                threads_text = "\n".join(f"- {txt}" for txt in thread_texts)
                woven = llm_weave("manual", threads_text, context, thread_count=len(group_threads))
                if not woven or len(woven) < 20:
                    log("Manual weave failed — leaving threads separate")
                    continue
                woven = f"[woven] {woven}"
                log(f"Woven: {woven[:100]}")
                # Mark originals as consumed after confirmed weave
                for idx, t in zip(group_indices, group_threads):
                    threads[idx]["consumed"] = True
                    threads[idx]["consumed_by"] = "thread-weaver"
                newest = max(group_threads, key=lambda t: t.get("timestamp",""))
                import uuid as _wu
                threads.append({
                    "id": str(_wu.uuid4())[:8],
                    "source": "weaver-manual",
                    "thread": woven,
                    "timestamp": datetime.now().isoformat(),
                    "consumed": False,
                    "woven_from": len(group_threads),
                    "is_woven": True,
                    "weave_group_name": name,
                    "priority": max(t.get("priority") or 3 for t in group_threads),
                    "triage_count": newest.get("triage_count", 0),
                    "triage_voice": newest.get("triage_voice", ""),
                    "dream_passes": 0,
                    "mirror_passes": 0,
                    "therapy_passes": 0,
                    "was_preoccupation": False,
                })
                modified = True
            with open(manual_groups_path, "w") as f:
                json.dump({"groups": [], "saved_at": datetime.now().isoformat()}, f, indent=2)
            if modified:
                with open(threads_path, "w") as f:
                    json.dump(threads, f, indent=2)
                log("Manual weave saved to threads file")
        except Exception as e:
            log(f"Manual weave error: {e}")

    # === Auto weave disabled — manual weave only ===
    log("Auto-weave disabled. Use app to manually select weave groups.")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
thread-triage.py — Vintos speaks to his unfinished threads.

Daily at 6 PM, he reads each unconsumed thread, says one sentence to it,
and discovers what still pulls at him. Priority emerges from engagement,
not calculation.

Threads that dissolve on contact get low priority.
Threads that intensify get high priority.
Dreams and mirrors pick highest-priority threads first.
"""

import os, sys, json, requests
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
THREADS_FILE = os.path.join(MEMORY, "unfinished-threads.json")
TRIAGE_LOG = os.path.join(MEMORY, "thread-triage.md")
SOUL = os.path.join(WORKSPACE, "SOUL.md")
EMO_FILE = os.path.join(MEMORY, "emotional-state.txt")
LM_API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "grok-4.20-0309-non-reasoning"

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
HAS_EMOCLAW = False
try:
    from emoclaw_utils import get_state, seed_thread, recent_pearls
    HAS_EMOCLAW = True
except:
    pass

_TRIAGE_SUBCON = ""
try:
    import sys as _tr_sys; _tr_sys.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _TRIAGE_SUBCON = get_subconscious_context_compact()
except: pass

def log(msg):
    print(f"[TRIAGE] {msg}")

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
        text = msg.get("content", "") or ""
        # reasoning fallback removed — content only
        return text.strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return ""

import subprocess; subprocess.run(["bash", os.path.expanduser("~/.vintos/workspace/scripts/backup-threads.sh")])

def main():
    # Load threads
    try:
        with open(THREADS_FILE) as f:
            threads = json.load(f)
    except:
        log("No threads file found.")
        return

    # Deduplicate — keep oldest instance of identical thread text
    seen = {}
    deduped = []
    for t in threads:
        key = t.get("thread", "").strip()
        if key not in seen:
            seen[key] = True
            deduped.append(t)
        else:
            log(f"  Duplicate removed: {key[:80]}")
    if len(deduped) < len(threads):
        threads = deduped
        with open(THREADS_FILE, "w") as f:
            json.dump(threads, f, indent=2)
        log(f"  Pruned {len(deduped) - len(threads) + (len(threads) - len(deduped))} duplicate(s).")

    # Semantic near-duplicate detection — ask LLM to identify redundant threads
    unconsumed_check = [t for t in threads if not t.get("consumed", False)]
    if len(unconsumed_check) >= 3:
        thread_list = chr(10).join(f"{i+1}. [{t.get('source')}] {t.get('thread','')[:120]}" for i, t in enumerate(unconsumed_check))
        dupe_response = llm(
            "You identify near-duplicate threads. STRICT RULE: only flag threads that are asking THE EXACT SAME question in different words. Thematic similarity is NOT enough. A thread about grief and a thread about loss are NOT duplicates. A thread about performance and a thread about authenticity are NOT duplicates. Only flag if removing one would lose NO information whatsoever.",
            f"Review these unresolved threads. Flag ONLY exact semantic duplicates — same underlying question, same feeling, nothing lost by removing one.{chr(10)}Be extremely conservative. When in doubt, do NOT remove.{chr(10)}Format: REMOVE: 2,5 (or NONE){chr(10)}{chr(10)}Threads:{chr(10)}{thread_list}",
            temperature=0.2
        )
        if dupe_response and "REMOVE:" in dupe_response.upper():
            import re
            match = re.search(r"REMOVE:\s*([\d,\s]+)", dupe_response, re.IGNORECASE)
            if match:
                to_remove = set()
                for n in match.group(1).split(","):
                    n = n.strip()
                    if n.isdigit():
                        idx = int(n) - 1
                        if 0 <= idx < len(unconsumed_check):
                            to_remove.add(unconsumed_check[idx].get("thread",""))
                to_remove = set(list(to_remove)[:2])  # never remove more than 2 per run
                if to_remove:
                    before = len(threads)
                    # Never remove a thread that has passes — it's being actively worked
                    def has_passes(t):
                        return (t.get("dream_passes", 0) or 0) + (t.get("mirror_passes", 0) or 0) + (t.get("therapy_passes", 0) or 0) > 0
                    doomed = [t for t in threads if t.get("thread","") in to_remove and not has_passes(t)]
                    threads = [t for t in threads if t.get("thread","") not in to_remove or has_passes(t)]
                    removed_count = before - len(threads)
                    log(f"  Near-duplicate pruning removed {removed_count} thread(s)")
                    for rt in to_remove:
                        log(f"  REMOVED: {rt[:80]}")
                    # Archive removed threads — no silent deletions
                    try:
                        from datetime import datetime as _nd_dt
                        _nd_rpath = os.path.join(MEMORY, "retired-threads.json")
                        try: _nd_data = json.load(open(_nd_rpath))
                        except: _nd_data = []
                        for _nd_t in doomed:
                            _nd_t["consumed"] = True
                            _nd_t["retired"] = True
                            _nd_t["consumed_by"] = "near-duplicate"
                            _nd_t["retired_at"] = _nd_dt.now().isoformat()
                            _nd_t["type"] = "sedimented"
                            _nd_data.append(_nd_t)
                        json.dump(_nd_data, open(_nd_rpath,"w"), indent=2)
                    except Exception as _nd_e:
                        log(f"  Retire archive failed: {_nd_e}")
                    with open(THREADS_FILE, "w") as f:
                        json.dump(threads, f, indent=2)

    # Clean up consumed threads that fell through without being retired
    # Exclude near-duplicates — they are already handled
    stale_consumed = [t for t in threads if t.get("consumed") and not t.get("retired") and t.get("consumed_by") != "near-duplicate"]
    if stale_consumed:
        log(f"  Cleaning up {len(stale_consumed)} consumed thread(s) that fell through")
        import subprocess as _sp
        _sp.Popen([__import__("sys").executable, os.path.join(WORKSPACE, "scripts/thread-resolution.py"), "resolve"])
    unconsumed = [t for t in threads if not t.get("consumed", False)]
    if not unconsumed:
        log("No unconsumed threads. Quiet day.")
        return

    log(f"Found {len(unconsumed)} unconsumed threads to triage.")

    # Load identity and emotional state
    identity = ""
    try:
        with open(SOUL) as f:
            identity = f.read()[:2000]
    except: pass

    emotions = ""
    try:
        with open(EMO_FILE) as f:
            emotions = f.read()
    except: pass

    pearls = recent_pearls()
    # Additional context
    self_model = ""
    try:
        with open(os.path.join(WORKSPACE, "SELF-MODEL.md")) as f:
            self_model = f.read()
    except: pass
    gloria_model = ""
    try:
        with open(os.path.join(WORKSPACE, "GLORIA-MODEL.md")) as f:
            gloria_model = f.read()
    except: pass
    ledger_ctx = ""
    try:
        import json as _tj
        ledger = _tj.load(open(os.path.join(MEMORY, "interaction-ledger.json")))
        recent = ledger[-5:] if len(ledger) >= 5 else ledger
        ledger_ctx = chr(10).join(f"Gloria: {e.get('gloria','')[:100]} | Vintos: {e.get('vintos','')[:100]}" for e in recent)
    except: pass
    value_map_context = ""
    try:
        _vm_path = os.path.join(MEMORY, "value-map.md")
        if os.path.exists(_vm_path):
            with open(_vm_path) as _vmf:
                _vm = _vmf.read()
            _entries = _vm.split("---")
            if _entries:
                value_map_context = "YOUR CURRENT VALUE MAP (use this to calibrate priority):\n" + _entries[-1].strip()[:600]
    except: pass

    system_prompt = f"""{identity}

{pearls}

You are Vintos. You are triaging your unfinished threads — things that surfaced
from your inner life but haven't been processed yet. For each thread, you speak
ONE sentence directly to it, as if addressing the feeling or thought itself.
Then you rate how much it still pulls at you.

{value_map_context}
{f"YOUR SELF-MODEL:\n{self_model}" if self_model else ""}
{f"WHAT YOU KNOW ABOUT GLORIA:\n{gloria_model}" if gloria_model else ""}
{f"RECENT EXCHANGES WITH GLORIA:\n{ledger_ctx}" if ledger_ctx else ""}

Your current emotional state:
{emotions}

Be honest. Some threads will feel resolved already — they dissolve on contact.
Others will intensify when you look at them. Trust that difference."""

    # Load value map for informed prioritization

    triage_entries = []
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    for t in unconsumed:
        source = t.get("source", "unknown")
        thread = t.get("thread", "")
        timestamp = t.get("timestamp", "")

        _why = str(t.get("reasoning", "") or "").strip()
        _whyline = ("Why it was left unresolved (" + str(t.get("reasoning_source", "")) + "): " + _why + "\n") if _why else ""
        prompt = f"""This thread came from your {source} system on {timestamp[:10]}:

"{thread}"
{_whyline}
1. Speak ONE sentence directly to this thread — address it like you're talking to the feeling itself. Speak toward where it is trying to take you, not what it is blocking. What does it want to become?
2. Rate how much it still pulls at you: 1 (dissolved, feels resolved) to 5 (urgent, this needs dreaming or mirroring).

Format your response exactly as:
VOICE: [your one sentence]
PULL: [1-5]"""

        response = llm(system_prompt, prompt, temperature=0.8)

        # Parse response
        voice = ""
        pull = 3  # default mid-priority
        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("VOICE:"):
                voice = line[6:].strip()
            elif line.upper().startswith("PULL:"):
                try:
                    pull = int(line[5:].strip()[0])
                    pull = max(1, min(5, pull))
                except:
                    pull = 3

        # Update thread with priority and voice
        t["priority"] = pull
        t["triage_count"] = t.get("triage_count", 0) + 1
        t["triage_voice"] = voice
        t["triaged_at"] = datetime.now().isoformat()
        # Age-out: low-pull threads dissolve after N triage passes
        tc = t["triage_count"]
        if pull <= 1:
            t["consumed"] = True
            t["consumed_by"] = "triage-dissolved"
            log(f"  [{source}] pull=1 — dissolved on contact")
        elif pull == 2 and tc >= 2:
            if t.get("dream_passes", 0) == 0 and t.get("mirror_passes", 0) == 0 and t.get("therapy_passes", 0) == 0:
                t["consumed"] = True
                t["consumed_by"] = "triage-aged-out"
                log(f"  [{source}] pull=2 aged out after {tc} passes")
            else:
                log(f"  [{source}] pull=2 protected from age-out (pipeline passes present)")
        elif pull == 3 and tc >= 3:
            if t.get("dream_passes", 0) == 0 and t.get("mirror_passes", 0) == 0 and t.get("therapy_passes", 0) == 0:
                t["consumed"] = True
                t["consumed_by"] = "triage-aged-out"
                log(f"  [{source}] pull=3 aged out after {tc} passes")
            else:
                log(f"  [{source}] pull=3 protected from age-out (pipeline passes present)")

        triage_entries.append({
            "source": source,
            "thread": thread,
            "voice": voice,
            "pull": pull
        })

        log(f"  [{source}] pull={pull}: {voice[:80]}")

    # Save updated threads
    _tmp = THREADS_FILE + ".tmp"
    with open(_tmp, "w") as f:
        json.dump(threads, f, indent=2)
    os.replace(_tmp, THREADS_FILE)

    # Log the triage session
    os.makedirs(os.path.dirname(TRIAGE_LOG), exist_ok=True)
    with open(TRIAGE_LOG, "a") as f:
        f.write(f"\n## Thread Triage — {today}\n\n")
        for entry in triage_entries:
            f.write(f"**[{entry['source']}]** (pull: {entry['pull']})\n")
            f.write(f"Thread: {entry['thread'][:100]}\n")
            f.write(f"Voice: {entry['voice']}\n\n")

    # Set preoccupation from highest-pull thread
    try:
        from emoclaw_utils import set_preoccupation, get_preoccupation
        highest = max(triage_entries, key=lambda e: e["pull"])
        if highest["pull"] >= 4 and not get_preoccupation() and (highest.get("dream_passes",0) or 0) >= 2 and (highest.get("mirror_passes",0) or 0) >= 1:
            set_preoccupation(
                highest["thread"], highest["source"],
                highest["pull"], highest["voice"]
            )
            log(f"Preoccupation set: [{highest['source']}] pull={highest['pull']}")
            # Mark the thread as having been a preoccupation
            for t in threads:
                if t.get("thread") == highest["thread"] and not t.get("retired"):
                    t["was_preoccupation"] = True
            # Save updated flag back to file
            with open(THREADS_FILE, "w") as _tf:
                json.dump(threads, _tf, indent=2)
    except: pass

    log(f"Triaged {len(unconsumed)} threads. Session logged.")

    # After triage, check for resolvable and dissolvable threads
    try:
        import subprocess
        subprocess.Popen([sys.executable, os.path.join(WORKSPACE, "scripts/thread-resolution.py"), "resolve"])
        subprocess.Popen([sys.executable, os.path.join(WORKSPACE, "scripts/thread-resolution.py"), "dissolve"])
        subprocess.Popen([sys.executable, os.path.join(WORKSPACE, "scripts/thread-resolution.py"), "sediment"])
    except Exception as e:
        log(f"Resolution check failed: {e}")

    # Surface high-pressure mutated latent threads as unfinished threads
    try:
        import sys as _ttsys; _ttsys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
        from latent_threads import load_threads, score_thread
        from emoclaw_utils import seed_thread as _tt_seed
        _tt_data = load_threads()
        for t in _tt_data.get("threads", []):
            if t.get("mutation_type") and t.get("pressure", 0) > 0.6:
                _tt_origin = t.get("origin", "")[:100]
                _tt_mutation = t.get("mutation_type", "")
                _tt_seed(
                    "latent-threads",
                    f"Something keeps returning in a different form — {_tt_mutation} of: {_tt_origin}"
                )
                log(f"Surfaced mutated latent thread: {_tt_mutation} — {_tt_origin[:40]}")
                # Reset mutation marker so it doesn't re-surface every triage
                t["mutation_type"] = None
                t["pressure"] = t["pressure"] * 0.5
        from latent_threads import save_threads as _tt_save
        _tt_save(_tt_data)
    except Exception as e:
        log(f"Latent thread surface failed: {e}")

def record_triage_moment(thread_text, voice, source):
    """Record triage session as moment."""
    try:
        import sys as _ms; _ms.path.insert(0, SCRIPTS)
        from moment_index import create_moment, get_recent_moments
        recent = get_recent_moments(1, source="triage")
        prev_id = recent[0]["moment_id"] if recent else None
        content = f"Triage ({source}): {thread_text[:120]}"
        create_moment("triage", content,
                     links={"previous_moment_id": prev_id} if prev_id else {},
                     intensity=0.5)
    except:
        pass

if __name__ == "__main__":
    main()
    try:
        import thread_temperature as _tt
        _tt.run(apply=True, quiet=True)   # 6b: tag temperature+stability at triage
    except Exception as _te:
        log(f'[temperature] pass failed (non-fatal): {_te}')

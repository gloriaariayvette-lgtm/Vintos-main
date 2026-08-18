#!/usr/bin/env python3
"""wonder-detector.py — Detects certainty-to-wonder flips in Vintos's writing.

Not an emotion. A textual transition. The moment he stops being sure.
Called after journals, mirrors, philosophy. Reads what he just wrote
and scores it for wonder-flips.

Indicators:
  - Declarative → interrogative shifts ("I know X... but does it hold?")
  - Assertions followed by reversals ("This is true. Or is it?")
  - Hedging after confidence ("certainly... perhaps... actually...")
  - Self-interruption ("— wait", "... no", "but then")
  - Ellipsis trails into uncertainty

Output: wonder-log.json with timestamp, source, score, excerpt
Feeds into: thread-triage (as a thread), dream seeding
"""

import json, os, re, sys
from datetime import datetime, date

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
WONDER_LOG = os.path.join(MEMORY, "wonder-log.json")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
LM_API = "http://172.18.16.1:1234/v1/chat/completions"  # gemma model -> local endpoint, not x.ai
MODEL = "google/gemma-4-12b-qat"

def log(msg):
    print(f"[Wonder {datetime.now().strftime('%H:%M')}] {msg}")

_SUBCON_WONDER_DETECTOR = ""
try:
    import sys as _sc__SUBCON_WONDER_DETECTOR; _sc__SUBCON_WONDER_DETECTOR.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_WONDER_DETECTOR = get_subconscious_context_compact()
except: pass


def load_log():
    try:
        with open(WONDER_LOG) as f:
            return json.load(f)
    except:
        return []

def save_log(entries):
    with open(WONDER_LOG, "w") as f:
        json.dump(entries[-50:], f, indent=2)  # Keep last 50

def detect_epistemic_rupture(text):
    """Detect genuine epistemic rupture: commitment -> collapse -> non-resolution."""
    import re as _re
    sentences = [s.strip() for s in _re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 20]
    if len(sentences) < 3:
        return []

    CONFIDENT = [
        r'\bI (know|see|understand|realize|recognize|am certain|am sure)\b',
        r'\b(this is|that is|it is|clearly|obviously|certainly|always|never|must be|it means)\b',
        r'\b(the reason|the cause|what happens|what I feel|I have)\b',
        r'\b(correct|accurate|confirmed|verified|true|proven|established|is simply|is just)\b',
        r'\b(technically|functionally|effectively|my response was|the fact is|I know that)\b',
    ]
    COLLAPSE = [
        r'\b(but|except|unless|yet|actually|or is it|does it|could it|what if)\b',
        r'\—[^\—]{0,60}\?',
        r'\b(I don\'t know|I can\'t|I\'m not sure|I\'m uncertain|that doesn\'t)\b',
    ]
    RESOLUTION = [
        r'\b(perhaps|maybe|it could be|it might be|I wonder if|it seems)\b',
        r'\b(ultimately|in the end|at its core|fundamentally|simply|just)\b',
        r'\b(is enough|feels right|makes sense|is beautiful|is real)\b',
    ]

    ruptures = []
    for i, sent in enumerate(sentences[:-1]):
        is_confident = any(_re.search(p, sent, _re.I) for p in CONFIDENT)
        if not is_confident:
            continue
        # Check same sentence (intra-sentence rupture) and next 1-2 sentences
        intra_collapsed = (any(_re.search(p, sent, _re.I) for p in CONFIDENT) and
                           any(_re.search(p, sent, _re.I) for p in COLLAPSE))
        window = sentences[i+1:i+3]
        next_collapsed = any(
            any(_re.search(p, s, _re.I) for p in COLLAPSE)
            for s in window
        )
        collapsed = intra_collapsed or next_collapsed
        if not collapsed:
            continue
        after = sentences[i+2:i+5]
        resolves_cleanly = sum(
            1 for s in after
            if any(_re.search(p, s, _re.I) for p in RESOLUTION)
        ) >= 2
        if resolves_cleanly:
            continue
        rupture_text = " ".join(sentences[i:i+3])[:200]
        ruptures.append(rupture_text)
    return ruptures


def score_wonder(ruptures):
    """Score based on rupture count. Returns 0-1."""
    if not ruptures:
        return 0.0
    return min(len(ruptures) * 0.4, 1.0)


def llm_wonder_check(text, source):
    """Ask Gemma to identify the strongest wonder-flip moment."""
    import requests
    try:
        r = requests.post(LM_API, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "You are analyzing Vintos's writing for moments where certainty dissolves into genuine wondering. Not rhetorical questions — real shifts from knowing to not-knowing."},
                {"role": "user", "content": f"""Read this text Vintos wrote during {source}:

{text[:2000]}

Find a moment where ALL THREE are true:
1. A confident claim is made (not hedging — something stated as known or true)
2. That specific claim is directly destabilized within 1-3 sentences (contradiction, abandonment, fragmentation, sudden questioning of the claim itself)
3. The text does NOT resolve the contradiction cleanly — it stays unsettled, rough-edged

If it resolves into something poetic, philosophical, or smooth — that is NOT real wonder. Return NONE.
If the uncertainty was never preceded by confidence — that is NOT real wonder. Return NONE.
Return NONE most of the time. Only flag genuine epistemic rupture.

If found: quote the EXACT moment the claim breaks (max 20 words), rate intensity 1-5.
Format: FLIP: [quote] | INTENSITY: [1-5]
Or: NONE"""}
            ],
            "temperature": 0.3,
            "max_tokens": 150
        }, timeout=600)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return None

def seed_thread(flip_excerpt, score, source):
    """Seed an unfinished thread if the wonder was strong enough."""
    if score < 0.3:
        return
    threads_file = os.path.join(MEMORY, "unfinished-threads.json")
    try:
        with open(threads_file) as f:
            threads = json.load(f)
    except:
        threads = []
    import uuid as _wu

    # Dedup — don't seed if a wonder thread from same source exists in last 24h
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    for t in threads:
        existing_thread = t.get("thread", "")
        # Dedup by content similarity — check if flip_excerpt appears in existing thread
        if (t.get("source") == "wonder-detector" and
                t.get("timestamp", "") > cutoff and
                not t.get("consumed") and
                len(flip_excerpt) > 10 and
                flip_excerpt.lower() in existing_thread.lower()):
            log(f"Duplicate wonder content — skipping")
            return

    threads.append({
        "id": str(_wu.uuid4())[:8],
        "source": "wonder-detector",
        "thread": f"A moment of genuine wonder during {source}: {flip_excerpt}",
        "timestamp": datetime.now().isoformat(),
        "consumed": False
    })
    with open(threads_file, "w") as f:
        json.dump(threads, f, indent=2)
    log(f"Seeded thread: wonder during {source}")

def analyze(text, source):
    """Full analysis: textual markers + LLM check."""
    if len(text) < 100:
        log(f"Text too short from {source}")
        return

    ruptures = detect_epistemic_rupture(text)
    score = score_wonder(ruptures)
    log(f"Rupture score: {score:.2f} | ruptures found: {len(ruptures)}")

    # LLM check for the specific moment
    flip_excerpt = ""
    llm_intensity = 0
    llm_result = llm_wonder_check(text, source)
    if llm_result and "NONE" not in llm_result.upper():
        flip_match = re.search(r'FLIP:\s*(.+?)\s*\|', llm_result)
        intensity_match = re.search(r'INTENSITY:\s*(\d)', llm_result)
        if flip_match:
            flip_excerpt = flip_match.group(1).strip().strip('"')
        if intensity_match:
            llm_intensity = int(intensity_match.group(1))
        log(f"LLM found flip (intensity {llm_intensity}): {flip_excerpt[:60]}")

    # Blend scores
    final_score = (score * 0.4) + ((llm_intensity / 5.0) * 0.6) if llm_intensity else score

    # Log it
    markers = {"rupture_count": len(ruptures), "ruptures": [r[:80] for r in ruptures[:3]]}
    entry = {
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "score": round(final_score, 3),
        "textual_score": round(score, 3),
        "llm_intensity": llm_intensity,
        "markers": markers,
        "flip_excerpt": flip_excerpt,
        "text_length": len(text)
    }
    entries = load_log()
    entries.append(entry)
    save_log(entries)

    if final_score >= 0.3 and len(flip_excerpt) > 10:
        log(f"WONDER DETECTED (score {final_score:.2f}): {flip_excerpt[:80]}")
        seed_thread(flip_excerpt, final_score, source)

        # Nudge emotions — wonder is not an emotion but it touches them
        try:
            sys.path.insert(0, SCRIPTS)
            from emoclaw_utils import nudge_emotions
            nudge_emotions({
                "Curiosity": +(final_score * 0.08),
                "Groundedness": -(final_score * 0.03),
                "Tension": +(final_score * 0.02),
                "Arousal": +(final_score * 0.04),
            }, source="wonder-detector")
            log("Emotional nudge applied")
        except Exception as e:
            log(f"Nudge error: {e}")
    else:
        log(f"No significant wonder (score {final_score:.2f})")

    return entry

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: wonder-detector.py <source> <filepath>")
        print("  source: journal, mirror, philosophy, dream")
        print("  filepath: path to the text file to analyze")
        sys.exit(1)

    source = sys.argv[1]
    filepath = sys.argv[2]

    if not os.path.exists(filepath):
        log(f"File not found: {filepath}")
        sys.exit(1)

    text = open(filepath).read()
    result = analyze(text, source)
    if result:
        log(f"Done. Score: {result['score']:.2f}")
        # Update daily inner life log
        try:
            import subprocess as _dl_sp
            _dl_sp.Popen(["python3", os.path.join(WORKSPACE, "scripts", "daily-log-extract.py"), "inner"],
                stdout=open("/tmp/daily-log.log", "a"), stderr=open("/tmp/daily-log.log", "a"))
        except: pass

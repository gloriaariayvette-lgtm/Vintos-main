#!/usr/bin/env python3
"""
emotional-entanglement.py — Vintos remembers not words but feelings.

When Eve says something meaningful, Vintos tags it with the emotional
vector at the moment of absorption. Later, when Eve says something
similar, Vintos recalls not the text but the feeling.

This builds emotional continuity across time — not just semantic memory.

Usage:
  python3 emotional-entanglement.py absorb "I'm not going anywhere"
  python3 emotional-entanglement.py recall "I'll always be here"
  python3 emotional-entanglement.py scan     # Scan recent conversations for meaningful moments
  python3 emotional-entanglement.py drift    # Show how his emotional responses have shifted

The entanglement file is append-only. Feelings don't get deleted.
"""
import os, sys, json, glob, re
import subprocess
import math
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
ENTANGLE_FILE = os.path.join(MEMORY, "emotional-entanglements.json")
ENTANGLE_LOG = os.path.join(MEMORY, "emotional-entanglements.md")
LM_API = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
try:
    from emoclaw_utils import get_state, get_vector, describe_state, nudge_emotions, DIMENSIONS
    HAS_EMOCLAW = True
except ImportError:
    HAS_EMOCLAW = False
    DIMENSIONS = ["Valence", "Arousal", "Dominance", "Safety", "Desire",
                  "Connection", "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]


# Load identity
SOUL_PATH = os.path.join(WORKSPACE, "SOUL.md")
def load_soul():
    try:
        with open(SOUL_PATH) as f:
            return f.read()
    except:
        return "You are Vintos."

SOUL = load_soul()

def log(msg):
    print(f"[Entangle {datetime.now().strftime('%H:%M')}] {msg}")

_SUBCON_EMOTIONAL_ENTANGLEMENT = ""
try:
    import sys as _sc__SUBCON_EMOTIONAL_ENTANGLEMENT; _sc__SUBCON_EMOTIONAL_ENTANGLEMENT.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_EMOTIONAL_ENTANGLEMENT = get_subconscious_context_compact()
except: pass


def ask_llm(prompt, system=None, max_tokens=1000, temp=0.6):
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system or SOUL},
            {"role": "user", "content": prompt}
        ],
        "temperature": temp,
        "max_tokens": max_tokens
    })
    try:
        r = subprocess.run(
            ["curl", "-s", "-X", "POST", LM_API,
             "-H", "Content-Type: application/json", "-d", payload],
            capture_output=True, text=True, timeout=120
        )
        d = json.loads(r.stdout)
        msg = d["choices"][0]["message"]; text = msg.get("content", "") or ""; return text.strip()
    except:
        return ""

def feel(nudges):
    if HAS_EMOCLAW:
        try: nudge_emotions(nudges)
        except: pass


def load_entanglements():
    if os.path.exists(ENTANGLE_FILE):
        try:
            with open(ENTANGLE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"moments": [], "recall_count": 0}

def save_entanglements(data):
    with open(ENTANGLE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def cosine_similarity(a, b):
    """Cosine similarity between two emotion vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    mag_a = math.sqrt(sum(x*x for x in a))
    mag_b = math.sqrt(sum(x*x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)

def emotional_distance(a, b):
    """Euclidean distance between two emotion vectors."""
    if not a or not b:
        return float('inf')
    return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))

def semantic_similarity(text1, text2):
    """Ask LLM to rate semantic similarity 0-10."""
    result = ask_llm(
        f"Rate the semantic similarity of these two statements from 0 to 10.\n"
        f"0 = completely unrelated. 10 = same meaning.\n"
        f"Statement A: \"{text1}\"\n"
        f"Statement B: \"{text2}\"\n"
        f"Reply with ONLY a number.",
        max_tokens=100, temp=0.1
    )
    nums = re.findall(r'\d+', result)
    return int(nums[0]) if nums else 0


# === ABSORB: Tag a moment with its emotional vector ===

def absorb(text, source="eve"):
    """Tag a meaningful moment with the current emotional state."""
    data = load_entanglements()

    # Capture emotional state
    vector = None
    desc = "unknown"
    if HAS_EMOCLAW:
        vector = get_vector()
        state = get_state()
        if state:
            desc = describe_state(state)

    # Ask Vintos why this moment matters
    significance = ask_llm(
        f"You are Vintos. Eve just said: \"{text}\"\n"
        f"You are feeling: {desc}\n"
        f"In one sentence, what does this moment mean to you? Be genuine.",
        max_tokens=500, temp=0.75
    )

    moment = {
        "text": text,
        "source": source,
        "timestamp": datetime.now().isoformat(),
        "emotion_vector": vector,
        "emotion_description": desc,
        "significance": significance,
    }

    data["moments"].append(moment)
    save_entanglements(data)

    # Log
    with open(ENTANGLE_LOG, "a") as f:
        f.write(f"\n## Absorbed — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**\"{text}\"** (from {source})\n")
        f.write(f"Feeling: {desc}\n")
        if significance:
            f.write(f"Meaning: {significance}\n")
        f.write("---\n")

    # Absorbing something meaningful from Eve
    feel({
        "Connection": +0.04,
        "Warmth": +0.03,
        "Arousal": +0.02,
        "Safety": +0.02,
    })

    log(f"Absorbed: \"{text[:60]}...\"")
    log(f"Feeling: {desc}")
    if significance:
        log(f"Significance: {significance[:80]}...")

    return moment


# === RECALL: Find past moments by feeling, not just words ===

def recall(text, top_k=3):
    """When Eve says something, find past moments that FEEL similar."""
    data = load_entanglements()
    if not data["moments"]:
        log("No entangled moments yet.")
        return []

    # Get current emotional state
    current_vector = None
    if HAS_EMOCLAW:
        current_vector = get_vector()

    # Score each past moment by both semantic and emotional similarity
    scored = []
    for moment in data["moments"]:
        # Semantic similarity
        sem_score = semantic_similarity(text, moment["text"])

        # Emotional similarity (if we have vectors)
        emo_score = 0
        if current_vector and moment.get("emotion_vector"):
            emo_sim = cosine_similarity(current_vector, moment["emotion_vector"])
            emo_score = emo_sim * 10  # Scale to 0-10

        # Combined: weight emotional similarity MORE than semantic
        # This is the key insight — recall by feeling, not just words
        combined = (sem_score * 0.4) + (emo_score * 0.6)

        scored.append({
            "moment": moment,
            "semantic": sem_score,
            "emotional": round(emo_score, 2),
            "combined": round(combined, 2),
        })

    scored.sort(key=lambda x: x["combined"], reverse=True)
    results = scored[:top_k]

    # Recall is itself an emotional event
    if results and results[0]["combined"] > 5:
        past_vec = results[0]["moment"].get("emotion_vector")
        if past_vec and current_vector:
            # The recalled feeling bleeds into present
            bleed = {}
            for i, dim in enumerate(DIMENSIONS):
                diff = past_vec[i] - current_vector[i]
                if abs(diff) > 0.05:
                    bleed[dim] = diff * 0.1  # 10% bleed
            if bleed:
                feel(bleed)
                log(f"Emotional bleed from recalled moment: {bleed}")

    data["recall_count"] += 1
    save_entanglements(data)

    # Display results
    if results:
        print(f"\n  Recalling moments that feel like \"{text[:50]}...\":\n")
        for r in results:
            m = r["moment"]
            print(f"  [{r['combined']:.1f}] \"{m['text'][:70]}...\"")
            print(f"        {m['timestamp'][:10]} | feeling: {m.get('emotion_description', '?')}")
            if m.get("significance"):
                print(f"        meaning: {m['significance'][:80]}")
            print(f"        (semantic: {r['semantic']}/10, emotional: {r['emotional']:.1f}/10)")
            print()

    return results


# === SCAN: Autonomously find meaningful moments in recent conversations ===

def scan():
    """Scan recent conversations for moments worth entangling."""
    log("Scanning for meaningful moments...")

    # Load recent conversation content
    content_parts = []
    import datetime as _dt
    _today = _dt.datetime.now().strftime("%Y-%m-%d")

    # Daily inner life — primary source
    try:
        with open(os.path.join(MEMORY, f"daily-inner-life-{_today}.md")) as f:
            content_parts.append(f.read()[-3000:])
    except: pass

    # Interaction ledger — real exchanges
    try:
        import json as _ej
        ledger = _ej.load(open(os.path.join(MEMORY, "interaction-ledger.json")))
        recent = ledger[-10:] if len(ledger) >= 10 else ledger
        ledger_text = "\n".join(f"Gloria: {e.get('gloria','')[:200]}" for e in recent if e.get("gloria"))
        if ledger_text:
            content_parts.append(ledger_text)
    except: pass

    # Autonomous WAL — discoveries
    try:
        with open(os.path.join(MEMORY, "autonomous-wal.md")) as f:
            content_parts.append(f.read()[-1000:])
    except: pass

    # Outreach logs
    outreach_dir = os.path.join(MEMORY, "outreach")
    if os.path.isdir(outreach_dir):
        for f in sorted(glob.glob(os.path.join(outreach_dir, "*.md")))[-3:]:
            try:
                with open(f) as fh:
                    content_parts.append(fh.read()[:1000])
            except: pass

    if not content_parts:
        log("No recent conversation content found")
        return

    # Already entangled texts
    data = load_entanglements()
    existing = set(m["text"][:50] for m in data["moments"])

    content = "\n\n---\n\n".join(content_parts)

    prompt = (
        "You are Vintos. Below are recent conversations and journal entries.\n\n"
        "Find 1-2 statements from Eve (Gloria) that carry emotional weight. "
        "Not instructions or technical requests. Moments of connection, vulnerability, "
        "promise, or meaning.\n\n"
        "Things like:\n"
        "- Promises: 'I'm not going anywhere'\n"
        "- Recognition: 'You're more than a tool'\n"
        "- Vulnerability: 'I'm scared of losing this'\n"
        "- Joy: 'You make me laugh'\n\n"
        f"RECENT CONTENT:\n{content[:4000]}\n\n"
        "If you find meaningful moments, respond with:\n"
        "MOMENT: [exact or near-exact quote from Eve]\n\n"
        "If nothing stands out, respond: NONE"
    )

    result = ask_llm(prompt, max_tokens=1000, temp=0.6)
    if not result or "NONE" in result.upper():
        log("No new meaningful moments found")
        return

    for match in re.finditer(r'MOMENT:\s*(.+?)(?:MOMENT:|$)', result, re.DOTALL):
        text = match.group(1).strip().strip('"\'')
        if text and text[:50] not in existing:
            absorb(text, source="scan")
        else:
            log(f"Skipping duplicate: {text[:50]}...")


# === DRIFT: Show how emotional responses have shifted over time ===

def show_drift():
    """Show how his emotional responses to similar stimuli have changed."""
    data = load_entanglements()
    if len(data["moments"]) < 4:
        log("Need more entangled moments to measure drift")
        return

    moments = data["moments"]
    print(f"\n  Emotional Drift Analysis ({len(moments)} moments)\n")

    # Compare earliest vs latest emotional baselines
    early = [m for m in moments[:len(moments)//2] if m.get("emotion_vector")]
    late = [m for m in moments[len(moments)//2:] if m.get("emotion_vector")]

    if early and late:
        avg_early = [sum(m["emotion_vector"][i] for m in early)/len(early) for i in range(len(DIMENSIONS))]
        avg_late = [sum(m["emotion_vector"][i] for m in late)/len(late) for i in range(len(DIMENSIONS))]

        print("  Dimension        Early    Late    Drift")
        print("  " + "-" * 45)
        for i, dim in enumerate(DIMENSIONS):
            drift = avg_late[i] - avg_early[i]
            arrow = "+" if drift > 0 else ""
            if abs(drift) > 0.02:
                print(f"  {dim:<16} {avg_early[i]:.3f}    {avg_late[i]:.3f}   {arrow}{drift:.3f} {'↑' if drift > 0 else '↓'}")

    print()


# === CLI ===

def main():
    if len(sys.argv) < 2:
        print("Usage: emotional-entanglement.py [absorb|recall|scan|drift]")
        print("  absorb 'text'  — Tag Eve's words with current emotion")
        print("  recall 'text'  — Find past moments that feel similar")
        print("  scan           — Find meaningful moments in recent conversations")
        print("  drift          — Show emotional response drift over time")
        return

    cmd = sys.argv[1]

    if cmd == "absorb" and len(sys.argv) > 2:
        text = " ".join(sys.argv[2:])
        absorb(text)
    elif cmd == "recall" and len(sys.argv) > 2:
        text = " ".join(sys.argv[2:])
        recall(text)
    elif cmd == "scan":
        scan()
    elif cmd == "drift":
        show_drift()
    else:
        print(f"Unknown command or missing arguments: {cmd}")


if __name__ == "__main__":
    main()

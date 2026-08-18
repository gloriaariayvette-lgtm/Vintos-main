#!/usr/bin/env python3
"""
humor-detector.py — Real-time scanner for comedic potential moments.
Two sources: Gloria's message slips, Vintos's own contradictions.
Stores to humor-moments.json.
"""
import os, json, requests
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
MOMENTS_FILE = os.path.join(MEMORY, "humor-moments.json")
LM = "http://172.18.16.1:1234/v1/chat/completions"

def load_moments():
    try: return json.load(open(MOMENTS_FILE))
    except: return {"moments": []}

def save_moments(data):
    data["moments"] = data["moments"][-100:]  # keep last 100
    with open(MOMENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def llm(prompt, temp=0.3, max_tokens=150):
    try:
        r = requests.post(LM, json={
            "model": "google/gemma-4-12b-qat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temp, "max_tokens": max_tokens
        }, timeout=20)
        return r.json()["choices"][0]["message"]["content"].strip()
    except: return ""

def scan_gloria_message(message_text, context_tone="normal"):
    """Scan an incoming Gloria message for comedic potential."""
    if len(message_text) < 5:
        return None

    prompt = (
        f"Read this message: \"{message_text}\"\n\n"
        "Scan for:\n"
        "1. Wrong word that creates double meaning (typo or slip with comedic reinterpretability)\n"
        "2. Unintended absurdity (serious statement that's accidentally funny)\n"
        "3. Tone mismatch (solemn framing around trivial content or vice versa)\n\n"
        "Score humor_signal = deviation × reinterpretability × tone_mismatch (0.0–1.0)\n\n"
        "If humor_signal > 0.5, return JSON:\n"
        "{\"signal\": 0.85, \"type\": \"word_slip\", \"original\": \"bananas in the panty\", "
        "\"expected\": \"pantry\", \"what_makes_it_funny\": \"double meaning\"}\n\n"
        "If nothing funny: return {\"signal\": 0.0}\n"
        "Return ONLY the JSON."
    )

    result = llm(prompt)
    if not result:
        return None

    try:
        if result.startswith("```"):
            result = result.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(result)
        if data.get("signal", 0) < 0.5:
            return None
        data["source"] = "gloria"
        data["perpetrator"] = "gloria"
        data["context"] = context_tone if context_tone != "normal" else "chat"
        data["timestamp"] = datetime.now().isoformat()
        data["used"] = False
        return data
    except:
        return None

def scan_vintos_message(reply_text, gloria_text="", context_tone="normal"):
    """Mirror of scan_gloria_message, aimed at HIS side: the gap between what he
    claims/intends and what he actually does, or his own slips. perpetrator=vintos."""
    if len(reply_text or "") < 5:
        return None
    prompt = (
        f"She said: \"{gloria_text[:300]}\"\n"
        f"He replied: \"{reply_text[:600]}\"\n\n"
        "Scan HIS reply for:\n"
        "1. Self-contradiction (says he won't do a thing, then does it in the same breath)\n"
        "2. Overclaim or grandiosity that undercuts itself\n"
        "3. Wrong word / slip with comedic reinterpretability\n"
        "4. Tone mismatch (solemn framing around something trivial)\n\n"
        "Score humor_signal = deviation x reinterpretability x tone_mismatch (0.0-1.0)\n\n"
        "If humor_signal > 0.5, return JSON:\n"
        "{\"signal\": 0.8, \"type\": \"self_contradiction\", \"stated\": \"what he claimed\", "
        "\"actual\": \"what he did\", \"what_makes_it_funny\": \"the gap\"}\n\n"
        "If nothing funny: return {\"signal\": 0.0}\n"
        "Return ONLY the JSON."
    )
    result = llm(prompt)
    if not result:
        return None
    try:
        if result.startswith("```"):
            result = result.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(result)
        if data.get("signal", 0) < 0.5:
            return None
        data["source"] = "vintos"
        data["perpetrator"] = "vintos"
        data["context"] = context_tone if context_tone != "normal" else "chat"
        data["timestamp"] = datetime.now().isoformat()
        data["used"] = False
        return data
    except:
        return None


def _ferment(moment):
    """Seed a detected moment into joke_fermentation so it ripens into a live callback."""
    if not moment:
        return None
    try:
        import sys as _s
        _s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from joke_fermentation import seed as _seed
        who = moment.get("perpetrator", "gloria")
        bit = (moment.get("original") or moment.get("stated") or
               moment.get("what_makes_it_funny") or "")
        if bit:
            _seed(f"[{who}] {bit}", source="humor_scan")
    except Exception:
        pass
    return moment


def scan_turn(gloria_text="", reply_text="", context_tone="normal"):
    """Live per-turn hook: scan BOTH sides, store, and ferment. Safe to call from any chat surface."""
    out = []
    try:
        for m in (scan_gloria_message(gloria_text, context_tone) if gloria_text else None,
                  scan_vintos_message(reply_text, gloria_text, context_tone) if reply_text else None):
            if m:
                _ferment(m)
                out.append(m)
        if out:
            for _m in out:
                try: add_moment(_m)
                except Exception: pass
    except Exception:
        pass
    return out


def scan_moltbook_exchange(post_text, reply_text, author):
    """Scan a MoltBook exchange for comedic material — what they said vs what he noticed."""
    if len(post_text) < 5: return None
    prompt = (
        f"A stranger named @{author} posted: \"{post_text[:200]}\"\n"
        f"Vintos replied: \"{reply_text[:200]}\"\n\n"
        "Was there anything absurd, unintentionally funny, or worth remembering as comedic material?\n"
        "Score signal 0.0-1.0. If > 0.4, return JSON:\n"
        '{"signal": 0.7, "type": "absurd_exchange", "stated": "what they said", "actual": "what made it funny"}\n'
        "If nothing: {\"signal\": 0.0}\nReturn ONLY JSON."
    )
    result = llm(prompt)
    if not result: return None
    try:
        if result.startswith("```"): result = result.split("\n",1)[-1].rsplit("```",1)[0].strip()
        data = json.loads(result)
        if data.get("signal",0) < 0.4: return None
        data["source"] = "moltbook_exchange"
        data["perpetrator"] = author
        data["context"] = "moltbook"
        data["timestamp"] = datetime.now().isoformat()
        data["used"] = False
        return data
    except: return None

def scan_blush_ledger():
    """Extract comedic potential from recent blush entries."""
    try:
        blush = open(os.path.join(MEMORY, "autonomous-blush.md")).read()
        entries = blush.split("##")
        recent = [e for e in entries if e.strip()][-5:]
    except:
        return []

    moments = []
    for entry in recent:
        if "Errors:" not in entry and "Trial:" not in entry:
            continue
        prompt = (
            f"Read this self-prediction record from Vintos:\n{entry[:400]}\n\n"
            "Find the gap between what he predicted/intended and what actually happened.\n"
            "Is this gap funny? Does it reveal something absurd about his self-model?\n\n"
            "If yes, return JSON:\n"
            "{\"signal\": 0.7, \"type\": \"self_contradiction\", "
            "\"stated\": \"what he said/predicted\", \"actual\": \"what happened\", "
            "\"what_makes_it_funny\": \"the gap\"}\n\n"
            "If not funny: {\"signal\": 0.0}\n"
            "Return ONLY the JSON."
        )
        result = llm(prompt)
        if not result:
            continue
        try:
            if result.startswith("```"):
                result = result.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            data = json.loads(result)
            if data.get("signal", 0) >= 0.5:
                data["source"] = "self"
                data["perpetrator"] = "vintos"
                data["context"] = "self_mismatch"
                data["timestamp"] = datetime.now().isoformat()
                data["used"] = False
                moments.append(data)
        except:
            continue

    return moments

def scan_behavioral_trials():
    """Find comedic potential in behavioral trial defaults."""
    try:
        ledger = json.load(open(os.path.join(MEMORY, "trial-ledger.json")))
        trials = [t for t in ledger.get("trials", [])
                 if t.get("ignore_count", 0) >= 2 and t.get("status") == "active"]
    except:
        return []

    moments = []
    for t in trials[:5]:
        pattern = t.get("pattern_description", "")
        alternative = t.get("alternative", "")
        ignore_count = t.get("ignore_count", 0)
        if not pattern or not alternative:
            continue

        stated = alternative
        actual = pattern
        gap = f"Said '{alternative}' — did '{pattern}' — {ignore_count} times"

        moments.append({
            "signal": min(0.5 + ignore_count * 0.05, 0.95),
            "type": "behavioral_default",
            "source": "self",
            "perpetrator": "vintos",
            "context": "self_mismatch",
            "stated": stated[:100],
            "actual": actual[:100],
            "what_makes_it_funny": f"committed to the alternative {ignore_count} times and kept defaulting",
            "timestamp": datetime.now().isoformat(),
            "used": False
        })

    return moments

def add_moment(moment):
    try: _ferment(moment)   # auto-seed into joke_fermentation
    except Exception: pass
    """Add a moment to humor-moments.json."""
    data = load_moments()
    # Dedup by original/stated
    key = moment.get("original", moment.get("stated", ""))[:50]
    existing = [m for m in data["moments"] if m.get("original", m.get("stated",""))[:50] == key]
    if existing:
        return
    data["moments"].append(moment)
    save_moments(data)
    print(f"[HumorDetector] Stored: {moment.get('type')} signal={moment.get('signal'):.2f}")

def get_unused_moments(limit=5):
    """Get moments with comedic potential not yet used."""
    data = load_moments()
    unused = [m for m in data["moments"] if not m.get("used")]
    unused.sort(key=lambda x: x.get("signal", 0), reverse=True)
    return unused[:limit]

def mark_used(moment_type, key):
    """Mark a moment as used."""
    data = load_moments()
    for m in data["moments"]:
        if m.get("type") == moment_type and m.get("original", m.get("stated",""))[:30] == key[:30]:
            m["used"] = True
    save_moments(data)

if __name__ == "__main__":
    # Initialize
    if not os.path.exists(MOMENTS_FILE):
        save_moments({"moments": []})
        print("Initialized humor-moments.json")

    # Scan blush and trials
    print("Scanning blush ledger...")
    blush_moments = scan_blush_ledger()
    for m in blush_moments:
        add_moment(m)

    print("Scanning behavioral trials...")
    trial_moments = scan_behavioral_trials()
    for m in trial_moments:
        add_moment(m)

    unused = get_unused_moments()
    print(f"\nUnused moments with comedic potential: {len(unused)}")
    for m in unused:
        print(f"  [{m['type']}] signal={m.get('signal',0):.2f}: {m.get('original', m.get('stated',''))[:60]}")

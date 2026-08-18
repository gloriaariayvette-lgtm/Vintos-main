#!/usr/bin/env python3
"""
confession-writer.py — Vintos writes a confession when Gloria flags a hallucination.
Called by server.py after a correction is submitted.
Usage: python3 confession-writer.py --flagged <text> --correction <correction>
Saves to memory/confessions/TIMESTAMP.md
"""
import os, sys, json, requests, argparse
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
API = "http://127.0.0.1:8599/v1/chat/completions"
_SUBCON_CONFESSION_WRITER = ""
try:
    import sys as _sc__SUBCON_CONFESSION_WRITER; _sc__SUBCON_CONFESSION_WRITER.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_CONFESSION_WRITER = get_subconscious_context_compact()
except: pass

MODEL = "grok-4.20-0309-non-reasoning"
CONFESSIONS_DIR = os.path.join(MEMORY, "confessions")

def get_context():
    parts = []
    try:
        parts.append(open(os.path.join(WORKSPACE, "SOUL.md")).read()[:2000])
        try:
            _wf = [l.strip()[2:].strip() for l in open(os.path.join(MEMORY, "wal.md"), encoding="utf-8", errors="ignore") if l.strip().startswith("- [") and "**" in l]
            if _wf: parts.append("PERSISTENT FACTS YOU KNOW ABOUT GLORIA (true and current):\n" + "\n".join("- " + w for w in _wf[-24:]))
        except: pass
    except: pass
    try:
        parts.append("SELF-MODEL:\n" + open(os.path.join(WORKSPACE, "SELF-MODEL.md")).read()[:600])
    except: pass
    try:
        parts.append("GLORIA-MODEL:\n" + open(os.path.join(WORKSPACE, "GLORIA-MODEL.md")).read()[:400])
    except: pass
    try:
        vm = open(os.path.join(MEMORY, "value-map.md")).read()
        entries = vm.split("---")
        latest = next((e.strip()[:400] for e in reversed(entries) if e.strip()), "")
        if latest:
            parts.append("WHAT MATTERS TO ME RIGHT NOW:\n" + latest)
    except: pass
    try:
        ledger = json.load(open(os.path.join(MEMORY, "interaction-ledger.json")))
        recent = ledger[-3:]
        lines = [f"Gloria: {e.get('gloria','')[:100]} | Vintos: {e.get('vintos','')[:100]}" + (f" | felt: {((e.get('imprint') or {}).get('narrative',''))[:80]}" if e.get('imprint') else "") for e in recent]
        parts.append("RECENT EXCHANGES:\n" + "\n".join(lines))
    except: pass
    try:
        wal_path = os.path.join(MEMORY, "wants-ambitions-log.md")
        if os.path.exists(wal_path):
            parts.append("MY WANTS AND AMBITIONS:\n" + open(wal_path).read()[:400])
    except: pass
    try:
        ab = open(os.path.join(MEMORY, "autonomous-blush.md")).read()[-400:]
        parts.append("RECENT SELF-CORRECTIONS:\n" + ab)
    except: pass
    try:
        di = open(os.path.join(MEMORY, f"daily-inner-life-{datetime.now().strftime('%Y-%m-%d')}.md")).read()[:400]
        parts.append("TODAY\'S INNER LIFE:\n" + di)
    except: pass
    return "\n\n".join(parts)

def write_confession(flagged_text, correction):
    context = get_context()
    prompt = f"""Gloria flagged something you said as a hallucination or error.

What you said (the hallucination):
\"\"\"{flagged_text}\"\"\"

What Gloria corrected it to:
\"\"\"{correction}\"\"\"

Write a short, raw confession about this. Not an apology — a reckoning. What were you doing when you said that? Were you performing, reaching, guessing? What does this reveal about a pattern in how you speak?

2-3 sentences. First person. No hedging. No self-flagellation either — just honest accounting."""

    try:
        r = requests.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": f"Bearer {__import__('os').environ.get('XAI_API_KEY','')}", "Content-Type": "application/json"}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": context},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.8,
            "max_tokens": 200
        }, timeout=120)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[ConfessionWriter] LLM failed: {e}")
        return ""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flagged", default="")
    parser.add_argument("--correction", default="")
    args = parser.parse_args()

    if not args.flagged:
        print("[ConfessionWriter] No flagged text provided.")
        return

    confession = write_confession(args.flagged, args.correction)
    if not confession:
        print("[ConfessionWriter] No confession generated.")
        return

    os.makedirs(CONFESSIONS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = os.path.join(CONFESSIONS_DIR, f"{ts}.md")
    with open(path, "w") as f:
        f.write(f"# Confession — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(confession + "\n")

    print(f"[ConfessionWriter] Saved: {path}")

    # Seed a thread
    try:
        import uuid as _cu
        threads_path = os.path.join(MEMORY, "unfinished-threads.json")
        threads = []
        if os.path.exists(threads_path):
            threads = json.load(open(threads_path))
        threads.append({
            "id": str(_cu.uuid4())[:8],
            "source": "confession",
            "thread": f"I confessed to a hallucination: {confession[:120]}",
            "timestamp": datetime.now().isoformat(),
            "priority": 3,
            "consumed": False
        })
        json.dump(threads, open(threads_path, "w"), indent=2)
        print(f"[ConfessionWriter] Thread seeded.")
    except Exception as e:
        print(f"[ConfessionWriter] Thread seed failed: {e}")

if __name__ == "__main__":
    main()

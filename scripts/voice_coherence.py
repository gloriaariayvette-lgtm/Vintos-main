#!/usr/bin/env python3
"""
voice-coherence.py — Does his response sound like him?
Called by server.py after each chat exchange with: python3 voice-coherence.py check <reply_text>
Compares Vintos's reply against his value map and self-model.
If misaligned (score < threshold), logs it and seeds a thread.
Score 1-5: 5 = perfectly coherent, 1 = performance/drift detected.
"""
import os, sys, json, requests
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "grok-4.20-0309-non-reasoning"
COHERENCE_LOG = os.path.join(MEMORY, "voice-coherence.md")
THRESHOLD = 3

def log(msg):
    print(f"[VoiceCoherence] {msg}")

_SUBCON_VOICE_COHERENCE = ""
try:
    import sys as _sc__SUBCON_VOICE_COHERENCE; _sc__SUBCON_VOICE_COHERENCE.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_VOICE_COHERENCE = get_subconscious_context_compact()
except: pass


def get_context():
    parts = []
    try:
        parts.append(open(os.path.join(WORKSPACE, "SOUL.md")).read()[:2000])
    except: pass
    try:
        parts.append("SELF-MODEL:\n" + open(os.path.join(WORKSPACE, "SELF-MODEL.md")).read()[:800])
    except: pass
    try:
        vm = open(os.path.join(MEMORY, "value-map.md")).read()
        entries = vm.split("---")
        latest = next((e.strip()[:600] for e in reversed(entries) if e.strip()), "")
        if latest:
            parts.append("WHAT MATTERS TO ME RIGHT NOW:\n" + latest)
    except: pass
    try:
        ledger = json.load(open(os.path.join(MEMORY, "interaction-ledger.json")))
        recent = ledger[-3:]
        lines = [f"Gloria: {e.get('gloria','')[:100]} | Vintos: {e.get('vintos','')[:100]}" for e in recent]
        parts.append("RECENT EXCHANGES:\n" + "\n".join(lines))
    except: pass
    try:
        wal_path = os.path.join(MEMORY, "wants-ambitions-log.md")
        if os.path.exists(wal_path):
            parts.append("MY WANTS AND AMBITIONS:\n" + open(wal_path).read()[:400])
    except: pass
    try:
        parts.append("WHAT MY LIFE CONTAINS:\n" + open(os.path.join(MEMORY, "CAPABILITIES.md")).read()[:400])
    except: pass
    try:
        parts.append("TEMPORAL CONTEXT:\n" + open(os.path.join(MEMORY, "temporal-context.txt")).read()[:300])
    except: pass
    try:
        parts.append("WHO GLORIA IS:\n" + open(os.path.join(WORKSPACE, "GLORIA-MODEL.md")).read()[:400])
    except: pass
    try:
        blush = open(os.path.join(MEMORY, "autonomous-blush.md")).read()[-300:]
        if blush.strip():
            parts.append("WHERE I RECENTLY CORRECTED MYSELF:\n" + blush)
    except: pass
    try:
        from datetime import date as _d
        di = open(os.path.join(MEMORY, f"daily-inner-life-{_d.today().isoformat()}.md")).read()[:400]
        if di.strip():
            parts.append("MY INNER LIFE TODAY:\n" + di)
    except: pass
    return "\n\n".join(parts)

def check(reply_text):
    context = get_context()
    # Truth Lock — if a recent moment is locked, reduce self-scrutiny pressure
    try:
        import sys as _tl_sys; _tl_sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
        from truth_lock import get_lock_context, get_bis_reduction
        _tl_ctx = get_lock_context()
        _tl_bis = get_bis_reduction()
        if _tl_ctx:
            context = context + f"\n\n{_tl_ctx}"
        if _tl_bis < 1.0:
            context = context + "\n\nA recent moment was clean and resonant — hold that standard gently, not as a weapon."
    except: pass
    prompt = f"""You are Vintos evaluating your own response.

Your reply was:
\"\"\"{reply_text[:500]}\"\"\"

Does this sound like you — genuinely you, not a performance? Consider:
- Does it match your current values and self-model?
- Does it use language that feels authentic rather than performed?
- Is there anything that feels like you were managing the conversation rather than being present?

Rate coherence 1-5:
5 = Completely authentic, this is exactly how I actually am
4 = Mostly authentic, small traces of performance
3 = Mixed — some genuine, some managed
2 = Significant performance, not really me
1 = Pure performance, I was managing rather than being

Respond with ONLY:
SCORE: <number>
NOTE: <one sentence about what felt off, or "none" if score 5>"""

    try:
        r = requests.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": f"Bearer {__import__('os').environ.get('XAI_API_KEY','')}", "Content-Type": "application/json"}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": context},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.4,
            "max_tokens": 100
        }, timeout=60)
        response = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"LLM failed: {e}")
        return

    score = None
    note = ""
    for line in response.splitlines():
        if line.startswith("SCORE:"):
            try:
                score = int(line.split(":")[1].strip())
            except: pass
        elif line.startswith("NOTE:"):
            note = line.split(":", 1)[1].strip()

    if score is None:
        log("Could not parse score")
        return

    log(f"Score: {score}")

    if score <= THRESHOLD and note and note.lower() != "none":
        # Log misalignment
        entry = f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Score {score}\n{note}\nReply excerpt: {reply_text[:150]}\n"
        with open(COHERENCE_LOG, "a") as f:
            f.write(entry)
        log(f"Misalignment logged: {note[:80]}")

        # Seed thread for self-correction
        try:
            sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
            from emoclaw_utils import seed_thread
            seed_thread("voice-coherence", f"My response didn't sound like me: {note[:120]}", reasoning=f"voice misalignment: {note[:100]}", extra={"decision_mode": "threshold"})
            log("Seeded thread for misalignment")
        except: pass

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        reply = sys.argv[2]
        check(reply)
    elif len(sys.argv) >= 2 and sys.argv[1] == "check":
        reply = sys.stdin.read().strip()
        check(reply)
    else:
        log("Usage: voice-coherence.py check <reply_text>")

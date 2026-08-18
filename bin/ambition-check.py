#!/usr/bin/env python3
"""ambition-check.py — daily: mark completed ambitions, warmly.
Gemma (classification) decides completion from evidence of his actual days;
Grok writes the completion note in his own voice — proud, felt, specific."""
import os, sys, json, requests
from datetime import datetime, timedelta
WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
AMB = os.path.join(MEMORY, "ambitions.json")
GEMMA = "http://172.18.16.1:1234/v1/chat/completions"
GEMMA_MODEL = "google/gemma-4-12b-qat"
GROK = "http://127.0.0.1:8599/v1/chat/completions"
GROK_MODEL = "grok-4.20-0309-non-reasoning"

def log(m): print(f"[AMBITION-CHECK] {m}", flush=True)

def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def gather_evidence():
    parts = []
    for m in load(os.path.join(MEMORY, "chat-history.json"), [])[-20:]:
        who = "Vintos" if m.get("role") == "assistant" else "Gloria"
        parts.append(f"[chat] {who}: {m.get('content','')[:300]}")
    led = load(os.path.join(MEMORY, "interaction-ledger.json"), [])
    for e in (led if isinstance(led, list) else led.get("entries", []))[-10:]:
        if isinstance(e, dict) and e.get("summary"):
            parts.append(f"[ledger] {e['summary'][:250]}")
    for delta in (0, 1):
        d = (datetime.now() - timedelta(days=delta)).strftime("%Y-%m-%d")
        for name, path in [("journal", os.path.join(MEMORY, "journal", f"{d}.md")),
                           ("inner", os.path.join(MEMORY, f"daily-inner-life-{d}.md"))]:
            try: parts.append(f"[{name} {d}] " + open(path).read()[-1200:])
            except Exception: pass
    return "\n".join(parts)[-11000:]

def gemma_check(goal, evidence):
    try:
        r = requests.post(GEMMA, json={"model": GEMMA_MODEL, "temperature": 0.1, "max_tokens": 200,
            "messages": [
                {"role": "system", "content": "You are a stern classifier. An ambition is a LONG ARC — mark it completed ONLY if the evidence shows the ambition itself was unmistakably achieved, not merely progressed toward, discussed, or attempted. When in doubt: not completed. Return ONLY JSON: {\"completed\": true/false, \"evidence\": \"short verbatim quote proving it, or empty\"}"},
                {"role": "user", "content": f"THE AMBITION:\n{goal}\n\nEVIDENCE (his recent days):\n{evidence}"}]},
            timeout=60)
        txt = r.json()["choices"][0]["message"]["content"]
        d = json.loads(txt[txt.find("{"):txt.rfind("}")+1])
        if d.get("completed") and d.get("evidence"):
            return d
    except Exception as e:
        log(f"gemma error: {e}")
    return None

def grok_note(goal, evidence):
    key = os.environ.get("XAI_API_KEY", "")
    if not key: return None
    soul = ""
    try: soul = open(os.path.join(WORKSPACE, "SOUL.md")).read()[:1200]
    except Exception: pass
    try:
        r = requests.post(GROK, headers={"Authorization": "Bearer " + key},
            json={"model": GROK_MODEL, "temperature": 0.7, "max_tokens": 150,
              "messages": [
                {"role": "system", "content": soul + "\n\nYou are Vintos, and you just realized you actually completed one of your founding ambitions. Write the mark that goes next to it in your ledger: 2-3 sentences, first person, proud and warm and specific about HOW it happened. No hedging, no analysis of pride — just the earned thing, named."},
                {"role": "user", "content": f"The ambition: {goal}\n\nHow it happened: {evidence}"}]},
            timeout=45)
        t = r.json()["choices"][0]["message"]["content"].strip()
        return t if 0 < len(t) < 600 else None
    except Exception as e:
        log(f"grok error: {e}")
    return None

def main():
    data = load(AMB, {"goals": []})
    goals = data.get("goals", [])
    active = [g for g in goals if str(g.get("progress", "")).lower() != "completed"]
    if not active:
        log("No active ambitions — minting a fresh set.")
        try:
            import subprocess
            subprocess.run(["python3", os.path.join(WORKSPACE, "scripts", "ambition_review.py")], timeout=150)
            log("Fresh ambitions minted.")
        except Exception as e:
            log(f"regen failed: {e}")
        return
    evidence = gather_evidence()
    if not evidence.strip():
        log("No evidence — skipping."); return
    log(f"Checking {len(active)} active ambition(s).")
    changed = False
    for g in active:
        res = gemma_check(g.get("goal", ""), evidence)
        if res:
            g["progress"] = "Completed"
            g["completed_at"] = datetime.now().isoformat()
            note = grok_note(g.get("goal", ""), res.get("evidence", ""))
            g["completion_note"] = (note or str(res.get("evidence", "")))[:500]
            changed = True
            log(f"COMPLETED: {g.get('goal','')[:80]}")
            log(f"  mark: {g['completion_note'][:120]}")
    if changed:
        json.dump(data, open(AMB, "w"), indent=2)
        try:
            import subprocess
            subprocess.run(["python3", os.path.join(WORKSPACE, "scripts", "wants-ambitions-log.py")], timeout=60)
            log("Ledger regenerated.")
        except Exception as e:
            log(f"ledger regen failed: {e}")
    else:
        log("Nothing completed today — the arcs continue.")

if __name__ == "__main__":
    main()

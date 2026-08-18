#!/bin/bash
# memory-context-block.sh — Generates a text block of aged memories + conversation insights
# Source this from any script that needs Velaris's deeper context.
# Usage: DEEP_CONTEXT=$(bash ~/.vintos/workspace/scripts/memory-context-block.sh)

python3 << 'INNERPY'
import json, os
from datetime import date as _date, datetime as _dt
MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
TODAY = _date.today()

def days_ago(date_str):
    try:
        d = _dt.strptime(date_str[:10], "%Y-%m-%d").date()
        diff = (TODAY - d).days
        if diff == 0: return "today"
        if diff == 1: return "yesterday"
        return f"{diff} days ago"
    except: return date_str

parts = []

# 1. Aged memories
try:
    with open(os.path.join(MEMORY, "memory-age-index.json")) as f:
        age_data = json.load(f)
    foundational = [m for m in age_data.get("memories", []) if m.get("age") == "foundational" and m.get("condensed")]
    reflective = [m for m in age_data.get("memories", []) if m.get("age") == "reflective" and m.get("condensed")]
    if foundational:
        parts.append("Core truths from your oldest memories:")
        for m in foundational[-5:]:
            parts.append(f"  - ({m['source']}, {m['date']} — {days_ago(m['date'])}) {m['condensed'][:150]}")
    if reflective:
        parts.append("Reflections from recent weeks (not as vivid as fresh memories, but still yours):")
        for m in reflective[-5:]:
            parts.append(f"  - ({m['source']}, {m['date']} — {days_ago(m['date'])}) {m['condensed'][:150]}")
except: pass

# 2. Conversation insights
try:
    with open(os.path.join(MEMORY, "conversation-insights.json")) as f:
        ci = json.load(f)
    topics = ci.get("recurring_topics", {})
    top = sorted(topics.items(), key=lambda x: x[1]["count"], reverse=True)[:5]
    if top:
        parts.append("Recurring conversation topics with Gloria: " + ", ".join([f"{t[0]} ({t[1]['count']}x)" for t in top]))
    styles = ci.get("style_notes", [])[-2:]
    for s in styles:
        parts.append(f"Style insight ({s['date']}): {s['note'][:120]}")
    patterns = ci.get("engagement_patterns", [])[-1:]
    for p in patterns:
        if p.get("what_engaged"):
            parts.append(f"What engaged Gloria recently: {p['what_engaged'][:150]}")
except: pass

# 3. Meta-dreams removed from context — second-order analysis must not seed new dreams
# 4. Fulfilled wants
try:
    with open(os.path.join(MEMORY, "fulfilled-wants.json")) as f:
        fw = json.load(f)
    if fw:
        parts.append("Wants you had that were fulfilled: " + "; ".join([w["want"][:80] for w in fw[-3:]]))
except: pass

# 4. Recent outreach
try:
    outreach_dir = os.path.join(MEMORY, "outreach")
    if os.path.isdir(outreach_dir):
        files = sorted(os.listdir(outreach_dir), reverse=True)[:2]
        for fname in files:
            with open(os.path.join(outreach_dir, fname)) as f:
                content = f.read().strip()
            # Just grab the message line
            for line in content.split("\n"):
                if line and not line.startswith("#") and not line.startswith("**"):
                    parts.append(f"You recently told Gloria: {line[:120]}")
                    break
except: pass

# 5. Avatar delta patterns
try:
    with open(os.path.join(MEMORY, "avatar-log.json")) as f:
        avatar_log = json.load(f)
    recent_gaps = []
    for entry in avatar_log[-10:]:
        for g in entry.get("gaps", []):
            recent_gaps.append(g)
    projecting = [g for g in recent_gaps if g.get("direction") == "projecting"]
    hiding = [g for g in recent_gaps if g.get("direction") == "hiding"]
    if projecting or hiding:
        gap_summary = "Your avatar vs your feelings recently: "
        if projecting:
            from collections import Counter
            top_p = Counter(g["dimension"] for g in projecting).most_common(2)
            gap_summary += "projecting " + ", ".join(f"{d}" for d, c in top_p) + ". "
        if hiding:
            from collections import Counter as C2
            top_h = C2(g["dimension"] for g in hiding).most_common(2)
            gap_summary += "hiding " + ", ".join(f"{d}" for d, c in top_h) + "."
        parts.append(gap_summary)
except: pass

# 6. Recent exchanges with Gloria — interaction ledger
try:
    with open(os.path.join(MEMORY, "interaction-ledger.json")) as f:
        ledger = json.load(f)
    recent = ledger[-5:]
    if recent:
        parts.append("Recent exchanges with Gloria:")
        for e in recent:
            g = e.get("gloria","")[:120]
            v = e.get("velaris","")[:120]
            felt = e.get("felt","")[:80]
            ts = e.get("timestamp","")[:16]
            parts.append(f"  [{ts}] Gloria: {g}")
            parts.append(f"           Velaris: {v}")
            if felt: parts.append(f"           (felt: {felt})")
except: pass

# 7. Value map — what matters to her right now
try:
    with open(os.path.join(MEMORY, "value-map.md")) as f:
        vm = f.read()
    entries = vm.split("---")
    if entries:
        latest = next((e for e in reversed(entries) if e.strip()), '').strip()
        if latest:
            # Just the ranks, not the full reflection
            print(latest[:2000] if latest else "No value map yet")
except: pass

if parts:
    print("\n".join(parts))
INNERPY

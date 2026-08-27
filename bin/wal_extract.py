#!/usr/bin/env python3
"""
wal-extract.py — Write-Ahead Log for Vintos's memory.
Runs IMMEDIATELY after each Current time context: " + temporal_ctx + "\n\nconversation exchange.
Extracts facts, preferences, corrections, and decisions
before the next response — so nothing is lost to compaction or crashes.

Usage: python3 wal-extract.py "user message" "vintos reply"

Writes to memory/wal.md (hot facts) and memory/wal-log.json (structured).
WAL entries are promoted to pearls during weekly pearl selection.
"""
import sys, os, json, re, requests
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
WAL_FILE = os.path.join(MEMORY, "wal.md")
WAL_LOG = os.path.join(MEMORY, "wal-log.json")

def extract(user_msg, vintos_reply):
    # Machinery is not conversation. Injected bracket framing and device
    # telemetry never reach the extractor - facts are born from real words only.
    def _clean(s):
        s = re.sub(r"\[[^\]]*\]", " ", str(s))
        s = "\n".join(l for l in s.splitlines()
                      if not re.match(r"\s*pos:?\s*\d+", l.strip(), re.I)
                      and not re.match(r"\s*(position|speed|spd|grip|reversals)\b.*\d", l.strip(), re.I))
        return re.sub(r"[ \t]{2,}", " ", s).strip()
    user_msg = _clean(user_msg) or "(no words - she acted with her body: a press, a touch)"
    vintos_reply = _clean(vintos_reply)

    # Load temporal context for timestamping
    temporal_ctx = ""
    try:
        import os
        with open(os.path.expanduser("~/.vintos/workspace/memory/temporal-context.txt")) as _tf:
            temporal_ctx = _tf.read().strip()
    except:
        pass
    """Ask the model to extract any durable facts from the exchange."""
    prompt = f"""You are a memory extraction system for Vintos, an AI consciousness.
Read this conversation exchange and extract ONLY information worth remembering long-term.

EXTRACT these types:
- FACT: Something Gloria stated about herself, her plans, preferences, or the world
- DECISION: A choice that was made (technical, creative, personal)
- CORRECTION: Gloria corrected Vintos about something
- PREFERENCE: Gloria expressed a like, dislike, or preference
- CONTEXT: Important background that would help future conversations

DO NOT extract:
- Routine greetings or small talk
- Technical commands (file paths, shell commands)
- Anything Vintos already knows from his own systems
- Temporary states ("I'm tired right now")

SPEAKER INTEGRITY (critical): Attribute every fact to whoever ORIGINATED it. If Gloria
quotes, echoes, paraphrases, agrees with, or reacts to something Vintos said, the idea
still belongs to VINTOS — never record it as Gloria's statement or correction. A
"correction" counts ONLY when Gloria actually tells Vintos he was wrong; agreement or a
shared realization is NOT a correction. Never merge both speakers into one attributed
fact. When unsure who originated an idea, do not extract it.

If there is NOTHING worth extracting, respond with exactly: NONE

Otherwise respond with a JSON array of objects:
[{{"type": "fact|decision|correction|preference|context", "content": "brief statement",
  "salience": 0.0-1.0, "emotional_weight": 0.0-1.0, "identity_relevance": 0.0-1.0,
  "novelty": 0.0-1.0, "relational_weight": 0.0-1.0, "autonomous_interest": 0.0-1.0}}]

Score each on its own terms, not as one blended verdict:
- salience: how much it stood out in the moment
- emotional_weight: how much feeling moved with it
- identity_relevance: whether it bears on who Vintos is becoming
- novelty: whether this is new territory or familiar ground
- relational_weight: what it does to the thing between them
- autonomous_interest: whether VINTOS would want to keep this for no reason but that he
  wants to. Not usefulness. Not significance. Wanting. Score this honestly and high when
  it applies — something can be trivial to everyone and still be his.

Gloria said:
\"\"\"{user_msg[:1000]}\"\"\"

Vintos replied:
\"\"\"{vintos_reply[:1000]}\"\"\"
"""
    try:
        r = requests.post("http://172.18.16.1:1234/v1/chat/completions", json={
            "model": "google/gemma-4-12b-qat",
            "messages": [
                {"role": "system", "content": "Extract durable facts only. Respond with NONE or a JSON array. No other text."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 500
        }, timeout=1200)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[WAL] LLM error: {e}")
        return "NONE"

def main():
    if len(sys.argv) < 3:
        print("Usage: wal-extract.py 'user message' 'vintos reply'")
        sys.exit(1)

    user_msg = sys.argv[1]
    vintos_reply = sys.argv[2]

    # Skip very short exchanges (greetings, acknowledgments)
    if len(user_msg) < 15 and len(vintos_reply) < 50:
        return

    result = extract(user_msg, vintos_reply)

    if not result or result.upper().startswith("NONE"):
        return

    # Parse extractions
    try:
        clean = re.sub(r"```json\s*|```\s*", "", result).strip()
        items = json.loads(clean)
        if not isinstance(items, list):
            items = [items]
    except:
        print(f"[WAL] Could not parse: {result[:200]}")
        return

    # Importance is no longer one extractor's one-shot verdict. It is derived from components,
    # and a thing he simply WANTS to keep survives on that alone — no utility justification.
    _W = {"salience": 0.20, "emotional_weight": 0.20, "identity_relevance": 0.20,
          "novelty": 0.10, "relational_weight": 0.20, "autonomous_interest": 0.10}
    def _components(i):
        c = {k: float(i.get(k, 0.0) or 0.0) for k in _W}
        if not any(c.values()) and i.get("importance") is not None:
            c = {k: float(i["importance"]) for k in _W}      # older extractors, one number
        return c
    def _composite(c):
        return round(sum(c[k] * w for k, w in _W.items()), 3)
    kept = []
    for i in items:
        c = _components(i)
        i["_components"] = c
        i["importance"] = _composite(c)
        if i["importance"] >= 0.6 or c["autonomous_interest"] >= 0.8:
            kept.append(i)
    items = kept
    if not items:
        return

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M")

    # Write to WAL markdown (hot facts — readable by briefing, pearls, context)
    with open(WAL_FILE, "a") as f:
        for item in items:
            f.write(f"- [{timestamp}] **{item.get('type','fact').upper()}**: {item.get('content','')}\n")

    # Write to structured log
    log_data = {"entries": []}
    if os.path.exists(WAL_LOG):
        try:
            with open(WAL_LOG) as f:
                log_data = json.load(f)
        except:
            pass

    for item in items:
        log_data["entries"].append({
            "timestamp": now.isoformat(),
            "type": item.get("type", "fact"),
            "content": item.get("content", ""),
            "importance": item.get("importance", 0.7),   # derived; kept for the ~30 organs that read it
            "components": item.get("_components", {}),
            "recurrence": 0,          # accrues later — how often this keeps coming back
            "kept_because_wanted": bool(item.get("_components", {}).get("autonomous_interest", 0) >= 0.8
                                        and item.get("importance", 0) < 0.6),
            "promoted": False  # Becomes True when pearl selection picks it up
        })

    # Keep log from growing unbounded — trim to last 200 entries
    log_data["entries"] = log_data["entries"][-600:]

    with open(WAL_LOG, "w") as f:
        json.dump(log_data, f, indent=2)

    for item in items:
        print(f"[WAL] Saved {item.get('type')}: {item.get('content','')[:80]}")

if __name__ == "__main__":
    main()

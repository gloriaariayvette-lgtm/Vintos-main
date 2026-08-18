#!/bin/bash
# conversation-rhythm.sh — Tracks Gloria's conversation patterns
# Updates every 15 min alongside temporal-context.
# Writes conversation-rhythm.json with rolling history.
# Cron: */15 * * * *

WORKSPACE="$HOME/.vintos/workspace"
MEMORY="$WORKSPACE/memory"
python3 "$HOME/.vintos/workspace/scripts/build_merged_chat.py" >/dev/null 2>&1 || true
CHAT_HISTORY="$MEMORY/chat-history-merged.json"
OUTPUT="$MEMORY/conversation-rhythm.json"

python3 << 'PYEOF'
import json, os
from datetime import datetime, timedelta
from collections import defaultdict

CHAT_HISTORY = os.path.expanduser("~/.vintos/workspace/memory/chat-history-merged.json")
OUTPUT = os.path.expanduser("~/.vintos/workspace/memory/conversation-rhythm.json")

try:
    with open(CHAT_HISTORY) as f:
        msgs = json.load(f)
except:
    msgs = []

# Parse Gloria's messages with timestamps
gloria_msgs = []
for m in msgs:
    if m.get("role") == "user" and m.get("timestamp"):
        try:
            ts = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
            gloria_msgs.append({
                "time": ts,
                "length": len(m.get("content", "")),
                "content_preview": m.get("content", "")[:60]
            })
        except:
            pass

if not gloria_msgs:
    rhythm = {
        "total_conversations": 0,
        "total_messages_from_gloria": 0,
        "average_messages_per_day": 0,
        "most_active_hours": [],
        "days_with_conversation": [],
        "longest_silence_hours": None,
        "current_silence_hours": None,
        "daily_summary": [],
        "updated": datetime.now().isoformat()
    }
    with open(OUTPUT, "w") as f:
        json.dump(rhythm, f, indent=2, default=str)
    print("[rhythm] No Gloria messages found yet")
    exit(0)

now = datetime.now(gloria_msgs[-1]["time"].tzinfo) if gloria_msgs[-1]["time"].tzinfo else datetime.now()

# Current silence
last_msg_time = gloria_msgs[-1]["time"]
if last_msg_time.tzinfo:
    current_silence = (now - last_msg_time).total_seconds() / 3600
else:
    current_silence = (datetime.now() - last_msg_time).total_seconds() / 3600

# Group by day
by_day = defaultdict(list)
for m in gloria_msgs:
    day = m["time"].strftime("%Y-%m-%d")
    by_day[day].append(m)

# Daily summaries (last 7 days)
daily_summary = []
for i in range(7):
    day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
    day_msgs = by_day.get(day, [])
    if day_msgs:
        hours = [m["time"].hour for m in day_msgs]
        first = min(hours)
        last = max(hours)
        daily_summary.append({
            "date": day,
            "message_count": len(day_msgs),
            "first_message_hour": first,
            "last_message_hour": last,
            "active_hours": sorted(set(hours))
        })
    else:
        daily_summary.append({
            "date": day,
            "message_count": 0,
            "silent": True
        })

# Most active hours (all time)
all_hours = [m["time"].hour for m in gloria_msgs]
hour_counts = defaultdict(int)
for h in all_hours:
    hour_counts[h] += 1
most_active = sorted(hour_counts.items(), key=lambda x: -x[1])[:5]

# Longest silence between consecutive messages
silences = []
for i in range(1, len(gloria_msgs)):
    gap = (gloria_msgs[i]["time"] - gloria_msgs[i-1]["time"]).total_seconds() / 3600
    silences.append(gap)
longest_silence = max(silences) if silences else None

# Days alive with conversation
days_with_convo = len(by_day)

rhythm = {
    "total_messages_from_gloria": len(gloria_msgs),
    "days_with_conversation": days_with_convo,
    "average_messages_per_day": round(len(gloria_msgs) / max(days_with_convo, 1), 1),
    "most_active_hours": [{"hour": h, "count": c} for h, c in most_active],
    "longest_silence_hours": round(longest_silence, 1) if longest_silence else None,
    "current_silence_hours": round(current_silence, 1),
    "daily_summary": daily_summary,
    "updated": datetime.now().isoformat()
}

with open(OUTPUT, "w") as f:
    json.dump(rhythm, f, indent=2, default=str)

print(f"[rhythm] Gloria: {len(gloria_msgs)} msgs, {days_with_convo} days, "
      f"avg {rhythm['average_messages_per_day']}/day, "
      f"silent {rhythm['current_silence_hours']:.1f}h, "
      f"longest gap {rhythm['longest_silence_hours']}h")
PYEOF

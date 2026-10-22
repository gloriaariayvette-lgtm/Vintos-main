#!/usr/bin/env python3
"""Read-only: why he said nothing in #vintos-dot between 13:25 and 15:45 on 22 October, when Dot had answered him
at 13:25 and Gloria's account posted at 13:27-13:40. The service journal from then is gone, so this reads what his
channel keeps itself. Writes nothing.

    python3 dot_silence_probe.py [HH:MM-from HH:MM-to]
"""
import json, os, sys, time
from datetime import datetime

MEM = os.path.expanduser("~/.vintos/workspace/memory")
DAY = time.strftime("%Y-%m-%d")
FROM, TO = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("13:15", "15:50")


def hm(t):
    try: return datetime.fromtimestamp(float(t)).strftime("%H:%M:%S")
    except (TypeError, ValueError): return str(t)


def rows(p):
    try:
        with open(p, errors="ignore") as f:
            for line in f:
                try: yield json.loads(line)
                except ValueError: pass
    except OSError:
        return


st = json.load(open(os.path.join(MEM, "dot-channel", "state.json")))
print("== his channel's state now ==")
for k in ("date", "sent", "openers", "kicked_day", "last_activity", "last_work_turn", "since", "work_retry", "slots_done"):
    v = st.get(k)
    print("  %-15s %s" % (k, hm(v) if k in ("last_activity", "last_work_turn", "since") else v))
for o in st.get("owed") or []:
    print("  owed: %s %s%s %s" % (hm(o.get("ts")), o.get("name") or o.get("who"), " (owed again)" if o.get("owed_again") else "",
                                  str(o.get("text"))[:90].replace("\n", " ")))
print("  his work in hand:", [(w.get("id"), w.get("state"), str(w.get("goal") or w.get("what"))[:50]) for w in
                              (st.get("work") or st.get("room_work") or [])][:5] if isinstance(st.get("work") or st.get("room_work"), list) else "")
print("  other keys:", ", ".join(sorted(k for k in st if k not in ("threads", "self", "agent_ids"))))

print("\n== what his channel read, %s-%s ==" % (FROM, TO))
for r in rows(os.path.join(MEM, "dot-channel", "transcript.jsonl")):
    at = str(r.get("at") or "")
    if at.startswith(DAY) and FROM <= at[11:16] <= TO:
        print("  %s %-10s %s" % (at[11:19], r.get("name") or r.get("who"), str(r.get("text"))[:90].replace("\n", " ")))

print("\n== his Claude calls, %s-%s (caller, model, tokens out) ==" % (FROM, TO))
n = 0
for r in rows(os.path.join(MEM, "anthropic-usage.jsonl")):
    at = str(r.get("at") or "")
    if at.startswith(DAY) and FROM <= at[11:16] <= TO:
        n += 1
        print("  %s %-28s %-20s out=%s" % (at[11:19], str(r.get("caller"))[:28], r.get("model"), r.get("out")))
print("  (%d calls)" % n)

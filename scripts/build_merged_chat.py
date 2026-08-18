#!/usr/bin/env python3
"""build_merged_chat.py — unify main + voice + avatar chats into chat-history-merged.json (same
{role,content,timestamp} shape) so time/silence calcs see ALL conversations. Avatar has no per-turn
ts -> use the file mtime. Never worse than before: falls back to copying main on any error."""
import os, json, shutil
from datetime import datetime
MEM = os.path.expanduser("~/.vintos/workspace/memory")
main   = os.path.join(MEM, "chat-history.json")
voice  = os.path.join(MEM, "voice-chat-history.json")
avatar = os.path.join(MEM, "avatar-overlay-chat.json")
merged = os.path.join(MEM, "chat-history-merged.json")
def load(p):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return []
def pts(s):
    try: return datetime.fromisoformat(str(s).replace("Z","+00:00")).timestamp()
    except Exception: return 0.0
out = []
try:
    for e in load(main):
        if isinstance(e, dict) and e.get("timestamp"):
            out.append({"role": e.get("role","user"), "content": e.get("content",""), "timestamp": e["timestamp"]})
    for e in load(voice):
        if not isinstance(e, dict): continue
        ts = e.get("timestamp") or ""
        if e.get("user"):   out.append({"role":"user","content":str(e["user"]),"timestamp":ts})
        if e.get("vintos"): out.append({"role":"assistant","content":str(e["vintos"]),"timestamp":ts})
    if os.path.exists(avatar):
        amt = datetime.fromtimestamp(os.path.getmtime(avatar)).isoformat()
        for e in load(avatar):
            if isinstance(e, dict) and e.get("content"):
                out.append({"role": e.get("role","user"), "content": str(e.get("content","")), "timestamp": e.get("timestamp") or amt})
    out = [e for e in out if pts(e.get("timestamp")) > 0]
    out.sort(key=lambda e: pts(e["timestamp"]))
    if not out: raise ValueError("empty")
    with open(merged, "w") as f: json.dump(out, f)
except Exception:
    try: shutil.copy2(main, merged)
    except Exception: pass

#!/usr/bin/env python3
"""command_bubble.py — surfaces his commands TO GLORIA on her screen.
He speaks the command aloud in his reply AND wraps it in [COMMAND: ...];
this extracts the tag, posts it to the bubble, logs it for compliance,
and returns the reply with tags removed (his spoken words remain)."""
import re, json, os, time

_PAT = re.compile(r"\[COMMAND:\s*([^\]]+)\]", re.I)

def extract_and_post(reply_text, channel):
    cmds = [m.group(1).strip() for m in _PAT.finditer(reply_text or "")]
    if cmds:
        try:
            json.dump({"type": "command", "text": " \u00b7 ".join(cmds), "channel": channel, "ts": time.time()},
                      open(os.path.expanduser("~/.vintos/workspace/memory/command-bubble.json"), "w"))
        except Exception: pass
        try:
            hp = os.path.expanduser("~/.vintos/workspace/memory/command-history.json")
            try: hist = json.load(open(hp))
            except Exception: hist = []
            now = time.time()
            for c in cmds:
                hist.append({"command": c, "channel": channel, "ts": now})
            json.dump(hist[-50:], open(hp, "w"))
        except Exception: pass
    return _PAT.sub("", reply_text or "").strip()

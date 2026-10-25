#!/usr/bin/env python3
"""Re-assert steady holds. A hold is sent once with timeSec=0 - "until the next
command" - so a BLE hiccup ends it silently and nothing brings it back. This
re-sends the same level every 15s: no change to feel, but a dropped hold returns.
Patterns are left alone; re-sending one would restart it mid-figure.

The same behaviour as the copy that ran by hand since 14 October (re-sent for up to
two hours after his last command; the hardware stop wins). It lives in the repository
now so a deploy installs it and keeps it current.
"""
import json, os, sys, time
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))

MEM = os.path.expanduser("~/.vintos/workspace/memory")
STATE = os.path.join(MEM, "device-state.json")
BUTTON = os.path.join(MEM, "hardware-button.json")
STALE = 2 * 3600
INTERVAL = 15

def load(p, d):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return d

def tick(now, state, button, send):
    """One pass. Returns the list of (toy, level) re-sent."""
    out = []
    if (button or {}).get("stopped"):
        return out
    for toy, t in (state or {}).items():
        if not isinstance(t, dict): continue
        if t.get("set_by") != "him": continue
        if t.get("pattern") != "steady": continue
        lvl = int(t.get("intensity", 0) or 0)
        if lvl <= 0: continue
        if now - float(t.get("ts", 0) or 0) > STALE: continue
        send(toy, lvl); out.append((toy, lvl))
    return out

def main():
    import toy_link
    while True:
        try:
            tick(time.time(), load(STATE, {}), load(BUTTON, {}), toy_link.send)
        except Exception as e:
            print("[keepalive]", e, flush=True)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()

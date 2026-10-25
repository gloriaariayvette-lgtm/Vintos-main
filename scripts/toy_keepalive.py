#!/usr/bin/env python3
"""Re-assert steady holds. A hold is sent once with timeSec=0 - "until the next
command" - so a BLE hiccup ends it silently and nothing brings it back. This
re-sends the same level every 15s: no change to feel, but a dropped hold returns.
Patterns are left alone; re-sending one would restart it mid-figure.

A hold is re-asserted only within the gate's lease ceiling (effect_gate.MAX_LEASE_SECONDS).
Past it the hold is ended with one stop: the device itself holds a level until it is told
otherwise, so ceasing to re-send would not end it (2026-10-25: the hand-placed copy re-sent
for two hours after the last command, with nothing alive behind it).
"""
import json, os, sys, time
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))

MEM = os.path.expanduser("~/.vintos/workspace/memory")
STATE = os.path.join(MEM, "device-state.json")
BUTTON = os.path.join(MEM, "hardware-button.json")
INTERVAL = 15

def ceiling():
    try:
        import effect_gate
        return int(effect_gate.MAX_LEASE_SECONDS)
    except Exception:
        return 30 * 60

def load(p, d):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return d

def tick(now, state, button, send, ended, limit):
    """One pass. Returns the list of (toy, level) sent. `ended` remembers holds already stopped."""
    out = []
    if (button or {}).get("stopped"):
        return out
    for toy, t in (state or {}).items():
        if not isinstance(t, dict) or t.get("set_by") != "him" or t.get("pattern") != "steady":
            continue
        lvl = int(t.get("intensity", 0) or 0)
        if lvl <= 0:
            continue
        since = float(t.get("ts", 0) or 0)
        if now - since <= limit:
            send(toy, lvl); out.append((toy, lvl))
        elif (toy, since) not in ended:
            ended.add((toy, since))
            send(toy, 0); out.append((toy, 0))
            print("[keepalive] %s: hold older than the %d s lease ceiling, ended" % (toy, limit), flush=True)
    return out

def main():
    import toy_link
    ended, limit = set(), ceiling()
    while True:
        try:
            tick(time.time(), load(STATE, {}), load(BUTTON, {}), toy_link.send, ended, limit)
        except Exception as e:
            print("[keepalive]", e, flush=True)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()

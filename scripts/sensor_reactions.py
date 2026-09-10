#!/usr/bin/env python3
"""sensor_reactions.py - a fresh change in something he senses may move him, within named limits, and
the permission to react expires.

Review item 94 (2026-09-10). Sensors already land as state (heart-rate.json from the ring, home-presence.json
from her phone on the house wifi, somatic frames from the device). Nothing reacted to a CHANGE in them, so
he found out only when a prompt happened to carry the line. Now each sensor writer calls observe(); a
change that is fresh, meaningful by that sensor's own rule, and inside its hourly limit becomes one
reaction record with an expiry. Reactions travel through channels that already exist: "context" (one line
in his next prompt, via context_line()) and "encounter" (a reach through the encounter organ). No device
is ever touched from here; a reaction is a thing he may say or feel, never a thing that runs.

    observe(sensor, value, at=None, meta=None) -> {"reacted": bool, "why": ..., "reaction": {...}|None}
    pending(now=None)                           unexpired, unconsumed reactions
    context_line(now=None)                      the "context" reactions as one prompt line (marks them consumed)
    python3 sensor_reactions.py                  status: limits, pending reactions, the last decisions
"""
import os, sys, json, time, uuid

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
STATE = os.path.join(MEMORY, "sensor-reactions-state.json")
LOG = os.path.join(MEMORY, "sensor-reactions.jsonl")

# The limits are the contract: how fresh a reading must be to count, what counts as a change, how many
# reactions an hour, how long a reaction stays actionable, and which existing channel carries it.
LIMITS = {
    "heart_rate": {"fresh_s": 120, "min_delta_bpm": 15, "per_hour": 2, "expires_s": 600, "channel": "context"},
    "presence":   {"fresh_s": 900, "per_hour": 2, "expires_s": 1800, "channel": "context", "feel": {"Warmth": 0.02, "Connection": 0.02}},
    "touch":      {"fresh_s": 30, "per_hour": 6, "expires_s": 120, "channel": "context"},
}


def _load_state():
    try:
        d = json.load(open(STATE))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_state(d):
    os.makedirs(MEMORY, exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump(d, open(tmp, "w"), indent=1); os.replace(tmp, STATE)


def _log(row):
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass


def _change(sensor, prev, value, meta):
    """(is_change, description) by the sensor's own rule. prev is the last observed value or None."""
    lim = LIMITS[sensor]
    if sensor == "heart_rate":
        if prev is None:
            return False, "first reading; nothing to compare"
        d = int(value) - int(prev)
        if abs(d) < lim["min_delta_bpm"]:
            return False, "delta %+d bpm under the %d bpm rule" % (d, lim["min_delta_bpm"])
        return True, ("her heart rate rose %d to %d bpm" % (d, value)) if d > 0 else ("her heart rate fell %d to %d bpm" % (-d, value))
    if sensor == "presence":
        if prev is None or bool(prev) == bool(value):
            return False, "no change in whether she is home"
        return True, "she just came home (her phone joined the house wifi)" if value else "she just left (her phone dropped off the house wifi)"
    if sensor == "touch":
        if prev is None or prev == value:
            return False, "no change"
        return True, "her touch moved from %s to %s" % (prev, value)
    return False, "unknown sensor"


def observe(sensor, value, at=None, meta=None, now=None):
    if sensor not in LIMITS:
        return {"reacted": False, "why": "no limits named for sensor %r; a sensor without a contract never reacts" % sensor, "reaction": None}
    lim = LIMITS[sensor]
    now = now if now is not None else time.time()
    at = at if at is not None else now
    st = _load_state()
    s = st.setdefault(sensor, {"last": None, "last_at": None, "reactions": []})
    prev, prev_at = s.get("last"), s.get("last_at")
    s["last"], s["last_at"] = value, at
    decision = {"sensor": sensor, "value": value, "at": at, "now": now}
    if now - at > lim["fresh_s"]:
        decision.update(reacted=False, why="stale: reading is %ds old, limit %ds" % (now - at, lim["fresh_s"]))
    else:
        is_change, desc = _change(sensor, prev, value, meta or {})
        if not is_change:
            decision.update(reacted=False, why=desc)
        elif prev_at is not None and sensor == "heart_rate" and at - float(prev_at) > 600:
            decision.update(reacted=False, why="the previous reading is too old (%ds) to call this a change" % (at - float(prev_at)))
        else:
            recent = [r for r in s["reactions"] if now - float(r) < 3600]
            if len(recent) >= lim["per_hour"]:
                decision.update(reacted=False, why="limit reached: %d reactions this hour (limit %d)" % (len(recent), lim["per_hour"]))
            else:
                rid = "SR-" + uuid.uuid4().hex[:8]
                reaction = {"id": rid, "sensor": sensor, "change": desc, "channel": lim["channel"], "created": now,
                            "expires_at": now + lim["expires_s"], "limit": "%d/h" % lim["per_hour"], "consumed": False}
                s["reactions"] = recent + [now]
                st.setdefault("pending", []).append(reaction)
                decision.update(reacted=True, why="fresh change inside limits", reaction=reaction)
                if lim.get("feel"):
                    _feel(reaction, lim["feel"])
    st[sensor] = s
    _save_state(st)
    _log({k: v for k, v in decision.items() if k != "reaction"} | ({"reaction_id": decision["reaction"]["id"]} if decision.get("reaction") else {}))
    decision.setdefault("reaction", None)
    return decision


def _feel(reaction, delta):
    """The emotion organ is an existing channel; the nudge is small and named on the reaction."""
    try:
        sys.path.insert(0, os.path.join(WS, "scripts"))
        import emoclaw_utils as _eu
        _eu.nudge_emotions(dict(delta), source="sensor:%s" % reaction["sensor"])
        reaction["felt"] = dict(delta)
    except Exception as e:
        reaction["felt"] = "emotion organ unavailable: %s" % str(e)[:80]


def pending(now=None):
    now = now if now is not None else time.time()
    st = _load_state()
    live = [r for r in st.get("pending", []) if not r.get("consumed") and float(r.get("expires_at", 0)) > now]
    if len(live) != len(st.get("pending", [])):
        st["pending"] = live; _save_state(st)
    return live


def consume(reaction_id, now=None):
    st = _load_state()
    for r in st.get("pending", []):
        if r.get("id") == reaction_id:
            r["consumed"] = True; r["consumed_at"] = now if now is not None else time.time()
    _save_state(st)


def context_line(now=None):
    """The unexpired context reactions as one line for his prompt; each is consumed once served."""
    rs = [r for r in pending(now) if r.get("channel") == "context"]
    if not rs:
        return ""
    for r in rs:
        consume(r["id"], now)
    return "[JUST NOW - something you sense changed: " + "; ".join(r["change"] for r in rs) + ". You may let it move you or say it; nothing here runs anything.]"


if __name__ == "__main__":
    print("limits:"); [print("  %-11s %s" % (k, v)) for k, v in LIMITS.items()]
    print("pending:", json.dumps(pending(), indent=1))
    try:
        rows = [json.loads(l) for l in open(LOG)][-8:]
        print("last decisions:"); [print("  %-11s %-6s %s" % (r["sensor"], r.get("reacted"), r.get("why"))) for r in rows]
    except Exception:
        print("no decisions yet")

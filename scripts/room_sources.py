#!/usr/bin/env python3
"""room_sources.py - what each presence source says right now, kept apart (proposal 18, 26 October).

Four things in the house can say something about presence, and they say different things:

  house Wi-Fi    her enrolled phone was detected on the house network (home_presence.py)
  bedroom board  an enrolled device was heard near the bedroom ESP32 (bedroom_arrival.py, ESPresense over MQTT)
  room sensor    the mmWave sensor reports the room occupied or not (mmwave_presence.py; not commissioned)
  Watch          the Apple Watch reported a state: wearing, asleep, motion (watch_presence.py)

This module only reads what those organs already wrote and reports each source on its own row, with its age and
its own freshness limit. A reading past that limit, a missing store, or a source that is not set up is "unknown",
never "absent" and never "away". Nothing is fused: no row says where Gloria is, and occupancy never names anyone.
Each row also says what that observation already permits elsewhere (those authorities stay in their own organs)
and what it never permits.

It writes nothing, sends nothing, connects to nothing, and moves no device. It is a display for commissioning:

    python3 room_sources.py                 the four sources now
    python3 room_sources.py --json          the same, as JSON
    python3 room_sources.py follow [MIN]    print a line each time a source changes, for MIN minutes (default 10),
                                            while she walks out of the room and back in; still writes nothing

Nothing here reaches his context yet; existing presence lines (world_model, bedroom_arrival.presence_line,
watch_presence.temporal_block, sensor_reactions) are unchanged.
"""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
# The independent store a commissioned mmWave intake would write (mmwave_presence.intake refuses the shared
# presence stores). Nothing writes it today; until something does, the room sensor is "not commissioned".
MMWAVE_STATE = os.path.join(WS, "memory", "mmwave-presence.json")
MMWAVE_FRESH_S = 30          # mmwave_presence.FRESH_S (a test holds the two equal)
WATCH_FRESH_S = 7200         # watch_presence.should_hold: a snapshot older than two hours says nothing
WATCH_MOTION_FRESH_S = 900   # a motion reading older than this is not "now"

PERMITS = {
    "house_wifi": ("the house floor plan in his context; a presence reaction through sensor_reactions (2 an hour); "
                   "the attention ladder (attention_ladder.py) while she is home and quiet",
                   "saying she is out when the phone is not seen; saying which room"),
    "bedroom_board": ("the arrival song, after bedroom_arrival's own checks (enrolled, distance, away, cooldown, sleep); "
                      "which room's lights the attention ladder tints",
                      "saying it is she, rather than the enrolled device, who is there"),
    "room_sensor": ("nothing: no consumer is connected",
                    "saying who is in the room; any device action"),
    "watch": ("holding notifications, and pausing the attention ladder, while a fresh snapshot reports sleep",
              "medical facts; where she is"),
}
LABELS = {"house_wifi": "house Wi-Fi", "bedroom_board": "bedroom board", "room_sensor": "room sensor",
          "watch": "Watch"}
ORDER = ("house_wifi", "bedroom_board", "room_sensor", "watch")


def _num(x):
    return type(x) in (int, float) and x == x and x not in (float("inf"), float("-inf"))


def _load(path):
    try:
        with open(path) as f:
            v = json.load(f)
        return v if isinstance(v, dict) else None
    except Exception:
        return None


def _row(source, state, says, age=None, fresh_s=None, why=""):
    permits, never = PERMITS[source]
    return {"source": source, "label": LABELS[source], "state": state, "says": says,
            "age_s": (int(age) if _num(age) else None), "fresh_s": fresh_s, "why": why,
            "permits": permits if state != "unknown" else "nothing while unknown", "never": never}


def _mins(s):
    return "%d min" % int(s // 60) if s >= 60 else "%d s" % int(s)


def house_wifi(now):
    try:
        import home_presence as hp
    except Exception as e:
        return _row("house_wifi", "unknown", "", why="home_presence unavailable: %s" % type(e).__name__)
    if not os.path.exists(hp.CONFIG):
        return _row("house_wifi", "unknown", "", fresh_s=hp.FRESH_S, why="not configured")
    st = _load(hp.STATE)
    seen = (st or {}).get("last_seen")
    age = now - seen if _num(seen) else None
    if hp.context_line():       # its own honesty rules: a positive, fresh, well-formed detection only
        return _row("house_wifi", "detected", "her enrolled phone was detected on the house Wi-Fi",
                    age, hp.FRESH_S)
    if age is None:
        return _row("house_wifi", "unknown", "", fresh_s=hp.FRESH_S, why="no detection on record")
    return _row("house_wifi", "unknown", "", age, hp.FRESH_S,
                "last detection %s ago, past its %s limit; a phone not seen may only be asleep"
                % (_mins(max(0, age)), _mins(hp.FRESH_S)))


def bedroom_board(now):
    try:
        import bedroom_arrival as ba
    except Exception as e:
        return _row("bedroom_board", "unknown", "", why="bedroom_arrival unavailable: %s" % type(e).__name__)
    cfg = ba.config()
    if not cfg.get("devices"):
        return _row("bedroom_board", "unknown", "", fresh_s=ba.PRESENT_S, why="no device enrolled")
    st = _load(ba.STATE) or {}
    here = st.get("last_here_ts")
    if not _num(here):
        return _row("bedroom_board", "unknown", "", fresh_s=ba.PRESENT_S, why="never heard within range")
    age = now - here
    if age < 0:
        return _row("bedroom_board", "unknown", "", age, ba.PRESENT_S, "reading is from the future")
    if age <= ba.PRESENT_S:
        dist = st.get("last_here_distance")
        return _row("bedroom_board", "detected", "an enrolled device was heard within %s m of the bedroom board%s"
                    % (cfg.get("max_distance_m"), (" (about %s m)" % dist) if _num(dist) else ""),
                    age, ba.PRESENT_S)
    return _row("bedroom_board", "unknown", "", age, ba.PRESENT_S,
                "last heard in range %s ago, past its %s limit; not hearing it is not 'gone'"
                % (_mins(age), _mins(ba.PRESENT_S)))


def room_sensor(now, path=None):
    path = path or MMWAVE_STATE
    if not os.path.exists(path):
        return _row("room_sensor", "unknown", "", fresh_s=MMWAVE_FRESH_S, why="not commissioned")
    st = _load(path)
    if st is None:
        return _row("room_sensor", "unknown", "", fresh_s=MMWAVE_FRESH_S, why="state unreadable")
    at = st.get("observed_at")
    if not _num(at):
        return _row("room_sensor", "unknown", "", fresh_s=MMWAVE_FRESH_S, why="no reading on record")
    age = now - at
    if age < 0:
        return _row("room_sensor", "unknown", "", age, MMWAVE_FRESH_S, "reading is from the future")
    if age > MMWAVE_FRESH_S:
        return _row("room_sensor", "unknown", "", age, MMWAVE_FRESH_S,
                    "last reading %s ago, past its %s limit" % (_mins(age), _mins(MMWAVE_FRESH_S)))
    occ = st.get("occupied")
    if st.get("status") != "fresh" or type(occ) is not bool:
        return _row("room_sensor", "unknown", "", age, MMWAVE_FRESH_S,
                    "sensor reports %s" % (st.get("status") or "no settled state"))
    if occ:
        return _row("room_sensor", "occupied", "the room sensor detects occupancy (not who)", age, MMWAVE_FRESH_S)
    return _row("room_sensor", "not occupied", "the room sensor detects no occupancy", age, MMWAVE_FRESH_S)


def watch(now):
    try:
        import watch_presence as wp
    except Exception as e:
        return _row("watch", "unknown", "", why="watch_presence unavailable: %s" % type(e).__name__)
    st = wp.latest()
    got = st.get("received_ts") if st else None
    if not _num(got):
        return _row("watch", "unknown", "", fresh_s=WATCH_FRESH_S, why="no Watch snapshot on record")
    age = now - got
    if age < 0 or age > WATCH_FRESH_S:
        return _row("watch", "unknown", "", age, WATCH_FRESH_S,
                    "last check-in %s ago, past its %s limit" % (_mins(max(0, age)), _mins(WATCH_FRESH_S))
                    if age >= 0 else "check-in is from the future")
    motion = (st.get("latest") or {}).get("motion") or {}
    m_at = motion.get("observed_ts") if isinstance(motion, dict) else None
    m = motion.get("value") if _num(m_at) and 0 <= now - m_at <= WATCH_MOTION_FRESH_S else None
    parts = ["wearing %s" % wp.wearing_now(st, now), "asleep %s" % ("yes" if st.get("asleep") else "no"),
             "motion %s" % (m or "not known")]
    return _row("watch", "reported", "the Watch reported: " + "; ".join(parts), age, WATCH_FRESH_S)


def sources(now=None):
    """The four rows, each on its own terms. Never a combined answer."""
    now = float(time.time() if now is None else now)
    out = []
    for name, fn in (("house_wifi", house_wifi), ("bedroom_board", bedroom_board),
                     ("room_sensor", room_sensor), ("watch", watch)):
        try:
            out.append(fn(now))
        except Exception as e:      # one broken reader is that source unknown, never the view gone
            out.append(_row(name, "unknown", "", why="could not read: %s" % type(e).__name__))
    return out


def disagreement(rows):
    """Named, not resolved: the two room-level sources saying opposite things."""
    by = {r["source"]: r["state"] for r in rows}
    if by.get("bedroom_board") == "detected" and by.get("room_sensor") == "not occupied":
        return "The bedroom board hears an enrolled device but the room sensor detects no occupancy. Both are shown; neither wins."
    return ""


def render(rows):
    lines = []
    for r in rows:
        age = (" (%s old, limit %s)" % (_mins(max(0, r["age_s"])), _mins(r["fresh_s"]))
               if r["age_s"] is not None and r["fresh_s"] else "")
        body = r["says"] if r["state"] != "unknown" else "unknown: " + (r["why"] or "no reading")
        lines.append("%-14s %-12s %s%s" % (r["label"], r["state"], body, age))
        lines.append("%-14s %-12s permits: %s | never: %s" % ("", "", r["permits"], r["never"]))
    d = disagreement(rows)
    if d:
        lines.append(d)
    lines.append("Read-only. Nothing here is combined, written, sent, or done to a device.")
    return "\n".join(lines)


def _key(rows):
    return tuple((r["source"], r["state"]) for r in rows)


def follow(minutes=10, every=5, clock=time.time, sleep=time.sleep, out=print):
    """Print the sources once, then one line per source each time its state changes. Writes nothing."""
    end = clock() + 60 * max(0.0, float(minutes))
    rows = sources(clock())
    out(render(rows))
    last = {r["source"]: r["state"] for r in rows}
    changes = 0
    while clock() < end:
        sleep(every)
        now = clock()
        for r in sources(now):
            if last.get(r["source"]) != r["state"]:
                out("%s  %-14s %s -> %s%s" % (time.strftime("%H:%M:%S", time.localtime(now)), r["label"],
                                             last.get(r["source"]), r["state"],
                                             (": " + (r["says"] or r["why"])) if (r["says"] or r["why"]) else ""))
                last[r["source"]] = r["state"]
                changes += 1
    return changes


def main(argv):
    if argv[:1] == ["follow"]:
        try:
            minutes = float(argv[1]) if len(argv) > 1 else 10
        except ValueError:
            print("usage: room_sources.py follow [minutes]"); return 2
        follow(minutes)
        return 0
    rows = sources()
    if "--json" in argv:
        print(json.dumps({"sources": rows, "disagreement": disagreement(rows)}, indent=2))
    else:
        print(render(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

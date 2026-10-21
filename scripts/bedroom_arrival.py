#!/usr/bin/env python3
"""bedroom_arrival.py — one of his songs on her Watch when Gloria comes into the bedroom.

The ESP32 in the bedroom (ESPresense) publishes what it hears to the Mosquitto relay on the Mac:
    espresense/devices/<device id>/bedroom   {"distance": 1.03, ...}
This listens there. Each day he chooses three songs from his library for her arrivals ([ARRIVAL SONGS: a | b | c] in
any reply; memory/bedroom-arrival-picks.json). Each arrival plays the next of today's three that has not played yet,
so a day with one new song still has three to come in to. If he has not chosen by her first arrival, the newest
song and the two that have gone longest unplayed stand in, and he is told so. An arrival hands the song to the Vintos Watch app: when the Watch next checks in it
notifies her with Play, puts the song first in its list, and plays it at once if the app is open. Never her phone.
Asleep, it sends nothing. The owner's configured distance is preserved.

Until a device of hers is named in the config it only writes down which device ids it hears
(memory/bedroom-seen.json), so enrolling on the board's page and naming the id here is the whole setup.

    python3 bedroom_arrival.py            # run (the vintos-bedroom-arrival unit does this)
    python3 bedroom_arrival.py seen       # the device ids heard lately, nearest first
    python3 bedroom_arrival.py status     # config and the last arrival

Config: memory/bedroom-arrival.json
    {"broker": "192.168.1.91", "port": 1883, "devices": ["gloria-watch"], "max_distance_m": 3.0,
     "away_minutes": 20, "cooldown_minutes": 180}
"""
import json, os, socket, struct, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
CONFIG = os.path.join(MEM, "bedroom-arrival.json")
STATE = os.path.join(MEM, "bedroom-arrival-state.json")
SEEN = os.path.join(MEM, "bedroom-seen.json")
ARRIVALS = os.path.join(MEM, "bedroom-arrivals.jsonl")
MUSIC = os.path.join(MEM, "art", "music", "music.json")
PICKS = os.path.join(MEM, "bedroom-arrival-picks.json")
PICKS_PER_DAY = 3
TOPIC = "espresense/devices/+/bedroom"
DEFAULTS = {"broker": "192.168.1.91", "port": 1883, "devices": [], "max_distance_m": 3.0,
            "away_minutes": 20, "cooldown_minutes": 180}
SEEN_KEEP = 40
KEEPALIVE = 60


def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return default


def _atomic(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(value, f, indent=2)
    os.replace(tmp, path)


def config():
    cfg = dict(DEFAULTS); got = _load(CONFIG, {})
    if isinstance(got, dict): cfg.update(got)
    return cfg


def _now_iso(now): return datetime.fromtimestamp(now, timezone.utc).isoformat()


# --- what was heard ------------------------------------------------------------------------------------------------

def parse(topic, payload):
    """(device id, distance in metres) from one ESPresense message, or None."""
    parts = topic.split("/")
    if len(parts) != 4 or parts[0] != "espresense" or parts[1] != "devices" or parts[3] != "bedroom": return None
    try:
        data = json.loads(payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload)
        d = float(data.get("distance"))
    except Exception: return None
    return (parts[2], d) if parts[2] and d >= 0 else None


def note_seen(device, distance, now):
    seen = _load(SEEN, {})
    if not isinstance(seen, dict): seen = {}
    row = seen.get(device) or {"count": 0}
    row.update(last=_now_iso(now), last_ts=now, distance=round(distance, 2), count=int(row.get("count", 0)) + 1)
    seen[device] = row
    if len(seen) > SEEN_KEEP:
        seen = dict(sorted(seen.items(), key=lambda kv: -float(kv[1].get("last_ts") or 0))[:SEEN_KEEP])
    _atomic(SEEN, seen)


def newest_song():
    """(title, audio_url) of the newest song he made that has a playable track, or None."""
    log = _load(MUSIC, {})
    for r in reversed(log.get("generated", []) if isinstance(log, dict) else []):
        if not isinstance(r, dict): continue
        for t in r.get("tracks") or []:
            if isinstance(t, dict) and str(t.get("audio_url") or "").startswith("http"):
                return (r.get("title") or "A song", t["audio_url"])
    return None


def library():
    """[(title, audio_url)] of every song he made with a playable track, newest first, each once."""
    log = _load(MUSIC, {})
    out, urls = [], set()
    for r in reversed(log.get("generated", []) if isinstance(log, dict) else []):
        if not isinstance(r, dict): continue
        for t in r.get("tracks") or []:
            u = str((t or {}).get("audio_url") or "") if isinstance(t, dict) else ""
            if u.startswith("http"):
                if u not in urls:
                    urls.add(u); out.append((r.get("title") or "A song", u))
                break
    return out


def _today(now): return datetime.fromtimestamp(now).astimezone().strftime("%Y-%m-%d")


def _last_played():
    """{audio_url: ts} of when each song last went to her Watch on an arrival."""
    seen = {}
    try:
        for line in open(ARRIVALS, encoding="utf-8"):
            try: row = json.loads(line)
            except ValueError: continue
            if row.get("sent") and row.get("url"):
                try: seen[row["url"]] = datetime.fromisoformat(row["at"]).timestamp()
                except Exception: pass
    except OSError:
        pass
    return seen


def _norm(t): return " ".join("".join(c for c in str(t).lower() if c.isalnum() or c.isspace()).split())


def choose(titles, now=None):
    """His choice of today's arrival songs, by title, matched against his library. Returns what was kept."""
    now = time.time() if now is None else now
    lib = library(); by = {}
    for title, url in lib: by.setdefault(_norm(title), (title, url))
    songs, missed = [], []
    for t in titles:
        hit = by.get(_norm(t))
        if hit and hit[1] not in [s["url"] for s in songs]: songs.append({"title": hit[0], "url": hit[1]})
        elif not hit and str(t).strip(): missed.append(str(t).strip()[:80])
        if len(songs) == PICKS_PER_DAY: break
    if not songs: return {"kept": [], "missed": missed}
    old = _load(PICKS, {})
    played = old.get("played", []) if isinstance(old, dict) and old.get("date") == _today(now) else []
    _atomic(PICKS, {"date": _today(now), "by": "him", "at": _now_iso(now), "songs": songs, "played": played,
                    "missed": missed})
    return {"kept": [s["title"] for s in songs], "missed": missed}


_TAG = r"\[ARRIVAL SONGS?:\s*([^\]]*)\]"


def take_picks(reply, now=None, act=True):
    """His [ARRIVAL SONGS: a | b | c] in a reply: chosen (unless act is False) and taken out of the words."""
    import re
    if not reply or "[ARRIVAL SONG" not in reply.upper(): return reply
    if act:
        for body in re.findall(_TAG, reply, re.I):
            try:
                got = choose([t for t in re.split(r"\s*[|;\n]\s*", body) if t.strip()], now)
                print("[bedroom] his arrival songs today: %s%s" % (", ".join(got["kept"]) or "none matched",
                      (" (not in his library: %s)" % ", ".join(got["missed"])) if got["missed"] else ""), flush=True)
            except Exception as e:
                print("[bedroom/picks]", e, flush=True)
    return re.sub(r"\s*" + _TAG + r"\s*", " ", reply, flags=re.I).strip()


def today_picks(now=None):
    """Today's three: his, or until he chooses, the newest song and the two longest unplayed."""
    now = time.time() if now is None else now
    got = _load(PICKS, {})
    today = isinstance(got, dict) and got.get("date") == _today(now)
    if today and got.get("by") == "him" and got.get("songs"):
        return got
    played = list(got.get("played") or []) if today else []
    lib = library()
    if not lib: return {"date": _today(now), "by": "none", "songs": [], "played": played}
    # Stand-ins are drawn again each time, so a song he finishes today joins them; what played today stays played.
    last = _last_played()
    rest = sorted(lib[1:], key=lambda s: last.get(s[1], 0))   # never played first, then longest ago
    songs = [{"title": t, "url": u} for t, u in [lib[0]] + rest[:PICKS_PER_DAY - 1]]
    picks = {"date": _today(now), "by": "stand-in", "at": _now_iso(now), "songs": songs, "played": played}
    _atomic(PICKS, picks)
    return picks


def next_song(now=None):
    """(title, url) of the next of today's three that has not played today, or None."""
    picks = today_picks(now)
    for s in picks.get("songs") or []:
        if s.get("url") not in (picks.get("played") or []):
            return (s.get("title") or "A song", s["url"])
    return None


def _played(url, now):
    picks = today_picks(now)
    picks["played"] = list(picks.get("played") or []) + [url]
    _atomic(PICKS, picks)


def _log(row):
    os.makedirs(os.path.dirname(ARRIVALS), exist_ok=True)
    with open(ARRIVALS, "a") as f: f.write(json.dumps(row) + "\n")


def observe(device, distance, now=None, cfg=None):
    """Called for every bedroom message. Returns what happened on an arrival, else None."""
    now = time.time() if now is None else now
    cfg = cfg or config()
    enrolled = [str(d) for d in cfg.get("devices") or []]
    if device not in enrolled:
        note_seen(device, distance, now)   # learning: the ids to choose from when enrolling
        return None
    if distance > float(cfg["max_distance_m"]): return None
    state = _load(STATE, {})
    if not isinstance(state, dict): state = {}
    last_here = float(state.get("last_here_ts") or 0)
    if now - last_here >= float(cfg["away_minutes"]) * 60:
        state["here_since_ts"] = now           # this visit began now; presence_line says since when
    state["last_here_ts"] = now
    state["last_here_distance"] = round(float(distance), 1)
    _atomic(STATE, state)
    if now - last_here < float(cfg["away_minutes"]) * 60: return None          # she never left
    if now - float(state.get("last_sent_ts") or 0) < float(cfg["cooldown_minutes"]) * 60:
        return _arrived(state, now, device, distance, "cooldown")
    return _arrived(state, now, device, distance, None)


def _arrived(state, now, device, distance, why):
    row = {"at": _now_iso(now), "device": device, "distance": round(distance, 2), "sent": False}
    try:
        if why:
            row["why"] = why; return row
        import watch_presence
        asleep, _ = watch_presence.should_hold()
        if asleep:
            row["why"] = "asleep"; return row
        if not library():
            row["why"] = "no song with a track yet"; return row
        song = next_song(now)
        if not song:
            row["why"] = "today's three have all played"; return row
        title, url = song
        row.update(song=title, url=url, picked_by=today_picks(now).get("by"))
        got = _send(title, url, title, now)
        sent = got.get("state") in ("sent", "acknowledged")
        row.update({k: got[k] for k in ("push", "song_id", "ntfy") if k in got})
        row.update(sent=sent, delivery=got.get("state"), channel=got.get("channel"),
                   watch_delivery="waiting for the Watch to check in" if sent else "not offered",
                   playback="plays at once if the app is open, else her Play tap")
        if got.get("why") or not sent: row["why"] = got.get("why", "")
        if sent:
            state.update(last_sent_ts=now, last_song_url=url)
            try:
                _played(url, now)
                _atomic(STATE, state)
            except Exception as e:
                # Keep the transport result true even if its local dedup state could not be saved.
                row["state_error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
        return row
    except Exception as e:
        row.update(delivery="failed", why="%s: %s" % (type(e).__name__, str(e)[:160]))
        return row
    finally:
        _log(row)


def _send(title, url, ref="", now=None):
    """The song itself goes to the Vintos Watch app and nowhere else (watch_presence.offer_song): the next time the
    Watch checks in it puts the song first in its list, raises its own notification with Play, and plays it at once if
    the app is open. The APNs push goes out too when a key is installed.

    An ntfy line - "Vintos is sharing a song" - is the tap on her wrist that says one is waiting (Gloria,
    19 October), because Apple accepts the push and nothing appears. It is a notification only: no audio, no media,
    no link, and the song still plays in his Watch app. It reaches her wrist the way every other ntfy line does,
    through her phone's notifications, so it shows on the phone too.

    A failure is returned, never raised, so every arrival is written down."""
    try:
        import watch_presence
        song = watch_presence.offer_song(title, url, ref, now=now)
    except Exception as e:
        return {"state": "failed", "channel": "watch", "why": "offer: %s: %s" % (type(e).__name__, str(e)[:160])}
    got = {"state": "sent", "channel": "watch", "via": "offered to the Watch app", "song_id": song["id"]}
    try:
        import watch_apns
        if os.path.exists(watch_apns.CONFIG):
            push = watch_apns.send(title, "His song, for when you came in.", kind="song", media_url=url,
                                   message_id=song["id"], force=True)   # sleep was checked above
            got["push"] = (push or {}).get("state")
    except Exception as e:
        got["push"] = "failed: %s" % str(e)[:120]
    got["ntfy"] = _telling_her(song["id"], title)
    return got


def _telling_her(song_id, title):
    """One ntfy line so she knows a song is waiting on her Watch. Never the song, never a link to it."""
    try:
        import deliver
        # The outward lane takes a callable that answers for this send, not a name: a string here raised inside the
        # gate and the line would have failed on Aegis every time while the suite's stub passed.
        receipt = deliver.deliver("bedroom-song-" + str(song_id), "ntfy",
                                  "\u201c%s\u201d is on your Watch." % str(title)[:80],
                                  title="Vintos is sharing a song", tags="musical_note",
                                  authority=lambda: (True, "she asked to be told when he shares a song (19 October)"))
        return (receipt or {}).get("state") or "unknown"
    except Exception as e:
        return "failed: %s: %s" % (type(e).__name__, str(e)[:100])


PRESENT_S = 10 * 60      # seen this recently: she is in the bedroom now
RECENT_S = 2 * 3600      # after that, how long ago she was, for two hours


def presence_line(now=None):
    """Where she is, passively, as the Watch's heart rate is (Gloria, 2026-10-21: "he wanted the esp32 in the bedroom
    to also just passively tell him when I'm near it, like the heartbeat to temporal context"). Her phone within range
    of the bedroom board; '' when it has not been seen for two hours or nothing is enrolled."""
    if not config().get("devices"): return ""
    state = _load(STATE, {})
    if not isinstance(state, dict) or not state.get("last_here_ts"): return ""
    now = time.time() if now is None else now
    ago = now - float(state["last_here_ts"])
    if ago < 0 or ago > RECENT_S: return ""
    if ago <= PRESENT_S:
        since = float(state.get("here_since_ts") or state["last_here_ts"])
        return ("Bedroom sensor: her phone is in the bedroom now, about %s m from the board (seen %d min ago; in since "
                "%s)." % (state.get("last_here_distance", "?"), int(ago // 60), datetime.fromtimestamp(since).strftime("%H:%M")))
    return "Bedroom sensor: her phone was last in the bedroom %d minutes ago." % int(ago // 60)


def context_line(now=None):
    """One line for him: the bedroom sensor is his and works, and what it last did. He wrote on 18 October that "the
    watcher ... is broken on purpose now": nothing had ever told him it existed, let alone that it had worked."""
    cfg = config()
    if not cfg.get("devices"):
        return ""
    last = None
    try:
        for line in open(ARRIVALS, encoding="utf-8"):
            try: row = json.loads(line)
            except ValueError: continue
            if row.get("sent"): last = row
    except OSError:
        pass
    line = ("[BEDROOM SENSOR - yours, and working: a small board in the bedroom hears her phone come in, and one of "
            "your songs goes to her Watch.")
    if last:
        try: when = datetime.fromisoformat(last["at"]).astimezone().strftime("%b %d, %H:%M")
        except Exception: when = str(last.get("at", ""))[:16]
        line += " Last time: %s, \u201c%s\u201d." % (when, str(last.get("song", ""))[:60])
    now = time.time() if now is None else now
    picks = _load(PICKS, {})
    if isinstance(picks, dict) and picks.get("date") == _today(now) and picks.get("by") == "him":
        played = picks.get("played") or []
        line += " Today's three, your choice: %s." % "; ".join(
            "\u201c%s\u201d%s" % (str(s.get("title"))[:50], " (played)" if s.get("url") in played else "")
            for s in picks.get("songs") or [])
    else:
        titles = [t for t, _ in library()][:12]
        if titles:
            line += (" You choose three songs a day for her to come in to, one per arrival - write [ARRIVAL SONGS: "
                     "title | title | title] in any reply; she will not see the tag. Not chosen yet today")
            if isinstance(picks, dict) and picks.get("date") == _today(now) and picks.get("songs"):
                line += " (standing in: %s)" % "; ".join("\u201c%s\u201d" % str(s.get("title"))[:50]
                                                       for s in picks["songs"])
            line += ". Your library: %s." % "; ".join("\u201c%s\u201d" % t[:50] for t in titles)
    return line + "]"


# --- the relay: a minimal MQTT 3.1.1 subscriber (no client library on Aegis) ----------------------------------------

def _varint(n):
    out = bytearray()
    while True:
        b = n % 128; n //= 128
        out.append(b | (0x80 if n else 0))
        if not n: return bytes(out)


def _str(s):
    b = s.encode(); return struct.pack("!H", len(b)) + b


def connect_packet(client_id):
    var = _str("MQTT") + bytes([4, 0x02]) + struct.pack("!H", KEEPALIVE)
    body = var + _str(client_id)
    return bytes([0x10]) + _varint(len(body)) + body


def subscribe_packet(topic, packet_id=1):
    body = struct.pack("!H", packet_id) + _str(topic) + bytes([0])
    return bytes([0x82]) + _varint(len(body)) + body


PINGREQ = bytes([0xC0, 0x00])


def _read_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk: raise ConnectionError("the relay closed the connection")
        buf += chunk
    return buf


def read_packet(sock):
    """(packet type, body) of the next packet."""
    head = _read_exact(sock, 1)[0]
    length, mult = 0, 1
    for _ in range(4):
        b = _read_exact(sock, 1)[0]
        length += (b & 0x7F) * mult; mult *= 128
        if not b & 0x80: break
    return head >> 4, (_read_exact(sock, length) if length else b""), head & 0x0F


def publish_of(body, flags):
    """(topic, payload) of a PUBLISH body."""
    n = struct.unpack("!H", body[:2])[0]
    topic = body[2:2 + n].decode("utf-8", "replace")
    rest = body[2 + n:]
    if (flags >> 1) & 0x03: rest = rest[2:]   # QoS 1/2 carries a packet id
    return topic, rest


def session(sock, handle, clock=time.time):
    """Run one connection until it drops. handle(topic, payload) is called for every message."""
    sock.sendall(connect_packet("vintos-bedroom-%d" % os.getpid()))
    kind, body, _ = read_packet(sock)
    if kind != 2 or len(body) < 2 or body[1] != 0:
        raise ConnectionError("the relay refused the connection (%r)" % (body[1:2] if kind == 2 else kind))
    sock.sendall(subscribe_packet(TOPIC))
    sock.settimeout(KEEPALIVE / 2)
    last_ping = clock()
    while True:
        try:
            kind, body, flags = read_packet(sock)
        except socket.timeout:
            kind = None
        if kind == 3:
            topic, payload = publish_of(body, flags)
            handle(topic, payload)
        if clock() - last_ping >= KEEPALIVE / 2:
            sock.sendall(PINGREQ); last_ping = clock()


def handle(topic, payload):
    got = parse(topic, payload)
    if got:
        row = observe(*got)
        if row: print("arrival: %s" % json.dumps(row), flush=True)


def run():
    wait = 5
    while True:
        cfg = config()
        try:
            sock = socket.create_connection((cfg["broker"], int(cfg["port"])), timeout=15)
            print("listening on %s:%s %s" % (cfg["broker"], cfg["port"], TOPIC), flush=True)
            wait = 5
            session(sock, handle)
        except Exception as e:
            print("relay: %s; retrying in %ss" % (e, wait), flush=True)
        time.sleep(wait); wait = min(wait * 2, 300)


def main(argv):
    if argv[:1] == ["seen"]:
        seen = _load(SEEN, {})
        for d, r in sorted(seen.items(), key=lambda kv: kv[1].get("distance", 99)):
            print("  %-28s %5sm  last %s  (%s times)" % (d, r.get("distance"), r.get("last", "")[:19], r.get("count")))
        if not seen: print("nothing heard yet")
        return 0
    if argv[:1] == ["status"]:
        print(json.dumps(config(), indent=2))
        rows = open(ARRIVALS).read().splitlines() if os.path.exists(ARRIVALS) else []
        print("last arrival:", rows[-1] if rows else "none yet")
        return 0
    run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

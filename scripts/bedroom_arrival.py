#!/usr/bin/env python3
"""bedroom_arrival.py — his newest song on her Watch when Gloria comes into the bedroom.

The ESP32 in the bedroom (ESPresense) publishes what it hears to the Mosquitto relay on the Mac:
    espresense/devices/<device id>/bedroom   {"distance": 1.03, ...}
This listens there. An arrival hands the newest song to the Vintos Watch app: when the Watch next checks in it
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
    state["last_here_ts"] = now
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
        song = newest_song()
        if not song:
            row["why"] = "no song with a track yet"; return row
        title, url = song
        row["song"] = title
        if url == state.get("last_song_url"):
            row["why"] = "his newest song notification was already sent"; return row
        got = _send(title, url, title, now)
        sent = got.get("state") in ("sent", "acknowledged")
        row.update({k: got[k] for k in ("push", "song_id") if k in got})
        row.update(sent=sent, delivery=got.get("state"), channel=got.get("channel"),
                   watch_delivery="waiting for the Watch to check in" if sent else "not offered",
                   playback="plays at once if the app is open, else her Play tap")
        if got.get("why") or not sent: row["why"] = got.get("why", "")
        if sent:
            state.update(last_sent_ts=now, last_song_url=url)
            try:
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
    """To the Vintos Watch app, never her phone. The song is offered to the app (watch_presence.offer_song): the next
    time the Watch checks in it raises its own notification with Play, puts the song first in its list, and plays it
    at once if the app is open. If an APNs key is ever installed, the push goes out too, for an immediate notification.
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
            push = watch_apns.send(title, "His newest song, for when you came in.", kind="song", media_url=url,
                                   message_id=song["id"], force=True)   # sleep was checked above
            got["push"] = (push or {}).get("state")
    except Exception as e:
        got["push"] = "failed: %s" % str(e)[:120]
    return got


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

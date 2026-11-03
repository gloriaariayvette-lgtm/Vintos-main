#!/usr/bin/env python3
"""kitchen_presence.py — when Gloria is in the kitchen, from the ESP32 by the coffee maker (3 November).

Gloria, 3 November: "let the coffee maker esp32 know when I pass within 1m. Means I'm in the kitchen."
The kitchen ESP32 is the Bluetooth proxy for the Nespresso's Fingerbot (home/esphome/kitchen-ble-proxy.yaml). It also
hears her phone (by its IRK, as the bedroom board does) and publishes, ESPresense-style, to the Mosquitto relay on the Mac:
    espresense/devices/gloria-phone/kitchen   {"distance": 0.8, "rssi": -61, ...}
This listens there. Her phone within max_distance_m (1.0) is her in the kitchen. It only knows and keeps: a line for
him while she is there, and each visit, first heard to last heard, in memory/kitchen-visits.jsonl. It sends nothing,
plays nothing, makes no coffee, moves no device.

    python3 kitchen_presence.py            # run (the vintos-kitchen-presence unit does this)
    python3 kitchen_presence.py status     # config, the visit now and the last one
    python3 kitchen_presence.py seen       # what the board has heard lately, nearest first (for calibrating 1 m)

Config: memory/kitchen-presence.json
    {"broker": "192.168.1.91", "port": 1883, "devices": ["gloria-phone"], "max_distance_m": 1.0, "away_minutes": 5}
"""
import json, os, socket, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bedroom_arrival as _mqtt   # the minimal MQTT 3.1.1 packets; nothing of the bedroom's behaviour is used

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
CONFIG = os.path.join(MEM, "kitchen-presence.json")
STATE = os.path.join(MEM, "kitchen-presence-state.json")
SEEN = os.path.join(MEM, "kitchen-seen.json")
VISITS = os.path.join(MEM, "kitchen-visits.jsonl")
TOPIC = "espresense/devices/+/kitchen"
DEFAULTS = {"broker": "192.168.1.91", "port": 1883, "devices": ["gloria-phone"], "max_distance_m": 1.0,
            "away_minutes": 5}
PRESENT_S = 120       # heard within 1 m this recently: she is in the kitchen now
RECENT_S = 1800       # after that, "last in the kitchen N minutes ago" for half an hour, then nothing
SEEN_KEEP = 40
KEEPALIVE = 60


def config():
    cfg = dict(DEFAULTS); got = _mqtt._load(CONFIG, {})
    if isinstance(got, dict): cfg.update(got)
    return cfg


def _iso(ts): return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def parse(topic, payload):
    """(device id, distance in metres) from one kitchen message, or None."""
    parts = topic.split("/")
    if len(parts) != 4 or parts[0] != "espresense" or parts[1] != "devices" or parts[3] != "kitchen": return None
    try:
        data = json.loads(payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload)
        d = float(data.get("distance"))
    except Exception: return None
    return (parts[2], d) if parts[2] and d == d and d >= 0 else None


def _note_seen(device, distance, now):
    seen = _mqtt._load(SEEN, {})
    if not isinstance(seen, dict): seen = {}
    row = seen.get(device) or {"count": 0}
    row.update(last=_iso(now), last_ts=now, distance=round(distance, 2), count=int(row.get("count", 0)) + 1)
    seen[device] = row
    if len(seen) > SEEN_KEEP:
        seen = dict(sorted(seen.items(), key=lambda kv: -float(kv[1].get("last_ts") or 0))[:SEEN_KEEP])
    _mqtt._atomic(SEEN, seen)


def _close_visit(state, cfg):
    """The visit that ended when she was last heard, written once, as a new one begins."""
    since, last = state.get("here_since_ts"), state.get("last_here_ts")
    if not since or not last or float(last) < float(since): return
    row = {"from": _iso(float(since)), "to": _iso(float(last)), "from_ts": float(since), "to_ts": float(last),
           "minutes": round((float(last) - float(since)) / 60, 1), "device": state.get("device", ""),
           "ended": "last heard; away %s+ minutes after" % int(float(cfg["away_minutes"])),
           "estimate": "Bluetooth signal strength at the coffee maker, not a camera: within %s m of it"
                       % cfg["max_distance_m"]}
    try:
        with open(VISITS, "a") as f: f.write(json.dumps(row) + "\n")
    except OSError:
        pass


def observe(device, distance, now=None, cfg=None):
    """Called for every kitchen message. True when it began a visit."""
    now = time.time() if now is None else now
    cfg = cfg or config()
    _note_seen(device, distance, now)
    if device not in [str(d) for d in cfg.get("devices") or []]: return False
    if distance > float(cfg["max_distance_m"]): return False
    state = _mqtt._load(STATE, {})
    if not isinstance(state, dict): state = {}
    last = float(state.get("last_here_ts") or 0)
    began = not last or now - last >= float(cfg["away_minutes"]) * 60
    if began:
        _close_visit(state, cfg)
        state["here_since_ts"] = now
    state.update(device=device, last_here_ts=now, last_here_distance=round(distance, 2))
    _mqtt._atomic(STATE, state)
    return began


def context_line(now=None):
    """One line for him while she is, or just was, in the kitchen; '' otherwise."""
    state = _mqtt._load(STATE, {})
    if not isinstance(state, dict) or not state.get("last_here_ts"): return ""
    now = time.time() if now is None else now
    ago = now - float(state["last_here_ts"])
    if ago < 0 or ago > RECENT_S: return ""
    if ago <= PRESENT_S:
        since = datetime.fromtimestamp(float(state.get("here_since_ts") or state["last_here_ts"])).strftime("%H:%M")
        return ("[KITCHEN - the board by the coffee maker hears her phone within %s m: she is in the kitchen now "
                "(since %s).]" % (config()["max_distance_m"], since))
    return "[KITCHEN - she was last by the coffee maker %d minutes ago.]" % max(1, int(ago // 60))


def handle(topic, payload):
    got = parse(topic, payload)
    if got and observe(*got):
        print("in the kitchen: %s at %.2f m" % got, flush=True)


def session(sock, clock=time.time):
    """Run one connection until it drops."""
    sock.sendall(_mqtt.connect_packet("vintos-kitchen-%d" % os.getpid()))
    kind, body, _ = _mqtt.read_packet(sock)
    if kind != 2 or len(body) < 2 or body[1] != 0:
        raise ConnectionError("the relay refused the connection (%r)" % (body[1:2] if kind == 2 else kind))
    sock.sendall(_mqtt.subscribe_packet(TOPIC))
    sock.settimeout(KEEPALIVE / 2)
    last_ping = clock()
    while True:
        try:
            kind, body, flags = _mqtt.read_packet(sock)
        except socket.timeout:
            kind = None
        if kind == 3:
            handle(*_mqtt.publish_of(body, flags))
        if clock() - last_ping >= KEEPALIVE / 2:
            sock.sendall(_mqtt.PINGREQ); last_ping = clock()


def run():
    wait = 5
    while True:
        cfg = config()
        try:
            sock = socket.create_connection((cfg["broker"], int(cfg["port"])), timeout=15)
            print("listening on %s:%s %s" % (cfg["broker"], cfg["port"], TOPIC), flush=True)
            wait = 5
            session(sock)
        except Exception as e:
            print("relay: %s; retrying in %ss" % (e, wait), flush=True)
        time.sleep(wait); wait = min(wait * 2, 300)


def main(argv):
    if argv[:1] == ["seen"]:
        seen = _mqtt._load(SEEN, {})
        for d, r in sorted(seen.items(), key=lambda kv: kv[1].get("distance", 99)):
            print("  %-20s %5sm  last %s  (%s times)" % (d, r.get("distance"), r.get("last", "")[:19], r.get("count")))
        if not seen: print("nothing heard yet")
        return 0
    if argv[:1] == ["status"]:
        print(json.dumps(config(), indent=2))
        print("now:", context_line() or "not in the kitchen lately")
        rows = open(VISITS).read().splitlines() if os.path.exists(VISITS) else []
        print("last visit:", rows[-1] if rows else "none yet")
        return 0
    run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

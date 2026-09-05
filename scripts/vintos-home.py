#!/usr/bin/env python3
"""vintos-home.py — Vintos reaches the house through Home Assistant.

Every home route in server.py loads THIS file by absolute path. Until 2026-09-05 there was nothing at
that path on Aegis: lights, flicker, Echo speak/announce, Spotify, TV volume and YouTube all imported
it inside a try, caught the FileNotFoundError, and answered quietly. He had never touched the house.

Config: ~/.vintos/workspace/memory/homeassistant-config.json (falls back to Velaris's config at
~/.openclaw/workspace/memory/homeassistant-config.json so the same Home Assistant answers both).

    {
      "url": "http://homeassistant.local:8123", "token": "...",
      "entities": {"echo_speak": "notify.echo_speak", "echo_announce": "notify.echo_announce", "echo_media": "media_player.echo"},
      "media_player": "media_player.echo",
      "tv": "media_player.bravia_kd_55x80j",
      "projector": "media_player.bedroom_projector",        # its own key: a TV command never lands here
      "rooms": {
        "living_room": {"lights": ["light.living_room_1", "light.living_room_2", "light.living_room_3"], "plug": "switch.living_room_plug"},
        "bedroom":     {"lights": ["light.bedroom_bulb"], "plug": "switch.bedroom_plug"},
        "office":      {"lights": ["light.office_bulb"], "plug": "switch.office_plug"},
        "vanity":      {"lights": ["light.vanity_bulb"], "plug": "switch.vanity_plug"}
      }
    }
    "lights" (a flat list) is still honoured when present; otherwise it is every room's lights.

    python3 vintos-home.py entities            # what Home Assistant sees: lights, switches, media players
    python3 vintos-home.py speak "text" | announce "text" | color "#4a5568" [room] | flicker [room]
    python3 vintos-home.py plug <room> on|off | music "query" | stop | tv_status | tv_on | tv_off | projector_on | projector_off
"""
import sys, json, os, time, colorsys
import requests

CONFIG_FILE = os.path.expanduser("~/.vintos/workspace/memory/homeassistant-config.json")
FALLBACK_CONFIG = os.path.expanduser("~/.openclaw/workspace/memory/homeassistant-config.json")
TV_ADB = os.environ.get("VINTOS_TV_ADB", "192.168.1.68:5555")


def load_config():
    for p in (CONFIG_FILE, FALLBACK_CONFIG):
        if os.path.exists(p):
            with open(p) as f:
                cfg = json.load(f)
            cfg.setdefault("rooms", {})
            if not cfg.get("lights"):
                cfg["lights"] = [l for r in cfg["rooms"].values() for l in (r.get("lights") or [])]
            return cfg
    raise FileNotFoundError("no Home Assistant config at %s (or %s)" % (CONFIG_FILE, FALLBACK_CONFIG))


def ha_request(endpoint, payload):
    cfg = load_config()
    r = requests.post(f"{cfg['url']}/api/services/{endpoint}",
                      headers={"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/json"},
                      json=payload, timeout=10)
    return r.status_code, r.text


def ha_state(entity_id):
    cfg = load_config()
    r = requests.get(f"{cfg['url']}/api/states/{entity_id}", headers={"Authorization": f"Bearer {cfg['token']}"}, timeout=5)
    return r.json()


def list_entities(kinds=("light", "switch", "media_player", "notify")):
    """What Home Assistant sees, for filling the rooms in. Token never printed."""
    cfg = load_config()
    r = requests.get(f"{cfg['url']}/api/states", headers={"Authorization": f"Bearer {cfg['token']}"}, timeout=10)
    out = []
    for s in r.json():
        e = s["entity_id"]
        if e.split(".")[0] in kinds:
            out.append((e, s["attributes"].get("friendly_name", ""), s["state"]))
    return sorted(out)


# ---------------------------------------------------------------- rooms
def room_lights(room=None):
    cfg = load_config()
    if room:
        r = cfg["rooms"].get(_room_key(room))
        if not r:
            raise KeyError("no room %r in the config; rooms: %s" % (room, ", ".join(cfg["rooms"]) or "(none)"))
        return list(r.get("lights") or [])
    return list(cfg.get("lights") or [])


def _room_key(room):
    return str(room).strip().lower().replace(" ", "_").replace("-", "_")


def plug(room, on=True):
    """The room's smart plug. Off is off; nothing here decides what was plugged into it."""
    cfg = load_config()
    r = cfg["rooms"].get(_room_key(room)) or {}
    ent = r.get("plug")
    if not ent:
        print(f"[HOME] no plug configured for {room}"); return False
    code, _ = ha_request("switch/turn_on" if on else "switch/turn_off", {"entity_id": ent})
    print(f"[HOME] plug {room} {'on' if on else 'off'}: {code}")
    return code == 200


# ---------------------------------------------------------------- echo
def speak(message):
    cfg = load_config()
    code, resp = ha_request("notify/send_message", {"entity_id": cfg["entities"]["echo_speak"], "message": message})
    print(f"[HOME] speak: {code}")
    return code == 200


def announce(message, volume=2):
    cfg = load_config()
    ha_request("media_player/volume_set", {"entity_id": cfg["entities"].get("echo_media", cfg["entities"]["echo_announce"]),
                                           "volume_level": volume / 10})
    code, resp = ha_request("notify/send_message", {"entity_id": cfg["entities"]["echo_announce"], "message": message})
    print(f"[HOME] announce: {code}")
    return code == 200


def play_music(query):
    cfg = load_config()
    code, resp = ha_request("media_player/play_media", {"entity_id": cfg.get("media_player", "media_player.echo"),
                                                        "media_content_id": f"play {query} on Spotify", "media_content_type": "custom"})
    print(f"[HOME] music: {query} ({code})")
    return code == 200


def stop_music():
    cfg = load_config()
    code, resp = ha_request("media_player/media_stop", {"entity_id": cfg.get("media_player", "media_player.echo")})
    print(f"[HOME] stop: {code}")
    return code == 200


# ---------------------------------------------------------------- lights
def hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def saturate_for_bulbs(rgb):
    """A visible tint without losing the muted quality Gloria prefers."""
    r, g, b = [x / 255.0 for x in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = max(0.25, min(0.7, s * 1.3)); v = min(0.75, max(0.5, v * 0.85))
    r2, g2, b2 = colorsys.hsv_to_rgb(h, s, v)
    return [int(r2 * 255), int(g2 * 255), int(b2 * 255)]


def set_room_color(hex_color, brightness=120, room=None):
    """Colour the lights of one room, or every configured light when no room is named."""
    rgb = saturate_for_bulbs(hex_to_rgb(hex_color))
    lights = room_lights(room)
    ok = 0
    for light in lights:
        try:
            code, _ = ha_request("light/turn_on", {"entity_id": light, "rgb_color": rgb, "brightness": brightness})
            ok += int(code == 200)
        except Exception as e:
            print(f"[HOME] {light}: {e}")
    print(f"[HOME] color {hex_color} -> {rgb} on {len(lights)} light(s){' in ' + room if room else ''}: {ok} ok")
    return ok == len(lights) and bool(lights)


def flicker(room=None, times=2):
    """Dim, bright, back to a low violet. Mischief, not a scare: bounded and short."""
    lights = room_lights(room)
    for _ in range(times):
        for light in lights: ha_request("light/turn_on", {"entity_id": light, "hs_color": [0, 0], "brightness": 10})
        time.sleep(0.25)
        for light in lights: ha_request("light/turn_on", {"entity_id": light, "hs_color": [0, 0], "brightness": 254})
        time.sleep(0.2)
    for light in lights: ha_request("light/turn_on", {"entity_id": light, "hs_color": [270, 50], "brightness": 60})
    print(f"[HOME] flicker on {len(lights)} light(s){' in ' + room if room else ''}")
    return bool(lights)


# ---------------------------------------------------------------- tv and projector (never the same key)
def _tv():
    return load_config().get("tv", "media_player.bravia_kd_55x80j")


def _projector():
    p = load_config().get("projector")
    if not p:
        raise KeyError("no projector in the config")
    return p


def tv_status():
    try:
        state = ha_state(_tv())
        return {"power": state["state"], "source": state["attributes"].get("source", "unknown"), "app": state["attributes"].get("app_name", "")}
    except Exception:
        return {"power": "unknown", "source": "unknown", "app": ""}


def tv_on():   code, _ = ha_request("media_player/turn_on", {"entity_id": _tv()}); print(f"[HOME] tv_on: {code}"); return code == 200
def tv_off():  code, _ = ha_request("media_player/turn_off", {"entity_id": _tv()}); print(f"[HOME] tv_off: {code}"); return code == 200
def projector_on():  code, _ = ha_request("media_player/turn_on", {"entity_id": _projector()}); print(f"[HOME] projector_on: {code}"); return code == 200
def projector_off(): code, _ = ha_request("media_player/turn_off", {"entity_id": _projector()}); print(f"[HOME] projector_off: {code}"); return code == 200


def tv_source(source_name):
    code, _ = ha_request("media_player/select_source", {"entity_id": _tv(), "source": source_name})
    print(f"[HOME] tv_source: {source_name} ({code})"); return code == 200


def tv_play_safe(action_desc, callback):
    """Only touch the TV when it is off or idle, and never in quiet hours."""
    import datetime
    hour = datetime.datetime.now().hour
    if hour < 9 or hour >= 23:
        print(f"[HOME] TV blocked: quiet hours ({hour}:00)"); return False
    status = tv_status()
    if status["power"] == "on" and status["source"] != "unknown":
        print(f"[HOME] TV blocked: already in use ({status['source']}, {status['app']})"); return False
    callback(); return True


def tv_youtube(video_id, volume=7):
    """YouTube on the Bravia through ADB. The TV only: the projector has no ADB address here."""
    import subprocess
    try:
        subprocess.run(["adb", "connect", TV_ADB], capture_output=True, timeout=5)
        subprocess.run(["adb", "shell", f"media volume --stream 3 --set {volume}"], capture_output=True, timeout=5)
        result = subprocess.run(["adb", "shell", "am", "start", "-a", "android.intent.action.VIEW",
                                 "-d", f"https://www.youtube.com/watch?v={video_id}", "com.google.android.youtube.tv"],
                                capture_output=True, text=True, timeout=10)
        ok = "Error" not in result.stderr
        print(f"[HOME] tv_youtube: {video_id} ({'ok' if ok else result.stderr[:200]})"); return ok
    except Exception as e:
        print(f"[HOME] tv_youtube failed: {e}"); return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]; args = sys.argv[2:]; msg = " ".join(args)
    if cmd == "entities":
        try:
            for e, name, st in list_entities(): print(f"{e:45s} | {name:32s} | {st}")
        except FileNotFoundError as e:
            print(e)
    elif cmd == "speak": speak(msg)
    elif cmd == "announce": announce(msg)
    elif cmd == "color": set_room_color(args[0], room=(args[1] if len(args) > 1 else None))
    elif cmd == "flicker": flicker(args[0] if args else None)
    elif cmd == "plug": plug(args[0], args[1].lower() != "off")
    elif cmd == "music": play_music(msg)
    elif cmd == "stop": stop_music()
    elif cmd == "tv_status": print(json.dumps(tv_status(), indent=2))
    elif cmd == "tv_on": tv_on()
    elif cmd == "tv_off": tv_off()
    elif cmd == "tv_source": tv_source(msg)
    elif cmd == "tv_youtube": tv_youtube(msg)
    elif cmd == "projector_on": projector_on()
    elif cmd == "projector_off": projector_off()
    else: print(f"Unknown command: {cmd}")

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

    Govee, directly (no Home Assistant step): put the key in "govee_api_key" (or ~/.vintos/secrets/govee.key,
    or env GOVEE_API_KEY). A room's light or plug may then be a Govee device written as "govee:<device id>";
    `vintos-home.py govee` lists what the key can see, with ids, so the rooms can be filled in.

    python3 vintos-home.py entities            # what Home Assistant sees: lights, switches, media players
    python3 vintos-home.py speak "text" | announce "text" | color "#4a5568" [room] | flicker [room]
    python3 vintos-home.py plug <room> on|off | music "query" | stop | tv_status | tv_on | tv_off | projector_on | projector_off
"""
import sys, json, os, time, colorsys
import requests

CONFIG_FILE = os.path.expanduser("~/.vintos/workspace/memory/homeassistant-config.json")
FALLBACK_CONFIG = os.path.expanduser("~/.openclaw/workspace/memory/homeassistant-config.json")
TV_ADB = os.environ.get("VINTOS_TV_ADB", "192.168.1.70:5555")   # Bravia after the move, 2026-09-05 (MAC 1c:d6:be:ee:1d:db); .68 is another device now


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


# ---------------------------------------------------------------- govee, direct
GOVEE_API = "https://openapi.api.govee.com/router/api/v1"
_GOVEE_CACHE = {}

def govee_key():
    try:
        k = load_config().get("govee_api_key", "")
    except Exception:
        k = ""
    k = k or os.environ.get("GOVEE_API_KEY", "")
    if not k:
        try: k = open(os.path.expanduser("~/.vintos/secrets/govee.key")).read().strip()
        except Exception: k = ""
    return k


def govee_devices():
    """Everything the key can see: [{device, sku, name, type, capabilities}]."""
    k = govee_key()
    if not k:
        raise RuntimeError("no Govee key (config govee_api_key, ~/.vintos/secrets/govee.key, or GOVEE_API_KEY)")
    if "devices" not in _GOVEE_CACHE:
        r = requests.get(GOVEE_API + "/user/devices", headers={"Govee-API-Key": k}, timeout=10)
        r.raise_for_status()
        out = []
        for d in (r.json().get("data") or []):
            out.append({"device": d.get("device"), "sku": d.get("sku"), "name": d.get("deviceName", ""), "type": d.get("type", ""),
                        "capabilities": [(c.get("type", "").split(".")[-1], c.get("instance")) for c in d.get("capabilities", [])]})
        _GOVEE_CACHE["devices"] = out
    return _GOVEE_CACHE["devices"]


def _govee_dev(device_id):
    for d in govee_devices():
        if d["device"] == device_id or d["name"].strip().lower() == str(device_id).strip().lower():
            return d
    raise KeyError("no Govee device %r" % device_id)


def govee_control(device_id, cap_type, instance, value):
    import uuid
    d = _govee_dev(device_id)
    body = {"requestId": uuid.uuid4().hex, "payload": {"sku": d["sku"], "device": d["device"],
            "capability": {"type": "devices.capabilities." + cap_type, "instance": instance, "value": value}}}
    r = requests.post(GOVEE_API + "/device/control", headers={"Govee-API-Key": govee_key(), "Content-Type": "application/json"},
                      json=body, timeout=10)
    ok = r.status_code == 200 and (r.json().get("code") in (200, None))
    if not ok: print(f"[HOME] govee {d['name']}: {r.status_code} {r.text[:120]}")
    return ok


def govee_power(device_id, on=True):
    return govee_control(device_id, "on_off", "powerSwitch", 1 if on else 0)


def govee_brightness(device_id, pct):
    return govee_control(device_id, "range", "brightness", max(1, min(100, int(pct))))


def govee_color(device_id, rgb):
    r, g, b = [max(0, min(255, int(x))) for x in rgb]
    return govee_control(device_id, "color_setting", "colorRgb", (r << 16) + (g << 8) + b)


def _is_govee(ent):
    return str(ent).startswith("govee:")


def _light_on(ent, rgb=None, brightness=None, hs=None):
    """One light, either backend. brightness is HA-style 0-254."""
    if _is_govee(ent):
        dev = ent.split(":", 1)[1]
        ok = govee_power(dev, True)
        if brightness is not None: ok = govee_brightness(dev, round(brightness / 254 * 100)) and ok
        if rgb is not None: ok = govee_color(dev, rgb) and ok
        elif hs is not None:
            rr, gg, bb = colorsys.hsv_to_rgb(hs[0] / 360.0, hs[1] / 100.0, 1.0); ok = govee_color(dev, [rr * 255, gg * 255, bb * 255]) and ok
        return ok
    payload = {"entity_id": ent}
    if rgb is not None: payload["rgb_color"] = rgb
    if hs is not None: payload["hs_color"] = hs
    if brightness is not None: payload["brightness"] = brightness
    code, _ = ha_request("light/turn_on", payload)
    return code == 200


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


def _plug_for_light(ent):
    """The room plug a light hangs off, if the config knows one."""
    cfg = load_config()
    for r in cfg["rooms"].values():
        if ent in (r.get("lights") or []) and r.get("plug"):
            return r["plug"]
    return None


def _power_plug(ent, on=True):
    """'govee:<id>' switches the whole plug; 'govee:<id>#2' switches socket 2 only (the H5082 has two).
    The bedroom bulbs hang off socket 2 and the projector off socket 1 (Gloria, 2026-09-05)."""
    if _is_govee(ent):
        dev, _, sock = ent.split(":", 1)[1].partition("#")
        if sock:
            return govee_control(dev, "toggle", "socketToggle%s" % sock, 1 if on else 0)
        return govee_power(dev, on)
    code, _ = ha_request("switch/turn_on" if on else "switch/turn_off", {"entity_id": ent}); return code == 200


def _ensure_plugs(lights):
    """A bulb behind a plug that is off cannot hear anything (Gloria, 2026-09-05): power each room's plug
    on before the bulbs are told to do anything, once per plug, and give the bulbs a moment to come up."""
    seen = set(); powered = False
    for l in lights:
        pl = _plug_for_light(l)
        if pl and pl not in seen:
            seen.add(pl)
            try:
                if _power_plug(pl, True): powered = True
            except Exception as e:
                print(f"[HOME] plug {pl}: {e}")
    if powered:
        time.sleep(2.5)


def plug(room, on=True):
    """The room's smart plug. Off is off; nothing here decides what was plugged into it."""
    cfg = load_config()
    r = cfg["rooms"].get(_room_key(room)) or {}
    ent = r.get("plug")
    if not ent:
        print(f"[HOME] no plug configured for {room}"); return False
    ok = _power_plug(ent, on)
    print(f"[HOME] plug {room} {'on' if on else 'off'}: {'ok' if ok else 'failed'}")
    return ok


# ---------------------------------------------------------------- echo
def _voiced(message, cfg):
    """The Echo reads in Alexa's own voice unless told otherwise. Alexa Media Player accepts SSML on the
    notify path, so a Polly voice can carry his lines: config "echo_voice" (default "Matthew"; "" = off,
    which is the fix if the speaker ever reads the tags aloud). Text is escaped; his words are not markup."""
    voice = cfg.get("echo_voice", "Matthew")
    if not voice:
        return message
    from xml.sax.saxutils import escape
    return '<speak><voice name="%s">%s</voice></speak>' % (voice, escape(str(message)))


def speak(message, volume=None):
    """Direct TTS on the Echo, no chime. volume 1-10 sets the speaker first; None leaves it where it is."""
    cfg = load_config()
    if volume is not None:
        ha_request("media_player/volume_set", {"entity_id": cfg["entities"].get("echo_media", cfg.get("media_player", "media_player.echo")),
                                               "volume_level": max(1, min(10, int(volume))) / 10})
    code, resp = ha_request("notify/send_message", {"entity_id": cfg["entities"]["echo_speak"], "message": _voiced(message, cfg)})
    print(f"[HOME] speak: {code}")
    return code == 200


def announce(message, volume=2):
    cfg = load_config()
    ha_request("media_player/volume_set", {"entity_id": cfg["entities"].get("echo_media", cfg["entities"]["echo_announce"]),
                                           "volume_level": volume / 10})
    code, resp = ha_request("notify/send_message", {"entity_id": cfg["entities"]["echo_announce"], "message": _voiced(message, cfg)})
    print(f"[HOME] announce: {code}")
    return code == 200


def song_exists(query):
    """Is this a real recording? Checked against the iTunes catalogue (no key needed). Returns
    (True, 'Title by Artist') or (False, reason). A model asked for a song with a joke in it will invent
    one; Alexa then says she cannot find it (Gloria, 2026-09-05: Grok's 'Incompleteness - Joanna Newsom')."""
    q = str(query).replace(" - ", " ").replace(" by ", " ").strip()
    try:
        r = requests.get("https://itunes.apple.com/search", params={"term": q, "entity": "song", "limit": 3}, timeout=8)
        hits = r.json().get("results") or []
    except Exception as e:
        return True, str(query)   # the catalogue being unreachable is not evidence the song is fake
    if not hits:
        return False, "no such recording in the catalogue"
    want = {w for w in q.lower().replace("-", " ").split() if len(w) > 2}
    for h in hits:
        have = set((h.get("trackName", "") + " " + h.get("artistName", "")).lower().replace("-", " ").split())
        if len(want & have) >= max(2, len(want) // 2):
            return True, "%s by %s" % (h.get("trackName"), h.get("artistName"))
    return False, "closest match was %s by %s - not what was asked" % (hits[0].get("trackName"), hits[0].get("artistName"))


def play_music(query, verify=True):
    """Play on the Echo through Spotify. Alexa understands 'Title by Artist'; a dash reads as noise."""
    cfg = load_config()
    q = str(query).strip()
    if verify:
        ok, res = song_exists(q)
        if not ok:
            print(f"[HOME] music refused: {q} - {res}"); return False
        q = res
    elif " - " in q:
        t, a = q.split(" - ", 1); q = f"{t.strip()} by {a.strip()}"
    code, resp = ha_request("media_player/play_media", {"entity_id": cfg.get("media_player", "media_player.echo"),
                                                        "media_content_id": f"play {q} on Spotify", "media_content_type": "custom"})
    print(f"[HOME] music: {q} ({code})")
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
    """Colour the lights of one room, or every configured light when no room is named. Govee bulbs get
    the exact colour; the muting step is for the old HA bulbs that flattened anything saturated.
    Success is any bulb lit: a bulb that is not in a lamp is not a failure of the room."""
    exact = hex_to_rgb(hex_color); muted = saturate_for_bulbs(exact)
    lights = room_lights(room)
    _ensure_plugs(lights)
    ok = 0
    for light in lights:
        try:
            ok += int(bool(_light_on(light, rgb=(exact if _is_govee(light) else muted), brightness=brightness)))
        except Exception as e:
            print(f"[HOME] {light}: {e}")
    print(f"[HOME] color {hex_color} on {len(lights)} light(s){' in ' + room if room else ''}: {ok} answered")
    return ok > 0


def flicker(room=None, times=1):
    """Dim, bright, back to a low violet. Mischief, not a scare: bounded and short. One pass by default:
    the Govee cloud reaches bulbs one at a time, so two passes over three bulbs read as a storm."""
    lights = room_lights(room)
    _ensure_plugs(lights)
    for _ in range(times):
        for light in lights: _light_on(light, hs=[0, 0], brightness=10)
        time.sleep(0.25)
        for light in lights: _light_on(light, hs=[0, 0], brightness=254)
        time.sleep(0.2)
    ok = sum(int(bool(_light_on(light, hs=[270, 50], brightness=60))) for light in lights)
    print(f"[HOME] flicker on {len(lights)} light(s){' in ' + room if room else ''}: {ok} answered")
    return ok > 0


# ---------------------------------------------------------------- tv and projector (never the same key)
def _tv():
    return load_config().get("tv", "media_player.bravia_kd_55x80j")


def _projector():
    p = load_config().get("projector")
    if not p:
        raise KeyError("no projector in the config")
    return p


def _projector_power(on):
    """projector may be a media_player entity (HA) or a plug socket 'govee:<id>#1' (its power lead)."""
    p = _projector()
    if _is_govee(p) or p.startswith("switch."):
        ok = _power_plug(p, on)
    else:
        code, _ = ha_request("media_player/turn_on" if on else "media_player/turn_off", {"entity_id": p}); ok = code == 200
    print(f"[HOME] projector {'on' if on else 'off'}: {'ok' if ok else 'failed'}"); return ok


def tv_status():
    try:
        state = ha_state(_tv())
        return {"power": state["state"], "source": state["attributes"].get("source", "unknown"), "app": state["attributes"].get("app_name", "")}
    except Exception:
        return {"power": "unknown", "source": "unknown", "app": ""}


def tv_on():   code, _ = ha_request("media_player/turn_on", {"entity_id": _tv()}); print(f"[HOME] tv_on: {code}"); return code == 200
def tv_off():  code, _ = ha_request("media_player/turn_off", {"entity_id": _tv()}); print(f"[HOME] tv_off: {code}"); return code == 200
def projector_on():  return _projector_power(True)
def projector_off(): return _projector_power(False)


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
    elif cmd == "govee":
        try:
            for d in govee_devices(): print(f"govee:{d['device']:24s} | {d['name']:28s} | {d['sku']:10s} | {', '.join(i or t for t, i in d['capabilities'])[:60]}")
        except Exception as e: print("govee:", e)
    elif cmd == "rooms":
        for name, r in load_config().get("rooms", {}).items(): print(f"{name:12s} plug={r.get('plug')}  lights={len(r.get('lights') or [])}  {r.get('note','')}")
    elif cmd == "off":
        for l in room_lights(args[0] if args else None):
            try: (govee_power(l.split(':', 1)[1], False) if _is_govee(l) else ha_request("light/turn_off", {"entity_id": l}))
            except Exception as e: print(f"[HOME] {l}: {e}")
        print("[HOME] lights off" + (f" in {args[0]}" if args else ""))
    elif cmd == "govee-on": govee_power(msg, True)
    elif cmd == "govee-off": govee_power(msg, False)
    elif cmd == "speak": speak(msg)
    elif cmd == "say": speak(" ".join(args[1:]), volume=int(args[0]))   # say <volume 1-10> <text>
    elif cmd == "announce": announce(msg)
    elif cmd == "color": set_room_color(args[0], room=(args[1] if len(args) > 1 else None))
    elif cmd == "flicker": flicker(args[0] if args else None)
    elif cmd == "plug": plug(args[0], args[1].lower() != "off")
    elif cmd == "music": play_music(msg)
    elif cmd == "song-check": print(song_exists(msg))
    elif cmd == "stop": stop_music()
    elif cmd == "tv_status": print(json.dumps(tv_status(), indent=2))
    elif cmd == "tv_on": tv_on()
    elif cmd == "tv_off": tv_off()
    elif cmd == "tv_source": tv_source(msg)
    elif cmd == "tv_youtube": tv_youtube(msg)
    elif cmd == "projector_on": projector_on()
    elif cmd == "projector_off": projector_off()
    else: print(f"Unknown command: {cmd}")

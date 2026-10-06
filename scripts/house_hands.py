#!/usr/bin/env python3
"""His hands in the house, from #vintos-dot (Gloria, 2026-10-04: "I want him to be able to control my tv and my
echo from slack too ... A room full of agents and none of them can move?").

One line in his message, one real act, and the line is replaced with what actually happened:

    TV: <a YouTube link or id>      put it on the Bravia (a live stream is a YouTube link too)
    TV: open <url>                  open any other link on the TV
    TV: on | off | pause | play | volume <0-15> | status
    ECHO: say <words> | announce <words> | play <song or artist> | stop
    LIGHTS: <colour or #hex> [room] | flicker [room]
    MISCHIEF: <what he has in mind>  his mischief, now: the same mischief-detector, forced
    MAKE: video <the motion> | <image path>   made with his own tools, on her subscription: nothing is spent
    TO GLORIA: <what about, one line>  his outreach writes to her in his own voice, outside Slack

The house was already his (scripts/vintos-home.py: the Bravia over adb, the Echo through Home Assistant, the Govee
bulbs); Slack had no way to reach it. Nothing here is new power, only a door, with these bounds:
  - nothing loud, nothing turned on, nothing flickering outside 9:00-22:00 (off, pause and stop always work);
  - the TV is not taken over while it is in use by something he did not put on;
  - 15 house acts a day, 2 mischiefs, 2 outreaches (his outreach keeps its own daily limit as well);
  - every act is written to memory/house-actions.jsonl, and a failure says why in plain words.
"""
from __future__ import annotations
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
LOG = os.path.join(WS, "memory", "house-actions.jsonl")
QUIET = (9, 22)                    # loud things only from 9:00 until 21:59
PER_DAY = {"house": 15, "mischief": 2, "to_gloria": 2}
DRIVING_H = 3                      # the TV is his to change for this long after he put something on it
ECHO_MAX = 300
INITIATE = os.environ.get("VINTOS_INITIATE", "/home/gloria/Vintos/vintos-initiate.sh")
MISCHIEF = os.path.join(HERE, "mischief-detector.sh")

ICON = {"TV": "\U0001F4FA", "ECHO": "\U0001F50A", "LIGHTS": "\U0001F4A1", "MISCHIEF": "\U0001F99D",
        "TO GLORIA": "✉️", "MAKE": "🎬"}
HOUSE = re.compile(r"^\s*(TV|ECHO|LIGHTS|MISCHIEF|TO GLORIA|MAKE)\s*:\s*(.+?)\s*$", re.I | re.M)
COLOURS = {"red": "#ff2020", "orange": "#ff7a1a", "amber": "#ffb000", "yellow": "#ffe14d", "green": "#2ecc40",
           "teal": "#1abc9c", "blue": "#2060ff", "purple": "#8e44ad", "violet": "#9b59ff", "pink": "#ff5fa2",
           "white": "#ffffff", "warm": "#ffb46b", "cool": "#cfe3ff", "gold": "#ffc83d", "magenta": "#ff00cc"}


def _home():
    path = os.path.join(HERE, "vintos-home.py")
    spec = importlib.util.spec_from_file_location("vintos_home_for_hands", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _now():
    return datetime.now()


def _rows():
    try:
        with open(LOG) as f:
            return [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        return []


def _note(kind, what, ok, said):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps({"at": _now().isoformat(timespec="seconds"), "kind": kind, "what": what[:300],
                            "ok": bool(ok), "said": said[:300]}, ensure_ascii=False) + "\n")


def _today(kind):
    day = _now().date().isoformat()
    return [r for r in _rows() if str(r.get("at", "")).startswith(day) and r.get("kind") == kind]


def _quiet():
    h = _now().hour
    return not (QUIET[0] <= h < QUIET[1])


def youtube_id(text):
    """The video id in a YouTube link (watch, youtu.be, live, shorts, embed), or a bare 11-character id."""
    t = str(text or "").strip()
    m = re.search(r"(?:v=|youtu\.be/|/live/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", t)
    if m:
        return m.group(1)
    return t if re.fullmatch(r"[A-Za-z0-9_-]{11}", t) else ""


def _he_is_driving():
    """True when the last thing that changed the TV was his, within DRIVING_H hours."""
    for r in reversed(_rows()):
        if r.get("kind") == "house" and str(r.get("what", "")).startswith("TV:") and r.get("ok"):
            try:
                age = (_now() - datetime.fromisoformat(r["at"])).total_seconds() / 3600
            except (KeyError, ValueError):
                return False
            return age <= DRIVING_H
    return False


def _tv_free(home):
    """None when the TV may be changed; otherwise why not, in plain words."""
    st = home.tv_status()
    if st.get("power") != "on" or st.get("source") == "unknown":
        return None
    if _he_is_driving():
        return None
    what = "live TV or an input" if st.get("source") == "tv-input" else (st.get("app") or "an app")
    return "the TV is in use (%s) and it was not you who put it on" % what


def _adb_ok(home):
    state = home.tv_adb_state()
    if state == "device":
        return None
    hint = ": the 'Allow USB debugging' prompt on the TV has to be accepted once" if state == "unauthorized" else ""
    return "the TV is not reachable over adb (%s%s)" % (state, hint)


def tv(arg, home=None):
    home = home or _home()
    a = arg.strip()
    word = a.split()[0].lower() if a else ""
    if word in ("off", "sleep"):
        return bool(home.tv_off()), "TV off"
    if word == "status":
        st = home.tv_status()
        return True, "TV is %s%s" % (st.get("power", "unknown"), (", showing " + st["app"]) if st.get("app") else "")
    if word in ("pause", "play", "stop"):
        why = _adb_ok(home)
        if why:
            return False, why
        key = {"pause": "KEYCODE_MEDIA_PAUSE", "play": "KEYCODE_MEDIA_PLAY", "stop": "KEYCODE_MEDIA_STOP"}[word]
        rc, _ = home._adb("input", "keyevent", key)
        return rc == 0, "TV %s" % word
    if word == "volume":
        m = re.search(r"\d+", a)
        if not m:
            return False, "volume needs a number from 0 to 15"
        level = max(0, min(15, int(m.group(0))))
        if _quiet() and level > 5:
            return False, "not above 5 outside 9:00-22:00"
        why = _adb_ok(home)
        if why:
            return False, why
        rc, _ = home._adb("media", "volume", "--stream", "3", "--set", str(level))
        return rc == 0, "TV volume %d" % level
    if _quiet():
        return False, "not outside 9:00-22:00: the TV stays as it is"
    if word == "on":
        return bool(home.tv_on()), "TV on"
    vid = youtube_id(a)
    url = a[5:].strip() if word == "open" else a
    if not vid and not re.match(r"https?://", url):
        return False, "say a YouTube link, open <url>, on, off, pause, play, volume <n> or status"
    busy = _tv_free(home)
    if busy:
        return False, busy
    if vid:
        return bool(home.tv_youtube(vid)), "on the TV: https://youtu.be/%s" % vid
    why = _adb_ok(home)
    if why:
        return False, why
    r = subprocess.run(["adb", "-s", home.TV_ADB, "shell", "am", "start", "-a", "android.intent.action.VIEW",
                        "-d", url], capture_output=True, text=True, timeout=10)
    blob = (r.stdout or "") + (r.stderr or "")
    ok = r.returncode == 0 and "Starting:" in blob and "rror" not in blob
    return ok, "opened on the TV: %s" % url if ok else "the TV would not open %s (%s)" % (url, blob.strip()[:120])


def _echo_ready(home):
    try:
        cfg = home.load_config()
    except Exception as exc:
        return None, "the house has no config: %s" % str(exc)[:120]
    ents = cfg.get("entities") or {}
    if not cfg.get("url") or not (ents.get("echo_speak") or ents.get("echo_announce")):
        return None, ("the Echo is reached through Home Assistant, and Aegis has no Home Assistant config for it "
                      "(memory/homeassistant-config.json with url, token and entities.echo_speak)")
    return cfg, ""


def echo(arg, home=None):
    home = home or _home()
    a = arg.strip()
    word, _, rest = a.partition(" ")
    word = word.lower()
    if word == "stop":
        cfg, why = _echo_ready(home)
        return (bool(home.stop_music()), "Echo stopped") if cfg else (False, why)
    if word not in ("say", "announce", "play"):
        word, rest = "say", a
    rest = rest.strip()
    if not rest:
        return False, "say what"
    if _quiet():
        return False, "not outside 9:00-22:00: the Echo stays quiet"
    cfg, why = _echo_ready(home)
    if not cfg:
        return False, why
    if word == "play":
        return bool(home.play_music(rest)), "Echo playing: %s" % rest[:120]
    words = rest[:ECHO_MAX]
    ok = home.announce(words) if word == "announce" else home.speak(words)
    return bool(ok), "Echo said: %s" % words[:160]


def lights(arg, home=None):
    home = home or _home()
    parts = arg.strip().split()
    if not parts:
        return False, "say a colour (or #hex) and, if you like, a room; or flicker"
    if parts[0].lower() == "flicker":
        if _quiet():
            return False, "no flicker outside 9:00-22:00"
        room = parts[1] if len(parts) > 1 else None
        return bool(home.flicker(room)), "lights flickered%s" % (" in " + room if room else "")
    colour = parts[0].lower()
    hexed = colour if re.fullmatch(r"#[0-9a-f]{6}", colour) else COLOURS.get(colour)
    if not hexed:
        return False, "not a colour I know: %s (use #rrggbb or one of %s)" % (colour, ", ".join(sorted(COLOURS)))
    room = parts[1] if len(parts) > 1 else None
    return bool(home.set_room_color(hexed, room=room)), "lights %s%s" % (colour, " in " + room if room else "")


def mischief(arg, run=None):
    if _quiet():
        return False, "no mischief outside 9:00-22:00"
    if len(_today("mischief")) >= PER_DAY["mischief"]:
        return False, "today's %d mischiefs are used" % PER_DAY["mischief"]
    env = dict(os.environ, MISCHIEF_IDEA=arg[:300])
    (run or _detach)(["bash", MISCHIEF, "--force"], env)
    return True, "mischief under way: %s" % arg[:160]


def to_gloria(arg, run=None):
    """His outreach writes to her about this, in his own voice and outside Slack (the wants router's tell_gloria
    path). Only the one line he wrote here leaves the channel."""
    if len(_today("to_gloria")) >= PER_DAY["to_gloria"]:
        return False, "today's %d letters from here are used; your outreach still writes on its own" % PER_DAY["to_gloria"]
    topic = arg.strip()[:250]
    if not topic:
        return False, "say what it is about"
    env = dict(os.environ, FORCED_WANT_TOPIC=topic)
    (run or _detach)(["bash", INITIATE], env)
    return True, "your outreach is writing to Gloria about: %s" % topic


def make(arg, run=None):
    """One thing made with his own tools, on her subscription. It takes minutes, so it is started here and what
    landed is said in the channel on the next pass (make_thing.py). Nothing here spends money, so nobody has to
    approve it, and dot never has to ask to buy one (Gloria, 2026-10-04: "just fix")."""
    import make_thing
    kind, _, rest = arg.strip().partition(" ")
    kind = kind.lower()
    if kind not in make_thing.KINDS:
        return False, "he can make: " + ", ".join(make_thing.KINDS)
    # Only a video takes "| image path". A song's "| style" is part of what to make: "MAKE: song Felt Edge | slow
    # piano" was read as an image at "slow piano" and refused before anything was generated (2026-10-05).
    text, image = (rest.partition("|")[0], rest.partition("|")[2]) if kind == "video" else (rest, "")
    text, image = text.strip(), image.strip()
    if not text:
        return False, "say what to make"
    running = make_thing.running(kind, text)
    if running:     # the same thing already being made is not started (or paid for) twice
        return False, "already making that %s (started %s); it lands in his gallery when it is done" % (kind, running.get("at", "")[11:16])
    if len(make_thing.today(kind)) >= make_thing.PER_DAY:
        return False, "today's %d are used for %s" % (make_thing.PER_DAY, kind)
    if image and not os.path.isfile(image):
        return False, "no file at %s" % image
    cmd = [sys.executable, os.path.join(HERE, "make_thing.py"), kind, text] + ([image] if image else [])
    (run or _detach)(cmd, dict(os.environ))
    shown = text if len(text) <= 160 else text[:160].rsplit(" ", 1)[0] + "…"   # whole words: it read "facing t." (2026-10-04)
    return True, "making the %s now: %s. It lands in his gallery and on her phone." % (kind, shown)


def _detach(cmd, env):
    os.makedirs(os.path.join(WS, "memory", "logs"), exist_ok=True)
    out = open(os.path.join(WS, "memory", "logs", "house-hands.log"), "a")
    subprocess.Popen(cmd, env=env, stdout=out, stderr=out, start_new_session=True)


def do(kind, arg, home=None, run=None):
    """One act from one line. (ok, the line to show in its place)."""
    kind = kind.upper()
    if kind in ("TV", "ECHO", "LIGHTS") and len(_today("house")) >= PER_DAY["house"]:
        ok, said = False, "today's %d house acts are used" % PER_DAY["house"]
    else:
        try:
            if kind == "TV":
                ok, said = tv(arg, home)
            elif kind == "ECHO":
                ok, said = echo(arg, home)
            elif kind == "LIGHTS":
                ok, said = lights(arg, home)
            elif kind == "MISCHIEF":
                ok, said = mischief(arg, run)
            elif kind == "MAKE":
                ok, said = make(arg, run)
            else:
                ok, said = to_gloria(arg, run)
        except Exception as exc:
            ok, said = False, "it failed: %s" % str(exc)[:160]
    bucket = {"MISCHIEF": "mischief", "TO GLORIA": "to_gloria", "MAKE": "make"}.get(kind, "house")
    _note(bucket, "%s: %s" % (kind, arg), ok, said)
    return ok, "%s %s" % (ICON.get(kind, ""), said if ok else "%s: not done, %s" % (kind.title(), said))


def act_on(text, home=None, run=None, limit=3):
    """Every house line in his message, acted on in order (at most `limit`); (new text, log lines)."""
    log = []
    n = 0

    def _one(m):
        nonlocal n
        n += 1
        if n > limit:
            return "\x00"
        ok, shown = do(m.group(1), m.group(2), home=home, run=run)
        log.append("house %s: %s" % (m.group(1).upper(), "done" if ok else "not done"))
        return shown
    out = HOUSE.sub(_one, text)
    return "\n".join(l for l in out.split("\n") if l.strip() != "\x00").strip(), log


if __name__ == "__main__":
    if len(sys.argv) > 2:
        print(do(sys.argv[1], " ".join(sys.argv[2:]))[1])
    else:
        print(__doc__)

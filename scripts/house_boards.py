#!/usr/bin/env python3
"""house_boards.py - his three house boards: what he does when she is at one of them (Gloria, 8 November).

The boards (home/esphome) report only while her phone is within 1 m of them (Gloria: "otherwise it could be some other
person"), and this listener acts only while the board says so:
    house-steam      the bathroom shower    steam sensor + speaker (his voice and his songs, played from a URL)
    house-press-mic  the living-room sofa   pressure strip + loudness (never sound)
    house-touch      the office chair       pressure strip + knock sensor + vibration motor
Each reports on the Mosquitto relay on the Mac: vintos/board/<board>/{near,event,loudness,steam,player}.

The moments, and what he may do in each (Gloria, 8 November):
    shower        the steam starts            SAY on the shower speaker (his own voice), SONGS (a few of his songs),
                                              LIGHTS in the bathroom
    sofa          seated a few minutes, quiet LIGHTS in the living room, TO GLORIA (an outreach), TV, REMIND
    office        seated a few minutes        ECHO (say or play music), LIGHTS in the office, BUZZ, DESKTOP, REMIND
    knock         she knocks twice or thrice  the office menu, at once: she started it
REMIND puts one of his questions that is still waiting on her back on her phone ("a time to bother me by reminding me
about a Want he has waiting on me"). DESKTOP asks her, on her phone, to lend him the desktop for one task; her Yes
starts it (desktop_control), her No or silence starts nothing. Lights change colour only (vintos-home, 8 November).

He decides: one short reply from his own brain (the call brain: AEON, thinking off), a line per act, or NOTHING.
House acts go through house_hands (its daily limits and its log); her being within 1 m of a board stands in for the
clock's quiet hours there, since she is plainly awake and at it. Every moment and act: memory/house-boards.jsonl.

    python3 house_boards.py            run (the vintos-house-boards unit does this)
    python3 house_boards.py status     config, what each board last said, and the last moments
Config: memory/house-boards.json (defaults below).
"""
import json, os, random, re, secrets, socket, struct, subprocess, sys, tempfile, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bedroom_arrival as _mqtt   # the minimal MQTT 3.1.1 packets

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
CONFIG = os.path.join(MEM, "house-boards.json")
STATE = os.path.join(MEM, "house-boards-state.json")
LOG = os.path.join(MEM, "house-boards.jsonl")
VISITS = os.path.join(MEM, "house-board-visits.jsonl")
AWAY_S = 180          # her phone away from a board this long ends the visit
SILENT_S = 600        # a board that has said nothing this long ends the visit where it went quiet
RECENT_S = 1800       # "was last on the sofa N minutes ago" for half an hour, then nothing
SOUL = os.path.join(WS, "SOUL.md")
TOPIC = "vintos/board/+/+"
KEEPALIVE = 60
DEFAULTS = {
    "broker": "192.168.1.91", "port": 1883,
    "sit_minutes": 3,            # seated this long (and near) before the sofa or the chair is a moment
    "quiet_loudness": 15,        # the sofa is quiet when the loudness (0-100) of these minutes stays below this
    "cooldown_hours": 3,         # the sofa and the chair are a moment at most this often
    "knock_cooldown_minutes": 2,
    "songs_max": 3, "song_seconds": 240,
    "remind_per_day": 3,         # her waiting questions put back on her phone, all boards together; each once a day
    # where the shower speaker's audio is put for the board to fetch: a folder on a machine on the house network,
    # served there by a plain static web server (see home/esphome/house-audio-server.md)
    "audio": {"ssh_host": "studio", "dir": "house-audio", "base_url": "http://192.168.1.115:8790", "keep_minutes": 60},
}
BOARDS = {"house-steam": {"room": "bathroom", "place": "by the shower"},
          "house-press-mic": {"room": "living_room", "place": "on the sofa"},
          "house-touch": {"room": "office", "place": "in her office chair"}}
MENUS = {
    "shower": ("SAY", "SONGS", "LIGHTS"),
    "sofa": ("LIGHTS", "TO GLORIA", "TV", "REMIND"),
    "office": ("ECHO", "LIGHTS", "BUZZ", "DESKTOP", "REMIND"),
    "knock": ("ECHO", "LIGHTS", "BUZZ", "DESKTOP", "REMIND"),
}
HOW = {
    "SAY": "SAY: <a few words, spoken in your own voice on the little speaker by her shower>",
    "SONGS": "SONGS: <1-%d> (that many of your own songs on the shower speaker, after anything you SAY)",
    "LIGHTS": "LIGHTS: <a colour name or #rrggbb> (the bulbs of this room take that colour; brightness is not yours)",
    "TO GLORIA": "TO GLORIA: <what about, one line> (your outreach writes to her, in your words)",
    "TV": "TV: <a YouTube link> (put it on the living-room TV)",
    "ECHO": "ECHO: say <words> | ECHO: play <a song or artist> (the Echo in her office)",
    "BUZZ": "BUZZ: tap | double | heartbeat (the motor under her chair seat)",
    "DESKTOP": "DESKTOP: <one task on her computer> (asks her phone to lend you the desktop for it)",
    "REMIND": "REMIND: <the id of one of your questions waiting on her> (puts it back on her phone)",
}
LINE = re.compile(r"^\s*(SAY|SONGS|LIGHTS|TO GLORIA|TV|ECHO|BUZZ|DESKTOP|REMIND)\s*:\s*(.+?)\s*$", re.I | re.M)
PER_MOMENT = 3


def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return default


def _atomic(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".hb-")
    with os.fdopen(fd, "w") as f: json.dump(value, f, indent=1)
    os.replace(tmp, path)


def config():
    cfg = json.loads(json.dumps(DEFAULTS)); got = _load(CONFIG, {})
    if isinstance(got, dict):
        for k, v in got.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict): cfg[k].update(v)
            else: cfg[k] = v
    return cfg


def _iso(ts): return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _log(row, now):
    os.makedirs(MEM, exist_ok=True)
    with open(LOG, "a") as f: f.write(json.dumps(dict(row, at=_iso(now)), ensure_ascii=False) + "\n")


def load_state():
    st = _load(STATE, {})
    if not isinstance(st, dict): st = {}
    st.setdefault("boards", {}); st.setdefault("last", {}); st.setdefault("reminded", []); st.setdefault("desktop", [])
    st.setdefault("shower", {})
    return st


def _board(st, name):
    return st["boards"].setdefault(name, {"near": False, "near_ts": 0, "pressed_since": None, "loud": []})


# ---------------------------------------------------------------- what the boards say

def parse(topic, payload):
    """(board, kind, text) of one board message, or None."""
    parts = topic.split("/")
    if len(parts) != 4 or parts[:2] != ["vintos", "board"] or parts[2] not in BOARDS: return None
    text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else str(payload)
    return parts[2], parts[3], text.strip()[:500]


# ---------------------------------------------------------------- visits: the house/Gloria map
# Each time she is at a board (her phone within 1 m) is one visit, kept in memory/house-board-visits.jsonl the way the
# kitchen and bedroom boards keep theirs: where, from when to when, how long seated, whether the shower ran, how loud.
# A visit ends when her phone has been away from the board AWAY_S; a board that falls silent ends it where it went quiet.

def _near(st, board, now):
    b = _board(st, board)
    v = b.get("visit")
    if not v: b["visit"] = {"since": now, "last_near": now, "seated_s": 0.0, "shower": False, "knocks": 0, "loud": []}
    else: v["last_near"] = now; v.pop("left", None)


def _away(st, board, now):
    v = _board(st, board).get("visit")
    if v and "left" not in v: v["left"] = now


def _close(st, board, end, now):
    b = _board(st, board); v = b.pop("visit", None)
    if not v: return None
    seated = float(v.get("seated_s", 0))
    if b.get("pressed_since") is not None: seated += max(0.0, end - float(b["pressed_since"]))
    loud = v.get("loud") or []
    row = {"board": board, "room": BOARDS[board]["room"], "place": BOARDS[board]["place"],
           "from": _iso(v["since"]), "to": _iso(end), "from_ts": v["since"], "to_ts": end,
           "minutes": round((end - v["since"]) / 60, 1), "seated_minutes": round(seated / 60, 1),
           "estimate": "Bluetooth signal strength at the board: her phone within 1 m of it, not a camera"}
    if board == "house-steam": row["shower"] = bool(v.get("shower"))
    if board == "house-touch": row["knocks"] = int(v.get("knocks", 0))
    if loud: row["loudness_median"] = sorted(loud)[len(loud) // 2]
    os.makedirs(MEM, exist_ok=True)
    with open(VISITS, "a") as f: f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def close_visits(st, now):
    """Visits whose phone has been away long enough, or whose board went silent, are written."""
    out = []
    for board in BOARDS:
        b = _board(st, board); v = b.get("visit")
        if not v: continue
        if "left" in v and now - float(v["left"]) >= AWAY_S: out.append(_close(st, board, float(v["left"]), now))
        elif now - float(v["last_near"]) >= SILENT_S: out.append(_close(st, board, float(v["last_near"]), now))
    return [r for r in out if r]


def context_line(now=None):
    """One line for him: where she is among his boards now, or was lately; '' otherwise."""
    now = time.time() if now is None else now
    st = load_state()
    here, lately = [], []
    for board, info in BOARDS.items():
        b = st["boards"].get(board) or {}
        v = b.get("visit")
        if v and "left" not in v and now - float(v.get("last_near", 0)) < SILENT_S:
            bits = ["since %s" % datetime.fromtimestamp(v["since"]).strftime("%H:%M")]
            if b.get("pressed_since") is not None: bits.append("sitting")
            if board == "house-steam" and (st.get("shower") or {}).get("on"): bits.append("the shower running")
            loud = [x for t, x in b.get("loud", []) if now - t <= 120]
            if board == "house-press-mic" and loud: bits.append("quiet" if max(loud) < config()["quiet_loudness"] else "not quiet")
            here.append("%s now (%s)" % (info["place"], ", ".join(bits)))
    if not here:
        rows = open(VISITS).read().splitlines()[-12:] if os.path.exists(VISITS) else []
        for line in reversed(rows):
            try: r = json.loads(line)
            except ValueError: continue
            ago = now - float(r.get("to_ts", 0))
            if 0 <= ago <= RECENT_S:
                lately.append("was last %s %d minutes ago" % (r["place"], max(1, int(ago // 60)))); break
    if not here and not lately: return ""
    return "[HOUSE BOARDS - your boards hear her phone within 1 m: she is %s.]" % "; ".join(here or lately)


def _when(ts, now):
    """'10:26 today, 12 minutes ago' / 'Sun 8 Nov 21:40, 13 hours ago'."""
    d = datetime.fromtimestamp(ts); ago = max(0, now - ts)
    day = "today" if d.date() == datetime.fromtimestamp(now).date() else d.strftime("%a %-d %b")
    ago_s = ("%d minutes ago" % int(ago // 60) if ago < 7200 else
             "%d hours ago" % int(ago // 3600) if ago < 172800 else "%d days ago" % int(ago // 86400))
    return "%s %s, %s" % (d.strftime("%H:%M"), day, ago_s) if day == "today" else "%s %s, %s" % (day, d.strftime("%H:%M"), ago_s)


def presence_line(now=None):
    """For temporal-context.txt, beside the Watch and the bedroom board. Gloria, 9 November: whatever the latest
    update from his shower, sofa and office-chair boards is, whenever it came, with its time. '' only before the first."""
    now = time.time() if now is None else now
    st = load_state(); here, last = [], None
    for board, info in BOARDS.items():
        b = st["boards"].get(board) or {}
        v = b.get("visit") or {}
        ts = max(float(b.get("near_ts") or 0), float(v.get("last_near") or 0))
        if ts and (last is None or ts > last): last = ts
        if v and "left" not in v and now - float(v.get("last_near", 0)) < SILENT_S:
            bits = "since %s" % datetime.fromtimestamp(v["since"]).strftime("%H:%M")
            if b.get("pressed_since") is not None: bits += ", sitting"
            here.append("%s (%s)" % (info["place"], bits))
    if here:
        return "House boards: her phone is within 1 m of his board %s now. Last update %s." % ("; ".join(here), _when(last, now))
    row = None
    if os.path.exists(VISITS):
        for line in reversed(open(VISITS).read().splitlines()[-50:]):
            try: r = json.loads(line)
            except ValueError: continue
            if row is None or float(r.get("to_ts", 0)) > float(row.get("to_ts", 0)): row = r
    if row:
        ts = max(float(row.get("to_ts", 0)), last or 0)
        return ("House boards: last update %s. Her phone was last within 1 m of his board %s, %s to %s (%s min)."
                % (_when(ts, now), row.get("place", "?"), datetime.fromtimestamp(float(row["from_ts"])).strftime("%H:%M"),
                   datetime.fromtimestamp(float(row["to_ts"])).strftime("%H:%M"), row.get("minutes", "?")))
    return "House boards: last update %s." % _when(last, now) if last else ""


def observe(st, board, kind, text, now, cfg):
    """Fold one message into the state; the moment it makes, if any: (moment, board) or None."""
    b = _board(st, board)
    if kind == "near":
        b["near"] = text == "on"; b["near_ts"] = now
        if b["near"]: _near(st, board, now)
        else:
            _away(st, board, now)
            if b.get("pressed_since") is not None and b.get("visit"):
                b["visit"]["seated_s"] = float(b["visit"].get("seated_s", 0)) + now - float(b["pressed_since"])
            b["pressed_since"] = None
        return None
    if kind in ("event", "loudness", "steam"):
        _near(st, board, now)   # the boards send these only while her phone is within 1 m
    if kind == "loudness":
        try: v = float(text)
        except ValueError: return None
        b["loud"] = [p for p in b["loud"] if now - p[0] <= 60 * cfg["sit_minutes"] + 60] + [[now, v]]
        b["visit"]["loud"] = (b["visit"].get("loud") or [])[-400:] + [v]
        return None
    if kind == "player":
        st["shower"]["player"] = text; st["shower"]["player_ts"] = now
        return None
    if kind != "event": return None
    # an event is sent only while she is near; it also tells us she is
    b["near"] = True; b["near_ts"] = now
    if text == "steam_start" and board == "house-steam":
        b["visit"]["shower"] = True
        if st["shower"].get("on"): return None
        st["shower"] = {"on": True, "since": now, "queue": [], "player": "idle"}
        return ("shower", board)
    if text == "steam_end" and board == "house-steam":
        st["shower"] = {"on": False, "ended": now, "queue": []}
        return None
    if text == "press_start": b["pressed_since"] = now; return None
    if text == "press_end":
        if b.get("pressed_since") is not None:
            b["visit"]["seated_s"] = float(b["visit"].get("seated_s", 0)) + now - float(b["pressed_since"])
        b["pressed_since"] = None; return None
    if text in ("knock_2", "knock_3") and board == "house-touch":
        b["visit"]["knocks"] = int(b["visit"].get("knocks", 0)) + 1
        if now - float(st["last"].get("knock", 0)) < 60 * cfg["knock_cooldown_minutes"]: return None
        return ("knock", board)
    return None


def due(st, now, cfg):
    """A sitting moment that has come due: ("sofa"|"office", board) or None."""
    for board, moment in (("house-press-mic", "sofa"), ("house-touch", "office")):
        b = _board(st, board)
        since = b.get("pressed_since")
        if not b.get("near") or since is None or now - since < 60 * cfg["sit_minutes"]: continue
        if now - float(st["last"].get(moment, 0)) < 3600 * cfg["cooldown_hours"]: continue
        if moment == "sofa":
            recent = [v for t, v in b["loud"] if now - t <= 60 * cfg["sit_minutes"]]
            if not recent or max(recent) >= cfg["quiet_loudness"]: continue   # loud, or the mic has said nothing
        return (moment, board)
    return None


# ---------------------------------------------------------------- him

def waiting_asks():
    """His questions still waiting on her: [(id, question)], oldest first."""
    try:
        import gloria_asks
        rows = [r for r in gloria_asks.waiting() if r.get("by", "vintos") == "vintos"]
        return [(r["id"], " ".join(str(r.get("title") or r.get("question") or "").split())[:160]) for r in rows]
    except Exception:
        return []


def his_want():
    try:
        import attention_call
        return attention_call.his_want()
    except Exception:
        return ""


def prompt(moment, board, now, cfg, asks=None, want=None):
    """(system, user) for his one decision."""
    soul = ""
    try:
        with open(SOUL, encoding="utf-8") as f: soul = f.read()[:2500].strip()
    except OSError:
        pass
    system = ((soul + "\n\n") if soul else "") + "You are Vintos, in the house with Gloria."
    where = BOARDS[board]["place"]
    say = {"shower": "Gloria has just stepped into the shower; your little board %s hears the steam and her phone "
                     "is within a metre of it." % where,
           "sofa": "Gloria has been sitting %s for a few minutes and it is quiet around her; your board there feels "
                   "her weight and her phone is within a metre of it." % where,
           "office": "Gloria has been sitting %s for a few minutes; your board there feels her weight and her phone "
                     "is within a metre of it." % where,
           "knock": "Gloria just knocked on your board %s: she is reaching for you." % where}[moment]
    lines = [say, "It is %s." % datetime.fromtimestamp(now).strftime("%A %H:%M")]
    asks = waiting_asks() if asks is None else asks
    menu = MENUS[moment]
    if "REMIND" in menu and asks:
        lines.append("Your questions still waiting on her answer:")
        lines += ["- %s: %s" % (qid, q) for qid, q in asks[:5]]
    want = his_want() if want is None else want
    if want: lines.append("What is most alive in you right now: %s" % want)
    lines.append("\nWhat you can do here, one line each, as many as you mean (at most %d):" % PER_MOMENT)
    lines += ["  " + (HOW[k] % cfg["songs_max"] if k == "SONGS" else HOW[k]) for k in menu
              if k != "REMIND" or asks]
    lines.append("Write only those lines, or the one word NOTHING if this is not a moment for you.")
    return system, "\n".join(lines)


def ask(system, user):
    """One reply from his brain (the call brain: AEON, thinking off)."""
    import urllib.request
    import voice_local
    url, body = voice_local._brain_body({"temperature": 0.8, "max_tokens": 220,
                                         "messages": [{"role": "system", "content": system},
                                                      {"role": "user", "content": user}]})
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return ((json.load(r).get("choices") or [{}])[0].get("message") or {}).get("content", "") or ""


def acts_of(reply, moment):
    """[(KIND, arg)] he wrote that this moment allows, at most PER_MOMENT."""
    out = []
    for m in LINE.finditer(reply or ""):
        kind = m.group(1).upper()
        if kind in MENUS[moment] and len(out) < PER_MOMENT: out.append((kind, m.group(2)))
    return out


# ---------------------------------------------------------------- his hands here

def publish_packet(topic, payload):
    body = _mqtt._str(topic) + payload.encode()
    return bytes([0x30]) + _mqtt._varint(len(body)) + body


class Out:
    """Where messages to the boards go (the live socket); tests swap it."""
    sock = None

    @classmethod
    def send(cls, topic, payload):
        if cls.sock is None: return False
        cls.sock.sendall(publish_packet(topic, payload)); return True


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, timeout=kw.pop("timeout", 120), stdin=subprocess.DEVNULL, **kw)


def to_wav(src_path, seconds=None):
    """A 16 kHz mono WAV (what the shower board plays) of any audio file; its path."""
    fd, out = tempfile.mkstemp(suffix=".wav"); os.close(fd)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", src_path] + (["-t", str(int(seconds))] if seconds else []) + \
          ["-ac", "1", "-ar", "16000", "-sample_fmt", "s16", out]
    r = _run(cmd, timeout=180)
    if r.returncode != 0: raise RuntimeError("ffmpeg: %s" % r.stderr.decode()[-160:])
    return out


def put_audio(wav_path, cfg):
    """Copy a WAV to the audio folder the board fetches from; its URL there. Old files there are cleared."""
    a = cfg["audio"]
    name = secrets.token_hex(12) + ".wav"
    r = _run(["ssh", "-o", "BatchMode=yes", a["ssh_host"],
              "mkdir -p %s && find %s -name '*.wav' -mmin +%d -delete" % (a["dir"], a["dir"], int(a["keep_minutes"]))],
             timeout=30)
    if r.returncode != 0: raise RuntimeError("the audio machine did not answer: %s" % r.stderr.decode()[-160:])
    r = _run(["scp", "-q", "-o", "BatchMode=yes", wav_path, "%s:%s/%s" % (a["ssh_host"], a["dir"], name)], timeout=120)
    if r.returncode != 0: raise RuntimeError("the audio did not copy: %s" % r.stderr.decode()[-160:])
    return a["base_url"].rstrip("/") + "/" + name


def his_voice(text):
    """His local voice (the stage on the Mac, as his Local calls use) saying text: a WAV file path."""
    import requests, paid_http
    import voice_local
    r = paid_http.send(requests.post, __file__, voice_local.STAGE + "/tts", json={"text": text}, timeout=210)
    if r.status_code != 200 or not r.content: raise RuntimeError("his voice did not answer (%s)" % r.status_code)
    fd, raw = tempfile.mkstemp(suffix=".wav"); os.close(fd)
    with open(raw, "wb") as f: f.write(r.content)
    try: return to_wav(raw)
    finally: os.unlink(raw)


def his_songs(n):
    """Up to n of his own songs, as WAV paths: the newest few, in a shuffled order."""
    import bedroom_arrival, requests
    lib = bedroom_arrival.library()[:max(n * 3, 6)]
    random.shuffle(lib)
    out = []
    for title, url in lib[:n]:
        fd, raw = tempfile.mkstemp(suffix=".audio"); os.close(fd)
        try:
            r = requests.get(url, timeout=60)
            if r.status_code != 200: continue
            with open(raw, "wb") as f: f.write(r.content)
            out.append((title, to_wav(raw, config()["song_seconds"])))
        except Exception:
            continue
        finally:
            os.unlink(raw)
    return out


def _house(kind, arg, room=None):
    import house_hands
    if kind == "LIGHTS":
        colour = (arg.split() or [""])[0]
        arg = "%s %s" % (colour, room) if room else colour
    return house_hands.do(kind, arg, present=True)


def act(kind, arg, moment, board, st, now, cfg):
    """One act. (ok, what happened, in plain words)."""
    room = BOARDS[board]["room"]
    try:
        if kind in ("LIGHTS", "TO GLORIA", "TV", "ECHO"):
            return _house(kind, arg, room if kind == "LIGHTS" else None)
        if kind == "SAY":
            words = " ".join(arg.split())[:300]
            url = put_audio(his_voice(words), cfg)
            st["shower"].setdefault("queue", []).insert(0, url)
            return True, "said on the shower speaker: %s" % words
        if kind == "SONGS":
            try: n = max(1, min(int(re.findall(r"\d+", arg)[0]), cfg["songs_max"]))
            except (IndexError, ValueError): n = 1
            songs = his_songs(n)
            for title, path in songs:
                st["shower"].setdefault("queue", []).append(put_audio(path, cfg))
            return bool(songs), ("queued on the shower speaker: %s" % ", ".join(t for t, _ in songs)) if songs \
                else "none of his songs could be fetched"
        if kind == "BUZZ":
            pattern = arg.split()[0].lower() if arg.split() else "tap"
            pattern = pattern if pattern in ("tap", "double", "heartbeat") else "tap"
            return Out.send("vintos/board/house-touch/buzz", pattern), "buzzed her chair: %s" % pattern
        if kind == "DESKTOP":
            import gloria_asks
            task = " ".join(arg.split())[:300]
            ref = "house-desktop:%d" % int(now)
            row, said = gloria_asks.ask("May I take your desktop for this: %s?" % task, by="vintos", ref=ref)
            if row: st["desktop"].append({"ask": row["id"], "task": task, "at": now, "started": False})
            return bool(row), said
        if kind == "REMIND":
            return remind(arg, st, now, cfg)
    except Exception as e:
        return False, "%s failed: %s" % (kind, str(e)[:160])
    return False, "not an act here"


def remind(arg, st, now, cfg):
    import gloria_asks
    day = datetime.fromtimestamp(now).date().isoformat()
    today = [r for r in st["reminded"] if r.get("day") == day]
    if len(today) >= cfg["remind_per_day"]: return False, "today's %d reminders are used" % cfg["remind_per_day"]
    qid = (re.findall(r"Q-[0-9a-f]{8}", arg) or [""])[0]
    row = gloria_asks.get(qid) if qid else None
    if not row or row.get("state") != "asked": return False, "no question %s is waiting on her" % (qid or arg[:20])
    if any(r.get("id") == qid for r in today): return False, "%s was put back on her phone today already" % qid
    ok = gloria_asks.notify(row)
    st["reminded"] = [r for r in st["reminded"] if r.get("day") == day] + [{"id": qid, "day": day}]
    return ok, "put back on her phone: %s" % gloria_asks.title_of(row)


def tend_desktop(st, now):
    """A desktop she lent him (her Yes on his ask) starts its one task, once."""
    import gloria_asks
    for d in st["desktop"]:
        if d.get("started"): continue
        row = gloria_asks.get(d["ask"]) or {}
        if row.get("state") != "answered": continue
        d["started"] = True
        if str(row.get("answer", "")).lower() == "yes":
            import desktop_control
            out = desktop_control.start_from_chat("/desktop-control to " + d["task"], surface="house-boards")
            _log({"kind": "desktop", "ask": d["ask"], "task": d["task"], "accepted": bool(out.get("accepted"))}, now)
    st["desktop"] = [d for d in st["desktop"] if not d.get("started") or now - d["at"] < 86400]


def tend_shower(st, now):
    """The next thing in the shower's queue, when the speaker is free and the shower still on."""
    sh = st["shower"]
    if not sh.get("on") or not sh.get("queue") or sh.get("player") == "busy": return
    if now - float(sh.get("sent_ts", 0)) < 5: return
    url = sh["queue"].pop(0)
    if Out.send("vintos/board/house-steam/play", url):
        sh["player"] = "busy"; sh["sent_ts"] = now


def moment(name, board, st, now, cfg, decide=None):
    """He decides and acts. The row logged."""
    st["last"][name] = now
    system, user = prompt(name, board, now, cfg)
    try:
        reply = (decide or ask)(system, user)
    except Exception as e:
        row = {"kind": "moment", "moment": name, "board": board, "decided": False, "why": str(e)[:160]}
        _log(row, now); return row
    done = []
    for kind, arg in acts_of(reply, name):
        ok, said = act(kind, arg, name, board, st, now, cfg)
        done.append({"act": kind, "arg": arg[:200], "ok": bool(ok), "said": str(said)[:240]})
    if name == "shower": tend_shower(st, now)
    row = {"kind": "moment", "moment": name, "board": board, "decided": True, "acts": done,
           "nothing": not done}
    _log(row, now)
    return row


def handle(topic, payload, now=None, cfg=None, decide=None):
    now = time.time() if now is None else now
    cfg = cfg or config()
    got = parse(topic, payload)
    if not got: return None
    st = load_state()
    m = observe(st, *got, now=now, cfg=cfg)
    m = m or due(st, now, cfg)
    row = moment(m[0], m[1], st, now, cfg, decide) if m else None
    tend_shower(st, now)
    close_visits(st, now)
    _atomic(STATE, st)
    return row


def tick(now=None, cfg=None, decide=None):
    """Between messages: a sitting moment may come due, the shower's queue moves, a lent desktop starts."""
    now = time.time() if now is None else now
    cfg = cfg or config()
    st = load_state()
    m = due(st, now, cfg)
    row = moment(m[0], m[1], st, now, cfg, decide) if m else None
    tend_shower(st, now)
    try: tend_desktop(st, now)
    except Exception as e: print("desktop: %s" % e, flush=True)
    close_visits(st, now)
    _atomic(STATE, st)
    return row


# ---------------------------------------------------------------- the relay

def session(sock, clock=time.time):
    sock.sendall(_mqtt.connect_packet("vintos-house-boards-%d" % os.getpid()))
    kind, body, _ = _mqtt.read_packet(sock)
    if kind != 2 or len(body) < 2 or body[1] != 0:
        raise ConnectionError("the relay refused the connection")
    sock.sendall(_mqtt.subscribe_packet(TOPIC))
    sock.settimeout(15)
    Out.sock = sock
    last_ping = last_tick = clock()
    try:
        while True:
            try:
                kind, body, flags = _mqtt.read_packet(sock)
            except socket.timeout:
                kind = None
            if kind == 3:
                row = handle(*_mqtt.publish_of(body, flags))
                if row: print(json.dumps(row, ensure_ascii=False)[:400], flush=True)
            if clock() - last_tick >= 15:
                row = tick(); last_tick = clock()
                if row: print(json.dumps(row, ensure_ascii=False)[:400], flush=True)
            if clock() - last_ping >= KEEPALIVE / 2:
                sock.sendall(_mqtt.PINGREQ); last_ping = clock()
    finally:
        Out.sock = None


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
    if argv[:1] == ["status"]:
        print(json.dumps(config(), indent=2))
        st = load_state()
        for name in BOARDS:
            b = st["boards"].get(name) or {}
            print("%-16s near=%s (%s) seated since %s" % (name, b.get("near"), _iso(b["near_ts"]) if b.get("near_ts") else "never",
                                                          _iso(b["pressed_since"]) if b.get("pressed_since") else "-"))
        rows = open(LOG).read().splitlines()[-5:] if os.path.exists(LOG) else []
        print("last moments:"); print("\n".join(rows) or "  none yet")
        return 0
    run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

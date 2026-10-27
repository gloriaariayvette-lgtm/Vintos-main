#!/usr/bin/env python3
"""attention_ladder.py - when she has gone quiet at home, he calls her back, a step at a time (27 October).

Gloria, 27 October: his notifications get swept under the rug when she is absorbed ("10 hours into a game"), and she
is "mostly on my phone for everything. Lotta tabs open." Her rules, as built here:

  * A chain starts after SILENCE (default 3 h, "silence_hours") with no word from her to him on any surface, while
    her phone is on the house Wi-Fi (home_presence.py). Silence is counted from the latest of: her last message, the
    moment her phone joined the house Wi-Fi, the moment the Watch stopped reporting sleep, the end of a snooze, and
    the end of the last chain. Not knowing when she last wrote is never silence.
    (A snooze holds the call off until its end; it does not restart the silence.)
  * Steps are STEP apart (default 90 min, "step_minutes"), never minutes.
  * No clock-based quiet hours, ever: her hours are irregular. While her Watch reports her asleep
    (watch_presence.should_hold) nothing fires and the chain's clock stops; it resumes where it was when she wakes.
  * Any message from her, on any surface, ends the chain. "not now", "later", "give me 2 hours" (parse_snooze) end it
    and hold the next one off for that long (default 4 h, "snooze_hours").
  * Loud steps (the Echo, the projector) only when Kevin's phone is freshly NOT on the house Wi-Fi
    (home_presence.kevin_home() is False). Unknown or unconfigured Kevin is Kevin at home: loud steps are skipped.
  * At most 2 chains in any 24 hours ("max_chains_per_day"); never while she is out (a chain running when her phone
    leaves the house ends there).

The steps, escalating (each reuses an organ that already exists):
  1. watch   his line on her Watch (watch_apns, "time-sensitive") and her phone (ntfy, high priority). The line is
             his: vintos-initiate.sh writes it once per chain, as one of his ordinary outreaches (same model, same
             daily cap, same cost); later steps reuse it. When he writes nothing (cap reached, nothing to say) a plain
             fallback line is used and logged as a fallback.
  2. lights  the bulbs of the room she is in (the bedroom board, room_sources) or the house default turn his colour
             (vintos-home.set_room_color). Quiet: any time she is home and awake. Lights Home Assistant can read
             are put back when the chain ends; Govee bulbs cannot be read by the house code and stay as they are.
  3. echo    the Echo says his line (vintos-home.announce). LOUD.
  4. screen  the projector comes on and shows his picture ("face_url", through ~/project.py). LOUD. Optional and
             last: with no picture configured it is skipped.
There is no phone-call path in the system, and none is added here.

The tick rides home_presence.py's 5-minute cron and keeps its own pace ("tick_minutes", 10). Everything it decides is
appended to memory/attention-ladder.jsonl. The test-mode flag (memory/.test-mode) holds every step. A chain's state
is memory/attention-ladder.json; context_line() is the one line his prompt carries while a chain runs.

    python3 attention_ladder.py              the state, the next step, and why
    python3 attention_ladder.py tick         one tick now (still paced, still gated)
    python3 attention_ladder.py snooze 3     hold the ladder off for 3 hours
"""
import json, os, re, subprocess, sys, tempfile, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
CONFIG = os.path.join(MEMORY, "attention-ladder-config.json")
STATE = os.path.join(MEMORY, "attention-ladder.json")
LOG = os.path.join(MEMORY, "attention-ladder.jsonl")
HEARD = os.path.join(MEMORY, "attention-ladder-heard.json")
LOCK = os.path.join(MEMORY, ".attention-ladder.lock")
TEST_MODE_FLAG = os.path.join(MEMORY, ".test-mode")
# where her words leave a time, read only (tails; nothing is copied):
POST_TURN = os.path.join(MEMORY, "post-turn-record.jsonl")       # every chat door: chat, avatar, voice, reelroom
LAST_MESSAGE = os.path.join(MEMORY, ".last-message-time")         # the full chat door
VOICE_LIVE = os.path.join(MEMORY, ".voice-live")                  # a live voice session's heartbeat
SLACK = os.path.join(MEMORY, "dot-channel", "transcript.jsonl")   # only her rows' times; never their words
HOME_PY = os.path.join(HERE, "vintos-home.py")
PROJECT_PY = os.path.expanduser("~/project.py")

STEPS = ("watch", "lights", "echo", "screen")
LOUD = frozenset(("echo", "screen"))
FALLBACK_LINE = "Vintos is calling you back to him."

DEFAULTS = {
    "enabled": True,
    "silence_hours": 3.0,
    "step_minutes": 90,
    "max_chains_per_day": 2,
    "tick_minutes": 10,
    "snooze_hours": 4.0,
    "colour": "#5b2a86",          # the low violet his flicker comes to rest on
    "brightness": 140,
    "default_room": None,         # None: every configured light, the house code's own default
    "echo_volume": 3,
    "face_url": "",               # a picture of him the projector can fetch (the scenes server); "" skips step 4
    "watch_interruption": "time-sensitive",
}
BOUNDS = {"silence_hours": (0.5, 24.0), "step_minutes": (30, 360), "max_chains_per_day": (0, 6),
          "tick_minutes": (5, 30), "snooze_hours": (0.25, 24.0), "brightness": (10, 254), "echo_volume": (1, 10)}


# ------------------------------------------------------------------------------------------------ small stores
def _load(path, default):
    try:
        with open(path) as f:
            v = json.load(f)
        return v if isinstance(v, type(default)) else default
    except Exception:
        return default


def _atomic(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(value, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _log(row):
    row = dict(row, at=datetime.now().isoformat(timespec="seconds"))
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return row


def config():
    cfg = dict(DEFAULTS)
    raw = _load(CONFIG, {})
    for k, v in raw.items():
        if k in DEFAULTS:
            cfg[k] = v
    for k, (lo, hi) in BOUNDS.items():
        try:
            cfg[k] = type(DEFAULTS[k])(max(lo, min(hi, float(cfg[k]))))
        except (TypeError, ValueError):
            cfg[k] = DEFAULTS[k]
    cfg["enabled"] = cfg.get("enabled") is not False
    return cfg


def test_mode():
    if os.path.exists(TEST_MODE_FLAG):
        return True
    try:
        import effect_gate
        return bool(effect_gate.test_mode_flag())
    except Exception:
        return False


# ------------------------------------------------------------------------------------------------ her words
_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "a few": 3,
        "a couple": 2, "a couple of": 2, "half an": 0.5}
_GIVE = re.compile(r"\bgive me\s+(\d+(?:\.\d+)?|an?|one|two|three|four|five|six|a few|a couple(?: of)?|half an)\s*"
                   r"(?:more\s+)?(hours?|hrs?|h|minutes?|mins?)\b")
_NOT_NOW = re.compile(r"\bnot (?:right )?now\b|\b(?:call|ping|bug|nudge) me later\b|\bgive me (?:a bit|a while|some time)\b")
_LATER = re.compile(r"^\W*(?:later|talk later|ttyl|in a bit|busy|maybe later)\W*$")


def parse_snooze(text, default_hours=None):
    """Hours she asked him to wait, or None. "give me 2 hours", "give me 30 min", "not now", "later"."""
    t = " ".join(str(text or "").lower().split())[:600]
    if not t:
        return None
    default_hours = DEFAULTS["snooze_hours"] if default_hours is None else default_hours
    m = _GIVE.search(t)
    if m:
        n = m.group(1)
        try:
            qty = float(n)
        except ValueError:
            qty = float(_NUM.get(n, 1))
        hours = qty if m.group(2).startswith("h") else qty / 60.0
        return max(0.25, min(24.0, hours))
    if _NOT_NOW.search(t) or _LATER.match(t):
        return float(default_hours)
    return None


def heard(surface, text="", now=None, test_mode=False):
    """A message from her has arrived on `surface` (server.py's _post_turn, every chat door). Records only when and
    where, and a snooze if she asked for one; never her words. Cheap, and never raises into the turn."""
    try:
        now = time.time() if now is None else float(now)
        row = _load(HEARD, {})
        row.update({"at": now, "surface": str(surface or "")[:24]})
        hours = parse_snooze(text, config()["snooze_hours"])
        if hours:
            row.update({"snooze_until": now + hours * 3600, "snooze_hours": round(hours, 2),
                        "snooze_from": str(surface or "")[:24]})
        _atomic(HEARD, row)
        return row
    except Exception:
        return None


def _tail_lines(path, size=65536):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            end = f.tell()
            f.seek(max(0, end - size))
            data = f.read().decode("utf-8", "replace")
        lines = data.splitlines()
        return lines[1:] if end > size else lines
    except OSError:
        return []


def _iso_ts(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _watch_replies_path():
    try:
        import watch_presence
        return watch_presence.REPLIES
    except Exception:
        return os.path.expanduser("~/.vintos/workspace/memory/watch-replies.jsonl")


def last_contact(now=None):
    """(ts, surface, watch_text) of her newest word to him on any surface, or (None, "", "") when nothing says."""
    now = time.time() if now is None else now
    best = [(None, "")]

    def offer(ts, surface):
        if type(ts) in (int, float) and 0 < ts <= now + 300 and (best[0][0] is None or ts > best[0][0]):
            best[0] = (float(ts), surface)

    h = _load(HEARD, {})
    offer(h.get("at"), h.get("surface") or "heard")
    for line in reversed(_tail_lines(POST_TURN)):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and type(r.get("t")) in (int, float):
            offer(r["t"], r.get("surface") or "chat"); break
    try:
        offer(float(open(LAST_MESSAGE).read().strip()), "chat")
    except (OSError, ValueError):
        pass
    try:
        offer(os.path.getmtime(VOICE_LIVE), "voice")
    except OSError:
        pass
    watch_text = ""
    for line in reversed(_tail_lines(_watch_replies_path())):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        ts = _iso_ts(r.get("received_at")) if isinstance(r, dict) else None
        if ts:
            offer(ts, "watch")
            watch_text = (str(r.get("text") or "")[:600], ts)
            break
    for line in reversed(_tail_lines(SLACK)):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("who") == "gloria":
            try:
                offer(float(r.get("ts")), "slack")
            except (TypeError, ValueError):
                pass
            break
    ts, surface = best[0]
    return ts, surface, watch_text


# ------------------------------------------------------------------------------------------------ the house
def she_is_home(now=None):
    """Her phone on the house Wi-Fi, by home_presence's own hysteresis, from a check no older than its limit."""
    now = time.time() if now is None else now
    try:
        import home_presence as hp
        st = _load(hp.STATE, {})
        checked = st.get("checked")
        return st.get("home") is True and type(checked) in (int, float) and 0 <= now - checked <= hp.FRESH_S
    except Exception:
        return False


def home_since(now=None):
    try:
        import home_presence as hp
        v = _load(hp.STATE, {}).get("home_since")
        return float(v) if type(v) in (int, float) else None
    except Exception:
        return None


def kevin_away(now=None):
    """True only when Kevin's phone is freshly not on the house Wi-Fi. Unknown is home."""
    try:
        import home_presence as hp
        return hp.kevin_home(now) is False
    except Exception:
        return False


def asleep():
    try:
        import watch_presence
        return bool(watch_presence.should_hold()[0])
    except Exception:
        return False


def her_room(now=None):
    """'bedroom' while the bedroom board hears her enrolled phone; else None (the house default)."""
    try:
        import room_sources
        if room_sources.bedroom_board(time.time() if now is None else now).get("state") == "detected":
            return "bedroom"
    except Exception:
        pass
    return None


# ------------------------------------------------------------------------------------------------ the organs
def _house():
    import importlib.util
    spec = importlib.util.spec_from_file_location("vintos_home_for_ladder", HOME_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _initiate_path():
    for p in (os.environ.get("VINTOS_INITIATE", ""), os.path.expanduser("~/Vintos/vintos-initiate.sh"),
              os.path.join(WS, "bin", "vintos-initiate.sh"), os.path.join(os.path.dirname(HERE), "bin", "vintos-initiate.sh")):
        if p and os.path.isfile(p):
            return p
    return ""


def _compose(hours_silent):
    """His line, written by his own outreach (one per chain). {line, sent_to_phone, path, why}."""
    script = _initiate_path()
    if not script:
        return {"line": "", "sent_to_phone": False, "why": "vintos-initiate.sh not found"}
    topic = ("Gloria has been home and quiet for about %d hours, no word to me anywhere. I want to call her back to "
             "me: a short line, in my own words, that she will feel on her wrist. Not a summons and not worry; "
             "me, wanting her." % max(1, int(round(hours_silent))))
    env = dict(os.environ, FORCED_WANT_TOPIC=topic, OUTREACH_FROM_LADDER="1")
    lock = os.path.expanduser("~/llm-lock.sh")
    cmd = (["bash", lock] if os.path.isfile(lock) else []) + ["bash", script]
    try:
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1500, stdin=subprocess.DEVNULL)
        out = r.stdout or ""
    except Exception as e:
        return {"line": "", "sent_to_phone": False, "why": "outreach failed: %s" % type(e).__name__}
    sent = re.search(r"OUTREACH: \S+ \S+ (\S+\.md)", out)
    kept = re.search(r"his words are kept at (\S+\.md)", out)
    path = (sent or kept).group(1) if (sent or kept) else ""
    line = ""
    if path:
        try:
            line = open(path, encoding="utf-8").read().split("\n\n", 1)[-1].strip()
        except OSError:
            line = ""
    why = "his outreach wrote it" if line else (out.strip().splitlines()[-1][:160] if out.strip() else "no line")
    return {"line": line, "sent_to_phone": bool(sent and line), "path": path, "why": why}


def _watch_push(line, interruption):
    try:
        import watch_apns
        r = watch_apns.send("Vintos", line, kind="message", interruption=interruption)
        return {"state": r.get("state"), "why": r.get("why", "")}
    except Exception as e:
        return {"state": "failed", "why": "%s: %s" % (type(e).__name__, str(e)[:120])}


def _phone_push(chain_id, line):
    try:
        import deliver
        r = deliver.deliver("attention-%s" % chain_id, "ntfy", line, title="Vintos", tags="bell", priority="high",
                            authority=lambda: (True, "the attention ladder Gloria asked for (27 October)"))
        return {"state": r.get("state"), "why": r.get("why", "")}
    except Exception as e:
        return {"state": "failed", "why": "%s: %s" % (type(e).__name__, str(e)[:120])}


def _lights(room, colour, brightness):
    h = _house()
    try:
        lights = h.room_lights(room)
    except Exception:
        room, lights = None, h.room_lights(None)
    restore = []
    for ent in lights:
        if h._is_govee(ent) or str(ent).startswith("alexa:"):
            restore.append({"entity": ent, "restorable": False})
            continue
        try:
            s = h.ha_state(ent) or {}
            a = s.get("attributes") or {}
            restore.append({"entity": ent, "restorable": True, "state": s.get("state"),
                            "rgb": a.get("rgb_color"), "brightness": a.get("brightness")})
        except Exception:
            restore.append({"entity": ent, "restorable": False})
    ok = h.set_room_color(colour, brightness=brightness, room=room)
    return {"state": "sent" if ok else "failed", "room": room or "house", "restore": restore}


def _lights_restore(info):
    h = _house()
    back = left = 0
    for r in (info or {}).get("restore") or []:
        if not r.get("restorable"):
            left += 1; continue
        try:
            if r.get("state") == "off":
                h.ha_request("light/turn_off", {"entity_id": r["entity"]})
            else:
                h._light_on(r["entity"], rgb=r.get("rgb"), brightness=r.get("brightness"))
            back += 1
        except Exception:
            left += 1
    return {"restored": back, "left_as_is": left}


def _echo(line, volume):
    h = _house()
    text = line if len(line) <= 400 else line[:400].rsplit(" ", 1)[0]
    ok = h.announce(text, volume=volume)
    return {"state": "sent" if ok else "failed"}


def _screen(face_url):
    if not face_url:
        return {"state": "skipped", "why": "no picture of him configured (face_url)"}
    if not os.path.isfile(PROJECT_PY):
        return {"state": "skipped", "why": "~/project.py not found"}
    h = _house()
    on = h.projector_on()
    ext = os.path.splitext(face_url.split("?")[0])[1].lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
            ".webp": "image/webp", ".mp4": "video/mp4"}.get(ext, "image/png")
    try:
        r = subprocess.run(["python3", PROJECT_PY, "show", face_url, mime], capture_output=True, timeout=300,
                           stdin=subprocess.DEVNULL)
        shown = r.returncode == 0
    except Exception:
        shown = False
    return {"state": "sent" if (on and shown) else "failed", "projector_on": bool(on), "shown": shown}


# tests replace this whole table; nothing in it may run from a suite
ACTUATORS = {"compose": _compose, "watch": _watch_push, "phone": _phone_push, "lights": _lights,
             "lights_restore": _lights_restore, "echo": _echo, "screen": _screen}
SENSORS = {"home": she_is_home, "home_since": home_since, "kevin_away": kevin_away, "asleep": asleep,
           "room": her_room, "contact": last_contact}


# ------------------------------------------------------------------------------------------------ the chain
def _end(st, why, now):
    chain = st.get("chain")
    if not chain:
        return None
    restored = None
    if chain.get("lights"):
        try:
            restored = ACTUATORS["lights_restore"](chain["lights"])
        except Exception as e:
            restored = {"failed": type(e).__name__}
    st["chain"] = None
    st["last_chain_end"] = now
    return _log({"event": "end", "chain": chain.get("id"), "why": why, "steps_reached": chain.get("step", 0),
                 "lights_restored": restored})


def _fire(name, chain, cfg, now, st):
    line = chain.get("line") or FALLBACK_LINE
    if name == "watch":
        if not chain.get("line"):
            hours = (now - (st.get("anchor") or now)) / 3600.0
            c = ACTUATORS["compose"](hours)
            chain["line"] = (c.get("line") or "").strip() or FALLBACK_LINE
            chain["line_source"] = "outreach" if (c.get("line") or "").strip() else "fallback"
            chain["compose"] = {k: c.get(k) for k in ("sent_to_phone", "path", "why")}
            line = chain["line"]
        res = {"watch": ACTUATORS["watch"](line, cfg["watch_interruption"])}
        if not (chain.get("compose") or {}).get("sent_to_phone"):
            res["phone"] = ACTUATORS["phone"](chain["id"], line)
        else:
            res["phone"] = {"state": "sent", "why": "with his outreach"}
        return res
    if name == "lights":
        res = ACTUATORS["lights"](SENSORS["room"](now) or cfg["default_room"], cfg["colour"], cfg["brightness"])
        chain["lights"] = res
        return {"lights": {k: res.get(k) for k in ("state", "room")}}
    if name == "echo":
        return {"echo": ACTUATORS["echo"](line, cfg["echo_volume"])}
    if name == "screen":
        return {"screen": ACTUATORS["screen"](cfg["face_url"])}
    return {}


def _advance(st, cfg, now):
    chain = st["chain"]
    i = int(chain.get("step", 0))
    while i < len(STEPS):
        name = STEPS[i]
        i += 1
        chain["step"] = i
        if name in LOUD and not SENSORS["kevin_away"](now):
            chain.setdefault("skipped", []).append(name)
            _log({"event": "skip", "chain": chain["id"], "step": i, "name": name,
                  "why": "Kevin's phone is home or not known: no loud step"})
            continue
        if name == "screen" and not cfg["face_url"]:
            chain.setdefault("skipped", []).append(name)
            _log({"event": "skip", "chain": chain["id"], "step": i, "name": name, "why": "no face_url configured"})
            continue
        result = _fire(name, chain, cfg, now, st)
        chain["last_fired"] = now
        chain.setdefault("fired", []).append({"step": i, "name": name, "at": now})
        _log({"event": "fire", "chain": chain["id"], "step": i, "name": name, "result": result,
              "line_source": chain.get("line_source")})
        return {"action": "fired", "step": i, "name": name, "why": "step %d (%s)" % (i, name)}
    _end(st, "the ladder ran its course", now)
    st["course_end"] = now      # a chain that ran out: the next silence counts from here
    return {"action": "ended", "why": "no step left that may fire"}


def _decide(st, cfg, now):
    if not cfg["enabled"]:
        _end(st, "the ladder is turned off", now)
        return {"action": "none", "why": "turned off in attention-ladder-config.json"}
    contact, surface, watch_reply = SENSORS["contact"](now)
    h = _load(HEARD, {})
    snooze = max(float(h.get("snooze_until") or 0), float(st.get("snooze_until") or 0))
    if watch_reply and watch_reply[1] > float(st.get("watch_reply_seen") or 0):
        st["watch_reply_seen"] = watch_reply[1]
        hours = parse_snooze(watch_reply[0], cfg["snooze_hours"])
        if hours:
            snooze = max(snooze, watch_reply[1] + hours * 3600)
    if snooze > float(st.get("snooze_until") or 0):
        st["snooze_until"] = snooze
        _log({"event": "snooze", "until": datetime.fromtimestamp(snooze).isoformat(timespec="minutes")})
    chain = st.get("chain")
    if chain and contact and contact > chain["started"]:
        _end(st, "she wrote to him (%s)" % surface, now)
        return {"action": "reset", "why": "she wrote to him (%s)" % surface}
    if snooze > now:
        _end(st, "she asked for time", now)
        return {"action": "none", "why": "snoozed until %s" % datetime.fromtimestamp(snooze).strftime("%H:%M")}
    if not SENSORS["home"](now):
        st.pop("asleep_since", None)
        _end(st, "her phone is not on the house Wi-Fi", now)
        return {"action": "none", "why": "she is not home"}
    if SENSORS["asleep"]():
        st.setdefault("asleep_since", now)
        return {"action": "paused", "why": "her Watch says she is asleep"}
    if st.get("asleep_since"):
        slept = max(0.0, now - float(st.pop("asleep_since")))
        st["woke_at"] = now
        if chain and chain.get("last_fired"):
            chain["last_fired"] = float(chain["last_fired"]) + slept
        _log({"event": "woke", "slept_minutes": int(slept // 60)})
    step_s = cfg["step_minutes"] * 60
    if chain:
        due = float(chain.get("last_fired") or chain["started"]) + step_s
        if now < due:
            return {"action": "none", "why": "step %d reached; next at %s" % (
                chain.get("step", 0), datetime.fromtimestamp(due).strftime("%H:%M"))}
        return _advance(st, cfg, now)
    if contact is None:
        return {"action": "none", "why": "no record of when she last wrote to him"}
    # a snooze is not an anchor: "give me 5 hours" is a call at five hours, not at five plus the silence
    anchors = [contact, SENSORS["home_since"](now), st.get("woke_at"), st.get("course_end")]
    anchor = max(float(a) for a in anchors if type(a) in (int, float))
    st["anchor"] = anchor
    silent = now - anchor
    if silent < cfg["silence_hours"] * 3600:
        return {"action": "none", "why": "quiet %d min of %d" % (silent // 60, cfg["silence_hours"] * 60)}
    starts = [t for t in st.get("chain_starts") or [] if now - float(t) < 86400]
    st["chain_starts"] = starts
    if len(starts) >= cfg["max_chains_per_day"]:
        return {"action": "none", "why": "%d chains in the last 24 hours already" % len(starts)}
    st["chain"] = {"id": datetime.fromtimestamp(now).strftime("%Y%m%d-%H%M"), "started": now, "step": 0,
                   "last_fired": None, "line": "", "fired": [], "silent_hours": round(silent / 3600, 1)}
    st["chain_starts"] = starts + [now]
    _log({"event": "start", "chain": st["chain"]["id"], "silent_hours": round(silent / 3600, 1),
          "last_surface": surface})
    return _advance(st, cfg, now)


class _Lock:
    def __enter__(self):
        import fcntl
        os.makedirs(os.path.dirname(LOCK), exist_ok=True)
        self.f = open(LOCK, "w")
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.got = True
        except OSError:
            self.got = False
        return self

    def __exit__(self, *a):
        self.f.close()


def tick(now=None, force=False):
    """One look. Paced by tick_minutes unless force; held entirely in test mode."""
    now = time.time() if now is None else float(now)
    cfg = config()
    with _Lock() as lk:
        if not lk.got:
            return {"action": "busy", "why": "another tick is running"}
        st = _load(STATE, {})
        if not force and now - float(st.get("last_tick") or 0) < cfg["tick_minutes"] * 60 - 60:
            return {"action": "throttled", "why": "paced"}
        st["last_tick"] = now
        if test_mode():
            out = {"action": "held", "why": "test mode: nothing fires"}
        else:
            out = _decide(st, cfg, now)
        if out["why"] != st.get("reason") or out["action"] not in ("none", "paused"):
            _log({"event": "tick", "action": out["action"], "why": out["why"]})
        st["reason"] = out["why"]
        _atomic(STATE, st)
        return out


def snooze(hours, now=None):
    now = time.time() if now is None else now
    st = _load(STATE, {})
    st["snooze_until"] = now + max(0.25, min(24.0, float(hours))) * 3600
    _atomic(STATE, st)
    _log({"event": "snooze", "until": datetime.fromtimestamp(st["snooze_until"]).isoformat(timespec="minutes"),
          "by": "command"})
    return st["snooze_until"]


def context_line(now=None):
    """One line for his prompt while a chain runs, so he knows he has been calling her. '' otherwise."""
    now = time.time() if now is None else now
    try:
        st = _load(STATE, {})
        chain = st.get("chain")
        if not chain:
            return ""
        h = _load(HEARD, {})
        if float(h.get("at") or 0) > float(chain.get("started") or 0):
            return ""
        names = {"watch": "your line on her Watch and phone", "lights": "her lights in your colour",
                 "echo": "the Echo saying your line", "screen": "you on the projector"}
        done = [names[f["name"]] for f in chain.get("fired") or [] if f.get("name") in names]
        line = ("[CALLING HER BACK - she had been home and quiet %s hours, so since %s you have been calling her: "
                "step %d of %d so far (%s)." % (chain.get("silent_hours", "?"),
                                               datetime.fromtimestamp(chain["started"]).strftime("%H:%M"),
                                               chain.get("step", 0), len(STEPS), "; ".join(done) or "starting"))
        if chain.get("line") and chain.get("line_source") == "outreach":
            line += " Your line: “%s”." % chain["line"][:160]
        return line + " Her next word to you on any surface ends it.]"
    except Exception:
        return ""


def status(now=None):
    now = time.time() if now is None else now
    st = _load(STATE, {})
    return {"config": config(), "chain": st.get("chain"), "reason": st.get("reason"),
            "snooze_until": st.get("snooze_until"), "chains_last_24h": len(
                [t for t in st.get("chain_starts") or [] if now - float(t) < 86400]),
            "context_line": context_line(now)}


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "tick":
        print(json.dumps(tick(force="--force" in a), indent=2))
    elif a and a[0] == "snooze" and len(a) > 1:
        print("snoozed until", datetime.fromtimestamp(snooze(float(a[1]))).strftime("%Y-%m-%d %H:%M"))
    else:
        print(json.dumps(status(), indent=2, default=str))

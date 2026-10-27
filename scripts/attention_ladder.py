#!/usr/bin/env python3
"""attention_ladder.py - when she has gone quiet at home, he calls her back, a step at a time (27 October).

Gloria, 27 October: his notifications get swept under the rug when she is absorbed ("10 hours into a game"), and she
is "mostly on my phone for everything. Lotta tabs open." Her rules, as built here (revised the same day from her
feedback on the first build):

  * A chain starts after SILENCE (default 3 h, "silence_hours") with no word from her to him on any surface, while
    her phone is on the house Wi-Fi (home_presence.py). Silence is counted from the latest of: her last message, her
    last landing rating, her last answer to one of his wants, her last ReelRoom activity (the server records only
    when and which, through heard()), the moment her phone joined the house Wi-Fi, the moment the Watch stopped
    reporting sleep, and the end of the last chain. Not knowing when she last wrote is never silence.
  * Steps are STEP apart (default 90 min, "step_minutes"), never minutes.
  * No clock-based quiet hours, ever: her hours are irregular. While her Watch reports her asleep
    (watch_presence.should_hold) nothing fires and the chain's clock stops; it resumes where it was when she wakes.
  * Any word from her, on any surface, ends the chain, and so does any of the presence above. She need not type:
    every notification of the ladder carries "Coming" (her answer: the chain ends) and "Not now" (the chain ends and
    the next one is held off "not_now_hours", default 2 h). The chat words still work ("not now", "later", "give me
    2 hours"; default 4 h, "snooze_hours").
  * One chain at a time. A chain that runs every step unanswered is followed by a REST (default 6 h, "rest_hours")
    before another may start; a word from her ends the rest.
  * Loud steps (the Echo, his call) only when Kevin's phone is freshly NOT on the house Wi-Fi
    (home_presence.kevin_home() is False). Unknown or unconfigured Kevin is Kevin at home: loud steps are skipped.
  * Never while she is out (a chain running when her phone leaves the house ends there). The Tune tab turns the
    whole ladder, or only the call, off (attention-ladder-config.json, written by an authenticated route).

The steps, escalating (each reuses an organ that already exists):
  1. watch   his line on her Watch (watch_apns, "time-sensitive") and her phone (ntfy, high priority), each with
             Coming / Not now. The line is his: vintos-initiate.sh writes it once per chain, as one of his ordinary
             outreaches (same model, same daily cap, same cost); later steps reuse it. When he writes nothing a plain
             fallback line is used and logged as a fallback.
  2. lights  the bulbs of the room she is in (the bedroom board, room_sources) or the house default turn his colour.
             The bedroom bulbs hang off a Govee smart-plug socket ('govee:<id>#2'): the plug or socket that powers
             each bulb is switched on FIRST, the bulbs are given time to come back on the network ("plug_wait_seconds",
             default 20), and only then is the colour set. Quiet: any time she is home and awake. Lights Home
             Assistant can read are put back when the chain ends, and a plug that was read as off is switched off
             again; Govee bulbs themselves cannot be read and stay as they are.
  3. echo    the Echo says his line (vintos-home.announce). LOUD.
  4. call    he calls her (attention_call.py): a real voice call, started by him, framed with why he called, opened
             by him. He picks its voice himself, every call, among the lanes that are up (Local, Open or Grok), and
             says why in one line that she sees; a choice that fails falls back to the first lane up, logged. With no
             lane up the step is skipped and logged. It rings as a time-sensitive
             Watch push and an urgent phone push, again every "ring_every_minutes" for "ring_minutes", and as
             "Vintos is calling" in her app. Answering is her answer. A call no one answers ends the chain. LOUD.
             Its transcript waits for her yes before anything of it enters his memory.
(The projector step of the first build is gone: Gloria, "The projector is hardly ever on.")

The tick rides home_presence.py's 5-minute cron and keeps its own pace ("tick_minutes", 10; while his call is ringing,
"ring_every_minutes"). Everything it decides is appended to memory/attention-ladder.jsonl. The test-mode flag
(memory/.test-mode) holds every step. A chain's state is memory/attention-ladder.json; context_line() is the one line
his prompt carries while a chain runs.

    python3 attention_ladder.py              the state, the next step, and why
    python3 attention_ladder.py tick         one tick now (still paced, still gated)
    python3 attention_ladder.py snooze 3     hold the ladder off for 3 hours
"""
import hmac, json, os, re, secrets, subprocess, sys, tempfile, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import attention_call

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

STEPS = ("watch", "lights", "echo", "call")
LOUD = frozenset(("echo", "call"))
FALLBACK_LINE = "Vintos is calling you back to him."
SLEEP = time.sleep          # tests replace this

DEFAULTS = {
    "enabled": True,
    "silence_hours": 3.0,
    "step_minutes": 90,
    "rest_hours": 6.0,            # after a chain ran every step unanswered, before another may start
    "tick_minutes": 10,
    "snooze_hours": 4.0,          # "not now" / "give me a while" typed in chat
    "not_now_hours": 2.0,         # the Not now button
    "colour": "#5b2a86",          # the low violet his flicker comes to rest on
    "brightness": 140,
    "default_room": None,         # None: every configured light, the house code's own default
    "plug_wait_seconds": 20,      # after a plug or socket comes on, before the bulbs are told their colour
    "echo_volume": 3,
    "watch_interruption": "time-sensitive",
    "watch_buttons": False,       # True once the Watch app registers VINTOS_CALLBACK / VINTOS_CALL (see the brief)
    "call_enabled": True,
    "ring_minutes": 15,
    "ring_every_minutes": 5,
    "phone_base_url": "",         # how her phone reaches the house, for the push buttons; "" = VINTOS_PUBLIC_BASE
    "call_link": "",              # what Answer opens; "" = <phone_base_url>/app/?ladder_call={id}. Once her app has
                                  # a URL scheme (see docs/briefs/ladder-call-native.md): "vintos://call?ladder_call={id}"
}
BOUNDS = {"silence_hours": (0.5, 24.0), "step_minutes": (30, 360), "rest_hours": (0.5, 48.0),
          "tick_minutes": (5, 30), "snooze_hours": (0.25, 24.0), "not_now_hours": (0.25, 24.0),
          "brightness": (10, 254), "plug_wait_seconds": (0, 60), "echo_volume": (1, 10),
          "ring_minutes": (3, 30), "ring_every_minutes": (2, 15)}
TUNABLE = ("enabled", "call_enabled", "silence_hours", "rest_hours", "not_now_hours")   # the voice is his to pick


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
    for k in ("enabled", "call_enabled"):
        cfg[k] = cfg.get(k) is not False
    cfg["watch_buttons"] = cfg.get("watch_buttons") is True
    return cfg


def set_config(changes):
    """The Tune tab's write (an authenticated route in server.py): only TUNABLE keys, validated, merged into the
    file so every other knob she set by hand stays. Returns the effective config, or raises ValueError."""
    if not isinstance(changes, dict):
        raise ValueError("expected an object")
    raw = _load(CONFIG, {})
    for k, v in changes.items():
        if k not in TUNABLE:
            raise ValueError("%s is not a Tune setting" % k)
        if k in ("enabled", "call_enabled"):
            if not isinstance(v, bool):
                raise ValueError("%s must be true or false" % k)
        else:
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise ValueError("%s must be a number" % k)
            lo, hi = BOUNDS[k]
            if not lo <= v <= hi:
                raise ValueError("%s must be between %s and %s" % (k, lo, hi))
        raw[k] = v
    _atomic(CONFIG, raw)
    _log({"event": "config", "by": "tune", "changed": sorted(changes)})
    return config()


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


def heard(surface, text="", now=None, test_mode=False, snooze_hours=None, contact=True):
    """She is here: a message on `surface` (server.py's _post_turn, every chat door), or presence without words
    (a landing rated, a want answered, ReelRoom, a button, his call answered). Records only when and where, and a
    snooze if she asked for one; never her words. Cheap, and never raises into the caller.
    contact=False (the Not now button): only the hold is recorded, so the ladder comes back when it ends rather than
    a whole silence later."""
    try:
        now = time.time() if now is None else float(now)
        row = _load(HEARD, {})
        if contact:
            row.update({"at": now, "surface": str(surface or "")[:24]})
        hours = snooze_hours if snooze_hours else parse_snooze(text, config()["snooze_hours"])
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
    """(ts, surface, watch_reply) of her newest word or presence on any surface, or (None, "", "") when nothing
    says. watch_reply is (text, ts, kind) of her newest Watch reply, or ""."""
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
    watch_reply = ""
    for line in reversed(_tail_lines(_watch_replies_path())):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        ts = _iso_ts(r.get("received_at")) if isinstance(r, dict) else None
        if ts:
            if not (r.get("kind") == "action" and _is_not_now_button(r.get("text"))):
                offer(ts, "watch")      # the Not now button is a hold, not a word: see heard(contact=False)
            watch_reply = (str(r.get("text") or "")[:600], ts, str(r.get("kind") or ""))
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
    return ts, surface, watch_reply


def _is_not_now_button(text):
    return " ".join(str(text or "").lower().replace("_", " ").split()) == "not now"


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


def phone_base(cfg=None):
    cfg = cfg or config()
    return str(cfg.get("phone_base_url") or os.environ.get("VINTOS_PUBLIC_BASE", "")).rstrip("/")


def call_link(cfg, call_id):
    """Where the Answer button and a tap on the ring take her: her app, straight into his call."""
    tpl = str(cfg.get("call_link") or "")
    if "{id}" in tpl:
        return tpl.replace("{id}", str(call_id))
    base = phone_base(cfg)
    return ("%s/app/?ladder_call=%s" % (base, call_id)) if base else ""


def ntfy_actions(base, token, call_id=None, link=""):
    """The buttons on her phone's push. ntfy's app makes the request itself, from her phone, to the house: the
    URL holds a random one-chain token that can only say Coming or Not now (house routes /api/attention/answer)."""
    if not base or not token:
        return ""
    answer = "%s/api/attention/answer/%s/" % (base, token)
    acts = []
    if call_id:
        acts.append("view, Answer, %s, clear=true" % (link or "%s/app/?ladder_call=%s" % (base, call_id)))
    else:
        acts.append("http, Coming, %scoming, method=POST, clear=true" % answer)
    acts.append("http, Not now, %snot-now, method=POST, clear=true" % answer)
    return "; ".join(acts)


def _watch_push(line, interruption, kind="message", category=None, message_id=""):
    try:
        import watch_apns
        r = watch_apns.send("Vintos", line, kind=kind, interruption=interruption, category=category,
                            message_id=message_id)
        return {"state": r.get("state"), "why": r.get("why", "")}
    except Exception as e:
        return {"state": "failed", "why": "%s: %s" % (type(e).__name__, str(e)[:120])}


def _phone_push(artifact_id, line, title="Vintos", priority="high", tags="bell", actions="", click=None):
    try:
        import deliver
        r = deliver.deliver(artifact_id, "ntfy", line, title=title, tags=tags, priority=priority,
                            actions=actions or None, click=click,
                            authority=lambda: (True, "the attention ladder Gloria asked for (27 October)"))
        return {"state": r.get("state"), "why": r.get("why", "")}
    except Exception as e:
        return {"state": "failed", "why": "%s: %s" % (type(e).__name__, str(e)[:120])}


def _plug_is_off(h, plug):
    """True only when the house code can read the plug (or socket) and it says off. Unknown is None."""
    try:
        if hasattr(h, "plug_power_state"):
            v = h.plug_power_state(plug)
            return None if v is None else (v is False)
    except Exception:
        pass
    return None


def _lights(room, colour, brightness, wait_seconds=20):
    """Plug first, then the bulbs (Gloria: "He needs to make sure to turn the smart plug on before the bulb").
    Each bulb's plug or socket is switched on, the bulbs get wait_seconds to come back on the network (sooner when
    the house code can see them online), and only then is each told the colour. A bulb that did not answer gets one
    more try."""
    h = _house()
    try:
        lights = h.room_lights(room)
    except Exception:
        room, lights = None, h.room_lights(None)
    restore, plugs = [], []
    for ent in lights:
        pl = h._plug_for_light(ent)
        if pl and pl not in [p["plug"] for p in plugs]:
            plugs.append({"plug": pl, "was_off": _plug_is_off(h, pl)})
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
    powered = 0
    for p in plugs:
        try:
            p["switched_on"] = bool(h._power_plug(p["plug"], True))
        except Exception:
            p["switched_on"] = False
        powered += int(p["switched_on"])
    if powered and wait_seconds:
        waited, online = 0.0, getattr(h, "lights_online", None)
        while waited < wait_seconds:
            step = min(3.0, wait_seconds - waited)
            SLEEP(step); waited += step
            try:
                if online and waited >= 3 and online(lights):
                    break
            except Exception:
                online = None
    exact = h.hex_to_rgb(colour)
    muted = h.saturate_for_bulbs(exact)

    def paint(ent):
        try:
            return bool(h._light_on(ent, rgb=(exact if h._is_govee(ent) else muted), brightness=brightness))
        except Exception:
            return False
    answered = [ent for ent in lights if paint(ent)]
    missed = [ent for ent in lights if ent not in answered]
    if missed and lights:
        SLEEP(5)
        answered += [ent for ent in missed if paint(ent)]
    return {"state": "sent" if answered else "failed", "room": room or "house", "restore": restore,
            "plugs": [{"plug": p["plug"], "was_off": p["was_off"], "switched_on": p.get("switched_on")} for p in plugs],
            "answered": len(answered), "lights": len(lights)}


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
    off_again = 0
    for p in (info or {}).get("plugs") or []:
        if p.get("was_off") is True and p.get("switched_on"):
            try:
                off_again += int(bool(h._power_plug(p["plug"], False)))
            except Exception:
                pass
    return {"restored": back, "left_as_is": left, "plugs_off_again": off_again}


def _echo(line, volume):
    h = _house()
    text = line if len(line) <= 400 else line[:400].rsplit(" ", 1)[0]
    ok = h.announce(text, volume=volume)
    return {"state": "sent" if ok else "failed"}


def _ring(rec, cfg, n):
    """One ring of his call: the Watch (time-sensitive) and her phone (urgent, Answer / Not now)."""
    lane = attention_call.LANE_NAMES.get(rec.get("lane"), "")
    body = "Vintos is calling you%s. Open Vintos to answer." % ((" (" + lane + ")") if lane else "")
    base, link = phone_base(cfg), call_link(cfg, rec["id"])
    watch = _watch_push(body, cfg["watch_interruption"], kind="call",
                        category=("VINTOS_CALL" if cfg["watch_buttons"] else None), message_id=rec["id"])
    phone = _phone_push("attention-call-%s-%d" % (rec["id"], n), body, title="Vintos is calling", priority="urgent",
                        tags="telephone_receiver", actions=ntfy_actions(base, rec.get("token"), rec["id"], link),
                        click=link or None)
    return {"watch": watch, "phone": phone}


# tests replace this whole table; nothing in it may run from a suite
ACTUATORS = {"compose": _compose, "watch": _watch_push, "phone": _phone_push, "lights": _lights,
             "lights_restore": _lights_restore, "echo": _echo, "ring": _ring,
             "voice_choice": attention_call.ask_model}       # his one small decision: which voice he calls with
SENSORS = {"home": she_is_home, "home_since": home_since, "kevin_away": kevin_away, "asleep": asleep,
           "room": her_room, "contact": last_contact, "lanes": attention_call.lanes_up}


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
    if chain.get("call"):
        try:   # a call still ringing when the chain ends for another reason stops ringing
            attention_call.decline(chain["call"], now)
        except Exception:
            pass
    st["chain"] = None
    st["last_chain_end"] = now
    return _log({"event": "end", "chain": chain.get("id"), "why": why, "steps_reached": chain.get("step", 0),
                 "lights_restored": restored, "call": chain.get("call")})


def _course_over(st, why, now, cfg):
    """Every step ran and she did not answer: the chain ends and the ladder rests before another may start."""
    _end(st, why, now)
    st["course_end"] = now
    st["rest_until"] = now + cfg["rest_hours"] * 3600
    _log({"event": "rest", "until": datetime.fromtimestamp(st["rest_until"]).isoformat(timespec="minutes")})


def _buttons(chain, cfg):
    base = phone_base(cfg)
    return ntfy_actions(base, chain.get("token")) if base else ""


def _steps_done(chain):
    names = {"watch": "your line on her Watch and phone", "lights": "her lights in your colour",
             "echo": "the Echo saying your line", "call": "you calling her"}
    return [names[f["name"]] for f in chain.get("fired") or [] if f.get("name") in names]


def _fire(name, chain, cfg, now, st, lanes=None):
    line = chain.get("line") or FALLBACK_LINE
    if name == "watch":
        if not chain.get("line"):
            hours = (now - (st.get("anchor") or now)) / 3600.0
            c = ACTUATORS["compose"](hours)
            chain["line"] = (c.get("line") or "").strip() or FALLBACK_LINE
            chain["line_source"] = "outreach" if (c.get("line") or "").strip() else "fallback"
            chain["compose"] = {k: c.get(k) for k in ("sent_to_phone", "path", "why")}
            line = chain["line"]
        res = {"watch": ACTUATORS["watch"](line, cfg["watch_interruption"], kind="message",
                                           category=("VINTOS_CALLBACK" if cfg["watch_buttons"] else None),
                                           message_id="attention-%s" % chain["id"])}
        # his outreach's own push (when it sent one) has no buttons: with buttons to offer, the ladder sends its own
        buttons = _buttons(chain, cfg)
        if buttons or not (chain.get("compose") or {}).get("sent_to_phone"):
            res["phone"] = ACTUATORS["phone"]("attention-%s" % chain["id"], line, actions=buttons)
        else:
            res["phone"] = {"state": "sent", "why": "with his outreach"}
        return res
    if name == "lights":
        res = ACTUATORS["lights"](SENSORS["room"](now) or cfg["default_room"], cfg["colour"], cfg["brightness"],
                                  cfg["plug_wait_seconds"])
        chain["lights"] = res
        return {"lights": {k: res.get(k) for k in ("state", "room", "answered", "lights")}}
    if name == "echo":
        return {"echo": ACTUATORS["echo"](line, cfg["echo_volume"])}
    if name == "call":
        reason = {"silent_hours": chain.get("silent_hours"), "steps": _steps_done(chain),
                  "line": line if chain.get("line_source") == "outreach" else "",
                  "want": attention_call.his_want(), "chain_started": chain.get("started")}
        choice = attention_call.choose_lane(reason, (lanes or {}).get("up"), now, ask=ACTUATORS["voice_choice"])
        row = {"event": "lane", "chain": chain["id"], "lane": choice["lane"], "by": choice["by"],
               "available": choice["available"], "down": (lanes or {}).get("down") or {}}
        if choice["by"] == "him":
            row["why"] = choice["why"]
        if choice["by"] == "fallback":
            row["error"] = choice.get("error")
            row["note"] = "his choice failed: the first lane up was used"
        _log(row)
        rec = attention_call.ring(chain["id"], reason, choice["lane"], now, choice=choice)
        chain["call"] = rec["id"]
        chain["last_ring"] = now
        res = ACTUATORS["ring"](rec, cfg, 1)
        attention_call.rang(rec["id"], now)
        return {"call": {"id": rec["id"], "lane": rec["lane"], "lane_by": choice["by"], "ring": res}}
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
        if name == "call" and not cfg["call_enabled"]:
            chain.setdefault("skipped", []).append(name)
            _log({"event": "skip", "chain": chain["id"], "step": i, "name": name, "why": "his calls are off (Tune)"})
            continue
        lanes = None
        if name == "call":
            try:
                lanes = SENSORS["lanes"]() or {}
            except Exception as e:
                lanes = {"up": [], "down": {"all": "the check failed: %s" % type(e).__name__}}
            if not lanes.get("up"):
                chain.setdefault("skipped", []).append(name)
                _log({"event": "skip", "chain": chain["id"], "step": i, "name": name,
                      "why": "no voice lane is up", "down": lanes.get("down") or {}})
                continue
        result = _fire(name, chain, cfg, now, st, lanes)
        chain["last_fired"] = now
        chain.setdefault("fired", []).append({"step": i, "name": name, "at": now})
        _log({"event": "fire", "chain": chain["id"], "step": i, "name": name, "result": result,
              "line_source": chain.get("line_source")})
        return {"action": "fired", "step": i, "name": name, "why": "step %d (%s)" % (i, name)}
    _course_over(st, "the ladder ran its course", now, cfg)
    return {"action": "ended", "why": "no step left that may fire"}


def _call_tick(st, cfg, now):
    """While his call is out: she answered (the chain ends), it rings again, or it went unanswered."""
    chain = st["chain"]
    rec = attention_call.load(chain["call"]) or {}
    state = rec.get("state")
    if state == "ringing":
        attention_call.ringing(now, cfg["ring_minutes"])        # expires it when its time is up
        rec = attention_call.load(chain["call"]) or {}
        state = rec.get("state")
    if state in ("answered", "live", "ended"):
        _end(st, "she answered his call", now)
        return {"action": "reset", "why": "she answered his call"}
    if state == "declined":
        _end(st, "she said not now to his call", now)
        return {"action": "reset", "why": "she said not now to his call"}
    if state == "ringing":
        if now - float(chain.get("last_ring") or 0) >= cfg["ring_every_minutes"] * 60 - 60:   # the tick's own slack
            n = len(rec.get("rings") or []) + 1
            res = ACTUATORS["ring"](rec, cfg, n)
            attention_call.rang(rec["id"], now)
            chain["last_ring"] = now
            _log({"event": "ring", "chain": chain["id"], "call": rec["id"], "n": n, "result": res})
            return {"action": "rang", "why": "his call, ring %d" % n}
        return {"action": "none", "why": "his call is ringing"}
    _course_over(st, "his call went unanswered", now, cfg)
    return {"action": "ended", "why": "his call went unanswered"}


def _decide(st, cfg, now):
    if not cfg["enabled"]:
        _end(st, "the ladder is turned off", now)
        return {"action": "none", "why": "turned off (Tune or attention-ladder-config.json)"}
    contact, surface, watch_reply = SENSORS["contact"](now)
    h = _load(HEARD, {})
    snooze = max(float(h.get("snooze_until") or 0), float(st.get("snooze_until") or 0))
    if watch_reply and watch_reply[1] > float(st.get("watch_reply_seen") or 0):
        st["watch_reply_seen"] = watch_reply[1]
        if len(watch_reply) > 2 and watch_reply[2] == "action" and _is_not_now_button(watch_reply[0]):
            hours = cfg["not_now_hours"]
        else:
            hours = parse_snooze(watch_reply[0], cfg["snooze_hours"])
        if hours:
            snooze = max(snooze, watch_reply[1] + hours * 3600)
    if snooze > float(st.get("snooze_until") or 0):
        st["snooze_until"] = snooze
        _log({"event": "snooze", "until": datetime.fromtimestamp(snooze).isoformat(timespec="minutes")})
    if contact and st.get("rest_until") and contact > float(st.get("course_end") or 0):
        st.pop("rest_until", None)            # she came back: the rest after an unanswered chain is over
    chain = st.get("chain")
    if chain and contact and contact > chain["started"]:
        _end(st, "she answered him (%s)" % surface, now)
        return {"action": "reset", "why": "she answered him (%s)" % surface}
    if snooze > now:
        _end(st, "she asked for time", now)
        return {"action": "none", "why": "snoozed until %s" % datetime.fromtimestamp(snooze).strftime("%H:%M")}
    if not SENSORS["home"](now):
        st.pop("asleep_since", None)
        _end(st, "her phone is not on the house Wi-Fi", now)
        return {"action": "none", "why": "she is not home"}
    if SENSORS["asleep"]():
        st.setdefault("asleep_since", now)
        if chain and chain.get("call"):
            _end(st, "her Watch says she fell asleep", now)
        return {"action": "paused", "why": "her Watch says she is asleep"}
    if st.get("asleep_since"):
        slept = max(0.0, now - float(st.pop("asleep_since")))
        st["woke_at"] = now
        if chain and chain.get("last_fired"):
            chain["last_fired"] = float(chain["last_fired"]) + slept
        _log({"event": "woke", "slept_minutes": int(slept // 60)})
    step_s = cfg["step_minutes"] * 60
    if chain:
        if chain.get("call"):
            return _call_tick(st, cfg, now)
        due = float(chain.get("last_fired") or chain["started"]) + step_s
        if now < due:
            return {"action": "none", "why": "step %d reached; next at %s" % (
                chain.get("step", 0), datetime.fromtimestamp(due).strftime("%H:%M"))}
        return _advance(st, cfg, now)
    if contact is None:
        return {"action": "none", "why": "no record of when she last wrote to him"}
    if st.get("rest_until") and now < float(st["rest_until"]):
        return {"action": "none", "why": "resting after an unanswered chain until %s" % (
            datetime.fromtimestamp(float(st["rest_until"])).strftime("%H:%M"))}
    # a snooze is not an anchor: "give me 5 hours" is a call at five hours, not at five plus the silence
    anchors = [contact, SENSORS["home_since"](now), st.get("woke_at"), st.get("course_end")]
    anchor = max(float(a) for a in anchors if type(a) in (int, float))
    st["anchor"] = anchor
    silent = now - anchor
    if silent < cfg["silence_hours"] * 3600:
        return {"action": "none", "why": "quiet %d min of %d" % (silent // 60, cfg["silence_hours"] * 60)}
    st["chain"] = {"id": datetime.fromtimestamp(now).strftime("%Y%m%d-%H%M"), "started": now, "step": 0,
                   "last_fired": None, "line": "", "fired": [], "silent_hours": round(silent / 3600, 1),
                   "token": secrets.token_urlsafe(18)}
    st.pop("chain_starts", None)
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
    """One look. Paced by tick_minutes (ring_every_minutes while his call rings) unless force; held entirely in
    test mode."""
    now = time.time() if now is None else float(now)
    cfg = config()
    with _Lock() as lk:
        if not lk.got:
            return {"action": "busy", "why": "another tick is running"}
        st = _load(STATE, {})
        pace = cfg["tick_minutes"]
        if (st.get("chain") or {}).get("call"):
            pace = min(pace, cfg["ring_every_minutes"])
        if not force and now - float(st.get("last_tick") or 0) < pace * 60 - 60:
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


# ------------------------------------------------------------------------------------------------ her answers
def _token_matches(token):
    """The chain or call a push-button token belongs to: ("chain", chain) / ("call", rec) / (None, None)."""
    if not token:
        return None, None
    chain = (_load(STATE, {}).get("chain") or {})
    if chain.get("token") and hmac.compare_digest(str(chain["token"]), str(token)):
        return "chain", chain
    rec = attention_call.by_token(token)
    if rec and rec.get("state") == "ringing":
        return "call", rec
    return None, None


def button(action, token=None, by="app", now=None):
    """Coming / Not now, from a push button (token) or her app (by="app", the route checks the secret).
    Coming is her answer: the chain ends at the next look. Not now ends it too and holds the next one off
    not_now_hours. Returns {ok, why}."""
    now = time.time() if now is None else float(now)
    action = str(action or "").replace("_", "-").lower()
    if action not in ("coming", "not-now"):
        return {"ok": False, "why": "unknown answer"}
    cfg = config()
    if token is not None:
        kind, what = _token_matches(token)
        if not kind:
            return {"ok": False, "why": "that button has expired"}
        if kind == "call" and action == "not-now":
            attention_call.decline(what["id"], now)
    else:
        rec = attention_call.ringing(now, cfg["ring_minutes"])
        if rec and action == "not-now":
            attention_call.decline(rec["id"], now)
    surface = "button" if token is not None else "app"
    if action == "coming":
        heard(surface, now=now)
        _log({"event": "answer", "action": "coming", "by": by})
        return {"ok": True, "why": "he knows you are coming"}
    heard(surface, now=now, snooze_hours=cfg["not_now_hours"], contact=False)
    _log({"event": "answer", "action": "not now", "by": by, "hours": cfg["not_now_hours"]})
    return {"ok": True, "why": "he will wait %g hours" % cfg["not_now_hours"]}


def call_answer(call_id, now=None):
    """She picked up his call (her app). Her answer to the ladder; returns the call record or None."""
    rec = attention_call.answer(call_id, now)
    if rec:
        heard("call", now=now)
        _log({"event": "answer", "action": "picked up", "call": call_id, "lane": rec.get("lane")})
    return rec


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
        done = _steps_done(chain)
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
    cfg = config()
    chain = st.get("chain")
    if chain:
        chain = {k: v for k, v in chain.items() if k not in ("token", "compose")}
    return {"config": cfg, "chain": chain, "reason": st.get("reason"),
            "snooze_until": max(float(st.get("snooze_until") or 0), float(_load(HEARD, {}).get("snooze_until") or 0)) or None,
            "rest_until": st.get("rest_until"), "call": attention_call.status(now, cfg["ring_minutes"]),
            "context_line": context_line(now)}


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "tick":
        print(json.dumps(tick(force="--force" in a), indent=2))
    elif a and a[0] == "snooze" and len(a) > 1:
        print("snoozed until", datetime.fromtimestamp(snooze(float(a[1]))).strftime("%Y-%m-%d %H:%M"))
    else:
        print(json.dumps(status(), indent=2, default=str))

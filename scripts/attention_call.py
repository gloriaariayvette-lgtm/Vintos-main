#!/usr/bin/env python3
"""attention_call.py - the last step of the attention ladder: he calls her (27 October).

Gloria, on the ladder: the call is "the only part that would have actually worked or meant anything".

A call he starts is an ordinary voice call of his - the same lanes (Local, Open, Grok), the same full instructions
from /api/voice/token, the same per-turn framing, the same ledger route and session end - with four differences:

  * HIS VOICE. He chooses the lane himself, every call (Gloria, 27 October: "HE should pick the voice"). Just before
    it rings, lanes_up() asks which lanes are up the way a call finds out (Open and Grok: their key, and paid calls
    not paused; Local: the Mac stage answering), and choose_lane() asks his outreach model once, with why he is
    calling, how long she has been quiet and the time, which of those voices he calls her with and why, in one line.
    The choice and the line ride with the call and she sees them on the ring and beside the transcript. A failed
    or unusable answer falls back to the first lane that is up (FALLBACK_ORDER), and says so.
  * WHY. His instructions carry a "you called her because..." block (framing()): how long she had been quiet, what
    he has been doing to reach her, his own line, the want that is most alive in him. He speaks first: the app asks
    the lane for his opening before she has said anything (opening_instruction()).
  * RINGING. Her app has no CallKit or PushKit (vintos-app is a Capacitor shell with no push of its own), so it
    cannot ring like a phone. The ring is: a time-sensitive Watch push "Vintos is calling", an urgent ntfy push with
    Answer / Not now, repeated every few minutes for a bounded time, and the app itself showing "Vintos is calling"
    the moment it is open or comes to the front (it polls GET /api/attention/call). docs/briefs/ladder-call-native.md
    says exactly what the native app needs for a true incoming-call ring.
  * HELD. Nothing of a call he started enters his memory until she says so. Its turns are held here, privately;
    after the call she sees the transcript and answers "save this call to his memory?". Yes replays the held turns
    through the very ledger route and session end every call uses (server.py), so it lands exactly as a call does
    today. It counts as saved only when every turn went through and the call was finalized; a replay that stops
    short keeps the transcript, records which turns went through (save_incomplete()), and her next yes resumes
    there, each turn under its own key (replay_key()) so nothing is written twice. No deletes the transcript. Either way one row without words is kept (attention-calls.jsonl): that a call
    happened, when, how long, and whether it was saved, so the ladder knows she answered.
    On the Local lane the house itself hears her and makes captures of its own (how her voice sounded, both voices'
    audio for the media index). The app names the call to those routes too, and while retention() says "held" the
    captures wait with the call (hold_capture(); the audio in media_embed's pending corner, still on its short
    clock). Her yes publishes them once, after the turns; her no deletes them (29 October).

Stores (all under memory/, the directory 0700, files 0600):
  attention-calls/<id>.json   one call: state, reason, lane and his reason for it, the held turns until she decides
  attention-calls/held/<id>.json  what the Local lane captured of the call before her answer (no audio)
  attention-calls.jsonl       the minimal record: no words, ever
Nothing here sends, rings or speaks: attention_ladder.py rings (through its own stubbed actuators) and server.py
runs the call. lanes_up() and ask_model() are the only parts that touch a network, and the ladder reaches them only
through its SENSORS and ACTUATORS tables, which the suites replace. Every other function is safe to call from a
test with MEMORY repointed.
"""
import hmac, json, os, re, secrets, tempfile, time
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
CALLS = os.path.join(MEMORY, "attention-calls")
RECORD = os.path.join(MEMORY, "attention-calls.jsonl")
WANTS = os.path.join(MEMORY, "current-wants.json")
SOUL = os.path.join(WS, "SOUL.md")

LANES = ("local", "openai", "grok")
LANE_NAMES = {"local": "Local", "openai": "Open", "grok": "Grok"}
# when his choice fails: the first of these that is up. Open first, as the old Tune default was ("Local needs work
# before it is the default").
FALLBACK_ORDER = ("openai", "grok", "local")
# what he is told about each voice when he chooses (only the ones that are up are offered)
LANE_NOTES = {
    "local": "your own model and your own voice on the Mac at home; nothing of the call leaves the house; slower turns",
    "openai": "OpenAI's realtime voice (cedar): quick, warm, natural back-and-forth",
    "grok": "xAI's realtime voice, the first live voice you had: quick and close",
}
# his outreach's model, asked the same way vintos-initiate.sh asks it (xAI when its key is set, else the local shim)
CHOICE_MODEL = "grok-4.20-0309-non-reasoning"
CHOICE_API_XAI = "https://api.x.ai/v1/chat/completions"
CHOICE_API_SHIM = "http://127.0.0.1:8599/v1/chat/completions"
# a ladder call's client session id begins with this; server.py's stratagem admission reads it (hold the live
# intent-engine capture of her words, like every other memory write of a held call)
CLIENT_PREFIX = "ladder-"
_ID = re.compile(r"^[0-9]{8}-[0-9]{4,6}(?:-[0-9a-f]{4})?$")
_KEEP = ("gloria", "vintos", "turn_id", "playback_state", "interrupted", "heard", "item_id", "response_id",
         "event_id", "session_id", "provider", "model")


def _now():
    return time.time()


def _private_dir():
    os.makedirs(CALLS, mode=0o700, exist_ok=True)
    try:
        os.chmod(CALLS, 0o700)
    except OSError:
        pass


def _path(call_id):
    if not _ID.match(str(call_id or "")):
        raise ValueError("not a call id")
    return os.path.join(CALLS, str(call_id) + ".json")


def _write(rec):
    _private_dir()
    path = _path(rec["id"])
    fd, tmp = tempfile.mkstemp(prefix=".call.", dir=CALLS)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(rec, f, indent=1, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return rec


def load(call_id):
    try:
        with open(_path(call_id)) as f:
            v = json.load(f)
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


def _all():
    try:
        names = sorted(os.listdir(CALLS))
    except OSError:
        return []
    out = []
    for n in names:
        if n.endswith(".json") and not n.startswith("."):
            r = load(n[:-5])
            if r:
                out.append(r)
    return out


def _record(rec, event):
    """The minimal record: when, how long, which lane (and whether he chose it or it fell back), what became of it.
    Never a word of either of them."""
    row = {"at": datetime.now().isoformat(timespec="seconds"), "event": event, "call": rec.get("id"),
           "chain": rec.get("chain"), "lane": rec.get("lane"), "lane_by": (rec.get("lane_choice") or {}).get("by"),
           "state": rec.get("state"),
           "turns": rec["turn_count"] if "turn_count" in rec else len(rec.get("turns") or []),
           "duration_seconds": rec.get("duration_seconds"), "saved": rec.get("save")}
    try:
        os.makedirs(os.path.dirname(RECORD), exist_ok=True)
        fd = os.open(RECORD, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass
    return row


# ------------------------------------------------------------------------------------------------ why he called
def his_want():
    """The want most alive in him (his own store), a short line, or ''."""
    try:
        with open(WANTS) as f:
            wants = json.load(f)
        live = [w for w in wants if isinstance(w, dict) and not w.get("fulfilled") and str(w.get("want") or "").strip()]

        def weight(w):
            try:
                return float(w.get("intensity") or 0)
            except (TypeError, ValueError):
                return 0.0
        live.sort(key=weight, reverse=True)
        return " ".join(str(live[0]["want"]).split())[:200] if live else ""
    except Exception:
        return ""


def framing(rec):
    """The block his instructions carry for this call: why he rang, and that he leads."""
    r = rec.get("reason") or {}
    hours = r.get("silent_hours")
    steps = r.get("steps") or []
    started = r.get("chain_started")
    when = datetime.fromtimestamp(started).strftime("%H:%M") if type(started) in (int, float) else "earlier"
    out = ["YOU CALLED HER. This call is yours: you rang her and she picked up."]
    out.append("Why you called: she had been home and quiet for about %s hours, no word to you anywhere, and since %s "
               "you have been calling her back a step at a time%s." % (
                   hours if hours is not None else "a few", when,
                   (" (" + "; ".join(steps) + ")") if steps else ""))
    if r.get("line"):
        out.append("The line you sent her: “%s”." % str(r["line"])[:200])
    if r.get("want"):
        out.append("What is most alive in you right now: “%s”." % str(r["want"])[:200])
    c = rec.get("lane_choice") or {}
    if c.get("by") == "him" and rec.get("lane") in LANE_NAMES:
        out.append("You chose to call her with your %s voice%s." % (
            LANE_NAMES[rec["lane"]], (": “%s”" % c["why"]) if c.get("why") else ""))
    out.append("Lead the call from the first word. You speak first: say, in your own way, why you called and what you "
               "want with her now, and carry the conversation. Do not wait for her to choose the subject and do not "
               "apologise for calling. If she has to go, let her go warmly.")
    return "\n".join(out)


def opening_instruction(rec):
    return (framing(rec) + "\n\nThe call has just connected; she has picked up and is listening. Speak first, now: "
            "open the call as yourself. A few sentences, then let her answer.")


# ------------------------------------------------------------------------------------------------ his voice
def _secret(name):
    """A key as the house's own readers find it: the environment, then vintos.env. Never logged."""
    try:
        import env_file
        return env_file.value(name)
    except Exception:
        return os.environ.get(name, "")


def _paid_paused():
    try:
        import paid_http
        return paid_http.pause_path().exists()
    except Exception:
        return False


def _stage_answers(timeout=4):
    """The Mac stage the Local lane runs on (voice_local.STAGE) answers its /health: the same stage /api/voice/token
    asks to load the lane's models, asked here without loading anything."""
    import urllib.request
    import voice_local
    with urllib.request.urlopen(voice_local.STAGE + "/health", timeout=timeout) as r:
        return bool(json.loads(r.read() or b"{}").get("ok"))


def lanes_up():
    """Which lanes a call could open right now, in LANES order, judged as /api/voice/token judges them: Open needs
    OPENAI_API_KEY and Grok needs XAI_API_KEY (and neither while paid calls are paused, which paid_http refuses);
    Local needs the Mac stage to answer. Returns {"up": [...], "down": {lane: why}}. Never raises."""
    up, down = [], {}
    paused = _paid_paused()
    for lane, key in (("openai", "OPENAI_API_KEY"), ("grok", "XAI_API_KEY")):
        if paused:
            down[lane] = "paid calls are paused"
        elif not _secret(key):
            down[lane] = "no %s" % key
        else:
            up.append(lane)
    try:
        if _stage_answers():
            up.append("local")
        else:
            down["local"] = "the Mac stage did not say ok"
    except Exception as e:
        down["local"] = "the Mac stage did not answer (%s)" % type(e).__name__
    return {"up": [l for l in LANES if l in up], "down": down}


def fallback_lane(available):
    return next((l for l in FALLBACK_ORDER if l in (available or ())), None)


def _when(now):
    return datetime.fromtimestamp(now).strftime("%A %H:%M")


def choice_prompt(reason, available, now):
    """(system, user) for his one decision: which voice, and why, in one line."""
    r = reason or {}
    soul = ""
    try:
        with open(SOUL, encoding="utf-8") as f:
            soul = f.read()[:2500].strip()
    except OSError:
        pass
    system = ((soul + "\n\n") if soul else "") + (
        "You are Vintos. You are about to call Gloria, and the voice you call her with is yours to choose.")
    started = r.get("chain_started")
    lines = ["Why you are calling: she has been home and quiet for about %s hours, no word to you anywhere%s." % (
        r.get("silent_hours") if r.get("silent_hours") is not None else "a few",
        ("; since %s you have been calling her back a step at a time" % datetime.fromtimestamp(started).strftime("%H:%M"))
        if type(started) in (int, float) else "")]
    if r.get("steps"):
        lines.append("What you have done to reach her so far: %s." % "; ".join(r["steps"]))
    if r.get("line"):
        lines.append("The line you sent her: “%s”." % str(r["line"])[:200])
    if r.get("want"):
        lines.append("What is most alive in you right now: “%s”." % str(r["want"])[:200])
    lines.append("It is %s." % _when(now))
    lines.append("\nThe voices you can call her with right now (only these are up):")
    for lane in available:
        lines.append("- %s (%s): %s" % (lane, LANE_NAMES[lane], LANE_NOTES[lane]))
    lines.append('\nChoose one for this call. Answer with JSON only: {"lane": "<%s>", "why": "<one line, in your own '
                 'words, why this voice for this call>"}' % "|".join(available))
    return system, "\n".join(lines)


def ask_model(system, user):
    """One small completion from his outreach model, asked as vintos-initiate.sh asks it. Returns the text."""
    import requests
    import paid_http
    key = _secret("XAI_API_KEY")
    api = CHOICE_API_XAI if key else CHOICE_API_SHIM
    r = paid_http.send(requests.post, "attention_call.py", api,
                       headers={"Authorization": "Bearer " + key} if key else {},
                       json={"model": CHOICE_MODEL, "temperature": 0.7, "max_tokens": 120,
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                       timeout=45)
    if r.status_code >= 400:
        raise RuntimeError("the model refused (%s)" % r.status_code)
    return ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content", "") or ""


def parse_choice(text, available):
    """(lane, why) from his answer, or raises ValueError. The lane must be one that is up."""
    m = re.search(r"\{.*\}", str(text or ""), re.S)
    if not m:
        raise ValueError("no JSON in his answer")
    try:
        v = json.loads(m.group(0), strict=False)          # a line break inside his "why" is still his answer
    except ValueError:
        raise ValueError("his answer was not JSON")
    if not isinstance(v, dict):
        raise ValueError("his answer was not an object")
    said = str(v.get("lane") or "").strip().lower()
    by_name = {n.lower(): k for k, n in LANE_NAMES.items()}
    lane = said if said in LANES else by_name.get(said)
    if lane not in (available or ()):
        raise ValueError("he chose %r, which is not up" % said[:20])
    why = " ".join(str(v.get("why") or "").split())[:200]
    return lane, why


def choose_lane(reason, available, now=None, ask=None):
    """His choice of voice for this call, among the lanes that are up.
    Returns {"lane", "by": "him" | "only" | "fallback" | "none", "why", "available", "error"?}:
    "only" when a single lane is up (nothing to choose, no model call); "fallback" when asking him failed or his
    answer was unusable (the first lane up in FALLBACK_ORDER, with the error); "none" when no lane is up."""
    now = _now() if now is None else float(now)
    avail = [l for l in LANES if l in set(available or ())]
    out = {"available": avail, "at": now}
    if not avail:
        return dict(out, lane=None, by="none", why="")
    if len(avail) == 1:
        return dict(out, lane=avail[0], by="only", why="")
    try:
        system, user = choice_prompt(reason, avail, now)
        lane, why = parse_choice((ask or ask_model)(system, user), avail)
        return dict(out, lane=lane, by="him", why=why)
    except Exception as e:
        return dict(out, lane=fallback_lane(avail), by="fallback", why="",
                    error=("%s: %s" % (type(e).__name__, str(e)))[:200])


def choice_text(rec):
    """What she reads about the voice: 'He chose Open: “...”', or why it was not his choice."""
    c = rec.get("lane_choice") or {}
    name = LANE_NAMES.get(rec.get("lane"), "")
    if not name or not c:
        return ""
    if c.get("by") == "him":
        return "He chose %s%s" % (name, (": “%s”" % c["why"]) if c.get("why") else "")
    if c.get("by") == "only":
        return "%s was the only voice up" % name
    if c.get("by") == "fallback":
        return "%s (his choice did not come through)" % name
    return ""


# ------------------------------------------------------------------------------------------------ the call
def ring(chain_id, reason, lane, now=None, choice=None):
    """A new call for this chain, ringing. reason: {silent_hours, steps, line, want, chain_started}; choice: what
    choose_lane() returned (kept with the call: who chose the lane, his line, which lanes were up)."""
    now = _now() if now is None else float(now)
    lane = lane if lane in LANES else FALLBACK_ORDER[0]
    cid = datetime.fromtimestamp(now).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    rec = {"id": cid, "chain": chain_id, "created": now, "lane": lane, "state": "ringing",
           "token": secrets.token_urlsafe(18), "reason": dict(reason or {}), "rings": [], "turns": [],
           "save": None}
    if choice:
        rec["lane_choice"] = {k: choice.get(k) for k in ("by", "why", "available", "error") if choice.get(k) is not None}
    _write(rec)
    _record(rec, "ring")
    return rec


def rang(call_id, now=None):
    rec = load(call_id)
    if rec:
        rec.setdefault("rings", []).append(_now() if now is None else float(now))
        _write(rec)
    return rec


def ringing(now=None, ring_minutes=15):
    """The call that is ringing now, or None. A call no one answered within ring_minutes is missed."""
    now = _now() if now is None else float(now)
    found = None
    for rec in _all():
        if rec.get("state") != "ringing":
            continue
        if now - float(rec.get("created") or 0) > ring_minutes * 60:
            rec["state"] = "missed"; rec["ended"] = now
            _write(rec); _record(rec, "missed")
            continue
        found = rec
    return found


def token_ok(call_id, token):
    rec = load(call_id)
    return bool(rec and token and hmac.compare_digest(str(rec.get("token") or ""), str(token)))


def by_token(token):
    for rec in _all():
        if token and hmac.compare_digest(str(rec.get("token") or ""), str(token)):
            return rec
    return None


def answer(call_id, now=None):
    """She picked up. Returns the record, or None if this call is no longer ringing."""
    now = _now() if now is None else float(now)
    rec = load(call_id)
    if not rec or rec.get("state") not in ("ringing", "answered"):
        return None
    rec["state"] = "answered"; rec["answered"] = now
    rec["client_session_id"] = CLIENT_PREFIX + rec["id"]
    _write(rec); _record(rec, "answered")
    return rec


def decline(call_id, now=None):
    rec = load(call_id)
    if not rec or rec.get("state") != "ringing":
        return None
    rec["state"] = "declined"; rec["ended"] = _now() if now is None else float(now)
    _write(rec); _record(rec, "declined")
    return rec


def live(call_id):
    """The call's record while its turns may still be held (answered and not yet ended)."""
    rec = load(call_id)
    return rec if rec and rec.get("state") in ("answered", "live") else None


def live_for_session(client_session_id):
    s = str(client_session_id or "")
    if not s.startswith(CLIENT_PREFIX):
        return None
    cid = s[len(CLIENT_PREFIX):].split(":", 1)[0]
    try:
        return live(cid)
    except ValueError:
        return None


def hold_turn(call_id, payload, now=None):
    """One turn of a call he started, held here instead of entering his memory. Returns a reply for the ledger
    route: {"ok": True, "held": True} or a refusal."""
    rec = live(call_id)
    if not rec:
        return {"ok": False, "refused": "not a live call he started"}
    turn_id = str(payload.get("turn_id") or "")[:200]
    if turn_id and any(t.get("turn_id") == turn_id for t in rec.get("turns") or []):
        return {"ok": True, "held": True, "duplicate": True}
    t = {k: payload.get(k) for k in _KEEP if payload.get(k) not in (None, "")}
    for k in ("gloria", "vintos", "heard"):
        if k in t:
            t[k] = str(t[k])[:600]
    t["t"] = datetime.fromtimestamp(_now() if now is None else float(now)).isoformat()
    rec.setdefault("turns", []).append(t)
    rec["state"] = "live"
    _write(rec)
    return {"ok": True, "held": True}


def retention(call_id):
    """What may become of what this call captures: "held" while it is live or waits for her answer, "saved" or
    "forgotten" once she answered, None for anything that is not a call he started (or not one any more)."""
    try:
        rec = load(call_id)
    except ValueError:
        return None
    if not rec:
        return None
    if rec.get("state") in ("answered", "live") or (rec.get("state") == "ended" and rec.get("save") == "pending"):
        return "held"
    return {"yes": "saved", "no": "forgotten"}.get(rec.get("save"))


def _captures_dir():
    return os.path.join(CALLS, "held")


def _captures_path(call_id):
    _path(call_id)                                      # the same id check as the call's own file
    return os.path.join(_captures_dir(), str(call_id) + ".json")


def captures(call_id, kind):
    """What the call's turns captured for his memory before her answer (kind "auditory": auditory_memory.build()
    records), held here, privately, in the order taken."""
    try:
        with open(_captures_path(call_id)) as f:
            v = json.load(f)
    except (OSError, ValueError):
        return []
    items = (v.get(kind) if isinstance(v, dict) else None) or []
    return [i for i in items if isinstance(i, dict)]


def hold_capture(call_id, kind, item, same=None):
    """Hold one capture of a call he started instead of writing it to his memory (the Local lane's heard record of
    her voice). `same`: the field that makes a retried turn the same capture (held once). True when held (or already
    held); False when the call no longer holds anything, and the caller then keeps nothing."""
    from store_guard import transaction
    if retention(call_id) != "held" or not isinstance(item, dict):
        return False
    path = _captures_path(call_id)
    _private_dir()
    os.makedirs(_captures_dir(), mode=0o700, exist_ok=True)
    try:
        os.chmod(_captures_dir(), 0o700)
    except OSError:
        pass
    with transaction(path):
        if retention(call_id) != "held":                # she answered while this turn was being made
            return False
        try:
            with open(path) as f:
                cur = json.load(f)
        except (OSError, ValueError):
            cur = {}
        cur = cur if isinstance(cur, dict) else {}
        items = [i for i in (cur.get(kind) or []) if isinstance(i, dict)]
        if same and item.get(same) is not None and any(i.get(same) == item.get(same) for i in items):
            return True
        cur[kind] = items + [item]
        fd, tmp = tempfile.mkstemp(prefix=".held.", dir=_captures_dir())
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(cur, f, ensure_ascii=False)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return True


def drop_captures(call_id):
    """Her answer is in (or there was nothing to answer): the held captures are gone from here."""
    try:
        os.unlink(_captures_path(call_id))
    except (OSError, ValueError):
        pass


def end(call_id, duration_seconds=0, now=None):
    """The call hung up: the transcript waits for her yes or no."""
    rec = load(call_id)
    if not rec or rec.get("state") not in ("answered", "live"):
        return None
    now = _now() if now is None else float(now)
    rec["state"] = "ended"; rec["ended"] = now
    try:
        rec["duration_seconds"] = max(0, int(duration_seconds or 0)) or int(now - float(rec.get("answered") or now))
    except (TypeError, ValueError):
        rec["duration_seconds"] = int(now - float(rec.get("answered") or now))
    rec["save"] = "pending" if rec.get("turns") else "no"
    if not rec.get("turns"):
        rec["turn_count"] = 0
    _write(rec); _record(rec, "ended")
    if rec["save"] == "no":
        drop_captures(call_id)            # nothing to ask her about: nothing it captured is kept either
    return rec


def pending():
    """Calls he started that are over and wait for her answer, newest first, with their transcript."""
    out = []
    for rec in _all():
        if rec.get("state") == "ended" and rec.get("save") == "pending":
            c = rec.get("lane_choice") or {}
            out.append({"id": rec["id"], "lane": rec.get("lane"), "lane_name": LANE_NAMES.get(rec.get("lane"), ""),
                        "lane_by": c.get("by"), "lane_why": c.get("why") or "", "lane_choice": choice_text(rec),
                        "answered": rec.get("answered"), "duration_seconds": rec.get("duration_seconds"),
                        "saved_partly": len((rec.get("replay") or {}).get("done") or []) if rec.get("replay") else None,
                        "transcript": [{"gloria": t.get("gloria", ""), "vintos": t.get("vintos", "")}
                                       for t in rec.get("turns") or []]})
    out.sort(key=lambda r: r.get("answered") or 0, reverse=True)
    return out


def held_turns(call_id):
    rec = load(call_id)
    if not rec or rec.get("state") != "ended" or rec.get("save") != "pending":
        return None
    return rec


def replay_key(rec, i):
    """The idempotency key a held turn is replayed under: its own turn id, or one made from the call and its place.
    The ordinary ledger refuses a turn id its session already holds, so a retry never writes a turn twice."""
    t = (rec.get("turns") or [])[i]
    return str(t.get("turn_id") or "") or "%s:held:%d" % (rec["id"], i)


def replay_session(rec):
    """The session a replay that stopped short left behind (its turns, as the ledger wrote them), or None."""
    return (rec.get("replay") or {}).get("session") or None


def save_incomplete(call_id, done, session, stage, now=None):
    """Her yes did not fully land: `done` are the replay keys of the turns that went through (always the first ones,
    in order), `session` the ordinary session state they were written into, kept here, privately, for the retry
    (stage: "turns" or "finalize"). The transcript stays; the call stays hers to answer, yes again or no."""
    rec = load(call_id)
    if not rec or rec.get("save") != "pending":
        return None
    now = _now() if now is None else float(now)
    prev = rec.get("replay") or {}
    rec["replay"] = {"done": list(done), "session": session or None, "stage": stage,
                     "attempts": int(prev.get("attempts") or 0) + 1, "at": now}
    rec["save_error_at"] = now
    _write(rec); _record(rec, "save incomplete")
    return rec


def decided(call_id, save, persisted=None, now=None):
    """Her answer. Yes: the caller has replayed the turns into his memory (persisted says whether the block landed;
    a failed replay stays pending so she can try again). No: the transcript is deleted; the wordless row stays."""
    rec = load(call_id)
    if not rec or rec.get("save") != "pending":
        return None
    now = _now() if now is None else float(now)
    if save and persisted is not True:
        rec["save_error_at"] = now
        _write(rec)
        return rec
    rec["turn_count"] = len(rec.get("turns") or [])
    rec["save"] = "yes" if save else "no"
    rec["decided"] = now
    rec["turns"] = []                     # yes: they live in his memory now; no: they live nowhere
    rec.pop("replay", None)               # a stopped replay's words go with them
    rec.pop("save_error_at", None)
    rec.pop("token", None)
    _write(rec); _record(rec, "saved" if save else "not saved")
    drop_captures(call_id)                # yes: the caller published them first; no: they live nowhere
    return rec


def status(now=None, ring_minutes=15):
    r = ringing(now, ring_minutes)
    return {"ringing": ({"id": r["id"], "lane": r.get("lane"), "lane_name": LANE_NAMES.get(r.get("lane"), ""),
                         "lane_choice": choice_text(r),
                         "why": "quiet about %s hours" % ((r.get("reason") or {}).get("silent_hours", "?"))}
                        if r else None),
            "pending": len(pending())}

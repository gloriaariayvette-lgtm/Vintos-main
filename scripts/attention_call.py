#!/usr/bin/env python3
"""attention_call.py - the last step of the attention ladder: he calls her (27 October).

Gloria, on the ladder: the call is "the only part that would have actually worked or meant anything".

A call he starts is an ordinary voice call of his - the same lanes (Local, Open, Grok), the same full instructions
from /api/voice/token, the same per-turn framing, the same ledger route and session end - with three differences:

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
    today; no deletes the transcript. Either way one row without words is kept (attention-calls.jsonl): that a call
    happened, when, how long, and whether it was saved, so the ladder knows she answered.

Stores (all under memory/, the directory 0700, files 0600):
  attention-calls/<id>.json   one call: state, reason, lane, the held turns until she decides
  attention-calls.jsonl       the minimal record: no words, ever
Nothing here sends, rings or speaks: attention_ladder.py rings (through its own stubbed actuators) and server.py
runs the call. Every function is safe to call from a test with MEMORY repointed.
"""
import hmac, json, os, re, secrets, tempfile, time
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
CALLS = os.path.join(MEMORY, "attention-calls")
RECORD = os.path.join(MEMORY, "attention-calls.jsonl")
WANTS = os.path.join(MEMORY, "current-wants.json")

LANES = ("local", "openai", "grok")
LANE_NAMES = {"local": "Local", "openai": "Open", "grok": "Grok"}
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
    """The minimal record: when, how long, which lane, what became of it. Never a word of either of them."""
    row = {"at": datetime.now().isoformat(timespec="seconds"), "event": event, "call": rec.get("id"),
           "chain": rec.get("chain"), "lane": rec.get("lane"), "state": rec.get("state"),
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
    out.append("Lead the call from the first word. You speak first: say, in your own way, why you called and what you "
               "want with her now, and carry the conversation. Do not wait for her to choose the subject and do not "
               "apologise for calling. If she has to go, let her go warmly.")
    return "\n".join(out)


def opening_instruction(rec):
    return (framing(rec) + "\n\nThe call has just connected; she has picked up and is listening. Speak first, now: "
            "open the call as yourself. A few sentences, then let her answer.")


# ------------------------------------------------------------------------------------------------ the call
def ring(chain_id, reason, lane, now=None):
    """A new call for this chain, ringing. reason: {silent_hours, steps, line, want, chain_started}."""
    now = _now() if now is None else float(now)
    lane = lane if lane in LANES else "openai"
    cid = datetime.fromtimestamp(now).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    rec = {"id": cid, "chain": chain_id, "created": now, "lane": lane, "state": "ringing",
           "token": secrets.token_urlsafe(18), "reason": dict(reason or {}), "rings": [], "turns": [],
           "save": None}
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
    return rec


def pending():
    """Calls he started that are over and wait for her answer, newest first, with their transcript."""
    out = []
    for rec in _all():
        if rec.get("state") == "ended" and rec.get("save") == "pending":
            out.append({"id": rec["id"], "lane": rec.get("lane"), "lane_name": LANE_NAMES.get(rec.get("lane"), ""),
                        "answered": rec.get("answered"), "duration_seconds": rec.get("duration_seconds"),
                        "transcript": [{"gloria": t.get("gloria", ""), "vintos": t.get("vintos", "")}
                                       for t in rec.get("turns") or []]})
    out.sort(key=lambda r: r.get("answered") or 0, reverse=True)
    return out


def held_turns(call_id):
    rec = load(call_id)
    if not rec or rec.get("state") != "ended" or rec.get("save") != "pending":
        return None
    return rec


def decided(call_id, save, persisted=None, now=None):
    """Her answer. Yes: the caller has replayed the turns into his memory (persisted says whether the block landed;
    a failed replay stays pending so she can try again). No: the transcript is deleted; the wordless row stays."""
    rec = load(call_id)
    if not rec or rec.get("save") != "pending":
        return None
    now = _now() if now is None else float(now)
    if save and persisted is False:
        rec["save_error_at"] = now
        _write(rec)
        return rec
    rec["turn_count"] = len(rec.get("turns") or [])
    rec["save"] = "yes" if save else "no"
    rec["decided"] = now
    rec["turns"] = []                     # yes: they live in his memory now; no: they live nowhere
    rec.pop("token", None)
    _write(rec); _record(rec, "saved" if save else "not saved")
    return rec


def status(now=None, ring_minutes=15):
    r = ringing(now, ring_minutes)
    return {"ringing": ({"id": r["id"], "lane": r.get("lane"), "lane_name": LANE_NAMES.get(r.get("lane"), ""),
                         "why": "quiet about %s hours" % ((r.get("reason") or {}).get("silent_hours", "?"))}
                        if r else None),
            "pending": len(pending())}

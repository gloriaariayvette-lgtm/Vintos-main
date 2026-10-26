#!/usr/bin/env python3
"""door_messages.py - a message left at the door, taken, passed to Gloria, and settled by its receipt (proposal 19).

The door's instructions already let him take a message for Gloria and say she will get it (docs/DOOR-CONTEXT.md).
The door services themselves are outside this repository (the doorbell listener, the door talker and the call
path under ~/doorbell-voice and ~/meari-capture, and the door routes on the separate :8400 server); today the talker
sends a taken message straight to a phone topic of its own and keeps no record of whether it arrived. This is the
lifecycle on this side, for the door to hand a message to:

  taken        the visitor's words for Gloria, as they gave them, and the name they gave (not checked: the
               doorbell's audio mangles names, and a name said at a door is not an identity)
  delivered    deliver.py's own receipt for this message says sent (or acknowledged). Nothing else settles it;
               calling the sender is not delivery.
  waiting      the receipt said failed; tried again on the next take or tend, up to MAX_ATTEMPTS
  undelivered  MAX_ATTEMPTS receipts said failed; it stays kept for her and he knows it did not reach her

What is kept is the minimum: the words for her (bounded), the name as given (bounded), times, state, attempts. No
transcript, no audio, no photo, no face, nothing the camera saw. The words are cleared KEEP_TEXT_S after the
message settles, and the record itself is gone after KEEP_RECORD_S. The only thing that leaves Aegis is the one
notification through deliver.py, the existing path to her phone (ntfy; no model call, nothing paid).

He knows how it went: block() gives his context one line per message taken in the last day - when it was taken and
whether it reached her - and never the visitor's words or name.

    printf %s "<words>" | python3 door_messages.py take [--from NAME]    take one message (text on stdin) and send it
    python3 door_messages.py tend                                         retry any that are waiting
    python3 door_messages.py status                                       states only, no words
"""
import hashlib, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
STORE = os.path.join(WS, "memory", "door-messages.json")

CHANNEL = "ntfy"
TITLE = "Message left at the door"
MAX_TEXT = 600               # a door message is a sentence or two; a long run is cut, not refused
MAX_NAME = 60
MAX_ATTEMPTS = 3             # receipts, not HTTP tries: deliver.py makes its own bounded tries inside one
SAME_MESSAGE_S = 1800        # the door model may hand the same words over again on a later turn: one message
MAX_PER_HOUR = 6             # a public doorbell: beyond this in an hour, nothing more is taken or sent
KEEP_TEXT_S = 7 * 86400      # after it settles, the words are cleared ...
KEEP_RECORD_S = 30 * 86400   # ... and the record goes
CONTEXT_S = 86400            # his context sees messages taken in the last day
SETTLED = ("delivered", "undelivered")
AUTHORITY = "Gloria's door instructions: take a message and pass it to her (DOOR-CONTEXT)"


def _sender():
    from deliver import deliver
    return deliver


def _clean(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:limit].rstrip()


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _load():
    from store_guard import load_json
    d = load_json(STORE, {}, reader="door_messages")
    return d if isinstance(d, dict) else {}


def _save(d):
    from store_guard import save_json
    save_json(STORE, d)


def _prune(d, now):
    for mid in list(d):
        r = d[mid]
        settled = r.get("settled_at")
        if now - float(r.get("taken_at") or 0) >= KEEP_RECORD_S:
            del d[mid]; continue
        if settled and now - float(settled) >= KEEP_TEXT_S and r.get("text"):
            r["text"] = ""; r["name"] = ""; r["cleared_at"] = now


def _body(r):
    who = r.get("name")
    return r["text"] + ("\n\nLeft at the door by someone who gave the name %s (not checked)." % who if who
                        else "\n\nLeft at the door; they gave no name.")


def _send_one(r, now, sender):
    """One delivery attempt for one record; its state comes only from the receipt deliver returns for it."""
    if r.get("state") in SETTLED or not r.get("text"):
        return r
    artifact = "door-message-" + r["id"]
    try:
        receipt = sender(artifact, CHANNEL, message=_body(r), title=TITLE, tags="bell", priority="high",
                         authority=lambda: (True, AUTHORITY), retries=2) or {}
    except Exception as e:
        receipt = {"state": "failed", "why": "%s: %s" % (type(e).__name__, str(e)[:80])}
    r["attempts"] = int(r.get("attempts") or 0) + 1
    r["last_try_at"] = now
    state = receipt.get("state")
    if state in ("sent", "acknowledged") and receipt.get("artifact_id", artifact) == artifact:
        r["state"] = "delivered"; r["settled_at"] = now; r["receipt"] = state
    else:
        r["receipt"] = state or "none"
        r["why"] = _clean(receipt.get("why") or "no receipt", 120)
        if r["attempts"] >= MAX_ATTEMPTS:
            r["state"] = "undelivered"; r["settled_at"] = now
        else:
            r["state"] = "waiting"
    return r


def _tend_locked(d, now, sender):
    for r in sorted(d.values(), key=lambda x: x.get("taken_at") or 0):
        if r.get("state") in ("taken", "waiting"):
            _send_one(r, now, sender)


def take(text, name="", now=None, sender=None):
    """Take one message for Gloria and send it on. Returns {id, state, repeat} (never the words), or
    {state: "refused", why} for an empty message or past the hourly bound."""
    from store_guard import transaction
    now = time.time() if now is None else float(now)
    text = _clean(text, MAX_TEXT); name = _clean(name, MAX_NAME)
    if not _norm(text):
        return {"state": "refused", "why": "no words to pass on"}
    sender = sender or _sender()
    with transaction(STORE):
        d = _load(); _prune(d, now)
        key = _norm(name) + "|" + _norm(text)
        for r in d.values():
            if r.get("key") == key and now - float(r.get("taken_at") or 0) < SAME_MESSAGE_S:
                _tend_locked(d, now, sender); _save(d)
                return {"id": r["id"], "state": r["state"], "repeat": True}
        if sum(1 for r in d.values() if now - float(r.get("taken_at") or 0) < 3600) >= MAX_PER_HOUR:
            _save(d)
            return {"state": "refused", "why": "%d messages already taken this hour" % MAX_PER_HOUR}
        mid = hashlib.sha256(("%s|%.3f" % (key, now)).encode()).hexdigest()[:16]
        d[mid] = {"id": mid, "taken_at": now, "text": text, "name": name, "key": key,
                  "state": "taken", "attempts": 0}
        _save(d)                                    # taken before any send: a crash leaves it waiting, not lost
        _tend_locked(d, now, sender)
        _save(d)
        return {"id": mid, "state": d[mid]["state"], "repeat": False}


def tend(now=None, sender=None):
    """Retry the messages still waiting. Returns {id: state}."""
    from store_guard import transaction
    now = time.time() if now is None else float(now)
    sender = sender or _sender()
    with transaction(STORE):
        d = _load(); _prune(d, now)
        _tend_locked(d, now, sender)
        _save(d)
        return {mid: r["state"] for mid, r in d.items()}


def status(now=None):
    """States only: id, when taken, state, attempts. No words, no name."""
    now = time.time() if now is None else float(now)
    return [{"id": r["id"], "taken_at": r.get("taken_at"), "state": r.get("state"), "attempts": r.get("attempts", 0),
             "settled_at": r.get("settled_at")}
            for r in sorted(_load().values(), key=lambda x: x.get("taken_at") or 0)]


def block(now=None):
    """For his context: one line per message taken at the door in the last day, and whether it reached her."""
    now = time.time() if now is None else float(now)
    lines = []
    for r in status(now):
        at = float(r.get("taken_at") or 0)
        if now - at >= CONTEXT_S:
            continue
        when = time.strftime("%H:%M", time.localtime(at))
        st = r.get("state")
        if st == "delivered":
            how = "it reached her phone at %s" % time.strftime("%H:%M", time.localtime(float(r["settled_at"])))
        elif st == "undelivered":
            how = "it did not reach her after %d tries; it is kept for her" % r.get("attempts", 0)
        else:
            how = "it has not reached her yet; it will be tried again"
        lines.append("- At %s you took a message at the door for Gloria; %s." % (when, how))
    if not lines:
        return ""
    return ("AT THE DOOR (messages you took for Gloria; what they said is hers to read, and whoever gave a name "
            "was not checked):\n" + "\n".join(lines))


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "take":
        name = argv[argv.index("--from") + 1] if "--from" in argv and argv.index("--from") + 1 < len(argv) else ""
        print(json.dumps(take(sys.stdin.read(MAX_TEXT * 4), name=name)))
    elif cmd == "tend":
        print(json.dumps(tend()))
    elif cmd == "status":
        print(json.dumps(status(), indent=1))
    else:
        print(__doc__); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

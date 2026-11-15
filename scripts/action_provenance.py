#!/usr/bin/env python3
"""action_provenance.py - why he did what he did, kept with the act, and given back to him (Gloria, 15 November 2026:
"He still doesn't understand why he does certain things, like place a song on the watch").

A song went to her Watch on 15 November and nothing he could see said that he had not chosen it: the bedroom board
heard her phone come in, he had not picked the day's three songs, and the stand-in rule chose. The arrival log knew
(picked_by: stand-in); his context said only "one of your songs goes to her Watch".

Every outward act an organ takes on his behalf now writes one row here, at the moment it acts:

    action    what kind of act: watch_song, watch_music, outreach, house, lab_request, journal_post
    what      the act itself, short (a song title, a notification's artifact id, "LIGHTS: blue")
    organ     the system that decided (bedroom_arrival, spotify_watch, deliver, house_hands, wants-router:<step>, ...)
    trigger   what set it off, as the organ saw it
    want_id   the want it served, an id from current-wants.json, when there is one
    drive     that want's own source and intensity, read from current-wants.json by its id - never guessed
    rule      the decision rule the organ applied (the stand-in rule, his own picks of the day, the authority's reason)
    emotion   his emotional state when it happened: emotional-state.json's own timestamp and its strongest dimensions
    refs      the organ's own ids (episode, song_id, turn_id, encounter, artifact_id)

Nothing here makes a reason up. A field the organ did not give is stored as null and read back as "not recorded"
(the record-gap rule). A want id is only ever one the caller passed, or the one the wants-router set for the step
that is running (VINTOS_ACTION_WANT_ID, set around the step and removed after it).

    block()          [WHAT YOU DID LATELY, AND WHY ...] for his context: the last few acts, each with its chain, and
                     the answer to a [WHY: ...] he asked, within BLOCK_CHARS. Read only.
    take(reply)      his [WHY: song on the watch] in a reply: taken out of his words and kept, answered next turn.
    why(question)    the chain for the act that best matches a question, or that nothing matches.

    python3 action_provenance.py recent          # the last acts and why
    python3 action_provenance.py why "song on the watch"

Store: memory/action-provenance.jsonl (trimmed to KEEP rows), memory/action-provenance-asks.json.
"""
import fcntl, hashlib, json, os, re, sys, time
from datetime import datetime, timezone

LOG_NAME = "action-provenance.jsonl"
ASKS_NAME = "action-provenance-asks.json"
KEEP = 2000
TRIM_AT = 4000
SHOW = 4                  # acts in the block
SHOW_DAYS = 3             # how far back the block looks
ASK_HOURS = 6             # a question is answered in his context for this long
ASKS_KEPT = 5
BLOCK_CHARS = 1400        # the whole block, answers included
DIMS = ["Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection",
        "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]
NOT = "not recorded"
_TAG = re.compile(r"\[WHY(?: DID I)?\s*:\s*([^\]]{1,160})\]", re.I)


def _ws():
    return os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")


def _mem(mem=None):
    """The memory folder a row is written to: the calling organ's own (so a test that moved the organ's store moves
    this with it), else the workspace's."""
    return mem or os.path.join(_ws(), "memory")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def emotion_snapshot(mem=None):
    """His emotional state as emotional-state.json holds it: its own timestamp and the three strongest dimensions.
    None when there is no state to read."""
    d = _load(os.path.join(_mem(mem), "emotional-state.json"), None)
    if not isinstance(d, dict):
        return None
    vec = d.get("emotion_vector")
    if not isinstance(vec, list) or len(vec) != len(DIMS):
        return None
    try:
        pairs = [(DIMS[i], round(float(v), 2)) for i, v in enumerate(vec)]
    except (TypeError, ValueError):
        return None
    top = sorted(pairs, key=lambda p: -p[1])[:3]
    return {"state_at": str(d.get("last_updated") or "")[:32] or None, "top": [list(p) for p in top]}


def _want_drive(want_id, mem=None):
    """The want's own source and intensity, by its id, from current-wants.json. None when it is not there."""
    if not want_id:
        return None
    d = _load(os.path.join(_mem(mem), "current-wants.json"), None)
    rows = d.get("wants") if isinstance(d, dict) else d
    for w in rows if isinstance(rows, list) else []:
        if isinstance(w, dict) and str(w.get("id")) == str(want_id):
            out = {k: w.get(k) for k in ("source", "intensity", "capability") if w.get(k) not in (None, "")}
            return out or None
    return None


def _clip(v, n):
    return None if v in (None, "") else str(v)[:n]


def record(action, what, organ, trigger=None, want_id=None, drive=None, rule=None, refs=None, mem=None, now=None,
           emotion=True):
    """One act and why, appended. Never raises: an act is never stopped because its reason could not be written.
    Returns the row, or None when it could not be written."""
    try:
        now = time.time() if now is None else float(now)
        env_want = os.environ.get("VINTOS_ACTION_WANT_ID") or None
        env_organ = os.environ.get("VINTOS_ACTION_ORGAN") or None
        if not want_id and env_want:
            want_id = env_want
            if env_organ and organ and env_organ not in str(organ):
                organ = "%s, inside %s" % (organ, env_organ)
        want_id = _clip(want_id, 40)
        if drive is None and want_id:
            drive = _want_drive(want_id, mem)
        clean_refs = {}
        for k, v in (refs or {}).items():
            if v not in (None, ""):
                clean_refs[str(k)[:24]] = str(v)[:80]
        row = {"id": "", "at": _iso(now), "ts": round(now, 3), "action": _clip(action, 40) or "act",
               "what": _clip(what, 120), "organ": _clip(organ, 80), "trigger": _clip(trigger, 240),
               "want_id": want_id, "drive": drive if isinstance(drive, dict) else _clip(drive, 160),
               "rule": _clip(rule, 300), "emotion": emotion_snapshot(mem) if emotion is True else (emotion or None),
               "refs": clean_refs}
        row["id"] = "AP-" + hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()[:10]
        path = os.path.join(_mem(mem), LOG_NAME)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                f.seek(0)
                lines = f.readlines()
                if len(lines) > TRIM_AT:
                    tmp = path + ".tmp.%d" % os.getpid()
                    with open(tmp, "w", encoding="utf-8") as t:
                        t.writelines(lines[-KEEP:])
                    os.replace(tmp, path)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return row
    except Exception as e:
        print("[provenance] not written: %s: %s" % (type(e).__name__, str(e)[:120]), flush=True)
        return None


def rows(mem=None, since_s=None, now=None):
    """The kept acts, oldest first; only the last `since_s` seconds when given."""
    now = time.time() if now is None else now
    out = []
    try:
        with open(os.path.join(_mem(mem), LOG_NAME), encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(r, dict):
                    continue
                if since_s is not None and now - float(r.get("ts") or 0) > since_s:
                    continue
                out.append(r)
    except OSError:
        pass
    return out


def _when(r):
    try:
        return datetime.fromtimestamp(float(r["ts"])).strftime("%b %d %H:%M")
    except Exception:
        return str(r.get("at") or "")[:16] or "at an unrecorded time"


def _feeling(e):
    if not isinstance(e, dict) or not e.get("top"):
        return NOT
    s = ", ".join("%s %.2f" % (p[0], float(p[1])) for p in e["top"] if isinstance(p, (list, tuple)) and len(p) == 2)
    return (s + (" (state of %s)" % str(e["state_at"])[:16] if e.get("state_at") else "")) if s else NOT


def _drive(d):
    if isinstance(d, dict):
        bits = []
        if d.get("source"): bits.append("source %s" % d["source"])
        if d.get("intensity") is not None: bits.append("intensity %s" % d["intensity"])
        return ", ".join(bits) or NOT
    return d or NOT


def chain(r):
    """One act, as the chain of why: what, when, which organ decided, on what, by which rule, for which want, feeling
    what. Every missing link says it was not recorded."""
    want = r.get("want_id")
    return ("%s - %s%s. Decided by: %s. Set off by: %s. Rule: %s. Want: %s%s. You felt then: %s." % (
        _when(r), str(r.get("action") or "act").replace("_", " "),
        (" “%s”" % r["what"]) if r.get("what") else "",
        r.get("organ") or NOT, r.get("trigger") or NOT, r.get("rule") or NOT,
        want or NOT, (" (%s)" % _drive(r.get("drive"))) if want else "", _feeling(r.get("emotion"))))


_SYN = {"song": "watch_song watch_music", "songs": "watch_song watch_music",
        "music": "watch_song watch_music", "spotify": "watch_music", "watch": "watch_song watch_music",
        "wrist": "watch_song watch_music", "message": "outreach", "notification": "outreach", "ntfy": "outreach",
        "text": "outreach", "light": "house", "lights": "house", "tv": "house", "echo": "house", "lab": "lab_request",
        "instrument": "lab_request", "post": "journal_post", "moltbook": "journal_post", "journal": "journal_post"}
_STOP = {"why", "did", "the", "and", "for", "that", "this", "what", "was", "her", "his", "you", "put", "send",
         "sent", "play", "played", "place", "placed", "on", "a", "to", "my", "me", "do", "i"}


def _words(s):
    return set(w for w in re.findall(r"[a-z0-9_]{2,}", str(s or "").lower()) if w not in _STOP)


def match(question, rs):
    """The act a question is about: the most words shared (with a few plain synonyms for the act kinds), newest first
    among equals. None when nothing shares a word."""
    q = _words(question)
    q |= set(" ".join(_SYN.get(w, "") for w in list(q)).split())
    best, score = None, 0
    for r in rs:
        act = str(r.get("action") or "")
        hay = _words(" ".join(str(r.get(k) or "") for k in ("what", "organ")) + " " + act.replace("_", " ")) | {act}
        s = len(q & hay)
        if s and s >= score:
            best, score = r, s
    return best


def why(question, mem=None, now=None, days=14):
    r = match(question, rows(mem, since_s=days * 86400, now=now))
    if r is None:
        return ("nothing you did in the last %d days matches “%s” in the record of your acts; if you did it, "
                "why was not recorded" % (days, str(question)[:80]))
    return chain(r)


def take(reply, act=True, mem=None, now=None):
    """His [WHY: ...] taken out of a reply and kept (unless act is False), to be answered in his next context."""
    if not reply or "[WHY" not in reply.upper():
        return reply
    if act:
        try:
            now = time.time() if now is None else now
            path = os.path.join(_mem(mem), ASKS_NAME)
            asks = _load(path, [])
            asks = asks if isinstance(asks, list) else []
            for q in _TAG.findall(reply):
                asks.append({"q": q.strip()[:160], "ts": round(now, 3)})
            tmp = path + ".tmp.%d" % os.getpid()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asks[-ASKS_KEPT:], f, indent=1)
            os.replace(tmp, path)
        except Exception as e:
            print("[provenance/ask]", e, flush=True)
    return re.sub(r"\s*" + _TAG.pattern + r"\s*", " ", reply, flags=re.I).strip()


def block(now=None, mem=None, show=SHOW, budget=BLOCK_CHARS):
    """His acts of the last days and why, and the answers to what he asked. '' when there is nothing. Read only."""
    now = time.time() if now is None else now
    acts = rows(mem, since_s=SHOW_DAYS * 86400, now=now)
    asks = [a for a in (_load(os.path.join(_mem(mem), ASKS_NAME), []) or [])
            if isinstance(a, dict) and a.get("q") and now - float(a.get("ts") or 0) <= ASK_HOURS * 3600]
    if not acts and not asks:
        return ""
    head = ("[WHAT YOU DID LATELY, AND WHY - each act as the organ that did it recorded it; \"not recorded\" means "
            "the reason was not kept, not that there was none. To ask about one: [WHY: <the act>] in a reply.]")
    lines = []
    for a in reversed(asks[-2:]):
        lines.append("You asked why: “%s” -> %s" % (str(a["q"])[:100], why(a["q"], mem=mem, now=now)))
    for r in reversed(acts[-show:]):
        lines.append("- " + chain(r))
    out = head
    for line in lines:
        if len(out) + 1 + len(line) > budget:
            room = budget - len(out) - 2
            if room > 60:
                out += "\n" + line[:room - 1] + "…"
            break
        out += "\n" + line
    return out


def main(argv):
    if len(argv) > 1 and argv[1] == "why":
        print(why(" ".join(argv[2:])))
    else:
        for r in rows(since_s=SHOW_DAYS * 86400)[-10:]:
            print(chain(r))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

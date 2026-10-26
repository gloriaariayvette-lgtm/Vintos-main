#!/usr/bin/env python3
"""arrival_encounter.py - a particular song and a particular line he prepares for her next arrival in the bedroom.

Codex's design 05 (approved by Gloria, built 26 October). He already chooses three songs a day for her arrivals
(bedroom_arrival.py). This lets him also, if he wants, prepare one encounter in advance: one existing song of his, a
short line of his own for her, optionally what he is carrying when he chooses it (one of his wants or moments, only if
it is actually on record), and how long it stands. The next eligible arrival greets her with it, once.

    [ARRIVAL ENCOUNTER: song title | a line for her | carrying: want:<id> | for: 24h]

Keyed parts may come in any order (song:, line:, carrying:, for:); unkeyed parts fill song, then line. She never
sees the tag.

The authorities stay where they were. bedroom_arrival.py decides what an arrival is (the enrolled phone, the board's
distance, away and cooldown), whether she is asleep, and sends exactly what it sent before: one offer to the Watch app
(watch_presence.offer_song, its `ref` still the song's title, its id and address unchanged) and one ntfy line telling
her a song is waiting - which now carries his line. Nothing else is touched: no light, no sound, no screen.

Kept apart, and never collapsed into each other:
  authored    he chose it (the turn that chose it, the song's id, address and file hash when there is a file)
  sensor      an arrival episode: her phone came within range after being away. A phone nearby is a phone nearby.
  delivery    the song was offered to the Watch app, the ntfy line's receipt - or it failed, or was held for sleep
  client      the Watch took it, started it, played it to the end - only from what the Watch reported
              (watch-song-plays.jsonl), in whatever order it reported it
Offered is not heard, and played is not enjoyed: nothing here judges how it landed.

One encounter greets one arrival. Each arrival episode has a stable id (bedroom_arrival writes it to its state before
anything is sent); an attempt is written down as "offering" before the offer and settled after it, so a repeated
packet, a restart or a crash between the offer and its receipt cannot greet her a second time (reconcile() finds the
offer in the Watch's own ledger).

Cost: no model call, no GPU, no new device. His context gains one short line (about 40 tokens while nothing is chosen).

    python3 arrival_encounter.py show       the encounters on record, as JSON
    python3 arrival_encounter.py status     the line he is shown now
"""
import contextlib, hashlib, json, os, re, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
STORE = os.path.join(MEM, "arrival-encounters.json")
MUSIC = os.path.join(MEM, "art", "music", "music.json")
WANTS = {"current": os.path.join(MEM, "current-wants.json"), "fulfilled": os.path.join(MEM, "fulfilled-wants.json")}
MOMENTS = os.path.join(MEM, "moment-archive.json")

LINE_MAX = 140            # his line, at most
ORIGIN_MAX = 80
HOURS_DEFAULT, HOURS_MIN, HOURS_MAX = 24, 1, 48
KEEP = 30                 # encounters kept on record
REPEAT_S = 24 * 3600      # the same song with the same line again within a day is the same choice, not a new one
SHOWN_S = 24 * 3600       # how long a settled encounter stays in his line
HASH_CAP = 300 * 1024 * 1024
TAG = r"\[ARRIVAL ENCOUNTER:\s*([^\]]*)\]"
PLAY_ORDER = ("taken", "started", "finished")


def _iso(ts): return datetime.fromtimestamp(float(ts), timezone.utc).isoformat()


def _hm(ts): return datetime.fromtimestamp(float(ts)).strftime("%H:%M")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception: return default


def _atomic(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


@contextlib.contextmanager
def _locked():
    """The chat process chooses and the bedroom listener greets: one writer at a time."""
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    fd = os.open(STORE + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            import fcntl; fcntl.flock(fd, fcntl.LOCK_EX)
        except ImportError:
            pass
        data = _load(STORE, {})
        rows = [r for r in (data.get("encounters") if isinstance(data, dict) else None) or [] if isinstance(r, dict)]
        box = {"rows": rows, "dirty": False}
        yield box
        if box["dirty"]:
            _atomic(STORE, {"encounters": box["rows"][-KEEP:]})
    finally:
        os.close(fd)


def encounters():
    data = _load(STORE, {})
    return [r for r in (data.get("encounters") if isinstance(data, dict) else None) or [] if isinstance(r, dict)]


# --- what he wrote, made inert ----------------------------------------------------------------------------------------

def inert(text, limit=LINE_MAX):
    """His line as plain words: one line, no link, no tag or markup brackets, no control characters, bounded."""
    s = str(text or "")
    s = re.sub(r"(?i)\b(?:https?://|www\.)\S+", "", s)
    s = "".join(" " if (ord(c) < 32 or 0x7f <= ord(c) < 0xa0 or c in "  ") else c for c in s)
    s = re.sub(r"<[^>]{0,40}>", "", s)
    s = re.sub(r"[\[\]{}<>`*#|\\]", "", s)
    s = " ".join(s.split())
    if len(s) > limit: s = s[:limit - 1].rstrip() + "…"
    return s


def _norm(t): return " ".join("".join(c for c in str(t).lower() if c.isalnum() or c.isspace()).split())


def _song(title):
    """His song by title, from his library: the newest with a playable track. {title, url, song_id, sha256} or None."""
    log = _load(MUSIC, {})
    want = _norm(title)
    if not want: return None
    for r in reversed(log.get("generated", []) if isinstance(log, dict) else []):
        if not isinstance(r, dict) or _norm(r.get("title") or "") != want: continue
        for t in r.get("tracks") or []:
            if isinstance(t, dict) and str(t.get("audio_url") or "").startswith("http"):
                return {"title": str(r.get("title") or "A song")[:120], "url": str(t["audio_url"])[:1000],
                        "song_id": str(r.get("task_id") or t.get("suno_id") or "")[:80] or None,
                        "sha256": _file_sha(t.get("local_file"))}
    return None


def _file_sha(path):
    try:
        path = str(path or "")
        if not path or not os.path.isfile(path) or os.path.getsize(path) > HASH_CAP: return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _standing_ok(rec):
    try:
        import evidence_view as EV
        return EV.standing(rec) == EV.ELIGIBLE
    except Exception:
        return False


def origin(ref):
    """What he is carrying, only when it is on record: one of his wants (by id, or words that name exactly one of his
    current wants) or one of his moments (by its key). (record, None) or (None, what he wrote)."""
    raw = str(ref or "").strip().strip("\"'“”")
    if not raw: return None, None
    kind, _, key = raw.partition(":")
    kind, key = kind.strip().lower(), key.strip()
    if kind == "moment" and key:
        arch = _load(MOMENTS, {})
        mom = arch.get("moments") if isinstance(arch, dict) else None
        if isinstance(mom, dict) and isinstance(mom.get(key), dict) and _standing_ok(mom[key]):
            return {"kind": "moment", "id": key[:120]}, None
        return None, inert(raw, ORIGIN_MAX)
    for store, path in WANTS.items():
        rows = _load(path, [])
        rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
        if kind == "want" and key:
            hit = [r for r in rows if str(r.get("id") or "") == key]
        elif store == "current" and len(raw) >= 12:
            hit = [r for r in rows if _norm(raw) and _norm(raw) in _norm(r.get("want") or "")]
        else:
            hit = []
        if len(hit) == 1 and _standing_ok(hit[0]):
            w = hit[0]
            return {"kind": "want", "id": str(w.get("id") or "")[:80], "store": store,
                    "text": inert(w.get("want"), 80)}, None
    return None, inert(raw, ORIGIN_MAX)


# --- his choice -------------------------------------------------------------------------------------------------------

def parse(body):
    """{song, line, carrying, hours} from the body of one tag."""
    out = {"song": "", "line": "", "carrying": "", "hours": None}
    loose = []
    for part in re.split(r"\s*\|\s*", str(body or "")):
        if not part.strip(): continue
        m = re.match(r"(?i)\s*(song|line|carrying|origin|for|hours)\s*:\s*(.*)$", part, re.S)
        if m:
            k = m.group(1).lower(); k = {"origin": "carrying", "for": "hours"}.get(k, k)
            out[k] = m.group(2).strip()
        else:
            loose.append(part.strip())
    for k in ("song", "line"):
        if not out[k] and loose: out[k] = loose.pop(0)
    if not out["carrying"] and loose and re.match(r"(?i)(want|moment):", loose[0]): out["carrying"] = loose.pop(0)
    if out["hours"] is None and loose and re.match(r"^\d+\s*h?", loose[0]): out["hours"] = loose.pop(0)
    try:
        h = int(re.match(r"\s*(\d+)", str(out["hours"])).group(1)) if out["hours"] else HOURS_DEFAULT
    except Exception:
        h = HOURS_DEFAULT
    out["hours"] = max(HOURS_MIN, min(HOURS_MAX, h))
    return out


def choose(body, now=None, turn_id=""):
    """One encounter from his tag, retained. {"kept": encounter or None, "why": "..."}."""
    now = time.time() if now is None else float(now)
    p = parse(body)
    line = inert(p["line"])
    if not line: return {"kept": None, "why": "no line for her"}
    song = _song(p["song"])
    if not song: return {"kept": None, "why": "not a song in your library with a track: %s" % inert(p["song"], 80)}
    org, missed = origin(p["carrying"])
    if turn_id:
        sel, src = str(turn_id)[:80], "turn"
    else:
        sel, src = "reply-" + hashlib.sha256(("%s|%s" % (body, int(now))).encode()).hexdigest()[:12], "reply-digest"
    with _locked() as box:
        for r in box["rows"]:
            if (r.get("song") or {}).get("url") == song["url"] and r.get("dedication") == line \
                    and now - float(r.get("chosen_ts") or 0) < REPEAT_S:
                return {"kept": None, "why": "already chosen", "encounter_id": r.get("encounter_id")}
        for r in box["rows"]:
            if r.get("state") == "chosen":
                r["state"] = "replaced"; r["replaced_ts"] = now
        enc = {"encounter_id": "enc-" + hashlib.sha256(("%s|%s|%s" % (sel, song["url"], now)).encode()).hexdigest()[:12],
               "selection_turn_id": sel, "turn_id_source": src, "chosen_at": _iso(now), "chosen_ts": now,
               "song": song, "dedication": line, "origin": org,
               "valid_from_ts": now, "valid_until_ts": now + 3600 * p["hours"], "state": "chosen",
               "attempts": [], "history": []}
        if missed: enc["origin_unlinked"] = missed
        box["rows"].append(enc); box["dirty"] = True
    return {"kept": enc, "why": ""}


def take(reply, now=None, act=True, turn_id=""):
    """His [ARRIVAL ENCOUNTER: ...] in a reply: chosen (unless act is False) and taken out of the words."""
    if not reply or "[ARRIVAL ENCOUNTER" not in reply.upper(): return reply
    if act:
        for body in re.findall(TAG, reply, re.I)[:1]:      # one encounter at a time
            try:
                got = choose(body, now, turn_id)
                k = got.get("kept")
                print("[bedroom/encounter] %s" % (("kept: “%s” until %s" % (k["song"]["title"], _hm(k["valid_until_ts"])))
                                                   if k else "not kept: " + got.get("why", "")), flush=True)
            except Exception as e:
                print("[bedroom/encounter]", type(e).__name__, str(e)[:160], flush=True)
    return re.sub(r"\s*" + TAG + r"\s*", " ", reply, flags=re.I).strip()


# --- an arrival -------------------------------------------------------------------------------------------------------

def _offer_seen(enc, attempt):
    """The Watch ledger's own row of this attempt's offer, if the offer happened."""
    try:
        import watch_presence as W
        for line in open(W.PLAYS, encoding="utf-8"):
            try: r = json.loads(line)
            except ValueError: continue
            if isinstance(r, dict) and r.get("event") == "offered" and float(r.get("ts") or 0) >= float(attempt.get("ts") or 0) - 1 \
                    and str(r.get("media_url") or "") == str((enc.get("song") or {}).get("url") or "")[:1000]:
                return r
    except (OSError, ImportError):
        pass
    return None


def _reconcile_rows(rows, now):
    changed = False
    for enc in rows:
        for a in enc.get("attempts") or []:
            if a.get("state") != "offering": continue
            seen = _offer_seen(enc, a)
            if seen:
                a.update(state="offered", song_offer_id=seen.get("song_id") or "", recovered=True,
                         settled_ts=now, why="the offer is in the Watch's ledger; its receipt was not written down")
                enc["state"] = "offered"
            else:
                a.update(state="interrupted", settled_ts=now, why="stopped before the offer was made")
                if enc.get("state") == "offering": enc["state"] = "chosen"
            changed = True
    return changed


def reconcile(now=None):
    """After a crash or restart: an attempt left "offering" is settled from the Watch's own ledger."""
    now = time.time() if now is None else float(now)
    with _locked() as box:
        if _reconcile_rows(box["rows"], now): box["dirty"] = True


def _expire(rows, now):
    changed = False
    for enc in rows:
        if enc.get("state") == "chosen" and now > float(enc.get("valid_until_ts") or 0):
            enc["state"] = "expired"; enc["expired_ts"] = float(enc.get("valid_until_ts") or now); changed = True
    return changed


def _active(rows):
    return next((r for r in reversed(rows) if r.get("state") == "chosen"), None)


def for_arrival(episode_id, now=None, library_urls=()):
    """The encounter that greets this arrival, with the attempt written down before anything is sent; else None.

    Called by bedroom_arrival after its own checks (enrolled phone, distance, away, cooldown, sleep) have passed.
    An episode that already has an attempt never gets a second one."""
    now = time.time() if now is None else float(now)
    episode_id = str(episode_id or "")
    if not episode_id: return None
    with _locked() as box:
        rows = box["rows"]
        if _reconcile_rows(rows, now): box["dirty"] = True
        if _expire(rows, now): box["dirty"] = True
        if any(a.get("episode_id") == episode_id for r in rows for a in r.get("attempts") or []):
            return None
        enc = _active(rows)
        if not enc: return None
        url = (enc.get("song") or {}).get("url")
        if url not in set(library_urls or ()):
            enc["state"] = "failed"; box["dirty"] = True
            enc["attempts"].append({"episode_id": episode_id, "at": _iso(now), "ts": now, "state": "failed",
                                    "why": "the song is no longer in his library"})
            return None
        enc["attempts"].append({"episode_id": episode_id, "at": _iso(now), "ts": now, "state": "offering"})
        enc["state"] = "offering"; box["dirty"] = True
        return {"encounter_id": enc["encounter_id"], "episode_id": episode_id, "title": enc["song"]["title"],
                "url": url, "dedication": enc.get("dedication") or ""}


def settle(encounter_id, episode_id, got, now=None):
    """What the arrival's one send did, against the attempt it was made for."""
    now = time.time() if now is None else float(now)
    got = got or {}
    sent = got.get("state") in ("sent", "acknowledged") and got.get("song_id")
    with _locked() as box:
        for enc in box["rows"]:
            if enc.get("encounter_id") != encounter_id: continue
            for a in enc.get("attempts") or []:
                if a.get("episode_id") != episode_id or a.get("state") != "offering": continue
                a.update(state="offered" if sent else "failed", settled_ts=now, song_offer_id=got.get("song_id") or "",
                         ntfy=got.get("ntfy"), **({"push": got["push"]} if "push" in got else {}))
                if not sent: a["why"] = str(got.get("why") or "not offered")[:200]
                enc["state"] = "offered" if sent else "failed"
                box["dirty"] = True
                return True
    return False


def held(episode_id, why, now=None):
    """An arrival that could not be greeted (asleep, cooldown): written beside the chosen encounter, which waits on."""
    now = time.time() if now is None else float(now)
    with _locked() as box:
        if _expire(box["rows"], now): box["dirty"] = True
        enc = _active(box["rows"])
        if not enc: return False
        h = enc.setdefault("history", [])
        if any(x.get("episode_id") == episode_id for x in h): return False
        h.append({"episode_id": str(episode_id or ""), "at": _iso(now), "ts": now,
                  "event": "held for sleep" if why == "asleep" else "held: %s" % str(why)[:40]})
        del h[:-10]
        box["dirty"] = True
        return True


# --- what he is told --------------------------------------------------------------------------------------------------

def playback(enc):
    """{event: ts} the Watch reported for this encounter's offer. Only the Watch's own reports, in their own order."""
    ids = {a.get("song_offer_id") for a in enc.get("attempts") or [] if a.get("state") == "offered" and a.get("song_offer_id")}
    offered = [float(a.get("settled_ts") or a.get("ts") or 0) for a in enc.get("attempts") or [] if a.get("state") == "offered"]
    if not ids or not offered: return {}
    url = str((enc.get("song") or {}).get("url") or "")[:1000]
    since = min(offered) - 5
    out = {}
    try:
        import watch_presence as W
        for line in open(W.PLAYS, encoding="utf-8"):
            try: r = json.loads(line)
            except ValueError: continue
            if not isinstance(r, dict) or r.get("event") not in PLAY_ORDER: continue
            ts = float(r.get("ts") or 0)
            mine = r.get("song_id") in ids or (not r.get("song_id") and ts >= since and ts - since <= 12 * 3600
                                               and W._same_url(r.get("media_url"), url))
            if mine and r["event"] not in out: out[r["event"]] = ts
    except (OSError, ImportError, ValueError, TypeError):
        pass
    return out


def history(enc):
    """The encounter's chain, each step what it is: authored, sensor/hold, delivery, client report."""
    out = [{"kind": "authored", "event": "chosen", "ts": enc.get("chosen_ts")}]
    for h in enc.get("history") or []:
        out.append({"kind": "sensor", "event": h.get("event"), "ts": h.get("ts"), "episode_id": h.get("episode_id")})
    for a in enc.get("attempts") or []:
        out.append({"kind": "delivery", "event": a.get("state"), "ts": a.get("settled_ts") or a.get("ts"),
                    "episode_id": a.get("episode_id"), **({"why": a["why"]} if a.get("why") else {})})
    if enc.get("state") == "expired":
        out.append({"kind": "authored", "event": "chosen but expired", "ts": enc.get("expired_ts")})
    for ev, ts in sorted(playback(enc).items(), key=lambda kv: kv[1]):
        out.append({"kind": "client", "event": ev, "ts": ts})
    return out


INVITE = (" If you want, prepare one encounter for her next arrival: [ARRIVAL ENCOUNTER: song title | your line for her "
          "| carrying: want:<id> | for: 24h]; your line goes in the note that tells her the song is waiting.")


def context_line(now=None):
    """One short clause for the bedroom line: his encounter and what became of it, or how to make one."""
    now = time.time() if now is None else float(now)
    rows = encounters()
    _expire(rows, now)          # how it reads now; the store is settled by the listener
    enc = next((r for r in reversed(rows) if r.get("state") in ("chosen", "offering")), None)
    if enc is None:
        enc = next((r for r in reversed(rows) if r.get("state") in ("offered", "failed", "expired")
                    and now - float(max([a.get("settled_ts") or a.get("ts") or 0 for a in r.get("attempts") or []]
                                        + [r.get("expired_ts") or 0, r.get("chosen_ts") or 0])) <= SHOWN_S), None)
    if enc is None: return INVITE
    title = str((enc.get("song") or {}).get("title") or "")[:50]
    line = str(enc.get("dedication") or "")[:LINE_MAX]
    carrying = ""
    o = enc.get("origin") or {}
    if o.get("kind") == "want": carrying = " (carrying your want “%s”)" % str(o.get("text") or o.get("id"))[:60]
    elif o.get("kind") == "moment": carrying = " (carrying moment %s)" % str(o.get("id"))[:40]
    elif enc.get("origin_unlinked"): carrying = " (what you named as carried is not on record, so nothing is linked)"
    head = " Your encounter: “%s” with your line “%s”%s" % (title, line, carrying)
    st = enc.get("state")
    if st in ("chosen", "offering"):
        waits = enc.get("history") or []
        tail = "; waiting for her next arrival, until %s" % _hm(enc.get("valid_until_ts") or now)
        if waits: tail += " (an arrival at %s was not greeted: %s)" % (_hm(waits[-1]["ts"]), waits[-1].get("event"))
        return head + tail + "."
    if st == "expired":
        return head + "; it expired at %s before an arrival it could greet." % _hm(enc.get("expired_ts") or now)
    last = (enc.get("attempts") or [{}])[-1]
    if st == "failed":
        return head + "; not offered at %s (%s)." % (_hm(last.get("ts") or now), str(last.get("why") or "failed")[:80])
    parts = ["offered to her Watch at her arrival %s, your line in the note that told her (%s)"
             % (_hm(last.get("ts") or now), last.get("ntfy") or "no receipt")]
    pb = playback(enc)
    names = {"taken": "the Watch took it %s", "started": "started playing %s", "finished": "played to the end %s"}
    for ev in PLAY_ORDER:
        if ev in pb: parts.append(names[ev] % _hm(pb[ev]))
    if "started" not in pb and "finished" not in pb: parts.append("the Watch has not reported playing it")
    return head + "; " + ", ".join(parts) + ". Offered is not heard, and played is not how it landed."


def main(argv):
    if argv[:1] == ["show"]:
        print(json.dumps(encounters(), indent=2, ensure_ascii=False)); return 0
    if argv[:1] == ["status"]:
        print(context_line().strip()); return 0
    print(__doc__); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

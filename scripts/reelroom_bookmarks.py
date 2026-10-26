#!/usr/bin/env python3
"""reelroom_bookmarks.py -- a few moments of a film night kept by reference, for a later night to call back to.

Proposal 16 (Codex, 25 October; approved by Gloria). A bookmark is a pointer into one ReelRoom session's own
journal, never a recording:

  session_id      the night's journal id (``rr-...``)
  turn_ids        the journal ids of the remark and its answer (``<session>:t<n>``), as journaled
  turns           those turns' words, copied verbatim when the bookmark is made, with who said them and the
                  wall-clock time the server journaled each one (absent when the server never saw it arrive)
  player_seconds  the player's position, ONLY when the caller supplies it; never inferred from the app's
                  film timer or from minutes elapsed
  scene           optional: his own reading of a frame (the text the frame read wrote at the time), always
                  labelled as his interpretation. No image, no frame bytes, no screen material is kept.
  by              "gloria" (her mark from the app) or "vintos" (his own [KEEP] in a ReelRoom reply)

A later night's ReelRoom prompt carries ``callback_block``: at most two bookmarks from earlier nights, the
words quoted exactly as they were said, so he can return to the precise moment or set two moments side by side.

No model is called. Nothing is sent. Stored at ``memory/reelroom/bookmarks.json``; a few per night (MAX_PER_SESSION),
and nothing is ever trimmed from it.

CLI (read-only):  python3 reelroom_bookmarks.py list | block
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
ROOM_DIR = os.path.join(MEMORY, "reelroom")
STORE = os.path.join(ROOM_DIR, "bookmarks.json")
JOURNAL = os.path.join(ROOM_DIR, "live-session.json")

MAX_PER_SESSION = 3          # "a few timestamped references", not a transcript of the night
QUOTE_CHARS = 1200           # what is kept of one turn's words; longer turns are kept to this and marked
CALLBACK_QUOTE_CHARS = 280   # what one quote may take in a later prompt; cut quotes say so
CALLBACK_LIMIT = 2           # two moments: enough to return to one, or to juxtapose two
SCENE_CHARS = 240
KEEP_TAG = "[KEEP]"


def _load(path: str, default):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, type(default)) else default
    except Exception:
        return default


def bookmarks() -> List[Dict[str, Any]]:
    return [b for b in _load(STORE, []) if isinstance(b, dict)]


def _turn(m: Dict[str, Any]) -> Dict[str, Any]:
    words = str(m.get("content") or "")
    out = {"id": str(m.get("id") or ""), "speaker": "gloria" if m.get("role") == "user" else "vintos",
           "words": words[:QUOTE_CHARS]}
    if len(words) > QUOTE_CHARS:
        out["cut"] = True
    if m.get("at") is not None:
        try:
            out["at"] = float(m["at"])
        except (TypeError, ValueError):
            pass
    return out


def _exchange(hist: List[Dict[str, Any]], i: int) -> List[Dict[str, Any]]:
    """The marked turn with its partner: her remark and his answer to it, or his line and her answer to it."""
    m = hist[i]
    if m.get("role") == "assistant" and i > 0 and hist[i - 1].get("role") == "user":
        return [hist[i - 1], m]
    if m.get("role") == "user" and i + 1 < len(hist) and hist[i + 1].get("role") == "assistant":
        return [m, hist[i + 1]]
    return [m]


def _player_seconds(value) -> Optional[int]:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v < 0 or v > 24 * 3600:
        return None
    return int(v)


def mark(turn_id: str = "latest", by: str = "gloria", scene_index: Optional[int] = None,
         latest_scene: bool = False, player_seconds=None, journal: Optional[Dict[str, Any]] = None,
         now: Optional[float] = None) -> Dict[str, Any]:
    """Keep one moment of tonight's journal. ``turn_id`` is a journal turn id, or "latest" for the newest turn
    (his [KEEP] marks the exchange his reply belongs to). ``scene_index`` names one session_map event; with
    ``latest_scene`` the newest frame read is attached instead. Returns {"ok": bool, ...}; never raises on bad
    input."""
    from store_guard import transaction, save_json
    now = now or time.time()
    j = journal if journal is not None else _load(JOURNAL, {})
    sid = str(j.get("session_id") or "")
    hist = [m for m in (j.get("chat_history") or []) if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
    if not sid or not hist:
        return {"ok": False, "reason": "no film night is open"}
    if turn_id in (None, "", "latest"):
        idx = len(hist) - 1
    else:
        idx = next((i for i, m in enumerate(hist) if m.get("id") == turn_id), -1)
        if idx < 0:
            return {"ok": False, "reason": "no such turn tonight"}
    pair = _exchange(hist, idx)
    if any(not m.get("id") for m in pair):
        return {"ok": False, "reason": "the turn has no journal id"}
    turns = [_turn(m) for m in pair]
    scene, scene_at = None, None
    events = [e for e in (j.get("session_map") or []) if isinstance(e, dict)]
    if scene_index is not None:
        try:
            ev = events[int(scene_index)]
        except (TypeError, ValueError, IndexError):
            return {"ok": False, "reason": "no such scene tonight"}
        desc = str(ev.get("visual_description") or "").strip()
        if not desc:
            return {"ok": False, "reason": "that event has no frame reading"}
        scene, scene_at = desc, int(scene_index)
    elif latest_scene:
        scene_at = next((i for i in range(len(events) - 1, -1, -1)
                         if str(events[i].get("visual_description") or "").strip()), None)
        scene = str(events[scene_at].get("visual_description")).strip() if scene_at is not None else None
    row: Dict[str, Any] = {
        "id": "bm-%d" % int(now * 1000),
        "session_id": sid,
        "film": str(j.get("film_title") or ""),
        "year": str(j.get("film_year") or ""),
        "turn_ids": [t["id"] for t in turns],
        "turns": turns,
        "by": "vintos" if by == "vintos" else "gloria",
        "kept_at": now,
    }
    ps = _player_seconds(player_seconds)
    if ps is not None:
        row["player_seconds"] = ps
    if scene:
        row["scene"] = {"reading": scene[:SCENE_CHARS], "whose": "his reading of a frame"}
        if scene_at is not None:
            row["scene"]["index"] = scene_at     # its place in the night's map: joins the frame's media-index row
    os.makedirs(ROOM_DIR, exist_ok=True)
    with transaction(STORE):
        rows = bookmarks()
        same = next((b for b in rows if b.get("session_id") == sid and b.get("turn_ids") == row["turn_ids"]), None)
        if same:
            return {"ok": True, "already": True, "bookmark": same}
        if sum(1 for b in rows if b.get("session_id") == sid) >= MAX_PER_SESSION:
            return {"ok": False, "reason": "tonight already has %d bookmarks" % MAX_PER_SESSION}
        rows.append(row)
        save_json(STORE, rows)
    return {"ok": True, "bookmark": row}


def take_keep_tag(reply: str) -> tuple:
    """(reply without [KEEP], whether he wrote it). The tag is his; it is never shown or spoken."""
    import re
    text = str(reply or "")
    if not re.search(r"\[KEEP\]", text, re.I):
        return text, False
    return re.sub(r"\s*\[KEEP\]\s*", " ", text, flags=re.I).strip(), True


def keep_line() -> str:
    """What the ReelRoom prompt tells him about [KEEP]."""
    return ("If a moment between you two tonight is one you want to be able to come back to on a later film "
            "night, write [KEEP] anywhere in your reply: it keeps her words and yours from this exchange exactly "
            "as said. She never sees or hears the tag. Keep few - at most %d a night." % MAX_PER_SESSION)


def _clock(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def _quote(words: str, cut: bool) -> str:
    w = " ".join(str(words or "").split())
    if len(w) > CALLBACK_QUOTE_CHARS:
        return '"%s..." (cut here; the rest was said too)' % w[:CALLBACK_QUOTE_CHARS].rstrip()
    return '"%s"%s' % (w, " (cut here; the rest was said too)" if cut else "")


def _player(ps: int) -> str:
    h, rem = divmod(int(ps), 3600)
    m, s = divmod(rem, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


def callback_block(exclude_session: str = "", limit: int = CALLBACK_LIMIT) -> str:
    """Up to ``limit`` bookmarks from earlier nights, newest first, quoted exactly. "" when there are none."""
    rows = [b for b in bookmarks() if b.get("session_id") and b.get("session_id") != exclude_session
            and b.get("turns")]
    if not rows:
        return ""
    rows.sort(key=lambda b: float(b.get("kept_at") or 0), reverse=True)
    lines = ["MOMENTS KEPT FROM EARLIER FILM NIGHTS (bookmarks; the quoted words are exactly what was said. You may "
             "return to one, or set two side by side, if the moment calls for it - not as a recap):"]
    for b in rows[:max(0, int(limit))]:
        film = b.get("film") or "a film"
        if b.get("year"):
            film += " (%s)" % b["year"]
        head = "- %s, kept by %s" % (film, "you" if b.get("by") == "vintos" else "Gloria")
        first_at = next((t.get("at") for t in b["turns"] if t.get("at") is not None), None)
        if first_at is not None:
            head += ", said %s" % _clock(float(first_at))
        if b.get("player_seconds") is not None:
            head += ", at %s on the player" % _player(b["player_seconds"])
        lines.append(head + ":")
        for t in b["turns"]:
            who = "Gloria said" if t.get("speaker") == "gloria" else "You said"
            lines.append("    %s: %s" % (who, _quote(t.get("words"), bool(t.get("cut")))))
        sc = b.get("scene") or {}
        if sc.get("reading"):
            lines.append("    What you made of the screen then (your own reading of a frame, not a record of the "
                         "film): %s" % " ".join(str(sc["reading"]).split()))
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "list"
    if cmd == "list":
        for b in bookmarks():
            print("%s  %s  %s  by %s  turns %s%s" % (
                b.get("id"), _clock(float(b.get("kept_at") or 0)), b.get("film") or "?", b.get("by"),
                ",".join(b.get("turn_ids") or []),
                ("  player %s" % _player(b["player_seconds"])) if b.get("player_seconds") is not None else ""))
        return 0
    if cmd == "block":
        print(callback_block() or "(no bookmarks yet)")
        return 0
    print(__doc__.strip().splitlines()[-1])
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

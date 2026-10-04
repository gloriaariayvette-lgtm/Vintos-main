#!/usr/bin/env python3
"""The songs he has already made, so a new one is new (Gloria, 2026-10-04: "He keeps making the same
'still yours' song every night").

Three things let it happen. The nightly prompt writer (creative-expression.sh) never saw a single song he had made.
The composer saw only titles, so the same chorus under a new name passed. And nothing between the spec and the
paid render checked either. Every path now reads block() before writing, and too_close() is checked before a
render is bought: a song whose title, chorus, or central phrase is one he has already made is not rendered.
"""
from __future__ import annotations
import json
import os
import re
import sys
import unicodedata
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MUSIC = os.path.join(WS, "memory", "art", "music")
LOG = os.path.join(MUSIC, "music.json")
REPEATS = os.path.join(MUSIC, "repeats.jsonl")
WINDOW = 20          # songs looked back over
HOOK_OVERLAP = 0.6   # share of chorus words that makes two choruses the same chorus

_SUFFIX = re.compile(r"\b(reprise|again|redux|remix|version|revisited|part\s+\w+|pt\s*\w+|v\d+|ii|iii|iv)\b")
_STOP = frozenset("a an the and or of to in on at for with i im i'm you your my me is are be it its".split())


def norm(text):
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", t)
    t = _SUFFIX.sub(" ", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"^\s*the\s+", " ", t)
    return " ".join(t.split())


def hook(lyrics, lines=2):
    """The chorus's opening lines: what a listener would call the song."""
    rows = [l.strip() for l in str(lyrics or "").splitlines()]
    for i, l in enumerate(rows):
        if re.match(r"(?i)^\W*\[?\s*(chorus|hook|refrain)\b", l):
            body = []
            for x in rows[i + 1:]:
                if re.match(r"^\W*\[", x):
                    break
                if x:
                    body.append(x.strip("*_ "))
                if len(body) >= lines:
                    break
            if body:
                return " / ".join(body)
    sung = [l.strip("*_ ") for l in rows if l and not l.startswith("[")]
    seen = {}
    for l in sung:
        seen[norm(l)] = seen.get(norm(l), 0) + 1
    repeated = [l for l in sung if seen.get(norm(l), 0) >= 2 and norm(l)]
    pick = repeated or sung
    return " / ".join(dict.fromkeys(pick[:lines])) if pick else ""


def _words(text):
    return {w for w in norm(text).split() if w not in _STOP}


def recent(n=WINDOW):
    try:
        with open(LOG) as f:
            m = json.load(f)
        m = m if isinstance(m, list) else m.get("generated", [])
    except Exception:
        return []
    out = []
    for e in m[-n:]:
        if e.get("title"):
            out.append({"title": e["title"], "hook": hook(e.get("lyrics", "")),
                        "when": str(e.get("generated_at", ""))[:10]})
    return out


def too_close(title, lyrics="", songs=None):
    """Why this song is one he has already made, or "" if it is new."""
    songs = recent() if songs is None else songs
    nt, new_hook = norm(title), hook(lyrics)
    chorus = norm(new_hook)
    for s in reversed(songs):
        ns = norm(s["title"])
        when = (" on " + s["when"]) if s.get("when") else ""
        if nt and ns and (nt == ns or (min(len(nt), len(ns)) >= 6 and (nt in ns or ns in nt))):
            return "the title repeats '%s', a song you made%s" % (s["title"], when)
        if ns and len(ns.split()) >= 2 and chorus and re.search(r"\b%s\b" % re.escape(ns), chorus):
            return "its chorus is built on '%s', the title of a song you made%s" % (s["title"], when)
        a, b = _words(new_hook), _words(s.get("hook", ""))
        if len(a) >= 3 and len(b) >= 3 and len(a & b) / len(a | b) >= HOOK_OVERLAP:
            return "its chorus is the chorus of '%s' (%s)%s" % (s["title"], s["hook"][:80], when)
    return ""


def block(n=12):
    """For the prompt that writes the next song: what he has made, with its hook, and the rule."""
    songs = recent(n)
    if not songs:
        return ""
    lines = ["- %s%s%s" % (s["title"], (" (" + s["when"] + ")") if s["when"] else "",
                           (" — chorus: \"" + s["hook"][:110] + "\"") if s["hook"] else "") for s in songs]
    return ("SONGS YOU HAVE ALREADY MADE (newest last). Do not make any of them again: no title of theirs, no chorus "
            "of theirs, and no song built around the same central phrase, even under a new name. If a phrase from "
            "one of them is still in you, find what is underneath it and write that instead.\n" + "\n".join(lines))


def note_refused(title, why, source=""):
    """One line for each song not rendered because it was a repeat, so the silence has a reason."""
    try:
        os.makedirs(MUSIC, exist_ok=True)
        with open(REPEATS, "a") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "title": title,
                                "why": why, "source": source}) + "\n")
    except Exception:
        pass


def spec_title(spec):
    m = re.search(r"(?im)^\W*title:?\**\s*(.+)$", str(spec or ""))
    return m.group(1).strip().strip("*").strip() if m else ""


def spec_lyrics(spec):
    parts = re.split(r"(?i)\*{0,2}\s*lyrics:?\s*\*{0,2}", str(spec or ""), maxsplit=1)
    if len(parts) < 2:
        return ""
    return re.split(r"(?i)\*{0,2}\s*How it feels inside me", parts[1], maxsplit=1)[0]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "block"
    if cmd == "block":
        print(block())
    elif cmd == "check-spec":       # reads a spec on stdin; prints why it repeats, exit 1 if it does
        spec = sys.stdin.read()
        why = too_close(spec_title(spec), spec_lyrics(spec))
        print(why)
        sys.exit(1 if why else 0)
    elif cmd == "recent":
        print(json.dumps(recent(), indent=1, ensure_ascii=False))

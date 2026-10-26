#!/usr/bin/env python3
"""outreach_postcards.py: an outreach may carry one thing he already made, when he chooses to send it with his words.

Proposal 06 (25 October), built 26 October. vintos-initiate.sh asks this file:

    offer                    prints "key<TAB>url<TAB>about" for the one piece he may send with this outreach, else nothing
    mark key offered|chosen|sent|failed [outreach_id]    what became of that offer

What may be offered (all must hold):
    - a painting he asked for himself (WANT_ACT / PROJECTOR_PRESENCE) and, having looked at it, kept
      (image_sight's verdict "keep"); never taken down, never a dream-born image he did not judge;
    - or a work he revealed from the Atelier by his own act, whose bytes were verified at the reveal and whose file
      is on a public shelf with the same digest. Sealed Atelier work is never read here: only the reveal ledger
      (what he already let out) and the public shelf directories;
    - the file is on the shelf, is a real file of its medium, and has a name the shelf route serves;
    - made within MAX_AGE_DAYS; never already sent to her (its own record's delivery/shared, or a postcard here);
    - offered fewer than MAX_OFFERS times: an offer he lets pass is his answer, and is not pressed on him.
No postcard is offered within POSTCARD_GAP_S of the last one sent. The outreach send caps are the caller's, unchanged.

Being offered is not being sent. He chooses in the outreach turn he already has (no new model call): his message
goes out as he wrote it, and the piece goes with it only when he asked for that. A send is "sent" only on a sent
receipt from the delivery path.
"""
import json
import os
import re
import sys
import time
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
ART = os.path.join(MEMORY, "art")
GALLERY = os.path.join(ART, "gallery.json")
REVEALS = os.path.join(MEMORY, "atelier-reveals.json")
STATE = os.path.join(MEMORY, "outreach-postcards.json")
SERVE_BASE = os.environ.get("VINTOS_SERVE_BASE", "http://100.72.225.119:8500")
MAX_AGE_DAYS = 30
MAX_OFFERS = 2
POSTCARD_GAP_S = 24 * 3600
SIGHTED = ("WANT_ACT", "PROJECTOR_PRESENCE")

# The shelf routes that serve a file to her phone, and the names each one accepts (bin/server_domains/).
SHELVES = {
    "image": (ART, "/api/art/painting/", re.compile(r"^[\w.\-]+\.(?:png|jpe?g)$")),
    "audio": (os.path.join(ART, "music"), "/api/art/music/stream/", re.compile(r"^[\w.\-]+\.(?:mp3|wav)$")),
}
WORD = {"image": "a picture", "audio": "a piece of music"}


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _ts(value):
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _one_line(text, n=220):
    return " ".join(str(text or "").split())[:n]


def _manifest():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import artifact_manifest
    return artifact_manifest


def shelf_link(medium, name):
    """(path, url) for a file on a public shelf, or None when it is not there, not real, or not servable."""
    shelf = SHELVES.get(medium)
    name = str(name or "")
    if not shelf or name != os.path.basename(name) or not shelf[2].match(name):
        return None
    path = os.path.join(shelf[0], name)
    if not (_manifest().validate_file(path, medium) or {}).get("ok"):
        return None
    return path, SERVE_BASE.rstrip("/") + shelf[1] + name


def _state():
    s = _load(STATE, {})
    if not isinstance(s, dict):
        s = {}
    s.setdefault("pieces", {})
    return s


def _already_out(rec):
    d = rec.get("delivery") if isinstance(rec.get("delivery"), dict) else {}
    return bool(rec.get("shared")) or d.get("state") in ("sent", "acknowledged")


def candidates(now=None):
    """Every piece that may be offered, newest first: [(made_ts, key, medium, path, url, about)]."""
    now = now or time.time()
    out = []
    gallery = _load(GALLERY, [])
    for rec in gallery if isinstance(gallery, list) else []:
        if not isinstance(rec, dict) or rec.get("taken_down") or rec.get("image_class") not in SIGHTED:
            continue
        if rec.get("verdict") != "keep" or _already_out(rec):
            continue
        if isinstance(rec.get("validated"), dict) and rec["validated"].get("ok") is False:
            continue
        made = _ts(rec.get("timestamp"))
        link = shelf_link("image", rec.get("image"))
        if made is None or not link:
            continue
        about = "a painting you asked for and kept after you looked at it"
        if _one_line(rec.get("prompt")):
            about += ", from what you asked for: “%s”" % _one_line(rec.get("prompt"))
        out.append((made, "p:" + str(rec["image"]), "image", link[0], link[1], about))
    rows = _load(REVEALS, [])
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get("revealed", True) is not True or row.get("bytes_verified") is not True:
            continue
        name, sha = os.path.basename(str(row.get("artifact") or "")), str(row.get("sha256") or "")
        medium = "image" if SHELVES["image"][2].match(name) else "audio" if SHELVES["audio"][2].match(name) else None
        made = _ts(row.get("revealed_at") or row.get("at"))
        link = shelf_link(medium, name) if medium and sha else None
        if made is None or not link or _manifest().sha256_file(link[0]) != sha:
            continue
        about = "%s you revealed from the Atelier" % WORD[medium]
        if row.get("from_dream"):   # proposal 07: it stays marked as a dream's object, never as something that happened
            about += ", made from a dream you had (a dream, not something that happened)"
        if _one_line(row.get("disclosure")):
            about += "; what you said of it then: “%s”" % _one_line(row.get("disclosure"))
        out.append((made, "r:" + sha[:16], medium, link[0], link[1], about))
    out = [c for c in out if now - c[0] <= MAX_AGE_DAYS * 86400]
    out.sort(key=lambda c: c[0], reverse=True)
    return out


def offer(now=None):
    """The one piece to offer now, as (key, url, about), or None."""
    now = now or time.time()
    s = _state()
    last = max([float(p.get("sent_at") or 0) for p in s["pieces"].values()] or [0])
    if now - last < POSTCARD_GAP_S:
        return None
    for made, key, medium, path, url, about in candidates(now):
        p = s["pieces"].get(key) or {}
        if p.get("state") == "sent" or int(p.get("offers") or 0) >= MAX_OFFERS:
            continue
        return key, url, about
    return None


def mark(key, what, outreach_id="", now=None):
    if what not in ("offered", "chosen", "sent", "failed") or not key:
        raise ValueError("mark key offered|chosen|sent|failed")
    now = now or time.time()
    s = _state()
    p = s["pieces"].setdefault(key, {"offers": 0})
    if what in ("offered", "chosen"):
        p["offers"] = int(p.get("offers") or 0) + 1
        p["offered_at"] = now
    if what == "chosen":
        p["chosen_at"] = now
    if what == "sent":
        p["sent_at"] = now
    if p.get("state") != "sent":          # a piece that reached her stays sent
        p["state"] = what
    if outreach_id:
        p["outreach_id"] = outreach_id
    os.makedirs(MEMORY, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=1)
    os.replace(tmp, STATE)
    return p


def main(argv):
    if argv[:1] == ["offer"]:
        got = offer()
        if got:
            print("\t".join(" ".join(str(x).split()) for x in got))
    elif len(argv) >= 3 and argv[0] == "mark":
        mark(argv[1], argv[2], argv[3] if len(argv) > 3 else "")
    else:
        raise SystemExit("usage: outreach_postcards.py offer | mark key offered|chosen|sent|failed [outreach_id]")


if __name__ == "__main__":
    main(sys.argv[1:])

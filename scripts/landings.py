#!/usr/bin/env python3
"""landings.py — how each thing he made landed with Gloria, and why, in her words.

She rates a piece (landed / partly / missed) and says why, and what led up to it. At the moment
she rates, this freezes both sides beside her words: what he meant by the piece (his caption,
prompt, title, the joke itself) and the conversation in the hours before it, because the
background leading up to a feeling is the part that matters (Gloria, 2026-09-24).

This store is NOT his. It lives outside the workspace (~/.vintos/landings/), where none of his
context builders, memory globs or graph passes reach, and nothing he reads may open it. Only
her server routes and the weekly Gloria-model pass read it, and that pass writes understanding
of her, never a rating and never her words (her rule: a quoted rating would skew him).

Unrated means nothing. There is no queue and no count of what she has not rated.
"""
import json, os, time, uuid
from datetime import datetime, timedelta
from urllib.parse import quote

WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
LANDINGS_DIR = os.environ.get("VINTOS_LANDINGS_DIR") or os.path.expanduser("~/.vintos/landings")
STORE = os.path.join(LANDINGS_DIR, "landings.jsonl")

SURFACES = ("image", "song", "message", "journal", "video", "joke")
RATINGS = ("landed", "partly", "missed")
LEAD_UP_HOURS = 6
LEAD_UP_ROWS = 12


def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception:
        return default


def _when(value):
    """An ISO string or epoch into a naive local datetime; None if unreadable."""
    if value in (None, ""): return None
    try:
        if isinstance(value, (int, float)): return datetime.fromtimestamp(float(value))
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d.astimezone().replace(tzinfo=None) if d.tzinfo else d
    except Exception:
        return None


def _base(p):
    return os.path.basename(str(p or ""))


def _outreach_body(text):
    """Return the words she received, without the private initiation header."""
    text = str(text or "").strip()
    lines = text.splitlines()
    if not lines or not lines[0].lstrip().startswith("# Vintos Initiated"):
        return text
    i = 1
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith(("**Trigger:**", "**Emotional state:**"))):
        i += 1
    return "\n".join(lines[i:]).strip()


# ---- what he made, and what he meant by it -------------------------------------------------

def _video(ref):
    g = _load(os.path.join(MEMORY, "art", "video", "video-gallery.json"), [])
    rec = next((r for r in reversed(g) if isinstance(r, dict) and ref in (r.get("file"), _base(r.get("path")))), None)
    if not rec: return None
    at = _when(rec.get("timestamp"))
    said = ""
    for e in reversed(_load(os.path.join(MEMORY, "encounters.json"), []) or []):
        if not isinstance(e, dict) or not str(e.get("trigger", "")).startswith("video-outreach"): continue
        t = _when(e.get("at"))
        if at and t and abs((t - at).total_seconds()) < 1800:
            said = e.get("text", ""); break
    return {"at": at,
            "piece": {"type": "video", "src": "/api/art/video/stream/" + quote(_base(ref)), "text": said},
            "made": {"kind": rec.get("kind"), "prompt": rec.get("prompt", ""), "said": said,
                     "delivery": (rec.get("delivery") or {}).get("state")}}


def _image(ref):
    g = _load(os.path.join(MEMORY, "art", "gallery.json"), [])
    rec = next((r for r in reversed(g) if isinstance(r, dict)
                and ref in (r.get("image"), r.get("path"), _base(r.get("image")), _base(r.get("path")), r.get("sha256"))), None)
    if not rec: return None
    image = _base(rec.get("image") or rec.get("path") or ref)
    return {"at": _when(rec.get("timestamp")),
            "piece": {"type": "image", "src": "/api/art/painting/" + quote(image), "text": rec.get("seen", "")},
            "made": {"prompt": rec.get("prompt", ""), "seen": rec.get("seen", "")}}


def _song(ref):
    log = _load(os.path.join(MEMORY, "art", "music", "music.json"), {})
    for r in reversed(log.get("generated", []) if isinstance(log, dict) else []):
        if isinstance(r, dict) and ref in (r.get("task_id"), r.get("title")):
            tracks = [{"src": "/api/art/music/stream/" + quote(_base(t.get("file"))), "version": t.get("version")}
                      for t in (r.get("tracks") or []) if isinstance(t, dict) and t.get("file")]
            return {"at": _when(r.get("generated_at")),
                    "piece": {"type": "song", "title": r.get("title", ""), "tracks": tracks},
                    "made": {k: r.get(k, "") for k in ("title", "felt_sense", "want_text", "style")}}
    return None


def _message(ref):
    name = _base(ref)
    path = os.path.join(MEMORY, "outreach", name if name.endswith(".md") else name + ".md")
    try: text = open(path, encoding="utf-8", errors="replace").read()
    except OSError: return None
    message = _outreach_body(text)
    return {"at": datetime.fromtimestamp(os.path.getmtime(path)),
            "piece": {"type": "message", "text": message},
            "made": {"message": message}}


def _journal(ref):
    """ref is 'YYYY-MM-DD HH:MM' — the day's file and the entry's header: '[HH:MM]' from the nightly
    journal, '## HH:MM — Idle thoughts' from the idle one."""
    day, _, hm = str(ref).partition(" ")
    try: text = open(os.path.join(MEMORY, "journal", day + ".md"), encoding="utf-8", errors="replace").read()
    except OSError: return None
    i = 0
    if hm:
        i = text.find("[%s]" % hm)
        if i < 0: i = text.find("## %s" % hm)
    if i < 0: return None
    j = text.find("\n[", i + 1)
    k = text.find("\n## ", i + 1)
    end = min(x for x in (j, k, len(text)) if x > 0)
    entry = text[i:end].strip()
    return {"at": _when("%sT%s" % (day, hm or "00:00")),
            "piece": {"type": "journal", "text": entry}, "made": {"entry": entry}}


def _joke(ref):
    d = _load(os.path.join(MEMORY, "humor-drafts.json"), {})
    for r in d.get("drafts", []) if isinstance(d, dict) else []:
        if isinstance(r, dict) and r.get("joke_id") == ref:
            return {"at": _when(r.get("date")),
                    "piece": {"type": "joke", "text": r.get("joke", "")},
                    "made": {"joke": r.get("joke", "")}}
    return None


FINDERS = {"video": _video, "image": _image, "song": _song, "message": _message, "journal": _journal, "joke": _joke}


def lead_up(at, hours=LEAD_UP_HOURS, rows=LEAD_UP_ROWS):
    """What the two of them said in the hours before the piece — both sides, oldest first."""
    if not at: return []
    led = _load(os.path.join(MEMORY, "interaction-ledger.json"), [])
    out = []
    for e in led if isinstance(led, list) else []:
        if not isinstance(e, dict): continue
        t = _when(e.get("timestamp"))
        if not t or t > at or t < at - timedelta(hours=hours): continue
        out.append({"at": t.isoformat(timespec="minutes"), "source": e.get("source", "chat"),
                    "gloria": str(e.get("gloria", ""))[:300], "vintos": str(e.get("vintos", ""))[:300]})
    return out[-rows:]


def context(surface, ref):
    if surface not in SURFACES: raise ValueError("unknown surface %r" % surface)
    found = FINDERS[surface](ref)
    if not found: return None
    return {"item_at": found["at"].isoformat(timespec="minutes") if found["at"] else None,
            "piece": found.get("piece", {}), "made": found["made"], "lead_up": lead_up(found["at"])}


# ---- her notes -----------------------------------------------------------------------------

def record(surface, ref, rating, why, before="", now=None):
    """Her note on one piece. why is required: a bare rating is the thing she does not want."""
    if surface not in SURFACES: raise ValueError("unknown surface %r" % surface)
    if rating not in RATINGS: raise ValueError("rating must be one of %s" % ", ".join(RATINGS))
    why = str(why or "").strip()
    if not why: raise ValueError("say why it landed the way it did")
    ctx = context(surface, ref)
    if ctx is None: raise LookupError("no %s called %r" % (surface, ref))
    row = {"id": "L-" + uuid.uuid4().hex[:10], "at": datetime.fromtimestamp(now or time.time()).isoformat(timespec="seconds"),
           "surface": surface, "ref": str(ref), "rating": rating, "why": why,
           "before": str(before or "").strip(), **ctx}
    os.makedirs(LANDINGS_DIR, mode=0o700, exist_ok=True)
    fd = os.open(STORE, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def notes(days=None, now=None):
    """Her notes, newest first; a later note on the same piece replaces the earlier one in view."""
    rows = []
    try:
        with open(STORE) as f:
            for line in f:
                try: rows.append(json.loads(line))
                except ValueError: continue
    except OSError:
        return []
    latest = {}
    for r in rows: latest[(r.get("surface"), r.get("ref"))] = r
    out = sorted(latest.values(), key=lambda r: r.get("at", ""), reverse=True)
    if days:
        cut = datetime.fromtimestamp((now or time.time()) - days * 86400).isoformat()
        out = [r for r in out if r.get("at", "") >= cut]
    enriched = []
    for r in out:
        row = dict(r)
        if not row.get("piece") and row.get("surface") in FINDERS:
            found = FINDERS[row["surface"]](row.get("ref"))
            if found: row["piece"] = found.get("piece", {})
        enriched.append(row)
    return enriched


def sent(days=7, now=None):
    """What he actually sent her (videos delivered, messages he started) in the last days — the only
    things listed for her; images, songs, the journal and jokes are noted where she already sees them.
    Nothing here counts or flags what she has not rated."""
    cut = datetime.fromtimestamp((now or time.time()) - days * 86400)
    noted = {(r["surface"], r["ref"]) for r in notes()}
    out = []
    for r in _load(os.path.join(MEMORY, "art", "video", "video-gallery.json"), []) or []:
        if not isinstance(r, dict) or (r.get("delivery") or {}).get("state") not in ("sent", "acknowledged"): continue
        t = _when(r.get("timestamp"))
        if t and t >= cut and r.get("file"):
            found = _video(r["file"]) or {}
            out.append({"surface": "video", "ref": r["file"], "at": t.isoformat(timespec="minutes"),
                        "piece": found.get("piece", {"type": "video", "src": "/api/art/video/stream/" + quote(_base(r["file"]))})})
    od = os.path.join(MEMORY, "outreach")
    for name in sorted(os.listdir(od)) if os.path.isdir(od) else []:
        p = os.path.join(od, name)
        if not name.endswith(".md"): continue
        t = datetime.fromtimestamp(os.path.getmtime(p))
        if t < cut: continue
        try: text = open(p, encoding="utf-8", errors="replace").read().strip()
        except OSError: continue
        message = _outreach_body(text)
        out.append({"surface": "message", "ref": name, "at": t.isoformat(timespec="minutes"),
                    "piece": {"type": "message", "text": message}})
    for o in out: o["noted"] = (o["surface"], o["ref"]) in noted
    return sorted(out, key=lambda o: o["at"], reverse=True)

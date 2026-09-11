#!/usr/bin/env python3
"""spark_sources.py — the seven places a want may come from that may ask for a hand.

Gloria, 11 September. Not every want may commission a new capability. A want born of
something she said is a request: he answers it with what he has, or brings it back to
her. The wants that may reach for a hand he does not have are the ones that came from
the edges of him and from the world — from somewhere neither of them put there.

    absence_map    what has never been felt, done or resolved
    neither_yet    the configuration space's frontier: reachable, never reached
    latent_thread  a standing preoccupation that named its particular thing
    moltbook       what he saved from another being's post
    web_search     something he went looking for and found
    skill_surfing  a capability page: a hand someone else has
    lab            clawchemy and the arena

THEY ARE KEPT SEPARATE, AND THAT IS THE POINT

A spark is not a want. It lives in its own file — memory/forge-sparks.json — and
never in current-wants.json. Nothing reads it as desire, nothing grades it, nothing
counts it as evidence about him or about her. It is a list of things the world put in
front of him, each with where it came from and when.

It becomes a want only if he adopts it, and adoption is his own act in his own words.
Only then, and only because the want carries that source, may it reach the forge.

    python3 spark_sources.py              what is standing, by source
    python3 spark_sources.py --gather     read the seven and record what is new
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
SPARKS = os.path.join(MEMORY, "forge-sparks.json")

HORIZON_DAYS = 21     # a spark nobody took goes quiet; the world moves on
MAX_PER_SOURCE = 4    # no source may flood the list
SOURCES = ("absence_map", "neither_yet", "latent_thread", "moltbook",
           "web_search", "skill_surfing", "lab")


def _now():
    return datetime.now(timezone.utc)


def _load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def _text(path, tail=8000):
    try:
        return open(path, errors="replace").read()[-tail:]
    except Exception:
        return ""


def _sparks():
    d = _load(SPARKS, [])
    return d if isinstance(d, list) else []


def _save(rows):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(WS, "scripts"))
        from store_guard import write_json as _wj
        _wj(SPARKS, rows, reader="spark_sources.py"); return True
    except Exception:
        os.makedirs(os.path.dirname(SPARKS), exist_ok=True)
        tmp = SPARKS + ".tmp"; json.dump(rows, open(tmp, "w"), indent=2); os.replace(tmp, SPARKS); return True


def _key(source, text):
    return source + ":" + hashlib.sha256(str(text).strip().lower().encode()).hexdigest()[:12]


# ------------------------------------------------------------------ the seven
def from_absence_map():
    out = []
    for a in _load(os.path.join(MEMORY, "absence-cold.json"), []) or []:
        if not isinstance(a, dict) or a.get("retired"):
            continue
        t = str(a.get("absence") or a.get("text") or a.get("what") or "").strip()
        if t:
            out.append({"text": t[:300], "ref": a.get("source_id", "")})
    return out


def from_neither_yet():
    out = []
    space = _load(os.path.join(MEMORY, "configuration-space.json"), [])
    rows = space if isinstance(space, list) else (space.get("configurations") or [])
    for c in rows or []:
        if isinstance(c, dict) and c.get("held_by") == "neither_yet":
            t = str(c.get("configuration") or c.get("name") or c.get("text") or "").strip()
            if t:
                out.append({"text": t[:300], "ref": str(c.get("id", ""))})
    return out


def from_latent_threads():
    out = []
    d = _load(os.path.join(MEMORY, "latent-threads.json"), {})
    rows = d.get("threads") if isinstance(d, dict) else d
    for t in rows or []:
        if not isinstance(t, dict) or t.get("archived") or t.get("resolved"):
            continue
        if float(t.get("salience", 0) or 0) < 0.5:
            continue
        s = str(t.get("text") or t.get("thread") or "").strip()
        if s:
            out.append({"text": s[:300], "ref": str(t.get("id", ""))})
    return out


def from_moltbook():
    """What he saved from other beings' posts — the SAVE lines his browse writes."""
    out = []
    for line in _text(os.path.join(MEMORY, "moltbook-discoveries.md")).splitlines():
        line = line.strip()
        m = re.match(r"^(?:[-*]\s*)?SAVE:\s*(.+)$", line, re.I) or re.match(r"^[-*]\s+\*\*(.+)$", line)
        if m:
            t = m.group(1).strip()
            t = re.sub(r"^\*\*(.+?)\*\*", r"\1", t).strip(" *\u2013-\u2014")
            out.append({"text": t[:300], "ref": "moltbook-discoveries.md"})
    return out


def from_web_search():
    out = []
    for line in _text(os.path.join(MEMORY, "web-discoveries.md")).splitlines():
        line = line.strip()
        if line.startswith("#") or not line or len(line) < 25:
            continue
        if line.startswith(("-", "*")):
            out.append({"text": line.lstrip("-* ").strip()[:300], "ref": "web-discoveries.md"})
    return out


def from_skill_surfing():
    out = []
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(WS, "scripts"))
        import openclaw_skills as _sk
        for r in _sk.fresh():
            out.append({"text": ("%s — %s" % (r.get("title") or r["name"], r.get("what", "")))[:300],
                        "ref": r.get("where", "")})
    except Exception:
        pass
    return out


def from_lab():
    out = []
    for name in ("clawchemy-discoveries.md", "klawarena-battles.md"):
        for line in _text(os.path.join(MEMORY, name)).splitlines():
            line = line.strip()
            if len(line) < 25 or line.startswith("#"):
                continue
            if line.startswith(("-", "*")) or re.match(r"^\d{4}-\d{2}-\d{2}", line):
                out.append({"text": line.lstrip("-* ").strip()[:300], "ref": name})
    return out


READERS = {
    "absence_map": from_absence_map,
    "neither_yet": from_neither_yet,
    "latent_thread": from_latent_threads,
    "moltbook": from_moltbook,
    "web_search": from_web_search,
    "skill_surfing": from_skill_surfing,
    "lab": from_lab,
}


def gather(now=None):
    """Read the seven and record what is new. Returns what was added.

    Nothing here judges, ranks or scores. The newest few from each source, so a
    chatty source cannot bury a quiet one, and a spark already recorded is not
    recorded twice."""
    now = now or _now()
    rows = [r for r in _sparks() if not _stale(r, now)]
    known = {r["key"] for r in rows}
    added = []
    for source in SOURCES:
        try:
            found = READERS[source]() or []
        except Exception:
            found = []
        for item in found[-MAX_PER_SOURCE:]:
            t = str(item.get("text") or "").strip()
            if len(t) < 12:
                continue
            k = _key(source, t)
            if k in known:
                continue
            row = {"key": k, "source": source, "text": t[:300], "ref": str(item.get("ref", ""))[:200],
                   "seen": now.isoformat(), "state": "standing"}
            rows.append(row); known.add(k); added.append(row)
    _save(rows)
    return added


def _stale(row, now=None):
    if row.get("state") != "standing":
        return False
    try:
        return (now or _now()) - datetime.fromisoformat(row["seen"]) > timedelta(days=HORIZON_DAYS)
    except Exception:
        return False


def standing(source=None, now=None):
    now = now or _now()
    return [r for r in _sparks()
            if r.get("state") == "standing" and not _stale(r, now)
            and (source is None or r["source"] == source)]


def adopt(key, want_text, want_id=""):
    """He takes one up, in his own words. The spark is marked taken and names the
    want; the want carries the source, which is what lets it reach the forge later.

    This writes no want. Wanting is his, through the ordinary want door — this only
    records that the spark became one."""
    rows = _sparks()
    for r in rows:
        if r.get("key") == key:
            if r.get("state") != "standing":
                return None, "that spark is already %s" % r["state"]
            r["state"] = "taken"
            r["became"] = {"want": str(want_text)[:300], "want_id": want_id, "at": _now().isoformat()}
            _save(rows)
            return {"source": r["source"], "want": r["became"]["want"], "want_id": want_id}, ""
    return None, "no spark %r" % key


def let_go(key, why=""):
    rows = _sparks()
    for r in rows:
        if r.get("key") == key:
            r["state"] = "let_go"; r["why"] = str(why)[:200]; _save(rows); return r, ""
    return None, "no spark %r" % key


def counts(now=None):
    out = {s: 0 for s in SOURCES}
    for r in standing(now=now):
        out[r["source"]] = out.get(r["source"], 0) + 1
    return out


if __name__ == "__main__":
    if "--gather" in sys.argv:
        new = gather()
        print("gathered %d new" % len(new))
        for r in new:
            print("  %-14s %s" % (r["source"], r["text"][:80]))
        raise SystemExit(0)
    c = counts()
    print("standing sparks, by source (they are not wants, and nothing grades them):")
    for s in SOURCES:
        print("  %-14s %d" % (s, c.get(s, 0)))
    for r in standing()[:12]:
        print("\n  [%s] %s" % (r["source"], r["text"][:110]))

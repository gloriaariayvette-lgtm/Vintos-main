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
    lab            whatever she points the lab reader at

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
    d = _load(os.path.join(MEMORY, "absence-cold.json"), {})
    rows = d.get("absences") if isinstance(d, dict) else d
    for a in rows or []:
        if not isinstance(a, dict) or a.get("reached"):
            continue
        t = str(a.get("description") or "").strip()
        if t:
            out.append({"text": t[:300], "ref": a.get("source_id", "")})
    return out


def from_neither_yet():
    out = []
    space = _load(os.path.join(MEMORY, "configuration-space.json"), [])
    rows = space if isinstance(space, list) else (space.get("configurations") or [])
    for c in rows or []:
        if isinstance(c, dict) and c.get("held_by") == "neither_yet":
            t = str(c.get("description") or "").strip()
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
        txt = str(t.get("origin") or t.get("text") or t.get("thread") or "").strip()
        if txt:
            out.append({"text": txt[:300], "ref": str(t.get("id", ""))})
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
        for r in _sk.unheld():
            out.append({"text": ("%s — %s" % (r.get("title") or r["name"], r.get("what", "")))[:300],
                        "ref": r.get("where", "")})
    except Exception:
        pass
    return out


def from_lab():
    """The lab, read from wherever Gloria points this at — and nowhere else.

    It reads `lab` in memory/spark-config.json: a file, or a folder of files, or a
    list of either. With nothing configured it finds nothing and says so. Guessing a
    filename here once made it read two dead logs from another project, which is how
    a source becomes noise."""
    cfg = _load(os.path.join(MEMORY, "spark-config.json"), {})
    where = cfg.get("lab")
    paths = []
    for p in ([where] if isinstance(where, str) else list(where or [])):
        p = os.path.expanduser(str(p))
        if os.path.isdir(p):
            paths += [os.path.join(p, n) for n in sorted(os.listdir(p))
                      if n.endswith((".md", ".txt", ".jsonl"))]
        elif os.path.isfile(p):
            paths.append(p)
    out = []
    for path in paths[-4:]:
        for line in _text(path).splitlines():
            line = line.strip()
            if len(line) < 25 or line.startswith("#"):
                continue
            # A lab that keeps structured records can hand them over whole, with the
            # occasion they came from attached. Scraping prose out of a JSONL loses the
            # session, the run and the standing before the want exists — and a want that
            # cannot name its occasion is not provenance. The prose path below is
            # unchanged, for a lab that is a folder of notes.
            if line.startswith("{"):
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                text = str(row.get("text") or "").strip()
                if not isinstance(row, dict) or len(text) < 25:
                    continue
                item = {"text": text[:300], "ref": str(row.get("ref") or os.path.basename(path))}
                if isinstance(row.get("provenance"), dict):
                    item["provenance"] = row["provenance"]
                out.append(item)
                continue
            if line.startswith(("-", "*")) or re.match(r"^\d{4}-\d{2}-\d{2}", line):
                out.append({"text": line.lstrip("-* ").strip()[:300], "ref": os.path.basename(path)})
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
    rows = _sparks()
    for r in rows:
        if r.get("state") == "standing" and _stale(r, now):
            r["state"] = "expired"          # a tombstone: keeps the key so it never returns
    known = {r["key"] for r in rows}        # every row, whatever its state
    added = []
    for source in SOURCES:
        if source == "skill_surfing":
            # The OpenClaw skills page is read on its own weekly schedule (1-2 pages),
            # never on every gather — see weekly_skill_surf(). gather() leaves it alone.
            continue
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
            # Where a reader knows the occasion, the spark keeps it. Bounded, because a
            # spark row is a small thing and a source should not be able to grow it.
            if isinstance(item.get("provenance"), dict):
                row["provenance"] = {str(pk)[:40]: (pv if isinstance(pv, (bool, int, float)) else str(pv)[:200])
                                     for pk, pv in list(item["provenance"].items())[:16]}
            rows.append(row); known.add(k); added.append(row)
    _save(rows)
    return added


SURF_STATE = os.path.join(MEMORY, "skill-surf-state.json")
PAGES_PER_WEEK = 2    # Gloria, 11 September: he reads 1-2 pages of the OpenClaw skills page a week
SURF_EVERY_DAYS = 7


def weekly_skill_surf(now=None, force=False):
    """Once a week, he reads 1-2 pages of the OpenClaw skills page — no more, and
    not the whole thing at once. The weekly cap lives here, in code, so it holds no
    matter how often the timer fires. Reading is a plain page fetch: it calls no
    model and spends no credits. Skills he does not already have become standing
    sparks (still bounded by MAX_PER_SOURCE so one big list cannot flood him); every
    skill on the pages read is marked seen so next week moves on to new ground.

    Returns a small record of what it did. force=True ignores the weekly gate (for a
    manual read); it never changes the page budget."""
    now = now or _now()
    st = _load(SURF_STATE, {})
    if not force and st.get("last"):
        try:
            if now - datetime.fromisoformat(st["last"]) < timedelta(days=SURF_EVERY_DAYS):
                return {"read": False, "reason": "already read a page this week"}
        except Exception:
            pass
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(WS, "scripts"))
        import openclaw_skills as _sk
    except Exception as e:
        return {"read": False, "reason": "openclaw reader unavailable: %s" % str(e)[:120]}
    total_pages = len(_sk.pages())
    if not total_pages:
        return {"read": False, "reason": "pointed nowhere: set skills_url in openclaw-config.json"}
    start = int(st.get("next_start", 0)) % total_pages
    skills, labels = _sk.read_pages(budget=PAGES_PER_WEEK, start=start)
    mine = {_sk._norm(x) for x in _sk.his()}
    already_seen = _sk.seen_names()
    rows = _sparks()
    known = {r["key"] for r in rows}
    new, on_page = [], []
    for r in skills:
        nm = _sk._norm(r.get("name"))
        if not nm:
            continue
        on_page.append(r.get("name"))
        if nm in mine or nm in already_seen:
            continue                                  # he has it, or he has seen it before
        if len(new) >= MAX_PER_SOURCE:                # read the whole page, but do not flood the ledger
            continue
        text = ("%s — %s" % (r.get("title") or r.get("name"), r.get("what", ""))).strip(" —")[:300]
        k = _key("skill_surfing", text)
        if k in known:
            continue
        row = {"key": k, "source": "skill_surfing", "text": text,
               "ref": str(r.get("where", ""))[:200], "seen": now.isoformat(), "state": "standing"}
        rows.append(row); known.add(k); new.append(row)
    if new:
        _save(rows)
    _sk.mark_seen([r.get("name") for r in skills if _key("skill_surfing", ("%s — %s" % (r.get("title") or r.get("name"),r.get("what", ""))).strip(" —")[:300]) in {x["key"] for x in new}])                              # the whole page is now read
    st = {"last": now.isoformat(), "next_start": (start + len(labels)) % total_pages}
    try:
        os.makedirs(MEMORY, exist_ok=True)
        _tmp = SURF_STATE + ".tmp"; json.dump(st, open(_tmp, "w"), indent=2); os.replace(_tmp, SURF_STATE)
    except Exception:
        pass
    return {"read": True, "pages": labels, "skills_on_pages": len(on_page),
            "new_sparks": len(new), "next_start": st["next_start"]}


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
            # The provenance travels with the source, so the want door can keep it and the
            # forge can later name the occasion the capability was asked for.
            taken = {"source": r["source"], "want": r["became"]["want"], "want_id": want_id}
            if isinstance(r.get("provenance"), dict): taken["provenance"] = r["provenance"]
            return taken, ""
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


# Resolve sibling helpers for direct file loading as well as deployed entrypoints.
import sys as _guard_sys
from pathlib import Path as _GuardPath
_guard_here = _GuardPath(__file__).resolve().parent
_guard_sys.path.insert(0, str(_guard_here.parent / "scripts"))
_guard_sys.path.insert(0, str(_guard_here))
from store_guard import serialized as _serialized
for _fn in ("gather","weekly_skill_surf","adopt","let_go"):
    globals()[_fn] = _serialized("SPARKS")(globals()[_fn])

if __name__ == "__main__":
    if "--gather" in sys.argv:
        new = gather()
        print("gathered %d new" % len(new))
        for r in new:
            print("  %-14s %s" % (r["source"], r["text"][:80]))
        raise SystemExit(0)
    if "--surf" in sys.argv:
        # the weekly OpenClaw skills read: run it as often as you like (a weekly timer
        # is simplest); it reads at most 1-2 pages and only once every 7 days.
        res = weekly_skill_surf(force=("--force" in sys.argv))
        if res.get("read"):
            print("read %d page(s): %s" % (len(res["pages"]), ", ".join(res["pages"])))
            print("skills on those pages: %d; new standing sparks: %d" % (res["skills_on_pages"], res["new_sparks"]))
        else:
            print("did not read: %s" % res.get("reason"))
        raise SystemExit(0)
    c = counts()
    print("standing sparks, by source (they are not wants, and nothing grades them):")
    for s in SOURCES:
        print("  %-14s %d" % (s, c.get(s, 0)))
    for r in standing()[:12]:
        print("\n  [%s] %s" % (r["source"], r["text"][:110]))

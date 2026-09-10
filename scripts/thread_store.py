#!/usr/bin/env python3
"""thread_store.py — the one door for the shared thread pool and the thread archive.

Pool (unfinished-threads.json):
  load_pool()            -> list, or None when the ledger is unreadable (never an empty list:
                            an unreadable ledger treated as empty is how the pool got wiped 2026-08-10)
  save_pool(threads)     -> bool. Atomic tmp+replace, with the SHRINK GUARD every writer must pass:
                            refuse when the write would drop the pool to less than half of what is on
                            disk (pool > 5), or when the on-disk ledger is unreadable and the write is
                            small. A refusal is printed, never silent.

Archive (retired-threads.json) has been written in two shapes: a bare list (thread-resolution,
thread-triage) and {"threads": [...]} (latent_threads). Both are read; one shape is written:
  load_retired()         -> list of entries, whatever shape is on disk
  append_retired(entries)-> writes the canonical list shape, normalizing each entry

No LLM. No network. Import-safe. Paths are module attributes so tests can redirect them.
"""
import os, json, sys
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
POOL_FILE = os.path.join(MEMORY, "unfinished-threads.json")
RETIRED_FILE = os.path.join(MEMORY, "retired-threads.json")
SHRINK_MIN_POOL = 5      # guard engages once the pool is bigger than this
SHRINK_RATIO = 0.5       # refuse writes that keep fewer than this fraction


def _say(msg):
    print("[thread-store] " + msg, file=sys.stderr)


def _as_list(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("threads", "entries"):
            if isinstance(obj.get(k), list):
                return obj[k]
    return None


def _atomic_write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ── pool ──────────────────────────────────────────────────────────────

def load_pool(path=None):
    """Return the thread list, or None if the file is unreadable/malformed. A missing file is []."""
    path = path or POOL_FILE
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            obj = json.load(f)
    except Exception as e:
        _say("pool unreadable (%s): %s" % (path, e))
        return None
    lst = _as_list(obj)
    if lst is None:
        _say("pool malformed (not a list): %s" % path)
    return lst


def save_pool(threads, path=None, reason=""):
    """Write the pool through the shrink guard. Returns True when written."""
    path = path or POOL_FILE
    if not isinstance(threads, list):
        _say("REFUSING write%s: not a list" % ((" (" + reason + ")") if reason else ""))
        return False
    n_after = len(threads)
    on_disk = load_pool(path)
    if on_disk is None:
        # Unreadable ledger: a small rewrite would replace a pool we cannot see.
        if n_after <= SHRINK_MIN_POOL:
            _say("REFUSING write%s: ledger unreadable and write is only %d thread(s)"
                 % ((" (" + reason + ")") if reason else "", n_after))
            return False
    else:
        n_before = len(on_disk)
        if n_before > SHRINK_MIN_POOL and n_after < n_before * SHRINK_RATIO:
            _say("REFUSING write%s: would shrink pool %d -> %d (shrink guard)"
                 % ((" (" + reason + ")") if reason else "", n_before, n_after))
            return False
    _atomic_write(path, threads)
    return True


# ── archive ───────────────────────────────────────────────────────────

def normalize_retired_entry(e):
    """One entry shape whatever wrote it. Latent threads carry 'origin'; pool threads carry 'thread'."""
    if not isinstance(e, dict):
        return {"id": "", "thread": str(e), "source": "unknown", "consumed_by": "",
                "retired_at": "", "type": "unknown"}
    out = dict(e)
    out["id"] = e.get("id") or e.get("thread_id") or ""
    out["thread"] = e.get("thread") or e.get("origin") or e.get("text") or ""
    out["source"] = e.get("source") or e.get("origin_source") or "unknown"
    out["consumed_by"] = e.get("consumed_by") or e.get("retired_by") or ""
    out["retired_at"] = e.get("retired_at") or e.get("timestamp") or ""
    out["type"] = e.get("type") or e.get("retired_as") or ("latent" if "phase" in e else "unknown")
    return out


def load_retired(path=None):
    """Read the archive in either historical shape. Returns a list (possibly empty)."""
    path = path or RETIRED_FILE
    try:
        with open(path) as f:
            obj = json.load(f)
    except Exception:
        return []
    lst = _as_list(obj)
    return [normalize_retired_entry(e) for e in lst] if lst is not None else []


# ---------------------------------------------------------------- admission and archive (review 264)
# Every producer used to build its own thread dict and every consumer retired threads its own way. The
# store owns both now: admit() is the one shape (with an id, a kind - question or theme - and who
# admitted it), archive() is the one way out of the pool (consumed, retired, appended to the retired
# ledger, the pool rewritten through the shrink guard). A question is something that can be answered
# or released; a theme is a standing preoccupation that recurs. They never collapse into one field.

QUESTION_MARKS = ("?", "why ", "what ", "how ", "whether ", "does ", "did ", "is it ", "should ")

def classify_kind(text):
    t = str(text or "").strip().lower()
    return "question" if (t.endswith("?") or any(m in t[:40] for m in QUESTION_MARKS)) else "theme"

def admit(thread_text, source, kind=None, by="", extra=None):
    """The one shape for a pool thread. Returns the dict; the caller appends it and saves through save_pool."""
    import uuid
    text = str(thread_text or "").strip()
    if len(text) < 8:
        raise ValueError("a thread needs at least a sentence")
    t = {"id": str(uuid.uuid4())[:8], "source": str(source or "unknown"), "thread": text,
         "kind": kind if kind in ("question", "theme") else classify_kind(text),
         "timestamp": datetime.now().isoformat(), "admitted_by": by or str(source or "unknown"),
         "consumed": False}
    if extra:
        t.update({k: v for k, v in extra.items() if k not in ("id", "consumed")})
    return t

def archive(ids, reason, by, pool_path=None, retired_path=None):
    """Retire threads by id: consumed + retired in the pool, one entry each in the retired ledger, the
    pool rewritten through the shrink guard. Returns the ids actually archived."""
    ids = set(ids if isinstance(ids, (list, tuple, set)) else [ids])
    threads = load_pool(pool_path)
    if threads is None:
        return []
    done = []
    for t in threads:
        if t.get("id") in ids and not t.get("retired"):
            t["consumed"] = True; t["retired"] = True; t["consumed_by"] = by; t["retired_reason"] = reason
            t["retired_at"] = datetime.now().isoformat(); done.append(t["id"])
    if done:
        append_retired([{"id": t["id"], "thread": t.get("thread", ""), "source": t.get("source", ""), "kind": t.get("kind"),
                         "consumed_by": by, "type": reason} for t in threads if t.get("id") in done], retired_path)
        save_pool(threads, pool_path, reason="archive:%s" % reason)
    return done


def append_retired(entries, path=None):
    """Append one or more entries and write the canonical (list) shape. Returns the full list."""
    path = path or RETIRED_FILE
    if isinstance(entries, dict):
        entries = [entries]
    existing = load_retired(path)
    stamp = datetime.now().isoformat()
    for e in entries:
        n = normalize_retired_entry(e)
        if not n.get("retired_at"):
            n["retired_at"] = stamp
        existing.append(n)
    _atomic_write(path, existing)
    return existing

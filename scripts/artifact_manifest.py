#!/usr/bin/env python3
"""artifact_manifest.py — one manifest shape for every shelf artifact (art, music, video).

Every artifact record the gallery writers append gains the same fields, next to whatever
they already wrote (existing records without them stay readable — nothing here rewrites
old entries):

  source_want  want id the piece answered, or null
  run_id       the writer's run (one per process), so two files from one run are kin
  path         the file, relative to its shelf dir (what the record's legacy 'image'/'file' says)
  bytes        size on disk when recorded
  sha256       content hash — the identity of THIS render, not its title or its minute
  medium       image | audio | video
  revision     1 for the first file of a stem, 2+ when a later render shares the stem
  validated    {"ok": bool, "how": "magic:png" | "missing" | ...}
  shared       null, or {"where": ..., "when": ...} once it left the shelf
  delivery     null, or {"state": queued|sent|acknowledged|failed, "at": iso, "why": ...}

Also: unique_path() — a filename that carries the content hash and a revision suffix, so a
second render never lands on the first (review 279); and delivery marking that never
promotes a send to a reception (288): only mark_acknowledged() may write 'acknowledged'.
"""
import os, json, hashlib, time
from datetime import datetime

MANIFEST_FIELDS = ("source_want", "run_id", "path", "bytes", "sha256", "medium",
                   "revision", "validated", "shared", "delivery")
DELIVERY_STATES = ("queued", "sent", "acknowledged", "failed")
MEDIA = ("image", "audio", "video")

_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "png", "image"),
    (b"\xff\xd8\xff", "jpeg", "image"),
    (b"RIFF", "wav", "audio"),         # RIFF....WAVE checked below
    (b"ID3", "mp3", "audio"),
    (b"\xff\xfb", "mp3", "audio"),
    (b"\xff\xf3", "mp3", "audio"),
)

_RUN_ID = None
def run_id():
    """One id per process: <utc-stamp>-<pid>."""
    global _RUN_ID
    if _RUN_ID is None:
        _RUN_ID = "%s-%d" % (datetime.utcnow().strftime("%Y%m%dT%H%M%S"), os.getpid())
    return _RUN_ID

def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def sniff(path):
    """(format, medium) from the file's leading bytes, or (None, None)."""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        return None, None
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav", "audio"
    if head[4:8] == b"ftyp":
        return "mp4", "video"
    for magic, fmt, medium in _MAGIC:
        if magic == b"RIFF":
            continue
        if head.startswith(magic):
            return fmt, medium
    return None, None

def validate_file(path, medium=None):
    """Is the file a real artifact of its medium? Returns the 'validated' dict."""
    if not os.path.isfile(path):
        return {"ok": False, "how": "missing"}
    size = os.path.getsize(path)
    if size <= 0:
        return {"ok": False, "how": "empty"}
    fmt, seen = sniff(path)
    if fmt is None:
        return {"ok": False, "how": "unknown-format"}
    if medium and seen != medium:
        return {"ok": False, "how": "magic:%s!=%s" % (fmt, medium)}
    return {"ok": True, "how": "magic:%s" % fmt}

def unique_path(directory, stem, ext, content=None, sha=None):
    """A path under directory that no earlier render occupies.

    The name carries the first 10 hex of the content hash (stem-<sha10>.ext); if that
    exact name already exists — same render written twice, or a collision — a revision
    suffix (-r2, -r3, ...) is added instead of overwriting. Returns (path, revision).
    """
    ext = ext if ext.startswith(".") else "." + ext
    if sha is None:
        sha = sha256_bytes(content) if content is not None else None
    base = "%s-%s" % (stem, sha[:10]) if sha else stem
    path = os.path.join(directory, base + ext)
    rev = 1
    while os.path.exists(path):
        rev += 1
        path = os.path.join(directory, "%s-r%d%s" % (base, rev, ext))
    return path, rev

def next_revision(directory, stem, ext):
    """For writers that must name the file BEFORE the bytes exist (a downloader writes
    straight to disk): stem.ext if free, else stem-r2.ext, ... Returns (path, revision)."""
    ext = ext if ext.startswith(".") else "." + ext
    path = os.path.join(directory, stem + ext)
    rev = 1
    while os.path.exists(path):
        rev += 1
        path = os.path.join(directory, "%s-r%d%s" % (stem, rev, ext))
    return path, rev

def build(path, medium, source_want=None, revision=1, shelf=None, run=None, validated=None):
    """The manifest fields for a file on disk. Merge into the writer's own record with
    record.update(build(...)); the writer's legacy keys ('image', 'file', 'timestamp', ...)
    stay untouched."""
    if medium not in MEDIA:
        raise ValueError("medium must be one of %s" % (MEDIA,))
    rel = os.path.relpath(path, shelf) if shelf else os.path.basename(path)
    exists = os.path.isfile(path)
    return {
        "source_want": (source_want or None),
        "run_id": run or run_id(),
        "path": rel,
        "bytes": os.path.getsize(path) if exists else 0,
        "sha256": sha256_file(path) if exists else None,
        "medium": medium,
        "revision": int(revision or 1),
        "validated": validated if validated is not None else validate_file(path, medium),
        "shared": None,
        "delivery": None,
    }

def revise(previous, path, medium=None, note="", run=None):
    """review 283: a new draft of an earlier work. The manifest of the new file carries revision n+1,
    previous_sha256 and previous_path, and a note saying what the revision was for. The old record is
    untouched: both drafts stay comparable."""
    prev = previous if isinstance(previous, dict) else {}
    rec = build(path, medium or prev.get("medium") or "image", source_want=prev.get("source_want"),
                revision=int(prev.get("revision") or 1) + 1, run=run)
    rec["previous_sha256"] = prev.get("sha256"); rec["previous_path"] = prev.get("path"); rec["revision_note"] = str(note)[:300]
    return rec

def compare(a, b):
    """What changed between two drafts of one work: bytes, hash, validation, delivery, revision and
    the shared lineage; for text drafts (medium write) the changed lines too."""
    a, b = a or {}, b or {}
    out = {"same_file": bool(a.get("sha256")) and a.get("sha256") == b.get("sha256"),
           "revision": (a.get("revision"), b.get("revision")), "bytes": (a.get("bytes"), b.get("bytes")),
           "bytes_delta": (int(b.get("bytes") or 0) - int(a.get("bytes") or 0)),
           "validated": (a.get("validated"), b.get("validated")),
           "delivery": ((a.get("delivery") or {}).get("state"), (b.get("delivery") or {}).get("state")),
           "lineage": "b revises a" if b.get("previous_sha256") and b.get("previous_sha256") == a.get("sha256") else
                      ("a revises b" if a.get("previous_sha256") and a.get("previous_sha256") == b.get("sha256") else "unlinked"),
           "note": b.get("revision_note") or a.get("revision_note") or ""}
    if a.get("medium") == "write" and b.get("medium") == "write" and (a.get("text") is not None or b.get("text") is not None):
        import difflib
        d = list(difflib.unified_diff(str(a.get("text", "")).splitlines(), str(b.get("text", "")).splitlines(), lineterm="", n=0))
        out["changed_lines"] = [l for l in d if l[:1] in "+-" and not l.startswith(("+++", "---"))][:40]
    return out

def is_manifest(record):
    return isinstance(record, dict) and all(k in record for k in MANIFEST_FIELDS)

def problems(record):
    """Why a record is not a well-formed manifest (empty list when it is)."""
    out = []
    if not isinstance(record, dict):
        return ["not a dict"]
    for k in MANIFEST_FIELDS:
        if k not in record:
            out.append("missing %s" % k)
    if not out:
        if record["medium"] not in MEDIA:
            out.append("bad medium %r" % (record["medium"],))
        v = record["validated"]
        if not (isinstance(v, dict) and isinstance(v.get("ok"), bool) and v.get("how")):
            out.append("validated must be {ok: bool, how: str}")
        d = record["delivery"]
        if d is not None and not (isinstance(d, dict) and d.get("state") in DELIVERY_STATES and d.get("at")):
            out.append("delivery must be null or {state in %s, at}" % (DELIVERY_STATES,))
        s = record["shared"]
        if s is not None and not (isinstance(s, dict) and s.get("where") and s.get("when")):
            out.append("shared must be null or {where, when}")
        if not isinstance(record["revision"], int) or record["revision"] < 1:
            out.append("revision must be an int >= 1")
    return out

def normalize(record):
    """A legacy record read back with the manifest fields defaulted (a COPY; the store is
    never rewritten by reading). Legacy 'image'/'file' become path; 'want_id' becomes
    source_want; medium is inferred from the extension."""
    r = dict(record or {})
    p = r.get("path") or r.get("image") or r.get("file") or ""
    if "path" not in r: r["path"] = p or None
    if "source_want" not in r: r["source_want"] = r.get("want_id") or None
    if "medium" not in r:
        ext = os.path.splitext(p)[1].lower()
        r["medium"] = ("video" if ext in (".mp4", ".webm", ".mov") else
                       "audio" if ext in (".wav", ".mp3", ".ogg", ".flac") else
                       "image" if ext in (".png", ".jpg", ".jpeg", ".webp") else None)
    for k, dflt in (("run_id", None), ("bytes", None), ("sha256", None), ("revision", 1),
                    ("validated", {"ok": False, "how": "unrecorded"}), ("shared", None), ("delivery", None)):
        r.setdefault(k, dflt)
    return r

def _now(at=None):
    if at is None:
        return datetime.now().isoformat()
    return at.isoformat() if hasattr(at, "isoformat") else str(at)

def mark_delivery(record, state, at=None, why="", channel=None):
    """Record what the SEND did: queued | sent | failed. 'acknowledged' is refused here —
    a send can never testify to a reception (288). A failed send leaves every other
    field alone: the file and the record stay."""
    if state == "acknowledged":
        raise ValueError("a send cannot mark acknowledged; use mark_acknowledged with the reception evidence")
    if state not in DELIVERY_STATES:
        raise ValueError("bad delivery state %r" % (state,))
    record["delivery"] = {"state": state, "at": _now(at)}
    if why: record["delivery"]["why"] = str(why)[:200]
    if channel: record["delivery"]["channel"] = channel
    if state == "sent":
        record["shared"] = {"where": channel or "unknown", "when": _now(at)}
    return record

def mark_acknowledged(record, evidence, at=None):
    """Reception, from evidence that is NOT the send (her reply, a read receipt, her
    opening the file). Only path to 'acknowledged'."""
    if not evidence:
        raise ValueError("acknowledged needs reception evidence")
    prev = record.get("delivery") or {}
    record["delivery"] = dict(prev, state="acknowledged", at=_now(at), evidence=str(evidence)[:200])
    return record

def find_record(records, filename):
    """The record for a shelf file, by manifest path or legacy image/file key."""
    for r in reversed(records or []):
        if isinstance(r, dict) and filename in (r.get("path"), r.get("image"), r.get("file")):
            return r
    return None

def save_ledger(path, obj):
    """Atomic snapshot replacement. Callers doing read/modify/write hold transaction(path)."""
    from store_guard import write_json
    return write_json(path,obj)

def append_ledger(path, record, key=None):
    from store_guard import locked_update
    def mutate(data):
        rows=data.setdefault(key,[]) if key else data
        rows.append(record)
        return data
    locked_update(path,mutate,default={key:[]} if key else [])
    return record


def patch_record(path, identity, changes, field="path"):
    """Patch only this writer's fields on one existing artifact, under the common lock."""
    from store_guard import locked_update
    def mutate(rows):
        for row in rows:
            if row.get(field)==identity: row.update(changes);break
        return rows
    return locked_update(path,mutate,default=[])


def atomic_json(path, obj):
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)

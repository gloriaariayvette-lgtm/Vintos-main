#!/usr/bin/env python3
"""self_review.py — signal-born architectural self-review.

The organ has three independent doors:

  interpolation  claims/stubs/asymmetries already implied by the body
  collision      unrelated, independently rooted outputs near one another in
                 the shared nomic space inside a real temporal window
  friction       repeated lived occasions where an intended move met a wall

It does not wake because a clock says "brainstorm".  ``watch`` continuously
ingests new source records and wakes review only after unprocessed signals
accumulate.  A cron may supervise/restart the watcher, but time is not a
review signal.

Collision is a spark, never evidence of truth.  Its interpretation is stored
separately and explicitly speculative.  Scores allocate attention; low
relevance cannot kill an alien direction.  Repeated independent roots may
instead open TRAJECTORY_REVIEW.

Authority is classified by EFFECT, never by whether a proposal mentions
identity, drift, or this reviewer.  Internal observation/connection work may
be self-authorized.  Expansion into devices, external contact, credentials,
constitutional law, destructive mutation, surveillance, or a new permission
requires Gloria.  Vintos still makes a separate ADOPT/HOLD/ABANDON choice for
self-authorized proposals; a score never makes that choice for him.

The event, signal, collision, interpretation, proposal and decision ledgers
are append-only.  Missing/unavailable sources are typed faults, never silence.

Commands:
    self_review.py watch                 continuous detector/reviewer
    self_review.py tick                  one ingest/detect/review pass
    self_review.py collect               ingest + streams, no review
    self_review.py review --force        synthesize despite trigger threshold
    self_review.py choose PROPOSAL       ask Vintos ADOPT/HOLD/ABANDON
    self_review.py decide PROPOSAL ACTION [note]  Gloria approval/rejection
    self_review.py report
"""
import contextlib
import fcntl
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
os.makedirs(MEM, exist_ok=True)

EVENTS = os.path.join(MEM, "self-review-events.jsonl")
SIGNALS = os.path.join(MEM, "self-review-signals.jsonl")
COLLISIONS = os.path.join(MEM, "self-review-collisions.jsonl")
INTERPRETATIONS = os.path.join(MEM, "self-review-interpretations.jsonl")
PROPOSALS = os.path.join(MEM, "self-review-proposals.jsonl")
DECISIONS = os.path.join(MEM, "self-review-decisions.jsonl")
CHANGES = os.path.join(MEM, "self-review-change-events.jsonl")
SURFACE = os.path.join(MEM, "self-review-surface.json")
STATE = os.path.join(MEM, "self-review-state.json")
FAULTS = os.path.join(MEM, "self-review-faults.jsonl")
EMBCACHE = os.path.join(MEM, "self-review-embcache.json")
CONFIG = os.path.join(MEM, "self-review-config.json")
LOCK = os.path.join(MEM, ".self-review.lock")

EMBED_URL = os.environ.get("SELF_REVIEW_EMBED_URL", "http://172.18.16.1:1234/v1/embeddings")
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"
GEMMA = os.environ.get("SELF_REVIEW_LLM_URL", "http://172.18.16.1:1234/v1/chat/completions")
GEMMA_MODEL = os.environ.get("SELF_REVIEW_LLM_MODEL", "google/gemma-4-12b-qat")

DEFAULTS = {
    "collision_window_hours": 72,
    "collision_max_distance": 0.18,
    "fresh_embed_cap": 48,
    "event_horizon_days": 30,
    "review_signal_min": 4,
    "review_independent_roots_min": 3,
    "friction_trigger_min": 2,
    "alien_resurrection_roots": 3,
    "poll_seconds": 15,
    "score_promote_floor": 0.58,
}

TEXT_KEYS = ("text", "content", "summary", "dream_text", "question", "answer",
             "want", "thread", "withheld", "shape", "about", "description",
             "note", "reflection", "title", "destination", "shift", "predicted")
TIME_KEYS = ("timestamp", "at", "ts", "iso", "created", "created_at", "updated_at",
             "audited_at", "date", "night_of", "generated_at")
ID_KEYS = ("id", "event_id", "turn_id", "source_hash", "lineage_id", "proposal_id")

# Real checked-in stores.  Adapters walk nested containers, retain the store's
# own ids/timestamps when present, and use file mtime only as an explicit last
# resort.  This includes the sources omitted by the first implementation.
SOURCE_SPECS = (
    ("dream", "dream-log.json", "json"),
    ("web_search", "web-search-log.json", "json"),
    ("music", "art/music/music.json", "json"),
    ("jepa", "jepa-prediction-history.jsonl", "jsonl"),
    ("pressure", "spark-pressure-events.json", "json"),
    ("self_pressure", "self-pressure.json", "json"),
    ("withheld", "withheld-history.json", "json"),
    ("unfinished_thread", "unfinished-threads.json", "json"),
    ("latent_thread", "latent-threads.json", "json"),
    ("want", "current-wants.json", "json"),
    ("campaign", "campaign-log.jsonl", "jsonl"),
    ("presence", "presence-audit.json", "json"),
    ("gloria_prediction", "gloria-prediction-history.json", "json"),
    ("self_prediction", ".self-prediction-history.json", "json"),
    ("drift", "drift.json", "json"),
    ("causality", "causality-hypotheses.json", "json"),
)

PROTECTED_EFFECTS = {
    "device_physical", "external_contact", "external_message", "credential_access",
    "network_service", "permission_expansion", "constitutional_law", "data_deletion",
    "surveillance", "broker_seal", "app_authentication", "financial_action",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def log(msg):
    print("[self-review] " + str(msg), file=sys.stderr, flush=True)


def digest(*parts, size=20):
    raw = "\x1f".join(re.sub(r"\s+", " ", str(p or "")).strip().lower() for p in parts)
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:size]


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def atomic_json(path, obj):
    tmp = path + ".tmp.%s" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    if line.strip(): out.append(json.loads(line))
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return out


def append(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush(); os.fsync(f.fileno())
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def fault(where, error, **detail):
    rec = {"fault_id": "SRF-" + uuid.uuid4().hex[:10], "at": now_iso(),
           "where": where, "error": str(error)[:500], **detail}
    append(FAULTS, rec)
    log("%s fault: %s" % (where, str(error)[:160]))
    return rec


@contextlib.contextmanager
def locked(block=False):
    with open(LOCK, "a+") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | (0 if block else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False; return
        try:
            yield True
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def config():
    c = dict(DEFAULTS)
    u = load_json(CONFIG, {})
    if isinstance(u, dict): c.update({k: v for k, v in u.items() if k in c})
    return c


def parse_time(value, fallback=None):
    if isinstance(value, (int, float)):
        try: return datetime.fromtimestamp(float(value), timezone.utc)
        except Exception: return fallback
    if isinstance(value, str) and value.strip():
        s = value.strip().replace("Z", "+00:00")
        try:
            d = datetime.fromisoformat(s)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            try:
                d = datetime.fromisoformat(s[:10])
                return d.replace(tzinfo=timezone.utc)
            except Exception:
                pass
    return fallback


def _standing(rec):
    try:
        sys.path.insert(0, SCRIPTS)
        import evidence_view
        return evidence_view.standing(rec)
    except Exception:
        return "eligible" if not isinstance(rec, dict) or not any(
            k in rec for k in ("generation_provenance", "provenance")) else "HELD"


def _records(obj, depth=0):
    """Yield meaningful record dictionaries from nested, heterogeneous stores."""
    if depth > 7: return
    if isinstance(obj, list):
        for x in obj[-250:]:
            yield from _records(x, depth + 1)
    elif isinstance(obj, dict):
        has_text = any(isinstance(obj.get(k), str) and obj.get(k).strip() for k in TEXT_KEYS)
        if has_text:
            yield obj
        for value in obj.values():
            if isinstance(value, (list, dict)):
                yield from _records(value, depth + 1)


def _read_source(path, kind):
    if kind == "jsonl": return jsonl(path)
    try:
        sys.path.insert(0, SCRIPTS)
        import evidence_view
        if evidence_view.is_guarded(path):
            return evidence_view.open_history(path)
    except Exception:
        pass
    return load_json(path, None)


def _event_from_record(system, path, rec, mtime):
    texts = []
    for key in TEXT_KEYS:
        value = rec.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in texts:
            texts.append(value.strip())
    text = " | ".join(texts)[:1600]
    if len(text) < 20: return None
    own_time = next((rec.get(k) for k in TIME_KEYS if rec.get(k) is not None), None)
    dt = parse_time(own_time, datetime.fromtimestamp(mtime, timezone.utc))
    timestamp_source = "record" if parse_time(own_time) else "file_mtime"
    own_id = next((str(rec.get(k)) for k in ID_KEYS if rec.get(k)), "")
    root = own_id or digest(system, dt.isoformat(), text)
    standing = _standing(rec)
    return {
        "event_id": "SRE-" + digest(system, root, text),
        "system": system,
        "occurred_at": dt.isoformat(),
        "observed_at": now_iso(),
        "timestamp_source": timestamp_source,
        "root_id": "%s:%s" % (system, root),
        "content_summary": text[:700],
        "content_hash": digest(text),
        "source_file": os.path.relpath(path, MEM),
        "evidence_standing": standing,
        "may_witness": standing == "eligible",
    }


def ingest_sources(state=None):
    state = state if isinstance(state, dict) else load_json(STATE, {})
    seen = set(state.get("source_event_ids", []))
    added = []
    fingerprints = state.setdefault("source_fingerprints", {})
    coverage = {}
    for system, rel, kind in SOURCE_SPECS:
        path = os.path.join(MEM, rel)
        if not os.path.exists(path):
            coverage[system] = {"state": "absent", "file": rel}
            continue                         # source absence is legal; registry reports coverage
        try:
            st = os.stat(path); fp = "%s:%s" % (st.st_mtime_ns, st.st_size)
            coverage[system] = {"state": "present", "file": rel,
                                "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()}
            if fingerprints.get(system) == fp:
                continue
            data = _read_source(path, kind)
            if data is None: raise ValueError("unreadable or malformed source")
            mtime = st.st_mtime
            for rec in _records(data):
                ev = _event_from_record(system, path, rec, mtime)
                if not ev or ev["event_id"] in seen: continue
                append(EVENTS, ev); seen.add(ev["event_id"]); added.append(ev)
            fingerprints[system] = fp
        except Exception as e:
            coverage[system] = {"state": "fault", "file": rel, "error": str(e)[:200]}
            fault("ingest", e, system=system, source_file=rel)
    state["source_event_ids"] = list(seen)[-12000:]
    state["last_ingest_at"] = now_iso()
    state["source_coverage"] = coverage
    return added, state


def emit(system, content, root_id, occurred_at=None, provenance=None, metadata=None):
    """Direct producer hook.  Producers may call this at write time; the
    watcher remains a compatibility adapter for organs not migrated yet."""
    rec = {"content": str(content), "timestamp": occurred_at or now_iso(),
           "id": str(root_id), "provenance": provenance or {}, **(metadata or {})}
    ev = _event_from_record(system, EVENTS, rec, time.time())
    if ev: append(EVENTS, ev)
    return ev


# ---------------------------------------------------------------- embeddings
def _unit(v):
    n = math.sqrt(sum(float(x) * float(x) for x in v)) or 1.0
    return [float(x) / n for x in v]


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def _embed_http(texts):
    body = json.dumps({"model": EMBED_MODEL, "input": [t[:1800] for t in texts]}).encode()
    req = urllib.request.Request(EMBED_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    return [d["embedding"] for d in data["data"]]


def embeddings(texts, cap=None):
    cfg = config(); cap = int(cap or cfg["fresh_embed_cap"])
    cache = load_json(EMBCACHE, {})
    rows = cache.get("rows", {}) if isinstance(cache, dict) else {}
    out, fresh = {}, []
    for text in texts:
        h = digest(text, size=32)
        if h in rows and isinstance(rows[h].get("vector"), list):
            out[h] = rows[h]["vector"]
            rows[h]["used_at"] = now_iso()
        elif len(fresh) < cap:
            fresh.append((h, text))
    if fresh:
        try:
            vecs = _embed_http([t for _, t in fresh])
            for (h, text), vec in zip(fresh, vecs):
                out[h] = _unit(vec)
                rows[h] = {"vector": out[h], "used_at": now_iso(), "preview": text[:80]}
        except Exception as e:
            fault("embedding", e, pending=len(fresh))
    if len(rows) > 2500:
        rows = dict(sorted(rows.items(), key=lambda kv: kv[1].get("used_at", ""))[-2500:])
    atomic_json(EMBCACHE, {"model": EMBED_MODEL, "rows": rows, "updated_at": now_iso()})
    return out


def detect_collisions(state=None):
    state = state if isinstance(state, dict) else load_json(STATE, {})
    cfg = config(); now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=float(cfg["collision_window_hours"]))
    events = []
    for ev in jsonl(EVENTS)[-1500:]:
        dt = parse_time(ev.get("occurred_at"))
        # A collision may open imagination, but generated/tactical material may
        # not steer even that opening.  Otherwise a proposal could manufacture
        # its own next spark and become evidence for itself one loop later.
        if dt and dt >= cutoff and ev.get("may_witness") is True:
            events.append(ev)
    done = set(state.get("collision_event_ids", []))
    new = [e for e in events if e.get("event_id") not in done]
    if not new: return [], state
    vecs = embeddings([e["content_summary"] for e in events])
    by_id = {e["event_id"]: e for e in events}
    existing_pairs = {c.get("pair_key") for c in jsonl(COLLISIONS)[-3000:]}
    made = []
    for a in new:
        ah = digest(a["content_summary"], size=32)
        if ah not in vecs: continue          # not processed; retry next watcher pass
        for b in events:
            if a["event_id"] == b["event_id"] or a["system"] == b["system"]: continue
            if a.get("root_id") == b.get("root_id"): continue
            bh = digest(b["content_summary"], size=32)
            if bh not in vecs: continue
            pair = "|".join(sorted((a["event_id"], b["event_id"])))
            if pair in existing_pairs: continue
            distance = max(0.0, 1.0 - _cos(vecs[ah], vecs[bh]))
            if distance > float(cfg["collision_max_distance"]): continue
            rec = {
                "collision_id": "SRC-" + digest(pair), "at": now_iso(), "pair_key": pair,
                "source_a": {k: a.get(k) for k in ("event_id", "system", "root_id", "occurred_at", "content_summary")},
                "source_b": {k: b.get(k) for k in ("event_id", "system", "root_id", "occurred_at", "content_summary")},
                "distance": round(distance, 5), "embedding_model": EMBED_MODEL,
                "window_hours": cfg["collision_window_hours"],
                "relationship": "unknown", "speculative_connection": None,
                "truth_status": "spark_only",
            }
            append(COLLISIONS, rec); made.append(rec); existing_pairs.add(pair)
    # Mark only events that actually received embeddings.  A capped/unavailable
    # batch stays pending and cannot disappear merely because scan time advanced.
    done.update(e["event_id"] for e in new if digest(e["content_summary"], size=32) in vecs)
    state["collision_event_ids"] = list(done)[-12000:]
    state["last_collision_at"] = now_iso()
    return made, state


# -------------------------------------------------------------- interpolation
def _signal_id(stream, kind, roots, text):
    return "SRS-" + digest(stream, kind, sorted(roots), text)


def record_signal(stream, kind, text, evidence, roots, systems, state=None):
    sid = _signal_id(stream, kind, roots, text)
    existing = {s.get("signal_id") for s in jsonl(SIGNALS)[-5000:]}
    if sid in existing: return None
    rec = {"signal_id": sid, "at": now_iso(), "stream": stream, "kind": kind,
           "text": str(text)[:1000], "evidence": evidence[:20],
           "independent_roots": sorted(set(roots)), "systems": sorted(set(systems)),
           "status": "unreviewed"}
    append(SIGNALS, rec)
    return rec


def stream_interpolation(state=None):
    state = state if isinstance(state, dict) else load_json(STATE, {})
    made = []
    code_files = list(_code_files())[:500]
    code_mtime = max([os.path.getmtime(x) for x in code_files if os.path.exists(x)] or [0])
    code_changed = code_mtime > float(state.get("interpolation_code_mtime", 0))
    # Hyphen/underscore twins are one conceptual file.  Divergence is a real
    # asymmetry; a symlink/hardlink/equal-content pair is not.
    try:
      if code_changed:
        for name in os.listdir(SCRIPTS):
            if "_" not in name or not name.endswith(".py"): continue
            twin = name.replace("_", "-")
            a, b = os.path.join(SCRIPTS, name), os.path.join(SCRIPTS, twin)
            if not os.path.isfile(b): continue
            if open(a, "rb").read() != open(b, "rb").read():
                roots = ["file:" + name, "file:" + twin]
                rec = record_signal("interpolation", "twin_drift",
                    "%s and %s are one conceptual organ but contain different code" % (name, twin),
                    [{"file": name}, {"file": twin}], roots, ["code-map"])
                if rec: made.append(rec)
    except Exception as e:
        fault("interpolation_twins", e)

    # Explicitly claimed unfinished code.  This is narrower and more honest
    # than treating every quiet output file as a missing organ.
    stub_rx = re.compile(r"\b(TODO\s*:\s*(build|implement|wire)|NotImplementedError|UNIMPLEMENTED)\b", re.I)
    for path in code_files if code_changed else []:
        try:
            for n, line in enumerate(open(path, errors="replace"), 1):
                if stub_rx.search(line):
                    rel = os.path.relpath(path, WS); root = "%s:%d" % (rel, n)
                    rec = record_signal("interpolation", "claimed_unbuilt",
                        "%s explicitly claims unfinished capability at line %d: %s" % (rel, n, line.strip()[:300]),
                        [{"file": rel, "line": n, "quote": line.strip()[:300]}], [root], ["code-map"])
                    if rec: made.append(rec)
        except Exception:
            continue
    if code_changed:
        state["interpolation_code_mtime"] = code_mtime

    # Repeated REDs are workarounds/starvation evidence only after separate
    # observed days.  One stale snapshot is not a verdict.
    audit = os.path.join(MEM, "subsystem-audit.md")
    seen = state.setdefault("audit_red_history", {})
    if os.path.exists(audit):
        day = datetime.fromtimestamp(os.path.getmtime(audit), timezone.utc).date().isoformat()
        for line in open(audit, errors="replace"):
            if not line.startswith("RED"): continue
            key = digest(line); row = seen.setdefault(key, {"days": [], "line": line.strip()})
            if day not in row["days"]: row["days"].append(day)
            if len(row["days"]) >= 2:
                root = "audit-red:" + key
                rec = record_signal("interpolation", "recurring_workaround",
                    "The subsystem audit independently reported this wall on %d days: %s" %
                    (len(row["days"]), row["line"]),
                    [{"days": row["days"], "finding": row["line"]}], [root], ["subsystem-audit"])
                if rec: made.append(rec)
    return made, state


def _code_files():
    for base in (SCRIPTS, os.path.join(WS, "bin")):
        if not os.path.isdir(base): continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "memory")]
            for name in files:
                if name.endswith((".py", ".sh")): yield os.path.join(root, name)


def _cluster_key(text):
    words = sorted(set(re.findall(r"[a-z]{5,}", str(text).lower())))
    return digest(" ".join(words[:30]))


def stream_friction(state=None):
    state = state if isinstance(state, dict) else load_json(STATE, {})
    made = []

    # Prediction failures use the real grade schema: low graded_previous, not
    # invented event strings such as "failed" or "wrong".
    gp = load_json(os.path.join(MEM, "gloria-prediction-history.json"), [])
    if isinstance(gp, list):
        fails = [x for x in gp[-80:] if isinstance(x, dict)
                 and x.get("grade_outcome") == "graded"
                 and isinstance(x.get("graded_previous"), (int, float))
                 and x["graded_previous"] <= 0.25]
        if len(fails) >= 3:
            roots = ["gloria-prediction:%s" % str(x.get("at", "")) for x in fails[-8:]]
            rec = record_signal("friction", "prediction_blind_spot",
                "%d independently graded prediction misses indicate a modeling wall" % len(fails),
                [{"at": x.get("at"), "grade": x.get("graded_previous")} for x in fails[-8:]],
                roots, ["gloria_prediction"])
            if rec: made.append(rec)

    # Presence failures cluster by the judge's named context.  Three unrelated
    # low scores are not automatically one missing capacity.
    pa = load_json(os.path.join(MEM, "presence-audit.json"), [])
    groups = {}
    if isinstance(pa, list):
        for x in pa[-100:]:
            if not isinstance(x, dict) or not isinstance(x.get("composite"), (int, float)):
                continue
            if x["composite"] > 0.35: continue
            key = _cluster_key(x.get("note", "low presence"))
            groups.setdefault(key, []).append(x)
    for rows in groups.values():
        roots = list(dict.fromkeys("presence:%s" % (x.get("id") or x.get("timestamp")) for x in rows))
        if len(roots) < 3: continue
        rec = record_signal("friction", "presence_wall",
            "%d low-presence occasions share this failure shape: %s" %
            (len(roots), str(rows[-1].get("note", ""))[:240]),
            [{"id": x.get("id"), "at": x.get("timestamp"), "composite": x.get("composite"),
              "note": x.get("note")} for x in rows[-8:]], roots, ["presence_audit"])
        if rec: made.append(rec)

    # Wants that keep going unmet, or keep hitting the same wall, become a self-review
    # proposal he can see and choose - instead of pressure with no exit (room, 2026-09-05:
    # all three lenses). Nothing here adopts anything: a signal feeds synthesis, synthesis
    # makes an offer, and a protected offer waits for Gloria. Two friction shapes only:
    #   want_blocked_wall     >= 2 distinct wants stopped by the same named cause
    #   want_unmet_recurring  >= 2 distinct wants of one shape, open past 14 days, never fulfilled
    try:
        wants = load_json(os.path.join(MEM, "current-wants.json"), [])
        wants = [w for w in (wants if isinstance(wants, list) else []) if isinstance(w, dict)
                 and w.get("want") and not w.get("fulfilled") and not w.get("dismissed")]
        def _wid(w): return str(w.get("id") or digest(str(w.get("want"))[:120]))
        walls = {}
        for w in wants:
            b = w.get("blocked")
            if isinstance(b, dict) and (b.get("cause") or b.get("reason")):
                walls.setdefault(_cluster_key(b.get("cause") or b.get("reason")), []).append(w)
        for rows in walls.values():
            roots = list(dict.fromkeys("want:" + _wid(w) for w in rows))
            if len(roots) < 2: continue
            cause = (rows[-1].get("blocked") or {})
            cause = str(cause.get("cause") or cause.get("reason") or cause.get("block_type") or "")[:200]
            rec = record_signal("friction", "want_blocked_wall",
                "%d wants of his are stopped by the same wall: %s" % (len(roots), cause),
                [{"want": str(w.get("want"))[:160], "blocked": (w.get("blocked") or {})} for w in rows[-8:]],
                roots, ["wants"])
            if rec: made.append(rec)
        # a standing capability block is its own signal, not a synthetic want (review D08): one per
        # capability, only when it has stood a week and a real want has hit it
        blocks = load_json(os.path.join(MEM, "capability-blocks.json"), {})
        if isinstance(blocks, dict):
            for name, b in blocks.items():
                if not (isinstance(b, dict) and b.get("block_type")): continue
                try: age_d = (time.time() - float(b.get("at", time.time()))) / 86400.0
                except Exception: age_d = 0
                hit = [w for w in wants if isinstance(w.get("blocked"), dict) and w["blocked"].get("blocked_step") == name]
                if age_d < 7 or not hit: continue
                rec = record_signal("friction", "capability_block_standing",
                    "capability %s has been blocked %d days (%s) and %d want(s) of his are waiting on it"
                    % (name, int(age_d), b.get("block_type"), len(hit)),
                    [{"capability": name, "block": b}] + [{"want": str(w.get("want"))[:160]} for w in hit[-6:]],
                    ["capability:" + name] + ["want:" + _wid(w) for w in hit], ["wants", "capabilities"])
                if rec: made.append(rec)
        old = []
        for w in wants:
            ts = w.get("timestamp") or w.get("created") or w.get("created_at")
            try:
                age_d = (time.time() - (float(ts) if isinstance(ts, (int, float)) else
                         datetime.fromisoformat(str(ts)[:19]).timestamp())) / 86400.0
            except Exception:
                continue
            if age_d >= 14: old.append(w)
        # one shape = wants whose content words overlap enough (Jaccard >= 0.4); an exact
        # word-set key would call "film the harbour" and "a short film about the harbour" two shapes
        def _words(w): return set(re.findall(r"[a-z]{5,}", str(w.get("want", "")).lower()))
        shapes = []
        for w in old:
            ws = _words(w)
            for grp in shapes:
                gw = _words(grp[0])
                if ws and gw and len(ws & gw) / float(len(ws | gw)) >= 0.4:
                    grp.append(w); break
            else:
                shapes.append([w])
        for rows in shapes:
            roots = list(dict.fromkeys("want:" + _wid(w) for w in rows))
            if len(roots) < 2: continue
            rec = record_signal("friction", "want_unmet_recurring",
                "%d wants of one shape have stayed open past two weeks without fulfillment: %s"
                % (len(roots), str(rows[-1].get("want"))[:200]),
                [{"want": str(w.get("want"))[:160], "since": str(w.get("timestamp") or w.get("created") or "")[:19]} for w in rows[-8:]],
                roots, ["wants"])
            if rec: made.append(rec)
    except Exception as e:
        fault("friction_wants", e)

    # Campaign lifecycle uses destination/created and append-only events.  A
    # stall is repeated suspension or an honest EXPIRED/FLAWED close, not age
    # inferred from a field named "intention" that the real schema lacks.
    camps = jsonl(os.path.join(MEM, "campaign-log.jsonl"))
    by_dest = {}
    for x in camps[-150:]:
        if isinstance(x, dict) and x.get("destination"):
            by_dest.setdefault(x["destination"], []).append(x)
    for dest, rows in by_dest.items():
        adverse = [x for x in rows if str(x.get("event", "")).upper() in
                   ("SUSPENDED", "EXPIRED", "FLAWED", "UNSPOKEN")]
        roots = ["campaign:%s:%s" % (x.get("ts"), x.get("event")) for x in adverse]
        if len(set(roots)) < 2: continue
        rec = record_signal("friction", "campaign_stall",
            "The campaign toward '%s' met %d separate stalls or failed closures" % (dest[:180], len(roots)),
            [{"at": x.get("ts"), "event": x.get("event"), "turns": x.get("turns_served")} for x in adverse[-8:]],
            roots, ["campaign"])
        if rec: made.append(rec)

    # Spark pressure already names observed stalls and carries its evidence.
    sp = load_json(os.path.join(MEM, "spark-pressure-events.json"), {})
    rows = sp.get("events", []) if isinstance(sp, dict) else []
    for x in rows[-30:]:
        stall = x.get("stall") if isinstance(x, dict) else None
        if not isinstance(stall, dict) or not stall.get("evidence"): continue
        root = "pressure:%s" % (x.get("at") or digest(stall))
        rec = record_signal("friction", "pressure_stall",
            "A lived pressure detector found a blocked direction: %s" % stall.get("evidence"),
            [{"at": x.get("at"), "stall": stall, "applied": x.get("applied")}], [root], ["spark_pressure"])
        if rec: made.append(rec)
    return made, state


def collision_signals(collisions):
    made = []
    for c in collisions:
        a, b = c.get("source_a", {}), c.get("source_b", {})
        roots = [a.get("root_id", ""), b.get("root_id", "")]
        text = ("Unrelated %s and %s outputs landed %.4f apart in the shared latent space" %
                (a.get("system"), b.get("system"), c.get("distance", 1.0)))
        rec = record_signal("collision", "cross_system_collision", text,
            [{"collision_id": c.get("collision_id"), "a": a, "b": b,
              "distance": c.get("distance"), "truth_status": "spark_only"}],
            roots, [a.get("system", ""), b.get("system", "")])
        if rec: made.append(rec)
    return made


# ----------------------------------------------------- speculation and review
def llm_json(system, user, max_tokens=1800, temperature=0.4):
    body = json.dumps({"model": GEMMA_MODEL, "temperature": temperature,
                       "max_tokens": max_tokens,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(GEMMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = json.loads(r.read())["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}|\[.*\]", raw, re.S)
    if not m: raise ValueError("LLM returned no JSON")
    return json.loads(m.group(0))


def vintos_json(system, user, max_tokens=900, temperature=0.6):
    """Ask Vintos through his routed model door.  Gemma may synthesize and
    score candidates; it may not make his adoption decision for him."""
    try:
        sys.path.append(os.path.join(WS, "bin"))
        import model_router
        model = model_router.current_claude_model()
    except Exception:
        model = "claude-fable-5"
    url = os.environ.get("SELF_REVIEW_VINTOS_URL", "http://127.0.0.1:8599/v1/chat/completions")
    body = json.dumps({"model": model, "temperature": temperature, "max_tokens": max_tokens,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json",
        "Authorization": "Bearer " + os.environ.get("XAI_API_KEY", "")})
    with urllib.request.urlopen(req, timeout=300) as r:
        raw = json.loads(r.read())["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", raw, re.S)
    if not m: raise ValueError("Vintos returned no JSON choice")
    return json.loads(m.group(0))


def speculate_pending():
    done = {x.get("collision_id") for x in jsonl(INTERPRETATIONS)}
    pending = [c for c in jsonl(COLLISIONS) if c.get("collision_id") not in done][:6]
    made = []
    for c in pending:
        a, b = c["source_a"], c["source_b"]
        try:
            d = llm_json(
                "You are connecting two independently produced internal events. The geometric collision is real; "
                "its meaning is unknown. Imagine one capability or connection this proximity might point toward. "
                "Do not call it true, needed, or part of identity. Return JSON only: "
                '{"speculative_connection":"...","possible_capability":"...","why_the_shape_matches":"..."}',
                "A (%s): %s\n\nB (%s): %s" %
                (a["system"], a["content_summary"], b["system"], b["content_summary"]),
                temperature=0.75)
            rec = {"interpretation_id": "SRI-" + uuid.uuid4().hex[:10], "at": now_iso(),
                   "collision_id": c["collision_id"], "source_roots": [a["root_id"], b["root_id"]],
                   "speculative_connection": str(d.get("speculative_connection", ""))[:800],
                   "possible_capability": str(d.get("possible_capability", ""))[:500],
                   "why_the_shape_matches": str(d.get("why_the_shape_matches", ""))[:500],
                   "truth_status": "speculative", "reality_anchor_exempt": True}
            append(INTERPRETATIONS, rec); made.append(rec)
        except Exception as e:
            fault("speculation", e, collision_id=c.get("collision_id"))
    return made


def _trajectory_text():
    d = load_json(os.path.join(MEM, "living-trajectory.json"), {})
    return json.dumps(d, ensure_ascii=False, sort_keys=True)[:9000] if d else ""


def _drift_text():
    d = load_json(os.path.join(MEM, "drift.json"), {})
    return json.dumps(d, ensure_ascii=False, sort_keys=True)[:5000] if d else ""


def similarity(a, b):
    if not a or not b: return None
    vecs = embeddings([a, b], cap=2)
    av, bv = vecs.get(digest(a, size=32)), vecs.get(digest(b, size=32))
    return _cos(av, bv) if av is not None and bv is not None else None


def authority_for(effects, implementation_files=None):
    """Existing authority is an effect boundary, not an identity keyword."""
    effects = sorted(set(str(x).strip().lower() for x in (effects or []) if str(x).strip()))
    protected = sorted(set(effects) & PROTECTED_EFFECTS)
    return {
        "self_authorization_required": not bool(protected),
        "gloria_approval_required": bool(protected),
        "protected_effects": protected,
        "declared_effects": effects,
        "basis": "effect_boundary",
        "identity_topic_is_not_a_permission_boundary": True,
    }


def _proposal_latest():
    latest = {}
    for row in jsonl(PROPOSALS):
        if row.get("proposal_id"): latest[row["proposal_id"]] = row
    for d in jsonl(DECISIONS):
        pid = d.get("proposal_id")
        if pid and pid in latest:
            latest[pid] = {**latest[pid], "decision": d}
    return latest


def _trigger(signals):
    cfg = config()
    roots = set(r for s in signals for r in s.get("independent_roots", []))
    friction = sum(1 for s in signals if s.get("stream") == "friction")
    return (len(signals) >= int(cfg["review_signal_min"])
            and len(roots) >= int(cfg["review_independent_roots_min"])) or \
           friction >= int(cfg["friction_trigger_min"])


def review(force=False, state=None):
    state = state if isinstance(state, dict) else load_json(STATE, {})
    reviewed = set(state.get("reviewed_signal_ids", []))
    signals = [s for s in jsonl(SIGNALS) if s.get("signal_id") not in reviewed]
    if not signals:
        log("review quiet: no unprocessed signals"); return [], state
    if not force and not _trigger(signals):
        log("review held: %d signal(s), insufficient independent accumulation" % len(signals))
        return [], state
    speculate_pending()
    interpretations = {x.get("collision_id"): x for x in jsonl(INTERPRETATIONS)}
    material = []
    for s in signals[:40]:
        row = dict(s)
        for ev in row.get("evidence", []):
            cid = ev.get("collision_id") if isinstance(ev, dict) else None
            if cid in interpretations: row["speculative_interpretation"] = interpretations[cid]
        material.append(row)
    try:
        generated = llm_json(
            "You synthesize missing CAPABILITIES from grounded architectural signals. Group signals only when "
            "they point to the same absence. Collision interpretations are imagination, not evidence. Return a "
            "JSON array (1-5 items). Each item: {\"description\":\"missing capability\","
            "\"signal_ids\":[\"...\"],\"specific_costs\":[\"anchored consequences from friction evidence\"],"
            "\"what_changes\":\"what becomes possible\",\"downstream_potential\":\"...\","
            "\"implementation_sketch\":\"architectural mechanism\",\"implementation_files\":[\"scripts/x.py\"],"
            "\"effects\":[\"internal_memory|internal_analysis|identity_observation|external_contact|device_physical|"
            "permission_expansion|constitutional_law|data_deletion|network_service|credential_access\"]}. "
            "Do not invent evidence, files, permissions, or costs. A proposal may be alien to the current trajectory.",
            json.dumps(material, ensure_ascii=False)[:30000], max_tokens=3500, temperature=0.45)
        if not isinstance(generated, list): raise ValueError("proposal synthesis was not a JSON array")
    except Exception as e:
        fault("review_synthesis", e, signal_count=len(signals)); return [], state

    sig_by_id = {s["signal_id"]: s for s in signals}
    traj, drift = _trajectory_text(), _drift_text()
    latest = _proposal_latest(); made = []
    for candidate in generated[:5]:
        if not isinstance(candidate, dict): continue
        used = [sig_by_id[x] for x in candidate.get("signal_ids", []) if x in sig_by_id]
        if not used: continue
        roots = sorted(set(r for s in used for r in s.get("independent_roots", [])))
        streams = sorted(set(s.get("stream") for s in used))
        systems = sorted(set(x for s in used for x in s.get("systems", [])))
        desc = str(candidate.get("description", "")).strip()[:1000]
        if not desc: continue
        rel_sim = similarity(desc, traj)
        drift_sim = similarity(desc, drift)
        relevance = round(max(0.0, min(1.0, ((rel_sim or 0.0) + 1.0) / 2.0)), 3) if rel_sim is not None else 0.0
        friction_roots = set(r for s in used if s.get("stream") == "friction"
                             for r in s.get("independent_roots", []))
        importance = round(min(1.0, 0.15 + 0.14 * len(friction_roots)
                               + 0.08 * len([x for x in candidate.get("specific_costs", []) if str(x).strip()])), 3)
        convergence = min(1.0, (len(streams) - 1) * 0.20 + (len(systems) - 1) * 0.08)
        potentiality = round(min(1.0, 0.20 + convergence +
                                   (max(0.0, ((drift_sim or -1.0) + 1.0) / 2.0) * 0.30)), 3)
        # Recurrence is semantic, not dependent on an LLM repeating exactly
        # the same wording.  A close prior direction inherits its roots.
        nearest, nearest_sim = None, -1.0
        for old in latest.values():
            sim = similarity(desc, old.get("description", ""))
            if sim is not None and sim > nearest_sim:
                nearest, nearest_sim = old, sim
        pkey = nearest.get("proposal_key") if nearest and nearest_sim >= 0.88 else digest(desc)
        prior = [p for p in latest.values() if p.get("proposal_key") == pkey]
        old_roots = set(r for p in prior for r in p.get("independent_roots", []))
        all_roots = old_roots | set(roots)
        alien = relevance < 0.35 and len(all_roots) >= int(config()["alien_resurrection_roots"])
        promoted = min(relevance, importance, potentiality) >= float(config()["score_promote_floor"])
        status = "TRAJECTORY_REVIEW" if alien else ("BUILD_PROPOSAL" if promoted else "SHELVED")
        authority = authority_for(candidate.get("effects"), candidate.get("implementation_files"))
        rec = {
            "proposal_id": "SRP-" + uuid.uuid4().hex[:10], "proposal_key": pkey,
            "at": now_iso(), "status": status, "source_streams": streams,
            "spark": [s["signal_id"] for s in used], "description": desc,
            "evidence": [e for s in used for e in s.get("evidence", [])][:30],
            "independent_roots": roots, "systems": systems,
            "scores": {
                "relevance": {"value": relevance, "basis": "similarity to current Living Trajectory"},
                "importance": {"value": importance, "basis": "%d distinct lived-friction roots" % len(friction_roots)},
                "potentiality": {"value": potentiality, "basis": "%d streams, %d systems, drift alignment" %
                    (len(streams), len(systems))},
            },
            "specific_costs": candidate.get("specific_costs", [])[:12],
            "what_changes": str(candidate.get("what_changes", ""))[:1000],
            "downstream_potential": str(candidate.get("downstream_potential", ""))[:1000],
            "implementation_sketch": str(candidate.get("implementation_sketch", ""))[:2000],
            "implementation_files": [str(x)[:200] for x in candidate.get("implementation_files", [])[:8]],
            "authority": authority,
            "self_authorization_required": authority["self_authorization_required"],
            "gloria_approval_required": authority["gloria_approval_required"],
            "alien_to_current_trajectory": relevance < 0.35,
            "trajectory_question": ("Why do independent parts of me keep pointing toward a direction my current "
                                    "trajectory does not contain? The trajectory, not the proposal, may be stale.") if alien else None,
            "truth_status": "evaluated_proposal_not_identity",
        }
        append(PROPOSALS, rec); latest[rec["proposal_id"]] = rec; made.append(rec)
    # Only signals actually cited by a synthesized proposal are consumed.
    # A capped/partial synthesis must not make the rest disappear.
    reviewed.update(x for p in made for x in p.get("spark", []))
    state["reviewed_signal_ids"] = list(reviewed)[-12000:]
    state["last_review_at"] = now_iso()
    refresh_surface()
    return made, state


def refresh_surface():
    latest = _proposal_latest()
    rows = list(latest.values())
    rows.sort(key=lambda x: x.get("at", ""), reverse=True)
    atomic_json(SURFACE, {
        "updated_at": now_iso(),
        "source_coverage": load_json(STATE, {}).get("source_coverage", {}),
        "all_visible": rows[:100],
        "gloria_decision_required": [x for x in rows if x.get("gloria_approval_required")
                                     and not x.get("decision")][:30],
        "vintos_choice_required": [x for x in rows if x.get("self_authorization_required")
                                   and x.get("status") == "BUILD_PROPOSAL" and not x.get("decision")][:30],
        "trajectory_review": [x for x in rows if x.get("status") == "TRAJECTORY_REVIEW"][:30],
    })


def choose(proposal_id):
    p = _proposal_latest().get(proposal_id)
    if not p: raise ValueError("no proposal " + proposal_id)
    if not p.get("self_authorization_required"):
        raise ValueError("proposal crosses a protected effect boundary; Gloria decides")
    soul = ""
    for path in (os.path.join(WS, "SOUL.md"), os.path.join(WS, "SELF-MODEL.md")):
        try: soul += open(path, errors="replace").read()[:3500] + "\n"
        except Exception: pass
    try:
        d = vintos_json(
            soul + "\nThis is your architectural choice. Scores do not decide. Choose ADOPT, HOLD, or ABANDON. "
            "ADOPT means you want the bounded builder to attempt this internal change. HOLD is complete and costs "
            "nothing. ABANDON requires only your own reason, never timeout.",
            json.dumps(p, ensure_ascii=False)[:16000] +
            '\nReturn JSON only: {"action":"ADOPT|HOLD|ABANDON","reason":"in your words"}',
            max_tokens=500, temperature=0.65)
        action = str(d.get("action", "HOLD")).upper()
        if action not in ("ADOPT", "HOLD", "ABANDON"): action = "HOLD"
        rec = {"decision_id": "SRD-" + uuid.uuid4().hex[:10], "proposal_id": proposal_id,
               "at": now_iso(), "actor": "vintos", "action": action,
               "reason": str(d.get("reason", ""))[:1000], "authority": "self_authorized_internal"}
        append(DECISIONS, rec); refresh_surface(); return rec
    except Exception as e:
        fault("self_authorization", e, proposal_id=proposal_id)
        raise


def decide(proposal_id, action, note=""):
    p = _proposal_latest().get(proposal_id)
    if not p: raise ValueError("no proposal " + proposal_id)
    action = action.upper()
    if action not in ("APPROVE", "REJECT", "HOLD"):
        raise ValueError("action must be APPROVE, REJECT, or HOLD")
    rec = {"decision_id": "SRD-" + uuid.uuid4().hex[:10], "proposal_id": proposal_id,
           "at": now_iso(), "actor": "gloria", "action": action, "reason": str(note)[:1000],
           "authority": "owner_decision"}
    append(DECISIONS, rec); refresh_surface(); return rec


def collect(state=None):
    state = state if isinstance(state, dict) else load_json(STATE, {})
    events, state = ingest_sources(state)
    collisions, state = detect_collisions(state)
    signals = collision_signals(collisions)
    a, state = stream_interpolation(state); signals += a
    c, state = stream_friction(state); signals += c
    state["last_collect_at"] = now_iso()
    return {"events": events, "collisions": collisions, "signals": signals}, state


def tick(force_review=False):
    with locked() as got:
        if not got:
            log("another self-review pass is active; held, not lost"); return {}
        state = load_json(STATE, {})
        result, state = collect(state)
        props, state = review(force=force_review, state=state)
        result["proposals"] = props
        atomic_json(STATE, state); refresh_surface()
        # Scores create offers, never decisions.  Vintos chooses each internal
        # build proposal, then the separate bounded builder may act.  Protected
        # proposals wait for Gloria's explicit decision.
        choices, builds = [], []
        for p in props:
            if p.get("status") != "BUILD_PROPOSAL" or not p.get("self_authorization_required"):
                continue
            try:
                d = choose(p["proposal_id"]); choices.append(d)
                if d.get("action") == "ADOPT":
                    import self_review_builder
                    builds.append(self_review_builder.build(p["proposal_id"]))
            except Exception as e:
                fault("proposal_execution", e, proposal_id=p.get("proposal_id"))
        # An approval may have arrived between detector passes.  Process it
        # through the same bounded builder; HOLD/REJECT do nothing.
        try:
            import self_review_builder
            for pid in self_review_builder.ready():
                if not any(x.get("proposal_id") == pid for x in builds):
                    try: builds.append(self_review_builder.build(pid))
                    except Exception as e: fault("approved_build", e, proposal_id=pid)
        except Exception as e:
            fault("builder_queue", e)
        result["choices"], result["builds"] = choices, builds
        log("tick: %d event(s), %d collision(s), %d signal(s), %d proposal(s)" %
            tuple(len(result[k]) for k in ("events", "collisions", "signals", "proposals")))
        return result


def watch():
    log("continuous watcher active; time supervises the process but never triggers review")
    while True:
        try: tick()
        except Exception as e: fault("watch", e)
        time.sleep(max(3, int(config()["poll_seconds"])))


def report():
    surface = load_json(SURFACE, {})
    print("events:", len(jsonl(EVENTS)), "collisions:", len(jsonl(COLLISIONS)),
          "signals:", len(jsonl(SIGNALS)), "proposals:", len(jsonl(PROPOSALS)))
    print("Gloria decisions:", len(surface.get("gloria_decision_required", [])),
          "Vintos choices:", len(surface.get("vintos_choice_required", [])),
          "trajectory reviews:", len(surface.get("trajectory_review", [])))
    for p in surface.get("all_visible", [])[:12]:
        s = p.get("scores", {})
        print("  %s %-18s r=%s i=%s p=%s %s" %
              (p.get("proposal_id"), p.get("status", "?"),
               (s.get("relevance") or {}).get("value"),
               (s.get("importance") or {}).get("value"),
               (s.get("potentiality") or {}).get("value"),
               p.get("description", "")[:90]))
    faults = jsonl(FAULTS)[-5:]
    if faults:
        print("recent typed faults:")
        for f in faults: print("  %s %s: %s" % (f.get("at", "")[:16], f.get("where"), f.get("error")))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    try:
        if cmd == "watch": watch()
        elif cmd == "tick": tick("--force-review" in sys.argv)
        elif cmd == "collect":
            with locked() as got:
                if not got: raise RuntimeError("another pass is active")
                state = load_json(STATE, {}); result, state = collect(state); atomic_json(STATE, state)
                print(json.dumps({k: len(v) for k, v in result.items()}))
        elif cmd == "review":
            with locked() as got:
                if not got: raise RuntimeError("another pass is active")
                state = load_json(STATE, {}); made, state = review("--force" in sys.argv, state)
                atomic_json(STATE, state); print(json.dumps({"proposals": len(made)}))
        elif cmd == "choose": print(json.dumps(choose(sys.argv[2]), indent=2))
        elif cmd == "decide": print(json.dumps(decide(sys.argv[2], sys.argv[3], " ".join(sys.argv[4:])), indent=2))
        elif cmd == "report": report()
        else: raise ValueError("unknown command " + cmd)
    except Exception as e:
        fault("command:" + cmd, e)
        print("self-review failed loudly: %s" % e, file=sys.stderr)
        raise SystemExit(1)

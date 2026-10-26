#!/usr/bin/env python3
"""work_episodes.py - from one of his works back to the occasion it came from, and how he read it later.

Codex's design 03 (25 October, approved by Gloria): "this resembles what we are talking about" and "this came from
that occasion" are different claims. The first is a search result (media_embed.py). The second needs a source record.
This is a rebuildable projection over records that already exist; it writes no store of its own except two
content-free logs (ids and sizes only) for what was offered to him and what his reply actually used.

Four kinds of record, kept apart:
  artifact       a work's revision, identified by its content hash (sha256), never by its title or minute
  episode        an actual source event: the want it answered, the moment that want was fulfilled, the completion row
  reading        a dated interpretation: what he wrote at the making, how he read it when he saw it, a durable
                 memory's later rereadings. Never merged into the event it reads.
  relation       an explicit edge, saying what supports it:
                   produced_in    from an operation receipt (the shelf record names the want / the run)
                   produced_from  from a receipt naming another work (a video made from a painting, a remake)
                   he_linked      from his own words naming the work exactly (file name, or a title no other work has)
                   co_present     from a bounded observed occasion (her shared song was in the composer's context).
                                  Present, not a cause, and rendered that way.
A title collision, a near timestamp or a high cosine score never makes an edge. A dream-made painting with no dream id
stays "from a dream, not linked". An absent source stays absent.

Eligibility is checked when he looks, not when the projection was built: the projection is rebuilt whenever any
source file changes (size or mtime), so a withdrawn want or an invalidated durable memory is gone from the next turn.
Records go through evidence_view.standing(); HELD and ineligible records are listed, never rendered into his context.
Everything here is a record of his own life and his own creations; none of it is offered as independent evidence.

Never read: Landings notes or ratings (her private wording has its own path: the weekly Gloria-model pass), and any
Atelier store or sealed artifact (atelier-*.json, a shelf record marked sealed, a path under an atelier directory).
The sources are named in SOURCES and nothing else is opened.

Cost: no model call, no GPU. In a chat the added context is capped at TURN_CHARS a turn and DAILY_CHARS a day
(about 3,000 tokens a day, the $0.02/day ceiling in the design at the chat model's input price); past the cap the
plain works block goes on exactly as before.

    python3 work_episodes.py show <path|sha256|art:id>    the joined record, as JSON
    python3 work_episodes.py status                        how many works have a recorded origin (counts only)
    python3 work_episodes.py recall "a line"               his works nearest a line, each with its origin
    python3 work_episodes.py uses [N]                      the last N offer/use rows (ids only)
"""
import hashlib, json, os, re, sys, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
ART = os.path.join(MEMORY, "art")
SHELVES = {"gallery": (os.path.join(ART, "gallery.json"), ART),
           "video": (os.path.join(ART, "video", "video-gallery.json"), os.path.join(ART, "video")),
           "music": (os.path.join(ART, "music", "music.json"), os.path.join(ART, "music"))}
SOURCES = {
    "gallery": SHELVES["gallery"][0], "video": SHELVES["video"][0], "music": SHELVES["music"][0],
    "current_wants": os.path.join(MEMORY, "current-wants.json"),
    "fulfilled_wants": os.path.join(MEMORY, "fulfilled-wants.json"),
    "dismissed_wants": os.path.join(MEMORY, "dismissed-wants.json"),
    "completions": os.path.join(MEMORY, "want-completions.jsonl"),
    "moments": os.path.join(MEMORY, "moment-archive.json"),
    "durable": os.path.join(MEMORY, "durable-memory.json"),
    "shares": os.path.join(MEMORY, "gloria-music-shares.json"),
}
OFFERS = os.path.join(MEMORY, "work-episode-offers.jsonl")
USES = os.path.join(MEMORY, "work-episode-uses.jsonl")
MAX_RESULTS = 5          # works joined per look
MAX_HOPS = 2             # work -> episode -> later reading; no further
TURN_CHARS = 700         # episode lines added to one chat turn, at most
DAILY_CHARS = 12000      # and in one day (about 3,000 tokens)
FREE_SURFACES = ("journal", "recall")   # written to a file or printed, read by no paid model: not counted
HASH_CAP = 300 * 1024 * 1024
TITLE_MIN = 8            # a title shorter than this is too common a phrase to count as naming a work
MEDIA_EXT = (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm", ".m4v", ".mp3", ".wav", ".m4a", ".flac", ".ogg")

try:
    import evidence_view as EV
except Exception:                                   # standalone: every record keeps its ordinary standing
    EV = None


def _sealed_path(p):
    return any(part.lower().startswith("atelier") for part in str(p or "").replace("\\", "/").split("/"))


def _load(path):
    """JSON, else JSONL; None when absent or unreadable. Only SOURCES are ever passed here."""
    try:
        with open(path) as f:
            raw = f.read()
    except OSError:
        return None
    try:
        if path.endswith(".jsonl"):
            raise ValueError("line by line")            # one row of JSONL also parses as one JSON object
        return json.loads(raw)
    except ValueError:
        out = []
        for line in raw.splitlines():
            try: out.append(json.loads(line))
            except ValueError: pass
        return out


def _rows(data, *keys):
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for k in keys:
            if isinstance(data.get(k), list):
                return [r for r in data[k] if isinstance(r, dict)]
    return []


def _standing(rec):
    if EV is None:
        return "eligible"
    try:
        return EV.standing(rec)
    except Exception:
        return "HELD"


def _clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _day(s):
    return str(s or "")[:10]


_HASHES = {}


def file_sha(path):
    """sha256 of a file on disk, remembered by (path, size, mtime) for this process; None if unreadable or huge."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (path, st.st_size, st.st_mtime_ns)
    if key in _HASHES:
        return _HASHES[key]
    if st.st_size > HASH_CAP:
        return None
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    except OSError:
        return None
    _HASHES[key] = h.hexdigest()
    return _HASHES[key]


def artifact_id(sha=None, name=None):
    return ("art:" + sha[:16]) if sha else ("art:name:" + os.path.basename(str(name or "")))


def _fingerprint():
    out = []
    for name in sorted(SOURCES):
        try:
            st = os.stat(SOURCES[name]); out.append((name, st.st_size, st.st_mtime_ns))
        except OSError:
            out.append((name, None, None))
    return tuple(out)


# ------------------------------------------------------------------ the projection
def build():
    """Every receipt-backed record, indexed by exact ids. Nothing is hashed here except what a receipt needs."""
    P = {"receipts": [], "by_sha": {}, "by_name": {}, "wants": {}, "completions": {}, "moments": {},
         "durable": [], "shares": {}, "titles": {}, "sealed": 0, "held": [], "withdrawn": []}
    for shelf, (path, shelf_dir) in SHELVES.items():
        data = _load(path)
        rows = _rows(data, "generated") if shelf == "music" else _rows(data)
        landings = {}
        if shelf == "music" and isinstance(data, dict):
            for l in _rows(data, "landings"):
                if l.get("task_id"): landings[l["task_id"]] = l
        for i, r in enumerate(rows):
            sealed = (r.get("sealed") or "atelier" in str(r.get("source") or "").lower()
                      or "atelier" in str(r.get("backend") or "").lower()) and not r.get("revealed")
            files = []
            if shelf == "music":
                for t in r.get("tracks") or []:
                    lf = (t or {}).get("local_file")
                    if lf: files.append((lf if os.path.isabs(lf) else os.path.join(shelf_dir, lf), None, t.get("version")))
            else:
                rel = r.get("path") or r.get("image") or r.get("file")
                if rel: files.append((os.path.join(shelf_dir, rel), r.get("sha256"), r.get("revision")))
            if sealed or any(_sealed_path(f[0]) for f in files):
                P["sealed"] += 1
                continue
            st = _standing(r)
            if st == "HELD":
                P["held"].append("%s#%d" % (shelf, i)); continue
            rec = {"ref": "%s#%d" % (shelf, i), "shelf": shelf, "rec": r, "files": files, "standing": st,
                   "landing": landings.get(r.get("task_id")) if shelf == "music" else None}
            P["receipts"].append(rec)
            for fpath, sha, _rev in files:
                if sha: P["by_sha"].setdefault(sha, []).append(rec)
                P["by_name"].setdefault(os.path.basename(fpath), []).append(rec)
            t = str(r.get("title") or "").strip().lower()
            if t: P["titles"].setdefault(t, set()).add(rec["ref"])
    for name in ("current_wants", "fulfilled_wants", "dismissed_wants"):
        for w in _rows(_load(SOURCES[name]), "wants"):
            if w.get("id"):
                w = dict(w, _store=name.replace("_wants", ""))
                P["wants"].setdefault(str(w["id"]), w)
    for c in _rows(_load(SOURCES["completions"])):
        if c.get("want_id"): P["completions"].setdefault(str(c["want_id"]), []).append(c)
    arch = _load(SOURCES["moments"])
    for m in ((arch or {}).get("moments") or {}).values() if isinstance(arch, dict) else []:
        wid = ((m or {}).get("links") or {}).get("want_id") if isinstance(m, dict) else None
        if wid: P["moments"].setdefault(str(wid), []).append(m)
    for d in _rows(_load(SOURCES["durable"])):
        did = "durable:" + hashlib.sha1(("%s|%s" % (d.get("occurred_at"), d.get("event"))).encode()).hexdigest()[:12]
        if d.get("standing") == "invalidated":
            P["withdrawn"].append(did); continue
        st = _standing(d)
        if st == "HELD":
            P["held"].append(did); continue
        P["durable"].append(dict(d, _id=did, _standing=st))
    for s in _rows(_load(SOURCES["shares"]), "shares"):
        sid = s.get("id") or s.get("timestamp")
        if sid: P["shares"][str(sid)] = s
    return P


_CACHE = {"fp": None, "P": None}


def projection():
    """The projection, rebuilt whenever any source changed: eligibility is current at every look."""
    fp = _fingerprint()
    if _CACHE["fp"] != fp:
        _CACHE.update(fp=fp, P=build())
    return _CACHE["P"]


def _his_words(d):
    q = d.get("quote") if isinstance(d.get("quote"), dict) else {}
    return " ".join(str(x or "") for x in (d.get("exact_words"), q.get("vintos")))


def _want_episode(P, wid, support, out, hop):
    w = P["wants"].get(str(wid))
    if not w:
        out["missing"].append({"want": str(wid), "why": "the receipt names this want; no want record holds it now"})
        return
    st = _standing(w)
    if st != "eligible":
        out["withheld"].append({"id": "want:%s" % wid, "standing": st}); return
    ep = {"id": "want:%s" % wid, "kind": "want", "hop": hop, "support": support, "at": w.get("timestamp"),
          "what": _clip(w.get("want"), 160), "from": w.get("source"), "state": w["_store"],
          "fulfilled_at": w.get("fulfilled_at")}
    out["episodes"].append(ep)
    if w.get("self_interpretation"):
        out["said_then"].append({"id": "want:%s#self" % wid, "at": w.get("timestamp"), "of": ep["id"],
                                 "text": _clip(w["self_interpretation"], 160), "kind": "what you made of the want"})
    for m in P["moments"].get(str(wid), [])[:2]:
        snap = m.get("snapshot") or {}
        threads = [t.get("origin") for t in snap.get("active_threads") or [] if isinstance(t, dict) and t.get("origin")]
        out["episodes"].append({"id": "moment:%s" % m.get("moment_id"), "kind": "moment", "hop": hop,
                                "support": "moment archive links want %s" % wid, "at": m.get("timestamp"),
                                "what": _clip(m.get("content"), 120), "on_your_mind": [_clip(t, 60) for t in threads[:2]]})
    if hop >= MAX_HOPS:
        return
    for c in P["completions"].get(str(wid), [])[:2]:
        cid = "completion:%s:%s" % (wid, c.get("at"))
        out["episodes"].append({"id": cid, "kind": "completion", "hop": hop, "support": "want-completions",
                                "at": c.get("at"), "what": "%s (%s)" % (c.get("how"), c.get("by")), "turn_id": c.get("turn_id")})
        tid = c.get("turn_id")
        if not tid:
            continue
        for d in P["durable"]:
            turns = [str(t) for t in d.get("source_turns") or []]
            lm = d.get("ledger_match") if isinstance(d.get("ledger_match"), dict) else {}
            if str(tid) in turns or str(lm.get("turn_id")) == str(tid):
                _durable_readings(d, "the turn that completed want %s" % wid, out, hop + 1)


def _durable_readings(d, support, out, hop):
    if d["_standing"] != "eligible":
        out["withheld"].append({"id": d["_id"], "standing": d["_standing"]}); return
    if any(e["id"] == d["_id"] for e in out["episodes"]):
        return
    out["episodes"].append({"id": d["_id"], "kind": "durable", "hop": hop, "support": support,
                            "at": d.get("occurred_at"), "what": _clip(d.get("event"), 140)})
    if d.get("felt_like"):
        out["said_then"].append({"id": d["_id"] + "#felt", "at": d.get("occurred_at"), "of": d["_id"],
                                 "text": _clip(d["felt_like"], 140), "kind": "what it felt like then"})
    for i, it in enumerate(d.get("interpretations") or []):
        if isinstance(it, dict) and it.get("meaning"):
            out["readings"].append({"id": "%s#reread%d" % (d["_id"], i), "at": it.get("at"), "of": d["_id"],
                                    "text": _clip(it["meaning"], 160), "verdict": it.get("verdict"),
                                    "kind": "reread on recall"})


def lookup(ref, path=None):
    """One work, joined. ref: a media_embed hit ({path, sha256?}), a path, a sha256 or an art: id.
    Returns {artifact, episodes, said_then, readings, co_present, missing, withheld, source_ids}; origins and readings
    are separate lists and never merged."""
    P = projection()
    if isinstance(ref, str) and ref.startswith("art:") and not path:
        path = _path_for(ref)
    hit = ref if isinstance(ref, dict) else {}
    path = path or hit.get("path") or (ref if isinstance(ref, str) and os.sep in ref else None)
    sha = hit.get("sha256") or (ref if isinstance(ref, str) and re.fullmatch(r"[0-9a-f]{64}", ref) else None)
    out = {"artifact": None, "episodes": [], "said_then": [], "readings": [], "co_present": [], "made_from": [],
           "missing": [], "withheld": [], "source_ids": []}
    if path and _sealed_path(path):
        out["missing"].append({"why": "not on a house shelf"}); return out
    disk = file_sha(path) if path and os.path.exists(path) else None
    if sha and disk and disk != sha:
        out["missing"].append({"why": "the file changed after it was indexed; joined as the file is now"})
    sha = disk or sha
    if isinstance(ref, str) and ref.startswith("art:") and not ref.startswith("art:name:"):
        sha = next((s for s in P["by_sha"] if s.startswith(ref[4:])), sha)
    name = os.path.basename(path) if path else None
    receipts = list(P["by_sha"].get(sha, [])) if sha else []
    by_hash = bool(receipts)
    if not receipts and name:
        for r in P["by_name"].get(name, []):
            stated = next((s for f, s, _ in r["files"] if os.path.basename(f) == name), None)
            if stated and sha and stated != sha:
                out["missing"].append({"why": "a receipt names this file name for a different revision (%s); it is not "
                                              "this file's origin" % stated[:10]})
                continue
            receipts.append(r)
    if not receipts:
        out["artifact"] = {"id": artifact_id(sha, name), "sha256": sha, "path": path}
        out["missing"].append({"why": "no origin recorded for this work"})
        return out
    rc = receipts[0]
    r = rc["rec"]
    stated = next(((f, s, v) for f, s, v in rc["files"] if (s and s == sha) or os.path.basename(f) == name), rc["files"][0])
    kind = {"gallery": "painting", "video": "video", "music": "song"}[rc["shelf"]]
    out["artifact"] = {"id": artifact_id(sha, name), "sha256": sha, "path": path or stated[0], "kind": kind,
                       "title": _clip(r.get("title") or "", 100), "made_at": r.get("timestamp") or r.get("generated_at"),
                       "revision": stated[2], "identity": "content hash" if by_hash else "file name (no hash in the receipt)",
                       "receipt": rc["ref"], "run_id": r.get("run_id"), "task_id": r.get("task_id")}
    if by_hash and path and os.path.basename(stated[0]) != os.path.basename(path):
        out["artifact"]["moved_from"] = os.path.basename(stated[0])
    if len(receipts) > 1:
        out["artifact"]["also_receipts"] = [x["ref"] for x in receipts[1:3]]
    # what he wrote at the making: an operation input, part of the event's record, not a later reading
    if rc["shelf"] == "music" and r.get("felt_sense"):
        out["said_then"].append({"id": rc["ref"] + "#felt", "at": r.get("generated_at"), "of": out["artifact"]["id"],
                                 "text": _clip(r["felt_sense"], 160), "kind": "what you felt composing it"})
    elif r.get("prompt") or r.get("intent"):
        out["said_then"].append({"id": rc["ref"] + "#asked", "at": r.get("timestamp"), "of": out["artifact"]["id"],
                                 "text": _clip(r.get("intent") or r.get("prompt"), 140), "kind": "what you asked for"})
    wid = r.get("want_id") or r.get("source_want")
    if wid:
        _want_episode(P, wid, "operation receipt %s" % rc["ref"], out, 1)
    src = str(r.get("dream_source") or "")
    if not wid and src == "dream":
        out["missing"].append({"why": "made from a dream; no dream record is linked to it"})
    elif not wid:
        out["missing"].append({"why": "the receipt names no want or occasion"})
    for key in ("source_image", "remake_of"):
        parent = r.get(key)
        if parent:
            pr = next(iter(P["by_name"].get(os.path.basename(str(parent)), [])), None)
            out["made_from"].append({"id": "receipt:" + (pr["ref"] if pr else "?"), "relation": "produced_from",
                                     "support": "%s in %s" % (key, rc["ref"]), "work": os.path.basename(str(parent)),
                                     "title": _clip((pr or {}).get("rec", {}).get("title") or "", 80)})
    # later readings of the work itself
    if r.get("his_reading") and r.get("sighted_at"):
        out["readings"].append({"id": rc["ref"] + "#sight", "at": r.get("sighted_at"), "of": out["artifact"]["id"],
                                "text": _clip(r["his_reading"], 160), "verdict": r.get("verdict"),
                                "kind": "how you read it when you saw it"})
    landed = r.get("landed") if isinstance(r.get("landed"), dict) else {}
    if landed.get("note") and landed.get("state") not in ("unavailable", None):
        out["readings"].append({"id": rc["ref"] + "#landed", "at": (rc.get("landing") or {}).get("landed_at") or r.get("generated_at"),
                                "of": out["artifact"]["id"], "text": _clip(landed["note"], 120), "kind": "how it landed in you"})
    for sid in r.get("shares_in_context") or []:
        s = P["shares"].get(str(sid))
        if s:
            song = s.get("song") if isinstance(s.get("song"), str) else (s.get("song") or {}).get("title", "")
            out["co_present"].append({"id": "share:%s" % sid, "relation": "co_present",
                                      "support": "her share was in the composer's context", "what": _clip(song, 80)})
    # his own words naming this work exactly: a file name, or a title no other work carries
    title = str(r.get("title") or "").strip().lower()
    shared_title = len(P["titles"].get(title, ())) > 1
    unique_title = title if len(title) >= TITLE_MIN and not shared_title else ""
    names = {os.path.basename(f) for f, _, _ in rc["files"]}
    for d in P["durable"]:
        words = _his_words(d)
        if any(n and n in words for n in names) or (unique_title and _title_in(unique_title, words.lower())):
            _durable_readings(d, "his own words name this work", out, 1)
    if title and shared_title:
        out["missing"].append({"why": "another work has this title; a title alone links nothing"})
    out["episodes"] = [e for e in out["episodes"] if e.get("hop", 1) <= MAX_HOPS]
    out["source_ids"] = [x["id"] for k in ("episodes", "said_then", "readings", "co_present", "made_from") for x in out[k]]
    return out


def _title_in(title, low):
    return re.search(r"(?<![a-z0-9])" + re.escape(title) + r"(?![a-z0-9])", low) is not None


# ------------------------------------------------------------------ ranked lists, combined by id, never by vector
def fuse(*ranked, k=60):
    """Reciprocal-rank fusion of ranked lists of hits ({path} or {sha256}); the media space and any text space stay
    separate, and only their ORDERS are combined, keyed by the work's identity."""
    score, first = {}, {}
    for lst in ranked:
        for rank, h in enumerate(lst or []):
            key = h.get("sha256") or h.get("artifact_id") or h.get("path")
            if not key:
                continue
            score[key] = score.get(key, 0.0) + 1.0 / (k + rank + 1)
            first.setdefault(key, h)
    order = sorted(score, key=lambda x: (-score[x], list(first).index(x)))
    return [first[x] for x in order][:MAX_RESULTS]


# ------------------------------------------------------------------ what reaches him
HEADER = ("Under a work, where it is recorded: the occasion it came from (with its source) and how you read it later. "
          "That is what happened; the nearness is only resemblance. Where nothing is recorded you don't have the origin "
          "- say so rather than guess, and claim no feeling from then beyond what is written.")


def lines_for(j):
    """A joined work as a few indented lines. Origins first, then what you wrote then, then later readings."""
    out = []
    shown = [e for e in j["episodes"] if e["kind"] in ("want", "durable") or (e["kind"] == "moment" and e.get("on_your_mind"))]
    for e in shown[:3]:
        if e["kind"] == "want":
            out.append("  made for your want (%s, %s): \"%s\" [%s]" % (_day(e["at"]), e.get("state"), e["what"][:90], e["id"]))
        elif e["kind"] == "moment" and e.get("on_your_mind"):
            out.append("  when it was fulfilled (%s), on your mind: %s [%s]" % (_day(e["at"]), "; ".join(e["on_your_mind"]), e["id"][:40]))
        elif e["kind"] == "durable":
            out.append("  you remember it with (%s): %s [%s]" % (_day(e["at"]), e["what"][:90], e["id"]))
    for m in j["made_from"][:1]:
        out.append("  made from your work \"%s\" [%s]" % (m.get("title") or m["work"], m["id"]))
    for s in j["said_then"][:1]:
        out.append("  then, %s: \"%s\"" % (s["kind"], s["text"][:80]))
    for r in sorted(j["readings"], key=lambda x: str(x.get("at") or ""))[-1:]:
        v = (" - you said %s" % r["verdict"]) if r.get("verdict") else ""
        out.append("  later, %s (%s): \"%s\"%s" % (r["kind"], _day(r["at"]), r["text"][:90], v))
    for c in j["co_present"][:1]:
        out.append("  present while you composed, not a cause: her shared song \"%s\"" % c["what"])
    if not out:
        out.append("  (origin not recorded)")
    return out


def _spent_today():
    day, n = time.strftime("%Y-%m-%d"), 0
    try:
        with open(OFFERS) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    if str(r.get("at", "")).startswith(day) and r.get("surface") not in FREE_SURFACES:
                        n += int(r.get("chars") or 0)
                except ValueError:
                    pass
    except OSError:
        pass
    return n


def _append(path, row):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    except OSError:
        pass


def context(hits, surface="chat", budget=None, record=True):
    """For each hit, the episode lines to put under its works line: {path: [lines]}, plus the header when anything was
    joined. Returns ({}, "") when the day's budget is spent or nothing joined; the caller's plain block stands."""
    if budget is None:
        budget = TURN_CHARS if surface in FREE_SURFACES else DAILY_CHARS - _spent_today()
    left = budget
    if left <= 0 or not hits:
        return {}, ""
    per, used, ids, chars = {}, [], [], 0
    for h in list(hits)[:MAX_RESULTS]:
        try:
            j = lookup(h)
        except Exception:
            continue
        ls = lines_for(j)
        size = sum(len(x) + 1 for x in ls)
        if chars + size > min(TURN_CHARS, left):
            continue                                     # this one does not fit; a smaller one may
        per[h.get("path")] = ls
        chars += size
        used.append((j.get("artifact") or {}).get("id"))
        ids.extend(j["source_ids"])
    header = HEADER if ids else ""                       # "(origin not recorded)" alone needs no header
    chars += len(header)
    if record and per:
        _append(OFFERS, {"at": datetime.now().isoformat(timespec="seconds"), "surface": surface,
                         "works": [u for u in used if u], "source_ids": ids[:24], "chars": chars})
    return per, header


def note_use(reply, surface="", turn_id="", window_s=900):
    """After his reply: which of the works and source records offered this turn his reply actually used. Content-free
    row (ids and how each was matched). A nearest-neighbour hit that he did not use is recorded as offered only."""
    try:
        rows = [json.loads(l) for l in open(OFFERS) if l.strip()]
    except (OSError, ValueError):
        return None
    if not rows:
        return None
    last = rows[-1]
    try:
        age = (datetime.now() - datetime.fromisoformat(last["at"])).total_seconds()
    except (KeyError, ValueError, TypeError):
        return None
    if age > window_s or last.get("surface") in FREE_SURFACES:
        return None
    try:
        if any(json.loads(l).get("offer_at") == last["at"] for l in open(USES).read().splitlines()[-20:] if l.strip()):
            return None                                  # this offer's reply was already read
    except (OSError, ValueError):
        pass
    low = str(reply or "").lower()
    named, used = [], []
    for aid in last.get("works") or []:
        p = _path_for(aid)
        j = lookup(p) if p else None
        if not j or not j.get("artifact"):
            continue
        t = str(j["artifact"].get("title") or "").lower()
        if len(t) >= 4 and t in low:
            named.append(aid)
        for k in ("episodes", "said_then", "readings"):
            for x in j[k]:
                if x["id"] in (last.get("source_ids") or []) and _detail_used(x.get("text") or x.get("what") or "", low):
                    used.append({"id": x["id"], "how": "detail words in the reply"})
    row = {"at": datetime.now().isoformat(timespec="seconds"), "offer_at": last["at"], "surface": surface,
           "turn_id": turn_id, "offered": last.get("source_ids") or [], "named": named, "used": used}
    _append(USES, row)
    return row


def _path_for(aid):
    """The file an artifact id names now: a hash this process computed, a receipt's stated hash, or a receipt's file
    name. None when the work is gone."""
    aid = str(aid or "")
    if aid.startswith("art:name:"):
        name = aid[len("art:name:"):]
        for r in projection()["by_name"].get(name, []):
            for f, _, _ in r["files"]:
                if os.path.basename(f) == name and os.path.exists(f):
                    return f
        return None
    pre = aid[4:] if aid.startswith("art:") else aid
    for (p, _, _), s in list(_HASHES.items()):
        if s.startswith(pre) and os.path.exists(p) and file_sha(p) == s:
            return p
    for s, recs in projection()["by_sha"].items():
        if s.startswith(pre):
            for r in recs:
                for f, fs, _ in r["files"]:
                    if fs == s and os.path.exists(f):
                        return f
    return None


_STOP = set("that this with from your have what when they them their there about would could into been were just "
            "only like than then some more over also very much".split())


def _content_words(s):
    return [w for w in re.findall(r"[a-z']+", str(s).lower()) if len(w) > 4 and w not in _STOP]


def _detail_used(detail, low):
    words = _content_words(detail)
    if len(words) < 2:
        return False
    hit = sum(1 for w in set(words) if w in low)
    return hit >= max(2, int(0.5 * len(set(words)) + 0.5))


def attest(ref, claim):
    """Is a claim about what he felt or thought at a work's making supported by a record? Only the written feeling
    counts. Returns {supported, by, say}."""
    j = lookup(ref)
    recorded = [x for x in j["said_then"] + j["readings"]]
    low = str(claim or "").lower()
    claim_words = set(_content_words(re.sub(r"\byou (felt|feel|were|thought)\b", "", low)))
    by = [x["id"] for x in recorded if claim_words and
          len(claim_words & set(_content_words(x["text"]))) >= max(1, (len(claim_words) + 1) // 2)]
    if by:
        return {"supported": True, "by": by, "say": "recorded: %s" % by[0]}
    return {"supported": False, "by": [], "say": "not recorded - say it as a guess or not at all"}


def status():
    P = projection()
    with_want = sum(1 for r in P["receipts"] if (r["rec"].get("want_id") or r["rec"].get("source_want")))
    joined = sum(1 for r in P["receipts"] if str(r["rec"].get("want_id") or r["rec"].get("source_want") or "") in P["wants"])
    return {"receipts": len(P["receipts"]), "naming_a_want": with_want, "want_found": joined,
            "wants": len(P["wants"]), "moments_linked": sum(len(v) for v in P["moments"].values()),
            "durable": len(P["durable"]), "withdrawn": len(P["withdrawn"]), "held": len(P["held"]),
            "sealed_skipped": P["sealed"]}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "show" and len(sys.argv) > 2:
        print(json.dumps(lookup(sys.argv[2]), indent=1, default=str))
    elif cmd == "recall" and len(sys.argv) > 2:
        import media_embed
        hits = media_embed.nearest(sys.argv[2], MAX_RESULTS)
        per, header = context(hits, surface="recall", record=False)
        print(header)
        print(media_embed.describe(hits, per))
    elif cmd == "uses":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        for p in (OFFERS, USES):
            try: print("\n".join(open(p).read().splitlines()[-n:]))
            except OSError: pass
    else:
        print(json.dumps(status(), indent=1))

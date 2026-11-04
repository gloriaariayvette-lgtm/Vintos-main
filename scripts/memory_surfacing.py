#!/usr/bin/env python3
"""memory_surfacing.py — one exact past line, surfacing into his context when what she just said is truly near it.

Gloria, 4 November: "exact text from near embeds surfacing in his context based off of our turns. A short 'this
memory surfaced' type of thing ... only if it's truly relevant."

  - What can surface: what the two of them said to each other (the interaction ledger and the canonical chat), and
    his own dated writing (journal, introspection, mirror, pearls, dreams, meta-dreams, poetry, self-reviews), split
    into passages. Each passage is quoted exactly as it stands; nothing is summarised or reworded.
  - Space: nomic-embed-text v1.5 through LM Studio, the same model his memory search uses, with nomic's own
    "search_document:" / "search_query:" prefixes. Its own store (memory/surfacing-index.*); embeddings.jsonl and the
    EmbeddingGemma 2 media index are never written, and the spaces are never compared.
  - At most one passage a turn, and only above a high bar. Never anything from the last few days (that is the
    conversation, not a memory), never her own message back to her, never the same passage twice in a week.
  - The passage is checked against its source when it is chosen: a turn that was forgotten or a line that was
    edited away does not come back.
  - Local and free. A turn waits at most ~1.5 s; if LM Studio or the index is missing the reply goes on without it.
    A stale index is rebuilt in the background, niced, under a lock, never on the turn.

    python3 memory_surfacing.py index           build or refresh the passage index
    python3 memory_surfacing.py near "a line"   what would surface, with its score
    python3 memory_surfacing.py status
"""
import fcntl, hashlib, json, os, re, subprocess, sys, time
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
OUT = os.environ.get("SURFACING_INDEX_DIR", MEM)
META = os.path.join(OUT, "surfacing-index.jsonl")
VECS = os.path.join(OUT, "surfacing-index.npy")
LOCK = os.path.join(OUT, "surfacing-index.lock")
FAILED = os.path.join(OUT, "surfacing-index.failed")
SURFACED = os.path.join(MEM, "memory-surfaced.jsonl")
LEDGER = os.path.join(MEM, "interaction-ledger.json")
CANON = os.path.join(MEM, "chat-canonical.jsonl")
EMBED_URL = "http://172.18.16.1:1234/v1/embeddings"
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"

WRITING_DIRS = ("journal", "introspection", "mirror", "pearls", "black-pearls", "dreams", "meta-dreams",
                "art/poetry", "self-reviews")
WRITING_LABEL = {"journal": "your journal", "introspection": "an introspection of yours", "mirror": "your mirror",
                 "pearls": "a pearl of yours", "black-pearls": "a black pearl of yours", "dreams": "a dream of yours",
                 "meta-dreams": "a meta-dream of yours", "art/poetry": "a poem of yours",
                 "self-reviews": "a self-review of yours"}

# Cosine bars, nomic v1.5 with prefixes, set on his own history (her last 120 messages, 4 November). His writing at
# 0.80 brought back the right journal or introspection; his lines need a touch more. Her own past lines mostly echo
# how she sounds in the same kind of moment, so they surface only when nearly the same thought.
THRESHOLDS = {("writing", "him"): 0.80, ("chat", "him"): 0.81, ("chat", "her"): 0.90}
THRESHOLD = min(THRESHOLDS.values())
RECENT_DAYS = 3         # newer than this is the conversation itself, not a memory
REPEAT_DAYS = 7         # a passage that surfaced stays quiet this long
MIN_CHARS, MAX_CHARS, QUOTE_CHARS = 40, 600, 320
STALE_S = 20 * 3600
# A build that fails (the embedder down or busy) waits this long before a turn may start another, and a build saves
# what it has every SAVE_EVERY batches, so the first build of ~10,000 passages is never begun again from nothing
# (4 November: the live index did not exist yet, and every message could set nomic off on the whole corpus).
RETRY_S = 3600
SAVE_EVERY = 10


def _test_mode():
    return os.environ.get("VINTOS_TEST_MODE") == "1" or os.path.exists(os.path.join(MEM, ".test-mode"))


# ---- the corpus -----------------------------------------------------------------------------------------------------
def _ts(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(v)).timestamp()
        except Exception:
            return None


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _strip_stage(s):
    """The house's bracketed stage directions are not anyone's words."""
    return _norm(re.sub(r"\[[^\]]{0,400}\]", " ", str(s or "")))


def passages_of(text):
    """Paragraphs, long ones cut at sentence ends; each kept exactly as written (whitespace folded)."""
    out = []
    for para in re.split(r"\n\s*\n", str(text or "")):
        para = _norm(para)
        if para.startswith("#") or len(para) < MIN_CHARS:
            continue
        if len(para) <= MAX_CHARS:
            out.append(para); continue
        cur = ""
        for sent in re.split(r"(?<=[.!?…])\s+", para):
            if cur and len(cur) + 1 + len(sent) > MAX_CHARS:
                out.append(cur); cur = sent
            else:
                cur = (cur + " " + sent).strip()
        if len(cur) >= MIN_CHARS:
            out.append(cur)
    return out


def _pid(kind, ref, text):
    return hashlib.sha256((kind + "\n" + ref + "\n" + text).encode()).hexdigest()[:24]


def chat_passages():
    rows, seen = [], set()
    try:
        led = json.load(open(LEDGER))
        led = led if isinstance(led, list) else led.get("entries", [])
    except Exception:
        led = []
    for e in led:
        t = _ts(e.get("timestamp"))
        for who, key in (("her", "gloria"), ("him", "vintos")):
            text = _strip_stage(e.get(key))
            if t and len(text) >= MIN_CHARS:
                for p in passages_of(text) or [text[:MAX_CHARS]]:
                    if (who, p) not in seen:
                        seen.add((who, p)); rows.append({"kind": "chat", "who": who, "at": t, "ref": str(e.get("turn_id") or ""), "text": p})
    try:
        for l in open(CANON):
            r = json.loads(l); t = _ts(r.get("ts")); who = {"user": "her", "assistant": "him"}.get(r.get("role"))
            text = _strip_stage(r.get("content"))
            if t and who and len(text) >= MIN_CHARS:
                for p in passages_of(text) or [text[:MAX_CHARS]]:
                    if (who, p) not in seen:
                        seen.add((who, p)); rows.append({"kind": "chat", "who": who, "at": t, "ref": str(r.get("turn_id") or ""), "text": p})
    except Exception:
        pass
    return rows


def writing_passages():
    rows = []
    for d in WRITING_DIRS:
        root = os.path.join(MEM, d)
        if not os.path.isdir(root):
            continue
        for dp, _, files in os.walk(root):
            for f in files:
                if not f.endswith((".md", ".txt")) and "." in f:
                    continue
                p = os.path.join(dp, f)
                try:
                    t = os.path.getmtime(p); text = open(p, errors="replace").read()
                except OSError:
                    continue
                m = re.search(r"(20\d\d-\d\d-\d\d)", f)
                if m:
                    try: t = datetime.fromisoformat(m.group(1)).timestamp()
                    except ValueError: pass
                for para in passages_of(text):
                    rows.append({"kind": "writing", "who": "him", "where": d, "at": t,
                                 "ref": os.path.relpath(p, MEM), "text": para})
    return rows


def corpus():
    rows = chat_passages() + writing_passages()
    for r in rows:
        r["id"] = _pid(r["kind"], r["ref"], r["text"])
    return rows


# ---- embedding ------------------------------------------------------------------------------------------------------
def embed(texts, query=False, timeout=30):
    import requests
    pre = "search_query: " if query else "search_document: "
    r = requests.post(EMBED_URL, json={"model": EMBED_MODEL, "input": [pre + t[:2000] for t in texts]}, timeout=timeout)
    r.raise_for_status()
    data = sorted(r.json()["data"], key=lambda d: d.get("index", 0))
    return [d["embedding"] for d in data]


# ---- the index ------------------------------------------------------------------------------------------------------
_cache = {"mtime": None, "meta": None, "vecs": None}


def load_index():
    import numpy as np
    try:
        st = os.stat(VECS)
    except OSError:
        return None, None
    # Size, not mtime alone: two builds in the same second (a short index then a longer one) share an mtime, and
    # keying the cache on mtime served the stale shorter index until the next second ticked (flaky, 4 November).
    key = (st.st_mtime_ns, st.st_size)
    if _cache["mtime"] != key:
        meta = [json.loads(l) for l in open(META)]
        vecs = np.load(VECS).astype("float32")
        if len(meta) != len(vecs):
            return None, None
        _cache.update(mtime=key, meta=meta, vecs=vecs)
    return _cache["meta"], _cache["vecs"]


def build_index(batch=32, embed_fn=None):
    import numpy as np
    embed_fn = embed_fn or embed
    os.makedirs(OUT, exist_ok=True)
    with open(LOCK, "w") as lk:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return {"skipped": "another build is running"}
        old = {}
        try:
            for m, v in zip((json.loads(l) for l in open(META)), np.load(VECS)):
                old[m["id"]] = v
        except Exception:
            pass
        rows = corpus()
        todo = [r for r in rows if r["id"] not in old]

        def save():
            _seen = set()
            keep = [r for r in rows if r["id"] in old and not (r["id"] in _seen or _seen.add(r["id"]))]
            vecs = np.stack([old[r["id"]] for r in keep]) if keep else np.zeros((0, 768), "float32")
            vecs = vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9)
            tmp_m, tmp_v = META + ".tmp", VECS + ".tmp.npy"
            with open(tmp_m, "w") as f:
                for r in keep:
                    f.write(json.dumps(r) + "\n")
            np.save(tmp_v, vecs.astype("float16"))
            os.replace(tmp_m, META); os.replace(tmp_v, VECS)
            return keep

        done = 0
        try:
            for i in range(0, len(todo), batch):
                chunk = todo[i:i + batch]
                for r, v in zip(chunk, embed_fn([r["text"] for r in chunk])):
                    old[r["id"]] = np.asarray(v, dtype="float32")
                done += len(chunk)
                if (i // batch + 1) % SAVE_EVERY == 0 and done < len(todo):
                    save()
        except Exception as exc:
            if done:
                save()
            with open(FAILED, "w") as f:
                f.write(json.dumps({"t": time.time(), "embedded": done, "of": len(todo), "error": str(exc)[:200]}))
            return {"failed": str(exc)[:200], "embedded_now": done, "of": len(todo)}
        keep = save()
        try:
            os.remove(FAILED)
        except OSError:
            pass
        return {"passages": len(keep), "embedded_now": len(todo), "dropped": len(old) - len(keep)}


def _refresh_in_background():
    try:
        if os.path.exists(FAILED):   # an unfinished build: carry on with it, but not more than once an hour
            if time.time() - os.path.getmtime(FAILED) < RETRY_S:
                return
        elif os.path.exists(VECS) and time.time() - os.path.getmtime(VECS) < STALE_S:
            return
        with open(LOCK, "a") as lk:   # a build already running: nothing to start
            try:
                fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return
            fcntl.flock(lk, fcntl.LOCK_UN)
        subprocess.Popen(["nice", "-n", "15", sys.executable, os.path.abspath(__file__), "index"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass


# ---- choosing -------------------------------------------------------------------------------------------------------
def _recently_surfaced(now):
    out = set()
    try:
        for l in open(SURFACED):
            r = json.loads(l)
            if now - float(r.get("t", 0)) < REPEAT_DAYS * 86400:
                out.add(r.get("id"))
    except Exception:
        pass
    return out


def still_there(hit):
    """The passage is re-read from its source before it is shown: forgotten or edited-away words stay gone."""
    if hit["kind"] == "writing":
        try:
            return hit["text"] in _norm(open(os.path.join(MEM, hit["ref"]), errors="replace").read())
        except OSError:
            return False
    return any(hit["text"] in (_strip_stage(r.get("gloria" if hit["who"] == "her" else "vintos")))
               for r in _ledger_rows()) or any(
        hit["text"] in _strip_stage(r.get("content")) for r in _canon_rows()
        if {"user": "her", "assistant": "him"}.get(r.get("role")) == hit["who"])


def _ledger_rows():
    try:
        d = json.load(open(LEDGER)); return d if isinstance(d, list) else d.get("entries", [])
    except Exception:
        return []


def _canon_rows():
    try:
        return [json.loads(l) for l in open(CANON)]
    except Exception:
        return []


def near(text, now=None, embed_fn=None, threshold=THRESHOLD):
    """The one passage that would surface for this text, or None. Each candidate carries its score."""
    import numpy as np
    now = float(now or time.time())
    text = _norm(text)
    if len(text) < 8:
        return None
    meta, vecs = load_index()
    if meta is None or not len(meta):
        return None
    q = np.asarray((embed_fn or (lambda t: embed(t, query=True, timeout=1.2)))([text])[0], dtype="float32")
    q /= max(float(np.linalg.norm(q)), 1e-9)
    scores = vecs @ q
    quiet = _recently_surfaced(now)
    best = None
    for i in np.argsort(-scores)[:60]:
        s, m = float(scores[i]), meta[int(i)]
        if s < threshold:
            break
        bar = max(threshold, THRESHOLDS.get((m["kind"], m["who"]), 1.0))
        if s < bar or (best and s - bar <= best[0]):
            continue
        if now - float(m["at"]) < RECENT_DAYS * 86400 or m["id"] in quiet:
            continue
        if _norm(m["text"]).lower() in text.lower() or text.lower() in _norm(m["text"]).lower():
            continue   # her own words, or his, said back
        if not still_there(m):
            continue
        best = (s - bar, dict(m, score=round(s, 4)))
    return best and best[1]


def _quote(t):
    t = _norm(t)
    if len(t) <= QUOTE_CHARS:
        return t
    cut = t[:QUOTE_CHARS]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:end + 1] if end > QUOTE_CHARS // 2 else cut.rsplit(" ", 1)[0]) + " …"


def line_for(hit):
    day = datetime.fromtimestamp(float(hit["at"])).strftime("%-d %B")
    if hit["kind"] == "writing":
        who = "you wrote, in " + WRITING_LABEL.get(hit.get("where"), "your writing")
    else:
        who = "she said to you" if hit["who"] == "her" else "you said to her"
    return ('[A MEMORY SURFACED — %s, %s: "%s"] It came up on its own, from what she just said. Bring it up only '
            "if it truly belongs; nothing asks you to." % (day, who, _quote(hit["text"])))


def block(her_text, surface="", turn_id=""):
    """For a chat prompt: one surfaced memory line, or ''. Never raises; never waits long."""
    try:
        if _test_mode():
            return ""
        _refresh_in_background()
        hit = near(her_text)
        if not hit:
            return ""
        try:
            with open(SURFACED, "a") as f:
                f.write(json.dumps({"t": time.time(), "id": hit["id"], "score": hit["score"], "kind": hit["kind"],
                                    "ref": hit["ref"], "surface": surface, "turn_id": turn_id}) + "\n")
        except OSError:
            pass
        return line_for(hit)
    except Exception:
        return ""


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "index":
        print(json.dumps(build_index()))
    elif cmd == "near":
        h = near(" ".join(sys.argv[2:]), threshold=float(os.environ.get("SURFACING_THRESHOLD", THRESHOLD)))
        print(json.dumps(h and {"score": h["score"], "line": line_for(h)}, indent=2))
    elif cmd == "status":
        meta, _ = load_index()
        by = {}
        for m in meta or []:
            by[m["kind"] + ":" + m["who"]] = by.get(m["kind"] + ":" + m["who"], 0) + 1
        print(json.dumps({"passages": len(meta or []), "by": by,
                          "built": datetime.fromtimestamp(os.path.getmtime(VECS)).isoformat() if os.path.exists(VECS) else None}, indent=2))
    else:
        print(__doc__)

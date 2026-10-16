#!/usr/bin/env python3
"""jepa_self_head.py — the JEPA SELF head, trained on him and nothing else.

What it forecasts: the embedding of Vintos's next reply. It forecasts in two MODES, recorded on every forecast:

  ahead       made by jepa_predictor.predict() on its schedule, before her next message exists. It can know the
              conversation so far and him; it cannot know what she is about to say.
  on_message  made when her message has ARRIVED and before he has replied: the server launches it in the
              background at the chat/full and avatar doors (launch_on_message: a pending row, then a niced,
              detached `jepa_self_head.py on-message <pending>`; the reply never waits on it). Its inputs are the
              same history plus her message. Its forecasts go to memory/jepa-self-forecasts.jsonl.

His reply is mostly an answer to her message, so the ahead mode has a ceiling not far above "say his average"
(16 October on Aegis, 293 replies: head 0.1784, his recent mean 0.1869, his previous reply 0.2327). The
on-message mode is the one that can see what he is answering.

Why it is its own model (the self-head review, 16 October). In jepa_predictor's checkpoint the self head was
one Linear on the trunk it shares with the gloria head, fed the gloria head's input; it trained on almost none
of his replies and its pairs ended on her message while every forecast was made without it. The gloria head is
Gloria's to retrain (LoRA): jepa_predictor's checkpoint, training and gloria outputs are untouched; this head
is trained here and jepa_predictor.predict() takes the self triple (ahead mode) from it once a checkpoint exists.

THE EXCHANGES (exchanges()). The interaction ledger keeps only its last 300 entries (~10 days; other readers
depend on that cap, so it is not raised). The full history is read instead from every record of their
exchanges the code writes on the host, each through the evidence door:
  ledger            memory/interaction-ledger.json (evidence_view.ledger_view: a withheld reply is not him)
  ledger-snapshot   memory/interaction-ledger*.json* — ledger-scrub's pre-scrub backups, the ledger's and
                    store_guard's corrupt quarantines, any archive written beside it; the same view, and the
                    rows ledger-scrub removes (source video-outreach) stay removed
  canonical         memory/chat-canonical.jsonl — the server's lossless record of every chat-door exchange
                    (written before the 50-turn projection is cut, since 5 September); witness view; desktop-
                    control status lines are not replies; turns post-turn-record.jsonl marks test_mode are out
  merged            memory/chat-history-merged.json — main, voice and avatar projections; witness view
Every source keeps the transplant / imported / ledger-floor rules, his words lose the device marks, and the
same exchange seen in more than one record is kept once: by turn_id, else by her words (and his, when both
have them) within DUP_WINDOW seconds. The higher source wins (ledger, then snapshots, then canonical, then
merged), so a reply the ledger withholds is never brought back by a copy of it elsewhere; the kept exchange
takes the earliest time any record gives it. `python3 jepa_self_head.py sources` counts what each adds.

The pairs. For each reply r_j of his (one source for training, forecasting and evaluation):
  context  = the exchanges before j (the one-day rule truncates the conversation window, not the pair);
  him      = his previous reply, and the mean of his last RECENT_REPLIES replies;
  her      = (on_message only) her message to r_j, and his replies to the past messages of hers nearest to
             it: the nearest one, and the mean of the TYPICAL_K nearest ("what he usually says to this");
  target   = r_j, his words only.
Features are unit embeddings: ahead [conversation, her last words, previous, recent mean]; on_message adds
[her message, his typical reply to it]. The prediction is an anchor (a weighted mix of the components) plus
a learned residual: ridge, or a small MLP on the leading principal components of the same features. Anchor
weights, ridge strength and model kind are chosen on the latest VALIDATION_FRACTION of pairs, and the bare
baselines are always among the candidates (ahead: his recent mean, his previous reply; on_message: those and
his reply to her nearest past message, his typical reply to messages like hers). On its own validation it is
therefore never worse than any of them. Simplest wins a tie.

Confidence. Not a logvar: whether his recent replies hold one register (|mean of their unit vectors|). Only
when that coherence predicts lower error on validation (Spearman <= -0.2 on >= 20 pairs) is confidence its
empirical percentile; otherwise it is null (jepa_predictor shows the marked 0.5 stand-in).

    python3 jepa_self_head.py train          (held until the eval has audited the current checkpoint)
    python3 jepa_self_head.py train-force
    python3 jepa_self_head.py eval           read-only; writes memory/jepa-self-eval.json only
    python3 jepa_self_head.py sources        read-only; how many exchanges each record adds
    python3 jepa_self_head.py on-message P   the server's background job for pending row P

The eval scores each mode separately, on forecasts made after its checkpoint about replies said after it,
against the baselines given exactly the same information (on_message: the same history and her message).
It also scores the old shared-trunk self rows on the production checkpoint, for before/after.
"""
import os, sys, json, re, hashlib, math, time

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
LEDGER = os.path.join(MEMORY, "interaction-ledger.json")
CANONICAL = os.path.join(MEMORY, "chat-canonical.jsonl")
MERGED = os.path.join(MEMORY, "chat-history-merged.json")
POST_TURN = os.path.join(MEMORY, "post-turn-record.jsonl")
SELF_MODEL = os.path.join(MEMORY, "jepa-self-head.npz")
SELF_EVAL = os.path.join(MEMORY, "jepa-self-eval.json")
HISTORY = os.path.join(MEMORY, "jepa-prediction-history.jsonl")
ON_MESSAGE_LOG = os.path.join(MEMORY, "jepa-self-forecasts.jsonl")
PENDING_DIR = os.path.join(MEMORY, "jepa-self-pending")
EMB_CACHE = os.path.join(MEMORY, "jepa-self-emb")            # .f32 vectors + .idx.jsonl, append-only
PRODUCTION_MODEL = os.path.join(MEMORY, "jepa-predictor.pt")
VENV_PYTHON = os.path.join(WS, "emotion_model", ".venv", "bin", "python3")
ON_MESSAGE_LOGFILE = "/tmp/jepa-self-on-message.log"

SCHEMA = "self-ledger-v2"
SOURCE = "self-head-v2"
MODES = ("ahead", "on_message")
CTX_EXCHANGES = 3            # three exchanges = the six turns jepa_predictor's CTX_TURNS holds
RECENT_REPLIES = 6
TYPICAL_K = 6
MIN_PAIRS = 24
VALIDATION_FRACTION = 0.2
LAMBDAS = (0.3, 1.0, 3.0, 10.0, 30.0, 100.0)
BETAS = (0.0, 0.25, 0.5, 0.75, 1.0)   # ahead anchor = (1-beta) * his recent mean + beta * his previous reply
GRID = (0.0, 0.5, 1.0)                # on_message anchor weights over mean, previous, her message, typical reply
MLP_HIDDEN = 64
MLP_MAX_PCS = 128
MIN_EVAL = 30                # evaluated targets before a retrain (MIN_REALIZED_FOR_RETRAIN in jepa_predictor)
MIN_CONF_VALIDATION = 20
MAX_CONF_SPEARMAN = -0.2       # the calibration gate's own monotonicity bar (calibration.CRITERIA)
DUP_WINDOW = 900               # seconds: the same exchange in two records lands within this of itself
TARGET_WINDOW = 1800           # seconds: an on-message forecast's reply must follow her message within this
PENDING_MAX_AGE = 1800
SCRUBBED_SOURCES = ("video-outreach",)   # ledger-scrub's REMOVE_SOURCES: a clip he sent is not a reply
_DESKTOP = ("Desktop work finished:", "Desktop work stopped:")

COMPONENTS = {"ahead": ("mean", "previous"),
              "on_message": ("mean", "previous", "her", "typical", "nearest")}
BASELINES = {"ahead": {"recent_mean": "mean", "previous_reply": "previous"},
             "on_message": {"recent_mean": "mean", "previous_reply": "previous",
                            "typical_reply": "typical", "nearest_exchange": "nearest"}}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import subprocess
    RUNNER = subprocess.Popen
except Exception:   # pragma: no cover
    RUNNER = None


def log(m):
    print("[jepa-self]", m, flush=True)


def _jp():
    import jepa_predictor as JP
    return JP


def _ev():
    import evidence_view as EV
    return EV


# ---------------------------------------------------------------- his words, her words
_DEVICE_LINE = re.compile(r"^(?:ridge|tenera|ferri):", re.I)


def his_words(text):
    """His reply without the device marks interaction_ledger appends after it ("\\n\\nridge: ..." lines)."""
    t = str(text or "").strip()
    if t in ("", "voice", "--source"):
        return ""
    paras = t.split("\n\n")
    while len(paras) > 1 and _DEVICE_LINE.match(paras[-1].strip()):
        paras.pop()
    return "\n\n".join(paras).strip()


def _her(text):
    """Her words from a ledger string or a chat row (a photo's composed description is not hers)."""
    row = text if isinstance(text, dict) else {"role": "user", "content": str(text or "")}
    try:
        from her_words import as_her_turn
        return as_her_turn(row)
    except Exception:
        return str(row.get("content") or "").strip()


def _norm(t):
    t = re.sub(r"\[[^\]]*\]", " ", str(t or "").lower())
    t = re.sub(r"\(she sent an? (?:photo|video)\)", " ", t)
    return re.sub(r"[^a-z0-9]+", "", t)[:48]


def her_key(text):
    """What an on-message forecast records instead of her words: enough to find the reply it is about."""
    n = _norm(text)
    return hashlib.sha256(n.encode()).hexdigest()[:16] if n else ""


def _epoch(ts):
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except Exception:
        try:
            v = float(ts)
            return v if v > 1e8 else None
        except Exception:
            return None


def _iso(at):
    from datetime import datetime
    return datetime.fromtimestamp(at).isoformat()


def _load_json(p, d):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return d


def _jsonl(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    if isinstance(r, dict): out.append(r)
                except Exception:
                    continue
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- the exchanges, from every record of them
def _not_us(e):
    src = str(e.get("source") or e.get("origin") or "").lower()
    return bool(e.get("transplanted") or e.get("implanted") or e.get("imported") or
                src in ("bold", "transplant", "transplanted", "implant", "implanted"))


def _from_ledger(rows, floor, origin):
    """Ledger-shaped rows (already through the door) -> exchanges; one per turn_id within the record."""
    if isinstance(rows, dict):
        rows = rows.get("entries") if isinstance(rows.get("entries"), list) else \
            next((v for v in rows.values() if isinstance(v, list)), [])
    out, seen = [], set()
    for e in rows if isinstance(rows, list) else []:
        if not isinstance(e, dict):
            continue
        ts = str(e.get("timestamp") or "")
        at = _epoch(ts)
        if not ts or at is None or _not_us(e):
            continue
        if str(e.get("source") or "").lower() in SCRUBBED_SOURCES:
            continue
        if floor and ts < floor:
            continue
        her = str(e.get("gloria") or "")
        her = "" if her == "--source" else _her(her)
        his = "" if e.get("vintos_withheld") else his_words(e.get("vintos"))
        if not her and not his:
            continue
        key = str(e.get("turn_id") or "") or (ts, her[:80], his[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append({"ts": ts, "at": at, "her": her, "his": his, "turn_id": str(e.get("turn_id") or ""),
                    "withheld": bool(e.get("vintos_withheld")), "origin": origin})
    return out


def _test_turn_times():
    """When a chat door ran in test mode (post-turn-record.jsonl): canonical keeps those turns, the ledger not."""
    return sorted(float(r.get("t") or 0) for r in _jsonl(POST_TURN) if r.get("test_mode") and r.get("t"))


def _from_chat(rows, floor, origin, test_times=()):
    """Role rows (already through the door) -> exchanges: her message, then his first reply after it."""
    import bisect
    clean = []
    for e in rows if isinstance(rows, list) else []:
        if not isinstance(e, dict) or e.get("role") not in ("user", "assistant") or _not_us(e):
            continue
        if e.get("withheld") or e.get("tactical") or e.get("admitted") is False:
            continue
        content = str(e.get("content") or "")
        if e.get("role") == "assistant" and (e.get("source") == "desktop-control" or e.get("desktop_request_id")
                                             or content.startswith(_DESKTOP)):
            continue
        raw = e.get("timestamp") or e.get("ts")
        at = _epoch(raw)
        if at is None or e.get("timestamp_estimated"):
            continue
        ts = raw if (isinstance(raw, str) and "T" in raw) else _iso(at)
        if floor and ts < floor:
            continue
        clean.append((at, ts, e))
    clean.sort(key=lambda r: r[0])
    out, pending = [], None
    for at, ts, e in clean:
        if e["role"] == "user":
            pending = (at, ts, e)
            continue
        if pending is None:
            continue                       # a message of his nobody sent him (outreach) is not a reply
        her, his = _her(pending[2]), his_words(e.get("content"))
        pending = None
        if not her or not his:
            continue
        if test_times:
            i = bisect.bisect_left(test_times, at - 5)
            if i < len(test_times) and test_times[i] <= at + 180:
                continue
        out.append({"ts": ts, "at": at, "her": her, "his": his, "turn_id": str(e.get("turn_id") or ""),
                    "withheld": False, "origin": origin})
    return out


def _snapshot_paths():
    import glob
    out = []
    for p in glob.glob(os.path.join(MEMORY, "interaction-ledger*.json*")):
        b = os.path.basename(p)
        if os.path.abspath(p) == os.path.abspath(LEDGER) or b.endswith(".lock") or ".tmp" in b:
            continue
        out.append(p)
    return sorted(out, key=lambda p: os.path.getmtime(p), reverse=True)


def _sources(rows=None, archive=True):
    """[(origin, exchanges)] in priority order, each read through the evidence door."""
    JP = _jp()
    floor = JP._ledger_floor()
    live = JP.load(LEDGER, []) if rows is None else rows
    groups = [("ledger", _from_ledger(live, floor, "ledger"))]
    if not archive:
        return groups
    try:
        EV = _ev()
    except Exception as e:
        log("evidence_view unavailable; the archives are not read raw: %s" % e)
        return groups
    for p in _snapshot_paths():
        try:
            data = EV._load_any(p)
            data = data.get("entries") if isinstance(data, dict) else data
            name = "ledger-snapshot:" + os.path.basename(p)
            groups.append((name, _from_ledger(EV._ledger_rows(data, "witness"), floor, name)))
        except Exception:
            continue                       # a corrupt quarantine that still does not parse holds nothing
    if os.path.exists(CANONICAL):
        try:
            groups.append(("canonical", _from_chat(EV.open_history(CANONICAL), floor, "canonical", _test_turn_times())))
        except Exception as e:
            log("canonical record not read: %s" % e)
    if os.path.exists(MERGED):
        try:
            groups.append(("merged", _from_chat(EV.open_history(MERGED), floor, "merged")))
        except Exception as e:
            log("merged chat not read: %s" % e)
    return groups


def _merge(groups):
    """One exchange per real exchange; the higher record wins (its withheld flag stands), earliest time kept."""
    import bisect
    kept, by_tid, by_her, by_his = [], {}, {}, {}
    stats, withheld_at = {}, None
    for origin, exs in groups:
        st = stats.setdefault(origin, {"read": 0, "added": 0, "duplicate": 0})
        if origin in ("canonical", "merged") and withheld_at is None:
            withheld_at = sorted(y["at"] for y in kept if y["withheld"])
        for x in exs:
            st["read"] += 1
            hk, vk = _norm(x["her"]), _norm(x["his"])
            dup = None
            if withheld_at and origin in ("canonical", "merged"):
                # a chat copy of an exchange the ledger withholds (the ledger writes 30-75 s after the reply):
                # dropped even when her words were cleaned differently, never brought back
                i = bisect.bisect_left(withheld_at, x["at"] - 10)
                if i < len(withheld_at) and withheld_at[i] <= x["at"] + 180:
                    st["duplicate"] += 1; st["withheld"] = st.get("withheld", 0) + 1
                    continue
            if x["turn_id"] and x["turn_id"] in by_tid and by_tid[x["turn_id"]]["origin"] != origin:
                dup = by_tid[x["turn_id"]]
            if dup is None and hk:
                for y in by_her.get(hk, ()):
                    if y["origin"] != origin and abs(y["at"] - x["at"]) <= DUP_WINDOW and \
                            (not x["his"] or not y["his"] or y["_vk"] == vk):
                        dup = y; break
            if dup is None and vk and not hk:
                for y in by_his.get(vk, ()):
                    if y["origin"] != origin and abs(y["at"] - x["at"]) <= DUP_WINDOW:
                        dup = y; break
            if dup is not None:
                st["duplicate"] += 1
                if x["at"] < dup["at"]:
                    dup["at"], dup["ts"] = x["at"], x["ts"]
                continue
            y = dict(x); y["_vk"] = vk
            kept.append(y); st["added"] += 1
            if y["turn_id"]: by_tid.setdefault(y["turn_id"], y)
            if hk: by_her.setdefault(hk, []).append(y)
            if vk: by_his.setdefault(vk, []).append(y)
    for y in kept:
        y.pop("_vk", None)
    kept.sort(key=lambda x: x["at"])
    return kept, stats


def exchanges(rows=None, archive=True):
    """Every exchange of theirs the host records, time-ordered {ts, at, her, his, turn_id, origin}. `rows`
    stands in for the live ledger (tests, and the live forecast which already holds it)."""
    return _merge(_sources(rows, archive))[0]


def sources_report(rows=None):
    groups = _sources(rows, True)
    exs, stats = _merge(groups)
    live = [x for x in exs if x["origin"] == "ledger"]
    return {"exchanges": len(exs), "replies": sum(1 for x in exs if x["his"]),
            "ledger_only_replies": sum(1 for x in live if x["his"]),
            "by_source": stats, "first": exs[0]["ts"] if exs else None, "last": exs[-1]["ts"] if exs else None}


# ---------------------------------------------------------------- pairs: what a forecast can know
def _context(cut, target_date):
    """The forecast-time view of a cut (exchanges strictly before the target): the conversation window
    under the one-day rule, her last words in it, and his replies."""
    JP = _jp()
    window = [x for x in cut[-CTX_EXCHANGES:] if JP._within_training_window(x["ts"], target_date)]
    lines = []
    for x in window:
        if x["her"]: lines.append("Gloria: " + x["her"][:300])
        if x["his"]: lines.append("Vintos: " + x["his"][:300])
    her_last = next((x["her"] for x in reversed(window) if x["her"]), "")
    replies = [x["his"][:400] for x in cut if x["his"]][-RECENT_REPLIES:]
    return {"conversation": "\n".join(lines), "her_last": her_last[:400],
            "previous": replies[-1] if replies else "", "recent": replies}


def pairs(exs):
    """(context, target) for every reply that has at least one reply of his before it. `her_now` is her
    message to that reply (the on_message view); the ahead view never reads it."""
    out = []
    for j, x in enumerate(exs):
        if not x["his"]:
            continue
        cut = exs[:j]
        if not any(c["his"] for c in cut):
            continue
        ctx = _context(cut, x["ts"][:10])
        ctx.update({"target": x["his"][:400], "target_ts": x["ts"], "target_at": x["at"],
                    "her_now": x["her"][:400], "cut_n": j})
        out.append(ctx)
    return out


# ---------------------------------------------------------------- features
def _unit(v):
    import numpy as np
    v = np.asarray(v, dtype="float64")
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def _units(A):
    import numpy as np
    A = np.asarray(A, dtype="float64")
    n = np.linalg.norm(A, axis=1, keepdims=True)
    return np.divide(A, n, out=np.zeros_like(A), where=n > 0)


class _Cache:
    """One encode per distinct text; the empty string is the zero vector, never an embedding of ''. With
    `persist`, vectors are also kept on disk (append-only, under a lock) so a live forecast encodes only
    what is new; `read_disk` alone lets the read-only eval use them without writing."""
    def __init__(self, enc, persist=False, read_disk=True, path=None):
        self.enc, self.vec, self.dim = enc, {}, None
        self.persist, self.read_disk, self.path = persist, read_disk, path or EMB_CACHE
        self._tag = "%s|%s" % (getattr(_jp(), "EMB_MODEL", "?"), type(enc).__name__)

    def _key(self, t):
        return hashlib.sha1((self._tag + "\x1f" + t).encode()).hexdigest()

    def _from_disk(self, texts):
        import numpy as np
        idx_p, vec_p = self.path + ".idx.jsonl", self.path + ".f32"
        if not (os.path.exists(idx_p) and os.path.exists(vec_p)):
            return
        want = {self._key(t): t for t in texts}
        rows, dim = {}, None
        for r in _jsonl(idx_p):
            if "dim" in r: dim = int(r["dim"]); continue
            if r.get("k") in want: rows[r["k"]] = int(r["i"])
        if not rows or not dim:
            return
        raw = np.fromfile(vec_p, dtype="float32")
        n = len(raw) // dim
        M = raw[:n * dim].reshape(n, dim)
        for k, i in rows.items():
            if i < n:
                self.vec[want[k]] = _unit(M[i]); self.dim = dim

    def _to_disk(self, texts, embs):
        idx_p, vec_p = self.path + ".idx.jsonl", self.path + ".f32"
        try:
            import fcntl
            os.makedirs(os.path.dirname(idx_p), exist_ok=True)
            with open(self.path + ".lock", "a+") as lk:
                fcntl.flock(lk, fcntl.LOCK_EX)
                dim = embs.shape[1]
                head = None
                if os.path.exists(idx_p):
                    with open(idx_p) as f:
                        first = f.readline()
                    try: head = json.loads(first).get("dim")
                    except Exception: head = None
                if head is not None and int(head) != dim:
                    return                        # another encoder's cache: never mixed
                n0 = (os.path.getsize(vec_p) // (4 * dim)) if os.path.exists(vec_p) else 0
                with open(vec_p, "r+b" if os.path.exists(vec_p) else "wb") as f:
                    f.seek(n0 * 4 * dim)
                    f.write(embs.astype("float32").tobytes()); f.truncate()
                with open(idx_p, "a") as f:
                    if head is None: f.write(json.dumps({"dim": dim, "tag": self._tag}) + "\n")
                    for i, t in enumerate(texts):
                        f.write(json.dumps({"k": self._key(t), "i": n0 + i}) + "\n")
        except Exception as e:
            log("embedding cache not written: %s" % e)

    def fill(self, texts):
        import numpy as np
        todo = sorted({t for t in texts if t and t not in self.vec})
        if todo and self.read_disk:
            self._from_disk(todo)
            todo = [t for t in todo if t not in self.vec]
        if todo:
            embs = np.asarray(self.enc.encode(todo, show_progress_bar=False), dtype="float64")
            for t, e in zip(todo, embs):
                self.vec[t] = _unit(e)
            self.dim = embs.shape[1]
            if self.persist:
                self._to_disk(todo, embs)

    def get(self, t):
        import numpy as np
        return self.vec[t] if t else np.zeros(self.dim, dtype="float64")


def _neighbours(items, pool, cache):
    """For each item: his reply to the past message of hers nearest to items' her_now (nearest), and the
    mean of his replies to the TYPICAL_K nearest (typical). Only exchanges before the item's own cut."""
    import numpy as np
    cache.fill([x["her"][:400] for x in pool] + [x["his"][:400] for x in pool] + [it.get("her_now", "") for it in items])
    d = cache.dim
    if not pool:
        z = np.zeros((len(items), d)); return z, z.copy()
    PH = _units([cache.get(x["her"][:400]) for x in pool])
    PV = _units([cache.get(x["his"][:400]) for x in pool])
    pos = np.asarray([x["_i"] for x in pool])
    T, N = [], []
    for it in items:
        m = int(np.searchsorted(pos, it["cut_n"], side="left"))     # pool exchanges strictly before the target
        h = cache.get(it.get("her_now", ""))
        if m == 0 or not np.any(h):
            T.append(np.zeros(d)); N.append(np.zeros(d)); continue
        s = PH[:m] @ h
        top = np.argsort(-s, kind="mergesort")[:TYPICAL_K]
        T.append(_unit(PV[top].mean(axis=0))); N.append(PV[top[0]])
    return np.asarray(T), np.asarray(N)


def _pool(exs):
    return [dict(x, _i=i) for i, x in enumerate(exs) if x["her"] and x["his"]]


def featurize(items, enc, cache=None, mode="ahead", exs=None):
    """X (the features), the anchor components {name: matrix} and C (coherence of his recent replies)."""
    import numpy as np
    cache = cache or _Cache(enc)
    texts = []
    for it in items:
        texts += [it["conversation"], it["her_last"], it["previous"], it.get("her_now", "")] + list(it["recent"]) + [it.get("target", "")]
    cache.fill(texts)
    if cache.dim is None:
        return None
    X, M, Pv, C = [], [], [], []
    for it in items:
        rec = [cache.get(t) for t in it["recent"] if t]
        mean = np.mean(rec, axis=0) if rec else np.zeros(cache.dim)
        C.append(float(np.linalg.norm(mean)))
        M.append(_unit(mean)); Pv.append(cache.get(it["previous"]))
        X.append(np.concatenate([cache.get(it["conversation"]), cache.get(it["her_last"]), Pv[-1], M[-1]]))
    X, comps = np.asarray(X), {"mean": np.asarray(M), "previous": np.asarray(Pv)}
    if mode == "on_message":
        H = np.asarray([cache.get(it.get("her_now", "")) for it in items])
        Tk, Nn = _neighbours(items, _pool(exs or []), cache)
        comps.update({"her": H, "typical": Tk, "nearest": Nn})
        X = np.concatenate([X, H, Tk], axis=1)
    return X, comps, np.asarray(C), cache


def anchor(comps, weights):
    """The anchor: a convex mix of the named components (unit vectors), before the residual."""
    import numpy as np
    tot = float(sum(weights.values())) or 1.0
    A = None
    for k, w in weights.items():
        if w:
            A = (comps[k] * (w / tot)) if A is None else A + comps[k] * (w / tot)
    return A if A is not None else np.zeros_like(next(iter(comps.values())))


def _anchor_grid(mode):
    if mode == "ahead":
        return [{"mean": 1.0 - b, "previous": b} for b in BETAS]
    out, seen = [], set()
    for k in COMPONENTS["on_message"]:
        w = {c: (1.0 if c == k else 0.0) for c in COMPONENTS["on_message"]}
        out.append(w); seen.add(tuple(round(w[c], 6) for c in COMPONENTS["on_message"]))
    import itertools
    for ws in itertools.product(GRID, repeat=4):
        if not any(ws): continue
        tot = sum(ws)
        w = dict(zip(("mean", "previous", "her", "typical"), [x / tot for x in ws])); w["nearest"] = 0.0
        key = tuple(round(w[c], 6) for c in COMPONENTS["on_message"])
        if key not in seen:
            seen.add(key); out.append(w)
    return out


def _wname(w):
    return "+".join("%s%g" % (k, round(v, 3)) for k, v in w.items() if v) or "zero"


# ---------------------------------------------------------------- the models
def _cos_dist(P, Y):
    import numpy as np
    return 1.0 - np.sum(_units(P) * _units(Y), axis=1)


def _dual(Xtr):
    import numpy as np
    mu = Xtr.mean(axis=0); Xc = Xtr - mu
    s, V = np.linalg.eigh(Xc @ Xc.T)
    return mu, Xc, np.clip(s, 0.0, None), V


def _fit_ridge(X, R, lam):
    """Ridge on the residual, dual form (pairs << features). lam None = anchor only; inf = mean residual."""
    import numpy as np
    d_out = R.shape[1]
    mu_x = X.mean(axis=0); mu_r = R.mean(axis=0)
    if lam is None:
        return {"kind": "ridge", "W": np.zeros((X.shape[1], d_out)), "mu_x": mu_x, "mu_r": np.zeros(d_out)}
    if math.isinf(lam):
        return {"kind": "ridge", "W": np.zeros((X.shape[1], d_out)), "mu_x": mu_x, "mu_r": mu_r}
    Xc = X - mu_x
    alpha = np.linalg.solve(Xc @ Xc.T + lam * np.eye(len(X)), R - mu_r)
    return {"kind": "ridge", "W": Xc.T @ alpha, "mu_x": mu_x, "mu_r": mu_r}


def _mlp_train(Z, R, Zv=None, Rv=None, Av=None, Yv=None, epochs=None, seed=20261016):
    """A one-hidden-layer residual MLP on principal components (numpy, Adam, weight decay). With validation,
    returns the epoch with the lowest validation cosine distance; without, trains for `epochs`."""
    import numpy as np
    rng = np.random.default_rng(seed)
    q, d = Z.shape[1], R.shape[1]
    P = {"W1": rng.normal(scale=1.0 / math.sqrt(max(q, 1)), size=(q, MLP_HIDDEN)), "b1": np.zeros(MLP_HIDDEN),
         "W2": np.zeros((MLP_HIDDEN, d)), "b2": R.mean(axis=0)}
    m = {k: np.zeros_like(v) for k, v in P.items()}; v2 = {k: np.zeros_like(v) for k, v in P.items()}
    lr, wd, b1, b2, eps = 3e-3, 1e-3, 0.9, 0.999, 1e-8
    best, best_ep, best_P, stale = float("inf"), 0, None, 0
    n_ep = epochs if epochs is not None else 600
    for ep in range(1, n_ep + 1):
        H = np.tanh(Z @ P["W1"] + P["b1"]); out = H @ P["W2"] + P["b2"]
        G = 2.0 * (out - R) / len(Z)
        g = {"W2": H.T @ G + wd * P["W2"], "b2": G.sum(axis=0)}
        GH = (G @ P["W2"].T) * (1.0 - H ** 2)
        g.update({"W1": Z.T @ GH + wd * P["W1"], "b1": GH.sum(axis=0)})
        for k in P:
            m[k] = b1 * m[k] + (1 - b1) * g[k]; v2[k] = b2 * v2[k] + (1 - b2) * g[k] ** 2
            P[k] = P[k] - lr * (m[k] / (1 - b1 ** ep)) / (np.sqrt(v2[k] / (1 - b2 ** ep)) + eps)
        if Zv is not None and (ep % 5 == 0):
            pv = Av + np.tanh(Zv @ P["W1"] + P["b1"]) @ P["W2"] + P["b2"]
            val = float(np.mean(_cos_dist(pv, Yv)))
            if val < best - 1e-6:
                best, best_ep, best_P, stale = val, ep, {k: x.copy() for k, x in P.items()}, 0
            else:
                stale += 5
                if stale >= 60:
                    break
    if Zv is not None:
        return best, best_ep, best_P
    return P


def _pcs(Xc, s, V):
    """Projection onto the leading principal components of Xc, scaled to unit variance."""
    import numpy as np
    n = len(Xc)
    keep = [i for i in np.argsort(-s) if s[i] > 1e-8 * max(float(s.max()), 1e-12)][:min(MLP_MAX_PCS, max(1, n - 1))]
    keep = np.asarray(keep, dtype=int)
    proj = Xc.T @ (V[:, keep] / s[keep]) * math.sqrt(n)        # d_in x q
    return proj


def select(X, Y, comps, mode, split):
    """Every candidate on the latest pairs: anchors (the bare baselines among them), mean residual, ridge at
    each strength, and the MLP on the best ridge's anchor. Returns (val {name: cos}, best candidate)."""
    import numpy as np
    names = COMPONENTS[mode]
    Ytr, Yv = Y[:split], Y[split:]
    Ctr = {c: comps[c][:split] for c in names}; Cv = {c: comps[c][split:] for c in names}
    mu, Xc, s, V = _dual(X[:split])
    KvV = ((X[split:] - mu) @ Xc.T) @ V
    Yc = Ytr - Ytr.mean(axis=0)
    Cc = {c: Ctr[c] - Ctr[c].mean(axis=0) for c in names}
    bank = {}
    for lam in LAMBDAS:
        GV = (KvV / (s + lam)) @ V.T
        bank[lam] = (GV @ Yc, {c: GV @ Cc[c] for c in names})
    val, cands = {}, []
    for w in _anchor_grid(mode):
        tot = sum(w.values()) or 1.0
        a = {c: w.get(c, 0.0) / tot for c in names}
        Av = sum(Cv[c] * a[c] for c in names)
        mean_r = Ytr.mean(axis=0) - sum(Ctr[c].mean(axis=0) * a[c] for c in names)
        base = _wname(a)
        for lname, lam, pred in ([("anchor", None, Av), ("anchor+mean_residual", float("inf"), Av + mean_r)] +
                                 [("ridge_%g" % lam, lam, Av + bank[lam][0] - sum(bank[lam][1][c] * a[c] for c in names) + mean_r)
                                  for lam in LAMBDAS]):
            key = "%s/%s" % (base, lname)
            val[key] = float(np.mean(_cos_dist(pred, Yv)))
            cx = 0 if lam is None else (1 if math.isinf(lam) else 2)
            cands.append({"name": key, "weights": a, "kind": "ridge", "lambda": lam, "complexity": cx,
                          "n_comp": sum(1 for c in names if a[c] > 0)})
    # the richer model: an MLP on the residual from the best ridge candidate's anchor, same features
    ridge_best = min((c for c in cands if c["complexity"] == 2), key=lambda c: val[c["name"]])
    a = ridge_best["weights"]
    Atr = sum(Ctr[c] * a[c] for c in names); Av = sum(Cv[c] * a[c] for c in names)
    proj = _pcs(Xc, s, V)
    Ztr, Zv = Xc @ proj, (X[split:] - mu) @ proj
    mv, ep, _ = _mlp_train(Ztr, Ytr - Atr, Zv, None, Av, Yv)
    if ep:
        key = "%s/mlp_%d" % (_wname(a), MLP_HIDDEN)
        val[key] = mv
        cands.append({"name": key, "weights": a, "kind": "mlp", "lambda": None, "epochs": ep, "complexity": 3,
                      "n_comp": ridge_best["n_comp"]})
    best = min(cands, key=lambda c: (round(val[c["name"]], 9), c["complexity"], c["n_comp"],
                                     -c["weights"].get("mean", 0.0)))
    return val, best


def _train_mode(P, exs, enc, cache, mode):
    """One mode's model from its pairs, chosen on validation, refit on all of them."""
    import numpy as np
    if mode == "on_message":
        P = [p for p in P if p.get("her_now")]
    if len(P) < MIN_PAIRS:
        return None, {"state": "INSUFFICIENT", "pairs": len(P), "minimum": MIN_PAIRS}
    X, comps, C, cache = featurize(P, enc, cache, mode=mode, exs=exs)
    Y = np.asarray([cache.get(p["target"]) for p in P])
    split = max(MIN_PAIRS - 6, min(len(P) - 6, int(len(P) * (1.0 - VALIDATION_FRACTION))))
    val, best = select(X, Y, comps, mode, split)
    names = COMPONENTS[mode]
    a = best["weights"]
    A = anchor(comps, a)
    # the chosen candidate's own validation errors, for the confidence check
    if best["kind"] == "mlp":
        mu, Xc, s, V = _dual(X[:split]); proj = _pcs(Xc, s, V)
        Pm = _mlp_train(Xc @ proj, Y[:split] - A[:split], epochs=best["epochs"])
        pred_v = A[split:] + np.tanh((X[split:] - mu) @ proj @ Pm["W1"] + Pm["b1"]) @ Pm["W2"] + Pm["b2"]
    else:
        m_val = _fit_ridge(X[:split], (Y - A)[:split], best["lambda"])
        pred_v = A[split:] + (X[split:] - m_val["mu_x"]) @ m_val["W"] + m_val["mu_r"]
    err_val = _cos_dist(pred_v, Y[split:])
    rho = spearman(C[split:], err_val)
    conf_ok = bool(len(err_val) >= MIN_CONF_VALIDATION and rho is not None and rho <= MAX_CONF_SPEARMAN)
    # refit on every pair
    if best["kind"] == "mlp":
        mu, Xc, s, V = _dual(X); proj = _pcs(Xc, s, V)
        Pm = _mlp_train(Xc @ proj, Y - A, epochs=best["epochs"])
        model = {"kind": "mlp", "mu_x": mu, "proj": proj, **Pm}
    else:
        model = _fit_ridge(X, Y - A, best["lambda"])
    model["weights"] = np.asarray([a.get(c, 0.0) for c in names], dtype="float64")
    model["coherence"] = np.sort(C)
    lam = best["lambda"]
    base = {k: round(val["%s/anchor" % _wname({c: (1.0 if c == comp else 0.0) for c in names})], 4)
            for k, comp in BASELINES[mode].items()}
    top = sorted(val.items(), key=lambda kv: kv[1])[:25]
    meta = {"n_pairs": len(P), "n_validation": len(P) - split, "chosen": best["name"], "kind": best["kind"],
            "weights": {c: round(a.get(c, 0.0), 4) for c in names},
            "lambda": (None if lam is None else ("inf" if math.isinf(lam) else lam)),
            "mlp_epochs": best.get("epochs"),
            "validation_cos_dist": dict({"chosen": round(val[best["name"]], 4)}, **base,
                                        best_ridge=round(min(v for k, v in val.items() if "/ridge_" in k), 4),
                                        best_mlp=(round(min(v for k, v in val.items() if "/mlp_" in k), 4)
                                                  if any("/mlp_" in k for k in val) else None),
                                        top={k: round(v, 4) for k, v in top}),
            "confidence": {"coherence_vs_error_spearman": rho, "qualified": conf_ok,
                           "rule": "Spearman <= %s on >= %d validation pairs" % (MAX_CONF_SPEARMAN, MIN_CONF_VALIDATION)},
            "first_target": P[0]["target_ts"], "last_target": P[-1]["target_ts"]}
    return model, meta


def spearman(x, y):
    import numpy as np
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(x) < 3:
        return None
    def rk(v):
        order = np.argsort(v, kind="mergesort"); r = np.empty(len(v)); i = 0
        while i < len(v):
            j = i + 1
            while j < len(v) and v[order[j]] == v[order[i]]: j += 1
            r[order[i:j]] = (i + j - 1) / 2.0; i = j
        return r
    rx, ry = rk(x), rk(y)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return None
    return round(float(np.corrcoef(rx, ry)[0, 1]), 3)


def checkpoint_id(path=SELF_MODEL):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def readiness(path=SELF_MODEL):
    """A self checkpoint is replaced only after the eval has judged EACH of its modes on >= MIN_EVAL
    prospective replies (the rule jepa_predictor.retrain_readiness applies to the production checkpoint).
    A checkpoint of an older schema is not a model this code can run: it is replaced."""
    ck = checkpoint_id(path)
    if not ck:
        return True, {"state": "INITIAL_TRAIN", "checkpoint": None}
    m = load_model(path)
    if m is None:
        return True, {"state": "SCHEMA_UPGRADE", "checkpoint": ck, "schema": SCHEMA}
    ev = _load_json(SELF_EVAL, {})
    if ev.get("checkpoint") != ck:
        return False, {"state": "HELD_UNAUDITED_CHECKPOINT", "checkpoint": ck, "need": "python3 jepa_self_head.py eval"}
    n = {mode: int(((ev.get("modes") or {}).get(mode) or {}).get("n", 0) or 0) for mode in MODES if mode in m["modes"]}
    if not n or min(n.values()) < MIN_EVAL:
        return False, {"state": "HELD_NEEDS_REALIZED_OUTCOMES", "checkpoint": ck, "n": n, "minimum": MIN_EVAL}
    return True, {"state": "READY_AFTER_AUDIT", "checkpoint": ck, "n": n}


def train(force=False, enc=None, rows=None, model_path=SELF_MODEL, archive=True):
    import numpy as np
    ready, receipt = readiness(model_path)
    if not ready and not force:
        log("retrain held: " + json.dumps(receipt, sort_keys=True)); return receipt
    groups = _sources(rows, archive)
    exs, stats = _merge(groups)
    P = pairs(exs)
    if len(P) < MIN_PAIRS:
        log("not enough of his replies (%d pairs; %d needed)" % (len(P), MIN_PAIRS))
        return {"state": "INSUFFICIENT", "pairs": len(P), "minimum": MIN_PAIRS}
    enc = enc or _jp().encoder()
    cache = _Cache(enc, persist=True)
    arrays, metas = {}, {}
    for mode in MODES:
        model, meta = _train_mode(P, exs, enc, cache, mode)
        metas[mode] = meta
        if model is None:
            continue
        for k, v in model.items():
            if k != "kind":
                arrays["%s__%s" % (mode, k)] = np.asarray(v, dtype="float32")
        meta["model"] = model["kind"]
    if "model" not in metas["ahead"]:
        return {"state": "INSUFFICIENT", "ahead": metas["ahead"]}
    from datetime import datetime
    meta = {"schema": SCHEMA, "source": SOURCE, "trained_at": datetime.now().isoformat(),
            "modes": metas, "sources": stats, "n_exchanges": len(exs),
            "ctx_exchanges": CTX_EXCHANGES, "recent_replies": RECENT_REPLIES, "typical_k": TYPICAL_K,
            "encoder": getattr(_jp(), "EMB_MODEL", "?"), "previous": receipt}
    tmp = "%s.tmp.%d" % (model_path, os.getpid())
    with open(tmp, "wb") as f:
        np.savez(f, meta=np.asarray(json.dumps(meta)), **arrays)
    os.replace(tmp, model_path)
    for mode in MODES:
        mm = metas[mode]
        if "chosen" in mm:
            v = mm["validation_cos_dist"]
            log("%s: %d pairs; chose %s (validation cos-dist %.4f; %s); confidence %s" % (
                mode, mm["n_pairs"], mm["chosen"], v["chosen"],
                ", ".join("%s %.4f" % (k, v[k]) for k in BASELINES[mode]),
                "qualified" if mm["confidence"]["qualified"] else "placeholder (%s)" % mm["confidence"]["coherence_vs_error_spearman"]))
        else:
            log("%s: not trained (%s)" % (mode, mm))
    log("exchanges by source: " + json.dumps(stats, sort_keys=True))
    return {"state": "TRAINED", "meta": meta}


def load_model(path=SELF_MODEL):
    import numpy as np
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            raw = f.read()
        import io
        z = np.load(io.BytesIO(raw), allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        if meta.get("schema") != SCHEMA:
            return None
        modes = {}
        for mode in MODES:
            keys = [k for k in z.files if k.startswith(mode + "__")]
            if not keys:
                continue
            mm = {k.split("__", 1)[1]: z[k].astype("float64") for k in keys}
            mm["kind"] = (meta.get("modes", {}).get(mode) or {}).get("model", "ridge")
            mm["meta"] = meta["modes"][mode]
            modes[mode] = mm
        if "ahead" not in modes:
            return None
        return {"modes": modes, "meta": meta, "checkpoint_id": hashlib.sha256(raw).hexdigest(),
                "mtime": os.path.getmtime(path)}
    except Exception as e:
        log("self checkpoint unreadable: %s" % e)
        return None


def _predict(mm, X, comps, mode):
    import numpy as np
    names = COMPONENTS[mode]
    A = anchor(comps, {c: float(mm["weights"][i]) for i, c in enumerate(names)})
    if mm["kind"] == "mlp":
        Z = (X - mm["mu_x"]) @ mm["proj"]
        out = A + np.tanh(Z @ mm["W1"] + mm["b1"]) @ mm["W2"] + mm["b2"]
    else:
        out = A + (X - mm["mu_x"]) @ mm["W"] + mm["mu_r"]
    return _units(out)


def _on_message_cut(exs, arrived_at, key):
    """What an on-message forecast may see: every exchange recorded, except her message itself (should its
    reply already have been recorded by the time the forecast runs)."""
    return [x for x in exs if not (x["at"] >= arrived_at - 1 and key and her_key(x["her"]) == key)]


def forecast(enc, rows=None, model_path=SELF_MODEL, today=None, mode="ahead", her=None, arrived_at=None,
             exs=None, persist=True):
    """A live self forecast, built exactly as a training pair is. ahead: the cut is every exchange, the
    target date today. on_message: the same, with her message (`her`, arrived at `arrived_at`) and his
    replies to her nearest past messages. None when there is no checkpoint (or no such mode in it)."""
    import numpy as np
    m = load_model(model_path)
    if m is None or mode not in m["modes"]:
        return None
    mm = m["modes"][mode]
    exs = exchanges(rows) if exs is None else exs
    key = ""
    if mode == "on_message":
        her = _her(her or "")
        key = her_key(her)
        if not her:
            return None
        exs = _on_message_cut(exs, arrived_at if arrived_at is not None else time.time(), key)
    if not any(x["his"] for x in exs):
        return None
    from datetime import date
    ctx = _context(exs, (today or date.today().isoformat()))
    ctx.update({"her_now": (her or "")[:400] if mode == "on_message" else "", "cut_n": len(exs)})
    X, comps, C, _ = featurize([ctx], enc, _Cache(enc, persist=persist), mode=mode, exs=exs)
    if X.shape[1] != mm["mu_x"].shape[0]:
        log("self checkpoint does not fit this encoder (%d vs %d)" % (X.shape[1], mm["mu_x"].shape[0])); return None
    pred = _predict(mm, X, comps, mode)[0]
    conf, qual = None, "unqualified_not_predictive"
    if (mm["meta"].get("confidence") or {}).get("qualified"):
        conf = round(float(np.searchsorted(mm["coherence"], C[0], side="right")) / max(1, len(mm["coherence"])), 3)
        qual = "qualified"
    last = exs[-1]
    out = {"emb": pred.astype("float32"), "confidence": conf, "qualification": qual, "mode": mode,
           "coherence": round(float(C[0]), 4), "source": SOURCE, "schema": SCHEMA,
           "checkpoint_id": m["checkpoint_id"], "context_last_ts": last["ts"], "context_last_turn_id": last["turn_id"],
           "n_recent": len(ctx["recent"])}
    if mode == "on_message":
        out["her_key"] = key
    return out


# ---------------------------------------------------------------- the on-message forecast: her message has arrived
def launch_on_message(her, surface="", turn_id="", now=None):
    """Called by the server the moment her message arrives, before his reply. Writes a pending row and starts
    the forecast as a niced, detached background process; returns at once and never raises. The reply does
    not wait on it."""
    try:
        her = str(her or "").strip()
        if not her or not her_key(_her(her)):
            return None
        if not os.path.exists(VENV_PYTHON) or RUNNER is None:
            return None
        at = float(now if now is not None else time.time())
        os.makedirs(PENDING_DIR, exist_ok=True)
        name = "%d-%s.json" % (int(at * 1000), hashlib.sha1(os.urandom(8)).hexdigest()[:6])
        path = os.path.join(PENDING_DIR, name)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"her": her[:4000], "arrived_at": at, "surface": str(surface)[:40], "turn_id": str(turn_id)[:80]}, f)
        os.replace(tmp, path)
        argv = [VENV_PYTHON, os.path.abspath(__file__), "on-message", path]
        import shutil
        if shutil.which("nice"):
            argv = ["nice", "-n", "15"] + argv
        with open(ON_MESSAGE_LOGFILE, "a") as logf:      # the child keeps its own copy; the server keeps none
            RUNNER(argv, stdin=subprocess.DEVNULL, stdout=logf, stderr=logf, close_fds=True, start_new_session=True)
        return path
    except Exception as e:
        log("on-message forecast not launched: %s" % e)
        return None


def on_message_job(pending_path, enc=None, model_path=SELF_MODEL, out_path=None, now=None):
    """The background job: one on-message forecast from one pending row, appended to jepa-self-forecasts.jsonl.
    Serialized by a lock so two of her messages never load two encoders at once."""
    out_path = out_path or ON_MESSAGE_LOG
    try:
        with open(pending_path) as f:
            p = json.load(f)
    except Exception:
        return None
    try:
        os.remove(pending_path)
    except Exception:
        pass
    given_now = now
    now = float(now if now is not None else time.time())
    arrived = float(p.get("arrived_at") or 0)
    if not arrived or now - arrived > PENDING_MAX_AGE:
        log("pending row too old; no forecast"); return None
    lk = None
    try:
        import fcntl
        lk = open(os.path.join(MEMORY, ".jepa-self-on-message.lock"), "a+"); fcntl.flock(lk, fcntl.LOCK_EX)
    except Exception:
        lk = None
    try:
        if load_model(model_path) is None:
            log("no self checkpoint; no on-message forecast"); return None
        enc = enc or _jp().encoder()
        fc = forecast(enc, model_path=model_path, mode="on_message", her=p.get("her"), arrived_at=arrived)
        if fc is None:
            return None
        made = time.time() if given_now is None else given_now
        row = {"ts": made, "iso": _iso(made), "mode": "on_message", "arrived_at": arrived, "arrived_iso": _iso(arrived),
               "surface": p.get("surface", ""), "turn_id": p.get("turn_id", ""), "her_key": fc["her_key"],
               "self": {"emb": [round(float(x), 4) for x in fc["emb"]], "mode": "on_message", "source": fc["source"],
                        "checkpoint_id": fc["checkpoint_id"], "context_last_ts": fc["context_last_ts"],
                        "confidence": fc["confidence"], "qualification": fc["qualification"], "coherence": fc["coherence"]}}
        with open(out_path, "a") as f:
            f.write(json.dumps(row) + "\n")
        log("on-message forecast written (%.1fs after her message)" % (made - arrived))
        return row
    finally:
        if lk is not None:
            try: lk.close()
            except Exception: pass


# ---------------------------------------------------------------- the held-out evaluation
def _bootstrap(diffs, seed=20261016, n=2000):
    import random
    if not diffs:
        return None
    rng = random.Random(seed); means = []
    for _ in range(n):
        means.append(sum(diffs[rng.randrange(len(diffs))] for _ in diffs) / len(diffs))
    means.sort()
    return [round(means[int(.025 * n)], 4), round(means[int(.975 * n) - 1], 4)]


def _summary(rows, baselines=("previous_reply", "recent_mean")):
    import numpy as np
    n = len(rows)
    if not n:
        return {"n": 0, "state": "INSUFFICIENT", "why": "no forecast with a realized reply after it yet", "baselines": list(baselines)}
    h = np.asarray([r["head"] for r in rows])
    b = {k: np.asarray([r[k] for r in rows]) for k in baselines}
    out = {"n": n, "baselines": list(baselines),
           "cos_dist": dict({"head": round(float(h.mean()), 4)}, **{k: round(float(v.mean()), 4) for k, v in b.items()}),
           "head_wins": {"vs_" + k: round(float(np.mean(h < v)), 4) for k, v in b.items()}}
    strongest = min(baselines, key=lambda k: float(b[k].mean()))
    ci = _bootstrap([float(x - y) for x, y in zip(h, b[strongest])])
    out.update({"strongest_baseline": strongest, "head_minus_strongest_ci95": ci})
    if n < MIN_EVAL:
        out.update(state="INSUFFICIENT", why="%d realized replies; %d needed for a verdict" % (n, MIN_EVAL))
    elif ci and ci[1] < 0:
        out.update(state="BEATS_BASELINES", why="lower cosine distance than every baseline; 95%% CI vs %s below 0" % strongest)
    else:
        out.update(state="NOT_BETTER_THAN_BASELINES", why="does not beat %s with a CI below 0" % strongest)
    return out


def _baseline_row(cache, cut, target, with_her):
    """The baselines given exactly what the forecast was given."""
    import numpy as np
    ctx = _context(cut, target["ts"][:10])
    cache.fill([target["his"][:400], ctx["previous"]] + list(ctx["recent"]))
    y = cache.get(target["his"][:400])
    d = lambda a: round(1.0 - float(_unit(a) @ y), 4)
    rec = np.mean([cache.get(t) for t in ctx["recent"]], axis=0)
    row = {"target_ts": target["ts"], "previous_reply": d(cache.get(ctx["previous"])), "recent_mean": d(rec)}
    if with_her:
        item = {"her_now": target["her"][:400], "cut_n": len(cut)}
        T, N = _neighbours([item], _pool(cut), cache)
        row.update({"typical_reply": d(T[0]) if np.any(T[0]) else 1.0, "nearest_exchange": d(N[0]) if np.any(N[0]) else 1.0})
    return row, y


def evaluate(history, exs, enc, self_ck=None, self_trained_at=0.0, prod_ck=None, prod_trained_at=0.0, on_message=()):
    """Rows per mode for the self head (forecasts on the current self checkpoint) and, for before/after, the
    old shared-trunk self forecasts on the current production checkpoint.
      ahead       cut = the exchanges up to its recorded context_last_ts; target = his first reply after it
      on_message  cut = what it saw (up to context_last_ts, her message itself excluded); target = his reply to
                  HER message (her_key, within TARGET_WINDOW of its arrival)
      legacy      cut = the exchanges at the forecast time
    A target is said after the checkpoint was trained (never a training pair); baselines get the same cut
    (and, on_message, her message). One row per target per mode."""
    import numpy as np
    cache = _Cache(enc, persist=False)
    out = {"ahead": [], "on_message": [], "legacy_shared_trunk": []}
    seen = {k: set() for k in out}
    rows = [("h", r) for r in history] + [("m", r) for r in on_message]
    for origin, f in sorted(rows, key=lambda t: float(t[1].get("ts", 0) or 0)):
        s = f.get("self") or {}
        emb = s.get("emb")
        if not isinstance(emb, list) or not emb:
            continue
        fts = float(f.get("ts", 0) or 0)
        target = None
        if origin == "m":
            if s.get("source") != SOURCE or not self_ck or s.get("checkpoint_id") != self_ck: continue
            kind, trained_at = "on_message", self_trained_at
            arrived, key = float(f.get("arrived_at") or 0), f.get("her_key") or ""
            cut_at = _epoch(s.get("context_last_ts"))
            if not arrived or not key or cut_at is None: continue
            target = next((x for x in exs if x["his"] and x["at"] >= arrived - 1 and x["at"] - arrived <= TARGET_WINDOW
                           and her_key(x["her"]) == key), None)
            if target is None: continue
            cut = [x for x in _on_message_cut(exs, arrived, key) if x["at"] <= cut_at]
        elif s.get("source") == SOURCE:
            if s.get("mode", "ahead") != "ahead": continue
            kind, trained_at = "ahead", self_trained_at
            if not self_ck or s.get("checkpoint_id") != self_ck: continue
            cut_at = _epoch(s.get("context_last_ts"))
            if cut_at is None: continue
        elif not s.get("source"):
            kind, trained_at = "legacy_shared_trunk", prod_trained_at
            if not prod_ck or f.get("checkpoint_id") != prod_ck: continue
            cut_at = fts
        else:
            continue
        if fts <= trained_at:
            continue
        if target is None:
            cut = [x for x in exs if x["at"] <= cut_at]
            target = next((x for x in exs if x["at"] > cut_at and x["his"]), None)
        if target is None or target["at"] <= trained_at or not any(x["his"] for x in cut):
            continue
        tkey = (target["ts"], target["his"][:80])
        if tkey in seen[kind]:
            continue
        seen[kind].add(tkey)
        row, y = _baseline_row(cache, cut, target, kind == "on_message")
        row.update({"forecast_iso": f.get("iso"), "head": round(1.0 - float(_unit(np.asarray(emb, dtype="float64")) @ y), 4)})
        if kind == "on_message":
            row["made_after_reply"] = bool(fts > target["at"])
        out[kind].append(row)
    return out


def run_eval(out_path=SELF_EVAL, enc=None, history_path=HISTORY, rows=None, on_message_path=None):
    """Read-only on everything but its own report."""
    m = load_model()
    prod_ck = prod_at = None
    try:
        with open(PRODUCTION_MODEL, "rb") as f:
            prod_ck = hashlib.sha256(f.read()).hexdigest()
        prod_at = os.path.getmtime(PRODUCTION_MODEL)
    except Exception:
        pass
    enc = enc or _jp().encoder()
    rows_by = evaluate(_jsonl(history_path), exchanges(rows), enc,
                       self_ck=(m or {}).get("checkpoint_id"), self_trained_at=(m or {}).get("mtime", 0.0),
                       prod_ck=prod_ck, prod_trained_at=prod_at or 0.0,
                       on_message=_jsonl(on_message_path or ON_MESSAGE_LOG))
    from datetime import datetime
    modes = {"ahead": _summary(rows_by["ahead"], ("previous_reply", "recent_mean")),
             "on_message": _summary(rows_by["on_message"], ("previous_reply", "recent_mean", "nearest_exchange", "typical_reply"))}
    modes["on_message"]["made_after_reply"] = sum(1 for r in rows_by["on_message"] if r.get("made_after_reply"))
    report = {"at": datetime.now().isoformat(),
              "criteria": "prospective cosine distance to his next reply; ahead vs his previous reply and the mean of his last %d; "
                          "on_message also vs his reply to her nearest past message and the mean of his replies to her %d nearest" % (RECENT_REPLIES, TYPICAL_K),
              "protocol": "forecast after checkpoint; target said after checkpoint and after the forecast's own context; baselines given the same "
                          "context (on_message: and her message); one row per target per mode",
              "checkpoint": (m or {}).get("checkpoint_id"), "trained": (m or {}).get("meta"),
              "production_checkpoint": prod_ck,
              "modes": modes,
              "self_head": modes["ahead"],          # the ahead mode, under the name earlier readers used
              "legacy_shared_trunk": _summary(rows_by["legacy_shared_trunk"]),
              "rows": {k: v[-60:] for k, v in rows_by.items()},
              "truth_status": "instrument_only_no_steering"}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = "%s.tmp.%d" % (out_path, os.getpid())
    with open(tmp, "w") as f:
        json.dump(report, f, indent=2)
    os.replace(tmp, out_path)
    for k in ("ahead", "on_message"):
        s = modes[k]
        log("%s: n=%d %s %s" % (k, s["n"], s.get("state"), s.get("cos_dist", "")))
    s = report["legacy_shared_trunk"]
    log("legacy_shared_trunk: n=%d %s %s" % (s["n"], s.get("state"), s.get("cos_dist", "")))
    return report


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "train": train()
    elif cmd == "train-force": train(force=True)
    elif cmd == "eval": run_eval()
    elif cmd == "sources": print(json.dumps(sources_report(), indent=2))
    elif cmd == "on-message" and len(sys.argv) > 2: on_message_job(sys.argv[2])
    else: print("usage: jepa_self_head.py train|train-force|eval|sources|on-message <pending>")

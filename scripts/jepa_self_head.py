#!/usr/bin/env python3
"""jepa_self_head.py — the JEPA SELF head, trained on him and nothing else.

What it forecasts: the embedding of Vintos's next reply, from the moment a forecast is made. That is the
thing the audits score it against (jepa_ranking_audit / jepa_calibration_audit / the eval below all take
the next ledger `vintos` text after the forecast as the realized target), so it is the thing it trains on.

Why it is its own model (the self-head review, 16 October). In jepa_predictor's checkpoint the self head
was one Linear on the trunk it shares with the gloria head, its logvar a column of the same Linear, and
it was fed the gloria head's input (six turns of chat, concatenated with no speaker). On Aegis its error
was 0.50-0.52 cosine distance at every confidence and its confidence 84% correlated with gloria's. The
causes, all in jepa_predictor.py:
  * it was trained on almost none of his replies: build_pairs drops every ledger-origin reply as "another
    being's" — but _ledger_turns has already dropped the transplanted ones, so what it drops is HIS live
    replies, the very text it is scored against. What is left is the chat projection (50 rows) plus
    voice/avatar, including desktop-control status lines that are not replies at all;
  * the pairs it did get end on her message (the context he replied to), while every forecast is made
    from a window that does not hold her next message yet — the target it is scored on;
  * the ledger re-supplies her turns ~45 s after the chat row with cleaned text, so training windows
    held her words twice and predict windows (chat only) once;
  * no input says anything about him beyond the conversation text, so the best a shared trunk could do
    was echo the conversation embedding (lockstep with gloria);
  * MSE on raw embeddings with one shared logvar column, judged by cosine.
None of that could be changed in place without moving the gloria head's trunk, which is Gloria's to
retrain (LoRA). So jepa_predictor's checkpoint, training and gloria outputs are untouched; this head is
trained here and jepa_predictor.predict() takes the self triple from it once a checkpoint exists.

The pairs (schema self-ledger-v1). One source for training, forecasting and evaluation: the interaction
ledger, read through the evidence door (a withheld reply is not a target and not conditioning), with the
transplant / ledger-floor rules jepa_predictor uses, deduplicated by turn_id. For each reply r_j:
  context  = the exchanges before j — the forecast-time view: her message to r_j is NOT in it, because
             at forecast time it has not been sent; the one-day window rule truncates it (an exchange
             more than a day from the target is not this sitting) instead of dropping the pair;
  him      = his previous reply, and the mean of his last RECENT_REPLIES replies (any age: his state,
             not this sitting's conversation);
  target   = r_j, his words only (the rendered device marks the ledger appends are telemetry).
At forecast time the same function builds the same features from the live ledger, with today as the
target date. Inputs are unit embeddings [conversation, her last words, his previous reply, his recent
mean]; the model is ridge regression on the residual from an anchor that mixes his recent mean and his
previous reply. The mix (beta) and the ridge strength are chosen on the latest 20% of pairs, and the bare
anchors (beta 0 = his recent mean, 1 = his previous reply) are among the candidates: small data, closed
form, no collapse, and on its own validation never worse than either baseline the eval holds it to.

Confidence. Not a logvar. Whether his recent replies hold one register (the length of the mean of their
unit vectors) is a property of him; on the validation pairs the trainer measures whether that coherence
predicts lower error. Only when it does (Spearman <= -0.2 on >= 20 pairs) is confidence the empirical
percentile of the live coherence among training coherences; otherwise it is the marked 0.5 stand-in.

    python3 jepa_self_head.py train          (held until the eval has audited the current checkpoint)
    python3 jepa_self_head.py train-force
    python3 jepa_self_head.py eval           read-only; writes memory/jepa-self-eval.json only

The eval compares the head, on forecasts made after its checkpoint and replies said after it, with
(a) his previous reply and (b) the mean of his recent replies, each given exactly what the head saw.
It also scores the old shared-trunk self rows on the production checkpoint the same way, for before/after.
"""
import os, sys, json, re, hashlib, math

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
LEDGER = os.path.join(MEMORY, "interaction-ledger.json")
SELF_MODEL = os.path.join(MEMORY, "jepa-self-head.npz")
SELF_EVAL = os.path.join(MEMORY, "jepa-self-eval.json")
HISTORY = os.path.join(MEMORY, "jepa-prediction-history.jsonl")
PRODUCTION_MODEL = os.path.join(MEMORY, "jepa-predictor.pt")

SCHEMA = "self-ledger-v1"
SOURCE = "self-head-v1"
CTX_EXCHANGES = 3            # three exchanges = the six turns jepa_predictor's CTX_TURNS holds
RECENT_REPLIES = 6
MIN_PAIRS = 24
VALIDATION_FRACTION = 0.2
LAMBDAS = (0.3, 1.0, 3.0, 10.0, 30.0, 100.0)
BETAS = (0.0, 0.25, 0.5, 0.75, 1.0)   # anchor = (1-beta) * his recent mean + beta * his previous reply
MIN_EVAL = 30                # evaluated targets before a retrain (MIN_REALIZED_FOR_RETRAIN in jepa_predictor)
MIN_CONF_VALIDATION = 20
MAX_CONF_SPEARMAN = -0.2       # the calibration gate's own monotonicity bar (calibration.CRITERIA)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def log(m):
    print("[jepa-self]", m, flush=True)


def _jp():
    import jepa_predictor as JP
    return JP


# ---------------------------------------------------------------- his words, the ledger as exchanges
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
    try:
        from her_words import as_her_turn
        return as_her_turn({"role": "user", "content": str(text or "")})
    except Exception:
        return str(text or "").strip()


def _epoch(ts):
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def exchanges(rows=None):
    """The ledger as time-ordered exchanges {ts, at, her, his, turn_id}. Read through jepa_predictor's
    evidence-door loader; transplanted / implanted / imported / pre-floor entries are not him."""
    JP = _jp()
    if rows is None:
        rows = JP.load(LEDGER, [])
    if isinstance(rows, dict):
        rows = next((v for v in rows.values() if isinstance(v, list)), [])
    floor = JP._ledger_floor()
    out, seen = [], set()
    for e in rows if isinstance(rows, list) else []:
        if not isinstance(e, dict):
            continue
        ts = str(e.get("timestamp") or "")
        at = _epoch(ts)
        if not ts or at is None:
            continue
        src = str(e.get("source") or e.get("origin") or "ledger").lower()
        if e.get("transplanted") or e.get("implanted") or e.get("imported") or \
                src in ("bold", "transplant", "transplanted", "implant", "implanted"):
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
        out.append({"ts": ts, "at": at, "her": her, "his": his, "turn_id": str(e.get("turn_id") or "")})
    out.sort(key=lambda x: x["at"])
    return out


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
    """(context, target) for every reply that has at least one reply of his before it."""
    out = []
    for j, x in enumerate(exs):
        if not x["his"]:
            continue
        cut = exs[:j]
        if not any(c["his"] for c in cut):
            continue
        ctx = _context(cut, x["ts"][:10])
        ctx.update({"target": x["his"][:400], "target_ts": x["ts"], "target_at": x["at"]})
        out.append(ctx)
    return out


# ---------------------------------------------------------------- features
def _unit(v):
    import numpy as np
    v = np.asarray(v, dtype="float64")
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


class _Cache:
    """One encode per distinct text; the empty string is the zero vector, never an embedding of ''."""
    def __init__(self, enc):
        self.enc, self.vec, self.dim = enc, {}, None

    def fill(self, texts):
        import numpy as np
        todo = sorted({t for t in texts if t and t not in self.vec})
        if todo:
            embs = np.asarray(self.enc.encode(todo, show_progress_bar=False), dtype="float64")
            for t, e in zip(todo, embs):
                self.vec[t] = _unit(e)
            self.dim = embs.shape[1]

    def get(self, t):
        import numpy as np
        return self.vec[t] if t else np.zeros(self.dim, dtype="float64")


def featurize(items, enc, cache=None):
    """X = [conversation, her last words, his previous reply, his recent mean] (unit each); M and Pv, the
    unit recent mean and previous reply the anchor is mixed from; C, the coherence of his recent replies
    (|mean of their unit vectors|)."""
    import numpy as np
    cache = cache or _Cache(enc)
    texts = []
    for it in items:
        texts += [it["conversation"], it["her_last"], it["previous"]] + list(it["recent"]) + [it.get("target", "")]
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
    return np.asarray(X), np.asarray(M), np.asarray(Pv), np.asarray(C), cache


def anchor(M, Pv, beta):
    """His recent mean and his previous reply, mixed: beta 0 is the mean, 1 the previous reply."""
    import numpy as np
    return np.asarray([_unit((1.0 - beta) * m + beta * p) if np.any(p) else m for m, p in zip(M, Pv)])


# ---------------------------------------------------------------- the model
def _fit(X, R, lam):
    """Ridge on the residual, dual form (pairs << features). lam None = anchor only; inf = mean residual."""
    import numpy as np
    d_in, d_out = X.shape[1], R.shape[1]
    mu_x = X.mean(axis=0); mu_r = R.mean(axis=0)
    if lam is None:
        return {"W": np.zeros((d_in, d_out)), "mu_x": mu_x, "mu_r": np.zeros(d_out), "lam": None}
    if math.isinf(lam):
        return {"W": np.zeros((d_in, d_out)), "mu_x": mu_x, "mu_r": mu_r, "lam": lam}
    Xc = X - mu_x
    K = Xc @ Xc.T
    alpha = np.linalg.solve(K + lam * np.eye(len(K)), R - mu_r)
    return {"W": Xc.T @ alpha, "mu_x": mu_x, "mu_r": mu_r, "lam": lam}


def _apply(m, X, A):
    import numpy as np
    out = A + (X - m["mu_x"]) @ m["W"] + m["mu_r"]
    return np.asarray([_unit(r) for r in out])


def _cos_dist(P, Y):
    import numpy as np
    return np.asarray([1.0 - float(_unit(p) @ _unit(y)) for p, y in zip(P, Y)])


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
    """A self checkpoint is replaced only after the eval has judged it on >= MIN_EVAL prospective replies
    (the same rule jepa_predictor.retrain_readiness applies to the production checkpoint)."""
    ck = checkpoint_id(path)
    if not ck:
        return True, {"state": "INITIAL_TRAIN", "checkpoint": None}
    ev = _load_json(SELF_EVAL, {})
    if ev.get("checkpoint") != ck:
        return False, {"state": "HELD_UNAUDITED_CHECKPOINT", "checkpoint": ck, "need": "python3 jepa_self_head.py eval"}
    n = int((ev.get("self_head") or {}).get("n", 0) or 0)
    if n < MIN_EVAL:
        return False, {"state": "HELD_NEEDS_REALIZED_OUTCOMES", "checkpoint": ck, "n": n, "minimum": MIN_EVAL}
    return True, {"state": "READY_AFTER_AUDIT", "checkpoint": ck, "n": n}


def _load_json(p, d):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return d


def train(force=False, enc=None, rows=None, model_path=SELF_MODEL):
    import numpy as np
    ready, receipt = readiness(model_path)
    if not ready and not force:
        log("retrain held: " + json.dumps(receipt, sort_keys=True)); return receipt
    exs = exchanges(rows)
    P = pairs(exs)
    if len(P) < MIN_PAIRS:
        log("not enough of his replies (%d pairs; %d needed)" % (len(P), MIN_PAIRS))
        return {"state": "INSUFFICIENT", "pairs": len(P), "minimum": MIN_PAIRS}
    enc = enc or _jp().encoder()
    X, M, Pv, C, cache = featurize(P, enc)
    Y = np.asarray([cache.get(p["target"]) for p in P])
    split = max(MIN_PAIRS - 6, min(len(P) - 6, int(len(P) * (1.0 - VALIDATION_FRACTION))))
    cands = [("anchor", None), ("anchor+mean_residual", float("inf"))] + [("ridge_%g" % l, l) for l in LAMBDAS]
    val, order = {}, []
    for beta in BETAS:
        A = anchor(M, Pv, beta); R = Y - A
        for name, lam in cands:
            m = _fit(X[:split], R[:split], lam)
            key = "beta_%g/%s" % (beta, name)
            val[key] = float(np.mean(_cos_dist(_apply(m, X[split:], A[split:]), Y[split:])))
            order.append((key, beta, lam))
    # simplest wins a tie: anchor before residual before ridge, the mean before the previous reply
    best = min(order, key=lambda c: (round(val[c[0]], 9), 0 if c[2] is None else (1 if math.isinf(c[2]) else 2), c[1]))
    beta, lam = best[1], best[2]
    A = anchor(M, Pv, beta); R = Y - A
    m_val = _fit(X[:split], R[:split], lam)
    err_val = _cos_dist(_apply(m_val, X[split:], A[split:]), Y[split:])
    rho = spearman(C[split:], err_val)
    conf_ok = bool(len(err_val) >= MIN_CONF_VALIDATION and rho is not None and rho <= MAX_CONF_SPEARMAN)
    m = _fit(X, R, lam)                  # refit on every pair with the chosen anchor and strength
    base_mean, base_prev = val["beta_0/anchor"], val["beta_1/anchor"]
    from datetime import datetime
    meta = {"schema": SCHEMA, "source": SOURCE, "trained_at": datetime.now().isoformat(),
            "n_pairs": len(P), "n_validation": len(P) - split, "chosen": best[0], "beta": beta,
            "lambda": (None if lam is None else ("inf" if math.isinf(lam) else lam)),
            "validation_cos_dist": {"chosen": round(val[best[0]], 4), "recent_mean": round(base_mean, 4),
                                    "previous_reply": round(base_prev, 4),
                                    "all": {k: round(v, 4) for k, v in val.items()}},
            "confidence": {"coherence_vs_error_spearman": rho, "qualified": conf_ok,
                           "rule": "Spearman <= %s on >= %d validation pairs" % (MAX_CONF_SPEARMAN, MIN_CONF_VALIDATION)},
            "first_target": P[0]["target_ts"], "last_target": P[-1]["target_ts"],
            "ctx_exchanges": CTX_EXCHANGES, "recent_replies": RECENT_REPLIES,
            "encoder": getattr(_jp(), "EMB_MODEL", "?"), "previous": receipt}
    tmp = "%s.tmp.%d" % (model_path, os.getpid())
    with open(tmp, "wb") as f:
        np.savez(f, W=m["W"].astype("float32"), mu_x=m["mu_x"].astype("float32"), mu_r=m["mu_r"].astype("float32"),
                 beta=np.asarray(beta, dtype="float32"),
                 coherence=np.sort(C).astype("float32"), meta=np.asarray(json.dumps(meta)))
    os.replace(tmp, model_path)
    log("trained on %d of his replies; chose %s (validation cos-dist %.4f; recent-mean %.4f; previous-reply %.4f); "
        "confidence %s" % (len(P), best[0], val[best[0]], base_mean, base_prev,
                           "qualified" if conf_ok else "placeholder (coherence does not predict error: %s)" % rho))
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
        return {"W": z["W"].astype("float64"), "mu_x": z["mu_x"].astype("float64"), "mu_r": z["mu_r"].astype("float64"),
                "beta": float(z["beta"]),
                "coherence": z["coherence"].astype("float64"), "meta": meta,
                "checkpoint_id": hashlib.sha256(raw).hexdigest(), "mtime": os.path.getmtime(path)}
    except Exception as e:
        log("self checkpoint unreadable: %s" % e)
        return None


def forecast(enc, rows=None, model_path=SELF_MODEL, today=None):
    """The live self forecast, built exactly as a training pair is (the cut = every exchange in the ledger,
    the target date = today). None when there is no checkpoint, so jepa_predictor keeps its old head."""
    import numpy as np
    m = load_model(model_path)
    if m is None:
        return None
    exs = exchanges(rows)
    if not any(x["his"] for x in exs):
        return None
    from datetime import date
    ctx = _context(exs, (today or date.today().isoformat()))
    X, M, Pv, C, _ = featurize([ctx], enc)
    A = anchor(M, Pv, m["beta"])
    if X.shape[1] != m["W"].shape[0]:
        log("self checkpoint does not fit this encoder (%d vs %d)" % (X.shape[1], m["W"].shape[0])); return None
    pred = _apply(m, X, A)[0]
    conf, qual = None, "unqualified_not_predictive"
    if (m["meta"].get("confidence") or {}).get("qualified"):
        conf = round(float(np.searchsorted(m["coherence"], C[0], side="right")) / max(1, len(m["coherence"])), 3)
        qual = "qualified"
    last = exs[-1]
    return {"emb": pred.astype("float32"), "confidence": conf, "qualification": qual,
            "coherence": round(float(C[0]), 4), "source": SOURCE, "schema": SCHEMA,
            "checkpoint_id": m["checkpoint_id"], "context_last_ts": last["ts"], "context_last_turn_id": last["turn_id"],
            "n_recent": len(ctx["recent"])}


# ---------------------------------------------------------------- the held-out evaluation
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


def _bootstrap(diffs, seed=20261016, n=2000):
    import random
    if not diffs:
        return None
    rng = random.Random(seed); means = []
    for _ in range(n):
        means.append(sum(diffs[rng.randrange(len(diffs))] for _ in diffs) / len(diffs))
    means.sort()
    return [round(means[int(.025 * n)], 4), round(means[int(.975 * n) - 1], 4)]


def _summary(rows):
    import numpy as np
    n = len(rows)
    if not n:
        return {"n": 0, "state": "INSUFFICIENT", "why": "no forecast with a realized reply after it yet"}
    h = np.asarray([r["head"] for r in rows]); p = np.asarray([r["previous_reply"] for r in rows])
    m = np.asarray([r["recent_mean"] for r in rows])
    out = {"n": n, "cos_dist": {"head": round(float(h.mean()), 4), "previous_reply": round(float(p.mean()), 4),
                                 "recent_mean": round(float(m.mean()), 4)},
           "head_wins": {"vs_previous_reply": round(float(np.mean(h < p)), 4), "vs_recent_mean": round(float(np.mean(h < m)), 4)}}
    strongest = "previous_reply" if p.mean() <= m.mean() else "recent_mean"
    ci = _bootstrap([float(a - b) for a, b in zip(h, p if strongest == "previous_reply" else m)])
    out.update({"strongest_baseline": strongest, "head_minus_strongest_ci95": ci})
    if n < MIN_EVAL:
        out.update(state="INSUFFICIENT", why="%d realized replies; %d needed for a verdict" % (n, MIN_EVAL))
    elif ci and ci[1] < 0:
        out.update(state="BEATS_BASELINES", why="lower cosine distance than both baselines; 95%% CI vs %s below 0" % strongest)
    else:
        out.update(state="NOT_BETTER_THAN_BASELINES", why="does not beat %s with a CI below 0" % strongest)
    return out


def evaluate(history, exs, enc, self_ck=None, self_trained_at=0.0, prod_ck=None, prod_trained_at=0.0):
    """Rows for the self head (forecasts on the current self checkpoint) and, for before/after, the old
    shared-trunk self forecasts on the current production checkpoint. A row's cut is what the forecast
    saw (the self head: the ledger up to its recorded context_last_ts; the old head: the ledger at the
    forecast time); the target is his first reply after that cut, said after the checkpoint was trained
    (so never a training pair); both baselines get exactly that cut. One row per target."""
    import numpy as np
    cache = _Cache(enc)
    out = {"self_head": [], "legacy_shared_trunk": []}
    seen = {"self_head": set(), "legacy_shared_trunk": set()}
    for f in sorted(history, key=lambda r: float(r.get("ts", 0) or 0)):
        s = f.get("self") or {}
        emb = s.get("emb")
        if not isinstance(emb, list) or not emb:
            continue
        fts = float(f.get("ts", 0) or 0)
        if s.get("source") == SOURCE:
            kind, trained_at = "self_head", self_trained_at
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
        cut = [x for x in exs if x["at"] <= cut_at]
        target = next((x for x in exs if x["at"] > cut_at and x["his"]), None)
        if target is None or target["at"] <= trained_at or not any(x["his"] for x in cut):
            continue
        key = (target["ts"], target["his"][:80])
        if key in seen[kind]:
            continue
        seen[kind].add(key)
        ctx = _context(cut, target["ts"][:10])
        cache.fill([target["his"][:400], ctx["previous"]] + list(ctx["recent"]))
        y = cache.get(target["his"][:400])
        rec = np.mean([cache.get(t) for t in ctx["recent"]], axis=0)
        d = lambda a: round(1.0 - float(_unit(a) @ y), 4)
        out[kind].append({"forecast_iso": f.get("iso"), "target_ts": target["ts"], "head": d(np.asarray(emb, dtype="float64")),
                          "previous_reply": d(cache.get(ctx["previous"])), "recent_mean": d(rec)})
    return out


def run_eval(out_path=SELF_EVAL, enc=None, history_path=HISTORY, rows=None):
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
                       prod_ck=prod_ck, prod_trained_at=prod_at or 0.0)
    from datetime import datetime
    report = {"at": datetime.now().isoformat(), "criteria": "prospective cosine distance to his next ledger reply vs his previous reply and the mean of his last %d" % RECENT_REPLIES,
              "protocol": "forecast after checkpoint; target said after checkpoint and after the forecast's own context; baselines given the same context; one row per target",
              "checkpoint": (m or {}).get("checkpoint_id"), "trained": (m or {}).get("meta"),
              "production_checkpoint": prod_ck,
              "self_head": _summary(rows_by["self_head"]),
              "legacy_shared_trunk": _summary(rows_by["legacy_shared_trunk"]),
              "rows": {k: v[-60:] for k, v in rows_by.items()},
              "truth_status": "instrument_only_no_steering"}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = "%s.tmp.%d" % (out_path, os.getpid())
    with open(tmp, "w") as f:
        json.dump(report, f, indent=2)
    os.replace(tmp, out_path)
    for k in ("self_head", "legacy_shared_trunk"):
        s = report[k]
        log("%s: n=%d %s %s" % (k, s["n"], s.get("state"), s.get("cos_dist", "")))
    return report


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "train": train()
    elif cmd == "train-force": train(force=True)
    elif cmd == "eval": run_eval()
    else: print("usage: jepa_self_head.py train|train-force|eval")

#!/usr/bin/env python3
"""latent_stream_linear.py — the continuous latent stream, second design (Chat's plan, 22 October): a strongly
regularised LINEAR recurrent state, trained to rank his next event among candidates, anchored on the baseline that
already works.

The first design (latent_stream_replay.py, a GRU regressing the next 768-d vector) lost on text: MRR 0.022 against
0.058 for "like the last text event". This one:

  experiment contract
    - each text event is a training target ONCE, from the state just before it (as it is scored); likewise each
      emotion reading. The old "every preceding step" emotion metric is kept beside it for comparison.
    - fixed day boundaries (validation from 9 October, test from 13 October); everything earlier is training.
    - a manifest of every event's split, source and whether its time is its own or placed after the one before it.
  state (no learned dynamics)
    - his text, projected onto a 32- or 64-d PCA fitted on training text only, held at three fixed timescales
      (about one hour, six hours, a day). An emotion reading never overwrites it; it only ages.
    - the last emotion reading, its trend against an hour-long average, the current source, how long since the
      last text, and the clock at prediction time (never the next event's time).
  text score of a candidate c
      beta * cos(last text, c) + gamma * cos(mean of last six, c) + (W h)ᵀ z_c
    starting at beta=1, gamma=0, W=0: exactly the "like the last one" baseline. W is fitted with a contrastive loss
    (the true next event against every training text, and against the same source's), strongly pulled to zero.
  emotion: a separately regularised linear readout of the change to the next reading.

  selection on VALIDATION only: the highest validation text MRR among designs that also beat emotion persistence.
  Then the chosen design runs on the test days ONCE. Also reported: a history ablation (no older state: last text,
  current emotion, source, clock only), per-source and per-day results, a paired day-block bootstrap of the gain,
  and whether the model's surprise says anything the last-text baseline's does not.

Reads his stores; writes only to --out. numpy only for the model; the text embedding uses the same frozen nomic
encoder as his JEPA heads (run with the torch venv):

    nice -n 15 ~/.vintos/workspace/emotion_model/.venv/bin/python3 latent_stream_linear.py
"""
import argparse, json, math, os, sys, tempfile, time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import latent_stream_replay as R

SOURCES = R.SOURCES
EMO = R.EMO_DIM
TAUS_MIN = (60.0, 360.0, 1440.0)
VAL_FROM = "2026-10-09"
TEST_FROM = "2026-10-13"


# ------------------------------------------------------------------ data
def split_of(e, val_from, test_from):
    d = e["t"].astimezone().date().isoformat()
    return "test" if d >= test_from else "val" if d >= val_from else "train"


def manifest(events, val_from, test_from, out):
    rows, cov = [], defaultdict(Counter)
    for i, e in enumerate(events):
        sp = split_of(e, val_from, test_from)
        rows.append({"i": i, "t": e["t"].isoformat(), "source": e["source"], "split": sp,
                     "time": "own" if e.get("t_exact", True) else "placed after the one before",
                     "text": bool(e.get("vec")), "emotion": bool(e.get("emo"))})
        cov[e["source"]][sp] += 1
    with open(os.path.join(out, "manifest.jsonl"), "w") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
    unseen = [s for s in SOURCES if cov[s]["test"] and not (cov[s]["train"] and cov[s]["val"])]
    return {s: dict(cov[s]) for s in SOURCES}, unseen


def arrays(events):
    T = len(events)
    dim = next(len(e["vec"]) for e in events if e.get("vec"))
    X = np.zeros((T, dim), np.float32)
    E = np.zeros((T, EMO), np.float32)
    is_t = np.zeros(T, bool); is_e = np.zeros(T, bool)
    for i, e in enumerate(events):
        if e.get("vec"): X[i] = e["vec"]; is_t[i] = True
        if e.get("emo"): E[i] = e["emo"]; is_e[i] = True
    return X, E, is_t, is_e


# ------------------------------------------------------------------ the state
def states(events, X, E, is_t, is_e, P, mu, emo_mu, emo_sd, clock="hour", history=True):
    """h after each event (row i = the state once event i has arrived), plus the baseline vectors at each step."""
    T, dz = len(events), P.shape[1]
    m = np.zeros((len(TAUS_MIN), dz)); m_at = [None] * len(TAUS_MIN)
    last_vec = np.zeros(X.shape[1], np.float32); six = []
    z_last = np.zeros(dz)
    last_e = emo_mu.copy(); ema = emo_mu.copy(); ema_at = None; last_text_at = None
    H, LAST, MEAN6 = [], np.zeros_like(X), np.zeros_like(X)
    for i, e in enumerate(events):
        t = e["t"]
        if is_t[i]:
            z = (X[i] - mu) @ P
            for k, tau in enumerate(TAUS_MIN):
                a = 0.0 if m_at[k] is None else math.exp(-max(0.0, (t - m_at[k]).total_seconds() / 60.0) / tau)
                m[k] = a * m[k] + (1 - a) * z; m_at[k] = t
            z_last = z; last_vec = X[i]; six = (six + [X[i]])[-6:]; last_text_at = t
        if is_e[i]:
            a = 0.0 if ema_at is None else math.exp(-max(0.0, (t - ema_at).total_seconds() / 60.0) / 60.0)
            ema = a * ema + (1 - a) * E[i]; ema_at = t; last_e = E[i]
        LAST[i] = last_vec
        if six:
            v = np.mean(six, 0); MEAN6[i] = v / (np.linalg.norm(v) or 1.0)
        age = 0.0 if last_text_at is None else math.log1p(max(0.0, (t - last_text_at).total_seconds() / 60.0))
        loc = t.astimezone()
        hr = (loc.hour + loc.minute / 60.0) / 24.0 * 2 * math.pi
        clk = []
        if clock in ("hour", "week"): clk += [math.sin(hr), math.cos(hr)]
        if clock == "week": clk += [math.sin(loc.weekday() / 7 * 2 * math.pi), math.cos(loc.weekday() / 7 * 2 * math.pi)]
        en = (last_e - emo_mu) / emo_sd
        src = [1.0 if e["source"] == s else 0.0 for s in SOURCES]
        if history:   # everything the present-moment model has, PLUS the held history (22 October: without z_last
            # here, "with history" was a blurrier picture, not the moment and more; it lost to the moment alone)
            h = np.concatenate([z_last, en, src, [age], clk, [1.0], m.ravel(), (last_e - ema) / emo_sd])
        else:   # the ablation: no older state, only what the last moment gives
            h = np.concatenate([z_last, en, src, [age], clk, [1.0]])
        H.append(h)
    return np.asarray(H, np.float32), LAST, MEAN6


def pca(Xtrain, dz):
    mu = Xtrain.mean(0)
    _, _, vt = np.linalg.svd(Xtrain - mu, full_matrices=False)
    return mu.astype(np.float32), vt[:dz].T.astype(np.float32)


# ------------------------------------------------------------------ text: contrastive, baseline-anchored
def text_ids(X):
    """The same text, the same id: identical vectors are one text."""
    seen, out = {}, np.zeros(len(X), np.int64)
    for i in range(len(X)):
        out[i] = seen.setdefault(X[i].tobytes(), len(seen))
    return out


def fit_text(H, LAST, MEAN6, X, Z, targets, cands, src_of, lam, steps=300, lr=0.05, seed=0, tid=None):
    """W, beta, gamma, log-scale. Loss: -log P(true | all training texts) + 0.5 * -log P(true | same source),
    identical texts counted as the same positive; + lam * |W|^2. Starts at the baseline (W=0, beta=1, gamma=0)."""
    rng = np.random.default_rng(seed)
    hs = H[[j - 1 for j in targets]]
    A = LAST[[j - 1 for j in targets]] @ X[cands].T
    B = MEAN6[[j - 1 for j in targets]] @ X[cands].T
    Zc = Z[cands]
    tid = text_ids(X) if tid is None else tid
    pos = tid[targets][:, None] == tid[cands][None, :]
    sa = np.array(src_of, dtype=object)
    same = sa[targets][:, None] == sa[cands][None, :]
    W = np.zeros((Z.shape[1], H.shape[1]), np.float32); beta, gamma, ls = 1.0, 0.0, math.log(20.0)
    params = [W, np.array(beta), np.array(gamma), np.array(ls)]
    mom = [np.zeros_like(p, dtype=np.float64) for p in params]; vel = [np.zeros_like(p, dtype=np.float64) for p in params]
    n = len(targets)
    for it in range(1, steps + 1):
        W, beta, gamma, ls = params[0], float(params[1]), float(params[2]), float(params[3])
        S = beta * A + gamma * B + (hs @ W.T) @ Zc.T
        sc = math.exp(ls)
        G = np.zeros_like(S); loss = 0.0
        for mask, wgt in ((None, 1.0), (same, 0.5)):
            L = sc * S if mask is None else np.where(mask, sc * S, -np.inf)
            L = L - L.max(1, keepdims=True)
            p = np.exp(L); p /= p.sum(1, keepdims=True)
            pp = np.where(pos, p, 0.0); ptrue = pp.sum(1, keepdims=True) + 1e-12
            loss += wgt * float(-np.log(ptrue).mean())
            G += wgt * (p - pp / ptrue) / n            # d loss / d (sc*S)
        gS = G * sc
        gW = (gS @ Zc).T @ hs + 2 * lam * W
        grads = [gW, np.array((gS * A).sum()), np.array((gS * B).sum()), np.array((G * S).sum() * sc)]
        for k, g in enumerate(grads):   # Adam
            mom[k] = 0.9 * mom[k] + 0.1 * g; vel[k] = 0.999 * vel[k] + 0.001 * g * g
            params[k] = params[k] - lr * (mom[k] / (1 - 0.9 ** it)) / (np.sqrt(vel[k] / (1 - 0.999 ** it)) + 1e-8)
    return {"W": params[0], "beta": float(params[1]), "gamma": float(params[2]), "scale": math.exp(float(params[3]))}


def rank_eval(score_rows, X, targets, cands):
    """MRR and top-10 among the candidates, ties against the guess (the protocol of the first design), and a
    duplicate-aware diagnostic that ignores candidates with the target's exact text."""
    pos = {c: k for k, c in enumerate(cands)}
    rr, top, rr_dup = [], 0, []
    for S, j in zip(score_rows, targets):
        s_true = S[pos[j]]
        r = int((S >= s_true).sum()); rr.append(1.0 / r); top += r <= 10
        dup = np.array([X[c].tobytes() == X[j].tobytes() for c in cands])
        rr_dup.append(1.0 / (int(((S >= s_true) & ~dup).sum()) + 1))
    n = max(1, len(rr))
    return {"mrr": float(np.mean(rr)) if rr else 0.0, "top10": top / n, "mrr_dup_aware": float(np.mean(rr_dup)) if rr_dup else 0.0}, rr


def text_scores(fit, H, LAST, MEAN6, X, Z, targets, cands):
    hs = H[[j - 1 for j in targets]]
    return (fit["beta"] * (LAST[[j - 1 for j in targets]] @ X[cands].T) + fit["gamma"] * (MEAN6[[j - 1 for j in targets]] @ X[cands].T)
            + (hs @ fit["W"].T) @ Z[cands].T)


# ------------------------------------------------------------------ emotion: ridge on the change
def emo_targets(is_e, idx_range):
    return [i for i in idx_range if is_e[i] and i > 0]


def last_emotion(E, is_e):
    out = np.zeros_like(E); last = None
    for i in range(len(E)):
        if is_e[i]: last = E[i]
        if last is not None: out[i] = last
    return out


def fit_emotion(H, LASTE, E, targets, lam, emo_sd):
    Hs = H[[i - 1 for i in targets]]
    D = (E[targets] - LASTE[[i - 1 for i in targets]]) / emo_sd
    A = Hs.T @ Hs + lam * np.eye(Hs.shape[1])
    return np.linalg.solve(A, Hs.T @ D)


def emo_eval(Bm, H, LASTE, E, targets, emo_sd, legacy_steps=None, nxt=None):
    """Error in units of the training spread of readings, as in the first design. Once per reading from the state just
    before it; and the legacy metric (every step before a reading) when asked."""
    def mse(pred, true): return float((((pred - true) / emo_sd) ** 2).mean())
    pre = [i - 1 for i in targets]
    model = LASTE[pre] + (H[pre] @ Bm) * emo_sd
    out = {"model": mse(model, E[targets]), "persistence": mse(LASTE[pre], E[targets])}
    if legacy_steps:
        tt = [nxt[i] for i in legacy_steps]
        out["legacy_model"] = mse(LASTE[legacy_steps] + (H[legacy_steps] @ Bm) * emo_sd, E[tt])
        out["legacy_persistence"] = mse(LASTE[legacy_steps], E[tt])
    return out


# ------------------------------------------------------------------ the whole experiment
def design(events, X, E, is_t, is_e, sp, dz, clock, history, emo_mu, emo_sd):
    tr_text = [i for i in range(1, len(events)) if is_t[i] and sp[i] == "train"]
    mu, P = pca(X[tr_text], dz)
    Z = ((X - mu) @ P).astype(np.float32)
    H, LAST, MEAN6 = states(events, X, E, is_t, is_e, P, mu, emo_mu, emo_sd, clock=clock, history=history)
    return Z, H, LAST, MEAN6


def run(events, out, val_from=VAL_FROM, test_from=TEST_FROM, grid=None, steps=200, log=print):
    os.makedirs(out, exist_ok=True)
    coverage, unseen = manifest(events, val_from, test_from, out)
    X, E, is_t, is_e = arrays(events)
    sp = [split_of(e, val_from, test_from) for e in events]
    src = [e["source"] for e in events]
    T = len(events)
    emo_tr = E[[i for i in range(T) if is_e[i] and sp[i] == "train"]]
    emo_mu, emo_sd = emo_tr.mean(0), np.maximum(emo_tr.std(0), 1e-3)
    LASTE = last_emotion(E, is_e)
    TID = text_ids(X)
    tsets = {s: [i for i in range(1, T) if is_t[i] and sp[i] == s] for s in ("train", "val", "test")}
    esets = {s: [i for i in range(1, T) if is_e[i] and sp[i] == s and LASTE[i - 1].any()] for s in ("train", "val", "test")}
    grid = grid or [(dz, clock, lam) for dz in (32, 64) for clock in ("none", "hour", "week") for lam in (1.0, 0.1, 0.01, 0.001)]
    results, cache = [], {}
    for history in (True, False):
        for dz, clock, lam in grid:
            key = (dz, clock, history)
            if key not in cache:
                cache[key] = design(events, X, E, is_t, is_e, sp, dz, clock, history, emo_mu, emo_sd)
            Z, H, LAST, MEAN6 = cache[key]
            fit = fit_text(H, LAST, MEAN6, X, Z, tsets["train"], tsets["train"], src, lam, steps=steps, tid=TID)
            v, _ = rank_eval(text_scores(fit, H, LAST, MEAN6, X, Z, tsets["val"], tsets["val"]), X, tsets["val"], tsets["val"])
            best_e = None
            for le in (100.0, 10.0, 1.0, 0.1):
                Bm = fit_emotion(H, LASTE, E, esets["train"], le, emo_sd)
                ev = emo_eval(Bm, H, LASTE, E, esets["val"], emo_sd)
                if best_e is None or ev["model"] < best_e[1]["model"]: best_e = (le, ev, Bm)
            row = {"history": history, "dz": dz, "clock": clock, "lam": lam, "val_text": v, "emotion_lam": best_e[0],
                   "val_emotion": best_e[1], "beta": round(fit["beta"], 3), "gamma": round(fit["gamma"], 3)}
            results.append((row, fit, best_e[2]))
            log("%-7s dz=%-3d clock=%-5s lam=%-6g  val MRR %.4f top10 %.3f | emotion %.4f vs %.4f" % (
                "full" if history else "ablate", dz, clock, lam, v["mrr"], v["top10"], best_e[1]["model"], best_e[1]["persistence"]))
    # the baselines on the validation days, same events
    Z0, H0, LAST0, MEAN60 = cache[(grid[0][0], grid[0][1], True)]
    base = lambda b, g: rank_eval(b * (LAST0[[j - 1 for j in tsets["val"]]] @ X[tsets["val"]].T)
                                  + g * (MEAN60[[j - 1 for j in tsets["val"]]] @ X[tsets["val"]].T), X, tsets["val"], tsets["val"])[0]
    val_base = {"last_one": base(1, 0), "mean_last_six": base(0, 1)}
    def choose(history):
        ok = [r for r in results if r[0]["history"] == history and r[0]["val_emotion"]["model"] < r[0]["val_emotion"]["persistence"]]
        return max(ok, key=lambda r: r[0]["val_text"]["mrr"]) if ok else None
    chosen, ablation = choose(True), choose(False)
    report = {"coverage": coverage, "unseen_in_train_or_val": unseen, "val_baselines": val_base,
              "grid": [r[0] for r in results],
              "note": "informed follow-up: the test days were seen in the first design's three runs"}
    if not chosen:
        report["verdict"] = "no design beat emotion persistence on the validation days: it fails validation"
        json.dump(report, open(os.path.join(out, "linear-result.json"), "w"), indent=2, default=float)
        return report
    report["validation_qualifies"] = chosen[0]["val_text"]["mrr"] > max(val_base["last_one"]["mrr"], val_base["mean_last_six"]["mrr"])

    # ---- the test days, once, for the frozen choice (and the predeclared ablation)
    def on_test(choice):
        row, fit, Bm = choice
        Z, H, LAST, MEAN6 = cache[(row["dz"], row["clock"], row["history"])]
        tt = tsets["test"]
        S = text_scores(fit, H, LAST, MEAN6, X, Z, tt, tt)
        m, rr = rank_eval(S, X, tt, tt)
        b1, rr1 = rank_eval(LAST[[j - 1 for j in tt]] @ X[tt].T, X, tt, tt)
        b6, _ = rank_eval(MEAN6[[j - 1 for j in tt]] @ X[tt].T, X, tt, tt)
        nxt = [-1] * T; ne = -1
        for i in range(T - 1, -1, -1):
            nxt[i] = ne
            if is_e[i]: ne = i
        legacy = [i for i in range(T) if sp[i] == "test" and nxt[i] >= 0 and LASTE[i].any()]
        em = emo_eval(Bm, H, LASTE, E, esets["test"], emo_sd, legacy, nxt)
        per_source = {}
        for s in SOURCES:
            k = [n for n, j in enumerate(tt) if src[j] == s]
            if k: per_source[s] = {"n": len(k), "model_mrr": round(float(np.mean([rr[n] for n in k])), 4),
                                   "last_one_mrr": round(float(np.mean([rr1[n] for n in k])), 4)}
        days = sorted({events[j]["t"].astimezone().date() for j in tt})
        by_day = {d: [n for n, j in enumerate(tt) if events[j]["t"].astimezone().date() == d] for d in days}
        rng = np.random.default_rng(11); diffs = []
        for _ in range(2000):
            pick = [n for d in rng.choice(days, len(days)) for n in by_day[d]]
            diffs.append(np.mean([rr[n] - rr1[n] for n in pick]))
        # surprise: does the model's say anything the last-text baseline's does not? rank correlation, within source
        p_model = [-math.log(max(1e-12, float(np.exp(S[n] * fit["scale"] - np.logaddexp.reduce(S[n] * fit["scale"]))[tt.index(j)])))
                   for n, j in enumerate(tt)]
        p_base = [1 - float(LAST[j - 1] @ X[j]) for j in tt]
        def spear(a, b):
            if len(a) < 3: return None
            ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
            return round(float(np.corrcoef(ra, rb)[0, 1]), 3)
        sur = {s: spear([p_model[n] for n, j in enumerate(tt) if src[j] == s], [p_base[n] for n, j in enumerate(tt) if src[j] == s])
               for s in SOURCES}
        top = sorted(range(len(tt)), key=lambda n: -p_model[n])[:6]
        return {"design": {k: row[k] for k in ("history", "dz", "clock", "lam", "emotion_lam", "beta", "gamma")},
                "text": {"model": m, "last_one": b1, "mean_last_six": b6}, "emotion": em, "per_source": per_source,
                "gain_over_last_one_mrr_95ci": [round(float(np.percentile(diffs, 2.5)), 4), round(float(np.percentile(diffs, 97.5)), 4)],
                "surprise_vs_last_text_rank_corr_by_source": sur,
                "most_surprising": [{"at": str(events[tt[n]]["t"].astimezone())[:16], "source": src[tt[n]],
                                     "text": events[tt[n]]["text"][:160]} for n in top]}
    report["test"] = on_test(chosen)
    report["test_history_ablation"] = on_test(ablation) if ablation else None
    t, e = report["test"]["text"], report["test"]["emotion"]
    wins = {"text_mrr": t["model"]["mrr"] > max(t["last_one"]["mrr"], t["mean_last_six"]["mrr"]),
            "text_top10": t["model"]["top10"] > max(t["last_one"]["top10"], t["mean_last_six"]["top10"]),
            "emotion_once": e["model"] < e["persistence"], "emotion_legacy": e["legacy_model"] < e["legacy_persistence"],
            "beats_history_ablation": bool(report["test_history_ablation"]) and
                t["model"]["mrr"] > report["test_history_ablation"]["text"]["model"]["mrr"]}
    report["acceptance"] = wins
    report["verdict"] = ("goes on to a shadow week" if all(wins.values()) else
                         "does not pass: " + ", ".join(k for k, v in wins.items() if not v))
    json.dump(report, open(os.path.join(out, "linear-result.json"), "w"), indent=2, default=float)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--days", type=int, default=365, help="history to use; everything before validation trains")
    ap.add_argument("--val-from", default=VAL_FROM); ap.add_argument("--test-from", default=TEST_FROM)
    a = ap.parse_args()
    out = a.out or tempfile.mkdtemp(prefix="latent-stream-linear-")
    t0 = time.time()
    ev = R.build_stream()
    ev = [e for e in ev if e["t"] >= datetime.now(timezone.utc) - timedelta(days=a.days)]
    sys.path.insert(0, os.path.join(R.WS, "scripts"))
    from jepa_predictor import encoder
    enc = encoder()
    ev = R.embed_texts(ev, lambda texts: enc.encode(texts, batch_size=32), os.path.join(out, "text-vectors.jsonl"))
    print("stream: %d events, %s; embedded in %.0f s" % (len(ev), dict(Counter(e["source"] for e in ev)), time.time() - t0))
    rep = run(ev, out, a.val_from, a.test_from)
    print("\ncoverage by split:", json.dumps(rep["coverage"]))
    if rep.get("unseen_in_train_or_val"):
        print("NOT SEEN in training or validation (a shared fallback covers them):", rep["unseen_in_train_or_val"])
    print("validation baselines:", json.dumps(rep["val_baselines"]))
    for k in ("test", "test_history_ablation"):
        if rep.get(k):
            print("\n== %s ==" % k); print(json.dumps({x: y for x, y in rep[k].items() if x != "most_surprising"}, indent=1))
    if rep.get("test"):
        print("\nmost surprising to the model on the test days:")
        for r in rep["test"]["most_surprising"]:
            print("  %s  %-8s %s" % (r["at"], r["source"], " ".join(r["text"].split())[:140]))
        print("\nacceptance:", json.dumps(rep["acceptance"]))
    print("\nVERDICT:", rep["verdict"])
    print("written only to", out, "(%.0f s)" % (time.time() - t0))


if __name__ == "__main__":
    main()

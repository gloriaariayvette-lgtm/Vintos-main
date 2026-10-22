#!/usr/bin/env python3
"""latent_stream_replay.py — step 1 of the continuous latent stream (docs/continuous-latent-stream.md): replay his
history through a small recurrent state and see whether it predicts him better than what he already has.

Reads his stores; writes only to --out (default a new scratch directory). Nothing of his is changed, nothing is sent,
no model is called over the network. Run with the torch venv, CPU:

    nice -n 15 ~/.vintos/workspace/emotion_model/.venv/bin/python3 ~/Vintos-main/scripts/latent_stream_replay.py

The stream (from the step 0 probe, 22 October: about 175 events a day):
  emotion   the dense 11-d emotion vector, every 10 minutes          (emotion-trajectory-dense.json)
  inner     his inner-life sections                                   (daily-inner-life-*.md)
  thread    unfinished threads as they formed                         (unfinished-threads.json)
  creative  what he made                                              (daily-creative-*.md)
  her/him   chat turns and ledger exchanges                           (chat-canonical.jsonl, interaction-ledger.json)
The Lab's machine steps are left out (3,000 a day would drown him). Text is embedded with the same frozen nomic encoder
his JEPA heads use; his media (EmbeddingGemma 2, another space) joins later through its own projection.

The model: each event -> [text projection, last emotion, source, log time since the last event] -> GRU hidden state
(the "hsv") -> heads for the next text event's embedding and the next emotion reading. Surprise = how far the next
text event fell from what the state expected.

The test (days it never trained on: the last 20%):
  text     rank of the true next text event among every text event of the test days (MRR, top-10), against
           "the next is like the last" and "the next is like the mean of the last six" (the JEPA window)
  emotion  error of the next emotion reading, against "the next is the last"
  surprise the test events it found most surprising, in his words, so a person can judge whether surprise means anything
Verdict: it goes on to a shadow week only if it beats every baseline on the test days.
"""
import argparse, glob, json, math, os, random, re, tempfile, time
from datetime import datetime, timedelta, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
SOURCES = ["emotion", "inner", "thread", "creative", "her", "him"]
EMO_DIM = 11
EMO_AXES = ["Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection", "Playfulness", "Curiosity", "Warmth",
            "Tension", "Groundedness"]
TS_KEYS = ("timestamp", "ts", "t", "at", "time", "created_at")


def _when(v):
    if isinstance(v, (int, float)):
        try: return datetime.fromtimestamp(v / 1000 if v > 1e12 else v, timezone.utc)
        except (OverflowError, OSError, ValueError): return None
    if isinstance(v, str) and re.match(r"\d{4}-\d\d-\d\d", v):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00")[:32])
            return d if d.tzinfo else d.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _stamp(row):
    return next((d for d in (_when(row.get(k)) for k in TS_KEYS) if d), None) if isinstance(row, dict) else None


def _json(path, default):
    try: return json.load(open(path))
    except (OSError, ValueError): return default


def _sections(pattern, source):
    """Markdown day files -> one event per '## ' section. A heading's own time is used; a section without one takes
    the time of the section before it, one minute later (the file keeps them in the order they happened)."""
    out = []
    for path in sorted(glob.glob(os.path.join(MEM, pattern))):
        m = re.search(r"(\d{4}-\d\d-\d\d)", os.path.basename(path))
        if not m: continue
        day = datetime.fromisoformat(m.group(1)).astimezone(timezone.utc)
        last = day.replace(hour=0, minute=0)
        for sec in open(path, errors="ignore").read().split("\n## ")[1:]:
            head, _, body = sec.partition("\n")
            t = re.search(r"\b(\d{1,2}):(\d\d)\b", head)
            when = (datetime.fromisoformat(m.group(1)).replace(hour=int(t.group(1)) % 24, minute=int(t.group(2)))
                    .astimezone(timezone.utc)) if t else last + timedelta(minutes=1)
            last = max(last, when)
            text = (head + "\n" + body).strip()
            if len(text) > 40:   # t_exact: the heading carried its own time; otherwise placed after the one before it
                out.append({"t": when, "source": source, "text": text[:1500], "t_exact": bool(t)})
    return out


def build_stream(mem=None):
    """All events, oldest first: {t, source, text?, emo?}."""
    global MEM
    MEM = mem or MEM
    ev = []
    for r in (_json(os.path.join(MEM, "emotion-trajectory-dense.json"), []) or []):
        t, v = _stamp(r), r.get("v") if isinstance(r, dict) else None
        if t and isinstance(v, list) and len(v) >= EMO_DIM:
            ev.append({"t": t, "source": "emotion", "emo": [float(x) for x in v[:EMO_DIM]]})
        elif t and isinstance(v, dict):   # by axis name, never by the order the dict happens to hold
            low = {str(k).lower(): x for k, x in v.items()}
            if all(d.lower() in low for d in EMO_AXES):
                ev.append({"t": t, "source": "emotion", "emo": [float(low[d.lower()]) for d in EMO_AXES]})
    ev += _sections("daily-inner-life-*.md", "inner")
    ev += _sections("daily-creative-*.md", "creative")
    for r in _json(os.path.join(MEM, "unfinished-threads.json"), []) or []:
        t = _stamp(r)
        if t and r.get("thread"): ev.append({"t": t, "source": "thread", "text": str(r["thread"])[:1500]})
    seen = {}
    def turn(t, role, text):
        """One turn kept in two stores (chat log and ledger) is one event: same side, same whole text, within 15
        minutes. The same words said again on another day are a new event."""
        side = "her" if role in ("user", "gloria") else "him"
        # the chat log carries the house's stage directions inside turns ("[she spoke with her body, not words]",
        # "[speak TO her ...]"): they are not anyone's words. Brackets out; a turn with nothing else left is dropped.
        text = re.sub(r"\[[^\]]*\]?", " ", str(text or ""))
        text = " ".join(text.split())
        if len(text.split()) < 1 or not re.search(r"\w", text): return
        key = (side, text)
        if not (t and text): return
        if key in seen and abs((t - seen[key]).total_seconds()) < 900: return
        seen[key] = t; ev.append({"t": t, "source": side, "text": str(text)[:1500]})
    try:
        for line in open(os.path.join(MEM, "chat-canonical.jsonl"), errors="ignore"):
            try: r = json.loads(line)
            except ValueError: continue
            turn(_stamp(r), r.get("role"), r.get("content"))
    except OSError:
        pass
    for r in _json(os.path.join(MEM, "interaction-ledger.json"), []) or []:
        t = _stamp(r)
        if isinstance(r, dict):
            if isinstance(r.get("gloria"), str): turn(t, "gloria", r["gloria"])
            for k in ("vintos", "reply", "response"):
                if isinstance(r.get(k), str): turn(t, "vintos", r[k]); break
    ev.sort(key=lambda e: e["t"])
    return ev


def embed_texts(events, encode, cache_path):
    """Each text event's nomic vector, cached by text so a second run embeds nothing again."""
    cache = {}
    if os.path.exists(cache_path):
        for line in open(cache_path):
            try: r = json.loads(line); cache[r["k"]] = r["v"]
            except (ValueError, KeyError): pass
    todo = sorted({e["text"] for e in events if e.get("text") and e["text"] not in cache})
    with open(cache_path, "a") as f:
        for i in range(0, len(todo), 32):
            batch = todo[i:i + 32]
            for text, vec in zip(batch, encode(batch)):
                v = [float(x) for x in vec]; n = math.sqrt(sum(x * x for x in v)) or 1.0
                cache[text] = [x / n for x in v]
                f.write(json.dumps({"k": text, "v": cache[text]}) + "\n")
    for e in events:
        if e.get("text"): e["vec"] = cache[e["text"]]
    return events


def featurize(events):
    """Per step: [vec(768 or 0), emotion carried forward(11), source one-hot(6), log1p(minutes since last)]."""
    dim = next((len(e["vec"]) for e in events if e.get("vec")), 768)
    emo, last_t, rows = [0.0] * EMO_DIM, None, []
    for e in events:
        if e.get("emo"): emo = e["emo"]
        gap = 0.0 if last_t is None else max(0.0, (e["t"] - last_t).total_seconds() / 60.0)
        last_t = e["t"]
        rows.append((e.get("vec") or [0.0] * dim) + list(emo) +
                    [1.0 if e["source"] == s else 0.0 for s in SOURCES] + [math.log1p(gap)])
    return rows, dim


def split_days(events, test_frac=0.2, val_frac=0.1):
    days = sorted({e["t"].date() for e in events})
    n = len(days)
    test_from = days[max(1, int(n * (1 - test_frac)))] if n > 2 else None
    val_from = days[max(1, int(n * (1 - test_frac - val_frac)))] if n > 3 else test_from
    idx = lambda d: next((i for i, e in enumerate(events) if e["t"].date() >= d), len(events)) if d else len(events)
    return idx(val_from), idx(test_from)


def run(events, out_dir, epochs=12, hidden=128, seed=7, log=print):
    import torch, torch.nn as nn
    torch.manual_seed(seed); random.seed(seed)
    torch.set_num_threads(max(1, min(8, (os.cpu_count() or 2) // 2)))
    X, dim = featurize(events)
    X = torch.tensor(X, dtype=torch.float32)
    T = len(events)
    is_text = torch.tensor([bool(e.get("vec")) for e in events])
    is_emo = torch.tensor([bool(e.get("emo")) for e in events])
    val_at, test_at = split_days(events)
    # next text event / next emotion reading, for every step
    nxt_text, nxt_emo, nt, ne = [-1] * T, [-1] * T, -1, -1
    for i in range(T - 1, -1, -1):
        nxt_text[i], nxt_emo[i] = nt, ne
        if is_text[i]: nt = i
        if is_emo[i]: ne = i
    emo_mean = X[:val_at, dim:dim + EMO_DIM][is_emo[:val_at]].mean(0) if is_emo[:val_at].any() else torch.zeros(EMO_DIM)
    emo_std = X[:val_at, dim:dim + EMO_DIM][is_emo[:val_at]].std(0).clamp_min(1e-3) if is_emo[:val_at].sum() > 1 else torch.ones(EMO_DIM)
    # the change from one reading to the next has its own scale; a dimension that barely moves must not be divided by
    # ~0 (22 October, second run: train loss 30, the emotion term drowned the text head)
    _pairs = [(i, nxt_emo[i]) for i in range(val_at) if is_emo[i] and 0 <= nxt_emo[i] < val_at]
    emo_dstd = ((X[[b for _, b in _pairs], dim:dim + EMO_DIM] - X[[a for a, _ in _pairs], dim:dim + EMO_DIM]).std(0)
                .clamp_min(0.05) if len(_pairs) > 1 else torch.ones(EMO_DIM))
    # the last text event so far, at every step: the text head predicts the next one as a change from it
    last_vec = torch.zeros(T, dim); _lv = torch.zeros(dim)
    for i in range(T):
        if is_text[i]: _lv = X[i, :dim]
        last_vec[i] = _lv

    class Stream(nn.Module):
        def __init__(self):
            super().__init__()
            self.text_in = nn.Linear(dim, 64)
            self.rest_in = nn.Linear(EMO_DIM + len(SOURCES) + 1, 32)
            self.gru = nn.GRU(96, hidden, batch_first=True)
            self.text_out = nn.Linear(hidden, dim)
            self.emo_out = nn.Linear(hidden, EMO_DIM)
            self.drop = nn.Dropout(0.2)
            for head in (self.text_out, self.emo_out):   # start predicting "no change": the model begins AT the baseline
                nn.init.zeros_(head.weight); nn.init.zeros_(head.bias)
        def forward(self, x, h=None):
            e = (x[..., dim:dim + EMO_DIM] - emo_mean) / emo_std
            z = torch.cat([self.text_in(x[..., :dim]), self.rest_in(torch.cat([e, x[..., dim + EMO_DIM:]], -1))], -1)
            s, h = self.gru(self.drop(torch.tanh(z)), h)
            return self.text_out(s), self.emo_out(s), h, s

    model = Stream()
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-2)
    chunk = 256
    def losses(lo, hi, train, score_from=0):
        """The state runs from lo; the loss counts only steps from score_from (validation scores validation days)."""
        total, n = 0.0, 0
        h = None
        for a in range(lo, hi, chunk):
            b = min(hi, a + chunk)
            pt, pe, h, _ = model(X[a:b].unsqueeze(0), h)
            h = h.detach()
            idx = torch.arange(a, b)
            tt = torch.tensor([nxt_text[i] for i in range(a, b)])
            te = torch.tensor([nxt_emo[i] for i in range(a, b)])
            mt, me = (tt >= 0) & (tt < hi) & (idx >= score_from), (te >= 0) & (te < hi) & (idx >= score_from)
            loss = torch.zeros(())
            if mt.any():   # like emotion: a change from the last text event, so predicting none is the baseline
                pred = nn.functional.normalize(last_vec[idx[mt]] + pt[0][mt], dim=-1)
                loss = loss + (1 - (pred * X[tt[mt], :dim]).sum(-1)).mean()
            if me.any():   # the head predicts the CHANGE from the last reading: predicting none is the baseline
                target = (X[te[me], dim:dim + EMO_DIM] - X[idx[me], dim:dim + EMO_DIM]) / emo_dstd
                loss = loss + 0.5 * ((pe[0][me] - target) ** 2).mean()
            if train and loss.requires_grad:
                opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step()
            if mt.any() or me.any():
                total += float(loss.detach()); n += 1
        return total / max(1, n)

    best, best_state = float("inf"), None
    for ep in range(epochs):
        model.train(); tr = losses(0, val_at, True)
        model.eval()
        with torch.no_grad(): va = losses(0, test_at, False, score_from=val_at)   # state through train, scored on val
        log("epoch %d: train %.4f, through validation %.4f" % (ep + 1, tr, va))
        if va < best: best, best_state = va, {k: v.clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        pt, pe, _, states = model(X.unsqueeze(0))
    pt, pe = nn.functional.normalize(last_vec + pt[0], dim=-1), pe[0]

    # ---- the test days ----
    test_text = [i for i in range(test_at, T) if is_text[i]]
    cand = X[test_text, :dim] if test_text else torch.zeros(0, dim)
    pos = {j: n for n, j in enumerate(test_text)}
    def rank_scores(pred_rows, truth_rows):
        """Rank of the true next event; ties count against the guess, so an empty guess ranks last, not first."""
        rr, top10 = [], 0
        for p, t in zip(pred_rows, truth_rows):
            sims = cand @ p
            r = int((sims >= sims[pos[t]]).sum())
            rr.append(1.0 / r); top10 += r <= 10
        return (sum(rr) / len(rr), top10 / len(rr)) if rr else (0.0, 0.0)
    steps = [j - 1 for j in test_text if j - 1 >= test_at]   # each text event once, from the state just before it
    stepset = set(steps)
    truths = [nxt_text[i] for i in steps]
    model_pred = [pt[i] for i in steps]
    last_text, window, last_pred, win_pred = None, [], [], []
    for i in range(0, T):
        if is_text[i]:
            last_text = X[i, :dim]; window = (window + [X[i, :dim]])[-6:]
        if i in stepset:
            z = torch.zeros(dim)
            last_pred.append(last_text if last_text is not None else z)
            win_pred.append(nn.functional.normalize(torch.stack(window).mean(0), dim=-1) if window else z)
    res = {"events": T, "text_events": int(is_text.sum()), "emotion_events": int(is_emo.sum()),
           "validation_from": str(events[val_at]["t"].date()) if val_at < T else None,
           "test_from": str(events[test_at]["t"].date()) if test_at < T else None, "test_text_events": len(test_text)}
    res["text"] = {name: dict(zip(("mrr", "top10"), [round(x, 4) for x in rank_scores(p, truths)]))
                   for name, p in (("stream", model_pred), ("last_one", last_pred), ("mean_last_six", win_pred))}
    em_steps = [i for i in range(test_at, T) if nxt_emo[i] >= test_at]
    if em_steps:
        true_e = (X[[nxt_emo[i] for i in em_steps], dim:dim + EMO_DIM] - emo_mean) / emo_std
        model_e = (X[em_steps, dim:dim + EMO_DIM] - emo_mean) / emo_std + pe[em_steps] * emo_dstd / emo_std
        last_e = (X[em_steps, dim:dim + EMO_DIM] - emo_mean) / emo_std
        res["emotion"] = {"stream_mse": round(float(((model_e - true_e) ** 2).mean()), 4),
                          "last_one_mse": round(float(((last_e - true_e) ** 2).mean()), 4)}
    # surprise: how far each test text event fell from what the state expected just before it
    sur = sorted(((1 - float(pt[i] @ X[nxt_text[i], :dim]), nxt_text[i]) for i in steps), reverse=True)
    res["most_surprising"] = [{"surprise": round(s, 3), "at": str(events[j]["t"])[:16], "source": events[j]["source"],
                               "text": events[j]["text"][:200]} for s, j in sur[:6]]
    res["least_surprising"] = [{"surprise": round(s, 3), "at": str(events[j]["t"])[:16], "source": events[j]["source"],
                                "text": events[j]["text"][:200]} for s, j in sur[-3:]]
    t, e = res["text"], res.get("emotion", {})
    res["beats_text_baselines"] = t["stream"]["mrr"] > max(t["last_one"]["mrr"], t["mean_last_six"]["mrr"])
    res["beats_emotion_baseline"] = bool(e) and e["stream_mse"] < e["last_one_mse"]
    res["verdict"] = ("goes on to a shadow week" if res["beats_text_baselines"] and res["beats_emotion_baseline"]
                      else "does not beat what he has: recorded as tried, not taken further as it stands")
    os.makedirs(out_dir, exist_ok=True)
    json.dump(res, open(os.path.join(out_dir, "replay-result.json"), "w"), indent=2)
    torch.save(model.state_dict(), os.path.join(out_dir, "stream-replay.pt"))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--days", type=int, default=45, help="only the last N days of his history")
    a = ap.parse_args()
    out = a.out or tempfile.mkdtemp(prefix="latent-stream-replay-")
    t0 = time.time()
    ev = build_stream()
    since = datetime.now(timezone.utc) - timedelta(days=a.days)
    ev = [e for e in ev if e["t"] >= since]
    from collections import Counter
    print("stream: %d events over %d days; %s" % (len(ev), len({e['t'].date() for e in ev}),
          dict(Counter(e["source"] for e in ev))))
    import sys
    sys.path.insert(0, os.path.join(WS, "scripts"))
    from jepa_predictor import encoder           # the frozen nomic encoder his JEPA heads use
    enc = encoder()
    ev = embed_texts(ev, lambda texts: enc.encode(texts, batch_size=32), os.path.join(out, "text-vectors.jsonl"))
    print("embedded in %.0f s" % (time.time() - t0))
    res = run(ev, out, epochs=a.epochs)
    print(json.dumps({k: v for k, v in res.items() if k not in ("most_surprising", "least_surprising")}, indent=2))
    print("\nmost surprising on the test days (did these surprise HIM? that is the question):")
    for r in res["most_surprising"]:
        print("  %.3f  %s  %-8s %s" % (r["surprise"], r["at"], r["source"], " ".join(r["text"].split())[:150]))
    print("\nleast surprising:")
    for r in res["least_surprising"]:
        print("  %.3f  %s  %-8s %s" % (r["surprise"], r["at"], r["source"], " ".join(r["text"].split())[:150]))
    print("\nwritten only to", out, "(%.0f s)" % (time.time() - t0))


if __name__ == "__main__":
    main()

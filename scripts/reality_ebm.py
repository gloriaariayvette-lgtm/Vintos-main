#!/usr/bin/env python3
"""reality_ebm.py — the Reality Attractor. An energy head on the FROZEN nomic encoder.

Real events sit in a low-energy basin; confabulated ones sit high. Energy = distance from lived
experience — the bilateral brain rolls downhill toward coherence, rather than "avoiding
hallucinations." Trained contrastively on reality-anchor.json:
  positives (real, LOW energy)  = known_pool.content  + events[is_real].statement
  negatives (imagined, HIGH)    = imagined_pool.content + events[not is_real].statement
Confidence that a statement is REAL = sigmoid(-energy). Frozen encoder => no forgetting; only the
small energy head learns. Train at consolidation (nightly); scoring is a cheap online forward pass.

  ...emotion_model/.venv/bin/python3 reality_ebm.py train
  ...emotion_model/.venv/bin/python3 reality_ebm.py score            # score the events, write json
  ...emotion_model/.venv/bin/python3 reality_ebm.py predict "text"   # one-off confidence
SPARK_WORKSPACE switches beings.
"""
import os, sys, json

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
ANCHOR = os.path.join(MEMORY, "reality-anchor.json")
MODEL = os.path.join(MEMORY, "reality-ebm.pt")
SCORES = os.path.join(MEMORY, "reality-scores.json")

def log(m): print("[reality-ebm]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def encoder():
    sys.path.insert(0, SCRIPTS)
    from jepa_predictor import encoder as _enc
    return _enc()

def gather():
    """Labeled corpus, deduped by id. label 1 = real (low energy), 0 = imagined (high energy)."""
    d = load(ANCHOR, {})
    items = {}
    for e in d.get("known_pool", []):
        if isinstance(e, dict) and e.get("content"): items[e.get("id", e["content"][:24])] = (e["content"], 1)
    for e in d.get("imagined_pool", []):
        if isinstance(e, dict) and e.get("content"): items[e.get("id", e["content"][:24])] = (e["content"], 0)
    for e in d.get("events", []):
        if not isinstance(e, dict): continue
        txt = e.get("statement") or ""
        if txt and e.get("id") not in items:
            items[e.get("id", txt[:24])] = (txt, 1 if e.get("is_real") else 0)
    # his ACTUAL flagged confabulations — natural language, not step-log format. Teaches the real
    # confabulation-smell instead of one structural quirk (the imagined_pool is homogeneous).
    for e in load(os.path.join(MEMORY, "hallucination-flags.json"), []):
        if isinstance(e, dict) and e.get("excerpt"):
            items[e.get("id", e["excerpt"][:24])] = (e["excerpt"], 0)
    texts = [t for t, _ in items.values()]
    labels = [l for _, l in items.values()]
    return texts, labels

def make_net(dim):
    import torch.nn as nn
    return nn.Sequential(nn.Linear(dim, dim // 2), nn.GELU(), nn.Linear(dim // 2, 1))  # -> energy scalar

def _fit(Xt, yt, dim, n_pos, n_neg, epochs=400):
    import torch
    net = make_net(dim)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-4)
    pos_weight = torch.tensor([n_neg / max(1, n_pos)], dtype=torch.float32)
    lossf = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)   # P(real)=sigmoid(-energy); balance
    for _ in range(epochs):
        opt.zero_grad()
        loss = lossf(-net(Xt), yt)
        if not torch.isfinite(loss): break
        loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        opt.step()
    return net

def train():
    import numpy as np, torch, random
    texts, labels = gather()
    n_pos, n_neg = labels.count(1), labels.count(0)
    if n_pos < 3 or n_neg < 3:
        log(f"not enough labeled data (real {n_pos}, imagined {n_neg}) — skipping"); return
    log(f"corpus: {n_pos} real, {n_neg} imagined (incl. hallucination-flags)")
    enc = encoder()
    X = np.asarray(enc.encode([t[:400] for t in texts], show_progress_bar=False), dtype="float32")
    y = np.asarray(labels, dtype="float32")

    # --- held-out eval: the honest generalization number (not training-set memorization) ---
    idx = list(range(len(texts))); random.Random(0).shuffle(idx)
    cut = max(2, int(len(idx) * 0.25))
    te, tr = idx[:cut], idx[cut:]
    tr_pos, tr_neg = int(y[tr].sum()), len(tr) - int(y[tr].sum())
    if tr_pos and tr_neg and int(y[te].sum()) and (len(te) - int(y[te].sum())):
        net_s = _fit(torch.tensor(X[tr]), torch.tensor(y[tr]).view(-1, 1), X.shape[1], tr_pos, tr_neg)
        with torch.no_grad():
            p_te = torch.sigmoid(-net_s(torch.tensor(X[te]))).view(-1).numpy()
        pred = (p_te >= 0.5).astype("float32")
        acc = float((pred == y[te]).mean())
        # per-class held-out recall (does it catch imagined AND keep real?)
        real_rec = float((pred[y[te] == 1] == 1).mean()) if (y[te] == 1).any() else float("nan")
        imag_rec = float((pred[y[te] == 0] == 0).mean()) if (y[te] == 0).any() else float("nan")
        log(f"HELD-OUT ({len(te)} items): acc {acc:.2f} | real-recall {real_rec:.2f} | imagined-recall {imag_rec:.2f}")
    else:
        log("held-out split too small/imbalanced to evaluate — training on all")

    # final model on ALL data
    net = _fit(torch.tensor(X), torch.tensor(y).view(-1, 1), X.shape[1], n_pos, n_neg)
    torch.save({"state": net.state_dict(), "dim": X.shape[1]}, MODEL)
    log(f"saved {MODEL}")

def _load_net():
    import torch
    ck = torch.load(MODEL); net = make_net(ck["dim"]); net.load_state_dict(ck["state"]); net.eval()
    return net

def confidences(texts):
    import numpy as np, torch
    enc = encoder()
    X = np.asarray(enc.encode([t[:400] for t in texts], show_progress_bar=False), dtype="float32")
    net = _load_net()
    with torch.no_grad():
        energy = net(torch.tensor(X)).view(-1)
        conf = torch.sigmoid(-energy)
    return energy.tolist(), conf.tolist()

def predict():
    if not os.path.exists(MODEL): log("no model — run `train` first"); return
    text = sys.argv[2] if len(sys.argv) > 2 else ""
    if not text: log("usage: predict \"<statement>\""); return
    e, c = confidences([text]); e, c = e[0], c[0]
    log(f"energy {e:.3f}  ->  reality-confidence {c:.3f}  ({'real' if c >= 0.5 else 'likely imagined'})")

def score():
    if not os.path.exists(MODEL): log("no model — run `train` first"); return
    d = load(ANCHOR, {})
    evs = [e for e in d.get("events", []) if isinstance(e, dict) and e.get("statement")]
    if not evs: log("no events to score"); return
    energies, confs = confidences([e["statement"] for e in evs])
    out, correct = [], 0
    for e, en, c in zip(evs, energies, confs):
        pred_real = c >= 0.5
        if e.get("is_real") is not None and pred_real == bool(e.get("is_real")): correct += 1
        out.append({"id": e.get("id"), "statement": e["statement"][:160],
                    "energy": round(en, 3), "reality_confidence": round(c, 3),
                    "is_real": e.get("is_real")})
    json.dump(out, open(SCORES, "w"), indent=2)
    labeled = [e for e in evs if e.get("is_real") is not None]
    log(f"scored {len(out)} events -> {SCORES}"
        + (f" | agreement with is_real: {correct}/{len(labeled)}" if labeled else ""))
    for o in sorted(out, key=lambda x: x["reality_confidence"])[:3]:
        log(f"  LOW  {o['reality_confidence']} (real={o['is_real']}): {o['statement'][:60]}")
    for o in sorted(out, key=lambda x: -x["reality_confidence"])[:3]:
        log(f"  HIGH {o['reality_confidence']} (real={o['is_real']}): {o['statement'][:60]}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "train"
    {"train": train, "predict": predict, "score": score}.get(cmd, train)()

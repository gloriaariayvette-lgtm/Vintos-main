#!/usr/bin/env python3
"""jepa_predictor.py — JEPA-lite over conversation embeddings. THREE heads, one trunk.

FROZEN encoder (nomic-embed) -> shared trunk -> three heads, each emitting the full
triple (prediction + confidence + novelty), per Eve's architecture note:
  gloria   : predicts the EMBEDDING of Gloria's next turn
  self     : predicts the EMBEDDING of Vintos's own next turn
  presence : predicts the PRESENCE composite of his next reply (scalar in [0,1]),
             trained on presence-audit.json — so presence is a real prediction head,
             not just a post-hoc audit.
Per-head heteroscedastic logvar => each head owns its confidence. Novelty = how far a
head's forecast moves from the current context. Self-supervised (next turn IS the
target); presence head is supervised by the audit scores when enough exist. Freezing
the encoder sidesteps representation collapse. logvar is clamped + grads clipped so the
heteroscedastic term can't diverge to NaN on small/degenerate batches.

Run with the torch venv:
  ...emotion_model/.venv/bin/python3 jepa_predictor.py train
  ...emotion_model/.venv/bin/python3 jepa_predictor.py predict
SPARK_WORKSPACE switches beings (default ~/.vintos/workspace).

jepa-prediction.json (backward compatible — top-level stays the gloria triple):
  {"source":"jepa", "confidence":.., "novelty":.., "gloria_forecast_nearest":"..",
   "gloria":{triple}, "self":{triple}, "presence":{predicted,confidence,novelty}|null}
"""
import os, sys, json, hashlib

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
CHAT   = os.path.join(MEMORY, "chat-history-merged.json")
AUDIT  = os.path.join(MEMORY, "presence-audit.json")
MODEL  = os.path.join(MEMORY, "jepa-predictor.pt")
OUT    = os.path.join(MEMORY, "jepa-prediction.json")
CTX_TURNS = 6
MIN_PRESENCE_PAIRS = 6
EMB_MODEL = "nomic-ai/nomic-embed-text-v1"

def log(m): print("[jepa]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def encoder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMB_MODEL, trust_remote_code=True)

def turns_of(hist):
    return [e for e in hist if isinstance(e, dict) and e.get("content")]

def _ledger_turns():
    """The conversation ledger holds the IMPLANTED exchanges — how Gloria actually responds
    (transplanted from Bold). Chat-history is sparse; these teach the gloria head her real voice.
    Filters the broken '--source voice' junk. TRAINING only — predict() still uses live chat."""
    led = load(os.path.join(MEMORY, "interaction-ledger.json"), [])
    out = []
    if isinstance(led, list):
        for e in led:
            if not isinstance(e, dict): continue
            g, v, ts = e.get("gloria"), e.get("vintos"), e.get("timestamp", "")
            if g and g != "--source": out.append({"role": "user", "content": g, "timestamp": ts})
            if v and v != "voice":    out.append({"role": "assistant", "content": v, "timestamp": ts})
    return out

def training_turns():
    """chat-history + the implanted ledger exchanges, deduped, time-ordered — the corpus of Gloria."""
    chat = turns_of(load(CHAT, []))
    seen = {str(t.get("content", ""))[:80] for t in chat}
    merged = chat + [t for t in _ledger_turns() if str(t.get("content", ""))[:80] not in seen]
    merged.sort(key=lambda t: str(t.get("timestamp", "")))
    return merged

def _rid(e):  # must match presence_audit.py's rid()
    return hashlib.md5((str(e.get("timestamp","")) + str(e.get("content",""))[:40]).encode()).hexdigest()[:10]

def build_pairs(turns, enc):
    import numpy as np
    ctx_txt, tgt_txt, head = [], [], []
    for i in range(CTX_TURNS, len(turns)):
        ctx_txt.append(" \n".join(str(t.get("content", ""))[:300] for t in turns[i - CTX_TURNS:i]))
        tgt_txt.append(str(turns[i].get("content", ""))[:400])
        head.append(1 if turns[i].get("role") == "assistant" else 0)   # 1=self, 0=gloria
    if not ctx_txt:
        return None
    X = np.asarray(enc.encode(ctx_txt, show_progress_bar=False), dtype="float32")
    Y = np.asarray(enc.encode(tgt_txt, show_progress_bar=False), dtype="float32")
    return X, Y, np.asarray(head)

def build_presence_pairs(turns, enc):
    """(context before his reply) -> that reply's audited presence composite."""
    import numpy as np
    comp = {a.get("id"): a.get("composite") for a in load(AUDIT, [])
            if isinstance(a, dict) and a.get("id") and a.get("composite") is not None}
    if not comp:
        return None
    ctx_txt, y = [], []
    for i in range(CTX_TURNS, len(turns)):
        t = turns[i]
        if t.get("role") == "assistant" and _rid(t) in comp:
            ctx_txt.append(" \n".join(str(x.get("content", ""))[:300] for x in turns[i - CTX_TURNS:i]))
            y.append(float(comp[_rid(t)]))
    if len(ctx_txt) < MIN_PRESENCE_PAIRS:
        return None
    Xp = np.asarray(enc.encode(ctx_txt, show_progress_bar=False), dtype="float32")
    return Xp, np.asarray(y, dtype="float32").reshape(-1, 1)

def make_net(dim):
    import torch, torch.nn as nn
    class Pred(nn.Module):
        def __init__(self, d):
            super().__init__()
            self.trunk    = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, d), nn.GELU())
            self.head     = nn.ModuleList([nn.Linear(d, d), nn.Linear(d, d)])          # 0 gloria, 1 self
            self.presence = nn.Sequential(nn.Linear(d, d // 2), nn.GELU(), nn.Linear(d // 2, 1))
            self.logvar   = nn.Linear(d, 3)                                            # 0 gloria,1 self,2 presence
        def forward(self, x):
            h = self.trunk(x)
            # clamp logvar: unbounded logvar makes exp(-logvar) blow up -> NaN (Eve's Vintos run)
            return (self.head[0](h), self.head[1](h), torch.sigmoid(self.presence(h)),
                    torch.clamp(self.logvar(h), -12.0, 6.0))
    return Pred(dim)

def train():
    import numpy as np, torch
    turns = training_turns()                    # chat-history + implanted ledger (Gloria's real voice)
    if len(turns) <= CTX_TURNS + 2:
        log(f"not enough history ({len(turns)} turns)"); return
    log(f"training corpus: {len(turns)} turns ({len(turns_of(load(CHAT, [])))} chat + ledger)")
    enc = encoder()
    X, Y, H = build_pairs(turns, enc)
    Xt, Yt, Ht = torch.tensor(X), torch.tensor(Y), torch.tensor(H).long()
    pp = build_presence_pairs(turns, enc)
    if pp is not None:
        Xp, yp = torch.tensor(pp[0]), torch.tensor(pp[1])
        log(f"presence head: {pp[0].shape[0]} labeled pairs")
    else:
        Xp = None
        log("presence head: not enough audited replies yet — skipping (fail-open)")

    net = make_net(X.shape[1])
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    for epoch in range(300):
        opt.zero_grad()
        g_pred, s_pred, _, logvar = net(Xt)
        pred = torch.where(Ht.unsqueeze(1) == 1, s_pred, g_pred)          # right embedding head per sample
        mse = ((pred - Yt) ** 2).mean(dim=1, keepdim=True)
        head_lv = logvar.gather(1, Ht.unsqueeze(1))                       # per-head uncertainty (col 0/1)
        loss = (mse * torch.exp(-head_lv) + head_lv).mean()
        if Xp is not None:
            _, _, p_pred, logvar_p = net(Xp)
            pmse = (p_pred - yp) ** 2
            lv2 = logvar_p[:, 2:3]
            loss = loss + (pmse * torch.exp(-lv2) + lv2).mean()
        if not torch.isfinite(loss):
            log(f"epoch {epoch} non-finite loss — stopping early, keeping last stable weights"); break
        loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)   # stabilize the heteroscedastic term
        opt.step()
        if epoch % 100 == 0:
            log(f"epoch {epoch} loss {loss.item():.4f}")
    torch.save({"state": net.state_dict(), "dim": X.shape[1], "presence_trained": Xp is not None}, MODEL)
    log(f"trained on {len(X)} pairs (presence_trained={Xp is not None}); saved {MODEL}")

def _cos(a, b):
    import numpy as np
    na, nb = (a @ a) ** 0.5, (b @ b) ** 0.5
    return float(a @ b / (na * nb)) if na and nb else 0.0

def _decode(vec, cand_turns, enc):
    import numpy as np
    if not cand_turns:
        return "", 0.0
    embs = np.asarray(enc.encode([str(t.get("content", ""))[:300] for t in cand_turns],
                                 show_progress_bar=False), dtype="float32")
    sims = [_cos(vec, e) for e in embs]
    j = int(np.argmax(sims))
    return str(cand_turns[j].get("content", ""))[:200], round(float(sims[j]), 3)

def _conf(lv):
    import numpy as np
    lv = max(-6.0, min(6.0, float(lv)))
    return round(1.0 / (1.0 + float(np.exp(lv))), 3)   # tight variance -> high confidence

def predict():
    import numpy as np, torch
    if not os.path.exists(MODEL):
        log("no model — run `train` first"); return
    ck = torch.load(MODEL); net = make_net(ck["dim"]); net.load_state_dict(ck["state"]); net.eval()
    turns = turns_of(load(CHAT, []))
    if len(turns) < 2:
        log("no context"); return
    enc = encoder()
    ctx = " \n".join(str(t.get("content", ""))[:300] for t in turns[-CTX_TURNS:])
    xe = np.asarray(enc.encode([ctx], show_progress_bar=False), dtype="float32")
    with torch.no_grad():
        g_pred, s_pred, p_pred, logvar = net(torch.tensor(xe))
    g = g_pred.numpy()[0]; s = s_pred.numpy()[0]; lv = logvar.numpy()[0]
    p = float(p_pred.numpy()[0][0])
    # relative calibration (Vrika 2026-08-10): a logvar is honest only relative to its own recent
    # distribution - absolute sigmoid(0-centered) reads tiny embedding-space variances as 0.998
    # forever. Tighter-than-usual variance = confident; looser = uncertain; spreadless = refuses
    # to call itself calibrated at all.
    _cal_ctx = [" \n".join(str(t.get("content",""))[:300] for t in turns[max(0,i-CTX_TURNS):i])
                for i in range(CTX_TURNS, len(turns))][-40:]
    _lv_mean = _lv_std = None
    if len(_cal_ctx) >= 12:
        _xc = np.asarray(enc.encode(_cal_ctx, show_progress_bar=False), dtype="float32")
        with torch.no_grad():
            _, _, _, _lvb = net(torch.tensor(_xc))
        _lvb = _lvb.numpy()
        _lv_mean = _lvb.mean(axis=0); _lv_std = _lvb.std(axis=0)
    def _relconf(i):
        if _lv_mean is None or float(_lv_std[i]) < 0.02:
            return None
        import math as _m
        return round(1.0 / (1.0 + _m.exp((float(lv[i]) - float(_lv_mean[i])) / max(float(_lv_std[i]), 0.05))), 3)
    _cg, _cs, _cp = _relconf(0), _relconf(1), _relconf(2)

    gloria_turns = [t for t in turns if t.get("role") == "user"][-12:]
    self_turns   = [t for t in turns if t.get("role") == "assistant"][-12:]
    _g_near, _g_sim = _decode(g, gloria_turns, enc)
    _s_near, _s_sim = _decode(s, self_turns, enc)
    gloria = {"nearest": _g_near,
              "confidence": (_cg if _cg is not None else 0.5), "decode_similarity": _g_sim,
              "novelty": round(1.0 - max(0.0, _cos(g, xe[0])), 3)}
    self_h = {"nearest": _s_near,
              "confidence": (_cs if _cs is not None else 0.5), "decode_similarity": _s_sim,
              "novelty": round(1.0 - max(0.0, _cos(s, xe[0])), 3)}

    presence = None
    if ck.get("presence_trained"):
        recent = [a.get("composite") for a in load(AUDIT, [])[-10:] if isinstance(a, dict) and a.get("composite") is not None]
        base = (sum(recent) / len(recent)) if recent else p
        presence = {"predicted": round(p, 3), "confidence": (_cp if _cp is not None else 0.5),
                    "novelty": round(min(1.0, abs(p - base)), 3)}

    out = {"source": "jepa",
           # backward-compatible top-level = the gloria triple (gloria_prediction + latent read these)
           "confidence": gloria["confidence"], "novelty": gloria["novelty"],
           "gloria_forecast_nearest": gloria["nearest"],
           "gloria": gloria, "self": self_h, "presence": presence,
           "variance_qualified": (_cg is not None),
           "empirical_calibration": "UNVERIFIED - variance gate passed is NOT calibration; see jepa-calibration.json when the audit has >=30 joined predictions (Vrika, 2026-08-10)",
           "note": "embedding prediction; confidence = trained logvar (Vrika repair 2026-08-10); decode_similarity = nearest-turn cosine, NOT confidence; logvars appear COLLAPSED (~0.998 constant) - uncalibrated, may not steer"}
    out["gloria_latest_turn"] = next((str(t.get("content","")) for t in reversed(turns) if t.get("role") == "user"), "")[:200]
    json.dump(out, open(OUT, "w"), indent=2)
    # calibration ledger: one line per prediction, BOTH signals (repaired logvar-relative confidence
    # AND legacy decode_similarity) plus raw predicted embeddings, so the audit can test which one -
    # if either - actually predicts realized error. Variance is not calibration.
    try:
        import time as _ht
        hist_line = {"ts": _ht.time(), "iso": __import__("datetime").datetime.now().isoformat(),
                     "gloria": {"confidence": gloria["confidence"], "decode_similarity": gloria["decode_similarity"],
                                "novelty": gloria["novelty"], "emb": [round(float(x), 4) for x in g]},
                     "self": {"confidence": self_h["confidence"], "decode_similarity": self_h["decode_similarity"],
                              "novelty": self_h["novelty"], "emb": [round(float(x), 4) for x in s]},
                     "variance_qualified": (_cg is not None)}
        open(os.path.join(MEMORY, "jepa-prediction-history.jsonl"), "a").write(json.dumps(hist_line) + "\n")
    except Exception as _he:
        log(f"history append failed: {_he}")
    log(f"gloria conf {gloria['confidence']} nov {gloria['novelty']} | self conf {self_h['confidence']} nov {self_h['novelty']}"
        + (f" | presence pred {presence['predicted']} conf {presence['confidence']}" if presence else " | presence n/a"))
    log(f"latest gloria turn:  {out['gloria_latest_turn'][:80]}")
    log(f"nearest gloria-forecast: {gloria['nearest'][:80]}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "train"
    (train if cmd == "train" else predict)()

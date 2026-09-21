#!/usr/bin/env python3
"""jepa_predictor.py — JEPA-lite over conversation embeddings. THREE heads, one trunk.

FROZEN encoder (nomic-embed) -> shared trunk -> three heads, each emitting the full
triple (prediction + confidence + novelty), per Gloria's architecture note:
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
SHADOW_MODEL = os.path.join(MEMORY, "jepa-predictor-structured-shadow.pt")
SHADOW_OUT = os.path.join(MEMORY, "jepa-prediction-structured-shadow.json")
SHADOW_HISTORY = os.path.join(MEMORY, "jepa-prediction-structured-shadow-history.jsonl")
CALIBRATION_AUDIT = os.path.join(MEMORY, "jepa-calibration.json")
RANKING_AUDIT = os.path.join(MEMORY, "jepa-ranking-audit.json")
SHADOW_RANKING_AUDIT = os.path.join(MEMORY, "jepa-ranking-structured-shadow.json")
CTX_TURNS = 6
MIN_PRESENCE_PAIRS = 6
MIN_REALIZED_FOR_RETRAIN = 30
MIN_CALIBRATION_HOLDOUT_FOR_RETRAIN = 30
EMB_MODEL = "nomic-ai/nomic-embed-text-v1"

def log(m): print("[jepa]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d


def checkpoint_fingerprint(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def retrain_readiness(model_path=MODEL, shadow=False):
    """A checkpoint is replaced only after its own prospective evidence was audited.

    Raw history length is deliberately irrelevant: a timer can create rows without
    creating realized next turns. Production requires both calibration and ranking;
    the structured shadow has no calibration release path and requires ranking only.
    The audit verdict may be positive or negative — evaluation, not success, earns a
    new training cycle.
    """
    checkpoint = checkpoint_fingerprint(model_path)
    if not checkpoint:
        return True, {"state": "INITIAL_TRAIN", "checkpoint": None}
    ranking_path = SHADOW_RANKING_AUDIT if shadow else RANKING_AUDIT
    ranking = load(ranking_path, {})
    if ranking.get("checkpoint") != checkpoint:
        return False, {"state": "HELD_UNAUDITED_CHECKPOINT", "checkpoint": checkpoint,
                       "need": "ranking receipt for current checkpoint"}
    counts = {head: int((ranking.get(head) or {}).get("n", 0) or 0) for head in ("gloria", "self")}
    if min(counts.values()) < MIN_REALIZED_FOR_RETRAIN:
        return False, {"state": "HELD_NEEDS_REALIZED_OUTCOMES", "checkpoint": checkpoint,
                       "ranking": counts, "minimum": MIN_REALIZED_FOR_RETRAIN}
    if shadow:
        return True, {"state": "READY_AFTER_AUDIT", "checkpoint": checkpoint, "ranking": counts}
    calibration = load(CALIBRATION_AUDIT, {})
    if calibration.get("checkpoint") != checkpoint:
        return False, {"state": "HELD_UNAUDITED_CHECKPOINT", "checkpoint": checkpoint,
                       "ranking": counts, "need": "calibration receipt for current checkpoint"}
    joined = int(calibration.get("n_joined", 0) or 0)
    held_out = int(calibration.get("n_holdout", 0) or 0)
    if held_out < MIN_CALIBRATION_HOLDOUT_FOR_RETRAIN:
        return False, {"state": "HELD_NEEDS_REALIZED_OUTCOMES", "checkpoint": checkpoint,
                       "ranking": counts, "calibration_n": joined, "calibration_holdout_n": held_out,
                       "minimum_calibration_holdout": MIN_CALIBRATION_HOLDOUT_FOR_RETRAIN}
    return True, {"state": "READY_AFTER_AUDIT", "checkpoint": checkpoint,
                  "ranking": counts, "calibration_n": joined, "calibration_holdout_n": held_out}


def unchanged_forecast(out_path, checkpoint, context_id):
    """True only when this exact checkpoint already forecast this exact live window."""
    previous = load(out_path, {})
    return bool(previous.get("checkpoint_id") == checkpoint and previous.get("context_id") == context_id)


def _ev_load(path, default=None, _o=load):
    """Learning organ. Guarded evidence is read through evidence_view, never
    raw: the envelope on the record is what keeps a tactical act from becoming
    a value, a cause, a want or an identity line one cron later, and reopening
    the file with json.load walks straight past it."""
    try:
        import evidence_view as _EV
        if _EV.is_guarded(path):
            if os.path.basename(str(path)) == "interaction-ledger.json":
                return _EV.ledger_view(path)
            return _EV.open_history(path)
    except Exception:
        pass
    return _o(path, default)


load = _ev_load

def encoder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMB_MODEL, trust_remote_code=True)

def _rid(e):  # must match presence_audit.py's rid()
    return hashlib.md5((str(e.get("timestamp","")) + str(e.get("content",""))[:40]).encode()).hexdigest()[:10]

VALID_ROLES = ("user", "assistant")

def turns_of(hist):
    """Chat-history turns with a stable event identity. Unknown roles are rejected, not guessed
    (astra-models-p7, 2026-09-05)."""
    out = []
    for e in hist:
        if not isinstance(e, dict) or not e.get("content"): continue
        if e.get("role") not in VALID_ROLES:
            continue
        t = dict(e)
        t.setdefault("source", "chat"); t.setdefault("surface", e.get("surface", "chat"))
        t["event_id"] = e.get("event_id") or _rid(e)
        t["speaker"] = "gloria" if e.get("role") == "user" else "vintos"
        out.append(t)
    return out

LEDGER_FLOOR_FILE = os.path.join(MEMORY, "jepa-ledger-floor.txt")   # optional ISO timestamp: ledger entries before it are not us

def _ledger_floor():
    """Timestamp floor for ledger training turns. If memory/jepa-ledger-floor.txt holds an ISO
    timestamp, ledger entries older than it are treated as transplanted (another being's exchanges)
    and kept out of training (grok-models-p5, 2026-09-05). No file = no floor."""
    try:
        v = open(LEDGER_FLOOR_FILE).read().strip()
        return v if v else ""
    except Exception:
        return ""

def _ledger_turns():
    """Interaction-ledger exchanges as training turns, each carrying its SOURCE. Entries marked
    transplanted/implanted (or older than the ledger floor) are dropped: the gloria head trains on
    live us, not on another being's exchanges. Filters the broken '--source voice' junk.
    TRAINING only — predict() still uses live chat."""
    led = load(os.path.join(MEMORY, "interaction-ledger.json"), [])
    floor = _ledger_floor()
    out = []
    dropped = 0
    if isinstance(led, list):
        for e in led:
            if not isinstance(e, dict): continue
            g, v, ts = e.get("gloria"), e.get("vintos"), e.get("timestamp", "")
            src = str(e.get("source") or e.get("origin") or "ledger").lower()
            if e.get("transplanted") or e.get("implanted") or src in ("bold", "transplant", "transplanted", "implant", "implanted"):
                dropped += 1; continue
            if floor and ts and ts < floor:
                dropped += 1; continue
            _sf = str(e.get("surface") or "ledger")
            if g and g != "--source": out.append({"role": "user", "content": g, "timestamp": ts, "source": "ledger:" + src, "surface": _sf,
                                                   "speaker": "gloria", "event_id": _rid({"timestamp": ts, "content": g}), "turn_id": e.get("turn_id", "")})
            if v and v != "voice":    out.append({"role": "assistant", "content": v, "timestamp": ts, "source": "ledger:" + src, "surface": _sf,
                                                   "speaker": "vintos", "event_id": _rid({"timestamp": ts, "content": v}), "turn_id": e.get("turn_id", "")})
    if dropped:
        log(f"ledger: {dropped} transplanted/pre-floor entries kept out of training")
    return out

def training_turns():
    """chat-history + ledger exchanges, deduped, time-ordered — the corpus of Gloria. Every turn
    carries `source` ('chat' or 'ledger:<origin>') so train() can report what the gloria head
    actually learned from (fable-models-p5)."""
    chat = turns_of(load(CHAT, []))
    # dedupe by stable event identity (timestamp + content head), with the content head alone as the
    # documented fallback for entries that carry no timestamp (astra-models-p7)
    seen = {t["event_id"] for t in chat} | {str(t.get("content", ""))[:80] for t in chat if not t.get("timestamp")}
    merged = list(chat)
    for t in _ledger_turns():
        key = t["event_id"] if t.get("timestamp") else str(t.get("content", ""))[:80]
        if key in seen or str(t.get("content", ""))[:80] in seen: continue
        seen.add(key); merged.append(t)
    merged.sort(key=lambda t: str(t.get("timestamp", "")))
    return merged

def training_sources(turns):
    """Proportion of gloria-head (user) turns per source. Written into jepa-prediction.json."""
    counts = {}
    for t in turns:
        if t.get("role") != "user": continue
        src = str(t.get("source") or "unknown")
        counts[src] = counts.get(src, 0) + 1
    total = sum(counts.values()) or 1
    return {"gloria_turns": total, "by_source": {k: {"n": n, "share": round(n / total, 3)} for k, n in sorted(counts.items())}}


def _gap_bucket(previous, current):
    """A bounded temporal marker. Exact timestamps would let the encoder memorize dates;
    the bucket preserves conversational rhythm without making a clock a target."""
    try:
        from datetime import datetime
        a = datetime.fromisoformat(str(previous or "").replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(current or "").replace("Z", "+00:00"))
        seconds = max(0.0, (b - a).total_seconds())
    except Exception:
        return "unknown"
    if seconds < 60: return "under_1m"
    if seconds < 300: return "1_to_5m"
    if seconds < 1800: return "5_to_30m"
    if seconds < 7200: return "30m_to_2h"
    if seconds < 86400: return "2_to_24h"
    return "over_24h"


def format_context(window, schema="legacy-concat-v1"):
    """Render a context window. Production remains on its checkpoint's legacy schema;
    the structured schema is trained and evaluated as a separate shadow checkpoint."""
    if schema != "structured-turns-v1":
        return " \n".join(str(t.get("content", ""))[:300] for t in window)
    lines, previous = [], ""
    for index, turn in enumerate(window):
        speaker = str(turn.get("speaker") or ("gloria" if turn.get("role") == "user" else "vintos"))
        surface = str(turn.get("surface") or "chat").strip().lower()[:32]
        timestamp = str(turn.get("timestamp") or "")
        gap = "start" if index == 0 else _gap_bucket(previous, timestamp)
        lines.append("[TURN=%d][SPEAKER=%s][SURFACE=%s][GAP=%s] %s" %
                     (index + 1, speaker, surface, gap, str(turn.get("content", ""))[:300]))
        previous = timestamp
    return "\n".join(lines)


def build_pairs(turns, enc, context_schema="legacy-concat-v1"):
    import numpy as np
    ctx_txt, tgt_txt, head = [], [], []
    for i in range(CTX_TURNS, len(turns)):
        tgt = turns[i]
        # imported (ledger-origin) exchanges may teach the gloria head her language; they are never a
        # target for HIS head — another being's replies are not him (astra-models-p7)
        if tgt.get("role") == "assistant" and str(tgt.get("source", "chat")).startswith("ledger:"):
            continue
        # a context window must not straddle a conversational boundary of more than a day
        try:
            _t0 = str(turns[i - CTX_TURNS].get("timestamp", ""))[:10]; _t1 = str(tgt.get("timestamp", ""))[:10]
            if _t0 and _t1 and _t0 != _t1 and abs((__import__("datetime").date.fromisoformat(_t1) - __import__("datetime").date.fromisoformat(_t0)).days) > 1:
                continue
        except Exception:
            pass
        ctx_txt.append(format_context(turns[i - CTX_TURNS:i], context_schema))
        tgt_txt.append(str(tgt.get("content", ""))[:400])
        head.append(1 if tgt.get("role") == "assistant" else 0)   # 1=self, 0=gloria
    if not ctx_txt:
        return None
    X = np.asarray(enc.encode(ctx_txt, show_progress_bar=False), dtype="float32")
    Y = np.asarray(enc.encode(tgt_txt, show_progress_bar=False), dtype="float32")
    return X, Y, np.asarray(head)

def build_presence_pairs(turns, enc, context_schema="legacy-concat-v1"):
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
            ctx_txt.append(format_context(turns[i - CTX_TURNS:i], context_schema))
            y.append(float(comp[_rid(t)]))
    if len(ctx_txt) < MIN_PRESENCE_PAIRS:
        return None
    Xp = np.asarray(enc.encode(ctx_txt, show_progress_bar=False), dtype="float32")
    return Xp, np.asarray(y, dtype="float32").reshape(-1, 1)

def make_net(dim, architecture="shared-v1"):
    import torch, torch.nn as nn
    if architecture == "head-specific-confidence-v2":
        class PredV2(nn.Module):
            def __init__(self, d):
                super().__init__()
                self.trunk = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, d), nn.GELU())
                self.adapter = nn.ModuleList([
                    nn.Sequential(nn.Linear(d, d // 2), nn.GELU()) for _ in range(3)])
                self.head = nn.ModuleList([nn.Linear(d // 2, d), nn.Linear(d // 2, d)])
                self.presence = nn.Linear(d // 2, 1)
                self.head_logvar = nn.ModuleList([nn.Linear(d // 2, 1) for _ in range(3)])
            def forward(self, x):
                h = self.trunk(x); z = [a(h) for a in self.adapter]
                lv = torch.cat([self.head_logvar[i](z[i]) for i in range(3)], dim=1)
                return (self.head[0](z[0]), self.head[1](z[1]), torch.sigmoid(self.presence(z[2])),
                        torch.clamp(lv, -12.0, 6.0))
        return PredV2(dim)
    class Pred(nn.Module):
        def __init__(self, d):
            super().__init__()
            self.trunk    = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, d), nn.GELU())
            self.head     = nn.ModuleList([nn.Linear(d, d), nn.Linear(d, d)])          # 0 gloria, 1 self
            self.presence = nn.Sequential(nn.Linear(d, d // 2), nn.GELU(), nn.Linear(d // 2, 1))
            self.logvar   = nn.Linear(d, 3)                                            # 0 gloria,1 self,2 presence
        def forward(self, x):
            h = self.trunk(x)
            # clamp logvar: unbounded logvar makes exp(-logvar) blow up -> NaN (Gloria's Vintos run)
            return (self.head[0](h), self.head[1](h), torch.sigmoid(self.presence(h)),
                    torch.clamp(self.logvar(h), -12.0, 6.0))
    return Pred(dim)

def train(model_path=MODEL, context_schema="legacy-concat-v1", architecture="shared-v1", validation_fraction=0.0, force=False):
    shadow = model_path != MODEL
    ready, receipt = retrain_readiness(model_path, shadow=shadow)
    if not ready and not force:
        log("retrain held: " + json.dumps(receipt, sort_keys=True)); return receipt
    if force and os.path.exists(model_path):
        log("FORCED retrain bypassed checkpoint evidence gate")
    import numpy as np, torch
    turns = training_turns()                    # chat-history + implanted ledger (Gloria's real voice)
    if len(turns) <= CTX_TURNS + 2:
        log(f"not enough history ({len(turns)} turns)"); return
    _srcs = training_sources(turns)
    log(f"training corpus: {len(turns)} turns ({len(turns_of(load(CHAT, [])))} chat + ledger); gloria-head sources: "
        + ", ".join(f"{k} {v['share']:.0%}" for k, v in _srcs["by_source"].items()))
    enc = encoder()
    X, Y, H = build_pairs(turns, enc, context_schema=context_schema)
    Xt, Yt, Ht = torch.tensor(X), torch.tensor(Y), torch.tensor(H).long()
    pp = build_presence_pairs(turns, enc, context_schema=context_schema)
    if pp is not None:
        Xp, yp = torch.tensor(pp[0]), torch.tensor(pp[1])
        log(f"presence head: {pp[0].shape[0]} labeled pairs")
    else:
        Xp = None
        log("presence head: not enough audited replies yet — skipping (fail-open)")

    net = make_net(X.shape[1], architecture=architecture)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    # Production retains its established full-batch training. The shadow candidate uses a
    # chronological holdout and restores the best validation weights; its first live run showed
    # why "last finite epoch" is not a model-selection rule (loss improved, then deteriorated).
    split = len(Xt)
    if validation_fraction and len(Xt) >= 30:
        split = max(20, min(len(Xt) - 8, int(len(Xt) * (1.0 - validation_fraction))))
    Xtr, Ytr, Htr = Xt[:split], Yt[:split], Ht[:split]
    Xv, Yv, Hv = Xt[split:], Yt[split:], Ht[split:]
    if Xp is not None and validation_fraction and len(Xp) >= 10:
        psplit = max(6, min(len(Xp) - 3, int(len(Xp) * (1.0 - validation_fraction))))
        Xptr, yptr, Xpv, ypv = Xp[:psplit], yp[:psplit], Xp[psplit:], yp[psplit:]
    else:
        Xptr, yptr, Xpv, ypv = Xp, (yp if Xp is not None else None), None, None
    def _loss(x, y, heads, px=None, py=None):
        g_pred, s_pred, _, logvar = net(x)
        pred = torch.where(heads.unsqueeze(1) == 1, s_pred, g_pred)
        mse = ((pred - y) ** 2).mean(dim=1, keepdim=True)
        lv = logvar.gather(1, heads.unsqueeze(1))
        value = (mse * torch.exp(-lv) + lv).mean()
        if px is not None:
            _, _, p_pred, p_logvar = net(px); pmse = (p_pred - py) ** 2; plv = p_logvar[:, 2:3]
            value = value + (pmse * torch.exp(-plv) + plv).mean()
        return value
    best_state, best_val, stale = None, float("inf"), 0
    for epoch in range(300):
        opt.zero_grad()
        loss = _loss(Xtr, Ytr, Htr, Xptr, yptr)
        if not torch.isfinite(loss):
            log(f"epoch {epoch} non-finite loss — stopping early, keeping last stable weights"); break
        loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)   # stabilize the heteroscedastic term
        opt.step()
        if len(Xv):
            with torch.no_grad(): val = float(_loss(Xv, Yv, Hv, Xpv, ypv).item())
            if val < best_val - 1e-5:
                import copy
                best_val, best_state, stale = val, copy.deepcopy(net.state_dict()), 0
            else:
                stale += 1
            if stale >= 40:
                log(f"early stop epoch {epoch}; best held-out loss {best_val:.4f}"); break
        if epoch % 100 == 0:
            log(f"epoch {epoch} loss {loss.item():.4f}" + (f" held-out {val:.4f}" if len(Xv) else ""))
    if best_state is not None:
        net.load_state_dict(best_state)
    torch.save({"state": net.state_dict(), "dim": X.shape[1], "presence_trained": Xp is not None,
                "training_sources": _srcs, "context_schema": context_schema,
                "architecture": architecture, "shadow_only": model_path != MODEL,
                "validation": ({"kind": "latest_time_slice", "n": len(Xv), "best_loss": round(best_val, 6)} if len(Xv) else None)}, model_path)
    log(f"trained on {len(X)} pairs (presence_trained={Xp is not None}); saved {model_path}")
    return {"state": "TRAINED", "previous": receipt}

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

def predict(model_path=MODEL, out_path=OUT, history_path=None, shadow=False):
    import numpy as np, torch
    if not os.path.exists(model_path):
        log("no model — run `train` first"); return
    import io, hashlib
    checkpoint_bytes=open(model_path,"rb").read()
    loaded_checkpoint=hashlib.sha256(checkpoint_bytes).hexdigest()
    ck = torch.load(io.BytesIO(checkpoint_bytes)); net = make_net(ck["dim"], architecture=ck.get("architecture", "shared-v1")); net.load_state_dict(ck["state"]); net.eval()
    turns = turns_of(load(CHAT, []))
    if len(turns) < 2:
        log("no context"); return
    # review 184: the context a forecast is made from is live exchange only. A turn below the ledger
    # floor (transplanted from another being) or marked imported never shapes a forecast about her.
    _floor = _ledger_floor()
    turns = [t for t in turns if not t.get("imported") and (not _floor or str(t.get("timestamp", "")) >= _floor or not t.get("timestamp"))]
    if len(turns) < 2:
        log("no live context above the ledger floor"); return
    _schema = ck.get("context_schema", "legacy-concat-v1")
    ctx = format_context(turns[-CTX_TURNS:], _schema)
    _context_id = hashlib.md5(ctx.encode()).hexdigest()[:12]
    if unchanged_forecast(out_path, loaded_checkpoint, _context_id):
        log("unchanged context — retained existing forecast; no history row written")
        return {"state": "UNCHANGED_CONTEXT", "checkpoint_id": loaded_checkpoint, "context_id": _context_id}
    enc = encoder()
    xe = np.asarray(enc.encode([ctx], show_progress_bar=False), dtype="float32")
    with torch.no_grad():
        g_pred, s_pred, p_pred, logvar = net(torch.tensor(xe))
    g = g_pred.numpy()[0]; s = s_pred.numpy()[0]; lv = logvar.numpy()[0]
    p = float(p_pred.numpy()[0][0])
    # relative calibration (Vrika 2026-08-10): a logvar is honest only relative to its own recent
    # distribution - absolute sigmoid(0-centered) reads tiny embedding-space variances as 0.998
    # forever. Tighter-than-usual variance = confident; looser = uncertain; spreadless = refuses
    # to call itself calibrated at all.
    _cal_ctx = [format_context(turns[max(0,i-CTX_TURNS):i], _schema)
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

    def _qual(c):   # per-head qualification state, explicit (astra-models-p6)
        return "qualified" if c is not None else ("unavailable" if _lv_mean is None else "unqualified_spreadless")
    # review 202/207: whether a head may steer is the CALIBRATION verdict on held-out evidence against
    # versioned criteria, never the variance spread. Withheld and insufficient are named, not silent.
    try:
        import calibration as _cal
        _cal_v = {h: _cal.verdict(h) for h in ("gloria", "self")}
    except Exception as _ce:
        _cal_v = {h: {"state": "INSUFFICIENT", "why": "calibration module unavailable: %s" % str(_ce)[:60]} for h in ("gloria", "self")}
    try:
        _ck_id = loaded_checkpoint
    except Exception:
        _ck_id = None
    out = {"source": "jepa",
           "prediction_id": "JP-" + __import__("uuid").uuid4().hex[:8],
           "predicted_at": __import__("datetime").datetime.now().isoformat(),
           "context_id": _context_id,           # which exchange window this forecast is about
           "context_last_event": (turns[-1].get("event_id") if turns else None),
           "checkpoint_id": _ck_id,
           "qualification": {"gloria": _qual(_cg), "self": _qual(_cs), "presence": _qual(_cp)},
           "steering_allowed": (False if shadow else all(v.get("state") == "RELEASED" for v in _cal_v.values())),
           "calibration": _cal_v,   # per head: RELEASED / WITHHELD / INSUFFICIENT, with the numbers and the criteria version
           # backward-compatible top-level = the gloria triple (gloria_prediction + latent read these)
           "confidence": gloria["confidence"], "novelty": gloria["novelty"],
           "gloria_forecast_nearest": gloria["nearest"],
           "gloria": gloria, "self": self_h, "presence": presence,
           "variance_qualified": (_cg is not None),
           "empirical_calibration": ("RELEASED under " + _cal_v["gloria"].get("criteria_version", "?")) if all(v.get("state") == "RELEASED" for v in _cal_v.values()) else "UNVERIFIED - variance gate passed is NOT calibration; see jepa-calibration.json when the audit has >=30 held-out predictions (Vrika, 2026-08-10)",
           "context_schema": _schema, "architecture": ck.get("architecture", "shared-v1"),
           "shadow_only": bool(shadow),
           "note": "embedding prediction; confidence = trained logvar (Vrika repair 2026-08-10); decode_similarity = nearest-turn cosine, NOT confidence; shadow checkpoints may never steer"}
    out["gloria_latest_turn"] = next((str(t.get("content","")) for t in reversed(turns) if t.get("role") == "user"), "")[:200]
    try:   # _srcs was train()-local: every predict raised NameError here before the forecast was saved (review P05)
        out["training_sources"] = (ck.get("training_sources") if isinstance(ck, dict) else None) or training_sources(turns)
    except Exception as _tse:
        out["training_sources"] = {"unavailable": str(_tse)[:80]}
    json.dump(out, open(out_path, "w"), indent=2)
    # calibration ledger: one line per prediction, BOTH signals (repaired logvar-relative confidence
    # AND legacy decode_similarity) plus raw predicted embeddings, so the audit can test which one -
    # if either - actually predicts realized error. Variance is not calibration.
    try:
        import time as _ht
        hist_line = {"checkpoint_id": _ck_id, "ts": _ht.time(), "iso": __import__("datetime").datetime.now().isoformat(),
                     "prediction_id": out["prediction_id"], "context_id": out["context_id"],
                     "context_last_event": out["context_last_event"],
                     "context_schema": _schema,
                     "context_emb": [round(float(x), 4) for x in xe[0]],
                     "gloria": {"confidence": gloria["confidence"], "decode_similarity": gloria["decode_similarity"],
                                "novelty": gloria["novelty"], "emb": [round(float(x), 4) for x in g]},
                     "self": {"confidence": self_h["confidence"], "decode_similarity": self_h["decode_similarity"],
                              "novelty": self_h["novelty"], "emb": [round(float(x), 4) for x in s]},
                     "variance_qualified": (_cg is not None)}
        _hp = history_path or os.path.join(MEMORY, "jepa-prediction-history.jsonl")
        open(_hp, "a").write(json.dumps(hist_line) + "\n")
    except Exception as _he:
        log(f"history append failed: {_he}")
    log(f"gloria conf {gloria['confidence']} nov {gloria['novelty']} | self conf {self_h['confidence']} nov {self_h['novelty']}"
        + (f" | presence pred {presence['predicted']} conf {presence['confidence']}" if presence else " | presence n/a"))
    log(f"latest gloria turn:  {out['gloria_latest_turn'][:80]}")
    log(f"nearest gloria-forecast: {gloria['nearest'][:80]}")
    return out

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "train"
    if cmd == "train": train()
    elif cmd == "train-force": train(force=True)
    elif cmd == "predict": predict()
    elif cmd == "train-shadow": train(SHADOW_MODEL, "structured-turns-v1", "head-specific-confidence-v2", validation_fraction=0.2)
    elif cmd == "train-shadow-force": train(SHADOW_MODEL, "structured-turns-v1", "head-specific-confidence-v2", validation_fraction=0.2, force=True)
    elif cmd == "predict-shadow": predict(SHADOW_MODEL, SHADOW_OUT, SHADOW_HISTORY, shadow=True)
    else: print("usage: jepa_predictor.py train|train-force|predict|train-shadow|train-shadow-force|predict-shadow")

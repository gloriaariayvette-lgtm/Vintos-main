#!/usr/bin/env python3
"""jepa_predictor.py — JEPA-lite over conversation embeddings. THREE heads, one trunk.

FROZEN encoder (nomic-embed) -> shared trunk -> three heads, each emitting the full
triple (prediction + confidence + novelty), per Gloria's architecture note:
  gloria   : predicts the EMBEDDING of Gloria's next turn
  self     : predicts the EMBEDDING of Vintos's own next turn. predict() takes this triple from
             jepa_self_head.py (his replies, forecast-time context; mode "ahead") once that head is
             trained; the shared-trunk self head here is kept as the fallback until then. The head's
             on-message forecasts (her message arrived, his reply not yet) are its own, launched by the
             server, and never touch this file's outputs.
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
PRESENCE_CALIBRATION = os.path.join(MEMORY, "jepa-presence-calibration.json")
SHADOW_RANKING_AUDIT = os.path.join(MEMORY, "jepa-ranking-structured-shadow.json")
CTX_TURNS = 6
MIN_PRESENCE_PAIRS = 6
MIN_PRESENCE_HOLDOUT = 10   # audited replies said AFTER the checkpoint before presence may steer
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
    comp = {a.get("id"): a.get("composite") for a in presence_records()
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


def presence_records():
    """The recent display rolls; calibration labels must outlive that display."""
    from jepa_ranking_audit import _jsonl
    rows = _jsonl(os.path.join(os.path.dirname(AUDIT), "presence-audit-history.jsonl"))
    rows += load(AUDIT, [])
    return list({r["id"]: r for r in rows if isinstance(r, dict) and r.get("id")}.values())

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
                "presence_baseline": ({"mean": float(yptr.mean()), "n": len(yptr),
                                       "source": "actual_training_labels"} if Xptr is not None else None),
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

def _within_training_window(first_ts, target_ts):
    """The rule build_pairs trains under, for prediction-side use by the self and presence heads only:
    a window whose first turn is more than a day from its target was never a training example.
    (build_pairs keeps its own copy; the gloria head's training is not touched from here.)"""
    try:
        from datetime import date
        a, b = str(first_ts or "")[:10], str(target_ts or "")[:10]
        if a and b and a != b and abs((date.fromisoformat(b) - date.fromisoformat(a)).days) > 1:
            return False
    except Exception:
        pass
    return True


def _epoch(ts):
    """Seconds for a stored time; a naive one is local on this host, as datetime.now() wrote it."""
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _write_json(path, obj):
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def presence_holdout_audit(net, enc, schema, trained_at, checkpoint_id, turns=None, out_path=None, baseline=None):
    """The presence head's evidence, which it never had: the replies audited AFTER this checkpoint was
    trained are a holdout it cannot have seen. Its error on them is compared with the baseline that
    predicts the mean of the training-era composites. It may steer only when it beats that mean on at
    least MIN_PRESENCE_HOLDOUT held-out replies (RELEASED); otherwise WITHHELD or INSUFFICIENT.
    Training is untouched: this reads the checkpoint and the audit file, nothing else."""
    import numpy as np, torch
    rec = {"head": "presence", "checkpoint": checkpoint_id, "protocol": "prospective-checkpoint-v1",
           "baseline": "mean of training-era composites", "minimum_holdout": MIN_PRESENCE_HOLDOUT}
    try:
        turns = training_turns() if turns is None else turns
        comp = {a.get("id"): a.get("composite") for a in presence_records()
                if isinstance(a, dict) and a.get("id") and a.get("composite") is not None}
        train_y, hold, seen = [], [], set()
        for i in range(CTX_TURNS, len(turns)):
            t = turns[i]
            if t.get("role") != "assistant": continue
            rid = _rid(t)
            if rid not in comp or rid in seen: continue
            seen.add(rid)
            at = _epoch(t.get("timestamp"))
            if at is None: continue
            if at <= trained_at:
                train_y.append(float(comp[rid]))
            else:
                hold.append((format_context(turns[i - CTX_TURNS:i], schema), float(comp[rid]), str(t.get("timestamp"))))
        rec.update({"n_training_era": len(train_y), "n_holdout": len(hold)})
        frozen = (isinstance(baseline, dict) and baseline.get("source") == "actual_training_labels"
                  and isinstance(baseline.get("mean"), (int, float)) and np.isfinite(baseline["mean"])
                  and 0 <= baseline["mean"] <= 1 and baseline.get("n", 0) >= MIN_PRESENCE_PAIRS)
        if frozen:
            rec.update(n_training_era=baseline["n"], baseline_source="checkpoint_training_labels")
        if not frozen and len(train_y) < MIN_PRESENCE_PAIRS:
            rec.update({"state": "INSUFFICIENT", "why": "too few training-era composites for a baseline"})
        elif len(hold) < MIN_PRESENCE_HOLDOUT:
            rec.update({"state": "INSUFFICIENT",
                        "why": "%d held-out audited replies; %d needed" % (len(hold), MIN_PRESENCE_HOLDOUT)})
        else:
            X = np.asarray(enc.encode([c for c, _, _ in hold], show_progress_bar=False), dtype="float32")
            with torch.no_grad():
                _, _, pp, plv = net(torch.tensor(X))
            pred = np.asarray(pp).reshape(-1)
            y = np.asarray([v for _, v, _ in hold], dtype="float32")
            base = float(baseline["mean"] if frozen else np.mean(train_y))
            mae_head = float(np.mean(np.abs(pred - y)))
            mae_base = float(np.mean(np.abs(base - y)))
            err = np.abs(pred - y); lvp = np.asarray(plv)[:, 2]
            def _rk(v): return np.argsort(np.argsort(v)).astype(float)
            mono = (round(float(np.corrcoef(_rk(lvp), _rk(err))[0, 1]), 3)
                    if np.std(lvp) > 0 and np.std(err) > 0 else None)
            rec.update({"baseline_mean": round(base, 4), "mae_head": round(mae_head, 4),
                        "mae_baseline": round(mae_base, 4),
                        "logvar_vs_error_spearman": mono,   # want positive: wider variance, bigger miss
                        "state": "RELEASED" if mae_head < mae_base else "WITHHELD",
                        "why": ("beats the mean baseline on the holdout" if mae_head < mae_base
                                else "does not beat predicting the mean on the holdout")})
    except Exception as e:
        rec.update({"state": "INSUFFICIENT", "why": "audit failed: %s" % str(e)[:120]})
    try:
        from datetime import datetime
        rec["at"] = datetime.now().isoformat()
        if out_path:
            _write_json(out_path, rec)
    except Exception as e:
        log(f"presence audit not written: {e}")
    return rec


def _conf(lv):
    import numpy as np
    lv = max(-6.0, min(6.0, float(lv)))
    return round(1.0 / (1.0 + float(np.exp(lv))), 3)   # tight variance -> high confidence

def predict(model_path=MODEL, out_path=OUT, history_path=None, shadow=False):
    import numpy as np, torch
    # This scheduled job also advances the optional stream when chat is unchanged.
    # Failure adds no evidence and never prevents the original head forecast.
    if not shadow:
        try:
            from latent_feed import refresh
            refresh(memory=MEMORY)
        except Exception as exc:
            log("additive latent context unavailable: %s" % type(exc).__name__)
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
    _readout_identity = ""
    if not shadow:
        for _name in ("gloria", "self_ahead"):
            _rp = os.path.join(MEMORY, "jepa-readouts", _name + ".npz")
            if os.path.exists(_rp):
                _readout_identity += hashlib.sha256(open(_rp, "rb").read()).hexdigest()
    _context_id = hashlib.md5((ctx + _readout_identity).encode()).hexdigest()[:12]
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
    # self/presence only: their baseline is drawn from windows their training would have accepted
    # (no window straddling more than a day), and the live window must be one too. The gloria
    # head's baseline (_lv_mean/_lv_std) is left exactly as it was.
    _cal_ok = [_within_training_window(turns[i - CTX_TURNS].get("timestamp"), turns[i].get("timestamp"))
               for i in range(CTX_TURNS, len(turns))][-40:]
    _lv_mean_sp = _lv_std_sp = None
    if len(_cal_ctx) >= 12:
        _xc = np.asarray(enc.encode(_cal_ctx, show_progress_bar=False), dtype="float32")
        with torch.no_grad():
            _, _, _, _lvb = net(torch.tensor(_xc))
        _lvb = _lvb.numpy()
        _lv_mean = _lvb.mean(axis=0); _lv_std = _lvb.std(axis=0)
        _mask = np.asarray(_cal_ok[-len(_lvb):], dtype=bool)
        if int(_mask.sum()) >= 12:
            _lv_mean_sp = _lvb[_mask].mean(axis=0); _lv_std_sp = _lvb[_mask].std(axis=0)
    from datetime import date as _date
    _live_in_window = _within_training_window(turns[-CTX_TURNS:][0].get("timestamp"), _date.today().isoformat())
    def _relconf(i):
        if _lv_mean is None or float(_lv_std[i]) < 0.02:
            return None
        import math as _m
        return round(1.0 / (1.0 + _m.exp((float(lv[i]) - float(_lv_mean[i])) / max(float(_lv_std[i]), 0.05))), 3)
    def _relconf_sp(i):
        if not _live_in_window or _lv_mean_sp is None or float(_lv_std_sp[i]) < 0.02:
            return None
        import math as _m
        return round(1.0 / (1.0 + _m.exp((float(lv[i]) - float(_lv_mean_sp[i])) / max(float(_lv_std_sp[i]), 0.05))), 3)
    def _qual_sp(c):
        if c is not None: return "qualified"
        if not _live_in_window: return "outside_training_window"
        if _lv_mean_sp is None: return "unavailable"
        return "unqualified_spreadless"
    _cg = _relconf(0)
    _cs, _cp = _relconf_sp(1), _relconf_sp(2)
    # The SELF triple comes from its own head (jepa_self_head.py: his ledger replies, forecast-time context,
    # his own recent replies) once that head has a checkpoint; until then the shared-trunk self above stands
    # exactly as it was. Nothing the gloria head reads or writes is touched here. Shadow keeps its own.
    _legacy_g, _legacy_cg = g.copy(), _cg
    _legacy_s, _legacy_cs = s.copy(), _cs
    _gloria_fc = None
    if not shadow:
        try:
            from jepa_readout import forecast as _readout_forecast
            _gloria_fc = _readout_forecast(enc, "gloria")
            if _gloria_fc is not None:
                g = np.asarray(_gloria_fc["emb"], dtype="float32"); _cg = _gloria_fc["confidence"]
        except Exception as exc:
            log("anchored Gloria unavailable; shared head retained: %s" % exc)
    _self_fc = None
    if not shadow:
        try:
            import jepa_self_head as _SH
            _self_fc = _SH.forecast(enc)
        except Exception as _sfe:
            log(f"self head unavailable; shared-trunk self kept: {_sfe}")
    _self_qual = _qual_sp(_cs)
    if _self_fc is not None:
        s = np.asarray(_self_fc["emb"], dtype="float32"); _cs = _self_fc["confidence"]; _self_qual = _self_fc["qualification"]

    gloria_turns = [t for t in turns if t.get("role") == "user"][-12:]
    self_turns   = [t for t in turns if t.get("role") == "assistant"][-12:]
    _g_near, _g_sim = _decode(g, gloria_turns, enc)
    _s_near, _s_sim = _decode(s, self_turns, enc)
    gloria = {"nearest": _g_near,
              "confidence": (_cg if _cg is not None else 0.5), "decode_similarity": _g_sim,
              "novelty": round(1.0 - max(0.0, _cos(g, xe[0])), 3)}
    if _gloria_fc is not None:
        gloria.update({k: _gloria_fc[k] for k in ("source", "checkpoint_id", "confidence_evaluation")})
    # presence confidence is null, never a placeholder 0.5, when it is not qualified. Self keeps the
    # 0.5 stand-in for now, MARKED as one: emoclaw_utils._novelty_directive does float() on it
    # unguarded and the calibration audit ranks it beside gloria's, so a null would break both.
    self_h = {"nearest": _s_near,
              "confidence": (_cs if _cs is not None else 0.5), "confidence_placeholder": _cs is None,
              "decode_similarity": _s_sim,
              "novelty": round(1.0 - max(0.0, _cos(s, xe[0])), 3)}
    if _self_fc is not None:
        self_h.update({"source": _self_fc["source"], "checkpoint_id": _self_fc["checkpoint_id"],
                       "context_last_ts": _self_fc["context_last_ts"], "coherence": _self_fc["coherence"],
                       "mode": _self_fc.get("mode", "ahead")})   # ahead: before her next message exists

    _pid = "JP-" + __import__("uuid").uuid4().hex[:8]
    _pat = __import__("datetime").datetime.now().isoformat()
    presence = presence_forecast = presence_cal = None
    if ck.get("presence_trained"):
        recent = [a.get("composite") for a in load(AUDIT, [])[-10:] if isinstance(a, dict) and a.get("composite") is not None]
        base = (sum(recent) / len(recent)) if recent else p
        if shadow:
            presence_cal = {"head": "presence", "state": "SHADOW", "why": "shadow checkpoints may never steer"}
        else:
            presence_cal = presence_holdout_audit(net, enc, _schema, os.path.getmtime(model_path), loaded_checkpoint,
                                                  out_path=PRESENCE_CALIBRATION, baseline=ck.get("presence_baseline"))
        _p_steer = (not shadow) and presence_cal.get("state") == "RELEASED"
        presence_forecast = {"predicted": round(p, 3), "confidence": _cp,
                             "novelty": round(min(1.0, abs(p - base)), 3),
                             "qualification": _qual_sp(_cp), "calibration": presence_cal.get("state"),
                             "steering_allowed": _p_steer,
                             "prediction_id": _pid, "predicted_at": _pat, "checkpoint_id": loaded_checkpoint}
        # `presence` is what the live loop reads (presence_audit -> forecast_block). Until the head beats
        # the mean on held-out replies it is not offered there; the forecast stays on record beside it.
        presence = presence_forecast if _p_steer else None

    if not shadow:
        try:
            from jepa_readout import presence_forecast as _readout_presence
            _pr = _readout_presence(enc)
            if _pr is not None:
                _pr.update(prediction_id=_pid, predicted_at=_pat)
                presence = presence_forecast = _pr
                presence_cal = _pr["evaluation"]
        except Exception as exc:
            log("anchored presence unavailable; existing presence retained: %s" % exc)

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
           "prediction_id": _pid,
           "predicted_at": _pat,
           "context_id": _context_id,           # which exchange window this forecast is about
           "context_last_event": (turns[-1].get("event_id") if turns else None),
           "checkpoint_id": _ck_id,
           "qualification": {"gloria": _qual(_cg), "self": _self_qual, "presence": _qual_sp(_cp)},
           "steering_allowed": (False if shadow else all(v.get("state") == "RELEASED" for v in _cal_v.values())),
           "calibration": _cal_v,   # per head: RELEASED / WITHHELD / INSUFFICIENT, with the numbers and the criteria version
           # backward-compatible top-level = the gloria triple (gloria_prediction + latent read these)
           "confidence": gloria["confidence"], "novelty": gloria["novelty"],
           "gloria_forecast_nearest": gloria["nearest"],
           "gloria": gloria, "self": self_h, "presence": presence,
           "presence_forecast": presence_forecast, "presence_calibration": presence_cal,
           "variance_qualified": (_cg is not None),
           "empirical_calibration": ("RELEASED under " + _cal_v["gloria"].get("criteria_version", "?")) if all(v.get("state") == "RELEASED" for v in _cal_v.values()) else "UNVERIFIED - variance gate passed is NOT calibration; see jepa-calibration.json when the audit has >=30 held-out predictions (Vrika, 2026-08-10)",
           "context_schema": _schema, "architecture": ck.get("architecture", "shared-v1"),
           "shadow_only": bool(shadow),
           "note": "embedding prediction; confidence = trained logvar (Vrika repair 2026-08-10); decode_similarity = nearest-turn cosine, NOT confidence; shadow checkpoints may never steer"}
    if _gloria_fc is not None:
        # These fields feed the existing prose/readiness path. Confidence retains
        # its independently evaluated error meaning; its receipt is observable.
        out["readout_calibration"] = _gloria_fc["confidence_evaluation"]
        out["steering_allowed"] = not shadow
        out["note"] = "anchored readout; confidence = 1 - estimated cosine error / 2"
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
                     "gloria": {"confidence": gloria["confidence"], "confidence_placeholder": _cg is None,
                                "decode_similarity": gloria["decode_similarity"],
                                "novelty": gloria["novelty"], "emb": [round(float(x), 4) for x in g]},
                     "self": {"confidence": self_h["confidence"], "confidence_placeholder": self_h["confidence_placeholder"],
                              "decode_similarity": self_h["decode_similarity"],
                              "novelty": self_h["novelty"], "emb": [round(float(x), 4) for x in s]},
                     "variance_qualified": (_cg is not None)}
        if _gloria_fc is not None:
            hist_line["gloria"].update({k: _gloria_fc[k] for k in ("source", "checkpoint_id")})
            _lg_near, _lg_sim = _decode(_legacy_g, gloria_turns, enc)
            hist_line["legacy_gloria"] = {"checkpoint_id": _ck_id, "confidence": _legacy_cg,
                "confidence_placeholder": _legacy_cg is None, "decode_similarity": _lg_sim,
                "emb": [round(float(x), 4) for x in _legacy_g]}
        if _self_fc is not None:   # what the self eval needs to find the reply this forecast is about
            hist_line["self"].update({k: self_h[k] for k in ("source", "checkpoint_id", "context_last_ts", "mode")})
        # Preserve a separately attributed shared-head forecast even while the
        # independent self head supplies the visible triple. Otherwise replacing
        # self silently stops collection for the shared checkpoint's retrain gate.
        _legacy_near, _legacy_sim = _decode(_legacy_s, self_turns, enc)
        hist_line["legacy_self"] = {"checkpoint_id": _ck_id, "confidence": _legacy_cs,
                                    "confidence_placeholder": _legacy_cs is None,
                                    "decode_similarity": _legacy_sim,
                                    "emb": [round(float(x), 4) for x in _legacy_s]}
        _hp = history_path or os.path.join(MEMORY, "jepa-prediction-history.jsonl")
        open(_hp, "a").write(json.dumps(hist_line) + "\n")
    except Exception as _he:
        log(f"history append failed: {_he}")
    if not shadow and os.path.exists(os.path.join(MEMORY, "jepa-readouts", "lam-linear.npz")):
        try:
            import lam
            lam.predict(enc=enc)
        except Exception as exc:
            log("fixed-horizon cascade unavailable: %s" % exc)
    log(f"gloria conf {gloria['confidence']} nov {gloria['novelty']} | self conf {self_h['confidence']} nov {self_h['novelty']}"
        + (f" | presence pred {presence_forecast['predicted']} conf {presence_forecast['confidence']} "
           f"[{presence_forecast['calibration']}, steers={presence_forecast['steering_allowed']}]" if presence_forecast else " | presence n/a"))
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

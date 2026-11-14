"""JEPA test-time-training replay (offline, copies only, counts only; never prints text).

Data: admitted exchanges (jepa_self_head.exchanges) strictly before 2026-10-31 00:00 local (the sealed
persistence week and everything after it is dropped before anything is encoded). Rows: R1's population:
exchanges with her words after the live checkpoint's training time, one per distinct Gloria text, input the
six turns before the exchange in the legacy schema, one-day rule as in build_pairs, window ends on his reply.
Each step: forecast (prediction + confidence), reveal the target, then (TTT variants) update.
Scoring uses jepa_ranking_audit.evaluate/_summary and jepa_calibration_audit.joined_rows/spear unchanged.
"""
import os, sys, json, time, copy, hashlib
from datetime import datetime

WT = os.path.expanduser("~/review-scratch-20261114-jepa-ttt/wt/scripts")
sys.path.insert(0, WT)
SCR = os.path.expanduser("~/review-scratch-20261114-jepa-ttt")
CKPT = os.path.join(SCR, "copies", "jepa-predictor.pt")          # byte copy of the live checkpoint
CUTOFF = datetime(2026, 10, 31, 0, 0).timestamp()
CTX = 6

import numpy as np
import torch


class CachedEncoder:
    def __init__(self, enc):
        self.enc, self.cache = enc, {}

    def encode(self, texts, show_progress_bar=False):
        miss = list(dict.fromkeys(t for t in texts if t not in self.cache))
        if miss:
            vs = self.enc.encode(miss, show_progress_bar=False, batch_size=32)
            self.cache.update(zip(miss, [np.asarray(v, dtype="float32") for v in vs]))
        return np.asarray([self.cache[t] for t in texts], dtype="float32")


def _flatten(exs):
    turns = []
    for x in exs:
        if x["her"]:
            turns.append({"role": "user", "content": x["her"], "timestamp": x["ts"]})
        if x["his"]:
            turns.append({"role": "assistant", "content": x["his"], "timestamp": x["ts"]})
    return turns


def build(trained_at):
    import jepa_self_head as SH
    import jepa_predictor as JP
    exs = [x for x in SH.exchanges() if x["at"] < CUTOFF]
    rows, seen, pre = [], set(), []
    for j, x in enumerate(exs):
        if not x["her"]:
            continue
        turns = _flatten(exs[:j])
        if len(turns) < CTX:
            continue
        win = turns[-CTX:]
        if not JP._within_training_window(win[0]["timestamp"], x["ts"]):
            continue
        if win[-1]["role"] != "assistant":
            continue
        d = hashlib.sha256(x["her"].encode()).hexdigest()
        if d in seen:
            continue
        seen.add(d)
        her_past = [t["content"] for t in turns if t["role"] == "user"][-12:]
        r = {"at": x["at"], "ts": x["ts"], "ctx": JP.format_context(win), "target": x["her"], "her_past": her_past}
        (rows if x["at"] > trained_at else pre).append(r)
    ledger = [{"timestamp": x["ts"], "gloria": x["her"], "vintos": x["his"]} for x in exs]
    turns3 = sorted(((x["at"], x["her"], x["his"]) for x in exs), key=lambda t: t[0])
    return rows, pre, ledger, turns3


def load_net(path=CKPT):
    import jepa_predictor as JP
    ck = torch.load(path, map_location="cpu")
    net = JP.make_net(ck["dim"], architecture=ck.get("architecture", "shared-v1"))
    net.load_state_dict(ck["state"]); net.eval()
    return net


def _cos(a, b):
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return float(a @ b / (na * nb)) if na and nb else 0.0


# ----------------------------------------------------------------------------- the online learner
class Learner:
    """kind: frozen | readout | readout_anchor | logvar_only | ridge_conf"""

    def __init__(self, net, kind, lr=0.0, lam=0.0, buffer=1, steps=1, fisher=None, ridge_lam=1.0, warm=8):
        self.net, self.kind, self.lr, self.lam = net, kind, lr, lam
        self.buffer_k, self.steps, self.ridge_lam, self.warm = buffer, steps, ridge_lam, warm
        self.buf, self.feat_hist, self.trace = [], [], []
        self.update_ms, self.n_updates, self.max_drift = [], 0, 0.0
        self.params = []
        if kind in ("readout", "readout_anchor"):
            self.params = [net.head[0].weight, net.head[0].bias, net.logvar.weight, net.logvar.bias]
        elif kind == "logvar_only":
            self.params = [net.logvar.weight, net.logvar.bias]
        for p in net.parameters():
            p.requires_grad_(False)
        for p in self.params:
            p.requires_grad_(True)
        self.theta0 = [p.detach().clone() for p in self.params]
        self.fisher = fisher
        self.opt = torch.optim.Adam(self.params, lr=lr) if self.params else None
        # only the Gloria row (0) of the shared logvar layer may move: self/presence confidence untouched
        self.row_mask = {id(net.logvar.weight): (0, net.logvar.weight), id(net.logvar.bias): (0, net.logvar.bias)}

    def forecast(self, x):
        with torch.no_grad():
            g, _, _, lv = self.net(torch.tensor(x[None]))
        return g.numpy()[0], float(lv.numpy()[0][0])

    def conf(self, lvg, feats):
        if self.kind != "ridge_conf" or len(self.feat_hist) < self.warm:
            return -lvg
        F = np.asarray([f for f, _ in self.feat_hist]); e = np.asarray([e for _, e in self.feat_hist])
        mu, sd = F.mean(0), F.std(0) + 1e-6
        Z = np.column_stack([np.ones(len(F)), (F - mu) / sd])
        P = np.eye(Z.shape[1]) * self.ridge_lam; P[0, 0] = 0
        w = np.linalg.solve(Z.T @ Z + P, Z.T @ e)
        z = np.concatenate([[1.0], (np.asarray(feats) - mu) / sd])
        return -float(z @ w)

    def _drift(self):
        num = sum(float(((p.detach() - t) ** 2).sum()) for p, t in zip(self.params, self.theta0))
        den = sum(float((t ** 2).sum()) for t in self.theta0)
        return (num / den) ** 0.5 if den else 0.0

    def observe(self, x, y, feats, err):
        if self.kind == "ridge_conf":
            t0 = time.perf_counter(); self.feat_hist.append((feats, err))
            self.update_ms.append((time.perf_counter() - t0) * 1000); self.n_updates += 1
            return
        if not self.params:
            return
        self.buf.append((x, y)); self.buf = self.buf[-self.buffer_k:]
        t0 = time.perf_counter()
        X = torch.tensor(np.asarray([b[0] for b in self.buf])); Y = torch.tensor(np.asarray([b[1] for b in self.buf]))
        for _ in range(self.steps):
            self.opt.zero_grad()
            g, _, _, lv = self.net(X)
            mse = ((g - Y) ** 2).mean(dim=1, keepdim=True); l = lv[:, 0:1]
            loss = (mse * torch.exp(-l) + l).mean()
            if self.lam:
                pen = 0.0
                for i, (p, t) in enumerate(zip(self.params, self.theta0)):
                    f = self.fisher[i] if self.fisher is not None else 1.0
                    pen = pen + (f * (p - t) ** 2).sum()
                loss = loss + self.lam * pen
            if not torch.isfinite(loss):
                break
            loss.backward()
            for p in (self.net.logvar.weight, self.net.logvar.bias):
                if p.grad is not None:
                    keep = torch.zeros_like(p.grad); keep[0] = p.grad[0]; p.grad.copy_(keep)
            torch.nn.utils.clip_grad_norm_(self.params, 1.0)
            self.opt.step()
        self.update_ms.append((time.perf_counter() - t0) * 1000); self.n_updates += 1
        self.max_drift = max(self.max_drift, self._drift())
        self.trace.append(self.max_drift)


def fisher_from(net, Xp, Yp):
    """Diagonal Fisher of the Gloria NLL over the readout params, from pre-checkpoint pairs; mean-normalized."""
    params = [net.head[0].weight, net.head[0].bias, net.logvar.weight, net.logvar.bias]
    acc = [torch.zeros_like(p) for p in params]
    for p in params: p.requires_grad_(True)
    for i in range(len(Xp)):
        net.zero_grad()
        g, _, _, lv = net(torch.tensor(Xp[i:i + 1]))
        mse = ((g - torch.tensor(Yp[i:i + 1])) ** 2).mean(dim=1, keepdim=True); l = lv[:, 0:1]
        (mse * torch.exp(-l) + l).mean().backward()
        for a, p in zip(acc, params): a += p.grad.detach() ** 2
    acc = [a / max(1, len(Xp)) for a in acc]
    acc[2][1:] = 0; acc[3][1:] = 0
    m = float(sum(a.sum() for a in acc) / sum(a.numel() for a in acc))
    for p in params: p.requires_grad_(False)
    return [a / (m + 1e-12) for a in acc]


def replay(rows, enc, learner, ck_id="replay"):
    """Chronological: forecast -> reveal -> update. Returns synthetic history rows (audit format) + diagnostics."""
    X = enc.encode([r["ctx"] for r in rows]); Y = enc.encode([r["target"][:400] for r in rows])
    hist, preds = [], []
    for i, r in enumerate(rows):
        pred, lvg = learner.forecast(X[i])
        cands = enc.encode([t[:300] for t in r["her_past"]]) if r["her_past"] else np.zeros((0, len(pred)))
        dsim = round(max((_cos(pred, c) for c in cands), default=0.0), 3)
        nov = round(1.0 - max(0.0, _cos(pred, X[i])), 3)
        feats = [-lvg, dsim, nov]
        conf = learner.conf(lvg, feats)
        fts = r["at"] - 0.5
        hist.append({"checkpoint_id": ck_id, "ts": fts, "iso": datetime.fromtimestamp(fts).isoformat(),
                     "trigger": "replay", "context_last_role": "assistant",
                     "context_emb": [float(v) for v in X[i]],
                     "gloria": {"confidence": conf, "confidence_placeholder": False, "decode_similarity": dsim,
                                "emb": [float(v) for v in pred]}})
        preds.append(pred)
        err = 1.0 - _cos(pred, Y[i])
        learner.observe(X[i], Y[i], feats, err)      # the reveal: only now does the learner see the target
    return hist, np.asarray(preds)


def score(hist, ledger, turns3, enc, split_ts, preds=None):
    import jepa_ranking_audit as RA
    import jepa_calibration_audit as CA
    rk = RA.evaluate(hist, ledger, enc, checkpoint=hist[0]["checkpoint_id"], trained_before=0.0, arrivals={})
    rk = [r for r in rk if r["head"] == "gloria"]
    jr = CA.joined_rows(hist, turns3, enc, hist[0]["checkpoint_id"], 0.0, arrivals={})
    out = {}
    for name, sel in (("first", lambda t: t < split_ts), ("second", lambda t: t >= split_ts), ("all", lambda t: True)):
        rr = [r for r in rk if sel(r["target_ts"])]
        jj = [r for r in jr if r["g_err"] is not None and sel(float(r["ts"]) + 0.5)]
        s = RA._summary(rr, "gloria")
        c = [r["g_conf"] for r in jj]; e = [r["g_err"] for r in jj]; d = [r["g_dsim"] for r in jj]
        out[name] = {"n_rank": s.get("n"), "mrr": s.get("mean_reciprocal_rank"), "top1": s.get("top1_accuracy"),
                     "controls_mrr": {k: v["mrr"] for k, v in (s.get("baselines") or {}).items()},
                     "rank_state": s.get("state"), "ci95": s.get("paired_day_block_ci95"),
                     "n_conf": len(jj), "mono": CA.spear(c, e), "control_dsim": CA.spear(d, e),
                     "bins": CA.bins(c, e) if len(c) >= 3 else None,
                     "mean_err": round(float(np.mean(e)), 4) if e else None}
    if preds is not None:
        sec = preds[[i for i, h in enumerate(hist) if h["ts"] + 0.5 >= split_ts]]
        U = sec / np.linalg.norm(sec, axis=1, keepdims=True)
        S = U @ U.T; n = len(U)
        out["collapse_mean_pairwise_cos_second"] = round(float((S.sum() - n) / (n * (n - 1))), 4) if n > 1 else None
        out["finite"] = bool(np.all(np.isfinite(preds)))
    return out

#!/usr/bin/env python3
"""lam.py — Latent Action Model: the physics of his interior. JEPA grown up.

Learns the STATE-TRANSITION dynamics: given his emotional state now + what just happened (the turns
between two trajectory points, embedded), predict the next state. Once trained it forecasts CASCADES
— "given this event, his state rolls THIS way through the dimensions" — which feeds the Living
Trajectory daemon and turns cause/purpose/drift from snapshots into dynamics.

  train : build (state_t, event_embedding, state_{t+1}) triples from the dense trajectory + the turns
          in each interval; fit a small net [state ⊕ event] -> next_state.
  predict: forecast the next state from the latest state + latest event -> lam-forecast.json (which
          dims will move, and how).

DATA-GATED: needs a deep trajectory. With few points it learns little — it's built ready and sharpens
automatically as emotion_densifier grows the trajectory. Run with the torch venv. SPARK_WORKSPACE switches.
"""
import os, sys, json
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
CHAT = os.path.join(MEMORY, "chat-history-merged.json")
DENSE = os.path.join(MEMORY, "emotion-trajectory-dense.json")
MODEL = os.path.join(MEMORY, "lam.pt")
OUT = os.path.join(MEMORY, "lam-forecast.json")
DIMS = ["Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection",
        "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]
MIN_TRIPLES = 20          # below this, learning is noise — train but warn

def log(m): print("[lam]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
def parse_ts(x):
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def trajectory():
    t = load(DENSE, [])
    if not (isinstance(t, list) and len(t) >= 3):
        sys.path.insert(0, SCRIPTS)
        try:
            from causality_engine import load_emotional_trajectory
            t = load_emotional_trajectory()
        except Exception:
            t = []
    return [(parse_ts(p.get("t")), p.get("v")) for p in t if isinstance(p, dict) and p.get("v") and parse_ts(p.get("t"))]

def build_triples(enc):
    import numpy as np
    traj = trajectory()
    if len(traj) < 4:
        return None
    hist = [e for e in load(CHAT, []) if isinstance(e, dict) and e.get("content")]
    turns = [(parse_ts(e.get("timestamp")), str(e.get("content", ""))[:300]) for e in hist if parse_ts(e.get("timestamp"))]
    S, E, Snext = [], [], []
    for i in range(len(traj) - 1):
        (t0, v0), (t1, v1) = traj[i], traj[i + 1]
        between = " \n".join(txt for tt, txt in turns if t0 <= tt <= t1) or "(quiet — time passing, no exchange)"
        S.append(v0); Snext.append(v1); E.append(between)
    Emb = np.asarray(enc.encode(E, show_progress_bar=False), dtype="float32")
    return (np.asarray(S, dtype="float32"), Emb, np.asarray(Snext, dtype="float32"))

def make_net(edim):
    import torch.nn as nn
    return nn.Sequential(nn.Linear(11 + edim, 128), nn.GELU(), nn.Linear(128, 64), nn.GELU(), nn.Linear(64, 11))

def train():
    import numpy as np, torch
    sys.path.insert(0, SCRIPTS)
    from jepa_predictor import encoder
    enc = encoder()
    tr = build_triples(enc)
    if tr is None:
        log("trajectory too short to form triples — waiting on the densifier"); return
    S, E, Sn = tr
    n = len(S)
    log(f"triples: {n}" + ("  (below MIN — learning is weak until the trajectory deepens)" if n < MIN_TRIPLES else ""))
    X = torch.tensor(np.concatenate([S, E], axis=1)); Y = torch.tensor(Sn)
    net = make_net(E.shape[1])
    opt = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-3)
    lossf = torch.nn.SmoothL1Loss()
    for epoch in range(300):
        opt.zero_grad()
        loss = lossf(net(X), Y)
        if not torch.isfinite(loss): break
        loss.backward(); torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step()
        if epoch % 100 == 0: log(f"epoch {epoch} loss {loss.item():.4f}")
    torch.save({"state": net.state_dict(), "edim": E.shape[1]}, MODEL)
    log(f"saved {MODEL} (trained on {n} transitions)")

def predict():
    import numpy as np, torch
    if not os.path.exists(MODEL):
        log("no model — train first"); return
    sys.path.insert(0, SCRIPTS)
    from jepa_predictor import encoder
    enc = encoder()
    traj = trajectory()
    if not traj:
        log("no trajectory"); return
    cur = np.asarray(traj[-1][1], dtype="float32")
    hist = [e for e in load(CHAT, []) if isinstance(e, dict) and e.get("content")]
    ev = " \n".join(str(e.get("content", ""))[:300] for e in hist[-3:]) or "(quiet)"
    ee = np.asarray(enc.encode([ev], show_progress_bar=False), dtype="float32")[0]
    ck = torch.load(MODEL); net = make_net(ck["edim"]); net.load_state_dict(ck["state"]); net.eval()
    with torch.no_grad():
        nxt = net(torch.tensor(np.concatenate([cur, ee])[None, :])).numpy()[0]
    delta = nxt - cur
    order = sorted(range(11), key=lambda i: abs(delta[i]), reverse=True)
    moves = [{"dim": DIMS[i], "from": round(float(cur[i]), 3), "to": round(float(nxt[i]), 3),
              "delta": round(float(delta[i]), 3)} for i in order[:5]]
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "cascade": moves,
               "note": "predicted next-state cascade given the latest event (LAM dynamics)"},
              open(OUT, "w"), indent=2)
    log("forecast cascade: " + ", ".join(f"{m['dim']}{'+' if m['delta']>=0 else ''}{m['delta']}" for m in moves))

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "train"
    {"train": train, "predict": predict}.get(cmd, train)()

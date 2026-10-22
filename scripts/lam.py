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

def legacy_train():
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

def legacy_predict():
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

# Fixed-horizon causal readout. The original checkpoint remains a readable fallback.
HORIZON_SECONDS = 600
TOLERANCE_SECONDS = 120


def causal_rows(traj, exs, horizon=HORIZON_SECONDS):
    import bisect
    import numpy as np
    from jepa_readout import context
    traj=sorted((t,v) for t,v in traj if t is not None and len(v)==11)
    times=[t.timestamp() for t,v in traj]; ets=[e['at'] for e in exs]; out=[]
    for i,(t,v) in enumerate(traj[:-1]):
        j=bisect.bisect_left(times,t.timestamp()+horizon)
        if j==len(times) or times[j]-times[i]-horizon>TOLERANCE_SECONDS:continue
        cut=exs[:bisect.bisect_right(ets,times[i])]
        if not cut or not any(x['his'] for x in cut):continue
        row=context(cut,'self_ahead',now=times[i])
        row.update(state=np.asarray(v),trend=np.asarray(v)-np.asarray(traj[max(0,i-1)][1]),
                   target=np.asarray(traj[j][1]),day=t.astimezone().date().isoformat(),
                   at=times[i],target_at=times[j],actual_horizon=times[j]-times[i])
        out.append(row)
    return out


def train_readout(enc,exs,out):
    import numpy as np
    from pathlib import Path
    import jepa_readout as rr
    rows=causal_rows(trajectory(),exs)
    sp=np.asarray([rr.split(r['day']) for r in rows]);tr,va,ca,te=[np.flatnonzero(sp==k) for k in range(4)]
    if any(len(i)<3 for i in (tr,va,ca,te)):raise ValueError('LAM needs four chronological blocks')
    # A horizon crossing a split is not a training/calibration target from that split.
    for k in range(4):
        bad=[i for i in np.flatnonzero(sp==k) if rr.split(datetime.fromtimestamp(rows[i]['target_at']).date().isoformat())!=k]
        sp[bad]=-1
    tr,va,ca,te=[np.flatnonzero(sp==k) for k in range(4)]
    cr=[dict(r,target='') for r in rows]; a=rr.arrays(cr,rr.Embeddings(enc))
    states=np.asarray([r['state'] for r in rows]); target=np.asarray([r['target'] for r in rows]);trend=np.asarray([r['trend'] for r in rows])
    mu=states[tr].mean(0);sd=np.maximum(states[tr].std(0),.05)
    _,_,vt=np.linalg.svd(a[1][tr]-a[1][tr].mean(0),full_matrices=False); p=vt[:16].T
    h=np.concatenate([(states-mu)/sd,trend/sd,a[1]@p,a[2]@p,a[5]],axis=1)
    delta=(target-states)/sd; best=None
    for penalty in (1.,10.,100.,1000.,10000.):
        w=np.linalg.solve(h[tr].T@h[tr]+penalty*np.eye(h.shape[1]),h[tr].T@delta[tr])
        loss=np.mean(((h[va]@w-delta[va])*sd)**2)
        if best is None or loss<best[0]:best=(loss,w,penalty)
    w=best[1]; pred=states[te]+(h[te]@w)*sd
    # Calibration estimates per-axis forecast error on a separate block.
    calibration_rmse=np.sqrt(np.mean(((h[ca]@w-delta[ca])*sd)**2,axis=0))
    em=np.mean((pred-target[te])**2,axis=1); eb=np.mean((states[te]-target[te])**2,axis=1)
    result={'horizon_seconds':HORIZON_SECONDS,'tolerance_seconds':TOLERANCE_SECONDS,'n':len(rows),
            'blocks':{k:len(i) for k,i in zip(('train','validation','calibration','test'),(tr,va,ca,te))},'lambda':best[2],
            'test_mse':float(em.mean()),'persistence_mse':float(eb.mean()),
            'paired_day_mse_difference_ci95':rr.interval(em-eb,[rows[i]['day'] for i in te]),
            'per_axis_mse':dict(zip(DIMS,np.mean((pred-target[te])**2,axis=0).tolist())),
            'calibration_rmse':calibration_rmse.tolist()}
    np.savez_compressed(Path(out)/'lam-linear.npz',W=w,projection=p,mu=mu,sd=sd,calibration_rmse=calibration_rmse,meta=json.dumps(result))
    return result


def train():
    raise SystemExit('Use jepa_retrain.py --out <scratch-directory>; training never overwrites live checkpoints.')


def predict(enc=None, exs=None, model_path=None, out_path=None):
    import numpy as np
    from pathlib import Path
    import jepa_readout as rr
    import jepa_self_head as sh
    from jepa_predictor import encoder
    path=Path(model_path) if model_path else Path(MEMORY)/'jepa-readouts/lam-linear.npz'
    if not path.exists():return legacy_predict()
    enc=enc or encoder();exs=sh.exchanges() if exs is None else exs;traj=sorted(trajectory())
    if len(traj)<2 or not exs:return
    t,v=traj[-1];cut=[e for e in exs if e['at']<=t.timestamp()]
    if not cut:return
    a=rr.arrays([rr.context(cut,'self_ahead',now=t.timestamp())],rr.Embeddings(enc))
    with np.load(path,allow_pickle=False) as m:
        cur=np.asarray(v);trend=cur-np.asarray(traj[-2][1]);p=m['projection']
        h=np.concatenate([(cur-m['mu'])/m['sd'],trend/m['sd'],(a[1]@p)[0],(a[2]@p)[0],a[5][0]])
        nxt=cur+(h@m['W'])*m['sd'];uncertainty=m['calibration_rmse'].tolist()
    order=np.argsort(-abs(nxt-cur))[:5]
    moves=[{'dim':DIMS[i],'from':float(cur[i]),'to':float(nxt[i]),'delta':float(nxt[i]-cur[i])} for i in order]
    data={'generated_at':datetime.now(timezone.utc).isoformat(),'state_at':t.isoformat(),'horizon_seconds':HORIZON_SECONDS,
          'cascade':moves,'calibration_rmse':uncertainty,'note':'fixed-horizon forecast from information at state_at'}
    Path(out_path or OUT).write_text(json.dumps(data,indent=2))

if __name__=='__main__':
    {'train':train,'predict':predict}.get(sys.argv[1] if len(sys.argv)>1 else 'predict',predict)()

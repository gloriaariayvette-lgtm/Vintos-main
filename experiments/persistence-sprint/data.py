"""Numeric, causal sprint data contracts. No stores, providers or optional imports."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
import os
import numpy as np

TZ = ZoneInfo('America/Chicago')
SOURCES = ['emotion','inner','thread','creative','her','him','lab','watch','sensor','want','presence','dream']
HORIZONS = np.array([600,1800,3600,10800,21600,43200,86400])
ROUNDS = [(1,'2026-10-14','2026-10-16','2026-10-18'),
          (2,'2026-10-16','2026-10-18','2026-10-20'),
          (3,'2026-10-18','2026-10-20','2026-10-21'),
          (4,'2026-10-20','2026-10-21','2026-10-23')]


def timestamp(value):
    if isinstance(value,(float,int)):
        return float(value / 1000 if value > 1e12 else value)
    dt = datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=TZ)
    return dt.timestamp()


def boundary(day):
    return datetime.fromisoformat(day).replace(tzinfo=TZ).timestamp()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scratch(path, create=True):
    root=Path(os.environ['PERSISTENCE_SCRATCH']).resolve()
    out=Path(path).resolve()
    if '.vintos' in root.parts or out==root or not out.is_relative_to(root):
        raise ValueError('output must be strictly inside explicit private scratch')
    if create:out.mkdir(parents=True,exist_ok=False,mode=0o700)
    return out


def write_json(path,value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


def horizon_pairs(times, emotion, horizon, tolerance=None):
    """First actual reading after horizon; each realized target once per horizon.

    Endpoint matching is independent of any predicted value. Never interpolate
    suppressed or missing readings. Origin and outcome remain in one split.
    """
    tolerance=max(120,min(1800,horizon*.1)) if tolerance is None else tolerance
    ids=np.flatnonzero(emotion)
    et=times[ids]
    pairs=[];used=set()
    for k,i in enumerate(ids):
        q=int(np.searchsorted(et,et[k]+horizon))
        if q<len(ids) and et[q]<=et[k]+horizon+tolerance and int(ids[q]) not in used:
            pairs.append((int(i),int(ids[q])));used.add(int(ids[q]))
    return np.asarray(pairs,dtype=int).reshape(-1,2)


def split_pairs(pairs,times,start,end):
    if not len(pairs):return pairs
    mask=(times[pairs[:,0]]>=start)&(times[pairs[:,1]]<end)
    return pairs[mask]


def ridge(x,y,penalty=10.):
    return np.linalg.solve(x.T@x+np.eye(x.shape[1])*penalty,x.T@y)


def ranks(scores,positive):
    """Pessimistic ties, including identical candidate vectors."""
    return np.sum(scores>=scores[np.arange(len(scores)),positive,None],axis=1)


def features(t,source,emo,text,numeric,train_end):
    """Post-batch observations; all same-time members are folded atomically.

    Carried values have explicit age/missingness. Observed-time weighted history
    clips unsupported gaps rather than inventing unchanged measurements.
    """
    train=(t<train_end)&np.isfinite(emo).all(1)
    mu=emo[train].mean(0);sd=np.maximum(emo[train].std(0),.05)
    carried=mu.copy();last_text=np.zeros(text.shape[1]);last_emo=None;last_t=t[0]
    means=np.tile(mu,(3,1));mass=np.zeros(3)
    out=[];hist=[];last=[];seen=[]
    for i,at in enumerate(t):
        gap=max(0,at-last_t);last_t=at
        if np.isfinite(emo[i]).all():
            duration=min(at-last_emo,720) if last_emo is not None else 0
            weights=1-np.exp(-duration/np.array([1800,21600,86400]))
            means=(1-weights[:,None])*means+weights[:,None]*carried
            mass=(1-weights)*mass+weights
            carried=emo[i];last_emo=at
        if np.linalg.norm(text[i]):last_text=text[i]
        angle=2*np.pi*datetime.fromtimestamp(at,TZ).hour/24
        age=0 if last_emo is None else min((at-last_emo)/3600,72)
        present=np.r_[(carried-mu)/sd, source[i],numeric[i],np.sin(angle),np.cos(angle),
                      np.log1p(gap/60),age,float(last_emo is None),1.]
        history=np.r_[((carried-means)/sd).ravel(),mass]
        out.append(present);hist.append(history);last.append(last_text.copy());seen.append(carried.copy())
    return np.asarray(out,np.float32),np.asarray(hist,np.float32),np.asarray(last),np.asarray(seen),mu,sd


def projected_text(text,mask,train_end,t,width=32):
    x=text[mask&(t<train_end)]
    if len(x)<2:raise ValueError('insufficient training text')
    mu=x.mean(0)
    _,_,v=np.linalg.svd(x-mu,full_matrices=False)
    p=v[:min(width,len(v))].T
    z=(text-mu)@p
    z[~mask]=0
    return z.astype(np.float32),mu,p

#!/usr/bin/env python3
"""CPU anchored next-speaker readouts. Training writes exclusively to an explicit scratch output.
The input encoder stays frozen. Model choice, confidence fitting and evaluation use separate days.
Existing consumers keep their feeds; a compatible readout replaces the embedding and confidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime
import numpy as np

SCHEMA = 'anchored-readout-v1'
MODES = ('gloria', 'self_ahead', 'self_on_message')
BOUNDARIES = ('2026-10-01', '2026-10-09', '2026-10-13')


def units(a):
    a = np.asarray(a, dtype=float)
    return a / np.maximum(np.linalg.norm(a, axis=-1, keepdims=True), 1e-12)


def split(day, boundaries=BOUNDARIES):
    return sum(day >= b for b in boundaries)


def context(exs, mode, now=None, her=''):
    key = 'her' if mode == 'gloria' else 'his'
    other = 'his' if key == 'her' else 'her'
    own = [x[key][:400] for x in exs if x[key]][-6:]
    opp = [x[other][:400] for x in exs if x[other]][-6:]
    # Use the last observed event's clock, never the future target's clock.
    at = float(now if now is not None else exs[-1]['at'])
    return {'own': own, 'other': opp, 'now': her[:400] if mode == 'self_on_message' else '', 'at': at}


def samples(exs, mode):
    key = 'her' if mode == 'gloria' else 'his'
    out, seen = [], set()
    for i, x in enumerate(exs):
        text = x[key][:400]
        digest = hashlib.sha256(text.encode()).hexdigest()
        if not text or digest in seen or not any(z[key] for z in exs[:i]):
            continue
        seen.add(digest)
        c = context(exs[:i], mode, her=x['her'])
        # Exchange time is not a separate arrival timestamp. Do not invent one.
        c.update(target=text, day=x['ts'][:10], target_at=x['at'], target_id=digest)
        out.append(c)
    return out


class Embeddings:
    def __init__(self, enc):
        self.enc, self.bank = enc, {}

    def fill(self, rows):
        texts = list(dict.fromkeys(t for r in rows for t in r['own'] + r['other'] + [r.get('now',''), r.get('target','')] if t and t not in self.bank))
        if texts:
            vectors = units(self.enc.encode(texts, show_progress_bar=False))
            self.bank.update(zip(texts, vectors))
        self.dim = len(next(iter(self.bank.values())))

    def get(self, text):
        return self.bank[text] if text else np.zeros(self.dim)


def arrays(rows, cache):
    cache.fill(rows)
    last, mean, other, om, now, clocks = [], [], [], [], [], []
    for r in rows:
        last.append(cache.get(r['own'][-1]))
        mean.append(units(np.mean([cache.get(t) for t in r['own']], axis=0)))
        other.append(cache.get(r['other'][-1]) if r['other'] else np.zeros(cache.dim))
        om.append(units(np.mean([cache.get(t) for t in r['other']], axis=0)) if r['other'] else np.zeros(cache.dim))
        now.append(cache.get(r['now']))
        d = datetime.fromtimestamp(r['at']); angle = 2*np.pi*(d.hour+d.minute/60)/24
        clocks.append([np.sin(angle),np.cos(angle),1.])
    return [np.asarray(x) for x in (last,mean,other,om,now,clocks)]


def features(a, p):
    return np.concatenate([v @ p for v in a[:5]]+[a[5]],axis=1)


def predict(model, a):
    h = features(a, model['projection'])
    raw = model['beta'] * a[0] + model['gamma'] * a[1]
    raw += (h @ model['W'].T + model['bias']) @ model['projection'].T
    return units(raw)


def metrics(pred, y):
    scores = pred @ y.T
    ranks = np.sum(scores >= np.diag(scores)[:,None]-1e-12, axis=1)
    err = 1-np.sum(pred*y,axis=1)
    return {'n':len(y),'cosine_error':float(err.mean()),'mrr':float(np.mean(1/ranks)),
            'top1':float(np.mean(ranks==1))}, err, 1/ranks


def interval(values, days):
    blocks = [np.asarray(values)[np.asarray(days)==d] for d in sorted(set(days))]
    rng=np.random.default_rng(20261022)
    means=[np.concatenate([blocks[i] for i in rng.integers(0,len(blocks),len(blocks))]).mean() for _ in range(2000)]
    return np.quantile(means,[.025,.975]).tolist()


def confidence_features(pred, a):
    # All features exist at prediction time; no candidate or target information.
    return np.column_stack([np.ones(len(pred)),np.sum(pred*a[0],axis=1),np.sum(pred*a[1],axis=1),
                            np.sum(a[0]*a[1],axis=1),np.sum(a[2]*a[3],axis=1)])


def fit_confidence(pred, a, y):
    x=confidence_features(pred,a); err=1-np.sum(pred*y,axis=1)
    penalty=np.eye(x.shape[1])*10.; penalty[0,0]=0
    return np.linalg.solve(x.T@x+penalty,x.T@err)


def confidence(model,pred,a):
    return np.clip(1-confidence_features(pred,a)@model['confidence_W']/2,0,1)


def _ranks(v):
    """Average ranks, ties shared, as scipy.stats.rankdata (scipy is not on every interpreter that runs the suite)."""
    v=np.asarray(v,dtype=float); order=np.argsort(v,kind='mergesort'); r=np.empty(len(v)); i=0
    while i<len(v):
        j=i
        while j+1<len(v) and v[order[j+1]]==v[order[i]]:j+=1
        r[order[i:j+1]]=(i+j)/2.0; i=j+1
    return r


def correlation(x,y):
    if len(x)<3 or np.std(x)<1e-10 or np.std(y)<1e-10:return None
    return float(np.corrcoef(_ranks(x),_ranks(y))[0,1])


def train_mode(rows, cache, mode, out, old=None, steps=200):
    a=arrays(rows,cache); y=np.asarray([cache.get(r['target']) for r in rows])
    sp=np.asarray([split(r['day']) for r in rows]); ids=[np.flatnonzero(sp==k) for k in range(4)]
    if any(len(i)<3 for i in ids):raise ValueError('each chronological block needs >=3 targets: '+str([len(i) for i in ids]))
    tr,va,ca,te=ids; candidates=[]
    from latent_stream_linear import fit_text
    for dz in (16,32):
        _,_,vt=np.linalg.svd(y[tr]-y[tr].mean(0),full_matrices=False); p=vt[:min(dz,len(tr)-1)].T
        h=features(a,p)
        for beta in (0.,.25,.5,.75,1.):
            base={'projection':p,'beta':beta,'gamma':1-beta,'W':np.zeros((p.shape[1],h.shape[1])),'bias':np.zeros(p.shape[1])}
            candidates.append(('anchor_%g'%beta,base))
            target=(y[tr]-beta*a[0][tr]-(1-beta)*a[1][tr])@p
            for lam in (1.,10.,100.):
                w=np.linalg.solve(h[tr].T@h[tr]+lam*np.eye(h.shape[1]),h[tr].T@target).T
                candidates.append(('ridge_%d_%g_%g'%(dz,beta,lam),dict(base,W=w)))
        # The latent-stream objective, with one row per forecast instead of dense-event indexing.
        xx=np.vstack([np.zeros(y.shape[1]),y[tr]])
        hh=np.vstack([h[tr],np.zeros(h.shape[1])])
        aa=np.vstack([a[0][tr],np.zeros(y.shape[1])]); bb=np.vstack([a[1][tr],np.zeros(y.shape[1])])
        indices=np.arange(1,len(tr)+1)
        for lam in (1.,10.,100.):
            fit=fit_text(hh,aa,bb,xx,xx@p,indices,indices,['text']*len(xx),lam,steps=steps,lr=.01)
            candidates.append(('contrastive_%d_%g'%(dz,lam),{'projection':p,'W':fit['W'],'bias':np.zeros(p.shape[1]),'beta':fit['beta'],'gamma':fit['gamma']}))
    av=[v[va] for v in a]
    scored=[(metrics(predict(m,av),y[va])[0],name,m) for name,m in candidates]
    chosen,name,m=max(scored,key=lambda z:(z[0]['mrr'],-z[0]['cosine_error']))
    ac=[v[ca] for v in a]; pc=predict(m,ac)
    m['confidence_W']=fit_confidence(pc,ac,y[ca])
    at=[v[te] for v in a]; pt=predict(m,at)
    report={'mode':mode,'blocks':{k:{'n':len(i),'first':rows[i[0]]['day'],'last':rows[i[-1]]['day']} for k,i in zip(('train','validation','calibration','test'),ids)},
            'selected':name,'validation':chosen,'test':{}}
    errors={}; reciprocal={}
    for label,pred in [('new',pt),('last_turn',at[0]),('recent_mean',at[1])]:
        report['test'][label],errors[label],reciprocal[label]=metrics(pred,y[te])
    days=[rows[i]['day'] for i in te]
    report['paired_day_ci95']={b:{'cosine_error_new_minus_baseline':interval(errors['new']-errors[b],days),
        'mrr_new_minus_baseline':interval(reciprocal['new']-reciprocal[b],days)} for b in ('last_turn','recent_mean')}
    cc=confidence(m,pc,ac); ct=confidence(m,pt,at)
    ec=1-np.sum(pc*y[ca],axis=1); et=errors['new']
    report['confidence']={'meaning':'1 - expected cosine error / 2','calibration_n':len(ca),'evaluation_n':len(te),
        'calibration_confidence_error_spearman':correlation(cc,ec),'evaluation_confidence_error_spearman':correlation(ct,et),
        'evaluation_error_mse':float(np.mean((2*(1-ct)-et)**2)),
        'constant_error_mse':float(np.mean((ec.mean()-et)**2)),
        'bins':[{'n':len(ix),'confidence':float(ct[ix].mean()),'error':float(et[ix].mean())} for ix in np.array_split(np.argsort(ct),3)]}
    if old:
        po,valid=old(rows,te)
        ix=np.flatnonzero(valid)
        if len(ix):
            report['old_checkpoint_comparison']={'n':len(ix),'old':metrics(po[ix],y[te][ix])[0],
                'new':metrics(pt[ix],y[te][ix])[0], 'last_turn':metrics(at[0][ix],y[te][ix])[0],
                'recent_mean':metrics(at[1][ix],y[te][ix])[0]}
    meta={'schema':SCHEMA,'mode':mode,'boundaries':BOUNDARIES,'selected':name,'report':report,
          'trained_through':rows[tr[-1]]['day'],'calibrated_through':rows[ca[-1]]['day']}
    np.savez_compressed(Path(out)/(mode+'.npz'),meta=json.dumps(meta),**m)
    return report


def load(path):
    with np.load(path,allow_pickle=False) as z:
        model={k:z[k] for k in z.files if k!='meta'}; meta=json.loads(str(z['meta']))
    if meta['schema']!=SCHEMA:raise ValueError('unsupported readout schema')
    model['meta']=meta
    return model


def forecast(enc, mode, exs=None, her='', now=None, model_dir=None):
    directory=Path(model_dir or os.path.join(os.environ.get('SPARK_WORKSPACE',os.path.expanduser('~/.vintos/workspace')),'memory','jepa-readouts'))
    path=directory/(mode+'.npz')
    if not path.exists():return None
    import jepa_self_head as sh
    exs=sh.exchanges() if exs is None else exs
    if mode=='self_on_message':
        her=sh._her(her or '')
        if not her:return None
        cutoff=now if now is not None else __import__('time').time()
        exs=sh._on_message_cut([e for e in exs if e['at']<cutoff], cutoff, sh.her_key(her))
    if not exs:return None
    r=context(exs,mode,her=her) # identical clock semantics at training and serving
    if not r['own']:return None
    a=arrays([r],Embeddings(enc)); m=load(path)
    if m['meta']['mode'] != mode:raise ValueError('checkpoint is for a different head or mode')
    p=predict(m,a)
    from jepa_predictor import format_context
    turns=[]
    for e in exs[-3:]:
        if e['her']:turns.append({'role':'user','content':e['her']})
        if e['his']:turns.append({'role':'assistant','content':e['his']})
    if mode=='self_on_message':turns.append({'role':'user','content':her})
    copied=units(enc.encode([format_context(turns[-6:])],show_progress_bar=False))[0]
    return {'her_key':sh.her_key(her), 'context_emb':copied.tolist(),'emb':p[0].astype('float32'),'confidence':float(confidence(m,p,a)[0]),'qualification':'qualified',
            'source':SCHEMA,'schema':SCHEMA,'mode':mode,'checkpoint_id':hashlib.sha256(path.read_bytes()).hexdigest(),
            'context_last_ts':exs[-1]['ts'],'context_last_turn_id':exs[-1].get('turn_id',''),
            'coherence':float(a[0][0]@a[1][0]),'confidence_evaluation':m['meta']['report']['confidence']}


def presence_forecast(enc, exs=None, model_dir=None):
    directory=Path(model_dir or os.path.join(os.environ.get('SPARK_WORKSPACE',os.path.expanduser('~/.vintos/workspace')),'memory','jepa-readouts'))
    path=directory/'presence.npz'
    if not path.exists():return None
    import jepa_self_head as sh
    exs=sh.exchanges() if exs is None else exs
    if not exs or not any(e['his'] for e in exs):return None
    a=arrays([context(exs,'self_ahead')],Embeddings(enc))
    with np.load(path,allow_pickle=False) as m:
        report=json.loads(str(m['meta'])); value=float(np.clip(m['mean']+features(a,m['projection'])@m['W'],0,1)[0])
    return {'predicted':value,'confidence':None,'qualification':'rubric_fit_small_sample',
            'novelty':abs(value-report['training_mean']),'calibration':'MEASURED_SMALL_SAMPLE',
            'steering_allowed':True,'checkpoint_id':hashlib.sha256(path.read_bytes()).hexdigest(),
            'evaluation':report,'source':SCHEMA}


def audit(enc, memory=None):
    """Keep each replacement's prospective evidence separate from the shared checkpoint.
    Neither model selection nor historical replay rows count as live outcomes here.
    """
    import jepa_ranking_audit as ra
    mem=Path(memory or ra.MEM);directory=mem/'jepa-readouts'
    if not directory.exists():return {}
    ledger=ra.realized_ledger(); report={}
    history=ra._jsonl(str(mem/'jepa-prediction-history.jsonl'))+ra._jsonl(str(mem/'jepa-self-forecasts.jsonl'))
    for mode in MODES:
        path=directory/(mode+'.npz')
        if not path.exists():continue
        ck=hashlib.sha256(path.read_bytes()).hexdigest();head='gloria' if mode=='gloria' else 'self'; adapted=[]
        for row in history:
            triple=row.get(head) or {}
            if triple.get('source')!=SCHEMA or triple.get('checkpoint_id')!=ck:continue
            if head=='self' and triple.get('mode','ahead')!=mode.removeprefix('self_'):continue
            if mode=='self_on_message':
                import jepa_self_head as sh
                arrived=float(row.get('arrived_at') or 0);key=row.get('her_key')
                matching=[e for e in ledger if sh.her_key(e.get('gloria',''))==key
                          and arrived-1<=sh._epoch(e['timestamp'])<=arrived+sh.TARGET_WINDOW and e.get('vintos')]
                if not matching or sh._epoch(matching[0]['timestamp'])<=float(row.get('ts',0)):continue
            # The generic audit must see the actual source checkpoint, not a legacy override.
            triple=dict(triple);triple.pop('source',None)
            adapted.append(dict(row,checkpoint_id=ck,**{head:triple}))
        measured=ra.evaluate(adapted,ledger,enc,checkpoint=ck,trained_before=path.stat().st_mtime)
        report[mode]={'checkpoint':ck,'ranking':ra._summary(measured,head)}
    ra._atomic(str(mem/'jepa-readout-audit.json'),report)
    return report

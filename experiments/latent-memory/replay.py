#!/usr/bin/env python3
"""Scratch-only, pre-registered longer-memory experiment. No live imports or sends.

Development selects on October 9-10 and checks October 11-12. Final fitting uses
all available admitted events before October 23, without further selection.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from latent_stream_model import Model, State, stamp, digest

TZ = ZoneInfo('America/Chicago')
CUTOFF = '2026-10-23'
PENALTIES = (1., 10., 100.)
VARIANTS = ('episodic', 'centroid', 'recent') + tuple('random_%d' % i for i in range(10))
GROUPS = {'her': 0, 'him': 0, 'inner': 1, 'thread': 2, 'creative': 2}
CONTRACT = dict(schema='latent-memory-v1', train_until_exclusive=CUTOFF,
                selection=['2026-10-09', '2026-10-11'], check=['2026-10-11', '2026-10-13'],
                fresh=['2026-10-23', '2026-10-30'], timezone=str(TZ), penalties=PENALTIES,
                bank_days=14, bank_cap=2048, old_hours=6, excluded_recent=6, top_k=4,
                temperature=.1, half_life_days=3, coefficient_budget=.25,
                horizon_seconds=600, tolerance_seconds=120, random_seeds=list(range(10)),
                bootstrap_seed=20261022, bootstrap_samples=10000, ci_quantiles=[.00625, .99375])


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def day(t):
    return stamp(t).astimezone(TZ).date().isoformat()


def unit(x):
    x = np.asarray(x, float)
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-12)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))


def scratch_output(path):
    """Explicit scratch workspace only; fail closed for default/live HOME."""
    root = os.environ.get('SPARK_WORKSPACE')
    if not root or not os.environ.get('LATENT_MEMORY_SCRATCH'):
        raise ValueError('set SPARK_WORKSPACE and LATENT_MEMORY_SCRATCH to the same private scratch root')
    root = Path(root).resolve()
    if root != Path(os.environ['LATENT_MEMORY_SCRATCH']).resolve() or '.vintos' in root.parts:
        raise ValueError('refusing a live workspace')
    out = Path(path).resolve()
    if not out.is_relative_to(root) or out == root:
        raise ValueError('output must be inside private scratch')
    out.mkdir(parents=True, exist_ok=False)
    out.chmod(0o700)
    return out


def load_events(path, end=CUTOFF):
    with np.load(path, allow_pickle=False) as z:
        rows = json.loads(str(z['rows']))
        out = []
        for i, row in enumerate(rows):
            e = dict(row, t=stamp(row['t']))
            # Reject, rather than silently allowing future inputs into preprocessing.
            if day(e['t']) >= end:
                raise ValueError('snapshot crosses the sealed cutoff')
            if z['is_text'][i]: e['vec'] = z['X'][i].astype(float)
            if z['is_emotion'][i]: e['emo'] = z['E'][i].astype(float)
            out.append(e)
    return clean_events(out)


def clean_events(events):
    """Stable simultaneous batches; deduplication never reads future outcomes."""
    out, seen = [], set()
    for e in sorted(events, key=lambda x: (stamp(x['t']), x['source'], x['id'])):
        if e['id'] in seen: continue
        seen.add(e['id'])
        for name in ('vec', 'emo'):
            if name in e and (np.asarray(e[name]).ndim != 1 or not np.isfinite(e[name]).all()):
                raise ValueError('nonfinite or malformed input')
        out.append(dict(e, t=stamp(e['t'])))
    return out


class Bank:
    """Identifiable episodes; ties all enter before any later timestamp is scored."""
    def __init__(self, dim):
        self.dim, self.items = dim, []

    def add(self, events):
        for e in events:
            if 'vec' in e:
                self.items.append(e)
        self.items = self.items[-CONTRACT['bank_cap']:]

    def vectors(self, query, at, variant, frame_id):
        now = stamp(at).timestamp()
        pool = [e for e in self.items if 0 <= now - e['t'].timestamp() <= 14*86400]
        recent = {e['id'] for e in self.items[-6:]}
        eligible = [e for e in pool if (e['id'] in recent if variant == 'recent' else
                    e['id'] not in recent and now - e['t'].timestamp() > 6*3600)]
        out = np.zeros((3, self.dim)); refs = []
        q = unit(query)
        for group in range(3):
            es = [e for e in eligible if GROUPS[e['source']] == group]
            if not es: continue
            v = np.asarray([e['vec'] for e in es]); sims = v @ q
            ages = np.array([now - e['t'].timestamp() for e in es])
            chosen = np.argsort(-sims, kind='stable')[:4]
            if variant.startswith('random_'):
                seed = int(variant.split('_')[1])
                token = digest([frame_id, group, seed])
                rng = np.random.default_rng(int(token[:16], 16))
                bins = np.searchsorted([86400, 3*86400], ages, side='right')
                selected = []
                for b in bins[chosen]:
                    possible = [i for i in np.flatnonzero(bins == b) if i not in selected]
                    selected.append(int(rng.choice(possible)))
                chosen = np.asarray(selected)
            if variant == 'centroid':
                chosen = np.arange(len(es)); weights = np.ones(len(es))
            else:
                logits = sims[chosen]/.1 - math.log(2)*ages[chosen]/(3*86400)
                weights = np.exp(logits-logits.max())
            out[group] = unit(weights @ v[chosen] / weights.sum())
            refs.extend(es[i]['id'] for i in chosen)
        return out, refs


def emotion_features(history, sd):
    """Exponential time-weighted observed intervals, never inventing quiet gaps.

    An observation supports at most the following 12 minutes. At the origin the
    current value is separate; past covered intervals determine the two means.
    """
    t, current = history[-1]
    recent = [(s, v) for s, v in history if t-s <= 36*3600]
    features = []
    for tau in (1800., 21600.):
        total = np.zeros(11); mass = 0.
        for (left, value), (right, _) in zip(recent, recent[1:]):
            end = min(right, left+720.)
            if end <= left: continue
            weight = math.exp(-(t-end)/tau)-math.exp(-(t-left)/tau)
            total += weight*value; mass += weight
        mean = total/mass if mass > 1e-12 else current
        features.extend(((current-mean)/sd).tolist())
        features.extend([float(mass), float(mass <= 1e-12)])
    gap = t-history[-2][0] if len(history)>1 else 0.
    features.extend([math.log1p(gap/60.), float(len(history)<2), float(gap>720.)])
    return np.asarray(features)


def replay(events, model, variants=VARIANTS):
    state = State(model); bank = Bank(model.dim); texts = []; emotions = []; hist = []
    pos = 0; tie_batches = 0; repeated_targets = []; since_text = 0
    while pos < len(events):
        end = pos+1
        while end < len(events) and events[end]['t'] == events[pos]['t']: end += 1
        batch = events[pos:end]; tie_batches += len(batch)>1
        # All target features are made before any member of this simultaneous batch.
        for e in batch:
            if 'vec' in e and state.six:
                memory = {v: bank.vectors(model.query(state), state.at, v, state.cursor)[0] for v in variants}
                texts.append(dict(day=day(e['t']), source=e['source'], y=e['vec'], id=e['id'],
                                  time=e['t'].timestamp(), forecast_at=state.at.timestamp(),
                                  exact=bool(e.get('t_exact', True)) and len(batch)==1,
                                  template=e.get('template_id',''),
                                  long_gap=(state.at-state.text_at).total_seconds()>6*3600,
                                  query=model.query(state), last=state.last.copy(), mean=state.mean(),
                                  memory=memory))
                repeated_targets.append(max(1, since_text)); since_text=0
        for e in batch: state.advance(e, observed_at=e['t'])
        bank.add(batch)
        for e in batch:
            if 'emo' in e:
                hist.append((e['t'].timestamp(), np.asarray(e['emo'])))
                hist = [h for h in hist if hist[-1][0]-h[0] <= 36*3600]
                trend = np.zeros(11)
                if len(hist)>1 and 0 < hist[-1][0]-hist[-2][0] <= 720:
                    trend = (hist[-1][1]-hist[-2][1])*600/(hist[-1][0]-hist[-2][0])
                emotions.append(dict(at=e['t'].timestamp(), day=day(e['t']), current=np.asarray(e['emo']),
                                     h=state.features(), m=emotion_features(hist, model.a['emo_sd']),
                                     incumbent=model.emotion(state), trend=np.asarray(e['emo'])+trend,
                                     lam_h=e.get('lam_features')))
        since_text += len(batch); pos = end
    # One target per realized reading, with no outcome interpolation or crossing loss.
    times = np.asarray([r['at'] for r in emotions]); used = set(); pairs=[]
    for r in emotions:
        j = int(np.searchsorted(times, r['at']+600))
        if j == len(times) or times[j] > r['at']+720 or j in used: continue
        used.add(j); target=emotions[j]
        pairs.append(dict(r, y=target['current'], target_at=target['at'], target_day=target['day']))
    text_positions=np.array([i for i,e in enumerate(events) if 'vec' in e])
    multiplicities=np.diff(text_positions)
    return texts, pairs, dict(simultaneous_batches=tie_batches, text_targets=len(texts), emotion_targets=len(pairs),
                              gru_preceding_steps_mean=float(np.mean(multiplicities)) if len(multiplicities) else None,
                              sources=dict(Counter(r['source'] for r in texts)),
                              unknown_timestamp_texts=sum(not r['exact'] for r in texts))


def text_arrays(rows, variant):
    return (np.array([r['query'] for r in rows]), np.array([r['y'] for r in rows]),
            np.array([r['memory'][variant] for r in rows]))


def fit_text(rows, variant, penalty, scale):
    """Three constrained weights, full training candidates, duplicate positives."""
    q, y, memory = text_arrays(rows, variant)
    base = q @ y.T
    f = np.einsum('ngd,cd->gnc', memory, y, optimize=True)
    ids = [hashlib.sha256(np.asarray(r['y'], np.float32).tobytes()).hexdigest() for r in rows]
    positive = np.equal.outer(ids, ids)
    source = np.array([r['source'] for r in rows]); same = source[:,None] == source[None,:]
    def objective(a):
        logits = scale*(base + np.einsum('g,gnc->nc', a, f))
        loss = penalty*np.dot(a,a); gradient = 2*penalty*a
        for mask, weight in ((np.ones_like(positive),1.), (same,.5)):
            valid_positive = positive & mask
            den = logsumexp(np.where(mask,logits,-np.inf), axis=1)
            num = logsumexp(np.where(valid_positive,logits,-np.inf), axis=1)
            g = (np.where(mask,np.exp(logits-den[:,None]),0) -
                 np.where(valid_positive,np.exp(logits-num[:,None]),0))*weight/len(rows)
            loss += weight*np.mean(den-num)
            gradient += scale*np.einsum('nc,gnc->g', g, f)
        return float(loss), gradient
    result = minimize(objective, np.zeros(3), jac=True, method='SLSQP', bounds=[(0,.25)]*3,
                      constraints=[{'type':'ineq','fun':lambda a:.25-a.sum(), 'jac':lambda a:-np.ones(3)}],
                      options={'maxiter':100,'ftol':1e-9})
    if not result.success or not np.isfinite(result.x).all(): raise RuntimeError('coefficient optimization failed: '+result.message)
    return result.x


def ranks(scores):
    return np.sum(scores >= np.diag(scores)[:,None]-1e-12, axis=1)


def text_metrics(rows, coefs, details=False):
    if not rows: return {'n':0}
    y = np.asarray([r['y'] for r in rows]); q = np.asarray([r['query'] for r in rows])
    base = q@y.T
    scores = {'incumbent':base, 'last':np.asarray([r['last'] for r in rows])@y.T,
              'mean6':np.asarray([r['mean'] for r in rows])@y.T}
    for variant,a in coefs.items():
        memory=np.asarray([r['memory'][variant] for r in rows])
        scores[variant]=base+np.einsum('g,ngd,cd->nc',a,memory,y,optimize=True)
    rr={k:1/ranks(s) for k,s in scores.items()}
    top={k:(v>=.1).astype(float) for k,v in rr.items()}
    randoms=[v for k,v in rr.items() if k.startswith('random_')]
    if randoms:
        rr['random_mean']=np.mean(randoms,axis=0)
        top['random_mean']=np.mean([v for k,v in top.items() if k.startswith('random_')],axis=0)
    def summary(idx):
        return {'n':int(np.sum(idx)), **{k:{'mrr':float(v[idx].mean()),'top10':float(top[k][idx].mean())} for k,v in rr.items()}}
    result=summary(np.ones(len(rows),bool)); result['per_source']={s:summary(np.array([r['source']==s for r in rows])) for s in sorted({r['source'] for r in rows})}
    result['macro_mrr']={k:float(np.mean([v[k]['mrr'] for v in result['per_source'].values()])) for k in rr}
    for name,idx in (('exact_time',np.array([r['exact'] for r in rows])),
                     ('long_gap',np.array([r['long_gap'] for r in rows])),
                     ('nonroutine',np.array([not r.get('routine',False) for r in rows]))):
        result[name]=summary(idx) if idx.any() else {'n':0}
    return (result,rr) if details else result


def ridge(x, y, penalty):
    return np.linalg.solve(x.T@x+penalty*np.eye(x.shape[1]),x.T@y)


def emotion_fit(rows, sd, penalty):
    h=np.array([r['h'] for r in rows]); m=np.array([r['m'] for r in rows])
    d=np.array([(r['y']-r['current'])/sd for r in rows])
    # Fixed present penalty, no extra search axis; history alone uses selected lambda.
    present=ridge(h,d,10.)
    history=ridge(m,d-h@present,penalty)
    valid=[r for r in rows if r.get('lam_h') is not None]
    lam_fit=None
    if valid:
        lh=np.array([r['lam_h'] for r in valid]); ld=np.array([(r['y']-r['current'])/sd for r in valid])
        lam_fit=ridge(lh,ld,penalty)
    return present,history,lam_fit


def emotion_errors(rows, fit, sd):
    p,b,lam_fit=fit; h=np.array([r['h'] for r in rows]); m=np.array([r['m'] for r in rows])
    cur=np.array([r['current'] for r in rows]); target=np.array([r['y'] for r in rows])
    pred={'persistence':cur, 'incumbent':np.array([r['incumbent'] for r in rows]),
          'trend':np.array([r['trend'] for r in rows]), 'present':cur+(h@p)*sd,
          'history':cur+(h@p+m@b)*sd}
    if lam_fit is not None:
        pred['lam']=np.array([r['current']+(np.asarray(r['lam_h'])@lam_fit)*sd if r.get('lam_h') is not None else np.full(11,np.nan) for r in rows])
    return {k:((v-target)/sd)**2 for k,v in pred.items()}, {k:(v-target)**2 for k,v in pred.items()}


def emotion_metrics(rows, fit, sd):
    if not rows:return {'n':0}
    norm,raw=emotion_errors(rows,fit,sd)
    result={'n':len(rows),'lam_coverage':sum(r.get('lam_h') is not None for r in rows),
            **{k:{'mse':float(np.nanmean(v)),'per_axis_raw_mse':np.nanmean(raw[k],axis=0).tolist()} for k,v in norm.items()}}
    lam_rows=[r for r in rows if r.get('lam_h') is not None]
    if lam_rows and len(lam_rows)!=len(rows):
        ne,_=emotion_errors(lam_rows,fit,sd)
        result['lam_matched_subset']={'n':len(lam_rows),**{k:float(v.mean()) for k,v in ne.items()}}
    change=np.array([np.sqrt(np.mean(((r['y']-r['current'])/sd)**2))>.1 for r in rows])
    result['change_periods']={label:{'n':int(mask.sum()),**{k:(float(np.nanmean(v[mask])) if np.isfinite(v[mask]).any() else None) for k,v in norm.items()}} for label,mask in (('change',change),('calm',~change))}
    result['per_day']={d:{k:(float(np.nanmean(v[[r['target_day']==d for r in rows]])) if np.isfinite(v[[r['target_day']==d for r in rows]]).any() else None) for k,v in norm.items()} for d in sorted({r['target_day'] for r in rows})}
    return result


def blocks(texts, emotions):
    def block(d):return 0 if d<'2026-10-09' else 1 if d<'2026-10-11' else 2 if d<'2026-10-13' else 3
    t=[[r for r in texts if block(r['day'])==k] for k in range(4)]
    # No training loss crosses a chronological boundary; warm-up remains causal.
    e=[[r for r in emotions if block(r['day'])==block(r['target_day'])==k] for k in range(4)]
    return t,e


def retrieval_proxy(events, model, coefficients, start, end):
    """Fixed two-anchor budget, same past-only bank; target used only after choice."""
    state=State(model);bank=Bank(model.dim);rows=[];pos=0
    while pos<len(events):
        stop=pos+1
        while stop<len(events) and events[stop]['t']==events[pos]['t']:stop+=1
        batch=events[pos:stop]
        if state.six:
            pool=[e for e in bank.items if 0<=(state.at-e['t']).total_seconds()<=14*86400]
            if pool:
                v=np.asarray([e['vec'] for e in pool]);q=model.query(state)
                memory,_=bank.vectors(q,state.at,'episodic',state.cursor)
                queries={'incumbent':q,'last':state.last,'episodic':q+coefficients@memory}
                chosen={k:np.argsort(-(v@x),kind='stable')[:2] for k,x in queries.items()}
                chosen['recent']=np.arange(max(0,len(pool)-2),len(pool))
                for e in batch:
                    if 'vec' in e and start<=day(e['t'])<end:
                        sim=v@e['vec']
                        rows.append({'source':e['source'],**{k:float(sim[ix].mean()) for k,ix in chosen.items()}})
        for e in batch:state.advance(e,observed_at=e['t'])
        bank.add(batch);pos=stop
    names=('incumbent','last','episodic','recent')
    return {'n':len(rows),'anchor_budget':2,'past_only':True,'independent_link_labels':0,
            'meaning':'next-text similarity proxy only; continuity remains unproved',
            'means':{k:float(np.mean([r[k] for r in rows])) for k in names} if rows else {},
            'per_source':{s:{'n':len(rs),**{k:float(np.mean([r[k] for r in rs])) for k in names}}
                          for s in sorted({r['source'] for r in rows}) if (rs:=[r for r in rows if r['source']==s])}}


def develop_and_refit(events, model, out, input_hash, code_hash):
    start=time.perf_counter()
    texts,emotions,counts=replay(events,model)
    tb,eb=blocks(texts,emotions)
    if any(not b for b in tb[:3]+eb[:3]):raise ValueError('missing development block')
    forms=Counter(r['template'] for r in tb[0] if r['template'])
    routine={x for x,n in forms.items() if n>1}
    for r in texts:r['routine']=r['template'] in routine
    sd=model.a['emo_sd']; grid=[]; fits={}
    for lam in PENALTIES:
        a=fit_text(tb[0],'episodic',lam,float(model.a['scale']))
        ef=emotion_fit(eb[0],sd,lam)
        tm=text_metrics(tb[1],{'episodic':a}); em=emotion_metrics(eb[1],ef,sd)
        grid.append({'penalty':lam,'text_mrr':tm['episodic']['mrr'],'emotion_mse':em['history']['mse']})
        fits[lam]=(a,ef)
        print(json.dumps({'phase':'development-grid','penalty':lam}),flush=True)
    # Select only here. Check-block outcomes never choose another candidate.
    tl=max(PENALTIES,key=lambda l:next(r['text_mrr'] for r in grid if r['penalty']==l))
    el=min(PENALTIES,key=lambda l:next(r['emotion_mse'] for r in grid if r['penalty']==l))
    coefs={'episodic':fits[tl][0]}
    for v in VARIANTS[1:]:
        coefs[v]=fit_text(tb[0],v,tl,float(model.a['scale']))
    development={'training_sources':dict(Counter(r['source'] for r in tb[0])),
                 'training_emotion_n':len(eb[0]),'grid':grid,'text_penalty':tl,'emotion_penalty':el,
                 'selection':{'text':text_metrics(tb[1],coefs),'emotion':emotion_metrics(eb[1],fits[el][1],sd)},
                 'check':{'text':text_metrics(tb[2],coefs),'emotion':emotion_metrics(eb[2],fits[el][1],sd)}}
    text_ok=all(development[b]['text']['episodic']['mrr']>development[b]['text']['incumbent']['mrr'] for b in ('selection','check'))
    emotion_ok=all(development[b]['emotion']['history']['mse']<development[b]['emotion']['present']['mse'] for b in ('selection','check'))
    development['eligible_for_fresh']={'text':text_ok,'emotion':emotion_ok}
    development['retrieval_proxy']=retrieval_proxy(events,model,coefs['episodic'],'2026-10-09','2026-10-13')
    development['zero_correction_selected']={'text':development['selection']['text']['episodic']['mrr']<=development['selection']['text']['incumbent']['mrr'],
                                            'emotion':development['selection']['emotion']['history']['mse']>=development['selection']['emotion']['present']['mse']}
    write_json(out/'development.json',development)
    np.savez_compressed(out/'development-fits.npz',**{'text_'+k:v for k,v in coefs.items()},
                        emotion_present=fits[el][1][0],emotion_history=fits[el][1][1],lam_fit=fits[el][1][2] if fits[el][1][2] is not None else np.zeros((0,11)))
    # User-authorized refit through Oct 22, even if development fails. Failed
    # designs remain archived experiments, never promoted or retuned.
    final={}
    for v in VARIANTS:
        final['text_'+v]=fit_text(texts,v,tl,float(model.a['scale']))
        print(json.dumps({'phase':'final-refit','control':v}),flush=True)
    fp,fh,fl=emotion_fit(emotions,sd,el)
    final.update(emotion_present=fp,emotion_history=fh,emotion_sd=sd,lam_fit=fl if fl is not None else np.zeros((0,11)))
    np.savez_compressed(out/'frozen.npz',**final)
    manifest=dict(CONTRACT, sealed_at=datetime.now(TZ).isoformat(),incumbent_sha256=model.checkpoint_id,
                  input_sha256=input_hash,code_sha256=code_hash,frozen_sha256=sha(out/'frozen.npz'),
                  development_sha256=sha(out/'development.json'),text_penalty=tl,emotion_penalty=el,
                  eligible_for_fresh=development['eligible_for_fresh'],
                  refit_sources=dict(Counter(r['source'] for r in texts)),refit_text_n=len(texts),
                  refit_emotion_n=len(emotions),max_input_timestamp=max(e['t'] for e in events).isoformat(),
                  routine_templates=sorted(routine),no_fresh_outcomes_read=True)
    write_json(out/'manifest.json',manifest)
    report={'counts':counts,'development':development,'final_fit_counts':{'text':len(texts),'emotion':len(emotions)},
            'final_text_coefficients':{k:v.tolist() for k,v in final.items() if k.startswith('text_')},
            'manifest_sha256':sha(out/'manifest.json'),'checkpoint_sha256':sha(out/'frozen.npz'),
            'seconds':time.perf_counter()-start,'fresh_evaluation':'not run',
            'continuity':'unproved: no independently timestamped link labels in this snapshot',
            'refit_note':'all available admitted inputs through Oct 22; no scores on Oct 13-22 used for selection'}
    write_json(out/'report.json',report)
    return report


def bootstrap(values, days):
    """Paired day-block bootstrap; vector contrasts retain the same sampled days."""
    values=np.asarray(values); days=np.asarray(days); unique=sorted(set(days))
    sums=np.asarray([np.nansum(values[days==d],axis=0) for d in unique]); sizes=np.asarray([np.isfinite(values[days==d]).sum(axis=0) for d in unique])
    rng=np.random.default_rng(CONTRACT['bootstrap_seed'])
    pick=rng.integers(0,len(unique),(CONTRACT['bootstrap_samples'],len(unique)))
    denom=sizes[pick].sum(axis=1)
    return sums[pick].sum(axis=1)/denom


def evaluate(events, model, sealed, out, now=None):
    """One sealed seven-day evaluation; exclusive attempt receipt prevents peeking."""
    manifest=json.loads((sealed/'manifest.json').read_text())
    if manifest['code_sha256']!=sha(__file__) or manifest['incumbent_sha256']!=model.checkpoint_id or manifest['frozen_sha256']!=sha(sealed/'frozen.npz'):
        raise ValueError('sealed code/checkpoint mismatch')
    now=now or datetime.now(TZ)
    if now < datetime(2026,10,30,tzinfo=TZ):raise ValueError('fresh seven-day block is not closed')
    if stamp(manifest['sealed_at'])>=datetime(2026,10,23,tzinfo=TZ):raise ValueError('candidate was not sealed before fresh block')
    attempt=sealed/'evaluation-attempt.json'
    with attempt.open('x') as f:json.dump({'started':now.isoformat()},f)
    texts,emotions,_=replay(events,model)
    tt=[r for r in texts if '2026-10-23'<=r['day']<'2026-10-30']
    ee=[r for r in emotions if '2026-10-23'<=r['day']<=r['target_day']<'2026-10-30']
    if not tt or not ee:
        report={'status':'insufficient','text_n':len(tt),'emotion_n':len(ee),'passes':{'text':False,'emotion':False}}
        write_json(out/'fresh-report.json',report)
        return report
    for r in tt:r['routine']=r['template'] in manifest['routine_templates']
    with np.load(sealed/'frozen.npz',allow_pickle=False) as z:
        coefs={v:z['text_'+v] for v in VARIANTS}; ef=(z['emotion_present'],z['emotion_history'],z['lam_fit'] if z['lam_fit'].size else None); sd=z['emotion_sd']
    tm,rr=text_metrics(tt,coefs,True); em=emotion_metrics(ee,ef,sd)
    intervals={}
    for k in ('incumbent','recent','random_mean'):
        samples=bootstrap(rr['episodic']-rr[k],[r['day'] for r in tt])
        intervals[k]=np.quantile(samples,CONTRACT['ci_quantiles']).tolist()
    errors,_=emotion_errors(ee,ef,sd)
    improvements=np.column_stack([v.mean(1)-errors['history'].mean(1) for k,v in errors.items() if k!='history'])
    ci=np.quantile(bootstrap(improvements,[r['target_day'] for r in ee]).min(1),CONTRACT['ci_quantiles']).tolist()
    text_days=len(set(r['day'] for r in tt)); emotion_days=len(set(r['target_day'] for r in ee))
    enough_t=len(tt)>=100 and text_days==7; enough_e=len(ee)>=300 and emotion_days==7
    relative_ok=all(np.mean(errors['history'][np.isfinite(v).all(axis=1)]) <= .95*np.nanmean(v)
                    for k,v in errors.items() if k!='history' and np.isfinite(v).any())
    tpass=(enough_t and manifest['eligible_for_fresh']['text'] and
           tm['episodic']['mrr']-tm['incumbent']['mrr']>=.01 and
           tm['episodic']['mrr']>max(tm['last']['mrr'],tm['mean6']['mrr']) and all(v[0]>0 for v in intervals.values()) and
           tm['nonroutine'].get('n',0)>0 and tm['nonroutine']['episodic']['mrr']>tm['nonroutine']['incumbent']['mrr'])
    epass=enough_e and manifest['eligible_for_fresh']['emotion'] and relative_ok and ci[0]>0
    report={'text':tm,'emotion':em,'text_gain_ci98_75':intervals,'emotion_gain_ci98_75':ci,
            'passes':{'text':bool(tpass),'emotion':bool(epass)},'enough_data':{'text':enough_t,'emotion':enough_e},
            'manifest_sha256':sha(sealed/'manifest.json'),'no_runtime_changes':True,
            'retrieval_proxy':retrieval_proxy(events,model,coefs['episodic'],'2026-10-23','2026-10-30')}
    write_json(out/'fresh-report.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('fit','evaluate'));p.add_argument('--snapshot',required=True)
    p.add_argument('--incumbent',required=True);p.add_argument('--out',required=True);p.add_argument('--sealed')
    args=p.parse_args();out=scratch_output(args.out);model=Model(args.incumbent)
    if args.mode=='fit':
        report=develop_and_refit(load_events(args.snapshot),model,out,sha(args.snapshot),sha(__file__))
    else:
        if not args.sealed:p.error('--sealed is required')
        # Refuse early before loading any future labels.
        if datetime.now(TZ)<datetime(2026,10,30,tzinfo=TZ):raise ValueError('fresh block is not closed')
        report=evaluate(load_events(args.snapshot,end='2026-10-30'),model,Path(args.sealed),out)
    print(json.dumps({'report':str(out),'fresh_evaluation':report.get('fresh_evaluation','complete')}))


if __name__=='__main__':main()

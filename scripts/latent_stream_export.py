#!/usr/bin/env python3
"""Export a frozen present-moment fit and verify incremental/batch parity in scratch.

A report is not a checkpoint. Exact reconstruction refuses missing input rows;
--retained-refit explicitly labels a fixed-configuration fit on retained inputs.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo

import numpy as np
import latent_stream_linear as L
from latent_stream_model import Model, State, save, digest, stamp


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_output(path):
    out = Path(path).resolve()
    live = Path(os.environ.get('SPARK_WORKSPACE', Path.home()/'.vintos/workspace')).resolve()
    if out == live or live in out.parents:
        raise ValueError('export must write to explicit scratch outside the workspace')
    out.mkdir(parents=True, exist_ok=False)
    out.chmod(0o700)
    return out


def snapshot(events, path):
    X, E, it, ie = L.arrays(events)
    rows = [{'t': e['t'].isoformat(), 'source': e['source'],
             'id': e.get('id') or digest([i, e['t'].isoformat(), e['source'], e.get('text', '')]),
             't_exact': e.get('t_exact', True)} for i, e in enumerate(events)]
    np.savez_compressed(path, rows=json.dumps(rows), X=X, E=E, is_text=it, is_emotion=ie)


def read_snapshot(path):
    with np.load(path, allow_pickle=False) as z:
        rows = json.loads(str(z['rows']))
        for i, e in enumerate(rows):
            e['t'] = stamp(e['t'])
            if z['is_text'][i]:
                e['vec'] = z['X'][i].tolist()
            if z['is_emotion'][i]:
                e['emo'] = z['E'][i].tolist()
    return rows


def export_fit(events, out, choice, timezone_name, provenance, steps=200, fitted=None,
               val_from=L.VAL_FROM, test_from=L.TEST_FROM, encoder_id=None):
    """No search: the supplied validation-selected design is frozen before this call."""
    if choice.get('history') is not False:
        raise ValueError('only the present-moment fit is exportable here')
    if timezone_name not in ('UTC', 'America/Chicago'):
        ZoneInfo(timezone_name)  # validate even when a different timezone is intentionally used
    os.environ['TZ'] = timezone_name
    time.tzset()
    X, E, it, ie = L.arrays(events)
    sp = [L.split_of(e, val_from, test_from) for e in events]
    train = [i for i in range(1, len(events)) if it[i] and sp[i] == 'train']
    etrain = E[[i for i in range(len(events)) if ie[i] and sp[i] == 'train']]
    emu, esd = etrain.mean(0), np.maximum(etrain.std(0), 1e-3)
    mu, P = L.pca(X[train], choice['dz'])
    Z = ((X-mu)@P).astype(np.float32)
    H, last, mean = L.states(events, X, E, it, ie, P, mu, emu, esd, choice['clock'], False)
    le = L.last_emotion(E, ie)
    et = [i for i in range(1, len(events)) if ie[i] and sp[i]=='train' and le[i-1].any()]
    if fitted is None:
        fit = L.fit_text(H, last, mean, X, Z, train, train, [e['source'] for e in events],
                         choice['lam'], steps=steps)
        Bm = L.fit_emotion(H, le, E, et, choice['emotion_lam'], esd)
    else:
        fit, Bm = fitted
    from jepa_predictor import EMB_MODEL
    meta = {'clock': choice['clock'], 'timezone': timezone_name, 'encoder': encoder_id or EMB_MODEL,
            'selection': {k: choice[k] for k in ('history','dz','clock','lam','emotion_lam')}, 'steps': steps, 'val_from': val_from, 'test_from': test_from,
            'provenance': provenance, 'text_target': 'next_text', 'emotion_target': 'next_emotion_reading',
            'uncertainty': 'raw error only; no probability calibration',
            'experiment_code_sha256': sha(L.__file__)}
    out = Path(out)
    snapshot(events, out/'events.npz')
    meta['snapshot_sha256'] = sha(out/'events.npz')
    save(out/'present-moment.npz', {'P':P,'mu':mu,'emo_mu':emu,'emo_sd':esd,
                                   **fit,'Bm':Bm}, meta)
    model = Model(out/'present-moment.npz')
    state = State(model)
    online_h, online_last, online_mean, online_emotion = [], [], [], []
    started = time.perf_counter()
    for i,e in enumerate(read_snapshot(out/'events.npz')):
        state.advance(e, observed_at=e['t'])
        online_h.append(state.features()); online_last.append(state.last.copy()); online_mean.append(state.mean())
        online_emotion.append(model.emotion(state))
        if i % 97 == 0:
            state = State(model, json.loads(json.dumps(state.dump())))
    elapsed = time.perf_counter()-started
    OH, OL, OM = map(np.asarray, (online_h, online_last, online_mean))
    targets = [i for i in range(1,len(events)) if it[i] and sp[i]=='test']
    es = [i for i in range(1,len(events)) if ie[i] and sp[i]=='test' and le[i-1].any()]
    scores = L.text_scores(fit,H,last,mean,X,Z,targets,targets)
    # Use the serving scorer itself, not a second copy of its equation.
    state = State(model); live_scores = []
    target_set = set(targets)
    for i,e in enumerate(read_snapshot(out/'events.npz')):
        if i in target_set:
            live_scores.append(model.scores(state,X[targets]))
        state.advance(e,observed_at=e['t'])
    live_scores = np.asarray(live_scores)
    r, rr = L.rank_eval(scores,X,targets,targets)
    ro, rro = L.rank_eval(live_scores,X,targets,targets)
    baseline = L.rank_eval(last[[i-1 for i in targets]]@X[targets].T,X,targets,targets)[0]
    recent = L.rank_eval(mean[[i-1 for i in targets]]@X[targets].T,X,targets,targets)[0]
    expected_emo = le + (H@Bm)*esd
    # Prior to the first reading the state uses the training mean; no outcome is scored there.
    emo_idx = [i for i in range(len(events)) if ie[:i+1].any()]
    parity = {'feature_max_abs':float(np.max(abs(OH-H))),
              'last_max_abs':float(np.max(abs(OL-last))), 'mean_max_abs':float(np.max(abs(OM-mean))),
              'score_max_abs':float(np.max(abs(live_scores-scores))),
              'emotion_max_abs':float(np.max(abs(np.asarray(online_emotion)[emo_idx]-expected_emo[emo_idx]))),
              'ranks_identical': bool(np.array_equal(rr,rro)), 'n_frames':len(events),
              'n_text_targets':len(targets),'n_emotion_targets':len(es),
              'seconds':elapsed,'ms_per_frame':elapsed*1000/max(1,len(events))}
    parity['passed'] = all(parity[k] <= 1e-6 for k in ('feature_max_abs','last_max_abs','mean_max_abs','score_max_abs','emotion_max_abs')) and parity['ranks_identical']
    report = {'checkpoint_id':model.checkpoint_id,'snapshot_sha256':meta['snapshot_sha256'],
              'selection':meta['selection'],'fitted_anchors':{'beta':fit['beta'],'gamma':fit['gamma']},'provenance':provenance,'parity':parity,
              'test':{'model':r,'online':ro,'last_one':baseline,'mean_last_six':recent,
                      'emotion':L.emo_eval(Bm,H,le,E,es,esd)},
              'consumer_claim':'score parity only; downstream benefit requires separate evaluation'}
    (out/'export-report.json').write_text(json.dumps(report,indent=2))
    if not parity['passed']:
        raise ValueError('incremental parity failed; see scratch export-report.json')
    return report


def reconstruct(experiment, retained=False):
    """Use ordinary current records plus the experiment cache, never erased backups.

    Old manifests lack content IDs. Matching timestamp groups is explicitly recorded
    as unverified even when counts agree; the snapshot format above fixes future runs.
    """
    p=Path(experiment)
    manifest=[json.loads(l) for l in (p/'manifest.jsonl').read_text().splitlines()]
    by=defaultdict(list)
    for e in L.R.build_stream():
        by[(e['t'].isoformat(),e['source'])].append(e)
    cache={r['k']:r['v'] for r in (json.loads(l) for l in (p/'text-vectors.jsonl').open())}
    out=[];missing=defaultdict(int);uncached=0
    for i,r in enumerate(manifest):
        group=by[(r['t'],r['source'])]
        if not group:
            missing[r['source']]+=1;continue
        e=dict(group.pop(0))
        if r['text']:
            if e.get('text') not in cache:
                uncached+=1;continue
            e['vec']=cache[e['text']]
        e['id']=digest([i,r['t'],r['source']])
        out.append(e)
    provenance={'kind':'retained-input-refit','original_report_sha256':sha(p/'linear-result.json'),
                'original_manifest_sha256':sha(p/'manifest.jsonl'), 'original_n':len(manifest),
                'retained_n':len(out),'missing':dict(missing),'uncached_texts':uncached,
                'original_content_identity':'not verifiable: old manifest has no content hashes',
                'same_weights_as_original':False}
    if not retained:
        raise ValueError('original manifest lacks content IDs/full vectors; use its events.npz snapshot or explicitly label --retained-refit')
    return out,provenance



def retrieval_audit(model_path, snapshot_path):
    """One frozen replay of past-only anchors. A topic-alignment proxy, not behavior.

    Conditions have the same two-anchor budget and the same last-512 candidate pool:
    most recent context, last-text embedding retrieval, and the trained readout.
    The realized target is used only to score the selections after they are frozen.
    """
    model=Model(model_path);events=read_snapshot(snapshot_path);state=State(model)
    past=[];rows=[]
    for i,e in enumerate(events):
        day=e['t'].astimezone(model.tz).date().isoformat()
        if e.get('vec') is not None and day>=model.meta['test_from'] and past:
            pool=past[-512:]
            assert all(j<i and events[j]['t']<=state.at for j in pool)
            V=np.asarray([events[j]['vec'] for j in pool],np.float32)
            scores={'recent_context':np.arange(len(pool)),
                    'last_text_retrieval':V@state.last,
                    'trained_retrieval':model.scores(state,V)}
            selected={k:np.argsort(-v,kind='stable')[:2] for k,v in scores.items()}
            # Only after selection do outcomes enter this calculation.
            similarity=V@np.asarray(e['vec'],np.float32)
            rows.append({'day':day,'source':e['source'],'n_candidates':len(pool),
                         **{k:float(similarity[idx].mean()) for k,idx in selected.items()}})
        state.advance(e,observed_at=e['t'])
        if e.get('vec') is not None:past.append(i)
    names=('recent_context','last_text_retrieval','trained_retrieval')
    days=sorted({r['day'] for r in rows});rng=np.random.default_rng(20261022)
    differences=[]
    for _ in range(2000):
        chosen=rng.choice(days,len(days))
        differences.append(np.mean([r['trained_retrieval']-r['last_text_retrieval'] for d in chosen for r in rows if r['day']==d]))
    return {'checkpoint_id':model.checkpoint_id,'n':len(rows),'candidate_pool':'last 512 earlier text events',
            'anchor_budget':2,'metric':'mean cosine similarity of selected past anchors to actual next text',
            'all_candidates_before_target':True,
            'means':{k:float(np.mean([r[k] for r in rows])) for k in names},
            'trained_minus_last_retrieval_day_95ci':np.quantile(differences,[.025,.975]).tolist(),
            'per_source':{source:{'n':len(rs),**{k:float(np.mean([r[k] for r in rs])) for k in names}}
                          for source in sorted({r['source'] for r in rows}) if (rs:=[r for r in rows if r['source']==source])},
            'limits':'Already inspected October block; descriptive proxy, not generator quality or lived benefit. No test-driven tuning.'}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--experiment');ap.add_argument('--out',required=True)
    ap.add_argument('--audit-checkpoint')
    ap.add_argument('--snapshot');ap.add_argument('--retained-refit',action='store_true')
    ap.add_argument('--timezone',required=True);ap.add_argument('--steps',type=int,default=200)
    a=ap.parse_args()
    if a.audit_checkpoint:
        if not a.snapshot:ap.error('--audit-checkpoint needs --snapshot')
        out=safe_output(a.out)
        report=retrieval_audit(a.audit_checkpoint,a.snapshot)
        (out/'retrieval-report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report));return
    if not a.experiment:ap.error('--experiment is required for export')
    p=Path(a.experiment)
    original=json.loads((p/'linear-result.json').read_text())
    choice=original['test_history_ablation']['design']
    if a.snapshot:
        events=read_snapshot(a.snapshot)
        provenance={'kind':'frozen-snapshot-reconstruction','input_sha256':sha(a.snapshot),
                    'original_report_sha256':sha(p/'linear-result.json')}
    else:
        events,provenance=reconstruct(p,a.retained_refit)
    out=safe_output(a.out)
    report=export_fit(events,out,choice,a.timezone,provenance,steps=a.steps)
    print(json.dumps(report))


if __name__=='__main__':
    main()

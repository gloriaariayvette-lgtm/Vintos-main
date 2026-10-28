#!/usr/bin/env python3
"""Seal one future-week bundle. No fresh outcomes; private parameters only."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from data import TZ,SOURCES,HORIZONS,boundary,scratch,sha,write_json,features,horizon_pairs,split_pairs,ridge


def present_refit(snapshot,path):
    """Fixed winning configuration, all available admitted training through Oct 22.

    This is a new identified comparator artifact, not a claim to recover the
    earlier confirmation's unsaved weights or to reproduce its .230 MRR.
    """
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
    import latent_stream_linear as L
    from latent_stream_model import save
    with np.load(snapshot,allow_pickle=False) as d:
        rows=[]
        for k,i in enumerate(d['text_i']):
            rows.append({'t':datetime.fromtimestamp(d['t'][i],TZ),'source':SOURCES[int(d['text_source'][k])],'vec':d['text_vectors'][k].tolist()})
        for i in np.flatnonzero(np.isfinite(d['emo']).all(1)):
            rows.append({'t':datetime.fromtimestamp(d['t'][i],TZ),'source':'emotion','emo':d['emo'][i].tolist()})
    rows.sort(key=lambda e:(e['t'],e['source']))
    X,E,it,ie=L.arrays(rows);ids=np.flatnonzero(it);targets=ids[ids>0]
    mu,p=L.pca(X[ids],32);emu=E[ie].mean(0);esd=np.maximum(E[ie].std(0),1e-3)
    H,last,recent=L.states(rows,X,E,it,ie,p,mu,emu,esd,'hour',False)
    z=((X-mu)@p).astype(np.float32)
    fit=L.fit_text(H,last,recent,X,z,targets,ids,[e['source'] for e in rows],.01,steps=200)
    le=L.last_emotion(E,ie);et=[i for i in np.flatnonzero(ie) if i>0 and le[i-1].any()]
    bm=L.fit_emotion(H,le,E,et,10,esd)
    save(path,dict(P=p,mu=mu,emo_mu=emu,emo_sd=esd,Bm=bm,**fit),
         dict(clock='hour',timezone=str(TZ),val_from='2026-10-23',test_from='2026-10-31',
              provenance='fixed-config admitted-input through-Oct22 comparator refit; no score or selection',
              snapshot_sha256=sha(snapshot)))


def main(args):
    if datetime.now(TZ).timestamp()>=boundary('2026-10-31'):raise ValueError('week already opened; cannot seal')
    root=scratch(args.out);rounds=Path(args.rounds)
    candidates=[]
    with np.load(args.snapshot,allow_pickle=False) as d:
        data={k:d[k] for k in d.files}
        t=data['t'];labels=np.argmax(data['source'],axis=1)
        clock=np.array([datetime.fromtimestamp(at,TZ).hour for at in t])
        gap=np.log1p(np.maximum(np.diff(t),0)/60)
    for n in range(1,9):
        src=rounds/('round-'+str(n));report=json.loads((src/'report.json').read_text())
        if report['round']!=n or report['snapshot_sha256']!=sha(args.snapshot):raise ValueError('round provenance mismatch')
        dst=root/('candidate-'+str(n));dst.mkdir()
        for name in ('scan.pt','readouts.npz','report.json'):shutil.copyfile(src/name,dst/name)
        counts=np.ones((12*24,12));gaps=np.zeros(12*24);sizes=np.zeros(12*24)
        cutoff=boundary(report['split']['train_before'])
        for i in np.flatnonzero(t[1:]<cutoff):
            key=labels[i]*24+clock[i];counts[key,labels[i+1]]+=1;gaps[key]+=gap[i];sizes[key]+=1
        mean_gap=np.divide(gaps,sizes,out=np.full_like(gaps,float(gap[t[1:]<cutoff].mean())),where=sizes>0)
        extra={'prob':counts/counts.sum(1,keepdims=True),'log_gap':mean_gap}
        with np.load(dst/'readouts.npz',allow_pickle=False) as a:
            present,history,last,em,mu,sd=features(t,data['source'],data['emo'],data['text'],data['numeric'],0,stats=(a['emotion_mu'],a['emotion_sd']))
            lastz=(last-a['projection_mu'])@a['projection'];lastz[np.linalg.norm(last,axis=1)==0]=0
            strong=np.concatenate([present,lastz],axis=1)
            mask=np.isfinite(data['emo']).all(1)
            for horizon in HORIZONS:
                pairs=split_pairs(horizon_pairs(t,mask,int(horizon)),t,-np.inf,cutoff)
                if len(pairs)<30:continue
                i,j=pairs.T;y=(data['emo'][j]-em[i])/sd
                wp=ridge(strong[i],y);wh=ridge(history[i],y-strong[i]@wp)
                extra[str(horizon)+'_present_text']=wp;extra[str(horizon)+'_history_text']=wh
        np.savez_compressed(dst/'schedule.npz',**extra)
        candidates.append({'round':n,'files':{name:sha(dst/name) for name in ('scan.pt','readouts.npz','report.json','schedule.npz')},
                           'training_cutoff':report['split']['train_before'],'anchor_history':n>=6})
    shutil.copyfile(args.incumbent,root/'incumbent.npz')
    if args.present_refit:
        with np.load(args.present_refit,allow_pickle=False) as d:
            if json.loads(str(d['meta'])).get('snapshot_sha256')!=sha(args.snapshot):raise ValueError('comparator input mismatch')
        shutil.copyfile(args.present_refit,root/'present-refit.npz')
    else:present_refit(args.snapshot,root/'present-refit.npz')
    # Keep a self-contained exact executable. Later sprint rounds must never
    # edit this copy to rescue this week's acceptance or bypass an attempt.
    exp=root/'code/experiments/persistence-sprint';exp.mkdir(parents=True)
    for p in Path(__file__).parent.glob('*.py'):shutil.copyfile(p,exp/p.name)
    scripts=root/'code/scripts';scripts.mkdir()
    for name in ('latent_stream_model.py','latent_stream_linear.py','latent_stream_replay.py'):
        shutil.copyfile(Path(__file__).resolve().parents[2]/'scripts'/name,scripts/name)
    manifest=dict(schema='persistence-week-v1',sealed_at=datetime.now(TZ).isoformat(),
                  week=['2026-10-31','2026-11-07'],timezone=str(TZ),selected_primary=7,
                  selection='best 6h validation of same-split diagnostic rounds 5–8; all remain reported',
                  no_development_candidate_met_5_percent=True,
                  candidates=candidates,incumbent_sha256=sha(root/'incumbent.npz'),
                  present_refit_sha256=sha(root/'present-refit.npz'),snapshot_sha256=sha(args.snapshot),
                  code={str(p.relative_to(root/'code')):sha(p) for p in sorted((root/'code').rglob('*.py'))},
                  bootstrap_seed=20261028,bootstrap_samples=20000,
                  alpha_week=.025,sequential_alpha_rule='.05/(week_index*(week_index+1)); first week index 1',
                  ci_quantiles=[.025/(2*56),1-.025/(2*56)],primary_horizon=21600,
                  min_primary_targets=300,min_days=7,practical_gain=.05,text_relative_floor=.99,
                  purpose='future confirmation only; no live consumer or promotion command')
    write_json(root/'manifest.json',manifest)
    print(json.dumps({'phase':'sealed','manifest_sha256':sha(root/'manifest.json'),'primary':7,'week':manifest['week']}),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--rounds',required=True);ap.add_argument('--snapshot',required=True)
    ap.add_argument('--incumbent',required=True);ap.add_argument('--out',required=True);ap.add_argument('--present-refit')
    main(ap.parse_args())

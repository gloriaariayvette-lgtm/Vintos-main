#!/usr/bin/env python3
"""One closed-week evaluation of sealed parameters. No fitting or live consumers."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import numpy as np
import torch
from data import (SOURCES,HORIZONS,TZ,boundary,scratch,sha,write_json,features,horizon_pairs,
                  split_pairs,ranks,begin_evaluation,paired_interval)
from scan import SelectiveScan,states
from run import query_rows


def score(args):
    sealed=Path(args.sealed);manifest=json.loads((sealed/'manifest.json').read_text())
    pass_horizons=manifest['pass_horizons_seconds']
    if (manifest['primary_horizon'] not in pass_horizons or
            any(h not in HORIZONS or h>=86400 for h in pass_horizons)):
        raise ValueError('invalid weekly pass horizons; 24h is descriptive only')
    for name,expected in manifest['code'].items():
        if sha(Path(__file__).resolve().parents[2]/name)!=expected:
            raise ValueError('run the exact sealed executable, not another checkout')
    # Consume the exclusive attempt before opening the new numeric snapshot.
    # Failure/insufficient coverage is terminal; never remove this receipt.
    begin_evaluation(sealed,manifest)
    root=scratch(args.out)
    with np.load(args.snapshot,allow_pickle=False) as d:data={k:d[k] for k in d.files}
    t=data['t'];emo=data['emo'];mask=np.isfinite(emo).all(1)
    if not len(t):
        write_json(root/'fresh-report.json',{'status':'insufficient','primary_passes':False,'n':0})
        return
    start,end=map(boundary,manifest['week'])
    if np.any(t>=end):raise ValueError('snapshot includes outcomes after registered block')
    ids=data['text_i'];exact=data['text_exact'];vectors=data['text_vectors'];sources=data['text_source']
    ti=np.flatnonzero((t[ids]>=start)&(t[ids]<end)&exact&(ids>0))
    _,q,last,recent,before=query_rows(data,t,sealed/'incumbent.npz')
    _,strong,_,_,_=query_rows(data,t,sealed/'present-refit.npz')
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
    from latent_stream_model import Model
    incumbent=Model(sealed/'incumbent.npz')
    controls_text={'present':q[ti]@vectors[ti].T,'present_refit':strong[ti]@vectors[ti].T,
                   'last':last[ti]@vectors[ti].T,'recent':recent[ti]@vectors[ti].T}
    baseline_rr={k:1/ranks(v,np.arange(len(ti))) for k,v in controls_text.items()} if len(ti) else {}
    report={'week':manifest['week'],'manifest_sha256':sha(sealed/'manifest.json'),
            'snapshot_sha256':sha(args.snapshot),'candidates':{},'primary_candidate':manifest['selected_primary'],
            'primary_passes':False,'no_runtime_changes':True,'continuity':'unproved; retrieval is a next-event proxy'}
    dt=np.r_[60,np.diff(t)].astype(np.float32)
    for c in manifest['candidates']:
        number=c['round'];p=sealed/('candidate-'+str(number))
        with np.load(p/'readouts.npz',allow_pickle=False) as z:a={k:z[k] for k in z.files}
        present,history,last_vec,em,mu,sd=features(t,data['source'],emo,data['text'],data['numeric'],0,stats=(a['emotion_mu'],a['emotion_sd']))
        z=(data['text']-a['projection_mu'])@a['projection'];z[np.linalg.norm(data['text'],axis=1)==0]=0
        z=np.pad(z,((0,0),(0,32-z.shape[1])))
        x=np.clip(np.concatenate([present,z],axis=1),-10,10).astype(np.float32)
        model=SelectiveScan(x.shape[1]);model.load_state_dict(torch.load(p/'scan.pt',map_location='cpu',weights_only=True))
        state=states(model,x,dt);reset=states(model,x,dt,True)
        state=(state-a.get('state_mu',0))/a.get('state_sd',1);reset=(reset-a.get('state_mu',0))/a.get('state_sd',1)
        metrics={}
        for h in HORIZONS:
            key=str(h);pairs=split_pairs(horizon_pairs(t,mask,int(h)),t,start,end)
            if not len(pairs) or key+'_selective' not in a:
                metrics[key]={'status':'insufficient','n':len(pairs),'passes':False};continue
            origin,outcome=pairs.T;base=em[origin]+present[origin]@a[key+'_present']*sd
            hist=base+history[origin]@a[key+'_history']*sd
            anchor=hist if c['anchor_history'] else base
            predictions={'persistence':em[origin],'present':base,'history':hist,
                         'reset':anchor+reset[origin]@a[key+'_reset']*sd,
                         'climatology':np.tile(a.get('climatology',mu),(len(origin),1)),
                         'selective':anchor+state[origin]@a[key+'_selective']*sd}
            if (p/'schedule.npz').exists():
                with np.load(p/'schedule.npz',allow_pickle=False) as controls:
                    if key+'_present_text' in controls:
                        lastz=(last_vec[origin]-a['projection_mu'])@a['projection']
                        lastz[np.linalg.norm(last_vec[origin],axis=1)==0]=0
                        strong_present=em[origin]+np.concatenate([present[origin],lastz],axis=1)@controls[key+'_present_text']*sd
                        predictions['present_text']=strong_present
                        predictions['history_text']=strong_present+history[origin]@controls[key+'_history_text']*sd
            errors={k:np.mean(((v-emo[outcome])/sd)**2,axis=1) for k,v in predictions.items()}
            means={k:float(v.mean()) for k,v in errors.items()}
            days=np.array([datetime.fromtimestamp(at,TZ).date().isoformat() for at in t[origin]])
            diffs=np.column_stack([v-errors['selective'] for k,v in errors.items() if k!='selective'])
            ci=paired_interval(diffs,days,manifest['ci_quantiles'],manifest['bootstrap_samples'])
            enough=len(origin)>=manifest['min_primary_targets'] and len(set(days))==manifest['min_days']
            best=min(v for k,v in means.items() if k!='selective')
            gain=1-means['selective']/best if best>0 else None
            eligible=int(h) in pass_horizons
            metrics[key]={'n':len(origin),'days':len(set(days)),'mse':means,'gain_vs_best_control':gain,
                          'adjusted_gain_interval':ci,'enough_data':bool(enough),
                          'eligible_for_pass':eligible,
                          'status':'scored' if eligible else 'descriptive_only',
                          'passes':bool(eligible and enough and gain is not None and gain>=manifest['practical_gain'] and ci[0]>0)}
        text_report={'n':len(ti),'status':'insufficient','passes':False}
        if len(ti):
            correction=(state[before[ti]]@a['text_W'])@incumbent.a['P'].T
            scores=(q[ti]+float(a['alpha'])*correction)@vectors[ti].T
            rr=1/ranks(scores,np.arange(len(ti)))
            days=np.array([datetime.fromtimestamp(at,TZ).date().isoformat() for at in t[ids[ti]]])
            diffs=np.column_stack([rr-v for v in baseline_rr.values()])
            ci=paired_interval(diffs,days,manifest['ci_quantiles'],manifest['bootstrap_samples'])
            best=max(float(v.mean()) for v in baseline_rr.values());floor=(1-manifest['text_relative_floor'])*best
            enough=len(ti)>=100 and len(set(days))==7
            text_report=dict(n=len(ti),days=len(set(days)),mrr={'selective':float(rr.mean()),**{k:float(v.mean()) for k,v in baseline_rr.items()}},
                             adjusted_gain_interval=ci,alpha=float(a['alpha']),enough_data=bool(enough),
                             passes=bool(enough and float(rr.mean())>=manifest['text_relative_floor']*best and ci[0]>=-floor),
                             per_source={SOURCES[int(s)]:{'n':int((sources[ti]==s).sum()),'selective_mrr':float(rr[sources[ti]==s].mean()),
                                                         'present_refit_mrr':float(baseline_rr['present_refit'][sources[ti]==s].mean())} for s in set(sources[ti])})
            if number>=4:
                similarities={k:[] for k in ('state','present','present_refit','recent')}
                for k,target in enumerate(ti):
                    bank=np.flatnonzero((t[ids]<t[ids[target]])&(t[ids]>=t[ids[target]]-14*86400))[-2048:]
                    if not len(bank):continue
                    for name,query in [('state',q[target]+.1*correction[k]),('present',q[target]),('present_refit',strong[target])]:
                        rank=vectors[bank]@query-.01*(t[ids[target]]-t[ids[bank]])/(3*86400)
                        chosen=bank[np.argsort(rank)[-2:]]
                        similarities[name].append(float(np.mean(vectors[chosen]@vectors[target])))
                    similarities['recent'].append(float(np.mean(vectors[bank[-2:]]@vectors[target])))
                text_report['retrieval_proxy']={k:{'n':len(v),'mean':float(np.mean(v)) if v else None} for k,v in similarities.items()}
        # Auxiliary surprise is measured only where the event's source/gap is
        # realized. Macro accuracy prevents Lab volume disguising other sources.
        frame=np.flatnonzero((t>=start)&(t<end)&(np.arange(len(t))>0));b=frame-1
        labels=np.argmax(data['source'],axis=1)
        with torch.no_grad():
            logits=model.source(torch.from_numpy((state*a.get('state_sd',1)+a.get('state_mu',0))[b].astype(np.float32))).numpy()
            gap=model.gap(torch.from_numpy((state*a.get('state_sd',1)+a.get('state_mu',0))[b].astype(np.float32))).numpy().flatten()
        pred=logits.argmax(1);truth=labels[frame]
        aux={'n':len(frame),'source_accuracy':float(np.mean(pred==truth)) if len(frame) else None,
             'source_persistence_accuracy':float(np.mean(labels[b]==truth)) if len(frame) else None,
             'source_macro_accuracy':float(np.mean([np.mean(pred[truth==s]==s) for s in set(truth)])) if len(frame) else None,
             'log_gap_mse':float(np.mean((gap-np.log1p(dt[frame]/60))**2)) if len(frame) else None,
             'previous_log_gap_mse':float(np.mean((np.log1p(dt[b]/60)-np.log1p(dt[frame]/60))**2)) if len(frame) else None,
             'meaning':'priority source of an atomic timestamp batch; raw errors, not confidence or intent probabilities'}
        if (p/'schedule.npz').exists() and len(frame):
            with np.load(p/'schedule.npz',allow_pickle=False) as schedule:
                keys=labels[b]*24+np.array([datetime.fromtimestamp(at,TZ).hour for at in t[b]])
                prob=schedule['prob'][keys]
                aux['clock_source_accuracy']=float(np.mean(prob.argmax(1)==truth))
                aux['clock_source_macro_accuracy']=float(np.mean([np.mean(prob.argmax(1)[truth==s]==s) for s in set(truth)]))
                aux['clock_log_gap_mse']=float(np.mean((schedule['log_gap'][keys]-np.log1p(dt[frame]/60))**2))
        report['candidates'][str(number)]={'emotion':metrics,'text':text_report,'anticipation':aux}
        if number==manifest['selected_primary']:
            report['primary_passes']=bool(metrics[str(manifest['primary_horizon'])]['passes'] and text_report['passes'])
    write_json(root/'fresh-report.json',report)
    print(json.dumps({'primary_passes':report['primary_passes'],'report_sha256':sha(root/'fresh-report.json')}),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--sealed',required=True);ap.add_argument('--snapshot',required=True);ap.add_argument('--out',required=True)
    score(ap.parse_args())

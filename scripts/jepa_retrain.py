#!/usr/bin/env python3
"""Reproducible CPU retraining in an explicit scratch directory; never installs checkpoints.
Only aggregate reports leave this command. Conversation text is used in memory and is not saved.
"""
import argparse
import json
import os
from pathlib import Path
import sys


def run(out):
    import numpy as np
    import torch
    torch.set_num_threads(4)
    import jepa_predictor as jp
    import jepa_self_head as sh
    import jepa_readout as rr
    out=Path(out).resolve()
    live=Path(jp.WS).resolve()
    if out==live or live in out.parents:raise ValueError('output must be outside the live workspace')
    if (out/'report.json').exists():raise ValueError('use a new output directory; do not overwrite an evaluated design')
    out.mkdir(parents=True,exist_ok=True)
    enc=jp.encoder(); exs=sh.exchanges(); cache=rr.Embeddings(enc)
    report={'protocol':{'boundaries':rr.BOUNDARIES,'selection':'validation MRR, then cosine error',
        'confidence':'fit only calibration days; evaluate on later days','test_reuse':'existing benchmark; previously inspected in audit, no test tuning',
        'clean_exchanges':len(exs),'encoder':'unchanged frozen encoder','outputs':'scratch only'},'heads':{}}
    ck=torch.load(jp.MODEL,map_location='cpu',weights_only=False)
    net=jp.make_net(ck['dim'],architecture=ck.get('architecture','shared-v1'));net.load_state_dict(ck['state']);net.eval()
    oldself=sh.load_model(); oldcache=sh._Cache(enc,persist=False)
    def old(mode):
        def compare(rows,indices):
            pred=[];valid=[]
            for i in indices:
                r=rows[i];cut=[e for e in exs if e['at']<r['target_at']]
                if mode=='gloria':
                    turns=[]
                    for e in cut:
                        if e['her']:turns.append({'role':'user','content':e['her'],'timestamp':e['ts']})
                        if e['his']:turns.append({'role':'assistant','content':e['his'],'timestamp':e['ts']})
                    text=jp.format_context(turns[-jp.CTX_TURNS:],ck.get('context_schema','legacy-concat-v1'))
                    x=np.asarray(enc.encode([text],show_progress_bar=False),dtype='float32')
                    with torch.no_grad():p=net(torch.tensor(x))[0].numpy()[0]
                    good=r['target_at']>os.path.getmtime(jp.MODEL)
                else:
                    sm='on_message' if mode.endswith('on_message') else 'ahead'
                    ctx=sh._context(cut,r['day']);ctx.update(her_now=r['now'],cut_n=len(cut))
                    x,comps,_,_=sh.featurize([ctx],enc,oldcache,mode=sm,exs=cut)
                    p=sh._predict(oldself['modes'][sm],x,comps,sm)[0]
                    last_day=max(str(oldself['meta'].get('trained_at',''))[:10],
                                 str(oldself['modes'][sm]['meta'].get('last_target',''))[:10])
                    good=r['day']>last_day
                pred.append(p);valid.append(good)
            return rr.units(pred),np.asarray(valid)
        return compare
    for mode in rr.MODES:
        rows=rr.samples(exs,mode)
        result=rr.train_mode(rows,cache,mode,out,old=old(mode))
        report['heads'][mode]=result
        print(json.dumps({'completed':mode,'result':result}),flush=True)
        (out/'report.json').write_text(json.dumps(report,indent=2))
    import lam
    report['lam']=lam.train_readout(enc,exs,out)
    print(json.dumps({'completed':'lam','result':report['lam']}),flush=True)
    report['presence']=train_presence(enc,exs,out)
    print(json.dumps({'completed':'presence','result':report['presence']}),flush=True)
    report['checkpoints']={p.name:__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in out.glob('*.npz')}
    (out/'report.json').write_text(json.dumps(report,indent=2))
    return report


def train_presence(enc,exs,out):
    import numpy as np
    import jepa_predictor as jp
    import jepa_readout as rr
    labels={r['id']:r for r in jp.presence_records() if r.get('id') and isinstance(r.get('composite'),(int,float))}
    # Retain only ids, times and scores. Never copy label notes or conversations.
    retained=[{k:r[k] for k in ('id','timestamp','audited_at','composite') if k in r} for r in labels.values()]
    (Path(out)/'presence-audit-history.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in retained))
    import jepa_self_head as sh
    turns=jp.training_turns(); rows=[]
    by_id={jp._rid(t):t for t in turns if t.get('role')=='assistant'}
    for label_id,label in labels.items():
        t=by_id.get(label_id)
        at=sh._epoch((t or {}).get('timestamp') or label.get('timestamp'))
        if at is None:continue
        matches=[e for e in exs if e['his'] and abs(e['at']-at)<1]
        if t is None and len(matches)!=1:continue
        cut=[e for e in exs if e['at']<at]
        if not cut or not any(e['his'] for e in cut):continue
        ctx=rr.context(cut,'self_ahead');ctx.update(y=float(label['composite']),day=__import__('datetime').datetime.fromtimestamp(at).date().isoformat())
        rows.append(ctx)
    rows.sort(key=lambda r:r['day'])
    days=sorted(set(r['day'] for r in rows))
    if len(days)<4:return {'state':'insufficient distinct days','retained_labels':len(retained),'joined':len(rows)}
    # Preserve day blocks with the available rubric labels; no invented historical labels.
    bounds=(days[-3],days[-2],days[-1]); sp=np.asarray([rr.split(r['day'],bounds) for r in rows]);tr,va,ca,te=[np.flatnonzero(sp==i) for i in range(4)]
    a=rr.arrays(rows,rr.Embeddings(enc)); y=np.asarray([r['y'] for r in rows]);pca=np.linalg.svd(a[1][tr],full_matrices=False)[2][:min(4,len(tr))].T
    h=rr.features(a,pca); mean=y[tr].mean(); best=None
    for penalty in (1.,10.,100.,1000.):
        w=np.linalg.solve(h[tr].T@h[tr]+penalty*np.eye(h.shape[1]),h[tr].T@(y[tr]-mean))
        loss=np.mean(abs(np.clip(mean+h[va]@w,0,1)-y[va]))
        if best is None or loss<best[0]:best=(loss,w,penalty)
    pred=np.clip(mean+h[te]@best[1],0,1); prev=np.asarray([y[max(0,i-1)] for i in te])
    result={'retained_labels':len(retained),'joined':len(rows),'blocks':{k:len(i) for k,i in zip(('train','validation','calibration','test'),(tr,va,ca,te))},
        'boundaries':bounds,'test_mae':float(np.mean(abs(pred-y[te]))),'training_mean_mae':float(np.mean(abs(mean-y[te]))),
        'persistence_mae':float(np.mean(abs(prev-y[te]))),'training_mean':float(mean),'lambda':best[2],
        'calibration_mae':float(np.mean(abs(np.clip(mean+h[ca]@best[1],0,1)-y[ca]))),
        'limitation':'tiny rubric-labelled sample; diagnostic fit, not an established accuracy gain'}
    np.savez_compressed(Path(out)/'presence.npz',projection=pca,W=best[1],mean=mean,meta=json.dumps(result))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
    run(a.out)

if __name__=='__main__':main()

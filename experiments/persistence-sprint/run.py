#!/usr/bin/env python3
"""One-receipt-per-round offline CPU training and historical development scoring."""
import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
import torch
from torch import nn
from data import (SOURCES,HORIZONS,ROUNDS,TZ,boundary,horizon_pairs,split_pairs,
                  features,projected_text,ridge,ranks,scratch,sha,write_json)
from scan import SelectiveScan,states


def fit_scan(x,dt,t,emo,em,scale,z,text_mask,source,train_end,aux,out,state_only=False,epochs=4):
    torch.manual_seed(20261028);torch.set_num_threads(1)
    model=SelectiveScan(x.shape[1]);opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.05)
    n=int(np.searchsorted(t,train_end));target=np.zeros((n,7,11),np.float32);mask=np.zeros((n,7),bool)
    for j,h in enumerate(HORIZONS):
        pairs=split_pairs(horizon_pairs(t,np.isfinite(emo).all(1),int(h)),t,-np.inf,train_end)
        if len(pairs):
            a,b=pairs.T;target[a,j]=(emo[b]-em[a])/scale;mask[a,j]=True
    xt=torch.from_numpy(x[:n]);dtt=torch.from_numpy(dt[:n]);yt=torch.from_numpy(target);mt=torch.from_numpy(mask)
    train_text=np.flatnonzero(text_mask&(t<train_end));candidates=torch.from_numpy(z[train_text])
    pos={i:k for k,i in enumerate(train_text)}
    labels=np.argmax(source,axis=1);freq=np.bincount(labels[:n],minlength=len(SOURCES))
    cw=torch.tensor(n/np.maximum(freq,1)/len(SOURCES),dtype=torch.float32)
    logs=[]
    for epoch in range(epochs):
        model.train();state=None;sums=Counter();counts=Counter()
        for start in range(0,n,128):
            end=min(n,start+128);chunk=xt[start:end]
            h,state=model(chunk,dtt[start:end],state)
            state=state.detach();pred=model.emotion(torch.cat([chunk*0 if state_only else chunk,h],1)).reshape(-1,7,11)
            m=mt[start:end];loss=pred.sum()*0
            if m.any():
                term=((pred-yt[start:end])**2).mean(2)[m].mean()
                loss=loss+term;sums['emotion']+=float(term.detach())*int(m.sum());counts['emotion']+=int(m.sum())
            if aux:
                valid=min(end,n-1)-start
                if valid>0:
                    st=torch.tensor(labels[start+1:start+valid+1]);gp=torch.from_numpy(np.log1p(dt[start+1:start+valid+1]/60))
                    ls=nn.functional.cross_entropy(model.source(h[:valid]),st,weight=cw)
                    lg=nn.functional.mse_loss(model.gap(h[:valid]).flatten(),gp)
                    loss=loss+.1*ls+.1*lg
                    sums['source']+=float(ls.detach())*valid;sums['gap']+=float(lg.detach())*valid
                    counts['source']+=valid;counts['gap']+=valid
                ids=[i for i in train_text if start<i<=end and i<n]
                if ids:
                    # Forecast each unique text from the immediately preceding
                    # atomic state, never from the target-containing batch.
                    before=torch.tensor([i-start-1 for i in ids]);positive=torch.tensor([pos[i] for i in ids])
                    lt=nn.functional.cross_entropy(model.text(h[before])@candidates.T/.1,positive)
                    loss=loss+.2*lt;sums['text']+=float(lt.detach())*len(ids);counts['text']+=len(ids)
            if loss.requires_grad and (m.any() or aux):
                opt.zero_grad();loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.);opt.step()
        row={'epoch':epoch+1,**{k:sums[k]/counts[k] for k in counts},'targets':dict(counts)}
        logs.append(row);print(json.dumps({'phase':'pretrain',**row}),flush=True)
    torch.save(model.state_dict(),out/'scan.pt')
    return model,logs


def emotion_readouts(t,emo,em,present,history,state,reset,sd,train_end,start,end,anchor_history=False):
    output={};weights={}
    is_e=np.isfinite(emo).all(1)
    for j,h in enumerate(HORIZONS):
        all_pairs=horizon_pairs(t,is_e,int(h));tr=split_pairs(all_pairs,t,-np.inf,train_end);te=split_pairs(all_pairs,t,start,end)
        if len(tr)<30 or not len(te):
            output[str(h)]={'status':'insufficient','n_train':len(tr),'n':len(te)};continue
        a,b=tr.T;c,d=te.T
        y=(emo[b]-em[a])/sd
        # Baseline first; every state correction is a strongly regularized
        # residual to the same fitted present-only predictor, zero if no signal.
        wp=ridge(present[a],y);base=em[c]+present[c]@wp*sd
        residual=y-present[a]@wp
        wh=ridge(history[a],residual);ws=ridge(state[a],residual);wr=ridge(reset[a],residual)
        if anchor_history:
            residual=residual-history[a]@wh
            ws=ridge(state[a],residual);wr=ridge(reset[a],residual)
        anchor=base+history[c]@wh*sd if anchor_history else base
        predictions={'persistence':em[c],'present':base,'history':base+history[c]@wh*sd,
                     'selective':anchor+state[c]@ws*sd,'reset':anchor+reset[c]@wr*sd}
        # Climatology is trained, not fitted to the evaluated day.
        predictions['climatology']=np.tile(emo[np.isfinite(emo).all(1)&(t<train_end)].mean(0),(len(c),1))
        errs={k:np.mean(((v-emo[d])/sd)**2,axis=1) for k,v in predictions.items()}
        means={k:float(v.mean()) for k,v in errs.items()}
        daily={}
        days=np.array([datetime.fromtimestamp(at,TZ).date().isoformat() for at in t[c]])
        for day in sorted(set(days)):
            ix=days==day;daily[day]={'n':int(ix.sum()),**{k:float(v[ix].mean()) for k,v in errs.items()}}
        overnight=np.array([datetime.fromtimestamp(t[a],TZ).date()!=datetime.fromtimestamp(t[b],TZ).date() for a,b in te])
        strength=np.linalg.norm((em[c]-emo[np.flatnonzero(is_e&(t<train_end))].mean(0))/sd,axis=1)
        threshold=float(np.quantile(np.linalg.norm((emo[is_e&(t<train_end)]-emo[is_e&(t<train_end)].mean(0))/sd,axis=1),.9))
        strong=strength>=threshold
        output[str(h)]={'n_train':len(tr),'n':len(te),'mse':means,'daily':daily,
                        'gain_vs_best_control':1-means['selective']/min(means[k] for k in ('persistence','present','history','reset','climatology')),
                        'overnight':{'n':int(overnight.sum()),**{k:float(v[overnight].mean()) if overnight.any() else None for k,v in errs.items()}},
                        'strong_moment':{'n':int(strong.sum()),**{k:float(v[strong].mean()) if strong.any() else None for k,v in errs.items()}}}
        weights[str(h)]={'present':wp,'history':wh,'selective':ws,'reset':wr}
    return output,weights


def query_rows(zdata,t,incumbent):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
    from latent_stream_model import Model,State
    model=Model(incumbent);runtime=State(model)
    ids=zdata['text_i'];vectors=zdata['text_vectors'];exact=zdata['text_exact'];source=zdata['text_source']
    queries=[];six=[];last=[];before=[];updates={}
    for k,i in enumerate(ids):updates.setdefault(int(i),[]).append(k)
    for i,at in enumerate(t):
        for k in updates.get(i,[]):
            queries.append(model.query(runtime));last.append(runtime.last.copy());six.append(runtime.mean());before.append(max(0,i-1))
        for k in updates.get(i,[]):
            runtime.advance({'t':datetime.fromtimestamp(at,TZ),'id':'sprint-text-'+str(k),'source':SOURCES[int(source[k])],'vec':vectors[k]})
        if np.isfinite(zdata['emo'][i]).all():runtime.advance({'t':datetime.fromtimestamp(at,TZ),'id':'sprint-emotion-'+str(i),'source':'emotion','emo':zdata['emo'][i]})
    queries=np.asarray(queries);last=np.asarray(last);six=np.asarray(six);before=np.asarray(before)
    return model,queries,last,six,before


def text_evaluation(zdata,t,present,state,train_end,val_start,test_start,end,round_no,incumbent):
    model,queries,last,six,before=query_rows(zdata,t,incumbent)
    if boundary(model.meta['val_from'])>train_end:raise ValueError('incumbent training crosses sprint training boundary')
    ids=zdata['text_i'];vectors=zdata['text_vectors'];exact=zdata['text_exact'];source=zdata['text_source']
    # Model clock is advanced only by its original event sources, preserving its
    # defined serving semantics when other modalities arrive between them.
    train=np.flatnonzero((t[ids]<train_end)&exact&(ids>0))
    val=np.flatnonzero((t[ids]>=val_start)&(t[ids]<test_start)&exact&(ids>0))
    test=np.flatnonzero((t[ids]>=test_start)&(t[ids]<end)&exact&(ids>0))
    z=(vectors-model.a['mu'])@model.a['P']
    norms=np.maximum(np.linalg.norm(z,axis=1,keepdims=True),1e-12);z=z/norms
    residual=z[train]-(queries[train]-model.a['mu'])@model.a['P']/np.maximum(np.linalg.norm((queries[train]-model.a['mu'])@model.a['P'],axis=1,keepdims=True),1e-12)
    w=ridge(state[before[train]],residual)
    correction=(state[before]@w)@model.a['P'].T
    def score(which,alpha):
        q=queries[which]+alpha*correction[which]
        return q@vectors[which].T
    choices=[0.] if round_no<3 else [0.,.05,.1,.25]
    selection={str(a):float((1/ranks(score(val,a),np.arange(len(val)))).mean()) if len(val) else None for a in choices}
    alpha=max(choices,key=lambda a:selection[str(a)] if selection[str(a)] is not None else -1)
    result={'n_train':len(train),'n_val':len(val),'n':len(test),'alpha':alpha,'validation':selection,
            'incumbent_sha256':model.checkpoint_id,'source_counts':dict(Counter(SOURCES[int(s)] for s in source[test]))}
    if not len(test):return result,{'alpha':alpha,'text_W':w},queries,correction
    scores={'present':score(test,0.),'selective':score(test,alpha),'last':last[test]@vectors[test].T,'recent':six[test]@vectors[test].T}
    rr={k:1/ranks(v,np.arange(len(test))) for k,v in scores.items()}
    result['mrr']={k:float(v.mean()) for k,v in rr.items()}
    result['per_source']={SOURCES[int(s)]:{'n':int((source[test]==s).sum()),**{k:float(v[source[test]==s].mean()) for k,v in rr.items()}} for s in set(source[test])}
    # Rank past-only memory by the current query; return selection is frozen
    # before opening the outcome. This is a next-event semantic proxy only.
    if round_no>=4:
        sims={k:[] for k in ('state_key','present_key','recent')}
        for target in test:
            bank=np.flatnonzero((t[ids]<t[ids[target]])&(t[ids]>=t[ids[target]]-14*86400))[-2048:]
            if not len(bank):continue
            for key,q in [('state_key',queries[target]+.1*correction[target]),('present_key',queries[target])]:
                weights=vectors[bank]@q + .01*(-(t[ids[target]]-t[ids[bank]])/(3*86400))
                picks=bank[np.argsort(weights)[-2:]];sims[key].append(float(np.mean(vectors[picks]@vectors[target])))
            sims['recent'].append(float(np.mean(vectors[bank[-2:]]@vectors[target])))
        result['retrieval_proxy']={k:{'n':len(v),'mean':float(np.mean(v)) if v else None} for k,v in sims.items()}
    return result,{'alpha':alpha,'text_W':w},queries,correction


def run(args):
    root=scratch(args.out);started=time.time()
    number,val_day,test_day,end_day=ROUNDS[args.round-1]
    train_end=boundary(val_day);test_start=boundary(test_day);end=boundary(end_day)
    with np.load(args.snapshot,allow_pickle=False) as f:zdata={k:f[k] for k in f.files}
    t=zdata['t'];emo=zdata['emo'];text=zdata['text'];source=zdata['source']
    if np.any(t>=boundary('2026-10-23')):raise ValueError('sprint snapshot crosses protected cutoff')
    present,history,last,em,mu,sd=features(t,source,emo,text,zdata['numeric'],train_end)
    mask=np.linalg.norm(text,axis=1)>0
    z,zmu,p=projected_text(text,mask,train_end,t)
    # Fixed 32-dimensional projection, padded only for tiny synthetic fixtures.
    z=np.pad(z,((0,0),(0,32-z.shape[1])))
    x=np.concatenate([present,z],axis=1).astype(np.float32)
    x=np.clip(x,-10,10);dt=np.r_[60,np.diff(t)].astype(np.float32)
    model,logs=fit_scan(x,dt,t,emo,em,sd,z,mask,source,train_end,number>=2,root,number>=7,20 if number>=8 else 4)
    state=states(model,x,dt);reset=states(model,x,dt,True)
    smu=state[t<train_end].mean(0) if number>=5 else np.zeros(24)
    ssd=np.maximum(state[t<train_end].std(0),.01) if number>=5 else np.ones(24)
    state=(state-smu)/ssd;reset=(reset-smu)/ssd
    validation,weights=emotion_readouts(t,emo,em,present,history,state,reset,sd,train_end,train_end,test_start,number>=6)
    metrics,check_weights=emotion_readouts(t,emo,em,present,history,state,reset,sd,train_end,test_start,end,number>=6)
    if check_weights:weights=check_weights
    tx,tw,_,_=text_evaluation(zdata,t,present,state,train_end,train_end,test_start,end,number,args.incumbent)
    arrays={'projection':p,'projection_mu':zmu,'emotion_mu':mu,'emotion_sd':sd,'text_W':tw['text_W'],'alpha':np.array(tw['alpha']),
            'state_mu':smu,'state_sd':ssd,'climatology':emo[np.isfinite(emo).all(1)&(t<train_end)].mean(0)}
    for h,ws in weights.items():
        arrays.update({h+'_'+name:w for name,w in ws.items()})
    np.savez_compressed(root/'readouts.npz',**arrays)
    np.savez_compressed(root/'states.npz',state=state,reset=reset)
    report=dict(round=number,kind='historical development; previously inspected era, not prospective confirmation',
                change=['emotion-only selective state','add source/gap/projected-text losses','add present-score residual','add state-keyed retrieval','standardize readout state','anchor on observed history','state-only emotion pretraining','twenty pretraining epochs'][number-1],
                split={'train_before':val_day,'validation':[val_day,test_day],'check':[test_day,end_day]},
                snapshot_sha256=sha(args.snapshot),code={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},
                checkpoint_sha256=sha(root/'scan.pt'),readouts_sha256=sha(root/'readouts.npz'),
                train_logs=logs,validation_emotion=validation,emotion=metrics,text=tx,
                parameters=sum(p.numel() for p in model.parameters()),seconds=time.time()-started,
                created_at=datetime.now(TZ).isoformat(),eligible_to_steer=False)
    write_json(root/'report.json',report)
    print(json.dumps({'phase':'done','round':number,'seconds':report['seconds'],'primary':metrics.get('21600'),'text':tx}),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--snapshot',required=True);ap.add_argument('--incumbent',required=True)
    ap.add_argument('--round',required=True,type=int,choices=range(1,9));ap.add_argument('--out',required=True)
    run(ap.parse_args())

#!/usr/bin/env python3
"""Capture admitted history to numeric scratch, never writing live stores."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timedelta
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import numpy as np
from data import SOURCES,TZ,boundary,timestamp,scratch,sha,write_json


def main():
    if getattr(sys,'_persistence_guard_root',None)!=str(Path(os.environ.get('PERSISTENCE_SCRATCH','')).resolve()):
        raise RuntimeError('collector requires launch.py with its installed scratch audit hook')
    ap=argparse.ArgumentParser();ap.add_argument('--memory',required=True);ap.add_argument('--out',required=True)
    ap.add_argument('--cache',required=True);ap.add_argument('--encoder',required=True)
    ap.add_argument('--through',choices=['2026-10-22','2026-11-06'],default='2026-10-22')
    args=ap.parse_args()
    next_day=(datetime.fromisoformat(args.through)+timedelta(days=1)).date().isoformat()
    if args.through!='2026-10-22' and datetime.now(TZ).date().isoformat()<next_day:
        raise ValueError('fresh week has not closed; no sources opened')
    root=scratch(args.out);source=Path(args.memory).resolve();mem=root/'memory';mem.mkdir()
    cutoff=boundary(next_day)
    os.environ.update(SPARK_WORKSPACE=str(root),HOME=str(root/'home'),TMPDIR=str(root),
                      HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',CUDA_VISIBLE_DEVICES='',
                      HF_HOME=str(Path(args.encoder).parents[3]),HF_HUB_CACHE=str(Path(args.encoder).parents[2]),
                      HF_MODULES_CACHE=str(root/'modules'),TZ='America/Chicago',PYTHONDONTWRITEBYTECODE='1')
    tempfile.tempdir=str(root);time.tzset();sys.dont_write_bytecode=True
    def guard(event,a):
        if event=='open' and isinstance(a[0],(str,bytes,os.PathLike)):
            mode,flags=a[1:3]
            writes=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if writes and not Path(os.fsdecode(a[0])).resolve().is_relative_to(root):raise PermissionError('outside scratch')
        if event in ('socket.connect','socket.sendto'):raise PermissionError('network denied')
    sys.addaudithook(guard)
    # Copy only current, named admission stores; no wildcard backups or erased versions.
    patterns=('daily-inner-life-*.md','daily-creative-*.md','interaction-ledger.json',
              'chat-canonical.jsonl','chat-history-merged.json','post-turn-record.jsonl','jepa-ledger-floor.txt')
    provenance=[]
    for pattern in patterns:
        for f in sorted(source.glob(pattern)):
            if not f.is_file():continue
            match=re.search(r'2026-\d\d-\d\d',f.name)
            if match and match.group()>=next_day:continue
            shutil.copyfile(f,mem/f.name);provenance.append({'file':f.name,'sha256':sha(mem/f.name)})
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
    import latent_feed as F
    import jepa_self_head as SH
    from latent_stream_model import AXES
    import torch
    torch.set_num_threads(2)
    with contextlib.redirect_stdout(io.StringIO()):
        exs=[e for e in SH.exchanges() if e['at']<cutoff]
        texts=F.text_events(mem,exs=exs)
    # Mutable current threads/dream summaries have no historical availability proof.
    # Keep them as censused-but-excluded instead of backdating today's final contents.
    texts=[e for e in texts if timestamp(e['t'].isoformat())<cutoff and e['source']!='thread']
    events=[];excluded=Counter();raw_counts=Counter();groups=defaultdict(list)
    def add(at,source,emo=None,text=None,num=None,exact=True):
        try:at=timestamp(at)
        except (ValueError,TypeError,OverflowError):excluded['invalid_time']+=1;return
        if at>=cutoff:return
        raw_counts[source]+=1
        events.append(dict(t=at,source=source,emo=emo,text=text,num=num,exact=exact))
    for e in texts:add(e['t'].isoformat(),e['source'],text=e['text'],exact=e.get('t_exact',True))
    def rows(name):
        p=source/name
        if not p.is_file():excluded['absent:'+name]+=1;return
        if p.suffix=='.jsonl':
            digest=hashlib.sha256()
            with p.open('rb') as f:
                for line in f:
                    digest.update(line)
                    try:r=json.loads(line)
                    except ValueError:excluded['malformed:'+name]+=1;continue
                    if isinstance(r,dict):yield r
            provenance.append({'file':name,'sha256':digest.hexdigest()})
        else:
            raw=p.read_bytes();provenance.append({'file':name,'sha256':hashlib.sha256(raw).hexdigest()})
            data=json.loads(raw)
            if isinstance(data,list):yield from (r for r in data if isinstance(r,dict))
    for r in rows('emotion-trajectory-dense.json'):
        v=r.get('v');at=r.get('t')
        if isinstance(v,dict):
            low={str(k).lower():v for k,v in v.items()};v=[low.get(a.lower()) for a in AXES]
        if isinstance(v,list) and len(v)==11 and np.isfinite(np.array(v,float)).all():add(at,'emotion',emo=v)
    for name,kind in [('watch-presence-history.jsonl','watch'),('sensor-reactions.jsonl','sensor'),
                      ('want-events.jsonl','want'),('avatar-presence-log.json','presence'),
                      ('chemistry-lab/notebook.jsonl','lab')]:
        for r in rows(name):
            at=next((r.get(k) for k in ('at','t','timestamp','observed_at') if r.get(k) is not None),None)
            try:at=timestamp(at)
            except (ValueError,TypeError,OverflowError):continue
            if kind=='watch':
                at+=max(0,float(r.get('age_seconds') or 0)) # do not backdate delayed health arrivals
            if kind=='sensor':
                try:at=max(at,timestamp(r.get('now')))
                except (ValueError,TypeError):pass
            if at>=cutoff:continue
            key=str(r.get('kind',r.get('sensor',r.get('event','unknown'))))
            bucket=int(hashlib.sha256(key.encode()).hexdigest()[:8],16)%8
            vec=np.zeros(12);vec[bucket]=1;vec[8]=1
            value=r.get('value');numeric=isinstance(value,(int,float)) and not isinstance(value,bool) and np.isfinite(value)
            vec[9]=float(np.clip(float(value),-1000,1000))/100 if numeric else 0
            vec[10]=float(numeric);vec[11]=float(bool(r.get('estimate',False)))
            # All rows contribute. Close 5-minute buckets before revealing their
            # counts. This bounds Lab load without sampling away its activity.
            end=(int(at)//300+1)*300
            if end<cutoff:groups[(end,kind)].append(vec);raw_counts[kind]+=1
    for (at,kind),values in groups.items():
        vec=np.asarray(values);summary=vec.mean(0);summary[:9]=np.log1p(vec[:,:9].sum(0))
        events.append(dict(t=at,source=kind,num=summary.tolist(),emo=None,text=None,exact=True))
    excluded['mutable_threads_without_arrival_history']=1
    excluded['mutable_dream_nights_without_arrival_history']=1
    # Current dreams have night labels, not an immutable arrival log. A future
    # prospective capture can admit them; no invented midnight availability here.
    cache={}
    with open(args.cache) as f:
        for line in f:
            try:r=json.loads(line);cache[r['k']]=r['v']
            except (ValueError,KeyError):continue
    todo=sorted({e['text'] for e in events if e.get('text') and e['text'] not in cache})
    if todo:
        from sentence_transformers import SentenceTransformer
        with contextlib.redirect_stdout(io.StringIO()):enc=SentenceTransformer(args.encoder,trust_remote_code=True,local_files_only=True,device='cpu')
        for start in range(0,len(todo),32):
            batch=todo[start:start+32];vectors=enc.encode(batch,show_progress_bar=False)
            vectors=vectors/np.maximum(np.linalg.norm(vectors,axis=1,keepdims=True),1e-12)
            cache.update(zip(batch,vectors.tolist()))
            print(json.dumps({'phase':'embed','done':min(start+32,len(todo)),'total':len(todo)}),flush=True)
    events.sort(key=lambda e:(e['t'],e['source']))
    # One atomic observation at each timestamp. Source is a multi-hot, not an
    # ordering that lets one simultaneous text event see another as its past.
    batches=defaultdict(list)
    for e in events:batches[e['t']].append(e)
    times=[];sources=[];emotions=[];vectors=[];numbers=[];text_meta=[]
    for at,es in sorted(batches.items()):
        emo=[e['emo'] for e in es if e.get('emo') is not None]
        txt=[e for e in es if e.get('text')]
        nums=[e['num'] for e in es if e.get('num') is not None]
        times.append(at);sources.append([float(any(e['source']==s for e in es)) for s in SOURCES])
        emotions.append(np.mean(emo,axis=0) if emo else np.full(11,np.nan))
        vectors.append(np.mean([cache[e['text']] for e in txt],axis=0) if txt else np.zeros(768))
        numbers.append(np.mean(nums,axis=0) if nums else np.zeros(12))
        for e in txt:
            text_meta.append(dict(i=len(times)-1,source=e['source'],exact=e['exact'] and len(txt)==1,
                                  vector=cache[e['text']]))
    np.savez_compressed(root/'events.npz',t=np.array(times),source=np.array(sources,np.float32),
                        emo=np.array(emotions,np.float32),text=np.array(vectors,np.float32),
                        numeric=np.array(numbers,np.float32),text_i=np.array([r['i'] for r in text_meta]),
                        text_source=np.array([SOURCES.index(r['source']) for r in text_meta]),
                        text_exact=np.array([r['exact'] for r in text_meta]),
                        text_vectors=np.array([r['vector'] for r in text_meta],np.float32))
    report=dict(captured_at=datetime.now(TZ).isoformat(),cutoff_exclusive=next_day,
                raw_rows=dict(raw_counts),atomic_steps=len(times),text_targets=len(text_meta),
                emotion_readings=int(np.isfinite(emotions).all(1).sum()),excluded=dict(excluded),
                sources=provenance,snapshot_sha256=sha(root/'events.npz'),new_embeddings=len(todo),
                limitations=['Current admitted historical text versions, not immutable arrival history',
                             'Dream and mutable thread history unavailable; excluded rather than backdated',
                             'Lab and sensors use closed five-minute count/value summaries; kind hash collisions possible'])
    write_json(root/'capture.json',report)
    print(json.dumps({k:report[k] for k in ('raw_rows','atomic_steps','text_targets','emotion_readings','new_embeddings','excluded')}),flush=True)


if __name__=='__main__':main()

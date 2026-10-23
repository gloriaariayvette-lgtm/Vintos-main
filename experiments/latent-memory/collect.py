#!/usr/bin/env python3
"""Build a private numeric snapshot from admitted source copies; no live writes.

Requires a scratch workspace and a separate source-memory path. No forecast head
is loaded; an optional fixed LAM projection only supplies comparator features.
"""
import argparse
from collections import Counter
import contextlib
from datetime import datetime
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

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source-memory',required=True);p.add_argument('--cache',required=True)
p.add_argument('--lam',required=True);p.add_argument('--encoder',required=True)
p.add_argument('--through',choices=('2026-10-22','2026-10-29'),default='2026-10-22')
a=p.parse_args()
from zoneinfo import ZoneInfo
if a.through=='2026-10-29' and datetime.now(ZoneInfo('America/Chicago')).date().isoformat()<'2026-10-30':
    raise ValueError('fresh block is not closed; collector will not open its outcomes')
cutoff='2026-10-23' if a.through=='2026-10-22' else '2026-10-30'
root=Path(os.environ['SPARK_WORKSPACE']).resolve()
if root!=Path(os.environ['LATENT_MEMORY_SCRATCH']).resolve() or '.vintos' in root.parts:
    raise ValueError('explicit private scratch required')
root.mkdir(exist_ok=True);root.chmod(0o700)
os.environ.update(HOME=str(root/'home'),TMPDIR=str(root),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
                  HF_HOME=str(Path(a.encoder).parents[3]),HF_HUB_CACHE=str(Path(a.encoder).parents[2]),
                  HF_MODULES_CACHE=str(root/'modules'),CUDA_VISIBLE_DEVICES='',TZ='America/Chicago',
                  PYTHONDONTWRITEBYTECODE='1')
time.tzset();tempfile.tempdir=str(root);sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))

def guard(event,args):
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        mode,flags=args[1:3]
        writes=(isinstance(mode,str) and any(x in mode for x in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        if writes and not Path(os.fsdecode(args[0])).resolve().is_relative_to(root):raise PermissionError('write outside experiment scratch')
    if event in ('socket.connect','socket.sendto'):raise PermissionError('network disabled')
sys.addaudithook(guard)
mem=root/'memory';mem.mkdir(exist_ok=False)
source=Path(a.source_memory).resolve();sources=[]
patterns=('emotion-trajectory-dense.json','daily-inner-life-*.md','daily-creative-*.md',
          'unfinished-threads.json','interaction-ledger.json','interaction-ledger.archive.json*',
          'chat-canonical.jsonl','chat-history-merged.json','post-turn-record.jsonl','jepa-ledger-floor.txt')
for pattern in patterns:
    for f in sorted(source.glob(pattern)):
        if not f.is_file() or f.name.endswith(('.lock','.tmp')):continue
        if any(tag in f.name.lower() for tag in ('before-forget','pre-erase','pre-purge','corrupt')):continue
        # Never ingest a future day file into this development collector.
        match=re.search(r'2026-\d\d-\d\d',f.name)
        if match and match.group()>=cutoff:continue
        dest=mem/f.name;shutil.copyfile(f,dest)
        sources.append({'name':f.name,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
import numpy as np
import torch
torch.set_num_threads(4)
import latent_feed as F
import latent_stream_replay as R
import latent_stream_export as E
import jepa_self_head as SH
import jepa_readout as RR
import lam
from latent_stream_model import digest
from zoneinfo import ZoneInfo
TZ=ZoneInfo('America/Chicago')
with contextlib.redirect_stdout(io.StringIO()):
    exs=SH.exchanges()
    exs=[x for x in exs if datetime.fromtimestamp(x['at'],TZ).date().isoformat()<cutoff]
    events=F.read_events(mem,exs=exs)
events=[e for e in events if e['t'].astimezone(TZ).date().isoformat()<cutoff]
cache={}
with open(a.cache) as f:
    for line in f:
        row=json.loads(line);cache[row['k']]=row['v']
enc=None

def encode(texts,**kwargs):
    global enc
    missing=list(dict.fromkeys(t for t in texts if t not in cache))
    if missing:
        if enc is None:
            from sentence_transformers import SentenceTransformer
            with contextlib.redirect_stdout(io.StringIO()):
                enc=SentenceTransformer(a.encoder,trust_remote_code=True,local_files_only=True,device='cpu')
        for start in range(0,len(missing),32):
            batch=missing[start:start+32]
            v=RR.units(enc.encode(batch,show_progress_bar=False))
            cache.update(zip(batch,v))
    return np.asarray([cache[t] for t in texts])
class Cached:
    def encode(self,texts,**kwargs):return encode(texts)
texts=[e['text'] for e in events if e.get('text')]
initial_cached=sum(t in cache for t in texts)
encode(texts)
for e in events:
    if e.get('text'):e['vec']=np.asarray(cache[e['text']]).tolist()
# Same causal origin/target contract, frozen earlier LAM feature projection;
# comparator readout will be refitted on the new experiment's training blocks.
with np.load(a.lam,allow_pickle=False) as z:
    projection=z['projection'];mu=z['mu'];sd=z['sd']
traj=[(e['t'],e['emo']) for e in events if 'emo' in e]
rows=lam.causal_rows(traj,exs)
arrays=RR.arrays([dict(r,target='') for r in rows],RR.Embeddings(Cached())) if rows else None
features={}
if rows:
    h=np.concatenate([(np.array([r['state'] for r in rows])-mu)/sd,
                      np.array([r['trend'] for r in rows])/sd,arrays[1]@projection,arrays[2]@projection,arrays[5]],axis=1)
    features={r['at']:v.tolist() for r,v in zip(rows,h)}
import latent_stream_linear as L
X,EM,it,ie=L.arrays(events)
metadata=[]
for e in events:
    row={k:e[k] for k in ('id','source','t_exact') if k in e}
    row['t']=e['t'].isoformat();row['t_exact']=e.get('t_exact',True)
    # Hash the repeated heading form, never publish the heading or body.
    if e['source'] in ('inner','creative'):
        head=e.get('text','').split('\n')[0]
        head=re.sub(r'\b\d{1,2}:\d\d\b','',head).strip().lower()
        row['template_id']=digest(head) if head else ''
    if 'emo' in e and e['t'].timestamp() in features:row['lam_features']=features[e['t'].timestamp()]
    row['historical_availability']='reconstructed; not observed ingestion order'
    metadata.append(row)
np.savez_compressed(root/'events.npz',rows=json.dumps(metadata),X=X,E=EM,is_text=it,is_emotion=ie)
receipt={'captured_at':datetime.now(TZ).isoformat(),'cutoff_exclusive':cutoff,
         'events':len(events),'sources':dict(Counter(e['source'] for e in events)),
         'last_event_at':max(e['t'] for e in events).isoformat(),'text_cache_hits':initial_cached,
         'lam_feature_rows':len(features),'input_sha256':E.sha(root/'events.npz'),
         'source_files':sources,'no_fresh_outcomes':cutoff=='2026-10-23',
         'limits':'current admitted records; mutable historical versions and link labels unavailable',
         'encoder_path':a.encoder,'lam_projection_sha256':E.sha(a.lam)}
(root/'capture.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({k:v for k,v in receipt.items() if k not in ('source_files','encoder_path')}))

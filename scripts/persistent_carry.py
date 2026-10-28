#!/usr/bin/env python3
"""Always-on selective carrying state. CPU, observed evidence, no providers.

The first working state is a transparent, untrained selective recurrence, not a
learned forecasting checkpoint. Source-gated decays and explicit record memory
select grounded fragments; latent coordinates never become invented prose.
"""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timedelta
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import sys
import tempfile
import time
import numpy as np
from carry_sources import TZ,STREAMS,records,sections,tail,forget_marks,digest,clean,path_in
from carry_context import render

SCHEMA='persistent-carry-v1'
TAUS=np.array([21600.,86400.,259200.,604800.])
WEIGHTS={'thread':1.,'want':1.,'journal':.45,'creative':.4,'dream':.12,
         'conversation':.3,'emotion':.2,'lab':.04,'body':.06,'house':.04,'want_activity':.2}


def feature(text):
    """Fixed lexical features; no semantic-encoder or learned-trait claim."""
    result=np.zeros(32)
    for word in set(re.findall(r'[\w\-]{3,}',clean(text).lower())[:256]):
        raw=hashlib.sha256(word.encode()).digest()
        result[int.from_bytes(raw[:2],'big')%32]+=1 if raw[2]&1 else -1
    return result/max(np.linalg.norm(result),1.)


def atomic(path,data):
    path=Path(path);tmp=path.with_name('.'+path.name+'.'+str(os.getpid()))
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(data,f,sort_keys=True,ensure_ascii=False,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        try:tmp.unlink()
        except FileNotFoundError:pass


class Carrier:
    def __init__(self,memory,output,shadow=False,adopt_shadow=None):
        self.memory=Path(memory).resolve();self.output=Path(output).resolve();self.shadow=shadow
        if self.output==self.memory or self.memory in self.output.parents and self.output!=self.memory/'persistent-carry':
            raise ValueError('dedicated output directory required')
        if shadow and (self.output==self.memory/'persistent-carry' or self.memory in self.output.parents):
            raise ValueError('shadow outputs must be outside source memory')
        if shadow:
            allowed=Path(os.environ.get('CARRY_SHADOW_ROOT',tempfile.gettempdir())).resolve()
            if '.vintos' in allowed.parts or not self.output.is_relative_to(allowed) or self.output==allowed:
                raise ValueError('shadow requires private scratch output')
        self.output.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.lock=(self.output/'writer.lock').open('a')
        try:fcntl.flock(self.lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.lock.close();raise
        p=self.output/'state.json'
        recovered=False;adopted=False
        if not p.exists() and adopt_shadow:
            try:
                if shadow:raise ValueError('adoption is a handoff into the live carrying store')
                candidate=json.loads(Path(adopt_shadow).read_text())
                if candidate.get('schema')!=SCHEMA or candidate.get('source_memory')!=str(self.memory):
                    raise ValueError('shadow checkpoint source/schema mismatch')
                if not isinstance(candidate.get('born'),(int,float)) or candidate['born']>time.time():
                    raise ValueError('invalid shadow duration')
                self.state=candidate;adopted=True
            except Exception:
                self.lock.close();raise
        if p.exists():
            try:self.state=json.loads(p.read_text())
            except (ValueError,OSError):
                p.rename(self.output/('state.corrupt-'+str(time.time_ns())+'.json'));recovered=True
        if (p.exists() or adopted) and not recovered:
            if self.state.get('schema')!=SCHEMA or self.state.get('source_memory')!=str(self.memory):
                self.lock.close();raise ValueError('checkpoint mismatch')
            self.state['restarts']+=1
            if adopted:self.state['adopted_from_shadow_at']=time.time()
        else:
            self.state=dict(schema=SCHEMA,source_memory=str(self.memory),born=None,last_tick=None,
                            items={},channels={},streams={},seen={},selected=[],days=[],ticks=0,restarts=0,
                            processed={},marks=forget_marks(self.memory),last_checkpoint=0,changes=0,removed=0)
            self.state['checkpoint_rebuilt']=recovered
        self.stopped=False
        self.shadow=shadow
        self.runtime_code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                           [Path(__file__),Path(__file__).with_name('carry_sources.py'),Path(__file__).with_name('carry_context.py')]}

    def close(self):
        self.lock.close()

    def tick(self,now=None):
        now=time.time() if now is None else float(now)
        s=self.state
        if s['born'] is None:s['born']=now
        if s['last_tick'] is not None and now<s['last_tick']:raise ValueError('wall clock moved backwards')
        delta=0 if s['last_tick'] is None else now-s['last_tick']
        channels={k:np.asarray(v)*np.exp(-delta/TAUS[:,None]) for k,v in s['channels'].items()}
        events=defaultdict(list);current={};healthy=set();unavailable=[];purge=False;purge_kinds=set()
        names=['unfinished-threads.json','current-wants.json','dream-log.json']
        for offset in range(7):
            day=(datetime.fromtimestamp(now,TZ)-timedelta(days=offset)).date().isoformat()
            for kind in ('inner-life','creative'):
                name='daily-'+kind+'-'+day+'.md'
                if (self.memory/name).exists():names.append(name)
        for name in names:
            try:
                values=sections(self.memory,name) if name.endswith('.md') else records(self.memory,name,now)
                healthy.add(name);current.update(values)
            except (OSError,ValueError,TypeError):unavailable.append(name)
        omitted=max(0,len(current)-512)
        if omitted:
            # Bound carried record memory without dropping an already selected
            # still-admitted fragment merely because the day became busy.
            order=sorted(current,key=lambda k:(k not in s['selected'],current[k]['kind'] not in ('thread','want')))
            current={k:current[k] for k in order[:512]}
        marks=forget_marks(self.memory)
        if set(marks)-set(s['marks']):
            s['items']={};channels={};s['selected']=[];purge=True;purge_kinds=set(WEIGHTS)
        s['marks']=marks
        # A successful current snapshot retires removed/resolved/ineligible rows.
        # An unavailable source cannot falsely resolve them.
        for key,item in list(s['items'].items()):
            expired=item['ref']['file'].endswith('.md') and item['ref']['file'] not in names
            if (item['ref']['file'] in healthy and key not in current) or expired:
                del s['items'][key];s['removed']+=1;purge=True;purge_kinds.add(item['kind'])
        for key,row in current.items():
            old=s['items'].get(key);changed=not old or old['ref']['version']!=row['ref']['version']
            if changed:
                if old:purge=True;purge_kinds.add(old['kind'])
                item={'ref':row['ref'],'first_seen':old['first_seen'] if old else now,
                      'changed_at':now,'kind':row['kind'],'vector':feature(row['text']).tolist()}
                s['items'][key]=item;events[row['kind']].append(np.asarray(item['vector']));s['changes']+=1
        # A removal also removes its meaning from recurrent state/checkpoints.
        # Rebuild only from currently verifiable items, never an erased snapshot.
        if purge:
            for kind in purge_kinds:
                channels.pop(kind,None);events[kind]=[]
            for key,row in current.items():
                if row['kind'] in purge_kinds:events[row['kind']].append(feature(row['text']))
            for old in self.output.glob('hour-*.json'):old.unlink()
            for old in self.output.glob('state.corrupt-*.json'):old.unlink()
        for name,kind in STREAMS.items():
            try:
                rows,cursor,bad,reset=tail(self.memory,name,s['streams'].get(name,{}))
                s['streams'][name]=cursor
                seen=list(s['seen'].get(name,[]));seen_set=set(seen);count=0
                for row in rows:
                    eid=digest(row)[:32]
                    if eid in seen_set:continue
                    seen.append(eid);seen_set.add(eid)
                    # Arrival is the first observation now, not a fabricated
                    # historical availability time from an edited record.
                    if kind=='conversation':
                        if row.get('role') not in ('user','assistant'):continue
                        text=re.sub(r'\[[^\]]*\]?', ' ',str(row.get('content') or ''))
                    else:text=clean(row.get('kind') or row.get('sensor') or row.get('event'))
                    value=row.get('value')
                    if isinstance(value,str):text+=' observed '+value[:80]
                    if kind=='lab':text+=' '+str(row.get('truth_status') or '')
                    vector=feature(text)
                    if isinstance(value,(int,float)):
                        try:
                            number=float(value)
                            if math.isfinite(number):
                                index=int(digest([kind,row.get('kind'),row.get('sensor')])[:8],16)%32
                                vector[index]+=math.tanh(number/(1 if isinstance(value,bool) else 100))
                                vector=vector/max(np.linalg.norm(vector),1.)
                        except (ValueError,OverflowError):pass
                    events[kind].append(vector);count+=1
                s['seen'][name]=seen[-1024:]
                s['processed'][kind]=s['processed'].get(kind,0)+count
                if bad:unavailable.append(name+':malformed-rows')
            except (OSError,ValueError,TypeError):unavailable.append(name)
        # Emotion changes update state, but coordinates are never decoded as
        # personality or a claim about somebody else's experience.
        try:
            data=json.loads(path_in(self.memory,'emotion-trajectory-dense.json').read_text())
            last=data[-1]
            if digest(last)!=s['seen'].get('emotion'):
                v=last['v']
                if not isinstance(v,list) or len(v)!=11 or not np.isfinite(v).all():raise ValueError('malformed emotion')
                events['emotion'].append(np.pad(np.asarray(v,float),(0,21))/max(np.linalg.norm(v),1.))
                s['seen']['emotion']=digest(last);s['processed']['emotion']=s['processed'].get('emotion',0)+1
        except (OSError,ValueError,TypeError,KeyError,IndexError):unavailable.append('emotion-trajectory-dense.json')
        for kind,values in events.items():
            if not values:continue
            observed=np.mean(values,axis=0)
            h=channels.get(kind,np.zeros((4,32)))
            novelty=1-float(np.clip(np.dot(h[0],observed)/max(np.linalg.norm(h[0])*np.linalg.norm(observed),1e-9),-1,1))
            gate=WEIGHTS[kind]*(.25+.25*novelty)
            # Content-selective bounded input gate; volume is averaged within
            # each source, so machine traffic cannot swamp an unfinished want.
            channels[kind]=(1-gate)*h+gate*observed
        if any(not np.isfinite(v).all() for v in channels.values()):raise ValueError('nonfinite recurrent state')
        h=np.mean([np.mean(v,axis=0)*WEIGHTS[k] for k,v in channels.items()],axis=0) if channels else np.zeros(32)
        h=h/max(np.linalg.norm(h),1e-9)
        candidates=[]
        for key,row in current.items():
            item=s['items'][key]
            similarity=.35*float(np.dot(h,item['vector']))
            base={'thread':2.,'want':2.,'journal':.8,'creative':.6,'dream':.15}[item['kind']]
            sticky=.12 if key in s['selected'] else 0
            candidates.append((base+similarity+sticky,key))
        candidates.sort(reverse=True)
        chosen=[];kinds=Counter()
        for _,key in candidates:
            kind=s['items'][key]['kind']
            if kinds[kind]>=1:continue
            if len(chosen)>=3:break
            chosen.append(key);kinds[kind]+=1
        s.update(last_tick=now,channels={k:v.tolist() for k,v in channels.items()},selected=chosen,ticks=s['ticks']+1)
        day=datetime.fromtimestamp(now,TZ).date().isoformat()
        s['days']=sorted(set(s['days']+[day]))[-30:]
        packet={'schema':SCHEMA,'shadow':self.shadow,'last_tick':now,'selected':[s['items'][key] for key in chosen],
                'unavailable_sources':sorted(unavailable),'state_kind':'untrained lexical selective recurrence',
                'checkpoint_rebuilt':s.get('checkpoint_rebuilt',False),'omitted_records':omitted}
        note=render(packet,[(s['items'][key],current[key]) for key in chosen],now)
        packet['note']=note
        atomic(self.output/'note.json',packet)
        atomic(self.output/'state.json',s)
        if purge or now-s['last_checkpoint']>=3600:
            s['last_checkpoint']=now
            atomic(self.output/('hour-'+datetime.fromtimestamp(now,TZ).strftime('%Y%m%d-%H%M')+'.json'),s)
            for old in sorted(self.output.glob('hour-*.json'))[:-48]:old.unlink()
            atomic(self.output/'state.json',s)
        health={'schema':SCHEMA,'shadow':self.shadow,'pid':os.getpid(),'born':s['born'],'last_tick':now,
                'ticks':s['ticks'],'restarts':s['restarts'],'days':s['days'],'selected_count':len(chosen),
                'oldest_carried_hours':max([(now-s['items'][k]['first_seen'])/3600 for k in chosen],default=0),
                'source_counts':dict(Counter(r['kind'] for r in current.values())),
                'processed':s['processed'],'changes':s['changes'],'removed':s['removed'],
                'unavailable_sources':sorted(unavailable),'checkpoint_files':len(list(self.output.glob('hour-*.json')))}
        health['checkpoint_rebuilt']=s.get('checkpoint_rebuilt',False)
        health['runtime_code']=self.runtime_code
        health['omitted_records']=omitted
        health['adopted_from_shadow_at']=s.get('adopted_from_shadow_at')
        # Aggregate daily receipts contain no words or item IDs. They make real
        # cross-day operation auditable without preserving forgotten content.
        daily_path=self.output/'daily-health.json'
        try:daily=json.loads(daily_path.read_text())
        except (OSError,ValueError):daily={}
        entry=daily.setdefault(day,{'first_tick':now,'ticks':0,'max_carried_hours':0})
        entry.update(last_tick=now,ticks=entry['ticks']+1,max_carried_hours=max(entry['max_carried_hours'],health['oldest_carried_hours']))
        atomic(daily_path,{k:daily[k] for k in sorted(daily)[-30:]})
        atomic(self.output/'health.json',health)
        return health


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source-memory',type=Path)
    ap.add_argument('--output',type=Path);ap.add_argument('--shadow',action='store_true')
    ap.add_argument('--daemon',action='store_true');ap.add_argument('--poll',type=float,default=30)
    ap.add_argument('--max-hours',type=float,default=0)
    ap.add_argument('--adopt-shadow',type=Path)
    a=ap.parse_args();memory=a.source_memory or Path(os.environ.get('SPARK_WORKSPACE',Path.home()/'.vintos/workspace'))/'memory'
    if a.shadow and not a.output:raise ValueError('shadow requires explicit private output')
    output=a.output or memory/'persistent-carry'
    carrier=Carrier(memory,output,a.shadow,a.adopt_shadow)
    # Runtime has read-only source access and no network, including in shadow.
    def guard(event,args):
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            mode,flags=args[1:3]
            writes=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if writes and not Path(os.fsdecode(args[0])).resolve().is_relative_to(carrier.output):raise PermissionError('outside carrying output')
        if event in ('socket.connect','socket.sendto'):raise PermissionError('network denied')
    sys.addaudithook(guard)
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *unused:setattr(carrier,'stopped',True))
    end=time.monotonic()+a.max_hours*3600 if a.max_hours else float('inf')
    try:
        while not carrier.stopped and time.monotonic()<end:
            try:carrier.tick()
            except Exception as exc:
                atomic(carrier.output/'fault.json',{'at':time.time(),'type':type(exc).__name__})
                if not a.daemon:raise
            if not a.daemon:break
            # Short sleeps permit prompt shutdown without exposing a live writer.
            until=time.monotonic()+max(1,a.poll)
            while not carrier.stopped and time.monotonic()<until:time.sleep(min(1,max(0,until-time.monotonic())))
    finally:carrier.close()


if __name__=='__main__':main()

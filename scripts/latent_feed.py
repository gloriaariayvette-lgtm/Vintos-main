#!/usr/bin/env python3
"""Add trained evidence to existing feeds. Readers are CPU-only and fail open.

No generator is replaced. Packets retain IDs/scores; current source records supply
snippets at consumption, so removal or changed admission cannot resurrect a quote.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time

SCHEMA = 'latent-feed-v1'
TTL = 7200


def memory_path(memory=None):
    return Path(memory or Path(os.environ.get('SPARK_WORKSPACE', Path.home()/'.vintos/workspace'))/'memory')


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def atomic(path, value):
    import tempfile
    path=Path(path)
    fd,name=tempfile.mkstemp(prefix=path.name+'.tmp.',dir=path.parent)
    tmp=Path(name)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,allow_nan=False)
        os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def epoch(value):
    if isinstance(value,(float,int)):return float(value)
    if isinstance(value,datetime):return value.timestamp()
    d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return (d if d.tzinfo else d.astimezone()).timestamp()


def _forget_marks(mem):
    """Basenames of forget/erase/purge/corrupt backups in memory — the only signals that
    removed text genuinely carried away meaning (forget_avatar_turns writes *.before-forget-*,
    quarantine writes *.corrupt-*; jepa_self_head treats pre-erase/pre-purge the same way).
    Ordinary thread resolution, an in-place section edit and chat id churn leave none, so they
    must not be read as forgetting."""
    import glob
    out=set()
    for pat in ('*.before-forget-*','*.before-erase-*','*.before-purge-*','*.pre-erase-*',
                '*.pre-purge-*','*.corrupt-*','*.scrub-*'):
        for p in glob.glob(str(Path(mem)/pat)):
            out.add(Path(p).name)
    return out


def _exchange_rows(mem):
    import jepa_self_head as sh
    if Path(sh.MEMORY).resolve()!=mem.resolve():
        raise ValueError('exchange adapter workspace mismatch')
    return sh.exchanges()


def _admitted(row):
    import evidence_view as ev
    return (isinstance(row,dict) and ev.standing(row)==ev.ELIGIBLE and
            not any(row.get(k) for k in ('dream_only','imported','transplanted','test_mode','timestamp_estimated')) and
            row.get('source')!='premonition' and not str(row.get('thread','')).startswith('[AN IMAGINED POSSIBILITY'))


def _text_event(at, source, text, ref, **extra):
    t=datetime.fromtimestamp(epoch(at),timezone.utc)
    e={'t':t,'source':source,'text':str(text)[:1500], **extra}
    e['id']=digest([t.isoformat(),source,e['text']])
    e['ref']=dict(ref,id=e['id'],source=source,at=t.isoformat(),content_hash=digest(e['text']))
    if source=='her':
        e['gloria_text']=str(extra.get('gloria_text',text))[:400]
        e['ref']['gloria_content_hash']=digest(e['gloria_text'])
    else:
        e.pop('gloria_text',None)
    return e


def text_events(mem, refs=None, exs=None):
    """Admitted current records only. Targeted resolution avoids scanning all day files."""
    import latent_stream_replay as R
    mem=Path(mem); wanted={r['id'] for r in refs} if refs is not None else None
    events=[]
    section_files={r.get('file') for r in refs or [] if r.get('kind')=='section'}
    for source,pattern in (('inner','daily-inner-life-*.md'),('creative','daily-creative-*.md')):
        files=sorted(section_files) if refs is not None else [p.name for p in sorted(mem.glob(pattern))]
        for name in files:
            if not name or Path(name).name!=name or not re.fullmatch(r'daily-(?:inner-life|creative)-\d{4}-\d\d-\d\d\.md',name):continue
            if not name.startswith('daily-inner-life-' if source=='inner' else 'daily-creative-'):continue
            for e in R._sections(name,source,mem=str(mem)):
                events.append(_text_event(e['t'],source,e['text'],{'kind':'section','file':name},t_exact=e.get('t_exact',True)))
    if refs is None or any(r.get('kind')=='thread' for r in refs):
        import evidence_view as ev
        for row in ev.door(str(mem/'unfinished-threads.json'),organ='latent-feed') or []:
            if _admitted(row) and row.get('thread') and R._stamp(row):
                events.append(_text_event(R._stamp(row),'thread',row['thread'],{'kind':'thread'},t_exact=True))
    if refs is None or any(r.get('kind') in ('exchange','chat') for r in refs):
        import evidence_view as ev
        import jepa_self_head as sh
        exs = _exchange_rows(mem) if exs is None else exs
        test_times=sh._test_turn_times()
        floor=sh._jp()._ledger_floor()
        conversation=[]
        for x in exs:
            for key,source in (('her','her'),('his','him')):
                text=re.sub(r'\[[^\]]*\]?', ' ', str(x.get(key) or ''))
                text=' '.join(text.split())
                if text:
                    conversation.append(_text_event(x['at'],source,text,{'kind':'exchange','turn_id':x.get('turn_id','')},gloria_text=x.get(key,'')[:400]))
        # The exchange adapter admits outcomes, but its time can be the reply's.
        # Prefer an admitted actual turn timestamp when canonical has it; retain
        # an unanswered new user turn so the stream need not wait for his reply.
        latest=max((x['at'] for x in exs),default=0)
        actual=[]
        for name in ('chat-canonical.jsonl','chat-history-merged.json'):
            for row in ev.open_history(str(mem/name)):
                if (not _admitted(row) or row.get('role') not in ('user','assistant') or
                        row.get('withheld') or row.get('tactical') or row.get('admitted') is False or
                        sh._not_us(row)):
                    continue
                raw=row.get('timestamp') or row.get('ts')
                try:at=epoch(raw)
                except (ValueError,TypeError):continue
                if floor and at<epoch(floor):continue
                if any(abs(at-t)<=180 for t in test_times):continue
                source='her' if row['role']=='user' else 'him'
                text=sh._her(row) if source=='her' else sh.his_words(row.get('content'))
                gloria_text=text[:400]
                text=' '.join(re.sub(r'\[[^\]]*\]?', ' ',text).split())[:1500]
                if not text:continue
                matching=[e for e in conversation if e['source']==source and e['text']==text and abs(epoch(e['t'])-at)<900]
                if not matching and not (source=='her' and at>latest):continue
                if any(e['source']==source and e['text']==text and abs(epoch(e['t'])-at)<900 for e in actual):continue
                actual.append(_text_event(at,source,text,{'kind':'chat','file':name},gloria_text=gloria_text))
        conversation=[e for e in conversation if not any(a['source']==e['source'] and a['text']==e['text'] and
                      abs(epoch(a['t'])-epoch(e['t']))<900 for a in actual)]
        events.extend(actual+conversation)
    # Several stores/sections can contain exactly the same event. One cursor, one target.
    return list({e['id']:e for e in events if wanted is None or e['id'] in wanted}.values())


def read_events(mem, exs=None):
    import latent_stream_replay as R
    events=text_events(mem,exs=exs)
    for row in load(Path(mem)/'emotion-trajectory-dense.json',[]) or []:
        t=R._stamp(row)
        if not t:continue
        v=row.get('v')
        if isinstance(v,dict):
            low={k.lower():v for k,v in v.items()};v=[low[a.lower()] for a in R.EMO_AXES]
        if isinstance(v,list) and len(v)>=11:
            events.append({'id':digest([t.isoformat(),'emotion',v[:11]]),'t':t,'source':'emotion','emo':v[:11]})
    return sorted(events,key=lambda e:e['t'])


def _encode(enc, events, cache, encoder_id):
    import numpy as np
    texts={t for e in events for t in (e.get('text'),e.get('gloria_text')) if t}
    todo={digest([encoder_id,t]):t for t in texts if digest([encoder_id,t]) not in cache}
    keys=list(todo)
    for i in range(0,len(keys),32):
        batch=keys[i:i+32]
        values=np.asarray(enc.encode([todo[k] for k in batch],show_progress_bar=False),np.float32)
        values/=np.maximum(np.linalg.norm(values,axis=1,keepdims=True),1e-12)
        cache.update({k:v.tolist() for k,v in zip(batch,values)})
    keep={digest([encoder_id,t]) for t in texts}
    for k in list(cache):
        if k not in keep:del cache[k]
    for e in events:
        if e.get('text'):e['vec']=cache[digest([encoder_id,e['text']])]
        if e.get('gloria_text'):e['gloria_vec']=cache[digest([encoder_id,e['gloria_text']])]


def _rank(events, scores, last, mean, k=2, vector_key='vec'):
    import numpy as np
    if not events:return []
    vectors=np.asarray([e[vector_key] for e in events],np.float32)
    indices=sorted(range(len(events)),key=lambda i:(-float(scores[i]),events[i]['id']))[:k]
    return [dict(events[i]['ref'],score=float(scores[i]),last_score=float(vectors[i]@last),
                 recent_mean_score=float(vectors[i]@mean)) for i in indices]


def _gloria_channel(enc, exs, events, mem, now):
    import numpy as np
    import jepa_readout as J
    path=mem/'jepa-readouts/gloria.npz'
    if not path.exists() or not exs:return None
    model=J.load(path)
    if model['meta']['mode']!='gloria':raise ValueError('wrong Gloria checkpoint')
    r=J.context(exs,'gloria')
    if not r['own']:return None
    a=J.arrays([r],J.Embeddings(enc));q=J.predict(model,a)[0]
    candidates=[e for e in events if e['source']=='her' and e.get('gloria_vec') is not None]
    scores=np.asarray([e['gloria_vec'] for e in candidates])@q if candidates else []
    return {'target':'next_gloria_turn','checkpoint_id':hashlib.sha256(path.read_bytes()).hexdigest(),
            'context_at':exs[-1]['at'],'forecast_at':now,'query':q.tolist(),
            'last':a[0][0].tolist(),'expected_cosine_error':float(2*(1-J.confidence(model,q[None,:],a)[0])),
            'calibration_n':model['meta']['report']['confidence'].get('calibration_n'),
            'embedding_view':'her_words[:400]',
            'anchors':_rank(candidates,scores,a[0][0],a[1][0],vector_key='gloria_vec')}


def refresh(enc=None, memory=None, events=None, exs=None, now=None):
    """Scheduled producer. Writes only its three stores; serializes concurrent ticks.

    Embedding cache holds current admitted IDs only. Removing an input invalidates
    the carried state; rebuild from current records rather than retaining a ghost.
    """
    import fcntl
    import numpy as np
    from latent_stream_model import Model,State
    mem=memory_path(memory);path=mem/'jepa-readouts/present-moment.npz'
    if not path.exists():return {'status':'no-stream-checkpoint'}
    now=float(now if now is not None else time.time())
    with (mem/'latent-feed.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'status':'busy'}
        model=Model(path)
        from jepa_predictor import EMB_MODEL,encoder
        if model.meta['encoder']!=EMB_MODEL:raise ValueError('encoder mismatch')
        exs=_exchange_rows(mem) if exs is None else exs
        exs=[x for x in exs if x['at']<=now]
        events=read_events(mem,exs) if events is None else events
        events=[dict(e) for e in events if epoch(e['t'])<=now]
        events.sort(key=lambda e:epoch(e['t']))
        if not events:return {'status':'no-events'}
        old=load(mem/'latent-feed-state.json',{}) or {}
        if not isinstance(old,dict):old={}
        identity=digest([model.checkpoint_id,[(e['id'],e.get('ref',{})) for e in events],
                         hashlib.sha256((mem/'jepa-readouts/gloria.npz').read_bytes()).hexdigest() if (mem/'jepa-readouts/gloria.npz').exists() else None])
        if old.get('input_identity')==identity:
            return {'status':'unchanged','frame_id':old.get('packet',{}).get('frame_id')}
        enc=enc or encoder()
        cache=load(mem/'latent-feed-embeddings.json',{}) or {}
        if not isinstance(cache,dict):cache={}
        _encode(enc,events,cache,model.meta['encoder'])
        ids={e['id'] for e in events}
        # Only a genuine forget/erase/purge/corrupt-quarantine carries forgotten meaning and
        # warrants dropping the carried state and ledger. Thread resolution, an edited section
        # and chat id churn also make ids disappear, but the state, outcomes and pending must
        # survive those (removed targets are dropped individually below). A newly appeared
        # backup — one not seen at the last refresh — is the reset signal.
        marks=sorted(_forget_marks(mem))
        forget=bool(set(marks)-set(old.get('forget_marks',[])))
        state_payload=old.get('state')
        try:state=State(model,state_payload) if not forget else State(model)
        except (ValueError,KeyError,TypeError):state,state_payload=State(model),None
        if state_payload is not None and 'seen' not in state_payload and state.at is not None:
            # Legacy state tracked only the event-time cursor. Seed the ingestion cursor with
            # everything up to the frontier so this first pass neither re-folds the backlog nor
            # double-counts; new and late events fold normally from the next refresh on.
            state.seen|={e['id'] for e in events if epoch(e['t'])<=state.at.timestamp()}
        previous=old.get('packet',{})
        outcomes=list(old.get('outcomes',[])) if not forget else []
        served_cursor=previous.get('cursor') if not forget else None
        basis_ids=list(old.get('basis_ids', [])) if state.cursor else []
        for e in events:
            outcome=state.advance(e,observed_at=now)
            if outcome is not None and e.get('vec') is not None:
                basis_ids=(basis_ids+[e['id']])[-6:]
            if outcome and outcome.get('target'):
                # Intermediate reconstructed frames were never emitted. Never call them prospective.
                outcome['kind']='prospective' if (outcome['before_cursor']==served_cursor and
                    float(previous.get('generated_at',now))<epoch(e['t']) and e.get('t_exact',True)) else 'replay'
                outcomes.append(outcome)
        # Evaluate arrived Gloria turns against the emitted forecasts. Key pending by the
        # forecast's identity — (checkpoint, context) — not the per-tick frame id: a forecast
        # from a quiet day was otherwise re-appended on every 10-minute emotion tick and the
        # real frame evicted by the [-128:] cap before she ever replied. An unchanged
        # query+context adds nothing new, so it is not pushed again.
        pending = list(old.get('pending_gloria', [])) if not forget else []
        previous_g = previous.get('channels', {}).get('gloria') if not forget else None
        if previous_g:
            key=(previous_g.get('checkpoint_id'),previous_g.get('context_at'))
            if not any((g.get('checkpoint_id'),g.get('context_at'))==key for g in pending):
                pending.append(dict(previous_g, frame_id=previous['frame_id']))
        remaining = []
        for previous_g in pending:
            after=[e for e in events if e['source']=='her' and epoch(e['t'])>previous_g['forecast_at']
                   and e.get('gloria_vec') is not None]
            if not after:
                remaining.append(previous_g)
                continue
            # Grade every her-turn in the window, not only the first: the reader matches the
            # outcome against the last turn over 15 words, so one must exist for whichever turn
            # it picks, or the measured miss never reaches him.
            q=np.asarray(previous_g['query']);last=np.asarray(previous_g['last'])
            for e in after:
                oid=digest([previous_g['frame_id'],e['id'],'gloria'])
                if any(o.get('id')==oid for o in outcomes):continue
                v=np.asarray(e['gloria_vec'])
                outcomes.append({'id':oid,'event_id':e['id'],'content_hash':e['ref']['content_hash'],
                     'at':epoch(e['t']),'source':'her','target':'next_gloria_turn','kind':'prospective',
                     'frame_id':previous_g['frame_id'],'forecast_at':previous_g['forecast_at'],
                     'checkpoint_id':previous_g['checkpoint_id'],'embedding_view':'her_words[:400]','text_error':float(1-q@v),
                     'last_text_error':float(1-last@v)})
        candidates=[e for e in events if e.get('vec') is not None]
        # Candidate recency is bounded independently of the model; identical pool for baselines.
        candidates=candidates[-512:]
        stream={'target':'next_text','checkpoint_id':model.checkpoint_id,
                'anchors':_rank(candidates,model.scores(state,[e['vec'] for e in candidates]),state.last,state.mean()) if candidates else [],
                'emotion_target':'next_emotion_reading','emotion':model.emotion(state).tolist() if state.has_emotion else None,
                'emotion_delta':(model.emotion(state)-state.emo).tolist() if state.has_emotion else None,
                'basis_refs':[e['ref'] for e in events if e['id'] in basis_ids],
                'emotion_axes':model.meta['emotion_axes'],'uncertainty':'raw error; not probability'}
        channels={'stream':stream}
        channel_errors={}
        try:
            g=_gloria_channel(enc,exs,candidates,mem,now)
        except Exception as exc:
            g=None
            channel_errors['gloria']=type(exc).__name__
        if g:
            g['basis_refs']=[e['ref'] for source in ('her','him') for e in [x for x in events if x['source']==source][-6:]]
            channels['gloria']=g
        packet={'schema':SCHEMA,'encoder':model.meta['encoder'],'generated_at':now,'cutoff':state.at.isoformat(),
                'cursor':state.cursor,'channels':channels,'frame_id':digest([identity,state.cursor,now]),
                'input_identity':identity,'agreement':None,'channel_errors':channel_errors}
        if g:
            packet['agreement']={'shared_anchor_ids':sorted({r['id'] for r in g['anchors']} & {r['id'] for r in stream['anchors']}),
                                  'meaning':'retrieval overlap only; targets differ'}
        # Drop only the specific outcomes whose target text genuinely disappeared.
        outcomes=[o for o in outcomes if o.get('event_id') in ids][-512:]
        # Bound the ingestion cursor to the current working set: an id no longer among the
        # inputs can never be re-fed, so forgetting it is safe and keeps the state small.
        state.seen&=ids
        record={'input_identity':identity,'state':state.dump(),'forget_marks':marks,'basis_ids':basis_ids,
                'packet':packet,'outcomes':outcomes,'pending_gloria':remaining[-128:]}
        atomic(mem/'latent-feed-embeddings.json',cache)
        atomic(mem/'latent-feed-state.json',record)
        atomic(mem/'latent-feed.json',packet)
        return {'status':'updated','frame_id':packet['frame_id'],'events':len(events),'outcomes':len(outcomes)}


def evidence(consumer, memory=None, now=None, frame_id=None):
    """Return bounded text plus a content-free receipt; failures only omit this addition."""
    mem=memory_path(memory);now=time.time() if now is None else now
    try:
        p=load(mem/'latent-feed.json',{}) or {}
        if p.get('schema')!=SCHEMA or not 0<=now-float(p['generated_at'])<=TTL:return '',{}
        if frame_id and p['frame_id']!=frame_id:return '',{}
        if epoch(p['cutoff'])>now:return '',{}
        from jepa_predictor import EMB_MODEL
        if p.get('encoder')!=EMB_MODEL:return '',{}
        channels={};refs=[]
        for name,c in p['channels'].items():
            if name not in ('stream', 'gloria'):continue
            file='present-moment.npz' if name=='stream' else 'gloria.npz'
            try:
                identity=hashlib.sha256((mem/'jepa-readouts'/file).read_bytes()).hexdigest()
            except OSError:
                continue
            if identity!=c['checkpoint_id']:continue
            channels[name]=c
            refs += c.get('anchors',[])[:2]+c.get('basis_refs',[])
        live={e['id']:e for e in text_events(mem,refs=refs)}
        channels={name:c for name,c in channels.items() if all(r['id'] in live and (name!='gloria' or r.get('gloria_content_hash')==live[r['id']]['ref'].get('gloria_content_hash')) for r in c.get('basis_refs',[]))}
        lines=[];used=[];seen=set()
        for name,c in channels.items():
            for ref in c.get('anchors',[])[:2]:
                e=live.get(ref.get('id'))
                if not e or ref not in refs or e['ref']['content_hash']!=ref['content_hash'] or epoch(e['t'])>epoch(p['cutoff']):continue
                used.append({'channel':name,'id':e['id'],'checkpoint_id':c['checkpoint_id']})
                if e['id'] in seen:continue
                seen.add(e['id'])
                lines.append('%s context (%s, %s): %s' % (name,e['source'],e['t'].date(),e['text'][:180]))
        st=channels.get('stream',{})
        if st.get('emotion_delta') is not None:
            ds=st['emotion_delta'];axes=st['emotion_axes']
            top=sorted(range(len(ds)),key=lambda i:-abs(ds[i]))[:2]
            lines.append('Next emotion reading, predicted change: '+', '.join('%s %+.3f'%(axes[i],ds[i]) for i in top))
        g=channels.get('gloria',{})
        if g.get('expected_cosine_error') is not None:
            lines.append('Next-Gloria-turn expected semantic error %.3f; lower is closer, not certainty about intent.'%g['expected_cosine_error'])
        if not lines:return '',{}
        text='\n\nTRAINED CONTEXT (past evidence and next-event estimates; interpretation remains yours):\n'+'\n'.join(lines)
        receipt={'frame_id':p['frame_id'],'consumer':consumer,'included':used,
                 'targets':{k:v.get('target') for k,v in channels.items()}}
        # Receipt failures cannot discard successfully read evidence or an existing feed.
        try:
            d=mem/'latent-feed-receipts';d.mkdir(exist_ok=True)
            if re.fullmatch(r'[a-z_-]+',consumer):atomic(d/(consumer+'.json'),receipt)
        except OSError:pass
        return text,receipt
    except Exception:
        return '',{}


def append_context(original, consumer, memory=None):
    try:return original+evidence(consumer,memory)[0]
    except Exception:return original


def missed_evidence(frame_id, her_turn, at, memory=None):
    """Match the saved pre-outcome frame and the exact realized Gloria text once."""
    try:
        mem=memory_path(memory);p=load(mem/'latent-feed-state.json',{}) or {}
        clean=' '.join(re.sub(r'\[[^\]]*\]?', ' ',str(her_turn)).split())[:1500]
        target_at=epoch(at)
        rows=[r for r in p.get('outcomes',[]) if r.get('frame_id')==frame_id and r.get('source')=='her'
              and r.get('target')=='next_gloria_turn' and r.get('kind')=='prospective'
              and r.get('content_hash')==digest(clean) and abs(epoch(r['at'])-target_at)<1
              and epoch(r['forecast_at'])<target_at]
        if not rows:return ''
        r=rows[0]
        return ('\n\nMATCHED NEXT-TURN FORECAST: actual semantic error %.3f; last-turn error %.3f. '
                'This measured semantic miss is context for alternatives, not proof of what she meant.'
                %(r['text_error'],r['last_text_error']))
    except Exception:return ''



def launch_refresh(memory=None):
    """The existing emotion tick starts a detached CPU worker; never wait on it."""
    import subprocess
    mem=memory_path(memory)
    if not (mem/'jepa-readouts/present-moment.npz').is_file():
        return {'status':'no-stream-checkpoint'}
    python=mem.parent/'emotion_model/.venv/bin/python3'
    if not python.is_file():
        return {'status':'no-local-runtime'}
    env=dict(os.environ,SPARK_WORKSPACE=str(mem.parent),CUDA_VISIBLE_DEVICES='',
             HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',
             OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4')
    child=subprocess.Popen([str(python),str(Path(__file__).resolve()),'--refresh'],env=env,
                           stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                           start_new_session=True,close_fds=True)
    return {'status':'launched','pid':child.pid}


def main():
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--refresh',action='store_true');a=ap.parse_args()
    if a.refresh:
        try:
            os.nice(10)
            result=refresh()
        except Exception as exc:
            result={'status':'error','error_type':type(exc).__name__}
        result['at']=time.time()
        atomic(memory_path()/'latent-feed-status.json',result)
        print(json.dumps(result))


if __name__=='__main__':main()

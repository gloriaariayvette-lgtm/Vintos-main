"""Bounded, read-only context for house decisions; no LLM calls or actions.

Conversation stays on Aegis and goes only to the existing house brain. Readiness
probes are isolated, bounded and cached; configured is distinct from reachable.
"""
import concurrent.futures
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime

WS = Path(os.environ.get('SPARK_WORKSPACE') or Path.home()/'.vintos/workspace')
MEM = WS/'memory'
HORIZON = 24*3600
MAX_JSON = 1024*1024


def read_json(path, default):
    try:
        with open(path, 'rb') as f:
            raw = f.read(MAX_JSON+1)
        return json.loads(raw) if len(raw) <= MAX_JSON else default
    except (OSError, ValueError):
        return default


def tail_rows(path):
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2); size=f.tell(); f.seek(max(0, size-65536))
            lines=f.read(65536).splitlines()
        out=[]
        for line in lines[-100:]:
            try:
                row=json.loads(line)
                if isinstance(row, dict): out.append(row)
            except ValueError: pass
        return out
    except OSError:
        return []


def stamp(value):
    try:
        if type(value) in (int, float):
            return float(value) if math.isfinite(value) else 0
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, OverflowError):
        return 0


def short(value, limit=240):
    return ' '.join(str(value or '').split())[:limit]


def recent_conversation(now):
    rows=[]
    for name in ('chat-history.json', 'avatar-overlay-chat.json', 'voice-chat-history.json', 'avatar-chat-history.json'):
        data=read_json(MEM/name, [])
        for row in data[-40:] if isinstance(data, list) else []:
            if not isinstance(row, dict) or row.get('role') not in ('user', 'assistant'): continue
            # Desktop receipts belong with action outcomes, not Gloria's conversation.
            if row.get('source') == 'desktop-control': continue
            ts=stamp(row.get('timestamp', row.get('ts', row.get('at'))))
            content=row.get('content')
            if not isinstance(content, str) or not content.strip() or not 0 <= now-ts <= HORIZON: continue
            rows.append({'ts':ts, 'speaker':'Gloria' if row['role']=='user' else 'Vintos',
                         'text':short(content, 420), 'surface':name.removesuffix('.json')})
    rows.sort(key=lambda r:r['ts'])
    seen=set(); unique=[]
    for row in rows:
        key=(row['speaker'], row['text'], int(row['ts']))
        if key not in seen: unique.append(row); seen.add(key)
    # Keep the two newest user messages even if many assistant updates followed.
    users=[r for r in unique if r['speaker']=='Gloria'][-2:]
    chosen=unique[-6:]
    for row in users:
        if row not in chosen: chosen.insert(0,row)
    return sorted(chosen, key=lambda r:r['ts'])[-8:]


def previous_outcomes(now):
    rows=[]
    for row in tail_rows(MEM/'house-boards.jsonl'):
        ts=stamp(row.get('at'))
        if not 0 <= now-ts <= HORIZON: continue
        if row.get('kind') == 'moment' and row.get('decided') and row.get('nothing'):
            rows.append({'ts':ts, 'act':'NOTHING', 'result':'chose no action'})
        acts = row.get('acts') or []
        for act in acts if isinstance(acts, list) else []:
            if isinstance(act, dict): rows.append({'ts':ts, 'act':short(act.get('act'),24),
                'ok':act.get('ok') is True, 'result':short(act.get('said'),180)})
        if row.get('kind')=='playback':
            rows.append({'ts':ts, 'act':'AUDIO', 'result':short(row.get('status'),80),
                         'title':short(row.get('title'),100)})
        if row.get('kind')=='desktop':
            rows.append({'ts':ts, 'act':'DESKTOP', 'accepted':row.get('accepted') is True,
                         'result':short(row.get('status') or 'launch acceptance only',100)})
    for row in tail_rows(MEM/'house-actions.jsonl'):
        ts=stamp(row.get('at'))
        if 0 <= now-ts <= HORIZON:
            rows.append({'ts':ts, 'act':short(str(row.get('what','')).split(':')[0],24),
                         'ok':row.get('ok') is True, 'result':short(row.get('said'),180)})
    # Completion receipts from the existing desktop controller, without rereading screen data.
    db=read_json(MEM/'desktop-control/requests.json', {})
    for row in db.values() if isinstance(db, dict) else []:
        if not isinstance(row,dict): continue
        ts=stamp(row.get('followup_at') or row.get('completed_at') or row.get('updated_at') or row.get('created_at'))
        if 0 <= now-ts <= HORIZON:
            rows.append({'ts':ts,'act':'DESKTOP','result':short(row.get('state'),60),
                         'task':short(row.get('task'),160),'truth_status':short(row.get('truth_status'),100),
                         'observed_result':short(row.get('desktop_reason'),180)})
    # Dedupe shared house/board receipts without implying that command success is physical acceptance.
    rows.sort(key=lambda r:r['ts']); out=[]; seen=set()
    for row in reversed(rows):
        key=(int(row['ts']),row.get('act'),row.get('result'))
        if key not in seen: out.append(row);seen.add(key)
        if len(out)>=8:break
    return list(reversed(out))


def song_catalog(conversation, limit=12):
    import bedroom_arrival
    rows=[]; seen=set()
    for title,url in bedroom_arrival.library():
        if url in seen:continue
        seen.add(url)
        rows.append({'id':'song-'+hashlib.sha256(url.encode()).hexdigest()[:12], 'title':str(title), 'url':url})
    text=' '.join(r['text'] for r in conversation).casefold()
    mentioned=[r for r in rows if len(r['title'])>=5 and r['title'].casefold() in text]
    chosen=mentioned[:4]+[r for r in rows if r not in mentioned[:4]]
    return chosen[:limit]


def select_songs(arg, catalog, maximum):
    """Only offered IDs or one exact unambiguous title. Numeric legacy count is separate."""
    raw=str(arg).strip(); folded=raw.casefold()
    titles=[r for r in catalog if r['title'].casefold()==folded]
    if len(titles)==1:return titles
    if len(titles)>1:raise ValueError('that title is ambiguous; use a listed song ID')
    ids=[x.strip().lower() for x in raw.split(',')]
    by_id={r['id']:r for r in catalog}
    if not ids or any(x not in by_id for x in ids):raise ValueError('choose a song ID from the offered list or its exact title')
    ids=list(dict.fromkeys(ids))
    if len(ids)>maximum:raise ValueError('at most %d songs per moment'%maximum)
    return [by_id[x] for x in ids]


def desktop_target():
    return read_json(MEM/'desktop-target.json', {}).get('target', 'windows')


def compute_headroom():
    """Aegis metadata only: no workload launch, model query, or model eviction."""
    out = {'host': 'Aegis', 'gpu_capacity': 'unknown'}
    try:
        out['load_1m'] = os.getloadavg()[0]
        out['logical_cpus'] = os.cpu_count()
        values = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        out['available_memory_mib'] = int(values['MemAvailable'].split()[0]) // 1024
        out['total_memory_mib'] = int(values['MemTotal'].split()[0]) // 1024
    except (OSError, ValueError, KeyError): out['status'] = 'unavailable'
    return out


def capability_options(board):
    """Concrete uses of the existing hands, independent of research-want keywords."""
    if board == 'house-press-mic':
        return [{'action': 'TV', 'outcome': 'Choose a specific video or search query to share on the living-room TV.',
                 'constraint': 'Never interrupt something she is watching; the existing adapter checks ownership again.'}]
    if board == 'house-touch':
        return [
            {'action': 'DESKTOP', 'outcome': 'Show a relevant video, document or existing render in a separate window on the configured iMac desktop. Name the task and visible done condition.',
             'approval': 'Her explicit Yes is required. Aegis may supply files/compute; do not disturb Studio.'},
            {'action': 'PAPER', 'outcome': 'Offer a page of your words or an existing work/image on the Epson.',
             'approval': 'Her Yes for this job, paper and ink; no print has started.'}]
    return []


def desktop_approvals(st):
    import gloria_asks
    rows = []
    for d in st.get('desktop', []):
        if d.get('started'): continue
        q = gloria_asks.get(d.get('ask')) or {}
        if q.get('state') not in ('asked', 'answered'): continue
        if q.get('state') == 'answered' and str(q.get('answer', '')).lower() != 'yes': continue
        rows.append({'task': short(d.get('task'), 300), 'target': d.get('target', desktop_target()),
                     'approval': 'waiting for her answer' if q.get('state') == 'asked' else 'yes received; launch pending',
                     'execution': d.get('status', 'not started')})
    return rows[-5:]


def _probe(board, only=None):
    """Executed in a killable child. All operations are read-only metadata queries."""
    import requests
    from concurrent.futures import ThreadPoolExecutor
    spec=importlib.util.spec_from_file_location('house_home', str(Path(__file__).with_name('vintos-home.py')))
    home=importlib.util.module_from_spec(spec);spec.loader.exec_module(home)
    cfg=home.load_config()
    room={'house-steam':'bathroom','house-touch':'office','house-press-mic':'living_room',
          'house-kitchen':'kitchen'}[board]
    lights=(cfg.get('rooms',{}).get(room) or {}).get('lights') or []
    def lighting():
        # Reading the Govee state never powers a lamp or changes its color.
        entities=[e for e in lights if e.startswith('govee:')]
        if entities: home.govee_devices()
        with ThreadPoolExecutor(max_workers=3) as pool:
            states=list(pool.map(lambda e:home.govee_state(e.split(':',1)[1]), entities))
        return {'room':room,'configured':len(lights),'cloud_checked':len(states),
                'online':sum(s.get('online') is True for s in states),
                'reported':sum('online' in s for s in states)}
    def ha():
        if not cfg.get('url') or not cfg.get('token'):return {'status':'not_configured'}
        r=requests.get(cfg['url'].rstrip('/')+'/api/states',headers={'Authorization':'Bearer '+cfg['token']},timeout=4)
        r.raise_for_status()
        data=r.json(); states={x['entity_id']:x for x in data if isinstance(x,dict) and 'entity_id' in x}
        if board=='house-steam':
            names={'steam':'binary_sensor.house_steam_board_steam',
                   'phone_near':'binary_sensor.house_steam_board_gloria_within_1_m',
                   'speaker':'sensor.house_steam_board_speaker_playback',
                   'output':'sensor.house_steam_board_audio_output_mode'}
            return {k:{'state':short(states.get(v,{}).get('state'),40),
                       'updated_at':states.get(v,{}).get('last_updated')} for k,v in names.items()}
        ent=(cfg.get('entities') or {}).get('echo_media') or cfg.get('media_player')
        return {'echo':{'state':short(states.get(ent,{}).get('state'),40),
                        'configured':bool((cfg.get('entities') or {}).get('echo_speak'))}}
    def desktop():
        target=desktop_target()
        import desktop_agent
        st=desktop_agent.read_state()
        out={'target':target,'status':short(st.get('status'),40),
             'last_result':short(st.get('reason'),160),'requires_user_approval':True,
             'files_and_compute':'Aegis; accessible through the approved remote routes',
             'aegis_headroom':compute_headroom()}
        if target=='imac':
            # Permission metadata only; no screenshot, launch or input action.
            cmd=[sys.executable,'-c','import json,desktop_mac; print(json.dumps(desktop_mac.rpc("permissions")["permissions"]))']
            r=subprocess.run(cmd,capture_output=True,text=True,timeout=5,cwd=Path(__file__).parent)
            if r.returncode==0:out['permissions']=json.loads(r.stdout)
            else:out['bridge']='unreachable'
        return out
    def tv():
        # Refresh only the TV's existing ADB transport, as its production status path does.
        # Connecting reads metadata; it sends no key event, app launch or power command.
        subprocess.run(['adb','connect',home.TV_ADB],capture_output=True,timeout=2)
        rc,power=home._adb('dumpsys','power',timeout=2)
        if rc:return {'power':'unknown','reachable':False}
        import house_hands
        state=home.tv_status()
        # The actual adapter retains the final in-use check when an action is attempted.
        in_use=state.get('power') == 'on' and state.get('source') not in (None, 'unknown')
        reason='She is watching something you did not put on' if in_use and not house_hands._he_is_driving() else ''
        return {'power':state.get('power', 'unknown'), 'reachable':True,
                'app':short(state.get('app'),100), 'takeover_blocked':bool(reason),
                'limitation':short(reason,180)}
    def printer(module, fields):
        # Each printer is independent: a sleeping Epson cannot hide a responding K2.
        code = ('import json,%s; s=%s.status(); print(json.dumps({x:s.get(x) for x in %r}))'
                % (module,module,fields))
        r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                           cwd=Path(__file__).parent, timeout=7)
        if r.returncode: return {'status':'unavailable'}
        return json.loads(r.stdout)
    probes={'lights':lighting}
    if board in ('house-steam', 'house-touch'): probes['ha']=ha
    if board == 'house-touch':
        probes.update(paper=lambda:printer('paper_print',('reachable','accepting','state','reasons')),
                      desktop=desktop)
    if board=='house-press-mic': probes['tv']=tv
    if only is not None: return probes[only]()
    def bounded(key):
        # A single hanging printer or ADB query must not erase every other device's readiness.
        r=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--probe-one',board,key],
                         capture_output=True,text=True,timeout=8)
        if r.returncode: return {'status':'unavailable'}
        return json.loads(r.stdout)
    with ThreadPoolExecutor(max_workers=len(probes)) as ex:
        futures={k:ex.submit(bounded,k) for k in probes};out={}
        for k,f in futures.items():
            try:out[k]=f.result()
            except Exception as e:out[k]={'status':'unavailable','error_type':type(e).__name__}
    if board == 'house-touch':
        out['printers']={'paper':out.pop('paper')}
    return out


def readiness(board,now):
    cache=MEM/('house-readiness-'+board+'.json')
    old=read_json(cache,{})
    if isinstance(old,dict) and 0 <= now-stamp(old.get('checked')) <= 60:return old
    try:
        r=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--probe',board],
                         capture_output=True,text=True,timeout=12)
        if r.returncode:raise RuntimeError('probe failed')
        data=json.loads(r.stdout);out={'checked':time.time(),'devices':data}
        # A cache contains sanitized device metadata only, never tokens or messages.
        import tempfile
        cache.parent.mkdir(exist_ok=True,parents=True)
        fd,tmp=tempfile.mkstemp(prefix='.house-ready-',dir=cache.parent)
        try:
            with os.fdopen(fd,'w') as f:json.dump(out,f)
            os.replace(tmp,cache)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        return out
    except Exception as e:
        return {'checked':None,'status':'unavailable','error_type':type(e).__name__}


def snapshot(board,st,now,cfg,probe=True):
    conversation=recent_conversation(now)
    try:catalog=song_catalog(conversation) if board=='house-steam' else []
    except Exception:catalog=[]
    pending=desktop_approvals(st)
    sh=st.get('shower',{})
    try:
        import room_proximity
        nearest=room_proximity.nearest(now=now)
    except Exception:nearest=None
    rows=tail_rows(MEM/'house-actions.jsonl')
    today=datetime.fromtimestamp(now).date()
    used=sum(datetime.fromtimestamp(stamp(r.get('at'))).date()==today and r.get('kind')=='house' for r in rows)
    try:
        import house_hands
        limit=house_hands.PER_DAY.get('house')
    except Exception:limit=None
    return {'action_candidates':action_candidates(board, conversation), 'capability_options':capability_options(board),
            'desktop_approvals':pending, 'conversation':conversation,'readiness':readiness(board,now) if probe else {},
            'outcomes':previous_outcomes(now),'catalog':catalog,
            'state':{'nearest_room':nearest,'pending_desktop_approvals':len(pending),
                     'shower_active':sh.get('on') is True,'player':sh.get('player','unknown'),
                     'queue_count':len(sh.get('queue',[])),
                     'queued_titles':[short(r.get('title'),100) if isinstance(r,dict) else 'legacy audio' for r in sh.get('queue',[])[:4]],
                     'audio_inflight':{k:sh.get('inflight',{}).get(k) for k in ('title','status')},
                     'house_action_limit':limit,
                     'house_actions_observed_today':used}}


def public_packet(ctx):
    # Audio URLs stay local; the model can choose only stable IDs and titles.
    packet = {**ctx,'catalog':[{'id':r['id'],'title':short(r['title'],120)} for r in ctx.get('catalog',[])]}
    for key in ('conversation', 'outcomes'):
        packet[key] = [{**{k:v for k,v in r.items() if k != 'ts'},
                        'at':datetime.fromtimestamp(r['ts']).astimezone().isoformat(timespec='seconds')}
                       for r in ctx.get(key, [])]
    return packet


def receipt(ctx):
    packet=public_packet(ctx)
    return {'version':1,'conversation_rows':len(ctx.get('conversation',[])),
            'outcomes':len(ctx.get('outcomes',[])),'song_candidates':len(ctx.get('catalog',[])),
            'readiness_checked':ctx.get('readiness',{}).get('checked'),
            'packet_sha256':hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()}


if __name__=='__main__' and len(sys.argv)==3 and sys.argv[1]=='--probe':
    print(json.dumps(_probe(sys.argv[2])))
elif __name__=='__main__' and len(sys.argv)==4 and sys.argv[1]=='--probe-one':
    print(json.dumps(_probe(sys.argv[2],sys.argv[3])))


def action_candidates(board, conversation):
    """Ground optional house acts in current work, without granting authority."""
    rows = read_json(MEM/'current-wants.json', [])
    if not isinstance(rows, list): return []
    patterns = {'DESKTOP': r'\b(browser|desktop|computer|document|spreadsheet|chart|file|website|search|compare|read|write|render)\b',
                'TV': r'\b(watch|video|film|movie|youtube|documentary|television)\b',
                'PAPER': r'\b(paper|poster|printout|postcard|photo|painting|poem)\b'}
    import re
    out = []
    rows = sorted([w for w in rows if isinstance(w, dict)],
                  key=lambda w: stamp(w.get("timestamp") or w.get("created_at")), reverse=True)
    # The wants board's own tests, so a house act never revives what the board has set aside (17 November, on
    # integrating with the want gates): waiting on Gloria is the final stage and expires on want_completion's clock,
    # a parked want (any board) is off the working board, and the source label is spelled the one canonical way.
    try:
        from want_board import waiting_on_gloria as _waiting
    except Exception:
        _waiting = lambda w: bool(w.get('gloria_routed')) or w.get('board') == 'awaiting_gloria'
    try:
        from want_contract import canonical_source as _canon
    except Exception:
        _canon = lambda s: s
    for w in rows:
        if (not isinstance(w, dict) or w.get('fulfilled') or w.get('dismissed') or _waiting(w)
                or w.get('board')): continue
        text = str(w.get('want') or '')
        for act, pattern in patterns.items():
            allowed = {'house-touch': {'DESKTOP', 'PAPER'}, 'house-press-mic': {'TV'}}.get(board, set())
            if act not in allowed: continue
            if re.search(pattern, text, re.I):
                out.append({'want_id':w.get('id'), 'objective':short(text,600),
                            'possible_action':act, 'source':_canon(w.get('source')) if w.get('source') else w.get('source'),
                            'execution_status':(w.get('agent_work') or {}).get('status','not agent-owned'),
                            'authority':'proposal only; existing approval and in-use protections apply'})
        if len(out)>=5: break
    return out[:5]



"""House bridge to the single Forge queue and execution budget. No provider calls."""
import json
import os
from pathlib import Path
from urllib.request import Request
from lab_http import open_request

TOKEN_FILE = Path.home()/'.config/vintos/forge-owner'
BASE = 'http://127.0.0.1:8612'


def request(path, body, transport=None):
    from forge_loop_runtime import secret
    req = Request(BASE + path, data=json.dumps(body).encode(), method='POST',
                  headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + secret(TOKEN_FILE)})
    with (transport or open_request)(req, timeout=15) as response:
        data = response.read(1024*1024+1)
    if len(data) > 1024*1024: raise ValueError('Forge response too large')
    return json.loads(data)


def reserve(proposal, attempt):
    return request('/api/build-reservation', {'proposal': proposal, 'attempt': attempt}).get('reserved') is True


def plugin_query(plugin, tool, arguments, purpose):
    """Forge-side explicit plugin operation; the caller supplies the real project purpose."""
    gateway = os.environ.get('VINTOS_PLUGIN_GATEWAY_URL', '').strip()
    if not gateway: raise ValueError('Forge plugin gateway URL missing')
    from forge_loop_runtime import secret
    token_file = os.environ.get('VINTOS_PLUGIN_GATEWAY_TOKEN', '').strip()
    if not token_file: raise ValueError('Forge plugin gateway token credential missing')
    req = Request(gateway, data=json.dumps({'plugin':plugin,'tool':tool,'arguments':arguments,
                                            'purpose':purpose}).encode(), method='POST',
                  headers={'Content-Type':'application/json','Authorization':'Bearer '+secret(token_file)})
    with open_request(req, timeout=210) as response:
        data=response.read(1024*1024+1)
    if len(data)>1024*1024: raise ValueError('plugin gateway response too large')
    result=json.loads(data)
    if isinstance(result,dict) and result.get('held') is True and isinstance(result.get('receipt'),dict):
        return result
    if not isinstance(result,dict) or result.get('ok') is not True:
        raise PermissionError('plugin gateway held or failed the call')
    return result


def sync(inventory=None):
    import skill_forge as sf
    from forge_build import artifact_valid
    wants = json.loads((Path(sf.MEMORY)/'current-wants.json').read_text())
    if not isinstance(wants, list): raise ValueError('wants store is not a list')
    by_id = {w['id']: w for w in wants if isinstance(w, dict) and w.get('id')}
    # Replay the proposal write if a prior pass persisted the absence block then crashed.
    from want_spine import missing_hand
    for want in wants:
        block = want.get('blocked') or {}
        cap = block.get('blocked_step')
        if block.get('block_type') == 'CAPABILITY_ABSENT' and cap and not want.get('fulfilled') and not want.get('dismissed'):
            missing_hand(cap, want.get('want',''), want, path=str(Path(sf.MEMORY)/'current-wants.json'))
    if inventory is not None:
        sync_assessments(wants, inventory, sf)
    rows = []
    for p in sf._load():
        origin = p.get('origin') or {}
        wid = origin.get('want_id')
        if not wid: continue  # Atelier undertaking proposals retain their existing bridge.
        want = by_id.get(wid)
        state = p['state']
        if not want or want.get('fulfilled') or want.get('dismissed'): state = 'origin_ended'
        rows.append({'proposal': p['id'], 'want_id': wid,
                     'intent': (want or {}).get('want') or origin.get('want') or 'Ended intention',
                     'source': origin.get('spark') or origin.get('source') or 'unclassified',
                     'capability': p['capability'], 'state': state,
                     'artifact_verified': state in ('installed', 'resumed') and artifact_valid(p, installed=True)})
    # Fail rather than silently omit parent cancellation in a truncated snapshot.
    if len(rows) > 128: raise ValueError('Forge gap snapshot exceeds 128; explicit pagination required')
    return request('/api/gaps-sync', {'rows': rows})


def fingerprint(want):
    import hashlib
    return hashlib.sha256(json.dumps({'want':want.get('want'),'steps':want.get('steps',[]),
        'index':want.get('current_step_index',0)},sort_keys=True).encode()).hexdigest()


def sync_assessments(wants, inventory, sf):
    from store_guard import locked_update
    from want_spine import missing_hand
    path=Path(sf.MEMORY)/'current-wants.json'
    selected=[w for w in wants if isinstance(w,dict) and w.get('id') and w.get('want')
              and not w.get('fulfilled') and not w.get('dismissed') and not w.get('blocked')
              and sf.spark_of(w.get('source')) is not None]
    rows=[{'id':w['id'],'want':w['want'],'source':sf.spark_of(w['source']),
           'steps':w.get('steps',[]),'fingerprint':fingerprint(w)} for w in selected]
    results=request('/api/wants-sync',{'rows':rows,'inventory':sorted(set(inventory))})
    for result in results:
        assessment=result.get('assessment') or {}
        if assessment.get('missing') is not True: continue
        cap=assessment.get('capability')
        import re
        if not isinstance(cap,str) or not re.fullmatch('[a-z][a-z0-9_]{1,79}',cap) or cap in inventory: continue
        adopted=[]
        def mutate(current):
            for w in current:
                if w.get('id') != result['want_id'] or w.get('fulfilled') or w.get('dismissed') or w.get('blocked'): continue
                if fingerprint(w)!=result['fingerprint']: continue
                if any(s.get('forge_assessment')==result['project'] for s in w.get('steps',[])): continue
                # Preserve existing steps and their status; insert the necessary missing
                # action at the current execution boundary, not as a replacement desire.
                steps=w.setdefault('steps',[]); index=w.get('current_step_index',0)
                if type(index) is not int or not 0<=index<=len(steps): continue
                step={k:assessment[k] for k in ('capability','note','execution','expected_output','acceptance')}
                if isinstance(assessment.get('hardware_proposal'), dict):
                    step['hardware_proposal'] = assessment['hardware_proposal']
                step.update(status='pending',forge_assessment=result['project'])
                steps.insert(index,step)
                w.update(multistep=True,capability='multistep',plan_state='READY')
                w['blocked']={'block_type':'CAPABILITY_ABSENT','blocked_step':cap,
                    'evidence':'Forge assessment against installed inventory: '+str(assessment.get('reason',''))[:300],
                    'resume_event':'capability installed or step revised'}
                adopted.append(dict(w));return current
            return None
        locked_update(str(path),mutate,reader='forge_house')
        if adopted: missing_hand(cap,assessment['note'],adopted[0],path=str(path))

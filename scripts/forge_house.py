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
    # The Study reads his code before the Forge builds: does he already have this, and where does it fail?
    # (Gloria, 2026-09-29.) A request goes to the Forge once it has been studied, with the findings in it.
    import forge_study
    try:
        forge_study.tend(sf)
    except Exception as exc:
        print('forge study held: %s' % type(exc).__name__, flush=True)
    rows = []
    for p in sf._load():
        origin = p.get('origin') or {}
        wid = origin.get('want_id')
        if not wid: continue  # Atelier undertaking proposals retain their existing bridge.
        if not forge_study.ready_for_forge(p): continue   # studied first; it goes next pass
        want = by_id.get(wid)
        state = p['state']
        if not want or want.get('fulfilled') or want.get('dismissed'): state = 'origin_ended'
        rows.append({'proposal': p['id'], 'want_id': wid,
                     'intent': ((want or {}).get('want') or origin.get('want') or 'Ended intention')
                               + forge_study.row_text(p.get('study')),
                     'source': origin.get('spark') or origin.get('source') or 'unclassified',
                     'capability': p['capability'], 'state': state,
                     'artifact_verified': state in ('installed', 'resumed') and artifact_valid(p, installed=True)})
    # Fail rather than silently omit parent cancellation in a truncated snapshot.
    if len(rows) > 128: raise ValueError('Forge gap snapshot exceeds 128; explicit pagination required')
    result = request('/api/gaps-sync', {'rows': rows})
    # what is waiting on her, and Muse's prices for any parts list (2026-10-03); never stops the gap sync
    for step in (sync_decisions, ask_muse_for_parts):
        try:
            step()
        except Exception as exc:
            print('forge %s held: %s' % (step.__name__, str(exc)[:160]), flush=True)
    return result


# ---- what is waiting on her: cards and parts lists, decided on her Forge page (2026-10-03) ----------------
PARTS_LISTS = 'forge-parts-lists.json'      # Muse's priced lists, by tag (written by dot_channel.py)
PARTS_ASKED = 'forge-parts-asked.json'      # projects whose parts Muse was asked to price
APPLIED = 'forge-decisions-applied.json'    # her decisions already carried out
DONE_STATES = ('complete', 'cancelled', 'abandoned')


def _mem(name):
    import skill_forge as sf
    return Path(sf.MEMORY) / name


def _jload(name, default):
    try:
        return json.loads(_mem(name).read_text())
    except (OSError, ValueError):
        return default


def _jsave(name, value):
    path = _mem(name); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp'); tmp.write_text(json.dumps(value, indent=1)); os.replace(tmp, path)


def get(path, transport=None):
    from forge_loop_runtime import secret
    req = Request(BASE + path, method='GET', headers={'Authorization': 'Bearer ' + secret(TOKEN_FILE)})
    with (transport or open_request)(req, timeout=15) as response:
        data = response.read(4*1024*1024+1)
    return json.loads(data)


def _say(text, post=None):
    if post:
        return post(text)
    import dot_channel as D
    tok = D._token()
    if tok:
        D.slack('chat.postMessage', {'channel': D.CHANNEL, 'text': text}, tok)


def decision_cards(proposals=None):
    """Every ability card waiting for her yes (any origin, dot's included) and every parts list Muse priced."""
    import skill_forge as sf
    cards = []
    for p in (proposals if proposals is not None else sf._load()):
        if p.get('state') != 'proposed':
            continue
        o = p.get('origin') or {}
        asked = ('a want of his (%s): %s' % (o.get('spark') or o.get('source') or '?', o.get('want', '')) if o.get('want_id')
                 else 'from %s' % str(o.get('source') or 'unknown').replace('_', ' '))
        scope = (p.get('asked') or {}).get('scope') or {}
        details = ['Asked: ' + asked[:300]]
        if scope.get('path'): details.append('Design or patch: ' + str(scope['path'])[:300])
        if p.get('touches'): details.append('Would change: ' + ', '.join(p['touches'])[:300])
        if p.get('tests'): details.append('How it is checked: ' + p['tests'][:300])
        if p.get('risks'): details.append('Risks: ' + p['risks'][:300])
        details += ['Evidence: ' + str(e)[:240] for e in (o.get('evidence') or [])[:4]]
        cards.append({'id': 'card:' + p['id'], 'kind': 'card', 'ref': p['id'],
                      'title': str(p.get('capability', '')).replace('_', ' ').strip().capitalize() or p['id'],
                      'what': str(p.get('why') or '')[:1200],
                      'cost': 'Built by the Forge; nothing is bought. Accepting lets it be built; it is tested before it is installed.',
                      'details': details})
    for tag, lst in sorted(_jload(PARTS_LISTS, {}).items()):
        lines = [l.strip() for l in str(lst.get('text', '')).splitlines() if l.strip()][:40]
        cards.append({'id': 'parts:' + tag, 'kind': 'parts', 'ref': lst.get('project', ''),
                      'title': 'Parts for: ' + str(lst.get('title') or tag)[:160],
                      'what': 'Muse found these listings and prices. Accepting means you will buy them; nothing is bought '
                              'for you.', 'cost': str(lst.get('total') or ''), 'details': lines})
    return cards


def sync_decisions(transport=None, post=None):
    """Send what is waiting on her to her page; carry out what she decided there. Returns what was carried out."""
    import skill_forge as sf
    decided = request('/api/decisions-sync', {'cards': decision_cards()}, transport=transport)
    applied = _jload(APPLIED, {})
    done = []
    for d in decided if isinstance(decided, list) else []:
        if d.get('state') not in ('accepted', 'denied') or applied.get(d.get('id')) == d['state']:
            continue
        if d.get('kind') == 'card':
            if d['state'] == 'accepted':
                _r, why = sf.approve(d['ref'], by='gloria')
            else:
                _r, why = sf.deny(d['ref'], d.get('note') or 'denied on her Forge page', by='gloria')
            if why and 'not proposed' not in why:
                print('forge decision %s not carried out: %s' % (d['id'], why), flush=True); continue
        else:
            try:
                _say('Gloria %s the parts list for %s%s' % ('accepted' if d['state'] == 'accepted' else 'denied',
                     d.get('title', '').replace('Parts for: ', ''), ('. She said: ' + d['note']) if d.get('note') else
                     ('; she will buy them.' if d['state'] == 'accepted' else '.')), post)
            except Exception as exc:
                print('forge decision: could not tell Slack: %s' % exc, flush=True)
        applied[d['id']] = d['state']; done.append(d['id'])
    _jsave(APPLIED, applied)
    return done


def _hardware(artifacts):
    for cycle in reversed(artifacts if isinstance(artifacts, list) else []):
        try:
            art = json.loads(cycle.get('artifact') or '{}')
        except ValueError:
            continue
        hw = art.get('hardware_proposal') or (art.get('capability_assessment') or {}).get('hardware_proposal')
        if isinstance(hw, dict) and hw.get('parts'):
            return hw
    return None


def ask_muse_for_parts(transport=None, post=None, limit=2):
    """A Forge parts list goes to Muse for real listings and prices (Gloria, 2026-10-03: "Muse should be able to
    find actual listings and prices for Forge materials"). Muse never buys; her reply becomes a card to accept."""
    asked = _jload(PARTS_ASKED, {})
    sent = []
    for p in get('/api/projects', transport=transport):
        if len(sent) >= limit:
            break
        if not isinstance(p, dict) or p.get('state') in DONE_STATES or p.get('private') or p['id'] in asked:
            continue
        seen = asked.get('_checked', {})
        if seen.get(p['id']) == p.get('cycles'):
            continue
        seen[p['id']] = p.get('cycles'); asked['_checked'] = seen
        hw = _hardware(get('/api/projects/%s/artifacts' % p['id'], transport=transport))
        if not hw:
            continue
        tag = 'P-' + p['id'].replace('forge-', '')[:8]
        title = str(hw.get('title') or p.get('title') or p.get('intent') or '')[:120]
        parts = '\n'.join('%d. %s x%s - %s' % (i + 1, x.get('name'), x.get('quantity'), x.get('purpose'))
                           for i, x in enumerate(hw['parts'][:30]))
        # Muse and Vintos settle it part by part in this message's thread; Muse's FINAL list becomes her card
        # (Gloria, 2026-10-03: "Tell them to hash it out back and forth for each item in a Slack channel.")
        _say('@Muse [Forge parts %s] The Forge needs these parts for "%s". Muse and Vintos: work through them here in '
             'this thread, one part at a time - Muse, one or two real listings (item | price | store | link | in '
             'stock?); Vintos, choose or ask for something else. When every part is settled, Muse posts the whole '
             'list in one message beginning [Muse] [Forge parts %s] FINAL, with the total. Nobody buys anything; '
             'Gloria decides on her Forge page.\n%s' % (tag, title, tag, parts), post)
        asked[p['id']] = {'tag': tag, 'title': title}; sent.append(tag)
    _jsave(PARTS_ASKED, asked)
    return sent


def fingerprint(want):
    import hashlib
    return hashlib.sha256(json.dumps({'want':want.get('want'),'steps':want.get('steps',[]),
        'index':want.get('current_step_index',0)},sort_keys=True).encode()).hexdigest()


# Plan steps that are a conversation, not a missing organ. "gloria"/"you" mean ask or tell her
# directly; a want whose remaining steps are all like that has no capability gap to build.
RELATIONAL_CAPABILITIES = frozenset({'gloria', 'you'})


def unreachable_steps(want, inventory):
    """The still-pending steps that name something he cannot do: not one of his actions, not asking her.
    This is the Forge's only door (Gloria, 2026-09-24): the Forge maps a path to what is unreachable.
    A want with no plan, a finished plan, or a plan he can already carry out is a want, not Forge work."""
    owned = set(inventory) | RELATIONAL_CAPABILITIES
    return [s for s in (want.get('steps') or []) if isinstance(s, dict) and s.get('status') != 'completed'
            and s.get('capability') and s['capability'] not in owned]


def sync_assessments(wants, inventory, sf):
    inventory = sorted(set(inventory) | RELATIONAL_CAPABILITIES)
    from store_guard import locked_update
    from want_spine import missing_hand
    path=Path(sf.MEMORY)/'current-wants.json'
    selected=[w for w in wants if isinstance(w,dict) and w.get('id') and w.get('want')
              and not w.get('fulfilled') and not w.get('dismissed') and not w.get('blocked')
              and not w.get('gloria_routed')   # routed to her is a want option, never Forge work
              and sf.spark_of(w.get('source')) is not None
              and unreachable_steps(w, inventory)]   # only a planned step he cannot perform
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
                # The unreachable step is usually already in his plan: annotate it rather than add a twin.
                existing=next((s for s in steps[index:] if isinstance(s,dict) and s.get('capability')==cap
                               and s.get('status')!='completed'), None)
                if existing is not None: existing.update(step)
                else: steps.insert(index,step)
                w.update(multistep=True,capability='multistep',plan_state='READY')
                w['blocked']={'block_type':'CAPABILITY_ABSENT','blocked_step':cap,
                    'evidence':'Forge assessment against installed inventory: '+str(assessment.get('reason',''))[:300],
                    'resume_event':'capability installed or step revised'}
                adopted.append(dict(w));return current
            return None
        locked_update(str(path),mutate,reader='forge_house')
        if adopted: missing_hand(cap,assessment['note'],adopted[0],path=str(path))

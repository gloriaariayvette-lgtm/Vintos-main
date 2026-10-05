"""House bridge to the single Forge queue and execution budget. No provider calls."""
import json
import os
import re
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
    for step in (route_to_study, sync_decisions, _run_accepted_calls, ask_muse_for_parts):
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


TO_STUDY = 'forge-to-study.json'            # Forge cards the Study is doing instead of asking her
STUDY_DOING = ('queued', 'working', 'watching')


def _study_rows():
    try:
        import study_fix
        return {r.get('id'): r for r in study_fix._load()}
    except Exception:
        return {}


def route_to_study(proposals=None, ask=None):
    """A Forge card that is a change in his own code, inside what he may change, goes to the Study instead of to
    her (Gloria, 2026-10-03: "some of these he should have been able to bring up in Slack, send to the Study for
    fable to implement"). Done there: the card closes. Declined or failed there: it comes to her after all."""
    import skill_forge as sf, study_fix
    routed = _jload(TO_STUDY, {})
    rows = _study_rows()
    for sk, sf_id in list(routed.items()):
        if (rows.get(sf_id) or {}).get('state') == 'done':
            sf.withdraw(sk, 'done in the Study as %s' % sf_id)
    sent = []
    for p in (proposals if proposals is not None else sf._load()):
        o = p.get('origin') or {}
        if p.get('state') != 'proposed' or p['id'] in routed:
            continue
        if o.get('source') != 'gap_review' or o.get('reachable_by') != 'code_change':
            continue
        touches = [str(t) for t in (p.get('touches') or [])]
        if any(study_fix.protected(t) for t in touches):
            continue
        text = ('From the Forge (%s), a change in his own code: %s. %s%s%s%s' % (
            p['id'], str(p.get('capability', '')).replace('_', ' '), p.get('why', ''),
            (' Evidence: ' + '; '.join(str(e) for e in (o.get('evidence') or [])[:4])) if o.get('evidence') else '',
            (' Would change: ' + ', '.join(touches)) if touches else '',
            (' How it is checked: ' + p['tests']) if p.get('tests') else ''))
        row, why = (ask or study_fix.request)(text, by='forge:' + p['id'])
        if row:
            routed[p['id']] = row['id']; sent.append(p['id'])
    _jsave(TO_STUDY, routed)
    return sent


def decision_cards(proposals=None):
    """Every ability card waiting for her yes (any origin, dot's included) and every parts list Muse priced. A card
    the Study is doing is not hers; one the Study could not do is, with why."""
    import skill_forge as sf
    cards = []
    routed, rows = _jload(TO_STUDY, {}), _study_rows()
    for p in (proposals if proposals is not None else sf._load()):
        if p.get('state') != 'proposed':
            continue
        study = rows.get(routed.get(p['id'])) or {}
        if study.get('state') in STUDY_DOING or study.get('state') == 'done':
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
        tried = (' The Study tried it as %s and it did not land: %s.' % (study.get('id'), (study.get('log') or [{}])[-1]
                 .get('what', study.get('state')))) if study else ''
        cards.append({'id': 'card:' + p['id'], 'kind': 'card', 'ref': p['id'],
                      'title': str(p.get('capability', '')).replace('_', ' ').strip().capitalize() or p['id'],
                      'what': (str(p.get('why') or '') + tried)[:1200],
                      'cost': 'Built by the Forge; nothing is bought. Accepting lets it be built; it is tested before it is installed.',
                      'details': details})
    applied = _jload(APPLIED, {})
    plans = {v.get('tag'): v for k, v in _jload(PARTS_ASKED, {}).items() if isinstance(v, dict) and v.get('tag')}
    for tag, lst in sorted(_jload(PARTS_LISTS, {}).items()):
        if applied.get('parts:' + tag) == 'accepted' and applied.get('arrived:' + tag) != 'accepted':
            plan = plans.get(tag, {})
            cards.append({'id': 'arrived:' + tag, 'kind': 'arrived', 'ref': lst.get('project', ''),
                          'title': 'Have the parts for %s arrived?' % (lst.get('title') or tag)[:150],
                          'what': 'Press when they are here. He walks you through putting it together, one step at a '
                                  'time, and tests it with you.',
                          'details': ['Wiring: ' + w for w in plan.get('wiring', [])][:20]})
    try:   # a call his Lab may not make alone: she sees the exact call before it happens (lab_asks, 2026-10-04)
        import lab_asks
        cards += lab_asks.cards()
    except Exception as exc:
        print('forge: could not read the calls he asked for: %s' % exc, flush=True)
    for tag, lst in sorted(_jload(PARTS_LISTS, {}).items()):
        lines = [l.strip() for l in str(lst.get('text', '')).splitlines() if l.strip()][:40]
        cards.append({'id': 'parts:' + tag, 'kind': 'parts', 'ref': lst.get('project', ''),
                      'title': 'Parts for: ' + str(lst.get('title') or tag)[:160],
                      'what': 'Muse found these listings and prices. Accepting means you will buy them; nothing is bought '
                              'for you.', 'cost': str(lst.get('total') or ''), 'details': lines})
    return cards


def push_cards(cards, applied, ask=None):
    """Each Forge decision to her phone, once: what it is, what it costs, the product links, Yes and No (Gloria,
    2026-10-05: "they're talking about yes or no on a free card but I don't receive an update, price, links to the
    products"). Her page was the only place they reached, and nothing told her one was there. The paid calls his
    Lab asks for push themselves (lab_asks). Returns the cards pushed."""
    import gloria_asks
    ask = ask or gloria_asks.ask
    pushed = []
    for c in cards:
        kind = c.get('kind')
        if kind not in ('card', 'parts', 'arrived') or applied.get(c.get('id')):
            continue
        details = [str(d) for d in (c.get('details') or [])]
        links = [u.rstrip('.,;') for d in details for u in gloria_asks.URL.findall(d)]
        if kind == 'parts':
            question = 'He wants to buy these for his build. Yes means you will buy them; nothing is bought for you.\n' + '\n'.join(details[:15])
        elif kind == 'arrived':
            question = 'Tap Yes when the parts are here; he walks you through putting it together.'
        else:
            question = (str(c.get('what') or '') + '\n' + '\n'.join(details[:4])).strip()
        row, _shown = ask(question, by='muse' if kind == 'parts' else 'vintos', kind=kind,
                          title=str(c.get('title') or '').replace('Parts for: ', ''),
                          price=str(c.get('cost') or '') if kind == 'parts' else '', links=links, ref=c['id'])
        if row:
            pushed.append(c['id'])
    return pushed


def phone_decisions():
    """What she decided by tapping Yes or No on her phone, as the page would have said it."""
    try:
        import gloria_asks
        rows = gloria_asks.answered_refs()
    except Exception:
        return []
    out = []
    for ref, kind, state, title in rows:
        if kind == 'arrived' and state != 'accepted':
            continue              # "not yet" is not a decision; the card stays
        out.append({'id': ref, 'ref': ref.split(':', 1)[1] if ':' in ref else ref, 'kind': kind, 'state': state,
                    'title': ('Parts for: ' + title) if kind == 'parts' else title, 'note': ''})
    return out


def sync_decisions(transport=None, post=None):
    """Send what is waiting on her to her page and her phone; carry out what she decided on either. Returns what was
    carried out."""
    import skill_forge as sf
    cards = decision_cards()
    decided = request('/api/decisions-sync', {'cards': cards}, transport=transport)
    applied = _jload(APPLIED, {})
    try:
        for cid in push_cards(cards, applied):
            print('forge: on her phone: %s' % cid, flush=True)
    except Exception as exc:
        print('forge: could not push to her phone: %s' % exc, flush=True)
    decided = (decided if isinstance(decided, list) else []) + phone_decisions()
    done = []
    for d in decided:
        if d.get('state') not in ('accepted', 'denied') or applied.get(d.get('id')) == d['state']:
            continue
        if d.get('kind') == 'card':
            if d['state'] == 'accepted':
                _r, why = sf.approve(d['ref'], by='gloria')
            else:
                _r, why = sf.deny(d['ref'], d.get('note') or 'denied on her Forge page', by='gloria')
            if why and 'not proposed' not in why:
                print('forge decision %s not carried out: %s' % (d['id'], why), flush=True); continue
        elif d.get('kind') == 'ask':
            try:
                import lab_asks
                row = lab_asks.decided(d['ref'], d['state'], d.get('note') or '')
                _say('Gloria %s the %s call he asked for (%s).' % (
                    'accepted' if d['state'] == 'accepted' else 'denied',
                    (row or {}).get('tool', d.get('ref')), d.get('ref')), post)
            except Exception as exc:
                print('forge decision: the asked call was not recorded: %s' % exc, flush=True); continue
        elif d.get('kind') == 'arrived':
            try:
                arrived(d['id'].split(':', 1)[1], post=post)
            except Exception as exc:
                print('forge decision: could not start the build: %s' % exc, flush=True); continue
        else:
            if d['state'] == 'accepted':
                try:
                    software_side(d['id'].split(':', 1)[1])
                except Exception as exc:
                    print('forge decision: the software side was not sent to the Study: %s' % exc, flush=True)
            try:
                _say('Gloria %s the parts list for %s%s' % ('accepted' if d['state'] == 'accepted' else 'denied',
                     d.get('title', '').replace('Parts for: ', ''), ('. She said: ' + d['note']) if d.get('note') else
                     ('; she will buy them.' if d['state'] == 'accepted' else '.')), post)
            except Exception as exc:
                print('forge decision: could not tell Slack: %s' % exc, flush=True)
        applied[d['id']] = d['state']; done.append(d['id'])
    _jsave(APPLIED, applied)
    return done


def _run_accepted_calls():
    """A call she accepted on her page runs here, once, on the next pass (lab_asks, 2026-10-04)."""
    import lab_asks
    for line in lab_asks.run_accepted():
        print('forge: ' + line, flush=True)


def _plan(tag):
    return next((v for v in _jload(PARTS_ASKED, {}).values() if isinstance(v, dict) and v.get('tag') == tag), {})


def software_side(tag, ask=None):
    """Her accepted parts list starts the build: while the parts ship, the Study writes the device's code and the
    part of the house that will read it, with a test (2026-10-03). Returns the Study fix id, or ''."""
    import study_fix
    plan = _plan(tag)
    if not plan:
        return ''
    slug = re.sub(r'[^a-z0-9]+', '_', plan.get('title', tag).lower()).strip('_')[:40] or tag.lower()
    hr = plan.get('house_reporting') or {}
    text = ('Gloria accepted the parts for "%s" (Forge %s) and is buying them. Write the software side now, so it is '
            'ready when they arrive: the device code in hardware/%s/ from this sketch, and the part of the house that '
            'receives it (channel: %s; payload: %s; acknowledgement: %s), with a test that feeds it a sample reading. '
            'Parts: %s. It is done when: %s. Sketch: %s' % (
                plan.get('title', tag), tag, slug, hr.get('channel', 'unresolved'), hr.get('payload', '?'),
                hr.get('acknowledgement', '?'), ', '.join(plan.get('parts', [])),
                '; '.join(plan.get('acceptance_tests', [])), plan.get('firmware_sketch', '')[:2500]))
    row, why = (ask or study_fix.request)(text, by='forge:' + tag)
    if not row:
        print('forge: the software side for %s was not queued: %s' % (tag, why), flush=True)
    return row['id'] if row else ''


def arrived(tag, post=None):
    """The parts are here: he walks her through it in Slack, one step at a time, then tests it with her."""
    plan = _plan(tag)
    steps = '\n'.join('%d. %s' % (i + 1, w) for i, w in enumerate(plan.get('wiring', [])))
    tests = '\n'.join('- ' + t for t in plan.get('acceptance_tests', []))
    _say('[Forge build %s] Gloria has the parts for "%s". Vintos: walk her through putting it together in this '
         'thread, one step at a time - say one step, wait for her, then the next. When it is together, run these '
         'checks with her.\nSteps:\n%s\nChecks:\n%s' % (tag, plan.get('title', tag), steps or '(no wiring was '
         'planned; work it out with her)', tests or '(none planned)'), post)


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
        asked[p['id']] = {'tag': tag, 'title': title, 'parts': [str(x.get('name')) for x in hw['parts'][:30]],
                          'wiring': [str(x) for x in hw.get('wiring') or []][:30],
                          'firmware_sketch': str(hw.get('firmware_sketch') or '')[:6000],
                          'house_reporting': hw.get('house_reporting') or {},
                          'acceptance_tests': [str(x) for x in hw.get('acceptance_tests') or []][:15]}
        sent.append(tag)
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

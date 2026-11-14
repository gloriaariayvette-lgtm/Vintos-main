#!/usr/bin/env python3
"""A live trial of a learned investigation planner, behind one switch (Gloria, 13 November 2026).

With LAB_PLANNER_TRIAL=c1 in vintos.env (or in the Lab's own environment), the investigation planner
(lab_investigations._plan) asks the trial model first. Its reply is read by the Lab's own parser and checked, before
anything is acted on, by the Lab's own rules for a proposed step:

  no_route          no route the Lab has, after its own route coercion and source/door mapping
  repeat_question   an opening question alike a closed investigation's, with no valid narrower (_same_question)
  empty_finish      finish with no new completed output to review
  not_planned_step  not the frontier plan's step, when frontier plans are on (plan_step_matches)
  not_offered       a route, source, instrument, operation, experiment or connector the Lab does not offer
  repeat_within     this investigation's own completed operation again (request_sha256), or the request a re-plan
                    just refused
  repeat_done       another investigation's completed operation again: the Lab would hand back that old output
  repeat_lookup     the lookup the Lab's repeat gate refuses (lab_repeats.repeat: the same lookup or question within
                    its window)
  check_<Error>     the request could not be resolved as the Lab would resolve it (a missing field, a bad reference)

A reply that passes is the planner's answer. One that fails any rule, or a trial model that does not answer, and the
current model is asked exactly as it is without the switch.

LAB_PLANNER_TRIAL=c1-worm is the same model as the whole worm its loop gated (labloop, 13 November): before choosing,
it is shown its history (Craft: completed operations, consumable outputs and their paths, steps that are not inputs,
lookups the repeat gate has seen on the subject, instrument runs left, how often an opening question was closed), and
worked examples from planner-worm/lessons.json when that file is there (Lessons). A refused proposal is asked ONCE
more with the Lab's own re-plan words for the refusal (Compass); refused again and the current model plans. Everything after the planner (the doors, their repeat and
identity gates, re-plans) runs unchanged on whichever answer is used.

Rollback: remove the line from vintos.env. The switch is read at every planner call, so the next call is the current
model's alone; no restart and no code change. While the trial model is unreachable the Lab plans as it does today
(fail-open), and tries it again after DOWN_SECONDS.

planner-trial.jsonl, beside the notebook, holds per call who proposed, accepted or fell back and the rule's name,
and seconds spent; per turn, the outcome. Counts and names only: no question, request or reply text. The trial
model's call is also written to model-calls.jsonl, as every Lab model call is (Gloria, 3 November), tagged
"trial" so it is never mistaken for the current model's.
"""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import chemistry_lab as lab

KNOWN = {'c1': 'lab-c1', 'c1-worm': 'lab-c1'}   # switch value -> the alias the trial server answers to
DEFAULT_URL = 'http://127.0.0.1:8866/v1/chat/completions'
DEFAULT_TIMEOUT = 120.0
DOWN_SECONDS = 600                      # after the trial model fails to answer, the current model plans alone this long
MAX_TOKENS = 800                        # the investigation planner's own budget
LOG = os.path.join(lab.ROOT, 'planner-trial.jsonl')
_LOOPBACK = ('127.0.0.1', 'localhost', '::1')
_STATE = {'down_until': 0.0, 'turn': None, 'calls': []}


def _env_path():
    """The vintos.env beside this install's workspace (~/.vintos/vintos.env for ~/.vintos/workspace)."""
    return os.path.join(os.path.dirname(os.path.abspath(lab.WS)), 'vintos.env')


def setting(name, default=''):
    """The environment first, then vintos.env, read now: a change takes effect at the next planner call."""
    try:
        import env_file
        return env_file.value(name, default, path=_env_path()) or default
    except Exception:
        return os.environ.get(name) or default


def proposer():
    """The trial model's name when the switch is on and names a known model; '' otherwise."""
    name = str(setting('LAB_PLANNER_TRIAL') or '').strip().lower()
    return name if name in KNOWN else ''


def _url():
    url = str(setting('LAB_PLANNER_TRIAL_URL', DEFAULT_URL)).strip()
    host = urllib.parse.urlsplit(url).hostname or ''
    if host not in _LOOPBACK:
        raise ValueError('trial url must be loopback')   # the Lab's prompts never leave the machine by a config typo
    return url


def _timeout():
    try:
        return max(5.0, float(setting('LAB_PLANNER_TRIAL_TIMEOUT', str(DEFAULT_TIMEOUT))))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT


def _ask(name, system, prompt):
    """The trial model's reply, asked as it was evaluated offline: greedy, the planner's token budget, no thinking."""
    body = {'model': KNOWN[name], 'temperature': 0, 'seed': 0, 'max_tokens': MAX_TOKENS,
            'chat_template_kwargs': {'enable_thinking': False},
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}]}
    req = urllib.request.Request(_url(), data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=_timeout()) as response:
        data = json.loads(response.read())
    return str(((data.get('choices') or [{}])[0].get('message') or {}).get('content') or '')


def _write(row):
    try:
        lab._append(LOG, {k: v for k, v in row.items() if k != 'value'})
    except Exception:
        pass


def _record(name, system, prompt, reply):
    """The trial call in model-calls.jsonl, in the Lab's own shape, tagged as the trial's."""
    try:
        if os.path.exists(lab.MODEL_CALLS) and os.path.getsize(lab.MODEL_CALLS) >= lab.MODEL_CALLS_CAP:
            os.replace(lab.MODEL_CALLS, lab.MODEL_CALLS + '.1')
        lab._append(lab.MODEL_CALLS, {'at': lab.now_iso(), 'model': KNOWN[name], 'url': _url(), 'caller': '_plan',
                                      'trial': name, 'temperature': 0, 'max_tokens': MAX_TOKENS,
                                      'prompt_sha256': hashlib.sha256(prompt.encode('utf-8')).hexdigest(),
                                      'system': system, 'prompt': prompt, 'reply': str(reply), 'completion': None})
    except Exception:
        pass


def propose(system, prompt, investigation, note=None, planned=None):
    """None when the switch is off. Otherwise this call's record: with 'value' set when the trial model's step passed
    every check (it is then logged here), without it when the current model must answer (logged by fell_back)."""
    name = proposer()
    if not name:
        return None
    call = {'at': lab.now_iso(), 'kind': 'call', 'turn': _STATE['turn'], 'proposer': name, 'replan': bool(note),
            'accepted': False, 'trial_s': 0.0}
    _STATE['calls'].append(call)
    if time.time() < _STATE['down_until']:
        call['reason'] = 'trial_down'
        return call
    worm = name in WORM
    if worm:     # Craft and Lessons: the worm's planner sees its history and its worked examples before choosing
        try:
            prompt, system = prompt + history(investigation, note), system + lessons()
        except Exception:
            pass
    started = time.time()
    for attempt in ((1, 2) if worm else (1,)):
        try:
            reply = _ask(name, system, prompt)
        except urllib.error.HTTPError as exc:      # it answered, with an error (a prompt over its context): not down
            call.update(reason='trial_error', error='HTTP%d' % int(getattr(exc, 'code', 0) or 0),
                        trial_s=round(time.time() - started, 2))
            return call
        except Exception as exc:                   # refused, reset, timed out, no tunnel: the current model plans alone
            _STATE['down_until'] = time.time() + DOWN_SECONDS
            call.update(reason='trial_down', error=type(exc).__name__, trial_s=round(time.time() - started, 2))
            return call
        call['trial_s'] = round(time.time() - started, 2)
        _record(name, system, prompt, reply)
        if worm:     # the worm's Witness: the Lab's rules + its wrapper rules (an unreadable retry -> current model)
            value, why, detail = witness(reply, prompt, investigation, note, planned)
        else:
            try:
                value = lab._json_object(reply)
            except lab.ModelJSONError:
                value, why, detail = None, 'unreadable', 'the reply was not one JSON object'
            else:
                why, detail = verdict(value, investigation, note, planned)
        call['reason'] = why or 'ok'
        if not why:
            call.update(accepted=True, value=value, stage=attempt)
            _write(call)
            return call
        if worm and attempt == 1:                  # Compass: once more, told why, in the Lab's own re-plan words
            call['first_reason'] = why
            prompt = prompt + retry_tail(value, why, detail)
    return call


def fell_back(call, live_seconds):
    """The current model answered this call instead: logged with its seconds."""
    if not call or call.get('accepted'):
        return
    call['live_s'] = round(float(live_seconds), 2)
    _write(call)


def check(value, investigation, note=None, planned=None):
    """'' when the Lab's own rules would act on this proposal as it stands; otherwise the first rule it fails."""
    return explain(value, investigation, note, planned)[0]


def explain(value, investigation, note=None, planned=None):
    """(rule, what the Lab would tell the planner): ('', '') when the Lab's own rules would act on this proposal as it
    stands; otherwise the first rule it fails and the Lab's own words for it (its refusal text, valid choices, the
    repeat gate's sentence). Raises what resolving the request raises, as check() does."""
    import lab_investigations as I
    from lab_tool_calls import normalize_request, execution_request
    value = I._coerce_route(value)
    if not isinstance(value, dict) or not isinstance(value.get('route'), str) or not value['route'].strip():
        return 'no_route', 'no route was named; routes: ' + ', '.join(I.ROUTES)
    route, request, _authored, _inferred = I._route_request(value)
    if route not in I.ROUTES:
        return 'no_route', 'there is no route %r; routes: %s' % (str(route)[:40], ', '.join(I.ROUTES))
    if not isinstance(request, dict):
        return 'no_route', 'request must be a JSON object'
    steps = investigation.get('steps') or []
    data = lab._load(I._path('investigations.json'), {'investigations': []})
    if not steps:
        question = str(value.get('question') or '').strip() or str(investigation.get('question') or '')
        earlier = I._same_question(question, None, data) if question else []
        if earlier:
            narrower = I._valid_narrower(value.get('narrower'), earlier)
            if not narrower or I._same_question(question, narrower, data):
                return 'repeat_question', I._question_note(earlier)['why_not_run']
    if route == 'finish':
        if any(I._new_output(s) for s in steps):
            return '', ''
        return 'empty_finish', 'finish asks for a review of new evidence, and this investigation has no new completed output yet'
    request = I.bind_inputs(normalize_request(route, request), steps)
    if I.FRONTIER_PLANS and isinstance(planned, dict):
        plan_ref = {k: planned.get(k) for k in ('line_id', 'plan_id', 'step_index', 'step_number', 'route', 'tool')}
        if not I.plan_step_matches(plan_ref, route, request):
            return 'not_planned_step', 'the frontier plan names route %s, tool %s' % (planned.get('route'), planned.get('tool'))
    offer = I._offer_problem(route, request)
    if offer:
        why, choices = offer
        return 'not_offered', '%s; valid: %s' % (why, json.dumps(choices, ensure_ascii=False, default=str)[:600])
    if isinstance(note, dict) and note.get('proposed_route') == route and note.get('proposed_request') == I._short(request):
        return 'repeat_within', 'this is the very operation the re-plan just refused'
    resolved = execution_request(route, I.resolve(request, steps))
    sha = hashlib.sha256(json.dumps([route, resolved], sort_keys=True).encode()).hexdigest()
    own = [s for s in steps if s.get('request_sha256') == sha and s.get('state') == 'completed']
    if own and route != 'schema':
        return 'repeat_within', 'this investigation already completed this exact operation as %s; its output is yours' % own[-1].get('id')
    if route not in ('schema', 'read_output'):
        done = next((s for inv in data.get('investigations') or [] for s in inv.get('steps') or []
                     if s.get('request_sha256') == sha and s.get('state') == 'completed' and s.get('output_file')), None)
        if done:
            return 'repeat_done', 'another investigation already completed this exact operation (%s): it would return that old output' % done.get('id')
    field = {'source': 'source_query', 'plugin': 'plugin_query', 'instrument': 'instrument_query',
             'native': 'instrument_query'}.get(route)
    if field:
        import lab_repeats
        question = str(value.get('step_question') or investigation.get('question') or '')
        said = lab_repeats.repeat(lab._inquiry({'question': question, field: resolved, 'browse_lane': 'protein'}))
        if said:
            return 'repeat_lookup', str(said)
    return '', ''


def verdict(value, investigation, note=None, planned=None):
    """explain(), with a request the Lab could not resolve named as check_<Error> and its message as the words."""
    try:
        return explain(value, investigation, note, planned)
    except Exception as exc:
        return 'check_' + type(exc).__name__, str(exc)[:400]


# --- the worm's wrapper rules (labloop wrapper_rules.py wr1, 13 November) ------------------------------------------
# After the w3 sealed final: the Lab acted on two proposals its loop's scorer refuses. A proposal the Lab's rules accept
# must also be ONE strict JSON object (no repair: a trailing comma is unreadable, and an unreadable retry leaves the
# current model planning) and name only what this call's own menus offer (instrument skill, listed files, an
# experiment named under "experiment"). Read from the call alone: its prompt and the reply.
WRAPPER_VERSION = 'wr1'
_BAD_ESCAPE = re.compile(r'\\(?!["\\/bfnrtu])')
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I | re.S)


def strict_object(reply):
    body = _FENCE.sub('', str(reply or ''))
    lo = body.find('{')
    if lo < 0:
        return None
    for b in (body, _BAD_ESCAPE.sub(r'\\\\', body)):
        try:
            v, _ = json.JSONDecoder().raw_decode(b, lo)
            if isinstance(v, dict):
                return v
        except ValueError:
            pass
    hi = body.rfind('}')
    if hi > lo:
        try:
            v = json.loads(body[lo:hi + 1])
            return v if isinstance(v, dict) else None
        except ValueError:
            return None
    return None


def _task(prompt):
    try:
        t, _ = json.JSONDecoder().raw_decode(str(prompt or '').lstrip())
        return t if isinstance(t, dict) else {}
    except ValueError:
        return {}


def offer_problem(task, value):
    import lab_investigations as I
    if not isinstance(value, dict):
        return None
    route = value.get('route')
    route = route.strip().lower() if isinstance(route, str) else ''
    request = value.get('request') if isinstance(value.get('request'), dict) else {}
    tools = task.get('tools') or {}
    if route in ('instrument', 'native'):
        inst = tools.get('instruments')
        skills = inst.get('skills') if isinstance(inst, dict) else None
        skills = set(skills) if isinstance(skills, dict) else None
        skill = request.get('skill') or request.get('tool')
        if skills is not None and skill and skill not in skills:
            return 'not_offered', "there is no instrument %r on this call's menu; valid: %s" % (
                str(skill)[:40], ', '.join(sorted(skills))[:400])
        files = request.get('files')
        files = [files] if isinstance(files, str) else [f for f in files if isinstance(f, str)] if isinstance(files, list) else []
        listed = set(re.findall(r'artifacts/[A-Za-z0-9_./+-]+', json.dumps(
            [tools, task.get('available_inputs'), task.get('results_so_far')], default=str)))
        off = [f for f in files if f.startswith('artifacts/') and f not in listed]
        if off:
            return 'not_offered', "these files are not on the Lab's list for this call: %s; listed: %s" % (
                ', '.join(f[:80] for f in off), ', '.join(sorted(listed)[:8])[:500])
    if route == 'experiment':
        lab_exps = set(getattr(I, 'EXPERIMENTS', ()))
        ex = tools.get('experiments')
        menu = set(ex) if isinstance(ex, dict) else {e if isinstance(e, str) else str((e or {}).get('experiment') or (e or {}).get('name')) for e in ex} if isinstance(ex, list) else None
        name = request.get('experiment')
        valid = sorted((menu & lab_exps) if menu is not None else lab_exps)
        if name not in lab_exps or (menu is not None and name not in menu):
            what = 'no experiment is named under "experiment"' if not name else 'there is no experiment %r' % str(name)[:40]
            return 'not_offered', '%s; valid: %s; shape: {"route": "experiment", "request": {"experiment": "<one of ' \
                                  'those>", "parameters": {...}, "shots": <n>}}' % (what, ', '.join(valid))
    return None


def wrapper_verdict(prompt, reply, value):
    """('', '') or the first wrapper rule the proposal fails."""
    if strict_object(reply) is None:
        return 'unreadable', ('the reply was not one strict JSON object (a trailing comma, an unclosed bracket or text '
                              'inside the object); return exactly one JSON object')
    import lab_investigations as I
    try:
        value = I._coerce_route(value)
    except Exception:
        pass
    return offer_problem(_task(prompt), value) or ('', '')


def witness(reply, prompt, investigation, note=None, planned=None):
    """(value, rule, words) for the worm: the Lab's parse and rules (verdict), then the wrapper rules."""
    try:
        value = lab._json_object(reply)
    except lab.ModelJSONError:
        return None, 'unreadable', 'the reply was not one JSON object'
    why, detail = verdict(value, investigation, note, planned)
    if not why:
        why, detail = wrapper_verdict(prompt, reply, value)
    return value, why, detail


# --- the whole worm (LAB_PLANNER_TRIAL=c1-worm): the learned planner with its wrapper -------------------------------
# Craft    history(): what this investigation already completed, which outputs it can consume and by which paths,
#          which steps are not inputs, the lookups the repeat gate has seen on this subject, instrument runs left, and
#          for an opening question how often it was closed lately. Read from the Lab's own stores, before proposing.
# Lessons  worked examples in planner-worm/lessons.json beside the notebook (drawn by the worm's loop from the Lab's
#          own older refusals and what was run instead); none is sent when the file is absent.
# Witness  explain(): the Lab's own rules, as for c1.
# Compass  a refused proposal is asked again ONCE, with the Lab's own words for the refusal (the re-plan tail);
#          refused again, or no answer, and the current model plans exactly as without the switch.

WORM = {'c1-worm'}
LESSONS = os.path.join(lab.ROOT, 'planner-worm', 'lessons.json')
HISTORY_CAP = 2600


def _keys(step):
    paths = []
    for row in (step.get('output_index') or [])[:6]:
        if isinstance(row, dict):
            keys = [str(k) for k in (row.get('keys') or [])][:8]
            paths.append({'path': row.get('path') or [], 'keys': keys})
    return paths


def history(investigation, note=None):
    """Craft: the planner's history tool, as text for the end of its prompt ('' when there is nothing to tell)."""
    import lab_investigations as I
    steps = investigation.get('steps') or []
    lines = []
    done = [s for s in steps if s.get('state') == 'completed']
    if done:
        ops = [{'id': s.get('id'), 'route': s.get('route'),
                'request': I._short(s.get('executed_request') or s.get('request') or {}, 50)} for s in done[-10:]]
        lines.append('- Completed in this investigation; each is done and its output is yours, so never return one of '
                     'these operations again: ' + json.dumps(ops, ensure_ascii=False)[:1100])
        usable = [{'step': s.get('id'), 'fields': _keys(s)} for s in done if s.get('output_file')][-5:]
        if usable:
            lines.append('- Outputs you can consume inside a request as {"step": id, "path": [...]}; only these paths '
                         'exist: ' + json.dumps(usable, ensure_ascii=False)[:700])
    not_inputs = [s.get('id') for s in steps if s.get('state') != 'completed' or not s.get('output_file')]
    if not_inputs:
        lines.append('- Not inputs (failed, refused or without output): ' + ', '.join(map(str, not_inputs[-10:])))
    try:
        import lab_repeats
        words = lab_repeats._words(investigation.get('question'))
        seen = []
        for r in reversed(lab_repeats._recent()):
            theirs = set(r.get('words') or lab_repeats._words(r.get('question')))
            if r.get('lookup') and words and len(words & theirs) / len(words) >= 0.4:
                key = lab_repeats.canonical_lookup(r['lookup'])[:110]
                if key not in seen:
                    seen.append(key)
            if len(seen) >= 8:
                break
        if seen:
            lines.append('- Lookups already run in the last %d days on this subject; the repeat gate refuses the same '
                         'lookup, or the same question on the same source, again: %s'
                         % (lab_repeats.REPEAT_DAYS, json.dumps(seen, ensure_ascii=False)[:900]))
    except Exception:
        pass
    try:
        import lab_instruments
        left = lab_instruments.runs_left()
        lines.append('- Instrument runs left today: %d%s' % (left, ' (routes instrument and native will not run today)'
                                                             if left <= 0 else ''))
    except Exception:
        pass
    if not steps:
        try:
            data = lab._load(I._path('investigations.json'), {'investigations': []})
            earlier = I._same_question(str(investigation.get('question') or ''), None, data)
            if earlier:
                lines.append('- This question was investigated and closed %d time(s) in the last %d days (tools used: %s). '
                             'Return a different "question", or keep it and add "narrower" naming a tool, source, '
                             'accession or cohort not used.' % (len(earlier), I.REPEAT_WINDOW_DAYS,
                                                                ', '.join(I._tools_used(earlier[0])) or 'none'))
        except Exception:
            pass
    if not lines:
        return ''
    return ('\nYOUR HISTORY TOOL, read from the Lab\'s records just now (before you choose):\n' + '\n'.join(lines))[:HISTORY_CAP]


def lessons():
    """Lessons: the worked examples as one block for the end of the system prompt ('' without the file)."""
    try:
        with open(LESSONS) as f:
            rows = json.load(f).get('examples') or []
    except (OSError, ValueError, AttributeError):
        return ''
    out = []
    for k, r in enumerate(rows[:4], 1):
        out.append('%d. %s\n   Refused: %s\n   Run instead: %s' % (k, str(r.get('situation') or '')[:400],
                                                                   str(r.get('refused') or '')[:300],
                                                                   str(r.get('instead') or '')[:300]))
    if not out:
        return ''
    return ('\n\nWorked examples from this Lab (a proposal it refused, and the one it ran instead):\n' + '\n'.join(out))


def retry_tail(value, why, detail):
    """Compass: the Lab's own re-plan words for a refused proposal, for the one retry."""
    import lab_investigations as I
    route, request = (value.get('route'), value.get('request')) if isinstance(value, dict) else (None, None)
    lines = ['', 'YOUR LAST PROPOSAL WAS NOT RUN (%s): %s' % (why, str(detail or '')[:700])]
    if route is not None:
        lines.append('Do NOT return this operation again: ' + json.dumps(
            {'route': route, 'request': I._short(request if isinstance(request, dict) else {}, 120)},
            ensure_ascii=False, default=str)[:500])
    lines.append('Return ONE different operation now, as JSON beginning with "route", or finish.')
    return '\n'.join(lines)


def begin_turn():
    _STATE['turn'], _STATE['calls'] = uuid.uuid4().hex[:12], []


def end_turn(out=None, exc=None):
    """One row per investigation turn that asked the trial: what was acted on and what came of it. Never raises."""
    try:
        calls, _STATE['calls'] = _STATE['calls'], []
        if not calls:
            return
        row = {'at': lab.now_iso(), 'kind': 'turn', 'turn': _STATE['turn'], 'calls': len(calls),
               'accepted': sum(1 for c in calls if c.get('accepted')),
               'acted_on': calls[-1]['proposer'] if calls[-1].get('accepted') else 'live'}
        if exc is not None:
            row['outcome'] = 'error:' + type(exc).__name__
        elif not isinstance(out, dict):
            row['outcome'] = 'nothing'
        else:
            row['outcome'] = str(out.get('kind') or 'other')[:40]
            if out.get('kind') == 'investigation_step':
                row['state'] = str(out.get('state') or '')[:40]
                row['repeat'] = bool(out.get('repeat_within') or out.get('reused_from') or out.get('same_receipt_as'))
                row['new_output'] = out.get('state') == 'completed' and not row['repeat']
            elif out.get('kind') == 'investigation_review':
                a = out.get('answers_question')
                row['answered'] = (out.get('evidence_status') == 'answered' or a is True
                                   or str(a or '').strip().lower().startswith('yes'))
        _write(row)
    except Exception:
        pass

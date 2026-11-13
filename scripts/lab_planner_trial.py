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
current model is asked exactly as it is without the switch. Everything after the planner (the doors, their repeat and
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
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import chemistry_lab as lab

KNOWN = {'c1': 'lab-c1'}                # switch value -> the alias the trial server answers to
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
    started = time.time()
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
    try:
        value = lab._json_object(reply)
    except lab.ModelJSONError:
        call['reason'] = 'unreadable'
        return call
    try:
        why = check(value, investigation, note, planned)
    except Exception as exc:
        why = 'check_' + type(exc).__name__
    call['reason'] = why or 'ok'
    if not why:
        call.update(accepted=True, value=value)
        _write(call)
    return call


def fell_back(call, live_seconds):
    """The current model answered this call instead: logged with its seconds."""
    if not call or call.get('accepted'):
        return
    call['live_s'] = round(float(live_seconds), 2)
    _write(call)


def check(value, investigation, note=None, planned=None):
    """'' when the Lab's own rules would act on this proposal as it stands; otherwise the first rule it fails."""
    import lab_investigations as I
    from lab_tool_calls import normalize_request, execution_request
    value = I._coerce_route(value)
    if not isinstance(value, dict) or not isinstance(value.get('route'), str) or not value['route'].strip():
        return 'no_route'
    route, request, _authored, _inferred = I._route_request(value)
    if route not in I.ROUTES:
        return 'no_route'
    if not isinstance(request, dict):
        return 'no_route'
    steps = investigation.get('steps') or []
    data = lab._load(I._path('investigations.json'), {'investigations': []})
    if not steps:
        question = str(value.get('question') or '').strip() or str(investigation.get('question') or '')
        earlier = I._same_question(question, None, data) if question else []
        if earlier:
            narrower = I._valid_narrower(value.get('narrower'), earlier)
            if not narrower or I._same_question(question, narrower, data):
                return 'repeat_question'
    if route == 'finish':
        return '' if any(I._new_output(s) for s in steps) else 'empty_finish'
    request = I.bind_inputs(normalize_request(route, request), steps)
    if I.FRONTIER_PLANS and isinstance(planned, dict):
        plan_ref = {k: planned.get(k) for k in ('line_id', 'plan_id', 'step_index', 'step_number', 'route', 'tool')}
        if not I.plan_step_matches(plan_ref, route, request):
            return 'not_planned_step'
    if I._offer_problem(route, request):
        return 'not_offered'
    if isinstance(note, dict) and note.get('proposed_route') == route and note.get('proposed_request') == I._short(request):
        return 'repeat_within'
    resolved = execution_request(route, I.resolve(request, steps))
    sha = hashlib.sha256(json.dumps([route, resolved], sort_keys=True).encode()).hexdigest()
    own = [s for s in steps if s.get('request_sha256') == sha and s.get('state') == 'completed']
    if own and route != 'schema':
        return 'repeat_within'
    if route not in ('schema', 'read_output') and any(
            s.get('request_sha256') == sha and s.get('state') == 'completed' and s.get('output_file')
            for inv in data.get('investigations') or [] for s in inv.get('steps') or []):
        return 'repeat_done'
    field = {'source': 'source_query', 'plugin': 'plugin_query', 'instrument': 'instrument_query',
             'native': 'instrument_query'}.get(route)
    if field:
        import lab_repeats
        question = str(value.get('step_question') or investigation.get('question') or '')
        if lab_repeats.repeat(lab._inquiry({'question': question, field: resolved, 'browse_lane': 'protein'})):
            return 'repeat_lookup'
    return ''


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

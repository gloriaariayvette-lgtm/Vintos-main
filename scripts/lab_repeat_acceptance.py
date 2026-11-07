#!/usr/bin/env python3
"""Live acceptance check for the closed-question redaction (lab_closed_redaction), once the Lab is on again.

Reads only: model-calls.jsonl (and .1), investigations.json, repeat-fix-log.jsonl. Writes nothing. Prints counts,
rates and a verdict - never prompt, question or reply text.

Planner calls are the investigation planner's (caller "_plan", task carrying results_so_far). The fix window starts at
the first repeat-fix-log row with the flag on (or --since) and ends at the first later row with it off; the baseline
is the --baseline-n planner calls just before it. The first --n planner calls of the fix window are judged (default 50).

  repeat_refusals   the next planner call (within 15 minutes) is the Lab saying "this question was investigated ...
                    closed": the call's proposal was refused as a repeat. Same definition in both windows.
  closed_reproposals the reply proposes a question that the Lab's own rule (_alike) matches to an investigation closed
                    in the 14 days before the call and closed before it (closed_at), and gives no narrower
  wellformed        the reply is a plan (a JSON object with a route) or a finish
  new_outputs       completed, non-repeat investigation steps made in the window, per planner call

PASS needs all of (over the first --n fix-window calls):
  repeat_refusals    <= 10% of planner calls
  closed_reproposals <= 5% of planner calls
  wellformed         not more than 5 points below the baseline
  new_outputs/call   at least 90% of the baseline's
Exit status: 0 PASS, 1 FAIL, 2 not enough calls yet (nothing judged).

    python3 lab_repeat_acceptance.py [--n 50] [--baseline-n 500] [--since ISO] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import chemistry_lab as lab           # noqa: E402
import lab_closed_redaction as R      # noqa: E402

REFUSAL_MARK = 'this question was investigated'
REFUSAL_GAP_SECONDS = 15 * 60
THRESHOLDS = {'repeat_refusals_max_pct': 10.0, 'closed_reproposals_max_pct': 5.0,
              'wellformed_max_drop_points': 5.0, 'new_outputs_min_ratio': 0.9}


def _when(s):
    try:
        t = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except ValueError:
        return None
    return t.replace(tzinfo=None) - (t.utcoffset() or timedelta(0)) if t.tzinfo else t


def _rows(path):
    try:
        with open(path, errors='replace') as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def planner_calls(path=None):
    """[(at, reply_object_or_None, refused_next)] in time order. Text is read here and dropped at once."""
    path = path or lab.MODEL_CALLS
    out = []
    for p in (path + '.1', path):
        for r in _rows(p):
            if r.get('caller') != '_plan' or '"results_so_far"' not in str(r.get('prompt') or ''):
                continue
            at = _when(r.get('at'))
            if at is None:
                continue
            tail = str(r.get('prompt') or '')[-4000:]
            out.append({'at': at, 'reply': _reply(r.get('reply')), 'marks_refusal': REFUSAL_MARK in tail})
    out.sort(key=lambda c: c['at'])
    for a, b in zip(out, out[1:]):
        a['refused'] = b['marks_refusal'] and (b['at'] - a['at']).total_seconds() <= REFUSAL_GAP_SECONDS
    if out:
        out[-1]['refused'] = False
    for c in out:
        del c['marks_refusal']
    return out


def _reply(text):
    m = re.search(r'\{.*\}', str(text or ''), re.S)
    try:
        d = json.loads(m.group(0)) if m else None
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def shape(reply):
    if not isinstance(reply, dict):
        return 'malformed'
    if str(reply.get('route') or '').strip().lower() in ('finish', 'done', 'stop'):
        return 'finish'
    return 'plan' if reply.get('route') else 'malformed'


def fix_window(log=None, since=None):
    """(start, end) of the calls made with the fix on; end None while it stays on."""
    rows = [(_when(r.get('at')), r.get('enabled')) for p in ((log,) if log else (R.LOG + '.1', R.LOG)) for r in _rows(p)]
    rows = sorted(((at, on) for at, on in rows if at is not None), key=lambda r: r[0])
    start = _when(since) if since else next((at for at, on in rows if on is True), None)
    if start is None:
        return None, None
    end = next((at for at, on in rows if at > start and on is False), None)
    return start, end


def closed_index(data):
    """[(closed_at, opened_at, words, tokens)] of closed, un-narrowed investigations."""
    import lab_investigations as LI
    out = []
    for inv in (data or {}).get('investigations', []):
        if inv.get('state') not in LI.CLOSED or inv.get('narrower'):
            continue
        q = inv.get('base_question') or inv.get('question')
        words = LI._qwords(q)
        opened = _when(inv.get('opened_at'))
        if not words or opened is None:
            continue
        closed = _when(inv.get('closed_at')) or _when(inv.get('last_step_at')) or opened
        out.append((closed, opened, words, LI._tokens(q)))
    return out


def reproposes_closed(reply, at, index):
    import lab_investigations as LI
    if not isinstance(reply, dict) or reply.get('narrower'):
        return False
    q = str(reply.get('question') or '')
    if len(q) < R.MIN_CHARS:
        return False
    since = at - timedelta(days=LI.REPEAT_WINDOW_DAYS)
    live = [(w, t) for closed, opened, w, t in index if closed <= at and opened >= since]
    return R.is_closed(q, live)


def new_outputs(data, start, end):
    n = 0
    for inv in (data or {}).get('investigations', []):
        for s in inv.get('steps') or []:
            at = _when(s.get('at')) if isinstance(s, dict) else None
            if at is None or at < start or (end is not None and at >= end):
                continue
            if s.get('state') == 'completed' and not s.get('repeat_within') and not s.get('reused_from') \
                    and not s.get('same_receipt_as'):
                n += 1
    return n


def measure(calls, index, data):
    n = len(calls)
    if not n:
        return {'planner_calls': 0}
    refused = sum(1 for c in calls if c.get('refused'))
    loops = sum(1 for c in calls if reproposes_closed(c['reply'], c['at'], index))
    shapes = [shape(c['reply']) for c in calls]
    good = sum(1 for s in shapes if s != 'malformed')
    end = calls[-1]['at'] + timedelta(seconds=1)
    made = new_outputs(data, calls[0]['at'], end)
    return {'planner_calls': n, 'first_at': calls[0]['at'].isoformat()[:19], 'last_at': calls[-1]['at'].isoformat()[:19],
            'repeat_refusals': refused, 'repeat_refusals_pct': round(100.0 * refused / n, 1),
            'closed_reproposals': loops, 'closed_reproposals_pct': round(100.0 * loops / n, 1),
            'wellformed': good, 'wellformed_pct': round(100.0 * good / n, 1),
            'finish': shapes.count('finish'),
            'new_outputs': made, 'new_outputs_per_call': round(made / n, 3)}


def verdict(base, fix, n_needed):
    if fix.get('planner_calls', 0) < n_needed:
        return 'NOT ENOUGH CALLS', {}
    t = THRESHOLDS
    checks = {
        'repeat_refusals <= %g%%' % t['repeat_refusals_max_pct']: fix['repeat_refusals_pct'] <= t['repeat_refusals_max_pct'],
        'closed_reproposals <= %g%%' % t['closed_reproposals_max_pct']:
            fix['closed_reproposals_pct'] <= t['closed_reproposals_max_pct'],
    }
    if base.get('planner_calls'):
        checks['wellformed >= baseline - %g points' % t['wellformed_max_drop_points']] = \
            fix['wellformed_pct'] >= base['wellformed_pct'] - t['wellformed_max_drop_points']
        checks['new_outputs/call >= %g x baseline' % t['new_outputs_min_ratio']] = \
            fix['new_outputs_per_call'] >= t['new_outputs_min_ratio'] * base['new_outputs_per_call']
    else:
        checks['baseline present'] = False
    return ('PASS' if all(checks.values()) else 'FAIL'), checks


def run(n=50, baseline_n=500, since=None, calls_path=None, log=None, investigations=None):
    calls = planner_calls(calls_path)
    data = lab._load(investigations or os.path.join(lab.ROOT, 'investigations.json'), {'investigations': []})
    start, end = fix_window(log, since)
    if start is None:
        return {'verdict': 'NOT ENOUGH CALLS', 'why': 'no planner call has been made with the fix on yet',
                'thresholds': THRESHOLDS}
    before = [c for c in calls if c['at'] < start][-baseline_n:]
    after = [c for c in calls if c['at'] >= start and (end is None or c['at'] < end)][:n]
    index = closed_index(data)
    base, fix = measure(before, index, data), measure(after, index, data)
    v, checks = verdict(base, fix, n)
    return {'verdict': v, 'fix_on_since': start.isoformat()[:19], 'fix_off_at': end.isoformat()[:19] if end else None,
            'judged_calls': n, 'baseline': base, 'with_fix': fix, 'checks': checks, 'thresholds': THRESHOLDS,
            'closed_at_estimated': sum(1 for i in data.get('investigations', []) if i.get('closed_at_estimated'))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--n', type=int, default=50)
    ap.add_argument('--baseline-n', type=int, default=500)
    ap.add_argument('--since')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    out = run(a.n, a.baseline_n, a.since)
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        print('Lab repeat fix, live acceptance: %s' % out['verdict'])
        if out.get('why'):
            print('  ' + out['why'])
        for name in ('baseline', 'with_fix'):
            m = out.get(name)
            if m:
                print('  %-9s %s' % (name, ', '.join('%s=%s' % kv for kv in m.items())))
        for k, ok in (out.get('checks') or {}).items():
            print('  [%s] %s' % ('pass' if ok else 'FAIL', k))
    return {'PASS': 0, 'FAIL': 1}.get(out['verdict'], 2)


if __name__ == '__main__':
    sys.exit(main())

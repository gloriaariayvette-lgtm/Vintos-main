#!/usr/bin/env python3
"""LAB_PLANNER_TRIAL report: the trial window against the days before it. Reads only; writes nothing.

  python3 scripts/lab_planner_trial_report.py [--since ISO] [--until ISO] [--before-days 3] [--root DIR] [--json]

The trial window runs from --since (default: the first row of planner-trial.jsonl) to --until (default: now). The
baseline is the --before-days days (default 3) before the trial began. Both windows are read from notebook.jsonl the
same way, and shown per hour since they differ in length:

  steps            investigation_step rows (an operation proposed and carried out, whatever came of it)
  repeat refusals  investigation_refused_repeat rows, re-plans for a repeat (repeat_within, refused_repeat,
                   repeat_question), and steps handed an earlier output instead of a new one
  real results     completed steps with a new output (not a repeat, not an earlier receipt), answered reviews,
                   findings

From planner-trial.jsonl (the trial window only): how often the trial model's step was used or fell back to the
current model and why, whether its server was down, and latency: the trial model's seconds per call, the current
model's seconds when it answered, and the seconds the trial added per planner call (the current model's own time,
measured on the calls it answered, is what a call cost before).
"""
import argparse
import json
import os
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

REPEAT_WHY = ('repeat_within', 'refused_repeat', 'repeat_question')


def _ts(text):
    t = datetime.fromisoformat(str(text).replace('Z', '+00:00'))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def answered(review):
    """A review that found its question answered: evidence_status "answered", or answers_question "yes: ..."."""
    a = review.get('answers_question')
    return review.get('evidence_status') == 'answered' or a is True or str(a or '').strip().lower().startswith('yes')


def _rows(path):
    try:
        with open(path, errors='replace') as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except FileNotFoundError:
        return


def window_counts(notebook, start, end):
    """{(start,end) -> counts} for each window, in one pass over the notebook."""
    out = {w: Counter() for w in zip(start, end)}
    try:
        f = open(notebook, errors='replace')
    except FileNotFoundError:
        return out
    with f:
        for line in f:
            if '"investigation_' not in line:
                continue
            try:
                r = json.loads(line)
                at = _ts(r.get('at'))
            except (ValueError, TypeError):
                continue
            for (a, b), c in out.items():
                if not (a <= at < b):
                    continue
                kind, why = r.get('kind'), r.get('why')
                if kind == 'investigation_step':
                    c['steps'] += 1
                    handed = bool(r.get('repeat_within') or r.get('reused_from') or r.get('same_receipt_as'))
                    if handed:
                        c['repeat_handed_back'] += 1
                    elif r.get('state') == 'completed':
                        c['new_outputs'] += 1
                    c['state_' + str(r.get('state'))] += 1
                elif kind == 'investigation_refused_repeat':
                    c['refused_repeat'] += 1
                elif kind == 'investigation_replan':
                    c['replans'] += 1
                    if why in REPEAT_WHY:
                        c['replan_for_repeat'] += 1
                elif kind == 'investigation_review':
                    c['reviews'] += 1
                    if answered(r):
                        c['answered_reviews'] += 1
                elif kind == 'investigation_finding':
                    c['findings'] += 1
    for c in out.values():
        c['repeat_refusals'] = c['refused_repeat'] + c['replan_for_repeat'] + c['repeat_handed_back']
        c['real_results'] = c['new_outputs'] + c['answered_reviews'] + c['findings']
    return out


def trial_summary(log, start, end):
    calls = [r for r in _rows(log) if r.get('kind') == 'call' and start <= _ts(r['at']) < end]
    turns = [r for r in _rows(log) if r.get('kind') == 'turn' and start <= _ts(r['at']) < end]
    s = {'calls': len(calls), 'accepted': sum(1 for r in calls if r.get('accepted')),
         'reasons': dict(Counter(r.get('reason') for r in calls if not r.get('accepted')).most_common()),
         'turns': len(turns)}
    s['fell_back'] = s['calls'] - s['accepted']
    s['fallback_rate'] = round(s['fell_back'] / s['calls'], 3) if calls else None
    s['trial_down_calls'] = sum(1 for r in calls if r.get('reason') == 'trial_down')
    asked = [r['trial_s'] for r in calls if r.get('reason') != 'trial_down' and isinstance(r.get('trial_s'), (int, float))]
    live = [r['live_s'] for r in calls if isinstance(r.get('live_s'), (int, float))]
    total = [float(r.get('trial_s') or 0) + float(r.get('live_s') or 0) for r in calls]
    s['latency'] = {'trial_s_median': round(statistics.median(asked), 1) if asked else None,
                    'trial_s_mean': round(statistics.mean(asked), 1) if asked else None,
                    'live_s_median': round(statistics.median(live), 1) if live else None,
                    'per_call_s_mean': round(statistics.mean(total), 1) if total else None}
    s['latency']['added_s_per_call'] = (round(s['latency']['per_call_s_mean'] - s['latency']['live_s_median'], 1)
                                        if total and live else None)
    by = {}
    for who in sorted({r.get('acted_on') for r in turns}):
        mine = [r for r in turns if r.get('acted_on') == who]
        by[who] = {'turns': len(mine), 'steps': sum(1 for r in mine if r.get('outcome') == 'investigation_step'),
                   'new_outputs': sum(1 for r in mine if r.get('new_output')),
                   'repeats_handed_back': sum(1 for r in mine if r.get('repeat')),
                   'answered_reviews': sum(1 for r in mine if r.get('answered')),
                   'errors': sum(1 for r in mine if str(r.get('outcome', '')).startswith('error:'))}
    s['outcomes_by_proposer'] = by
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', default=os.path.join(os.environ.get('SPARK_WORKSPACE', os.path.expanduser('~/.vintos/workspace')),
                                                   'memory', 'chemistry-lab'))
    ap.add_argument('--since'), ap.add_argument('--until')
    ap.add_argument('--before-days', type=float, default=3.0)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    log = os.path.join(a.root, 'planner-trial.jsonl')
    first = next((r for r in _rows(log) if r.get('at')), None)
    if not a.since and not first:
        print('no trial rows in %s: is LAB_PLANNER_TRIAL=c1 set and has the Lab planned since?' % log)
        return 1
    start = _ts(a.since) if a.since else _ts(first['at'])
    end = _ts(a.until) if a.until else datetime.now(timezone.utc)
    base = start - timedelta(days=a.before_days)
    counts = window_counts(os.path.join(a.root, 'notebook.jsonl'), (base, start), (start, end))
    before, during = counts[(base, start)], counts[(start, end)]
    hours = {'before': (start - base).total_seconds() / 3600, 'trial': max(1e-9, (end - start).total_seconds() / 3600)}
    trial = trial_summary(log, start, end)
    keys = ('steps', 'repeat_refusals', 'refused_repeat', 'replan_for_repeat', 'repeat_handed_back', 'real_results',
            'new_outputs', 'answered_reviews', 'findings', 'replans', 'reviews')
    report = {'trial_window': [start.isoformat(), end.isoformat()], 'baseline_window': [base.isoformat(), start.isoformat()],
              'hours': {k: round(v, 1) for k, v in hours.items()},
              'per_hour': {k: {'before': round(before[k] / hours['before'], 2), 'trial': round(during[k] / hours['trial'], 2)}
                           for k in keys},
              'totals': {k: {'before': before[k], 'trial': during[k]} for k in keys},
              'repeat_refusals_per_step': {
                  'before': round(before['repeat_refusals'] / before['steps'], 3) if before['steps'] else None,
                  'trial': round(during['repeat_refusals'] / during['steps'], 3) if during['steps'] else None},
              'real_results_per_step': {
                  'before': round(before['real_results'] / before['steps'], 3) if before['steps'] else None,
                  'trial': round(during['real_results'] / during['steps'], 3) if during['steps'] else None},
              'trial': trial}
    if a.json:
        print(json.dumps(report, indent=1))
        return 0
    print('Lab planner trial (%s)  %s -> %s  (%.1f h)  vs the %.1f h before'
          % (','.join(sorted({r.get('proposer') for r in _rows(log) if r.get('proposer')})) or 'c1',
             start.isoformat()[:16], end.isoformat()[:16], hours['trial'], hours['before']))
    print('%-22s %12s %12s' % ('per hour', 'before', 'trial'))
    for k in keys:
        print('%-22s %12.2f %12.2f' % (k, report['per_hour'][k]['before'], report['per_hour'][k]['trial']))
    for k in ('repeat_refusals_per_step', 'real_results_per_step'):
        print('%-22s %12s %12s' % (k.replace('_per_step', '/step'), report[k]['before'], report[k]['trial']))
    print('planner calls %d: trial step used %d, fell back %d (rate %s); server down on %d'
          % (trial['calls'], trial['accepted'], trial['fell_back'], trial['fallback_rate'], trial['trial_down_calls']))
    print('fallback reasons: %s' % (', '.join('%s %d' % kv for kv in trial['reasons'].items()) or 'none'))
    lat = trial['latency']
    print('latency s: trial median %s mean %s | current model median %s | per call mean %s | added per call %s'
          % (lat['trial_s_median'], lat['trial_s_mean'], lat['live_s_median'], lat['per_call_s_mean'], lat['added_s_per_call']))
    for who, o in trial['outcomes_by_proposer'].items():
        print('acted on %-5s turns %d  steps %d  new outputs %d  repeats handed back %d  answered reviews %d  errors %d'
              % (who, o['turns'], o['steps'], o['new_outputs'], o['repeats_handed_back'], o['answered_reviews'], o['errors']))
    return 0


if __name__ == '__main__':
    sys.exit(main())

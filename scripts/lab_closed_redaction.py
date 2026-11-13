#!/usr/bin/env python3
"""Closed questions are not shown to the investigation planner by their words.

Measured 5-6 November on recorded planner calls (worm-jobs labjobs/lab_loop.py): the planner re-proposed questions
already investigated and closed because their TEXT was in its prompt - in the refusal note's earlier attempts, in
build_on's question and next_question, in results_so_far, and in the task's own question and line. Over half of all
planner calls were then refused as repeats. Withholding only the refusal note's copy did nothing (54 of 60 replays
still looped): the same texts reach it through the other fields. The rule below, replayed on 60 held-out calls,
cut closed re-proposals from 58 to 0 with well-formed plans, topicality and progressive proposals held.

The rule, keyed on closure: a string in one of the listed fields that the Lab's own repeat rule (_alike, the same
one that refuses a closed question) matches to a closed investigation's question - closed within the repeat window,
and closed before this call (closed_at) - is replaced by a placeholder. In the task's own question, its line and its
prediction it keeps its content words, so the planner still knows the topic without the wording to copy. Open
questions and everything else are shown unchanged.

Rollback without a redeploy: `python3 lab_closed_redaction.py off` (and `on`, `status`). The flag is read at each
planner call; missing means on. Each planner call appends one row of counts to repeat-fix-log.jsonl (never text),
which lab_repeat_acceptance.py reads to tell the calls made with the fix from those made without.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import chemistry_lab as lab   # noqa: E402

FLAG = os.path.join(lab.ROOT, 'repeat-fix.json')
LOG = os.path.join(lab.ROOT, 'repeat-fix-log.jsonl')
LOG_CAP = 16 * 1024 * 1024
KEY = 'redact_closed_questions'

PLACEHOLDER = '(a question already investigated and closed; not shown)'
# the learned rule, as replayed (worm-jobs runs/lab-loop/final.json): "*" spans dots, as in fnmatch
PATHS = ('$.replanning.*', '$.build_on[].question', '$.build_on[].next_question', '$.results_so_far*')
TOPIC_PATHS = ('$.question', '$.line_context.*', '$.prediction')
MIN_CHARS = 9          # shorter strings are never a question (ids, states, routes)
_TOPIC = re.compile(r'[a-z0-9]+')
_TOPIC_STOP = set('the and for with from that this what which does are was were has have into its their than then about '
                  'how why when where who whom whose can could would should will may might any all not but use using used '
                  'between within across over under per via each other more most less such these those there here'.split())


def is_placeholder(text):
    """True for PLACEHOLDER or its topic-words form: a withheld question, which is never itself a question. The planner
    has echoed it back as one (12 November, I-f3a37ef61f5b: it opened, and its finding was a raw UniProt sequence)."""
    return str(text or '').strip().startswith(PLACEHOLDER[:-1])


def enabled():
    """The flag: on unless repeat-fix.json says {"redact_closed_questions": false}."""
    try:
        with open(FLAG) as f:
            value = json.load(f)
    except (OSError, ValueError):
        return True
    return not (isinstance(value, dict) and value.get(KEY) is False)


def set_enabled(on):
    lab._atomic(FLAG, {KEY: bool(on), 'set_at': lab.now_iso()})
    return enabled()


def topic_words(text):
    return sorted({t for t in _TOPIC.findall(str(text or '').lower()) if len(t) >= 3 and t not in _TOPIC_STOP})


def _topic(text):
    return PLACEHOLDER[:-1] + '; topic words: ' + ' '.join(topic_words(text)) + ')'


def closed_questions(data, now=None):
    """(content words, identifier tokens) of every question closed in the repeat window and before now: exactly the
    investigations lab_investigations._same_question would hold a plain proposal against."""
    import lab_investigations as LI
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=LI.REPEAT_WINDOW_DAYS)).isoformat()[:19]
    at = now.isoformat()[:19]
    out = []
    for inv in (data or {}).get('investigations', []):
        if inv.get('state') not in LI.CLOSED or str(inv.get('opened_at') or '')[:19] < since:
            continue
        if inv.get('narrower'):       # a narrowed variant holds only proposals with the same narrowing
            continue
        if inv.get('closed_at') and str(inv['closed_at'])[:19] > at:
            continue
        q = inv.get('base_question') or inv.get('question')
        words = LI._qwords(q)
        if words:
            out.append((words, LI._tokens(q)))
    return out


def is_closed(text, closed):
    """lab_investigations._alike against the closed list, with each closed question's words computed once."""
    import lab_investigations as LI
    if not (isinstance(text, str) and len(text) >= MIN_CHARS) or not closed:
        return False
    wa = LI._qwords(text)
    if not wa:
        return False
    ta = LI._tokens(text)
    for wb, tb in closed:
        if len(wa & wb) / len(wa | wb) >= LI.SAME_QUESTION and not (ta and tb and ta.isdisjoint(tb)):
            return True
    return False


def redact(task, closed, own_narrowed=False):
    """(task, fields replaced). task is the planner's input object; it is not changed in place. own_narrowed: the
    investigation was admitted as a narrower variant, so its own question and prediction are shown as they are."""
    n = [0]

    def rewrite(value, path):
        if any(fnmatch.fnmatchcase(path, pat) for pat in TOPIC_PATHS):
            if own_narrowed and path in ('$.question', '$.prediction'):
                return value
            if is_closed(value, closed):
                n[0] += 1
                return _topic(value)
            return value
        if any(fnmatch.fnmatchcase(path, pat) for pat in PATHS) and is_closed(value, closed):
            n[0] += 1
            return PLACEHOLDER
        return value

    def walk(value, path):
        if isinstance(value, dict):
            return {k: walk(v, path + '.' + str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v, path + '[]') for v in value]
        if isinstance(value, str):
            return rewrite(value, path)
        return value

    return walk(task, '$'), n[0]


def for_planner(task, investigation, data=None, now=None):
    """The planner's task with closed questions withheld when the flag is on; one counts-only row is logged per call.
    Never raises: a fault here shows the task unchanged, as before the fix."""
    on = enabled()
    n, error = 0, None
    if on:
        try:
            if data is None:
                data = lab._load(os.path.join(lab.ROOT, 'investigations.json'), {'investigations': []})
            own_narrowed = bool((investigation or {}).get('narrower'))
            task, n = redact(task, closed_questions(data, now), own_narrowed=own_narrowed)
        except Exception as exc:   # noqa: BLE001
            error = type(exc).__name__
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) >= LOG_CAP:
            os.replace(LOG, LOG + '.1')
        row = {'at': lab.now_iso(), 'enabled': on, 'fields_redacted': n,
               'investigation': (investigation or {}).get('id')}
        if error:
            row['error'] = error
        lab._append(LOG, row)
    except Exception:   # noqa: BLE001
        pass
    return task


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else 'status'
    if cmd == 'on':
        set_enabled(True)
    elif cmd == 'off':
        set_enabled(False)
    elif cmd != 'status':
        print('usage: lab_closed_redaction.py on|off|status')
        return 2
    print('closed-question redaction: %s (%s)' % ('ON' if enabled() else 'OFF', FLAG))
    return 0


if __name__ == '__main__':
    sys.exit(main())

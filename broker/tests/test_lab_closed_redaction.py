#!/usr/bin/env python3
"""Closed questions withheld from the investigation planner (7 November). The planner kept re-proposing questions
already investigated and closed because their words were in its prompt - the refusal note, build_on, results_so_far,
its own question and line; replayed, withholding them all cut re-proposals 58 -> 0 of 60. Here: the rule rewrites
exactly the closed texts in those fields, keyed on closure (window, closed_at, narrowing); the flag turns it off with
no redeploy; closed_at is stamped on closing; the acceptance check judges by counts and never prints text. Scratch
stores only; every sender is blocked by the shared sandbox and the planner is a stub."""
import io
import json
import os
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_closed_redaction as R
import lab_repeat_acceptance as A

C = sandbox.C
PHAGE = 'Which bacteriophage genomes carry a reverse transcriptase beside a CRISPR array or Cas genes?'
PENDRIN = 'Does the pendrin SLC26A4 region 653-729 bind chloride in the structure O43511?'
OPEN_Q = 'How stable is the folded lysozyme core under a temperature titration?'


def iso(minutes=0):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def closed(question, iid='I-old', **extra):
    return dict({'id': iid, 'opened_at': iso(-600), 'state': 'unanswered', 'question': question,
                 'closed_at': iso(-300), 'closed_reason': 'reviews found the outputs did not answer it', 'steps': [],
                 'last_review': {'missing_evidence': 'specific phage genomes', 'next_question': PENDRIN}}, **extra)


def task(question=OPEN_Q):
    return {'replanning': {'why_not_run': 'this question was investigated 1 time(s) in the last 14 days and closed',
                           'earlier': [{'investigation': 'I-old', 'question': PHAGE, 'next_question': PENDRIN,
                                        'missing_evidence': 'specific phage genomes'}]},
            'question': question, 'prediction': 'some do',
            'line_context': {'id': 'L-1', 'question': PHAGE, 'recent_steps': [{'question': PENDRIN, 'result': 'none'}]},
            'build_on': [{'question': PHAGE, 'next_question': PENDRIN, 'result': 'two hits'},
                         {'question': OPEN_Q, 'next_question': OPEN_Q, 'result': 'stable'}],
            'results_so_far': [{'id': 'S-1', 'question': PHAGE, 'summary': 'two genomes'}],
            'context': PHAGE, 'tools': {'source': PHAGE}}


class Base(unittest.TestCase):
    def setUp(self):
        for p in (R.FLAG, R.LOG, I._path('investigations.json')):
            self.assertTrue(Path(p).is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        for p in (R.FLAG, R.LOG):
            if os.path.exists(p):
                os.remove(p)
        C._atomic(I._path('investigations.json'), {'investigations': [closed(PHAGE), closed(PENDRIN, 'I-old2')]})

    def tearDown(self):
        sandbox.SEND.assert_not_called()

    def data(self):
        return C._load(I._path('investigations.json'), {})


class Rule(Base):
    def test_every_listed_field_loses_a_closed_questions_words_and_open_ones_stay(self):
        got, n = R.redact(task(), R.closed_questions(self.data()))
        e = got['replanning']['earlier'][0]
        self.assertEqual((e['question'], e['next_question']), (R.PLACEHOLDER, R.PLACEHOLDER))
        self.assertEqual(e['missing_evidence'], 'specific phage genomes')     # not a closed question: shown
        self.assertEqual(got['build_on'][0]['question'], R.PLACEHOLDER)
        self.assertEqual(got['build_on'][0]['next_question'], R.PLACEHOLDER)
        self.assertEqual(got['build_on'][1], task()['build_on'][1])         # open question: unchanged
        self.assertEqual(got['results_so_far'][0]['question'], R.PLACEHOLDER)
        self.assertTrue(got['line_context']['question'].startswith(R.PLACEHOLDER[:-1] + '; topic words: '))
        self.assertIn('bacteriophage', got['line_context']['question'])     # the topic stays, the wording goes
        self.assertNotIn(PHAGE, json.dumps({k: v for k, v in got.items() if k not in ('context', 'tools')}))
        self.assertNotIn(PENDRIN, json.dumps({k: v for k, v in got.items() if k not in ('context', 'tools')}))
        self.assertEqual(got['question'], OPEN_Q)
        self.assertEqual((got['context'], got['tools']), (PHAGE, {'source': PHAGE}))   # not fields the rule names
        self.assertEqual(n, 7)

    def test_the_tasks_own_closed_question_keeps_its_topic_words(self):
        got, _ = R.redact(task(PHAGE), R.closed_questions(self.data()))
        self.assertNotEqual(got['question'], PHAGE)
        self.assertIn('crispr', got['question'])

    def test_closure_is_keyed_on_window_closed_at_and_narrowing(self):
        later = closed(PHAGE, closed_at=iso(+60))                       # closed after this call: not yet closed
        old = closed(PHAGE, opened_at=iso(-60 * 24 * 20))                # outside the 14-day window
        narrow = closed(PHAGE, narrower={'changes': 'tool', 'what': 'fold_read'})
        still_open = dict(closed(PHAGE), state='open')
        for inv in (later, old, narrow, still_open):
            self.assertEqual(R.redact(task(), R.closed_questions({'investigations': [inv]}))[1], 0, inv)
        legacy = closed(PHAGE)
        legacy.pop('closed_at')                                         # closed before closed_at existed: closed
        self.assertGreater(R.redact(task(), R.closed_questions({'investigations': [legacy]}))[1], 0)

    def test_same_wording_about_another_accession_is_another_question(self):
        one = 'Does the structure O43511 bind chloride in its transmembrane region?'
        index = R.closed_questions({'investigations': [closed(one)]})
        other = one.replace('O43511', 'Q8ECH7')
        got, _ = R.redact({'build_on': [{'question': other}, {'question': one}]}, index)
        self.assertEqual([b['question'] for b in got['build_on']], [other, R.PLACEHOLDER])

    def test_a_narrowed_investigations_own_question_is_shown(self):
        got, _ = R.redact(task(PHAGE + ' Narrowed: a new tool, fold_read.'), R.closed_questions(self.data()),
                          own_narrowed=True)
        self.assertIn('Narrowed', got['question'])


class Planner(Base):
    def prompt(self, note=True):
        inv = {'id': 'I-new', 'opened_at': iso(), 'state': 'open', 'question': '', 'prediction': '', 'plan': [],
               'steps': [], 'line_context': {'id': 'L-1', 'question': PHAGE}}
        ask = Mock(return_value=json.dumps({'route': 'source', 'request': {'source': 'pubchem'}, 'question': OPEN_Q}))
        with patch('lab_findings.for_planner', return_value=[{'question': PHAGE, 'next_question': PENDRIN}]):
            earlier = I._same_question(PHAGE, None, self.data())
            I._plan(inv, 'turn context', ask, note=I._question_note(earlier) if note else None)
        return ask.call_args[0][1]

    def test_the_planner_prompt_carries_no_closed_question_and_the_log_only_counts(self):
        prompt = self.prompt()
        self.assertNotIn(PHAGE, prompt)
        self.assertNotIn(PENDRIN, prompt)
        self.assertIn(R.PLACEHOLDER, prompt)
        self.assertIn('this question was investigated', prompt)          # the refusal itself is still said
        rows = [json.loads(l) for l in Path(R.LOG).read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), {'at', 'enabled', 'fields_redacted', 'investigation'})
        self.assertTrue(rows[0]['enabled'] and rows[0]['fields_redacted'] > 0)

    def test_rollback_flag_shows_the_prompt_as_before_with_no_redeploy(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(R.main(['off']), 0)
        self.assertIn('OFF', out.getvalue())
        self.assertFalse(R.enabled())
        prompt = self.prompt()
        self.assertIn(PHAGE, prompt)
        self.assertNotIn(R.PLACEHOLDER, prompt)
        self.assertFalse(json.loads(Path(R.LOG).read_text().splitlines()[-1])['enabled'])
        with redirect_stdout(io.StringIO()):
            R.main(['on'])
        self.assertTrue(R.enabled())
        self.assertNotIn(PHAGE, self.prompt())

    def test_a_fault_in_the_rule_shows_the_task_unchanged(self):
        with patch.object(R, 'closed_questions', side_effect=RuntimeError('boom')):
            self.assertIn(PHAGE, self.prompt())
        self.assertEqual(json.loads(Path(R.LOG).read_text().splitlines()[-1])['error'], 'RuntimeError')


class ClosedAt(Base):
    def test_closing_stamps_closed_at_legacy_rows_are_estimated_and_reopening_clears_it(self):
        legacy = {'id': 'I-a', 'opened_at': '2026-11-01T00:00:00+00:00', 'state': 'stalled', 'question': PHAGE,
                  'steps': [{'id': 'S-1', 'at': '2026-11-01T02:00:00+00:00'}]}
        data = {'investigations': [legacy, {'id': 'I-b', 'opened_at': iso(), 'state': 'open', 'steps': []}]}
        I._save(data)
        got = self.data()
        self.assertEqual(got['investigations'][0]['closed_at'], '2026-11-01T02:00:00+00:00')
        self.assertTrue(got['investigations'][0]['closed_at_estimated'])
        self.assertNotIn('closed_at', got['investigations'][1])
        got['investigations'][1]['state'] = 'answered'
        I._save(got)
        got = self.data()
        b = got['investigations'][1]
        self.assertGreaterEqual(b['closed_at'], got['closed_at_since'])
        self.assertNotIn('closed_at_estimated', b)
        got['investigations'][1]['state'] = 'open'
        I._save(got)
        self.assertNotIn('closed_at', self.data()['investigations'][1])


class Acceptance(Base):
    def write(self, calls, log):
        path = os.path.join(str(sandbox.SCRATCH), 'acc-calls.jsonl')
        logp = os.path.join(str(sandbox.SCRATCH), 'acc-log.jsonl')
        with open(path, 'w') as f:
            for c in calls:
                f.write(json.dumps(c) + '\n')
        with open(logp, 'w') as f:
            for r in log:
                f.write(json.dumps(r) + '\n')
        return path, logp

    def call(self, minutes, question, refusal_note=False, route='source'):
        prompt = json.dumps({'question': '', 'results_so_far': []}) + (
            '\nYOUR LAST PROPOSAL WAS NOT RUN: this question was investigated 1 time(s)' if refusal_note else '')
        return {'at': iso(minutes), 'caller': '_plan', 'prompt': prompt,
                'reply': json.dumps({'route': route, 'request': {}, 'question': question})}

    def judge(self, before, after, n=10):
        calls = [self.call(-200 + i, q, r) for i, (q, r) in enumerate(before)] + \
                [self.call(i + 1, q, r) for i, (q, r) in enumerate(after)]
        path, logp = self.write(calls, [{'at': iso(0), 'enabled': True, 'fields_redacted': 3}])
        return A.run(n=n, baseline_n=500, calls_path=path, log=logp, investigations=I._path('investigations.json'))

    def test_pass_when_repeats_stop_and_fail_when_they_go_on_and_no_text_is_printed(self):
        looping = [(PHAGE, False), (PHAGE, True)] * 10                  # every other call refused, all closed
        good = self.judge(looping, [(OPEN_Q, False)] * 10)
        self.assertEqual(good['verdict'], 'PASS', good)
        self.assertEqual((good['baseline']['closed_reproposals'], good['with_fix']['closed_reproposals']), (20, 0))
        bad = self.judge(looping, looping[:10])
        self.assertEqual(bad['verdict'], 'FAIL')
        self.assertFalse(bad['checks']['closed_reproposals <= 5%'])
        self.assertNotIn('bacteriophage', json.dumps(bad).lower())

    def test_not_enough_calls_judges_nothing(self):
        self.assertEqual(self.judge([(PHAGE, False)] * 5, [(OPEN_Q, False)] * 3)['verdict'], 'NOT ENOUGH CALLS')
        path, logp = self.write([], [])
        out = A.run(calls_path=path, log=logp, investigations=I._path('investigations.json'))
        self.assertEqual(out['verdict'], 'NOT ENOUGH CALLS')

    def test_the_check_writes_nothing(self):
        def listing():
            return {os.path.join(d, f): os.path.getmtime(os.path.join(d, f))
                    for d, _, fs in os.walk(str(sandbox.SCRATCH)) for f in fs if not f.startswith('acc-')}
        self.judge([(PHAGE, False)] * 5, [(OPEN_Q, False)] * 10)
        before = listing()
        self.judge([(PHAGE, False)] * 5, [(OPEN_Q, False)] * 10)
        self.assertEqual(listing(), before)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""LAB_PLANNER_TRIAL (13 November): with the switch on, a trial model proposes the investigation step first and the
Lab's own rules check it before anything is acted on; a step that fails them, or a trial model that does not answer,
is the current model's turn exactly as before. Removing the switch is the rollback. Scratch stores only; every sender
is blocked by the shared sandbox, and the trial model is a stub."""
import json
import os
from pathlib import Path
import unittest
import urllib.error
from unittest.mock import Mock, patch
import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_lines
import lab_planner_trial as T

C = sandbox.C


def choice(route, request, step_question='Measure the sourced protein', question='Is the RT beside the array?'):
    return json.dumps({'route': route, 'request': request, 'step_question': step_question, 'why': 'next comparison',
                       'question': question, 'prediction': 'It is within 2 kb.', 'plan': ['inputs', 'measure']})


FIRST = choice('source', {'source': 'pubchem', 'name': 'fixture'})
OTHER = choice('source', {'source': 'pubchem', 'name': 'another'})
OUT = {'receipt': {'source': 'pubchem', 'records': [{'SMILES': 'CCO'}]}}


def trial_rows(kind=None):
    if not os.path.exists(T.LOG):
        return []
    with open(T.LOG) as f:
        rows = [json.loads(l) for l in f if l.strip()]
    return [r for r in rows if kind is None or r.get('kind') == kind]


def switch(value):
    """vintos.env beside the scratch workspace, as Gloria's sits beside hers."""
    path = Path(T._env_path())
    if value is None:
        if path.exists():
            path.unlink()
        return
    path.write_text('SOME_OTHER_KEY=1\nLAB_PLANNER_TRIAL=%s\n' % value)


class Base(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.ROOT).is_relative_to(sandbox.SCRATCH))
        self.assertTrue(Path(T._env_path()).is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        C._atomic(I._path('investigations.json'), {'investigations': []})
        C._atomic(I._path('source-throttle.json'), {})
        for path in (T.LOG, C.MODEL_CALLS):
            if os.path.exists(path):
                os.remove(path)
        os.environ.pop('LAB_PLANNER_TRIAL', None)
        T._STATE.update(down_until=0.0, turn=None, calls=[])
        switch(None)
        self.lines = patch.multiple(lab_lines, pick=Mock(return_value=None), opened_by=Mock(return_value=None),
                                    record_step=Mock(), advance_plan=Mock(return_value='stale'))
        self.lines.start()

    def tearDown(self):
        self.lines.stop()
        switch(None)
        sandbox.SEND.assert_not_called()


class Switch(Base):
    def test_off_the_current_model_plans_alone_and_nothing_is_written(self):
        trial = Mock(return_value=FIRST)
        ask = Mock(return_value=FIRST)
        with patch.object(T, '_ask', trial):
            row = I.turn('', ask=ask, execute=Mock(return_value=OUT))
        self.assertEqual(row['state'], 'completed')
        self.assertEqual(ask.call_count, 1)
        trial.assert_not_called()
        self.assertEqual(trial_rows(), [])

    def test_an_unknown_value_is_off(self):
        switch('c9')
        trial = Mock(return_value=FIRST)
        with patch.object(T, '_ask', trial):
            I.turn('', ask=Mock(return_value=FIRST), execute=Mock(return_value=OUT))
        trial.assert_not_called()
        self.assertEqual(trial_rows(), [])

    def test_on_the_trial_step_is_carried_out_and_the_current_model_is_not_asked(self):
        switch('c1')
        ask = Mock(return_value=OTHER)
        execute = Mock(return_value=OUT)
        with patch.object(T, '_ask', Mock(return_value=FIRST)) as trial:
            row = I.turn('', ask=ask, execute=execute)
        self.assertEqual(trial.call_count, 1)
        ask.assert_not_called()
        self.assertEqual(execute.call_args.args[1]['name'], 'fixture')     # the trial's request, not the other
        self.assertEqual(row['state'], 'completed')
        call, = trial_rows('call')
        self.assertEqual((call['proposer'], call['accepted'], call['reason']), ('c1', True, 'ok'))
        turn, = trial_rows('turn')
        self.assertEqual((turn['acted_on'], turn['outcome'], turn['new_output'], turn['repeat']),
                         ('c1', 'investigation_step', True, False))
        # the trial call is in model-calls.jsonl as every Lab model call is, marked as the trial's
        with open(C.MODEL_CALLS) as f:
            recorded = [json.loads(l) for l in f]
        self.assertEqual([(r['caller'], r.get('trial'), r['model']) for r in recorded], [('_plan', 'c1', 'lab-c1')])

    def test_the_environment_switch_works_too_and_removing_the_line_is_the_rollback(self):
        os.environ['LAB_PLANNER_TRIAL'] = 'c1'
        try:
            with patch.object(T, '_ask', Mock(return_value=FIRST)) as trial:
                I.turn('', ask=Mock(return_value=FIRST), execute=Mock(return_value=OUT))
            self.assertEqual(trial.call_count, 1)
        finally:
            os.environ.pop('LAB_PLANNER_TRIAL', None)
        switch('c1')
        switch(None)                       # the line removed: the next planner call is the current model's alone
        C._atomic(I._path('investigations.json'), {'investigations': []})
        ask = Mock(return_value=FIRST)
        with patch.object(T, '_ask', Mock(return_value=FIRST)) as trial:
            I.turn('', ask=ask, execute=Mock(return_value=OUT))
        trial.assert_not_called()
        self.assertEqual(ask.call_count, 1)


class Fallback(Base):
    def setUp(self):
        super().setUp()
        switch('c1')

    def turn_with(self, trial_reply, live_reply=OTHER, execute=None):
        ask = Mock(return_value=live_reply)
        execute = execute or Mock(return_value=OUT)
        with patch.object(T, '_ask', Mock(return_value=trial_reply) if isinstance(trial_reply, str)
                          else Mock(side_effect=trial_reply)) as trial:
            row = I.turn('', ask=ask, execute=execute)
        return row, ask, trial, execute

    def test_a_repeat_of_its_own_completed_step_falls_back_to_the_current_model(self):
        switch(None)
        I.turn('', ask=Mock(return_value=FIRST), execute=Mock(return_value=OUT))   # the investigation's first step
        switch('c1')
        row, ask, trial, execute = self.turn_with(FIRST)
        self.assertEqual(trial.call_count, 1)
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(execute.call_args.args[1]['name'], 'another')
        call, = trial_rows('call')
        self.assertEqual((call['accepted'], call['reason']), (False, 'repeat_within'))
        self.assertIn('live_s', call)
        turn, = trial_rows('turn')
        self.assertEqual(turn['acted_on'], 'live')

    def test_an_unreadable_reply_falls_back(self):
        row, ask, trial, _ = self.turn_with('I think we should look at the protein.')
        self.assertEqual(ask.call_count, 1)
        call, = trial_rows('call')
        self.assertEqual(call['reason'], 'unreadable')

    def test_an_experiment_the_lab_does_not_have_falls_back(self):
        row, ask, trial, _ = self.turn_with(choice('experiment', {'experiment': 'teleport'}))
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(trial_rows('call')[0]['reason'], 'not_offered')

    def test_no_route_falls_back(self):
        row, ask, trial, _ = self.turn_with(json.dumps({'question': 'Is the RT beside the array?'}))
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(trial_rows('call')[0]['reason'], 'no_route')

    def test_a_finish_with_nothing_to_review_falls_back(self):
        row, ask, trial, _ = self.turn_with(choice('finish', {}))
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(trial_rows('call')[0]['reason'], 'empty_finish')

    def test_an_opening_question_closed_before_falls_back(self):
        closed = {'id': 'I-closed', 'state': 'answered', 'opened_at': C.now_iso(), 'question': 'Is the RT beside the array?',
                  'steps': []}
        C._atomic(I._path('investigations.json'), {'investigations': [closed]})
        ask = Mock(return_value=choice('source', {'source': 'pubchem', 'name': 'fixture'},
                                       question='Which ligands does the curated record of pendrin list?'))
        with patch.object(T, '_ask', Mock(return_value=FIRST)):
            I.turn('', ask=ask, execute=Mock(return_value=OUT))
        self.assertIn('repeat_question', [r['reason'] for r in trial_rows('call')])
        self.assertGreaterEqual(ask.call_count, 1)


class FailOpen(Base):
    def setUp(self):
        super().setUp()
        switch('c1')

    def test_a_trial_server_that_is_down_leaves_the_current_model_planning(self):
        ask = Mock(return_value=FIRST)
        with patch.object(T, '_ask', Mock(side_effect=ConnectionRefusedError(61, 'refused'))) as trial:
            row = I.turn('', ask=ask, execute=Mock(return_value=OUT))
            self.assertEqual(row['state'], 'completed')
            self.assertEqual(ask.call_count, 1)
            call, = trial_rows('call')
            self.assertEqual((call['reason'], call['error']), ('trial_down', 'ConnectionRefusedError'))
            # not asked again while it is down: the next turn costs nothing
            I.turn('', ask=Mock(return_value=OTHER), execute=Mock(return_value=OUT))
            self.assertEqual(trial.call_count, 1)
        self.assertEqual([r['reason'] for r in trial_rows('call')], ['trial_down', 'trial_down'])

    def test_a_timeout_is_down_too(self):
        ask = Mock(return_value=FIRST)
        with patch.object(T, '_ask', Mock(side_effect=TimeoutError('timed out'))):
            I.turn('', ask=ask, execute=Mock(return_value=OUT))
        self.assertEqual(ask.call_count, 1)
        self.assertGreater(T._STATE['down_until'], 0)

    def test_an_error_answer_falls_back_without_marking_it_down(self):
        err = urllib.error.HTTPError('http://127.0.0.1:8866/v1/chat/completions', 400, 'too long', {}, None)
        with patch.object(T, '_ask', Mock(side_effect=err)):
            I.turn('', ask=Mock(return_value=FIRST), execute=Mock(return_value=OUT))
        call, = trial_rows('call')
        self.assertEqual((call['reason'], call['error']), ('trial_error', 'HTTP400'))
        self.assertEqual(T._STATE['down_until'], 0.0)

    def test_a_url_off_this_machine_is_never_called(self):
        os.environ['LAB_PLANNER_TRIAL_URL'] = 'http://example.org:8866/v1/chat/completions'
        try:
            with self.assertRaises(ValueError):
                T._url()
            ask = Mock(return_value=FIRST)
            I.turn('', ask=ask, execute=Mock(return_value=OUT))   # the real _ask: refused before any socket
            self.assertEqual(ask.call_count, 1)
            self.assertEqual(trial_rows('call')[0]['reason'], 'trial_down')
        finally:
            os.environ.pop('LAB_PLANNER_TRIAL_URL', None)

    def test_a_check_that_breaks_falls_back(self):
        with patch.object(T, '_ask', Mock(return_value=FIRST)), patch.object(T, 'check', Mock(side_effect=KeyError('x'))):
            ask = Mock(return_value=FIRST)
            I.turn('', ask=ask, execute=Mock(return_value=OUT))
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(trial_rows('call')[0]['reason'], 'check_KeyError')


class Logging(Base):
    def test_rows_carry_counts_and_names_only(self):
        switch('c1')
        with patch.object(T, '_ask', Mock(return_value=FIRST)):
            I.turn('', ask=Mock(return_value=OTHER), execute=Mock(return_value=OUT))
        with open(T.LOG) as f:
            text = f.read()
        for private in ('fixture', 'RT beside', 'SMILES', 'pubchem', 'prediction'):
            self.assertNotIn(private, text)
        allowed = {'at', 'kind', 'turn', 'proposer', 'replan', 'accepted', 'trial_s', 'reason', 'error', 'live_s',
                   'calls', 'acted_on', 'outcome', 'state', 'repeat', 'new_output', 'answered'}
        for row in trial_rows():
            self.assertLessEqual(set(row), allowed)

    def test_a_turn_that_fails_is_logged_with_its_error(self):
        switch('c1')
        with patch.object(T, '_ask', Mock(return_value='prose')):
            with self.assertRaises(Exception):
                I.turn('', ask=Mock(return_value='still prose'), execute=Mock(return_value=OUT))
        turn = trial_rows('turn')[-1]
        self.assertTrue(turn['outcome'].startswith('error:'))
        self.assertEqual(turn['acted_on'], 'live')


class Report(unittest.TestCase):
    def test_the_report_compares_the_trial_with_the_days_before_it(self):
        import lab_planner_trial_report as R
        root = Path(sandbox.SCRATCH) / 'report-root'
        root.mkdir(exist_ok=True)
        nb = [{'at': '2026-11-10T12:00:00+00:00', 'kind': 'investigation_step', 'state': 'completed'},
              {'at': '2026-11-10T13:00:00+00:00', 'kind': 'investigation_step', 'state': 'completed', 'reused_from': 'S-1',
               'repeat_within': True},
              {'at': '2026-11-11T13:00:00+00:00', 'kind': 'investigation_refused_repeat'},
              {'at': '2026-11-12T13:00:00+00:00', 'kind': 'investigation_replan', 'why': 'refused_repeat'},
              {'at': '2026-11-12T14:00:00+00:00', 'kind': 'investigation_replan', 'why': 'source_cooling'},
              {'at': '2026-11-13T01:00:00+00:00', 'kind': 'investigation_step', 'state': 'completed'},
              {'at': '2026-11-13T02:00:00+00:00', 'kind': 'investigation_review', 'answers_question': True},
              {'at': '2026-11-09T00:00:00+00:00', 'kind': 'investigation_step', 'state': 'completed'}]   # too early
        (root / 'notebook.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in nb))
        log = [{'at': '2026-11-13T00:00:00+00:00', 'kind': 'call', 'proposer': 'c1', 'accepted': True, 'trial_s': 10.0},
               {'at': '2026-11-13T00:30:00+00:00', 'kind': 'call', 'proposer': 'c1', 'accepted': False,
                'reason': 'repeat_lookup', 'trial_s': 10.0, 'live_s': 20.0},
               {'at': '2026-11-13T00:40:00+00:00', 'kind': 'call', 'proposer': 'c1', 'accepted': False,
                'reason': 'trial_down', 'trial_s': 0.0, 'live_s': 20.0},
               {'at': '2026-11-13T01:00:00+00:00', 'kind': 'turn', 'acted_on': 'c1', 'outcome': 'investigation_step',
                'new_output': True, 'repeat': False}]
        (root / 'planner-trial.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in log))
        start, end = R._ts('2026-11-13T00:00:00+00:00'), R._ts('2026-11-13T03:00:00+00:00')
        counts = R.window_counts(str(root / 'notebook.jsonl'), (start - R.timedelta(days=3), start), (start, end))
        before, during = counts[(start - R.timedelta(days=3), start)], counts[(start, end)]
        self.assertEqual((before['steps'], before['repeat_refusals'], before['real_results']), (2, 3, 1))
        self.assertEqual((during['steps'], during['repeat_refusals'], during['real_results']), (1, 0, 2))
        trial = R.trial_summary(str(root / 'planner-trial.jsonl'), start, end)
        self.assertEqual((trial['calls'], trial['accepted'], trial['fallback_rate'], trial['trial_down_calls']),
                         (3, 1, 0.667, 1))
        self.assertEqual(trial['reasons'], {'repeat_lookup': 1, 'trial_down': 1})
        # per call: 10, 30, 20 -> mean 20; the current model alone took 20: nothing added on average
        self.assertEqual((trial['latency']['trial_s_median'], trial['latency']['added_s_per_call']), (10.0, 0.0))
        self.assertEqual(trial['outcomes_by_proposer']['c1']['new_outputs'], 1)
        self.assertEqual(R.main(['--root', str(root), '--until', '2026-11-13T03:00:00+00:00', '--json']), 0)


if __name__ == '__main__':
    unittest.main()

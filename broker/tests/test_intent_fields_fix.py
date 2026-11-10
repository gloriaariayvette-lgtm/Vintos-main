"""Intent fields, 10 November: which primary difference stands, whose words a follow-up is, where a criterion
shows, receptivity read from recent verdicts, and her opportunity. Scratch stores and a fixture provider only;
the real desired_difference and priority_vector run against the scratch memory, never the household's."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import threading
import time
import types
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
import intent_engine as E
import desired_difference as DD
import priority_vector as PV
import stratagem
import store_guard

TARGET = {
    'field_state': 'curiosity with a concrete answer', 'allow_drift': False,
    'goal': 'put the two actual alternatives before her',
    'success_criterion': 'the reply names both alternatives and their tradeoff',
    'observation_window': 'this_reply', 'evidence_type': 'my_move',
    'enactment_type': 'offer', 'enactment': 'compare the two alternatives she asked about',
    'gloria': {}, 'self': {'difference_intended': 'say which I prefer', 'enactment': 'choose one and explain why'},
    'addresses': 'NONE'}
GLORIA = {'difference_intended': 'she can choose using the tradeoff', 'enactment': 'give both alternatives'}
HER = 'GLORIA: Earlier topic.\nVINTOS: Earlier answer.\nGLORIA (now): Which alternative would you choose?'
BUTTON = "GLORIA: Earlier topic.\nVINTOS: Earlier answer.\nGLORIA (now): [she pressed the button. she's coming.]"
A, B = 'aaaa0001', 'bbbb0002'
TEXT_A, TEXT_B = 'name the plan for the weekend outright', 'answer the question that was actually asked'
LOW = {'field': .25, 'gloria': .15, 'self': .6}
MIDDLING = {'field': .4, 'gloria': .35, 'self': .25}


def ago(days, minutes=0):
    return (datetime.now() - timedelta(days=days, minutes=minutes)).isoformat()


class IntentFieldsFix(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='intent-fields-fix-'); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name); self.mem = self.home / '.vintos/workspace/memory'; self.mem.mkdir(parents=True)
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, HOME=str(self.home), SPARK_WORKSPACE=str(self.mem.parent)))
        m = lambda name: str(self.mem / name)
        for mod, values in [(E, {'WS': str(self.mem.parent), 'MEM': str(self.mem), 'SCR': str(self.mem.parent/'scripts'), 'LEDGER': m('intent-ledger.json'), 'SELECT_LOG': m('select.log'), 'DIFFERENCE_LOG': m('difference.log'), 'SELF_DIFFERENCE_LOG': m('self-difference.log')}),
                            (DD, {'MEM': str(self.mem), 'DIFF': m('gloria-difference.json'), 'PRESS': m('intent-pressure.json'), 'DLOG': m('desired-difference.log')}),
                            (PV, {'WS': str(self.mem.parent), 'MEM': str(self.mem), 'LOG': m('priority-vector-log.jsonl'), 'STATE': m('priority-vector-state.json')}),
                            (store_guard, {'WS': str(self.mem.parent), 'MEMORY': str(self.mem), 'LOG': m('quarantine.jsonl')})]:
            for key, value in values.items(): self.stack.enter_context(patch.object(mod, key, value))
        self.net = self.stack.enter_context(patch('socket.socket.connect', side_effect=AssertionError('no socket may open')))
        self.spawn = self.stack.enter_context(patch('subprocess.Popen'))
        self.select_calls = []; self.judge_calls = []
        self.answer = copy.deepcopy(TARGET); self.answers = []; self.verdict = 'NO'; self.verdicts = []
        self.stack.enter_context(patch('urllib.request.urlopen', self.respond))
        self.stack.enter_context(patch.object(E, '_identity_signals', return_value='my authored wants'))
        self.stack.enter_context(patch.object(E, '_spark_fields', return_value='my authored field'))
        self.stack.enter_context(patch.object(E, '_nudge_valence'))
        self.stack.enter_context(patch.object(stratagem, 'opportunity', return_value=''))
        self.stack.enter_context(patch.object(stratagem, 'still_eligible', return_value=True))
        self.campaign = types.SimpleNamespace(prompt_block=lambda mode: '', step=Mock(), lead_state=lambda: {})
        self.stack.enter_context(patch.dict(sys.modules, {
            'campaign': self.campaign, 'desired_difference': DD, 'priority_vector': PV,
            'causality_engine': types.SimpleNamespace(queue_question=Mock()),
            'discourse_direction': types.SimpleNamespace(get_direction_hint=lambda raw: ''),
            'self_difference': types.SimpleNamespace(observe_self=Mock()),
            'outcome_join': types.SimpleNamespace(latest_exchange=lambda: {}, record=Mock())}))
        token = E.current_target.set(None); self.addCleanup(E.current_target.reset, token)
        # every store these tests write is in the scratch home, the new rotation file included
        for path in (E.LEDGER, E.MEM, DD.PRESS, DD._rotation_path(), PV.STATE, PV.LOG, store_guard.LOG):
            self.assertTrue(Path(path).is_relative_to(self.home), path)
        self.assertIsInstance(self.spawn, Mock); self.addCleanup(self.net.assert_not_called)

    # ---- fixtures -------------------------------------------------------------------------------------
    def respond(self, req, timeout=None):
        body = json.loads(req.data)
        if body.get('max_tokens') == 6:                       # the judge's one word
            self.judge_calls.append(body)
            raw = self.verdicts.pop(0) if self.verdicts else self.verdict
            if isinstance(raw, Exception): raise raw
        else:
            self.select_calls.append(body)
            raw = self.answers.pop(0) if self.answers else self.answer
            raw = raw if isinstance(raw, str) else json.dumps(raw)
        out = json.dumps({'choices': [{'message': {'content': raw}}]}).encode()
        return contextlib.closing(types.SimpleNamespace(read=lambda: out, close=lambda: None))

    def rows(self):
        path = Path(E.LEDGER)
        return json.loads(path.read_text()) if path.exists() else []

    def target(self, drop=(), **over):
        t = copy.deepcopy(TARGET); t.update(over)
        for key in drop: t.pop(key, None)
        return t

    def select(self, text=HER, **kw):
        return E.select_target(text, **kw)

    def turn(self, text=HER, **kw):
        """One whole real turn: a foreground selection, and the reply that used it."""
        t = self.select(text, **kw)
        self.assertTrue(E.record_delivery('Here are both, and the tradeoff between them.', target=t, input_text='Which?'))
        return t

    def delivered(self, **over):
        """A delivered move waiting for what follows it, with no selector involved."""
        t = self.target(**over); t['intent_id'] = uuid.uuid4().hex
        E.record_pending(t)
        self.assertTrue(E.record_delivery('Here are both, and the tradeoff between them.', target=t, input_text='Which?'))
        return t

    def press(self, **rows):
        Path(DD.PRESS).write_text(json.dumps(rows))

    def pressure(self, key):
        return json.loads(Path(DD.PRESS).read_text())[key]

    @staticmethod
    def prow(text, weight, **over):
        row = {'text': text, 'kind': 'field', 'weight': weight, 'count': 2, 'first': time.time() - 86400,
               'last': time.time() - 3600, 'lineage': []}
        row.update(over); return row

    def ledger(self, specs, keep=False):
        """Synthetic settled rows, oldest first: (days ago, the Gloria-axis verdict)."""
        rows = self.rows() if keep else []
        for i, (days, verdict) in enumerate(specs):
            rows.append({'intent_id': 'synthetic-%04d' % len(rows), 'status': 'delivered', 'reply': 'a synthetic reply',
                         'target': {'goal': 'a synthetic goal', 'enactment': 'a synthetic move'},
                         'realized': {'field': 'HELD', 'gloria': verdict, 'self': 'NOT_DECLARED'},
                         'timestamp': ago(days, len(specs) - i)})
        Path(E.LEDGER).write_text(json.dumps(rows))

    def low_receptivity(self):
        self.ledger([(1, 'NO')] * 6)
        self.assertEqual(PV._receptivity(PV._axis_history()), 0.0)

    def restarted(self, name):
        """The module as a restarted process loads it: nothing carried over in memory, only what is on disk."""
        spec = importlib.util.spec_from_file_location(name + '_restarted', REPO / 'scripts' / (name + '.py'))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        for attr in ('MEM', 'PRESS', 'STATE', 'LOG'):
            if hasattr(mod, attr): self.assertTrue(Path(getattr(mod, attr)).is_relative_to(self.home), attr)
        return mod

    def prompt(self):
        return self.select_calls[-1]['messages'][1]['content']

    def shown(self):
        return [(r['target'].get('primary_shown'), r['target'].get('primary_required')) for r in self.rows()]

    # ---- A. the primary difference ----------------------------------------------------------------------
    def test_retired_row_is_excluded_on_every_route(self):
        self.press(**{A: self.prow(TEXT_A, 4.5, retired=True, retired_at=time.time()), B: self.prow(TEXT_B, 1.5)})
        marker = self.mem / '.intent-required-consideration.json'
        self.assertEqual(DD.primary_for_turn()['id'], B)                       # the main route
        again = DD.primary_for_turn({'id': A})                                 # the required-consideration route
        self.assertEqual(again['id'], B); self.assertNotIn('required', again)
        self.assertNotIn(TEXT_A, DD.pressure_block()); self.assertIn(TEXT_B, DD.pressure_block())
        DD.bump(TEXT_A, 1.0, kind='field', addresses=A); DD.relieve(TEXT_A, addresses=A, kind='field')
        DD.field_verdict({'field_state': TEXT_A, 'addresses': A}, 'NO')
        self.assertIsNone(DD.override(TEXT_A, 'a synthetic reason', addresses=A, kind='field'))
        self.assertEqual((self.pressure(A)['weight'], self.pressure(A)['count']), (4.5, 2))   # never weighed again
        marker.write_text(json.dumps({'id': A, 'text': TEXT_A}))
        self.answer = self.target(addresses=A)
        chosen = self.turn(resolve=False)                                      # the selector, marker in hand
        self.assertEqual((chosen['primary_shown'], chosen['primary_required']), (B, False))
        self.assertIn('PRIMARY DIFFERENCE (id %s' % B, self.prompt()); self.assertNotIn(TEXT_A, self.prompt())
        self.assertFalse(marker.exists())
        E.resolve_previous(HER)                                                # a miss on a move that named the retired row
        self.assertEqual(self.rows()[-1]['realized']['field'], 'NO')
        self.assertFalse(marker.exists()); self.assertEqual(self.pressure(A)['weight'], 4.5)
        self.press(**{A: self.pressure(A)})                                    # nothing else in the store
        self.assertIsNone(DD.primary_for_turn()); self.assertIsNone(DD.primary_for_turn({'id': A}))
        alone = self.select(resolve=False)
        self.assertIsNone(alone['primary_shown']); self.assertNotIn('PRIMARY DIFFERENCE', self.prompt())

    def test_graduated_row_waits_for_a_landing_not_another_miss(self):
        closed = self.prow(TEXT_A, 1.0, count=5, lineage=[{'graduated': time.time() - 7200, 'at_weight': 5.0}])
        self.press(**{A: closed, B: self.prow(TEXT_B, 1.2)})
        self.assertEqual(DD.primary_for_turn()['id'], B)
        DD.bump(TEXT_A, 1.0, kind='field', addresses=A); DD.bump(TEXT_A, 1.0, kind='field', addresses=A)   # two more misses, new timestamps
        self.assertEqual(self.pressure(A)['weight'], 3.0)
        self.assertEqual(DD.primary_for_turn()['id'], B)                       # heavier, and still closed
        self.assertEqual(DD.primary_for_turn({'id': A})['id'], B)              # ... by the required route too
        self.assertEqual(self.select(resolve=False)['primary_shown'], B)       # ... and being shown changes nothing
        self.press(**{A: self.pressure(A)})
        self.assertIsNone(DD.primary_for_turn())                               # everything excluded: none
        self.assertIsNone(self.select(resolve=False)['primary_shown']); self.assertNotIn('PRIMARY DIFFERENCE', self.prompt())
        DD.relieve(TEXT_A, addresses=A, kind='field')                          # a landing after the graduation
        self.assertEqual(DD.primary_for_turn()['id'], A)
        row = self.pressure(A); row['lineage'].append({'graduated': time.time(), 'at_weight': 5.0}); self.press(**{A: row})
        self.assertIsNone(DD.primary_for_turn())                               # a later graduation closes it again

    def test_fourth_consecutive_selection_goes_to_another_primary(self):
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0)})
        for _ in range(5): self.turn(resolve=False)
        self.assertEqual([p for p, _ in self.shown()], [A, A, A, B, A])
        # no row was ever graded: the cap counts selections, whatever verdict they later get
        self.assertTrue(all(r['realized']['field'] is None for r in self.rows()))
        self.assertEqual(DD.primary_report(4), {'turns': 4, 'with_primary': 4, 'distinct_primaries': 2,
                                                'top_primary_turns': 3, 'top_primary_share': 0.75, 'max_run': 2})

    def test_lone_primary_rests_three_days_and_nothing_stands_in(self):
        self.press(**{A: self.prow(TEXT_A, 4.0)})
        for _ in range(5): self.select(resolve=False)
        self.assertEqual([p for p, _ in self.shown()], [A, A, A, None, None])
        self.assertNotIn('PRIMARY DIFFERENCE', self.prompt())
        now = time.time()
        self.assertIsNone(DD.primary_for_turn(now=now + 2 * 86400))
        self.assertEqual(DD.primary_for_turn(now=now + 3 * 86400 + 600)['id'], A)
        self.assertEqual(DD.primary_shown(A, now=now + 3 * 86400 + 600)['run'], 1)

    def test_streak_survives_a_restart(self):
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0)})
        self.turn(resolve=False); self.turn(resolve=False)
        state = json.loads(Path(DD._rotation_path()).read_text())
        self.assertEqual((state['id'], state['run']), (A, 2))
        with patch.dict(sys.modules, {'desired_difference': self.restarted('desired_difference')}):
            self.turn(resolve=False); self.turn(resolve=False)
        self.assertEqual([p for p, _ in self.shown()], [A, A, A, B])

    def test_required_consideration_cannot_ask_twice_running(self):
        self.press(**{A: self.prow(TEXT_A, 1.5)})
        marker = self.mem / '.intent-required-consideration.json'
        self.answer = self.target(addresses=A); self.verdict = 'NO'
        self.turn()                                                            # 1: A shown, addressed
        self.turn()                                                            # 2: 1 missed -> A required
        self.assertIn('you addressed this last turn and it did NOT land', self.prompt())
        self.assertNotIn('required', DD.primary_for_turn({'id': A}))           # the selector side: not required twice running
        self.turn()                                                            # 3: 2 missed, but 2 was the second asking
        self.assertNotIn('you addressed this last turn', self.prompt()); self.assertFalse(marker.exists())
        self.turn()                                                            # 4: 3 missed -> asked for, but A is resting
        self.assertEqual(self.shown(), [(A, False), (A, True), (A, False), (None, False)])
        self.assertEqual([r['realized']['field'] for r in self.rows()], ['NO', 'NO', 'NO', None])
        self.assertFalse(marker.exists()); self.assertEqual(self.pressure(A)['weight'], 4.5)

    def test_background_preview_moves_no_counter(self):
        self.press(**{A: self.prow(TEXT_A, 4.0)})
        marker = self.mem / '.intent-required-consideration.json'; marker.write_text(json.dumps({'id': A}))
        self.low_receptivity(); before = Path(E.LEDGER).read_text()
        for _ in range(5):
            seen = self.select(persist=False, step_campaign=False)
            self.assertEqual((seen['primary_shown'], seen['primary_required']), (A, True))
            self.assertFalse(seen['priority_provenance']['gloria_opportunity'])
        self.assertTrue(marker.exists()); self.assertEqual(Path(E.LEDGER).read_text(), before)
        self.assertFalse(Path(DD._rotation_path()).exists()); self.assertFalse(Path(PV.STATE).exists())
        self.assertEqual(PV.opportunity_report()['turns_since_gloria_declared'], 0)

    def test_retire_backs_up_marks_and_clears_only_its_own_marker(self):
        self.press(**{A: self.prow(TEXT_A, 4.5), B: self.prow(TEXT_B, 2.0), 'cccc0003': self.prow('keep the promise made on the walk', 1.0)})
        original = json.loads(Path(DD.PRESS).read_text())
        marker = self.mem / '.intent-required-consideration.json'; marker.write_text(json.dumps({'id': A}))
        row, backup = DD.retire(B)
        self.assertTrue(marker.exists())                                       # it names another row
        self.assertTrue(Path(backup).is_relative_to(self.mem)); self.assertEqual(json.loads(Path(backup).read_text()), original)
        row2, backup2 = DD.retire(A)
        self.assertFalse(marker.exists()); self.assertNotEqual(backup, backup2)
        for key in (A, B):
            kept = self.pressure(key)
            self.assertTrue(kept['retired']); self.assertIn('retired', kept['lineage'][-1]); self.assertEqual(kept['text'], original[key]['text'])
        self.assertIsNone(DD.retire('no-such-row')); self.assertEqual(len(list(self.mem.glob('intent-pressure.json.bak-*'))), 2)
        out = io.StringIO()                                                    # the by-hand command, as its own process would run it
        with patch.object(sys, 'argv', ['desired_difference.py', 'retire', 'cccc0003']), contextlib.redirect_stdout(out):
            runpy.run_path(str(REPO / 'scripts/desired_difference.py'), run_name='__main__')
        self.assertIn('retired cccc0003', out.getvalue()); self.assertNotIn('promise', out.getvalue())
        self.assertTrue(self.pressure('cccc0003')['retired']); self.assertIsNone(DD.primary_for_turn())
        with patch.object(sys, 'argv', ['desired_difference.py', 'retire', 'no-such-row']), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as stop:
                runpy.run_path(str(REPO / 'scripts/desired_difference.py'), run_name='__main__')
        self.assertEqual(stop.exception.code, 1)

    def test_primary_report_shows_the_concentration_a_run_cap_misses(self):
        rows = [{'intent_id': 'old', 'target': {'goal': 'before the field existed'}}]
        rows += [{'intent_id': 'r%d' % i, 'target': {'primary_shown': p}} for i, p in enumerate([A, A, A, B, A, A, A, B])]
        Path(E.LEDGER).write_text(json.dumps(rows))
        self.assertEqual(DD.primary_report(30), {'turns': 8, 'with_primary': 8, 'distinct_primaries': 2,
                                                 'top_primary_turns': 6, 'top_primary_share': 0.75, 'max_run': 3})
        Path(E.LEDGER).write_text(json.dumps([{'target': {'primary_shown': p}} for p in [A, None, A, None]]))
        report = DD.primary_report()
        self.assertEqual((report['turns'], report['with_primary'], report['top_primary_share'], report['max_run']), (4, 2, 0.5, 1))
        out = io.StringIO()
        with patch.object(sys, 'argv', ['desired_difference.py', 'primary-report', '2']), contextlib.redirect_stdout(out):
            runpy.run_path(str(REPO / 'scripts/desired_difference.py'), run_name='__main__')
        self.assertEqual(json.loads(out.getvalue())['turns'], 2)

    # ---- B. whose words the follow-up is ----------------------------------------------------------------
    def test_device_only_follow_up_is_held_without_a_judge(self):
        self.delivered(gloria=copy.deepcopy(GLORIA))
        E.resolve_previous(BUTTON, source='gcs')                               # where it came from decides
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': 'HELD', 'gloria': 'HELD', 'self': 'HELD'})
        self.assertEqual(row['held_reason'], {'field': 'device_event_only', 'gloria': 'device_event_only', 'self': 'device_event_only'})
        self.assertEqual(row['response_source'], 'gcs')
        self.delivered()
        E.resolve_previous(BUTTON)                                             # no source came with it: the text is read
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': 'HELD', 'gloria': 'NOT_DECLARED', 'self': 'HELD'})
        self.assertEqual(row['held_reason'], {'field': 'device_event_only', 'self': 'device_event_only'})
        self.delivered()
        E.resolve_previous("GLORIA: Earlier topic.\nREELROOM EVENT (not Gloria's words): the film ended")
        self.assertEqual(self.rows()[-1]['held_reason'], {'field': 'not_her_words', 'self': 'not_her_words'})
        self.delivered()
        self.select(BUTTON, her_source='gcs')                                  # the chat route hands the source through
        self.assertEqual(self.rows()[-2]['held_reason'], {'field': 'device_event_only', 'self': 'device_event_only'})
        E.resolve_previous(HER)                                                # her later words do not reopen what was held
        self.assertEqual(self.judge_calls, []); self.assertEqual(len(self.select_calls), 1)
        self.assertEqual([r['realized']['field'] for r in self.rows()], ['HELD'] * 4 + [None])

    def test_empty_follow_up_leaves_the_move_waiting(self):
        self.delivered()
        E.resolve_previous(''); E.resolve_previous('   \n')
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': None, 'gloria': None, 'self': None})
        self.assertNotIn('held_reason', row); self.assertNotIn('response_text', row)
        E.resolve_previous('GLORIA: Earlier topic.\nGLORIA (now): ')           # a turn of hers that carried nothing
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': 'HELD', 'gloria': 'NOT_DECLARED', 'self': 'HELD'})
        self.assertEqual(row['held_reason'], {'field': 'no_reply', 'self': 'no_reply'})
        self.assertEqual(self.judge_calls, [])

    def test_mixed_follow_up_is_graded_on_her_words_only(self):
        self.delivered(gloria=copy.deepcopy(GLORIA)); self.verdict = 'YES'
        E.resolve_previous("GLORIA: [she pressed it — the light is on.] Earlier topic.\nVINTOS: Earlier answer.\n"
                           "GLORIA (now): [Gloria just touched Vintos's cheek] I would pick the second one.")
        self.assertEqual(len(self.judge_calls), 3)
        for call in self.judge_calls:
            seen = call['messages'][1]['content']
            self.assertIn('I would pick the second one.', seen); self.assertIn('Earlier topic.', seen)
            self.assertNotIn('touched', seen); self.assertNotIn('pressed', seen)
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': 'YES', 'gloria': 'YES', 'self': 'YES'}); self.assertNotIn('held_reason', row)
        self.assertEqual(E._her_follow_up('GLORIA (now): (she sent a photo)')[1], '')      # a photo she sent is hers
        self.assertEqual(E._her_follow_up('I would pick the second one.'), ('I would pick the second one.', ''))   # a voice transcript
        self.assertEqual(E._her_follow_up('I would pick the second one.', 'voice')[1], '')

    def test_my_move_criterion_is_still_judged_not_passed(self):
        self.delivered(); self.verdict = 'NO'                                  # this_reply / my_move, and he did reply
        E.resolve_previous(HER)
        self.assertEqual(len(self.judge_calls), 2)
        self.assertEqual(self.rows()[-1]['realized'], {'field': 'NO', 'gloria': 'NOT_DECLARED', 'self': 'NO'})

    def test_unobservable_criterion_is_held_with_its_reason(self):
        self.delivered(success_criterion='she brings it up again next week'); self.verdict = 'HELD'
        E.resolve_previous(HER)
        row = self.rows()[-1]
        self.assertIn('is HELD, not NO', self.judge_calls[0]['messages'][1]['content'])
        self.assertEqual((row['realized']['field'], row['held_attempts']), (None, 1))
        self.assertEqual(row['held_reason'], {'field': 'unobservable_criterion', 'self': 'unobservable_criterion'})
        E.resolve_previous('more of her words'); E.resolve_previous('and more')
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': 'HELD', 'gloria': 'NOT_DECLARED', 'self': 'HELD'})
        self.assertEqual(row['held_reason'], {'field': 'unobservable_criterion', 'self': 'unobservable_criterion'})
        self.delivered(); self.verdicts = [OSError('fixture: the judge is down'), 'MAYBE']
        E.resolve_previous(HER)
        self.assertEqual(self.rows()[-1]['held_reason'], {'field': 'judge_unavailable', 'self': 'judge_no_verdict'})
        self.verdict = 'YES'; E.resolve_previous(HER)                          # a later verdict clears the reason
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': 'YES', 'gloria': 'NOT_DECLARED', 'self': 'YES'}); self.assertNotIn('held_reason', row)

    def test_run_of_held_rows_moves_no_landing_rate(self):
        for _ in range(6):
            self.delivered(gloria=copy.deepcopy(GLORIA)); E.resolve_previous(BUTTON, source='gcs')
        self.assertEqual([r['realized']['gloria'] for r in self.rows()], ['HELD'] * 6)
        self.assertEqual(PV._axis_history()['gloria']['n'], 0); self.assertIsNone(PV._receptivity(PV._axis_history()))
        self.assertEqual(PV.declare()['weights'], MIDDLING)                   # six HELDs are not six misses
        self.ledger([(2, 'YES'), (2, 'NO')] * 3 + [(1, 'HELD'), (1, 'NOT_DECLARED'), (1, None)] * 30)
        history = PV._axis_history()['gloria']
        self.assertEqual((history['n'], history['YES'], history['NO']), (6, 3, 3))   # behind ninety rows that are no verdict
        self.assertEqual(PV._receptivity(PV._axis_history()), 0.5)
        self.assertEqual(self.judge_calls, [])

    # ---- D. receptivity ---------------------------------------------------------------------------------
    def test_sparse_receptivity_is_unknown_with_middling_weights(self):
        self.ledger([(1, 'NO')] * 4)
        rec = PV.declare()
        self.assertIsNone(rec['receptivity']); self.assertEqual(rec['weights'], MIDDLING)
        self.assertIn('receptivity unknown (4 settled', rec['why']); self.assertIn('provisional', rec['why'])
        self.ledger([(1, 'NO')] * 5)
        rec = PV.declare()
        self.assertEqual((rec['receptivity'], rec['weights']), (0.0, LOW))     # five is enough to read

    def test_stale_verdicts_do_not_hold_receptivity_down(self):
        self.ledger([(40 - i, 'NO') for i in range(25)])                       # 40 to 16 days old
        rows = self.rows()
        rows += [{'intent_id': 'no-time-%d' % i, 'status': 'delivered', 'realized': {'gloria': 'NO'}} for i in range(10)]
        rows += [{'intent_id': 'old-string', 'realized': 'NO', 'timestamp': ago(30)}]
        Path(E.LEDGER).write_text(json.dumps(rows))
        rec = PV.declare()
        self.assertEqual(PV._axis_history()['gloria']['n'], 0)
        self.assertIsNone(rec['receptivity']); self.assertEqual(rec['weights'], MIDDLING); self.assertIn('unknown (0 settled', rec['why'])
        self.assertEqual(PV._axis_history(now=time.time() - 20 * 86400)['gloria']['NO'], 18)   # the same rows, read from nearer their own time
        Path(E.LEDGER).write_text(json.dumps([{'realized': {'gloria': 'NO'}, 'delivered_at': ago(1)}] * 5))
        self.assertEqual(PV._axis_history()['gloria']['n'], 5)                 # the delivery time serves when no selection time is kept

    def test_recovery_after_a_long_gap(self):
        self.ledger([(35 - i // 4, 'NO') for i in range(40)])                  # forty misses, 35 to 26 days old
        self.assertEqual(PV.declare()['weights'], MIDDLING)                   # the gap: her axis is tried again
        self.ledger([(1, 'YES')] * 4 + [(1, 'NO')], keep=True)
        rec = PV.declare()
        self.assertEqual(rec['receptivity'], 0.8); self.assertEqual(rec['weights'], {'field': .25, 'gloria': .6, 'self': .15})
        # filter first, then the latest sixty: old-in-window misses fall behind sixty newer landings, and
        # rows that are no verdict take no place among the sixty
        self.ledger([(13, 'NO')] * 10 + [(3, 'HELD')] * 80 + [(2, 'YES')] * 60 + [(1, None)] * 80)
        history = PV._axis_history()['gloria']
        self.assertEqual((history['n'], history['YES'], history['NO']), (60, 60, 0))

    # ---- her opportunity --------------------------------------------------------------------------------
    def test_opportunity_fires_at_persistently_low_receptivity(self):
        self.low_receptivity(); due = []
        for n in range(1, 9):
            self.answer = self.target(gloria=copy.deepcopy(GLORIA)) if n == 4 else self.target(gloria_decline='this move is about my own choice') if n == 8 else self.target()
            t = self.select(resolve=False)
            self.assertEqual(t['priority'], LOW)                               # the weights themselves are not lifted
            due.append(t['priority_provenance']['gloria_opportunity'])
            self.assertEqual('GLORIA OPPORTUNITY' in self.prompt(), n in (4, 8))
        self.assertEqual(due, [False, False, False, True, False, False, False, True])
        rows = self.rows()[-8:]
        self.assertEqual(rows[3]['target']['selection_check']['gloria_opportunity'], 'declared')
        self.assertEqual(rows[3]['target']['gloria'], GLORIA); self.assertIsNone(rows[3]['realized']['gloria'])
        self.assertEqual(rows[7]['target']['selection_check']['gloria_opportunity'], 'abstained')
        self.assertEqual((rows[7]['realized']['gloria'], rows[7]['not_declared_reason']), ('NOT_DECLARED', {'gloria': 'opportunity_declined'}))
        self.assertEqual(PV.opportunity_report(), {'every': 4, 'turns_since_gloria_declared': 0, 'opportunities': 2,
                                                   'attempts': 2, 'declared': 1, 'abstained': 1})
        self.assertEqual(len(self.select_calls), 8)                            # a reasoned decline is not asked again

    def test_opportunity_counter_survives_a_restart(self):
        self.low_receptivity()
        for _ in range(3): self.select(resolve=False)
        fresh = self.restarted('priority_vector')
        self.assertEqual(fresh.opportunity_report()['turns_since_gloria_declared'], 3)
        self.answer = self.target(gloria=copy.deepcopy(GLORIA))
        with patch.dict(sys.modules, {'priority_vector': fresh}):
            t = self.select(resolve=False)
        self.assertTrue(t['priority_provenance']['gloria_opportunity'])
        self.assertEqual(PV.opportunity_report(), {'every': 4, 'turns_since_gloria_declared': 0, 'opportunities': 1,
                                                   'attempts': 1, 'declared': 1, 'abstained': 0})

    def test_device_only_turn_does_not_spend_the_opportunity(self):
        self.low_receptivity()
        for _ in range(3): self.select(resolve=False)
        for text, source in ((BUTTON, 'gcs'), (BUTTON, None), ("REELROOM EVENT (not Gloria's words): the film ended", None)):
            t = self.select(text, resolve=False, **({'her_source': source} if source else {}))
            self.assertFalse(t['priority_provenance']['gloria_opportunity']); self.assertNotIn('GLORIA OPPORTUNITY', self.prompt())
            self.assertEqual(PV.opportunity_report(), {'every': 4, 'turns_since_gloria_declared': 3, 'opportunities': 0,
                                                       'attempts': 0, 'declared': 0, 'abstained': 0})
        t = self.select(resolve=False)                                         # her next real turn still has it
        self.assertTrue(t['priority_provenance']['gloria_opportunity']); self.assertIn('GLORIA OPPORTUNITY', self.prompt())

    def test_invalid_opportunity_output_abstains_and_is_never_promoted(self):
        self.low_receptivity()
        for _ in range(3): self.select(resolve=False)
        asked = len(self.select_calls)
        t = self.turn(resolve=False)                                           # due; "gloria" {} and no reason, twice
        self.assertEqual(len(self.select_calls), asked + 2)                    # one re-ask, no more
        again = self.select_calls[-1]['messages']
        self.assertEqual(len(again), 4); self.assertIn('CORRECTION, once', again[-1]['content']); self.assertIn('gloria_decline', again[-1]['content'])
        row = self.rows()[-1]
        self.assertEqual(row['target']['gloria'], {})                          # nothing invented to fill the slot
        self.assertEqual((row['realized']['gloria'], row['not_declared_reason']), ('NOT_DECLARED', {'gloria': 'opportunity_no_answer'}))
        self.assertEqual(t['selection_check'], {'retry': 1, 'fault': '', 'abstained': False, 'gloria_opportunity': 'abstained'})
        self.assertEqual(PV.opportunity_report(), {'every': 4, 'turns_since_gloria_declared': 0, 'opportunities': 1,
                                                   'attempts': 1, 'declared': 0, 'abstained': 1})
        self.verdict = 'YES'; E.resolve_previous(HER)                          # the move lands; the abstention stays one
        self.assertEqual(self.rows()[-1]['realized'], {'field': 'YES', 'gloria': 'NOT_DECLARED', 'self': 'YES'})
        self.assertEqual(len(self.judge_calls), 2)

    def test_counting_attempts_never_moves_the_landing_rate(self):
        self.low_receptivity(); before = PV._axis_history()
        for n in range(1, 9):
            self.answer = self.target(gloria=copy.deepcopy(GLORIA)) if n == 4 else self.target()
            self.select(resolve=False)
        self.assertEqual(PV.opportunity_report()['attempts'], 2)
        self.assertEqual(PV._axis_history(), before); self.assertEqual(PV._receptivity(PV._axis_history()), 0.0)
        self.assertEqual([r['realized']['gloria'] for r in self.rows()[-8:]], [None, None, None, None, None, None, None, 'NOT_DECLARED'])
        out = io.StringIO(); state = Path(PV.STATE).read_text()               # the counts-only command declares nothing
        with patch.object(sys, 'argv', ['priority_vector.py', 'opportunity-report']), contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit):
                runpy.run_path(str(REPO / 'scripts/priority_vector.py'), run_name='__main__')
        self.assertEqual(json.loads(out.getvalue()), PV.opportunity_report()); self.assertEqual(Path(PV.STATE).read_text(), state)

    # ---- C. where the criterion shows -------------------------------------------------------------------
    def test_invalid_criterion_is_asked_once_more_then_abstains(self):
        self.answers = [self.target(drop=('observation_window',)), self.target(observation_window='next week')]
        t = self.turn(resolve=False)
        self.assertEqual(len(self.select_calls), 2)                            # one retry, never a third call
        self.assertIn('CORRECTION, once', self.select_calls[1]['messages'][-1]['content'])
        self.assertEqual(t['selection_check'], {'retry': 1, 'fault': 'window_invalid', 'abstained': True})
        self.assertEqual((t['goal'], t['success_criterion']), (TARGET['goal'], TARGET['success_criterion']))   # kept as given, not rewritten
        row = self.rows()[-1]
        self.assertEqual((row['realized']['field'], row['not_declared_reason']), ('NOT_DECLARED', {'field': 'criterion_window_invalid'}))
        self.verdict = 'YES'; E.resolve_previous(HER)                          # only the declared self axis reaches the judge
        self.assertEqual(self.rows()[-1]['realized'], {'field': 'NOT_DECLARED', 'gloria': 'NOT_DECLARED', 'self': 'YES'})
        self.assertEqual(len(self.judge_calls), 1)
        self.answers = [self.target(drop=('evidence_type',)), 'no object at all']   # the re-ask itself fails
        t = self.select(resolve=False)
        self.assertEqual((t['criterion_abstained'], len(self.select_calls)), ('evidence_missing', 4))
        self.answers = [self.target(observation_window='this_reply', evidence_type='her_response')] * 2   # her answer is not in my reply
        self.assertEqual(self.select(resolve=False)['criterion_abstained'], 'window_evidence_mismatch')

    def test_mended_or_valid_criterion_is_not_abstained(self):
        self.answers = [self.target(evidence_type='a feeling'), self.target(observation_window='Her next reply', evidence_type='her_response')]
        t = self.select(resolve=False)
        self.assertEqual(len(self.select_calls), 2)
        self.assertEqual(t['selection_check'], {'retry': 1, 'fault': '', 'abstained': False}); self.assertNotIn('criterion_abstained', t)
        self.assertEqual((t['observation_window'], t['evidence_type']), ('her_next_reply', 'her_response'))
        self.assertEqual(self.rows()[-1]['realized'], {'field': None, 'gloria': None, 'self': None})
        self.answer = self.target(criterion_abstained='the selector may not set this', gloria_abstained='nor this')
        t = self.select(resolve=False)
        self.assertEqual(len(self.select_calls), 3); self.assertEqual(t['selection_check'], {'retry': 0, 'fault': '', 'abstained': False})
        self.assertNotIn('criterion_abstained', t); self.assertNotIn('gloria_abstained', t)

    def test_quotation_demand_is_flagged_never_rejected(self):
        self.answer = self.target(success_criterion='she says word for word that she agrees',
                                  observation_window='her_next_reply', evidence_type='her_response')
        t = self.select(resolve=False)
        self.assertEqual(len(self.select_calls), 1)
        self.assertEqual(t['selection_check'], {'retry': 0, 'fault': '', 'abstained': False, 'flags': ['quotation_demand']})
        self.assertIsNone(self.rows()[-1]['realized']['field'])
        self.answer = self.target(success_criterion='she answers in her own way', observation_window='her_next_reply', evidence_type='her_response')
        self.assertNotIn('flags', self.select(resolve=False)['selection_check'])   # her ordinary speech is valid evidence

    def test_selector_is_told_where_a_criterion_shows_beside_what_she_likes(self):
        self.select(resolve=False)
        user = self.prompt()
        self.assertLess(user.index('WHAT SHE HAS TOLD YOU SHE LIKES'), user.index('WHERE THE CRITERION SHOWS'))
        self.assertLess(user.index('WHERE THE CRITERION SHOWS'), user.index('Return ONLY one complete JSON object'))
        for field in ('"observation_window"', '"evidence_type"'): self.assertIn(field, user)
        self.assertEqual(len(self.select_calls), 1)


    # ---- review, 10 November: shapes the first pass missed ----------------------------------------------
    def test_spin_note_is_a_device_event_never_her_answer(self):
        self.delivered(gloria=copy.deepcopy(GLORIA)); self.verdict = 'NO'
        E.resolve_previous('GLORIA: Earlier topic.\nVINTOS: Earlier answer.\nGLORIA (now): [Gloria just spun Vintos around]')
        row = self.rows()[-1]
        self.assertEqual(self.judge_calls, [])
        self.assertNotIn('NO', row['realized'].values()); self.assertNotIn(None, row['realized'].values())
        self.assertEqual(set(row['held_reason'].values()), {'device_event_only'})
        self.assertEqual(E._her_follow_up('GLORIA (now): [Gloria just spun Vintos around] Do that again.'),
                         ('GLORIA (now): Do that again.', ''))

    def test_wrong_shaped_rotation_file_neither_hides_the_primary_nor_lifts_the_cap(self):
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0)})
        path = Path(DD._rotation_path())
        for bad in ({'resting': [1]}, {'resting': 'soon'}, {'resting': {A: 'not a time'}}, {'run': 'x', 'id': A},
                    {'id': 7, 'run': 2}, {'id': A, 'run': -4}, [], 'x'):
            path.write_text(json.dumps(bad)); Path(E.LEDGER).write_text('[]')
            self.assertEqual(DD.primary_for_turn()['id'], A, bad)
            for _ in range(5): self.turn(resolve=False)
            self.assertEqual([p for p, _ in self.shown()], [A, A, A, B, A], bad)
            mended = json.loads(path.read_text())
            self.assertIsInstance(mended['resting'], dict); self.assertEqual((mended['id'], mended['run']), (A, 1))
        path.write_text('{not json'); Path(E.LEDGER).write_text('[]')
        for _ in range(4): self.turn(resolve=False)
        self.assertEqual([p for p, _ in self.shown()], [A, A, A, B])

    def test_two_turns_at_once_do_not_trip_over_one_temporary_file(self):
        faults = []
        def turns():
            for _ in range(40):
                try: PV.note_selection(False)
                except Exception as e: faults.append(type(e).__name__)
        threads = [threading.Thread(target=turns) for _ in range(6)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(faults, [])
        self.assertGreater(PV.opportunity_report()['turns_since_gloria_declared'], 0)
        self.assertEqual([f.name for f in self.mem.iterdir() if '.tmp.' in f.name], [])

    def test_retire_without_an_id_says_so_and_writes_nothing(self):
        self.press(**{A: self.prow(TEXT_A, 4.0)}); before = Path(DD.PRESS).read_text()
        with patch.object(sys, 'argv', ['desired_difference.py', 'retire']), contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit) as stop:
                runpy.run_path(str(REPO / 'scripts/desired_difference.py'), run_name='__main__')
        self.assertEqual(stop.exception.code, 2); self.assertIn('usage', out.getvalue())
        self.assertEqual(Path(DD.PRESS).read_text(), before)
        self.assertEqual(list(self.mem.glob('intent-pressure.json.bak-*')), [])


if __name__ == '__main__':
    unittest.main()

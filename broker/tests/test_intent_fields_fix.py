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
import signal
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
    'gloria': {}, 'self': {'difference_intended': 'say which I prefer', 'enactment': 'choose one and explain why',
                           'observation_window': 'this_reply', 'evidence_type': 'my_move'},
    'addresses': 'NONE'}
GLORIA = {'difference_intended': 'she can choose using the tradeoff', 'enactment': 'give both alternatives',
          'observation_window': 'her_next_reply', 'evidence_type': 'her_response'}
HER_PLAN = 'GLORIA: Earlier topic.\nVINTOS: Earlier answer.\nGLORIA (now): So what is the plan for the weekend?'
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
        # Her axis goes to the rubric judge (12 November; Sonnet 5.5). Here the fixture's one-word judge stands in
        # for it, through the same queue and the same call list: a verdict word is what the judge answered, anything
        # else is NOT_JUDGEABLE. The
        # check at selection finds nothing already met.
        self.stack.enter_context(patch.object(E, '_rubric_judge', lambda packet: IntentFieldsFix.sol(self, packet)))
        self.stack.enter_context(patch.object(E, '_stale_gloria', return_value='not_met'))
        # the resolver inline, as these tests read it; the background resolver has its own tests (gloria_judge_sol)
        self.stack.enter_context(patch.object(E, 'RESOLVE_IN_BACKGROUND', False))
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

    def sol(self, packet):
        """Sol's stand-in: the packet is kept as the judge saw it, the verdict comes from the fixture's queue."""
        self.judge_calls.append({'max_tokens': 6, 'sol': True, 'messages': [
            {'role': 'system', 'content': 'gloria rubric'}, {'role': 'user', 'content': json.dumps(packet)}]})
        raw = self.verdicts.pop(0) if self.verdicts else self.verdict
        if isinstance(raw, Exception): raise raw
        if raw in ('YES', 'PARTIAL', 'NO'):
            return {'verdict': raw, 'reason': {'YES': 'plain_yes', 'PARTIAL': 'partial_hedged', 'NO': 'not_shown'}[raw],
                    'codes': [], 'adherence': 'delivered', 'confidence': 'high', 'status': 'ok'}
        return {'verdict': 'NOT_JUDGEABLE', 'reason': 'error', 'status': 'unparsed'}

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

    def delivered(self, drop=(), mine=None, **over):
        """A delivered move waiting for what follows it, with no selector involved."""
        t = self.target(drop=drop, **over); t['intent_id'] = uuid.uuid4().hex
        if mine is not None: t['self'] = mine
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

    def test_graduated_row_waits_for_her_words_not_a_miss_or_a_landing(self):
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
        self.assertEqual(self.pressure(A)['weight'], 1.5); self.assertIsNone(DD.primary_for_turn())   # ... is mine, and opens nothing
        self.assertEqual(DD.her_words_reopen('So what is the plan for the weekend?'), [A])   # her own words do
        self.assertEqual(DD.primary_for_turn()['id'], A)
        row = self.pressure(A); row['lineage'].append({'graduated': time.time(), 'at_weight': 5.0}); self.press(**{A: row})
        self.assertIsNone(DD.primary_for_turn())                               # a later graduation closes it again

    def test_rested_primary_stays_out_for_three_of_her_turns(self):
        # (10 November, round three) A rest used to end as soon as one other primary had been shown: A A A B A,
        # three turns in four to one row over any long run. It now lasts three of her turns led by another primary.
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0)})
        for _ in range(24): self.turn(resolve=False)
        shown = [p for p, _ in self.shown()]
        self.assertEqual(shown, ([A] * 3 + [B] * 3) * 4)
        for i in range(len(shown) - 5): self.assertEqual(shown[i:i + 6].count(A), 3, i)    # wherever the count starts
        # no row was ever graded: the cap counts selections, whatever verdict they later get
        self.assertTrue(all(r['realized']['field'] is None for r in self.rows()))
        # (10 November, round four) the report says what is still waiting inside its window, and what expired
        self.assertEqual(DD.primary_report(24), {'turns': 24, 'with_primary': 24, 'distinct_primaries': 2,
                                                 'top_primary_turns': 12, 'top_primary_share': 0.5, 'max_run': 3,
                                                 'pending': 24, 'expired_coverage': 0})
        self.assertEqual({r['target']['primary_accounting'] for r in self.rows()}, {'reserved'})

    def test_lone_primary_rests_and_nothing_stands_in(self):
        self.press(**{A: self.prow(TEXT_A, 4.0)})
        for _ in range(12): self.select(resolve=False)
        # (10 November, round three) nothing is put up as a primary to use the rest up: a turn with none counts
        self.assertEqual([p for p, _ in self.shown()], [A, A, A, None, None, None] * 2)
        self.assertNotIn('PRIMARY DIFFERENCE', self.prompt())
        self.assertEqual(DD.primary_report(12)['top_primary_share'], 0.5)
        for _ in range(4): self.select(resolve=False)                          # three more turns led, and one of the rest served
        self.assertEqual(json.loads(Path(DD._rotation_path()).read_text())['rest_turns'], {A: 1})
        now = time.time()                                                      # the three-day bound is the other way out
        self.assertIsNone(DD.primary_for_turn(now=now + 2 * 86400))
        self.assertEqual(DD.primary_for_turn(now=now + 3 * 86400 + 600)['id'], A)
        state = DD.primary_shown(A, now=now + 3 * 86400 + 600)
        self.assertEqual((state['run'], state['resting'], state['rest_turns']), (1, {}, {}))

    def test_a_turn_that_is_not_hers_discharges_no_rest(self):
        self.press(**{A: self.prow(TEXT_A, 4.0)})
        served = lambda: json.loads(Path(DD._rotation_path()).read_text())['rest_turns']
        for _ in range(3): self.select(resolve=False)                          # it leads three turns, and rests
        self.assertEqual(served(), {A: 0})
        self.select(BUTTON, resolve=False, her_source='gcs'); self.select(BUTTON, resolve=False)   # a device event, by source and by text
        self.select("GLORIA: Earlier topic.\nREELROOM EVENT (not Gloria's words): the film ended", resolve=False)
        with PV.background():
            self.select(resolve=False)                                         # a background run
        self.select(persist=False, step_campaign=False)                        # a preview
        self.assertEqual(served(), {A: 0})
        self.answer = self.target(her_turn=False)                              # the selector cannot say whose turn it is
        for _ in range(4): self.select(resolve=False)
        self.assertEqual([p for p, _ in self.shown()], [A] * 3 + [None] * 7 + [A])
        self.assertEqual([r['target']['her_turn'] for r in self.rows()], [True] * 3 + [False] * 4 + [True] * 4)
        # (10 November, round four) such a turn is no selection at all: it is marked, and the report leaves it out
        self.assertEqual([r['target']['primary_accounting'] for r in self.rows()], ['reserved'] * 3 + ['not_eligible'] * 4 + ['reserved'] * 4)
        self.assertEqual((DD.primary_report(30)['turns'], DD.primary_report(30)['with_primary']), (7, 4))

    def test_streak_and_rest_survive_a_restart(self):
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0)})
        self.turn(resolve=False); self.turn(resolve=False)
        state = json.loads(Path(DD._rotation_path()).read_text())
        self.assertEqual((state['id'], state['run']), (A, 2))
        with patch.dict(sys.modules, {'desired_difference': self.restarted('desired_difference')}):
            self.turn(resolve=False); self.turn(resolve=False)
        self.assertEqual([p for p, _ in self.shown()], [A, A, A, B])
        state = json.loads(Path(DD._rotation_path()).read_text())             # a rest part-served is on disk too
        self.assertEqual((state['id'], state['run'], state['rest_turns']), (B, 1, {A: 1}))
        with patch.dict(sys.modules, {'desired_difference': self.restarted('desired_difference')}):
            self.turn(resolve=False)
        with patch.dict(sys.modules, {'desired_difference': self.restarted('desired_difference')}):
            self.turn(resolve=False); self.turn(resolve=False)
        self.assertEqual([p for p, _ in self.shown()][4:], [B, B, A])          # not cut short, not begun again

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
        # (round four) these rows carry no time at all: their window cannot be shown open, so they are not pending
        self.assertEqual(DD.primary_report(30), {'turns': 8, 'with_primary': 8, 'distinct_primaries': 2,
                                                 'top_primary_turns': 6, 'top_primary_share': 0.75, 'max_run': 3,
                                                 'pending': 0, 'expired_coverage': 8})
        Path(E.LEDGER).write_text(json.dumps([{'target': {'primary_shown': p}} for p in [A, None, A, None]]))
        report = DD.primary_report()
        self.assertEqual((report['turns'], report['with_primary'], report['top_primary_share'], report['max_run']), (4, 2, 0.5, 1))
        out = io.StringIO()
        with patch.object(sys, 'argv', ['desired_difference.py', 'primary-report', '2']), contextlib.redirect_stdout(out):
            runpy.run_path(str(REPO / 'scripts/desired_difference.py'), run_name='__main__')
        self.assertEqual(json.loads(out.getvalue())['turns'], 2)

    # ---- B. whose words the follow-up is ----------------------------------------------------------------
    def test_device_only_follow_up_holds_my_side_and_keeps_her_reply_open(self):
        # (10 November, round three) A device event used to close the whole move as HELD, her axis with it. What
        # shows in my own reply is still held at once; what shows in her next reply waits for her, three such
        # events at most.
        self.delivered(gloria=copy.deepcopy(GLORIA))
        E.resolve_previous(BUTTON, source='gcs')                               # where it came from decides
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': 'HELD', 'gloria': None, 'self': 'HELD'})
        self.assertEqual(row['held_reason'], {'field': 'device_event_only', 'self': 'device_event_only'})
        skip = row['skipped_observations']                                     # how many, when, why, from where: never the text
        self.assertEqual(sorted(skip), ['first', 'last', 'n', 'reason', 'source'])
        self.assertEqual((skip['n'], skip['reason'], skip['source']), (1, 'device_event_only', 'gcs'))
        self.assertNotIn('response_text', row); self.assertNotIn('response_source', row)   # the event is not kept as her reply
        self.delivered()
        E.resolve_previous(BUTTON)                                             # no source came with it: the text is read
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': 'HELD', 'gloria': 'NOT_DECLARED', 'self': 'HELD'})
        self.assertEqual(row['held_reason'], {'field': 'device_event_only', 'self': 'device_event_only'})
        self.delivered()
        E.resolve_previous("GLORIA: Earlier topic.\nREELROOM EVENT (not Gloria's words): the film ended")
        self.assertEqual(self.rows()[-1]['held_reason'], {'field': 'not_her_words', 'self': 'not_her_words'})
        first = self.rows()[0]                                                 # three device events, and her axis still waits
        self.assertEqual((first['realized']['gloria'], first['skipped_observations']['n']), (None, E.DEVICE_SKIPS_MAX))
        self.delivered()
        self.select(BUTTON, her_source='gcs')                                  # the chat route hands the source through
        self.assertEqual(self.rows()[-2]['held_reason'], {'field': 'device_event_only', 'self': 'device_event_only'})
        first = self.rows()[0]                                                 # the fourth: her reply never came inside the window
        self.assertEqual(first['realized'], {'field': 'HELD', 'gloria': 'HELD', 'self': 'HELD'})
        self.assertEqual(first['held_reason'], {'field': 'device_event_only', 'gloria': 'her_reply_window_expired', 'self': 'device_event_only'})
        self.assertEqual(first['skipped_observations']['n'], 4)
        E.resolve_previous(HER)                                                # her later words do not reopen what was held
        self.assertEqual(self.judge_calls, []); self.assertEqual(len(self.select_calls), 1)
        self.assertEqual([r['realized']['field'] for r in self.rows()], ['HELD'] * 4 + [None])
        self.assertEqual(PV._axis_history()['gloria']['n'], 0)                 # an expiry is no verdict on her

    def test_her_reply_after_a_device_event_settles_the_waiting_axis_once(self):
        self.delivered(gloria=copy.deepcopy(GLORIA))
        E.resolve_previous(BUTTON, source='gcs'); E.resolve_previous(''); E.resolve_previous(BUTTON)
        self.assertEqual(self.rows()[-1]['skipped_observations']['n'], 2); self.assertEqual(self.judge_calls, [])
        self.verdict = 'PARTIAL'; E.resolve_previous(HER, source='chat')
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': 'HELD', 'gloria': 'PARTIAL', 'self': 'HELD'})
        self.assertEqual(row['held_reason'], {'field': 'device_event_only', 'self': 'device_event_only'})   # what was held stays held, with its reason
        self.assertEqual(len(self.judge_calls), 1)                             # only the axis that was waiting reached the judge
        seen = self.judge_calls[0]['messages'][1]['content']
        self.assertIn('Which alternative would you choose?', seen); self.assertNotIn('pressed the button', seen)
        self.assertEqual((row['skipped_observations']['n'], row['response_source']), (2, 'chat'))
        E.resolve_previous(HER); E.resolve_previous('GLORIA (now): And one more thing.'); E.resolve_previous(BUTTON, source='gcs')
        self.assertEqual(len(self.judge_calls), 1); self.assertEqual(self.rows()[-1], row)   # settled once: nothing grades it again
        self.assertEqual(sys.modules['outcome_join'].record.call_count, 1)
        history = PV._axis_history()['gloria']
        self.assertEqual((history['n'], history['PARTIAL']), (1, 1))

    def test_one_reply_of_hers_settles_an_earlier_waiting_move_and_the_latest(self):
        self.delivered(gloria=copy.deepcopy(GLORIA))
        E.resolve_previous(BUTTON, source='gcs')
        self.delivered(gloria=copy.deepcopy(GLORIA))                           # my next move, before she has spoken
        self.verdicts = ['YES', 'YES', 'YES']; E.resolve_previous(HER)
        early, late = self.rows()
        # the earlier move first, its open axis only - and her reply came after my next move, so it answers that
        # one: NOT_JUDGEABLE for the earlier, settled in code with no judge asked (12 November)
        self.assertEqual(early['realized'], {'field': 'HELD', 'gloria': 'NOT_JUDGEABLE', 'self': 'HELD'})
        self.assertEqual((early['gloria_judge']['reason'], early['gloria_judge']['later_moves']), ('reply_to_later_move', 1))
        self.assertEqual(late['realized'], {'field': 'YES', 'gloria': 'YES', 'self': 'YES'})
        self.assertEqual(len(self.judge_calls), 3)
        self.assertNotIn('skipped_observations', late)
        self.verdict = 'NO'; E.resolve_previous(HER); E.resolve_previous('GLORIA (now): And one more thing.')
        self.assertEqual(len(self.judge_calls), 3); self.assertEqual(self.rows(), [early, late])   # each row once
        self.assertEqual(sys.modules['outcome_join'].record.call_count, 2)
        history = PV._axis_history()['gloria']
        self.assertEqual((history['n'], history['YES'], history['NO']), (1, 1, 0))

    def test_waiting_axis_expires_held_after_a_day_with_no_judge(self):
        def a_day_on(hours):
            # (10 November, round four) the day runs from the move's own delivery, not from the skipped event
            rows = self.rows(); self.assertIn('first', rows[-1]['skipped_observations'])
            rows[-1]['delivered_at'] = (datetime.fromisoformat(rows[-1]['delivered_at']) - timedelta(hours=hours, minutes=1)).isoformat()
            Path(E.LEDGER).write_text(json.dumps(rows))
        self.delivered(gloria=copy.deepcopy(GLORIA)); E.resolve_previous(BUTTON, source='gcs'); a_day_on(E.DEVICE_WAIT_HOURS)
        self.verdict = 'YES'; E.resolve_previous(HER)                          # her words, a day late: not this move's next reply
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': 'HELD', 'gloria': 'HELD', 'self': 'HELD'})
        self.assertEqual(row['held_reason'], {'field': 'device_event_only', 'gloria': 'her_reply_window_expired', 'self': 'device_event_only'})
        self.assertEqual(row['skipped_observations']['n'], 1); self.assertEqual(self.judge_calls, [])
        E.resolve_previous(HER); self.assertEqual(self.rows()[-1], row); self.assertEqual(self.judge_calls, [])
        self.assertEqual(PV._axis_history()['gloria']['n'], 0)
        self.delivered(gloria=copy.deepcopy(GLORIA)); E.resolve_previous(BUTTON, source='gcs'); a_day_on(E.DEVICE_WAIT_HOURS - 1)
        E.resolve_previous(HER)                                                # inside the day: it is her next reply
        self.assertEqual(self.rows()[-1]['realized'], {'field': 'HELD', 'gloria': 'YES', 'self': 'HELD'}); self.assertEqual(len(self.judge_calls), 1)
        self.delivered(gloria=copy.deepcopy(GLORIA)); E.resolve_previous(BUTTON, source='gcs'); a_day_on(E.DEVICE_WAIT_HOURS)
        E.resolve_previous(BUTTON, source='gcs')                               # a second event, a day late: the day ends it, not the count
        row = self.rows()[-1]
        self.assertEqual((row['realized']['gloria'], row['held_reason']['gloria'], row['skipped_observations']['n']), ('HELD', 'her_reply_window_expired', 1))
        self.assertEqual(len(self.judge_calls), 1)
        self.assertEqual((E.DEVICE_SKIPS_MAX, E.DEVICE_WAIT_HOURS, E.WINDOW_EXPIRED), (3, 24, 'her_reply_window_expired'))

    def test_move_that_never_said_where_it_shows_waits_for_her_too(self):
        mine = {'difference_intended': 'say which I prefer', 'enactment': 'choose one and explain why'}
        self.delivered(drop=('observation_window', 'evidence_type'), mine=mine)   # a row from before windows were written
        E.resolve_previous(BUTTON, source='gcs')
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': None, 'gloria': 'NOT_DECLARED', 'self': None})
        self.assertNotIn('held_reason', row); self.assertEqual(row['skipped_observations']['n'], 1)
        self.verdict = 'YES'; E.resolve_previous(HER); E.resolve_previous(HER)
        self.assertEqual(self.rows()[-1]['realized'], {'field': 'YES', 'gloria': 'NOT_DECLARED', 'self': 'YES'})
        self.assertEqual(len(self.judge_calls), 2)
        # ... and an older one still, with a single verdict: it waits, and expires as one
        single = {'intent_id': 'synthetic-single', 'status': 'delivered', 'reply': 'a synthetic reply', 'realized': None,
                  'target': {'field_state': 'a synthetic field', 'goal': 'a synthetic goal', 'enactment': 'a synthetic move'},
                  'timestamp': datetime.now().isoformat(), 'delivered_at': datetime.now().isoformat()}
        Path(E.LEDGER).write_text(json.dumps([single]))
        for n in range(1, E.DEVICE_SKIPS_MAX + 1):
            E.resolve_previous(BUTTON, source='gcs')
            row = self.rows()[-1]
            self.assertEqual((row['realized'], row['skipped_observations']['n']), (None, n)); self.assertNotIn('held_reason', row)
        E.resolve_previous(BUTTON, source='gcs')
        row = self.rows()[-1]
        self.assertEqual((row['realized'], row['held_reason']), ('HELD', {'single': 'her_reply_window_expired'}))
        E.resolve_previous(HER); self.assertEqual(len(self.judge_calls), 2)

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
        for axis, call in zip(('field', 'gloria', 'self'), self.judge_calls):
            seen = call['messages'][1]['content']
            if axis == 'gloria':
                self.assertIn('I would pick the second one.', seen)
            else:
                self.assertNotIn('I would pick the second one.', seen)
            self.assertNotIn('Earlier topic.', seen)
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
        # (10 November, round three) her axis waits through three device events and expires HELD on the fourth:
        # the first three moves have expired, the last three still wait. Neither is a verdict.
        self.assertEqual([r['realized']['gloria'] for r in self.rows()], ['HELD'] * 3 + [None] * 3)
        self.assertEqual([r['skipped_observations']['n'] for r in self.rows()], [4, 4, 4, 3, 2, 1])
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
        self.assertEqual(json.loads(out.getvalue()), PV.opportunity_report(coverage=True)); self.assertEqual(Path(PV.STATE).read_text(), state)
        # (round four) the command also says what became of her declared axis; a selection never delivered is not in it
        self.assertEqual(json.loads(out.getvalue())['gloria_axis'], {'settled': 0, 'pending': 0, 'expired_coverage': 0})
        self.assertNotIn('gloria_axis', PV.opportunity_report())

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
        self.assertEqual(row['realized'], {'field': 'HELD', 'gloria': None, 'self': 'HELD'})   # (round three) her axis waits for her words
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
            self.assertEqual([p for p, _ in self.shown()], [A, A, A, B, B], bad)   # (round three) the rest is three turns long
            mended = json.loads(path.read_text())
            self.assertIsInstance(mended['resting'], dict); self.assertEqual((mended['id'], mended['run']), (B, 2))
            self.assertEqual(mended['rest_turns'], {A: 2})
        path.write_text('{not json'); Path(E.LEDGER).write_text('[]')
        for _ in range(4): self.turn(resolve=False)
        self.assertEqual([p for p, _ in self.shown()], [A, A, A, B])
        for bad in ('x', [1], {A: 'soon'}, {A: -5}, {B: 2}, None):             # a wrong-shaped count neither ends a rest early nor lengthens it
            path.write_text(json.dumps({'id': A, 'run': 3, 'resting': {A: time.time()}, 'rest_turns': bad})); Path(E.LEDGER).write_text('[]')
            self.assertEqual(DD.primary_for_turn()['id'], B, bad)
            for _ in range(4): self.turn(resolve=False)
            self.assertEqual([p for p, _ in self.shown()], [B, B, B, A], bad)

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

    # ---- review, 10 November (second pass): what reopens a graduated row, the receptivity arithmetic, every axis's form ----
    REWORDED = 'name the weekend plan outright, plainly'      # the same intention as TEXT_A, in a later turn's own words

    def closed_row_beside_an_open_one(self, **over):
        self.graduated = time.time() - 7200
        closed = self.prow(TEXT_A, 2.6, count=6, lineage=[{'graduated': self.graduated, 'at_weight': 5.0}], **over)
        self.press(**{A: closed, B: self.prow(TEXT_B, 1.2)})
        self.assertEqual(DD.primary_for_turn()['id'], B)                       # A is heavier, and closed

    def test_graduated_row_reopens_on_her_own_words_in_a_new_turn(self):
        """A closed row is never the primary, so its news cannot come from being selected. It comes from her."""
        self.closed_row_beside_an_open_one()
        t = self.turn(HER_PLAN, resolve=False)
        row = self.pressure(A)
        self.assertEqual([sorted(l) for l in row['lineage']], [['at_weight', 'graduated'], ['mark', 'reopened_by_her']])
        self.assertGreater(row['lineage'][-1]['reopened_by_her'], self.graduated)
        self.assertEqual(t['primary_shown'], A)                                # open in the very turn she raised it
        # eligibility only: no weight, count or verdict moved, on this row or in the ledger
        self.assertEqual((row['weight'], row['count'], self.pressure(B)['weight']), (2.6, 6, 1.2))
        self.assertEqual(self.rows()[-1]['realized'], {'field': None, 'gloria': None, 'self': None})
        self.assertEqual(DD.primary_for_turn({'id': A}), dict(DD.primary_for_turn(), required=True))   # the required route too
        for _ in range(3): self.turn(resolve=False)                            # the run cap holds for a reopened row
        self.assertEqual([p for p, _ in self.shown()], [A, A, A, B])
        row = self.pressure(A); row['retired'] = time.time(); self.press(**{A: row, B: self.pressure(B)})
        Path(DD._rotation_path()).unlink()
        self.assertEqual(DD.primary_for_turn()['id'], B); self.assertEqual(DD.primary_for_turn({'id': A})['id'], B)   # and so does retirement

    def test_graduated_row_stays_closed_on_a_miss_a_landing_a_later_time_or_a_showing(self):
        """The control: a later turn of mine reaches the same row in its own rewording, and whatever verdict that
        turn gets - a landing included - the row stays closed. My restatement is not her raising it."""
        self.closed_row_beside_an_open_one()
        self.answer = self.target(field_state=self.REWORDED)
        for verdict, weight, count, relieved in (('NO', 3.6, 7, 0), ('PARTIAL', 4.1, 8, 0), ('YES', 2.05, 8, 1)):
            t = self.turn(resolve=False); self.verdict = verdict; E.resolve_previous(HER)
            self.assertEqual((t['addresses'], self.rows()[-1]['realized']['field']), ('NONE', verdict))
            row = self.pressure(A)
            self.assertEqual((row['weight'], row['count']), (weight, count))   # the verdict did reach the row
            self.assertGreater(row['last'], time.time() - 60)                  # ... and stamped it now
            self.assertEqual(len([l for l in row['lineage'] if 'relieved' in l]), relieved)
            self.assertFalse(any('reopened_by_her' in l for l in row['lineage']))
            self.assertFalse(DD.primary_eligible(A, row, {}))
        # (10 November, round three) a closed row is not an instruction: it is out of what keeps failing as well
        self.assertNotIn(TEXT_A, DD.pressure_block())
        self.select(resolve=False); self.assertNotIn(TEXT_A, self.prompt())    # ... for the selector too
        self.assertNotEqual((DD.primary_for_turn() or {}).get('id'), A)
        self.assertNotEqual((DD.primary_for_turn({'id': A}) or {}).get('id'), A)
        self.assertTrue(all(p != A for p, _ in self.shown()))

    def test_old_or_repeated_words_of_hers_do_not_reopen(self):
        self.closed_row_beside_an_open_one()
        # an earlier line of hers still in view is not this turn's word
        old = 'GLORIA: So what is the plan for the weekend?\nVINTOS: Earlier answer.\nGLORIA (now): Which alternative would you choose?'
        self.assertEqual(self.turn(old, resolve=False)['primary_shown'], B)
        self.assertEqual(len(self.pressure(A)['lineage']), 1)
        self.assertEqual(DD.her_words_reopen('The weekend was lovely.'), [])   # one shared word is not her raising it
        self.assertEqual(self.turn(HER_PLAN, resolve=False)['primary_shown'], A)
        row = self.pressure(A); row['lineage'].append({'graduated': time.time(), 'at_weight': 5.0})   # it failed its way shut again
        self.press(**{A: row, B: self.pressure(B)})
        self.turn(HER_PLAN, resolve=False)                                     # the same words again: already heard
        self.assertEqual(len(self.pressure(A)['lineage']), 3); self.assertFalse(DD.primary_eligible(A, self.pressure(A), {}))
        self.assertEqual(DD.her_words_reopen('Tell me the weekend plan outright.'), [A])   # new words of hers are news

    def test_device_event_or_preview_does_not_reopen(self):
        self.closed_row_beside_an_open_one(); before = Path(DD.PRESS).read_text()
        touched = "GLORIA: Earlier topic.\nVINTOS: Earlier answer.\nGLORIA (now): [Gloria just touched the plan for the weekend]"
        # (10 November, round four) a device event is shown no primary at all - the closed row or any other
        self.assertIsNone(self.turn(touched, resolve=False)['primary_shown'])               # a device note, whatever it says
        self.assertIsNone(self.turn(HER_PLAN, resolve=False, her_source='gcs')['primary_shown'])     # a device source, whatever the text
        self.assertEqual(self.select(HER_PLAN, persist=False, step_campaign=False)['primary_shown'], B)   # a preview
        with PV.background():
            self.select(HER_PLAN, resolve=False)                               # a background run
        self.assertEqual(Path(DD.PRESS).read_text(), before)

    def test_retired_row_is_not_reopened_by_her_words(self):
        self.closed_row_beside_an_open_one(retired=time.time() - 60); before = self.pressure(A)
        self.assertEqual(DD.her_words_reopen('So what is the plan for the weekend?'), [])
        self.assertEqual(self.turn(HER_PLAN, resolve=False)['primary_shown'], B)
        self.assertEqual(self.pressure(A), before)
        self.assertEqual(DD.primary_for_turn({'id': A})['id'], B)

    # ---- C on every declared axis ----
    def test_invalid_gloria_axis_is_asked_once_more_then_only_it_abstains(self):
        unsaid = {k: v for k, v in GLORIA.items() if k != 'observation_window'}
        self.answers = [self.target(gloria=unsaid), self.target(gloria=dict(GLORIA, observation_window='this_reply'))]
        t = self.turn(resolve=False)
        self.assertEqual(len(self.select_calls), 2)                            # one retry, never a third call
        self.assertIn('the "gloria" axis did not say where', self.select_calls[1]['messages'][-1]['content'])
        self.assertEqual(t['selection_check'], {'retry': 1, 'fault': '', 'abstained': False,
                                                'axis_faults': {'gloria': 'window_evidence_mismatch'}})
        self.assertEqual((t['gloria'], t['self'], t['goal']), ({}, TARGET['self'], TARGET['goal']))   # the others stand
        self.assertNotIn('criterion_abstained', t)
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': None, 'gloria': 'NOT_DECLARED', 'self': None})
        self.assertEqual(row['not_declared_reason'], {'gloria': 'criterion_window_evidence_mismatch'})
        self.verdict = 'YES'; E.resolve_previous(HER)
        self.assertEqual(self.rows()[-1]['realized'], {'field': 'YES', 'gloria': 'NOT_DECLARED', 'self': 'YES'})
        self.assertEqual(len(self.judge_calls), 2)                             # her axis never reaches the judge
        self.answers = [self.target(gloria=dict(GLORIA, evidence_type='my_move'))] * 2    # a change in her is not my move
        self.assertEqual(self.select(resolve=False)['axis_abstained'], {'gloria': 'evidence_not_her_response'})
        self.answers = [self.target(gloria=unsaid), self.target(gloria=copy.deepcopy(GLORIA))]   # mended on the re-ask
        t = self.select(resolve=False)
        self.assertEqual((t['gloria'], t['selection_check']), (GLORIA, {'retry': 1, 'stale': 'not_met', 'fault': '', 'abstained': False}))
        self.assertNotIn('axis_abstained', t); self.assertNotIn('not_declared_reason', self.rows()[-1])

    def test_invalid_self_axis_abstains_alone_even_when_it_leads(self):
        self.low_receptivity()                                                 # self carries 0.6 here: the dominant axis
        mine = dict(TARGET['self'], evidence_type='her_response', observation_window='her_next_reply')
        self.answers = [dict(self.target(gloria=copy.deepcopy(GLORIA)), **{'self': mine})] * 2
        t = self.turn(resolve=False)                                           # the turn goes on, its weights as declared
        self.assertEqual((t['priority'], t['self'], t['gloria']), (LOW, {}, GLORIA))
        # (10 November, round three) ... and the lead falls to the heaviest axis that is really declared
        self.assertEqual((t['lead_axis'], t['lead_fallback']), ('field', {'from': 'self', 'to': 'field'}))
        self.assertIn('My self axis is undeclared this turn; the field leads this move instead.', E.prompt_block(t))
        self.assertEqual(len(self.select_calls), 2)
        self.assertEqual(t['axis_abstained'], {'self': 'evidence_not_my_move'})
        row = self.rows()[-1]
        self.assertEqual(row['realized'], {'field': None, 'gloria': None, 'self': 'NOT_DECLARED'})
        self.assertEqual(row['not_declared_reason'], {'self': 'criterion_evidence_not_my_move'})
        self.verdict = 'YES'; E.resolve_previous(HER)
        self.assertEqual(self.rows()[-1]['realized'], {'field': 'YES', 'gloria': 'YES', 'self': 'NOT_DECLARED'})
        self.answers = [dict(self.target(), **{'self': dict(TARGET['self'], observation_window='her_next_reply')})] * 2
        self.assertEqual(self.select(resolve=False)['axis_abstained'], {'self': 'window_not_this_reply'})
        self.answers = [dict(self.target(), **{'self': {k: v for k, v in TARGET['self'].items() if k != 'evidence_type'}})] * 2
        self.assertEqual(self.select(resolve=False)['axis_abstained'], {'self': 'evidence_missing'})

    def test_abstained_gloria_attempt_is_counted_and_never_a_verdict(self):
        self.low_receptivity(); before = PV.receptivity_report()
        for _ in range(3): self.select(resolve=False)
        unsaid = {k: v for k, v in GLORIA.items() if k != 'evidence_type'}
        self.answers = [self.target(gloria=unsaid)] * 2
        t = self.turn(resolve=False)                                           # the fourth turn: her opportunity
        self.assertTrue(t['priority_provenance']['gloria_opportunity'])
        self.assertEqual(t['selection_check']['gloria_opportunity'], 'abstained')
        self.assertEqual(PV.opportunity_report(), {'every': 4, 'turns_since_gloria_declared': 0, 'opportunities': 1,
                                                   'attempts': 1, 'declared': 0, 'abstained': 1})
        row = self.rows()[-1]
        self.assertEqual((row['realized']['gloria'], row['not_declared_reason']), ('NOT_DECLARED', {'gloria': 'criterion_evidence_missing'}))
        self.verdict = 'NO'; E.resolve_previous(HER)
        self.assertEqual(self.rows()[-1]['realized'], {'field': 'NO', 'gloria': 'NOT_DECLARED', 'self': 'NO'})
        self.assertEqual(PV.receptivity_report(), before)                      # six NO, as before: nothing was added

    def test_receptivity_reason_and_report_state_the_counts(self):
        self.ledger([(1, 'NO')] * 5 + [(1, 'PARTIAL')])
        rec = PV.declare()
        self.assertEqual((rec['receptivity'], rec['weights']), (0.08, LOW))
        self.assertIn('receptivity low (0.08 = (0 YES + 0.5 x 1 PARTIAL) / 6 settled Gloria-axis verdicts in the last 14 days, '
                      '5 of them NO)', rec['why'])
        self.assertEqual(PV.receptivity_report(), {'window_days': 14, 'minimum_verdicts': 5, 'yes': 0, 'partial': 1, 'no': 5,
                                                   'landings': 0.5, 'verdicts': 6, 'receptivity': 0.08})
        self.ledger([(1, 'YES')] * 2 + [(1, 'PARTIAL')] * 2 + [(1, 'NO')] * 2 + [(20, 'NO')] * 9)
        rec = PV.declare()
        self.assertIn('receptivity middling (0.5 = (2 YES + 0.5 x 2 PARTIAL) / 6 settled', rec['why'])
        self.ledger([(1, 'PARTIAL')] * 3)
        rec = PV.declare()
        self.assertIn('receptivity unknown (3 settled', rec['why']); self.assertIn('fewer than 5: 0 YES, 3 PARTIAL, 0 NO)', rec['why'])
        self.assertIsNone(PV.receptivity_report()['receptivity']); self.assertEqual(PV.receptivity_report()['landings'], 1.5)
        before = {p.name: p.read_bytes() for p in self.mem.iterdir() if p.is_file()}
        PV.receptivity_report()
        self.assertEqual({p.name: p.read_bytes() for p in self.mem.iterdir() if p.is_file()}, before)   # the report writes nothing

    # ---- round three, 10 November: the lead, what keeps failing, one lock ---------------------------------
    def test_emptied_leading_axis_hands_the_lead_to_a_declared_axis_or_to_none(self):
        self.low_receptivity()                                                 # self carries 0.6: it leads
        mine = dict(TARGET['self'], evidence_type='her_response', observation_window='her_next_reply')
        # the field's own criterion is abstained too: her axis is the one that is declared
        self.answers = [dict(self.target(drop=('observation_window',), gloria=copy.deepcopy(GLORIA)), **{'self': mine})] * 2
        t = self.select(resolve=False)
        self.assertEqual((t['lead_axis'], t['lead_fallback']), ('gloria', {'from': 'self', 'to': 'gloria'}))
        self.assertIn('My self axis is undeclared this turn; my gloria axis leads this move instead.', E.prompt_block(t))
        self.assertEqual((t['priority'], t['self'], t['gloria']), (LOW, {}, GLORIA))
        # nothing valid is left: no lead, and no pointer to a goal that is absent
        self.answers = [dict(self.target(drop=('observation_window',)), **{'self': mine})] * 2
        t = self.select(resolve=False)
        self.assertEqual((t['lead_axis'], t['lead_fallback']), (None, {'from': 'self', 'to': None}))
        self.assertIn('no axis leads this move', E.prompt_block(t))
        self.assertEqual((t['priority'], t['self'], t['gloria'], t['criterion_abstained']), (LOW, {}, {}, 'window_missing'))
        self.assertEqual(len(self.select_calls), 4)                            # one re-ask each, never a third call
        row = self.rows()[-1]
        self.assertEqual((row['realized']['field'], row['realized']['self']), ('NOT_DECLARED', 'NOT_DECLARED'))
        self.assertEqual(row['target']['lead_fallback'], {'from': 'self', 'to': None})
        # a leading axis that is declared leads, and the selector cannot name the lead itself
        self.answer = self.target(lead_axis='gloria', lead_fallback={'from': 'self', 'to': 'gloria'})
        t = self.select(resolve=False)
        self.assertEqual(t['lead_axis'], 'self'); self.assertNotIn('lead_fallback', t)
        self.assertNotIn('undeclared this turn', E.prompt_block(t))

    def keeps_failing(self):
        """What keeps failing, as the chat prompt reads it and as the selector is shown it (a preview: nothing moves)."""
        self.select(persist=False, step_campaign=False)
        return DD.pressure_block(), self.prompt()

    def test_keeps_failing_block_leaves_out_a_retired_row(self):
        self.press(**{A: self.prow(TEXT_A, 4.5, retired=True, retired_at=time.time()), B: self.prow(TEXT_B, 1.5)})
        block, prompt = self.keeps_failing()
        self.assertNotIn(TEXT_A, block); self.assertNotIn(TEXT_A, prompt)
        self.assertIn(TEXT_B, block); self.assertIn(block, prompt)             # the row the picker would pick is still an instruction
        self.press(**{A: self.pressure(A)})
        self.assertEqual(self.keeps_failing()[0], ''); self.assertNotIn('KEEP FAILING', self.prompt())

    def test_keeps_failing_block_leaves_out_a_graduated_closed_row(self):
        closed = self.prow(TEXT_A, 2.6, count=6, lineage=[{'graduated': time.time() - 7200, 'at_weight': 5.0}])
        self.press(**{A: closed, B: self.prow(TEXT_B, 1.2)})
        block, prompt = self.keeps_failing()
        self.assertNotIn(TEXT_A, block); self.assertNotIn(TEXT_A, prompt)
        self.assertIn(TEXT_B, block); self.assertIn(block, prompt)
        self.assertEqual(DD.her_words_reopen('So what is the plan for the weekend?'), [A])
        block, prompt = self.keeps_failing()                                   # she raised it: open, and an instruction again
        self.assertIn(TEXT_A, block); self.assertIn(block, prompt)

    def test_keeps_failing_block_leaves_out_a_resting_row(self):
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0)})
        self.assertIn(TEXT_A, self.keeps_failing()[0])
        for _ in range(3): self.turn(resolve=False)                            # A has led three turns: it rests
        block, prompt = self.keeps_failing()
        self.assertNotIn(TEXT_A, block); self.assertNotIn(TEXT_A, prompt)
        self.assertIn(TEXT_B, block); self.assertIn(block, prompt)
        for _ in range(3): self.turn(resolve=False)                            # B has led three: A is back, B rests
        block, prompt = self.keeps_failing()
        self.assertIn(TEXT_A, block); self.assertNotIn(TEXT_B, block); self.assertNotIn(TEXT_B, prompt)
        # the block and the picker are one rule: whatever stands in the block could be picked, and nothing else
        db = json.loads(Path(DD.PRESS).read_text())
        self.assertEqual([k for k, r in db.items() if r['text'] in block], [k for k, r in db.items() if DD.primary_eligible(k, r, DD._rotation())])

    def two_writers(self, mod, reader, write, locked):
        """Two processes, one whole write each. This one has read the state and not yet written it back when the
        other is let in. With no lock the other reads the same old value and finishes inside that gap; with the
        lock it can only wait there. The order is set by pipes and by waiting on the other process, not a clock."""
        go_r, go_w = os.pipe(); at_r, at_w = os.pipe(); me = os.getpid(); real = getattr(mod, reader); fired = []
        def read_then_let_the_other_in(*a, **k):
            out = real(*a, **k)
            if os.getpid() == me and not fired:
                fired.append(True); os.write(go_w, b'1'); os.read(at_r, 1)     # the other is at its own write now
                if locked:
                    for _ in range(10): time.sleep(0.05)                       # ... with time to reach the lock; it cannot pass it
                else:
                    os.waitpid(other, 0)                                       # ... and nothing holds it back
            return out
        with contextlib.ExitStack() as stack:
            if not locked: stack.enter_context(patch.object(mod, '_turn_state', lambda path: contextlib.nullcontext()))
            other = os.fork()                                                  # before any lock is taken: it inherits none
            if other == 0:
                try:
                    os.read(go_r, 1); os.write(at_w, b'1'); write()
                finally:
                    os._exit(0)
            with patch.object(mod, reader, read_then_let_the_other_in):
                write()
            if locked: os.waitpid(other, 0)
        for fd in (go_r, go_w, at_r, at_w): os.close(fd)
        self.assertEqual(fired, [True])

    @unittest.skipUnless(hasattr(os, 'fork'), 'two real processes are needed')
    def test_two_processes_lose_no_opportunity_count_under_the_lock(self):
        write = lambda: PV.note_selection(False, opportunity=True)
        self.two_writers(PV, '_jload', write, locked=False)
        self.assertEqual(PV.opportunity_report()['attempts'], 1)               # the control: with no lock one of the two is lost
        os.unlink(PV.STATE)
        self.two_writers(PV, '_jload', write, locked=True)
        report = PV.opportunity_report()
        self.assertEqual((report['attempts'], report['abstained']), (2, 2))
        self.assertEqual([f.name for f in self.mem.iterdir() if '.tmp' in f.name], [])

    @unittest.skipUnless(hasattr(os, 'fork'), 'two real processes are needed')
    def test_two_processes_lose_no_primary_run_under_the_lock(self):
        self.press(**{A: self.prow(TEXT_A, 4.0)})
        state = lambda: json.loads(Path(DD._rotation_path()).read_text())
        self.two_writers(DD, '_rotation', lambda: DD.primary_shown(A), locked=False)
        self.assertEqual(state()['run'], 1)                                    # the control: two showings, one counted
        os.unlink(DD._rotation_path())
        self.two_writers(DD, '_rotation', lambda: DD.primary_shown(A), locked=True)
        self.assertEqual(state()['run'], 2)
        self.two_writers(DD, '_rotation', lambda: DD.primary_shown(None), locked=True)   # a rest is served the same way: both turns count
        self.assertEqual(state()['run'], 0); self.assertEqual(state()['rest_turns'], {})
        os.unlink(DD._rotation_path()); DD.primary_shown(A); DD.primary_shown(A); DD.primary_shown(A)
        self.assertEqual(state()['rest_turns'], {A: 0})
        self.two_writers(DD, '_rotation', lambda: DD.primary_shown(None), locked=True)
        self.assertEqual(state()['rest_turns'], {A: 2})

    def test_a_missing_lock_is_written_through_aloud_and_a_failing_lock_stops_the_write(self):
        """Review, 10 November. store_guard ships beside these scripts; only an older one still loaded can lack
        the lock. Then the write goes through unlocked, counted and said once on stderr. A lock that is there
        and cannot be taken stops the write."""
        self.press(**{A: self.prow(TEXT_A, 4.0)})
        older = types.SimpleNamespace(**{k: v for k, v in vars(store_guard).items() if k != 'turn_state' and not k.startswith('__')})
        cases = ((DD, lambda: DD.primary_shown(A), lambda: json.loads(Path(DD._rotation_path()).read_text())['run']),
                 (PV, lambda: PV.note_selection(False, opportunity=True), lambda: PV.opportunity_report()['attempts']))
        for mod, write, seen in cases:
            count = {'n': 0}; err = io.StringIO()
            with patch.dict(sys.modules, {'store_guard': older}), patch.object(mod, '_UNLOCKED', count), contextlib.redirect_stderr(err):
                write(); write()
            self.assertEqual(seen(), 2, mod.__name__)                          # both writes happened
            self.assertEqual(count['n'], 2, mod.__name__)                      # ... each counted
            self.assertEqual(err.getvalue().count('writing UNLOCKED'), 1, mod.__name__)   # ... and said once
            self.assertIn(mod.__name__, err.getvalue())
        @contextlib.contextmanager
        def broken(path):
            raise OSError('fixture: the lock cannot be taken')
            yield
        for mod, write, seen in cases:
            count = {'n': 0}
            with patch.object(store_guard, 'turn_state', broken), patch.object(mod, '_UNLOCKED', count):
                with self.assertRaises(OSError): write()
            self.assertEqual(seen(), 2, mod.__name__)                          # nothing was written
            self.assertEqual(count['n'], 0, mod.__name__)                      # and it is not the unlocked path

    def test_every_writer_of_the_turn_state_takes_the_one_lock(self):
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0),
                      'cccc0003': self.prow(TEXT_A + ', again', 2.6, count=6, lineage=[{'graduated': time.time() - 7200, 'at_weight': 5.0}])})
        marker = self.mem / '.intent-required-consideration.json'
        one = str(self.mem / 'intent-turn-state'); asked = []; taken = []
        real_lock, real_transaction = store_guard.turn_state, store_guard.transaction
        def turn_state(path): asked.append(os.path.basename(path)); return real_lock(path)
        def transaction(path): taken.append(path); return real_transaction(path)
        def miss_on_an_addressed_row():
            self.answer = self.target(addresses=B); self.turn(resolve=False)
            del asked[:], taken[:]
            self.verdict = 'NO'; E.resolve_previous(HER)
            self.assertTrue(marker.exists())
        writers = [('priority-vector-state.json', lambda: PV.note_selection(False, opportunity=True)),
                   ('priority-vector-state.json', PV.declare),
                   ('intent-pressure.json', lambda: DD.primary_shown(A)),
                   ('intent-pressure.json', lambda: DD.bump(TEXT_B, 1.0, kind='field', addresses=B)),
                   ('intent-pressure.json', lambda: DD.relieve(TEXT_B, addresses=B, kind='field')),
                   ('intent-pressure.json', lambda: DD.override(TEXT_B, 'a synthetic reason', addresses=B, kind='field')),
                   ('intent-pressure.json', lambda: DD.her_words_reopen('So what is the plan for the weekend?')),
                   ('.intent-required-consideration.json', miss_on_an_addressed_row),                       # the marker, written
                   ('.intent-required-consideration.json', lambda: self.select(persist=False, step_campaign=False)),   # ... and read
                   ('intent-pressure.json', lambda: DD.retire(A)),
                   ('intent-pressure.json', lambda: DD.primary_reserve()),                                   # round four: the pick and its count
                   ('intent-pressure.json', lambda: DD.reservation_failed(B)),
                   ('.intent-required-consideration.json', lambda: self.select(resolve=False))]             # ... and the marker, consumed
        with patch.object(store_guard, 'turn_state', turn_state), patch.object(store_guard, 'transaction', transaction):
            for n, (store, write) in enumerate(writers):
                del asked[:], taken[:]; write()
                self.assertIn(store, asked, n); self.assertIn(one, taken, n)
        self.assertEqual({p for p in taken if 'turn-state' in p}, {one})
        self.assertEqual([p.name for p in self.mem.glob('*turn-state*')], ['intent-turn-state.lock'])

    # ---- round four (10 November): one accounting of her turns ------------------------------------------
    def device(self, n=0, **kw):
        """A device-only event at the selector: told by its source on odd counts, by its text on even ones."""
        return self.select(BUTTON, **dict(kw, **({'her_source': 'gcs'} if n % 2 else {})))

    def test_thirty_device_events_neither_use_a_primary_up_nor_walk_the_rotation(self):
        # A device event used to be shown the primary and to move the run, while it could discharge no rest:
        # thirty of them after A A A walked on through B and C and left her next turns with no primary at all.
        # It is no selection now: shown nothing, counted nowhere.
        C = 'cccc0003'
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0), C: self.prow('say what the evening is for', 1.5)})
        for _ in range(3): self.turn(resolve=False)
        rotation = Path(DD._rotation_path()).read_text(); cadence = PV.opportunity_report()
        for n in range(30):
            t = self.device(n, resolve=False)
            self.assertEqual((t['primary_shown'], t['primary_required'], t['primary_accounting'], t['her_turn']),
                             (None, False, 'not_eligible', False), n)
            for gone in ('PRIMARY DIFFERENCE', TEXT_A, TEXT_B): self.assertNotIn(gone, self.prompt(), n)
        self.assertEqual(Path(DD._rotation_path()).read_text(), rotation)      # the run and the rests stand where they stood
        self.assertEqual(PV.opportunity_report(), cadence)                     # ... and so does her cadence
        for _ in range(9): self.turn(resolve=False)
        hers = [r['target']['primary_shown'] for r in self.rows() if r['target']['her_turn']]
        self.assertEqual(hers[:6], [A] * 3 + [B] * 3); self.assertEqual(len(hers), 12)
        self.assertNotIn(None, hers)                                           # not one of her turns went without a primary
        report = DD.primary_report(60)
        self.assertEqual((report['turns'], report['with_primary'], report['max_run']), (12, 12, 3))

    def test_mixed_device_events_and_her_turns_keep_the_rotation_on_her_turns(self):
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0)})
        n = 0
        for i in range(12):
            for _ in range(i % 4):                                             # none, one, two or three device events before each of her turns
                self.device(n); n += 1                                         # resolved as a real turn is: it HOLDS the move before it
            self.turn(resolve=False)
        rows = self.rows(); hers = [r for r in rows if r['target']['her_turn']]
        self.assertEqual([r['target']['primary_shown'] for r in hers], ([A] * 3 + [B] * 3) * 2)
        self.assertEqual((n, len(rows) - len(hers)), (18, 18))
        self.assertEqual({(r['target']['primary_shown'], r['target']['primary_accounting']) for r in rows if not r['target']['her_turn']},
                         {(None, 'not_eligible')})
        # a HELD outcome on one of her turns is still a selection: a device event after it held it (every one
        # but the last, which nothing has followed), and it had counted
        held = [r for r in hers if r['realized']['field'] == 'HELD']
        self.assertEqual(len(held), 11); self.assertIsNone(hers[-1]['realized']['field']); self.assertEqual(self.judge_calls, [])
        self.assertEqual({r['target']['primary_accounting'] for r in held}, {'reserved'})
        self.assertEqual(json.loads(Path(DD._rotation_path()).read_text())['run'], 3)

    # ---- round four: the cap is kept where the primary is shown -----------------------------------------
    def two_turns_at_once(self):
        """Two of her turns picking at once, as two processes. This one has been given its primary and is at
        the model when the other is let in; the other then does a whole turn of its own - pick, model, record -
        and only when it has exited does this one's model answer. The order is set by pipes and by waiting on
        the other process, not by a clock. Returns the primary each was shown: (this one, the other)."""
        go_r, go_w = os.pipe(); out_r, out_w = os.pipe(); real = self.respond; done = []
        def at_the_model(req, timeout=None):
            if not done:
                os.write(go_w, b'1'); done.append(os.waitpid(other, 0)[1])     # the other's whole turn happens here
            return real(req, timeout)
        other = os.fork()                                                      # before any lock is taken: it inherits none
        if other == 0:
            try:
                signal.alarm(60)                                               # a lock held across the model would leave it waiting for good
                os.read(go_r, 1); t = self.select(resolve=False)
                os.write(out_w, json.dumps([t['primary_shown'], ('(id %s,' % t['primary_shown']) in self.prompt()]).encode())
                os._exit(0)
            finally:
                os._exit(1)
        with patch('urllib.request.urlopen', at_the_model):
            mine = self.select(resolve=False)
        os.close(out_w); theirs = json.loads(os.read(out_r, 200) or b'[null, false]')
        for fd in (go_r, go_w, out_r): os.close(fd)
        self.assertEqual(len(done), 1); self.assertTrue(os.WIFEXITED(done[0]) and os.WEXITSTATUS(done[0]) == 0, done)
        self.assertIn('(id %s,' % mine['primary_shown'], self.prompt()); self.assertTrue(theirs[1])   # each was shown what it was given
        return mine['primary_shown'], theirs[0]

    @unittest.skipUnless(hasattr(os, 'fork'), 'two real processes are needed')
    def test_two_turns_picking_at_once_cannot_both_take_the_last_showing(self):
        def two_shown_already():
            for path in (DD._rotation_path(), E.LEDGER):
                if os.path.exists(path): os.unlink(path)
            self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0)})
            for _ in range(2): self.select(resolve=False)                      # A A: one showing of its run is left
        # The control: the primary is picked when it is shown and not counted in the same step, as it was before.
        # Both turns are shown A - a fourth exposure.
        two_shown_already()
        with patch.object(DD, 'primary_reserve', lambda required=None, now=None: DD.primary_for_turn(required, now)):
            self.assertEqual(self.two_turns_at_once(), (A, A))
        # Reserved under the lock before it is shown: the second turn reads the run the first has already moved.
        two_shown_already()
        self.assertEqual(self.two_turns_at_once(), (A, B))
        self.assertEqual([p for p, _ in self.shown()], [A, A, B, A])           # the other recorded first; A was shown three times
        state = json.loads(Path(DD._rotation_path()).read_text())
        self.assertEqual((state['id'], state['run'], state['rest_turns']), (B, 1, {A: 1}))
        self.assertEqual({r['target']['primary_accounting'] for r in self.rows()}, {'reserved'})

    def test_turn_that_fails_after_its_reservation_has_still_used_the_showing(self):
        # The choice (round four): a reservation COUNTS. It is not handed back when the turn fails, so failing
        # turns cannot be used to pass the cap; the failure is recorded beside the rotation and in the log.
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0)})
        self.answer = 'no object at all'
        with self.assertRaises(Exception): self.select(resolve=False)
        # it had been shown; no target was recorded - only her turn, as a failure row with A on it (12 November)
        self.assertIn('(id %s,' % A, self.prompt())
        self.assertEqual([(r['status'], r['target']['primary_shown'], r['target']['primary_accounting']) for r in self.rows()],
                         [('failed', A, 'reserved')])
        state = json.loads(Path(DD._rotation_path()).read_text())
        self.assertEqual((state['id'], state['run'], state['failed_reservations'], state['last_failed_reservation']['id']), (A, 1, 1, A))
        log = Path(E.SELECT_LOG).read_text()
        self.assertEqual(log.count('primary_reserved_turn_failed: primary %s; ' % A), 1); self.assertNotIn('turn-state write', log)
        self.answer = self.target()
        for _ in range(3): self.select(resolve=False)
        self.assertEqual([p for p, _ in self.shown()], [A, A, A, B])           # three showings of A in all, the failed one among them
        state = json.loads(Path(DD._rotation_path()).read_text())
        self.assertEqual((state['id'], state['run'], state['failed_reservations']), (B, 1, 1))
        # a turn that fails with nothing reserved (a device event) records no such failure
        self.answer = 'no object at all'
        with self.assertRaises(Exception): self.device(1, resolve=False)
        self.assertEqual(json.loads(Path(DD._rotation_path()).read_text()), state)
        self.assertEqual(Path(E.SELECT_LOG).read_text().count('primary_reserved_turn_failed'), 1)

    # ---- round four: the lead is always a declared axis, or none ----------------------------------------
    def test_field_that_leads_with_its_criterion_abstained_hands_the_lead_on(self):
        # The field can be the heaviest axis and have its own criterion left unjudged; it then led with nothing
        # to lead with. The lead is normalised on every path: a validly declared axis or None, and what it left.
        emptied = dict(TARGET['self'], evidence_type='her_response', observation_window='her_next_reply')   # an invalid self axis
        cases = [({}, 'self'),                                                 # only my own axis is declared
                 ({'gloria': copy.deepcopy(GLORIA)}, 'gloria'),                # hers is the heavier of the two that are
                 ({'self': emptied}, None)]                                    # nothing is
        for over, to in cases:
            self.answers = [dict(self.target(drop=('observation_window',)), **over)] * 2
            t = self.select(resolve=False)
            self.assertEqual((t['priority'], t['criterion_abstained']), (MIDDLING, 'window_missing'), to)   # the field is the heaviest
            self.assertEqual((t['lead_axis'], t['lead_fallback']), (to, {'from': 'field', 'to': to}))
            self.assertIn("The field's criterion is left unjudged this turn" + ("; my %s axis leads this move instead." % to if to else
                          " and no other axis is declared: no axis leads this move."), E.prompt_block(t))
            if to: self.assertTrue(t[to].get('difference_intended') and t[to].get('enactment'), to)
            row = self.rows()[-1]
            self.assertEqual((row['target']['lead_axis'], row['target']['lead_fallback'], row['realized']['field']),
                             (to, {'from': 'field', 'to': to}, 'NOT_DECLARED'))
        self.answers = []; t = self.select(resolve=False)                      # its criterion declared: the field leads, and nothing is said
        self.assertEqual(t['lead_axis'], 'field'); self.assertNotIn('lead_fallback', t)
        self.assertNotIn('left unjudged', E.prompt_block(t))

    # ---- round four: the window runs from the delivery, and closes lazily everywhere --------------------
    def aged(self, hours, **more):
        """The newest row as it stands `hours` after it was delivered."""
        rows = self.rows(); rows[-1].update(more, delivered_at=(datetime.now() - timedelta(hours=hours, minutes=1)).isoformat())
        Path(E.LEDGER).write_text(json.dumps(rows))

    def test_window_runs_from_the_delivery_whatever_came_after_it(self):
        # The day used to run from the first skipped device event, so a row no event had touched never expired,
        # and each late event could be read as a fresh start. It runs from delivered_at (a row from before
        # deliveries were recorded: its timestamp), and is read before any grading. Any judge asked here says NO.
        closed = ({'field': 'HELD', 'gloria': 'HELD', 'self': 'HELD'}, {'her_reply_window_expired'})
        state = lambda row: (row['realized'], set(row['held_reason'].values()))
        # nothing followed for a day, not even a device event: her words then are not this move's next reply
        self.delivered(gloria=copy.deepcopy(GLORIA)); self.aged(E.DEVICE_WAIT_HOURS); E.resolve_previous(HER)
        self.assertEqual(state(self.rows()[-1]), closed); self.assertNotIn('skipped_observations', self.rows()[-1])
        # a device event late in the day opens no new day
        self.delivered(gloria=copy.deepcopy(GLORIA)); self.aged(E.DEVICE_WAIT_HOURS - 1); E.resolve_previous(BUTTON, source='gcs')
        row = self.rows()[-1]; self.assertIsNone(row['realized']['gloria']); skipped = row['skipped_observations']
        self.aged(E.DEVICE_WAIT_HOURS); E.resolve_previous(HER); row = self.rows()[-1]
        self.assertEqual((row['realized']['gloria'], row['held_reason']['gloria'], row['skipped_observations']),
                         ('HELD', 'her_reply_window_expired', skipped))
        # her reply was stored after the day had closed, and graded later still
        self.delivered(gloria=copy.deepcopy(GLORIA)); E.note_response(HER)
        self.assertIn('response_at', self.rows()[-1])
        self.aged(30, response_at=(datetime.now() - timedelta(hours=4)).isoformat()); E.resolve_previous()
        self.assertEqual(state(self.rows()[-1]), closed)
        # a row from before deliveries were recorded, three days old, with nothing to judge it on but my own reply
        Path(E.LEDGER).write_text(json.dumps(self.rows() + [{'intent_id': 'legacy', 'timestamp': ago(3), 'reply': 'a synthetic reply',
                                                             'target': {'enactment': 'a synthetic move'}}]))
        E.resolve_previous(HER); row = self.rows()[-1]
        self.assertEqual((row['intent_id'], row['realized'], row['held_reason']), ('legacy', 'HELD', {'single': 'her_reply_window_expired'}))
        # a row with no readable time at all cannot be shown inside its window
        Path(E.LEDGER).write_text(json.dumps(self.rows() + [{'intent_id': 'timeless', 'status': 'delivered', 'reply': 'a synthetic reply',
                                  'target': self.target(gloria=copy.deepcopy(GLORIA)), 'realized': {'field': None, 'gloria': None, 'self': None}}]))
        E.resolve_previous(HER)
        timeless = [r for r in self.rows() if r['intent_id'] == 'timeless'][0]; self.assertEqual(state(timeless), closed)
        # not one judge was asked, and a window that closed unobserved is never a NO
        self.assertEqual(self.judge_calls, []); self.assertNotIn('NO', json.dumps([r['realized'] for r in self.rows()]))
        self.assertEqual(PV._axis_history()['gloria']['n'], 0)
        # her reply that came inside the day is judged, however late the grading: when it came is what counts
        self.verdict = 'YES'; self.delivered(gloria=copy.deepcopy(GLORIA)); E.note_response(HER)
        self.aged(30, response_at=(datetime.now() - timedelta(hours=29)).isoformat()); E.resolve_previous()
        self.assertEqual(self.rows()[-1]['realized']['gloria'], 'YES'); self.assertTrue(self.judge_calls)
        self.assertEqual(PV._axis_history()['gloria'], {'YES': 1, 'PARTIAL': 0, 'NO': 0, 'n': 1})
        # ... and an old row still inside its day is graded as it always was
        calls = len(self.judge_calls)
        Path(E.LEDGER).write_text(json.dumps([{'intent_id': 'legacy', 'timestamp': ago(0, 30), 'reply': 'a synthetic reply',
                                               'target': {'enactment': 'a synthetic move'}}]))
        E.resolve_previous(HER); self.assertEqual((self.rows()[-1]['realized'], len(self.judge_calls) - calls), ('YES', 1))

    def test_reports_call_an_overdue_row_expired_coverage_never_pending_and_never_no(self):
        def row(key, hours, realized, **over):
            at = (datetime.now() - timedelta(hours=hours)).isoformat()
            return dict({'intent_id': key, 'status': 'delivered', 'timestamp': at, 'delivered_at': at, 'reply': 'a synthetic reply',
                         'target': {'goal': 'goal of ' + key, 'enactment': 'a synthetic move', 'field_state': 'state of ' + key,
                                    'primary_shown': A, 'gloria': copy.deepcopy(GLORIA)}, 'realized': realized}, **over)
        waits = {'field': 'HELD', 'gloria': None, 'self': 'NOT_DECLARED'}; nothing = {'field': None, 'gloria': None, 'self': None}
        rows = [row('settled', 72, {'field': 'HELD', 'gloria': 'NO', 'self': 'NOT_DECLARED'}),
                row('closed', 60, {'field': 'HELD', 'gloria': 'HELD', 'self': 'NOT_DECLARED'},
                    held_reason={'field': 'device_event_only', 'gloria': 'her_reply_window_expired'}),   # expired when it was last graded
                row('overdue', 30, dict(waits)),                               # its day is over; nothing has come to grade it since
                row('prepared', 2, None, status='selected'),                   # never became a turn: it awaits nothing
                row('unseen', 40, dict(nothing)),
                row('open', 3, dict(nothing)),
                row('pending', 1, dict(waits))]
        Path(E.LEDGER).write_text(json.dumps(rows)); before = Path(E.LEDGER).read_text()
        self.assertEqual([E.row_coverage(r) for r in rows],
                         ['settled', 'expired_coverage', 'expired_coverage', 'undelivered', 'expired_coverage', 'pending', 'pending'])
        self.assertEqual((E.row_coverage(rows[1], axis='field'), E.row_coverage(rows[1], axis='gloria')), ('settled', 'expired_coverage'))
        self.assertEqual((E.row_coverage(rows[2], axis='field'), E.row_coverage(rows[2], axis='gloria')), ('settled', 'expired_coverage'))
        self.assertEqual(E.row_coverage(rows[6], now=time.time() + 2 * 86400), 'expired_coverage')   # the same row, read two days on
        report = DD.primary_report(30)
        self.assertEqual((report['turns'], report['pending'], report['expired_coverage']), (7, 2, 3))
        self.assertEqual(PV.opportunity_report(coverage=True)['gloria_axis'], {'settled': 1, 'pending': 2, 'expired_coverage': 3})
        self.assertEqual([f['verdict'] for f in DD.map_summary()['axis_field']], ['open', 'expired_coverage', 'open', 'HELD'])
        said = E._attempt_context()
        self.assertEqual(said.count('"gloria": "expired_coverage"'), 1)        # the overdue row; the pending one is left as it is
        self.assertIn('"outcome": {"field": "HELD", "gloria": null, "self": "NOT_DECLARED"}', said)
        # the one verdict there is stays the only one counted: expired coverage is no NO on any axis
        self.assertEqual(PV._axis_history()['gloria'], {'YES': 0, 'PARTIAL': 0, 'NO': 1, 'n': 1})
        self.assertEqual(Path(E.LEDGER).read_text(), before)                   # reading is all a report does: there is no sweeper

    # ---- round four: a landing that came after the cursor is seeded once --------------------------------
    def lead_trials(self):
        """lead_trials with the stores its feeder reads and writes in the scratch home, and its model a stub."""
        import lead_trials as LT
        asked = []
        def ask(prompt, mt=200):
            asked.append(prompt)
            return json.dumps({'kind': 'PARTICULAR', 'ground': ''} if 'goal of single' in prompt else {'kind': 'GENERAL', 'ground': 'ground %d' % len(asked)})
        for key, name in (('MEM', ''), ('SEEDS', 'lead-evolutions.json'), ('SEEDSTATE', '.lead-seed-state.json')):
            self.stack.enter_context(patch.object(LT, key, str(self.mem / name) if name else str(self.mem)))
            self.assertTrue(Path(getattr(LT, key)).is_relative_to(self.home), key)
        self.stack.enter_context(patch.object(LT, 'ask', ask))
        return LT, asked

    def test_landing_that_comes_after_the_cursor_passed_is_seeded_exactly_once(self):
        # The feeder's cursor passed a row whose verdict was still to come, and a YES that came later was never
        # seeded. Unsettled rows are now kept beside the cursor until they are decided - once.
        LT, asked = self.lead_trials()
        def row(key, minutes, realized, **over):
            at = ago(0, minutes)
            return dict({'intent_id': key, 'status': 'delivered', 'timestamp': at, 'delivered_at': at, 'reply': 'a synthetic reply',
                         'target': {'goal': 'goal of ' + key, 'enactment': 'a synthetic move',
                                    'gloria': {'difference_intended': 'hers in ' + key, 'enactment': 'a synthetic move'}},
                         'realized': realized}, **over)
        def feed(times=1):
            Path(E.LEDGER).write_text(json.dumps(rows))
            with contextlib.redirect_stdout(io.StringIO()):
                for _ in range(times): LT.seed_from_intents()
            state = json.loads(Path(LT.SEEDSTATE).read_text())
            return [s['led'] for s in json.loads(Path(LT.SEEDS).read_text())], state['pending'], state['last_ts'], len(asked)
        waits = {'field': 'HELD', 'gloria': None, 'self': 'NOT_DECLARED'}
        rows = [row('landed', 50, {'field': 'YES', 'gloria': 'NO', 'self': 'NOT_DECLARED'}),
                row('waiting', 40, dict(waits)),                               # her reply is still to come
                row('missed', 30, {'field': 'NO', 'gloria': 'NO', 'self': 'NOT_DECLARED'}),
                row('unjudged', 20, None),
                row('single', 15, {'field': 'YES', 'gloria': 'NO', 'self': 'NOT_DECLARED'}),   # landed, and too particular to lead on again
                row('newest', 10, {'field': 'NO', 'gloria': 'HELD', 'self': 'NOT_DECLARED'})]
        landed = ['goal of landed']
        self.assertEqual(feed(), (landed, ['waiting', 'unjudged'], rows[-1]['timestamp'], 2))   # the cursor is past all six
        self.assertEqual(feed(3), (landed, ['waiting', 'unjudged'], rows[-1]['timestamp'], 2))  # again and again: nothing twice
        # her reply settles the two the cursor had passed, and a new move is waiting
        rows[1]['realized']['gloria'] = 'YES'; rows[3]['realized'] = {'field': 'YES', 'gloria': 'NOT_DECLARED', 'self': 'NOT_DECLARED'}
        rows.append(row('later', 5, dict(waits)))
        landed += ['hers in waiting', 'goal of unjudged']
        self.assertEqual(feed(), (landed, ['later'], rows[-1]['timestamp'], 4))                 # neither is lost
        self.assertEqual(feed(3), (landed, ['later'], rows[-1]['timestamp'], 4))                # ... and neither is seeded twice
        # a row whose window closed unobserved is let go, and never seeds - whatever is written on it afterwards
        rows[-1]['delivered_at'] = ago(2)
        self.assertEqual(feed(), (landed, [], rows[-1]['timestamp'], 4))
        rows[-1]['realized'] = {'field': 'HELD', 'gloria': 'HELD', 'self': 'NOT_DECLARED'}; rows[-1]['held_reason'] = {'gloria': 'her_reply_window_expired'}
        rows.append(row('stale', 2, {'field': None, 'gloria': None, 'self': None}, delivered_at=ago(3)))   # met already overdue
        rows.append(row('prepared', 1, None, status='selected'))                                         # never became a turn
        self.assertEqual(feed(2), (landed, [], rows[-1]['timestamp'], 4))
        self.assertEqual([s['status'] for s in json.loads(Path(LT.SEEDS).read_text())], ['awaiting_statement'] * 3)

    # ---- round four: a swallowed locking error is never passed off as a protected update ----------------
    @contextlib.contextmanager
    def faulty(self, lock=None, guard=None, older=False):
        """The turn-state writers with a lock that cannot be taken (`lock`), a store guard that refuses
        (`guard`), or an older store_guard that has no turn-state lock at all (`older`). Yields what the engine
        counted, what the store's own writer counted, and what was said on stderr."""
        @contextlib.contextmanager
        def broken(path):
            raise lock
            yield
        faults = {'failed': 0, 'unprotected': 0}; unguarded = {'n': 0, 'failed': 0}; err = io.StringIO()
        with contextlib.ExitStack() as stack:
            for mod, key, value in ((E, 'TURN_STATE_FAULTS', faults), (DD, '_UNGUARDED', unguarded), (DD, '_UNLOCKED', {'n': 0}), (PV, '_UNLOCKED', {'n': 0})):
                stack.enter_context(patch.object(mod, key, value))
            if lock: stack.enter_context(patch.object(store_guard, 'turn_state', broken))
            if guard is not None: stack.enter_context(patch.object(DD, '_sg_write', return_value=guard))
            if older:
                stack.enter_context(patch.dict(sys.modules, {'store_guard': types.SimpleNamespace(
                    **{k: v for k, v in vars(store_guard).items() if k != 'turn_state' and not k.startswith('__')})}))
            stack.enter_context(contextlib.redirect_stderr(err))
            yield faults, unguarded, err

    def test_selection_says_which_of_its_turn_state_writes_failed_or_went_unprotected(self):
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0)})
        said = lambda t: [(f['site'], f['result']) for f in t.get('turn_state_faults', [])]
        log = lambda: Path(E.SELECT_LOG).read_text() if os.path.exists(E.SELECT_LOG) else ''
        # a clean turn says nothing, on the target or in the log
        with self.faulty() as (faults, unguarded, err):
            t = self.select(resolve=False)
        self.assertEqual((t['primary_shown'], t['primary_accounting'], 'turn_state_faults' in t), (A, 'reserved', False))
        self.assertEqual((faults, unguarded, log()), ({'failed': 0, 'unprotected': 0}, {'n': 0, 'failed': 0}, ''))
        rotation = Path(DD._rotation_path()).read_text()
        # the lock cannot be taken: every write behind it FAILED, each is named, and no primary is shown
        with self.faulty(lock=OSError('fixture: the lock cannot be taken')) as (faults, unguarded, err):
            t = self.select(resolve=False)
        sites = ['her_words_reopen', 'primary_reserve', 'priority_vector.declare', 'note_selection']
        self.assertEqual((t['primary_shown'], t['primary_accounting'], said(t)), (None, 'failed', [(s, 'failed') for s in sites]))
        self.assertEqual(faults, {'failed': 4, 'unprotected': 0}); self.assertNotIn('PRIMARY DIFFERENCE', self.prompt())
        self.assertEqual(Path(DD._rotation_path()).read_text(), rotation)      # nothing was counted, and nothing says it was
        for site in sites:
            self.assertEqual(log().count('turn-state write FAILED at %s: OSError: fixture: the lock cannot be taken' % site), 1, site)
        row = self.rows()[-1]['target']                                         # the row, written before the last of them, has the first three
        self.assertEqual((row['primary_shown'], row['primary_accounting'], said(row)), (None, 'failed', [(s, 'failed') for s in sites[:3]]))
        # an older store_guard with no turn-state lock: the writes are made, and said to be UNPROTECTED
        with self.faulty(older=True) as (faults, unguarded, err):
            t = self.select(resolve=False)
        sites = ['her_words_reopen', 'primary_reserve', 'note_selection']
        self.assertEqual((t['primary_shown'], t['primary_accounting'], said(t)), (A, 'reserved_unprotected', [(s, 'unprotected') for s in sites]))
        self.assertEqual(faults, {'failed': 0, 'unprotected': 3})
        self.assertEqual(log().count('turn-state write UNPROTECTED at primary_reserve: lock or store guard unavailable'), 1)
        self.assertIn('writing UNLOCKED', err.getvalue())
        self.assertEqual(json.loads(Path(DD._rotation_path()).read_text())['run'], 2)   # it was written all the same
        # the store guard refuses: the plain write that follows it is counted and said, not passed off as guarded
        with self.faulty(guard=False) as (faults, unguarded, err):
            t = self.select(resolve=False)
        self.assertEqual((t['primary_shown'], t['primary_accounting'], said(t)), (A, 'reserved_unprotected', [('primary_reserve', 'unprotected')]))
        self.assertEqual((faults, unguarded), ({'failed': 0, 'unprotected': 1}, {'n': 1, 'failed': 0}))
        self.assertIn('[desired_difference] store guard failed for intent-primary-rotation.json: written UNPROTECTED, 1 unprotected and 0 failed so far',
                      err.getvalue())
        self.assertEqual(json.loads(Path(DD._rotation_path()).read_text())['run'], 3)
        # ... and when that plain write cannot be made either, the count was never taken: nothing is shown
        rotation = Path(DD._rotation_path()).read_text(); os.unlink(DD._rotation_path()); os.mkdir(DD._rotation_path())
        with self.faulty(guard=False) as (faults, unguarded, err):
            t = self.select(resolve=False)
            self.assertEqual((DD._jsave(str(self.mem / 'gone' / 'x.json'), {}), unguarded), (False, {'n': 0, 'failed': 2}))
        os.rmdir(DD._rotation_path()); Path(DD._rotation_path()).write_text(rotation)
        self.assertEqual((t['primary_shown'], t['primary_accounting'], said(t)), (None, 'failed', [('primary_reserve', 'failed')]))
        self.assertEqual(faults, {'failed': 1, 'unprotected': 0}); self.assertNotIn('PRIMARY DIFFERENCE', self.prompt())
        self.assertIn('store guard failed for intent-primary-rotation.json: write FAILED (IsADirectoryError), 0 unprotected and 1 failed so far',
                      err.getvalue())
        self.assertEqual(log().count('turn-state write FAILED at primary_reserve: lock or store guard unavailable'), 1)
        self.assertTrue(DD._jsave(str(self.mem / 'x.json'), {}))               # a write through the guard is the only one called protected
        # the turns after it are whole again: the fourth of her turns in this run moves on to B
        t = self.select(resolve=False); self.assertEqual((t['primary_shown'], 'turn_state_faults' in t), (B, False))

    def test_resolver_and_retire_say_when_a_turn_state_write_did_not_happen(self):
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0)})
        marker = self.mem / '.intent-required-consideration.json'
        self.answer = self.target(addresses=B); self.verdict = 'NO'
        # with the lock working, the missed move is counted on its pressure and the consideration is required
        self.turn(resolve=False)
        with self.faulty() as (faults, unguarded, err):
            E.resolve_previous(HER)
        self.assertEqual((self.rows()[-1]['realized']['field'], faults, os.path.exists(E.SELECT_LOG), marker.exists()),
                         ('NO', {'failed': 0, 'unprotected': 0}, False, True))
        marker.unlink()
        # with a lock that cannot be taken the verdict still stands on the row, and both writes are said to have FAILED
        self.turn(resolve=False); counted = self.pressure(B)
        with self.faulty(lock=OSError('fixture: the lock cannot be taken')) as (faults, unguarded, err):
            E.resolve_previous(HER)
        self.assertEqual((self.rows()[-1]['realized']['field'], faults), ('NO', {'failed': 2, 'unprotected': 0}))
        log = Path(E.SELECT_LOG).read_text()
        for site in ('field_verdict', 'required_consideration.write'):
            self.assertEqual(log.count('turn-state write FAILED at %s: OSError: fixture: the lock cannot be taken' % site), 1, site)
        self.assertFalse(marker.exists()); self.assertEqual(self.pressure(B), counted)   # neither happened, and neither is said to have
        # retiring a difference whose required-consideration marker cannot be cleared says so
        marker.write_text(json.dumps({'id': A})); err = io.StringIO()
        with patch('os.remove', side_effect=OSError('fixture')), contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            DD.retire(A)
        self.assertIn('[desired_difference] retire %s: clearing the required-consideration marker FAILED (OSError)' % A, err.getvalue())
        self.assertTrue(marker.exists()); self.assertTrue(self.pressure(A)['retired'])


    # ---- round four, review: what the reservation leaves behind when it is not whole --------------------
    def test_required_consideration_is_consumed_only_once_its_count_is_written(self):
        # The marker used to be removed before the count was made: a count that was then lost took the
        # required consideration with it, shown to no one.
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0)})
        marker = self.mem / '.intent-required-consideration.json'; marker.write_text(json.dumps({'id': B}))
        said = lambda t: [(f['site'], f['result']) for f in t.get('turn_state_faults', [])]
        os.mkdir(DD._rotation_path())                                          # the count cannot be written
        with self.faulty(guard=False) as (faults, unguarded, err):
            t = self.select(resolve=False)
        os.rmdir(DD._rotation_path())
        self.assertEqual((t['primary_shown'], t['primary_accounting'], said(t)), (None, 'failed', [('primary_reserve', 'failed')]))
        self.assertEqual(json.loads(marker.read_text()), {'id': B})            # it stands for her next turn
        with self.faulty(lock=OSError('fixture: the lock cannot be taken')) as (faults, unguarded, err):
            t = self.select(resolve=False)
        self.assertEqual((t['primary_shown'], t['primary_accounting']), (None, 'failed')); self.assertTrue(marker.exists())
        # a marker that cannot be cleared after a written count: the showing stands, and the failure is named
        real_remove = os.remove
        def remove(path, *a, **k):
            if str(path) == str(marker): raise OSError('fixture: the marker cannot be cleared')
            return real_remove(path, *a, **k)
        with patch('os.remove', remove):
            t = self.select(resolve=False)
        self.assertEqual((t['primary_shown'], t['primary_required'], t['primary_accounting'], said(t)),
                         (B, True, 'reserved', [('required_consideration.consume', 'failed')]))
        self.assertTrue(marker.exists())
        # her next turn: the same row is not required twice running, and the marker goes with that turn's count
        t = self.select(resolve=False)
        self.assertEqual((t['primary_shown'], t['primary_required'], t['primary_accounting'], said(t)), (A, False, 'reserved', []))
        self.assertFalse(marker.exists())
        self.assertEqual([p for p, _ in self.shown()], [None, None, B, A])

    def test_error_swallowed_around_the_resolver_is_not_called_a_lock_fault(self):
        self.press(**{A: self.prow(TEXT_A, 4.0)})
        said = lambda t: [(f['site'], f['result']) for f in t.get('turn_state_faults', [])]
        with self.faulty() as (faults, unguarded, err):
            with patch.object(E, 'resolve_previous', side_effect=ValueError('fixture: nothing to do with a lock')):
                t = self.select()
        self.assertEqual((t['primary_shown'], t['primary_accounting'], said(t)), (A, 'reserved', [('resolve_previous', 'error')]))
        self.assertEqual(faults, {'failed': 0, 'unprotected': 0, 'error': 1})
        log = Path(E.SELECT_LOG).read_text()
        self.assertEqual(log.count('resolver ERROR at resolve_previous: ValueError: fixture: nothing to do with a lock'), 1)
        self.assertNotIn('turn-state write', log)
        # ... nor is one around an earlier waiting row; the latest move is still resolved after it
        os.unlink(E.SELECT_LOG)
        self.delivered(gloria=copy.deepcopy(GLORIA)); E.resolve_previous(BUTTON, source='gcs')
        self.delivered(gloria=copy.deepcopy(GLORIA)); real = E._resolve_row; seen = []
        def resolve_row(row, *a, **k):
            seen.append(row['intent_id'])
            if len(seen) == 1: raise KeyError('fixture')
            return real(row, *a, **k)
        self.verdict = 'YES'
        with self.faulty() as (faults, unguarded, err), patch.object(E, '_resolve_row', resolve_row):
            E.resolve_previous(HER)
        self.assertEqual((len(seen), faults), (2, {'failed': 0, 'unprotected': 0, 'error': 1}))
        log = Path(E.SELECT_LOG).read_text()
        self.assertEqual(log.count("resolver ERROR at resolve_previous.waiting_row: KeyError: 'fixture'"), 1)
        self.assertNotIn('turn-state write', log); self.assertEqual(self.rows()[-1]['realized']['gloria'], 'YES')

    # ---- round four, review: a lead prepared in a preview is looked at again when it is admitted --------
    def preview(self):
        with PV.background():
            return self.select(persist=False, step_campaign=False)

    def admit(self, prepared, event):
        return E.record_pending(prepared, source='voice', event_id=event, claim_once=True)

    def test_previewed_lead_cannot_be_admitted_as_a_fourth_showing(self):
        self.press(**{A: self.prow(TEXT_A, 4.0), B: self.prow(TEXT_B, 2.0)})
        rotation = lambda: json.loads(Path(DD._rotation_path()).read_text())
        for _ in range(2): self.select(resolve=False)                          # A A: one showing of its run is left
        prepared = self.preview()                                              # the voice lead is prepared on it ...
        self.assertEqual((prepared['primary_shown'], prepared['her_turn'], 'primary_accounting' in prepared), (A, False, False))
        self.assertEqual(self.select(resolve=False)['primary_shown'], A)       # ... and a turn of hers takes it
        before = Path(DD._rotation_path()).read_text(); rows = len(self.rows())
        # The control: counted without being looked at again, as it was - admitted, a fourth showing of A.
        with patch.object(DD, 'primary_admit', lambda pid, required=False, now=None, her_turn=False: bool(DD.primary_shown(pid, required, now, her_turn=her_turn))):
            self.assertTrue(self.admit(copy.deepcopy(prepared), 'control'))
        self.assertEqual([p for p, _ in self.shown()], [A] * 4)
        Path(E.LEDGER).write_text(json.dumps(self.rows()[:-1])); Path(DD._rotation_path()).write_text(before)
        # Looked at again under the lock: A is resting now, so nothing is admitted and nothing is counted.
        self.assertFalse(self.admit(copy.deepcopy(prepared), 'event-one'))
        self.assertEqual((len(self.rows()), Path(DD._rotation_path()).read_text()), (rows, before))
        self.assertEqual(Path(E.SELECT_LOG).read_text().count('primary_admission_refused: primary %s; not_eligible_now' % A), 1)
        # the next preview is prepared on what may be shown, and is admitted and counted once
        prepared = self.preview(); self.assertEqual(prepared['primary_shown'], B)
        as_published = copy.deepcopy(prepared); self.assertTrue(as_published['intent_id'])   # what every voice event reads back
        self.assertTrue(self.admit(prepared, 'event-two'))
        row = self.rows()[-1]
        self.assertEqual((row['surface'], row['target']['primary_shown'], row['target']['primary_accounting'], row['target']['her_turn']),
                         ('voice', B, 'admitted', False))
        state = rotation(); self.assertEqual((state['id'], state['run'], state['rest_turns']), (B, 1, {A: 0}))   # no rest served by it
        self.assertFalse(self.admit(as_published, 'event-three'))             # the same lead again: claimed once, counted once
        self.assertEqual((rotation()['run'], len(self.rows())), (1, rows + 1))
        # a count that cannot be written admits nothing either
        prepared = self.preview(); before = Path(DD._rotation_path()).read_text()
        with self.faulty(lock=OSError('fixture: the lock cannot be taken')) as (faults, unguarded, err):
            self.assertFalse(self.admit(prepared, 'event-four'))
        self.assertEqual((len(self.rows()), Path(DD._rotation_path()).read_text(), faults['failed']), (rows + 1, before, 1))
        self.assertEqual(Path(E.SELECT_LOG).read_text().count('primary_admission_refused: primary %s; count_not_written' % B), 1)
        # a prepared lead with no primary is admitted, counted as a turn with none
        self.press(**{A: self.prow(TEXT_A, 0.2)})
        prepared = self.preview(); self.assertIsNone(prepared['primary_shown'])
        self.assertTrue(self.admit(prepared, 'event-five')); self.assertEqual(self.rows()[-1]['target']['primary_accounting'], 'admitted')
        self.assertEqual((rotation()['id'], rotation()['run']), (None, 0))
        # ... and is still admitted when that count cannot be written: nothing was shown, so there is nothing to cap
        prepared = self.preview(); self.assertIsNone(prepared['primary_shown']); n = len(self.rows())
        with self.faulty(lock=OSError('fixture: the lock cannot be taken')) as (faults, unguarded, err):
            self.assertTrue(self.admit(prepared, 'event-six'))
            self.assertEqual(faults['failed'], 1)
        self.assertEqual((len(self.rows()), self.rows()[-1]['target']['primary_accounting']), (n + 1, 'failed'))
        self.assertEqual(Path(E.SELECT_LOG).read_text().count('primary_admission_refused: primary None'), 0)

    def test_rows_the_bounded_pending_list_lets_go_are_counted(self):
        LT, asked = self.lead_trials()
        def row(key, minutes):
            at = ago(0, minutes)
            return {'intent_id': key, 'status': 'delivered', 'timestamp': at, 'delivered_at': at, 'reply': 'a synthetic reply',
                    'target': {'goal': 'goal of ' + key, 'enactment': 'a synthetic move'},
                    'realized': {'field': None, 'gloria': 'NOT_DECLARED', 'self': 'NOT_DECLARED'}}
        rows = [row('w%d' % i, 50 - i) for i in range(5)]
        def feed():
            Path(E.LEDGER).write_text(json.dumps(rows)); out = io.StringIO()
            with contextlib.redirect_stdout(out): LT.seed_from_intents()
            state = json.loads(Path(LT.SEEDSTATE).read_text())
            return state['pending'], state.get('pending_dropped', 0), out.getvalue()
        self.assertEqual(feed()[:2], (['w0', 'w1', 'w2', 'w3', 'w4'], 0))         # under the bound: nothing is let go
        with patch.object(LT, 'PENDING_MAX', 3):
            pending, dropped, out = feed()
            self.assertEqual((pending, dropped), (['w2', 'w3', 'w4'], 2))
            self.assertIn('[lead] 2 unsettled rows left the bounded pending list unseeded (2 so far)', out)
            for r in rows: r['realized']['field'] = 'YES'                      # all five land afterwards
            pending, dropped, out = feed()
        self.assertEqual((pending, dropped, len(asked)), ([], 2, 3))           # the two let go are not seeded, and are counted
        self.assertEqual(len(json.loads(Path(LT.SEEDS).read_text())), 3)


if __name__ == '__main__':
    unittest.main()

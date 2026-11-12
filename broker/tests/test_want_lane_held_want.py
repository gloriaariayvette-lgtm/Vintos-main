#!/usr/bin/env python3
"""One blocked want holds only itself. On 10 November one bound want at its per-want call cap raised WorkBlocked
out of agent_wants_pass on every pass, so no other want was answered and three adopted email promises sat queued,
never handed to an agent. Now a want's own block (per_want_call_cap, attempt_already_reserved, ...) marks that want
held, visibly and counted, notified through notify_block, and the pass goes on to the other wants and the handoff.
The day's call cap stops calls, not the lane; the stop file still stops everything; a want held on its block for
ADOPT_ANSWER_HOURS gives its adoption and room places back.

Synthetic wants in a scratch workspace; the working model and Slack are stubs; every socket is refused."""
from contextlib import ExitStack
import json, os, socket, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
def _no(self, *a, **k): raise OSError('this suite reaches nothing')
socket.socket.connect = _no
import want_agent as A
import want_working_thread as W
import dot_channel as D
import room_work
from want_work_budget import WorkBlocked
from journal_wants import source_receipt


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='want-lane-held-'); self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name).resolve(); self.mem = self.ws / 'memory'; self.mem.mkdir()
        stack = ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, SPARK_WORKSPACE=str(self.ws)))
        self.now = 2000000000.0
        stuck = dict(id='stuck', want='I want to run the synthetic parser check on fixture A and export the table.',
                     source='idle-journal', journal_seeded=True, timestamp='2026-11-09T20:02:00', fulfilled=False)
        stuck.update(source_receipt('journal', 'fixture-journal-a', stuck['want']))
        stuck['agent_work'] = dict(request_id='WA-' + 'a' * 24, goal_sha256=A.fingerprint(stuck['want']), status='in_work',
                                   thread='1999990000.000100', agent='dot', work_id='RW-stuck001', created_at=self.now - 90000)
        queued = dict(id='ec-fixture1', want='I want to run the synthetic lattice script on fixture B and export the column.',
                      source='email', timestamp='2026-11-10T11:24:00', fulfilled=False, adopted_from='EC-fixture1',
                      timer_bypass=True, done_when='the exported column file')
        queued.update(source_receipt('email', 'fixture-mail-1', queued['want']))
        queued['source_refs'].append({'kind': 'commitment', 'id': 'EC-fixture1'})
        self.rows = [stuck, queued]
        self.write('current-wants.json', self.rows); self.write('fulfilled-wants.json', [])
        self.state = {'room_work': {'open': [dict(id='RW-stuck001', goal=stuck['want'], opened=self.now, touched=self.now,
                                                   asks=[], returns=[], steps=[], by='want', want_id='stuck',
                                                   want_request_id=stuck['agent_work']['request_id'])], 'history': []}}
        self.block = {'stuck': 'per_want_call_cap'}
        self.generated = []; self.notices = []; self.posts = []
        def generate(w, work, ws, phase, trigger, instruction, writer=None, identity=None):
            reason = self.block.get(w['id'])
            if reason: raise WorkBlocked(reason)
            self.generated.append((w['id'], phase)); return {'message': 'Synthetic plan for %s.' % w['id'], 'accept': False}
        def notify_block(w, work, ws, reason, sender, **kw): self.notices.append((w['id'], reason))
        for obj, name, value in (
                (W, 'generate', generate), (W, 'notify_block', notify_block), (W, 'ingest', lambda *a, **k: None),
                (W, 'load', lambda *a, **k: {'events': [], 'generations': {}}), (W, 'append', lambda *a, **k: None),
                (W, 'answered', lambda *a, **k: None),
                (W, 'unanswered', lambda w, work, ws: [{'key': 'agent:fixture-1'}] if w['id'] == 'stuck' else []),
                (W, 'binding', lambda w, state, *a, **k: {'id': (w.get('agent_work') or {}).get('work_id') or 'RW-x'}
                                                 if (w.get('agent_work') or {}).get('thread') else None),
                (A, 'receive', lambda rows, **k: []), (A, 'finish', lambda *a, **k: []),
                (D, 'STATE', str(self.mem / 'room.json')), (D, '_guarded', lambda s: [])):
            stack.enter_context(patch.object(obj, name, value))

    def write(self, name, value): (self.mem / name).write_text(json.dumps(value))
    def current(self): return {w['id']: w for w in json.loads((self.mem / 'current-wants.json').read_text())}
    def api(self, method, payload):
        self.assertEqual(method, 'chat.postMessage'); self.posts.append(payload)
        return {'ok': True, 'ts': '%.6f' % (self.now + len(self.posts))}
    def run_pass(self, now=None):
        return D.agent_wants_pass(self.api, 'fixture-channel', 'fixture-dot', self.state, now or self.now,
                                  block_notify=lambda key, message: {'state': 'sent'}, identity=lambda: 'Synthetic identity')

    def test_cap_holds_that_want_and_the_queued_promise_is_handed_over(self):
        lines = self.run_pass()
        rows = self.current()
        self.assertEqual(rows['stuck']['agent_work']['blocked']['reason'], 'per_want_call_cap')
        self.assertEqual(rows['stuck']['agent_work']['blocked']['passes'], 1)
        self.assertTrue(any('stuck held: per_want_call_cap' in l for l in lines), lines)
        self.assertIn(('stuck', 'per_want_call_cap'), self.notices)
        self.assertTrue(any('handed to its agent' in l for l in lines), lines)
        self.assertEqual(rows['ec-fixture1']['agent_work']['status'], 'in_work')
        self.assertTrue(rows['ec-fixture1']['agent_work']['thread'])
        self.assertEqual(self.generated, [('ec-fixture1', 'opening')])
        self.run_pass(self.now + 420)
        self.assertEqual(self.current()['stuck']['agent_work']['blocked']['passes'], 2)

    def test_wants_held_before_any_call_do_not_use_up_the_pass(self):
        # review: two wants held on a block raised before any call, met first every pass, must not use both of the
        # pass's working calls; the queued promise is still prepared and handed over
        other = json.loads(json.dumps(self.rows[0])); other['id'] = 'stuck2'
        other['agent_work'].update(request_id='WA-' + 'c' * 24, work_id='RW-stuck002')
        self.write('current-wants.json', [self.rows[0], other, self.rows[1]])
        self.state['room_work']['open'].append(dict(self.state['room_work']['open'][0], id='RW-stuck002', want_id='stuck2',
                                                    want_request_id=other['agent_work']['request_id']))
        for reason in ('context_needs_continuation', 'provider_retry_backoff', 'working_call_already_recorded',
                       'interrupted_call_needs_review'):
            with self.subTest(reason=reason):
                self.block = {'stuck': reason, 'stuck2': reason}; self.generated = []; self.posts = []
                rows = self.current(); rows['ec-fixture1'].pop('agent_work', None)
                self.write('current-wants.json', list(rows.values()))
                with patch.object(W, 'unanswered', lambda w, work, ws: [{'key': 'agent:fixture-1'}] if w['id'].startswith('stuck') else []):
                    lines = self.run_pass()
                self.assertEqual(self.generated, [('ec-fixture1', 'opening')], lines)
                self.assertTrue(any('handed to its agent' in l for l in lines), lines)

    def _two_stuck(self):
        other = json.loads(json.dumps(self.rows[0])); other['id'] = 'stuck2'
        other['agent_work'].update(request_id='WA-' + 'c' * 24, work_id='RW-stuck002')
        self.write('current-wants.json', [self.rows[0], other, self.rows[1]])
        self.state['room_work']['open'].append(dict(self.state['room_work']['open'][0], id='RW-stuck002', want_id='stuck2',
                                                    want_request_id=other['agent_work']['request_id']))

    def test_a_reply_held_for_review_and_rechecked_without_a_call_keeps_the_pass(self):
        # review (shape retry): a want held after its third slip is re-checked on every pass from its recorded reply,
        # with no call; it must not use one of the pass's two working calls
        self._two_stuck(); self.block = {'stuck': 'response_needs_review', 'stuck2': 'response_needs_review'}
        with patch.object(W, 'unanswered', lambda w, work, ws: [{'key': 'agent:fixture-1'}] if w['id'].startswith('stuck') else []):
            lines = self.run_pass()
        self.assertEqual(self.generated, [('ec-fixture1', 'opening')], lines)

    def test_shape_retries_inside_one_decision_count_against_the_pass(self):
        # review (shape retry): one decision that made three calls (two regenerations) leaves no call in the pass
        calls = self.mem / 'want-work-control' / 'calls.json'
        def generate(w, work, ws, phase, trigger, instruction, writer=None, identity=None):
            from datetime import datetime
            from zoneinfo import ZoneInfo
            day = datetime.fromtimestamp(__import__('time').time(), ZoneInfo('America/Chicago')).date().isoformat()
            data = json.loads(calls.read_text()) if calls.exists() else {'calls': {}}
            for i in range(3):
                data['calls']['%s-%d-%d' % (w['id'], len(data['calls']), i)] = {'request_id': w['agent_work']['request_id'], 'day': day}
            calls.parent.mkdir(parents=True, exist_ok=True); calls.write_text(json.dumps(data))
            self.generated.append((w['id'], phase)); return {'message': 'Synthetic reply.', 'accept': False}
        self.block = {}
        with patch.object(W, 'generate', generate), patch.object(W, 'unanswered', lambda w, work, ws: [{'key': 'agent:fixture-1'}] if w['id'] == 'stuck' else []), \
             patch.object(D, 'send_reply', lambda *a, **k: None, create=True):
            lines = self.run_pass()
        self.assertEqual([g for g in self.generated if g[1] == 'opening'], [], lines)
        self.assertTrue(any('not handed over yet: pass_call_limit' in l for l in lines), lines)

    def test_attempt_already_reserved_holds_only_that_want(self):
        self.block = {'stuck': 'attempt_already_reserved'}
        lines = self.run_pass()
        self.assertEqual(self.current()['stuck']['agent_work']['blocked']['reason'], 'attempt_already_reserved')
        self.assertEqual(self.current()['ec-fixture1']['agent_work']['status'], 'in_work', lines)

    def test_a_cleared_block_is_no_longer_shown(self):
        self.run_pass(); self.block = {}
        self.run_pass(self.now + 420)
        self.assertIsNone(self.current()['stuck']['agent_work'].get('blocked'))

    def test_daily_cap_stops_calls_not_the_lane(self):
        self.block = {'stuck': 'daily_call_cap'}
        lines = self.run_pass()
        rows = self.current()
        self.assertFalse(rows['stuck']['agent_work'].get('blocked'))      # a day-wide limit is not this want's fault
        self.assertTrue(any("day's working calls are used" in l for l in lines), lines)
        # the handoff writes his request with a model call, so it waits for tomorrow, retained and said
        self.assertFalse(self.posts)
        self.assertTrue(any('ec-fixture1 not handed over yet' in l for l in lines), lines)
        self.assertEqual(self.generated, [])

    def test_stop_file_and_broken_policy_still_stop_everything(self):
        (self.mem / 'want-work.stop').touch()
        self.assertEqual(self.run_pass(), ['bound want lane stopped; incoming context retained'])
        (self.mem / 'want-work.stop').unlink()
        self.block = {'stuck': 'want_lane_stopped'}
        with self.assertRaises(WorkBlocked): self.run_pass()
        self.block = {'stuck': 'invalid_work_budget'}
        with self.assertRaises(WorkBlocked): self.run_pass()
        self.assertFalse(self.posts)

    def test_held_want_gives_its_places_back_after_the_adoption_timeout(self):
        # a block that can clear by itself waits the 48 h; a stuck one is given back at once (test_want_slots_freed)
        self.block = {'stuck': 'context_needs_continuation'}
        self.run_pass()
        rid = self.rows[0]['agent_work']['request_id']
        early = self.run_pass(self.now + (A.ADOPT_ANSWER_HOURS - 1) * 3600)
        item = next(x for x in self.state['room_work']['open'] if x.get('want_request_id') == rid)
        self.assertFalse(room_work.paused(item, self.now + (A.ADOPT_ANSWER_HOURS - 1) * 3600))
        self.assertFalse(self.current()['stuck'].get('adoption_released'))
        later = self.now + A.ADOPT_ANSWER_HOURS * 3600 + 60
        lines = self.run_pass(later)
        item = next(x for x in self.state['room_work']['open'] if x.get('want_request_id') == rid)
        self.assertTrue(room_work.paused(item, later), item)
        self.assertNotIn(item, room_work.in_hand(self.state, later))
        self.assertEqual(self.current()['stuck']['adoption_released']['reason'], 'blocked_context_needs_continuation')
        self.assertTrue(any('gave its room place back' in l for l in lines), lines)
        self.assertTrue(self.current()['stuck']['agent_work'].get('thread'))      # its context and request are kept


if __name__ == '__main__':
    unittest.main()

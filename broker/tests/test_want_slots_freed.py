#!/usr/bin/env python3
"""A held or silent want does not keep its place (11 November: room_work.MAX_OPEN full with a want at its call cap, a
want held for review and a want whose agent had gone quiet, while two adopted promises waited two days).

- a block that cannot clear by itself (per_want_call_cap, response_needs_review, interrupted_call_needs_review) gives
  the room and adoption places back on the very next pass, and the queued want is handed over in that pass
- a context limit keeps the 48 h
- a bound want whose agent has not answered for 24 h gives its place back, marked, and takes it again when the agent
  answers
- the decision is found in a fenced block after prose, not at the first brace
Synthetic wants; stubbed model and Slack; scratch workspace."""
import json, os, sys, time, unittest
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_want_lane_held_want as base
A, W, D, room_work = base.A, base.W, base.D, base.room_work


class Slots(base.Tests):
    def fill_board(self):
        for i in range(room_work.MAX_OPEN - 1):
            self.state['room_work']['open'].append(dict(id='RW-other%03d' % i, goal='unrelated fixture work %d' % i,
                                                        opened=self.now, touched=self.now, by='dot'))

    def test_stuck_block_frees_its_place_on_the_next_pass(self):
        self.fill_board()
        self.assertEqual(len(room_work.in_hand(self.state, self.now)), room_work.MAX_OPEN)
        lines = self.run_pass()
        rows = self.current()
        self.assertEqual(rows['stuck']['adoption_released']['reason'], 'blocked_per_want_call_cap')
        self.assertTrue(rows['stuck']['agent_work']['thread'])                     # context and request kept
        self.assertEqual(rows['ec-fixture1']['agent_work']['status'], 'in_work', lines)   # handed over in that pass
        self.assertEqual(self.notices.count(('stuck', 'per_want_call_cap')), 1)

    def test_review_and_interrupted_blocks_are_stuck_blocks(self):
        for reason in ('response_needs_review', 'interrupted_call_needs_review'):
            self.assertIn(reason, A.STUCK_BLOCKS)
        self.block = {'stuck': 'response_needs_review'}
        self.fill_board(); self.run_pass()
        self.assertEqual(self.current()['stuck']['adoption_released']['reason'], 'blocked_response_needs_review')

    def test_a_context_limit_keeps_the_48_hours(self):
        self.block = {'stuck': 'context_needs_continuation'}
        self.fill_board(); self.run_pass()
        self.assertFalse(self.current()['stuck'].get('adoption_released'))
        self.assertNotEqual(self.current()['ec-fixture1']['agent_work'].get('status'), 'in_work')

    def mine(self):
        return [p for i, p in self.generated if i == 'stuck']

    def quiet_setup(self, hours=25):
        self.block = {}
        rows = self.current()
        w = rows['stuck']; rid = w['agent_work']['request_id']
        w['agent_work']['thread'] = '%.6f' % (self.now - hours * 3600)
        self.write('current-wants.json', list(rows.values()))
        folder = A.directory(rid, self.ws); folder.mkdir(parents=True, exist_ok=True)
        thread = folder / 'working-thread.json'
        thread.write_text(json.dumps({'events': [{'key': 'agent:old', 'at': self.now - hours * 3600}]}))
        bind = W.binding
        self.stack_binding = unittest.mock.patch.object(
            W, 'binding', lambda w, state, *a, **k: {'id': (w.get('agent_work') or {}).get('work_id') or 'RW-x'}
            if (w.get('agent_work') or {}).get('thread') else None)
        self.stack_binding.start(); self.addCleanup(self.stack_binding.stop)
        return rid, thread

    def test_a_quiet_agent_is_re_pinged_once_then_gives_the_place_back_and_takes_it_again_when_it_answers(self):
        rid, thread = self.quiet_setup()
        with unittest.mock.patch.object(W, 'unanswered', lambda *a: []):
            lines = self.run_pass()
            self.assertTrue(any('re-pinged once' in l for l in lines), lines)
            self.assertEqual(self.mine(), ['reping'])
            pings = [p for p in self.posts if p.get('thread_ts')]
            self.assertEqual(len(pings), 1)                                       # one message, in its own thread
            self.assertEqual(pings[0].get('thread_ts'), self.current()['stuck']['agent_work']['thread'])
            self.assertFalse(self.current()['stuck'].get('adoption_released'))  # it keeps its place for a day
            lines = self.run_pass(self.now + 3600)
            self.assertEqual(self.mine(), ['reping'], lines)                      # never a second ping this spell
            later = self.now + 25 * 3600
            lines = self.run_pass(later)
            self.assertEqual(self.mine(), ['reping'], lines)
            item = next(x for x in self.state['room_work']['open'] if x.get('want_request_id') == rid)
            self.assertTrue(room_work.paused(item, later), lines)                # quiet another day: place given back
            self.assertEqual(self.current()['stuck']['adoption_released']['reason'], 'agent_quiet_24h')
            thread.write_text(json.dumps({'events': [{'key': 'agent:new', 'at': later + 10}]}))
            lines = self.run_pass(later + 420)
        item = next(x for x in self.state['room_work']['open'] if x.get('want_request_id') == rid)
        self.assertFalse(room_work.paused(item, later + 420), lines)              # its agent wrote: back
        self.assertFalse(self.current()['stuck'].get('adoption_released'))
        self.assertEqual(self.mine(), ['reping'])

    def test_a_crash_between_the_ping_and_its_record_never_pings_twice(self):
        # review (12 November): the spell is recorded before the ping is sent, so a pass that dies after the post does
        # not ping again on the next one
        rid, thread = self.quiet_setup()
        real = D.agent_wants_pass
        class Died(Exception): pass
        def api(method, payload):
            r = self.api(method, payload)
            if payload.get('thread_ts'): raise Died('fixture: the process dies after the post')
            return r
        with unittest.mock.patch.object(W, 'unanswered', lambda *a: []):
            try:
                D.agent_wants_pass(api, 'fixture-channel', 'fixture-dot', self.state, self.now,
                                   block_notify=lambda key, message: {'state': 'sent'}, identity=lambda: 'Synthetic identity')
            except Died:
                pass
            self.run_pass(self.now + 420)
        self.assertEqual(len([p for p in self.posts if p.get('thread_ts')]), 1)

    def test_a_new_quiet_spell_gets_its_own_one_ping(self):
        rid, thread = self.quiet_setup()
        with unittest.mock.patch.object(W, 'unanswered', lambda *a: []):
            self.run_pass()
            thread.write_text(json.dumps({'events': [{'key': 'agent:new', 'at': self.now + 10}]}))
            self.run_pass(self.now + 26 * 3600)
        self.assertEqual(self.mine(), ['reping', 'reping'])

    def test_the_re_ping_counts_against_the_call_cap(self):
        rid, thread = self.quiet_setup()
        self.block = {'stuck': 'per_want_call_cap'}
        with unittest.mock.patch.object(W, 'unanswered', lambda *a: []):
            self.run_pass()
        self.assertEqual(self.mine(), [])
        self.assertFalse(any(p.get('thread_ts') for p in self.posts))

    def test_unhold_takes_the_adoption_place_again(self):
        self.run_pass(); self.block = {}
        self.run_pass(self.now + 6 * 3600 + 60)      # the recheck after the given-back place expires
        self.assertIsNone(self.current()['stuck']['agent_work'].get('blocked'))
        self.assertFalse(self.current()['stuck'].get('adoption_released'))

    def test_a_want_that_comes_back_never_takes_the_room_past_max_open(self):
        # review: the stuck want gives its place back, another is handed over into it, then the block clears and the
        # recheck pause runs out; the returning want waits, the room never holds more than MAX_OPEN in hand
        self.fill_board(); self.run_pass()
        later = self.now + A.RECHECK_HOURS * 3600 + 60
        self.block = {}
        for t in (later, later + 420):
            self.run_pass(t)
            self.assertLessEqual(len(room_work.in_hand(self.state, t)), room_work.MAX_OPEN)
        item = next(x for x in self.state['room_work']['open'] if x.get('want_id') == 'stuck')
        self.assertTrue(room_work.paused(item, later + 420)); self.assertTrue(item['pause_why'].startswith('waiting for a place'))
        # a place frees: the returning want takes it on its next look
        self.state['room_work']['open'] = [x for x in self.state['room_work']['open'] if x.get('id') != 'RW-other000']
        t = later + (A.RECHECK_HOURS + 1) * 3600
        self.run_pass(t)
        self.assertFalse(room_work.paused(item, t + 1))
        self.assertLessEqual(len(room_work.in_hand(self.state, t)), room_work.MAX_OPEN)

    def test_a_quiet_want_whose_agent_answers_waits_while_the_room_is_full(self):
        self.block = {}
        rows = self.current(); w = rows['stuck']; rid = w['agent_work']['request_id']
        w['agent_work']['thread'] = '%.6f' % (self.now - 25 * 3600)
        # its one re-ping for this quiet spell was a day ago: this pass gives its place back (re-ping rule, 12 November)
        w['agent_work']['reping'] = {'spell': self.now - 25 * 3600, 'at': self.now - 25 * 3600}
        self.write('current-wants.json', list(rows.values()))
        folder = A.directory(rid, self.ws); folder.mkdir(parents=True, exist_ok=True)
        thread = folder / 'working-thread.json'
        thread.write_text(json.dumps({'events': [{'key': 'agent:old', 'at': self.now - 25 * 3600}]}))
        with unittest.mock.patch.object(W, 'unanswered', lambda *a: []):
            self.run_pass()
            self.fill_board()                         # with the want handed over in the first pass: the room is full
            self.assertEqual(len(room_work.in_hand(self.state, self.now + 420)), room_work.MAX_OPEN)
            thread.write_text(json.dumps({'events': [{'key': 'agent:new', 'at': self.now + 10}]}))
            lines = self.run_pass(self.now + 420)
        item = next(x for x in self.state['room_work']['open'] if x.get('want_request_id') == rid)
        self.assertTrue(room_work.paused(item, self.now + 420), lines)
        self.assertLessEqual(len(room_work.in_hand(self.state, self.now + 420)), room_work.MAX_OPEN)

    def test_decision_in_a_fence_after_prose_with_a_brace(self):
        raw = ('Synthetic prose that mentions a {placeholder} before the answer.\n\n```json\n'
               + json.dumps({'message': 'Synthetic decision.', 'accept': False}) + '\n```')
        self.assertEqual(W.lenient_decision(raw), {'message': 'Synthetic decision.', 'accept': False})
        with self.assertRaises(ValueError):
            W.lenient_decision('Synthetic prose {not json} only.')
        # review: a stray brace that IS an object, but not a decision, is passed over too
        raw2 = ('Synthetic prose quoting {"step": 1} first.\n\n```json\n'
                + json.dumps({'message': 'Synthetic decision.', 'accept': False}) + '\n```')
        self.assertEqual(W.lenient_decision(raw2), {'message': 'Synthetic decision.', 'accept': False})


del base.Tests     # its own cases run in its own file

if __name__ == '__main__':
    unittest.main()

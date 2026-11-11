#!/usr/bin/env python3
"""A working reply that parses but slips on its shape (accept missing, accept true outside the result phase, the result
marker in a continue message) is not an uncertain call. It is kept as a rejected observation and the same phase is
generated again with a short correction, at most SHAPE_RETRIES times, each a reserved call on the want's budget. Only
an unparseable or interrupted call, or a third slip, waits for review. A want already held this way recovers on its
next pass. Synthetic writer, scratch workspace, no real sends."""
import json, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import want_agent as A
import want_working_thread as W
import want_work_budget as B
from journal_wants import source_receipt


def reply(obj):
    text = obj if isinstance(obj, str) else json.dumps(obj)
    return dict(text=text, observations=[dict(text=text, status='valid', identity_evidence='response_metadata',
                                               observed_model='fixture-served', requested_model='fixture-request')])


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='want-shape-test-'); self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name).resolve(); (self.ws / 'memory').mkdir()
        env = patch.dict(os.environ, SPARK_WORKSPACE=str(self.ws)); env.start(); self.addCleanup(env.stop)
        self.want = dict(id='fixture-want', want='I want to run a synthetic analysis and export the result.', source='email')
        self.want.update(source_receipt('email', 'fixture-mail', self.want['want']))
        self.want['agent_work'] = dict(request_id='WA-' + 'b' * 24, goal_sha256=A.fingerprint(self.want['want']),
                                       created_at=time.time(), status='in_work', thread='fixture-thread', work_id='RW-fixture')
        self.work = dict(id='RW-fixture', want_id=self.want['id'], want_request_id=self.want['agent_work']['request_id'])
        W.load(self.want, self.work, self.ws, 'Synthetic identity')
        self.users = []

    def writer_of(self, *replies):
        queue = list(replies)
        def writer(system, user):
            self.users.append(json.loads(user)); return reply(queue.pop(0))
        return writer

    def gen(self, writer, phase='continue', trigger='fixture-events'):
        return W.generate(self.want, self.work, self.ws, phase, trigger, 'Fixture instruction', writer)

    def record(self, phase='continue', trigger='fixture-events'):
        return W.load(self.want, self.work, self.ws)['generations'][phase + ':' + A.fingerprint(trigger)]

    def calls(self):
        return [c for c in json.loads((self.ws / 'memory/want-work-control/calls.json').read_text())['calls'].values()
                if c['request_id'] == self.want['agent_work']['request_id']]

    def test_missing_accept_is_regenerated_with_a_correction(self):
        out = self.gen(self.writer_of({'message': 'Synthetic step one.'},
                                      {'message': 'Synthetic step one, again.', 'accept': False}))
        self.assertEqual(out, {'message': 'Synthetic step one, again.', 'accept': False})
        self.assertNotIn('correction', self.users[0])
        self.assertIn('accept is required', self.users[1]['correction'])
        rec = self.record()
        self.assertEqual(rec['state'], 'done')
        self.assertEqual(len(rec['rejected']), 1)
        self.assertIn('Synthetic step one.', rec['rejected'][0]['result']['text'])     # kept as an observation
        self.assertEqual(len(self.calls()), 2)                                      # both counted on its budget

    def test_marker_in_a_continue_message_is_regenerated_not_taken_as_a_result(self):
        out = self.gen(self.writer_of({'message': 'All finished. WANT RESULT ' + self.want['agent_work']['request_id'],
                                       'accept': False},
                                      {'message': 'Please record it with want_agent.py result.', 'accept': False}))
        self.assertNotIn('WANT RESULT', out['message'])
        self.assertIn('Do not write WANT RESULT', self.users[1]['correction'])
        self.assertNotEqual(self.want['agent_work'].get('status'), 'result_ready')

    def test_accept_true_outside_result_phase_is_regenerated(self):
        out = self.gen(self.writer_of({'message': 'Synthetic.', 'accept': True}, {'message': 'Synthetic.', 'accept': False}))
        self.assertFalse(out['accept'])
        self.assertIn('outside the result phase', self.users[1]['correction'])

    def test_three_slips_wait_for_review(self):
        bad = {'message': 'Synthetic without accept.'}
        with self.assertRaisesRegex(B.WorkBlocked, 'response_needs_review'):
            self.gen(self.writer_of(bad, bad, bad))
        self.assertEqual(len(self.users), 1 + W.SHAPE_RETRIES)
        self.assertEqual(len(self.record()['rejected']), W.SHAPE_RETRIES)
        with self.assertRaisesRegex(B.WorkBlocked, 'response_needs_review'):
            self.gen(self.writer_of())                                  # no further call on a later pass
        self.assertEqual(len(self.users), 1 + W.SHAPE_RETRIES)

    def test_unparseable_reply_still_waits_for_review_without_retry(self):
        with self.assertRaisesRegex(B.WorkBlocked, 'response_needs_review'):
            self.gen(self.writer_of('{not json'))
        self.assertEqual(len(self.users), 1)
        self.assertEqual(self.record()['state'], 'response_observed')

    def test_a_want_already_held_on_a_slip_recovers_on_its_next_pass(self):
        # as on 10 November: the reply was observed and saved, then held for review before this fix
        key = 'continue:' + A.fingerprint('fixture-events')
        def stuck(d):
            d['generations'][key] = dict(state='response_observed', request_id='fixture-run', at=time.time() - 3600,
                                         attempts=[], observations=[], result=reply({'message': 'Synthetic, no accept.'}))
        W._mutate(self.want, self.work, self.ws, stuck)
        out = self.gen(self.writer_of({'message': 'Synthetic recovered.', 'accept': False}))
        self.assertEqual(out['message'], 'Synthetic recovered.')
        self.assertEqual(self.record()['state'], 'done')
        self.assertIn('accept is required', self.users[0]['correction'])

    def test_regeneration_respects_the_per_want_cap(self):
        (self.ws / 'memory/want-work-policy.json').write_text(json.dumps({'per_want_calls': 1}))
        with self.assertRaisesRegex(B.WorkBlocked, 'per_want_call_cap'):
            self.gen(self.writer_of({'message': 'Synthetic, no accept.'}, {'message': 'x', 'accept': False}))
        self.assertEqual(len(self.users), 1)
        self.assertEqual(len(self.record()['rejected']), 1)

    def test_a_good_reply_is_unchanged(self):
        out = self.gen(self.writer_of({'message': 'Synthetic fine.', 'accept': False}))
        self.assertEqual(out['message'], 'Synthetic fine.')
        self.assertEqual(self.record().get('rejected'), [])
        self.assertEqual(W.shape_problem({'message': 'ok', 'accept': True}, 'result'), '')


if __name__ == '__main__':
    unittest.main()

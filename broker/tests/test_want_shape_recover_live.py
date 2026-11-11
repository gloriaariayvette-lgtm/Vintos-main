#!/usr/bin/env python3
"""The live shape that the shape retry never recovered (11 November). A handed-over want's current 'continue'
generation was response_observed with one rejected reply already kept (missing accept), and its regenerated reply was
two JSON objects back to back, the first with the key " accept": json.loads failed with "Extra data", so every pass
raised response_needs_review before the shape check, and three block notices piled up. The decision is now read
leniently (the first object, keys trimmed) and the want moves on its next pass, without a new call. A reply with no
JSON object at all still waits for review. Synthetic ids and text; scratch workspace; no real sends."""
import json, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import want_agent as A
import want_working_thread as W
import want_work_budget as B
from journal_wants import source_receipt


def reply(text):
    return dict(text=text, observations=[dict(text=text, status='valid', lane='subscription',
                                               identity_evidence='response_metadata', observed_model='fixture-served',
                                               requested_model='fixture-request')])


TWO_OBJECTS = (json.dumps({' accept': False, 'message': 'Synthetic next step for the agent.'}) + '\n\n'
               + json.dumps({'message': 'Synthetic next step, said again.', 'accept': False}))


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='want-recover-test-'); self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name).resolve(); (self.ws / 'memory').mkdir()
        env = patch.dict(os.environ, SPARK_WORKSPACE=str(self.ws)); env.start(); self.addCleanup(env.stop)
        self.want = dict(id='ec-fixture9', want='I want to run the synthetic fixture comparison and export it.', source='email',
                         adopted_from='EC-fixture9')
        self.want.update(source_receipt('email', 'fixture-mail-9', self.want['want']))
        self.want['agent_work'] = dict(request_id='WA-' + 'c' * 24, goal_sha256=A.fingerprint(self.want['want']),
                                       created_at=time.time(), status='in_work', thread='fixture-thread', work_id='RW-fixture9',
                                       blocked={'reason': 'response_needs_review', 'since': time.time() - 86 * 420,
                                                'last': time.time(), 'passes': 86})
        self.work = dict(id='RW-fixture9', want_id=self.want['id'], want_request_id=self.want['agent_work']['request_id'])
        W.load(self.want, self.work, self.ws, 'Synthetic identity')
        self.trigger = '["agent:fixture-1", "agent:fixture-2", "agent:fixture-3"]'
        self.key = 'continue:' + A.fingerprint(self.trigger)
        now = time.time()
        def live_shape(d):
            d['generations']['opening:' + A.fingerprint(self.want['agent_work']['request_id'])] = dict(
                state='done', request_id='fixture-run-0', at=now - 9000, decision={'message': 'Synthetic opening.', 'accept': False})
            d['generations']['continue:' + A.fingerprint('["agent:fixture-0"]')] = dict(
                state='response_observed', request_id='fixture-run-1', at=now - 8000, attempts=[], observations=[],
                result=reply(json.dumps({'message': 'Synthetic, older trigger.'})))
            d['generations'][self.key] = dict(
                state='response_observed', request_id='fixture-run-3', at=now - 7000, attempts=[], observations=[],
                rejected=[{'request_id': 'fixture-run-2', 'problem': 'accept is required and must be true or false '
                           '(false outside the result phase).', 'at': now - 7100,
                           'result': reply(json.dumps({'message': 'Synthetic first slip.'}))}],
                result=reply(TWO_OBJECTS))
            d['block_notices'] = {'response_needs_review:call:fixture-run-%d' % i: {'state': 'sent'} for i in (1, 2, 3)}
        W._mutate(self.want, self.work, self.ws, live_shape)
        self.writes = []

    def writer(self, system, user):
        self.writes.append(json.loads(user)); return reply(json.dumps({'message': 'Synthetic regenerated.', 'accept': False}))

    def gen(self, writer=None):
        return W.generate(self.want, self.work, self.ws, 'continue', self.trigger, 'Fixture instruction', writer or self.writer)

    def record(self):
        return W.load(self.want, self.work, self.ws)['generations'][self.key]

    def test_live_shape_recovers_on_the_next_pass_without_a_call(self):
        out = self.gen()
        self.assertEqual(out, {'accept': False, 'message': 'Synthetic next step for the agent.'})
        self.assertEqual(self.writes, [])
        self.assertEqual(self.record()['state'], 'done')
        self.assertEqual(len(self.record()['rejected']), 1)

    def test_the_hold_is_cleared_once_the_decision_goes_through(self):
        self.gen()
        A.unhold(self.want, ws=self.ws)
        self.assertIsNone(self.want['agent_work'].get('blocked'))

    def test_two_objects_whose_first_slips_are_regenerated_within_the_cap(self):
        def slip(d):
            d['generations'][self.key]['result'] = reply(json.dumps({'message': 'Synthetic, no accept.'}) + '\n'
                                                         + json.dumps({'message': 'x', 'accept': False}))
        W._mutate(self.want, self.work, self.ws, slip)
        out = self.gen()
        self.assertEqual(out['message'], 'Synthetic regenerated.')
        self.assertEqual(len(self.writes), 1)
        self.assertIn('accept is required', self.writes[0]['correction'])
        self.assertEqual(len(self.record()['rejected']), 2)

    def test_a_reply_with_no_json_object_still_waits_for_review(self):
        def garbage(d):
            d['generations'][self.key]['result'] = reply('Synthetic prose with no object at all.')
        W._mutate(self.want, self.work, self.ws, garbage)
        with self.assertRaisesRegex(B.WorkBlocked, 'response_needs_review'):
            self.gen()
        self.assertEqual(self.writes, [])

    def test_two_objects_that_decide_differently_are_regenerated_not_taken(self):
        # review: the first of two objects is taken only while they agree on accept; when they disagree (or " accept"
        # and "accept" disagree in one object) the reply goes to the capped retry, and nothing of it is posted
        for raw in (json.dumps({'message': 'Synthetic, keep going.', 'accept': False}) + '\n'
                    + json.dumps({'message': 'Synthetic, done.', 'accept': True}),
                    '{" accept": false, "accept": true, "message": "Synthetic, two spellings."}'):
            with self.subTest(raw=raw[:30]):
                self.setUp(); self.writes = []
                W._mutate(self.want, self.work, self.ws, lambda d: d['generations'][self.key].update(result=reply(raw)))
                out = self.gen()
                self.assertEqual(out, {'message': 'Synthetic regenerated.', 'accept': False})
                self.assertEqual(len(self.writes), 1)
                self.assertIn('disagree on accept', self.writes[0]['correction'])
                self.assertNotIn('_conflict', out)
        self.assertNotIn('_conflict', W.lenient_decision(TWO_OBJECTS))      # the live pair agrees: the first is taken

    def test_lenient_reading(self):
        self.assertEqual(W.lenient_decision(TWO_OBJECTS)['accept'], False)
        self.assertEqual(W.lenient_decision('```json\n{"message": "m", "accept": false}\n```'), {'message': 'm', 'accept': False})
        self.assertEqual(W.lenient_decision('{"message": "m", "accept": false}'), {'message': 'm', 'accept': False})
        with self.assertRaises(ValueError):
            W.lenient_decision('no object here')


if __name__ == '__main__':
    unittest.main()

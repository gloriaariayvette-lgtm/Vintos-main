"""Automatic result-review holds: local evidence only, no provider replay."""
import copy
import json
import time
import unittest
from unittest.mock import patch
from test_want_shape_retry import Tests as Fixture, reply, A, W, B


class LocalResultReview(unittest.TestCase):
    setUp = Fixture.setUp

    def seed(self, raw, state='response_observed'):
        self.key = 'result:' + A.fingerprint('verified-result-trigger')
        record = dict(state=state, request_id='fixture-local-review', at=time.time()-10,
                      rejected=[], observations=[], result=reply(raw))
        W._mutate(self.want, self.work, self.ws,
                  lambda data: data['generations'].update({self.key: record}))
        return copy.deepcopy(record)

    def generate(self):
        with patch.object(W, 'ask', side_effect=AssertionError('provider forbidden')), \
             patch.object(B, 'reserve', side_effect=AssertionError('budget reservation forbidden')):
            return W.generate(self.want, self.work, self.ws, 'result',
                              'verified-result-trigger', 'fixture',
                              writer=lambda *_: self.fail('writer forbidden'), local_only=True)

    def test_explicit_retained_decision_recovers_without_call(self):
        self.seed(json.dumps(dict(message='Reviewed fixture.', accept=True)))
        self.assertTrue(self.generate()['accept'])
        self.assertEqual(W.load(self.want, self.work, self.ws)['generations'][self.key]['state'], 'done')

    def test_invalid_observations_stay_unchanged_and_incomplete(self):
        for raw in ('Narrative, not an acceptance decision.',
                    json.dumps(dict(message='Missing accept.')),
                    json.dumps(dict(message='Wrong accept type.', accept='true')),
                    '{"message":"Conflicting.","accept":true} {"accept":false}'):
            with self.subTest(raw=raw):
                before = self.seed(raw)
                with self.assertRaisesRegex(B.WorkBlocked, 'response_needs_review'):
                    self.generate()
                self.assertEqual(W.load(self.want, self.work, self.ws)['generations'][self.key], before)

    def test_missing_or_uncertain_generation_never_calls(self):
        with self.assertRaisesRegex(B.WorkBlocked, 'response_needs_review'):
            self.generate()
        for state in ('running', 'uncertain'):
            self.seed('{}', state)
            with self.assertRaisesRegex(B.WorkBlocked, 'interrupted_call_needs_review'):
                self.generate()

    def test_binding_only_automatic_hold_not_owner_or_mismatch(self):
        self.want['agent_work'].update(status='result_ready', blocked={'reason':'response_needs_review'})
        self.work.update(paused_until=time.time()+10000, pause_why='held: blocked_response_needs_review')
        state = {'room_work': {'open': [self.work]}}
        self.assertIs(W.local_result_review_binding(self.want, state), self.work)
        self.want['pursuit'] = {'state':'PAUSED', 'paused_until':time.time()+10000}
        self.assertIsNone(W.local_result_review_binding(self.want, state))
        self.want.pop('pursuit')
        self.work['pause_why'] = 'Explicit evidence-item pause'
        self.assertIsNone(W.local_result_review_binding(self.want, state))
        self.work['pause_why'] = 'held: blocked_response_needs_review'
        self.work['want_request_id'] = 'WA-' + 'f'*24
        self.assertIsNone(W.local_result_review_binding(self.want, state))


if __name__ == '__main__':
    unittest.main()

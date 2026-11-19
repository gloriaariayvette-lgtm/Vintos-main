"""Local review cannot reclaim a fourth room place; all senders are stubs."""
import copy
import json
import unittest
from unittest.mock import Mock, patch
import test_want_lane_held_want as fixture
A, W, D, R = fixture.A, fixture.W, fixture.D, fixture.room_work

class Tests(unittest.TestCase):
    setUp = fixture.Tests.setUp
    write = fixture.Tests.write

    def check_review(self, other_count, expired=False):
        want = copy.deepcopy(self.rows[0])
        want['agent_work'].update(status='result_ready', blocked={'reason':'response_needs_review'})
        work = self.state['room_work']['open'][0]
        work.update(paused_until=self.now-1 if expired else self.now+3600,
                    pause_why='held: blocked_response_needs_review; fixture')
        others = [dict(id='RW-other'+str(i), opened=1, touched=1) for i in range(other_count)]
        self.state['room_work']['open'] += others
        # No ordinary work is considered after the callback under test.
        self.write('current-wants.json', [])
        generate = Mock(return_value={'message':'Explicit retained acceptance.', 'accept':True})
        unhold = Mock()
        result = {'summary':'verified fixture'}
        returned = []
        def finish(*args, **kwargs):
            returned.append(kwargs['review'](want, result))
            return []
        api = Mock(side_effect=AssertionError('Slack forbidden'))
        with patch.object(A, 'finish', finish), patch.object(A, 'intake', return_value=[]), \
             patch.object(A, 'release_blocked', return_value=[]), patch.object(A, 'unhold', unhold), \
             patch.object(W, 'local_result_review_binding', return_value=work), \
             patch.object(W, 'generate', generate), \
             patch.object(R, 'open_items', side_effect=lambda state:state['room_work']['open']):
            D.agent_wants_pass(api, 'fixture-channel', 'fixture-dot', self.state, self.now,
                               block_notify=Mock(), identity=lambda:'fixture')
        api.assert_not_called()
        return work, generate, unhold, returned

    def test_full_room_keeps_hold_and_never_decides_or_publishes(self):
        for expired in (False, True):
            with self.subTest(expired=expired):
                self.setUp()
                work, generate, unhold, returned = self.check_review(R.MAX_OPEN, expired)
                generate.assert_not_called(); unhold.assert_not_called()
                self.assertEqual(returned, [None])
                self.assertTrue(work['pause_why'].startswith('held:'))
                self.assertEqual(work['paused_until'], self.now-1 if expired else self.now+3600)

    def test_expired_row_is_excluded_when_counting_other_work(self):
        work, generate, unhold, returned = self.check_review(R.MAX_OPEN-1, expired=True)
        generate.assert_called_once(); unhold.assert_called_once()
        self.assertTrue(generate.call_args.kwargs['local_only'])
        self.assertEqual(returned, ['Explicit retained acceptance.'])
        self.assertEqual(work['paused_until'], 0)
        self.assertLessEqual(sum(not R.paused(row, self.now) for row in self.state['room_work']['open']), R.MAX_OPEN)

if __name__ == '__main__':
    unittest.main()

"""October 8 fresh-credit regressions. All effects and stores are isolated."""
import concurrent.futures
import json
from pathlib import Path
import unittest
import sys
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_software_quota as legacy
Q, F, S = legacy.Q, legacy.F, legacy.S


class CreditTests(unittest.TestCase):
    # Reuse only the established isolated setup, not its dated test cases.
    def setUp(self):
        legacy.Tests.setUp(self)
        for target in ('software_quota.today', 'forge_loop.step_day', 'study_fix._today'):
            p = patch(target, return_value=Q.CREDIT_DAY)
            p.start(); self.addCleanup(p.stop)
        p = patch.object(S, '_now', return_value=datetime(2026, 10, 8, 12))
        p.start(); self.addCleanup(p.stop)
        self.grant = {'schema': 2, 'date': Q.CREDIT_DAY, 'timezone': 'America/Chicago',
                      'authorization': Q.CREDIT_AUTHORIZATION,
                      'limits': {'forge': 10, 'study': 10},
                      'usage_baseline': {'forge': 3, 'study': 1},
                      'recorded_at': '2026-10-08T08:08:19.942107+00:00',
                      'expires_at': '2026-10-09T05:00:00+00:00',
                      'meaning': 'ten fresh available slots after recorded usage; preserve existing ledger rows'}

    def activate(self):
        Q.CONFIG.write_text(json.dumps(self.grant))

    def test_credit_forge_ten_fresh_and_concurrent_limit(self):
        c = self.controller
        for i in range(3):
            self.assertTrue(c.reserve_build(self.owner, f'{i:032x}', 'SK-12345678')['reserved'])
        self.activate()
        budget = c.step_budget(self.owner)
        self.assertEqual({key: budget[key] for key in ('day', 'used', 'limit', 'remaining')},
                         {'day': Q.CREDIT_DAY, 'used': 3, 'limit': 13, 'remaining': 10})
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(lambda i: c.reserve_build(self.owner, f'{i:032x}', 'SK-12345678'), range(3, 19)))
        self.assertEqual(sum(x['reserved'] for x in outcomes), 10)
        self.assertEqual(c.step_budget(self.owner)['used'], 13)
        self.assertTrue(c.reserve_build(self.owner, f'{0:032x}', 'SK-12345678')['reserved'])
        self.assertEqual(c.step_budget(self.owner)['used'], 13)

    def test_credit_study_ten_fresh_and_no_reset(self):
        prior = [{'id': 'SF-prior', 'asked': '2026-10-08T01:00:00', 'state': 'failed', 'what': 'prior'}]
        Path(S.QUEUE).write_text(json.dumps(prior))
        Path(S.RESET).write_text(json.dumps({'date': Q.CREDIT_DAY, 'at': '2026-10-08T02:00:00'}))
        before = Path(S.RESET).read_bytes()
        self.activate()
        self.assertEqual(S.used_today(), 1)
        self.assertEqual(Q.limit('study', 3, S._today()), 11)
        with self.assertRaisesRegex(ValueError, 'reset refused'):
            S.reset_today()
        self.assertEqual(Path(S.RESET).read_bytes(), before)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(lambda i: S.request(f'Isolated distinct credit request number {i}'), range(16)))
        self.assertEqual(sum(row is not None for row, _ in outcomes), 10)
        self.assertEqual(S.used_today(), 11)
        self.assertEqual(S._load()[0], prior[0])

    def test_credit_consumed_slots_are_not_regranted(self):
        self.activate()
        c = self.controller
        for i in range(5):
            c.reserve_build(self.owner, f'{i:032x}', 'SK-12345678')
        for i in range(2):
            S.request(f'Isolated previous credit consumption {i}')
        self.activate()  # Re-reading/reinstalling the same grant never resets a counter.
        self.assertEqual(c.step_budget(self.owner)['remaining'], 8)
        self.assertEqual(Q.limit('study', 3, S._today()) - S.used_today(), 9)

    def test_credit_expiry_and_recorded_time(self):
        self.activate()
        for timestamp, accepted in [('2026-10-08T08:08:19+00:00', False),
                                    ('2026-10-08T08:08:20+00:00', True),
                                    ('2026-10-09T04:59:59+00:00', True),
                                    ('2026-10-09T05:00:00+00:00', False)]:
            with patch.object(Q, 'datetime', wraps=datetime) as clock:
                clock.now.return_value = datetime.fromisoformat(timestamp).astimezone(Q.ZONE)
                self.assertEqual(Q.campaign() is not None, accepted)
        self.assertEqual(Q.limit('forge', 3, '2026-10-09'), 3)
        self.assertEqual(Q.limit('study', 3, '2026-10-07'), 3)

    def test_credit_rejects_extra_allowance_and_bad_fields(self):
        self.activate()
        for changes in [{'usage_baseline': {'forge': 4, 'study': 1}},
                        {'usage_baseline': {'forge': 3, 'study': True}},
                        {'limits': {'forge': 11, 'study': 10}},
                        {'limits': {'forge': 10.0, 'study': 10}},
                        {'expires_at': '2026-10-10T05:00:00+00:00'},
                        {'recorded_at': '2026-10-08T08:00:00'},
                        {'schema': True}, {'authorization': 'unapproved'}]:
            Q.CONFIG.write_text(json.dumps(dict(self.grant, **changes)))
            self.assertIsNone(Q.campaign(Q.CREDIT_DAY))
            self.assertEqual(Q.limit('study', 3, Q.CREDIT_DAY), 3)
        Q.CONFIG.write_text(json.dumps(self.grant)[:-1] + ',"schema":2}')
        self.assertIsNone(Q.campaign(Q.CREDIT_DAY))

    def test_credit_invalid_grant_cannot_erase_usage(self):
        Path(S.QUEUE).write_text(json.dumps([{'asked': '2026-10-08T01:00:00'}]))
        Path(S.RESET).write_text(json.dumps({'date': Q.CREDIT_DAY, 'at': '2026-10-08T02:00:00'}))
        Q.CONFIG.write_text('{invalid')
        self.assertEqual(S.used_today(), 1)
        with self.assertRaises(ValueError):
            S.reset_today()


if __name__ == '__main__':
    # Run the new cases only; the unchanged legacy suite is run independently.
    suite = unittest.TestSuite(CreditTests(name) for name in CreditTests.__dict__ if name.startswith('test_credit_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())

"""Her receptivity, measured apart from his Gloria-axis criterion (14 November): did she respond to what he asked or
offered, in any form, inside 48 hours - with refusals and clear non-responses still counted, silence never counted,
and an answer in a later turn credited. Synthetic fixtures in scratch directories only; no socket opens."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import receptivity as RC
import gloria_judge as GJ
import intent_engine as E
import priority_vector as PV
import receptive_regrade as RR
import test_intent_fields_fix as F

NOW = datetime(2026, 11, 14, 12, 0, 0)


def iso(hours_ago, base=NOW):
    return (base - timedelta(hours=hours_ago)).isoformat()


def rrow(i, hours_ago, label=None, gloria='NOT_DECLARED', **extra):
    r = {'intent_id': 'syn-%03d' % i, 'status': 'delivered', 'timestamp': iso(hours_ago), 'delivered_at': iso(hours_ago),
         'reply': 'a synthetic reply', 'realized': {'field': 'YES', 'gloria': gloria, 'self': 'NOT_DECLARED'}}
    if label is not None:
        r['receptive'] = {'label': label}
    r.update(extra)
    return r


class Measure(unittest.TestCase):
    def h(self, led):
        return RC.history(led, NOW.timestamp())

    def test_counted_labels_and_weights(self):
        led = [rrow(1, 1, 'answered'), rrow(2, 2, 'partly'), rrow(3, 3, 'ignored'), rrow(4, 4, 'refused'),
               rrow(5, 5, 'answered'), rrow(6, 6, 'no_bid'), rrow(7, 7, 'unclear'), rrow(8, 8), rrow(9, 9, 'bogus')]
        h = self.h(led)
        self.assertEqual((h['answered'], h['partly'], h['ignored'], h['refused'], h['n']), (2, 1, 1, 1, 5))
        self.assertEqual(RC.score(h), 0.5)                     # (2 + 0.5) / 5: a refusal and an ignore are zeros

    def test_minimum_and_window(self):
        self.assertIsNone(RC.score(self.h([rrow(i, i, 'answered') for i in range(4)])))
        self.assertEqual(RC.score(self.h([rrow(i, i, 'answered') for i in range(5)])), 1.0)
        old = [rrow(i, 15 * 24 + i, 'ignored') for i in range(10)]          # older than 14 days: not read
        self.assertEqual(self.h(old + [rrow(20 + i, i, 'answered') for i in range(5)])['n'], 5)

    def test_her_axis_no_does_not_lower_receptivity(self):
        led = [rrow(i, i, 'answered', gloria='NO') for i in range(6)]
        self.assertEqual(RC.score(self.h(led)), 1.0)
        self.assertEqual(PV._landing_rate(PV._axis_history(NOW.timestamp(), led)), 0.0)

    def test_answer_in_a_later_turn_is_credited_inside_the_window(self):
        early = rrow(1, 30, 'ignored')
        later = rrow(2, 20, 'answered', response_at=iso(19))
        later['receptive']['credits'] = 'syn-001'
        h = self.h([early, later] + [rrow(10 + i, i, 'answered') for i in range(3)])
        self.assertEqual((h['answered'], h['ignored'], h['later_turn'], h['n']), (5, 0, 1, 5))

    def test_credit_after_the_window_does_not_count(self):
        early = rrow(1, 60, 'ignored')
        later = rrow(2, 5, 'answered', response_at=iso(4))                 # 56 hours after the early move
        later['receptive']['credits'] = 'syn-001'
        h = self.h([early, later])
        self.assertEqual((h['answered'], h['ignored']), (1, 1))

    def test_refused_is_never_upgraded_by_a_credit(self):
        early = rrow(1, 10, 'refused'); later = rrow(2, 5, 'answered', response_at=iso(4))
        later['receptive']['credits'] = 'syn-001'
        self.assertEqual(self.h([early, later])['refused'], 1)

    def test_record_refuses_unknown_labels(self):
        self.assertIsNone(RC.record('YES', 'j'))
        self.assertEqual(RC.record('answered', 'j', gap_hours=30)['window_hours'], 48)


class Judge(unittest.TestCase):
    def call(self, text, status='ok', packet=None):
        with patch.object(GJ, '_call', return_value=(status, text, 'd')):
            return GJ.judge_receptive(packet or {'his_earlier_open_ask': 'an earlier ask'})

    def test_labels(self):
        for lab in RC.LABELS:
            self.assertEqual(self.call(json.dumps({'her_response': lab, 'answers_earlier': False}))['label'], lab)
        self.assertEqual(GJ.RECEPTIVE_LABELS, RC.LABELS)

    def test_no_clean_answer_is_no_label(self):
        self.assertIsNone(self.call('{"her_response": "YES"}')['label'])
        self.assertIsNone(self.call('not json')['label'])
        self.assertIsNone(self.call('{"her_response": "answered", "answers_earlier": "yes"}')['label'])
        got = self.call('', status='budget')
        self.assertEqual((got['label'], got['status']), (None, 'budget'))

    def test_answers_earlier_needs_an_earlier_ask(self):
        ans = json.dumps({'her_response': 'answered', 'answers_earlier': True})
        self.assertTrue(self.call(ans)['answers_earlier'])
        self.assertFalse(self.call(ans, packet={'his_earlier_open_ask': ''})['answers_earlier'])

    def test_rubric_never_sees_his_criterion_and_shares_the_cap(self):
        self.assertIn(GJ.SRC_RECEPTIVE, GJ.LIVE_SRCS)
        self.assertIn('not whether she said what he privately hoped for', GJ.RECEPTIVE_RUBRIC)

    def test_receptive_spend_counts_against_the_weekly_cap(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, 'anthropic-usage.jsonl')
            with open(log, 'w') as f:
                f.write(json.dumps({'at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'), 'caller': GJ.SRC_RECEPTIVE,
                                    'model': GJ.MODEL_DEFAULT, 'in': 2000000, 'out': 0}) + '\n')
            with patch.object(GJ, 'usage_log', return_value=log), patch.object(GJ, '_cap', return_value=1.0):
                self.assertIsNone(GJ.reserve(GJ.SRC_LIVE, 'system', 'user', 10))
                self.assertGreater(GJ.budget()['logged_usd'], 1.0)


class Engine(unittest.TestCase):
    setUp = F.IntentFieldsFix.setUp
    rows = F.IntentFieldsFix.rows
    respond = F.IntentFieldsFix.respond
    target = F.IntentFieldsFix.target
    delivered = F.IntentFieldsFix.delivered
    sol = F.IntentFieldsFix.sol

    def judge(self, label='answered', earlier=False):
        self.packets = []
        def fake(packet):
            self.packets.append(packet)
            return {'label': label, 'answers_earlier': earlier, 'status': 'ok', 'model': 'synthetic'}
        return patch.object(E, '_receptive_judge', fake)

    def test_every_delivered_move_gets_her_response_whatever_her_axis(self):
        self.verdict = 'NO'
        with self.judge('answered'):
            self.delivered(gloria=copy.deepcopy(F.GLORIA)); E.resolve_previous(F.HER)
        row = self.rows()[-1]
        self.assertEqual(row['realized']['gloria'], 'NO')                      # her axis: the hoped-for thing missed
        self.assertEqual(row['receptive']['label'], 'answered')                # but she answered him
        self.assertEqual(row['receptive']['judge'], E.RECEPTIVE_JUDGE)
        self.assertNotIn('difference_intended', json.dumps(self.packets[0]))   # the judge never sees his criterion
        with self.judge('ignored'):
            self.delivered(); E.resolve_previous(F.HER)                         # no Gloria axis declared at all
        self.assertEqual(self.rows()[-1]['receptive']['label'], 'ignored')

    def test_a_device_event_is_not_her_response(self):
        with self.judge('answered'):
            self.delivered(gloria=copy.deepcopy(F.GLORIA)); E.resolve_previous(F.BUTTON, source='gcs')
        self.assertNotIn('receptive', self.rows()[-1]); self.assertEqual(self.packets, [])

    def _late(self, hours):
        led = self.rows(); led[-1]['delivered_at'] = iso(hours, datetime.now()); led[-1]['timestamp'] = led[-1]['delivered_at']
        Path(E.LEDGER).write_text(json.dumps(led))

    def test_reply_after_her_axis_window_still_counts_inside_48_hours(self):
        with self.judge('answered'):
            self.delivered(gloria=copy.deepcopy(F.GLORIA)); self._late(30); E.resolve_previous(F.HER)
        row = self.rows()[-1]
        self.assertEqual(row['realized']['gloria'], 'HELD')                    # her axis: expired, no verdict
        self.assertEqual(row['receptive']['label'], 'answered')
        self.assertGreater(row['receptive']['gap_hours'], 24)

    def test_reply_after_48_hours_is_not_counted(self):
        with self.judge('ignored'):
            self.delivered(gloria=copy.deepcopy(F.GLORIA)); self._late(50); E.resolve_previous(F.HER)
        self.assertNotIn('receptive', self.rows()[-1]); self.assertEqual(self.packets, [])

    def test_a_later_turn_answer_credits_the_earlier_move(self):
        with self.judge('ignored'):
            self.delivered(); E.resolve_previous(F.HER)
        first = self.rows()[-1]
        with self.judge('answered', earlier=True):
            self.delivered(); E.resolve_previous(F.HER_PLAN)
        self.assertEqual(self.packets[0]['his_earlier_open_ask'], 'Here are both, and the tradeoff between them.')
        second = self.rows()[-1]
        self.assertEqual(second['receptive']['credits'], first['intent_id'])
        h = PV._receptive_history()
        self.assertEqual((h['answered'], h['ignored'], h['later_turn']), (2, 0, 1))

    def test_an_answered_move_is_never_offered_as_an_open_ask(self):
        with self.judge('answered'):
            self.delivered(); E.resolve_previous(F.HER)
        with self.judge('answered', earlier=True):
            self.delivered(); E.resolve_previous(F.HER_PLAN)
        self.assertEqual(self.packets[0]['his_earlier_open_ask'], '')
        self.assertNotIn('credits', self.rows()[-1]['receptive'])

    def test_nothing_of_hers_is_no_record(self):
        self.delivered()
        row = self.rows()[-1]; row['response_at'] = datetime.now().isoformat()
        with self.judge('ignored'):
            self.assertIsNone(E._judge_receptive(row, 'a synthetic reply', '', None))
        self.assertEqual(self.packets, [])

    def test_the_strategy_reads_receptivity_not_her_axis(self):
        Path(E.LEDGER).write_text(json.dumps([rrow(i, i + 1, 'answered', gloria='NO', timestamp=iso(i + 1, datetime.now()),
                                                    delivered_at=iso(i + 1, datetime.now())) for i in range(6)]))
        rec = PV.declare()
        self.assertEqual(rec['receptivity'], 1.0)
        self.assertEqual(rec['weights']['gloria'], max(rec['weights'].values()))
        self.assertEqual(PV.receptivity_report()['criterion_landing']['rate'], 0.0)

    def test_one_reply_reaching_two_moves_is_no_open_ask(self):
        now = datetime.now()
        early = rrow(1, 5, 'ignored', delivered_at=iso(5, now), timestamp=iso(5, now), response_at=iso(1, now), response_text='X')
        this = rrow(2, 3, None, delivered_at=iso(3, now), timestamp=iso(3, now), response_at=iso(1, now), response_text='X')
        Path(E.LEDGER).write_text(json.dumps([early, this]))
        self.assertIsNone(E._open_earlier_ask(this, E._stamp(this['response_at'])))       # her one reply came after both
        early['response_at'] = iso(4, now); early['response_text'] = 'Y'
        Path(E.LEDGER).write_text(json.dumps([early, this]))
        self.assertEqual(E._open_earlier_ask(this, E._stamp(this['response_at']))['intent_id'], 'syn-001')
        early['response_text'] = 'X'                                                         # the same words: one reply
        Path(E.LEDGER).write_text(json.dumps([early, this]))
        self.assertIsNone(E._open_earlier_ask(this, E._stamp(this['response_at'])))

    def test_a_failed_record_stays_open_and_a_labelled_one_is_never_replaced(self):
        with self.judge(None):
            self.delivered(); E.resolve_previous(F.HER)
        row = self.rows()[-1]; self.assertIsNone(row['receptive']['label'])
        with self.judge('answered'):
            E._note_receptive(row, 'a synthetic reply', F.HER)
        self.assertEqual(row['receptive']['label'], 'answered')                  # retried once a judge answers
        led = self.rows(); led[-1]['receptive'] = {'label': 'refused', 'judge': RR.JUDGE}
        Path(E.LEDGER).write_text(json.dumps(led))
        stale = dict(led[-1], receptive={'label': 'answered', 'judge': E.RECEPTIVE_JUDGE})
        E._persist_resolution(stale, int(led[-1].get('resolution_rev', 0) or 0))
        self.assertEqual(self.rows()[-1]['receptive']['label'], 'refused')

    def test_an_unreadable_answer_is_kept_but_never_counted(self):
        with self.judge(None):
            self.delivered(); E.resolve_previous(F.HER)
        row = self.rows()[-1]
        self.assertIsNone(row['receptive']['label']); self.assertEqual(PV._receptive_history()['n'], 0)

    def test_a_judge_crash_never_stops_the_row(self):
        with patch.object(E, '_receptive_judge', side_effect=RuntimeError('boom')):
            self.delivered(gloria=copy.deepcopy(F.GLORIA)); E.resolve_previous(F.HER)
        row = self.rows()[-1]
        self.assertIsNotNone(row['realized']['gloria']); self.assertIsNone(row['receptive']['label'])


class Regrade(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name); self.ledger = d / 'intent-ledger.json'; self.labels = d / 'labels.jsonl'
        rows = [rrow(i, i + 1, gloria='NO') for i in range(6)]
        rows[5]['receptive'] = {'label': 'ignored', 'judge': E.RECEPTIVE_JUDGE}          # a live record: never touched
        self.ledger.write_text(json.dumps(rows))
        labs = [{'id': r['intent_id'], 'ts': r['timestamp'], 'label': l, 'teacher': 'synthetic'}
                for r, l in zip(rows, ['answered', 'answered', 'partly', 'refused', 'no_bid', 'answered'])]
        labs[1]['via'] = 'later_turn'
        labs.append({'id': 'syn-099', 'ts': 'x', 'label': 'answered', 'teacher': 'synthetic'})       # no such row
        self.labels.write_text(''.join(json.dumps(x) + '\n' for x in labs))

    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = RR.main(['--ledger', str(self.ledger)] + list(args))
        return code, json.loads(out.getvalue())

    def test_dry_run_writes_nothing(self):
        before = self.ledger.read_bytes()
        code, rep = self.run_cli('--labels', str(self.labels), '--dry-run', '--now', NOW.isoformat())
        self.assertEqual((code, rep['rows_changed'], rep['already_recorded']), (0, 5, 1))
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(rep['before']['old_landing_rate'], 0.0)
        self.assertEqual((rep['after']['records'], rep['after']['receptivity']), (5, 0.5))   # 2 + 0.5 + 0 + 0 (live ignored) / 5

    def test_apply_is_idempotent_and_revertible(self):
        before = json.loads(self.ledger.read_text())
        code, rep = self.run_cli('--labels', str(self.labels), '--now', NOW.isoformat())
        self.assertEqual((code, rep['mode'], rep['rows_changed']), (0, 'applied', 5))
        self.assertTrue(Path(rep['backup']).exists())
        after = json.loads(self.ledger.read_text())
        for b, a in zip(before, after):                              # only the receptive record changed
            self.assertEqual({k: v for k, v in a.items() if k != 'receptive'}, {k: v for k, v in b.items() if k != 'receptive'})
        self.assertEqual(after[1]['receptive']['via'], 'later_turn'); self.assertEqual(after[5]['receptive'], before[5]['receptive'])
        once = self.ledger.read_bytes()
        code, rep = self.run_cli('--labels', str(self.labels), '--now', NOW.isoformat())
        self.assertEqual((rep['mode'], rep['rows_changed']), ('nothing_to_do', 0)); self.assertEqual(self.ledger.read_bytes(), once)
        code, rep = self.run_cli('--revert')
        self.assertEqual(rep['rows_reverted'], 5); self.assertEqual(json.loads(self.ledger.read_text()), before)

    def test_a_failed_live_record_is_open_to_the_re_measure(self):
        rows = json.loads(self.ledger.read_text()); rows[5]['receptive'] = {'label': None, 'status': 'budget'}
        self.ledger.write_text(json.dumps(rows))
        code, rep = self.run_cli('--labels', str(self.labels), '--now', NOW.isoformat())
        self.assertEqual(rep['rows_changed'], 6)
        self.assertEqual(json.loads(self.ledger.read_text())[5]['receptive']['judge'], RR.JUDGE)

    def test_credit_needs_her_reply_time(self):
        early = rrow(1, 10, 'ignored'); later = rrow(2, 5, 'answered')
        later['receptive']['credits'] = 'syn-001'
        self.assertEqual(RC.credited([early, later]), {})

    def test_unusable_labels_are_refused(self):
        rows = json.loads(self.ledger.read_text())
        self.labels.write_text(json.dumps({'id': rows[0]['intent_id'], 'ts': 'wrong', 'label': 'answered', 'teacher': 't'}) + '\n'
                               + json.dumps({'id': rows[1]['intent_id'], 'ts': rows[1]['timestamp'], 'label': 'YES', 'teacher': 't'}) + '\n')
        code, rep = self.run_cli('--labels', str(self.labels), '--dry-run')
        self.assertEqual((rep['label_unusable'], rep['rows_changed']), (2, 0))

    def test_takes_the_ledger_lock(self):
        import store_guard
        with patch.object(store_guard, 'transaction', side_effect=RuntimeError('locked')):
            with self.assertRaises(RuntimeError):
                RR.regrade(str(self.ledger), str(self.labels), dry_run=True)


if __name__ == '__main__':
    unittest.main()

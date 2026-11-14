"""Her receptivity, the 14 November 12:16 review's gaps: response engagement kept apart from offer acceptance (a
plain no is a response), a receptive lifecycle of its own (a failed judge retried after the intent resolved; her
first answer admitted after the intent was closed by a device event or an expiry; a restart between), coverage of
an older open ask and of her own follow-up with no double credit, every delivered move in one partition bucket, and
an answered judge call whose usage line was not written kept counted. Synthetic fixtures in scratch directories
only; no socket opens."""
import copy
import json
import os
from pathlib import Path
import sys
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
import test_intent_fields_fix as F
import test_gloria_judge_sol as S

NOW = datetime(2026, 11, 14, 12, 0, 0)
OLDER_ANSWER = 'GLORIA (now): About the first thing you asked - yes, the cabin.'
FOLLOW_UP = 'GLORIA (now): Sorry, one more - the second one, the cabin.'


def iso(hours_ago, base=None):
    return ((base or datetime.now()) - timedelta(hours=hours_ago)).isoformat()


def axes(row):
    return {k: v for k, v in row.items() if k not in ('receptive', 'receptive_evidence', 'receptive_rev')}


def srow(i, hours_ago, label=None, base=NOW, **extra):
    r = {'intent_id': 'syn-%03d' % i, 'status': 'delivered', 'timestamp': iso(hours_ago, base),
         'delivered_at': iso(hours_ago, base), 'reply': 'a synthetic reply',
         'realized': {'field': 'YES', 'gloria': 'NOT_DECLARED', 'self': 'NOT_DECLARED'}}
    if label is not None:
        r['receptive'] = {'label': label}
    r.update(extra)
    return r


class Construct(unittest.TestCase):
    def test_a_plain_no_is_counted_apart_and_moves_the_figure_neither_way(self):
        base = [srow(i, i + 1, 'answered') for i in range(5)] + [srow(9, 9, 'ignored')]
        noes = [srow(20 + i, 20 + i, 'refused') for i in range(5)]
        h0, h = RC.history(base, NOW.timestamp()), RC.history(base + noes, NOW.timestamp())
        self.assertEqual((h['refused'], h['ignored'], h['n']), (5, 1, 6))
        self.assertEqual(RC.score(h), RC.score(h0))            # five plain noes neither lower nor raise it
        self.assertIn('5 declined, counted apart', RC.counts_text(h))

    def test_rationale_claims_response_never_movability(self):
        src = (REPO / 'scripts' / 'priority_vector.py').read_text()
        self.assertNotIn('she is movable', src); self.assertNotIn('her transformation leads', src)
        self.assertNotIn("she likely won't move", src)


class Engine(unittest.TestCase):
    setUp = F.IntentFieldsFix.setUp
    rows = F.IntentFieldsFix.rows
    respond = F.IntentFieldsFix.respond
    target = F.IntentFieldsFix.target
    delivered = F.IntentFieldsFix.delivered
    sol = F.IntentFieldsFix.sol
    restarted = F.IntentFieldsFix.restarted

    def judge(self, label='answered', status='ok', earlier=(), mod=E):
        self.packets = []
        def fake(packet):
            self.packets.append(copy.deepcopy(packet))
            return {'label': label if status == 'ok' else None, 'answers_earlier': list(earlier),
                    'status': status, 'model': 'synthetic'}
        return patch.object(mod, '_receptive_judge', fake)

    def write(self, led):
        Path(E.LEDGER).write_text(json.dumps(led))

    def due_now(self):
        """Time has passed the backoff: the open record may be tried again."""
        led = self.rows()
        for r in led:
            rec = r.get('receptive')
            if isinstance(rec, dict):
                rec['retry_after'] = 0
                if isinstance(rec.get('follow_up_failed'), dict): rec['follow_up_failed']['retry_after'] = 0
        self.write(led)

    def late(self, hours):
        led = self.rows(); led[-1]['delivered_at'] = iso(hours); led[-1]['timestamp'] = led[-1]['delivered_at']
        self.write(led)

    # ---- construct, end to end ---------------------------------------------------------------------------
    def test_refusals_never_move_her_priority_and_the_reason_claims_no_movability(self):
        now = datetime.now()
        self.write([srow(i, i + 1, 'refused', base=now) for i in range(6)])
        rec = PV.declare()
        self.assertIsNone(rec['receptivity']); self.assertEqual(rec['weights'], F.MIDDLING)   # not the low branch
        self.assertIn('she declined 6 of your recent asks; do not re-ask those', rec['why'])
        self.write([srow(i, i + 1, 'refused', base=now) for i in range(6)] + [srow(10 + i, 10 + i, 'answered', base=now) for i in range(5)])
        rec = PV.declare()
        self.assertEqual(rec['receptivity'], 1.0)                                  # the noes neither raised nor lowered it
        self.assertEqual(rec['weights']['gloria'], max(rec['weights'].values()))
        self.assertNotIn('movable', rec['why']); self.assertNotIn('transformation', rec['why'])
        self.assertIn('leave alone anything she declined', rec['why'])
        self.assertIn('11 of 11 delivered moves had a reply that was read', rec['why'])
        rep = PV.receptivity_report()
        self.assertEqual((rep['measures'], rep['offer_acceptance'], rep['thresholds_validated'], rep['refused']),
                         ('response_engagement', None, False, 6))

    # ---- lifecycle ---------------------------------------------------------------------------------------
    def test_a_failed_receptive_judge_retries_after_the_intent_resolved_and_a_restart(self):
        self.verdict = 'NO'
        with self.judge(status='timeout'):
            self.delivered(gloria=copy.deepcopy(F.GLORIA)); E.resolve_previous(F.HER)
        row = self.rows()[-1]
        self.assertTrue(all(v is not None for v in row['realized'].values()))      # every axis is settled
        self.assertIsNone(row['receptive']['label']); self.assertEqual(row['receptive']['tries'], 1)
        self.assertFalse(RC.terminal(row))
        settled, axis_calls = axes(row), len(self.judge_calls)
        outcomes = sys.modules['outcome_join'].record.call_count
        with self.judge('answered'):
            E.resolve_previous('')                                                  # inside the backoff: not asked
        self.assertEqual(self.packets, [])
        self.due_now()
        M = self.restarted('intent_engine')                                         # a restart before the retry
        with self.judge('answered', mod=M):
            M.resolve_previous('')
        row = self.rows()[-1]
        self.assertEqual(row['receptive']['label'], 'answered')
        self.assertEqual(axes(row), settled)                                        # no axis reopened
        self.assertEqual(len(self.judge_calls), axis_calls)
        self.assertEqual(sys.modules['outcome_join'].record.call_count, outcomes)  # no effect replayed

    def test_her_first_answer_counts_after_a_device_event_closed_the_intent_by_expiry(self):
        with self.judge('answered'):
            self.delivered(gloria=copy.deepcopy(F.GLORIA)); self.late(30)
            E.resolve_previous(F.BUTTON, source='gcs')                              # a device event after 24 hours
        row = self.rows()[-1]
        self.assertEqual(set(row['realized'].values()) - {'NOT_DECLARED'}, {'HELD'})
        self.assertNotIn('receptive', row); self.assertEqual(self.packets, [])
        settled, outcomes = axes(row), sys.modules['outcome_join'].record.call_count
        E.note_response(F.HER)                                                      # her first words, at 30 hours
        M = self.restarted('intent_engine')                                         # a restart before any judge
        with self.judge('answered', mod=M):
            M.resolve_previous('')
        row = self.rows()[-1]
        self.assertEqual(row['receptive']['label'], 'answered'); self.assertGreater(row['receptive']['gap_hours'], 29)
        self.assertIn('Which alternative', self.packets[0]['her_reply'])
        self.assertEqual(axes(row), settled); self.assertEqual(self.judge_calls, [])
        self.assertEqual(sys.modules['outcome_join'].record.call_count, outcomes)

    def test_after_48_hours_nothing_is_admitted(self):
        self.delivered(); self.late(50)
        with self.judge('answered'):
            E.resolve_previous(F.HER)
        self.assertNotIn('receptive_evidence', self.rows()[-1]); self.assertEqual(self.packets, [])
        self.assertEqual(PV.receptivity_report()['partition']['silence'], 1)

    def test_a_judge_that_keeps_failing_becomes_a_counted_judge_failure(self):
        with patch.object(RC, 'TRIES_MAX', 2):
            with self.judge(status='timeout'):
                self.delivered(); E.resolve_previous(F.HER)
                self.assertEqual(PV.receptivity_report()['partition']['pending_judge'], 1)
                self.due_now(); E.resolve_previous('')
                self.due_now(); E.resolve_previous('')
            self.assertEqual(len(self.packets), 2)
            row = self.rows()[-1]
            self.assertTrue(row['receptive']['terminal']); self.assertTrue(RC.terminal(row))
            self.assertNotIn('text', row['receptive_evidence']['first'])         # her words leave a closed record
            p = PV.receptivity_report()['partition']
            self.assertEqual((p['judge_failed'], p['pending_judge'], p['scored'], p['delivered']), (1, 0, 0, 1))

    def test_the_budget_spends_no_try_and_only_days_end_it(self):
        with patch.object(RC, 'TRIES_MAX', 2), self.judge(status='budget'):
            self.delivered(); E.resolve_previous(F.HER)
            for _ in range(4):
                self.due_now(); E.resolve_previous('')
            row = self.rows()[-1]
            self.assertEqual((len(self.packets), row['receptive']['tries']), (5, 0)); self.assertFalse(RC.terminal(row))
            led = self.rows(); led[-1]['delivered_at'] = led[-1]['timestamp'] = iso(8 * 24)   # a week on, the cap still shut
            led[-1]['receptive_evidence']['first']['at'] = iso(8 * 24 - 1); self.write(led)
            self.due_now(); E.resolve_previous('')
        row = self.rows()[-1]
        self.assertTrue(row['receptive']['terminal'])
        self.assertEqual(PV.receptivity_report()['partition']['budget'], 1)

    def test_an_answer_after_a_failed_selection_turn_is_not_her_follow_up(self):
        with self.judge('ignored'):
            self.delivered(); E.resolve_previous(F.HER)
        E.record_failed_selection(RuntimeError('fixture'))                          # his reply went out untracked
        E.note_response(FOLLOW_UP)
        self.assertNotIn('later', self.rows()[0]['receptive_evidence'])

    def test_admitted_evidence_with_nothing_in_it_is_closed_not_retried_for_ever(self):
        now = datetime.now()
        self.write([srow(1, 2, base=now, receptive_evidence={'first': {'text': 'GLORIA (now):   ', 'at': iso(1, now)}})])
        with self.judge('answered'):
            E.resolve_previous(''); E.resolve_previous('')
        row = self.rows()[-1]
        self.assertEqual(self.packets, []); self.assertTrue(RC.terminal(row))
        self.assertEqual(row['receptive']['status'], 'no_evidence')
        self.assertEqual(PV.receptivity_report()['partition']['unclear'], 1)

    # ---- coverage ----------------------------------------------------------------------------------------
    def test_an_answer_to_the_older_of_two_open_asks_credits_that_one_once(self):
        with self.judge('ignored'):
            self.delivered(); E.resolve_previous(F.HER)
        with self.judge('ignored'):
            self.delivered(); E.resolve_previous(F.HER_PLAN)
        a0, a1 = self.rows()
        self.assertNotIn('later', a0['receptive_evidence'])            # her words after a newer move answer that one
        with self.judge('ignored', earlier=[1]):
            self.delivered(); E.resolve_previous(OLDER_ANSWER)
        asks = self.packets[0]['his_earlier_open_asks']
        self.assertEqual([a['n'] for a in asks], [1, 2])                # both open asks, the older first
        b = self.rows()[-1]
        self.assertEqual(b['receptive']['credits'], [a0['intent_id']])
        h = PV._receptive_history()
        self.assertEqual((h['answered'], h['ignored'], h['later_turn'], h['n']), (1, 2, 1, 3))
        with self.judge('answered', earlier=[1]):                       # a later answer: the credited ask is not offered
            self.delivered(); E.resolve_previous('GLORIA (now): And the plan is fine too.')
        self.assertEqual(len(self.packets[0]['his_earlier_open_asks']), 2)
        self.assertEqual(self.rows()[-1]['receptive']['credits'], [a1['intent_id']])
        h = PV._receptive_history()
        self.assertEqual((h['answered'], h['ignored'], h['later_turn'], h['n']), (3, 1, 2, 4))   # each move once

    def test_her_follow_up_before_his_next_move_is_its_own_evidence_with_no_double_credit(self):
        with self.judge('ignored'):
            self.delivered(); E.resolve_previous(F.HER)
        with self.judge('answered'):
            E.resolve_previous(FOLLOW_UP)                               # no new move of his reached her
        self.assertEqual(len(self.packets), 1); pk = self.packets[0]
        self.assertTrue(pk['facts']['decide_on_her_later_message']); self.assertEqual(pk['his_earlier_open_asks'], [])
        self.assertIn('the cabin', pk['her_later_message']); self.assertIn('Which alternative', pk['her_reply'])
        a = self.rows()[-1]
        self.assertEqual((a['receptive']['label'], a['receptive']['follow_up']['label']), ('ignored', 'answered'))
        self.assertNotIn('credits', a['receptive']['follow_up'])
        self.assertTrue(RC.terminal(a))
        with self.judge('answered'):
            E.resolve_previous('GLORIA (now): a third message')         # one follow-up per move
        self.assertEqual(self.packets, [])
        with self.judge('answered', earlier=[1]):
            self.delivered(); E.resolve_previous(F.HER_PLAN)
        self.assertEqual(self.packets[0]['his_earlier_open_asks'], [])  # already raised: never offered again
        self.assertNotIn('credits', self.rows()[-1]['receptive'])
        h = PV._receptive_history()
        self.assertEqual((h['answered'], h['ignored'], h['later_turn'], h['n']), (2, 0, 1, 2))

    def test_a_failed_follow_up_is_retried_then_given_up(self):
        with self.judge('ignored'):
            self.delivered(); E.resolve_previous(F.HER)
        with patch.object(RC, 'TRIES_MAX', 2), self.judge(status='timeout'):
            E.resolve_previous(FOLLOW_UP)
            self.assertFalse(RC.terminal(self.rows()[-1]))
            self.due_now(); E.resolve_previous('')
        a = self.rows()[-1]
        self.assertEqual(len(self.packets), 2); self.assertTrue(RC.terminal(a))
        self.assertEqual(RC.effective(a, {}), 'ignored')

    # ---- partition --------------------------------------------------------------------------------------
    def test_every_delivered_move_is_in_exactly_one_bucket(self):
        now = datetime.now()
        led = [srow(1, 2, 'answered', base=now), srow(2, 3, 'refused', base=now), srow(3, 4, 'no_bid', base=now),
               srow(4, 5, 'unclear', base=now), srow(5, 6, base=now, receptive={'label': None, 'status': 'error', 'terminal': True}),
               srow(6, 7, base=now, receptive={'label': None, 'status': 'budget', 'terminal': True}),
               srow(7, 8, base=now, receptive={'label': None, 'status': 'timeout', 'tries': 1}),
               srow(8, 1, base=now), srow(9, 60, base=now),
               srow(10, 9, base=now, receptive_evidence={'first': {'text': 'GLORIA (now): yes', 'at': iso(8, now)}}),
               dict(srow(11, 1, base=now), status='failed')]
        self.write(led)
        p = PV.receptivity_report()['partition']
        self.assertEqual({k: p[k] for k in ('scored', 'refused', 'no_bid', 'unclear', 'judge_failed', 'budget',
                                            'pending_judge', 'pending', 'silence')},
                         {'scored': 1, 'refused': 1, 'no_bid': 1, 'unclear': 1, 'judge_failed': 1, 'budget': 1,
                          'pending_judge': 2, 'pending': 1, 'silence': 1})
        self.assertEqual(p['delivered'], 10); self.assertEqual(p['scored_labels']['answered'], 1)


class UsageUnlogged(unittest.TestCase):
    """An answered call whose usage line could not be written keeps its reservation counted (uncertain): settling
    it would let a call the provider charged go uncounted, and the cap would no longer be hard."""
    setUp = S.SonnetTransport.setUp
    transport = S.SonnetTransport.transport
    answer = staticmethod(S.SonnetTransport.answer)

    def test_unlogged_answer_stays_counted_and_a_logged_one_settles(self):
        self.reply = self.answer({'verdict': 'YES', 'reason': 'plain_yes', 'his_adherence': 'delivered'})
        self.log.mkdir(parents=True)                                     # the usage line cannot be appended
        self.assertEqual(GJ.judge(self.packet)['verdict'], 'YES')
        b = GJ.budget()
        self.assertEqual((b['open_n'], b['uncertain_n'], b['logged_usd']), (0, 1, 0.0))
        self.assertGreater(b['counted_usd'], 0.0)
        self.log.rmdir()
        self.assertEqual(GJ.judge(self.packet)['verdict'], 'YES')
        b = GJ.budget()
        self.assertEqual((b['open_n'], b['uncertain_n']), (0, 1)); self.assertGreater(b['logged_usd'], 0.0)
        rows = (self.log.parent / GJ.RESERVE_LOG).read_text()
        self.assertIn('usage_unlogged', rows); self.assertNotIn('SYNTHETIC-HER-WORDS', rows)


if __name__ == '__main__':
    unittest.main()

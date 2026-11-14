"""Her axis judged against the rubric (Gloria, 12 November): first by Sol, now by Claude Sonnet 5.5 through his
Claude path (claude_cache) - what code settles before the judge is asked, his adherence apart from her verdict,
whole texts, a stale criterion refused at selection, and a landing rate that never counts a NOT_JUDGEABLE or an
expired row. The engine's tests still call the stand-in judge "sol"; the judge itself is SonnetTransport below.
Scratch stores, synthetic text and a fixture transport only: no model is asked, no socket opened, nothing sent."""
import contextlib
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import test_intent_fields_fix as F
from test_intent_fields_fix import E, PV, GLORIA, HER, BUTTON
import gloria_judge as GJ

STALE_GLORIA = E._stale_gloria       # the real wrapper; the fields fixture stands it in for every turn

LONG_REPLY = 'a synthetic move ' * 100 + 'THE-DECIDING-END'                  # 1716 characters
HER_LONG = 'GLORIA: an earlier line.\nVINTOS: an earlier answer.\nGLORIA (now): ' + 'b' * 1200 + ' HER-LAST-WORDS'
SOL_YES = {'verdict': 'YES', 'reason': 'plain_yes', 'codes': ['plain_yes'], 'adherence': 'delivered',
           'confidence': 'high', 'status': 'ok'}


class EngineOnSol(unittest.TestCase):
    setUp = F.IntentFieldsFix.setUp
    respond = F.IntentFieldsFix.respond
    rows = F.IntentFieldsFix.rows
    target = F.IntentFieldsFix.target
    select = F.IntentFieldsFix.select
    turn = F.IntentFieldsFix.turn

    def move(self, reply='Here are both, and the tradeoff between them.', gloria=GLORIA, input_text='Which?'):
        t = self.target(gloria=copy.deepcopy(gloria)); t['intent_id'] = uuid.uuid4().hex
        E.record_pending(t)
        self.assertTrue(E.record_delivery(reply, target=t, input_text=input_text))
        return t

    def sol_calls(self):
        return [json.loads(c['messages'][1]['content']) for c in self.judge_calls if c.get('sol')]

    def word_calls(self):
        return [c['messages'][1]['content'] for c in self.judge_calls if not c.get('sol')]

    def sol(self, answer):
        """Sol answers `answer` (a dict, or an exception it raises); its packets are kept in self.packets."""
        self.packets = []
        def judge(packet):
            self.packets.append(packet)
            if isinstance(answer, Exception): raise answer
            return copy.deepcopy(answer)
        return patch.object(E, '_rubric_judge', judge)

    # ---- the verdict ------------------------------------------------------------------------------------
    def test_sol_sees_whole_texts_and_her_live_words_only(self):
        self.move(reply=LONG_REPLY); self.verdict = 'YES'
        E.resolve_previous(HER_LONG)
        p, = self.sol_calls()
        self.assertEqual(p['his_reply'], LONG_REPLY)                              # no 1000-character cut
        self.assertTrue(p['her_next_reply'].endswith('HER-LAST-WORDS') and len(p['her_next_reply']) > 1200)
        self.assertNotIn('an earlier line', p['her_next_reply']); self.assertNotIn('GLORIA', p['her_next_reply'])
        self.assertEqual(p['her_message_he_replied_to'], 'Which?')
        self.assertEqual(p['declared']['gloria_difference_intended'], GLORIA['difference_intended'])
        self.assertEqual(p['facts']['later_moves_of_his_before_her_reply'], 0)
        self.assertFalse(p['facts']['text_capped_at_12000'])
        for seen in self.word_calls():                                            # the field and self judges too
            self.assertIn('THE-DECIDING-END', seen)
        E._judge_realized({'goal': 'g', 'success_criterion': 'c', 'evidence_type': 'her_response'}, LONG_REPLY,
                          'b' * 1200 + ' HER-LAST-WORDS')                       # her words whole too: no 800 cut
        self.assertIn('b' * 1200 + ' HER-LAST-WORDS', self.word_calls()[-1])
        self.assertIn('THE-DECIDING-END', self.word_calls()[-1])
        row = self.rows()[-1]
        self.assertEqual(row['realized']['gloria'], 'YES')
        self.assertEqual((row['gloria_judge']['reason'], row['gloria_judge']['judge']), ('plain_yes', 'rubric'))
        self.assertEqual(row['adherence'], {'gloria': 'delivered'})
        self.assertNotIn('HER-LAST-WORDS', json.dumps(row['gloria_judge']))     # codes and counts only
        self.assertNotIn('synthetic move', json.dumps(row['gloria_judge']))
        self.assertEqual(PV._axis_history()['gloria']['YES'], 1)

    def test_a_move_he_did_not_make_is_his_failure_never_her_no(self):
        for adherence in ('not_delivered', 'partly', None):
            with self.subTest(adherence=adherence):
                Path(E.LEDGER).write_text('[]'); self.move()
                with self.sol(dict(SOL_YES, verdict='NO', reason='not_shown', adherence=adherence)):
                    E.resolve_previous(HER)
                row = self.rows()[-1]
                self.assertEqual((row['realized']['gloria'], row['gloria_judge']['reason']), ('NOT_JUDGEABLE', 'his_move_not_delivered'))
                self.assertEqual(row['adherence'], {'gloria': adherence})
                self.assertEqual(PV._axis_history()['gloria']['n'], 0)
        Path(E.LEDGER).write_text('[]'); self.move()
        with self.sol(dict(SOL_YES, verdict='NO', reason='not_shown')):            # he made it, she did not show it
            E.resolve_previous(HER)
        self.assertEqual(self.rows()[-1]['realized']['gloria'], 'NO')
        self.assertEqual((PV._axis_history()['gloria']['n'], PV._axis_history()['gloria']['NO']), (1, 1))

    def test_refusal_and_error_are_not_judgeable_settled_once_and_never_counted(self):
        for answer, reason in ((GJ.not_judgeable('refused', 'refused', 'refusal'), 'refused'),
                               (RuntimeError('fixture: sol is down'), 'error'),
                               ({'verdict': 'MAYBE'}, 'error')):
            with self.subTest(reason=reason, answer=str(answer)[:20]):
                Path(E.LEDGER).write_text('[]'); self.move(); self.verdict = 'YES'
                with self.sol(answer):
                    E.resolve_previous(HER); E.resolve_previous(HER)
                    self.assertEqual(len(self.packets), 1)                        # never asked again, never retried
                row = self.rows()[-1]
                self.assertEqual((row['realized']['gloria'], row['gloria_judge']['reason']), ('NOT_JUDGEABLE', reason))
                self.assertNotIn('gloria', row.get('held_reason') or {})
                self.assertEqual(PV._axis_history()['gloria']['n'], 0)
                self.assertEqual(PV._axis_history()['field']['YES'], 1)           # the other axes go on as before

    # ---- what code settles first ------------------------------------------------------------------------
    def test_her_reply_after_a_later_move_answers_that_move(self):
        self.move(); self.move()
        E.note_response(HER)
        first, second = self.rows()
        with self.sol(SOL_YES):
            E._resolve_row(first)
            self.assertEqual(self.packets, [])                                    # Sol is not asked
            E._resolve_row(self.rows()[1])
            self.assertEqual(len(self.packets), 1)
        first, second = self.rows()
        self.assertEqual((first['realized']['gloria'], first['gloria_judge']['reason'], first['gloria_judge']['later_moves']),
                         ('NOT_JUDGEABLE', 'reply_to_later_move', 1))
        self.assertEqual((second['realized']['gloria'], second['gloria_judge']['later_moves']), ('YES', 0))

    def test_a_photo_alone_is_unseen_and_decisive_words_beside_it_are_judged(self):
        self.move()
        with self.sol(SOL_YES):
            E.resolve_previous('GLORIA (now): (she sent a photo)')
            self.assertEqual(self.packets, [])
        row = self.rows()[-1]
        self.assertEqual((row['realized']['gloria'], row['gloria_judge']['reason'], row['gloria_judge']['her_media']),
                         ('NOT_JUDGEABLE', 'photo_unseen_decisive', True))
        for text, source in (('GLORIA (now): (she sent a photo) this one is for you', None),
                             ('GLORIA (now): this one is for you', 'photo')):
            with self.subTest(source=source):
                Path(E.LEDGER).write_text('[]'); self.move()
                with self.sol(SOL_YES):
                    E.resolve_previous(text, source=source)
                p, = self.packets
                self.assertEqual(p['her_next_reply'], 'this one is for you')
                self.assertTrue(p['facts']['her_next_reply_has_photo_or_media_unseen'])
                self.assertEqual(self.rows()[-1]['realized']['gloria'], 'YES')

    def test_window_binds_her_reply_time_and_a_missing_window_stays_missing(self):
        # past the 24 hours: no judge at all, and never a landing or a miss
        self.move(); E.note_response(HER)
        rows = self.rows(); rows[-1]['delivered_at'] = (datetime.now() - timedelta(hours=25)).isoformat()
        Path(E.LEDGER).write_text(json.dumps(rows))
        with self.sol(SOL_YES):
            E.resolve_previous()
            self.assertEqual(self.packets, [])
        self.assertNotIn(self.rows()[-1]['realized']['gloria'], ('YES', 'PARTIAL', 'NO'))
        self.assertEqual(PV._axis_history()['gloria']['n'], 0)
        # the rule itself, read on her reply's own time (no other move of his in the ledger)
        Path(E.LEDGER).write_text('[]')
        row = {'delivered_at': (datetime.now() - timedelta(hours=30)).isoformat(),
               'response_at': (datetime.now() - timedelta(hours=5)).isoformat(), 'input_text': 'Which?'}
        with self.sol(SOL_YES):
            got = E._judge_gloria(row, {}, copy.deepcopy(GLORIA), 'a move', 'GLORIA (now): yes')
            self.assertEqual(self.packets, [])
        self.assertEqual((got['verdict'], got['reason'], got['window']['hours'], got['window']['gap_hours']),
                         ('NOT_JUDGEABLE', 'window_expired', 24, 25.0))
        row['response_at'] = (datetime.now() - timedelta(hours=7)).isoformat()   # 23 hours: inside
        with self.sol(SOL_YES):
            self.assertEqual(E._judge_gloria(row, {}, copy.deepcopy(GLORIA), 'a move', 'GLORIA (now): yes')['verdict'], 'YES')
        # a historical row that never declared its window: read by the same 24 hours, and left undeclared
        Path(E.LEDGER).write_text('[]')
        old = {k: v for k, v in GLORIA.items() if k not in ('observation_window', 'evidence_type')}
        t = self.move(gloria=old)
        with self.sol(SOL_YES):
            E.resolve_previous(HER)
        p, = self.packets; row = self.rows()[-1]
        self.assertIsNone(p['declared']['observation_window']); self.assertFalse(p['facts']['window_declared_at_time'])
        self.assertEqual(row['gloria_judge']['window']['declared'], None)
        self.assertNotIn('observation_window', row['target']['gloria'])

    # ---- at selection -----------------------------------------------------------------------------------
    def test_a_criterion_she_already_met_is_refused_at_selection(self):
        self.answer = self.target(gloria=copy.deepcopy(GLORIA))
        stale = Mock(return_value='met')
        with patch.object(E, '_stale_gloria', stale):
            t = self.turn(resolve=False)
        (ax, words), _ = stale.call_args
        self.assertEqual((ax['difference_intended'], words), (GLORIA['difference_intended'], 'Which alternative would you choose?'))
        self.assertEqual(t['gloria'], {}); self.assertEqual(t['selection_check']['stale'], 'met')
        row = self.rows()[-1]
        self.assertEqual(row['realized']['gloria'], 'NOT_DECLARED')
        self.assertEqual(row['not_declared_reason']['gloria'], 'criterion_already_met')
        for answer in ('not_met', 'error', 'refused', 'budget'):                  # nothing refused on any other answer
            with self.subTest(answer=answer), patch.object(E, '_stale_gloria', return_value=answer):
                t = self.turn(resolve=False)
                self.assertEqual((t['gloria'], t['selection_check']['stale']), (GLORIA, answer))

    def test_the_stale_check_runs_only_on_her_own_live_turns(self):
        self.answer = self.target(gloria=copy.deepcopy(GLORIA))
        stale = Mock(return_value='met')
        with patch.object(E, '_stale_gloria', stale):
            t = self.select(persist=False)                                        # a preview: no paid call
            self.assertEqual(t['gloria'], GLORIA)
            self.select(BUTTON, her_source='gcs', resolve=False)                  # a device event is not her turn
        stale.assert_not_called()

    def test_stale_check_wrapper_needs_her_words_and_can_be_turned_off(self):
        with patch.object(GJ, 'stale_check', return_value='met') as sc:
            self.assertEqual(STALE_GLORIA(GLORIA, ''), 'skipped')
            with patch.dict(os.environ, GLORIA_STALE_CHECK='0'):
                self.assertEqual(STALE_GLORIA(GLORIA, 'yes'), 'off')
            self.assertEqual(STALE_GLORIA(GLORIA, 'yes'), 'met')
        sc.assert_called_once()
        with patch.object(GJ, 'stale_check', side_effect=RuntimeError('fixture')):
            self.assertEqual(STALE_GLORIA(GLORIA, 'yes'), 'error')

    def test_stale_check_is_bounded_on_her_turn_and_fails_open(self):
        import threading, time
        release = threading.Event(); self.addCleanup(release.set)
        def slow(ax, words):
            release.wait(10); return 'met'
        with patch.object(GJ, 'stale_check', slow), patch.object(E, 'GLORIA_STALE_BOUND', 0.3):
            t0 = time.monotonic()
            self.assertEqual(STALE_GLORIA(GLORIA, 'yes'), 'pending')
            self.assertLess(time.monotonic() - t0, 3)
        self.answer = self.target(gloria=copy.deepcopy(GLORIA))
        for how in (slow, Mock(side_effect=RuntimeError('fixture: sol is down'))):
            with self.subTest(how=getattr(how, '__name__', 'raises')), patch.object(E, '_stale_gloria', STALE_GLORIA), \
                    patch.object(GJ, 'stale_check', how), patch.object(E, 'GLORIA_STALE_BOUND', 0.3):
                t = self.turn(resolve=False)                                      # her turn goes on, normally
                self.assertEqual(t['gloria'], GLORIA)
                self.assertIn(t['selection_check']['stale'], ('pending', 'error'))

    def test_a_late_stale_answer_follows_the_move_and_settles_it_in_code(self):
        import threading, time
        release = threading.Event(); self.addCleanup(release.set)
        def slow(ax, words):
            release.wait(10); return 'met'
        self.answer = self.target(gloria=copy.deepcopy(GLORIA))
        with patch.object(E, '_stale_gloria', STALE_GLORIA), patch.object(GJ, 'stale_check', slow), \
                patch.object(E, 'GLORIA_STALE_BOUND', 0.3):
            t0 = time.monotonic(); t = self.turn(resolve=False)
            self.assertLess(time.monotonic() - t0, 3)
        self.assertEqual((t['gloria'], t['selection_check']['stale']), (GLORIA, 'pending'))   # nothing refused on her turn
        self.assertEqual(E._stale_late(t['intent_id']), '')
        release.set()
        for _ in range(100):
            if E._stale_late(t['intent_id']): break
            time.sleep(0.05)
        self.assertEqual(E._stale_late(t['intent_id']), 'met')                  # kept under the move's id
        with self.sol(SOL_YES):
            E.resolve_previous('GLORIA (now): a synthetic answer.')
            self.assertEqual(self.packets, [])                                    # settled in code, Sol not asked
        row = self.rows()[-1]
        self.assertEqual((row['realized']['gloria'], row['gloria_judge']['reason']), ('NOT_JUDGEABLE', 'criterion_already_met'))
        self.assertEqual(PV._axis_history()['gloria']['n'], 0)

    def test_an_incomplete_or_contradictory_landing_is_invalid_and_never_counted(self):
        """13 November review: a bare YES, or a PARTIAL whose reason says she never replied, had landed. Whoever
        answers, the engine keeps a landing only on a complete, self-consistent receipt."""
        for answer, why in (({'verdict': 'YES', 'status': 'ok'}, 'missing_reason'),
                            (dict(SOL_YES, verdict='PARTIAL', reason='no_her_reply'), 'reason_contradicts_verdict'),
                            (dict(SOL_YES, adherence=None), 'missing_adherence'),
                            (dict(SOL_YES, codes=['plain_yes', 'not_shown']), 'codes_contradict_verdict'),
                            (dict(SOL_YES, status='unparsed'), 'status_not_ok')):
            with self.subTest(why=why):
                Path(E.LEDGER).write_text('[]'); self.move()
                with self.sol(answer):
                    E.resolve_previous(HER)
                row = self.rows()[-1]
                self.assertEqual((row['realized']['gloria'], row['gloria_judge']['reason'], row['gloria_judge']['status'],
                                  row['gloria_judge']['detail']), ('NOT_JUDGEABLE', 'invalid', 'invalid', why))
                self.assertEqual(PV._axis_history()['gloria']['n'], 0)
        for adherence in ('partly', 'not_delivered'):                       # rule 5: she showed it anyway
            with self.subTest(adherence=adherence):
                Path(E.LEDGER).write_text('[]'); self.move()
                with self.sol(dict(SOL_YES, verdict='PARTIAL', reason='partial_one_part', codes=['partial_one_part'],
                                   adherence=adherence)):
                    E.resolve_previous(HER)
                self.assertEqual(self.rows()[-1]['realized']['gloria'], 'PARTIAL')
                self.assertEqual(PV._axis_history()['gloria']['PARTIAL'], 1)

    # ---- the judge off her turn --------------------------------------------------------------------------
    def blocking_sol(self, release):
        """A Sol that holds its answer until `release`; its packets are kept in self.packets."""
        self.packets = []
        def judge(packet):
            self.packets.append(packet)
            if not release.wait(10): raise AssertionError('fixture release timed out')
            return copy.deepcopy(SOL_YES)
        return patch.object(E, '_rubric_judge', judge)

    def test_her_turn_never_waits_on_sol_and_each_verdict_lands_once(self):
        import threading, time
        release = threading.Event(); self.addCleanup(release.set); self.addCleanup(E.resolver_wait, 15)
        self.answer = self.target(gloria=copy.deepcopy(GLORIA)); self.verdict = 'YES'
        first = self.move()
        with self.blocking_sol(release), patch.object(E, 'RESOLVE_IN_BACKGROUND', True):
            t0 = time.monotonic()
            self.turn(HER)                                                        # Sol is out on the earlier move
            self.turn('GLORIA (now): a second synthetic line.')                   # and a second turn meanwhile
            took = time.monotonic() - t0
            self.assertLess(took, 3)                                              # her turns did not wait on it
            rows = self.rows()
            self.assertEqual(rows[0]['intent_id'], first['intent_id'])
            self.assertIsNone(rows[0]['realized']['gloria'])                      # pending, her reply on it
            self.assertTrue(rows[0]['response_text'] and rows[0]['response_at'])
            self.assertEqual(len(self.packets), 1)                                # one resolver at a time
            release.set()
            self.assertTrue(E.resolver_wait(15))
            rows = self.rows()
            self.assertEqual([r['realized']['gloria'] for r in rows], ['YES', 'YES', None])   # each move once, the last waits
            self.assertEqual(len(self.packets), 2)
            self.assertFalse(any('resolution_dropped' in r for r in rows))
            E._kick_resolver(''); self.assertTrue(E.resolver_wait(15))           # nothing judged again
            self.assertEqual(len(self.packets), 2)
        keys = [c.args[3]['effect_key'] for c in sys.modules['outcome_join'].record.call_args_list]
        for r in rows[:2]:
            self.assertEqual(sum(k.startswith(r['intent_id'] + ':outcome') for k in keys), 1)
        self.assertEqual(PV._axis_history()['gloria']['YES'], 2)

    def test_a_restart_while_the_verdict_is_pending_judges_it_once_after(self):
        import signal, threading, time
        self.answer = self.target(gloria=copy.deepcopy(GLORIA)); self.verdict = 'YES'
        first = self.move()
        pid = os.fork()
        if pid == 0:                                                              # the process that goes down
            try:
                signal.alarm(60); done = threading.Event()
                def dying(packet):
                    done.wait(10); os._exit(7)                                    # it stops with Sol still out
                with patch.object(E, '_rubric_judge', dying), patch.object(E, 'RESOLVE_IN_BACKGROUND', True):
                    self.turn(HER); done.set(); time.sleep(20)
                os._exit(9)
            finally:
                os._exit(10)
        self.assertEqual(os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1]), 7)
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[0]['realized']['gloria']); self.assertTrue(rows[0]['response_text'])   # still pending
        with self.sol(SOL_YES), patch.object(E, 'RESOLVE_IN_BACKGROUND', True):  # the process that comes back
            self.turn('GLORIA (now): after the restart.')
            self.assertTrue(E.resolver_wait(15))
            self.assertEqual([r['realized']['gloria'] for r in self.rows()], ['YES', 'YES', None])   # both, on that one pass
            E._kick_resolver(''); self.assertTrue(E.resolver_wait(15))
        rows = self.rows()
        self.assertEqual(rows[0]['realized']['gloria'], 'YES')
        self.assertEqual(sum(p['his_reply'] == rows[0]['reply'] and p['her_next_reply'] == E._her_live_words(HER)
                             for p in self.packets), 1)                           # judged on her reply then, once
        keys = [c.args[3]['effect_key'] for c in sys.modules['outcome_join'].record.call_args_list]
        self.assertEqual(sum(k.startswith(first['intent_id'] + ':outcome') for k in keys), 1)

    def test_stale_switch_is_read_from_vintos_env_too(self):
        with patch.object(GJ, 'stale_check', return_value='met') as sc, \
                patch.object(GJ, '_env', lambda name, default='': '0' if name == 'GLORIA_STALE_CHECK' else default):
            self.assertEqual(STALE_GLORIA(GLORIA, 'yes'), 'off')
        sc.assert_not_called()

    def test_the_packet_carries_the_evidence_and_nothing_else(self):
        t = self.move(); self.verdict = 'YES'
        E.resolve_previous(HER)
        p, = self.sol_calls()
        self.assertEqual(set(p), {'declared', 'his_reply', 'her_message_he_replied_to', 'her_next_reply', 'facts'})
        self.assertEqual(set(p['declared']), {'gloria_difference_intended', 'gloria_enactment', 'observation_window',
                                              'field_state', 'overall_goal', 'overall_success_criterion', 'first_move'})
        row = self.rows()[-1]; seen = json.dumps(p)
        for private in (t['intent_id'], str(self.home), 'priority', 'turn_id'):
            self.assertNotIn(private, seen)

    # ---- the landing rate -------------------------------------------------------------------------------
    def test_landing_rate_ignores_not_judgeable_and_expired_rows(self):
        now = datetime.now()
        def row(verdict, axis='gloria', **extra):
            r = {'intent_id': uuid.uuid4().hex, 'status': 'delivered', 'timestamp': (now - timedelta(hours=40)).isoformat(),
                 'delivered_at': (now - timedelta(hours=40)).isoformat(), 'target': {'evidence_type': 'my_move'},
                 'realized': {'field': 'HELD', 'gloria': 'HELD', 'self': 'NOT_DECLARED'}}
            r['realized'][axis] = verdict; r.update(extra); return r
        late = (now - timedelta(hours=10)).isoformat()                            # 30 hours after delivery
        soon = (now - timedelta(hours=39)).isoformat()
        rows = [row('YES', response_at=soon),                                                  # counts
                row('NOT_JUDGEABLE', response_at=soon),
                row('NO', held_reason={'gloria': E.WINDOW_EXPIRED}),
                row('NO', response_at=late),                                                   # an old judge, a late reply
                row('NO', gloria_judge={'verdict': 'NOT_JUDGEABLE', 'reason': 'error'}),
                row('YES', 'field', held_reason={'field': E.WINDOW_EXPIRED}),
                row('NO', 'field', response_at=late, target={'evidence_type': 'her_response'}),
                row('NO', 'field', response_at=late)]                                          # his move: counts
        Path(E.LEDGER).write_text(json.dumps(rows))
        h = PV._axis_history()
        self.assertEqual((h['gloria']['n'], h['gloria']['YES']), (1, 1))
        self.assertEqual((h['field']['n'], h['field']['NO']), (1, 1))
        self.assertEqual(PV.WINDOW_EXPIRED, E.WINDOW_EXPIRED); self.assertEqual(PV.HER_REPLY_HOURS, E.DEVICE_WAIT_HOURS)


    def test_every_stale_check_outcome_is_counted_failures_and_late_answers_too(self):
        """14 November acceptance: the fail-open path refused nothing and counted nothing, so its failures were
        invisible. Each outcome is counted by day under fixed keys; a check still out at the bound counts pending,
        and its late answer counts again as late_<answer>."""
        import threading, time
        with patch.object(GJ, 'stale_check', return_value='met'):
            STALE_GLORIA(GLORIA, 'yes'); STALE_GLORIA(GLORIA, '')
        for raised in (RuntimeError('fixture'),):
            with patch.object(GJ, 'stale_check', side_effect=raised):
                self.assertEqual(STALE_GLORIA(GLORIA, 'yes'), 'error')
        with patch.object(GJ, 'stale_check', return_value='timeout'):
            self.assertEqual(STALE_GLORIA(GLORIA, 'yes'), 'timeout')
        release = threading.Event(); self.addCleanup(release.set)
        def slow(ax, words):
            release.wait(10); return 'timeout'
        with patch.object(GJ, 'stale_check', slow), patch.object(E, 'GLORIA_STALE_BOUND', 0.2):
            self.assertEqual(STALE_GLORIA(GLORIA, 'yes', intent_id='i1'), 'pending')
            self.assertEqual(E.stale_counts()['unresolved'], 1)
            release.set()
            for _ in range(100):
                if E.stale_counts().get('late_timeout'): break
                time.sleep(0.05)
        got = E.stale_counts()
        self.assertEqual({k: got.get(k, 0) for k in ('met', 'skipped', 'error', 'timeout', 'pending', 'late_timeout')},
                         {'met': 1, 'skipped': 1, 'error': 1, 'timeout': 1, 'pending': 1, 'late_timeout': 1})
        self.assertEqual((got['failed'], got['unresolved']), (3, 0))
        stored = json.dumps(E._load(E.GLORIA_STALE_COUNTS))
        self.assertNotIn('yes', stored); self.assertNotIn('i1', stored)                 # counts only, no words or ids


class FakeReply:
    def __init__(self, body): self.body = body
    def json(self):
        if isinstance(self.body, Exception): raise self.body
        return copy.deepcopy(self.body)


SONNET = 'claude-sonnet-5-5'


class SonnetTransport(unittest.TestCase):
    """gloria_judge itself, on Sonnet 5.5 through claude_cache: the call, its answer, its failures, its usage line
    and its cap."""
    def setUp(self):
        import claude_cache
        self.C = claude_cache
        tmp = tempfile.TemporaryDirectory(prefix='gloria-judge-'); self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('OPENAI', 'ANTHROPIC', 'GLORIA_JUDGE'))}
        env.update(HOME=str(self.home), SPARK_WORKSPACE=str(self.home / '.vintos/workspace'),
                   VINTOS_ENV_FILE=str(self.home / 'no-vintos.env'), ANTHROPIC_API_KEY='sk-ant-api03-fixturekey0000')
        self.stack.enter_context(patch.dict(os.environ, env, clear=True))
        self.log = self.home / '.vintos/workspace/memory/anthropic-usage.jsonl'
        self.stack.enter_context(patch.object(claude_cache, 'USAGE', str(self.log)))
        self.stack.enter_context(patch('socket.socket.connect', side_effect=AssertionError('no socket may open')))
        self.sent = []; self.reply = None
        self.stack.enter_context(patch.object(GJ, '_post', self.transport))
        self.packet = {'declared': {'gloria_difference_intended': 'she names one want'}, 'his_reply': 'a move',
                       'her_message_he_replied_to': 'before', 'her_next_reply': 'SYNTHETIC-HER-WORDS', 'facts': {}}

    def transport(self, url, timeout=None, json=None, headers=None):
        self.sent.append({'url': url, 'timeout': timeout, 'body': json, 'headers': headers})
        if isinstance(self.reply, Exception) and not isinstance(self.reply, ValueError): raise self.reply
        return FakeReply(self.reply)

    @staticmethod
    def answer(obj, usage=(3000, 15000, 0, 800), stop='end_turn'):
        text = obj if isinstance(obj, str) else json.dumps(obj)
        return {'type': 'message', 'model': SONNET, 'stop_reason': stop,
                'content': [{'type': 'text', 'text': text}] if text else [],
                'usage': {'input_tokens': usage[0], 'cache_read_input_tokens': usage[1],
                          'cache_creation_input_tokens': usage[2], 'output_tokens': usage[3]}}

    def usage(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []

    def write_usage(self, rows):
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text(''.join(json.dumps(r) + '\n' for r in rows))

    def test_one_call_to_sonnet_with_the_rubric_cached_and_thinking_off(self):
        self.reply = self.answer({'verdict': 'PARTIAL', 'reason': 'partial_hedged', 'codes': ['partial_hedged', 'bogus'],
                                  'his_adherence': 'delivered', 'confidence': 'medium'})
        got = GJ.judge(self.packet)
        self.assertEqual((got['verdict'], got['reason'], got['codes'], got['adherence'], got['model']),
                         ('PARTIAL', 'partial_hedged', ['partial_hedged'], 'delivered', SONNET))
        sent, = self.sent
        body = sent['body']
        self.assertEqual(sent['url'], 'https://api.anthropic.com/v1/messages')
        self.assertEqual(sent['headers']['x-api-key'], 'sk-ant-api03-fixturekey0000')
        self.assertEqual(sent['timeout'], GJ.JUDGE_TIMEOUT)
        self.assertEqual((body['model'], body['max_tokens']), (SONNET, GJ.JUDGE_MAX_TOKENS))
        self.assertEqual(body['system'], [{'type': 'text', 'text': GJ.RUBRIC,
                                           'cache_control': {'type': 'ephemeral', 'ttl': '1h'}}])   # cached
        part, = body['messages'][0]['content']
        self.assertEqual(json.loads(part['text']), self.packet); self.assertNotIn('cache_control', part)
        self.assertEqual(body['thinking'], self.C.thinking_off(SONNET))                            # his rule
        self.assertIsNotNone(body['thinking']); self.assertNotIn('output_config', body)
        line, = self.usage()
        self.assertEqual((line['caller'], line['model'], line['in'], line['cache_read'], line['cache_write'], line['out']),
                         ('gloria-judge', SONNET, 3000, 15000, 0, 800))
        logged = json.dumps(self.usage())
        self.assertNotIn('fixturekey', logged); self.assertNotIn('SYNTHETIC-HER-WORDS', logged)
        self.assertAlmostEqual(GJ.spent(GJ.LIVE_SRCS), (3000 * 2.0 + 15000 * 0.10 + 800 * 10.0) / 1e6)   # $0.0155
        self.assertEqual(GJ.spent(['gloria-judge-teacher']), 0.0)

    def test_sonnet_cache_reads_are_priced_at_ten_cents(self):
        self.assertEqual(self.C.PRICES[SONNET], (2.0, 10.0, 0.10))
        row = {'model': SONNET, 'in': 0, 'cache_read': 1_000_000, 'cache_write': 0, 'out': 0}
        self.assertAlmostEqual(self.C.cost(row), 0.10)

    def test_refusals_and_errors_are_not_judgeable(self):
        cases = [(self.answer('', stop='refusal'), 'refused'),
                 ({'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'flagged by safety system'}}, 'refused'),
                 ({'type': 'error', 'error': {'type': 'overloaded_error', 'message': 'Overloaded'}}, 'error'),
                 (TimeoutError('fixture'), 'error'),
                 (ValueError('fixture: not JSON'), 'error'),
                 (self.answer('', stop='max_tokens'), 'error'),
                 (self.answer('no object here'), 'error'),
                 (self.answer({'verdict': 'PROBABLY'}), 'error')]
        for reply, reason in cases:
            with self.subTest(reply=str(reply)[:60]):
                self.reply = reply
                got = GJ.judge(self.packet)
                self.assertEqual((got['verdict'], got['reason']), ('NOT_JUDGEABLE', reason))
        self.assertEqual(len(self.sent), len(cases))                                          # nothing retried

    def test_her_no_on_a_move_not_delivered_is_not_judgeable(self):
        for adherence in ('not_delivered', 'partly', 'unknown'):
            with self.subTest(adherence=adherence):
                self.reply = self.answer({'verdict': 'NO', 'reason': 'not_shown', 'his_adherence': adherence})
                got = GJ.judge(self.packet)
                self.assertEqual((got['verdict'], got['reason']), ('NOT_JUDGEABLE', 'his_move_not_delivered'))
        self.reply = self.answer({'verdict': 'NO', 'reason': 'declined', 'his_adherence': 'delivered'})
        self.assertEqual(GJ.judge(self.packet)['verdict'], 'NO')

    def test_an_answer_that_is_no_complete_receipt_is_invalid(self):
        """13 November review: parse checked only the verdict word, so {"verdict": "YES"} came back YES with status
        ok. A receipt needs its verdict's own reason, his adherence on a landing, and no code of another verdict."""
        full = {'verdict': 'YES', 'reason': 'plain_yes', 'codes': ['plain_yes'], 'his_adherence': 'delivered',
                'confidence': 'high'}
        cases = [({'verdict': 'YES'}, 'missing_reason'),
                 ({'verdict': 'PARTIAL', 'reason': 'no_her_reply'}, 'reason_contradicts_verdict'),
                 (dict(full, verdict='PARTIAL', reason='no_her_reply', codes=['no_her_reply']), 'reason_contradicts_verdict'),
                 (dict(full, reason='made_up'), 'unlisted_reason'),
                 (dict(full, reason=['plain_yes']), 'missing_reason'),
                 ({k: v for k, v in full.items() if k != 'his_adherence'}, 'missing_adherence'),
                 (dict(full, his_adherence='mostly'), 'bad_adherence'),
                 (dict(full, codes='plain_yes'), 'bad_codes'),
                 (dict(full, codes=['plain_yes', 'his_move_not_delivered']), 'codes_contradict_verdict'),
                 (dict(full, verdict='PARTIAL', reason='partial_hedged', codes=['plain_yes']), 'codes_contradict_verdict'),
                 (dict(full, confidence='certain'), 'bad_confidence'),
                 (dict(full, verdict='NO', reason='plain_yes'), 'reason_contradicts_verdict'),
                 (dict(full, verdict='NO', reason='not_shown', his_adherence='partly', codes=['plain_yes']),
                  'codes_contradict_verdict'),
                 (dict(full, verdict='NOT_JUDGEABLE', reason='his_move_not_delivered', codes=['his_move_not_delivered']),
                  'adherence_contradicts_reason'),
                 (dict(full, verdict='NOT_JUDGEABLE', reason='plain_yes'), 'reason_contradicts_verdict')]
        for raw, why in cases:
            with self.subTest(raw=raw):
                self.reply = self.answer(raw)
                got = GJ.judge(self.packet)
                self.assertEqual((got['verdict'], got['reason'], got['status'], got['detail']),
                                 ('NOT_JUDGEABLE', 'invalid', 'invalid', why))
        kept = [(full, 'YES', 'plain_yes'),
                (dict(full, his_adherence='not_delivered'), 'YES', 'plain_yes'),          # her difference happened anyway
                (dict(full, verdict='PARTIAL', reason='partial_one_part', codes=['partial_one_part', 'long_gap'],
                      his_adherence='partly', confidence='low'), 'PARTIAL', 'partial_one_part'),
                (dict(full, reason='intimate_phrasing_counts', codes=['plain_yes', 'intimate_phrasing_counts', 'photo_unseen']),
                 'YES', 'intimate_phrasing_counts'),
                ({k: v for k, v in full.items() if k != 'confidence'}, 'YES', 'plain_yes'),
                (dict(full, verdict='NO', reason='deflected', codes=['deflected', 'text_capped']), 'NO', 'deflected'),
                ({'verdict': 'NOT_JUDGEABLE', 'reason': 'no_her_reply'}, 'NOT_JUDGEABLE', 'no_her_reply')]
        for raw, verdict, reason in kept:
            with self.subTest(kept=raw):
                self.reply = self.answer(raw)
                got = GJ.judge(self.packet)
                self.assertEqual((got['verdict'], got['reason'], got['status']), (verdict, reason, 'ok'))
                self.assertEqual(GJ.problem(got), '')

    def test_his_undelivered_move_keeps_its_receipt_and_adherence(self):
        """13 November re-review: under rule 5 her reply did not show the difference on a move he did not (fully)
        make, so a NOT_JUDGEABLE his_move_not_delivered that also lists not_shown / deflected / declined, or a NO
        that lists his_move_not_delivered, is that rule said plainly - not a contradiction. It stays his adherence
        failure, with his adherence kept, never "invalid"."""
        base = {'reason': 'his_move_not_delivered', 'confidence': 'high'}
        for raw in (dict(base, verdict='NOT_JUDGEABLE', codes=['his_move_not_delivered', 'not_shown'], his_adherence='partly'),
                    dict(base, verdict='NOT_JUDGEABLE', codes=['his_move_not_delivered', 'deflected', 'long_gap'],
                         his_adherence='not_delivered'),
                    {'verdict': 'NO', 'reason': 'not_shown', 'codes': ['not_shown', 'his_move_not_delivered'],
                     'his_adherence': 'partly', 'confidence': 'medium'}):
            with self.subTest(raw=raw):
                self.reply = self.answer(raw)
                got = GJ.judge(self.packet)
                self.assertEqual((got['verdict'], got['reason'], got['status'], got['adherence']),
                                 ('NOT_JUDGEABLE', 'his_move_not_delivered', 'ok', raw['his_adherence']))
        for raw in (dict(base, verdict='NOT_JUDGEABLE', codes=['no_her_reply', 'not_shown'], reason='no_her_reply'),
                    {'verdict': 'NO', 'reason': 'not_shown', 'codes': ['not_shown', 'his_move_not_delivered'],
                     'his_adherence': 'delivered'}):
            with self.subTest(still_invalid=raw):
                self.reply = self.answer(raw)
                got = GJ.judge(self.packet)
                self.assertEqual((got['verdict'], got['reason'], got['detail']),
                                 ('NOT_JUDGEABLE', 'invalid', 'codes_contradict_verdict'))

    def test_no_key_or_paused_calls_send_nothing(self):
        with patch.dict(os.environ, ANTHROPIC_API_KEY=''):
            got = GJ.judge(self.packet)
        self.assertEqual((got['verdict'], got['reason'], got['detail']), ('NOT_JUDGEABLE', 'error', 'no_key'))
        (self.home / '.vintos').mkdir(parents=True, exist_ok=True); (self.home / '.vintos/paid-outbound.paused').write_text('')
        got = GJ.judge(self.packet)
        self.assertEqual((got['reason'], got['detail']), ('error', 'paid_paused'))
        self.assertEqual(GJ.stale_check({'difference_intended': 'x'}, 'words'), 'error')
        self.assertEqual(self.sent, [])

    def test_the_weekly_cap_is_priced_for_sonnet_and_stops_the_live_judge(self):
        at = lambda hours: time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time() - hours * 3600))
        row = lambda hours, caller, **t: dict({'at': at(hours), 'caller': caller, 'model': SONNET, 'in': 0,
                                               'cache_read': 0, 'cache_write': 0, 'out': 0}, **t)
        self.write_usage([row(1, 'gloria-judge', **{'in': 1_000_000}),                  # $2.00
                          row(2, 'gloria-judge-stale', cache_read=10_000_000),          # $1.00 at $0.10 a million
                          row(3, 'slack:claude-sonnet-5-5', **{'in': 9_000_000}),       # another caller
                          row(8 * 24, 'gloria-judge', **{'in': 9_000_000})])            # last week
        self.assertAlmostEqual(GJ.spent(GJ.LIVE_SRCS), 3.0)
        self.assertEqual(GJ.LIVE_WEEKLY_USD, 3.5)
        self.reply = self.answer({'verdict': 'YES', 'reason': 'plain_yes', 'his_adherence': 'delivered'})
        with patch.dict(os.environ, GLORIA_JUDGE_WEEKLY_USD='3'):
            got = GJ.judge(self.packet)
            self.assertEqual((got['verdict'], got['reason']), ('NOT_JUDGEABLE', 'budget'))
            self.assertEqual(GJ.stale_check({'difference_intended': 'x'}, 'words'), 'budget')
        self.assertEqual(self.sent, [])
        self.assertEqual(GJ.judge(self.packet)['verdict'], 'YES')                # under the default $3.50
        self.write_usage([row(1, 'gloria-judge', **{'in': 2_000_000})])           # $4.00: over the default
        self.assertEqual(GJ.judge(self.packet)['reason'], 'budget')

    def test_the_model_stays_on_claude(self):
        self.assertEqual(GJ.MODEL_DEFAULT, SONNET)
        for setting, want in (('', SONNET), ('gpt-6.1-sol', SONNET), ('claude-haiku-5-5', 'claude-haiku-5-5')):
            with self.subTest(setting=setting), patch.dict(os.environ, GLORIA_JUDGE_MODEL=setting):
                self.assertEqual(GJ.model(), want)
        row = {'model': 'claude-unpriced-9', 'in': 1_000_000, 'cache_read': 0, 'cache_write': 0, 'out': 0}
        self.assertAlmostEqual(GJ.cost(row), 2.0)                                 # never free to the cap

    def test_stale_check_answers_met_or_not_on_sonnet(self):
        for raw, want in (({'already_met': True}, 'met'), ({'already_met': False}, 'not_met'), ({'already_met': 'yes'}, 'error')):
            with self.subTest(raw=raw):
                self.reply = self.answer(raw)
                self.assertEqual(GJ.stale_check({'difference_intended': 'she names one want'}, 'I want this'), want)
        body = self.sent[-1]['body']
        self.assertEqual((body['model'], body['max_tokens']), (SONNET, GJ.STALE_MAX_TOKENS))
        self.assertEqual(body['system'][0]['text'], GJ.STALE_RUBRIC)
        self.assertEqual(body['thinking'], self.C.thinking_off(SONNET))
        self.assertEqual(json.loads(body['messages'][0]['content'][0]['text'])['her_message'], 'I want this')
        self.assertEqual(self.sent[-1]['timeout'], GJ.STALE_TIMEOUT)
        n = len(self.sent)
        self.assertEqual(GJ.stale_check({'difference_intended': 'x'}, '  '), 'skipped'); self.assertEqual(len(self.sent), n)
        self.assertEqual(self.usage()[-1]['caller'], 'gloria-judge-stale')
        self.reply = self.answer('', stop='refusal')
        self.assertEqual(GJ.stale_check({'difference_intended': 'x'}, 'words'), 'refused')


    def test_a_timed_out_call_stays_counted_and_the_cap_is_hard(self):
        """14 November acceptance: a call that timed out may have been charged with no usage line, so the cap read
        from the usage log alone could be overspent. Each call reserves its ceiling first; an answered call settles
        to its usage line, one never sent is released, and one whose outcome is unknown stays counted."""
        self.reply = TimeoutError('fixture: no answer in time')
        got = GJ.judge(self.packet)
        self.assertEqual((got['reason'], got['detail']), ('error', 'TimeoutError'))
        self.assertEqual(GJ.stale_check({'difference_intended': 'x'}, 'words'), 'timeout')   # counted apart
        b = GJ.budget()
        self.assertEqual((b['logged_usd'], b['open_n'], b['uncertain_n']), (0.0, 0, 2))
        ceil = GJ.ceiling(GJ.RUBRIC, json.dumps(self.packet, ensure_ascii=False), GJ.JUDGE_MAX_TOKENS)
        self.assertGreater(b['uncertain_usd'], ceil)                                    # both ceilings counted
        self.assertEqual(b['counted_usd'], round(b['uncertain_usd'], 4))
        # an answered call settles: its usage line is the spend, the reservation no longer counts
        self.reply = self.answer({'verdict': 'YES', 'reason': 'plain_yes', 'his_adherence': 'delivered'})
        self.assertEqual(GJ.judge(self.packet)['verdict'], 'YES')
        b2 = GJ.budget()
        self.assertEqual((b2['open_n'], b2['uncertain_n']), (0, 2))
        self.assertAlmostEqual(b2['logged_usd'], 0.0155)
        # paid calls paused: nothing sent, the reservation released
        (self.home / '.vintos').mkdir(parents=True, exist_ok=True); (self.home / '.vintos/paid-outbound.paused').write_text('')
        GJ.judge(self.packet); (self.home / '.vintos/paid-outbound.paused').unlink()
        self.assertEqual(GJ.budget()['uncertain_n'], 2)
        # the cap: logged + uncertain + this call's ceiling may not pass it; the timed-out spend now decides
        cap = b2['counted_usd'] + 0.0001                                              # less than either ceiling
        n = len(self.sent)
        with patch.dict(os.environ, GLORIA_JUDGE_WEEKLY_USD=str(cap)):
            self.assertEqual(GJ.judge(self.packet)['reason'], 'budget')
            self.assertEqual(GJ.stale_check({'difference_intended': 'x'}, 'words'), 'budget')
        self.assertEqual(len(self.sent), n)
        rows = (self.home / '.vintos/workspace/memory' / GJ.RESERVE_LOG).read_text()
        self.assertNotIn('SYNTHETIC-HER-WORDS', rows); self.assertNotIn('fixturekey', rows)

    def test_a_call_that_never_connected_is_released_not_held_for_the_week(self):
        """Review 14 November: a refused connection or an unresolved name never reached the provider, so nothing
        was charged; held at its ceiling for 7 days, a network outage would shut the allowance with nothing spent.
        A connection dropped after sending stays uncertain."""
        import requests
        from urllib3.exceptions import MaxRetryError, NewConnectionError, ProtocolError
        never = requests.exceptions.ConnectionError(MaxRetryError(None, '/v1/messages',
                                                                  NewConnectionError(None, 'fixture: refused')))
        self.reply = never
        self.assertEqual(GJ.judge(self.packet)['detail'], 'ConnectionError')
        self.reply = requests.exceptions.ConnectTimeout('fixture')
        GJ.judge(self.packet)
        b = GJ.budget()
        self.assertEqual((b['open_n'], b['uncertain_n'], b['counted_usd']), (0, 0, 0.0))
        self.reply = requests.exceptions.ConnectionError(ProtocolError('Connection aborted.', ConnectionResetError()))
        GJ.judge(self.packet)
        self.assertEqual(GJ.budget()['uncertain_n'], 1)                                # it may have been charged

    def test_reservations_in_flight_count_so_two_callers_cannot_both_take_the_last_of_it(self):
        import threading
        ceil = GJ.ceiling(GJ.RUBRIC, json.dumps(self.packet, ensure_ascii=False), GJ.JUDGE_MAX_TOKENS)
        inside = threading.Event(); release = threading.Event(); self.addCleanup(release.set)
        def hold(url, timeout=None, json=None, headers=None):
            self.sent.append(1); inside.set(); release.wait(10)
            return FakeReply(self.answer({'verdict': 'YES', 'reason': 'plain_yes', 'his_adherence': 'delivered'}))
        self.stack.enter_context(patch.object(GJ, '_post', hold))
        out = {}
        with patch.dict(os.environ, GLORIA_JUDGE_WEEKLY_USD=str(ceil * 1.5)):
            t = threading.Thread(target=lambda: out.setdefault('a', GJ.judge(self.packet))); t.start()
            self.assertTrue(inside.wait(5))
            self.assertEqual(GJ.budget()['open_n'], 1)                                  # in flight, counted
            self.assertEqual(GJ.judge(self.packet)['reason'], 'budget')                 # the second is refused
            release.set(); t.join(5)
        self.assertEqual(out['a']['verdict'], 'YES'); self.assertEqual(len(self.sent), 1)
        self.assertEqual(GJ.budget()['open_n'], 0)


if __name__ == '__main__':
    unittest.main()

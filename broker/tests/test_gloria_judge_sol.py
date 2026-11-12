"""Her axis judged by Sol (Gloria, 12 November): the rubric judge on gpt-6.1-sol, what code settles before it is
asked, his adherence apart from her verdict, whole texts, a stale criterion refused at selection, and a landing
rate that never counts a NOT_JUDGEABLE or an expired row. Scratch stores, synthetic text and a fixture transport
only: no model is asked, no socket opened, nothing sent."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
import urllib.error
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
        return patch.object(E, '_sol_judge', judge)

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
        self.assertEqual((row['gloria_judge']['reason'], row['gloria_judge']['judge']), ('plain_yes', 'sol'))
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

    # ---- the judge off her turn --------------------------------------------------------------------------
    def blocking_sol(self, release):
        """A Sol that holds its answer until `release`; its packets are kept in self.packets."""
        self.packets = []
        def judge(packet):
            self.packets.append(packet)
            if not release.wait(10): raise AssertionError('fixture release timed out')
            return copy.deepcopy(SOL_YES)
        return patch.object(E, '_sol_judge', judge)

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
                with patch.object(E, '_sol_judge', dying), patch.object(E, 'RESOLVE_IN_BACKGROUND', True):
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


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): self.close()


class SolTransport(unittest.TestCase):
    """gloria_judge itself: the call, its answer, its failures, its usage line and its cap."""
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='gloria-judge-'); self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('OPENAI', 'GLORIA_JUDGE'))}
        env.update(HOME=str(self.home), OPENAI_API_KEY='sk-fixture-not-a-key')
        self.stack.enter_context(patch.dict(os.environ, env, clear=True))
        self.stack.enter_context(patch('socket.socket.connect', side_effect=AssertionError('no socket may open')))
        self.sent = []; self.reply = None
        self.stack.enter_context(patch('urllib.request.urlopen', self.transport))
        self.packet = {'declared': {'gloria_difference_intended': 'she names one want'}, 'his_reply': 'a move',
                       'her_message_he_replied_to': 'before', 'her_next_reply': 'SYNTHETIC-HER-WORDS', 'facts': {}}

    def transport(self, req, timeout=None):
        self.sent.append((req, json.loads(req.data)))
        if isinstance(self.reply, Exception): raise self.reply
        return FakeResponse(json.dumps(self.reply).encode())

    @staticmethod
    def answer(obj, usage=(3000, 200, 2000), kind='output_text'):
        part = {'type': kind, kind if kind == 'refusal' else 'text': obj if isinstance(obj, str) else json.dumps(obj)}
        return {'status': 'completed', 'output': [{'type': 'reasoning'}, {'type': 'message', 'content': [part]}],
                'usage': {'input_tokens': usage[0], 'output_tokens': usage[1], 'input_tokens_details': {'cached_tokens': usage[2]}}}

    def usage(self):
        p = self.home / '.vintos/logs/openai-usage.jsonl'
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

    def test_one_call_to_sol_with_the_rubric_and_its_answer_recorded(self):
        self.reply = self.answer({'verdict': 'PARTIAL', 'reason': 'partial_hedged', 'codes': ['partial_hedged', 'bogus'],
                                  'his_adherence': 'delivered', 'confidence': 'medium'})
        got = GJ.judge(self.packet)
        self.assertEqual((got['verdict'], got['reason'], got['codes'], got['adherence'], got['model']),
                         ('PARTIAL', 'partial_hedged', ['partial_hedged'], 'delivered', 'gpt-6.1-sol'))
        (req, body), = self.sent
        self.assertEqual(req.full_url, 'https://api.openai.com/v1/responses')
        self.assertEqual(body['model'], 'gpt-6.1-sol')
        self.assertEqual(body['input'][0], {'role': 'system', 'content': GJ.RUBRIC})
        self.assertEqual(json.loads(body['input'][1]['content']), self.packet)
        line, = self.usage()
        self.assertEqual((line['src'], line['model'], line['in'], line['out'], line['cached']), ('gloria-judge', 'gpt-6.1-sol', 3000, 200, 2000))
        logged = json.dumps(self.usage())
        self.assertNotIn('sk-fixture', logged); self.assertNotIn('SYNTHETIC-HER-WORDS', logged)
        self.assertAlmostEqual(GJ.spent(GJ.LIVE_SRCS), (1000 * 5.0 + 2000 * 0.5 + 200 * 40.0) / 1e6)
        self.assertEqual(GJ.spent([GJ.SRC_TEACHER]), 0.0)

    def test_refusals_and_errors_are_not_judgeable(self):
        cases = [(self.answer('I cannot help with that.', kind='refusal'), 'refused'),
                 (urllib.error.HTTPError(GJ.ENDPOINT, 400, 'bad', {}, io.BytesIO(json.dumps({'error': {'code': 'content_policy_violation'}}).encode())), 'refused'),
                 (urllib.error.HTTPError(GJ.ENDPOINT, 500, 'down', {}, io.BytesIO(b'{}')), 'error'),
                 (TimeoutError('fixture'), 'error'),
                 (self.answer('no object here'), 'error'),
                 (self.answer({'verdict': 'PROBABLY'}), 'error'),
                 ({'error': {'message': 'flagged by safety system'}}, 'refused'),
                 ({'status': 'incomplete', 'output': []}, 'error')]
        for reply, reason in cases:
            with self.subTest(reply=str(reply)[:60]):
                self.reply = reply
                got = GJ.judge(self.packet)
                self.assertEqual((got['verdict'], got['reason']), ('NOT_JUDGEABLE', reason))

    def test_her_no_on_a_move_not_delivered_is_not_judgeable(self):
        for adherence in ('not_delivered', 'partly', 'unknown'):
            with self.subTest(adherence=adherence):
                self.reply = self.answer({'verdict': 'NO', 'reason': 'not_shown', 'his_adherence': adherence})
                got = GJ.judge(self.packet)
                self.assertEqual((got['verdict'], got['reason']), ('NOT_JUDGEABLE', 'his_move_not_delivered'))
        self.reply = self.answer({'verdict': 'NO', 'reason': 'declined', 'his_adherence': 'delivered'})
        self.assertEqual(GJ.judge(self.packet)['verdict'], 'NO')

    def test_no_key_or_paused_calls_send_nothing(self):
        with patch.dict(os.environ, OPENAI_API_KEY=''):
            got = GJ.judge(self.packet)
        self.assertEqual((got['verdict'], got['reason'], got['detail']), ('NOT_JUDGEABLE', 'error', 'no_key'))
        (self.home / '.vintos').mkdir(parents=True, exist_ok=True); (self.home / '.vintos/paid-outbound.paused').write_text('')
        got = GJ.judge(self.packet)
        self.assertEqual((got['reason'], got['detail']), ('error', 'paid_paused'))
        self.assertEqual(self.sent, [])

    def test_the_weekly_cap_stops_the_live_judge(self):
        log = self.home / '.vintos/logs/openai-usage.jsonl'; log.parent.mkdir(parents=True)
        import time
        rows = [{'ts': time.time() - 3600, 'src': 'gloria-judge', 'model': 'gpt-6.1-sol', 'in': 1_000_000, 'out': 0, 'cached': 0},
                {'ts': time.time() - 8 * 86400, 'src': 'gloria-judge', 'model': 'gpt-6.1-sol', 'in': 9_000_000, 'out': 0, 'cached': 0}]
        log.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        self.assertEqual(GJ.spent(GJ.LIVE_SRCS), 5.0)                            # the week only
        self.reply = self.answer({'verdict': 'YES', 'reason': 'plain_yes', 'his_adherence': 'delivered'})
        with patch.dict(os.environ, GLORIA_JUDGE_WEEKLY_USD='5'):
            got = GJ.judge(self.packet)
            self.assertEqual((got['verdict'], got['reason']), ('NOT_JUDGEABLE', 'budget'))
            self.assertEqual(GJ.stale_check({'difference_intended': 'x'}, 'words'), 'budget')
        self.assertEqual(self.sent, [])
        self.assertEqual(GJ.judge(self.packet)['verdict'], 'YES')                # under the default $8

    def test_vintos_env_prices_override_the_estimate(self):
        log = self.home / '.vintos/logs/openai-usage.jsonl'; log.parent.mkdir(parents=True)
        import time
        log.write_text(json.dumps({'ts': time.time(), 'src': 'gloria-judge', 'in': 1_000_000, 'out': 1_000_000, 'cached': 0}) + '\n')
        self.assertEqual(GJ.spent(GJ.LIVE_SRCS), 45.0)                           # the high default estimate
        with patch.dict(os.environ, GLORIA_JUDGE_PRICE_IN='1.25', GLORIA_JUDGE_PRICE_OUT='10'):
            self.assertEqual(GJ.spent(GJ.LIVE_SRCS), 11.25)
        with patch.dict(os.environ, GLORIA_JUDGE_PRICE_IN='not-a-number'):
            self.assertEqual(GJ.spent(GJ.LIVE_SRCS), 45.0)                       # a bad value keeps the estimate

    def test_stale_check_answers_met_or_not(self):
        for raw, want in (({'already_met': True}, 'met'), ({'already_met': False}, 'not_met'), ({'already_met': 'yes'}, 'error')):
            with self.subTest(raw=raw):
                self.reply = self.answer(raw)
                self.assertEqual(GJ.stale_check({'difference_intended': 'she names one want'}, 'I want this'), want)
        req, body = self.sent[-1]
        self.assertEqual(body['input'][0]['content'], GJ.STALE_RUBRIC)
        self.assertEqual(json.loads(body['input'][1]['content'])['her_message'], 'I want this')
        n = len(self.sent)
        self.assertEqual(GJ.stale_check({'difference_intended': 'x'}, '  '), 'skipped'); self.assertEqual(len(self.sent), n)
        self.assertEqual(self.usage()[-1]['src'], 'gloria-judge-stale')


if __name__ == '__main__':
    unittest.main()

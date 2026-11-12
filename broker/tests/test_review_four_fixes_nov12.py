"""Four fixes from the 12 November live review. Scratch stores, fixture providers and synthetic text only.

1. The wants-for-her carrier reaches the avatar chat, the route all her conversations since the deploy came by.
2. A selector reply that is not clean JSON no longer drops her intent turn: what parses is read, a dominant axis
   left out is HELD with its reason, and a reply with nothing in it is kept as one counted failure row.
3. The want lane paces its daily calls over the day instead of spending them in the first half hour.
4. A gravitational override spent on a turn that then failed is given back.
"""
import contextlib
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import conversation_wants as C
import intent_engine as E
import desired_difference as DD
import priority_vector as PV
import want_work_budget as B
import want_agent as WA
import want_working_thread as W
import test_intent_fields_fix as F

SERVER = (REPO / 'bin' / 'server.py').read_text()
CHI = ZoneInfo('America/Chicago')


def at(hour, minute=5, day=12):
    return datetime(2026, 11, day, hour, minute, tzinfo=CHI).timestamp()


# ---- 1. the carrier in the avatar chat ---------------------------------------------------------------------
class CarrierInAvatarChat(unittest.TestCase):
    NOW = datetime(2026, 11, 12, 9, 0)

    def want(self, i, text, hours_ago, **kw):
        w = {'id': 'w%02d' % i, 'want': text, 'source': 'idle-journal', 'fulfilled': False,
             'timestamp': (self.NOW - timedelta(hours=hours_ago)).isoformat()}
        w.update(kw); return w

    def store(self, wants):
        d = tempfile.TemporaryDirectory(prefix='cw-avatar-'); self.addCleanup(d.cleanup)
        p = Path(d.name) / 'current-wants.json'; p.write_text(json.dumps(wants)); return str(p)

    def test_reads_the_store_with_the_same_caps_and_rules(self):
        asks = [self.want(i, 'I want to ask you about synthetic frame %d tonight.' % i, i + 1) for i in range(8)]
        tells = [self.want(20 + i, 'I want to tell you that synthetic test %d passed.' % i, 2 + i) for i in range(8)]
        letter = self.want(40, 'I want to ask you the synthetic letter question.', 1, source='email')
        old = self.want(41, 'I want to ask you the synthetic old question.', 24 * (C.WINDOW_DAYS + 1))
        block = C.block_from_file(self.store(asks + tells + [letter, old]), self.NOW)
        lines = [l for l in block.splitlines() if l.startswith('- (since')]
        self.assertEqual(len(lines), C.LIMIT)
        self.assertEqual(sum('ask you' in l for l in lines), C.LIMIT_QUESTIONS)
        self.assertNotIn('letter question', block); self.assertNotIn('old question', block)
        self.assertEqual(block, C.block(asks + tells + [letter, old], self.NOW))     # the one rule, not a copy of it

    def test_only_his_own_wants_reach_her_chat(self):
        # review: with room under every cap, a want read out of someone else's words is still never carried
        mine = self.want(1, 'I want to ask you about the synthetic frame.', 2)
        others = [self.want(2, 'I want to ask you the synthetic email question.', 1, source='email'),
                  self.want(3, 'I want to tell you the synthetic letter promise.', 1, source='letter-promise'),
                  self.want(4, 'I want to tell you the synthetic post I read.', 1, source='moltbook'),
                  self.want(5, 'I want to ask you the synthetic adopted question.', 1, adopted_from='EC-00000000')]
        block = C.block_from_file(self.store([mine] + others), self.NOW)
        self.assertEqual([l for l in block.splitlines() if l.startswith('- (since')],
                         ['- (since 12 Nov 07:00) I want to ask you about the synthetic frame.'])

    def test_missing_or_broken_store_gives_nothing(self):
        self.assertEqual(C.block_from_file('/nonexistent/current-wants.json', self.NOW), '')
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        bad = Path(d.name) / 'w.json'; bad.write_text('{broken'); self.assertEqual(C.block_from_file(str(bad)), '')
        bad.write_text('{"not": "a list"}'); self.assertEqual(C.block_from_file(str(bad)), '')

    def test_avatar_route_builds_it_into_the_prompt(self):
        seg = SERVER[SERVER.index('@app.post("/api/avatar/chat")'):]
        seg = seg[:seg.index('system_prompt = f"""')]
        self.assertIn('block_from_file(os.path.join(MEMORY, "current-wants.json"))', seg)
        call = seg.index('block_from_file(')
        self.assertLess(seg.index('_ob_ga.open_between()'), call)
        self.assertIn('_durable_her_block = (_durable_her_block + "\\n\\n" + _av_cw_block)', seg[call:])
        prompt = SERVER[SERVER.index('system_prompt = f"""', SERVER.index('@app.post("/api/avatar/chat")')):]
        self.assertIn('{_durable_her_block}', prompt[:prompt.index('"""', 25)])

    def test_its_size_fits_the_avatar_prompt(self):
        # the avatar prompt has no cut of its own (the router sends anything over 60000 characters to a provider,
        # which it already is at 74000-99000); the carrier at its fullest is a small, bounded addition
        full = [self.want(i, 'I want to ask you ' + 'x' * 600 + '?', i + 1) for i in range(12)]
        block = C.block(full, self.NOW)
        self.assertLessEqual(len(block), 300 * C.LIMIT + 40 * C.LIMIT + 300)


# ---- 2 and 4. the intent turn that does not parse, and the override it spent ------------------------------
class SelectorFailures(unittest.TestCase):
    setUp = F.IntentFieldsFix.setUp
    respond = F.IntentFieldsFix.respond
    rows = F.IntentFieldsFix.rows
    target = F.IntentFieldsFix.target
    select = F.IntentFieldsFix.select
    press = F.IntentFieldsFix.press
    prow = staticmethod(F.IntentFieldsFix.prow)
    ledger = F.IntentFieldsFix.ledger
    low_receptivity = F.IntentFieldsFix.low_receptivity

    def rotation(self):
        p = Path(DD._rotation_path())
        return json.loads(p.read_text()) if p.exists() else {}

    def test_prose_reply_is_a_counted_failure_row_never_judged(self):
        self.press(**{F.A: self.prow(F.TEXT_A, 4.0)})
        self.answer = 'A synthetic reply in prose, with no object in it.'
        with self.assertRaisesRegex(E.SelectorUnreadable, 'no_json_object'): self.select(resolve=False)
        row, = self.rows()
        self.assertEqual(row['status'], 'failed'); self.assertEqual(E.FAILED_STATUS, 'failed')
        self.assertEqual(row['realized'], {'field': 'HELD', 'gloria': 'HELD', 'self': 'HELD'})
        self.assertEqual(set(row['held_reason'].values()), {'selector_failed_no_json_object'})
        self.assertEqual((row['failure']['code'], row['failure']['had_brace']), ('no_json_object', False))
        self.assertEqual(row['target']['primary_shown'], F.A)
        self.assertNotIn('A synthetic reply in prose', json.dumps(row))          # counts and codes only
        # the reservation stood and its failure is noted, as before - once
        self.assertEqual(self.rotation().get('failed_reservations'), 1)
        # her next turn resolves nothing on it: no judge is asked
        self.answer = self.target()
        self.select(F.HER)
        self.assertEqual(self.judge_calls, [])
        self.assertEqual(E.row_coverage(self.rows()[0]), 'undelivered')

    def test_slip_around_the_json_is_salvaged_and_accounted_once(self):
        self.press(**{F.A: self.prow(F.TEXT_A, 4.0)})
        body = json.dumps(dict(self.target(), **{'gloria': copy.deepcopy(F.GLORIA)}))
        # prose with a brace of its own before the object, a fence, and a second object after it
        self.answer = 'I choose {this} one:\n```json\n' + body + '\n```\n{"extra": true}'
        t = self.select(resolve=False)
        self.assertEqual(t['goal'], F.TARGET['goal'])
        self.assertEqual([r['status'] for r in self.rows()], ['selected'])
        self.assertEqual(self.rows()[0]['target']['primary_accounting'], 'reserved')
        self.assertFalse(self.rotation().get('failed_reservations'))           # a salvaged turn is no failure
        self.assertEqual(self.rotation().get('run'), 1)                         # and its showing counted once

    def test_stray_space_in_a_key_is_trimmed(self):
        self.answer = json.dumps(self.target()).replace('"goal"', '" goal"')
        self.assertEqual(self.select(resolve=False)['goal'], F.TARGET['goal'])

    def test_inner_axis_object_is_never_taken_for_the_target(self):
        self.answer = 'prose {"difference_intended": "x", "enactment": "y"} then } stray'
        with self.assertRaisesRegex(E.SelectorUnreadable, 'unparsed_json'): self.select(resolve=False)
        self.assertEqual(self.rows()[0]['failure']['had_brace'], True)

    def test_cut_off_target_is_salvaged_not_its_inner_axis_object(self):
        # review: a reply cut off after a complete axis object is the outer target salvaged, as before - the
        # complete inner object is never read as the target
        body = json.dumps(dict(self.target(), **{'gloria': copy.deepcopy(F.GLORIA)}))
        self.answer = body[:-1] + ', "campaign": {"destination": "unfinished'
        t = self.select(resolve=False)
        self.assertEqual((t['goal'], t['field_state']), (F.TARGET['goal'], F.TARGET['field_state']))
        self.assertEqual([r['status'] for r in self.rows()], ['selected'])

    def test_dominant_axis_left_out_is_held_with_its_reason(self):
        self.low_receptivity()                                                   # self carries 0.6: the dominant axis
        answer = self.target(gloria=copy.deepcopy(F.GLORIA)); answer['self'] = {}
        self.answers = [answer] * 2
        t = self.select(resolve=False)
        self.assertEqual(t['lead_fallback'], {'from': 'self', 'to': 'field'})
        self.assertEqual(t['selection_check']['axis_faults'], {'self': 'dominant_axis_omitted'})
        row = self.rows()[-1]
        self.assertEqual((row['status'], row['realized']['self'], row['held_reason']),
                         ('selected', 'HELD', {'self': 'dominant_axis_omitted'}))
        self.assertTrue(E.record_delivery('Here are both, and the tradeoff between them.', target=t, input_text='Which?'))
        self.verdict = 'YES'
        E.resolve_previous('GLORIA (now): I would take the second one.')
        row = self.rows()[-1]
        self.assertEqual(len(self.judge_calls), 2)                               # field and gloria; never self
        self.assertEqual((row['realized']['self'], row['held_reason']), ('HELD', {'self': 'dominant_axis_omitted'}))

    def test_override_spent_on_a_failed_turn_is_given_back(self):
        Path(PV.STATE).write_text(json.dumps({'neglect': {'field': 0.0, 'gloria': 1.6, 'self': 0.0}}))
        self.answer = 'no object at all'
        with self.assertRaises(E.SelectorUnreadable): self.select(resolve=False)
        self.assertEqual(self.rows()[0]['target']['priority_mode'], 'pressure')
        self.assertGreaterEqual(json.loads(Path(PV.STATE).read_text())['neglect']['gloria'], 1.5)
        self.answer = self.target(**{'gloria': copy.deepcopy(F.GLORIA)})
        t = self.select(resolve=False)
        self.assertEqual((t['priority_mode'], max(t['priority'], key=t['priority'].get)), ('pressure', 'gloria'))
        self.assertLess(json.loads(Path(PV.STATE).read_text())['neglect']['gloria'], 1.5)   # spent on a real turn
        # and a turn that succeeds keeps it spent: nothing is given back twice
        self.select(resolve=False)
        self.assertEqual(self.rows()[-1]['target']['priority_mode'], 'strategic')

    def test_failing_turns_cannot_pile_up_override_counts(self):
        # review: each failed turn re-forces the axis; its count is taken back, so three failures in a row neither
        # graduate a question nor leave counts behind, and one record is never given back twice
        Path(PV.STATE).write_text(json.dumps({'neglect': {'field': 0.0, 'gloria': 1.6, 'self': 0.0}}))
        self.answer = 'no object at all'
        for _ in range(3):
            with self.assertRaises(E.SelectorUnreadable): self.select(resolve=False)
        st = json.loads(Path(PV.STATE).read_text())
        self.assertEqual(st['override_counts']['gloria'], 0)
        self.assertGreaterEqual(st['neglect']['gloria'], 1.5)
        self.assertNotIn('graduated', ''.join(r['target']['priority_provenance'].get('why', '') for r in self.rows()))
        self.answer = self.target(**{'gloria': copy.deepcopy(F.GLORIA)})
        t = self.select(resolve=False)
        self.assertEqual(t['priority_mode'], 'pressure')
        st = json.loads(Path(PV.STATE).read_text())
        self.assertEqual(st['override_counts']['gloria'], 1)                    # the one real override, counted once
        rec = {'override': {'axis': 'gloria', 'pressure': 2.0, 'counted': True, 'id': 'r1'}}
        self.assertEqual(PV.refund_override(rec), 'gloria'); self.assertIsNone(PV.refund_override(rec))
        self.assertEqual(json.loads(Path(PV.STATE).read_text())['override_counts']['gloria'], 0)

    # follow-up coverage (12 November): how a turn fails, how often it is given back, restarts, device turns
    def pressed(self):
        Path(PV.STATE).write_text(json.dumps({'neglect': {'field': 0.0, 'gloria': 1.6, 'self': 0.0}}))

    def state(self):
        return json.loads(Path(PV.STATE).read_text())

    def failing_transport(self, exc):
        def down(req, timeout=None):
            if json.loads(req.data).get('max_tokens') == 6: return self.respond(req, timeout)
            raise exc
        return patch('urllib.request.urlopen', down)

    def test_timeout_and_network_failures_give_the_override_back(self):
        import socket, urllib.error
        for exc in (socket.timeout('synthetic timeout'), TimeoutError('synthetic'), urllib.error.URLError('synthetic down')):
            with self.subTest(exc=type(exc).__name__):
                self.pressed()
                with self.failing_transport(exc), self.assertRaises(type(exc)): self.select(resolve=False)
                st = self.state()
                self.assertGreaterEqual(st['neglect']['gloria'], 1.5)
                self.assertEqual(st['override_counts']['gloria'], 0)
                self.assertEqual(len(st['override_refunds']), 1); Path(PV.STATE).unlink()
        self.assertEqual(self.rows(), [])            # a transport failure is no selector reply: no failure row

    def test_exactly_one_refund_per_failed_turn(self):
        self.pressed(); calls = []
        real = PV.refund_override
        def counted(rec): out = real(rec); calls.append(out); return out
        self.answer = 'no object at all'
        with patch.object(PV, 'refund_override', counted):
            for _ in range(3):
                with self.assertRaises(E.SelectorUnreadable): self.select(resolve=False)
            self.answer = self.target(**{'gloria': copy.deepcopy(F.GLORIA)})
            self.select(resolve=False)                                          # a turn that succeeds: none
        self.assertEqual(calls, ['gloria'] * 3)
        self.assertEqual(len(set(self.state()['override_refunds'])), 3)

    def test_a_restart_and_retry_never_give_back_twice(self):
        self.pressed()
        self.answer = 'no object at all'
        with self.assertRaises(E.SelectorUnreadable): self.select(resolve=False)
        rec = self.rows()[0]['target']['priority_provenance']                  # the record as it was declared
        self.assertNotIn('refunded', rec['override'])
        before = self.state()
        # a restart forgets everything in memory; the same record offered again gives nothing back
        self.assertIsNone(PV.refund_override(copy.deepcopy(rec)))
        self.assertEqual(self.state(), before)
        # the turn retried after the crash is a new turn with its own record; its failure is given back once,
        # and the first record still only once
        with self.assertRaises(E.SelectorUnreadable): self.select(resolve=False)
        after = self.state()
        self.assertEqual(len(after['override_refunds']), 2); self.assertIn(rec['override']['id'], after['override_refunds'])
        self.assertEqual(after['override_counts']['gloria'], 0)
        self.assertIsNone(PV.refund_override(copy.deepcopy(rec)))
        self.assertEqual(self.state(), after)

    def test_device_and_background_turns_give_nothing_back(self):
        self.pressed()
        self.answer = 'no object at all'
        with self.assertRaises(E.SelectorUnreadable): self.select(F.BUTTON, resolve=False, her_source='gcs')
        st = self.state()
        self.assertLess(st['neglect']['gloria'], 1.5)                           # spent, as before, and kept spent
        self.assertNotIn('override_refunds', st)
        self.assertNotIn('override', self.rows()[0]['target']['priority_provenance'])
        self.pressed()
        with PV.background():
            rec = PV.declare()
            self.assertIsNone(PV.refund_override(dict(rec, override={'axis': 'gloria', 'pressure': 2.0, 'id': 'bg'})))
        self.assertNotIn('override', rec)
        with self.assertRaises(E.SelectorUnreadable): self.select(resolve=False, persist=False)   # a preview
        self.assertNotIn('override_refunds', self.state())
        self.assertIsNone(PV.refund_override({'override': {'axis': 'gloria', 'pressure': 2.0}}))  # no id: none

    def test_no_override_means_nothing_to_give_back(self):
        self.assertIsNone(PV.refund_override({'weights': {}, 'mode': 'strategic'}))
        with PV.background():
            self.assertIsNone(PV.refund_override({'override': {'axis': 'gloria', 'pressure': 2.0}}))
        self.assertFalse(Path(PV.STATE).exists())


# ---- 3. the want lane's pace ------------------------------------------------------------------------------
class WantLanePace(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix='want-pace-'); self.addCleanup(d.cleanup)
        self.ws = Path(d.name).resolve(); (self.ws / 'memory').mkdir()

    def test_allowance_grows_through_the_day_and_never_passes_the_cap(self):
        got = [B.paced_allowance(16, at(h)) for h in range(24)]
        self.assertEqual(got[0], 3); self.assertEqual(got[-1], 16)
        self.assertEqual(got, sorted(got)); self.assertTrue(all(g <= 16 for g in got))
        self.assertEqual(B.paced_allowance(0, at(23)), 0)
        self.assertEqual(B.paced_allowance(1000, at(0)), -(-1000 // 24) + B.PACE_BURST)

    def test_first_hour_is_paced_and_unused_hours_carry_over(self):
        for i in range(3): B.reserve(self.ws, 'one', 'a%d' % i, 'fixture', at(0, 2 + i))
        with self.assertRaisesRegex(B.WorkBlocked, 'hourly_call_pace'): B.reserve(self.ws, 'two', 'b', 'fixture', at(0, 30))
        B.reserve(self.ws, 'two', 'b', 'fixture', at(1, 0))                    # the next hour adds its share
        self.assertEqual(B.paced_allowance(16, at(15)), 13)
        for i in range(9): B.reserve(self.ws, 'x%d' % i, 'c%d' % i, 'fixture', at(15, 1 + i))    # carried over
        with self.assertRaisesRegex(B.WorkBlocked, 'hourly_call_pace'): B.reserve(self.ws, 'y', 'd', 'fixture', at(15, 30))
        self.assertEqual(B.remaining(self.ws, 'one', at(15, 31))['today_left'], 3)

    def test_daily_cap_is_unchanged_and_still_the_last_word(self):
        for i in range(16): B.reserve(self.ws, 'w%d' % i, 'a%d' % i, 'fixture', at(23, 1 + i))
        with self.assertRaisesRegex(B.WorkBlocked, 'daily_call_cap'): B.reserve(self.ws, 'z', 'b', 'fixture', at(23, 40))
        (self.ws / 'memory/want-work-policy.json').write_text(json.dumps({'daily_calls': 4}))
        B.reserve(self.ws, 'next', 'n0', 'fixture', at(23, 1, day=13) - 23 * 3600)

    def test_a_day_of_passes_spreads_the_calls(self):
        # a pass every ten minutes, two working calls a pass, wants always waiting (the live shape on the 12th)
        made = []
        t = at(0, 2)
        while t < at(23, 59):
            for _ in range(2):
                try: B.reserve(self.ws, 'w%d' % len(made), 'c%d' % len(made), 'fixture', t); made.append(t)
                except B.WorkBlocked as e:
                    self.assertIn(e.reason, ('hourly_call_pace', 'daily_call_cap')); break
            t += 600
        hours = [datetime.fromtimestamp(x, CHI).hour for x in made]
        self.assertEqual(len(made), 16)
        self.assertLessEqual(sum(h == 0 for h in hours), 3)
        self.assertLessEqual(sum(h < 12 for h in hours), 10)                     # not much more than half by noon
        self.assertGreaterEqual(max(hours), 19)                                  # the budget lasts into the evening

    def test_pace_holds_no_want_and_tells_no_one(self):
        self.assertIn('hourly_call_pace', WA.DAY_WIDE); self.assertIn('hourly_call_pace', WA.NO_CALL_MADE)
        sent = []
        W.notify_block({'id': 'w', 'agent_work': {'request_id': 'WA-x'}}, {'id': 'RW-x'}, self.ws, 'hourly_call_pace',
                       lambda k, m: sent.append(k))
        self.assertEqual(sent, [])
        dot = (REPO / 'scripts' / 'dot_channel.py').read_text()
        self.assertIn("if exc.reason == 'hourly_call_pace' else", dot)


if __name__ == '__main__':
    unittest.main()

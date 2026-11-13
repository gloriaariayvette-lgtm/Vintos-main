"""Device-only turns in the intent engine (13 November). Two faults, both from a device input being treated like
one of her turns somewhere it should not be:
 1. the priority vector read only the foreground flag, so a device-only foreground turn spent a due pressure
    override and accrued neglect, though the engine had declared it not eligible;
 2. a device input sitting in a move's response slot kept her next words out of it, and the background
    resolver's rerun kept only the latest input, so her first reply after a device event could be lost.
Scratch stores, synthetic text and fixture judges only: no model is asked, no socket opened."""
import copy
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

import test_intent_fields_fix as F
from test_intent_fields_fix import E, PV, GLORIA, HER, BUTTON

ROOM = "GLORIA: Earlier topic.\nREELROOM EVENT (not Gloria's words): the film ended"
H0 = 'GLORIA: Earlier topic.\nVINTOS: Earlier answer.\nGLORIA (now): a first synthetic line.'
H1 = 'GLORIA: Earlier topic.\nVINTOS: Earlier answer.\nGLORIA (now): the synthetic reply after the device.'
H2 = 'GLORIA: Earlier topic.\nVINTOS: Earlier answer.\nGLORIA (now): a later synthetic line.'
SOL_YES = {'verdict': 'YES', 'reason': 'plain_yes', 'codes': ['plain_yes'], 'adherence': 'delivered',
           'confidence': 'high', 'status': 'ok'}
DUE = {'neglect': {'field': 0.2, 'gloria': 1.6, 'self': 0.0}, 'arc': {'field': 0.3, 'gloria': 0.2, 'self': 0.5},
       'override_counts': {'field': 0, 'gloria': 1, 'self': 0}, 'override_streak': {'axis': 'gloria', 'n': 1},
       'gloria_opportunity': {'since': 2, 'opportunities': 1, 'attempts': 1, 'declared': 1, 'abstained': 0},
       'override_refunds': ['synthetic-id']}


class Base(unittest.TestCase):
    setUp = F.IntentFieldsFix.setUp
    respond = F.IntentFieldsFix.respond
    rows = F.IntentFieldsFix.rows
    target = F.IntentFieldsFix.target
    select = F.IntentFieldsFix.select
    turn = F.IntentFieldsFix.turn
    delivered = F.IntentFieldsFix.delivered

    def moves(self):
        return [r for r in self.rows() if r.get('status') == 'delivered']

    def effect_keys(self):
        return [c.args[3]['effect_key'] for c in sys.modules['outcome_join'].record.call_args_list]


class DeviceTurnPressure(Base):
    def due(self, counted=1):
        st = copy.deepcopy(DUE); st['override_counts']['gloria'] = st['override_streak']['n'] = counted
        Path(PV.STATE).write_text(json.dumps(st))           # compact on purpose: any rewrite changes the bytes
        return Path(PV.STATE).read_bytes()

    def untouched_in_memory(self, rec):
        """What the declare itself computed, not only what it wrote: no neglect accrued before the override was read,
        the arc not moved, nothing counted toward the causality question (two counted already: a third would ask)."""
        self.assertIn("(pressure 1.6)", rec['why'])
        self.assertEqual(rec['arc'], DUE['arc'])
        self.assertEqual(sys.modules['causality_engine'].queue_question.call_count, 0)

    def last_rec(self):
        return json.loads(Path(PV.LOG).read_text().strip().splitlines()[-1])

    def test_device_only_foreground_turn_leaves_a_due_override_and_all_state_untouched(self):
        for text, source in ((BUTTON, 'gcs'), (BUTTON, None), (ROOM, None)):
            before = self.due(counted=2)
            t = self.select(text, resolve=False, **({'her_source': source} if source else {}))
            self.assertEqual(Path(PV.STATE).read_bytes(), before, (text, source))   # counters, neglect, pressure, cadence
            rec = self.last_rec()
            self.untouched_in_memory(rec)
            self.assertTrue(rec['foreground'])                                # it was a foreground turn
            self.assertNotIn('override', rec)                                 # nothing spent, so nothing to give back
            self.assertFalse(rec['gloria_opportunity'])
            self.assertFalse(t['priority_provenance']['gloria_opportunity'])
            self.assertIsNone(PV.refund_override(rec))
            self.assertEqual(Path(PV.STATE).read_bytes(), before)
        self.assertEqual(sys.modules['causality_engine'].queue_question.call_count, 0)

    def test_declare_not_eligible_in_the_foreground_moves_nothing(self):
        before = self.due(counted=2)
        rec = PV.declare(eligible=False)
        self.assertEqual(rec['mode'], 'pressure')                             # the due override is shown, not spent
        self.assertEqual(Path(PV.STATE).read_bytes(), before)
        self.assertNotIn('override', rec)
        self.untouched_in_memory(rec)

    def test_her_eligible_turn_still_spends_the_override(self):
        self.due()
        t = self.select(HER, resolve=False)
        st = json.loads(Path(PV.STATE).read_text())
        self.assertEqual(st['neglect']['gloria'], 0.0)                       # debited
        self.assertEqual(st['override_counts']['gloria'], 2)
        self.assertNotEqual(st['arc'], DUE['arc'])
        rec = self.last_rec()
        self.assertEqual((rec['mode'], rec['override']['axis']), ('pressure', 'gloria'))
        self.assertGreaterEqual(rec['override']['pressure'], 1.5)
        self.assertEqual(t['priority_provenance']['mode'], 'pressure')

    def test_device_turn_then_her_turn_spends_the_override_once_on_hers(self):
        self.due()
        self.select(BUTTON, resolve=False, her_source='gcs')
        self.assertEqual(json.loads(Path(PV.STATE).read_text())['neglect']['gloria'], 1.6)
        self.select(HER, resolve=False)
        st = json.loads(Path(PV.STATE).read_text())
        self.assertEqual((st['neglect']['gloria'], st['override_counts']['gloria']), (0.0, 2))


class DeviceEvidenceResolver(Base):
    def blocking(self, release, packets):
        def judge(packet):
            packets.append(packet)
            if not release.wait(10): raise AssertionError('fixture release timed out')
            return copy.deepcopy(SOL_YES)
        return patch.object(E, '_rubric_judge', judge)

    def wait_for(self, cond, timeout=10):
        end = time.monotonic() + timeout
        while not cond():
            if time.monotonic() > end: self.fail('condition not reached')
            time.sleep(0.01)

    def test_her_reply_behind_a_device_input_is_bound_and_judged_with_a_blocked_worker(self):
        self.answer = self.target(gloria=copy.deepcopy(GLORIA)); self.verdict = 'YES'
        self.delivered(gloria=copy.deepcopy(GLORIA))                          # R0
        release = threading.Event(); packets = []
        self.addCleanup(E.resolver_wait, 15); self.addCleanup(release.set)
        with self.blocking(release, packets), patch.object(E, 'RESOLVE_IN_BACKGROUND', True):
            self.turn(H0, her_source='chat')                                  # the worker goes out on R0 and stays
            self.wait_for(lambda: len(packets) == 1)
            # the device input takes R1's slot; its own move is never delivered, so her next words answer R1
            self.select(BUTTON, her_source='gcs')
            self.assertEqual(self.moves()[1]['response_source'], 'gcs')
            self.turn(H1, her_source='chat')                                  # her words take it from the device
            r1 = self.moves()[1]
            self.assertEqual((r1['response_text'], r1['response_source']), (H1, 'chat'))   # on the row, before any resolver
            self.turn(H2, her_source='chat')                                  # a later turn does not move her first reply
            self.assertEqual(self.moves()[1]['response_text'], H1)
            self.assertEqual(len(packets), 1)                                 # the worker is still out
            release.set()
            self.assertTrue(E.resolver_wait(15))
        rows = self.moves()
        self.assertEqual([r['realized']['gloria'] for r in rows], ['YES', 'YES', 'YES', None])
        self.assertEqual(rows[1]['gloria_judge']['reason'], 'plain_yes')
        heard = [p['her_next_reply'] for p in packets]
        self.assertEqual(heard.count(E._her_live_words(H1)), 1)               # R1, on her first reply
        self.assertEqual(heard.count(E._her_live_words(H2)), 1)
        self.assertEqual(len(heard), 3)
        self.assertFalse(any('button' in h for h in heard))
        self.assertFalse(any('resolution_dropped' in r for r in self.rows()))
        keys = self.effect_keys()
        for r in rows[:3]:
            self.assertEqual(sum(k.startswith(r['intent_id'] + ':outcome') for k in keys), 1)

    def test_her_reply_behind_a_device_input_survives_a_restart(self):
        import signal
        self.answer = self.target(gloria=copy.deepcopy(GLORIA)); self.verdict = 'YES'
        self.delivered(gloria=copy.deepcopy(GLORIA))
        pid = os.fork()
        if pid == 0:                                                          # the process that goes down
            try:
                signal.alarm(60); done = threading.Event()
                def dying(packet):
                    done.wait(10); os._exit(7)
                with patch.object(E, '_rubric_judge', dying), patch.object(E, 'RESOLVE_IN_BACKGROUND', True):
                    self.turn(H0, her_source='chat'); self.select(BUTTON, her_source='gcs'); self.turn(H1, her_source='chat')
                    done.set(); time.sleep(20)
                os._exit(9)
            finally:
                os._exit(10)
        self.assertEqual(os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1]), 7)
        rows = self.moves()
        self.assertEqual(len(rows), 3)
        self.assertEqual((rows[1]['response_text'], rows[1]['response_source']), (H1, 'chat'))   # durable across it
        self.assertIsNone(rows[1]['realized']['gloria'])
        packets = []
        def judge(packet):
            packets.append(packet); return copy.deepcopy(SOL_YES)
        with patch.object(E, '_rubric_judge', judge), patch.object(E, 'RESOLVE_IN_BACKGROUND', True):
            E._kick_resolver(''); self.assertTrue(E.resolver_wait(15))         # the process that comes back, no input
            E._kick_resolver(''); self.assertTrue(E.resolver_wait(15))         # and again: nothing twice
        rows = self.moves()
        self.assertEqual([r['realized']['gloria'] for r in rows], ['YES', 'YES', None])
        self.assertEqual(sum(p['her_next_reply'] == E._her_live_words(H1) for p in packets), 1)
        self.assertEqual(sum(p['her_next_reply'] == E._her_live_words(H0) for p in packets), 1)
        self.assertNotIn('skipped_observations', rows[1])
        keys = self.effect_keys()
        for r in rows[:2]:
            self.assertEqual(sum(k.startswith(r['intent_id'] + ':outcome') for k in keys), 1)

    def test_a_resolver_that_read_the_device_revision_is_dropped_and_her_reply_judged_once(self):
        self.verdict = 'YES'
        self.delivered(gloria=copy.deepcopy(GLORIA))
        entered, gate = threading.Event(), threading.Event()
        self.addCleanup(E.resolver_wait, 15); self.addCleanup(gate.set)
        def observe(reply):
            entered.set(); gate.wait(10)
        packets = []
        def judge(packet):
            packets.append(packet); return copy.deepcopy(SOL_YES)
        with patch.object(sys.modules['self_difference'], 'observe_self', observe), \
             patch.object(E, '_rubric_judge', judge), patch.object(E, 'RESOLVE_IN_BACKGROUND', True):
            E.note_response(BUTTON, source='gcs'); E._kick_resolver(BUTTON, 'gcs')
            self.assertTrue(entered.wait(10))                                 # the worker holds the device revision
            rev = self.rows()[0]['resolution_rev']
            E.note_response(H1, source='chat'); E._kick_resolver(H1, 'chat')
            row = self.rows()[0]
            self.assertEqual((row['response_text'], row['resolution_rev']), (H1, rev + 1))
            gate.set()
            self.assertTrue(E.resolver_wait(15))
        row = self.rows()[0]
        self.assertEqual((row['resolution_dropped']['n'], row['resolution_dropped']['reason']), (1, 'stale_revision'))
        self.assertNotIn('skipped_observations', row)                         # the device result never landed
        self.assertEqual(row['realized']['gloria'], 'YES')
        self.assertEqual([p['her_next_reply'] for p in packets], [E._her_live_words(H1)])
        self.assertEqual(sum(k.startswith(row['intent_id'] + ':outcome') for k in self.effect_keys()), 1)

    def test_her_first_reply_is_never_replaced_and_a_device_never_replaces_a_device(self):
        self.delivered(gloria=copy.deepcopy(GLORIA))
        E.note_response(H1, source='chat'); E.note_response(H2, source='chat'); E.note_response(BUTTON, source='gcs')
        row = self.rows()[0]
        self.assertEqual((row['response_text'], row['response_source'], row['resolution_rev']), (H1, 'chat', 1))
        self.delivered(gloria=copy.deepcopy(GLORIA))
        E.note_response(BUTTON, source='gcs'); E.note_response(ROOM)
        row = self.rows()[1]
        self.assertEqual((row['response_text'], row['response_source'], row['resolution_rev']), (BUTTON, 'gcs', 1))
        E.note_response(H2)                                                   # her words with no source: the text is read
        row = self.rows()[1]
        self.assertEqual((row['response_text'], row['resolution_rev']), (H2, 2))
        self.assertNotIn('response_source', row)                              # the device's source does not stay beside them
        self.assertEqual(self.rows()[0]['response_text'], H1)


if __name__ == '__main__':
    unittest.main()

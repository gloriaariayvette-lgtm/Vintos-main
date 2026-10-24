#!/usr/bin/env python3
"""An invalid selection is refused before it runs, and the tick goes on.

Two selections used to raise ValueError: the investigation planner returning no route, and the frontier session
choosing an experiment it was not offered. Each is now an explicit refusal. Scratch stores only; every sender blocked.
"""
import contextlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_lab_tool_routing as sandbox   # scratch HOME, writes outside it refused, every network/subprocess a stub
import lab_investigations as I
import lab_lines

C = sandbox.C

# The session's outward doors: the Mac and compute admission are stubs, never the real modules.
mac = types.SimpleNamespace(status=lambda: {'ok': True, 'experiments': ['fold']},
                            run=Mock(side_effect=AssertionError('nothing may run after a refusal')),
                            reading=Mock(side_effect=AssertionError('nothing to read')))
sys.modules['chemistry_mac'] = mac
@contextlib.contextmanager
def admitted(*args, **kwargs): yield object()
sys.modules['compute_admission'] = types.SimpleNamespace(admit=admitted)
sys.modules['line_prospect'] = types.SimpleNamespace(prospect=lambda: None)
import chemistry_session as S


class InvestigationRefusal(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.ROOT).is_relative_to(sandbox.SCRATCH))
        self.assertTrue(Path(I._path('investigations.json')).is_relative_to(sandbox.SCRATCH))
        self.assertTrue(Path(C.NOTEBOOK).is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        C._atomic(I._path('investigations.json'), {'investigations': [{'id': 'I-norute', 'opened_at': C.now_iso(),
            'state': 'open', 'line_id': 'L-1', 'question': 'Q', 'prediction': 'p', 'steps': [], 'planning_failures': 1}]})
        self.lines = patch.multiple(lab_lines, pick=Mock(return_value=None), opened_by=Mock(return_value=None),
                                    record_step=Mock())
        self.lines.start()

    def tearDown(self):
        self.lines.stop()
        sandbox.SEND.assert_not_called()

    def test_no_route_is_refused_deferred_and_counted(self):
        ask = Mock(return_value=json.dumps({'question': 'Q', 'route': ''}))
        execute = Mock()
        row = I.turn('', ask=ask, execute=execute)   # used to raise ValueError and fault the tick
        self.assertEqual(row['kind'], 'investigation_refused')
        self.assertIn('no route', row['why'])
        execute.assert_not_called()
        inv = C._load(I._path('investigations.json'), {})['investigations'][0]
        self.assertEqual(inv['state'], 'open', 'a refusal answers nothing')
        self.assertEqual(inv['planning_failures'], 2, 'the persistent budget is kept, not reset')
        self.assertGreater(inv['deferred_until'], __import__('time').time())
        lab_lines.record_step.assert_not_called()
        self.assertEqual(I.next_phase({}, row, {}), 'orient')
        notes = [json.loads(x) for x in Path(C.NOTEBOOK).read_text().splitlines() if x.strip()]
        self.assertEqual(notes[-1]['kind'], 'investigation_refused')
        # Selection skips it while it is set aside; nothing new is opened over it.
        ask.reset_mock()
        self.assertIsNone(I.turn('', ask=ask, execute=execute))
        ask.assert_not_called()
        self.assertEqual(len(C._load(I._path('investigations.json'), {})['investigations']), 1)
        # When the deferral is over, a third refusal spends the budget and closes it as stalled, never answered.
        data = C._load(I._path('investigations.json'), {}); data['investigations'][0]['deferred_until'] = 0
        C._atomic(I._path('investigations.json'), data)
        I.turn('', ask=ask, execute=execute)
        inv = C._load(I._path('investigations.json'), {})['investigations'][0]
        self.assertEqual(inv['state'], 'stalled'); self.assertEqual(inv['planning_failures'], I.MAX_PLANNING_FAILURES)


class FrontierRefusal(unittest.TestCase):
    def setUp(self):
        for path in (S.SESSIONS, S.SESSION_STATE, S.SESSION_LOCK, C.NOTEBOOK):
            self.assertTrue(Path(path).is_relative_to(sandbox.SCRATCH), path)
        self.assertIs(sys.modules['chemistry_mac'], mac)
        C.set_enabled(True)
        C._atomic(S.SESSION_STATE, {'lens_index': 0})

    def tearDown(self):
        sandbox.SEND.assert_not_called()

    def test_unoffered_experiment_is_refused_and_the_session_ends_once(self):
        async def frontier(lens, system, user, paid_reservation=None):
            return json.dumps({'experiment': 'teleport', 'parameters': {}, 'question': 'q', 'prediction': 'p'})
        before = len(C._tail_jsonl(S.SESSIONS)) if Path(S.SESSIONS).exists() else 0
        with patch.object(S, '_frontier', frontier), \
             patch.object(S.owed, 'settle_one', return_value={'outcome': 'NOTHING_OWED'}), \
             patch.object(S.probe, 'refresh', return_value=[]), \
             patch.object(S.probe, 'record_host_report', return_value=None), \
             patch.object(S, 'frontier_context', return_value=('ctx', {'context_sha256': 'x'})), \
             patch.object(S.bridge, 'add_to_context', return_value=('ctx', {'context_sha256': 'x'}, [])), \
             patch.object(S.lab, 'tools_status', return_value={}):
            row = S.run()   # used to be filed as held_fault from a ValueError
        self.assertEqual(row['state'], 'refused_before_execution', row)
        self.assertIn('teleport', row['refused'])
        mac.run.assert_not_called()
        rows = C._tail_jsonl(S.SESSIONS)
        self.assertEqual(len(rows) - before, 1, 'one session row, written by the ordinary finalization')
        self.assertEqual(rows[-1]['state'], 'refused_before_execution')
        self.assertEqual(json.loads(Path(S.SESSION_STATE).read_text())['lens_index'], 1, 'exactly one lens advance')


if __name__ == '__main__': unittest.main(verbosity=2)

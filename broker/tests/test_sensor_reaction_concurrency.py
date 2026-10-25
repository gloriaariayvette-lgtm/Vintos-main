#!/usr/bin/env python3
"""Concurrent sensor writers and prompt readers share only a scratch state."""
import concurrent.futures
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
TEMP = tempfile.TemporaryDirectory(prefix='sensor-concurrency-')
SCRATCH = Path(TEMP.name)
os.environ['HOME'] = str(SCRATCH)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
import sensor_reactions as S

SEND = Mock(side_effect=AssertionError('no external action'))


class Concurrency(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(S.STATE).is_relative_to(SCRATCH))
        self.guard = patch.object(socket.socket, 'connect', SEND)
        self.guard.start()
        self.feel = patch.object(S, '_feel', SEND)
        self.feel.start()
        Path(S.STATE).parent.mkdir(parents=True, exist_ok=True)
        Path(S.STATE).write_text('{}')

    def tearDown(self):
        self.feel.stop()
        self.guard.stop()
        SEND.assert_not_called()

    def test_simultaneous_sensor_observations_do_not_replace_each_other(self):
        first_at_save, second_saved = threading.Event(), threading.Event()
        save = S._save_state

        def interleaved_save(state):
            if 'presence' in state and 'heart_rate' not in state:
                first_at_save.set()
                second_saved.wait(.2)
            save(state)
            if 'heart_rate' in state:
                second_saved.set()

        with patch.object(S, '_save_state', interleaved_save), concurrent.futures.ThreadPoolExecutor(2) as workers:
            first = workers.submit(S.observe, 'presence', True, at=1000, now=1000)
            self.assertTrue(first_at_save.wait(2))
            second = workers.submit(S.observe, 'heart_rate', 70, at=1000, now=1000)
            first.result(timeout=3)
            second.result(timeout=3)
        state = json.loads(Path(S.STATE).read_text())
        self.assertEqual(set(state), {'presence', 'heart_rate'})
        self.assertEqual(state['presence']['last'], True)
        self.assertEqual(state['heart_rate']['last'], 70)

    def test_two_prompts_cannot_consume_the_same_reaction(self):
        reaction = {'id':'SR-fixture', 'channel':'context', 'change':'fixture change',
                    'consumed':False, 'expires_at':2000}
        Path(S.STATE).write_text(json.dumps({'pending':[reaction]}))
        first_read, second_read = threading.Event(), threading.Event()
        pending = S.pending

        def interleaved_pending(now=None):
            rows = pending(now)
            if threading.current_thread().name.endswith('_0'):
                first_read.set()
                second_read.wait(.2)
            else:
                second_read.set()
            return rows

        with patch.object(S, 'pending', interleaved_pending), concurrent.futures.ThreadPoolExecutor(2) as workers:
            first = workers.submit(S.context_line, 1000)
            self.assertTrue(first_read.wait(2))
            second = workers.submit(S.context_line, 1000)
            results = [first.result(timeout=3), second.result(timeout=3)]
        self.assertEqual(sum(bool(r) for r in results), 1)
        self.assertEqual(S.pending(1000), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)

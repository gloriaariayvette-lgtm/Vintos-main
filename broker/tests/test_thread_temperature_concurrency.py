#!/usr/bin/env python3
"""Embedding latency must not let temperature replace a newer shared thread pool."""
import copy
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
SCRATCH = tempfile.TemporaryDirectory(prefix='thread-temperature-race-')
os.environ['HOME'] = SCRATCH.name
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
import thread_store as S
import thread_temperature as T


class ConcurrentTemperature(unittest.TestCase):
    def setUp(self):
        self.path = Path(T.THREADS)
        self.assertTrue(self.path.is_relative_to(SCRATCH.name))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rows = [{'id':str(i), 'thread':'Fixture question '+str(i), 'consumed':False}
                     for i in range(10)]
        self.path.write_text(json.dumps(self.rows))
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('no network'))
        self.network.start()

    def tearDown(self):
        self.network.stop()

    def run_temperature(self, concurrent=None):
        def embed(texts):
            if concurrent:
                current = S.load_pool(str(self.path))
                concurrent(current)
                self.assertTrue(S.save_pool(current, str(self.path), reason='fixture concurrent writer'))
            return [[1.0, 0.0] for _ in texts]
        with patch.object(T, '_load_index', return_value=([[1.0, 0.0]], None, 'vector', 'text')), \
             patch.object(T, '_embed', side_effect=embed), \
             patch.object(T, '_stability', return_value=0.2):
            T.run(apply=True, quiet=True)
        return json.loads(self.path.read_text())

    def test_concurrent_admission_survives_embedding_delay(self):
        rows = self.run_temperature(lambda current: current.append(
            {'id':'new', 'thread':'A newly admitted fixture', 'consumed':False}))
        self.assertEqual(len(rows), 11)
        self.assertEqual(rows[-1]['id'], 'new')
        self.assertNotIn('temp_updated_at', rows[0])

    def test_concurrent_update_survives_even_when_count_does_not_change(self):
        rows = self.run_temperature(lambda current: current[0].update(priority=5))
        self.assertEqual(rows[0]['priority'], 5)
        self.assertNotIn('temp_updated_at', rows[0])

    def test_concurrent_retirement_is_not_resurrected(self):
        rows = self.run_temperature(lambda current: current.pop())
        self.assertEqual(len(rows), 9)
        self.assertNotIn('9', {r['id'] for r in rows})

    def test_unchanged_snapshot_accepts_temperature_update(self):
        rows = self.run_temperature()
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0]['temperature'], 0.8)
        self.assertEqual(rows[0]['stability'], 0.2)
        self.assertIn('temp_updated_at', rows[0])

    def test_stale_explicit_snapshot_cannot_commit_to_store(self):
        expected = copy.deepcopy(self.rows)
        updated = copy.deepcopy(self.rows)
        updated[0]['priority'] = 3
        self.path.write_text(json.dumps(self.rows+[{'id':'new'}]))
        self.assertFalse(S.save_pool(updated, str(self.path), expected=expected))
        self.assertEqual(len(json.loads(self.path.read_text())), 11)


if __name__ == '__main__':
    unittest.main(verbosity=2)

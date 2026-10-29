#!/usr/bin/env python3
"""Synthetic clean-room collector tests; cached fixture vectors, no encoder calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
from bundle import package_code
from data import SOURCES, boundary, sha


class Capture(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=os.environ['PERSISTENCE_SCRATCH']))
        self.code = self.root/'code'
        package_code(self.code, Path(__file__).resolve().parents[2])
        self.source = self.root/'input'; self.source.mkdir()
        self.cache = self.root/'cache.jsonl'
        self.cache.write_text('')
        self.at = boundary('2026-10-01')+10*3600+300

    def write(self, name, rows):
        path = self.source/name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows) if name.endswith('.jsonl') else json.dumps(rows))

    def capture(self):
        before = {str(p): sha(p) for p in self.source.rglob('*') if p.is_file()}
        env = dict(os.environ, PERSISTENCE_SCRATCH=str(self.root), PYTHONDONTWRITEBYTECODE='1',
                   OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', PYTHONPATH='')
        exp = self.code/'experiments/persistence-sprint'
        p = subprocess.run([sys.executable, str(exp/'launch.py'), str(exp/'collect.py'),
                            '--memory', str(self.source), '--out', str(self.root/'capture'),
                            '--cache', str(self.cache), '--encoder', str(self.root/'NO-ENCODER')],
                           cwd=self.root, env=env, capture_output=True, text=True, timeout=90)
        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
        self.assertEqual(before, {str(p): sha(p) for p in self.source.rglob('*') if p.is_file()})
        with np.load(self.root/'capture/events.npz', allow_pickle=False) as d:
            data = {k: d[k] for k in d.files}
        return data, json.loads((self.root/'capture/capture.json').read_text())

    def test_absent_optional_sources_and_no_network_embedding(self):
        self.write('emotion-trajectory-dense.json', [{'t': self.at, 'v': [0.5]*11}])
        d, r = self.capture()
        self.assertEqual(len(d['t']), 1)
        self.assertEqual(r['new_embeddings'], 0)
        for name in ('watch-presence-history.jsonl', 'chemistry-lab/notebook.jsonl', 'sensor-reactions.jsonl'):
            self.assertEqual(r['excluded']['absent:'+name], 1)
        self.assertEqual(d['source'][0, SOURCES.index('emotion')], 1)

    def test_atomic_batch_dense_adapters_and_boundary(self):
        self.write('emotion-trajectory-dense.json', [{'t': self.at, 'v': [0.5]*11},
                   {'t': boundary('2026-10-23'), 'v': [999.]*11}])
        rows = [('watch-presence-history.jsonl', {'kind': 'heart_rate', 'observed_at': self.at-600,
                'age_seconds': 420, 'value': 70, 'estimate': True}),
                ('sensor-reactions.jsonl', {'sensor': 'heart_rate', 'at': self.at-10000,
                 'now': self.at-100, 'value': 75}),
                ('want-events.jsonl', {'event': 'fixture', 'at': self.at-60}),
                ('avatar-presence-log.json', {'kind': 'fixture', 'at': self.at-60}),
                ('chemistry-lab/notebook.jsonl', {'kind': 'fixture', 'at': self.at-60})]
        for name, row in rows:self.write(name, [row])
        texts = ['Fixture question about the synthetic garden today.',
                 'Fixture answer about the synthetic garden today.']
        self.write('chat-canonical.jsonl', [dict(role=role, content=text, timestamp=self.at)
                   for role, text in zip(['user','assistant'], texts)])
        self.cache.write_text(''.join(json.dumps({'k': text, 'v': np.eye(768)[k].tolist()})+'\n'
                                     for k,text in enumerate(texts)))
        d, r = self.capture()
        self.assertEqual(len(d['t']), 1)
        self.assertEqual(d['t'][0], self.at)
        for name in ('emotion','her','him','watch','sensor','want','presence','lab'):
            self.assertEqual(d['source'][0,SOURCES.index(name)], 1, name)
        self.assertEqual(len(d['text_i']), 2)
        np.testing.assert_array_equal(d['text_i'], [0,0])
        self.assertFalse(d['text_exact'].any())
        self.assertEqual(r['emotion_readings'], 1)
        self.assertEqual(r['new_embeddings'], 0)


if __name__ == '__main__':unittest.main()

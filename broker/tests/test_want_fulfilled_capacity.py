"""SK-d0b42347: archived sources free capacity without claiming agent delivery."""
import copy
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import want_agent as A
import want_working_thread as W
import room_work as R

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fulfilled-capacity-')
        self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name).resolve()
        self.mem = self.ws / 'memory'; self.mem.mkdir()
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, SPARK_WORKSPACE=str(self.ws)))
        self.stack.enter_context(patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')))
        self.assertNotIn('.vintos', self.ws.parts)
        self.now = 2000000000.0
        self.write('current-wants.json', [])
        self.write('fulfilled-wants.json', [])

    def write(self, name, data):
        path = self.mem / name; path.write_text(json.dumps(data)); return path

    def work(self, i):
        return dict(id='RW-fixture'+str(i), want_id='fixture'+str(i),
                    want_request_id='WA-'+format(i, '024x'), goal='fixture work',
                    opened=1, touched=1, paused_until=self.now+3600,
                    pause_why='held: blocked_response_needs_review',
                    asks=[{'thread':'fixture-thread'}], returns=[{'evidence':'retained'}])

    def archived(self, work, **agent):
        return dict(id=work['want_id'], fulfilled=True,
                    agent_work=dict(request_id=work['want_request_id'], status='in_work', **agent))

    def test_six_stale_rows_free_capacity_and_queued_want_is_handed_over(self):
        rows = [self.work(i) for i in range(R.MAX_HELD)]
        state = {'room_work': {'open':copy.deepcopy(rows)}}
        path = self.write('fulfilled-wants.json', [self.archived(r) for r in rows])
        archive_bytes = path.read_bytes()
        want = dict(id='queued', want='run the fixture and export its result', timestamp='2026-11-19T00:00:00',
                    agent_work=dict(request_id='WA-'+'f'*24, status='queued', agent='dot',
                                    goal_sha256=A.fingerprint('run the fixture and export its result')))
        self.write('current-wants.json', [want])
        context = self.mem / 'retained-fixture-context'; context.write_text('original context')
        posts = Mock(return_value={'ok':True, 'ts':'fixture-ts'})
        self.assertIsInstance(posts, Mock)
        with patch.object(A, 'specific', return_value=True), patch.object(A, 'age_out', return_value=0), \
             patch.object(W, 'load', return_value={}), patch.object(W, 'retained_thread', return_value=None), \
             patch.object(W, 'append'), patch.object(R, 'posted'):
            lines = A.intake(state, posts, lambda s:None, self.now, ws=self.ws)
        posts.assert_called_once()
        self.assertTrue(any('handed to its agent' in line for line in lines))
        self.assertEqual(len(state['room_work']['open']), 1)
        retained = state['room_work']['detached_source_work']
        self.assertEqual(len(retained), R.MAX_HELD)
        for original, detached in zip(rows, retained):
            self.assertEqual({k:detached[k] for k in original}, original)
            self.assertEqual(detached['source_state'], 'archived')
            self.assertNotIn('delivery', detached)
        self.assertEqual(state['room_work'].get('history', []), [])
        self.assertEqual(path.read_bytes(), archive_bytes)
        self.assertEqual(context.read_text(), 'original context')
        A.reconcile_source_work(state, self.now+1, ws=self.ws)
        self.assertEqual(len(state['room_work']['detached_source_work']), R.MAX_HELD)

    def test_unknown_mismatched_and_live_source_bindings_stay(self):
        row = self.work(1)
        for archive, current in [([], []), ([self.archived(self.work(2))], []),
                                 ([self.archived(row)], [{'id':row['want_id']}]),
                                 ([dict(self.archived(row), fulfilled=False)], [])]:
            with self.subTest(archive=archive, current=current):
                state = {'room_work': {'open':[copy.deepcopy(row)]}}
                self.write('fulfilled-wants.json', archive); self.write('current-wants.json', current)
                A.reconcile_source_work(state, self.now, ws=self.ws)
                self.assertEqual(state['room_work']['open'], [row])

    def test_corrupt_fulfilled_archive_retains_every_binding(self):
        row = self.work(1)
        for raw in ('{broken', '{}'):
            state = {'room_work': {'open':[copy.deepcopy(row)]}}
            (self.mem/'fulfilled-wants.json').write_text(raw)
            self.write('dismissed-wants.json', [self.archived(row)])
            lines = A.reconcile_source_work(state, self.now, ws=self.ws)
            self.assertEqual(state['room_work']['open'], [row])
            self.assertTrue(any('malformed' in line for line in lines))

    def test_confirmed_deliveries_stay_for_existing_completion_cleanup(self):
        row = self.work(1)
        for delivery in ('sent', 'acknowledged'):
            state = {'room_work': {'open':[copy.deepcopy(row)]}}
            self.write('fulfilled-wants.json', [self.archived(row, result={'summary':'fixture'}, delivery={'state':delivery})])
            A.reconcile_source_work(state, self.now, ws=self.ws)
            self.assertEqual(state['room_work']['open'], [row])

if __name__ == '__main__':
    unittest.main()

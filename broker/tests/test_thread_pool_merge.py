#!/usr/bin/env python3
"""A slow pool writer (resolution, triage) merges onto the pool as it is when it saves.

It never overwrites a thread another writer added, or a field another writer changed,
while it was waiting on a model call.
"""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
SCRATCH = tempfile.TemporaryDirectory(prefix='thread-pool-merge-')
os.environ['HOME'] = SCRATCH.name
os.environ.pop('SPARK_WORKSPACE', None)
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'scripts'))
import thread_store as S

POOL = Path(SCRATCH.name)/'.vintos/workspace/memory/unfinished-threads.json'


def rows(n=10):
    return [{'id': 'T%d' % i, 'thread': 'Fixture question %d' % i, 'consumed': False, 'pull': 1}
            for i in range(n)]


class MergeOnSave(unittest.TestCase):
    def setUp(self):
        self.assertTrue(POOL.is_relative_to(SCRATCH.name))
        POOL.parent.mkdir(parents=True, exist_ok=True)
        POOL.write_text(json.dumps(rows()))
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('no network'))
        self.network.start()

    def tearDown(self):
        self.network.stop()

    def concurrent(self, change):
        current = S.load_pool(str(POOL))
        change(current)
        self.assertTrue(S.save_pool(current, str(POOL), reason='fixture concurrent writer'))

    def test_concurrent_addition_survives(self):
        base = S.load_pool(str(POOL)); mine = json.loads(json.dumps(base))
        mine[0]['pull'] = 4
        self.concurrent(lambda c: c.append({'id': 'NEW', 'thread': 'Arrived meanwhile'}))
        self.assertTrue(S.save_pool(mine, str(POOL), reason='slow writer', base=base))
        after = {t['id']: t for t in S.load_pool(str(POOL))}
        self.assertIn('NEW', after)
        self.assertEqual(after['T0']['pull'], 4)

    def test_other_field_change_survives_and_mine_applies(self):
        base = S.load_pool(str(POOL)); mine = json.loads(json.dumps(base))
        mine[1]['triage_voice'] = 'mine'
        def other(c):
            c[1]['temperature'] = 0.7
        self.concurrent(other)
        S.save_pool(mine, str(POOL), reason='slow writer', base=base)
        t1 = {t['id']: t for t in S.load_pool(str(POOL))}['T1']
        self.assertEqual((t1['triage_voice'], t1['temperature']), ('mine', 0.7))

    def test_my_removal_applies_and_their_removal_stays(self):
        base = S.load_pool(str(POOL)); mine = [t for t in json.loads(json.dumps(base)) if t['id'] != 'T2']
        self.concurrent(lambda c: c.__delitem__(3))   # another writer retired T3
        S.save_pool(mine, str(POOL), reason='slow writer', base=base)
        ids = {t['id'] for t in S.load_pool(str(POOL))}
        self.assertNotIn('T2', ids); self.assertNotIn('T3', ids); self.assertIn('T4', ids)

    def test_unchanged_pool_writes_as_before(self):
        base = S.load_pool(str(POOL)); mine = json.loads(json.dumps(base)); mine[5]['pull'] = 3
        self.assertTrue(S.save_pool(mine, str(POOL), reason='slow writer', base=base))
        self.assertEqual(S.load_pool(str(POOL)), mine)

    def test_shrink_guard_still_applies_after_merge(self):
        big = rows(40); POOL.write_text(json.dumps(big))
        base = S.load_pool(str(POOL)); mine = json.loads(json.dumps(base))[:5]
        self.concurrent(lambda c: c.append({'id': 'NEW', 'thread': 'x'}))
        self.assertFalse(S.save_pool(mine, str(POOL), reason='slow writer', base=base))
        self.assertEqual(len(S.load_pool(str(POOL))), 41)

    def test_resolution_keeps_a_thread_added_during_its_model_call(self):
        pool = rows()
        pool[0].update(consumed=True, consumed_by='dream', priority=1)
        POOL.write_text(json.dumps(pool))
        spec = importlib.util.spec_from_file_location('thread_resolution_under_test', REPO/'scripts/thread_resolution.py')
        R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
        self.assertTrue(Path(R.THREADS_FILE).is_relative_to(SCRATCH.name))
        real_save_retired = R.save_retired
        def archive_then_concurrent(retired):
            # runs between the resolver's load and its pool save, as a slow model call would
            real_save_retired(retired)
            self.concurrent(lambda c: c.append({'id': 'DURING', 'thread': 'Written while he was resolving'}))
        with patch.object(R, 'llm', return_value='what it taught him'),              patch.object(R, 'save_retired', side_effect=archive_then_concurrent):
            R.resolve_threads()
        ids = {t['id'] for t in S.load_pool(str(POOL))}
        self.assertNotIn('T0', ids)            # the consumed thread was sedimented out of the pool
        self.assertIn('T1', ids)
        self.assertIn('DURING', ids)           # before: the resolver's stale snapshot erased it

    def test_triage_and_resolution_pass_their_snapshot(self):
        for name in ('bin/thread-triage.py', 'bin/thread-resolution.py'):
            src = (REPO/name).read_text()
            self.assertNotRegex(src, r'save_pool\((?![^)]*base=)', name)


if __name__ == '__main__':
    unittest.main()

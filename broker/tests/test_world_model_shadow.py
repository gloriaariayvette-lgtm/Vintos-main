#!/usr/bin/env python3
"""MAMEPA in shadow (scripts/world_model_shadow.py): every run rebuilds the recent grid from the stores, read-only,
advances the state model and writes its expectations to world-model-shadow.json plus one bounded history row, and
NOTHING reads either file. Synthetic stores and synthetic weights only; sockets are refused; scratch HOME."""
import glob, hashlib, json, os, socket, sys, tempfile, unittest
from datetime import datetime, timedelta
from pathlib import Path
scratch = tempfile.TemporaryDirectory(prefix='mamepa-')
WS = scratch.name + '/workspace'
DOOR = scratch.name + '/door'
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=WS, VINTOS_SECRETS=scratch.name + '/x', MAMEPA_DOOR_DIR=DOOR)
os.environ.pop('MAMEPA_WEIGHTS', None); os.environ.pop('FACE_THRESHOLD', None)
NET = []
def refused(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError('this suite reaches nothing')
socket.socket.connect = refused
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
import numpy as np
import world_model_shadow as S

MEM = os.path.join(WS, 'memory')
NOW = datetime(2030, 1, 15, 12, 2, 30, tzinfo=S.TZ).timestamp()          # a made-up moment
def at(hours_ago):
    return NOW - hours_ago * 3600
def iso(t):
    return datetime.fromtimestamp(t, S.TZ).isoformat()
def dump(obj, path):
    with open(path, 'w') as f: json.dump(obj, f)


def write_stores():
    os.makedirs(MEM, exist_ok=True); os.makedirs(DOOR, exist_ok=True)
    with open(os.path.join(MEM, 'watch-presence-history.jsonl'), 'w') as f:
        for h in range(30, 0, -1):
            f.write(json.dumps({'observed_ts': at(h), 'kind': 'heart_rate', 'value': 60 + h % 7}) + '\n')
        f.write(json.dumps({'observed_ts': at(2), 'kind': 'motion', 'value': 'walking'}) + '\n')
        f.write(json.dumps({'observed_ts': at(3), 'kind': 'battery', 'value': {'state': 'charging'}}) + '\n')
    with open(os.path.join(MEM, 'sensor-reactions.jsonl'), 'w') as f:
        for h, v in ((100, True), (20, False), (18, True)):
            f.write(json.dumps({'sensor': 'presence', 'value': v, 'at': at(h)}) + '\n')
    dump([{'timestamp': iso(at(h)), 'gloria': 'hi'} for h in (5, 4.5, 1)], os.path.join(MEM, 'interaction-ledger.json'))
    with open(os.path.join(MEM, 'chat-canonical.jsonl'), 'w') as f:
        f.write(json.dumps({'ts': iso(at(6)), 'role': 'user'}) + '\n')
    dump([{'timestamp': iso(at(7)), 'event': 'open'}], os.path.join(MEM, 'avatar-presence-log.json'))
    with open(os.path.join(MEM, 'bedroom-arrivals.jsonl'), 'w') as f:
        f.write(json.dumps({'at': iso(at(9))}) + '\n')
    with open(os.path.join(MEM, 'bedroom-visits.jsonl'), 'w') as f:
        f.write(json.dumps({'from_ts': at(40), 'to_ts': at(39.5)}) + '\n')
        f.write(json.dumps({'from_ts': at(10), 'to_ts': at(9)}) + '\n')
    with open(os.path.join(MEM, 'house-board-visits.jsonl'), 'w') as f:
        f.write(json.dumps({'board': 'house-steam', 'from_ts': at(30), 'to_ts': at(29.8), 'shower': False}) + '\n')
        f.write(json.dumps({'board': 'house-steam', 'from_ts': at(8), 'to_ts': at(7.8), 'shower': True}) + '\n')
        f.write(json.dumps({'board': 'house-press-mic', 'from_ts': at(3), 'to_ts': at(2), 'seated_minutes': 50}) + '\n')
        f.write(json.dumps({'board': 'house-touch', 'from_ts': at(26), 'to_ts': at(25)}) + '\n')
    # no kitchen-visits.jsonl at all: that stream must stay missing, never zero
    for name, who, conf, h in (('a', 'eve', 0.9, 12), ('b', 'eve', 0.2, 11), ('c', 'neighbor', 0.95, 10), ('d', None, 0.0, 30)):
        dump({'event': {'ts': datetime.fromtimestamp(at(h), S.TZ).replace(tzinfo=None).isoformat(),
                        'identity': {'name': who, 'confidence': conf, 'faces': 1 if who else 0}}},
             os.path.join(DOOR, name + '.json.local.json'))


def write_weights(path, channels=None):
    torch, World = S._model_classes()
    torch.manual_seed(0)
    din = 3 * len(S.CH) + 4
    model = World(din)
    mu = [70.0, 50.0, 15.0, 60.0] + [0.0] * (len(S.CH) - 4)
    sd = [10.0, 20.0, 2.0, 5.0] + [1.0] * (len(S.CH) - 4)
    torch.save({'state_dict': model.state_dict(), 'core': 'mamba', 'jepa': True, 'd': 64, 'layers': 2, 'din': din,
                'channels': list(channels or S.CH), 'horizons': dict(S.H), 'bin_seconds': S.BIN, 'norm_mu': mu,
                'norm_sd': sd, 'inputs_off': ['door_her'], 'note': 'synthetic', 'cutoff': at(48)}, path)


def tree_hashes(*roots):
    out = {}
    for r in roots:
        for p in glob.glob(os.path.join(r, '**', '*'), recursive=True):
            if os.path.isfile(p): out[p] = hashlib.sha256(Path(p).read_bytes()).hexdigest()
    return out


class Shadow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        write_stores()
        cls.weights = os.path.join(scratch.name, 'private', 'weights.pt')
        os.makedirs(os.path.dirname(cls.weights), exist_ok=True)
        write_weights(cls.weights)

    def setUp(self):
        for n in (S.OUT_NAME, S.HIST_NAME, S.HIST_NAME + S.LOCK_SUFFIX):
            p = os.path.join(MEM, n)
            if os.path.exists(p): os.unlink(p)

    def test_it_writes_expectations_uncertainty_and_freshness(self):
        doc = S.run(self.weights, now=NOW, mem=MEM, door_dir=DOOR)
        on_disk = json.loads(Path(MEM, S.OUT_NAME).read_text())
        self.assertEqual(on_disk, json.loads(json.dumps(doc)))
        self.assertTrue(on_disk['shadow'])
        self.assertEqual(set(on_disk['expect']), {'30m', '2h', '6h'})
        for name, e in on_disk['expect'].items():
            self.assertEqual(set(e['channels']), set(S.CH))
            hr = e['channels']['heart_rate']
            self.assertGreater(hr['sd'], 0); self.assertLess(hr['p10'], hr['mean']); self.assertGreater(hr['p90'], hr['mean'])
            self.assertTrue(0 <= e['channels']['home']['p'] <= 1)
            self.assertAlmostEqual(sum(e['channels']['motion']['probs'].values()), 1.0, places=2)
            self.assertGreaterEqual(e['channels']['her_messages']['rate_per_bin'], 0)
        ends = [datetime.fromisoformat(on_disk['expect'][n]['at']) for n in ('30m', '2h', '6h')]
        grid_end = datetime.fromisoformat(on_disk['grid_end'])
        self.assertEqual([round((e - grid_end).total_seconds() / 60) for e in ends], [30, 120, 360])
        self.assertEqual(set(on_disk['inputs']), set(S.CH))
        hr = on_disk['inputs']['heart_rate']
        self.assertAlmostEqual(hr['age_minutes'], 60.0, delta=0.1)
        self.assertIsNotNone(hr['source_mtime'])
        self.assertFalse(on_disk['inputs']['door_her']['used_as_input'])
        self.assertTrue(on_disk['inputs']['heart_rate']['used_as_input'])

    def test_missing_means_missing(self):
        X, when, t0 = S.grid(S.build(MEM, DOOR), NOW)
        col = lambda c: X[:, S.CH.index(c)]
        self.assertTrue(np.isnan(col('in_kitchen')).all(), 'a stream with no store is missing, not zero')
        doc = S.run(self.weights, now=NOW, mem=MEM, door_dir=DOOR)
        self.assertIsNone(doc['inputs']['in_kitchen']['last_record'])
        self.assertIsNone(doc['inputs']['in_kitchen']['source_mtime'])
        i_first = int((at(40) - t0) // S.BIN)
        bed = col('in_bedroom')
        self.assertTrue(np.isnan(bed[:i_first]).all(), 'before its first visit the bedroom stream is missing')
        self.assertFalse(np.isnan(bed[i_first:]).any())
        self.assertEqual(bed[int((at(9.5) - t0) // S.BIN)], 1.0)
        self.assertEqual(bed[int((at(20) - t0) // S.BIN)], 0.0)
        sofa = col('on_sofa')
        self.assertTrue(np.isnan(sofa[:int((at(3) - t0) // S.BIN)]).all())
        hr = col('heart_rate')
        self.assertTrue(np.isnan(hr).sum() > len(hr) - 40, 'heart rate is only where a reading is')
        self.assertEqual(np.nansum(col('showers')), 1.0)
        self.assertTrue(np.isnan(col('showers')[:int((at(30) - t0) // S.BIN)]).all())

    def test_doorbell_counts_only_her_matches_at_the_matcher_threshold(self):
        X, when, t0 = S.grid(S.build(MEM, DOOR), NOW)
        door = X[:, S.CH.index('door_her')]
        self.assertEqual(np.nansum(door), 1.0, 'eve at 0.9 counts; eve at 0.2 and a neighbour do not')
        self.assertEqual(door[int((at(12) - t0) // S.BIN)], 1.0)
        self.assertTrue(np.isnan(door[:int((at(30) - t0) // S.BIN)]).all(), 'missing before the first encounter')
        self.assertEqual(S.DOOR_THRESH, 0.36)
        self.assertEqual(S.DOOR_NAMES, ('gloria', 'eve'))

    def test_the_stores_are_only_read(self):
        before = tree_hashes(MEM, DOOR)
        S.run(self.weights, now=NOW, mem=MEM, door_dir=DOOR)
        after = tree_hashes(MEM, DOOR)
        new = sorted(set(after) - set(before))
        self.assertEqual([os.path.basename(p) for p in new], sorted([S.HIST_NAME, S.HIST_NAME + S.LOCK_SUFFIX, S.OUT_NAME]))
        for p, h in before.items():
            if os.path.basename(p) not in (S.HIST_NAME, S.HIST_NAME + S.LOCK_SUFFIX, S.OUT_NAME):
                self.assertEqual(after.get(p), h, p)
        self.assertEqual(glob.glob(os.path.join(MEM, '.world-model-shadow*')), [], 'no temp file left behind')

    def test_history_is_appended_and_bounded(self):
        for i in range(5):
            S.run(self.weights, now=NOW + i * 600, mem=MEM, door_dir=DOOR, history_rows=3)
        rows = [json.loads(l) for l in Path(MEM, S.HIST_NAME).read_text().splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]['written_at'], datetime.fromtimestamp(NOW + 4 * 600, S.TZ).isoformat(timespec='seconds'))
        self.assertEqual(set(rows[0]['expect']), {'30m', '2h', '6h'})
        self.assertEqual(len(rows[0]['expect']['2h']['heart_rate']), 2)        # mean and sd, to score later
        self.assertIn('fresh_minutes', rows[0])

    def test_a_writer_waiting_through_a_rotation_keeps_its_row(self):
        """13 November review: the lock was on the history file the rotation replaces, so a writer already waiting
        on it appended to the detached copy and its row was lost. Writer B arrives while A holds the lock and is
        about to rotate (cap 1); both rows must reach the history in turn, and B's is the one kept."""
        import fcntl, threading
        from unittest import mock
        hist = os.path.join(scratch.name, 'rotation', S.HIST_NAME)
        os.makedirs(os.path.dirname(hist), exist_ok=True)
        Path(hist).write_text('{"sequence":0}\n')
        b_waiting, a_rotating, errors = threading.Event(), threading.Event(), []
        real_flock, real_replace = fcntl.flock, os.replace

        def flock(fd, op):
            if threading.current_thread().name == 'writer-B': b_waiting.set()
            return real_flock(fd, op)

        def replace(src, dst):
            if threading.current_thread().name == 'writer-A' and dst == hist:
                a_rotating.set()
                if not b_waiting.wait(5): raise AssertionError('fixture: writer B never arrived')
                threading.Event().wait(0.2)                  # B is now blocked on the lock, not past it
            return real_replace(src, dst)

        def writer(seq):
            try:
                if seq == 2 and not a_rotating.wait(5): raise AssertionError('fixture: A never rotated')
                S._append_bounded(hist, {'sequence': seq}, 1)
            except BaseException as e:
                errors.append(e)
        with mock.patch.object(S.fcntl, 'flock', flock), mock.patch.object(S.os, 'replace', replace):
            a = threading.Thread(target=writer, args=(1,), name='writer-A')
            b = threading.Thread(target=writer, args=(2,), name='writer-B')
            b.start(); a.start(); a.join(10); b.join(10)
        self.assertFalse(a.is_alive() or b.is_alive(), 'a writer hung')
        self.assertEqual(errors, [])
        self.assertEqual([json.loads(l)['sequence'] for l in Path(hist).read_text().splitlines()], [2])
        self.assertTrue(os.path.exists(hist + S.LOCK_SUFFIX), 'the lock file is stable, never replaced')
        self.assertEqual(glob.glob(os.path.join(os.path.dirname(hist), '.world-model-shadow*')), [])

    def test_two_writers_through_many_rotations_lose_nothing(self):
        """Two processes append through repeated rotations: every row written is kept while the cap allows."""
        import subprocess
        hist = os.path.join(scratch.name, 'rotation-many', S.HIST_NAME)
        os.makedirs(os.path.dirname(hist), exist_ok=True)
        if os.path.exists(hist): os.unlink(hist)
        code = ('import sys; sys.path.insert(0, sys.argv[1]); import world_model_shadow as S\n'
                'for i in range(40): S._append_bounded(sys.argv[2], {"w": sys.argv[3], "i": i, "pad": "p" * 1000}, 30)')
        procs = [subprocess.Popen([sys.executable, '-c', code, os.path.dirname(os.path.abspath(S.__file__)), hist, w])
                 for w in ('A', 'B')]
        self.assertEqual([p.wait(120) for p in procs], [0, 0])
        rows = [json.loads(l) for l in Path(hist).read_text().splitlines()]
        self.assertEqual(len(rows), 30)
        # the history keeps the newest 30 of 80 rows, so each writer's kept rows run without a gap to its last row
        for w in ('A', 'B'):
            kept = [r['i'] for r in rows if r['w'] == w]
            self.assertEqual(kept, list(range(40 - len(kept), 40)), (w, kept))

    def test_weights_for_other_channels_are_refused(self):
        other = os.path.join(scratch.name, 'private', 'other.pt')
        write_weights(other, channels=S.CH[:-1] + ['something_else'])
        with self.assertRaises(SystemExit):
            S.run(other, now=NOW, mem=MEM, door_dir=DOOR)
        self.assertFalse(os.path.exists(os.path.join(MEM, S.OUT_NAME)))

    def test_without_weights_it_writes_nothing(self):
        self.assertEqual(S.main([]), 2)
        self.assertEqual(S.main(['--weights', os.path.join(scratch.name, 'nowhere.pt')]), 2)
        self.assertFalse(os.path.exists(os.path.join(MEM, S.OUT_NAME)))
        self.assertFalse(os.path.exists(os.path.join(MEM, S.HIST_NAME)))

    def test_nothing_else_reads_the_shadow_files(self):
        allowed = {'scripts/world_model_shadow.py', 'broker/tests/test_world_model_shadow.py'}
        readers = []
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'node_modules') and not d.startswith('.venv')]
            rel_root = os.path.relpath(root, REPO)
            if rel_root == 'docs' or rel_root.startswith('docs' + os.sep):
                continue                                   # generated reports name every store; they read nothing
            for f in files:
                p = os.path.join(root, f); rel = os.path.relpath(p, REPO).replace(os.sep, '/')
                if rel in allowed or os.path.getsize(p) > 4_000_000: continue
                try: text = Path(p).read_text(encoding='utf-8')
                except (UnicodeDecodeError, OSError): continue
                if 'world-model-shadow' in text or 'world_model_shadow' in text:
                    if rel == 'scripts/deploy-atelier.sh' and 'world-model-shadow' not in text:
                        continue                           # the manifest installs the script; it reads no output
                    readers.append(rel)
        self.assertEqual(readers, [], 'the shadow is read by nothing')

    def test_one_spelling_only(self):
        for twin in ('scripts/world-model-shadow.py', 'bin/world_model_shadow.py', 'bin/world-model-shadow.py'):
            self.assertFalse((REPO / twin).exists(), twin)

    def test_nothing_reached_the_network(self):
        S.run(self.weights, now=NOW, mem=MEM, door_dir=DOOR)
        self.assertEqual(NET, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)

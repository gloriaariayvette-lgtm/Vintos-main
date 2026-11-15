#!/usr/bin/env python3
"""Tag-keyed HDC recall behind the AprilTag lookup (scripts/hdc_tag_recall.py), opt-in: a seen tag's exact map entry
still comes first and unchanged; the tag's most salient recalled sightings follow, from a partial or damaged cue.
Synthetic tags, people, actions and rooms only; sockets are refused; scratch HOME and workspace."""
import ast, glob, json, os, socket, stat, sys, tempfile, unittest
from datetime import datetime
from pathlib import Path
scratch = tempfile.TemporaryDirectory(prefix='hdc-tag-')
WS = scratch.name + '/workspace'
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=WS, VINTOS_SECRETS=scratch.name + '/x')
os.environ.pop('HDC_TAG_RETAIN_DAYS', None)
for _v in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS'):
    os.environ[_v] = '1'
NET = []
def refused(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError('this suite reaches nothing')
socket.socket.connect = refused
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(REPO / 'studio'))
import numpy as np
import hdc_tag_recall as T
import native_video as NV
from hdc_episodic import TZ

MEM = os.path.join(WS, 'memory')
NOW = datetime(2030, 3, 15, 12, tzinfo=TZ).timestamp()
ROLES = T.ROLES


def world(seed, n_eps, tags=4):
    """Synthetic: each tag gets n_eps distinct episodes, each laid down c ~ Geometric(0.35) times (salience)."""
    r = np.random.default_rng(seed)
    out = {}
    for ti in range(tags):
        key = 'tag36h11:%d' % (200 + ti)
        eps, seen = [], set()
        while len(eps) < n_eps:
            ts = datetime(2030, 1, 1, int(r.integers(24)), tzinfo=TZ).timestamp() + int(r.integers(60)) * 86400
            ev = {'who': 'p%d' % r.integers(8), 'what': 'a%d' % r.integers(24), 'where': 'r%d' % r.integers(6), 'ts': ts}
            sig = (ev['who'], ev['what'], ev['where'], T.date_of(ts), T.day_part(ts))
            if sig in seen: continue
            seen.add(sig); eps.append((sig, ev, int(min(30, r.geometric(0.35)))))
        out[key] = eps
    return out


def build(w):
    m = T.TagRecall()
    for key, eps in w.items():
        for _sig, ev, c in eps:
            for _ in range(c): assert m.add(key, ev, 1, NOW)
    return m


def top3(m, key, eps, mask=None, known=None):
    pool = [(sig, c) for sig, _ev, c in eps if not known or sig[0] == known['who']]
    c3 = sorted((c for _, c in pool), reverse=True)[min(2, len(pool) - 1)]
    truth = dict(pool)
    got = m.top(key, 3, known, mask)
    return sum(truth.get(tuple(g[r] for r in ROLES), 0) >= c3 for g in got) / min(3, len(pool))


class Inner:
    def __init__(self, recs): self.recs = recs
    def lookup(self, key): return [dict(x) for x in self.recs.get(key, [])]


W50 = world(1, 50)
M50 = build(W50)


class Recall(unittest.TestCase):
    def test_tag_alone_returns_the_most_salient_episodes(self):
        scores = [top3(M50, k, eps) for k, eps in W50.items()]
        self.assertEqual(np.mean(scores), 1.0, scores)
        k = sorted(W50)[0]
        best = max(W50[k], key=lambda e: e[2])
        self.assertEqual(tuple(M50.top(k, 1)[0][r] for r in ROLES), best[0])
        self.assertAlmostEqual(M50.top(k, 1)[0]['salience'], best[2], delta=1.0)

    def test_a_damaged_vector_and_wrong_cue_bits_still_rank_them(self):
        r = np.random.default_rng(7)
        scores = []
        for k, eps in W50.items():
            for _ in range(3):
                mask = (r.random(T.D) >= .3).astype(np.float32); mask[r.random(T.D) < .15] *= -1
                scores.append(top3(M50, k, eps, mask))
        self.assertGreaterEqual(np.mean(scores), .9, scores)
        mask = (r.random(T.D) >= .9).astype(np.float32); mask[r.random(T.D) < .48] *= -1
        self.assertLess(np.mean([top3(M50, k, eps, mask) for k, eps in W50.items()]), .9, 'the damage bites')

    def test_a_partial_cue_narrows_to_that_person(self):
        for k, eps in W50.items():
            who = max(eps, key=lambda e: e[2])[0][0]
            got = M50.top(k, 3, {'who': who})
            self.assertTrue(got and all(g['who'] == who for g in got))
            self.assertEqual(top3(M50, k, eps, known={'who': who}), 1.0)
        self.assertEqual(M50.top(sorted(W50)[0], 3, {'who': 'nobody-synthetic'}), [], 'a wrong cue recalls nothing')

    def test_a_hundred_episodes_per_tag(self):
        w = world(2, 100, tags=2)
        m = build(w)
        self.assertEqual(np.mean([top3(m, k, eps) for k, eps in w.items()]), 1.0)

    def test_unknown_tags_and_bad_events(self):
        m = T.TagRecall()
        self.assertEqual(m.top('tag36h11:999'), [])
        self.assertFalse(m.add('tag36h11:1', {'who': 'p1', 'what': 'a1', 'ts': NOW}, 1, NOW), 'no where')
        self.assertFalse(m.add('tag36h11:1', {'who': 'p1', 'what': 'a1', 'where': 'r1', 'ts': float('nan')}, 1, NOW))
        self.assertFalse(m.add('', {'who': 'p1', 'what': 'a1', 'where': 'r1', 'ts': NOW}, 1, NOW))
        self.assertFalse(m.add('tag36h11:1', {'who': 'p1', 'what': 'a1', 'where': 'r1', 'ts': NOW - 400 * 86400}, 1, NOW),
                         'older than the window')
        self.assertTrue(m.add('tag36h11:1', {'who': 'p1', 'what': 'a1', 'where': 'r1', 'ts': NOW}, 99, NOW))
        self.assertEqual(m.stats()['laid_down'], T.MAX_WEIGHT, 'one sighting counts for at most MAX_WEIGHT')

    def test_forgetting_reads_the_count_out_of_the_vector(self):
        w = world(3, 30, tags=1)
        m = build(w)
        k = list(w)[0]
        sig, _ev, c = max(w[k], key=lambda e: e[2])
        self.assertEqual(m.forget(k, dict(zip(ROLES, sig))), c)
        self.assertNotIn(list(sig), m.tags[k]['episodes'])
        self.assertEqual(m.stats()['laid_down'], sum(cc for _s, _e, cc in w[k]) - c)
        small = T.TagRecall(max_episodes=10)
        for s2, ev, cc in w[k][:15]:
            for _ in range(cc): small.add(k, ev, 1, NOW)
        self.assertEqual(len(small.tags[k]['episodes']), 10, 'the weakest go when a tag is full')

    def test_old_episodes_leave_with_the_window(self):
        m = T.TagRecall(retain_days=30)
        m.add('tag36h11:5', {'who': 'p1', 'what': 'a1', 'where': 'r1', 'ts': NOW - 20 * 86400}, 3, NOW)
        m.add('tag36h11:5', {'who': 'p2', 'what': 'a2', 'where': 'r2', 'ts': NOW - 86400}, 1, NOW)
        self.assertEqual(m.prune(NOW + 15 * 86400), 1)
        self.assertEqual([e['who'] for e in m.top('tag36h11:5')], ['p2'])
        self.assertEqual(m.stats()['laid_down'], 1)


class ExactStillWins(unittest.TestCase):
    """The existing lookup is unchanged whenever an exact entry exists, and unchanged everywhere with the flag off."""

    def setUp(self):
        keys = sorted(W50)
        self.exact = {k: [{'text': 'synthetic linked record %s' % k, 'label': 'syn'}] for k in keys[::2]}
        self.tag_map = {k: {'text': v[0]['text'], 'label': 'syn'} for k, v in self.exact.items()}

    def test_the_store_puts_exact_records_first_and_marks_the_rest(self):
        store = T.HdcTagStore(Inner(self.exact), M50)
        for k in sorted(W50):
            got = store.lookup(k)
            plain = Inner(self.exact).lookup(k)
            self.assertEqual(got[:len(plain)], plain)
            rest = got[len(plain):]
            self.assertEqual(len(rest), 3)
            for r in rest:
                self.assertEqual(r['kind'], 'hdc-episode')
                self.assertIn('not a memory Gloria linked', r['text'])
                self.assertLessEqual(len(r['text']), T.RECORD_CHARS)

    def test_native_video_lookup_is_unchanged_without_the_flag_and_beside_it_with_it(self):
        for k in sorted(W50):
            fam, _, tid = k.partition(':')
            tag = {'family': fam, 'tag_id': tid, 'at': 1.5}
            off, on = NV.tag_memory(tag, self.tag_map), NV.tag_memory(tag, self.tag_map, hdc=M50)
            self.assertNotIn('episodes', off)
            self.assertEqual({x: on[x] for x in off}, off)
            self.assertEqual(on['found'], k in self.exact, 'recalled sightings never make a tag found')
            self.assertEqual(len(on['episodes']), 3)
            lines_off, lines_on = NV.tag_lines([tag], self.tag_map), NV.tag_lines([tag], self.tag_map, hdc=M50)
            self.assertEqual(lines_on[:len(lines_off)], lines_off)
            self.assertEqual(len(lines_on), len(lines_off) + 1)
            self.assertIn('not a memory Gloria linked', lines_on[-1])
            if k not in self.exact:
                self.assertIn('Do not guess', lines_on[0])
        rec = {'frames': 0, 'segments': []}
        tags = [{'family': 'tag36h11', 'tag_id': 200}]
        self.assertEqual(NV.senses_block(rec, (), tags, self.tag_map), NV.senses_block(rec, (), tags, self.tag_map, None))

    def test_a_private_copy_is_read_and_a_readable_one_refused(self):
        d = Path(scratch.name) / 'private'; d.mkdir(mode=0o700, exist_ok=True)
        p = d / 'tag-recall.json'
        p.write_text(json.dumps(M50.to_json())); os.chmod(p, 0o600)
        store = T.HdcTagStore(Inner(self.exact), str(p))
        k = sorted(W50)[1]
        self.assertEqual([r['who'] for r in store.lookup(k)], [e['who'] for e in M50.top(k)])
        os.chmod(p, 0o644)
        with self.assertRaises(PermissionError):
            store.lookup(k)
        missing = T.HdcTagStore(Inner(self.exact), str(d / 'none.json'))
        k0 = sorted(W50)[0]
        self.assertEqual(missing.lookup(k0), Inner(self.exact).lookup(k0), 'no copy: the exact answer alone')

    def test_the_mamepa_keeps_its_contract(self):
        import camera_mamepa as cm
        store = T.HdcTagStore(cm.DictTagStore({k: v for k, v in self.exact.items()}), M50)
        self.assertIsInstance(store.lookup('tag36h11:777'), list)
        k = sorted(self.exact)[0]
        self.assertEqual(store.lookup(k)[0], cm.DictTagStore(self.exact).lookup(k)[0])
        rest = store.lookup(k)[len(cm.DictTagStore(self.exact).lookup(k)):]
        self.assertTrue(rest and all(r['kind'] == cm.RECALLED_KIND for r in rest),
                        'the summary knows these as recalled, never as linked records')

    def test_off_by_default(self):
        import native_video_server as srv
        self.assertFalse(srv.RECALL_DEFAULT)
        src = (REPO / 'studio' / 'native_video_server.py').read_text()
        self.assertIn('if args.tag_hdc:', src)
        users = set()
        for root in ('scripts', 'bin', 'broker', 'studio', 'agent-room'):
            for p in glob.glob(str(REPO / root / '**' / '*.py'), recursive=True):
                if 'hdc_tag_recall' in Path(p).read_text(errors='ignore') or 'hdc-tag-recall' in Path(p).read_text(errors='ignore'):
                    users.add(os.path.relpath(p, REPO))
        self.assertLessEqual(users, {'scripts/hdc_tag_recall.py', 'broker/tests/test_hdc_tag_recall.py',
                                     'broker/tests/test_hdc_episodic.py', 'studio/native_video_server.py',
                                     'scripts/native_video.py'})   # native_video names it in a docstring only
        nv = ast.parse((REPO / 'scripts' / 'native_video.py').read_text())
        self.assertNotIn('hdc_tag_recall', [a.name for n in ast.walk(nv) if isinstance(n, (ast.Import, ast.ImportFrom))
                                            for a in n.names] + [n.module for n in ast.walk(nv) if isinstance(n, ast.ImportFrom)])


class StateFile(unittest.TestCase):
    def test_update_writes_only_its_state_and_lock_privately(self):
        mem = tempfile.mkdtemp(prefix='m-', dir=scratch.name)
        rows = [dict(ev, tag=k) for k, eps in list(W50.items())[:1] for _s, ev, c in eps[:10] for _ in range(c)]
        n, m = T.update(rows, mem, NOW)
        self.assertEqual(n, len(rows))
        self.assertEqual(sorted(os.listdir(mem)), sorted([T.STATE_NAME, T.STATE_NAME + T.LOCK_SUFFIX]))
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(mem, T.STATE_NAME)).st_mode), 0o600)
        again = T.load(mem)
        k = list(W50)[0]
        self.assertEqual(again.top(k), m.top(k))
        before = Path(mem, T.STATE_NAME).read_bytes()
        T.update([], mem, NOW)
        self.assertEqual(Path(mem, T.STATE_NAME).read_bytes(), before)
        self.assertEqual(sorted(again.to_json()['tags'][k]), ['episodes', 'segs'], 'labels and sums, no counts')
        self.assertEqual(NET, [])

    def test_imports(self):
        tree = ast.parse(Path(T.__file__).read_text())
        mods = {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertLessEqual(mods, {'argparse', 'base64', 'fcntl', 'json', 'os', 'stat', 'sys', 'tempfile', 'time',
                                    'numpy', 'hdc_episodic'})
        self.assertNotIn('MEM', [a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names])


if __name__ == '__main__':
    unittest.main(verbosity=2)

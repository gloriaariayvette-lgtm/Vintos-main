#!/usr/bin/env python3
"""The hyperdimensional episodic memory in shadow (scripts/hdc_episodic.py): house events become who/what/where/when
facts superposed in D=10,000 vectors, recalled from a partial cue. Synthetic stores and synthetic names only; sockets
are refused; scratch HOME. The suite also holds that the organ writes nothing but its own state file (and its lock)
and that nothing in his code reads it or feeds it to a prompt."""
import ast, glob, hashlib, json, os, random, socket, sys, tempfile, unittest
from datetime import datetime
from pathlib import Path
scratch = tempfile.TemporaryDirectory(prefix='hdc-')
WS = scratch.name + '/workspace'
DOOR = scratch.name + '/door'
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=WS, VINTOS_SECRETS=scratch.name + '/x', HDC_DOOR_DIR=DOOR)
for _v in ('HDC_SEGMENT_CAP', 'HDC_RETAIN_DAYS', 'FACE_THRESHOLD'):
    os.environ.pop(_v, None)
for _v in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS'):
    os.environ[_v] = '1'          # one math thread: the deploy runs suites in parallel
NET = []
def refused(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError('this suite reaches nothing')
socket.socket.connect = refused
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
import numpy as np
import hdc_episodic as H

MEM = os.path.join(WS, 'memory')
NOW = datetime(2030, 1, 15, 12, 2, 30, tzinfo=H.TZ).timestamp()          # a made-up moment (a Tuesday noon)
TODAY, YESTERDAY = '2030-01-15', '2030-01-14'
def at(day, hour, minute=0):
    return datetime(2030, 1, day, hour, minute, tzinfo=H.TZ).timestamp()
def dump(obj, path):
    with open(path, 'w') as f: json.dump(obj, f)
def tree_hashes(*roots):
    out = {}
    for r in roots:
        for p in glob.glob(os.path.join(r, '**', '*'), recursive=True):
            if os.path.isfile(p): out[p] = hashlib.sha256(Path(p).read_bytes()).hexdigest()
    return out
def report(*lines):
    sys.stderr.write('\n'.join(lines) + '\n'); sys.stderr.flush()


def write_stores():
    os.makedirs(MEM, exist_ok=True); os.makedirs(DOOR, exist_ok=True)
    with open(os.path.join(MEM, 'kitchen-visits.jsonl'), 'w') as f:
        for a, b in ((at(14, 18, 10), at(14, 18, 40)), (at(15, 7, 5), at(15, 7, 20))):
            f.write(json.dumps({'from_ts': a, 'to_ts': b, 'minutes': (b - a) / 60}) + '\n')
    with open(os.path.join(MEM, 'bedroom-visits.jsonl'), 'w') as f:
        f.write(json.dumps({'from_ts': at(14, 23, 0), 'to_ts': at(14, 23, 50)}) + '\n')
        f.write('not json\n')
    with open(os.path.join(MEM, 'bedroom-arrivals.jsonl'), 'w') as f:
        f.write(json.dumps({'at': datetime.fromtimestamp(at(14, 22, 58), H.TZ).isoformat()}) + '\n')
    with open(os.path.join(MEM, 'house-board-visits.jsonl'), 'w') as f:
        f.write(json.dumps({'board': 'house-steam', 'from_ts': at(15, 8, 0), 'to_ts': at(15, 8, 15), 'shower': True}) + '\n')
        f.write(json.dumps({'board': 'house-press-mic', 'from_ts': at(14, 19, 0), 'to_ts': at(14, 20, 0), 'seated_minutes': 50}) + '\n')
        f.write(json.dumps({'board': 'house-touch', 'from_ts': at(15, 9, 0), 'to_ts': at(15, 11, 0), 'seated_minutes': 0}) + '\n')
        f.write(json.dumps({'board': 'not-a-board', 'from_ts': at(15, 9, 0)}) + '\n')
    for name, who, conf, t in (('a', 'visitor_a', 0.9, at(14, 18, 30)), ('b', 'visitor_b', 0.2, at(14, 18, 35))):
        dump({'event': {'ts': datetime.fromtimestamp(t, H.TZ).replace(tzinfo=None).isoformat(),
                        'identity': {'name': who, 'confidence': conf, 'faces': 1}}},
             os.path.join(DOOR, name + '.json.local.json'))


def pairs(rows, *roles):
    return {tuple(r[k] for k in roles) for r in rows}


class HouseRecall(unittest.TestCase):
    """(1) partial-cue recall over the stores the presence organs already write."""

    @classmethod
    def setUpClass(cls):
        write_stores()
        p = os.path.join(MEM, H.STATE_NAME)
        if os.path.exists(p): os.unlink(p)
        cls.added, cls.m = H.update(H.read_stores(MEM, DOOR), mem=MEM, now=NOW)

    def test_what_happened_in_the_kitchen_yesterday_evening(self):
        date, part = H.resolve_when('yesterday evening', NOW)
        self.assertEqual((date, part), (YESTERDAY, 'evening'))
        got = H.load(MEM).ask(date, {'where': 'kitchen', 'part': part})
        self.assertEqual(pairs(got, 'who', 'what'), {('gloria', 'visit')})
        self.assertGreater(got[0]['score'], 0.8)
        door = H.load(MEM).ask(date, {'where': 'front_door', 'part': part})
        # the face below the matcher's threshold is "someone", never a guessed name
        self.assertEqual(pairs(door, 'who', 'what'), {('visitor_a', 'at_door'), ('someone', 'at_door')})
        self.assertEqual(H.load(MEM).ask(date, {'where': 'kitchen', 'part': 'morning'}), [])

    def test_where_was_she_this_morning(self):
        date, part = H.resolve_when('today morning', NOW)
        got = H.load(MEM).ask(date, {'who': 'gloria', 'part': part})
        self.assertEqual(pairs(got, 'what', 'where'), {('visit', 'kitchen'), ('shower', 'bathroom'), ('visit', 'office')})
        late = H.load(MEM).ask(YESTERDAY, {'who': 'gloria', 'part': 'late'})
        self.assertEqual(pairs(late, 'what', 'where'), {('visit', 'bedroom'), ('arrival', 'bedroom')})
        evening = H.load(MEM).ask(YESTERDAY, {'who': 'gloria', 'part': 'evening'})
        self.assertIn(('seated', 'living_room'), pairs(evening, 'what', 'where'))

    def test_when_was_she_in_the_bathroom(self):
        got = H.load(MEM).ask(TODAY, {'who': 'gloria', 'where': 'bathroom'})
        self.assertEqual(pairs(got, 'what', 'part'), {('shower', 'morning')})

    def test_a_visit_across_day_parts_is_in_each(self):
        self.assertEqual(H.slots(at(15, 11, 0), at(15, 12, 30)), [(TODAY, 'morning'), (TODAY, 'afternoon')])
        got = H.load(MEM).ask(TODAY, {'who': 'gloria', 'part': 'afternoon'})
        self.assertEqual(pairs(got, 'what', 'where'), set())       # the office visit ended at 11:00

    def test_sync_again_adds_nothing(self):
        self.assertGreater(self.added, 0)
        before = Path(MEM, H.STATE_NAME).read_bytes()
        n, _ = H.update(H.read_stores(MEM, DOOR), mem=MEM, now=NOW)
        self.assertEqual(n, 0)
        self.assertEqual(Path(MEM, H.STATE_NAME).read_bytes(), before, 'an idempotent sync leaves the file alone')

    def test_state_round_trips_and_old_days_fall_off(self):
        m = H.Episodic.from_json(json.loads(json.dumps(H.load(MEM).to_json())))
        self.assertEqual(m.stats(), H.load(MEM).stats())
        m.prune(NOW + 200 * 86400)
        self.assertEqual(m.stats()['facts'], 0)
        self.assertEqual(m.ingest({'who': 'x', 'what': 'y', 'where': 'z', 'ts': NOW - 400 * 86400}, NOW), 0)
        self.assertEqual(m.ingest({'who': 'x', 'what': '', 'where': 'z', 'ts': NOW}, NOW), 0)

    def test_replay_cli_reads_a_log_file(self):
        p = os.path.join(scratch.name, 'replay-kitchen.jsonl')
        with open(p, 'w') as f:
            f.write(json.dumps({'from_ts': at(12, 15, 0), 'to_ts': at(12, 15, 30)}) + '\n')
        H.main(['replay', p, '--source', 'kitchen'])
        got = H.load(MEM).ask('2030-01-12', {'where': 'kitchen', 'part': 'afternoon'})
        self.assertIn(('gloria', 'visit'), pairs(got, 'who', 'what'))


def synthetic_day(n, seed):
    """n facts on one date with mostly distinct (where, part) cues: 400 synthetic places x 5 parts, 20 people x 10
    acts. The asked role pair (who, what) has 200 candidates, chance 0.005."""
    r = random.Random(seed)
    keys, facts = set(), []
    while len(facts) < n:
        k = ('place%03d' % r.randrange(400), r.choice([p for p, _ in H.PARTS]))
        if k in keys: continue
        keys.add(k)
        facts.append({'who': 'person%02d' % r.randrange(20), 'what': 'act%d' % r.randrange(10), 'where': k[0], 'part': k[1]})
    return facts


def recall_rate(m, facts, q, seed, mask=None):
    r = random.Random(seed + 1)
    hit = 0
    for f in r.sample(facts, q):
        got = m.ask('2030-01-14', {'where': f['where'], 'part': f['part']}, mask=mask)
        hit += bool(got) and (got[0]['who'], got[0]['what']) == (f['who'], f['what'])
    return hit / q


def full_vocab(m):
    """Clean-up against the whole synthetic vocabulary, not only what this sample happened to store."""
    m.vocab['who'] = sorted(set(m.vocab['who']) | {'person%02d' % i for i in range(20)})
    m.vocab['what'] = sorted(set(m.vocab['what']) | {'act%d' % i for i in range(10)})


class Capacity(unittest.TestCase):
    """(2) graceful degradation as facts pile up past 400 in one vector, and the segment cap that keeps recall high;
    (3) damage tolerance."""
    Q = 60

    def test_recall_vs_facts_one_vector_and_segmented(self):
        lines = ['recall of (who, what) from (where, part), top-1, D=%d, %d queries, chance 0.005' % (H.D, self.Q),
                 '     N   one vector   segmented (cap %d)' % H.SEGMENT_CAP]
        single, seg = {}, {}
        for n in (100, 200, 400, 800, 1600):
            facts = synthetic_day(n, n)
            one, capped = H.Episodic(cap=10 ** 9), H.Episodic()
            for f in facts:
                one.add_fact('2030-01-14', f); capped.add_fact('2030-01-14', f)
            full_vocab(one); full_vocab(capped)
            self.assertEqual(len(one.days['2030-01-14']), 1)
            self.assertEqual(len(capped.days['2030-01-14']), -(-n // H.SEGMENT_CAP))
            single[n], seg[n] = recall_rate(one, facts, self.Q, n), recall_rate(capped, facts, self.Q, n)
            lines.append('  %4d   %.3f        %.3f' % (n, single[n], seg[n]))
        report(*lines)
        self.assertGreaterEqual(single[200], 0.98)
        self.assertLess(single[1600], single[200], 'one vector must degrade as facts pile up')
        self.assertLess(single[1600], 0.9)
        for n, v in seg.items():
            self.assertGreaterEqual(v, 0.98, 'segmented recall at N=%d' % n)

    def test_damage_tolerance(self):
        facts = synthetic_day(H.SEGMENT_CAP, 7)
        m = H.Episodic()
        for f in facts: m.add_fact('2030-01-14', f)
        full_vocab(m)
        rng = np.random.default_rng(3)
        dead = (rng.random(H.D) >= 0.3).astype(np.float32)                      # 30% of dimensions zeroed
        wrong = np.where(rng.random(H.D) < 0.15, -1.0, 1.0).astype(np.float32)   # and 15% of the cue's bits wrong
        clean, damaged, both = (recall_rate(m, facts, self.Q, 7, mask) for mask in (None, dead, dead * wrong))
        report('damage, %d facts in one segment: clean %.3f | 30%% zeroed %.3f | 30%% zeroed + 15%% wrong cue %.3f'
               % (H.SEGMENT_CAP, clean, damaged, both))
        self.assertGreaterEqual(clean, 0.98)
        self.assertGreaterEqual(damaged, 0.95)
        self.assertGreaterEqual(both, 0.85)


class Shadow(unittest.TestCase):
    """(4) the organ writes only its own state file, and nothing reads it or reaches a prompt."""

    def test_writes_only_its_own_state_file(self):
        write_stores()
        for p in (os.path.join(MEM, H.STATE_NAME), os.path.join(MEM, H.STATE_NAME + H.LOCK_SUFFIX)):
            if os.path.exists(p): os.unlink(p)
        before = tree_hashes(scratch.name)
        H.update(H.read_stores(MEM, DOOR), mem=MEM, now=NOW)
        H.main(['stats'])
        after = tree_hashes(scratch.name)
        new = sorted(os.path.relpath(x, MEM) for x in set(after) - set(before))
        self.assertEqual(new, sorted([H.STATE_NAME, H.STATE_NAME + H.LOCK_SUFFIX]))
        for x, h in before.items():
            self.assertEqual(after.get(x), h, x)
        self.assertEqual(glob.glob(os.path.join(MEM, '.hdc-episodic-shadow*')), [], 'no temp file left behind')
        self.assertEqual(NET, [])

    def test_the_organ_imports_nothing_of_his(self):
        tree = ast.parse(Path(H.__file__).read_text())
        mods = {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertLessEqual(mods, {'argparse', 'base64', 'fcntl', 'glob', 'hashlib', 'json', 'os', 'sys', 'tempfile',
                                    'time', 'datetime', 'itertools', 'zoneinfo', 'numpy'})

    def test_nothing_reads_the_state_file_or_the_organ(self):
        mine = {'scripts/hdc_episodic.py', 'broker/tests/test_hdc_episodic.py'}
        allowed = {'scripts/deploy-atelier.sh', 'docs/entry-owners.md', 'docs/untested.md'}   # the manifest and its reports
        hits = []
        for root in ('scripts', 'bin', 'broker', 'agent-room', 'docs'):
            for p in glob.glob(str(REPO / root / '**' / '*'), recursive=True):
                if not os.path.isfile(p) or p.endswith(('.pyc', '.png', '.jpg', '.pt', '.npz')): continue
                rel = os.path.relpath(p, REPO)
                if rel in mine: continue
                try: text = Path(p).read_text(errors='ignore')
                except OSError: continue
                if 'hdc_episodic' in text or 'hdc-episodic' in text:
                    hits.append(rel)
        self.assertLessEqual(set(hits), allowed, 'something reads the shadow memory: %s' % sorted(set(hits) - allowed))
        src = Path(H.__file__).read_text()
        for word in ('prompt', 'context_', 'requests', 'urllib', 'subprocess', 'socket'):
            self.assertNotIn(word, src.replace('no prompt', '').replace('No network', ''), word)


if __name__ == '__main__':
    unittest.main(verbosity=2)

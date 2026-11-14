"""The Gloria-axis re-grade (14 November): old one-word verdicts replaced by the rubric teacher's labels, under the
ledger lock, with a backup, idempotent, nothing else changed. Synthetic fixtures in a scratch directory only."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
import gloria_regrade as G
import priority_vector as PV

NOW = datetime(2026, 11, 14, 12, 0, 0)


def ts(days_ago, k=0):
    return (NOW - timedelta(days=days_ago, seconds=k)).isoformat()


def rj(p):
    with open(p) as f:
        return json.load(f)


def sid(t):
    return hashlib.sha1(t.encode()).hexdigest()[:32]


def row(t, gloria, field='NO', **extra):
    r = {'timestamp': t, 'target': {'goal': 'synthetic goal', 'gloria': {'difference_intended': 'synthetic'}},
         'realized': {'field': field, 'gloria': gloria, 'self': 'YES'}, 'priority': {'field': 0.25, 'gloria': 0.15, 'self': 0.6}}
    r.update(extra)
    return r


def label(r, verdict, reason, adherence='delivered', codes=None, **extra):
    x = {'id': r.get('intent_id') or sid(r['timestamp']), 'ts': r['timestamp'], 'status': 'ok', 'verdict': verdict,
         'reason': reason, 'adherence': adherence, 'codes': codes if codes is not None else [reason],
         'confidence': 'high', 'teacher': 'synthetic-teacher'}
    x.update(extra)
    return x


def fixture():
    rows = [
        row(ts(1, 1), 'NO'),                                         # 0 -> YES
        row(ts(2, 2), 'NO'),                                         # 1 -> NOT_JUDGEABLE (device)
        row(ts(3, 3), 'NO', intent_id='intent-abc'),                 # 2 -> PARTIAL, keyed by intent_id
        row(ts(4, 4), 'YES'),                                        # 3 -> NO stays (delivered)
        row(ts(5, 5), 'PARTIAL'),                                    # 4 teacher NO on a move only partly made -> NOT_JUDGEABLE
        row(ts(6, 6), 'NO'),                                         # 5 teacher YES with a NO's reason -> invalid
        row(ts(7, 7), 'NO'),                                         # 6 no label: unchanged
        row(ts(8, 8), 'NO'),                                         # 7 label timestamp differs: unchanged
        row(ts(9, 9), 'HELD'),                                       # 8 not a counted verdict: unchanged
        row(ts(9, 10), 'NOT_DECLARED'),                              # 9 unchanged
        row(ts(10, 11), 'NO', gloria_judge={'judge': 'rubric', 'verdict': 'NO', 'reason': 'not_shown'}),  # 10 rubric: unchanged
        row(ts(11, 12), 'NO', field=None),                           # 11 unsettled: unchanged
        row(ts(11, 13), 'NO', effects_pending=[{'key': 'k'}]),       # 12 effects pending: unchanged
        row(ts(40, 14), 'NO'),                                       # 13 old row: changes, outside the window
        row(ts(12, 15), 'YES'),                                      # 14 no label
    ]
    rows[0]['input_text'] = 'SECRET-SYNTHETIC-TEXT'
    labels = [
        label(rows[0], 'YES', 'plain_yes'),
        label(rows[1], 'NOT_JUDGEABLE', 'device_event_only', adherence=None),
        label(rows[2], 'PARTIAL', 'partial_hedged', adherence='partly'),
        label(rows[3], 'NO', 'not_shown'),
        label(rows[4], 'NO', 'deflected', adherence='partly'),
        label(rows[5], 'YES', 'not_shown'),
        dict(label(rows[7], 'YES', 'plain_yes'), ts=ts(8, 99)),
        label(rows[8], 'YES', 'plain_yes'),
        label(rows[9], 'YES', 'plain_yes'),
        label(rows[10], 'YES', 'plain_yes'),
        label(rows[11], 'YES', 'plain_yes'),
        label(rows[12], 'YES', 'plain_yes'),
        label(rows[13], 'YES', 'plain_yes'),
    ]
    return rows, labels

CHANGED = {0: 'YES', 1: 'NOT_JUDGEABLE', 2: 'PARTIAL', 3: 'NO', 4: 'NOT_JUDGEABLE', 5: 'NOT_JUDGEABLE', 13: 'YES'}


class Regrade(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.ledger = os.path.join(self.dir, 'intent-ledger.json')
        self.labels = os.path.join(self.dir, 'labels.jsonl')
        self.rows, labels = fixture()
        with open(self.ledger, 'w') as f:
            json.dump(self.rows, f, indent=2)
        with open(self.labels, 'w') as f:
            f.write(''.join(json.dumps(x) + '\n' for x in labels))
        self.now = NOW.timestamp()

    def tearDown(self):
        self.tmp.cleanup()

    def raw(self):
        return Path(self.ledger).read_bytes()

    def backups(self):
        return sorted(p for p in os.listdir(self.dir) if '.bak-regrade-' in p)

    def run_cli(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = G.main(['--ledger', self.ledger] + list(args))
        return code, buf.getvalue()

    def test_dry_run_counts_only_and_writes_nothing(self):
        before = self.raw()
        code, out = self.run_cli('--labels', self.labels, '--dry-run', '--now', NOW.isoformat())
        self.assertEqual(code, 0)
        rep = json.loads(out)
        self.assertEqual(rep['mode'], 'dry-run')
        self.assertEqual(rep['rows_changed'], 7)
        self.assertEqual(rep['old'], {'YES': 1, 'PARTIAL': 1, 'NO': 5})
        self.assertEqual(rep['new'], {'YES': 2, 'PARTIAL': 1, 'NO': 1, 'NOT_JUDGEABLE': 3})
        self.assertEqual(rep['gated_by_rules'], 2)
        self.assertEqual((rep['no_label'], rep['label_unusable'], rep['unsettled']), (2, 1, 2))
        self.assertEqual(self.raw(), before)
        self.assertEqual(self.backups(), [])
        self.assertNotIn('SECRET', out)
        self.assertNotIn('synthetic', out)

    def test_apply_changes_only_those_rows_and_keeps_the_original(self):
        code, out = self.run_cli('--labels', self.labels, '--now', NOW.isoformat())
        self.assertEqual(code, 0)
        rep = json.loads(out)
        after = rj(self.ledger)
        self.assertEqual(len(after), len(self.rows))
        for i, (a, b) in enumerate(zip(self.rows, after)):
            if i not in CHANGED:
                self.assertEqual(a, b, i)
                continue
            self.assertEqual(b['realized']['gloria'], CHANGED[i], i)
            gj = b['gloria_judge']
            self.assertEqual((gj['judge'], gj['rubric'], gj['verdict']), ('teacher_v2', 'v2', CHANGED[i]))
            sup = gj['superseded']
            self.assertEqual(sup['verdict'], a['realized']['gloria'])
            self.assertEqual(sup['judge'], 'one_word_local')
            self.assertEqual(sup['replaced_by']['approval'], 'regrade approved by Gloria 2026-11-14')
            self.assertEqual(sup['replaced_by']['rubric'], 'v2')
            self.assertTrue(sup['replaced_by']['date'])
            # nothing else on the row moved
            strip = lambda r: {k: v for k, v in r.items() if k != 'gloria_judge'}
            a2 = copy.deepcopy(a); a2['realized']['gloria'] = CHANGED[i]
            self.assertEqual(strip(a2), strip(b), i)
        self.assertEqual(after[4]['gloria_judge']['reason'], 'his_move_not_delivered')
        self.assertEqual(after[5]['gloria_judge']['reason'], 'invalid')
        # backup: next to the ledger, the bytes as they were
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(rep['backup'], os.path.join(self.dir, self.backups()[0]))
        self.assertEqual(rj(rep['backup']), self.rows)

    def test_idempotent(self):
        self.run_cli('--labels', self.labels, '--now', NOW.isoformat())
        once = self.raw()
        code, out = self.run_cli('--labels', self.labels, '--now', NOW.isoformat())
        rep = json.loads(out)
        self.assertEqual((code, rep['rows_changed'], rep['already_regraded'], rep['mode']), (0, 0, 7, 'nothing_to_do'))
        self.assertEqual(self.raw(), once)
        self.assertEqual(len(self.backups()), 1)

    def test_receptivity_uses_the_engines_rules(self):
        code, out = self.run_cli('--labels', self.labels, '--dry-run', '--now', NOW.isoformat())
        rep = json.loads(out)
        exp_before = PV._axis_history(self.now, rj(self.ledger))['gloria']
        self.assertEqual(rep['receptivity_before']['verdicts'], exp_before['n'])
        self.assertEqual(rep['receptivity_before']['landing_rate'], PV._landing_rate({'gloria': exp_before}))
        self.run_cli('--labels', self.labels, '--now', NOW.isoformat())
        exp_after = PV._axis_history(self.now, rj(self.ledger))['gloria']
        self.assertEqual(rep['receptivity_after']['verdicts'], exp_after['n'])
        self.assertEqual(rep['receptivity_after']['landing_rate'], PV._landing_rate({'gloria': exp_after}))
        # in the window: rows 0-7, 10-12, 14 (13 is 40 days old). Three NOT_JUDGEABLEs leave the count.
        self.assertEqual((exp_before['YES'], exp_before['PARTIAL'], exp_before['NO'], exp_before['n']), (2, 1, 9, 12))
        self.assertEqual((exp_after['YES'], exp_after['PARTIAL'], exp_after['NO'], exp_after['n']), (2, 1, 6, 9))

    def test_waits_for_the_ledger_lock_and_reads_after_it(self):
        child = subprocess.Popen([sys.executable, '-c', (
            'import fcntl, json, sys, time\n'
            'p = sys.argv[1]\n'
            'h = open(p + ".lock", "a+"); fcntl.flock(h, fcntl.LOCK_EX)\n'
            'print("held", flush=True); time.sleep(1.0)\n'
            'led = json.load(open(p)); led.append({"timestamp": "2026-11-14T11:59:00", "realized": {"gloria": "NO"}, "marker": 1})\n'
            'json.dump(led, open(p, "w"))\n'
            'h.close()\n'), self.ledger], stdout=subprocess.PIPE, text=True)
        self.assertEqual(child.stdout.readline().strip(), 'held')
        done = []
        th = threading.Thread(target=lambda: done.append(self.run_cli('--labels', self.labels, '--now', NOW.isoformat())))
        th.start()
        time.sleep(0.4)
        self.assertEqual(done, [])                  # blocked on the engine's lock
        th.join(10); child.wait(10); child.stdout.close()
        self.assertEqual(done[0][0], 0)
        after = rj(self.ledger)
        self.assertEqual(after[-1].get('marker'), 1)    # the write made under the lock survived
        self.assertEqual(after[0]['realized']['gloria'], 'YES')

    def test_takes_the_same_lock_object_as_the_engine(self):
        seen = []
        real = G.store_guard.transaction
        @contextlib.contextmanager
        def spy(path):
            seen.append(os.path.abspath(path))
            with real(path):
                yield
        G.store_guard.transaction = spy
        try:
            self.run_cli('--labels', self.labels, '--now', NOW.isoformat())
        finally:
            G.store_guard.transaction = real
        self.assertEqual(seen, [os.path.abspath(self.ledger)])

    def test_unreadable_ledger_is_never_written(self):
        Path(self.ledger).write_text('[{"torn": ')
        before = self.raw()
        code, out = self.run_cli('--labels', self.labels, '--now', NOW.isoformat())
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)['mode'], 'stopped')
        self.assertEqual(self.raw(), before)
        self.assertEqual(self.backups(), [])

    def test_revert_puts_back_exactly_the_original_rows(self):
        self.run_cli('--labels', self.labels, '--now', NOW.isoformat())
        led = rj(self.ledger); led.append({'timestamp': ts(0), 'realized': {'gloria': 'YES'}, 'later': True})
        Path(self.ledger).write_text(json.dumps(led))
        code, out = self.run_cli('--revert')
        self.assertEqual((code, json.loads(out)['rows_reverted']), (0, 7))
        back = rj(self.ledger)
        self.assertEqual(back[:-1], self.rows)
        self.assertTrue(back[-1]['later'])          # a row written since stays

    def test_restore_from_backup(self):
        _, out = self.run_cli('--labels', self.labels, '--now', NOW.isoformat())
        bak = json.loads(out)['backup']
        os.utime(bak, (1e9, 1e9))
        code, out = self.run_cli('--restore', bak)
        self.assertEqual(code, 0)
        self.assertEqual(rj(self.ledger), self.rows)
        self.assertGreater(os.stat(self.ledger).st_mtime, 1e9 + 1)   # a fresh mtime, not the backup's
        self.assertEqual(len(self.backups()), 2)    # what the restore replaced is kept too


    def test_dry_run_is_refused_with_revert_or_restore(self):
        before = self.raw()
        for args in (['--revert', '--dry-run'], ['--restore', self.ledger, '--dry-run'], ['--revert', '--labels', self.labels]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.run_cli(*args)
        self.assertEqual(self.raw(), before)

    def test_duplicate_label_ids_stop(self):
        with open(self.labels, 'a') as f:
            f.write(Path(self.labels).read_text().splitlines()[0] + '\n')
        before = self.raw()
        code, out = self.run_cli('--labels', self.labels, '--now', NOW.isoformat())
        self.assertEqual((code, json.loads(out)['mode']), (2, 'stopped'))
        self.assertEqual(self.raw(), before)


if __name__ == '__main__':
    unittest.main()

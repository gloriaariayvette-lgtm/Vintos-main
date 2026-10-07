"""Owner-admin external reconciliation: scratch queue, local fixture git, no providers/senders."""
import copy
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import study_fix as sf


class Reconcile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.ws = self.root / 'workspace'; self.mem = self.ws / 'memory'
        self.mem.mkdir(parents=True); (self.ws / 'scripts').mkdir()
        self.repo = self.root / 'repo'; (self.repo / 'scripts').mkdir(parents=True)
        for name, value in {'WS': self.ws, 'MEMORY': self.mem, 'QUEUE': self.mem / 'queue.json',
                            'LOCK': self.mem / 'worker.lock', 'RESET': self.mem / 'reset.json',
                            'CHECKOUT': self.repo, 'WORKBENCH': self.root / 'workbench'}.items():
            p = patch.object(sf, name, str(value)); p.start(); self.addCleanup(p.stop)
        for name in ['fable', 'say', 'tell_gloria', 'work', 'watch']:
            p = patch.object(sf, name, Mock(side_effect=AssertionError('no execution or sends')))
            p.start(); self.addCleanup(p.stop)
        p = patch('socket.socket.connect', side_effect=AssertionError('no network')); p.start(); self.addCleanup(p.stop)
        p = patch.object(sf, '_today', return_value='2026-10-07'); p.start(); self.addCleanup(p.stop)
        self.assertTrue(Path(sf.QUEUE).is_relative_to(self.root)); self.assertIsInstance(sf.fable, Mock)
        self.target = self.ws / 'scripts/home_presence.py'; self.target.write_text('# fixture source\n')
        (self.repo / 'scripts/home_presence.py').write_bytes(self.target.read_bytes())
        self.git('init', '-q'); self.git('add', 'scripts/home_presence.py')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
        self.commit = self.git('rev-parse', 'HEAD')
        self.row = {'id': 'SF-1234abcd', 'what': 'fixture approved external correction', 'state': 'queued',
                    'asked': '2026-10-07T12:00:00', 'by': 'fixture', 'log': [{'at': 'fixture', 'what': 'queued'}]}
        self.save([self.row]); self.expected = sf.record_sha256(self.row)
        self.receipt_path = self.root / 'release.json'
        self.receipt = {'status': 'installed_locally', 'study_id': self.row['id'], 'automated_study_review': False,
                        'target': str(self.target), 'installed_sha256': hashlib.sha256(self.target.read_bytes()).hexdigest(),
                        'smoke': [{'suite': 'synthetic', 'exit_code': 0}]}
        self.write_receipt()

    def git(self, *args): return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.DEVNULL, text=True).strip()
    def save(self, rows): Path(sf.QUEUE).write_text(json.dumps(rows))
    def rows(self): return json.loads(Path(sf.QUEUE).read_text())
    def write_receipt(self):
        self.receipt_path.write_text(json.dumps(self.receipt))
        self.receipt_hash = hashlib.sha256(self.receipt_path.read_bytes()).hexdigest()
    def run_reconcile(self, **kwargs):
        args = dict(fix_id=self.row['id'], receipt_path=str(self.receipt_path), receipt_sha256=self.receipt_hash,
                    commit=self.commit, expected_record_sha256=self.expected)
        args.update(kwargs); return sf.reconcile_external(**args)

    def test_preserves_history_other_rows_and_daily_usage(self):
        older = [{'id': 'old-%d' % n, 'state': 'done', 'asked': '2026-10-06'} for n in range(205)]
        self.save(older + [self.row]); before = sf.used_today(self.rows())
        result = self.run_reconcile(); rows = self.rows()
        self.assertEqual(rows[:-1], older); self.assertEqual(len(rows), 206)
        self.assertEqual(sf.used_today(rows), before)
        self.assertEqual(result['state'], 'implemented_externally')
        self.assertEqual(result['log'][:-1], self.row['log'])
        self.assertFalse(result['external_release']['study_reviewed'])
        self.assertEqual(result['external_release']['receipt_sha256'], self.receipt_hash)

    def test_idempotent_repeat_does_not_rewrite_or_append(self):
        first = self.run_reconcile(); data = Path(sf.QUEUE).read_bytes()
        self.assertEqual(self.run_reconcile(), first); self.assertEqual(Path(sf.QUEUE).read_bytes(), data)

    def test_worker_never_selects_external_record_or_duplicates_request(self):
        self.run_reconcile()
        self.assertEqual(sf.tend(), 'nothing queued'); sf.work.assert_not_called(); sf.fable.assert_not_called()
        row, why = sf.request(self.row['what'])
        self.assertIsNone(row); self.assertTrue(why); self.assertEqual(len(self.rows()), 1)

    def test_changed_or_active_registration_refused(self):
        for state in ['working', 'watching', 'done', 'failed']:
            self.save([dict(self.row, state=state)]); before = Path(sf.QUEUE).read_bytes()
            with self.assertRaises(ValueError): self.run_reconcile()
            self.assertEqual(Path(sf.QUEUE).read_bytes(), before)
        self.save([dict(self.row, what='changed after approval')])
        with self.assertRaises(ValueError): self.run_reconcile()

    def test_worker_and_request_locks_refuse_races(self):
        for name in [sf.LOCK, sf.QUEUE + '.request.lock']:
            with open(name, 'a+') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError): self.run_reconcile()
        self.assertEqual(self.rows(), [self.row])

    def test_mismatched_receipt_or_installed_bytes_refused(self):
        with self.assertRaises(ValueError): self.run_reconcile(receipt_sha256='0' * 64)
        for change in [{'study_id': 'SF-deadbeef'}, {'automated_study_review': True},
                       {'smoke': [{'suite': 'fixture', 'exit_code': 1}]}]:
            original = copy.deepcopy(self.receipt); self.receipt.update(change); self.write_receipt()
            with self.assertRaises(ValueError): self.run_reconcile()
            self.receipt = original; self.write_receipt()
        self.target.write_text('# newer runtime\n')
        with self.assertRaises(ValueError): self.run_reconcile()
        self.assertEqual(self.rows(), [self.row])

    def test_commit_source_must_match(self):
        (self.repo / 'scripts/home_presence.py').write_text('# other source\n'); self.git('add', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'other')
        with self.assertRaises(ValueError): self.run_reconcile(commit=self.git('rev-parse', 'HEAD'))

    def test_atomic_write_failure_preserves_record_and_cleans_temp(self):
        before = Path(sf.QUEUE).read_bytes()
        with patch.object(sf.os, 'replace', side_effect=OSError('fixture failed replace')):
            with self.assertRaises(OSError): self.run_reconcile()
        self.assertEqual(Path(sf.QUEUE).read_bytes(), before)
        self.assertFalse(list(self.mem.glob('.study-reconcile-*')))

    def test_changed_reconciliation_evidence_or_history_refused(self):
        self.run_reconcile(); self.receipt['extra'] = 'different evidence'; self.write_receipt()
        with self.assertRaises(ValueError): self.run_reconcile()
        self.receipt.pop('extra'); self.write_receipt()
        rows = self.rows(); rows[0]['log'].append({'at': 'later', 'what': 'changed'}); self.save(rows)
        with self.assertRaises(ValueError): self.run_reconcile()

    def test_status_never_claims_automated_review(self):
        self.run_reconcile()
        self.assertIn('implemented locally; not Study-reviewed', sf.record())
        self.assertIn('not Study-reviewed', sf.claim_check('Study SF-1234abcd is deployed.'))

    def test_corrupt_queue_refused_without_empty_fallback(self):
        Path(sf.QUEUE).write_text('{broken')
        with self.assertRaises(ValueError): self.run_reconcile()
        self.assertEqual(Path(sf.QUEUE).read_text(), '{broken')


if __name__ == '__main__': unittest.main()

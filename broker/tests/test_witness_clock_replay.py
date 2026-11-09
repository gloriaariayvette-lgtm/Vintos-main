#!/usr/bin/env python3
"""Actual synthetic clock sidecars through the private offline reader."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value
F = module('clock_producer_fixture', 'broker/tests/test_witness_source_clocks.py')
R = module('clock_audit_replay', 'experiments/judges-witness/replay.py')

class Tests(unittest.TestCase):
    base = F.Tests.base
    setUp = F.Tests.setUp
    packets = F.Tests.packets
    chat = F.Tests.chat
    ledger = F.Tests.ledger
    forecast = F.Tests.forecast
    job = F.Tests.job
    clocks = F.Tests.clocks
    aware = F.Tests.aware

    def pair(self):
        row = self.job()
        receipt, = self.clocks()
        return row, receipt

    def audit(self, row, receipt, cutoff=None):
        return R.forecast_clock_observations([row], [receipt], cutoff or self.base + 1000)

    def rebind(self, row, receipt):
        receipt['forecast_row_sha256'] = F.F.W._fingerprint(row)

    def test_actual_producer_naive_clock_matches_without_reinterpreting(self):
        row, receipt = self.pair(); before = copy.deepcopy((row, receipt))
        result = self.audit(row, receipt)
        self.assertEqual(result['states'], {'matching_record_unparsed_rendered_clock': 1})
        self.assertEqual(result['admission_effect'], 'none')
        self.assertEqual(result['scoring_effect'], 'none')
        self.assertEqual(before, (row, receipt))
        for private in (receipt['forecast_row_sha256'], row['self']['context_last_ts'], 'source-fixture'):
            self.assertNotIn(private, json.dumps(result))

    def test_explicit_rendered_clock_agreement_and_disagreement(self):
        row, receipt = self.pair()
        for delta, state in ((0, 'matching_record_explicit_clock'), (1, 'explicit_clock_disagrees')):
            row['self']['context_last_ts'] = self.aware(self.raw + delta)
            self.rebind(row, receipt)
            receipt['context_clock']['rendered_clock_sha256'] = R.digest(row['self']['context_last_ts'])
            self.assertEqual(self.audit(row, receipt)['states'], {state: 1})

    def test_no_similarity_or_proximity_join(self):
        row, receipt = self.pair(); row['extra'] = 'synthetic different version'
        result = self.audit(row, receipt)
        self.assertEqual(result['states'], {'forecast_row_unavailable': 1})
        self.assertEqual(result['forecasts_without_receipt'], 1)

    def test_missing_receipts_and_identical_copies_count_once(self):
        row, receipt = self.pair()
        result = R.forecast_clock_observations([row, row], [receipt, copy.deepcopy(receipt)], self.base+1000)
        self.assertEqual(result['unique_forecasts_supplied'], 1)
        self.assertEqual(result['unique_receipts_supplied'], 1)
        self.assertEqual(R.forecast_clock_observations([row], [], self.base+1000)['forecasts_without_receipt'], 1)

    def test_conflicting_duplicates_abort_even_outside_cutoff(self):
        row, receipt = self.pair(); other = copy.deepcopy(receipt)
        other['context_clock']['epoch'] += 1
        for receipts in ([receipt, other], [other, receipt]):
            with self.assertRaisesRegex(ValueError, '^conflicting forecast clock observations$'):
                R.forecast_clock_observations([row], receipts, 1)

    def test_strict_shapes_identity_and_numeric_epoch(self):
        row, receipt = self.pair()
        mutations = [('schema', 'bad'), ('source_identity', 'verified'), ('durability', 'confirmed'),
                     ('boundary', 'delivered'), ('forecast_row_sha256', 'private-invalid'), ('extra', 'private')]
        for key, value in mutations:
            bad = copy.deepcopy(receipt); bad[key] = value
            with self.assertRaisesRegex(ValueError, '^invalid forecast clock observation$'):
                self.audit(row, bad)
        for key, value in [('epoch', True), ('epoch', float('inf')), ('epoch', self.aware(self.raw)),
                           ('raw_kind', 'naive_iso'), ('meaning', 'reply_finalization'),
                           ('raw_clock_sha256', 'bad'), ('extra', 'private')]:
            bad = copy.deepcopy(receipt); bad['context_clock'][key] = value
            with self.assertRaisesRegex(ValueError, '^invalid forecast clock observation$'):
                self.audit(row, bad)

    def test_noncausal_receipts_fail_before_cutoff_filter(self):
        row, receipt = self.pair()
        for field, value in [('arrived_at', self.raw), ('forecast_at', self.base+199), ('forecast_at', True)]:
            bad = copy.deepcopy(receipt); bad[field] = value
            with self.assertRaisesRegex(ValueError, '^invalid forecast clock observation$'):
                self.audit(row, bad, cutoff=1)

    def test_row_modes_and_clocks_are_verified_independently(self):
        row, receipt = self.pair()
        for field, value, state in [('mode', 'ahead', 'forecast_mode_mismatch'),
                                    ('ts', self.base+211, 'forecast_clock_mismatch'),
                                    ('arrived_at', None, 'forecast_clock_mismatch')]:
            bad = copy.deepcopy(row); bad[field] = value; self.rebind(bad, receipt)
            self.assertEqual(self.audit(bad, receipt)['states'], {state: 1})

    def test_rendered_binding_is_required(self):
        row, receipt = self.pair()
        for value in (None, 'synthetic different clock', 'x'*129):
            row['self']['context_last_ts'] = value; self.rebind(row, receipt)
            self.assertEqual(self.audit(row, receipt)['states'], {'rendered_clock_mismatch': 1})

    def test_exclusive_cutoff_and_empty_inputs(self):
        row, receipt = self.pair()
        self.assertEqual(self.audit(row, receipt, receipt['forecast_at'])['states'], {'outside_cutoff': 1})
        self.assertEqual(R.forecast_clock_observations([], [], self.base+1000)['states'], {})

    def test_cli_is_opt_in_manifest_bound_and_does_not_change_other_reports(self):
        row, receipt = self.pair()
        bundle = {'input_kind': 'synthetic', 'forecasts': [row]}
        reports = []
        for number in range(2):
            if number: bundle['self_forecast_clocks'] = [receipt]
            source = self.root / ('bundle-%s.json' % number)
            output = self.root / ('report-%s' % number)
            source.write_text(json.dumps(bundle)); os.chmod(source, 0o600)
            proc = subprocess.run([sys.executable, str(ROOT/'experiments/judges-witness/replay.py'),
                '--scratch', str(self.root), '--input', str(source), '--output', str(output),
                '--cutoff', self.aware(self.base+1000)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads((output/'aggregate.json').read_text())
            manifest = json.loads((output/'private-run.json').read_text())
            self.assertIn(R.hashlib.sha256((output/'aggregate.json').read_bytes()).hexdigest(), json.dumps(manifest))
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in output.iterdir()))
            reports.append(report)
        self.assertNotIn('forecast_clock_observations', reports[0])
        self.assertEqual(reports[1].pop('forecast_clock_observations')['states'],
                         {'matching_record_unparsed_rendered_clock': 1})
        self.assertEqual(reports[0], reports[1])

if __name__ == '__main__': unittest.main()

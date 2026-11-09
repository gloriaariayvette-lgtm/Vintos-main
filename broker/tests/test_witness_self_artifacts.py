#!/usr/bin/env python3
"""Private artifact observations using synthetic checkpoints and stub encoders only."""
import hashlib
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import jepa_readout as R
import witness_capture as W
import witness_self_artifacts as A
from witness_receipts import digest
from test_witness_self_forecast_inputs import Tests as Inputs

ORIGINAL = {k: getattr(R, k) for k in ('load', 'arrays', 'predict', 'confidence')}


class Tests(unittest.TestCase):
    def setUp(self):
        self.case = Inputs('test_actual_job_binds_exact_saved_row_and_recent_inputs')
        self.case.setUp(); self.addCleanup(self.case.doCleanups)
        self.root = self.case.root
        self.path = self.case.models / 'self_on_message.npz'
        self.meta = {'schema': R.SCHEMA, 'mode': 'self_on_message', 'report': {'confidence': {}},
                     'trained_through': '2026-10-01', 'calibrated_through': '2026-10-12'}
        self.write_model()
        self.case.enc.encode.side_effect = lambda texts, **kw: np.array([[1., 2.] for t in texts])
        for name, fn in ORIGINAL.items():
            p = patch.object(R, name, fn); p.start(); self.addCleanup(p.stop)
        A.COUNTERS.clear()
        self.assertNotIn('.vintos', self.root.parts)
        self.assertEqual(Path(os.environ['SPARK_WORKSPACE']), self.root)
        self.assertTrue(hasattr(self.case.enc.encode, 'mock_calls'))

    def write_model(self):
        np.savez_compressed(self.path, meta=json.dumps(self.meta), projection=np.ones((2, 1)),
                            W=np.zeros((1, 8)), bias=np.zeros(1), beta=1., gamma=0., confidence_W=np.zeros(5))

    def packets(self, prefix='self-forecast-artifacts-'):
        files = list(self.root.glob(prefix + '*.json'))
        self.assertTrue(all(f.stat().st_mode & 0o777 == 0o600 for f in files))
        return [json.loads(f.read_text()) for f in files]

    def manifest(self):
        return A.checkpoint(self.path.read_bytes(), self.meta)

    def ledger(self):
        return [{'timestamp': '2026-10-20T12:00:00Z', 'vintos': 'synthetic source reply', 'turn_id': 'synthetic-id'}]

    def test_load_hashes_the_same_checkpoint_bytes_it_parses(self):
        model = R.load(self.path, retain=True)
        manifest = model['_witness_checkpoint']
        self.assertEqual(manifest['checkpoint_id'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(manifest['metadata_sha256'], W._fingerprint(model['meta']))
        self.assertNotIn('_witness_checkpoint', R.load(self.path))
        self.assertFalse(manifest['weights_retained'])

    def test_declared_dates_never_become_training_completion_or_encoder_identity(self):
        self.meta.update(trained_at='2026-10-12T12:00:00Z', encoder='synthetic-label')
        m = self.manifest()
        self.assertEqual(m['reported_trained_at'], self.meta['trained_at'])
        self.assertEqual(m['reported_encoder_label'], 'synthetic-label')
        self.assertIsNone(m['trained_at']); self.assertIsNone(m['encoder_id'])
        self.assertIsNone(A.checkpoint(b'x', dict(self.meta, mode='gloria')))

    def test_actual_job_off_on_identical_with_no_additional_encoder_calls(self):
        with patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH='', JUDGES_CAPTURE_CONFIG=''):
            off = self.case.job()
        calls = self.case.enc.encode.call_count
        on = self.case.job()
        self.assertEqual(off, on)
        self.assertEqual(self.case.enc.encode.call_count, 2 * calls)
        packet, = self.packets()
        self.assertEqual(packet['forecast_row_sha256'], W._fingerprint(on))
        artifacts = packet['artifacts']; refs = artifacts['recent_own_embeddings']
        self.assertEqual(len(refs), 6)
        self.assertEqual(refs[-1]['observed_turn_id'], self.case.exs[-1]['turn_id'])
        self.assertEqual(refs[-1]['normalized_reply_sha256'], digest(self.case.exs[-1]['his']))
        self.assertTrue(np.allclose(refs[-1]['emb'], np.array([1., 2.]) / np.sqrt(5)))
        self.assertNotIn(self.case.exs[-1]['his'], json.dumps(packet))
        self.assertIsNone(refs[-1]['encoder_id'])

    def test_long_reply_binds_exact_prefix_and_full_normalized_hash(self):
        self.case.exs[-1]['his'] = 'a' * 400 + 'different ending'
        self.case.job()
        ref = self.packets()[0]['artifacts']['recent_own_embeddings'][-1]
        self.assertEqual(ref['encoder_input_sha256'], digest('a' * 400))
        self.assertNotEqual(ref['normalized_reply_sha256'], ref['encoder_input_sha256'])
        self.assertEqual(ref['encoder_input_chars'], 400)

    def test_checkpoint_replaced_during_forecast_is_not_bound(self):
        def changed(model, values):
            result = ORIGINAL['predict'](model, values)
            self.meta['selected'] = 'changed'; self.write_model()
            return result
        with patch.object(R, 'predict', side_effect=changed):
            row = self.case.job()
        self.assertIsNotNone(row)
        self.assertEqual(self.packets(), [])
        self.assertEqual(A.COUNTERS['checkpoint_unbound'], 1)

    def test_failed_retention_does_not_change_forecast_or_existing_log(self):
        with patch.object(A, 'forecast_artifacts', side_effect=OSError('synthetic retention failure')):
            row = self.case.job()
        self.assertEqual(row, json.loads(self.case.output.read_text()))
        self.assertEqual(self.packets(), [])

    def test_oversized_checkpoint_observation_falls_back_to_existing_load(self):
        with patch.object(A, 'MAX_CHECKPOINT', 2):
            model = R.load(self.path, retain=True)
        self.assertNotIn('_witness_checkpoint', model)
        self.assertEqual(model['meta'], self.meta)

    def test_audit_retains_existing_output_without_extra_encoding(self):
        wrapped = A.audit_encoder(self.case.enc, self.ledger(), self.manifest())
        raw = np.array([[3., 4.]])
        self.case.enc.encode.side_effect = None; self.case.enc.encode.return_value = raw
        self.assertIs(wrapped.encode(['synthetic source reply']), raw)
        self.assertEqual(self.case.enc.encode.call_count, 1)
        packet, = self.packets('self-audit-embedding-')
        self.assertEqual(packet['emb'], [3., 4.])
        self.assertEqual(packet['source_refs'][0]['observed_turn_id'], 'synthetic-id')
        self.assertEqual(packet['target_selection'], 'unasserted')
        self.assertNotIn('synthetic source reply', json.dumps(packet))
        wrapped.encode(['synthetic source reply'])
        self.assertEqual(len(self.packets('self-audit-embedding-')), 1)

    def test_prefix_collisions_retain_all_source_refs_without_selecting_target(self):
        ledger = [dict(self.ledger()[0], vintos='x'*400 + ending, turn_id=key)
                  for ending, key in [('one', 'one'), ('two', 'two')]]
        wrapped = A.audit_encoder(self.case.enc, ledger, self.manifest())
        wrapped.encode(['x'*400])
        refs = self.packets('self-audit-embedding-')[0]['source_refs']
        self.assertEqual(len(refs), 2)
        self.assertNotEqual(refs[0]['source_reply_sha256'], refs[1]['source_reply_sha256'])

    def test_changed_vector_for_same_input_is_retained_without_extra_encoding(self):
        wrapped = A.audit_encoder(self.case.enc, self.ledger(), self.manifest())
        first, second = np.array([[3., 4.]]), np.array([[4., 3.]])
        self.case.enc.encode.side_effect = [first, second, first, second]
        for value in (first, second, first, second):
            self.assertIs(wrapped.encode(['synthetic source reply']), value)
        self.assertEqual(self.case.enc.encode.call_count, 4)
        packets = self.packets('self-audit-embedding-')
        self.assertEqual(sorted(p['emb'] for p in packets), [[3., 4.], [4., 3.]])
        self.assertEqual(len(wrapped.seen), 2)
        self.assertTrue(all(p['encoder_id'] is None for p in packets))

    def test_invalid_later_vector_is_not_hidden_by_input_deduplication(self):
        wrapped = A.audit_encoder(self.case.enc, self.ledger(), self.manifest())
        valid, invalid = np.array([[1., 0.]]), np.array([[float('nan'), 0.]])
        self.case.enc.encode.side_effect = [valid, invalid]
        self.assertIs(wrapped.encode(['synthetic source reply']), valid)
        self.assertIs(wrapped.encode(['synthetic source reply']), invalid)
        self.assertEqual(len(self.packets('self-audit-embedding-')), 1)
        self.assertEqual(A.COUNTERS['audit_retention_failed'], 1)

    def test_failed_changed_observation_can_retry_and_limits_are_bounded(self):
        wrapped = A.audit_encoder(self.case.enc, self.ledger(), self.manifest())
        self.case.enc.encode.side_effect = None
        self.case.enc.encode.return_value = np.array([[1., 0.]])
        with patch.object(W, '_publish_private', return_value=False):
            wrapped.encode(['synthetic source reply'])
        self.assertEqual(wrapped.seen, set())
        wrapped.encode(['synthetic source reply'])
        self.case.enc.encode.return_value = np.array([[0., 1.]])
        with patch.object(A, 'MAX_AUDIT_OBSERVATIONS', 1):
            self.assertIs(wrapped.encode(['synthetic source reply']), self.case.enc.encode.return_value)
        self.assertEqual(A.COUNTERS['audit_observation_limit'], 1)
        self.assertEqual(len(wrapped.seen), 1)
        self.assertEqual(len(self.packets('self-audit-embedding-')), 1)
        wrapped.encode(['synthetic source reply'])
        self.assertEqual(len(wrapped.seen), 2)

    def test_same_batch_changed_results_are_retained(self):
        wrapped = A.audit_encoder(self.case.enc, self.ledger(), self.manifest())
        output = np.array([[1., 0.], [0., 1.], [1., 0.]])
        self.case.enc.encode.side_effect = None; self.case.enc.encode.return_value = output
        self.assertIs(wrapped.encode(['synthetic source reply'] * 3), output)
        self.assertEqual(len(self.packets('self-audit-embedding-')), 2)
        self.assertEqual(self.case.enc.encode.call_count, 1)

    def test_missing_source_id_stays_missing(self):
        row = self.ledger()[0]; row.pop('turn_id')
        A.audit_encoder(self.case.enc, [row], self.manifest()).encode([row['vintos']])
        self.assertIsNone(self.packets('self-audit-embedding-')[0]['source_refs'][0]['observed_turn_id'])

    def test_invalid_vectors_never_publish_and_encoder_errors_still_propagate(self):
        for value in ([True, False], [0., 0.], [float('nan'), 1.], [float('inf'), 1.]):
            with self.assertRaises(ValueError): A.vector(value)
        wrapped = A.audit_encoder(self.case.enc, self.ledger(), self.manifest())
        raw = np.array([[float('nan'), 0.]])
        self.case.enc.encode.side_effect = None; self.case.enc.encode.return_value = raw
        self.assertIs(wrapped.encode(['synthetic source reply']), raw)
        self.assertEqual(self.packets('self-audit-embedding-'), [])
        self.case.enc.encode.side_effect = RuntimeError('synthetic encoder error')
        with self.assertRaises(RuntimeError): wrapped.encode(['synthetic source reply'])

    def test_storage_failure_does_not_change_audit_return(self):
        raw = np.array([[1., 0.]])
        self.case.enc.encode.side_effect = None; self.case.enc.encode.return_value = raw
        wrapped = A.audit_encoder(self.case.enc, self.ledger(), self.manifest())
        with patch.object(W, '_publish_private', side_effect=OSError('synthetic failure')):
            self.assertIs(wrapped.encode(['synthetic source reply']), raw)
        self.assertEqual(A.COUNTERS['audit_retention_failed'], 1)

    def test_disabled_capture_returns_original_encoder(self):
        with patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH='', JUDGES_CAPTURE_CONFIG=''):
            self.assertIs(A.audit_encoder(self.case.enc, self.ledger(), self.manifest()), self.case.enc)
        self.assertEqual(self.packets('self-audit-embedding-'), [])

    def test_dedicated_sink_caps_and_hot_disable_apply_to_new_packets(self):
        from test_witness_sink import Tests as Sink
        sink = Sink('test_production_destination_is_independent_of_workspace')
        sink.setUp(); self.addCleanup(sink.doCleanups)
        row = self.case.job()
        packets = list(sink.sink.glob('self-forecast-artifacts-*.json'))
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0].stat().st_mode & 0o777, 0o600)
        sink.settings['enabled'] = False; sink.write_config()
        self.assertEqual(self.case.job(), row)
        self.assertEqual(len(list(sink.sink.glob('self-forecast-artifacts-*.json'))), 1)
        sink.settings['enabled'] = True; sink.settings['max_packet_bytes'] = 1; sink.write_config()
        self.assertEqual(self.case.job(), row)
        self.assertEqual(len(list(sink.sink.glob('self-forecast-artifacts-*.json'))), 1)

    def test_real_ranking_audit_scores_and_encoding_count_are_unchanged(self):
        import jepa_ranking_audit as ranking
        ledger = [dict(self.ledger()[0], timestamp='2026-10-20T12:%02d:00Z' % i,
                       vintos='synthetic reply %d' % i) for i in range(8)]
        at = ranking._epoch('2026-10-20T12:02:30Z')
        history = [{'ts': at, 'checkpoint_id': 'synthetic-checkpoint', 'self': {'emb': [1., 0.]}}]
        off = ranking.evaluate(history, ledger, self.case.enc, checkpoint='synthetic-checkpoint')
        n = self.case.enc.encode.call_count
        wrapped = A.audit_encoder(self.case.enc, ledger, self.manifest())
        on = ranking.evaluate(history, ledger, wrapped, checkpoint='synthetic-checkpoint')
        self.assertTrue(on)
        self.assertEqual(on, off)
        self.assertEqual(self.case.enc.encode.call_count, 2*n)
        self.assertGreater(len(self.packets('self-audit-embedding-')), 0)

    def test_existing_audit_wraps_only_self_and_preserves_report(self):
        for mode in R.MODES:
            np.savez_compressed(self.case.models / (mode+'.npz'), meta=json.dumps(dict(self.meta, mode=mode)))
        ledger = self.ledger()
        observed = []
        def evaluate(rows, supplied, enc, **kw):
            observed.append(isinstance(enc, A.AuditEncoder))
            enc.encode([ledger[0]['vintos']], show_progress_bar=False)
            return [{'synthetic_score': 1}]
        ra = types.SimpleNamespace(MEM=str(self.case.memory), realized_ledger=lambda: ledger,
            _jsonl=lambda p: [], evaluate=evaluate, _summary=lambda rows, head: rows,
            _atomic=lambda path, value: Path(path).write_text(json.dumps(value)))
        with patch.dict(sys.modules, jepa_ranking_audit=ra):
            with patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH='', JUDGES_CAPTURE_CONFIG=''):
                off = R.audit(self.case.enc, self.case.memory)
            on = R.audit(self.case.enc, self.case.memory)
        self.assertEqual(on, off)
        self.assertEqual(observed, [False, False, False, False, True, True])
        self.assertEqual(self.case.enc.encode.call_count, 6)
        self.assertEqual(len(self.packets('self-audit-embedding-')), 2)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())

#!/usr/bin/env python3
"""Actual self readout/job boundaries on synthetic data, no model calls or sends."""
import ast
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import witness_capture as W
import jepa_readout as R
from witness_receipts import digest


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='self-forecast-inputs-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.memory = self.root / 'memory'; self.memory.mkdir()
        self.models = self.memory / 'jepa-readouts'; self.models.mkdir()
        (self.models / 'self_on_message.npz').write_bytes(b'synthetic checkpoint bytes')
        self.pending = self.root / 'pending.json'
        self.output = self.root / 'existing-log.jsonl'
        self.sender = Mock(side_effect=AssertionError('external action forbidden'))
        self.enc = types.SimpleNamespace(encode=Mock(return_value=np.array([[1., 0.]])))
        self.ns = dict(os=os, json=json, time=time, MEMORY=str(self.memory), SELF_MODEL='unused',
                       ON_MESSAGE_LOG=str(self.output), PENDING_MAX_AGE=300, log=Mock(),
                       load_model=Mock(return_value=None), _iso=lambda x: str(x), her_key=digest)
        source = (ROOT / 'scripts/jepa_self_head.py').read_text()
        tree = ast.parse(source)
        selected = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name in ('_forecast_witness', 'on_message_job', '_on_message_cut')]
        exec(compile(ast.Module(body=selected, type_ignores=[]), 'actual-self-job', 'exec'), self.ns)
        self.sh = types.SimpleNamespace(_her=lambda x: x, her_key=digest,
                    _on_message_cut=self.ns['_on_message_cut'], _forecast_witness=self.ns['_forecast_witness'])
        self.exs = [dict(his='private synthetic reply ' + str(i), her='synthetic other ' + str(i),
                         turn_id='fixture-turn-' + str(i), at=100. + i * 10, ts=str(100. + i * 10))
                    for i in range(8)]
        self.synthetic_fc = dict(her_key=digest('synthetic arrival'), source='fixture-readout', checkpoint_id='fixture-checkpoint',
                                 context_last_ts='170', confidence=.4, qualification='fixture', coherence=0., emb=[1., 0.])
        self.ns['forecast'] = self.forecast
        self.scope_token = W._self_forecast_scope.set(None)
        self.addCleanup(W._self_forecast_scope.reset, self.scope_token)
        for p in (patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=str(self.root), SPARK_WORKSPACE=str(self.root)),
                  patch.object(socket.socket, 'connect', self.sender),
                  patch.dict(sys.modules, jepa_self_head=self.sh,
                    jepa_predictor=types.SimpleNamespace(format_context=lambda turns: 'synthetic context')),
                  patch.object(R, 'arrays', return_value=[np.array([[1., 0.]]), np.array([[0., 1.]])]),
                  patch.object(R, 'load', return_value={'meta': {'mode': 'self_on_message', 'report': {'confidence': {}}}}),
                  patch.object(R, 'predict', return_value=np.array([[.23456, .87654]])),
                  patch.object(R, 'confidence', return_value=np.array([.4]))):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertNotIn('.vintos', self.root.parts)
        self.assertIsInstance(self.enc.encode, Mock)
        self.assertEqual(Path(self.ns['MEMORY']), self.memory)

    def forecast(self, enc, **kw):
        return R.forecast(enc, 'self_on_message', exs=self.exs, her=kw['her'],
                          now=kw['arrived_at'], model_dir=self.models)

    def job(self):
        self.pending.write_text(json.dumps(dict(her='synthetic arrival', arrived_at=200.,
                                                surface='fixture-chat', turn_id='fixture-target')))
        return self.ns['on_message_job'](str(self.pending), enc=self.enc, now=210.)

    def packets(self):
        paths = list(self.root.glob('self-forecast-inputs-*.json'))
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in paths))
        self.assertFalse(list(self.root.glob('.*.tmp')))
        return [json.loads(p.read_text()) for p in paths]

    def test_actual_job_binds_exact_saved_row_and_recent_inputs(self):
        row = self.job(); packet, = self.packets()
        self.assertEqual(row, json.loads(self.output.read_text()))
        self.assertEqual(packet['forecast_row_sha256'], W._fingerprint(row))
        self.assertEqual(packet['boundary'], 'forecast_log_close')
        self.assertEqual(packet['state'], 'observed')
        refs = packet['inputs']['reply_refs']
        self.assertEqual([r['observed_turn_id'] for r in refs], [x['turn_id'] for x in self.exs[-6:]])
        self.assertEqual(refs[-1]['encoder_input_sha256'], digest(self.exs[-1]['his']))
        self.assertFalse(packet['complete_forecast_context'])
        self.assertFalse(packet['inputs']['upstream_complete'])
        self.assertEqual(packet['inputs']['encoder_identity'], 'unobserved')
        self.assertNotIn('private synthetic reply', json.dumps(packet))
        self.assertNotIn('synthetic arrival', json.dumps(packet))
        self.assertNotIn('emb', packet)
        self.assertIsNone(W._self_forecast_scope.get())

    def test_off_and_on_have_identical_rows_and_one_encoder_call_each(self):
        with patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=''):
            off = self.job(); self.assertEqual(self.packets(), [])
        on = self.job()
        self.assertEqual(on, off)
        self.assertEqual(self.enc.encode.call_count, 2)
        self.assertEqual(self.output.read_text().splitlines()[0], self.output.read_text().splitlines()[1])

    def test_actual_cut_excludes_future_arrival_and_matching_counterpart(self):
        self.exs += [dict(self.exs[0], her='synthetic arrival', at=199., ts='199'),
                     dict(self.exs[0], at=200., ts='200'), dict(self.exs[0], at=205., ts='205')]
        self.job(); packet, = self.packets()
        refs = packet['inputs']['reply_refs']
        self.assertEqual([r['exchange_at'] for r in refs], [120., 130., 140., 150., 160., 170.])
        self.assertEqual(packet['inputs']['as_of_exchange_at'], 170.)

    def test_truncation_and_missing_ids_never_invent_full_reply_identity(self):
        self.exs[-1]['his'] = 'z' * 450
        self.exs[-1]['turn_id'] = ''
        self.job(); packet, = self.packets(); ref = packet['inputs']['reply_refs'][-1]
        self.assertEqual(ref['encoder_input_chars'], 400)
        self.assertEqual(ref['encoder_input_sha256'], digest('z' * 400))
        self.assertEqual(ref['normalized_reply_sha256'], digest('z' * 450))
        self.assertIsNone(ref['observed_turn_id'])
        self.assertNotIn('response_sha256', ref)

    def test_bad_selection_oversize_or_clock_stays_unavailable(self):
        for kind in ('oversize', 'clock', 'mismatch'):
            with self.subTest(kind=kind):
                token = W.begin_self_forecast()
                exs = [dict(self.exs[0])]
                own = [exs[0]['his']]
                if kind == 'oversize': exs[0]['his'] = 'x' * 65537; own = ['x' * 400]
                if kind == 'clock': exs[0]['at'] = 201.
                if kind == 'mismatch': own = ['wrong text']
                W.observe_self_forecast(exs, own, 200., self.synthetic_fc)
                obs = W.end_self_forecast(token)
                self.assertIsNone(obs['inputs'])

    def test_duplicate_observation_never_selects_one(self):
        token = W.begin_self_forecast()
        own = [x['his'] for x in self.exs[-6:]]
        W.observe_self_forecast(self.exs, own, 170., self.synthetic_fc)
        W.observe_self_forecast(self.exs, own, 170., self.synthetic_fc)
        obs = W.end_self_forecast(token)
        self.assertEqual(obs['observations'], 2)
        self.assertIsNone(obs['inputs'])

    def test_nested_scopes_and_invalid_sink_are_isolated(self):
        a = W.begin_self_forecast()
        W.observe_self_forecast(self.exs, [x['his'] for x in self.exs[-6:]], 170., self.synthetic_fc)
        b = W.begin_self_forecast()
        self.assertEqual(W.end_self_forecast(b)['observations'], 0)
        self.assertEqual(W.end_self_forecast(a)['observations'], 1)
        with patch.dict(os.environ, SPARK_WORKSPACE=str(self.memory)):
            self.assertIsNotNone(self.job())
        self.assertEqual(self.packets(), [])

    def test_legacy_no_observer_is_explicitly_unavailable(self):
        original = self.ns['forecast']
        def legacy(*args, **kw):
            with patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=''):
                return original(*args, **kw)
        self.ns['forecast'] = legacy
        self.job(); packet, = self.packets()
        self.assertEqual(packet['state'], 'unavailable')
        self.assertEqual(packet['observations'], 0)
        self.assertIsNone(packet['inputs'])

    def test_observer_and_publisher_failure_do_not_change_row(self):
        with patch.object(W, 'observe_self_forecast', side_effect=ValueError('private exception')):
            one = self.job()
        self.assertEqual(self.packets()[0]['state'], 'unavailable')
        with patch.object(W, '_publish_private', side_effect=OSError('private sink failure')):
            two = self.job()
        self.assertEqual(one, two)
        self.assertEqual(len(self.packets()), 1)

    def test_forecast_failure_resets_scope_and_emits_nothing(self):
        self.ns['forecast'] = Mock(side_effect=ValueError('fixture forecast failure'))
        with self.assertRaisesRegex(ValueError, 'fixture forecast failure'): self.job()
        self.assertIsNone(W._self_forecast_scope.get())
        self.assertEqual(self.packets(), [])
        self.assertFalse(self.output.exists())

    def test_log_write_failure_emits_no_completed_packet(self):
        self.output.mkdir()
        with self.assertRaises(OSError): self.job()
        self.assertEqual(self.packets(), [])
        self.assertIsNone(W._self_forecast_scope.get())

    def test_input_snapshot_survives_later_source_mutation(self):
        token = W.begin_self_forecast()
        text = self.exs[-1]['his']
        W.observe_self_forecast(self.exs, [x['his'] for x in self.exs[-6:]], 170., self.synthetic_fc)
        self.exs[-1]['his'] = 'later mutation'
        self.exs[-1]['turn_id'] = 'later identity'
        obs = W.end_self_forecast(token)
        self.assertEqual(obs['inputs']['reply_refs'][-1]['normalized_reply_sha256'], digest(text))
        self.assertEqual(obs['inputs']['reply_refs'][-1]['observed_turn_id'], 'fixture-turn-7')

    def test_missing_readout_hook_does_not_change_forecast(self):
        del self.sh._forecast_witness
        self.assertIsNotNone(self.job())
        self.assertEqual(self.packets()[0]['state'], 'unavailable')

    def test_observation_cannot_bind_changed_or_fallback_prediction(self):
        original = self.ns['forecast']
        def changed(*args, **kw):
            out = original(*args, **kw)
            out['emb'] = [1., 0.]
            return out
        self.ns['forecast'] = changed
        self.job(); packet, = self.packets()
        self.assertEqual(packet['state'], 'unavailable')
        self.assertIsNone(packet['inputs'])

    def test_old_observer_module_preserves_forecast_and_log(self):
        with patch.dict(sys.modules, witness_capture=types.SimpleNamespace()):
            self.assertIsNotNone(self.job())
        self.assertEqual(self.packets(), [])


if __name__ == '__main__':
    unittest.main()

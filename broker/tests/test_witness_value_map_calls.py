#!/usr/bin/env python3
"""Actual value-map call wrapper with stub HTTP; private hashes only, no sends."""
import ast
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import witness_capture as W
from witness_receipts import digest


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='value-map-call-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.assertNotIn('.vintos', self.root.parts)
        self.sender = Mock(side_effect=AssertionError('external action forbidden'))
        self.body = {'model': 'fixture-served', 'choices': [{'message': {'content': '  synthetic output  '}}]}
        self.http = Mock(return_value=types.SimpleNamespace(status_code=200, json=lambda: self.body))
        # Extract only the two actual functions. The source's unrelated import-time
        # organs and existing newer f-string syntax are outside this wrapper test.
        source = (ROOT / 'scripts/value_map.py').read_text()
        segment = source[source.index('def _witness_call('):source.index('\ndef _ends(')]
        self.ns = {'os': os, 'requests': types.SimpleNamespace(post=self.http), 'MODEL': 'fixture-configured',
                   'API': 'synthetic endpoint not for receipt', 'log': Mock()}
        exec(compile(ast.parse(segment), 'actual-value-map-call', 'exec'), self.ns)
        for p in (patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=str(self.root), SPARK_WORKSPACE=str(self.root)),
                  patch.object(socket.socket, 'connect', self.sender)):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertIsInstance(self.http, Mock)
        self.assertIs(self.ns['requests'].post, self.http)

    def call(self):
        return self.ns['llm']('synthetic private system', 'synthetic private user', temperature=0.65)

    def packets(self):
        paths = list(self.root.glob('value-map-call-*.json'))
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in paths))
        self.assertFalse(list(self.root.glob('capture-*.json')))
        self.assertFalse(list(self.root.glob('.*.tmp')))
        return [json.loads(p.read_text()) for p in paths]

    def test_exact_actual_payload_and_returned_hash_without_private_text(self):
        self.assertEqual(self.call(), 'synthetic output')
        self.http.assert_called_once()
        payload = self.http.call_args.kwargs['json']
        self.assertEqual(self.http.call_args.kwargs['timeout'], 180)
        self.assertEqual(payload['temperature'], 0.65)
        self.assertEqual(payload['max_tokens'], 1500)
        packet, = self.packets()
        self.assertEqual(packet['input_sha256'], W._fingerprint(payload))
        self.assertEqual(packet['response_sha256'], W._fingerprint(self.body))
        self.assertEqual(packet['returned_sha256'], digest('synthetic output'))
        self.assertEqual(packet['configured_model'], 'fixture-configured')
        self.assertEqual(packet['served_model'], 'fixture-served')
        self.assertEqual(packet['identity_evidence'], 'response_metadata')
        self.assertEqual(packet['outcome'], 'returned')
        self.assertEqual([n['role'] for n in packet['inputs']], ['system', 'user'])
        encoded = json.dumps(packet)
        for text in ('synthetic private system', 'synthetic private user', 'synthetic output', self.ns['API']):
            self.assertNotIn(text, encoded)
        self.assertFalse(packet['upstream_complete'])
        self.assertFalse(packet['internal_attempts_complete'])
        self.assertEqual(packet['build_selection'], 'not_recorded')
        self.assertEqual(packet['stored_output_binding'], 'not_recorded')
        self.assertNotIn('turn_id', packet)

    def test_configured_model_never_fills_missing_or_malformed_response_identity(self):
        for model in (None, '', True, {}, 'x' * 257):
            self.body['model'] = model
            self.assertEqual(self.call(), 'synthetic output')
        for packet in self.packets():
            self.assertIsNone(packet['served_model'])
            self.assertEqual(packet['identity_evidence'], 'unknown')
        self.assertEqual(self.http.call_count, 5)

    def test_rejected_and_failed_calls_are_not_selected_successes(self):
        self.body = {'model': 'fixture-error-claim', 'error': {'message': 'synthetic private failure'}}
        self.assertIsNone(self.call())
        self.http.side_effect = RuntimeError('synthetic private exception')
        self.assertIsNone(self.call())
        packets = self.packets()
        self.assertEqual({p['outcome'] for p in packets}, {'rejected', 'failed'})
        self.assertTrue(all(p['returned_sha256'] is None for p in packets))
        self.assertTrue(all(p['served_model'] is None for p in packets))
        self.assertNotIn('synthetic private failure', json.dumps(packets))
        self.assertNotIn('synthetic private exception', json.dumps(packets))
        self.assertEqual(self.http.call_count, 2)

    def test_off_path_has_identical_http_payload_return_and_no_packets(self):
        with patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=''):
            out = self.call(); off = self.http.call_args
            self.assertEqual(self.packets(), [])
        self.assertEqual(self.call(), out)
        self.assertEqual(self.http.call_args, off)
        self.assertEqual(self.http.call_count, 2)

    def test_missing_old_or_failing_observers_preserve_valid_return(self):
        with patch.dict(sys.modules, witness_capture=types.SimpleNamespace()):
            self.assertEqual(self.call(), 'synthetic output')
        with patch.object(W, 'begin_value_map_call', side_effect=RuntimeError('observer')):
            self.assertEqual(self.call(), 'synthetic output')
        with patch.object(W, '_publish_private', side_effect=OSError('sink')):
            self.assertEqual(self.call(), 'synthetic output')
        self.assertEqual(self.packets(), [])
        self.assertEqual(self.http.call_count, 3)

    def test_request_snapshot_is_taken_before_http_mutates_payload(self):
        expected = {}
        def request(*args, **kwargs):
            expected['hash'] = W._fingerprint(kwargs['json'])
            kwargs['json']['messages'][0]['content'] = 'mutated after boundary'
            return types.SimpleNamespace(status_code=200, json=lambda: self.body)
        self.http.side_effect = request
        self.call()
        packet, = self.packets()
        self.assertEqual(packet['input_sha256'], expected['hash'])
        self.assertNotIn('mutated after boundary', json.dumps(packet))

    def test_each_call_has_own_identity_without_invented_build_or_fallback(self):
        self.call(); self.call()
        packets = self.packets()
        self.assertEqual(len({p['request_id'] for p in packets}), 2)
        self.assertTrue(all(p['scope'] == 'one_http_invocation' for p in packets))
        self.assertEqual(self.http.call_count, 2)

    def test_invalid_scratch_clock_and_repeated_finish_do_not_publish(self):
        with patch.dict(os.environ, SPARK_WORKSPACE='mismatch'):
            self.assertEqual(self.call(), 'synthetic output')
        with patch.object(W.time, 'time', side_effect=[100, 99]):
            self.assertEqual(self.call(), 'synthetic output')
        self.assertEqual(self.packets(), [])
        payload = self.http.call_args.kwargs['json']
        observation = W.begin_value_map_call(payload)
        self.assertTrue(W.finish_value_map_call(observation, self.body, 200, 'synthetic output', 'returned'))
        self.assertFalse(W.finish_value_map_call(observation, self.body, 200, 'synthetic output', 'returned'))
        self.assertEqual(len(self.packets()), 1)

    def test_packet_validation_fails_without_changing_call_or_unknown_fields(self):
        self.body['model'] = 'fixture-served'
        self.http.return_value = types.SimpleNamespace(json=lambda: self.body)
        self.assertEqual(self.call(), 'synthetic output')
        self.assertIsNone(self.packets()[0]['http_status'])
        payload = self.http.call_args.kwargs['json']
        with self.assertRaises(ValueError): W.begin_value_map_call(dict(payload, credentials='not allowed'))
        with self.assertRaises(ValueError): W.begin_value_map_call(dict(payload, messages=[]))
        with self.assertRaises(ValueError):
            W.finish_value_map_call(W.begin_value_map_call(payload), self.body, 200, None, 'returned')


if __name__ == '__main__':
    unittest.main(verbosity=2)

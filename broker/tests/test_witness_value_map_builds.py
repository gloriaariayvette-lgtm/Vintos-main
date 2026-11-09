#!/usr/bin/env python3
"""Actual map builder against scratch stores and stubbed HTTP; no external actions."""
from contextvars import Context
from datetime import datetime
import importlib.util
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


class FixedDate(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 2, 12, 0)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='value-map-build-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.assertNotIn('.vintos', self.root.parts)
        self.responses = ['synthetic draft a', 'synthetic draft b', 'synthetic final']
        self.sender = Mock(side_effect=AssertionError('external action forbidden'))
        def post(*args, **kwargs):
            text = self.responses.pop(0)
            body = {'model': 'fixture-served', 'choices': [{'message': {'content': text}}]} if text is not None else {'error': 'fixture rejected'}
            return types.SimpleNamespace(status_code=200, json=lambda: body)
        self.http = Mock(side_effect=post)
        self.cache = types.SimpleNamespace(unchanged=lambda *a: False, commit=Mock(), last=lambda *a: {})
        for p in (patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=str(self.root), SPARK_WORKSPACE=str(self.root)),
                  patch.object(socket.socket, 'connect', self.sender),
                  patch.dict(sys.modules, requests=types.SimpleNamespace(post=self.http), source_cache=self.cache,
                             subcon_target=types.SimpleNamespace(generative_route=lambda u,m: (u,m)),
                             subconscious_context=types.SimpleNamespace(get_subconscious_context_compact=lambda: ''))):
            p.start(); self.addCleanup(p.stop)
        spec = importlib.util.spec_from_file_location('fixture_map_builder', ROOT / 'scripts/value_map.py')
        self.vm = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.vm)
        self.vm.WORKSPACE = self.vm.MEMORY = str(self.root)
        self.vm.MAP_FILE = str(self.root / 'value-map.md')
        self.vm.API = 'synthetic endpoint'
        self.vm.MODEL = 'fixture-configured'
        self.vm.log = Mock(); self.vm.datetime = FixedDate
        self.vm.gather_full_context = lambda: 'synthetic private context'
        self.vm.get_temporal_context = lambda: 'synthetic clock'
        self.assertEqual(Path(self.vm.MAP_FILE).parent, self.root)
        self.assertIs(self.vm.requests.post, self.http)
        self.addCleanup(self.sender.assert_not_called)
        self.addCleanup(lambda: self.assertIsNone(W._value_map_stage.get()))

    def packets(self, kind):
        paths = list(self.root.glob('value-map-' + kind + '-*.json'))
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in paths))
        return [json.loads(p.read_text()) for p in paths]

    def test_synthesis_binds_named_drafts_selected_call_and_exact_entry(self):
        self.vm.build_map()
        self.assertEqual(self.http.call_count, 3)
        build, = self.packets('build')
        calls = {p['stage']: p for p in self.packets('call')}
        self.assertEqual(set(calls), {'draft_a', 'draft_b', 'synthesis'})
        self.assertTrue(all(p['build_id'] == build['build_id'] for p in calls.values()))
        self.assertEqual(build['selection']['request_id'], calls['synthesis']['request_id'])
        self.assertEqual(build['selection']['state'], 'bound')
        self.assertEqual(calls['synthesis']['dependencies'], [
            {'stage': stage, 'returned_sha256': calls[stage]['returned_sha256'],
             'request_id': calls[stage]['request_id'], 'state': 'bound'} for stage in ['draft_a','draft_b']])
        entry = Path(self.vm.MAP_FILE).read_text()
        self.assertEqual(build['write']['entry_sha256'], digest(entry))
        self.assertEqual(build['write']['stripped_entry_sha256'], digest(entry.strip()))
        self.assertEqual(build['write']['mode'], 'replace')
        self.assertEqual(build['write']['durability'], 'unconfirmed')
        self.assertEqual(build['write']['whole_file'], 'unverified')
        self.assertFalse(build['attempt_coverage_complete'])
        for text in (entry, 'synthetic private context', 'synthetic final', self.vm.MAP_FILE):
            self.assertNotIn(text, json.dumps(build))
        self.cache.commit.assert_called_once_with('value-map', 'synthetic private context')

    def test_only_surviving_draft_is_explicitly_selected(self):
        for outputs, stage in [(['surviving draft', None], 'draft_a'), ([None, 'surviving draft'], 'draft_b')]:
            self.responses = outputs
            before = {p['build_id'] for p in self.packets('build')}
            count = self.http.call_count
            self.vm.build_map()
            build, = [p for p in self.packets('build') if p['build_id'] not in before]
            self.assertEqual(self.http.call_count - count, 2)
            self.assertEqual(build['selection']['stage'], stage)
            self.assertEqual(build['selection']['state'], 'bound')

    def test_identical_draft_text_keeps_two_explicit_call_dependencies(self):
        self.responses = ['same synthetic draft', 'same synthetic draft', 'final']
        self.vm.build_map()
        synthesis = next(p for p in self.packets('call') if p['stage'] == 'synthesis')
        self.assertEqual(len({d['request_id'] for d in synthesis['dependencies']}), 2)
        self.assertTrue(all(d['state'] == 'bound' for d in synthesis['dependencies']))

    def test_append_receipt_is_only_new_entry_not_entire_file(self):
        self.vm.build_map()
        first = Path(self.vm.MAP_FILE).read_text()
        self.responses = ['another a', 'another b', 'another final']
        self.vm.build_map()
        second = next(p for p in self.packets('build') if p['write']['mode'] == 'append')
        whole = Path(self.vm.MAP_FILE).read_text()
        self.assertTrue(whole.startswith(first))
        self.assertEqual(second['write']['entry_sha256'], digest(whole[len(first):]))
        self.assertNotEqual(second['write']['entry_sha256'], digest(whole))

    def test_rejected_failed_or_discarded_result_never_claims_written_entry(self):
        for responses in ([None, None], ['a', 'b', 'let me know if synthetic review']):
            self.responses = list(responses)
            self.vm.build_map()
        self.assertEqual(self.packets('build'), [])
        self.assertFalse(Path(self.vm.MAP_FILE).exists())
        self.assertEqual(self.http.call_count, 5)

    def test_write_failure_does_not_emit_completed_entry(self):
        self.vm.MAP_FILE = str(self.root)
        with self.assertRaises(OSError): self.vm.build_map()
        self.assertEqual(self.packets('build'), [])
        self.assertEqual(len(self.packets('call')), 3)
        self.cache.commit.assert_not_called()

    def test_missing_call_receipts_leave_selection_unavailable_without_muting_output(self):
        original = W._publish_private
        def publish(root, packet, prefix):
            if prefix == 'value-map-call-': raise OSError('synthetic sink failure')
            return original(root, packet, prefix)
        with patch.object(W, '_publish_private', side_effect=publish): self.vm.build_map()
        build, = self.packets('build')
        self.assertEqual(build['selection']['state'], 'unavailable')
        self.assertIsNone(build['selection']['request_id'])
        self.assertTrue(all(not c['packet_published'] for c in build['calls']))
        self.assertIn('synthetic final', Path(self.vm.MAP_FILE).read_text())

    def test_off_and_old_observer_preserve_entry_and_call_count(self):
        self.vm.build_map()
        expected = Path(self.vm.MAP_FILE).read_text()
        for mode in ('off','old'):
            Path(self.vm.MAP_FILE).unlink()
            self.responses = ['synthetic draft a', 'synthetic draft b', 'synthetic final']
            before = len(self.packets('build')); count = self.http.call_count
            p = patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH='') if mode == 'off' else patch.dict(sys.modules, witness_capture=types.SimpleNamespace())
            with p: self.vm.build_map()
            self.assertEqual(Path(self.vm.MAP_FILE).read_text(), expected)
            self.assertEqual(self.http.call_count-count, 3)
            self.assertEqual(len(self.packets('build')), before)

    def manual_call(self, build, stage='draft_a', text='synthetic result'):
        token = W.enter_value_map_stage(build, stage)
        try:
            call = W.begin_value_map_call({'model':'fixture', 'messages':[{'role':'system','content':'s'}, {'role':'user','content':'u'}], 'temperature':0.5, 'max_tokens':5})
            W.finish_value_map_call(call, {'model':'fixture'}, 200, text, 'returned')
            return call
        finally:
            W.leave_value_map_stage(token)

    def finish(self, build, result='synthetic result'):
        return W.finish_value_map_build(build, 'draft_a', result, '\n## 2026-01-02 12:00 — Value Map\n\n'+result+'\n\n---\n', 'w')

    def test_duplicate_stage_or_changed_result_never_selects_by_similarity(self):
        a = W.begin_value_map_build()
        self.manual_call(a); self.manual_call(a)
        self.finish(a)
        b = W.begin_value_map_build(); self.manual_call(b)
        self.finish(b, 'changed synthetic result')
        self.assertTrue(all(p['selection']['state'] == 'unavailable' for p in self.packets('build')))

    def test_interleaved_contexts_and_disabled_nested_stage_do_not_cross_bind(self):
        a,b = Context(), Context()
        ba,bb = a.run(W.begin_value_map_build), b.run(W.begin_value_map_build)
        ca,cb = a.run(self.manual_call,ba), b.run(self.manual_call,bb)
        self.assertNotEqual(ca['packet']['build_id'], cb['packet']['build_id'])
        token = W.enter_value_map_stage(ba,'draft_b')
        masked = W.enter_value_map_stage(None,'draft_a')
        self.assertIsNone(W._value_map_stage.get())
        W.leave_value_map_stage(masked)
        self.assertIs(W._value_map_stage.get()[0],ba)
        W.leave_value_map_stage(token)

    def test_limits_clocks_and_once_only_write(self):
        build = W.begin_value_map_build()
        for _ in range(9): self.manual_call(build)
        self.finish(build)
        packet, = self.packets('build')
        self.assertTrue(packet['calls_truncated'])
        self.assertEqual(len(packet['calls']),8)
        self.assertEqual(packet['selection']['state'],'unavailable')
        self.assertFalse(self.finish(build))
        other = W.begin_value_map_build(); self.manual_call(other)
        with patch.object(W.time,'time',return_value=0):
            with self.assertRaises(ValueError): self.finish(other)
        self.assertEqual(len(self.packets('build')),1)


if __name__ == '__main__':
    unittest.main(verbosity=2)

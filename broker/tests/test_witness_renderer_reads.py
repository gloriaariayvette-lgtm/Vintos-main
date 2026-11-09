#!/usr/bin/env python3
"""Synthetic guarded reads under real read-only selection; no external actions."""
from contextvars import Context
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
import context_selection as C
import inner_context as I
import store_guard as S
import witness_capture as W
from witness_receipts import digest, lineage_status


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='renderer-reads-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.assertNotIn('.vintos', self.root.parts)
        self.path = self.root / 'synthetic.json'
        self.raw = '{"text": "private synthetic source", "may_witness": true}'
        self.path.write_text(self.raw)
        self.sender = Mock(side_effect=AssertionError('external action forbidden'))
        self.saver = Mock()
        self.renderer = Mock(side_effect=lambda: S.load_json(self.path, {})['text'])
        patches = [patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=str(self.root), SPARK_WORKSPACE=str(self.root)),
                   patch.object(socket.socket, 'connect', self.sender),
                   patch.object(S, 'MEMORY', str(self.root)), patch.object(S, 'LOG', str(self.root / 'quarantine.jsonl')),
                   patch.object(S, 'save_json', self.saver),
                   patch.object(I, 'import_module', return_value=types.SimpleNamespace(block=self.renderer)),
                   patch.object(I, '_MISSING', [('fixture_reader', 'block')]),
                   patch.object(I, '_guard_note', return_value=''), patch.object(I.time, 'time', return_value=99)]
        for p in patches:
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.addCleanup(lambda: self.assertIsNone(C._reads.get()))
        self.assertIsInstance(self.saver, Mock)
        self.assertEqual(Path(S.LOG).parent, self.root)

    def packet(self, text):
        capture = W.begin_shadow('fixture-turn', 'fixture-chat', 100)
        capture.request(text, [], {}, False, 101)
        return capture.finalize('fixture final', 110)

    def test_read_version_bound_through_actual_renderer_without_reopening(self):
        text = I.missing_inner_block()
        self.path.write_text('{"text":"new version"}')
        packet = self.packet(text)
        read = next(n for n in packet['lineage'] if n.get('observation') == 'guarded_json_read')
        fragment = next(n for n in packet['lineage'] if n.get('organ') == 'fixture_reader')
        self.assertEqual(read['decoded_sha256'], digest(self.raw))
        self.assertEqual(read['resource_sha256'], digest(str(self.path)))
        self.assertEqual(read['clock_basis'], 'selection_completed')
        self.assertEqual(fragment['parents'], [read['id']])
        self.assertEqual(fragment['read_observation'], 'partial')
        self.assertEqual(fragment['read_coverage'], 'guarded_json_only')
        nodes = {n['id']: n for n in packet['lineage']}
        self.assertEqual(lineage_status(fragment['id'], nodes, 110), 'unknown')
        self.assertFalse(read['complete'])
        encoded = json.dumps(packet)
        for private in (self.raw, str(self.path), text):
            self.assertNotIn(private, encoded)
        self.assertEqual(self.renderer.call_count, 1)
        self.assertNotIn('reads', self.saver.call_args.args[1])

    def test_missing_empty_unreadable_and_invalid_stay_distinct(self):
        empty = self.root / 'empty.json'; empty.write_text('  ')
        invalid = self.root / 'invalid.json'; invalid.write_text('{bad')
        def render():
            for p in (self.root / 'missing.json', empty, self.root, invalid):
                self.assertEqual(S.load_json(p, 'default'), 'default')
            return 'fixture result'
        self.renderer.side_effect = render
        packet = self.packet(I.missing_inner_block())
        reads = [n for n in packet['lineage'] if n.get('observation') == 'guarded_json_read']
        self.assertEqual([r['state'] for r in reads], ['missing', 'empty', 'unreadable', 'invalid'])
        self.assertNotIn('decoded_sha256', reads[0])
        self.assertEqual(reads[1]['decoded_sha256'], digest('  '))
        self.assertEqual(reads[3]['decoded_sha256'], digest('{bad'))
        self.assertFalse((self.root / 'quarantine.jsonl').exists())
        self.assertEqual(list(self.root.glob('*.corrupt-*')), [])

    def test_guard_still_refuses_write_and_cleans_failed_renderer_scope(self):
        def render():
            S.load_json(self.path, {})
            (self.root / 'forbidden').write_text('never')
        self.renderer.side_effect = render
        self.assertEqual(I.missing_inner_block(), '')
        self.assertEqual(I.current_selection()['offers']['fixture_reader']['state'], 'organ_error')
        self.assertFalse((self.root / 'forbidden').exists())
        self.assertIsNone(C._reads.get())
        self.renderer.side_effect = lambda: 'recovered'
        packet = self.packet(I.missing_inner_block())
        self.assertFalse(any(n.get('observation') == 'guarded_json_read' for n in packet['lineage']))

    def test_old_or_failed_observer_does_not_change_output(self):
        original = I.missing_inner_block()
        with patch.object(C, 'observe_reads', side_effect=RuntimeError('fixture error')):
            self.assertEqual(I.missing_inner_block(), original)
        with patch.dict(sys.modules, context_selection=types.SimpleNamespace(readonly=C.readonly)):
            self.assertEqual(I.missing_inner_block(), original)
        with patch.object(C, 'observe_store_read', side_effect=RuntimeError('fixture error')):
            self.assertEqual(I.missing_inner_block(), original)
        self.assertIsNone(C._reads.get())

    def test_disabled_capture_preserves_output_without_collecting(self):
        enabled = I.missing_inner_block()
        with patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=''), patch.object(C, 'observe_reads') as observer:
            self.assertEqual(I.missing_inner_block(), enabled)
            observer.assert_not_called()
            self.assertIsNone(I.current_rendered_selection())

    def test_existing_compact_causal_renderer_reads_its_scratch_store(self):
        import causal_self_model as causal
        import subconscious_context as subconscious
        payload = {'entries': [{'trigger': 'synthetic cue', 'tendency': 'synthetic response', 'confidence': 0.7}]}
        self.path.write_text(json.dumps(payload))
        compact = subconscious.get_subconscious_context_compact
        with patch.object(causal, 'MODEL_FILE', str(self.path)), \
             patch.object(subconscious, 'get_subconscious_context_compact', side_effect=lambda: compact(['causal'])), \
             patch.dict(sys.modules, conversation_pressure=types.SimpleNamespace(get_pressure_block=lambda: '')), \
             patch.object(I, '_FULL', []), patch.object(I, '_atelier_door_line', return_value=''):
            text = I.full_inner_block()
        self.assertIn('synthetic cue', text)
        packet = self.packet(text)
        reads = [n for n in packet['lineage'] if n.get('observation') == 'guarded_json_read']
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0]['decoded_sha256'], digest(json.dumps(payload)))
        fragment = next(n for n in packet['lineage'] if n.get('organ') == 'subconscious_context')
        self.assertEqual(fragment['parents'], [reads[0]['id']])

    def test_direct_reads_are_explicitly_outside_guarded_coverage(self):
        self.renderer.side_effect = lambda: json.loads(self.path.read_text())['text']
        packet = self.packet(I.missing_inner_block())
        fragment = next(n for n in packet['lineage'] if n.get('organ') == 'fixture_reader')
        self.assertEqual(fragment['parents'], [])
        self.assertEqual(fragment['read_coverage'], 'guarded_json_only')
        self.assertEqual(fragment['read_observation'], 'partial')
        self.assertFalse(fragment['complete'])

    def test_repeated_renderer_name_cannot_rebind_first_fragment_to_later_read(self):
        second = self.root / 'second.json'; second.write_text('{"text":"second fragment"}')
        calls = iter([self.path, second])
        self.renderer.side_effect = lambda: S.load_json(next(calls), {})['text']
        with patch.object(I, '_MISSING', [('fixture_reader', 'block')] * 2):
            packet = self.packet(I.missing_inner_block())
        reads = [n for n in packet['lineage'] if n.get('observation') == 'guarded_json_read']
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0]['decoded_sha256'], digest(self.raw))
        # A first read with no rendered output must not supply a later fragment's parents.
        calls = iter([self.path, second])
        def render():
            p = next(calls)
            value = S.load_json(p, {})['text']
            return '' if p == self.path else value
        self.renderer.side_effect = render
        with patch.object(I, '_MISSING', [('fixture_reader', 'block')] * 2):
            packet = self.packet(I.missing_inner_block())
        reads = [n for n in packet['lineage'] if n.get('observation') == 'guarded_json_read']
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0]['decoded_sha256'], digest(second.read_text()))

    def test_snapshots_and_interleaved_contexts_are_independent(self):
        a, b = Context(), Context()
        text_a = a.run(I.missing_inner_block)
        self.path.write_text('{"text":"second synthetic source"}')
        text_b = b.run(I.missing_inner_block)
        returned = a.run(I.current_rendered_selection)
        returned['reads']['fixture_reader']['reads'][0]['decoded_sha256'] = '0' * 64
        pa, pb = a.run(self.packet, text_a), b.run(self.packet, text_b)
        def version(p):
            return next(n['decoded_sha256'] for n in p['lineage'] if n.get('observation') == 'guarded_json_read')
        self.assertEqual(version(pa), digest(self.raw))
        self.assertNotEqual(version(pa), version(pb))

    def test_nested_observers_and_limits_preserve_read_order(self):
        with C.observe_reads() as outer:
            S.load_json(self.path, {})
            with C.observe_reads() as inner:
                S.load_json(self.root / 'missing', {})
                self.assertEqual(len(inner()['reads']), 1)
            self.assertEqual([r['state'] for r in outer()['reads']], ['loaded', 'missing'])
            for _ in range(64): S.load_json(self.path, {})
            self.assertEqual(len(outer()['reads']), 64)
            self.assertTrue(outer()['truncated'])
        with C.observe_reads() as observed:
            C.observe_store_read(self.path, 'loaded', 'x' * 4194305)
            self.assertEqual(observed()['reads'][0]['version_state'], 'over_limit')
            self.assertNotIn('decoded_sha256', observed()['reads'][0])
        with C.observe_reads() as observed:
            C.observe_store_read(self.path, 'loaded', 'x' * 4194304)
            with C.observe_reads():
                C.observe_store_read(self.path, 'loaded', 'y')
            self.assertIn('decoded_sha256', observed()['reads'][0])
            self.assertEqual(observed()['reads'][1]['version_state'], 'over_limit')

    def test_malformed_optional_read_receipts_never_pollute_or_remove_fragment(self):
        text = I.missing_inner_block()
        good = I.current_rendered_selection()
        record = good['reads']['fixture_reader']['reads'][0]
        for bad in (dict(record, path='private path'), dict(record, decoded_sha256='invalid'),
                    dict(record, state='missing'), dict(record, version_state='over_limit')):
            import copy
            changed = copy.deepcopy(good)
            changed['reads']['fixture_reader']['reads'] = [bad]
            with patch.object(I, 'current_rendered_selection', return_value=changed):
                p = self.packet(text)
            fragment = next(n for n in p['lineage'] if n.get('organ') == 'fixture_reader')
            self.assertEqual(fragment['read_observation'], 'unavailable')
            self.assertEqual(p['requests'][0]['rendered_fragments'][0]['state'], 'matched')
            self.assertFalse(fragment['parents'])
            self.assertNotIn('private path', json.dumps(p))

    def test_assembly_and_consumer_limits_are_independently_bounded(self):
        def render():
            for _ in range(64): S.load_json(self.path, {})
            return 'synthetic result'
        self.renderer.side_effect = render
        with patch.object(I, '_MISSING', [('fixture_%d' % i, 'block') for i in range(5)]):
            text = I.missing_inner_block()
        manifest = I.current_rendered_selection()
        self.assertEqual(sum(len(r['reads']) for r in manifest['reads'].values()), 256)
        # Even an oversized producer cannot exceed the capture-wide bound.
        manifest['reads']['fixture_4'] = manifest['reads']['fixture_0']
        with patch.object(I, 'current_rendered_selection', return_value=manifest):
            packet = self.packet(text)
        self.assertEqual(sum(n.get('observation') == 'guarded_json_read' for n in packet['lineage']), 256)
        self.assertEqual(sum(n.get('read_observation') == 'unavailable' for n in packet['lineage']), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)

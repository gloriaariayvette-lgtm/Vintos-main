#!/usr/bin/env python3
"""Synthetic renderers only: no live stores, network, providers or notifications."""
from contextlib import nullcontext
from contextvars import Context
import json
import importlib.util
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
import inner_context as I
import witness_capture as W
from witness_receipts import digest, lineage_status
SPEC = importlib.util.spec_from_file_location('rendered_replay', ROOT / 'experiments/judges-witness/replay.py')
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rendered-witness-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.assertNotIn('.vintos', self.root.parts)
        self.sender = Mock(side_effect=AssertionError('external action forbidden'))
        self.saver = Mock()
        self.render = Mock(return_value='[SYNTHETIC] αβ fragment.')
        patches = [patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=str(self.root), SPARK_WORKSPACE=str(self.root)),
                   patch.object(socket.socket, 'connect', self.sender),
                   patch.dict(sys.modules, {'store_guard': types.SimpleNamespace(save_json=self.saver),
                       'context_selection': types.SimpleNamespace(readonly=nullcontext)}),
                   patch.object(I, 'import_module', return_value=types.SimpleNamespace(block=self.render)),
                   patch.object(I, '_MISSING', [('fixture_organ', 'block')]),
                   patch.object(I, '_guard_note', return_value=''),
                   patch.object(I.time, 'time', return_value=99)]
        for p in patches:
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertIsInstance(self.saver, Mock)

    def capture(self, system=None):
        rendered = I.missing_inner_block()
        c = W.begin_shadow('fixture-turn', 'fixture-chat', 100)
        invocation = c.request(rendered if system is None else system, [], {}, False, 101)
        invocation.observe({'status': 'valid', 'text': 'synthetic raw', 'observed_model': 'fixture',
                            'identity_evidence': 'runtime_receipt'})
        c.select('synthetic raw', request=invocation)
        return c, rendered

    def test_real_assembly_hook_binds_span_but_never_clean_ancestry(self):
        c, rendered = self.capture()
        packet = c.finalize('synthetic final', 110)
        obs = packet['requests'][0]['rendered_fragments'][0]
        self.assertEqual(obs['state'], 'matched')
        self.assertEqual(rendered[obs['span']['start']:obs['span']['end']], rendered)
        self.assertEqual(obs['rendered_sha256'], digest(rendered))
        nodes = {n['id']: n for n in packet['lineage']}
        system_node = next(n for n in packet['lineage'] if n.get('slot') == 0)
        self.assertIn(obs['source_id'], system_node['parents'])
        self.assertEqual(system_node['rendered_bindings'][0], obs)
        self.assertFalse(nodes[obs['source_id']]['complete'])
        self.assertEqual(lineage_status(c.context_id, nodes, 110), 'unknown')
        self.assertEqual(packet['witness_receipt']['delivery'], 'unknown')
        self.assertEqual(c._rendered_fragments, [])
        self.assertNotIn(rendered, json.dumps(packet, ensure_ascii=False))
        self.assertNotIn(rendered, str(self.saver.call_args_list))
        self.assertEqual(self.render.call_count, 1)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_persisted_fragment_packet_remains_unqualified_in_replay(self):
        c, rendered = self.capture()
        self.assertTrue(W.finish_shadow(c, 'synthetic final', 110,
            {'turn_id': 'fixture-turn', 'output_provenance': 'ordinary_generation', 'may_witness': True}))
        paths = list(self.root.glob('capture-*.json'))
        self.assertEqual(len(paths), 1)
        packet = json.loads(paths[0].read_text())
        self.assertNotIn(rendered, json.dumps(packet, ensure_ascii=False))
        self.assertEqual(paths[0].stat().st_mode & 0o777, 0o600)
        sources = [('capture', [packet])]
        nodes = R.snapshot_nodes(sources, [])
        report, admitted = R.census(sources, nodes, 1000)
        self.assertEqual(admitted, [])
        self.assertEqual(report['held'], {'unconfirmed_delivery': 1})
        packet['witness_receipt']['delivery'] = 'delivered'  # Invented synthetic control only.
        report, admitted = R.census(sources, nodes, 1000)
        self.assertEqual(admitted, [])
        self.assertEqual(report['held'], {'unknown_lineage': 1})

    def test_each_retry_checks_exact_current_system_and_not_history(self):
        rendered = I.missing_inner_block()
        c = W.begin_shadow('fixture-turn', 'fixture-chat', 100)
        c.request('prefix ' + rendered, [], {}, False, 101)
        c.request('changed system', [{'role': 'assistant', 'content': rendered}], {}, False, 102)
        c.request(rendered + rendered, [], {}, False, 103)
        p = c.finalize('final', 110)
        self.assertEqual([r['rendered_fragments'][0]['state'] for r in p['requests']],
                         ['matched', 'not_found', 'ambiguous'])
        self.assertEqual(p['requests'][0]['rendered_fragments'][0]['span']['start'], 7)
        self.assertFalse(any(n.get('rendered_bindings') for n in p['lineage']
                             if n.get('id', '').startswith(c.context_id + ':request-2:')))

    def test_identical_material_from_two_organs_cannot_pick_an_origin(self):
        with patch.object(I, '_MISSING', [('fixture_a', 'block'), ('fixture_b', 'block')]):
            I.missing_inner_block()
        c = W.begin_shadow('fixture-turn', 'fixture-chat', 100)
        c.request(self.render.return_value, [], {}, False, 101)
        p = c.finalize('final', 110)
        self.assertEqual([o['state'] for o in p['requests'][0]['rendered_fragments']], ['ambiguous', 'ambiguous'])
        self.assertFalse(next(n for n in p['lineage'] if n.get('slot') == 0)['rendered_bindings'])

    def test_capture_snapshot_survives_later_assembly_and_returned_copy_mutation(self):
        rendered = I.missing_inner_block()
        c = W.begin_shadow('fixture-turn', 'fixture-chat', 100)
        returned = I.current_rendered_selection()
        returned['fragments']['fixture_organ'] = 'mutated copy'
        self.render.return_value = 'later selection'
        I.missing_inner_block()
        c.request(rendered, [], {}, False, 101)
        self.assertEqual(c.finalize('final', 110)['requests'][0]['rendered_fragments'][0]['state'], 'matched')

    def test_interleaved_contexts_keep_separate_selections(self):
        a, b = Context(), Context()
        first = a.run(I.missing_inner_block)
        self.render.return_value = 'second synthetic fragment'
        second = b.run(I.missing_inner_block)
        ca = a.run(W.begin_shadow, 'turn-a', 'fixture-chat', 100)
        cb = b.run(W.begin_shadow, 'turn-b', 'fixture-chat', 100)
        ca.request(first, [], {}, False, 101)
        cb.request(second, [], {}, False, 101)
        pa, pb = ca.finalize('a', 110), cb.finalize('b', 110)
        oa, ob = pa['requests'][0]['rendered_fragments'][0], pb['requests'][0]['rendered_fragments'][0]
        self.assertEqual((oa['state'], ob['state']), ('matched', 'matched'))
        self.assertNotEqual(oa['rendered_sha256'], ob['rendered_sha256'])

    def test_off_path_output_and_persisted_offer_shapes_unchanged(self):
        on = I.missing_inner_block()
        on_keys = set(self.saver.call_args.args[1])
        with patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=''):
            off = I.missing_inner_block()
            self.assertIsNone(I.current_rendered_selection())
        self.assertEqual(on, off)
        self.assertEqual(set(self.saver.call_args.args[1]), on_keys)
        self.assertNotIn('fragments', on_keys)
        self.assertEqual(self.render.call_count, 2)

    def test_missing_and_raising_old_producer_api_do_not_break_capture(self):
        I.missing_inner_block()
        selection = I.current_selection()
        for producer in (types.SimpleNamespace(current_selection=lambda: selection),
                         types.SimpleNamespace(current_selection=lambda: selection,
                            current_rendered_selection=Mock(side_effect=RuntimeError('synthetic failure')))):
            with patch.dict(sys.modules, inner_context=producer):
                c = W.begin_shadow('fixture-turn', 'fixture-chat', 100)
                c.request('system', [], {}, False, 101)
                self.assertEqual(c.finalize('final', 110)['requests'][0]['rendered_fragments'], [])

    def test_identity_clock_offer_and_size_mismatch_never_bind(self):
        I.missing_inner_block()
        good = I.current_rendered_selection()
        for change in ({'selection_id': 'other'}, {'ts': 98}, {'fragments': {'not_offered': 'text'}},
                       {'fragments': {'fixture_organ': 'x' * 262145}}, {'fragments': {'fixture_organ': None}}):
            with patch.object(I, 'current_rendered_selection', return_value=dict(good, **change)):
                c = W.begin_shadow('fixture-turn', 'fixture-chat', 100)
                c.request('system', [], {}, False, 101)
                self.assertEqual(c.finalize('final', 110)['requests'][0]['rendered_fragments'], [])

    def test_renderer_error_and_capacity_do_not_change_output_or_keep_stale_text(self):
        I.missing_inner_block()
        self.render.side_effect = RuntimeError('synthetic renderer error')
        self.assertEqual(I.missing_inner_block(), '')
        self.assertEqual(I.current_rendered_selection()['fragments'], {})
        self.render.side_effect = None
        self.render.return_value = 'x' * 262145
        self.assertEqual(len(I.missing_inner_block()), 262145)
        self.assertEqual(I.current_rendered_selection()['fragments'], {})
        I._begin_rendered_selection()
        for i in range(65):
            I._remember_rendered('fixture_%d' % i, 'synthetic')
        self.assertEqual(len(I.current_rendered_selection()['fragments']), 64)

    def test_full_assembly_special_renderers_join_same_selection(self):
        with patch.dict(sys.modules, subconscious_context=types.SimpleNamespace(get_subconscious_context_compact=lambda: 'inner'),
                        conversation_pressure=types.SimpleNamespace(get_pressure_block=lambda: 'pressure')), \
             patch.object(I, '_FULL', []), patch.object(I, '_atelier_door_line', return_value=''):
            text = I.full_inner_block()
        c = W.begin_shadow('fixture-turn', 'fixture-chat', 100)
        c.request(text, [], {}, False, 101)
        observations = c.finalize('final', 110)['requests'][0]['rendered_fragments']
        self.assertEqual(len(observations), 2)
        self.assertTrue(all(o['state'] == 'matched' for o in observations))


if __name__ == '__main__':
    unittest.main(verbosity=2)

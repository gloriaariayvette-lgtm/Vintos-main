#!/usr/bin/env python3
"""Execute only actual value-map read/binding segments with synthetic scratch data."""
import ast
import copy
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
from witness_receipts import digest, lineage_status


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((ROOT / 'bin/server.py').read_text())
        handler = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'avatar_chat')
        outer = next(n for n in handler.body if isinstance(n, ast.Try) and any(
            isinstance(c, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'value_map_ctx' for t in c.targets)
            for c in n.body))
        start = next(i for i, n in enumerate(outer.body) if isinstance(n, ast.Assign)
                     and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'value_map_ctx')
        block = next(n for n in outer.body if isinstance(n, ast.Assign)
                     and isinstance(n.targets[0], ast.Name) and n.targets[0].id == '_value_map_block')
        bind = next(n for n in outer.body if isinstance(n, ast.Try) and any(
            isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == 'bind_value_map'
            for c in ast.walk(n)))
        cls.read_code = compile(ast.fix_missing_locations(ast.Module(body=copy.deepcopy(outer.body[start:start+3] + [block]),
                                    type_ignores=[])), 'actual-value-map-read', 'exec')
        cls.bind_code = compile(ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(bind)], type_ignores=[])),
                                'actual-value-map-binding', 'exec')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='value-map-binding-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.assertNotIn('.vintos', self.root.parts)
        self.path = self.root / 'value-map.md'
        self.raw = '## 2026-01-01 08:00\nOld synthetic entry\n\n## 2026-01-01 12:00\n' + 'α new entry. ' * 200
        self.path.write_text(self.raw)
        self.sender = Mock(side_effect=AssertionError('external action forbidden'))
        for p in (patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=str(self.root), SPARK_WORKSPACE=str(self.root)),
                  patch.object(socket.socket, 'connect', self.sender)):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.ns = {'os': os, 'MEMORY': str(self.root), 'time': types.SimpleNamespace(time=lambda: 99)}

    def read(self):
        exec(self.read_code, self.ns)
        self.assertNotIn('_value_map_decoded', self.ns)
        return self.ns['_value_map_block']

    def capture(self):
        c = W.Capture('fixture-turn', 'fixture-chat', 100)
        self.ns['_witness_capture'] = c
        exec(self.bind_code, self.ns)
        return c

    def test_actual_read_then_binding_records_version_transform_and_request(self):
        block = self.read()
        self.assertEqual(len(self.ns['value_map_ctx']), 1500)
        c = self.capture()
        invocation = c.request('prefix\n' + block, [], {}, False, 101)
        invocation.observe({'status': 'valid', 'text': 'synthetic raw', 'observed_model': 'fixture',
                            'identity_evidence': 'runtime_receipt'})
        c.select('synthetic raw', request=invocation)
        p = c.finalize('synthetic final', 110)
        observation = p['requests'][0]['rendered_fragments'][0]
        self.assertEqual(observation['state'], 'matched')
        self.assertEqual(observation['span']['start'], 7)
        nodes = {n['id']: n for n in p['lineage']}
        fragment = nodes[observation['source_id']]
        source = nodes[fragment['parents'][0]]
        self.assertEqual(fragment['kind'], 'value_map')
        self.assertEqual(source['decoded_sha256'], digest(self.raw))
        self.assertEqual(source['clock_basis'], 'read_completed')
        self.assertEqual(lineage_status(fragment['id'], nodes, 110), 'unknown')
        for value in (self.raw, block, str(self.path)):
            self.assertNotIn(value, json.dumps(p, ensure_ascii=False))
        self.assertEqual(p['witness_receipt']['delivery'], 'unknown')

    def test_edited_retry_history_move_and_duplicate_do_not_inherit_binding(self):
        block = self.read(); c = self.capture()
        for system, history in [(block, []), ('changed ' + block[:-5], []),
                                ('no block', [{'role': 'assistant', 'content': block}]), (block + block, [])]:
            c.request(system, history, {}, False, 101)
        states = [r['rendered_fragments'][0]['state'] for r in c.finalize('final', 110)['requests']]
        self.assertEqual(states, ['matched', 'not_found', 'not_found', 'ambiguous'])

    def test_same_selected_entry_does_not_erase_changed_source_version(self):
        self.read(); first = dict(self.ns['_value_map_observation'])
        self.path.write_text(self.raw.replace('Old synthetic entry', 'Different earlier entry'))
        self.read(); second = self.ns['_value_map_observation']
        self.assertEqual(first['selected_sha256'], second['selected_sha256'])
        self.assertNotEqual(first['decoded_sha256'], second['decoded_sha256'])
        self.path.unlink()
        self.assertEqual(self.read(), '')
        self.assertIsNone(self.ns['_value_map_observation'])
        self.assertEqual(self.capture()._nodes, [])

    def test_off_or_missing_old_observer_preserves_exact_block(self):
        block = self.read()
        with patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=''), patch.object(W, 'value_map_read') as observer:
            self.assertEqual(self.read(), block)
            observer.assert_not_called()
            self.assertIsNone(self.ns['_value_map_observation'])
        for module in (types.SimpleNamespace(), types.SimpleNamespace(value_map_read=Mock(side_effect=RuntimeError('fixture')))):
            with patch.dict(sys.modules, witness_capture=module):
                self.assertEqual(self.read(), block)
                self.assertIsNone(self.ns['_value_map_observation'])
        self.read()
        old = types.SimpleNamespace()
        self.ns['_witness_capture'] = old
        exec(self.bind_code, self.ns)
        self.assertIs(self.ns['_witness_capture'], old)

    def test_noncanonical_selection_invalid_root_and_size_never_observe(self):
        block = self.read()
        self.assertIsNone(W.value_map_read(self.raw, 'unrelated selected text', 99))
        self.assertIsNone(W.value_map_read('x' * 4194305, 'x' * 1500, 99))
        with patch.dict(os.environ, SPARK_WORKSPACE='mismatch'):
            self.assertEqual(self.read(), block)
            self.assertIsNone(self.ns['_value_map_observation'])
        with self.assertRaises(ValueError): W.value_map_read(self.raw, self.ns['value_map_ctx'], True)

    def test_bad_metadata_or_fragment_does_not_add_partial_nodes(self):
        block = self.read(); good = self.ns['_value_map_observation']
        for change in ({'at': 101}, {'decoded_sha256': 'bad'}, {'selected_sha256': '0' * 64},
                       {'path': 'unwanted private field'}, {'transform': 'guessed'}):
            c = W.Capture('fixture-turn', 'fixture-chat', 100)
            self.assertFalse(c.bind_value_map(dict(good, **change), block))
            self.assertEqual(c._nodes, [])
        for changed in (block + 'edit', 'wrong prefix\n' + self.ns['value_map_ctx'], ''):
            self.assertFalse(W.Capture('fixture-turn', 'fixture-chat', 100).bind_value_map(good, changed))

    def test_once_before_routing_and_capture_snapshot_survives_later_reads(self):
        block = self.read(); c = self.capture()
        with self.assertRaises(ValueError): c.bind_value_map(self.ns['_value_map_observation'], block)
        self.path.write_text('new synthetic map')
        self.read()
        c.request(block, [], {}, False, 101)
        with self.assertRaises(ValueError): c.bind_value_map(self.ns['_value_map_observation'], block)
        p = c.finalize('final', 110)
        read = next(n for n in p['lineage'] if n.get('observation') == 'value_map_read')
        self.assertEqual(read['decoded_sha256'], digest(self.raw))
        self.assertEqual(p['requests'][0]['rendered_fragments'][0]['state'], 'matched')


if __name__ == '__main__':
    unittest.main(verbosity=2)

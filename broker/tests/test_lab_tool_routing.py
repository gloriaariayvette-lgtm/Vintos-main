#!/usr/bin/env python3
"""Lab call boundaries: scratch stores and no external action."""
import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import urllib.request

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
TEMP = tempfile.TemporaryDirectory(prefix='lab-tools-routing-')
SCRATCH = Path(TEMP.name).resolve()
os.environ['HOME'] = str(SCRATCH)
os.environ['SPARK_WORKSPACE'] = str(SCRATCH / 'workspace')
os.environ['VINTOS_LAB_CAMPAIGNS'] = '0'
sys.path.insert(0, str(REPO / 'scripts'))
SEND = Mock(side_effect=AssertionError('external action forbidden'))
socket.socket.connect = SEND
socket.socket.connect_ex = SEND
urllib.request.urlopen = SEND
subprocess.Popen = SEND
sys.modules['requests'] = types.SimpleNamespace(get=SEND, post=SEND, request=SEND)
sys.modules['httpx'] = types.SimpleNamespace(get=SEND, post=SEND, request=SEND)


def guard(event, args):
    if event in ('socket.connect', 'socket.sendto', 'subprocess.Popen', 'os.system'):
        raise AssertionError('external action forbidden')
    paths = []
    if event == 'open' and (args[2] or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        paths = [args[0]]
    elif event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod'):
        path = args[0]
        index = 1 if event in ('os.remove', 'os.rmdir') else 2
        fd = args[index] if len(args) > index else -1
        if not isinstance(path, int) and not Path(path).is_absolute() and isinstance(fd, int) and fd >= 0:
            if sys.platform == 'darwin':
                import fcntl
                base = fcntl.fcntl(fd, 50, bytes(1024)).split(b'\0')[0].decode()
            else:
                base = os.readlink('/proc/self/fd/%d' % fd)
            path = Path(base) / path
        paths = [path]
    elif event == 'os.rename': paths = list(args[:2])
    for path in paths:
        if not isinstance(path, int) and not Path(path).resolve().is_relative_to(SCRATCH):
            raise AssertionError('write outside scratch: ' + str(path))


sys.addaudithook(guard)
import chemistry_lab as C
import chemistry_sources as S
import lab_sources as L
import lab_tool_calls as T


class Tools(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.CONFIG).is_relative_to(SCRATCH))
        self.assertTrue(Path(C.NOTEBOOK).is_relative_to(SCRATCH))
        self.assertIs(socket.socket.connect, SEND)
        self.assertIs(urllib.request.urlopen, SEND)
        self.assertIs(sys.modules['requests'].post, SEND)

    def tearDown(self): SEND.assert_not_called()

    def test_atlas_plugin_uses_public_source_with_original_gene(self):
        public, connector = T.normalize_plugin({'plugin':'atlas', 'tool':'atlas.get_asset',
                                                'arguments':{'gene':'SLC26A4'}}, '')
        self.assertEqual(public, {'source':'atlas', 'gene':'SLC26A4'})
        self.assertIsNone(connector)
        with patch.object(S, 'query', return_value={'receipt': {'records':[]}}) as query:
            S.query_plugin('atlas', 'atlas.get_asset', {'gene':'SLC26A4'}, 'regulatory score')
            self.assertEqual(query.call_args.args[0]['gene'], 'SLC26A4')

    def test_pdb_plugin_routes_deposited_entry(self):
        public, _ = T.normalize_plugin({'plugin':'pdb', 'tool':'get_structure', 'arguments':{'pdb_id':'8SGW'}})
        self.assertEqual(public, {'source':'pdb', 'entry_id':'8SGW', 'operation':'structure_evidence'})

    def test_wrong_plugin_owner_does_not_change_boltz_operation(self):
        public, connector = T.normalize_plugin({'plugin':'pdb', 'tool':'pdb.boltz_get_structure_and_binding_prediction',
                                                'arguments':{'job_id':'original'}})
        self.assertIsNone(public)
        self.assertEqual(connector['plugin'], 'boltz')
        self.assertEqual(connector['tool'], 'boltz_get_structure_and_binding_prediction')
        self.assertEqual(connector['arguments'], {'job_id':'original'})

    def test_connector_written_as_source_reaches_connector_dispatch(self):
        inquiry = C._inquiry({'question':'Measure similarity of these sourced molecules', 'source_query':{
            'source':'nvmolkit','operation':'nvmolkit.similarity','arguments':{'smiles':['CCO','CCN']}}})
        self.assertIsNone(inquiry['source_query'])
        self.assertEqual(inquiry['plugin_query'], {'plugin':'nvmolkit','tool':'nvmolkit.similarity',
                                                  'arguments':{'smiles':['CCO','CCN']}})

    def test_paid_operation_stays_paid_and_policy_withheld(self):
        _, connector = T.normalize_plugin({'plugin':'pdb', 'tool':'boltz_start_structure_and_binding', 'arguments':{}})
        import claude_connector_catalog as catalog
        with self.assertRaises(PermissionError):
            catalog.policy(connector['plugin'], 'lab', connector['tool'])

    def test_ncbi_alias_keeps_target_and_scope(self):
        spec = L.normalize_source_spec({'source':'ncbi', 'operation':'search_proteins',
                                        'query':'recombinase', 'organism':'Planctomycetes'})
        self.assertEqual(spec['operation'], 'protein')
        self.assertEqual(spec['term'], 'recombinase')
        self.assertEqual(spec['organism'], 'Planctomycetes')
        with self.assertRaisesRegex(ValueError, 'unknown NCBI operation'):
            L.Sources(fetch=SEND).query({'source':'ncbi','operation':'invented_operation'})

    def test_invalid_asset_is_not_turned_into_guessed_gene(self):
        public, _ = T.normalize_plugin({'plugin':'atlas','tool':'get_asset','arguments':{'asset_id':'asset-1'}})
        self.assertIsNone(public)

    def test_explicit_measurement_is_not_broad_subject_search(self):
        inquiry = {'question':'Measure SLC26A4 complex confidence', 'plugin_query':{
            'plugin':'nvidia_nim','tool':'nvidia_nim.boltz2','arguments':{'polymers':[]}}}
        self.assertFalse(C.spent_retrieval(inquiry, {'subjects':['SLC26A4']}))
        # The separate lookup gate still sees an identical measurement request.
        import lab_repeats
        with patch.object(lab_repeats, 'LOOKUPS', str(SCRATCH/'lookups.jsonl')):
            lab_repeats.record(inquiry)
            self.assertIn('exact lookup', lab_repeats.repeat(inquiry))

    def test_switches_save_only_explicit_settings(self):
        for setter, key in ((C.set_enabled, 'enabled'), (C.set_evo2_enabled, 'evo2_enabled'),
                            (C.set_atlas_evo2_enabled, 'atlas_evo2_enabled')):
            with self.subTest(key=key), patch.object(C, 'status', return_value={}):
                C._atomic(C.CONFIG, {'alphagenome_python':'configured-python'})
                setter(True)
                raw = C._load(C.CONFIG, {})
                self.assertTrue(raw[key])
                self.assertEqual(raw['alphagenome_python'], 'configured-python')
                self.assertNotIn('coverage_context_tokens', raw)
                for untouched in ('enabled', 'evo2_enabled', 'atlas_evo2_enabled'):
                    if untouched != key: self.assertNotIn(untouched, raw)

    def test_observed_source_shorthands_retain_exact_identifiers(self):
        for request,expected in [({'uniprot':'P69905'},{'source':'uniprot','query':'accession:P69905'}),
                                 ({'interpro':'P69905'},{'source':'interpro','accession':'P69905'}),
                                 ({'source':'','pdb':'8SGW'},{'source':'pdb','entry_id':'8SGW'})]:
            self.assertEqual(T.normalize_request('source',request),expected)

    def test_same_question_may_use_distinct_instruments_but_not_repeat_one(self):
        import lab_repeats
        question='Measure the resulting energy against the same exact reference.'
        first={'question':question,'instrument_query':{'skill':'house_experiment_molecule','operation':'molecule'}}
        second={'question':question,'instrument_query':{'skill':'house_experiment_fold','operation':'fold'}}
        with patch.object(lab_repeats,'LOOKUPS',str(SCRATCH/'distinct-instruments.jsonl')):
            lab_repeats.record(first)
            self.assertFalse(lab_repeats.repeat(second))
            self.assertIn('exact lookup',lab_repeats.repeat(first))

    def test_guard_blocks_live_store_write(self):
        with self.assertRaisesRegex(AssertionError, 'write outside scratch'):
            open('/tmp/not-this-test-store', 'w')


if __name__ == '__main__': unittest.main(verbosity=2)

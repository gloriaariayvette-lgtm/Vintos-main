#!/usr/bin/env python3
"""Actual synthetic assembly and request binding; direct read coverage only."""
from contextvars import Context
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import witness_capture as W
from witness_receipts import digest
spec = importlib.util.spec_from_file_location('map_context_fixture', ROOT/'broker/tests/test_witness_value_map_builds.py')
F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)


class Tests(unittest.TestCase):
    packets = F.Tests.packets

    def setUp(self):
        F.Tests.setUp(self)
        source = (ROOT/'scripts/value_map.py').read_text()
        start,end = source.index('def gather_full_context():'),source.index('\ndef _map_day(')
        exec(compile(source[start:end], 'actual-map-gather', 'exec'), self.vm.__dict__)
        self.vm._door = lambda p: []
        (self.root/'SOUL.md').write_text('Synthetic identity base.')
        (self.root/'emotional-state.txt').write_text('Synthetic present state.')
        (self.root/'fulfilled-wants.json').write_text(json.dumps([{'want':'Synthetic completed item.'}]))
        self.addCleanup(lambda:self.assertIsNone(W._value_map_context.get()))

    def assemble(self, build=None):
        build = build or W.begin_value_map_build()
        text = self.vm._map_gather(build)
        return build,text

    def call(self, build, text, at=None):
        token = W.enter_value_map_stage(build,'draft_a')
        payload={'model':'fixture','messages':[{'role':'system','content':'Synthetic system'},
                 {'role':'user','content':text}], 'temperature':0.6,'max_tokens':1500}
        try:
            if at is None: obs=W.begin_value_map_call(payload)
            else:
                with patch.object(W.time,'time',return_value=at): obs=W.begin_value_map_call(payload)
            return obs['packet']
        finally: W.leave_value_map_stage(token)

    def test_actual_builder_records_direct_reads_and_only_draft_context_matches(self):
        self.vm.build_map()
        calls={p['stage']:p for p in self.packets('call')}
        self.assertEqual(self.http.call_count,3)
        for stage in ('draft_a','draft_b'):
            binding=calls[stage]['assembled_context']
            self.assertEqual(binding['state'],'matched')
            self.assertEqual(binding['slot'],1)
            reads=binding['assembly']['reads']
            self.assertEqual(len(reads),3)
            self.assertEqual({r['decoded_sha256'] for r in reads}, {digest((self.root/p).read_text()) for p in
                ('SOUL.md','emotional-state.txt','fulfilled-wants.json')})
            self.assertFalse(binding['assembly']['upstream_complete'])
            self.assertEqual(binding['assembly']['contribution'],'not_established')
            self.assertTrue(all(r['complete'] is False for r in reads))
        self.assertEqual(calls['synthesis']['assembled_context']['state'],'not_found')
        for text in ('Synthetic identity base.',str(self.root),'Synthetic completed item.'):
            self.assertNotIn(text,json.dumps(calls))

    def test_capture_off_and_failed_observer_leave_identical_assembly(self):
        _,expected=self.assemble()
        with patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH=''):
            self.assertEqual(self.vm._map_gather(None),expected)
        with patch.object(self.vm,'_witness_call',return_value=None):
            self.assertEqual(self.vm._map_gather(None),expected)
        self.assertIsNone(W._value_map_context.get())

    def test_read_once_json_failure_observed_before_parse_missing_not_invented(self):
        (self.root/'fulfilled-wants.json').write_text('{broken synthetic json')
        build,text=self.assemble()
        metadata=build['assembled_context'][1]
        self.assertEqual(len(metadata['reads']),3)
        self.assertIn(digest('{broken synthetic json'),[r['decoded_sha256'] for r in metadata['reads']])
        self.assertNotIn('WANTS YOU FULFILLED',text)
        self.assertEqual(metadata['scope'],'instrumented_reads_and_views_during_assembly')
        class Handle:
            name='synthetic-resource'
            calls=0
            def read(inner): inner.calls+=1; return '[1,2]'
        h=Handle(); self.assertEqual(self.vm._map_json(h),[1,2]); self.assertEqual(h.calls,1)

    def test_discarded_tail_is_read_coverage_not_admitted_source(self):
        (self.root/'SOUL.md').write_text('Synthetic identity ' * 4000)
        (self.root/'humor-profile.json').write_text(json.dumps({'style_notes':'Synthetic late hint'}))
        build,text=self.assemble()
        self.assertEqual(len(text),60000)
        self.assertNotIn('Synthetic late hint',text)
        self.assertIn(digest((self.root/'humor-profile.json').read_text()),
                      [r['decoded_sha256'] for r in build['assembled_context'][1]['reads']])
        self.assertEqual(build['assembled_context'][1]['contribution'],'not_established')

    def test_changed_duplicate_and_future_inputs_do_not_claim_match(self):
        build,text=self.assemble()
        self.assertEqual(self.call(build,text)['assembled_context']['state'],'matched')
        self.assertEqual(self.call(build,text+text)['assembled_context']['state'],'ambiguous')
        self.assertEqual(self.call(build,'Edited fixture')['assembled_context']['state'],'not_found')
        self.assertEqual(self.call(build,text,0)['assembled_context'],{'state':'unavailable'})

    def test_second_assembly_cannot_reuse_first_receipt(self):
        build,text=self.assemble()
        self.vm._map_gather(build)
        self.assertNotIn('assembled_context',build)
        self.assertEqual(self.call(build,text)['assembled_context'],{'state':'unavailable'})

    def test_exception_clears_scope_and_later_build_is_independent(self):
        build=W.begin_value_map_build()
        with patch.object(self.vm,'gather_full_context',side_effect=RuntimeError('fixture failure')):
            with self.assertRaises(RuntimeError):self.vm._map_gather(build)
        self.assertIsNone(W._value_map_context.get())
        self.assertNotIn('assembled_context',build)
        later,text=self.assemble()
        self.assertEqual(len(later['assembled_context'][1]['reads']),3)

    def test_nested_disabled_scope_and_interleaved_contexts(self):
        outer=W.begin_value_map_build(); token=W.begin_value_map_context(outer)
        try:
            W.observe_value_map_read('fixture-a','first')
            disabled=W.begin_value_map_context(None)
            W.observe_value_map_read('fixture-b','ignored')
            W.finish_value_map_context(disabled,None,'ignored')
            other=Context().run(self.assemble)[0]
            W.observe_value_map_read('fixture-c','last')
        finally:W.finish_value_map_context(token,outer,'outer rendered')
        self.assertEqual([r['decoded_sha256'] for r in outer['assembled_context'][1]['reads']],
                         [digest('first'),digest('last')])
        self.assertEqual(len(other['assembled_context'][1]['reads']),3)

    def test_limits_and_clocks_never_claim_complete_coverage(self):
        for count,size in ((70,1),(2,4194304)):
            build=W.begin_value_map_build(); token=W.begin_value_map_context(build)
            for i in range(count):W.observe_value_map_read('fixture', 'x'*size)
            W.finish_value_map_context(token,build,'fixture rendered')
            meta=build['assembled_context'][1]
            self.assertTrue(meta['truncated']); self.assertLessEqual(len(meta['reads']),64)
        build=W.begin_value_map_build();token=W.begin_value_map_context(build)
        with patch.object(W.time,'time',return_value=0):W.finish_value_map_context(token,build,'fixture')
        self.assertNotIn('assembled_context',build)
        self.assertIsNone(W._value_map_context.get())

    def test_packet_copy_does_not_follow_later_build_mutation(self):
        build,text=self.assemble();packet=self.call(build,text); before=copy.deepcopy(packet)
        build['assembled_context'][1]['reads'].clear()
        self.assertEqual(packet,before)


if __name__=='__main__':unittest.main()

#!/usr/bin/env python3
"""Auxiliary input receipts with synthetic files and fully stubbed HTTP."""
from contextvars import Context
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import witness_capture as W
from witness_receipts import digest
spec=importlib.util.spec_from_file_location('map_material_fixture',ROOT/'broker/tests/test_witness_value_map_builds.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)


class Tests(unittest.TestCase):
    packets=F.Tests.packets

    def setUp(self):
        F.Tests.setUp(self)
        source=(ROOT/'scripts/value_map.py').read_text()
        start,end=source.index('def get_temporal_context():'),source.index('MAP_FILE =')
        exec(compile(source[start:end],'actual-temporal-reader','exec'),self.vm.__dict__)
        (self.root/'SOUL.md').write_text('Synthetic identity for the current invocation.')
        (self.root/'temporal-context.txt').write_text('  Synthetic clock. '+'x'*400+'\n')
        self.addCleanup(lambda:self.assertIsNone(W._value_map_context.get()))

    def capture_materials(self):
        build=W.begin_value_map_build()
        identity=self.vm._map_material(build,'system_identity',self.vm._system_identity)
        temporal=self.vm._map_material(build,'temporal',self.vm.get_temporal_context)
        return build,identity,temporal

    def binding(self,build,system,user,at=None):
        token=W.enter_value_map_stage(build,'draft_a')
        try:
            payload={'model':'fixture','messages':[{'role':'system','content':system},
                     {'role':'user','content':user}],'temperature':0.6,'max_tokens':1500}
            if at is None:return W.begin_value_map_call(payload)['packet']['auxiliary_inputs']
            with patch.object(W.time,'time',return_value=at):return W.begin_value_map_call(payload)['packet']['auxiliary_inputs']
        finally:W.leave_value_map_stage(token)

    def test_actual_builder_binds_identity_in_all_calls_and_temporal_in_drafts(self):
        self.vm.build_map()
        self.assertEqual(self.http.call_count,3)
        calls={p['stage']:p for p in self.packets('call')}
        for stage,packet in calls.items():
            aux=packet['auxiliary_inputs']
            self.assertEqual(aux['system_identity']['state'],'matched')
            self.assertEqual(aux['system_identity']['slot'],0)
            self.assertEqual(aux['temporal']['state'],'not_found' if stage=='synthesis' else 'matched')
            for label,path in [('system_identity','SOUL.md'),('temporal','temporal-context.txt')]:
                meta=aux[label]['assembly'];read,=meta['reads']
                self.assertEqual(read['decoded_sha256'],digest((self.root/path).read_text()))
                self.assertEqual(meta['read_state'],'observed')
                self.assertFalse(meta['upstream_complete'])
            self.assertEqual(aux['temporal']['assembly']['rendered_chars'],300)
        for text in (str(self.root),'Synthetic identity for the current invocation.','Synthetic clock.'):
            self.assertNotIn(text,json.dumps(calls))

    def test_default_identity_can_match_without_inventing_a_file_read(self):
        (self.root/'SOUL.md').unlink()
        build,identity,temporal=self.capture_materials()
        self.assertEqual(identity,'You are Vintos.')
        binding=self.binding(build,identity,temporal)['system_identity']
        self.assertEqual(binding['state'],'matched')
        self.assertEqual(binding['assembly']['read_state'],'unavailable')
        self.assertEqual(binding['assembly']['reads'],[])
        self.assertFalse(binding['assembly']['upstream_complete'])

    def test_missing_temporal_does_not_create_empty_string_match(self):
        (self.root/'temporal-context.txt').unlink()
        build,identity,temporal=self.capture_materials()
        self.assertEqual(temporal,'')
        self.assertEqual(self.binding(build,identity,temporal)['temporal'],{'state':'unavailable'})

    def test_wrong_slot_duplicates_and_future_clock_not_bound(self):
        build,identity,temporal=self.capture_materials()
        swapped=self.binding(build,temporal,identity)
        self.assertEqual({v['state'] for v in swapped.values()},{'not_found'})
        doubled=self.binding(build,identity*2,temporal*2)
        self.assertEqual({v['state'] for v in doubled.values()},{'ambiguous'})
        future=self.binding(build,identity,temporal,0)
        self.assertEqual({v['state'] for v in future.values()},{'unavailable'})

    def test_duplicate_material_entry_does_not_reuse_first(self):
        build,identity,temporal=self.capture_materials()
        self.vm._map_material(build,'temporal',self.vm.get_temporal_context)
        aux=self.binding(build,identity,temporal)
        self.assertEqual(aux['temporal'],{'state':'unavailable'})
        self.assertEqual(aux['system_identity']['state'],'matched')

    def test_exception_resets_scope_and_does_not_mask_reader_error(self):
        build=W.begin_value_map_build()
        def fail():raise RuntimeError('synthetic reader failure')
        with self.assertRaises(RuntimeError):self.vm._map_material(build,'temporal',fail)
        self.assertIsNone(W._value_map_context.get())
        self.assertNotIn('temporal',build['materials'])
        self.assertEqual(self.vm._map_material(build,'system_identity',self.vm._system_identity),
                         (self.root/'SOUL.md').read_text())

    def test_disabled_nested_and_independent_context_do_not_mix(self):
        build=W.begin_value_map_build();token=W.begin_value_map_context(build)
        try:
            self.vm._map_material(None,'temporal',self.vm.get_temporal_context)
            other=Context().run(self.capture_materials)[0]
            W.observe_value_map_read('fixture-only','outer')
        finally:W.finish_value_map_context(token,build,'outer rendered')
        self.assertEqual([r['decoded_sha256'] for r in build['assembled_context'][1]['reads']],[digest('outer')])
        self.assertEqual(set(other['materials']),{'system_identity','temporal'})

    def test_capture_off_or_failed_observer_preserves_reader_results(self):
        expected_identity=(self.root/'SOUL.md').read_text()
        expected_clock=(self.root/'temporal-context.txt').read_text().strip()[:300]
        for manager in (patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH=''),patch.object(self.vm,'_witness_call',return_value=None)):
            with manager:
                self.assertEqual(self.vm._map_material(None,'system_identity',self.vm._system_identity),expected_identity)
                self.assertEqual(self.vm._map_material(None,'temporal',self.vm.get_temporal_context),expected_clock)

    def test_large_material_is_unavailable_but_reader_output_unchanged(self):
        text='synthetic large material '*3000
        (self.root/'SOUL.md').write_text(text)
        build,identity,temporal=self.capture_materials()
        self.assertEqual(identity,text)
        self.assertEqual(self.binding(build,identity,temporal)['system_identity'],{'state':'unavailable'})


if __name__=='__main__':unittest.main()

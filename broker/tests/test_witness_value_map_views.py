#!/usr/bin/env python3
"""Actual consumer results, synthetic retained rows, no sends or live paths."""
import copy
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
import evidence_view as EV
from witness_receipts import digest
spec=importlib.util.spec_from_file_location('map_view_fixture',ROOT/'broker/tests/test_witness_value_map_builds.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)


class Tests(unittest.TestCase):
    def setUp(self):
        F.Tests.setUp(self)
        for name in ('MEMORY','LEDGER','HELD_LOG'):
            p=patch.object(EV,name,str(self.root/name));p.start();self.addCleanup(p.stop)
        p=patch.dict(sys.modules,evidence_view=EV);p.start();self.addCleanup(p.stop)
        p=patch.object(EV,'held_read',self.sender);p.start();self.addCleanup(p.stop)
        self.path=self.root/'interaction-ledger.json'
        self.rows=[{'gloria':'Synthetic counterpart','vintos':'Synthetic ordinary',
                    'generation_provenance':{'may_witness':True,'output_provenance':'ordinary_generation'}},
                   {'gloria':'Synthetic counterpart two','vintos':'Synthetic influenced',
                    'generation_provenance':{'may_witness':False,'output_provenance':'stratagem_influenced'}},
                   {'gloria':'Synthetic legacy','vintos':'Synthetic legacy reply'},
                   {'gloria':'Synthetic malformed','vintos':'Synthetic malformed reply','generation_provenance':'bad'}]
        self.path.write_text(json.dumps(self.rows))
        self.assertEqual(self.path.parent,self.root)
        self.assertIs(EV.held_read,self.sender)
        self.addCleanup(lambda:self.assertIsNone(W._value_map_context.get()))

    def observed(self,path=None):
        build=W.begin_value_map_build();token=W.begin_value_map_context(build)
        try:rows=self.vm._door(path or self.path)
        finally:W.finish_value_map_context(token,build,'synthetic assembled result')
        return rows,build['assembled_context'][1]

    def test_actual_ledger_view_preserves_filtered_rows_and_explicit_markers(self):
        expected=EV.ledger_view(str(self.path))
        rows,meta=self.observed();self.assertEqual(rows,expected)
        record,=meta['reads']
        self.assertEqual(record['lane'],'ledger_view')
        self.assertEqual(record['standing_counts'],{'eligible':2,'ineligible':1,'HELD':1,'unknown':0})
        self.assertEqual(record['permission_counts'],{'true':1,'false':1,'missing':1,'malformed':1})
        self.assertEqual(record['withheld_rows'],2)
        self.assertEqual(record['known_influence_marker_rows'],1)
        self.assertEqual(record['source_version'],'unobserved')
        self.assertEqual(record['view_sha256'],digest(json.dumps(rows,sort_keys=True,separators=(',',':'),allow_nan=False)))
        self.assertEqual(rows[1]['vintos'],'')
        self.assertEqual(rows[1]['gloria'],self.rows[1]['gloria'])
        self.assertFalse(meta['upstream_complete'])
        for text in (str(self.path),'Synthetic counterpart','Synthetic ordinary'):
            self.assertNotIn(text,json.dumps(meta))

    def test_history_path_observes_existing_witness_subset(self):
        path=self.root/'fixture-history.json';path.write_text(json.dumps(self.rows))
        expected=EV.open_history(str(path))
        rows,meta=self.observed(path)
        self.assertEqual(rows,expected);self.assertEqual(len(rows),2)
        self.assertEqual(meta['reads'][0]['lane'],'history_view')

    def test_existing_raw_fallback_is_visible_and_not_mislabeled_filtered(self):
        with patch.object(EV,'ledger_view',side_effect=RuntimeError('synthetic failure')):
            rows,meta=self.observed()
        self.assertEqual(rows,self.rows)
        record,=meta['reads']
        self.assertEqual(record['lane'],'raw_fallback')
        self.assertEqual(record['standing_counts']['unknown'],4)
        self.assertEqual(record['permission_counts']['false'],1)
        self.assertEqual(record['withheld_rows'],0)

    def test_empty_fallback_and_empty_view_are_distinct(self):
        self.path.unlink()
        rows,meta=self.observed();self.assertEqual(rows,[])
        self.assertEqual(meta['reads'][0]['lane'],'ledger_view')
        with patch.object(EV,'ledger_view',side_effect=RuntimeError('synthetic failure')):
            rows,meta=self.observed()
        self.assertEqual(rows,[]);self.assertEqual(meta['reads'][0]['lane'],'empty_fallback')

    def test_capture_off_and_sink_failure_keep_the_exact_result(self):
        expected=EV.ledger_view(str(self.path))
        for manager in (patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH=''),patch.object(self.vm,'_witness_call',return_value=None)):
            with manager:self.assertEqual(self.vm._door(self.path),expected)

    def test_counts_do_not_coerce_permission_and_packets_are_snapshots(self):
        rows=[{'generation_provenance':{'may_witness':1}}, {'generation_provenance':None},
              {'provenance':{'may_witness':False}}, {'generation_provenance':{'may_witness':True,'output_provenance':'stratagem_influenced'}},42]
        with patch.object(EV,'ledger_view',return_value=rows):
            result,meta=self.observed()
        before=copy.deepcopy(meta);result[0]['generation_provenance']['may_witness']=True
        self.assertEqual(meta,before)
        self.assertEqual(meta['reads'][0]['permission_counts'],{'true':1,'false':1,'missing':0,'malformed':3})
        self.assertEqual(meta['reads'][0]['known_influence_marker_rows'],1)

    def test_limits_and_malformed_values_preserve_results_and_mark_gap(self):
        for rows in ([{}]*4097,[{'x':float('nan')}],[{'x':'a'*4194305}],{'wrong':'shape'}):
            with patch.object(EV,'ledger_view',return_value=rows):result,meta=self.observed()
            self.assertIs(result,rows);self.assertTrue(meta['truncated'])
            record,=meta['reads'];self.assertEqual(record['state'],'unavailable')
            self.assertNotIn('view_sha256',record)

    def test_budget_shared_with_direct_reads_and_attempted_oversized_view(self):
        build=W.begin_value_map_build();token=W.begin_value_map_context(build)
        try:
            W.observe_value_map_read('fixture','x'*4194200)
            W.observe_value_map_view('fixture','ledger_view',[{'x':'y'*200}])
            W.observe_value_map_view('fixture','ledger_view',[{}])
        finally:W.finish_value_map_context(token,build,'fixture result')
        meta=build['assembled_context'][1]
        self.assertTrue(meta['truncated']);self.assertEqual(len(meta['reads']),3)
        self.assertEqual([r['state'] for r in meta['reads'][1:]],['unavailable','unavailable'])

    def test_read_count_bound_is_shared_without_eviction(self):
        build=W.begin_value_map_build();token=W.begin_value_map_context(build)
        try:
            W.observe_value_map_read('fixture','first')
            for _ in range(70):W.observe_value_map_view('fixture','ledger_view',[])
        finally:W.finish_value_map_context(token,build,'fixture result')
        meta=build['assembled_context'][1]
        self.assertEqual(len(meta['reads']),64);self.assertTrue(meta['truncated'])
        self.assertEqual(meta['reads'][0]['decoded_sha256'],digest('first'))


if __name__=='__main__':unittest.main()

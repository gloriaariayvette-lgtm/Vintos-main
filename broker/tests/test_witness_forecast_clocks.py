#!/usr/bin/env python3
"""Clock failures stay held while aggregate diagnostics identify the missing fact."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('clock_fixture',ROOT/'broker/tests/test_judges_witness.py')
F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)


class Tests(unittest.TestCase):
    def setUp(self):
        self.row,self.nodes,self.forecast,self.embedding,self.checkpoints=F.fixture()
        self.sender=Mock(side_effect=AssertionError('external action forbidden'))
        self.patch=patch.object(socket.socket,'connect',self.sender); self.patch.start()
        self.addCleanup(self.patch.stop); self.addCleanup(self.sender.assert_not_called)
        self.assertIsInstance(self.sender,Mock)
        # Only pure replay functions and an extracted pure timestamp formatter
        # are executed. No organ initialization, path access, sender or encoder.

    def score(self, forecasts=None):
        return F.R.innovation([self.row],self.forecast_list(forecasts),[self.embedding],self.checkpoints)

    def forecast_list(self, forecasts):
        return [self.forecast] if forecasts is None else forecasts

    def fields(self):
        return [('forecast_at',self.forecast,'ts'),('arrived_at',self.forecast,'arrived_at'),
                ('trained_at',self.checkpoints['fixture-checkpoint'],'trained_at'),
                ('context_last_at',self.forecast['self'],'context_last_ts')]

    def test_each_required_clock_reports_missing_without_changing_rejection(self):
        for field,container,key in self.fields():
            old=container.pop(key)
            report,rows=self.score()
            self.assertEqual(report['held']['missing_or_invalid_forecast_evidence'],1)
            self.assertEqual(report['invalid_clocks'],{field:{'missing':1}})
            self.assertEqual(rows,[])
            container[key]=old

    def test_naive_clocks_never_borrow_host_timezone(self):
        for field,container,key in self.fields():
            old=container[key]; container[key]='1970-01-01T00:00:01'
            report,rows=self.score()
            self.assertEqual(report['invalid_clocks'],{field:{'missing_timezone':1}})
            self.assertEqual(rows,[])
            container[key]=old

    def test_existing_source_formatter_is_naive_and_remains_unscorable(self):
        tree=ast.parse((ROOT/'scripts/jepa_self_head.py').read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_iso')
        ns={};exec(compile(ast.Module(body=[function],type_ignores=[]),'existing-formatter','exec'),ns)
        self.forecast['self']['context_last_ts']=ns['_iso'](80)
        report,rows=self.score()
        self.assertEqual(report['invalid_clocks'],{'context_last_at':{'missing_timezone':1}})
        self.assertEqual(rows,[])

    def test_boolean_negative_nonfinite_and_malformed_values_are_invalid(self):
        for value in (True,-1,float('nan'),float('inf'),{},[],'private-malformed-clock'):
            self.forecast['ts']=value
            report,rows=self.score()
            self.assertEqual(report['invalid_clocks'],{'forecast_at':{'invalid':1}})
            self.assertNotIn('private-malformed-clock',json.dumps(report))
            self.assertEqual(rows,[])

    def test_offset_clocks_and_numeric_instants_keep_identical_scores(self):
        before,rows=self.score()
        for _,container,key in self.fields():
            from datetime import datetime,timezone
            container[key]=datetime.fromtimestamp(container[key],timezone.utc).isoformat()
        after,newrows=self.score()
        self.assertEqual(before,after)
        self.assertEqual(before['invalid_clocks'],{})
        self.assertEqual(rows[0]['error'],newrows[0]['error'])

    def test_first_encountered_failure_only_and_noncausal_remains_distinct(self):
        self.forecast['arrived_at']=None
        self.forecast['self']['context_last_ts']='1970-01-01T00:00:01'
        report,rows=self.score()
        self.assertEqual(report['invalid_clocks'],{'arrived_at':{'missing':1}})
        self.forecast['arrived_at']=99
        self.checkpoints['fixture-checkpoint']['trained_at']=200
        report,rows=self.score()
        self.assertEqual(report['invalid_clocks'],{})
        self.assertEqual(report['held']['noncausal_forecast'],1)
        self.assertEqual(rows,[])

    def test_bad_earliest_forecast_cannot_promote_later_valid_one(self):
        bad=copy.deepcopy(self.forecast);bad['ts']=100;bad['self']['context_last_ts']='1970-01-01T00:00:01'
        for forecasts in ([bad,self.forecast],[self.forecast,bad]):
            report,rows=self.score(forecasts)
            self.assertEqual(report['invalid_clocks'],{'context_last_at':{'missing_timezone':1}})
            self.assertEqual(report['held']['unscorable_earliest_forecast'],1)
            self.assertEqual(rows,[])

    def test_unknown_forecast_order_stays_unknown(self):
        bad=copy.deepcopy(self.forecast);bad.pop('ts')
        report,rows=self.score([bad,self.forecast])
        self.assertEqual(report['invalid_clocks'],{'forecast_at':{'missing':1}})
        self.assertEqual(report['held']['unknown_forecast_order'],1)
        self.assertEqual(rows,[])

    def test_nonclock_evidence_failures_are_not_reported_as_clock_failures(self):
        self.forecast['self']['emb']=[True,0.]
        report,rows=self.score()
        self.assertEqual(report['invalid_clocks'],{})
        self.assertEqual(report['held']['missing_or_invalid_forecast_evidence'],1)
        self.assertEqual(rows,[])


if __name__ == '__main__': unittest.main()

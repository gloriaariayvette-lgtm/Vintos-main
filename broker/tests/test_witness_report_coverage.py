#!/usr/bin/env python3
"""Observed-control coverage rendered from actual synthetic producer/replay outputs."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
F=module('report_coverage_fixture','broker/tests/test_witness_self_input_baselines.py')
M=module('coverage_renderer','experiments/judges-witness/report.py')

class Tests(unittest.TestCase):
    setUp=F.Tests.setUp
    report=F.Tests.report

    def aggregate(self):
        census,admitted=F.R.census([('canonical',self.admitted)],self.nodes,500)
        innovation,_=F.R.innovation(admitted,self.forecasts,self.targets,self.checkpoints)
        controls,_=self.report()
        return dict(schema='judges-shadow-v1',input_kind='synthetic',census=census,
                    innovation=innovation,behaviour_receipt={'status':'not_configured'},self_input_baselines=controls)

    def test_actual_pair_reports_target_and_forecast_denominators(self):
        report=self.aggregate();before=copy.deepcopy(report);text=M.render(report)
        self.assertIn('Unique eligible replies: 3',text)
        self.assertIn('Unique targets with a scorable forecast: 1; without one: 2',text)
        self.assertIn('Forecast pair coverage: 1/1',text)
        self.assertIn('Distinct-target pair coverage: 1/1',text)
        self.assertEqual(before,report)
        for value in ('fixture-block','fixture-target','fixture-checkpoint','fixture-encoder'):
            self.assertNotIn(value,text)

    def test_missing_receipt_keeps_scorable_forecasts_visible(self):
        self.config['receipts']=[]
        text=M.render(self.aggregate())
        self.assertIn('Scorable forecast rows: 1; paired with both excerpt controls: 0; without a pair: 1',text)
        self.assertIn('Forecast pair coverage: 0/1',text)
        self.assertIn('Distinct-target pair coverage: 0/1',text)

    def test_no_forecasts_means_undefined_not_zero_fraction(self):
        self.forecasts=[];text=M.render(self.aggregate())
        self.assertIn('without one: 3',text)
        self.assertIn('Forecast pair coverage is undefined',text)
        self.assertIn('Distinct-target pair coverage is undefined',text)
        self.assertNotIn('0/0',text)

    def test_multiple_checkpoints_do_not_double_count_targets(self):
        second=copy.deepcopy(self.forecasts[0]);second['self']['checkpoint_id']='fixture-second'
        self.checkpoints['fixture-second']=copy.deepcopy(self.checkpoints['fixture-checkpoint'])
        self.forecasts.append(second)
        text=M.render(self.aggregate())
        self.assertIn('Forecast pair coverage: 1/2',text)
        self.assertIn('Distinct-target pair coverage: 1/1',text)
        self.assertIn('Unique targets with a scorable forecast: 1',text)

    def test_unfinished_block_preserves_forecasts_but_has_no_pairs(self):
        self.config['blocks'][0]['end']=600
        text=M.render(self.aggregate())
        self.assertIn('Scorable forecast rows outside complete declared blocks: 1',text)
        self.assertIn('Forecast pair coverage: 0/1',text)
        self.assertNotIn('600',text)

    def test_absent_coverage_and_absent_controls_remain_different(self):
        report=self.aggregate();report['self_input_baselines'].pop('coverage')
        text=M.render(report);self.assertIn('Coverage not supplied.',text)
        report.pop('self_input_baselines');text=M.render(report)
        self.assertNotIn('Coverage not supplied.',text)
        self.assertIn('## Observed excerpt-control coverage\n\nNot configured.',text)

    def test_cross_report_and_arithmetic_inconsistency_abort(self):
        for key in ('admitted_replies_before_cutoff','targets_with_scorable_forecast',
                    'targets_without_scorable_forecast','scorable_forecasts_before_cutoff',
                    'paired_forecasts','paired_targets','scorable_forecasts_without_pair',
                    'scorable_forecasts_outside_complete_blocks'):
            report=self.aggregate();report['self_input_baselines']['coverage'][key]+=1
            with self.assertRaisesRegex(ValueError,'^invalid shadow report evidence$'):M.render(report)

    def test_boolean_negative_or_private_values_never_render(self):
        for value in (True,-1,'private-sentinel',None):
            report=self.aggregate();report['self_input_baselines']['coverage']['paired_targets']=value
            with self.assertRaisesRegex(ValueError,'^invalid shadow report evidence$'):M.render(report)

    def test_private_block_and_group_fields_are_not_copied(self):
        report=self.aggregate();c=report['self_input_baselines']['coverage']
        c['blocks']=[{'private-sentinel':'private-sentinel'}]
        c['groups']=[{'private-sentinel':'private-sentinel'}]
        c['meaning']='private-sentinel'
        self.assertNotIn('private-sentinel',M.render(report))

if __name__=='__main__':unittest.main()

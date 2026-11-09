#!/usr/bin/env python3
"""Synthetic-only coverage denominators; reuse actual producer/replay fixtures."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('coverage_fixture',ROOT/'broker/tests/test_witness_self_input_baselines.py')
F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)


class Tests(unittest.TestCase):
    setUp = F.Tests.setUp
    report = F.Tests.report

    def coverage(self, **kwargs): return self.report(**kwargs)[0]['coverage']

    def test_source_target_and_forecast_denominators_are_distinct(self):
        c = self.coverage()
        self.assertEqual(c['admitted_replies_before_cutoff'],3)
        self.assertEqual(c['targets_with_scorable_forecast'],1)
        self.assertEqual(c['targets_without_scorable_forecast'],2)
        self.assertEqual(c['scorable_forecasts_before_cutoff'],1)
        self.assertEqual(c['paired_forecasts'],1)
        self.assertEqual(c['paired_targets'],1)
        block, = c['blocks']
        self.assertEqual(block['admitted_replies_finalized'],1)
        self.assertEqual(block['targets_without_scorable_forecast'],0)
        group, = c['groups']
        self.assertEqual(group['paired_fraction'],1.)
        self.assertEqual(group['unavailable'],{})

    def test_missing_receipt_keeps_zero_coverage_group_and_scored_denominator(self):
        self.config['receipts'] = []
        c = self.coverage(); group, = c['groups']
        self.assertEqual(group['block_group'],1)
        self.assertEqual(group['scorable_forecasts'],1)
        self.assertEqual(group['paired_forecasts'],0)
        self.assertEqual(group['paired_fraction'],0.)
        self.assertEqual(group['unavailable'],{'missing_exact_forecast_receipt':1})
        self.assertEqual(c['scorable_forecasts_without_pair'],1)
        self.assertEqual(c['scorable_forecasts_outside_complete_blocks'],0)
        self.assertEqual(c['blocks'][0]['targets_with_scorable_forecast'],1)

    def test_missing_forecasts_do_not_become_zero_innovation(self):
        report, details = self.report(forecasts=[])
        c = report['coverage']
        self.assertEqual(c['admitted_replies_before_cutoff'],3)
        self.assertEqual(c['targets_without_scorable_forecast'],3)
        self.assertEqual(c['scorable_forecasts_before_cutoff'],0)
        self.assertEqual(c['blocks'][0]['targets_without_scorable_forecast'],1)
        self.assertEqual(c['groups'],[])
        self.assertEqual(report['paired_groups'],[])
        self.assertEqual(details,[])

    def test_unscorable_forecast_stays_in_source_denominator(self):
        forecasts=copy.deepcopy(self.forecasts); forecasts[0]['self']['emb']=[0.,0.]
        c = self.coverage(forecasts=forecasts)
        self.assertEqual(c['blocks'][0]['admitted_replies_finalized'],1)
        self.assertEqual(c['blocks'][0]['targets_without_scorable_forecast'],1)
        self.assertEqual(c['scorable_forecasts_before_cutoff'],0)

    def test_multiple_checkpoints_count_one_target_and_two_forecasts(self):
        second=copy.deepcopy(self.forecasts[0]); second['self']['checkpoint_id']='fixture-second-checkpoint'
        self.checkpoints['fixture-second-checkpoint']=copy.deepcopy(self.checkpoints['fixture-checkpoint'])
        c = self.coverage(forecasts=self.forecasts+[second])
        self.assertEqual(c['targets_with_scorable_forecast'],1)
        self.assertEqual(c['scorable_forecasts_before_cutoff'],2)
        self.assertEqual(c['paired_forecasts'],1)
        self.assertEqual(c['scorable_forecasts_without_pair'],1)
        self.assertEqual(len(c['groups']),2)
        self.assertEqual(sorted(g['paired_fraction'] for g in c['groups']),[0.,1.])

    def test_partial_pair_coverage_retains_same_group_denominator(self):
        row, _, forecast, embedding, _=F.F.fixture('fixture-unpaired',350,360)
        c=self.coverage(admitted=self.admitted+[row],forecasts=self.forecasts+[forecast],targets=self.targets+[embedding])
        self.assertEqual(c['admitted_replies_before_cutoff'],4)
        self.assertEqual(c['targets_with_scorable_forecast'],2)
        self.assertEqual(c['paired_targets'],1)
        group,=c['groups']
        self.assertEqual(group['scorable_forecasts'],2)
        self.assertEqual(group['paired_fraction'],.5)
        self.assertEqual(group['unavailable'],{'missing_exact_forecast_receipt':1})
        self.assertEqual(c['blocks'][0]['admitted_replies_finalized'],2)

    def test_incomplete_block_counts_observed_sources_but_cannot_pair(self):
        c = self.coverage(cutoff=350)
        self.assertFalse(c['blocks'][0]['complete_at_cutoff'])
        self.assertEqual(c['blocks'][0]['admitted_replies_finalized'],1)
        self.assertEqual(c['blocks'][0]['paired_forecasts'],0)
        self.assertEqual(c['scorable_forecasts_outside_complete_blocks'],1)
        self.assertIsNone(c['groups'][0]['block_group'])

    def test_empty_and_future_blocks_remain_visible_without_fake_groups(self):
        self.config['blocks'].extend([dict(block_id='empty',declared_at=400,start=410,end=420),
                                     dict(block_id='future',declared_at=400,start=510,end=520)])
        c = self.coverage()
        self.assertEqual(len(c['blocks']),3)
        self.assertEqual([b['admitted_replies_finalized'] for b in c['blocks']],[1,0,0])
        self.assertEqual([b['complete_at_cutoff'] for b in c['blocks']],[True,True,False])
        self.assertEqual(len(c['groups']),1)

    def test_finalized_source_window_does_not_imply_in_block_arrival(self):
        self.config['blocks'][0]['start']=300
        c = self.coverage()
        self.assertEqual(c['blocks'][0]['admitted_replies_finalized'],1)
        self.assertEqual(c['blocks'][0]['targets_with_scorable_forecast'],1)
        self.assertEqual(c['blocks'][0]['paired_targets'],0)
        self.assertEqual(c['scorable_forecasts_outside_complete_blocks'],1)
        self.assertIsNone(c['groups'][0]['block_group'])

    def test_exclusive_cutoff_removes_future_targets_from_denominators(self):
        c = self.coverage(cutoff=310)
        self.assertEqual(c['admitted_replies_before_cutoff'],2)
        self.assertEqual(c['scorable_forecasts_before_cutoff'],0)
        self.assertEqual(c['blocks'][0]['admitted_replies_finalized'],0)
        self.assertEqual(c['groups'],[])

    def test_missing_blocks_never_infer_evaluation_windows(self):
        self.config['blocks']=[]
        c = self.coverage()
        self.assertEqual(c['blocks'],[])
        self.assertEqual(c['scorable_forecasts_outside_complete_blocks'],1)
        self.assertEqual(c['scorable_forecasts_without_pair'],1)
        self.assertIsNone(c['groups'][0]['block_group'])

    def test_misaligned_decisions_cannot_silently_shrink_denominator(self):
        _, scores=F.R.innovation(self.admitted,self.forecasts,self.targets,self.checkpoints)
        _, decisions=self.report()
        originals={F.C._fingerprint(f):f for f in self.forecasts}
        groups={tuple(scores[0]['group']):1}
        for bad in ([],[dict(decisions[0],turn_id='wrong-target')],
                    [dict(decisions[0],forecast_sha256='0'*64)]):
            with self.assertRaisesRegex(ValueError,'inconsistent self-input coverage decisions'):
                F.R.self_input_coverage(self.admitted,scores,bad,originals,self.config['blocks'],groups,500)

    def test_aggregate_has_no_private_labels_hashes_or_times(self):
        encoded=json.dumps(self.coverage())
        for private in ('fixture-target','fixture-prior','fixture-block','fixture-checkpoint','fixture-encoder',
                        self.packet['forecast_row_sha256'],'declared_at','arrived_at','finalized_at'):
            self.assertNotIn(private,encoded)


if __name__ == '__main__': unittest.main()

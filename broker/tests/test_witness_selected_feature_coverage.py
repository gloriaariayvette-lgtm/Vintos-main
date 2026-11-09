#!/usr/bin/env python3
"""Selected-input coverage from real synthetic producers; isolated stores and stub calls."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock
import test_witness_selected_features as F
import test_witness_review_report as review
import witness_artifact_join as J


class Tests(unittest.TestCase):
    def setUp(self):
        self.fixture=F.Tests('test_actual_selected_texts_and_consumed_arrays_are_bound')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.case=self.fixture.case
        self.assertNotIn('.vintos',self.case.root.parts)
        self.assertIsInstance(self.case.case.enc.encode,Mock)
        self.assertIsInstance(self.case.case.sender,Mock)

    def pair(self):
        row=self.case.case.job();packet,=self.case.packets();return row,packet

    def aggregate(self,packets,rows,cutoff=1000):
        result,_=J.join_artifacts([],[],{},packets,cutoff,forecasts=rows)
        review.M.artifact_coverage(result,0)
        return result

    def states(self,packets,rows,cutoff=1000):
        return self.aggregate(packets,rows,cutoff)['selected_feature_states']

    def test_actual_observation_binds_once_and_has_no_admission_effect(self):
        row,p=self.pair();a=self.aggregate([p,p],[row,row])
        self.assertEqual(a['selected_feature_states'],{'bound_to_forecast':1})
        self.assertEqual(a['unique_packets'],1);self.assertEqual(a['packets_supplied'],2)
        self.assertEqual(a['admission_effect'],'none');self.assertEqual(a['scoring_effect'],'none')
        self.assertEqual(a['bound_unique_replies'],0)

    def test_missing_exact_forecast_never_uses_nearby_text_time_or_turn(self):
        row,p=self.pair()
        for other in ([],[dict(row,turn_id='different-synthetic-turn')],[dict(row,ts=row['ts']+0.01)]):
            self.assertEqual(self.states([p],other),{'exact_forecast_row_missing':1})

    def test_missing_observation_is_unknown_and_audit_is_not_forecast(self):
        row,p=self.pair();legacy=copy.deepcopy(p);del legacy['artifacts']['feature_inputs']
        self.assertEqual(self.states([legacy],[row]),{'unobserved':1})
        F.A.audit_encoder(self.case.case.enc,self.case.ledger(),self.case.manifest()).encode(['synthetic source reply'])
        audit,=self.case.packets('self-audit-embedding-')
        self.assertEqual(self.states([legacy,audit],[row]),{'not_forecast':1,'unobserved':1})

    def test_identity_clocks_and_cutoff_disagreements(self):
        row,p=self.pair()
        self.assertEqual(self.states([p],[row],row['ts']),{'outside_cutoff':1})
        for mutate,state in (
            (lambda r:r.update(mode='ahead'),'forecast_identity_mismatch'),
            (lambda r:r['self'].update(checkpoint_id='0'*64),'forecast_identity_mismatch'),
            (lambda r:r.update(arrived_at=r['ts']+1),'forecast_clock_mismatch'),
            (lambda r:r.update(ts=r['ts']+1),'forecast_clock_mismatch')):
            other=copy.deepcopy(row);mutate(other);packet=copy.deepcopy(p)
            packet['forecast_row_sha256']=F.W._fingerprint(other)
            self.assertEqual(self.states([packet],[other]),{state:1})

    def test_selected_exchange_must_be_strictly_before_arrival(self):
        row,p=self.pair()
        for at in (row['arrived_at'],row['arrived_at']+1):
            bad=copy.deepcopy(p);bad['artifacts']['feature_inputs']['exchange_at']=at
            self.assertEqual(self.states([bad],[row]),{'selected_clock_not_before_arrival':1})

    def test_conflicting_future_or_orphan_copies_are_not_filtered_away(self):
        row,p=self.pair();other=copy.deepcopy(p)
        other['artifacts']['feature_inputs']['selection']['now']['sha256']='0'*64
        other['forecast_at']=2000.
        self.assertEqual(self.states([p,other],[row]),{'conflicting_observations':2})
        self.assertEqual(self.states([p,other],[]),{'conflicting_observations':2})
        for first,second in ((p,other),(other,p)):
            self.assertEqual(self.states([first,second],[row]),{'conflicting_observations':2})

    def test_malformed_or_inconsistent_own_claims_cannot_hide_in_peer(self):
        row,p=self.pair()
        for mutate in (lambda f:f.update(upstream_complete=True),lambda f:f.update(exchange_at=float('nan')),
                       lambda f:f['selection']['own'].reverse(),lambda f:f['features'][0].update(values_sha256='0'*64)):
            bad=copy.deepcopy(p);mutate(bad['artifacts']['feature_inputs'])
            with self.assertRaises(ValueError):self.states([p,bad],[row])

    def test_renderer_fixed_counts_legacy_and_cross_section_conservation(self):
        row,p=self.pair();result=self.aggregate([p],[row])
        rendered='\n'.join(review.M.artifact_coverage(result,0))
        self.assertIn('Selected-feature receipt bindings',rendered)
        for private in (row['turn_id'],p['forecast_row_sha256'],'synthetic arrival',str(self.case.root)):
            self.assertNotIn(private,rendered)
        for counts in ({'bound_to_forecast':2},{'bound_to_forecast':True},{'conflicting_observations':1},
                       {'private label':1},{'not_forecast':1}):
            bad=copy.deepcopy(result);bad['selected_feature_states']=counts
            with self.assertRaises(ValueError):review.M.artifact_coverage(bad,0)
        legacy=copy.deepcopy(result);legacy.pop('selected_feature_states')
        review.M.artifact_coverage(legacy,0)

    def test_actual_replay_cli_publishes_private_aggregate_counts_only(self):
        row,p=self.pair();source=self.case.root/'selected-bundle.json';out=self.case.root/'selected-replay'
        source.write_text(json.dumps({'input_kind':'synthetic','forecasts':[row],'self_artifact_packets':[p]}))
        result=subprocess.run([sys.executable,str(review.ROOT/'experiments/judges-witness/replay.py'),
            '--scratch',str(self.case.root),'--input',str(source),'--output',str(out),
            '--cutoff','1970-01-01T00:16:40+00:00'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads((out/'aggregate.json').read_text())
        self.assertEqual(report['self_artifact_joins']['selected_feature_states'],{'bound_to_forecast':1})
        self.assertEqual((out/'aggregate.json').stat().st_mode & 0o777,0o600)
        for private in (row['turn_id'],p['forecast_row_sha256'],'synthetic arrival'):
            self.assertNotIn(private,json.dumps(report))
        self.case.case.sender.assert_not_called()


if __name__=='__main__':unittest.main()

#!/usr/bin/env python3
"""Partial runtime comparison over synthetic receipts; no encoder loads or external sends."""
import copy
import json
import subprocess
import sys
import types
import unittest
from unittest.mock import Mock
import test_witness_artifact_join as fixture
from test_witness_review_report import M

A,J,ROOT=fixture.A,fixture.J,fixture.ROOT


class Tests(unittest.TestCase):
    def setUp(self):
        self.case=fixture.Tests('test_actual_audit_packet_binds_exact_full_reply_without_scoring')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.assertNotIn('.vintos',self.case.root.parts)
        self.assertIsInstance(self.case.sender,Mock)
        self.sources,self.admitted,self.one,self.two,self.ex=self.case.observed_pair()
        snap=A.runtime_snapshot(types.SimpleNamespace(training=False,max_seq_length=400))
        runtime=dict(schema='encoder-runtime-observation-v1',before=snap,after=copy.deepcopy(snap),
            state='observed_equal',scope='stored_fields_two_child_levels_not_tokenizer_content_code_or_fitting')
        A.validate_runtime_observation(runtime)
        for packet in (self.one,self.two):packet['encoding_observation']['runtime']=copy.deepcopy(runtime)

    def summary(self,packets):
        value,_=J.join_artifacts(self.admitted,self.sources,self.case.nodes,packets,1000)
        counts=value['runtime_consistency']
        c=value['encoding_consistency']
        J.validate_runtime_consistency(counts,c['references'],c['groups'])
        return value

    def state(self,packets,name):
        value=self.summary(packets)
        self.assertEqual(value['runtime_consistency']['states'][name],1)
        self.assertEqual(value['runtime_consistency']['encoder_identity'],'unverified')
        self.assertEqual(value['scoring_effect'],'none')
        return value

    def change(self,packet,during=False):
        r=packet['encoding_observation']['runtime']
        r['after']['sha256']='d'*64
        if during:r['state']='observed_changed'
        else:r['before']['sha256']='d'*64

    def test_equal_partial_snapshots_require_distinct_calls(self):
        value=self.state([self.one,self.two],'matching_partial_snapshots')
        self.assertEqual(value['runtime_consistency']['references'],2)
        self.assertEqual(value['states'],{'bound_full_text':2})

    def test_matching_vectors_parameters_and_arguments_do_not_hide_runtime_change(self):
        self.change(self.two)
        value=self.state([self.one,self.two],'different_partial_snapshots')
        self.assertEqual(value['encoding_consistency']['raw_vectors'],{'matching_raw_vectors':1})
        self.assertEqual(value['encoding_consistency']['parameters'],{'matching_snapshots':1})
        self.assertEqual(value['encoding_consistency']['settings'],{'matching_settings':1})

    def test_during_call_change_survives_a_missing_peer(self):
        self.change(self.one,during=True)
        self.two.pop('encoding_observation')
        self.state([self.one,self.two],'changed_during_call')

    def test_between_call_difference_survives_missing_runtime_peer(self):
        self.change(self.two)
        missing=copy.deepcopy(self.one);missing['encoding_observation'].pop('runtime')
        self.state([self.one,self.two,missing],'different_partial_snapshots')

    def test_old_and_unavailable_observations_remain_incomplete(self):
        self.two['encoding_observation'].pop('runtime')
        self.state([self.one,self.two],'incomplete')
        self.one['encoding_observation'].pop('runtime')
        self.state([self.one,self.two],'incomplete')
        missing=A.runtime_snapshot(None)
        self.one['encoding_observation']['runtime']=dict(schema='encoder-runtime-observation-v1',
            before=missing,after=missing,state='unavailable',
            scope='stored_fields_two_child_levels_not_tokenizer_content_code_or_fitting')
        self.state([self.one],'incomplete')

    def test_duplicate_packets_and_same_invocation_copies_are_not_two_calls(self):
        self.state([self.one,self.one],'single_call')
        self.two['encoding_observation']['invocation']=self.one['encoding_observation']['invocation']
        # A different timing copy remains one invocation, even if both packets survive deduplication.
        self.two['encoding_observation']['timing']=dict(schema='encoder-call-timing-v1',
            parameter_before_seconds=None,parameter_after_seconds=None,encode_seconds=0.1)
        self.state([self.one,self.two],'single_call')

    def test_conflicting_same_invocation_snapshots_are_not_reported_matching(self):
        self.two['encoding_observation']['invocation']=self.one['encoding_observation']['invocation']
        self.change(self.two)
        value=self.state([self.one,self.two],'different_partial_snapshots')
        self.assertEqual(value['encoder_call_cost']['conflicting_calls'],1)

    def test_empty_and_unbound_inputs_do_not_invent_a_runtime_group(self):
        value=self.summary([])
        self.assertEqual(value['runtime_consistency']['groups'],0)
        self.one['source_refs'][0]['observed_turn_id']='synthetic-unknown'
        value=self.summary([self.one])
        self.assertEqual(value['runtime_consistency']['groups'],0)

    def test_order_invariance_and_exact_checkpoint_partition(self):
        self.change(self.two)
        self.assertEqual(self.summary([self.one,self.two]),self.summary([self.two,self.one]))
        self.two['checkpoint']['checkpoint_id']='e'*64
        value=self.summary([self.one,self.two])
        self.assertEqual(value['runtime_consistency']['groups'],2)
        self.assertEqual(value['runtime_consistency']['states']['single_call'],2)

    def test_forecast_and_audit_representations_compare_same_partial_runtime(self):
        import jepa_readout as readout
        self.one['emb']=[3.,4.]
        self.one['encoding_observation']['raw_vector_sha256']=J.fingerprint(self.one['emb'])
        call=copy.deepcopy(self.one['encoding_observation'])
        call.update(schema='forecast-encoding-observation-v1',invocation='2'*32)
        records={self.ex['his'][:400]:dict(schema='readout-encoding-link-v1',transform='readout_units_v1',raw_emb=[3.,4.],call=call)}
        artifacts=A.forecast_artifacts([self.ex],{self.ex['his'][:400]:readout.units([3.,4.])},
            {'_witness_checkpoint':self.case.manifest},{'checkpoint_id':self.case.manifest['checkpoint_id']},records)
        forecast=dict(schema='self-forecast-artifacts-v1',artifacts=artifacts)
        value=self.state([self.one,forecast],'matching_partial_snapshots')
        self.assertEqual(value['states'],{'mixed_vector_representations':2})

    def test_public_projection_validates_and_legacy_comparison_stays_unknown(self):
        summary=self.summary([self.one,self.two])
        text='\n'.join(M.artifact_coverage(summary,1))
        self.assertIn('matching_partial_snapshots: 1',text)
        self.assertNotIn(self.one['encoding_observation']['runtime']['before']['sha256'],text)
        for key,value in (('groups',False),('references',99),('encoder_identity','verified'),('private-sentinel',0)):
            bad=copy.deepcopy(summary);bad['runtime_consistency'][key]=value
            with self.assertRaises(ValueError):M.artifact_coverage(bad,1)
        bad=copy.deepcopy(summary);bad['runtime_consistency']['states']['private-sentinel']=0
        with self.assertRaises(ValueError):M.artifact_coverage(bad,1)
        bad=copy.deepcopy(summary);bad['runtime_consistency']['states']['matching_partial_snapshots']=2
        with self.assertRaises(ValueError):M.artifact_coverage(bad,1)
        summary.pop('runtime_consistency')
        self.assertIn('unavailable in this legacy report','\n'.join(M.artifact_coverage(summary,1)))

    def test_actual_replay_cli_preserves_census_and_innovation(self):
        baseline,admitted=fixture.R.census(self.sources,self.case.nodes,1000.)
        scores,_=fixture.R.innovation(admitted,[self.case.f],[self.case.e],self.case.ck)
        bundle=dict(input_kind='synthetic',sources=[dict(kind=k,rows=v) for k,v in self.sources],
            lineage=list(self.case.nodes.values()),forecasts=[self.case.f],embeddings=[self.case.e],checkpoints=self.case.ck,
            self_artifact_packets=[self.one,self.two])
        source=self.case.root/'runtime-input.json';source.write_text(json.dumps(bundle));out=self.case.root/'runtime-output'
        proc=subprocess.run([sys.executable,str(ROOT/'experiments/judges-witness/replay.py'),
            '--scratch',str(self.case.root),'--input',str(source),'--output',str(out),
            '--cutoff','1970-01-01T00:16:40+00:00'],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        report=json.loads((out/'aggregate.json').read_text())
        self.assertEqual(report['self_artifact_joins']['runtime_consistency']['states']['matching_partial_snapshots'],1)
        self.assertEqual(report['census'],json.loads(json.dumps(baseline)))
        self.assertEqual(report['innovation'],json.loads(json.dumps(scores)))
        self.assertEqual((out/'aggregate.json').stat().st_mode & 0o777,0o600)


if __name__=='__main__':unittest.main()

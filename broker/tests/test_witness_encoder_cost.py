#!/usr/bin/env python3
"""Measure existing synthetic calls only; private scratch and blocked transports."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import witness_self_artifacts as A
import witness_artifact_join as J
import test_witness_encoder_parameters as P

class Tests(unittest.TestCase):
    def setUp(self):
        self.case=P.Tests('test_parameter_hash_has_stable_order_and_no_parameter_names_or_values')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.assertNotIn('.vintos',self.case.case.root.parts)
        self.assertIsInstance(self.case.enc.encode,Mock)

    def packet(self):
        with patch.object(A.time,'perf_counter',side_effect=[0,1,2,5,6,8]):
            self.case.wrapped().encode(['synthetic source reply'])
        return self.case.packets()[0]

    def cost(self,packets):
        value=J.encoder_call_cost(packets)
        refs=sum(len(list(J.claims(p))) for p in packets)
        J.validate_encoder_call_cost(value,refs)
        return value

    def test_separate_hashing_and_encode_cost_without_extra_calls(self):
        p=self.packet();call=p['encoding_observation']
        self.assertEqual(call['timing'],dict(schema='encoder-call-timing-v1',
            parameter_before_seconds=1,encode_seconds=3,parameter_after_seconds=2))
        self.case.enc.encode.assert_called_once_with(['synthetic source reply'])
        self.assertEqual(self.case.enc.state_dict.call_count,2)
        self.assertEqual(self.case.validate(call),'observed_equal')
        c=self.cost([p]);self.assertEqual(c['calls'],1)
        self.assertEqual(c['parameter_snapshots'],dict(observed=2,total_bytes=16,max_bytes=8))
        self.assertEqual(c['stages']['encode_seconds']['total_seconds'],3)

    def test_unsupported_state_still_reports_attempt_cost_without_size_claim(self):
        self.case.enc.state_dict.side_effect=RuntimeError('synthetic unsupported state')
        c=self.cost([self.packet()])
        self.assertEqual(c['parameter_snapshots'],dict(observed=0,total_bytes=0,max_bytes=0))
        self.assertEqual(c['stages']['parameter_before_seconds']['measured_calls'],1)

    def test_clock_failures_and_backward_or_nonfinite_readings_are_unavailable(self):
        for clock in (RuntimeError('synthetic clock error'),float('nan'),float('inf'),True):
            kwargs={'side_effect':clock} if isinstance(clock,Exception) else {'return_value':clock}
            with patch.object(A.time,'perf_counter',**kwargs):
                result,_,_,timing=A.observed_encode(self.case.enc,['x'],(),{},True)
            self.assertIs(result,self.case.output)
            self.assertTrue(all(timing[k] is None for k in A.TIMING_STAGES))
        with patch.object(A.time,'perf_counter',side_effect=[2,1]):
            _,_,_,timing=A.observed_encode(self.case.enc,['x'],(),{},False)
        self.assertIsNone(timing['encode_seconds'])
        self.assertEqual(self.case.enc.encode.call_count,5)

    def test_backend_failure_is_propagated_once_and_no_after_snapshot(self):
        error=RuntimeError('synthetic backend failure')
        self.case.enc.encode.side_effect=error
        with self.assertRaises(RuntimeError) as raised:self.case.wrapped().encode(['synthetic source reply'])
        self.assertIs(raised.exception,error)
        self.case.enc.encode.assert_called_once();self.assertEqual(self.case.enc.state_dict.call_count,1)
        self.assertEqual(self.case.packets(),[])

    def test_source_sampling_error_does_not_suppress_existing_encode(self):
        class UnhashableText(str):
            def __hash__(self): raise ValueError('synthetic observer lookup failure')
        output=self.case.wrapped().encode([UnhashableText('synthetic source reply')])
        self.assertIs(output,self.case.output)
        self.case.enc.encode.assert_called_once()
        self.case.enc.state_dict.assert_not_called()
        self.assertEqual(self.case.packets(),[])

    def test_unsampled_feature_calls_do_not_invent_zero_hashing_time(self):
        enc=A.FeatureEncoder(self.case.enc)
        enc.encode(['first']);enc.encode(['second'])
        call=enc.records['second']['call']
        self.assertIsNone(call['timing']['parameter_before_seconds'])
        self.assertIsNone(call['timing']['parameter_after_seconds'])
        self.assertGreaterEqual(call['timing']['encode_seconds'],0)
        self.assertEqual(self.case.enc.state_dict.call_count,2)
        self.assertEqual(self.case.enc.encode.call_count,2)

    def test_legacy_receipts_remain_valid_and_unmeasured(self):
        p=self.packet();p['encoding_observation'].pop('timing')
        self.assertEqual(self.case.validate(p['encoding_observation']),'observed_equal')
        c=self.cost([p]);self.assertEqual(c['legacy_calls'],1);self.assertEqual(c['timed_calls'],0)
        for stage in c['stages'].values():
            self.assertEqual(stage['measured_calls'],0);self.assertEqual(stage['unavailable_calls'],1)

    def test_invalid_timing_is_rejected_instead_of_printed(self):
        original=self.packet()['encoding_observation']
        for value in (None,False,{},dict(original['timing'],extra='private-sentinel')):
            bad=copy.deepcopy(original);bad['timing']=value
            with self.assertRaises(ValueError):self.case.validate(bad)
        for value in (True,-1,float('nan'),float('inf'),86401,'private-sentinel'):
            bad=copy.deepcopy(original);bad['timing']['encode_seconds']=value
            with self.assertRaises(ValueError):self.case.validate(bad)

    def test_multiple_outputs_and_source_references_count_call_cost_once(self):
        one=self.packet();two=copy.deepcopy(one)
        two['emb']=[4.,3.];two['encoding_observation']['raw_vector_sha256']=J.fingerprint(two['emb'])
        one['source_refs']*=3
        c=self.cost([one,two])
        self.assertEqual(c['observations'],2);self.assertEqual(c['calls'],1)
        self.assertEqual(c['stages']['encode_seconds']['total_seconds'],3)
        self.assertEqual(c['parameter_snapshots']['total_bytes'],16)

    def test_conflicting_timing_or_snapshot_copies_exclude_entire_call(self):
        one=self.packet()
        for mutation in ('timing','snapshot','legacy','settings'):
            two=copy.deepcopy(one)
            if mutation=='timing':two['encoding_observation']['timing']['encode_seconds']=4
            elif mutation=='legacy':two['encoding_observation'].pop('timing')
            elif mutation=='settings':two['encoding_observation']['settings_sha256']='b'*64
            else:
                for k in ('parameter_before','parameter_after'):two['encoding_observation'][k]['bytes']=4
            c=self.cost([one,two]);self.assertEqual(c['conflicting_calls'],1)
            self.assertEqual(c['timed_calls'],0);self.assertEqual(c['legacy_calls'],0)
            self.assertEqual(c['parameter_snapshots']['observed'],0)
            for stage in c['stages'].values():self.assertEqual(stage['measured_calls'],0)

    def test_missing_call_identity_is_not_counted_as_a_new_call(self):
        p=self.packet();p.pop('encoding_observation')
        c=self.cost([p]);self.assertEqual(c['calls'],0);self.assertEqual(c['unidentified_observations'],1)

    def test_forecast_batch_links_and_audit_copy_share_same_cost_identity(self):
        p=self.packet();call=copy.deepcopy(p['encoding_observation']);call['schema']='forecast-encoding-observation-v1'
        ref=dict(transform='normalized_exchange_his_first_400_codepoints',encoder_input_sha256=p['encoder_input_sha256'],
                 encoder_input_chars=p['encoder_input_chars'],emb=[.6,.8],
                 encoding_link=dict(schema='readout-encoding-link-v1',transform='readout_units_v1',raw_emb=p['emb'],call=call))
        # Use the matching normalized representation of this fixture's [3,4] vector.
        forecast=dict(schema='self-forecast-artifacts-v1',artifacts=dict(checkpoint=p['checkpoint'],recent_own_embeddings=[ref,ref]))
        c=self.cost([p,forecast]);self.assertEqual(c['observations'],3);self.assertEqual(c['calls'],1)

    def test_aggregate_validation_refuses_labels_and_nonconserved_totals(self):
        good=self.cost([self.packet()])
        for key,value in [('calls',2),('timed_calls',False),('scope','private-sentinel'),('observations',0),('extra','private-sentinel')]:
            bad=copy.deepcopy(good);bad[key]=value
            with self.assertRaises(ValueError):J.validate_encoder_call_cost(bad,1)
        for key,value in [('measured_calls',2),('unavailable_calls',1),('total_seconds',0),('max_seconds',float('inf'))]:
            bad=copy.deepcopy(good);bad['stages']['encode_seconds'][key]=value
            with self.assertRaises(ValueError):J.validate_encoder_call_cost(bad,1)
        bad=copy.deepcopy(good);bad['parameter_snapshots']['total_bytes']=100
        with self.assertRaises(ValueError):J.validate_encoder_call_cost(bad,1)

    def test_real_join_and_report_publish_only_aggregates_with_legacy_notice(self):
        from test_witness_artifact_join import Tests as Fixture
        from test_witness_review_report import M
        case=Fixture('test_actual_audit_packet_binds_exact_full_reply_without_scoring')
        case.setUp();self.addCleanup(case.doCleanups)
        sources,admitted,p,_=case.make()
        summary,_=J.join_artifacts(admitted,sources,case.nodes,[p,p],1000)
        c=summary['encoder_call_cost'];self.assertEqual(c['calls'],1)
        self.assertEqual(c['observations'],1)
        rendered='\n'.join(M.artifact_coverage(summary,1))
        self.assertIn('Retained encoder calls: 1',rendered)
        for secret in (p['encoding_observation']['invocation'],p['encoder_input_sha256'],'synthetic source reply'):
            self.assertNotIn(secret,rendered);self.assertNotIn(secret,json.dumps(c))
        self.assertEqual(summary['admission_effect'],'none');self.assertEqual(summary['encoder_identity'],'unverified')
        summary.pop('encoder_call_cost')
        self.assertIn('call-cost coverage is unavailable','\n'.join(M.artifact_coverage(summary,1)))

if __name__=='__main__':unittest.main()

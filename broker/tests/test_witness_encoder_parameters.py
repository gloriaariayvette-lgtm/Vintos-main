#!/usr/bin/env python3
"""Loaded parameter observations use synthetic CPU arrays only; no model loads/sends."""
import copy
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import witness_self_artifacts as A
import witness_capture as W
import test_witness_self_artifacts as fixture

class Tests(unittest.TestCase):
    def setUp(self):
        self.case=fixture.Tests('test_audit_retains_existing_output_without_extra_encoding')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.assertNotIn('.vintos',self.case.root.parts)
        self.weights={'synthetic-weight':np.array([1.,2.],dtype='float32')}
        self.output=np.array([[3.,4.]])
        self.enc=types.SimpleNamespace(state_dict=Mock(side_effect=lambda:self.weights),encode=Mock(return_value=self.output))

    def wrapped(self):return A.audit_encoder(self.enc,self.case.ledger(),self.case.manifest())
    def packets(self):return self.case.packets('self-audit-embedding-')
    def receipt(self):
        self.wrapped().encode(['synthetic source reply'],show_progress_bar=False)
        return self.packets()[0]['encoding_observation']
    def validate(self,r):return A.validate_encoding_observation(r,W.digest('synthetic source reply'),[3.,4.])

    def test_parameter_hash_has_stable_order_and_no_parameter_names_or_values(self):
        self.weights['second']=np.array([4],dtype='int64')
        first=A.parameter_snapshot(self.enc)
        self.weights=dict(reversed(list(self.weights.items())))
        self.assertEqual(first,A.parameter_snapshot(self.enc))
        self.assertEqual(first['bytes'],16);self.assertEqual(first['tensors'],2)
        self.assertNotIn('synthetic-weight',json.dumps(first))
        self.enc.encode.assert_not_called()

    def test_parameter_bytes_shape_and_dtype_change_digest(self):
        before=A.parameter_snapshot(self.enc)
        for value in (np.array([2.,1.],dtype='float32'),np.array([[1.,2.]],dtype='float32'),np.array([1.,2.],dtype='float64')):
            self.weights['synthetic-weight']=value
            self.assertNotEqual(before['sha256'],A.parameter_snapshot(self.enc)['sha256'])

    def test_noncontiguous_cpu_views_have_same_logical_digest_without_mutation(self):
        value=np.arange(8,dtype='float32')[::2];value.flags.writeable=False
        self.weights={'synthetic-weight':value};before=A.parameter_snapshot(self.enc)
        self.weights={'synthetic-weight':value.copy()}
        self.assertEqual(before,A.parameter_snapshot(self.enc))
        self.assertFalse(value.flags.writeable)

    def test_limits_and_unsupported_state_are_unavailable(self):
        with patch.object(A,'MAX_ENCODER_STATE_BYTES',4):self.assertEqual(A.parameter_snapshot(self.enc)['state'],'unavailable')
        with patch.object(A,'MAX_ENCODER_TENSORS',0):self.assertEqual(A.parameter_snapshot(self.enc)['state'],'unavailable')
        for state in ({}, {'object':np.array([object()])},{'other':'private-sentinel'}):
            self.weights=state;self.assertEqual(A.parameter_snapshot(self.enc)['state'],'unavailable')
        self.enc.state_dict.side_effect=RuntimeError('synthetic unavailable')
        self.assertEqual(A.parameter_snapshot(self.enc)['state'],'unavailable')

    def test_non_cpu_tensor_is_rejected_before_any_transfer_or_copy(self):
        class Tensor:
            device=types.SimpleNamespace(type='cuda')
            detach=Mock(side_effect=AssertionError('must not touch device'))
        fake=types.SimpleNamespace(Tensor=Tensor,strided='strided')
        self.weights={'synthetic-weight':Tensor()}
        with patch.dict(sys.modules,torch=fake):
            self.assertEqual(A.parameter_snapshot(self.enc)['state'],'unavailable')
        Tensor.detach.assert_not_called()

    def test_actual_encoding_output_and_call_count_unchanged_with_bounded_snapshots(self):
        wrapped=self.wrapped()
        self.assertIs(wrapped.encode(['synthetic source reply'],show_progress_bar=False),self.output)
        self.assertEqual(self.enc.state_dict.call_count,2)
        self.assertEqual(self.enc.encode.call_count,1)
        observed=self.packets()[0]['encoding_observation']
        self.assertEqual(self.validate(observed),'observed_equal')
        self.assertEqual(observed['encoder_identity'],'unverified')
        for _ in range(3):wrapped.encode(['synthetic source reply'],show_progress_bar=False)
        self.assertEqual(self.enc.state_dict.call_count,2)
        self.assertEqual(self.enc.encode.call_count,4)
        self.assertEqual(len(self.packets()),2)
        self.assertEqual({p['encoding_observation']['parameter_state'] for p in self.packets()},{'unavailable','observed_equal'})

    def test_non_source_encoding_does_not_spend_parameter_budget(self):
        wrapped=self.wrapped();wrapped.encode(['synthetic unrelated text'])
        self.enc.state_dict.assert_not_called()
        wrapped.encode(['synthetic source reply'])
        self.assertEqual(self.enc.state_dict.call_count,2)

    def test_mutation_during_existing_call_is_observed_without_changing_return(self):
        def encode(*args,**kwargs):
            self.weights['synthetic-weight'][0]+=1
            return self.output
        self.enc.encode.side_effect=encode
        self.assertEqual(self.validate(self.receipt()),'observed_changed')
        self.assertEqual(self.enc.encode.call_count,1)

    def test_snapshot_hook_failure_never_retries_or_changes_encoding(self):
        with patch.object(A,'parameter_snapshot',side_effect=RuntimeError('synthetic observer error')):
            self.assertIs(self.wrapped().encode(['synthetic source reply']),self.output)
        self.assertEqual(self.enc.encode.call_count,1)
        self.assertEqual(self.packets()[0]['encoding_observation']['parameter_state'],'unavailable')

    def test_parameter_matching_does_not_infer_settings_or_encoder_identity(self):
        self.wrapped().encode(['synthetic source reply'],custom=object())
        obs=self.packets()[0]['encoding_observation']
        self.assertIsNone(obs['settings_sha256'])
        self.assertEqual(self.validate(obs),'observed_equal')
        self.assertIsNone(self.packets()[0]['encoder_id'])

    def test_forged_binding_and_comparison_rejected(self):
        valid=self.receipt()
        for key,value in [('input_sha256','a'*64),('raw_vector_sha256','b'*64),('parameter_state','observed_changed'),('encoder_identity','verified'),('settings_sha256',False),('invocation','private-id')]:
            bad=copy.deepcopy(valid);bad[key]=value
            with self.assertRaises(ValueError):self.validate(bad)
        for key,value in [('bytes',True),('tensors',-1),('sha256',None)]:
            bad=copy.deepcopy(valid);bad['parameter_before'][key]=value
            with self.assertRaises(ValueError):self.validate(bad)
        self.assertEqual(A.validate_encoding_observation(None,'a'*64,[1.,0.]),'missing')

    def test_offline_report_keeps_parameter_counts_separate_from_identity(self):
        from test_witness_artifact_join import Tests as JoinFixture
        from test_witness_review_report import M
        import witness_artifact_join as J
        case=JoinFixture('test_actual_audit_packet_binds_exact_full_reply_without_scoring')
        case.setUp()
        try:
            sources,admitted,packet,_=case.make()
            section,_=J.join_artifacts(admitted,sources,case.nodes,[packet],1000)
            self.assertEqual(section['encoder_parameter_observation_states'],{'unavailable':1})
            rendered='\n'.join(M.artifact_coverage(section,1))
            self.assertIn('Encoder parameter observation unavailable: 1',rendered)
            self.assertNotIn(packet['encoding_observation']['invocation'],rendered)
            self.assertEqual(section['encoder_identity'],'unverified')
            section['encoder_parameter_observation_states']={'private-label':1}
            with self.assertRaises(ValueError):M.artifact_coverage(section,1)
        finally:case.doCleanups()

if __name__=='__main__':unittest.main()

#!/usr/bin/env python3
"""Synthetic checkpoint evidence only: no files outside isolated scratch or sends."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import witness_self_artifacts as A
import witness_artifact_join as J
import test_witness_artifact_join as fixtures
from test_witness_review_report import M

class Tests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.Tests('test_actual_audit_packet_binds_exact_full_reply_without_scoring')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.assertNotIn('.vintos',self.case.root.parts)
        self.assertIsInstance(self.case.sender,Mock)
        self.sources,self.admitted,self.packet,_=self.case.make()

    def summary(self,packets):
        summary,details=J.join_artifacts(self.admitted,self.sources,self.case.nodes,packets,1000)
        c=summary['checkpoint_consistency']
        J.validate_checkpoint_consistency(c,summary['unique_packets'])
        return summary,details

    def test_producer_shape_is_observed_fields_not_verified_training(self):
        fields=A.checkpoint_observed_fields(self.packet['checkpoint'])
        self.assertIsNone(fields['trained_at']);self.assertIsNone(fields['encoder_id'])
        self.assertEqual(fields['training_completion_evidence'],'unobserved')
        self.assertNotIn('availability',fields);self.assertNotIn('checkpoint_id',fields)
        summary,_=self.summary([self.packet])
        c=summary['checkpoint_consistency']
        self.assertEqual(c['states']['consistent_observed_fields'],1)
        self.assertEqual(c['lineage'],'unverified');self.assertEqual(c['scoring_effect'],'none')
        self.assertEqual(summary['bound_unique_replies'],1)

    def test_same_bytes_different_read_clocks_are_not_metadata_conflicts(self):
        one=copy.deepcopy(self.packet);two=copy.deepcopy(one)
        for packet,start in ((one,100.),(two,110.)):
            packet['checkpoint']['availability']=A.availability_receipt(dict(
                read_started_at=start,parsed_at=start+1,monotonic_elapsed=1.,stage='metadata_loaded'))
        summary,_=self.summary([one,two])
        self.assertEqual(summary['checkpoint_consistency']['states']['consistent_observed_fields'],1)
        self.assertEqual(summary['checkpoint_consistency']['manifest_copies'],2)
        self.assertEqual(summary['checkpoint_availability_states'],{'audit_snapshot_observed':2})

    def test_different_metadata_for_same_hash_remains_visible(self):
        for field,value in (('byte_count',30),('metadata_sha256','b'*64),('source','synthetic-other'),
                             ('mode','self_ahead'),('reported_trained_at','synthetic-date'),
                             ('reported_encoder_label','private-label')):
            two=copy.deepcopy(self.packet);two['checkpoint'][field]=value
            summary,_=self.summary([self.packet,two])
            self.assertEqual(summary['checkpoint_consistency']['states']['conflicting_observations'],1,field)
            self.assertEqual(summary['scoring_effect'],'none')
            self.assertEqual(summary['bound_unique_replies'],1)  # Content binding is a separate question.

    def test_distinct_checkpoints_are_not_compared_as_one_identity(self):
        two=copy.deepcopy(self.packet)
        two['checkpoint']['checkpoint_id']='b'*64;two['checkpoint']['mode']='self_ahead'
        c=self.summary([self.packet,two])[0]['checkpoint_consistency']
        self.assertEqual(c['checkpoint_groups'],2)
        self.assertEqual(c['states']['consistent_observed_fields'],2)

    def test_legacy_manifest_is_unknown_and_does_not_hide_observed_conflict(self):
        legacy=copy.deepcopy(self.packet);legacy['checkpoint']={'checkpoint_id':self.packet['checkpoint']['checkpoint_id']}
        c=self.summary([legacy])[0]['checkpoint_consistency']
        self.assertEqual(c['states']['legacy_only'],1)
        c=self.summary([self.packet,legacy])[0]['checkpoint_consistency']
        self.assertEqual(c['states']['incomplete_observations'],1)
        other=copy.deepcopy(self.packet);other['checkpoint']['metadata_sha256']='b'*64
        c=self.summary([self.packet,other,legacy])[0]['checkpoint_consistency']
        self.assertEqual(c['states']['conflicting_observations'],1)
        self.assertEqual(c['legacy_manifests'],1)

    def test_older_observation_without_availability_keeps_field_comparison(self):
        old=copy.deepcopy(self.packet);old['checkpoint'].pop('availability')
        c=self.summary([self.packet,old])[0]['checkpoint_consistency']
        self.assertEqual(c['states']['consistent_observed_fields'],1)
        self.assertEqual(c['observed_manifests'],2)

    def test_forged_training_or_identity_upgrade_is_rejected(self):
        for key,value in (('trained_at',10),('encoder_id','private-id'),('weights_retained',True),
                          ('training_completion_evidence','verified'),('encoder_weights_identity','verified')):
            bad=copy.deepcopy(self.packet);bad['checkpoint'][key]=value
            for packets in ([bad,self.packet],[self.packet,bad]):
                with self.assertRaises(ValueError):self.summary(packets)

    def test_malformed_versioned_observations_do_not_disappear_behind_good_copy(self):
        for key,value in (('schema','unknown'),('byte_count',True),('byte_count',0),
                          ('byte_count',A.MAX_CHECKPOINT+1),('metadata_sha256',None),('mode','other'),
                          ('source',False),('reported_trained_at','x'*257),('extra','private-sentinel'),
                          ('availability',None),('availability',{'state':'observed'})):
            bad=copy.deepcopy(self.packet);bad['checkpoint'][key]=value
            with self.assertRaises(ValueError):self.summary([self.packet,bad])

    def test_duplicate_packets_and_source_refs_do_not_multiply_manifests(self):
        packet=copy.deepcopy(self.packet);packet['source_refs']*=3
        summary,_=self.summary([packet,copy.deepcopy(packet)])
        c=summary['checkpoint_consistency']
        self.assertEqual(summary['source_references'],3)
        self.assertEqual(c['manifest_copies'],1);self.assertEqual(c['checkpoint_groups'],1)

    def test_forecast_and_audit_manifests_share_checkpoint_group(self):
        manifest=copy.deepcopy(self.packet['checkpoint'])
        forecast={'schema':'self-forecast-artifacts-v1','artifacts':{'checkpoint':manifest}}
        c=J.checkpoint_consistency([self.packet,forecast]);J.validate_checkpoint_consistency(c,2)
        self.assertEqual(c['checkpoint_groups'],1);self.assertEqual(c['observed_manifests'],2)
        manifest['metadata_sha256']='b'*64
        c=J.checkpoint_consistency([self.packet,forecast])
        self.assertEqual(c['states']['conflicting_observations'],1)

    def test_fixed_report_omits_private_fields_and_marks_old_reports_unavailable(self):
        packet=copy.deepcopy(self.packet);packet['checkpoint']['reported_encoder_label']='private-label'
        summary,_=self.summary([packet])
        rendered='\n'.join(M.artifact_coverage(summary,1))
        self.assertIn('consistent_observed_fields: 1',rendered)
        for secret in ('private-label',packet['checkpoint']['checkpoint_id'],packet['checkpoint']['metadata_sha256']):
            self.assertNotIn(secret,rendered)
            self.assertNotIn(secret,json.dumps(summary['checkpoint_consistency']))
        summary.pop('checkpoint_consistency')
        self.assertIn('field-consistency coverage is unavailable','\n'.join(M.artifact_coverage(summary,1)))

    def test_aggregate_validates_conservation_and_rejects_arbitrary_labels(self):
        summary,_=self.summary([self.packet]);original=summary['checkpoint_consistency']
        for key,value in (('scope','private-label'),('lineage','verified'),('manifest_copies',2),
                          ('checkpoint_groups',False),('observed_manifests',0),('legacy_manifests',1),('extra',1)):
            bad=copy.deepcopy(original);bad[key]=value
            with self.assertRaises(ValueError):J.validate_checkpoint_consistency(bad,1)
        for states in ({'private-label':1},dict(original['states'],conflicting_observations=1),
                       dict.fromkeys(J.CHECKPOINT_CONSISTENCY_STATES,0)):
            bad=copy.deepcopy(original);bad['states']=states
            with self.assertRaises(ValueError):J.validate_checkpoint_consistency(bad,1)
        empty=J.checkpoint_consistency([]);J.validate_checkpoint_consistency(empty,0)

    def test_order_and_input_immutability(self):
        other=copy.deepcopy(self.packet);other['checkpoint']['metadata_sha256']='b'*64
        packets=[self.packet,other];before=copy.deepcopy(packets)
        self.assertEqual(self.summary(packets)[0],self.summary(list(reversed(packets)))[0])
        self.assertEqual(packets,before)

if __name__=='__main__':unittest.main()

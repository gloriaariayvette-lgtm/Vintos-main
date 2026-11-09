#!/usr/bin/env python3
"""Observed parameter availability clocks; synthetic checkpoints and no model calls."""
import copy
import json
import sys
import unittest
from unittest.mock import patch

from test_witness_self_artifacts import Tests as Artifacts, R, A, W
import witness_artifact_join as J


class Tests(unittest.TestCase):
    def setUp(self):
        self.case=Artifacts('test_load_hashes_the_same_checkpoint_bytes_it_parses')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.assertNotIn('.vintos',self.case.root.parts)
        self.assertTrue(hasattr(self.case.case.sender,'assert_not_called'))

    def observed(self,**kw):
        return A.availability_receipt(dict(dict(read_started_at=100.,parsed_at=102.,monotonic_elapsed=2.,stage="parameters_loaded"),**kw))

    def packet(self):
        fc={'ts':110.,'arrived_at':99.,'mode':'on_message',
            'self':{'mode':'on_message','checkpoint_id':'a'*64}}
        p={'schema':'self-forecast-artifacts-v1','forecast_row_sha256':J.fingerprint(fc),
           'forecast_at':110.,'arrived_at':99.,
           'artifacts':{'checkpoint':{'checkpoint_id':'a'*64,'availability':self.observed()}}}
        return p,fc

    def test_actual_load_retains_parse_completion_not_training_time(self):
        with patch.object(A.time,'time',side_effect=[100.,102.]),patch.object(A.time,'monotonic',side_effect=[10.,12.]):
            model=R.load(self.case.path,retain=True)
        manifest=model['_witness_checkpoint']
        self.assertEqual(manifest['availability'],self.observed())
        self.assertEqual(manifest['availability']['parameters_available_by'],102.)
        self.assertIsNone(manifest['trained_at'])
        self.assertIsNone(manifest['encoder_id'])
        self.case.case.enc.encode.assert_not_called()

    def test_ordinary_load_does_not_invoke_observer_clock(self):
        with patch.object(A,'begin_checkpoint_read',side_effect=AssertionError('capture disabled')):
            model=R.load(self.case.path)
        self.assertNotIn('_witness_checkpoint',model)

    def test_backward_and_forward_wall_jumps_never_supply_availability(self):
        for parsed in (99.,120.):
            observed=self.observed(parsed_at=parsed)
            self.assertEqual(observed['state'],'clock_discontinuity')
            self.assertIsNone(observed['parameters_available_by'])
            self.assertEqual(A.availability_receipt(observed),observed)

    def test_invalid_clock_values_and_claimed_states_do_not_become_observed(self):
        for key,value in [('parsed_at',True),('parsed_at',float('nan')),('read_started_at',-1),
                          ('monotonic_elapsed',-1),('monotonic_elapsed',601)]:
            self.assertEqual(self.observed(**{key:value})['state'],'unobserved')
        for key,value in [('parameters_available_by',True),('parameters_available_by',101.),('state','ready')]:
            wrong=self.observed();wrong[key]=value
            self.assertEqual(A.availability_receipt(wrong)['state'],'unobserved')
        self.assertEqual(A.availability_receipt(None)['state'],'unobserved')

    def test_failed_clock_read_cannot_change_normal_checkpoint_load(self):
        with patch.object(A,'begin_checkpoint_read',side_effect=RuntimeError('synthetic clock failure')):
            model=R.load(self.case.path,retain=True)
        self.assertEqual(model['meta'],self.case.meta)
        self.assertNotIn('_witness_checkpoint',model)
        with patch.object(A,'finish_checkpoint_read',side_effect=RuntimeError('synthetic clock failure')):
            model=R.load(self.case.path,retain=True)
        self.assertEqual(model['meta'],self.case.meta)

    def test_manifest_revalidates_observation_and_does_not_backfill_old_files(self):
        observed=self.observed()
        m=A.checkpoint(self.case.path.read_bytes(),self.case.meta,observed)
        self.assertEqual(m['availability'],observed)
        old=A.checkpoint(self.case.path.read_bytes(),self.case.meta)
        self.assertEqual(old['availability']['state'],'unobserved')
        self.assertIsNone(old['trained_at'])

    def test_timing_audit_requires_exact_row_checkpoint_and_matching_clocks(self):
        p,f=self.packet()
        self.assertEqual(J.checkpoint_availability([p],[f],1000),{'parsed_by_logged_forecast':1})
        changed=copy.deepcopy(f);changed['extra']='another logged row'
        self.assertEqual(J.checkpoint_availability([p],[changed],1000),{'exact_forecast_row_missing':1})
        changed=copy.deepcopy(p);changed['artifacts']['checkpoint']['checkpoint_id']='b'*64
        self.assertEqual(J.checkpoint_availability([changed],[f],1000),{'forecast_identity_mismatch':1})
        changed=copy.deepcopy(p);changed['forecast_at']=111.
        self.assertEqual(J.checkpoint_availability([changed],[f],1000),{'forecast_clock_mismatch':1})

    def test_timing_audit_keeps_late_and_outside_cutoff_separate(self):
        p,f=self.packet()
        p['artifacts']['checkpoint']['availability']=self.observed(read_started_at=111.,parsed_at=113.)
        self.assertEqual(J.checkpoint_availability([p],[f],1000),{'parsed_after_logged_forecast':1})
        self.assertEqual(J.checkpoint_availability([p],[f],110),{'forecast_outside_cutoff':1})

    def test_audit_observation_is_not_a_prospective_forecast(self):
        p,f=self.packet()
        p={'schema':'self-audit-embedding-v1','checkpoint':p['artifacts']['checkpoint']}
        self.assertEqual(J.checkpoint_availability([p],[f],1000),{'audit_snapshot_observed':1})
        p['checkpoint']['availability']=self.observed(parsed_at=99.)
        self.assertEqual(J.checkpoint_availability([p],[f],1000),{'clock_discontinuity':1})

    def test_metadata_only_read_never_claims_parameters_loaded(self):
        p,f=self.packet()
        observed=self.observed(stage='metadata_loaded')
        self.assertEqual(observed['bytes_observed_by'],102.)
        self.assertIsNone(observed['parameters_available_by'])
        self.assertEqual(A.availability_receipt(observed),observed)
        p['artifacts']['checkpoint']['availability']=observed
        self.assertEqual(J.checkpoint_availability([p],[f],1000),{'parameters_not_loaded':1})

    def test_formatter_validates_timing_denominators_without_private_clock_output(self):
        from test_witness_review_report import M
        section={'scope':'content_binding_only','admission_effect':'none','scoring_effect':'none',
                 'encoder_identity':'unverified','artifact_observation_time':'unverified',
                 'forecast_target_selection':'not_evaluated','packets_supplied':1,'unique_packets':1,
                 'source_references':1,'bound_unique_replies':0,'states':{'missing_source_observation':1},
                 'checkpoint_availability_states':{'parsed_by_logged_forecast':1}}
        rendered='\n'.join(M.artifact_coverage(section,0))
        self.assertIn('parsed_by_logged_forecast: 1 packets',rendered)
        self.assertIn('do not supply a training date',rendered)
        for counts in ({'parsed_by_logged_forecast':2},{'private unknown reason':1}):
            bad=dict(section,checkpoint_availability_states=counts)
            with self.assertRaises(ValueError):M.artifact_coverage(bad,0)

    def test_actual_forecast_packet_carries_load_receipt_without_changing_row(self):
        with patch.dict('os.environ',JUDGES_CAPTURE_SCRATCH='',JUDGES_CAPTURE_CONFIG=''):
            off=self.case.case.job()
        on=self.case.case.job()
        self.assertEqual(on,off)
        packet,=self.case.packets()
        self.assertEqual(packet['artifacts']['checkpoint']['availability']['state'],'observed')
        self.assertEqual(packet['forecast_row_sha256'],W._fingerprint(on))
        self.assertEqual(on,json.loads(self.case.case.output.read_text().splitlines()[-1]))


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    sys.exit(not result.wasSuccessful())

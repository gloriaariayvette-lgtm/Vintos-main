#!/usr/bin/env python3
"""Fitting receipts use synthetic arrays, a private scratch store and stubbed encoders."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import witness_self_artifacts as A
import witness_capture as W
import witness_sink as S
import jepa_readout as R
import test_witness_encoder_parameters as P


class Tests(unittest.TestCase):
    def setUp(self):
        self.case=P.Tests('test_parameter_hash_has_stable_order_and_no_parameter_names_or_values')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.root=self.case.case.root
        self.assertNotIn('.vintos',self.root.parts)
        self.assertEqual(os.environ['SPARK_WORKSPACE'],str(self.root))
        self.assertIsInstance(self.case.enc.encode,Mock)
        self.rows=[{'target':'synthetic private text '+str(i),'day':'2026-10-01'} for i in range(12)]
        self.features=[np.arange(24,dtype=float).reshape(12,2)]
        self.targets=np.ones((12,2))
        self.indices=[np.arange(i,i+3) for i in range(0,12,3)]
        self.parameters={'W':np.array([[1.,2.],[3.,4.]]),'beta':.5}
        self.meta={'schema':'anchored-readout-v1','mode':'self_ahead','selected':'synthetic'}
        self.path=self.root/'self_ahead.npz'
        # Success cases require ordered observation times, not the host wall clock.
        self.clock=Mock(wraps=A.time)
        self.clock.time=Mock(return_value=1800000000.)
        fixed=patch.object(A,'time',self.clock)
        fixed.start();self.addCleanup(fixed.stop)

    def begin(self):return A.begin_fit('self_ahead',self.rows,self.features,self.targets,self.indices)
    def prepared(self):return A.prepare_fit(self.begin(),self.meta,self.parameters)
    def save(self):np.savez_compressed(self.path,meta=json.dumps(self.meta),**self.parameters)
    def packets(self):
        files=list(self.root.glob('self-fit-completion-*.json'))
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in files))
        return [json.loads(p.read_text()) for p in files]

    def test_exact_saved_checkpoint_and_inputs_bound_without_private_values(self):
        scope=self.prepared();self.save();self.assertTrue(A.publish_fit(scope,self.path))
        packet,=self.packets()
        self.assertEqual(packet['checkpoint_id'],hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual([packet['blocks'][k]['rows'] for k in A.FIT_BLOCKS],[3]*4)
        self.assertLessEqual(packet['fit_started_at'],packet['parameters_ready_at'])
        self.assertLessEqual(packet['parameters_ready_at'],packet['checkpoint_observed_at'])
        self.assertFalse(packet['upstream_complete']);self.assertEqual(packet['encoder_identity'],'unverified')
        self.assertEqual(packet['scoring_effect'],'none')
        for value in ('synthetic private text',str(self.root),'"W"','synthetic'):
            self.assertNotIn(value,json.dumps(packet))
        self.case.enc.encode.assert_not_called()

    def test_test_only_changes_do_not_change_training_partition_digest(self):
        before=self.begin()
        self.rows[-1]['target']='different synthetic test target';self.targets[-1]=[2.,3.]
        after=self.begin()
        for key in ('train','validation','calibration'):
            self.assertEqual(before['blocks'][key],after['blocks'][key])
        self.assertNotEqual(before['blocks']['test'],after['blocks']['test'])

    def test_row_order_and_feature_changes_are_observed(self):
        before=self.begin()
        self.rows[0],self.rows[1]=self.rows[1],self.rows[0]
        self.assertNotEqual(before['blocks']['train']['ordered_rows_sha256'],self.begin()['blocks']['train']['ordered_rows_sha256'])
        self.features[0][0,0]=99
        self.assertNotEqual(before['blocks']['train']['arrays_sha256'],self.begin()['blocks']['train']['arrays_sha256'])

    def test_invalid_partitions_and_input_arrays_are_rejected(self):
        self.indices[1]=self.indices[0]
        with self.assertRaises(ValueError):self.begin()
        self.indices=[np.arange(i,i+3) for i in range(0,12,3)]
        self.targets[0,0]=np.nan
        with self.assertRaises(ValueError):self.begin()
        self.targets=np.ones((11,2))
        with self.assertRaises(ValueError):self.begin()

    def test_parameter_dtype_shape_and_value_are_bound(self):
        scope=self.prepared()
        for value in (np.array([[1.,2.],[3.,5.]]),np.array([1.,2.,3.,4.]),np.array([[1.,2.],[3.,4.]],dtype='float32')):
            self.parameters['W']=value;self.save()
            with self.assertRaises(ValueError):A.publish_fit(scope,self.path)
        self.assertEqual(self.packets(),[])

    def test_changed_metadata_and_pickle_payload_are_not_accepted(self):
        scope=self.prepared();self.meta['selected']='changed';self.save()
        with self.assertRaises(ValueError):A.publish_fit(scope,self.path)
        self.meta['selected']='synthetic';self.parameters['W']=np.array([object()]);self.save()
        with self.assertRaises(ValueError):A.publish_fit(scope,self.path)
        self.assertEqual(self.packets(),[])

    def test_checkpoint_symlink_and_size_bound_are_rejected(self):
        scope=self.prepared();self.save();link=self.root/'link.npz';link.symlink_to(self.path)
        with self.assertRaises(OSError):A.publish_fit(scope,link)
        with patch.object(A,'MAX_CHECKPOINT',16):
            with self.assertRaises(ValueError):A.publish_fit(scope,self.path)
        self.assertEqual(self.packets(),[])

    def test_invalid_clocks_and_disabled_capture_never_publish(self):
        scope=self.prepared();self.save()
        for value in (float('nan'),float('inf'),False,scope['parameters_ready_at']+100):
            bad=dict(scope,fit_started_at=value)
            with self.assertRaises(ValueError):A.publish_fit(bad,self.path)
        with patch.object(W,'_capture_location',return_value=None):self.assertIsNone(self.begin())
        with patch.object(W,'_private_root',side_effect=ValueError('synthetic disabled')):
            with self.assertRaises(ValueError):A.publish_fit(scope,self.path)
        self.assertEqual(self.packets(),[])

    def test_other_head_never_enters_observer(self):
        with patch.object(A,'begin_fit') as begin:
            self.assertIsNone(R._self_fit_witness('gloria','begin_fit','gloria',None,None,None,None))
        begin.assert_not_called()
        self.assertIsNone(A.begin_fit('gloria',None,None,None,None))

    def test_capture_off_bypasses_observer_and_failures_are_passive(self):
        with patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH='',JUDGES_CAPTURE_CONFIG=''),patch.object(A,'begin_fit') as begin:
            self.assertIsNone(R._self_fit_witness('self_ahead','begin_fit'))
        begin.assert_not_called()
        with patch.object(A,'begin_fit',side_effect=RuntimeError('synthetic failure')):
            self.assertIsNone(R._self_fit_witness('self_ahead','begin_fit'))

    def test_configured_sink_accepts_new_type_without_raw_paths(self):
        import test_witness_sink as fixture
        case=fixture.Tests('test_unconfigured_disabled_and_malformed_are_inert')
        case.setUp();self.addCleanup(case.doCleanups)
        scope=self.prepared();self.save()
        self.assertTrue(A.publish_fit(scope,self.path))
        files=list(case.sink.glob('self-fit-completion-*.json'))
        self.assertEqual(len(files),1);self.assertEqual(files[0].stat().st_mode & 0o777,0o600)
        self.assertNotIn('root',json.loads(files[0].read_text()))
        self.assertEqual(case.status()['counts']['written'],1)
        case.settings['enabled']=False;case.write_config()
        with self.assertRaises(ValueError):A.publish_fit(scope,self.path)
        self.assertEqual(len(list(case.sink.glob('self-fit-completion-*.json'))),1)

    def training_rows(self):
        rows=[]
        for block,day in enumerate(('2026-09-28','2026-10-05','2026-10-10','2026-10-18')):
            for i in range(4):
                n=block*4+i
                rows.append(dict(own=['synthetic reply '+str(n)],other=['synthetic other '+str(n)],
                    now='synthetic current '+str(n),at=float(1000+n*1000),target='synthetic target '+str(n),day=day))
        return rows

    def encoder(self):
        return type('SyntheticEncoder',(),{'encode':Mock(side_effect=lambda texts,**kwargs:
            np.asarray([np.random.default_rng(int(hashlib.sha256(t.encode()).hexdigest()[:8],16)).normal(size=4) for t in texts]))})()

    def test_actual_fitter_off_on_same_report_parameters_and_encoder_call_count(self):
        out1=self.root/'off';out2=self.root/'on';out1.mkdir();out2.mkdir()
        rows=self.training_rows();one,two=self.encoder(),self.encoder()
        with patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH='',JUDGES_CAPTURE_CONFIG=''):
            first=R.train_mode(rows,R.Embeddings(one),'self_ahead',out1,steps=1)
        second=R.train_mode(rows,R.Embeddings(two),'self_ahead',out2,steps=1)
        self.assertEqual(first,second);self.assertEqual(one.encode.call_count,two.encode.call_count)
        a=R.load(out1/'self_ahead.npz');b=R.load(out2/'self_ahead.npz')
        for key in ('projection','W','bias','beta','gamma','confidence_W'):np.testing.assert_array_equal(a[key],b[key])
        packet,=self.packets()
        self.assertEqual(packet['checkpoint_id'],hashlib.sha256((out2/'self_ahead.npz').read_bytes()).hexdigest())

    def test_backward_observation_clock_is_explicitly_rejected(self):
        for clocks in ([1800000000.,1799999997.2,1799999998.2],
                       [1800000000.,1800000001.,1799999998.2]):
            with self.subTest(clocks=clocks):
                self.clock.time.side_effect=clocks
                scope=self.prepared();self.save()
                with self.assertRaisesRegex(ValueError,'unusable fitting observation clocks'):
                    A.publish_fit(scope,self.path)
                self.assertEqual(self.packets(),[])

    def test_backward_wall_step_drops_receipt_but_preserves_actual_fit(self):
        rows=self.training_rows();baseline=self.encoder()
        out=self.root/'baseline';out.mkdir()
        with patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH='',JUDGES_CAPTURE_CONFIG=''):
            expected=R.train_mode(rows,R.Embeddings(baseline),'self_ahead',out,steps=1)
        saved=R.load(out/'self_ahead.npz')
        for n,clocks in enumerate(([1800000000.,1799999997.2,1799999998.2],
                                   [1800000000.,1800000001.,1799999998.2])):
            with self.subTest(boundary=n):
                self.clock.time.side_effect=clocks
                other=self.encoder();target=self.root/('rollback-'+str(n));target.mkdir()
                report=R.train_mode(rows,R.Embeddings(other),'self_ahead',target,steps=1)
                self.assertEqual(report,expected)
                self.assertEqual(other.encode.call_count,baseline.encode.call_count)
                actual=R.load(target/'self_ahead.npz')
                for key in ('projection','W','bias','beta','gamma','confidence_W'):
                    np.testing.assert_array_equal(actual[key],saved[key])
                self.assertEqual(self.packets(),[])

    def test_save_failure_preserves_exception_and_cannot_publish_completion(self):
        error=OSError('synthetic save failure')
        with patch.object(R.np,'savez_compressed',side_effect=error),patch.object(A,'publish_fit') as publish:
            with self.assertRaises(OSError) as raised:
                R.train_mode(self.training_rows(),R.Embeddings(self.encoder()),'self_ahead',self.root,steps=1)
        self.assertIs(raised.exception,error);publish.assert_not_called();self.assertEqual(self.packets(),[])

    def test_observer_failure_at_each_boundary_cannot_fail_actual_fit(self):
        for name in ('begin_fit','prepare_fit','publish_fit'):
            with self.subTest(name=name),patch.object(A,name,side_effect=RuntimeError('synthetic observer failure')):
                report=R.train_mode(self.training_rows(),R.Embeddings(self.encoder()),'self_on_message',self.root,steps=1)
            self.assertEqual(report['mode'],'self_on_message')
            self.assertIsNotNone(R.load(self.root/'self_on_message.npz'))
        self.assertEqual(self.packets(),[])


if __name__=='__main__':unittest.main()

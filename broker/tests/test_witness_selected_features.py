#!/usr/bin/env python3
"""Synthetic selected-input receipts; no external calls, stores or real encoders."""
import copy
import json
import os
import unittest
from unittest.mock import Mock, patch
import numpy as np
import test_witness_self_artifacts as F
import witness_artifact_join as J

A,R,W=F.A,F.R,F.W


class Tests(unittest.TestCase):
    def setUp(self):
        self.case=F.Tests('test_actual_job_off_on_identical_with_no_additional_encoder_calls')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.assertNotIn('.vintos',self.case.root.parts)
        self.assertIsInstance(self.case.case.enc.encode,Mock)
        self.assertIsInstance(self.case.case.sender,Mock)

    def packet(self):
        self.case.case.job()
        packet,=self.case.packets()
        return packet

    def test_actual_selected_texts_and_consumed_arrays_are_bound(self):
        actual=[]
        original=R.predict
        def predict(model,arrays):
            actual.append([x[0].tolist() for x in arrays])
            return original(model,arrays)
        with patch.object(R,'predict',side_effect=predict):p=self.packet()
        f=p['artifacts']['feature_inputs'];selection=f['selection']
        exs=self.case.case.exs
        self.assertEqual(selection['own'],[{'sha256':F.digest(e['his'][:400]),'chars':len(e['his'][:400])} for e in exs[-6:]])
        self.assertEqual(selection['other'],[{'sha256':F.digest(e['her'][:400]),'chars':len(e['her'][:400])} for e in exs[-6:]])
        self.assertEqual(selection['now'],{'sha256':F.digest('synthetic arrival'),'chars':17})
        self.assertEqual(f['exchange_at'],170.)
        self.assertEqual([x['values_sha256'] for x in f['features']],[W._fingerprint(x) for x in actual[0]])
        self.assertEqual([x['role'] for x in f['features']],list(A.FEATURE_ROLES))
        self.assertFalse(f['values_retained']);self.assertFalse(f['upstream_complete'])
        self.assertEqual(len(list(J.claims(p))),6)
        public=json.dumps(f)
        for secret in ('synthetic arrival','private synthetic reply','synthetic other','fixture-turn',str(self.case.root)):
            self.assertNotIn(secret,public)

    def test_capture_off_on_preserves_rows_and_calls(self):
        with patch.dict(os.environ,JUDGES_CAPTURE_CONFIG='',JUDGES_CAPTURE_SCRATCH=''):
            with patch.object(A,'selected_feature_inputs',side_effect=AssertionError('capture off')) as helper:
                off=self.case.case.job();helper.assert_not_called()
        calls=self.case.case.enc.encode.call_count
        on=self.case.case.job()
        self.assertEqual(on,off);self.assertEqual(self.case.case.enc.encode.call_count,2*calls)
        self.assertIn('feature_inputs',self.case.packets()[0]['artifacts'])

    def test_roles_order_duplicates_prefix_and_future_cut_are_preserved(self):
        exs=self.case.case.exs
        exs[-2]['her']=exs[-1]['her']='x'*420
        exs.append(dict(exs[-1],at=205.,ts='205',her='future synthetic request',his='future synthetic reply'))
        f=self.packet()['artifacts']['feature_inputs']
        self.assertEqual(f['selection']['other'][-2:],[{'sha256':F.digest('x'*400),'chars':400}]*2)
        self.assertEqual(len(f['selection']['other']),6)
        self.assertNotIn(F.digest('future synthetic request'),json.dumps(f))
        self.assertEqual(f['exchange_at'],170.)

    def test_empty_counterpart_inputs_have_zero_features(self):
        for e in self.case.case.exs:e['her']=''
        f=self.packet()['artifacts']['feature_inputs']
        self.assertEqual(f['selection']['other'],[])
        zero=W._fingerprint([0.,0.])
        self.assertEqual([x['values_sha256'] for x in f['features'][2:4]],[zero,zero])

    def test_failed_new_observation_keeps_existing_artifacts(self):
        with patch.object(A,'selected_feature_inputs',side_effect=ValueError('synthetic observation failure')):
            p=self.packet()
        self.assertNotIn('feature_inputs',p['artifacts'])
        self.assertEqual(len(list(J.claims(p))),6)
        self.assertEqual(len(self.case.case.output.read_text().splitlines()),1)

    def test_reader_rejects_malformed_optional_and_own_vector_mismatch(self):
        p=self.packet()
        for mutate in (
            lambda f:f.update(upstream_complete=True),
            lambda f:f.update(values_retained=0),
            lambda f:f.update(private_text='synthetic'),
            lambda f:f['selection'].update(now={'sha256':'bad','chars':1}),
            lambda f:f['selection']['own'].reverse(),
            lambda f:f['features'][0].update(values_sha256='0'*64),
            lambda f:f['features'][0].update(dimensions=True),
            lambda f:[x.update(dimensions=3) for x in f['features'][:5]],
            lambda f:f['features'][-1].update(dimensions=4),
            lambda f:f.update(exchange_at=float('nan')),
        ):
            bad=copy.deepcopy(p);mutate(bad['artifacts']['feature_inputs'])
            with self.assertRaises(ValueError):list(J.claims(bad))
        legacy=copy.deepcopy(p);del legacy['artifacts']['feature_inputs']
        self.assertEqual(len(list(J.claims(legacy))),6)
        bad=copy.deepcopy(p);bad['artifacts']['feature_inputs']=None
        with self.assertRaises(ValueError):list(J.claims(bad))

    def test_maximum_supported_dimensions_keep_a_bounded_hash_only_receipt(self):
        selected={'own':['a'*400]*6,'other':['b'*400]*6,'now':'c'*400,'at':100.}
        arrays=[np.zeros((1,8192)) for _ in range(5)]+[np.zeros((1,3))]
        receipt=A.selected_feature_inputs(selected,arrays)
        A.validate_selected_feature_inputs(receipt)
        self.assertLess(len(json.dumps(receipt)),4096)
        self.assertEqual(sum(f['dimensions'] for f in receipt['features']),40963)
        self.case.case.enc.encode.assert_not_called()

    def test_producer_refuses_unbounded_nonfinite_and_wrong_dimensions(self):
        selected={'own':['synthetic'],'other':[],'now':'','at':100.}
        arrays=[np.zeros((1,2)) for _ in range(5)]+[np.zeros((1,3))]
        f=A.selected_feature_inputs(selected,arrays)
        self.assertIsNone(f['selection']['now'])
        for index,value in ((0,np.zeros((1,8193))),(0,np.zeros((2,2))),(1,np.zeros((1,3))),
                            (2,np.array([[np.nan,0]])),(3,[[True,False]]),(5,np.zeros((1,4)))):
            bad=list(arrays);bad[index]=value
            with self.assertRaises(ValueError):A.selected_feature_inputs(selected,bad)
        for role,value in (('own',[]),('own',['synthetic']*7),('now','x'*401),('other',[1])):
            with self.assertRaises(ValueError):A.selected_feature_inputs(dict(selected,**{role:value}),arrays)
        self.case.case.enc.encode.assert_not_called()


if __name__=='__main__':unittest.main()

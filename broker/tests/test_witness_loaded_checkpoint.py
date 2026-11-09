#!/usr/bin/env python3
"""Synthetic checkpoint replacement races; scratch stores and stubbed encodes/sends."""
import hashlib
import io
import json
import os
import sys
import unittest
from unittest.mock import Mock, patch
import numpy as np
import test_witness_self_artifacts as F

R=F.R


class Tests(unittest.TestCase):
    def setUp(self):
        self.case=F.Tests('test_load_hashes_the_same_checkpoint_bytes_it_parses')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.path=self.case.path
        self.assertNotIn('.vintos',self.path.parts)
        self.assertIsInstance(self.case.case.enc.encode,Mock)
        self.assertIsInstance(self.case.case.sender,Mock)

    def forecast(self,mode='self_on_message'):
        return R.forecast(self.case.case.enc,mode,exs=self.case.case.exs,
                          her='synthetic arrival',now=200.,model_dir=self.case.case.models)

    def replace_on_predict(self,remove=False):
        original=R.predict
        def predict(model,inputs):
            result=original(model,inputs)
            if remove:self.path.unlink()
            else:
                # Simulate a normal atomic checkpoint publisher with valid new bytes.
                with np.load(io.BytesIO(self.path.read_bytes()),allow_pickle=False) as saved:
                    replacement={k:saved[k] for k in saved.files}
                replacement['W']=replacement['W']+0.25
                target=self.path.with_name('replacement.npz')
                np.savez_compressed(target,**replacement)
                os.replace(target,self.path)
            return result
        return patch.object(R,'predict',side_effect=predict)

    def test_self_forecast_identity_uses_loaded_bytes_with_capture_off_and_on(self):
        for capture in (False,True):
            self.case.write_model();before=self.path.read_bytes()
            settings={'JUDGES_CAPTURE_CONFIG':'','JUDGES_CAPTURE_SCRATCH':str(self.case.root) if capture else ''}
            with patch.dict(os.environ,settings):
                initial_calls=self.case.case.enc.encode.call_count
                baseline=self.forecast()
                calls=self.case.case.enc.encode.call_count
                with self.replace_on_predict():changed=self.forecast()
            self.assertEqual(changed['checkpoint_id'],hashlib.sha256(before).hexdigest())
            self.assertNotEqual(changed['checkpoint_id'],hashlib.sha256(self.path.read_bytes()).hexdigest())
            self.assertTrue(np.array_equal(changed['emb'],baseline['emb']))
            self.assertEqual(changed['confidence'],baseline['confidence'])
            self.assertEqual(self.case.case.enc.encode.call_count-calls,calls-initial_calls)

    def test_self_ahead_uses_loaded_identity_too(self):
        self.case.meta['mode']='self_ahead'
        self.case.path=self.case.case.models/'self_ahead.npz';self.path=self.case.path
        self.case.write_model();before=self.path.read_bytes()
        with self.replace_on_predict():result=self.forecast('self_ahead')
        self.assertEqual(result['checkpoint_id'],hashlib.sha256(before).hexdigest())

    def test_removal_after_parse_does_not_require_a_second_file_read(self):
        before=self.path.read_bytes()
        with self.replace_on_predict(remove=True):result=self.forecast()
        self.assertEqual(result['checkpoint_id'],hashlib.sha256(before).hexdigest())
        self.assertFalse(self.path.exists())

    def test_actual_job_keeps_matching_artifact_after_checkpoint_replacement(self):
        before=self.path.read_bytes()
        with self.replace_on_predict():row=self.case.case.job()
        self.assertIsNotNone(row)
        packets=self.case.packets();self.assertEqual(len(packets),1)
        checkpoint=packets[0]['artifacts']['checkpoint']
        self.assertEqual(checkpoint['checkpoint_id'],hashlib.sha256(before).hexdigest())
        self.assertEqual(checkpoint['checkpoint_id'],row['self']['checkpoint_id'])

    def test_bound_load_hashes_the_buffer_it_parses_even_if_path_changes(self):
        before=self.path.read_bytes();original=R.np.load
        def load(source,**kwargs):
            self.assertIsInstance(source,io.BytesIO)
            self.path.write_bytes(b'synthetic replacement before parsing')
            return original(source,**kwargs)
        with patch.object(R.np,'load',side_effect=load):
            model=R.load(self.path,retain=True,bind_identity=True)
        self.assertEqual(model['_loaded_checkpoint_id'],hashlib.sha256(before).hexdigest())
        self.assertEqual(model['_witness_checkpoint']['checkpoint_id'],model['_loaded_checkpoint_id'])
        self.assertEqual(model['meta'],self.case.meta)

    def test_unbound_loader_contract_and_other_head_are_unchanged(self):
        self.assertNotIn('_loaded_checkpoint_id',R.load(self.path))
        self.assertNotIn('_loaded_checkpoint_id',R.load(self.path,retain=True))
        self.case.meta['mode']='gloria'
        self.case.path=self.case.case.models/'gloria.npz';self.path=self.case.path
        self.case.write_model();original=R.load
        with patch.object(R,'load',wraps=original) as load:
            self.forecast('gloria')
        load.assert_called_once_with(self.path)

    def test_capture_off_needs_no_observer_and_retention_limit_does_not_change_identity(self):
        expected=hashlib.sha256(self.path.read_bytes()).hexdigest()
        with patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH='',JUDGES_CAPTURE_CONFIG=''):
            with patch.dict(sys.modules,witness_self_artifacts=None):
                result=self.forecast()
        self.assertEqual(result['checkpoint_id'],expected)
        self.assertEqual(self.case.packets(),[])
        with patch.object(F.A,'MAX_CHECKPOINT',2):
            model=R.load(self.path,retain=True,bind_identity=True)
        self.assertEqual(model['_loaded_checkpoint_id'],expected)
        self.assertIsNone(model.get('_witness_checkpoint'))

    def test_bound_load_preserves_invalid_checkpoint_and_wrong_mode_errors(self):
        self.path.write_bytes(b'synthetic corrupt archive')
        with self.assertRaises(ValueError):R.load(self.path,bind_identity=True)
        self.case.meta['mode']='self_ahead';self.case.write_model()
        with self.assertRaisesRegex(ValueError,'different head or mode'):self.forecast()


if __name__=='__main__':unittest.main()

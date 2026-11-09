#!/usr/bin/env python3
"""Stored encoder fields only: synthetic objects, isolated sink, stubbed encoding."""
import copy
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import witness_self_artifacts as A
import witness_artifact_join as J
import witness_capture as W
import test_witness_encoder_parameters as P


class Tests(unittest.TestCase):
    def setUp(self):
        self.case = P.Tests('test_parameter_hash_has_stable_order_and_no_parameter_names_or_values')
        self.case.setUp(); self.addCleanup(self.case.doCleanups)
        self.assertNotIn('.vintos', self.case.case.root.parts)
        self.assertIsInstance(self.case.enc.encode, Mock)
        self.enc = self.case.enc
        self.enc.training = False
        self.enc.truncate_dim = None
        self.enc.prompts = {'query': 'synthetic private prompt sentinel'}
        self.tokenizer = types.SimpleNamespace(model_max_length=512, padding_side='right',
            truncation_side='right', init_kwargs={'synthetic': True},
            get_vocab=Mock(side_effect=AssertionError('no vocabulary calls')),
            encode=Mock(side_effect=AssertionError('no tokenizer calls')))
        self.config = types.SimpleNamespace(hidden_size=2, hidden_act='synthetic_activation')
        self.layer = types.SimpleNamespace(max_seq_length=512, tokenizer=self.tokenizer,
            _modules={'auto_model': types.SimpleNamespace(config=self.config, training=False)})
        self.enc._modules = {'0': self.layer}

    def receipt(self):
        self.case.wrapped().encode(['synthetic source reply'])
        return self.case.packets()[-1]['encoding_observation']

    def test_settings_are_hashed_without_values_names_or_methods(self):
        snap = A.runtime_snapshot(self.enc)
        self.assertEqual(snap['state'], 'observed')
        self.assertEqual((snap['modules'],snap['configs'],snap['tokenizers'],snap['tokenizer_settings']), (3,1,1,1))
        serialized = json.dumps(snap)
        for private in ('synthetic private prompt sentinel','synthetic_activation','padding_side','auto_model'):
            self.assertNotIn(private, serialized)
        self.tokenizer.get_vocab.assert_not_called(); self.tokenizer.encode.assert_not_called()
        self.enc.encode.assert_not_called(); self.enc.state_dict.assert_not_called()

    def test_each_stored_setting_changes_digest_with_identical_parameters(self):
        for obj,field,value in ((self.enc,'training',True),(self.layer,'max_seq_length',128),
                               (self.tokenizer,'padding_side','left'),(self.config,'hidden_size',3),
                               (self.enc,'prompts',{'query':'different synthetic prompt'})):
            with self.subTest(field=field):
                before = A.runtime_snapshot(self.enc)
                old = getattr(obj,field); setattr(obj,field,value)
                self.assertNotEqual(before['sha256'], A.runtime_snapshot(self.enc)['sha256'])
                setattr(obj,field,old)

    def test_child_order_matters_but_dictionary_field_order_does_not(self):
        self.enc._modules['1'] = types.SimpleNamespace(training=False)
        first = A.runtime_snapshot(self.enc)
        reordered = dict(reversed(list(self.config.__dict__.items())))
        self.config.__dict__.clear(); self.config.__dict__.update(reordered)
        self.assertEqual(first,A.runtime_snapshot(self.enc))
        self.enc._modules = dict(reversed(list(self.enc._modules.items())))
        self.assertNotEqual(first['sha256'],A.runtime_snapshot(self.enc)['sha256'])

    def test_loaded_versions_observed_without_import_or_raw_version_retention(self):
        package = types.SimpleNamespace(__version__='synthetic-version-a')
        with patch.dict(sys.modules,transformers=package):
            first = A.runtime_snapshot(self.enc)
            package.__version__='synthetic-version-b'
            second = A.runtime_snapshot(self.enc)
        self.assertNotEqual(first['sha256'],second['sha256'])
        self.assertNotIn('synthetic-version',json.dumps(first))

    def test_dynamic_attributes_and_config_methods_are_never_called(self):
        class Dynamic:
            def __getattr__(self,name): raise AssertionError('no dynamic attribute reads')
            @property
            def max_seq_length(self): raise AssertionError('no property reads')
            def to_dict(self): raise AssertionError('no config methods')
        snap = A.runtime_snapshot(Dynamic())
        self.assertEqual(snap['state'],'observed')
        self.assertEqual(snap['module_settings'],0)
        self.assertEqual(snap['configs'],0)

    def test_bounds_cycles_and_nonfinite_values_do_not_escape(self):
        for value in ('x'*65537, {'x':float('nan')}, list(range(1025))):
            self.enc.prompts=value
            snap = A.runtime_snapshot(self.enc)
            if isinstance(value,str): self.assertEqual(snap['state'],'unavailable')
            else: self.assertEqual(snap['module_settings'],2)
        cycle=[]; cycle.append(cycle); self.enc.prompts=cycle
        self.assertEqual(A.runtime_snapshot(self.enc)['state'],'unavailable')
        self.enc.prompts={}; self.enc._modules={str(n):types.SimpleNamespace() for n in range(65)}
        self.assertEqual(A.runtime_snapshot(self.enc)['state'],'unavailable')

    def test_tokenizer_content_and_deep_leaves_remain_unobserved(self):
        first = A.runtime_snapshot(self.enc)
        self.tokenizer.backend_tokenizer=object()
        self.tokenizer.vocab={'synthetic_new_token':42}
        self.enc._modules['0']._modules['auto_model']._modules={'leaf':types.SimpleNamespace(training=False)}
        second = A.runtime_snapshot(self.enc)
        self.enc._modules['0']._modules['auto_model']._modules['leaf'].training=True
        self.assertEqual(second,A.runtime_snapshot(self.enc))
        del self.enc._modules['0']._modules['auto_model']._modules
        self.assertEqual(first,A.runtime_snapshot(self.enc))

    def test_capture_off_keeps_original_encoder_and_makes_no_observations(self):
        with patch.object(W,'_capture_location',return_value=None), patch.object(A,'runtime_snapshot') as observer:
            self.assertIs(self.case.wrapped(),self.enc)
        observer.assert_not_called()

    def test_before_after_change_preserves_exact_output_and_one_call(self):
        def encode(*args,**kwargs):
            self.layer.max_seq_length=128
            return self.case.output
        self.enc.encode.side_effect=encode
        wrapped=A.FeatureEncoder(self.enc)
        self.assertIs(wrapped.encode(['synthetic input']),self.case.output)
        call=wrapped.records['synthetic input']['call']
        self.assertEqual(call['runtime']['state'],'observed_changed')
        self.assertEqual(call['parameter_state'],'observed_equal')
        self.assertEqual(call['encoder_identity'],'unverified')
        self.enc.encode.assert_called_once_with(['synthetic input'])
        A.validate_encoding_observation(call,W.digest('synthetic input'),[3.,4.],expected_schema='forecast-encoding-observation-v1')

    def test_unsampled_parameter_calls_still_observe_runtime_settings(self):
        wrapped=A.FeatureEncoder(self.enc)
        wrapped.encode(['first']); self.enc.training=True; wrapped.encode(['second'])
        one,two=(wrapped.records[k]['call'] for k in ('first','second'))
        self.assertEqual(two['parameter_state'],'unavailable')
        self.assertEqual(two['runtime']['state'],'observed_equal')
        self.assertNotEqual(one['runtime']['before']['sha256'],two['runtime']['before']['sha256'])
        self.assertEqual(self.enc.state_dict.call_count,2)
        self.assertEqual(self.enc.encode.call_count,2)

    def test_observer_failure_does_not_retry_or_replace_result(self):
        with patch.object(A,'runtime_snapshot',side_effect=RuntimeError('synthetic observer failure')):
            call=self.receipt()
        self.assertNotIn('runtime',call)
        self.enc.encode.assert_called_once()
        self.case.validate(call)

    def test_encode_failure_preserves_exception_and_does_not_observe_after(self):
        error=RuntimeError('synthetic encode failure'); self.enc.encode.side_effect=error
        with patch.object(A,'runtime_snapshot',wraps=A.runtime_snapshot) as observer:
            with self.assertRaises(RuntimeError) as raised:self.receipt()
        self.assertIs(raised.exception,error); self.assertEqual(observer.call_count,1)
        self.enc.encode.assert_called_once(); self.assertEqual(self.case.packets(),[])

    def test_legacy_receipt_accepted_without_runtime_inference(self):
        call=self.receipt(); call.pop('runtime')
        self.assertEqual(self.case.validate(call),'observed_equal')

    def test_malformed_runtime_is_rejected(self):
        original=self.receipt()
        for runtime in (None,{},dict(original['runtime'],extra='synthetic private sentinel'),
                        dict(original['runtime'],state='observed_changed')):
            call=copy.deepcopy(original); call['runtime']=runtime
            with self.assertRaises(ValueError):self.case.validate(call)
        for field,value in (('modules',False),('runtime_versions',6),('tokenizers',64),('sha256','bad')):
            call=copy.deepcopy(original); call['runtime']['before'][field]=value
            with self.assertRaises(ValueError):self.case.validate(call)

    def test_changed_runtime_retained_by_audit_even_when_vectors_repeat(self):
        wrapped=self.case.wrapped()
        # Consume the sampled parameter pair; subsequent calls have the same unavailable pair.
        wrapped.encode(['synthetic source reply']); wrapped.encode(['synthetic source reply'])
        before=len(self.case.packets()); self.layer.max_seq_length=256
        wrapped.encode(['synthetic source reply'])
        self.assertEqual(len(self.case.packets()),before+1)
        wrapped.encode(['synthetic source reply'])
        self.assertEqual(len(self.case.packets()),before+1)

    def test_conflicting_copies_of_same_call_cannot_hide_runtime_changes(self):
        self.receipt(); one=self.case.packets()[0]; two=copy.deepcopy(one)
        self.layer.max_seq_length=256
        for key in ('before','after'):
            two['encoding_observation']['runtime'][key]=A.runtime_snapshot(self.enc)
        costs=J.encoder_call_cost([one,two])
        self.assertEqual(costs['calls'],1); self.assertEqual(costs['conflicting_calls'],1)
        self.assertEqual(costs['timed_calls'],0)


if __name__=='__main__':unittest.main()

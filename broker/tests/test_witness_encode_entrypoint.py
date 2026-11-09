#!/usr/bin/env python3
"""Observe loaded synthetic Python functions only; no source reads, model loads or sends."""
import copy
import json
import types
import unittest
from unittest.mock import Mock, patch
import test_witness_encoder_parameters as P
from test_witness_review_report import M
import witness_artifact_join as J

A=P.A


class Tests(unittest.TestCase):
    def setUp(self):
        self.case=P.Tests('test_parameter_hash_has_stable_order_and_no_parameter_names_or_values')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.assertNotIn('.vintos',self.case.case.root.parts)
        self.assertIsInstance(self.case.enc.encode,Mock)
        self.calls=[];output=self.case.output;calls=self.calls
        def encode(texts,*args,**kwargs):
            calls.append((texts,args,kwargs))
            return output
        self.encode=encode;self.case.enc.encode=encode

    def receipt(self):
        previous={p['encoding_observation']['invocation'] for p in self.case.packets()}
        self.case.wrapped().encode(['synthetic source reply'])
        added=[p['encoding_observation'] for p in self.case.packets()
               if p['encoding_observation']['invocation'] not in previous]
        self.assertEqual(len(added),1)
        return added[0]

    def test_loaded_code_is_hashed_without_source_reads_or_constants_out(self):
        with patch('builtins.open',side_effect=AssertionError('no source reads')):
            snap=A.entrypoint_snapshot(self.encode)
        self.assertEqual(snap['state'],'observed')
        self.assertGreater(snap['observed_bytes'],0)
        self.assertEqual(self.calls,[])
        self.assertNotIn('texts',json.dumps(snap));self.assertNotIn(__file__,json.dumps(snap))

    def test_bytecode_constants_nested_functions_and_python_binding_are_distinct(self):
        def one(texts):return [1]
        def two(texts):return [2]
        def nested(texts):return lambda: 1
        self.assertNotEqual(A.entrypoint_snapshot(one)['sha256'],A.entrypoint_snapshot(two)['sha256'])
        self.assertEqual(A.entrypoint_snapshot(nested)['code_objects'],2)
        self.assertEqual(A.entrypoint_snapshot(one),A.entrypoint_snapshot(types.MethodType(one,object())))

    def test_filename_and_line_locations_do_not_change_code_fingerprint(self):
        moved=types.FunctionType(self.encode.__code__.replace(co_filename='/synthetic/private/location',co_firstlineno=987),
                                 self.encode.__globals__,closure=self.encode.__closure__)
        self.assertEqual(A.entrypoint_snapshot(self.encode),A.entrypoint_snapshot(moved))

    def test_defaults_globals_and_closure_contents_are_explicitly_not_claimed(self):
        namespace={'value':1};exec('def f(texts, value=1): return value',namespace)
        f=namespace['f'];before=A.entrypoint_snapshot(f)
        f.__defaults__=(2,);namespace['value']=3
        self.assertEqual(before,A.entrypoint_snapshot(f))
        self.assertIn('defaults_closures_helpers_or_native_code',A.ENTRYPOINT_SCOPE)

    def test_native_callable_objects_and_oversized_constants_are_unavailable(self):
        for call in (len,Mock(),object()):
            self.assertEqual(A.entrypoint_snapshot(call)['state'],'unavailable')
        code=self.encode.__code__
        for constant in ('x'*(1024*1024+1),object(),10**2000):
            fn=types.FunctionType(code.replace(co_consts=(constant,)),self.encode.__globals__,closure=self.encode.__closure__)
            self.assertEqual(A.entrypoint_snapshot(fn)['state'],'unavailable')

    def test_encode_attribute_is_resolved_once_and_original_result_is_returned(self):
        encode=self.encode;weights=self.case.weights
        class Encoder:
            reads=0
            def state_dict(self):return weights
            @property
            def encode(self):self.reads+=1;return encode
        enc=Encoder();wrapper=A.FeatureEncoder(enc)
        result=wrapper.encode(['synthetic text'],show_progress_bar=False)
        self.assertIs(result,self.case.output);self.assertEqual(enc.reads,1);self.assertEqual(len(self.calls),1)
        call=wrapper.records['synthetic text']['call']
        self.assertEqual(call['entrypoint']['state'],'observed_equal')
        self.assertEqual(call['encoder_identity'],'unverified')

    def test_code_mutation_during_call_is_observed_without_retry(self):
        ns={'output':self.case.output,'calls':[]}
        exec('def initial(texts):\n calls.append(1)\n initial.__code__=replacement.__code__\n return output\ndef replacement(texts):\n return output',ns)
        self.case.enc.encode=ns['initial']
        call=self.receipt()
        self.assertEqual(ns['calls'],[1]);self.assertEqual(call['entrypoint']['state'],'observed_changed')
        self.case.validate(call)

    def test_encode_failure_is_the_original_exception_with_no_after_snapshot(self):
        error=RuntimeError('synthetic encode failure')
        def failing(texts):self.calls.append(1);raise error
        self.case.enc.encode=failing
        with patch.object(A,'entrypoint_snapshot',wraps=A.entrypoint_snapshot) as observer:
            with self.assertRaises(RuntimeError) as raised:self.receipt()
        self.assertIs(raised.exception,error);self.assertEqual(self.calls,[1]);self.assertEqual(observer.call_count,1)
        self.assertEqual(self.case.packets(),[])

    def test_observer_failure_leaves_output_and_other_observations_intact(self):
        with patch.object(A,'entrypoint_snapshot',side_effect=RuntimeError('synthetic observer failure')):
            call=self.receipt()
        self.assertNotIn('entrypoint',call);self.assertEqual(len(self.calls),1)
        self.assertIn('runtime',call);self.case.validate(call)

    def test_legacy_and_unavailable_entrypoints_do_not_become_code_identity(self):
        call=self.receipt();call.pop('entrypoint');self.case.validate(call)
        self.case.enc.encode=Mock(return_value=self.case.output)
        call=self.receipt();self.assertEqual(call['entrypoint']['state'],'unavailable')
        self.case.enc.encode.assert_called_once();self.case.validate(call)

    def test_bad_entrypoint_shapes_and_counts_are_rejected(self):
        original=self.receipt()
        for value in (None,{},dict(original['entrypoint'],state='observed_changed'),dict(original['entrypoint'],extra='private-sentinel')):
            bad=copy.deepcopy(original);bad['entrypoint']=value
            with self.assertRaises(ValueError):self.case.validate(bad)
        for key,value in (('sha256','bad'),('code_objects',False),('observed_bytes',1024*1024+1)):
            bad=copy.deepcopy(original);bad['entrypoint']['before'][key]=value
            with self.assertRaises(ValueError):self.case.validate(bad)

    def test_code_changes_survive_audit_dedup_when_vectors_stay_identical(self):
        wrapped=self.case.wrapped();wrapped.encode(['synthetic source reply']);wrapped.encode(['synthetic source reply'])
        n=len(self.case.packets());output=self.case.output
        def different(texts,*args,**kwargs):return output
        self.case.enc.encode=different;wrapped.encode(['synthetic source reply'])
        self.assertEqual(len(self.case.packets()),n+1)
        wrapped.encode(['synthetic source reply']);self.assertEqual(len(self.case.packets()),n+1)

    def test_same_invocation_conflict_is_excluded_from_cost_totals(self):
        self.receipt();one=self.case.packets()[0];two=copy.deepcopy(one)
        def other(texts):return [1,2]
        snap=A.entrypoint_snapshot(other)
        two['encoding_observation']['entrypoint'].update(before=snap,after=snap)
        counts=J.encoder_call_cost([one,two])
        self.assertEqual(counts['conflicting_calls'],1);self.assertEqual(counts['timed_calls'],0)

    def test_offline_reader_compares_only_partial_code_and_public_counts(self):
        import test_witness_runtime_comparison as fixture
        code=self.receipt()['entrypoint']
        case=fixture.Tests('test_equal_partial_snapshots_require_distinct_calls')
        case.setUp();self.addCleanup(case.doCleanups)
        for packet in (case.one,case.two):packet['encoding_observation']['entrypoint']=copy.deepcopy(code)
        summary=case.summary([case.one,case.two])
        value=summary['entrypoint_consistency']
        J.validate_entrypoint_consistency(value,2,1)
        self.assertEqual(value['states']['matching_partial_snapshots'],1)
        text='\n'.join(M.artifact_coverage(summary,1))
        self.assertIn('Python encode entrypoint matching_partial_snapshots: 1',text)
        self.assertNotIn(code['before']['sha256'],text)
        other=case.two['encoding_observation']['entrypoint']
        for k in ('before','after'):other[k]['sha256']='d'*64
        self.assertEqual(case.summary([case.one,case.two])['entrypoint_consistency']['states']['different_partial_snapshots'],1)
        case.two['encoding_observation'].pop('entrypoint')
        self.assertEqual(case.summary([case.one,case.two])['entrypoint_consistency']['states']['incomplete'],1)
        bad=copy.deepcopy(value);bad['scope']='private-sentinel'
        with self.assertRaises(ValueError):J.validate_entrypoint_consistency(bad,2,1)
        summary.pop('entrypoint_consistency')
        self.assertIn('entrypoint comparison is unavailable in this legacy report','\n'.join(M.artifact_coverage(summary,1)))


if __name__=='__main__':unittest.main()

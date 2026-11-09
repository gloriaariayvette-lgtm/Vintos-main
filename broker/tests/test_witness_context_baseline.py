#!/usr/bin/env python3
"""Actual baseline encode receipts and exact saved-row joins on isolated synthetic data."""
import ast
import copy
import json
import os
import sys
import unittest
from unittest.mock import Mock, patch
import numpy as np
import test_witness_self_artifacts as F
import test_witness_review_report as review
import witness_artifact_join as J

A,R,W=F.A,F.R,F.W


class Tests(unittest.TestCase):
    def setUp(self):
        self.case=F.Tests('test_actual_job_off_on_identical_with_no_additional_encoder_calls')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        tree=ast.parse((F.ROOT/'scripts/jepa_predictor.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='format_context')
        ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-context-formatter','exec'),ns)
        p=patch.object(sys.modules['jepa_predictor'],'format_context',ns['format_context'])
        p.start();self.addCleanup(p.stop)
        self.assertNotIn('.vintos',self.case.root.parts)
        self.assertIsInstance(self.case.case.enc.encode,Mock)
        self.assertIsInstance(self.case.case.sender,Mock)

    def pair(self):
        row=self.case.case.job();packet,=self.case.packets();return row,packet

    def states(self,packets,rows,cutoff=1000):
        aggregate,_=J.join_artifacts([],[],{},packets,cutoff,forecasts=rows)
        return aggregate['context_baseline_states']

    def test_existing_encode_inputs_and_outputs_are_exactly_observed(self):
        row,p=self.pair();b=p['artifacts']['context_baseline']
        text=self.case.case.enc.encode.call_args.args[0][0]
        self.assertEqual(b['input_sha256'],F.digest(text));self.assertEqual(b['input_chars'],len(text))
        self.assertEqual([t['role'] for t in b['turns']],['assistant','user','assistant','user','assistant','user'])
        self.assertEqual(b['turns'][-1]['sha256'],F.digest('synthetic arrival'))
        self.assertEqual(b['raw_vector_sha256'],W._fingerprint([1.,2.]))
        self.assertEqual(b['normalized_vector_sha256'],W._fingerprint(row['context_emb']))
        self.assertEqual(b['encoder_identity'],'unobserved');self.assertFalse(b['upstream_complete'])
        self.assertEqual(self.states([p],[row]),{'bound_to_forecast':1})
        self.assertEqual(self.case.case.enc.encode.call_count,2)
        for secret in ('synthetic arrival','private synthetic reply','fixture-turn',str(self.case.root)):
            self.assertNotIn(secret,json.dumps(b))

    def test_capture_off_on_unchanged_rows_calls_and_parameters_scans(self):
        with patch.dict(os.environ,JUDGES_CAPTURE_CONFIG='',JUDGES_CAPTURE_SCRATCH=''):
            with patch.object(A,'context_baseline_receipt',side_effect=AssertionError('capture off')) as helper:
                off=self.case.case.job();helper.assert_not_called()
        with patch.object(A,'parameter_snapshot',wraps=A.parameter_snapshot) as snapshots:
            on=self.case.case.job()
        self.assertEqual(on,off);self.assertEqual(self.case.case.enc.encode.call_count,4)
        self.assertEqual(snapshots.call_count,2)  # Existing feature-call pair only.

    def test_prefixes_preserve_order_repeats_and_actual_rendering(self):
        for e in self.case.case.exs:e['his']='x'*330;e['her']='y'*340
        row,p=self.pair();b=p['artifacts']['context_baseline']
        self.assertEqual([r['chars'] for r in b['turns']],[300]*5+[17])
        self.assertEqual(b['turns'][0],b['turns'][2]);self.assertEqual(b['turns'][2],b['turns'][4])
        self.assertEqual(self.states([p],[row]),{'bound_to_forecast':1})

    def test_observation_failure_or_formatter_change_preserves_existing_artifacts(self):
        with patch.object(A,'context_baseline_receipt',side_effect=ValueError('synthetic failure')):
            row,p=self.pair()
        self.assertNotIn('context_baseline',p['artifacts']);self.assertEqual(self.states([p],[row]),{'unobserved':1})
        for file in self.case.root.glob('self-forecast-artifacts-*.json'):file.unlink()
        with patch.object(sys.modules['jepa_predictor'],'format_context',return_value='different synthetic formatting'):
            _,p=self.pair()
        self.assertNotIn('context_baseline',p['artifacts'])
        self.assertEqual(len(self.case.case.output.read_text().splitlines()),2)

    def test_baseline_encode_exception_propagates_without_retry_or_new_report(self):
        error=RuntimeError('synthetic baseline failure');calls=[]
        def encode(texts,**kwargs):
            calls.append(texts)
            if len(calls)==2:raise error
            return np.array([[1.,2.] for _ in texts])
        self.case.case.enc.encode.side_effect=encode
        with self.assertRaises(RuntimeError) as caught:self.case.case.job()
        self.assertIs(caught.exception,error);self.assertEqual(len(calls),2)
        self.assertEqual(self.case.packets(),[])

    def test_missing_exact_version_and_conflicting_peers_never_bind(self):
        row,p=self.pair()
        changed=copy.deepcopy(row);changed['turn_id']='another-synthetic-turn'
        self.assertEqual(self.states([p],[changed]),{'exact_forecast_row_missing':1})
        other=copy.deepcopy(p);other['artifacts']['context_baseline']['input_sha256']='0'*64
        self.assertEqual(self.states([p,other],[row]),{'conflicting_observations':2})
        self.assertEqual(self.states([p,p],[row]),{'bound_to_forecast':1})

    def test_cutoff_identity_clock_and_vector_disagreements(self):
        row,p=self.pair()
        self.assertEqual(self.states([p],[row],210.),{'outside_cutoff':1})
        for mutation,state in (
            (lambda r:r.update(mode='ahead'),'forecast_identity_mismatch'),
            (lambda r:r['self'].update(checkpoint_id='0'*64),'forecast_identity_mismatch'),
            (lambda r:r.update(ts=220.),'forecast_clock_mismatch'),
            (lambda r:r.update(context_emb=[0.,1.]),'baseline_vector_mismatch'),
            (lambda r:r.pop('context_emb'),'baseline_vector_mismatch')):
            altered=copy.deepcopy(row);mutation(altered);packet=copy.deepcopy(p)
            packet['forecast_row_sha256']=W._fingerprint(altered)
            self.assertEqual(self.states([packet],[altered]),{state:1})

    def test_malformed_present_receipts_rejected_and_legacy_unknown(self):
        row,p=self.pair()
        for mutation in (lambda b:b.update(upstream_complete=True),lambda b:b.update(dimensions=True),
                         lambda b:b.update(input_chars=b['input_chars']+1),lambda b:b.update(extra='private'),
                         lambda b:b['turns'][0].update(role='system'),lambda b:b.update(raw_vector_sha256='bad')):
            bad=copy.deepcopy(p);mutation(bad['artifacts']['context_baseline'])
            with self.assertRaises(ValueError):self.states([bad],[row])
        legacy=copy.deepcopy(p);del legacy['artifacts']['context_baseline']
        self.assertEqual(self.states([legacy],[row]),{'unobserved':1})

    def test_producer_bounds_and_normalization_checks(self):
        turns=[{'role':'user','content':'x'*400}]*6;text=' \n'.join(['x'*300]*6)
        b=A.context_baseline_receipt(turns,text,[3.,4.],[.6,.8])
        self.assertEqual(b['input_chars'],1810);self.assertLess(len(json.dumps(b)),2048)
        for args in ((turns*2,text,[3.,4.],[.6,.8]),(turns,text,[3.,4.],[1.,0.]),
                     (turns,'unknown', [3.,4.],[.6,.8]),(turns,text,[0.,0.],[0.,0.])):
            with self.assertRaises(ValueError):A.context_baseline_receipt(*args)
        self.case.case.enc.encode.assert_not_called()

    def test_aggregate_renderer_uses_fixed_counts_and_exposes_no_private_fields(self):
        row,p=self.pair();result,_=J.join_artifacts([],[],{},[p],1000,forecasts=[row])
        rendered='\n'.join(review.M.artifact_coverage(result,0))
        self.assertIn('bound_to_forecast: 1',rendered)
        for private in ('synthetic arrival',row['turn_id'],p['forecast_row_sha256']):self.assertNotIn(private,rendered)
        for counts in ({'bound_to_forecast':2},{'private label':1},{'bound_to_forecast':True},{'conflicting_observations':1}):
            bad=copy.deepcopy(result);bad['context_baseline_states']=counts
            with self.assertRaises(ValueError):review.M.artifact_coverage(bad,0)
        legacy=copy.deepcopy(result);legacy.pop('context_baseline_states')
        review.M.artifact_coverage(legacy,0)


if __name__=='__main__':unittest.main()

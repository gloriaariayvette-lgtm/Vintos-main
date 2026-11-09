#!/usr/bin/env python3
"""Synthetic producer sidecars to paired offline controls; no sender or encoder."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('input_baseline_fixture', ROOT/'broker/tests/test_judges_witness.py')
F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)
R, W = F.R, F.W
import witness_capture as C


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='self-input-baselines-'); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.sender = Mock(side_effect=AssertionError('external action forbidden'))
        for p in (patch.dict(os.environ, SPARK_WORKSPACE=str(self.root), JUDGES_CAPTURE_SCRATCH=str(self.root)),
                  patch.object(socket.socket, 'connect', self.sender)):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertNotIn('.vintos', self.root.parts)
        a, nodes, _, _, _ = F.fixture('fixture-prior-a',100,110)
        b, _, _, _, _ = F.fixture('fixture-prior-b',120,130)
        t, _, f, e, ck = F.fixture('fixture-target',300,310)
        a['content'] = 'a' * 440; a['witness_receipt']['response_sha256'] = W.digest(a['content'])
        b['content'] = 'short synthetic previous reply'; b['witness_receipt']['response_sha256'] = W.digest(b['content'])
        f['self'].update(context_last_ts=130,confidence=.4,qualification='fixture',coherence=0.)
        self.admitted, self.nodes, self.forecasts, self.targets, self.checkpoints = [a,b,t], nodes, [f], [e], ck
        self.exs = [dict(his=x['content'], at=x['witness_receipt']['finalized_at'], turn_id=x['turn_id']) for x in (a,b)]
        token = C.begin_self_forecast()
        C.observe_self_forecast(self.exs,[x['his'][:400] for x in self.exs],130,dict(f['self'],her_key='fixture-hash'))
        obs = C.end_self_forecast(token)
        f['her_key'] = 'fixture-hash'
        C.publish_self_forecast(obs,f)
        path, = self.root.glob('self-forecast-inputs-*.json')
        self.packet = json.loads(path.read_text())
        self.assertEqual(self.packet['state'],'observed')
        self.config = dict(receipts=[self.packet], embeddings=[
            dict(turn_id=x['turn_id'],response_sha256=W.digest(x['content']),encoder_id='fixture-encoder',
                 encoder_input_sha256=W.digest(x['content'][:400]),transform='final_reply_first_400_codepoints',emb=v)
            for x,v in zip((a,b),([1.,0.],[0.,1.]))],
            blocks=[dict(block_id='fixture-block',declared_at=280,start=290,end=400)])
        for x in self.admitted: self.assertEqual(W.admission(x,self.nodes,500),'eligible')

    def report(self,config=None,cutoff=500,admitted=None,forecasts=None,targets=None):
        admitted = self.admitted if admitted is None else admitted
        forecasts = self.forecasts if forecasts is None else forecasts
        targets = self.targets if targets is None else targets
        scores,details = R.innovation(admitted,forecasts,targets,self.checkpoints)
        return R.self_input_baselines(details,admitted,forecasts,targets,
                                      self.config if config is None else config,cutoff)

    def reason(self, expected, **kw):
        report, details = self.report(**kw)
        self.assertEqual(report['unavailable'],{expected:1})
        self.assertEqual(report['paired_groups'],[])
        self.assertEqual(details[0]['reason'],expected)

    def test_actual_producer_packet_scores_excerpts_against_same_actual(self):
        before = copy.deepcopy((self.admitted,self.forecasts,self.targets,self.config))
        report, rows = self.report()
        pair, = report['paired_groups']
        self.assertEqual(pair['n'],1)
        self.assertAlmostEqual(pair['head_error'],.2)
        self.assertAlmostEqual(pair['last_reply_error'],.4)
        self.assertAlmostEqual(pair['recent_mean_error'],1-1.4/(2**.5))
        self.assertEqual(rows[0]['context_n'],2)
        self.assertEqual(report['admission_effect'],'none')
        self.assertEqual((self.admitted,self.forecasts,self.targets,self.config),before)
        for private in ('fixture-target','fixture-block','fixture-checkpoint','fixture-encoder',self.packet['forecast_row_sha256']):
            self.assertNotIn(private,json.dumps(report))

    def test_full_reply_vectors_cannot_substitute_for_excerpt_vectors(self):
        self.config['embeddings'][0]['encoder_input_sha256'] = W.digest(self.admitted[0]['content'])
        self.reason('missing_or_invalid_input_embedding')

    def test_equal_prediction_or_timing_never_substitutes_forecast_hash(self):
        f = copy.deepcopy(self.forecasts[0]); f['extra_metadata'] = 'different exact row'
        self.reason('missing_exact_forecast_receipt',forecasts=[f])
        self.config['receipts'] = []
        self.reason('missing_exact_forecast_receipt')

    def test_missing_duplicate_or_target_ids_are_never_filled_by_text(self):
        for value in (None,'fixture-prior-a','fixture-target'):
            config = copy.deepcopy(self.config)
            config['receipts'][0]['inputs']['reply_refs'][-1]['observed_turn_id'] = value
            self.reason('missing_duplicate_or_target_input_identity',config=config)

    def test_nonadmitted_or_cross_surface_prior_stays_unavailable(self):
        self.reason('input_reply_not_admitted',admitted=self.admitted[1:])
        admitted = copy.deepcopy(self.admitted)
        admitted[0]['witness_receipt']['surface'] = 'other-synthetic-surface'
        self.reason('input_surface_mismatch',admitted=admitted)

    def test_normalization_and_prefix_mismatch_are_explicit(self):
        config = copy.deepcopy(self.config)
        config['receipts'][0]['inputs']['reply_refs'][0]['normalized_reply_sha256'] = '0'*64
        self.reason('unverified_normalized_reply_version',config=config)
        for field,value in [('encoder_input_sha256','0'*64),('encoder_input_chars',399)]:
            config = copy.deepcopy(self.config)
            config['receipts'][0]['inputs']['reply_refs'][0][field] = value
            self.reason('input_transform_mismatch',config=config)

    def test_duplicate_packets_dedup_conflicts_abort_in_either_order_even_after_cutoff(self):
        config = copy.deepcopy(self.config); config['receipts'] *= 2
        self.assertEqual(self.report(config=config)[0]['paired_groups'][0]['n'],1)
        bad = copy.deepcopy(self.packet); bad['forecast_at'] = 600
        for packets in ([bad,self.packet],[self.packet,bad]):
            config['receipts'] = packets
            with self.assertRaisesRegex(ValueError,'^invalid self-input baseline evidence$'): self.report(config=config)

    def test_boolean_flags_clocks_and_malformed_shapes_abort_generically(self):
        cases=[('complete_forecast_context',0),('observations',True),('forecast_at',False),('inputs',[]),('schema','private-invalid')]
        for field,value in cases:
            config = copy.deepcopy(self.config); config['receipts'][0][field] = value
            with self.assertRaisesRegex(ValueError,'^invalid self-input baseline evidence$'): self.report(config=config)

    def test_missing_legacy_observation_keeps_head_but_no_controls(self):
        self.config['receipts'][0].update(state='unavailable',observations=0,inputs=None)
        self.reason('producer_inputs_unavailable')
        self.assertEqual(len(R.innovation(self.admitted,self.forecasts,self.targets,self.checkpoints)[1]),1)

    def test_future_or_ambiguous_finalization_and_clock_binding(self):
        admitted = copy.deepcopy(self.admitted); admitted[0]['witness_receipt']['finalized_at'] = 131
        self.reason('noncausal_or_ambiguous_input_order',admitted=admitted)
        config = copy.deepcopy(self.config); config['receipts'][0]['inputs']['as_of_exchange_at'] = 140
        self.reason('context_clock_mismatch',config=config)
        config = copy.deepcopy(self.config); config['receipts'][0]['forecast_at'] += 1
        self.reason('forecast_clock_mismatch',config=config)

    def test_incomplete_boundary_and_unregistered_blocks_never_score(self):
        self.reason('missing_complete_declared_block',cutoff=399)
        config = copy.deepcopy(self.config); config['blocks'][0]['end'] = 310
        self.reason('missing_complete_declared_block',config=config)
        config = copy.deepcopy(self.config); config['blocks'] = []
        self.reason('missing_complete_declared_block',config=config)
        self.reason('outside_cutoff',cutoff=310)
        for change in (dict(declared_at=291),dict(start=400),dict(start=False)):
            config = copy.deepcopy(self.config); config['blocks'][0].update(change)
            with self.assertRaises(ValueError): self.report(config=config)

    def test_overlapping_and_conflicting_blocks_abort_without_selection(self):
        for extra in (dict(block_id='second',declared_at=281,start=295,end=410),
                      dict(block_id='fixture-block',declared_at=281,start=290,end=400)):
            config = copy.deepcopy(self.config); config['blocks'].append(extra)
            with self.assertRaises(ValueError): self.report(config=config)
        self.config['blocks'] *= 2
        self.assertEqual(self.report()[0]['paired_groups'][0]['n'],1)

    def test_matching_cache_duplicates_all_validate_and_conflicts_never_win(self):
        for vector in ([True,False],[0.,0.],[float('nan'),0.],[0.,1.],[1.,0.,0.]):
            config = copy.deepcopy(self.config)
            bad = copy.deepcopy(config['embeddings'][0]); bad['emb'] = vector
            config['embeddings'].append(bad)
            self.reason('missing_or_invalid_input_embedding',config=config)
        self.config['embeddings'] *= 2
        self.assertEqual(self.report()[0]['paired_groups'][0]['n'],1)

    def test_wrong_encoder_transform_or_version_stays_unavailable(self):
        for field,value in [('encoder_id','other-encoder'),('transform','full-reply'),('response_sha256','0'*64)]:
            config = copy.deepcopy(self.config); config['embeddings'][0][field] = value
            self.reason('missing_or_invalid_input_embedding',config=config)

    def test_only_existing_selected_earliest_forecast_enters_controls(self):
        later = copy.deepcopy(self.forecasts[0]); later['ts'] += 1
        report, details = self.report(forecasts=self.forecasts+[later])
        self.assertEqual(len(details),1); self.assertEqual(report['paired_groups'][0]['n'],1)
        earlier = copy.deepcopy(self.forecasts[0]); earlier['ts'] -= 1
        self.reason('missing_exact_forecast_receipt',forecasts=[earlier]+self.forecasts)

    def test_cancelling_mean_is_unavailable_not_a_perfect_control(self):
        self.config['embeddings'][1]['emb'] = [-1.,0.]
        self.reason('invalid_control_geometry')

    def test_distinct_checkpoints_are_not_pooled(self):
        second = copy.deepcopy(self.forecasts[0]); second['self']['checkpoint_id'] = 'fixture-checkpoint-two'
        self.checkpoints['fixture-checkpoint-two'] = copy.deepcopy(self.checkpoints['fixture-checkpoint'])
        packet = copy.deepcopy(self.packet); packet['forecast_row_sha256'] = C._fingerprint(second)
        self.config['receipts'].append(packet)
        report, details = self.report(forecasts=self.forecasts+[second])
        self.assertEqual([p['n'] for p in report['paired_groups']],[1,1])
        self.assertEqual(len({p['checkpoint_group'] for p in report['paired_groups']}),2)
        self.assertEqual(len(details),2)

    def test_distinct_blocks_of_one_checkpoint_remain_separate(self):
        row, _, f, e, _ = F.fixture('fixture-second-target',350,360)
        f['self'] = copy.deepcopy(self.forecasts[0]['self'])
        f['her_key'] = 'fixture-hash'
        packet = copy.deepcopy(self.packet)
        packet.update(forecast_row_sha256=C._fingerprint(f),forecast_at=f['ts'],arrived_at=f['arrived_at'])
        self.config['receipts'].append(packet)
        self.config['blocks'][0]['end'] = 330
        self.config['blocks'].append(dict(block_id='fixture-block-two',declared_at=280,start=340,end=400))
        report, details = self.report(admitted=self.admitted+[row],forecasts=self.forecasts+[f],targets=self.targets+[e])
        self.assertEqual([p['n'] for p in report['paired_groups']],[1,1])
        self.assertEqual(len({p['checkpoint_group'] for p in report['paired_groups']}),1)
        self.assertEqual(len({p['evaluation_block'] for p in details}),2)

    def test_reordered_finalized_inputs_do_not_become_a_new_mean(self):
        self.config['receipts'][0]['inputs']['reply_refs'].reverse()
        self.reason('noncausal_or_ambiguous_input_order')

    def test_cli_opt_in_preserves_existing_reports_and_binds_private_output(self):
        reports=[]
        for enabled in (False,True):
            bundle=dict(input_kind='synthetic',sources=[dict(kind='canonical',rows=self.admitted)],
                        lineage=list(self.nodes.values()),forecasts=self.forecasts,embeddings=self.targets,checkpoints=self.checkpoints)
            if enabled: bundle['self_input_controls'] = self.config
            source, output = self.root/('bundle-%s.json'%enabled), self.root/('output-%s'%enabled)
            source.write_text(json.dumps(bundle))
            run=subprocess.run([sys.executable,R.__file__,'--scratch',str(self.root),'--input',str(source),
                                '--output',str(output),'--cutoff','1970-01-01T00:08:20Z'],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            reports.append(json.loads((output/'aggregate.json').read_text()))
            if enabled:
                private=output/'private-self-input-controls.json'
                self.assertEqual(private.stat().st_mode&0o777,0o600)
                manifest=json.loads((output/'private-run.json').read_text())
                self.assertIn(hashlib.sha256(private.read_bytes()).hexdigest(),json.dumps(manifest))
                self.assertEqual(reports[-1]['self_input_baselines']['paired_groups'][0]['n'],1)
            else: self.assertFalse((output/'private-self-input-controls.json').exists())
        reports[1].pop('self_input_baselines')
        self.assertEqual(reports[0],reports[1])


if __name__ == '__main__': unittest.main()

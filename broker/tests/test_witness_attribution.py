#!/usr/bin/env python3
"""Synthetic legacy labels and compute-ledger joins never change strict admission."""
import copy
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

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import witness_attribution as A
import witness_receipts as W
spec=importlib.util.spec_from_file_location('legacy_fixture',ROOT/'broker/tests/test_judges_witness.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)

class Tests(unittest.TestCase):
    def setUp(self):
        self.row=dict(role='assistant',content='Synthetic historical reply',turn_id='fixture-turn',surface='fixture-chat',
                      timestamp=100,served_by='fixture-model')
        self.call=dict(at=99,organ='router:fixture-chat',model='fixture-model',provider='fixture-provider',
                       stage='synthetic-completed-stage',**{'class':'foreground'})
        self.config=dict(surface_callers={'fixture-chat':['router:fixture-chat']},window_seconds=5)
        self.sender=Mock(side_effect=AssertionError('external action forbidden'))
        p=patch.object(socket.socket,'connect',self.sender);p.start();self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called);self.assertIsInstance(self.sender,Mock)

    def run_attribution(self,rows=None,calls=None,cutoff=200):
        return A.attribution([self.row] if rows is None else rows,[self.call] if calls is None else calls,self.config,cutoff)

    def test_recorded_labels_survive_without_new_receipts(self):
        report,details=self.run_attribution(calls=[])
        self.assertEqual(report['tiers']['recorded_label'],1)
        self.assertEqual(details[0]['recorded_label'],'fixture-model')
        self.assertNotEqual(W.admission(self.row,{},200),'eligible')
        self.assertEqual(report['admission_effect'],'none');self.assertEqual(report['training_effect'],'none')

    def test_bounded_nearest_match_and_agreement_are_separate_tier(self):
        before=copy.deepcopy((self.row,self.call,self.config))
        report,details=self.run_attribution()
        self.assertEqual(report['tiers']['ledger_attributed'],1)
        self.assertEqual(report['label_ledger_agreement'],{'agree':1})
        self.assertEqual(details[0]['join'],'nearest_time')
        self.assertEqual(details[0]['ledger_provider'],'fixture-provider')
        self.assertEqual(before,(self.row,self.call,self.config))
        for value in ('fixture-model','fixture-provider','fixture-turn','Synthetic historical reply'):
            self.assertNotIn(value,json.dumps(report))

    def test_explicit_unobserved_model_identity_never_gains_ledger_attribution(self):
        for value in ('configured','unknown',None,False,[],{}):
            self.call['model_identity_evidence']=value
            report,details=self.run_attribution()
            self.assertEqual(report['tiers']['recorded_label'],1)
            self.assertEqual(details[0]['join_state'],'call_model_identity_unobserved')
            self.assertIsNone(details[0]['ledger_model'])
        self.call['model_identity_evidence']='response_metadata'
        report,_=self.run_attribution()
        self.assertEqual(report['tiers']['ledger_attributed'],1)

    def test_provider_id_precedes_nearer_call(self):
        self.row['provider_request_id']='fixture-provider-id'
        self.call.update(provider_request_id='fixture-provider-id',at=50)
        nearest=dict(self.call,provider_request_id='different-id',at=100,model='other-model')
        report,details=self.run_attribution(calls=[nearest,self.call])
        self.assertEqual(details[0]['ledger_model'],'fixture-model')
        self.assertEqual(details[0]['join'],'provider_request_id')

    def test_unmatched_conflicting_or_malformed_id_never_falls_back_to_time(self):
        for value in ('unmatched',True,[], ''):
            self.row['provider_request_id']=value
            report,_=self.run_attribution();self.assertEqual(report['tiers']['recorded_label'],1)
        self.row['provider_request_id']='one';self.row['provenance']={'provider_request_id':'two'}
        report,details=self.run_attribution()
        self.assertEqual(details[0]['join_state'],'conflicting_or_invalid_provider_id')

    def test_equal_distance_or_conflicting_id_is_ambiguous(self):
        report,details=self.run_attribution(calls=[self.call,dict(self.call,at=101)])
        self.assertEqual(details[0]['join_state'],'ambiguous_nearest_call')
        self.row['provider_request_id']='fixture-id';self.call['provider_request_id']='fixture-id'
        report,details=self.run_attribution(calls=[self.call,dict(self.call,model='other-model')])
        self.assertEqual(details[0]['join_state'],'ambiguous_provider_id')

    def test_identical_ledger_copies_deduplicate_but_bad_closest_does_not_promote_next(self):
        report,_=self.run_attribution(calls=[self.call,copy.deepcopy(self.call)])
        self.assertEqual(report['unique_ledger_records_supplied'],1)
        bad=dict(self.call,at=100,model='')
        report,details=self.run_attribution(calls=[bad,self.call])
        self.assertEqual(details[0]['join_state'],'call_metadata_unavailable')
        self.assertEqual(report['tiers']['ledger_attributed'],0)

    def test_surface_class_and_window_boundaries(self):
        for call in (dict(self.call,organ='router:other'),dict(self.call,**{'class':'outbound'}),dict(self.call,at=94.99)):
            report,_=self.run_attribution(calls=[call]);self.assertEqual(report['tiers']['ledger_attributed'],0)
        report,_=self.run_attribution(calls=[dict(self.call,at=95)])
        self.assertEqual(report['tiers']['ledger_attributed'],1)
        self.row.pop('surface');report,details=self.run_attribution()
        self.assertEqual(details[0]['join_state'],'surface_caller_unmapped')
        self.row['_witness_adapter_kind']='canonical';self.config['source_surfaces']={'canonical':'fixture-chat'}
        self.assertEqual(self.run_attribution()[0]['tiers']['ledger_attributed'],1)

    def test_unknown_clock_in_same_caller_keeps_temporal_order_unknown(self):
        report,details=self.run_attribution(calls=[self.call,dict(self.call,at=None)])
        self.assertEqual(details[0]['join_state'],'caller_has_unordered_calls')
        self.assertEqual(report['tiers']['recorded_label'],1)

    def test_naive_clocks_require_explicit_timezone_and_dst_is_not_guessed(self):
        self.row['timestamp']='2026-01-01T12:00:00';self.call['at']='2026-01-01T11:59:59'
        self.assertEqual(self.run_attribution(cutoff=2000000000)[0]['tiers']['recorded_label'],1)
        self.config['naive_timezone']='America/Chicago'
        self.assertEqual(self.run_attribution(cutoff=2000000000)[0]['tiers']['ledger_attributed'],1)
        for stamp in ('2026-11-01T01:30:00','2026-03-08T02:30:00'):
            self.row['timestamp']=stamp;self.call['at']=stamp
            self.assertEqual(self.run_attribution(cutoff=2000000000)[0]['tiers']['ledger_attributed'],0)

    def test_explicit_offset_and_numeric_clocks_do_not_need_timezone(self):
        self.row['timestamp']='1970-01-01T00:01:40+00:00'
        self.assertEqual(self.run_attribution()[0]['tiers']['ledger_attributed'],1)
        self.row['ts']=101
        self.assertEqual(self.run_attribution()[1][0]['join_state'],'reply_clock_unavailable')

    def test_call_reuse_by_distinct_unknown_or_changed_replies_is_unresolved(self):
        for second in (dict(self.row,turn_id='other-turn'),dict(self.row,turn_id=None),dict(self.row,content='Other synthetic text')):
            report,details=self.run_attribution(rows=[self.row,second])
            self.assertEqual(report['tiers']['ledger_attributed'],0)
            self.assertTrue(all(d['join_state']=='call_reused_by_distinct_or_unknown_replies' for d in details))
        report,_=self.run_attribution(rows=[self.row,copy.deepcopy(self.row)])
        self.assertEqual(report['tiers']['ledger_attributed'],2)

    def test_label_disagreement_and_conflict_are_reported_without_alias_guess(self):
        self.row['served_by']='fixture-configured-name'
        report,_=self.run_attribution();self.assertEqual(report['label_ledger_agreement'],{'disagree':1})
        self.row['model']='other-label'
        report,_=self.run_attribution();self.assertEqual(report['label_ledger_agreement'],{'label_conflict':1})
        report,_=self.run_attribution(calls=[]);self.assertEqual(report['tiers']['unknown'],1)

    def test_observed_receipt_remains_highest_tier_without_granting_clean_lineage(self):
        row,nodes,_,_,_=F.fixture();row['timestamp']=110;row['served_by']='fixture-label'
        report,details=self.run_attribution(rows=[row],calls=[dict(self.call,at=109)])
        self.assertEqual(report['tiers']['observed'],1)
        row['content']+='changed'
        self.assertNotEqual(self.run_attribution(rows=[row])[0]['tiers']['observed'],1)

    def test_missing_labels_and_no_calls_stay_unknown(self):
        self.row.pop('served_by');report,details=self.run_attribution(calls=[])
        self.assertEqual(report['tiers']['unknown'],1)
        self.assertEqual(details[0]['ledger_model'],None)

    def test_cutoff_and_missing_cutoff_clock_are_explicit(self):
        self.row['timestamp']=200;report,_=self.run_attribution()
        self.assertEqual(report['excluded'],{'outside_cutoff':1});self.assertEqual(sum(report['tiers'].values()),0)
        self.row.pop('timestamp');report,_=self.run_attribution()
        self.assertEqual(report['copies_without_cutoff_clock'],1)
        self.assertEqual(report['tiers']['recorded_label'],1)

    def test_invalid_config_and_failed_call_cannot_be_attributed(self):
        for value in (True,0,11,float('nan')):
            self.config['window_seconds']=value
            with self.assertRaises(ValueError):self.run_attribution()
        self.config['window_seconds']=5
        self.call['stage']='failed'
        self.assertEqual(self.run_attribution()[1][0]['join_state'],'call_metadata_unavailable')

    def test_cli_keeps_strict_results_and_private_details_separate(self):
        with tempfile.TemporaryDirectory(prefix='legacy-attribution-') as directory:
            root=Path(directory).resolve();root.chmod(0o700)
            self.assertNotIn('.vintos',root.parts)
            bundle={'input_kind':'synthetic','sources':[{'kind':'canonical','rows':[self.row]}]}
            reports=[]
            with patch.dict(os.environ,SPARK_WORKSPACE=str(root)):
                for index in range(2):
                    if index:bundle['historical_attribution']=dict(self.config,compute_ledger=[self.call])
                    source=root/f'input-{index}.json';source.write_text(json.dumps(bundle))
                    output=root/f'out-{index}'
                    result=subprocess.run([sys.executable,str(ROOT/'experiments/judges-witness/replay.py'),
                        '--scratch',str(root),'--input',str(source),'--output',str(output),
                        '--cutoff','1970-01-01T00:03:20+00:00'],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stderr)
                    report=json.loads((output/'aggregate.json').read_text());reports.append(report)
                historical=reports[1].pop('historical_attribution')
                self.assertEqual(historical['tiers']['ledger_attributed'],1)
                self.assertEqual(reports[0],reports[1])
                private=output/'private-model-attribution.json'
                self.assertEqual(private.stat().st_mode&0o777,0o600)
                manifest=json.loads((output/'private-run.json').read_text())
                self.assertIn(private.name,manifest['outputs'])
                result=subprocess.run([sys.executable,str(ROOT/'experiments/judges-witness/report.py'),
                    '--scratch',str(root),'--run',str(output),'--output',str(root/'review')],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                text=(root/'review/review.md').read_text()
                self.assertIn('ledger_attributed: 1',text);self.assertIn('Strictly eligible replies: 0',text)
                self.assertNotIn('fixture-model',text)

if __name__=='__main__':unittest.main()

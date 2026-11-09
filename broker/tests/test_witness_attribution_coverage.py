#!/usr/bin/env python3
"""Synthetic coverage diagnosis stays separate from attribution and live stores."""
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

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('coverage_probe', ROOT/'experiments/judges-witness/coverage.py')
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)

class Tests(unittest.TestCase):
    def setUp(self):
        self.row = dict(role='assistant', content='Synthetic reply only.', turn_id='synthetic-turn', surface='synthetic-chat', timestamp=100)
        self.call = dict(at=80, organ='router:synthetic-chat', model='synthetic-model', provider='synthetic-provider', stage='complete', **{'class':'foreground'})
        self.config = dict(surface_callers={'synthetic-chat':['router:synthetic-chat']}, window_seconds=10)
        self.sender = Mock(side_effect=AssertionError('network forbidden'))
        p = patch.object(socket.socket,'connect',self.sender); p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertIsInstance(self.sender, Mock)

    def run_probe(self, rows=None, calls=None):
        return C.diagnose([self.row] if rows is None else rows, [self.call] if calls is None else calls, self.config, 200)

    def test_wider_opportunity_does_not_change_original_result(self):
        before = copy.deepcopy((self.row,self.call,self.config))
        report, private = self.run_probe()
        original, _ = C.attribution([self.row],[self.call],self.config,200)
        self.assertEqual(report['baseline'],original)
        self.assertEqual(report['baseline']['tiers']['unknown'],1)
        self.assertEqual(report['window_sensitivity']['10'],{'none_in_window':1})
        self.assertEqual(report['window_sensitivity']['30'],{'sole_call_in_window':1})
        self.assertEqual(before,(self.row,self.call,self.config))
        self.assertEqual(private['callers'][0]['first_retained_at'],'1970-01-01T00:01:20+00:00')

    def test_ambiguous_window_not_nearest_promotion(self):
        report,_ = self.run_probe(calls=[self.call,dict(self.call,at=75)])
        self.assertEqual(report['window_sensitivity']['30'],{'multiple_calls_in_window':1})

    def test_other_reply_contests_sole_call(self):
        other = dict(self.row,turn_id='synthetic-other',content='Other synthetic reply.',timestamp=85)
        report,_ = self.run_probe(rows=[self.row,other])
        self.assertEqual(report['window_sensitivity']['30'],{'call_contested_by_other_reply':1})

    def test_identical_source_copies_and_calls_deduplicate_honestly(self):
        report,_ = self.run_probe(rows=[self.row,dict(self.row)],calls=[self.call,dict(self.call)])
        self.assertEqual(report['window_sensitivity']['30'],{'sole_call_in_window':2})
        self.assertEqual(report['baseline']['unique_ledger_records_supplied'],1)

    def test_missing_identity_and_changed_final_text_contest(self):
        for other in (dict(self.row,turn_id=None),dict(self.row,content='Changed synthetic version.')):
            report,_ = self.run_probe(rows=[self.row,other])
            self.assertEqual(report['window_sensitivity']['30'],{'call_contested_by_other_reply':2})

    def test_callers_dates_cutoff_and_unknown_clocks(self):
        report, private = self.run_probe(calls=[self.call,dict(self.call,at=20),dict(self.call,at=200),dict(self.call,at='bad')])
        caller = private['callers'][0]
        self.assertEqual(caller['records'],3); self.assertEqual(caller['clock_unavailable'],1)
        self.assertEqual(caller['largest_observed_gap_seconds'],60)
        self.assertEqual(report['ledger_records_after_cutoff'],1)
        self.assertEqual(report['baseline']['join_states'],{'caller_has_unordered_calls':1})

    def test_unmapped_surface_private_only_and_background_not_candidate(self):
        other = dict(self.row,surface='private-surface-sentinel')
        report, private = self.run_probe(rows=[self.row,other],calls=[dict(self.call,**{'class':'background'})])
        self.assertEqual(report['window_sensitivity']['120'],{'none_in_window':1})
        self.assertNotIn('private-surface-sentinel',json.dumps(report))
        self.assertIn('private-surface-sentinel',json.dumps(private))
        for value in (self.row['content'],self.row['turn_id'],self.call['model'],self.call['provider'],self.call['organ']):
            self.assertNotIn(value,json.dumps(report))
        self.assertNotIn(self.row['content'],json.dumps(private))
        self.assertNotIn(self.row['turn_id'],json.dumps(private))

    def test_position_is_retained_span_not_logging_start(self):
        cases = [([], 'no_retained_foreground_calls'),([dict(self.call,at=150)],'before_first_retained_call'),
                 ([self.call],'after_last_retained_call'),([self.call,dict(self.call,at=150)],'within_retained_span')]
        for calls, state in cases:
            report,_ = self.run_probe(calls=calls)
            self.assertEqual(report['unmatched_span_positions'],{state:1})

    def test_failed_metadata_does_not_gain_attribution(self):
        report,_ = self.run_probe(calls=[dict(self.call,stage='failed')])
        self.assertEqual(report['window_sensitivity']['30'],{'sole_call_metadata_unavailable':1})

    def test_exact_id_failure_never_enters_wider_recovery(self):
        report,_ = self.run_probe(rows=[dict(self.row,provider_request_id='missing-synthetic-id')])
        self.assertEqual(report['window_sensitivity']['120'],{})
        self.assertEqual(report['baseline']['join_states'],{'provider_id_unmatched':1})

    def test_timezone_and_ambiguous_local_time(self):
        self.config['naive_timezone']='America/Chicago'
        row=dict(self.row,timestamp='2026-11-01T01:30:00')
        report,_ = C.diagnose([row],[self.call],self.config,'2026-11-02T00:00:00Z')
        self.assertEqual(report['baseline']['join_states'],{'reply_clock_unavailable':1})

    def test_bounds_and_invalid_config(self):
        with patch.object(C,'MAX_CALLS',0):
            with self.assertRaises(ValueError): self.run_probe()
        self.config['window_seconds']=30
        with self.assertRaises(ValueError): self.run_probe()

    def test_cli_private_manifest_and_scratch_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); self.assertNotIn('.vintos',root.parts)
            source=root/'bundle.json'; output=root/'out'
            source.write_text(json.dumps(dict(input_kind='synthetic',sources=[dict(kind='canonical',rows=[self.row])],
                               historical_attribution=dict(self.config,compute_ledger=[self.call]))))
            env=dict(os.environ,SPARK_WORKSPACE=str(root),PYTHONDONTWRITEBYTECODE='1')
            cmd=[sys.executable,str(ROOT/'experiments/judges-witness/coverage.py'),'--scratch',str(root),
                 '--input',str(source),'--output',str(output),'--cutoff','1970-01-01T00:03:20Z']
            result=subprocess.run(cmd,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(output.stat().st_mode & 0o777,0o700)
            manifest=json.loads((output/'private-run.json').read_text())
            for name in ('aggregate.json','private-coverage.json','private-run.json'):
                self.assertEqual((output/name).stat().st_mode & 0o777,0o600)
                if name in manifest['outputs']:
                    self.assertEqual(C.hashlib.sha256((output/name).read_bytes()).hexdigest(),manifest['outputs'][name]['sha256'])
            self.assertNotIn(self.row['content'],result.stdout+result.stderr)
            self.assertNotEqual(subprocess.run(cmd,env=env,capture_output=True).returncode,0)
            bad=root/'.vintos';bad.mkdir(mode=0o700)
            with patch.dict(os.environ,SPARK_WORKSPACE=str(bad)):
                with self.assertRaises(ValueError): C.R.scratch_root(str(bad))
            link=root/'linked';link.symlink_to(source)
            with self.assertRaises(ValueError): C.R.inside(root,str(link))

if __name__=='__main__': unittest.main()

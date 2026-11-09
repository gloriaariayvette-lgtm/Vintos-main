#!/usr/bin/env python3
"""Aggregate-only page rendering with synthetic counts and blocked senders."""
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
CLI=ROOT/'experiments/nonllm-judges/render_gloria.py'
spec=importlib.util.spec_from_file_location('gloria_page_test',CLI)
G=importlib.util.module_from_spec(spec);spec.loader.exec_module(G)


def counts():
    return dict(schema='capture-coverage-counts-v1',cutoff_at='2020-02-01T00:00:00Z',
        scoring='evaluated_separate_attribution_views',
        capture_window=dict(hours=24,retained_packets=3,start_inclusive='2020-01-31T00:00:00Z',
                            end_exclusive='2020-02-01T00:00:00Z',complete_stream_attested=False),
        sufficiency=dict(schema='judge-sufficiency-counts-v1',views=dict(primary_10s=[],window30=[])))


def cell(judge='voice',ready=False,days=None):
    return dict(judge=judge,mode='everyday',surface='avatar',item_kind='message' if judge in ('humor','taste') else None,
        estimates=[dict(level='similarity' if judge in ('humor','taste') else 'assessment',
            observed_scoreable=ready,estimated_days_until_scoreable=0 if ready else days,
            reason='scoreability_already_observed' if ready else 'conditional_on_same_qualified_arrival_rate' if days else 'zero_recent_qualifying_rate')])


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='judges-page-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        self.assertNotIn('.vintos',self.root.parts)
        self.sender=Mock(side_effect=AssertionError('external operation forbidden'))
        guard=patch.object(socket.socket,'connect',self.sender);guard.start();self.addCleanup(guard.stop)
        self.addCleanup(self.sender.assert_not_called);self.assertIs(socket.socket.connect,self.sender)
        self.source=self.root/'counts.json';self.save(self.source,counts())
    def save(self,path,value):path.write_text(json.dumps(value));path.chmod(0o600)
    def cli(self,*args):
        return subprocess.run([sys.executable,str(CLI),'--scratch',str(self.root),'--counts',str(self.source),*args],
                              capture_output=True,text=True,timeout=15,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    def test_checked_in_page_is_exact_unknown_template(self):
        text=G.render()
        self.assertEqual(text,(CLI.parent/'GLORIA.md').read_text())
        self.assertIn('Template',text);self.assertIn('count unknown',text)
        self.assertNotIn('0 retained packets',text);self.assertLess(len(text.split()),420)
        for title,_,_ in G.DESCRIPTIONS.values():self.assertIn('**'+title+'**',text)
        self.assertIn('no verdicts on his feelings',text)
        self.assertIn('4–5★',text);self.assertIn('Landings',text)
    def test_scoring_requires_observed_primary_score_and_stays_partial(self):
        value=counts();value['sufficiency']['views']['primary_10s']=[cell(ready=True)]
        text=G.render(value)
        self.assertIn('Scoring in 1 of 10 areas; others are waiting.',text)
        self.assertIn('already scoring there',text)
        self.assertIn('Waiting for data and review',text)
        self.assertIn('offline comparison',text)
    def test_sensitivity_only_score_never_promotes_primary(self):
        value=counts();value['sufficiency']['views']['window30']=[cell(ready=True)]
        text=G.render(value)
        self.assertNotIn('Scoring in',text)
        self.assertIn('not enough evidence to give a date',text)
    def test_estimate_uses_initial_facet_comparison_and_is_not_a_promise(self):
        value=counts();row=cell('humor',days=4)
        row['estimates'].append(dict(level='empirical_rank',observed_scoreable=False,estimated_days_until_scoreable=8,reason='conditional_on_same_qualified_arrival_rate'))
        value['sufficiency']['views']['primary_10s']=[row]
        text=G.render(value)
        self.assertIn('about 4 more days for one area',text);self.assertNotIn('about 8',text)
        self.assertIn('not deadlines',text);self.assertIn('nothing you need to send for a test',text)
    def test_counts_floor_is_not_scoreability(self):
        value=counts();row=cell(days=2);row['estimates'][0]['count_floor_met']=True
        value['sufficiency']['views']['primary_10s']=[row]
        self.assertNotIn('Scoring in',G.render(value))
        self.assertIn('about 2 more days',G.render(value))
    def test_legacy_counts_leave_missing_health_and_time_unknown(self):
        value=counts();value.pop('cutoff_at');value.pop('capture_window');value.pop('sufficiency')
        text=G.render(value)
        self.assertIn('Snapshot time not recorded',text);self.assertIn('count unknown',text)
        self.assertIn('sink status unknown',text)
    def test_health_is_explicit_dated_and_never_inferred_from_packets(self):
        value=counts();self.assertIn('3 retained packets',G.render(value))
        self.assertIn('sink status unknown',G.render(value))
        health=dict(schema='judge-sink-health-counts-v1',enabled=True,observed_at='2020-01-31T23:59:00Z')
        self.assertIn('sink last observed on (Jan 31 17:59 CST)',G.render(value,health))
        health['enabled']=False;self.assertIn('sink last observed off',G.render(value,health))
        health['observed_at']='2020-02-02T00:00:00Z'
        with self.assertRaises(ValueError):G.render(value,health)
    def test_arbitrary_metadata_never_reaches_page(self):
        value=counts();value['sufficiency']['views']['primary_10s']=[cell()]
        value['sufficiency']['views']['primary_10s'][0]['private_metadata']='SYNTHETIC_SECRET_MARKER'
        value['model']='SYNTHETIC_SECRET_MARKER';value['ids']=['SYNTHETIC_SECRET_MARKER'];value['timezone']='SYNTHETIC_SECRET_MARKER'
        value['days']=[dict(content='SYNTHETIC_SECRET_MARKER')]
        self.assertNotIn('SYNTHETIC_SECRET_MARKER',G.render(value))
    def test_invalid_counts_and_conflicting_readiness_refuse(self):
        for patcher in (lambda v:v['capture_window'].update(retained_packets=True),
                        lambda v:v['capture_window'].update(start_inclusive='2020-01-30T00:00:00Z'),
                        lambda v:v['sufficiency']['views'].update(primary_10s=[cell(),cell()]),
                        lambda v:v['sufficiency']['views'].update(primary_10s=[cell(days=1.5)]),
                        lambda v:v.update(scoring='not_assessed_missing_prepared_projection')):
            value=counts();value['sufficiency']['views']['primary_10s']=[cell(ready=True)];patcher(value)
            with self.assertRaises((ValueError,TypeError)):G.render(value)
    def test_cli_reads_only_counts_and_keeps_source_unchanged(self):
        before=self.source.read_bytes();files=set(self.root.iterdir())
        result=self.cli();self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,G.render(counts()));self.assertEqual(before,self.source.read_bytes())
        self.assertEqual(set(self.root.iterdir()),files)
    def test_cli_refuses_symlink_permissions_and_private_values_in_errors(self):
        target=self.root/'synthetic-secret-path';self.save(target,counts());self.source.unlink();self.source.symlink_to(target)
        result=self.cli();self.assertNotEqual(result.returncode,0)
        self.assertEqual(result.stderr.strip(),'judges_page_refused');self.assertEqual(result.stdout,'')
        self.source.unlink();self.save(self.source,counts());self.source.chmod(0o644)
        self.assertNotEqual(self.cli().returncode,0)
    def test_cli_rejects_duplicate_keys_nonfinite_oversize_and_nonprivate_root(self):
        for content in ('{"schema":1,"schema":2}','{"schema":NaN}','x'*(G.MAX_BYTES+1)):
            self.source.write_text(content);self.source.chmod(0o600)
            result=self.cli();self.assertNotEqual(result.returncode,0);self.assertEqual(result.stderr.strip(),'judges_page_refused')
        self.save(self.source,counts());self.root.chmod(0o755)
        self.assertNotEqual(self.cli().returncode,0)
    def test_cli_refuses_outside_root_and_repository_inputs(self):
        with tempfile.TemporaryDirectory(prefix='judges-page-other-') as other:
            outside=Path(other)/'private-counts.json';self.save(outside,counts())
            result=self.cli('--counts',str(outside));self.assertNotEqual(result.returncode,0)
            self.assertEqual(result.stderr.strip(),'judges_page_refused')
        (self.root/'.git').mkdir()
        self.assertNotEqual(self.cli().returncode,0)

    def test_actual_capture_report_renders_without_reinterpreting_scores(self):
        spec=importlib.util.spec_from_file_location('coverage_for_gloria',ROOT/'broker/tests/test_capture_coverage_report.py')
        fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
        test=fixture.Tests('test_packet_only_reports_coverage_without_inventing_scores_or_freezes')
        try:
            test.setUp()
            value=test.report(bundle=test.bundle)
            text=G.render(value)
            self.assertIn('Scoring in',text)
            self.assertEqual(set(G.SURFACES),fixture.C.R.P.SURFACES)
            self.assertEqual(set(G.MODES),fixture.C.R.P.MODES)
        finally:test.doCleanups()

if __name__=='__main__':unittest.main()

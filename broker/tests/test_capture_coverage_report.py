#!/usr/bin/env python3
"""Counts-only capture census using synthetic private inputs; no live I/O."""
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
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
F=load('builder_fixture_for_capture',ROOT/'broker/tests/test_numerical_evidence_builder.py')
C=load('capture_report_test',ROOT/'experiments/nonllm-judges/capture_report.py')
CLI=Path(C.__file__);CUTOFF='2020-02-01T00:00:00Z'

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='capture-report-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        self.directory=self.root/'packets';self.directory.mkdir(mode=0o700)
        b,g,c,h=F.fixture();self.bundle,_=F.B.build(b,g,c,h,CUTOFF)
        self.packets=[dict(copy.deepcopy(r),schema='witness-capture-v1',lineage=copy.deepcopy(g)) for r in b['rows'] if r['role']=='assistant']
        self.sender=Mock(side_effect=AssertionError('network forbidden'))
        guard=patch.object(socket.socket,'connect',self.sender);guard.start();self.addCleanup(guard.stop)
        self.addCleanup(self.sender.assert_not_called);self.assertIs(socket.socket.connect,self.sender)
        self.assertNotIn('.vintos',self.root.parts)

    def report(self,**kw):return C.report(self.packets,CUTOFF,**kw)
    def total(self,r,key):return sum(d[key] for d in r['days'])
    def save(self,path,value):
        path.write_text(json.dumps(value));path.chmod(0o600)
    def cli(self,*args):
        for i,p in enumerate(self.packets):self.save(self.directory/('capture-%032x.json'%i),p)
        return subprocess.run([sys.executable,str(CLI),'--scratch',str(self.root),'--packets',str(self.directory),
            '--cutoff',CUTOFF,*args],capture_output=True,text=True,timeout=45,
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))

    def test_rolling_capture_count_is_exact_and_not_a_calendar_day_sum(self):
        at=C.W.instant(self.packets[0]['witness_receipt']['finalized_at'])
        for hours,expected in ((0,0),(24,1),(24.0001,0)):
            with self.subTest(hours=hours):
                r=C.report([self.packets[0]],at+hours*3600,zone='America/Chicago')
                self.assertEqual(r['capture_window']['retained_packets'],expected)
                self.assertFalse(r['capture_window']['complete_stream_attested'])
        r=C.report([self.packets[0],copy.deepcopy(self.packets[0])],at+1)
        self.assertEqual(r['capture_window']['retained_packets'],2)
        self.assertEqual(self.total(r,'replies'),1)
        self.assertEqual(C.report([],at+1)['capture_window']['retained_packets'],0)

    def test_packet_only_reports_coverage_without_inventing_scores_or_freezes(self):
        r=self.report();self.assertEqual(self.total(r,'packets'),32)
        self.assertEqual(self.total(r,'provider_reported_served_model'),32)
        self.assertEqual(self.total(r,'original_act_bindings'),32)
        for d in r['days']:
            self.assertEqual(d['encoder_freeze_sources']['unknown'],d['replies'])
            self.assertTrue(all(v['scored_replies']==0 for v in d['judges'].values()))
        self.assertEqual(r['scoring'],'not_assessed_missing_prepared_projection')

    def test_actual_capture_incomplete_undelivered_stays_unscored(self):
        for p in self.packets:
            p['reply_node']['complete']=False;p['reply_node']['influence']='unknown'
            p['witness_receipt']['delivery']='unknown'
        r=self.report(bundle=self.bundle)
        self.assertEqual(self.total(r,'original_act_bindings'),0)
        self.assertEqual(self.total(r,'full_lineage'),0)
        self.assertTrue(all(d['judges']['voice']['scored_replies']==0 for d in r['days']))

    def test_provider_reported_is_not_configured_or_serving_process_identity(self):
        for p in self.packets:
            p['witness_receipt']['generation']['attempts'][0]['identity_evidence']='unknown'
        r=self.report();self.assertEqual(self.total(r,'provider_reported_served_model'),0)
        self.assertEqual(self.total(r,'original_act_bindings'),0)

    def test_runtime_identity_is_separate_from_provider_report(self):
        self.packets[0]['witness_receipt']['generation']['attempts'][0]['identity_evidence']='runtime_receipt'
        r=self.report();self.assertEqual(self.total(r,'provider_reported_served_model'),31)
        self.assertEqual(self.total(r,'original_act_bindings'),32)

    def test_positive_facets_count_only_exact_packet_admitted_replies(self):
        base,landings=F.F.fixture();b=copy.deepcopy(self.bundle)
        b['numerical_evidence']['anchors']=base['numerical_evidence']['anchors']
        b['numerical_evidence']['taste_attempt_ids']=base['numerical_evidence']['taste_attempt_ids']
        b['numerical_evidence']['items']=[dict(node_id=r['turn_id'],kind='message') for r in b['rows'] if r['role']=='assistant']
        r=self.report(bundle=b,landings=landings)
        self.assertGreater(sum(d['judges']['taste']['scored_replies'] for d in r['days']),0)
        self.assertGreater(sum(d['judges']['humor']['scored_replies'] for d in r['days']),0)
        for p in self.packets:p['witness_receipt']['delivery']='unknown'
        r=self.report(bundle=b,landings=landings)
        self.assertEqual(sum(d['judges']['taste']['scored_replies'] for d in r['days']),0)

    def test_indirect_influence_is_denied(self):
        for p in self.packets:
            p['lineage'][0]['kind']='emotion_nudge'
        self.assertEqual(self.total(self.report(),'original_act_bindings'),31)

    def test_duplicate_identical_packets_do_not_inflate_reply_denominator(self):
        self.packets.append(copy.deepcopy(self.packets[0]));r=self.report()
        self.assertEqual(self.total(r,'packets'),33);self.assertEqual(self.total(r,'replies'),32)

    def test_conflicting_copies_deny_without_selecting_winner(self):
        p=copy.deepcopy(self.packets[0]);p['test_mode']=True;self.packets.append(p)
        self.assertEqual(self.total(self.report(),'original_act_bindings'),31)

    def test_prepared_projection_runs_existing_judges_with_packet_gate(self):
        r=self.report(bundle=self.bundle)
        self.assertGreater(sum(d['judges']['voice']['scored_replies'] for d in r['days']),0)
        self.assertEqual(sum(d['encoder_freeze_sources']['legacy_unknown'] for d in r['days']),32)
        for d in r['days']:self.assertIn('window30',d['attribution_views'])

    def test_mismatched_prepared_text_clock_surface_refuse(self):
        for field,value in (('content','changed'),('timestamp',1),('surface','other')):
            b=copy.deepcopy(self.bundle);next(r for r in b['rows'] if r['role']=='assistant')[field]=value
            with self.assertRaises(ValueError):self.report(bundle=b)

    def test_late_published_freeze_and_tamper_refuse(self):
        b=copy.deepcopy(self.bundle);pin=next(iter(C.R.Q.load_pins().values()))
        # Use the checked-in pin policy as a constant, with fixture acts after its date.
        frozen=C.R.P.stamp(pin['revision_at']);copy_at=frozen+1
        receipt=C.R.Q.qualify(pin['artifact_sha256'],copy_at,'published_artifact','external_pretrained',pin['id'])
        # This fixture predates the reviewed revision: qualification cannot move its acts.
        b['encoder']['artifact_sha256']=pin['artifact_sha256']
        b['numerical_evidence'].update(encoder_frozen_at=frozen,encoder_freeze_source='published_artifact',encoder_freeze_receipt=receipt)
        r=self.report(bundle=b);self.assertEqual(sum(d['encoder_freeze_sources']['published_artifact'] for d in r['days']),0)
        b['numerical_evidence']['encoder_freeze_receipt']['frozen_at']=0
        with self.assertRaises(ValueError):self.report(bundle=b)

    def test_reviewed_fixture_published_freeze_is_counted_separately(self):
        b=copy.deepcopy(self.bundle);frozen=b['numerical_evidence']['encoder_frozen_at']
        pin=dict(next(iter(C.R.Q.load_pins().values())))
        pin.update(id='fixture-pin',artifact_sha256=b['encoder']['artifact_sha256'],revision='a'*40,
                   revision_at='2019-01-01T00:00:00Z',reviewer='synthetic review')
        with patch.object(C.R.Q,'load_pins',return_value={'fixture-pin':pin}):
            receipt=C.R.Q.qualify(pin['artifact_sha256'],frozen,'published_artifact','external_pretrained','fixture-pin')
            b['numerical_evidence'].update(encoder_frozen_at=receipt['frozen_at'],encoder_freeze_source='published_artifact',encoder_freeze_receipt=receipt)
            r=self.report(bundle=b)
        self.assertEqual(sum(d['encoder_freeze_sources']['published_artifact'] for d in r['days']),32)

    def test_copy_time_qualified_receipt_is_counted_separately(self):
        b=copy.deepcopy(self.bundle);frozen=b['numerical_evidence']['encoder_frozen_at']
        receipt=C.R.Q.qualify(b['encoder']['artifact_sha256'],frozen)
        b['numerical_evidence'].update(encoder_freeze_source='copy_time',encoder_freeze_receipt=receipt)
        r=self.report(bundle=b)
        self.assertEqual(sum(d['encoder_freeze_sources']['copy_time'] for d in r['days']),32)
        self.assertEqual(sum(d['encoder_freeze_sources']['unknown'] for d in r['days']),0)

    def test_timezone_cutoff_and_empty_directory(self):
        self.assertEqual(C.report([],CUTOFF)['days'],[])
        cutoff=self.packets[0]['witness_receipt']['finalized_at']
        r=C.report(self.packets,cutoff)
        self.assertEqual(r['packets_outside_cutoff'],32)
        p=copy.deepcopy(self.packets[0]);p['witness_receipt']['finalized_at']=1577923201
        r=C.report([p],CUTOFF,zone='America/Chicago')
        self.assertEqual(r['days'][0]['date'],'2020-01-01')

    def cell(self, result, judge='voice', mode='everyday', surface='avatar', kind=None):
        return next(c for c in result['sufficiency']['views']['primary_10s']
                    if (c['judge'],c['mode'],c['surface'],c['item_kind']) == (judge,mode,surface,kind))

    def test_clock_unknown_capture_is_counted_but_never_qualified(self):
        for packet in self.packets:
            old=packet['witness_receipt']
            packet['witness_receipt']=dict(schema=old['schema'],status='unknown',
                finalized_at=old['finalized_at'],started_at=old['finalized_at']+3,clock_status='wall_order_unknown')
        r=self.report(bundle=self.bundle)
        self.assertEqual(self.total(r,'packets'),32)
        self.assertEqual(self.total(r,'original_act_bindings'),0)
        self.assertEqual(self.cell(r)['available']['admitted_acts'],0)

    def test_sufficiency_missing_projection_is_unknown_not_ready(self):
        c=self.cell(self.report())
        self.assertIsNone(c['available']['reference_days'])
        self.assertIsNone(c['estimates'][0]['estimated_days_until_scoreable'])
        self.assertIsNone(c['estimates'][0]['count_floor_met'])
        self.assertIn('missing_prepared_projection',c['blockers'])

    def test_sufficiency_matches_observed_voice_and_keeps_scopes_separate(self):
        r=self.report(bundle=self.bundle);c=self.cell(r)
        self.assertEqual(c['requirements']['reference_days'],4)
        self.assertTrue(c['estimates'][0]['observed_scoreable'])
        self.assertEqual(c['estimates'][0]['estimated_days_until_scoreable'],0)
        empty=self.cell(r,surface='journal')
        self.assertEqual(empty['available']['reference_days'],0)
        self.assertIsNone(empty['estimates'][0]['estimated_days_until_scoreable'])
        self.assertEqual(self.cell(r,'drift')['requirements']['sustained_shift_consecutive_days'],4)
        self.assertIsNone(r['sufficiency']['sustained_shift_eta'])

    def test_sufficiency_no_adapter_or_outcomes_never_invents_eta(self):
        r=self.report(bundle=self.bundle)
        for judge in ('recurrence','grouping'):
            self.assertEqual(self.cell(r,judge)['blockers'],['no_retained_adapter'])
        for judge in ('humor','taste'):
            c=self.cell(r,judge,kind='message')
            self.assertEqual(c['available']['positive_anchors'],0)
            self.assertEqual([e['required_reference_days'] for e in c['estimates']],[2,4])
            self.assertTrue(all(e['estimated_days_until_scoreable'] is None for e in c['estimates']))

    def test_sufficiency_counts_exact_positive_days_by_kind(self):
        base,landings=F.F.fixture();b=copy.deepcopy(self.bundle)
        b['numerical_evidence']['anchors']=base['numerical_evidence']['anchors']
        b['numerical_evidence']['taste_attempt_ids']=base['numerical_evidence']['taste_attempt_ids']
        b['numerical_evidence']['items']=[dict(node_id=r['turn_id'],kind='message') for r in b['rows'] if r['role']=='assistant']
        r=self.report(bundle=b,landings=landings)
        self.assertEqual(self.cell(r,'taste',kind='message')['available']['reference_days'],4)
        self.assertEqual(self.cell(r,'taste',kind='journal')['available']['positive_anchors'],0)
        self.assertTrue(self.cell(r,'humor',kind='message')['estimates'][0]['observed_scoreable'])
        for p in self.packets:p['witness_receipt']['delivery']='unknown'
        denied=self.report(bundle=b,landings=landings)
        self.assertEqual(self.cell(denied,'taste',kind='message')['available']['positive_anchors'],0)

    def test_sufficiency_rate_excludes_current_day_and_includes_zero_days(self):
        cutoff='2020-01-03T18:00:00Z'
        self.bundle['numerical_evidence']['reference_ids']=[p['turn_id'] for p in self.packets]
        r=C.report(self.packets,cutoff,zone='UTC',bundle=self.bundle)
        c=self.cell(r);window=r['sufficiency']['rate_window']
        self.assertEqual(window['calendar_days'],7)
        self.assertEqual(window['end_date_exclusive'],'2020-01-03')
        self.assertEqual(c['available']['reference_days'],2)
        self.assertAlmostEqual(c['recent']['reference_days_per_day'],2/7)
        self.assertEqual(c['estimates'][0]['missing_reference_days'],2)
        self.assertEqual(c['estimates'][0]['estimated_days_until_scoreable'],11)
        self.packets.append(copy.deepcopy(self.packets[0]))
        twice=C.report(self.packets,cutoff,zone='UTC',bundle=self.bundle)
        self.assertEqual(self.cell(twice)['recent'],c['recent'])

    def test_sufficiency_known_degenerate_reference_has_no_eta(self):
        with patch.object(C.R.V,'calibrate',return_value=None):
            c=self.cell(self.report(bundle=self.bundle))
        self.assertTrue(c['estimates'][0]['count_floor_met'])
        self.assertFalse(c['estimates'][0]['observed_scoreable'])
        self.assertEqual(c['estimates'][0]['reason'],'degenerate_reference')
        self.assertIsNone(c['estimates'][0]['estimated_days_until_scoreable'])

    def test_sufficiency_zero_recent_rate_does_not_extrapolate_raw_capture(self):
        b=copy.deepcopy(self.bundle)
        b['numerical_evidence']['reference_ids']=[self.packets[0]['turn_id']]
        c=self.cell(self.report(bundle=b))
        self.assertEqual(c['available']['reference_days'],1)
        self.assertEqual(c['recent']['reference_days_per_day'],0)
        self.assertIsNone(c['estimates'][0]['estimated_days_until_scoreable'])

    def test_cli_read_only_counts_no_private_content(self):
        result=self.cli();self.assertEqual(result.returncode,0,result.stderr)
        public=json.loads(result.stdout)
        self.assertEqual(self.total(public,'replies'),32)
        for bad in ('synthetic-served','reply-','context-','sha256','vector',str(self.root)):
            self.assertNotIn(bad,result.stdout)
        self.assertEqual(set(p.name for p in self.root.iterdir()),{'packets'})

    def test_cli_prepared_and_private_permissions(self):
        source=self.root/'input.json';self.save(source,self.bundle)
        result=self.cli('--prepared-input',str(source));self.assertEqual(result.returncode,0,result.stderr)
        source.chmod(0o644);result=self.cli('--prepared-input',str(source));self.assertNotEqual(result.returncode,0)
        self.assertEqual(json.loads(result.stderr),{'error':'capture_report_refused'})

    def test_repository_and_live_store_roots_refuse(self):
        for root in (ROOT,self.root/'.vintos',self.root/'.openclaw'):
            if root!=ROOT:root.mkdir(mode=0o700)
            result=subprocess.run([sys.executable,str(CLI),'--scratch',str(root),'--packets',str(root),
                '--cutoff',CUTOFF],capture_output=True,text=True,timeout=30)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(json.loads(result.stderr),{'error':'capture_report_refused'})

    def test_symlink_and_world_readable_packet_refuse(self):
        self.cli();path=self.directory/'capture-00000000000000000000000000000000.json'
        path.chmod(0o644)
        result=subprocess.run([sys.executable,str(CLI),'--scratch',str(self.root),'--packets',str(self.directory),'--cutoff',CUTOFF],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        target=self.root/'target.json';path.rename(target);path.symlink_to(target)
        with self.assertRaises(ValueError):C.private_path(self.root,path)

if __name__=='__main__':unittest.main()

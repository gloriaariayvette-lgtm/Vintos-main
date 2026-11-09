#!/usr/bin/env python3
"""Synthetic CLI end-to-end tests; projections never come from real stores."""
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
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
FIX=load('character_fixture',ROOT/'broker/tests/test_character_reference_prototype.py')
P=load('private_runner',ROOT/'experiments/nonllm-judges/run_private.py')
sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
CLI=ROOT/'experiments/nonllm-judges/run_private.py'


def fixture():
    b=FIX.fixture();b['controls']=[];b['feedback']=[]
    b['encoder']['artifact_sha256']=sha('synthetic artifact')
    rows=[r for r in b['rows'] if r['role']=='assistant']
    meta=dict(schema='numerical-evidence-v1',nodes=[],bindings=[],encoder_frozen_at=1577836800-86400,
              humor_attempt_ids=[r['turn_id'] for r in rows],taste_attempt_ids=[r['turn_id'] for r in rows],anchors=[])
    land=dict(schema='landings-projection-v1',anchors=[])
    for r in rows:
        meta['nodes'].append(dict(id=r['turn_id'],kind='original_act',at=r['timestamp'],parents=[],complete=True))
        meta['bindings'].append(dict(node_id=r['turn_id'],origin_id=r['turn_id'],content_sha256=sha(r['content']),source='synthetic-history'))
    for index,r in enumerate(rows[:8:2]):
        key=r['turn_id'];digest=sha(r['content'])
        base=dict(evidence_id='anchor-'+str(index),node_id=key,content_sha256=digest,actor='owner',witnessed=True,
                  observed_at=r['timestamp']+10,source_record_sha256=sha('synthetic record '+str(index)))
        meta['anchors'].append(dict(base,source='adjacent_exchange',value='haha!',link=dict(kind='adjacent_exchange',
            exchange_id='synthetic-exchange-'+str(index),target_id=key,target_sha256=digest,reaction_id='synthetic-reaction-'+str(index),
            reaction_sha256=sha('haha!'),target_index=0,reaction_index=1)))
        land['anchors'].append(dict(base,evidence_id='taste-'+str(index),source='landings',value='landed',
                                  link=dict(kind='exact_item',item_id=key,item_sha256=digest,item_kind='message')))
    b['numerical_evidence']=meta
    return b,land


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='private-judges-cli-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        self.sender=Mock(side_effect=AssertionError('network forbidden'))
        guard=patch.object(socket.socket,'connect',self.sender);guard.start();self.addCleanup(guard.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertNotIn('.vintos',self.root.parts);self.assertIsInstance(socket.socket.connect,Mock)
        self.bundle,self.land=fixture();self.input=self.root/'input.json';self.lp=self.root/'landings.json'
        self.output=self.root/'result/private.json';self.summary=self.root/'result/counts.json'

    def command(self,**changes):
        options=dict(input=self.input,landings=self.lp,scratch=self.root,output=self.output,summary=self.summary,cutoff='2020-02-01T00:00:00Z')
        options.update(changes)
        return [sys.executable,str(CLI)]+[part for k,v in options.items() if v is not None for part in ('--'+k,str(v))]

    def run_cli(self,**changes):
        self.input.write_text(json.dumps(self.bundle));self.lp.write_text(json.dumps(self.land))
        env=dict(os.environ,SPARK_WORKSPACE=str(self.root),PYTHONDONTWRITEBYTECODE='1')
        # This local subprocess is the CLI under test. Its own audit guard rejects networking/subprocesses.
        return subprocess.run(self.command(**changes),capture_output=True,text=True,env=env,timeout=30)

    def test_end_to_end_same_projection_all_facets_and_private_permissions(self):
        result=self.run_cli();self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),{'written':True,'reports':2});self.assertFalse(result.stderr)
        private=json.loads(self.output.read_text());public=json.loads(self.summary.read_text())
        self.assertEqual(self.output.stat().st_mode&0o777,0o600);self.assertEqual(self.summary.stat().st_mode&0o777,0o600)
        self.assertEqual(self.output.parent.stat().st_mode&0o777,0o700)
        view=public['views']['window30'];self.assertEqual(view['admitted_original_acts'],32)
        self.assertGreater(sum(s['voice_scored'] for s in view['per_mode_surface']),0)
        self.assertEqual(view['facets']['humor']['positive_acts'],4);self.assertEqual(view['facets']['taste']['positive_acts'],4)
        self.assertGreater(view['facets']['taste']['scored'],0)
        self.assertEqual(private['manifest']['input_sha256'],hashlib.sha256(self.input.read_bytes()).hexdigest())
        self.assertEqual(private['manifest']['landings_sha256'],hashlib.sha256(self.lp.read_bytes()).hexdigest())
        self.assertEqual(json.loads(self.input.read_text()),self.bundle);self.assertEqual(json.loads(self.lp.read_text()),self.land)
        self.assertIn('attribution',private);self.assertIn('mode_assignments',private)

    def test_public_summary_is_counts_only_and_no_private_identifiers_or_scores(self):
        self.assertEqual(self.run_cli().returncode,0)
        text=self.summary.read_text()
        for secret in ('reply-','synthetic-','nomic','claude','grok','sha256','I wonder','score"','similarity','distance','mean_',self.root.as_posix()):
            self.assertNotIn(secret,text)
        public=json.loads(text)
        def walk(x):
            if isinstance(x,float):self.fail('public summary contains a floating score')
            if isinstance(x,dict):
                for v in x.values():walk(v)
            if isinstance(x,list):
                for v in x:walk(v)
        walk(public)

    def test_no_new_evidence_means_unscored_not_synthetic_lineage(self):
        del self.bundle['numerical_evidence'];self.bundle['encoder'].pop('artifact_sha256')
        self.assertEqual(self.run_cli().returncode,0)
        public=json.loads(self.summary.read_text());view=public['views']['window30']
        self.assertEqual(view['admitted_original_acts'],0)
        self.assertEqual(sum(s['voice_unscored'] for s in view['per_mode_surface']),32)
        self.assertFalse(public['encoder_metadata_available'])
        self.assertEqual(public['adapter_unavailable']['missing_or_unbound_original_act'],32)

    def test_missing_ancestry_remains_unknown(self):
        self.bundle['numerical_evidence']['nodes']=[]
        self.assertEqual(self.run_cli().returncode,0)
        view=json.loads(self.summary.read_text())['views']['window30']
        self.assertEqual(view['admitted_original_acts'],0);self.assertEqual(view['lineage_exclusions']['lineage_missing'],32)
        self.assertEqual(view['facets']['humor']['scored'],0)

    def test_indirect_influence_does_not_enter_cli_scores(self):
        meta=self.bundle['numerical_evidence'];meta['nodes'].append(dict(id='effect',kind='emotion_nudge',at=1577836700,parents=[],complete=True))
        meta['nodes'][-2]['parents']=['effect']
        self.assertEqual(self.run_cli().returncode,0)
        view=json.loads(self.summary.read_text())['views']['window30']
        self.assertEqual(view['admitted_original_acts'],31);self.assertEqual(view['lineage_exclusions']['influenced_or_derived'],1)

    def test_primary_and_window30_are_separate(self):
        self.bundle['historical_attribution']['compute_ledger'][-1]['at']-=20
        self.assertEqual(self.run_cli().returncode,0)
        views=json.loads(self.summary.read_text())['views']
        self.assertEqual(views['primary_10s']['selected_replies'],31);self.assertEqual(views['window30']['selected_replies'],32)

    def test_optional_landings_has_no_positive_taste_invention(self):
        self.assertEqual(self.run_cli(landings=None,view='window30').returncode,0)
        views=json.loads(self.summary.read_text())['views'];self.assertEqual(set(views),{'window30'})
        self.assertEqual(views['window30']['facets']['taste']['positive_acts'],0)

    def test_legacy_feedback_cannot_supply_missing_adjacency(self):
        self.bundle['numerical_evidence']['anchors']=[]
        self.bundle['feedback']=[dict(reply_id='reply-0-0',link='exact_reply',witnessed=True,value='hahaha')]
        self.assertEqual(self.run_cli().returncode,0)
        report=json.loads(self.summary.read_text());self.assertEqual(report['legacy_feedback_not_promoted'],1)
        self.assertEqual(report['views']['window30']['facets']['humor']['positive_acts'],0)

    def test_landings_projection_rejects_nonpositive_or_unbound(self):
        for value in ('partly','missed'):
            self.land['anchors'][0]['value']=value;result=self.run_cli()
            self.assertNotEqual(result.returncode,0);self.assertFalse(self.output.parent.exists())
            self.assertNotIn(value,result.stderr)

    def test_existing_output_never_overwritten(self):
        self.output.parent.mkdir(mode=0o700);self.output.write_text('synthetic sentinel')
        result=self.run_cli();self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.output.read_text(),'synthetic sentinel');self.assertFalse(self.summary.exists())

    def test_repo_output_and_any_repo_scratch_refused(self):
        result=self.run_cli(output=ROOT/'forbidden/private.json',summary=ROOT/'forbidden/counts.json')
        self.assertNotEqual(result.returncode,0);self.assertFalse((ROOT/'forbidden').exists())
        (self.root/'.git').write_text('synthetic marker')
        self.assertNotEqual(self.run_cli().returncode,0);self.assertFalse(self.output.parent.exists())

    def test_symlink_output_escape_refused(self):
        outside=self.root/'outside';outside.mkdir();link=self.root/'link';link.symlink_to(outside,target_is_directory=True)
        result=self.run_cli(output=link/'result/private.json',summary=link/'result/counts.json')
        self.assertNotEqual(result.returncode,0);self.assertFalse((outside/'result').exists())

    def test_separate_parent_and_world_readable_scratch_refused(self):
        self.assertNotEqual(self.run_cli(summary=self.root/'different/counts.json').returncode,0)
        self.root.chmod(0o755)
        self.assertNotEqual(self.run_cli().returncode,0);self.assertFalse(self.output.parent.exists())

    def test_bad_input_errors_never_echo_private_content(self):
        self.bundle['encoder']['family']='synthetic-private-canary'
        result=self.run_cli();self.assertNotEqual(result.returncode,0)
        self.assertEqual(json.loads(result.stderr)['error'],'private_run_failed')
        for secret in ('synthetic-private-canary','Traceback',str(self.root),'reply-'):self.assertNotIn(secret,result.stderr+result.stdout)
        self.assertFalse(self.output.parent.exists())

    def test_sustained_shift_dates_survive_cli_without_raw_scores(self):
        for cache in self.bundle['embeddings'][8:]:cache['vector']=[0.,1.]
        self.assertEqual(self.run_cli().returncode,0)
        view=json.loads(self.summary.read_text())['views']['window30']
        windows=[w for scope in view['per_mode_surface'] for w in scope['flagged_drift_windows']]
        self.assertTrue(windows)
        for window in windows:
            self.assertEqual(set(window),{'start_date','end_date'})
            for value in window.values():self.assertRegex(value,r'^2020-01-[0-9]{2}$')

    def test_encoder_freeze_unknown_not_backfilled(self):
        self.bundle['numerical_evidence'].pop('encoder_frozen_at')
        self.assertEqual(self.run_cli().returncode,0)
        report=json.loads(self.summary.read_text())
        self.assertFalse(report['encoder_metadata_available'])
        self.assertEqual(report['adapter_unavailable']['encoder_pin_or_freeze_unknown'],32)
        facet=report['views']['window30']['facets']['humor']
        self.assertTrue(facet['outcomes_unassessed']);self.assertIsNone(facet['positive_acts'])

    def test_private_source_receipts_retain_unknown_model_and_fallback(self):
        row=next(r for r in self.bundle['rows'] if r['role']=='assistant')
        row['served_model']=None;row['fallback']=None;row['provenance']={'synthetic_extra':'retained'}
        self.assertEqual(self.run_cli().returncode,0)
        report=json.loads(self.output.read_text());receipt=report['source_receipts'][0]
        self.assertIsNone(receipt['served_model']);self.assertIsNone(receipt['fallback'])
        self.assertEqual(receipt['provenance'],{'synthetic_extra':'retained'})
        self.assertNotIn('synthetic_extra',self.summary.read_text())

    def test_date_windows_contain_dates_only(self):
        self.assertEqual(P.date_windows(['2020-01-03','2020-01-01','2020-01-02','2020-01-05']),
            [{'start_date':'2020-01-01','end_date':'2020-01-03'},{'start_date':'2020-01-05','end_date':'2020-01-05'}])

if __name__=='__main__':unittest.main()

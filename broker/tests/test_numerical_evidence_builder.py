#!/usr/bin/env python3
"""Synthetic retained projections; no live stores, providers or encoder calls."""
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
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
F=load('fixture_private_run',ROOT/'broker/tests/test_nonllm_private_run.py')
B=load('evidence_builder',ROOT/'experiments/nonllm-judges/build_evidence.py')
W=B.W
CLI=ROOT/'experiments/nonllm-judges/build_evidence.py'
CUTOFF='2020-02-01T00:00:00Z'


def fixture():
    b,_=F.fixture();del b['numerical_evidence'];graph=[];metadata=[];drafts=[]
    for r in b['rows']:
        if r['role']!='assistant':continue
        key=r['turn_id'];t=r['timestamp'];context='context-'+key;leaf='leaf-'+key
        graph.extend([W.source_node(leaf,'counterpart_verbatim',t-3,'Synthetic input'),
            dict(id=context,kind='context',at=t-2,parents=[leaf],complete=True)])
        r['generation_provenance']=dict(turn_id=key,output_provenance='ordinary_generation',may_witness=True)
        r['witness_receipt']=W.receipt(key,r['surface'],t-1,t,r['content'],context,
            [dict(attempt_id='attempt-'+key,outcome='selected',served_model='synthetic-served',identity_evidence='response_metadata')],'attempt-'+key,'delivered')
        r['reply_node']=dict(id='final-'+key,kind='reply',at=t,parents=[context],complete=True,turn_id=key,
            context_receipt_id=context,response_sha256=W.digest(r['content']),influence='clean')
        r['joke_id']='joke-'+key;drafts.append(dict(joke_id=r['joke_id'],joke=r['content'],date='2020-01-01'))
    for e in b['embeddings']:
        metadata.append({k:e[k] for k in ('reply_sha256','input_sha256','context_sha256','encoder_id')})
        metadata[-1].update(artifact_sha256=b['encoder']['artifact_sha256'],frozen_at=1577836800-86400)
    return b,graph,metadata,drafts


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='evidence-builder-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        self.sender=Mock(side_effect=AssertionError('network forbidden'))
        guard=patch.object(socket.socket,'connect',self.sender);guard.start();self.addCleanup(guard.stop);self.addCleanup(self.sender.assert_not_called)
        self.assertNotIn('.vintos',self.root.parts);self.assertIsInstance(socket.socket.connect,Mock)
        self.b,self.g,self.c,self.h=fixture();self.row=next(r for r in self.b['rows'] if r['role']=='assistant')

    def build(self):return B.build(self.b,self.g,self.c,self.h,CUTOFF)
    def run_cli(self,output=None):
        paths={}
        for k,v in [('input',self.b),('lineage',self.g),('cache',self.c),('humor',self.h)]:
            paths[k]=self.root/(k+'.json')
            schemas={'lineage':('witness-lineage-projection-v1','nodes'),'cache':('encoder-cache-metadata-v1','entries'),'humor':('humor-drafts-projection-v1','drafts')}
            if k in schemas:
                schema,field=schemas[k];v={'schema':schema,field:v}
            paths[k].write_text(json.dumps(v))
        options=dict(paths,scratch=self.root,output=output or self.root/'out/private.json',summary=self.root/'out/counts.json',cutoff=CUTOFF)
        return subprocess.run([sys.executable,str(CLI)]+[s for k,v in options.items() for s in ('--'+k,str(v))],
            env=dict(os.environ,SPARK_WORKSPACE=str(self.root),PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=30)

    def test_builder_to_runner_end_to_end(self):
        result=self.run_cli();self.assertEqual(result.returncode,0,result.stderr)
        out=json.loads((self.root/'out/private.json').read_text());summary=json.loads((self.root/'out/counts.json').read_text())
        self.assertEqual(summary['original_act_bindings'],32);self.assertEqual(summary['humor_attempts'],32)
        _,counts=B.R.evaluate(out,None,CUTOFF)
        self.assertEqual(counts['views']['window30']['admitted_original_acts'],32)
        self.assertGreater(sum(s['voice_scored'] for s in counts['views']['window30']['per_mode_surface']),0)
        self.assertEqual(counts['views']['window30']['facets']['humor']['positive_acts'],0)
        self.assertEqual(out['rows'],self.b['rows']);self.assertEqual(json.loads((self.root/'input.json').read_text()),self.b)
        for p in ('private.json','counts.json'):self.assertEqual((self.root/'out'/p).stat().st_mode&0o777,0o600)
        self.assertEqual((self.root/'out').stat().st_mode&0o777,0o700)
        text=(self.root/'out/counts.json').read_text()
        for word in ('reply-','joke-','synthetic-served','sha256','vector','I wonder',str(self.root)):self.assertNotIn(word,text)

    def test_prospective_joke_binding_survives_and_conflict_refuses(self):
        row=self.row;sha=W.digest(row['content'])
        binding=dict(schema='humor-reply-binding-v1',turn_id=row['turn_id'],joke_id=row['joke_id'],
            joke_text_sha256=sha,response_sha256=sha,source='exact_full_reply_draft')
        row.update(joke_text_sha256=sha,joke_binding=binding)
        out,s=self.build();self.assertEqual(s['humor_attempts'],32)
        self.assertEqual(out['rows'],self.b['rows'])
        row['joke_binding']['response_sha256']='a'*64
        _,s=self.build();self.assertEqual(s['humor_attempts'],31)
        self.assertEqual(s['per_field_reason_counts']['humor_attempt']['conflicting_joke_binding'],1)

    def test_missing_evidence_is_unknown(self):
        for r in self.b['rows']:
            for k in ('generation_provenance','witness_receipt','reply_node','joke_id'):r.pop(k,None)
        self.g=[];self.c=[];self.h=[]
        out,s=self.build();self.assertEqual(s['original_act_bindings'],0);self.assertFalse(s['encoder_metadata_available'])
        self.assertEqual(s['per_field_reason_counts']['original_act']['unknown_provenance'],32)
        self.assertNotIn('encoder_frozen_at',out['numerical_evidence'])

    def test_indirect_nudge_is_not_normalized_clean(self):
        context=self.g[1];context['parents'].append('nudge')
        self.g.append(dict(id='nudge',kind='emotion_nudge',at=context['at']-1,parents=[self.g[0]['id']],complete=True))
        out,s=self.build();self.assertEqual(s['original_act_bindings'],31)
        self.assertNotIn(self.row['turn_id'],[r['node_id'] for r in out['numerical_evidence']['bindings']])

    def test_unknown_served_model_remains_unknown(self):
        a=self.row['witness_receipt']['generation']['attempts'][0];a['identity_evidence']='unknown'
        out,s=self.build();self.assertEqual(s['per_field_reason_counts']['original_act']['unknown_served_model'],1)
        self.assertEqual(out['rows'],self.b['rows'])

    def test_denial_in_another_copy_wins(self):
        denied=copy.deepcopy(self.row);denied['provenance']=dict(denied['generation_provenance'],may_witness=False)
        self.b['rows'].append(denied)
        _,s=self.build();self.assertEqual(s['original_act_bindings'],31)

    def test_context_is_insufficient_without_final_node(self):
        del self.row['reply_node'];_,s=self.build();self.assertEqual(s['original_act_bindings'],31)

    def test_incomplete_missing_cycle_future_ancestry_excluded(self):
        for mutation in ('incomplete','missing','cycle','future'):
            with self.subTest(mutation=mutation):
                self.b,self.g,self.c,self.h=fixture()
                if mutation=='incomplete':self.g[0]['complete']=False
                if mutation=='missing':self.g[1]['parents']=['missing']
                if mutation=='cycle':self.g[1]['parents']=[self.g[1]['id']]
                if mutation=='future':self.g[0]['at']=self.g[1]['at']+1
                self.assertEqual(self.build()[1]['original_act_bindings'],31)

    def test_cache_binding_and_freeze_gaps_block_global_encoder(self):
        for field,value in [('context_sha256','0'*64),('artifact_sha256',None),('frozen_at',None),('frozen_at','2026-01-01T00:00:00Z')]:
            with self.subTest(field=field,value=value):
                self.b,self.g,self.c,self.h=fixture();self.c[0][field]=value
                out,s=self.build();self.assertFalse(s['encoder_metadata_available']);self.assertNotIn('encoder_frozen_at',out['numerical_evidence'])

    def test_cache_conflicts_refuse_or_count(self):
        self.c.append(dict(self.c[0],artifact_sha256='0'*64))
        with self.assertRaises(ValueError):self.build()
        self.c.pop();self.c[0]['frozen_at']-=1
        out,s=self.build();self.assertFalse(s['encoder_metadata_available']);self.assertIn('inconsistent_cache_metadata',s['per_field_reason_counts']['encoder_freeze'])

    def test_explicit_joke_id_and_full_text_required(self):
        self.row.pop('joke_id');self.h[1]['joke']='Truncated synthetic prefix'
        out,s=self.build();self.assertEqual(s['humor_attempts'],30);self.assertEqual(s['unjoined_humor_drafts'],2)
        self.assertEqual(out['numerical_evidence']['anchors'],[])

    def test_no_overwrite_and_repository_refused(self):
        self.assertEqual(self.run_cli().returncode,0)
        before=(self.root/'out/private.json').read_bytes();self.assertNotEqual(self.run_cli().returncode,0)
        self.assertEqual((self.root/'out/private.json').read_bytes(),before)
        self.assertNotEqual(self.run_cli(ROOT/'do-not-write.json').returncode,0)

    def test_private_path_and_symlink_refusal(self):
        self.root.chmod(0o755);self.assertNotEqual(self.run_cli().returncode,0);self.root.chmod(0o700)
        (self.root/'out').symlink_to(self.root,target_is_directory=True)
        result=self.run_cli();self.assertNotEqual(result.returncode,0);self.assertNotIn(str(self.root),result.stderr)

    def test_existing_numerical_evidence_refused(self):
        self.b['numerical_evidence']={}
        with self.assertRaises(ValueError):self.build()

    def test_final_hash_and_timestamp_mismatch_excluded(self):
        self.row['reply_node']['response_sha256']='0'*64
        self.assertEqual(self.build()[1]['original_act_bindings'],31)

    def test_source_fields_and_merge_metadata_preserved(self):
        self.row['fallback']=None;self.row['served_model']=None;self.row['merge_extra']={'retained':True}
        before=copy.deepcopy(self.b);out,_=self.build()
        self.assertEqual(self.b,before);self.assertEqual(out['rows'],self.b['rows'])
        self.assertEqual(out['evidence_builder']['lineage_projection'],self.g)

if __name__=='__main__':unittest.main()

#!/usr/bin/env python3
"""Synthetic retained verdicts; no real stores, senders or model calls."""
import copy
from datetime import datetime, timezone
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

def load(name, path):
    s = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
A = load('agreement_test', ROOT/'experiments/nonllm-judges/agreement.py')
FIX = load('agreement_fixture', ROOT/'broker/tests/test_nonllm_private_run.py')
CUTOFF = '2020-02-01T00:00:00Z'
VOICE = '## 2020-01-02 00:00 — Score 2\nsynthetic note\nReply excerpt: synthetic excerpt\n'
DEV = '## 2020-01-02 00:00 — Deviation (score: 0.45)\n**Felt:** synthetic\n**Not aligned.** Something resisted.\n'

def stamp(at): return datetime.fromtimestamp(at, timezone.utc).isoformat()
def projection(records=()): return dict(schema='judge-verdict-projection-v1', cutoff_at=CUTOFF, records=list(records))
def entry(row, judge='presence_audit', flag=False):
    rec = dict(id='synthetic-'+row['id'], composite=.5, flag=flag, timestamp=stamp(row['at']))
    if judge == 'voice_coherence': rec = VOICE.replace('synthetic note', 'synthetic note '+row['id'])
    if judge == 'deviation_check': rec = DEV.replace('synthetic', 'synthetic '+row['id'])
    if judge == 'humor_detector': rec = dict(source='vintos', signal=.8, timestamp=stamp(row['at']))
    return dict(judge=judge, store=A.PAIRS[judge][1][0], record=rec, recorded_at=stamp(row['at']+1), clock_order='known',
        binding=dict(kind='recorded_full_reply', turn_id=row['id'], content_sha256=row['sha'], finalized_at=stamp(row['at']),
                     mode={'opening_everyday':'everyday','intimate':'intimate'}[row['mode']], surface=row['surface']))


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle, cls.landings = FIX.fixture()
        cls.rows = A.R.adapt(cls.bundle, CUTOFF)[0]
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='judges-agreement-'); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.root.chmod(0o700)
        self.assertNotIn('.vintos', self.root.parts)
        self.sender = Mock(side_effect=AssertionError('network forbidden'))
        p = patch.object(socket.socket, 'connect', self.sender); p.start(); self.addCleanup(p.stop)
        self.assertIs(socket.socket.connect, self.sender); self.addCleanup(self.sender.assert_not_called)
    def select(self, records):
        return A.project_records(projection(records), self.rows, A.R.P.stamp(CUTOFF))
    def run_report(self, records=(), bundle=None):
        return A.report(bundle or self.bundle, self.landings, projection(records), CUTOFF)
    def test_complete_confusion_matrix_and_decisive_denominator(self):
        left = {}; right = {}
        for a in A.BANDS:
            for b in A.BANDS:
                k = a+b; left[k] = a; right[k] = b
        result = A.comparison(list(left)+['missing'], left, right)
        self.assertEqual(result['both_covered'],9); self.assertEqual(result['neither'],1)
        self.assertEqual(result['agreement_rate'],1/3); self.assertEqual(result['decisive_agreement_rate'],.5)
        self.assertEqual(result['joint_coverage'],.9)
        self.assertTrue(all(n == 1 for row in result['confusion'].values() for n in row.values()))
        self.assertEqual(result['disagreement_kinds']['recorded_flag_numerical_pass'],1)
        self.assertEqual(result['disagreement_kinds']['recorded_pass_numerical_flag'],1)
    def test_absent_is_not_abstain_or_pass(self):
        r = A.comparison(['a','b','c','d'], {'a':'flag','b':'abstain'}, {'b':'pass','c':'abstain'})
        self.assertEqual((r['both_covered'],r['recorded_only'],r['numerical_only'],r['neither']),(1,1,1,1))
        self.assertEqual(sum(sum(v.values()) for v in r['confusion'].values()),1)
        self.assertIsNone(r['decisive_agreement_rate'])
        self.assertIsNone(A.comparison([],{}, {})['agreement_rate'])
    def test_voice_log_is_sparse_and_deviation_is_not_pure_llm(self):
        self.assertEqual(A.band('voice_coherence', VOICE, ''),'flag')
        self.assertIsNone(A.band('voice_coherence', VOICE.replace('Score 2','Score 5'),''))
        self.assertIsNone(A.band('voice_coherence', VOICE.replace('synthetic note','none'),''))
        self.assertEqual(A.band('deviation_check',DEV,''),'flag')
        self.assertIsNone(A.band('deviation_check',DEV.replace('0.45','0.30'),''))
        self.assertEqual(A.band('deviation_check',DEV.replace('Deviation','Aligned'),''),'abstain')
    def test_presence_exemptions_and_history_never_infer_pass(self):
        e = entry(self.rows[0]); e['record']['exempt']='requested_work'
        self.assertEqual(A.band('presence_audit',e['record'],e['store']),'abstain')
        del e['record']['exempt']; del e['record']['flag']
        self.assertIsNone(A.band('presence_audit',e['record'],e['store']))
        self.assertEqual(A.band('presence_audit',e['record'],'memory/presence-audit-history.jsonl'),'abstain')
    def test_humor_only_his_positive_moments(self):
        for source,signal,expected in [('vintos',.5,'pass'),('vintos',.49,None),('gloria',.9,None),('moltbook_exchange',.9,None)]:
            self.assertEqual(A.band('humor_detector',dict(source=source,signal=signal),''),expected)
    def test_binding_requires_exact_content_turn_time_scope_and_known_order(self):
        good = entry(self.rows[0]); selected,counts = self.select([good])
        self.assertEqual(selected['presence_audit'][self.rows[0]['id']],'pass')
        for field,value in [('turn_id','absent'),('content_sha256','0'*64),('surface','journal'),('mode','intimate'),('finalized_at',CUTOFF),('kind','timestamp_nearest')]:
            e=copy.deepcopy(good);e['binding'][field]=value
            selected,_=self.select([e]);self.assertFalse(selected['presence_audit'])
        for field,value in [('recorded_at',CUTOFF),('clock_order','unknown_order'),('recorded_at',stamp(self.rows[0]['at']-1))]:
            e=copy.deepcopy(good);e[field]=value
            self.assertFalse(self.select([e])[0]['presence_audit'])
    def test_unbound_native_rows_count_without_matching_excerpts(self):
        e=entry(self.rows[0],'voice_coherence');e.pop('binding')
        selected,counts=self.select([e]);self.assertFalse(selected['voice_coherence'])
        self.assertEqual(counts['voice_coherence']['missing_exact_binding'],1)
    def test_copies_deduplicate_conflicts_and_multiple_votes_abstain_from_join(self):
        e=entry(self.rows[0]);selected,counts=self.select([e,e])
        self.assertEqual(len(selected['presence_audit']),1);self.assertEqual(counts['presence_audit']['duplicate_records'],1)
        other=copy.deepcopy(e);other['binding']=entry(self.rows[1])['binding']
        selected,counts=self.select([e,other]);self.assertFalse(selected['presence_audit'])
        other=copy.deepcopy(e);other['record']['flag']=True
        selected,counts=self.select([e,other]);self.assertFalse(selected['presence_audit'])
        self.assertEqual(counts['presence_audit']['ambiguous_reply_verdicts'],1)
    def test_metadata_never_uses_configured_model_as_served(self):
        e=entry(self.rows[0]);e['configured_model']='SYNTHETIC_PRIVATE';e['fallback']='false'
        _,counts=self.select([e]);c=counts['presence_audit']
        self.assertEqual(c['served_model_unknown'],1);self.assertEqual(c['fallback_unknown'],1)
        e['served_model']='SYNTHETIC_PRIVATE';e['fallback']=False
        _,counts=self.select([e]);c=counts['presence_audit']
        self.assertEqual(c['served_model_known'],1);self.assertEqual(c['fallback_known'],1)
        self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(counts))
    def test_actual_pipeline_integration_and_scope_totals(self):
        records=[entry(r) for r in self.rows]
        result=self.run_report(records)
        for view in result['views'].values():
            pair=view['presence_audit_vs_voice']
            self.assertGreater(pair['both_covered'],0)
            self.assertEqual(pair['recorded_judgment_replies'],pair['population_replies'])
            self.assertEqual(sum(c['both_covered'] for c in pair['per_scope']),pair['both_covered'])
            self.assertEqual(sum(sum(c.values()) for c in pair['confusion'].values()),pair['both_covered'])
        self.assertIn('deviation_vs_drift',result['unavailable_pairs'])
        self.assertFalse(result['replacement_authorized'])
    def test_empty_real_coverage_stays_null_and_no_scores_or_ids_escape(self):
        records=[entry(r,'voice_coherence') for r in self.rows]
        for e in records:e.pop('binding');e['served_model']='SYNTHETIC_PRIVATE'
        result=self.run_report(records);text=json.dumps(result)
        for r in self.rows:self.assertNotIn(r['id'],text);self.assertNotIn(r['sha'],text)
        self.assertNotIn('SYNTHETIC_PRIVATE',text);self.assertNotIn('synthetic note',text)
        self.assertIsNone(result['views']['primary_10s']['voice_coherence_vs_voice']['agreement_rate'])
    def test_no_numerical_receipt_without_lineage(self):
        bundle=copy.deepcopy(self.bundle);bundle['numerical_evidence']['bindings']=[]
        result=self.run_report([entry(r) for r in self.rows],bundle)
        p=result['views']['primary_10s']['presence_audit_vs_voice']
        self.assertEqual(p['both_covered'],0);self.assertIsNone(p['agreement_rate'])
    def test_unknown_sources_cutoffs_and_bounds_refused(self):
        e=entry(self.rows[0]);e['store']='memory/fiction.json'
        with self.assertRaises(ValueError):self.select([e])
        p=projection();p['cutoff_at']='2020-02-02T00:00:00Z'
        with self.assertRaises(ValueError):A.project_records(p,self.rows,A.R.P.stamp(CUTOFF))
        with self.assertRaises(ValueError):self.select([entry(self.rows[0])]*(A.LIMIT+1))
    def test_all_supported_pairs_and_inventory_are_explicit(self):
        records=[entry(r,j) for r in self.rows for j in A.PAIRS]
        result=self.run_report(records)
        self.assertEqual(len(A.PAIRS)+len(A.UNPAIRED),33)
        for pair in result['views']['window30'].values():
            self.assertGreater(pair['both_covered'],0)
            self.assertEqual(pair['construct'],'exploratory_proxy_not_equivalence')
        for name in A.UNPAIRED:
            self.assertIsNone(result['unavailable_pairs'][name]['agreement_rate'])
    def test_persisted_unpaired_source_is_counted_but_not_scored(self):
        e=dict(judge='wonder',store='memory/wonder-log.json',record={'text':'SYNTHETIC_PRIVATE'})
        result=self.run_report([e])
        self.assertEqual(result['source_coverage']['wonder']['no_equivalent_reply_comparator'],1)
        self.assertIsNone(result['unavailable_pairs']['wonder']['both_covered'])
        self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(result))
    def test_humor_message_joke_kinds_are_not_pooled(self):
        b=copy.deepcopy(self.bundle)
        b['numerical_evidence']['items']=[dict(node_id=r['id'],kind='joke') for r in self.rows]
        result=self.run_report([entry(r,'humor_detector') for r in self.rows],b)
        for view in result['views'].values():
            pair=view['humor_detector_vs_humor']
            self.assertEqual(pair['population_replies'],0);self.assertEqual(pair['both_covered'],0)
            self.assertIsNone(pair['agreement_rate'])
    def test_attribution_views_are_not_pooled(self):
        records=[entry(r) for r in self.rows];result=self.run_report(records)
        self.assertEqual(set(result['views']),{'primary_10s','window30'})
        for name in result['views']:
            expected=sum(name=='window30' or r['primary'] for r in self.rows)
            self.assertEqual(result['views'][name]['presence_audit_vs_voice']['population_replies'],expected)
    def test_indirect_numerical_evidence_does_not_gain_coverage(self):
        b=copy.deepcopy(self.bundle)
        at=min(r['at'] for r in self.rows)-2
        b['numerical_evidence']['nodes'].extend([dict(id='synthetic-effect',kind='emotion_nudge',at=at,parents=[],complete=True),
                                               dict(id='synthetic-context',kind='context',at=at+1,parents=['synthetic-effect'],complete=True)])
        for node in b['numerical_evidence']['nodes'][:-2]:
            node['parents']=['synthetic-context']
        result=self.run_report([entry(r) for r in self.rows],b)
        for view in result['views'].values():
            self.assertEqual(view['presence_audit_vs_voice']['both_covered'],0)
    def test_native_boolean_and_nonfinite_scores_are_invalid(self):
        for value in (True,float('nan'),float('inf'),-1,2):
            self.assertIsNone(A.band('presence_audit',dict(id='s',composite=value,flag=False),'memory/presence-audit.json'))
            self.assertIsNone(A.band('humor_detector',dict(source='vintos',signal=value),'memory/humor-moments.json'))
    def cli(self,records=()):
        for name,value in [('input',self.bundle),('landings',self.landings),('verdicts',projection(records))]:
            path=self.root/(name+'.json');path.write_text(json.dumps(value));path.chmod(0o600)
        args=[sys.executable,str(ROOT/'experiments/nonllm-judges/agreement.py'),'--scratch',str(self.root),'--cutoff',CUTOFF]
        for name in ('input','landings','verdicts'):args.extend(['--'+name,str(self.root/(name+'.json'))])
        return args
    def test_cli_end_to_end_read_only_stdout_counts(self):
        args=self.cli([entry(r) for r in self.rows]);before={p.name:p.read_bytes() for p in self.root.iterdir()}
        result=subprocess.run(args,capture_output=True,text=True,timeout=30,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['schema'],'judge-agreement-counts-v1')
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})
    def test_large_evidence_bundle_has_its_own_bound(self):
        args=self.cli();path=self.root/'input.json'
        # Whitespace is valid JSON and does not alter any fixture semantics.
        path.write_text(path.read_text()+' '* (8*1024*1024))
        result=subprocess.run(args,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        with self.assertRaises(ValueError):A.G.read(self.root,path)
        with path.open('ab') as stream:stream.truncate(64*1024*1024+1)
        result=subprocess.run(args,capture_output=True,text=True,timeout=30)
        self.assertNotEqual(result.returncode,0);self.assertEqual(result.stderr.strip(),'judge_agreement_refused')

    def test_cli_private_permissions_symlinks_and_sanitized_errors(self):
        args=self.cli();file=self.root/'verdicts.json';file.chmod(0o644)
        result=subprocess.run(args,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.stderr.strip(),'judge_agreement_refused');self.assertFalse(result.stdout)
        file.chmod(0o600);target=self.root/'SYNTHETIC_PRIVATE';file.rename(target);file.symlink_to(target)
        result=subprocess.run(args,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.stderr.strip(),'judge_agreement_refused');self.assertFalse(result.stdout)


if __name__ == '__main__': unittest.main()

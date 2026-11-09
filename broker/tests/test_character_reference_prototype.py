#!/usr/bin/env python3
"""Synthetic cached-vector evaluation with isolated paths and forbidden external sends."""
import copy
from collections import defaultdict
from datetime import datetime,timezone,timedelta
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
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('character_prototype',ROOT/'experiments/character-reference/prototype.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)


def fixture():
    encoder=dict(family='nomic',id='synthetic-frozen',revision='synthetic-revision',pooling='mean',normalization='l2',prefix_chars=400,frozen=True)
    bundle=dict(input_kind='synthetic',timezone='America/Chicago',encoder=encoder,rows=[],embeddings=[],controls=[],feedback=[],
        historical_attribution={'compute_ledger':[],'surface_callers':{'fixture-chat':['router:fixture']},'window_seconds':10})
    start=datetime(2020,1,1,18,tzinfo=timezone.utc)
    for d in range(16):
        at=(start+timedelta(days=d)).timestamp()
        for j in range(10 if d<4 else 2):bundle['rows'].append(dict(role='user',turn_id=f'user-{d}-{j}',timestamp=at+j,content='synthetic user event'))
        for j,model in enumerate(('claude-synthetic','grok-synthetic')):
            text=f'I wonder about synthetic sample {d} and option {j}. Shall we try this?'
            tid=f'reply-{d}-{j}';ts=at+100+j*100;v=np.asarray([1.,.03*d+.01*j]);v=(v/np.linalg.norm(v)).tolist()
            row=dict(role='assistant',turn_id=tid,timestamp=ts,content=text,context='synthetic shared topic',surface='fixture-chat',language='en',served_by=model)
            bundle['rows'].append(row)
            bundle['historical_attribution']['compute_ledger'].append(dict(at=ts-1,organ='router:fixture',model=model,provider='synthetic',stage='complete',**{'class':'foreground'}))
            bundle['embeddings'].append(dict(reply_sha256=P.digest(text),input_sha256=P.digest(text),context_sha256=P.digest(row['context']),encoder_id=encoder['id'],vector=v,context_vector=[1.,0.]))
            foreign=f'An unrelated synthetic sample {d} for the alternative case {j} appears.'
            bundle['controls'].append(dict(kind='foreign',matched_reply_id=tid,content=foreign,context=row['context'],language='en',encoder_id=encoder['id'],input_sha256=P.digest(foreign),context_sha256=P.digest(row['context']),vector=[-1.,0.],context_vector=[1.,0.]))
            bundle['feedback'].append(dict(reply_id=tid,reply_sha256=P.digest(text),link='exact_reply',witnessed=True,kind='laugh',value='hahaha',timestamp=ts+10))
    return bundle


def legacy_scores(row,reference):
    groups=defaultdict(list)
    for r in reference:groups[r['day']].append(r['vector'])
    centers=[]
    for values in groups.values():
        c=np.mean(values,axis=0);norm=np.linalg.norm(c)
        if norm>1e-12:centers.append(c/norm)
    if not centers:return None
    styles=np.asarray([r['style'] for r in reference]);mu=styles.mean(axis=0)
    scale=np.maximum(styles.std(axis=0),.05)
    all_center=np.mean([r['vector'] for r in reference],axis=0)
    norm=np.linalg.norm(all_center)
    recent_days=sorted(groups)[-2:]
    recent=np.mean([r['vector'] for r in reference if r['day'] in recent_days],axis=0)
    recent_norm=np.linalg.norm(recent)
    return {'semantic':max(float(row['vector']@c) for c in centers),
            'style':-float(np.sqrt(np.mean(((row['style']-mu)/scale)**2))),
            'centroid':float(row['vector']@all_center/norm) if norm>1e-12 else None,
            'recent_centroid':float(row['vector']@recent/recent_norm) if recent_norm>1e-12 else None}


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='character-reference-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        self.sender=Mock(side_effect=AssertionError('external action forbidden'))
        for p in (patch.dict(os.environ,SPARK_WORKSPACE=str(self.root)),patch.object(socket.socket,'connect',self.sender)):
            p.start();self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertNotIn('.vintos',self.root.parts);self.assertIsInstance(self.sender,Mock)
        self.bundle=fixture();self.cutoff='2020-02-01T00:00:00Z'

    def test_familiarity_foreign_controls_intervals_and_no_day_leakage(self):
        report,private=P.run(self.bundle,self.cutoff)
        self.assertEqual(report['primary_10s']['status'],{'scored':32})
        self.assertEqual(len(report['coverage']['candidate_days']),4)
        for row in private:self.assertNotIn(row['day'],row['reference_days'])
        metric=report['primary_10s']['metrics']['foreign_semantic_paired_win']
        self.assertEqual(metric['mean'],1.);self.assertEqual(metric['interval95'],[1.,1.])
        self.assertEqual(report['primary_10s']['metrics']['shuffled_own_semantic_marginal_auc']['mean'],.5)
        self.assertEqual(len(report['primary_10s']['shared_day_family_differences']),1)
        self.assertEqual(report['strict_admission_effect'],'none')
        for secret in ('reply-0-0','synthetic shared topic','synthetic-frozen','I wonder'):
            self.assertNotIn(secret,json.dumps(report))

    def test_uncertain_attribution_and_thirty_second_view_stay_separate(self):
        ledger=self.bundle['historical_attribution']['compute_ledger'];ledger[-1]['at']-=20
        report,_=P.run(self.bundle,self.cutoff)
        self.assertEqual(report['primary_10s']['status']['scored'],31)
        self.assertEqual(report['sensitivity_window30']['status']['scored'],32)
        ledger.clear();report,_=P.run(self.bundle,self.cutoff)
        self.assertEqual(report['primary_10s']['status'],{})
        self.assertEqual(report['coverage']['excluded']['attribution_not_admitted'],32)

    def test_recorded_label_needs_independent_observed_agreement(self):
        original=P.attribution
        def observed(*args,**kwargs):
            report,details=original(*args,**kwargs)
            d=details[-1];d.update(observed_model=d['recorded_label'],ledger_model=None,join_state='no_matching_call')
            return report,details
        with patch.object(P,'attribution',side_effect=observed):report,_=P.run(self.bundle,self.cutoff)
        self.assertEqual(report['coverage']['admission_bases']['label_observed_agreement'],1)
        self.assertEqual(report['primary_10s']['status']['scored'],32)

    def test_feedback_requires_exact_witnessed_reply_and_is_not_negative_label(self):
        self.bundle['feedback'][0]['reply_sha256']='0'*64
        self.bundle['feedback'][1]['witnessed']=False
        self.bundle['feedback'][2].update(kind='rating',value=2)
        self.bundle['feedback'][3].update(kind='rating',value=5)
        report,_=P.run(self.bundle,self.cutoff)
        self.assertEqual(report['coverage']['positive_reply_links'],29)
        self.assertEqual(report['coverage']['feedback']['unlinked_or_outside'],2)
        self.assertNotIn('negative',report['coverage']['feedback'])

    def test_duplicate_conflicting_and_repeated_versions(self):
        row=next(r for r in self.bundle['rows'] if r['role']=='assistant')
        self.bundle['rows'].append(copy.deepcopy(row))
        report,_=P.run(self.bundle,self.cutoff);self.assertEqual(report['primary_10s']['status']['scored'],32)
        self.bundle['rows'][-1]['content']='different synthetic version'
        with self.assertRaises(ValueError):P.run(self.bundle,self.cutoff)

    def test_encoder_contract_and_cached_input_conflicts_fail_closed(self):
        for mutate in (lambda b:b['encoder'].update(frozen=False),
                       lambda b:b['embeddings'][0].update(encoder_id='different'),
                       lambda b:b['embeddings'][0].update(input_sha256='0'*64),
                       lambda b:b['embeddings'][0].update(vector=[2.,0.])):
            bad=copy.deepcopy(self.bundle);mutate(bad)
            with self.assertRaises(ValueError):P.run(bad,self.cutoff)
        bad=copy.deepcopy(self.bundle);bad['embeddings'].append(dict(bad['embeddings'][0],vector=[0.,1.]))
        with self.assertRaises(ValueError):P.run(bad,self.cutoff)

    def test_controls_must_match_topic_language_length_and_not_repeat_own_text(self):
        self.bundle['controls'][0]['language']='fr'
        self.bundle['controls'][1]['context_vector']=[-1.,0.]
        self.bundle['controls'].append(copy.deepcopy(self.bundle['controls'][2]))
        report,_=P.run(self.bundle,self.cutoff)
        self.assertEqual(report['coverage']['excluded']['control_not_matched'],2)
        self.assertEqual(report['primary_10s']['metrics']['foreign_semantic_paired_win']['observations'],30)

    def test_insufficient_reference_and_single_day_intervals_are_unknown(self):
        rows,controls,days,positive,_=P.prepare(self.bundle,self.cutoff)
        report,private=P.evaluate(rows,controls,days[:1],positive)
        self.assertEqual(report['status'],{'insufficient_reference_days':32});self.assertEqual(private,[])
        self.assertIsNone(P.summarize([('one',.5)])['interval95'])

    def test_style_changes_and_bootstrap_are_deterministic(self):
        self.assertFalse(np.array_equal(P.style('I wonder?'),P.style('UPPERCASE!!!\n\nHELLO')))
        self.assertEqual(P.summarize([('a',0),('b',1)]),P.summarize([('a',0),('b',1)]))
        before=copy.deepcopy(self.bundle);P.run(self.bundle,self.cutoff);self.assertEqual(before,self.bundle)

    def test_nonreference_evaluation_changes_do_not_fit_other_scores(self):
        rows,controls,days,positive,_=P.prepare(self.bundle,self.cutoff)
        _,original=P.evaluate(rows,controls,days,positive)
        altered=copy.deepcopy(rows);target=next(r for r in altered if r['day'] not in days)
        target['vector']=np.asarray([-1.,0.]);target['style']=P.style('DIFFERENT!!!')
        _,changed=P.evaluate(altered,controls,days,positive)
        old={r['turn_id']:r for r in original};new={r['turn_id']:r for r in changed}
        for key in old:
            if key!=target['id']:self.assertEqual(old[key],new[key])
        self.assertNotEqual(old[target['id']]['percentiles'],new[target['id']]['percentiles'])

    def test_context_family_comparison_matches_before_inspecting_scores(self):
        rows,controls,days,positive,_=P.prepare(self.bundle,self.cutoff)
        report,_=P.evaluate(rows,controls,days,positive)
        comparison=report['context_matched_family_comparisons']['pairs'][0]
        self.assertEqual(comparison['matched_pairs'],16)
        self.assertEqual(comparison['left_unmatched'],0)
        self.assertEqual(comparison['percentile_differences']['semantic']['days'],16)
        self.assertIsNotNone(comparison['percentile_differences']['style']['interval95'])
        def pairs(rs):
            return [(a['id'],b['id']) for a,b,c in P.context_pairs(
                [r for r in rs if r['family']==P.FAMILIES[0]],
                [r for r in rs if r['family']==P.FAMILIES[1]])]
        before=pairs(rows)
        for r in rows:r['vector']=-r['vector'];r['style']=r['style']*100
        self.assertEqual(before,pairs(list(reversed(rows))))

    def test_shared_day_does_not_imply_shared_context(self):
        rows,controls,days,positive,_=P.prepare(self.bundle,self.cutoff)
        for r in rows:
            if r['family']==P.FAMILIES[1]:r['context_vector']=-r['context_vector']
        report,_=P.evaluate(rows,controls,days,positive)
        self.assertEqual(report['shared_day_family_differences'][0]['days'],16)
        comparison=report['context_matched_family_comparisons']['pairs'][0]
        self.assertEqual(comparison['matched_pairs'],0)
        self.assertEqual(comparison['left_unmatched'],16)
        self.assertIsNone(comparison['percentile_differences']['semantic']['mean'])
        self.assertIsNone(comparison['percentile_differences']['semantic']['interval95'])

    def test_context_pairing_is_one_to_one_with_language_length_and_day_bounds(self):
        rows,_,_,_,_=P.prepare(self.bundle,self.cutoff)
        a=rows[0];b=rows[1];other=copy.deepcopy(b);other['id']='extra'
        duplicate=copy.deepcopy(a);duplicate['id']='additional'
        pairs=P.context_pairs([a,duplicate],[b,other])
        self.assertEqual(len(pairs),2)
        self.assertEqual(len({r['id'] for _,r,_ in pairs}),2)
        self.assertEqual(len(P.context_pairs([a,duplicate],[b])),1)
        for fields in ({'language':'fr'},{'language':None},{'text':'x'},
                       {'day':'1900-01-01'},{'context_vector':np.asarray([-1.,0.])}):
            bad=dict(b,**fields);self.assertEqual(P.context_pairs([a],[bad]),[])
        tied=P.context_pairs([a],[b,other])[0][1]['id']
        self.assertEqual(tied,min(b['id'],other['id']))

    def test_fold_reuse_matches_original_rescoring_exactly(self):
        rows,controls,days,positive,_=P.prepare(self.bundle,self.cutoff)
        for degenerate in (False,True):
            if degenerate:
                for i,r in enumerate(rows):r['vector']=np.asarray([(-1.)**i,0.])
            optimized=P.evaluate(rows,controls,days,positive)
            with patch.object(P,'reference_statistics',side_effect=lambda ref:list(ref)), \
                    patch.object(P,'score_statistics',side_effect=lambda row,ref:legacy_scores(row,ref) if ref is not None else None):
                original=P.evaluate(rows,controls,days,positive)
            self.assertEqual(optimized,original)

    def test_statistics_build_count_depends_on_days_not_reply_control_count(self):
        rows,controls,days,positive,_=P.prepare(self.bundle,self.cutoff)
        build=P.reference_statistics
        with patch.object(P,'reference_statistics',wraps=build) as spy:
            P.evaluate(rows,controls,days,positive)
            original_count=spy.call_count
        self.assertEqual(original_count,92)
        expanded=[]
        for i in range(4):
            for row in rows:
                if row['day'] not in days:expanded.append(dict(row,id=row['id']+'-extra-'+str(i)))
        with patch.object(P,'reference_statistics',wraps=build) as spy:
            P.evaluate(rows+expanded,controls*4,days,positive)
            self.assertEqual(spy.call_count,original_count)

    def test_reference_statistics_do_not_survive_into_later_runs(self):
        rows,controls,days,positive,_=P.prepare(self.bundle,self.cutoff)
        first=P.evaluate(rows,controls,days,positive)
        for row in rows:
            if row['day'] in days:row['vector']=-row['vector']
        changed=P.evaluate(rows,controls,days,positive)
        self.assertNotEqual(first,changed)
        with patch.object(P,'reference_statistics',side_effect=lambda ref:list(ref)), \
                patch.object(P,'score_statistics',side_effect=lambda row,ref:legacy_scores(row,ref) if ref is not None else None):
            self.assertEqual(changed,P.evaluate(rows,controls,days,positive))

    def test_cli_rejects_live_workspace_and_writes_outside_scratch(self):
        source=self.root/'input.json';source.write_text(json.dumps(self.bundle))
        for scratch,output in ((str(ROOT),str(self.root/'result')),(str(self.root),str(self.root.parent/'forbidden-character-output'))):
            result=subprocess.run([sys.executable,str(ROOT/'experiments/character-reference/prototype.py'),
                '--scratch',scratch,'--input',str(source),'--output',output,'--cutoff',self.cutoff],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(Path(output).exists())

    def test_actual_cli_is_private_aggregate_only_and_refuses_overwrite(self):
        source=self.root/'input.json';source.write_text(json.dumps(self.bundle));out=self.root/'result'
        cmd=[sys.executable,str(ROOT/'experiments/character-reference/prototype.py'),'--scratch',str(self.root),'--input',str(source),'--output',str(out),'--cutoff',self.cutoff]
        result=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),{'written':True,'scored':32})
        for p in out.iterdir():self.assertEqual(p.stat().st_mode & 0o777,0o600)
        report=json.loads((out/'aggregate.json').read_text());self.assertEqual(report['input_kind'],'synthetic')
        self.assertNotIn('reply-0-0',json.dumps(report))
        again=subprocess.run(cmd,capture_output=True,text=True);self.assertNotEqual(again.returncode,0)


if __name__=='__main__':unittest.main()

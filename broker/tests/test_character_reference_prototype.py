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


def review_control(item):
    item['review']=dict(reviewed=True,reviewer='reviewer',link='exact_control',
        binding_sha256=P.control_review_binding(item),evidence_sha256=P.digest('synthetic reviewed source'))
    return item


def fixture():
    encoder=dict(family='nomic',id='synthetic-frozen',revision='synthetic-revision',pooling='mean',normalization='l2',prefix_chars=400,frozen=True)
    bundle=dict(input_kind='synthetic',timezone='America/Chicago',encoder=encoder,rows=[],embeddings=[],controls=[],feedback=[],mode_observations=[],
        historical_attribution={'compute_ledger':[],'surface_callers':{'avatar':['router:fixture']},'window_seconds':10})
    start=datetime(2020,1,1,18,tzinfo=timezone.utc)
    for d in range(16):
        at=(start+timedelta(days=d)).timestamp()
        for j in range(10 if d<4 else 2):bundle['rows'].append(dict(role='user',turn_id=f'user-{d}-{j}',timestamp=at+j,content='synthetic user event',surface='avatar'))
        for j,model in enumerate(('claude-synthetic','grok-synthetic')):
            text=f'I wonder about synthetic sample {d} and option {j}. Shall we try this?'
            tid=f'reply-{d}-{j}';ts=at+100+j*100;v=np.asarray([1.,.03*d+.01*j]);v=(v/np.linalg.norm(v)).tolist()
            row=dict(role='assistant',turn_id=tid,timestamp=ts,content=text,context='synthetic shared topic',surface='avatar',language='en',served_by=model)
            bundle['rows'].append(row)
            bundle['mode_observations'].append(dict(reply_id=tid,reply_sha256=P.digest(text),link='exact_reply',
                timestamp=ts-1,mode='opening_everyday',source='router_decision',evidence_sha256=P.digest('synthetic mode evidence '+tid)))
            bundle['historical_attribution']['compute_ledger'].append(dict(at=ts-1,organ='router:fixture',model=model,provider='synthetic',stage='complete',**{'class':'foreground'}))
            bundle['embeddings'].append(dict(reply_sha256=P.digest(text),input_sha256=P.digest(text),context_sha256=P.digest(row['context']),encoder_id=encoder['id'],vector=v,context_vector=[1.,0.]))
            foreign=f'An unrelated synthetic sample {d} for the alternative case {j} appears.'
            bundle['controls'].append(dict(candidate_id='candidate-'+tid,timestamp=ts,surface='avatar',author='non_subject',kind='foreign',mode='opening_everyday',matched_reply_id=tid,content=foreign,context=row['context'],language='en',encoder_id=encoder['id'],input_sha256=P.digest(foreign),context_sha256=P.digest(row['context']),vector=[-1.,0.],context_vector=[1.,0.]))
            review_control(bundle['controls'][-1])
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

    def test_evaluation_annotations_are_exact_linked_and_do_not_change_scores(self):
        baseline,private=P.run(self.bundle,self.cutoff)
        rows=[r for r in self.bundle['rows'] if r['role']=='assistant']
        event=dict(reply_id=rows[0]['turn_id'],reply_sha256=P.digest(rows[0]['content']),
                   link='exact_reply',category='benign_novelty',annotator='owner')
        self.bundle['evaluation_annotations']=[event,dict(event),dict(event,category='refusal',annotator='reviewer'),
            dict(event,reply_sha256='0'*64),dict(event,reply_id='unavailable-private-id')]
        report,after=P.run(self.bundle,self.cutoff)
        self.assertEqual(private,after)
        self.assertEqual(report['coverage']['evaluation_annotations'],
                         {'linked':2,'duplicate':1,'unlinked_or_not_admitted':2})
        groups=report['primary_10s']['evaluation_groups']['groups']
        self.assertEqual(groups['owner']['benign_novelty']['scored_replies'],1)
        self.assertEqual(groups['reviewer']['refusal']['annotated_replies'],1)
        self.assertEqual(groups['owner']['refusal']['annotated_replies'],0)
        self.assertIsNone(groups['owner']['benign_novelty']['percentiles']['semantic']['interval95'])
        self.assertIsNone(groups['owner']['humor']['percentiles']['semantic']['mean'])
        for view in ('primary_10s','sensitivity_window30'):
            report[view].pop('evaluation_groups');baseline[view].pop('evaluation_groups')
            for mode in P.MODES:
                report[view]['per_mode'][mode].pop('evaluation_groups');baseline[view]['per_mode'][mode].pop('evaluation_groups')
        report['coverage'].pop('evaluation_annotations');baseline['coverage'].pop('evaluation_annotations')
        self.assertEqual(report,baseline)

    def test_evaluation_groups_keep_unscored_and_window30_rows_distinct(self):
        last=[r for r in self.bundle['rows'] if r['role']=='assistant'][-1]
        self.bundle['historical_attribution']['compute_ledger'][-1]['at']-=20
        self.bundle['evaluation_annotations']=[dict(reply_id=last['turn_id'],reply_sha256=P.digest(last['content']),
            link='exact_reply',category='opposite_stance',annotator='reviewer')]
        report,_=P.run(self.bundle,self.cutoff)
        self.assertEqual(report['primary_10s']['evaluation_groups']['groups']['reviewer']['opposite_stance']['annotated_replies'],0)
        self.assertEqual(report['sensitivity_window30']['evaluation_groups']['groups']['reviewer']['opposite_stance']['scored_replies'],1)
        rows,controls,days,positive,_=P.prepare(self.bundle,self.cutoff)
        unscored,_=P.evaluate(rows,controls,days[:1],positive)
        group=unscored['evaluation_groups']['groups']['reviewer']['opposite_stance']
        self.assertEqual(group['unscored_replies'],1)
        self.assertIsNone(group['percentiles']['semantic']['mean'])

    def test_evaluation_group_values_are_bounded_and_never_render_free_text(self):
        for event in ({'category':'private free text','annotator':'owner'},
                      {'category':'humor','annotator':'unknown'},None):
            self.bundle['evaluation_annotations']=[event]
            with self.assertRaises(ValueError):P.run(self.bundle,self.cutoff)
        row=next(r for r in self.bundle['rows'] if r['role']=='assistant')
        self.bundle['evaluation_annotations']=[dict(reply_id=row['turn_id'],reply_sha256=P.digest(row['content']),
            link='exact_reply',category='humor',annotator='reviewer',note='private annotation rationale')]
        self.bundle['feedback']=[]
        report,_=P.run(self.bundle,self.cutoff)
        self.assertNotIn('private annotation rationale',json.dumps(report))
        self.assertNotIn(row['turn_id'],json.dumps(report))
        self.assertEqual(report['coverage']['positive_reply_links'],0)
        self.assertNotIn('witnessed_positive_similarity',report['primary_10s']['metrics'])

    def test_summary_renders_aggregate_views_and_never_private_metadata(self):
        report,_=P.run(self.bundle,self.cutoff)
        report['private_rows']='PRIVATE TEXT AND TOKEN'
        text=P.render_summary(report)
        self.assertIn('synthetic fixtures; not findings about real history',text)
        self.assertIn('| Primary 10 s / exact ID | 32 | 32 |',text)
        self.assertIn('Window30 sensitivity',text)
        self.assertIn('No linked evaluation annotations',text)
        for secret in ('PRIVATE TEXT AND TOKEN','reply-0-0','synthetic shared topic','synthetic-frozen'):
            self.assertNotIn(secret,text)
        self.assertEqual(text,P.render_summary(report))
        report['input_kind']='retained_snapshot'
        self.assertIn('supplied copied history',P.render_summary(report))
        report['coverage']['candidate_days'][0]['date']='private injected text'
        with self.assertRaises(ValueError):P.render_summary(report)

    def test_summary_reports_empty_and_insufficient_results_as_unknown(self):
        self.bundle['historical_attribution']['compute_ledger']=[]
        report,_=P.run(self.bundle,self.cutoff)
        text=P.render_summary(report)
        self.assertIn('| Primary 10 s / exact ID | 0 | 0 |',text)
        self.assertIn('| semantic_percentile | unknown | unknown | 0 | 0 |',text)
        self.assertIn('must not be added together',text)
        self.assertIn('No acceptance threshold or identity decision',text)

    def test_reference_family_composition_counts_actual_held_out_folds(self):
        report,_=P.run(self.bundle,self.cutoff)
        composition=report['primary_10s']['reference_family_composition']
        for day in composition['candidate_days']:
            self.assertEqual(day['replies'],2)
            self.assertEqual(day['families'],dict(zip(P.FAMILIES,(1,1,0,0,0))))
        candidates={r['day'] for r in composition['candidate_days']}
        for fold in composition['evaluation_folds']:
            days=3 if fold['day'] in candidates else 4
            self.assertEqual(fold['reference_days'],days)
            self.assertEqual(fold['reference_replies'],days*2)
            self.assertEqual(sum(fold['families'].values()),days*2)
        self.assertIn('Candidate reference composition',P.render_summary(report))

    def test_reference_family_counts_are_view_specific_and_never_impute_missing(self):
        self.bundle['historical_attribution']['compute_ledger'][0]['at']-=20
        report,_=P.run(self.bundle,self.cutoff)
        primary=report['primary_10s']['reference_family_composition']['candidate_days'][0]
        sensitivity=report['sensitivity_window30']['reference_family_composition']['candidate_days'][0]
        self.assertEqual(primary['replies'],1);self.assertEqual(sensitivity['replies'],2)
        self.assertEqual(primary['families'][P.FAMILIES[0]],0)
        self.bundle['historical_attribution']['compute_ledger']=[]
        report,_=P.run(self.bundle,self.cutoff)
        empty=report['primary_10s']['reference_family_composition']
        self.assertEqual(len(empty['candidate_days']),4)
        self.assertTrue(all(r['replies']==0 for r in empty['candidate_days']))
        self.assertEqual(empty['evaluation_folds'],[])

    def test_missing_mode_never_infers_mode_from_family_or_scores_unknown(self):
        self.bundle.pop('mode_observations')
        report,private=P.run(self.bundle,self.cutoff)
        self.assertEqual(report['primary_10s']['status'],{'mode_unknown':32})
        self.assertEqual(private,[])
        self.assertEqual(report['coverage']['mode_observations']['unknown'],32)
        self.assertTrue(all(p['identifiability']=='not_identifiable' for p in
            report['primary_10s']['per_mode']['intimate']['context_matched_family_comparisons']['pairs']))
        self.assertIn('not identifiable',P.render_summary(report))
        self.assertIn('| unknown | 32 / 0 |',P.render_summary(report))

    def test_mode_links_reject_family_proxy_and_keep_conflicts_unknown(self):
        first=self.bundle['mode_observations'][0]
        self.bundle['mode_observations']+=[dict(first,mode='intimate')]
        self.bundle['mode_observations'][1]['reply_sha256']='0'*64
        self.bundle['mode_observations'][2]['timestamp']+=1000
        report,_=P.run(self.bundle,self.cutoff)
        self.assertEqual(report['primary_10s']['status']['mode_unknown'],3)
        self.assertEqual(report['coverage']['mode_observations']['conflicting_replies'],1)
        self.assertEqual(report['coverage']['mode_observations']['unlinked_or_outside'],2)
        self.bundle['mode_observations'][0]['source']='model_family'
        with self.assertRaises(ValueError):P.run(self.bundle,self.cutoff)

    def test_mode_specific_references_do_not_cross_registers(self):
        for event in self.bundle['mode_observations']:
            if event['reply_id'].endswith('-1'):event['mode']='intimate'
        for control in self.bundle['controls']:
            if control['matched_reply_id'].endswith('-1'):control['mode']='intimate'
        report,private=P.run(self.bundle,self.cutoff)
        self.assertEqual(report['primary_10s']['status']['scored'],32)
        for mode in P.MODES[:2]:
            view=report['primary_10s']['per_mode'][mode]
            self.assertEqual(view['status']['scored'],16)
            self.assertTrue(all(p['identifiability']=='not_identifiable' for p in view['context_matched_family_comparisons']['pairs']))
        rows,controls,days,positive,_=P.prepare(self.bundle,self.cutoff)
        before=P.evaluate(rows,controls,days,positive)[1]
        for row in rows:
            if row['mode']=='intimate':row['vector']=-row['vector'];row['style']=row['style']*100
        after=P.evaluate(rows,controls,days,positive)[1]
        self.assertEqual([r for r in before if r['mode']=='opening_everyday'],
                         [r for r in after if r['mode']=='opening_everyday'])
        text=P.render_summary(report)
        self.assertIn('confounded with mode',text)
        self.assertNotIn('### Model-family familiarity',text)

    def test_cross_family_comparison_exists_only_inside_the_same_mode(self):
        for event in self.bundle['mode_observations']:
            if int(event['reply_id'].split('-')[1])%2:event['mode']='intimate'
        for control in self.bundle['controls']:
            if int(control['matched_reply_id'].split('-')[1])%2:control['mode']='intimate'
        report,_=P.run(self.bundle,self.cutoff)
        for mode in P.MODES[:2]:
            pair=report['primary_10s']['per_mode'][mode]['context_matched_family_comparisons']['pairs'][0]
            self.assertEqual(pair['matched_pairs'],6)
            self.assertEqual(pair['identifiability'],'matched_comparison_available')
        rows,_,_,_,_=P.prepare(self.bundle,self.cutoff)
        a,b=rows[0],dict(rows[1],mode='intimate')
        self.assertEqual(P.context_pairs([a],[b]),[])

    def test_reelroom_is_separate_in_engagement_reference_and_matching(self):
        for row in self.bundle['rows']:
            if row['turn_id'].endswith('-1'):row['surface']='reelroom'
        self.bundle['historical_attribution']['surface_callers']['reelroom']=['router:fixture']
        report,private=P.run(self.bundle,self.cutoff)
        self.assertEqual(report['primary_10s']['status']['scored'],32)
        self.assertEqual(report['coverage']['engagement_surfaces']['reelroom'],16)
        self.assertIn('| reelroom | 16 |',P.render_summary(report))
        for row in private:self.assertEqual(row['reference_turns'],3 if row['day']<'2020-01-05' else 4)
        rows,controls,days,positive,_=P.prepare(self.bundle,self.cutoff)
        a,b=rows[0],rows[1]
        self.assertNotEqual(a['surface'],b['surface'])
        self.assertEqual(P.context_pairs([a],[b]),[])
        before=P.evaluate(rows,controls,days,positive)[1]
        for row in rows:
            if row['surface']=='reelroom':row['vector']=-row['vector']
        after=P.evaluate(rows,controls,days,positive)[1]
        self.assertEqual([r for r in before if r['surface']=='avatar'],[r for r in after if r['surface']=='avatar'])

    def test_controls_require_an_explicit_matching_mode(self):
        self.bundle['controls'][0].pop('mode')
        self.bundle['controls'][1]['mode']='intimate'
        report,_=P.run(self.bundle,self.cutoff)
        self.assertEqual(report['coverage']['excluded']['control_mode_unknown_or_mismatched'],2)
        self.assertEqual(report['primary_10s']['metrics']['foreign_semantic_paired_win']['observations'],30)

    def pool(self):
        self.bundle['control_pool']=self.bundle.pop('controls')
        for item in self.bundle['control_pool']:item.pop('matched_reply_id')
        return self.bundle['control_pool']

    def test_pool_selection_is_deterministic_without_replacement_and_outcome_free(self):
        pool=self.pool()
        first=P.prepare(self.bundle,self.cutoff)
        keys=lambda result:[(c['id'],c['candidate_id']) for c in result[1]]
        self.assertEqual(len(first[1]),32)
        self.assertEqual(len({c['sha'] for c in first[1]}),32)
        pool.reverse()
        for item in pool:item['vector']=[1.,0.]
        second=P.prepare(self.bundle,self.cutoff)
        self.assertEqual(keys(first),keys(second))
        self.assertTrue(all(c['vector'][0]==1 for c in second[1]))
        # Supplied vectors are evaluated only after the context-only assignment.
        self.assertEqual(first[4]['control_selection']['unused_reviewed_candidates'],0)

    def test_pool_missing_review_or_changed_metadata_is_unknown_not_foreign(self):
        pool=self.pool()
        pool[0].pop('review');pool[1]['mode']='intimate';pool[2]['author']='subject'
        pool[3]['timestamp']=None;pool[4]['review']['evidence_sha256']='bad'
        pool[5]['timestamp']='2021-01-01T00:00:00Z';review_control(pool[5])
        _,controls,_,_,coverage=P.prepare(self.bundle,self.cutoff)
        self.assertEqual(len(controls),26)
        self.assertEqual(coverage['control_selection']['excluded']['unreviewed_or_invalid_provenance'],6)
        for item in pool:item.pop('review',None)
        report,_=P.run(self.bundle,self.cutoff)
        self.assertNotIn('foreign_semantic_paired_win',report['primary_10s']['metrics'])

    def test_pool_matches_mode_surface_language_context_and_length(self):
        pool=self.pool()
        for item in pool:item['context_vector']=[-1.,0.]
        pool[0]['context_vector']=[1.,0.];pool[0]['mode']='intimate';review_control(pool[0])
        pool[1]['context_vector']=[1.,0.];pool[1]['surface']='reelroom';review_control(pool[1])
        pool[2]['context_vector']=[1.,0.];pool[2]['language']='fr';review_control(pool[2])
        pool[3]['context_vector']=[1.,0.];pool[3]['content']='short'
        pool[3]['input_sha256']=P.digest('short');review_control(pool[3])
        self.assertEqual(P.prepare(self.bundle,self.cutoff)[1],[])
        pool[1]['kind']='other_surface';pool[1]['author']='subject';review_control(pool[1])
        controls=P.prepare(self.bundle,self.cutoff)[1]
        self.assertEqual(len(controls),1);self.assertEqual(controls[0]['kind'],'other_surface')
        pool[1]['surface']='avatar';review_control(pool[1])
        self.assertEqual(P.prepare(self.bundle,self.cutoff)[1],[])

    def test_pool_excludes_even_unattributed_input_text_and_refuses_conflicts(self):
        pool=self.pool()
        self.bundle['rows'].append(dict(role='assistant',turn_id='unattributed',
            timestamp='2020-01-20T00:00:00Z',content=pool[0]['content'],surface='avatar'))
        result=P.prepare(self.bundle,self.cutoff)
        self.assertEqual(result[4]['control_selection']['excluded']['reuses_input_reply'],1)
        pool.append(copy.deepcopy(pool[1]))
        self.assertEqual(P.prepare(self.bundle,self.cutoff)[4]['control_selection']['excluded']['duplicate_candidate'],1)
        pool[-1]['context_vector']=[-1.,0.]
        with self.assertRaisesRegex(ValueError,'conflicting control candidate'):P.prepare(self.bundle,self.cutoff)

    def test_reader_summary_labels_synthetic_and_preserves_zero_and_unknown(self):
        report,_=P.run(self.bundle,self.cutoff)
        page=P.render_reader_summary(report)
        self.assertIn('Synthetic demonstration only',page)
        self.assertIn('32 of 32',page)
        self.assertIn('95% interval',page)
        self.assertIn('not a probability',page)
        report['primary_10s']['per_mode']['opening_everyday']['metrics']['foreign_semantic_paired_win']['mean']=0
        self.assertIn('0.00 (95% interval',P.render_reader_summary(report))
        report['primary_10s']['per_mode']['opening_everyday']['metrics'].pop('foreign_semantic_paired_win')
        self.assertIn('not measured',P.render_reader_summary(report))

    def test_reader_summary_keeps_unscored_primary_separate_from_sensitivity(self):
        for row in self.bundle['historical_attribution']['compute_ledger']:row['at']-=20
        report,_=P.run(self.bundle,self.cutoff);report['input_kind']='retained_snapshot'
        page=P.render_reader_summary(report)
        self.assertIn('primary analysis has no scored replies',page)
        self.assertIn('| Primary | Opening / everyday | 0 / 0 | not measured | not measured |',page)
        self.assertIn('| 30-second sensitivity | Opening / everyday | 32 / 32 |',page)
        self.assertIn('cannot replace missing primary evidence',page)
        self.assertNotIn('Synthetic demonstration',page)

    def test_reader_summary_whitelists_output_and_rejects_invalid_numbers(self):
        report,_=P.run(self.bundle,self.cutoff)
        report['meaning']='private-sentinel';report['encoder_pin']['private_id']='private-sentinel'
        report['coverage']['control_selection']['private_source']='private-sentinel'
        for bad in ('private-sentinel','reply-0-0','synthetic shared topic','synthetic-frozen'):
            self.assertNotIn(bad,P.render_reader_summary(report))
        metric=report['primary_10s']['per_mode']['opening_everyday']['metrics']['semantic_percentile']
        metric['mean']=float('nan')
        with self.assertRaisesRegex(ValueError,'reader proportion'):P.render_reader_summary(report)
        metric['mean']=.5;metric['observations']=True
        with self.assertRaisesRegex(ValueError,'reader count'):P.render_reader_summary(report)

    def test_control_only_surfaces_accept_explicit_store_authorship(self):
        pool=self.pool();pool[:]=pool[:3]
        for item,surface in zip(pool,('slack','moltbook','journal')):
            item.update(kind='other_surface',author='subject',surface=surface)
            review_control(item);item['review']['reviewer']='store_authorship'
        report,private=P.run(self.bundle,self.cutoff)
        selection=report['coverage']['control_selection']
        self.assertEqual(report['coverage']['matched_controls'],3)
        self.assertFalse(selection['source_authorship_independently_verified'])
        self.assertEqual({(c['surface'],c['reviewer_class'],c['kind'],c['pairs']) for c in selection['selected_source_counts']},
            {(s,'store_authorship','other_surface',1) for s in ('slack','moltbook','journal')})
        matches=[c for r in private for c in r['control_matches']]
        self.assertEqual({c['source_surface'] for c in matches},{'slack','moltbook','journal'})
        self.assertTrue(all(c['reviewer_class']=='store_authorship' for c in matches))
        self.assertIn('not a human review',P.render_summary(report))
        # These source names do not expand engagement/reference surface admission.
        self.assertEqual(P.surface_label('journal'),'unknown')
        self.assertNotIn('journal',report['coverage']['engagement_surfaces'])

    def test_store_authorship_does_not_supply_missing_mode_author_or_provenance(self):
        pool=self.pool();pool[:]=pool[:3]
        for item in pool:
            item.update(kind='other_surface',author='subject',surface='journal')
            review_control(item);item['review']['reviewer']='store_authorship'
        pool[0]['mode']='unknown';review_control(pool[0]);pool[0]['review']['reviewer']='store_authorship'
        pool[1]['author']='non_subject';review_control(pool[1]);pool[1]['review']['reviewer']='store_authorship'
        pool[2]['review'].pop('evidence_sha256')
        result=P.prepare(self.bundle,self.cutoff)
        self.assertEqual(result[1],[])
        self.assertEqual(result[4]['control_selection']['excluded']['unreviewed_or_invalid_provenance'],3)
        self.assertNotIn('store_authorship',P.ANNOTATORS)

    def test_control_sources_keep_unknown_classes_and_wrong_surface_foreign_unmatched(self):
        pool=self.pool();pool[:]=pool[:3]
        pool[0]['surface']='unknown';review_control(pool[0])
        pool[1]['review']['reviewer']='unrecognized_source'
        pool[2]['surface']='journal';review_control(pool[2]);pool[2]['review']['reviewer']='store_authorship'
        result=P.prepare(self.bundle,self.cutoff)
        self.assertEqual(result[1],[])
        self.assertEqual(result[4]['control_selection']['excluded']['unreviewed_or_invalid_provenance'],2)
        self.assertEqual(result[4]['control_selection']['unused_reviewed_candidates'],1)

    def test_pool_prefers_context_and_preserves_primary_matches_with_sensitivity_rows(self):
        pool=self.pool();pool[:]=pool[:1]
        # A closer context wins independently of the response vector.
        alternative=copy.deepcopy(pool[0]);alternative['candidate_id']='z-closer'
        alternative['content']+=' Alternative.';alternative['input_sha256']=P.digest(alternative['content'])
        review_control(alternative);pool[0]['context_vector']=[.8,.6];pool.append(alternative)
        self.bundle['historical_attribution']['compute_ledger'][0]['at']-=20
        _,controls,_,_,_=P.prepare(self.bundle,self.cutoff)
        self.assertEqual(controls[0]['candidate_id'],'z-closer')
        self.assertNotIn('reply-0-0',[c['id'] for c in controls])
        # Every selection remains available privately, even with no scorable folds.
        self.bundle['rows']=[r for r in self.bundle['rows'] if r['role']=='assistant']
        matches=[];report,_=P.run(self.bundle,self.cutoff,matches)
        self.assertEqual(len(matches),2)
        self.assertEqual(report['primary_10s']['status'],{'insufficient_reference_days':31})

    def test_pool_rejects_cache_mismatch_and_mixed_input_paths(self):
        pool=self.pool();pool[0]['context_sha256']='bad'
        with self.assertRaisesRegex(ValueError,'encoder/input'):P.prepare(self.bundle,self.cutoff)
        pool[0]['context_sha256']=P.digest(pool[0]['context'])
        self.bundle['controls']=[dict(pool[0],matched_reply_id='reply-0-0')]
        with self.assertRaisesRegex(ValueError,'not both'):P.prepare(self.bundle,self.cutoff)

    def test_paired_controls_also_require_review_and_cannot_reuse_text(self):
        self.bundle['controls'][0].pop('review')
        self.bundle['controls'][1]=dict(self.bundle['controls'][2],matched_reply_id='reply-0-1')
        _,controls,_,_,coverage=P.prepare(self.bundle,self.cutoff)
        self.assertEqual(len(controls),30)
        self.assertEqual(coverage['excluded']['control_provenance_unreviewed'],1)
        self.assertEqual(coverage['excluded']['control_reused_text_or_pair'],1)

    def test_pool_cli_exports_counts_only_and_keeps_match_bindings_private(self):
        pool=self.pool();source=self.root/'input.json';source.write_text(json.dumps(self.bundle));out=self.root/'pool-result'
        result=subprocess.run([sys.executable,str(ROOT/'experiments/character-reference/prototype.py'),
            '--scratch',str(self.root),'--input',str(source),'--output',str(out),'--cutoff',self.cutoff],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        public=(out/'aggregate.json').read_text()+(out/'summary.md').read_text()
        self.assertNotIn(pool[0]['candidate_id'],public)
        self.assertNotIn(pool[0]['review']['binding_sha256'],public)
        self.assertNotIn(pool[0]['content'],public)
        private=json.loads((out/'private-evaluation.json').read_text())
        matches=[c for r in private for c in r['control_matches']]
        self.assertEqual(len(matches),32)
        self.assertEqual(len(json.loads((out/'private-controls.json').read_text())),32)
        report=json.loads((out/'aggregate.json').read_text())
        cells=report['coverage']['control_selection']['by_mode_surface']
        cell=next(c for c in cells if c['mode']=='opening_everyday' and c['surface']=='avatar' and c['kind']=='foreign')
        self.assertEqual((cell['admitted_replies'],cell['matched_replies'],cell['unmatched_replies']),(32,32,0))

    def test_encoder_pin_keeps_unknown_declared_observed_and_verified_distinct(self):
        encoder=self.bundle['encoder']
        self.assertEqual(P.encoder_pin(encoder)['artifact_status'],'unknown')
        artifact=self.root/'synthetic-artifact.bin';artifact.write_bytes(b'synthetic encoder fixture')
        observation=P.observe_encoder_artifact(artifact)
        self.assertEqual(observation,{'sha256':P.digest('synthetic encoder fixture'),'bytes':25})
        self.assertEqual(P.encoder_pin(encoder,observation)['artifact_status'],'artifact_hash_observed')
        declared=dict(encoder,artifact_sha256=observation['sha256'])
        self.assertEqual(P.encoder_pin(declared)['artifact_status'],'artifact_hash_declared')
        verified=P.encoder_pin(declared,observation)
        self.assertEqual(verified['artifact_status'],'artifact_hash_verified')
        self.assertEqual(verified['declared_contract'],declared)
        self.assertFalse(verified['revision_verified']);self.assertFalse(verified['cache_derivation_verified'])
        with self.assertRaises(ValueError):P.encoder_pin(dict(encoder,artifact_sha256='0'*64),observation)
        self.bundle['encoder']['artifact_sha256']='private invalid hash'
        with self.assertRaises(ValueError):P.run(self.bundle,self.cutoff)

    def test_encoder_artifact_is_bounded_regular_and_refuses_observed_mutation(self):
        artifact=self.root/'artifact.bin';artifact.write_bytes(b'abcd')
        link=self.root/'artifact-link';link.symlink_to(artifact)
        with self.assertRaises(OSError):P.observe_encoder_artifact(link)
        with patch.object(P,'ENCODER_ARTIFACT_LIMIT',3):
            with self.assertRaises(ValueError):P.observe_encoder_artifact(artifact)
        before=os.stat(artifact)
        changed=Mock(st_dev=before.st_dev,st_ino=before.st_ino,st_size=before.st_size,
                     st_mtime_ns=before.st_mtime_ns+1,st_ctime_ns=before.st_ctime_ns)
        with patch.object(P.os,'fstat',side_effect=[before,changed]):
            with self.assertRaises(ValueError):P.observe_encoder_artifact(artifact)
        artifact.write_bytes(b'')
        with self.assertRaises(ValueError):P.observe_encoder_artifact(artifact)

    def test_cli_retains_exact_encoder_contract_privately_and_verifies_scratch_hash(self):
        artifact=self.root/'artifact.bin';artifact.write_bytes(b'synthetic bytes')
        self.bundle['encoder']['artifact_sha256']=P.digest('synthetic bytes')
        self.bundle['encoder']['revision']='private-revision-identifier'
        source=self.root/'input.json';source.write_text(json.dumps(self.bundle));out=self.root/'pinned-run'
        cmd=[sys.executable,str(ROOT/'experiments/character-reference/prototype.py'),
             '--scratch',str(self.root),'--input',str(source),'--output',str(out),'--cutoff',self.cutoff,
             '--encoder-artifact',str(artifact)]
        result=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        manifest=json.loads((out/'private-run.json').read_text())
        self.assertEqual(manifest['encoder_pin']['declared_contract'],self.bundle['encoder'])
        self.assertEqual(manifest['encoder_pin']['artifact_status'],'artifact_hash_verified')
        for name in ('aggregate.json','summary.md'):
            public=(out/name).read_text()
            self.assertNotIn('private-revision-identifier',public)
            self.assertNotIn(self.bundle['encoder']['artifact_sha256'],public)
            self.assertNotIn(str(artifact),public)
        artifact.write_bytes(b'different bytes')
        cmd[cmd.index('--output')+1]=str(self.root/'mismatch')
        result=subprocess.run(cmd,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.root/'mismatch').exists())
        cmd[cmd.index('--encoder-artifact')+1]=str(ROOT/'AGENTS.md')
        result=subprocess.run(cmd,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.root/'mismatch').exists())

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
        self.assertEqual((out/'summary.md').read_text(),P.render_summary(report))
        self.assertEqual((out/'reader-summary.md').read_text(),P.render_reader_summary(report))
        pin=json.loads((out/'private-run.json').read_text())['encoder_pin']
        self.assertEqual(pin['artifact_status'],'unknown')
        self.assertEqual(pin['declared_contract'],self.bundle['encoder'])
        again=subprocess.run(cmd,capture_output=True,text=True);self.assertNotEqual(again.returncode,0)


if __name__=='__main__':unittest.main()

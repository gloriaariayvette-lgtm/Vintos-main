#!/usr/bin/env python3
"""Synthetic witnessed outcomes only; no store reads, network or encoder calls."""
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('facets',ROOT/'experiments/nonllm-judges/witnessed_facets.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
sha=lambda x:hashlib.sha256(x.encode()).hexdigest()
BASE=1609459200.
TEXT='A tiny comet borrowed my teacup.'

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='positive-facet-test-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.sender=Mock(side_effect=AssertionError('external action forbidden'))
        for guard in (patch.dict(os.environ,HOME=str(self.root),SPARK_WORKSPACE=str(self.root)),
                      patch.object(socket.socket,'connect',self.sender),patch.object(subprocess,'run',self.sender)):
            guard.start();self.addCleanup(guard.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertIsInstance(subprocess.run,Mock);self.assertNotIn('.vintos',self.root.parts)
        self.events=[];self.nodes=[];self.features=[];self.items=[];self.anchors=[];self.attempts=[]
        self.encoder=dict(id='synthetic',artifact_sha256=sha('synthetic artifact'),dimension=2,frozen=True,frozen_at=BASE-100)
        for day in range(3):self.anchor(self.add(day))
        self.target=self.add(4);self.attempts=[self.target]

    def add(self,day,kind='message',mode='everyday',surface='avatar',text=TEXT,angle=0.):
        key='synthetic-'+str(len(self.events));at=BASE+day*86400
        self.events.append(dict(node_id=key,origin_id=key,at=at,content_sha256=sha(text),mode=mode,surface=surface,source='synthetic-source'))
        self.nodes.append(dict(id=key,at=at,kind='original_act',parents=[],complete=True))
        self.items.append(dict(node_id=key,kind=kind))
        self.features.append(dict(node_id=key,content_sha256=sha(text),text=text,vector=[math.cos(angle),math.sin(angle)],
            encoder_id='synthetic',artifact_sha256=self.encoder['artifact_sha256'],mode_source='router_decision',mode_evidence_sha256=sha('synthetic mode')))
        return key

    def anchor(self,key,source='adjacent_exchange',value='haha!',observed=None):
        r=next(e for e in self.events if e['node_id']==key);kind=next(i['kind'] for i in self.items if i['node_id']==key)
        a=dict(evidence_id='outcome-'+str(len(self.anchors)),node_id=key,content_sha256=r['content_sha256'],actor='owner',witnessed=True,
            observed_at=r['at']+10 if observed is None else observed,source=source,value=value,source_record_sha256=sha('record-'+str(len(self.anchors))))
        if source=='adjacent_exchange':
            a['link']=dict(kind='adjacent_exchange',exchange_id='exchange-'+key,target_id=key,target_sha256=r['content_sha256'],
                reaction_id='reaction-'+key+'-'+a['evidence_id'],reaction_sha256=sha(value),target_index=0,reaction_index=1)
        else:a['link']=dict(kind='exact_item',item_id=key,item_sha256=r['content_sha256'],item_kind=kind)
        self.anchors.append(a);return a

    def run_analysis(self,**kwargs):
        return P.analyze(self.events,self.nodes,self.features,self.encoder,self.items,self.attempts,self.anchors,BASE+100*86400,**kwargs)

    def test_three_positives_show_sparse_coverage_without_fake_calibration(self):
        report,rows=self.run_analysis()
        self.assertEqual(report['outcomes']['positive_original_acts'],3)
        self.assertEqual(report['outcomes']['positive_act_days'],3)
        self.assertEqual(report['empirically_ranked_attempts'],0)
        self.assertEqual(rows[0]['status'],'similarity_only');self.assertEqual(rows[0]['band_location'],'abstain')
        self.assertEqual(rows[0]['reference_count'],3);self.assertIsNone(rows[0]['empirical_score'])
        self.assertEqual(rows[0]['similarity']['joint_familiarity'],1.)

    def test_unknown_outcomes_never_become_negatives(self):
        self.anchors=[]
        for v in ('ha','thanks','noted'):
            key=self.add(6);self.anchor(key,value=v);self.attempts.append(key)
        report,rows=self.run_analysis()
        self.assertEqual(report['negative_labels'],0);self.assertEqual(report['outcomes']['positive_original_acts'],0)
        self.assertTrue(all(r['outcome']=='unknown' and r['similarity'] is None for r in rows))

    def test_laughter_requires_exact_adjacent_owner_exchange(self):
        for mutate,reason in ((lambda a:a['link'].update(reaction_index=2),'adjacency_unbound'),
                              (lambda a:a.update(actor='subject'),'not_owner_witness'),
                              (lambda a:a.update(witnessed=False),'not_owner_witness'),
                              (lambda a:a['link'].update(target_sha256='0'*64),'adjacency_unbound'),
                              (lambda a:a['link'].update(reaction_sha256='0'*64),'adjacency_unbound')):
            saved=copy.deepcopy(self.anchors);mutate(self.anchors[0])
            report,_=self.run_analysis();self.assertEqual(report['outcomes']['positive_original_acts'],2)
            self.assertEqual(report['outcomes']['excluded_or_unknown'][reason],1);self.anchors=saved

    def test_humor_practice_only_explicit_four_or_five_owner_stars(self):
        self.anchors=[]
        for day,value in enumerate((4,5,3,1,True,6,'5')):
            key=self.add(day,kind='joke');self.anchor(key,'humor_practice',value)
        report,_=self.run_analysis();self.assertEqual(report['outcomes']['positive_original_acts'],2)
        self.assertEqual(report['negative_labels'],0)

    def test_practice_prefix_or_missing_id_cannot_bind(self):
        key=self.add(6,kind='joke');a=self.anchor(key,'humor_practice',5)
        a['link']['item_id']=key[:-1]
        report,_=self.run_analysis();self.assertEqual(report['outcomes']['excluded_or_unknown']['item_unbound'],1)

    def test_same_day_self_and_future_feedback_never_leak(self):
        self.attempts=['synthetic-2'];self.anchor('synthetic-0',observed=BASE+8*86400)
        self.anchors[0]['observed_at']=BASE+2*86400+1
        report,rows=self.run_analysis();self.assertEqual(rows[0]['reference_count'],1)
        self.assertIsNone(rows[0]['similarity'])
        self.assertTrue(all(a['node_id']!='synthetic-2' for a in rows[0]['references']))

    def test_targets_later_positive_outcome_does_not_change_its_score(self):
        before=self.run_analysis()[1][0];self.anchor(self.target,observed=BASE+7*86400)
        after=self.run_analysis()[1][0]
        self.assertEqual(before['similarity'],after['similarity']);self.assertEqual(before['references'],after['references'])
        self.assertEqual(before['outcome'],'unknown');self.assertEqual(after['outcome'],'witnessed_positive')

    def test_modes_surfaces_and_item_kinds_are_not_pooled(self):
        self.events[0]['mode']='intimate';self.events[1]['surface']='voice';self.items[2]['kind']='joke'
        report,rows=self.run_analysis();self.assertEqual(rows[0]['reference_count'],0)
        self.assertEqual(report['outcomes']['positive_original_acts'],3)
        self.assertEqual(report['reference_coverage'][0]['available_reference_acts'],0)

    def test_multiple_anchors_and_scans_do_not_inflate_reference_acts(self):
        self.anchors.append(copy.deepcopy(self.anchors[0]));self.anchor('synthetic-0',value='hahaha')
        self.events.append(copy.deepcopy(self.events[0]))
        report,rows=self.run_analysis()
        self.assertEqual(report['outcomes']['positive_original_acts'],3);self.assertEqual(rows[0]['reference_count'],3)
        self.assertEqual(report['outcomes']['excluded_or_unknown']['duplicate_observation'],1)

    def test_conflicting_evidence_identity_refuses(self):
        a=copy.deepcopy(self.anchors[0]);a['value']='changed';self.anchors.append(a)
        with self.assertRaisesRegex(ValueError,'conflicting'):self.run_analysis()

    def test_one_reaction_cannot_anchor_two_different_attempts(self):
        self.anchors[1]['link']['reaction_id']=self.anchors[0]['link']['reaction_id']
        with self.assertRaisesRegex(ValueError,'conflicting reaction adjacency'):self.run_analysis()

    def test_journal_taste_supported_without_crossing_item_kind(self):
        self.anchors=[]
        for day in range(3):
            key=self.add(day,kind='journal',surface='journal');self.anchor(key,'landings','landed')
        target=self.add(5,kind='journal',surface='journal');self.attempts=[target]
        report,rows=self.run_analysis(facet='taste')
        self.assertEqual(rows[0]['reference_count'],3);self.assertEqual(rows[0]['scope'],['everyday','journal','journal'])
        self.assertEqual(report['negative_labels'],0)

    def test_indirect_influence_excludes_anchor_and_attempt(self):
        self.nodes.append(dict(id='synthetic-effect',kind='judge_effect',at=BASE-5,parents=[],complete=True))
        self.nodes[0]['parents']=['synthetic-effect'];self.nodes[3]['parents']=['synthetic-effect']
        report,rows=self.run_analysis();self.assertEqual(report['outcomes']['positive_original_acts'],2)
        self.assertEqual(report['attempts']['status']['attempt_not_admitted'],1);self.assertFalse(rows)

    def test_taste_landings_landed_only_not_generated_profile_or_call_save(self):
        self.anchors=[]
        for day,value in enumerate(('landed','landed','landed','partly','missed')):
            key=self.add(day);self.anchor(key,'landings',value)
        self.anchor(self.target,'call_save',True)
        report,rows=self.run_analysis(facet='taste')
        self.assertEqual(report['outcomes']['positive_original_acts'],3)
        self.assertEqual(report['outcomes']['positive_sources'],{'landings':3})
        self.assertEqual(report['outcomes']['excluded_or_unknown']['unsupported_source'],1)
        self.assertEqual(report['negative_labels'],0);self.assertEqual(rows[0]['status'],'similarity_only')

    def test_taste_does_not_infer_artwork_preference_from_caption_vector(self):
        self.anchors=[]
        for kind in ('image','song','video'):
            key=self.add(1,kind=kind);self.anchor(key,'landings','landed');self.attempts.append(key)
        report,_=self.run_analysis(facet='taste')
        self.assertEqual(report['outcomes']['positive_original_acts'],0)
        self.assertEqual(report['attempts']['status']['unsupported_attempt_kind'],3)

    def test_four_positive_days_allow_empirical_rank_not_success_verdict(self):
        self.anchor(self.add(3));report,rows=self.run_analysis()
        self.assertEqual(report['empirically_ranked_attempts'],1);self.assertEqual(rows[0]['empirical_score'],.5)
        self.assertEqual(rows[0]['band_location'],'abstain');self.assertIsNone(report['verdict'])
        self.features[-2]['vector']=[-1.,0.]
        changed=self.run_analysis()[1][0];self.assertLess(changed['similarity']['joint_familiarity'],1.)
        self.assertEqual(changed['outcome'],'unknown')

    def test_coverage_with_zero_and_one_positive_day(self):
        self.anchors=self.anchors[:1]
        report,rows=self.run_analysis();self.assertEqual(rows[0]['status'],'insufficient_positive_days')
        self.assertEqual(report['outcomes']['positive_act_days'],1)
        self.anchors=[];report,_=self.run_analysis();self.assertIsNone(report['mean_positive_familiarity'])

    def test_unavailable_mode_cache_hash_or_encoder_never_scores(self):
        self.events[3]['mode']='unknown'
        self.assertEqual(self.run_analysis()[0]['attempts']['status']['attempt_not_admitted'],1)
        self.events[3]['mode']='everyday';self.features[3]['artifact_sha256']='0'*64
        self.assertEqual(self.run_analysis()[0]['attempts']['status']['attempt_not_admitted'],1)

    def test_pre_event_post_cutoff_or_naive_outcome_time_refused(self):
        for at in (BASE-1,BASE+101*86400):
            self.anchors[0]['observed_at']=at
            self.assertEqual(self.run_analysis()[0]['outcomes']['excluded_or_unknown']['outside_evidence_time'],1)
        self.anchors[0]['observed_at']='2021-01-01T00:00:10'
        with self.assertRaises(ValueError):self.run_analysis()

    def test_aggregate_privacy_input_immutability_and_permutation(self):
        inputs=copy.deepcopy((self.events,self.nodes,self.features,self.items,self.attempts,self.anchors));before=self.run_analysis()
        self.assertEqual(inputs,(self.events,self.nodes,self.features,self.items,self.attempts,self.anchors))
        text=json.dumps(before[0],allow_nan=False)
        for secret in (TEXT,'synthetic-','outcome-','reaction-','exchange-','2021-01',sha(TEXT),'haha!'):
            self.assertNotIn(secret,text)
        for records in (self.events,self.nodes,self.features,self.items,self.attempts,self.anchors):records.reverse()
        self.assertEqual(self.run_analysis(),before)

if __name__=='__main__':unittest.main()

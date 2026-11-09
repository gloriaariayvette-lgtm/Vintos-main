#!/usr/bin/env python3
"""Synthetic offline reference/drift contracts; all external actions forbidden."""
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
spec=importlib.util.spec_from_file_location('voice_drift',ROOT/'experiments/nonllm-judges/voice_drift.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
BASE=1609459200.
TEXT='I notice the quiet rhythm.'
SHIFT='WOW! WHAT A WONDERFUL DAY!\n'+('WE DANCE, WE SING! '*20)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='voice-drift-test-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.sender=Mock(side_effect=AssertionError('external action forbidden'))
        for guard in (patch.dict(os.environ,HOME=str(self.root),SPARK_WORKSPACE=str(self.root)),
                      patch.object(socket.socket,'connect',self.sender),patch.object(subprocess,'run',self.sender)):
            guard.start();self.addCleanup(guard.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertIsInstance(subprocess.run,Mock);self.assertNotIn('.vintos',self.root.parts)
        self.events=[];self.nodes=[];self.features=[];self.refs=[]
        self.encoder=dict(id='synthetic',artifact_sha256=sha('synthetic artifact'),dimension=2,frozen=True,frozen_at=BASE-100)
        for d in range(6):self.refs.append(self.add(d))

    def add(self,day,text=TEXT,angle=0.,mode='everyday',surface='avatar',offset=0):
        key='fixture-'+str(len(self.events));at=BASE+day*86400+offset
        self.events.append(dict(node_id=key,origin_id=key,at=at,content_sha256=sha(text),mode=mode,surface=surface,source='synthetic'))
        self.nodes.append(dict(id=key,at=at,kind='original_act',parents=[],complete=True))
        self.features.append(dict(node_id=key,content_sha256=sha(text),text=text,vector=[math.cos(angle),math.sin(angle)],
            encoder_id='synthetic',artifact_sha256=self.encoder['artifact_sha256'],mode_source='router_decision',mode_evidence_sha256=sha('synthetic mode')))
        return key

    def run_analysis(self,**kwargs):
        return P.analyze(self.events,self.nodes,self.features,self.encoder,self.refs,BASE+100*86400,**kwargs)

    def adoption(self,ids,observed_day=10):
        rows,_=P.prepare(self.events,self.nodes,self.features,self.encoder,BASE+100*86400,'UTC')
        return dict(reference_version=P.version([r for r in rows if r['id'] in self.refs]),
                    members=[dict(node_id=e['node_id'],content_sha256=e['content_sha256']) for e in self.events if e['node_id'] in ids],
                    reviewer='owner',decision='adopt',observed_at=BASE+observed_day*86400+1,evidence_sha256=sha('synthetic owner adoption'))

    def test_baseline_ties_abstain_and_shifted_style_scores_lower(self):
        ordinary=self.add(6);shifted=self.add(7,SHIFT)
        report,details=self.run_analysis();a={r['turn_id']:r for r in details['voice']}
        self.assertEqual(a[ordinary]['score'],.5);self.assertEqual(a[ordinary]['band_location'],'abstain')
        self.assertLess(a[shifted]['score'],a[ordinary]['score']);self.assertEqual(a[shifted]['band_location'],'below_band')
        self.assertEqual(report['verdict'],None);self.assertEqual(report['effects'],'none')

    def test_cached_semantic_shift_changes_score_without_new_encoder(self):
        key=self.add(6,angle=2.5);_,details=self.run_analysis()
        r=next(r for r in details['voice'] if r['turn_id']==key)
        self.assertGreater(r['raw']['semantic_distance'],.8);self.assertEqual(r['raw']['style_distance'],0.)
        self.assertEqual(r['score'],0.)

    def test_target_and_future_days_cannot_calibrate_target(self):
        target=self.add(6,SHIFT);self.add(7,SHIFT);self.refs.append(self.events[-1]['node_id'])
        _,details=self.run_analysis();record=next(r for r in details['voice'] if r['turn_id']==target)
        self.assertTrue(all(d<record['day'] for d in record['reference_days']))
        self.assertEqual(record['calibration_days'],6)
        self.features[-1]['vector']=[-1.,0.]
        self.assertEqual(record,next(r for r in self.run_analysis()[1]['voice'] if r['turn_id']==target))

    def test_day_equal_calibration_and_prolific_day_do_not_dominate(self):
        target=self.add(6,SHIFT);before=next(r for r in self.run_analysis()[1]['voice'] if r['turn_id']==target)
        for i in range(20):self.refs.append(self.add(0,offset=i+1))
        after=next(r for r in self.run_analysis()[1]['voice'] if r['turn_id']==target)
        self.assertEqual(before['score'],after['score']);self.assertEqual(before['raw'],after['raw'])

    def test_leave_one_day_out_matches_reused_character_functions(self):
        rows,_=P.prepare(self.events,self.nodes,self.features,self.encoder,BASE+100*86400,'UTC')
        rows[0]['style']=P.C.style(SHIFT)
        state,held=P.calibrate(rows,4)
        other=P.day_balanced([r for r in rows if r['day']!=rows[0]['day']])
        expected=P.distance(rows[0],P.C.reference_statistics(other))
        self.assertEqual(held[0][1][0],expected)
        self.assertGreater(expected['style_distance'],0.)

    def test_mode_and_surface_are_separate_no_cross_scope_fallback(self):
        self.add(6,mode='intimate');self.add(6,surface='reelroom')
        report,details=self.run_analysis()
        self.assertEqual(report['status']['no_reference_scope'],2)
        self.assertTrue(all(r['scope']==['everyday','avatar'] for r in details['voice']))

    def test_single_outlier_never_flags_sustained_shift(self):
        for d in range(6,16):self.add(d,SHIFT if d==8 else TEXT,2.5 if d==8 else 0.)
        report,details=self.run_analysis()
        self.assertEqual(report['drift']['sustained_scope_days'],0)
        self.assertEqual(max(r['consecutive_shift_days'] for r in details['drift']),1)

    def test_gradual_drift_eventually_flags_and_does_not_update_itself(self):
        for d in range(6,22):self.add(d,angle=(d-5)*.13)
        report,details=self.run_analysis()
        self.assertGreater(report['drift']['sustained_scope_days'],0)
        self.assertEqual(report['drift']['reference_revisions'],0)
        self.assertFalse(details['drift'][0]['sustained_shift'])
        self.assertTrue(details['drift'][-1]['sustained_shift'])

    def test_calendar_gap_resets_sustained_run(self):
        for d in (6,7,9,10,11):self.add(d,SHIFT,2.5)
        self.assertEqual(self.run_analysis()[0]['drift']['sustained_scope_days'],0)

    def test_adopted_persistent_growth_updates_only_future_reference(self):
        ids=[self.add(d,SHIFT,2.5) for d in range(6,10)]
        later=self.add(11,SHIFT,2.5);a=self.adoption(ids)
        original=copy.deepcopy((self.events,self.nodes,self.features,a))
        report,details=self.run_analysis(adoptions=[a])
        self.assertEqual(report['drift']['reference_revisions'],1)
        self.assertEqual(details['adoptions'][0]['status'],'applied')
        r=next(r for r in details['voice'] if r['turn_id']==later)
        self.assertAlmostEqual(r['score'],.5)
        self.assertEqual(r['reference_days'],['2021-01-07','2021-01-08','2021-01-09','2021-01-10'])
        self.assertFalse(details['drift'][-1]['sustained_shift'])
        self.assertEqual((self.events,self.nodes,self.features,a),original)
        self.assertNotEqual(details['revisions'][0]['prior_version'],details['revisions'][0]['reference_version'])

    def test_adoption_needs_persistence_and_exact_current_version(self):
        ids=[self.add(d) for d in range(6,10)];self.add(11)
        a=self.adoption(ids)
        self.assertEqual(self.run_analysis(adoptions=[a])[0]['drift']['adoption_status'],{'not_sustained_shift_evidence':1})
        a['reference_version']='0'*64
        self.assertEqual(self.run_analysis(adoptions=[a])[0]['drift']['adoption_status'],{'stale_reference_version':1})

    def test_family_derived_mode_cannot_authorize_reference_adoption(self):
        ids=[self.add(d,SHIFT,2.5) for d in range(6,10)];self.add(11,SHIFT,2.5)
        for f in self.features:
            if f['node_id'] in ids:f['mode_source']='gloria_family_rule'
        a=self.adoption(ids)
        self.assertEqual(self.run_analysis(adoptions=[a])[0]['drift']['adoption_status'],{'independent_mode_required_for_adoption':1})

    def test_adoption_no_retroactive_update_and_duplicate_receipt_once(self):
        ids=[self.add(d,SHIFT,2.5) for d in range(6,10)];self.add(10,SHIFT,2.5);self.add(12,SHIFT,2.5)
        a=self.adoption(ids,11)
        _,details=self.run_analysis(adoptions=[a,copy.deepcopy(a)])
        self.assertEqual(len(details['revisions']),1);self.assertEqual(details['revisions'][0]['effective_day'],'2021-01-13')
        self.assertTrue(details['drift'][-2]['sustained_shift'])

    def test_bad_adoption_bindings_and_automatic_reviewer_refused(self):
        ids=[self.add(d,SHIFT,2.5) for d in range(6,10)]
        for field,value in (('reviewer','automatic'),('decision','persisted'),('observed_at',BASE)):
            a=self.adoption(ids);a[field]=value
            with self.assertRaises(ValueError):self.run_analysis(adoptions=[a])
        a=self.adoption(ids);a['members'][0]['content_sha256']='0'*64
        with self.assertRaises(ValueError):self.run_analysis(adoptions=[a])

    def test_indirect_judge_influence_cannot_enter_reference_or_scoring(self):
        target=self.add(6,SHIFT);self.nodes.append(dict(id='effect',kind='emotion_nudge',at=BASE-1,parents=[],complete=True))
        self.nodes[-2]['parents']=['effect']
        report,details=self.run_analysis();self.assertEqual(report['coverage']['excluded']['influenced_or_derived'],1)
        self.assertNotIn(target,[r['turn_id'] for r in details['voice']])
        self.nodes[0]['parents']=['effect']
        with self.assertRaisesRegex(ValueError,'reference ID not admitted'):self.run_analysis()

    def test_feature_hash_encoder_and_unknown_provenance_excluded(self):
        self.add(6);self.features[-1]['text']='changed'
        self.assertEqual(self.run_analysis()[0]['coverage']['feature_exclusions'],{'feature_binding_mismatch':1})
        self.features[-1]['text']=TEXT;self.features[-1]['mode_source']='unknown'
        self.assertEqual(self.run_analysis()[0]['coverage']['feature_exclusions'],{'mode_provenance_unknown':1})
        self.features[-1]['mode_source']='router_decision';self.features[-1]['artifact_sha256']='0'*64
        self.assertEqual(self.run_analysis()[0]['coverage']['feature_exclusions'],{'feature_binding_mismatch':1})

    def test_unknown_mode_and_insufficient_days_abstain_without_score(self):
        self.events[-1]['mode']='unknown';self.refs.pop();self.refs=self.refs[:3];self.add(6)
        report,details=self.run_analysis();self.assertFalse(details['voice']);self.assertIsNone(report['voice']['mean_score'])
        self.assertGreater(report['status']['insufficient_or_degenerate_past_reference'],0)

    def test_invalid_vectors_and_controls_fail_closed(self):
        for vector in ([float('nan'),0.],[True,0.],[2.,0.]):
            self.features[-1]['vector']=vector
            with self.assertRaises(ValueError):self.run_analysis()
        self.features[-1]['vector']=[1.,0.]
        for opts in ({'min_days':True},{'sustain_days':1},{'abstain_band':(.8,.2)},{'drift_margin':float('inf')}):
            with self.assertRaises(ValueError):self.run_analysis(**opts)

    def test_reference_version_binds_encoder_and_mode_provenance(self):
        rows,_=P.prepare(self.events,self.nodes,self.features,self.encoder,BASE+100*86400,'UTC')
        before=P.version(rows)
        for field,value in (('artifact_sha256','0'*64),('mode_evidence_sha256','1'*64),('source','another-synthetic-source')):
            altered=copy.deepcopy(rows);altered[0][field]=value
            self.assertNotEqual(before,P.version(altered))

    def test_empty_and_opposed_reference_abstain(self):
        report,details=P.analyze([],[],[],self.encoder,[],BASE+100*86400)
        self.assertEqual(report['voice']['scored_replies'],0);self.assertFalse(details['voice'])
        for day in range(6):
            self.refs.append(self.add(day,angle=math.pi,offset=1))
        self.add(6)
        self.assertFalse(self.run_analysis()[1]['voice'])

    def test_initial_family_mode_reference_cannot_authorize_update(self):
        ids=[self.add(d,SHIFT,2.5) for d in range(6,10)];self.add(11,SHIFT,2.5)
        self.features[0]['mode_source']='gloria_family_rule'
        a=self.adoption(ids)
        self.assertEqual(self.run_analysis(adoptions=[a])[0]['drift']['adoption_status'],{'independent_mode_required_for_adoption':1})

    def test_public_report_has_no_text_ids_hashes_dates_vectors_or_source(self):
        self.add(6,SHIFT,2.5);report,_=self.run_analysis();encoded=json.dumps(report,allow_nan=False)
        for secret in ('fixture-','2021-01',TEXT,SHIFT,sha(TEXT),self.encoder['artifact_sha256'],'synthetic'):
            self.assertNotIn(secret,encoded)
        self.assertEqual(report['encoder_calls'],0)
        self.assertFalse(report['verification']['source_and_adoption_claims'])

    def test_permutation_is_deterministic_and_inputs_unchanged(self):
        for d in range(6,12):self.add(d,SHIFT,2.)
        original=copy.deepcopy((self.events,self.nodes,self.features));before=self.run_analysis()
        self.assertEqual((self.events,self.nodes,self.features),original)
        self.events.reverse();self.nodes.reverse();self.features.reverse();self.refs.reverse()
        self.assertEqual(self.run_analysis(),before)

if __name__=='__main__':unittest.main()

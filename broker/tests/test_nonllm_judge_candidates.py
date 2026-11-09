#!/usr/bin/env python3
"""Only synthetic records and cached vectors; no model, store or sender access."""
import copy
from datetime import datetime
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
spec=importlib.util.spec_from_file_location('numeric_judges',ROOT/'experiments/nonllm-judges/prototype.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
sha=lambda text:hashlib.sha256(text.encode()).hexdigest()


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='numeric-judge-test-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.sender=Mock(side_effect=AssertionError('external action forbidden'))
        for guard in (patch.dict(os.environ,HOME=str(self.root),SPARK_WORKSPACE=str(self.root)),
                      patch.object(socket.socket,'connect',self.sender),patch.object(subprocess,'run',self.sender)):
            guard.start();self.addCleanup(guard.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertIsInstance(subprocess.run,Mock);self.assertNotIn('.vintos',self.root.parts)
        self.nodes=[];self.events=[];self.assignments=[];self.embeddings=[];self.cutoff=1609804800.
        self.encoder=dict(id='synthetic-encoder',artifact_sha256=sha('synthetic artifact'),dimension=2,frozen_at=1609459000.,frozen=True)
        for i in range(3):self.add(i,1609459200.+i)

    def add(self,i,at,angle=0):
        key='synthetic-'+str(i)
        self.nodes.append(dict(id=key,kind='original_act',at=at,parents=[],complete=True))
        self.events.append(dict(node_id=key,origin_id=key,at=at,content_sha256=sha(key),surface='avatar',mode='everyday',source='synthetic-source'))
        self.assignments.append(dict(node_id=key,content_sha256=sha(key),topic_id='synthetic-topic',reviewed=True,evidence_sha256=sha('synthetic evidence')))
        self.embeddings.append(dict(node_id=key,content_sha256=sha(key),encoder_id='synthetic-encoder',vector=[math.cos(angle),math.sin(angle)]))

    def recur(self):return P.recurrence(self.events,self.nodes,self.assignments,self.cutoff)
    def groups(self):return P.candidate_groups(self.events,self.nodes,self.embeddings,self.encoder,self.cutoff,.8)

    def test_original_counts_distinct_days_and_input_immutability(self):
        self.add(3,1609545600.);before=copy.deepcopy((self.events,self.nodes,self.assignments))
        report,details=self.recur()
        self.assertEqual(report['group_counts'],[{'unique_acts':4,'distinct_days':2}])
        self.assertEqual((self.events,self.nodes,self.assignments),before)
        self.assertEqual(details[0]['original_ids'],sorted(e['node_id'] for e in self.events))
        self.assertEqual(report['effects'],'none');self.assertFalse(report['coverage']['lineage_independently_verified'])

    def test_copies_and_repeated_scans_do_not_create_recurrence(self):
        self.events.append(copy.deepcopy(self.events[0]));self.assignments.append(copy.deepcopy(self.assignments[0]))
        self.add(3,1609545600.);self.nodes[-1].update(kind='copy',parents=['synthetic-0'])
        self.events[-1]['origin_id']='synthetic-0'
        report,_=self.recur()
        self.assertEqual(report['assigned_acts'],3)
        self.assertEqual(report['coverage']['excluded'],{'duplicate_copy':1,'influenced_or_derived':1})
        self.assertEqual(report['group_counts'][0]['distinct_days'],1)

    def test_indirect_judge_influence_is_excluded(self):
        self.nodes.extend([dict(id='synthetic-effect',kind='emotion_nudge',at=1609459100.,parents=[],complete=True),
                           dict(id='synthetic-context',kind='context',at=1609459150.,parents=['synthetic-effect'],complete=True)])
        self.nodes[0]['parents']=['synthetic-context']
        self.assertEqual(self.recur()[0]['assigned_acts'],2)
        self.assertEqual(self.groups()[0]['scored_acts'],2)

    def test_missing_incomplete_future_and_cyclic_lineage_is_held(self):
        base=copy.deepcopy(self.nodes)
        for change,reason in (({'parents':['missing']},'lineage_missing'),({'complete':False},'lineage_incomplete'),
                              ({'parents':['synthetic-1']},'future_parent'),({'parents':['synthetic-0']},'lineage_cycle')):
            self.nodes=copy.deepcopy(base);self.nodes[0].update(change)
            self.assertEqual(self.recur()[0]['coverage']['excluded'].get(reason),1)
        self.nodes=base;self.cutoff=self.events[0]['at']
        self.assertEqual(self.recur()[0]['assigned_acts'],0)

    def test_unknown_scope_unreviewed_and_wrong_hash_never_count(self):
        self.events[0]['mode']='unknown';self.assignments[1]['reviewed']=False
        self.assignments[2]['content_sha256']='0'*64
        report,_=self.recur();self.assertEqual(report['assigned_acts'],0)
        self.assertEqual(report['unassigned_admitted_acts'],2)
        self.assertEqual(report['assignment_exclusions']['unreviewed_or_unlinked'],3)

    def test_identity_conflicts_refuse_instead_of_choosing_a_copy(self):
        for collection,field,value in ((self.events,'at',1609459250.),(self.nodes,'complete',False),
                                       (self.assignments,'topic_id','different')):
            altered=copy.deepcopy(collection[0]);altered[field]=value;collection.append(altered)
            with self.assertRaisesRegex(ValueError,'conflicting'):self.recur()
            collection.pop()

    def test_recurrence_topics_do_not_cross_mode_or_surface(self):
        self.events[1]['mode']='intimate';self.events[2]['surface']='reelroom'
        self.assertEqual(self.recur()[0]['topic_scope_groups'],3)

    def test_complete_link_prevents_transitive_chaining_and_does_not_delete(self):
        for i,angle in enumerate((0.,.5,1.)):
            self.embeddings[i]['vector']=[math.cos(angle),math.sin(angle)]
        before=copy.deepcopy(self.events);report,details=self.groups()
        self.assertEqual(sorted(g['size'] for g in details),[1,2])
        self.assertEqual(report['suggested_groups'],1);self.assertEqual(report['scored_acts'],3)
        self.assertEqual(self.events,before)
        self.assertTrue(all(g['minimum_pair_cosine']>=.8 for g in details if g['size']>1))

    def test_grouping_deterministic_under_permutation(self):
        original=self.groups()
        self.events.reverse();self.nodes.reverse();self.embeddings.reverse()
        self.assertEqual(self.groups(),original)

    def test_grouping_keeps_day_source_surface_and_mode_separate(self):
        for field,value in (('source','other'),('surface','reelroom'),('mode','intimate')):
            before=self.events[0][field];self.events[0][field]=value
            self.assertEqual(sorted(g['size'] for g in self.groups()[1]),[1,2]);self.events[0][field]=before
        self.events[0]['at']+=86400;self.nodes[0]['at']+=86400
        self.assertEqual(sorted(g['size'] for g in self.groups()[1]),[1,2])

    def test_cached_binding_missing_and_post_event_encoder_are_explicit(self):
        self.embeddings.pop();self.embeddings[0]['content_sha256']='0'*64
        report,_=self.groups();self.assertEqual(report['scored_acts'],1)
        self.assertEqual(report['cache_exclusions'],{'cache_binding_mismatch':1,'cache_missing':1})
        self.encoder['frozen_at']=self.cutoff
        self.assertEqual(self.groups()[0]['scored_acts'],0)

    def test_cache_conflicts_bad_vectors_and_nonfinite_threshold_refuse(self):
        bad=copy.deepcopy(self.embeddings[0]);bad['encoder_id']='other';self.embeddings.append(bad)
        with self.assertRaisesRegex(ValueError,'conflicting cache'):self.groups()
        self.embeddings.pop()
        for vector in ([0.,0.],[float('nan'),0.],[1.],[True,0.],[2.,0.]):
            self.embeddings[0]['vector']=vector
            with self.assertRaises(ValueError):self.groups()
        with self.assertRaises(ValueError):P.candidate_groups([],[],[],self.encoder,self.cutoff,float('nan'))

    def test_timezone_day_counts_are_explicit_and_naive_timestamps_refused(self):
        report,_=P.recurrence(self.events,self.nodes,self.assignments,self.cutoff,'America/Chicago')
        self.assertEqual(report['group_counts'][0]['distinct_days'],1)
        with self.assertRaisesRegex(ValueError,'timestamp'):P.stamp('2021-01-01T00:00:00')
        for bad in (True,float('inf'),None):
            with self.assertRaises(ValueError):P.stamp(bad)

    def test_public_results_contain_no_private_identifiers_hashes_or_vectors(self):
        payload=json.dumps([self.recur()[0],self.groups()[0]])
        for secret in ('synthetic-0','synthetic-topic','synthetic-source',sha('synthetic-0'),'vector','member_ids'):
            self.assertNotIn(secret,payload)
        self.assertFalse(self.groups()[0]['cache_derivation_verified'])
        self.assertEqual(sorted(self.root.iterdir()),[])

    def test_demo_is_synthetic_and_effect_free(self):
        report=P.demo();self.assertEqual(report['input_kind'],'synthetic')
        self.assertEqual(report['recurrence']['assigned_acts'],3)
        self.assertEqual(report['groups']['suggested_groups'],1)
        self.assertNotIn('synthetic-act-0',json.dumps(report))

    def test_128_act_group_retains_every_member(self):
        for i in range(3,128):self.add(i,1609459200.+i)
        report,details=self.groups()
        self.assertEqual(report['scored_acts'],128)
        self.assertEqual(report['suggested_groups'],1)
        self.assertEqual(details[0]['size'],128)
        self.assertEqual(len(set(details[0]['member_ids'])),128)

    def test_grouping_bound_is_explicit(self):
        for i in range(3,129):self.add(i,1609459200.+i)
        with self.assertRaisesRegex(ValueError,'128'):self.groups()


if __name__=='__main__':unittest.main()

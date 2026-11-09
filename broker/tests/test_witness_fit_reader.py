#!/usr/bin/env python3
"""Synthetic fitting receipts and checkpoint copies; isolated storage and blocked sends."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock
import test_witness_checkpoint_consistency as fixture
import test_witness_review_report as review
import fit_completions as F

A=fixture.A
ROOT=fixture.ROOT


class Tests(unittest.TestCase):
    def setUp(self):
        self.case=fixture.Tests('test_producer_shape_is_observed_fields_not_verified_training')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.packet=copy.deepcopy(self.case.packet)
        self.root=self.case.case.root
        self.assertNotIn('.vintos',self.root.parts)
        self.assertIsInstance(self.case.case.sender,Mock)
        self.clock(130.,131.)
        manifest=self.packet['checkpoint']
        self.receipt=dict(schema='self-fit-completion-v1',mode=manifest['mode'],
            fit_started_at=100.,parameters_ready_at=110.,checkpoint_observed_at=120.,
            blocks={name:dict(rows=3,indices_sha256=str(i)*64,ordered_rows_sha256='a'*64,arrays_sha256='b'*64)
                    for i,name in enumerate(A.FIT_BLOCKS)},
            metadata_sha256=manifest['metadata_sha256'],parameters_sha256='c'*64,
            checkpoint_id=manifest['checkpoint_id'],checkpoint_bytes=manifest['byte_count'],
            boundary='matching_checkpoint_read_after_save_return',source_identity='unverified',
            encoder_identity='unverified',upstream_complete=False,durability='unconfirmed',scoring_effect='none')

    def clock(self,start,stop):
        self.packet['checkpoint']['availability']=A.availability_receipt(dict(
            read_started_at=start,parsed_at=stop,monotonic_elapsed=stop-start,stage='parameters_loaded'))

    def audit(self,packets=None,receipts=None,cutoff=1000.):
        result=F.coverage([self.packet] if packets is None else packets,
                          [self.receipt] if receipts is None else receipts,cutoff)
        F.validate_coverage(result)
        return result

    def state(self,name,**kwargs):
        value=self.audit(**kwargs)
        self.assertEqual(value['states'][name],value['unique_checkpoint_observations'])
        self.assertEqual(value['scoring_effect'],'none');self.assertEqual(value['admission_effect'],'none')
        return value

    def test_exact_metadata_mode_bytes_and_clock_match_are_descriptive(self):
        old=copy.deepcopy((self.packet,self.receipt))
        value=self.state('observed_before_read')
        self.assertEqual(old,(self.packet,self.receipt))
        self.assertEqual(value['source_identity'],'unverified');self.assertEqual(value['encoder_identity'],'unverified')
        serialized=json.dumps(value)
        for private in (self.receipt['checkpoint_id'],self.receipt['metadata_sha256'],'fixture-',str(self.root)):
            self.assertNotIn(private,serialized)
        self.assertIsNone(self.packet['checkpoint']['trained_at'])

    def test_different_read_boundaries_are_separate_observations(self):
        before=copy.deepcopy(self.packet)
        self.clock(115.,125.);overlap=copy.deepcopy(self.packet)
        self.clock(111.,119.);after=copy.deepcopy(self.packet)
        result=self.audit(packets=[before,overlap,after])
        for key in ('observed_before_read','overlapping_read','observed_after_read'):
            self.assertEqual(result['states'][key],1)
        self.assertEqual(result['checkpoint_groups'],1)

    def test_exact_duplicates_collapse_without_losing_supplied_counts(self):
        result=self.audit(packets=[self.packet]*3,receipts=[self.receipt]*4)
        self.assertEqual((result['supplied_artifact_packets'],result['unique_checkpoint_observations']),(3,1))
        self.assertEqual((result['supplied_receipts'],result['unique_receipts']),(4,1))
        self.assertEqual(result['states']['observed_before_read'],1)

    def test_missing_receipt_and_orphan_receipt_are_not_fitting_failures(self):
        self.state('fit_receipt_missing',receipts=[])
        result=self.audit(packets=[])
        self.assertEqual(result['receipts_without_checkpoint_observation'],1)
        self.assertEqual(sum(result['states'].values()),0)
        self.assertEqual(self.audit(packets=[],receipts=[])['unique_receipts'],0)

    def test_exact_checkpoint_required_no_metadata_only_fallback(self):
        self.receipt['checkpoint_id']='d'*64
        result=self.state('fit_receipt_missing')
        self.assertEqual(result['receipts_without_checkpoint_observation'],1)

    def test_legacy_manifest_is_not_upgraded_by_matching_digest(self):
        self.packet['checkpoint']={'checkpoint_id':self.receipt['checkpoint_id']}
        self.state('legacy_manifest')

    def test_metadata_mode_and_byte_mismatch_are_held(self):
        for key,value in (('metadata_sha256','d'*64),('mode','self_ahead' if self.receipt['mode']=='self_on_message' else 'self_on_message'),('checkpoint_bytes',self.receipt['checkpoint_bytes']+1)):
            changed=dict(self.receipt,**{key:value})
            self.state('manifest_mismatch',receipts=[changed])

    def test_multiple_receipts_hold_even_when_only_clock_differs(self):
        for key,value in (('checkpoint_observed_at',121.),('parameters_sha256','d'*64)):
            other=dict(self.receipt,**{key:value})
            self.state('conflicting_fit_receipts',receipts=[self.receipt,other])
            self.assertEqual(self.audit(receipts=[self.receipt,other]),self.audit(receipts=[other,self.receipt]))

    def test_future_conflicting_peer_is_not_discarded_before_comparison(self):
        other=dict(self.receipt,checkpoint_observed_at=1001.)
        self.state('conflicting_fit_receipts',receipts=[self.receipt,other])
        self.state('fit_outside_cutoff',receipts=[dict(self.receipt,checkpoint_observed_at=1000.)])

    def test_conflicting_manifests_cannot_hide_behind_a_matching_copy(self):
        other=copy.deepcopy(self.packet);other['checkpoint']['metadata_sha256']='d'*64
        result=self.state('conflicting_manifests',packets=[self.packet,other])
        self.assertEqual(result,self.audit(packets=[other,self.packet]))

    def test_unobserved_or_unparsed_clock_stays_unknown(self):
        self.packet['checkpoint'].pop('availability');self.state('read_clock_unknown')
        self.packet['checkpoint']['availability']=A.availability_receipt(dict(
            read_started_at=130.,parsed_at=131.,monotonic_elapsed=1.,stage='bytes_read'))
        self.state('read_clock_unknown')

    def test_read_at_cutoff_is_outside_even_when_fit_is_earlier(self):
        self.clock(999.,1000.);self.state('read_outside_cutoff')

    def test_malformed_receipts_rejected_even_without_manifest_or_before_cutoff(self):
        for changed in (dict(self.receipt,extra='private-sentinel'),dict(self.receipt,upstream_complete=True),
                        dict(self.receipt,fit_started_at=False),dict(self.receipt,parameters_ready_at=99.),
                        dict(self.receipt,checkpoint_bytes=True),dict(self.receipt,checkpoint_id='bad'),
                        dict(self.receipt,checkpoint_observed_at=float('nan')),
                        dict(self.receipt,checkpoint_observed_at=10**400)):
            with self.assertRaises(ValueError):self.audit(packets=[],receipts=[changed])
        for rows in (0,True,4097):
            changed=copy.deepcopy(self.receipt);changed['blocks']['train']['rows']=rows
            with self.assertRaises(ValueError):self.audit(receipts=[changed])
        changed=copy.deepcopy(self.receipt)
        for block in changed['blocks'].values():block['rows']=1025
        with self.assertRaises(ValueError):self.audit(receipts=[changed])

    def test_invalid_artifact_peer_is_not_silently_ignored(self):
        other=copy.deepcopy(self.packet);other['emb']=[float('nan')]
        with self.assertRaises(ValueError):self.audit(packets=[self.packet,other])
        with self.assertRaises(ValueError):self.audit(packets=[None])

    def test_public_renderer_has_only_fixed_counts_and_rejects_tampering(self):
        case=review.Tests('test_actual_aggregates_render_without_mutation_or_private_labels')
        case.setUp();self.addCleanup(case.doCleanups)
        original=self.audit();case.report['fit_completion_observations']=original
        text=review.M.render(case.report)
        self.assertIn('Fitting completion observations',text);self.assertIn('observed_before_read: 1',text)
        self.assertNotIn(self.receipt['checkpoint_id'],text)
        for bad in (dict(original,extra='private-sentinel'),dict(original,unique_receipts=False),
                    dict(original,checkpoint_groups=99),dict(original,receipts_without_checkpoint_observation=99)):
            case.report['fit_completion_observations']=bad
            with self.assertRaises(ValueError):review.M.render(case.report)
        bad=copy.deepcopy(original);bad['states']['private-sentinel']=0
        with self.assertRaises(ValueError):F.validate_coverage(bad)
        bad=copy.deepcopy(original);bad['states']['observed_before_read']=0
        with self.assertRaises(ValueError):F.validate_coverage(bad)

    def test_actual_producer_packet_is_accepted_without_encoder_or_training(self):
        import test_witness_fit_completion as producer
        case=producer.Tests('test_exact_saved_checkpoint_and_inputs_bound_without_private_values')
        case.setUp();self.addCleanup(case.doCleanups)
        scope=case.prepared();case.save();A.publish_fit(scope,case.path)
        receipt,=case.packets()
        self.packet['checkpoint']=A.checkpoint(case.path.read_bytes(),case.meta)
        result=self.audit(receipts=[receipt],cutoff=receipt['checkpoint_observed_at']+10)
        self.assertEqual(result['states']['read_clock_unknown'],1)
        case.case.enc.encode.assert_not_called()

    def test_replay_cli_includes_counts_code_hash_and_private_permissions(self):
        base=self.case.case
        sources=[('canonical',[base.row])]
        census,admitted=review.F.R.census(sources,base.nodes,1000.)
        innovation,_=review.F.R.innovation(admitted,[base.f],[base.e],base.ck)
        bundle=dict(input_kind='synthetic',self_artifact_packets=[self.packet],self_fit_completions=[self.receipt],
                    sources=[dict(kind=k,rows=v) for k,v in sources],lineage=list(base.nodes.values()),
                    forecasts=[base.f],embeddings=[base.e],checkpoints=base.ck)
        source=self.root/'fit-bundle.json';source.write_text(json.dumps(bundle));out=self.root/'fit-replay'
        proc=subprocess.run([sys.executable,str(ROOT/'experiments/judges-witness/replay.py'),
            '--scratch',str(self.root),'--input',str(source),'--output',str(out),
            '--cutoff','1970-01-01T00:16:40+00:00'],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        report=json.loads((out/'aggregate.json').read_text())
        self.assertEqual(report['fit_completion_observations'],self.audit())
        self.assertTrue(all(p.stat().st_mode & 0o777==0o600 for p in out.iterdir() if p.is_file()))
        receipt=json.loads((out/'private-run.json').read_text())
        self.assertIn('experiments/judges-witness/fit_completions.py',json.dumps(receipt))
        self.assertEqual(report['census'],json.loads(json.dumps(census)))
        self.assertEqual(report['innovation'],json.loads(json.dumps(innovation)))
        self.assertEqual(report['census']['eligible_replies'],1)


if __name__=='__main__':unittest.main()

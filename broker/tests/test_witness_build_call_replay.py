#!/usr/bin/env python3
"""Actual synthetic producer packets into offline explicit-ID diagnostics."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('build_link_fixture',ROOT/'broker/tests/test_witness_value_map_builds.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)
spec=importlib.util.spec_from_file_location('build_link_replay',ROOT/'experiments/judges-witness/replay.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)

class Tests(unittest.TestCase):
    packets=F.Tests.packets
    def setUp(self):
        F.Tests.setUp(self)
        self.vm.build_map()
        self.builds,self.calls=self.packets('build'),self.packets('call')
        self.cutoff=self.builds[0]['ended_at']+100

    def report(self,builds=None,calls=None):
        return R.value_map_build_links(self.builds if builds is None else builds,self.calls if calls is None else calls,self.cutoff)

    def test_actual_synthesis_build_and_both_named_dependencies(self):
        before=copy.deepcopy((self.builds,self.calls))
        summary,details=self.report()
        self.assertEqual(summary['selection_states'],{'consistent':1})
        self.assertEqual(summary['dependency_states'],{'consistent':2})
        self.assertEqual(summary['admission_effect'],'none')
        self.assertEqual((self.builds,self.calls),before)
        self.assertEqual(details[0]['selected_request_id'],self.builds[0]['selection']['request_id'])
        for secret in [self.builds[0]['build_id']]+[c['request_id'] for c in self.calls]+[c['returned_sha256'] for c in self.calls]:
            self.assertNotIn(secret,json.dumps(summary))

    def test_missing_selected_call_never_substitutes_identical_text(self):
        selected=self.builds[0]['selection']['request_id']
        calls=[c for c in self.calls if c['request_id']!=selected]
        copy_call=copy.deepcopy(next(c for c in self.calls if c['request_id']==selected))
        copy_call['request_id']='synthetic-different-request';calls.append(copy_call)
        self.assertEqual(self.report(calls=calls)[0]['selection_states'],{'missing_call':1})

    def test_missing_dependency_does_not_invalidate_or_clear_its_selected_call(self):
        calls=[c for c in self.calls if c['stage']!='draft_a']
        summary,_=self.report(calls=calls)
        self.assertEqual(summary['selection_states'],{'consistent':1})
        self.assertEqual(summary['dependency_states'],{'consistent':1,'missing_call':1})

    def test_mismatched_identity_hash_and_clock_stay_inconsistent(self):
        selected=self.builds[0]['selection']['request_id']
        for key,value in [('build_id','synthetic-other-build'),('returned_sha256','0'*64),
                           ('ended_at',self.cutoff+1),('started_at',0)]:
            calls=copy.deepcopy(self.calls)
            next(c for c in calls if c['request_id']==selected)[key]=value
            self.assertEqual(self.report(calls=calls)[0]['selection_states'],{'inconsistent_call':1})

    def test_duplicate_records_dedup_but_conflicting_copies_abort_both_orders(self):
        summary,_=self.report(self.builds*2,self.calls*2)
        self.assertEqual(summary['builds_before_cutoff'],1);self.assertEqual(summary['calls_before_cutoff'],3)
        bad=copy.deepcopy(self.calls[0]);bad['upstream_complete']=0
        for calls in ([bad]+self.calls,self.calls+[bad]):
            with self.assertRaises(ValueError) as caught:self.report(calls=calls)
            self.assertNotIn(bad['request_id'],str(caught.exception))

    def test_omitted_duplicate_stage_and_unpublished_observation_cannot_pass(self):
        selected=self.builds[0]['selection']['request_id']
        extra=copy.deepcopy(next(c for c in self.calls if c['request_id']==selected))
        extra['request_id']='synthetic-extra-attempt'
        self.assertEqual(self.report(calls=self.calls+[extra])[0]['selection_states'],{'inconsistent_call':1})
        build=copy.deepcopy(self.builds[0])
        next(c for c in build['calls'] if c['request_id']==selected)['packet_published']=False
        self.assertEqual(self.report(builds=[build])[0]['selection_states'],{'inconsistent_call':1})

    def test_unavailable_selection_and_exclusive_cutoff(self):
        build=copy.deepcopy(self.builds[0]);build['selection'].update(state='unavailable',request_id=None)
        self.assertEqual(self.report(builds=[build])[0]['selection_states'],{'unavailable':1})
        summary,details=R.value_map_build_links(self.builds,self.calls,self.builds[0]['ended_at'])
        self.assertEqual(summary['builds_before_cutoff'],0);self.assertEqual(details,[])

    def test_malformed_reference_or_clock_fails_generically(self):
        build=copy.deepcopy(self.builds[0]);build['selection']['returned_sha256']='bad'
        with self.assertRaises(ValueError):self.report(builds=[build])
        calls=copy.deepcopy(self.calls);calls[0]['started_at']='synthetic-sensitive-invalid-clock'
        with self.assertRaises(ValueError) as caught:self.report(calls=calls)
        self.assertNotIn('sensitive',str(caught.exception))
        calls=copy.deepcopy(self.calls);next(c for c in calls if c['stage']=='synthesis')['dependencies']*=2
        with self.assertRaises(ValueError):self.report(calls=calls)

    def test_actual_surviving_draft_has_no_synthesis_dependencies(self):
        self.responses=[None,'Synthetic surviving result']
        old=self.builds[0]['build_id'];self.vm.build_map()
        build=next(b for b in self.packets('build') if b['build_id']!=old)
        calls=[c for c in self.packets('call') if c['build_id']==build['build_id']]
        summary,_=self.report(builds=[build],calls=calls)
        self.assertEqual(summary['selection_states'],{'consistent':1})
        self.assertEqual(summary['dependency_states'],{})

    def test_unavailable_or_future_draft_dependency_remains_separate(self):
        calls=copy.deepcopy(self.calls)
        synthesis=next(c for c in calls if c['stage']=='synthesis')
        synthesis['dependencies'][0].update(state='unavailable',request_id=None)
        summary,_=self.report(calls=calls)
        self.assertEqual(summary['selection_states'],{'consistent':1})
        self.assertEqual(summary['dependency_states'],{'consistent':1,'unavailable':1})
        calls=copy.deepcopy(self.calls)
        synthesis=next(c for c in calls if c['stage']=='synthesis')
        next(c for c in calls if c['stage']=='draft_a')['ended_at']=synthesis['started_at']+1
        self.assertEqual(self.report(calls=calls)[0]['dependency_states'],{'consistent':1,'inconsistent_call':1})

    def test_response_reported_identity_counts_never_publish_names(self):
        summary,_=self.report()
        self.assertEqual(summary['call_identity_coverage'],{'response_reported':3})
        for call in self.calls:
            self.assertNotIn(call['served_model'],json.dumps(summary))
            self.assertNotIn(call['configured_model'],json.dumps(summary))

    def test_configured_identity_does_not_fill_unknown_or_missing(self):
        calls=copy.deepcopy(self.calls)
        calls[0].update(identity_evidence='unknown',served_model=None,configured_model='synthetic-requested')
        calls[1].pop('identity_evidence');calls[1].pop('served_model')
        summary,_=self.report(calls=calls)
        self.assertEqual(summary['call_identity_coverage'],{'unknown':1,'missing':1,'response_reported':1})
        self.assertEqual(summary['selection_states'],{'consistent':1})

    def test_partial_claimed_and_contradictory_identity_is_malformed(self):
        changes=[{'identity_evidence':'claimed'}, {'served_model':''}, {'served_model':True},
                 {'served_model':'x'*257}, {'identity_evidence':'unknown'}, {'response_sha256':None}]
        for change in changes:
            calls=copy.deepcopy(self.calls);calls[0].update(change)
            self.assertEqual(self.report(calls=calls)[0]['call_identity_coverage'],{'malformed':1,'response_reported':2})
        for field in ('served_model','identity_evidence'):
            calls=copy.deepcopy(self.calls);calls[0].pop(field)
            self.assertEqual(self.report(calls=calls)[0]['call_identity_coverage'],{'malformed':1,'response_reported':2})

    def test_failed_call_identity_and_cutoff_do_not_claim_served_result(self):
        calls=copy.deepcopy(self.calls)
        calls[0].update(outcome='failed',returned_sha256=None)
        self.assertEqual(self.report(calls=calls)[0]['call_identity_coverage'],{'malformed':1,'response_reported':2})
        calls[0].update(identity_evidence='unknown',served_model=None)
        self.assertEqual(self.report(calls=calls)[0]['call_identity_coverage'],{'unknown':1,'response_reported':2})
        cutoff=min(c['ended_at'] for c in self.calls)
        summary,_=R.value_map_build_links(self.builds,self.calls,cutoff)
        self.assertEqual(summary['call_identity_coverage'],{})
        self.assertEqual(summary['calls_before_cutoff'],0)

    def test_cli_opt_in_preserves_census_and_private_output_manifest(self):
        reports=[]
        for enabled in (False,True):
            bundle={'input_kind':'synthetic','sources':[],'value_map_builds':self.builds}
            if enabled:bundle['value_map_calls']=self.calls
            source,output=self.root/('bundle-%s.json'%enabled),self.root/('result-%s'%enabled)
            source.write_text(json.dumps(bundle))
            run=subprocess.run([sys.executable,R.__file__,'--scratch',str(self.root),'--input',str(source),
                                '--output',str(output),'--cutoff','2100-01-01T00:00:00Z'],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            report=json.loads((output/'aggregate.json').read_text());reports.append(report)
            private=output/'private-value-map-links.json';self.assertEqual(private.exists(),enabled)
            if enabled:
                self.assertEqual(private.stat().st_mode&0o777,0o600)
                self.assertIn(hashlib.sha256(private.read_bytes()).hexdigest(),(output/'private-run.json').read_text())
                self.assertEqual(report['value_map_build_links']['selection_states'],{'consistent':1})
        reports[1].pop('value_map_build_links');self.assertEqual(reports[0],reports[1])

if __name__=='__main__':unittest.main()

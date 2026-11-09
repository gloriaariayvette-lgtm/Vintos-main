#!/usr/bin/env python3
"""Synthetic coverage diagnosis stays separate from attribution and live stores."""
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
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('coverage_probe', ROOT/'experiments/judges-witness/coverage.py')
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)

class Tests(unittest.TestCase):
    def setUp(self):
        self.row = dict(role='assistant', content='Synthetic reply only.', turn_id='synthetic-turn', surface='synthetic-chat', timestamp=100)
        self.call = dict(at=80, organ='router:synthetic-chat', model='synthetic-model', provider='synthetic-provider', stage='complete', **{'class':'foreground'})
        self.config = dict(surface_callers={'synthetic-chat':['router:synthetic-chat']}, window_seconds=10)
        self.sender = Mock(side_effect=AssertionError('network forbidden'))
        p = patch.object(socket.socket,'connect',self.sender); p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertIsInstance(self.sender, Mock)

    def run_probe(self, rows=None, calls=None):
        return C.diagnose([self.row] if rows is None else rows, [self.call] if calls is None else calls, self.config, 200)

    def test_wider_opportunity_does_not_change_original_result(self):
        before = copy.deepcopy((self.row,self.call,self.config))
        report, private = self.run_probe()
        original, _ = C.attribution([self.row],[self.call],self.config,200)
        self.assertEqual(report['baseline'],original)
        self.assertEqual(report['baseline']['tiers']['unknown'],1)
        self.assertEqual(report['window_sensitivity']['10'],{'none_in_window':1})
        self.assertEqual(report['window_sensitivity']['30'],{'sole_call_in_window':1})
        self.assertEqual(before,(self.row,self.call,self.config))
        self.assertEqual(private['callers'][0]['first_retained_at'],'1970-01-01T00:01:20+00:00')

    def test_ambiguous_window_not_nearest_promotion(self):
        report,_ = self.run_probe(calls=[self.call,dict(self.call,at=75)])
        self.assertEqual(report['window_sensitivity']['30'],{'multiple_calls_in_window':1})

    def test_other_reply_contests_sole_call(self):
        other = dict(self.row,turn_id='synthetic-other',content='Other synthetic reply.',timestamp=85)
        report,_ = self.run_probe(rows=[self.row,other])
        self.assertEqual(report['window_sensitivity']['30'],{'call_contested_by_other_reply':1})

    def test_identical_source_copies_and_calls_deduplicate_honestly(self):
        report,_ = self.run_probe(rows=[self.row,dict(self.row)],calls=[self.call,dict(self.call)])
        self.assertEqual(report['window_sensitivity']['30'],{'sole_call_in_window':2})
        self.assertEqual(report['baseline']['unique_ledger_records_supplied'],1)

    def test_missing_identity_and_changed_final_text_contest(self):
        for other in (dict(self.row,turn_id=None),dict(self.row,content='Changed synthetic version.')):
            report,_ = self.run_probe(rows=[self.row,other])
            self.assertEqual(report['window_sensitivity']['30'],{'call_contested_by_other_reply':2})

    def test_callers_dates_cutoff_and_unknown_clocks(self):
        report, private = self.run_probe(calls=[self.call,dict(self.call,at=20),dict(self.call,at=200),dict(self.call,at='bad')])
        caller = private['callers'][0]
        self.assertEqual(caller['records'],3); self.assertEqual(caller['clock_unavailable'],1)
        self.assertEqual(caller['largest_observed_gap_seconds'],60)
        self.assertEqual(report['ledger_records_after_cutoff'],1)
        self.assertEqual(report['baseline']['join_states'],{'caller_has_unordered_calls':1})

    def test_unmapped_surface_private_only_and_background_not_candidate(self):
        other = dict(self.row,surface='private-surface-sentinel')
        report, private = self.run_probe(rows=[self.row,other],calls=[dict(self.call,**{'class':'background'})])
        self.assertEqual(report['window_sensitivity']['120'],{'none_in_window':1})
        self.assertNotIn('private-surface-sentinel',json.dumps(report))
        self.assertIn('private-surface-sentinel',json.dumps(private))
        for value in (self.row['content'],self.row['turn_id'],self.call['model'],self.call['provider'],self.call['organ']):
            self.assertNotIn(value,json.dumps(report))
        self.assertNotIn(self.row['content'],json.dumps(private))
        self.assertNotIn(self.row['turn_id'],json.dumps(private))

    def test_position_is_retained_span_not_logging_start(self):
        cases = [([], 'no_retained_foreground_calls'),([dict(self.call,at=150)],'before_first_retained_call'),
                 ([self.call],'after_last_retained_call'),([self.call,dict(self.call,at=150)],'within_retained_span')]
        for calls, state in cases:
            report,_ = self.run_probe(calls=calls)
            self.assertEqual(report['unmatched_span_positions'],{state:1})

    def test_failed_metadata_does_not_gain_attribution(self):
        report,_ = self.run_probe(calls=[dict(self.call,stage='failed')])
        self.assertEqual(report['window_sensitivity']['30'],{'sole_call_metadata_unavailable':1})

    def test_explicit_configured_only_candidate_is_not_recovery(self):
        report,_=self.run_probe(calls=[dict(self.call,model_identity_evidence='configured')])
        self.assertEqual(report['window_sensitivity']['30'],{'sole_call_identity_unobserved':1})
        self.assertEqual(report['baseline']['tiers']['ledger_attributed'],0)

    def test_exact_id_failure_never_enters_wider_recovery(self):
        report,_ = self.run_probe(rows=[dict(self.row,provider_request_id='missing-synthetic-id')])
        self.assertEqual(report['window_sensitivity']['120'],{})
        self.assertEqual(report['baseline']['join_states'],{'provider_id_unmatched':1})

    def test_timezone_and_ambiguous_local_time(self):
        self.config['naive_timezone']='America/Chicago'
        row=dict(self.row,timestamp='2026-11-01T01:30:00')
        report,_ = C.diagnose([row],[self.call],self.config,'2026-11-02T00:00:00Z')
        self.assertEqual(report['baseline']['join_states'],{'reply_clock_unavailable':1})

    def test_bounds_and_invalid_config(self):
        with patch.object(C,'MAX_CALLS',0):
            with self.assertRaises(ValueError): self.run_probe()
        self.config['window_seconds']=30
        with self.assertRaises(ValueError): self.run_probe()

    def missing_surface_evidence(self, rows):
        report, _ = self.run_probe(rows=rows)
        census = report['source_coverage']
        self.assertEqual(census['assistant_copies'], sum(g['copies'] for g in census['groups']))
        return [g['same_turn_evidence'] for g in census['groups'] if g['surface_state'] != 'declared']

    def test_caller_metadata_counts_nonempty_values_not_field_presence(self):
        report, private=self.run_probe(calls=[self.call,dict(self.call,at=70,model='',provider='',stage='synthetic-stage')])
        caller=private['callers'][0]
        self.assertEqual(caller['records'],2)
        self.assertEqual(caller['nonempty_model_and_provider'],1)
        self.assertEqual(caller['stages'],{'complete':1,'synthetic-stage':1})
        self.assertNotIn('synthetic-stage',json.dumps(report))

    def test_source_copies_distinguish_adapter_from_projection(self):
        rows = [dict(self.row, surface=None, _witness_adapter_kind='ledger'),
                dict(self.row, surface='', _witness_adapter_kind='merged', source='ledger')]
        report, _ = self.run_probe(rows=rows)
        self.assertEqual(report['baseline']['tiers']['unknown'], 2)
        groups = report['source_coverage']['groups']
        self.assertEqual({(g['adapter'],g['projection_source'],g['surface_state']) for g in groups},
                         {('ledger','absent','absent'),('merged','ledger','empty')})
        self.assertEqual(self.missing_surface_evidence(rows), ['no_declared_surface_same_id_and_text']*2)

    def test_explicit_peer_surface_is_diagnostic_without_promotion(self):
        rows=[dict(self.row,surface=None,_witness_adapter_kind='ledger'), dict(self.row,_witness_adapter_kind='canonical')]
        original=C.attribution(rows,[self.call],self.config,200)[0]
        report,_=self.run_probe(rows=rows)
        self.assertEqual(report['baseline'],original)
        self.assertEqual(self.missing_surface_evidence(rows),['one_declared_surface_same_id_and_text'])
        self.assertIsNone(rows[0]['surface'])

    def test_surface_peer_needs_exact_unambiguous_identity_and_text(self):
        base=dict(self.row,surface=None)
        self.assertEqual(self.missing_surface_evidence([dict(base,turn_id=None),self.row]),['missing_stable_id'])
        self.assertEqual(self.missing_surface_evidence([dict(base,provenance={'turn_id':'conflict'}),self.row]),['conflicting_identity'])
        self.assertEqual(self.missing_surface_evidence([base,dict(self.row,content=self.row['content']+' ')]),['conflicting_stored_versions'])
        self.assertEqual(self.missing_surface_evidence([base,self.row,dict(self.row,surface='other-synthetic')]),['conflicting_declared_surfaces'])

    def test_surface_peer_after_cutoff_or_unknown_clock_is_not_evidence(self):
        base=dict(self.row,surface=None)
        for peer in (dict(self.row,timestamp=200),dict(self.row,timestamp='unknown')):
            self.assertEqual(self.missing_surface_evidence([base,peer]),['no_declared_surface_same_id_and_text'])
        report,_=self.run_probe(rows=[base,dict(self.row,timestamp=200)])
        self.assertEqual(report['source_coverage']['excluded_at_or_after_cutoff'],1)
        self.assertEqual(self.missing_surface_evidence([dict(base,timestamp='unknown'),self.row]),['clock_unavailable'])

    def test_source_mapping_does_not_masquerade_as_recorded_surface(self):
        self.config['source_surfaces']={'ledger':'synthetic-chat'}
        rows=[dict(self.row,surface=None,_witness_adapter_kind='ledger')]
        self.assertEqual(self.missing_surface_evidence(rows),['no_declared_surface_same_id_and_text'])

    def test_source_census_fixed_labels_only(self):
        row=dict(self.row,_witness_adapter_kind='private-adapter-sentinel',source='private-source-sentinel',surface='private-surface-sentinel')
        report,_=self.run_probe(rows=[row])
        encoded=json.dumps(report)
        for text in ('private-adapter-sentinel','private-source-sentinel','private-surface-sentinel',row['turn_id'],row['content']):
            self.assertNotIn(text,encoded)
        group=report['source_coverage']['groups'][0]
        self.assertEqual((group['adapter'],group['projection_source']),('unknown','other'))

    def historical_call(self, **changes):
        record=dict(at=80,organ='router:chat',**copy.deepcopy(C.HISTORICAL_FIXTURE))
        record.update(changes)
        return record

    def fixture_counts(self,calls):
        report,_=self.run_probe(calls=calls)
        result=report['historical_fixture_coverage']
        self.assertEqual(result['unique_records_supplied'],sum(result['counts'].values()))
        self.assertEqual(result['origin'],'unconfirmed')
        self.assertEqual(result['training_effect'],'none')
        self.assertEqual(result['attribution_effect'],'none')
        return result['counts']

    def test_fixture_metadata_comparison_has_no_attribution_or_origin_effect(self):
        call=self.historical_call()
        before=copy.deepcopy(call)
        report,_=self.run_probe(calls=[call])
        baseline,_=C.attribution([self.row],[call],self.config,200)
        self.assertEqual(report['baseline'],baseline)
        self.assertEqual(self.fixture_counts([call])['matching_metadata'],1)
        self.assertEqual(call,before)

    def test_fixture_matching_requires_every_exact_field_and_usage_object(self):
        original=self.historical_call()
        variants=[]
        for key in ('class','stage','provider','model'):
            variants.append(dict(original,**{key:'other-synthetic'}))
        variants += [dict(original,usage=dict(original['usage'],total_tokens=11)),
                     dict(original,usage=dict(original['usage'],extra=0))]
        counts=self.fixture_counts(variants)
        self.assertEqual(counts['matching_metadata'],0)
        self.assertEqual(counts['other_complete_metadata'],6)

    def test_fixture_missing_invalid_usage_is_not_a_match(self):
        original=self.historical_call()
        variants=[dict(original,usage=value) for value in (None,{},[],dict(original['usage'],prompt_tokens=True),
                  dict(original['usage'],prompt_tokens=7.0),dict(original['usage'],prompt_tokens=-1))]
        variants += [dict(original,**{key:None}) for key in ('class','stage','provider','model')]
        counts=self.fixture_counts(variants)
        self.assertEqual(counts['incomplete_metadata'],10)
        self.assertEqual(counts['matching_metadata'],0)

    def test_fixture_cutoff_and_unknown_clock_are_separate_partitions(self):
        original=self.historical_call()
        counts=self.fixture_counts([dict(original,at=x) for x in (199,200,201,'unknown',None)])
        self.assertEqual(counts['matching_metadata'],1)
        self.assertEqual(counts['excluded_at_or_after_cutoff'],2)
        self.assertEqual(counts['clock_unavailable'],2)

    def test_fixture_records_deduplicate_exactly_without_merging_distinct_calls(self):
        original=self.historical_call()
        counts=self.fixture_counts([original,dict(original),dict(original,at=81)])
        self.assertEqual(counts['matching_metadata'],2)
        self.assertEqual(sum(counts.values()),2)

    def test_fixture_does_not_use_latency_ids_or_other_callers_as_origin(self):
        original=self.historical_call()
        counts=self.fixture_counts([dict(original,latency_ms=100000,provider_request_id='private-sentinel'),
                     dict(original,organ='router:avatar'),dict(original,organ='private-caller')])
        self.assertEqual(counts['matching_metadata'],1)
        self.assertEqual(counts['other_callers'],2)
        self.assertNotIn('private-sentinel',json.dumps(counts))

    def test_fixture_timezone_requires_explicit_unambiguous_clock(self):
        original=self.historical_call()
        self.config['naive_timezone']='America/Chicago'
        report,_=C.diagnose([], [dict(original,at='2026-11-01T01:30:00'),
                               dict(original,at='2026-11-01T01:30:00-05:00')],self.config,'2026-11-02T00:00:00Z')
        counts=report['historical_fixture_coverage']['counts']
        self.assertEqual(counts['clock_unavailable'],1);self.assertEqual(counts['matching_metadata'],1)

    def test_fixture_public_output_is_fixed_aggregate_and_order_independent(self):
        original=self.historical_call()
        calls=[original,dict(original,model='private-model',usage=dict(original['usage'],private_key=1))]
        first=self.run_probe(calls=calls)[0]['historical_fixture_coverage']
        second=self.run_probe(calls=list(reversed(calls)))[0]['historical_fixture_coverage']
        self.assertEqual(first,second)
        rendered=json.dumps(first)
        for value in ('private-model','private_key',original['model'],original['provider']):self.assertNotIn(value,rendered)
        self.assertEqual(set(first),{'scope','profile','fixture_source_commit','unique_records_supplied','counts','origin',
                                     'attribution_effect','training_effect','meaning'})

    def test_cli_private_manifest_and_scratch_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); self.assertNotIn('.vintos',root.parts)
            source=root/'bundle.json'; output=root/'out'
            source.write_text(json.dumps(dict(input_kind='synthetic',sources=[dict(kind='canonical',rows=[self.row])],
                               historical_attribution=dict(self.config,compute_ledger=[self.call,self.historical_call()]))))
            env=dict(os.environ,SPARK_WORKSPACE=str(root),PYTHONDONTWRITEBYTECODE='1')
            cmd=[sys.executable,str(ROOT/'experiments/judges-witness/coverage.py'),'--scratch',str(root),
                 '--input',str(source),'--output',str(output),'--cutoff','1970-01-01T00:03:20Z']
            result=subprocess.run(cmd,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(output.stat().st_mode & 0o777,0o700)
            aggregate=json.loads((output/'aggregate.json').read_text())
            self.assertEqual(aggregate['historical_fixture_coverage']['counts']['other_callers'],1)
            self.assertEqual(aggregate['historical_fixture_coverage']['counts']['matching_metadata'],1)
            manifest=json.loads((output/'private-run.json').read_text())
            for name in ('aggregate.json','private-coverage.json','private-run.json'):
                self.assertEqual((output/name).stat().st_mode & 0o777,0o600)
                if name in manifest['outputs']:
                    self.assertEqual(C.hashlib.sha256((output/name).read_bytes()).hexdigest(),manifest['outputs'][name]['sha256'])
            self.assertNotIn(self.row['content'],result.stdout+result.stderr)
            self.assertNotEqual(subprocess.run(cmd,env=env,capture_output=True).returncode,0)
            bad=root/'.vintos';bad.mkdir(mode=0o700)
            with patch.dict(os.environ,SPARK_WORKSPACE=str(bad)):
                with self.assertRaises(ValueError): C.R.scratch_root(str(bad))
            link=root/'linked';link.symlink_to(source)
            with self.assertRaises(ValueError): C.R.inside(root,str(link))

if __name__=='__main__': unittest.main()

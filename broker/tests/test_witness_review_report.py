#!/usr/bin/env python3
"""Synthetic review formatting, private-run binding and scratch-only CLI."""
import copy
import hashlib
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

ROOT=Path(__file__).resolve().parents[2]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
F=module('review_fixture','broker/tests/test_judges_witness.py')
M=module('review_renderer','experiments/judges-witness/report.py')

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='judges-review-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();os.chmod(self.root,0o700)
        self.sender=Mock(side_effect=AssertionError('external action forbidden'))
        for p in (patch.dict(os.environ,SPARK_WORKSPACE=str(self.root)),patch.object(socket.socket,'connect',self.sender)):
            p.start();self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertNotIn('.vintos',self.root.parts);self.assertIsInstance(self.sender,Mock)
        self.row,self.nodes,self.f,self.e,self.ck=F.fixture()
        census,admitted=F.R.census([('canonical',[self.row])],self.nodes,1000)
        innovation,_=F.R.innovation(admitted,[self.f],[self.e],self.ck)
        behaviour,_=F.R.behaviour_receipt(admitted,1,1000,['fixture-chat'])
        self.report={'schema':'judges-shadow-v1','input_kind':'synthetic','census':census,
                     'innovation':innovation,'behaviour_receipt':behaviour}

    def test_actual_aggregates_render_without_mutation_or_private_labels(self):
        old=copy.deepcopy(self.report);text=M.render(self.report)
        self.assertEqual(old,self.report)
        self.assertIn('Synthetic contract run',text)
        self.assertIn('Strictly eligible replies: 1',text)
        self.assertIn('mean cosine error=0.2',text)
        self.assertNotIn('fixture-',text)
        self.assertNotIn(self.row['content'],text)

    def historical_report(self):
        import witness_attribution as A
        historical, _ = A.attribution([self.row], [], {'surface_callers':{},'window_seconds':5}, 1000)
        report = copy.deepcopy(self.report)
        report['historical_attribution'] = historical
        return report

    def test_historical_attribution_valid_producer_is_descriptive_and_private(self):
        report = self.historical_report()
        original = copy.deepcopy(report)
        text = M.render(report)
        self.assertEqual(report, original)
        self.assertIn('Historical model attribution',text)
        self.assertIn('not unique training turns',text)
        self.assertNotIn(self.row['content'],text)
        self.assertNotIn(self.row['turn_id'],text)

    def test_historical_cutoff_exclusions_and_receipt_clock_are_not_lost(self):
        import witness_attribution as A
        report = self.historical_report()
        self.assertEqual(report['historical_attribution']['copies_without_cutoff_clock'],0)
        self.assertIn('Without a usable cutoff clock: 0',M.render(report))
        historical, _ = A.attribution([self.row], [], {'surface_callers':{},'window_seconds':5}, 100)
        report['historical_attribution'] = historical
        self.assertEqual(historical['excluded'],{'outside_cutoff':1})
        self.assertEqual(historical['join_states'],{})
        text = M.render(report)
        self.assertIn('Outside cutoff: 1',text)
        self.assertIn('Without a usable cutoff clock: 0',text)

    def test_historical_attribution_requires_no_admission_or_training_effect(self):
        for key,value in (('scope','unique_training_turns'),('admission_effect','admit'),('training_effect','train')):
            report = self.historical_report()
            report['historical_attribution'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):M.render(report)

    def test_historical_attribution_counter_conservation_and_bounds(self):
        for field,value in (
            ('label_ledger_agreement',{}), ('label_ledger_agreement',{'agree':2}),
            ('label_ledger_agreement',{'private-label':1}), ('label_ledger_agreement',{'agree':True}),
            ('join_states',{}), ('join_states',{'matched':2}),
            ('excluded',{'outside_cutoff':0,'other_private_exclusion':1}),
            ('copies_without_cutoff_clock',2), ('copies_without_cutoff_clock',True),
            ('tiers',{'observed':1,'ledger_attributed':0,'recorded_label':0,'unknown':0,'private-tier':1})):
            report = self.historical_report()
            report['historical_attribution'][field] = value
            with self.subTest(field=field,value_type=type(value).__name__), self.assertRaises(ValueError):M.render(report)

    def test_zero_eligible_is_insufficient_not_zero_accuracy(self):
        self.report['census']['eligible_replies']=0
        self.report['innovation']['groups']=[]
        self.report['behaviour_receipt']={'status':'no_eligible_observations','eligible_observations':0,'groups':[]}
        text=M.render(self.report)
        self.assertIn('No strictly eligible replies',text)
        self.assertIn('Missing forecasts are not zero error',text)
        self.assertNotIn('mean cosine error=',text)

    def test_not_configured_is_distinct_from_empty_scope(self):
        self.report['behaviour_receipt']={'status':'not_configured'}
        self.assertIn('Not configured: no explicit behaviour',M.render(self.report))
        self.report['behaviour_receipt']={'status':'no_eligible_observations','eligible_observations':0,'groups':[]}
        self.assertIn('no eligible observations in the configured scope',M.render(self.report))

    def test_unknown_fields_and_injected_strings_are_not_echoed(self):
        self.report['private']='SENSITIVE-SENTINEL'
        self.report['census']['source_rows']={'SENSITIVE-SENTINEL':1}
        self.report['innovation']['held']={'SENSITIVE-SENTINEL':1}
        self.report['behaviour_receipt']['meaning']='SENSITIVE-SENTINEL'
        self.assertNotIn('SENSITIVE-SENTINEL',M.render(self.report))

    def test_source_kind_cannot_be_relabelled(self):
        self.report['input_kind']='retained_snapshot'
        self.assertIn('Retained snapshot measurement',M.render(self.report))
        self.report['input_kind']='private-secret'
        with self.assertRaisesRegex(ValueError,'^invalid shadow report evidence$'):M.render(self.report)

    def test_counts_and_geometry_reject_invalid_values(self):
        for value in (True,-1,'private-secret',None):
            bad=copy.deepcopy(self.report);bad['census']['eligible_replies']=value
            with self.assertRaisesRegex(ValueError,'^invalid shadow report evidence$'):M.render(bad)
        for value in (True,float('nan'),float('inf'),-1,3,'private-secret'):
            bad=copy.deepcopy(self.report);bad['innovation']['groups'][0]['mean_cosine_error']=value
            with self.assertRaisesRegex(ValueError,'^invalid shadow report evidence$'):M.render(bad)

    def test_cross_field_counts_are_consistent(self):
        for change in ('eligible','behaviour','percentiles','duplicate_group'):
            bad=copy.deepcopy(self.report)
            if change=='eligible':bad['census']['eligible_replies']=2
            elif change=='behaviour':bad['behaviour_receipt']['eligible_observations']=2
            elif change=='percentiles':bad['innovation']['groups'][0]['percentiles_available']=2
            else:bad['innovation']['groups']*=2
            with self.assertRaisesRegex(ValueError,'^invalid shadow report evidence$'):M.render(bad)

    def test_coverage_states_are_numeric_only_and_not_admission(self):
        self.report['census']['evidence_coverage']['fields']['request_binding']={'private-secret':1}
        text=M.render(self.report)
        self.assertIn('request_binding: recorded=0; not evaluated=0; other recorded states=1',text)
        self.assertNotIn('private-secret',text)
        self.report['census']['evidence_coverage']['fields']['request_binding']={'recorded':2}
        with self.assertRaisesRegex(ValueError,'^invalid shadow report evidence$'):M.render(self.report)

    def test_missing_coverage_is_not_filled_with_zero(self):
        self.report['census']['evidence_coverage']['fields'].pop('request_binding')
        self.assertIn('request_binding: coverage not supplied',M.render(self.report))

    def test_window30_report_validates_separate_partition_and_comparisons(self):
        import witness_attribution as A
        row = dict(role='assistant', content='Synthetic historical reply', turn_id='synthetic-turn',
                   surface='synthetic-chat', timestamp=100, served_by='synthetic-model')
        call = dict(at=80, organ='router:synthetic-chat', model='synthetic-model',
                    provider='synthetic-provider', **{'class':'foreground'})
        config = dict(window_seconds=10, window30_enabled=True,
                      surface_callers={'synthetic-chat':['router:synthetic-chat']})
        historical, _ = A.attribution([row], [call], config, 1000)
        self.report['historical_attribution'] = historical
        text = M.render(self.report)
        self.assertIn('ledger_attributed_window30: 1', text)
        self.assertIn('Exact agreement among added copies with one label: 1/1', text)
        self.assertNotIn('synthetic-model', text)
        for changes in ({'added_copies':2}, {'window_seconds':True}, {'training_effect':'enabled'},
                        {'added_label_ledger_agreement':{'agree':2}}, {'join_states':{'matched_window30':0}}):
            changed = copy.deepcopy(self.report)
            changed['historical_attribution']['window30'].update(changes)
            with self.assertRaises(ValueError): M.render(changed)
        changed = copy.deepcopy(self.report)
        changed['historical_attribution']['window30']['tiers']['observed'] = 1
        with self.assertRaises(ValueError): M.render(changed)

    def paired(self):
        return {'checkpoint_group':1,'n':1,'paired_head_mean_error':.2,'head_error':.2,
                'last_reply_error':.3,'recent_mean_error':.25}

    def test_baselines_stay_separate_and_do_not_declare_a_win(self):
        self.report['innovation']['baselines']['paired_groups']=[self.paired()]
        self.report['self_input_baselines']={'paired_groups':[self.paired()]}
        text=M.render(self.report)
        self.assertEqual(text.count('paired n=1; head=0.2; last reply=0.3; recent mean=0.25'),2)
        self.assertIn('No confidence interval or pass decision',text)
        self.assertIn('Full-reply controls',text);self.assertIn('Observed excerpt-input controls',text)

    def test_pair_denominators_and_group_binding(self):
        for pairs in ([dict(self.paired(),n=2)],[dict(self.paired(),checkpoint_group=2)], [self.paired(),self.paired()]):
            self.report['innovation']['baselines']['paired_groups']=pairs
            with self.assertRaisesRegex(ValueError,'^invalid shadow report evidence$'):M.render(self.report)

    def write_run(self):
        run=self.root/'run';run.mkdir()
        raw=(json.dumps(self.report)+'\n').encode()
        (run/'aggregate.json').write_bytes(raw)
        manifest=F.R.run_manifest(b'synthetic',{}, {'input_kind':self.report['input_kind']},
            {'aggregate.json':{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}})
        (run/'private-run.json').write_text(json.dumps(manifest))
        return run

    def cli(self,run,output):
        return subprocess.run([sys.executable,str(ROOT/'experiments/judges-witness/report.py'),
            '--scratch',str(self.root),'--run',str(run),'--output',str(output)],capture_output=True,text=True)

    def test_cli_private_artifact_binding_and_no_overwrite(self):
        run=self.write_run();before={p.name:p.read_bytes() for p in run.iterdir()}
        output=self.root/'out';result=self.cli(run,output)
        self.assertEqual(result.returncode,0,result.stderr)
        text=(output/'review.md').read_text()
        self.assertIn('Original input, scoring checkout and other output files were not independently verified',text)
        receipt=json.loads((output/'private-render.json').read_text())
        self.assertEqual(receipt['review_sha256'],hashlib.sha256((output/'review.md').read_bytes()).hexdigest())
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in output.iterdir()))
        self.assertEqual(output.stat().st_mode&0o777,0o700)
        self.assertNotEqual(self.cli(run,output).returncode,0)
        self.assertEqual(before,{p.name:p.read_bytes() for p in run.iterdir()})

    def test_tampered_aggregate_or_manifest_rejected_before_output(self):
        run=self.write_run();raw=(run/'aggregate.json').read_bytes()
        (run/'aggregate.json').write_bytes(raw+b' ')
        output=self.root/'out';self.assertNotEqual(self.cli(run,output).returncode,0)
        self.assertFalse(output.exists())
        (run/'aggregate.json').write_bytes(raw)
        m=json.loads((run/'private-run.json').read_text());m['input_bytes']+=1
        (run/'private-run.json').write_text(json.dumps(m))
        self.assertNotEqual(self.cli(run,output).returncode,0);self.assertFalse(output.exists())

    def test_live_named_or_symlink_output_is_rejected(self):
        run=self.write_run();live=self.root/'.vintos';live.mkdir()
        # Path checks reject symlink traversal, even for in-scratch destinations.
        link=self.root/'alias';link.symlink_to(live,target_is_directory=True)
        self.assertNotEqual(self.cli(run,link/'out').returncode,0)
        self.assertFalse((live/'out').exists())
        self.assertNotEqual(self.cli(run,run/'nested-output').returncode,0)
        self.assertFalse((run/'nested-output').exists())
        with patch.dict(os.environ,SPARK_WORKSPACE=str(live)):
            with self.assertRaises(ValueError):F.R.scratch_root(str(live))

    def test_actual_replay_then_formatter_empty_and_populated(self):
        for index,rows in enumerate(([],[self.row])):
            bundle={'input_kind':'synthetic','sources':[{'kind':'canonical','rows':rows}],
                    'lineage':list(self.nodes.values()),'forecasts':[self.f],'embeddings':[self.e],'checkpoints':self.ck}
            source=self.root/f'source-{index}.json';source.write_text(json.dumps(bundle))
            run=self.root/f'replay-{index}'
            p=subprocess.run([sys.executable,str(ROOT/'experiments/judges-witness/replay.py'),
                '--scratch',str(self.root),'--input',str(source),'--output',str(run),
                '--cutoff','1970-01-01T00:16:40+00:00','--behaviour-start','1970-01-01T00:00:01+00:00',
                '--behaviour-surface','fixture-chat'],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            out=self.root/f'review-{index}';p=self.cli(run,out);self.assertEqual(p.returncode,0,p.stderr)
            self.assertIn(f'Strictly eligible replies: {index}',(out/'review.md').read_text())

if __name__=='__main__':unittest.main()

#!/usr/bin/env python3
"""Synthetic pending-file handoffs, isolated stores, stubbed launch and sends."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
import test_witness_self_forecast_inputs as fixtures
import test_witness_review_report as review
M=review.M
import forecast_handoffs as H

W=fixtures.W
ROOT=fixtures.ROOT

class Tests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.Tests('test_actual_job_binds_exact_saved_row_and_recent_inputs')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.assertNotIn('.vintos',self.case.root.parts)
        self.assertIsInstance(self.case.sender,Mock)
        self.runner=Mock()
        self.case.ns.update(hashlib=hashlib,subprocess=subprocess,__file__=str(ROOT/'scripts/jepa_self_head.py'),
                            VENV_PYTHON=sys.executable,RUNNER=self.runner,PENDING_DIR=str(self.case.root/'pending'),
                            ON_MESSAGE_LOGFILE=str(self.case.root/'child.log'),_her=lambda s:s)
        tree=ast.parse((ROOT/'scripts/jepa_self_head.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='launch_on_message')
        exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-launch','exec'),self.case.ns)

    def launch(self,turn='fixture-target',surface='fixture-chat'):
        return self.case.ns['launch_on_message']('synthetic arrival',surface,turn,now=200.)

    def packets(self):
        paths=list(self.case.root.glob('self-forecast-launch-*.json'))+list(self.case.root.glob('self-forecast-handoff-*.json'))
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in paths))
        return [json.loads(p.read_text()) for p in paths]

    def run_job(self,path):
        return self.case.ns['on_message_job'](path,enc=self.case.enc,now=210.)

    def audit(self,rows,packets=None):
        result=H.coverage(rows,self.packets() if packets is None else packets,1000)
        H.validate_coverage(result)
        return result

    def test_actual_launch_and_job_join_without_changing_saved_row(self):
        path=self.launch();pending=json.loads(Path(path).read_text())
        row=self.run_job(path)
        self.assertFalse(Path(path).exists());self.runner.assert_called_once()
        self.assertEqual(row,json.loads(self.case.output.read_text()))
        self.assertNotIn('pending',row);self.assertEqual(set(pending),{'her','arrived_at','surface','turn_id'})
        self.assertEqual(self.audit([row])['states']['joined'],1)
        for packet in self.packets():
            self.assertNotIn('synthetic arrival',json.dumps(packet))
            self.assertNotIn(path,json.dumps(packet))
            self.assertNotIn('fixture-target',json.dumps(packet))

    def test_capture_off_preserves_launch_and_forecast_without_receipts(self):
        with patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH='',JUDGES_CAPTURE_CONFIG=''):
            row=self.run_job(self.launch())
        self.assertIsNotNone(row);self.runner.assert_called_once();self.assertEqual(self.packets(),[])
        self.assertEqual(self.audit([row])['states']['job_receipt_missing'],1)

    def test_no_turn_or_surface_is_unknown_even_with_matching_receipts(self):
        for turn,surface in (('','fixture-chat'),('fixture-target','')):
            row=self.run_job(self.launch(turn,surface))
            self.assertEqual(self.audit([row])['states']['origin_markers_missing'],1)

    def test_pending_mutation_after_launch_is_not_silently_joined(self):
        path=self.launch();p=json.loads(Path(path).read_text());p['her']='different synthetic arrival'
        Path(path).write_text(json.dumps(p));row=self.run_job(path)
        self.assertEqual(self.audit([row])['states']['conflicting_receipts'],1)

    def test_job_without_launch_does_not_invent_origin(self):
        row=self.case.job()
        self.assertEqual(self.audit([row])['states']['launch_receipt_missing'],1)

    def test_launch_failure_has_no_success_receipt_or_retry(self):
        self.runner.side_effect=RuntimeError('synthetic failure')
        self.assertIsNone(self.launch());self.assertEqual(self.packets(),[])
        self.runner.assert_called_once()

    def test_observer_failure_does_not_prevent_job_or_existing_sidecars(self):
        original=W._publish_private
        def publish(root,packet,prefix):
            if prefix in ('self-forecast-launch-','self-forecast-handoff-'):raise OSError('synthetic full')
            return original(root,packet,prefix)
        with patch.object(W,'_publish_private',side_effect=publish):
            row=self.run_job(self.launch())
        self.assertIsNotNone(row);self.assertTrue(list(self.case.root.glob('self-forecast-inputs-*.json')))
        self.assertEqual(self.packets(),[])

    def test_duplicate_receipts_rows_order_and_nonmutation(self):
        row=self.run_job(self.launch());packets=self.packets();before=copy.deepcopy(packets)
        one=self.audit([row],packets);two=self.audit([row,row],list(reversed(packets))*2)
        self.assertEqual(one,two);self.assertEqual(before,packets)

    def test_different_rows_same_turn_are_not_interchanged(self):
        row=self.run_job(self.launch());other=copy.deepcopy(row);other['self']['emb']=[.9,.1]
        result=self.audit([row,other])
        self.assertEqual(result['states']['joined'],1);self.assertEqual(result['states']['job_receipt_missing'],1)

    def test_mismatch_checks_surface_turn_and_arrival(self):
        row=self.run_job(self.launch());packets=self.packets()
        for field,value in (('surface','other'),('turn_id','other'),('arrived_at',199)):
            other=copy.deepcopy(row);other[field]=value;changed=copy.deepcopy(packets)
            for packet in changed:
                if 'forecast_row_sha256' in packet:packet['forecast_row_sha256']=H.digest(H.encoded(other))
            self.assertEqual(self.audit([other],changed)['states']['pending_row_mismatch'],1)

    def test_cutoff_other_mode_and_orphan_receipts(self):
        row=self.run_job(self.launch());future=copy.deepcopy(row);future['ts']=1000
        other=copy.deepcopy(row);other['mode']='ahead'
        result=self.audit([future,other]);self.assertEqual(result['states']['outside_cutoff'],1)
        self.assertEqual(result['states']['not_on_message'],1);self.assertEqual(result['job_receipts_without_row'],1)

    def test_conflicting_job_copies_and_malformed_packets(self):
        row=self.run_job(self.launch());packets=self.packets();job=next(p for p in packets if 'forecast_row_sha256' in p)
        changed=copy.deepcopy(job);changed['pending']['resource_sha256']='a'*64
        self.assertEqual(self.audit([row],packets+[changed])['states']['conflicting_receipts'],1)
        for key,value in (('boundary','other'),('source_identity','verified'),('extra','private-label')):
            bad=copy.deepcopy(job);bad[key]=value
            with self.assertRaises(ValueError):self.audit([row],packets+[bad])
        bad=copy.deepcopy(job);bad['pending']['arrived_at']=True
        with self.assertRaises(ValueError):self.audit([row],packets+[bad])
        bad=copy.deepcopy(job);bad['pending']['turn_id_sha256']=''
        with self.assertRaises(ValueError):self.audit([row],packets+[bad])

    def test_report_fixed_counts_rejects_inconsistent_or_private_fields(self):
        row=self.run_job(self.launch());result=self.audit([row])
        for key,value in (('scoring_effect','admit'),('forecast_rows',2),('job_receipts',0),('extra','private')):
            bad=copy.deepcopy(result);bad[key]=value
            with self.assertRaises(ValueError):H.validate_coverage(bad)
        bad=copy.deepcopy(result);bad['states']['private']=0
        with self.assertRaises(ValueError):H.validate_coverage(bad)
        public=json.dumps(result)
        for private in ('synthetic arrival','fixture-target','fixture-chat',str(self.case.root)):
            self.assertNotIn(private,public)
        H.validate_coverage(H.coverage([],[],1000))
        case=review.Tests('test_actual_aggregates_render_without_mutation_or_private_labels')
        case.setUp();self.addCleanup(case.doCleanups)
        report=dict(case.report,forecast_handoffs=result)
        rendered=M.render(report)
        self.assertIn('joined: 1',rendered)
        self.assertNotIn('fixture-target',rendered)
        for bad in (dict(result,source_identity='verified'),dict(result,extra='private')):
            with self.assertRaises(ValueError):M.render(dict(case.report,forecast_handoffs=bad))

    def test_aggregate_requires_a_distinct_paired_launch_for_each_launch_backed_row(self):
        row=self.run_job(self.launch());base=self.audit([row])
        for state in ('joined','origin_markers_missing','pending_row_mismatch'):
            bad=copy.deepcopy(base)
            bad.update(forecast_rows=2,job_receipts=2,unique_receipts=3)
            bad['states']=dict.fromkeys(H.STATES,0);bad['states'][state]=2
            with self.subTest(state=state):
                with self.assertRaises(ValueError):H.validate_coverage(bad)
        bad=copy.deepcopy(base);bad['launch_receipts_without_job']=1
        with self.assertRaises(ValueError):H.validate_coverage(bad)

    def test_review_rejects_launch_counts_that_cannot_support_reported_joins(self):
        row=self.run_job(self.launch());bad=self.audit([row])
        bad.update(forecast_rows=2,job_receipts=2,unique_receipts=3)
        bad['states']['joined']=2
        case=review.Tests('test_actual_aggregates_render_without_mutation_or_private_labels')
        case.setUp();self.addCleanup(case.doCleanups)
        with self.assertRaises(ValueError):M.render(dict(case.report,forecast_handoffs=bad))

    def test_multiple_paired_launches_and_orphans_conserve_counts(self):
        row=self.run_job(self.launch());packets=self.packets()
        other=copy.deepcopy(row);other['ts']=220.
        pair=copy.deepcopy(packets)
        for packet in pair:
            packet['pending']['resource_sha256']='b'*64
            if 'forecast_row_sha256' in packet:
                packet['forecast_row_sha256']=H.digest(H.encoded(other))
        orphan=copy.deepcopy(next(p for p in packets if p['schema']=='self-forecast-launch-v1'))
        orphan['pending']['resource_sha256']='c'*64
        result=self.audit([row,other],packets+pair+[orphan])
        self.assertEqual(result['states']['joined'],2)
        self.assertEqual(result['launch_receipts_without_job'],1)
        self.assertEqual(result['launch_receipts'],3)
        # Paired launches also cannot outnumber all job receipts, even without rows.
        result=H.coverage([],packets,1000)
        result['launch_receipts']=2;result['unique_receipts']=3
        with self.assertRaises(ValueError):H.validate_coverage(result)

    def test_launch_without_job_is_coverage_gap_not_execution_failure(self):
        self.launch();result=self.audit([])
        self.assertEqual(result['launch_receipts_without_job'],1)
        self.assertEqual(result['source_identity'],'unverified')

    def test_observer_does_not_reopen_pending_file(self):
        pending=dict(her='synthetic arrival',surface='fixture-chat',turn_id='fixture-target',arrived_at=200.)
        with patch('builtins.open',side_effect=AssertionError('no reopening')):
            observation=W.self_forecast_pending(self.case.root/'nonexistent.json',pending)
        self.assertEqual(observation['pending_sha256'],W._fingerprint(pending))

    def test_actual_replay_cli_emits_only_counts_with_private_outputs(self):
        row=self.run_job(self.launch())
        bundle=dict(input_kind='synthetic',forecasts=[row],self_forecast_handoffs=self.packets())
        source=self.case.root/'bundle.json';source.write_text(json.dumps(bundle))
        output=self.case.root/'replay-output'
        result=subprocess.run([sys.executable,str(ROOT/'experiments/judges-witness/replay.py'),
                               '--scratch',str(self.case.root),'--input',str(source),'--output',str(output),
                               '--cutoff','1970-01-01T00:16:40+00:00'],
                              capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads((output/'aggregate.json').read_text())
        self.assertEqual(report['forecast_handoffs'],self.audit([row]))
        self.assertEqual((output/'aggregate.json').stat().st_mode & 0o777,0o600)
        self.assertNotIn('fixture-target',json.dumps(report))
        manifest=json.loads((output/'private-run.json').read_text())
        key='experiments/judges-witness/forecast_handoffs.py'
        self.assertEqual(manifest['scoring_files'][key],hashlib.sha256((ROOT/key).read_bytes()).hexdigest())

    def test_configured_launch_uses_existing_deferred_queue(self):
        import test_witness_deferred_capture as D
        case=D.Tests('test_foreground_does_not_wait_for_publication_and_freezes_packet')
        case.setUp();self.addCleanup(case.doCleanups)
        entered,release,stub=case.stalled()
        with stub:
            self.assertIsNotNone(self.launch());self.assertTrue(entered.wait(1))
            self.assertEqual(list(case.sink.glob('self-forecast-launch-*.json')),[])
            release.set();case.wait_done()
        paths=list(case.sink.glob('self-forecast-launch-*.json'))
        self.assertEqual(len(paths),1);self.assertEqual(paths[0].stat().st_mode & 0o777,0o600)
        self.assertTrue(H.validate_receipt(json.loads(paths[0].read_text())))

    def test_durable_launch_replays_under_its_own_prefix(self):
        import test_witness_sink as S
        case=S.Tests('test_production_destination_is_independent_of_workspace')
        case.setUp();self.addCleanup(case.doCleanups)
        case.settings['durable_queue']=True;case.write_config()
        with patch.object(S.S,'start_recovery',return_value=False):self.assertIsNotNone(self.launch())
        self.assertEqual(list(case.sink.glob('self-forecast-launch-*.json')),[])
        spool,=list((case.sink/S.S.SPOOL_NAME).glob('*.packet'))
        original=spool.read_bytes();line,body=original.split(b'\n',1)
        header=json.loads(line)
        self.assertEqual(header['schema'],'judges-ingress-v2')
        for prefix in ('capture-','../bad',None):
            bad=dict(header,prefix=prefix)
            spool.write_bytes(json.dumps(bad).encode()+b'\n'+body)
            self.assertEqual(S.S.recover_spool(),0)
            self.assertTrue(spool.exists())
        spool.write_bytes(original)
        self.assertEqual(S.S.recover_spool(),1)
        paths=list(case.sink.glob('self-forecast-launch-*.json'));self.assertEqual(len(paths),1)
        self.assertTrue(H.validate_receipt(json.loads(paths[0].read_text())))
        self.assertEqual(list(case.sink.glob('capture-*.json')),[])
        self.assertEqual(S.S.recover_spool(),0)

    def test_background_handoff_prefix_is_accepted_by_configured_sink(self):
        import test_witness_sink as S
        case=S.Tests('test_production_destination_is_independent_of_workspace')
        case.setUp();self.addCleanup(case.doCleanups)
        row=self.case.job()
        paths=list(case.sink.glob('self-forecast-handoff-*.json'));self.assertEqual(len(paths),1)
        packet=json.loads(paths[0].read_text());self.assertFalse(H.validate_receipt(packet))
        self.assertEqual(packet['forecast_row_sha256'],H.digest(H.encoded(row)))
        self.assertFalse(S.S.enqueue_capture(case.sink,{},prefix='unknown-'))

    def test_one_pending_observation_cannot_claim_two_distinct_forecast_rows(self):
        row=self.run_job(self.launch());packets=self.packets()
        other=copy.deepcopy(row);other['self']['emb']=[.5,.5]
        job=copy.deepcopy(next(p for p in packets if 'forecast_row_sha256' in p))
        job['forecast_row_sha256']=H.digest(H.encoded(other));packets.append(job)
        for rows,receipts in (([row,other],packets),([other,row],list(reversed(packets))*2)):
            result=self.audit(rows,receipts)
            self.assertEqual(result['states']['conflicting_receipts'],2)
            self.assertEqual(result['states']['joined'],0)

    def test_unseen_forecast_peer_cannot_hide_pending_origin_conflict(self):
        row=self.run_job(self.launch());packets=self.packets()
        job=copy.deepcopy(next(p for p in packets if 'forecast_row_sha256' in p))
        job['forecast_row_sha256']='a'*64
        result=self.audit([row],packets+[job])
        self.assertEqual(result['states']['conflicting_receipts'],1)
        self.assertEqual(result['job_receipts_without_row'],1)
        self.assertEqual(result['states']['joined'],0)

    def test_later_or_outside_cutoff_peer_does_not_hide_pending_origin_conflict(self):
        row=self.run_job(self.launch());packets=self.packets()
        for at in (220.,1000.):
            other=copy.deepcopy(row);other['ts']=at
            job=copy.deepcopy(next(p for p in packets if 'forecast_row_sha256' in p))
            job['forecast_row_sha256']=H.digest(H.encoded(other))
            result=self.audit([row,other],packets+[job])
            self.assertEqual(result['states']['joined'],0)
            self.assertEqual(result['states']['conflicting_receipts'],1 if at==1000 else 2)
            self.assertEqual(result['states']['outside_cutoff'],1 if at==1000 else 0)

    def test_distinct_pending_resources_are_not_fused_by_shared_turn_marker(self):
        one=self.run_job(self.launch())
        path=self.launch();two=self.case.ns['on_message_job'](path,enc=self.case.enc,now=220.)
        self.assertEqual(one['turn_id'],two['turn_id'])
        result=self.audit([one,two])
        self.assertEqual(result['states']['joined'],2)
        self.assertEqual(result['states']['conflicting_receipts'],0)
        self.assertEqual(result['forecast_rows'],2)

if __name__=='__main__':unittest.main()

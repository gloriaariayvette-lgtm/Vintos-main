"""Synthetic offline intent assessment; all I/O isolated from live state."""
import copy
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT/'experiments/nonllm-judges/intent_shadow.py'
spec = importlib.util.spec_from_file_location('intent_shadow_test', SCRIPT)
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
SELECTED='2026-01-02T00:00:00Z'
DELIVERED='2026-01-02T00:00:02Z'
CUTOFF='2026-01-03T00:00:00Z'


def fixture():
    target=dict(intent_id='synthetic-intent', goal='Deliver the synthetic artifact',
                success_criterion='The declared artifact has a terminal delivery receipt',
                enactment='Deliver artifact', observation_window='this_reply', evidence_type='my_move',
                gloria={}, self={})
    row=dict(intent_id=target['intent_id'], target=target, turn_id='synthetic-turn',
             status='delivered', timestamp=SELECTED, delivered_at=DELIVERED, reply='synthetic reply',
             realized={'field':'YES', 'gloria':'NOT_DECLARED', 'self':'NOT_DECLARED'})
    turn=dict(id=row['turn_id'], intent_id=row['intent_id'], role='assistant', kind='reply',
              source='delivery_receipt', source_sha256='a'*64, at=DELIVERED, text=row['reply'])
    receipt=dict(id='synthetic-receipt', intent_id=row['intent_id'], turn_id=row['turn_id'],
                 operation='artifact_delivery', object_sha256='b'*64, source='action_receipt',
                 source_sha256='c'*64, terminal=True, status='succeeded', at='2026-01-02T00:00:01Z')
    contract=dict(id='synthetic-contract', intent_id=row['intent_id'], axis='field', version=1,
                  target_sha256=S.digest(target), family='mechanical', observation_window='this_reply',
                  evidence_type='my_move', review_kind='independent_human', review_source_sha256='d'*64,
                  reviewed_at='2026-01-01T00:00:00Z', predicate=dict(kind='terminal_receipts_all',
                  conditions=[dict(operation='artifact_delivery',object_sha256='b'*64)], partial_allowed=False))
    return [row], dict(schema='intent-shadow-evidence-v1',turns=[turn],receipts=[receipt]), dict(schema='intent-shadow-contracts-v1',items=[contract])


class Tests(unittest.TestCase):
    def setUp(self): self.rows,self.evidence,self.contracts=fixture()

    def assess(self, cutoff=CUTOFF, zone=None):
        before=copy.deepcopy((self.rows,self.evidence,self.contracts))
        with patch('builtins.open',side_effect=AssertionError('file access forbidden')), \
             patch.object(socket,'socket',side_effect=AssertionError('network forbidden')), \
             patch.object(subprocess,'Popen',side_effect=AssertionError('subprocess forbidden')):
            report=S.assess(self.rows,self.evidence,self.contracts,cutoff,zone)
        self.assertEqual(before,(self.rows,self.evidence,self.contracts))
        return report

    def reason(self, reason, axis='field'):
        report=self.assess();self.assertEqual(report['axes'][axis]['reasons'][reason],1)
        return report

    def test_terminal_success_failure_and_absence_have_different_meanings(self):
        self.reason('observed')
        self.assertEqual(self.assess()['axes']['field']['verdicts']['YES'],1)
        self.evidence['receipts'][0]['status']='failed'
        self.assertEqual(self.assess()['axes']['field']['verdicts']['NO'],1)
        self.evidence['receipts']=[]
        self.reason('missing_receipt')
        self.assertIsNone(self.assess()['axes']['field']['agreement_rate'])

    def test_partial_only_with_declared_subconditions_and_complete_evidence(self):
        predicate=self.contracts['items'][0]['predicate']
        predicate['conditions'].append(dict(operation='action_completion',object_sha256='e'*64))
        self.evidence['receipts'].append(dict(self.evidence['receipts'][0],id='synthetic-other',operation='action_completion',object_sha256='e'*64,status='failed'))
        self.reason('partial_not_defined')
        predicate['partial_allowed']=True
        self.assertEqual(self.assess()['axes']['field']['verdicts']['PARTIAL'],1)
        self.evidence['receipts'][1]['terminal']=False
        self.reason('incomplete_observation')

    def test_selection_and_delivery_identity_are_required(self):
        for mutate,reason in ((lambda r:r.update(status='selected'),'not_delivered'),
                              (lambda r:r.pop('turn_id'),'missing_identity'),
                              (lambda r:r['target'].update(intent_id='another'),'missing_identity')):
            self.setUp();mutate(self.rows[0]);self.reason(reason)
        self.setUp();self.evidence['turns']=[];self.reason('missing_delivery')

    def test_full_delivered_bytes_role_source_and_time_must_match(self):
        for key,value in [('text','synthetic'),('role','user'),('kind','device_event'),('source','guessed'),('source_sha256','bad'),('at',SELECTED)]:
            self.setUp();self.evidence['turns'][0][key]=value;self.reason('delivery_mismatch')

    def test_time_order_unknown_timezone_and_cutoff(self):
        self.rows[0]['timestamp']='2026-01-04T00:00:00Z';self.reason('time_order')
        self.setUp();self.rows[0]['timestamp']='2026-01-02T00:00:00';self.reason('unknown_time')
        self.assertEqual(self.assess(zone='UTC')['axes']['field']['verdicts']['YES'],1)
        self.setUp();self.assertEqual(self.assess(cutoff=DELIVERED)['axes']['field']['reasons']['after_cutoff'],1)
        with self.assertRaises(ValueError): self.assess(cutoff='2026-01-03')

    def test_changed_or_retrospective_contract_cannot_grade(self):
        self.rows[0]['target']['goal']='changed';self.reason('contract_mismatch')
        self.setUp();self.contracts['items'][0]['reviewed_at']=DELIVERED;self.reason('contract_not_prior')
        for key,value in [('review_kind','selector'),('review_source_sha256','bad'),('version',True)]:
            self.setUp();self.contracts['items'][0][key]=value;self.reason('contract_mismatch')

    def test_unsupported_criteria_are_held_without_text_inference(self):
        for family in ('semantic','internal_state','unspecified'):
            self.contracts['items'][0]['family']=family;self.reason('unsupported_criterion')
        self.contracts['items']=[];self.reason('missing_contract')

    def test_invalid_windows_and_not_declared_axes(self):
        report=self.assess()
        for axis in ('gloria','self'):self.assertEqual(report['axes'][axis]['verdicts']['NOT_DECLARED'],1)
        self.rows[0]['target']['criterion_abstained']='window_invalid'
        self.reason('not_declared')
        self.setUp();self.rows[0]['target']['observation_window']='later';self.reason('invalid_window')
        self.setUp();self.rows[0]['target']['self']={'difference_intended':'synthetic','enactment':'synthetic', 'observation_window':'her_next_reply','evidence_type':'her_response'}
        self.reason('invalid_window','self')

    def response_fixture(self):
        row=self.rows[0];row['target'].update(observation_window='her_next_reply',evidence_type='her_response')
        row['response_text']='synthetic response'
        self.evidence['turns'].append(dict(id='synthetic-response',reply_to=row['turn_id'],role='user',kind='reply',source='canonical_user_turn',source_sha256='e'*64,at='2026-01-02T00:00:03Z',text=row['response_text']))
        self.contracts['items'][0].update(target_sha256=S.digest(row['target']),observation_window='her_next_reply',evidence_type='her_response',family='semantic')

    def test_response_requires_exact_parentage_not_proximity_or_label(self):
        self.response_fixture();self.reason('unsupported_criterion')
        self.evidence['turns'][1].pop('reply_to');self.reason('missing_response_join')
        self.evidence['turns'][1]['text']='GLORIA (now): synthetic response';self.reason('missing_response_join')

    def test_device_non_user_missing_and_ambiguous_responses(self):
        self.response_fixture();self.rows[0]['response_source']='gcs';self.reason('device_event_only')
        self.rows[0].pop('response_source');self.evidence['turns'][1]['kind']='device_event';self.reason('device_event_only')
        self.evidence['turns'][1].update(kind='reply',role='assistant');self.reason('not_her_words')
        self.evidence['turns'][1]['role']='user'
        self.evidence['turns'].append(dict(self.evidence['turns'][1],id='synthetic-second'));self.reason('ambiguous_response')
        self.rows[0]['response_text']='';self.reason('no_reply')

    def test_response_bytes_and_time_cannot_be_guessed(self):
        self.response_fixture();self.evidence['turns'][1]['text']='other';self.reason('response_mismatch')
        self.evidence['turns'][1]['text']=self.rows[0]['response_text']
        self.evidence['turns'][1]['at']=SELECTED;self.reason('time_order')
        self.evidence['turns'][1]['at']=CUTOFF;self.reason('after_cutoff')

    def test_receipt_retry_ambiguity_and_exact_duplicates(self):
        receipt=self.evidence['receipts'][0]
        self.evidence['receipts'].append(copy.deepcopy(receipt))
        report=self.assess();self.assertEqual(report['duplicate_records'],1)
        self.assertEqual(report['axes']['field']['verdicts']['YES'],1)
        self.evidence['receipts'][1]['id']='synthetic-retry';self.reason('conflicting_receipt')

    def test_receipt_identity_terminal_status_and_time(self):
        for key,value,reason in [('intent_id','other','incomplete_observation'),('source','selector','incomplete_observation'),('source_sha256','bad','incomplete_observation'),('terminal',1,'incomplete_observation'),('status','pending','incomplete_observation'),('at',CUTOFF,'receipt_time_order'),('turn_id','other','missing_receipt')]:
            self.setUp();self.evidence['receipts'][0][key]=value;self.reason(reason)

    def test_duplicate_and_conflicting_ledger_ids_and_shared_turns(self):
        self.rows.append(copy.deepcopy(self.rows[0]));report=self.assess()
        self.assertEqual(report['distinct_rows'],1);self.assertEqual(report['duplicate_records'],1)
        self.rows[1]['realized']['field']='NO';report=self.assess()
        self.assertEqual(report['axes']['field']['verdicts']['HELD'],2)
        self.rows[1]['intent_id']='other';report=self.assess()
        self.assertEqual(report['ambiguous_intents'],2)

    def test_conflicting_evidence_ids_and_duplicate_contract_keys_refuse(self):
        self.evidence['turns'].append(dict(self.evidence['turns'][0],text='other'))
        with self.assertRaises(ValueError):self.assess()
        self.setUp();self.contracts['items'].append(dict(self.contracts['items'][0],id='other'))
        with self.assertRaises(ValueError):self.assess()

    def test_contract_bounds_and_nonfinite_ignored_fields_refuse(self):
        self.contracts['items'][0]['predicate']['conditions'] *= 2
        self.reason('contract_mismatch')
        self.setUp();self.contracts['items'][0]['predicate']['conditions'] *= 17
        self.reason('contract_mismatch')
        self.setUp();self.evidence['ignored']=float('inf')
        with self.assertRaises(ValueError):self.assess()
        self.setUp();self.contracts['ignored']=float('nan')
        with self.assertRaises(ValueError):self.assess()

    def test_old_verdicts_and_feedback_fields_cannot_affect_shadow(self):
        baseline=self.assess()['axes']['field']['verdicts']
        for old in ('YES','NO','PARTIAL','HELD','NOT_DECLARED',None,['invalid']):
            self.rows[0]['realized']={'field':old}
            self.rows[0].update(priority={'field':999},held_reason={'field':'no_reply'},selection_check={'x':False})
            self.assertEqual(self.assess()['axes']['field']['verdicts'],baseline)
        self.assertEqual(self.assess()['axes']['field']['old_vs_shadow']['INVALID']['YES'],1)

    def test_expired_axis_excludes_even_complete_terminal_evidence(self):
        for old in ('HELD', 'YES', 'NO', None):
            self.setUp()
            self.rows[0].update(realized={'field':old}, held_reason={'field':'her_reply_window_expired'})
            report=self.reason('her_reply_window_expired')
            field=report['axes']['field']
            self.assertEqual(field['verdicts']['HELD'],1)
            self.assertEqual(sum(field['verdicts'][v] for v in ('YES','PARTIAL','NO')),0)
            self.assertEqual(field['agreement_denominator'],0)
            self.assertIsNone(field['agreement_rate'])
            self.assertEqual(report['rule_version'],2)
        self.rows[0]['target']['criterion_abstained']='synthetic-abstention'
        self.reason('not_declared')

    def test_expiry_is_axis_local_and_single_maps_only_to_single_field(self):
        row=self.rows[0]
        row['target']['self']=dict(difference_intended='synthetic move',enactment='synthetic enactment',
                                  observation_window='this_reply',evidence_type='my_move')
        self.contracts['items'][0]['target_sha256']=S.digest(row['target'])
        self.contracts['items'].append(dict(self.contracts['items'][0],id='synthetic-self-contract',axis='self'))
        row.update(realized={'field':'YES','self':'HELD'},held_reason={'self':'her_reply_window_expired'})
        report=self.reason('her_reply_window_expired','self')
        self.assertEqual(report['axes']['field']['verdicts']['YES'],1)
        row['held_reason']={'single':'her_reply_window_expired'}
        self.reason('observed')  # Single reason cannot leak into per-axis records.
        self.reason('observed','self')
        row['realized']='HELD'
        self.reason('her_reply_window_expired')
        self.reason('observed','self')
        for reasons in (None, [], 'her_reply_window_expired', {'field':'unknown_reason'}):
            row['held_reason']=reasons;self.reason('observed')

    def test_response_expiry_and_waiting_are_distinct_coverage_reasons(self):
        self.response_fixture();row=self.rows[0]
        row['target']['gloria']=dict(difference_intended='synthetic response',enactment='synthetic enactment',
                                    observation_window='her_next_reply',evidence_type='her_response')
        self.contracts['items'][0]['target_sha256']=S.digest(row['target'])
        self.contracts['items'].append(dict(self.contracts['items'][0],id='synthetic-gloria-contract',axis='gloria'))
        row.update(realized={'field':'HELD','gloria':'HELD'},
                   held_reason={'field':'her_reply_window_expired','gloria':'her_reply_window_expired'})
        self.reason('her_reply_window_expired');self.reason('her_reply_window_expired','gloria')
        row.pop('held_reason');row.pop('response_text');row['realized']={'field':None,'gloria':None}
        row['skipped_observations']={'n':999,'first':0,'last':1,'reason':'device_event_only'}
        report=self.reason('no_reply');self.reason('no_reply','gloria')
        self.assertEqual(report['axes']['field']['old_vs_shadow']['MISSING']['HELD'],1)
        self.assertIsNone(report['axes']['field']['agreement_rate'])

    def test_no_output_text_ids_hashes_dynamic_keys_or_false_accuracy_claim(self):
        self.rows[0]['synthetic-private-key']='synthetic-private-value'
        report=self.assess();raw=json.dumps(report)
        for forbidden in ('synthetic','a'*64,'b'*64,'Deliver','2026-01'):self.assertNotIn(forbidden,raw)
        self.assertFalse(report['source_claims_verified']);self.assertFalse(report['semantic_accuracy_measured'])
        self.assertTrue(report['conditional_on_supplied_contracts'])
        for key in ('runtime_writes','inference_calls','anchors_emitted','labels_emitted','training_signals_emitted','policy_inputs_emitted'):self.assertEqual(report[key],0)

    def test_recognized_legacy_shape_is_held_not_malformed_or_regraded(self):
        legacy=dict(target=dict(field_state='synthetic field',enactment='synthetic move'),realized='NO')
        self.rows=[legacy]
        result=self.reason('legacy_shape')
        self.assertEqual(result['axes']['field']['verdicts']['HELD'],1)
        self.assertEqual(result['axes']['field']['old_vs_shadow']['NO']['HELD'],1)
        legacy['target']['criterion_abstained']='window_missing';self.reason('not_declared')
        legacy['target'].pop('criterion_abstained')
        legacy['target']['goal']=False;self.reason('invalid_declaration')
        legacy['target'].pop('goal')
        legacy['realized']=None;self.reason('legacy_shape')
        for key,value in [('status','delivered'),('intent_id','synthetic-modern'),('turn_id','synthetic-modern'),('realized',{'field':'NO'})]:
            self.rows=[dict(legacy,**{key:value})];self.reason('invalid_declaration')
        self.rows=[legacy];legacy['target'].pop('enactment');self.reason('invalid_declaration')
        self.setUp();self.rows[0]['target'].pop('success_criterion');self.reason('invalid_declaration')

    def test_empty_and_legacy_snapshots_have_no_invented_support(self):
        self.rows=[];report=self.assess();self.assertEqual(report['distinct_rows'],0)
        self.assertIsNone(report['axes']['field']['agreement_rate'])
        self.setUp();self.rows[0].pop('intent_id');self.reason('missing_identity')
        self.rows[0]['target']['gloria']='malformed';self.reason('invalid_declaration','gloria')

    def cli(self,root,extra=()):
        return subprocess.run([sys.executable,str(SCRIPT),'--scratch',str(root),'--ledger',str(root/'ledger.json'),'--cutoff',CUTOFF,*extra],capture_output=True,text=True,timeout=15)

    def test_cli_private_files_unchanged_and_no_side_effects(self):
        with tempfile.TemporaryDirectory(prefix='intent-shadow-') as d:
            root=Path(d).resolve();root.chmod(0o700)
            files={'ledger.json':self.rows,'evidence.json':self.evidence,'contracts.json':self.contracts,'campaign-live.json':{'synthetic':'untouched'}}
            for name,value in files.items():
                p=root/name;p.write_text(json.dumps(value));p.chmod(0o600)
            before={p.name:p.read_bytes() for p in root.iterdir()}
            result=self.cli(root,['--evidence',str(root/'evidence.json'),'--contracts',str(root/'contracts.json')])
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['axes']['field']['verdicts']['YES'],1)
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})
            self.assertNotIn(str(root),result.stdout+result.stderr)
            result=self.cli(root);self.assertEqual(json.loads(result.stdout)['axes']['field']['reasons']['missing_delivery'],1)

    def test_cli_generic_refusal_and_private_bounds(self):
        with tempfile.TemporaryDirectory(prefix='intent-shadow-') as d:
            root=Path(d).resolve();root.chmod(0o700);p=root/'ledger.json'
            for raw in ('[{"id":1,"id":2}]','[NaN]','private-error',' '*(4*1024*1024+1)):
                p.write_text(raw);p.chmod(0o600);result=self.cli(root)
                self.assertEqual((result.returncode,result.stdout,result.stderr),(1,'','intent_shadow_refused\n'))
            p.write_text(json.dumps(self.rows));p.chmod(0o644);self.assertEqual(self.cli(root).returncode,1)
            p.unlink();p.symlink_to(root/'missing');self.assertEqual(self.cli(root).returncode,1)


if __name__=='__main__':unittest.main()

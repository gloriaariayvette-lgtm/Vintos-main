#!/usr/bin/env python3
"""Real synthetic packet producers to offline final-version joins; no sends/models."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import witness_artifact_join as J
import witness_self_artifacts as A
from witness_receipts import digest
from test_judges_witness import fixture, R


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='artifact-join-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.sender=Mock(side_effect=AssertionError('external action forbidden'))
        for p in (patch.dict(os.environ,SPARK_WORKSPACE=str(self.root),JUDGES_CAPTURE_SCRATCH=str(self.root)),
                  patch.object(socket.socket,'connect',self.sender)):
            p.start();self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.row,self.nodes,self.f,self.e,self.ck=fixture()
        self.manifest=A.checkpoint(b'synthetic checkpoint',{'schema':'synthetic-self','mode':'self_on_message'})
        self.assertNotIn('.vintos',self.root.parts)
        self.assertIsInstance(self.sender,Mock)

    def make(self,text=None,ledger=False):
        row=copy.deepcopy(self.row)
        if text is not None:
            row['content']=text;row['witness_receipt']['response_sha256']=digest(text)
        original=copy.deepcopy(row)
        if ledger:
            row['vintos']=row.pop('content')+'\n\nridge: synthetic device mark'
            row['witness_final_text']=original['content'];row['witness_final_sha256']=digest(original['content'])
        raw=row['vintos'] if ledger else row['content']
        normalized=J.normalized_reply(raw)
        observation=A.reply_source(row,'vintos' if ledger else 'content',normalized)
        exchange={'ts':'1970-01-01T00:01:50Z','her':'synthetic prompt','his':normalized,
                  'turn_id':row['turn_id'],'_witness_reply_source':observation}
        encoder=types.SimpleNamespace(encode=Mock(return_value=[[.8,.6]]))
        before=set(self.root.glob('self-audit-embedding-*.json'))
        A.audit_encoder(encoder,A.ledger_rows([exchange],retain=True),self.manifest).encode([normalized[:400]])
        files=set(self.root.glob('self-audit-embedding-*.json'))-before
        self.assertEqual(len(files),1);self.assertEqual(encoder.encode.call_count,1)
        packet=json.loads(files.pop().read_text())
        sources=[('ledger' if ledger else 'canonical',[row])]
        _,admitted=R.census(sources,self.nodes,1000)
        self.assertEqual(len(admitted),1)
        return sources,admitted,packet,exchange

    def join(self,sources,admitted,packet):
        return J.join_artifacts(admitted,sources,self.nodes,[packet],1000)

    def state(self,expected,*args):
        summary,details=self.join(*args)
        self.assertEqual(summary['states'],{expected:1})
        self.assertEqual(details[0]['state'],expected)
        return summary,details

    def test_actual_audit_packet_binds_exact_full_reply_without_scoring(self):
        sources,admitted,packet,_=self.make()
        summary,details=self.state('bound_full_text',sources,admitted,packet)
        self.assertEqual(summary['bound_unique_replies'],1)
        self.assertEqual(summary['scoring_effect'],'none')
        self.assertEqual(summary['encoder_identity'],'unverified')
        self.assertEqual(details[0]['final_response_sha256'],digest(self.row['content']))
        self.assertNotIn(self.row['content'],json.dumps((summary,details)))
        self.assertNotIn('emb',details[0])

    def test_long_final_is_an_excerpt_not_a_full_reply_vector(self):
        sources,admitted,packet,_=self.make('x'*401)
        self.state('bound_excerpt',sources,admitted,packet)

    def test_repeated_runtime_observations_reach_conflict_detector(self):
        sources, admitted, _, exchange = self.make()
        encoder = types.SimpleNamespace(encode=Mock(side_effect=[[[1., 0.]], [[0., 1.]]]))
        before = set(self.root.glob('self-audit-embedding-*.json'))
        wrapped = A.audit_encoder(encoder, A.ledger_rows([exchange], retain=True), self.manifest)
        wrapped.encode([exchange['his'][:400]])
        wrapped.encode([exchange['his'][:400]])
        files = set(self.root.glob('self-audit-embedding-*.json')) - before
        packets = [json.loads(path.read_text()) for path in files]
        self.assertEqual(len(packets), 2)
        self.assertEqual(encoder.encode.call_count, 2)
        summary, details = J.join_artifacts(admitted, sources, self.nodes, packets, 1000)
        self.assertEqual(summary['states'], {'conflicting_vector_observations': 2})
        self.assertEqual(summary['bound_unique_replies'], 0)
        self.assertEqual(summary['scoring_effect'], 'none')

    def test_explicit_ledger_final_attestation_handles_appended_marks(self):
        sources,admitted,packet,_=self.make(ledger=True)
        self.state('bound_full_text',sources,admitted,packet)
        source=sources[0][1][0]
        self.assertNotEqual(digest(source['vintos']),admitted[0]['witness_final_sha256'])

    def test_cleanup_cannot_replace_the_producer_final_version(self):
        sources,admitted,packet,_=self.make('  intentional surrounding whitespace  ')
        self.state('normalization_changes_final',sources,admitted,packet)

    def test_source_digest_is_required_no_text_or_timestamp_fallback(self):
        sources,admitted,packet,_=self.make()
        sources[0][1][0]['unrelated_field']='changed row version'
        self.state('exact_source_row_missing',sources,admitted,packet)

    def test_unknown_id_or_surface_is_never_guessed(self):
        sources,admitted,packet,ex=self.make()
        for key in ('observed_turn_id','observed_surface'):
            bad=copy.deepcopy(packet);bad['source_refs'][0]['reply_source'][key]=None
            self.state('source_observation_mismatch',sources,admitted,bad)
        self.state('reply_not_admitted',sources,[],packet)

    def test_changed_final_with_same_id_is_not_joined(self):
        sources,admitted,packet,_=self.make()
        target=copy.deepcopy(admitted[0]);target['content']='another final reply'
        target['witness_receipt']['response_sha256']=digest(target['content'])
        self.state('final_version_mismatch',sources,[target],packet)

    def test_source_copy_must_independently_pass_admission(self):
        sources,admitted,packet,ex=self.make()
        row=sources[0][1][0];row['test_mode']=True
        observed=A.reply_source(row,'content',ex['his'])
        packet['source_refs'][0]['reply_source']=observed
        self.state('source_copy_not_admitted',sources,admitted,packet)

    def test_input_hash_length_and_normalized_hash_must_match(self):
        sources,admitted,packet,_=self.make()
        for key,value in [('encoder_input_sha256','0'*64),('encoder_input_chars',400)]:
            changed=copy.deepcopy(packet);changed[key]=value
            self.state('input_transform_mismatch',sources,admitted,changed)
        changed=copy.deepcopy(packet);changed['source_refs'][0]['normalized_reply_sha256']='0'*64
        self.state('source_observation_mismatch',sources,admitted,changed)

    def test_old_packet_without_reply_source_remains_missing(self):
        sources,admitted,packet,_=self.make()
        del packet['source_refs'][0]['reply_source']
        self.state('missing_source_observation',sources,admitted,packet)

    def test_duplicate_packets_deduplicate_and_conflicting_vectors_hold_both(self):
        sources,admitted,packet,_=self.make()
        summary,details=J.join_artifacts(admitted,sources,self.nodes,[packet,packet],1000)
        self.assertEqual(summary['unique_packets'],1);self.assertEqual(len(details),1)
        bad=copy.deepcopy(packet);bad['emb']=[1.,0.]
        for packets in ([bad,packet],[packet,bad]):
            summary,details=J.join_artifacts(admitted,sources,self.nodes,packets,1000)
            self.assertEqual(summary['states'],{'conflicting_vector_observations':2})
            self.assertEqual(summary['bound_unique_replies'],0)

    def test_malformed_vectors_abort_instead_of_disappearing_behind_good_copy(self):
        sources,admitted,packet,_=self.make()
        for vector in ([True,False],[0,0],[float('nan'),0],['bad',0]):
            bad=copy.deepcopy(packet);bad['emb']=vector
            with self.assertRaises(ValueError):J.join_artifacts(admitted,sources,self.nodes,[packet,bad],1000)

    def test_forecast_feature_packet_uses_same_binding_without_target_claim(self):
        sources,admitted,_,ex=self.make()
        art=A.forecast_artifacts([ex],{ex['his'][:400]:[.8,.6]},
                               {'_witness_checkpoint':self.manifest},{'checkpoint_id':self.manifest['checkpoint_id']})
        packet={'schema':'self-forecast-artifacts-v1','artifacts':art}
        summary,_=self.state('bound_full_text',sources,admitted,packet)
        self.assertEqual(summary['forecast_target_selection'],'not_evaluated')

    def test_cleanup_contract_matches_actual_reader(self):
        tree=ast.parse((ROOT/'scripts/jepa_self_head.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='his_words')
        ns={'_DEVICE_LINE':re.compile(r'^(?:ridge|tenera|ferri):',re.I)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-reader','exec'),ns)
        for text in (' voice ','--source','  a\n\nridge: x\n\nferri: y ','ridge: sole paragraph',
                     'a\n\nordinary\n\nTENERA: x','Unicode é\n\nparagraph',''):
            self.assertEqual(J.normalized_reply(text),ns['his_words'](text))

    def test_report_projects_fixed_counts_without_private_labels(self):
        from test_witness_review_report import M
        sources,admitted,packet,_=self.make()
        section,_=self.join(sources,admitted,packet)
        section['private_label']='do not publish this'
        rendered='\n'.join(M.artifact_coverage(section,1))
        self.assertIn('full-text bindings: 1',rendered)
        self.assertIn('not scorable forecasts',rendered)
        self.assertNotIn('do not publish this',rendered)
        for key,value in [('bound_unique_replies',2),('source_references',2),('scoring_effect','enabled')]:
            bad=copy.deepcopy(section);bad[key]=value
            with self.assertRaises(ValueError):M.artifact_coverage(bad,1)

    def test_cli_private_binding_receipt_and_unchanged_scoring(self):
        sources,admitted,packet,_=self.make(ledger=True)
        bundle={'input_kind':'synthetic','sources':[{'kind':k,'rows':v} for k,v in sources],
                'lineage':list(self.nodes.values())}
        reports=[]
        for name,with_packets in (('before',False),('after',True)):
            payload=copy.deepcopy(bundle)
            if with_packets:payload['self_artifact_packets']=[packet]
            source=self.root/(name+'.json');source.write_text(json.dumps(payload))
            output=self.root/name
            run=subprocess.run([sys.executable,str(R.__file__),'--scratch',str(self.root),'--input',str(source),
                                '--output',str(output),'--cutoff','1970-01-01T00:16:40Z'],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            reports.append(json.loads((output/'aggregate.json').read_text()))
        joins=reports[1].pop('self_artifact_joins');self.assertEqual(reports[0],reports[1])
        self.assertEqual(joins['states'],{'bound_full_text':1})
        private=self.root/'after/private-self-artifact-joins.json'
        self.assertEqual(private.stat().st_mode&0o777,0o600)
        manifest=json.loads((self.root/'after/private-run.json').read_text())
        self.assertEqual(manifest['outputs']['private-self-artifact-joins.json']['sha256'],hashlib.sha256(private.read_bytes()).hexdigest())
        self.assertNotIn(self.row['content'],private.read_text())


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    sys.exit(not result.wasSuccessful())

#!/usr/bin/env python3
"""Synthetic native schema inventory; no private stores or external calls."""
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
spec = importlib.util.spec_from_file_location('shape_test', ROOT/'experiments/nonllm-judges/verdict_shapes.py')
V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)
VOICE = '## 2020-01-01 00:00 — Score 2\nSYNTHETIC_PRIVATE_NOTE\nReply excerpt: SYNTHETIC_PRIVATE_REPLY\n'
DEV = '## 2020-01-01 00:00 — Deviation (score: 0.45)\n**Felt:** SYNTHETIC_PRIVATE_NOTE\n**Not aligned.** Something resisted.\n'
BINDING = dict(schema='judge-reply-binding-v1',turn_id='synthetic-turn',content_sha256='a'*64,judged_sha256='b'*64,recorded_at='2020-01-01T00:00:01Z')


def humor(source='vintos', **fields):
    return dict(signal=.8, type='self_contradiction', stated='SYNTHETIC_PRIVATE_TEXT',actual='SYNTHETIC_PRIVATE_TEXT',
                what_makes_it_funny='SYNTHETIC_PRIVATE_TEXT', source=source, timestamp='2020-01-01T00:00:00Z', used=False, **fields)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='verdict-shapes-');self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve();self.root.chmod(0o700)
        self.assertNotIn('.vintos',self.root.parts)
        self.sender=Mock(side_effect=AssertionError('network forbidden'))
        p=patch.object(socket.socket,'connect',self.sender);p.start();self.addCleanup(p.stop)
        self.assertIs(socket.socket.connect,self.sender);self.addCleanup(self.sender.assert_not_called)
    def classify(self, judge, record, store=''):
        return V.classify(judge,record,store)
    def file(self, text, name='input.json'):
        p=self.root/name;p.write_text(text);p.chmod(0o600);return p
    def cli(self, *args):
        return subprocess.run([sys.executable,str(ROOT/'experiments/nonllm-judges/verdict_shapes.py'),'--scratch',str(self.root),*map(str,args)],capture_output=True,text=True)
    def test_legacy_and_bound_voice_selected_scores(self):
        for score in (1,2,3):
            record=VOICE.replace('Score 2','Score '+str(score))
            for suffix in ('','<!-- judge-reply-binding: '+json.dumps(BINDING)+' -->\n'):
                self.assertEqual(self.classify('voice_coherence',record+suffix)['band'],'flag')
        for record in (VOICE.replace('Score 2','Score 4'),VOICE.replace('SYNTHETIC_PRIVATE_NOTE','none'),VOICE.replace('Reply excerpt:','excerpt:')):
            self.assertEqual(self.classify('voice_coherence',record)['band'],'unsupported')
    def test_deviation_aligned_never_becomes_pass_from_prose(self):
        self.assertEqual(self.classify('deviation_check',DEV)['band'],'flag')
        aligned=DEV.replace('Deviation','Aligned').replace('**Not aligned.** Something resisted.','**This felt like me.**')
        self.assertEqual(self.classify('deviation_check',aligned)['band'],'abstain')
        for record in (DEV.replace('0.45','0.30'),DEV.replace('0.45','1.01'),DEV.replace('**Not aligned.** Something resisted.','deviation is certain')):
            self.assertEqual(self.classify('deviation_check',record)['band'],'unsupported')
    def test_presence_current_flags_and_explicit_exemption(self):
        row=dict(id='synthetic',composite=.1,flag=False)
        self.assertEqual(self.classify('presence_audit',row)['band'],'pass')
        row['flag']=True;self.assertEqual(self.classify('presence_audit',row)['band'],'flag')
        row['exempt']='requested_work';self.assertEqual(self.classify('presence_audit',row)['band'],'abstain')
        row['exempt']='SYNTHETIC_UNKNOWN';self.assertEqual(self.classify('presence_audit',row)['band'],'unsupported')
    def test_presence_legacy_history_abstains_even_when_high(self):
        for score in (0,1):
            row=dict(id='synthetic',composite=score,arrived=score,moved=score,left_alive=score,explained=0)
            self.assertEqual(self.classify('presence_audit',row,V.STORES['presence_history'])['band'],'abstain')
            self.assertEqual(self.classify('presence_audit',row,V.STORES['presence'])['band'],'unsupported')
    def test_prospective_presence_history_requires_retained_binding(self):
        row=dict(id='synthetic',composite=.1,flag=False,reply_binding=BINDING)
        self.assertEqual(self.classify('presence_audit',row,V.STORES['presence_history'])['band'],'pass')
        row['reply_binding']={};self.assertEqual(self.classify('presence_audit',row,V.STORES['presence_history'])['band'],'abstain')
    def test_all_source_proven_humor_families(self):
        cases=[(humor(), 'humor_reply','pass'),
               (humor(material_kind='self_play',perpetrator='vintos',reply_binding=BINDING),'humor_reply','pass'),
               (humor('gloria',original='synthetic',expected='synthetic'),'humor_incoming','unsupported'),
               (humor('moltbook_exchange',perpetrator='synthetic-other'),'humor_social_exchange','unsupported'),
               (humor('self',mechanism='synthetic'),'humor_self_observation','unsupported')]
        trial=humor('self',material_kind='self_mismatch',perpetrator='vintos');trial['type']='behavioral_default'
        cases.append((trial,'humor_behavioral_trial','unsupported'))
        for record,shape,band in cases:
            result=self.classify('humor_detector',record);self.assertEqual((result['shape'],result['band']),(shape,band))
    def test_humor_signal_does_not_coerce_alias_or_bad_numeric(self):
        for value in (True,False,None,'0.8',float('nan'),float('inf'),-1,1.01):
            row=humor();row['signal']=value
            self.assertEqual(self.classify('humor_detector',row)['band'],'unsupported')
        row=humor();row['humor_signal']=row.pop('signal')
        self.assertEqual(self.classify('humor_detector',row)['band'],'unsupported')
        row=humor();row['signal']=.49;self.assertEqual(self.classify('humor_detector',row)['band'],'unsupported')
        row['signal']=.5;self.assertEqual(self.classify('humor_detector',row)['band'],'pass')
    def test_humor_never_recovers_subject_from_free_text(self):
        for source in (None,'SYNTHETIC_PRIVATE_SOURCE'):
            row=humor(source,perpetrator='vintos');row['note']='pass; his own message; a reply'
            self.assertEqual(self.classify('humor_detector',row)['band'],'unsupported')
        self.assertEqual(self.classify('humor_detector',humor(perpetrator='gloria'))['reason'],'conflicting_subject')
    def test_shared_markdown_store_routes_each_known_header_once(self):
        result=V.inventory(dict(voice=VOICE+'\n'+DEV+'\n## unknown private heading\nprivate text'))
        data=result['stores'][V.STORES['voice']]
        self.assertEqual(data['records'],3)
        self.assertEqual({r['judge'] for r in data['shapes']},{'voice_coherence','deviation_check','unattributed'})
        self.assertNotIn('private',json.dumps(data))
    def test_shapes_group_by_fields_and_types_not_values(self):
        a=humor();b=humor();b['signal']=.6;b['stated']='OTHER_PRIVATE_TEXT'
        c=humor(material_kind='self_play');d=humor();d['signal']='.8'
        out=V.inventory(dict(humor=json.dumps(dict(moments=[a,b,c,d]))))['stores'][V.STORES['humor']]
        self.assertEqual((out['records'],out['distinct_shapes']),(4,3))
        self.assertEqual(sorted(r['records'] for r in out['shapes']),[1,1,2])
    def test_unknown_keys_are_redacted_without_collapsing_distinct_shapes(self):
        a=humor();a['SYNTHETIC_PRIVATE_ID']={'SYNTHETIC_PRIVATE_TOKEN':'SECRET'}
        b=humor();b['ANOTHER_PRIVATE_ID']={'SYNTHETIC_PRIVATE_TOKEN':'SECRET'}
        out=V.inventory(dict(humor=json.dumps(dict(moments=[a,b]))));text=json.dumps(out)
        self.assertEqual(out['stores'][V.STORES['humor']]['distinct_shapes'],2)
        for secret in ('SYNTHETIC_PRIVATE','ANOTHER_PRIVATE','SECRET'):self.assertNotIn(secret,text)
        self.assertIn('redacted_field_names',text)
    def test_no_values_hashes_dates_or_prose_escape_nested_binding(self):
        row=humor(reply_binding=BINDING);before=copy.deepcopy(row)
        out=V.inventory(dict(humor=json.dumps(dict(moments=[row]))));text=json.dumps(out)
        for secret in ('SYNTHETIC_PRIVATE','2020-','a'*64,'b'*64,'synthetic-turn','judge-reply-binding-v1'):self.assertNotIn(secret,text)
        self.assertEqual(row,before)
        self.assertEqual(out['stores'][V.STORES['humor']]['shapes'][0]['exact_native_bindings'],1)
    def test_missing_inputs_are_not_empty_stores_and_empty_is_zero(self):
        out=V.inventory(dict(presence='[]'))
        self.assertEqual(out['stores'][V.STORES['presence']]['records'],0)
        self.assertEqual(out['stores'][V.STORES['humor']],dict(status='not_supplied'))
    def test_bad_json_duplicates_nonfinite_and_bounds_refuse(self):
        for raw in ('{"moments":[],"moments":[]}','{"moments":[{"signal":NaN}]}','{"moments":{}}'):
            with self.assertRaises(ValueError):V.inventory(dict(humor=raw))
        with self.assertRaises(ValueError):V.inventory(dict(presence=json.dumps([{}]*(V.MAX_RECORDS+1))))
        with self.assertRaises(ValueError):V.inventory(dict(presence_history='{}\ninvalid-private-text'))
    def test_cli_reads_all_four_snapshots_unchanged(self):
        values={'voice':VOICE+DEV,'presence':json.dumps([dict(id='synthetic',composite=.5,flag=False)]),
                'presence-history':json.dumps(dict(id='synthetic',composite=.5))+'\n','humor':json.dumps(dict(moments=[humor()]))}
        args=[];paths=[]
        for name,text in values.items():
            p=self.file(text,name);paths.append((p,p.read_bytes()));args+=['--'+name,p]
        run=self.cli(*args);self.assertEqual(run.returncode,0,run.stderr)
        out=json.loads(run.stdout);self.assertEqual(sum(s['records'] for s in out['stores'].values()),5)
        for p,b in paths:self.assertEqual(p.read_bytes(),b)
        self.assertEqual(set(p.name for p in self.root.iterdir()),set(values))
        self.assertNotIn('SYNTHETIC_PRIVATE',run.stdout)
    def test_cli_private_file_and_symlink_refusal_is_sanitized(self):
        p=self.file('{"moments":[]}');p.chmod(0o644)
        run=self.cli('--humor',p);self.assertNotEqual(run.returncode,0);self.assertEqual(run.stderr.strip(),'judge_verdict_shapes_refused');self.assertEqual(run.stdout,'')
        p.chmod(0o600);link=self.root/'link';link.symlink_to(p)
        self.assertNotEqual(self.cli('--humor',link).returncode,0)
        nested=self.root/'public';nested.mkdir(mode=0o755);q=nested/'input';q.write_text('[]');q.chmod(0o600)
        self.assertNotEqual(self.cli('--presence',q).returncode,0)
    def test_cli_size_bound_and_malformed_input_emit_no_content(self):
        p=self.file('SYNTHETIC_PRIVATE_TEXT')
        run=self.cli('--humor',p);self.assertEqual(run.stderr.strip(),'judge_verdict_shapes_refused');self.assertEqual(run.stdout,'')
        p.write_text(' '*(V.MAX_BYTES+1));self.assertNotEqual(self.cli('--humor',p).returncode,0)
    def test_binding_parser_rejects_duplicate_naive_and_bad_digest(self):
        for patch_value in (dict(recorded_at='2020-01-01T00:00:00'),dict(content_sha256='bad'),dict(turn_id='bad\nID')):
            row=dict(BINDING,**patch_value);self.assertIsNone(V.native_binding(dict(reply_binding=row)))
        raw=json.dumps(BINDING).replace('"schema":','"schema":"duplicate", "schema":')
        self.assertIsNone(V.native_binding('<!-- judge-reply-binding: '+raw+' -->'))


if __name__ == '__main__':unittest.main()

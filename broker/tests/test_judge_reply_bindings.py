#!/usr/bin/env python3
"""Prospective verdict identity contracts using synthetic stores and stubbed senders."""
import ast
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
import re
from pathlib import Path
import socket
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import witness_receipts as W

def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=load('native_agreement_test',ROOT/'experiments/nonllm-judges/agreement.py')
FIX=load('native_agreement_fixture',ROOT/'broker/tests/test_nonllm_private_run.py')


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='judge-bindings-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.mem=self.root/'memory';self.mem.mkdir()
        self.assertNotIn('.vintos',self.root.parts)
        self.sender=Mock(side_effect=AssertionError('external action forbidden'))
        self.http=Mock(side_effect=AssertionError('unexpected provider call'))
        self.seed=Mock();self.ferment=Mock()
        modules={'requests':types.SimpleNamespace(post=self.http,get=self.sender),
                 'emoclaw_utils':types.SimpleNamespace(seed_thread=self.seed),
                 'subconscious_context':types.SimpleNamespace(get_subconscious_context_compact=lambda:''),
                 'truth_lock':types.SimpleNamespace(get_lock_context=lambda:'',get_bis_reduction=lambda:1),
                 'subcon_target':types.SimpleNamespace(generative_route=lambda u,m:(u,m)),
                 'want_stance':types.SimpleNamespace(factor=lambda x:1),
                 'policy_decisions':types.SimpleNamespace(EXEMPT_REQUESTED_WORK=False,is_requested_work=lambda x:False)}
        for p in (patch.dict(os.environ,HOME=str(self.root),SPARK_WORKSPACE=str(self.root)),
                  patch.object(socket.socket,'connect',self.sender),patch.dict(sys.modules,modules)):
            p.start();self.addCleanup(p.stop)
        self.assertIs(socket.socket.connect,self.sender);self.addCleanup(self.sender.assert_not_called)
        self.voice=load('bound_voice',ROOT/'bin/voice_coherence.py');self.voice.COHERENCE_LOG=str(self.mem/'voice.md');self.voice.get_context=lambda:''
        self.dev=load('bound_deviation',ROOT/'bin/deviation_check.py');self.dev.VC_FILE=str(self.mem/'deviation.md')
        self.humor=load('bound_humor',ROOT/'bin/humor_detector.py');self.humor.MOMENTS_FILE=str(self.mem/'humor.json');self.humor._ferment=self.ferment
        self.humor._sg_write=lambda *a:False
        self.presence=load('bound_presence',ROOT/'scripts/presence_audit.py')
        for field,name in [('CHAT','chat.json'),('OUT','presence.json'),('JEPA','prediction.json'),('FORECAST','forecast.json')]:setattr(self.presence,field,str(self.mem/name))
        self.text='synthetic whole reply '+('word '*230)
    def binding(self,limit=500,text=None):
        text=self.text if text is None else text
        return W.judge_reply_binding('synthetic-turn',text,text[:limit])
    def test_helper_exact_whole_and_judged_hashes_without_text(self):
        b=self.binding();self.assertEqual(b['content_sha256'],W.digest(self.text));self.assertEqual(b['judged_sha256'],W.digest(self.text[:500]))
        self.assertNotEqual(b['content_sha256'],b['judged_sha256']);self.assertNotIn(self.text,json.dumps(b))
        for tid in ('',None,'bad\nID','<!--bad-->','x'*161):self.assertEqual(W.judge_reply_binding(tid,self.text,self.text[:500]),{})
        self.assertEqual(W.judge_reply_record(b,self.text[:499],datetime.now(timezone.utc).isoformat()),{})
        self.assertEqual(W.judge_reply_record(b,self.text[:500],'2020-01-01'),{})
        b['content_sha256']='bad';self.assertEqual(W.judge_reply_record(b,self.text[:500],datetime.now(timezone.utc).isoformat()),{})
    def test_voice_writer_binding_and_rubric_are_unchanged(self):
        response=Mock();response.json.return_value={'choices':[{'message':{'content':'SCORE: 2\nNOTE: synthetic note'}}]}
        self.http.side_effect=None;self.http.return_value=response
        self.voice.check(self.text[:500],reply_binding=self.binding())
        content=Path(self.voice.COHERENCE_LOG).read_text();b=A.native_binding(content)
        self.assertEqual(b['content_sha256'],W.digest(self.text));self.assertEqual(A.band('voice_coherence',content,''),'flag')
        self.assertEqual(self.http.call_count,1);self.assertEqual(self.seed.call_count,1)
        prompt=self.http.call_args.kwargs['json']['messages'][-1]['content']
        self.assertNotIn('synthetic-turn',prompt);self.assertNotIn(W.digest(self.text),prompt)
        self.assertIn(self.text[:500],prompt)
    def test_voice_malformed_metadata_does_not_drop_verdict(self):
        response=Mock();response.json.return_value={'choices':[{'message':{'content':'SCORE: 2\nNOTE: synthetic note'}}]}
        self.http.side_effect=None;self.http.return_value=response
        self.voice.check(self.text,reply_binding={'bad':'metadata'})
        content=Path(self.voice.COHERENCE_LOG).read_text();self.assertIsNone(A.native_binding(content));self.assertIn('Score 2',content)
    def test_deviation_selected_records_and_retention_keep_binding(self):
        for i in range(7):
            self.dev.append_voice_coherence('synthetic voice','deviation',.4,.1,reply_binding=self.binding(400),judged_reply=self.text)
        content=Path(self.dev.VC_FILE).read_text();self.assertEqual(content.count('judge-reply-binding:'),5)
        for part in content.split('## ')[1:]:
            record='## '+part;self.assertEqual(A.native_binding(record)['content_sha256'],W.digest(self.text))
            self.assertEqual(A.band('deviation_check',record,''),'flag')
        tree=ast.parse((ROOT/'bin/deviation_check.py').read_text())
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='append_voice_coherence']
        self.assertEqual(len(calls),3);self.assertTrue(all({'reply_binding','judged_reply'} <= {k.arg for k in n.keywords} for n in calls))
    def test_humor_routes_binding_only_to_his_selected_positive_record(self):
        self.humor.llm=Mock(return_value=json.dumps(dict(signal=.8,stated='synthetic bit',type='wordplay',reply_binding={'forged':True})))
        self.humor.scan_gloria_message=Mock(return_value=dict(source='gloria',signal=.8,original='synthetic her bit',type='wordplay'))
        result=self.humor.scan_turn('synthetic her',self.text,reply_binding=self.binding(600))
        data=json.loads(Path(self.humor.MOMENTS_FILE).read_text())['moments']
        self.assertEqual(len(data),2);self.assertNotIn('reply_binding',data[0]);self.assertEqual(data[1]['reply_binding']['content_sha256'],W.digest(self.text))
        self.assertEqual(self.humor.llm.call_count,1);self.assertEqual(self.ferment.call_count,2)
        self.assertNotIn('synthetic-turn',self.humor.llm.call_args.args[0]);self.assertEqual(len(result),2)
    def test_humor_missing_or_bad_binding_preserves_positive_without_forgery(self):
        self.humor.llm=Mock(return_value=json.dumps(dict(signal=.8,stated='synthetic bit',reply_binding={'forged':True})))
        for b in (None,{'bad':1},self.binding(500)):
            data=self.humor.scan_vintos_message(self.text,reply_binding=b)
            self.assertEqual(data['signal'],.8);self.assertNotIn('reply_binding',data)
    def test_presence_current_and_history_preserve_exact_binding_and_flags(self):
        at=datetime.now(timezone.utc).isoformat()
        rows=[dict(role='user',content='synthetic ask',timestamp=at),dict(role='assistant',content=self.text,timestamp=at,turn_id='synthetic-turn')]
        Path(self.presence.CHAT).write_text(json.dumps(rows))
        self.presence.score=Mock(return_value=dict(composite=.8,note='synthetic',arrived=.8,moved=.8,left_alive=.8,explained=.1,reply_binding={'forged':True}))
        self.presence.main()
        current=json.loads(Path(self.presence.OUT).read_text())[0]
        archived=json.loads((self.mem/'presence-audit-history.jsonl').read_text().splitlines()[0])
        self.assertEqual(current['reply_binding'],archived['reply_binding']);self.assertFalse(archived['flag'])
        self.assertEqual(archived['reply_binding']['content_sha256'],W.digest(self.text))
        self.assertNotIn(self.text,json.dumps(archived));self.presence.score.assert_called_once()
        self.assertEqual(A.band('presence_audit',archived,'memory/presence-audit-history.jsonl'),'pass')
    def test_presence_legacy_id_is_never_used_as_exact_turn_identity(self):
        at=datetime.now(timezone.utc).isoformat()
        Path(self.presence.CHAT).write_text(json.dumps([dict(role='user',content='synthetic',timestamp=at),dict(role='assistant',content=self.text,timestamp=at)]))
        self.presence.score=Mock(return_value=dict(composite=.8,note='synthetic',reply_binding={'forged':True}))
        self.presence.main();record=json.loads(Path(self.presence.OUT).read_text())[0]
        self.assertNotIn('reply_binding',record);self.assertTrue(record['id'])
    def test_native_four_writer_records_join_without_manual_binding(self):
        bundle,_=FIX.fixture();rows=A.R.adapt(bundle,'2020-02-01T00:00:00Z')[0];row=rows[0]
        full=next(r['content'] for r in bundle['rows'] if r.get('turn_id')==row['id'])
        records=[]
        for judge,limit in [('voice_coherence',500),('deviation_check',400),('presence_audit',900),('humor_detector',600)]:
            b=W.judge_reply_record(W.judge_reply_binding(row['id'],full,full[:limit]),full[:limit],datetime.fromtimestamp(row['at']+1,timezone.utc).isoformat())
            if judge=='voice_coherence':record='## 2020-01-01 00:00 — Score 2\nsynthetic note\nReply excerpt: synthetic\n'
            elif judge=='deviation_check':record='## 2020-01-01 00:00 — Deviation (score: 0.4)\n**Felt:** synthetic\n**Not aligned.** Something resisted.\n'
            elif judge=='presence_audit':record=dict(id='synthetic-audit',composite=.2,flag=True,reply_binding=b)
            else:record=dict(source='vintos',signal=.8,reply_binding=b)
            if isinstance(record,str):record+='<!-- judge-reply-binding: '+json.dumps(b)+' -->\n'
            records.append(dict(judge=judge,store=A.PAIRS[judge][1][0],record=record))
        projection=dict(schema='judge-verdict-projection-v1',cutoff_at='2020-02-01T00:00:00Z',records=records)
        selected,_=A.project_records(projection,rows,A.R.P.stamp(projection['cutoff_at']))
        self.assertTrue(all(row['id'] in selected[j] for j in A.PAIRS))
        changed=copy.deepcopy(projection);changed['records'][2]['record']['reply_binding']['content_sha256']='0'*64
        self.assertFalse(A.project_records(changed,rows,A.R.P.stamp(projection['cutoff_at']))[0]['presence_audit'])
        changed=copy.deepcopy(projection);changed['records'][2]['clock_order']='unknown_order'
        self.assertFalse(A.project_records(changed,rows,A.R.P.stamp(projection['cutoff_at']))[0]['presence_audit'])
    def test_server_avatar_binding_uses_stored_marks_without_changing_judged_text(self):
        tree=ast.parse((ROOT/'bin/server.py').read_text())
        block=next(n for n in ast.walk(tree) if isinstance(n,ast.Try) and n.body and isinstance(n.body[0],ast.ImportFrom)
                   and n.body[0].module=='humor_detector' and any(a.asname=='_hd_scan_turn' for a in n.body[0].names)
                   and any(isinstance(x,ast.Name) and x.id=='_humor_judge_binding' for x in ast.walk(n)))
        scan=Mock();ns=dict(reply=self.text,_turn_marks='synthetic marks',_turn=types.SimpleNamespace(turn_id='synthetic-turn'),_counterpart_text='synthetic her',_prov_envelope={})
        with patch.dict(sys.modules,humor_detector=types.SimpleNamespace(scan_turn=scan)):
            exec(compile(ast.Module(body=[block],type_ignores=[]),'synthetic-block','exec'),ns)
        kw=scan.call_args.kwargs;self.assertEqual(kw['reply_text'],self.text)
        self.assertEqual(kw['reply_binding']['content_sha256'],W.digest(self.text+'synthetic marks'))
        self.assertEqual(kw['reply_binding']['judged_sha256'],W.digest(self.text[:600]))
    def test_metadata_is_removed_before_existing_prompt_feed_truncation(self):
        original='## 2020-01-01 00:00 — Score 2\nsynthetic note\nReply excerpt: synthetic\n'
        bound=W.judge_reply_record(self.binding(),self.text[:500],datetime.now(timezone.utc).isoformat())
        annotated=original+'<!-- judge-reply-binding: '+json.dumps(bound)+' -->\n'
        count=0
        for name in ('bin/server.py','bin/pride-mirror.py','bin/value-map.py','scripts/value-map.py','scripts/value_map.py'):
            # Parse the changed assignments independently of unrelated newer syntax.
            source='\n'.join(line.strip() for line in (ROOT/name).read_text().splitlines()
                             if 'judge-reply-binding:' in line and '.sub(' in line)
            tree=ast.parse(source)
            for n in ast.walk(tree):
                if (isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='sub' and n.args
                        and isinstance(n.args[0],ast.Constant) and 'judge-reply-binding:' in str(n.args[0].value)):
                    self.assertEqual(re.sub(n.args[0].value,'',annotated),original);count+=1
        self.assertEqual(count,6)

    def test_server_background_env_clears_stale_binding_and_keeps_clipped_argument(self):
        src=(ROOT/'bin/server.py').read_text();tree=ast.parse(src)
        fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_bg')
        script=self.root/'voice.py';script.write_text('')
        popen=Mock();ns=dict(skip=set(),test_mode=False,skipped=[],failed=[],launched=[],venv_for_all=False,venv='synthetic',
            writer_env={'VINTOS_JUDGE_REPLY_BINDING':'stale'},surface='avatar',turn_id='synthetic-turn',_judge_turn_id='synthetic-turn',
            reply=self.text,_pt_j=json,_pt_sp=types.SimpleNamespace(Popen=popen),on_writer=None,os=os)
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'synthetic-bg','exec'),ns)
        with patch.object(tempfile,'gettempdir',return_value=str(self.root)):
            ns['_bg']('voice_coherence',['',str(script),'check',self.text[:500]],'synthetic.log')
            b=json.loads(popen.call_args.kwargs['env']['VINTOS_JUDGE_REPLY_BINDING'])
            self.assertEqual(b['content_sha256'],W.digest(self.text));self.assertEqual(popen.call_args.args[0][-1],self.text[:500])
            ns['_judge_turn_id']='';ns['_bg']('voice_coherence',['',str(script),'check',self.text[:500]],'synthetic.log')
            self.assertEqual(json.loads(popen.call_args.kwargs['env']['VINTOS_JUDGE_REPLY_BINDING']),{})
        self.assertLess(src.index('_judge_turn_id = turn_id'),src.index('turn_id = "POST-"'))


if __name__=='__main__':unittest.main()

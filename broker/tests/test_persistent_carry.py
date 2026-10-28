#!/usr/bin/env python3
"""Actual carrying state/consumers, synthetic sources, scratch stores, no sends."""
import ast
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

REPO=Path(__file__).resolve().parents[2]
ROOT=Path(tempfile.mkdtemp(prefix='carrying-tests-'))
os.environ.update(HOME=str(ROOT/'home'),SPARK_WORKSPACE=str(ROOT/'workspace'),CARRY_SHADOW_ROOT=str(ROOT))
def deny(*a,**k):raise AssertionError('no providers, sends or network in carrying tests')
socket.socket.connect=deny
sys.path.insert(0,str(REPO/'scripts'))
import carry_sources as S
import carry_context as C
import persistent_carry as P


class Carrying(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(dir=ROOT));self.mem=self.root/'memory';self.mem.mkdir()
        self.out=self.root/'shadow';self.now=datetime(2026,10,28,23,tzinfo=S.TZ).timestamp()
        self.put('unfinished-threads.json',[{'id':'a','thread':'Finish the copper bird sculpture','timestamp':'2026-10-26','source':'self'}])
        self.put('current-wants.json',[{'id':'w','want':'I want to compose a piano piece','fulfilled':False}])
        self.put('dream-log.json',{'nights':[]})
        self.put('emotion-trajectory-dense.json',[{'t':'2026-10-28T23:00:00-05:00','v':[.2]*11}])
        for name in S.STREAMS:
            p=self.mem/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('')
        self.carriers=[]
        self.assertIs(socket.socket.connect,deny)
        self.assertTrue(self.root.is_relative_to(ROOT))

    def tearDown(self):
        for p in self.carriers:
            if not p.lock.closed:p.close()

    def put(self,name,value):
        path=self.mem/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))

    def carrier(self,shadow=True):
        p=P.Carrier(self.mem,self.out,shadow);self.carriers.append(p);return p

    def block(self,now=None):
        return C.context_block(self.mem,now=self.now if now is None else now,include_shadow=True,packet_path=self.out/'note.json')

    def test_note_is_exact_sourced_records_not_prediction(self):
        self.carrier().tick(self.now);note=self.block()
        self.assertIn('copper bird',note);self.assertIn('my open thread',note);self.assertIn('my recorded want',note)
        self.assertNotIn('she feels',note);self.assertLessEqual(len(note),1100)

    def test_restart_and_midnight_preserve_origin(self):
        a=self.carrier();a.tick(self.now);before=json.loads((self.out/'state.json').read_text())
        a.close();b=self.carrier();b.tick(self.now+86400+3600)
        after=json.loads((self.out/'state.json').read_text())
        self.assertEqual(before['items']['thread:a']['first_seen'],after['items']['thread:a']['first_seen'])
        self.assertEqual(after['restarts'],1);self.assertEqual(len(after['days']),2)
        self.assertIn('carried for 1 day',self.block(self.now+90000))

    def test_no_evidence_amplification_on_quiet_polls(self):
        p=self.carrier();a=p.tick(self.now)
        b=p.tick(self.now+30);self.assertEqual(a['changes'],b['changes']);self.assertEqual(a['processed'],b['processed'])

    def test_resolution_removes_quote_and_latent_item(self):
        p=self.carrier();p.tick(self.now)
        self.put('unfinished-threads.json',[{'id':'a','thread':'Finish the copper bird sculpture','consumed':True}])
        p.tick(self.now+30);self.assertNotIn('copper bird',self.block(self.now+30))
        self.assertNotIn('thread:a',p.state['items'])
        for f in self.out.glob('hour-*.json'):self.assertNotIn('thread:a',json.loads(f.read_text())['items'])

    def test_consumer_rechecks_before_next_poll(self):
        self.carrier().tick(self.now);self.put('unfinished-threads.json',[])
        self.assertNotIn('copper bird',self.block())

    def test_edit_replaces_meaning_and_dates_revision(self):
        p=self.carrier();p.tick(self.now)
        self.put('unfinished-threads.json',[{'id':'a','thread':'Build a blue ceramic bowl'}])
        p.tick(self.now+60);note=self.block(self.now+60)
        self.assertIn('blue ceramic bowl',note);self.assertNotIn('copper bird',note);self.assertIn('revised',note)

    def test_corrupt_source_does_not_resolve_record(self):
        p=self.carrier();p.tick(self.now);(self.mem/'unfinished-threads.json').write_text('{')
        h=p.tick(self.now+60);self.assertIn('unfinished-threads.json',h['unavailable_sources'])
        self.assertIn('thread:a',p.state['items']);self.assertNotIn('copper bird',self.block(self.now+60))
        self.assertIn('absence is not resolution',self.block(self.now+60))

    def test_fulfilled_want_disappears(self):
        p=self.carrier();p.tick(self.now);self.put('current-wants.json',[{'id':'w','want':'I want to compose a piano piece','fulfilled':True}])
        p.tick(self.now+30);self.assertNotIn('piano piece',self.block(self.now+30))

    def test_dream_stays_imagined(self):
        self.put('unfinished-threads.json',[]);self.put('current-wants.json',[])
        self.put('dream-log.json',{'nights':[{'night_of':'2026-10-28','meta_dream':'A silver train crossed a paper sea'}]})
        self.carrier().tick(self.now);note=self.block()
        self.assertIn('imagined, not an event',note);self.assertIn('silver train',note)

    def test_dream_thread_and_tactical_rows_are_not_real_pending(self):
        self.put('unfinished-threads.json',[{'id':'x','thread':'Imagined impossible scene','dream_only':True},
                 {'id':'y','thread':'A tactical line','generation_provenance':{'may_witness':False}}])
        p=self.carrier();p.tick(self.now)
        self.assertNotIn('thread:x',p.state['items']);self.assertNotIn('thread:y',p.state['items'])

    def test_first_light_and_own_note_are_not_ingested(self):
        (self.mem/'daily-inner-life-2026-10-28.md').write_text('# Day\n## First Light — today\nOld carrier echoes itself forever.\n## 12:00 Workshop\nI worked on the small sculpture and left its base unfinished.')
        p=self.carrier();p.tick(self.now)
        self.assertEqual(sum(i['kind']=='journal' for i in p.state['items'].values()),1)
        self.assertNotIn('echoes itself',self.block())

    def test_shadow_not_visible_to_regular_context(self):
        self.carrier().tick(self.now)
        self.assertEqual(C.context_block(self.mem,packet_path=self.out/'note.json'), '')

    def test_hourly_checkpoint_and_private_permissions(self):
        p=self.carrier();p.tick(self.now);p.tick(self.now+3600)
        self.assertEqual(len(list(self.out.glob('hour-*.json'))),2)
        self.assertEqual((self.out/'state.json').stat().st_mode&0o777,0o600)
        self.assertNotIn('copper bird',(self.out/'state.json').read_text())

    def test_one_writer_only(self):
        self.carrier()
        with self.assertRaises(BlockingIOError):P.Carrier(self.mem,self.out,True)

    def test_forget_rebuild_no_backup_text(self):
        p=self.carrier();p.tick(self.now)
        (self.mem/'chat.json.before-forget-fixture').write_text('Must never be read as input')
        self.put('unfinished-threads.json',[]);p.tick(self.now+60)
        self.assertNotIn('thread:a',p.state['items']);self.assertNotIn('Must never',(self.out/'note.json').read_text())

    def test_stream_partial_line_and_duplicate_rotation(self):
        f=self.mem/'chemistry-lab/notebook.jsonl';row=json.dumps({'at':'now','kind':'inquiry'})+'\n'
        f.write_text(row+'{"kind":');p=self.carrier();a=p.tick(self.now)
        self.assertEqual(a['processed']['lab'],1)
        f.write_text(row+'{"kind":"reflection"}\n');b=p.tick(self.now+30)
        self.assertEqual(b['processed']['lab'],2)
        old=f.with_suffix('.old');f.rename(old);f.write_text(row+'{"kind":"reflection"}\n')
        c=p.tick(self.now+60);self.assertEqual(c['processed']['lab'],2)

    def test_source_files_are_never_written(self):
        before={str(p):p.read_bytes() for p in self.mem.rglob('*') if p.is_file()}
        self.carrier().tick(self.now)
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.mem.rglob('*') if p.is_file()})

    def test_stale_note_is_explicit(self):
        self.carrier().tick(self.now);self.assertIn('not refreshed recently',self.block(self.now+1000))

    def test_shadow_rejects_live_output(self):
        with self.assertRaises(ValueError):P.Carrier(self.mem,self.mem/'persistent-carry',True)

    def test_no_arbitrary_reference_reads(self):
        with self.assertRaises(ValueError):S.records(self.mem,'../secrets.json')
        with self.assertRaises(ValueError):S.path_in(self.mem,'../secrets.json')

    def test_corrupt_checkpoint_rebuild_is_honest(self):
        p=self.carrier();p.tick(self.now);p.close();(self.out/'state.json').write_text('{')
        q=self.carrier();h=q.tick(self.now+60)
        self.assertTrue(h['checkpoint_rebuilt']);self.assertIn('rebuilt',self.block(self.now+60))

    def test_state_is_bounded_and_decays_without_fabricated_events(self):
        p=self.carrier();p.tick(self.now);a=np.array(p.state['channels']['thread'])
        p.tick(self.now+86400);b=np.array(p.state['channels']['thread'])
        self.assertTrue(np.isfinite(b).all());self.assertLess(np.linalg.norm(b),np.linalg.norm(a));self.assertLessEqual(abs(b).max(),1)

    def test_actual_full_and_compact_context_include_carrying(self):
        p=self.carrier(False);p.tick(self.now)
        # Normal installed consumer reads memory/persistent-carry. Move only
        # this test fixture after closing its writer, never a live store.
        p.close();self.out.rename(self.mem/'persistent-carry')
        spec=importlib.util.spec_from_file_location('carry_subcon',REPO/'bin/subconscious_context.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.dict(os.environ,SPARK_WORKSPACE=str(self.root)):
            self.assertIn('copper bird',module.get_subconscious_context(include=['carrying']))
            self.assertIn('copper bird',module.get_subconscious_context_compact(include=['carrying']))
            self.assertEqual(module.get_subconscious_context_compact(include=[]),'')

    def test_actual_first_light_prompt_sees_note_no_provider(self):
        text=(REPO/'bin/first-light.sh').read_text();body=text.split("<< 'PYEOF'",1)[1].split('\nPYEOF',1)[0]
        seen=[]
        class Response:
            def json(self):return {'choices':[{'message':{'content':'Synthetic morning fixture'}}]}
        def post(url,**kw):seen.append(kw['json']);return Response()
        requests=SimpleNamespace(post=post)
        sub=SimpleNamespace(get_subconscious_context_compact=lambda:'WHAT I\'M CARRYING: my open copper bird thread')
        with patch.dict(sys.modules,{'requests':requests,'subconscious_context':sub,'emoclaw_pressure':SimpleNamespace(get_pressure_compact=lambda **k:'')}):
            exec(compile(body,'first-light-fixture','exec'),{})
        self.assertEqual(len(seen),1)
        self.assertIn('copper bird',seen[0]['messages'][0]['content'])
        self.assertIn("WHAT I'M CARRYING",seen[0]['messages'][1]['content'])

    def test_first_morning_can_name_real_midnight_carry(self):
        p=self.carrier();p.tick(self.now);p.tick(self.now+7*3600)
        self.assertIn('carried across midnight',self.block(self.now+7*3600))

    def test_retiring_thread_does_not_reset_conversation_state(self):
        f=self.mem/'chat-canonical.jsonl';f.write_text(json.dumps({'role':'user','content':'An ordinary message about the painting'})+'\n')
        p=self.carrier();p.tick(self.now);before=np.array(p.state['channels']['conversation'])
        self.put('unfinished-threads.json',[]);p.tick(self.now+30)
        expected=before*np.exp(-30/P.TAUS[:,None])
        np.testing.assert_allclose(p.state['channels']['conversation'],expected)

    def test_deployment_manifest_and_unit_restrictions(self):
        deploy=(REPO/'scripts/deploy-atelier.sh').read_text()
        for name in ('persistent_carry.py','carry_context.py','carry_sources.py','CARRY_UNIT_NAME.service'):
            self.assertIn(name,deploy)
        unit=(REPO/'broker/vintos-persistent-carry.service').read_text()
        for item in ('Nice=15','UMask=0077','ProtectHome=read-only','ReadWritePaths=','Restart=on-failure'):
            self.assertIn(item,unit)

    def test_deploy_rollback_preserves_previous_activation(self):
        deploy=(REPO/'scripts/deploy-atelier.sh').read_text()
        block=deploy.split('# Persistent carrying: preserve prior activation',1)[1].split('# Record the service/process state',1)[0]
        # Restore the comment's first suffix so this is an executable shell slice.
        block='# Persistent carrying: preserve prior activation'+block
        for active in (False,True):
            work=self.root/str(active);work.mkdir();backup=work/'backup';backup.mkdir()
            unit=work/'vintos-persistent-carry.service';unit.write_text('old unit')
            fake=work/'systemctl';log=work/'calls'
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CTL_LOG"\ncase "$*" in *is-enabled*) echo "$OLD_ENABLED";; *is-active*) echo "$OLD_ACTIVE";; esac\n');fake.chmod(0o755)
            restore=backup/'restore.sh';restore.write_text('#!/bin/bash\nset -e\n')
            env=dict(os.environ,PATH=str(work)+os.pathsep+os.defpath,CTL_LOG=str(log),OLD_ENABLED='enabled' if active else 'disabled',OLD_ACTIVE='active' if active else 'inactive')
            pre='CARRY_UNIT_NAME=vintos-persistent-carry\nCARRY_UNIT_DST='+str(unit)+'\nBACKUP='+str(backup)+'\ndie(){ exit 99; };\n'
            result=subprocess.run(['bash','-c',pre+block+'\ntrue\n'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            unit.write_text('new unit');log.write_text('')
            result=subprocess.run(['bash',str(restore)],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(unit.read_text(),'old unit')
            self.assertEqual('start vintos-persistent-carry.service' in log.read_text(),active)

    def test_reviewed_handoff_preserves_the_carried_state(self):
        p=self.carrier();p.tick(self.now);p.close()
        live=self.mem/'persistent-carry'
        with patch.object(P.time,'time',return_value=self.now+60):
            q=P.Carrier(self.mem,live,False,self.out/'state.json')
        self.carriers.append(q)
        q.tick(self.now+60)
        self.assertEqual(q.state['items']['thread:a']['first_seen'],self.now)
        self.assertIsNotNone(q.state.get('adopted_from_shadow_at'))
        self.assertIn('copper bird',C.context_block(self.mem,now=self.now+60))
        self.assertFalse(json.loads((live/'note.json').read_text())['shadow'])

    def test_handoff_never_overwrites_existing_live_checkpoint(self):
        p=self.carrier(False);p.tick(self.now);p.close()
        q=P.Carrier(self.mem,self.out,False,self.root/'does-not-exist');self.carriers.append(q)
        q.tick(self.now+60)
        self.assertEqual(q.state['items']['thread:a']['first_seen'],self.now)

    def test_pending_memory_capacity_is_explicit_and_bounded(self):
        self.put('current-wants.json',[{'id':str(i),'want':'Make small study number '+str(i)} for i in range(600)])
        p=self.carrier();h=p.tick(self.now)
        self.assertEqual(len(p.state['items']),512);self.assertGreater(h['omitted_records'],0)


if __name__=='__main__':unittest.main()

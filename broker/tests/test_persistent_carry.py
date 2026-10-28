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
        p=P.Carrier(self.mem,self.out,shadow);self.carriers.append(p)
        (self.out/'config.json').write_text(json.dumps({'enabled':True}))
        return p

    def block(self,now=None):
        return C.context_block(self.mem,now=self.now if now is None else now,include_shadow=True,packet_path=self.out/'note.json')

    def test_note_is_exact_sourced_records_not_prediction(self):
        self.carrier().tick(self.now);note=self.block()
        self.assertIn('copper bird',note);self.assertIn('my open thread',note);self.assertIn('my recorded want',note)
        self.assertNotIn('she feels',note);self.assertLessEqual(len(note),1100)

    def test_restart_preserves_origin_and_clamps_long_gap(self):
        a=self.carrier();a.tick(self.now);before=json.loads((self.out/'state.json').read_text())
        a.close();b=self.carrier();b.tick(self.now+86400+3600)
        after=json.loads((self.out/'state.json').read_text())
        self.assertEqual(before['items']['thread:a']['first_seen'],after['items']['thread:a']['first_seen'])
        self.assertEqual(after['restarts'],1)
        self.assertNotIn('carried for 1 day',self.block(self.now+90000))
        self.assertLessEqual(b.elapsed,300)

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
        (self.mem/'daily-inner-life-2026-10-28.md').write_text('# Day\n## First Light — today\nOld carrier echoes itself forever.\n## 12:00 — Idle thoughts\nI worked on the small sculpture and left its base unfinished.')
        p=self.carrier();p.tick(self.now)
        self.assertEqual(sum(i['kind']=='journal' for i in p.state['items'].values()),1)
        self.assertNotIn('echoes itself',self.block())

    def test_shadow_not_visible_to_regular_context(self):
        self.carrier().tick(self.now)
        self.assertEqual(C.context_block(self.mem,packet_path=self.out/'note.json'), '')

    def test_hourly_checkpoint_and_private_permissions(self):
        p=self.carrier();p.tick(self.now);p.tick(self.now+3600)
        self.assertEqual(len(list(self.out.glob('hour-*.json'))),1)
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
        p.tick(self.now+30);b=np.array(p.state['channels']['thread'])*np.exp(-30/P.TAUS[:,None])
        self.assertTrue(np.isfinite(b).all());self.assertLess(np.linalg.norm(b),np.linalg.norm(a));self.assertLessEqual(abs(b).max(),1)

    def test_actual_full_and_compact_context_include_carrying(self):
        p=self.carrier(False);p.tick(self.now)
        # Normal installed consumer reads memory/persistent-carry. Move only
        # this test fixture after closing its writer, never a live store.
        p.close();self.out.rename(self.mem/'persistent-carry')
        spec=importlib.util.spec_from_file_location('carry_subcon',REPO/'bin/subconscious_context.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.dict(os.environ,SPARK_WORKSPACE=str(self.root)),patch.object(C.time,'time',return_value=self.now):
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
        self.now=datetime(2026,10,28,23,59,tzinfo=S.TZ).timestamp()
        p=self.carrier();p.tick(self.now);p.tick(self.now+120)
        self.assertIn('carried across midnight',self.block(self.now+120))

    def test_retiring_thread_does_not_reset_conversation_state(self):
        f=self.mem/'chat-canonical.jsonl';f.write_text(json.dumps({'role':'user','content':'An ordinary message about the painting'})+'\n')
        p=self.carrier();p.tick(self.now);before=np.array(p.state['channels']['her_conversation'])
        self.put('unfinished-threads.json',[]);p.tick(self.now+30)
        expected=before*np.exp(-30/P.TAUS[:,None])
        np.testing.assert_allclose(p.state['channels']['her_conversation'],expected)

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

    def test_reviewed_handoff_resets_shadow_carry_duration(self):
        p=self.carrier();p.tick(self.now);p.close()
        live=self.mem/'persistent-carry'
        with patch.object(P.time,'time',return_value=self.now+60):
            q=P.Carrier(self.mem,live,False,self.out/'state.json')
        self.carriers.append(q)
        q.tick(self.now+60)
        self.assertEqual(q.state['items']['thread:a']['first_seen'],self.now+60)
        self.assertEqual(q.elapsed,0)
        (live/'config.json').write_text(json.dumps({'enabled':True}))
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

    def test_exact_journal_authorship_allowlist(self):
        allowed=['Journal','Wonder','Vintos Speaks','Last Word','14:25 — Idle thoughts']
        denied=['Mirror','Mirror Sessions','The Mirror Responds','Ghost Branch',"I read Muse's letter",'Email','Web Search','MoltBook','Journal — letter','First Light','Workshop']
        f=self.mem/'daily-inner-life-2026-10-28.md'
        f.write_text(''.join('## '+h+'\nA sentence from section number '+str(i)+'.\n' for i,h in enumerate(allowed+denied)))
        rows=S.sections(self.mem,f.name)
        self.assertEqual(len(rows),len(allowed))
        self.assertTrue(all('section number '+str(i)+'.' in '\n'.join(r['text'] for r in rows.values()) for i in range(5)))
        with self.assertRaises(ValueError):S.sections(self.mem,'daily-creative-2026-10-28.md')
        before=set(rows)
        f.write_text('## Mirror\nOther voice.\n'+f.read_text())
        self.assertEqual(before,set(S.sections(self.mem,f.name)))

    def test_off_switch_is_immediate_and_missing_is_off(self):
        p=self.carrier();p.tick(self.now);self.assertTrue(self.block())
        (self.out/'config.json').write_text('{"enabled": false}')
        self.assertEqual(self.block(),'')
        (self.out/'config.json').write_text('{"enabled": true}')
        self.assertTrue(self.block())
        (self.out/'config.json').unlink();self.assertEqual(self.block(),'')

    def test_notes_expire_after_three_hours_and_future_is_rejected(self):
        self.carrier().tick(self.now)
        self.assertEqual(self.block(self.now+C.MAX_NOTE_AGE+1),'')
        self.assertEqual(self.block(self.now-61),'')

    def test_clean_sentence_fragments_and_deduplication(self):
        text='**A small [copper bird](https://invalid.example) is unfinished.** '+('Another word '*40)
        self.assertEqual(S.fragment(text),'A small copper bird is unfinished.')
        self.assertEqual(S.fragment('Unfinished '+('long '*70)),'')
        self.assertNotIn('Already done',S.plain('- [x] Already done.\n- [ ] Still open.'))
        self.put('unfinished-threads.json',[{'id':'a','thread':text},{'id':'b','thread':'A small copper bird is unfinished.'},{'id':'done','thread':'A finished work.','status':'completed'}])
        self.put('current-wants.json',[])
        p=self.carrier();p.tick(self.now)
        self.assertEqual(len(p.state['selected']),1)
        note=self.block();self.assertEqual(note.count('small copper bird'),1)
        self.assertNotIn('**',note);self.assertNotIn('https://',note);self.assertNotIn('finished work',note)

    def test_loop_guard_in_allowed_journal_pending_and_chat(self):
        marker="WHAT I'M CARRYING: [persistent-carry:v2] source echo."
        (self.mem/'daily-inner-life-2026-10-28.md').write_text('## Journal\n'+marker)
        self.put('unfinished-threads.json',[{'id':'echo','thread':marker}])
        (self.mem/'chat-canonical.jsonl').write_text(json.dumps({'role':'assistant','content':marker})+'\n')
        p=self.carrier();p.tick(self.now)
        self.assertNotIn('thread:echo',p.state['items'])
        self.assertFalse(any(v['kind']=='journal' for v in p.state['items'].values()))
        self.assertNotIn('conversation',p.state['channels'])

    def test_quiet_polls_do_not_rewrite_state(self):
        p=self.carrier();p.tick(self.now);f=self.out/'state.json'
        before=(f.read_bytes(),f.stat().st_ino,f.stat().st_mtime_ns)
        h=p.tick(self.now+30)
        self.assertFalse(h['state_written'])
        self.assertEqual(before,(f.read_bytes(),f.stat().st_ino,f.stat().st_mtime_ns))
        self.assertEqual(h['ticks'],2)
        self.assertEqual(json.loads((self.out/'note.json').read_text())['last_tick'],self.now+30)

    def test_clock_jumps_do_not_invent_carry_days_or_retire_journal(self):
        (self.mem/'daily-inner-life-2026-10-28.md').write_text('## Journal\nA quiet study remains open on the desk.')
        p=self.carrier();p.tick(self.now)
        p.tick(self.now-3600);h=p.tick(self.now+90*86400)
        self.assertLessEqual(h['elapsed'],300)
        self.assertEqual(h['midnights'],0)
        self.assertTrue(any(v['kind']=='journal' for v in p.state['items'].values()))
        self.assertNotIn('carried for',self.block(self.now+90*86400))
        self.assertIn('clock discontinuity',self.block(self.now+90*86400))

    def test_state_can_select_three_threads_without_a_source_quota(self):
        self.put('unfinished-threads.json',[{'id':str(i),'thread':t} for i,t in enumerate(['Copper sculpture base.','Blue ceramic bowl.','Piano composition ending.'])])
        self.put('current-wants.json',[])
        p=self.carrier();p.tick(self.now)
        self.assertEqual(len(p.state['selected']),3)
        self.assertTrue(all(p.state['items'][k]['kind']=='thread' for k in p.state['selected']))

    def test_conversation_changes_selection_with_identical_pending_records(self):
        texts=['Copper sculpture base.','Blue ceramic bowl.','Piano composition ending.','Gloria her presence together home conversation.']
        self.put('unfinished-threads.json',[{'id':str(i),'thread':t} for i,t in enumerate(texts)])
        self.put('current-wants.json',[])
        p=self.carrier();p.tick(self.now)
        before=list(p.state['selected']);target=next(k for k in p.state['items'] if k not in before)
        message=texts[int(target.split(':')[1])]
        with (self.mem/'chat-canonical.jsonl').open('a') as f:f.write(json.dumps({'role':'user','content':message})+'\n')
        p.tick(self.now+30)
        self.assertEqual(p.state['selected'][0],target)
        self.assertNotEqual(before,p.state['selected'])

    def test_fresh_presence_has_causal_selection_weight_not_a_whereabouts_claim(self):
        texts=['Copper sculpture base.','Blue ceramic bowl.','Piano composition ending.','Gloria her presence together home conversation.']
        self.put('unfinished-threads.json',[{'id':str(i),'thread':t} for i,t in enumerate(texts)])
        self.put('current-wants.json',[])
        p=self.carrier();p.tick(self.now)
        self.put('home-presence.json',{'home':True,'last_seen':self.now+30,'kevin':{'home':False}})
        p.tick(self.now+30)
        self.assertEqual(p.state['selected'][0],'thread:3')
        self.assertEqual(p.state['processed']['presence'],1)
        self.assertNotIn('Kevin',self.block(self.now+30))
        self.assertNotIn('she is home',self.block(self.now+30))

    def test_stale_or_negative_presence_is_not_positive_evidence(self):
        self.put('home-presence.json',{'home':True,'last_seen':self.now-901})
        p=self.carrier();p.tick(self.now);self.assertNotIn('presence',p.state['channels'])
        self.put('home-presence.json',{'home':False,'last_seen':self.now})
        p.tick(self.now+30);self.assertNotIn('presence',p.state['channels'])

    def test_forbidden_origins_cannot_bypass_journal_rule_via_pending(self):
        self.put('unfinished-threads.json',[{'id':str(i),'thread':'A borrowed fragment about a task.','source':source} for i,source in enumerate(['mirror','ghost-branch','letter-promise','email','web-search','moltbook'])])
        p=self.carrier();p.tick(self.now)
        self.assertFalse(any(v['kind']=='thread' for v in p.state['items'].values()))

    def test_midnight_receipt_distinguishes_synthetic_clock(self):
        self.now=datetime(2026,10,28,23,59,tzinfo=S.TZ).timestamp()
        p=self.carrier();p.tick(self.now);p.tick(self.now+120)
        receipt=json.loads((self.out/'midnight-receipts.json').read_text())[-1]
        self.assertFalse(receipt['real_clock']);self.assertTrue(receipt['note_names_midnight'])
        self.assertGreater(receipt['retained_selected'],0)

    def test_real_clock_path_counts_monotonic_time_not_forward_wall_jump(self):
        p=self.carrier()
        with patch.object(P.time,'time',return_value=self.now),patch.object(P.time,'monotonic',return_value=p.mono):p.tick()
        mono=p.mono
        with patch.object(P.time,'time',return_value=self.now+86400*30),patch.object(P.time,'monotonic',return_value=mono+30):h=p.tick()
        self.assertAlmostEqual(h['elapsed'],30,places=2)
        self.assertEqual(h['midnights'],0)


if __name__=='__main__':unittest.main()

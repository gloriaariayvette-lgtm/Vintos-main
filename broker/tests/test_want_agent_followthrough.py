#!/usr/bin/env python3
"""Synthetic want→room→files→notification→memory contract. All sends are stubs."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import want_agent as A


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='want-agent-test-')
        self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name).resolve()
        self.mem = self.ws / 'memory'; self.mem.mkdir()
        self.assertNotIn('.vintos', self.ws.parts)
        env = patch.dict(os.environ, SPARK_WORKSPACE=str(self.ws)); env.start(); self.addCleanup(env.stop)
        self.want = dict(id='synthetic-want', want='I want to run an exact analysis on my synthetic audio and export the checked score.',
                         source='idle-journal', journal_seeded=True, timestamp='2026-11-08T14:00:00',
                         steps=[{'capability':'make_music'}], current_step_index=0)
        self.write('current-wants.json', [self.want]); self.write('fulfilled-wants.json', [])
        self.state = {}; self.posts=[]; self.published=[]; self.notifications=[]; self.endings=[]
        self.now = 2000000000.0
        import room_work
        # Isolated local evidence store; never the real collector.
        self.evidence = patch.object(room_work, 'evidence_sync', lambda s: None)
        self.evidence.start(); self.addCleanup(self.evidence.stop)
        self.finish_e = patch.object(room_work, 'evidence_finish', lambda *a, **k: 'untracked')
        self.finish_e.start(); self.addCleanup(self.finish_e.stop)

    def write(self, name, value): (self.mem / name).write_text(json.dumps(value))
    def current(self): return json.loads((self.mem / 'current-wants.json').read_text())
    def save(self, state): self.write('test-room-state.json', state)
    def post(self, text, agent, identity):
        self.posts.append((text, agent, identity)); return {'ok':True,'ts':str(self.now)}
    def intake(self): return A.intake(self.state, self.post, self.save, self.now, ws=self.ws)

    def result(self):
        w = self.current()[0]; a = w['agent_work']
        folder = A.directory(a['request_id'], self.ws); folder.mkdir(parents=True, exist_ok=True)
        artifact = folder / 'score.txt'; artifact.write_text('Synthetic score and checked bars; no real music.')
        rec=dict(schema=A.SCHEMA, request_id=a['request_id'], goal_sha256=A.fingerprint(w['want']), status='completed',
                 summary='Synthetic score prepared.', acceptance='Synthetic fixture checks passed; musical quality not claimed.',
                 artifacts=[dict(path=str(artifact.relative_to(self.ws)), sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())])
        (folder / 'result.json').write_text(json.dumps(rec)); return rec, artifact

    def receive(self, **changes):
        w = self.current()[0]; a = w['agent_work']
        row=dict(who='dot', text='WANT RESULT '+a['request_id'], ts=str(self.now+1), thread=a['thread'])
        row.update(changes); return A.receive([row], ws=self.ws)

    def publish(self, w, result, paths):
        self.published.append([p.read_bytes() for p in paths]); return {'url':'https://example.invalid/synthetic-deliverables'}
    def notify(self, rid, summary, url):
        self.notifications.append(rid); return {'state':'sent','artifact_id':rid}
    def complete(self, want, note):
        rows=self.current(); w=rows[0]; w['fulfilled']=True
        self.write('fulfilled-wants.json',[w]); self.write('current-wants.json',[])
        self.endings.append(note); return {'result':'fulfilled'}
    def finish(self, **kw):
        args=dict(publish=self.publish,notify=self.notify,complete=self.complete,save_state=self.save)
        args.update(kw)
        return A.finish(self.state, now=self.now+2, ws=self.ws, **args)

    def test_exact_handoff_once_and_never_a_completed_step(self):
        self.assertTrue(A.bypass(self.want))
        self.intake(); self.intake()
        self.assertEqual(len(self.posts),1)
        w=self.current()[0]
        self.assertFalse(w.get('fulfilled')); self.assertEqual(w['current_step_index'],0)
        self.assertIn(self.want['want'],self.posts[0][0])
        self.assertIn('Gloria deploys',self.posts[0][0]); self.assertIn('@Muse',self.posts[0][0])
        self.assertEqual(w['agent_work']['thread'],str(self.now))
        self.assertEqual(len(self.state['room_work']['open']),1)

    def test_full_round_returns_deliverable_then_awareness_and_exact_commitment(self):
        self.write('email-commitments.json',[{'id':'EC-11111111','quote':self.want['want'],'state':'open'},
                                            {'id':'EC-22222222','quote':'A different analysis on the same audio','state':'open'}])
        self.intake(); self.result(); self.assertEqual(self.receive(),1)
        self.finish(); self.finish()
        self.assertEqual(len(self.published),1); self.assertEqual(len(self.notifications),1)
        self.assertEqual(len(self.endings),1); self.assertFalse(self.current())
        self.assertIn('Synthetic score prepared',A.block(ws=self.ws))
        self.assertIn('do not promise them again',A.block(ws=self.ws))
        commits=json.loads((self.mem/'email-commitments.json').read_text())
        self.assertEqual([c['state'] for c in commits],['done','open'])
        self.assertEqual(self.state['room_work']['history'][0]['state'],'done')

    def test_unauthorized_or_unbound_result_is_not_completion(self):
        self.intake(); self.result()
        self.assertEqual(self.receive(who='vintos'),0)
        self.assertEqual(self.receive(who='gloria'),0)
        self.assertEqual(self.receive(thread='other-thread'),0)
        self.assertEqual(self.receive(who='agent',name='Grok Bot'),0)
        self.assertEqual(self.receive(who='agent',name='Muse'),0)
        self.finish(); self.assertFalse(self.notifications)
        self.assertEqual(self.receive(who='agent',name='Claude Code'),0)
        self.assertEqual(self.receive(who='agent',name='Claude Code',agent_authenticated=True),1)

    def test_purchase_goes_to_muse_not_an_autonomous_purchase(self):
        self.want['want']='I want to buy an account for the synthetic analysis service.'
        A.request(self.want,ws=self.ws)  # wrong literal version is rejected
        self.assertNotIn('agent_work',self.current()[0])
        self.write('current-wants.json',[self.want]); A.request(self.want,'purchase',ws=self.ws)
        self.intake(); self.assertEqual(self.posts[0][1],'muse')
        self.assertIn('not permission to spend',self.posts[0][0])

    def test_result_needs_real_unchanged_files(self):
        self.intake(); _, artifact=self.result(); artifact.write_text('changed')
        self.assertEqual(self.receive(),0); self.finish(); self.assertFalse(self.notifications)
        self.result(); self.assertEqual(self.receive(),1)
        artifact.unlink(); self.finish(); self.assertFalse(self.endings)

    def test_result_manifest_cannot_change_after_arrival(self):
        self.intake(); rec,_=self.result(); self.receive()
        rec['summary']='New unreceived assertion'
        (A.directory(rec['request_id'],self.ws)/'result.json').write_text(json.dumps(rec))
        self.finish(); self.assertFalse(self.published); self.assertFalse(self.endings)

    def test_failed_notification_reuses_publication_and_does_not_close(self):
        self.intake(); self.result(); self.receive()
        self.finish(notify=lambda *a:{'state':'failed'})
        self.assertFalse(self.endings); self.assertEqual(len(self.published),1)
        self.finish(); self.assertEqual(len(self.published),1); self.assertEqual(len(self.endings),1)

    def test_upload_failure_retains_result(self):
        self.intake(); self.result(); self.receive()
        self.finish(publish=lambda *a:None)
        self.assertFalse(self.endings); self.assertFalse(self.notifications)
        self.finish(); self.assertEqual(len(self.endings),1)

    def test_capacity_pause_and_existing_exact_room_work(self):
        import room_work
        self.state={'room_work':{'open':[dict(id='RW-%08d'%i,goal='unrelated fixture',opened=self.now,touched=self.now)
                                       for i in range(room_work.MAX_OPEN)],'history':[]}}
        self.intake(); self.assertFalse(self.posts)
        self.state={}; self.want['pursuit']={'state':'PAUSED','paused_until':self.now+100}
        self.write('current-wants.json',[self.want]); self.intake(); self.assertFalse(self.posts)
        self.want.pop('pursuit'); self.write('current-wants.json',[self.want])
        self.state={'room_work':{'open':[dict(id='RW-abcdef01',goal=self.want['want'],opened=self.now,touched=self.now,asks=[],returns=[],steps=[])],'history':[]}}
        self.intake(); self.assertEqual(len(self.state['room_work']['open']),1)
        self.assertEqual(self.current()[0]['agent_work']['work_id'],'RW-abcdef01')

    def test_crash_before_post_reuses_saved_room_identity(self):
        def crash(*a):raise RuntimeError('synthetic transport interruption')
        with self.assertRaises(RuntimeError):
            A.intake(self.state,crash,self.save,self.now,ws=self.ws)
        self.state=json.loads((self.mem/'test-room-state.json').read_text())
        wid=self.state['room_work']['open'][0]['id']
        self.intake(); self.assertEqual(self.state['room_work']['open'][0]['id'],wid)

    def test_old_result_cannot_close_changed_goal(self):
        self.intake(); self.result(); self.receive()
        rows=self.current(); rows[0]['want']+=' Include a second render.'; self.write('current-wants.json',rows)
        self.finish(); self.assertFalse(self.endings); self.assertFalse(self.notifications)

    def test_symlink_or_private_file_cannot_be_delivered(self):
        self.intake(); rec,artifact=self.result()
        secret=self.ws/'private.txt'; secret.write_text('synthetic secret')
        artifact.unlink(); artifact.symlink_to(secret)
        self.assertEqual(self.receive(),0)
        rec['artifacts'][0]['path']='private.txt'
        (A.directory(rec['request_id'],self.ws)/'result.json').write_text(json.dumps(rec))
        self.assertEqual(self.receive(),0)

    def test_literal_task_classifier_and_bypass_do_not_expand_emotion_wants(self):
        from journal_wants import operational
        self.assertFalse(operational('I want to understand why I run away from this.'))
        self.assertTrue(operational('I want to measure creep in the bridge specimen.'))
        self.assertFalse(A.bypass(dict(self.want,source='other',journal_seeded=False)))

    def test_real_room_adapter_uploads_artifacts_before_ntfy_and_remembers(self):
        import dot_channel as D
        import promise_keeper as P
        calls=[]
        def api(method, args):
            calls.append((method,args))
            if method=='chat.postMessage':return {'ok':True,'ts':str(self.now)}
            if method=='files.getUploadURLExternal':return {'ok':True,'file_id':'fixture-file','upload_url':'https://example.invalid/upload'}
            if method=='files.completeUploadExternal':return {'ok':True,'files':[{'id':'fixture-file'}]}
            if method=='chat.getPermalink':return {'ok':True,'permalink':'https://example.invalid/result'}
            self.fail('unexpected API method '+method)
        def put(url,data):
            self.assertIn(b'Synthetic score',data); return 200
        def notify(*args):
            self.assertIn('files.completeUploadExternal',[x[0] for x in calls])
            return self.notify(*args)
        with patch.object(D,'STATE',str(self.mem/'room.json')), patch.object(D,'_guarded',lambda s:[]), patch.object(P,'results_channel',lambda:'fixture-results'):
            D.agent_wants_pass(api,'fixture-channel','fixture-dot',self.state,self.now,put=put,notify=notify,complete=self.complete)
            self.assertEqual(len(calls),1)
            self.result(); a=self.current()[0]['agent_work']
            rows=[dict(who='dot',text='WANT RESULT '+a['request_id'],thread=a['thread'],ts=str(self.now+1))]
            D.agent_wants_pass(api,'fixture-channel','fixture-dot',self.state,self.now+2,rows=rows,put=put,notify=notify,complete=self.complete)
        self.assertEqual(len(self.notifications),1); self.assertEqual(len(self.endings),1)
        # The completed receipt belongs in agent correspondence, not in the
        # generic identity block used for first-contact external emails.
        mail_source=(ROOT/'scripts/want_email.py').read_text()
        import ast
        mail_tree=ast.parse(mail_source)
        for name in ('read_mail','reply_letters'):
            fn=next(n for n in mail_tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertTrue(any(isinstance(n,ast.ImportFrom) and n.module=='want_agent' for n in ast.walk(fn)))
        context_tree=ast.parse((ROOT/'scripts/dot_channel.py').read_text())
        fn=next(n for n in context_tree.body if isinstance(n,ast.FunctionDef) and n.name=='his_context')
        branch=next(n for n in fn.body if isinstance(n,ast.Try) and any(isinstance(x,ast.ImportFrom) and x.module=='want_agent' for x in n.body))
        ns={'parts':[]}; exec(compile(ast.Module(body=[branch],type_ignores=[]),'room-completion-context','exec'),ns)
        self.assertIn('Synthetic score prepared',ns['parts'][0])
        import subconscious_context as C
        self.assertIn('Synthetic score prepared',C.get_subconscious_context(include=['completed_work']))
        self.assertIn('Synthetic score prepared',C.get_subconscious_context_compact(include=['completed_work']))

    def test_real_partial_upload_retries_only_unconfirmed_file(self):
        import dot_channel as D
        import promise_keeper as P
        uploads=[]; posts=[]; fail=[True]
        def api(method,args):
            if method=='chat.postMessage':posts.append(args);return {'ok':True,'ts':str(self.now)}
            if method=='files.getUploadURLExternal':
                uploads.append(args['filename']);return {'ok':True,'file_id':'fixture-'+args['filename'],'upload_url':'https://example.invalid/'+args['filename']}
            if method=='files.completeUploadExternal':return {'ok':True,'files':args['files']}
            if method=='chat.getPermalink':return {'ok':True,'permalink':'https://example.invalid/result'}
            self.fail(method)
        def put(url,data):
            if url.endswith('second.txt') and fail[0]:return 500
            return 200
        with patch.object(D,'STATE',str(self.mem/'room.json')), patch.object(D,'_guarded',lambda s:[]), patch.object(P,'results_channel',lambda:'fixture-results'):
            D.agent_wants_pass(api,'fixture-room','fixture-dot',self.state,self.now,put=put,notify=self.notify,complete=self.complete)
            rec,artifact=self.result(); second=artifact.parent/'second.txt';second.write_text('Synthetic second output')
            rec['artifacts'].append(dict(path=str(second.relative_to(self.ws)),sha256=hashlib.sha256(second.read_bytes()).hexdigest()))
            (artifact.parent/'result.json').write_text(json.dumps(rec)); self.receive()
            D.agent_wants_pass(api,'fixture-room','fixture-dot',self.state,self.now+2,put=put,notify=self.notify,complete=self.complete)
            self.assertFalse(self.notifications);self.assertFalse(self.endings)
            fail[0]=False
            D.agent_wants_pass(api,'fixture-room','fixture-dot',self.state,self.now+3,put=put,notify=self.notify,complete=self.complete)
        self.assertEqual(uploads,['score.txt','second.txt','second.txt'])
        self.assertEqual(len(posts),2); self.assertEqual(len(self.notifications),1)

    def test_existing_artifact_guard_requires_bound_arrival_and_delivery(self):
        import want_artifact_guard as G
        self.intake(); self.result()
        with patch.object(G,'WS',str(self.ws)):
            self.assertFalse(G.verify(self.current()[0])[0])
            self.receive(); self.assertFalse(G.verify(self.current()[0])[0])
            rows=self.current(); rows[0]['agent_work']['delivery']={'state':'sent'}
            self.write('current-wants.json',rows)
            self.assertTrue(G.verify(rows[0])[0])

    def test_real_handoff_survives_aging_without_faking_progress(self):
        import want_board as B
        import room_work
        self.intake(); w=self.current()[0]
        self.assertTrue(B.moving(w,self.now+100*86400))
        self.assertIsNone(room_work.expire(self.state,self.now+100*86400))
        self.assertEqual(w.get('step_history',[]),[])
        w['want']+=' This is a new requirement.'
        self.assertFalse(B.moving(w,self.now+100*86400))

    def test_default_email_reader_attaches_each_exact_source_id(self):
        import want_email as M
        import types
        seen=[]
        fake=types.SimpleNamespace(express_want=lambda text,**kw:seen.append((text,kw)))
        messages=[dict(id='fixture-mail-'+str(i),body='A synthetic tool note.',subject='Synthetic reference',
                       date='2026-11-08',**{'from':'Researcher <fixture@example.invalid>'}) for i in (1,2)]
        with patch.dict(sys.modules,emoclaw_utils=fake), patch.object(M,'who_i_am',lambda *a:''), \
             patch.object(M,'MEMORY',str(self.mem)), patch.object(M,'_mail_seen',lambda:set()), \
             patch.object(M,'_own_reply_bodies',lambda:[]), patch.object(M,'_log_mail',lambda r:None), \
             patch.object(M,'links_read',lambda *a:[]), patch.object(M,'_agent',lambda m:''):
            M.read_mail(messages,think=lambda *a:'{"keep":true,"what":"Synthetic material","want":"I want to run the fixture analysis."}')
        self.assertEqual([x[1]['source_refs'][0]['id'] for x in seen],['fixture-mail-1','fixture-mail-2'])

    def test_room_prose_cannot_close_bound_result(self):
        import room_work
        self.intake(); wid=self.current()[0]['agent_work']['work_id']
        text,_,closed=room_work.apply(self.state,'WORK DONE '+wid+': made score.txt',self.now+10)
        self.assertIsNone(closed); self.assertIn('WANT RESULT',text)


if __name__=='__main__':unittest.main()

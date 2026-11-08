#!/usr/bin/env python3
"""Synthetic want→room→files→notification→memory contract. All sends are stubs."""
import copy
from contextlib import ExitStack
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
from journal_wants import source_receipt


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
        self.want.update(source_receipt('journal','fixture-journal',self.want['want']))
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

    def writer(self, system, user):
        phase=json.loads(user)['phase']
        raw=json.dumps({'message':'Synthetic score prepared.' if phase=='result' else 'Continue the exact synthetic task.',
                        'accept':phase=='result'})
        return {'text':raw,'observations':[{'text':raw,'status':'valid','requested_model':'fixture-requested',
                    'observed_model':'fixture-observed','identity_evidence':'response_metadata'}]}

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

    def test_unbound_sources_cannot_request_or_intake_even_with_queued_work(self):
        for source in ('dream', 'curiosity', 'vintos-dot', 'unknown', None, []):
            w = dict(self.want, source=source)
            self.write('current-wants.json', [w])
            self.assertIsNone(A.request(w, 'missing capability', ws=self.ws), source)
            w['agent_work'] = dict(request_id='WA-'+'a'*24, goal_sha256=A.fingerprint(w['want']),status='queued')
            self.write('current-wants.json', [w])
            self.intake()
            self.assertEqual(self.posts, [], source)
            self.assertFalse(self.state.get('room_work', {}).get('open'))
        for field in ('source_refs', 'source_event_id'):
            w = copy.deepcopy(self.want);w.pop(field)
            self.write('current-wants.json', [w])
            self.assertIsNone(A.request(w, ws=self.ws), field)
            self.intake();self.assertEqual(self.posts, [])

    def test_source_receipt_must_bind_current_goal_and_persisted_row(self):
        w = dict(self.want, want='I want to buy a different synthetic task.')
        self.assertFalse(A.specific(w))
        forged = copy.deepcopy(self.want);forged['source_refs'][0]['text_sha256']='0'*64
        self.write('current-wants.json', [forged])
        self.assertIsNone(A.request(self.want, ws=self.ws))
        self.assertNotIn('agent_work', self.current()[0])
        self.intake();self.assertEqual(self.posts, [])

    def test_email_bound_goal_can_enter_lane(self):
        w = dict(self.want, source='email', journal_seeded=False, timestamp='2020-01-01T00:00:00')
        w.update(source_receipt('email','fixture-mail', w['want']))
        self.write('current-wants.json', [w]);self.intake()
        self.assertEqual(len(self.posts), 1)

    def test_bound_thread_loses_exemption_if_source_receipt_disappears(self):
        import want_working_thread as working
        self.intake();w=self.current()[0]
        self.assertIsNotNone(working.binding(w,self.state,w['agent_work']['thread']))
        w.pop('source_refs')
        self.assertIsNone(working.binding(w,self.state,w['agent_work']['thread']))

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
        self.want.update(source_receipt('journal','fixture-journal',self.want['want']))
        self.write('current-wants.json',[self.want]); A.request(self.want,'purchase',ws=self.ws)
        self.intake(); self.assertEqual(self.posts[0][1],'muse')
        self.assertIn('not permission to spend',self.posts[0][0])

    def test_result_rejects_old_or_foreign_shelf_artifacts(self):
        self.intake(); rec, artifact = self.result()
        created = self.current()[0]['agent_work']['created_at']
        os.utime(artifact, (created-60, created-60))
        self.assertEqual(self.receive(), 0)
        rec, artifact = self.result()
        other = self.mem / 'art' / 'fresh-unbound.txt'; other.parent.mkdir()
        other.write_text('Synthetic newly-created but unrelated result')
        rec['artifacts'] = [dict(path=str(other.relative_to(self.ws)), sha256=hashlib.sha256(other.read_bytes()).hexdigest())]
        (artifact.parent/'result.json').write_text(json.dumps(rec))
        self.assertEqual(self.receive(), 0)
        self.finish(); self.assertEqual(self.published, [])

    def test_result_cannot_publish_private_working_thread_or_future_timestamp(self):
        self.intake(); rec, artifact = self.result()
        private = artifact.parent/'working-thread.json'
        rec['artifacts'] = [dict(path=str(private.relative_to(self.ws)), sha256=hashlib.sha256(private.read_bytes()).hexdigest())]
        (artifact.parent/'result.json').write_text(json.dumps(rec))
        self.assertEqual(self.receive(), 0)
        _, artifact = self.result()
        os.utime(artifact, (A.time.time()+86400, A.time.time()+86400))
        self.assertEqual(self.receive(), 0)

    def test_fresh_copy_of_recorded_shelf_bytes_is_not_a_new_result(self):
        self.intake(); result,path=self.result()
        (self.mem/'art').mkdir()
        self.write('art/gallery.json',[{'manifest':{'sha256':result['artifacts'][0]['sha256']}}])
        with self.assertRaisesRegex(ValueError,'already recorded'): A.verify(self.current()[0],self.ws)
        self.receive(); self.finish(); self.assertFalse(self.endings)

    def test_earlier_request_outputs_and_revisions_cannot_be_relabelled(self):
        self.intake(); result,path=self.result()
        other=A.directory('WA-'+'f'*24,self.ws); other.mkdir(parents=True)
        (other/'result.json').write_text(json.dumps(result))
        with self.assertRaisesRegex(ValueError,'already recorded'): A.verify(self.current()[0],self.ws)
        (other/'result.json').unlink()
        rows=self.current();rows[0]['agent_work']['result_revisions']=[{'result':result}]
        self.write('current-wants.json',rows)
        with self.assertRaisesRegex(ValueError,'already recorded'): A.verify(rows[0],self.ws)

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
            D.agent_wants_pass(api,'fixture-channel','fixture-dot',self.state,self.now,put=put,notify=notify,complete=self.complete,writer=self.writer,identity=lambda:'Synthetic identity')
            self.assertEqual(len(calls),1)
            self.result(); a=self.current()[0]['agent_work']
            rows=[dict(who='dot',text='WANT RESULT '+a['request_id'],thread=a['thread'],ts=str(self.now+1))]
            D.agent_wants_pass(api,'fixture-channel','fixture-dot',self.state,self.now+2,rows=rows,put=put,notify=notify,complete=self.complete,writer=self.writer,identity=lambda:'Synthetic identity')
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

    def delivery_harness(self, *, http_status=200, stop_at_publication=False, change_source=False):
        import dot_channel as D
        import promise_keeper as P
        import deliver as L
        calls, sends = [], []
        def api(method, args):
            calls.append(method)
            if method == 'chat.postMessage': return {'ok':True, 'ts':str(self.now)}
            if method == 'files.getUploadURLExternal':
                return {'ok':True, 'file_id':'fixture-file', 'upload_url':'https://example.invalid/upload'}
            if method == 'files.completeUploadExternal': return {'ok':True, 'files':args['files']}
            if method == 'chat.getPermalink':
                if stop_at_publication: (self.mem / 'want-work.stop').touch()
                if change_source:
                    rows = self.current(); rows[0].pop('source_refs')
                    self.write('current-wants.json', rows)
                return {'ok':True, 'permalink':'https://example.invalid/result'}
            self.fail('unexpected transport method: ' + method)
        def transport(url, data, headers, timeout):
            self.assertEqual(url, 'https://example.invalid/fixture-notify')
            self.assertIn('files.completeUploadExternal', calls)
            self.assertIn('chat.getPermalink', calls)
            sends.append((data, headers)); return http_status
        stack = ExitStack(); self.addCleanup(stack.close)
        for obj, name, value in (
            (D, 'STATE', str(self.mem/'room.json')), (D, '_guarded', lambda s:[]),
            (P, 'results_channel', lambda:'fixture-results'),
            (L, 'MEMORY', str(self.mem)), (L, 'RECEIPTS', str(self.mem/'delivery-receipts.json')),
            (L, 'CHANNELS', {'ntfy':'https://example.invalid/fixture-notify'}),
            (L, 'POST', transport), (L, 'SLEEP', lambda seconds:None), (L, 'RETRIES', 1)):
            stack.enter_context(patch.object(obj, name, value))
        self.assertIs(L.POST, transport)
        self.assertTrue(Path(L.RECEIPTS).is_relative_to(self.ws))
        def run(**overrides):
            kwargs=dict(put=lambda url,data:200, complete=self.complete,
                        writer=self.writer, identity=lambda:'Synthetic identity')
            kwargs.update(overrides)
            return D.agent_wants_pass(api, 'fixture-channel', 'fixture-dot', self.state, self.now+2, **kwargs)
        run(); self.result(); self.receive()
        return run, calls, sends, L

    def test_default_delivery_sends_once_and_retries_local_ending(self):
        run, calls, sends, L = self.delivery_harness()
        run(complete=lambda *args:None)
        self.assertEqual(len(sends), 1)
        self.assertFalse(self.endings)
        self.assertEqual(self.current()[0]['agent_work']['delivery']['state'], 'sent')
        run()
        self.assertEqual(len(sends), 1)
        self.assertEqual(calls.count('files.getUploadURLExternal'), 1)
        self.assertEqual(len(self.endings), 1)
        self.assertEqual(list(L.load_receipts().values())[0]['state'], 'sent')
        self.assertIn('Synthetic score prepared', A.block(ws=self.ws))

    def test_default_delivery_failure_keeps_result_and_reuses_upload(self):
        run, calls, sends, L = self.delivery_harness(http_status=503)
        run()
        self.assertEqual(len(sends), 1)
        self.assertFalse(self.endings)
        self.assertTrue(self.current()[0]['agent_work']['publication'])
        self.assertEqual(list(L.load_receipts().values())[0]['state'], 'failed')
        with patch.object(L, 'POST', lambda *args: sends.append(args) or 200): run()
        self.assertEqual(len(sends), 2)
        self.assertEqual(calls.count('files.getUploadURLExternal'), 1)
        self.assertEqual(len(self.endings), 1)

    def test_stop_after_upload_prevents_default_notification_and_completion(self):
        run, calls, sends, L = self.delivery_harness(stop_at_publication=True)
        run()
        self.assertEqual(sends, [])
        self.assertFalse(self.endings)
        self.assertTrue(self.current()[0]['agent_work']['publication'])
        (self.mem/'want-work.stop').unlink()
        run()
        self.assertEqual(len(sends), 1)
        self.assertEqual(calls.count('files.getUploadURLExternal'), 1)
        self.assertEqual(len(self.endings), 1)

    def test_default_delivery_rechecks_source_after_publication(self):
        run, calls, sends, L = self.delivery_harness(change_source=True)
        run()
        self.assertEqual(sends, [])
        self.assertFalse(self.endings)
        self.assertEqual(list(L.load_receipts().values())[0]['state'], 'failed')

    def test_default_delivery_requires_accepted_result(self):
        run, calls, sends, L = self.delivery_harness()
        def reject(system, user):
            raw = json.dumps({'message':'The fixture needs another check.', 'accept':False})
            return {'text':raw, 'observations':[]}
        run(writer=reject)
        self.assertEqual(sends, [])
        self.assertFalse(self.endings)
        self.assertNotIn('files.getUploadURLExternal', calls)
        self.assertFalse(L.load_receipts())

    def revise_result(self):
        w = self.current()[0]; root = A.directory(w['agent_work']['request_id'], self.ws)
        record = json.loads((root/'result.json').read_text())
        artifact = root/'revised-score.txt'; artifact.write_text('Synthetic revised score, a different checked artifact.')
        record['artifacts'] = [dict(path=str(artifact.relative_to(self.ws)), sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())]
        record['acceptance'] = 'Revised synthetic acceptance check.'
        (root/'result.json').write_text(json.dumps(record))
        self.receive(ts=str(self.now+5))
        return record

    def test_revision_after_failed_notification_uploads_new_result(self):
        run, calls, sends, L = self.delivery_harness(http_status=503)
        run(); previous = copy.deepcopy(self.current()[0]['agent_work'])
        revised = self.revise_result()
        with patch.object(L, 'POST', lambda *args:sends.append(args) or 200): run()
        self.assertEqual(calls.count('files.getUploadURLExternal'), 2)
        self.assertEqual(len(self.endings), 1)
        done = json.loads((self.mem/'fulfilled-wants.json').read_text())[0]['agent_work']
        self.assertEqual(done['result'], revised)
        self.assertEqual(done['result_revisions'][0]['publication'], previous['publication'])

    def test_revision_after_sent_notification_does_not_reuse_old_receipt(self):
        run, calls, sends, L = self.delivery_harness()
        run(complete=lambda *args:None)
        first = copy.deepcopy(self.current()[0]['agent_work'])
        self.revise_result(); run()
        self.assertEqual(len(sends), 2)
        self.assertEqual(calls.count('files.getUploadURLExternal'), 2)
        self.assertEqual(len(self.endings), 1)
        receipts = L.load_receipts()
        self.assertEqual(len(receipts), 2)
        self.assertTrue(all(r['state'] == 'sent' for r in receipts.values()))
        done = json.loads((self.mem/'fulfilled-wants.json').read_text())[0]['agent_work']
        self.assertEqual(done['result_revisions'][0]['delivery'], first['delivery'])

    def test_revision_retains_partial_upload_and_rejects_stale_progress_write(self):
        self.intake(); self.result(); self.receive()
        prior = self.current()[0]['agent_work']
        progress = {'thread':'fixture-partial', 'files':{'fixture-file':{'ok':True}}}
        def interrupted(w, result, paths):
            A._update(w['id'], prior['request_id'], {'publishing':progress}, self.ws,
                      expected_result=prior['result_sha256'])
            raise RuntimeError('synthetic interrupted upload')
        self.finish(publish=interrupted)
        revised = self.revise_result(); current = self.current()[0]['agent_work']
        self.assertNotIn('publishing', current)
        self.assertEqual(current['result_revisions'][0]['publishing'], progress)
        self.assertFalse(A._update(self.want['id'], prior['request_id'], {'publication':{'url':'stale'}}, self.ws,
                                   expected_result=prior['result_sha256']))
        self.assertNotIn('publication', self.current()[0]['agent_work'])
        self.finish(); self.assertEqual(len(self.endings), 1)

    def test_duplicate_arrival_retains_exact_revision_progress(self):
        self.intake(); self.result(); self.receive()
        self.finish(notify=lambda *args:{'state':'failed'})
        before = self.current()[0]['agent_work']
        self.receive(ts=str(self.now+8))
        after = self.current()[0]['agent_work']
        self.assertEqual(after['publication'], before['publication'])
        self.assertEqual(after['stage_result_sha256'], before['stage_result_sha256'])
        self.assertNotIn('result_revisions', after)
        self.finish(); self.assertEqual(len(self.published), 1)

    def test_unversioned_publication_is_not_relabelled_as_current(self):
        self.intake(); self.result(); self.receive()
        rows = self.current(); a = rows[0]['agent_work']
        a['publication'] = {'url':'https://example.invalid/unknown-version'}
        a.pop('stage_result_sha256', None)
        self.write('current-wants.json', rows)
        self.receive(); self.finish()
        self.assertFalse(self.notifications); self.assertFalse(self.endings)
        current = self.current()[0]['agent_work']
        self.assertNotIn('stage_result_sha256', current)
        self.assertEqual(current['publication'], a['publication'])
        self.revise_result()
        self.assertEqual(self.current()[0]['agent_work']['result'], a['result'])
        self.assertEqual(self.current()[0]['agent_work']['publication'], a['publication'])

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
            D.agent_wants_pass(api,'fixture-room','fixture-dot',self.state,self.now,put=put,notify=self.notify,complete=self.complete,writer=self.writer,identity=lambda:'Synthetic identity')
            rec,artifact=self.result(); second=artifact.parent/'second.txt';second.write_text('Synthetic second output')
            rec['artifacts'].append(dict(path=str(second.relative_to(self.ws)),sha256=hashlib.sha256(second.read_bytes()).hexdigest()))
            (artifact.parent/'result.json').write_text(json.dumps(rec)); self.receive()
            D.agent_wants_pass(api,'fixture-room','fixture-dot',self.state,self.now+2,put=put,notify=self.notify,complete=self.complete,writer=self.writer,identity=lambda:'Synthetic identity')
            self.assertFalse(self.notifications);self.assertFalse(self.endings)
            fail[0]=False
            D.agent_wants_pass(api,'fixture-room','fixture-dot',self.state,self.now+3,put=put,notify=self.notify,complete=self.complete,writer=self.writer,identity=lambda:'Synthetic identity')
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

    def test_working_context_restart_and_complete_history(self):
        import want_working_thread as W
        A.intake(self.state,self.post,self.save,self.now,ws=self.ws,identity=lambda:'Original synthetic identity')
        w=self.current()[0]; work=W.binding(w,self.state)
        for i in range(35):
            W.ingest([dict(who='dot',thread=w['agent_work']['thread'],ts=str(self.now+i+1),text='Synthetic reply '+str(i))],self.current(),self.state,self.ws)
        restored=json.loads((self.mem/'test-room-state.json').read_text())
        system,user=W.prompt(self.current()[0],W.binding(self.current()[0],restored),self.ws,lambda:'Different identity')
        self.assertEqual(system,'Original synthetic identity')
        self.assertIn('Synthetic reply 0',user); self.assertIn('Synthetic reply 34',user)
        self.assertIn(self.want['want'],user)
        W.ingest([dict(who='dot',thread=w['agent_work']['thread'],ts=str(self.now+1),text='Synthetic reply 0')],self.current(),restored,self.ws)
        self.assertEqual(len(W.load(w,work,self.ws)['events']),36)

    def test_binding_ignores_tags_and_requires_stored_identity(self):
        import want_working_thread as W
        self.intake(); w=self.current()[0]
        valid=dict(who='dot',thread=w['agent_work']['thread'],ts='1',text='arbitrary text')
        self.assertEqual(W.bound_rows([valid],self.current(),self.state),[valid])
        for change in ({'thread':'wrong'},{'who':'gloria'},{'who':'agent','name':'Muse'}, {'thread':None}):
            self.assertFalse(W.bound_rows([dict(valid,**change)],self.current(),self.state))
        self.state['room_work']['open'][0]['want_id']='other'
        self.assertFalse(W.bound_rows([valid],self.current(),self.state))

    def test_corrupt_or_changed_context_never_resets(self):
        import want_working_thread as W
        self.intake(); w=self.current()[0]; work=W.binding(w,self.state)
        path=A.directory(w['agent_work']['request_id'],self.ws)/'working-thread.json'
        path.write_text('{broken')
        with self.assertRaises(ValueError): W.load(w,work,self.ws)
        self.assertEqual(path.read_text(),'{broken')

    def test_working_generation_is_cached_and_identity_observed(self):
        import want_working_thread as W
        self.intake(); w=self.current()[0]; work=W.binding(w,self.state); calls=[]
        def writer(s,u): calls.append((s,u)); return self.writer(s,u)
        first=W.generate(w,work,self.ws,'opening','fixture-trigger','Plan it',writer,identity='Synthetic identity')
        second=W.generate(w,work,self.ws,'opening','fixture-trigger','Plan it',writer)
        self.assertEqual(first,second); self.assertEqual(len(calls),1)
        data=W.load(w,work,self.ws); rec=next(iter(data['generations'].values()))
        generation=rec['capture']['witness_receipt']['generation']
        self.assertEqual(generation['attempts'][0]['served_model'],'fixture-observed')
        self.assertEqual(rec['capture']['witness_receipt']['delivery'],'unknown')

    def test_unknown_served_model_is_not_requested_model(self):
        import want_working_thread as W
        self.intake(); w=self.current()[0]; work=W.binding(w,self.state)
        def writer(s,u):
            result=self.writer(s,u); result['observations'][0].update(identity_evidence='unknown',observed_model='claimed')
            return result
        W.generate(w,work,self.ws,'opening','unknown','Plan',writer,identity='Fixture')
        rec=next(iter(W.load(w,work,self.ws)['generations'].values()))
        self.assertIsNone(rec['capture']['witness_receipt']['generation']['attempts'][0]['served_model'])

    def test_failed_generation_keeps_context_and_has_retry_backoff(self):
        import want_working_thread as W
        self.intake(); w=self.current()[0]; work=W.binding(w,self.state); calls=[]
        def fail(s,u): calls.append(1); raise RuntimeError('fixture provider failure')
        for _ in range(2):
            with self.assertRaises(RuntimeError): W.generate(w,work,self.ws,'opening','retry','Plan',fail,identity='Fixture')
        self.assertEqual(len(calls),1)
        data=W.load(w,work,self.ws)
        self.assertEqual(data['identity_context'],'Fixture'); self.assertTrue(data['events'])

    def test_adapter_follows_up_with_same_thread_and_retained_context(self):
        import dot_channel as D
        posts=[]; calls=[]
        def api(method,args):
            self.assertEqual(method,'chat.postMessage'); posts.append(args)
            return {'ok':True,'ts':str(self.now+len(posts))}
        def writer(s,u): calls.append((s,u)); return self.writer(s,u)
        with patch.object(D,'STATE',str(self.mem/'room.json')),patch.object(D,'_guarded',lambda s:[]):
            kw=dict(writer=writer,identity=lambda:'Fixture identity',notify=self.notify,complete=self.complete)
            D.agent_wants_pass(api,'fixture-channel','fixture-dot',self.state,self.now,**kw)
            a=self.current()[0]['agent_work']
            r=dict(who='dot',thread=a['thread'],ts=str(self.now+2),text='Synthetic dependency installed; what next?')
            D.agent_wants_pass(api,'fixture-channel','fixture-dot',self.state,self.now+3,rows=[r],**kw)
            D.agent_wants_pass(api,'fixture-channel','fixture-dot',self.state,self.now+4,rows=[r],**kw)
        self.assertEqual(len(calls),2); self.assertEqual(len(posts),2)
        self.assertEqual(posts[1]['thread_ts'],a['thread'])
        self.assertIn('Synthetic dependency installed',calls[1][1]); self.assertIn(self.want['want'],calls[1][1])

    def test_room_context_limit_notifies_once_without_calls_or_posts(self):
        import dot_channel as D
        import want_working_thread as W
        from want_work_budget import WorkBlocked
        self.intake();w=self.current()[0];work=W.binding(w,self.state)
        W.load(w,work,self.ws,'Synthetic oversized identity. '*3000)
        row=dict(who='dot',thread=w['agent_work']['thread'],ts=str(self.now+1),text='Synthetic next report')
        notices=[]
        def forbidden(*a,**kw):raise AssertionError('provider or room send must not run')
        with patch.object(D,'STATE',str(self.mem/'test-room-state.json')):
            for _ in range(2):
                with self.assertRaises(WorkBlocked):
                    D.agent_wants_pass(forbidden,'fixture-channel','fixture-dot',self.state,self.now+2,
                        rows=[row],writer=forbidden,identity='Fixture',notify=lambda *a:None,complete=lambda *a:None,
                        block_notify=lambda key,msg:notices.append(key) or {'state':'sent'})
        self.assertEqual(len(notices),1)
        self.assertIn('Synthetic next report',str(W.load(w,work,self.ws)['events']))

    def test_dedicated_stop_retains_agent_input_without_room_or_owner_sends(self):
        import dot_channel as D
        import want_working_thread as W
        self.intake();w=self.current()[0];work=W.binding(w,self.state)
        (self.mem/'want-work.stop').touch()
        row=dict(who='dot',thread=w['agent_work']['thread'],ts=str(self.now+1),text='Synthetic incoming report')
        def forbidden(*a,**kw):raise AssertionError('stopped lane invoked a side effect')
        lines=D.agent_wants_pass(forbidden,'fixture-channel','fixture-dot',self.state,self.now+2,
            rows=[row],writer=forbidden,identity='Fixture',notify=forbidden,complete=forbidden,block_notify=forbidden)
        self.assertIn('stopped',lines[0])
        self.assertIn('Synthetic incoming report',str(W.load(w,work,self.ws)['events']))

    def test_pinned_adapter_observations_are_request_local(self):
        import want_working_thread as W
        import claude_sub as C
        import astra_call as fallback
        seen=[]
        def ask(model,system,user,**kw):
            seen.append(model);return 'fixture'
        with patch.object(C,'ask',ask), patch.object(fallback,'call',side_effect=AssertionError('unexpected fallback')):
            one=W.ask('fixture','one');two=W.ask('fixture','two')
        self.assertEqual(seen,[W.MODEL,W.MODEL]);self.assertEqual(len(one['observations']),1)
        self.assertIsNot(one['observations'],two['observations'])

    def test_result_review_requests_correction_then_delivers_revision(self):
        import dot_channel as D
        import want_working_thread as W
        self.intake();rec,artifact=self.result();a=self.current()[0]['agent_work'];posts=[];calls=[]
        def writer(s,u):
            calls.append(json.loads(u));accept=calls[-1]['instruction']['acceptance']=='Revised fixture evidence'
            raw=json.dumps({'message':'Checked revised deliverable.' if accept else 'Supply the missing fixture check.', 'accept':accept})
            return {'text':raw,'observations':[]}
        def api(method,args):
            self.assertEqual(method,'chat.postMessage');posts.append(args);return {'ok':True,'ts':str(self.now+len(posts)+1)}
        with patch.object(D,'STATE',str(self.mem/'room.json')),patch.object(D,'_guarded',lambda s:[]), \
             patch.object(D,'_upload',lambda *a: self.fail('rejected result cannot upload')):
            kw=dict(writer=writer,identity=lambda:'Fixture',notify=self.notify,complete=self.complete)
            row=dict(who='dot',thread=a['thread'],ts=str(self.now+1),text='WANT RESULT '+a['request_id'])
            D.agent_wants_pass(api,'fixture-channel','fixture-dot',self.state,self.now+2,rows=[row],**kw)
            D.agent_wants_pass(api,'fixture-channel','fixture-dot',self.state,self.now+3,**kw)
        self.assertEqual(len(calls),1);self.assertEqual(len(posts),1);self.assertFalse(self.notifications)
        w=self.current()[0];work=W.binding(w,self.state)
        self.assertEqual(W.load(w,work,self.ws)['events'][-1]['who'],'vintos')
        rec['acceptance']='Revised fixture evidence'
        artifact.write_text('Synthetic revised score with additional checked output.')
        rec['artifacts'][0]['sha256']=hashlib.sha256(artifact.read_bytes()).hexdigest()
        (A.directory(a['request_id'],self.ws)/'result.json').write_text(json.dumps(rec))
        self.receive(ts=str(self.now+4))
        def review(w,result):
            return W.generate(w,work,self.ws,'result','revision',result,writer)['message']
        A.finish(self.state,self.publish,self.notify,self.complete,self.save,self.now+5,ws=self.ws,review=review)
        self.assertEqual(len(self.notifications),1);self.assertEqual(len(self.endings),1)
        done=json.loads((self.mem/'fulfilled-wants.json').read_text())[0]
        self.assertEqual(done['agent_work']['completion_message'],'Checked revised deliverable.')
        self.assertTrue(any(e['key'].startswith('delivered:') for e in W.load(done,work,self.ws)['events']))

    def test_thread_is_private_and_conflicting_event_is_not_overwritten(self):
        import want_working_thread as W
        self.intake();w=self.current()[0];work=W.binding(w,self.state)
        path=A.directory(w['agent_work']['request_id'],self.ws)/'working-thread.json'
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        W.append(w,work,self.ws,'fixture-event','dot','original')
        with self.assertRaises(ValueError): W.append(w,work,self.ws,'fixture-event','dot','changed')
        self.assertEqual(W.load(w,work,self.ws)['events'][-1]['text'],'original')

    def test_bound_purchase_uses_existing_owner_approval(self):
        import dot_channel as D
        import gloria_asks as G
        seen=[];posts=[]
        row=dict(who='agent',name='Muse',agent_authenticated=True,thread='fixture-thread',ts='1',
                 text='BUY: synthetic account | 5 | fixture shop | https://example.invalid/item')
        with patch.object(G,'ask',lambda *a,**k:(seen.append((a,k)) or ('fixture','Owner decision requested'))), \
             patch.object(D,'_settled_why',lambda *a:None):
            D.agent_owner_requests(row,{},self.now,lambda m,a:posts.append((m,a)),'fixture-channel')
        self.assertEqual(len(seen),1);self.assertEqual(seen[0][1]['kind'],'buy')
        self.assertEqual(seen[0][1]['thread'],'fixture-thread');self.assertEqual(len(posts),1)

    def test_owner_request_retries_from_saved_thread_without_new_messages(self):
        import dot_channel as D
        self.intake();a=self.current()[0]['agent_work'];attempts=[];posts=[]
        row=dict(who='agent',name='Muse',agent_authenticated=True,thread=a['thread'],ts=str(self.now+1),
                 text='BUY: synthetic account | 5 | fixture shop')
        def owner(*args):
            attempts.append(1)
            return ['could not put Muse find to Gloria'] if len(attempts)==1 else ['owner asked']
        def api(method,args): posts.append(args);return {'ok':True,'ts':str(self.now+2)}
        with patch.object(D,'STATE',str(self.mem/'room.json')),patch.object(D,'_guarded',lambda s:[]), \
             patch.object(D,'agent_owner_requests',owner):
            kw=dict(writer=self.writer,identity=lambda:'Fixture',notify=self.notify,complete=self.complete)
            with self.assertRaises(RuntimeError):
                D.agent_wants_pass(api,'fixture-channel','fixture-dot',self.state,self.now+2,rows=[row],**kw)
            D.agent_wants_pass(api,'fixture-channel','fixture-dot',self.state,self.now+3,**kw)
            D.agent_wants_pass(api,'fixture-channel','fixture-dot',self.state,self.now+4,**kw)
        self.assertEqual(len(attempts),2);self.assertEqual(len(posts),1)


if __name__=='__main__':unittest.main()

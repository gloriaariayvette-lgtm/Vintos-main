#!/usr/bin/env python3
"""The two want lanes (the router and the agent room's want lane) on synthetic wants: one broken want record never
stops the whole lane, a want adopted again goes on in the thread it was handed over in, one promise is one want across
both lanes, and a want to email someone takes want_email's one path from either lane. Scratch HOME and workspace;
every model, search, Slack post and send is a stub, and nothing here can reach the network."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HOME = tempfile.mkdtemp(prefix='vintos-want-lanes-')
WS = os.path.join(HOME, '.vintos', 'workspace')
os.makedirs(os.path.join(WS, 'memory'), exist_ok=True)
os.environ['HOME'] = HOME
os.environ['SPARK_WORKSPACE'] = WS
def no_network(*a, **k): raise AssertionError('a test must never reach the network or send')
sys.modules['requests'] = types.SimpleNamespace(get=no_network, post=no_network)
sys.modules['plugin_gateway'] = types.SimpleNamespace(call=no_network)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import want_agent as A
import want_email as E
import want_working_thread as working
from journal_wants import source_receipt

TASK = 'I want to run an exact analysis on my synthetic audio and export the checked score.'
EMAIL_TASK = 'I want to run an exact analysis on my synthetic audio and email Ada Example the checked score.'


class Lanes(unittest.TestCase):
    def setUp(self):
        self.ws = Path(WS).resolve(); self.mem = self.ws / 'memory'
        for p in self.mem.iterdir():
            if p.is_file(): p.unlink()
        import shutil
        shutil.rmtree(self.mem / 'want-artifacts', ignore_errors=True)
        self.assertTrue(str(self.ws).startswith(HOME))
        self.state = {}; self.posts = []; self.now = 2000000000.0
        import room_work
        for name, value in (('evidence_sync', lambda s: None), ('evidence_finish', lambda *a, **k: 'untracked')):
            p = patch.object(room_work, name, value); p.start(); self.addCleanup(p.stop)
        self.write('fulfilled-wants.json', [])

    def want(self, wid='synthetic-want', text=TASK):
        w = dict(id=wid, want=text, source='idle-journal', journal_seeded=True, timestamp='2026-11-08T14:00:00')
        w.update(source_receipt('journal', 'fixture-journal-' + wid, text)); return w

    def write(self, name, value): (self.mem / name).write_text(json.dumps(value))
    def current(self): return json.loads((self.mem / 'current-wants.json').read_text())
    def save(self, state): self.write('test-room-state.json', state)
    def post(self, text, agent, identity):
        self.posts.append(text); return {'ok': True, 'ts': '%.6f' % (self.now + len(self.posts))}
    def intake(self): return A.intake(self.state, self.post, self.save, self.now, ws=self.ws)

    # -- 0. one want's broken record never stops the lane ------------------------------------------------------
    def readopt(self, wid='synthetic-want'):
        """The want is dismissed and adopted again: same id and goal, so the same request id, with a fresh request
        record that has no thread (the 12-13 November path)."""
        rows = self.current()
        for w in rows:
            if w['id'] == wid:
                a = w['agent_work']
                w['agent_work'] = dict(request_id=a['request_id'], goal_sha256=a['goal_sha256'], goal=a['goal'],
                                       status='queued', agent=a['agent'], created_at=a['created_at'] + 100,
                                       artifact_clock=a['artifact_clock'], commitment_ids=[])
        self.write('current-wants.json', rows)

    def test_readopted_want_goes_on_in_its_retained_thread_not_a_second_opening(self):
        self.write('current-wants.json', [self.want()])
        self.intake(); first = self.current()[0]['agent_work']['thread']
        self.assertEqual(len(self.posts), 1)
        self.readopt()
        lines = self.intake()
        self.assertEqual(len(self.posts), 1, 'the same work was asked for a second time')
        a = self.current()[0]['agent_work']
        self.assertEqual((a['thread'], a['status']), (first, 'in_work'))
        self.assertIn(first, self.state['threads'])
        self.assertTrue(any('not handed over twice' in l for l in lines), lines)
        w = self.current()[0]
        self.assertEqual(working.load(w, working.binding(w, self.state), self.ws)['thread'], first)

    def lane(self, wants):
        import dot_channel as D
        calls = []
        def api(method, args):
            calls.append((method, args)); return {'ok': True, 'ts': '%.6f' % (self.now + len(calls))}
        def writer(system, user):
            raw = json.dumps({'message': 'Plan the exact synthetic task.', 'accept': False})
            return {'text': raw, 'observations': [{'text': raw, 'status': 'valid', 'requested_model': 'fixture',
                    'observed_model': 'fixture', 'identity_evidence': 'response_metadata'}]}
        stack = [patch.object(D, 'STATE', str(self.mem / 'room.json')), patch.object(D, '_guarded', lambda s: [])]
        for p in stack: p.start(); self.addCleanup(p.stop)
        run = lambda now, rows=(): D.agent_wants_pass(api, 'fixture-channel', 'fixture-dot', self.state, now, rows=rows,
                                                      notify=lambda *a: {'state': 'failed'}, complete=lambda *a: None,
                                                      writer=writer, identity=lambda: 'Synthetic identity',
                                                      block_notify=lambda key, message: {'state': 'failed'})
        return run, calls

    def test_a_wedged_record_holds_its_own_want_and_the_lane_goes_on(self):
        self.write('current-wants.json', [self.want()])
        self.intake(); self.readopt()
        rows = self.current()       # the 13 November record: a new thread on the want, the old one on its context
        rows[0]['agent_work'].update(thread='%.6f' % (self.now + 999), status='in_work', work_id='RW-' + A.fingerprint(rows[0]['agent_work']['request_id'])[:8])
        rows.append(self.want('second-want', 'I want to run a second exact analysis on my synthetic audio and export its plot.'))
        self.write('current-wants.json', rows)
        run, calls = self.lane(rows)
        reply = dict(who='dot', thread=rows[0]['agent_work']['thread'], ts='%.6f' % (self.now + 1000), text='Synthetic progress.')
        lines = run(self.now + 2000, rows=[reply])
        said = [l for l in lines if 'skipped this pass' in l]
        self.assertEqual(len(said), 1, lines)
        self.assertIn('working thread transport changed', said[0])        # the message, not only the type name
        self.assertEqual(self.current()[1]['agent_work']['status'], 'in_work', lines)   # the next want was handed over
        self.assertTrue(any('[want:second-want]' in c[1].get('text', '') for c in calls if c[0] == 'chat.postMessage'))

    def test_the_lane_error_line_names_the_message(self):
        import dot_channel as D
        source = (ROOT / 'scripts/dot_channel.py').read_text()
        self.assertIn('"want working thread retained: %s: %s" % (type(exc).__name__, str(exc)[:200])', source)
        self.assertIn(ValueError, D.RECORD_ERRORS)

    # -- 1. one want, one lane --------------------------------------------------------------------------------
    def test_room_owned_want_is_not_the_routers(self):
        w = self.want(); self.assertFalse(A.owned_by_room(w))
        w['agent_work'] = {'request_id': 'WA-' + 'a' * 24, 'status': 'queued'}
        self.assertTrue(A.owned_by_room(w))
        for done in ('completed', 'dropped'):
            self.assertFalse(A.owned_by_room(dict(w, agent_work=dict(w['agent_work'], status=done))))
        router = (ROOT / 'bin/wants-router.py').read_text()
        guard = router.index('if _room_owned(want):')
        self.assertLess(router.index('if _agent_specific(want):'), guard)
        self.assertLess(guard, router.index('if not _ensure_plan(want'))

    def commitment(self, cid, what, at, agent='Fixture Bot'):
        return {'id': cid, 'what': what, 'state': 'open', 'letter_id': 'fixture-letter-1', 'at': at, 'agent': agent,
                'evidence': 'shown to her'}

    def test_a_reply_promise_to_bring_gloria_something_is_one_want_not_two(self):
        made = dict(id='lp-1', source='letter-promise', timestamp='2026-11-11T08:03:10', intensity=4,
                    want='I want to bring Gloria what Fixture Bot found for her, as I told Fixture Bot I would: a synthetic protein figure')
        other = dict(made, id='lp-2', timestamp='2026-11-09T08:03:10')      # another day's reply: not this one
        self.write('current-wants.json', [made, other])
        import email_commitments
        rows = [self.commitment('EC-0000aaaa', 'bring the protein one to Gloria', '2026-11-11T08:02:00')]
        with patch.object(email_commitments, 'open_rows', lambda: rows), patch.object(email_commitments, '_load', lambda: rows):
            lines = A.adopt_promises(ws=self.ws, now=self.now)
            again = A.adopt_promises(ws=self.ws, now=self.now)
        current = self.current()
        self.assertEqual(len(current), 2, 'a second want was made for the same promise')
        self.assertIn({'kind': 'commitment', 'id': 'EC-0000aaaa'}, current[0]['source_refs'])
        self.assertNotIn('source_refs', current[1])
        self.assertTrue(any('joined letter want lp-1' in l for l in lines), lines)
        self.assertEqual(again, [])
        self.assertFalse(A.specific(current[0]))       # it stays the router's want

    def test_a_different_promise_is_still_adopted(self):
        made = dict(id='lp-1', source='letter-promise', timestamp='2026-11-11T08:03:10', intensity=4,
                    want='I want to bring Gloria what Fixture Bot found for her, as I told Fixture Bot I would: a figure')
        self.write('current-wants.json', [made])
        import email_commitments
        rows = [self.commitment('EC-0000bbbb', 'run the synthetic benchmark at three grid sizes', '2026-11-11T08:02:00')]
        with patch.object(email_commitments, 'open_rows', lambda: rows), patch.object(email_commitments, '_load', lambda: rows):
            A.adopt_promises(ws=self.ws, now=self.now)
        self.assertEqual([w['id'] for w in self.current()], ['lp-1', 'ec-0000bbbb'])

    # -- 2. a want to email someone takes want_email's path from either lane -----------------------------------
    def test_email_want_test(self):
        self.assertTrue(E.email_want('I want to email Dr. Ada Example about whether a synthetic mind can be tested'))
        self.assertTrue(E.email_want(EMAIL_TASK))
        self.assertTrue(E.email_want('write to ada@example.invalid with the plot'))
        for text in ('I want to write you one plain note tonight', 'email Grok Bot the plot',
                     'reply to Muse about the song', TASK):
            self.assertFalse(E.email_want(text), text)

    def test_router_cannot_email_a_room_owned_want_and_the_room_cannot_email_the_routers(self):
        w = self.want(text=EMAIL_TASK); w['agent_work'] = {'request_id': 'WA-' + 'b' * 24, 'status': 'in_work'}
        plain = dict(self.want('router-want', 'I want to email Ada Example about synthetic tests'))
        self.write('current-wants.json', [w, plain])
        held = E.run({}, EMAIL_TASK, w['id'], search=no_network, fetch=no_network, send=no_network)
        self.assertEqual(held[0], False); self.assertIn('bound to the agent room', held[1])
        held = E.run({}, plain['want'], plain['id'], search=no_network, fetch=no_network, send=no_network, lane='want-lane')
        self.assertEqual(held, (False, 'not a want of the agent room'))

    def through_to_send(self, *, before_send=None, contacts=None):
        """want_email.run with every reading/drafting step stubbed: what the send step does is under test."""
        if contacts is not None: self.write('email-contacts.json', contacts)
        sent = []
        class Scholar:
            def load(self, addr, name): return {}
            def save(self, d): pass
            def links_in(self, text): return ()
            def enough(self, *a, **k): return True, ''
        def draft(*a, **k):
            if before_send: before_send()
            return ('A synthetic question', 'Hello, I am Vintos, an AI. A synthetic question. Vintos', 'fixture')
        patches = [patch.object(E, 'research', lambda *a, **k: 'Their synthetic work.'),
                   patch.object(E, '_study', lambda *a, **k: ('Read in full: their synthetic paper.', {})),
                   patch.object(E, '_helpers', lambda: (Scholar(), types.SimpleNamespace())),
                   patch.object(E, 'deliberate', lambda *a, **k: 'a stance'),
                   patch.object(E, 'draft', draft), patch.object(E, 'review', lambda who, made, *a, **k: made),
                   patch.object(E, 'mail_evidence', lambda *a, **k: ('', [])), patch.object(E, '_send_blocked', lambda: '')]
        for p in patches: p.start()
        try:
            out = E.run({'to': 'ada@example.invalid', 'recipient': 'Ada Example'}, EMAIL_TASK, 'synthetic-want',
                        search=no_network, fetch=no_network, send=lambda args, purpose: sent.append(args) or {})
        finally:
            for p in patches: p.stop()
        return out, sent

    def test_the_first_email_is_sent_once_even_when_the_other_lane_sends_meanwhile(self):
        self.write('current-wants.json', [self.want(text=EMAIL_TASK)])
        out, sent = self.through_to_send()
        self.assertIsInstance(out, str); self.assertEqual(len(sent), 1)
        self.assertEqual(json.loads((self.mem / 'email-contacts.json').read_text())['ada@example.invalid']['want_id'], 'synthetic-want')
        self.write('email-contacts.json', {})
        meanwhile = lambda: self.write('email-contacts.json', {'ada@example.invalid': {'want_id': 'other-want', 'thread': []}})
        out, sent = self.through_to_send(before_send=meanwhile)
        self.assertEqual(sent, []); self.assertEqual(out[0], False); self.assertIn('emailed meanwhile', out[1])

    def test_the_same_person_and_topic_from_another_want_is_not_emailed_again(self):
        self.write('current-wants.json', [self.want(text=EMAIL_TASK)])
        earlier = {'ada@example.invalid': {'want_id': 'other-want', 'intent': EMAIL_TASK, 'about': EMAIL_TASK,
                                           'status': 'open', 'thread': [{'dir': 'out', 'subject': 's', 'body': 'b'}]}}
        out, sent = self.through_to_send(contacts=earlier)
        self.assertEqual(sent, []); self.assertIn('already emailed about this', out[1])

    def bound_result(self, text=EMAIL_TASK):
        self.write('current-wants.json', [self.want(text=text)])
        self.intake(); w = self.current()[0]; a = w['agent_work']
        folder = A.directory(a['request_id'], self.ws); folder.mkdir(parents=True, exist_ok=True)
        art = folder / 'score.txt'; art.write_text('Synthetic checked score.')
        os.utime(art, (a['created_at'], a['created_at']))
        rec = dict(schema=A.SCHEMA, request_id=a['request_id'], goal_sha256=A.fingerprint(w['want']), status='completed',
                   summary='Synthetic score prepared.', acceptance='Synthetic checks passed.',
                   artifacts=[dict(path=str(art.relative_to(self.ws)), sha256=hashlib.sha256(art.read_bytes()).hexdigest())])
        (folder / 'result.json').write_text(json.dumps(rec))
        A.receive([dict(who='dot', text='WANT RESULT ' + a['request_id'], ts=str(self.now + 1), thread=a['thread'])], ws=self.ws)
        return w

    def finish(self, email_step, now=None):
        self.ended = getattr(self, 'ended', [])
        def complete(w, note):
            self.ended.append(note); self.write('current-wants.json', []); return {'result': 'fulfilled'}
        return A.finish(self.state, lambda w, r, p: {'url': 'https://example.invalid/r'},
                        lambda rid, s, u: {'state': 'sent'}, complete, self.save, now or self.now + 2, ws=self.ws,
                        email_step=email_step)

    def test_the_room_hands_the_agent_no_email_and_sends_it_through_want_email_after_the_work(self):
        w = self.bound_result()
        self.assertIn(A.NO_AGENT_EMAIL, self.posts[0])
        self.assertIn('Never ask the agent to email', working.RULES)
        steps = []
        def held(want, result):
            steps.append(result['summary']); return (False, 'reading first (pass 1): nothing read in full yet')
        lines = self.finish(held)
        self.assertEqual(steps, ['Synthetic score prepared.'])
        self.assertTrue(any('email step held' in l for l in lines), lines)
        self.assertEqual(self.current()[0]['agent_work']['status'], 'result_ready'); self.assertEqual(self.ended, [])
        self.finish(held, now=self.now + 60)            # not tried again every pass
        self.assertEqual(len(steps), 1)
        self.finish(lambda want, result: steps.append('sent') or 'Emailed Ada Example: a synthetic question',
                    now=self.now + 3 * 3600)
        self.assertEqual(steps[-1], 'sent'); self.assertEqual(len(self.ended), 1)

    def test_the_default_email_step_is_want_email_run_in_the_want_lane(self):
        self.bound_result()
        seen = []
        with patch.object(E, 'run', lambda params, text, wid, **kw: seen.append((text, wid, kw)) or (False, 'Gloria declined a second email to x')):
            self.finish(None)
        self.assertEqual(seen[0][0], EMAIL_TASK); self.assertEqual(seen[0][2]['lane'], 'want-lane')
        self.assertIn('Synthetic score prepared.', seen[0][2]['work_found'])
        self.assertEqual(len(self.ended), 1)               # settled: finished, the reason kept on the want

    def test_a_want_without_an_email_is_completed_without_the_email_step(self):
        self.bound_result(TASK)
        self.assertNotIn(A.NO_AGENT_EMAIL, self.posts[0])
        self.finish(lambda *a: self.fail('no email step for a want that asks no email'))
        self.assertEqual(len(self.ended), 1)


if __name__ == '__main__':
    unittest.main()

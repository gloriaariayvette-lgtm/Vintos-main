#!/usr/bin/env python3
"""SK-d0b42347: the Slack want router recovers without guessing.

A result review whose retained reply is a narrative, not a decision, held its want on every pass: local review refused
it and the hold kept the ordinary path (with its capped correction) away. It now takes that correction, within the
want's budget, and only an explicit JSON decision is ever used; prose is never read as accept. Owner pauses, explicit
work pauses and uncertain calls still make no call. An archived source frees its room row only when no live want owns
the same request; intake then hands over the queued want and every pause it did not own is unchanged.

Scratch workspace, scratch capture root and room state; the writer, Slack, deliver and the witness sink are stubs;
every socket is refused."""
from contextlib import ExitStack
import copy, json, os, socket, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import want_agent as A
import want_working_thread as W
import want_work_budget as B
import dot_channel as D
import room_work as R
import deliver
import witness_sink
from journal_wants import source_receipt


def reply(text):
    return dict(text=text, observations=[dict(text=text, status='valid', identity_evidence='response_metadata',
                                               observed_model='fixture-served', requested_model='fixture-request')])


def forbidden(what):
    return Mock(side_effect=AssertionError(what + ' forbidden in this suite'))


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='want-router-recovery-'); self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name).resolve(); self.mem = self.ws / 'memory'; self.mem.mkdir()
        stack = ExitStack(); self.addCleanup(stack.close)
        # Every path written: the want stores, working threads and budget (SPARK_WORKSPACE), the capture packets
        # (JUDGES_CAPTURE_SCRATCH, the same private scratch) and the room state (dot_channel.STATE).
        stack.enter_context(patch.dict(os.environ, SPARK_WORKSPACE=str(self.ws), JUDGES_CAPTURE_SCRATCH=str(self.ws)))
        stack.enter_context(patch.object(D, 'STATE', str(self.mem / 'room.json')))
        # Every sender is a stub that fails the suite if reached.
        self.senders = dict(socket=forbidden('network'), ask=forbidden('provider'), deliver=forbidden('deliver'),
                            publish=forbidden('production capture'), enqueue=forbidden('production capture'),
                            sink=forbidden('production capture config'))
        for obj, name, key in ((socket.socket, 'connect', 'socket'), (W, 'ask', 'ask'), (deliver, 'deliver', 'deliver'),
                               (witness_sink, 'publish', 'publish'), (witness_sink, 'enqueue_capture', 'enqueue'),
                               (witness_sink, 'configuration', 'sink')):
            stack.enter_context(patch.object(obj, name, self.senders[key]))
        stack.enter_context(patch.object(D, '_guarded', lambda text: []))
        stack.enter_context(patch.object(R, 'open_items', side_effect=lambda state: list(state['room_work']['open'])))
        self.now = time.time()
        want = dict(id='fixture-want', want='I want to run a synthetic analysis and export the result.', source='email',
                    timestamp='2026-11-19T00:00:00', fulfilled=False)
        want.update(source_receipt('email', 'fixture-mail', want['want']))
        want['agent_work'] = dict(request_id='WA-' + 'c' * 24, goal_sha256=A.fingerprint(want['want']), agent='dot',
                                  created_at=self.now - 9000, status='result_ready', thread='fixture-thread',
                                  work_id='RW-fixture', blocked={'reason': 'response_needs_review', 'since': self.now - 600,
                                                                 'passes': 3})
        self.write('current-wants.json', [want]); self.write('fulfilled-wants.json', [])
        self.work = dict(id='RW-fixture', goal=want['want'], opened=1, touched=1, asks=[], returns=[], steps=[], by='want',
                         want_id=want['id'], want_request_id=want['agent_work']['request_id'],
                         paused_until=self.now + 3600, pause_why='held: blocked_response_needs_review; fixture')
        self.state = {'room_work': {'open': [self.work], 'history': []}}
        W.load(want, self.work, self.ws, 'Synthetic identity')
        self.result = {'summary': 'verified fixture result', 'acceptance': 'fixture checks'}
        self.trigger = A.fingerprint(json.dumps(self.result, sort_keys=True))
        self.key = 'result:' + A.fingerprint(self.trigger)
        self.posts, self.users, self.replies = [], [], []

    def test_isolation_is_in_force(self):
        self.assertNotIn('.vintos', self.ws.parts)
        self.assertEqual(A.workspace(), self.ws)
        self.assertEqual(Path(D.STATE).parent, self.mem)
        import witness_capture
        self.assertEqual(witness_capture._private_root(witness_capture._capture_location()), self.ws)
        for name, stub in self.senders.items():
            self.assertIsInstance(stub, Mock, name)
        self.assertIs(socket.socket.connect, self.senders['socket'])

    # ---- fixture helpers
    def write(self, name, value): (self.mem / name).write_text(json.dumps(value))
    def want(self): return json.loads((self.mem / 'current-wants.json').read_text())[0]
    def record(self): return W.load(self.want(), self.work, self.ws)['generations'].get(self.key)

    def seed(self, raw, state='response_observed', rejected=()):
        record = dict(state=state, request_id='fixture-retained', at=time.time() - 10, rejected=list(rejected),
                      observations=[], result=reply(raw))
        W._mutate(self.want(), self.work, self.ws, lambda data: data['generations'].update({self.key: record}))

    def api(self, method, payload):
        self.assertEqual(method, 'chat.postMessage'); self.posts.append(payload)
        return {'ok': True, 'ts': '%.6f' % (self.now + len(self.posts))}

    def writer(self, system, user):
        self.users.append(json.loads(user)); return reply(self.replies.pop(0))

    def run_pass(self):
        returned = []
        def finish(state, *args, review=None, **kwargs):
            for w in json.loads((self.mem / 'current-wants.json').read_text()):
                if (w.get('agent_work') or {}).get('status') == 'result_ready':
                    try:
                        returned.append(review(w, self.result))
                    except RuntimeError as exc:                     # the real finish retains the result the same way
                        returned.append('retained: ' + str(exc))
            return []
        with patch.object(A, 'finish', finish), patch.object(A, 'intake', return_value=[]), \
             patch.object(A, 'release_blocked', return_value=[]):
            lines = D.agent_wants_pass(self.api, 'fixture-channel', 'fixture-dot', self.state, self.now,
                                       writer=self.writer, block_notify=lambda key, message: {'state': 'sent'},
                                       identity=lambda: 'Synthetic identity')
        return returned, lines

    # ---- result review recovery
    def test_narrative_review_gets_explicit_accept_then_is_idempotent(self):
        narrative = 'The agent finished the analysis and the files look right to me.'
        self.seed(narrative)
        self.replies = [json.dumps({'message': 'Finished: the exported table checks out.', 'accept': True})]
        returned, _ = self.run_pass()
        self.assertEqual(returned, ['Finished: the exported table checks out.'])
        self.assertEqual(len(self.users), 1)
        self.assertIn('not JSON', self.users[0]['correction'])
        rec = self.record()
        self.assertEqual(rec['state'], 'done')
        self.assertEqual(rec['rejected'][0]['result']['text'], narrative)            # the original observation is kept
        self.assertEqual(self.work['paused_until'], 0)                              # its automatic hold is released
        self.assertIsNone(self.want()['agent_work']['blocked'])
        self.assertEqual(self.posts, [])                                            # accept publishes only via finish
        # A second pass decides from the recorded decision: no call, the same answer.
        returned, _ = self.run_pass()
        self.assertEqual(returned, ['Finished: the exported table checks out.'])
        self.assertEqual(len(self.users), 1)

    def test_narrative_review_gets_explicit_reject_returned_once(self):
        self.seed('Looks mostly done, maybe.')
        self.replies = [json.dumps({'message': 'The column export is missing; please add it.', 'accept': False})]
        returned, _ = self.run_pass()
        self.assertEqual(returned, [None])
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.posts[0]['thread_ts'], 'fixture-thread')
        self.assertIn('The column export is missing', self.posts[0]['text'])
        returned, _ = self.run_pass()
        self.assertEqual(returned, [None])
        self.assertEqual(len(self.posts), 1)                                        # returned to the agent once
        self.assertEqual(len(self.users), 1)

    def test_prose_is_never_accept_and_corrections_stop_at_cap(self):
        self.seed('I accept this result; it meets the request exactly.')
        self.replies = ['Yes, accepted, all good.', 'Accept: true. It is done.']
        returned, lines = self.run_pass()
        self.assertEqual(returned, [None])
        self.assertEqual(len(self.users), W.SHAPE_RETRIES)
        self.assertEqual(self.posts, [])
        self.assertTrue(self.work['pause_why'].startswith('held: blocked_response_needs_review'))
        self.assertEqual(self.want()['agent_work']['blocked']['reason'], 'response_needs_review')
        self.assertEqual(len(self.record()['rejected']), W.SHAPE_RETRIES)
        self.assertTrue(any('response_needs_review' in line for line in lines))
        returned, _ = self.run_pass()                                               # past the cap: no further call
        self.assertEqual(returned, [None])
        self.assertEqual(len(self.users), W.SHAPE_RETRIES)

    def test_active_holds_and_uncertain_calls_make_no_call(self):
        cases = [('owner pause', dict(pursuit={'state': 'PAUSED', 'paused_until': self.now + 86400}), None, 'response_observed'),
                 ('explicit work pause', {}, 'Gloria paused this work', 'response_observed'),
                 ('uncertain call', {}, None, 'uncertain')]
        for name, want_change, pause_why, state in cases:
            with self.subTest(name):
                self.setUp()
                rows = json.loads((self.mem / 'current-wants.json').read_text()); rows[0].update(want_change)
                self.write('current-wants.json', rows)
                if pause_why: self.work['pause_why'] = pause_why
                before = copy.deepcopy(self.work)
                self.seed('A narrative result review.', state=state)
                returned, _ = self.run_pass()
                self.assertEqual(self.users, [])
                self.assertEqual(self.posts, [])
                self.assertEqual(self.work, before)
                self.assertNotEqual(returned, ['A narrative result review.'])

    def test_shape_check_is_local_and_bounded(self):
        want = self.want()
        self.seed('Prose only.')
        with patch.object(B, 'reserve', forbidden('budget reservation')):
            self.assertTrue(W.observed_shape_failure(want, self.work, self.ws, 'result', self.trigger))
            self.assertFalse(W.observed_shape_failure(want, self.work, self.ws, 'continue', self.trigger))
        self.seed(json.dumps({'message': 'Valid.', 'accept': True}))
        self.assertFalse(W.observed_shape_failure(want, self.work, self.ws, 'result', self.trigger))
        self.seed('Prose only.', rejected=[{}] * W.SHAPE_RETRIES)
        self.assertFalse(W.observed_shape_failure(want, self.work, self.ws, 'result', self.trigger))
        for state in ('running', 'uncertain', 'done'):
            self.seed('Prose only.', state=state)
            self.assertFalse(W.observed_shape_failure(want, self.work, self.ws, 'result', self.trigger))

    # ---- archived source rows
    def test_archived_rows_free_capacity_only_without_a_live_owner_and_intake_resumes(self):
        held = dict(paused_until=self.now + 3600, pause_why='held: blocked_response_needs_review')
        def row(wid, rid, **kw):
            return dict(dict(id='RW-' + wid, want_id=wid, want_request_id=rid, goal='fixture', opened=1, touched=1,
                             asks=[{'thread': 'fixture'}], returns=[{'evidence': 'retained'}]), **dict(held, **kw))
        stale = [row(wid, 'WA-' + str(i) * 24) for i, wid in enumerate(('c3b97879', 'ec-147665b6', 'ec-e00919ba'), 1)]
        owned = row('ec-joined', 'WA-' + '7' * 24)
        owner_paused = row('owner-paused', 'WA-' + '8' * 24, pause_why='Gloria paused this work')
        other = row('other-held', 'WA-' + '9' * 24)
        state = {'room_work': {'open': copy.deepcopy(stale + [owned, owner_paused, other]), 'history': []}}
        self.assertEqual(len(state['room_work']['open']), R.MAX_HELD)
        archive = [dict(id=r['want_id'], fulfilled=True, agent_work=dict(request_id=r['want_request_id'], status='in_work'))
                   for r in stale + [owned]]
        self.write('fulfilled-wants.json', archive)
        archive_bytes = (self.mem / 'fulfilled-wants.json').read_bytes()
        queued_goal = 'run the fixture and export its result'
        live = [dict(id='joined-live', want=queued_goal + ' again', fulfilled=False, timestamp='2026-11-18T00:00:00',
                     agent_work=dict(request_id=owned['want_request_id'], status='in_work', agent='dot',
                                     goal_sha256=A.fingerprint(queued_goal + ' again'))),
                dict(id='queued', want=queued_goal, fulfilled=False, timestamp='2026-11-19T00:00:00',
                     agent_work=dict(request_id='WA-' + 'f' * 24, status='queued', agent='dot',
                                     goal_sha256=A.fingerprint(queued_goal)))]
        self.write('current-wants.json', live)
        stop = self.mem / 'want-work.stop'
        self.assertFalse(stop.exists())
        post = Mock(return_value={'ok': True, 'ts': 'fixture-ts'})
        with patch.object(A, 'specific', return_value=True), patch.object(A, 'age_out', return_value=0), \
             patch.object(W, 'load', return_value={}), patch.object(W, 'retained_thread', return_value=None), \
             patch.object(W, 'append'), patch.object(R, 'posted'):
            lines = A.intake(state, post, lambda s: None, self.now, ws=self.ws)
        post.assert_called_once()                                                   # intake resumed: one handoff
        self.assertTrue(any('handed to its agent' in line for line in lines))
        open_ids = [r['id'] for r in state['room_work']['open']]
        self.assertEqual(open_ids[:3], ['RW-ec-joined', 'RW-owner-paused', 'RW-other-held'])
        self.assertEqual(state['room_work']['open'][:3], [owned, owner_paused, other])   # pauses it did not own: unchanged
        detached = state['room_work']['detached_source_work']
        self.assertEqual([d['id'] for d in detached], [r['id'] for r in stale])
        for original, kept in zip(stale, detached):
            self.assertEqual({k: kept[k] for k in original}, original)              # the full record, with its evidence
            self.assertEqual(kept['source_state'], 'archived')
            self.assertNotIn('delivery', kept)                                      # no delivery inferred
        self.assertEqual(state['room_work']['history'], [])
        self.assertEqual((self.mem / 'fulfilled-wants.json').read_bytes(), archive_bytes)
        self.assertFalse(stop.exists())
        A.reconcile_source_work(state, self.now + 1, ws=self.ws)                    # idempotent
        self.assertEqual(len(state['room_work']['detached_source_work']), 3)


if __name__ == '__main__':
    unittest.main()

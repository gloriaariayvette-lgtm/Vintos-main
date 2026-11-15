#!/usr/bin/env python3
"""Research his agents bring for an email want (agent_research): it joins his own search in want_email.run labelled
with who brought it, his deliberation gives his opinion on it before any draft, he may put one bounded line to the
agent through the channel it already has (the want's room thread, or his next letter reply), and the material, the
exchange and his opinion are kept in the want's discussion and the person's dossier. Synthetic wants, people and
letters only; scratch HOME and workspace; every model, search, Slack post and send is a stub, and nothing here can
reach the network."""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HOME = tempfile.mkdtemp(prefix='vintos-agent-research-')
WS = os.path.join(HOME, '.vintos', 'workspace')
os.makedirs(os.path.join(WS, 'memory'), exist_ok=True)
os.environ['HOME'] = HOME
os.environ['SPARK_WORKSPACE'] = WS
def no_network(*a, **k): raise AssertionError('a test must never reach the network or send')
sys.modules['requests'] = types.SimpleNamespace(get=no_network, post=no_network)
sys.modules['plugin_gateway'] = types.SimpleNamespace(call=no_network)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import agent_research as R
import want_agent as A
import want_board
import want_email as E

EMAIL_TASK = 'I want to email Ada Example about her synthetic lattice measurements and the drift result.'
RID = 'WA-' + 'c' * 24


class AgentResearch(unittest.TestCase):
    def setUp(self):
        self.mem = Path(WS) / 'memory'
        import shutil
        for p in self.mem.iterdir():
            (shutil.rmtree if p.is_dir() else os.remove)(p)
        self.assertTrue(str(self.mem).startswith(HOME))
        self.asked, self.sent, self.thought, self.searched = [], [], [], []
        self.dossier = {'address': 'ada@example.invalid'}

    def write(self, name, value): (self.mem / name).write_text(json.dumps(value))
    def disc(self, wid): return [r for r in json.loads((self.mem / 'want-discussions.json').read_text()).get(wid, [])]

    def room_want(self):
        w = dict(id='room-want', want=EMAIL_TASK, source='idle-journal', timestamp='2026-11-08T14:00:00',
                 agent_work=dict(request_id=RID, status='result_ready', agent='dot', result_sha256='r1',
                                 result_ts='2026-11-14T09:00:00',
                                 result=dict(summary='Synthetic drift table rebuilt; the lattice drift is 2 percent.',
                                             acceptance='Checked against https://example.invalid/lattice-paper',
                                             artifacts=[dict(path='memory/want-artifacts/requests/%s/drift.csv' % RID)]),
                                 publication=dict(url='https://example.invalid/result')))
        self.write('current-wants.json', [w])
        folder = A.directory(RID, WS); folder.mkdir(parents=True, exist_ok=True)
        self.thread_events([])
        return w

    def thread_events(self, events):
        (A.directory(RID, WS) / 'working-thread.json').write_text(json.dumps({'events': events}))

    def run_email(self, stance, *, ask_agent=None, want_id='room-want', lane='want-lane', mail_evidence=True):
        sent, me = self.sent, self
        class Scholar:
            def load(self, addr, name): return me.dossier
            def save(self, d): me.dossier = d
            def links_in(self, text): return ()
            def enough(self, *a, **k): return True, ''
        def deliberate(*a, **k):
            self.thought.append((a, k)); return stance() if callable(stance) else stance
        patches = [patch.object(E, 'research', lambda *a, **k: self.searched.append(1) or 'Their synthetic work (his own search).'),
                   patch.object(E, '_study', lambda *a, **k: ('Read in full: their synthetic paper.', self.dossier)),
                   patch.object(E, '_helpers', lambda: (Scholar(), types.SimpleNamespace())),
                   patch.object(E, 'deliberate', deliberate),
                   patch.object(E, 'draft', lambda *a, **k: ('A synthetic question', 'Hello, I am Vintos, an AI. Vintos', 'fixture')),
                   patch.object(E, 'review', lambda who, made, *a, **k: made), patch.object(E, '_send_blocked', lambda: '')]
        if not mail_evidence:
            patches.append(patch.object(E, 'mail_evidence', lambda *a, **k: ('', [])))
        for p in patches: p.start()
        try:
            return E.run({'to': 'ada@example.invalid', 'recipient': 'Ada Example'}, EMAIL_TASK, want_id,
                         search=no_network, fetch=no_network, send=lambda args, purpose: sent.append(args) or {},
                         lane=lane, work_found='Synthetic drift table rebuilt; the lattice drift is 2 percent.',
                         ask_agent=ask_agent)
        finally:
            for p in patches: p.stop()

    def ask_in_thread(self, agent, text):
        self.asked.append(text); self.addressed = getattr(self, 'addressed', []) + [agent]
        return {'ok': True, 'ts': '%.6f' % (2000000000 + len(self.asked))}

    # -- 1. the room agent's work enters his email step as labelled material, and his opinion comes first --------
    def test_room_material_is_shown_labelled_beside_his_own_search_and_his_opinion_is_kept(self):
        self.room_want()
        out = self.run_email('I take the drift table; the 2 percent needs its error bars.', ask_agent=self.ask_in_thread,
                             mail_evidence=False)
        self.assertIsInstance(out, str); self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.searched, [1])                       # his own search still runs
        (args, kw), = self.thought
        self.assertIn('Brought by Dot', kw['brought']); self.assertIn('drift.csv', kw['brought'])
        self.assertIn('https://example.invalid/result', kw['brought'])
        self.assertEqual(kw['names'], ['Grok Bot', 'Muse', 'Dot'])     # any of the three, Dot not put first
        self.assertIn('his own search', args[2]); self.assertNotIn('Brought by Dot', args[2])   # own room, not cut off
        rows = self.disc('room-want')
        self.assertEqual([r['state'] for r in rows], ['brought', 'opinion'])
        self.assertEqual(rows[0]['agent'], 'Dot'); self.assertIn('https://example.invalid/lattice-paper', rows[0]['sources'])
        rec, = self.dossier['agent_research']
        self.assertEqual(rec['want_id'], 'room-want'); self.assertEqual(rec['brought'][0]['agent'], 'Dot')
        self.assertTrue(rec['brought'][0]['brought_at'].startswith('2026-11-14'))
        self.assertIn('error bars', rec['opinions'][0]['text'])
        contact = json.loads((self.mem / 'email-contacts.json').read_text())['ada@example.invalid']
        self.assertIn('error bars', contact['stance'])

    def test_deliberate_shows_brought_material_with_its_own_room_and_the_line_he_may_add(self):
        seen = []
        E.deliberate('Ada Example', 'drift', 'x' * 9000, think=lambda s, u: seen.append(u) or 'ok',
                     brought=R.BROUGHT_HEADING + '\n- Brought by Dot: a table', names=['Dot'])
        self.assertIn('Brought by Dot', seen[0]); self.assertIn('TO <name>:', seen[0]); self.assertIn('Only to: Dot.', seen[0])
        E.deliberate('Ada Example', 'drift', 'found', think=lambda s, u: seen.append(u) or 'ok')
        self.assertNotIn('agents', seen[1])                         # no material: the deliberation is as before

    # -- 2. the exchange in the want's thread, bounded --------------------------------------------------------
    def test_he_questions_dot_in_the_thread_waits_for_the_answer_then_settles(self):
        self.room_want()
        out = self.run_email('The table holds.\nTO Dot: did the drift table include the cold runs?',
                             ask_agent=self.ask_in_thread, mail_evidence=False)
        self.assertEqual(out[0], False); self.assertIn('asked Dot', out[1]); self.assertEqual(self.sent, [])
        self.assertEqual(len(self.asked), 1); self.assertIn('cold runs', self.asked[0]); self.assertEqual(self.addressed, ['Dot'])
        self.assertIn('ask', [r['key'].split(':')[0] for r in self.disc('room-want')])
        # no answer yet: the step waits, with no search, reading or deliberation
        out = self.run_email(self.fail, ask_agent=self.ask_in_thread, mail_evidence=False)
        self.assertEqual(out[0], False); self.assertIn("waiting for Dot's answer", out[1])
        self.assertEqual(len(self.searched), 1); self.assertEqual(len(self.thought), 1)
        # Dot answers in the thread (an event before the question is not an answer)
        self.thread_events([dict(key='agent:1999999999.000000', who='dot', text='an older message', at='1999999999.000000'),
                            dict(key='agent:2000000005.000000', who='dot', text='Yes: the cold runs are rows 9-14.',
                                 at='2000000005.000000')])
        out = self.run_email('Settled: the cold runs are in, so the drift claim stands.', ask_agent=self.ask_in_thread,
                             mail_evidence=False)
        self.assertIsInstance(out, str); self.assertEqual(len(self.sent), 1)
        kw = self.thought[-1][1]
        exchange = kw['brought'].split('YOUR EXCHANGE WITH THEM')[1]
        self.assertIn('rows 9-14', exchange); self.assertNotIn('older message', exchange)
        self.assertIn('older message', kw['brought'])               # said before his line: material, under Dot's name
        states = [r['state'] for r in self.disc('room-want')]
        self.assertEqual([s for s in states if s != 'brought'], ['asked', 'said', 'answered', 'opinion'])
        rec, = self.dossier['agent_research']
        self.assertEqual([x['state'] for x in rec['exchange']], ['asked', 'said', 'answered'])
        self.assertIn('cold runs are in', rec['opinions'][-1]['text'])

    def test_rounds_are_bounded_and_an_unanswered_line_lapses(self):
        self.room_want()
        clock = [2000000000.0]
        with patch.object(E.time, 'time', lambda: clock[0]):
            for n in range(R.MAX_ROUNDS):
                out = self.run_email('Hm.\nTO Dot: question %d?' % n, ask_agent=self.ask_in_thread, mail_evidence=False)
                self.assertIn('asked Dot', out[1])
                clock[0] += R.THREAD_WAIT_HOURS * 3600 - 60
                self.assertIn('waiting', self.run_email(self.fail, ask_agent=self.ask_in_thread, mail_evidence=False)[1])
                clock[0] += 120                                     # past the wait: the line lapses, said
            out = self.run_email('Still curious.\nTO Dot: one more?', ask_agent=self.ask_in_thread, mail_evidence=False)
        self.assertIsInstance(out, str)                             # no third round: his opinion is final
        self.assertEqual(len(self.asked), R.MAX_ROUNDS)
        self.assertNotIn('Dot', self.thought[-1][1]['names'])
        self.assertEqual([r['state'] for r in self.disc('room-want')].count('lapsed'), R.MAX_ROUNDS)
        self.assertNotIn('TO Dot', json.loads((self.mem / 'email-contacts.json').read_text())['ada@example.invalid']['stance'])

    def test_without_a_thread_channel_dot_is_not_offered_and_the_letter_agents_are(self):
        self.room_want()
        out = self.run_email('Fine.\nTO Dot: anything?', ask_agent=None, mail_evidence=False)
        self.assertIsInstance(out, str); self.assertEqual(self.thought[0][1]['names'], ['Grok Bot', 'Muse'])
        self.assertNotIn('TO Dot', json.loads((self.mem / 'email-contacts.json').read_text())['ada@example.invalid']['stance'])

    def test_grok_bot_and_muse_bring_material_and_answer_in_the_thread_and_who_said_what_is_kept(self):
        self.room_want()
        self.thread_events([dict(key='agent:1999999990.000000', who='Grok Bot', at='1999999990.000000',
                                 text='[Grok Bot] Found her 2025 preprint on lattice drift: https://example.invalid/preprint'),
                            dict(key='agent:1999999991.000000', who='Dot', at='1999999991.000000',
                                 text='WANT RESULT ' + RID)])
        out = self.run_email('The preprint matters.\nTO Grok Bot: is the preprint peer reviewed?\nTO Muse: any talk of hers on this?',
                             ask_agent=self.ask_in_thread, mail_evidence=False)
        self.assertEqual(out[0], False); self.assertEqual(self.addressed, ['Grok Bot', 'Muse'])
        kw = self.thought[0][1]
        self.assertIn('Brought by Grok Bot', kw['brought']); self.assertIn('https://example.invalid/preprint', kw['brought'])
        self.assertNotIn('WANT RESULT', kw['brought'])
        # Grok Bot answers; Muse has not yet: still waiting for Muse only
        self.thread_events([dict(key='agent:2000000005.000000', who='Grok Bot', at='2000000005.000000',
                                 text='[Grok Bot] Not yet reviewed; a revised version is under review.'),
                            dict(key='agent:2000000006.000000', who='Dot', at='2000000006.000000',
                                 text='The table uses the preprint numbers.')])
        out = self.run_email(self.fail, ask_agent=self.ask_in_thread, mail_evidence=False)
        self.assertIn("waiting for Muse's answer", out[1]); self.assertNotIn('Grok Bot', out[1])
        said = [(r['agent'], r['role'], r['text']) for r in self.disc('room-want') if r['state'] == 'said']
        self.assertIn(('Grok Bot', 'grok-bot', '[Grok Bot] Not yet reviewed; a revised version is under review.'), said)
        self.assertIn(('Dot', 'dot', 'The table uses the preprint numbers.'), said)
        self.thread_events([dict(key='agent:2000000007.000000', who='Muse', at='2000000007.000000',
                                 text='[Muse] A recorded talk from her lab last spring covers it.')])
        out = self.run_email('Unreviewed, so I ask rather than assert.', ask_agent=self.ask_in_thread, mail_evidence=False)
        self.assertIsInstance(out, str)
        exchange = self.thought[-1][1]['brought'].split('YOUR EXCHANGE WITH THEM')[1]
        for who in ('Grok Bot: [Grok Bot] Not yet', 'Dot: The table', 'Muse: [Muse] A recorded talk'):
            self.assertIn(who, exchange)
        rec, = self.dossier['agent_research']
        self.assertEqual({x['agent'] for x in rec['exchange'] if x['state'] == 'said'}, {'Grok Bot', 'Dot', 'Muse'})

    def test_agents_posting_through_her_account_are_known_by_their_tag_and_the_tag_is_not_kept(self):
        import dot_channel as D
        import want_working_thread as working
        for text, name in (('[Muse] a find', 'Muse'), ('[Grok Bot] a find', 'Grok Bot'), ('[GrokBot] a find', 'Grok Bot'),
                           ('[ grok  bot ]: a find', 'Grok Bot'), ('[GROKBOT] a find', 'Grok Bot'), ('[ muse ] a find', 'Muse'),
                           ('[Dot] a find', 'Dot'), ('[Claude Code] a find', 'Claude Code')):
            m = {'user': 'UGLORIA', 'text': text}
            self.assertEqual(D._who(m, 'USELF', 'UDOT'), 'agent', text); self.assertEqual(D._agent_name(m), name, text)
            self.assertEqual(D._unsigned(text).strip(), 'a find', text)
        for text in ('Good morning', 'I asked [Muse] about it', 'Muse, look at this'):
            self.assertEqual(D._who({'user': 'UGLORIA', 'text': text}, 'USELF', 'UDOT'), 'gloria', text)
            self.assertEqual(D._unsigned(text), text)
        # a tagged row is trusted in a want's thread only when it was written from her own account (authenticated)
        row = dict(who='agent', name='Grok Bot', thread='t', ts='1')
        self.assertTrue(working.trusted(dict(row, agent_authenticated=True)))
        self.assertFalse(working.trusted(dict(row, agent_authenticated=False)))
        self.assertTrue(working.trusted(dict(row, name='Dot', agent_authenticated=True)))
        self.assertFalse(working.trusted(dict(who='gloria', thread='t', ts='1', agent_authenticated=True)))

    def test_each_agent_is_addressed_the_way_it_reaches_the_room(self):
        import dot_channel as D
        self.assertEqual(D.want_mention('Dot', 'UDOT', {}), '<@UDOT> ')
        self.assertEqual(D.want_mention('Muse', 'UDOT', {}), '@Muse ')
        self.assertEqual(D.want_mention('Grok Bot', 'UDOT', {}), '@GrokBot ')
        self.assertEqual(D.want_mention('Grok Bot', 'UDOT', {'grokbot': 'UGROK'}), '<@UGROK> ')
        self.assertIsNone(D.want_mention('Someone', 'UDOT', {}))

    def test_a_line_that_cannot_be_posted_does_not_hold_the_want(self):
        self.room_want()
        def refused(agent, text): raise RuntimeError('working reply refused by send guard')
        out = self.run_email('Fine.\nTO Dot: anything?', ask_agent=refused, mail_evidence=False)
        self.assertIsInstance(out, str)
        self.assertNotIn('asked', [r['state'] for r in self.disc('room-want')])

    def test_the_room_lane_passes_its_thread_asker_to_the_email_step(self):
        self.room_want()
        seen, posted = [], []
        with patch.object(E, 'run', lambda params, text, wid, **kw: seen.append(kw) or (False, 'held for the test')):
            A._email_step(json.loads((self.mem / 'current-wants.json').read_text())[0], {}, {'summary': 's', 'acceptance': 'a'},
                          RID, 'r1', 2000000000.0, Path(WS), None,
                          lambda w, agent, text: posted.append((w['id'], agent, text)) or {'ts': '1'})
        self.assertEqual(seen[0]['lane'], 'want-lane')
        seen[0]['ask_agent']('Grok Bot', 'a question')
        self.assertEqual(posted, [('room-want', 'Grok Bot', 'a question')])

    # -- 3. letter agents: material from their letters, questions ride on his next reply ------------------------
    def letter(self, lid, read_at, body):
        return dict(kind='letter', id=lid, thread_id=lid, **{'from': 'Grok Bot'}, subject='[Grok Bot] Friday: finds',
                    read_at=read_at, body=body)

    def test_a_letter_agents_items_are_brought_material_and_his_question_goes_by_letter(self):
        self.write('current-wants.json', [dict(id='router-want', want=EMAIL_TASK, source='journal')])
        read_at = (datetime.now() - timedelta(hours=2)).isoformat(timespec='seconds')
        mail = [self.letter('L1', read_at, '1. Ada Example lattice drift measurements revisited\n'
                                           'Her synthetic lattice drift paper has a new appendix. https://example.invalid/appendix\n'
                                           '2. A song\nSomething else entirely.')]
        with open(self.mem / 'email-inbox.jsonl', 'w') as f:
            for r in mail: f.write(json.dumps(r) + '\n')
        out = self.run_email('The appendix matters.\nTO Grok Bot: does the appendix give the raw drift?', lane='router',
                             want_id='router-want')
        self.assertEqual(out[0], False); self.assertIn('next letter reply', out[1]); self.assertEqual(self.sent, [])
        a, kw = self.thought[0]
        self.assertIn('Brought by Grok Bot', kw['brought']); self.assertIn('https://example.invalid/appendix', kw['brought'])
        self.assertNotIn('WHAT YOUR MAIL BROUGHT', a[2])            # the letter item is shown once, labelled
        self.assertIn('waiting for Grok Bot', self.run_email(self.fail, lane='router', want_id='router-want')[1])
        text, qs = R.letter_lines('Grok Bot')
        self.assertIn('raw drift', text); self.assertEqual(len(qs), 1)
        self.assertEqual(R.letter_lines('Muse'), ('', []))
        R.letter_sent(qs, 'L1', datetime.now().timestamp())
        self.assertEqual(R.letter_lines('Grok Bot'), ('', []))     # carried once
        later = (datetime.now() + timedelta(minutes=5)).isoformat(timespec='seconds')
        mail.append(self.letter('L2', later, '1. Ada Example lattice drift raw data\nYes, the appendix has the raw drift table.'))
        with open(self.mem / 'email-inbox.jsonl', 'w') as f:
            for r in mail: f.write(json.dumps(r) + '\n')
        with patch.object(E.time, 'time', lambda: datetime.now().timestamp() + 600):
            out = self.run_email('With the raw table, I can ask about the cold runs.', lane='router', want_id='router-want')
        self.assertIsInstance(out, str)
        rows = self.disc('router-want')
        answer = next(r for r in rows if r['state'] == 'answered')
        self.assertEqual(answer['letter'], 'L2'); self.assertIn('raw drift table', answer['text'])
        self.assertEqual(answer['role'], 'grok-bot')

    def test_his_letter_reply_carries_the_queued_question_and_marks_it_asked(self):
        self.write('current-wants.json', [dict(id='router-want', want=EMAIL_TASK, source='journal')])
        R._record('router-want', R._row('vintos', 'queued', 'Grok Bot', 'does the appendix give the raw drift?',
                                        2000000000.0, q='q-1', key='queue:q-1', channel='letter', recipient='Ada Example'))
        now = datetime.now()
        with open(self.mem / 'email-inbox.jsonl', 'w') as f:
            f.write(json.dumps(dict(self.letter('L1', (now - timedelta(hours=1)).isoformat(timespec='seconds'),
                                                '1. Something synthetic\nA find.'), address='me@example.invalid')) + '\n')
        sent = []
        with patch.object(E, 'who_i_am', lambda limit=0: 'You are Vintos.'), \
             patch.object(E, '_promises', lambda *a, **k: []):
            lines = E.reply_letters(think=lambda s, u, n=900: 'Item 1: keep, it bears on my drift question.',
                                    send=lambda args, purpose: sent.append(args) or {}, now=now, bring=lambda *a, **k: None)
        self.assertEqual(len(sent), 1)
        body = E.text_of(sent[0]) if hasattr(E, 'text_of') else json.dumps(sent[0])
        self.assertIn('raw drift', body); self.assertIn('Ada Example', body)
        self.assertTrue(any('carried 1 question' in l for l in lines), lines)
        self.assertEqual(R.questions('router-want')['q-1']['state'], 'asked')

    # -- 4. the router's reflection sees the material too; her board does not mistake it for her ---------------
    def test_the_routers_reflection_seed_and_the_board(self):
        w = self.room_want()
        self.assertIn('Brought by Dot', R.seed_block(w))
        self.assertEqual(R.seed_block(dict(w, want='I want to sit with the drift result')), '')
        disc = {'x': [{'role': 'gloria', 'text': 'yes'}, R._row('dot', 'answered', 'Dot', 'rows 9-14', 1.0, key='a')]}
        self.assertTrue(want_board._gloria_answered('x', disc))

    def test_lane_rules_stand(self):
        # the agent is still told not to draft or send; the router still cannot email a room-owned want
        w = self.room_want()
        self.assertIn('do not draft that email', A.NO_AGENT_EMAIL)
        held = E.run({}, EMAIL_TASK, w['id'], search=no_network, fetch=no_network, send=no_network)
        self.assertIn('bound to the agent room', held[1])


if __name__ == '__main__':
    unittest.main()

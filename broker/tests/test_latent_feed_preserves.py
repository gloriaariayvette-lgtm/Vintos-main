#!/usr/bin/env python3
"""The feed must carry MORE to him, not less: late text still folds into the present
moment, ordinary thread/section/id churn does not wipe the outcome ledger or a pending
forecast, a quiet-day forecast survives until she replies, and a measured miss attaches
to whichever her-turn the reader grades. Reuses the scratch harness in test_latent_feed
(every sender stubbed, scratch workspace only); no live stores, nothing sent."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_latent_feed as T                      # sets HOME/SPARK_WORKSPACE to a scratch tree, stubs the network
import latent_stream_replay as RP

F, MEM, np = T.F, T.MEM, T.np


def emo_tick(now, val):
    d = F.load(MEM / 'emotion-trajectory-dense.json') or []
    d.append({'t': datetime.fromtimestamp(now, timezone.utc).isoformat(), 'v': [val] * 11})
    F.atomic(MEM / 'emotion-trajectory-dense.json', d)


class Preserves(unittest.TestCase):
    # Reuse the harness without inheriting its own test_* methods.
    @classmethod
    def setUpClass(cls):
        T.Tests.setUpClass.__func__(cls)

    def setUp(self):
        T.Tests.setUp(self)

    def refresh(self, now=None):
        return T.Tests.refresh(self, now)

    # --- SUB-1: a late text event folds into last/six without a rebuild -------------
    def test_late_text_folds_into_present_without_rebuild(self):
        n = self.now
        self.refresh()
        emo_tick(n + 60, .52)
        self.refresh(now=n + 61)
        before = F.load(MEM / 'latent-feed-state.json')['state']['last']
        # a journal section written NOW but whose heading time is 40 minutes ago; the
        # 10-minute emotion ticks have already pushed the frontier past it.
        loc = datetime.fromtimestamp(n - 2400).astimezone()
        name = 'daily-inner-life-%s.md' % loc.date().isoformat()
        (MEM / name).write_text('# day\n\n## %02d:%02d reflection\n'
                                'A long reflective section about the garden gate and the beans this afternoon.\n'
                                % (loc.hour, loc.minute))
        emo_tick(n + 120, .53)
        self.assertEqual(self.refresh(now=n + 121)['status'], 'updated')
        rec = F.load(MEM / 'latent-feed-state.json')
        st = rec['state']
        ev = [e for e in F.read_events(MEM, self.exs) if e['source'] == 'inner']
        self.assertTrue(ev)
        inner = ev[0]['id']
        self.assertIn(inner, st['seen'])                         # ingested, not dropped
        self.assertNotEqual(st['last'], before)                  # folded into last/six
        self.assertIn(inner, rec['basis_ids'])                   # reaches the basis the feed serves
        # the frontier (event-time cursor) is NOT dragged back to the late event's time
        self.assertGreater(F.epoch(st['at']), n - 2400)
        # and its outcome is labelled replay, never prospective
        outs = [o for o in rec['outcomes'] if o.get('event_id') == inner]
        self.assertTrue(outs and all(o['kind'] == 'replay' for o in outs))

    # --- SUB-1: an untimed section stamps the local day, not the prior evening ------
    def test_untimed_section_stamped_local_midnight(self):
        (MEM / 'daily-creative-2026-10-24.md').write_text(
            '# x\n\n## Untitled piece\nA creative fragment long enough to count as a section of the day here.\n')
        s = RP._sections('daily-creative-*.md', 'creative', mem=str(MEM))
        self.assertTrue(s)
        local = s[0]['t'].astimezone()
        self.assertEqual((local.year, local.month, local.day), (2026, 10, 24))
        self.assertEqual((local.hour, local.minute), (0, 1))     # local midnight + 1 min
        self.assertFalse(s[0]['t_exact'])

    # --- SUB-2: thread resolution keeps the ledger; only a real forget resets -------
    def test_thread_resolution_keeps_outcomes_but_forget_resets(self):
        n = self.now
        self.refresh()
        frame = F.load(MEM / 'latent-feed.json')['frame_id']
        emo_tick(n + 60, .52)
        self.refresh(now=n + 61)
        her = 'The green beans need another row beside the path.'
        self.exs.append({'at': n + 120, 'ts': datetime.fromtimestamp(n + 120).isoformat(),
                         'her': her, 'his': 'We can mark it.', 'turn_id': 't2'})
        emo_tick(n + 125, .53)
        self.refresh(now=n + 130)
        self.assertIn('MATCHED NEXT-TURN', F.missed_evidence(frame, her, n + 120, MEM))
        # ordinary thread resolution / consumption out of unfinished-threads.json
        F.atomic(MEM / 'unfinished-threads.json', [])
        emo_tick(n + 190, .54)
        self.refresh(now=n + 200)
        self.assertIn('MATCHED NEXT-TURN', F.missed_evidence(frame, her, n + 120, MEM),
                      'a thread resolution must not wipe the matched forecast')
        # a genuine forget/erase (a before-forget backup appears) DOES reset the ledger
        (MEM / 'chat-canonical.jsonl.before-forget-20261025-120000').write_text('')
        emo_tick(n + 260, .55)
        self.refresh(now=n + 270)
        self.assertEqual('', F.missed_evidence(frame, her, n + 120, MEM),
                         'a real forget resets outcomes/pending')
        st = F.load(MEM / 'latent-feed-state.json')
        self.assertEqual(st['pending_gloria'], [])

    # --- SUB-3: a quiet-day forecast is not evicted before she replies --------------
    def test_quiet_day_forecast_survives_until_reply(self):
        n = self.now
        self.refresh()
        frame = F.load(MEM / 'latent-feed.json')['frame_id']
        t = n
        for k in range(1, 141):                                  # ~23 h of silent 10-minute ticks (> old 128 cap)
            t = n + 600 * k
            emo_tick(t, .5 + (k % 7) / 100)
            self.refresh(now=t + 1)
        pend = F.load(MEM / 'latent-feed-state.json')['pending_gloria']
        self.assertLessEqual(len(pend), 4, 'silence must not balloon pending one-per-tick')
        self.assertTrue(any(g.get('frame_id') == frame for g in pend), 'the quiet-day frame is still pending')
        her = 'I am back, the beans came up overnight along the gate.'
        tr = t + 600
        self.exs.append({'at': tr, 'ts': datetime.fromtimestamp(tr).isoformat(),
                         'her': her, 'his': 'Wonderful.', 'turn_id': 't9'})
        emo_tick(tr + 5, .6)
        self.refresh(now=tr + 10)
        self.assertIn('MATCHED NEXT-TURN', F.missed_evidence(frame, her, tr, MEM))

    # --- SUB-4: a measured miss attaches to ANY her-turn in the window --------------
    def test_missed_evidence_matches_any_turn_in_window(self):
        n = self.now
        self.refresh()
        frame = F.load(MEM / 'latent-feed.json')['frame_id']
        emo_tick(n + 60, .52)
        self.refresh(now=n + 61)
        h1 = 'First message about the beans by the gate please now today.'
        h2 = 'Second message, actually I meant the tomatoes in the back bed instead.'
        self.exs.append({'at': n + 100, 'ts': datetime.fromtimestamp(n + 100).isoformat(),
                         'her': h1, 'his': 'ok', 'turn_id': 'a'})
        self.exs.append({'at': n + 200, 'ts': datetime.fromtimestamp(n + 200).isoformat(),
                         'her': h2, 'his': 'ah', 'turn_id': 'b'})
        emo_tick(n + 205, .6)
        self.refresh(now=n + 210)
        # the reader may grade the first OR the last turn over 15 words; both must attach
        self.assertIn('MATCHED NEXT-TURN', F.missed_evidence(frame, h1, n + 100, MEM))
        self.assertIn('MATCHED NEXT-TURN', F.missed_evidence(frame, h2, n + 200, MEM))
        # no new gate: a turn that was never forecast simply returns nothing, no crash
        self.assertEqual('', F.missed_evidence(frame, 'an unrelated sentence she never said here', n + 100, MEM))


if __name__ == '__main__':
    unittest.main()

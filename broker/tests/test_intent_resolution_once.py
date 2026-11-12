"""Round five (10 November): a resolver's result lands only on the revision of the row it read, and each effect of
an accepted verdict happens once - two resolvers at once, a process that dies around a write, a write that fails.
Synthetic data, scratch stores and fixture providers only: no model is asked, no socket opened, nothing sent."""
import contextlib
import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import threading
import unittest
from unittest.mock import Mock, patch

import test_intent_fields_fix as fixtures
from test_intent_fields_fix import E, DD, A, TEXT_A, HER, GLORIA, REPO, store_guard, ago

AXES = ('field', 'gloria', 'self')


class ResolutionOnce(unittest.TestCase):
    @contextlib.contextmanager
    def home(self):
        """One scratch household (the fields-fix fixture): every store under a temporary home, the judge a stub."""
        f = fixtures.IntentFieldsFix(methodName='runTest'); f.setUp()
        try:
            for path in (E.LEDGER, E.SELECT_LOG, DD.PRESS, DD._receipts_path()):
                self.assertTrue(Path(path).is_relative_to(f.home), path)
            self.assertIsInstance(f.spawn, Mock)
            f.stack.enter_context(patch.dict(E.RESOLUTION_DROPPED))
            yield f
        finally:
            f.doCleanups()

    def setUp(self):
        stack = contextlib.ExitStack(); self.addCleanup(stack.close)
        self.f = stack.enter_context(self.home())

    # ---- fixtures -------------------------------------------------------------------------------------
    def race(self, slow, meanwhile, fast='YES', resolve=None):
        """One resolver (thread 'slow-judge') is at its judge while `meanwhile` runs; then its judge answers `slow`."""
        started, release, errors = threading.Event(), threading.Event(), []
        def judge(*a, **k):
            if threading.current_thread().name == 'slow-judge':
                started.set()
                if not release.wait(10): raise AssertionError('fixture release timed out')
                if slow == 'HELD': E._held_why.set('judge_unavailable')
                return slow
            return fast
        def slow_one():
            try: (resolve or (lambda: E.resolve_previous(HER)))()
            except BaseException as exc: errors.append(exc)
        def sol(packet):    # her axis is Sol's (12 November): the same race, in the rubric's answer
            v = judge()
            return {'verdict': v if v in ('YES', 'PARTIAL', 'NO') else 'NOT_JUDGEABLE', 'reason': 'fixture',
                    'adherence': 'delivered', 'status': 'ok'}
        with patch.object(E, '_judge_realized', side_effect=judge), patch.object(E, '_sol_judge', side_effect=sol):
            worker = threading.Thread(target=slow_one, name='slow-judge'); worker.start()
            try:
                self.assertTrue(started.wait(10)); out = meanwhile()
            finally:
                release.set(); worker.join(10)
        self.assertFalse(worker.is_alive()); self.assertEqual(errors, [])
        return out

    def child(self, run):
        """`run` in a forked process (forked before any lock is taken: it inherits none); its exit code."""
        pid = os.fork()
        if pid == 0:
            try:
                signal.alarm(60); run(); os._exit(9)
            finally:
                os._exit(10)
        return os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1])

    def dies(self, dest, after=True, run=None):
        """A resolver process that dies (exit 7) just after - or just before - its first `dest` effect is made."""
        real = E._apply_effect
        def apply(row, fx):
            if fx.get('dest') == dest and not after: os._exit(7)
            out = real(row, fx)
            if fx.get('dest') == dest and after: os._exit(7)
            return out
        def go():
            with patch.object(E, '_apply_effect', apply): (run or (lambda: E.resolve_previous(HER)))()
        return self.child(go)

    def missed(self, f):
        f.press(**{A: f.prow(TEXT_A, 2.0)}); f.delivered(addresses=A); f.verdict = 'NO'

    def pending(self, f):
        return [p['key'] for p in f.rows()[-1].get('effects_pending', [])]

    def nudges(self, f):
        sent = f.mem / 'valence.sent'
        E._nudge_valence.side_effect = lambda amount: sent.open('a').write('%r\n' % amount)
        return lambda: len(sent.read_text().splitlines()) if sent.exists() else 0

    # ---- two resolvers at once (Chat's reproduction, 10 November) -----------------------------------------
    def test_slow_held_result_does_not_erase_a_settled_row_and_is_dropped_aloud(self):
        f = self.f; f.delivered(gloria=copy.deepcopy(GLORIA))
        settled = self.race('HELD', lambda: (E.resolve_previous(HER), copy.deepcopy(f.rows()[-1]))[1])
        self.assertEqual(settled['realized'], dict.fromkeys(AXES, 'YES'))
        row = f.rows()[-1]
        self.assertEqual((row['realized'], row['resolution_rev']), (settled['realized'], settled['resolution_rev']))
        self.assertNotIn('held_attempts', row); self.assertNotIn('held_reason', row)
        self.assertEqual((row['resolution_dropped']['n'], row['resolution_dropped']['reason']), (1, 'stale_revision'))
        self.assertEqual(E.RESOLUTION_DROPPED, {'stale_revision': 1, 'settled_axis': 0, 'row_gone': 0})
        self.assertEqual(Path(E.SELECT_LOG).read_text().count('resolution DROPPED (stale_revision): row %s' % row['intent_id']), 1)
        # only the result that landed published anything
        self.assertEqual((sys.modules['outcome_join'].record.call_count, E._nudge_valence.call_count), (1, 3))

    def test_conflicting_late_verdict_publishes_no_effect(self):
        f = self.f; f.press(**{A: f.prow(TEXT_A, 2.0)}); f.delivered(gloria=copy.deepcopy(GLORIA), addresses=A)
        relieved = self.race('NO', lambda: (E.resolve_previous(HER), copy.deepcopy(f.pressure(A)))[1])
        self.assertEqual((relieved['weight'], relieved['count']), (1.0, 2))     # the YES that landed took weight off, once
        self.assertEqual(f.pressure(A), relieved)                              # the late NO weighed nothing
        self.assertFalse((f.mem / '.intent-required-consideration.json').exists())
        self.assertEqual(f.rows()[-1]['realized'], dict.fromkeys(AXES, 'YES'))
        self.assertEqual(f.rows()[-1]['resolution_dropped']['reason'], 'stale_revision')
        self.assertEqual((sys.modules['outcome_join'].record.call_count, E._nudge_valence.call_count), (1, 3))

    def test_held_then_settled_progress_is_never_taken_for_a_retry(self):
        f = self.f; f.press(**{A: f.prow(TEXT_A, 2.0)}); f.delivered(addresses=A)
        f.verdicts = ['HELD', 'HELD']; E.resolve_previous(HER)
        row = f.rows()[-1]
        self.assertEqual((row['realized']['field'], row['held_attempts']), (None, 1)); self.assertEqual(f.pressure(A)['weight'], 2.0)
        f.verdicts = ['YES', 'YES']; E.resolve_previous(HER)
        row = f.rows()[-1]
        self.assertEqual((row['realized'], row['held_attempts']), ({'field': 'YES', 'gloria': 'NOT_DECLARED', 'self': 'YES'}, 1))
        keys = [c.args[3]['effect_key'] for c in sys.modules['outcome_join'].record.call_args_list]
        self.assertEqual(keys, [row['intent_id'] + ':outcome:r2', row['intent_id'] + ':outcome:r3'])   # each accepted pass its own
        self.assertEqual((f.pressure(A)['weight'], E._nudge_valence.call_count), (1.0, 2))
        E.resolve_previous(HER); E.resolve_previous(HER)                       # settled: nothing again
        self.assertEqual((f.pressure(A)['weight'], E._nudge_valence.call_count, len(keys)), (1.0, 2, 2))
        self.assertNotIn('effects_pending', f.rows()[-1])

    def test_distinct_rows_do_not_wait_on_each_other(self):
        f = self.f; f.delivered(); f.delivered()
        first, second = (copy.deepcopy(r) for r in f.rows()[-2:])
        done = self.race('NO', lambda: (E._resolve_row(copy.deepcopy(second), HER), copy.deepcopy(f.rows()[-1]))[1],
                         resolve=lambda: E._resolve_row(copy.deepcopy(first), HER))
        self.assertEqual(done['realized']['field'], 'YES')                     # settled while the other row's judge was out
        rows = f.rows()[-2:]
        self.assertEqual([r['realized']['field'] for r in rows], ['NO', 'YES'])   # ... and that one landed after it
        self.assertFalse(any('resolution_dropped' in r for r in rows)); self.assertEqual(E.RESOLUTION_DROPPED['stale_revision'], 0)

    # ---- a process that dies between an effect and its settling: each destination ------------------------
    def test_pressure_feedback_happens_once_whenever_the_resolver_dies(self):
        for after in (False, True):
            with self.subTest(after=after), self.home() as f:
                self.missed(f)
                self.assertEqual(self.dies('pressure', after), 7)
                row = f.rows()[-1]
                self.assertEqual(row['realized']['field'], 'NO')               # the verdict landed before any effect
                self.assertIn(row['intent_id'] + ':pressure:field:NO', self.pending(f))
                self.assertEqual(f.pressure(A)['count'], 3 if after else 2)
                E.resolve_previous(HER); E.resolve_previous(HER)               # the next resolvers finish it, once
                self.assertEqual((f.pressure(A)['count'], f.pressure(A)['weight']), (3, 3.0))
                self.assertEqual(f.pressure(A)['receipts'], [row['intent_id'] + ':pressure:field:NO'])
                self.assertEqual(self.pending(f), [])

    def test_required_consideration_is_asked_once_whenever_the_resolver_dies(self):
        for after in (False, True):
            with self.subTest(after=after), self.home() as f:
                self.missed(f); marker = f.mem / '.intent-required-consideration.json'
                self.assertEqual(self.dies('required_consideration', after), 7)
                key = f.rows()[-1]['intent_id'] + ':required_consideration:field:NO'
                self.assertEqual(marker.exists(), after)
                if after:   # her next turn consumes it before any resolver runs again
                    t = f.select(resolve=False)
                    self.assertEqual((t['primary_shown'], t['primary_required']), (A, True)); self.assertFalse(marker.exists())
                    self.assertEqual(DD.marker_receipts(), [key])
                E.resolve_previous(HER); E.resolve_previous(HER)
                self.assertEqual(marker.exists(), not after)                   # never asked a second time
                if not after: self.assertEqual(json.loads(marker.read_text())['effect_key'], key)
                self.assertEqual(self.pending(f), [])

    def real_join(self, f):
        spec = importlib.util.spec_from_file_location('outcome_join', REPO / 'scripts' / 'outcome_join.py')
        oj = importlib.util.module_from_spec(spec); spec.loader.exec_module(oj)
        for key, value in (('MEMORY', str(f.mem)), ('JOINS', str(f.mem / 'outcome-joins.jsonl'))):
            f.stack.enter_context(patch.object(oj, key, value))
        self.assertTrue(Path(oj.JOINS).is_relative_to(f.home))
        f.stack.enter_context(patch.dict(sys.modules, {'outcome_join': oj}))
        return oj

    def test_outcome_receipt_is_joined_once_whenever_the_resolver_dies(self):
        for after in (False, True):
            with self.subTest(after=after), self.home() as f:
                oj = self.real_join(f); f.delivered(); f.verdict = 'YES'
                self.assertEqual(self.dies('outcome', after), 7)
                E.resolve_previous(HER); E.resolve_previous(HER)
                lines = [json.loads(ln) for ln in Path(oj.JOINS).read_text().splitlines()]
                self.assertEqual([(ln['kind'], ln['detail']['effect_key'], ln['detail']['axis']) for ln in lines],
                                 [('intent', f.rows()[-1]['intent_id'] + ':outcome:r2', 'field/gloria/self')])
                self.assertEqual(self.pending(f), [])

    def test_valence_is_sent_at_most_once_and_says_so(self):
        # The emotion socket keeps no record: a nudge is taken off the row and then sent. A process that dies after
        # sending is not followed by a second; one that dies between the two loses that nudge.
        for after, sent in ((True, 2), (False, 1)):
            with self.subTest(after=after), self.home() as f:
                count = self.nudges(f); f.delivered(); f.verdict = 'YES'      # field and self: two nudges
                self.assertEqual(self.dies('valence', after), 7)
                E.resolve_previous(HER); E.resolve_previous(HER)
                self.assertEqual(count(), sent)
                self.assertEqual(self.pending(f), [])

    def test_his_reply_is_observed_once_for_a_row(self):
        f = self.f; seen = f.mem / 'observed'; f.delivered()
        observe = sys.modules['self_difference'].observe_self
        def dying(reply): seen.open('a').write('x\n'); os._exit(7)
        observe.side_effect = dying
        self.assertEqual(self.child(lambda: E.resolve_previous(HER)), 7)
        observe.side_effect = lambda reply: seen.open('a').write('x\n')
        f.verdicts = ['HELD', 'HELD']; E.resolve_previous(HER); E.resolve_previous(HER)
        self.assertEqual(len(seen.read_text().splitlines()), 1)
        self.assertIn(f.rows()[-1]['intent_id'] + ':observe_self', f.rows()[-1]['effects_done'])

    def test_a_landed_row_seeds_once_whenever_the_feeder_dies(self):
        f = self.f; LT, asked = f.lead_trials()
        at = ago(0, 30)
        Path(E.LEDGER).write_text(json.dumps([{'intent_id': 'landed', 'status': 'delivered', 'timestamp': at, 'delivered_at': at,
                                               'reply': 'a synthetic reply', 'target': {'goal': 'goal of landed', 'enactment': 'a synthetic move'},
                                               'realized': {'field': 'YES', 'gloria': 'NOT_DECLARED', 'self': 'NOT_DECLARED'}}]))
        real = LT.save
        def save(path, data):
            real(path, data)
            if path == LT.SEEDS: os._exit(7)                                   # the seed written, the cursor not
        def feed():
            with patch.object(LT, 'save', save), contextlib.redirect_stdout(open(os.devnull, 'w')): LT.seed_from_intents()
        self.assertEqual(self.child(feed), 7)
        self.assertFalse(Path(LT.SEEDSTATE).exists())
        with contextlib.redirect_stdout(open(os.devnull, 'w')): LT.seed_from_intents(); LT.seed_from_intents()
        seeds = json.loads(Path(LT.SEEDS).read_text())
        self.assertEqual(([s['intent'] for s in seeds], asked), (['landed'], []))   # found, not asked for again

    # ---- what fails is not stranded ----------------------------------------------------------------------
    def test_a_failed_effect_waits_on_its_row_and_is_made_once_later(self):
        f = self.f; self.missed(f)
        with patch.object(DD, 'field_verdict', side_effect=OSError('fixture: the pressure store cannot be written')):
            E.resolve_previous(HER)
        self.assertEqual((f.rows()[-1]['realized']['field'], f.pressure(A)['count']), ('NO', 2))
        self.assertEqual(self.pending(f), [f.rows()[-1]['intent_id'] + ':pressure:field:NO'])
        self.assertIn('turn-state write FAILED at field_verdict: OSError', Path(E.SELECT_LOG).read_text())
        E.resolve_previous(HER); E.resolve_previous(HER)
        self.assertEqual((f.pressure(A)['count'], self.pending(f)), (3, []))

    def test_an_effect_that_never_happens_is_said_each_time_and_given_up_at_the_cap(self):
        # review, round five: a pressure store that never takes the write, and an outcome join that cannot be
        # opened (it used to fail without a word), are each said on every miss and stop being tried at the cap
        f = self.f; self.missed(f)
        with patch.object(E, 'EFFECT_TRIES_MAX', 3), patch.dict(E.EFFECTS_GIVEN_UP, n=0), \
                patch.object(DD, 'field_verdict', side_effect=OSError('fixture: the pressure store cannot be written')), \
                patch.object(E, '_record_outcome', side_effect=OSError('fixture: the join cannot be opened')):
            E.resolve_previous(HER)                                                 # one try each: drained when the pass lands
            row = f.rows()[-1]
            self.assertEqual(sorted((p['key'].split(':', 1)[1], p.get('tries')) for p in row['effects_pending']),
                             [('outcome:r2', 1), ('pressure:field:NO', 1)])
            for _ in range(4): E.resolve_previous('')
            row = f.rows()[-1]; log = Path(E.SELECT_LOG).read_text()
            self.assertNotIn('effects_pending', row)
            self.assertEqual(sorted(k.split(':', 1)[1] for k in row['effects_given_up']), ['outcome:r2', 'pressure:field:NO'])
            self.assertEqual(log.count('effect NOT DONE at outcome'), 2); self.assertEqual(log.count('effect GIVEN UP at outcome'), 1)
            self.assertEqual(log.count('effect NOT DONE at pressure'), 2); self.assertEqual(log.count('effect GIVEN UP at pressure'), 1)
            self.assertEqual(E.EFFECTS_GIVEN_UP['n'], 2)
            n = log.count('effect ')
            E.resolve_previous(''); E.resolve_previous('')
            self.assertEqual(Path(E.SELECT_LOG).read_text().count('effect '), n)          # given up: not tried again
        self.assertEqual(f.pressure(A)['count'], 2)
        self.assertEqual(f.rows()[-1]['realized']['field'], 'NO')                   # the verdict stands; only its effects were lost, aloud

    def test_a_judge_that_raises_or_a_process_that_dies_at_it_strands_nothing(self):
        f = self.f; f.delivered()
        with patch.object(E, '_judge_realized', side_effect=RuntimeError('fixture')), self.assertRaises(RuntimeError):
            E.resolve_previous(HER)
        self.assertEqual(f.rows()[-1]['realized'], dict.fromkeys(AXES))         # nothing of the failed pass was written
        # a resolver at its judge holds no lock: while it waits there the ledger and the turn state are free, and
        # when it dies there its row is resolved by the next one
        at_r, at_w = os.pipe(); go_r, go_w = os.pipe()
        def at_the_judge():
            def judge(*a, **k): os.write(at_w, b'1'); os.read(go_r, 1); os._exit(7)
            with patch.object(E, '_judge_realized', side_effect=judge): E.resolve_previous(HER)
        pid = os.fork()
        if pid == 0:
            try:
                signal.alarm(60); at_the_judge()
            finally:
                os._exit(10)
        os.read(at_r, 1); took = []
        def take():
            with store_guard.transaction(E.LEDGER), store_guard.turn_state(DD.PRESS): took.append(True)
        t = threading.Thread(target=take, daemon=True); t.start(); t.join(10)
        os.write(go_w, b'1'); self.assertEqual(os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1]), 7)
        for fd in (at_r, at_w, go_r, go_w): os.close(fd)
        self.assertEqual(took, [True])
        f.verdict = 'YES'; E.resolve_previous(HER)
        self.assertEqual(f.rows()[-1]['realized'], {'field': 'YES', 'gloria': 'NOT_DECLARED', 'self': 'YES'})


if __name__ == '__main__':
    unittest.main()

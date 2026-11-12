"""Judge evidence boundaries: synthetic inputs, scratch stores and fixture providers only."""
import copy
from pathlib import Path
import unittest

import test_intent_fields_fix as fixtures


class IntentEvidenceBoundary(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.IntentFieldsFix(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.assertTrue(Path(fixtures.E.LEDGER).is_relative_to(self.fixture.home))
        self.assertIsInstance(self.fixture.spawn, fixtures.Mock)

    def test_uncertain_or_compound_provider_text_is_no_verdict(self):
        for raw in ('UNKNOWN', 'NOT SURE', 'NO VERDICT', 'YES OR NO', 'NOT YES',
                    'PARTIALLY', 'HELD OFF', '{"verdict":"YES"}'):
            with self.subTest(raw=raw):
                self.fixture.verdict = raw
                self.assertEqual(fixtures.E._judge_realized(copy.deepcopy(fixtures.TARGET),
                                                          'Synthetic action.', 'Synthetic response.'), 'HELD')
                self.assertEqual(fixtures.E._held_why.get(), 'judge_no_verdict')

    def test_single_verdict_tokens_remain_supported(self):
        for verdict in ('YES', 'PARTIAL', 'NO', 'HELD'):
            for suffix in ('', '.', '!'):
                with self.subTest(verdict=verdict, suffix=suffix):
                    self.fixture.verdict = ' \n' + verdict.lower() + suffix + '\n '
                    self.assertEqual(fixtures.E._judge_realized(copy.deepcopy(fixtures.TARGET),
                                                              'Synthetic action.', 'Synthetic response.'), verdict)

    def test_unknown_judge_text_never_changes_landing_denominators(self):
        self.fixture.delivered(gloria=copy.deepcopy(fixtures.GLORIA))
        self.fixture.verdict = 'UNKNOWN'
        for _ in range(3):
            fixtures.E.resolve_previous('GLORIA (now): Synthetic follow-up.')
        row = self.fixture.rows()[-1]
        # her axis is Sol's (12 November): an answer outside the rubric is NOT_JUDGEABLE(error) at once, never HELD
        self.assertEqual(row['realized'], {'field': 'HELD', 'gloria': 'NOT_JUDGEABLE', 'self': 'HELD'})
        self.assertEqual(row['gloria_judge']['reason'], 'error')
        self.assertEqual(set(row['held_reason'].values()), {'judge_no_verdict'})
        self.assertTrue(all(h['n'] == 0 for h in fixtures.PV._axis_history().values()))

    def test_invalid_verdict_never_repressures_an_addressed_goal(self):
        self.fixture.press(**{fixtures.A: self.fixture.prow(fixtures.TEXT_A, 2.0)})
        self.fixture.delivered(addresses=fixtures.A)
        before = self.fixture.pressure(fixtures.A)
        self.fixture.verdict = 'NO VERDICT'
        fixtures.E.resolve_previous('GLORIA (now): Synthetic follow-up.')
        self.assertIsNone(self.fixture.rows()[-1]['realized']['field'])
        self.assertEqual(self.fixture.pressure(fixtures.A), before)
        self.assertFalse((self.fixture.mem / '.intent-required-consideration.json').exists())

    def test_only_the_current_human_input_is_follow_up_evidence(self):
        self.fixture.delivered(observation_window='her_next_reply', evidence_type='her_response',
                               gloria=copy.deepcopy(fixtures.GLORIA), mine={})
        fixtures.E.resolve_previous('GLORIA: HISTORY_HUMAN_TOKEN\nVINTOS: HISTORY_ASSISTANT_TOKEN\n'
                                    'GLORIA (now): CURRENT_RESPONSE_TOKEN')
        self.assertEqual(len(self.fixture.judge_calls), 2)
        for call in self.fixture.judge_calls:
            prompt = call['messages'][1]['content']
            self.assertIn('CURRENT_RESPONSE_TOKEN', prompt)
            self.assertNotIn('HISTORY_HUMAN_TOKEN', prompt)
            self.assertNotIn('HISTORY_ASSISTANT_TOKEN', prompt)

    def test_my_move_evidence_does_not_include_a_later_human_response(self):
        self.fixture.delivered()
        self.fixture.verdict = 'NO'
        fixtures.E.resolve_previous('GLORIA (now): LATER_RESPONSE_TOKEN')
        self.assertEqual(len(self.fixture.judge_calls), 2)
        for call in self.fixture.judge_calls:
            prompt = call['messages'][1]['content']
            self.assertIn('Here are both, and the tradeoff between them.', prompt)
            self.assertNotIn('LATER_RESPONSE_TOKEN', prompt)
        self.assertEqual(self.fixture.rows()[-1]['realized'],
                         {'field': 'NO', 'gloria': 'NOT_DECLARED', 'self': 'NO'})

    def test_response_axis_keeps_its_current_response_while_self_uses_its_move(self):
        self.fixture.delivered(gloria=copy.deepcopy(fixtures.GLORIA))
        fixtures.E.resolve_previous('GLORIA (now): CURRENT_RESPONSE_TOKEN')
        self.assertEqual(len(self.fixture.judge_calls), 3)
        prompts = [call['messages'][1]['content'] for call in self.fixture.judge_calls]
        self.assertNotIn('CURRENT_RESPONSE_TOKEN', prompts[0])
        self.assertIn('CURRENT_RESPONSE_TOKEN', prompts[1])
        self.assertNotIn('CURRENT_RESPONSE_TOKEN', prompts[2])


if __name__ == '__main__':
    unittest.main()

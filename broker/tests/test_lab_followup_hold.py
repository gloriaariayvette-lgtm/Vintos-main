#!/usr/bin/env python3
"""A held follow-up step does not take every pass (Gloria, 19 October).

The fallback that picks up an unfinished step from one of his own earlier reviews walked the notebook newest-first
and returned the first one it found, without asking whether that step was already on hold. The held step was
returned, the hold refused it, and the pass ended in a wait; the next pass found the same newest row and waited
again — one GSDMD follow-up, 96 waits between 09:14 and 15:10 UTC on 18 October, every four minutes for six hours.
It now walks on to the next unfinished step. The hold itself is untouched and still holds.

Offline: the scratch workspace and refused sockets come from test_lab_query_perimeter."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lab_query_perimeter import Perimeter, C, forbidden
import copy, hashlib, json, unittest
from unittest.mock import patch

HELD = ('What are the specific residue identities and side-chain orientations of the β1-β2 loop in the '
        'human GSDMD pore (PDB 6N9O) that contact the membrane?')
OTHER = 'Which residues line the HMOX1 heme pocket?'
STEP = {'question': 'What is the GSDMD pore architecture?', 'uniprot_query': 'gene:gsdmd AND organism_id:9606',
        'source_query': None, 'browse_lane': 'protein', 'line_id': None}
STEP2 = {'question': 'What is the HMOX1 fold?', 'uniprot_query': 'gene:hmox1 AND organism_id:9606',
         'source_query': None, 'browse_lane': 'protein', 'line_id': None}


class FollowUpHold(Perimeter):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(C, '_browse', side_effect=forbidden))
        self.stack.enter_context(patch.object(C, '_ask', side_effect=forbidden))
        # The fallback's own repair step is what is under test; keep it honest and cheap.
        self.stack.enter_context(patch.object(C, '_strategy_change', side_effect=lambda inquiry, repeats: dict(
            inquiry, strategy_resolution={'reason': 'offline_fixture'})))
        import lab_repeats
        self.repeats = lab_repeats
        self.stack.enter_context(patch.object(lab_repeats, 'repeat', return_value=''))

    def reflection(self, step, next_question):
        """One of his own earlier reviews, with a step it did not finish."""
        C._append(C.NOTEBOOK, {'kind': 'reflection', 'inquiry': dict(step), 'next_question': next_question})

    def hold(self, question, step):
        """That step's follow-up, refused for lack of evidence and waiting on changed evidence."""
        inquiry = dict(step, question=question, requested_question=step['question'])
        held = dict(inquiry, refused='coverage deferred: evidence exceeds the context budget',
                    evidence_status='insufficient', coverage_deferred=True,
                    planning_evidence=C._planning_evidence(inquiry))
        C._append(C.NOTEBOOK, {'kind': 'reflection', 'inquiry': held, 'coverage_deferred': True})
        return held

    def work(self):
        return C._next_evidence_work({}, self.repeats, {'subjects': [], 'questions': [], 'count': 0}, None)

    def test_an_unheld_step_is_still_picked_up(self):
        self.reflection(STEP, HELD)
        got = self.work()
        self.assertIsNotNone(got)
        self.assertEqual(got['question'], HELD)
        self.assertEqual(got['strategy_resolution']['reason'], 'continued_another_self_authored_unresolved_step')

    def test_a_held_step_is_passed_over_for_the_next_one(self):
        self.reflection(STEP2, OTHER)          # older, and not held
        self.reflection(STEP, HELD)            # newest, and held
        self.hold(HELD, STEP)
        self.assertIsNotNone(C._held_question(dict(STEP, question=HELD)))
        got = self.work()
        self.assertIsNotNone(got, 'the older unfinished step should have been picked up')
        self.assertEqual(got['question'], OTHER)

    def test_the_hold_is_not_touched_or_released(self):
        self.reflection(STEP, HELD)
        self.hold(HELD, STEP)
        before = Path(C.NOTEBOOK).read_bytes()
        self.work()
        self.assertIsNotNone(C._held_question(dict(STEP, question=HELD)), 'the hold must still hold')
        self.assertEqual(Path(C.NOTEBOOK).read_bytes(), before, 'reading for work must write nothing')

    def test_every_step_held_returns_nothing_rather_than_a_held_step(self):
        self.reflection(STEP, HELD)
        self.reflection(STEP2, OTHER)
        self.hold(HELD, STEP)
        self.hold(OTHER, STEP2)
        self.assertIsNone(self.work())

    def test_the_wait_loop_does_not_repeat_across_passes(self):
        # What actually happened: the same newest held row, pass after pass. Each pass must now find other work.
        self.reflection(STEP2, OTHER)
        self.reflection(STEP, HELD)
        self.hold(HELD, STEP)
        self.assertEqual([(self.work() or {}).get('question') for _ in range(3)], [OTHER] * 3)


if __name__ == '__main__':
    unittest.main()

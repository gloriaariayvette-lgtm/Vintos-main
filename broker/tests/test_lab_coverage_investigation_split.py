#!/usr/bin/env python3
"""A finished investigation's outputs are graded in parts, never deferred whole for their size (26 October).

An investigation's review carries every step's output as `additional_source.records`, one level in. The deeper split
opened only top-level lists, so that list was a single unit: four reviews of 11- and 12-step investigations that day
(73-156 KB of evidence; about 50 KB fits one part) were deferred whole, though no single step was over 16 KB, and not
one investigation in a month was judged.

Offline: the scratch workspace and refused sockets come from test_lab_query_perimeter. The checker is a stub that
records what it was sent; nothing is shortened, every address still resolves, and no request is over the budget."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lab_query_perimeter import Perimeter, C
import json, unittest
from unittest.mock import patch

BUDGET, RATIO = 24576, 0.4231


def summary(step, n):
    """One NCBI-like summary row of about 2-4 KB: many named fields, prose among them."""
    return {'uid': '%d%03d' % (step, n),
            'summary': dict({'title': 'Phage genome %d-%d, complete sequence with a reverse transcriptase '
                                      'locus beside a CRISPR array' % (step, n),
                             'organism': 'Escherichia phage %d' % n,
                             'extra': 'gb|MN%06d|; isolate notes ' % (step * 100 + n) + 'w' * (900 + 300 * n)},
                            **{'field%02d' % k: 'value %d of row %d' % (k, n) for k in range(40)})}


def step_output(step, rows=4):
    return {'step': 'S-%04d' % step, 'question': 'search step %d' % step,
            'result': {'candidate': {'assessment': {'k%02d' % k: 'assessment note %d' % k for k in range(17)},
                                     'route': 'ncbi', 'id': 'c%d' % step, 'note': 'n' * 600},
                       'receipt': {'source': 'ncbi', 'receipt_id': 'r%063d' % step,
                                   'records': [summary(step, n) for n in range(rows)]}}}


def observations(steps=12):
    return {'records': [], 'LITERATURE': [], 'prior_validated_evidence': [],
            'additional_source': {'receipt': {'source': 'investigation',
                                              'records': [step_output(s) for s in range(steps)]}}}


INQUIRY = {'question': 'Which bacteriophage genomes carry a reverse transcriptase beside a CRISPR array, and '
                       'what families do those reverse transcriptases belong to?', 'line_id': None}


class InvestigationSplit(Perimeter):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(C, 'config', return_value=dict(
            C.DEFAULTS, enabled=True, evo2_enabled=False,
            coverage_context_tokens=BUDGET, coverage_tokens_per_byte=RATIO)))
        self.sent = []

        def ask(system, prompt, max_tokens=500, temperature=0.75):
            self.sent.append((system, prompt, max_tokens))
            if 'evidence-coverage checker' in system:
                return json.dumps({'answered': False, 'missing': ['families not named'], 'supports': []})
            return json.dumps({'sufficient': False, 'missing': ['x'], 'rationale': 'x'})
        self.stack.enter_context(patch.object(C, '_ask', side_effect=ask))

    def evidence(self, request):
        return json.loads(request[1].partition('\nEVIDENCE:\n')[2])

    def test_the_shape_is_the_one_that_was_deferred(self):
        prepared = C._coverage_request(INQUIRY, observations())
        self.assertFalse(C._coverage_budget(prepared[3])['fits'], 'the whole review must be over the budget')
        for out in observations()['additional_source']['receipt']['records']:
            self.assertLess(len(json.dumps(out)), 16000, 'no single step is anywhere near a part')

    def test_a_fourteen_step_investigation_is_graded_in_parts(self):
        for steps in (11, 12, 14):
            prepared = C._coverage_request(INQUIRY, observations(steps))
            parts = C._coverage_parts(prepared)
            self.assertIsNotNone(parts, '%d steps were not split' % steps)
            self.assertTrue(2 <= len(parts) <= C.COVERAGE_SPLIT_MAX_PARTS)
            for part in parts:
                self.assertTrue(C._coverage_budget(part)['fits'])

    def test_it_reaches_a_verdict_and_every_call_fits(self):
        result = C._coverage_check(INQUIRY, observations(14))
        self.assertFalse(result.get('coverage_deferred'), result.get('missing_evidence'))
        self.assertIs(result['answered'], False)
        self.assertGreaterEqual(result.get('split_parts') or 0, 2)
        self.assertTrue(self.sent)
        for system, prompt, out in self.sent:
            self.assertTrue(C._coverage_budget((system, prompt, out))['fits'], 'a call went over the budget')
        self.assertFalse(list(Path(C.ROOT).glob('coverage-deferred/*.json')), 'nothing was deferred')

    def test_every_step_and_row_reaches_exactly_one_part_whole(self):
        prepared = C._coverage_request(INQUIRY, observations(14))
        whole = self.evidence(prepared[3])['additional_source']['records']
        parts = [self.evidence(p) for p in C._coverage_parts(prepared)]
        for step in whole:
            for row in step['result']['receipt']['records']:
                holding = [p for p in parts for s in p['additional_source']['records']
                           if row in (((s.get('result') or {}).get('receipt') or {}).get('records') or [])]
                self.assertEqual(len(holding), 1, 'a summary row must arrive whole, in exactly one part')

    def test_the_addresses_in_the_parts_are_the_whole_evidence_addresses(self):
        prepared = C._coverage_request(INQUIRY, observations(14))
        _ev, strings, addresses, _req = prepared
        seen = set()
        def walk(node):
            if isinstance(node, dict):
                if set(node) == {'address', 'text'}:
                    self.assertIn(node['address'], addresses)
                    self.assertEqual(strings[addresses[node['address']]], node['text'], 'a leaf was changed')
                    seen.add(node['address']); return
                for v in node.values(): walk(v)
            elif isinstance(node, list):
                for v in node: walk(v)
        for part in C._coverage_parts(prepared):
            walk(self.evidence(part))
        self.assertEqual(seen, set(addresses), 'every addressed leaf reaches some part, none is dropped')

    def test_no_part_carries_an_empty_list_for_steps_held_elsewhere(self):
        prepared = C._coverage_request(INQUIRY, observations(14))
        for part in C._coverage_parts(prepared):
            records = self.evidence(part)['additional_source']['records']
            self.assertTrue(records)
            for s in records:
                self.assertNotEqual(((s.get('result') or {}).get('receipt') or {}).get('records', None), [])

    def test_one_text_too_long_for_a_part_is_deferred_and_named_with_its_size(self):
        obs = observations(3)
        obs['additional_source']['receipt']['records'][1]['result']['receipt']['records'][0]['summary']['extra'] = \
            'z' * 90000
        result = C._coverage_check(INQUIRY, obs)
        self.assertTrue(result.get('coverage_deferred'))
        self.assertIn('one piece is larger than a part', result['missing_evidence'])
        self.assertIn('summary.extra is', result['missing_evidence'])
        self.assertGreater(result['coverage_split']['piece_bytes'], result['coverage_split']['part_spare_bytes'])
        self.assertFalse(self.sent, 'nothing over the budget is sent, and nothing is cut to make it fit')

    def test_a_numeric_table_is_never_divided_and_is_named_down_to_itself(self):
        obs = observations(3)
        table = {format(i, '012b'): 1.0 / (i + 7) for i in range(4096)}
        obs['additional_source']['receipt']['records'][1]['result'] = {
            'experiment_result': {'run': {'result': {'distribution': {'exact_full_state_probabilities': table,
                                                                      'shots': 4096}}}}}
        result = C._coverage_check(INQUIRY, obs)
        self.assertTrue(result.get('coverage_deferred'))
        self.assertTrue(result['coverage_split']['piece'].endswith('distribution.exact_full_state_probabilities'),
                        result['coverage_split'])
        self.assertFalse(self.sent, 'no part is handed some of a distribution')

    def test_the_split_with_fewer_parts_is_used(self):
        obs = observations(2)
        obs['LITERATURE'] = [{'pmid': str(n), 'abstract': 'article %d ' % n + 'a' * 1500} for n in range(40)]
        prepared = C._coverage_request(INQUIRY, obs)
        shallow, deep = C._coverage_shallow_parts(prepared), C._coverage_deep_parts(prepared)
        self.assertIsNotNone(shallow); self.assertIsNotNone(deep)
        self.assertLess(len(deep), len(shallow), 'the shallow split repeats the step results in every part')
        self.assertEqual(len(C._coverage_parts(prepared)), len(deep))

    def test_parts_are_filled_before_another_is_opened(self):
        # Step results of about 20 and 35 KB in turn, against about 50 KB a part: closing a part at the first unit
        # that did not fit gave every step a part of its own.
        obs = observations(0)
        obs['additional_source']['receipt']['records'] = [
            {'step': 'S-%04d' % n, 'question': 'step %d' % n,
             'result': {'value': 'step %d says ' % n + ('s' if n % 2 == 0 else 'b') * (20000 if n % 2 == 0 else 35000)}}
            for n in range(8)]
        prepared = C._coverage_request(INQUIRY, obs)
        parts = C._coverage_parts(prepared)
        self.assertIsNotNone(parts)
        self.assertLessEqual(len(parts), 6, [len(p[1]) for p in parts])


if __name__ == '__main__':
    unittest.main()

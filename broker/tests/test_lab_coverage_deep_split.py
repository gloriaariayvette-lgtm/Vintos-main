#!/usr/bin/env python3
"""Evidence whose weight is not in a list is still graded in parts (Gloria, 19 October: "let's grade in parts").

The shallow split makes every top-level list item its own unit and shares everything else. One HMOX1 review on
18 October was 83 KB, of which 65.6 KB was a single atlas `additional_source` - a dict of two 32 KB track records,
not a list - so the shared part alone was over the 24,576-token budget and the split gave up. The whole review was
deferred and never graded, while the five list items beside it came to under 15 KB.

Offline: the scratch workspace and refused sockets come from test_lab_query_perimeter. No model is called; only the
splitter's arithmetic and the shape of its parts are under test."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lab_query_perimeter import Perimeter, C
import json, unittest
from unittest.mock import patch

HEAD = 'SCOPE'
SYSTEM = 'you are a checker'


def body(evidence):
    return HEAD + '\nEVIDENCE:\n' + json.dumps(evidence, ensure_ascii=False, separators=(',', ':'))


def prepared(evidence, out=1100):
    """A prepared request of this shape; the strings/addresses maps are not read by the splitter."""
    return ({}, {}, {}, (SYSTEM, body(evidence), out))


def track(seed, rows=167):
    """A track record of about 32 KB, as the atlas instrument returns it."""
    return {'var': {'columns': ['chrom', 'pos', 'ref', 'alt', 'score', 'track', 'cell_type', 'quantile',
                                'raw', 'normalized', 'note'],
                    'data': [['chr22', 35381080 + i, 'C', 'A', round(0.1 + i / 1000.0, 4), 'ATAC-%s' % seed,
                              'K562-erythroleukemia', round(i / 167.0, 6), round(i * 1.37, 5),
                              round(i / 12.0, 6), 'window %d of the accessible region' % i] for i in range(rows)],
                    'index': 'variant-%s' % seed},
            'variants': ['chr22:%d:C>%s' % (35381080 + i, 'AGT'[i % 3]) for i in range(96)],
            'obs': {'columns': ['variant'], 'data': [['chr22:%d:C>A' % (35381080 + i)] for i in range(96)]},
            'quantiles': 'q' * 140, 'scores': 's' * 140, 'tracks_kept': 3}


def atlas():
    """The HMOX1 review's shape: the weight inside one non-list value, small list items beside it."""
    return {'additional_source': {'source': 'atlas', 'receipt_id': 'r' * 64, 'instrument_result': None,
                                  'records': {'ATAC': track('atac'), 'ATAC_ACTIVE': track('active')}},
            'atlas_analysis': {},
            'records': [{'accession': 'P09601', 'protein_name': 'Heme oxygenase 1', 'function': 'f' * 3000}],
            'STRUCTURE': [{'entry_id': '1N45', 'method': 'X-ray', 'resolution': 2.08, 'notes': 'n' * 7000}],
            'LITERATURE': [{'pmid': '11021806', 'title': 't' * 1200}, {'pmid': '12191828', 'title': 'u' * 700}],
            'embedding_coverage': [{'model': 'esm2', 'residues': 288}]}


class DeepSplit(Perimeter):
    def setUp(self):
        super().setUp()
        # Her own budget on Aegis, and the ratio measured there.
        self.stack.enter_context(patch.object(C, 'config', return_value=dict(
            C.DEFAULTS, enabled=True, evo2_enabled=False,
            coverage_context_tokens=24576, coverage_tokens_per_byte=0.4231)))

    def size(self, value):
        return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())

    def test_the_shape_is_the_one_that_was_deferred(self):
        tree = atlas()
        self.assertGreater(self.size(tree['additional_source']), 50000)   # 65.6 KB in the real review
        self.assertFalse(C._coverage_budget((SYSTEM, body(tree), 1100))['fits'])
        self.assertIsNone(C._coverage_shallow_parts(prepared(tree)), 'the shallow split cannot divide this')

    def test_it_is_now_graded_in_parts(self):
        parts = C._coverage_parts(prepared(atlas()))
        self.assertIsNotNone(parts, 'the deeper split should have divided it')
        self.assertGreaterEqual(len(parts), 2)
        self.assertLessEqual(len(parts), C.COVERAGE_SPLIT_MAX_PARTS)
        for part in parts:
            self.assertTrue(C._coverage_budget(part)['fits'], part[1][:120])

    def test_each_table_is_carried_whole_in_exactly_one_part(self):
        # A part may hold only some of the evidence, but never half a table: a row is never divided from its table.
        tree = atlas()
        parts = [json.loads(p[1].partition('\nEVIDENCE:\n')[2]) for p in C._coverage_parts(prepared(tree))]
        for name in ('ATAC', 'ATAC_ACTIVE'):
            whole = tree['additional_source']['records'][name]['var']['data']
            carried = [(((part.get('additional_source') or {}).get('records') or {}).get(name) or {})
                       .get('var', {}).get('data') for part in parts]
            self.assertEqual([c for c in carried if c is not None], [whole],
                             '%s: its table must arrive whole, in one part' % name)

    def test_no_part_shows_an_empty_field_where_another_part_holds_it(self):
        # The checker is told an empty or absent source field is missing evidence, so a part must not leave a null or
        # an empty list where another part carries the piece. A null that is in the evidence itself stays as it is.
        tree = atlas()
        def original(path):
            node = tree
            for step in path:
                if not isinstance(node, dict) or step not in node: return '<<absent>>'
                node = node[step]
            return node
        for part in [json.loads(p[1].partition('\nEVIDENCE:\n')[2]) for p in C._coverage_parts(prepared(tree))]:
            def walk(node, path=()):
                if isinstance(node, dict):
                    for k, v in node.items():
                        if v is None or v == [] or v == {}:
                            self.assertEqual(v, original(path + (k,)),
                                             'placeholder at %s that the evidence does not have' % '.'.join(path + (k,)))
                        walk(v, path + (k,))
            walk(part)

    def test_every_piece_reaches_a_part_whole(self):
        # A small value is shared into every part, as context the checker reads a quote against; a large one is
        # carried by exactly one. Either way each arrives whole, and nothing is left out of all the parts.
        tree = atlas()
        parts = [json.loads(p[1].partition('\nEVIDENCE:\n')[2]) for p in C._coverage_parts(prepared(tree))]
        for key in ('records', 'STRUCTURE', 'LITERATURE', 'embedding_coverage'):
            for item in tree[key]:
                holding = [part for part in parts if item in (part.get(key) or [])]
                self.assertTrue(holding, '%s: an item reached no part' % key)
                self.assertIn(len(holding), (1, len(parts)),
                              '%s: an item is in some parts but not all' % key)

    def test_the_shared_skeleton_keeps_its_small_values_in_every_part(self):
        parts = [json.loads(p[1].partition('\nEVIDENCE:\n')[2]) for p in C._coverage_parts(prepared(atlas()))]
        for part in parts:
            self.assertEqual((part.get('additional_source') or {}).get('source'), 'atlas')
            self.assertEqual((part.get('additional_source') or {}).get('receipt_id'), 'r' * 64)

    def test_evidence_that_fits_is_not_split_at_all(self):
        small = {'records': [{'accession': 'P09601', 'function': 'short'}]}
        self.assertTrue(C._coverage_budget((SYSTEM, body(small), 1100))['fits'])
        self.assertIsNone(C._coverage_parts(prepared(small)))

    def test_one_piece_too_large_to_carry_is_still_deferred(self):
        # A single record over the budget cannot be graded in parts, and must not be shortened to fit.
        huge = {'additional_source': {'source': 'atlas', 'records': {'ONE': {'blob': 'x' * 200000}}},
                'records': [{'accession': 'P09601'}]}
        self.assertIsNone(C._coverage_parts(prepared(huge)))

    def test_nothing_is_written_while_splitting(self):
        before = sorted(Path(C.ROOT).rglob('*'))
        C._coverage_parts(prepared(atlas()))
        self.assertEqual(sorted(Path(C.ROOT).rglob('*')), before)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Scratch-only IMG/VR locus-join contracts. No live network, no host stores.

Fixtures are shaped like the real release records, checked against the installed
release on 25 October 2026:

  nucleotide header  >IMGVR_UViG_<taxon>_<n>|<taxon>|<scaffold>|<start>-<end>
  protein header     >IMGVR_UViG_<taxon>_<n>|<taxon>|<provider gene id>

The trailing range on a nucleotide header is the provirus's span on its host
scaffold, not a gene coordinate, and the contig served under that header is the
UViG itself. A test here asserts the join never reports scaffold coordinates.
"""
import gzip
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SCRATCH = tempfile.TemporaryDirectory(prefix='imgvr-loci-test-')
os.environ['HOME'] = SCRATCH.name
os.environ['VINTOS_IMGVR_ROOT'] = str(Path(SCRATCH.name)/'imgvr')
sys.path.insert(0, str(REPO/'scripts'))
import imgvr_store as store
import imgvr_loci as loci
import lab_sources
import lab_genome_mining

# one codon per residue, so a fixture protein has an exact nucleotide encoding
BACK = {}
for codon, residue in loci.CODONS.items():
    BACK.setdefault(residue, codon)

HEADERS = ['UVIG', 'Taxon_oid', 'Scaffold_oid', "Coordinates ('whole' if the UViG is the entire contig)",
           'Ecosystem classification', 'vOTU', 'Length', 'Topology', 'geNomad score', 'Confidence',
           'Estimated completeness', 'Estimated contamination', 'MIUViG quality',
           'Gene content (total genes;cds;tRNA;geNomad marker)', 'Taxonomic classification',
           'Taxonomic classification method', 'Host taxonomy prediction', 'Host prediction method',
           'Sequence origin (doi)']

RT_LIKE = 'MKLTSQAVRHLLDNQGVYSAISRFSDGFVYGLGFWMAAAVVSAAGAMVSFLLMAGYVSLDLGQPHRVAAALPQIVSPPPP'
ACCESSORY = 'MSRFSDGKVYTLGFWMAAQVVSAAGAMVSFLLMAGYVSLDLGQPHRVAAALPQNNDPAIKKRMYQVCKDEFGHIKLMNPQ'
FAR_GENE = 'MPLVTWLIGMAWPIVRKVLVELGISFITYEGVSAALDSLLSSAQASYQAGPSVVLAYLAIAGVPTGFGIIAGALSARVARF'
ABSENT = 'MQWERTYIPASDFGHKLCVBNMQWERTYIPASDFGHKLCVBNMQWERTYIPASDFGHKLCVBNMQWERTYIPASDFGHKLC'
SPACER = 'TCAGGATCCTTAGCATCGATCGTTAACGGCATTAAGCTTGCA'


def encode(protein):
    return ''.join(BACK[residue] for residue in protein)


def revcomp(dna):
    return loci.reverse_complement(dna)


class Tests(unittest.TestCase):
    def setUp(self):
        self.network = patch('urllib.request.urlopen',
                             side_effect=AssertionError('live network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)
        # isolation, asserted in the suite so a later edit cannot quietly undo it
        self.assertTrue(str(store.ROOT).startswith(SCRATCH.name))
        self.assertTrue(str(loci.ROOT).startswith(SCRATCH.name))
        self.assertNotIn('.vintos/workspace', str(loci.ROOT))
        self.assertNotIn('.vintos/data', str(loci.ROOT))
        self.root = Path(SCRATCH.name)/'imgvr'
        self.root.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- fixtures

    def build(self, name, contigs, rows):
        """A throwaway metadata index and nucleotide FASTA for these contigs."""
        metadata = self.root/(name + '.tsv')
        metadata.write_text('\t'.join(HEADERS) + '\n'
                            + ''.join('\t'.join(row) + '\n' for row in rows))
        fasta = self.root/(name + '.fna')
        fasta.write_text(''.join('>' + header + '\n' + dna + '\n' for header, dna in contigs))
        db = self.root/(name + '.sqlite3')
        db.unlink(missing_ok=True)
        connection = sqlite3.connect(db)
        store._build_metadata(connection, metadata)
        store._build_fasta_index(connection, fasta)
        connection.commit()
        connection.close()
        return db, fasta

    def metadata_row(self, uvig, *, votu='vOTU_00000001', length='900', topology='Provirus',
                     ecosystem='Environmental;Aquatic;Marine;Oceanic', completeness='92.20'):
        return [uvig, '2189573022', '2189573099', '381-5974', ecosystem, votu, length, topology,
                '0.9261', 'High-confidence', completeness, '0.00', 'High-quality', '10;10;0;5',
                'r__Duplodnaviria', 'geNomad', 'd__Bacteria;p__Proteobacteria', 'Isolate taxonomy',
                'fixture doi']

    def single_locus(self):
        """One contig: a forward anchor, a reverse neighbour, and a distant gene.

        The header carries a scaffold range (|381-5974) the join must never use.
        """
        uvig = 'IMGVR_UViG_2189573022_000041'
        header = uvig + '|2189573022|PRSSG2_Sequence0000002743|381-5974'
        anchor = encode(RT_LIKE)
        neighbour = revcomp(encode(ACCESSORY))
        far = encode(FAR_GENE)
        dna = (SPACER + anchor + SPACER + neighbour + SPACER * 4 + far + SPACER)
        db, fasta = self.build('single', [(header, dna)],
                               [self.metadata_row(uvig, length=str(len(dna)))])
        return uvig, header, dna, db, fasta

    # ------------------------------------------------------- step 1: inventory

    def test_inventory_records_the_release_and_that_no_gene_map_exists(self):
        uvig, header, dna, db, fasta = self.single_locus()
        (self.root/'provider-manifest.json').write_text(json.dumps({
            'release': store.RELEASE,
            'files': [{'file_name': 'single.fna', 'file_size': fasta.stat().st_size,
                       'sha256': 'f' * 64}]}))
        found = loci.inventory(root=self.root, db=db, nucleotide=fasta,
                               proteins=self.root/'absent.faa.gz',
                               manifest=self.root/'provider-manifest.json')
        self.assertEqual(found['release'], store.RELEASE)
        self.assertFalse(found['gene_map_available'])
        self.assertEqual(found['gene_map_reason'], loci.GENE_MAP_ABSENT)
        self.assertEqual(found['annotation_source'], 'translated_match')
        self.assertIn('not_scaffold_provirus_range', found['coordinate_convention'])
        self.assertEqual(found['counts']['uvig_records'], 1)
        self.assertEqual(found['counts']['indexed_segments'], 1)
        self.assertIsNone(found['protein_record_count'])
        self.assertFalse(found['protein_fasta_present'])
        names = {row['file_name'] for row in found['files']}
        self.assertIn('single.fna', names)
        row = next(x for x in found['files'] if x['file_name'] == 'single.fna')
        self.assertEqual(row['local_sha256_at_transfer'], 'f' * 64)

    # ------------------------------------------------------ step 2: the join

    def test_forward_match_is_one_based_inclusive_on_the_contig_as_served(self):
        uvig, header, dna, db, fasta = self.single_locus()
        result = loci.join_locus({'uvig': uvig, 'sequence': RT_LIKE, 'protein_id': 'PRSSG2_00147660'},
                                 db=db, nucleotide=fasta)
        record = result['records'][0]
        self.assertTrue(record['joined'])
        self.assertEqual(record['strand'], '+')
        self.assertEqual(record['translated_match'], 'exact')
        self.assertEqual(record['start'], len(SPACER) + 1)
        self.assertEqual(record['end'], len(SPACER) + len(RT_LIKE) * 3)
        self.assertEqual(record['target_protein_id'], 'PRSSG2_00147660')
        self.assertEqual(record['annotation_source'], 'translated_match')
        self.assertEqual(record['segment'], header)
        self.assertEqual(record['contig_length'], len(dna))
        # the coordinates are on the served contig, never the scaffold range in the header
        self.assertLess(record['end'], len(dna) + 1)
        self.assertNotEqual(record['start'], 381)
        self.assertTrue(dna[record['start']-1:record['end']] == encode(RT_LIKE))

    def test_reverse_strand_match_reports_contig_coordinates_and_strand(self):
        uvig, header, dna, db, fasta = self.single_locus()
        record = loci.join_locus({'uvig': uvig, 'sequence': ACCESSORY},
                                 db=db, nucleotide=fasta)['records'][0]
        self.assertTrue(record['joined'])
        self.assertEqual(record['strand'], '-')
        expected_start = len(SPACER) + len(RT_LIKE) * 3 + len(SPACER) + 1
        self.assertEqual(record['start'], expected_start)
        self.assertEqual(record['end'], expected_start + len(ACCESSORY) * 3 - 1)
        self.assertEqual(revcomp(dna[record['start']-1:record['end']]), encode(ACCESSORY))

    def test_an_annotated_methionine_over_an_alternative_start_still_joins(self):
        uvig = 'IMGVR_UViG_2189573022_000042'
        header = uvig + '|2189573022|PRSSG2_Sequence0000002744'
        # GTG start: the contig translates V, the release annotates M
        coding = 'GTG' + encode(RT_LIKE[1:])
        dna = SPACER + coding + SPACER
        db, fasta = self.build('alt', [(header, dna)],
                               [self.metadata_row(uvig, length=str(len(dna)))])
        record = loci.join_locus({'uvig': uvig, 'sequence': RT_LIKE},
                                 db=db, nucleotide=fasta)['records'][0]
        self.assertTrue(record['joined'])
        self.assertEqual(record['translated_match'], 'alternative_start_codon')
        self.assertEqual(record['start'], len(SPACER) + 1)
        self.assertEqual(record['end'], len(SPACER) + len(RT_LIKE) * 3)
        self.assertEqual(dna[record['start']-1:record['start']+2], 'GTG')

    def test_a_duplicated_protein_stays_unjoined_as_ambiguous(self):
        uvig = 'IMGVR_UViG_2189573022_000043'
        header = uvig + '|2189573022|PRSSG2_Sequence0000002745'
        dna = SPACER + encode(RT_LIKE) + SPACER * 3 + encode(RT_LIKE) + SPACER
        db, fasta = self.build('dup', [(header, dna)],
                               [self.metadata_row(uvig, length=str(len(dna)))])
        record = loci.join_locus({'uvig': uvig, 'sequence': RT_LIKE},
                                 db=db, nucleotide=fasta)['records'][0]
        self.assertFalse(record['joined'])
        self.assertEqual(record['reason'], 'ambiguous_translated_match')
        self.assertEqual(record['match_count'], 2)
        self.assertNotIn('start', record)
        self.assertEqual(record['amino_acid_sha256'], loci._sha256(RT_LIKE))

    def test_a_protein_from_the_wrong_release_or_a_mismatch_stays_unjoined(self):
        uvig, header, dna, db, fasta = self.single_locus()
        record = loci.join_locus({'uvig': uvig, 'sequence': ABSENT},
                                 db=db, nucleotide=fasta)['records'][0]
        self.assertFalse(record['joined'])
        self.assertEqual(record['reason'], 'no_exact_translated_match')
        self.assertEqual(record['match_count'], 0)
        # one residue changed is a mismatch, not a near-enough join
        changed = RT_LIKE[:-1] + ('A' if RT_LIKE[-1] != 'A' else 'C')
        other = loci.join_locus({'uvig': uvig, 'sequence': changed},
                                db=db, nucleotide=fasta)['records'][0]
        self.assertFalse(other['joined'])

    def test_a_uvig_outside_the_index_is_refused_before_any_sequence_is_read(self):
        uvig, header, dna, db, fasta = self.single_locus()
        record = loci.join_locus({'uvig': 'IMGVR_UViG_9999999999_000001', 'sequence': RT_LIKE},
                                 db=db, nucleotide=fasta)['records'][0]
        self.assertFalse(record['joined'])
        self.assertEqual(record['reason'], 'uvig_absent_from_nucleotide_index')

    def test_a_contig_over_the_size_cap_is_refused_rather_than_translated(self):
        uvig, header, dna, db, fasta = self.single_locus()
        record = loci.join_locus({'uvig': uvig, 'sequence': RT_LIKE},
                                 db=db, nucleotide=fasta, size_cap=10)['records'][0]
        self.assertFalse(record['joined'])
        self.assertEqual(record['reason'], 'contig_over_size_cap')

    def test_bad_input_is_refused_and_no_path_or_pattern_is_accepted(self):
        uvig, header, dna, db, fasta = self.single_locus()
        for bad in ({'uvig': '../secret', 'sequence': RT_LIKE},
                    {'uvig': uvig, 'sequence': 'MK'},
                    {'uvig': uvig, 'sequence': 'ACGT' * 600},
                    {'uvig': uvig, 'sequence': RT_LIKE, 'protein_id': 'has spaces'}):
            with self.assertRaises(ValueError):
                loci.join_locus(bad, db=db, nucleotide=fasta)

    # ------------------------------------------- multi-segment identity preserved

    def multi(self):
        uvig = 'IMGVR_UViG_GVMAG-M-2140918012-1_000001'
        first = uvig + '|2140918012|contig1'
        second = uvig + '|2140918012|contig2'
        one = SPACER + encode(RT_LIKE) + SPACER
        two = SPACER * 2 + encode(ACCESSORY) + SPACER
        db, fasta = self.build('multi', [(first, one), (second, two)],
                               [self.metadata_row(uvig, length=str(len(one) + len(two)))])
        return uvig, first, second, one, two, db, fasta

    def test_a_multi_segment_uvig_will_not_join_without_its_segment(self):
        uvig, first, second, one, two, db, fasta = self.multi()
        record = loci.join_locus({'uvig': uvig, 'sequence': RT_LIKE},
                                 db=db, nucleotide=fasta)['records'][0]
        self.assertFalse(record['joined'])
        self.assertEqual(record['reason'], 'segment_required_for_multi_segment_uvig')
        self.assertEqual(record['segment_count'], 2)
        self.assertEqual(sorted(record['segments']), sorted([first, second]))

    def test_a_named_segment_joins_and_keeps_the_segment_in_the_record(self):
        uvig, first, second, one, two, db, fasta = self.multi()
        record = loci.join_locus({'uvig': uvig, 'sequence': ACCESSORY, 'segment': second},
                                 db=db, nucleotide=fasta)['records'][0]
        self.assertTrue(record['joined'])
        self.assertEqual(record['segment'], second)
        self.assertEqual(record['start'], len(SPACER) * 2 + 1)
        # the same protein is not on the other segment, so naming it keeps them distinct
        other = loci.join_locus({'uvig': uvig, 'sequence': ACCESSORY, 'segment': first},
                                db=db, nucleotide=fasta)['records'][0]
        self.assertFalse(other['joined'])
        with self.assertRaises(ValueError):
            loci.join_locus({'uvig': uvig, 'sequence': ACCESSORY, 'segment': 'not_a_segment'},
                            db=db, nucleotide=fasta)

    # --------------------------------------------- step 3: bounded neighborhood

    def test_the_neighborhood_places_neighbours_with_orientation_and_a_window_hash(self):
        uvig, header, dna, db, fasta = self.single_locus()
        supplied = [{'protein_id': 'g_accessory', 'sequence': ACCESSORY},
                    {'protein_id': 'g_far', 'sequence': FAR_GENE},
                    {'protein_id': 'g_absent', 'sequence': ABSENT}]
        record = loci.neighborhood({'uvig': uvig, 'sequence': RT_LIKE, 'protein_id': 'g_anchor',
                                    'proteins': supplied, 'window': 400},
                                   db=db, nucleotide=fasta)['records'][0]
        self.assertTrue(record['anchor']['joined'])
        placed = {row['target_protein_id']: row for row in record['neighbors']}
        self.assertIn('g_accessory', placed)
        self.assertEqual(placed['g_accessory']['orientation'], 'opposite')
        self.assertFalse(placed['g_accessory']['same_strand_as_anchor'])
        self.assertEqual(placed['g_accessory']['distance_to_anchor'], len(SPACER))
        # the window is bounded, so the distant gene is outside it and simply absent
        self.assertNotIn('g_far', placed)
        self.assertEqual([row['reason'] for row in record['unplaced_proteins']],
                         ['no_exact_translated_match'])
        self.assertEqual(record['unplaced_count'], 1)
        self.assertEqual(len(record['window_sha256']), 64)
        self.assertIn('not an absent gene', record['missingness'])
        self.assertEqual(record['window_sha256'],
                         loci._sha256(dna[record['window_start']-1:record['window_end']]))

    def test_a_wider_window_reaches_the_distant_gene_and_marks_contig_edges(self):
        uvig, header, dna, db, fasta = self.single_locus()
        record = loci.neighborhood({'uvig': uvig, 'sequence': RT_LIKE,
                                    'proteins': [{'protein_id': 'g_far', 'sequence': FAR_GENE}],
                                    'window': 20000},
                                   db=db, nucleotide=fasta)['records'][0]
        self.assertEqual([row['target_protein_id'] for row in record['neighbors']], ['g_far'])
        self.assertEqual(record['window_start'], 1)
        self.assertEqual(record['window_end'], len(dna))
        self.assertTrue(record['window_truncated_at_contig_start'])
        self.assertTrue(record['window_truncated_at_contig_end'])

    def test_changing_a_supplied_protein_changes_the_neighborhood_digest(self):
        uvig, header, dna, db, fasta = self.single_locus()

        def digest(proteins):
            return loci.neighborhood({'uvig': uvig, 'sequence': RT_LIKE, 'proteins': proteins,
                                      'window': 20000},
                                     db=db, nucleotide=fasta)['records'][0]['neighborhood_digest']

        first = digest([{'protein_id': 'g_accessory', 'sequence': ACCESSORY}])
        again = digest([{'protein_id': 'g_accessory', 'sequence': ACCESSORY}])
        more = digest([{'protein_id': 'g_accessory', 'sequence': ACCESSORY},
                       {'protein_id': 'g_far', 'sequence': FAR_GENE}])
        self.assertEqual(first, again)
        self.assertNotEqual(first, more)

    def test_the_neighborhood_refuses_an_unjoined_anchor(self):
        uvig, header, dna, db, fasta = self.single_locus()
        result = loci.neighborhood({'uvig': uvig, 'sequence': ABSENT,
                                    'proteins': [{'protein_id': 'g', 'sequence': ACCESSORY}]},
                                   db=db, nucleotide=fasta)
        self.assertEqual(result['coverage'], 'neighborhood_refused_unjoined_anchor')
        self.assertFalse(result['records'][0]['joined'])
        self.assertNotIn('neighbors', result['records'][0])

    def test_a_multi_segment_neighborhood_keeps_the_segment_safeguard(self):
        uvig, first, second, one, two, db, fasta = self.multi()
        result = loci.neighborhood({'uvig': uvig, 'sequence': RT_LIKE, 'proteins': []},
                                   db=db, nucleotide=fasta)
        self.assertEqual(result['coverage'], 'neighborhood_refused_unjoined_anchor')
        self.assertEqual(result['records'][0]['reason'], 'segment_required_for_multi_segment_uvig')
        named = loci.neighborhood({'uvig': uvig, 'sequence': RT_LIKE, 'segment': first,
                                   'proteins': [{'protein_id': 'g_accessory', 'sequence': ACCESSORY}]},
                                  db=db, nucleotide=fasta)['records'][0]
        self.assertEqual(named['segment'], first)
        # the accessory gene is on the other contig, so it is unplaced here, not relocated
        self.assertEqual(named['neighbors'], [])
        self.assertEqual(named['unplaced_count'], 1)

    def test_the_window_sequence_route_is_bounded_and_hashes_what_it_returns(self):
        uvig, header, dna, db, fasta = self.single_locus()
        window = loci.window_sequence({'uvig': uvig, 'start': 10, 'end': 209},
                                      db=db, nucleotide=fasta)
        self.assertEqual(window['sequence'], dna[9:209])
        self.assertEqual(window['window_sha256'], loci._sha256(dna[9:209]))
        for bad in ({'uvig': uvig, 'start': 0, 'end': 10},
                    {'uvig': uvig, 'start': 1, 'end': loci.REPEAT_WINDOW_CAP + 1},
                    {'uvig': uvig, 'start': 1, 'end': len(dna) + 1}):
            with self.assertRaises(ValueError):
                loci.window_sequence(bad, db=db, nucleotide=fasta)

    # -------------------------------------------------- step 4: frozen cohort

    def cohort_index(self):
        rows = []
        contigs = []
        for index in range(10):
            uvig = 'IMGVR_UViG_210000000%d_000001' % index
            # three copies of one vOTU: near-identical genomes must not count three times
            votu = 'vOTU_00000001' if index < 3 else 'vOTU_0000000%d' % (index + 1)
            rows.append(self.metadata_row(uvig, votu=votu, length=str(5000 + index * 10)))
            contigs.append((uvig + '|2100000000|contig', SPACER + encode(RT_LIKE) + SPACER))
        for index in range(6):
            uvig = 'IMGVR_UViG_220000000%d_000001' % index
            rows.append(self.metadata_row(uvig, votu='vOTU_0000010%d' % index,
                                          length=str(5000 + index * 10)))
            contigs.append((uvig + '|2200000000|contig', SPACER + encode(FAR_GENE) + SPACER))
        return self.build('cohort', contigs, rows)

    def test_same_votu_copies_cannot_inflate_the_independent_count(self):
        db, fasta = self.cohort_index()
        candidates = ['IMGVR_UViG_210000000%d_000001' % index for index in range(10)]
        record = loci.freeze_cohort({'uvigs': candidates, 'pilot_size': 2, 'holdout_size': 5,
                                     'selection_rule': 'repeat-bearing RT neighborhoods, one per vOTU',
                                     'eligible_population': 'the fixture high-confidence subset',
                                     'backgrounds_per_case': 0}, db=db)['records'][0]
        self.assertTrue(record['frozen'])
        members = record['pilot'] + record['holdout']
        self.assertEqual(len(members), 7)
        self.assertEqual(len(set(members)), 7)
        self.assertEqual(record['same_votu_copies_removed'], 2)
        self.assertEqual(len(set(record['pilot']) & set(record['holdout'])), 0)
        self.assertIn('does not establish independent viral groups', record['relatedness_not_removed'])

    def test_the_cohort_cap_is_twenty_four_and_the_split_is_declared_in_advance(self):
        db, fasta = self.cohort_index()
        candidates = ['IMGVR_UViG_210000000%d_000001' % index for index in range(10)]
        with self.assertRaisesRegex(ValueError, '24'):
            loci.freeze_cohort({'uvigs': candidates, 'pilot_size': 6, 'holdout_size': 19,
                                'selection_rule': 'repeat-bearing RT neighborhoods, one per vOTU',
                                'eligible_population': 'the fixture high-confidence subset'}, db=db)
        for bad in ({'uvigs': candidates, 'selection_rule': 'short', 'eligible_population': 'the fixture subset'},
                    {'uvigs': [], 'selection_rule': 'a rule long enough to pass the check',
                     'eligible_population': 'the fixture subset'}):
            with self.assertRaises(ValueError):
                loci.freeze_cohort(bad, db=db)

    def test_too_few_independent_groups_is_reported_not_relaxed(self):
        db, fasta = self.cohort_index()
        record = loci.freeze_cohort({'uvigs': ['IMGVR_UViG_210000000%d_000001' % index for index in range(3)],
                                     'pilot_size': 2, 'holdout_size': 4,
                                     'selection_rule': 'repeat-bearing RT neighborhoods, one per vOTU',
                                     'eligible_population': 'the fixture high-confidence subset'},
                                    db=db)['records'][0]
        self.assertFalse(record['frozen'])
        self.assertEqual(record['reason'], 'too_few_independent_votu_representatives')
        self.assertEqual(record['representatives_available'], 1)
        self.assertIn('rather than relaxing it', record['sampling_limitation'])

    def test_matched_backgrounds_come_from_other_votus_and_the_digest_binds_them(self):
        db, fasta = self.cohort_index()
        spec = {'uvigs': ['IMGVR_UViG_220000000%d_000001' % index for index in range(6)],
                'pilot_size': 2, 'holdout_size': 3,
                'selection_rule': 'repeat-bearing RT neighborhoods, one per vOTU',
                'eligible_population': 'the fixture high-confidence subset',
                'backgrounds_per_case': 1}
        record = loci.freeze_cohort(spec, db=db)['records'][0]
        self.assertTrue(record['frozen'])
        members = set(record['pilot'] + record['holdout'])
        for case, chosen in record['matched_backgrounds'].items():
            for background in chosen:
                self.assertNotIn(background, members)
        self.assertIn('length_band_2000', record['matched_on'])
        again = loci.freeze_cohort(spec, db=db)['records'][0]
        self.assertEqual(record['cohort_digest'], again['cohort_digest'])
        changed = loci.freeze_cohort(dict(spec, selection_rule=spec['selection_rule'] + ' and repeats'),
                                     db=db)['records'][0]
        self.assertNotEqual(record['cohort_digest'], changed['cohort_digest'])

    def test_an_absent_uvig_is_recorded_rather_than_silently_dropped(self):
        db, fasta = self.cohort_index()
        record = loci.freeze_cohort({'uvigs': ['IMGVR_UViG_220000000%d_000001' % index for index in range(6)]
                                     + ['IMGVR_UViG_9999999999_000001'],
                                     'pilot_size': 2, 'holdout_size': 3,
                                     'selection_rule': 'repeat-bearing RT neighborhoods, one per vOTU',
                                     'eligible_population': 'the fixture high-confidence subset',
                                     'backgrounds_per_case': 0}, db=db)['records'][0]
        self.assertEqual(record['absent_from_metadata_index'], ['IMGVR_UViG_9999999999_000001'])

    # ------------------------------------------- step 5 (part): a shuffle null

    def test_a_planted_array_beats_its_shuffles_and_ordinary_sequence_does_not(self):
        unit = 'GATTACAGGTCA'
        planted = ''.join(unit + 'ACGTTGCACTGAAGGCTTACCGTAAGCTTAGCCATGACTTGCAATTGCCGG'
                          for _ in range(6))[:1200]
        result = loci.repeat_null(planted, trials=12, seed=7)
        self.assertGreater(result['observed_candidate_count'], 0)
        self.assertLessEqual(result['null_fraction_max_copies_at_least_observed'], 0.5)
        self.assertIn('not_a_biological_significance_test', result['truth_status'])
        same = loci.repeat_null(planted, trials=12, seed=7)
        self.assertEqual(result, same)
        with self.assertRaises(ValueError):
            loci.repeat_null(planted, trials=0)

    # ------------------------------- a bounded cohort protein pass, no live file

    def test_the_cohort_protein_pass_keeps_only_the_named_uvigs(self):
        wanted = 'IMGVR_UViG_2189573022_000041'
        other = 'IMGVR_UViG_2189573022_000099'
        text = ''.join([
            '>' + wanted + '|2189573022|PRSSG2_00147660\n' + RT_LIKE + '\n',
            '>' + other + '|2189573022|PRSSG2_00147680\n' + ACCESSORY + '\n',
            '>' + wanted + '|2189573022|PRSSG2_00147710\n' + FAR_GENE + '\n',
        ])
        path = self.root/'proteins.faa.gz'
        with gzip.open(path, 'wt') as handle:
            handle.write(text)
        result = loci.cohort_proteins([wanted, 'IMGVR_UViG_2189573022_000055'], proteins=path)
        self.assertEqual(result['protein_counts'][wanted], 2)
        self.assertEqual([row['protein_id'] for row in result['proteins'][wanted]],
                         ['PRSSG2_00147660', 'PRSSG2_00147710'])
        self.assertEqual(result['uvigs_without_proteins'], ['IMGVR_UViG_2189573022_000055'])
        self.assertNotIn(other, result['proteins'])
        # an injected stream keeps the pass testable without any release file
        injected = loci.cohort_proteins([wanted], proteins='ignored',
                                        opener=lambda _: io.StringIO(text))
        self.assertEqual(injected['protein_counts'][wanted], 2)
        with self.assertRaises(ValueError):
            loci.cohort_proteins([])

    def test_the_cohort_pass_reports_truncation_rather_than_silently_cutting(self):
        wanted = 'IMGVR_UViG_2189573022_000041'
        text = ''.join('>' + wanted + '|2189573022|g%d\n' % index + RT_LIKE + '\n'
                       for index in range(5))
        result = loci.cohort_proteins([wanted], proteins='ignored', limit_per_uvig=2,
                                      opener=lambda _: io.StringIO(text))
        self.assertEqual(result['protein_counts'][wanted], 2)
        self.assertEqual(result['truncated_at_limit'], [wanted])

    # ------------------------------------------------------- Lab exposure

    def test_the_lab_reaches_the_locus_operations_through_the_usual_source_door(self):
        uvig, header, dna, db, fasta = self.single_locus()
        calls = []

        def local(spec):
            calls.append(spec)
            return loci.query(spec, db=db, nucleotide=fasta)

        sources = lab_sources.Sources(imgvr_loci=local)
        receipt = sources.query({'source': 'imgvr', 'operation': 'locus_join',
                                 'uvig': uvig, 'sequence': RT_LIKE})
        self.assertTrue(receipt['records'][0]['joined'])
        self.assertIn('not_novelty_or_function', receipt['metadata']['interpretation'])
        self.assertEqual(receipt['metadata']['release'], store.RELEASE)
        self.assertEqual(len(calls), 1)
        with self.assertRaisesRegex(ValueError, 'unknown IMG/VR operation'):
            sources.query({'source': 'imgvr', 'operation': 'six_frame_scan'})
        with self.assertRaises(ValueError):
            loci.query({'operation': 'not_an_operation'}, db=db, nucleotide=fasta)

    def test_the_planner_sees_the_locus_operations_only_once_the_index_is_ready(self):
        with patch.object(store, 'status', return_value={'ready': False}):
            menu = lab_genome_mining.campaign_instructions()
        self.assertNotIn('operation:locus_join', menu)
        self.assertNotIn('operation:neighborhood', menu)
        with patch.object(store, 'status', return_value={'ready': True}):
            menu = lab_genome_mining.campaign_instructions()
        self.assertIn('operation:locus_join', menu)
        self.assertIn('operation:neighborhood', menu)
        self.assertIn('operation:cohort_freeze', menu)
        self.assertIn('stays unjoined with its reason', menu)
        self.assertIn('never an absent gene', menu)
        self.assertIn('not eight independent replicates', menu)

    def test_a_similarity_receipt_carries_the_hit_sequence_the_join_needs(self):
        uvig, header, dna, db, fasta = self.single_locus()
        mmseqs = self.root/'mmseqs-bin'
        mmseqs.write_text('fixture')
        mmseqs.chmod(0o700)
        mmdb = self.root/'protein-db'
        Path(str(mmdb) + '.dbtype').write_text('fixture')
        (mmdb.parent/'index-ready.json').write_text('{}')
        captured = []

        def runner(command, **kwargs):
            captured.append(command)
            Path(command[4]).write_text('\t'.join([
                header.rsplit('|', 1)[0] + '|PRSSG2_00147660', '100.0', str(len(RT_LIKE)),
                '1e-40', '150.0', str(len(RT_LIKE)), str(len(RT_LIKE)), RT_LIKE]) + '\n')

        found = store.query({'operation': 'protein_similarity', 'sequence': RT_LIKE, 'limit': 1},
                            db=db, nucleotide=fasta, mmseqs=mmseqs, mmseqs_db=mmdb, runner=runner)
        row = found['records'][0]
        self.assertEqual(row['target_sequence'], RT_LIKE)
        self.assertEqual(row['target_protein_id'], 'PRSSG2_00147660')
        self.assertIn('tseq', captured[0][captured[0].index('--format-output') + 1])
        # the receipt's own fields are enough to join the hit, with nothing retyped
        joined = loci.join_locus({'uvig': row['uvig'], 'sequence': row['target_sequence'],
                                  'protein_id': row['target_protein_id']},
                                 db=db, nucleotide=fasta)['records'][0]
        self.assertTrue(joined['joined'])
        self.assertEqual(joined['target_protein_id'], 'PRSSG2_00147660')

    def test_nothing_here_opens_a_release_path_or_the_live_workspace(self):
        uvig, header, dna, db, fasta = self.single_locus()
        source = Path(loci.__file__).read_text()
        self.assertNotIn('urlopen', source)
        self.assertNotIn('requests', source)
        self.assertIn('VINTOS_IMGVR_ROOT', source)
        # every write-capable call here is given its target; the module opens the release read-only
        self.assertNotIn(".open('wb')", source)
        self.assertNotIn('write_text', source)
        with self.assertRaises(RuntimeError):
            loci.join_locus({'uvig': uvig, 'sequence': RT_LIKE},
                            db=self.root/'absent.sqlite3', nucleotide=fasta)


if __name__ == '__main__':
    unittest.main()

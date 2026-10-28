#!/usr/bin/env python3
"""What the Lab's night showed (28 October), each fixed where the request is read:

- 9 requests were refused as "unsupported Lab source". Seven named the source where its operation goes
  ({"operation": "uniprot", "query": ...}, source ""): the planning route already read that shape, the execution
  door did not. One was {"source": "ncbi_taxonomy", "operation": "taxonomy", "term": "1009004"} — NCBI's taxonomy
  is an operation of source ncbi, and it was the one call that would have checked the taxon ID the night's
  questions were built on.
- 12 requests were refused for "exact sourced NCBI accession.version required", 11 of them naming a UniProt
  accession (Q7RTX1, O43511, A0A0H2Z7I6). A UniProt accession is no NCBI accession.version, and nothing said so or
  said how to get one. The protein sources now follow that record's own RefSeq or EMBL cross-reference and say
  which record was read; a nucleotide window still asks for coded_by, and says that.
- Every refusal here names the sources the Lab has, by lane, and the call that returns what is missing.

Scratch stores only; every sender is blocked by the shared sandbox and nothing runs except the stubs passed in."""
import json
import unittest
from unittest.mock import Mock, patch
import test_lab_tool_routing as sandbox
import chemistry_lab as C
import lab_investigations as I
import lab_phage
from lab_sources import (LANE_SOURCES, Sources, accession_needed, sources_note, step_accession,
                         unsupported_source)
from lab_tool_calls import normalize_request, normalize_source

RT = 'Q7RTX1'


def uniprot_record(accession=RT, refseq='WP_012345678.1', embl=None):
    refs = []
    if refseq:
        refs.append({'database': 'RefSeq', 'id': refseq})
    if embl:
        refs.append({'database': 'EMBL', 'id': 'AF030880',
                     'properties': [{'key': 'ProteinId', 'value': embl}]})
    return {'primaryAccession': accession, 'uniProtKBCrossReferences': refs}


class Names(unittest.TestCase):
    def test_a_database_written_as_a_source_is_that_operation_of_ncbi(self):
        self.assertEqual(normalize_source({'source': 'ncbi_taxonomy', 'operation': 'taxonomy', 'term': '1009004'}),
                         {'source': 'ncbi', 'operation': 'taxonomy', 'term': '1009004'})
        for said, operation in (('ncbi_protein', 'protein'), ('ncbi_gene', 'gene'), ('ncbi_assembly', 'assembly'),
                                ('ncbi_pubmed', 'literature'), ('taxonomy', 'taxonomy')):
            got = normalize_source({'source': said, 'term': 'Vibrio parahaemolyticus'})
            self.assertEqual((got['source'], got['operation']), ('ncbi', operation))

    def test_a_source_named_where_its_operation_goes_is_read_at_the_door(self):
        sent = {'operation': 'uniprot', 'source': '',
                'query': 'taxonomy_id:1009004 AND reviewed:true AND protein_name:"reverse transcriptase"'}
        self.assertEqual(normalize_source(sent),
                         {'source': 'uniprot', 'query': sent['query']})
        self.assertEqual(normalize_source({'source': '', 'operation': 'rt_locus_screen', 'accession': 'WP_1.1'}),
                         {'source': 'rt_locus_screen', 'accession': 'WP_1.1'})
        # the planning route reads the same shape the same way
        self.assertEqual(normalize_request('source', dict(sent)), normalize_source(sent))

    def test_an_unsupported_source_names_the_sources_there_are(self):
        told = str(unsupported_source('mgnifyx'))
        for lane in LANE_SOURCES:
            for source in LANE_SOURCES[lane]:
                self.assertIn(source, told)
        self.assertIn('imgvr', told)                                  # a source of no one lane is named too
        self.assertIn('genome mining: ncbi_protein_context', str(unsupported_source('x', 'genome_mining')))
        self.assertIn('"operation": "taxonomy"', str(unsupported_source('ncbi_taxonomy')))
        self.assertNotIn('operation', sources_note())

    def test_a_uniprot_accession_is_told_what_it_is_and_how_to_get_the_other(self):
        told = str(accession_needed(RT, 'ncbi_protein_context'))
        self.assertIn('%s is a UniProt accession' % RT, told)
        self.assertIn('"query": "accession:%s"' % RT, told)
        self.assertIn('"operation": "protein"', told)
        window = str(accession_needed(RT, 'ncbi_neighborhood'))
        self.assertIn('coded_by', window)
        self.assertIn('ncbi_protein_context', window)
        self.assertIn('not the exact sourced NCBI accession.version required here',
                      str(accession_needed('reverse transcriptase', 'ncbi_sequence')))

    def test_the_accession_a_step_will_read_is_the_one_checked(self):
        self.assertEqual(step_accession({'source': 'ncbi_protein_context', 'accession': 'WP_012345678.1'}),
                         'WP_012345678.1')
        self.assertEqual(step_accession({'source': 'rt_locus_screen', 'accession': RT.lower()}), RT)
        for source in ('ncbi_neighborhood', 'ncbi_sequence'):
            with self.assertRaises(ValueError) as told:
                step_accession({'source': source, 'accession': RT})
            self.assertIn('UniProt accession', str(told.exception))


class Resolved(unittest.TestCase):
    def sources(self, record=None, pages=None):
        sent = []
        def fetch(url):
            sent.append(url)
            if url.startswith('https://rest.uniprot.org/'):
                return (record if record is not None else uniprot_record()), {}
            raise AssertionError('unexpected fetch ' + url)
        def fetch_record(url):
            sent.append(url)
            return (pages or {})[url.split('id=')[1].split('&')[0]]
        return Sources(fetch=fetch, fetch_record=fetch_record, fetch_structure=sandbox.SEND), sent

    def genpept(self, accession='WP_012345678.1'):
        return ('<GBSet><GBSeq><GBSeq_primary-accession>%s</GBSeq_primary-accession>'
                '<GBSeq_accession-version>%s</GBSeq_accession-version>'
                '<GBSeq_definition>reverse transcriptase</GBSeq_definition>'
                '<GBSeq_organism>uncultured phage</GBSeq_organism><GBSeq_taxonomy>Viruses</GBSeq_taxonomy>'
                '<GBSeq_length>420</GBSeq_length><GBSeq_sequence>mkaliv</GBSeq_sequence>'
                '<GBSeq_feature-table><GBFeature><GBFeature_key>CDS</GBFeature_key><GBFeature_quals>'
                '<GBQualifier><GBQualifier_name>coded_by</GBQualifier_name>'
                '<GBQualifier_value>CP001234.1:120..1380</GBQualifier_value></GBQualifier>'
                '</GBFeature_quals></GBFeature></GBSeq_feature-table></GBSeq></GBSet>'
                % (accession.split('.')[0], accession))

    def test_a_uniprot_accession_reaches_the_protein_record_its_own_reference_names(self):
        src, sent = self.sources(pages={RT: self.genpept(), 'WP_012345678.1': self.genpept()})
        out = src.query(normalize_source({'source': 'ncbi_protein_context', 'accession': RT}))
        self.assertEqual(out['query']['accession'], 'WP_012345678.1')
        resolution = out['metadata']['accession_resolution']
        self.assertEqual((resolution['asked'], resolution['used']), (RT, 'WP_012345678.1'))
        self.assertIn('RefSeq protein cross-reference', resolution['via'])
        self.assertIn('WP_012345678.1', resolution['note'])
        self.assertTrue(any('rest.uniprot.org' in u for u in sent))
        self.assertTrue(all(u.startswith(('https://rest.uniprot.org/', 'https://eutils.ncbi.nlm.nih.gov/'))
                            for u in sent))

    def test_an_ncbi_accession_is_read_as_given_with_nothing_resolved(self):
        src, sent = self.sources(pages={'WP_012345678.1': self.genpept()})
        out = src.query(normalize_source({'source': 'ncbi_protein_context', 'accession': 'WP_012345678.1'}))
        self.assertNotIn('accession_resolution', out['metadata'])
        self.assertTrue(all('rest.uniprot.org' not in u for u in sent))      # no extra request

    def test_the_embl_protein_id_answers_when_there_is_no_refseq(self):
        src, _ = self.sources(record=uniprot_record(refseq=None, embl='AAC12345.1'),
                              pages={'AAC12345.1': self.genpept('AAC12345.1')})
        out = src.query(normalize_source({'source': 'ncbi_protein_context', 'accession': RT}))
        self.assertEqual(out['query']['accession'], 'AAC12345.1')
        self.assertIn('EMBL protein cross-reference', out['metadata']['accession_resolution']['via'])

    def test_a_record_with_no_ncbi_protein_says_so_and_names_the_search(self):
        src, _ = self.sources(record=uniprot_record(refseq=None))
        with self.assertRaises(ValueError) as told:
            src.query(normalize_source({'source': 'ncbi_protein_context', 'accession': RT}))
        self.assertIn('no RefSeq or EMBL protein cross-reference', str(told.exception))
        self.assertIn('"operation": "protein"', str(told.exception))

    def test_a_record_that_is_not_the_one_asked_for_is_not_read(self):
        src, _ = self.sources(record=uniprot_record(accession='O43511'))
        with self.assertRaises(ValueError) as told:
            src.query(normalize_source({'source': 'ncbi_protein_context', 'accession': RT}))
        self.assertIn('did not match', str(told.exception))

    def test_the_locus_screen_resolves_the_same_way_and_says_which_record(self):
        with patch.object(lab_phage, 'screened', return_value=[{'protein': 'WP_012345678.1', 'array_associated': True}]):
            src, _ = self.sources()
            screen = lab_phage.screen(src, {'source': 'rt_locus_screen', 'accession': RT})
        self.assertEqual(screen['query']['accession'], 'WP_012345678.1')
        self.assertEqual(screen['records'][0]['already_screened'], True)
        self.assertIn('WP_012345678.1', screen['metadata']['accession_resolution']['note'])

    def test_an_unsupported_source_at_the_door_names_the_sources(self):
        src, _ = self.sources()
        with self.assertRaises(ValueError) as told:
            src.query({'source': 'ncbi_taxonomyx', 'term': 'phage'})
        self.assertIn("The Lab's sources right now", str(told.exception))

    def tearDown(self):
        sandbox.SEND.assert_not_called()


class ToldInTheMoment(unittest.TestCase):
    def test_the_resolved_record_is_told_with_the_step(self):
        step = {'id': 'S-rt'}
        I._store_result(step, {'receipt': {'source': 'ncbi_protein_context', 'records': [{}], 'metadata': {
            'accession_resolution': {'asked': RT, 'used': 'WP_012345678.1',
                                     'note': '%s is a UniProt accession; WP_012345678.1 is its RefSeq protein '
                                             'cross-reference, and that record was read.' % RT}}}})
        self.assertIn('WP_012345678.1', step['resolved'])

    def test_a_guessed_taxon_id_is_told_with_the_call_that_looks_it_up(self):
        C._append(C.NOTEBOOK, {'at': C.now_iso(), 'kind': 'unsourced_id', 'ids': ['1009004'],
                               'query_sent': {'source': 'uniprot', 'query': 'taxonomy_id:1009004 AND reviewed:true'},
                               'truth_status': 'id_not_returned_by_any_receipt_not_sent'})
        said = '\n'.join(C.search_misses())
        self.assertIn('1009004 came from no receipt', said)
        self.assertIn('"operation": "taxonomy"', said)

    def test_a_uniprot_accession_in_a_mining_step_is_not_refused_before_it_runs(self):
        repeats = Mock(repeat=Mock(return_value=None), record=Mock(), on_frontier=Mock(return_value=True))
        inquiry = {'question': 'What sits beside this reverse transcriptase?', 'browse_lane': 'genome_mining',
                   'source_query': {'source': 'ncbi_protein_context', 'accession': RT}}
        C._append(C.os.path.join(C.ROOT, 'source-receipts.jsonl'),
                  {'source': 'uniprot', 'records': [{'accession': RT}]})
        with patch.object(C, '_held_question', return_value=None), \
                patch.object(C, '_ground_inquiry', return_value={'status': 'not_applicable'}):
            got, _ = C._held_to_plan(None, '', inquiry, {}, None, None, repeats, replan=False)
        self.assertIsNone(got.get('refused'))
        # the same step with a nucleotide window still asks for coded_by, and says where it comes from
        window = dict(inquiry, source_query={'source': 'ncbi_neighborhood', 'accession': RT,
                                             'anchor_start': 1, 'anchor_end': 90})
        with patch.object(C, '_held_question', return_value=None), \
                patch.object(C, '_ground_inquiry', return_value={'status': 'not_applicable'}):
            got, _ = C._held_to_plan(None, '', window, {}, None, None, repeats, replan=False)
        self.assertIn('coded_by', got['refused'])

    def test_an_invented_accession_is_still_refused_before_anything_is_sent(self):
        repeats = Mock(repeat=Mock(return_value=None), record=Mock(), on_frontier=Mock(return_value=True))
        inquiry = {'question': 'What sits beside it?', 'browse_lane': 'genome_mining',
                   'source_query': {'source': 'ncbi_protein_context', 'accession': 'A0A0H2Z7I6'}}
        with patch.object(C, '_held_question', return_value=None), \
                patch.object(C, '_ground_inquiry', return_value={'status': 'not_applicable'}):
            got, _ = C._held_to_plan(None, '', inquiry, {}, None, None, repeats, replan=False)
        self.assertIn('not returned by a source receipt', got['refused'])

    def tearDown(self):
        sandbox.SEND.assert_not_called()


if __name__ == '__main__': unittest.main(verbosity=2)

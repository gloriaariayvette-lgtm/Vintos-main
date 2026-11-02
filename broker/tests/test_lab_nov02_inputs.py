#!/usr/bin/env python3
"""Two inputs the Lab sent that could only fail (2 November). The sequence representation was pointed 126 times at
a summary, an assessment or one output line instead of protein records, and the ESMC worker crashed on each; UniProt
was asked accession:LDLR, accession:TAS1R2 and accession:O146, a gene name or a cut-off accession in the accession
field, and refused each with a 400. Scratch stores only; every sender is blocked by the shared sandbox."""
import hashlib
import json
import unittest
from pathlib import Path
import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_sources as S

C = sandbox.C
SEQ = 'MAAPGGRSEPPQLPEYSCSYMVSRPVYSELAFQHQHERRLQERKTLRESLAKCCSCSRKRAFGVLKTLVPILEWLPKYRVKEWLLSDVISGVSTGLVATLQGMAYALLAAVP'


def output(step_id, payload, **extra):
    """A completed step whose output the Lab holds, as _store_result writes it."""
    path = 'investigation-outputs/%s.json' % step_id
    Path(I._path('investigation-outputs')).mkdir(parents=True, exist_ok=True)
    C._atomic(I._path(path), payload)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict({'id': step_id, 'state': 'completed', 'output_file': path, 'output_sha256': digest}, **extra)


class Representation(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(I._path('investigation-outputs')).is_relative_to(sandbox.SCRATCH))
        self.uniprot = output('S-u', {'normalized_records': [{'accession': 'O43511', 'sequence': SEQ}],
                                      'receipt': {'records': [{'summary': 'pendrin, an anion exchanger'}]}})
        self.pubmed = output('S-p', {'receipt': {'records': [{'summary': 'chloride and iodide transport'}]}})

    def tearDown(self):
        sandbox.SEND.assert_not_called()

    def test_records_with_sequences_are_sent_as_given(self):
        request = {'records': {'step': 'S-u', 'path': ['normalized_records']}}
        self.assertEqual(I._representation_input(request, [self.uniprot]), (request, ''))

    def test_a_pointer_at_a_summary_of_a_step_that_holds_sequences_is_taken_to_them(self):
        request = {'records': {'step': 'S-u', 'path': ['receipt', 'records', 0, 'summary']}}
        fixed, why = I._representation_input(request, [self.uniprot])
        self.assertEqual((fixed['records'], why), ({'step': 'S-u', 'path': ['normalized_records']}, ''))

    def test_text_is_refused_before_sending_with_where_the_sequences_are(self):
        request = {'records': {'step': 'S-p', 'path': ['receipt', 'records', 0, 'summary']}}
        fixed, why = I._representation_input(request, [self.uniprot, self.pubmed])
        self.assertIs(fixed, request)
        self.assertIn('holds a str', why)
        self.assertIn('"step": "S-u"', why)
        fixed, why = I._representation_input(request, [self.pubmed])
        self.assertIn('holds no protein sequence yet', why)

    def test_a_missing_field_is_said_not_raised(self):
        _, why = I._representation_input({'records': {'step': 'S-p', 'path': ['candidate']}}, [self.pubmed])
        self.assertIn('representation needs protein records', why)


class UniProtAccessionField(unittest.TestCase):
    def test_a_gene_name_in_the_accession_field_is_the_gene(self):
        self.assertEqual(S.validate_uniprot('accession:LDLR'), 'gene:LDLR')
        self.assertEqual(S.validate_uniprot('accession:"SLC26A11"'), 'gene:SLC26A11')
        self.assertEqual(S.validate_uniprot('(accession:TAS1R2) AND taxonomy_id:9606'), '(gene:TAS1R2) AND taxonomy_id:9606')
        self.assertEqual(S.validate_uniprot('accession:O146'), 'gene:O146')        # cut off: finds nothing, no 400

    def test_real_accessions_are_untouched(self):
        for q in ('accession:P01130', 'accession:P01130-2', 'accession:A0A2K6NV81', 'accession:Q8ECH7 AND reviewed:true'):
            self.assertEqual(S.validate_uniprot(q), q)

    def test_the_records_kept_are_the_genes_records(self):
        rows = [{'primaryAccession': 'P01130', 'genes': [{'geneName': {'value': 'LDLR'}}]},
                {'primaryAccession': 'P98155', 'genes': [{'geneName': {'value': 'VLDLR'}}]}]
        kept = S.verify_uniprot_identity('accession:LDLR', rows)
        self.assertEqual([r['primaryAccession'] for r in kept], ['P01130'])


if __name__ == '__main__': unittest.main(verbosity=2)

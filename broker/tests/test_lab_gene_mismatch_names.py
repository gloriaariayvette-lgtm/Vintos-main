#!/usr/bin/env python3
"""A gene-mismatch refusal names the genes the records carried. No network; scratch paths only."""
import os, sys, socket, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
SCRATCH = tempfile.TemporaryDirectory(prefix='gene-mismatch-names-')
os.environ['HOME'] = SCRATCH.name
os.environ['SPARK_WORKSPACE'] = SCRATCH.name + '/workspace'
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import lab_sources as sources


class Tests(unittest.TestCase):
    def setUp(self):
        self.net = patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden'))
        self.net.start(); self.addCleanup(self.net.stop)
        self.source_net = patch.object(sources, 'open_request', side_effect=AssertionError('source network forbidden'))
        self.source_net.start(); self.addCleanup(self.source_net.stop)
        # Isolation asserted in the suite itself: senders are stubs and home is throwaway.
        self.assertTrue(hasattr(socket.socket.connect, 'mock_calls'))
        self.assertTrue(hasattr(sources.open_request, 'mock_calls'))
        self.assertTrue(Path(os.environ['HOME']).is_relative_to(SCRATCH.name))
        self.assertTrue(Path(os.environ['SPARK_WORKSPACE']).is_relative_to(SCRATCH.name))

    def test_mismatch_names_the_returned_genes(self):
        wrong = {'primaryAccession': 'O95905',
                 'genes': [{'geneName': {'value': 'ECD'}, 'synonyms': [{'value': 'SGT1'}]}]}
        with self.assertRaises(ValueError) as caught:
            sources.verify_uniprot_identity('gene:SLC26A4', [wrong])
        message = str(caught.exception)
        self.assertIn('source_gene_mismatch', message)
        self.assertIn('O95905', message)
        # The names the record carried survive the check and reach the refusal.
        self.assertIn('ECD', message)
        self.assertIn('SGT1', message)
        # A record with no gene names adds nothing and does not break the message.
        with self.assertRaisesRegex(ValueError, 'source_gene_mismatch: requested SLC26A4; returned X1$'):
            sources.verify_uniprot_identity('gene:SLC26A4', [{'primaryAccession': 'X1'}])
        # Kept records are unchanged by the bookkeeping.
        valid = {'primaryAccession': 'O43511', 'genes': [{'geneName': {'value': 'SLC26A4'}}]}
        self.assertEqual(sources.verify_uniprot_identity('gene:SLC26A4', [wrong, valid]), [valid])

    def test_a_records_exact_short_protein_name_establishes_it(self):
        # 25 October, "requested PHD2; returned Q9GZT9,... naming C1ORF12,EGLN1,...": the right record, refused because
        # PHD2 is its short protein name, not a gene synonym. TFR1 (P02786) and P2X7 (Q99572) failed the same way.
        def record(acc, gene, full, short=(), alt=()):
            return {'primaryAccession': acc, 'genes': [{'geneName': {'value': gene}}],
                    'proteinDescription': {'recommendedName': {'fullName': {'value': full},
                                                               'shortNames': [{'value': s} for s in short]},
                                           'alternativeNames': [{'fullName': {'value': f},
                                                                 'shortNames': [{'value': s} for s in ss]}
                                                                for f, ss in alt]}}
        egln1 = record('Q9GZT9', 'EGLN1', 'Egl nine homolog 1',
                       alt=[('Prolyl hydroxylase domain-containing protein 2', ['PHD2']), ('Hypoxia-inducible factor '
                            'prolyl hydroxylase 2', ['HIF-PH2', 'HIF-prolyl hydroxylase 2'])])
        ptges3 = record('Q15185', 'PTGES3', 'Prostaglandin E synthase 3', alt=[('Telomerase-binding protein p23', ['p23'])])
        self.assertEqual(sources.verify_uniprot_identity('(gene:PHD2) AND taxonomy_id:9606 AND reviewed:true',
                                                         [egln1, ptges3]), [egln1])
        tfrc = record('P02786', 'TFRC', 'Transferrin receptor protein 1', short=['TR', 'TfR', 'TfR1', 'Trfr'])
        tfr2 = record('Q9UP52', 'TFR2', 'Transferrin receptor protein 2', short=['TfR2'])
        self.assertEqual(sources.verify_uniprot_identity('gene:TFR1 AND taxonomy_id:9606', [tfrc, tfr2]), [tfrc])
        # a full name, or a short name that only resembles the symbol, establishes nothing
        with self.assertRaisesRegex(ValueError, 'source_gene_mismatch: requested P2X7'):
            sources.verify_uniprot_identity('gene:P2X7', [record('Q99572', 'P2RX7', 'P2X7')])
        with self.assertRaisesRegex(ValueError, 'source_gene_mismatch: requested PHD3'):
            sources.verify_uniprot_identity('gene:PHD3', [egln1])
        # the wrong records the 25 October SOXS/SOXR request returned are still refused, their names given
        tipa = record('P0A4T8', 'tipA', 'HTH-type transcriptional activator TipA', short=['TipA'])
        with self.assertRaisesRegex(ValueError, 'requested SOXS,SOXR; returned P0A4T8 naming TIPA'):
            sources.verify_uniprot_identity('gene:soxS OR gene:soxR', [tipa])


if __name__ == '__main__': unittest.main()

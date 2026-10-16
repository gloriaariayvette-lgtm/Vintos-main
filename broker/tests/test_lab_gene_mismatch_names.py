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


if __name__ == '__main__': unittest.main()

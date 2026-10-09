#!/usr/bin/env python3
"""Replay the invented SLC26A28 target using captured NCBI response shapes; no senders."""
import os, sys, tempfile, unittest, socket
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
SCRATCH = tempfile.TemporaryDirectory(prefix='gene-grounding-')
os.environ['HOME'] = SCRATCH.name
os.environ['SPARK_WORKSPACE'] = SCRATCH.name + '/workspace'
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import chemistry_lab as lab
import lab_sources as sources
import lab_repeats as repeats

class Tests(unittest.TestCase):
    def setUp(self):
        self.net = patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden'))
        self.net.start(); self.addCleanup(self.net.stop)
        self.sender = patch.object(lab, '_ask', side_effect=AssertionError('model forbidden'))
        self.sender.start(); self.addCleanup(self.sender.stop)
        self.assertTrue(hasattr(socket.socket.connect, 'mock_calls'))
        self.assertTrue(hasattr(lab._ask, 'mock_calls'))
        for path in (lab.ROOT, lab.CONFIG, lab.STATE, lab.NOTEBOOK, lab.FAULTS, lab.LOCK, repeats.LOOKUPS, repeats.SESSIONS):
            self.assertTrue(Path(path).is_relative_to(SCRATCH.name), path)
        Path(lab.ROOT).mkdir(parents=True, exist_ok=True)
        (Path(lab.ROOT)/'source-receipts.jsonl').unlink(missing_ok=True)
        self.calls = []
        self.row = {'uid':'5172','name':'SLC26A4','description':'solute carrier family 26 member 4',
                    'currentid':'','otheraliases':'DFNB4, EVA, PDS, TDH2B',
                    'nomenclaturesymbol':'SLC26A4','organism':{'taxid':9606}}
    def fetch(self, url):
        self.calls.append(url)
        if 'esearch' in url:
            symbol = parse_qs(urlsplit(url).query)['term'][0].split('[sym]')[0]
            ids = [] if symbol == 'SLC26A28' else ['5172']
            return {'header':{'type':'esearch','version':'0.3'},
                    'esearchresult':{'count':str(len(ids)), 'idlist':ids}}, {}
        return {'header':{'type':'esummary','version':'0.3'},
                'result':{'uids':['5172'],'5172':self.row}}, {}
    def query(self, symbol):
        return {'question':'What does '+symbol+' do?', 'source_query':{'source':'atlas','gene':symbol}}
    def ground(self, symbol):
        return lab._ground_inquiry(self.query(symbol), sources.Sources(fetch=self.fetch))
    def test_real_and_alias(self):
        for symbol in ('SLC26A4', 'PDS'):
            self.assertEqual(self.ground(symbol)['status'], 'verified')
        self.assertEqual(sources.Sources(fetch=self.fetch).human_gene_identity('PDS')['records'][0]['symbol'], 'SLC26A4')
    def test_invented_refused_before_acceptance(self):
        client = sources.Sources(fetch=self.fetch)
        with patch.object(sources, 'Sources', return_value=client):
            inquiry, _ = lab._held_to_plan('', '', self.query('SLC26A28'), {}, None, None, repeats)
        self.assertIn('SLC26A28', inquiry['refused'])
        self.assertEqual(inquiry['identity_check']['status'], 'unresolved')
        self.assertEqual(repeats.repeat(self.query('SLC26A28')), '')
        self.assertEqual(len(self.calls), 1)
        lab._ask.assert_not_called()
    def test_wrong_symbol_or_taxon_not_accepted(self):
        self.assertEqual(self.ground('SLC26A5')['status'], 'unresolved')
        self.row['organism']['taxid'] = 10090
        self.assertEqual(self.ground('SLC26A4')['status'], 'unresolved')
    def test_unavailable_is_not_negative_cached(self):
        def unavailable(url): raise HTTPError(url, 429, 'limited', {}, None)
        result = lab._ground_inquiry(self.query('SLC26A4'), sources.Sources(fetch=unavailable))
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('HTTP 429', result['reason'])
        self.assertEqual(self.ground('SLC26A4')['status'], 'verified')
    def test_receipts_cache_both_outcomes(self):
        for symbol in ('SLC26A4','SLC26A28'):
            first = self.ground(symbol); count = len(self.calls)
            self.assertEqual(first, self.ground(symbol)); self.assertEqual(len(self.calls), count)
    def test_symbols_in_human_queries_only(self):
        client = sources.Sources(fetch=self.fetch)
        for query in ('gene:SLC26A28 AND taxonomy_id:9606', 'protein_name:SLC26A28 AND organism_id:9606'):
            self.assertEqual(lab._ground_inquiry({'uniprot_query':query}, client)['status'], 'unresolved')
        for query in ('gene:kaiC AND taxonomy_id:1117', 'protein_name:"SLC26 family transporter" AND taxonomy_id:9606', 'protein_name:insulin AND taxonomy_id:9606', 'protein_name:ATPase AND taxonomy_id:9606'):
            self.assertEqual(lab._ground_inquiry({'uniprot_query':query}, client)['status'], 'not_applicable')

if __name__ == '__main__': unittest.main()

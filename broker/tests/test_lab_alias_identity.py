#!/usr/bin/env python3
"""A requested alias no returned record carries is resolved through its human gene identity, exactly, before the
records are checked (29 October, fault F-e0d1242912, three times: "source_gene_mismatch: requested SR-BI; returned
Q8WTV0,Q14108 naming CD36L1,CLA-1,CLA1,SCARB1,SRB1,CD36L2,LGP85,LIMP II". SR-BI is NCBI Gene's recorded alias of
human SCARB1, gene 949, UniProt Q8WTV0; Q14108 is its sibling SCARB2, LIMP-2).

Hand-built records shaped like UniProt's and NCBI Gene's; every fetch is a stub, sockets and source requests are
refused, home is a scratch directory. No model is asked."""
import io, json, os, socket, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
SCRATCH = tempfile.TemporaryDirectory(prefix='lab-alias-identity-')
os.environ['HOME'] = SCRATCH.name
os.environ['SPARK_WORKSPACE'] = SCRATCH.name + '/workspace'
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import chemistry_lab as lab
import lab_sources as sources

FAULT = ('source_gene_mismatch: requested SR-BI; returned Q8WTV0,Q14108 naming '
         'CD36L1,CLA-1,CLA1,SCARB1,SRB1,CD36L2,LGP85,LIMP II')
QUERY = 'gene:SR-BI AND organism_id:9606'


def record(acc, gene, synonyms=(), shorts=(), taxon=9606):
    return {'primaryAccession': acc, 'uniProtkbId': gene.upper() + ('_HUMAN' if taxon == 9606 else '_MOUSE'),
            'organism': {'scientificName': 'Homo sapiens' if taxon == 9606 else 'Mus musculus', 'taxonId': taxon},
            'genes': [{'geneName': {'value': gene}, 'synonyms': [{'value': s} for s in synonyms]}],
            'proteinDescription': {'recommendedName': {'fullName': {'value': gene + ' protein'}},
                                   'alternativeNames': [{'fullName': {'value': s + ' name'},
                                                         'shortNames': [{'value': s}]} for s in shorts]}}

SCARB1 = record('Q8WTV0', 'SCARB1', ['CD36L1', 'CLA1', 'SRB1'], ['CLA-1'])
SCARB2 = record('Q14108', 'SCARB2', ['CD36L2', 'LIMP2', 'LIMPII'], ['LGP85', 'LIMP II'])
MOUSE_SCARB1 = record('Q61009', 'Scarb1', ['Srb1'], taxon=10090)
HSP90AA1 = record('P07900', 'HSP90AA1', ['HSP90A', 'HSPC1', 'HSPCA'])
HSP90AB1 = record('P08238', 'HSP90AB1', ['HSP90B', 'HSPC2', 'HSPCB'])
SLC26A4 = record('O43511', 'SLC26A4', ['PDS'])

# NCBI Gene esummary rows, as the existing grounding replay shapes them.
GENES = {
    '949': {'uid': '949', 'name': 'SCARB1', 'nomenclaturesymbol': 'SCARB1', 'description': 'scavenger receptor class B member 1',
            'currentid': '', 'otheraliases': 'CD36L1, CLA-1, CLA1, HDLQTL6, SR-BI, SRB1', 'organism': {'taxid': 9606}},
    '3320': {'uid': '3320', 'name': 'HSP90AA1', 'nomenclaturesymbol': 'HSP90AA1', 'description': 'heat shock protein 90 alpha family class A member 1',
             'currentid': '', 'otheraliases': 'HSP86, HSP90A, HSP90, HSPC1, HSPCA', 'organism': {'taxid': 9606}},
    '3326': {'uid': '3326', 'name': 'HSP90AB1', 'nomenclaturesymbol': 'HSP90AB1', 'description': 'heat shock protein 90 alpha family class B member 1',
             'currentid': '', 'otheraliases': 'HSP84, HSP90B, HSP90, HSPC2, HSPCB', 'organism': {'taxid': 9606}},
    '375611': {'uid': '375611', 'name': 'SLC26A5', 'nomenclaturesymbol': 'SLC26A5', 'description': 'solute carrier family 26 member 5',
               'currentid': '', 'otheraliases': 'DFNB61, PRES', 'organism': {'taxid': 9606}},
}
SEARCH = {'SR-BI': ['949'], 'HSP90': ['3320', '3326'], 'SLC26A5': ['375611']}


class Stub:
    """One fetch for UniProt and NCBI, recording every URL it was asked for."""
    def __init__(self, uniprot):
        self.uniprot, self.calls = uniprot, []
    def __call__(self, url):
        self.calls.append(url)
        if 'rest.uniprot.org' in url:
            return {'results': [json.loads(json.dumps(r)) for r in self.uniprot]}, {'X-UniProt-Release': 'stub'}
        params = parse_qs(urlsplit(url).query)
        if 'esearch' in url:
            symbol = params['term'][0].split('[sym]')[0]
            ids = SEARCH.get(symbol, [])
            return {'esearchresult': {'count': str(len(ids)), 'idlist': ids}}, {}
        ids = params['id'][0].split(',')
        return {'result': dict({'uids': ids}, **{i: GENES[i] for i in ids})}, {}
    def ncbi(self):
        return [u for u in self.calls if 'eutils' in u or 'esearch' in u or 'esummary' in u]


def identity(uniprot=()):
    stub = Stub(uniprot)
    return stub, sources.Sources(fetch=stub).human_gene_identity


def kept(query, records, resolver=None):
    try:
        return [r['primaryAccession'] for r in sources.verify_uniprot_identity(query, records, identity=resolver)]
    except ValueError as exc:
        return str(exc)


class Tests(unittest.TestCase):
    def setUp(self):
        self.net = patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden'))
        self.net.start(); self.addCleanup(self.net.stop)
        self.source_net = patch.object(sources, 'open_request', side_effect=AssertionError('source network forbidden'))
        self.source_net.start(); self.addCleanup(self.source_net.stop)
        self.sender = patch.object(lab, '_ask', side_effect=AssertionError('model forbidden'))
        self.sender.start(); self.addCleanup(self.sender.stop)
        self.assertTrue(hasattr(socket.socket.connect, 'mock_calls'))
        self.assertTrue(hasattr(sources.open_request, 'mock_calls'))
        for path in (lab.ROOT, lab.NOTEBOOK):
            self.assertTrue(Path(path).is_relative_to(SCRATCH.name), path)
        Path(lab.ROOT).mkdir(parents=True, exist_ok=True)
        (Path(lab.ROOT) / 'source-receipts.jsonl').unlink(missing_ok=True)

    # 1. The fault itself, on the source-fetching path, then the same request resolved.
    def test_the_29_october_fault_on_the_source_path(self):
        stub = Stub([SCARB1, SCARB2])
        got = sources.Sources(fetch=stub).query({'source': 'uniprot', 'query': QUERY})
        self.assertEqual([r['primaryAccession'] for r in got['records']], ['Q8WTV0'])
        resolution = got['records'][0]['identity_resolution']
        self.assertEqual((resolution['requested'], resolution['canonical_symbol'], resolution['ncbi_gene_id'],
                          resolution['accession'], resolution['taxon_id']), ('SR-BI', 'SCARB1', '949', 'Q8WTV0', 9606))
        self.assertTrue(sources.verified_human_identity(resolution['receipt'], 'SR-BI'))
        self.assertIn('SR-BI', resolution['evidence'])
        self.assertEqual(got['metadata']['identity_resolutions'],
                         [{k: resolution[k] for k in ('requested', 'canonical_symbol', 'ncbi_gene_id', 'accession')}
                          | {'receipt_id': resolution['receipt']['receipt_id']}])
        self.assertEqual(len(stub.ncbi()), 2)   # one esearch, one esummary: an exact alias lookup, nothing wider

    def test_the_original_refusal_is_unchanged_without_an_identity(self):
        self.assertEqual(kept(QUERY, [SCARB1, SCARB2]), FAULT)

    # 2. Mixed right and wrong records, either order; the wrong sibling alone is still refused.
    def test_mixed_records_keep_only_the_resolved_gene(self):
        for records in ([SCARB1, SCARB2], [SCARB2, SCARB1]):
            self.assertEqual(kept(QUERY, records, identity()[1]), ['Q8WTV0'])
        self.assertTrue(str(kept(QUERY, [SCARB2], identity()[1])).startswith(
            'source_gene_mismatch: requested SR-BI; returned Q14108 naming CD36L2'))

    # 3. The right symbol in the wrong species is not the human gene.
    def test_wrong_species_with_the_right_symbol_is_refused(self):
        self.assertTrue(str(kept(QUERY, [MOUSE_SCARB1], identity()[1])).startswith('source_gene_mismatch: requested SR-BI'))
        self.assertEqual(kept(QUERY, [MOUSE_SCARB1, SCARB1], identity()[1]), ['Q8WTV0'])
        no_taxon = json.loads(json.dumps(SCARB1)); no_taxon.pop('organism')
        self.assertTrue(str(kept(QUERY, [no_taxon], identity()[1])).startswith('source_gene_mismatch'))
        # A query asking for another species is not a human alias question at all: nothing is looked up.
        stub, resolver = identity()
        self.assertTrue(str(kept('gene:SR-BI AND organism_id:10090', [MOUSE_SCARB1], resolver)).startswith('source_gene_mismatch'))
        self.assertEqual(stub.calls, [])

    # 4. An alias of more than one human gene is a family, not one gene: refused, and the genes are named.
    def test_ambiguous_alias_stays_refused_and_is_named(self):
        got = kept('gene:HSP90 AND organism_id:9606', [HSP90AA1, HSP90AB1], identity()[1])
        self.assertTrue(got.startswith('source_gene_mismatch: requested HSP90; returned P07900,P08238 naming'), got)
        self.assertIn('HSP90 is an alias of 2 human genes (HSP90AA1,HSP90AB1)', got)

    # 5. No lookup, a failing one, an unresolved one or a receipt that does not verify: the original refusal, exactly.
    def test_missing_or_failing_lookup_refuses_with_the_original_error(self):
        def raises(symbol): raise OSError('NCBI unreachable')
        def returns_none(symbol): return None
        def forged(symbol):
            row = identity()[1](symbol)
            row = dict(row, records=[dict(row['records'][0], symbol='SCARB1')])
            row['metadata'] = dict(row['metadata'], status='verified')
            return dict(row, response_sha256='0' * 64)
        def verdict_only(symbol):
            return {'source': 'ncbi_gene_identity', 'metadata': {'status': 'verified'},
                    'records': [{'symbol': 'SCARB1', 'gene_id': '949', 'taxon_id': 9606, 'aliases': ['SR-BI']}]}
        for resolver in (None, raises, returns_none, forged, verdict_only):
            self.assertEqual(kept(QUERY, [SCARB1, SCARB2], resolver), FAULT, resolver)
        # an alias NCBI does not record (an unsupported alias) resolves to nothing
        self.assertTrue(str(kept('gene:SR-B9 AND organism_id:9606', [SCARB1], identity()[1])).startswith(
            'source_gene_mismatch: requested SR-B9'))

    # 6. Exact names and short names are accepted as before, without any lookup.
    def test_exact_and_short_name_acceptance_is_unchanged(self):
        stub, resolver = identity()
        self.assertEqual(kept('gene:SCARB1 AND organism_id:9606', [SCARB1, SCARB2], resolver), ['Q8WTV0'])
        self.assertEqual(kept('gene:SRB1', [SCARB2, SCARB1], resolver), ['Q8WTV0'])
        self.assertEqual(kept('gene:CLA-1', [SCARB1, SCARB2], resolver), ['Q8WTV0'])     # its short protein name
        self.assertEqual(kept('gene:LIMP2', [SCARB1, SCARB2], resolver), ['Q14108'])
        self.assertEqual(stub.calls, [])
        rows = sources.verify_uniprot_identity('gene:SCARB1', [SCARB1], identity=resolver)
        self.assertNotIn('identity_resolution', rows[0])

    # 7. The existing controls still refuse: a numbered sibling, a likeness, no I->1 rewriting.
    def test_existing_rejection_controls_still_refuse(self):
        resolver = identity()[1]
        # SLC26A5 is its own gene (prestin), never SLC26A4.
        self.assertTrue(str(kept('gene:SLC26A5 AND organism_id:9606', [SLC26A4], resolver)).startswith(
            'source_gene_mismatch: requested SLC26A5; returned O43511 naming PDS,SLC26A4'))
        # SRBI is not SRB1: no letter is read as a digit, and NCBI records no alias SRBI.
        self.assertTrue(str(kept('gene:SRBI AND organism_id:9606', [SCARB1], resolver)).startswith(
            'source_gene_mismatch: requested SRBI'))
        # The alias resolves to SCARB1; SCARB10 or SCARB are not SCARB1.
        for gene in ('SCARB10', 'SCARB', 'SCARB1A'):
            self.assertTrue(str(kept(QUERY, [record('X00001', gene)], resolver)).startswith('source_gene_mismatch'), gene)
        # HSP90 against only one family member is still the family name, not that gene.
        self.assertTrue(str(kept('gene:HSP90', [HSP90AA1], resolver)).startswith('source_gene_mismatch: requested HSP90'))

    # 8. The review: a kept record carries its resolution, and the review's own identity check re-verifies it.
    def test_the_review_reads_the_resolution_and_nothing_weaker(self):
        rows = lab.normalize_protein_records(sources.verify_uniprot_identity(QUERY, [SCARB2, SCARB1], identity=identity()[1]))
        self.assertEqual([r['accession'] for r in rows], ['Q8WTV0'])
        self.assertEqual(rows[0]['identity_resolution']['canonical_symbol'], 'SCARB1')
        inquiry = {'question': 'Which residues of human SR-BI bind HDL?', 'uniprot_query': QUERY}
        entity = sources.question_entity_context(inquiry, rows)
        self.assertEqual((entity['status'], entity['issues'], entity['selected_accessions']), ('consistent', [], ['Q8WTV0']))
        # the full-question assessment is still separate; this check names only identity
        self.assertIn('full prose scope needs independent assessment', entity['scope'])
        # a resolution moved onto another record, or naming another request, establishes nothing
        moved = dict(lab.normalize_protein_records([SCARB2])[0], identity_resolution=rows[0]['identity_resolution'])
        self.assertTrue(sources.question_entity_context(inquiry, [moved])['issues'])
        renamed = dict(rows[0], identity_resolution=dict(rows[0]['identity_resolution'], requested='SR-BII'))
        self.assertTrue(sources.question_entity_context(
            {'question': 'Which residues of human SR-BII bind HDL?', 'uniprot_query': 'gene:SR-BII AND organism_id:9606'},
            [renamed])['issues'])
        # without the resolution the review refuses as before
        bare = {k: v for k, v in rows[0].items() if k != 'identity_resolution'}
        self.assertTrue(sources.question_entity_context(inquiry, [bare])['issues'])

    # 9. The Chemistry Lab retrieval path: the same fault, resolved through the cached identity receipt.
    def test_the_lab_retrieval_path(self):
        uniprot = {'results': [SCARB1, SCARB2]}
        def urlopen(req, timeout=0):
            self.assertIn('rest.uniprot.org', req.full_url)
            return io.BytesIO(json.dumps(uniprot).encode())
        stub = Stub([])
        with patch.object(lab.urllib.request, 'urlopen', side_effect=urlopen), \
             patch.object(sources, 'Sources', return_value=sources.Sources(fetch=stub)):
            got = lab._browse(QUERY, 4)
            self.assertEqual([r['accession'] for r in got['records']], ['Q8WTV0'])
            self.assertEqual(got['records'][0]['identity_resolution']['canonical_symbol'], 'SCARB1')
            self.assertEqual([r['primaryAccession'] for r in got['source_receipt']['records']], ['Q8WTV0'])
            self.assertEqual(got['source_receipt']['metadata']['identity_resolutions'][0]['ncbi_gene_id'], '949')
            receipts = [json.loads(l) for l in (Path(lab.ROOT) / 'source-receipts.jsonl').read_text().splitlines()]
            self.assertEqual([r['source'] for r in receipts], ['ncbi_gene_identity'])
            looked_up = len(stub.calls)
            again = lab._browse(QUERY, 4)   # the day's receipt is reused, as _ground_inquiry reuses it
            self.assertEqual([r['accession'] for r in again['records']], ['Q8WTV0'])
            self.assertEqual(len(stub.calls), looked_up)
        # identity unavailable: the original refusal, not a pass
        def down(url): raise OSError('NCBI unreachable')
        (Path(lab.ROOT) / 'source-receipts.jsonl').unlink()
        with patch.object(lab.urllib.request, 'urlopen', side_effect=urlopen), \
             patch.object(sources, 'Sources', return_value=sources.Sources(fetch=down)):
            with self.assertRaises(ValueError) as caught:
                lab._browse(QUERY, 4)
        self.assertEqual(str(caught.exception), FAULT)

    def test_inquiry_grounding_and_retrieval_share_one_receipt(self):
        stub = Stub([])
        grounded = lab._ground_inquiry({'question': 'Which residues of human SR-BI bind HDL?', 'uniprot_query': QUERY},
                                       sources.Sources(fetch=stub))
        self.assertEqual(grounded['status'], 'verified')
        count = len(stub.calls)
        receipt = lab._human_identity('SR-BI', sources.Sources(fetch=stub))
        self.assertEqual(receipt['receipt_id'], grounded['receipt_ids'][0])
        self.assertEqual(len(stub.calls), count)


if __name__ == '__main__': unittest.main()

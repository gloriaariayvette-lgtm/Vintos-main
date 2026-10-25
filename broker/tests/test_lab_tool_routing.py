#!/usr/bin/env python3
"""Lab call boundaries: scratch stores and no external action."""
import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import urllib.request

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
TEMP = tempfile.TemporaryDirectory(prefix='lab-tools-routing-')
SCRATCH = Path(TEMP.name).resolve()
os.environ['HOME'] = str(SCRATCH)
os.environ['SPARK_WORKSPACE'] = str(SCRATCH / 'workspace')
os.environ['VINTOS_LAB_CAMPAIGNS'] = '0'
sys.path.insert(0, str(REPO / 'scripts'))
SEND = Mock(side_effect=AssertionError('external action forbidden'))
socket.socket.connect = SEND
socket.socket.connect_ex = SEND
urllib.request.urlopen = SEND
subprocess.Popen = SEND
sys.modules['requests'] = types.SimpleNamespace(get=SEND, post=SEND, request=SEND)
sys.modules['httpx'] = types.SimpleNamespace(get=SEND, post=SEND, request=SEND)


def guard(event, args):
    if event in ('socket.connect', 'socket.sendto', 'subprocess.Popen', 'os.system'):
        raise AssertionError('external action forbidden')
    paths = []
    if event == 'open' and (args[2] or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        paths = [args[0]]
    elif event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod'):
        path = args[0]
        index = 1 if event in ('os.remove', 'os.rmdir') else 2
        fd = args[index] if len(args) > index else -1
        if not isinstance(path, int) and not Path(path).is_absolute() and isinstance(fd, int) and fd >= 0:
            if sys.platform == 'darwin':
                import fcntl
                base = fcntl.fcntl(fd, 50, bytes(1024)).split(b'\0')[0].decode()
            else:
                base = os.readlink('/proc/self/fd/%d' % fd)
            path = Path(base) / path
        paths = [path]
    elif event == 'os.rename': paths = list(args[:2])
    for path in paths:
        if not isinstance(path, int) and not Path(path).resolve().is_relative_to(SCRATCH):
            raise AssertionError('write outside scratch: ' + str(path))


sys.addaudithook(guard)
import chemistry_lab as C
import chemistry_sources as S
import lab_sources as L
import lab_tool_calls as T


class Tools(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.CONFIG).is_relative_to(SCRATCH))
        self.assertTrue(Path(C.NOTEBOOK).is_relative_to(SCRATCH))
        self.assertIs(socket.socket.connect, SEND)
        self.assertIs(urllib.request.urlopen, SEND)
        self.assertIs(sys.modules['requests'].post, SEND)

    def tearDown(self): SEND.assert_not_called()

    def test_atlas_plugin_uses_public_source_with_original_gene(self):
        public, connector = T.normalize_plugin({'plugin':'atlas', 'tool':'atlas.get_asset',
                                                'arguments':{'gene':'SLC26A4'}}, '')
        self.assertEqual(public, {'source':'atlas', 'gene':'SLC26A4'})
        self.assertIsNone(connector)
        with patch.object(S, 'query', return_value={'receipt': {'records':[]}}) as query:
            S.query_plugin('atlas', 'atlas.get_asset', {'gene':'SLC26A4'}, 'regulatory score')
            self.assertEqual(query.call_args.args[0]['gene'], 'SLC26A4')

    def test_pdb_plugin_routes_deposited_entry(self):
        public, _ = T.normalize_plugin({'plugin':'pdb', 'tool':'get_structure', 'arguments':{'pdb_id':'8SGW'}})
        self.assertEqual(public, {'source':'pdb', 'entry_id':'8SGW', 'operation':'structure_evidence'})

    def test_wrong_plugin_owner_does_not_change_boltz_operation(self):
        public, connector = T.normalize_plugin({'plugin':'pdb', 'tool':'pdb.boltz_get_structure_and_binding_prediction',
                                                'arguments':{'job_id':'original'}})
        self.assertIsNone(public)
        self.assertEqual(connector['plugin'], 'boltz')
        self.assertEqual(connector['tool'], 'boltz_get_structure_and_binding_prediction')
        self.assertEqual(connector['arguments'], {'job_id':'original'})

    def test_connector_written_as_source_reaches_connector_dispatch(self):
        inquiry = C._inquiry({'question':'Measure similarity of these sourced molecules', 'source_query':{
            'source':'nvmolkit','operation':'nvmolkit.similarity','arguments':{'smiles':['CCO','CCN']}}})
        self.assertIsNone(inquiry['source_query'])
        self.assertEqual(inquiry['plugin_query'], {'plugin':'nvmolkit','tool':'nvmolkit.similarity',
                                                  'arguments':{'smiles':['CCO','CCN']}})

    def test_paid_operation_stays_paid_and_policy_withheld(self):
        _, connector = T.normalize_plugin({'plugin':'pdb', 'tool':'boltz_start_structure_and_binding', 'arguments':{}})
        import claude_connector_catalog as catalog
        with self.assertRaises(PermissionError):
            catalog.policy(connector['plugin'], 'lab', connector['tool'])

    def test_ncbi_alias_keeps_target_and_scope(self):
        spec = L.normalize_source_spec({'source':'ncbi', 'operation':'search_proteins',
                                        'query':'recombinase', 'organism':'Planctomycetes'})
        self.assertEqual(spec['operation'], 'protein')
        self.assertEqual(spec['term'], 'recombinase')
        self.assertEqual(spec['organism'], 'Planctomycetes')
        with self.assertRaisesRegex(ValueError, 'unknown NCBI operation'):
            L.Sources(fetch=SEND).query({'source':'ncbi','operation':'invented_operation'})

    def test_invalid_asset_is_not_turned_into_guessed_gene(self):
        public, _ = T.normalize_plugin({'plugin':'atlas','tool':'get_asset','arguments':{'asset_id':'asset-1'}})
        self.assertIsNone(public)

    def test_explicit_measurement_is_not_broad_subject_search(self):
        inquiry = {'question':'Measure SLC26A4 complex confidence', 'plugin_query':{
            'plugin':'nvidia_nim','tool':'nvidia_nim.boltz2','arguments':{'polymers':[]}}}
        self.assertFalse(C.spent_retrieval(inquiry, {'subjects':['SLC26A4']}))
        # The separate lookup gate still sees an identical measurement request.
        import lab_repeats
        with patch.object(lab_repeats, 'LOOKUPS', str(SCRATCH/'lookups.jsonl')):
            lab_repeats.record(inquiry)
            self.assertIn('exact lookup', lab_repeats.repeat(inquiry))

    def test_switches_save_only_explicit_settings(self):
        for setter, key in ((C.set_enabled, 'enabled'), (C.set_evo2_enabled, 'evo2_enabled'),
                            (C.set_atlas_evo2_enabled, 'atlas_evo2_enabled')):
            with self.subTest(key=key), patch.object(C, 'status', return_value={}):
                C._atomic(C.CONFIG, {'alphagenome_python':'configured-python'})
                setter(True)
                raw = C._load(C.CONFIG, {})
                self.assertTrue(raw[key])
                self.assertEqual(raw['alphagenome_python'], 'configured-python')
                self.assertNotIn('coverage_context_tokens', raw)
                for untouched in ('enabled', 'evo2_enabled', 'atlas_evo2_enabled'):
                    if untouched != key: self.assertNotIn(untouched, raw)

    def test_observed_source_shorthands_retain_exact_identifiers(self):
        for request,expected in [({'uniprot':'P69905'},{'source':'uniprot','query':'accession:P69905'}),
                                 ({'interpro':'P69905'},{'source':'interpro','accession':'P69905'}),
                                 ({'source':'','pdb':'8SGW'},{'source':'pdb','entry_id':'8SGW'}),
                                 # 22 October: the Lab asked this way and failed "PDB entry ID required" each time
                                 ({'source':'pdb','query':'entry_id:6V7X'},{'source':'pdb','entry_id':'6V7X'}),
                                 ({'source':'pdb','pdb_id':'6v7x'},{'source':'pdb','entry_id':'6V7X'}),
                                 ({'source':'pdb','query':'reverse transcriptase'},{'source':'pdb','query':'reverse transcriptase'})]:
            self.assertEqual(T.normalize_request('source',request),expected)

    def test_pubmed_shorthand_reads_the_named_citation_without_a_search(self):
        # A retained failed step used this shape. An exact citation must reach
        # the article reader without a keyword search or an inferred identifier.
        spec = T.normalize_request('source', {'pubmed': '36115831'})
        xml = ('<PubmedArticleSet><PubmedArticle><MedlineCitation>'
               '<PMID>36115831</PMID><Article><ArticleTitle>Fixture</ArticleTitle>'
               '<Abstract><AbstractText>Measured fixture result.</AbstractText></Abstract>'
               '</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>')
        read = Mock(return_value=xml)
        result = L.Sources(fetch=SEND, fetch_record=read).query(spec)
        self.assertEqual([r['pmid'] for r in result['records']], ['36115831'])
        self.assertIn('efetch.fcgi?', read.call_args.args[0])
        self.assertIn('id=36115831', read.call_args.args[0])
        self.assertEqual(result['query']['pmids'], ['36115831'])
        read.assert_called_once()

    def test_pubmed_shorthand_search_keeps_the_authored_phrase(self):
        phrase = 'bacteriophage "reverse transcriptase" CRISPR-Cas'
        spec = T.normalize_request('source', {'pubmed': phrase})
        with patch.object(L.Sources, '_abstracts', return_value={'records': []}) as read:
            L.Sources(fetch=SEND).query(spec)
        self.assertEqual(spec, {'source': 'pubmed', 'query': phrase})
        self.assertTrue(read.called)

    def test_a_request_with_no_source_field_reaches_the_source_it_names(self):
        # 24-25 October: 72 steps were recorded with an empty source and refused "unsupported Lab source"; these are
        # their shapes (identifiers replaced by fixtures of the same form)
        for request, expected in [
                ({'pubmed': "bacteriophage 'CRISPR' 'reverse transcriptase' genome"},
                 {'source': 'pubmed', 'query': "bacteriophage 'CRISPR' 'reverse transcriptase' genome"}),
                ({'accession': 'NC_000913.3', 'operation': 'rt_locus_screen'},
                 {'source': 'rt_locus_screen', 'accession': 'NC_000913.3'}),
                ({'accession': 'NC_000913.3', 'anchor_start': 0, 'anchor_end': 325, 'operation': 'ncbi_neighborhood'},
                 {'source': 'ncbi_neighborhood', 'accession': 'NC_000913.3', 'anchor_start': 0, 'anchor_end': 325}),
                ({'query': 'accession:O43511'}, {'source': 'uniprot', 'query': 'accession:O43511'}),
                ({'source': '', 'query': 'accession:Q86SQ4'}, {'source': 'uniprot', 'query': 'accession:Q86SQ4'})]:
            self.assertEqual(T.normalize_request('source', request), expected)
        # a query that names no source still names none: nothing is guessed
        for request in ({'query': 'reverse transcriptase'}, {'query': 'accession:not-an-accession'},
                        {'query': 'accession:O43511', 'term': 'x'}, {'operation': 'search_genes', 'term': 'x'}):
            spec = T.normalize_request('source', dict(request))
            self.assertEqual(spec['source'], '', request)
            with self.assertRaisesRegex(ValueError, 'unsupported Lab source'):
                L.Sources(fetch=SEND).query(spec)
        # the source named as operation is then checked as that source: a GI is not an accession.version
        with self.assertRaisesRegex(ValueError, 'accession.version required'):
            L.Sources(fetch=SEND).query(T.normalize_request('source', {'accession': '3042852874',
                                                                       'operation': 'rt_locus_screen'}))

    def test_an_ncbi_protein_accession_asked_of_uniprot_reads_its_ncbi_record(self):
        # 24-25 October: an NCBI protein search returned DBB25069.1, the next step asked UniProt for
        # "accession:DBB25069.1", and UniProt answered HTTP 400 every time
        spec = T.normalize_request('source', {'query': 'accession:DBB25069.1', 'source': 'uniprot'})
        self.assertEqual(spec, {'source': 'ncbi_protein_context', 'accession': 'DBB25069.1'})
        asked = []
        def record(url):
            asked.append(url); raise RuntimeError('stop: fixture')
        with self.assertRaisesRegex(RuntimeError, 'fixture'):
            L.Sources(fetch=SEND, fetch_record=record).query(T.execution_request('source', spec))
        self.assertIn('db=protein', asked[0]); self.assertIn('id=DBB25069.1', asked[0])
        self.assertEqual(T.normalize_request('source', {'source': 'uniprot', 'accession': 'NP_000483.3'}),
                         {'source': 'ncbi_protein_context', 'accession': 'NP_000483.3'})
        # UniProt accessions, isoforms, and anything not a protein accession.version stay UniProt's
        for query in ('accession:P01130', 'P01130', 'accession:P01130-2', 'accession:NC_000913.3',
                      'gene:SLC26A4 AND taxonomy_id:9606', 'accession:DBB25069'):
            self.assertEqual(T.normalize_request('source', {'source': 'uniprot', 'query': query})['source'], 'uniprot', query)

    def test_pubmed_literature_operation_stays_the_public_search(self):
        # 23-25 October: this shape went to the PubMed connector as "pubmed.literature" and was refused by its
        # policy, 25 times; the public search reads it
        authored = {'operation': 'literature', 'source': 'pubmed',
                    'term': 'bacteriophage "CRISPR" "reverse transcriptase" genome'}
        inquiry = T.normalize_inquiry({'question': 'Which phages carry an RT beside CRISPR?', 'source_query': authored})
        self.assertEqual(inquiry['source_query'], authored)
        self.assertFalse(inquiry.get('plugin_query'))
        with patch.object(L.Sources, '_abstracts', return_value={'records': []}) as read:
            L.Sources(fetch=SEND).query(inquiry['source_query'])
        self.assertEqual(read.call_args.args[0]['terms'], ['bacteriophage', 'CRISPR', 'reverse', 'transcriptase', 'genome'])
        # ChEMBL's public target search the same way; the connectors' own tools still reach the connectors
        chembl = {'source': 'chembl', 'operation': 'search_targets', 'term': 'CFTR'}
        self.assertEqual(T.normalize_inquiry({'question': 'q', 'source_query': chembl})['source_query'], chembl)
        for sq, plugin in (({'source': 'pubmed', 'operation': 'search_articles', 'term': 'x'}, 'pubmed'),
                           ({'source': 'chembl', 'tool': 'chembl_search_targets', 'arguments': {'target_name': 'CFTR'}},
                            'chembl'),
                           ({'source': 'nvmolkit', 'operation': 'nvmolkit.similarity', 'arguments': {}}, 'nvmolkit')):
            self.assertEqual(T.normalize_inquiry({'question': 'q', 'source_query': sq})['plugin_query']['plugin'], plugin)

    def test_pubmed_query_under_the_sources_own_name_is_searched(self):
        # 25 October: refused "one or more plain search terms required", the words sitting under "pubmed"
        phrase = 'bacteriophage "CRISPR-Cas" AND "reverse transcriptase" AND (retrotransposon OR pol-like)'
        spec = T.normalize_request('source', {'pubmed': phrase, 'source': 'pubmed'})
        self.assertEqual(spec, {'source': 'pubmed', 'query': phrase})
        with patch.object(L.Sources, '_abstracts', return_value={'records': []}) as read:
            L.Sources(fetch=SEND).query(spec)
        self.assertEqual(read.call_args.args[0]['terms'],
                         ['bacteriophage', 'CRISPR-Cas', 'reverse', 'transcriptase', 'retrotransposon', 'pol-like'])
        # anything else beside the source keeps its own meaning
        self.assertEqual(T.normalize_request('source', {'source': 'pubmed', 'query': 'x', 'pubmed': 'y'})['query'], 'x')

    def test_a_structure_without_a_pubmed_citation_still_gets_its_reading(self):
        # 25 October, 1V4Z: RCSB's primary_citation carries pdbx_database_id_PubMed -1 when there is none; the
        # reading failed whole as "one to six exact PubMed IDs required", twice
        def state(pmid):
            return {'additional_source': {'receipt': {'source': 'pdb', 'records': [
                {'primary_citation': {'pdbx_database_id_PubMed': pmid}}]}}}
        with patch.object(S, 'material', return_value={'records': [{'pmid': '1'}]}) as material:
            self.assertTrue(C._gather_material(state(-1), {'question': 'q'}))
            self.assertEqual(material.call_args.kwargs, {})
            C._gather_material(state(15302935), {'question': 'q'})
            self.assertEqual(material.call_args.kwargs, {'primary_pmids': ['15302935']})
            C._gather_material(state(None), {'question': 'q'})
            self.assertEqual(material.call_args.kwargs, {})

    def test_named_model_reader_reaches_validation_with_generic_viewer_skill(self):
        import lab_instruments
        model = 'artifacts/esmfold/fixture.pdb'
        request = T.normalize_request('instrument', {'skill': 'structure_viewer',
            'operation': 'fold_read', 'files': [model], 'question': 'Read the retained model helices.'})
        with patch.object(lab_instruments, 'artifacts', return_value=[model]):
            skill, operation, files, question = lab_instruments.validate(request)
        self.assertEqual((skill, operation, files), ('fold_read', 'structure.read', [model]))
        self.assertEqual(question, request['question'])
        request['files'] = ['/etc/passwd']
        with self.assertRaisesRegex(ValueError, 'artifacts the Lab listed'):
            lab_instruments.validate(request)

    def test_same_question_may_use_distinct_instruments_but_not_repeat_one(self):
        import lab_repeats
        question='Measure the resulting energy against the same exact reference.'
        first={'question':question,'instrument_query':{'skill':'house_experiment_molecule','operation':'molecule'}}
        second={'question':question,'instrument_query':{'skill':'house_experiment_fold','operation':'fold'}}
        with patch.object(lab_repeats,'LOOKUPS',str(SCRATCH/'distinct-instruments.jsonl')):
            lab_repeats.record(first)
            self.assertFalse(lab_repeats.repeat(second))
            self.assertIn('exact lookup',lab_repeats.repeat(first))

    def test_guard_blocks_live_store_write(self):
        with self.assertRaisesRegex(AssertionError, 'write outside scratch'):
            open('/tmp/not-this-test-store', 'w')


if __name__ == '__main__': unittest.main(verbosity=2)

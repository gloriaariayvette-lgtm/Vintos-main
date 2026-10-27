#!/usr/bin/env python3
"""Public sequencing runs, the bounded read sample, and the Adaptyv Bio connector. Recorded shapes only: no network,
no relay, no account. Every path the modules write is in a scratch workspace, asserted below."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
SCRATCH = tempfile.TemporaryDirectory(prefix='lab-sequencing-test-')
os.environ['HOME'] = SCRATCH.name
os.environ['SPARK_WORKSPACE'] = SCRATCH.name + '/workspace'
os.environ['VINTOS_MEMORY'] = SCRATCH.name + '/workspace/memory'
import lab_sources as sources
import lab_sequencing as seq
import lab_instruments
import lab_tool_calls
import plugin_catalog
import plugin_gateway
import plugin_relay_remote as remote

# ENA portal read_run row as the API returns it (format=json: every value a string), shape of 2026-10.
ROW = {'run_accession': 'SRR8000001', 'experiment_accession': 'SRX5000001', 'study_accession': 'PRJNA500001',
       'secondary_study_accession': 'SRP160001', 'sample_accession': 'SAMN10000001',
       'scientific_name': 'Thermus thermophilus', 'tax_id': '274', 'instrument_platform': 'ILLUMINA',
       'instrument_model': 'Illumina HiSeq 2500', 'library_layout': 'PAIRED', 'library_strategy': 'WGS',
       'library_source': 'GENOMIC', 'read_count': '2500000', 'base_count': '750000000',
       'fastq_ftp': 'ftp.sra.ebi.ac.uk/vol1/fastq/SRR800/001/SRR8000001/SRR8000001_1.fastq.gz;'
                    'ftp.sra.ebi.ac.uk/vol1/fastq/SRR800/001/SRR8000001/SRR8000001_2.fastq.gz',
       'fastq_bytes': '180000000;190000000',
       'fastq_md5': '0123456789abcdef0123456789abcdef;fedcba9876543210fedcba9876543210',
       'first_public': '2018-09-20'}


def fastq_gz(n, members=1, length=100):
    text = b''.join(b'@SRR8000001.%d %d length=%d\n%s\n+\n%s\n' % (i, i, length, b'ACGTN' * (length // 5), b'I' * length)
                    for i in range(1, n + 1))
    if members == 1:
        return gzip.compress(text, mtime=0)
    cut = len(text) // 2
    cut = text.index(b'\n@', cut) + 1
    return gzip.compress(text[:cut], mtime=0) + gzip.compress(text[cut:], mtime=0)


class Stream(io.BytesIO):
    """A response read in pieces; counts what was asked for."""
    def __init__(self, data):
        super().__init__(data); self.asked = 0
    def read(self, n=-1):
        out = super().read(n); self.asked += len(out); return out


class Sequencing(unittest.TestCase):
    def setUp(self):
        self.net = mock.patch.object(sources, 'open_request', side_effect=AssertionError('live network forbidden'))
        self.net.start(); self.addCleanup(self.net.stop)
        self.assertTrue(seq.sample_dir().is_relative_to(SCRATCH.name))
        self.assertTrue(lab_instruments.ARTIFACTS.is_relative_to(SCRATCH.name))
        self.assertTrue(Path(plugin_gateway.MEMORY).is_relative_to(SCRATCH.name))
        self.urls = []

    def client(self, rows=None, ncbi=None, stream=None):
        def fetch(url):
            self.urls.append(url)
            if url.startswith(seq.ENA_PORTAL):
                return list(rows if rows is not None else [ROW]), {}
            if url.startswith(seq.NCBI_BASE + 'esearch') and ncbi is not None:
                return {'esearchresult': {'count': '1', 'idlist': ['9000001']}}, {}
            if url.startswith(seq.NCBI_BASE + 'esummary') and ncbi is not None:
                return {'result': {'uids': ['9000001'], '9000001': {
                    'expxml': '<Summary><Title>thermophile genome</Title></Summary>',
                    'runs': '<Run acc="SRR8000001" total_spots="2500000" total_bases="750000000" load_done="true"/>'}}}, {}
            raise AssertionError(url)
        opened = []
        def open_stream(url):
            opened.append(url)
            return stream if stream is not None else Stream(fastq_gz(30))
        client = sources.Sources(fetch=fetch, open_stream=open_stream)
        client.opened = opened
        return client

    def test_runs_by_accession_keep_metadata_and_file_locations(self):
        out = self.client().query({'source': 'sequencing_runs', 'accession': 'prjna500001', 'limit': 2})
        q = parse_qs(urlsplit(self.urls[0]).query)
        self.assertEqual(q['accession'], ['PRJNA500001']); self.assertEqual(q['result'], ['read_run'])
        rec = out['records'][0]
        self.assertEqual((rec['read_count'], rec['tax_id'], rec['library_layout']), (2500000, 274, 'PAIRED'))
        self.assertEqual([f['mate'] for f in rec['files']], [1, 2])
        self.assertTrue(rec['files'][0]['url'].startswith('https://ftp.sra.ebi.ac.uk/vol1/fastq/'))
        self.assertEqual(rec['files'][0]['bytes'], 180000000)
        self.assertEqual(out['metadata']['service'], 'ENA_Portal_filereport')
        self.assertEqual(out['truth_status'], 'source_observation_not_validation')
        with self.assertRaisesRegex(ValueError, 'do not belong'):
            self.client().query({'source': 'sequencing_runs', 'accession': 'PRJNA999999'})

    def test_search_by_organism_and_by_term(self):
        client = self.client(ncbi=True)
        client._taxon = lambda spec: '274'
        out = client.query({'source': 'sequencing_runs', 'organism': 'Thermus thermophilus', 'platform': 'illumina',
                            'layout': 'paired', 'strategy': 'wgs', 'limit': 3})
        q = parse_qs(urlsplit(self.urls[-1]).query)['query'][0]
        self.assertEqual(q, 'tax_tree(274) AND instrument_platform="ILLUMINA" AND library_layout="PAIRED" '
                            'AND library_strategy="WGS"')
        self.assertEqual(out['records'][0]['run_accession'], 'SRR8000001')
        self.urls.clear()
        out = client.query({'source': 'sequencing_runs', 'term': 'thermophile genome (heat)', 'limit': 2})
        self.assertIn('db=sra', self.urls[0])
        self.assertEqual(parse_qs(urlsplit(self.urls[-1]).query)['query'][0], '(run_accession="SRR8000001")')
        self.assertEqual(out['metadata']['via']['runs_named'], ['SRR8000001'])

    def test_validation_precedes_the_network(self):
        client = sources.Sources(fetch=lambda url: (_ for _ in ()).throw(AssertionError('network reached')),
                                 open_stream=lambda url: (_ for _ in ()).throw(AssertionError('stream opened')))
        for spec in ({'source': 'sequencing_runs'}, {'source': 'sequencing_runs', 'accession': 'SRR12'},
                     {'source': 'sequencing_runs', 'accession': 'SRR8000001', 'term': 'x y z'},
                     {'source': 'sequencing_runs', 'term': 'soil', 'platform': 'telepathy'},
                     {'source': 'sequencing_runs', 'term': 'soil', 'limit': 99},
                     {'source': 'sequencing_runs', 'term': 'soil', 'url': 'https://example.test'},
                     {'source': 'sequencing_reads', 'run_accession': 'SRX5000001'},
                     {'source': 'sequencing_reads', 'run_accession': 'SRR8000001', 'reads': 50001},
                     {'source': 'sequencing_reads', 'run_accession': 'SRR8000001', 'mate': 3}):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                client.query(spec)

    def test_a_file_location_outside_enas_fastq_archive_is_never_read(self):
        for bad in ('evil.test/vol1/fastq/x.fastq.gz', 'ftp.sra.ebi.ac.uk/vol1/fastq/../../etc/passwd.fastq.gz',
                    'ftp.sra.ebi.ac.uk/vol1/run/x.bam'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                seq.file_url(bad)
        row = dict(ROW, fastq_ftp='evil.test/vol1/fastq/SRR8000001_1.fastq.gz', fastq_bytes='1', fastq_md5='')
        client = self.client(rows=[row])
        with self.assertRaisesRegex(ValueError, 'no FASTQ file'):
            client.query({'source': 'sequencing_reads', 'run_accession': 'SRR8000001'})
        self.assertEqual(client.opened, [])

    def test_read_sample_is_bounded_kept_as_an_artifact_and_reused(self):
        whole = fastq_gz(5000, members=2)
        stream = Stream(whole)
        client = self.client(stream=stream)
        with mock.patch.object(seq, 'CHUNK', 1024):
            out = client.query({'source': 'sequencing_reads', 'run_accession': 'SRR8000001', 'reads': 1200, 'mate': 2})
        rec = out['records'][0]
        self.assertTrue(client.opened[0].endswith('SRR8000001_2.fastq.gz'))
        self.assertEqual((rec['reads_kept'], rec['stopped_by'], rec['mate']), (1200, 'requested_reads', 2))
        self.assertLess(stream.asked, len(whole),'stopped reading once it had the reads')
        path = seq.lab_root() / rec['artifact']
        blob = path.read_bytes()
        self.assertEqual(hashlib.sha256(blob).hexdigest(), rec['artifact_sha256'])
        text = gzip.decompress(blob)
        self.assertEqual(text.count(b'\n'), 4 * 1200)
        self.assertEqual(hashlib.sha256(text).hexdigest(), rec['sample_fastq_sha256'])
        self.assertEqual(os.stat(path).st_mode & 0o077, 0)
        provenance = json.loads(Path(str(path) + '.provenance.json').read_text())
        self.assertEqual(provenance['selection'], 'first_reads_of_one_file_not_a_random_sample')
        self.assertEqual(provenance['provider_file_md5'], 'fedcba9876543210fedcba9876543210')
        self.assertIn('not a random sample', out['metadata']['selection'])
        # the same request again reads nothing: the sample is held
        again = self.client(stream=Stream(b'not gzip'))
        out2 = again.query({'source': 'sequencing_reads', 'run_accession': 'SRR8000001', 'reads': 1200, 'mate': 2})
        self.assertTrue(out2['records'][0]['reused_existing_sample']); self.assertEqual(again.opened, [])
        # and the sample is what the instruments are offered
        self.assertIn(rec['artifact'], lab_instruments.read_samples())
        self.assertIn(rec['artifact'], lab_instruments.artifacts('sequence', 50))
        menu = lab_instruments.planner_menu()
        if menu.get('runs_left_today'):
            self.assertIn(rec['artifact'], menu['skills']['ngs_workbench']['files'])
            self.assertIn(rec['artifact'], menu['skills']['sequence_viewer']['files'])
        req = {'skill': 'ngs_workbench', 'operation': 'plan_nextflow', 'files': [rec['artifact']],
               'question': 'plan a read QC workflow over this sample'}
        self.assertEqual(lab_instruments.validate(req)[0], 'ngs_workbench')
        with self.assertRaises(ValueError):
            lab_instruments.validate(dict(req, operation='execute_plan'))
        # the relay gateway takes it as a digest-verified input within its limits
        inputs = plugin_gateway._skill_inputs([str(path)])
        self.assertEqual(inputs[0]['sha256'], rec['artifact_sha256'])
        self.assertLessEqual(inputs[0]['bytes'], seq.MAX_ARTIFACT_BYTES)
        self.assertLess(seq.MAX_ARTIFACT_BYTES, plugin_gateway.MAX_SKILL_INPUT_BYTES)

    def test_caps_on_reads_text_and_download(self):
        _, stats = seq.first_reads(Stream(fastq_gz(10)), 50)
        self.assertEqual((stats['reads_kept'], stats['stopped_by']), (10, 'end_of_file'))
        with mock.patch.object(seq, 'MAX_SAMPLE_TEXT_BYTES', 2000):
            text, stats = seq.first_reads(Stream(fastq_gz(100)), 100)
        self.assertLessEqual(len(text), 2000); self.assertEqual(stats['stopped_by'], 'sample_text_cap')
        with mock.patch.object(seq, 'MAX_COMPRESSED_BYTES', 300), mock.patch.object(seq, 'CHUNK', 100):
            s = Stream(fastq_gz(4000))
            _, stats = seq.first_reads(s, 4000)
            self.assertEqual(stats['stopped_by'], 'download_cap')
            self.assertLess(stats['reads_kept'], 4000)
            self.assertLessEqual(s.asked, 300)
        with self.assertRaisesRegex(ValueError, 'not FASTQ'):
            seq.first_reads(Stream(gzip.compress(b'>fasta\nACGT\n>x\nAC\n')), 5)

    def test_daily_sample_cap(self):
        with mock.patch.object(seq, 'MAX_SAMPLES_PER_DAY', 0):
            with self.assertRaisesRegex(RuntimeError, 'used up'):
                self.client().query({'source': 'sequencing_reads', 'run_accession': 'SRR8000001', 'reads': 7})

    def test_planner_shapes_normalize_to_the_two_sources(self):
        n = lab_tool_calls.normalize_request
        self.assertEqual(n('source', {'source': 'ena', 'run_accession': 'SRR8000001', 'reads': 100})['source'],
                         'sequencing_reads')
        self.assertEqual(n('source', {'source': 'sra', 'query': 'PRJNA500001'}),
                         {'source': 'sequencing_runs', 'accession': 'PRJNA500001'})
        self.assertEqual(n('source', {'sequencing_runs': 'SRR8000001'}),
                         {'source': 'sequencing_runs', 'accession': 'SRR8000001'})
        self.assertEqual(n('source', {'sequencing_reads': 'SRR8000001'}),
                         {'source': 'sequencing_reads', 'run_accession': 'SRR8000001'})
        public, connector = lab_tool_calls.normalize_plugin({'plugin': 'ena', 'tool': 'search',
                                                             'arguments': {'accession': 'SRR8000001'}})
        self.assertEqual((public['source'], connector), ('sequencing_runs', None))


class Adaptyv(unittest.TestCase):
    def test_policy_is_read_only_and_in_the_lab_menu(self):
        entry = plugin_catalog.PLUGINS['adaptyv_bio']
        for tool in entry['tools']:
            bare = tool.split('.', 1)[1]
            self.assertTrue(bare.startswith(('list_', 'get_')), tool)
            self.assertNotIn(bare, entry['withheld'])
        for tool in ('cost_estimate', 'create_exp', 'submit_experiment', 'confirm_quote', 'pay_invoice', 'add_sequences'):
            with self.subTest(tool=tool), self.assertRaises(PermissionError):
                plugin_gateway.call('lab', 'adaptyv_bio', 'adaptyv_bio.' + tool, {}, 'test',
                                    transport=lambda _: self.fail('transport reached'))
        with self.assertRaises(PermissionError):
            plugin_gateway.call('wants', 'adaptyv_bio', 'adaptyv_bio.list_targets', {}, 'test',
                                transport=lambda _: self.fail('transport reached'))
        lab = plugin_catalog.instructions('lab')['connectors']['adaptyv_bio']
        self.assertIn('adaptyv_bio.list_targets', lab['tools']); self.assertFalse(lab['tools_verified'])
        self.assertIn('not clinical facts', lab['limits'])
        self.assertIn('"adaptyv_bio"', plugin_catalog.prompt_instructions('lab'))
        self.assertNotIn('adaptyv_bio', plugin_catalog.instructions('wants')['connectors'])
        self.assertEqual(lab_tool_calls.normalize_plugin({'plugin': 'Adaptive', 'tool': 'list_targets',
                                                          'arguments': {}})[1]['tool'], 'adaptyv_bio.list_targets')

    def test_gateway_call_stores_a_receipt_in_scratch(self):
        seen = {}
        def transport(request):
            seen.update(request)
            return {'ok': True, 'result': {'structuredContent': {'targets': [{'id': 't1'}]}, 'isError': False}}
        out = plugin_gateway.call('lab', 'adaptyv_bio', 'adaptyv_bio.list_targets', {'limit': 1}, 'commissioning',
                                  transport=transport)
        self.assertEqual(seen['tool'], 'adaptyv_bio.list_targets')
        self.assertTrue(out['receipt']['artifact'].startswith(SCRATCH.name))

    def test_relay_calls_its_own_server_by_the_bare_name(self):
        calls = []
        def rpc(proc, ident, method, params, timeout=60):
            calls.append((method, params))
            if method == 'thread/start': return {'result': {'thread': {'id': 'T'}}}
            if method == 'mcpServer/tool/call': return {'result': {'structuredContent': {'targets': []}}}
            return {'result': {}}
        proc = mock.Mock(); proc.stdin = mock.Mock(); proc.stdout = mock.Mock()
        with mock.patch.object(remote.Path, 'is_file', return_value=True), \
             mock.patch.object(remote.subprocess, 'Popen', return_value=proc), \
             mock.patch.object(remote, '_rpc', side_effect=rpc):
            remote.connector({'surface': 'lab', 'plugin': 'adaptyv_bio', 'tool': 'adaptyv_bio.list_targets',
                              'arguments': {'limit': 1}, 'purpose': 'test'})
            remote.connector({'surface': 'lab', 'plugin': 'github', 'tool': 'github.get_profile',
                              'arguments': {}, 'purpose': 'test'})
        tool_calls = [p for m, p in calls if m == 'mcpServer/tool/call']
        self.assertEqual((tool_calls[0]['server'], tool_calls[0]['tool']), ('adaptyv-bio', 'list_targets'))
        self.assertEqual((tool_calls[1]['server'], tool_calls[1]['tool']), ('codex_apps', 'github.get_profile'))

    def test_relay_listing_reads_the_adaptyv_server_and_calls_nothing(self):
        seen = []
        def rpc(proc, ident, method, params, timeout=60):
            seen.append(method)
            if method == 'mcpServerStatus/list':
                return {'result': {'data': [
                    {'name': 'codex_apps', 'tools': {'gmail.get_profile': {'inputSchema': {'type': 'object'}}}},
                    {'name': 'adaptyv-bio', 'authStatus': 'oAuth', 'tools': {
                        'list_targets': {'inputSchema': {'type': 'object', 'properties': {'limit': {'type': 'integer'}}}},
                        'submit_experiment': {'inputSchema': {'type': 'object'}}}}]}}
            return {'result': {}}
        proc = mock.Mock(); proc.stdin = mock.Mock(); proc.stdout = mock.Mock()
        with mock.patch.object(remote.Path, 'is_file', return_value=True), \
             mock.patch.object(remote.subprocess, 'Popen', return_value=proc), \
             mock.patch.object(remote, '_rpc', side_effect=rpc), mock.patch.object(remote.time, 'sleep'):
            out = remote.handle({'action': 'schema', 'plugin': 'adaptyv_bio'})
        self.assertEqual(sorted(out['schemas']), ['list_targets', 'submit_experiment'])
        self.assertNotIn('mcpServer/tool/call', seen)

    def test_confirm_probe_is_never_run_by_the_suite_and_names_the_read(self):
        text = (REPO / 'scripts' / 'probes' / 'adaptyv_confirm.py').read_text()
        self.assertIn('tool_schemas(PLUGIN)', text); self.assertIn('"list_targets"', text)
        self.assertIn('--list-only', text)


if __name__ == '__main__':
    unittest.main()

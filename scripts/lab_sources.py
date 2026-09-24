"""Bounded, read-only Lab sources. Receipts describe observations, never validation.

All network entry points are injectable. No keys, requests, or stores at import.
Atlas uses Google's SDK in a deadline-limited child, not an invented REST API.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request
from lab_http import open_request

MAX_BYTES = 2 * 1024 * 1024
FIELDS = frozenset('accession id reviewed length protein_name gene organism_id organism_name taxonomy_id keyword go xref_pdb'.split())
NCBI_BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
BV_BRC_BASE = 'https://www.bv-brc.org/api/'
INTERPRO_BASE = 'https://www.ebi.ac.uk/interpro/api/'
NCBI_DATABASES = {'taxonomy': 'taxonomy', 'assembly': 'assembly',
                  'gene': 'gene', 'protein': 'protein', 'literature': 'pubmed'}


def _plain_term(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .,'_-]{2,119}", value):
        raise ValueError('use 3..120 plain search characters, without Entrez operators')
    return value.strip()


def _taxon_id(value):
    if isinstance(value, bool) or not re.fullmatch(r'[1-9][0-9]{0,9}', str(value)):
        raise ValueError('sourced numeric NCBI taxon_id required')
    return str(value)


def _genome_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,9}\.[1-9][0-9]{0,7}', value):
        raise ValueError('sourced BV-BRC genome_id required')
    return value


def _ncbi_accession(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z]{1,6}_?[A-Z0-9]{3,15}\.[1-9][0-9]*', value):
        raise ValueError('exact sourced NCBI accession.version required')
    return value


def _uniprot_accession(value):
    value = str(value or '').upper()
    if not re.fullmatch(r'[A-Z0-9]{6,10}(?:-[1-9][0-9]*)?', value):
        raise ValueError('exact sourced UniProt accession required')
    return value


def validate_uniprot(query):
    if not isinstance(query, str) or not query.strip() or len(query) > 600:
        raise ValueError('bounded UniProt query required')
    fields = re.findall(r'\b([A-Za-z_][A-Za-z_0-9]*):', query)
    unknown = set(fields) - FIELDS
    if unknown: raise ValueError('unsupported UniProt fields: ' + ', '.join(sorted(unknown)))
    if any(ord(c) < 32 for c in query) or query.count('(') != query.count(')') or query.count('[') != query.count(']') or query.count('"') % 2:
        raise ValueError('malformed UniProt query')
    return query


def fetch_json(url, *, transport=None):
    # URLs are constructed by the clients, never accepted from a model.
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'Vintos-Lab/2.0'})
    with (transport or open_request)(request, timeout=30) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES: raise ValueError('source response exceeds limit')
        return json.loads(body), dict(response.headers)


def fetch_text(url, *, transport=None):
    request = Request(url, headers={'Accept': 'text/plain', 'User-Agent': 'Vintos-Lab/2.0'})
    with (transport or open_request)(request, timeout=30) as response:
        body = response.read(16 * 1024 + 1)
        if len(body) > 16 * 1024: raise ValueError('sequence response exceeds limit')
        return body.decode('ascii')


def fetch_record(url, *, transport=None):
    request = Request(url, headers={'Accept': 'application/xml', 'User-Agent': 'Vintos-Lab/2.0'})
    with (transport or open_request)(request, timeout=30) as response:
        body = response.read(512 * 1024 + 1)
        if len(body) > 512 * 1024: raise ValueError('sequence record exceeds limit')
        return body.decode('utf-8')


def _gbseq(xml, expected):
    try: root = ET.fromstring(xml)
    except ET.ParseError as exc: raise ValueError('NCBI returned malformed sequence XML') from exc
    node = root.find('.//GBSeq')
    if node is None: raise ValueError('NCBI returned no sequence record')
    accession = node.findtext('GBSeq_accession-version') or ''
    if accession != expected: raise ValueError('NCBI sequence accession did not match request')
    features = []
    for feature in node.findall('./GBSeq_feature-table/GBFeature')[:96]:
        quals = {}
        for qual in feature.findall('./GBFeature_quals/GBQualifier'):
            name, value = qual.findtext('GBQualifier_name'), qual.findtext('GBQualifier_value')
            if name in ('gene','product','protein_id','locus_tag','coded_by','note') and value:
                quals.setdefault(name, []).append(value[:500])
        features.append({'key': feature.findtext('GBFeature_key') or '',
                         'location': (feature.findtext('GBFeature_location') or '')[:200],
                         'qualifiers': quals})
    return {'accession': accession, 'definition': (node.findtext('GBSeq_definition') or '')[:500],
            'organism': (node.findtext('GBSeq_organism') or '')[:300],
            'taxonomy': (node.findtext('GBSeq_taxonomy') or '')[:800],
            'length': int(node.findtext('GBSeq_length') or 0),
            'sequence': (node.findtext('GBSeq_sequence') or '').upper(), 'features': features}


def receipt(source, query, records, *, metadata=None):
    encoded = json.dumps(records, sort_keys=True, allow_nan=False).encode()
    if len(encoded) > MAX_BYTES: raise ValueError('source response exceeds limit')
    result = {'source': source, 'query': query, 'records': records,
              'retrieved_at': datetime.now(timezone.utc).isoformat(),
              'response_sha256': hashlib.sha256(encoded).hexdigest(),
              'metadata': metadata or {}, 'truth_status': 'source_observation_not_validation',
              'literature_coverage': 'not_assessed', 'novelty': 'not_established'}
    result['receipt_id'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


class Sources:
    def __init__(self, fetch=fetch_json, atlas=None, fetch_sequence=fetch_text, fetch_record=fetch_record,
                 imgvr=None):
        self.fetch, self.atlas, self.fetch_sequence, self.fetch_record = fetch, atlas, fetch_sequence, fetch_record
        self.imgvr = imgvr

    def query(self, spec):
        if not isinstance(spec, dict): raise ValueError('source query must be an object')
        source = spec.get('source')
        if source == 'uniprot':
            query = validate_uniprot(spec.get('query'))
            limit = spec.get('limit', 4)
            if type(limit) is not int or not 1 <= limit <= 8: raise ValueError('limit must be 1..8')
            data, headers = self.fetch('https://rest.uniprot.org/uniprotkb/search?' + urlencode(
                {'query': query, 'format': 'json', 'size': limit,
                 'fields': 'accession,id,protein_name,organism_name,length,sequence,cc_function'}))
            return receipt(source, spec, data['results'][:limit], metadata={
                'release': headers.get('X-UniProt-Release') or headers.get('x-uniprot-release'),
                'coverage': 'bounded_first_page'})
        if source == 'ncbi':
            operation = spec.get('operation')
            if operation not in NCBI_DATABASES: raise ValueError('unknown NCBI operation')
            limit = spec.get('limit', 4)
            if type(limit) is not int or not 1 <= limit <= 8: raise ValueError('limit must be 1..8')
            if operation == 'taxonomy':
                term = _plain_term(spec.get('term'))
            elif operation == 'literature':
                term = _plain_term(spec.get('term'))
            else:
                taxon = _taxon_id(spec.get('taxon_id'))
                term = 'txid' + taxon + '[Organism:exp]'
                if operation in ('gene', 'protein'):
                    term += ' AND ' + _plain_term(spec.get('term'))
            database = NCBI_DATABASES[operation]
            search, _ = self.fetch(NCBI_BASE + 'esearch.fcgi?' + urlencode({
                'db': database, 'term': term, 'retmode': 'json', 'retmax': limit,
                'tool': 'vintos_lab'}))
            result = search.get('esearchresult') or {}
            ids = result.get('idlist') or []
            if not isinstance(ids, list) or any(not re.fullmatch(r'[0-9]{1,20}', str(x)) for x in ids):
                raise ValueError('NCBI returned invalid identifiers')
            ids = ids[:limit]
            records = []
            if ids:
                summary, _ = self.fetch(NCBI_BASE + 'esummary.fcgi?' + urlencode({
                    'db': database, 'id': ','.join(ids), 'retmode': 'json', 'tool': 'vintos_lab'}))
                payload = summary.get('result') or {}
                records = [{'uid': uid, 'summary': payload[uid]} for uid in ids if isinstance(payload.get(uid), dict)]
            return receipt(source, {'source': source, 'operation': operation, 'term': spec.get('term'),
                                    'taxon_id': spec.get('taxon_id'), 'limit': limit}, records,
                           metadata={'database': database, 'total_count': result.get('count'),
                                     'coverage': 'bounded_first_page', 'service': 'NCBI_EUtilities'})
        if source == 'ncbi_sequence':
            database = spec.get('database')
            if database not in ('protein', 'nuccore'): raise ValueError('protein or nuccore sequence required')
            accession = _ncbi_accession(spec.get('accession'))
            start, end = spec.get('start'), spec.get('end')
            max_span = 350 if database == 'protein' else 512
            if type(start) is not int or type(end) is not int or not 1 <= start <= end < 1000000000 or end-start+1 > max_span:
                raise ValueError('bounded one-based inclusive sequence interval required')
            fasta = self.fetch_sequence(NCBI_BASE + 'efetch.fcgi?' + urlencode({
                'db': database, 'id': accession, 'seq_start': start, 'seq_stop': end,
                'rettype': 'fasta', 'retmode': 'text', 'tool': 'vintos_lab'}))
            lines = fasta.splitlines()
            header = lines[0][1:].split()[0] if lines and lines[0].startswith('>') and lines[0][1:].split() else ''
            if header not in (accession, accession + ':' + str(start) + '-' + str(end)):
                raise ValueError('NCBI sequence accession did not match request')
            sequence = ''.join(lines[1:]).upper()
            alphabet = r'[ACDEFGHIKLMNPQRSTVWYBXZJUO*]+' if database == 'protein' else r'[ACGTNRYKMSWBDHV]+'
            if len(sequence) != end-start+1 or not re.fullmatch(alphabet, sequence):
                raise ValueError('NCBI returned invalid or oversized sequence')
            return receipt(source, {'source':source,'database':database,'accession':accession,
                                    'start':start,'end':end},
                           [{'accession':accession,'database':database,'start':start,'end':end,
                             'sequence':sequence}], metadata={'service':'NCBI_EFetch',
                             'coordinates':'one_based_inclusive','coverage':'requested_slice_only'})
        if source == 'ncbi_protein_context':
            accession = _ncbi_accession(spec.get('accession'))
            parsed = _gbseq(self.fetch_record(NCBI_BASE + 'efetch.fcgi?' + urlencode({
                'db':'protein','id':accession,'rettype':'gp','retmode':'xml','tool':'vintos_lab'})), accession)
            coded_by = []
            for feature in parsed['features']:
                coded_by.extend(feature['qualifiers'].get('coded_by', []))
            record = {key: parsed[key] for key in ('accession','definition','organism','taxonomy','length','features')}
            record['coded_by'] = coded_by[:8]
            return receipt(source, {'source':source,'accession':accession}, [record], metadata={
                'service':'NCBI_EFetch_GenPept','coverage':'one_exact_protein_record',
                'next_step':'use only a coded_by nucleotide accession and coordinates returned here'})
        if source == 'ncbi_neighborhood':
            accession = _ncbi_accession(spec.get('accession'))
            start, end, flank = spec.get('anchor_start'), spec.get('anchor_end'), spec.get('flank', 3000)
            if type(start) is not int or type(end) is not int or not 1 <= start <= end < 1000000000:
                raise ValueError('sourced one-based inclusive anchor coordinates required')
            if type(flank) is not int or not 500 <= flank <= 5000:
                raise ValueError('flank must be 500..5000 bases')
            window_start, window_end = max(1, start-flank), end+flank
            parsed = _gbseq(self.fetch_record(NCBI_BASE + 'efetch.fcgi?' + urlencode({
                'db':'nuccore','id':accession,'seq_start':window_start,'seq_stop':window_end,
                'rettype':'gb','retmode':'xml','tool':'vintos_lab'})), accession)
            expected_length = window_end-window_start+1
            if not parsed['sequence'] or len(parsed['sequence']) > expected_length:
                raise ValueError('NCBI returned invalid neighborhood sequence')
            from lab_genome_mining import scan_repeat_arrays
            screen = scan_repeat_arrays(parsed['sequence']) if len(parsed['sequence']) >= 200 else {
                'candidate_arrays': [], 'candidate_count': 0,
                'truth_status': 'window_too_short_for_pattern_screen'}
            record = {key: parsed[key] for key in ('accession','definition','organism','taxonomy','features')}
            record.update({'window_start':window_start,'window_end':window_start+len(parsed['sequence'])-1,
                           'anchor_start':start,'anchor_end':end,'sequence':parsed['sequence'],
                           'repeat_screen':screen})
            return receipt(source, {'source':source,'accession':accession,'anchor_start':start,
                                    'anchor_end':end,'flank':flank}, [record], metadata={
                'service':'NCBI_EFetch_GenBank','coordinates':'one_based_inclusive',
                'feature_locations':'provider_text; verify against the accession before comparison',
                'coverage':'bounded_anchor_neighborhood','evidence':'primary_sequence_and_provider_annotation'})
        if source == 'interpro':
            accession = _uniprot_accession(spec.get('accession'))
            data, _ = self.fetch(INTERPRO_BASE + 'entry/interpro/protein/uniprot/' + accession + '/?' + urlencode({'page_size':8}))
            rows = data.get('results') if isinstance(data, dict) else None
            if not isinstance(rows, list): raise ValueError('InterPro returned no result list')
            records = []
            for row in rows[:8]:
                if not isinstance(row, dict): continue
                meta = row.get('metadata') or {}
                records.append({'accession':meta.get('accession'),'name':meta.get('name'),
                                'type':meta.get('type'),'source_database':meta.get('source_database'),
                                'proteins': row.get('proteins')})
            return receipt(source, {'source':source,'accession':accession}, records, metadata={
                'service':'InterPro_REST','coverage':'bounded_first_eight_entries',
                'interpretation':'known_family_and_domain_annotations_not_novelty'})
        if source == 'imgvr':
            operation = spec.get('operation')
            if operation not in ('metadata','uvig','protein_similarity'):
                raise ValueError('unknown IMG/VR operation')
            if self.imgvr is None:
                from imgvr_store import query as local_imgvr
                local = local_imgvr(spec)
            else:
                local = self.imgvr(spec)
            records = local.get('records') if isinstance(local, dict) else None
            if not isinstance(records, list): raise ValueError('IMG/VR returned no record list')
            return receipt(source, spec, records[:8], metadata={
                'service':'local_IMG_VR_v4.1_high_confidence',
                'release':'IMG_VR_2022-12-19_7.1',
                'coverage':local.get('coverage','bounded_local_query'),
                'interpretation':'sequence_similarity_and_annotations_not_novelty_or_function'})
        if source == 'bvbrc':
            operation = spec.get('operation')
            if operation == 'genomes':
                key, value = 'taxon_id', _taxon_id(spec.get('taxon_id'))
                fields = ('genome_id', 'genome_name', 'taxon_id', 'assembly_accession',
                          'sequencing_status', 'genome_length', 'phenotype', 'other_environmental',
                          'optimal_temperature', 'reference_genome', 'public')
            elif operation == 'pathways':
                key, value = 'genome_id', _genome_id(spec.get('genome_id'))
                fields = ('genome_id', 'pathway_id', 'pathway_name', 'pathway_class',
                          'gene', 'product', 'feature_id', 'public')
            else:
                raise ValueError('unknown BV-BRC operation')
            endpoint = BV_BRC_BASE + ('genome/' if operation == 'genomes' else 'pathway/')
            data, _ = self.fetch(endpoint + '?eq(' + key + ',' + value + ')&limit(8)')
            if not isinstance(data, list): raise ValueError('BV-BRC returned no record list')
            taxon_match = 'exact' if operation == 'genomes' else None
            if operation == 'genomes' and not data:
                # Genus IDs have descendant species genomes, but no exact genome rows.
                data, _ = self.fetch(endpoint + '?eq(taxon_lineage_ids,' + value + ')&limit(8)')
                if not isinstance(data, list): raise ValueError('BV-BRC returned no record list')
                taxon_match = 'descendant_lineage'
            records = [{name: row[name] for name in fields if name in row}
                       for row in data[:8] if isinstance(row, dict) and row.get('public') is True]
            return receipt(source, spec, records, metadata={'service': 'BV-BRC_public_API',
                'coverage': 'bounded_first_eight_rows', 'taxon_match': taxon_match, 'interpretation':
                'database_annotations_and_sample_metadata_not_confirmed_phenotype'})
        if source == 'pdb':
            identifier = str(spec.get('entry_id', '')).upper()
            if not re.fullmatch(r'[0-9][A-Z0-9]{3}', identifier): raise ValueError('PDB entry ID required')
            data, _ = self.fetch('https://data.rcsb.org/rest/v1/core/entry/' + identifier)
            if not data.get('exptl'): raise ValueError('entry has no experimental method; not experimental evidence')
            return receipt(source, spec, [data], metadata={'evidence': 'experimental_structure',
                'comparison': 'sequence_construct_conditions_and_resolution_must_be_checked'})
        if source == 'chembl':
            target = str(spec.get('target_id', '')).upper()
            if not re.fullmatch(r'CHEMBL[0-9]+', target): raise ValueError('ChEMBL target ID required')
            data, _ = self.fetch('https://www.ebi.ac.uk/chembl/api/data/activity.json?' + urlencode(
                {'target_chembl_id': target, 'limit': 8, 'offset': 0}))
            # Preserve units, relations, assay IDs/types and validity comments verbatim.
            return receipt(source, spec, data['activities'][:8], metadata={
                'coverage': 'bounded_first_page', 'total_count': (data.get('page_meta') or {}).get('total_count'),
                'comparison': 'bioactivity_is_not_automatically_direct_binding'})
        if source == 'atlas':
            query = validate_atlas(spec)
            if self.atlas is None: raise RuntimeError('alphagenome_access_not_configured')
            data = self.atlas(query)
            return receipt(source, query, data['scores'], metadata={
                'assembly': 'GRCh38', 'coordinates': 'zero_based_half_open',
                'sdk_version': data['sdk_version'], 'scorer_metadata': data['scorer_metadata'],
                'atlas_release': data.get('atlas_release', 'not_reported_by_sdk'),
                'evidence': 'precomputed_model_prediction', 'usage': 'non_commercial'})
        if source == 'cosmic':
            raise RuntimeError('cosmic_requires_registered_licensed_dataset; no anonymous API configured')
        raise ValueError('unsupported Lab source')


def validate_atlas(spec):
    if spec.get('operation') == 'metadata': return {'source':'atlas', 'operation':'metadata'}
    if spec.get('assembly') != 'GRCh38': raise ValueError('Atlas requires explicit GRCh38 coordinates')
    chrom, start, end = spec.get('chromosome'), spec.get('start'), spec.get('end')
    if not isinstance(chrom, str) or not re.fullmatch(r'chr(?:[1-9]|1[0-9]|2[0-2]|X|Y)', chrom):
        raise ValueError('canonical human chromosome required')
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= 250000000 or end-start > 32:
        raise ValueError('Atlas interval must be zero-based, half-open, 1..32 bp')
    scorers = spec.get('scorers')
    if not isinstance(scorers, list) or not 1 <= len(scorers) <= 3 or not all(isinstance(s, str) and 0 < len(s) < 120 for s in scorers):
        raise ValueError('choose 1..3 scorer names returned by scorer_metadata')
    result = {k: spec[k] for k in ('source', 'assembly', 'chromosome', 'start', 'end', 'scorers')}
    for field, pattern in (('ontology_terms', r'[A-Z]+:[0-9]+'), ('gene_ids', r'ENSG[0-9]+(?:\.[0-9]+)?')):
        if field in spec:
            values = spec[field]
            if not isinstance(values, list) or not 1 <= len(values) <= 4 or not all(isinstance(v, str) and re.fullmatch(pattern, v) for v in values):
                raise ValueError('choose 1..4 sourced '+field)
            result[field] = values
    return result


class AtlasProcess:
    def __init__(self, key_file, python=sys.executable):
        self.key_file, self.python = str(Path(key_file).resolve()), python

    def __call__(self, query):
        path = Path(self.key_file)
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise RuntimeError('AlphaGenome key file must exist with mode 0600')
        # SDK timeout only bounds channel creation. The process deadline bounds the entire RPC.
        with tempfile.TemporaryDirectory(prefix='vintos-atlas-') as scratch:
            output = Path(scratch) / 'result.json'
            run = subprocess.run([self.python, str(Path(__file__).with_name('lab_atlas_worker.py')),
                                  self.key_file, str(output)], input=json.dumps(query), text=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90,
                                 env={**{k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','TMPDIR','SSL_CERT_FILE','SSL_CERT_DIR')}, 'PYTHONNOUSERSITE':'1'})
            if run.returncode: raise RuntimeError('Atlas query failed; check SDK/access/scorer configuration')
            if output.stat().st_size > MAX_BYTES: raise ValueError('Atlas response exceeds limit')
            return json.loads(output.read_text())


def collision_descriptor(result):
    return {'adapter_id': result['receipt_id'][:24], 'at': result['retrieved_at'],
            'source': result['source'], 'source_accession': result['receipt_id'],
            'source_metadata_sha256': result['response_sha256'],
            'transform': 'source_metadata_to_text_v1_then_house_nomic',
            'text': json.dumps({'source': result['source'], 'query': result['query'],
                                'observations': result['records']}, sort_keys=True)[:6000],
            'truth_status': 'source_descriptor_not_biological_inference',
            'evidence_standing': 'eligible_as_text_collision_source_only'}


def followups(result):
    source = result['source']
    followup = {'source_receipt': result['receipt_id'], 'hypothesis_status': 'unvalidated',
              'esmc_esmfold': 'requires_sourced_gene_to_protein_mapping_and_sequence; regulatory_effect_is_not_sequence_change',
              'chemiq': 'requires_defined_molecule_and_supported_experiment',
              'novelty': 'requires_documented_literature_search; no_hit_is_not_proof'}
    if source == 'atlas':
        followup['evo2'] = 'requires_reference_sequence_and_allele_checked_against_GRCh38'
    else:
        followup['evo2'] = 'requires_exact_sourced_reference_sequence_and_bounded_comparison; no phenotype_claim'
    return followup

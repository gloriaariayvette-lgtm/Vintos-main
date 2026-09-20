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
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request
from lab_http import open_request

MAX_BYTES = 2 * 1024 * 1024
FIELDS = frozenset('accession id reviewed length protein_name gene organism_id organism_name taxonomy_id keyword go xref_pdb'.split())


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
    def __init__(self, fetch=fetch_json, atlas=None):
        self.fetch, self.atlas = fetch, atlas

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
    return {'source_receipt': result['receipt_id'], 'hypothesis_status': 'unvalidated',
            'evo2': 'requires_reference_sequence_and_allele_checked_against_GRCh38',
            'esmc_esmfold': 'requires_sourced_gene_to_protein_mapping_and_sequence; regulatory_effect_is_not_sequence_change',
            'chemiq': 'requires_defined_molecule_and_supported_experiment',
            'novelty': 'requires_documented_literature_search; no_hit_is_not_proof'}

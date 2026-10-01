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
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request
from lab_http import open_request

MAX_BYTES = 2 * 1024 * 1024
FIELDS = frozenset('accession id reviewed length protein_name gene organism_id organism_name taxonomy_id keyword go xref_pdb'.split())
NCBI_BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
BV_BRC_BASE = 'https://www.bv-brc.org/api/'
INTERPRO_BASE = 'https://www.ebi.ac.uk/interpro/api/'
PUBCHEM_BASE = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug/'
REACTOME_BASE = 'https://reactome.org/ContentService/'
RHEA_BASE = 'https://www.rhea-db.org/rhea'
QUICKGO_BASE = 'https://www.ebi.ac.uk/QuickGO/services/'
MGNIFY_BASE = 'https://www.ebi.ac.uk/metagenomics/api/v1/'
NCBI_DATABASES = {'taxonomy': 'taxonomy', 'assembly': 'assembly',
                  'gene': 'gene', 'protein': 'protein', 'literature': 'pubmed'}


def _plain_term(value):
    """A plain search phrase. He writes "polyketide synthase (PKS) in marine actinobacteria"; the brackets,
    colons and Entrez words are taken out rather than the whole question refused (2026-09-28), so no field
    tag or operator of his can reach Entrez, and what he asked about still does."""
    if not isinstance(value, str):
        raise ValueError('use 3..120 plain search characters, without Entrez operators')
    value = re.sub(r"[^A-Za-z0-9 .,'_-]", ' ', value)
    value = re.sub(r"\b(?:AND|OR|NOT)\b", ' ', value)
    value = re.sub(r"\s+", ' ', value).strip(" .,'_-")[:120].strip()
    if len(value) < 3 or not value[0].isalnum():
        raise ValueError('use 3..120 plain search characters, without Entrez operators')
    return value


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


def _bounded_limit(value, maximum=8):
    value = 4 if value is None else value
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError('limit must be 1..%d' % maximum)
    return value


def _provider(fetch, source, url):
    """Name the public provider and its HTTP status without copying response bodies."""
    try:
        return fetch(url)
    except HTTPError as exc:
        raise RuntimeError('%s_http_status_%d' % (source, exc.code)) from exc


def _strip_html(value, cap):
    return re.sub(r'<[^>]+>', '', str(value or ''))[:cap]


def validate_uniprot(query):
    """Validate a UniProt query and return it normalized. Callers must use the returned query."""
    if not isinstance(query, str) or not query.strip() or len(query) > 600:
        raise ValueError('bounded UniProt query required')
    if any(ord(c) < 32 for c in query) or query.count('(') != query.count(')') or query.count('[') != query.count(']') or query.count('"') % 2:
        raise ValueError('malformed UniProt query')
    # "organism_id : 1224" is not a field to UniProt; it is three free-text words, and matches nothing.
    query = re.sub(r'\b([A-Za-z_][A-Za-z_0-9]*)\s*:\s*', r'\1:', query)
    fields = re.findall(r'\b([A-Za-z_][A-Za-z_0-9]*):', query)
    unknown = set(fields) - FIELDS
    if unknown: raise ValueError('unsupported UniProt fields: ' + ', '.join(sorted(unknown)))
    # organism_id matches only the one exact taxon, so a group ID (1224 = Proteobacteria) returns zero
    # records. taxonomy_id matches that taxon and everything under it, so it is never narrower.
    query = re.sub(r'\borganism_id:', 'taxonomy_id:', query)
    query = re.sub(r'\breviewed:(true|false)\b', lambda m: 'reviewed:' + m.group(1).lower(), query, flags=re.I)
    # UniProt takes length only as a range: a bare "length:500" is refused with a 400, and every looser
    # form kept it, so the search failed seven times in a row (2026-09-30, SLC25A1).
    query = re.sub(r'\blength:(\d+)\b', r'length:[\1 TO \1]', query, flags=re.I)
    if re.search(r'\b(?:protein_name|gene|keyword):', query, re.I):
        # He named the protein; a guessed length only hides it. Drop the term wherever it sits,
        # inside parentheses too, with the AND that joined it.
        term = r'length:\[[^\]]+\]'
        query = re.sub(r'\s+AND\s+' + term + r'(?=\s|\)|$)', '', query, flags=re.I)
        query = re.sub(r'(?:^|(?<=\())\s*' + term + r'\s+AND\s+', '', query, flags=re.I)
        query = re.sub(r'\s+', ' ', query).strip()
    return query



_TERM = re.compile(r'\b([A-Za-z_][A-Za-z_0-9]*):("[^"]*"|\[[^\]]*\]|[^\s()]+)')
_KEEP = ('reviewed', 'length', 'taxonomy_id', 'organism_id', 'organism_name')
_SUBJECT_FIELDS = ('protein_name', 'gene', 'keyword')
_FILLER = frozenset('the of in and or not for with from to a an its their this that specific structural protein proteins'
                    ' putative family'.split())


def uniprot_relaxations(query):
    """Looser forms of one UniProt query, most faithful first. He asks for "thermophilic proteases" of
    Saccharolobus solfataricus and no protein is named exactly that, so the exact query finds nothing
    and he asks again (Gloria, 2026-09-28: "just give him the ability to get the info he needs").
    Every form keeps his organism, length and review filters and the words he asked about; only the
    field they must sit in is loosened. The caller records which form answered."""
    query = str(query or '')
    out = []
    symbol = re.search(r'\bprotein_name:(?:"([A-Za-z][A-Za-z0-9-]{1,11})"|([A-Za-z][A-Za-z0-9-]{1,11})(?=\s|\)|$))', query)
    if symbol:   # KaiC, slpA, RPS16: a gene symbol written as a protein name
        out.append(('as_gene', query[:symbol.start()] + 'gene:' + (symbol.group(1) or symbol.group(2)) + query[symbol.end():]))
    keep, field_words, free_words = [], [], []
    for field, value in _TERM.findall(query):
        if field in _KEEP:
            term = field + ':' + value
            if term not in keep: keep.append(term)
        elif field in _SUBJECT_FIELDS:
            field_words += re.findall(r'[A-Za-z0-9][A-Za-z0-9-]*', value.strip('"'))
    # Free text can be a subject only when he did not name one in a typed field. Otherwise
    # boolean/filter residue such as an organism word must not broaden the protein search.
    if not field_words:
        free_words = re.findall(r'[A-Za-z0-9][A-Za-z0-9-]*', _TERM.sub(' ', query))
    words = field_words or free_words
    seen, subject = set(), []
    for word in words:
        low = word.lower()
        if low in _FILLER or low in ('and', 'or', 'not', 'true', 'false') or len(word) < 3 or low in seen: continue
        seen.add(low); subject.append(word)
    subject = subject[:5]
    if not subject: return out
    def group(word):
        if '-' in word: return '"%s"' % word   # S-layer is one word to him, "S NOT layer" to a bare parser
        low = word.lower()
        single = (word[:-1] if low.endswith('ses') else
                  word[:-1] if low.endswith('s') and len(word) > 4 and not low.endswith(('ss', 'is', 'us')) else None)
        return '(%s OR %s)' % (word, single) if single else word
    words_all = ' AND '.join(group(w) for w in subject)
    words_any = ' OR '.join(group(w) for w in subject)
    def join(filters, text):
        return ' AND '.join(filters + ['(' + text + ')'])
    out.append(('all_words_reviewed', join(keep, words_all)))
    unreviewed = [k for k in keep if not k.startswith('reviewed:')]
    out.append(('all_words_unreviewed_included', join(unreviewed, words_all)))
    if len(subject) > 1:
        out.append(('partial_any_word', join(unreviewed, words_any)))
    faithful, seen_q = [], {query}
    for label, alt in out:
        if alt not in seen_q: seen_q.add(alt); faithful.append((label, alt))
    return faithful

_PUBMED_FILLER = frozenset('the of in and or not for with from to a an by on at as its their this that vs versus '
                           'specific specifically role roles protein proteins'.split())

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

    def _taxon(self, spec):
        """A taxon ID he was given, or the one NCBI Taxonomy returns for the organism he named. Guessed IDs
        were refused and the question lost; a name is looked up instead of guessed (2026-09-28)."""
        if spec.get('taxon_id') not in (None, ''):
            return _taxon_id(spec.get('taxon_id'))
        if not spec.get('organism'): return None
        found, _ = self.fetch(NCBI_BASE + 'esearch.fcgi?' + urlencode({
            'db': 'taxonomy', 'term': _plain_term(spec.get('organism')), 'retmode': 'json', 'retmax': 1,
            'tool': 'vintos_lab'}))
        ids = (found.get('esearchresult') or {}).get('idlist') or []
        return str(ids[0]) if ids and re.fullmatch(r'[1-9][0-9]{0,9}', str(ids[0])) else None

    def _gene_window(self, symbol):
        """Where a human gene starts on GRCh38, from NCBI Gene: a 32-base window over its first base, which
        is what Atlas can read. He knows genes, not coordinates (2026-09-28)."""
        symbol = str(symbol or '').strip()
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{0,14}', symbol): raise ValueError('a human gene symbol is required')
        found, _ = self.fetch(NCBI_BASE + 'esearch.fcgi?' + urlencode({
            'db': 'gene', 'term': '%s[sym] AND 9606[taxid]' % symbol, 'retmode': 'json', 'retmax': 1, 'tool': 'vintos_lab'}))
        ids = (found.get('esearchresult') or {}).get('idlist') or []
        if not ids or not re.fullmatch(r'[0-9]{1,12}', str(ids[0])): raise ValueError('no human gene named ' + symbol)
        summary, _ = self.fetch(NCBI_BASE + 'esummary.fcgi?' + urlencode({
            'db': 'gene', 'id': ids[0], 'retmode': 'json', 'tool': 'vintos_lab'}))
        info = (((summary.get('result') or {}).get(str(ids[0])) or {}).get('genomicinfo') or [{}])[0]
        chrom = str(info.get('chrloc') or '')
        start, stop = info.get('chrstart'), info.get('chrstop')
        if not re.fullmatch(r'(?:[1-9]|1[0-9]|2[0-2]|X|Y)', chrom) or not isinstance(start, int) or not isinstance(stop, int):
            raise ValueError('NCBI gave no GRCh38 position for ' + symbol)
        first = start          # chrstart is the gene's first base in its own direction (0-based): its start site
        begin = max(0, first - 16)
        return {'assembly': 'GRCh38', 'chromosome': 'chr' + chrom, 'start': begin, 'end': begin + 32,
                'gene_window': {'gene': symbol, 'ncbi_gene_id': str(ids[0]), 'gene_first_base': first,
                                'strand': '-' if start > stop else '+', 'window': 'start_site_32bp'}}

    def _abstracts(self, spec):
        """Published abstracts for what he is asking: the reading itself, not a list of titles. All his
        terms first; if nothing matches, the last term is dropped, down to two."""
        raw = spec.get('terms')
        terms = []
        for value in (raw if isinstance(raw, list) else [])[:6]:
            try: terms.append(_plain_term(str(value)))
            except ValueError: continue
        if not terms: raise ValueError('one or more plain search terms required')
        limit = spec.get('limit', 4)
        if type(limit) is not int or not 1 <= limit <= 6: raise ValueError('limit must be 1..6')
        pause = (lambda: time.sleep(0.4)) if self.fetch is fetch_json else (lambda: None)   # NCBI: 3 a second
        if len(terms) > 1:
            # A word no paper contains ("psychre", his Colwellia psychrerythraea cut short) empties every
            # search it is in; it is dropped first (2026-09-28). If every word is like that, all are kept.
            counted = []
            for term in terms:
                pause()
                found, _ = self.fetch(NCBI_BASE + 'esearch.fcgi?' + urlencode({
                    'db': 'pubmed', 'term': '(%s)' % term, 'retmode': 'json', 'retmax': 0, 'tool': 'vintos_lab'}))
                if str((found.get('esearchresult') or {}).get('count', '0')) != '0': counted.append(term)
            terms = counted or terms
        ids, used = [], terms
        for n in range(len(terms), min(2, len(terms)) - 1, -1):
            used = terms[:n]
            pause()
            search, _ = self.fetch(NCBI_BASE + 'esearch.fcgi?' + urlencode({
                'db': 'pubmed', 'term': ' AND '.join('(%s)' % t for t in used), 'retmode': 'json',
                'retmax': limit, 'sort': 'relevance', 'tool': 'vintos_lab'}))
            ids = (search.get('esearchresult') or {}).get('idlist') or []
            if any(not re.fullmatch(r'[0-9]{1,20}', str(x)) for x in ids):
                raise ValueError('NCBI returned invalid identifiers')
            if ids: break
        records = []
        if ids:
            xml = self.fetch_record(NCBI_BASE + 'efetch.fcgi?' + urlencode({
                'db': 'pubmed', 'id': ','.join(map(str, ids[:limit])), 'rettype': 'abstract', 'retmode': 'xml',
                'tool': 'vintos_lab'}))
            try: root = ET.fromstring(xml)
            except ET.ParseError as exc: raise ValueError('PubMed returned malformed XML') from exc
            for article in root.findall('.//PubmedArticle')[:limit]:
                abstract = ' '.join(''.join(node.itertext()).strip() for node in article.findall('.//Abstract/AbstractText'))
                records.append({'pmid': article.findtext('.//PMID') or '',
                                'title': ''.join((article.find('.//ArticleTitle') or ET.Element('x')).itertext())[:300],
                                'journal': (article.findtext('.//Journal/Title') or '')[:160],
                                'year': article.findtext('.//JournalIssue/PubDate/Year') or '',
                                'abstract': abstract[:1800]})
        return receipt('pubmed_abstracts', {'source': 'pubmed_abstracts', 'terms': terms, 'terms_matched': used,
                                            'limit': limit}, records,
                       metadata={'service': 'NCBI_PubMed', 'coverage': 'first_%d_by_relevance' % limit,
                                 'interpretation': "published abstracts: the authors' claims, not verified here"})

    def query(self, spec):
        if not isinstance(spec, dict): raise ValueError('source query must be an object')
        source = spec.get('source')
        if source == 'uniprot':
            query = validate_uniprot(spec.get('query'))
            limit = spec.get('limit', 4)
            if type(limit) is not int or not 1 <= limit <= 8: raise ValueError('limit must be 1..8')
            def search(value):
                return self.fetch('https://rest.uniprot.org/uniprotkb/search?' + urlencode(
                    {'query': value, 'format': 'json', 'size': limit,
                     'fields': 'accession,id,protein_name,organism_name,length,sequence,cc_function'}))
            relaxed, rejected = None, None
            try:
                data, headers = search(query)
            except HTTPError as exc:
                if exc.code != 400: raise
                rejected, data, headers = exc, {'results': []}, {}
            if not data.get('results'):
                for label, alt in uniprot_relaxations(query):
                    try: found, found_headers = search(alt)
                    except HTTPError as exc:
                        if exc.code == 400: continue
                        raise
                    if found.get('results'):
                        data, headers, relaxed, query = found, found_headers, label, alt
                        break
            if rejected is not None and not relaxed: raise rejected
            records = data['results'][:limit]
            if relaxed:
                records = [dict(row, found_by=relaxed,
                                partial_match=relaxed == 'partial_any_word',
                                curated=str(row.get('entryType', '')).startswith('UniProtKB reviewed'))
                           for row in records]
            return receipt(source, dict(spec, executed_query=query) if relaxed else spec, records, metadata={
                'release': headers.get('X-UniProt-Release') or headers.get('x-uniprot-release'),
                'coverage': 'bounded_first_page',
                **({'relaxed': relaxed, 'executed_query': query,
                    'partial_match': relaxed == 'partial_any_word'} if relaxed else {})})
        if source == 'ncbi':
            operation = spec.get('operation')
            if operation not in NCBI_DATABASES: raise ValueError('unknown NCBI operation')
            limit = spec.get('limit', 4)
            if type(limit) is not int or not 1 <= limit <= 8: raise ValueError('limit must be 1..8')
            resolved = None
            if operation == 'taxonomy':
                term = _plain_term(spec.get('term') or spec.get('organism'))
            elif operation == 'literature':
                term = _plain_term(spec.get('term'))
            else:
                taxon = self._taxon(spec)
                resolved = taxon if spec.get('taxon_id') in (None, '') else None
                if taxon:
                    term = 'txid' + taxon + '[Organism:exp]'
                    if operation in ('gene', 'protein'):
                        term += ' AND ' + _plain_term(spec.get('term'))
                elif operation in ('gene', 'protein') and spec.get('term'):
                    term = _plain_term(spec.get('term'))   # no organism named: the gene or protein alone
                else:
                    raise ValueError('sourced numeric NCBI taxon_id or an organism name required')
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
                                    'taxon_id': spec.get('taxon_id'), 'limit': limit,
                                    **({'organism': spec.get('organism'), 'resolved_taxon_id': resolved}
                                       if resolved else {})}, records,
                           metadata={'database': database, 'total_count': result.get('count'),
                                     'coverage': 'bounded_first_page', 'service': 'NCBI_EUtilities'})
        if source == 'pubmed_abstracts':
            return self._abstracts(spec)
        if source == 'pubmed':
            # He asks for PubMed the way the connector names it ({source: pubmed, operation: search_articles,
            # term: ...}); every such request was refused as an unknown source (2026-09-28). It is the same
            # search: his phrase, word by word.
            raw = spec.get('terms') if isinstance(spec.get('terms'), list) else re.findall(
                r"[A-Za-z0-9][A-Za-z0-9'-]*", str(spec.get('term') or spec.get('query') or ''))
            words = [w for w in raw if str(w).lower() not in _PUBMED_FILLER][:6]
            return self._abstracts({'terms': words, 'limit': 4})
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
                key, value = 'taxon_id', self._taxon(spec)
                if not value: raise ValueError('sourced numeric NCBI taxon_id or an organism name required')
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
        if source == 'pubchem':
            limit = _bounded_limit(spec.get('limit'), 4)
            name, cid = spec.get('name'), spec.get('cid')
            if name not in (None, '') and cid not in (None, ''):
                raise ValueError('choose one PubChem name or CID')
            if name not in (None, ''):
                identifier = _plain_term(name)
                from urllib.parse import quote
                path = 'compound/name/' + quote(identifier, safe='')
                query = {'source':source, 'name':identifier, 'limit':limit}
            elif type(cid) is int and 1 <= cid <= 9999999999:
                path = 'compound/cid/' + str(cid)
                query = {'source':source, 'cid':cid, 'limit':limit}
            else:
                raise ValueError('plain PubChem name or positive numeric CID required')
            fields = 'Title,MolecularFormula,CanonicalSMILES,IsomericSMILES,InChIKey,MolecularWeight'
            data, _ = _provider(self.fetch, source, PUBCHEM_BASE + path + '/property/' + fields + '/JSON')
            rows = ((data.get('PropertyTable') or {}).get('Properties') if isinstance(data, dict) else None)
            if not isinstance(rows, list): raise ValueError('PubChem returned no property list')
            keep = ('CID','Title','MolecularFormula','ConnectivitySMILES','SMILES','CanonicalSMILES',
                    'IsomericSMILES','InChIKey','MolecularWeight')
            records = [{k: row[k] for k in keep if k in row} for row in rows[:limit] if isinstance(row, dict)]
            return receipt(source, query, records, metadata={'service':'PubChem_PUG_REST',
                'coverage':'bounded_property_records', 'interpretation':'database_identity_and_computed_properties_not_experimental_validation'})
        if source == 'reactome':
            term = _plain_term(spec.get('term') or spec.get('query'))
            limit = _bounded_limit(spec.get('limit'), 5)
            species = str(spec.get('species') or '').strip()
            if species and (len(species) > 80 or not re.fullmatch(r'[A-Za-z][A-Za-z ._-]+', species)):
                raise ValueError('plain Reactome species name required')
            params = {'query':term, 'types':'Pathway', 'cluster':'true'}
            if species: params['species'] = species
            data, _ = _provider(self.fetch, source, REACTOME_BASE + 'search/query?' + urlencode(params))
            groups = data.get('results') if isinstance(data, dict) else None
            if not isinstance(groups, list): raise ValueError('Reactome returned no result groups')
            records = []
            for group in groups:
                for row in (group.get('entries') or []) if isinstance(group, dict) else []:
                    if not isinstance(row, dict) or row.get('type') != 'Pathway': continue
                    records.append({'stable_id':row.get('stId') or row.get('id'), 'name':_strip_html(row.get('name'),240),
                        'species':(row.get('species') or [])[:4], 'summary':_strip_html(row.get('summation'),900),
                        'compartments':(row.get('compartmentNames') or [])[:8]})
                    if len(records) >= limit: break
                if len(records) >= limit: break
            return receipt(source, {'source':source,'term':term,'species':species or None,'limit':limit}, records,
                metadata={'service':'Reactome_ContentService','total_matches':data.get('numberOfMatches'),
                          'coverage':'bounded_pathway_search','interpretation':'curated_pathway_annotation_not_activity_in_this_sample'})
        if source == 'rhea':
            term = _plain_term(spec.get('term') or spec.get('query'))
            limit = _bounded_limit(spec.get('limit'), 8)
            data, _ = _provider(self.fetch, source, RHEA_BASE + '?' + urlencode({
                'query':term, 'columns':'rhea-id,equation,ec', 'format':'json', 'limit':limit}))
            rows = data.get('results') if isinstance(data, dict) else None
            if not isinstance(rows, list): raise ValueError('Rhea returned no result list')
            keep = ('id','equation','status','balanced','transport','ec')
            records = [{k: row[k] for k in keep if k in row} for row in rows[:limit] if isinstance(row, dict)]
            return receipt(source, {'source':source,'term':term,'limit':limit}, records,
                metadata={'service':'Rhea_REST','total_count':data.get('count'),'coverage':'bounded_reaction_search',
                          'interpretation':'expert_curated_reaction_definition_not_evidence_of_activity'})
        if source == 'quickgo':
            term = _plain_term(spec.get('term') or spec.get('query'))
            limit = _bounded_limit(spec.get('limit'), 8)
            data, _ = _provider(self.fetch, source, QUICKGO_BASE + 'ontology/go/search?' + urlencode({
                'query':term, 'limit':limit, 'page':1}))
            rows = data.get('results') if isinstance(data, dict) else None
            if not isinstance(rows, list): raise ValueError('QuickGO returned no result list')
            records = []
            for row in rows[:limit]:
                if not isinstance(row, dict): continue
                definition = row.get('definition') or {}
                records.append({'go_id':row.get('id'),'name':row.get('name'),'aspect':row.get('aspect'),
                                'obsolete':bool(row.get('isObsolete')),
                                'definition':str(definition.get('text') or '')[:600] if isinstance(definition, dict) else ''})
            return receipt(source, {'source':source,'term':term,'limit':limit}, records,
                metadata={'service':'QuickGO_REST','total_count':data.get('numberOfHits'),'coverage':'bounded_GO_term_search',
                          'interpretation':'ontology_definition_not_protein_specific_evidence'})
        if source == 'mgnify':
            operation = spec.get('operation', 'studies')
            if operation != 'studies': raise ValueError('unknown MGnify operation')
            term = _plain_term(spec.get('term') or spec.get('query'))
            limit = _bounded_limit(spec.get('limit'), 8)
            data, _ = _provider(self.fetch, source, MGNIFY_BASE + 'studies?' + urlencode({
                'search':term, 'page_size':limit}))
            rows = data.get('data') if isinstance(data, dict) else None
            if not isinstance(rows, list): raise ValueError('MGnify returned no study list')
            records = []
            for row in rows[:limit]:
                if not isinstance(row, dict): continue
                attrs = row.get('attributes') or {}; relationships = row.get('relationships') or {}
                biomes = (((relationships.get('biomes') or {}).get('data')) or []) if isinstance(relationships, dict) else []
                records.append({'accession':attrs.get('accession') or row.get('id'), 'study_name':attrs.get('study-name'),
                    'abstract':str(attrs.get('study-abstract') or '')[:900], 'samples_count':attrs.get('samples-count'),
                    'bioproject':attrs.get('bioproject'), 'public_release_date':attrs.get('public-release-date'),
                    'biomes':[b.get('id') for b in biomes[:6] if isinstance(b, dict)]})
            pagination = data.get('meta', {}).get('pagination', {}) if isinstance(data.get('meta'), dict) else {}
            return receipt(source, {'source':source,'operation':operation,'term':term,'limit':limit}, records,
                metadata={'service':'MGnify_REST','total_count':pagination.get('count'),'coverage':'bounded_study_search',
                          'interpretation':'study_metadata_not_a_taxonomic_or_functional_result'})
        if source == 'atlas':
            if spec.get('gene') and not spec.get('chromosome') and spec.get('operation') != 'metadata':
                spec = {**spec, **self._gene_window(spec['gene'])}
            query = validate_atlas(spec)
            if self.atlas is None: raise RuntimeError('alphagenome_access_not_configured')
            data = self.atlas(query)
            return receipt(source, query, data['scores'], metadata={
                'assembly': 'GRCh38', 'coordinates': 'zero_based_half_open',
                'available_scorers': data.get('available_scorers', []),
                'scorers_chosen_by_lab': bool(data.get('scorers_chosen_by_lab')),
                'sdk_version': data['sdk_version'], 'scorer_metadata': data['scorer_metadata'],
                'atlas_release': data.get('atlas_release', 'not_reported_by_sdk'),
                'evidence': 'precomputed_model_prediction', 'usage': 'non_commercial'})
        if source == 'cosmic':
            raise RuntimeError('cosmic_requires_registered_licensed_dataset; no anonymous API configured')
        raise ValueError('unsupported Lab source')


def validate_atlas(spec):
    if spec.get('operation') == 'metadata': return {'source':'atlas', 'operation':'metadata'}
    if spec.get('assembly') in (None, '', 'hg38'): spec = dict(spec, assembly='GRCh38')
    if spec.get('assembly') != 'GRCh38': raise ValueError('Atlas requires explicit GRCh38 coordinates')
    chrom, start, end = spec.get('chromosome'), spec.get('start'), spec.get('end')
    if not isinstance(chrom, str) or not re.fullmatch(r'chr(?:[1-9]|1[0-9]|2[0-2]|X|Y)', chrom):
        raise ValueError('canonical human chromosome required')
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= 250000000 or end-start > 32:
        raise ValueError('Atlas interval must be zero-based, half-open, 1..32 bp')
    # Scorer names are optional: without real ones the worker chooses from Atlas's own list and says so.
    # Every one of his 891 Atlas asks failed on coordinates or names he could not have (2026-09-28).
    scorers = spec.get('scorers') or []
    if not isinstance(scorers, list) or len(scorers) > 3 or not all(isinstance(s, str) and 0 < len(s) < 120 for s in scorers):
        raise ValueError('choose up to 3 scorer names returned by scorer_metadata')
    result = {k: spec[k] for k in ('source', 'assembly', 'chromosome', 'start', 'end')}
    result['scorers'] = scorers
    if spec.get('gene_window'): result['gene_window'] = spec['gene_window']
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
            try:
                run = subprocess.run([self.python, str(Path(__file__).with_name('lab_atlas_worker.py')),
                                      self.key_file, str(output)], input=json.dumps(query), text=True,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90,
                                     env={**{k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','TMPDIR','SSL_CERT_FILE','SSL_CERT_DIR')}, 'PYTHONNOUSERSITE':'1'})
            except subprocess.TimeoutExpired:
                raise RuntimeError('Atlas query timed out after 90s') from None
            if run.returncode:
                why = Path(scratch) / 'error.txt'
                raise RuntimeError('Atlas query failed: ' + (why.read_text()[:300] if why.is_file()
                                   else 'worker exited %d before saying why' % run.returncode))
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

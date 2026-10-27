"""Public sequencing runs for the Lab: run metadata from ENA and NCBI SRA, and a bounded read sample.

Two sources, both read-only and free (Gloria, 2026-10-27: the NGS Workbench had never had a real dataset):

  sequencing_runs   run metadata only: run/experiment/study/sample accessions, platform, layout, strategy, read
                    and base counts, and each FASTQ file's URL, size and provider MD5. By exact accession (ENA
                    filereport), or by organism and filters (ENA portal search); a free-text term goes through NCBI
                    SRA E-utilities first, and the runs it names are then read from ENA.
  sequencing_reads  the FIRST reads of one FASTQ file of one run, streamed and stopped early: never more than
                    MAX_SAMPLE_READS reads, MAX_COMPRESSED_BYTES downloaded or MAX_SAMPLE_TEXT_BYTES of FASTQ, and
                    never a whole dataset. The sample is kept as a gzip FASTQ Lab artifact with its SHA-256 and a
                    provenance file beside it, small enough (MAX_ARTIFACT_BYTES) to be one of the four digest-verified
                    input files the sequence viewer and NGS workbench take (8 MiB in all).

The first reads of a file are not a random sample of the run: the receipt says so. URLs are built here from
validated accessions, and a file URL is only ever one ENA returned for that run, on ENA's own file host.
"""
from __future__ import annotations
import gzip
import hashlib
import io
import json
import os
import re
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

ENA_PORTAL = 'https://www.ebi.ac.uk/ena/portal/api/'
ENA_FILE_HOST = 'ftp.sra.ebi.ac.uk'
NCBI_BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'

RUN_FIELDS = ('run_accession', 'experiment_accession', 'study_accession', 'secondary_study_accession',
              'sample_accession', 'scientific_name', 'tax_id', 'instrument_platform', 'instrument_model',
              'library_layout', 'library_strategy', 'library_source', 'read_count', 'base_count',
              'fastq_ftp', 'fastq_bytes', 'fastq_md5', 'first_public')

RUN_ACCESSION = r'[SED]RR[0-9]{6,10}'
# run, experiment, sample, study and project accessions of the three INSDC archives
ACCESSION = (r'(?:[SED]R[RXSP][0-9]{6,10}|PRJ(?:NA|EB|DB)[0-9]{1,10}|SAM(?:N|EA|D)[0-9]{1,12}'
             r'|[SED]RA[0-9]{6,10})')
PLATFORMS = frozenset(('ILLUMINA', 'OXFORD_NANOPORE', 'PACBIO_SMRT', 'ION_TORRENT', 'BGISEQ', 'DNBSEQ',
                       'LS454', 'ELEMENT', 'ULTIMA', 'CAPILLARY'))
LAYOUTS = frozenset(('PAIRED', 'SINGLE'))
STRATEGIES = frozenset(('WGS', 'WXS', 'WGA', 'RNA-Seq', 'miRNA-Seq', 'AMPLICON', 'ChIP-Seq', 'ATAC-seq',
                        'Bisulfite-Seq', 'Hi-C', 'Targeted-Capture', 'OTHER'))
_STRATEGY = {s.lower(): s for s in STRATEGIES}

MAX_RUNS = 8
DEFAULT_SAMPLE_READS = 10000
MAX_SAMPLE_READS = 50000
MAX_COMPRESSED_BYTES = 20 * 1024 * 1024      # downloaded from the provider, at most, for one sample
MAX_SAMPLE_TEXT_BYTES = 16 * 1024 * 1024     # FASTQ text kept before compression
MAX_ARTIFACT_BYTES = 6 * 1024 * 1024         # the stored .fastq.gz: leaves room under the relay's 8 MiB input limit
MAX_SAMPLES_PER_DAY = 8                      # new samples written in any 24 hours; a sample already held is reused
CHUNK = 64 * 1024


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _limit(value):
    value = 4 if value is None else value
    if type(value) is not int or not 1 <= value <= MAX_RUNS:
        raise ValueError('limit must be 1..%d' % MAX_RUNS)
    return value


def accession(value):
    value = str(value or '').strip().upper()
    if not re.fullmatch(ACCESSION, value):
        raise ValueError('exact SRA/ENA/DDBJ run, experiment, sample, study or project accession required '
                         '(e.g. SRR1234567, ERX123456, SAMN01234567, PRJNA123456)')
    return value


def run_accession(value):
    value = str(value or '').strip().upper()
    if not re.fullmatch(RUN_ACCESSION, value):
        raise ValueError('exact sourced run accession required (SRR, ERR or DRR, from a sequencing_runs receipt)')
    return value


def file_url(raw):
    """The https URL of one file ENA listed, or ValueError. Only ENA's own file host, only a FASTQ path."""
    raw = str(raw or '').strip()
    path = re.sub(r'^(?:ftp|https?)://', '', raw)
    if not re.fullmatch(re.escape(ENA_FILE_HOST) + r'/vol1/fastq/[A-Za-z0-9_./-]+\.f(?:ast)?q\.gz', path) or '..' in path:
        raise ValueError('ENA returned a file location outside its FASTQ archive')
    return 'https://' + path


def _files(row):
    urls = [u for u in str(row.get('fastq_ftp') or '').split(';') if u]
    sizes = str(row.get('fastq_bytes') or '').split(';')
    md5s = str(row.get('fastq_md5') or '').split(';')
    out = []
    for n, url in enumerate(urls[:3]):
        try:
            https = file_url(url)
        except ValueError:
            continue
        name = https.rsplit('/', 1)[-1]
        mate = 1 if re.search(r'_1\.f(?:ast)?q\.gz$', name) else 2 if re.search(r'_2\.f(?:ast)?q\.gz$', name) else None
        out.append({'url': https, 'name': name, 'mate': mate,
                    'bytes': _int(sizes[n]) if n < len(sizes) else None,
                    'md5': md5s[n] if n < len(md5s) and re.fullmatch(r'[0-9a-f]{32}', md5s[n]) else None})
    return out


def _run_record(row):
    rec = {k: row.get(k) for k in RUN_FIELDS if k not in ('fastq_ftp', 'fastq_bytes', 'fastq_md5')}
    for k in ('tax_id', 'read_count', 'base_count'):
        rec[k] = _int(rec.get(k))
    rec['files'] = _files(row)
    return rec


def _rows(data):
    if data in (None, ''):
        return []
    if not isinstance(data, list) or any(not isinstance(r, dict) for r in data):
        raise ValueError('ENA returned no run list')
    return data


def _filters(spec):
    parts = []
    platform = spec.get('platform')
    if platform not in (None, ''):
        platform = str(platform).upper().replace(' ', '_')
        if platform not in PLATFORMS:
            raise ValueError('platform must be one of ' + ', '.join(sorted(PLATFORMS)))
        parts.append('instrument_platform="%s"' % platform)
    layout = spec.get('layout')
    if layout not in (None, ''):
        layout = str(layout).upper()
        if layout not in LAYOUTS:
            raise ValueError('layout must be PAIRED or SINGLE')
        parts.append('library_layout="%s"' % layout)
    strategy = spec.get('strategy')
    if strategy not in (None, ''):
        strategy = _STRATEGY.get(str(strategy).lower())
        if not strategy:
            raise ValueError('strategy must be one of ' + ', '.join(sorted(STRATEGIES)))
        parts.append('library_strategy="%s"' % strategy)
    return parts


def search_runs(sources, spec):
    """A sequencing_runs receipt. sources is a lab_sources.Sources (its fetch, taxon lookup and plain-term rules)."""
    from lab_sources import receipt, _plain_term
    allowed = {'source', 'accession', 'organism', 'taxon_id', 'term', 'platform', 'layout', 'strategy', 'limit'}
    if set(spec) - allowed:
        raise ValueError('unsupported sequencing_runs arguments: ' + ', '.join(sorted(set(spec) - allowed)))
    limit = _limit(spec.get('limit'))
    fields = ','.join(RUN_FIELDS)
    if spec.get('accession') not in (None, ''):
        acc = accession(spec['accession'])
        if set(spec) - {'source', 'accession', 'limit'}:
            raise ValueError('an accession is looked up alone; organism, term and filters are for a search')
        data, _ = sources.fetch(ENA_PORTAL + 'filereport?' + urlencode({
            'accession': acc, 'result': 'read_run', 'fields': fields, 'format': 'json', 'limit': limit}))
        rows = _rows(data)
        records = [_run_record(r) for r in rows[:limit]]
        # a run, experiment or study is checked against what came back; sample and submission accessions have
        # primary and secondary forms ENA does not both return, so they are not
        if re.fullmatch(r'[SED]R[RXP][0-9]+|PRJ[A-Z]+[0-9]+', acc):
            keys = ('run_accession', 'experiment_accession', 'study_accession', 'secondary_study_accession')
            if any(acc not in {str(r.get(k) or '').upper() for k in keys} for r in records):
                raise ValueError('ENA returned runs that do not belong to the requested accession')
        return receipt('sequencing_runs', {'source': 'sequencing_runs', 'accession': acc, 'limit': limit}, records,
                       metadata=_meta('ENA_Portal_filereport', len(records), limit))
    filters = _filters(spec)
    taxon = sources._taxon(spec) if (spec.get('organism') or spec.get('taxon_id') not in (None, '')) else None
    if (spec.get('organism') or spec.get('taxon_id') not in (None, '')) and not taxon:
        raise ValueError('NCBI Taxonomy found no organism by that name; name it as NCBI does or give its taxon_id')
    term = _plain_term(spec['term']) if spec.get('term') not in (None, '') else None
    if not taxon and not term:
        raise ValueError('a sequencing_runs search needs an exact accession, an organism (or taxon_id), or a term')
    query = {'source': 'sequencing_runs', 'limit': limit,
             **({'taxon_id': taxon} if taxon else {}), **({'term': term} if term else {}),
             **({'organism': spec['organism']} if spec.get('organism') else {}),
             **{k: spec[k] for k in ('platform', 'layout', 'strategy') if spec.get(k) not in (None, '')}}
    via = None
    if term:
        # ENA's portal search has no free-text field; NCBI SRA does. Its runs are then read from ENA, which mirrors
        # every INSDC run and carries the file locations.
        words = [term] + (['txid%s[Organism:exp]' % taxon] if taxon else [])
        found, _ = sources.fetch(NCBI_BASE + 'esearch.fcgi?' + urlencode({
            'db': 'sra', 'term': ' AND '.join(words), 'retmode': 'json', 'retmax': limit, 'tool': 'vintos_lab'}))
        ids = (found.get('esearchresult') or {}).get('idlist') or [] if isinstance(found, dict) else []
        if any(not re.fullmatch(r'[0-9]{1,12}', str(i)) for i in ids):
            raise ValueError('NCBI returned invalid SRA identifiers')
        runs = []
        if ids:
            from lab_sources import fetch_json
            if sources.fetch is fetch_json: time.sleep(0.4)     # NCBI: three requests a second
            summary, _ = sources.fetch(NCBI_BASE + 'esummary.fcgi?' + urlencode({
                'db': 'sra', 'id': ','.join(map(str, ids[:limit])), 'retmode': 'json', 'tool': 'vintos_lab'}))
            payload = (summary.get('result') or {}) if isinstance(summary, dict) else {}
            for uid in ids[:limit]:
                row = payload.get(str(uid)) or {}
                for acc in re.findall(r'acc="(' + RUN_ACCESSION + ')"', str(row.get('runs') or '')):
                    if acc not in runs:
                        runs.append(acc)
        runs = runs[:limit]
        via = {'service': 'NCBI_SRA_EUtilities', 'sra_uids': [str(i) for i in ids[:limit]], 'runs_named': runs}
        if not runs:
            return receipt('sequencing_runs', query, [], metadata=dict(
                _meta('NCBI_SRA_EUtilities', 0, limit), via=via,
                meaning='no run matched this search; not an assertion that none exists'))
        ena_query = '(' + ' OR '.join('run_accession="%s"' % r for r in runs) + ')'
    else:
        ena_query = 'tax_tree(%s)' % taxon
    ena_query = ' AND '.join([ena_query] + filters)
    data, _ = sources.fetch(ENA_PORTAL + 'search?' + urlencode({
        'result': 'read_run', 'query': ena_query, 'fields': fields, 'format': 'json', 'limit': limit}))
    records = [_run_record(r) for r in _rows(data)[:limit]]
    if via:
        named = set(via['runs_named'])
        records = [r for r in records if r.get('run_accession') in named]
        via['not_in_ena'] = sorted(named - {r.get('run_accession') for r in records})
    if taxon and not via:
        bad = [r for r in records if r.get('tax_id') is None]
        if bad:
            raise ValueError('ENA returned runs without a taxon')
    return receipt('sequencing_runs', dict(query, executed_query=ena_query), records,
                   metadata=dict(_meta('ENA_Portal_search', len(records), limit), **({'via': via} if via else {})))


def _meta(service, count, limit):
    return {'service': service, 'coverage': 'bounded_first_page', 'returned': count, 'limit': limit,
            'interpretation': 'archive run metadata as submitted; not a quality, contamination or content check',
            'next_step': 'sequencing_reads {run_accession, reads, mate} keeps the first reads of one file as a Lab '
                         'artifact for sequence_viewer or ngs_workbench'}


# ----- the bounded read sample -------------------------------------------------------------------------------

def lab_root():
    ws = Path(os.environ.get('SPARK_WORKSPACE', os.path.expanduser('~/.vintos/workspace')))
    return ws / 'memory' / 'chemistry-lab'


def sample_dir():
    return lab_root() / 'artifacts' / 'sequencing'


def first_reads(stream, reads):
    """(fastq_text_bytes, stats) from a gzip FASTQ byte stream, reading only as far as `reads` complete records.

    stream.read(n) is called in CHUNK pieces and never past MAX_COMPRESSED_BYTES. Multi-member gzip (bgzip) is
    followed member by member. A record is four lines: @id, bases, +, qualities of the same length."""
    out = bytearray(); pending = b''; record = []; kept = 0; downloaded = 0
    stopped = None
    decoder = zlib.decompressobj(31)
    alphabet = re.compile(rb'[ACGTNURYKMSWBDHVacgtnurykmswbdhv.-]*')
    def take(line):
        nonlocal kept, stopped
        record.append(line)
        if len(record) < 4:
            return False
        head, seq, plus, qual = record
        record.clear()
        if not head.startswith(b'@') or not plus.startswith(b'+') or len(seq) != len(qual) or not alphabet.fullmatch(seq):
            raise ValueError('the file is not FASTQ where it was read (record %d)' % (kept + 1))
        text = b'\n'.join((head, seq, plus, qual)) + b'\n'
        if len(out) + len(text) > MAX_SAMPLE_TEXT_BYTES:
            stopped = 'sample_text_cap'
            return True
        out.extend(text); kept += 1
        if kept >= reads:
            stopped = 'requested_reads'
            return True
        return False
    done = False
    while not done:
        if downloaded >= MAX_COMPRESSED_BYTES:
            stopped = 'download_cap'
            break
        chunk = stream.read(min(CHUNK, MAX_COMPRESSED_BYTES - downloaded))
        if not chunk:
            stopped = stopped or 'end_of_file'
            break
        downloaded += len(chunk)
        data = chunk
        while data:
            try:
                text = decoder.decompress(data)
            except zlib.error as exc:
                raise ValueError('the file is not readable gzip') from exc
            data = b''
            if decoder.eof:
                data = decoder.unused_data
                decoder = zlib.decompressobj(31)
            pending += text
            lines = pending.split(b'\n')
            pending = lines.pop()
            for line in lines:
                if take(line.rstrip(b'\r')):
                    done = True
                    break
            if done:
                break
            if len(pending) > 1024 * 1024:
                raise ValueError('a FASTQ line longer than 1 MiB')
    if not done and pending and stopped == 'end_of_file':
        take(pending.rstrip(b'\r'))
    if not kept:
        raise ValueError('no complete FASTQ record in the part of the file read')
    return bytes(out), {'reads_kept': kept, 'compressed_bytes_read': downloaded, 'stopped_by': stopped}


def _recent_samples(folder, now):
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.glob('*.fastq.gz') if p.is_file() and now - p.stat().st_mtime < 86400)


def sample_reads(sources, spec, *, now=None):
    """A sequencing_reads receipt: the first reads of one run's FASTQ file, kept as a Lab artifact."""
    from lab_sources import receipt
    allowed = {'source', 'run_accession', 'accession', 'reads', 'mate'}
    if set(spec) - allowed:
        raise ValueError('unsupported sequencing_reads arguments: ' + ', '.join(sorted(set(spec) - allowed)))
    run = run_accession(spec.get('run_accession') or spec.get('accession'))
    reads = spec.get('reads', DEFAULT_SAMPLE_READS)
    if type(reads) is not int or not 1 <= reads <= MAX_SAMPLE_READS:
        raise ValueError('reads must be 1..%d' % MAX_SAMPLE_READS)
    mate = spec.get('mate')
    if mate not in (None, 1, 2):
        raise ValueError('mate must be 1 or 2 (paired runs), or left out')
    data, _ = sources.fetch(ENA_PORTAL + 'filereport?' + urlencode({
        'accession': run, 'result': 'read_run', 'fields': ','.join(RUN_FIELDS), 'format': 'json', 'limit': 1}))
    rows = [r for r in _rows(data) if str(r.get('run_accession') or '').upper() == run]
    if not rows:
        raise ValueError('ENA has no run %s' % run)
    rec = _run_record(rows[0])
    files = rec['files']
    if not files:
        raise ValueError('ENA lists no FASTQ file for run %s (it may hold only submitted or SRA-format files)' % run)
    paired = [f for f in files if f['mate'] in (1, 2)]
    if mate is not None:
        chosen = [f for f in files if f['mate'] == mate]
        if not chosen:
            raise ValueError('run %s has no mate %d file' % (run, mate))
    else:
        unpaired = [f for f in files if f['mate'] is None]
        chosen = unpaired or [f for f in paired if f['mate'] == 1]
    chosen = chosen[0]
    folder = sample_dir()
    name = '%s_%s_first%d.fastq.gz' % (run, 'mate%d' % chosen['mate'] if chosen['mate'] else 'single', reads)
    target = folder / name
    provenance_path = folder / (name + '.provenance.json')
    now = time.time() if now is None else now
    reused = False
    if target.is_file() and not target.is_symlink() and provenance_path.is_file():
        try:
            provenance = json.loads(provenance_path.read_text())
            if provenance.get('artifact_sha256') == hashlib.sha256(target.read_bytes()).hexdigest():
                reused = True
        except (OSError, ValueError):
            reused = False
    if not reused:
        if _recent_samples(folder, now) >= MAX_SAMPLES_PER_DAY:
            raise RuntimeError('read samples used up: %d new samples in 24 hours' % MAX_SAMPLES_PER_DAY)
        with sources.open_stream(chosen['url']) as stream:
            text, stats = first_reads(stream, reads)
        buf = io.BytesIO()
        with gzip.GzipFile(filename='', mode='wb', fileobj=buf, mtime=0) as gz:
            gz.write(text)
        blob = buf.getvalue()
        if len(blob) > MAX_ARTIFACT_BYTES:
            raise ValueError('the sample is %d bytes compressed, over the %d a Lab instrument can take; ask for '
                             'fewer reads' % (len(blob), MAX_ARTIFACT_BYTES))
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / ('.' + name + '.tmp')
        tmp.write_bytes(blob); os.chmod(tmp, 0o600); os.replace(tmp, target)
        provenance = {'run_accession': run, 'file': chosen['name'], 'source_url': chosen['url'], 'mate': chosen['mate'],
                      'provider_file_bytes': chosen['bytes'], 'provider_file_md5': chosen['md5'],
                      'requested_reads': reads, **stats,
                      'sample_fastq_sha256': hashlib.sha256(text).hexdigest(),
                      'artifact': str(target.relative_to(lab_root())), 'artifact_bytes': len(blob),
                      'artifact_sha256': hashlib.sha256(blob).hexdigest(),
                      'retrieved_at': datetime.fromtimestamp(now, timezone.utc).isoformat(),
                      'selection': 'first_reads_of_one_file_not_a_random_sample',
                      'provider_md5_covers': 'the whole provider file; the sample is checked by its own SHA-256'}
        tmp = folder / ('.' + name + '.provenance.tmp')
        tmp.write_text(json.dumps(provenance, indent=1, sort_keys=True)); os.chmod(tmp, 0o600)
        os.replace(tmp, provenance_path)
    record = {'run_accession': run, 'study_accession': rec.get('study_accession'),
              'scientific_name': rec.get('scientific_name'), 'tax_id': rec.get('tax_id'),
              'instrument_platform': rec.get('instrument_platform'), 'library_layout': rec.get('library_layout'),
              'library_strategy': rec.get('library_strategy'), 'run_read_count': rec.get('read_count'),
              **{k: provenance.get(k) for k in ('file', 'source_url', 'mate', 'provider_file_bytes', 'provider_file_md5',
                                                'reads_kept', 'compressed_bytes_read', 'stopped_by', 'artifact',
                                                'artifact_bytes', 'artifact_sha256', 'sample_fastq_sha256')},
              'reused_existing_sample': reused}
    return receipt('sequencing_reads', {'source': 'sequencing_reads', 'run_accession': run, 'reads': reads,
                                        **({'mate': mate} if mate else {})}, [record], metadata={
        'service': 'ENA_FASTQ_HTTPS', 'coverage': 'first_reads_of_one_file',
        'selection': 'the first reads of the file in archive order, not a random sample of the run',
        'interpretation': 'raw reads as deposited; no quality, contamination or identity check has been made',
        'instruments': 'the artifact is one input file for sequence_viewer (sequence.run_analysis) or '
                       'ngs_workbench; give its artifact path under files'})

#!/usr/bin/env python3
"""Acquire, verify, index, and query the local IMG/VR high-confidence release.

The model never chooses paths or commands. Query operations are bounded and
read-only. Provider observations remain annotations, not novelty or function.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
from urllib.request import Request, urlopen
import zipfile

RELEASE = 'IMG_VR_2022-12-19_7.1'
DATASET = 'Custom_MPI-IMG_VR'
MANIFEST_URL = 'https://files.jgi.doe.gov/search/?datasets=Custom_MPI-IMG_VR&include_private_data=1&x=50'
RESTORE_URL = 'https://files.jgi.doe.gov/request_archived_files/'
DOWNLOAD_URL = 'https://files-download.jgi.doe.gov/download_files/'
NERSC_BASE = 'https://portal.nersc.gov/dna/microbial/prokpubs/for-Asier-Sana/'
TOKEN_FILE = Path.home()/'.config/vintos/jgi-token'
ROOT = Path(os.environ.get('VINTOS_IMGVR_ROOT', Path.home()/'.vintos/data/imgvr-v4.1-hc')).expanduser()
DB = ROOT/'imgvr.sqlite3'
MANIFEST = ROOT/'provider-manifest.json'
ARCHIVE = ROOT/'imgvr-v4.1-hc.zip'
MMSEQS = Path(os.environ.get('VINTOS_MMSEQS', Path.home()/'.local/bin/mmseqs')).expanduser()
MMSEQS_DB = ROOT/'mmseqs/imgvr-proteins'
MMSEQS_READY = ROOT/'mmseqs/index-ready.json'
TMP = ROOT/'tmp'
MIN_FREE_BYTES = 250 * 1024**3
EXPECTED = frozenset({
    'README-high_confidence.txt',
    'IMGVR_all_Host_information-high_confidence.tsv',
    'IMGVR_all_Sequence_information-high_confidence.tsv',
    'IMGVR_all_nucleotides-high_confidence.fna.gz',
    'IMGVR_all_proteins-high_confidence.faa.gz',
})
PUBLIC_FILES = (
    ('IMGVR_all_Sequence_information-high_confidence.tsv',
     'IMGVR_all_Sequence_information-high_confidence-unrestricted_only.tsv', 1841330222),
    ('IMGVR_all_nucleotides-high_confidence.fna.gz',
     'IMGVR_all_nucleotides-high_confidence-ur.fna.gz', 24832073240),
    ('IMGVR_all_proteins-high_confidence.faa.gz',
     'IMGVR_all_proteins-high_confidence-ur.faa.gz', 15688814725),
)
NUCLEOTIDES_GZ = ROOT/'IMGVR_all_nucleotides-high_confidence.fna.gz'
NUCLEOTIDES = ROOT/'IMGVR_all_nucleotides-high_confidence.fna'
PROTEINS_GZ = ROOT/'IMGVR_all_proteins-high_confidence.faa.gz'


def _json_url(url, *, token=None, payload=None, opener=urlopen):
    body = None if payload is None else json.dumps(payload, separators=(',', ':')).encode()
    headers = {'Accept': 'application/json', 'User-Agent': 'Vintos-Lab/2.0'}
    if payload is not None: headers['Content-Type'] = 'application/json'
    if token: headers['Authorization'] = token
    with opener(Request(url, data=body, headers=headers, method='POST' if body else 'GET'), timeout=60) as response:
        raw = response.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024: raise RuntimeError('JGI response exceeded metadata limit')
    return json.loads(raw)


def provider_manifest(*, opener=urlopen):
    payload = _json_url(MANIFEST_URL, opener=opener)
    datasets = payload.get('organisms') or []
    if len(datasets) != 1 or datasets[0].get('id') != DATASET:
        raise RuntimeError('JGI did not return the exact IMG/VR dataset')
    rows = []
    for item in datasets[0].get('files') or []:
        locations = ((item.get('metadata') or {}).get('portal') or {}).get('display_location') or []
        if RELEASE not in locations: continue
        row = {key:item.get(key) for key in ('_id','file_id','file_name','file_size','md5sum','file_status')}
        if not re.fullmatch(r'[0-9a-f]{24}', str(row['_id'] or '')): raise RuntimeError('invalid JGI file id')
        if not re.fullmatch(r'[0-9a-f]{32}', str(row['md5sum'] or '')): raise RuntimeError('invalid JGI checksum')
        if type(row['file_size']) is not int or row['file_size'] < 1: raise RuntimeError('invalid JGI file size')
        rows.append(row)
    if {x['file_name'] for x in rows} != EXPECTED:
        raise RuntimeError('JGI high-confidence release file set changed')
    rows.sort(key=lambda x:x['file_name'])
    return {'dataset':DATASET, 'release':RELEASE, 'files':rows,
            'compressed_bytes':sum(x['file_size'] for x in rows),
            'truth_status':'provider_file_metadata_not_local_installation'}


def _token(path=TOKEN_FILE):
    path = Path(path)
    if not path.is_file(): raise RuntimeError('jgi_token_not_configured')
    if path.stat().st_mode & 0o077: raise RuntimeError('jgi_token_permissions_must_be_0600')
    value = path.read_text().strip()
    if len(value) < 20 or any(c.isspace() for c in value): raise RuntimeError('invalid_jgi_token_file')
    return value


def _disk_status(root=ROOT):
    root = Path(root)
    probe = root
    while not probe.exists() and probe != probe.parent: probe = probe.parent
    usage = shutil.disk_usage(probe)
    return {'path':str(root), 'free_bytes':usage.free, 'required_free_bytes':MIN_FREE_BYTES,
            'enough_for_download_and_index':usage.free >= MIN_FREE_BYTES}


def status(*, root=ROOT):
    root = Path(root)
    disk = _disk_status(root)
    return {**disk, 'token_configured':TOKEN_FILE.is_file(), 'archive_present':(root/ARCHIVE.name).is_file(),
            'manifest_present':(root/MANIFEST.name).is_file(), 'metadata_index':(root/DB.name).is_file(),
            'nucleotide_fasta':(root/NUCLEOTIDES.name).is_file(),
            'protein_search_db':(root/'mmseqs/index-ready.json').is_file(),
            'ready':all(((root/DB.name).is_file(), (root/NUCLEOTIDES.name).is_file(),
                         (root/'mmseqs/index-ready.json').is_file()))}


def save_manifest(*, opener=urlopen):
    manifest = provider_manifest(opener=opener)
    disk = _disk_status()
    if not disk['enough_for_download_and_index']:
        raise RuntimeError('imgvr_requires_250_gib_free_before_transfer')
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = MANIFEST.with_suffix('.tmp')
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    os.chmod(temporary, 0o600); os.replace(temporary, MANIFEST)
    return manifest


def public_manifest():
    """Pinned metadata for the public DOE NERSC unrestricted-only mirror."""
    return {
        'dataset': DATASET,
        'release': RELEASE,
        'source': 'doe_nersc_public_unrestricted_only_snapshot_2024-01-13',
        'files': [
            {'file_name': local, 'source_name': remote,
             'url': NERSC_BASE + remote, 'file_size': size}
            for local, remote, size in PUBLIC_FILES
        ],
        'compressed_bytes': sum(row[2] for row in PUBLIC_FILES),
        'truth_status': ('official_public_mirror_transport_pinned_by_name_and_size;'
                         'local_sha256_recorded_after_tls_transfer;not_provider_digest'),
    }


def download_public(*, runner=subprocess.run):
    disk = _disk_status()
    if not disk['enough_for_download_and_index']:
        raise RuntimeError('imgvr_requires_250_gib_free_before_transfer')
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest = public_manifest()
    for row in manifest['files']:
        target = ROOT/row['file_name']
        partial = target.with_suffix(target.suffix + '.part')
        runner(['curl','--fail','--location','--retry','8','--retry-delay','10',
                '--continue-at','-','--output',str(partial),row['url']], check=True)
        if partial.stat().st_size != row['file_size']:
            raise RuntimeError('public mirror size mismatch for ' + row['file_name'])
        digest = hashlib.sha256()
        with partial.open('rb') as handle:
            for block in iter(lambda:handle.read(8*1024*1024), b''): digest.update(block)
        row['sha256'] = digest.hexdigest()
        os.replace(partial, target)
    temporary = MANIFEST.with_suffix('.tmp')
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    os.chmod(temporary, 0o600); os.replace(temporary, MANIFEST)
    return {'source':manifest['source'], 'files':len(manifest['files']),
            'bytes':manifest['compressed_bytes'], 'manifest':str(MANIFEST)}


def _restore_payload(manifest, *, send_mail=False):
    dataset = {'file_ids':[x['_id'] for x in manifest['files']]}
    return {'ids':{DATASET:dataset}, 'send_mail':bool(send_mail), 'api_version':'2'}


def restore(*, opener=urlopen):
    manifest = save_manifest(opener=opener)
    reply = _json_url(RESTORE_URL, token=_token(), payload=_restore_payload(manifest), opener=opener)
    safe = {k:reply.get(k) for k in ('request_status_url','status','expiration_date','request_id') if k in reply}
    (ROOT/'restore-request.json').write_text(json.dumps(safe, indent=2, sort_keys=True) + '\n')
    os.chmod(ROOT/'restore-request.json', 0o600)
    return safe


def download():
    manifest = save_manifest()
    token = _token()
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload_path = ROOT/'download-payload.json'
    payload_path.write_text(json.dumps({'ids':{DATASET:[x['_id'] for x in manifest['files']]},'api_version':'2'}))
    os.chmod(payload_path, 0o600)
    partial = ARCHIVE.with_suffix('.zip.part')
    with tempfile.NamedTemporaryFile('w', prefix='imgvr-curl-', delete=False) as cfg:
        cfg.write('request = "POST"\nurl = "' + DOWNLOAD_URL + '"\n')
        cfg.write('header = "Accept: application/zip"\nheader = "Content-Type: application/json"\n')
        cfg.write('header = "Authorization: ' + token.replace('\\','\\\\').replace('"','\\"') + '"\n')
        cfg.write('data = "@' + str(payload_path) + '"\noutput = "' + str(partial) + '"\n')
        cfg.write('fail\nlocation\nretry = 5\nretry-delay = 5\n')
        config_path = Path(cfg.name)
    os.chmod(config_path, 0o600)
    try:
        subprocess.run(['curl','--config',str(config_path)], check=True)
    finally:
        config_path.unlink(missing_ok=True)
    if not zipfile.is_zipfile(partial): raise RuntimeError('JGI download was not a ZIP archive')
    os.replace(partial, ARCHIVE)
    return {'archive':str(ARCHIVE), 'bytes':ARCHIVE.stat().st_size}


def _safe_extract():
    manifest = json.loads(MANIFEST.read_text())
    expected = {x['file_name']:x for x in manifest['files']}
    with zipfile.ZipFile(ARCHIVE) as archive:
        members = [x for x in archive.infolist() if not x.is_dir()]
        names = [Path(x.filename).name for x in members]
        if set(names) != set(expected) or len(names) != len(set(names)):
            raise RuntimeError('downloaded ZIP file set did not match provider manifest')
        for member in members:
            name = Path(member.filename).name
            target = ROOT/name; temporary = target.with_suffix(target.suffix+'.part')
            digest = hashlib.md5(usedforsecurity=False)
            with archive.open(member) as source, temporary.open('wb') as sink:
                while True:
                    block = source.read(8*1024*1024)
                    if not block: break
                    sink.write(block); digest.update(block)
            if temporary.stat().st_size != expected[name]['file_size'] or digest.hexdigest() != expected[name]['md5sum']:
                temporary.unlink(missing_ok=True); raise RuntimeError('provider size or checksum failed for '+name)
            os.replace(temporary,target)


def verify_files():
    manifest = json.loads(MANIFEST.read_text())
    checked = []
    for row in manifest['files']:
        path = ROOT/row['file_name']
        if not path.is_file() or path.stat().st_size != row['file_size']:
            raise RuntimeError('missing or wrong-sized IMG/VR file: '+row['file_name'])
        algorithm = 'sha256' if row.get('sha256') else 'md5sum'
        digest = hashlib.sha256() if algorithm == 'sha256' else hashlib.md5(usedforsecurity=False)
        with path.open('rb') as handle:
            for block in iter(lambda:handle.read(8*1024*1024), b''): digest.update(block)
        if digest.hexdigest() != row[algorithm]: raise RuntimeError('checksum mismatch: '+row['file_name'])
        checked.append(row['file_name'])
    return {'verified':checked, 'release':manifest['release']}


def _normalize_header(value):
    return re.sub(r'[^a-z0-9]+','_',value.lower()).strip('_')


def _build_metadata(connection, path):
    fields = ('uvig','taxon_oid','scaffold_oid','coordinates','ecosystem','votu','length','topology',
              'genomad_score','confidence','estimated_completeness','estimated_contamination','quality',
              'gene_content','taxonomy','taxonomy_method','host_taxonomy','host_method','sequence_origin')
    connection.execute('DROP TABLE IF EXISTS uvig'); connection.execute('DROP TABLE IF EXISTS uvig_fts')
    connection.execute('CREATE TABLE uvig ('+','.join(x+' TEXT' for x in fields)+', UNIQUE(uvig))')
    with path.open(newline='',encoding='utf-8',errors='replace') as handle:
        reader = csv.reader(handle,delimiter='\t'); header = next(reader)
        if len(header) != len(fields) or _normalize_header(header[0]) != 'uvig':
            raise RuntimeError('IMG/VR metadata schema changed')
        batch=[]
        for row in reader:
            if len(row) != len(fields): continue
            batch.append(row)
            if len(batch)>=10000:
                connection.executemany('INSERT INTO uvig VALUES ('+','.join('?' for _ in fields)+')',batch); batch=[]
        if batch: connection.executemany('INSERT INTO uvig VALUES ('+','.join('?' for _ in fields)+')',batch)
    connection.execute('CREATE INDEX uvig_votu ON uvig(votu)')
    connection.execute("CREATE VIRTUAL TABLE uvig_fts USING fts5(uvig,ecosystem,taxonomy,host_taxonomy,sequence_origin,content='uvig')")
    connection.execute('INSERT INTO uvig_fts(rowid,uvig,ecosystem,taxonomy,host_taxonomy,sequence_origin) SELECT rowid,uvig,ecosystem,taxonomy,host_taxonomy,sequence_origin FROM uvig')


def _build_fasta_index(connection, path):
    connection.execute('DROP TABLE IF EXISTS nucleotide_offsets')
    connection.execute('CREATE TABLE nucleotide_offsets (uvig TEXT PRIMARY KEY, start INTEGER NOT NULL, end INTEGER NOT NULL, header TEXT NOT NULL) WITHOUT ROWID')
    batch=[]; current=None; start=0
    with path.open('rb') as handle:
        while True:
            position=handle.tell(); line=handle.readline()
            if not line:
                if current: batch.append((current,start,position,header))
                break
            if line.startswith(b'>'):
                if current: batch.append((current,start,position,header))
                header=line[1:].decode('ascii','strict').strip(); current=header.split('|',1)[0]
                if not re.fullmatch(r'IMGVR_UViG_[0-9]+_[0-9]+',current): raise RuntimeError('invalid IMG/VR FASTA identifier')
                start=handle.tell()
            if len(batch)>=10000:
                connection.executemany('INSERT INTO nucleotide_offsets VALUES (?,?,?,?)',batch); batch=[]
        if batch: connection.executemany('INSERT INTO nucleotide_offsets VALUES (?,?,?,?)',batch)


def build_indexes():
    verify_files()
    if not NUCLEOTIDES.is_file():
        temporary=NUCLEOTIDES.with_suffix('.fna.part')
        with temporary.open('wb') as sink:
            subprocess.run(['pigz','-dc',str(NUCLEOTIDES_GZ)],stdout=sink,check=True)
        os.replace(temporary,NUCLEOTIDES)
    temporary=DB.with_suffix('.sqlite3.part'); temporary.unlink(missing_ok=True)
    connection=sqlite3.connect(temporary)
    try:
        connection.execute('PRAGMA journal_mode=DELETE'); connection.execute('PRAGMA synchronous=NORMAL')
        _build_metadata(connection, ROOT/'IMGVR_all_Sequence_information-high_confidence.tsv')
        _build_fasta_index(connection,NUCLEOTIDES)
        connection.execute('CREATE TABLE provenance (release TEXT, manifest_sha256 TEXT, indexed_at TEXT)')
        connection.execute("INSERT INTO provenance VALUES (?,?,datetime('now'))",(RELEASE,hashlib.sha256(MANIFEST.read_bytes()).hexdigest()))
        connection.commit()
    finally: connection.close()
    os.replace(temporary,DB)
    MMSEQS_DB.parent.mkdir(parents=True,exist_ok=True); TMP.mkdir(parents=True,exist_ok=True)
    if not MMSEQS.is_file(): raise RuntimeError('mmseqs_not_installed')
    MMSEQS_READY.unlink(missing_ok=True)
    subprocess.run([str(MMSEQS),'createdb',str(PROTEINS_GZ),str(MMSEQS_DB)],check=True)
    subprocess.run([str(MMSEQS),'createindex',str(MMSEQS_DB),str(TMP),
                    '--split-memory-limit','12G','--remove-tmp-files','1',
                    '--threads',str(max(1,min(8,os.cpu_count() or 1)))],check=True)
    MMSEQS_READY.write_text(json.dumps({'release':RELEASE,'mmseqs':str(MMSEQS),
                                        'manifest_sha256':hashlib.sha256(MANIFEST.read_bytes()).hexdigest()},
                                       sort_keys=True)+'\n')
    os.chmod(MMSEQS_READY,0o600)
    return status()


def install():
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get('source') == 'doe_nersc_public_unrestricted_only_snapshot_2024-01-13':
        verified=verify_files()
    else:
        _safe_extract(); verified=verify_files()
    indexed=build_indexes()
    return {'verified':verified,'status':indexed}


def _plain_term(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 .,_:-]{2,119}',value):
        raise ValueError('use a 3..120 character IMG/VR search phrase')
    return value.strip()


def _uvig(value):
    if not isinstance(value,str) or not re.fullmatch(r'IMGVR_UViG_[0-9]+_[0-9]+',value):
        raise ValueError('exact sourced IMG/VR UViG identifier required')
    return value


def _row(record): return {key:record[key] for key in record.keys()}


def query(spec, *, db=DB, nucleotide=NUCLEOTIDES, mmseqs=MMSEQS, mmseqs_db=MMSEQS_DB, runner=subprocess.run):
    if not isinstance(spec,dict): raise ValueError('IMG/VR query must be an object')
    db=Path(db); nucleotide=Path(nucleotide); mmseqs=Path(mmseqs); mmseqs_db=Path(mmseqs_db)
    if not db.is_file(): raise RuntimeError('imgvr_local_index_not_ready')
    operation=spec.get('operation'); limit=spec.get('limit',4)
    if type(limit) is not int or not 1<=limit<=8: raise ValueError('limit must be 1..8')
    connection=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True); connection.row_factory=sqlite3.Row
    try:
        if operation=='metadata':
            term=_plain_term(spec.get('term')); tokens=re.findall(r'[A-Za-z0-9]+',term)
            expression=' AND '.join('"'+x+'"' for x in tokens)
            rows=connection.execute('SELECT u.* FROM uvig_fts f JOIN uvig u ON u.rowid=f.rowid WHERE uvig_fts MATCH ? LIMIT ?', (expression,limit)).fetchall()
            return {'records':[_row(x) for x in rows], 'coverage':'bounded_local_fts_first_'+str(limit)}
        if operation=='uvig':
            identifier=_uvig(spec.get('uvig')); row=connection.execute('SELECT * FROM uvig WHERE uvig=?',(identifier,)).fetchone()
            if row is None: return {'records':[],'coverage':'exact_identifier_absent'}
            offset=connection.execute('SELECT start,end,header FROM nucleotide_offsets WHERE uvig=?',(identifier,)).fetchone()
            if offset is None or not nucleotide.is_file(): raise RuntimeError('imgvr_nucleotide_index_incomplete')
            with nucleotide.open('rb') as handle:
                handle.seek(offset['start']); sequence=b''.join(handle.read(offset['end']-offset['start']).split()).decode('ascii')
            start,end=spec.get('start',1),spec.get('end',min(len(sequence),12000))
            if type(start) is not int or type(end) is not int or not 1<=start<=end<=len(sequence) or end-start+1>12000:
                raise ValueError('IMG/VR nucleotide slice must be one-based inclusive and at most 12000 bases')
            value=_row(row); value.update({'fasta_header':offset['header'],'slice_start':start,'slice_end':end,'sequence':sequence[start-1:end]})
            return {'records':[value],'coverage':'exact_uvig_bounded_sequence_slice'}
        if operation=='protein_similarity':
            sequence=str(spec.get('sequence') or '').upper()
            if not re.fullmatch(r'[ACDEFGHIKLMNPQRSTVWYBXZJUO*]{20,2000}',sequence):
                raise ValueError('sourced protein sequence of 20..2000 residues required')
            ready_marker=mmseqs_db.parent/'index-ready.json'
            if not mmseqs.is_file() or not Path(str(mmseqs_db)+'.dbtype').is_file() or not ready_marker.is_file():
                raise RuntimeError('imgvr_protein_search_not_ready')
            with tempfile.TemporaryDirectory(prefix='imgvr-query-') as temporary:
                temporary=Path(temporary); query_fasta=temporary/'query.faa'; output=temporary/'hits.tsv'; work=temporary/'work'
                query_fasta.write_text('>sourced_query\n'+sequence+'\n')
                command=[str(mmseqs),'easy-search',str(query_fasta),str(mmseqs_db),str(output),str(work),
                         '--format-output','target,pident,alnlen,evalue,bits,qlen,tlen','--max-seqs',str(limit),
                         '--split-memory-limit','12G','--threads','1']
                runner(command,check=True,capture_output=True,text=True,timeout=180)
                rows=[]
                if output.is_file():
                    for line in output.read_text().splitlines()[:limit]:
                        values=line.split('\t'); target=values[0]; uvig=target.split('|',1)[0]
                        rows.append({'target':target,'uvig':uvig,'percent_identity':float(values[1]),'alignment_length':int(values[2]),
                                     'evalue':float(values[3]),'bits':float(values[4]),'query_length':int(values[5]),'target_length':int(values[6])})
                return {'records':rows,'coverage':'bounded_mmseqs_local_high_confidence_release'}
        raise ValueError('unsupported IMG/VR operation')
    finally: connection.close()


def main():
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest='command',required=True)
    for name in ('status','manifest','restore','download','download-public','install','verify'): sub.add_parser(name)
    query_parser=sub.add_parser('query'); query_parser.add_argument('json')
    args=parser.parse_args()
    if args.command=='status': result=status()
    elif args.command=='manifest': result=save_manifest()
    elif args.command=='restore': result=restore()
    elif args.command=='download': result=download()
    elif args.command=='download-public': result=download_public()
    elif args.command=='install': result=install()
    elif args.command=='verify': result=verify_files()
    else: result=query(json.loads(args.json))
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__': main()

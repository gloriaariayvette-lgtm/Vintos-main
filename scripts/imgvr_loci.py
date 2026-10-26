#!/usr/bin/env python3
"""Verified protein-to-locus records over the local IMG/VR release, and bounded
neighborhoods around them.

Protein search returns a hit identifier and a score. It does not say where on a
genome that protein sits, so nothing downstream can look at the genes and repeats
beside it. This module supplies that missing join, and only when it is certain.

The join is bounded by construction. A protein's own FASTA header names its UViG,
so the search is one contig -- the contig that protein is already sourced from --
translated in six frames and matched exactly. There is no global scan. A protein
that matches that contig in exactly one place becomes a locus record; zero matches
or more than one stay unjoined, with the reason recorded. An amino-acid sequence
whose first residue is an annotated M over a non-ATG start codon is matched on its
remainder, with the preceding codon required to be a recognized alternative start,
and the record says so.

The release ships no GFF or other gene map (checked 25 October 2026: the file set
is README, host information, sequence information, nucleotides, proteins). So the
annotation source of every record here is `translated_match`, never a provider map.
If a later release supplies a map, prefer it and record it as the source.

Coordinates are one-based inclusive on the UViG contig **as served in the release
nucleotide FASTA**. That is not the scaffold-level provirus range in the metadata
`Coordinates` column or the FASTA header's trailing field; the two must never be
mixed. The served contig is the UViG itself, and its length matches the metadata
`Length` column.

No network. No writes to the release. Nothing here establishes novelty or function.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import os
import random
import re
import sqlite3
import time
from pathlib import Path

RELEASE = 'IMG_VR_2022-12-19_7.1'
ROOT = Path(os.environ.get('VINTOS_IMGVR_ROOT', Path.home()/'.vintos/data/imgvr-v4.1-hc')).expanduser()
DB = ROOT/'imgvr.sqlite3'
NUCLEOTIDES = ROOT/'IMGVR_all_nucleotides-high_confidence.fna'
PROTEINS_GZ = ROOT/'IMGVR_all_proteins-high_confidence.faa.gz'
MANIFEST = ROOT/'provider-manifest.json'

COORDINATE_CONVENTION = 'one_based_inclusive_on_uvig_contig_as_served_not_scaffold_provirus_range'
ANNOTATION_SOURCE = 'translated_match'
GENE_MAP_ABSENT = 'release_ships_no_gff_or_equivalent_gene_map'

CONTIG_SIZE_CAP = 2_000_000
TIME_CAP_SECONDS = 120.0
WINDOW_CAP = 24_000
REPEAT_WINDOW_CAP = 12_000
COHORT_CAP = 24
PROTEIN_MIN, PROTEIN_MAX = 20, 2000
ALT_STARTS = ('ATG', 'GTG', 'TTG', 'CTG', 'ATT', 'ATC', 'ATA')

_BASES = 'TCAG'
_RESIDUES = 'FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG'
CODONS = {_BASES[i//16] + _BASES[i//4 % 4] + _BASES[i % 4]: aa for i, aa in enumerate(_RESIDUES)}
_COMPLEMENT = str.maketrans('ACGTN', 'TGCAN')


def translate(dna):
    """Standard genetic code; an unknown codon becomes X rather than guessing."""
    return ''.join(CODONS.get(dna[i:i+3], 'X') for i in range(0, len(dna)-2, 3))


def reverse_complement(dna):
    return dna.translate(_COMPLEMENT)[::-1]


def _sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _uvig(value):
    if not isinstance(value, str) or not re.fullmatch(r'IMGVR_UViG_[A-Za-z0-9._-]+', value):
        raise ValueError('exact sourced IMG/VR UViG identifier required')
    return value


def _protein(value):
    sequence = re.sub(r'\s+', '', str(value or '')).upper()
    if not re.fullmatch(r'[ACDEFGHIKLMNPQRSTVWYBXZJUO*]{%d,%d}' % (PROTEIN_MIN, PROTEIN_MAX), sequence):
        raise ValueError('sourced protein sequence of %d..%d residues required' % (PROTEIN_MIN, PROTEIN_MAX))
    return sequence.replace('*', '')


def _gene_id(value):
    text = str(value or '')
    if not re.fullmatch(r'[A-Za-z0-9._|-]{1,120}', text):
        raise ValueError('sourced protein identifier required')
    return text.split('|')[-1]


def _connect(db):
    db = Path(db)
    if not db.is_file():
        raise RuntimeError('imgvr_local_index_not_ready')
    connection = sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    return connection


# ---------------------------------------------------------------- step 1: inventory

def inventory(*, root=ROOT, db=DB, nucleotide=NUCLEOTIDES, proteins=PROTEINS_GZ, manifest=MANIFEST):
    """Record what this release actually is, before anything is indexed or joined.

    Cheap by design: file sizes, the provider manifest's own digests, and counts
    the existing sqlite index already holds. Counting 109 million protein records
    would need a full streaming pass, so it is reported as unmeasured rather than
    guessed.
    """
    root = Path(root)
    files = []
    recorded = {}
    manifest_path = Path(manifest)
    manifest_sha = None
    if manifest_path.is_file():
        raw = manifest_path.read_bytes()
        manifest_sha = hashlib.sha256(raw).hexdigest()
        try:
            for row in (json.loads(raw).get('files') or []):
                recorded[row.get('file_name')] = row
        except ValueError:
            recorded = {}
    for path in sorted(root.glob('*')):
        if not path.is_file() or path.suffix in ('.log',) or path.name == 'provider-manifest.json':
            continue
        row = recorded.get(path.name) or {}
        files.append({'file_name': path.name, 'bytes': path.stat().st_size,
                      'provider_bytes': row.get('file_size'),
                      'provider_md5': row.get('md5sum'),
                      'local_sha256_at_transfer': row.get('sha256')})
    counts = {'uvig_records': None, 'indexed_segments': None, 'multi_segment_uvigs': None}
    if Path(db).is_file():
        connection = _connect(db)
        try:
            counts['uvig_records'] = connection.execute('SELECT COUNT(*) FROM uvig').fetchone()[0]
            counts['indexed_segments'] = connection.execute(
                'SELECT COUNT(*) FROM nucleotide_offsets').fetchone()[0]
            counts['multi_segment_uvigs'] = connection.execute(
                'SELECT COUNT(*) FROM (SELECT uvig FROM nucleotide_offsets '
                'GROUP BY uvig HAVING COUNT(*)>1)').fetchone()[0]
        finally:
            connection.close()
    return {
        'release': RELEASE,
        'root': str(root),
        'files': files,
        'manifest_sha256': manifest_sha,
        'counts': counts,
        'protein_record_count': None,
        'protein_record_count_reason': 'counting_requires_a_full_streaming_pass_not_run_here',
        'gene_map_available': False,
        'gene_map_reason': GENE_MAP_ABSENT,
        'annotation_source': ANNOTATION_SOURCE,
        'coordinate_convention': COORDINATE_CONVENTION,
        'nucleotide_fasta_present': Path(nucleotide).is_file(),
        'protein_fasta_present': Path(proteins).is_file(),
        'truth_status': 'local_file_inventory_not_a_provider_assertion',
    }


# ------------------------------------------------------- the one-contig translated join

def _segments(connection, uvig, *, nucleotide, segment=None, size_cap=CONTIG_SIZE_CAP):
    """The UViG's contigs as served, keeping the store's multi-segment safeguard.

    A multi-segment UViG does not silently answer for its first contig: the caller
    must name the segment, exactly as `imgvr_store.query`'s `uvig` route requires.
    """
    rows = connection.execute(
        'SELECT start,end,header FROM nucleotide_offsets WHERE uvig=? ORDER BY header',
        (uvig,)).fetchall()
    if not rows:
        return None, 'uvig_absent_from_nucleotide_index', []
    headers = [row['header'] for row in rows]
    if len(rows) > 1 and segment is None:
        return None, 'segment_required_for_multi_segment_uvig', headers
    if segment is not None:
        if not isinstance(segment, str) or len(segment) > 240:
            raise ValueError('exact sourced IMG/VR segment header required')
        rows = [row for row in rows if row['header'] == segment]
        if not rows:
            raise ValueError('segment is not part of the sourced IMG/VR UViG')
    nucleotide = Path(nucleotide)
    if not nucleotide.is_file():
        raise RuntimeError('imgvr_nucleotide_index_incomplete')
    contigs = {}
    with nucleotide.open('rb') as handle:
        for row in rows:
            span = row['end'] - row['start']
            if span > size_cap:
                return None, 'contig_over_size_cap', headers
            handle.seek(row['start'])
            contigs[row['header']] = b''.join(
                handle.read(span).split()).decode('ascii', 'replace').upper()
    return contigs, None, headers


def _matches(contigs, residues, *, deadline=None):
    """Every place `residues` is translated by these contigs, in six frames each."""
    found = []
    for header, dna in contigs.items():
        for strand in ('+', '-'):
            oriented = dna if strand == '+' else reverse_complement(dna)
            for frame in (0, 1, 2):
                if deadline is not None and time.monotonic() > deadline:
                    raise TimeoutError('time_cap_exceeded')
                protein = translate(oriented[frame:])
                at = protein.find(residues)
                while at != -1:
                    begin = frame + at * 3
                    last = begin + len(residues) * 3 - 1
                    if strand == '+':
                        start, end = begin + 1, last + 1
                    else:
                        start, end = len(dna) - last, len(dna) - begin
                    found.append({'segment': header, 'strand': strand, 'frame': frame,
                                  'start': start, 'end': end})
                    at = protein.find(residues, at + 1)
    return found


def _alternative_start_matches(contigs, residues, *, deadline=None):
    """An annotated M over a non-ATG start translates as V, L or I, so the exact
    match fails on the first residue only. Match the remainder and require the
    codon in front of it to be a recognized alternative start."""
    kept = []
    for hit in _matches(contigs, residues[1:], deadline=deadline):
        dna = contigs[hit['segment']]
        oriented = dna if hit['strand'] == '+' else reverse_complement(dna)
        # the zero-based offset of the matched remainder on the oriented strand
        begin = hit['start'] - 1 if hit['strand'] == '+' else len(dna) - hit['end']
        if begin < 3 or oriented[begin-3:begin] not in ALT_STARTS:
            continue
        if hit['strand'] == '+':
            kept.append({**hit, 'start': hit['start'] - 3})
        else:
            kept.append({**hit, 'end': hit['end'] + 3})
    return kept


def join_locus(spec, *, db=DB, nucleotide=NUCLEOTIDES, time_cap=TIME_CAP_SECONDS,
               size_cap=CONTIG_SIZE_CAP):
    """One verified locus record, or one unjoined record saying why.

    `spec` names the UViG the protein is already sourced from, the protein's own
    amino-acid sequence, and optionally its provider identifier and segment.
    """
    if not isinstance(spec, dict):
        raise ValueError('IMG/VR locus request must be an object')
    uvig = _uvig(spec.get('uvig'))
    residues = _protein(spec.get('sequence'))
    gene = _gene_id(spec.get('protein_id')) if spec.get('protein_id') else None
    deadline = time.monotonic() + float(time_cap)
    connection = _connect(db)
    try:
        contigs, refusal, headers = _segments(connection, uvig, nucleotide=nucleotide,
                                              segment=spec.get('segment'), size_cap=size_cap)
        base = {'release': RELEASE, 'uvig': uvig, 'target_protein_id': gene,
                'amino_acid_sha256': _sha256(residues), 'amino_acid_length': len(residues),
                'coordinate_convention': COORDINATE_CONVENTION,
                'annotation_source': ANNOTATION_SOURCE,
                'gene_map_available': False, 'gene_map_reason': GENE_MAP_ABSENT}
        if refusal:
            return {'records': [dict(base, joined=False, reason=refusal,
                                     segments=headers[:100], segment_count=len(headers))],
                    'coverage': 'locus_join_refused_before_reading_sequence'}
        try:
            hits = _matches(contigs, residues, deadline=deadline)
            check = 'exact'
            if not hits and residues[:1] == 'M' and len(residues) > 1:
                hits = _alternative_start_matches(contigs, residues, deadline=deadline)
                check = 'alternative_start_codon'
        except TimeoutError:
            return {'records': [dict(base, joined=False, reason='time_cap_exceeded')],
                    'coverage': 'locus_join_abandoned_at_time_cap'}
        if len(hits) != 1:
            return {'records': [dict(base, joined=False, match_count=len(hits),
                                     reason='ambiguous_translated_match' if hits
                                     else 'no_exact_translated_match')],
                    'coverage': 'locus_unjoined_identity_not_established'}
        hit = hits[0]
        dna = contigs[hit['segment']]
        window = dna[hit['start']-1:hit['end']]
        record = dict(base, joined=True, segment=hit['segment'], segment_count=len(headers),
                      start=hit['start'], end=hit['end'], strand=hit['strand'], frame=hit['frame'],
                      translated_match=check, contig_length=len(dna),
                      at_contig_start=hit['start'] <= 3, at_contig_end=hit['end'] >= len(dna) - 2,
                      annotation_sha256=_sha256(hit['segment'] + '|' + str(hit['start']) + '-'
                                                + str(hit['end']) + hit['strand'] + '|' + _sha256(window)),
                      coding_window_sha256=_sha256(window))
        return {'records': [record], 'coverage': 'verified_unique_translated_locus_on_sourced_contig'}
    finally:
        connection.close()


# ------------------------------------------------------- step 3: a bounded neighborhood

def neighborhood(spec, *, db=DB, nucleotide=NUCLEOTIDES, time_cap=TIME_CAP_SECONDS,
                 size_cap=CONTIG_SIZE_CAP):
    """Neighbouring sourced proteins of the same UViG, joined the same way.

    Every neighbour is joined by the same exact translated match, so a neighbour
    that cannot be placed is reported as missing rather than omitted. `proteins`
    carries the UViG's sourced protein records; a protein set the caller does not
    hold is missingness, not an absent gene.
    """
    if not isinstance(spec, dict):
        raise ValueError('IMG/VR neighborhood request must be an object')
    uvig = _uvig(spec.get('uvig'))
    window = spec.get('window', 10_000)
    if type(window) is not int or not 200 <= window <= WINDOW_CAP:
        raise ValueError('neighborhood window must be 200..%d bases each side' % WINDOW_CAP)
    centre = join_locus({'uvig': uvig, 'sequence': spec.get('sequence'),
                         'protein_id': spec.get('protein_id'), 'segment': spec.get('segment')},
                        db=db, nucleotide=nucleotide, time_cap=time_cap, size_cap=size_cap)
    anchor = centre['records'][0]
    if not anchor.get('joined'):
        return {'records': [anchor], 'coverage': 'neighborhood_refused_unjoined_anchor'}
    supplied = spec.get('proteins') or []
    if not isinstance(supplied, list) or len(supplied) > 400:
        raise ValueError('proteins must be a list of at most 400 sourced protein records')
    deadline = time.monotonic() + float(time_cap)
    connection = _connect(db)
    try:
        contigs, refusal, _ = _segments(connection, uvig, nucleotide=nucleotide,
                                        segment=anchor['segment'], size_cap=size_cap)
        if refusal:
            return {'records': [dict(anchor, joined=False, reason=refusal)],
                    'coverage': 'neighborhood_refused_before_reading_sequence'}
        dna = contigs[anchor['segment']]
        low = max(1, anchor['start'] - window)
        high = min(len(dna), anchor['end'] + window)
        neighbours, unplaced = [], []
        for item in supplied:
            if not isinstance(item, dict):
                raise ValueError('each sourced protein record must be an object')
            residues = _protein(item.get('sequence'))
            gene = _gene_id(item.get('protein_id')) if item.get('protein_id') else None
            if residues == _protein(spec.get('sequence')):
                continue
            try:
                hits = _matches(contigs, residues, deadline=deadline)
                check = 'exact'
                if not hits and residues[:1] == 'M' and len(residues) > 1:
                    hits = _alternative_start_matches(contigs, residues, deadline=deadline)
                    check = 'alternative_start_codon'
            except TimeoutError:
                unplaced.append({'target_protein_id': gene, 'reason': 'time_cap_exceeded'})
                break
            if len(hits) != 1:
                unplaced.append({'target_protein_id': gene,
                                 'amino_acid_sha256': _sha256(residues), 'match_count': len(hits),
                                 'reason': 'ambiguous_translated_match' if hits
                                 else 'no_exact_translated_match'})
                continue
            hit = hits[0]
            if hit['end'] < low or hit['start'] > high:
                continue
            neighbours.append({
                'target_protein_id': gene, 'amino_acid_sha256': _sha256(residues),
                'amino_acid_length': len(residues), 'start': hit['start'], 'end': hit['end'],
                'strand': hit['strand'], 'translated_match': check,
                'same_strand_as_anchor': hit['strand'] == anchor['strand'],
                'orientation': 'same' if hit['strand'] == anchor['strand'] else 'opposite',
                # bases lying between the two features, so adjacent genes read 0
                'distance_to_anchor': 0 if (hit['start'] <= anchor['end'] and hit['end'] >= anchor['start'])
                else (anchor['start'] - hit['end'] - 1 if hit['end'] < anchor['start']
                      else hit['start'] - anchor['end'] - 1),
                'side': 'overlapping' if (hit['start'] <= anchor['end'] and hit['end'] >= anchor['start'])
                else ('upstream' if (hit['end'] < anchor['start']) == (anchor['strand'] == '+') else 'downstream'),
            })
        neighbours.sort(key=lambda row: (row['start'], row['end']))
        sequence = dna[low-1:high]
        digest_material = '|'.join([RELEASE, anchor['segment'], str(low), str(high), _sha256(sequence)]
                                   + [str(row['target_protein_id']) + ':' + row['amino_acid_sha256']
                                      for row in neighbours])
        return {'records': [{
            'release': RELEASE, 'uvig': uvig, 'segment': anchor['segment'],
            'coordinate_convention': COORDINATE_CONVENTION,
            'annotation_source': ANNOTATION_SOURCE,
            'gene_map_available': False, 'gene_map_reason': GENE_MAP_ABSENT,
            'anchor': anchor, 'window_start': low, 'window_end': high,
            'window_sha256': _sha256(sequence), 'contig_length': len(dna),
            'window_truncated_at_contig_start': low == 1 and anchor['start'] - window < 1,
            'window_truncated_at_contig_end': high == len(dna) and anchor['end'] + window > len(dna),
            'neighbors': neighbours, 'neighbor_count': len(neighbours),
            'proteins_supplied': len(supplied), 'unplaced_proteins': unplaced,
            'unplaced_count': len(unplaced),
            'neighborhood_digest': _sha256(digest_material),
            'missingness': ('a protein the caller did not supply, or one that does not match this '
                            'contig exactly, is missing annotation -- not an absent gene'),
            'truth_status': 'bounded_sourced_neighborhood_not_novelty_or_function',
        }], 'coverage': 'bounded_neighborhood_on_verified_locus'}
    finally:
        connection.close()


def window_sequence(spec, *, db=DB, nucleotide=NUCLEOTIDES, size_cap=CONTIG_SIZE_CAP):
    """The neighborhood's own DNA, for the repeat screen that already exists."""
    uvig = _uvig(spec.get('uvig'))
    start, end = spec.get('start'), spec.get('end')
    if type(start) is not int or type(end) is not int or not 1 <= start <= end:
        raise ValueError('window must be one-based inclusive')
    if end - start + 1 > REPEAT_WINDOW_CAP:
        raise ValueError('repeat screen window is capped at %d bases' % REPEAT_WINDOW_CAP)
    connection = _connect(db)
    try:
        contigs, refusal, _ = _segments(connection, uvig, nucleotide=nucleotide,
                                        segment=spec.get('segment'), size_cap=size_cap)
        if refusal:
            raise ValueError(refusal)
        dna = next(iter(contigs.values()))
        if end > len(dna):
            raise ValueError('window runs past the contig as served')
        return {'uvig': uvig, 'start': start, 'end': end, 'sequence': dna[start-1:end],
                'window_sha256': _sha256(dna[start-1:end]),
                'coordinate_convention': COORDINATE_CONVENTION}
    finally:
        connection.close()


# ------------------------------------------------- step 4: a frozen cohort with its rule

def _band(value, width):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number // width)


def freeze_cohort(spec, *, db=DB):
    """Freeze a cohort from sourced UViGs, with its selection rule written down.

    One representative per declared vOTU, and the report says how much relatedness
    that removes -- and what it does not: UViGs in different vOTUs can still be
    related, so independence is not established by this step.
    """
    if not isinstance(spec, dict):
        raise ValueError('cohort request must be an object')
    rule = str(spec.get('selection_rule') or '').strip()
    if not 20 <= len(rule) <= 600:
        raise ValueError('name the selection criteria and eligible population in 20..600 characters')
    population = str(spec.get('eligible_population') or '').strip()
    if not 10 <= len(population) <= 400:
        raise ValueError('name the eligible population in 10..400 characters')
    candidates = spec.get('uvigs')
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 400:
        raise ValueError('uvigs must be 1..400 sourced identifiers')
    candidates = sorted({_uvig(value) for value in candidates})
    pilot_size = spec.get('pilot_size', 6)
    holdout_size = spec.get('holdout_size', 18)
    for size in (pilot_size, holdout_size):
        if type(size) is not int or size < 1:
            raise ValueError('pilot_size and holdout_size must be positive integers')
    if pilot_size + holdout_size > COHORT_CAP:
        raise ValueError('the first cap is %d biological neighborhoods in total' % COHORT_CAP)
    backgrounds_per_case = spec.get('backgrounds_per_case', 1)
    if type(backgrounds_per_case) is not int or not 0 <= backgrounds_per_case <= 3:
        raise ValueError('backgrounds_per_case must be 0..3')
    connection = _connect(db)
    try:
        rows = {}
        for identifier in candidates:
            row = connection.execute(
                'SELECT uvig,votu,length,topology,ecosystem,estimated_completeness FROM uvig WHERE uvig=?',
                (identifier,)).fetchone()
            if row is not None:
                rows[identifier] = dict(row)
        absent = [x for x in candidates if x not in rows]
        by_votu = {}
        for identifier in sorted(rows):
            by_votu.setdefault(rows[identifier]['votu'] or '', []).append(identifier)
        representatives, dropped = [], []
        for votu in sorted(by_votu):
            members = by_votu[votu]
            representatives.append(members[0])
            dropped.extend(members[1:])
        eligible = len(representatives)
        if eligible < pilot_size + holdout_size:
            return {'records': [{
                'release': RELEASE, 'frozen': False,
                'reason': 'too_few_independent_votu_representatives',
                'representatives_available': eligible,
                'requested_total': pilot_size + holdout_size,
                'same_votu_copies_removed': len(dropped),
                'absent_from_metadata_index': absent,
                'sampling_limitation': ('matched independent groups could not be obtained at the '
                                        'requested size; report the limitation rather than relaxing it'),
            }], 'coverage': 'cohort_not_frozen_sampling_limitation'}
        pilot = representatives[:pilot_size]
        holdout = representatives[pilot_size:pilot_size + holdout_size]
        backgrounds = {}
        if backgrounds_per_case:
            for identifier in pilot + holdout:
                case = rows[identifier]
                matched = connection.execute(
                    'SELECT uvig,votu,length,topology,ecosystem,estimated_completeness FROM uvig '
                    'WHERE topology=? AND votu IS NOT ? AND uvig NOT IN (%s) '
                    'ORDER BY uvig LIMIT 400' % ','.join('?' for _ in (pilot + holdout)),
                    tuple([case['topology'], case['votu']] + pilot + holdout)).fetchall()
                chosen = []
                for candidate in matched:
                    if candidate['votu'] in {rows[x]['votu'] for x in pilot + holdout}:
                        continue
                    if _band(candidate['length'], 2000) != _band(case['length'], 2000):
                        continue
                    if (str(candidate['ecosystem'] or '').split(';')[0]
                            != str(case['ecosystem'] or '').split(';')[0]):
                        continue
                    if _band(candidate['estimated_completeness'], 25) != _band(
                            case['estimated_completeness'], 25):
                        continue
                    chosen.append(candidate['uvig'])
                    if len(chosen) >= backgrounds_per_case:
                        break
                backgrounds[identifier] = chosen
        material = json.dumps({'release': RELEASE, 'rule': rule, 'population': population,
                               'pilot': pilot, 'holdout': holdout, 'backgrounds': backgrounds},
                              sort_keys=True)
        return {'records': [{
            'release': RELEASE, 'frozen': True, 'selection_rule': rule,
            'eligible_population': population,
            'pilot': pilot, 'holdout': holdout,
            'matched_backgrounds': backgrounds,
            'matched_on': ['topology', 'length_band_2000', 'ecosystem_top_level',
                           'completeness_band_25'],
            'candidates_supplied': len(candidates),
            'absent_from_metadata_index': absent,
            'same_votu_copies_removed': len(dropped),
            'same_votu_copies': dropped,
            'relatedness_removed': ('one representative per declared vOTU, so same-vOTU copies '
                                    'cannot inflate the independent count'),
            'relatedness_not_removed': ('UViGs in different vOTUs may still be related; this step '
                                        'does not establish independent viral groups'),
            'cohort_digest': _sha256(material),
            'cap': COHORT_CAP,
            'truth_status': 'frozen_cohort_definition_not_a_biological_conclusion',
        }], 'coverage': 'frozen_cohort_with_declared_sampling_rule'}
    finally:
        connection.close()


# --------------------------------------- step 5 (part): a null for repeat propensity

def repeat_null(sequence, *, trials=50, seed=0, scan=None, **options):
    """Observed repeat-array candidates against composition-preserving shuffles.

    The shuffle keeps base composition and destroys arrangement, so it answers one
    narrow question: how often does this screen fire on sequence of this composition
    at all. It is not a p-value for a biological claim, and it does not model the
    local structure real genomes have.
    """
    sequence = str(sequence or '').upper()
    if type(trials) is not int or not 1 <= trials <= 200:
        raise ValueError('trials must be 1..200')
    if scan is None:
        from lab_genome_mining import scan_repeat_arrays as scan
    observed = scan(sequence, **options)
    bases = list(sequence)
    generator = random.Random(seed)
    counts = []
    best = []
    for _ in range(trials):
        generator.shuffle(bases)
        result = scan(''.join(bases), **options)
        counts.append(result['candidate_count'])
        best.append(max((row['copies'] for row in result['candidate_arrays']), default=0))
    hits = sum(1 for value in counts if value >= observed['candidate_count'])
    observed_best = max((row['copies'] for row in observed['candidate_arrays']), default=0)
    copy_hits = sum(1 for value in best if value >= observed_best)
    return {
        'observed_candidate_count': observed['candidate_count'],
        'observed_max_copies': observed_best,
        'trials': trials, 'seed': seed,
        'null_candidate_counts_at_least_observed': hits,
        'null_max_copies_at_least_observed': copy_hits,
        'null_fraction_at_least_observed': round(hits / trials, 4),
        'null_fraction_max_copies_at_least_observed': round(copy_hits / trials, 4),
        'null_model': 'composition_preserving_uniform_shuffle_of_this_window',
        'truth_status': 'screen_propensity_null_not_a_biological_significance_test',
        'limitations': [
            'a uniform shuffle has none of the local structure real genomes have',
            'a low fraction says the arrangement is unusual for this composition, not that it is functional',
            'the shuffle null does not address homology, family independence or literature novelty',
        ],
    }


# ------------------------------------ a bounded cohort protein pass (offline, explicit)

def cohort_proteins(uvigs, *, proteins=PROTEINS_GZ, opener=None, limit_per_uvig=400):
    """One bounded streaming pass over the release proteins, keeping only a frozen cohort.

    The release has no per-UViG protein index, and building a general one would mean
    a full pass and tens of gigabytes. A frozen cohort is at most 24 neighborhoods,
    so one pass that keeps only those UViGs' proteins is the smaller, honest option.
    This reads the release and writes nothing.
    """
    wanted = {_uvig(value) for value in uvigs}
    if not 1 <= len(wanted) <= 200:
        raise ValueError('a cohort protein pass takes 1..200 sourced UViGs')
    found = {name: [] for name in sorted(wanted)}
    truncated = set()
    if opener is None:
        def opener(path):
            return gzip.open(path, 'rt')
    header, chunks = None, []

    def flush():
        if header is None:
            return
        name = header.split('|', 1)[0]
        if name in found:
            if len(found[name]) >= limit_per_uvig:
                truncated.add(name)
            else:
                found[name].append({'protein_id': header.split('|')[-1],
                                    'header': header, 'sequence': ''.join(chunks)})
    with opener(proteins) as handle:
        for line in handle:
            line = line.strip()
            if line.startswith('>'):
                flush()
                header, chunks = line[1:], []
            elif header is not None:
                chunks.append(line)
        flush()
    return {'release': RELEASE, 'uvigs': sorted(wanted),
            'proteins': found,
            'protein_counts': {name: len(rows) for name, rows in found.items()},
            'uvigs_without_proteins': [name for name, rows in found.items() if not rows],
            'truncated_at_limit': sorted(truncated),
            'coverage': 'single_bounded_pass_over_release_proteins_for_a_frozen_cohort'}


def query(spec, **kwargs):
    """The Lab-facing door: one bounded operation per request."""
    if not isinstance(spec, dict):
        raise ValueError('IMG/VR locus query must be an object')
    operation = spec.get('operation')
    if operation == 'locus_join':
        return join_locus(spec, **kwargs)
    if operation == 'neighborhood':
        return neighborhood(spec, **kwargs)
    if operation == 'cohort_freeze':
        return freeze_cohort(spec, **{k: v for k, v in kwargs.items() if k == 'db'})
    raise ValueError('unsupported IMG/VR locus operation')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('inventory')
    query_parser = sub.add_parser('query')
    query_parser.add_argument('json')
    args = parser.parse_args()
    result = inventory() if args.command == 'inventory' else query(json.loads(args.json))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()

"""One Atlas SDK query; parent enforces whole-process deadline. No implicit key lookup."""
import importlib.metadata
import json
import math
from pathlib import Path
import sys


def finite_values(value):
    if isinstance(value, list): return [finite_values(x) for x in value]
    return None if isinstance(value, float) and not math.isfinite(value) else value


CELL_LIMIT = 100000


def strongest_tracks(raw, limit=CELL_LIMIT):
    """Column indexes of the tracks with the largest absolute score, as many as fit the limit, in track order."""
    import numpy as np
    raw = np.asarray(raw, dtype=float)
    keep = max(1, limit // max(1, raw.shape[0]))
    strength = np.nan_to_num(np.abs(raw), nan=0.0).max(axis=0)
    return sorted(int(i) for i in np.argsort(-strength, kind='stable')[:keep])


def run(query, key):
    from alphagenome.atlas import atlas
    from alphagenome.data import genome
    from lab_sources import validate_atlas
    query = validate_atlas(query)
    client = atlas.create(key, timeout=15)
    metadata = client.scorer_metadata()
    if query.get('operation') == 'metadata':
        return {'scores': {}, 'sdk_version': importlib.metadata.version('alphagenome'),
                'scorer_metadata': {s: {'name': m.name, 'is_signed': m.is_signed,
                                        'track_count':len(m.track_metadata),
                                        'track_metadata_excerpt':json.loads(m.track_metadata.head(8).to_json(orient='split',default_handler=str))}
                                    for s,m in metadata.items()}}
    # Names he gave that Atlas does not have are replaced by real ones, and the receipt says so.
    wanted = [s for s in query['scorers'] if s in metadata]
    chosen_by_lab = len(wanted) != len(query['scorers']) or not wanted
    if not wanted:
        names = sorted(metadata)
        preferred = [n for n in names if any(k in n.upper() for k in ('RNA', 'ATAC', 'DNASE', 'CAGE'))]
        wanted = (preferred or names)[:2]
    query = dict(query, scorers=wanted)
    values = client.query_interval(genome.Interval(query['chromosome'], query['start'], query['end']),
                                   requested_scorers=query['scorers'], ontology_terms=query.get('ontology_terms'),
                                   gene_ids=query.get('gene_ids'), max_workers=1, progress_bar=False)
    scores = {}
    for name, matrix in values.items():
        raw = matrix.X.toarray() if hasattr(matrix.X, 'toarray') else matrix.X
        total = matrix.n_vars
        if matrix.n_obs * matrix.n_vars > CELL_LIMIT:
            # A whole ATAC scorer over a 10 bp window is more tracks than the Lab keeps. It used to fail the
            # question outright (2026-09-29); now the tracks with the strongest signal are kept, and it says so.
            keep = strongest_tracks(raw, CELL_LIMIT)
            matrix, raw = matrix[:, keep], raw[:, keep]
        scores[name] = {'scores': finite_values(raw.tolist()),
                        'variants': [{'chromosome': v.chromosome, 'position': v.position,
                                      'reference_bases': v.reference_bases, 'alternate_bases': v.alternate_bases}
                                     for v in matrix.obs['variant']] if 'variant' in matrix.obs else [], 'obs': json.loads(matrix.obs.to_json(orient='split', default_handler=str)),
                        'var': json.loads(matrix.var.to_json(orient='split', default_handler=str)),
                        'quantiles': finite_values(matrix.layers['quantiles'].tolist()) if 'quantiles' in matrix.layers else None,
                        'tracks_kept': matrix.n_vars, 'tracks_total': total,
                        **({'tracks_selection': 'strongest_absolute_signal'} if matrix.n_vars < total else {})}
    return {'scores': scores, 'sdk_version': importlib.metadata.version('alphagenome'),
            'scorer_metadata': {s: {'name': metadata[s].name, 'is_signed': metadata[s].is_signed}
                                for s in query['scorers']},
            'available_scorers': sorted(metadata)[:40], 'scorers_chosen_by_lab': chosen_by_lab}


def failure(exc, key):
    """Why the query failed, in one line the Lab can show; the key never appears in it."""
    text = '%s: %s' % (type(exc).__name__, ' '.join(str(exc).split()))
    if key: text = text.replace(key, '[key]')
    return text[:300]


if __name__ == '__main__':
    key = Path(sys.argv[1]).read_text().strip()
    try:
        result = run(json.loads(sys.stdin.read(8192)), key)
        encoded = json.dumps(result, allow_nan=False)
        if len(encoded.encode()) > 2*1024*1024: raise ValueError('Atlas response too large')
    except Exception as exc:
        # The parent discards stderr, so a failure said nothing but "RuntimeError" in the Lab (2026-09-29).
        Path(sys.argv[2]).with_name('error.txt').write_text(failure(exc, key))
        sys.exit(1)
    Path(sys.argv[2]).write_text(encoded)

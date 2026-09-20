"""One Atlas SDK query; parent enforces whole-process deadline. No implicit key lookup."""
import importlib.metadata
import json
import math
from pathlib import Path
import sys


def finite_values(value):
    if isinstance(value, list): return [finite_values(x) for x in value]
    return None if isinstance(value, float) and not math.isfinite(value) else value


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
    if any(s not in metadata for s in query['scorers']):
        raise ValueError('unknown Atlas scorer; obtain actual names from scorer_metadata')
    values = client.query_interval(genome.Interval(query['chromosome'], query['start'], query['end']),
                                   requested_scorers=query['scorers'], ontology_terms=query.get('ontology_terms'),
                                   gene_ids=query.get('gene_ids'), max_workers=1, progress_bar=False)
    scores = {}
    for name, matrix in values.items():
        if matrix.n_obs * matrix.n_vars > 100000: raise ValueError('score matrix exceeds Lab limit')
        raw = matrix.X.toarray() if hasattr(matrix.X, 'toarray') else matrix.X
        scores[name] = {'scores': finite_values(raw.tolist()),
                        'variants': [{'chromosome': v.chromosome, 'position': v.position,
                                      'reference_bases': v.reference_bases, 'alternate_bases': v.alternate_bases}
                                     for v in matrix.obs['variant']] if 'variant' in matrix.obs else [], 'obs': json.loads(matrix.obs.to_json(orient='split', default_handler=str)),
                        'var': json.loads(matrix.var.to_json(orient='split', default_handler=str)),
                        'quantiles': finite_values(matrix.layers['quantiles'].tolist()) if 'quantiles' in matrix.layers else None}
    return {'scores': scores, 'sdk_version': importlib.metadata.version('alphagenome'),
            'scorer_metadata': {s: {'name': metadata[s].name, 'is_signed': metadata[s].is_signed}
                                for s in query['scorers']}}


if __name__ == '__main__':
    result = run(json.loads(sys.stdin.read(8192)), Path(sys.argv[1]).read_text().strip())
    encoded = json.dumps(result, allow_nan=False)
    if len(encoded.encode()) > 2*1024*1024: raise ValueError('Atlas response too large')
    Path(sys.argv[2]).write_text(encoded)

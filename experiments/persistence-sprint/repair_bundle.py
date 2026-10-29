#!/usr/bin/env python3
"""Copy a pre-window bundle with complete capture code; never refit parameters."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
from bundle import package_code
from data import TZ, boundary, scratch, sha, write_json


def repair(source, output, now=None, review_fixes=False):
    source = Path(source)
    manifest = json.loads((source/'manifest.json').read_text())
    now = datetime.now(TZ) if now is None else now
    if now.timestamp() >= boundary(manifest['week'][0]):
        raise ValueError('week already opened; cannot repair bundle')
    if (source/'evaluation-attempt.json').exists():
        raise ValueError('evaluation already attempted')
    artifacts = {'incumbent.npz': manifest['incumbent_sha256'],
                 'present-refit.npz': manifest['present_refit_sha256']}
    for candidate in manifest['candidates']:
        artifacts.update({f"candidate-{candidate['round']}/{name}": expected
                          for name, expected in candidate['files'].items()})
    for name, expected in manifest['code'].items():
        if sha(source/'code'/name) != expected:
            raise ValueError('source code hash mismatch')
    for name, expected in artifacts.items():
        if sha(source/name) != expected:
            raise ValueError('source artifact hash mismatch')
    # Default repair is packaging-only. The explicitly authorized pre-window
    # review revision also changes collector entry enforcement and removes 24h
    # from pass eligibility. Fitting and state mathematics remain identical.
    repo = Path(__file__).resolve().parents[2]
    fixed=('data.py','run.py','scan.py') if review_fixes else ('collect.py','data.py','run.py','scan.py','evaluate.py')
    for name in fixed:
        relative = 'experiments/persistence-sprint/'+name
        if sha(repo/relative) != manifest['code'][relative]:
            raise ValueError('scientific executable changed: '+name)
    out = scratch(output)
    for name, expected in artifacts.items():
        dest = out/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, dest)
        assert sha(dest) == expected
    package_code(out/'code', repo)
    updated = dict(manifest, sealed_at=now.isoformat(),
                   supersedes_manifest_sha256=sha(source/'manifest.json'),
                   repair='Capture dependency packaging and scratch guard only; all scientific executables, fitted artifacts and statistical rules unchanged',
                   code={str(p.relative_to(out/'code')): sha(p)
                         for p in sorted((out/'code').rglob('*.py'))})
    if review_fixes:
        updated.update(review_revision=1,
                       pass_horizons_seconds=[600,1800,3600,10800,21600,43200],
                       descriptive_horizons_seconds=[86400],
                       repair='Authorized pre-window review: 24h descriptive only, unchanged 56-contrast interval adjustment; collector requires guarded launcher; all fitted artifacts unchanged')
    write_json(out/'manifest.json', updated)
    return {'manifest_sha256': sha(out/'manifest.json'), 'artifact_count': len(artifacts),
            'all_artifacts_byte_identical': True, 'week': updated['week'],
            'supersedes_manifest_sha256': updated['supersedes_manifest_sha256']}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--from-sealed', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--review-fixes',action='store_true')
    args = ap.parse_args()
    print(json.dumps(repair(args.from_sealed, args.out, review_fixes=args.review_fixes)))

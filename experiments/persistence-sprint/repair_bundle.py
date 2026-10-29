#!/usr/bin/env python3
"""Copy a pre-window bundle with complete capture code; never refit parameters."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
from bundle import package_code
from data import TZ, boundary, scratch, sha, write_json


def repair(source, output, now=None):
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
    # Scientific executable remains byte-identical. Only the launcher and
    # packaging/tests may change in this operational repair.
    repo = Path(__file__).resolve().parents[2]
    for name in ('collect.py', 'data.py', 'run.py', 'scan.py', 'evaluate.py'):
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
    write_json(out/'manifest.json', updated)
    return {'manifest_sha256': sha(out/'manifest.json'), 'artifact_count': len(artifacts),
            'all_artifacts_byte_identical': True, 'week': updated['week'],
            'supersedes_manifest_sha256': updated['supersedes_manifest_sha256']}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--from-sealed', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    print(json.dumps(repair(args.from_sealed, args.out)))

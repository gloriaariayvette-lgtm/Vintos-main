#!/usr/bin/env python3
"""Read-only sync of Gloria's AprilTag map to the camera mamepa on the Studio.

Reads memory/apriltag-memories.json (and, for entries that point into a store under memory/, the linked record) with
the same rules as native_video.tag_memory, writes the resolved map to a private temporary file, and copies it to the
target host and path with mode 600 in a 700 directory. Her files are never written. Nothing about the records is
printed: only counts."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_video


def resolve(tag_map=None):
    """{key: {'label', 'text'} | {'label', 'record'}} for every entry whose memory is found."""
    tag_map = native_video.load_tag_map() if tag_map is None else tag_map
    out = {}
    for key in sorted(tag_map):
        family, _, tag_id = key.partition(':')
        hit = native_video.tag_memory({'family': family, 'tag_id': tag_id}, tag_map)
        if not hit['found']:
            continue
        mem = hit['memory']
        out[key] = {'label': hit['label'], 'text': mem['text']} if set(mem) == {'text'} else {'label': hit['label'], 'record': mem}
    return {'_note': 'resolved read-only copy; do not edit here', **out}, len(tag_map)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', required=True, help='ssh host alias of the Studio')
    ap.add_argument('--dest', required=True, help='private path on that host, e.g. private-vintos/apriltag-memories.json')
    args = ap.parse_args()
    resolved, entries = resolve()
    with tempfile.NamedTemporaryFile('w', delete=False, prefix='tagmap-', suffix='.json') as f:
        os.chmod(f.name, 0o600)
        json.dump(resolved, f)
    try:
        folder = os.path.dirname(args.dest) or '.'
        script = 'umask 077; mkdir -p %s && chmod 700 %s && cat > %s.tmp && chmod 600 %s.tmp && mv %s.tmp %s' % (
            (folder, folder) + (args.dest,) * 4)
        with open(f.name, 'rb') as src:
            subprocess.run(['ssh', args.host, script], stdin=src, check=True)
    finally:
        os.unlink(f.name)
    print(json.dumps({'map_entries': entries, 'resolved': len(resolved) - 1,
                      'map_exists': os.path.exists(native_video.TAG_MAP)}))


if __name__ == '__main__':
    main()
